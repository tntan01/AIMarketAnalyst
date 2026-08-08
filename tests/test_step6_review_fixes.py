"""Test Bước 6 review fixes — wiring + integration (Critical 1/2/3, Major 4/5/6/7, Minor 9/11).

Bao phủ các lỗi tìm được trong docs/macro/step6_ai_macro_verdict_review.md:
- Critical 1: ai_service nối vào pipeline (integration test qua pipeline THẬT).
- Critical 2: macro_verdict_context (tier1/tier2/tier3/v2/stance) tới prompt AI.
- Critical 3: adjustment trừ thẳng vào component macro (0-30) của side chọn.
- Major 4: reason codes Bước 6 không bị ghi đè.
- Major 5: backtest read-cache-only (không gọi AI, đọc cache không cần fingerprint).
- Major 6: cache/journal phân biệt best_side.
- Major 7: timeout AI 15s (thread budget) → fallback.
- Minor 9: negative cache (failure được cache TTL ngắn).
- Minor 11: diagnostics status của macro_verdict nằm trong contract.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from core.analysis_pipeline import AnalysisPipeline
from core.market_models import Candle
from core.reason_codes import (
    MACRO_AI_VETO,
    MACRO_AI_ADJUSTMENT,
    MACRO_AI_VERDICT_SKIPPED,
)
from core.risk_engine import AnalysisInput
from services.macro_ai_verdict import (
    MacroVerdict,
    MacroVerdictAssessor,
    MacroVerdictCache,
    _ai_fingerprint,
    build_verdict_prompt,
    verdict_cache_key,
)

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


def _candles(n: int, *, bar_minutes: int, start: datetime, step: float = 0.0002) -> list[Candle]:
    result: list[Candle] = []
    price = 1.0800
    t = start
    for i in range(n):
        result.append(
            Candle(
                time=t,
                open=round(price, 5),
                high=round(price + 0.0008, 5),
                low=round(price - 0.0008, 5),
                close=round(price + step, 5),
                volume=float(1000 + i),
            )
        )
        price += step
        t += timedelta(minutes=bar_minutes)
    return result


def _candles_by_timeframe() -> dict[str, list[Candle]]:
    end = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    return {
        "D1": _candles(120, bar_minutes=1440, start=end - timedelta(days=120)),
        "H4": _candles(120, bar_minutes=240, start=end - timedelta(days=20)),
        "H1": _candles(60, bar_minutes=60, start=end - timedelta(days=3)),
        "M15": _candles(60, bar_minutes=15, start=end - timedelta(hours=15)),
    }


def _default_input(symbol: str = "EUR/USD") -> AnalysisInput:
    return AnalysisInput(
        symbol=symbol,
        broker_symbol="EURUSDm",
        account_balance=10_000.0,
        risk_percent=2.0,
        account_currency="USD",
        lot_step=0.01,
        minimum_lot=0.01,
        contract_size_override=100_000.0,
        timezone_name="Asia/Ho_Chi_Minh",
    )


def _assessor_with_temp_storage(tmpdir: str) -> tuple[MacroVerdictAssessor, Path, Path]:
    """Assessor dùng cache/journal trong temp dir (không động vào data/ repo)."""
    cache_dir = Path(tmpdir) / "cache"
    journal_path = Path(tmpdir) / "macro_verdict_journal.jsonl"
    assessor = MacroVerdictAssessor(
        cache=MacroVerdictCache(cache_dir=cache_dir),
        journal_path=journal_path,
    )
    return assessor, cache_dir, journal_path


# ---------------------------------------------------------------------------
# Critical 1 — ai_service nối vào pipeline (integration test qua pipeline thật)
# ---------------------------------------------------------------------------

def test_pipeline_wiring_ai_service_goi_verdict_va_ap_dung():
    """Pipeline thật với ai_service + flag ON + macro_score>=20 → AI được gọi,
    verdict có hiệu lực, reason code xuất hiện, adjustment trừ điểm."""
    with TemporaryDirectory() as tmpdir:
        assessor, cache_dir, journal_path = _assessor_with_temp_storage(tmpdir)
        ai_svc = _mock_ai_service(_valid_verdict_json(
            bias="conflict", conviction=0.9,
            conflicts=["Tier 1 hawkish nhưng DXY giảm"],
            veto=False, adjustment=-3,
        ))

        pipeline = AnalysisPipeline()
        pipeline._macro_ai_assessor = assessor  # test seam
        result = pipeline.execute(
            _default_input(),
            _candles_by_timeframe(),
            data_quality={
                "macro_ai_verdict_enabled": True,
                "spread_status": "normal",
                "event_impact_derate_enabled": False,
            },
            macro_alignment={"buy": 25, "sell": 10},
            ai_service=ai_svc,
            trade_date=T0,
        )

        # AI được gọi đúng 1 lần.
        assert ai_svc.analyze.call_count == 1, "AI phải được gọi qua pipeline"

        # Verdict có hiệu lực: adjustment được áp dụng (trừ > 0 điểm).
        deducted = result["macro"]["macro_ai_deducted"]
        assert deducted >= 1, f"Adjustment -3 phải trừ điểm, deducted={deducted}"

        # Reason code Bước 6 xuất hiện trong danh sách cuối (Major 4).
        assert MACRO_AI_ADJUSTMENT in result["reason_codes"]

        # Cache ghi (file tồn tại) + journal ghi (1 dòng).
        cache_files = list(Path(cache_dir).glob("*.json"))
        assert len(cache_files) == 1, f"Cache phải ghi 1 file, có {len(cache_files)}"
        assert journal_path.exists()


def test_pipeline_wiring_ai_service_none_thi_skip_tu_do():
    """Pipeline có flag ON nhưng ai_service=None → assessor fallback → pipeline
    không áp verdict (reason code rỗng, deductible=0). Không crash."""
    with TemporaryDirectory() as tmpdir:
        assessor, cache_dir, journal_path = _assessor_with_temp_storage(tmpdir)
        pipeline = AnalysisPipeline()
        pipeline._macro_ai_assessor = assessor
        result = pipeline.execute(
            _default_input(),
            _candles_by_timeframe(),
            data_quality={
                "macro_ai_verdict_enabled": True,
                "spread_status": "normal",
            },
            macro_alignment={"buy": 25, "sell": 10},
            ai_service=None,
            trade_date=T0,
        )
        assert result["macro"]["macro_ai_deducted"] == 0
        assert MACRO_AI_ADJUSTMENT not in result["reason_codes"]
        assert result["macro"]["macro_ai_verdict"]["source"] == "fallback"


def test_pipeline_wiring_flag_off_khong_goi_ai():
    """Flag OFF → pipeline không gọi AI (Guard 1)."""
    with TemporaryDirectory() as tmpdir:
        assessor, cache_dir, journal_path = _assessor_with_temp_storage(tmpdir)
        ai_svc = _mock_ai_service(_valid_verdict_json())
        pipeline = AnalysisPipeline()
        pipeline._macro_ai_assessor = assessor
        result = pipeline.execute(
            _default_input(),
            _candles_by_timeframe(),
            data_quality={"spread_status": "normal"},
            macro_alignment={"buy": 25, "sell": 10},
            ai_service=ai_svc,
            trade_date=T0,
        )
        assert ai_svc.analyze.call_count == 0
        assert result["macro"]["macro_ai_verdict"] is None
        assert result["macro"]["macro_ai_deducted"] == 0


# ---------------------------------------------------------------------------
# Critical 2 — macro_verdict_context (tier1/tier2/tier3/v2/stance) tới AI
# ---------------------------------------------------------------------------

def test_pipeline_macro_verdict_context_lot_duoc_forward():
    """macro_verdict_context truyền vào execute → prompt AI nhận dữ liệu đầy đủ."""
    context_pkg = {
        "tier1": {"buy": 9, "sell": 3, "detail": {"fed_rate": "5.25%"}},
        "tier2": {"buy": 4, "sell": 6, "event_risk_level": "high"},
        "tier3": {"buy": 6, "sell": 2},
        "macro_v2": {"buy": 20, "sell": 10, "confidence": 0.7},
        "stance": {"currency": "USD", "stance": "hawkish", "strength": 7},
    }
    captured: dict = {}

    class _CapturingAssessor:
        def assess(self, *, pair, macro_context, ai_service, date_str, best_side,
                   verdict_enabled, is_backtest=False):
            captured["prompt"] = build_verdict_prompt(pair, macro_context, best_side)
            captured["ctx"] = macro_context
            return MacroVerdict(
                pair=pair, date=date_str, bias="aligned", conviction=0.9,
                conflicts=[], veto=False, adjustment=0, evidence=["ok"],
                source="ai", best_side=best_side,
            )

    pipeline = AnalysisPipeline()
    pipeline._macro_ai_assessor = _CapturingAssessor()  # type: ignore[assignment]
    result = pipeline.execute(
        _default_input(),
        _candles_by_timeframe(),
        data_quality={
            "macro_ai_verdict_enabled": True,
            "spread_status": "normal",
        },
        macro_alignment={"buy": 25, "sell": 10},
        ai_service=_mock_ai_service(""),
        macro_verdict_context=context_pkg,
        trade_date=T0,
    )

    # Context AI nhận được chứa dữ liệu tầng đầy đủ (Critical 2 fix).
    ctx = captured["ctx"]
    assert ctx["tier1"].get("buy") == 9
    assert ctx["tier2"].get("event_risk_level") == "high"
    assert ctx["tier3"].get("buy") == 6
    assert ctx["macro_v2"].get("confidence") == 0.7
    assert ctx["stance"].get("stance") == "hawkish"
    # Trường bổ sung của pipeline: alignment + DXY.
    assert ctx["alignment"]["buy"] == 25
    assert "correlation" in ctx


def test_pipeline_dxy_movement_trong_context():
    """DXY candles có trong correlation_context → prompt chứa hướng/% đổi (V6)."""
    captured: dict = {}

    class _CapturingAssessor:
        def assess(self, *, pair, macro_context, ai_service, date_str, best_side,
                   verdict_enabled, is_backtest=False):
            captured["ctx"] = macro_context
            return MacroVerdict(
                pair=pair, date=date_str, bias="aligned", conviction=0.9,
                conflicts=[], veto=False, adjustment=0, evidence=["ok"],
                source="ai", best_side=best_side,
            )

    dxy_candles = _candles(30, bar_minutes=1440,
                           start=T0 - timedelta(days=30), step=0.001)
    pipeline = AnalysisPipeline()
    pipeline._macro_ai_assessor = _CapturingAssessor()  # type: ignore[assignment]
    pipeline.execute(
        _default_input(),
        _candles_by_timeframe(),
        data_quality={
            "macro_ai_verdict_enabled": True,
            "spread_status": "normal",
        },
        macro_alignment={"buy": 25, "sell": 10},
        ai_service=_mock_ai_service(""),
        correlation_context={"dxy_candles": dxy_candles},
        trade_date=T0,
    )

    dxy = captured["ctx"]["correlation"]["dxy"]
    assert dxy["has_data"] is True
    assert dxy["direction"] in ("up", "down", "flat")
    assert "change_pct" in dxy


# ---------------------------------------------------------------------------
# Critical 3 — adjustment trừ thẳng vào component macro (0-30)
# ---------------------------------------------------------------------------

def test_adjustment_tru_truc_tiep_vao_component_macro():
    """Adjustment -N → component macro_alignment của side chọn giảm đúng N điểm,
    signal_score giảm tương ứng (so với chạy không adjustment)."""
    with TemporaryDirectory() as tmpdir:
        # Baseline: adjustment=0
        base_ai = _mock_ai_service(_valid_verdict_json(adjustment=0))
        assessor, cache_dir, _ = _assessor_with_temp_storage(tmpdir)
        pipeline = AnalysisPipeline()
        pipeline._macro_ai_assessor = assessor
        base = pipeline.execute(
            _default_input(),
            _candles_by_timeframe(),
            data_quality={"macro_ai_verdict_enabled": True, "spread_status": "normal"},
            macro_alignment={"buy": 25, "sell": 10},
            ai_service=base_ai,
            trade_date=T0,
        )
        best_side = base["direction_bias"]["best_side"]
        assert best_side in ("buy", "sell")
        base_macro = base["scenario_scores"][best_side]["macro_alignment"]
        base_signal = base["scenario_scores"][best_side]["signal_score"]
        assert base["macro"]["macro_ai_deducted"] == 0

    with TemporaryDirectory() as tmpdir:
        # Adjustment=-3: macro component giảm 3, signal giảm 3.
        adj_ai = _mock_ai_service(_valid_verdict_json(adjustment=-3))
        assessor, cache_dir, _ = _assessor_with_temp_storage(tmpdir)
        pipeline = AnalysisPipeline()
        pipeline._macro_ai_assessor = assessor
        adj = pipeline.execute(
            _default_input(),
            _candles_by_timeframe(),
            data_quality={"macro_ai_verdict_enabled": True, "spread_status": "normal"},
            macro_alignment={"buy": 25, "sell": 10},
            ai_service=adj_ai,
            trade_date=T0,
        )
        best_side = adj["direction_bias"]["best_side"]
        adj_macro = adj["scenario_scores"][best_side]["macro_alignment"]
        adj_signal = adj["scenario_scores"][best_side]["signal_score"]

        assert adj["macro"]["macro_ai_deducted"] == 3
        assert base_macro - adj_macro == 3, f"{base_macro} - {adj_macro} != 3"
        assert base_signal - adj_signal == 3, f"{base_signal} - {adj_signal} != 3"


def test_adjustment_khong_lam_de_setup():
    """Adjustment không bao giờ làm điểm tăng (bất đối xứng): signal_score
    với adjustment<0 ≤ baseline."""
    with TemporaryDirectory() as tmpdir:
        base_ai = _mock_ai_service(_valid_verdict_json(adjustment=0))
        assessor, _, _ = _assessor_with_temp_storage(tmpdir)
        pipeline = AnalysisPipeline()
        pipeline._macro_ai_assessor = assessor
        base = pipeline.execute(
            _default_input(),
            _candles_by_timeframe(),
            data_quality={"macro_ai_verdict_enabled": True, "spread_status": "normal"},
            macro_alignment={"buy": 25, "sell": 10},
            ai_service=base_ai,
            trade_date=T0,
        )
        best_side = base["direction_bias"]["best_side"]
        base_signal = base["scenario_scores"][best_side]["signal_score"]

    with TemporaryDirectory() as tmpdir:
        adj_ai = _mock_ai_service(_valid_verdict_json(adjustment=-5))
        assessor, _, _ = _assessor_with_temp_storage(tmpdir)
        pipeline = AnalysisPipeline()
        pipeline._macro_ai_assessor = assessor
        adj = pipeline.execute(
            _default_input(),
            _candles_by_timeframe(),
            data_quality={"macro_ai_verdict_enabled": True, "spread_status": "normal"},
            macro_alignment={"buy": 25, "sell": 10},
            ai_service=adj_ai,
            trade_date=T0,
        )
        best_side = adj["direction_bias"]["best_side"]
        adj_signal = adj["scenario_scores"][best_side]["signal_score"]
        assert adj_signal <= base_signal


# ---------------------------------------------------------------------------
# Major 4 — reason codes Bước 6 không bị ghi đè
# ---------------------------------------------------------------------------

def test_reason_codes_buoc6_giu_duoc_trong_ket_qua():
    """MACRO_AI_ADJUSTMENT + MACRO_AI_VETO đều có trong reason_codes cuối."""
    with TemporaryDirectory() as tmpdir:
        ai_svc = _mock_ai_service(_valid_verdict_json(
            bias="conflict", conviction=0.9,
            conflicts=["Tier 1 hawkish nhưng DXY giảm"],
            veto=True, adjustment=-2,
        ))
        assessor, _, _ = _assessor_with_temp_storage(tmpdir)
        pipeline = AnalysisPipeline()
        pipeline._macro_ai_assessor = assessor
        result = pipeline.execute(
            _default_input(),
            _candles_by_timeframe(),
            data_quality={"macro_ai_verdict_enabled": True, "spread_status": "normal"},
            macro_alignment={"buy": 25, "sell": 10},
            ai_service=ai_svc,
            trade_date=T0,
        )
        assert MACRO_AI_ADJUSTMENT in result["reason_codes"]
        assert MACRO_AI_VETO in result["reason_codes"]


def test_reason_code_verdict_skipped_khi_conviction_thap():
    """Conviction < 0.7 → MACRO_AI_VERDICT_SKIPPED trong reason_codes."""
    with TemporaryDirectory() as tmpdir:
        ai_svc = _mock_ai_service(_valid_verdict_json(
            conviction=0.5, adjustment=-3,
        ))
        assessor, _, _ = _assessor_with_temp_storage(tmpdir)
        pipeline = AnalysisPipeline()
        pipeline._macro_ai_assessor = assessor
        result = pipeline.execute(
            _default_input(),
            _candles_by_timeframe(),
            data_quality={"macro_ai_verdict_enabled": True, "spread_status": "normal"},
            macro_alignment={"buy": 25, "sell": 10},
            ai_service=ai_svc,
            trade_date=T0,
        )
        assert MACRO_AI_VERDICT_SKIPPED in result["reason_codes"]
        assert result["macro"]["macro_ai_deducted"] == 0


# ---------------------------------------------------------------------------
# Major 5 — backtest read-cache-only
# ---------------------------------------------------------------------------

def test_assessor_backtest_read_cache_khong_kiem_tra_fingerprint():
    """Backtest (is_backtest=True) đọc cache theo (pair,date,side) kể cả khi
    fingerprint khác (cache live ghi bởi AI model khác). Không gọi AI."""
    with TemporaryDirectory() as tmpdir:
        cache = MacroVerdictCache(cache_dir=Path(tmpdir))
        live_verdict = MacroVerdict(
            pair=PAIR, date=TODAY, bias="conflict", conviction=0.9,
            conflicts=["mâu thuẫn"], veto=True, adjustment=-4,
            evidence=["live verdict"], source="ai", best_side="buy",
        )
        cache.put(live_verdict, "live-fingerprint")

        assessor = MacroVerdictAssessor(cache=cache)
        ai_svc = _mock_ai_service(_valid_verdict_json())
        verdict = assessor.assess(
            PAIR, _macro_context(buy=25), ai_svc,
            date_str=TODAY, best_side="buy", verdict_enabled=True,
            is_backtest=True,  # fingerprint của backtest = _ai_fingerprint(None) khác live
        )
        assert verdict.source == "ai"
        assert verdict.veto is True
        assert ai_svc.analyze.call_count == 0, "Backtest tuyệt đối không gọi AI"


def test_assessor_backtest_miss_thi_skip_trung_tinh():
    """Backtest miss cache → skip_backtest_no_cache (trung tính), không gọi AI."""
    with TemporaryDirectory() as tmpdir:
        assessor = MacroVerdictAssessor(cache=MacroVerdictCache(cache_dir=Path(tmpdir)))
        ai_svc = _mock_ai_service(_valid_verdict_json())
        verdict = assessor.assess(
            PAIR, _macro_context(buy=25), ai_svc,
            date_str=TODAY, best_side="buy", verdict_enabled=True,
            is_backtest=True,
        )
        assert verdict.source == "skip_backtest_no_cache"
        assert verdict.veto is False
        assert verdict.adjustment == 0
        assert ai_svc.analyze.call_count == 0


def test_backtest_data_quality_co_flag_macro_ai_verdict():
    """_run_analysis_snapshot gắn macro_ai_verdict_enabled vào data_quality."""
    from core.system_backtest_engine import _run_analysis_snapshot
    from core.system_backtest_engine import BacktestRequest

    request = BacktestRequest(
        symbol="EUR/USD",
        broker_symbol="EURUSD",
        start=T0 - timedelta(days=10),
        end=T0,
        initial_balance=10_000.0,
        risk_percent=1.0,
        macro_ai_verdict_enabled=True,
    )
    candles = {
        "D1": _candles(120, bar_minutes=1440, start=T0 - timedelta(days=120)),
        "H4": _candles(120, bar_minutes=240, start=T0 - timedelta(days=20)),
        "H1": _candles(60, bar_minutes=60, start=T0 - timedelta(days=3)),
    }
    captured: dict = {}

    def _fake_analysis_fn(request, candles, *, data_quality, **kwargs):
        captured["dq"] = data_quality
        return {
            "symbol": request.symbol,
            "pipeline_diagnostics": [],
            "macro": {},
            "final_score": 0,
        }

    _run_analysis_snapshot(
        request, candles, balance=10_000.0, closed_trades=[],
        current_time=T0, analysis_fn=_fake_analysis_fn,
    )
    assert captured["dq"]["macro_ai_verdict_enabled"] is True


# ---------------------------------------------------------------------------
# Major 6 — cache/journal phân biệt best_side
# ---------------------------------------------------------------------------

def test_cache_phan_biet_best_side():
    """Cache key/file path chứa side → best_side khác → miss."""
    with TemporaryDirectory() as tmpdir:
        cache = MacroVerdictCache(cache_dir=Path(tmpdir))
        verdict = MacroVerdict(
            pair=PAIR, date=TODAY, bias="aligned", conviction=0.9,
            conflicts=[], veto=False, adjustment=-2, evidence=["ok"],
            source="ai", best_side="buy",
        )
        cache.put(verdict, "fp1")

        # Cùng pair/date nhưng khác side → miss.
        cached_sell = cache.get(PAIR, TODAY, "fp1", best_side="sell")
        assert cached_sell is None
        # Cùng side → hit.
        cached_buy = cache.get(PAIR, TODAY, "fp1", best_side="buy")
        assert cached_buy is not None
        assert cached_buy.best_side == "buy"

        # File path khác nhau cho 2 side.
        files = sorted(p.name for p in Path(tmpdir).glob("*.json"))
        assert len(files) == 1
        assert "_buy.json" in files[0]


def test_journal_ghi_best_side():
    """Journal record có best_side (để sau này đối chiếu theo hướng)."""
    with TemporaryDirectory() as tmpdir:
        journal_path = Path(tmpdir) / "journal.jsonl"
        assessor = MacroVerdictAssessor(
            cache=MacroVerdictCache(cache_dir=Path(tmpdir) / "cache"),
            journal_path=journal_path,
        )
        ai_svc = _mock_ai_service(_valid_verdict_json(adjustment=-2))
        assessor.assess(
            PAIR, _macro_context(buy=25), ai_svc,
            date_str=TODAY, best_side="sell", verdict_enabled=True,
        )
        lines = [json.loads(l) for l in journal_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 1
        assert lines[0]["best_side"] == "sell"
        assert lines[0]["pair"] == PAIR
        assert lines[0]["date"] == TODAY


# ---------------------------------------------------------------------------
# Major 7 — timeout AI (thread budget)
# ---------------------------------------------------------------------------

def test_assessor_timeout_fallback():
    """AI analyze() chạy lâu hơn timeout → fallback, ai_blocking_time_s ≈ timeout."""
    with TemporaryDirectory() as tmpdir:
        assessor = MacroVerdictAssessor(
            cache=MacroVerdictCache(cache_dir=Path(tmpdir) / "cache"),
            timeout_s=0.05,
        )
        slow_ai = MagicMock()

        def _slow(_prompt, **kwargs):
            time.sleep(0.5)
            return _valid_verdict_json()

        slow_ai.analyze.side_effect = _slow
        slow_ai.config = MagicMock(provider="test", model="test-model")

        verdict = assessor.assess(
            PAIR, _macro_context(buy=25), slow_ai,
            date_str=TODAY, verdict_enabled=True,
        )
        assert verdict.source == "fallback"
        assert verdict.veto is False
        assert verdict.adjustment == 0
        assert abs(verdict.ai_blocking_time_s - 0.05) < 0.05


# ---------------------------------------------------------------------------
# Minor 9 — negative cache (failure được cache TTL ngắn)
# ---------------------------------------------------------------------------

def test_negative_cache_failure_duoc_cache_30_phut():
    """AI hỏng → fallback được cache với TTL ngắn; gọi lại trong TTL không gọi AI."""
    class _FrozenDatetime(datetime):
        _frozen = T0

        @classmethod
        def now(cls, tz=None):
            return cls._frozen

        @classmethod
        def _set(cls, value):
            cls._frozen = value

    with TemporaryDirectory() as tmpdir:
        cache = MacroVerdictCache(cache_dir=Path(tmpdir))
        assessor = MacroVerdictAssessor(cache=cache)

        with patch("services.macro_ai_verdict.datetime", _FrozenDatetime):
            # Lần 1: AI hỏng → fallback + negative cache (cùng fingerprint provider/model).
            bad_ai = _mock_ai_service(RuntimeError("AI down"))
            v1 = assessor.assess(
                PAIR, _macro_context(buy=25), bad_ai,
                date_str=TODAY, verdict_enabled=True,
            )
            assert v1.source == "fallback"
            assert bad_ai.analyze.call_count == 1

            # Lần 2 (cùng fingerprint provider/model, trong TTL): đọc negative cache.
            good_ai = _mock_ai_service(_valid_verdict_json())
            v2 = assessor.assess(
                PAIR, _macro_context(buy=25), good_ai,
                date_str=TODAY, verdict_enabled=True,
            )
            assert v2.source == "fallback"
            assert good_ai.analyze.call_count == 0, "Trong TTL phải đọc negative cache"

            # Lần 3: sau TTL (31 phút) → miss → gọi AI lại.
            _FrozenDatetime._set(T0 + timedelta(minutes=31))
            v3 = assessor.assess(
                PAIR, _macro_context(buy=25), good_ai,
                date_str=TODAY, verdict_enabled=True,
            )
            assert v3.source == "ai"
            assert good_ai.analyze.call_count == 1


# ---------------------------------------------------------------------------
# Minor 11 — diagnostics status hợp lệ khi flag ON
# ---------------------------------------------------------------------------

def test_pipeline_diagnostics_status_hop_le_khi_flag_on():
    """Flag ON + AI trả verdict → mọi status của macro_verdict trong contract."""
    with TemporaryDirectory() as tmpdir:
        ai_svc = _mock_ai_service(_valid_verdict_json(
            bias="conflict", conviction=0.9,
            conflicts=["mâu thuẫn"], veto=True, adjustment=-2,
        ))
        assessor, _, _ = _assessor_with_temp_storage(tmpdir)
        pipeline = AnalysisPipeline()
        pipeline._macro_ai_assessor = assessor
        result = pipeline.execute(
            _default_input(),
            _candles_by_timeframe(),
            data_quality={"macro_ai_verdict_enabled": True, "spread_status": "normal"},
            macro_alignment={"buy": 25, "sell": 10},
            ai_service=ai_svc,
            trade_date=T0,
        )
        diags = result["pipeline_diagnostics"]
        verdict_diags = [d for d in diags if d["step"] == "macro_verdict"]
        assert verdict_diags, "Phải có diag macro_verdict khi flag ON"
        for d in verdict_diags:
            assert d["status"] in ("pass", "fail", "warning", "skip"), d


def test_pipeline_diagnostics_status_hop_le_khi_flag_off():
    """Flag OFF → macro_verdict diag = skip (hợp lệ)."""
    pipeline = AnalysisPipeline()
    result = pipeline.execute(
        _default_input(),
        _candles_by_timeframe(),
        data_quality={"spread_status": "normal"},
        macro_alignment={"buy": 25, "sell": 10},
    )
    diags = result["pipeline_diagnostics"]
    verdict_diags = [d for d in diags if d["step"] == "macro_verdict"]
    assert len(verdict_diags) == 1
    assert verdict_diags[0]["status"] == "skip"


# ---------------------------------------------------------------------------
# Cache key — side trong key (Major 6)
# ---------------------------------------------------------------------------

def test_verdict_cache_key_chua_side():
    """verdict_cache_key khác nhau giữa buy/sell (cùng pair/date/fingerprint)."""
    k_buy = verdict_cache_key("EUR/USD", "2026-08-07", "fp1", best_side="buy")
    k_sell = verdict_cache_key("EUR/USD", "2026-08-07", "fp1", best_side="sell")
    assert k_buy != k_sell
    # Ổn định.
    assert k_buy == verdict_cache_key("EUR/USD", "2026-08-07", "fp1", best_side="buy")