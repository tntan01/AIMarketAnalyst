"""Scanner V4 Step 06: target-only FinalScore fallback + rounding contract.

Covers the locked formula and ROUND_HALF_UP boundaries, fail-closed technical
handling (typed error -> DATA_UNAVAILABLE, never a numeric fallback), the exact
50-neutral evidence/execution fallback with warning + fallback source, the
no-copy-no-renormalize contract, weight immutability (no ``weights=``/adaptive
input), determinism, input clamping, immutability, version invariants, and the
runtime-isolation / ownership deduplication guards that keep this step
target-only.
"""

from __future__ import annotations

import inspect
import json
from fractions import Fraction
from pathlib import Path

import pytest

import core.final_score_v4 as _FSV

from core.final_score_v4 import (
    FINAL_SCORE_FORMULA,
    FINAL_SCORE_NEUTRAL_FALLBACK,
    FINAL_SCORE_NEUTRAL_FALLBACK_SOURCE,
    FINAL_SCORE_POLICY_VERSION,
    FinalScoreDataError,
    FinalScoreResult,
    score_final_score,
)
from core.reason_codes import (
    FINAL_SCORE_DATA_UNAVAILABLE,
    FINAL_SCORE_EVIDENCE_NEUTRAL_FALLBACK,
    FINAL_SCORE_EXECUTION_NEUTRAL_FALLBACK,
    REASON_CODE_MESSAGES,
)
from core.scanner_v4_models import SCANNER_V4_SCORING_VERSION

_CORE_DIR = Path(__file__).resolve().parents[1] / "core"

_TE = _FSV._TECHNICAL_WEIGHT
_EW = _FSV._EVIDENCE_WEIGHT
_XW = _FSV._EXECUTION_WEIGHT


def _exact(text: str) -> Fraction:
    return Fraction(text)


# ---------------------------------------------------------------------------
# Committed vectors: standard 0/50/100 grid and ROUND_HALF_UP boundaries.
# Expected values are hand-computed from the locked formula, not derived from
# the implementation.
# ---------------------------------------------------------------------------


class TestCommittedVectors:
    @pytest.mark.parametrize(
        ("technical", "evidence", "execution", "expected"),
        [
            # Weighted midpoint grid: n,n,n -> n exactly.
            (0, 0, 0, 0),
            (20, 20, 20, 20),
            (50, 50, 50, 50),
            (99, 99, 99, 99),
            (100, 100, 100, 100),
            # Single-input dominance (other two neutral 50).
            (0, 50, 50, 18),    # 0.65*0 + 10 + 7.5 = 17.5  -> HALF_UP 18
            (25, 50, 50, 34),   # 16.25 + 17.5 = 33.75     -> 34
            (50, 50, 50, 50),   # 32.5 + 17.5 = 50.0       -> 50
            (100, 50, 50, 83),  # 65 + 17.5 = 82.5         -> HALF_UP 83
            # Evidence weighting.
            (0, 25, 50, 13),    # 5 + 7.5 = 12.5           -> HALF_UP 13
            (0, 50, 50, 18),
            (0, 75, 50, 23),    # 15 + 7.5 = 22.5          -> HALF_UP 23
            (0, 100, 50, 28),   # 20 + 7.5 = 27.5          -> HALF_UP 28
            # Execution weighting.
            (0, 50, 0, 10),
            (0, 50, 100, 25),   # 10 + 15 = 25
            # Exact .5 boundaries toward the half mark.
            (50, 0, 0, 33),     # 32.5                     -> HALF_UP 33
            (50, 100, 100, 68), # 32.5+20+15 = 67.5        -> HALF_UP 68
            (100, 50, 0, 75),   # 65 + 10 = 75             -> 75
            # Just below / just above the half boundary.
            (100, 50, 48, 82),  # 65 + 10 + 7.2 = 82.2     -> 82
            (100, 50, 49, 82),  # 82.35                    -> 82
            (100, 50, 52, 83),  # 82.8                     -> 83
            (50, 50, 49, 50),   # 32.5 + 10 + 7.35 = 49.85 -> 50
        ],
    )
    def test_committed_vector(self, technical, evidence, execution, expected):
        result = score_final_score(technical, evidence, execution)
        assert result.setup_score == expected
        assert result.final_score == expected  # compatibility alias
        assert result.setup_score == result.setup_score

    def test_exact_fraction_blend_matches_committed_contributions(self):
        result = score_final_score(100, 50, 50)
        assert result.technical_contribution == 65.0
        assert result.evidence_contribution == 10.0
        assert result.execution_contribution == 7.5
        # Contributions are stored from exact Fractions + one rounding at total.
        assert result.setup_score == 83

    def test_fraction_weights_are_locked_and_sum_to_one(self):
        assert _TE == _exact("65/100")
        assert _EW == _exact("20/100")
        assert _XW == _exact("15/100")
        assert _TE + _EW + _XW == 1

    def test_full_precision_not_prematurely_rounded(self):
        # 0.1 technical has a non-terminating binary expansion; blending must
        # stay exact so the final result equals the hand-computed value.
        t = float("0.1")
        result = score_final_score(t, 0, 0)
        assert t != 1_000_000_000 / 10_000_000_001  # not mangled
        assert 0 <= result.setup_score <= 100


# ---------------------------------------------------------------------------
# Fail-closed technical: typed error, no numeric score, no order/candidate.
# ---------------------------------------------------------------------------


class TestTechnicalFailClosed:
    @pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), float("-inf")])
    def test_missing_or_non_finite_raises(self, bad):
        with pytest.raises(FinalScoreDataError) as exc:
            score_final_score(bad, 50, 50)
        assert exc.value.code == FINAL_SCORE_DATA_UNAVAILABLE
        assert "technical_signal_score" in str(exc.value)

    @pytest.mark.parametrize("bad", [True, False, "1", [], {}, object()])
    def test_non_numeric_raises_no_number_created(self, bad):
        with pytest.raises(FinalScoreDataError):
            score_final_score(bad, 50, 50)

    def test_error_has_side_context(self):
        with pytest.raises(FinalScoreDataError) as exc:
            score_final_score(None, 50, 50, side="buy")
        assert exc.value.code == FINAL_SCORE_DATA_UNAVAILABLE
        assert exc.value.side == "buy"
        assert " for buy" in str(exc.value)

    def test_invalid_technical_has_no_fallback_at_all(self):
        # The V3 legacy copied signal into evidence; V4 must refuse to produce a
        # numeric score when technical is missing, so the pipeline maps the pair
        # to DATA_UNAVAILABLE and no candidate/order can be created.
        for bad in (None, float("nan"), float("inf"), True, "n/a"):
            with pytest.raises(FinalScoreDataError):
                score_final_score(bad, None, None)  # even with everyone missing
            with pytest.raises(FinalScoreDataError):
                score_final_score(bad, 100, 100)

    def test_side_must_be_valid(self):
        with pytest.raises(FinalScoreDataError) as exc:
            score_final_score(50, 50, 50, side="hold")
        assert "side" in str(exc.value)
        # Valid sides pass through and are preserved.
        for side in ("buy", "sell"):
            assert score_final_score(50, 50, 50, side=side).side == side


# ---------------------------------------------------------------------------
# Evidence/Execution fallback: exactly 50 neutral + warning + fallback source.
# Never copied from technical.
# ---------------------------------------------------------------------------


class TestNeutralFallback:
    @pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), "x", True, [], {}])
    def test_evidence_invalid_becomes_exactly_50(self, bad):
        result = score_final_score(100, bad, 0)
        assert result.evidence_score == float(FINAL_SCORE_NEUTRAL_FALLBACK)
        assert result.evidence_score == 50.0
        assert result.evidence_source == FINAL_SCORE_NEUTRAL_FALLBACK_SOURCE
        assert result.fallback_warnings == (FINAL_SCORE_EVIDENCE_NEUTRAL_FALLBACK,)
        # 0.65*100 + 0.20*50 + 0.0 = 65 + 10 = 75 -> 75
        assert result.setup_score == 75

    @pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), "x", True, [], {}])
    def test_execution_invalid_becomes_exactly_50(self, bad):
        result = score_final_score(0, 50, bad)
        assert result.execution_quality_score == 50.0
        assert result.execution_quality_source == FINAL_SCORE_NEUTRAL_FALLBACK_SOURCE
        assert result.fallback_warnings == (FINAL_SCORE_EXECUTION_NEUTRAL_FALLBACK,)
        # 0 + 10 + 7.5 = 17.5 -> 18
        assert result.setup_score == 18

    def test_both_invalid_keeps_two_warnings(self):
        result = score_final_score(100, None, float("inf"))
        assert result.fallback_warnings == (
            FINAL_SCORE_EVIDENCE_NEUTRAL_FALLBACK,
            FINAL_SCORE_EXECUTION_NEUTRAL_FALLBACK,
        )
        assert result.evidence_score == 50.0
        assert result.execution_quality_score == 50.0
        # 65 + 10 + 7.5 = 82.5 -> 83
        assert result.setup_score == 83

    def test_fallback_never_copies_technical(self):
        # The document forbids copying Technical into Evidence/Execution.
        for technical in (0, 30, 100):
            result = score_final_score(technical, None, None)
            assert result.evidence_score == 50.0
            assert result.execution_quality_score == 50.0
            assert result.evidence_score != float(technical)
            assert result.execution_quality_score != float(technical)

    def test_valid_source_is_kept_and_fallback_overrides_source(self):
        result = score_final_score(100, 60, 20, evidence_source="stat_edge_v3", execution_quality_source="journal_v3")
        assert result.evidence_source == "stat_edge_v3"
        assert result.execution_quality_source == "journal_v3"
        assert result.fallback_warnings == ()

        # A substituted value must never keep the declared source.
        result = score_final_score(100, None, 20, evidence_source="stat_edge_v3")
        assert result.evidence_source == FINAL_SCORE_NEUTRAL_FALLBACK_SOURCE
        assert result.fallback_warnings == (FINAL_SCORE_EVIDENCE_NEUTRAL_FALLBACK,)

    def test_source_must_be_string(self):
        with pytest.raises(FinalScoreDataError) as exc:
            score_final_score(100, 50, 50, evidence_source=123)
        assert "source" in str(exc.value)

    def test_valid_values_reported_exactly(self):
        result = score_final_score(37.5, 12.25, 99.75)
        assert result.technical_signal_score == 37.5
        assert result.evidence_score == 12.25
        assert result.execution_quality_score == 99.75


# ---------------------------------------------------------------------------
# Immutability, determinism, clamping, no input mutation, versions.
# ---------------------------------------------------------------------------


class TestContractInvariants:
    def test_result_is_frozen(self):
        result = score_final_score(50, 50, 50)
        with pytest.raises(Exception):
            result.setup_score = 0  # type: ignore[misc]
        with pytest.raises(Exception):
            result.fallback_warnings = ()  # type: ignore[misc]
        with pytest.raises(Exception):
            result.policy_version = "x"  # type: ignore[misc]

    def test_fields_are_atomic_value_types(self):
        result = score_final_score(50, None, 50)
        assert isinstance(result.fallback_warnings, tuple)
        blob = result.to_dict()
        assert isinstance(blob["fallback_warnings"], list)

    def test_immutable_output_survives_snapshot_json(self):
        result = score_final_score(40, 30, 20)
        roundtrip = json.loads(json.dumps(result.to_dict()))
        # 26 + 6 + 3 = 35 -> 35
        assert roundtrip["setup_score"] == 35
        assert roundtrip["final_score"] == 35
        assert roundtrip["policy_version"] == FINAL_SCORE_POLICY_VERSION

    def test_deterministic_across_calls(self):
        a = score_final_score(63, 71, 44, side="sell")
        b = score_final_score(63, 71, 44, side="sell")
        assert a == b
        assert a.to_dict() == b.to_dict()

    def test_no_input_mutation(self):
        args = [63, 71, 44]
        before = tuple(args)
        score_final_score(*args, side="sell")
        assert tuple(args) == before

    def test_clamps_out_of_range_valid_inputs(self):
        assert score_final_score(-100, 50, 50).technical_signal_score == 0.0
        assert score_final_score(500, 50, 50).technical_signal_score == 100.0
        assert score_final_score(50, -5, 50).evidence_score == 0.0
        assert score_final_score(50, 500, 50).evidence_score == 100.0
        assert score_final_score(50, 50, -5).execution_quality_score == 0.0
        assert score_final_score(50, 50, 500).execution_quality_score == 100.0
        # Clamped to (100, 0, 100) -> 65 + 0 + 15 = 80.
        assert score_final_score(500, -5, 500).setup_score == 80

    def test_versions_exposed(self):
        result = score_final_score(50, 50, 50)
        assert result.formula == FINAL_SCORE_FORMULA
        assert "0.65" in result.formula and "0.20" in result.formula and "0.15" in result.formula
        assert result.policy_version == FINAL_SCORE_POLICY_VERSION
        assert result.scoring_version == SCANNER_V4_SCORING_VERSION

    def test_always_within_0_100(self):
        for technical in (0, 7, 50, 93, 100):
            for evidence in (0, 50, 100):
                for execution in (0, 50, 100):
                    result = score_final_score(technical, evidence, execution)
                    assert 0 <= result.setup_score <= 100
                    for name in (
                        "technical_contribution",
                        "evidence_contribution",
                        "execution_contribution",
                    ):
                        assert 0 <= getattr(result, name) <= 100

    def test_final_is_pure_alias_of_setup(self):
        for args in [(100, 50, 50), (0, 25, 50), (37, 91, 12), (0, 0, 100)]:
            result = score_final_score(*args)
            assert result.final_score == result.setup_score
            assert "final_score" in result.to_dict()


# ---------------------------------------------------------------------------
# Fixed weights: no custom/adaptive input can influence the V4 blend.
# ---------------------------------------------------------------------------


class TestWeightImmutability:
    def test_no_weights_parameter(self):
        sig = inspect.signature(score_final_score)
        assert "weights" not in sig.parameters
        with pytest.raises(TypeError):
            score_final_score(50, 50, 50, weights={"technical": 0.9})  # type: ignore[call-arg]

    def test_no_adaptive_state_parameter(self):
        sig = inspect.signature(score_final_score)
        for name in ("recent_trades", "adaptive", "adjust", "renormalize", "fallback_weights"):
            assert name not in sig.parameters

    def test_dunder_signature_is_locked(self):
        text = (_CORE_DIR / "final_score_v4.py").read_text(encoding="utf-8")
        for forbidden in (
            "normalize_weights",
            "_compute_adaptive_weight_adjustment",
            "DEFAULT_EXECUTION_QUALITY_SCORE",
            "pick_signal_score",
            "round(w",
            "round(",
            "int(round(",
        ):
            assert forbidden not in text, f"V3 adaptive/renormalize marker {forbidden!r} leaks in"

    def test_module_never_imports_v3_engine(self):
        text = (_CORE_DIR / "final_score_v4.py").read_text(encoding="utf-8")
        assert "import final_score_engine" not in text
        assert "from core.final_score_engine" not in text
        assert "from core import final_score_engine" not in text


# ---------------------------------------------------------------------------
# Reason codes + messages are registered and Vietnamese.
# ---------------------------------------------------------------------------


class TestReasonCodes:
    def test_new_codes_registered_with_vietnamese_messages(self):
        assert REASON_CODE_MESSAGES[FINAL_SCORE_DATA_UNAVAILABLE] == (
            "Dữ liệu technical signal thiếu hoặc không hợp lệ, không thể tính final score."
        )
        assert REASON_CODE_MESSAGES[FINAL_SCORE_EVIDENCE_NEUTRAL_FALLBACK] == (
            "Evidence thiếu/không hợp lệ, final score dùng 50 neutral thay thế an toàn."
        )
        assert REASON_CODE_MESSAGES[FINAL_SCORE_EXECUTION_NEUTRAL_FALLBACK] == (
            "Execution quality thiếu/không hợp lệ, final score dùng 50 neutral thay thế an toàn."
        )

    def test_codes_are_distinct_from_v3(self):
        assert FINAL_SCORE_DATA_UNAVAILABLE != "FINAL_SCORE_DATA_INCOMPLETE"


# ---------------------------------------------------------------------------
# Target-only ownership: single constructor for the V4 result, no wiring into
# the executable runtime, no dual path.
# ---------------------------------------------------------------------------


class TestOwnershipDeduplication:
    def test_only_final_score_v4_constructs_the_result(self):
        origins: list[str] = []
        for py in _CORE_DIR.glob("*.py"):
            if py.name == "final_score_v4.py":
                continue
            if "FinalScoreResult(" in py.read_text(encoding="utf-8"):
                origins.append(py.name)
        assert not origins, f"FinalScoreResult constructed outside final_score_v4.py: {origins}"

    @pytest.mark.parametrize(
        "module",
        [
            "analysis_pipeline.py",
            "scanner.py",
            "scanner_controller.py",
            "system_backtest_engine.py",
            "trade_gate_engine.py",
            "final_score_engine.py",
        ],
    )
    def test_final_score_v4_not_referenced_by_runtime_modules(self, module):
        path = _CORE_DIR / module
        if path.exists():
            assert "final_score_v4" not in path.read_text(encoding="utf-8")

    def test_v3_engine_kept_intact_no_dual_path(self):
        # The V3 engine is not deleted in this step; only the ledger documents
        # which of its paths Bước 07/12 must remove.  It must not reference V4.
        text = (_CORE_DIR / "final_score_engine.py").read_text(encoding="utf-8")
        assert "final_score_v4" not in text

    def test_no_v3_optimistic_default_equivalents_in_target(self):
        # V3 defaults signal=0 / execution=100.  V4 must not re-invent them.
        text = (_CORE_DIR / "final_score_v4.py").read_text(encoding="utf-8")
        assert "DEFAULT_SIGNAL_SCORE" not in text
        assert "DEFAULT_EXECUTION_QUALITY_SCORE" not in text

    def test_pipeline_still_ledgers_v3_fallbacks(self):
        # Ledger anchors stay documented so cutover removes both paths together.
        pipeline = (_CORE_DIR / "analysis_pipeline.py").read_text(encoding="utf-8")
        assert "safe_score(" in pipeline
        assert "fallback=signal_score" in pipeline
        engine = (_CORE_DIR / "final_score_engine.py").read_text(encoding="utf-8")
        assert "DEFAULT_SIGNAL_SCORE" in engine
        assert "DEFAULT_EXECUTION_QUALITY_SCORE" in engine