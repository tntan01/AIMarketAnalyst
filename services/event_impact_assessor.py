"""Bước 5 — AI Event Impact Assessment: module logic thuần (chưa nối runtime).

Đánh giá nguy cơ của các sự kiện vĩ mô high-impact trong cửa sổ 4-48 giờ tới
bằng AI, trả lời 3 câu hỏi: mức nguy hiểm (magnitude), thị trường đã price-in
chưa (priced_in), cửa sổ rủi ro dài bao nhiêu giờ (risk_window_hours).

Kết quả CHỈ dùng để phòng thủ (hạ macro_confidence + cảnh báo), KHÔNG bao giờ
cộng điểm, KHÔNG tạo bias hướng. Module này thuần logic — chưa được import từ
bất kỳ file nào khác (nối runtime ở Prompt 2).

Đọc ngữ cảnh thiết kế tại docs/macro/step5_deepseek_handoff.md (Phần 1).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from services.calendar_helpers import _is_high_impact

# ---------------------------------------------------------------------------
# Hằng số chung
# ---------------------------------------------------------------------------

# Cửa sổ kích hoạt Bước 5 (giờ). Đúng mốc 4.0 thuộc về Bước 3.
MIN_HOURS_UNTIL = 4.0
MAX_HOURS_UNTIL = 48.0

# Enum hợp lệ cho các trường của assessment.
MAGNITUDE_VALUES = frozenset({"low", "medium", "high"})
PRICED_IN_VALUES = frozenset({"priced_in", "partial", "not_priced_in", "unknown"})
DIRECTION_VALUES = frozenset({"currency_up", "currency_down", "two_way", "unknown"})

# Decision table: hệ số = 1 − penalty(magnitude) × thừa_số(priced_in).
MAGNITUDE_PENALTY = {"high": 0.30, "medium": 0.15, "low": 0.05}
PRICED_IN_FACTOR = {"not_priced_in": 1.0, "partial": 0.6, "priced_in": 0.3, "unknown": 1.0}

# Backstop: hours_until ≤ 24 mà magnitude=high thì hệ số không vượt quá giá trị này.
HIGH_BACKSTOP_HOURS = 24.0
HIGH_BACKSTOP_FACTOR = 0.85

# Floor tuyệt đối và trần cho hệ số derate.
DERATE_FLOOR = 0.15
DERATE_CEIL = 1.0

# Ngưỡng confidence của AI: dưới ngưỡng coi priced_in như "unknown".
AI_CONFIDENCE_GATE = 0.5

# Fallback dùng khi AI lỗi / không có AI / JSON hỏng (D6).
FALLBACK = {
    "magnitude": "medium",
    "priced_in": "unknown",
    "expected_direction": "unknown",
    "risk_window_hours": 24.0,
    "ai_confidence": None,
    "evidence": [],
    "source": "fallback",
}

# TTL cache (D7).
STATIC_TTL_CAP_HOURS = 24.0        # TTL nhóm trường tĩnh = min(thời_gian_đến_event, 24h)
PRICED_IN_TTL = timedelta(hours=6)  # TTL riêng của trường priced_in
NEGATIVE_CACHE_TTL = timedelta(minutes=30)  # Negative cache (AI hỏng): 30 phút

# Số headline tối đa đưa vào prompt.
MAX_PROMPT_HEADLINES = 8


# ---------------------------------------------------------------------------
# Assessment
# ---------------------------------------------------------------------------

@dataclass
class EventImpactAssessment:
    """Đánh giá tác động của một sự kiện vĩ mô high-impact trong 4-48 giờ tới.

    Trường expected_direction KHÔNG dùng để chấm điểm (đối xứng, D3) — chỉ dùng
    cho cảnh báo và journal. Trường applied_derate ghi hệ số thực tế đã nhân
    vào macro_confidence (do pipeline bước sau gán, mặc định None).
    """

    event_key: str
    currency: str
    event_name: str
    time_utc: str
    hours_until: float
    magnitude: str  # "low" | "medium" | "high"
    priced_in: str  # "priced_in" | "partial" | "not_priced_in" | "unknown"
    expected_direction: str  # "currency_up" | "currency_down" | "two_way" | "unknown"
    risk_window_hours: float
    ai_confidence: float | None
    evidence: list[str]
    source: str  # "ai" | "fallback"
    applied_derate: float | None = None


def _normalize_currency(value: object) -> str:
    return str(value or "").strip().upper()


def _normalize_event_name(value: object) -> str:
    """Chuẩn hóa tên event: lowercase, gộp khoảng trắng liên tiếp."""
    return " ".join(str(value or "").lower().split())


def make_event_key(event: dict) -> str:
    """Tạo key ổn định cho một event theo bộ ba (time_utc, currency, tên).

    ForexFactory không có stable ID — dự án dedup bằng (time_utc, currency,
    event) (forex_factory_client.py:179). Key là sha1 hex của chuỗi
    "time_utc|currency|tên_chuẩn_hóa" để 1 assessment phục vụ mọi cặp chứa
    currency đó (D7).
    """
    time_utc = str(event.get("time_utc", "")).strip()
    currency = _normalize_currency(event.get("currency"))
    name = _normalize_event_name(event.get("event"))
    raw = f"{time_utc}|{currency}|{name}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

def build_event_prompt(event: dict, stance_info: dict | None, headlines: list[str]) -> str:
    """Dựng prompt tiếng Việt yêu cầu AI trả DUY NHẤT một JSON đúng schema.

    - event: dict event của dự án (currency, event, impact, time_utc,
      hours_until, forecast, previous, actual).
    - stance_info: dict {stance, strength, confidence, source} hoặc None/rỗng.
    - headlines: tối đa 8 headline, mỗi dòng gạch đầu dòng.

    Thiết kế đã chốt (Bước 5, minor-3 trong báo cáo review): prompt KHÔNG nhận
    dữ liệu biến động giá gần đây. Headlines được chọn làm proxy cho mức độ
    price-in — tin là thứ thị trường phản ứng trước tiên, và forecast/previous
    + headlines đủ để AI phán đoán "đã price-in chưa". Nếu sau này cần tín
    hiệu giá, chỉ cần bổ sung 1 trường vào đây (thay đổi cục bộ, không đụng
    decision table/cache).
    """
    lines = [
        "Bạn là trợ lý phân tích vĩ mô cho trading forex. Hãy đánh giá một \"sự kiện kinh tế\" sắp diễn ra.",
        "",
        "THÔNG TIN SỰ KIỆN:",
        f"- Tên sự kiện: {str(event.get('event', '')).strip()}",
        f"- Đồng tiền liên quan: {_normalize_currency(event.get('currency'))}",
        f"- Thời gian (UTC): {str(event.get('time_utc', '')).strip()}",
        f"- Còn {str(event.get('hours_until', ''))} giờ nữa diễn ra",
        f"- Mức tác động: {str(event.get('impact', '')).strip()}",
        f"- Dự báo (forecast): {str(event.get('forecast', '')).strip()}",
        f"- Giá trị kỳ trước (previous): {str(event.get('previous', '')).strip()}",
        "",
        "STANCE HIỆN TẠI CỦA ĐỒNG TIỀN:",
    ]
    if stance_info:
        for field in ("stance", "strength", "confidence", "source"):
            lines.append(f"- {field}: {stance_info.get(field)}")
    else:
        lines.append("- Không có dữ liệu stance.")
    lines.append("")
    lines.append("TIN TỨC GẦN ĐÂY (tối đa 8 headline):")
    if headlines:
        for headline in list(headlines)[:MAX_PROMPT_HEADLINES]:
            lines.append(f"- {headline}")
    else:
        lines.append("- Không có headline.")
    lines.append("")
    lines.append("HÃY TRẢ LỜI DUY NHẤT MỘT JSON HỢP LỆ THEO ĐÚNG SCHEMA SAU, KHÔNG THÊM VĂN BẢN KHÁC:")
    lines.append(
        '{"magnitude": "low" | "medium" | "high", "priced_in": "priced_in" | "partial" '
        '| "not_priced_in" | "unknown", "expected_direction": "currency_up" | "currency_down" '
        '| "two_way" | "unknown", "risk_window_hours": <số từ 1 đến 24>, "confidence": '
        '<số từ 0 đến 1>, "evidence": ["căn cứ ngắn 1", "căn cứ ngắn 2"]}'
    )
    lines.append("")
    lines.append("GIẢI THÍCH CÁC TRƯỜNG:")
    lines.append('- magnitude: mức nguy hiểm của sự kiện với thị trường (low/medium/high).')
    lines.append('- priced_in: mức độ thị trường đã "price-in" sự kiện — "priced_in" nghĩa là')
    lines.append('  phần lớn tác động đã phản ánh vào giá, "not_priced_in" nghĩa là còn bất ngờ')
    lines.append('  lớn khi công bố, "partial" là một phần, "unknown" là không đủ căn cứ phán đoán.')
    lines.append('- expected_direction: hướng giá dự kiến của đồng tiền khi sự kiện công bố.')
    lines.append('- risk_window_hours: số giờ quanh thời điểm công bố mà thị trường dễ biến động mạnh (1-24).')
    lines.append('- confidence: độ tự tin của bạn về toàn bộ đánh giá (0-1).')
    lines.append("- evidence: các căn cứ ngắn gọn, mỗi phần tử một câu.")
    lines.append("")
    lines.append("QUY TẮC BẮT BUỘC:")
    lines.append("- evidence phải dựa trên forecast/previous/headlines được cung cấp, tuyệt đối KHÔNG được bịa đặt.")
    lines.append('- Nếu không đủ căn cứ để phán đoán mức độ price-in thì trả priced_in = "unknown".')
    lines.append("- Chỉ trả về JSON, không thêm lời giải thích, không thêm markdown.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Parser + validate
# ---------------------------------------------------------------------------

def _normalize_enum(value: object, allowed: frozenset[str]) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized if normalized in allowed else None


def _validate_event_json(data: dict) -> dict | None:
    """Validate dữ liệu JSON theo đúng QUY TẮC VALIDATE trong tài liệu thiết kế."""
    magnitude = _normalize_enum(data.get("magnitude"), MAGNITUDE_VALUES)
    if magnitude is None:
        return None
    priced_in = _normalize_enum(data.get("priced_in"), PRICED_IN_VALUES)
    if priced_in is None:
        return None
    direction = _normalize_enum(data.get("expected_direction"), DIRECTION_VALUES)
    if direction is None:
        return None
    risk = data.get("risk_window_hours")
    if isinstance(risk, bool) or not isinstance(risk, (int, float)) or not (1 <= risk <= 24):
        return None
    confidence = data.get("confidence")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not (0 <= confidence <= 1)
    ):
        return None
    evidence = data.get("evidence")
    if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
        return None
    evidence = [str(item) for item in evidence]
    # evidence rỗng mà priced_in chưa phải "unknown" → KHÔNG loại, nhưng hạ
    # priced_in xuống "unknown" (thiếu căn cứ thì không được khẳng định price-in).
    if not evidence and priced_in != "unknown":
        priced_in = "unknown"
    return {
        "magnitude": magnitude,
        "priced_in": priced_in,
        "expected_direction": direction,
        "risk_window_hours": float(risk),
        "confidence": float(confidence),
        "evidence": evidence,
    }


def parse_ai_event_json(response: object) -> dict | None:
    """Parse và validate phản hồi JSON của AI cho sự kiện.

    Trả về dict đã chuẩn hóa {magnitude, priced_in, expected_direction,
    risk_window_hours, confidence, evidence} hoặc None nếu không thể trích JSON
    hợp lệ. Trích được JSON kể cả khi response bị bọc trong markdown fence hoặc
    có rác bao quanh (tìm từ "{" đầu đến "}" cuối).
    """
    if not isinstance(response, str):
        return None
    text = response.strip()
    if not text:
        return None
    candidates = [text.strip("`").strip()]
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        parsed = _validate_event_json(data)
        if parsed is not None:
            return parsed
    return None


# ---------------------------------------------------------------------------
# Decision table
# ---------------------------------------------------------------------------

def derate_factor(assessment: EventImpactAssessment, hours_until: float) -> float:
    """Hệ số nhân macro_confidence theo DECISION TABLE trong tài liệu thiết kế.

    Điều kiện đủ:
    - hours_until ≤ 4 hoặc > 48 → 1.0 (ngoài cửa sổ Bước 5).
    - hours_until > risk_window_hours → 1.0 (ngoài cửa sổ rủi ro của sự kiện).
    - ai_confidence < 0.5 (confidence gate) → coi priced_in như "unknown" (giữ
      nguyên magnitude) ĐỒNG THỜI cap factor ≤ 0.85 — AI thiếu tự tin không được
      phòng thủ NHẸ hơn AI chết hẳn (fallback medium/unknown = 0.85, D6).
    - Backstop: hours_until ≤ 24 và magnitude == "high" → kết quả không vượt 0.85.
    - Không bao giờ trả dưới 0.15 hoặc trên 1.0.
    """
    if not (MIN_HOURS_UNTIL < hours_until <= MAX_HOURS_UNTIL):
        return 1.0
    if hours_until > assessment.risk_window_hours:
        return 1.0
    magnitude = assessment.magnitude
    if magnitude not in MAGNITUDE_PENALTY:
        magnitude = "medium"
    priced_in = assessment.priced_in
    if priced_in not in PRICED_IN_FACTOR:
        priced_in = "unknown"
    # Confidence gate: AI tự tin thấp → không tin phán đoán price-in của AI.
    gate_active = (
        assessment.ai_confidence is not None
        and assessment.ai_confidence < AI_CONFIDENCE_GATE
    )
    if gate_active:
        priced_in = "unknown"
    factor = 1.0 - MAGNITUDE_PENALTY[magnitude] * PRICED_IN_FACTOR[priced_in]
    if gate_active:
        # Ngưỡng phòng thủ tối thiểu khi AI thiếu tự tin: không nhẹ hơn fallback.
        factor = min(factor, HIGH_BACKSTOP_FACTOR)
    # Backstop: sự kiện high rất gần (≤ 24h) thì không bao giờ được nhẹ nhàng.
    if magnitude == "high" and hours_until <= HIGH_BACKSTOP_HOURS:
        factor = min(factor, HIGH_BACKSTOP_FACTOR)
    return max(DERATE_FLOOR, min(DERATE_CEIL, factor))


def select_dominant_assessment(
    assessments: list[EventImpactAssessment],
    pair_base: str,
    pair_quote: str,
) -> EventImpactAssessment | None:
    """Chọn assessment duy nhất được áp dụng derate cho một cặp tiền (D5).

    Chỉ giữ assessment có currency thuộc (base, quote) VÀ thỏa điều kiện kích
    hoạt (4 < hours_until ≤ 48, hours_until ≤ risk_window_hours). Chọn cái có
    derate_factor nhỏ nhất; tie thì chọn hours_until nhỏ hơn. Không có → None.
    """
    base = _normalize_currency(pair_base)
    quote = _normalize_currency(pair_quote)
    candidates = []
    for assessment in assessments or []:
        if assessment.currency not in (base, quote):
            continue
        if not (MIN_HOURS_UNTIL < assessment.hours_until <= MAX_HOURS_UNTIL):
            continue
        if assessment.hours_until > assessment.risk_window_hours:
            continue
        candidates.append(assessment)
    if not candidates:
        return None
    return min(candidates, key=lambda a: (derate_factor(a, a.hours_until), a.hours_until))


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _ai_fingerprint(ai_service: object | None) -> str:
    """Fingerprint ổn định của AI service (copy logic news_service._ai_fingerprint).

    Không đọc secret — chỉ provider + model. Cache theo đồng tiền + fingerprint
    để đổi model AI (hoặc tắt AI) là cache miss.
    """
    if ai_service is None:
        payload = {"enabled": False, "provider": "", "model": ""}
    else:
        config = getattr(ai_service, "config", None)
        provider = getattr(config, "provider", "")
        model = getattr(config, "model", "")
        payload = {
            "enabled": True,
            "provider": provider if isinstance(provider, str) else "unknown",
            "model": model if isinstance(model, str) else "unknown",
        }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


class EventImpactAssessmentCache:
    """Cache assessment theo EVENT (1 assessment phục vụ mọi cặp chứa currency).

    Key = event_key + ai_fingerprint. Hai tầng TTL (D7):
    - Nhóm trường tĩnh (magnitude, expected_direction, risk_window_hours):
      min(thời_gian_đến_event, 24h) — tính từ hours_until của assessment.
    - Trường priced_in: 6 giờ riêng.
    - Negative cache (source="fallback"): 30 phút.
    Entry quá hạn bị loại bỏ khi get.
    """

    def __init__(self) -> None:
        self._entries: dict[str, tuple[EventImpactAssessment, datetime]] = {}

    @staticmethod
    def cache_key(event_key: str, fingerprint: str) -> str:
        return json.dumps(
            {"event_key": event_key, "ai": fingerprint},
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _static_ttl(assessment: EventImpactAssessment) -> timedelta:
        hours = min(assessment.hours_until, STATIC_TTL_CAP_HOURS)
        if assessment.source == "fallback":
            hours = min(hours, NEGATIVE_CACHE_TTL.total_seconds() / 3600)
        return timedelta(hours=hours)

    def get(
        self, event_key: str, fingerprint: str, now: datetime
    ) -> tuple[EventImpactAssessment, bool] | None:
        """Trả (assessment, priced_in_stale) nếu còn hạn, None nếu miss.

        priced_in_stale=True khi nhóm trường tĩnh còn hạn nhưng priced_in đã
        quá TTL 6h — caller quyết định có gọi AI lại để refresh hay không.
        """
        key = self.cache_key(event_key, fingerprint)
        entry = self._entries.get(key)
        if entry is None:
            return None
        assessment, put_time = entry
        static_expires = put_time + self._static_ttl(assessment)
        if now >= static_expires:
            del self._entries[key]
            return None
        priced_in_stale = now >= put_time + PRICED_IN_TTL
        return (assessment, priced_in_stale)

    def put(self, event_key: str, fingerprint: str, assessment: EventImpactAssessment, now: datetime) -> None:
        key = self.cache_key(event_key, fingerprint)
        self._entries[key] = (assessment, now)


# ---------------------------------------------------------------------------
# Assessor
# ---------------------------------------------------------------------------

class EventImpactAssessor:
    """Đánh giá các sự kiện high-impact trong cửa sổ 4-48 giờ bằng AI.

    Fail-closed (D6): mọi lỗi → assessment fallback {magnitude: "medium",
    priced_in: "unknown"} → hệ số 0.85. Không bao giờ ném exception ra khỏi
    assess_upcoming_events.
    """

    def __init__(self, cache: EventImpactAssessmentCache | None = None) -> None:
        self.cache = cache if cache is not None else EventImpactAssessmentCache()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _currency_of(event: dict) -> str:
        return _normalize_currency(event.get("currency"))

    @staticmethod
    def _filter_candidates(events: list[dict]) -> list[dict]:
        """Giữ event impact high trong cửa sổ 4 < hours_until ≤ 48, sắp tăng dần."""
        candidates = []
        for event in events or []:
            if not isinstance(event, dict):
                continue
            hours_until = event.get("hours_until")
            if isinstance(hours_until, bool) or not isinstance(hours_until, (int, float)):
                continue
            if not (MIN_HOURS_UNTIL < float(hours_until) <= MAX_HOURS_UNTIL):
                continue
            if not _is_high_impact(str(event.get("impact", ""))):
                continue
            candidates.append(event)
        candidates.sort(key=lambda e: float(e.get("hours_until", 0) or 0))
        return candidates

    def _fallback_assessment(self, event: dict, event_key: str, currency: str) -> EventImpactAssessment:
        return EventImpactAssessment(
            event_key=event_key,
            currency=currency,
            event_name=str(event.get("event", "")),
            time_utc=str(event.get("time_utc", "")),
            hours_until=float(event.get("hours_until", 0) or 0),
            magnitude=FALLBACK["magnitude"],
            priced_in=FALLBACK["priced_in"],
            expected_direction=FALLBACK["expected_direction"],
            risk_window_hours=float(FALLBACK["risk_window_hours"]),
            ai_confidence=FALLBACK["ai_confidence"],
            evidence=list(FALLBACK["evidence"]),
            source=FALLBACK["source"],
        )

    def _assessment_from_ai(
        self, event: dict, event_key: str, currency: str, parsed: dict
    ) -> EventImpactAssessment:
        return EventImpactAssessment(
            event_key=event_key,
            currency=currency,
            event_name=str(event.get("event", "")),
            time_utc=str(event.get("time_utc", "")),
            hours_until=float(event.get("hours_until", 0) or 0),
            magnitude=parsed["magnitude"],
            priced_in=parsed["priced_in"],
            expected_direction=parsed["expected_direction"],
            risk_window_hours=parsed["risk_window_hours"],
            ai_confidence=parsed["confidence"],
            evidence=list(parsed["evidence"]),
            source="ai",
        )

    def _assess_with_ai(
        self,
        event: dict,
        event_key: str,
        currency: str,
        ai_service: object,
        stance_lookup,
        headlines_by_currency: dict[str, list[str]],
    ) -> EventImpactAssessment:
        """Một lời gọi AI: build prompt → analyze → parse. Lỗi/None → fallback."""
        try:
            stance_info = None
            if stance_lookup is not None:
                stance_info = stance_lookup(currency)
            headlines = []
            if headlines_by_currency:
                headlines = list(headlines_by_currency.get(currency, []) or [])
            prompt = build_event_prompt(event, stance_info, headlines)
            response = ai_service.analyze(prompt, max_tokens=300)
            parsed = parse_ai_event_json(response)
            if parsed is None:
                return self._fallback_assessment(event, event_key, currency)
            return self._assessment_from_ai(event, event_key, currency, parsed)
        except Exception:
            return self._fallback_assessment(event, event_key, currency)

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def assess_upcoming_events(
        self,
        events: list[dict],
        ai_service: object | None,
        stance_lookup,
        headlines_by_currency: dict[str, list[str]],
        *,
        now: datetime | None = None,
        max_ai_calls: int = 2,
    ) -> tuple[list[EventImpactAssessment], set[str]]:
        """Đánh giá toàn bộ event high-impact trong 4-48 giờ, tối đa max_ai_calls lời gọi AI.

        Trả về (assessments, fresh_ai_keys):
        - assessments: toàn bộ đánh giá (cache hit, AI mới, fallback).
        - fresh_ai_keys: tập event_key VỪA được gọi AI thật trong chu kỳ này
          (cả nhánh miss-cache lẫn nhánh refresh khi priced_in hết hạn 6h, kể cả
          lời gọi AI bị lỗi). Caller chỉ được coi là "assessment mới do AI tạo"
          khi event_key nằm trong tập này — cache hit KHÔNG phải assessment mới.

        - Event đã có cache hợp lệ → dùng cache (gọi lại AI nếu priced_in_stale
          và còn quota).
        - Mỗi lời gọi AI: build_event_prompt → analyze(max_tokens=300) →
          parse_ai_event_json → assessment source="ai". Exception/None → fallback.
        - Event chưa đến lượt gọi AI → assessment fallback như trên.
        - Assessment từ CUỘC GỌI AI (thành công hoặc lỗi) được put vào cache
          (negative cache 30 phút nếu lỗi). Event bị bỏ qua vì hết quota KHÔNG
          được cache — scan sau vẫn có cơ hội gọi AI.
        - Toàn bộ method fail-closed: không bao giờ ném exception.
        """
        try:
            if now is None:
                now = datetime.now(UTC)
            candidates = self._filter_candidates(events)
            results: list[EventImpactAssessment] = []
            fresh_ai_keys: set[str] = set()
            calls_left = max_ai_calls
            fingerprint = _ai_fingerprint(ai_service)
            for event in candidates:
                event_key = make_event_key(event)
                currency = self._currency_of(event)
                cached = self.cache.get(event_key, fingerprint, now)
                if cached is not None:
                    assessment, priced_in_stale = cached
                    if priced_in_stale and ai_service is not None and calls_left > 0:
                        fresh = self._assess_with_ai(
                            event, event_key, currency, ai_service, stance_lookup, headlines_by_currency
                        )
                        calls_left -= 1
                        fresh_ai_keys.add(event_key)
                        self.cache.put(event_key, fingerprint, fresh, now)
                        assessment = fresh
                    else:
                        # Cập nhật hours_until theo event hiện tại để derate chính xác.
                        assessment = replace(
                            assessment, hours_until=float(event.get("hours_until", 0) or 0)
                        )
                    results.append(assessment)
                    continue
                # Không có cache.
                if ai_service is not None and calls_left > 0:
                    assessment = self._assess_with_ai(
                        event, event_key, currency, ai_service, stance_lookup, headlines_by_currency
                    )
                    calls_left -= 1
                    fresh_ai_keys.add(event_key)
                    self.cache.put(event_key, fingerprint, assessment, now)
                else:
                    assessment = self._fallback_assessment(event, event_key, currency)
                results.append(assessment)
            return results, fresh_ai_keys
        except Exception:
            # Fail-closed: lỗi bất ngờ → fallback toàn bộ event đầu vào hợp lệ.
            candidates = self._filter_candidates(events)
            return (
                [
                    self._fallback_assessment(event, make_event_key(event), self._currency_of(event))
                    for event in candidates
                ],
                set(),
            )