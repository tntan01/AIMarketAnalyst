"""Scanner version alias migration (P1; mono-version rename 2026-08-17).

When the "v4" moniker was dropped from the persisted schema markers, every
strict reader was loosened so it accepts BOTH the new bare value AND the legacy
"…-v4" / "…-v1" value written before the rename.  These tests prove the
migration contract:

* a row / composition result / snapshot envelope that carries the NEW bare
  version values round-trips unchanged (writes the new value);
* the SAME payload re-labelled to a LEGACY value still loads — data saved before
  the rename is never REFUSED on read;
* a version value that is neither the new value nor a real legacy value is
  still refused (the alias only opens the exact old value, not any string).

Readers canonicalize the accepted legacy identity to the current bare value on
load (stringly a typed read, persisted bytes are never rewritten).
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from core.reason_codes import SCANNER_VERSION_MISMATCH
from core.scanner_composition import (
    COMPOSITION_POLICY_LEGACY_VERSION,
    COMPOSITION_POLICY_VERSION,
    ScannerCompositionResult,
)
from core.scanner_row import (
    RowContractError,
    SCANNER_ROW_LEGACY_VERSION,
    SCANNER_ROW_VERSION,
    scanner_row_from_composition,
    scanner_row_from_dict,
)
from core.scanner_snapshot import (
    MODE_FULL,
    SCANNER_SNAPSHOT_ENVELOPE_LEGACY_VERSION,
    SCANNER_SNAPSHOT_ENVELOPE_VERSION,
    build_snapshot_envelope,
    snapshot_envelope_from_dict,
)

from tests.scanner_testkit import build_snapshot, compose

ENVELOPE_KEY = "envelope_schema_version"


def _composition() -> ScannerCompositionResult:
    return compose(build_snapshot())


class TestRowAlias:
    def test_row_writes_new_bare_value(self) -> None:
        row = scanner_row_from_composition(_composition())
        assert row.row_version == SCANNER_ROW_VERSION == "scanner-row"

    def test_legacy_row_version_still_loads(self) -> None:
        d = scanner_row_from_composition(_composition()).to_dict()
        # What was saved before the rename carried the legacy value.
        legacy = deepcopy(d)
        legacy["row_version"] = SCANNER_ROW_LEGACY_VERSION
        loaded = scanner_row_from_dict(legacy)  # must NOT refuse
        new_row = scanner_row_from_dict(d)
        # Read-only: the loaded object is canonical and equal to the new-value one.
        assert loaded.to_dict() == new_row.to_dict()

    def test_neither_new_nor_legacy_row_version_refused(self) -> None:
        d = scanner_row_from_composition(_composition()).to_dict()
        for bad in ("scanner-v99-row-v1", "scanner-v4-row-v2", "row", SCANNER_ROW_VERSION + "-x"):
            payload = deepcopy(d)
            payload["row_version"] = bad
            with pytest.raises(RowContractError) as exc:
                scanner_row_from_dict(payload)
            assert exc.value.code == SCANNER_VERSION_MISMATCH


class TestCompositionAlias:
    def test_composition_writes_new_bare_value(self) -> None:
        d = _composition().to_dict()
        assert d["composition_version"] == COMPOSITION_POLICY_VERSION == "scanner-composition"

    def test_legacy_composition_version_still_loads(self) -> None:
        d = _composition().to_dict()
        legacy = deepcopy(d)
        legacy["composition_version"] = COMPOSITION_POLICY_LEGACY_VERSION
        loaded = ScannerCompositionResult.from_dict(legacy)  # must NOT refuse
        # Loaded object re-serializes to the canonical new value.
        assert loaded.to_dict()["composition_version"] == COMPOSITION_POLICY_VERSION

    def test_neither_composition_version_refused(self) -> None:
        d = _composition().to_dict()
        for bad in ("scanner-composition-v99", COMPOSITION_POLICY_VERSION + "-x", "composition"):
            payload = deepcopy(d)
            payload["composition_version"] = bad
            with pytest.raises(ValueError):
                ScannerCompositionResult.from_dict(payload)


class TestSnapshotEnvelopeAlias:
    def test_envelope_writes_new_bare_value(self) -> None:
        env = build_snapshot_envelope(_composition(), mode=MODE_FULL).to_dict()
        assert env[ENVELOPE_KEY] == SCANNER_SNAPSHOT_ENVELOPE_VERSION

    def test_legacy_envelope_version_still_loads(self) -> None:
        d = build_snapshot_envelope(_composition(), mode=MODE_FULL).to_dict()
        legacy = deepcopy(d)
        legacy[ENVELOPE_KEY] = SCANNER_SNAPSHOT_ENVELOPE_LEGACY_VERSION
        loaded = snapshot_envelope_from_dict(legacy)  # must NOT refuse
        new_envelope = snapshot_envelope_from_dict(d)
        # The envelope reader preserves the exact version label it was given
        # (no canonical rewrite); the rest of the content is identical.
        a, b = deepcopy(dict(loaded.to_dict())), deepcopy(dict(new_envelope.to_dict()))
        del a[ENVELOPE_KEY]
        del b[ENVELOPE_KEY]
        assert a == b
        assert loaded.to_dict()[ENVELOPE_KEY] == SCANNER_SNAPSHOT_ENVELOPE_LEGACY_VERSION

    def test_neither_envelope_version_refused(self) -> None:
        d = build_snapshot_envelope(_composition(), mode=MODE_FULL).to_dict()
        for bad in ("scanner-snapshot-envelope-v99", SCANNER_SNAPSHOT_ENVELOPE_VERSION + "-x"):
            payload = deepcopy(d)
            payload[ENVELOPE_KEY] = bad
            with pytest.raises(ValueError):
                snapshot_envelope_from_dict(payload)