from __future__ import annotations

import json
import re
from email.utils import parsedate_to_datetime
from html import unescape
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from config.paths import app_data_dir


class NewsService:
    FOREX_FACTORY_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    FOREX_FACTORY_HTML_URL = "https://www.forexfactory.com/calendar?week=this"
    CALENDAR_CACHE_MAX_AGE = timedelta(hours=12)
    CALENDAR_CACHE_FILE: Path | None = None
    HIGH_IMPACT_VALUES = {"high", "red", "cao"}
    BASELINE_MACRO_SCORE = 7
    BASELINE_MACRO_SCORE_30 = 15  # neutral midpoint for 0-30 scale
    CURRENCY_KEYWORDS = {
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
    HAWKISH_TERMS = ["hike", "tightening", "hawkish", "inflation above", "yields rise", "wages rise", "intervention"]
    DOVISH_TERMS = ["cut", "easing", "dovish", "slowdown", "recession", "yields fall", "weaker inflation"]
    HOTSPOT_TERMS = ["war", "strike", "sanction", "tariff", "oil", "geopolitical", "Middle East", "Ukraine", "Taiwan", "risk-off"]
    _calendar_cache: dict[str, tuple[datetime, list[dict[str, object]]]] = {}
    _interest_rates: dict[str, object] | None = None
    _tier_scores_cache: dict[str, dict[str, object]] = {}
    _last_fetch_time: datetime | None = None

    # ------------------------------------------------------------------
    # Interest rate config
    # ------------------------------------------------------------------
    @classmethod
    def _load_interest_rates(cls) -> dict[str, object]:
        if cls._interest_rates is not None:
            return cls._interest_rates
        try:
            path = Path(__file__).resolve().parents[1] / "config" / "interest_rates.json"
            raw = json.loads(path.read_text(encoding="utf-8"))
            cls._interest_rates = raw.get("currencies", {})
        except Exception:
            cls._interest_rates = {}
        return cls._interest_rates

    def rate_info(self, currency: str) -> dict[str, object]:
        rates = self._load_interest_rates()
        return rates.get(currency, {})

    def rate_differential(self, base: str, quote: str) -> float:
        """Returns base_rate - quote_rate differential."""
        rates = self._load_interest_rates()
        base_rate = float(rates.get(base, {}).get("rate", 0))
        quote_rate = float(rates.get(quote, {}).get("rate", 0))
        return base_rate - quote_rate

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def latest_macro_context(self, symbol: str, *, include_latest_statements: bool = True) -> dict[str, object]:
        cache_key = f"{symbol}_{include_latest_statements}"
        if cache_key in self._tier_scores_cache and self._tier_scores_cache[cache_key] is not None:
            return self._tier_scores_cache[cache_key]

        currencies = [part for part in symbol.split("/") if part]
        calendar = self._calendar_events(currencies)
        events = calendar["events"]
        calendar_source = str(calendar["source"])
        calendar_warning = str(calendar["warning"])
        headlines = self._get_headlines(symbol, currencies)
        latest_statements = self._latest_official_statements() if include_latest_statements else []
        themes = self._macro_themes(symbol, currencies, headlines)
        hotspots = self._geopolitical_hotspots(headlines + latest_statements)

        # Three-tier macro scoring (0-30 scale)
        tier_scores = self._compute_macro_tiers(symbol, currencies, headlines, events, themes, hotspots)
        data_quality = self._macro_data_quality(headlines, events)
        # Khong set _last_fetch_time neu dang preload (tranh ghi de thoi gian thuc)
        if not hasattr(self, '_preloading') or not self._preloading:
            self._last_fetch_time = datetime.now(UTC)

        return {
            "symbol": symbol,
            "source": calendar_source,
            "events": events,
            "latest_headlines": headlines,
            "latest_statements": latest_statements,
            "macro_themes": themes,
            "geopolitical_hotspots": hotspots,
            "macro_alignment_scores": tier_scores["alignment"],
            "macro_alignment_reasons": tier_scores["reasons"],
            "macro_tier_detail": {
                "tier1_interest_rate": tier_scores["tier1"],
                "tier2_calendar": tier_scores["tier2"],
                "tier3_sentiment": tier_scores["tier3"],
                "data_confidence": round(data_quality, 2),
                "macro_score_raw": tier_scores["raw_total"],
            },
            "macro_data_quality": data_quality,
            "warning": calendar_warning
            or ("" if events else "Không có dữ liệu sự kiện kinh tế sắp tới khớp cặp tiền trong nguồn đã kiểm tra."),
        }

    def data_quality_flags(
        self,
        symbol: str,
        *,
        buffer_minutes: int = 30,
        include_latest_statements: bool = True,
    ) -> dict[str, object]:
        context = self.latest_macro_context(symbol, include_latest_statements=include_latest_statements)
        events = context.get("events", [])
        if not isinstance(events, list):
            events = []
        now = datetime.now(UTC)
        high_events = [
            event
            for event in events
            if _is_high_impact(str(event.get("impact", "")))
            and _event_time(event) is not None
            and _event_time(event) >= now
        ]
        next_high = min(high_events, key=lambda event: _event_time(event) or now) if high_events else None
        event_time = _event_time(next_high) if next_high else None
        hours_until = ((event_time - now).total_seconds() / 3600) if event_time else None
        resume_after = (event_time + timedelta(minutes=buffer_minutes)).isoformat() if event_time else None
        return {
            "macro_context": context,
            "news_in_3h": bool(hours_until is not None and 0 <= hours_until <= 3),
            "high_impact_event_within_30m": bool(hours_until is not None and 0 <= hours_until <= 0.5),
            "next_high_impact_event": next_high,
            "resume_after": resume_after,
        }

    def preload_macro_contexts(self, symbols: list[str]) -> None:
        """Pre-fetch RSS (1 query tong quat) + calendar + compute tier scores."""
        if not symbols:
            return

        # Buoc 1: Fetch calendar 1 lan
        first = symbols[0]
        currencies_first = [part for part in first.split("/") if part]
        self._calendar_events(currencies_first)

        # Buoc 2: Fetch RSS headlines 1 lan duy nhat (query tong quat cho ca forex)
        # MOI: Thay vi goi _macro_headlines 29 lan, chi goi 1 lan voi query tong quat
        self._global_headlines: list[dict[str, object]] = self._fetch_global_forex_headlines()
        self._latest_official_statements()

        # Buoc 3: Pre-compute macro context cho TAT CA symbols
        # latest_macro_context se dung _global_headlines thay vi goi _macro_headlines
        self._preloading = True
        try:
            for symbol in symbols:
                for include_stmts in (True,):
                    ctx = self.latest_macro_context(symbol, include_latest_statements=include_stmts)
                    cache_key = f"{symbol}_{include_stmts}"
                    self._tier_scores_cache[cache_key] = ctx
        finally:
            self._preloading = False

        self._last_fetch_time = datetime.now(UTC)

    def _fetch_global_forex_headlines(self) -> list[dict[str, object]]:
        """Fetch 1 query tong quat de lay headlines cho toan bo cac cap tien te."""
        rows: list[dict[str, object]] = []
        seen: set[str] = set()
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        broad_queries = [
            "forex central bank Fed ECB BOJ BOE rate decision macro latest",
            "global macro risk sentiment dollar yen euro pound forex markets",
            "forex geopolitical oil gold safe haven latest",
        ]
        for query in broad_queries:
            url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=en-US&gl=US&ceid=US:en"
            for item in self._rss_items(url, query=query):
                title_key = str(item.get("title", "")).lower()
                if not title_key or title_key in seen:
                    continue
                published = parse_rss_time(str(item.get("published_utc", "")))
                if not published or published < cutoff:
                    continue
                seen.add(title_key)
                rows.append(item)
        return rows

    def _get_headlines(self, symbol: str, currencies: list[str]) -> list[dict[str, object]]:
        """Lay headlines cho symbol tu cache neu co, hoac fetch rieng."""
        global_headlines = getattr(self, '_global_headlines', None)
        if global_headlines is not None:
            return [h for h in global_headlines if self._filter_by_currencies(h, currencies)]
        return self._macro_headlines(symbol, currencies)

    def _filter_by_currencies(self, item: dict[str, object], currencies: list[str]) -> bool:
        """Kiem tra item co lien quan den bat ky currency nao khong."""
        title = str(item.get("title", "")).lower()
        for currency in currencies:
            if currency.lower() in title:
                return True
            for keyword in self.CURRENCY_KEYWORDS.get(currency, []):
                if keyword.lower() in title:
                    return True
        return True  # Fallback: keep global headline

    def macro_data_age_minutes(self) -> int:
        if self._last_fetch_time is None:
            return 9999
        delta = datetime.now(UTC) - self._last_fetch_time
        return int(delta.total_seconds() / 60)

    def macro_freshness_status(self) -> dict[str, object]:
        age = self.macro_data_age_minutes()
        if age < 240:
            status = "fresh"
            multiplier = 1.0
        elif age < 1440:
            status = "stale"
            multiplier = 0.85
        else:
            status = "expired"
            multiplier = 0.6
        return {
            "status": status,
            "age_minutes": age,
            "confidence_multiplier": multiplier,
        }

    # ------------------------------------------------------------------
    # Macro Tier Scoring (3 tiers, total 0-30)
    # ------------------------------------------------------------------
    def _compute_macro_tiers(
        self,
        symbol: str,
        currencies: list[str],
        headlines: list[dict[str, object]],
        events: list[dict[str, object]],
        themes: list[dict[str, object]],
        hotspots: list[dict[str, object]],
    ) -> dict[str, object]:
        base = currencies[0] if currencies else ""
        quote = currencies[1] if len(currencies) > 1 else ""
        base_stance = currency_stance(
            [str(item.get("title", "")) for item in headlines if self._matches_currency(item, base)],
            self.HAWKISH_TERMS,
            self.DOVISH_TERMS,
        )
        quote_stance = currency_stance(
            [str(item.get("title", "")) for item in headlines if self._matches_currency(item, quote)],
            self.HAWKISH_TERMS,
            self.DOVISH_TERMS,
        )

        tier1_buy, tier1_sell, tier1_detail = self._macro_tier1(base, quote, base_stance, quote_stance)
        tier2_buy, tier2_sell, tier2_detail = self._macro_tier2(base, quote, events)
        tier3_buy, tier3_sell, tier3_detail = self._macro_tier3(currencies, headlines, hotspots)

        raw_buy = tier1_buy + tier2_buy + tier3_buy
        raw_sell = tier1_sell + tier2_sell + tier3_sell

        return {
            "tier1": {"buy": tier1_buy, "sell": tier1_sell, "detail": tier1_detail},
            "tier2": {"buy": tier2_buy, "sell": tier2_sell, "detail": tier2_detail},
            "tier3": {"buy": tier3_buy, "sell": tier3_sell, "detail": tier3_detail},
            "raw_total": {"buy": raw_buy, "sell": raw_sell},
            "alignment": {"buy": raw_buy, "sell": raw_sell},
            "reasons": {
                "buy": self._build_macro_reason(base, quote, base_stance, quote_stance, "buy", tier1_detail, tier2_detail, tier3_detail),
                "sell": self._build_macro_reason(base, quote, base_stance, quote_stance, "sell", tier1_detail, tier2_detail, tier3_detail),
            },
        }

    # --- Tier 1: Interest Rate & Monetary Policy (0-12) ---
    # Weights: rate_diff 0-2, trend 0-5, stance 0-5 = total 0-12
    # Trend and stance dominate because markets care more about where rates are GOING
    def _macro_tier1(self, base: str, quote: str, base_stance: str, quote_stance: str) -> tuple[int, int, dict[str, object]]:
        rates = self._load_interest_rates()
        base_info = rates.get(base, {})
        quote_info = rates.get(quote, {})

        # Rate differential score (0-2): absolute level matters less
        rate_diff = self.rate_differential(base, quote)
        if rate_diff > 2.0:
            diff_buy, diff_sell = 2, 0
        elif rate_diff > 0.5:
            diff_buy, diff_sell = 1, 0
        elif rate_diff > -0.5:
            diff_buy, diff_sell = 1, 1
        elif rate_diff > -2.0:
            diff_buy, diff_sell = 0, 1
        else:
            diff_buy, diff_sell = 0, 2

        # Rate trend score (0-5): direction of change dominates
        trend_score_map = {"hike": 5, "hold": 2, "cut": 0}
        base_trend = int(trend_score_map.get(str(base_info.get("trend", "hold")), 2))
        quote_trend = int(trend_score_map.get(str(quote_info.get("trend", "hold")), 2))
        trend_diff = base_trend - quote_trend
        if trend_diff >= 3:
            trend_buy, trend_sell = 5, 0
        elif trend_diff in (1, 2):
            trend_buy, trend_sell = 3, 2
        elif trend_diff == 0:
            trend_buy, trend_sell = 2, 2
        elif trend_diff in (-1, -2):
            trend_buy, trend_sell = 2, 3
        else:
            trend_buy, trend_sell = 0, 5

        # Stance score from headlines (0-5): real-time sentiment
        stance_delta = stance_value(base_stance) - stance_value(quote_stance)
        if stance_delta >= 2:
            stance_buy, stance_sell = 5, 0
        elif stance_delta == 1:
            stance_buy, stance_sell = 4, 1
        elif stance_delta == 0:
            stance_buy, stance_sell = 2, 2
        elif stance_delta == -1:
            stance_buy, stance_sell = 1, 4
        else:
            stance_buy, stance_sell = 0, 5

        detail = {
            "base_rate": base_info.get("rate_label", "--"),
            "quote_rate": quote_info.get("rate_label", "--"),
            "rate_differential": round(rate_diff, 2),
            "base_trend": base_info.get("trend", "hold"),
            "quote_trend": quote_info.get("trend", "hold"),
            "base_stance": base_stance,
            "quote_stance": quote_stance,
            "components": {
                "rate_diff": {"buy": diff_buy, "sell": diff_sell},
                "rate_trend": {"buy": trend_buy, "sell": trend_sell},
                "stance": {"buy": stance_buy, "sell": stance_sell},
            },
        }
        return (diff_buy + trend_buy + stance_buy, diff_sell + trend_sell + stance_sell, detail)

    # --- Tier 2: Economic Calendar Impact (0-10) ---
    # Calendar events create timing uncertainty — penalize the exposed side.
    # Base 5 for each side; high-impact events on a currency reduce that side's score.
    def _macro_tier2(self, base: str, quote: str, events: list[dict[str, object]]) -> tuple[int, int, dict[str, object]]:
        whitelist = self._high_impact_whitelist()
        now = datetime.now(UTC)
        cutoff = now + timedelta(hours=72)

        base_quality = 0  # count of high-importance events for base
        quote_quality = 0  # count of high-importance events for quote
        base_total = 0
        quote_total = 0

        for event in events:
            currency = str(event.get("currency", ""))
            impact = str(event.get("impact", "")).lower()
            title = str(event.get("event", "")).lower()
            event_time = _event_time(event)
            if not event_time or event_time > cutoff:
                continue
            is_high = _is_high_impact(impact) or any(
                keyword.lower() in title for keyword in whitelist
            )
            if currency == base:
                base_total += 1
                if is_high:
                    base_quality += 1
            elif currency == quote:
                quote_total += 1
                if is_high:
                    quote_quality += 1

        # Events on a currency → uncertainty for positions exposed to that currency
        # BUY = long base + short quote → penalized by base events, helped by quote events
        # SELL = short base + long quote → penalized by quote events, helped by base events
        buy_cal = 5 - min(2, base_quality) + min(2, quote_quality)
        sell_cal = 5 - min(2, quote_quality) + min(2, base_quality)
        buy_cal = max(1, min(9, buy_cal))
        sell_cal = max(1, min(9, sell_cal))

        detail = {
            "base_event_count": base_total,
            "quote_event_count": quote_total,
            "base_high_impact": base_quality,
            "quote_high_impact": quote_quality,
            "next_72h_events": len(events),
        }
        return (buy_cal, sell_cal, detail)

    # --- Tier 3: Risk Sentiment & Geopolitical (0-8) ---
    def _macro_tier3(
        self, currencies: list[str], headlines: list[dict[str, object]], hotspots: list[dict[str, object]]
    ) -> tuple[int, int, dict[str, object]]:
        all_text = " ".join(str(item.get("title", "")) for item in headlines).lower()

        # Risk sentiment: count risk-on vs risk-off terms
        risk_on_terms = ["risk-on", "rally", "bullish", "soft landing", "goldilocks", "stimulus", "recovery"]
        risk_off_terms = ["risk-off", "sell-off", "bearish", "recession", "crash", "fear", "panic", "flight to safety"]

        risk_on_count = sum(1 for t in risk_on_terms if t in all_text)
        risk_off_count = sum(1 for t in risk_off_terms if t in all_text)

        # Risk-off → favors safe havens (USD, JPY, CHF, XAU) and hurts risk currencies (AUD, NZD, CAD)
        base = currencies[0] if currencies else ""
        quote = currencies[1] if len(currencies) > 1 else ""
        safe_havens = {"USD", "JPY", "CHF", "XAU"}
        risk_currencies = {"AUD", "NZD", "CAD"}

        base_is_safe = base in safe_havens
        quote_is_safe = quote in safe_havens
        base_is_risk = base in risk_currencies
        quote_is_risk = quote in risk_currencies

        # Base risk sentiment (0-4)
        if risk_off_count > risk_on_count:
            sentiment = "risk_off"
            if base_is_safe and not quote_is_safe:
                risk_buy, risk_sell = 4, 0
            elif base_is_risk and not quote_is_risk:
                risk_buy, risk_sell = 0, 4
            elif quote_is_safe and not base_is_safe:
                risk_buy, risk_sell = 0, 4
            elif quote_is_risk and not base_is_risk:
                risk_buy, risk_sell = 4, 0
            else:
                risk_buy, risk_sell = 2, 2
        elif risk_on_count > risk_off_count:
            sentiment = "risk_on"
            if base_is_risk and not quote_is_risk:
                risk_buy, risk_sell = 4, 0
            elif base_is_safe and not quote_is_safe:
                risk_buy, risk_sell = 0, 4
            elif quote_is_risk and not base_is_risk:
                risk_buy, risk_sell = 0, 4
            elif quote_is_safe and not base_is_safe:
                risk_buy, risk_sell = 4, 0
            else:
                risk_buy, risk_sell = 2, 2
        else:
            sentiment = "neutral"
            risk_buy, risk_sell = 2, 2

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

        # Hotspots → risk-off → safe havens benefit
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
            "risk_sentiment": sentiment,
            "risk_on_terms": risk_on_count,
            "risk_off_terms": risk_off_count,
            "hotspot_count": len(hotspots),
            "hotspot_severity": hotspot_severity,
            "components": {
                "risk_sentiment": {"buy": risk_buy, "sell": risk_sell},
                "geopolitical": {"buy": geo_buy, "sell": geo_sell},
            },
        }
        return (risk_buy + geo_buy, risk_sell + geo_sell, detail)

    # --- Macro Data Quality (0.0-1.0) ---
    def _macro_data_quality(
        self, headlines: list[dict[str, object]], events: list[dict[str, object]]
    ) -> float:
        confidence = 1.0
        now = datetime.now(UTC)

        # Check headline recency
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
            confidence -= 0.30  # No headlines at all

        # Check headline count
        if len(headlines) < 3:
            confidence -= 0.10
        if len(headlines) == 0:
            confidence -= 0.10

        # Check calendar data
        if not events:
            confidence -= 0.10

        return max(0.10, confidence)

    def _build_macro_reason(
        self,
        base: str,
        quote: str,
        base_stance: str,
        quote_stance: str,
        side: str,
        tier1_detail: dict[str, object],
        tier2_detail: dict[str, object],
        tier3_detail: dict[str, object],
    ) -> str:
        rates = self._load_interest_rates()
        base_rate = rates.get(base, {}).get("rate_label", "--")
        quote_rate = rates.get(quote, {}).get("rate_label", "--")
        parts = [
            f"[T1] {base}={base_rate}({base_stance}) vs {quote}={quote_rate}({quote_stance})",
            f"[T2] Calendar events: base={tier2_detail.get('base_event_weight',0)}, quote={tier2_detail.get('quote_event_weight',0)}",
            f"[T3] Sentiment={tier3_detail.get('risk_sentiment','neutral')}, hotspots={tier3_detail.get('hotspot_count',0)}",
        ]
        return " | ".join(parts)

    # ------------------------------------------------------------------
    # Legacy scoring (kept for backward compatibility, returns 0-15)
    # ------------------------------------------------------------------
    def _macro_alignment_scores(self, symbol: str, headlines: list[dict[str, object]]) -> dict[str, object]:
        currencies = [part for part in symbol.split("/") if part]
        base = currencies[0] if currencies else ""
        quote = currencies[1] if len(currencies) > 1 else ""
        base_stance = currency_stance(
            [str(item.get("title", "")) for item in headlines if self._matches_currency(item, base)],
            self.HAWKISH_TERMS,
            self.DOVISH_TERMS,
        )
        quote_stance = currency_stance(
            [str(item.get("title", "")) for item in headlines if self._matches_currency(item, quote)],
            self.HAWKISH_TERMS,
            self.DOVISH_TERMS,
        )
        buy_delta = stance_value(base_stance) - stance_value(quote_stance)
        sell_delta = -buy_delta
        return {
            "scores": {
                "buy": macro_score_from_delta(buy_delta),
                "sell": macro_score_from_delta(sell_delta),
            },
            "reasons": {
                "buy": f"{base} stance={base_stance}, {quote} stance={quote_stance}.",
                "sell": f"{quote} stance={quote_stance}, {base} stance={base_stance}.",
            },
        }

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    @classmethod
    def _high_impact_whitelist(cls) -> list[str]:
        try:
            path = Path(__file__).resolve().parents[1] / "config" / "interest_rates.json"
            raw = json.loads(path.read_text(encoding="utf-8"))
            return raw.get("high_impact_event_whitelist", [])
        except Exception:
            return [
                "CPI", "Core CPI", "PCE", "Core PCE", "NFP", "Nonfarm",
                "FOMC", "Federal Funds Rate", "Interest Rate Decision",
                "ECB", "BOE", "BOJ", "RBA", "RBNZ", "BOC", "SNB",
                "GDP", "Unemployment", "Retail Sales", "PMI", "ISM",
                "Wage", "Employment", "Payroll",
            ]

    def _forex_factory_events(self, currencies: list[str]) -> list[dict[str, object]]:
        return self._select_calendar_events(currencies, self._fetch_forex_factory_json_events())

    def _calendar_events(self, currencies: list[str]) -> dict[str, object]:
        errors: list[str] = []
        for source, fetcher in (
            ("Forex Factory", self._fetch_forex_factory_json_events),
            ("Forex Factory HTML", self._fetch_forex_factory_html_events),
        ):
            try:
                rows = fetcher()
            except Exception as exc:
                errors.append(f"{source}: {exc}")
                continue

            # If JSON source, try to enrich actual values from HTML
            if source == "Forex Factory":
                try:
                    html_rows = self._fetch_forex_factory_html_events()
                    self._merge_actual_from_html(rows, html_rows)
                except Exception:
                    pass  # HTML enrichment is best-effort

            self._store_calendar_cache(rows)
            return {
                "source": source,
                "events": self._select_calendar_events(currencies, rows),
                "warning": "",
            }

        cached = self._cached_calendar_events()
        if cached:
            return {
                "source": "Calendar file cache",
                "events": self._select_calendar_events(currencies, cached),
                "warning": "Không cập nhật được lịch kinh tế từ Forex Factory; đang dùng cache lịch kinh tế gần nhất.",
            }
        return {
            "source": "Calendar unavailable",
            "events": [],
            "warning": "Không lấy được lịch kinh tế từ Forex Factory: " + "; ".join(errors),
        }

    def _merge_actual_from_html(self, json_rows: list[dict[str, object]], html_rows: list[dict[str, object]]) -> None:
        """Merge actual values from HTML scraper into JSON rows. Only merge for past events."""
        if not html_rows:
            return
        now = datetime.now(UTC)
        # Build lookup from HTML: key = (currency, event_name, date_bucket)
        html_lookup: dict[tuple[str, str, str], str] = {}
        for row in html_rows:
            currency = str(row.get("currency", "")).upper()
            event = str(row.get("event", "")).strip().lower()
            actual = str(row.get("actual", "")).strip()
            ev_time = _event_time(row)
            date_key = ev_time.strftime("%Y%m%d") if ev_time else ""
            if actual and currency and event:
                html_lookup[(currency, event, date_key)] = actual

        if not html_lookup:
            return

        for row in json_rows:
            ev_time = _event_time(row)
            if not ev_time or ev_time >= now:
                continue  # Only merge actual for past events
            currency = str(row.get("currency", "")).upper()
            event = str(row.get("event", "")).strip().lower()
            date_key = ev_time.strftime("%Y%m%d")
            # Try exact date match first, then fall back to name-only match
            key = (currency, event, date_key)
            if key in html_lookup and not str(row.get("actual", "")).strip():
                row["actual"] = html_lookup[key]

    def _fetch_forex_factory_json_events(self) -> list[dict[str, object]]:
        import time
        last_error = None
        for attempt in range(3):
            try:
                request = Request(
                    self.FOREX_FACTORY_CALENDAR_URL,
                    headers={"User-Agent": "AI Market Analyst/1.0"},
                )
                with urlopen(request, timeout=10) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                return self._normalize_calendar_items(payload if isinstance(payload, list) else [], source="Forex Factory")
            except HTTPError as exc:
                last_error = RuntimeError(f"HTTP {exc.code}")
                if exc.code == 429 and attempt < 2:
                    time.sleep(2 * (attempt + 1))  # 2s, 4s backoff
                    continue
                raise last_error from exc
            except URLError as exc:
                last_error = RuntimeError(str(exc.reason))
                if attempt < 2:
                    time.sleep(1)
                    continue
                raise last_error from exc

    def _fetch_forex_factory_html_events(self) -> list[dict[str, object]]:
        request = Request(
            self.FOREX_FACTORY_HTML_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; AI Market Analyst/1.0)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        try:
            with urlopen(request, timeout=10) as response:
                html = response.read().decode("utf-8", errors="ignore")
        except HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(str(exc.reason)) from exc
        rows = self._parse_forex_factory_html(html)
        if not rows:
            raise RuntimeError("không đọc được bảng HTML")
        return rows

    def _normalize_calendar_items(self, payload: list[object], *, source: str) -> list[dict[str, object]]:
        now = datetime.now(UTC)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        rows: list[dict[str, object]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            currency = str(item.get("country") or item.get("currency") or "")
            if not currency:
                continue
            event_time = parse_event_time(str(item.get("date") or ""))
            if event_time and event_time < today_start:
                continue
            hours_until = ((event_time - now).total_seconds() / 3600) if event_time else None
            rows.append(
                {
                    "source": source,
                    "currency": currency,
                    "event": item.get("title", ""),
                    "impact": item.get("impact", ""),
                    "time_utc": event_time.isoformat(timespec="minutes").replace("+00:00", "Z") if event_time else "",
                    "hours_until": round(hours_until, 2) if hours_until is not None else None,
                    "forecast": item.get("forecast", ""),
                    "previous": item.get("previous", ""),
                    "actual": item.get("actual", ""),
                }
            )
        return rows

    def _parse_forex_factory_html(self, html: str) -> list[dict[str, object]]:
        from datetime import datetime as dt

        now = datetime.now(UTC)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        rows: list[dict[str, object]] = []
        current_date: str | None = None

        # Detect timezone from HTML (Forex Factory shows times in viewer's local tz)
        html_tz = self._detect_html_timezone(html)

        row_blocks = re.findall(r"<tr[^>]*calendar__row[^>]*>(.*?)</tr>", html, flags=re.IGNORECASE | re.DOTALL)
        for block in row_blocks:
            # Track current date from calendar__date cell
            date_text = self._html_cell_text(block, "calendar__date")
            if date_text:
                # Format: "Mon Jun 15" or "Mon  Jun 15"
                date_clean = re.sub(r"\s+", " ", date_text).strip()
                current_date = date_clean

            currency = self._html_cell_text(block, "calendar__currency")
            event = self._html_cell_text(block, "calendar__event-title") or self._html_cell_text(block, "calendar__event")
            if not currency or not event:
                continue

            # Extract time from calendar__time cell + current_date
            time_text = self._html_raw_cell(block, "calendar__time")
            time_text = re.sub(r"<[^>]+>", " ", time_text).strip() if time_text else ""
            event_time = self._parse_html_time(time_text, current_date, html_tz)

            if event_time and event_time < today_start:
                continue
            hours_until = ((event_time - now).total_seconds() / 3600) if event_time else None
            rows.append(
                {
                    "source": "Forex Factory HTML",
                    "currency": currency,
                    "event": event,
                    "impact": self._html_impact(block),
                    "time_utc": event_time.isoformat(timespec="minutes").replace("+00:00", "Z") if event_time else "",
                    "hours_until": round(hours_until, 2) if hours_until is not None else None,
                    "forecast": self._html_cell_text(block, "calendar__forecast"),
                    "previous": self._html_cell_text(block, "calendar__previous"),
                    "actual": self._html_cell_text(block, "calendar__actual"),
                }
            )
        return rows

    def _detect_html_timezone(self, html: str) -> str:
        """Detect the timezone used by Forex Factory HTML page.

        Forex Factory auto-detects the viewer's timezone from IP and displays
        all event times in that timezone. We extract it from the page metadata."""
        # Primary: "Calendar Time Zone: Asia/Bangkok (GMT +7)"
        tz_match = re.search(r"Calendar Time Zone:\s*([^<]+)", html)
        if tz_match:
            tz_text = tz_match.group(1).strip()
            tz_name = re.search(r"([A-Z][a-z]+/[A-Z][a-z_]+)", tz_text)
            if tz_name:
                return tz_name.group(1)
        # Secondary: JS config 'User Timezone': 'Asia/Bangkok'
        tz_match = re.search(r"'User Timezone':\s*'([^']+)'", html)
        if tz_match:
            return tz_match.group(1)
        # Fallback: system local timezone
        return str(datetime.now().astimezone().tzinfo)

    def _parse_html_time(self, time_text: str, date_text: str | None, html_tz: str = "UTC") -> datetime | None:
        """Parse time like '5:30am' or 'All Day' combined with date like 'Mon Jun 15'.

        html_tz is the timezone detected from the Forex Factory HTML page
        (matches the viewer's local timezone based on IP)."""
        if not time_text or not date_text:
            return None
        time_text = time_text.strip().lower()
        if time_text in ("all day", "tentative", ""):
            return None  # skip events without specific time

        match = re.match(r"(\d{1,2}):(\d{2})(am|pm)", time_text)
        if not match:
            return None
        hour = int(match.group(1))
        minute = int(match.group(2))
        ampm = match.group(3)
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0

        # Parse date: "Mon Jun 15"
        try:
            parsed_date = datetime.strptime(date_text + f" {datetime.now(UTC).year}", "%a %b %d %Y")
        except ValueError:
            return None

        from zoneinfo import ZoneInfo
        try:
            tz = ZoneInfo(html_tz)
        except Exception:
            tz = None
        dt_local = parsed_date.replace(hour=hour, minute=minute, tzinfo=tz)
        if tz:
            return dt_local.astimezone(UTC)
        return dt_local.replace(tzinfo=UTC)

    def _html_raw_cell(self, row_html: str, class_name: str) -> str:
        """Extract raw HTML content of a cell by class name (without stripping tags)."""
        match = re.search(
            rf'<(?:td|span|div)[^>]*class="[^"]*{re.escape(class_name)}[^"]*"[^>]*>(.*?)</(?:td|span|div)>',
            row_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return match.group(1) if match else ""

    def _html_cell_text(self, row_html: str, class_name: str) -> str:
        match = re.search(
            rf'<(?:td|span|div)[^>]*class="[^"]*{re.escape(class_name)}[^"]*"[^>]*>(.*?)</(?:td|span|div)>',
            row_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return ""
        return clean_text(re.sub(r"<[^>]+>", " ", match.group(1)))

    def _html_event_time(self, row_html: str) -> datetime | None:
        for pattern in (
            r'data-event-datetime="([^"]+)"',
            r'data-event-time="([^"]+)"',
            r'datetime="([^"]+)"',
        ):
            match = re.search(pattern, row_html, flags=re.IGNORECASE)
            if match:
                parsed = parse_event_time(match.group(1))
                if parsed:
                    return parsed
        return None

    def _html_impact(self, row_html: str) -> str:
        lowered = row_html.lower()
        if "high impact" in lowered or "calendar__impact-icon--red" in lowered or "ff-impact-red" in lowered:
            return "High"
        if "medium impact" in lowered or "calendar__impact-icon--orange" in lowered or "ff-impact-orange" in lowered:
            return "Medium"
        if "low impact" in lowered or "calendar__impact-icon--yellow" in lowered or "ff-impact-yellow" in lowered:
            return "Low"
        return ""

    def _select_calendar_events(self, currencies: list[str], rows: list[dict[str, object]]) -> list[dict[str, object]]:
        wanted = {currency.upper() for currency in currencies}
        relevant = [dict(row) for row in rows if str(row.get("currency", "")).upper() in wanted]
        if relevant:
            return sorted(relevant, key=lambda row: str(row.get("time_utc", "")))[:8]
        important = [
            dict(row)
            for row in rows
            if _is_high_impact(str(row.get("impact", ""))) or str(row.get("impact", "")).lower() == "medium"
        ]
        return sorted(important, key=lambda row: str(row.get("time_utc", "")))[:8]

    def _store_calendar_cache(self, rows: list[dict[str, object]]) -> None:
        if rows:
            now = datetime.now(UTC)
            snapshot = [dict(row) for row in rows]
            self._calendar_cache["global"] = (now, snapshot)
            try:
                cache_file = self._calendar_cache_file()
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(
                    json.dumps({"stored_utc": now.isoformat(), "rows": snapshot}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception:
                pass

    def _cached_calendar_events(self) -> list[dict[str, object]]:
        cached = self._calendar_cache.get("global")
        if cached:
            timestamp, rows = cached
            if datetime.now(UTC) - timestamp <= self.CALENDAR_CACHE_MAX_AGE:
                return [dict(row) for row in rows]
        try:
            cache_file = self._calendar_cache_file()
            raw = json.loads(cache_file.read_text(encoding="utf-8"))
            stored = parse_event_time(str(raw.get("stored_utc", "")))
            rows = raw.get("rows", [])
            if stored and datetime.now(UTC) - stored <= self.CALENDAR_CACHE_MAX_AGE and isinstance(rows, list):
                clean_rows = [dict(row) for row in rows if isinstance(row, dict)]
                if clean_rows:
                    self._calendar_cache["global"] = (stored, clean_rows)
                    return clean_rows
        except Exception:
            return []
        return []

    def _calendar_cache_file(self) -> Path:
        if self.CALENDAR_CACHE_FILE is not None:
            return self.CALENDAR_CACHE_FILE
        return app_data_dir() / "cache" / "economic_calendar_thisweek.json"

    def _macro_headlines(self, symbol: str, currencies: list[str]) -> list[dict[str, object]]:
        queries = self._headline_queries(symbol, currencies)
        rows: list[dict[str, object]] = []
        seen: set[str] = set()
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        for query in queries:
            url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=en-US&gl=US&ceid=US:en"
            for item in self._rss_items(url, query=query):
                title_key = str(item.get("title", "")).lower()
                if not title_key or title_key in seen:
                    continue
                published = parse_rss_time(str(item.get("published_utc", "")))
                if not published or published < cutoff:
                    continue
                seen.add(title_key)
                rows.append(item)
                if len(rows) >= 12:
                    return rows
        return rows

    def _latest_official_statements(self) -> list[dict[str, object]]:
        queries = [
            'Trump Truth Social tariffs dollar Fed "Truth Social"',
            "Trump remarks dollar tariffs Fed markets latest",
            "Fed officials speech Powell Waller Bowman dollar yields latest",
            "Japan Prime Minister remarks yen BOJ latest",
            "UK Prime Minister remarks pound BOE latest",
            "European Union officials Lagarde von der Leyen euro latest",
        ]
        rows: list[dict[str, object]] = []
        seen: set[str] = set()
        cutoff = datetime.now(UTC) - timedelta(hours=24)

        def _fetch_one(query: str) -> list[dict[str, object]]:
            items: list[dict[str, object]] = []
            url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=en-US&gl=US&ceid=US:en"
            for item in self._rss_items(url, query=query):
                title = str(item.get("title", ""))
                title_key = title.lower()
                if not title_key or title_key in seen:
                    continue
                published = parse_rss_time(str(item.get("published_utc", "")))
                if not published or published < cutoff:
                    continue
                enriched = dict(item)
                enriched["category"] = "official_statement"
                enriched["impact_note"] = self._headline_impact_note(title)
                items.append(enriched)
            return items

        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(_fetch_one, q): q for q in queries}
            for future in as_completed(futures):
                try:
                    items = future.result()
                except Exception:
                    continue
                for enriched in items:
                    title = str(enriched.get("title", ""))
                    title_key = title.lower()
                    if title_key in seen:
                        continue
                    seen.add(title_key)
                    rows.append(enriched)
                    if len(rows) >= 10:
                        return rows
        return rows

    def _headline_queries(self, symbol: str, currencies: list[str]) -> list[str]:
        base_terms = " OR ".join(currencies)
        central_banks = " OR ".join(
            term
            for currency in currencies
            for term in self.CURRENCY_KEYWORDS.get(currency, [])[:4]
        )
        queries = [
            f"{symbol} forex macro central bank latest",
            f"({base_terms}) ({central_banks}) forex Reuters OR Bloomberg OR Investing.com",
            f"{symbol} yield differential intervention risk forex",
            "global geopolitical risk oil sanctions forex markets",
        ]
        return [query for query in queries if query.strip()]

    def _rss_items(self, url: str, *, query: str) -> list[dict[str, object]]:
        request = Request(url, headers={"User-Agent": "AI Market Analyst/1.0"})
        try:
            with urlopen(request, timeout=8) as response:
                payload = response.read()
        except Exception:
            return []
        try:
            root = ElementTree.fromstring(payload)
        except ElementTree.ParseError:
            return []
        rows: list[dict[str, object]] = []
        for item in root.findall(".//item")[:8]:
            title = clean_text(item.findtext("title") or "")
            link = clean_text(item.findtext("link") or "")
            source = clean_text(item.findtext("source") or "")
            published = parse_rss_time(item.findtext("pubDate") or "")
            rows.append(
                {
                    "source": source or "Google News RSS",
                    "query": query,
                    "title": title,
                    "url": link,
                    "published_utc": published.isoformat(timespec="minutes").replace("+00:00", "Z") if published else "",
                    "tags": self._headline_tags(title),
                }
            )
        return rows

    def _macro_themes(self, symbol: str, currencies: list[str], headlines: list[dict[str, object]]) -> list[dict[str, object]]:
        themes: list[dict[str, object]] = []
        for currency in currencies:
            matched = [
                item
                for item in headlines
                if currency.lower() in str(item.get("title", "")).lower()
                or any(keyword.lower() in str(item.get("title", "")).lower() for keyword in self.CURRENCY_KEYWORDS.get(currency, []))
            ]
            stance = currency_stance([str(item.get("title", "")) for item in matched], self.HAWKISH_TERMS, self.DOVISH_TERMS)
            themes.append(
                {
                    "currency": currency,
                    "stance": stance,
                    "headline_count": len(matched),
                    "key_points": [item.get("title", "") for item in matched[:4]],
                }
            )
        return themes

    def _geopolitical_hotspots(self, headlines: list[dict[str, object]]) -> list[dict[str, object]]:
        hotspots = []
        for item in headlines:
            title = str(item.get("title", ""))
            if any(term.lower() in title.lower() for term in self.HOTSPOT_TERMS):
                hotspots.append(item)
        return hotspots[:6]

    def _matches_currency(self, item: dict[str, object], currency: str) -> bool:
        text = str(item.get("title", "")).lower()
        return currency.lower() in text or any(keyword.lower() in text for keyword in self.CURRENCY_KEYWORDS.get(currency, []))

    def _headline_tags(self, title: str) -> list[str]:
        tags = []
        lowered = title.lower()
        for tag, terms in {
            "central_bank": ["fed", "boj", "ecb", "boe", "snb", "rba", "rbnz", "boc", "central bank"],
            "inflation": ["cpi", "pce", "inflation", "prices"],
            "labor": ["wages", "jobs", "payrolls", "employment"],
            "yields": ["yield", "treasury", "bund", "jgb"],
            "intervention": ["intervention"],
            "geopolitical": self.HOTSPOT_TERMS,
        }.items():
            if any(term.lower() in lowered for term in terms):
                tags.append(tag)
        return tags

    def _headline_impact_note(self, title: str) -> str:
        lowered = title.lower()
        if any(term in lowered for term in ["tariff", "sanction", "risk-off", "war", "geopolitical"]):
            return "Có thể làm tăng biến động và hỗ trợ nhóm tài sản trú ẩn như USD, JPY, CHF hoặc XAU."
        if any(term in lowered for term in ["fed", "powell", "fomc", "rate", "yield", "inflation"]):
            return "Có thể tác động trực tiếp tới USD và lợi suất trái phiếu Mỹ."
        if any(term in lowered for term in ["boj", "japan", "yen", "ueda"]):
            return "Có thể tác động tới JPY qua kỳ vọng chính sách BOJ hoặc rủi ro can thiệp."
        if any(term in lowered for term in ["boe", "uk", "pound", "sterling"]):
            return "Có thể tác động tới GBP qua kỳ vọng chính sách BOE và triển vọng kinh tế Anh."
        if any(term in lowered for term in ["ecb", "euro", "european union", "lagarde", "von der leyen"]):
            return "Có thể tác động tới EUR qua kỳ vọng chính sách ECB hoặc rủi ro chính trị châu Âu."
        return ""


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------
def parse_event_time(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _event_time(event: object) -> datetime | None:
    if not isinstance(event, dict):
        return None
    return parse_event_time(str(event.get("time_utc") or ""))


def _is_high_impact(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in NewsService.HIGH_IMPACT_VALUES or "high" in normalized or "red" in normalized


def parse_rss_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except Exception:
        return parse_event_time(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def clean_text(value: str) -> str:
    return " ".join(unescape(value or "").split())


def currency_stance(headlines: list[str], hawkish_terms: list[str], dovish_terms: list[str]) -> str:
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
        return NewsService.BASELINE_MACRO_SCORE
    if delta == -1:
        return 4
    return 0
