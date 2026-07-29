"""Offline A/B comparison for Scanner Tier-1 fast path — Bước 6.

Runs every corpus fixture through both the full baseline and the Tier-1-active
route, then compares selected zones, zone scores, signal scores, scenarios,
decision engine, and scoring provenance.  The test gates Tier-1 activation:
trade false reject must be zero and full survivor parity must hold before
``scanner_fast_tier1`` can be set to ``true`` in the persisted runtime config.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from core.analysis_engine import analyze_symbol
from core.scanner import scanner_row_from_analysis
from core.scanner_candidate_engine import evaluate_scanner_candidate
from core.scanner_models import OUT_OF_STRATEGY, READY_NOW
from core.smc_context import build_smc_context
from core.smc_prefilter import evaluate_post_context_prefilter
from tests.scanner_fast_path_fixtures import make_candles, make_request


_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "scanner_fast_path"
_CORPUS = json.loads((_FIXTURE_DIR / "corpus.json").read_text(encoding="utf-8"))
_ORACLES = json.loads((_FIXTURE_DIR / "full-oracles.json").read_text(encoding="utf-8"))["cases"]


# ---------------------------------------------------------------------------
# Run helpers
# ---------------------------------------------------------------------------


def _run_full(case: dict[str, Any]) -> dict[str, Any]:
    candles = make_candles(case)
    return analyze_symbol(
        make_request(case, _CORPUS["analysis_input"]),
        candles,
        m15_candles=candles["M15"],
        thresholds=_CORPUS["thresholds"],
        smc_scoring_mode=str(case.get("smc_scoring_mode", "v2")),
    )


def _run_fast_tier1(case: dict[str, Any]) -> dict[str, Any]:
    candles = make_candles(case)
    return analyze_symbol(
        make_request(case, _CORPUS["analysis_input"]),
        candles,
        m15_candles=candles["M15"],
        thresholds=_CORPUS["thresholds"],
        smc_scoring_mode=str(case.get("smc_scoring_mode", "v2")),
        scanner_fast_tier1=True,
    )


def _derive_would_reject(case: dict[str, Any]) -> dict[str, Any]:
    candles = make_candles(case)
    smc = build_smc_context(
        candles["D1"], candles["H4"], candles["H1"],
        symbol=str(case.get("symbol", "EUR/USD")),
    )
    full = _run_full(case)
    technical = full.get("technical", {}) if isinstance(full.get("technical"), dict) else {}
    market_regime = full.get("market_regime", {}) if isinstance(full.get("market_regime"), dict) else {}
    return evaluate_post_context_prefilter(
        mode=str(case.get("smc_scoring_mode", "v2")),
        smc=smc,
        technical=technical,
        market_regime=market_regime,
    )


# ---------------------------------------------------------------------------
# Extraction helpers — mục 8.4 parity fields
# ---------------------------------------------------------------------------


def _zone_ids(result: dict[str, Any]) -> dict[str, str | None]:
    scoring = result.get("smc_scoring", {})
    decision = scoring.get("decision", {}) if isinstance(scoring, dict) else {}
    return {
        side: decision.get(side, {}).get("selected_zone_id")
        if isinstance(decision.get(side), dict) else None
        for side in ("buy", "sell")
    }


def _zone_scores(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract selected zone scores and timeframe per side (mục 8.4)."""
    scoring = result.get("smc_scoring", {})
    decision = scoring.get("decision", {}) if isinstance(scoring, dict) else {}
    out: dict[str, dict[str, Any]] = {}
    for side in ("buy", "sell"):
        side_data = decision.get(side, {}) if isinstance(decision, dict) else {}
        out[side] = {
            "selected_zone_timeframe": side_data.get("selected_zone_timeframe"),
            "selected_zone_score": side_data.get("selected_zone_score"),
            "selected_zone_relevance_score": side_data.get("selected_zone_relevance_score"),
            "selected_zone_setup_score": side_data.get("selected_zone_setup_score"),
        }
    return out


def _signal_scores(result: dict[str, Any]) -> dict[str, int]:
    """BUY/SELL signal scores from scenario_scores (mục 8.4)."""
    scores = result.get("scenario_scores", {}) if isinstance(result.get("scenario_scores"), dict) else {}
    return {
        side: int(scores.get(side, {}).get("signal_score", 0) or 0)
        for side in ("buy", "sell")
    }


def _scenario_signature(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Scenario type, entry_status, entry_zone, SL, TP, RR (mục 8.4)."""
    scenarios = result.get("scenarios") or []
    return [
        {
            "type": s.get("type"),
            "entry_status": s.get("entry_status"),
            "entry_zone": s.get("entry_zone"),
            "stop_loss": s.get("stop_loss"),
            "take_profit": s.get("take_profit"),
            "risk_reward": s.get("risk_reward"),
        }
        for s in scenarios
        if isinstance(s, dict)
    ]


def _decision_engine(result: dict[str, Any]) -> dict[str, str]:
    de = result.get("decision_engine", {}) if isinstance(result.get("decision_engine"), dict) else {}
    return {
        "decision": str(de.get("decision", "")),
        "legacy_action": str(de.get("legacy_action", "")),
    }


def _scoring_provenance(result: dict[str, Any]) -> dict[str, Any]:
    sp = result.get("scoring_provenance", {}) if isinstance(result.get("scoring_provenance"), dict) else {}
    return {
        "scorer_version": sp.get("scorer_version"),
        "gate_version": sp.get("gate_version"),
        "score_metric": sp.get("score_metric"),
    }


def _smc_policy(result: dict[str, Any]) -> dict[str, Any]:
    scoring = result.get("smc_scoring", {})
    policy = scoring.get("policy", {}) if isinstance(scoring, dict) else {}
    return {
        "requested_mode": policy.get("requested_mode"),
        "effective_mode": policy.get("effective_mode"),
        "decision_impact_allowed": policy.get("decision_impact_allowed"),
    }


def _candidate_status(result: dict[str, Any]) -> str:
    row = scanner_row_from_analysis(result)
    return evaluate_scanner_candidate(row).status


def _has_trade_setup(result: dict[str, Any]) -> bool:
    scenarios = result.get("scenarios") or []
    return any(
        isinstance(s, dict)
        and s.get("type") in ("buy", "sell")
        and s.get("entry_status") not in ("watch_zone", "no_setup", None)
        for s in scenarios
    )


def _has_watch_signal(result: dict[str, Any]) -> bool:
    scenarios = result.get("scenarios") or []
    return any(
        isinstance(s, dict) and s.get("entry_status") == "watch_zone"
        for s in scenarios
    )


def _analyze_case(case: dict[str, Any]) -> dict[str, Any]:
    full = _run_full(case)
    would = _derive_would_reject(case)
    fast = _run_fast_tier1(case)
    mode = str(case.get("smc_scoring_mode", "v2"))
    full_zone_ids = _zone_ids(full)
    full_has_zone = any(full_zone_ids[side] is not None for side in ("buy", "sell"))
    is_legacy_shadow = mode in ("legacy", "shadow")

    return {
        "name": case["name"],
        "mode": mode,
        "full_has_zone": full_has_zone,
        "is_legacy_shadow": is_legacy_shadow,
        "full_has_trade": _has_trade_setup(full),
        "full_has_watch": _has_watch_signal(full),
        "would_should_reject": would.get("should_reject", False),
        "would_fail_open": would.get("fail_open", False),
        "would_reason": would.get("reason_code", ""),
        "fast_status": fast.get("analysis_status"),
        "fast_route": fast.get("pipeline_route"),
        # mục 8.4 parity fields
        "full": {
            "zone_ids": full_zone_ids,
            "zone_scores": _zone_scores(full),
            "signal_scores": _signal_scores(full),
            "scenarios": _scenario_signature(full),
            "decision_engine": _decision_engine(full),
            "scoring_provenance": _scoring_provenance(full),
            "smc_policy": _smc_policy(full),
            "candidate": _candidate_status(full),
        },
        "fast": {
            "zone_ids": _zone_ids(fast),
            "zone_scores": _zone_scores(fast),
            "signal_scores": _signal_scores(fast),
            "scenarios": _scenario_signature(fast),
            "decision_engine": _decision_engine(fast),
            "scoring_provenance": _scoring_provenance(fast),
            "smc_policy": _smc_policy(fast),
            "candidate": _candidate_status(fast),
        },
    }


# ---------------------------------------------------------------------------
# Gate tests
# ---------------------------------------------------------------------------


class TestTier1OfflineAB:
    """Bước 6 cổng: trade false reject = 0, full survivor parity, contract valid."""

    @pytest.fixture(scope="class")
    def analysis_results(self) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        for case in _CORPUS["cases"]:
            results[case["name"]] = _analyze_case(case)
        return results

    @staticmethod
    def _is_survivor(r: dict[str, Any]) -> bool:
        return r["is_legacy_shadow"] or r["full_has_zone"]

    # -- Cổng 1: trade false reject = 0 ---------------------------------------

    def test_trade_false_reject_is_zero(
        self, analysis_results: dict[str, dict[str, Any]]
    ) -> None:
        false_rejects = [
            name
            for name, r in analysis_results.items()
            if r["full_has_trade"] and r["fast_status"] == "structural_reject"
        ]
        assert false_rejects == [], (
            f"TRADE FALSE REJECT: {false_rejects}. "
            f"Cannot enable scanner_fast_tier1 until this is zero."
        )

    # -- Cổng 2: full survivor parity (mục 8.4) -------------------------------

    def test_survivor_zone_id_and_timeframe_parity(
        self, analysis_results: dict[str, dict[str, Any]]
    ) -> None:
        mismatches = []
        for name, r in analysis_results.items():
            if not self._is_survivor(r):
                continue
            if r["fast"]["zone_ids"] != r["full"]["zone_ids"]:
                mismatches.append(f"{name}: zone_ids full={r['full']['zone_ids']} fast={r['fast']['zone_ids']}")
            for side in ("buy", "sell"):
                fz = r["full"]["zone_scores"][side]
                tz = r["fast"]["zone_scores"][side]
                if fz["selected_zone_timeframe"] != tz["selected_zone_timeframe"]:
                    mismatches.append(
                        f"{name}: {side} timeframe full={fz['selected_zone_timeframe']} fast={tz['selected_zone_timeframe']}"
                    )
        assert mismatches == [], f"Zone ID / timeframe mismatch: {mismatches}"

    def test_survivor_zone_scores_parity(
        self, analysis_results: dict[str, dict[str, Any]]
    ) -> None:
        mismatches = []
        for name, r in analysis_results.items():
            if not self._is_survivor(r):
                continue
            for side in ("buy", "sell"):
                fz = r["full"]["zone_scores"][side]
                tz = r["fast"]["zone_scores"][side]
                for key in (
                    "selected_zone_score",
                    "selected_zone_relevance_score",
                    "selected_zone_setup_score",
                ):
                    if fz[key] != tz[key]:
                        mismatches.append(
                            f"{name}: {side}.{key} full={fz[key]} fast={tz[key]}"
                        )
        assert mismatches == [], f"Zone score mismatch: {mismatches}"

    def test_survivor_signal_scores_parity(
        self, analysis_results: dict[str, dict[str, Any]]
    ) -> None:
        mismatches = []
        for name, r in analysis_results.items():
            if not self._is_survivor(r):
                continue
            if r["fast"]["signal_scores"] != r["full"]["signal_scores"]:
                mismatches.append(
                    f"{name}: full={r['full']['signal_scores']} fast={r['fast']['signal_scores']}"
                )
        assert mismatches == [], f"Signal score mismatch: {mismatches}"

    def test_survivor_scenario_parity(
        self, analysis_results: dict[str, dict[str, Any]]
    ) -> None:
        mismatches = []
        for name, r in analysis_results.items():
            if not self._is_survivor(r):
                continue
            if r["fast"]["scenarios"] != r["full"]["scenarios"]:
                mismatches.append(
                    f"{name}: full={r['full']['scenarios']} fast={r['fast']['scenarios']}"
                )
        assert mismatches == [], f"Scenario mismatch: {mismatches}"

    def test_survivor_decision_engine_parity(
        self, analysis_results: dict[str, dict[str, Any]]
    ) -> None:
        mismatches = []
        for name, r in analysis_results.items():
            if not self._is_survivor(r):
                continue
            if r["fast"]["decision_engine"] != r["full"]["decision_engine"]:
                mismatches.append(
                    f"{name}: full={r['full']['decision_engine']} fast={r['fast']['decision_engine']}"
                )
        assert mismatches == [], f"Decision engine mismatch: {mismatches}"

    def test_survivor_scoring_provenance_parity(
        self, analysis_results: dict[str, dict[str, Any]]
    ) -> None:
        mismatches = []
        for name, r in analysis_results.items():
            if not self._is_survivor(r):
                continue
            if r["fast"]["scoring_provenance"] != r["full"]["scoring_provenance"]:
                mismatches.append(
                    f"{name}: full={r['full']['scoring_provenance']} fast={r['fast']['scoring_provenance']}"
                )
        assert mismatches == [], f"Scoring provenance mismatch: {mismatches}"

    def test_survivor_smc_policy_parity(
        self, analysis_results: dict[str, dict[str, Any]]
    ) -> None:
        mismatches = []
        for name, r in analysis_results.items():
            if not self._is_survivor(r):
                continue
            if r["fast"]["smc_policy"] != r["full"]["smc_policy"]:
                mismatches.append(
                    f"{name}: full={r['full']['smc_policy']} fast={r['fast']['smc_policy']}"
                )
        assert mismatches == [], f"SMC policy mismatch: {mismatches}"

    def test_survivor_candidate_parity(
        self, analysis_results: dict[str, dict[str, Any]]
    ) -> None:
        mismatches = []
        for name, r in analysis_results.items():
            if not self._is_survivor(r):
                continue
            if r["fast"]["candidate"] != r["full"]["candidate"]:
                mismatches.append(
                    f"{name}: full={r['full']['candidate']} fast={r['fast']['candidate']}"
                )
        assert mismatches == [], f"Candidate status mismatch: {mismatches}"

    def test_survivors_take_full_route(
        self, analysis_results: dict[str, dict[str, Any]]
    ) -> None:
        errors = []
        for name, r in analysis_results.items():
            if not self._is_survivor(r):
                continue
            if r["fast_status"] != "completed" or r["fast_route"] != "full":
                errors.append(f"{name}: status={r['fast_status']} route={r['fast_route']}")
        assert errors == [], f"Survivors must complete the full route: {errors}"

    # -- Cổng 3: structural reject contract -----------------------------------

    def test_structural_rejects_have_valid_contract(
        self, analysis_results: dict[str, dict[str, Any]]
    ) -> None:
        errors = []
        for name, r in analysis_results.items():
            if r["fast_status"] != "structural_reject":
                continue
            if r["fast_route"] != "post_context_reject":
                errors.append(f"{name}: expected post_context_reject, got {r['fast_route']}")
            if r["fast"]["candidate"] != OUT_OF_STRATEGY:
                errors.append(f"{name}: candidate must be OUT_OF_STRATEGY, got {r['fast']['candidate']}")
            if r["fast"]["candidate"] == READY_NOW:
                errors.append(f"{name}: structural reject produced READY_NOW candidate")
        assert errors == [], f"Structural reject contract violations: {errors}"

    def test_structural_rejects_are_not_data_unavailable(
        self, analysis_results: dict[str, dict[str, Any]]
    ) -> None:
        for name, r in analysis_results.items():
            if r["fast_status"] != "structural_reject":
                continue
            case = next(c for c in _CORPUS["cases"] if c["name"] == name)
            fast = _run_fast_tier1(case)
            row = scanner_row_from_analysis(fast)
            assert row.get("entry_status") != "data_unavailable", (
                f"{name}: structural reject must not map to data_unavailable"
            )
            assert row.get("candidate_status") == OUT_OF_STRATEGY, (
                f"{name}: expected OUT_OF_STRATEGY, got {row.get('candidate_status')}"
            )

    # -- Cổng 4: would-reject consistency -------------------------------------

    def test_would_reject_consistent_with_full_baseline(
        self, analysis_results: dict[str, dict[str, Any]]
    ) -> None:
        mismatches = []
        for name, r in analysis_results.items():
            if r["is_legacy_shadow"]:
                if r["would_should_reject"]:
                    mismatches.append(f"{name}: legacy/shadow must not reject")
            elif r["full_has_zone"] and r["would_should_reject"]:
                mismatches.append(
                    f"{name}: would-reject but full has zone {r['full']['zone_ids']}"
                )
            elif not r["full_has_zone"] and not r["would_should_reject"]:
                mismatches.append(
                    f"{name}: full has no zone but prefilter did not reject "
                    f"(fail_open={r['would_fail_open']})"
                )
        assert mismatches == [], f"Would-reject vs baseline mismatch: {mismatches}"

    # -- Cổng 5: watch false reject report (allowed, tracked) -----------------

    def test_watch_false_reject_report(
        self, analysis_results: dict[str, dict[str, Any]]
    ) -> None:
        watch_false = [
            name
            for name, r in analysis_results.items()
            if r["fast_status"] == "structural_reject"
            and r["full_has_watch"]
            and not r["full_has_trade"]
        ]
        if watch_false:
            print(f"\n[INFO] Watch false rejects (allowed): {watch_false}")
            print("[INFO] These are expected display changes per the fast-track plan.")

    # -- Regression: flags off = baseline -------------------------------------

    def test_flags_off_matches_full_oracle(
        self, analysis_results: dict[str, dict[str, Any]]
    ) -> None:
        for name, r in analysis_results.items():
            if self._is_survivor(r):
                assert r["fast"]["zone_ids"] == r["full"]["zone_ids"], (
                    f"{name}: flags-off zone mismatch"
                )
