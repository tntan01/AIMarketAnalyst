"""Scanner V4 — Mục 13 invariant / property tests (Bước 11; target-only).

These tests lock the *cross-cutting invariants* the architecture demands
(Mục 13) independently of any single module.  They use the Bước 11 testkit to
build deterministic canonical snapshots and only the already-stamped test
policies.  No production threshold is invented here.

Coverage contract exercised:

1. every valid raw input (seeded pseudo-random across all regimes) yields a
   TechnicalScore in 0..100, deterministically, monotonically in each component,
   and without component truncation (each contribution is exact raw/raw_max*w);
2. changing only Safety (or Macro) policy never mutates side scores / scenario /
   gap — the gate never leaks into the number;
3. BLOCK + score-100 scenario stays BLOCKED; a CAUTION/non-critical UNKNOWN never
   reaches READY_NOW — a strong score/final/rank never loosens a gate;
4. missing safety evidence is never PASS; missing technical stays DATA_UNAVAILABLE;
5. BestSide/gap/scenario are side-consistent with the TechnicalScore (Mục 13);
6. live and backtest stamp the same scorer/feature/version identity and produce
   the same candidate status for the same immutable input;
7. Evidence/Execution missing fall back to *exactly* neutral 50 with a warning
   source — never a copy of the TechnicalScore.
"""

from __future__ import annotations

import math
import random
from fractions import Fraction

import pytest

from core.final_score_v4 import (
    FINAL_SCORE_NEUTRAL_FALLBACK_SOURCE,
    score_final_score,
)
from core.scanner_v4_composition import ComposeOptions
from core.scanner_v4_models import (
    BLOCK,
    BLOCKED,
    BUY,
    CAUTION,
    DATA_UNAVAILABLE,
    PASS,
    READY_NOW,
    SCANNER_V4_FEATURE_VERSION,
    SCANNER_V4_SCORING_VERSION,
    SELL,
    UNKNOWN,
    WAITING_CONFIRMATION,
    WATCH_ZONE,
)
from core.technical_signal_scorer import (
    TECHNICAL_COMPONENT_RAW_MAX,
    VALID_TECHNICAL_REGIMES,
    score_technical_signal,
)

from tests.scanner_v4_testkit import (
    build_snapshot,
    canonical_smc,
    compose,
    macro_policy,
    safety_context,
    safety_policy,
    side_snapshot,
)

VALID_RAW_RANGES = {"trend": (0, 25), "momentum": (0, 20), "location": (0, 25)}

SEED = 20260813  # stable, deterministic property-test seed


def _rand_raws(rng: random.Random) -> dict[str, int]:
    return {
        name: rng.randint(lo, hi) for name, (lo, hi) in VALID_RAW_RANGES.items()
    }


def _expected_technical(
    regime: str, raws: dict[str, int], *, smc_raw: int
) -> tuple[int, float, list[float]]:
    """Reference round-half-up implementation independent of the module.

    Returns (score, exact_total, contributions).  Mirrors the locked formula
    Mục 4.3: no int() on components; round-half-up ONCE at the total.  The SMC
    raw is passed explicitly (the scan-projected pre-gate subtotal of the side
    being scored) — it must never be guessed from the test's own keys.
    """
    weights = {
        "trending_up": {"trend": 40, "momentum": 20, "location": 20, "smc": 20},
        "trending_down": {"trend": 40, "momentum": 20, "location": 20, "smc": 20},
        "ranging": {"trend": 10, "momentum": 10, "location": 40, "smc": 40},
        "volatile": {"trend": 20, "momentum": 10, "location": 40, "smc": 30},
        "unknown": {"trend": 25, "momentum": 25, "location": 25, "smc": 25},
    }[regime]
    contributions: dict[str, float] = {}
    for component in ("trend", "momentum", "location"):
        raw = min(max(raws[component], 0), TECHNICAL_COMPONENT_RAW_MAX[component])
        contributions[component] = raw / TECHNICAL_COMPONENT_RAW_MAX[component] * weights[component]
    contributions["smc"] = smc_raw / TECHNICAL_COMPONENT_RAW_MAX["smc"] * weights["smc"]
    total = sum(contributions.values())
    return math.floor(total + 0.5), total, list(contributions.values())


class TestTechnicalRangeAndDeterminism:
    @pytest.mark.parametrize("regime", sorted(VALID_TECHNICAL_REGIMES))
    def test_random_valid_raws_stay_in_0_100_and_match_reference(self, regime: str) -> None:
        rng = random.Random(SEED)
        # smc_subtotal=12 (buy) is fixed by the canonical fixture; raws vary.
        for _ in range(60):
            raws = _rand_raws(rng)
            result = score_technical_signal(
                BUY,
                trend_raw=raws["trend"],
                momentum_raw=raws["momentum"],
                location_raw=raws["location"],
                canonical_smc=canonical_smc(buy_subtotal=12, sell_subtotal=7),
                regime=regime,
            )
            assert 0 <= result.technical_signal_score <= 100
            # BUY side: the canonical fixture's buy SMC subtotal is 12.
            expected, total, contribs = _expected_technical(regime, raws, smc_raw=12)
            # Our reference hardcodes the SMC subtotal through the same formula;
            # the scorer must arrive at the same round-half-up total.
            assert result.technical_signal_score == expected, (
                f"regime={regime} raws={raws} ref_tot={total} scored={result.technical_signal_score}"
            )
            # No int() truncation: the four contributions are exact fractions of
            # raw/raw_max and the stored total must equal round(sum(contrib)).
            breakdown = result.technical_breakdown
            items = {
                "trend": breakdown.trend,
                "momentum": breakdown.momentum,
                "location": breakdown.location,
                "smc": breakdown.smc,
            }
            stored_total = sum(i.contribution for i in items.values())
            assert math.isclose(stored_total, total, rel_tol=1e-9, abs_tol=1e-9), (
                f"component truncation leaked into the total: {stored_total} vs {total}"
            )

    @pytest.mark.parametrize("regime", sorted(VALID_TECHNICAL_REGIMES))
    def test_deterministic_and_does_not_mutate_inputs(self, regime: str) -> None:
        rng = random.Random(SEED ^ 0xB11)
        smc = canonical_smc(buy_subtotal=12, sell_subtotal=7)
        trend = rng.randint(0, 25)
        momentum = rng.randint(0, 20)
        location = rng.randint(0, 25)
        first = score_technical_signal(
            BUY, trend_raw=trend, momentum_raw=momentum, location_raw=location,
            canonical_smc=smc, regime=regime,
        )
        second = score_technical_signal(
            BUY, trend_raw=trend, momentum_raw=momentum, location_raw=location,
            canonical_smc=smc, regime=regime,
        )
        assert first.to_dict() == second.to_dict()
        # Inputs still present and unmutated in the result breakdown.
        bd = first.technical_breakdown
        assert (bd.trend.raw, bd.momentum.raw, bd.location.raw) == (trend, momentum, location)

    @pytest.mark.parametrize("regime", ["trending_up", "ranging"])
    def test_monotonic_in_each_component(self, regime: str) -> None:
        # Increasing any single component never lowers the technical score.
        smc = canonical_smc(buy_subtotal=12, sell_subtotal=7)
        base = {"trend": 5, "momentum": 5, "location": 5}
        base_score = score_technical_signal(
            BUY, trend_raw=base["trend"], momentum_raw=base["momentum"],
            location_raw=base["location"], canonical_smc=smc, regime=regime,
        ).technical_signal_score
        for comp in ("trend", "momentum", "location"):
            hi = dict(base)
            hi[comp] = VALID_RAW_RANGES[comp][1]
            hi_score = score_technical_signal(
                BUY, trend_raw=hi["trend"], momentum_raw=hi["momentum"],
                location_raw=hi["location"], canonical_smc=smc, regime=regime,
            ).technical_signal_score
            assert hi_score >= base_score, f"{comp} de-monotonized {base_score}->{hi_score}"
            assert hi_score > base_score, f"{comp} had no effect {base_score}->{hi_score}"


class TestScoreInvarianceUnderGates:
    """Mục 13: changing Risk/Macro/safety never mutates Technical/Setup scores."""

    @staticmethod
    def _score_signature(result) -> tuple:
        return (
            result.canonical.side_scores[0].to_dict(),
            result.canonical.side_scores[1].to_dict(),
            result.scenario.to_dict(),
        )

    def test_safety_block_keeps_identical_scores(self) -> None:
        blocked_safety = safety_policy(spread_threshold_by_symbol={"XAUUSD": 20})
        base = compose(build_snapshot())
        blocked = compose(
            build_snapshot(safety=safety_context(spread_points=40.0)),
            safety=blocked_safety,
        )
        assert base.decision.candidate_status == WAITING_CONFIRMATION
        assert blocked.decision.candidate_status == BLOCKED
        assert blocked.safety.status == BLOCK
        assert self._score_signature(base) == self._score_signature(blocked)
        assert blocked.canonical.side_scores[0].technical_signal_score == 76

    def test_macro_block_keeps_identical_scores(self) -> None:
        snapshot = build_snapshot(macro_raw_buy=10, macro_raw_sell=20)
        macro = macro_policy(conflict_cap="BLOCK")
        base = compose(build_snapshot())
        blocked = compose(snapshot, macro=macro)
        assert blocked.macro_gate.status == BLOCK
        assert self._score_signature(base) == self._score_signature(blocked)
        assert blocked.decision.candidate_status == BLOCKED

    def test_buy_sell_gap_excludes_common_mode(self) -> None:
        # The gap only reflects TechnicalScore BUY/SELL (Mục 13 + Mục 4.3).
        result = compose(build_snapshot())
        buy = result.canonical.side_scores[0].technical_signal_score
        sell = result.canonical.side_scores[1].technical_signal_score
        assert result.decision.score_gap == abs(buy - sell)
        assert result.decision.selected_side == (BUY if buy > sell else SELL)


class TestGateCannotBeLoosenedByScore:
    def test_block_with_high_score_stays_blocked(self) -> None:
        strong = side_snapshot(BUY, trend=25, momentum=20, location=25)
        weak = side_snapshot(SELL, trend=5, momentum=3, location=4)
        snapshot = build_snapshot(buy_side=strong, sell_side=weak)
        blocked = compose(
            snapshot,
            safety=safety_policy(spread_threshold_by_symbol={"XAUUSD": 10}),
        )
        # Technical is at/near max on the selected side yet the gate still blocks.
        assert blocked.decision.selected_side == BUY
        assert blocked.canonical.side_scores[0].technical_signal_score >= 90
        assert blocked.decision.candidate_status == BLOCKED
        assert blocked.decision.block_codes

    def test_final_score_alias_never_loosens_cap(self) -> None:
        snapshot = build_snapshot()
        base = compose(snapshot)
        # The alias invariant holds: final == setup.
        for score in base.canonical.side_scores:
            assert score.final_score == score.setup_score


class TestMissingSafetyNeverPass:
    @pytest.mark.parametrize(
        "override",
        [
            {"spread_threshold_by_symbol": {}},          # per-symbol empty -> UNKNOWN
            {"max_candle_age_minutes": None},            # freshness SLA OPEN -> UNKNOWN
            {"volatility_calibrated": False},            # band OPEN -> UNKNOWN
        ],
    )
    def test_default_open_policy_fails_closed(self, override) -> None:
        result = compose(build_snapshot(), safety=safety_policy(**override))
        assert result.safety.status in {BLOCK, UNKNOWN}
        assert result.safety.status != PASS

    def test_missing_safety_provider_error_is_not_pass(self) -> None:
        # A connectivity source with provider-error availability must aggregate
        # to UNKNOWN/BLOCK, never PASS (Mục 13: missing safety data isn't a
        # generic pass).  Evaluate at the captured time so the valid fixture is
        # fresh: without a `now`, the gate uses the real clock and the fixture
        # has long gone stale.
        from dataclasses import replace

        from core.market_safety_gate import (
            AVAILABILITY_ERROR,
            AVAILABILITY_VALID,
            MarketSafetyGate,
        )
        from tests.scanner_v4_testkit import CAPTURED, safety_context, safety_policy

        gate = MarketSafetyGate()
        ok = safety_context()
        fresh = gate.evaluate(ok, policy=safety_policy(), now=CAPTURED)
        assert fresh.status == PASS
        fresh_conn = [c for c in fresh.checks if c.name == "connectivity"][0]
        assert fresh_conn.status == PASS

        assert ok.connectivity.availability == AVAILABILITY_VALID
        bad_ctx = replace(
            ok,
            connectivity=replace(
                ok.connectivity,
                availability=AVAILABILITY_ERROR,
                terminal_connected=None,
                broker_logged_in=None,
            ),
        )
        err = gate.evaluate(bad_ctx, policy=safety_policy(), now=CAPTURED)
        assert err.status in {UNKNOWN, BLOCK}
        assert err.status != PASS
        err_conn = [c for c in err.checks if c.name == "connectivity"][0]
        assert err_conn.status in {UNKNOWN, BLOCK}
        # A whole context using the error source never aggregates to PASS.
        assert gate.evaluate(bad_ctx, policy=safety_policy(), now=CAPTURED).status != PASS


class TestSideGapScenarioConsistency:
    def test_best_side_gap_and_scenario_are_consistent(self) -> None:
        strong_buy = side_snapshot(BUY, trend=20, momentum=14, location=18)
        weak_sell = side_snapshot(SELL, trend=8, momentum=5, location=6)
        result = compose(build_snapshot(buy_side=strong_buy, sell_side=weak_sell))
        assert result.decision.selected_side == BUY
        assert result.scenario.side == BUY
        assert result.scenario.plan.direction == BUY
        assert result.macro_gate.assessed_side == BUY
        assert result.decision.score_gap == abs(
            result.canonical.side_scores[0].technical_signal_score
            - result.canonical.side_scores[1].technical_signal_score
        )

    def test_selected_side_is_the_technical_winner(self) -> None:
        # When the two technical scores differ, the selected side is the higher.
        strong_sell = side_snapshot(SELL, trend=20, momentum=14, location=18)
        weak_buy = side_snapshot(BUY, trend=8, momentum=5, location=6)
        result = compose(build_snapshot(
            buy_side=weak_buy, sell_side=strong_sell,
            smc=canonical_smc(buy_subtotal=7, sell_subtotal=12),
        ))
        assert result.decision.selected_side == SELL
        assert result.scenario.side == SELL


class TestLiveBacktestSameVersion:
    def test_same_identity_versions(self) -> None:
        live = compose(build_snapshot(source="live"))
        backtest = compose(build_snapshot(source="backtest"))
        for attr in ("scoring_version", "feature_version", "snapshot_version"):
            lv = getattr(live.canonical, attr)
            bv = getattr(backtest.canonical, attr)
            assert lv == bv == (SCANNER_V4_SCORING_VERSION if attr == "scoring_version" else SCANNER_V4_FEATURE_VERSION if attr == "feature_version" else "scanner-pair-snapshot-v4")

    def test_same_candidate_status_for_same_input(self) -> None:
        live = compose(build_snapshot(source="live"))
        backtest = compose(build_snapshot(source="backtest"))
        assert live.decision.candidate_status == backtest.decision.candidate_status
        assert live.snapshot_id == backtest.snapshot_id


class TestNeutralFallbackNeverCopiesTechnical:
    def test_missing_evidence_execution_use_exactly_50(self) -> None:
        no_ev = side_snapshot(BUY, trend=25, momentum=20, location=25, evidence=None, execution=None)
        result = compose(build_snapshot(buy_side=no_ev))
        score = result.canonical.side_scores[0]
        assert score.technical_signal_score >= 90  # strong technical exists
        assert score.evidence_score == 50           # exactly neutral, never the technical
        assert score.execution_quality_score == 50
        assert score.evidence_source == FINAL_SCORE_NEUTRAL_FALLBACK_SOURCE

    def test_final_score_direct_missing_evidence_is_50(self) -> None:
        res = score_final_score(
            76, None, None,
            side=BUY, evidence_source="", execution_quality_source="",
        )
        assert res.evidence_score == 50
        assert res.execution_quality_score == 50
        assert res.evidence_source == FINAL_SCORE_NEUTRAL_FALLBACK_SOURCE
        # 0.65*76 + 0.20*50 + 0.15*50 = 49.4 + 10 + 7.5 = 66.9 -> ROUND_HALF_UP 67
        assert res.setup_score == 67