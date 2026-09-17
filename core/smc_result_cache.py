"""Narrow result-cache seam for one canonical SMC evaluation (tasks 118/120).

This module is a **cache record store**, not a cache policy: it writes one
canonical SMC result under a caller-supplied snapshot identity and reads it back
only when the stored record can still be trusted.  It is deliberately NOT wired
into Scanner or Analyze — the live routes keep evaluating from source, and
nothing here changes scoring, M15, lifecycle, selection, risk or execution.

A hit requires ALL of:

* the record exists and parses;
* the envelope carries the *running* rule identity — every marker including the
  selection policy and the recomputed digest (``smc_identity_mismatch_codes``);
* the stored snapshot identity equals the one being asked for;
* the embedded result block is itself ``canonical_compatible``.

Anything else is a **miss with a reason**.  There is no last-known-good path and
no fallback to an older record: a miss never returns a result, so a stale or
tampered artifact can never be served as a current evaluation (compatibility
spec §4.1 invalidation, §5 reader policy).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import gzip
import hashlib
import json
from typing import Any, Mapping

from core.smc_persistence import (
    SMC_PAYLOAD_CANONICAL,
    classify_persisted_smc,
    smc_identity_mismatch_codes,
    smc_persistence_identity,
)


SMC_RESULT_CACHE_VERSION = "smc-result-cache-v1"
SMC_RESULT_CACHE_IDENTITY_KEY = "cache_identity"
SMC_RESULT_CACHE_SNAPSHOT_KEY = "snapshot_identity"
SMC_RESULT_CACHE_RECORD_KEY = "record"
_CACHE_DIRECTORY = ("cache", "smc_results")

# Absent is a normal, expected miss: nothing has been cached for this input yet.
SMC_CACHE_MISS_ABSENT = "SMC_CACHE_MISS_ABSENT"
# The artifact is unreadable or is not the envelope this seam writes.
SMC_CACHE_MISS_RECORD_CORRUPTED = "SMC_CACHE_MISS_RECORD_CORRUPTED"
# The envelope is readable but was written under other rules / another input.
SMC_CACHE_MISS_IDENTITY_MISMATCH = "SMC_CACHE_MISS_IDENTITY_MISMATCH"
SMC_CACHE_MISS_SNAPSHOT_MISMATCH = "SMC_CACHE_MISS_SNAPSHOT_MISMATCH"
# The envelope is fine but the result it carries is not usable as current.
SMC_CACHE_MISS_RECORD_INVALID = "SMC_CACHE_MISS_RECORD_INVALID"


@dataclass(frozen=True, slots=True)
class SmcCacheLookup:
    """Outcome of one cache read.  A miss never carries a result."""

    hit: bool
    reason_codes: tuple[str, ...] = ()
    record: Mapping[str, Any] | None = None
    identity_mismatch_codes: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        """Whether the caller may use ``record`` as a current evaluation."""

        return self.hit and self.record is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "hit": self.hit,
            "reason_codes": list(self.reason_codes),
            "identity_mismatch_codes": list(self.identity_mismatch_codes),
        }


def smc_result_cache_path(root: Path, *, snapshot_identity: str) -> Path:
    """Where one cached result lives.

    The filename is a digest of the snapshot identity, so two different inputs
    can never share a slot and a caller cannot address another input's record.
    """

    normalized = str(snapshot_identity or "").strip()
    if not normalized:
        raise ValueError("SMC result cache requires a snapshot identity")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return Path(root).joinpath(*_CACHE_DIRECTORY, f"{digest}.json.gz")


def write_smc_result_record(
    root: Path,
    *,
    snapshot_identity: str,
    record: Mapping[str, Any],
) -> Path:
    """Atomically store one canonical result under its snapshot identity.

    Writing is unconditional: the caller has just evaluated the input, so the
    record is by construction the current one.  Reading is where trust is
    decided.
    """

    normalized = str(snapshot_identity or "").strip()
    if not normalized:
        raise ValueError("SMC result cache requires a snapshot identity")
    if not isinstance(record, Mapping) or not record:
        raise ValueError("SMC result cache requires a result record")

    envelope = {
        "cache_contract_version": SMC_RESULT_CACHE_VERSION,
        SMC_RESULT_CACHE_IDENTITY_KEY: smc_persistence_identity(),
        SMC_RESULT_CACHE_SNAPSHOT_KEY: normalized,
        SMC_RESULT_CACHE_RECORD_KEY: json.loads(
            json.dumps(dict(record), default=str)
        ),
    }
    path = smc_result_cache_path(root, snapshot_identity=normalized)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    with gzip.open(temporary, "wt", encoding="utf-8") as handle:
        json.dump(envelope, handle, ensure_ascii=False, indent=None)
    temporary.replace(path)
    return path


def read_smc_result_record(root: Path, *, snapshot_identity: str) -> SmcCacheLookup:
    """Read the cached result for one input, or explain why it cannot be used."""

    path = smc_result_cache_path(root, snapshot_identity=snapshot_identity)
    if not path.is_file():
        return SmcCacheLookup(hit=False, reason_codes=(SMC_CACHE_MISS_ABSENT,))

    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            envelope = json.load(handle)
    except (OSError, ValueError, EOFError):
        return SmcCacheLookup(
            hit=False, reason_codes=(SMC_CACHE_MISS_RECORD_CORRUPTED,)
        )
    if not isinstance(envelope, Mapping):
        return SmcCacheLookup(
            hit=False, reason_codes=(SMC_CACHE_MISS_RECORD_CORRUPTED,)
        )
    if envelope.get("cache_contract_version") != SMC_RESULT_CACHE_VERSION:
        return SmcCacheLookup(
            hit=False, reason_codes=(SMC_CACHE_MISS_RECORD_INVALID,)
        )

    identity = envelope.get(SMC_RESULT_CACHE_IDENTITY_KEY)
    identity_codes = smc_identity_mismatch_codes(identity)
    if identity_codes:
        # Another rule identity produced this record (older scorer/selection) or
        # the identity was tampered with.  Either way it is not this input's
        # current result, and there is no fallback that would make it one.
        return SmcCacheLookup(
            hit=False,
            reason_codes=(SMC_CACHE_MISS_IDENTITY_MISMATCH,),
            identity_mismatch_codes=identity_codes,
        )

    stored_identity = envelope.get(SMC_RESULT_CACHE_SNAPSHOT_KEY)
    if not isinstance(stored_identity, str) or stored_identity != str(
        snapshot_identity or ""
    ).strip():
        return SmcCacheLookup(
            hit=False, reason_codes=(SMC_CACHE_MISS_SNAPSHOT_MISMATCH,)
        )

    record = envelope.get(SMC_RESULT_CACHE_RECORD_KEY)
    if not isinstance(record, Mapping):
        return SmcCacheLookup(
            hit=False, reason_codes=(SMC_CACHE_MISS_RECORD_CORRUPTED,)
        )
    compat = classify_persisted_smc({"smc_scoring": record})
    if compat.status != SMC_PAYLOAD_CANONICAL:
        # The envelope is current but the result it carries is not readable as a
        # current evaluation, so it is not served.
        return SmcCacheLookup(
            hit=False,
            reason_codes=(SMC_CACHE_MISS_RECORD_INVALID, *compat.reason_codes),
        )
    return SmcCacheLookup(hit=True, record=record)


__all__ = [
    "SMC_CACHE_MISS_ABSENT",
    "SMC_CACHE_MISS_IDENTITY_MISMATCH",
    "SMC_CACHE_MISS_RECORD_CORRUPTED",
    "SMC_CACHE_MISS_RECORD_INVALID",
    "SMC_CACHE_MISS_SNAPSHOT_MISMATCH",
    "SMC_RESULT_CACHE_IDENTITY_KEY",
    "SMC_RESULT_CACHE_RECORD_KEY",
    "SMC_RESULT_CACHE_SNAPSHOT_KEY",
    "SMC_RESULT_CACHE_VERSION",
    "SmcCacheLookup",
    "read_smc_result_record",
    "smc_result_cache_path",
    "write_smc_result_record",
]
