"""Synthetic tests for the SMC demote replay labeler (task SD-C2).

No MT5 and no ``derive_live_analysis``: ``label_side`` and the JSONL reader are
pure helpers, exercised with hand-built candles and plans.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from core.market_models import Candle
from scripts.smc_demote_replay import RowsFileError, label_side, read_jsonl

CUTOFF = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)


def _c(minutes: int, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        time=CUTOFF + timedelta(minutes=minutes),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1.0,
    )


def _h1(index: int, close: float) -> Candle:
    return Candle(
        time=CUTOFF + timedelta(hours=index),
        open=close,
        high=close + 0.001,
        low=close - 0.001,
        close=close,
        volume=1.0,
    )


def _plan(entry: float, stop_loss: float, take_profit: float) -> SimpleNamespace:
    return SimpleNamespace(entry=entry, stop_loss=stop_loss, take_profit=take_profit)


def test_tail_before_cutoff_raises() -> None:
    tail = {"H1": [], "M15": [_c(-15, 1.0, 1.0, 1.0, 1.0)]}
    with pytest.raises(ValueError):
        label_side("buy", None, 1.0, 0.01, CUTOFF, tail)


def test_buy_sl_and_tp_same_bar_is_sl_first() -> None:
    plan = _plan(1.10, 1.09, 1.12)
    tail = {
        "H1": [],
        "M15": [_c(0, 1.10, 1.13, 1.08, 1.11)],
    }
    labels = label_side("buy", plan, 1.10, 0.01, CUTOFF, tail)
    assert labels["tp_sl"] == "sl_first"
    assert labels["fill_bar"] == 0
    assert labels["resolve_bar"] == 0


def test_buy_tp_on_fill_bar_is_ignored_so_unresolved() -> None:
    plan = _plan(1.10, 1.09, 1.12)
    tail = {
        "H1": [],
        "M15": [
            _c(0, 1.10, 1.13, 1.095, 1.11),
            _c(15, 1.11, 1.115, 1.095, 1.11),
        ],
    }
    labels = label_side("buy", plan, 1.10, 0.01, CUTOFF, tail)
    assert labels["tp_sl"] == "unresolved"
    assert labels["fill_bar"] == 0
    assert labels["resolve_bar"] is None


def test_sell_not_filled_has_no_mfe() -> None:
    plan = _plan(1.10, 1.12, 1.08)
    tail = {
        "H1": [],
        "M15": [_c(0, 1.09, 1.095, 1.085, 1.09)],
    }
    labels = label_side("sell", plan, 1.10, 0.01, CUTOFF, tail)
    assert labels["tp_sl"] == "not_filled"
    assert labels["fill_bar"] is None
    assert labels["mfe_r"] is None
    assert labels["mae_r"] is None


def test_sell_fill_then_tp_first_with_mfe_mae() -> None:
    plan = _plan(1.10, 1.12, 1.08)
    tail = {
        "H1": [],
        "M15": [
            _c(0, 1.10, 1.105, 1.095, 1.10),
            _c(15, 1.09, 1.10, 1.075, 1.08),
        ],
    }
    labels = label_side("sell", plan, 1.10, 0.02, CUTOFF, tail)
    assert labels["tp_sl"] == "tp_first"
    assert labels["fill_bar"] == 0
    assert labels["resolve_bar"] == 1
    assert labels["mfe_r"] == pytest.approx(1.25)
    assert labels["mae_r"] == pytest.approx(0.25)


def test_forward_atr_uses_defined_h1_indices_and_side_sign() -> None:
    closes = [1.0 + 0.01 * index for index in range(24)]
    tail = {"H1": [_h1(index, close) for index, close in enumerate(closes)], "M15": []}
    ref_close = 1.0
    atr_h1 = 0.5

    buy = label_side("buy", None, ref_close, atr_h1, CUTOFF, tail)
    assert buy["fwd_8h_atr"] == pytest.approx((closes[7] - ref_close) / atr_h1)
    assert buy["fwd_24h_atr"] == pytest.approx((closes[23] - ref_close) / atr_h1)

    sell = label_side("sell", None, ref_close, atr_h1, CUTOFF, tail)
    assert sell["fwd_8h_atr"] == pytest.approx(-(closes[7] - ref_close) / atr_h1)
    assert sell["fwd_24h_atr"] == pytest.approx(-(closes[23] - ref_close) / atr_h1)


def test_buy_invalid_geometry_is_plan_invalid() -> None:
    plan = _plan(1.10, 1.11, 1.12)
    tail = {"H1": [], "M15": [_c(0, 1.10, 1.13, 1.05, 1.11)]}
    labels = label_side("buy", plan, 1.10, 0.01, CUTOFF, tail)
    assert labels["tp_sl"] == "plan_invalid"
    assert labels["mfe_r"] is None


def test_read_jsonl_drops_corrupt_tail_and_rejects_middle(tmp_path) -> None:
    trailing = tmp_path / "trailing.jsonl"
    trailing.write_text('{"a": 1}\n{"a": 2}\n{"a": 3', encoding="utf-8")
    rows, corrupt = read_jsonl(trailing)
    assert [row["a"] for row in rows] == [1, 2]
    assert corrupt is True

    middle = tmp_path / "middle.jsonl"
    middle.write_text('{"a": 1}\nnot json\n{"a": 3}\n', encoding="utf-8")
    with pytest.raises(RowsFileError):
        read_jsonl(middle)
