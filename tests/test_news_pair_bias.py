"""Pure tests for the forex pair-bias derivation (contract §9.3 khoản 2, plan B4).

``core/pair_bias.py`` is the registered owner of the derived pair bias.  Its
contract, verified here:

* the deterministic matrix of §9.3 khoản 2 (missing leg / ``insufficient_data``
  -> ``UNCLEAR``; same direction -> that direction; one ``neutral`` -> the other
  side; opposite directions -> the higher-confidence side, equal -> ``NEUTRAL``);
* the confidence ordering ``high > medium > low`` across all three levels;
* ``PairBias`` pins the frozen strings and is a display-only derivation (never
  persisted, never a second AI call);
* the module stays pure and layer-clean: stdlib + ``core.news_models`` only,
  ASCII source, returns enum members.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core.news_models import (
    TrendVerdict,
    VerdictConfidence,
    VerdictDirection,
    VerdictHorizon,
    VerdictScopeType,
)
from core.pair_bias import PairBias, derive_pair_bias

_PAIR_BIAS_PY = Path(__file__).resolve().parents[1] / "core" / "pair_bias.py"

_BULLISH = VerdictDirection.BULLISH
_BEARISH = VerdictDirection.BEARISH
_NEUTRAL = VerdictDirection.NEUTRAL
_INSUFFICIENT = VerdictDirection.INSUFFICIENT_DATA
_HIGH = VerdictConfidence.HIGH
_MEDIUM = VerdictConfidence.MEDIUM
_LOW = VerdictConfidence.LOW


def _verdict(
    direction: VerdictDirection,
    confidence: VerdictConfidence,
    *,
    scope_value: str = "EUR",
) -> TrendVerdict:
    return TrendVerdict(
        created_at="2026-09-23T09:00:00Z",
        scope_type=VerdictScopeType.CURRENCY,
        scope_value=scope_value,
        horizon=VerdictHorizon.SHORT,
        direction=direction,
        confidence=confidence,
        rationale="Lập luận tiếng Việt.",
        evidence_item_ids=[],
        input_snapshot={},
        provider="deepseek",
        model="deepseek-v4-flash",
        prompt_hash="h",
    )


class TestEnumPinning:
    def test_members_pin_the_contract_strings(self):
        assert {member.value for member in PairBias} == {
            "bullish",
            "bearish",
            "neutral",
            "unclear",
        }

    def test_is_a_string_enum(self):
        assert issubclass(PairBias, str)
        assert str(PairBias.BULLISH) == "bullish"


class TestMatrix:
    def test_missing_leg_is_unclear(self):
        bullish = _verdict(_BULLISH, _HIGH)
        assert derive_pair_bias(None, bullish) is PairBias.UNCLEAR
        assert derive_pair_bias(bullish, None) is PairBias.UNCLEAR
        assert derive_pair_bias(None, None) is PairBias.UNCLEAR

    @pytest.mark.parametrize("side", ["base", "quote"])
    def test_insufficient_data_leg_is_unclear(self, side):
        good = _verdict(_BULLISH, _HIGH)
        weak = _verdict(_INSUFFICIENT, VerdictConfidence.NONE)
        base, quote = (weak, good) if side == "base" else (good, weak)
        assert derive_pair_bias(base, quote) is PairBias.UNCLEAR

    @pytest.mark.parametrize(
        ("direction", "expected"),
        [
            (_BULLISH, PairBias.BULLISH),
            (_BEARISH, PairBias.BEARISH),
            (_NEUTRAL, PairBias.NEUTRAL),
        ],
    )
    def test_same_direction_wins(self, direction, expected):
        assert derive_pair_bias(
            _verdict(direction, _LOW), _verdict(direction, _HIGH)
        ) is expected

    @pytest.mark.parametrize(
        ("other", "expected"),
        [(_BULLISH, PairBias.BULLISH), (_BEARISH, PairBias.BEARISH)],
    )
    def test_neutral_yields_the_other_side_both_orders(self, other, expected):
        neutral = _verdict(_NEUTRAL, _LOW)
        side = _verdict(other, _MEDIUM)
        assert derive_pair_bias(neutral, side) is expected
        assert derive_pair_bias(side, neutral) is expected

    def test_opposite_equal_confidence_is_neutral(self):
        for confidence in (_HIGH, _MEDIUM, _LOW):
            assert derive_pair_bias(
                _verdict(_BULLISH, confidence), _verdict(_BEARISH, confidence)
            ) is PairBias.NEUTRAL

    def test_opposite_confidence_decides_both_ways(self):
        # Base wins when it carries the higher confidence; quote wins otherwise.
        assert derive_pair_bias(
            _verdict(_BULLISH, _HIGH), _verdict(_BEARISH, _LOW)
        ) is PairBias.BULLISH
        assert derive_pair_bias(
            _verdict(_BULLISH, _LOW), _verdict(_BEARISH, _HIGH)
        ) is PairBias.BEARISH

    @pytest.mark.parametrize(
        ("base_conf", "quote_conf", "expected"),
        [
            (_HIGH, _MEDIUM, PairBias.BULLISH),
            (_MEDIUM, _LOW, PairBias.BULLISH),
            (_MEDIUM, _HIGH, PairBias.BEARISH),
            (_LOW, _MEDIUM, PairBias.BEARISH),
        ],
    )
    def test_all_three_confidence_levels(self, base_conf, quote_conf, expected):
        assert derive_pair_bias(
            _verdict(_BULLISH, base_conf), _verdict(_BEARISH, quote_conf)
        ) is expected


class TestCoreLayerBoundary:
    def test_module_source_is_ascii(self):
        assert _PAIR_BIAS_PY.read_text(encoding="utf-8").isascii()

    def test_module_imports_only_stdlib_and_core_news_models(self):
        tree = ast.parse(_PAIR_BIAS_PY.read_text(encoding="utf-8"))
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
            elif isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
        modules.discard("__future__")
        assert modules == {"enum", "core.news_models"}
