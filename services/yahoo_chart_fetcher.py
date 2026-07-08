from __future__ import annotations

from typing import Any

import requests


def fetch_single_yahoo_chart(tag: str, ticker: str, *, timeout: int = 10) -> tuple[str, tuple[float, float]] | None:
    """Fetch the latest close and percent change for a single Yahoo Finance ticker.

    Returns ``(tag, (close, change_pct))`` on success, or ``None`` if data is
    unavailable.  This is the building block used by the parallel fallback in
    ``fetch_market_overview_from_yahoo_chart``.
    """
    headers = {"User-Agent": "Mozilla/5.0"}
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1mo&interval=1d"
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 429:
            import time
            time.sleep(2)
            resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            return None
        json_data = resp.json()
        result: list[dict[str, Any]] = json_data.get("chart", {}).get("result", [])
        if not result:
            return None
        quotes = result[0].get("indicators", {}).get("quote", [])
        if not quotes:
            return None
        closes = [float(c) for c in quotes[0].get("close", []) if c is not None]
        if len(closes) < 2:
            return None
        close = closes[-1]
        prev = closes[-2]
        change_pct = (close - prev) / prev * 100 if prev != 0 else 0.0
        return tag, (close, change_pct)
    except Exception:
        return None
