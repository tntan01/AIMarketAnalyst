"""Tự động cập nhật lãi suất từ ForexFactory HTML + FRED API (miễn phí).
Fallback về interest_rates.json nếu không có nguồn nào khả dụng.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, UTC
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# Map tiền tệ → series ID trên FRED
FRED_SERIES: dict[str, str] = {
    "USD": "FEDFUNDS",           # Fed Funds Rate
    "EUR": "ECBDFR",             # ECB Deposit Facility Rate
    "GBP": "BOEBR",              # Bank of England Base Rate
    "JPY": "IRSTCI01JPM156N",    # BOJ Policy Rate
    "AUD": "RBATCTR",            # RBA Cash Rate
    "NZD": "RBNZ_OCR",           # RBNZ OCR
    "CAD": "BOCWATCH",           # BOC Rate
    "CHF": "SNPOLICYR",          # SNB Policy Rate
}

# Map tiền tệ → event name patterns trên ForexFactory
_FOREX_RATE_EVENTS: dict[str, list[str]] = {
    "USD": ["federal funds rate", "fed funds rate"],
    "EUR": ["ecb deposit rate", "ecb interest rate", "ecb refinancing rate"],
    "GBP": ["boe official bank rate", "mpc official bank rate", "boe interest rate"],
    "JPY": ["boj policy rate", "boj interest rate"],
    "AUD": ["cash rate"],
    "NZD": ["official cash rate"],
    "CAD": ["overnight rate"],
    "CHF": ["snb policy rate", "snb interest rate"],
}

_CACHE: dict[str, object] | None = None
_CACHE_TIME: datetime | None = None
_CACHE_TTL = timedelta(hours=6)  # cập nhật tối đa 4 lần/ngày
_FALLBACK_PATH = Path(__file__).resolve().parents[1] / "config" / "interest_rates.json"
_FF_LAST_SCAN: datetime | None = None
_FF_SCAN_TTL = timedelta(hours=3)


def get_latest_rates(fred_api_key: str | None = None) -> dict[str, object]:
    """Trả về dict lãi suất. Ưu tiên FRED, sau đó ForexFactory HTML, fallback JSON."""
    global _CACHE, _CACHE_TIME

    now = datetime.now(UTC)
    if _CACHE and _CACHE_TIME and (now - _CACHE_TIME) < _CACHE_TTL:
        return _CACHE

    rates = _load_fallback()

    if fred_api_key:
        try:
            fred_rates = _fetch_from_fred(fred_api_key)
            if fred_rates:
                rates = fred_rates
        except Exception as e:
            logger.warning("FRED fetch failed: %s", e)

    updated = _update_from_forexfactory(rates)
    if updated:
        rates = updated
        _save_fallback(rates)

    _CACHE = rates
    _CACHE_TIME = now
    return _CACHE


def _update_from_forexfactory(current_rates: dict[str, object]) -> dict[str, object] | None:
    """Scan ForexFactory HTML for central bank rate decisions. Returns updated rates or None."""
    global _FF_LAST_SCAN
    now = datetime.now(UTC)
    if _FF_LAST_SCAN and (now - _FF_LAST_SCAN) < _FF_SCAN_TTL:
        return None

    try:
        from urllib.request import Request, urlopen
        from services.forex_factory_client import ForexFactoryClient
        ff = ForexFactoryClient()
        all_rows: list[dict[str, object]] = []
        for week_url in (
            "https://www.forexfactory.com/calendar?week=this",
            "https://www.forexfactory.com/calendar?week=last",
        ):
            try:
                ff.FOREX_FACTORY_HTML_URL = week_url
                all_rows.extend(ff._fetch_html_events())
            except Exception:
                continue
        if not all_rows:
            return None

        _FF_LAST_SCAN = now
        updated = dict(current_rates)
        changed = False

        for r in all_rows:
            currency = str(r.get("currency", "")).strip()
            if currency not in _FOREX_RATE_EVENTS:
                continue
            event_name = str(r.get("event", "")).strip().lower()
            patterns = _FOREX_RATE_EVENTS[currency]
            if not any(p in event_name for p in patterns):
                continue
            actual = str(r.get("actual", "")).strip()
            if not actual:
                continue
            try:
                new_rate = float(actual.replace("%", ""))
            except (ValueError, TypeError):
                continue

            old = updated.get(currency, {})
            old_rate = float(old.get("rate", 0)) if isinstance(old, dict) else 0.0
            if new_rate != old_rate:
                trend = "hike" if new_rate > old_rate + 0.01 else "cut" if new_rate < old_rate - 0.01 else "hold"
                existing = dict(old) if isinstance(old, dict) else {}
                existing.update({
                    "rate": new_rate,
                    "rate_label": actual if "%" in actual else f"{new_rate:.2f}%",
                    "trend": trend,
                    "_source": "ForexFactory",
                    "_updated": str(r.get("time_utc", ""))[:10] or now.strftime("%Y-%m-%d"),
                })
                updated[currency] = existing
                changed = True

        return updated if changed else None

    except Exception:
        _FF_LAST_SCAN = now
        return None


def _save_fallback(rates: dict[str, object]) -> None:
    """Ghi rates vào interest_rates.json."""
    try:
        raw = json.loads(_FALLBACK_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raw = {}
        raw["currencies"] = rates
        raw["_last_updated"] = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        _FALLBACK_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _fetch_from_fred(api_key: str) -> dict[str, object] | None:
    """Gọi FRED API lấy lãi suất mới nhất cho từng tiền tệ."""
    base_url = "https://api.stlouisfed.org/fred/series/observations"
    fallback = _load_fallback()
    result = dict(fallback)  # bắt đầu từ fallback, override từng currency có data

    for currency, series_id in FRED_SERIES.items():
        try:
            resp = requests.get(base_url, params={
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 2,  # lấy 2 điểm để tính trend
            }, timeout=5)
            if resp.status_code != 200:
                continue

            obs = resp.json().get("observations", [])
            valid = [o for o in obs if o.get("value", ".") != "."]
            if not valid:
                continue

            latest_rate = float(valid[0]["value"])
            prev_rate = float(valid[1]["value"]) if len(valid) > 1 else latest_rate

            # Tính trend so với kỳ trước
            if latest_rate > prev_rate + 0.1:
                trend = "hike"
            elif latest_rate < prev_rate - 0.1:
                trend = "cut"
            else:
                trend = "hold"

            # Merge vào result, giữ các field khác từ fallback
            existing = dict(fallback.get(currency, {}))
            existing.update({
                "rate": latest_rate,
                "rate_label": f"{latest_rate:.2f}%",
                "trend": trend,
                "_source": "FRED",
                "_updated": valid[0]["date"],
            })
            result[currency] = existing

        except Exception as e:
            logger.debug("FRED error cho %s/%s: %s", currency, series_id, e)
            continue

    return result


def _load_fallback() -> dict[str, object]:
    try:
        raw = json.loads(_FALLBACK_PATH.read_text(encoding="utf-8"))
        return raw.get("currencies", {})
    except Exception:
        return {}
