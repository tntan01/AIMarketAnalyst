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
