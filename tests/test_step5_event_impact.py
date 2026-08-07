"""Test Bước 5 — module AI Event Impact Assessment (services/event_impact_assessor.py).

Bao phủ: parser + validate JSON (nhóm A), decision table (nhóm B), cache 2 tầng
TTL (nhóm C), orchestrator fail-closed (nhóm D).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from services.event_impact_assessor import (
    AI_CONFIDENCE_GATE,
    DERATE_FLOOR,
    DERATE_CEIL,
    EventImpactAssessment,
    EventImpactAssessmentCache,
    EventImpactAssessor,
    _ai_fingerprint,
    build_event_prompt,
    derate_factor,
    make_event_key,
    parse_ai_event_json,
    select_dominant_assessment,
)

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
    forecast: str = "5.25%",
    previous: str = "5.00%",
) -> dict:
    return {
        "currency": currency,
        "event": name,
        "impact": impact,
        "time_utc": time_utc,
        "hours_until": hours_until,
        "forecast": forecast,
        "previous": previous,
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


def _make_assessment(
    event: dict,
    magnitude: str = "high",
    priced_in: str = "not_priced_in",
    risk: float = 48.0,
    direction: str = "currency_up",
    confidence: float = 0.8,
    source: str = "ai",
) -> EventImpactAssessment:
    return EventImpactAssessment(
        event_key=make_event_key(event),
        currency=str(event["currency"]).strip().upper(),
        event_name=str(event["event"]),
        time_utc=str(event["time_utc"]),
        hours_until=float(event["hours_until"]),
        magnitude=magnitude,
        priced_in=priced_in,
        expected_direction=direction,
        risk_window_hours=risk,
        ai_confidence=confidence,
        evidence=["căn cứ kiểm tra"],
        source=source,
    )


class FakeAI:
    """Mock AI service: đếm lời gọi, trả string dựng sẵn, có chế độ ném exception."""

    def __init__(self, response: str | None = None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.config = SimpleNamespace(provider="test", model="test-model")
        self.call_count = 0
        self.prompts: list[str] = []

    def analyze(self, prompt: str, max_tokens: int = 300) -> str:
        self.call_count += 1
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return self.response or ""


def _noop_stance(currency: str):
    return {"stance": "neutral", "strength": None, "confidence": None, "source": "test"}


# ---------------------------------------------------------------------------
# Nhóm A — parse_ai_event_json
# ---------------------------------------------------------------------------

def test_parser_json_hop_le_day_du():
    """JSON hợp lệ đầy đủ → dict chuẩn hóa đúng schema."""
    parsed = parse_ai_event_json(_json_assessment())
    assert parsed is not None
    assert parsed["magnitude"] == "high"
    assert parsed["priced_in"] == "not_priced_in"
    assert parsed["expected_direction"] == "currency_up"
    assert parsed["risk_window_hours"] == 12.0
    assert parsed["confidence"] == 0.8
    assert parsed["evidence"] == ["forecast lệch lớn so với kỳ trước"]


def test_parser_magnitude_sai_enum():
    """magnitude sai enum → None."""
    assert parse_ai_event_json(_json_assessment(magnitude="massive")) is None


def test_parser_priced_in_sai_enum():
    """priced_in sai enum → None."""
    assert parse_ai_event_json(_json_assessment(priced_in="already_priced")) is None


def test_parser_expected_direction_sai_enum():
    """expected_direction sai enum → None."""
    assert parse_ai_event_json(_json_assessment(direction="bullish")) is None


def test_parser_risk_window_ngoai_1_24():
    """risk_window_hours ngoài 1-24 → None."""
    assert parse_ai_event_json(_json_assessment(risk=25.0)) is None
    assert parse_ai_event_json(_json_assessment(risk=0.5)) is None


def test_parser_risk_window_la_bool():
    """risk_window_hours là bool → None."""
    body = _json_assessment().replace('"risk_window_hours": 12.0', '"risk_window_hours": true')
    assert parse_ai_event_json(body) is None


def test_parser_confidence_la_bool():
    """confidence là bool → None."""
    body = _json_assessment().replace('"confidence": 0.8', '"confidence": true')
    assert parse_ai_event_json(body) is None


def test_parser_confidence_ngoai_0_1():
    """confidence ngoài 0-1 → None."""
    assert parse_ai_event_json(_json_assessment(confidence=1.5)) is None
    assert parse_ai_event_json(_json_assessment(confidence=-0.1)) is None


def test_parser_evidence_khong_phai_list():
    """evidence không phải list[str] → None."""
    body = _json_assessment().replace('"evidence": ["forecast lệch lớn so với kỳ trước"]', '"evidence": "x"')
    assert parse_ai_event_json(body) is None


def test_parser_json_boc_fence_markdown():
    """JSON bọc trong markdown fence → vẫn trích được."""
    parsed = parse_ai_event_json("```json\n" + _json_assessment(magnitude="medium") + "\n```")
    assert parsed is not None
    assert parsed["magnitude"] == "medium"


def test_parser_json_co_rac_bao_quanh():
    """Response có rác bao quanh JSON → trích từ '{' đầu đến '}' cuối."""
    parsed = parse_ai_event_json("Đây là kết quả: " + _json_assessment() + " Cảm ơn!")
    assert parsed is not None
    assert parsed["priced_in"] == "not_priced_in"


def test_parser_response_rong_hoac_khong_phai_str():
    """Response rỗng / không phải str → None."""
    assert parse_ai_event_json("") is None
    assert parse_ai_event_json("   ") is None
    assert parse_ai_event_json(None) is None
    assert parse_ai_event_json(123) is None
    assert parse_ai_event_json("không có JSON") is None


def test_parser_evidence_rong_ha_priced_in_unknown():
    """evidence rỗng + priced_in='priced_in' → giữ trường khác, hạ priced_in='unknown'."""
    parsed = parse_ai_event_json(_json_assessment(priced_in="priced_in", evidence=()))
    assert parsed is not None
    assert parsed["priced_in"] == "unknown"
    assert parsed["magnitude"] == "high"
    assert parsed["risk_window_hours"] == 12.0
    assert parsed["confidence"] == 0.8


# ---------------------------------------------------------------------------
# Nhóm B — derate_factor (decision table)
# ---------------------------------------------------------------------------

def test_decision_table_du_9_o():
    """Đủ 9 ô của decision table (kiểm tra số gần đúng 3 chữ số)."""
    table = [
        # (magnitude, priced_in, kỳ vọng)
        ("high", "not_priced_in", 0.70),
        ("high", "partial", 0.82),
        ("high", "priced_in", 0.91),
        ("high", "unknown", 0.70),
        ("medium", "not_priced_in", 0.85),
        ("medium", "partial", 0.91),
        ("medium", "priced_in", 0.955),
        ("medium", "unknown", 0.85),
        ("low", "not_priced_in", 0.95),
        ("low", "partial", 0.97),
        ("low", "priced_in", 0.985),
        ("low", "unknown", 0.95),
    ]
    for magnitude, priced_in, expected in table:
        event = _make_event(hours_until=30.0)  # trong (24, 48] để không dính backstop high
        assessment = _make_assessment(event, magnitude=magnitude, priced_in=priced_in, risk=48.0)
        factor = derate_factor(assessment, 30.0)
        assert round(factor, 3) == expected, f"{magnitude}/{priced_in} → {factor}, kỳ vọng {expected}"


def test_decision_hours_until_bang_4():
    """hours_until=4.0 → 1.0 (mốc 4.0 thuộc Bước 3)."""
    event = _make_event(hours_until=4.0)
    assessment = _make_assessment(event, magnitude="high", priced_in="not_priced_in", risk=48.0)
    assert derate_factor(assessment, 4.0) == 1.0


def test_decision_hours_until_485():
    """hours_until=48.5 → 1.0 (ngoài cửa sổ Bước 5)."""
    event = _make_event(hours_until=48.5)
    assessment = _make_assessment(event, magnitude="high", priced_in="not_priced_in", risk=48.0)
    assert derate_factor(assessment, 48.5) == 1.0


def test_decision_hours_until_48_dung_nguong():
    """hours_until=48.0 → vẫn kích hoạt (trong (4, 48])."""
    event = _make_event(hours_until=48.0)
    assessment = _make_assessment(event, magnitude="high", priced_in="not_priced_in", risk=48.0)
    assert round(derate_factor(assessment, 48.0), 3) == 0.70


def test_decision_hours_until_qua_risk_window():
    """hours_until > risk_window_hours → 1.0."""
    event = _make_event(hours_until=30.0)
    assessment = _make_assessment(event, magnitude="high", priced_in="not_priced_in", risk=20.0)
    assert derate_factor(assessment, 30.0) == 1.0


def test_decision_backstop_high_gan():
    """Backstop: hours=20 + magnitude=high + priced_in → hệ số ≤ 0.85."""
    event = _make_event(hours_until=20.0)
    assessment = _make_assessment(event, magnitude="high", priced_in="priced_in", risk=48.0)
    factor = derate_factor(assessment, 20.0)
    assert factor <= 0.85
    assert round(factor, 3) == 0.85  # min(0.91, 0.85)


def test_decision_confidence_thap_doi_unknown():
    """ai_confidence=0.3 + high + priced_in → nhánh unknown (0.70)."""
    event = _make_event(hours_until=30.0)
    assessment = _make_assessment(
        event, magnitude="high", priced_in="priced_in", risk=48.0, confidence=0.3
    )
    assert round(derate_factor(assessment, 30.0), 3) == 0.70


def test_decision_khong_duoi_floor_khong_tren_ceil():
    """Hệ số luôn nằm trong [0.15, 1.0] kể cả enum bất thường."""
    event = _make_event(hours_until=20.0)
    assessment = _make_assessment(event, magnitude="high", priced_in="priced_in", risk=48.0)
    factor = derate_factor(assessment, 20.0)
    assert DERATE_FLOOR <= factor <= DERATE_CEIL
    # Enum sai → xử lý như medium/unknown (0.85), không ném exception.
    bad = EventImpactAssessment(
        event_key="k",
        currency="USD",
        event_name="x",
        time_utc="t",
        hours_until=20.0,
        magnitude="huge",
        priced_in="weird",
        expected_direction="up",
        risk_window_hours=48.0,
        ai_confidence=0.9,
        evidence=[],
        source="ai",
    )
    assert round(derate_factor(bad, 20.0), 3) == 0.85


# ---------------------------------------------------------------------------
# Nhóm C — EventImpactAssessmentCache + make_event_key
# ---------------------------------------------------------------------------

def test_cache_hit_trong_ttl_khong_goi_lai():
    """Hit trong TTL → không gọi lại AI (2 event, đủ quota cho cả 2)."""
    events = [_make_event(name="FOMC A", time_utc="2026-08-08T06:00:00Z", hours_until=6.0),
              _make_event(name="NFP B", time_utc="2026-08-08T18:00:00Z", hours_until=12.0)]
    ai = FakeAI(response=_json_assessment())
    assessor = EventImpactAssessor()
    assessor.assess_upcoming_events(events, ai, _noop_stance, {}, now=T0, max_ai_calls=2)
    assert ai.call_count == 2
    # Lần chạy thứ hai trong TTL → cache hit, không gọi AI thêm.
    assessor.assess_upcoming_events(events, ai, _noop_stance, {}, now=T0 + timedelta(hours=1), max_ai_calls=2)
    assert ai.call_count == 2


def test_cache_het_ttl_truong_tinh_can_danh_gia_lai():
    """Hết TTL nhóm trường tĩnh → entry bị loại, get trả None (cần đánh giá lại)."""
    event = _make_event(hours_until=20.0)
    assessment = _make_assessment(event)
    cache = EventImpactAssessmentCache()
    cache.put(assessment.event_key, "fp", assessment, T0)
    # static TTL = min(20, 24) = 20h → quá 25h là hết hạn.
    assert cache.get(assessment.event_key, "fp", T0 + timedelta(hours=25)) is None


def test_cache_het_ttl_priced_in_6h_stale_flag():
    """Hết TTL priced_in 6h (nhưng trường tĩnh còn hạn) → cờ priced_in_stale=True."""
    event = _make_event(hours_until=20.0)
    assessment = _make_assessment(event)
    cache = EventImpactAssessmentCache()
    cache.put(assessment.event_key, "fp", assessment, T0)
    hit, stale = cache.get(assessment.event_key, "fp", T0 + timedelta(hours=7))
    assert hit is assessment
    assert stale is True
    # Trong 6h đầu → không stale.
    hit2, stale2 = cache.get(assessment.event_key, "fp", T0 + timedelta(hours=1))
    assert hit2 is assessment
    assert stale2 is False


def test_cache_negative_entry_ton_tai_sau_loi():
    """Negative cache: AI lỗi → assessment fallback được cache, get không trả None."""
    event = _make_event(hours_until=20.0)
    ai = FakeAI(response=None, error=TimeoutError("timeout"))
    assessor = EventImpactAssessor()
    results = assessor.assess_upcoming_events(
        [event], ai, _noop_stance, {}, now=T0, max_ai_calls=2
    )
    assert len(results) == 1
    assert results[0].source == "fallback"
    cached = assessor.cache.get(make_event_key(event), _ai_fingerprint(ai), T0)
    assert cached is not None
    assert cached[0].source == "fallback"


def test_cache_fingerprint_ai_khac_la_miss():
    """Fingerprint AI khác → miss (đổi model/tắt AI là cache miss)."""
    event = _make_event(hours_until=20.0)
    assessment = _make_assessment(event)
    cache = EventImpactAssessmentCache()
    cache.put(assessment.event_key, "fpA", assessment, T0)
    assert cache.get(assessment.event_key, "fpB", T0 + timedelta(hours=1)) is None


def test_make_event_key_2_event_cung_ten_khac_gio():
    """2 event cùng tên + cùng currency nhưng khác giờ → 2 key khác nhau."""
    e1 = _make_event(time_utc="2026-08-08T12:00:00Z", currency="USD", name="FOMC Meeting")
    e2 = _make_event(time_utc="2026-08-08T18:00:00Z", currency="USD", name="FOMC Meeting")
    assert make_event_key(e1) != make_event_key(e2)
    # Cùng currency + tên nhưng khác case/space → key giống nhau (chuẩn hóa).
    e3 = _make_event(time_utc="2026-08-08T12:00:00Z", currency="usd", name="  fomc   meeting  ")
    assert make_event_key(e1) == make_event_key(e3)


def test_make_event_key_2_event_khac_currency():
    """Cùng tên + giờ nhưng khác currency → key khác nhau."""
    e1 = _make_event(time_utc="2026-08-08T12:00:00Z", currency="USD", name="CPI")
    e2 = _make_event(time_utc="2026-08-08T12:00:00Z", currency="EUR", name="CPI")
    assert make_event_key(e1) != make_event_key(e2)


# ---------------------------------------------------------------------------
# Nhóm D — EventImpactAssessor (orchestrator)
# ---------------------------------------------------------------------------

def test_orchestrator_max_ai_calls_2_4_event():
    """4 event + max_ai_calls=2 → đúng 2 lời gọi AI, 2 event còn lại fallback 0.85."""
    events = [
        _make_event(name="A", time_utc="2026-08-08T06:00:00Z", hours_until=6.0),
        _make_event(name="B", time_utc="2026-08-08T12:00:00Z", hours_until=12.0),
        _make_event(name="C", time_utc="2026-08-08T18:00:00Z", hours_until=18.0),
        _make_event(name="D", time_utc="2026-08-08T22:00:00Z", hours_until=22.0),
    ]
    ai = FakeAI(response=_json_assessment())
    assessor = EventImpactAssessor()
    results = assessor.assess_upcoming_events(events, ai, _noop_stance, {}, now=T0, max_ai_calls=2)
    assert ai.call_count == 2
    assert [r.source for r in results] == ["ai", "ai", "fallback", "fallback"]
    # Fallback medium/unknown trong cửa sổ → hệ số 0.85.
    assert round(derate_factor(results[2], results[2].hours_until), 3) == 0.85
    assert round(derate_factor(results[3], results[3].hours_until), 3) == 0.85


def test_orchestrator_ai_loi_toan_fallback():
    """FakeAI ném exception → không exception lọt ra, toàn fallback."""
    events = [
        _make_event(name="A", time_utc="2026-08-08T06:00:00Z", hours_until=6.0),
        _make_event(name="B", time_utc="2026-08-08T12:00:00Z", hours_until=12.0),
    ]
    ai = FakeAI(response=None, error=TimeoutError("timeout"))
    assessor = EventImpactAssessor()
    results = assessor.assess_upcoming_events(events, ai, _noop_stance, {}, now=T0, max_ai_calls=2)
    assert len(results) == 2
    assert all(r.source == "fallback" for r in results)
    assert all(r.magnitude == "medium" and r.priced_in == "unknown" for r in results)


def test_orchestrator_ai_service_none_toan_fallback():
    """ai_service=None → toàn fallback, không lỗi."""
    events = [
        _make_event(name="A", time_utc="2026-08-08T06:00:00Z", hours_until=6.0),
        _make_event(name="B", time_utc="2026-08-08T12:00:00Z", hours_until=12.0),
    ]
    assessor = EventImpactAssessor()
    results = assessor.assess_upcoming_events(events, None, _noop_stance, {}, now=T0, max_ai_calls=2)
    assert len(results) == 2
    assert all(r.source == "fallback" for r in results)


def test_orchestrator_loc_dung_cua_so():
    """Lọc đúng cửa sổ: loại h=3.9, h=49, impact không high."""
    events = [
        _make_event(name="Quá sớm", time_utc="2026-08-07T13:00:00Z", hours_until=3.9),
        _make_event(name="Quá xa", time_utc="2026-08-09T10:00:00Z", hours_until=49.0),
        _make_event(name="Medium", time_utc="2026-08-08T12:00:00Z", hours_until=20.0, impact="medium"),
        _make_event(name="Hợp lệ", time_utc="2026-08-08T05:00:00Z", hours_until=20.0, impact="high"),
    ]
    ai = FakeAI(response=_json_assessment())
    assessor = EventImpactAssessor()
    results = assessor.assess_upcoming_events(events, ai, _noop_stance, {}, now=T0, max_ai_calls=2)
    assert len(results) == 1
    assert results[0].event_name == "Hợp lệ"
    assert results[0].source == "ai"
    assert ai.call_count == 1


def test_orchestrator_ai_tra_ve_json_hong_fallback():
    """AI trả JSON hỏng → assessment fallback (fail-closed), không exception."""
    event = _make_event(name="Hợp lệ", hours_until=20.0)
    ai = FakeAI(response="không phải JSON hợp lệ")
    assessor = EventImpactAssessor()
    results = assessor.assess_upcoming_events([event], ai, _noop_stance, {}, now=T0, max_ai_calls=2)
    assert len(results) == 1
    assert results[0].source == "fallback"
    assert results[0].magnitude == "medium"


def test_select_dominant_currency_khong_thuoc_cap_bi_loai():
    """Currency không thuộc cặp bị loại khỏi select_dominant_assessment."""
    usd = _make_assessment(_make_event(currency="USD", hours_until=10.0),
                           magnitude="high", priced_in="not_priced_in", risk=48.0)
    eur = _make_assessment(_make_event(currency="EUR", hours_until=20.0),
                           magnitude="medium", priced_in="partial", risk=48.0)
    jpy = _make_assessment(_make_event(currency="JPY", hours_until=8.0),
                           magnitude="high", priced_in="not_priced_in", risk=48.0)
    selected = select_dominant_assessment([usd, eur, jpy], "EUR", "USD")
    assert selected is not None
    assert selected.currency == "USD"  # JPY bị loại; USD 0.70 < EUR 0.91


def test_select_dominant_tie_break_chon_gan_hon():
    """Tie derate_factor → chọn event có hours_until nhỏ hơn (gần hơn)."""
    near = _make_assessment(_make_event(hours_until=10.0),
                            magnitude="high", priced_in="not_priced_in", risk=48.0)
    far = _make_assessment(_make_event(hours_until=20.0),
                           magnitude="high", priced_in="not_priced_in", risk=48.0)
    selected = select_dominant_assessment([far, near], "EUR", "USD")
    assert selected is near
    assert selected.hours_until == 10.0


def test_select_dominant_khong_co_ca_hop_le_tra_none():
    """Không có assessment thỏa điều kiện kích hoạt → None."""
    out_of_window = _make_assessment(_make_event(hours_until=60.0),
                                     magnitude="high", priced_in="not_priced_in", risk=48.0)
    wrong_currency = _make_assessment(_make_event(currency="JPY", hours_until=10.0),
                                      magnitude="high", priced_in="not_priced_in", risk=48.0)
    assert select_dominant_assessment([out_of_window, wrong_currency], "EUR", "USD") is None


# ---------------------------------------------------------------------------
# build_event_prompt — cấu trúc prompt
# ---------------------------------------------------------------------------

def test_build_event_prompt_ghi_ro_stance_va_headlines():
    """Prompt chứa đủ thông tin event, stance, headline; nhấn mạnh không bịa đặt."""
    event = _make_event(hours_until=20.0)
    stance = {"stance": "hawkish", "strength": 8, "confidence": 0.9, "source": "ai"}
    headlines = ["Tin 1", "Tin 2"]
    prompt = build_event_prompt(event, stance, headlines)
    assert "FOMC Meeting" in prompt
    assert "USD" in prompt
    assert "hawkish" in prompt
    assert "- Tin 1" in prompt
    assert "- Tin 2" in prompt
    assert "KHÔNG" in prompt and "bịa" in prompt
    assert 'priced_in = "unknown"' in prompt or "'unknown'" in prompt


def test_build_event_prompt_khong_co_stance_headline():
    """Không có stance/headline → ghi rõ 'không có' thay vì bỏ sót."""
    event = _make_event(hours_until=20.0)
    prompt = build_event_prompt(event, None, [])
    assert "không có dữ liệu stance" in prompt.lower()
    assert "không có headline" in prompt.lower()


def test_build_event_prompt_gioi_han_8_headline():
    """Prompt chỉ đưa tối đa 8 headlines."""
    event = _make_event(hours_until=20.0)
    headlines = [f"Tin {i}" for i in range(20)]
    prompt = build_event_prompt(event, None, headlines)
    assert "- Tin 0" in prompt
    assert "- Tin 7" in prompt
    assert "- Tin 8" not in prompt