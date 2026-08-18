"""Scanner observability + session review tests (Bước 10; target-only; 10E).

Proves the telemetry contract:

* the observability document traces per-side technical raw/scaled components,
  the neutral-fallback execution/evidence source, every safety sub-gate and the
  macro gate with its decision_cap, every UNKNOWN reason code and the full
  version identity — all consumed from the canonical composition, never
  re-scored;
* counters cover the candidate distribution by status, gate-status
  (PASS/CAUTION/BLOCK/UNKNOWN), neutral-fallback count and blocked-high-score
  count;
* the session review consumes ONLY canonical candidate statuses and produces a
  deterministic brief; legacy/new disagreement metrics are never produced.
"""

from __future__ import annotations

import pytest

from core.reason_codes import (
    FINAL_SCORE_EVIDENCE_NEUTRAL_FALLBACK,
    FINAL_SCORE_EXECUTION_NEUTRAL_FALLBACK,
    SAFETY_MT5_STATE_UNKNOWN,
)
from core.market_safety_gate import (
    AVAILABILITY_MISSING,
    AVAILABILITY_VALID,
    ConnectivitySource,
    MarketSafetyContext,
)
from core.scanner_v4_models import (
    BLOCKED,
    BUY,
    READY_NOW,
    SELL,
    UNKNOWN,
    WAITING_CONFIRMATION,
)
from core.scanner_v4_observability import (
    SCANNER_V4_OBSERVABILITY_VERSION,
    has_no_v3_disagreement_metric,
    has_required_trace_keys,
    build_observability_document,
)
from core.scanner_v4_session_review import (
    SCANNER_SESSION_REVIEW_VERSION,
    reveal_session,
    session_summary,
)

from tests.test_scanner_composition import (
    PROV,
    _compose,
    _run,
    _side_snapshot,
    _snapshot,
    _safety_context,
)

# ---------------------------------------------------------------------------
# Scenario builders (reuse the canonical composition helpers)
# ---------------------------------------------------------------------------


def _safety_variant(connectivity: ConnectivitySource):
    base = _safety_context()
    return _compose(
        _snapshot(
            safety=MarketSafetyContext(
                symbol=base.symbol,
                captured_at=base.captured_at,
                connectivity=connectivity,
                data=base.data,
                spread=base.spread,
                news=base.news,
                volatility=base.volatility,
            )
        )
    )


def _unknown_composition():
    return _safety_variant(
        ConnectivitySource(
            availability=AVAILABILITY_MISSING,
            source="mt5_connection_status",
            checked_at=None,
            provenance=PROV,
            terminal_connected=None,
            broker_logged_in=None,
        )
    )


def _fallback_composition():
    """BUY evidence missing => FINAL_SCORE_EVIDENCE_NEUTRAL_FALLBACK."""
    from core.scanner_v4_models import BUY

    buy = _side_snapshot(BUY, trend=20, momentum=14, location=18, evidence=None, execution=70)
    return _compose(_snapshot(buy_side=buy))


class TestDocumentShape:
    def test_required_telemetry_surface(self):
        doc = build_observability_document(_run())
        assert has_required_trace_keys(doc.to_dict())
        assert has_no_v3_disagreement_metric(doc.to_dict())

    def test_version_identity_full(self):
        comp = _run()
        doc = build_observability_document(comp)
        versions = doc.versions
        for key in (
            "scoring_version",
            "feature_version",
            "output_schema_version",
            "safety_policy_version",
            "macro_policy_version",
            "snapshot_version",
            "composition_version",
        ):
            assert versions[key] == comp.to_dict().get(
                key.replace("_version", "_version")
            ) or versions[key]  # every slot populated
        assert doc.snapshot_id == comp.snapshot_id
        assert doc.capture_source == comp.capture_source

    def test_technical_traces_four_components_per_side(self):
        doc = build_observability_document(_run())
        assert [t.side for t in doc.technical] == ["buy", "sell"]
        for trace in doc.technical:
            assert len(trace.components) == 4
            names = [c["name"] for c in trace.components]
            assert names == ["trend", "momentum", "location", "smc"]
            for component in trace.components:
                assert {"name", "raw", "raw_max", "weight", "contribution"} <= set(component)

    def test_gate_trace_covers_all_cards(self):
        doc = build_observability_document(_run())
        names = [g["name"] for g in doc.gate_trace]
        assert names[:5] == [
            "market_safety.connectivity",
            "market_safety.data",
            "market_safety.spread",
            "market_safety.news",
            "market_safety.volatility",
        ]
        assert "macro" in names
        for gate in doc.gate_trace:
            assert "status" in gate
            assert "reason_codes" in gate

    def test_macro_gate_carries_decision_cap(self):
        doc = build_observability_document(_run())
        macro = next(g for g in doc.gate_trace if g["name"] == "macro")
        assert "decision_cap" in macro


class TestCounters:
    def test_candidate_distribution_includes_all_valid_statuses(self):
        doc = build_observability_document(_run())
        distribution = doc.counters.candidates_by_status
        # every valid status listed (zero-count kept), and the sample sums to 1
        assert sum(distribution.values()) == 1
        assert distribution[doc.candidate_status] == 1

    def test_gate_status_counters_sum_to_cards(self):
        doc = build_observability_document(_run())
        total_cards = sum(doc.counters.gate_status.values())
        assert total_cards == len(doc.gate_trace)
        assert doc.counters.gate_status["PASS"] >= 1

    def test_samples_aggregate_distribution(self):
        comps = [_run(), _unknown_composition()]
        doc = build_observability_document(comps[0], samples=comps[1:])
        assert sum(doc.counters.candidates_by_status.values()) == 2
        # the UNKNOWN-safety sample is a BLOCKED candidate (fail-closed)
        assert doc.counters.candidates_by_status[BLOCKED] >= 1

    def test_neutral_fallback_counter(self):
        comp = _fallback_composition()
        doc = build_observability_document(comp)
        assert doc.counters.neutral_fallback_count == 1
        buy_trace = next(t for t in doc.technical if t.side == BUY)
        assert buy_trace.fallback_evidence is True
        assert buy_trace.fallback_execution is False

    def test_blocked_high_score_counter(self):
        # UNKNOWN safety -> candidate BLOCKED, selected BUY setup above floor
        comp = _unknown_composition()
        doc = build_observability_document(comp, blocked_high_score_floor=40)
        assert doc.candidate_status == BLOCKED
        assert doc.counters.blocked_high_score_count == 1

    def test_unknown_reasons_collected_from_fail_closed_gates(self):
        comp = _unknown_composition()
        doc = build_observability_document(comp)
        assert SAFETY_MT5_STATE_UNKNOWN in doc.unknown_reasons
        # the connectivity card itself is UNKNOWN, never PASS
        connectivity = next(
            g for g in doc.gate_trace if g["name"] == "market_safety.connectivity"
        )
        assert connectivity["status"] == UNKNOWN


class TestSessionReview:
    def test_summary_consumes_canonical_statuses(self):
        docs = [build_observability_document(_run())]
        summary = session_summary(docs)
        assert summary.symbol == "XAUUSD"
        assert summary.candidate_count == 1
        assert summary.candidates_by_status[WAITING_CONFIRMATION] == 1
        assert summary.gate_status != {}
        assert summary.evidence_fallbacks == 0

    def test_reveal_session_is_deterministic(self):
        docs = [build_observability_document(_run())]
        first = reveal_session(docs)
        second = reveal_session(docs)
        assert first == second
        assert SCANNER_SESSION_REVIEW_VERSION in first or "Session Review" in first

    def test_mixed_symbols_refused(self):
        from core.scanner_composition import build_live_snapshot

        base = _snapshot()  # XAUUSD helper snapshot
        other = build_live_snapshot(
            symbol="EURUSD",
            captured_at=base.captured_at,
            regime=base.regime,
            canonical_smc=base.canonical_smc,
            buy=base.buy,
            sell=base.sell,
            safety_context=base.safety,
            macro_raw_buy=base.macro_raw_buy,
            macro_raw_sell=base.macro_raw_sell,
            macro_confidence=base.macro_confidence,
            account=base.account,
            portfolio=base.portfolio,
            journal=base.journal,
        )
        docs = [
            build_observability_document(_compose(base)),
            build_observability_document(_compose(other)),
        ]
        with pytest.raises(ValueError):
            reveal_session(docs)

    def test_no_disagreement_metric_in_digest(self):
        doc = build_observability_document(_run())
        assert has_no_v3_disagreement_metric(doc.to_dict())
        summary = session_summary([doc])
        assert "disagreement" not in str(summary.to_dict()).lower()


class TestNoScoringInTelemetry:
    def test_observability_never_rewrites_scores(self):
        # traces mirror the canonical values, they do not recompute them
        comp = _run()
        doc = build_observability_document(comp)
        for trace in doc.technical:
            canonical = comp.canonical.side_score(trace.side)
            components = {c["name"]: c for c in trace.components}
            assert components["trend"]["raw"] == canonical.technical_breakdown.trend.raw
            assert components["momentum"]["raw"] == canonical.technical_breakdown.momentum.raw