"""Scanner V4 Step 05: target-only MacroAssessment + MacroGate contract.

Covers the full assessment/gate matrix, provenance, side consistency,
fail-closed OPEN-policy semantics, aggregate precedence, determinism,
TechnicalScore invariance, and the ownership deduplication /
runtime-isolation guards that keep this step target-only.
"""

from __future__ import annotations

import json
import inspect
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.macro_gate import (
    CONFLICT_CAP_BLOCK_SENTINEL,
    DEFAULT_MACRO_POLICY,
    MacroGate,
    MacroGateError,
    MacroPolicy,
    VALID_MACRO_DECISION_CAPS,
    build_macro_assessment,
    classify_macro_status,
)
from core.reason_codes import (
    MACRO_ALIGNED,
    MACRO_CONFIDENCE_THRESHOLD_UNSET,
    MACRO_CONFLICT,
    MACRO_CONFLICT_CAP_UNSET,
    MACRO_DATA_UNAVAILABLE,
    MACRO_DEADBAND_UNSET,
    MACRO_LOW_CONFIDENCE,
    MACRO_NEUTRAL,
    MACRO_SIDE_MISSING,
    MACRO_UNKNOWN_CAP_UNSET,
    REASON_CODE_MESSAGES,
)
from core.scanner_v4_models import (
    ALIGNED,
    BLOCK,
    BLOCKED,
    BUY,
    CAUTION,
    CONFLICT,
    DATA_UNAVAILABLE,
    MACRO_UNKNOWN,
    NEUTRAL,
    PASS,
    SCANNER_V4_MACRO_POLICY_VERSION,
    SELL,
    UNKNOWN,
    WAITING_CONFIRMATION,
    WATCH_ZONE,
    MacroAssessment,
    MacroGateResult,
)
from core.smc_models import SMC_DOMAIN_VERSION
from core.smc_scoring_result import (
    SMC_SCORING_CONTRACT_VERSION,
    SmcScoringResult,
    SmcSideScoringResult,
)
from core.smc_versions import SMC_SCORER_VERSION
from core.technical_signal_scorer import score_technical_signal

_NOW = datetime(2026, 8, 13, 9, 30, tzinfo=timezone.utc)
_CORE_DIR = Path(__file__).resolve().parents[1] / "core"

# Locked test policy: deadband 2 raw points, confidence >= 0.7, conflict ->
# CAUTION + WAITING_CONFIRMATION, unknown -> WATCH_ZONE.
LOCKED_POLICY = MacroPolicy(
    policy_version=SCANNER_V4_MACRO_POLICY_VERSION,
    deadband_points=2,
    confidence_threshold=0.7,
    conflict_cap=WAITING_CONFIRMATION,
    unknown_cap=WATCH_ZONE,
)


def _assessment(**kw) -> MacroAssessment:
    base: dict = {
        "symbol": "XOM",
        "captured_at": _NOW,
        "raw_buy": 20,
        "raw_sell": 10,
        "confidence": 0.9,
        "assessed_side": BUY,
        "deadband_points": 2,
    }
    base.update(kw)
    return build_macro_assessment(**base)


def _evaluate(
    assessment: MacroAssessment,
    *,
    side: str | None = BUY,
    policy: MacroPolicy | None = None,
) -> MacroGateResult:
    return MacroGate().evaluate(
        assessment,
        assessed_side=side,
        policy=policy if policy is not None else LOCKED_POLICY,
        now=_NOW,
    )


# ---------------------------------------------------------------------------
# Classification matrix
# ---------------------------------------------------------------------------


class TestClassifyStatus:
    @pytest.mark.parametrize(
        "raw_buy,raw_sell,side,db,expected",
        [
            (20, 10, BUY, 2, ALIGNED),
            (10, 20, SELL, 2, ALIGNED),
            (18, 20, BUY, 2, NEUTRAL),  # |diff| == deadband -> neutral
            (19, 20, BUY, 2, NEUTRAL),  # |diff| < deadband -> neutral
            (20, 18, BUY, 2, NEUTRAL),
            (20, 23, BUY, 2, CONFLICT),
            (10, 20, BUY, 2, CONFLICT),
            (20, 10, SELL, 2, CONFLICT),  # side flip mirrors the spread
            (30, 0, BUY, 2, ALIGNED),
            (0, 30, SELL, 2, ALIGNED),
            (0, 30, BUY, 2, CONFLICT),
            (30, 0, SELL, 2, CONFLICT),
        ],
    )
    def test_matrix(self, raw_buy, raw_sell, side, db, expected):
        assert classify_macro_status(raw_buy, raw_sell, side, db) == expected

    @pytest.mark.parametrize(
        "raw_buy,raw_sell,side,db",
        [
            (20, 10, BUY, None),  # uncalibrated deadband cannot certify
            (20, None, BUY, 2),
            (None, 10, BUY, 2),
            (20, 10, None, 2),
            (20, 10, "north", 2),
        ],
    )
    def test_fail_closed_unknown(self, raw_buy, raw_sell, side, db):
        assert classify_macro_status(raw_buy, raw_sell, side, db) == MACRO_UNKNOWN

    def test_pure_deterministic(self):
        assert classify_macro_status(20, 10, BUY, 2) == ALIGNED
        assert classify_macro_status(20, 10, BUY, 2) == ALIGNED


# ---------------------------------------------------------------------------
# Gate matrix under a locked policy
# ---------------------------------------------------------------------------


class TestGateMatrix:
    def test_aligned_is_pass_without_cap(self):
        result = _evaluate(_assessment())
        assert result.status == PASS
        assert result.decision_cap is None
        assert MACRO_ALIGNED in result.reason_codes

    def test_neutral_is_pass_without_cap(self):
        result = _evaluate(_assessment(raw_buy=18, raw_sell=20))
        assert result.status == PASS
        assert result.decision_cap is None
        assert MACRO_NEUTRAL in result.reason_codes

    def test_conflict_is_caution_with_cap(self):
        result = _evaluate(_assessment(raw_buy=10, raw_sell=20))
        assert result.status == CAUTION
        assert result.decision_cap == WAITING_CONFIRMATION
        assert result.reason_codes == (MACRO_CONFLICT,)

    def test_conflict_block_sentinel(self):
        policy = MacroPolicy(
            deadband_points=2,
            confidence_threshold=0.7,
            conflict_cap=CONFLICT_CAP_BLOCK_SENTINEL,
            unknown_cap=WATCH_ZONE,
        )
        result = _evaluate(_assessment(raw_buy=10, raw_sell=20), policy=policy)
        assert result.status == BLOCK
        assert result.decision_cap == BLOCKED

    def test_unknown_cap_carried_on_unknown_results(self):
        # Low confidence grants nothing -> UNKNOWN with the WATCH_ZONE cap.
        result = _evaluate(_assessment(raw_buy=10, raw_sell=20, confidence=0.4))
        assert result.status == UNKNOWN
        assert result.decision_cap == WATCH_ZONE
        assert MACRO_LOW_CONFIDENCE in result.reason_codes

    def test_missing_raw_data_is_unknown(self):
        result = _evaluate(_assessment(raw_sell=None, deadband_points=None))
        assert result.status == UNKNOWN
        assert result.decision_cap == WATCH_ZONE
        assert MACRO_DATA_UNAVAILABLE in result.reason_codes

    def test_missing_confidence_is_unknown(self):
        result = _evaluate(_assessment(confidence=None, deadband_points=None))
        assert result.status == UNKNOWN
        assert result.decision_cap == WATCH_ZONE
        assert MACRO_DATA_UNAVAILABLE in result.reason_codes

    def test_missing_side_is_unknown(self):
        result = _evaluate(_assessment(assessed_side=None), side=None)
        assert result.status == UNKNOWN
        assert result.decision_cap == WATCH_ZONE
        assert result.reason_codes == (MACRO_SIDE_MISSING,)

    def test_capped_unknown_is_not_marked_unset(self):
        result = _evaluate(_assessment(confidence=0.4))
        assert result.decision_cap == WATCH_ZONE
        assert MACRO_UNKNOWN_CAP_UNSET not in result.reason_codes

    def test_assessed_side_and_policy_version_surface(self):
        result = _evaluate(_assessment())
        assert result.assessed_side == BUY
        assert result.policy_version == SCANNER_V4_MACRO_POLICY_VERSION


# ---------------------------------------------------------------------------
# OPEN policy (DEFAULT_MACRO_POLICY) fail-closed certification
# ---------------------------------------------------------------------------


class TestFailClosedOpenPolicy:
    def test_default_policy_never_passes(self):
        for kw in (
            {"deadband_points": None},  # full data but band uncalibrated
            {"raw_sell": None, "deadband_points": None},
            {"confidence": None, "deadband_points": None},
            {"assessed_side": None, "deadband_points": None},
        ):
            result = _evaluate(_assessment(**kw), policy=DEFAULT_MACRO_POLICY)
            assert result.status == UNKNOWN, kw
            assert result.status not in {PASS, CAUTION, BLOCK}

    def test_open_deadband_is_explicit(self):
        result = _evaluate(
            _assessment(deadband_points=None),
            policy=DEFAULT_MACRO_POLICY,
        )
        assert result.status == UNKNOWN
        assert MACRO_DEADBAND_UNSET in result.reason_codes

    def test_open_confidence_threshold_is_explicit(self):
        policy = MacroPolicy(deadband_points=2)
        result = _evaluate(_assessment(), policy=policy)
        assert result.status == UNKNOWN
        assert MACRO_CONFIDENCE_THRESHOLD_UNSET in result.reason_codes

    def test_open_conflict_cap_is_explicit(self):
        policy = MacroPolicy(deadband_points=2, confidence_threshold=0.7)
        result = _evaluate(_assessment(raw_buy=10, raw_sell=20), policy=policy)
        assert result.status == UNKNOWN
        assert MACRO_CONFLICT_CAP_UNSET in result.reason_codes

    def test_uncapped_unknown_is_explicit_under_open_unknown_cap(self):
        policy = MacroPolicy(deadband_points=2, confidence_threshold=0.7)
        result = _evaluate(
            _assessment(raw_sell=None, deadband_points=None),
            policy=policy,
        )
        assert result.status == UNKNOWN
        assert result.decision_cap is None
        assert MACRO_DATA_UNAVAILABLE in result.reason_codes
        assert MACRO_UNKNOWN_CAP_UNSET in result.reason_codes


# ---------------------------------------------------------------------------
# Policy validation
# ---------------------------------------------------------------------------


class TestPolicyValidation:
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"policy_version": "scanner-macro-policy-v3"},
            {"deadband_points": 0},
            {"deadband_points": -2},
            {"deadband_points": 2.5},
            {"deadband_points": True},
            {"confidence_threshold": 1.1},
            {"confidence_threshold": -0.1},
            {"conflict_cap": "PROMOTE"},
            {"unknown_cap": "RANDOM"},
            {"deadband_semantics_version": "scanner-macro-deadband-raw-v9"},
            {"cap_semantics_version": "scanner-macro-cap-v9"},
        ],
    )
    def test_rejects_invalid_policy(self, kwargs):
        base = dict(
            policy_version=SCANNER_V4_MACRO_POLICY_VERSION,
            deadband_points=2,
            confidence_threshold=0.7,
            conflict_cap=WAITING_CONFIRMATION,
            unknown_cap=WATCH_ZONE,
        )
        base.update(kwargs)
        with pytest.raises(MacroGateError):
            MacroPolicy(**base)

    def test_allows_blocked_as_a_conflict_cap_membership_value(self):
        policy = MacroPolicy(conflict_cap=BLOCKED, unknown_cap=None)
        assert policy.conflict_cap == BLOCKED

    def test_allows_data_unavailable_unknown_cap(self):
        policy = MacroPolicy(unknown_cap=DATA_UNAVAILABLE)
        assert policy.unknown_cap == DATA_UNAVAILABLE


class TestAssessmentValidation:
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"symbol": ""},
            {"symbol": "   "},
            {"captured_at": "2026-08-13T09:30:00Z"},  # not a datetime
            {"raw_buy": 31},
            {"raw_buy": -1},
            {"raw_buy": 20.5},
            {"raw_sell": 31},
            {"confidence": 1.5},
            {"confidence": -0.1},
            {"assessed_side": "long"},
            {"deadband_points": 0},
            {"deadband_points": -1},
            {"correlation_context": [("vix", 18.5)]},  # list, not mapping
            {"macro_sources": "nonsense"},
            {"events": 42},
            {"events": [("not", "a", "mapping")]},
        ],
    )
    def test_rejects_invalid_assessment_input(self, kwargs):
        with pytest.raises(MacroGateError):
            _assessment(**kwargs)


# ---------------------------------------------------------------------------
# Side consistency (the gate stays the decision owner)
# ---------------------------------------------------------------------------


class TestSideConsistency:
    def test_buy_aligned_rejected_on_sell(self):
        assessment = _assessment()  # raw buy 20 / sell 10, built for side=buy
        with pytest.raises(MacroGateError):
            _evaluate(assessment, side=SELL)

    def test_sell_aligned_rejected_on_buy(self):
        assessment = _assessment(raw_buy=10, raw_sell=20, assessed_side=SELL)
        with pytest.raises(MacroGateError):
            _evaluate(assessment, side=BUY)

    def test_neutral_combination_both_sides(self):
        for side in (BUY, SELL):
            assessment = _assessment(
                raw_buy=18, raw_sell=20, assessed_side=side, deadband_points=2
            )
            result = _evaluate(assessment, side=side)
            assert result.status == PASS

    def test_unsided_assessment_cannot_be_reinterpreted(self):
        assessment = _assessment(assessed_side=None, deadband_points=None)
        with pytest.raises(MacroGateError):
            _evaluate(assessment, side=BUY)
        # Fully unsided evaluation still resolves fail-closed.
        result = _evaluate(assessment, side=None)
        assert result.status == UNKNOWN
        assert result.reason_codes == (MACRO_SIDE_MISSING,)

    def test_gate_rejects_a_forged_status(self):
        # The canonical builder derives status; a hand-rolled assessment whose
        # status contradicts its own raws is rejected by the gate (single owner).
        forged = MacroAssessment(
            raw_buy=10,
            raw_sell=20,  # conflict for buy with db=2 ...
            confidence=0.9,
            status=ALIGNED,  # ... but claims aligned
            correlation_context={"vix": 18.5},
            provenance={"symbol": "XOM", "captured_at": _NOW.isoformat()},
        )
        with pytest.raises(MacroGateError):
            _evaluate(forged, side=BUY)


# ---------------------------------------------------------------------------
# Aggregate invariants
# ---------------------------------------------------------------------------


class TestAggregateInvariants:
    @pytest.mark.parametrize("status", [CONFLICT, MACRO_UNKNOWN])
    def test_non_passible_assessment_never_gates_pass(self, status):
        assessment = (
            _assessment(raw_buy=10, raw_sell=20)
            if status == CONFLICT
            else _assessment(raw_sell=None, deadband_points=None)
        )
        assert assessment.status == status
        result = _evaluate(assessment)
        assert result.status != PASS

    def test_block_always_carries_blocked_cap(self):
        policy = MacroPolicy(
            deadband_points=2,
            confidence_threshold=0.7,
            conflict_cap=CONFLICT_CAP_BLOCK_SENTINEL,
            unknown_cap=WATCH_ZONE,
        )
        result = _evaluate(_assessment(raw_buy=10, raw_sell=20), policy=policy)
        assert result.status == BLOCK
        assert result.decision_cap == BLOCKED

    def test_pass_is_explicit_and_uncapped(self):
        result = _evaluate(_assessment())
        assert result.status == PASS
        assert result.assessed_side == BUY
        assert result.decision_cap is None
        assert result.provenance
        assert all(
            code in {MACRO_ALIGNED, MACRO_NEUTRAL}
            for code in result.reason_codes
        )

    def test_nonpass_has_at_least_one_reason(self):
        for kw in ({"raw_sell": None, "deadband_points": None}, {"confidence": 0.3}):
            result = _evaluate(_assessment(**kw))
            assert result.status != PASS
            assert result.reason_codes

    def test_unknown_wins_over_caution(self):
        # Conflict raws alone would be CAUTION; low confidence escalates the
        # aggregate to UNKNOWN (precedence UNKNOWN > CAUTION).
        result = _evaluate(_assessment(raw_buy=10, raw_sell=20, confidence=0.4))
        assert result.status == UNKNOWN
        assert result.decision_cap == WATCH_ZONE

    def test_reason_codes_deduplicated(self):
        result = _evaluate(_assessment(raw_buy=10, raw_sell=20))
        assert len(result.reason_codes) == len(set(result.reason_codes))
        assert set(result.reason_codes) == {MACRO_CONFLICT}

    def test_checked_at_and_side_fidelity(self):
        result = _evaluate(_assessment())
        assert result.checked_at == _NOW
        assert result.assessed_side == BUY


# ---------------------------------------------------------------------------
# Provenance & determinism
# ---------------------------------------------------------------------------


class TestProvenanceAndDeterminism:
    def test_assessment_provenance_roundtrip_shape(self):
        assessment = _assessment(
            macro_sources={"calendar": "fed"},
            correlation_context={"vix": 18.5, "usd_index": 96.2},
            events=[{"id": "CPI", "severity": "HIGH"}],
        )
        prov = assessment.provenance
        assert prov["symbol"] == "XOM"
        assert dict(prov["correlation"]) == {"vix": 18.5, "usd_index": 96.2}
        assert [dict(event) for event in prov["events"]] == [{"id": "CPI", "severity": "HIGH"}]
        # No forbidden or identity fields at any nesting level.
        blob = json.dumps(assessment.to_dict())
        assert "macro_alignment" not in blob
        assert "scoring_version" not in blob

    def test_evaluate_is_deterministic(self):
        assessment = _assessment(raw_buy=10, raw_sell=20)
        first = _evaluate(assessment).to_dict()
        second = _evaluate(assessment).to_dict()
        assert first == second

    def test_checked_at_is_the_only_now_dependency(self):
        base = _evaluate(_assessment()).to_dict()
        later = datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)
        result = MacroGate().evaluate(_assessment(), assessed_side=BUY, policy=LOCKED_POLICY, now=later)
        other = result.to_dict()
        assert other["checked_at"] == later.isoformat()
        assert other["assessed_side"] == base["assessed_side"]
        assert other["status"] == base["status"]
        assert other["decision_cap"] == base["decision_cap"]
        assert other["reason_codes"] == base["reason_codes"]

    def test_gate_provenance_records_policy(self):
        result = _evaluate(_assessment(raw_buy=10, raw_sell=20))
        policy = result.provenance["policy"]
        assert policy["deadband_points"] == 2
        assert policy["confidence_threshold"] == 0.7
        assert policy["conflict_cap"] == WAITING_CONFIRMATION
        assert policy["unknown_cap"] == WATCH_ZONE

    def test_reason_codes_registered(self):
        result = _evaluate(_assessment(raw_sell=None, deadband_points=None))
        for code in result.reason_codes:
            assert code in REASON_CODE_MESSAGES


# ---------------------------------------------------------------------------
# TechnicalScore invariance: macro never touches the technical score
# ---------------------------------------------------------------------------

_SIDE_KEYS = {BUY: ("buy", "demand_zone"), SELL: ("sell", "supply_zone")}


def _smc_side(
    side: str,
    *,
    subtotal: int,
    evidence: str,
) -> SmcSideScoringResult:
    side_key, zone_type = _SIDE_KEYS[side]
    structure = min(5, subtotal)
    zone = min(5, subtotal - structure)
    ltf = min(3, subtotal - structure - zone)
    technical = subtotal - structure - zone - ltf
    has_zone = zone > 0
    setup_score = {1: 25, 2: 40, 3: 55, 4: 70, 5: 85}.get(zone)
    zone_id = f"zone-{side}-0" if has_zone else None
    reasons = (f"{evidence}",)
    breakdown = {
        "side": side,
        "total": subtotal,
        "structure_score": structure,
        "zone_score": zone,
        "ltf_confirmation_score": ltf,
        "technical_validation_score": technical,
        "subtotal": subtotal,
        "penalty_points": 0,
        "applied_cap": None,
        "penalties": [],
        "caps": [],
        "selected_zone_id": zone_id,
        "selected_zone_quality_score": 80 if has_zone else None,
        "selected_zone_relevance_score": 70 if has_zone else None,
        "selected_zone_setup_score": setup_score if has_zone else None,
        "reason_codes": list(reasons),
        "scoring_version": SMC_SCORER_VERSION,
        "domain_version": SMC_DOMAIN_VERSION,
    }
    zone_payload = (
        {
            "zone_id": zone_id,
            "direction": side,
            "timeframe": "H4",
            "family": "demand" if side == BUY else "supply",
            "zone_type": zone_type,
            "low": 90.0 if side == BUY else 105.0,
            "high": 95.0 if side == BUY else 110.0,
            "level": 92.5 if side == BUY else 107.5,
            "zone_quality_score": 80,
            "zone_relevance_score": 70,
            "zone_setup_score": setup_score,
            "liquidity_sweep_linked": False,
            "linked_sweep_id": None,
            "linked_sweep_distance_atr": None,
            "linked_sweep_time_delta": None,
            "source": "smc_selected",
            "scoring_version": SMC_SCORER_VERSION,
            "domain_version": SMC_DOMAIN_VERSION,
            "selection_reason_codes": ("H4_TIMEFRAME_PREFERRED",),
            "type": zone_type,
        }
        if has_zone
        else None
    )
    return SmcSideScoringResult(
        score=subtotal,
        breakdown=breakdown,
        selected_zone=zone_payload,
        selected_zone_id=zone_id,
        selected_zone_type=zone_type if has_zone else None,
        selected_zone_timeframe="H4" if has_zone else None,
        reason_codes=reasons,
        smc_reason=evidence,
        selected_zone_score=setup_score if has_zone else None,
        selected_zone_quality_score=80 if has_zone else None,
        selected_zone_relevance_score=70 if has_zone else None,
        selected_zone_setup_score=setup_score if has_zone else None,
    )


def _canonical_smc() -> SmcScoringResult:
    return SmcScoringResult(
        scoring_version=SMC_SCORER_VERSION,
        contract_version=SMC_SCORING_CONTRACT_VERSION,
        sides={
            BUY: _smc_side(BUY, subtotal=10, evidence="BUY_CANONICAL_EVIDENCE"),
            SELL: _smc_side(SELL, subtotal=8, evidence="SELL_CANONICAL_EVIDENCE"),
        },
    )


def _technical_score() -> int:
    return score_technical_signal(
        BUY,
        trend_raw=20,
        momentum_raw=15,
        location_raw=20,
        canonical_smc=_canonical_smc(),
        regime="trending_up",
    ).technical_signal_score


class TestTechnicalScoreInvariance:
    def test_scorer_has_no_macro_or_ai_inputs(self):
        signature = inspect.signature(score_technical_signal)
        params = set(signature.parameters)
        assert not (
            params
            & {
                "macro_buy",
                "macro_sell",
                "macro_confidence",
                "ai_verdict",
                "correlation",
            }
        )
        assert {"trend_raw", "momentum_raw", "location_raw", "canonical_smc", "regime"} <= params

    def test_macro_context_changes_leave_technical_score_unchanged(self):
        baseline = _technical_score()

        # A BLOCK macro gate (conflict under a blocking conflict cap)
        # coexisting with the same data.
        policy = MacroPolicy(
            deadband_points=2,
            confidence_threshold=0.7,
            conflict_cap=CONFLICT_CAP_BLOCK_SENTINEL,
            unknown_cap=WATCH_ZONE,
        )
        blocked = _evaluate(
            _assessment(raw_buy=10, raw_sell=20), policy=policy
        )
        assert blocked.status == BLOCK

        # Technical inputs untouched -> identical score, regardless of the macro
        # magnitudes/confidence/events that only feed the gate.
        assert baseline == _technical_score()

    def test_technical_result_carries_no_macro_dimension(self):
        from core.technical_signal_scorer import TechnicalSignalScoreResult

        result = score_technical_signal(
            BUY,
            trend_raw=20,
            momentum_raw=15,
            location_raw=20,
            canonical_smc=_canonical_smc(),
            regime="trending_up",
        )
        assert isinstance(result, TechnicalSignalScoreResult)
        blob = result.to_dict()
        for marker in ("macro", "macro_alignment", "correlation", "ai_verdict", "confidence"):
            assert marker not in json.dumps(blob)


# ---------------------------------------------------------------------------
# Target-only ownership: single constructor for the V4 macro objects,
# and no wiring into the executable runtime.
# ---------------------------------------------------------------------------


class TestOwnershipDeduplication:
    def test_only_macro_gate_constructs_the_objects_in_target(self):
        constructors = ("MacroAssessment(", "MacroGateResult(")
        origins: dict[str, list[str]] = {}
        for py in _CORE_DIR.glob("*.py"):
            if py.name == "macro_gate.py":
                continue
            text = py.read_text(encoding="utf-8")
            for token in constructors:
                if token in text:
                    origins.setdefault(token, []).append(py.name)
        assert not origins, f"macro objects constructed outside macro_gate.py: {origins}"

    @pytest.mark.parametrize(
        "module",
        [
            "analysis_pipeline.py",
            "scanner.py",
            "scanner_controller.py",
            "system_backtest_engine.py",
            "trade_gate_engine.py",
        ],
    )
    def test_macro_gate_not_referenced_by_runtime_modules(self, module):
        path = _CORE_DIR / module
        if path.exists():
            assert "macro_gate" not in path.read_text(encoding="utf-8")

    def test_target_module_has_no_v3_numeric_mutation_markers(self):
        text = (_CORE_DIR / "macro_gate.py").read_text(encoding="utf-8")
        for marker in (
            "macro_effective",
            "_apply_macro_ai_adjustment",
            "correlation_adjustment",
            "derate",
        ):
            assert marker not in text, f"V3 numeric mutation marker {marker!r} leaks into target"

    def test_gate_never_imports_the_technical_scorer(self):
        import ast

        tree = ast.parse((_CORE_DIR / "macro_gate.py").read_text(encoding="utf-8"))
        imported_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported_modules.add(node.module or "")
            elif isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
        assert "core.technical_signal_scorer" not in imported_modules