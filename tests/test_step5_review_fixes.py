"""Test Bước 5 — các fix từ báo cáo review (review fixes).

Bao phủ các lỗi đã sửa theo báo cáo "Bước 5 — AI Event Impact Assessment":

1.  CRITICAL: cờ derate/verdict đọc-ghi sống sót qua SettingsService + UI.
2.  MAJOR-1: journal chỉ ghi assessment AI MỚI (dedup theo fresh_ai_keys),
    schema journal 13 trường, reader-side dedup trong validate script.
3.  MAJOR-2: e2e R9 (applied_derate), priced_in refresh >6h, negative cache
    hết hạn, fallback e2e, over-quota không cache.
4.  MINOR-1: floor 0.15 kích hoạt thật (test_step5_floor_kich_hoat_that).
5.  MINOR-2: hết double-derate quanh mốc 4h (tính lại hours từ time_utc).
6.  MINOR-4: chú thích ô decision table không đạt được (high+priced_in 0.91)
    và sự kiện 24-48h không bao giờ bị derate (risk_window ≤ 24).
7.  MINOR-5: confidence gate cap factor ≤ 0.85.

Mọi test đều mock/offline — không network, không MT5 thật.
"""

from __future__ import annotations

import importlib.util
import json
import os
from dataclasses import asdict
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from core.analysis_pipeline import AnalysisPipeline
from core.market_models import Candle
from core.reason_codes import (
    MACRO_DATA_UNAVAILABLE,
    MACRO_HIGH_IMPACT_EVENT_AHEAD,
    MACRO_HIGH_IMPACT_EVENT_NEARBY,
)
from core.risk_engine import AnalysisInput
from services.data_provider import ConnectionStatus
from services.event_impact_assessor import (
    EventImpactAssessment,
    EventImpactAssessor,
    _ai_fingerprint,
    derate_factor,
    make_event_key,
)
from services.news_service import NewsService
from services.settings_service import SettingsService

# Qt offscreen cho test UI (phải set TRƯỚC khi import PyQt6 lần đầu).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

T0 = datetime(2026, 8, 7, 9, 0, 0, tzinfo=UTC)


def _make_event(
    time_utc: str = "2026-08-08T12:00:00Z",
    currency: str = "USD",
    name: str = "FOMC Meeting",
    impact: str = "high",
    hours_until: float = 20.0,
) -> dict:
    return {
        "currency": currency,
        "event": name,
        "impact": impact,
        "time_utc": time_utc,
        "hours_until": hours_until,
        "forecast": "5.25%",
        "previous": "5.00%",
        "actual": "",
    }


def _json_assessment(
    magnitude: str = "high",
    priced_in: str = "not_priced_in",
    direction: str = "currency_up",
    risk: float = 12.0,
    confidence: float = 0.8,
    evidence: tuple[str, ...] = ("forecast lệch lớn so với kỳ trước",),
) -> str:
    return json.dumps(
        {
            "magnitude": magnitude,
            "priced_in": priced_in,
            "expected_direction": direction,
            "risk_window_hours": risk,
            "confidence": confidence,
            "evidence": list(evidence),
        },
        ensure_ascii=False,
    )


class FakeAI:
    """AI giả: đếm lời gọi, trả string dựng sẵn, có chế độ ném exception."""

    def __init__(self, response: str | None = None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.config = SimpleNamespace(provider="test", model="test-model")
        self.call_count = 0

    def analyze(self, prompt: str, max_tokens: int = 300) -> str:
        self.call_count += 1
        if self.error is not None:
            raise self.error
        return self.response or ""


def _noop_stance(currency: str):
    return {"stance": "neutral", "strength": None, "confidence": None, "source": "test"}


def _assessment_dict(
    *,
    currency: str = "USD",
    magnitude: str = "high",
    priced_in: str = "not_priced_in",
    hours_until: float = 6.0,
    time_utc: str | None = None,
    risk_window_hours: float = 24.0,
    ai_confidence: float = 0.8,
    source: str = "ai",
    event_key: str = "review_fix_key",
) -> dict[str, Any]:
    """Payload assessment (dict) cho data_quality. time_utc mặc định = now +
    hours_until để nhất quán với việc pipeline TÍNH LẠI hours từ time_utc."""
    if time_utc is None:
        time_utc = (datetime.now(timezone.utc) + timedelta(hours=hours_until)).isoformat()
    return asdict(
        EventImpactAssessment(
            event_key=event_key,
            currency=currency,
            event_name="NFP",
            time_utc=time_utc,
            hours_until=hours_until,
            magnitude=magnitude,
            priced_in=priced_in,
            expected_direction="two_way",
            risk_window_hours=risk_window_hours,
            ai_confidence=ai_confidence,
            evidence=["forecast lệch"],
            source=source,
        )
    )


def _corr_candle_list(closes: list[float]) -> list[Candle]:
    t = datetime(2026, 6, 10, tzinfo=timezone.utc)
    return [
        Candle(time=t, open=c, high=c, low=c, close=c, volume=0) for c in closes
    ]


def _full_correlation_context() -> dict[str, Any]:
    """Đủ 4 nguồn correlation → không bị derate thiếu dữ liệu (0.4/0.8)."""
    return {
        "dxy_candles": _corr_candle_list([100.0, 100.5]),
        "vix_candles": _corr_candle_list([18.0, 18.5]),
        "us10y_candles": _corr_candle_list([4.2, 4.3]),
        "us2y_candles": _corr_candle_list([4.0, 4.1]),
    }


def _pipe_for_step5(
    *,
    derate_enabled: bool = True,
    assessments: list[dict[str, Any]] | None = None,
    next_high_impact_event: dict[str, Any] | None = None,
    confidence_in: float = 1.0,
    correlation: dict[str, Any] | None = None,
) -> AnalysisPipeline:
    """Pipeline đã gắn đủ state để chạy _step_compute_correlation()."""
    pipe = AnalysisPipeline()
    pipe._diag = []
    pipe._request = AnalysisInput(
        symbol="EUR/USD",
        broker_symbol="EURUSDm",
        account_balance=10_000.0,
        risk_percent=2.0,
        account_currency="USD",
        lot_step=0.01,
        minimum_lot=0.01,
        contract_size_override=100_000.0,
        timezone_name="Asia/Ho_Chi_Minh",
    )
    pipe._correlation_context = (
        _full_correlation_context() if correlation is None else correlation
    )
    pipe._macro_confidence_in = confidence_in
    pipe._macro_data_reason_code = None
    pipe._macro_event_reason_code = None
    pipe._macro_event_ahead_assessment = None
    pipe._macro_event_ahead_reason_code = None
    pipe._macro_event_ahead_derate_factor = None
    dq: dict[str, Any] = {
        "event_impact_derate_enabled": derate_enabled,
        "upcoming_event_assessments": assessments or [],
    }
    if next_high_impact_event is not None:
        dq["next_high_impact_event"] = next_high_impact_event
    pipe._data_quality = dq
    return pipe


# Nến tổng hợp tối thiểu cho AnalysisPipeline.execute() (đủ route).

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


def _execute_input() -> AnalysisInput:
    return AnalysisInput(
        symbol="EUR/USD",
        broker_symbol="EURUSDm",
        account_balance=10_000.0,
        risk_percent=2.0,
        account_currency="USD",
        lot_step=0.01,
        minimum_lot=0.01,
        contract_size_override=100_000.0,
        timezone_name="Asia/Ho_Chi_Minh",
    )


def _snapshot_with_event(time_utc: str, hours_until: float) -> Any:
    return type(
        "FakeSnapshot",
        (),
        {
            "calendar_payload": {
                "source": "test",
                "events": [
                    {
                        "currency": "USD",
                        "event": "FOMC Meeting",
                        "impact": "high",
                        "time_utc": time_utc,
                        "hours_until": hours_until,
                        "forecast": "5.25%",
                        "previous": "5.00%",
                        "actual": "",
                    }
                ],
                "warning": "",
            },
            "global_headlines": ({"title": "Fed hikes rate sharply"},),
            "fetched_at_utc": T0,
            "expires_at_utc": T0 + timedelta(minutes=5),
        },
    )()


def _write_settings_file(path: Path, advanced: dict[str, Any]) -> None:
    path.write_text(json.dumps({"advanced": advanced}), encoding="utf-8")


@pytest.fixture
def reset_flag_cache():
    """Reset cache cờ advanced của NewsService trước/sau test."""
    NewsService._advanced_flag_cache = None
    yield
    NewsService._advanced_flag_cache = None


# ---------------------------------------------------------------------------
# Nhóm 1 — CRITICAL: cờ flag đọc/ghi qua SettingsService thật (không mock)
# ---------------------------------------------------------------------------

def test_settings_service_roundtrip_hai_flag(tmp_path):
    """Flag Bước 5 + Bước 6 phải đọc được từ settings.json và sống sót qua save."""
    path = tmp_path / "settings.json"

    # Mặc định khi chưa có file: cả 2 cờ TẮT.
    defaults = SettingsService(path).load()
    assert defaults.advanced.event_impact_derate_enabled is False
    assert defaults.advanced.macro_ai_verdict_enabled is False

    # File có cờ BẬT → load phải thấy BẬT (lỗi cũ: _load bỏ qua 2 cờ này).
    _write_settings_file(
        path,
        {"event_impact_derate_enabled": True, "macro_ai_verdict_enabled": True},
    )
    loaded = SettingsService(path).load()
    assert loaded.advanced.event_impact_derate_enabled is True
    assert loaded.advanced.macro_ai_verdict_enabled is True

    # Save (không đụng 2 cờ) → reload vẫn BẬT (lỗi cũ: save rebuild về mặc định).
    SettingsService(path).save(loaded)
    reloaded = SettingsService(path).load()
    assert reloaded.advanced.event_impact_derate_enabled is True
    assert reloaded.advanced.macro_ai_verdict_enabled is True


def test_settings_service_save_khong_reset_api_keys_va_co_carry_over(tmp_path):
    """brave/fred API keys cũng từng bị reset khi save — phải carry-over."""
    path = tmp_path / "settings.json"
    _write_settings_file(
        path,
        {
            "brave_api_key": "brave-x",
            "fred_api_key": "fred-y",
            "event_impact_derate_enabled": True,
            "macro_ai_verdict_enabled": False,
        },
    )
    loaded = SettingsService(path).load()
    assert loaded.advanced.brave_api_key == "brave-x"
    assert loaded.advanced.fred_api_key == "fred-y"

    SettingsService(path).save(loaded)
    reloaded = SettingsService(path).load()
    assert reloaded.advanced.brave_api_key == "brave-x"
    assert reloaded.advanced.fred_api_key == "fred-y"
    assert reloaded.advanced.event_impact_derate_enabled is True
    assert reloaded.advanced.macro_ai_verdict_enabled is False


def test_data_quality_flags_doc_flag_tu_settings_file_that(
    tmp_path, monkeypatch, reset_flag_cache
):
    """R9: data_quality_flags phải trả cờ đọc TỪ FILE (qua SettingsService thật),
    không hardcode False. Kèm kiểm tra TTL cache của _read_advanced_flags."""
    settings_file = tmp_path / "settings.json"
    _write_settings_file(
        settings_file,
        {"event_impact_derate_enabled": True, "macro_ai_verdict_enabled": True},
    )
    monkeypatch.setattr(
        "services.settings_service.settings_path", lambda: settings_file
    )

    svc = NewsService()
    with patch.object(
        svc,
        "latest_macro_context",
        return_value={"events": [], "source": "test", "warning": ""},
    ):
        flags = svc.data_quality_flags("EUR/USD")
    assert flags["event_impact_derate_enabled"] is True
    assert flags["macro_ai_verdict_enabled"] is True

    # TTL cache: đổi file mà chưa reset cache → giá trị cũ còn hiệu lực.
    _write_settings_file(
        settings_file,
        {"event_impact_derate_enabled": False, "macro_ai_verdict_enabled": False},
    )
    assert NewsService._read_derate_enabled() is True
    # Reset cache → đọc giá trị mới.
    NewsService._advanced_flag_cache = None
    assert NewsService._read_derate_enabled() is False
    assert NewsService._read_macro_verdict_enabled() is False

    # Khóa mutation: data_quality_flags() cũng phải trả False khi file ghi False —
    # không chỉ các reader nội bộ. Nếu data_quality_flags hardcode True cho 2 cờ
    # (thay vì ủy quyền cho reader), assertion này sẽ bắt được.
    with patch.object(
        svc,
        "latest_macro_context",
        return_value={"events": [], "source": "test", "warning": ""},
    ):
        flags_off = svc.data_quality_flags("EUR/USD")
    assert flags_off["event_impact_derate_enabled"] is False
    assert flags_off["macro_ai_verdict_enabled"] is False


def test_read_advanced_flags_fail_closed_file_hong(tmp_path, monkeypatch, reset_flag_cache):
    """File settings hỏng → fail-closed (False, False), không ném exception."""
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{json hỏng", encoding="utf-8")
    monkeypatch.setattr(
        "services.settings_service.settings_path", lambda: settings_file
    )
    assert NewsService._read_advanced_flags() == (False, False)


# ---------------------------------------------------------------------------
# Nhóm 2 — MAJOR-2/R9: e2e AnalysisPipeline.execute() → applied_derate nhìn thấy
# ---------------------------------------------------------------------------

def test_e2e_r9_flag_on_applied_derate_va_reason_code():
    """Flag BẬT + assessment high/not_priced_in 6h → execute() trả
    applied_derate trong payload + reason code MACRO_HIGH_IMPACT_EVENT_AHEAD
    (chuỗi R9: UI đọc đúng 2 field này để hiển thị cảnh báo)."""
    payload = _assessment_dict(hours_until=6.0)
    result = AnalysisPipeline().execute(
        _execute_input(),
        _candles_by_timeframe(),
        data_quality={
            "event_impact_derate_enabled": True,
            "upcoming_event_assessments": [payload],
        },
        macro_confidence=1.0,
    )
    assessments = result["macro"]["event_assessments"]
    assert len(assessments) == 1
    assert assessments[0]["applied_derate"] == pytest.approx(0.70)
    assert MACRO_HIGH_IMPACT_EVENT_AHEAD in result["reason_codes"]
    # Thiếu correlation (×0.4) rồi derate (×0.70) → 0.28.
    assert result["macro"]["macro_confidence"] == pytest.approx(0.28)


def test_e2e_r9_flag_off_applied_derate_none():
    """Flag TẮT → payload vẫn có assessment nhưng applied_derate=None,
    không có reason code, confidence không bị derate."""
    payload = _assessment_dict(hours_until=6.0)
    result = AnalysisPipeline().execute(
        _execute_input(),
        _candles_by_timeframe(),
        data_quality={
            "event_impact_derate_enabled": False,
            "upcoming_event_assessments": [payload],
        },
        macro_confidence=1.0,
    )
    assessments = result["macro"]["event_assessments"]
    assert len(assessments) == 1
    assert assessments[0]["applied_derate"] is None
    assert MACRO_HIGH_IMPACT_EVENT_AHEAD not in result["reason_codes"]
    # Chỉ còn derate thiếu correlation (×0.4), không có derate Bước 5.
    assert result["macro"]["macro_confidence"] == pytest.approx(0.4)


def test_e2e_fallback_assessment_derate_0_85():
    """Fallback (AI chết — medium/unknown) đi qua pipeline thật vẫn derate 0.85
    (fail-closed D6: có sự kiện trong cửa sổ thì không bao giờ nhẹ hơn 0.85)."""
    payload = _assessment_dict(
        magnitude="medium", priced_in="unknown", source="fallback", hours_until=6.0
    )
    result = AnalysisPipeline().execute(
        _execute_input(),
        _candles_by_timeframe(),
        data_quality={
            "event_impact_derate_enabled": True,
            "upcoming_event_assessments": [payload],
        },
        macro_confidence=1.0,
    )
    assessments = result["macro"]["event_assessments"]
    assert assessments[0]["applied_derate"] == pytest.approx(0.85)
    assert MACRO_HIGH_IMPACT_EVENT_AHEAD in result["reason_codes"]
    assert result["macro"]["macro_confidence"] == pytest.approx(0.4 * 0.85)


# ---------------------------------------------------------------------------
# Nhóm 3 — MAJOR-1: nhánh refresh khi priced_in hết hạn 6h
# ---------------------------------------------------------------------------

def test_cache_priced_in_stale_refresh_goi_lai_ai():
    """Cache hit nhưng priced_in >6h → gọi AI refresh, key vào fresh_ai_keys
    (để được ghi journal), cache cập nhật assessment mới."""
    assessor = EventImpactAssessor()
    fake_ai = FakeAI(_json_assessment(priced_in="priced_in", confidence=0.85))
    event = _make_event(hours_until=20.0)
    key = make_event_key(event)
    fp = _ai_fingerprint(fake_ai)

    cached = EventImpactAssessment(
        event_key=key,
        currency="USD",
        event_name="FOMC Meeting",
        time_utc=event["time_utc"],
        hours_until=20.0,
        magnitude="high",
        priced_in="not_priced_in",
        expected_direction="currency_up",
        risk_window_hours=12.0,
        ai_confidence=0.8,
        evidence=["cũ"],
        source="ai",
    )
    assessor.cache.put(key, fp, cached, T0)

    # T0+7h: static TTL 20h còn hạn, priced_in TTL 6h đã stale.
    results, fresh_keys = assessor.assess_upcoming_events(
        [event], fake_ai, _noop_stance, {}, now=T0 + timedelta(hours=7)
    )
    assert fake_ai.call_count == 1, "priced_in stale phải gọi AI refresh"
    assert len(results) == 1
    assert results[0].priced_in == "priced_in", "assessment phải lấy giá trị mới từ AI"
    assert results[0].source == "ai"
    assert key in fresh_keys, "nhánh refresh phải tính là assessment AI mới"
    # Cache đã cập nhật: đọc lại ngay sau đó không stale nữa.
    got = assessor.cache.get(key, fp, T0 + timedelta(hours=7))
    assert got is not None
    new_cached, stale = got
    assert new_cached.priced_in == "priced_in"
    assert stale is False


def test_cache_priced_in_stale_het_quota_khong_goi_ai():
    """priced_in stale nhưng hết quota AI → KHÔNG gọi AI, KHÔNG ghi fresh key,
    chỉ cập nhật hours_until từ event hiện tại."""
    assessor = EventImpactAssessor()
    fake_ai = FakeAI(_json_assessment())
    event = _make_event(hours_until=19.5)
    key = make_event_key(event)
    fp = _ai_fingerprint(fake_ai)

    cached = EventImpactAssessment(
        event_key=key,
        currency="USD",
        event_name="FOMC Meeting",
        time_utc=event["time_utc"],
        hours_until=20.0,
        magnitude="high",
        priced_in="not_priced_in",
        expected_direction="currency_up",
        risk_window_hours=12.0,
        ai_confidence=0.8,
        evidence=["cũ"],
        source="ai",
    )
    assessor.cache.put(key, fp, cached, T0)

    results, fresh_keys = assessor.assess_upcoming_events(
        [event], fake_ai, _noop_stance, {}, now=T0 + timedelta(hours=7), max_ai_calls=0
    )
    assert fake_ai.call_count == 0, "hết quota không được gọi AI"
    assert fresh_keys == set()
    assert len(results) == 1
    assert results[0].priced_in == "not_priced_in", "không refresh → giữ giá trị cũ"
    assert results[0].hours_until == pytest.approx(19.5), "hours_until phải cập nhật từ event"


# ---------------------------------------------------------------------------
# Nhóm 4 — MAJOR-1: journal thật 13 trường + dedup giữa 2 chu kỳ preload
# ---------------------------------------------------------------------------

JOURNAL_FIELDS = {
    "timestamp_utc",
    "event_key",
    "currency",
    "event_name",
    "time_utc",
    "hours_until",
    "magnitude",
    "priced_in",
    "expected_direction",
    "risk_window_hours",
    "ai_confidence",
    "evidence",
    "source",
}


def test_journal_schema_13_truong_va_dedup_hai_chu_ky(tmp_path):
    """Ghi journal qua code THẬT (không patch _journal_event_assessment):
    dòng đầu đủ 13 trường; chu kỳ 2 (cache hit) KHÔNG ghi thêm dòng."""
    journal_path = tmp_path / "event_assessment_journal.jsonl"
    svc = NewsService()
    fake_ai = FakeAI(_json_assessment(magnitude="high", priced_in="not_priced_in"))
    snapshot = _snapshot_with_event(time_utc="2026-08-08T12:00:00Z", hours_until=20.0)

    with patch.object(svc, "_event_journal_path", return_value=journal_path):
        # Chu kỳ 1: AI được gọi → ghi 1 dòng.
        svc._preload_event_impact_assessments(
            snapshot, ai_service=fake_ai, performance_tracker=None, now=T0
        )
        lines = journal_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1, "chu kỳ đầu phải ghi đúng 1 dòng journal"
        line = json.loads(lines[0])
        assert set(line.keys()) == JOURNAL_FIELDS
        assert line["source"] == "ai"
        assert line["currency"] == "USD"
        assert line["magnitude"] == "high"
        assert line["priced_in"] == "not_priced_in"
        assert isinstance(line["evidence"], list)
        assert line["event_key"] == make_event_key(
            {"currency": "USD", "event": "FOMC Meeting", "time_utc": "2026-08-08T12:00:00Z"}
        )

        # Chu kỳ 2: cache hit (source vẫn "ai") → KHÔNG ghi thêm.
        svc._preload_event_impact_assessments(
            snapshot, ai_service=fake_ai, performance_tracker=None, now=T0
        )
        lines2 = journal_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines2) == 1, "cache hit không được ghi trùng journal"
    assert fake_ai.call_count == 1, "chu kỳ 2 phải dùng cache, không gọi AI lại"


# ---------------------------------------------------------------------------
# Nhóm 5 — validate_event_assessment.py: helper dedup + report không phóng to
# ---------------------------------------------------------------------------

def _load_validate_module():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "validate_event_assessment", root / "scripts" / "validate_event_assessment.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_validate_script_latest_by_event_key():
    mod = _load_validate_module()
    entries = [
        {"event_key": "a", "priced_in": "unknown"},
        {"event_key": "b", "priced_in": "partial"},
        {"event_key": "a", "priced_in": "priced_in"},
        {"no_key": 1},
    ]
    out = mod._latest_by_event_key(entries)
    assert len(out) == 2
    by_key = {e["event_key"]: e for e in out}
    assert by_key["a"]["priced_in"] == "priced_in", "dòng muộn nhất phải thắng"
    assert by_key["b"]["priced_in"] == "partial"


def test_validate_script_report_dedup_khong_phong_to_ma_tran(tmp_path, capsys):
    """3 dòng trùng event_key trong journal (tàn dư trước khi có dedup) →
    report chỉ đếm 1 event theo dự đoán mới nhất."""
    mod = _load_validate_module()
    journal_path = tmp_path / "journal.jsonl"
    labels_path = tmp_path / "labels.jsonl"

    entry = {
        "timestamp_utc": "2026-08-01T09:00:00+00:00",
        "event_key": "evk1",
        "currency": "USD",
        "event_name": "NFP",
        "time_utc": "2026-08-01T12:00:00Z",
        "hours_until": 3.0,
        "magnitude": "high",
        "priced_in": "priced_in",
        "expected_direction": "currency_up",
        "risk_window_hours": 12.0,
        "ai_confidence": 0.8,
        "evidence": ["tin cũ"],
        "source": "ai",
    }
    with open(journal_path, "w", encoding="utf-8") as fh:
        for _ in range(3):
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    label = {
        "event_key": "evk1",
        "actual_priced_in": "yes",
        "direction_correct": "yes",
        "volatile": "yes",
    }
    with open(labels_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(label, ensure_ascii=False) + "\n")

    assert mod._report(journal_path, labels_path) == 0
    out = capsys.readouterr().out
    assert "Tổng sự kiện đã diễn ra: 1" in out, "3 dòng trùng chỉ được đếm 1 event"
    assert "Đã label: 1" in out
    assert "1/1 (100.0%)" in out


# ---------------------------------------------------------------------------
# Nhóm 6 — MAJOR-2: negative cache hết hạn sau 30 phút
# ---------------------------------------------------------------------------

def test_negative_cache_hit_29p_miss_31p():
    """AI lỗi → fallback vào negative cache: còn hạn ở 29 phút, hết hạn ở 31 phút."""
    assessor = EventImpactAssessor()
    fake_ai = FakeAI(error=RuntimeError("AI down"))
    event = _make_event(hours_until=20.0)
    key = make_event_key(event)
    fp = _ai_fingerprint(fake_ai)

    results, fresh_keys = assessor.assess_upcoming_events(
        [event], fake_ai, _noop_stance, {}, now=T0
    )
    assert len(results) == 1
    assert results[0].source == "fallback"
    assert key in fresh_keys, "lời gọi AI lỗi vẫn tính là vừa gọi AI thật"

    hit = assessor.cache.get(key, fp, T0 + timedelta(minutes=29))
    assert hit is not None, "29 phút: negative cache phải còn hạn"
    assert hit[0].source == "fallback"

    miss = assessor.cache.get(key, fp, T0 + timedelta(minutes=31))
    assert miss is None, "31 phút: negative cache phải hết hạn"


# ---------------------------------------------------------------------------
# Nhóm 7 — MAJOR-2: event hết quota KHÔNG được cache (invariant)
# ---------------------------------------------------------------------------

def test_event_over_quota_khong_duoc_cache():
    """Event bị bỏ qua vì hết quota → KHÔNG put cache: chu kỳ sau quota hồi
    phải được gọi AI ngay, không ăn fallback cũ."""
    assessor = EventImpactAssessor()
    fake_ai = FakeAI(_json_assessment())
    event = _make_event(hours_until=20.0)
    key = make_event_key(event)
    fp = _ai_fingerprint(fake_ai)

    results, fresh_keys = assessor.assess_upcoming_events(
        [event], fake_ai, _noop_stance, {}, now=T0, max_ai_calls=0
    )
    assert len(results) == 1
    assert results[0].source == "fallback"
    assert fresh_keys == set()
    assert fake_ai.call_count == 0
    assert assessor.cache.get(key, fp, T0) is None, (
        "event over-quota không được cache — invariant của thiết kế D7"
    )


# ---------------------------------------------------------------------------
# Nhóm 8 — MINOR-1: floor 0.15 kích hoạt thật (luôn áp dụng, kể cả flag OFF)
# ---------------------------------------------------------------------------

def test_step5_floor_kich_hoat_that():
    """0.30 × 0.4 (thiếu toàn bộ correlation) = 0.12 → floor nâng lên 0.15.
    Floor áp VÔ ĐIỀU KIỆN — kể cả khi cờ Bước 5 tắt (chủ đích Prompt 4,
    ngoại lệ duy nhất với lời hứa 'flag tắt → không đổi')."""
    for flag in (True, False):
        pipe = _pipe_for_step5(
            derate_enabled=flag,
            assessments=[],
            confidence_in=0.30,
            correlation={},  # thiếu toàn bộ → ×0.4
        )
        pipe._step_compute_correlation()
        assert pipe._macro_confidence_in == pytest.approx(0.15), (
            f"floor phải nâng 0.12 lên 0.15 khi flag={flag}"
        )
        assert pipe._macro_data_reason_code == MACRO_DATA_UNAVAILABLE


# ---------------------------------------------------------------------------
# Nhóm 9 — MINOR-2: hết double-derate quanh mốc 4h
# ---------------------------------------------------------------------------

def test_double_derate_4h_boundary_chi_step3_no():
    """Tái hiện bug: payload hours_until=4.03 (stale ≤5 phút) nhưng time_utc thật
    chỉ còn 3.96h → cả Bước 3 (0.5, 4.0] lẫn Bước 5 (4.0, 48] cùng thấy event.
    Fix: pipeline tính lại hours từ time_utc trước derate → CHỈ Bước 3 nổ."""
    now = datetime.now(timezone.utc)
    time_utc = (now + timedelta(hours=3.96)).isoformat()
    payload = _assessment_dict(hours_until=4.03, time_utc=time_utc)

    pipe = _pipe_for_step5(
        assessments=[payload],
        next_high_impact_event={"currency": "USD", "impact": "high", "time_utc": time_utc},
    )
    pipe._step_compute_correlation()

    # Bước 3 nổ: ×0.8.
    assert pipe._macro_confidence_in == pytest.approx(0.8)
    assert pipe._macro_event_reason_code == MACRO_HIGH_IMPACT_EVENT_NEARBY
    # Bước 5 KHÔNG nổ thêm (không có ×0.70 kép → conf không phải 0.56).
    assert pipe._macro_event_ahead_reason_code is None
    assert pipe._macro_event_ahead_derate_factor is None


def test_boundary_stale_thap_hon_4h_selection_bo_qua_an_toan():
    """Hướng ngược lại: event thật 4.5h nhưng payload stale ghi 3.97h →
    select_dominant_assessment loại (≤4) → không derate. Mất derate ~5 phút
    quanh mốc 4h là hướng an toàn (không phạt oan), được chấp nhận."""
    now = datetime.now(timezone.utc)
    time_utc = (now + timedelta(hours=4.5)).isoformat()
    payload = _assessment_dict(hours_until=3.97, time_utc=time_utc)

    pipe = _pipe_for_step5(
        assessments=[payload],
        next_high_impact_event={"currency": "USD", "impact": "high", "time_utc": time_utc},
    )
    pipe._step_compute_correlation()

    # Bước 3: 4.5h ngoài cửa sổ (0.5, 4.0] → không nổ.
    assert pipe._macro_event_reason_code is None
    # Bước 5: payload 3.97 ≤ 4 → không được chọn → cũng không nổ.
    assert pipe._macro_event_ahead_reason_code is None
    assert pipe._macro_confidence_in == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Nhóm 10 — MINOR-5: confidence gate cap ≤ 0.85
# ---------------------------------------------------------------------------

def _gate_assessment(magnitude: str, priced_in: str, confidence: float, hours: float) -> EventImpactAssessment:
    return EventImpactAssessment(
        event_key="gate",
        currency="USD",
        event_name="NFP",
        time_utc="",
        hours_until=hours,
        magnitude=magnitude,
        priced_in=priced_in,
        expected_direction="two_way",
        risk_window_hours=24.0,
        ai_confidence=confidence,
        evidence=["x"],
        source="ai",
    )


def test_confidence_gate_cap_0_85_low_magnitude():
    """low/not_priced_in @20h + conf 0.3: không gate thì 0.95 — quá nhẹ so với
    AI chết hẳn (0.85). Gate phải cap về 0.85. (Chọn hours ≤ 24 vì
    risk_window_hours bị parser cap ≤ 24 — hours > 24 không bao giờ derate.)"""
    assessment = _gate_assessment("low", "not_priced_in", 0.3, 20.0)
    assert derate_factor(assessment, 20.0) == pytest.approx(0.85)


def test_confidence_gate_cap_0_85_medium_partial():
    """medium/partial @20h + conf 0.4: raw 1 - 0.15×0.6 = 0.91 → cap 0.85."""
    assessment = _gate_assessment("medium", "partial", 0.4, 20.0)
    assert derate_factor(assessment, 20.0) == pytest.approx(0.85)


def test_confidence_gate_khong_kich_hoat_khi_ai_chet():
    """ai_confidence=None (AI không trả được) → gate KHÔNG kích hoạt:
    giữ hệ số bảng decision gốc (low/not_priced_in @20h = 0.95)."""
    assessment = EventImpactAssessment(
        event_key="gate",
        currency="USD",
        event_name="NFP",
        time_utc="",
        hours_until=20.0,
        magnitude="low",
        priced_in="not_priced_in",
        expected_direction="two_way",
        risk_window_hours=24.0,
        ai_confidence=None,
        evidence=["x"],
        source="ai",
    )
    assert derate_factor(assessment, 20.0) == pytest.approx(0.95)


# ---------------------------------------------------------------------------
# Nhóm 11 — MINOR-4: chú thích ô decision table không đạt được trong thực tế
# ---------------------------------------------------------------------------

def test_minor4_o_high_priced_in_091_khong_dat_duoc_qua_pipeline():
    """CHÚ THÍCH (minor-4): ô "high + priced_in → 0.91" của bảng decision KHÔNG
    BAO GIỜ được áp trong thực tế:
    - hours ≤ 24h → backstop kẹp factor về ≤ 0.85 (0.91 bị kẹp);
    - hours > 24h → risk_window_hours bị parser cap ≤ 24 nên
      hours_until > risk_window → factor 1.0 (không derate).
    Sự kiện 24-48h vì vậy chỉ được đánh giá + cảnh báo, KHÔNG derate.
    Số 0.91 chỉ tồn tại trong công thức `1 - 0.30 × 0.3`, không phải output
    của derate_factor()."""
    # ≤24h: công thức raw là 0.91 nhưng backstop kẹp về 0.85.
    high_priced = _gate_assessment("high", "priced_in", 0.9, 20.0)
    assert derate_factor(high_priced, 20.0) == pytest.approx(0.85)

    # >24h (risk_window max 24): ngoài cửa sổ rủi ro → 1.0, không derate.
    high_far = _gate_assessment("high", "priced_in", 0.9, 30.0)
    assert derate_factor(high_far, 30.0) == pytest.approx(1.0)

    # Đối chứng: cùng hours ≤24h mà not_priced_in thì derate thật (0.70) —
    # chỉ ô priced_in là "hụt" vì backstop.
    high_not_priced = _gate_assessment("high", "not_priced_in", 0.9, 20.0)
    assert derate_factor(high_not_priced, 20.0) == pytest.approx(0.70)


# ---------------------------------------------------------------------------
# Nhóm 12 — CRITICAL (UI): cờ flag bật/tắt được từ SettingsScreen và sống sót
# ---------------------------------------------------------------------------

class _StubMT5:
    """MT5 giả đủ cho SettingsScreen build UI (không kết nối thật)."""

    def connect(self):
        return None

    def connection_status(self) -> ConnectionStatus:
        return ConnectionStatus(
            initialized=False,
            connected=False,
            logged_in=False,
            trade_allowed=False,
            provider_name="stub",
        )

    def account_balance(self):
        return None


class _StubCatalog:
    """Catalog AI giả — không đọc disk."""

    def load(self) -> dict[str, list[str]]:
        return {}

    def refresh_models(self, *args, **kwargs):
        return []


_QAPP = None  # giữ reference toàn cục — QApplication bị GC khi còn widget sẽ crash


def _ensure_qapp():
    """QApplication chỉ tạo 1 lần và GIỮ REFERENCE (PyQt6 crash nếu QApplication
    bị GC trong khi widget còn sống)."""
    global _QAPP
    from PyQt6.QtWidgets import QApplication

    if QApplication.instance() is None:
        _QAPP = QApplication([])
    return QApplication.instance()


def _make_settings_screen(settings_file: Path):
    from ui.screens.settings_screen import SettingsScreen

    stub_app = SimpleNamespace(
        settings_service=SettingsService(settings_file),
        ai_catalog_service=_StubCatalog(),
        mt5=_StubMT5(),
    )
    return SettingsScreen(app=stub_app)


def test_ui_settings_screen_flag_roundtrip(tmp_path):
    """Bật 2 cờ trong UI → lưu → reload file thấy BẬT (R1/R2 của báo cáo)."""
    _ensure_qapp()
    settings_file = tmp_path / "settings.json"
    screen = _make_settings_screen(settings_file)

    assert screen.advanced_derate_input.isChecked() is False
    assert screen.advanced_macro_verdict_input.isChecked() is False

    screen.advanced_derate_input.setChecked(True)
    screen.advanced_macro_verdict_input.setChecked(True)
    screen._save_advanced_settings()

    reloaded = SettingsService(settings_file).load()
    assert reloaded.advanced.event_impact_derate_enabled is True
    assert reloaded.advanced.macro_ai_verdict_enabled is True


def test_ui_settings_screen_save_khong_reset_flag_da_bat(tmp_path):
    """Tái hiện CRITICAL bug: file có cờ BẬT + API keys, người dùng lưu cài đặt
    nâng cao (không đụng checkbox) → cờ và keys KHÔNG bị reset về mặc định."""
    _ensure_qapp()
    settings_file = tmp_path / "settings.json"
    _write_settings_file(
        settings_file,
        {
            "event_impact_derate_enabled": True,
            "macro_ai_verdict_enabled": True,
            "brave_api_key": "brave-secret",
            "fred_api_key": "fred-secret",
        },
    )
    screen = _make_settings_screen(settings_file)

    # UI phản ánh đúng trạng thái file: checkbox BẬT.
    assert screen.advanced_derate_input.isChecked() is True
    assert screen.advanced_macro_verdict_input.isChecked() is True

    # Lưu mà không đụng checkbox (kịch bản bug: rebuild AdvancedSettings thiếu cờ).
    screen._save_advanced_settings()

    reloaded = SettingsService(settings_file).load()
    assert reloaded.advanced.event_impact_derate_enabled is True
    assert reloaded.advanced.macro_ai_verdict_enabled is True
    assert reloaded.advanced.brave_api_key == "brave-secret"
    assert reloaded.advanced.fred_api_key == "fred-secret"


def test_ui_settings_screen_tat_co_luu_duoc(tmp_path):
    """Đổi cờ BẬT → TẮT trong UI rồi lưu phải ra TẮT (chiều ngược lại)."""
    _ensure_qapp()
    settings_file = tmp_path / "settings.json"
    _write_settings_file(
        settings_file,
        {"event_impact_derate_enabled": True, "macro_ai_verdict_enabled": True},
    )
    screen = _make_settings_screen(settings_file)
    screen.advanced_derate_input.setChecked(False)
    screen.advanced_macro_verdict_input.setChecked(False)
    screen._save_advanced_settings()

    reloaded = SettingsService(settings_file).load()
    assert reloaded.advanced.event_impact_derate_enabled is False
    assert reloaded.advanced.macro_ai_verdict_enabled is False
