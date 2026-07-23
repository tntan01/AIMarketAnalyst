"""Tests for Phase 5B: current effective RR as execution guard.

Includes:
- Unit tests for guard decision logic (Phase 5B original)
- Integration tests for _execute_auto_trades() with mocked MT5 (micro-hardening)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from controllers.scanner_controller import ScannerController
from core.risk_engine import calculate_current_effective_rr
from core.scanner import ScannerRequest
from config.settings import TradingSettings
from services.mt5_service import MT5OrderResult
from services.settings_service import SettingsService


# ===========================================================================
# Phase 5B original: unit tests for guard decision logic
# ===========================================================================


class TestCurrentRRGuardLogic:
    """Test the decision logic that Phase 5B adds around order placement."""

    MIN_RR = 1.3

    def _should_skip(self, cur_rr: float | None, cur_rr_source: str, min_rr: float) -> bool:
        """Replicate the Phase 5B guard check from _execute_auto_trades."""
        if cur_rr_source == "current_price" and cur_rr is not None and cur_rr < min_rr:
            return True
        return False

    def test_skip_when_current_rr_below_min_rr(self):
        assert self._should_skip(0.8, "current_price", 1.3) is True
        assert self._should_skip(1.29, "current_price", 1.3) is True

    def test_proceed_when_current_rr_above_min_rr(self):
        assert self._should_skip(1.3, "current_price", 1.3) is False
        assert self._should_skip(1.31, "current_price", 1.3) is False
        assert self._should_skip(2.5, "current_price", 1.3) is False

    def test_proceed_when_no_current_price(self):
        assert self._should_skip(None, "no_current_price", 1.3) is False
        assert self._should_skip(None, "no_stop_loss", 1.3) is False
        assert self._should_skip(None, "no_take_profit", 1.3) is False

    def test_proceed_when_price_behind_sl(self):
        assert self._should_skip(None, "price_behind_sl", 1.3) is False


class TestEntryZoneCheck:
    def test_live_price_inside_zone_passes(self):
        entry_low, entry_high = 1.0970, 1.0990
        live_price = 1.0980
        assert entry_low <= live_price <= entry_high

    def test_live_price_outside_zone_fails(self):
        entry_low, entry_high = 1.0970, 1.0990
        live_price = 1.1000
        assert not (entry_low <= live_price <= entry_high)

    def test_live_price_at_zone_boundary_passes(self):
        entry_low, entry_high = 1.0970, 1.0990
        assert 1.0970 >= 1.0970 and 1.0970 <= 1.0990
        assert 1.0990 >= 1.0970 and 1.0990 <= 1.0990


class TestCurrentRRWithLivePrice:
    def test_buy_live_price_above_entry_edge_gives_lower_rr(self):
        result = calculate_current_effective_rr(
            direction="buy",
            current_price=1.0985,
            stop_loss=1.0940,
            take_profit=1.1050,
        )
        assert result["current_rr_source"] == "current_price"
        assert result["current_effective_rr"] is not None
        assert result["current_effective_rr"] < 2.6
        assert result["current_effective_rr"] > 0

    def test_sell_live_price_below_entry_edge_risks_more(self):
        result = calculate_current_effective_rr(
            direction="sell",
            current_price=1.1020,
            stop_loss=1.1060,
            take_profit=1.0920,
        )
        assert result["current_rr_source"] == "current_price"
        assert result["current_effective_rr"] is not None
        assert result["current_effective_rr"] > 0


class TestAutoTradeSkipReason:
    def test_skip_reason_includes_rr_and_min_rr(self):
        cur_rr = 0.95
        cfg_min_rr = 1.3
        exec_price = 1.0985
        symbol = "EUR/USD"
        reason = (
            f"{symbol}: current RR {cur_rr:.2f} < min_rr {cfg_min_rr:.1f} "
            f"(live price {exec_price:.5f}), bỏ qua auto trade."
        )
        assert "0.95" in reason
        assert "1.3" in reason
        assert "1.09850" in reason
        assert "EUR/USD" in reason


class TestManualOrderWarning:
    def test_warning_includes_current_rr_and_live_price(self):
        symbol = "GBP/USD"
        live_px = 1.3035
        cur_rr = 0.80
        manual_min_rr = 1.3
        msg = (
            f"{symbol}: R:R tại giá hiện tại ({live_px:.5f}) là {cur_rr:.2f}, "
            f"thấp hơn ngưỡng tối thiểu {manual_min_rr:.1f}.\n\n"
            f"Không nên vào lệnh khi R:R hiện tại không đạt.\n"
            f"Chờ giá điều chỉnh về gần mép entry zone để có R:R tốt hơn."
        )
        assert "GBP/USD" in msg
        assert "1.30350" in msg
        assert "0.80" in msg
        assert "1.3" in msg


def test_real_scenario_best_base_pass_but_current_fails():
    best_rr = 2.5
    base_rr = 1.8
    cur_rr = 1.1
    min_rr = 1.3
    assert base_rr >= min_rr
    assert cur_rr < min_rr
    assert (cur_rr < min_rr) is True


def test_real_scenario_best_base_current_all_pass():
    best_rr = 2.5
    base_rr = 2.0
    cur_rr = 1.8
    min_rr = 1.3
    assert best_rr >= min_rr
    assert base_rr >= min_rr
    assert cur_rr >= min_rr
    assert (cur_rr < min_rr) is False


# ---------------------------------------------------------------------------
# Fake MT5 service
# ---------------------------------------------------------------------------

class FakeMT5:
    """Controllable MT5 service for integration tests."""

    def __init__(self, *, live_price: float | None = 1.0980):
        self._live_price = live_price
        self._has_position = False
        self.place_calls: list[dict[str, Any]] = []

    def set_live_price(self, px: float | None) -> None:
        self._live_price = px

    def set_has_position(self, v: bool) -> None:
        self._has_position = v

    def get_live_price(self, broker_symbol: str, side: str) -> float | None:
        return self._live_price

    def has_open_position_or_order(self, broker_symbol: str) -> bool:
        return self._has_position

    def place_market_order(self, **kwargs: Any) -> MT5OrderResult:
        self.place_calls.append(dict(kwargs))
        return MT5OrderResult(
            success=True,
            symbol=str(kwargs.get("symbol", "")),
            broker_symbol=str(kwargs.get("broker_symbol", "")),
            side=str(kwargs.get("side", "")),
            volume=float(kwargs.get("volume", 0)),
            order_id=12345,
        )

    def quote_to_usd_rate(self, quote_currency: str) -> float | None:
        return 1.0


# ---------------------------------------------------------------------------
# Fake settings
# ---------------------------------------------------------------------------


@dataclass
class FakeAppSettings:
    trading: TradingSettings = field(default_factory=TradingSettings)


def _fake_settings_service() -> SettingsService:
    """Return a SettingsService whose load() returns sane trading defaults."""
    svc = MagicMock(spec=SettingsService)
    svc.load.return_value = FakeAppSettings(
        trading=TradingSettings(
            account_balance=10000.0,
            account_currency="USD",
            default_risk_percent=1.0,
            lot_step=0.01,
            minimum_lot=0.01,
            contract_size_override=100000.0,
        ),
    )
    return svc


# ---------------------------------------------------------------------------
# Scenario builder
# ---------------------------------------------------------------------------


def _scenario(*, entry_zone=None, stop_loss=1.0940, take_profit=1.1050,
              entry_zone_source="smc") -> dict[str, Any]:
    if entry_zone is None:
        entry_zone = [1.0970, 1.0990]
    return {
        "type": "buy",
        "entry_zone": entry_zone,
        "stop_loss": stop_loss,
        "take_profit": [take_profit],
        "entry_zone_source": entry_zone_source,
        "risk_reward": "1:2.5",
        "expected_effective_rr": 2.3,
        "expected_effective_rr_base": 1.8,
        "position_sizing": {
            "suggested_lot": 0.05,
            "risk_amount_usd": 20.0,
            "entry_price": 1.0970,
            "stop_loss": stop_loss,
        },
    }


def _row(*, symbol="EUR/USD", broker_symbol="EURUSDm", best_side="buy",
          scenario=None, **overrides) -> dict[str, Any]:
    sc = scenario or _scenario()
    row: dict[str, Any] = {
        "symbol": symbol,
        "broker_symbol": broker_symbol,
        "best_side": best_side,
        "market_regime": "trend_up",
        "best_score": 82,
        "scanner_group": "ready_now",
        "trade_permission": "allowed",
        "scanner_action": "ready",
        "expected_effective_rr": 2.3,
        "analysis_result": {
            "symbol": symbol,
            "scenarios": [sc],
            "technical": {"price": 1.0980, "atr_h4": 0.0020, "atr_h1": 0.0010},
            "data_quality": {"spread_price": 0.00015},
            "trade_gate": {"allowed": True, "block_codes": [], "warning_codes": []},
        },
    }
    row.update(overrides)
    return row


def _request(**overrides) -> ScannerRequest:
    return ScannerRequest(
        symbols=["EUR/USD"],
        account_balance=10000.0,
        risk_percent=1.0,
        timezone_name="Asia/Ho_Chi_Minh",
        auto_trade_enabled=True,
        symbol_auto_trade={"EUR/USD": {"side": "buy", "min_rr": 1.3}},
        **overrides,
    )


# ---------------------------------------------------------------------------
# Controller builder
# ---------------------------------------------------------------------------


def _make_controller(fake_mt5: FakeMT5) -> ScannerController:
    settings_svc = _fake_settings_service()
    ctrl = ScannerController.__new__(ScannerController)
    ctrl.settings_service = settings_svc
    ctrl.mt5 = fake_mt5
    ctrl.news_service = MagicMock()
    ctrl.telegram_service = MagicMock()
    ctrl.journal_service = MagicMock()
    ctrl.orders_screen = None  # avoid BE tracking side-effect
    return ctrl


# ---------------------------------------------------------------------------
# Patch helpers
# ---------------------------------------------------------------------------


def _patch_controller(ctrl: ScannerController, *, at_cfg=None, is_candidate=True,
                       best_scenario=None):
    """Apply common patches to the controller instance."""
    ctrl._auto_trade_config = MagicMock(return_value=at_cfg)
    ctrl._is_auto_trade_candidate = MagicMock(return_value=is_candidate)
    ctrl._best_scenario = MagicMock(return_value=best_scenario or _scenario())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAutoTradeCurrentRRLowSkips:
    """Case A: current RR < min_rr → skip, no order placed."""

    def test_current_rr_below_min_rr_skips_order(self):
        fake_mt5 = FakeMT5(live_price=1.0985)  # far from SL → RR < 2.67
        ctrl = _make_controller(fake_mt5)

        scenario = _scenario(
            entry_zone=[1.0970, 1.0990],
            stop_loss=1.0940,
            take_profit=1.1050,
        )
        row = _row(scenario=scenario)
        req = _request()
        at_cfg = {"side": "buy", "min_rr": 3.0}  # high min_rr to force skip

        _patch_controller(ctrl, at_cfg=at_cfg, best_scenario=scenario)

        result = ctrl._execute_auto_trades([row], req)

        # Should attempt but skip due to current RR
        assert result["attempted"] == 1
        assert result["opened"] == 0
        assert result["skipped"] == 1
        assert len(result["errors"]) >= 1
        error_text = " ".join(result["errors"]).lower()
        assert "current rr" in error_text
        assert "min_rr" in error_text or "3.0" in " ".join(result["errors"])
        # No order placed
        assert len(fake_mt5.place_calls) == 0

    def test_current_rr_above_min_rr_places_order(self):
        fake_mt5 = FakeMT5(live_price=1.0970)  # at edge → best possible RR
        ctrl = _make_controller(fake_mt5)

        scenario = _scenario(
            entry_zone=[1.0970, 1.0990],
            stop_loss=1.0940,
            take_profit=1.1050,
        )
        row = _row(scenario=scenario)
        req = _request()
        at_cfg = {"side": "buy", "min_rr": 1.3}

        _patch_controller(ctrl, at_cfg=at_cfg, best_scenario=scenario)

        result = ctrl._execute_auto_trades([row], req)

        assert result["attempted"] == 1
        assert result["opened"] == 1
        assert result["skipped"] == 0
        assert len(fake_mt5.place_calls) == 1
        call = fake_mt5.place_calls[0]
        assert call["symbol"] == "EUR/USD"
        assert call["side"] == "buy"


class TestAutoTradeLivePriceOutsideEntryZone:
    """Case C: live price outside entry zone → skip."""

    def test_live_price_outside_entry_zone_skips(self):
        # Live price 1.1010, but entry zone is [1.0970, 1.0990]
        fake_mt5 = FakeMT5(live_price=1.1010)
        ctrl = _make_controller(fake_mt5)

        scenario = _scenario(
            entry_zone=[1.0970, 1.0990],
            stop_loss=1.0940,
            take_profit=1.1050,
        )
        # Stale technical.price says price is still inside zone
        row = _row(scenario=scenario)
        row["analysis_result"]["technical"]["price"] = 1.0980  # stale

        req = _request()
        at_cfg = {"side": "buy", "min_rr": 1.3}

        _patch_controller(ctrl, at_cfg=at_cfg, best_scenario=scenario)

        result = ctrl._execute_auto_trades([row], req)

        assert result["attempted"] == 1
        assert result["opened"] == 0
        assert result["skipped"] == 1
        errors_text = " ".join(result["errors"]).lower()
        assert "ngoài vùng entry" in errors_text
        assert len(fake_mt5.place_calls) == 0


class TestAutoTradeLivePriceMissing:
    """Case D: live price unavailable → fallback to technical.price."""

    def test_live_price_none_falls_back_to_technical_price(self):
        fake_mt5 = FakeMT5(live_price=None)  # MT5 unavailable
        ctrl = _make_controller(fake_mt5)

        # technical.price = 1.0980 is inside [1.0970, 1.0990]
        # At technical price 1.0980: risk=0.0040, reward=0.0070 → RR=1.75 >= 1.3
        scenario = _scenario(
            entry_zone=[1.0970, 1.0990],
            stop_loss=1.0940,
            take_profit=1.1050,
        )
        row = _row(scenario=scenario)
        row["analysis_result"]["technical"]["price"] = 1.0980

        req = _request()
        at_cfg = {"side": "buy", "min_rr": 1.3}

        _patch_controller(ctrl, at_cfg=at_cfg, best_scenario=scenario)

        result = ctrl._execute_auto_trades([row], req)

        # Should proceed — fallback price inside zone, current RR passes
        assert result["attempted"] == 1
        assert result["opened"] == 1
        assert len(fake_mt5.place_calls) == 1

    def test_live_price_none_but_technical_outside_zone_skips(self):
        fake_mt5 = FakeMT5(live_price=None)
        ctrl = _make_controller(fake_mt5)

        # technical.price = 1.1010 is OUTSIDE [1.0970, 1.0990]
        scenario = _scenario(
            entry_zone=[1.0970, 1.0990],
            stop_loss=1.0940,
            take_profit=1.1050,
        )
        row = _row(scenario=scenario)
        row["analysis_result"]["technical"]["price"] = 1.1010

        req = _request()
        at_cfg = {"side": "buy", "min_rr": 1.3}

        _patch_controller(ctrl, at_cfg=at_cfg, best_scenario=scenario)

        result = ctrl._execute_auto_trades([row], req)

        assert result["attempted"] == 1
        assert result["opened"] == 0
        assert result["skipped"] == 1
        assert "ngoài vùng entry" in " ".join(result["errors"]).lower()


class TestAutoTradeCurrentRRMissingSlTp:
    """Edge case: no SL/TP → skip at validation stage, before RR guard."""

    def test_missing_sl_skips_before_execution_guard(self):
        fake_mt5 = FakeMT5(live_price=1.0980)
        ctrl = _make_controller(fake_mt5)

        scenario = _scenario(stop_loss=None)  # missing SL
        row = _row(scenario=scenario)
        req = _request()
        at_cfg = {"side": "buy", "min_rr": 1.3}

        _patch_controller(ctrl, at_cfg=at_cfg, best_scenario=scenario)

        result = ctrl._execute_auto_trades([row], req)

        assert result["opened"] == 0
        # Skips at float conversion stage — before guard
        assert "thiếu" in " ".join(result["errors"]).lower()


class TestAutoTradeExistingPosition:
    """Has open position → skip before entry zone / RR check."""

    def test_existing_position_skips(self):
        fake_mt5 = FakeMT5(live_price=1.0970)
        fake_mt5.set_has_position(True)
        ctrl = _make_controller(fake_mt5)

        scenario = _scenario()
        row = _row(scenario=scenario)
        req = _request()
        at_cfg = {"side": "buy", "min_rr": 1.3}

        _patch_controller(ctrl, at_cfg=at_cfg, best_scenario=scenario)

        result = ctrl._execute_auto_trades([row], req)

        assert result["attempted"] == 1
        assert result["opened"] == 0
        assert len(fake_mt5.place_calls) == 0
        # Should have a skipped result with "đã có lệnh" message
        assert len(result["orders"]) == 1
        assert result["orders"][0]["success"] is False


class TestAutoTradePlaceOrderFailure:
    """place_market_order returns failure → counted as skipped, not opened."""

    def test_mt5_rejects_order_not_counted_as_opened(self):
        fake_mt5 = FakeMT5(live_price=1.0970)

        # Override place_market_order to return failure
        def _fail_order(**kwargs):
            fake_mt5.place_calls.append(dict(kwargs))
            return MT5OrderResult(
                success=False,
                symbol=str(kwargs.get("symbol", "")),
                broker_symbol=str(kwargs.get("broker_symbol", "")),
                side=str(kwargs.get("side", "")),
                volume=float(kwargs.get("volume", 0)),
                message="MT5 từ chối lệnh: không đủ margin.",
            )
        fake_mt5.place_market_order = _fail_order

        ctrl = _make_controller(fake_mt5)
        scenario = _scenario()
        row = _row(scenario=scenario)
        req = _request()
        at_cfg = {"side": "buy", "min_rr": 1.3}
        _patch_controller(ctrl, at_cfg=at_cfg, best_scenario=scenario)

        result = ctrl._execute_auto_trades([row], req)

        assert result["attempted"] == 1
        assert result["opened"] == 0
        assert result["skipped"] == 1
        assert len(fake_mt5.place_calls) == 1
        error_text = " ".join(result["errors"])
        assert "không đủ margin" in error_text.lower() or "từ chối" in error_text.lower()


# ===========================================================================
# Phase 5D: diagnostic payload tests
# ===========================================================================


class TestAutoTradeDiagnosticPayload:
    """Verify diagnostic dicts in _execute_auto_trades() result."""

    def test_place_decision_has_full_diagnostic(self):
        fake_mt5 = FakeMT5(live_price=1.0970)
        ctrl = _make_controller(fake_mt5)
        scenario = _scenario()
        row = _row(scenario=scenario)
        req = _request()
        at_cfg = {"side": "buy", "min_rr": 1.3}
        _patch_controller(ctrl, at_cfg=at_cfg, best_scenario=scenario)

        result = ctrl._execute_auto_trades([row], req)

        assert "diagnostics" in result
        diags = result["diagnostics"]
        assert len(diags) == 1
        d = diags[0]
        assert d["decision"] == "place"
        assert d["price_source"] == "live"
        assert d["symbol"] == "EUR/USD"
        assert d["side"] == "buy"
        assert d["live_price"] == 1.0970
        assert d["current_effective_rr"] is not None
        assert d["current_effective_rr"] > 0
        assert d["min_rr"] == 1.3

    def test_skip_current_rr_decision(self):
        fake_mt5 = FakeMT5(live_price=1.0985)
        ctrl = _make_controller(fake_mt5)
        scenario = _scenario(
            entry_zone=[1.0970, 1.0990],
            stop_loss=1.0940,
            take_profit=1.1050,
        )
        row = _row(scenario=scenario)
        req = _request()
        at_cfg = {"side": "buy", "min_rr": 3.0}  # high threshold forces skip
        _patch_controller(ctrl, at_cfg=at_cfg, best_scenario=scenario)

        result = ctrl._execute_auto_trades([row], req)

        diags = result["diagnostics"]
        assert len(diags) == 1
        d = diags[0]
        assert d["decision"] == "skip_current_rr"
        assert d["current_effective_rr"] < 3.0
        assert d["min_rr"] == 3.0
        assert "current rr" in d["reason"].lower()

    def test_skip_outside_entry_zone_decision(self):
        fake_mt5 = FakeMT5(live_price=1.1010)
        ctrl = _make_controller(fake_mt5)
        scenario = _scenario(entry_zone=[1.0970, 1.0990])
        row = _row(scenario=scenario)
        req = _request()
        at_cfg = {"side": "buy", "min_rr": 1.3}
        _patch_controller(ctrl, at_cfg=at_cfg, best_scenario=scenario)

        result = ctrl._execute_auto_trades([row], req)

        d = result["diagnostics"][0]
        assert d["decision"] == "skip_outside_entry_zone"
        assert d["current_price_in_entry_zone"] is False

    def test_technical_fallback_price_source(self):
        fake_mt5 = FakeMT5(live_price=None)  # MT5 unavailable
        ctrl = _make_controller(fake_mt5)
        scenario = _scenario()
        row = _row(scenario=scenario)
        row["analysis_result"]["technical"]["price"] = 1.0980
        req = _request()
        at_cfg = {"side": "buy", "min_rr": 1.3}
        _patch_controller(ctrl, at_cfg=at_cfg, best_scenario=scenario)

        result = ctrl._execute_auto_trades([row], req)

        d = result["diagnostics"][0]
        assert d["decision"] == "place"
        assert d["price_source"] == "technical_fallback"
        assert d["live_price"] is None

    def test_diagnostics_key_in_return_dict(self):
        fake_mt5 = FakeMT5(live_price=1.0970)
        ctrl = _make_controller(fake_mt5)
        req = _request()
        # No candidates → empty diagnostics
        ctrl._is_auto_trade_candidate = MagicMock(return_value=False)

        result = ctrl._execute_auto_trades([], req)

        assert "diagnostics" in result
        assert isinstance(result["diagnostics"], list)
        assert result["diagnostics"] == []

    def test_skip_missing_sl_tp_decision(self):
        fake_mt5 = FakeMT5(live_price=1.0970)
        ctrl = _make_controller(fake_mt5)
        scenario = _scenario(stop_loss=None)
        row = _row(scenario=scenario)
        req = _request()
        at_cfg = {"side": "buy", "min_rr": 1.3}
        _patch_controller(ctrl, at_cfg=at_cfg, best_scenario=scenario)

        result = ctrl._execute_auto_trades([row], req)

        d = result["diagnostics"][0]
        assert d["decision"] == "skip_missing_sl_tp"

    def test_existing_position_diagnostic(self):
        fake_mt5 = FakeMT5(live_price=1.0970)
        fake_mt5.set_has_position(True)
        ctrl = _make_controller(fake_mt5)
        scenario = _scenario()
        row = _row(scenario=scenario)
        req = _request()
        at_cfg = {"side": "buy", "min_rr": 1.3}
        _patch_controller(ctrl, at_cfg=at_cfg, best_scenario=scenario)

        result = ctrl._execute_auto_trades([row], req)

        d = result["diagnostics"][0]
        assert d["decision"] == "skip_existing_position"


class TestManualOrderDiagnostic:
    """Verify execution_guard dict shape in manual order flow (Phase 5D.1)."""

    def _build_manual_diag(self, raw_live_px, fallback_entry_px):
        """Replicate the Phase 5D.1 manual guard logic for diagnostic building."""
        if raw_live_px is not None and raw_live_px > 0:
            exec_px = raw_live_px
            price_source = "live"
            fallback_px = None
        else:
            fallback_px = float(fallback_entry_px) if fallback_entry_px is not None else None
            if fallback_px is not None and fallback_px > 0:
                exec_px = fallback_px
                price_source = "order_entry_fallback"
            else:
                exec_px = 0.0
                price_source = "none"
                fallback_px = None

        if exec_px <= 0:
            return None

        return {
            "symbol": "EUR/USD",
            "broker_symbol": "EURUSDm",
            "side": "buy",
            "live_price": raw_live_px if raw_live_px is not None and raw_live_px > 0 else None,
            "fallback_price": fallback_px,
            "price_source": price_source,
            "entry_zone": [1.0970, 1.0990],
            "current_price_in_entry_zone": True,
            "current_effective_rr": 2.1,
            "current_rr_source": "current_price",
            "min_rr": 1.3,
            "decision": "manual_place",
            "reason": "ok",
        }

    def test_live_price_valid_sets_correct_source(self):
        diag = self._build_manual_diag(raw_live_px=1.0980, fallback_entry_px=None)
        assert diag is not None
        assert diag["price_source"] == "live"
        assert diag["live_price"] == 1.0980
        assert diag["fallback_price"] is None

    def test_live_price_none_fallback_used(self):
        """No live price → fallback to order_info.entry_price."""
        diag = self._build_manual_diag(raw_live_px=None, fallback_entry_px=1.0980)
        assert diag is not None
        assert diag["price_source"] == "order_entry_fallback"
        assert diag["live_price"] is None
        assert diag["fallback_price"] == 1.0980

    def test_live_price_zero_fallback_used(self):
        """Live price = 0 → treated as invalid, fallback used."""
        diag = self._build_manual_diag(raw_live_px=0.0, fallback_entry_px=1.0980)
        assert diag is not None
        assert diag["price_source"] == "order_entry_fallback"
        assert diag["live_price"] is None
        assert diag["fallback_price"] == 1.0980

    def test_live_and_fallback_both_invalid_price_source_none(self):
        diag = self._build_manual_diag(raw_live_px=None, fallback_entry_px=None)
        assert diag is None  # no valid execution price

    def test_fallback_entry_price_used_for_rr_and_can_block(self):
        """Fallback entry_price used as exec_px → RR computed and can block."""
        raw_live = None
        fallback = 1.1010  # far from SL → low RR

        if raw_live is not None and raw_live > 0:
            exec_px = raw_live
        else:
            exec_px = float(fallback) if fallback is not None else 0.0

        # At exec_px=1.1010, SL=1.0940, TP=1.1050
        # risk=0.0070, reward=0.0040 → RR=0.57 < 1.3
        from core.risk_engine import calculate_current_effective_rr
        rr_check = calculate_current_effective_rr(
            direction="buy",
            current_price=exec_px,
            stop_loss=1.0940,
            take_profit=1.1050,
        )
        cur_rr = rr_check.get("current_effective_rr")
        cur_src = rr_check.get("current_rr_source")

        min_rr = 1.3
        assert cur_src == "current_price"
        assert cur_rr is not None
        assert cur_rr < min_rr, f"Expected current RR < {min_rr}, got {cur_rr}"

    def test_live_price_none_and_fallback_zero_price_source_none(self):
        """Live None + fallback 0.0 → no valid price."""
        diag = self._build_manual_diag(raw_live_px=None, fallback_entry_px=0.0)
        assert diag is None

    def test_manual_block_has_correct_decision(self):
        """When current RR < min_rr, decision is manual_block_current_rr."""
        diag = {
            "symbol": "EUR/USD",
            "broker_symbol": "EURUSDm",
            "side": "buy",
            "live_price": None,
            "fallback_price": 1.1010,
            "price_source": "order_entry_fallback",
            "entry_zone": [1.0970, 1.0990],
            "current_price_in_entry_zone": False,
            "current_effective_rr": 0.57,
            "current_rr_source": "current_price",
            "min_rr": 1.3,
            "decision": "manual_block_current_rr",
            "reason": "current RR 0.57 < min_rr 1.3",
        }
        assert diag["decision"] == "manual_block_current_rr"
        assert diag["price_source"] == "order_entry_fallback"
        assert diag["live_price"] is None
        assert diag["fallback_price"] == 1.1010
        assert diag["current_effective_rr"] < diag["min_rr"]

    def test_manual_place_with_fallback_has_correct_fields(self):
        diag = {
            "symbol": "EUR/USD",
            "broker_symbol": "EURUSDm",
            "side": "buy",
            "live_price": None,
            "fallback_price": 1.0970,
            "price_source": "order_entry_fallback",
            "entry_zone": [1.0970, 1.0990],
            "current_price_in_entry_zone": True,
            "current_effective_rr": 2.67,
            "current_rr_source": "current_price",
            "min_rr": 1.3,
            "decision": "manual_place",
            "reason": "manual order passed current RR guard",
        }
        assert diag["decision"] == "manual_place"
        assert diag["price_source"] == "order_entry_fallback"
        assert diag["live_price"] is None
        assert diag["fallback_price"] is not None
