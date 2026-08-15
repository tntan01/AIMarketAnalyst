"""Scanner V4 candidate ledger (Bước 09, target-only).

Mục 9C: ledger dùng side-owned ``technical_signal_score``/``setup_score``, lưu
breakdown/gate reason/identity, và không đọc bất kỳ field V3 nào
(``scenario_scores``/``signal_score``/``final_score``/``opportunity_score``).
"""

from __future__ import annotations

from datetime import datetime, timezone
from fractions import Fraction

import pytest

from core.scanner_v4_backtest_contract import SCANNER_V4_CANDIDATE_LEDGER_VERSION
from core.scanner_v4_candidate import ScannerV4CandidateDecision
from core.scanner_v4_candidate_ledger import (
    LedgerSideScore,
    ScannerV4LedgerRow,
    build_scanner_v4_ledger_row,
)
from core.scanner_v4_composition import ScannerV4CompositionResult
from core.scanner_v4_strategy_router import ROUTE_ROUTED, route_scanner_v4
from core.scanner_v4_threshold_policy import make_default_threshold_policy
from tests.test_scanner_v4_composition import _run, _snapshot, _compose

NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=timezone.utc)


def _composition_and_candidate() -> tuple[ScannerV4CompositionResult, ScannerV4CandidateDecision]:
    composition = _compose(_snapshot(source="backtest"))
    out = route_scanner_v4(
        composition.to_dict(),
        thresholds=make_default_threshold_policy(),
        entry_confirmation="confirmed",
    )
    assert out.route_status == ROUTE_ROUTED
    assert out.candidate is not None
    return composition, out.candidate


class TestLedgerRowBuild:
    def test_row_is_side_owned_and_versioned(self):
        composition, candidate = _composition_and_candidate()
        row = build_scanner_v4_ledger_row(composition, candidate)
        assert isinstance(row, ScannerV4LedgerRow)
        assert row.candidate_ledger_version == SCANNER_V4_CANDIDATE_LEDGER_VERSION
        assert row.candidate_id == f"v4:{candidate.snapshot_id}"
        assert row.selected_side == candidate.selected_side
        assert row.selected_setup_score == candidate.setup_score
        assert row.selected_technical_signal_score == candidate.technical_signal_score

    def test_row_keeps_gate_reason_and_identity(self):
        composition, candidate = _composition_and_candidate()
        row = build_scanner_v4_ledger_row(composition, candidate)
        assert row.safety_policy_version == candidate.safety_policy_version
        assert row.macro_policy_version == candidate.macro_policy_version
        assert row.threshold_policy_version == candidate.threshold_policy_version
        assert row.gate_codes == candidate.gate_codes
        assert row.reason_codes == candidate.reason_codes
        assert row.composition_version == "scanner-composition-v4"

    def test_row_sides_are_side_score_copies(self):
        composition, candidate = _composition_and_candidate()
        row = build_scanner_v4_ledger_row(composition, candidate)
        assert {s.side for s in row.side_scores} == {"buy", "sell"}
        for ledger_score in row.side_scores:
            canonical = next(
                s for s in composition.canonical.side_scores if s.side == ledger_score.side
            )
            assert ledger_score.setup_score == canonical.setup_score
            assert ledger_score.technical_signal_score == canonical.technical_signal_score

    def test_ledger_score_from_side_score(self):
        composition, _ = _composition_and_candidate()
        canonical = composition.canonical.side_scores[0]
        ledger = LedgerSideScore.from_side_score(canonical)
        assert ledger.side == canonical.side
        assert ledger.technical_signal_score == canonical.technical_signal_score
        assert ledger.setup_score == canonical.setup_score
        assert ledger.reason_codes == canonical.reason_codes

    def test_ledger_score_rejects_non_side_score(self):
        with pytest.raises(TypeError):
            LedgerSideScore.from_side_score(object())  # type: ignore[arg-type]

    def test_mismatched_artifacts_refused(self):
        from dataclasses import replace

        composition, _ = _composition_and_candidate()
        other_snapshot = replace(_snapshot(source="backtest"), symbol="EURUSD")
        other = _compose(other_snapshot)
        other_out = route_scanner_v4(
            other.to_dict(),
            thresholds=make_default_threshold_policy(),
            entry_confirmation="confirmed",
        )
        assert other_out.candidate is not None
        with pytest.raises(ValueError):
            build_scanner_v4_ledger_row(composition, other_out.candidate)

    def test_type_checks(self):
        composition, candidate = _composition_and_candidate()
        with pytest.raises(TypeError):
            build_scanner_v4_ledger_row(object(), candidate)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            build_scanner_v4_ledger_row(composition, object())  # type: ignore[arg-type]

    def test_row_to_dict_has_no_legacy_fields(self):
        composition, candidate = _composition_and_candidate()
        payload = build_scanner_v4_ledger_row(composition, candidate).to_dict()
        for forbidden in ("final_score", "scenario_scores", "signal_score",
                          "opportunity_score", "scanner_action", "total",
                          "best_score"):
            assert forbidden not in payload, forbidden


class TestLedgerToDict:
    def test_round_trip_identity(self):
        _, candidate = _composition_and_candidate()
        composition = _compose(_snapshot(source="backtest"))
        row = build_scanner_v4_ledger_row(composition, candidate)
        payload = row.to_dict()
        assert payload["candidate_ledger_version"] == SCANNER_V4_CANDIDATE_LEDGER_VERSION
        assert payload["selected_side"] == candidate.selected_side
        assert len(payload["side_scores"]) == 2

    def test_fraction_rr_serialised_as_string(self):
        composition, candidate = _composition_and_candidate()
        row = build_scanner_v4_ledger_row(composition, candidate)
        if row.risk_reward_ratio is not None:
            assert isinstance(row.to_dict()["risk_reward_ratio"], str)
            assert Fraction(row.to_dict()["risk_reward_ratio"]) == row.risk_reward_ratio


class TestLedgerStandalone:
    def test_scanner_v4_backtest_composition_yields_ledger_row(self):
        # A full pipeline row from the canonical Bước 07 fixture (routed) is
        # byte-deterministic; re-running on the same immutable input yields
        # the same ledger row.
        composition, candidate = _composition_and_candidate()
        row_a = build_scanner_v4_ledger_row(composition, candidate)
        composition_b, candidate_b = _composition_and_candidate()
        row_b = build_scanner_v4_ledger_row(composition_b, candidate_b)
        assert row_a.to_dict() == row_b.to_dict()
        assert row_a.candidate_id == row_b.candidate_id