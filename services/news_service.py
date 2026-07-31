"""News service — macro context, calendar data quality, and headline analysis."""

from __future__ import annotations

import json
import re
import time
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from config.paths import app_data_dir
from services.calendar_helpers import (
    _clean_economic_value,
    _event_time,
    _is_high_impact,
    clean_text,
    parse_event_time,
)
from services.forex_factory_client import ForexFactoryClient
from services.ai_service import AIService, AIProviderConfig
from services.macro_market_cache import get_shared_cache
from services.settings_service import SettingsService
import yfinance as yf

# ---------------------------------------------------------------------------
# Re-export for backward compatibility
# ---------------------------------------------------------------------------
__all__ = [
    "NewsService",
    "MacroGlobalSnapshot",
    "parse_event_time",
    "clean_text",
    "parse_rss_time",
    "currency_stance",
    "stance_value",
    "macro_score_from_delta",
]


@dataclass(frozen=True, slots=True)
class MacroGlobalSnapshot:
    """One coherent set of market-global macro inputs for a scan/TTL."""

    fetched_at_utc: datetime
    expires_at_utc: datetime
    tnx: float | None
    fvx: float | None
    yield_spread_10y_5y: float | None
    yield_steepening: bool | None
    vix: float | None
    global_headlines: tuple[dict[str, object], ...]
    official_statements: tuple[dict[str, object], ...]
    calendar_payload: dict[str, object]
    source_status: dict[str, dict[str, object]]
    stale_fields: tuple[str, ...]

    def yield_spread_payload(self) -> dict[str, object]:
        spread = self.yield_spread_10y_5y
        return {
            "spread": spread,
            "tnx": self.tnx,
            "fvx": self.fvx,
            "steepening": self.yield_steepening,
            "ten_year_yield": round(self.tnx, 2) if self.tnx is not None else None,
            "five_year_yield": round(self.fvx, 2) if self.fvx is not None else None,
            "yield_spread_10y_5y": spread,
            "yield_spread_2s10s": spread,
        }

    def provenance(self) -> dict[str, object]:
        return {
            "fetched_at_utc": self.fetched_at_utc.isoformat(),
            "expires_at_utc": self.expires_at_utc.isoformat(),
            "source_status": deepcopy(self.source_status),
            "stale_fields": list(self.stale_fields),
        }


@dataclass(frozen=True, slots=True)
class _MacroContextCacheEntry:
    value: dict[str, object]
    fetched_at_utc: datetime
    expires_at_utc: datetime
    ai_fingerprint: str
    source_freshness: dict[str, object]


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
    _last_fetch_time: datetime | None = None
    _macro_context_cache_ttl = timedelta(minutes=5)
    _global_snapshot_ttl = timedelta(minutes=5)
    _global_snapshot_stale_if_error = timedelta(minutes=30)

    def __init__(self) -> None:
        self._ff_client = ForexFactoryClient()
        self._stance_cache: dict[str, tuple[str, datetime]] = {}
        self._tier_scores_cache: dict[str, _MacroContextCacheEntry] = {}
        self._macro_context_cache_lock = RLock()
        self._global_snapshot_lock = RLock()
        self._global_snapshot: MacroGlobalSnapshot | None = None
        self._preload_cache_time: datetime | None = None
        self._preloading = False

    # ------------------------------------------------------------------
    # Interest rate config
    # ------------------------------------------------------------------
    @classmethod
    def _load_interest_rates(cls) -> dict[str, object]:
        if cls._interest_rates is not None:
            return cls._interest_rates
        from services.interest_rate_service import get_latest_rates
        from services.settings_service import SettingsService
        try:
            settings = SettingsService().load()
            fred_key = getattr(settings.advanced, "fred_api_key", "") or ""
        except Exception:
            fred_key = ""
        cls._interest_rates = get_latest_rates(fred_api_key=fred_key or None)
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

    @staticmethod
    def _ai_fingerprint(ai_service: object | None) -> str:
        """Return a stable provider/model fingerprint without reading secrets."""
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

    @staticmethod
    def _macro_context_cache_key(
        symbol: str,
        include_latest_statements: bool,
        ai_fingerprint: str,
    ) -> str:
        """Canonical key used by every macro-context cache reader/writer."""
        return json.dumps(
            {
                "symbol": str(symbol).strip().upper(),
                "include_latest_statements": bool(include_latest_statements),
                "ai": str(ai_fingerprint),
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _symbol_currencies(symbol: str) -> list[str]:
        currencies = [part for part in str(symbol).upper().split("/") if part]
        if len(currencies) == 1 and len(currencies[0]) >= 6:
            raw = currencies[0]
            currencies = [raw[:3], raw[3:6]]
        return currencies

    def _fresh_context_entry(
        self,
        cache_key: str,
        now: datetime,
        expected_snapshot: MacroGlobalSnapshot | None = None,
    ) -> _MacroContextCacheEntry | None:
        entry = self._tier_scores_cache.get(cache_key)
        if entry is None or now >= entry.expires_at_utc:
            return None
        if expected_snapshot is not None:
            snapshot_fetched_at = entry.source_freshness.get("fetched_at_utc")
            if snapshot_fetched_at != expected_snapshot.fetched_at_utc.isoformat():
                return None
        return entry

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def latest_macro_context(
        self,
        symbol: str,
        *,
        include_latest_statements: bool = True,
        ai_service: object | None = None,
        _snapshot: MacroGlobalSnapshot | None = None,
    ) -> dict[str, object]:
        ai_fingerprint = self._ai_fingerprint(ai_service)
        cache_key = self._macro_context_cache_key(
            symbol,
            include_latest_statements,
            ai_fingerprint,
        )
        now = datetime.now(UTC)

        # Keep the lock through the build so concurrent consumers cannot build
        # the same key twice. Different symbols are preloaded sequentially.
        with self._macro_context_cache_lock:
            cached = self._fresh_context_entry(cache_key, now, _snapshot)
            if cached is not None:
                return deepcopy(cached.value)

            snapshot = _snapshot or self._get_global_macro_snapshot(now=now)
            currencies = self._symbol_currencies(symbol)
            context = self._build_macro_context(
                symbol,
                currencies,
                include_latest_statements=include_latest_statements,
                ai_service=ai_service,
                snapshot=snapshot,
            )
            fetched_at = datetime.now(UTC)
            # Context expiry is bounded by BOTH the local context TTL and the
            # snapshot's own expiry: once the underlying source snapshot is
            # stale/expired, cached contexts built from it must not keep being
            # served as fresh (no silent +5 min extension past the source).
            expires_at = min(
                fetched_at + self._macro_context_cache_ttl,
                snapshot.expires_at_utc,
            )
            source_freshness = snapshot.provenance()
            context["macro_cache"] = {
                "fetched_at_utc": fetched_at.isoformat(),
                "expires_at_utc": expires_at.isoformat(),
                "ai_fingerprint": ai_fingerprint,
                "source_freshness": deepcopy(source_freshness),
            }
            entry = _MacroContextCacheEntry(
                value=deepcopy(context),
                fetched_at_utc=fetched_at,
                expires_at_utc=expires_at,
                ai_fingerprint=ai_fingerprint,
                source_freshness=deepcopy(source_freshness),
            )
            self._tier_scores_cache[cache_key] = entry
            if not self._preloading:
                self._last_fetch_time = fetched_at
            return deepcopy(entry.value)

    def _build_macro_context(
        self,
        symbol: str,
        currencies: list[str],
        *,
        include_latest_statements: bool,
        ai_service: object | None,
        snapshot: MacroGlobalSnapshot,
    ) -> dict[str, object]:
        base = currencies[0] if currencies else ""
        quote = currencies[1] if len(currencies) > 1 else ""
        calendar = self._calendar_context_from_snapshot(snapshot, currencies)
        events = calendar["events"]
        calendar_source = str(calendar["source"])
        calendar_warning = str(calendar["warning"])
        headlines = [
            deepcopy(item)
            for item in snapshot.global_headlines
            if self._filter_by_currencies(item, currencies)
        ]
        latest_statements = (
            [deepcopy(item) for item in snapshot.official_statements]
            if include_latest_statements
            else []
        )
        themes = self._macro_themes(symbol, currencies, headlines)
        hotspots = self._geopolitical_hotspots(headlines + latest_statements)

        # Three-tier macro scoring (0-30 scale)
        tier_scores = self._compute_macro_tiers(
            symbol,
            currencies,
            headlines,
            events,
            themes,
            hotspots,
            ai_service=ai_service,
            global_snapshot=snapshot,
        )
        data_quality = self._macro_data_quality(headlines, events)

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
            "macro_data_quality_detail": self._macro_data_quality_detail(
                base=base, quote=quote, headlines=headlines, events=events,
                calendar_source=calendar_source, calendar_warning=calendar_warning,
                tier1_detail=tier_scores["tier1"]["detail"],
                tier3_detail=tier_scores["tier3"]["detail"],
                ai_available=ai_service is not None,
            ),  # Phase 15F.1: provenance from pre-fetched data
            "macro_v2": tier_scores.get("macro_v2"),  # Phase 15D.2: shadow diagnostics
            "warning": calendar_warning
            or ("" if events else "Không có dữ liệu sự kiện kinh tế sắp tới khớp cặp tiền trong nguồn đã kiểm tra."),
        }

    def data_quality_flags(
        self,
        symbol: str,
        *,
        buffer_minutes: int = 30,
        include_latest_statements: bool = True,
        ai_service: object | None = None,
    ) -> dict[str, object]:
        context = self.latest_macro_context(symbol, include_latest_statements=include_latest_statements, ai_service=ai_service)
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

    def execution_news_status(
        self,
        symbol: str,
        *,
        before_minutes: int = 30,
        after_minutes: int = 30,
        now: datetime | None = None,
    ) -> dict[str, object]:
        """Return a fail-closed, execution-time high-impact news status."""

        checked_at = now.astimezone(UTC) if now and now.tzinfo else (
            now.replace(tzinfo=UTC) if now else datetime.now(UTC)
        )
        try:
            context = self.latest_macro_context(
                symbol,
                include_latest_statements=False,
            )
        except Exception as exc:
            return {
                "available": False,
                "blackout": None,
                "checked_at": checked_at.isoformat(),
                "event": None,
                "reason_codes": ["NEWS_STATUS_UNAVAILABLE"],
                "message": str(exc),
            }

        source = str(context.get("source") or "").strip()
        normalized_source = source.lower()
        source_is_available = bool(
            source
            and normalized_source not in {"error", "none"}
            and "unavailable" not in normalized_source
        )
        events = context.get("events")
        if not source_is_available or not isinstance(events, list):
            return {
                "available": False,
                "blackout": None,
                "checked_at": checked_at.isoformat(),
                "event": None,
                "source": source,
                "reason_codes": ["NEWS_STATUS_UNAVAILABLE"],
            }

        before = max(0, int(before_minutes))
        after = max(0, int(after_minutes))
        blackout_event: dict[str, object] | None = None
        smallest_distance: float | None = None
        for event in events:
            if not isinstance(event, dict) or not _is_high_impact(
                str(event.get("impact", ""))
            ):
                continue
            event_time = _event_time(event)
            if event_time is None:
                continue
            event_time = event_time.astimezone(UTC)
            delta_minutes = (event_time - checked_at).total_seconds() / 60.0
            if -after <= delta_minutes <= before:
                distance = abs(delta_minutes)
                if smallest_distance is None or distance < smallest_distance:
                    smallest_distance = distance
                    blackout_event = dict(event)

        return {
            "available": True,
            "blackout": blackout_event is not None,
            "checked_at": checked_at.isoformat(),
            "event": blackout_event,
            "source": source,
            "reason_codes": (
                ["NEWS_BLACKOUT"] if blackout_event is not None else []
            ),
        }

    _preload_cache_ttl = timedelta(minutes=5)
    NEWS_WINDOW_DAYS = 7

    # Additional RSS feeds (free, no API key)
    EXTRA_RSS_FEEDS = [
        "https://www.fxstreet.com/rss/news",
        "https://www.investing.com/rss/news_301.rss",
    ]

    def _download_macro_source(self, ticker: str, *, now: datetime | None = None) -> dict[str, object]:
        """Fetch one Yahoo macro proxy via the shared single-flight cache."""
        return get_shared_cache().get_scalar(ticker, now=now, period="5d", interval="1d")

    def _fetch_global_calendar_payload(self) -> dict[str, object]:
        currencies = sorted(self.CURRENCY_KEYWORDS)
        result = self._ff_client.calendar_events(currencies)
        if not isinstance(result, dict):
            raise TypeError("Calendar provider returned a non-dict payload")
        source = str(result.get("source", ""))
        normalized_source = source.strip().lower()
        if not source or normalized_source in {"error", "none"} or "unavailable" in normalized_source:
            raise RuntimeError("Calendar source unavailable")
        events = result.get("events", [])
        cached_reader = getattr(self._ff_client, "_cached_calendar_events", None)
        if callable(cached_reader):
            try:
                cached_events = cached_reader()
                if isinstance(cached_events, list) and cached_events:
                    events = cached_events
            except Exception:
                pass
        return {
            "events": deepcopy(events),
            "source": source,
            "warning": str(result.get("warning", "")),
        }

    @staticmethod
    def _snapshot_source_status(
        status: str,
        *,
        source: str,
        now: datetime,
        previous: dict[str, object] | None = None,
        error_type: str = "",
        data_fetched_at_utc: str = "",
        origin_expires_at_utc: str = "",
        raw_provenance: dict[str, object] | None = None,
    ) -> dict[str, object]:
        previous = previous or {}

        # Yahoo-backed sources must retain the complete raw-cache provenance
        # schema for every final status, including unavailable. Keep this path
        # distinct from RSS/calendar metadata, which has no raw cache key.
        if raw_provenance is not None:
            raw = raw_provenance
            checked_at = str(raw.get("checked_at_utc", "") or now.isoformat())
            raw_data_fetched = str(
                raw.get("data_fetched_at_utc", "")
                or raw.get("fetched_at_utc", "")
            )
            raw_origin_expires = str(
                raw.get("origin_expires_at_utc", "")
                or raw.get("expires_at_utc", "")
            )
            previous_data_fetched = (
                str(previous.get("data_fetched_at_utc", ""))
                if status in {"stale", "unavailable"}
                else ""
            )
            previous_origin_expires = (
                str(previous.get("origin_expires_at_utc", ""))
                if status in {"stale", "unavailable"}
                else ""
            )
            served_data_fetched = (
                data_fetched_at_utc
                or raw_data_fetched
                or previous_data_fetched
            )
            if not served_data_fetched and status in {"fresh", "degraded"}:
                served_data_fetched = now.isoformat()
            served_origin_expires = (
                origin_expires_at_utc
                or raw_origin_expires
                or previous_origin_expires
            )
            if "next_retry_at_utc" in raw:
                next_retry_at = str(raw.get("next_retry_at_utc", "") or "")
            else:
                next_retry_at = str(previous.get("next_retry_at_utc", ""))
            if "cache_key" in raw:
                cache_key = deepcopy(raw.get("cache_key"))
            else:
                cache_key = deepcopy(previous.get("cache_key", []))
            refresh_error = str(
                error_type
                or raw.get("refresh_error_type", "")
                or raw.get("error_type", "")
                or ""
            )
            return {
                "status": status,
                "source": source,
                "cache_key": cache_key,
                "checked_at_utc": checked_at,
                "data_fetched_at_utc": served_data_fetched,
                "origin_expires_at_utc": served_origin_expires,
                "next_retry_at_utc": next_retry_at,
                "refresh_error_type": refresh_error,
            }

        payload: dict[str, object] = {
            "status": status,
            "source": source,
            "checked_at_utc": now.isoformat(),
        }
        if status in {"fresh", "degraded"}:
            # Prefer the cache's origin fetched_at over snapshot construction time.
            payload["data_fetched_at_utc"] = data_fetched_at_utc or now.isoformat()
        elif status == "stale":
            # Use the cache's origin timestamp if available; fall back to
            # the previous snapshot's record, then to checked_at. The origin
            # expiry must be retained even when the served value comes from a
            # previous snapshot (e.g. a discarded-fresh curve leg), so stale
            # provenance never loses its data-expiry evidence.
            if data_fetched_at_utc:
                payload["data_fetched_at_utc"] = data_fetched_at_utc
            elif previous:
                payload["data_fetched_at_utc"] = previous.get(
                    "data_fetched_at_utc", previous.get("checked_at_utc", "")
                )
            if not origin_expires_at_utc and previous:
                origin_expires_at_utc = str(previous.get("origin_expires_at_utc", ""))
        if origin_expires_at_utc:
            payload["origin_expires_at_utc"] = origin_expires_at_utc
        if error_type:
            payload["refresh_error_type"] = error_type
        return payload

    @staticmethod
    def _resolve_source_error(
        result_dict: dict[str, object],
        name: str,
        errors: dict[str, str],
    ) -> str:
        """Resolve the real refresh error for one source, consistently.

        ``get_scalar`` normalises stale errors to ``refresh_error_type`` while
        total failures carry ``error_type``; task-level exceptions land in
        ``errors``. Prefer the real source error in that order so provenance
        never hides an upstream failure behind a generic label.
        """
        return str(
            result_dict.get("refresh_error_type")
            or result_dict.get("error_type")
            or errors.get(name, "")
        )

    def _get_global_macro_snapshot(
        self,
        *,
        now: datetime | None = None,
    ) -> MacroGlobalSnapshot:
        checked_at = now or datetime.now(UTC)
        with self._global_snapshot_lock:
            current = self._global_snapshot
            if current is not None and checked_at < current.expires_at_utc:
                return current
            refreshed = self._refresh_global_macro_snapshot(checked_at, current)
            self._global_snapshot = refreshed
            self._global_headlines = [deepcopy(item) for item in refreshed.global_headlines]
            return refreshed

    def _refresh_global_macro_snapshot(
        self,
        now: datetime,
        previous: MacroGlobalSnapshot | None,
    ) -> MacroGlobalSnapshot:
        tasks = {
            "^TNX": lambda: self._download_macro_source("^TNX", now=now),
            "^FVX": lambda: self._download_macro_source("^FVX", now=now),
            "^VIX": lambda: self._download_macro_source("^VIX", now=now),
            "global_headlines": self._fetch_global_forex_headlines_with_status,
            "official_statements": self._latest_official_statements_with_status,
            "calendar": lambda: {
                "status": "fresh",
                "value": self._fetch_global_calendar_payload(),
                "attempted_sources": 1,
                "successful_sources": 1,
                "error_types": [],
            },
        }
        results: dict[str, object] = {}
        errors: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            futures = {executor.submit(task): name for name, task in tasks.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    results[name] = future.result()
                except Exception as exc:
                    errors[name] = type(exc).__name__

        def can_use_stale(source_name: str) -> bool:
            if previous is None:
                return False
            status = previous.source_status.get(source_name, {})
            if status.get("status") not in {"fresh", "degraded", "stale"}:
                return False
            raw_timestamp = status.get("data_fetched_at_utc")
            if not raw_timestamp:
                return False
            try:
                fetched_at = datetime.fromisoformat(str(raw_timestamp).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                return False
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=UTC)
            else:
                fetched_at = fetched_at.astimezone(UTC)
            return now < fetched_at + self._global_snapshot_stale_if_error
        stale_fields: list[str] = []
        source_status: dict[str, dict[str, object]] = {}

        scalar_values: dict[str, float | None] = {}
        previous_scalars = {
            "^TNX": previous.tnx if previous else None,
            "^FVX": previous.fvx if previous else None,
            "^VIX": previous.vix if previous else None,
        }
        for name in ("^TNX", "^FVX", "^VIX"):
            result = results.get(name)
            result_dict = result if isinstance(result, dict) else {}
            status = str(result_dict.get("status", ""))
            value = result_dict.get("value")
            fresh = status == "fresh" and value is not None
            cache_stale = status == "stale" and value is not None
            # Pull origin provenance from the shared-cache result.
            origin_fetched = str(
                result_dict.get("data_fetched_at_utc", "")
                or result_dict.get("fetched_at_utc", "")
            )
            origin_expires = str(
                result_dict.get("origin_expires_at_utc", "")
                or result_dict.get("expires_at_utc", "")
            )
            refresh_error = self._resolve_source_error(result_dict, name, errors)
            if fresh:
                scalar_values[name] = float(value)
                source_status[name] = self._snapshot_source_status(
                    "fresh", source=f"Yahoo Finance {name}", now=now,
                    data_fetched_at_utc=origin_fetched,
                    origin_expires_at_utc=origin_expires,
                    raw_provenance=result_dict,
                )
            elif cache_stale:
                scalar_values[name] = float(value)
                stale_fields.append(name)
                source_status[name] = self._snapshot_source_status(
                    "stale",
                    source=f"Yahoo Finance {name}",
                    now=now,
                    previous=previous.source_status.get(name) if previous else None,
                    error_type=refresh_error,
                    data_fetched_at_utc=origin_fetched,
                    origin_expires_at_utc=origin_expires,
                    raw_provenance=result_dict,
                )
            elif can_use_stale(name) and previous_scalars[name] is not None:
                scalar_values[name] = previous_scalars[name]
                stale_fields.append(name)
                source_status[name] = self._snapshot_source_status(
                    "stale",
                    source=f"Yahoo Finance {name}",
                    now=now,
                    previous=previous.source_status.get(name) if previous else None,
                    error_type=self._resolve_source_error(result_dict, name, errors),
                    raw_provenance=result_dict,
                )
            else:
                scalar_values[name] = None
                source_status[name] = self._snapshot_source_status(
                    "unavailable",
                    source=f"Yahoo Finance {name}",
                    now=now,
                    previous=previous.source_status.get(name) if previous else None,
                    error_type=self._resolve_source_error(result_dict, name, errors),
                    raw_provenance=result_dict,
                )

        # TNX/FVX form one curve input. If only one leg refreshes, never mix
        # fresh and stale observations; retain the prior coherent pair instead.
        tnx_result = results.get("^TNX") if isinstance(results.get("^TNX"), dict) else {}
        fvx_result = results.get("^FVX") if isinstance(results.get("^FVX"), dict) else {}
        tnx_fresh = tnx_result.get("status") == "fresh" and tnx_result.get("value") is not None
        fvx_fresh = fvx_result.get("status") == "fresh" and fvx_result.get("value") is not None
        can_reuse_curve = bool(
            previous is not None
            and previous.tnx is not None
            and previous.fvx is not None
            and can_use_stale("^TNX")
            and can_use_stale("^FVX")
        )
        curve_reused_from_previous = False
        if tnx_fresh != fvx_fresh and can_reuse_curve:
            scalar_values["^TNX"] = previous.tnx
            scalar_values["^FVX"] = previous.fvx
            curve_reused_from_previous = True
            for name, result_dict in (("^TNX", tnx_result), ("^FVX", fvx_result)):
                if name not in stale_fields:
                    stale_fields.append(name)
                # Keep the leg's REAL source error (e.g. RuntimeError from a
                # failed download). Only fall back to the generic peer label
                # when the leg itself reported no error — i.e. its fresh value
                # is discarded solely because its curve peer is unusable.
                error_type = self._resolve_source_error(result_dict, name, errors)
                if not error_type:
                    error_type = "YieldCurvePeerUnavailable"
                # When the served value comes from the shared cache's stale
                # entry, retain that entry's origin fetched/expires timestamps.
                # For a discarded fresh leg the served value is previous's, so
                # carry over the PREVIOUS record's origin fetched/expiry — the
                # healthy leg must not lose its data-expiry evidence.
                previous_status = previous.source_status.get(name) if previous else {}
                served_from_stale_cache = result_dict.get("status") == "stale"
                if served_from_stale_cache:
                    origin_fetched = str(
                        result_dict.get("data_fetched_at_utc", "")
                        or result_dict.get("fetched_at_utc", "")
                    )
                    origin_expires = str(
                        result_dict.get("origin_expires_at_utc", "")
                        or result_dict.get("expires_at_utc", "")
                    )
                else:
                    origin_fetched = str(previous_status.get("data_fetched_at_utc", ""))
                    origin_expires = str(previous_status.get("origin_expires_at_utc", ""))
                source_status[name] = self._snapshot_source_status(
                    "stale",
                    source=f"Yahoo Finance {name}",
                    now=now,
                    previous=previous_status,
                    error_type=error_type,
                    data_fetched_at_utc=origin_fetched,
                    origin_expires_at_utc=origin_expires,
                    raw_provenance=result_dict,
                )
                discarded_fresh = bool(result_dict.get("status") == "fresh")
                source_status[name]["refresh_discarded_for_curve_consistency"] = discarded_fresh
                if discarded_fresh:
                    # Canonical fields above describe the old value actually
                    # served. Preserve the healthy refresh's own origin too, so
                    # coherent-curve fallback does not erase that observation.
                    refreshed_status = self._snapshot_source_status(
                        "fresh",
                        source=f"Yahoo Finance {name}",
                        now=now,
                        raw_provenance=result_dict,
                    )
                    provenance_keys = (
                        "cache_key",
                        "checked_at_utc",
                        "data_fetched_at_utc",
                        "origin_expires_at_utc",
                        "next_retry_at_utc",
                        "refresh_error_type",
                    )
                    source_status[name]["discarded_refresh_provenance"] = {
                        key: deepcopy(refreshed_status[key]) for key in provenance_keys
                    }

        curve_is_coherent = bool(
            (tnx_fresh and fvx_fresh)
            or curve_reused_from_previous
            or (
                not tnx_fresh
                and not fvx_fresh
                and can_reuse_curve
                and scalar_values["^TNX"] == previous.tnx
                and scalar_values["^FVX"] == previous.fvx
            )
        )
        if not curve_is_coherent:
            scalar_values["^TNX"] = None
            scalar_values["^FVX"] = None
            source_status["^TNX"]["discarded_for_curve_consistency"] = True
            source_status["^FVX"]["discarded_for_curve_consistency"] = True

        def collection_value(
            name: str,
            previous_value: object,
            empty_value: object,
            source: str,
        ) -> object:
            result = results.get(name)
            result_dict = result if isinstance(result, dict) else {}
            result_status = str(result_dict.get("status", ""))
            result_value = result_dict.get("value")
            refresh_error_types = (
                list(result_dict.get("error_types", []))
                if isinstance(result_dict.get("error_types"), (list, tuple))
                else []
            )
            if name in errors:
                refresh_error_types.append(errors[name])
            refresh_error_types = sorted(set(str(item) for item in refresh_error_types if item))
            use_previous = result_status == "degraded" and can_use_stale(name)
            if result_status in {"fresh", "degraded"} and not use_previous:
                source_status[name] = self._snapshot_source_status(
                    result_status, source=source, now=now
                )
                source_status[name].update({
                    "attempted_sources": int(result_dict.get("attempted_sources", 0) or 0),
                    "successful_sources": int(result_dict.get("successful_sources", 0) or 0),
                    "refresh_error_types": refresh_error_types,
                })
                return deepcopy(result_value)
            if can_use_stale(name):
                stale_fields.append(name)
                source_status[name] = self._snapshot_source_status(
                    "stale",
                    source=source,
                    now=now,
                    previous=previous.source_status.get(name) if previous else None,
                    error_type=",".join(refresh_error_types),
                )
                source_status[name].update({
                    "attempted_sources": int(result_dict.get("attempted_sources", 0) or 0),
                    "successful_sources": int(result_dict.get("successful_sources", 0) or 0),
                    "refresh_error_types": refresh_error_types,
                })
                return deepcopy(previous_value)
            source_status[name] = self._snapshot_source_status(
                "unavailable",
                source=source,
                now=now,
                error_type=",".join(refresh_error_types),
            )
            source_status[name].update({
                "attempted_sources": int(result_dict.get("attempted_sources", 0) or 0),
                "successful_sources": int(result_dict.get("successful_sources", 0) or 0),
                "refresh_error_types": refresh_error_types,
            })
            return deepcopy(empty_value)

        headlines = collection_value(
            "global_headlines",
            previous.global_headlines if previous else (),
            [],
            "Global RSS feeds",
        )
        statements = collection_value(
            "official_statements",
            previous.official_statements if previous else (),
            [],
            "Official-statement RSS queries",
        )
        calendar = collection_value(
            "calendar",
            previous.calendar_payload if previous else {},
            {"events": [], "source": "Calendar unavailable", "warning": ""},
            "Forex Factory calendar",
        )

        tnx = scalar_values["^TNX"]
        fvx = scalar_values["^FVX"]
        raw_spread = tnx - fvx if tnx is not None and fvx is not None else None
        spread = round(raw_spread, 2) if raw_spread is not None else None
        if "^TNX" in stale_fields or "^FVX" in stale_fields:
            steepening = previous.yield_steepening if previous else None
        else:
            tnx_result = results.get("^TNX") if isinstance(results.get("^TNX"), dict) else {}
            fvx_result = results.get("^FVX") if isinstance(results.get("^FVX"), dict) else {}
            previous_tnx = tnx_result.get("previous")
            previous_fvx = fvx_result.get("previous")
            steepening = (
                raw_spread > float(previous_tnx) - float(previous_fvx)
                if raw_spread is not None and previous_tnx is not None and previous_fvx is not None
                else False
            )

        # Expiry is derived from FINAL statuses (after coherent-curve/RSS
        # fallback), not raw task results. A retry gate may shorten cache life,
        # but can never extend the served data's hard stale deadline.
        snapshot_expires = now + self._global_snapshot_ttl

        def provenance_time(raw_value: object) -> datetime | None:
            if not raw_value:
                return None
            try:
                parsed = datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                return None
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)

        for final_status in source_status.values():
            status_name = str(final_status.get("status", ""))
            candidates: list[datetime] = []
            if status_name in {"fresh", "degraded"}:
                origin_expiry = provenance_time(
                    final_status.get("origin_expires_at_utc")
                )
                if origin_expiry is not None:
                    candidates.append(origin_expiry)
            elif status_name == "stale":
                next_retry = provenance_time(final_status.get("next_retry_at_utc"))
                if next_retry is not None:
                    candidates.append(next_retry)
                origin_fetched = provenance_time(
                    final_status.get("data_fetched_at_utc")
                )
                if origin_fetched is not None:
                    candidates.append(
                        origin_fetched + self._global_snapshot_stale_if_error
                    )
            elif status_name == "unavailable":
                # Do not clamp unavailable by an already-expired stale
                # deadline. It may be cached until the retry gate reopens.
                next_retry = provenance_time(final_status.get("next_retry_at_utc"))
                if next_retry is not None:
                    candidates.append(next_retry)

            for candidate in candidates:
                if candidate < snapshot_expires:
                    snapshot_expires = candidate

        return MacroGlobalSnapshot(
            fetched_at_utc=now,
            expires_at_utc=snapshot_expires,
            tnx=tnx,
            fvx=fvx,
            yield_spread_10y_5y=spread,
            yield_steepening=steepening,
            vix=scalar_values["^VIX"],
            global_headlines=tuple(deepcopy(headlines)) if isinstance(headlines, (list, tuple)) else (),
            official_statements=tuple(deepcopy(statements)) if isinstance(statements, (list, tuple)) else (),
            calendar_payload=deepcopy(calendar) if isinstance(calendar, dict) else {},
            source_status=source_status,
            stale_fields=tuple(stale_fields),
        )

    def _calendar_context_from_snapshot(
        self,
        snapshot: MacroGlobalSnapshot,
        currencies: list[str],
    ) -> dict[str, object]:
        payload = snapshot.calendar_payload
        rows = payload.get("events", []) if isinstance(payload, dict) else []
        rows = rows if isinstance(rows, list) else []
        selector = getattr(self._ff_client, "_select_calendar_events", None)
        if callable(selector):
            events = selector(currencies, rows)
        else:
            wanted = {currency.upper() for currency in currencies}
            events = [
                deepcopy(row)
                for row in rows
                if isinstance(row, dict)
                and str(row.get("currency", "")).upper() in wanted
            ][:8]
        return {
            "events": deepcopy(events),
            "source": str(payload.get("source", "")) if isinstance(payload, dict) else "",
            "warning": str(payload.get("warning", "")) if isinstance(payload, dict) else "",
        }

    def preload_macro_contexts(self, symbols: list[str], progress_callback=None, *, ai_service: object | None = None) -> None:
        """Pre-fetch RSS (1 query tong quat) + calendar + compute tier scores.

        Results are cached for _preload_cache_ttl (5 min) to avoid redundant
        HTTP calls on repeated scans.
        """
        if not symbols:
            return
        progress = progress_callback or (lambda _p, _m: None)

        now = datetime.now(UTC)
        progress(15, "Đang tải snapshot vĩ mô toàn cầu...")
        snapshot = self._get_global_macro_snapshot(now=now)

        # Pre-compute every requested key against the exact same snapshot.
        self._preloading = True
        try:
            total = max(1, len(symbols))
            for idx, symbol in enumerate(symbols):
                progress(17 + int((idx + 1) / total * 2), f"Đang phân tích vĩ mô {symbol} ({idx + 1}/{total})...")
                self.latest_macro_context(
                    symbol,
                    include_latest_statements=True,
                    ai_service=ai_service,
                    _snapshot=snapshot,
                )
        finally:
            self._preloading = False

        self._last_fetch_time = snapshot.fetched_at_utc
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
        result = self._fetch_global_forex_headlines_with_status()
        value = result.get("value", [])
        return value if isinstance(value, list) else []

    @staticmethod
    def _rss_collection_result(
        value: list[dict[str, object]],
        *,
        attempted_sources: int,
        successful_sources: int,
        error_types: list[str],
    ) -> dict[str, object]:
        if successful_sources <= 0:
            status = "unavailable"
        elif successful_sources < attempted_sources:
            status = "degraded"
        else:
            status = "fresh"
        return {
            "status": status,
            "value": value,
            "attempted_sources": attempted_sources,
            "successful_sources": successful_sources,
            "error_types": sorted(set(error_types)),
        }

    def _fetch_global_forex_headlines_with_status(self) -> dict[str, object]:
        """Fetch broad RSS queries while preserving success/error provenance."""
        rows: list[dict[str, object]] = []
        seen: set[str] = set()
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        broad_queries = [
            "forex central bank Fed ECB BOJ BOE rate decision macro latest",
            "global macro risk sentiment dollar yen euro pound forex markets",
            "forex geopolitical oil gold safe haven latest",
        ]

        def _fetch_one(query: str) -> tuple[list[dict[str, object]], dict[str, object]]:
            items: list[dict[str, object]] = []
            url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=en-US&gl=US&ceid=US:en"
            rss_items, fetch_status = self._rss_items_with_status(url, query=query)
            for item in rss_items:
                title_key = str(item.get("title", "")).lower()
                if not title_key:
                    continue
                published = parse_rss_time(str(item.get("published_utc", "")))
                if not published or published < cutoff:
                    continue
                items.append(item)
            return items, fetch_status

        successful_sources = 0
        error_types: list[str] = []
        with ThreadPoolExecutor(max_workers=3) as ex:
            futures = {ex.submit(_fetch_one, q): q for q in broad_queries}
            for future in as_completed(futures):
                try:
                    items, fetch_status = future.result()
                    if fetch_status.get("status") == "fresh":
                        successful_sources += 1
                    else:
                        error_type = str(fetch_status.get("error_type", ""))
                        if error_type:
                            error_types.append(error_type)
                    for item in items:
                        title_key = str(item.get("title", "")).lower()
                        if title_key in seen:
                            continue
                        seen.add(title_key)
                        rows.append(item)
                except Exception as exc:
                    error_types.append(type(exc).__name__)
        return self._rss_collection_result(
            rows,
            attempted_sources=len(broad_queries),
            successful_sources=successful_sources,
            error_types=error_types,
        )

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
        *,
        ai_service: object | None = None,
        global_snapshot: MacroGlobalSnapshot | None = None,
    ) -> dict[str, object]:
        snapshot = global_snapshot or self._get_global_macro_snapshot()
        base = currencies[0] if currencies else ""
        quote = currencies[1] if len(currencies) > 1 else ""
        base_headlines = [str(h.get("title", "")) for h in headlines if self._matches_currency(h, base)]
        quote_headlines = [str(h.get("title", "")) for h in headlines if self._matches_currency(h, quote)]
        base_stance = self._ai_currency_stance(base, base_headlines, ai_service)
        quote_stance = self._ai_currency_stance(quote, quote_headlines, ai_service)

        tier1_buy, tier1_sell, tier1_detail = self._macro_tier1(
            base,
            quote,
            base_stance,
            quote_stance,
            yield_spread_data=snapshot.yield_spread_payload(),
        )
        tier2_buy, tier2_sell, tier2_detail = self._macro_tier2(base, quote, events)
        tier3_buy, tier3_sell, tier3_detail = self._macro_tier3(
            currencies,
            headlines,
            hotspots,
            ai_service=ai_service,
            vix_data={"vix": snapshot.vix},
        )

        raw_buy = tier1_buy + tier2_buy + tier3_buy
        raw_sell = tier1_sell + tier2_sell + tier3_sell

        # Phase 15D: Macro V2 — pair-relative currency strength (shadow mode)
        macro_v2 = self._compute_macro_v2(base, quote, base_stance, quote_stance,
                                          tier1_detail)

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
            "macro_v2": macro_v2,
        }

    def _ai_currency_stance(
        self,
        currency: str,
        headlines: list[str],
        ai_service: object | None = None,
    ) -> str:
        """Dùng AI đánh giá hawkish/dovish cho 1 tiền tệ từ danh sách headline.
        Trả về: "hawkish" | "dovish" | "neutral"
        Fallback về keyword matching nếu AI không khả dụng.
        """
        if not ai_service or not headlines:
            return currency_stance(headlines, self.HAWKISH_TERMS, self.DOVISH_TERMS)

        cache_key = json.dumps(
            {
                "currency": currency,
                "headlines": headlines[:5],
                "ai": self._ai_fingerprint(ai_service),
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        cached = self._stance_cache.get(cache_key)
        if cached and (datetime.now(UTC) - cached[1]).total_seconds() < 1800:
            return cached[0]

        prompt = f"""Bạn là chuyên gia phân tích vĩ mô forex.
Đọc các headline dưới đây liên quan đến {currency} và đánh giá xu hướng chính sách tiền tệ.
Trả lời DUY NHẤT 1 từ: hawkish, dovish, hoặc neutral. Không giải thích.

Headlines:
{chr(10).join(f'- {h}' for h in headlines[:8])}

Trả lời:"""

        try:
            response = ai_service.analyze(prompt, max_tokens=10)
            result = response.strip().lower().split()[0]
            if result in ("hawkish", "dovish", "neutral"):
                self._stance_cache[cache_key] = (result, datetime.now(UTC))
                return result
        except Exception:
            pass

        # Fallback nếu AI lỗi hoặc trả về không hợp lệ
        fallback = currency_stance(headlines, self.HAWKISH_TERMS, self.DOVISH_TERMS)
        self._stance_cache[cache_key] = (fallback, datetime.now(UTC))
        return fallback

    # --- Tier 1: Interest Rate & Monetary Policy (0-12) ---

    @staticmethod
    def _fetch_yield_spread() -> dict[str, object]:
        try:
            tnx = yf.download("^TNX", period="5d", interval="1d", progress=False)
            fvx = yf.download("^FVX", period="5d", interval="1d", progress=False)
            if tnx.empty or fvx.empty:
                return {"spread": None, "tnx": None, "fvx": None}
            import pandas as pd
            if isinstance(tnx.columns, pd.MultiIndex):
                tnx_close = float(tnx.iloc[-1, 0])
                fvx_close = float(fvx.iloc[-1, 0])
            else:
                tnx_close = float(tnx["Close"].iloc[-1])
                fvx_close = float(fvx["Close"].iloc[-1])
            spread = tnx_close - fvx_close
            steepening = False
            if len(tnx) >= 2 and len(fvx) >= 2:
                if isinstance(tnx.columns, pd.MultiIndex):
                    prev_tnx = float(tnx.iloc[-2, 0])
                    prev_fvx = float(fvx.iloc[-2, 0])
                else:
                    prev_tnx = float(tnx["Close"].iloc[-2])
                    prev_fvx = float(fvx["Close"].iloc[-2])
                prev_spread = prev_tnx - prev_fvx
                steepening = spread > prev_spread
            return {
                "spread": round(spread, 2),
                "tnx": tnx_close, "fvx": fvx_close, "steepening": steepening,
                # Phase 15F.2: canonical field names (^TNX=10Y, ^FVX=5Y)
                "ten_year_yield": round(float(tnx_close), 2),
                "five_year_yield": round(float(fvx_close), 2),
                "yield_spread_10y_5y": round(spread, 2),
                # Deprecated alias — same value, remove after Phase 15G
                "yield_spread_2s10s": round(spread, 2),
                "_deprecated_alias": "yield_spread_2s10s is a 10Y-5Y spread (^TNX - ^FVX), kept for backward compat. Use yield_spread_10y_5y.",
            }
        except Exception:
            return {
                "spread": None, "tnx": None, "fvx": None,
                "ten_year_yield": None, "five_year_yield": None,
                "yield_spread_10y_5y": None,
                "yield_spread_2s10s": None,
            }

    # --- Phase 15D.1: Macro V2 — pair-relative currency strength (hardened) ---

    def _compute_macro_v2(
        self, base: str, quote: str, base_stance: str, quote_stance: str,
        tier1_detail: dict[str, object],
    ) -> dict[str, object]:
        """Compute pair-relative macro scores from currency strength.

        base_strength and quote_strength from rate, trend, and stance.
        pair_edge = base_strength - quote_strength.
        Exact symmetry: sell_v2 = 30 - buy_v2 (buy computed by round/clamp).
        Missing/unavailable data = neutral score (2), tracked in availability.
        """
        rates = self._load_interest_rates()
        base_info = rates.get(base, {})
        quote_info = rates.get(quote, {})

        # --- Component availability ---
        # Phase 15G.4: rate=0.0 is valid data; use type-check + parse, not bool()
        def _rate_available(info: dict) -> bool:
            v = info.get("rate") if isinstance(info, dict) else None
            if v is None:
                return False
            try:
                float(str(v).replace("%", ""))
                return True
            except (ValueError, TypeError):
                return False

        def _trend_available(info: dict) -> bool:
            v = info.get("trend") if isinstance(info, dict) else None
            return isinstance(v, str) and v.strip() in ("hike", "hold", "cut")

        base_rate_avail = _rate_available(base_info)
        quote_rate_avail = _rate_available(quote_info)
        base_trend_avail = _trend_available(base_info)
        quote_trend_avail = _trend_available(quote_info)
        base_stance_avail = isinstance(base_stance, str) and base_stance.strip()
        quote_stance_avail = isinstance(quote_stance, str) and quote_stance.strip()

        # --- Currency strength components (0-4 each) ---
        # Missing data → neutral score 2 (not 0 dovish/weak)

        def _rate_score(info: dict, available: bool) -> tuple[int, bool]:
            if not available:
                return 2, False
            try:
                f = float(str(info.get("rate", 0)).replace("%", ""))
            except (ValueError, TypeError):
                return 2, False
            return round(4 * min(abs(f), 5.0) / 5.0), True

        def _trend_score(info: dict, available: bool) -> tuple[int, bool]:
            trend_map = {"hike": 4, "hold": 2, "cut": 0}
            if not available:
                return 2, False
            return int(trend_map.get(str(info.get("trend", "hold")), 2)), True

        def _stance_score(stance: str, available: bool) -> tuple[int, bool]:
            stance_map = {"hawkish": 4, "neutral": 2, "dovish": 0}
            if not available:
                return 2, False
            return int(stance_map.get(stance.strip().lower(), 2)), True

        base_rate, br_ok = _rate_score(base_info, base_rate_avail)
        quote_rate, qr_ok = _rate_score(quote_info, quote_rate_avail)
        base_trend, bt_ok = _trend_score(base_info, base_trend_avail)
        quote_trend, qt_ok = _trend_score(quote_info, quote_trend_avail)
        base_st, bs_ok = _stance_score(base_stance, base_stance_avail)
        quote_st, qs_ok = _stance_score(quote_stance, quote_stance_avail)

        # --- Currency strength (0-12) ---
        base_strength = base_rate + base_trend + base_st
        quote_strength = quote_rate + quote_trend + quote_st

        # Pair edge: positive = base stronger → favors BUY  [-12, +12]
        pair_edge = base_strength - quote_strength

        # Exact symmetry: compute buy, derive sell = 30 - buy
        scale = 30.0 / 24.0
        buy_v2 = round(max(0.0, min(30.0, 15.0 + pair_edge * scale)))
        sell_v2 = 30 - buy_v2

        # Confidence: fraction of 6 components available
        total_avail = sum([br_ok, qr_ok, bt_ok, qt_ok, bs_ok, qs_ok])
        confidence = round(total_avail / 6.0, 2)

        return {
            "base_strength": base_strength,
            "quote_strength": quote_strength,
            "pair_edge": pair_edge,
            "buy": buy_v2,
            "sell": sell_v2,
            "confidence": confidence,
            "availability": {
                "base_rate": br_ok, "quote_rate": qr_ok,
                "base_trend": bt_ok, "quote_trend": qt_ok,
                "base_stance": bs_ok, "quote_stance": qs_ok,
            },
            "components": {
                "base": {"rate": base_rate, "trend": base_trend, "stance": base_st},
                "quote": {"rate": quote_rate, "trend": quote_trend, "stance": quote_st},
            },
        }

    def _macro_tier1(
        self,
        base: str,
        quote: str,
        base_stance: str,
        quote_stance: str,
        *,
        yield_spread_data: dict[str, object] | None = None,
    ) -> tuple[int, int, dict[str, object]]:
        rates = self._load_interest_rates()
        base_info = rates.get(base, {})
        quote_info = rates.get(quote, {})

        # Rate differential score (0-4) — linear scale
        MAX_DIFF = 5.0
        rate_diff = self.rate_differential(base, quote)
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
        yield_spread_data = yield_spread_data or {
            "spread": None,
            "tnx": None,
            "fvx": None,
            "steepening": None,
            "ten_year_yield": None,
            "five_year_yield": None,
        }
        spread_val = yield_spread_data.get("spread")
        if spread_val is not None and "USD" in (base, quote):
            if spread_val < 0:
                if base == "USD":
                    yield_adj_buy, yield_adj_sell = -2, 2
                else:
                    yield_adj_buy, yield_adj_sell = 2, -2
            elif spread_val > 0.5 and yield_spread_data.get("steepening"):
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
            "ten_year_yield": yield_spread_data.get("ten_year_yield"),
            "five_year_yield": yield_spread_data.get("five_year_yield"),
            "yield_spread_tnx": yield_spread_data.get("tnx"),
            "yield_spread_fvx": yield_spread_data.get("fvx"),
            "yield_spread_steepening": yield_spread_data.get("steepening"),
            "yield_spread_adj": {"buy": yield_adj_buy, "sell": yield_adj_sell},
            "components": {
                "rate_diff": {"buy": diff_buy, "sell": diff_sell},
                "rate_trend": {"buy": trend_buy, "sell": trend_sell},
                "stance": {"buy": stance_buy, "sell": stance_sell},
            },
        }
        return (max(0, min(12, diff_buy + trend_buy + stance_buy + yield_adj_buy)),
                max(0, min(12, diff_sell + trend_sell + stance_sell + yield_adj_sell)), detail)

    # --- Tier 2: Economic Calendar Impact (0-10) ---
    def _macro_tier2(self, base: str, quote: str, events: list[dict[str, object]]) -> tuple[int, int, dict[str, object]]:
        EVENT_SEVERITY = {
            "nonfarm payrolls": 3, "nfp": 3, "fomc": 3, "cpi": 3, "core cpi": 3,
            "pce": 3, "gdp": 3, "interest rate decision": 3, "unemployment": 3,
            "fed": 3,
            "ism manufacturing": 2, "ism services": 2, "retail sales": 2,
            "ppi": 2, "consumer confidence": 2, "durable goods": 2,
        }
        now = datetime.now(UTC)
        cutoff = now + timedelta(hours=72)

        base_quality = 0
        quote_quality = 0
        base_total = 0
        quote_total = 0
        base_events_detail: list[dict[str, object]] = []
        quote_events_detail: list[dict[str, object]] = []
        has_surprise = False  # Phase 15C: track if any event has actual/forecast

        for event in events:
            currency = str(event.get("currency", ""))
            title = str(event.get("event", "")).lower()
            event_time = _event_time(event)
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

    # --- Tier 3: Risk Sentiment & Geopolitical (0-12) ---

    @staticmethod
    def _fetch_vix() -> dict[str, object]:
        try:
            vix = yf.download("^VIX", period="5d", interval="1d", progress=False)
            if vix.empty:
                return {"vix": None}
            import pandas as pd
            if isinstance(vix.columns, pd.MultiIndex):
                vix_close = float(vix.iloc[-1, 0])
            else:
                vix_close = float(vix["Close"].iloc[-1])
            return {"vix": vix_close}
        except Exception:
            return {"vix": None}

    def _macro_tier3(
        self, currencies: list[str], headlines: list[dict[str, object]], hotspots: list[dict[str, object]],
        ai_service: object | None = None,
        *,
        vix_data: dict[str, object] | None = None,
    ) -> tuple[int, int, dict[str, object]]:
        SENTIMENT_LEXICON = {
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
        NEGATION_WORDS = {"no", "not", "fade", "fades", "fading", "diminish", "diminishes",
                          "ease", "eases", "eased", "subside", "subsides"}

        all_text = " ".join(str(item.get("title", "")) for item in headlines).lower()

        base = currencies[0] if currencies else ""
        quote = currencies[1] if len(currencies) > 1 else ""
        safe_havens = {"USD", "JPY", "CHF", "XAU"}
        risk_currencies = {"AUD", "NZD", "CAD"}

        base_is_safe = base in safe_havens
        quote_is_safe = quote in safe_havens
        base_is_risk = base in risk_currencies
        quote_is_risk = quote in risk_currencies

        # --- AI stance (if available) ---
        ai_sentiment_score = None
        if ai_service is not None:
            try:
                base_headlines = [str(h.get("title", "")) for h in headlines if self._matches_currency(h, base)]
                quote_headlines = [str(h.get("title", "")) for h in headlines if self._matches_currency(h, quote)]
                base_stance = self._ai_currency_stance(base, base_headlines, ai_service)
                quote_stance = self._ai_currency_stance(quote, quote_headlines, ai_service)
                stance_map = {"hawkish": -2, "dovish": 2, "neutral": 0}
                ai_sentiment_score = stance_map.get(base_stance, 0) + stance_map.get(quote_stance, 0)
            except Exception:
                ai_sentiment_score = None

        # --- Keyword lexicon scoring ---
        raw_sentiment = 0
        matched_terms: list[dict[str, object]] = []
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
                matched_terms.append({"term": term, "weight": weight, "effective": effective_weight, "negated": negated})
                idx = end

        # --- Combine AI + lexicon ---
        # Phase 15E: AI stance already contributes via Tier 1 (stance delta).
        # Tier 3 ai_sentiment_score is DIAGNOSTIC ONLY — not added to raw_sentiment.
        ai_used = ai_sentiment_score is not None and ai_sentiment_score != 0
        # (ai_sentiment_score * 3 no longer added to raw_sentiment)

        # --- VIX adjustment ---
        vix_data = vix_data or {"vix": None}
        vix_level = vix_data.get("vix")
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
        # Phase 15E: VIX already contributes via correlation_adjustment().
        # Tier 3 vix_adj is DIAGNOSTIC ONLY — not added to raw_sentiment.

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
            "ai_sentiment_used": ai_used,
            "ai_sentiment_score": ai_sentiment_score,
            "ai_applied_to_score": False,  # Phase 15E: only Tier 1 stance contributes
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

    # --- Phase 15F.1: Data quality provenance (uses pre-fetched data only) ---

    def _macro_data_quality_detail(
        self, *, base: str, quote: str,
        headlines: list[dict[str, object]], events: list[dict[str, object]],
        calendar_source: str, calendar_warning: str,
        tier1_detail: dict[str, object], tier3_detail: dict[str, object],
        ai_available: bool,
    ) -> dict[str, object]:
        """Per-component provenance from pre-fetched pipeline data.
        Does NOT re-fetch VIX, yields, or rates.
        """
        now = datetime.now(UTC)

        def _headline_age(hl: list[dict]) -> float | None:
            newest = None
            for h in hl:
                pub = h.get("published_utc", "")
                if not pub:
                    continue
                try:
                    t = datetime.fromisoformat(str(pub).replace("Z", "+00:00"))
                    if newest is None or t > newest:
                        newest = t
                except ValueError:
                    pass
            return round((now - newest).total_seconds() / 3600.0, 1) if newest else None

        def _age_conf(age_hours: float | None) -> tuple[float, str]:
            if age_hours is None:
                return 0.0, "stale"
            if age_hours <= 3:
                return 1.0, "fresh"
            if age_hours <= 6:
                return 0.8, "recent"
            if age_hours <= 12:
                return 0.5, "aging"
            return 0.2, "stale"

        # --- Rates (from pre-loaded _load_interest_rates, already fetched) ---
        rates = self._load_interest_rates()
        base_info = rates.get(base, {})
        quote_info = rates.get(quote, {})
        rate_source = str(rates.get("_source", "unknown"))
        rate_updated = rates.get("_updated")  # ISO timestamp or None
        is_fallback = rate_source == "fallback"
        # Confidence: degrade if fallback or stale (>7 days since update)
        rate_conf = 1.0
        if is_fallback:
            rate_conf = 0.5
        if rate_updated:
            try:
                age_days = (now - datetime.fromisoformat(str(rate_updated).replace("Z", "+00:00"))).days
                if age_days > 30:
                    rate_conf = min(rate_conf, 0.3)
                elif age_days > 7:
                    rate_conf = min(rate_conf, 0.6)
            except (ValueError, TypeError):
                rate_conf = min(rate_conf, 0.7)

        # --- Calendar (from pre-fetched calendar_events) ---
        cal_fetch_ok = str(calendar_warning) == "" or "no_fetch" not in str(calendar_warning).lower()
        cal_avail = cal_fetch_ok and calendar_source != "none"
        cal_conf = 1.0 if cal_avail else 0.0
        if str(calendar_warning).strip():
            cal_conf = min(cal_conf, 0.8)

        # --- Headlines ---
        base_headlines = [h for h in headlines if self._matches_currency(h, base)]
        quote_headlines = [h for h in headlines if self._matches_currency(h, quote)]
        global_headlines = [h for h in headlines
                           if not self._matches_currency(h, base)
                           and not self._matches_currency(h, quote)]
        base_age = _headline_age(base_headlines)
        quote_age = _headline_age(quote_headlines)
        base_conf, base_fresh = _age_conf(base_age)
        quote_conf, quote_fresh = _age_conf(quote_age)

        # --- AI stance (from actual ai_service availability, not fetch) ---
        stance_used = str(tier1_detail.get("base_stance", "")).strip()
        stance_from_ai = bool(stance_used) and not (
            stance_used in ("hawkish", "neutral", "dovish")
            and not ai_available  # AI unavailable → keyword fallback
        )
        ai_is_fallback = not ai_available

        # --- Market proxies (from tier1_detail and tier3_detail, pre-fetched) ---
        vix_val = tier3_detail.get("vix_level")
        vix_avail = vix_val is not None
        yield_val = tier1_detail.get("yield_spread_10y_5y") or tier1_detail.get("yield_spread_2s10s")
        yield_avail = yield_val is not None

        return {
            "rates": {
                "available": bool(base_info) and bool(quote_info),
                "source": rate_source,
                "is_fallback": is_fallback,
                "last_updated": rate_updated,
                "confidence": round(rate_conf, 2),
            },
            "calendar": {
                "available": cal_avail,
                "source": str(calendar_source),
                "warning": str(calendar_warning) if calendar_warning else None,
                "event_count": len(events),
                "has_warning": bool(str(calendar_warning).strip()),
                "confidence": round(cal_conf, 2),
            },
            "headlines": {
                "base_count": len(base_headlines),
                "quote_count": len(quote_headlines),
                "global_count": len(global_headlines),
                "base_freshness": base_fresh,
                "quote_freshness": quote_fresh,
                "base_age_hours": base_age,
                "quote_age_hours": quote_age,
                "base_confidence": base_conf,
                "quote_confidence": quote_conf,
                "global_not_counted_for_coverage": True,
            },
            "ai_stance": {
                "available": ai_available,
                "source": "ai_service" if ai_available else "keyword_fallback",
                "is_fallback": ai_is_fallback,
                "stance_used_for_tier1": stance_used if stance_used else None,
                "confidence": 1.0 if ai_available else 0.4,
            },
            "market_proxies": {
                "vix": {
                    "available": vix_avail,
                    "source": "yahoo_finance" if vix_avail else "unavailable",
                    "level": vix_val,
                    "is_fallback": not vix_avail,
                    "confidence": 1.0 if vix_avail else 0.0,
                },
                "yield_spread": {
                    "available": yield_avail,
                    "source": "yahoo_finance" if yield_avail else "unavailable",
                    "spread_2s10s": yield_val,
                    "is_fallback": not yield_avail,
                    "confidence": 1.0 if yield_avail else 0.0,
                },
            },
        }

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
        
        stance_map = {"hawkish": "Thắt chặt", "dovish": "Nới lỏng", "neutral": "Trung tính"}
        bs_vn = stance_map.get(str(base_stance).lower(), base_stance)
        qs_vn = stance_map.get(str(quote_stance).lower(), quote_stance)
        
        sent_raw = str(tier3_detail.get('risk_sentiment', 'neutral')).lower()
        sent_map = {"risk_on": "Chấp nhận rủi ro", "risk_off": "Né tránh rủi ro", "neutral": "Trung tính"}
        sent_vn = sent_map.get(sent_raw, sent_raw)

        parts = [
            f"[T1] {base}={base_rate}({bs_vn}) so với {quote}={quote_rate}({qs_vn})",
            f"[T2] Sự kiện lịch KT: base={tier2_detail.get('base_event_weight',0)}, quote={tier2_detail.get('quote_event_weight',0)}",
            f"[T3] Tâm lý TT={sent_vn}, điểm nóng={tier3_detail.get('hotspot_count',0)}",
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
        result = self._latest_official_statements_with_status()
        value = result.get("value", [])
        return value if isinstance(value, list) else []

    def _latest_official_statements_with_status(self) -> dict[str, object]:
        """Fetch statement RSS queries with explicit partial/error provenance."""
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

        def _fetch_one(query: str) -> tuple[list[dict[str, object]], dict[str, object]]:
            items: list[dict[str, object]] = []
            url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=en-US&gl=US&ceid=US:en"
            rss_items, fetch_status = self._rss_items_with_status(url, query=query)
            for item in rss_items:
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
            return items, fetch_status

        successful_sources = 0
        error_types: list[str] = []
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(_fetch_one, q): q for q in queries}
            for future in as_completed(futures):
                try:
                    items, fetch_status = future.result()
                except Exception as exc:
                    error_types.append(type(exc).__name__)
                    continue
                if fetch_status.get("status") == "fresh":
                    successful_sources += 1
                else:
                    error_type = str(fetch_status.get("error_type", ""))
                    if error_type:
                        error_types.append(error_type)
                for enriched in items:
                    title = str(enriched.get("title", ""))
                    title_key = title.lower()
                    if title_key in seen:
                        continue
                    seen.add(title_key)
                    rows.append(enriched)
        return self._rss_collection_result(
            rows[:10],
            attempted_sources=len(queries),
            successful_sources=successful_sources,
            error_types=error_types,
        )

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
        rows, _status = self._rss_items_with_status(url, query=query)
        return rows

    def _rss_items_with_status(
        self,
        url: str,
        *,
        query: str,
    ) -> tuple[list[dict[str, object]], dict[str, object]]:
        """Return RSS rows plus transport/parse status; an empty feed can be fresh."""
        request = Request(url, headers={"User-Agent": "AI Market Analyst/1.0"})
        try:
            with urlopen(request, timeout=5) as response:
                payload = response.read()
        except Exception as exc:
            return [], {"status": "unavailable", "error_type": type(exc).__name__}
        try:
            root = ElementTree.fromstring(payload)
        except ElementTree.ParseError as exc:
            return [], {"status": "unavailable", "error_type": type(exc).__name__}
        root_name = str(root.tag).rsplit("}", 1)[-1].lower()
        if root_name != "rss" or root.find(".//channel") is None:
            return [], {"status": "unavailable", "error_type": "InvalidRSSStructure"}
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
        return rows, {"status": "fresh", "error_type": ""}

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
                    return {
                        k: _clean_economic_value(v) if isinstance(v, str) else v
                        for k, v in data.items()
                    }
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

    def lookup_actual_single(self, currency: str, event_name: str, ev_time_str: str, forecast: str = "", previous: str = "") -> str:
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

        actual = self._parse_with_ai(all_text, event_name, forecast, previous)
        cache[cache_key] = actual
        self._write_actual_cache(cache)
        return actual

    def _parse_with_ai(self, text: str, event_name: str, forecast: str, previous: str) -> str:
        try:
            settings = SettingsService().load()
            active = settings.ai.active_provider()
            if not active or not active.api_key:
                return self._parse_fallback_regex(text)

            config = AIProviderConfig(provider=active.provider, model=active.model, api_key=active.api_key)
            ai = AIService(config)

            prompt = (
                "Extract actual economic data value from search results.\n"
                f"Event: {event_name}\n"
                f"Forecast: {forecast} | Previous: {previous}\n\n"
                "Rules:\n"
                "- Return ONLY the number with unit: e.g. '0.1%', '7.6M', '122K', '-2.5B', '50.2'\n"
                "- If this is a speech/meeting/holiday with no data → return 'NONE'\n"
                "- Distinguish ACTUAL from forecast/previous/estimate\n"
                "- If actual not found → return 'NONE'\n"
                "- WRONG formats to REJECT: dates like '2026', 'July', years with letters like '2026M',\n"
                "  '2026B', text like 'higher than expected' or 'unchanged'\n\n"
                f"Search results:\n{text[:3000]}"
            )
            result = ai.analyze(prompt, max_tokens=100).strip()
            if not result or result.upper() == "NONE":
                return ""
            if len(result) > 20:
                return self._parse_fallback_regex(text)
            cleaned = _clean_economic_value(result)
            if cleaned == "—":
                return ""
            return cleaned
        except Exception:
            return ""

    @staticmethod
    def _parse_fallback_regex(text: str) -> str:
        clean = re.sub(r"<[^>]+>", "", text)
        m = re.search(r'(\d+\.?\d*)\s*(%|[MBK])', clean)
        if not m:
            return ""
        num = m.group(1)
        unit = m.group(2)
        try:
            f = float(num)
        except (ValueError, TypeError):
            return ""
        if unit == "%" and not (-100.0 <= f <= 100.0):
            return ""
        return num + unit

    def lookup_actuals_batch(self, events: list[dict[str, object]]) -> None:
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        cache = self._read_actual_cache()

        missing: list[dict[str, object]] = []
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
                cached_val = _clean_economic_value(cache[cache_key])
                if cached_val and cached_val != "—":
                    ev["actual"] = cached_val
                    continue
            if now - ev_time < timedelta(minutes=30):
                continue
            missing.append({"ev": ev, "cache_key": cache_key})

        if not missing:
            return

        # Fetch HTML from ForexFactory (this week + last week)
        from services.forex_factory_client import ForexFactoryClient
        ff_client = ForexFactoryClient()
        html_rows: list[dict[str, object]] = []
        original_url = ff_client.FOREX_FACTORY_HTML_URL
        for week_url in (original_url, "https://www.forexfactory.com/calendar?week=last"):
            try:
                ff_client.FOREX_FACTORY_HTML_URL = week_url
                html_rows.extend(ff_client._fetch_html_events())
            except Exception:
                continue
        ff_client.FOREX_FACTORY_HTML_URL = original_url

        if not html_rows:
            return

        html_lookup: dict[tuple[str, str], str] = {}
        for r in html_rows:
            curr = str(r.get("currency", "")).strip()
            evt = str(r.get("event", "")).strip().lower()
            act = str(r.get("actual", "")).strip()
            if curr and evt and act:
                key = (curr, evt)
                if key not in html_lookup:
                    html_lookup[key] = act

        cache_updated = False
        for item in missing:
            ev = item["ev"]
            cache_key = item["cache_key"]
            curr = str(ev.get("currency", "")).strip()
            title = str(ev.get("title", "")).strip().lower()
            matched = html_lookup.get((curr, title), "")
            if matched:
                cleaned = _clean_economic_value(matched)
                if cleaned and cleaned != "—":
                    ev["actual"] = cleaned
                    cache[cache_key] = cleaned
                    cache_updated = True

        if cache_updated:
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
