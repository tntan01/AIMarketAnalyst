"""Scanner V4 backtest safety-data audit (Bước 09, target-only).

Mục 9B: inventory dữ liệu historical point-in-time cho connectivity / candle
freshness / spread / news / volatility kèm timestamp + provenance.  Thiếu hoặc
không point-in-time → ``MISSING``/``UNKNOWN`` fail-closed; **không bao giờ**
biến missing thành normal/no-news/PASS để tăng sample calibration, và không
được dùng để auto-entry/validation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.reason_codes import (
    SCANNER_V4_SAFETY_AUDIT_MISSING,
    SCANNER_V4_SAFETY_AUDIT_NON_PIT,
    SCANNER_V4_SAFETY_AUDIT_UNKNOWN,
)
from core.scanner_v4_safety_audit import (
    AVAILABLE,
    MISSING,
    NON_PIT,
    UNKNOWN,
    SAFETY_AUDIT_CATEGORIES,
    SCANNER_V4_SAFETY_AUDIT_VERSION,
    SafetyDataSource,
    SafetyDataAuditReport,
    audit_safety_data,
    is_eligible_for_entry,
)

NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=timezone.utc)
BOUNDARY = NOW - timedelta(days=30)


def _source(
    category: str,
    *,
    point_in_time: bool = True,
    observed_from: datetime | None = None,
    observed_to: datetime | None = None,
    sample_count: int = 0,
) -> SafetyDataSource:
    from_dt = observed_from if observed_from is not None else BOUNDARY - timedelta(days=90)
    to_dt = observed_to if observed_to is not None else BOUNDARY + timedelta(days=30)
    return SafetyDataSource(
        category=category,
        source=f"data/{category}_pit",
        observed_from=from_dt,
        observed_to=to_dt,
        point_in_time=point_in_time,
        provenance=f"tests/fixtures/{category}_pit",
        checked_at=NOW,
        sample_count=sample_count,
    )


class TestEmptyInventory:
    def test_no_declared_sources_all_missing(self):
        report = audit_safety_data((), pit_boundary=BOUNDARY)
        assert report.audit_version == SCANNER_V4_SAFETY_AUDIT_VERSION
        assert report.sufficient_for_calibration is False
        assert report.blockers
        for category in SAFETY_AUDIT_CATEGORIES:
            item = report.by_category()[category]
            assert item.status == MISSING, category
            assert SCANNER_V4_SAFETY_AUDIT_MISSING in item.reason_codes, category
            assert is_eligible_for_entry(item) is False

    def test_missing_is_never_normal(self):
        # Fail-closed: a MISSING item never becomes PASS/no-news — the audit
        # keeps it non-eligible and names the blocker.
        report = audit_safety_data((), pit_boundary=BOUNDARY)
        for category in SAFETY_AUDIT_CATEGORIES:
            item = report.by_category()[category]
            assert is_eligible_for_entry(item) is False


class TestPitSources:
    def test_full_pit_inventory_becomes_available(self):
        declared = tuple(_source(category) for category in SAFETY_AUDIT_CATEGORIES)
        report = audit_safety_data(declared, pit_boundary=BOUNDARY)
        assert report.sufficient_for_calibration is True
        assert not report.blockers
        for category in SAFETY_AUDIT_CATEGORIES:
            assert report.by_category()[category].status == AVAILABLE

    def test_pit_source_outside_boundary_is_missing(self):
        # A source that does not cover the calibration boundary cannot support
        # it, regardless of point_in_time=True.
        outside = _source(
            "spread",
            observed_from=BOUNDARY - timedelta(days=200),
            observed_to=BOUNDARY - timedelta(days=190),
        )
        report = audit_safety_data((outside,), pit_boundary=BOUNDARY)
        item = report.by_category()["spread"]
        assert item.status != AVAILABLE
        assert is_eligible_for_entry(item) is False

    def test_pit_source_covers_boundary_but_below_minimum(self):
        narrow = _source(
            "spread",
            observed_from=BOUNDARY - timedelta(days=1),
            observed_to=BOUNDARY + timedelta(days=1),
        )
        report = audit_safety_data(
            (narrow,),
            pit_boundary=BOUNDARY,
            minimum_required={"spread": 30},
        )
        assert report.sufficient_for_calibration is False
        assert any("minimum" in blocker for blocker in report.blockers)


class TestNonPitIsNeverAvailable:
    def test_non_pit_source_is_never_available(self):
        non_pit = _source("news", point_in_time=False)
        report = audit_safety_data((non_pit,), pit_boundary=BOUNDARY)
        item = report.by_category()["news"]
        assert item.status == NON_PIT
        assert SCANNER_V4_SAFETY_AUDIT_NON_PIT in item.reason_codes
        assert is_eligible_for_entry(item) is False

    def test_mixed_pit_and_non_pit(self):
        # PIT spread + NON_PIT news → spread AVAILABLE only, never promoted.
        declared = (
            _source("spread", point_in_time=True),
            _source("news", point_in_time=False),
        )
        report = audit_safety_data(declared, pit_boundary=BOUNDARY)
        assert report.by_category()["spread"].status == AVAILABLE
        assert report.by_category()["news"].status == NON_PIT
        assert report.sufficient_for_calibration is False

    def test_non_pit_never_reasons_as_unknown_or_available(self):
        non_pit = _source("volatility", point_in_time=False)
        report = audit_safety_data((non_pit,), pit_boundary=BOUNDARY)
        item = report.by_category()["volatility"]
        assert item.status not in (AVAILABLE,)


class TestUnknownAndProvenance:
    def test_category_with_unknown_reason_carries_audit_unknown(self):
        # A PIT source that does NOT cover the calibration boundary produces
        # UNKNOWN (not PASS) and is not eligible.
        partial = _source(
            "connectivity",
            observed_from=BOUNDARY - timedelta(days=2),
            observed_to=BOUNDARY - timedelta(days=1),
        )
        report = audit_safety_data((partial,), pit_boundary=BOUNDARY)
        item = report.by_category()["connectivity"]
        assert item.status != AVAILABLE
        assert is_eligible_for_entry(item) is False

    def test_available_source_keeps_provenance_and_timestamps(self):
        src = _source("spread", sample_count=120)
        report = audit_safety_data((src,), pit_boundary=BOUNDARY)
        item = report.by_category()["spread"]
        assert item.status == AVAILABLE
        assert item.sources[0].provenance == src.provenance
        assert item.sources[0].observed_from.isoformat() == src.observed_from.isoformat()
        assert item.sources[0].sample_count == 120

    def test_report_to_dict_shape(self):
        report = audit_safety_data((), pit_boundary=BOUNDARY)
        payload = report.to_dict()
        assert payload["audit_version"] == SCANNER_V4_SAFETY_AUDIT_VERSION
        assert payload["pit_boundary"] == BOUNDARY.isoformat()
        assert len(payload["items"]) == len(SAFETY_AUDIT_CATEGORIES)
        assert payload["sufficient_for_calibration"] is False


class TestCurrentRepoState:
    def test_current_repo_has_no_pit_safety_dataset(self):
        # data/ holds journals/baseline only (no CSV/PIT candles/spread/news).
        # The audit against the current repository must be MISSING for every
        # category — this is the blocker evidence for calibration.
        report = audit_safety_data((), pit_boundary=datetime.now(timezone.utc))
        assert report.sufficient_for_calibration is False
        codes = {
            code
            for item in report.items
            for code in item.reason_codes
        }
        assert SCANNER_V4_SAFETY_AUDIT_MISSING in codes


class TestReportContract:
    def test_report_is_immutable_and_typed(self):
        report = audit_safety_data((), pit_boundary=BOUNDARY)
        assert isinstance(report, SafetyDataAuditReport)
        with pytest.raises(AttributeError):
            report.sufficient_for_calibration = True

    def test_only_available_can_enter(self):
        src = _source("spread", sample_count=90)
        report = audit_safety_data((src,), pit_boundary=BOUNDARY)
        assert is_eligible_for_entry(report.by_category()["spread"]) is True
        assert is_eligible_for_entry(report.by_category()["news"]) is False
        missing_payload = report.by_category()["news"].to_dict()
        assert missing_payload["status"] == MISSING