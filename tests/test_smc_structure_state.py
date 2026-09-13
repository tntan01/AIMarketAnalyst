from core.smc_context import initialize_structure_state


def swing(swing_id, kind, level, pivot, confirmed, *, usable=True):
    return {
        "swing_id": swing_id,
        "kind": kind,
        "level": level,
        "pivot_time": f"2026-01-{pivot:02d}T00:00:00Z",
        "confirmed_at": f"2026-01-{confirmed:02d}T00:00:00Z",
        "confirmed": True,
        "usable": usable,
    }


def bullish_swings():
    return {
        "highs": [
            swing("H1", "high", 100.0, 1, 2),
            swing("H2", "high", 110.0, 5, 6),
        ],
        "lows": [
            swing("L1", "low", 90.0, 2, 3),
            swing("L2", "low", 95.0, 6, 7),
        ],
    }


def test_bullish_bootstrap_requires_two_confirmed_highs_and_lows():
    result = initialize_structure_state(bullish_swings())

    assert result["state"] == "bullish"
    assert result["structure"] == "HH/HL"
    assert result["direction"] == "bullish"
    assert result["tracked_continuation_id"] == "H2"
    assert result["tracked_continuation_level"] == 110.0
    assert result["protected_swing_id"] is None
    assert result["bootstrap_ready_at"] == "2026-01-07T00:00:00+00:00"
    assert result["source_history_anchor_at"] == "2026-01-01T00:00:00+00:00"
    assert result["anchor_start_at"] == result["source_history_anchor_at"]


def test_bearish_bootstrap_tracks_latest_low_without_defaulting_up():
    result = initialize_structure_state(
        {
            "highs": [
                swing("H1", "high", 110.0, 1, 2),
                swing("H2", "high", 100.0, 5, 6),
            ],
            "lows": [
                swing("L1", "low", 90.0, 2, 3),
                swing("L2", "low", 80.0, 6, 7),
            ],
        }
    )

    assert result["state"] == "bearish"
    assert result["structure"] == "LH/LL"
    assert result["direction"] == "bearish"
    assert result["tracked_continuation_id"] == "L2"
    assert result["tracked_continuation_level"] == 80.0


def test_insufficient_confirmed_swings_returns_unknown_without_direction():
    result = initialize_structure_state(
        {
            "highs": [swing("H1", "high", 100.0, 1, 2)],
            "lows": [swing("L1", "low", 90.0, 2, 3)],
        }
    )

    assert result["state"] == "unknown"
    assert result["structure"] == "unknown"
    assert result["direction"] is None
    assert result["tracked_continuation_id"] is None
    assert "SMC_INSUFFICIENT_CONFIRMED_SWINGS" in result["reason_codes"]


def test_unconfirmed_or_provisional_swings_are_not_used_for_bootstrap():
    swings = bullish_swings()
    swings["highs"][1]["confirmed"] = False
    swings["lows"][1]["usable"] = False

    result = initialize_structure_state(swings)

    assert result["state"] == "unknown"
    assert result["confirmed_high_count"] == 1
    assert result["confirmed_low_count"] == 1


def test_conflicting_latest_relations_return_mixed_not_a_default_trend():
    swings = bullish_swings()
    swings["lows"][1]["level"] = 85.0

    result = initialize_structure_state(swings)

    assert result["state"] == "mixed"
    assert result["structure"] == "mixed"
    assert result["direction"] is None
    assert "SMC_STRUCTURE_MIXED" in result["reason_codes"]


def test_equal_latest_level_with_tolerance_is_mixed():
    swings = bullish_swings()
    swings["highs"][1]["level"] = 100.05

    result = initialize_structure_state(swings, equal_tolerance=0.1)

    assert result["state"] == "mixed"
    assert "SMC_EQUAL_SWING_LEVEL" in result["reason_codes"]


def test_as_of_excludes_future_confirmations_causally():
    result = initialize_structure_state(
        bullish_swings(),
        as_of="2026-01-06T00:00:00Z",
    )

    assert result["state"] == "unknown"
    assert result["confirmed_high_count"] == 2
    assert result["confirmed_low_count"] == 1


def test_missing_stable_reference_is_data_quality_not_a_default_swing():
    swings = bullish_swings()
    del swings["highs"][1]["swing_id"]

    result = initialize_structure_state(swings)

    assert result["state"] == "unknown"
    assert "SMC_SWING_REFERENCE_MISSING" in result["reason_codes"]
