from __future__ import annotations

import pytest

import core.risk_engine as risk_engine
from core.reason_codes import EXECUTION_ZONE_RR_EMPTY
from core.risk_engine import (
    _trim_execution_zone_for_effective_rr,
    calculate_expected_effective_rr,
)
from core.scanner import scanner_row_from_analysis
from tests.test_source_zone_diagnostics import _preferred_zone, _valid_plan


def _trim(
    *,
    side: str,
    zone: list[float],
    stop: float,
    target: float | None,
    spread: float = 0.0,
    digits: int = 3,
) -> dict:
    return _trim_execution_zone_for_effective_rr(
        side=side,
        structural_zone=zone,
        stop_loss=stop,
        take_profit=target,
        spread_price=spread,
        min_effective_rr=1.3,
        tolerance=0.0001,
        price_digits=digits,
    )


def test_configured_floor_is_independent_and_loaded() -> None:
    assert risk_engine._EXECUTION_ZONE_MIN_EFFECTIVE_RR == 1.3
    assert risk_engine._EXECUTION_ZONE_RR_TOLERANCE == 0.0001


def test_buy_trims_only_far_edge_and_meets_floor() -> None:
    result = _trim(side="buy", zone=[100.0, 105.0], stop=90.0, target=120.0)

    assert result["status"] == "trimmed"
    assert result["final_zone"][0] == 100.0
    assert result["final_zone"][1] < 105.0
    assert result["post_trim_effective_rr_worst"] >= 1.3


def test_sell_trims_only_far_edge_and_meets_floor() -> None:
    result = _trim(side="sell", zone=[95.0, 100.0], stop=110.0, target=80.0)

    assert result["status"] == "trimmed"
    assert result["final_zone"][0] > 95.0
    assert result["final_zone"][1] == 100.0
    assert result["post_trim_effective_rr_worst"] >= 1.3


@pytest.mark.parametrize(
    ("side", "zone", "stop", "target"),
    [
        ("buy", [100.0, 103.0], 90.0, 119.9),
        ("sell", [97.0, 100.0], 110.0, 80.1),
    ],
)
def test_exact_boundary_is_kept_with_float_tolerance(
    side: str,
    zone: list[float],
    stop: float,
    target: float,
) -> None:
    result = _trim(side=side, zone=zone, stop=stop, target=target)

    assert result["status"] == "unchanged"
    assert result["final_zone"] == zone
    assert result["post_trim_effective_rr_worst"] + 0.0001 >= 1.3


def test_no_tp1_keeps_structural_zone_without_rr_claim() -> None:
    result = _trim(
        side="buy",
        zone=[100.0, 105.0],
        stop=90.0,
        target=None,
    )

    assert result["status"] == "not_applicable_no_tp1"
    assert result["final_zone"] == [100.0, 105.0]
    assert result["post_trim_effective_rr_worst"] is None


@pytest.mark.parametrize(
    ("side", "zone", "stop", "target"),
    [
        ("buy", [104.0, 105.0], 90.0, 120.0),
        ("sell", [95.0, 96.0], 110.0, 80.0),
    ],
)
def test_empty_intersection_has_no_final_zone(
    side: str,
    zone: list[float],
    stop: float,
    target: float,
) -> None:
    result = _trim(side=side, zone=zone, stop=stop, target=target)

    assert result["status"] == "empty"
    assert result["final_zone"] is None


def test_one_tick_intersection_remains_valid() -> None:
    result = _trim(
        side="buy",
        zone=[103.042, 103.050],
        stop=90.0,
        target=120.0,
    )

    assert result["status"] == "trimmed"
    assert result["final_zone"] == [103.042, 103.043]
    assert result["post_trim_effective_rr_worst"] >= 1.3


def test_gbpjpy_fixture_uses_three_digit_conservative_boundary() -> None:
    result = _trim(
        side="buy",
        zone=[218.120, 218.215],
        stop=217.973,
        target=218.571,
        spread=0.020,
        digits=3,
    )

    assert result["status"] == "trimmed"
    assert result["final_zone"][0] == 218.120
    assert result["final_zone"][1] <= 218.215
    assert result["final_zone"][1] * 1000 == pytest.approx(
        round(result["final_zone"][1] * 1000)
    )
    assert result["post_trim_effective_rr_worst"] >= 1.3


def test_trade_plan_recomputes_rr_anchors_and_lot_on_final_zone() -> None:
    plan = _valid_plan(_preferred_zone())
    low, high = plan["execution_zone"]
    worst_entry = high
    tp1 = plan["take_profit"][0]

    assert plan["entry_zone"] == plan["execution_zone"]
    assert plan["rr_trimmed"] is True
    assert plan["rr_trim_diagnostics"]["pre_trim_effective_rr_worst"] < 1.3
    assert plan["rr_trim_diagnostics"]["post_trim_effective_rr_worst"] >= 1.3
    assert plan["structural_execution_zone"][0] <= low < high
    assert high <= plan["structural_execution_zone"][1]
    # Sizing anchors the far edge (worst fill), not the display entry.
    assert plan["position_sizing"]["entry_price"] == worst_entry
    assert plan["position_sizing"]["price_distance"] == pytest.approx(
        worst_entry - float(plan["stop_loss"]), abs=1e-5
    )
    assert plan["expected_effective_rr_worst"] == calculate_expected_effective_rr(
        direction="buy",
        entry=worst_entry,
        stop_loss=plan["stop_loss"],
        take_profit=tp1,
        spread_price=0.0,
    )
    assert plan["expected_effective_rr_worst"] + 0.0001 >= 1.3


def test_trade_plan_without_tp1_keeps_structural_execution_zone(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        risk_engine,
        "_validate_tp1_candidate",
        lambda **_kwargs: {
            "valid": False,
            "rejection_reason": "effective_rr_below_min",
        },
    )

    plan = _valid_plan(_preferred_zone())

    assert plan["take_profit"] == []
    assert plan["entry_zone"] == plan["structural_execution_zone"]
    assert plan["rr_trimmed"] is False
    assert plan["rr_trim_diagnostics"]["status"] == "not_applicable_no_tp1"
    assert plan["expected_effective_rr_worst"] is None


def test_empty_plan_becomes_watch_only_with_reason_code(monkeypatch) -> None:
    monkeypatch.setattr(risk_engine, "_EXECUTION_ZONE_MIN_EFFECTIVE_RR", 100.0)

    plan = _valid_plan(_preferred_zone())

    assert plan["entry_zone"] is None
    assert plan["execution_zone"] is None
    assert plan["entry_price"] is None
    assert plan["entry_status"] == "watch_zone"
    assert plan["ready_to_trade"] is False
    assert plan["position_sizing"]["suggested_lot"] == 0.0
    assert EXECUTION_ZONE_RR_EMPTY in plan["warning_codes"]
    assert plan["rr_trim_diagnostics"]["status"] == "empty"


def test_scanner_row_exposes_rr_trim_diagnostics() -> None:
    plan = _valid_plan(_preferred_zone())
    plan["type"] = "buy"
    result = {
        "symbol": "EUR/USD",
        "scenario_scores": {
            "buy": {"signal_score": 80},
            "sell": {"signal_score": 40},
        },
        "trade_permission": {"status": "allowed"},
        "scenarios": [plan],
        "technical": {"price": 1.1000, "atr_h4": 0.0020},
        "decision_engine": {"legacy_action": "watch", "decision": "WATCH_ONLY"},
        "direction_bias": {"best_side": "buy"},
    }

    row = scanner_row_from_analysis(result)

    assert row["structural_execution_zone"] == plan["structural_execution_zone"]
    assert row["rr_valid_zone"] == plan["rr_valid_zone"]
    assert row["rr_trimmed"] == plan["rr_trimmed"]
    assert row["rr_trim_diagnostics"] == plan["rr_trim_diagnostics"]
