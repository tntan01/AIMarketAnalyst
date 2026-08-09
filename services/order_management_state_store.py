"""Durable, account-scoped persistence for order-management state.

The store is deliberately independent from the Qt UI and MT5 service models.
Callers may pass small local dataclasses, dictionaries, or any account object
that exposes ``broker``, ``server`` and ``login`` attributes.

Writes are synchronous: a complete JSON document is flushed to a temporary
file in the destination directory and atomically replaced.  A previous
generation is kept as a backup.  Invalid JSON/schema data is never treated as
an empty position set; it is quarantined and reported through an explicit
status instead.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import threading
from typing import Any, Protocol

from config.paths import app_data_dir


ORDER_MANAGEMENT_SCHEMA = "ama.order-management-state"
ORDER_MANAGEMENT_SCHEMA_VERSION = 2
DEFAULT_STATE_FILENAME = "be_trailing_state.json"

_MAX_TICKET = (1 << 64) - 1
_MAX_SYMBOL_LENGTH = 64
_ACCOUNT_FIELDS = frozenset({"broker", "server", "login", "fingerprint"})
_DOCUMENT_FIELDS = frozenset(
    {"schema", "schema_version", "saved_at_utc", "account", "positions"}
)
_POSITION_FIELDS = frozenset(
    {"ticket", "symbol", "side", "original_sl", "trailing"}
)


class AccountIdentity(Protocol):
    """Minimal account contract accepted by :class:`OrderManagementStateStore`."""

    broker: object
    server: object
    login: object


class OrderManagementStateStatus(str, Enum):
    SAVED = "saved"
    LOADED = "loaded"
    RECOVERED_FROM_BACKUP = "recovered_from_backup"
    FLUSHED = "flushed"
    NOT_FOUND = "not_found"
    ACCOUNT_MISMATCH = "account_mismatch"
    CORRUPT_QUARANTINED = "corrupt_quarantined"
    UNSUPPORTED_VERSION = "unsupported_version"
    VALIDATION_ERROR = "validation_error"
    IO_ERROR = "io_error"


@dataclass(frozen=True, slots=True)
class AccountFingerprint:
    """Stable identity for one broker account.

    Broker and server are compared case-insensitively; login remains exact.
    All three components are stored alongside the digest so a corrupted or
    tampered identity can be detected while loading.
    """

    broker: str
    server: str
    login: str

    @classmethod
    def from_value(
        cls,
        value: AccountFingerprint | AccountIdentity | Mapping[str, object],
    ) -> AccountFingerprint:
        if isinstance(value, cls):
            broker, server, login = value.broker, value.server, value.login
        elif isinstance(value, Mapping):
            broker = value.get("broker")
            server = value.get("server")
            login = value.get("login")
        else:
            broker = getattr(value, "broker", None)
            server = getattr(value, "server", None)
            login = getattr(value, "login", None)
        return cls(
            broker=_required_account_text(broker, "broker"),
            server=_required_account_text(server, "server"),
            login=_required_login(login),
        )

    @property
    def digest(self) -> str:
        canonical = json.dumps(
            [self.broker.casefold(), self.server.casefold(), self.login],
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(canonical).hexdigest()}"

    def to_document(self) -> dict[str, str]:
        return {
            "broker": self.broker,
            "server": self.server,
            "login": self.login,
            "fingerprint": self.digest,
        }


@dataclass(frozen=True, slots=True)
class ManagedPositionState:
    """Broker position state needed to restore BE/trailing management."""

    ticket: int
    symbol: str
    side: str
    original_sl: float | None = None
    trailing: dict[str, Any] = field(default_factory=dict)

    def to_document(self) -> dict[str, Any]:
        return {
            "ticket": self.ticket,
            "symbol": self.symbol,
            "side": self.side,
            "original_sl": self.original_sl,
            "trailing": _json_mapping_copy(self.trailing, field_name="trailing"),
        }


@dataclass(frozen=True, slots=True)
class OrderManagementStateSnapshot:
    account: AccountFingerprint
    positions: tuple[ManagedPositionState, ...]
    saved_at_utc: str = ""

    def by_ticket(self) -> dict[int, ManagedPositionState]:
        return {position.ticket: position for position in self.positions}

    def trailing_configs(self) -> dict[int, dict[str, Any]]:
        """Return UI-compatible copies without coupling this store to Qt."""

        result: dict[int, dict[str, Any]] = {}
        for position in self.positions:
            config = _json_mapping_copy(
                position.trailing,
                field_name=f"positions[{position.ticket}].trailing",
            )
            config.update(
                {
                    "position_id": position.ticket,
                    "symbol": position.symbol,
                    "side": position.side,
                }
            )
            result[position.ticket] = config
        return result

    def original_sl_by_ticket(self) -> dict[int, float]:
        return {
            position.ticket: position.original_sl
            for position in self.positions
            if position.original_sl is not None
        }


@dataclass(frozen=True, slots=True)
class OrderManagementStateResult:
    status: OrderManagementStateStatus
    path: Path
    snapshot: OrderManagementStateSnapshot | None = None
    backup_path: Path | None = None
    quarantined_paths: tuple[Path, ...] = ()
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.status in {
            OrderManagementStateStatus.SAVED,
            OrderManagementStateStatus.LOADED,
            OrderManagementStateStatus.RECOVERED_FROM_BACKUP,
            OrderManagementStateStatus.FLUSHED,
        }


class _StateValidationError(ValueError):
    pass


class _UnsupportedSchemaVersion(_StateValidationError):
    def __init__(self, version: object) -> None:
        super().__init__(
            f"Unsupported order-management schema version: {version!r}; "
            f"expected {ORDER_MANAGEMENT_SCHEMA_VERSION}."
        )
        self.version = version


class OrderManagementStateStore:
    """Synchronous v2 state store with backup and corrupt quarantine."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = Path(path) if path is not None else app_data_dir() / DEFAULT_STATE_FILENAME
        self.backup_path = self.path.with_name(f"{self.path.name}.bak")
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()

    def save(
        self,
        *,
        account: AccountFingerprint | AccountIdentity | Mapping[str, object],
        positions: (
            Mapping[object, ManagedPositionState | Mapping[str, object]]
            | Iterable[ManagedPositionState | Mapping[str, object]]
        ),
    ) -> OrderManagementStateResult:
        """Synchronously validate, flush and atomically replace the state."""

        return self.save_sync(account=account, positions=positions)

    def save_sync(
        self,
        *,
        account: AccountFingerprint | AccountIdentity | Mapping[str, object],
        positions: (
            Mapping[object, ManagedPositionState | Mapping[str, object]]
            | Iterable[ManagedPositionState | Mapping[str, object]]
        ),
    ) -> OrderManagementStateResult:
        try:
            normalized_account = AccountFingerprint.from_value(account)
            normalized_positions = _normalize_positions(positions)
            saved_at = _utc_iso(self._clock())
            document = _snapshot_document(
                normalized_account,
                normalized_positions,
                saved_at=saved_at,
            )
            payload = (
                json.dumps(
                    document,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                )
                + "\n"
            ).encode("utf-8")
        except (_StateValidationError, TypeError, ValueError, OverflowError) as exc:
            return self._result(
                OrderManagementStateStatus.VALIDATION_ERROR,
                error=str(exc),
            )

        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                if self.path.exists():
                    previous = self.path.read_bytes()
                    self._atomic_write_bytes(self.backup_path, previous)
                else:
                    # Keep a recoverable generation even after the first save.
                    self._atomic_write_bytes(self.backup_path, payload)
                self._atomic_write_bytes(self.path, payload)
            except OSError as exc:
                return self._result(
                    OrderManagementStateStatus.IO_ERROR,
                    error=f"Could not save order-management state: {exc}",
                )

        return self._result(OrderManagementStateStatus.SAVED)

    def load(
        self,
        *,
        account: AccountFingerprint | AccountIdentity | Mapping[str, object],
    ) -> OrderManagementStateResult:
        """Load state only when its broker/server/login fingerprint matches."""

        try:
            expected_account = AccountFingerprint.from_value(account)
        except (_StateValidationError, TypeError, ValueError) as exc:
            return self._result(
                OrderManagementStateStatus.VALIDATION_ERROR,
                error=str(exc),
            )

        with self._lock:
            if not self.path.exists():
                if not self.backup_path.exists():
                    return self._result(OrderManagementStateStatus.NOT_FOUND)
                return self._load_backup(
                    expected_account,
                    quarantined_paths=(),
                    primary_error="Primary state file is missing.",
                )

            try:
                snapshot = self._read_snapshot(self.path)
            except _UnsupportedSchemaVersion as exc:
                return self._result(
                    OrderManagementStateStatus.UNSUPPORTED_VERSION,
                    error=str(exc),
                )
            except (json.JSONDecodeError, UnicodeDecodeError, _StateValidationError) as exc:
                return self._quarantine_and_recover(
                    self.path,
                    expected_account,
                    error=f"Primary state is corrupt: {exc}",
                )
            except OSError as exc:
                return self._result(
                    OrderManagementStateStatus.IO_ERROR,
                    error=f"Could not read order-management state: {exc}",
                )

            if snapshot.account.digest != expected_account.digest:
                return self._result(
                    OrderManagementStateStatus.ACCOUNT_MISMATCH,
                    error=(
                        "Stored order-management state belongs to a different "
                        "broker/server/login account."
                    ),
                )
            return self._result(
                OrderManagementStateStatus.LOADED,
                snapshot=snapshot,
            )

    def flush(self) -> OrderManagementStateResult:
        """Synchronously fsync the current primary file.

        ``save``/``save_sync`` already flush before atomic replacement.  This
        method is provided for an explicit shutdown checkpoint without a
        hidden debounce queue.
        """

        with self._lock:
            if not self.path.exists():
                return self._result(OrderManagementStateStatus.NOT_FOUND)
            try:
                # Windows requires a writable descriptor for ``os.fsync``.
                # Opening without truncation preserves the persisted bytes.
                with self.path.open("r+b") as handle:
                    os.fsync(handle.fileno())
                self._fsync_parent_directory()
            except OSError as exc:
                return self._result(
                    OrderManagementStateStatus.IO_ERROR,
                    error=f"Could not flush order-management state: {exc}",
                )
        return self._result(OrderManagementStateStatus.FLUSHED)

    def _load_backup(
        self,
        expected_account: AccountFingerprint,
        *,
        quarantined_paths: tuple[Path, ...],
        primary_error: str,
    ) -> OrderManagementStateResult:
        if not self.backup_path.exists():
            return self._result(
                OrderManagementStateStatus.CORRUPT_QUARANTINED,
                quarantined_paths=quarantined_paths,
                error=primary_error,
            )
        try:
            snapshot = self._read_snapshot(self.backup_path)
        except _UnsupportedSchemaVersion as exc:
            return self._result(
                OrderManagementStateStatus.CORRUPT_QUARANTINED,
                quarantined_paths=quarantined_paths,
                error=f"{primary_error} Backup cannot be used: {exc}",
            )
        except (json.JSONDecodeError, UnicodeDecodeError, _StateValidationError) as exc:
            try:
                quarantined_backup = self._quarantine(self.backup_path)
            except (OSError, _StateValidationError) as quarantine_error:
                return self._result(
                    OrderManagementStateStatus.IO_ERROR,
                    quarantined_paths=quarantined_paths,
                    error=(
                        f"{primary_error} Backup is corrupt ({exc}) and could "
                        f"not be quarantined: {quarantine_error}"
                    ),
                )
            return self._result(
                OrderManagementStateStatus.CORRUPT_QUARANTINED,
                quarantined_paths=quarantined_paths + (quarantined_backup,),
                error=f"{primary_error} Backup is also corrupt: {exc}",
            )
        except OSError as exc:
            return self._result(
                OrderManagementStateStatus.IO_ERROR,
                quarantined_paths=quarantined_paths,
                error=f"{primary_error} Could not read backup: {exc}",
            )

        if snapshot.account.digest != expected_account.digest:
            return self._result(
                OrderManagementStateStatus.ACCOUNT_MISMATCH,
                quarantined_paths=quarantined_paths,
                error=(
                    f"{primary_error} Backup belongs to a different "
                    "broker/server/login account."
                ),
            )
        return self._result(
            OrderManagementStateStatus.RECOVERED_FROM_BACKUP,
            snapshot=snapshot,
            quarantined_paths=quarantined_paths,
            error=primary_error,
        )

    def _quarantine_and_recover(
        self,
        source: Path,
        expected_account: AccountFingerprint,
        *,
        error: str,
    ) -> OrderManagementStateResult:
        try:
            quarantined = self._quarantine(source)
        except (OSError, _StateValidationError) as exc:
            return self._result(
                OrderManagementStateStatus.IO_ERROR,
                error=f"{error} Quarantine failed: {exc}",
            )
        return self._load_backup(
            expected_account,
            quarantined_paths=(quarantined,),
            primary_error=error,
        )

    def _read_snapshot(self, source: Path) -> OrderManagementStateSnapshot:
        raw = source.read_bytes()
        document = json.loads(raw.decode("utf-8"))
        return _snapshot_from_document(document)

    def _quarantine(self, source: Path) -> Path:
        timestamp = _filename_timestamp(self._clock())
        candidate = source.with_name(f"{source.name}.corrupt.{timestamp}")
        index = 1
        while candidate.exists():
            candidate = source.with_name(
                f"{source.name}.corrupt.{timestamp}.{index}"
            )
            index += 1
        os.replace(source, candidate)
        self._fsync_parent_directory()
        return candidate

    def _atomic_write_bytes(self, target: Path, payload: bytes) -> None:
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{target.name}.",
                suffix=".tmp",
                dir=target.parent,
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, target)
            temporary_path = None
            self._fsync_parent_directory()
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    def _fsync_parent_directory(self) -> None:
        # Windows does not support opening directory handles through os.open;
        # flushed file contents plus os.replace are the strongest portable
        # guarantees available there.
        if os.name == "nt":
            return
        descriptor = os.open(self.path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _result(
        self,
        status: OrderManagementStateStatus,
        *,
        snapshot: OrderManagementStateSnapshot | None = None,
        quarantined_paths: tuple[Path, ...] = (),
        error: str = "",
    ) -> OrderManagementStateResult:
        return OrderManagementStateResult(
            status=status,
            path=self.path,
            snapshot=snapshot,
            backup_path=self.backup_path,
            quarantined_paths=quarantined_paths,
            error=error,
        )


def _snapshot_document(
    account: AccountFingerprint,
    positions: tuple[ManagedPositionState, ...],
    *,
    saved_at: str,
) -> dict[str, Any]:
    return {
        "schema": ORDER_MANAGEMENT_SCHEMA,
        "schema_version": ORDER_MANAGEMENT_SCHEMA_VERSION,
        "saved_at_utc": saved_at,
        "account": account.to_document(),
        "positions": {
            str(position.ticket): position.to_document()
            for position in positions
        },
    }


def _snapshot_from_document(document: object) -> OrderManagementStateSnapshot:
    if not isinstance(document, dict):
        raise _StateValidationError("State document must be a JSON object.")
    _require_exact_fields(document, _DOCUMENT_FIELDS, "document")
    if document.get("schema") != ORDER_MANAGEMENT_SCHEMA:
        raise _StateValidationError("State document has an invalid schema name.")
    version = document.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise _StateValidationError("schema_version must be an integer.")
    if version != ORDER_MANAGEMENT_SCHEMA_VERSION:
        raise _UnsupportedSchemaVersion(version)

    saved_at = _validated_utc_iso(document.get("saved_at_utc"))
    account = _account_from_document(document.get("account"))
    raw_positions = document.get("positions")
    if not isinstance(raw_positions, dict):
        raise _StateValidationError("positions must be a JSON object keyed by ticket.")

    positions: list[ManagedPositionState] = []
    for raw_key, raw_position in raw_positions.items():
        if not isinstance(raw_key, str) or not raw_key.isdigit():
            raise _StateValidationError("Every position key must be a decimal ticket.")
        ticket = _validated_ticket(raw_key)
        if raw_key != str(ticket):
            raise _StateValidationError(
                f"Position key {raw_key!r} is not a canonical ticket."
            )
        if not isinstance(raw_position, dict):
            raise _StateValidationError(
                f"positions[{raw_key}] must be a JSON object."
            )
        _require_exact_fields(
            raw_position,
            _POSITION_FIELDS,
            f"positions[{raw_key}]",
        )
        if _validated_ticket(raw_position.get("ticket")) != ticket:
            raise _StateValidationError(
                f"positions[{raw_key}].ticket does not match its key."
            )
        positions.append(
            _normalize_position(
                raw_position,
                ticket_hint=ticket,
                require_nested_trailing=True,
            )
        )

    return OrderManagementStateSnapshot(
        account=account,
        positions=tuple(sorted(positions, key=lambda item: item.ticket)),
        saved_at_utc=saved_at,
    )


def _account_from_document(value: object) -> AccountFingerprint:
    if not isinstance(value, dict):
        raise _StateValidationError("account must be a JSON object.")
    _require_exact_fields(value, _ACCOUNT_FIELDS, "account")
    account = AccountFingerprint.from_value(value)
    stored_digest = value.get("fingerprint")
    if not isinstance(stored_digest, str) or stored_digest != account.digest:
        raise _StateValidationError(
            "Stored account fingerprint does not match broker/server/login."
        )
    return account


def _normalize_positions(
    positions: (
        Mapping[object, ManagedPositionState | Mapping[str, object]]
        | Iterable[ManagedPositionState | Mapping[str, object]]
    ),
) -> tuple[ManagedPositionState, ...]:
    if isinstance(positions, Mapping):
        raw_items = list(positions.items())
    elif isinstance(positions, (str, bytes, bytearray)):
        raise _StateValidationError("positions must be a mapping or iterable of records.")
    else:
        try:
            raw_items = [(None, value) for value in positions]
        except TypeError as exc:
            raise _StateValidationError(
                "positions must be a mapping or iterable of records."
            ) from exc

    normalized: list[ManagedPositionState] = []
    seen: set[int] = set()
    for ticket_hint, raw_position in raw_items:
        position = _normalize_position(raw_position, ticket_hint=ticket_hint)
        if position.ticket in seen:
            raise _StateValidationError(
                f"Duplicate managed position ticket: {position.ticket}."
            )
        seen.add(position.ticket)
        normalized.append(position)
    return tuple(sorted(normalized, key=lambda item: item.ticket))


def _normalize_position(
    value: ManagedPositionState | Mapping[str, object],
    *,
    ticket_hint: object = None,
    require_nested_trailing: bool = False,
) -> ManagedPositionState:
    if isinstance(value, ManagedPositionState):
        raw: Mapping[str, object] = {
            "ticket": value.ticket,
            "symbol": value.symbol,
            "side": value.side,
            "original_sl": value.original_sl,
            "trailing": value.trailing,
        }
    elif isinstance(value, Mapping):
        raw = value
    else:
        raise _StateValidationError("Each managed position must be a mapping or dataclass.")

    raw_ticket = raw.get("ticket", raw.get("position_id", ticket_hint))
    ticket = _validated_ticket(raw_ticket)
    if "ticket" in raw and "position_id" in raw:
        position_id = _validated_ticket(raw.get("position_id"))
        if position_id != ticket:
            raise _StateValidationError(
                f"Position ticket {ticket} does not match position_id {position_id}."
            )
    if ticket_hint is not None and _validated_ticket(ticket_hint) != ticket:
        raise _StateValidationError(
            f"Position ticket {ticket} does not match mapping key {ticket_hint!r}."
        )
    symbol = _validated_symbol(raw.get("symbol"))
    side = _validated_side(raw.get("side"))
    original_sl = _validated_original_sl(raw.get("original_sl"))

    if require_nested_trailing or "trailing" in raw:
        trailing_value = raw.get("trailing")
    else:
        reserved = {"ticket", "position_id", "symbol", "side", "original_sl"}
        trailing_value = {key: item for key, item in raw.items() if key not in reserved}
    trailing = _json_mapping_copy(
        trailing_value,
        field_name=f"positions[{ticket}].trailing",
    )
    return ManagedPositionState(
        ticket=ticket,
        symbol=symbol,
        side=side,
        original_sl=original_sl,
        trailing=trailing,
    )


def _validated_ticket(value: object) -> int:
    if isinstance(value, bool):
        raise _StateValidationError("Position ticket must be a positive integer.")
    try:
        ticket = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise _StateValidationError("Position ticket must be a positive integer.") from exc
    if isinstance(value, float) and not value.is_integer():
        raise _StateValidationError("Position ticket must be a positive integer.")
    if ticket <= 0 or ticket > _MAX_TICKET:
        raise _StateValidationError(
            f"Position ticket must be between 1 and {_MAX_TICKET}."
        )
    return ticket


def _validated_symbol(value: object) -> str:
    if not isinstance(value, str):
        raise _StateValidationError("Position symbol must be a string.")
    symbol = value.strip()
    if not symbol or symbol == "--" or len(symbol) > _MAX_SYMBOL_LENGTH:
        raise _StateValidationError(
            f"Position symbol must contain 1-{_MAX_SYMBOL_LENGTH} characters."
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in symbol):
        raise _StateValidationError("Position symbol contains control characters.")
    return symbol


def _validated_side(value: object) -> str:
    if not isinstance(value, str):
        raise _StateValidationError("Position side must be 'buy' or 'sell'.")
    side = value.strip().lower()
    if side not in {"buy", "sell"}:
        raise _StateValidationError("Position side must be 'buy' or 'sell'.")
    return side


def _validated_original_sl(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise _StateValidationError("original_sl must be a finite positive number or null.")
    try:
        stop_loss = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise _StateValidationError(
            "original_sl must be a finite positive number or null."
        ) from exc
    if not math.isfinite(stop_loss) or stop_loss <= 0:
        raise _StateValidationError(
            "original_sl must be a finite positive number or null."
        )
    return stop_loss


def _json_mapping_copy(value: object, *, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _StateValidationError(f"{field_name} must be a JSON object.")
    if any(not isinstance(key, str) for key in value):
        raise _StateValidationError(f"{field_name} keys must be strings.")
    try:
        encoded = json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )
        decoded = json.loads(encoded)
    except (TypeError, ValueError, OverflowError, json.JSONDecodeError) as exc:
        raise _StateValidationError(
            f"{field_name} must contain only finite JSON values: {exc}"
        ) from exc
    if not isinstance(decoded, dict):
        raise _StateValidationError(f"{field_name} must be a JSON object.")
    return decoded


def _required_account_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise _StateValidationError(f"Account {field_name} must be a non-empty string.")
    text = value.strip()
    if not text or any(ord(character) < 32 for character in text):
        raise _StateValidationError(f"Account {field_name} must be a non-empty string.")
    return text


def _required_login(value: object) -> str:
    if value is None or isinstance(value, bool):
        raise _StateValidationError("Account login must be non-empty.")
    login = str(value).strip()
    if not login or any(ord(character) < 32 for character in login):
        raise _StateValidationError("Account login must be non-empty.")
    return login


def _require_exact_fields(
    value: Mapping[str, object],
    expected: frozenset[str],
    field_name: str,
) -> None:
    keys = set(value)
    if keys != expected:
        missing = sorted(expected - keys)
        unexpected = sorted(keys - expected)
        details: list[str] = []
        if missing:
            details.append(f"missing={missing}")
        if unexpected:
            details.append(f"unexpected={unexpected}")
        raise _StateValidationError(
            f"{field_name} has invalid fields ({', '.join(details)})."
        )


def _utc_iso(value: datetime) -> str:
    if not isinstance(value, datetime):
        raise _StateValidationError("State clock must return datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise _StateValidationError("State clock must return a timezone-aware datetime.")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _validated_utc_iso(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _StateValidationError("saved_at_utc must be an ISO-8601 timestamp.")
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _StateValidationError(
            "saved_at_utc must be an ISO-8601 timestamp."
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _StateValidationError("saved_at_utc must include a timezone.")
    return parsed.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _filename_timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise _StateValidationError("State clock must return a timezone-aware datetime.")
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")


__all__ = [
    "AccountFingerprint",
    "AccountIdentity",
    "DEFAULT_STATE_FILENAME",
    "ManagedPositionState",
    "ORDER_MANAGEMENT_SCHEMA",
    "ORDER_MANAGEMENT_SCHEMA_VERSION",
    "OrderManagementStateResult",
    "OrderManagementStateSnapshot",
    "OrderManagementStateStatus",
    "OrderManagementStateStore",
]
