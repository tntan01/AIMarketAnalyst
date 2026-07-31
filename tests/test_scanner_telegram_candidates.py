"""Phase 1 Telegram candidate correctness and request telemetry."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from controllers.scanner_controller import ScannerController
from core.scanner_performance import ScanPerformanceTracker
from services.telegram_alert_service import TelegramAlertService


def _canonical_payload(
    symbol: str = "EUR/USD",
    **overrides: object,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "symbol": symbol,
        "broker_symbol": symbol.replace("/", ""),
        "side": "buy",
        "entry_zone": [1.1000, 1.1010],
        "stop_loss": 1.0950,
        "take_profit": 1.1100,
        "best_score": 80,
        "candidate_status": "READY_NOW",
        "scan_id": "scan-telegram",
        "row_id": f"scan-telegram:{symbol.replace('/', '')}",
        "settings_hash": "settings-hash",
        "scorer_version": "scanner-scorer-v1",
        "ranking_version": "phase6-ranking-v1",
    }
    payload.update(overrides)
    return payload


def _legacy_row(symbol: str = "EUR/USD") -> dict[str, object]:
    return {
        "symbol": symbol,
        "broker_symbol": symbol.replace("/", ""),
        "scanner_group": "ready_now",
        "scanner_action": "ready",
        "analysis_result": {
            "scenarios": [{
                "type": "buy",
                "entry_zone": [1.1000, 1.1010],
                "entry_price": 1.1010,
                "stop_loss": 1.0950,
                "take_profit": [1.1100],
                "position_sizing": {"suggested_lot": 0.1},
            }],
        },
    }


def _rejected_row(
    status: str,
    index: int,
) -> dict[str, object]:
    row = _legacy_row(f"R{index:02d}/USD")
    row.update({
        "candidate_status": status,
        "candidate_order_payload": None,
    })
    return row


def test_present_valid_canonical_payload_is_the_only_source() -> None:
    controller = ScannerController.__new__(ScannerController)
    tracker = ScanPerformanceTracker()
    row = {
        "symbol": "ROW/SYMBOL",
        "candidate_status": "READY_NOW",
        "candidate_order_payload": _canonical_payload(),
    }

    candidates = controller._get_alert_order_candidates(
        [row],
        performance_tracker=tracker,
    )
    counters = tracker.finalize()["counters"]

    assert len(candidates) == 1
    assert candidates[0]["symbol"] == "EUR/USD"
    assert counters["telegram_canonical_candidates"] == 1
    assert counters["telegram_legacy_fallback_candidates"] == 0
    assert counters["telegram_skipped_non_candidates"] == 0


def test_canonical_payload_does_not_inherit_legacy_rejection() -> None:
    controller = ScannerController.__new__(ScannerController)
    row = {
        "candidate_status": "READY_NOW",
        "legacy_candidate_status": "OUT_OF_STRATEGY",
        "scanner_group": "out_of_strategy",
        "scanner_action": "stand_aside",
        "candidate_order_payload": _canonical_payload(),
    }

    candidates = controller._get_alert_order_candidates([row])

    assert len(candidates) == 1
    assert candidates[0]["candidate_status"] == "READY_NOW"


@pytest.mark.parametrize("stored", [None, "legacy", [], 7])
def test_present_non_dict_payload_never_falls_back(stored: object) -> None:
    controller = ScannerController.__new__(ScannerController)
    tracker = ScanPerformanceTracker()
    row = _legacy_row()
    row["candidate_order_payload"] = stored

    candidates = controller._get_alert_order_candidates(
        [row],
        performance_tracker=tracker,
    )
    counters = tracker.finalize()["counters"]

    assert candidates == []
    assert counters["telegram_legacy_fallback_candidates"] == 0
    assert counters["telegram_skipped_non_candidates"] == 1


def test_absent_payload_key_uses_valid_legacy_compatibility() -> None:
    controller = ScannerController.__new__(ScannerController)
    tracker = ScanPerformanceTracker()

    candidates = controller._get_alert_order_candidates(
        [_legacy_row()],
        performance_tracker=tracker,
    )
    counters = tracker.finalize()["counters"]

    assert len(candidates) == 1
    assert candidates[0]["symbol"] == "EUR/USD"
    assert candidates[0]["side"] == "buy"
    assert counters["telegram_canonical_candidates"] == 0
    assert counters["telegram_legacy_fallback_candidates"] == 1
    assert counters["telegram_skipped_non_candidates"] == 0


def test_structural_reject_skips_even_valid_canonical_payload() -> None:
    controller = ScannerController.__new__(ScannerController)
    row = {
        "analysis_status": "structural_reject",
        "candidate_status": "READY_NOW",
        "candidate_order_payload": _canonical_payload(),
    }

    assert controller._get_alert_order_candidates([row]) == []


@pytest.mark.parametrize(
    "status",
    ["OUT_OF_STRATEGY", "DATA_UNAVAILABLE"],
)
def test_explicit_rejected_status_skips_without_fallback(
    status: str,
) -> None:
    controller = ScannerController.__new__(ScannerController)
    row = _legacy_row()
    row.update({
        "candidate_status": status,
        "candidate_order_payload": _canonical_payload(
            candidate_status=status,
        ),
    })

    assert controller._get_alert_order_candidates([row]) == []


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("broker_symbol", ""),
        ("side", "stand_aside"),
        ("entry_zone", [1.1000]),
        ("stop_loss", None),
        ("take_profit", None),
        ("candidate_status", "OUT_OF_STRATEGY"),
        ("scan_id", ""),
        ("row_id", ""),
        ("settings_hash", ""),
        ("scorer_version", ""),
        ("ranking_version", ""),
    ],
)
def test_malformed_canonical_payload_fails_closed(
    field: str,
    invalid: object,
) -> None:
    controller = ScannerController.__new__(ScannerController)
    row = {
        "candidate_status": "READY_NOW",
        "candidate_order_payload": _canonical_payload(
            **{field: invalid},
        ),
    }

    assert controller._get_alert_order_candidates([row]) == []


def test_27_rejected_rows_produce_zero_detail_candidates() -> None:
    controller = ScannerController.__new__(ScannerController)
    rejected_rows = [
        _rejected_row("OUT_OF_STRATEGY", index)
        for index in range(27)
    ]

    assert controller._get_alert_order_candidates(rejected_rows) == []


def test_27_out_of_strategy_plus_data_unavailable_send_no_detail_alert(
    monkeypatch,
) -> None:
    controller = ScannerController.__new__(ScannerController)
    controller.settings_service = SimpleNamespace(
        load=lambda: SimpleNamespace(
            notifications=SimpleNamespace(
                telegram_bot_token="test-token",
                telegram_chat_ids=["test-chat"],
            ),
        ),
    )
    service = TelegramAlertService()
    controller.telegram_service = service
    requests: list[tuple[str, str, str]] = []
    summary_candidate_counts: list[int] = []
    original_summary_formatter = service.format_summary_alert

    def capture_request(
        token: str,
        chat_id: str,
        message: str,
    ) -> None:
        requests.append((token, chat_id, message))

    def capture_summary_candidates(
        rows: list[dict[str, object]],
        candidates: list[dict[str, object]],
        timestamp: str,
    ) -> str:
        summary_candidate_counts.append(len(candidates))
        return original_summary_formatter(rows, candidates, timestamp)

    monkeypatch.setattr(service, "_send_message", capture_request)
    monkeypatch.setattr(
        service,
        "format_summary_alert",
        capture_summary_candidates,
    )
    rejected_rows = [
        _rejected_row("OUT_OF_STRATEGY", index)
        for index in range(27)
    ]
    rejected_rows.append(_rejected_row("DATA_UNAVAILABLE", 27))
    clock_values = iter((0.0, 1.0, 2.0, 3.0))
    tracker = ScanPerformanceTracker(
        clock=lambda: next(clock_values),
    )

    result = controller._send_telegram_alerts(
        rejected_rows,
        performance_tracker=tracker,
    )
    performance = tracker.finalize()
    counters = performance["counters"]

    assert result == {
        "attempted": 0,
        "sent": 0,
        "errors": [],
        "summary_sent": 1,
    }
    assert summary_candidate_counts == [0]
    assert len(requests) == 1
    assert counters["telegram_candidates"] == 0
    assert counters["telegram_canonical_candidates"] == 0
    assert counters["telegram_legacy_fallback_candidates"] == 0
    assert counters["telegram_skipped_non_candidates"] == 28
    assert counters["telegram_requests"] == 1
    assert counters["telegram_errors"] == 0
    assert performance["phases"]["telegram_ms"] == 1_000.0
