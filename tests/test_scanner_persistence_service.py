from datetime import datetime, timedelta, timezone

from services.scanner_persistence_service import ScannerPersistenceService, summary_row


def test_summary_mode_becomes_full_for_first_periodic_sample(tmp_path):
    service = ScannerPersistenceService(tmp_path)
    assert service.select_mode({"persistence_mode": "summary", "rows": []}) == "full"

    service.record("full", now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert service._sample_due(now=datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc)) is False
    assert service._sample_due(now=datetime(2026, 1, 1, 1, 1, tzinfo=timezone.utc)) is True


def test_summary_mode_becomes_full_for_ready_or_error_event(tmp_path):
    service = ScannerPersistenceService(tmp_path)
    service.record("full")
    assert service.select_mode({"persistence_mode": "summary", "rows": [{"scanner_action": "ready"}]}) == "full"
    assert service.select_mode({"persistence_mode": "summary", "rows": [], "auto_trade_results": {"errors": ["x"]}}) == "full"


def test_summary_row_is_explicitly_bounded_to_allowed_fields():
    compact = summary_row({"symbol": "EURUSD", "best_score": 80, "analysis_result": {"candles": [1]}, "observability": {"raw": 1}})
    assert compact == {"symbol": "EURUSD", "best_score": 80}


def test_summary_row_preserves_structural_reject_route_and_reason():
    compact = summary_row({
        "symbol": "EURUSD",
        "analysis_status": "structural_reject",
        "pipeline_route": "post_context_reject",
        "fast_path_version": "scanner-fast-path-v1",
        "fast_reject_reason": "NO_ACTIONABLE_SMC_ZONE",
        "analysis_result": {"candles": [1]},
    })

    assert compact == {
        "symbol": "EURUSD",
        "analysis_status": "structural_reject",
        "pipeline_route": "post_context_reject",
        "fast_path_version": "scanner-fast-path-v1",
        "fast_reject_reason": "NO_ACTIONABLE_SMC_ZONE",
    }


def test_summary_row_keeps_entry_zone_source_and_zone_origin_class():
    compact = summary_row({
        "symbol": "EURUSD",
        "best_score": 80,
        "entry_zone_source": "smc_v2_selected",
        "zone_origin_class": "smc",
    })
    assert compact["entry_zone_source"] == "smc_v2_selected"
    assert compact["zone_origin_class"] == "smc"


def test_summary_row_still_excludes_analysis_result_and_observability():
    compact = summary_row({
        "symbol": "GBPUSD",
        "entry_zone_source": "fallback",
        "zone_origin_class": "fallback",
        "analysis_result": {"scenarios": [{"type": "buy"}]},
        "observability": {"trace": "data"},
    })
    assert "analysis_result" not in compact
    assert "observability" not in compact
    assert compact["entry_zone_source"] == "fallback"
    assert compact["zone_origin_class"] == "fallback"


def test_summary_row_old_snapshot_missing_new_fields_does_not_crash():
    """Backward compat: row without entry_zone_source/zone_origin_class is fine."""
    compact = summary_row({
        "symbol": "AUDUSD",
        "best_score": 70,
    })
    assert "entry_zone_source" not in compact
    assert "zone_origin_class" not in compact
    assert compact == {"symbol": "AUDUSD", "best_score": 70}


def test_summary_row_preserves_price_vs_zone_all_values():
    """summary must keep the internal enum, not the Vietnamese display text."""
    for zone_value in ("in_zone", "near_zone", "far", "unknown"):
        compact = summary_row({
            "symbol": "EURUSD",
            "price_vs_zone": zone_value,
        })
        assert compact["price_vs_zone"] == zone_value


def test_summary_row_still_excludes_entry_zone_and_analysis_result():
    compact = summary_row({
        "symbol": "EURUSD",
        "price_vs_zone": "in_zone",
        "entry_zone": [1.09500, 1.09900],
        "analysis_result": {"candles": [1]},
    })
    assert "price_vs_zone" in compact
    assert "entry_zone" not in compact
    assert "analysis_result" not in compact


def test_summary_row_old_snapshot_without_price_vs_zone_does_not_crash():
    """Backward compat: row without price_vs_zone is fine."""
    compact = summary_row({
        "symbol": "GBPUSD",
        "best_score": 60,
    })
    assert "price_vs_zone" not in compact
    assert compact == {"symbol": "GBPUSD", "best_score": 60}
