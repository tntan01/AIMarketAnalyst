"""Task 23: Location detail propagation through canonical consumers."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from core.location_engine import (
    DEFAULT_LOCATION_CONFIG,
    LocationResult,
    LocationZone,
)
from core.scanner_composition import CompositionInputError
from core.scanner_row import scanner_row_from_composition, scanner_row_from_dict
from core.scanner_snapshot import (
    MODE_COMPACT,
    MODE_FULL,
    build_snapshot_envelope,
    snapshot_envelope_from_dict,
)
from core.scanner_v4_models import (
    CanonicalPairSnapshot,
    ScannerContractError,
)

from tests.test_scanner_composition import _compose, _snapshot

NOW = _snapshot().captured_at


def _location_detail(side: str, raw: int) -> LocationResult:
    role = "support" if side == "buy" else "resistance"
    anchor = LocationZone(
        id=f"{role}:2026-08-13T08:00:00Z",
        role=role,
        low=99.9 if side == "buy" else 100.1,
        high=100.0 if side == "buy" else 100.2,
        formed_at=NOW - timedelta(hours=8),
        confirmed_at=NOW - timedelta(hours=4),
        formation_atr=0.2,
        status="ACTIVE",
    )
    return LocationResult(
        side=side,
        raw=raw,
        status="LIMITED_CONTEXT",
        reason_codes=("LOCATION_LIMITED_CONTEXT",),
        reference_price=100.0,
        reference_closed_at=NOW - timedelta(hours=1),
        anchor=anchor,
        obstacle=None,
        distance_atr=0.25,
        clearance_atr=None,
        proximity_factor=0.75,
        clearance_factor=0.5,
        model_version=DEFAULT_LOCATION_CONFIG.model_version,
        config_used=DEFAULT_LOCATION_CONFIG,
        raw_exact=float(raw),
        cutoff=NOW,
        h4_bars_considered=80,
    )


def _composition_with_location_detail():
    base = _snapshot()
    buy = replace(
        base.buy,
        location_detail=_location_detail(
            "buy", base.buy.technical_raws["location"]
        ),
    )
    sell = replace(
        base.sell,
        location_detail=_location_detail(
            "sell", base.sell.technical_raws["location"]
        ),
    )
    return _compose(replace(base, buy=buy, sell=sell))


def test_location_detail_reaches_canonical_full_and_compact_consumers():
    composition = _composition_with_location_detail()
    canonical_payload = composition.canonical.to_dict()

    for side in ("buy", "sell"):
        detail = canonical_payload["side_scores"][side]["location_detail"]
        assert detail["side"] == side
        assert detail["raw"] == canonical_payload["side_scores"][side]["technical_breakdown"]["location"]["raw"]

    canonical_restored = CanonicalPairSnapshot.from_dict(canonical_payload)
    assert canonical_restored == composition.canonical

    full = build_snapshot_envelope(composition, mode=MODE_FULL)
    full_restored = snapshot_envelope_from_dict(full.to_dict())
    assert full_restored.to_dict() == full.to_dict()
    assert "location_detail" in full_restored.composition["canonical"]["side_scores"]["buy"]

    compact = build_snapshot_envelope(composition, mode=MODE_COMPACT)
    compact_restored = snapshot_envelope_from_dict(compact.to_dict())
    for side in compact_restored.side_scores:
        assert side.location_status == "LIMITED_CONTEXT"
        assert side.location_raw is not None
        assert side.location_reason_codes == ("LOCATION_LIMITED_CONTEXT",)

    row = scanner_row_from_composition(composition)
    row_restored = scanner_row_from_dict(row.to_dict())
    for side in row_restored.side_scores:
        assert side.location_status == "LIMITED_CONTEXT"
        assert side.location_raw is not None
        assert side.location_reason_codes == ("LOCATION_LIMITED_CONTEXT",)


@pytest.mark.parametrize(
    ("status", "raw"),
    [
        ("UNAVAILABLE", 25),
        ("CONFLICT", 25),
        ("EVALUATED", 99),
        ("EVALUATED", None),
        ("NOT_A_LOCATION_STATUS", 0),
    ],
)
def test_location_summary_readers_reject_invalid_status_and_raw(status, raw):
    composition = _composition_with_location_detail()

    compact = build_snapshot_envelope(composition, mode=MODE_COMPACT).to_dict()
    compact["side_scores"][0]["location_status"] = status
    compact["side_scores"][0]["location_raw"] = raw
    with pytest.raises(ValueError):
        snapshot_envelope_from_dict(compact)

    row = scanner_row_from_composition(composition).to_dict()
    row["side_scores"][0]["location_status"] = status
    row["side_scores"][0]["location_raw"] = raw
    with pytest.raises(ValueError):
        scanner_row_from_dict(row)


def test_full_envelope_rejects_location_summary_mismatched_with_detail():
    composition = _composition_with_location_detail()
    payload = build_snapshot_envelope(composition, mode=MODE_FULL).to_dict()
    payload["side_scores"][0]["location_raw"] = 0
    payload["side_scores"][0]["location_status"] = "CONFLICT"
    payload["side_scores"][0]["location_reason_codes"] = ["LOCATION_CONFLICT"]

    with pytest.raises(ValueError, match="canonical location_detail"):
        snapshot_envelope_from_dict(payload)


def test_historical_canonical_payload_without_location_detail_still_reads():
    composition = _compose(_snapshot())
    payload = composition.canonical.to_dict()
    assert "location_detail" not in payload["side_scores"]["buy"]
    restored = CanonicalPairSnapshot.from_dict(payload)
    assert restored == composition.canonical


def test_snapshot_identity_changes_when_location_config_changes_with_same_raw():
    base = _snapshot()
    original = _location_detail("buy", base.buy.technical_raws["location"])
    changed_config = replace(
        original.config_used,
        zone_half_width_atr=original.config_used.zone_half_width_atr + 0.05,
    )
    changed_detail = replace(original, config_used=changed_config)
    base_with_detail = replace(
        base,
        buy=replace(base.buy, location_detail=original),
        sell=replace(
            base.sell,
            location_detail=_location_detail(
                "sell", base.sell.technical_raws["location"]
            ),
        ),
    )
    changed_snapshot = replace(
        base_with_detail,
        buy=replace(base_with_detail.buy, location_detail=changed_detail),
    )
    original_composition = _compose(base_with_detail)
    changed_composition = _compose(changed_snapshot)

    assert (
        original_composition.canonical.side_score("buy").technical_breakdown.location.raw
        == changed_composition.canonical.side_score("buy").technical_breakdown.location.raw
    )
    assert original_composition.snapshot_id != changed_composition.snapshot_id
    assert (
        original_composition.canonical.side_score("buy").location_detail.config_used
        != changed_composition.canonical.side_score("buy").location_detail.config_used
    )


def test_location_detail_side_and_raw_mismatches_are_rejected():
    base = _snapshot()
    wrong_side = replace(
        base.buy,
        location_detail=_location_detail(
            "sell", base.buy.technical_raws["location"]
        ),
    )
    with pytest.raises(CompositionInputError):
        replace(base, buy=wrong_side)

    composition = _composition_with_location_detail()
    payload = composition.canonical.to_dict()
    payload["side_scores"]["buy"]["location_detail"]["raw"] += 1
    with pytest.raises(ScannerContractError):
        CanonicalPairSnapshot.from_dict(payload)


def test_location_detail_does_not_change_existing_scenario_plan():
    baseline = _compose(_snapshot())
    enriched = _composition_with_location_detail()

    assert baseline.scenario.to_dict() == enriched.scenario.to_dict()
    for side in ("buy", "sell"):
        before = baseline.canonical.side_score(side).technical_breakdown
        after = enriched.canonical.side_score(side).technical_breakdown
        assert before.trend == after.trend
        assert before.momentum == after.momentum
        assert before.smc == after.smc
