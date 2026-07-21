"""Tests for Tier 0 zone_bucket grouping in statistical_edge_engine."""

from core.statistical_edge_engine import (
    ZONE_BUCKET_SAMPLE_SIZE,
    calculate_evidence_score,
    normalize_zone_bucket,
)


# ---------------------------------------------------------------------------
# normalize_zone_bucket
# ---------------------------------------------------------------------------


def test_normalize_zone_bucket_boundaries():
    assert normalize_zone_bucket(35) == "weak"
    assert normalize_zone_bucket(0) == "weak"
    assert normalize_zone_bucket(39) == "weak"
    assert normalize_zone_bucket(40) == "fair"
    assert normalize_zone_bucket(59) == "fair"
    assert normalize_zone_bucket(60) == "good"
    assert normalize_zone_bucket(79) == "good"
    assert normalize_zone_bucket(80) == "strong"
    assert normalize_zone_bucket(100) == "strong"


def test_normalize_zone_bucket_edge_cases():
    assert normalize_zone_bucket(None) is None
    assert normalize_zone_bucket(-10) is None
    assert normalize_zone_bucket(101) is None
    assert normalize_zone_bucket("abc") is None


# ---------------------------------------------------------------------------
# Tier 0 grouping
# ---------------------------------------------------------------------------


def _make_trade(symbol, direction, result_r, entry_zone_score=None):
    return {
        "symbol": symbol,
        "direction": direction,
        "result_r": result_r,
        "entry_zone_score": entry_zone_score,
        "closed_at": "2026-01-01T00:00:00Z",
    }


def test_tier_0_used_when_enough_zone_samples():
    """25 trades in same zone_bucket -> Tier 0 used."""
    need = ZONE_BUCKET_SAMPLE_SIZE + 5  # 25
    trades = [
        _make_trade("EURUSD", "buy", 1.0, entry_zone_score=85)
        for _ in range(need)
    ]
    result = calculate_evidence_score(trades, "EURUSD", "buy", zone_score=85)
    assert result["group_used"] == "symbol_direction_zone", (
        f"Expected Tier 0, got {result['group_used']}"
    )
    assert result["zone_bucket_used"] == "strong"
    assert result["sample_size"] == need


def test_tier_0_below_threshold_falls_back():
    """Only 5 trades in zone_bucket but 50 total -> falls back to Tier 1/2."""
    few_zone = 5
    total = 55
    trades = []
    for i in range(total):
        # First few have zone_score, rest don't
        zs = 85 if i < few_zone else None
        trades.append(_make_trade("EURUSD", "buy", 1.0, entry_zone_score=zs))

    result = calculate_evidence_score(trades, "EURUSD", "buy", zone_score=85)
    # Tier 0 should fail (< ZONE_BUCKET_SAMPLE_SIZE), fall to Tier 1
    # Tier 1: no regime provided -> None, falls to Tier 2
    # Tier 2: 55 total trades -> >= STRONG_SAMPLE_SIZE(50) -> used
    assert result["group_used"] == "symbol_direction", (
        f"Expected Tier 2 fallback, got {result['group_used']}"
    )
    assert result["zone_bucket_used"] is None


def test_no_zone_score_param_preserves_old_behavior():
    """Call without zone_score -> identical to pre-Tier-0 behavior."""
    trades = [_make_trade("EURUSD", "buy", 1.0) for _ in range(55)]
    result = calculate_evidence_score(trades, "EURUSD", "buy")
    assert result["group_used"] == "symbol_direction"
    assert result["zone_bucket_used"] is None


def test_different_zone_bucket_labels():
    """Verify all 4 bucket labels work."""
    for score, bucket in [(35, "weak"), (55, "fair"), (75, "good"), (95, "strong")]:
        need = ZONE_BUCKET_SAMPLE_SIZE + 1
        trades = [
            _make_trade("EURUSD", "buy", 1.0, entry_zone_score=score)
            for _ in range(need)
        ]
        result = calculate_evidence_score(trades, "EURUSD", "buy", zone_score=score)
        assert result["group_used"] == "symbol_direction_zone"
        assert result["zone_bucket_used"] == bucket, (
            f"score={score} -> expected bucket '{bucket}', got '{result['zone_bucket_used']}'"
        )
