"""Công thức chấm điểm vĩ mô 3 tier (0-30) — module THUẦN.

Port nguyên thức từ `services/news_service.py` (ca đấu nối (b), WI-2):

| Hàm ở đây | Nguồn cũ |
|---|---|
| `compute_macro_tiers` | `NewsService._compute_macro_tiers` (d.1567) |
| `macro_tier1` | `NewsService._macro_tier1` (d.1876) |
| `macro_tier2` | `NewsService._macro_tier2` (d.1979) |
| `macro_tier3` | `NewsService._macro_tier3` (d.2135) |
| `macro_data_quality` | `NewsService._macro_data_quality` (d.2333) |
| `matches_currency` | `NewsService._matches_currency` (d.2766) |
| `macro_themes` | `NewsService._macro_themes` (d.2738) |
| `geopolitical_hotspots` | `NewsService._geopolitical_hotspots` (d.2758) |
| `currency_stance` / `stance_value` / `macro_score_from_delta` | cùng tên (d.3056/d.3067/d.3071) |
| `_macro_reason` | `NewsService._build_macro_reason` (d.2516) |

Quy tắc port (plan §3.1):

* **Thuần tuyệt đối** — không I/O, không AI, không đọc đồng hồ: `now` là tham số,
  dữ liệu (rates, yield, headlines, events) do caller đưa vào. Không import
  `services`/`ui`/`controllers`/PyQt6.
* **Giữ nguyên từng hằng số**: `MAX_DIFF 5.0`, `trend_score_map`, ngưỡng spread
  (`< 0` / `> 0.5` + steepening), bucket time_weight 6/24/48h, thang sentiment
  0-8, hotspot severity.
* **Tier 2 luôn trung lập 5/5** (Phase 15C): severity × time_weight chỉ vào
  `detail`/`event_risk`.
* **AI stance bỏ hẳn** (quyết định owner 16/08/2026; verdict AI advisory-only):
  `base_stance`/`quote_stance` tính bằng `currency_stance` (keyword) — đúng đường
  "AI off" của code cũ. Kết quả trả `stance_detail` (source `"keyword"`) thay cho
  `stance_journal`; ba khóa `ai_sentiment_*` trong detail Tier 3 đóng băng ở giá
  trị AI-off của code cũ (`None`/`False`) để shape không đổi.
* **VIX** chỉ là diagnostic: `vix_level=None` mặc định → `vix_applied_to_score`
  luôn `False` (Phase 15E).

Tham số chỉ để tương thích chữ ký ở bản cũ mà thân hàm không đọc (`symbol` của
`_compute_macro_tiers`/`_macro_themes`, `themes` của `_compute_macro_tiers`) đã
được bỏ — module thuần chỉ nhận đúng thứ công thức dùng.

Bản cũ còn `_event_time` đọc `time_utc` qua `services/calendar_helpers.parse_event_time`;
module thuần không được import `services`, nên `_event_time_utc` dưới đây chép
nguyên ngữ nghĩa của hàm đó (Z → +00:00, naive coi là UTC, quy về UTC).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

__all__ = [
    "BASELINE_MACRO_SCORE",
    "CURRENCY_KEYWORDS",
    "DOVISH_TERMS",
    "EVENT_SEVERITY",
    "HAWKISH_TERMS",
    "HOTSPOT_TERMS",
    "NEGATION_WORDS",
    "SENTIMENT_LEXICON",
    "compute_macro_tiers",
    "currency_stance",
    "geopolitical_hotspots",
    "macro_data_quality",
    "macro_score_from_delta",
    "macro_themes",
    "macro_tier1",
    "macro_tier2",
    "macro_tier3",
    "matches_currency",
    "stance_value",
]

# ---------------------------------------------------------------------------
# Lexicon (port nguyên văn — news_service.py d.105-120 / d.1980 / d.2142)
# ---------------------------------------------------------------------------

CURRENCY_KEYWORDS: dict[str, list[str]] = {
    "USD": ["Fed", "FOMC", "Powell", "Treasury yields", "US yields", "dollar"],
    "JPY": ["BOJ", "BoJ", "Ueda", "Japan", "Tokyo CPI", "Tankan", "intervention", "yen"],
    "EUR": ["ECB", "Lagarde", "Eurozone", "Bund yields", "euro"],
    "GBP": ["BOE", "Bailey", "UK", "sterling", "pound"],
    "CHF": ["SNB", "Swiss CPI", "franc", "safe haven"],
    "AUD": ["RBA", "Australia CPI", "China data", "iron ore", "Aussie"],
    "NZD": ["RBNZ", "New Zealand CPI", "kiwi"],
    "CAD": ["BOC", "Canada CPI", "WTI", "oil", "loonie"],
    "XAU": ["gold", "real yields", "safe haven", "geopolitics", "central banks"],
    "XAG": ["silver", "gold/silver ratio", "industrial metals", "real yields", "PMI"],
    "BTC": ["Bitcoin", "BTC", "crypto", "spot ETF", "on-chain", "digital assets"],
}

HAWKISH_TERMS: list[str] = [
    "hike", "tightening", "hawkish", "inflation above", "yields rise", "wages rise", "intervention",
]
DOVISH_TERMS: list[str] = [
    "cut", "easing", "dovish", "slowdown", "recession", "yields fall", "weaker inflation",
]
HOTSPOT_TERMS: list[str] = [
    "war", "strike", "sanction", "tariff", "oil", "geopolitical", "Middle East", "Ukraine", "Taiwan", "risk-off",
]

EVENT_SEVERITY: dict[str, int] = {
    "nonfarm payrolls": 3, "nfp": 3, "fomc": 3, "cpi": 3, "core cpi": 3,
    "pce": 3, "gdp": 3, "interest rate decision": 3, "unemployment": 3,
    "fed": 3,
    "ism manufacturing": 2, "ism services": 2, "retail sales": 2,
    "ppi": 2, "consumer confidence": 2, "durable goods": 2,
}

SENTIMENT_LEXICON: dict[str, int] = {
    "soft landing": 3, "dovish pivot": 3, "rate cuts confirmed": 3,
    "dovish": 2, "rate cut": 2, "stimulus": 2, "optimism": 2, "breakout": 2, "goldilocks": 2,
    "rally": 1, "bullish": 1, "recovery": 1, "easing": 1, "upside": 1,
    "momentum": 1, "rotation": 1, "accommodative": 1, "expansion": 1, "rebound": 1,
    "recession": -3, "crash": -3, "default": -3, "contagion": -3, "financial crisis": -3,
    "hawkish": -2, "rate hike": -2, "tightening": -2, "collapse": -2, "turmoil": -2,
    "sell-off": -2, "panic": -2,
    "bearish": -1, "fear": -1, "downturn": -1, "pessimism": -1, "downside": -1,
    "correction": -1, "overvalued": -1, "flight to safety": -1, "stagnation": -1,
    "slowdown": -1, "bear market": -1, "debt ceiling": -1,
}

NEGATION_WORDS: set[str] = {
    "no", "not", "fade", "fades", "fading", "diminish", "diminishes",
    "ease", "eases", "eased", "subside", "subsides",
}

_SAFE_HAVENS: frozenset[str] = frozenset({"USD", "JPY", "CHF", "XAU"})
_RISK_CURRENCIES: frozenset[str] = frozenset({"AUD", "NZD", "CAD"})

# Thang legacy 0-15 (NewsService.BASELINE_MACRO_SCORE) — chỉ dùng cho
# `macro_score_from_delta`; Scanner không tiêu thụ đường này.
BASELINE_MACRO_SCORE = 7

# AI đã bị gỡ khỏi Tier 3 (Phase 15E): ba khóa này đóng băng ở giá trị AI-off
# của code cũ để shape detail không đổi cho consumer hiện hành.
_AI_OFF_SENTIMENT_SCORE = None
_AI_OFF_SENTIMENT_USED = False
_AI_OFF_APPLIED_TO_SCORE = False


# ---------------------------------------------------------------------------
# Helpers thuần
# ---------------------------------------------------------------------------


def _event_time_utc(event: object) -> datetime | None:
    """Đọc `time_utc` của một event (bản chép của `calendar_helpers.parse_event_time`)."""
    if not isinstance(event, Mapping):
        return None
    raw = event.get("time_utc") or ""
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def matches_currency(item: Mapping[str, Any], currency: str) -> bool:
    """Headline có thuộc về `currency` không (mã tiền tệ hoặc từ khóa nhận diện)."""
    text = str(item.get("title", "")).lower()
    return currency.lower() in text or any(
        keyword.lower() in text for keyword in CURRENCY_KEYWORDS.get(currency, [])
    )


def currency_stance(
    headlines: Sequence[str], hawkish_terms: Sequence[str], dovish_terms: Sequence[str]
) -> str:
    """Stance theo keyword: "hawkish" | "dovish" | "neutral"."""
    text = " ".join(headlines).lower()
    hawkish = sum(1 for term in hawkish_terms if term.lower() in text)
    dovish = sum(1 for term in dovish_terms if term.lower() in text)
    if hawkish > dovish:
        return "hawkish"
    if dovish > hawkish:
        return "dovish"
    return "neutral"


def stance_value(stance: str) -> int:
    return {"hawkish": 1, "neutral": 0, "dovish": -1}.get(stance, 0)


def macro_score_from_delta(delta: int) -> int:
    if delta >= 2:
        return 15
    if delta == 1:
        return 11
    if delta == 0:
        return BASELINE_MACRO_SCORE
    if delta == -1:
        return 4
    return 0


def macro_themes(
    currencies: Sequence[str], headlines: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Chủ đề theo từng đồng tiền (stance keyword + headline khớp)."""
    themes: list[dict[str, Any]] = []
    for currency in currencies:
        matched = [item for item in headlines if matches_currency(item, currency)]
        stance = currency_stance(
            [str(item.get("title", "")) for item in matched], HAWKISH_TERMS, DOVISH_TERMS
        )
        themes.append(
            {
                "currency": currency,
                "stance": stance,
                "headline_count": len(matched),
                "key_points": [item.get("title", "") for item in matched[:4]],
            }
        )
    return themes


def geopolitical_hotspots(
    headlines: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    hotspots = []
    for item in headlines:
        title = str(item.get("title", ""))
        if any(term.lower() in title.lower() for term in HOTSPOT_TERMS):
            hotspots.append(item)
    return hotspots[:6]


# ---------------------------------------------------------------------------
# Tier 1 — Lãi suất & chính sách tiền tệ (0-12)
# ---------------------------------------------------------------------------


def macro_tier1(
    base: str,
    quote: str,
    base_stance: str,
    quote_stance: str,
    *,
    rates: Mapping[str, Mapping[str, Any]],
    yield_payload: Mapping[str, Any] | None = None,
) -> tuple[int, int, dict[str, Any]]:
    """Tier 1: rate differential (0-4) + rate trend (0-4) + stance (0-4) + yield (±2/±1)."""
    base_info = rates.get(base, {})
    quote_info = rates.get(quote, {})

    # Rate differential score (0-4) — linear scale
    MAX_DIFF = 5.0
    rate_diff = float(base_info.get("rate", 0)) - float(quote_info.get("rate", 0))
    diff_score = round(4 * abs(rate_diff) / MAX_DIFF)
    diff_score = max(0, min(4, diff_score))
    if rate_diff >= 0:
        diff_buy, diff_sell = diff_score, 0
    else:
        diff_buy, diff_sell = 0, diff_score

    # Rate trend score (0-4)
    trend_score_map = {"hike": 4, "hold": 2, "cut": 0}
    base_trend = int(trend_score_map.get(str(base_info.get("trend", "hold")), 2))
    quote_trend = int(trend_score_map.get(str(quote_info.get("trend", "hold")), 2))
    trend_diff = base_trend - quote_trend
    if trend_diff >= 3:
        trend_buy, trend_sell = 4, 0
    elif trend_diff in (1, 2):
        trend_buy, trend_sell = 3, 1
    elif trend_diff == 0:
        trend_buy, trend_sell = 2, 2
    elif trend_diff in (-1, -2):
        trend_buy, trend_sell = 1, 3
    else:
        trend_buy, trend_sell = 0, 4

    # Stance score from headlines (0-4)
    stance_delta = stance_value(base_stance) - stance_value(quote_stance)
    if stance_delta >= 2:
        stance_buy, stance_sell = 4, 0
    elif stance_delta == 1:
        stance_buy, stance_sell = 3, 1
    elif stance_delta == 0:
        stance_buy, stance_sell = 2, 2
    elif stance_delta == -1:
        stance_buy, stance_sell = 1, 3
    else:
        stance_buy, stance_sell = 0, 4

    # Yield spread 2s10s adjustment (USD pairs only)
    yield_adj_buy = 0
    yield_adj_sell = 0
    yield_payload = yield_payload or {
        "spread": None,
        "tnx": None,
        "fvx": None,
        "steepening": None,
        "ten_year_yield": None,
        "five_year_yield": None,
    }
    spread_val = yield_payload.get("spread")
    if spread_val is not None and "USD" in (base, quote):
        if spread_val < 0:
            if base == "USD":
                yield_adj_buy, yield_adj_sell = -2, 2
            else:
                yield_adj_buy, yield_adj_sell = 2, -2
        elif spread_val > 0.5 and yield_payload.get("steepening"):
            if base == "USD":
                yield_adj_buy, yield_adj_sell = 1, -1
            else:
                yield_adj_buy, yield_adj_sell = -1, 1

    detail = {
        "base_rate": base_info.get("rate_label", "--"),
        "quote_rate": quote_info.get("rate_label", "--"),
        "rate_differential": round(rate_diff, 2),
        "base_trend": base_info.get("trend", "hold"),
        "quote_trend": quote_info.get("trend", "hold"),
        "base_stance": base_stance,
        "quote_stance": quote_stance,
        "yield_spread_2s10s": spread_val,  # deprecated alias (10Y-5Y)
        "yield_spread_10y_5y": spread_val,  # Phase 15F.2: canonical name
        "ten_year_yield": yield_payload.get("ten_year_yield"),
        "five_year_yield": yield_payload.get("five_year_yield"),
        "yield_spread_tnx": yield_payload.get("tnx"),
        "yield_spread_fvx": yield_payload.get("fvx"),
        "yield_spread_steepening": yield_payload.get("steepening"),
        "yield_spread_adj": {"buy": yield_adj_buy, "sell": yield_adj_sell},
        "components": {
            "rate_diff": {"buy": diff_buy, "sell": diff_sell},
            "rate_trend": {"buy": trend_buy, "sell": trend_sell},
            "stance": {"buy": stance_buy, "sell": stance_sell},
        },
    }
    return (
        max(0, min(12, diff_buy + trend_buy + stance_buy + yield_adj_buy)),
        max(0, min(12, diff_sell + trend_sell + stance_sell + yield_adj_sell)),
        detail,
    )


# ---------------------------------------------------------------------------
# Tier 2 — Lịch kinh tế (0-10; runtime luôn 5/5)
# ---------------------------------------------------------------------------


def macro_tier2(
    base: str,
    quote: str,
    events: Sequence[Mapping[str, Any]],
    *,
    now: datetime,
) -> tuple[int, int, dict[str, Any]]:
    """Tier 2: directional LUÔN 5/5 (Phase 15C); severity × time_weight vào detail."""
    cutoff = now + timedelta(hours=72)

    base_quality = 0
    quote_quality = 0
    base_total = 0
    quote_total = 0
    base_events_detail: list[dict[str, Any]] = []
    quote_events_detail: list[dict[str, Any]] = []
    has_surprise = False  # Phase 15C: track if any event has actual/forecast

    for event in events:
        currency = str(event.get("currency", ""))
        title = str(event.get("event", "")).lower()
        event_time = _event_time_utc(event)
        if not event_time or event_time > cutoff:
            continue

        hours_until = max(0.0, (event_time - now).total_seconds() / 3600.0)
        if hours_until < 6:
            time_weight = 3.0
        elif hours_until < 24:
            time_weight = 2.0
        elif hours_until < 48:
            time_weight = 1.5
        else:
            time_weight = 1.0

        severity = 1
        for key, sev in EVENT_SEVERITY.items():
            if key in title:
                severity = sev
                break

        quality_raw = severity * time_weight
        quality = int(quality_raw)
        if quality_raw > quality:
            quality += 1

        # Phase 15C: check for actual-vs-forecast surprise data
        actual = event.get("actual")
        forecast = event.get("forecast")
        has_event_surprise = False
        try:
            if actual is not None and forecast is not None:
                actual_f = float(str(actual).replace("%", ""))
                forecast_f = float(str(forecast).replace("%", ""))
                if forecast_f != 0:
                    has_event_surprise = True
                    has_surprise = True
        except (ValueError, TypeError):
            pass

        event_info = {
            "title": str(event.get("event", "")),
            "time": event_time.isoformat(),
            "hours_until": round(hours_until, 1),
            "severity": severity,
            "time_weight": time_weight,
            "quality": quality,
            "has_surprise": has_event_surprise,
        }

        if currency == base:
            base_total += 1
            base_quality += quality
            base_events_detail.append(event_info)
        elif currency == quote:
            quote_total += 1
            quote_quality += quality
            quote_events_detail.append(event_info)

    # Phase 15C.1: calendar events are ALWAYS directional-neutral
    # until a standardized surprise-direction engine is implemented.
    # actual/forecast are tracked as diagnostic only (has_surprise_data).
    buy_cal = 5
    sell_cal = 5
    buy_cal = max(1, min(9, buy_cal))
    sell_cal = max(1, min(9, sell_cal))

    # Phase 15C: event risk diagnostic (severity × time, direction-neutral)
    total_risk = base_quality + quote_quality
    if total_risk >= 8:
        risk_level = "high"
    elif total_risk >= 4:
        risk_level = "medium"
    elif total_risk > 0:
        risk_level = "low"
    else:
        risk_level = "none"

    detail = {
        "base_event_count": base_total,
        "quote_event_count": quote_total,
        "base_quality": base_quality,
        "quote_quality": quote_quality,
        "next_72h_events": len(events),
        "has_surprise_data": has_surprise,
        "event_risk_score": total_risk,
        "event_risk_level": risk_level,
        "base_events": base_events_detail,
        "quote_events": quote_events_detail,
    }
    return (buy_cal, sell_cal, detail)


# ---------------------------------------------------------------------------
# Tier 3 — Tâm lý rủi ro & địa chính trị (0-12)
# ---------------------------------------------------------------------------


def macro_tier3(
    currencies: Sequence[str],
    headlines: Sequence[Mapping[str, Any]],
    hotspots: Sequence[Mapping[str, Any]],
    *,
    vix_level: float | None = None,
) -> tuple[int, int, dict[str, Any]]:
    """Tier 3: sentiment keyword (0-8) + geopolitical (0-4). VIX/AI chỉ diagnostic."""
    all_text = " ".join(str(item.get("title", "")) for item in headlines).lower()

    base = currencies[0] if currencies else ""
    quote = currencies[1] if len(currencies) > 1 else ""

    base_is_safe = base in _SAFE_HAVENS
    quote_is_safe = quote in _SAFE_HAVENS
    base_is_risk = base in _RISK_CURRENCIES
    quote_is_risk = quote in _RISK_CURRENCIES

    # --- Keyword lexicon scoring ---
    raw_sentiment = 0
    matched_terms: list[dict[str, Any]] = []
    sorted_terms = sorted(SENTIMENT_LEXICON.items(), key=lambda x: -len(x[0]))
    scanned_positions: set[int] = set()
    for term, weight in sorted_terms:
        idx = 0
        while True:
            idx = all_text.find(term, idx)
            if idx == -1:
                break
            end = idx + len(term)
            if any(idx <= p < end for p in scanned_positions):
                idx += 1
                continue
            for p in range(idx, end):
                scanned_positions.add(p)
            pre_text = all_text[max(0, idx - 50):idx].strip()
            pre_words = pre_text.split()
            post_text = all_text[end:end + 50].strip()
            post_words = post_text.split()
            negated = any(w in NEGATION_WORDS for w in pre_words[-3:]) or \
                      any(w in NEGATION_WORDS for w in post_words[:3])
            effective_weight = -weight if negated else weight
            raw_sentiment += effective_weight
            matched_terms.append(
                {"term": term, "weight": weight, "effective": effective_weight, "negated": negated}
            )
            idx = end

    # --- VIX adjustment (Phase 15E: diagnostic only, never added to raw_sentiment) ---
    vix_adj = 0
    if vix_level is not None:
        if vix_level < 15:
            vix_adj = 2
        elif vix_level < 20:
            vix_adj = 0
        elif vix_level < 25:
            vix_adj = -1
        elif vix_level < 30:
            vix_adj = -2
        else:
            vix_adj = -3

    # --- Map raw sentiment to 0-8 ---
    MAX_ABS = 12.0
    raw_clamped = max(-MAX_ABS, min(MAX_ABS, raw_sentiment))
    sentiment_0_8 = int(round(4.0 + raw_clamped * 4.0 / MAX_ABS))
    sentiment_0_8 = max(0, min(8, sentiment_0_8))

    # --- Convert sentiment to buy/sell (0-8) ---
    deviation = sentiment_0_8 - 4
    abs_dev = abs(deviation) / 4.0
    if deviation > 0:
        sentiment_label = "risk_on"
        if base_is_risk and not quote_is_risk:
            risk_buy = int(round(2 + abs_dev * 6)); risk_sell = int(round(2 - abs_dev * 2))
        elif base_is_safe and not quote_is_safe:
            risk_buy = int(round(2 - abs_dev * 2)); risk_sell = int(round(2 + abs_dev * 6))
        elif quote_is_risk and not base_is_risk:
            risk_buy = int(round(2 - abs_dev * 2)); risk_sell = int(round(2 + abs_dev * 6))
        elif quote_is_safe and not base_is_safe:
            risk_buy = int(round(2 + abs_dev * 6)); risk_sell = int(round(2 - abs_dev * 2))
        else:
            risk_buy = 4; risk_sell = 4
    elif deviation < 0:
        sentiment_label = "risk_off"
        if base_is_safe and not quote_is_safe:
            risk_buy = int(round(2 + abs_dev * 6)); risk_sell = int(round(2 - abs_dev * 2))
        elif base_is_risk and not quote_is_risk:
            risk_buy = int(round(2 - abs_dev * 2)); risk_sell = int(round(2 + abs_dev * 6))
        elif quote_is_safe and not base_is_safe:
            risk_buy = int(round(2 - abs_dev * 2)); risk_sell = int(round(2 + abs_dev * 6))
        elif quote_is_risk and not base_is_risk:
            risk_buy = int(round(2 + abs_dev * 6)); risk_sell = int(round(2 - abs_dev * 2))
        else:
            risk_buy = 4; risk_sell = 4
    else:
        sentiment_label = "neutral"
        risk_buy, risk_sell = 4, 4
    risk_buy = max(0, min(8, risk_buy))
    risk_sell = max(0, min(8, risk_sell))

    # Geopolitical score (0-4)
    hotspot_severity = 0
    for hotspot in hotspots:
        title = str(hotspot.get("title", "")).lower()
        if any(t in title for t in ["war", "strike"]):
            hotspot_severity += 2
        elif any(t in title for t in ["sanction", "tariff"]):
            hotspot_severity += 1
        else:
            hotspot_severity += 1
    hotspot_severity = min(4, hotspot_severity)

    if hotspot_severity >= 3:
        if base_is_safe:
            geo_buy, geo_sell = 3, 1
        elif quote_is_safe:
            geo_buy, geo_sell = 1, 3
        else:
            geo_buy, geo_sell = 2, 2
    elif hotspot_severity >= 1:
        if base_is_safe:
            geo_buy, geo_sell = 3, 1
        elif quote_is_safe:
            geo_buy, geo_sell = 1, 3
        else:
            geo_buy, geo_sell = 2, 2
    else:
        geo_buy, geo_sell = 2, 2

    detail = {
        "risk_sentiment": sentiment_label,
        "sentiment_score_0_8": sentiment_0_8,
        "raw_sentiment": raw_sentiment,
        "ai_sentiment_used": _AI_OFF_SENTIMENT_USED,
        "ai_sentiment_score": _AI_OFF_SENTIMENT_SCORE,
        "ai_applied_to_score": _AI_OFF_APPLIED_TO_SCORE,
        "matched_terms": matched_terms,
        "vix_level": vix_level,
        "vix_adjustment": vix_adj,
        "vix_applied_to_score": False,  # Phase 15E: only correlation_adjustment contributes
        "hotspot_count": len(hotspots),
        "hotspot_severity": hotspot_severity,
        "components": {
            "risk_sentiment": {"buy": risk_buy, "sell": risk_sell},
            "geopolitical": {"buy": geo_buy, "sell": geo_sell},
        },
    }
    return (risk_buy + geo_buy, risk_sell + geo_sell, detail)


# ---------------------------------------------------------------------------
# Macro data quality (0.0-1.0)
# ---------------------------------------------------------------------------


def macro_data_quality(
    headlines: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
    *,
    now: datetime,
) -> float:
    """Độ tin cậy dữ liệu vĩ mô (0.0-1.0) theo độ tươi headline + độ phủ event."""
    confidence = 1.0

    if headlines:
        newest = None
        for h in headlines:
            pub = h.get("published_utc", "")
            if pub:
                try:
                    t = datetime.fromisoformat(str(pub).replace("Z", "+00:00"))
                    if newest is None or t > newest:
                        newest = t
                except ValueError:
                    pass
        if newest:
            age_hours = (now - newest).total_seconds() / 3600
            if age_hours > 12:
                confidence -= 0.15
            elif age_hours > 6:
                confidence -= 0.10
            elif age_hours > 3:
                confidence -= 0.05
    else:
        confidence -= 0.30

    if len(headlines) < 3:
        confidence -= 0.10
    if len(headlines) == 0:
        confidence -= 0.10

    if not events:
        confidence -= 0.10

    return max(0.10, confidence)


# ---------------------------------------------------------------------------
# Tổng hợp
# ---------------------------------------------------------------------------


def _macro_reason(
    base: str,
    quote: str,
    base_stance: str,
    quote_stance: str,
    tier2_detail: Mapping[str, Any],
    tier3_detail: Mapping[str, Any],
    *,
    rates: Mapping[str, Mapping[str, Any]],
) -> str:
    """Câu giải thích ngắn cho một phía (port `_build_macro_reason`)."""
    base_rate = rates.get(base, {}).get("rate_label", "--")
    quote_rate = rates.get(quote, {}).get("rate_label", "--")

    stance_map = {"hawkish": "Thắt chặt", "dovish": "Nới lỏng", "neutral": "Trung tính"}
    bs_vn = stance_map.get(str(base_stance).lower(), base_stance)
    qs_vn = stance_map.get(str(quote_stance).lower(), quote_stance)

    sent_raw = str(tier3_detail.get('risk_sentiment', 'neutral')).lower()
    sent_map = {"risk_on": "Chấp nhận rủi ro", "risk_off": "Né tránh rủi ro", "neutral": "Trung tính"}
    sent_vn = sent_map.get(sent_raw, sent_raw)

    parts = [
        f"[T1] {base}={base_rate}({bs_vn}) so với {quote}={quote_rate}({qs_vn})",
        f"[T2] Sự kiện lịch KT: base={tier2_detail.get('base_event_weight', 0)}, quote={tier2_detail.get('quote_event_weight', 0)}",
        f"[T3] Tâm lý TT={sent_vn}, điểm nóng={tier3_detail.get('hotspot_count', 0)}",
    ]
    return " | ".join(parts)


def compute_macro_tiers(
    currencies: Sequence[str],
    headlines: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
    hotspots: Sequence[Mapping[str, Any]],
    *,
    rates: Mapping[str, Mapping[str, Any]],
    yield_payload: Mapping[str, Any] | None,
    now: datetime,
    vix_level: float | None = None,
) -> dict[str, Any]:
    """Tổng hợp 3 tier → shape cũ của `_compute_macro_tiers`.

    Stance lấy từ keyword (`currency_stance`) — đúng đường "AI off" của code cũ;
    `stance_detail` thay `stance_journal` với `source="keyword"`.
    """
    base = currencies[0] if currencies else ""
    quote = currencies[1] if len(currencies) > 1 else ""
    base_headlines = [str(h.get("title", "")) for h in headlines if matches_currency(h, base)]
    quote_headlines = [str(h.get("title", "")) for h in headlines if matches_currency(h, quote)]
    base_stance = currency_stance(base_headlines, HAWKISH_TERMS, DOVISH_TERMS)
    quote_stance = currency_stance(quote_headlines, HAWKISH_TERMS, DOVISH_TERMS)

    tier1_buy, tier1_sell, tier1_detail = macro_tier1(
        base,
        quote,
        base_stance,
        quote_stance,
        rates=rates,
        yield_payload=yield_payload,
    )
    tier2_buy, tier2_sell, tier2_detail = macro_tier2(base, quote, events, now=now)
    tier3_buy, tier3_sell, tier3_detail = macro_tier3(
        currencies, headlines, hotspots, vix_level=vix_level
    )

    raw_buy = tier1_buy + tier2_buy + tier3_buy
    raw_sell = tier1_sell + tier2_sell + tier3_sell

    return {
        "tier1": {"buy": tier1_buy, "sell": tier1_sell, "detail": tier1_detail},
        "tier2": {"buy": tier2_buy, "sell": tier2_sell, "detail": tier2_detail},
        "tier3": {"buy": tier3_buy, "sell": tier3_sell, "detail": tier3_detail},
        "raw_total": {"buy": raw_buy, "sell": raw_sell},
        "alignment": {"buy": raw_buy, "sell": raw_sell},
        "reasons": {
            "buy": _macro_reason(
                base, quote, base_stance, quote_stance,
                tier2_detail, tier3_detail, rates=rates,
            ),
            "sell": _macro_reason(
                base, quote, base_stance, quote_stance,
                tier2_detail, tier3_detail, rates=rates,
            ),
        },
        # Stance từng đồng tiền (keyword). Bản cũ là `stance_journal` với chi tiết
        # AI; AI đã gỡ nên `source` đổi "fallback" → "keyword" (chênh lệch đã duyệt).
        "stance_detail": {
            "base": {
                "currency": base,
                "stance": base_stance,
                "strength": None,
                "confidence": None,
                "source": "keyword",
            },
            "quote": {
                "currency": quote,
                "stance": quote_stance,
                "strength": None,
                "confidence": None,
                "source": "keyword",
            },
        },
    }
