"""Test Bước 6 — AI Macro Verdict (services/macro_ai_verdict.py).

Bao phủ: parser + validate JSON (nhóm A), decision table / constraints (nhóm B),
cache disk (nhóm C), assessor fail-closed (nhóm D), integration với gate engine (nhóm E).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

import pytest

from services.macro_ai_verdict import (
    ADJUSTMENT_MAX,
    ADJUSTMENT_MIN,
    MIN_AI_CONVICTION,
    MIN_MACRO_SCORE_FOR_VERDICT,
    FALLBACK_VERDICT,
    BIAS_VALUES,
    MacroVerdict,
    MacroVerdictAssessor,
    MacroVerdictCache,
    _ai_fingerprint,
    build_verdict_prompt,
    parse_verdict_json,
    verdict_cache_key,
)
from core.reason_codes import (
    MACRO_AI_VETO,
    MACRO_AI_ADJUSTMENT,
    MACRO_AI_VERDICT_SKIPPED,
)
from core.trade_gate_engine import check_trade_gates


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

T0 = datetime(2026, 8, 7, 9, 0, 0, tzinfo=UTC)
TODAY = "2026-08-07"
PAIR = "EUR/USD"


def _mock_ai_service(response: str | Exception) -> MagicMock:
    """Tạo AIService giả với analyze() trả về response hoặc raise Exception."""
    svc = MagicMock()
    if isinstance(response, Exception):
        svc.analyze.side_effect = response
    else:
        svc.analyze.return_value = response
    svc.config = MagicMock(provider="test", model="test-model")
    return svc


def _macro_context(buy: int = 22, sell: int = 10) -> dict:
    """Tạo macro_context tối thiểu để qua ngưỡng top candidate."""
    return {
        "alignment": {"buy": buy, "sell": sell},
        "tier1": {"buy": 8, "sell": 4, "detail": {}},
        "tier2": {"buy": 5, "sell": 5, "event_risk_level": "medium"},
        "tier3": {"buy": 5, "sell": 3},
        "macro_v2": {"buy": 18, "sell": 12, "confidence": 0.6},
        "data_quality": {"macro_confidence": 0.85},
        "upcoming_event_assessments": [],
        "correlation": {"has_dxy": True, "has_vix": False},
        "stance": {},
    }


def _valid_verdict_json(
    bias: str = "aligned",
    conviction: float = 0.85,
    conflicts: list | None = None,
    veto: bool = False,
    adjustment: int = 0,
    evidence: list | None = None,
) -> str:
    return json.dumps({
        "bias": bias,
        "conviction": conviction,
        "conflicts": conflicts or [],
        "veto": veto,
        "adjustment": adjustment,
        "evidence": evidence or ["các tầng đồng thuận"],
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Nhóm A: Parser + Validate
# ---------------------------------------------------------------------------

class TestParseVerdictJson:
    """Nhóm A: parse_verdict_json() — trích xuất và validate JSON từ AI response."""

    def test_valid_json(self):
        """Parse JSON hợp lệ trả về dict chuẩn hóa."""
        result = parse_verdict_json(_valid_verdict_json(
            bias="conflict", conviction=0.9,
            conflicts=["mâu thuẫn lãi suất vs DXY"],
            veto=True, adjustment=-4,
        ))
        assert result is not None
        assert result["bias"] == "conflict"
        assert result["conviction"] == 0.9
        assert result["conflicts"] == ["mâu thuẫn lãi suất vs DXY"]
        assert result["veto"] is True
        assert result["adjustment"] == -4

    def test_json_wrapped_in_markdown_fence(self):
        """JSON bọc trong ```json ... ``` vẫn parse được."""
        raw = "```json\n" + _valid_verdict_json() + "\n```"
        result = parse_verdict_json(raw)
        assert result is not None
        assert result["bias"] == "aligned"

    def test_json_with_surrounding_text(self):
        """JSON có text bao quanh — extract bằng bracket matching."""
        raw = "Đây là phân tích:\n" + _valid_verdict_json() + "\nHy vọng hữu ích."
        result = parse_verdict_json(raw)
        assert result is not None

    def test_missing_bias_field(self):
        """Thiếu trường bias → None."""
        data = {"conviction": 0.8, "conflicts": [], "veto": False, "adjustment": 0, "evidence": []}
        result = parse_verdict_json(json.dumps(data))
        assert result is None

    def test_bias_invalid_value(self):
        """bias không nằm trong {aligned, conflict, unclear} → None."""
        result = parse_verdict_json(_valid_verdict_json(bias="bullish"))
        assert result is None

    def test_conviction_out_of_range(self):
        """conviction > 1.0 → None."""
        result = parse_verdict_json(_valid_verdict_json(conviction=1.5))
        assert result is None

    def test_conviction_negative(self):
        """conviction < 0 → None."""
        result = parse_verdict_json(_valid_verdict_json(conviction=-0.1))
        assert result is None

    def test_adjustment_positive_rejected(self):
        """adjustment > 0 bị từ chối (bất đối xứng)."""
        result = parse_verdict_json(_valid_verdict_json(adjustment=3))
        assert result is None

    def test_adjustment_below_minus_5_rejected(self):
        """adjustment < -5 bị từ chối."""
        result = parse_verdict_json(_valid_verdict_json(adjustment=-7))
        assert result is None

    def test_empty_response(self):
        """Response rỗng → None."""
        assert parse_verdict_json("") is None

    def test_non_string_response(self):
        """Response không phải string → None."""
        assert parse_verdict_json(None) is None
        assert parse_verdict_json(123) is None

    def test_veto_true_without_conflicts(self):
        """veto=true nhưng conflicts=[] → tự động sửa veto=false."""
        result = parse_verdict_json(_valid_verdict_json(
            veto=True, conflicts=[],
        ))
        assert result is not None
        assert result["veto"] is False

    def test_bias_conflict_without_conflicts(self):
        """bias=conflict nhưng không có conflicts → sửa thành unclear."""
        result = parse_verdict_json(_valid_verdict_json(
            bias="conflict", conflicts=[],
        ))
        assert result is not None
        assert result["bias"] == "unclear"

    def test_missing_evidence_field(self):
        """Thiếu evidence → None."""
        data = {"bias": "aligned", "conviction": 0.8, "conflicts": [], "veto": False, "adjustment": 0}
        result = parse_verdict_json(json.dumps(data))
        assert result is None

    def test_evidence_not_list(self):
        """evidence không phải list → None."""
        result = parse_verdict_json(_valid_verdict_json(evidence="not a list"))  # type: ignore[arg-type]
        assert result is None

    def test_garbage_text(self):
        """Text không chứa JSON → None."""
        assert parse_verdict_json("đây không phải json") is None


# ---------------------------------------------------------------------------
# Nhóm B: Constraints / Decision Table
# ---------------------------------------------------------------------------

class TestConstraints:
    """Nhóm B: ràng buộc bất đối xứng — adjustment chỉ -5..0, veto chỉ làm khó."""

    def test_adjustment_at_boundary_minus_5(self):
        """adjustment=-5 hợp lệ."""
        result = parse_verdict_json(_valid_verdict_json(adjustment=-5))
        assert result is not None
        assert result["adjustment"] == -5

    def test_adjustment_at_boundary_zero(self):
        """adjustment=0 hợp lệ."""
        result = parse_verdict_json(_valid_verdict_json(adjustment=0))
        assert result is not None
        assert result["adjustment"] == 0

    def test_veto_false_no_effect(self):
        """veto=false → không có tác dụng."""
        result = parse_verdict_json(_valid_verdict_json(veto=False, adjustment=0))
        assert result is not None
        assert result["veto"] is False
        assert result["adjustment"] == 0

    def test_veto_and_adjustment_combined(self):
        """veto=true + adjustment=-3 cùng lúc."""
        result = parse_verdict_json(_valid_verdict_json(
            veto=True, adjustment=-3,
            conflicts=["Tier 1 hawkish nhưng DXY giảm"],
        ))
        assert result is not None
        assert result["veto"] is True
        assert result["adjustment"] == -3

    def test_all_bias_values_accepted(self):
        """Tất cả bias hợp lệ đều parse được."""
        for bias in BIAS_VALUES:
            # "conflict" requires non-empty conflicts list, else auto-corrected to "unclear"
            extra = {}
            if bias == "conflict":
                extra["conflicts"] = ["mâu thuẫn Tier 1 vs DXY"]
            result = parse_verdict_json(_valid_verdict_json(bias=bias, **extra))
            assert result is not None, f"bias={bias} should be valid"
            assert result["bias"] == bias

    def test_conviction_at_boundary(self):
        """conviction=0.0 và 1.0 đều hợp lệ."""
        result = parse_verdict_json(_valid_verdict_json(conviction=0.0))
        assert result is not None
        result = parse_verdict_json(_valid_verdict_json(conviction=1.0))
        assert result is not None


# ---------------------------------------------------------------------------
# Nhóm C: Cache
# ---------------------------------------------------------------------------

class TestMacroVerdictCache:
    """Nhóm C: MacroVerdictCache — disk cache per (pair, date)."""

    def test_put_and_get_same_day(self):
        """Ghi rồi đọc lại cùng ngày → hit."""
        with TemporaryDirectory() as tmpdir:
            cache = MacroVerdictCache(cache_dir=Path(tmpdir))
            verdict = MacroVerdict(
                pair=PAIR, date=TODAY, bias="aligned", conviction=0.9,
                conflicts=[], veto=False, adjustment=0, evidence=["ok"],
                source="ai",
            )
            fp = _ai_fingerprint(None)
            cache.put(verdict, fp)
            cached = cache.get(PAIR, TODAY, fp)
            assert cached is not None
            assert cached.pair == PAIR
            assert cached.bias == "aligned"
            assert cached.veto is False

    def test_different_date_miss(self):
        """Khác ngày → miss."""
        with TemporaryDirectory() as tmpdir:
            cache = MacroVerdictCache(cache_dir=Path(tmpdir))
            verdict = MacroVerdict(
                pair=PAIR, date=TODAY, bias="aligned", conviction=0.9,
                conflicts=[], veto=False, adjustment=0, evidence=["ok"],
                source="ai",
            )
            fp = _ai_fingerprint(None)
            cache.put(verdict, fp)
            cached = cache.get(PAIR, "2026-08-08", fp)
            assert cached is None

    def test_different_pair_miss(self):
        """Khác cặp → miss."""
        with TemporaryDirectory() as tmpdir:
            cache = MacroVerdictCache(cache_dir=Path(tmpdir))
            verdict = MacroVerdict(
                pair=PAIR, date=TODAY, bias="aligned", conviction=0.9,
                conflicts=[], veto=False, adjustment=0, evidence=["ok"],
                source="ai",
            )
            fp = _ai_fingerprint(None)
            cache.put(verdict, fp)
            cached = cache.get("GBP/JPY", TODAY, fp)
            assert cached is None

    def test_fingerprint_mismatch_miss(self):
        """Khác fingerprint → miss (đổi model AI)."""
        with TemporaryDirectory() as tmpdir:
            cache = MacroVerdictCache(cache_dir=Path(tmpdir))
            verdict = MacroVerdict(
                pair=PAIR, date=TODAY, bias="aligned", conviction=0.9,
                conflicts=[], veto=False, adjustment=0, evidence=["ok"],
                source="ai",
            )
            cache.put(verdict, "fp-v1")
            cached = cache.get(PAIR, TODAY, "fp-v2")
            assert cached is None

    def test_empty_cache_dir(self):
        """Cache dir rỗng → get trả về None."""
        with TemporaryDirectory() as tmpdir:
            cache = MacroVerdictCache(cache_dir=Path(tmpdir))
            fp = _ai_fingerprint(None)
            assert cache.get(PAIR, TODAY, fp) is None

    def test_verdict_cache_key(self):
        """Cache key ổn định."""
        k1 = verdict_cache_key("EUR/USD", "2026-08-07", "fp1")
        k2 = verdict_cache_key("EUR/USD", "2026-08-07", "fp1")
        assert k1 == k2
        k3 = verdict_cache_key("EUR/USD", "2026-08-08", "fp1")
        assert k1 != k3


# ---------------------------------------------------------------------------
# Nhóm D: Assessor — fail-closed
# ---------------------------------------------------------------------------

class TestMacroVerdictAssessor:
    """Nhóm D: MacroVerdictAssessor.assess() — AI call, cache, fallback."""

    def test_feature_flag_off_skips(self):
        """Feature flag OFF → skip_disabled."""
        assessor = MacroVerdictAssessor()
        ai_svc = _mock_ai_service(_valid_verdict_json())
        verdict = assessor.assess(
            PAIR, _macro_context(), ai_svc, date_str=TODAY, verdict_enabled=False,
        )
        assert verdict.source == "skip_disabled"
        assert verdict.veto is False
        assert verdict.adjustment == 0

    def test_below_threshold_skips(self):
        """Macro score < 20 → skip_below_threshold."""
        assessor = MacroVerdictAssessor()
        ai_svc = _mock_ai_service(_valid_verdict_json())
        ctx = _macro_context(buy=15, sell=15)  # below 20
        verdict = assessor.assess(
            PAIR, ctx, ai_svc, date_str=TODAY, verdict_enabled=True,
        )
        assert verdict.source == "skip_below_threshold"

    def test_ai_success_returns_verdict(self):
        """AI thành công → verdict với source='ai'."""
        with TemporaryDirectory() as tmpdir:
            cache = MacroVerdictCache(cache_dir=Path(tmpdir) / "cache")
            assessor = MacroVerdictAssessor(cache=cache)
            ai_svc = _mock_ai_service(_valid_verdict_json(
                bias="aligned", conviction=0.9, veto=False, adjustment=-1,
            ))
            verdict = assessor.assess(
                PAIR, _macro_context(), ai_svc, date_str=TODAY, verdict_enabled=True,
            )
            assert verdict.source == "ai"
            assert verdict.bias == "aligned"
            assert verdict.conviction == 0.9
            assert verdict.adjustment == -1
            assert verdict.veto is False

    def test_ai_returns_veto(self):
        """AI phát hiện mâu thuẫn → veto=true."""
        with TemporaryDirectory() as tmpdir:
            cache = MacroVerdictCache(cache_dir=Path(tmpdir) / "cache")
            assessor = MacroVerdictAssessor(cache=cache)
            ai_svc = _mock_ai_service(_valid_verdict_json(
                bias="conflict", conviction=0.85,
                conflicts=["Tier 1 hawkish nhưng DXY giảm mạnh"],
                veto=True, adjustment=-5,
            ))
            verdict = assessor.assess(
                PAIR, _macro_context(), ai_svc, date_str=TODAY, verdict_enabled=True,
            )
            assert verdict.source == "ai"
            assert verdict.veto is True
            assert verdict.adjustment == -5
            assert len(verdict.conflicts) > 0

    def test_ai_exception_fallback(self):
        """AI ném exception → fallback."""
        assessor = MacroVerdictAssessor()
        ai_svc = _mock_ai_service(RuntimeError("timeout"))
        verdict = assessor.assess(
            PAIR, _macro_context(), ai_svc, date_str=TODAY, verdict_enabled=True,
        )
        assert verdict.source == "fallback"
        assert verdict.veto is False
        assert verdict.adjustment == 0

    def test_ai_invalid_json_fallback(self):
        """AI trả về text không phải JSON → fallback."""
        assessor = MacroVerdictAssessor()
        ai_svc = _mock_ai_service("xin chào, tôi không thể phân tích")
        verdict = assessor.assess(
            PAIR, _macro_context(), ai_svc, date_str=TODAY, verdict_enabled=True,
        )
        assert verdict.source == "fallback"

    def test_no_ai_service_fallback(self):
        """ai_service=None → fallback."""
        assessor = MacroVerdictAssessor()
        verdict = assessor.assess(
            PAIR, _macro_context(), None, date_str=TODAY, verdict_enabled=True,
        )
        assert verdict.source == "fallback"

    def test_cache_hit_avoids_ai_call(self):
        """Cache hit → không gọi AI lại."""
        with TemporaryDirectory() as tmpdir:
            cache = MacroVerdictCache(cache_dir=Path(tmpdir) / "cache")
            assessor = MacroVerdictAssessor(cache=cache)

            # First call → writes cache
            ai_svc = _mock_ai_service(_valid_verdict_json(conviction=0.9))
            v1 = assessor.assess(
                PAIR, _macro_context(), ai_svc, date_str=TODAY, verdict_enabled=True,
            )
            assert v1.source == "ai"
            call_count_1 = ai_svc.analyze.call_count

            # Second call → reads cache, no AI call
            ai_svc2 = _mock_ai_service(_valid_verdict_json(conviction=0.7))
            v2 = assessor.assess(
                PAIR, _macro_context(), ai_svc2, date_str=TODAY, verdict_enabled=True,
            )
            assert v2.source == "ai"
            assert ai_svc2.analyze.call_count == 0  # cached, no call


# ---------------------------------------------------------------------------
# Nhóm E: Prompts
# ---------------------------------------------------------------------------

class TestBuildPrompt:
    """Nhóm E: build_verdict_prompt() — prompt construction."""

    def test_prompt_includes_pair_and_side(self):
        """Prompt chứa tên cặp và hướng."""
        prompt = build_verdict_prompt(PAIR, _macro_context(), "buy")
        assert PAIR in prompt
        assert "BUY" in prompt

    def test_prompt_includes_tier_scores(self):
        """Prompt chứa điểm các tier."""
        prompt = build_verdict_prompt(PAIR, _macro_context(), "sell")
        assert "TẦNG 1" in prompt
        assert "TẦNG 2" in prompt
        assert "TẦNG 3" in prompt

    def test_prompt_handles_empty_context(self):
        """Prompt với context None không crash."""
        prompt = build_verdict_prompt(PAIR, None, "buy")
        assert PAIR in prompt

    def test_prompt_specifies_rules(self):
        """Prompt có hướng dẫn về quy tắc bất đối xứng."""
        prompt = build_verdict_prompt(PAIR, _macro_context(), "buy")
        assert "QUY TẮC BẮT BUỘC" in prompt
        assert "-5 đến 0" in prompt


# ---------------------------------------------------------------------------
# Nhóm F: Fingerprint
# ---------------------------------------------------------------------------

class TestFingerprint:
    """Nhóm F: _ai_fingerprint() ổn định."""

    def test_none_ai_service(self):
        """ai_service=None → fingerprint ghi enabled=False."""
        fp = _ai_fingerprint(None)
        assert "enabled" in fp
        data = json.loads(fp)
        assert data["enabled"] is False

    def test_ai_service_with_config(self):
        """ai_service có config → fingerprint chứa provider + model."""
        svc = _mock_ai_service("ok")
        fp = _ai_fingerprint(svc)
        data = json.loads(fp)
        assert data["enabled"] is True
        assert data["provider"] == "test"
        assert data["model"] == "test-model"

    def test_different_model_different_fingerprint(self):
        """Khác model → khác fingerprint."""
        svc1 = _mock_ai_service("ok")
        svc2 = _mock_ai_service("ok")
        svc2.config.model = "different-model"
        assert _ai_fingerprint(svc1) != _ai_fingerprint(svc2)


# ---------------------------------------------------------------------------
# Nhóm G: Dataclass
# ---------------------------------------------------------------------------

class TestMacroVerdictDataclass:
    """Nhóm G: MacroVerdict dataclass — factory methods + to_dict."""

    def test_skip_factory(self):
        """MacroVerdict.skip() tạo verdict với source=reason."""
        v = MacroVerdict.skip(PAIR, TODAY, "skip_below_threshold")
        assert v.pair == PAIR
        assert v.veto is False
        assert v.adjustment == 0
        assert v.source == "skip_below_threshold"

    def test_fallback_factory(self):
        """MacroVerdict.fallback() tạo verdict an toàn."""
        v = MacroVerdict.fallback(PAIR, TODAY)
        assert v.source == "fallback"
        assert v.veto is False
        assert v.adjustment == 0
        assert v.bias == "unclear"

    def test_to_dict(self):
        """to_dict() chứa tất cả trường."""
        v = MacroVerdict(
            pair=PAIR, date=TODAY, bias="conflict", conviction=0.8,
            conflicts=["mâu thuẫn"], veto=True, adjustment=-3,
            evidence=["căn cứ"], source="ai",
        )
        d = v.to_dict()
        assert d["pair"] == PAIR
        assert d["veto"] is True
        assert d["adjustment"] == -3
        assert "conviction" in d


# ---------------------------------------------------------------------------
# Nhóm H: Gate Engine Integration
# ---------------------------------------------------------------------------

class TestGateMacroAiVerdict:
    """Nhóm H: _gate_macro_ai_verdict trong trade_gate_engine."""

    def _gate_context(self, **overrides):
        ctx = {
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
            "macro_ai_veto": False,
            "macro_ai_conviction": 1.0,
            "macro_ai_conflicts": [],
        }
        ctx.update(overrides)
        return ctx

    def test_veto_false_no_effect(self):
        """veto=false → gate không thay đổi gì."""
        ctx = self._gate_context(macro_ai_veto=False)
        result = check_trade_gates(ctx)
        assert result["allowed"] is True
        assert MACRO_AI_VETO not in result.get("warning_codes", [])

    def test_veto_true_caps_to_watch(self):
        """veto=true → decision_cap = WATCH_ONLY."""
        ctx = self._gate_context(
            macro_ai_veto=True,
            macro_ai_conviction=0.9,
            macro_ai_conflicts=["mâu thuẫn Tier 1 vs DXY"],
        )
        result = check_trade_gates(ctx)
        assert result["allowed"] is True  # không block, chỉ cap
        assert result["decision_cap"] == "WATCH_ONLY"
        assert MACRO_AI_VETO in result.get("warning_codes", [])

    def test_veto_with_low_conviction_no_effect(self):
        """veto=true nhưng conviction < 0.7 → gate bỏ qua."""
        ctx = self._gate_context(
            macro_ai_veto=True,
            macro_ai_conviction=0.5,
        )
        result = check_trade_gates(ctx)
        assert MACRO_AI_VETO not in result.get("warning_codes", [])

    def test_veto_when_already_blocked_no_effect(self):
        """Nếu gate đã TRADE_BLOCKED → veto không thay đổi."""
        ctx = self._gate_context(
            macro_ai_veto=True,
            macro_ai_conviction=0.9,
            spread_status="abnormal",  # ← triggers TRADE_BLOCKED
        )
        result = check_trade_gates(ctx)
        assert result["allowed"] is False
        assert result["decision_cap"] == "TRADE_BLOCKED"
