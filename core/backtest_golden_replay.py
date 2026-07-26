"""Small broker-free golden replay used on Windows and CI."""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
from typing import Any

from core.backtest_execution import (
    BACKTEST_EXECUTION_POLICY_VERSION,
    SAME_BAR_STOP_FIRST,
    build_execution_events,
    find_confirmation_close_fill,
    resolve_post_fill_exit,
)
from core.market_models import Candle


GOLDEN_REPLAY_VERSION = "backtest-phase7-golden-replay-v1"
GOLDEN_RESULT_FINGERPRINT = (
    "1990c198354354545871323fa970fc8c4b0a9ff9b6c05f54aa1dfa3adb5a47b8"
)


def run_golden_replay(path: str | Path) -> dict[str, Any]:
    fixture_path = Path(path)
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    candles = [_candle(row) for row in fixture["candles"]]
    setup = fixture["setup"]
    signal_time = _moment(setup["signal_time"])
    fill = find_confirmation_close_fill(
        side=setup["side"],
        zone_low=float(setup["zone_low"]),
        zone_high=float(setup["zone_high"]),
        future_candles=candles,
        setup_active_time=signal_time,
        setup_expiry=timedelta(minutes=int(setup["setup_expiry_minutes"])),
        execution_timeframe="M15",
        spread_price=float(setup.get("spread_price", 0.0)),
        slippage_price=float(setup.get("slippage_price", 0.0)),
    )
    if fill is None:
        actual = {"candidate_count": 1, "trade_count": 0, "outcome": "not_filled"}
        events: list[dict[str, Any]] = []
    else:
        exit_resolution = resolve_post_fill_exit(
            side=setup["side"], entry_price=fill.price,
            stop_loss=float(setup["stop_loss"]),
            take_profit=float(setup["take_profit"]),
            future_candles=candles, filled_at=fill.filled_at,
            max_holding=timedelta(minutes=int(setup["max_holding_minutes"])),
            execution_timeframe="M15", same_bar_policy=SAME_BAR_STOP_FIRST,
        )
        risk = abs(fill.price - float(setup["stop_loss"]))
        result_r = (
            abs(float(exit_resolution.price) - fill.price) / risk
            * (1.0 if exit_resolution.outcome == "win" else -1.0)
            if exit_resolution.price is not None and risk > 0 else 0.0
        )
        actual = {
            "candidate_count": 1,
            "trade_count": 1,
            "fill_time": fill.filled_at.isoformat(),
            "fill_price": round(fill.price, 8),
            "outcome": exit_resolution.outcome,
            "exit_price": round(float(exit_resolution.price or 0.0), 8),
            "result_r": round(result_r, 6),
        }
        events = build_execution_events(
            signal_time=signal_time,
            setup_expires_at=signal_time + timedelta(minutes=int(setup["setup_expiry_minutes"])),
            fill=fill,
            exit_resolution=exit_resolution,
        )
    fingerprint = _fingerprint({"actual": actual, "events": events})
    expected = fixture.get("expected", {})
    mismatches = [
        key for key, value in expected.items()
        if actual.get(key) != value
    ]
    if str(fixture.get("expected_result_fingerprint") or "") != fingerprint:
        mismatches.append("result_fingerprint")
    return {
        "version": GOLDEN_REPLAY_VERSION,
        "execution_policy_version": BACKTEST_EXECUTION_POLICY_VERSION,
        "fixture": fixture_path.name,
        "fixture_hash": _fingerprint(fixture),
        "actual": actual,
        "expected": expected,
        "events": events,
        "result_fingerprint": fingerprint,
        "mismatches": mismatches,
        "passed": not mismatches,
    }


def _candle(payload: dict[str, Any]) -> Candle:
    return Candle(
        time=_moment(payload["time"]), open=float(payload["open"]),
        high=float(payload["high"]), low=float(payload["low"]),
        close=float(payload["close"]), volume=float(payload.get("volume", 0.0)),
    )


def _moment(value: object) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _fingerprint(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
