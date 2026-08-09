from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

import services.order_management_state_store as state_store_module
from services.order_management_state_store import (
    AccountFingerprint,
    ManagedPositionState,
    ORDER_MANAGEMENT_SCHEMA,
    ORDER_MANAGEMENT_SCHEMA_VERSION,
    OrderManagementStateStatus,
    OrderManagementStateStore,
)


FIXED_NOW = datetime(2026, 8, 9, 12, 34, 56, 123456, tzinfo=UTC)


def _account(
    *,
    broker: str = "Example Broker Ltd",
    server: str = "Example-Demo",
    login: int = 12345678,
) -> dict[str, object]:
    return {"broker": broker, "server": server, "login": login}


def _position(
    ticket: int = 101,
    *,
    symbol: str = "EURUSDm",
    side: str = "buy",
    original_sl: float = 1.098,
    current_sl: float = 1.1002,
) -> ManagedPositionState:
    return ManagedPositionState(
        ticket=ticket,
        symbol=symbol,
        side=side,
        original_sl=original_sl,
        trailing={
            "enabled": True,
            "be_done": True,
            "current_sl": current_sl,
            "trail_mode": "wide",
        },
    )


def _store(path: Path) -> OrderManagementStateStore:
    return OrderManagementStateStore(path, clock=lambda: FIXED_NOW)


def test_v2_round_trip_is_account_scoped_and_synchronous(tmp_path: Path) -> None:
    path = tmp_path / "be_trailing_state.json"
    store = _store(path)
    positions = {
        202: {
            "position_id": 202,
            "symbol": "USDJPYm",
            "side": "SELL",
            "original_sl": 151.25,
            # A flattened legacy-style config is accepted and nested safely.
            "enabled": True,
            "be_done": False,
            "trail_mode": "tight",
        },
        101: _position(),
    }

    saved = store.save_sync(account=_account(), positions=positions)

    assert saved.status is OrderManagementStateStatus.SAVED
    assert saved.ok is True
    assert saved.error == ""
    assert path.is_file()
    assert store.backup_path.is_file()
    assert not list(tmp_path.glob("*.tmp"))

    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["schema"] == ORDER_MANAGEMENT_SCHEMA
    assert document["schema_version"] == ORDER_MANAGEMENT_SCHEMA_VERSION
    assert document["saved_at_utc"] == "2026-08-09T12:34:56.123456Z"
    assert document["account"]["broker"] == "Example Broker Ltd"
    assert document["account"]["server"] == "Example-Demo"
    assert document["account"]["login"] == "12345678"
    assert document["account"]["fingerprint"].startswith("sha256:")
    assert document["positions"]["202"]["ticket"] == 202
    assert document["positions"]["202"]["side"] == "sell"

    # Broker/server matching is case-insensitive; login remains part of it.
    loaded = store.load(
        account=_account(broker="example broker ltd", server="example-demo")
    )

    assert loaded.status is OrderManagementStateStatus.LOADED
    assert loaded.ok is True
    assert loaded.snapshot is not None
    assert [position.ticket for position in loaded.snapshot.positions] == [101, 202]
    assert loaded.snapshot.by_ticket()[202].symbol == "USDJPYm"
    assert loaded.snapshot.by_ticket()[202].side == "sell"
    assert loaded.snapshot.by_ticket()[202].trailing["trail_mode"] == "tight"
    assert loaded.snapshot.original_sl_by_ticket() == {101: 1.098, 202: 151.25}
    assert loaded.snapshot.trailing_configs()[101]["position_id"] == 101

    flushed = store.flush()
    assert flushed.status is OrderManagementStateStatus.FLUSHED
    assert flushed.ok is True


def test_account_fingerprint_uses_broker_server_and_login() -> None:
    baseline = AccountFingerprint.from_value(_account())
    same_case_insensitive = AccountFingerprint.from_value(
        _account(broker="example broker ltd", server="example-demo")
    )
    different_broker = AccountFingerprint.from_value(_account(broker="Other Broker"))
    different_server = AccountFingerprint.from_value(_account(server="Example-Live"))
    different_login = AccountFingerprint.from_value(_account(login=87654321))

    assert baseline.digest == same_case_insensitive.digest
    assert baseline.digest != different_broker.digest
    assert baseline.digest != different_server.digest
    assert baseline.digest != different_login.digest


@pytest.mark.parametrize(
    "wrong_account",
    [
        _account(broker="Other Broker"),
        _account(server="Example-Live"),
        _account(login=87654321),
    ],
)
def test_load_never_returns_state_for_another_account(
    tmp_path: Path,
    wrong_account: dict[str, object],
) -> None:
    path = tmp_path / "state.json"
    store = _store(path)
    assert store.save(account=_account(), positions=[_position()]).ok

    result = store.load(account=wrong_account)

    assert result.status is OrderManagementStateStatus.ACCOUNT_MISMATCH
    assert result.ok is False
    assert result.snapshot is None
    assert "different" in result.error.lower()
    assert result.quarantined_paths == ()
    assert path.exists()


def test_backup_keeps_previous_generation_and_recovers_corrupt_primary(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.json"
    store = _store(path)
    assert store.save(account=_account(), positions=[_position(current_sl=1.1002)]).ok
    assert store.save(account=_account(), positions=[_position(current_sl=1.1025)]).ok

    backup_document = json.loads(store.backup_path.read_text(encoding="utf-8"))
    assert backup_document["positions"]["101"]["trailing"]["current_sl"] == 1.1002

    path.write_text('{"schema":', encoding="utf-8")
    recovered = store.load(account=_account())

    assert recovered.status is OrderManagementStateStatus.RECOVERED_FROM_BACKUP
    assert recovered.ok is True
    assert recovered.snapshot is not None
    assert recovered.snapshot.by_ticket()[101].trailing["current_sl"] == 1.1002
    assert recovered.error.startswith("Primary state is corrupt")
    assert len(recovered.quarantined_paths) == 1
    quarantined = recovered.quarantined_paths[0]
    assert quarantined.is_file()
    assert quarantined.name.startswith("state.json.corrupt.20260809T123456123456Z")
    assert not path.exists()


def test_missing_primary_recovers_matching_backup(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    store = _store(path)
    assert store.save(account=_account(), positions=[_position()]).ok
    path.unlink()

    result = store.load(account=_account())

    assert result.status is OrderManagementStateStatus.RECOVERED_FROM_BACKUP
    assert result.snapshot is not None
    assert result.snapshot.by_ticket()[101].symbol == "EURUSDm"
    assert "missing" in result.error.lower()


def test_corrupt_primary_without_backup_is_quarantined(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_bytes(b"\xff\xfe not utf-8")
    store = _store(path)

    result = store.load(account=_account())

    assert result.status is OrderManagementStateStatus.CORRUPT_QUARANTINED
    assert result.ok is False
    assert result.snapshot is None
    assert "corrupt" in result.error.lower()
    assert len(result.quarantined_paths) == 1
    assert result.quarantined_paths[0].read_bytes() == b"\xff\xfe not utf-8"
    assert not path.exists()


def test_corrupt_backup_is_also_quarantined_with_explicit_status(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.json"
    store = _store(path)
    path.write_text("not-json", encoding="utf-8")
    store.backup_path.write_text("also-not-json", encoding="utf-8")

    result = store.load(account=_account())

    assert result.status is OrderManagementStateStatus.CORRUPT_QUARANTINED
    assert result.snapshot is None
    assert "also corrupt" in result.error.lower()
    assert len(result.quarantined_paths) == 2
    assert all(item.exists() for item in result.quarantined_paths)


def test_unsupported_schema_is_reported_without_quarantine_or_backup_fallback(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.json"
    store = _store(path)
    assert store.save(account=_account(), positions=[_position()]).ok
    document = json.loads(path.read_text(encoding="utf-8"))
    document["schema_version"] = 1
    path.write_text(json.dumps(document), encoding="utf-8")

    result = store.load(account=_account())

    assert result.status is OrderManagementStateStatus.UNSUPPORTED_VERSION
    assert result.snapshot is None
    assert "version" in result.error.lower()
    assert result.quarantined_paths == ()
    assert path.exists()


def test_tampered_account_fingerprint_is_quarantined(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    store = _store(path)
    assert store.save(account=_account(), positions=[_position()]).ok
    store.backup_path.unlink()
    document = json.loads(path.read_text(encoding="utf-8"))
    document["account"]["broker"] = "Tampered Broker"
    path.write_text(json.dumps(document), encoding="utf-8")

    result = store.load(account=_account())

    assert result.status is OrderManagementStateStatus.CORRUPT_QUARANTINED
    assert "fingerprint" in result.error.lower()
    assert len(result.quarantined_paths) == 1


@pytest.mark.parametrize(
    ("positions", "expected_error"),
    [
        ({0: {"symbol": "EURUSD", "side": "buy"}}, "ticket"),
        ({1: {"ticket": 2, "symbol": "EURUSD", "side": "buy"}}, "match"),
        (
            {
                1: {
                    "ticket": 1,
                    "position_id": 2,
                    "symbol": "EURUSD",
                    "side": "buy",
                }
            },
            "position_id",
        ),
        ({1: {"ticket": 1, "symbol": "", "side": "buy"}}, "symbol"),
        ({1: {"ticket": 1, "symbol": "EURUSD", "side": "hold"}}, "side"),
        (
            {
                1: {
                    "ticket": 1,
                    "symbol": "EURUSD",
                    "side": "buy",
                    "original_sl": float("nan"),
                }
            },
            "original_sl",
        ),
        (
            {
                1: {
                    "ticket": 1,
                    "symbol": "EURUSD",
                    "side": "buy",
                    "trailing": {"bad": object()},
                }
            },
            "json",
        ),
    ],
)
def test_invalid_position_is_rejected_before_any_write(
    tmp_path: Path,
    positions: dict[object, dict[str, object]],
    expected_error: str,
) -> None:
    path = tmp_path / "state.json"
    store = _store(path)

    result = store.save(account=_account(), positions=positions)

    assert result.status is OrderManagementStateStatus.VALIDATION_ERROR
    assert result.ok is False
    assert expected_error in result.error.lower()
    assert not path.exists()
    assert not store.backup_path.exists()


def test_invalid_stored_position_is_quarantined_instead_of_loaded_empty(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.json"
    store = _store(path)
    assert store.save(account=_account(), positions=[_position()]).ok
    store.backup_path.unlink()
    document = json.loads(path.read_text(encoding="utf-8"))
    document["positions"]["101"]["side"] = "unknown"
    path.write_text(json.dumps(document), encoding="utf-8")

    result = store.load(account=_account())

    assert result.status is OrderManagementStateStatus.CORRUPT_QUARANTINED
    assert result.snapshot is None
    assert "side" in result.error.lower()
    assert len(result.quarantined_paths) == 1


def test_save_and_load_io_failures_are_explicit(tmp_path: Path) -> None:
    parent_file = tmp_path / "not-a-directory"
    parent_file.write_text("occupied", encoding="utf-8")
    save_store = _store(parent_file / "state.json")

    save_result = save_store.save(account=_account(), positions=[_position()])

    assert save_result.status is OrderManagementStateStatus.IO_ERROR
    assert save_result.error

    directory_path = tmp_path / "directory-state"
    directory_path.mkdir()
    load_store = _store(directory_path)

    load_result = load_store.load(account=_account())

    assert load_result.status is OrderManagementStateStatus.IO_ERROR
    assert load_result.error
    assert load_result.quarantined_paths == ()


def test_failed_atomic_replace_preserves_previous_primary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "state.json"
    store = _store(path)
    assert store.save(account=_account(), positions=[_position(current_sl=1.1002)]).ok
    previous_bytes = path.read_bytes()
    real_replace = state_store_module.os.replace

    def fail_primary_replace(source: object, destination: object) -> None:
        if Path(destination) == path:
            raise OSError("simulated replace failure")
        real_replace(source, destination)

    monkeypatch.setattr(state_store_module.os, "replace", fail_primary_replace)

    failed = store.save(
        account=_account(),
        positions=[_position(current_sl=1.105)],
    )

    assert failed.status is OrderManagementStateStatus.IO_ERROR
    assert "simulated replace failure" in failed.error
    assert path.read_bytes() == previous_bytes
    assert json.loads(path.read_text(encoding="utf-8"))["positions"]["101"][
        "trailing"
    ]["current_sl"] == 1.1002
    assert not list(tmp_path.glob("*.tmp"))


def test_not_found_and_invalid_account_have_explicit_status(tmp_path: Path) -> None:
    store = _store(tmp_path / "missing.json")

    missing = store.load(account=_account())
    invalid = store.load(account={"broker": "", "server": "x", "login": 1})
    flush_missing = store.flush()

    assert missing.status is OrderManagementStateStatus.NOT_FOUND
    assert invalid.status is OrderManagementStateStatus.VALIDATION_ERROR
    assert invalid.error
    assert flush_missing.status is OrderManagementStateStatus.NOT_FOUND
