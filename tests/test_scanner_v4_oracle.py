"""Scanner V4 — oracle fixture + static V3-isolation checks (Bước 11).

Two complementary guarantees:

A. **Oracle**: a frozen, independent reference for the locked Mục 4.3 technical
   formula and the Bước 06 final-score blend, plus the Bước 07 canonical
   composition geometry (buy 76 / sell 32 / gap 44).  The reference is a
   hand-written ``Fraction``/ROUND_HALF_UP model — never a copy of the module —
   so any drift in the scorer or the final blend is caught.  A versioned V4
   fixture must carry the locked version identities.

B. **Static V3 isolation**: the target-only V4 modules must not reference the
   V3 six-component scored fields (``risk_condition`` / ``macro_alignment`` /
   ``opportunity_score`` / ``scanner_action`` / ``scanner_group`` /
   ``expected_effective_rr`` / ``best_score``), must not run the V3 runtime
   scorer, and the MarketSafety gate must only ever treat ``AVAILABILITY_VALID``
   as usable — a missing/error source can never auto-default to PASS.

No production threshold is set here; the oracle is the fixed Bước 04-07 model.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from core.final_score_v4 import score_final_score
from core.scanner_v4_models import SCANNER_V4_SCORING_VERSION
from core.technical_signal_scorer import (
    TECHNICAL_COMPONENT_RAW_MAX,
    score_technical_signal,
)

from tests.scanner_v4_testkit import (
    BUY,
    SELL,
    DEFAULT_THRESHOLD_POLICY,
    build_snapshot,
    canonical_smc,
    compose,
    safety_policy,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

# V4 target-only source files scanned by the static isolation checks.
V4_SOURCE_FILES = (
    "core/technical_signal_scorer.py",
    "core/final_score_v4.py",
    "core/market_safety_gate.py",
    "core/macro_gate.py",
    "core/scanner_v4_composition.py",
    "core/scanner_v4_candidate.py",
    "core/scanner_v4_threshold_policy.py",
    "core/scanner_v4_execution_readiness.py",
    "core/scanner_v4_ranking.py",
    "core/scanner_v4_strategy_router.py",
    "core/scanner_v4_row.py",
    "core/scanner_v4_snapshot.py",
    "core/scanner_v4_replay.py",
    "core/scanner_v4_observability.py",
    "core/scanner_v4_session_review.py",
    "core/scanner_v4_backtest_contract.py",
    "core/scanner_v4_candidate_ledger.py",
    "core/scanner_v4_calibration.py",
    "core/scanner_v4_safety_audit.py",
    "core/scanner_v4_config_invalidation.py",
    "services/scanner_v4_journal_models.py",
    "services/scanner_v4_journal_converters.py",
    "ui/scanner_v4_presentation.py",
)

# V3 six-component scored fields V4 must never read as scored evidence.
V3_FORBIDDEN_SCORED_TOKENS = (
    "risk_condition",
    "macro_alignment",
    "opportunity_score",
    "scanner_action",
    "scanner_group",
    "expected_effective_rr",
    "best_score",
)


def _collect_keys(value, out: set[str]) -> None:
    """Recursively collect every mapping key from a serialized V4 payload."""
    if isinstance(value, dict):
        out.update(value)
        for item in value.values():
            _collect_keys(item, out)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _collect_keys(item, out)


# ---------------------------------------------------------------------------
# A. Oracle: independent Fraction reference for the locked formulas
# ---------------------------------------------------------------------------


def _round_half_up(value: Fraction) -> int:
    quotient, remainder = divmod(value.numerator, value.denominator)
    return quotient + int(remainder * 2 >= value.denominator)


def _ref_technical(side: str, raws: dict[str, int], *, smc_raw: int, regime: str) -> int:
    """Independent Mục 4.3 technical reference (weights lock, ROUND_HALF_UP once)."""
    weights = {
        ("trending_up"): {"trend": 40, "momentum": 20, "location": 20, "smc": 20},
        ("trending_down"): {"trend": 40, "momentum": 20, "location": 20, "smc": 20},
        ("ranging"): {"trend": 10, "momentum": 10, "location": 40, "smc": 40},
        ("volatile"): {"trend": 20, "momentum": 10, "location": 40, "smc": 30},
        ("unknown"): {"trend": 25, "momentum": 25, "location": 25, "smc": 25},
    }[regime]
    total = Fraction(0, 1)
    for component, raw in [("trend", raws["trend"]), ("momentum", raws["momentum"]), ("location", raws["location"])]:
        total += Fraction(raw * weights[component], TECHNICAL_COMPONENT_RAW_MAX[component])
    total += Fraction(smc_raw * weights["smc"], TECHNICAL_COMPONENT_RAW_MAX["smc"])
    return _round_half_up(min(Fraction(100, 1), max(Fraction(0, 1), total)))


def _ref_final(technical: int, evidence: int, execution: int) -> int:
    """Independent Bước 06 blend: 0.65 tech + 0.20 evidence + 0.15 execution."""
    total = Fraction(65 * technical + 20 * evidence + 15 * execution, 100)
    return _round_half_up(min(Fraction(100, 1), max(Fraction(0, 1), total)))


class TestTechnicalOracle:
    def test_default_buy_and_sell_match_reference(self) -> None:
        smc = canonical_smc(buy_subtotal=12, sell_subtotal=7)

        buy = score_technical_signal(
            BUY, trend_raw=20, momentum_raw=14, location_raw=18,
            canonical_smc=smc, regime="trending_up",
        )
        assert buy.technical_signal_score == _ref_technical(
            BUY, {"trend": 20, "momentum": 14, "location": 18}, smc_raw=12, regime="trending_up"
        ) == 76  # Bước 07 canonical strong-buy geometry

        sell = score_technical_signal(
            SELL, trend_raw=8, momentum_raw=5, location_raw=6,
            canonical_smc=smc, regime="trending_up",
        )
        assert sell.technical_signal_score == _ref_technical(
            SELL, {"trend": 8, "momentum": 5, "location": 6}, smc_raw=7, regime="trending_up"
        ) == 32  # Bước 07 canonical weak-sell geometry

    def test_fixed_vector_matches_reference(self) -> None:
        smc = canonical_smc(buy_subtotal=12, sell_subtotal=7)
        # A far-from-default vector across all components.
        result = score_technical_signal(
            BUY, trend_raw=25, momentum_raw=20, location_raw=25,
            canonical_smc=smc, regime="ranging",
        )
        expected = _ref_technical(BUY, {"trend": 25, "momentum": 20, "location": 25}, smc_raw=12, regime="ranging")
        assert result.technical_signal_score == expected


class TestFinalOracle:
    def test_final_blend_matches_independent_reference(self) -> None:
        result = score_final_score(76, 60, 70, side=BUY, evidence_source="e", execution_quality_source="x")
        assert result.setup_score == _ref_final(76, 60, 70) == 72
        sell = score_final_score(32, 60, 70, side=SELL, evidence_source="e", execution_quality_source="x")
        assert sell.setup_score == _ref_final(32, 60, 70) == 43

    def test_neutral_fallback_not_part_of_technical(self) -> None:
        result = score_final_score(76, None, None, side=BUY, evidence_source="", execution_quality_source="")
        # 0.65*76 + 0.20*50 + 0.15*50 = 49.4 + 10 + 7.5 = 66.9 -> 67
        assert result.setup_score == _ref_final(76, 50, 50) == 67


class TestCompositionOracle:
    def test_frozen_composition_carries_locked_versions_and_scores(self) -> None:
        result = compose(build_snapshot())
        buy = result.canonical.side_scores[0]
        sell = result.canonical.side_scores[1]
        assert buy.side == BUY and sell.side == SELL
        assert buy.technical_signal_score == 76
        assert sell.technical_signal_score == 32
        assert buy.setup_score == _ref_final(76, 60, 70) == 72
        assert sell.setup_score == _ref_final(32, 60, 70) == 43
        assert result.decision.score_gap == 44
        assert buy.final_score == buy.setup_score  # V4 alias, never a separate number
        assert result.canonical.scoring_version == SCANNER_V4_SCORING_VERSION
        assert result.decision.candidate_status == "WAITING_CONFIRMATION"


class TestVersionedFixture:
    def test_versions_are_stamped(self) -> None:
        from core.scanner_v4_composition import COMPOSITION_POLICY_VERSION
        from core.scanner_v4_snapshot import SCANNER_V4_SNAPSHOT_ENVELOPE_VERSION
        from core.scanner_v4_row import SCANNER_V4_ROW_VERSION
        from core.scanner_v4_threshold_policy import SCANNER_V4_THRESHOLD_POLICY_VERSION

        for value in (
            SCANNER_V4_SCORING_VERSION,
            COMPOSITION_POLICY_VERSION,
            SCANNER_V4_SNAPSHOT_ENVELOPE_VERSION,
            SCANNER_V4_ROW_VERSION,
            SCANNER_V4_THRESHOLD_POLICY_VERSION,
        ):
            assert isinstance(value, str) and value.startswith("scanner")
        assert "v4" in SCANNER_V4_SNAPSHOT_ENVELOPE_VERSION


# ---------------------------------------------------------------------------
# B. Static V3-isolation checks
# ---------------------------------------------------------------------------


class TestStaticV3Isolation:
    def test_v4_serialized_outputs_never_emit_v3_scored_keys(self) -> None:
        # The V3 six-component scored fields must never appear as an output
        # key anywhere in a serialized V4 artifact (row / envelope / candidate /
        # presentation).  Guard constants and docstrings may name them; the
        # emitted schema may not.
        from core.scanner_v4_candidate import build_candidate
        from core.scanner_v4_execution_readiness import evaluate_execution_readiness
        from core.scanner_v4_row import scanner_v4_row_from_composition
        from core.scanner_v4_snapshot import MODE_FULL, build_v4_snapshot_envelope
        from ui.scanner_v4_presentation import build_scanner_v4_presentation

        composition = compose(build_snapshot())
        artifacts = [
            scanner_v4_row_from_composition(composition).to_dict(),
            build_v4_snapshot_envelope(composition, mode=MODE_FULL).to_dict(),
            build_candidate(
                composition=composition,
                thresholds=DEFAULT_THRESHOLD_POLICY,
                entry_confirmation="confirmed",
                execution=evaluate_execution_readiness(composition),
            ).to_dict(),
            build_scanner_v4_presentation(composition).to_dict(),
            build_scanner_v4_presentation(composition).to_dict()["side_scores"][0],
        ]

        forbidden = set()
        for payload in artifacts:
            _collect_keys(payload, forbidden)
        leaking = sorted(set(V3_FORBIDDEN_SCORED_TOKENS) & forbidden)
        assert not leaking, f"V4 outputs emit V3 scored keys: {leaking}"

    def test_v4_sources_never_import_v3_runtime_scorer(self) -> None:
        # V4 is pure and target-only: it never runs the V3 service / controller /
        # detail screen scorer.  ``core.scanner`` (V3) must not be imported; the
        # ``core.scanner_v4_*`` modules must not be caught by the boundary.
        # ``from core.scanner import`` matches "core.scanner\\n... import"; the
        # regex below excludes the ``_v4`` suffix so V4 self-imports are allowed.
        import re

        boundary = re.compile(r"\bcore\.scanner\b(?!_v)")
        offender: list[tuple[str, str]] = []
        for rel in V4_SOURCE_FILES:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            if boundary.search(text):
                offender.append((rel, "core.scanner (V3)"))
        assert not offender, f"V4 sources import the V3 runtime: {offender}"

    def test_router_forbids_the_full_legacy_guard_set(self) -> None:
        from core.scanner_v4_strategy_router import FORBIDDEN_LEGACY_KEYS

        expected = {
            "total", "best_score", "final_score", "opportunity_score",
            "scanner_action", "scanner_group", "expected_effective_rr",
            "risk_condition", "macro_alignment",
        }
        assert FORBIDDEN_LEGACY_KEYS == expected
        assert set(V3_FORBIDDEN_SCORED_TOKENS) <= set(FORBIDDEN_LEGACY_KEYS)

    def test_safety_gate_only_usable_on_valid_availability(self) -> None:
        # Fail-closed rule: a sub-source is usable for a PASS only when its
        # availability is exactly AVAILABILITY_VALID; anything else is UNKNOWN.
        from dataclasses import replace

        from core.market_safety_gate import AVAILABILITY_ERROR, MarketSafetyGate
        from tests.scanner_v4_testkit import CAPTURED, safety_context

        gate = MarketSafetyGate()
        ok = gate.evaluate(safety_context(), policy=safety_policy(), now=CAPTURED)
        assert ok.status == "PASS"
        bad = replace(
            safety_context().connectivity,
            availability=AVAILABILITY_ERROR,
            terminal_connected=None,
            broker_logged_in=None,
        )
        bad_ctx = replace(safety_context(), connectivity=bad)
        err = gate.evaluate(bad_ctx, policy=safety_policy(), now=CAPTURED)
        assert err.status != "PASS"
        assert err.status == "UNKNOWN"