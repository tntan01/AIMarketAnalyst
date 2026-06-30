"""News service — macro context, calendar data quality, and headline analysis."""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from config.paths import app_data_dir
from services.forex_factory_client import (
    ForexFactoryClient,
    _event_time,
    _is_high_impact,
    clean_text,
    parse_event_time,
)

# ---------------------------------------------------------------------------
# Re-export for backward compatibility
# ---------------------------------------------------------------------------
__all__ = [
    "NewsService",
    "parse_event_time",
    "clean_text",
    "parse_rss_time",
    "currency_stance",
    "stance_value",
    "macro_score_from_delta",
]


class NewsService:
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
    _interest_rates: dict[str, object] | None = None
    _tier_scores_cache: dict[str, dict[str, object]] = {}
    _last_fetch_time: datetime | None = None

    def __init__(self) -> None:
        self._ff_client = ForexFactoryClient()

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
        calendar = self._ff_client.calendar_events(currencies)
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

    _preload_cache_time: datetime | None = None
    _preload_cache_ttl = timedelta(minutes=5)
    NEWS_WINDOW_DAYS = 7

    # Additional RSS feeds (free, no API key)
    EXTRA_RSS_FEEDS = [
        "https://www.fxstreet.com/rss/news",
        "https://www.investing.com/rss/news_301.rss",
    ]

    def preload_macro_contexts(self, symbols: list[str], progress_callback=None) -> None:
        """Pre-fetch RSS (1 query tong quat) + calendar + compute tier scores.

        Results are cached for _preload_cache_ttl (5 min) to avoid redundant
        HTTP calls on repeated scans.
        """
        if not symbols:
            return
        progress = progress_callback or (lambda _p, _m: None)

        # Skip if preload was done recently (within 5 min)
        now = datetime.now(UTC)
        if self._preload_cache_time is not None and now - self._preload_cache_time < self._preload_cache_ttl:
            return

        # Buoc 1: Fetch calendar 1 lan (uses disk cache with 12h TTL)
        progress(15, "Đang tải lịch kinh tế...")
        first = symbols[0]
        currencies_first = [part for part in first.split("/") if part]
        self._ff_client.calendar_events(currencies_first)

        # Buoc 2+3: Fetch RSS + official statements in parallel
        progress(16, "Đang tải tin tức toàn cầu...")
        with ThreadPoolExecutor(max_workers=2) as ex:
            headlines_future = ex.submit(self._fetch_global_forex_headlines)
            statements_future = ex.submit(self._latest_official_statements)
            self._global_headlines: list[dict[str, object]] = headlines_future.result()
            statements_future.result()  # caches internally

        # Buoc 4: Pre-compute macro context cho TAT CA symbols
        self._preloading = True
        try:
            total = max(1, len(symbols))
            for idx, symbol in enumerate(symbols):
                progress(17 + int((idx + 1) / total * 2), f"Đang phân tích vĩ mô {symbol} ({idx + 1}/{total})...")
                for include_stmts in (True,):
                    ctx = self.latest_macro_context(symbol, include_latest_statements=include_stmts)
                    cache_key = f"{symbol}_{include_stmts}"
                    self._tier_scores_cache[cache_key] = ctx
        finally:
            self._preloading = False

        self._last_fetch_time = now
        self._preload_cache_time = now

    # ------------------------------------------------------------------
    # News Window API (±7 days for Dashboard display)
    # ------------------------------------------------------------------
    def fetch_news_window(
        self,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        currencies: list[str] | None = None,
    ) -> dict[str, object]:
        """Fetch headlines + calendar events in [from_date, to_date] range.

        Defaults to ±NEWS_WINDOW_DAYS from now. Tries multiple sources with
        graceful fallback. Returns a dict suitable for Dashboard display.
        """
        now = datetime.now(UTC)
        if from_date is None:
            from_date = now - timedelta(days=self.NEWS_WINDOW_DAYS)
        if to_date is None:
            to_date = now + timedelta(days=self.NEWS_WINDOW_DAYS)
        if currencies is None:
            currencies = []

        # 1) Fetch headlines from multiple RSS sources
        headlines, headline_sources = self._fetch_headlines_window(from_date, to_date)

        # 2) Fetch calendar events
        calendar_result: dict[str, object] = {"source": "", "events": [], "warning": ""}
        try:
            calendar_result = self._ff_client.calendar_events_window(currencies, from_date, to_date)
        except Exception as exc:
            calendar_result = {"source": "unavailable", "events": [], "warning": str(exc)}

        events = calendar_result.get("events", [])
        if not isinstance(events, list):
            events = []

        # 3) Store to disk cache
        try:
            self._store_news_cache(headlines, events)
        except Exception:
            pass

        # 4) Build deduplicated, tagged combined list
        combined = self._build_news_feed(headlines, events, from_date, to_date, now)

        return {
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "headlines": headlines,
            "events": events,
            "combined": combined,
            "sources": {
                "headlines": headline_sources,
                "calendar": str(calendar_result.get("source", "")),
            },
            "warnings": [w for w in [str(calendar_result.get("warning", "")).strip()] if w],
        }

    def _fetch_headlines_window(
        self, from_date: datetime, to_date: datetime
    ) -> tuple[list[dict[str, object]], list[str]]:
        """Fetch headlines from Google News RSS → extra RSS feeds → disk cache."""
        all_headlines: list[dict[str, object]] = []
        sources: list[str] = []
        seen: set[str] = set()

        def add_items(items: list[dict[str, object]], source_label: str) -> None:
            if items and source_label not in sources:
                sources.append(source_label)
            for item in items:
                title_key = str(item.get("title", "")).lower().strip()
                if not title_key or title_key in seen:
                    continue
                seen.add(title_key)
                all_headlines.append(item)

        # Source 1: Google News RSS (broad queries)
        try:
            broad_queries = [
                "forex central bank Fed ECB BOJ BOE rate decision macro latest",
                "global macro risk sentiment dollar yen euro pound forex markets",
                "forex geopolitical oil gold safe haven latest",
            ]
            cutoff = from_date

            def _fetch_one(query: str) -> list[dict[str, object]]:
                items: list[dict[str, object]] = []
                url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=en-US&gl=US&ceid=US:en"
                for item in self._rss_items(url, query=query):
                    published = parse_rss_time(str(item.get("published_utc", "")))
                    if not published or published < cutoff:
                        continue
                    items.append(item)
                return items

            with ThreadPoolExecutor(max_workers=3) as ex:
                futures = {ex.submit(_fetch_one, q): q for q in broad_queries}
                for future in as_completed(futures):
                    try:
                        add_items(future.result(), "Google News RSS")
                    except Exception:
                        pass
        except Exception:
            pass

        # Source 2: Extra RSS feeds (FXStreet, Investing.com)
        for feed_url in self.EXTRA_RSS_FEEDS:
            try:
                items = self._fetch_extra_rss(feed_url, from_date)
                source_name = "FXStreet" if "fxstreet" in feed_url else "Investing.com"
                add_items(items, source_name)
            except Exception:
                pass

        # Always merge disk cache to preserve older headlines not in live RSS
        try:
            cached = self._read_news_cache()
            cached_headlines = cached.get("headlines", [])
            if isinstance(cached_headlines, list):
                for item in cached_headlines:
                    if not isinstance(item, dict):
                        continue
                    published = parse_rss_time(str(item.get("published_utc", "")))
                    if published and from_date <= published <= to_date:
                        add_items([item], "Disk cache")
        except Exception:
            pass

        # Sort by published date descending
        all_headlines.sort(
            key=lambda h: str(h.get("published_utc", "")),
            reverse=True,
        )
        return all_headlines, sources

    def _fetch_extra_rss(self, url: str, cutoff: datetime) -> list[dict[str, object]]:
        """Fetch items from a standard RSS feed (FXStreet, Investing.com, etc.)."""
        items: list[dict[str, object]] = []
        try:
            request = Request(url, headers={"User-Agent": "AI Market Analyst/1.0"})
            with urlopen(request, timeout=8) as response:
                payload = response.read()
            root = ElementTree.fromstring(payload)
        except Exception:
            return items

        for item in root.findall(".//item")[:15]:
            title = clean_text(item.findtext("title") or "")
            link = clean_text(item.findtext("link") or "")
            source_name = clean_text(item.findtext("source") or "")
            pub_str = item.findtext("pubDate") or ""
            published = parse_rss_time(pub_str)
            if not title:
                continue
            if published and published < cutoff:
                continue
            if not source_name:
                source_name = url.split("/")[2].replace("www.", "")
            tags = self._headline_tags(title)
            items.append({
                "source": source_name,
                "title": title,
                "url": link,
                "published_utc": published.isoformat(timespec="minutes").replace("+00:00", "Z") if published else "",
                "tags": tags,
                "impact_note": self._headline_impact_note(title),
            })
        return items

    def _build_news_feed(
        self,
        headlines: list[dict[str, object]],
        events: list[dict[str, object]],
        from_date: datetime,
        to_date: datetime,
        now: datetime,
    ) -> list[dict[str, object]]:
        """Merge headlines and calendar events into a unified sorted feed."""
        combined: list[dict[str, object]] = []

        for h in headlines:
            pub = parse_rss_time(str(h.get("published_utc", "")))
            combined.append({
                "type": "headline",
                "title": str(h.get("title", "")),
                "source": str(h.get("source", "RSS")),
                "url": str(h.get("url", "")),
                "time_utc": pub.isoformat().replace("+00:00", "Z") if pub else "",
                "display_time": pub,
                "tags": h.get("tags", []),
                "impact_note": str(h.get("impact_note", "")),
            })

        for ev in events:
            ev_time = _event_time(ev)
            combined.append({
                "type": "event",
                "title": str(ev.get("event", "")),
                "currency": str(ev.get("currency", "")),
                "impact": str(ev.get("impact", "low")),
                "source": str(ev.get("source", "Forex Factory")),
                "time_utc": str(ev.get("time_utc", "")),
                "display_time": ev_time,
                "forecast": str(ev.get("forecast", "")),
                "previous": str(ev.get("previous", "")),
                "actual": str(ev.get("actual", "")),
                "tags": [],
                "impact_note": "",
            })

        # Sort by time (items without time go last)
        def sort_key(item: dict[str, object]) -> tuple[int, str]:
            dt = item.get("display_time")
            if isinstance(dt, datetime):
                return (0, dt.isoformat())
            return (1, "")

        combined.sort(key=sort_key)
        # Batch lookup actual for past events
        try:
            self.lookup_actuals_batch(combined)
        except Exception:
            pass
        return combined

    # ------------------------------------------------------------------
    # News disk cache
    # ------------------------------------------------------------------
    def _news_cache_file(self) -> Path:
        return app_data_dir() / "cache" / "news_cache.json"

    def _read_news_cache(self) -> dict[str, object]:
        try:
            cache_file = self._news_cache_file()
            if cache_file.exists():
                return json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _store_news_cache(
        self, headlines: list[dict[str, object]], events: list[dict[str, object]]
    ) -> None:
        """Merge new headlines/events into persistent cache, keeping up to 14 days."""
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=14)
        cache_file = self._news_cache_file()
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        # Read existing cache
        existing = {}
        try:
            if cache_file.exists():
                existing = json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass

        # Merge headlines (dedup by title)
        seen_titles: set[str] = set()
        merged_headlines: list[dict[str, object]] = []
        for item in headlines:
            title_key = str(item.get("title", "")).lower().strip()
            if title_key and title_key not in seen_titles:
                seen_titles.add(title_key)
                merged_headlines.append(item)

        existing_headlines = existing.get("headlines", [])
        if isinstance(existing_headlines, list):
            for item in existing_headlines:
                if not isinstance(item, dict):
                    continue
                title_key = str(item.get("title", "")).lower().strip()
                if not title_key or title_key in seen_titles:
                    continue
                published = parse_rss_time(str(item.get("published_utc", "")))
                if published and published < cutoff:
                    continue
                seen_titles.add(title_key)
                merged_headlines.append(item)

        # Merge events (dedup by currency+title+time)
        seen_event_keys: set[str] = set()
        merged_events: list[dict[str, object]] = []
        for ev in events:
            key = f"{ev.get('currency','')}|{ev.get('event','')}|{ev.get('time_utc','')}".lower()
            if key not in seen_event_keys:
                seen_event_keys.add(key)
                merged_events.append(ev)

        existing_events = existing.get("events", [])
        if isinstance(existing_events, list):
            for ev in existing_events:
                if not isinstance(ev, dict):
                    continue
                key = f"{ev.get('currency','')}|{ev.get('event','')}|{ev.get('time_utc','')}".lower()
                if key in seen_event_keys:
                    continue
                ev_time = parse_event_time(str(ev.get("time_utc", "")))
                if ev_time and ev_time < cutoff:
                    continue
                seen_event_keys.add(key)
                merged_events.append(ev)

        cache_file.write_text(
            json.dumps({
                "date": now.strftime("%Y%m%d"),
                "stored_utc": now.isoformat(),
                "headlines": merged_headlines[:200],
                "events": merged_events[:200],
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _fetch_global_forex_headlines(self) -> list[dict[str, object]]:
        """Fetch 3 broad queries in parallel to get headlines for all currency pairs."""
        rows: list[dict[str, object]] = []
        seen: set[str] = set()
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        broad_queries = [
            "forex central bank Fed ECB BOJ BOE rate decision macro latest",
            "global macro risk sentiment dollar yen euro pound forex markets",
            "forex geopolitical oil gold safe haven latest",
        ]

        def _fetch_one(query: str) -> list[dict[str, object]]:
            items: list[dict[str, object]] = []
            url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=en-US&gl=US&ceid=US:en"
            for item in self._rss_items(url, query=query):
                title_key = str(item.get("title", "")).lower()
                if not title_key:
                    continue
                published = parse_rss_time(str(item.get("published_utc", "")))
                if not published or published < cutoff:
                    continue
                items.append(item)
            return items

        with ThreadPoolExecutor(max_workers=3) as ex:
            futures = {ex.submit(_fetch_one, q): q for q in broad_queries}
            for future in as_completed(futures):
                try:
                    for item in future.result():
                        title_key = str(item.get("title", "")).lower()
                        if title_key in seen:
                            continue
                        seen.add(title_key)
                        rows.append(item)
                except Exception:
                    pass
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
    def _macro_tier1(self, base: str, quote: str, base_stance: str, quote_stance: str) -> tuple[int, int, dict[str, object]]:
        rates = self._load_interest_rates()
        base_info = rates.get(base, {})
        quote_info = rates.get(quote, {})

        # Rate differential score (0-2)
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

        # Rate trend score (0-5)
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

        # Stance score from headlines (0-5)
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
    def _macro_tier2(self, base: str, quote: str, events: list[dict[str, object]]) -> tuple[int, int, dict[str, object]]:
        whitelist = self._high_impact_whitelist()
        now = datetime.now(UTC)
        cutoff = now + timedelta(hours=72)

        base_quality = 0
        quote_quality = 0
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

        risk_on_terms = ["risk-on", "rally", "bullish", "soft landing", "goldilocks", "stimulus", "recovery"]
        risk_off_terms = ["risk-off", "sell-off", "bearish", "recession", "crash", "fear", "panic", "flight to safety"]

        risk_on_count = sum(1 for t in risk_on_terms if t in all_text)
        risk_off_count = sum(1 for t in risk_off_terms if t in all_text)

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
            with urlopen(request, timeout=5) as response:
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
    # Actual value lookup (Brave Search)
    # ------------------------------------------------------------------

    _CURRENCY_TO_COUNTRY: dict[str, str] = {
        "USD": "US United States",
        "CAD": "Canada",
        "GBP": "UK United Kingdom",
        "EUR": "Eurozone Euro area",
        "JPY": "Japan",
        "AUD": "Australia",
        "NZD": "New Zealand",
        "CHF": "Switzerland",
        "CNY": "China",
    }
    _ABBREV_TO_FULL: dict[str, str] = {
        "m/m": "monthly",
        "q/q": "quarterly",
        "y/y": "annual year-over-year",
    }
    _MONTH_NAMES: list[str] = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]

    @classmethod
    def _build_search_query(cls, currency: str, event_name: str, date_str: str) -> str:
        country = cls._CURRENCY_TO_COUNTRY.get(currency.upper(), currency)
        event_full = event_name
        for abbr, full in cls._ABBREV_TO_FULL.items():
            if abbr in event_full.lower():
                event_full = event_full.replace(abbr, full).replace(abbr.upper(), full)
        month = ""
        year = ""
        try:
            parts = date_str.split("-")
            if len(parts) >= 2:
                m = int(parts[1])
                if 1 <= m <= 12:
                    month = cls._MONTH_NAMES[m - 1]
            if len(parts) >= 1:
                year = parts[0]
        except (ValueError, IndexError):
            pass
        time_part = f"{month} {year}".strip() if month else date_str
        return f"{country} {event_full} {time_part} actual result"

    def _get_brave_api_key(self) -> str:
        try:
            from config.paths import settings_path
            from services.storage_service import JsonStorage
            storage = JsonStorage(settings_path())
            raw = storage.load() or {}
            adv = raw.get("advanced", {})
            return adv.get("brave_api_key", "")
        except Exception:
            return ""

    def _actual_cache_file(self) -> Path:
        return app_data_dir() / "cache" / "actual_cache.json"

    def _read_actual_cache(self) -> dict[str, str]:
        try:
            cache_file = self._actual_cache_file()
            if cache_file.exists():
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {}

    def _write_actual_cache(self, cache: dict[str, str]) -> None:
        try:
            cache_file = self._actual_cache_file()
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def lookup_actual_single(self, currency: str, event_name: str, ev_time_str: str) -> str:
        api_key = self._get_brave_api_key()
        if not api_key:
            return ""

        date_key = ev_time_str[:10]
        cache_key = f"{currency}|{event_name}|{date_key}"
        cache = self._read_actual_cache()
        if cache_key in cache:
            return cache[cache_key]

        query = self._build_search_query(currency, event_name, date_key)
        from services.forex_factory_client import ForexFactoryClient
        ff_client = ForexFactoryClient()
        results = ff_client._brave_search(query, api_key)

        all_text = " ".join(
            r.get("title", "") + " " + r.get("description", "")
            for r in results
        )
        all_text = all_text.replace("&#x27;", "'").replace("&amp;", "&")

        actual = self._parse_actual_simple(all_text)
        cache[cache_key] = actual
        self._write_actual_cache(cache)
        return actual

    @staticmethod
    def _parse_actual_simple(text: str) -> str:
        clean = re.sub(r"<[^>]+>", "", text)
        m = re.search(
            r'(?:actual|result|rose|fell|increased|decreased|expanded|expands|declined|contracted|shrunk|grew|advanced|dropped|came in at)\s+(?:by\s+)?(\d+\.?\d*%?)',
            clean, re.IGNORECASE,
        )
        if m:
            val = m.group(1).strip()
            if "%" not in val:
                val = val + "%"
            return val
        return ""

    def lookup_actuals_batch(self, events: list[dict[str, object]]) -> None:
        api_key = self._get_brave_api_key()
        if not api_key:
            return

        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        cache = self._read_actual_cache()

        missing = []
        for ev in events:
            if str(ev.get("type", "")) != "event":
                continue
            actual = str(ev.get("actual", "")).strip()
            if actual:
                continue
            ev_time_str = str(ev.get("time_utc", ""))
            if not ev_time_str:
                continue
            try:
                ev_time = datetime.fromisoformat(ev_time_str.replace("Z", "+00:00"))
            except Exception:
                continue
            if ev_time >= now:
                continue
            date_key = ev_time_str[:10]
            cache_key = f"{str(ev.get('currency',''))}|{str(ev.get('title',''))}|{date_key}"
            if cache_key in cache:
                if cache[cache_key]:
                    ev["actual"] = cache[cache_key]
                continue
            if now - ev_time < timedelta(minutes=30):
                continue
            missing.append({"ev": ev, "cache_key": cache_key})

        if not missing:
            return

        missing = missing[:15]

        from services.forex_factory_client import ForexFactoryClient
        ff_client = ForexFactoryClient()
        cache_updated = False

        for item in missing:
            ev = item["ev"]
            cache_key = item["cache_key"]
            currency = str(ev.get("currency", ""))
            title = str(ev.get("title", ""))
            ev_time_str = str(ev.get("time_utc", ""))
            date_key = ev_time_str[:10]

            query = self._build_search_query(currency, title, date_key)
            try:
                results = ff_client._brave_search(query, api_key)
            except Exception:
                continue

            if not results:
                continue

            time.sleep(0.3)

            all_text = " ".join(
                r.get("title", "") + " " + r.get("description", "")
                for r in results
            )
            all_text = all_text.replace("&#x27;", "'").replace("&amp;", "&")
            clean_text = re.sub(r"<[^>]+>", "", all_text)

            actual = self._parse_actual_simple(clean_text)
            cache[cache_key] = actual
            if actual:
                ev["actual"] = actual
            cache_updated = True
            self._write_actual_cache(cache)


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------
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
