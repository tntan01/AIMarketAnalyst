"""Tests for the Scanner V4 analysis pipeline and direct composition (Bước 07).

Target-only discipline: this module validates the composition module in
isolation.  It never wires V4 into runtime, never checks numeric values that
were not calibrated (Bước 04/05 OPEN policies fail closed to UNKNOWN), and
proves the pipeline emits no READY_NOW / OUT_OF_STRATEGY / order payload
(those are Bước 08/12).

Coverage contracts exercised:

* side consistency — every score/scenario/evidence/execution/macro carries an
  explicit side; the best side and gap come only from TechnicalScore; the
  selected side's plan is never borrowed from the other side;
* deterministic snapshot — same input -> identical snapshot_id and canonical
  JSON regardless of the evaluation wall clock (while fresh);
* full-schema fail-closed — stale/future/invalid-technical snapshots produce
  DATA_UNAVAILABLE with the complete V4 schema and no fake scores;
* BLOCK keeps score+scenario — a blocking gate preserves the honest scores and
  scenario for explanation, yet never emits READY_NOW/order payload;
* score invariance — changing only Safety/Macro policies never mutates the
  side scores or the scenario;
* live/backtest parity — the same immutable input through both adapters yields
  the same snapshot_id/decision/scores (differing only in capture_source);
* runtime isolation — the composition module imports no V3 engine and no
  runtime module imports the composition module.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import re
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from pathlib import Path

import pytest

from core.final_score_v4 import (
    FINAL_SCORE_NEUTRAL_FALLBACK_SOURCE,
    FINAL_SCORE_POLICY_VERSION,
)
from core.macro_gate import MacroGate, MacroGateError, MacroPolicy, build_macro_assessment
from core.market_safety_gate import (
    AVAILABILITY_VALID,
    ConnectivitySource,
    DataFreshnessSource,
    MarketSafetyContext,
    MarketSafetyGate,
    MarketSafetyGateError,
    NewsSource,
    SafetyPolicy,
    SpreadSource,
    VolatilitySource,
)
from core.reason_codes import (
    COMPOSE_FLOOR_POLICY_OPEN,
    COMPOSE_SCORE_FLOOR_NOT_MET,
    GATES_ALL_PASS,
    GATE_ACCOUNT_DATA_MISSING,
    GATE_ACCOUNT_MARGIN_BLOCK,
    GATE_JOURNAL_DATA_MISSING,
    GATE_JOURNAL_DRAWDOWN_CAUTION,
    GATE_JOURNAL_POLICY_OPEN,
    GATE_JOURNAL_REVENGE_BLOCK,
    GATE_PORTFOLIO_DATA_MISSING,
    GATE_PORTFOLIO_LIMIT_BLOCK,
    GATE_PORTFOLIO_POLICY_OPEN,
    GATE_SCENARIO_PLAN_MISSING,
    GATE_SCENARIO_POLICY_OPEN,
    GATE_SCENARIO_RR_BLOCK,
    REASON_CODE_MESSAGES,
    SNAPSHOT_FRESHNESS_UNKNOWN,
    SNAPSHOT_STALE,
    TECHNICAL_DATA_UNAVAILABLE,
)
from core.scanner_v4_composition import (
    COMPOSITION_POLICY_VERSION,
    SNAPSHOT_MAX_AGE_SECONDS,
    SNAPSHOT_MAX_FUTURE_SKEW_SECONDS,
    AccountState,
    ComposeOptions,
    CompositionInputError,
    CompositionServiceError,
    CompositionGate,
    JournalState,
    PortfolioState,
    ScenarioEvaluation,
    ScenarioPlan,
    ScannerV4CompositionResult,
    ScannerV4Snapshot,
    SideSnapshot,
    build_backtest_snapshot,
    build_live_snapshot,
    compose_scanner_v4,
    compute_scenario_rr,
    snapshot_id_of,
)
from core.scanner_v4_models import (
    BLOCK,
    BLOCKED,
    BUY,
    CAUTION,
    DATA_UNAVAILABLE,
    PASS,
    SCANNER_V4_MACRO_POLICY_VERSION,
    SCANNER_V4_SAFETY_POLICY_VERSION,
    SCANNER_V4_SCORING_VERSION,
    SELL,
    UNKNOWN,
    WAITING_CONFIRMATION,
    WATCH_ZONE,
    CanonicalPairSnapshot,
)
from core.smc_models import SMC_DOMAIN_VERSION
from core.smc_scoring_result import (
    SMC_SCORING_CONTRACT_VERSION,
    SmcScoringResult,
    SmcSideScoringResult,
)
from core.smc_versions import SMC_SCORER_VERSION
from core.technical_signal_scorer import (
    TechnicalScoreDataError,
    score_technical_signal,
)

UTC = timezone.utc
NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)
CAPTURED = NOW
PROV = {"captured_by": "scanner-v4-target", "feed": "mt5", "session": "test"}

_CORE_DIR = Path(__file__).resolve().parents[1] / "core"


# ---------------------------------------------------------------------------
# Shared fixtures (mirror the canonical SMC constructor used by the scorer)
# ---------------------------------------------------------------------------


def _smc_components(subtotal: int) -> tuple[int, int, int, int]:
    remaining = subtotal
    structure = min(5, remaining)
    remaining -= structure
    zone = min(5, remaining)
    remaining -= zone
    ltf = min(3, remaining)
    remaining -= ltf
    technical = min(2, remaining)
    return structure, zone, ltf, technical


def _smc_side(
    side: str,
    *,
    subtotal: int,
    penalty_points: int = 0,
    applied_cap: int | None = None,
    evidence_code: str = "CANONICAL_STRUCTURE_EVIDENCE",
) -> SmcSideScoringResult:
    structure, zone, ltf, technical = _smc_components(subtotal)
    has_selected_zone = zone > 0
    setup_score = {1: 25, 2: 40, 3: 55, 4: 70, 5: 85}.get(zone)
    source_score = max(0, subtotal - penalty_points)
    if applied_cap is not None:
        source_score = min(source_score, applied_cap)
    zone_id = f"zone-{side}" if has_selected_zone else None
    zone_type = "demand_zone" if side == "buy" else "supply_zone"
    breakdown = {
        "side": side,
        "total": source_score,
        "structure_score": structure,
        "zone_score": zone,
        "ltf_confirmation_score": ltf,
        "technical_validation_score": technical,
        "subtotal": subtotal,
        "penalty_points": penalty_points,
        "applied_cap": applied_cap,
        "penalties": [evidence_code] if penalty_points else [],
        "caps": [evidence_code] if applied_cap is not None else [],
        "selected_zone_id": zone_id,
        "selected_zone_quality_score": 80 if has_selected_zone else None,
        "selected_zone_relevance_score": 70 if has_selected_zone else None,
        "selected_zone_setup_score": setup_score if has_selected_zone else None,
        "reason_codes": [evidence_code],
        "scoring_version": SMC_SCORER_VERSION,
        "domain_version": SMC_DOMAIN_VERSION,
    }
    zone_payload = (
        {
            "zone_id": zone_id,
            "direction": side,
            "timeframe": "H4",
            "family": "demand" if side == "buy" else "supply",
            "zone_type": zone_type,
            "low": 90.0 if side == "buy" else 105.0,
            "high": 95.0 if side == "buy" else 110.0,
            "level": 92.5 if side == "buy" else 107.5,
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
        if has_selected_zone
        else None
    )
    return SmcSideScoringResult(
        score=source_score,
        breakdown=breakdown,
        selected_zone=zone_payload,
        selected_zone_id=zone_id,
        selected_zone_type=zone_type if has_selected_zone else None,
        selected_zone_timeframe="H4" if has_selected_zone else None,
        reason_codes=(evidence_code,),
        smc_reason=evidence_code,
        selected_zone_score=setup_score if has_selected_zone else None,
        selected_zone_quality_score=80 if has_selected_zone else None,
        selected_zone_relevance_score=70 if has_selected_zone else None,
        selected_zone_setup_score=setup_score if has_selected_zone else None,
    )


def _canonical_smc(
    *,
    buy_subtotal: int = 12,
    sell_subtotal: int = 7,
) -> SmcScoringResult:
    return SmcScoringResult(
        scoring_version=SMC_SCORER_VERSION,
        contract_version=SMC_SCORING_CONTRACT_VERSION,
        sides={
            "buy": _smc_side("buy", subtotal=buy_subtotal),
            "sell": _smc_side("sell", subtotal=sell_subtotal),
        },
    )


def _safety_context(
    *,
    captured_at: datetime = CAPTURED,
    spread_points: float = 20.0,
) -> MarketSafetyContext:
    return MarketSafetyContext(
        symbol="XAUUSD",
        captured_at=captured_at,
        connectivity=ConnectivitySource(
            availability=AVAILABILITY_VALID,
            source="mt5_connection_status",
            checked_at=captured_at,
            provenance=PROV,
            terminal_connected=True,
            broker_logged_in=True,
        ),
        data=DataFreshnessSource(
            availability=AVAILABILITY_VALID,
            source="mt5_candles",
            checked_at=captured_at,
            provenance=PROV,
            last_candle_time_utc=captured_at - timedelta(seconds=60),
            intended_timeframe="M15",
        ),
        spread=SpreadSource(
            availability=AVAILABILITY_VALID,
            source="mt5_tick",
            checked_at=captured_at,
            provenance=PROV,
            spread_points=spread_points,
            symbol="XAUUSD",
        ),
        news=NewsSource(
            availability=AVAILABILITY_VALID,
            source="news_service",
            checked_at=captured_at,
            provenance=PROV,
            source_verified=True,
            events=(),
        ),
        volatility=VolatilitySource(
            availability=AVAILABILITY_VALID,
            source="technical_context",
            checked_at=captured_at,
            provenance=PROV,
            volatility_ratio=1.0,
            metric="atr14_h1",
        ),
    )


def _safety_policy(**overrides) -> SafetyPolicy:
    base = {
        "policy_version": SCANNER_V4_SAFETY_POLICY_VERSION,
        "max_candle_age_minutes": 5,
        "spread_threshold_by_symbol": {"XAUUSD": 50},
        "connectivity_max_age_minutes": 10,
        "volatility_calibrated": True,
        "volatility_upper_ratio": 1.5,
    }
    base.update(overrides)
    return SafetyPolicy(**base)


def _macro_policy(**overrides) -> MacroPolicy:
    base = {
        "policy_version": SCANNER_V4_MACRO_POLICY_VERSION,
        "deadband_points": 3,
        "confidence_threshold": 0.0,
    }
    base.update(overrides)
    return MacroPolicy(**base)


def _options(**overrides) -> ComposeOptions:
    base = {
        "min_risk_reward": Fraction(2, 1),
        "technical_floor": 40,
        "setup_floor": 35,
        "portfolio_position_limit": 5,
        "portfolio_exposure_limit": 2.0,
        "journal_max_consecutive_losses": 3,
        "journal_drawdown_caution_ratio": 0.5,
    }
    base.update(overrides)
    return ComposeOptions(**base)


def _side_snapshot(
    side: str,
    *,
    trend: int,
    momentum: int,
    location: int,
    evidence: int | None = 60,
    execution: int | None = 70,
    plan: bool = True,
) -> SideSnapshot:
    if side == "buy":
        plan_obj = (
            ScenarioPlan("buy", 91.0, 90.0, 94.0, source="plan") if plan else None
        )
    else:
        plan_obj = (
            ScenarioPlan("sell", 108.0, 109.0, 105.0, source="plan") if plan else None
        )
    return SideSnapshot(
        technical_raws={"trend": trend, "momentum": momentum, "location": location},
        evidence_score=evidence,
        evidence_source=("evidence_feed" if evidence is not None else ""),
        execution_quality_score=execution,
        execution_quality_source=("exec_feed" if execution is not None else ""),
        scenario_plan=plan_obj,
    )


_EXPLICIT = object()


def _snapshot(
    *,
    captured_at: datetime = CAPTURED,
    buy_side: SideSnapshot | None = None,
    sell_side: SideSnapshot | None = None,
    smc: SmcScoringResult | None = None,
    safety: MarketSafetyContext | None = None,
    macro_raw_buy: int | None = 20,
    macro_raw_sell: int | None = 14,
    macro_confidence: float | None = 0.8,
    account: AccountState | None | object = _EXPLICIT,
    portfolio: PortfolioState | None | object = _EXPLICIT,
    journal: JournalState | None | object = _EXPLICIT,
    source: str = "live",
) -> ScannerV4Snapshot:
    buy = buy_side if buy_side is not None else _side_snapshot(BUY, trend=20, momentum=14, location=18)
    sell = sell_side if sell_side is not None else _side_snapshot(
        SELL, trend=8, momentum=5, location=6, evidence=30, execution=40
    )
    builder = build_live_snapshot if source == "live" else build_backtest_snapshot
    if account is _EXPLICIT:
        account = AccountState(free_margin=10000.0, required_margin=500.0)
    if portfolio is _EXPLICIT:
        portfolio = PortfolioState(open_positions=2, exposure_ratio=0.8)
    if journal is _EXPLICIT:
        journal = JournalState(consecutive_losses=1, recent_drawdown_ratio=0.2)
    return builder(
        symbol="XAUUSD",
        captured_at=captured_at,
        regime="trending_up",
        canonical_smc=smc if smc is not None else _canonical_smc(),
        buy=buy,
        sell=sell,
        safety_context=(
            safety if safety is not None else _safety_context(captured_at=captured_at)
        ),
        macro_raw_buy=macro_raw_buy,
        macro_raw_sell=macro_raw_sell,
        macro_confidence=macro_confidence,
        account=account,
        portfolio=portfolio,
        journal=journal,
    )


def _compose(
    snapshot: ScannerV4Snapshot,
    *,
    now: datetime = NOW,
    safety: SafetyPolicy | None = None,
    macro: MacroPolicy | None = None,
    options: ComposeOptions | None = None,
) -> ScannerV4CompositionResult:
    if safety is None:
        safety = _safety_policy()
    if macro is None:
        macro = _macro_policy()
    if options is None:
        options = _options()
    return compose_scanner_v4(
        snapshot,
        now=now,
        safety_policy=safety,
        macro_policy=macro,
        options=options,
    )


def _run(source: str = "live") -> ScannerV4CompositionResult:
    return _compose(_snapshot(source=source))


def _code_text() -> str:
    text = (_CORE_DIR / "scanner_v4_composition.py").read_text(encoding="utf-8")
    # Strip every docstring so descriptive prose can never fake a marker test.
    return re.sub(r'"""(?:[^"]|"(?!""))*"""', "", text, flags=re.S)


# ---------------------------------------------------------------------------
# Contract / structure
# ---------------------------------------------------------------------------


class TestContract:
    def test_result_wraps_canonical_artifact(self):
        result = _run()
        assert type(result) is ScannerV4CompositionResult
        assert type(result.canonical) is CanonicalPairSnapshot
        assert result.snapshot_id == result.canonical.snapshot_id

    def test_versions_stamped(self):
        result = _run()
        assert result.canonical.scoring_version == SCANNER_V4_SCORING_VERSION
        assert result.canonical.snapshot_version == "scanner-pair-snapshot-v4"
        assert result.canonical.safety_policy_version == SCANNER_V4_SAFETY_POLICY_VERSION
        assert result.canonical.macro_policy_version == SCANNER_V4_MACRO_POLICY_VERSION

    def test_composition_version_constant(self):
        assert COMPOSITION_POLICY_VERSION == "scanner-composition-v4"
        result = _run()
        assert result.to_dict()["composition_version"] == COMPOSITION_POLICY_VERSION

    def test_snapshot_id_format_locked(self):
        result = _run()
        prefix = f"v4:XAUUSD:{CAPTURED.astimezone(UTC).isoformat().replace('+00:00', 'Z')}:"
        assert result.snapshot_id.startswith(prefix)
        digest = result.snapshot_id[len(prefix):]
        assert len(digest) == 12

    def test_freshness_constants_locked(self):
        assert SNAPSHOT_MAX_AGE_SECONDS == 120
        assert SNAPSHOT_MAX_FUTURE_SKEW_SECONDS == 30
        assert ComposeOptions().snapshot_max_age_seconds == SNAPSHOT_MAX_AGE_SECONDS

    def test_compose_rejects_non_snapshot(self):
        with pytest.raises(CompositionInputError):
            compose_scanner_v4(object(), now=NOW)

    def test_compose_rejects_tz_naive_now(self):
        with pytest.raises(CompositionInputError):
            compose_scanner_v4(_snapshot(), now=datetime(2026, 8, 13, 12, 0))

    def test_compose_rejects_wrong_policy_option_types(self):
        snapshot = _snapshot()
        with pytest.raises(CompositionInputError):
            compose_scanner_v4(snapshot, now=NOW, safety_policy=object())
        with pytest.raises(CompositionInputError):
            compose_scanner_v4(snapshot, now=NOW, macro_policy=object())
        with pytest.raises(CompositionInputError):
            compose_scanner_v4(snapshot, now=NOW, options=object())

    def test_compose_requires_canonical_policy_versions(self):
        # The policy classes self-validate their canonical version at
        # construction; compose additionally rejects non-policy types.
        with pytest.raises(MarketSafetyGateError):
            SafetyPolicy(policy_version="scanner-safety-policy-v9")
        with pytest.raises(MacroGateError):
            MacroPolicy(
                policy_version="scanner-macro-policy-v9",
                deadband_points=3,
                confidence_threshold=0.0,
                conflict_cap="BLOCK",
            )

    def test_bad_options_are_rejected(self):
        with pytest.raises(CompositionInputError):
            ComposeOptions(snapshot_max_age_seconds=0)
        with pytest.raises(CompositionInputError):
            ComposeOptions(snapshot_max_future_skew_seconds=-1)
        with pytest.raises(CompositionInputError):
            ComposeOptions(technical_floor=101)
        with pytest.raises(CompositionInputError):
            ComposeOptions(min_risk_reward=0)
        with pytest.raises(CompositionInputError):
            ComposeOptions(portfolio_position_limit=0)
        with pytest.raises(CompositionInputError):
            ComposeOptions(journal_drawdown_caution_ratio=1.5)

    def test_snapshot_input_contract(self):
        with pytest.raises(CompositionInputError):
            ScannerV4Snapshot(
                symbol="XAUUSD",
                captured_at=CAPTURED.replace(tzinfo=None),
                capture_source="live",
                regime="trending_up",
                canonical_smc=_canonical_smc(),
                buy=_side_snapshot(BUY, trend=20, momentum=14, location=18),
                sell=_side_snapshot(SELL, trend=8, momentum=5, location=6),
                safety=_safety_context(),
            )
        with pytest.raises(CompositionInputError):
            build_live_snapshot(
                symbol="XAUUSD",
                captured_at=CAPTURED,
                regime="not-a-regime",
                canonical_smc=_canonical_smc(),
                buy=_side_snapshot(BUY, trend=20, momentum=14, location=18),
                sell=_side_snapshot(SELL, trend=8, momentum=5, location=6),
                safety_context=_safety_context(),
            )
        with pytest.raises(CompositionInputError):
            SideSnapshot(
                technical_raws={"trend": 99, "momentum": 14, "location": 18},
            )
        with pytest.raises(CompositionInputError):
            SideSnapshot(
                technical_raws={"trend": 1, "momentum": 2, "location": 3},
                evidence_score=60,
            )
        with pytest.raises(CompositionInputError):
            SideSnapshot(
                technical_raws={"trend": 1, "momentum": 2, "location": 3},
                evidence_source="orphan-source",
            )
        with pytest.raises(CompositionInputError):
            SideSnapshot(
                technical_raws={"trend": 1, "momentum": 2, "location": 3},
                evidence_score=60.5,
                evidence_source="feed",
            )
        with pytest.raises(CompositionInputError):
            ScenarioPlan("buy", 90.0, 91.0, 95.0)
        with pytest.raises(CompositionInputError):
            ScenarioPlan("buy", 91.0, 90.0, 90.0)

    def test_compose_scanner_v4_is_the_single_api(self):
        sig = inspect.signature(compose_scanner_v4)
        assert "snapshot" in sig.parameters
        assert sig.parameters["now"].kind is inspect.Parameter.KEYWORD_ONLY
        for name in ("safety_policy", "macro_policy", "options"):
            assert sig.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_repeat_compose_is_identical(self):
        snapshot = _snapshot()
        first = _compose(snapshot).to_dict()
        second = _compose(snapshot).to_dict()
        assert first == second

    def test_snapshot_id_is_independent_of_now(self):
        snapshot = _snapshot()
        r1 = _compose(snapshot, now=CAPTURED)
        r2 = _compose(snapshot, now=CAPTURED + timedelta(seconds=100))
        assert r1.snapshot_id == r2.snapshot_id

    @staticmethod
    def _strip_runtime_artifacts(payload):
        if isinstance(payload, list):
            return [TestDeterminism._strip_runtime_artifacts(i) for i in payload]
        if isinstance(payload, dict):
            return {
                k: TestDeterminism._strip_runtime_artifacts(v)
                for k, v in payload.items()
                if not isinstance(k, str)
                or k not in {"checked_at", "assessed_at"}
            }
        return payload

    @staticmethod
    def _terminal_diffs(a, b, path: str = ""):
        if isinstance(a, dict) and isinstance(b, dict):
            for k in set(a) | set(b):
                key = f"{path}/{k}"
                if k not in a:
                    yield key, "missing-a", b[k]
                elif k not in b:
                    yield key, "missing-b", a[k]
                elif a[k] != b[k]:
                    yield from TestDeterminism._terminal_diffs(a[k], b[k], key)
        elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
            for i, (x, y) in enumerate(zip(a, b)):
                if x != y:
                    yield from TestDeterminism._terminal_diffs(x, y, f"{path}[{i}]")
        else:
            yield path, (a, b), None

    def test_canonical_payload_is_independent_of_now_while_fresh(self):
        # The ONLY time-dependent fields are the safety gate's derived candle
        # ages (they are computed from the evaluation clock) — everything else
        # in the canonical payload must be byte-identical across clocks.
        snapshot = _snapshot()
        fresh1 = _compose(snapshot, now=CAPTURED)
        fresh2 = _compose(snapshot, now=CAPTURED + timedelta(seconds=100))
        a = self._strip_runtime_artifacts(
            json.loads(fresh1.canonical.to_json())
        )
        b = self._strip_runtime_artifacts(
            json.loads(fresh2.canonical.to_json())
        )
        diffs = list(self._terminal_diffs(a, b))
        assert len(diffs) == 1, (
            f"expected exactly one time-derived diff, got {diffs}"
        )
        path, (va, vb) = diffs[0][:2]
        assert (
            path.endswith("last_candle_age_seconds")
            and abs(float(vb) - float(va) - 100.0) < 1e-9
        ), f"unexpected diff: {path}: {va} vs {vb}"

    def test_different_symbol_yields_different_id(self):
        a = _snapshot()
        b = build_live_snapshot(
            symbol="EURUSD",
            captured_at=CAPTURED,
            regime="trending_up",
            canonical_smc=_canonical_smc(),
            buy=_side_snapshot(BUY, trend=20, momentum=14, location=18),
            sell=_side_snapshot(SELL, trend=8, momentum=5, location=6),
            safety_context=_safety_context(),
        )
        assert snapshot_id_of(a) != snapshot_id_of(b)

    def test_different_captured_at_yields_different_id(self):
        a = _snapshot(captured_at=CAPTURED)
        b = _snapshot(captured_at=CAPTURED + timedelta(seconds=5))
        assert snapshot_id_of(a) != snapshot_id_of(b)
        # Both are internally fresh when evaluated at their own capture time.
        assert _compose(a, now=CAPTURED).decision.candidate_status == WAITING_CONFIRMATION
        assert _compose(b, now=CAPTURED + timedelta(seconds=5)).decision.candidate_status == WAITING_CONFIRMATION


# ---------------------------------------------------------------------------
# Whole pipeline happy path
# ---------------------------------------------------------------------------


class TestWholePipeline:
    def test_full_pass_yields_waiting_confirmation(self):
        result = _run()
        assert result.decision.candidate_status == WAITING_CONFIRMATION
        assert result.decision.selected_side == BUY
        assert result.decision.reason_codes == (GATES_ALL_PASS,)

    def test_explicit_gate_status_all_pass(self):
        result = _run()
        assert result.safety.status == PASS
        assert result.macro_gate.status == PASS
        assert [g.status for g in result.composition_gates] == [PASS, PASS, PASS, PASS]

    def test_pipeline_order_is_snapshot_first(self):
        snapshot = _snapshot()
        result = _compose(snapshot)
        assert result.captured_at == snapshot.captured_at
        assert result.capture_source == snapshot.capture_source

    def test_canonical_json_is_well_formed(self):
        result = _run()
        payload = json.loads(result.canonical.to_json())
        assert payload["decision"]["candidate_status"] == WAITING_CONFIRMATION
        assert set(payload["side_scores"]) == {"buy", "sell"}
        assert payload["market_safety"]["status"] == PASS


# ---------------------------------------------------------------------------
# Side consistency
# ---------------------------------------------------------------------------


class TestSideConsistency:
    def test_best_side_and_gap_come_from_technical_only(self):
        result = _run()
        buy = result.canonical.side_scores[0].technical_signal_score
        sell = result.canonical.side_scores[1].technical_signal_score
        assert buy == 76
        assert sell == 32
        assert result.decision.selected_side == BUY  # 76 > 32
        assert result.decision.score_gap == 44

    def test_macro_gate_assessed_side_matches_selected_side(self):
        result = _run()
        assert result.macro_gate.assessed_side == result.decision.selected_side == BUY

    def test_scenario_carries_the_selected_side(self):
        result = _run()
        assert result.scenario.side == BUY
        assert result.scenario.plan is not None
        assert result.scenario.plan.direction == BUY

    def test_scenario_never_borrows_from_other_side(self):
        # selected = buy (higher technical) but buy has NO plan while sell does.
        buy_no_plan = _side_snapshot(
            BUY, trend=20, momentum=14, location=18, plan=False
        )
        snapshot = _snapshot(buy_side=buy_no_plan)
        result = _compose(snapshot)
        assert result.decision.selected_side == BUY
        assert result.scenario.side == BUY
        assert result.scenario.plan is None
        assert result.composition_gates[0].status == UNKNOWN
        assert GATE_SCENARIO_PLAN_MISSING in result.composition_gates[0].reason_codes
        assert result.decision.candidate_status == WATCH_ZONE  # non-critical UNKNOWN

    def test_side_scores_do_not_leak_across_sides(self):
        result = _run()
        buy_score = result.canonical.side_scores[0]
        sell_score = result.canonical.side_scores[1]
        assert buy_score.evidence_score == 60
        assert sell_score.evidence_score == 30
        assert buy_score.execution_quality_score == 70
        assert sell_score.execution_quality_score == 40

    def test_sell_higher_technical_selects_sell(self):
        # sell raws mirror the strong buy profile, buy weak -> sell selected.
        strong = {"trend": 20, "momentum": 14, "location": 18}
        weak = {"trend": 8, "momentum": 5, "location": 6}
        snapshot = _snapshot(
            buy_side=_side_snapshot(
                BUY, trend=weak["trend"], momentum=weak["momentum"],
                location=weak["location"],
            ),
            sell_side=_side_snapshot(
                SELL, trend=strong["trend"], momentum=strong["momentum"],
                location=strong["location"],
            ),
            smc=_canonical_smc(buy_subtotal=7, sell_subtotal=12),
        )
        result = _compose(snapshot)
        assert result.decision.selected_side == SELL
        assert result.scenario.side == SELL
        assert result.scenario.plan.direction == SELL
        assert result.macro_gate.assessed_side == SELL

    def test_tie_breaks_deterministically_to_buy(self):
        same = {"trend": 10, "momentum": 10, "location": 10}
        snapshot = _snapshot(
            buy_side=_side_snapshot(
                BUY, trend=same["trend"], momentum=same["momentum"],
                location=same["location"],
            ),
            sell_side=_side_snapshot(
                SELL, trend=same["trend"], momentum=same["momentum"],
                location=same["location"],
            ),
            smc=_canonical_smc(buy_subtotal=6, sell_subtotal=6),
        )
        result = _compose(snapshot)
        buy = result.canonical.side_scores[0].technical_signal_score
        sell = result.canonical.side_scores[1].technical_signal_score
        assert buy == sell
        assert result.decision.score_gap == 0
        assert result.decision.selected_side == BUY

    def test_every_side_score_is_explicit_side(self):
        result = _run()
        for score in result.canonical.side_scores:
            assert score.side in (BUY, SELL)
            assert score.final_score == score.setup_score  # the alias contract


# ---------------------------------------------------------------------------
# Full-schema fail closed: stale / future / invalid technical
# ---------------------------------------------------------------------------


class TestFailClosedDataUnavailable:
    def test_stale_snapshot_drives_data_unavailable(self):
        snapshot = _snapshot(captured_at=CAPTURED - timedelta(seconds=180))
        result = _compose(snapshot)
        assert result.decision.candidate_status == DATA_UNAVAILABLE
        assert result.decision.selected_side is None
        assert SNAPSHOT_STALE in result.decision.reason_codes

    def test_exact_max_age_boundary_is_still_fresh(self):
        snapshot = _snapshot(captured_at=CAPTURED - timedelta(seconds=SNAPSHOT_MAX_AGE_SECONDS))
        result = _compose(snapshot)
        assert result.decision.candidate_status == WAITING_CONFIRMATION

    def test_future_snapshot_drives_data_unavailable(self):
        snapshot = _snapshot(captured_at=CAPTURED + timedelta(seconds=120))
        result = _compose(snapshot)
        assert result.decision.candidate_status == DATA_UNAVAILABLE
        assert SNAPSHOT_FRESHNESS_UNKNOWN in result.decision.reason_codes

    def test_stale_full_schema_keeps_honest_scores(self):
        snapshot = _snapshot(captured_at=CAPTURED - timedelta(seconds=180))
        result = _compose(snapshot)
        buy = result.canonical.side_scores[0]
        assert buy.technical_signal_score == 76  # honest score, no fabrication
        assert result.decision.score_gap == 44
        assert result.macro_gate.assessed_side is None  # matches decision side
        json.loads(result.canonical.to_json())  # schema still complete/valid

    def test_invalid_technical_context_drives_data_unavailable(self):
        # SMC contract version forged -> TechnicalScoreDataError on both sides.
        bad_smc = SmcScoringResult(
            scoring_version="smc-v9",
            contract_version=SMC_SCORING_CONTRACT_VERSION,
            sides={"buy": _smc_side("buy", subtotal=12), "sell": _smc_side("sell", subtotal=7)},
        )
        result = _compose(_snapshot(smc=bad_smc))
        assert result.decision.candidate_status == DATA_UNAVAILABLE
        assert result.decision.selected_side is None
        assert result.decision.score_gap is None
        assert TECHNICAL_DATA_UNAVAILABLE in result.decision.reason_codes
        assert result.technical[BUY] is None and result.technical[SELL] is None
        assert result.technical_errors[BUY] is not None

    def test_invalid_technical_has_no_fake_scores(self):
        bad_smc = SmcScoringResult(
            scoring_version="smc-v9",
            contract_version=SMC_SCORING_CONTRACT_VERSION,
            sides={"buy": _smc_side("buy", subtotal=12), "sell": _smc_side("sell", subtotal=7)},
        )
        result = _compose(_snapshot(smc=bad_smc))
        for score in result.canonical.side_scores:
            assert score.technical_signal_score is None
            assert score.setup_score is None
            assert score.final_score is None
            assert score.evidence_score is None
            assert score.execution_quality_score is None

    def test_direct_scorer_error_matches_pipeline_behavior(self):
        bad_smc = SmcScoringResult(
            scoring_version="smc-v9",
            contract_version=SMC_SCORING_CONTRACT_VERSION,
            sides={"buy": _smc_side("buy", subtotal=12), "sell": _smc_side("sell", subtotal=7)},
        )
        with pytest.raises(TechnicalScoreDataError):
            score_technical_signal(
                BUY, trend_raw=20, momentum_raw=14, location_raw=18,
                canonical_smc=bad_smc, regime="trending_up",
            )


# ---------------------------------------------------------------------------
# BLOCK keeps score + scenario but never emits an execution payload
# ---------------------------------------------------------------------------


class TestBlockKeepsScoreAndScenario:
    SCENARIO_GATE = 0
    ACCOUNT_GATE = 1
    PORTFOLIO_GATE = 2
    JOURNAL_GATE = 3

    def _assert_blocked_keeps_evidence(
        self, result: ScannerV4CompositionResult
    ) -> None:
        assert result.decision.candidate_status == BLOCKED
        assert result.decision.block_codes
        buy = result.canonical.side_scores[0]
        assert buy.technical_signal_score == 76
        assert buy.setup_score is not None
        assert result.scenario.side == BUY
        assert result.scenario.plan is not None
        assert result.scenario.risk_reward_ratio == Fraction(3, 1)

    def test_safety_block_keeps_scores(self):
        safety = _safety_policy(spread_threshold_by_symbol={"XAUUSD": 30})
        context = _safety_context(spread_points=40.0)
        result = _compose(_snapshot(safety=context), safety=safety)
        self._assert_blocked_keeps_evidence(result)
        assert result.safety.status == BLOCK
        assert {check.name for check in result.safety.checks} >= {"spread"}

    def test_macro_conflict_block_keeps_scores(self):
        macro = _macro_policy(conflict_cap="BLOCK")
        snapshot = _snapshot(macro_raw_buy=10, macro_raw_sell=20)
        result = _compose(snapshot, macro=macro)
        self._assert_blocked_keeps_evidence(result)
        assert result.macro_gate.status == BLOCK
        assert result.macro_assessment.status == "conflict"

    def test_account_margin_block(self):
        snapshot = _snapshot(account=AccountState(free_margin=500.0, required_margin=1000.0))
        result = _compose(snapshot)
        self._assert_blocked_keeps_evidence(result)
        assert result.composition_gates[self.ACCOUNT_GATE].status == BLOCK
        assert GATE_ACCOUNT_MARGIN_BLOCK in result.composition_gates[self.ACCOUNT_GATE].reason_codes

    def test_portfolio_limit_block(self):
        snapshot = _snapshot(portfolio=PortfolioState(open_positions=5, exposure_ratio=0.8))
        result = _compose(snapshot)
        self._assert_blocked_keeps_evidence(result)
        gate = result.composition_gates[self.PORTFOLIO_GATE]
        assert gate.status == BLOCK
        assert gate.reason_codes == (GATE_PORTFOLIO_LIMIT_BLOCK,)
        assert GATE_PORTFOLIO_LIMIT_BLOCK in result.decision.block_codes

    def test_journal_revenge_block(self):
        snapshot = _snapshot(journal=JournalState(consecutive_losses=4, recent_drawdown_ratio=0.2))
        result = _compose(snapshot)
        self._assert_blocked_keeps_evidence(result)
        gate = result.composition_gates[self.JOURNAL_GATE]
        assert gate.status == BLOCK
        assert gate.reason_codes == (GATE_JOURNAL_REVENGE_BLOCK,)

    def test_scenario_rr_block(self):
        result = _compose(_snapshot(), options=_options(min_risk_reward=4))
        self._assert_blocked_keeps_evidence(result)
        gate = result.composition_gates[self.SCENARIO_GATE]
        assert gate.status == BLOCK
        assert gate.reason_codes == (GATE_SCENARIO_RR_BLOCK,)

    def test_never_ready_now_or_order_payload(self):
        results = [
            _run(),
            _compose(_snapshot(), options=_options(min_risk_reward=4)),
            _compose(
                _snapshot(),
                safety=_safety_policy(spread_threshold_by_symbol={"XAUUSD": 30}),
            ),
        ]
        for result in results:
            assert result.decision.candidate_status not in {"READY_NOW", "OUT_OF_STRATEGY"}
            payload = result.to_dict()
            assert "orders" not in payload
            assert "order_payload" not in payload
            assert payload["decision"]["candidate_status"] != "READY_NOW"


# ---------------------------------------------------------------------------
# Score invariance when only Safety/Macro policies change
# ---------------------------------------------------------------------------


class TestScoreInvariance:
    def _score_signature(self, result: ScannerV4CompositionResult) -> tuple:
        return (
            result.canonical.side_scores[0].to_dict(),
            result.canonical.side_scores[1].to_dict(),
            result.scenario.to_dict(),
            json.dumps(result.final_scores[BUY].to_dict(), sort_keys=True),
        )

    def test_safety_block_never_mutates_scores(self):
        context = _safety_context(spread_points=45.0)
        blocked = _safety_policy(spread_threshold_by_symbol={"XAUUSD": 30})
        base = _compose(_snapshot())
        blocked_safety = _compose(_snapshot(safety=context), safety=blocked)
        assert base.decision.candidate_status == WAITING_CONFIRMATION
        assert blocked_safety.decision.candidate_status == BLOCKED
        assert self._score_signature(base) == self._score_signature(blocked_safety)

    def test_macro_block_never_mutates_scores(self):
        snapshot = _snapshot(macro_raw_buy=10, macro_raw_sell=20)
        macro = _macro_policy(conflict_cap="BLOCK")
        base = _compose(_snapshot())
        blocked_macro = _compose(snapshot, macro=macro)
        assert base.decision.candidate_status == WAITING_CONFIRMATION
        assert blocked_macro.decision.candidate_status == BLOCKED
        assert self._score_signature(base) == self._score_signature(blocked_macro)

    def test_macro_selected_side_only_evaluated_once(self):
        result = _run()
        # The macro gate evaluated exactly one side: the selected one.
        assert result.macro_gate.assessed_side == BUY
        assert result.macro_assessment.status in {"aligned", "neutral"}


# ---------------------------------------------------------------------------
# Evidence / Execution fallback (Bước 06 integration)
# ---------------------------------------------------------------------------


class TestEvidenceExecutionFallback:
    def test_missing_evidence_and_execution_use_neutral_50(self):
        buy = _side_snapshot(BUY, trend=20, momentum=14, location=18, evidence=None, execution=None)
        result = _compose(_snapshot(buy_side=buy))
        score = result.canonical.side_scores[0]
        assert score.evidence_score == 50
        assert score.execution_quality_score == 50
        assert score.evidence_source == FINAL_SCORE_NEUTRAL_FALLBACK_SOURCE
        assert score.execution_quality_source == FINAL_SCORE_NEUTRAL_FALLBACK_SOURCE

    def test_fallback_warnings_surface_on_the_side(self):
        buy = _side_snapshot(BUY, trend=20, momentum=14, location=18, evidence=None, execution=None)
        result = _compose(_snapshot(buy_side=buy))
        score = result.canonical.side_scores[0]
        assert "FINAL_SCORE_EVIDENCE_NEUTRAL_FALLBACK" in score.reason_codes
        assert "FINAL_SCORE_EXECUTION_NEUTRAL_FALLBACK" in score.reason_codes

    def test_fallback_formula_is_exact(self):
        # 0.65*76 + 0.20*50 + 0.15*50 = 49.4 + 10 + 7.5 = 66.9 -> ROUND_HALF_UP 67
        buy = _side_snapshot(BUY, trend=20, momentum=14, location=18, evidence=None, execution=None)
        result = _compose(_snapshot(buy_side=buy))
        score = result.canonical.side_scores[0]
        assert score.setup_score == 67
        assert score.final_score == 67

    def test_neutral_fallback_never_copies_technical(self):
        buy = _side_snapshot(BUY, trend=25, momentum=20, location=25, evidence=None, execution=None)
        result = _compose(_snapshot(buy_side=buy))
        score = result.canonical.side_scores[0]
        assert score.technical_signal_score == 96  # max trending_up technical
        assert score.evidence_score == 50  # exactly 50, never 96
        assert score.execution_quality_score == 50

    def test_valid_evidence_is_not_touched(self):
        result = _run()
        score = result.canonical.side_scores[0]
        assert score.evidence_score == 60
        assert score.evidence_source == "evidence_feed"
        assert score.reason_codes == ()  # no fallback warnings


# ---------------------------------------------------------------------------
# Gate statuses and minimal decision mapping
# ---------------------------------------------------------------------------


class TestDecisionMapping:
    def test_default_policies_fail_closed_to_blocked(self):
        snapshot = _snapshot()
        result = compose_scanner_v4(snapshot, now=NOW, options=_options())
        assert result.decision.candidate_status == BLOCKED
        assert result.safety.status == UNKNOWN
        assert result.macro_gate.status == UNKNOWN
        assert "MACRO_DEADBAND_UNSET" in result.decision.block_codes

    def test_account_unknown_is_critical_block(self):
        result = _compose(_snapshot(account=None))
        assert result.composition_gates[1].status == UNKNOWN
        assert GATE_ACCOUNT_DATA_MISSING in result.composition_gates[1].reason_codes
        assert result.decision.candidate_status == BLOCKED

    def test_portfolio_unknown_is_critical_block(self):
        result = _compose(_snapshot(portfolio=None))
        assert result.composition_gates[2].status == UNKNOWN
        assert result.decision.candidate_status == BLOCKED
        assert GATE_PORTFOLIO_DATA_MISSING in result.decision.block_codes

    def test_portfolio_policy_open_fails_closed(self):
        snapshot = _snapshot(portfolio=PortfolioState(open_positions=2, exposure_ratio=0.8))
        result = _compose(snapshot, options=_options(portfolio_position_limit=None, portfolio_exposure_limit=None))
        gate = result.composition_gates[2]
        assert gate.status == UNKNOWN
        assert gate.reason_codes == (GATE_PORTFOLIO_POLICY_OPEN,)
        assert result.decision.candidate_status == BLOCKED

    def test_journal_policy_open_is_watch_zone_not_block(self):
        snapshot = _snapshot(journal=JournalState(consecutive_losses=2, recent_drawdown_ratio=0.3))
        result = _compose(
            snapshot,
            options=_options(journal_max_consecutive_losses=None, journal_drawdown_caution_ratio=None),
        )
        gate = result.composition_gates[3]
        assert gate.status == UNKNOWN
        assert gate.reason_codes == (GATE_JOURNAL_POLICY_OPEN,)
        assert result.decision.candidate_status == WATCH_ZONE  # non-critical

    def test_journal_drawdown_caution_is_watch_zone(self):
        snapshot = _snapshot(journal=JournalState(consecutive_losses=1, recent_drawdown_ratio=0.8))
        result = _compose(snapshot, options=_options(journal_drawdown_caution_ratio=0.5))
        gate = result.composition_gates[3]
        assert gate.status == CAUTION
        assert gate.reason_codes == (GATE_JOURNAL_DRAWDOWN_CAUTION,)
        assert result.decision.candidate_status == WATCH_ZONE

    def test_scenario_policy_open_is_watch_zone_not_block(self):
        result = _compose(_snapshot(), options=_options(min_risk_reward=None))
        gate = result.composition_gates[0]
        assert gate.status == UNKNOWN
        assert gate.reason_codes == (GATE_SCENARIO_POLICY_OPEN,)
        assert result.decision.candidate_status == WATCH_ZONE

    def test_open_floors_cannot_certify_confirmation(self):
        result = _compose(_snapshot(), options=_options(technical_floor=None, setup_floor=None))
        assert result.decision.candidate_status == WATCH_ZONE
        assert result.decision.reason_codes == (COMPOSE_FLOOR_POLICY_OPEN,)

    def test_score_below_floor_is_watch_zone(self):
        # buy setup = 72 < setup_floor 80
        result = _compose(_snapshot(), options=_options(technical_floor=40, setup_floor=80))
        assert result.decision.candidate_status == WATCH_ZONE
        assert result.decision.reason_codes == (COMPOSE_SCORE_FLOOR_NOT_MET,)

    def test_technical_below_floor_is_watch_zone(self):
        # buy technical = 76 < technical_floor 90
        result = _compose(_snapshot(), options=_options(technical_floor=90, setup_floor=35))
        assert result.decision.candidate_status == WATCH_ZONE
        assert result.decision.reason_codes == (COMPOSE_SCORE_FLOOR_NOT_MET,)

    def test_gates_all_pass_code_only_on_full_pass(self):
        passing = _compose(_snapshot(), options=_options())
        failing = _compose(
            _snapshot(),
            options=_options(portfolio_position_limit=1),
        )
        assert passing.decision.candidate_status == WAITING_CONFIRMATION
        assert passing.decision.reason_codes == (GATES_ALL_PASS,)
        assert failing.decision.candidate_status == BLOCKED
        assert GATES_ALL_PASS not in failing.decision.reason_codes


# ---------------------------------------------------------------------------
# Live / backtest parity (same single API on the same immutable input)
# ---------------------------------------------------------------------------


class TestLiveBacktestParity:
    def _pair(self):
        live = _snapshot(source="live")
        backtest = _snapshot(source="backtest")
        r_live = _compose(live)
        r_bt = _compose(backtest)
        return live, backtest, r_live, r_bt

    def test_identical_snapshot_id(self):
        _, _, r_live, r_bt = self._pair()
        assert r_live.snapshot_id == r_bt.snapshot_id

    def test_identical_decision_and_scores(self):
        _, _, r_live, r_bt = self._pair()
        assert r_live.decision.to_dict() == r_bt.decision.to_dict()
        assert (
            r_live.canonical.side_scores[0].to_dict()
            == r_bt.canonical.side_scores[0].to_dict()
        )
        assert (
            r_live.canonical.side_scores[1].to_dict()
            == r_bt.canonical.side_scores[1].to_dict()
        )

    def test_canonical_differs_only_in_capture_source(self):
        _, _, r_live, r_bt = self._pair()
        a = r_live.canonical.to_dict()
        b = r_bt.canonical.to_dict()
        a.pop("provenance")
        b.pop("provenance")
        assert a == b
        assert r_live.canonical.provenance["capture_source"] == "live"
        assert r_bt.canonical.provenance["capture_source"] == "backtest"

    def test_capture_source_is_not_part_of_the_input_fingerprint(self):
        live = _snapshot(source="live")
        backtest = _snapshot(source="backtest")
        assert (
            live.to_canonical_input_dict()
            == backtest.to_canonical_input_dict()
        )
        assert live.capture_source != backtest.capture_source

    def test_compute_scenario_rr_is_deterministic(self):
        plan = ScenarioPlan("buy", 91.0, 90.0, 94.0)
        assert compute_scenario_rr(plan, BUY) == Fraction(3, 1)
        assert compute_scenario_rr(plan, BUY) == compute_scenario_rr(plan, BUY)
        sell = ScenarioPlan("sell", 108.0, 109.0, 105.0)
        assert compute_scenario_rr(sell, SELL) == Fraction(3, 1)
        with pytest.raises(CompositionInputError):
            compute_scenario_rr(plan, SELL)  # never borrow a plan across sides


# ---------------------------------------------------------------------------
# Reason codes + registration
# ---------------------------------------------------------------------------


class TestReasonCodes:
    @pytest.mark.parametrize(
        "code",
        [
            SNAPSHOT_STALE,
            SNAPSHOT_FRESHNESS_UNKNOWN,
            GATE_SCENARIO_PLAN_MISSING,
            GATE_SCENARIO_POLICY_OPEN,
            GATE_SCENARIO_RR_BLOCK,
            GATE_ACCOUNT_DATA_MISSING,
            GATE_ACCOUNT_MARGIN_BLOCK,
            GATE_PORTFOLIO_DATA_MISSING,
            GATE_PORTFOLIO_POLICY_OPEN,
            GATE_PORTFOLIO_LIMIT_BLOCK,
            GATE_JOURNAL_DATA_MISSING,
            GATE_JOURNAL_POLICY_OPEN,
            GATE_JOURNAL_REVENGE_BLOCK,
            GATE_JOURNAL_DRAWDOWN_CAUTION,
            COMPOSE_FLOOR_POLICY_OPEN,
            COMPOSE_SCORE_FLOOR_NOT_MET,
            GATES_ALL_PASS,
        ],
    )
    def test_composition_code_registered_with_message(self, code: str) -> None:
        assert REASON_CODE_MESSAGES[code]
        assert isinstance(REASON_CODE_MESSAGES[code], str)


# ---------------------------------------------------------------------------
# Runtime isolation and ownership
# ---------------------------------------------------------------------------


class TestIsolationAndOwnership:
    def test_module_imports_v4_modules_only(self):
        module = importlib.util.find_spec("core.scanner_v4_composition")
        assert module is not None
        text = _code_text()
        for name in (
            "analysis_pipeline",
            "signal_engine",
            "final_score_engine",
            "risk_engine",
            "decision_engine",
            "scanner",
        ):
            # \b prevents `scanner_v4_models` matching the `scanner` whitelist.
            assert not re.search(rf"\b(?:from|import)\s+{re.escape(name)}\b", text), (
                f"V3 module {name!r} imported by composition"
            )
            assert not re.search(rf"\bfrom\s+core\.{re.escape(name)}\b", text), (
                f"V3 core.{name} imported by composition"
            )

    def test_no_forbidden_pipeline_markers(self):
        text = _code_text()
        for marker in (
            "scenario_scores",
            "risk_score",
            "risk_condition",
            "macro_alignment",
            "normalize_weights",
            "_compute_adaptive_weight_adjustment",
            "pick_signal_score",
        ):
            assert marker not in text, f"V3 marker {marker!r} leaks into composition"

    def test_no_ready_now_or_order_payload_markers(self):
        # Check the operative forms: status literals, payload keys, executor
        # functions.  A bare prose mention ("no READY_NOW") is not a status.
        text = _code_text()
        assert '"READY_NOW"' not in text
        assert '"OUT_OF_STRATEGY"' not in text
        assert "order_payload" not in text
        assert "def _execute" not in text
        assert len(re.findall(r'status\s*==\s*["\']', text)) == 0

    def test_final_score_is_used_without_custom_weights(self):
        # score_final_score is called with positional evidence/execution; no
        # weights= / renormalization is possible at the call site.
        text = _code_text()
        assert "weights=" not in text
        assert "renormalize" not in text

    def test_composition_constructors_are_single_owned(self):
        # The composition module is the single owner of its result/snapshot
        # constructors.  ONE documented exception: the RuntimeOrderPolicy config
        # seam (core/scanner_v4_order_policy.py) materializes the ComposeOptions
        # the release path consumes — ComposeOptions is a policy-input DTO (like
        # SafetyPolicy/MacroPolicy, which the test does not guard), and the order
        # policy is the single owner-facing place that builds it.
        OPTIONS_OWNER = {"scanner_v4_order_policy.py"}
        origins: list[str] = []
        for py in _CORE_DIR.glob("*.py"):
            if py.name == "scanner_v4_composition.py":
                continue
            content = py.read_text(encoding="utf-8")
            for cursor in ("ScannerV4CompositionResult(", "ScannerV4Snapshot(", "ComposeOptions("):
                if cursor not in content:
                    continue
                if cursor == "ComposeOptions(" and py.name in OPTIONS_OWNER:
                    continue
                origins.append(f"{py.name}:{cursor}")
        assert not origins, f"composition constructors used outside the module: {origins}"

    def test_runtime_modules_do_not_reference_composition(self):
        for module in (
            "analysis_pipeline.py",
            "scanner.py",
            "scanner_controller.py",
            "system_backtest_engine.py",
            "trade_gate_engine.py",
            "final_score_engine.py",
            "signal_engine.py",
            "risk_engine.py",
            "decision_engine.py",
        ):
            path = _CORE_DIR / module
            if path.exists():
                assert (
                    "scanner_v4_composition" not in path.read_text(encoding="utf-8")
                ), f"{module} must stay V3 until atomic cutover"

    def test_no_dual_snapshot_id_algorithms(self):
        # The composition computes the id exactly once from the canonical input.
        text = _code_text()
        assert text.count("snapshot_id_of") >= 1
        assert "sha256" in text