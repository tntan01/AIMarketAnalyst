from __future__ import annotations

from math import inf, nan

from core.decision_engine import clamp_score as decision_clamp_score
from core.execution_quality_engine import clamp_score as execution_clamp_score
from core.final_score_engine import clamp_score as final_clamp_score
from core.safe_types import (
    clamp_score,
    finite_float,
    optional_float,
    safe_float,
    safe_optional_float,
)
from core.scanner_ranking_engine import clamp_score as scanner_clamp_score

# Legacy alias test — _safe_float was consolidated into optional_float
feedback_safe_float = optional_float


def test_finite_float_accepts_numeric_like_values():
    assert finite_float(1) == 1.0
    assert finite_float(1.25) == 1.25
    assert finite_float(" 2.5 ") == 2.5


def test_finite_float_rejects_dirty_or_non_finite_values():
    assert finite_float(None) is None
    assert finite_float("") is None
    assert finite_float("abc") is None
    assert finite_float(nan) is None
    assert finite_float(inf) is None
    assert finite_float("-inf") is None


def test_safe_float_supports_default_and_negative_policy():
    assert safe_float("bad", default=3.5) == 3.5
    assert safe_float("-1.5") == -1.5
    assert safe_float("-1.5", default=0.0, allow_negative=False) == 0.0
    assert safe_float("bad", default=None) is None
    assert safe_optional_float("bad") is None


def test_optional_float_preserves_non_finite_values_for_legacy_wrappers():
    assert optional_float("bad") is None
    assert optional_float("inf") == inf
    assert feedback_safe_float("inf") == inf


def test_clamp_score_rounds_values_and_clamps_range():
    assert clamp_score("72.5") == 72
    assert clamp_score("72.6") == 73
    assert clamp_score(101) == 100
    assert clamp_score(-1) == 0
    assert clamp_score("bad") == 0
    assert clamp_score("bad", default=55) == 55
    assert clamp_score("bad", minimum=35, maximum=65) == 35


def test_engine_wrappers_preserve_fallback_signatures():
    assert final_clamp_score("bad", 10, 90) == 10
    assert decision_clamp_score("bad", default=40) == 40
    assert scanner_clamp_score("bad", default=40, minimum=20, maximum=60) == 40
    assert execution_clamp_score("inf") == 100
