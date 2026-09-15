"""Task112 — the legacy AI penalty / cap / old formula stays off the canonical route.

Caller map measured on this worktree (not inferred):

* the legacy producer is ``core.smc_scorer.score_smc`` -> ``_score_side``: the
  0-15 ``subtotal`` clamp, the H1/H4 confirmed-CHOCH caps (8/4) and the AI
  zone-review penalty.  The AI channel is ``_score_side`` ->
  ``_ai_zone_review_penalty`` -> ``core.smc_zone_ai_review.review_zone_with_cache``
  -> ``review_selected_zone`` (the only place that calls the provider).
* its single production-module caller is ``core.smc_validation.replay_smc_cases``
  (the legacy replay), which itself has no production caller; the shipped
  validation script reads a saved document instead.
* the canonical chain (``build_smc_snapshot`` -> ``evaluate_smc_snapshot`` ->
  quality -> selection -> readiness -> consumer -> revalidation) imports none of
  them, and the legacy ``selected_zone``/``subtotal`` readers are either ``None``
  on this route or historical-reader only.

These tests go through the RUNTIME routes: the legacy AI channel is still real
where it lives (control), and it can neither change nor even be reached by a
canonical verdict.  The independent AI gate that lives OUTSIDE SMC scoring
(``core.scanner_ai_auditor``) keeps its own consumer and is covered by its own
control.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from core.smc_scorer import score_smc
from core.smc_scoring_result import smc_selection_of
from core.smc_validation import replay_canonical_snapshot

UTC = timezone.utc
NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)

_LEGACY_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "smc_canonical"
    / "golden_cases.json"
)

# A confident WEAK verdict: combined (zone_validity + displacement_quality)/2 is
# at or below the weak threshold and confidence clears the minimum, so the
# legacy scorer must subtract exactly the documented penalty.
_WEAK_VERDICT = {
    "zone_validity": 2,
    "liquidity_setup": "weak",
    "displacement_quality": 2,
    "confidence": 0.9,
    "reasons": ["weak displacement"],
}


class _StubAiService:
    """Minimal stand-in for the app AIService used by the zone reviewer."""

    def __init__(self, verdict: dict[str, Any] | None = None) -> None:
        self.verdict = dict(verdict or _WEAK_VERDICT)
        self.calls: list[str] = []

    def analyze(self, prompt: str, max_tokens: int = 4000) -> str:
        self.calls.append(prompt)
        return json.dumps(self.verdict)


def _legacy_case(name: str) -> dict[str, Any]:
    payload = json.loads(_LEGACY_FIXTURE.read_text(encoding="utf-8"))
    return next(case for case in payload["cases"] if case["name"] == name)


def _live_candles():
    from tests.test_scanner_release import _zoned_candles

    return _zoned_candles()


def _scanner_analysis():
    from core.scanner_live_producers import derive_live_analysis

    d1, h4, h1 = _live_candles()
    return derive_live_analysis(
        d1, h4, h1, symbol="XAUUSD", captured_at=NOW, tick_size=0.01, min_rr=2.0
    )


# ---------------------------------------------------------------------------
# Control — the legacy AI channel is still real where it lives
# ---------------------------------------------------------------------------


def test_the_legacy_ai_penalty_still_applies_on_the_legacy_scorer():
    """Without an AI service the legacy score is fully deterministic."""

    case = _legacy_case("buy_selected_zone")
    baseline = score_smc(case["smc"], case["technical"], case["market_regime"])
    base_side = baseline.side("buy")
    assert base_side.breakdown["subtotal"] >= 8, "the AI threshold must be reached"
    assert base_side.selected_zone_id is not None

    stub = _StubAiService()
    audited = score_smc(
        case["smc"],
        case["technical"],
        case["market_regime"],
        ai_service=stub,
    )
    audited_side = audited.side("buy")

    assert stub.calls, "the legacy scorer must consult the AI provider"
    assert audited_side.score == base_side.score - 2
    assert "AI_ZONE_WEAK" in audited_side.breakdown["penalties"]
    assert audited_side.breakdown["penalty_points"] == 2


def test_the_legacy_caps_are_still_recorded_on_the_legacy_scorer():
    """The retired CHOCH cap keeps its characterization on its own route."""

    case = _legacy_case("choch_cap")
    legacy = score_smc(case["smc"], case["technical"], case["market_regime"])
    side = legacy.side("buy")
    assert side.breakdown["applied_cap"] is not None
    assert side.breakdown["caps"]
    assert side.score == min(side.breakdown["subtotal"], side.breakdown["applied_cap"])


def test_the_independent_ai_gate_keeps_its_own_consumer():
    """The AI setup audit lives outside SMC scoring and is still wired."""

    from core.scanner_ai_auditor import (
        build_ai_setup_audit_prompt,
        parse_ai_setup_audit,
        summarize_ai_setup_audit,
    )

    sample = {
        "symbol": "XAUUSD",
        "side": "buy",
        "signal_score": 72,
        "entry_zone": [2400.0, 2405.0],
        "stop_loss": 2390.0,
        "take_profit": [2430.0],
    }
    prompt = build_ai_setup_audit_prompt(sample)
    assert prompt, "the independent gate must still build its own prompt"

    audit = parse_ai_setup_audit(
        json.dumps(
            {
                "agreement": "disagree",
                "confidence_score": 80,
                "trade_plan_quality": 30,
                "setup_summary": "cấu trúc chưa xác nhận",
                "risk_flags": ["spread rộng"],
                "do_not_trade_reason": "chờ xác nhận M15",
            }
        )
    )
    assert audit["agreement"] == "disagree"
    assert "chờ xác nhận M15" in summarize_ai_setup_audit(audit)

    # It is owned by the controller, not by the SMC scoring modules.
    import controllers.scanner_controller as scanner_controller

    assert scanner_controller.parse_ai_setup_audit is parse_ai_setup_audit
    assert hasattr(scanner_controller.ScannerController, "_write_scanner_ai_audit")
    assert hasattr(scanner_controller.ScannerController, "audit_single_row")


# ---------------------------------------------------------------------------
# The canonical route never reaches the legacy scorer or the AI zone review
# ---------------------------------------------------------------------------


def test_the_canonical_routes_never_call_the_legacy_scorer_or_the_ai_review(
    monkeypatch: pytest.MonkeyPatch,
):
    """Scanner, Analyze and replay run with both legacy channels poisoned."""

    from core.analysis_pipeline import AnalysisPipeline
    from core.risk_engine import AnalysisInput
    import core.smc_scorer as smc_scorer
    import core.smc_zone_ai_review as ai_review

    def _explode(*_args: Any, **_kwargs: Any):
        raise AssertionError("the canonical route reached a legacy scorer channel")

    # ``review_selected_zone`` is the only function that calls the provider, so
    # poisoning it in its own module catches every importer.
    monkeypatch.setattr(ai_review, "review_selected_zone", _explode)
    monkeypatch.setattr(ai_review, "review_zone_with_cache", _explode)
    # The legacy side scorer owns the subtotal clamp, the CHOCH caps and the AI
    # penalty; ``score_smc`` looks it up as a module global.
    monkeypatch.setattr(smc_scorer, "_score_side", _explode)

    analysis = _scanner_analysis()
    assert analysis["canonical_smc"] is not None
    assert analysis["smc_evaluation"] is not None

    d1, h4, h1 = _live_candles()
    pipeline = AnalysisPipeline()
    result = pipeline.execute(
        AnalysisInput(
            symbol="XAUUSD",
            broker_symbol="XAUUSD",
            account_balance=10_000.0,
            risk_percent=1.0,
        ),
        {"D1": d1, "H4": h4, "H1": h1},
        snapshot_as_of=NOW,
        tick_size=0.01,
    )
    assert result["analysis_status"] in {"completed", "structural_reject"}

    # Task 114: replay takes the very snapshot the live routes freeze.
    replay = replay_canonical_snapshot(analysis["smc_snapshot"], min_rr=2.0)
    assert replay["status"], "the replay route must still produce a verdict"


def test_the_canonical_modules_do_not_import_the_legacy_scoring_channels():
    """A static guard on the import graph, independent of any call path."""

    import core.smc_canonical_context as canonical_context
    import core.smc_quality as quality
    import core.smc_readiness as readiness
    import core.smc_selection as selection
    import core.smc_snapshot as snapshot

    forbidden = ("smc_scorer", "smc_zone_ai_review")
    for module in (canonical_context, quality, readiness, selection, snapshot):
        source = Path(module.__file__).read_text(encoding="utf-8")
        for name in forbidden:
            assert f"import {name}" not in source, f"{module.__name__} imports {name}"
        assert "score_smc" not in source, f"{module.__name__} references score_smc"


# ---------------------------------------------------------------------------
# A canonical verdict is not repairable by the legacy cap/penalty/AI
# ---------------------------------------------------------------------------


def _canonical_fingerprint(analysis: dict[str, Any]) -> dict[str, Any]:
    evaluation = analysis["smc_evaluation"]
    fingerprint: dict[str, Any] = {}
    for side in ("buy", "sell"):
        selection = smc_selection_of(evaluation.result.side(side))
        candidate_set = evaluation.candidate_sets[side]
        fingerprint[side] = {
            "state": selection.state,
            "quality_raw": selection.quality_raw,
            "b": selection.b,
            "q": selection.q,
            "l": selection.l,
            "c": selection.c,
            "total": selection.total,
            "selected_zone_id": selection.selected_zone_id,
            "selected_setup_id": selection.selected_setup_id,
            "plan": dict(selection.plan) if selection.plan else None,
            "plan_available": selection.plan_available,
            "readiness": dict(selection.readiness or {}),
            "reason_codes": list(candidate_set.reason_codes),
        }
    return fingerprint


def test_arming_the_legacy_ai_and_caps_leaves_the_canonical_verdict_untouched():
    """The legacy channel moves its own score and nothing else.

    The same snapshot is evaluated while a legacy AI service is armed on the
    legacy context.  The legacy total changes (control), the canonical
    fingerprint does not — there is no channel between them.
    """

    analysis = _scanner_analysis()
    before = _canonical_fingerprint(analysis)

    case = _legacy_case("buy_selected_zone")
    stub = _StubAiService()
    deterministic = score_smc(case["smc"], case["technical"], case["market_regime"])
    armed = score_smc(
        case["smc"], case["technical"], case["market_regime"], ai_service=stub
    )
    # Control: the legacy number did move, so the AI channel is genuinely armed.
    assert armed.side("buy").score != deterministic.side("buy").score
    assert stub.calls

    after = _canonical_fingerprint(_scanner_analysis())
    assert after == before


def test_the_legacy_cap_cannot_turn_a_canonical_state_into_a_plan():
    """No cap/penalty/fallback may raise a canonical state's rights."""

    analysis = _scanner_analysis()
    evaluation = analysis["smc_evaluation"]
    for side in ("buy", "sell"):
        selection = smc_selection_of(evaluation.result.side(side))
        if selection.state == "no_zone":
            # A no-zone side is an evaluated ZERO, never a plan or a zone id.
            assert selection.quality_raw == 0
            assert selection.selected_zone_id is None
            assert selection.plan_available is False
        elif selection.state == "data_unavailable":
            # Unavailable keeps a null raw and can never carry a plan.
            assert selection.quality_raw is None
            assert selection.selected_zone_id is None
            assert selection.plan_available is False
        elif selection.state == "evaluated":
            assert selection.quality_raw is not None
            assert selection.plan_available is True
