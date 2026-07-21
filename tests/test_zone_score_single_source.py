"""Verify smc_quality_score uses zone_score from smc_context directly,
without re-scoring low-score zones internally.

Regression test: if someone adds back the "internal_points + max()" logic,
this test MUST fail.
"""

from core.signal_engine import smc_quality_score


def test_low_zone_score_not_boosted():
    """Zone with zone_score=30 must yield zone_points=1, NOT >=3.

    Before the fix, smc_quality_score would see zone_score < 50, compute
    an internal_zone_score from raw attributes (broken/mitigated/test_count/
    sweep/location), and take max(internal, 30).  A fresh unbroken zone
    would get internal_points=5 -> internal_zone_score=100 -> zone_points
    would be 4 (>=75 threshold), completely ignoring the actual 30 score.

    After the fix, zone_score is read directly from the enriched zone
    dict; zone_score=30 gives zone_points=1.  Additional bonuses for
    location (+3 for correct premium/discount) and liquidity sweep (+1)
    still apply, giving total score=5.

    Before the fix, the internal_points re-score would give zone_points=4,
    making total score=8.  This test verifies we get 5, not 8.
    """
    zone = {
        "zone_score": 30,
        "broken": False,
        "mitigated": False,
        "test_count": 0,
        "liquidity_sweep": True,
        "zone_location": "discount",
    }
    smc = {
        "H4": {"demand_zones": [zone]},
        "H1": {},
    }
    score, reason = smc_quality_score("buy", smc, {})
    assert "zone_score=30" in reason, (
        f"Expected zone_score=30 in reason, got: {reason}"
    )
    # zone_score=30 -> < 55 -> zone_points=1
    # +3 (correct location: discount for buy)
    # +1 (liquidity_sweep=True)
    assert score == 5, (
        f"Zone with zone_score=30 should get 1+3+1=5 (NOT boosted to 8), got {score}"
    )


def test_moderate_zone_score_not_changed():
    """Zone with zone_score=65 should get zone_points=3 (moderate tier)."""
    zone = {
        "zone_score": 65,
        "broken": False,
        "mitigated": False,
        "test_count": 1,
        "liquidity_sweep": False,
        "zone_location": "equilibrium",
    }
    smc = {
        "H4": {"demand_zones": [zone]},
        "H1": {},
    }
    score, reason = smc_quality_score("buy", smc, {})
    assert "zone_score=65" in reason
    # zone_points=3 + equilibrium location +1 = 4
    assert score == 4, (
        f"Zone with zone_score=65 should get 3+1=4, got {score}"
    )


def test_high_zone_score_unchanged():
    """Zone with zone_score=80 should get zone_points=4 (strong tier)."""
    zone = {
        "zone_score": 80,
        "broken": False,
        "mitigated": False,
        "test_count": 0,
        "liquidity_sweep": False,
        "zone_location": "discount",
    }
    smc = {
        "H4": {"demand_zones": [zone]},
        "H1": {},
    }
    score, reason = smc_quality_score("buy", smc, {})
    assert "zone_score=80" in reason
    # zone_points=4 + correct location +3 = 7
    assert score == 7, (
        f"Zone with zone_score=80 should get 4+3=7, got {score}"
    )
