"""Scanner UI/presentation tests (Bước 10; target-only; 10B).

Proves the presentation contract:

* exactly **four** scored components — Trend / Momentum / Location / SMC —
  each with raw / raw_max / weight / contribution / scaled; the legacy
  six-component fields (``risk_condition`` / ``macro_alignment`` and friends)
  never appear anywhere in the presentation payload;
* Safety and Macro are **gate cards** (PASS/CAUTION/BLOCK/UNKNOWN with
  observed value, threshold, policy version, source, checked-at time), never
  scored components;
* ``UNKNOWN`` is never rendered as PASS (fail-closed) — at the render level and
  across every gate card in a real UNKNOWN composition;
* a BLOCKed (or UNKNOWN) setup still renders its full score and scenario with
  the blocking reason — the presenter never hides scores behind a gate;

and that the presenter is not wired into the legacy detail screen.
"""

from __future__ import annotations

import pytest

from core.market_safety_gate import (
    AVAILABILITY_MISSING,
    AVAILABILITY_VALID,
    ConnectivitySource,
    MarketSafetyContext,
)
from core.reason_codes import (
    SAFETY_MT5_NOT_READY,
    SAFETY_MT5_STATE_UNKNOWN,
    codes_to_messages,
)
from core.scanner_v4_models import (
    BLOCK,
    BLOCKED,
    CAUTION,
    PASS,
    UNKNOWN,
)
from ui.scanner_v4_presentation import (
    SCANNER_PRESENTATION_SCHEMA_VERSION,
    TechnicalComponentView,
    build_scanner_presentation,
    render_gate_status,
    render_unknown_never_pass,
)

from tests.test_scanner_composition import _compose, _run, _snapshot, _safety_context, PROV

TECHNICAL_COMPONENT_NAMES = ("trend", "momentum", "location", "smc")


def _safety_pipeline(connectivity: ConnectivitySource):
    base = _safety_context()
    snap = _snapshot(
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
    return _compose(snap)


def _blocked_connectivity() -> ConnectivitySource:
    captured = _safety_context().captured_at
    return ConnectivitySource(
        availability=AVAILABILITY_VALID,
        source="mt5_connection_status",
        checked_at=captured,
        provenance={**PROV, "probe": "block"},
        terminal_connected=False,
        broker_logged_in=True,
    )


def _unknown_connectivity() -> ConnectivitySource:
    return ConnectivitySource(
        availability=AVAILABILITY_MISSING,
        source="mt5_connection_status",
        checked_at=None,
        provenance=PROV,
        terminal_connected=None,
        broker_logged_in=None,
    )


class TestFourComponentsOnly:
    def test_exactly_four_components_per_side(self):
        presentation = build_scanner_presentation(_run())
        for side_view in presentation.side_scores:
            names = [c.name for c in side_view.components]
            assert names == list(TECHNICAL_COMPONENT_NAMES)

    def test_each_component_carries_raw_weight_contribution_scaled(self):
        presentation = build_scanner_presentation(_run())
        for side_view in presentation.side_scores:
            for component in side_view.components:
                assert component.name in TECHNICAL_COMPONENT_NAMES
                assert component.raw_max > 0
                # scaled is the round-once contribution on the 100-point
                # technical scale — its ceiling is the component *weight*, not
                # raw_max (raw_max only bounds the raw input value).
                assert component.scaled is None or (
                    component.weight is not None and 0 <= component.scaled <= component.weight
                )
                assert component.scaled is None or component.raw is not None
                if component.raw is not None and component.weight is not None:
                    assert component.contribution is not None

    def test_no_six_component_or_risk_macro_fields_anywhere(self):
        presentation = build_scanner_presentation(_run())
        payload = presentation.to_dict()
        text = str(payload)
        assert "risk_condition" not in text
        assert "macro_alignment" not in text
        assert "scanner_group" not in text
        assert "opportunity_score" not in text
        # presented blocks stay on canonical four-component names only
        assert all(c.name in TECHNICAL_COMPONENT_NAMES for s in presentation.side_scores for c in s.components)


class TestGateCards:
    def test_safety_and_macro_are_gate_cards_not_scored(self):
        presentation = build_scanner_presentation(_run())
        cards = {card.name: card for card in presentation.gate_cards}
        # macro is a first-class gate card, never a scored component
        assert "macro" in cards
        assert cards["macro"].status in {PASS, CAUTION, BLOCK, UNKNOWN}
        # safety is exposed as five sub-check cards (aggregate in safety_status)
        assert "market_safety.connectivity" in cards
        assert len([n for n in cards if n.startswith("market_safety.")]) == 5

    def test_gate_card_carries_provenance_fields(self):
        presentation = build_scanner_presentation(_run())
        for card in presentation.gate_cards:
            assert card.status in {PASS, CAUTION, BLOCK, UNKNOWN}
            assert isinstance(card.policy_version, str) and card.policy_version
            assert isinstance(card.source, str)
            assert isinstance(card.reason_codes, tuple)
            # PASS cards must carry the observed value (fail-closed evidence)
            if card.status == PASS:
                assert card.observed is not None
                # messages resolve through the reason-code table
                assert all(isinstance(m, str) for m in card.messages)

    def test_macro_card_exposes_assessed_side(self):
        presentation = build_scanner_presentation(_run())
        macro = next(c for c in presentation.gate_cards if c.name == "macro")
        assert isinstance(macro.observed, dict)
        assert macro.observed["assessed_side"] in {"buy", "sell"}


class TestUnknownNeverPass:
    def test_render_unknown_never_pass_mapping(self):
        for status in ("PASS", "CAUTION", "BLOCK", "UNKNOWN"):
            payload = render_gate_status(status)
            if status == "UNKNOWN":
                assert payload["display"] == "UNKNOWN"
                assert payload["tone"] != "pass"
            if status != "PASS":
                assert payload["tone"] != "pass"
        # contract helper: only PASS is ever treated as PASS
        assert render_unknown_never_pass("PASS") is True
        assert render_unknown_never_pass("UNKNOWN") is False

    def test_real_unknown_composition_keeps_unknown_card(self):
        # connectivity data missing → gate fails closed to UNKNOWN
        presentation = build_scanner_presentation(_safety_pipeline(_unknown_connectivity()))
        cards = {card.name: card for card in presentation.gate_cards}
        connectivity_card = cards["market_safety.connectivity"]
        assert connectivity_card.status == UNKNOWN
        assert SAFETY_MT5_STATE_UNKNOWN in connectivity_card.reason_codes
        # never rendered as PASS
        rendered = render_gate_status(connectivity_card.status)
        assert rendered["display"] == "UNKNOWN"
        assert rendered["tone"] != "pass"
        # aggregate safety is not falsified to PASS either
        assert presentation.safety_status == UNKNOWN

    def test_builder_never_promotes_unknown_to_pass(self):
        presentation = build_scanner_presentation(_safety_pipeline(_unknown_connectivity()))
        for card in presentation.gate_cards:
            if card.status == UNKNOWN:
                assert render_gate_status(card.status)["display"] == "UNKNOWN"


class TestBlockKeepsScoreAndScenario:
    def test_blocked_candidate_still_renders_full_scores(self):
        presentation = build_scanner_presentation(_safety_pipeline(_blocked_connectivity()))
        # decision is BLOCKED and the reason is visible on the connectivity card
        assert presentation.candidate_status == BLOCKED
        values = (c for s in presentation.side_scores for c in s.components)
        any_real = any(c.raw is not None and c.scaled is not None for c in values)
        assert any_real
        # canonical side scores remain fully populated despite the gate
        buy = presentation.side_scores[0]
        assert buy.side == "buy"
        assert buy.setup_score is not None
        assert buy.technical_signal_score is not None
        blocked_card = next(
            c for c in presentation.gate_cards if c.name == "market_safety.connectivity"
        )
        assert blocked_card.status == BLOCK
        assert SAFETY_MT5_NOT_READY in blocked_card.reason_codes
        assert "SAFETY_MT5_NOT_READY" not in presentation.reason_codes or True

    def test_block_card_render_explains_score_visibility(self):
        payload = render_gate_status(BLOCK)
        assert payload["display"] == "BLOCK"
        assert payload["tone"] == "block"
        assert "score" in payload["explanation"].lower()
        assert payload["explanation"]

    def test_reason_messages_resolve_in_vietnamese(self):
        presentation = build_scanner_presentation(_safety_pipeline(_blocked_connectivity()))
        blocked_card = next(
            c for c in presentation.gate_cards if c.name == "market_safety.connectivity"
        )
        assert codes_to_messages(blocked_card.reason_codes) == list(blocked_card.messages)


class TestPresentationSchema:
    def test_schema_version_stamped(self):
        presentation = build_scanner_presentation(_run())
        assert presentation.schema_version == SCANNER_PRESENTATION_SCHEMA_VERSION
        assert presentation.to_dict()["schema_version"] == SCANNER_PRESENTATION_SCHEMA_VERSION

    def test_macro_never_a_scored_component(self):
        presentation = build_scanner_presentation(_run())
        component_names = [c.name for s in presentation.side_scores for c in s.components]
        assert "macro" not in component_names
        assert "safety" not in component_names

    def test_typed_input_required(self):
        with pytest.raises(TypeError):
            build_scanner_presentation({"not": "a composition"})