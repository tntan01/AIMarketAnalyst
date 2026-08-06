"""AI review of the selected SMC zone.

The module sends the selected zone's evidence (zone type, timeframe,
displacement, position versus the current price, nearby liquidity) to the AI
provider configured in the app and expects a strict JSON verdict::

    {
        "zone_validity": 0-10,
        "liquidity_setup": "strong|weak|none",
        "displacement_quality": 0-10,
        "confidence": 0-1,
        "reasons": [...]
    }

Any AI error, unparsable response, or schema violation is treated as
``uncertain`` so callers can skip the verdict and apply nothing.
"""

from __future__ import annotations

import json
import re
from math import isfinite
from typing import Any


ZONE_REVIEW_SCHEMA_VERSION = 1
ZONE_REVIEW_LIQUIDITY_VALUES = ("strong", "weak", "none")
_ZONE_REVIEW_MAX_REASONS = 8
_ZONE_REVIEW_REASON_LIMIT = 200
_ZONE_REVIEW_RAW_LIMIT = 1200

# Key of the AI zone-audit cache carried inside a persisted scan result.
# The cache maps zone_id -> valid verdict, so a backtest replay over the
# same data reuses stored verdicts instead of calling the AI again.
AI_ZONE_AUDIT_CACHE_KEY = "ai_zone_audit_cache"


def default_zone_review(reason: str = "not_reviewed") -> dict[str, Any]:
    """Uncertain verdict: nothing from the AI may be applied."""
    return {
        "schema_version": ZONE_REVIEW_SCHEMA_VERSION,
        "status": "uncertain",
        "zone_validity": None,
        "liquidity_setup": None,
        "displacement_quality": None,
        "confidence": 0.0,
        "reasons": [],
        "review_error": reason,
    }


def review_selected_zone(
    zone_data: dict[str, Any] | None,
    ai_service: Any,
    *,
    max_tokens: int = 4000,
) -> dict[str, Any]:
    """Review the selected SMC zone with the app-configured AI provider.

    ``ai_service`` is the :class:`AIService` built from
    ``settings.ai.active_provider()`` by the caller.  Every failure path
    (missing zone data, missing AI service, provider error, invalid JSON,
    wrong schema) returns an ``uncertain`` verdict so nothing is applied.
    """

    if not isinstance(zone_data, dict) or not zone_data:
        return default_zone_review("missing_zone_data")
    if ai_service is None:
        return default_zone_review("ai_unavailable")
    prompt = build_zone_review_prompt(zone_data)
    try:
        raw = ai_service.analyze(prompt, max_tokens=max_tokens)
    except Exception:
        return default_zone_review("ai_error")
    return parse_zone_review(raw)


def zone_audit_cache_from_scan_result(scan_result: Any) -> dict[str, Any]:
    """Return the zone-audit cache embedded in *scan_result*, creating it.

    The cache is a JSON-safe dict keyed by zone_id that travels with the
    persisted scan result, so a backtest replay over the same data can read
    stored verdicts instead of calling the AI again.
    """

    if not isinstance(scan_result, dict):
        return {}
    cache = scan_result.get(AI_ZONE_AUDIT_CACHE_KEY)
    if not isinstance(cache, dict):
        cache = {}
        scan_result[AI_ZONE_AUDIT_CACHE_KEY] = cache
    return cache


def get_cached_zone_review(
    cache: Any,
    zone_id: Any,
) -> dict[str, Any] | None:
    """Return the cached valid verdict for *zone_id*, else ``None``.

    Cached entries are re-validated with the same strict schema rules, so a
    corrupted cache fails closed instead of applying a bad verdict.
    """

    if not isinstance(cache, dict):
        return None
    zone_key = str(zone_id or "").strip()
    if not zone_key:
        return None
    entry = cache.get(zone_key)
    if not isinstance(entry, dict):
        return None
    review = _normalize_zone_review(entry)
    if review.get("status") != "valid":
        return None
    return review


def remember_zone_review(cache: Any, zone_id: Any, review: Any) -> bool:
    """Store *review* under *zone_id* when it is a valid verdict.

    Only valid verdicts are cached: they are the only ones able to change a
    score, so replaying a cache miss on uncertain or failed reviews yields
    the same outcome as the original run.
    """

    if not isinstance(cache, dict) or not isinstance(review, dict):
        return False
    zone_key = str(zone_id or "").strip()
    if not zone_key or review.get("status") != "valid":
        return False
    cache[zone_key] = {
        "schema_version": review.get(
            "schema_version",
            ZONE_REVIEW_SCHEMA_VERSION,
        ),
        "status": "valid",
        "zone_validity": review.get("zone_validity"),
        "liquidity_setup": review.get("liquidity_setup"),
        "displacement_quality": review.get("displacement_quality"),
        "confidence": review.get("confidence"),
        "reasons": list(review.get("reasons") or []),
        "review_error": "",
    }
    return True


def review_zone_with_cache(
    zone_data: dict[str, Any] | None,
    zone_audit_cache: Any,
    ai_service: Any = None,
) -> dict[str, Any]:
    """Cache-through wrapper around :func:`review_selected_zone`.

    A cache hit replays the stored verdict without touching the AI.  On a
    miss the AI is consulted when available and a valid verdict is stored
    for replay.  Backtest replay passes ``ai_service=None`` so a miss
    returns the uncertain default without any AI call — reproducible and
    free.
    """

    zone_id = ""
    if isinstance(zone_data, dict):
        zone_id = str(zone_data.get("zone_id") or "").strip()
    if zone_id:
        cached = get_cached_zone_review(zone_audit_cache, zone_id)
        if cached is not None:
            return cached
    review = review_selected_zone(zone_data, ai_service)
    if zone_id:
        remember_zone_review(zone_audit_cache, zone_id, review)
    return review


def parse_zone_review(raw: str) -> dict[str, Any]:
    """Parse and strictly validate the AI verdict.

    Returns a ``valid`` verdict only when every schema constraint holds;
    otherwise returns the ``uncertain`` default with a ``review_error``.
    """

    payload = _extract_json_object(raw)
    if payload is None:
        review = default_zone_review("invalid_json")
        review["raw_response"] = str(raw or "")[:_ZONE_REVIEW_RAW_LIMIT]
        return review
    return _normalize_zone_review(payload)


def build_zone_review_prompt(zone_data: dict[str, Any]) -> str:
    payload = _zone_review_payload(zone_data)
    return (
        "Bạn là AI Zone Reviewer của AI Market Analyst. Nhiệm vụ: đánh giá chất lượng "
        "zone SMC đã được rule engine chọn. Không được tự tạo entry/SL/TP mới và "
        "không được ra lệnh giao dịch.\n"
        "Chỉ trả về JSON object hợp lệ, không markdown, không giải thích ngoài JSON.\n"
        "Schema bắt buộc:\n"
        "{\n"
        '  "zone_validity": 0-10,\n'
        '  "liquidity_setup": "strong|weak|none",\n'
        '  "displacement_quality": 0-10,\n'
        '  "confidence": 0-1,\n'
        '  "reasons": ["tối đa 8 lý do ngắn"]\n'
        "}\n"
        "Quy tắc: zone_validity là độ tin cậy của zone (0 = zone hỏng/không hợp lệ, "
        "10 = zone rất sạch). liquidity_setup=strong khi liquidity quanh zone đã được "
        "quét rõ ràng trước khi tạo zone, weak khi tín hiệu yếu, none khi không thấy. "
        "displacement_quality chấm sức mạnh của displacement tạo ra zone (0-10). "
        "confidence là độ tin cậy của chính đánh giá này (0-1). "
        "reasons liệt kê ngắn gọn các lý do chính.\n"
        "Dữ liệu zone:\n"
        f"{json.dumps(payload, ensure_ascii=False, default=str)}"
    )


def _normalize_zone_review(payload: dict[str, Any]) -> dict[str, Any]:
    zone_validity = _bounded_number(payload.get("zone_validity"), 10.0)
    displacement_quality = _bounded_number(
        payload.get("displacement_quality"),
        10.0,
    )
    confidence = _bounded_number(payload.get("confidence"), 1.0)
    liquidity_setup = _liquidity_setup(payload.get("liquidity_setup"))
    reasons = payload.get("reasons")
    if (
        zone_validity is None
        or displacement_quality is None
        or confidence is None
        or liquidity_setup is None
        or not isinstance(reasons, (list, tuple))
    ):
        return default_zone_review("invalid_schema")
    return {
        "schema_version": ZONE_REVIEW_SCHEMA_VERSION,
        "status": "valid",
        "zone_validity": zone_validity,
        "liquidity_setup": liquidity_setup,
        "displacement_quality": displacement_quality,
        "confidence": confidence,
        "reasons": _reason_list(reasons),
        "review_error": "",
    }


def _zone_review_payload(zone_data: dict[str, Any]) -> dict[str, Any]:
    price = _optional_float(zone_data.get("price"))
    low = _optional_float(zone_data.get("low"))
    high = _optional_float(zone_data.get("high"))
    atr_value = _optional_float(
        zone_data.get("atr", zone_data.get("atr_h4"))
    )
    position = str(zone_data.get("price_position") or "").strip()
    if not position:
        position = _price_position(price, low, high)
    distance_atr = None
    if (
        price is not None
        and low is not None
        and high is not None
        and atr_value
    ):
        distance_atr = round(
            _distance_to_zone(price, low, high) / atr_value,
            4,
        )
    displacement = zone_data.get("displacement")
    if displacement is None:
        displacement = zone_data.get("displacement_multiple")
    liquidity = zone_data.get("liquidity")
    if liquidity is None:
        liquidity = zone_data.get("nearby_liquidity")
    payload: dict[str, Any] = {
        "symbol": zone_data.get("symbol"),
        "zone_type": zone_data.get("zone_type") or zone_data.get("family"),
        "direction": zone_data.get("direction"),
        "timeframe": zone_data.get("timeframe"),
        "displacement": displacement,
        "price": price,
        "zone_low": low,
        "zone_high": high,
        "price_position": position,
        "distance_atr": distance_atr,
        "nearby_liquidity": liquidity,
    }
    sweep_linked = zone_data.get("liquidity_sweep_linked")
    if isinstance(sweep_linked, bool):
        payload["liquidity_sweep_linked"] = sweep_linked
    return payload


def _price_position(
    price: float | None,
    low: float | None,
    high: float | None,
) -> str:
    if price is None or low is None or high is None:
        return "unknown"
    if low <= price <= high:
        return "inside_zone"
    return "above_zone" if price > high else "below_zone"


def _distance_to_zone(price: float, low: float, high: float) -> float:
    if price < low:
        return low - price
    if price > high:
        return price - high
    return 0.0


def _bounded_number(value: object, maximum: float) -> float | None:
    """Return *value* as a float within ``[0, maximum]``, else ``None``.

    Schema violations (wrong type, NaN, out of range) yield ``None`` so the
    caller can fail closed.
    """

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number != number or number < 0 or number > maximum:
        return None
    return number


def _liquidity_setup(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized not in ZONE_REVIEW_LIQUIDITY_VALUES:
        return None
    return normalized


def _reason_list(value: object) -> list[str]:
    items = list(value) if isinstance(value, (list, tuple)) else []
    reasons: list[str] = []
    for item in items[:_ZONE_REVIEW_MAX_REASONS]:
        text = str(item).strip()[:_ZONE_REVIEW_REASON_LIMIT]
        if text:
            reasons.append(text)
    return reasons


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    # Try direct parse first
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    # Try fenced block (greedy match for nested JSON)
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        try:
            value = json.loads(fenced.group(1))
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            pass
    # Try finding outermost { ... } by bracket counting
    start = text.find("{")
    if start >= 0:
        depth = 0
        end = -1
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end > start:
            try:
                value = json.loads(text[start:end + 1])
                return value if isinstance(value, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if isfinite(result) else None
