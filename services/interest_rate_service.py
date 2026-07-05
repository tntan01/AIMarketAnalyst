"""Tự động cập nhật lãi suất từ FRED API (miễn phí).
Fallback về interest_rates.json nếu FRED không khả dụng.
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

_CACHE: dict[str, object] | None = None
_CACHE_TIME: datetime | None = None
_CACHE_TTL = timedelta(hours=6)  # cập nhật tối đa 4 lần/ngày
_FALLBACK_PATH = Path(__file__).resolve().parents[1] / "config" / "interest_rates.json"


def get_latest_rates(fred_api_key: str | None = None) -> dict[str, object]:
    """Trả về dict lãi suất. Ưu tiên FRED nếu có API key, fallback về JSON."""
    global _CACHE, _CACHE_TIME

    now = datetime.now(UTC)
    if _CACHE and _CACHE_TIME and (now - _CACHE_TIME) < _CACHE_TTL:
        return _CACHE

    if fred_api_key:
        try:
            rates = _fetch_from_fred(fred_api_key)
            if rates:
                _CACHE = rates
                _CACHE_TIME = now
                return _CACHE
        except Exception as e:
            logger.warning("FRED fetch failed: %s, dùng fallback JSON", e)

    return _load_fallback()


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
