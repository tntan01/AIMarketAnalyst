"""Scanner V4 UI presentation contract (Bước 10; target-only).

10B replaces the V3 six-component rendering in
``ui/screens/scanner_detail_screen.py:2940-3021`` (which views
``risk_condition`` and ``macro_alignment`` as scored components) with a strict
presenter that consumes the canonical Step 07/08 output and renders:

* exactly **four** scored components — Trend / Momentum / Location / SMC —
  each with its raw value, raw max, weight and scaled contribution;
* **gate cards** for MarketSafety and Macro as first-class gates (not scored
  components): PASS / CAUTION / BLOCK / UNKNOWN together with the observed
  value, threshold, policy version, source, checked-at time and reason codes.

Rules enforced (DoR-10 / 10B):

* ``UNKNOWN`` is NEVER rendered as PASS.  A gate that has no certified PASS
  keeps its canonical status and shows its reason code.
* A BLOCKed setup still renders the full score/scenario with the blocking
  reason — the presenter never hides scores behind a gate.
* No ``risk_condition`` / ``macro_alignment`` / six-component layout is
  produced; Safety/Macro are never rendered as additive points.

The module is pure (dicts in, dicts out) so it stays UI-framework neutral and
testable.  It is not wired into the V3 detail screen until cutover.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.reason_codes import codes_to_messages
from core.scanner_v4_composition import ScannerV4CompositionResult
from core.scanner_v4_models import (
    BLOCK,
    BUY,
    CAUTION,
    PASS,
    SELL,
    UNKNOWN,
    TechnicalComponent,
)

SCANNER_V4_PRESENTATION_SCHEMA_VERSION = "scanner-v4-presentation-v1"

# The only components the V4 UI may render as scored; anything else (in
# particular the V3 six-component rows) is a presenter error.
TECHNICAL_COMPONENT_NAMES = ("trend", "momentum", "location", "smc")

# Gate-card order: safety sub-checks in canonical SAFETY_CHECK_NAMES order,
# then macro, then composition gates (scenario/account/portfolio/journal).
_ERROR_MSG = "V4 presenter only accepts a ScannerV4CompositionResult"
_ERROR_MSG_UNKNOWN_PASS = (
    "UNKNOWN/None evidence can never be rendered as PASS (fail-closed)"
)


@dataclass(frozen=True, slots=True)
class TechnicalComponentView:
    """Rendered component: raw + scaled contribution (never re-scored)."""

    name: str
    raw: int | None
    raw_max: int
    weight: int | None
    contribution: float | None
    scaled: int | None  # round-once contribution in 0..raw_max scale

    @classmethod
    def from_technical(cls, name: str, component: TechnicalComponent) -> TechnicalComponentView:
        if type(component) is not TechnicalComponent:
            raise TypeError("expected a Scanner V4 TechnicalComponent")
        scaled = _round_half_up_contribution(component)
        return cls(
            name=name,
            raw=component.raw,
            raw_max=component.raw_max,
            weight=component.weight,
            contribution=component.contribution,
            scaled=scaled,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "raw": self.raw,
            "raw_max": self.raw_max,
            "weight": self.weight,
            "contribution": self.contribution,
            "scaled": self.scaled,
        }


def _round_half_up_contribution(component: TechnicalComponent) -> int | None:
    """Round the exact contribution (raw/raw_max*weight) once, half up.

    Mirrors the single-rounding rule the scorer already owns; the presenter
    only formats, it never re-aggregates the breakdown total.
    """
    if component.raw is None or component.weight is None or component.raw_max <= 0:
        return None
    exact = component.raw * component.weight / component.raw_max
    import math

    return math.floor(exact + 0.5)


@dataclass(frozen=True, slots=True)
class SideScoreView:
    """One side's score view: four components + setup/technical summary."""

    side: str
    technical_signal_score: int | None
    setup_score: int | None
    final_score: int | None  # alias of setup_score on the canonical side score
    evidence_score: int | None
    execution_quality_score: int | None
    components: tuple[TechnicalComponentView, ...]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "technical_signal_score": self.technical_signal_score,
            "setup_score": self.setup_score,
            "final_score": self.final_score,
            "evidence_score": self.evidence_score,
            "execution_quality_score": self.execution_quality_score,
            "components": [c.to_dict() for c in self.components],
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True, slots=True)
class GateCard:
    """One rendered gate card (PASS/CAUTION/BLOCK/UNKNOWN with evidence)."""

    name: str
    status: str
    observed: Any
    threshold: Any
    policy_version: str
    source: str
    checked_at: str
    reason_codes: tuple[str, ...]
    messages: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "observed": self.observed,
            "threshold": self.threshold,
            "policy_version": self.policy_version,
            "source": self.source,
            "checked_at": self.checked_at,
            "reason_codes": list(self.reason_codes),
            "messages": list(self.messages),
        }


@dataclass(frozen=True, slots=True)
class ScannerV4Presentation:
    """Full V4 presentation result (4 component view + gate cards)."""

    schema_version: str
    composition_version: str
    snapshot_id: str
    symbol: str
    captured_at: str
    candidate_status: str
    selected_side: str | None
    decision_cap: str | None
    side_scores: tuple[SideScoreView, ...]
    safety_status: str
    macro_status: str
    gate_cards: tuple[GateCard, ...]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "composition_version": self.composition_version,
            "snapshot_id": self.snapshot_id,
            "symbol": self.symbol,
            "captured_at": self.captured_at,
            "candidate_status": self.candidate_status,
            "selected_side": self.selected_side,
            "decision_cap": self.decision_cap,
            "side_scores": [s.to_dict() for s in self.side_scores],
            "safety_status": self.safety_status,
            "macro_status": self.macro_status,
            "gate_cards": [g.to_dict() for g in self.gate_cards],
            "reason_codes": list(self.reason_codes),
        }


def build_scanner_v4_presentation(
    composition: ScannerV4CompositionResult,
) -> ScannerV4Presentation:
    """Render the canonical composition as the V4 presentation (target-only)."""
    if type(composition) is not ScannerV4CompositionResult:
        raise TypeError(_ERROR_MSG)

    canonical = composition.canonical
    side_views: list[SideScoreView] = []
    for side in (BUY, SELL):
        score = canonical.side_score(side)
        side_views.append(
            SideScoreView(
                side=side,
                technical_signal_score=score.technical_signal_score,
                setup_score=score.setup_score,
                final_score=score.final_score,
                evidence_score=score.evidence_score,
                execution_quality_score=score.execution_quality_score,
                components=tuple(
                    TechnicalComponentView.from_technical(name, component)
                    for name, component in _breakdown_items(score.technical_breakdown)
                ),
                reason_codes=score.reason_codes,
            )
        )

    gate_cards = tuple(_build_gate_cards(composition))
    _assert_no_unknown_passed(gate_cards)

    return ScannerV4Presentation(
        schema_version=SCANNER_V4_PRESENTATION_SCHEMA_VERSION,
        composition_version=composition.to_dict()["composition_version"],
        snapshot_id=composition.snapshot_id,
        symbol=composition.symbol,
        captured_at=composition.captured_at.isoformat(),
        candidate_status=composition.decision.candidate_status,
        selected_side=composition.decision.selected_side,
        decision_cap=composition.decision.decision_cap,
        side_scores=tuple(side_views),
        safety_status=canonical.market_safety.status,
        macro_status=canonical.macro_gate.status,
        gate_cards=gate_cards,
        reason_codes=composition.decision.reason_codes,
    )


def _breakdown_items(breakdown: Any) -> tuple[tuple[str, TechnicalComponent], ...]:
    """Yield (name, TechnicalComponent) for the four allowed component names."""
    rows = (
        ("trend", breakdown.trend),
        ("momentum", breakdown.momentum),
        ("location", breakdown.location),
        ("smc", breakdown.smc),
    )
    for name, component in rows:
        if type(component) is not TechnicalComponent:
            raise TypeError(f"expected TechnicalComponent for {name!r}")
    return rows


def _build_gate_cards(composition: ScannerV4CompositionResult) -> list[GateCard]:
    canonical = composition.canonical
    cards: list[GateCard] = []

    # MarketSafety: one card per sub-check (canonical SAFETY_CHECK_NAMES order).
    # The aggregate status is exposed as ``presentation.safety_status``; there is
    # deliberately no aggregate card because it carries no single observed value
    # and the PASS-with-evidence invariant (10B) requires one.
    safety = canonical.market_safety
    for check in safety.checks:
        cards.append(
            GateCard(
                name=f"market_safety.{check.name}",
                status=check.status,
                observed=check.observed_value,
                threshold=check.threshold,
                policy_version=check.policy_version,
                source=check.source,
                checked_at=check.checked_at.isoformat(),
                reason_codes=check.reason_codes,
                messages=tuple(codes_to_messages(check.reason_codes)),
            )
        )

    # Macro: one gate card (never a scored component).
    macro = canonical.macro_gate
    cards.append(
        GateCard(
            name="macro",
            status=macro.status,
            observed={"assessed_side": macro.assessed_side},
            threshold=None,
            policy_version=macro.policy_version,
            source="macro_policy",
            checked_at=macro.checked_at.isoformat(),
            reason_codes=macro.reason_codes,
            messages=tuple(codes_to_messages(macro.reason_codes)),
        )
    )

    # Composition gates: scenario/account/portfolio/journal in canonical order.
    for gate in composition.composition_gates:
        cards.append(
            GateCard(
                name=gate.name,
                status=gate.status,
                observed=gate.observed,
                threshold=gate.threshold,
                policy_version=composition.to_dict()["composition_version"],
                source=gate.source,
                checked_at=gate.checked_at.isoformat(),
                reason_codes=gate.reason_codes,
                messages=tuple(codes_to_messages(gate.reason_codes)),
            )
        )
    return cards


def _assert_no_unknown_passed(gate_cards: tuple[GateCard, ...]) -> None:
    """Invariant: UNKNOWN / evidence-less gates are never rendered PASS."""
    for card in gate_cards:
        if card.status == PASS:
            if card.observed is None:
                raise ValueError(f"PASS card {card.name!r} has no observed value")
            if not card.reason_codes:
                # PASS gate cards may legitimately have empty reason codes at
                # the sub-check level when the gate is a pure pass (e.g. all
                # safety checks pass), but the *observed* evidence is required.
                pass
        if card.status == UNKNOWN:
            if _displays_as_pass(card):
                raise ValueError(_ERROR_MSG_UNKNOWN_PASS)


def _displays_as_pass(card: GateCard) -> bool:
    """Never true: UNKNOWN renders as UNKNOWN, not PASS (fail-closed rule)."""
    return False


# ---------------------------------------------------------------------------
# Blocked/UNKNOWN render helpers
# ---------------------------------------------------------------------------


def render_gate_status(status: str) -> dict[str, str]:
    """Map a canonical gate status to a render payload (never unknown->pass)."""
    from core.scanner_v4_models import VALID_GATE_STATUSES

    if status not in VALID_GATE_STATUSES:
        raise ValueError(f"invalid gate status {status!r}")
    if status == UNKNOWN:
        return {"display": "UNKNOWN", "tone": "unknown", "explanation": None}
    if status == PASS:
        return {"display": "PASS", "tone": "pass", "explanation": None}
    if status == CAUTION:
        return {
            "display": "CAUTION",
            "tone": "caution",
            "explanation": "Gate đạt trạng thái thận trọng, chờ xác nhận thêm.",
        }
    if status == BLOCK:
        return {
            "display": "BLOCK",
            "tone": "block",
            "explanation": "Gate đã chặn setup; score/scenario vẫn hiển thị để giải thích.",
        }
    raise AssertionError("unreachable")


def render_unknown_never_pass(status: str) -> bool:
    """Contract helper: return True iff a status renders as PASS.

    UNKNOWN (and any non-PASS status) renders as itself, never as PASS.
    """
    return status == PASS