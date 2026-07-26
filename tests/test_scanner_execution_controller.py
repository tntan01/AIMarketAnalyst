"""Controller integration tests for the shared Phase-3 order gate."""

from __future__ import annotations

import ast
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from controllers.scanner_controller import ScannerController
from core.portfolio_models import PortfolioRiskItem, PortfolioSnapshot
from core.scanner_models import ExecutionMarketSnapshot
from config.settings import ScannerRolloutSettings


def _settings():
    return SimpleNamespace(
        trading=SimpleNamespace(
            account_balance=10000.0,
            account_currency="USD",
            default_risk_percent=1.0,
            lot_step=0.01,
            minimum_lot=0.01,
            contract_size_override=100000.0,
            max_daily_loss_pct=2.0,
            max_weekly_loss_pct=5.0,
            max_consecutive_losses=3,
            max_open_risk_pct=3.0,
            max_symbol_risk_pct=2.0,
            max_currency_exposure_pct=2.0,
            max_correlated_risk_pct=2.0,
            max_concurrent_orders=5,
        ),
        advanced=SimpleNamespace(
            high_impact_news_block_before_minutes=30,
            high_impact_news_block_after_minutes=30,
            block_high_impact_news=True,
        ),
        display=SimpleNamespace(timezone="Asia/Ho_Chi_Minh"),
    )


def _snapshot():
    now = datetime.now(timezone.utc)
    return ExecutionMarketSnapshot(
        broker_symbol="EURUSD",
        captured_at=now,
        connected=True,
        logged_in=True,
        trade_allowed=True,
        symbol_available=True,
        symbol_trade_mode=4,
        bid=1.1000,
        ask=1.1002,
        point=0.0001,
        spread_points=2.0,
        spread_price=0.0002,
        tick_time=now,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
        symbol_state_available=True,
        has_open_position_or_order=False,
        trade_tick_size=0.0001,
        trade_tick_value_loss=10.0,
        contract_size=100000.0,
    )


def _proposal():
    return {
        "scan_id": "scan-test",
        "row_id": "scan-test:EURUSD",
        "symbol": "EUR/USD",
        "broker_symbol": "EURUSD",
        "side": "buy",
        "entry_zone": [1.0990, 1.1015],
        "entry_price": 9.9999,
        "current_price": 9.9999,
        "stop_loss": 1.0950,
        "take_profit": 1.1120,
        "volume": 0.1,
        "required_min_rr": 1.5,
    }


class _SettingsService:
    def load(self):
        return _settings()


class _Journal:
    def list_closed_trades_for_account_guard(self):
        return []


class _MT5:
    def __init__(self):
        self.place_calls = []
        self.portfolio_items = []
        self.portfolio_snapshot_calls = 0

    def execution_snapshot(self, broker_symbol):
        return replace(_snapshot(), broker_symbol=broker_symbol)

    def portfolio_snapshot(self):
        self.portfolio_snapshot_calls += 1
        return PortfolioSnapshot(
            available=True,
            captured_at=datetime.now(timezone.utc),
            account_balance=10000.0,
            account_currency="USD",
            positions=tuple(self.portfolio_items),
        )

    def quote_to_usd_rate(self, currency):
        return 1.0

    def get_open_positions(self):
        return []

    def place_market_order(self, **kwargs):
        self.place_calls.append(kwargs)
        self.portfolio_items.append(
            PortfolioRiskItem(
                source="position",
                ticket=len(self.place_calls),
                symbol=str(kwargs["symbol"]),
                broker_symbol=str(kwargs["broker_symbol"]),
                side=str(kwargs["side"]),
                entry_price=1.1002,
                current_price=1.1002,
                stop_loss=float(kwargs["stop_loss"]),
                volume=float(kwargs["volume"]),
                tick_size=0.0001,
                tick_value_loss=10.0,
                contract_size=100000.0,
            )
        )
        return {
            "success": True,
            "order_id": 123,
            "message": "ok",
            **kwargs,
        }


class _News:
    def __init__(self, available=True, blackout=False):
        self.available = available
        self.blackout = blackout

    def execution_news_status(self, *args, **kwargs):
        return {
            "available": self.available,
            "blackout": self.blackout if self.available else None,
            "reason_codes": [],
        }


def _controller(mt5, news):
    return ScannerController(
        settings_service=_SettingsService(),
        mt5=mt5,
        news_service=news,
        journal_service=_Journal(),
    )


def test_controller_revalidates_then_places_with_live_price_sizing():
    mt5 = _MT5()
    result = _controller(mt5, _News()).execute_order_candidate(_proposal())

    assert result["success"] is True
    assert result["revalidation"]["allowed"] is True
    assert result["revalidation"]["execution_price"] == 1.1002
    assert len(mt5.place_calls) == 1
    assert result["portfolio_guard"]["allowed"] is True
    assert "post_trade_portfolio" in result
    assert mt5.portfolio_snapshot_calls == 2
    assert mt5.place_calls[0]["comment"].startswith("AMA-FWD:")
    assert result["forward_correlation_id"]


def test_manual_order_bypasses_only_missing_release_evidence():
    class _ProductionSettingsService:
        def __init__(self) -> None:
            self.settings = _settings()
            self.settings.scanner_rollout = ScannerRolloutSettings(
                stage="PRODUCTION",
                production_approved=True,
            )

        def load(self):
            return self.settings

    class _NotReadyMetrics:
        def readiness(self, _settings):
            return {"ready": False}

        def canary_readiness(self, _settings):
            return {"ready": False}

    mt5 = _MT5()
    controller = ScannerController(
        settings_service=_ProductionSettingsService(),
        mt5=mt5,
        news_service=_News(),
        journal_service=_Journal(),
    )
    controller.rollout_metrics = _NotReadyMetrics()

    blocked = controller.execute_order_candidate(_proposal())
    result = controller.execute_order_candidate(
        _proposal(),
        manual_release_gate_override=True,
    )

    assert blocked["success"] is False
    assert blocked["rollout"]["reason_codes"] == ["RELEASE_GATE_NOT_READY"]
    assert result["success"] is True
    assert len(mt5.place_calls) == 1


def test_controller_does_not_place_when_realtime_news_is_unavailable():
    mt5 = _MT5()
    result = _controller(
        mt5,
        _News(available=False),
    ).execute_order_candidate(_proposal())

    assert result["success"] is False
    assert "NEWS_STATUS_UNAVAILABLE" in result["revalidation"]["block_codes"]
    assert mt5.place_calls == []


def test_second_order_uses_portfolio_state_after_first_order():
    mt5 = _MT5()
    controller = _controller(mt5, _News())
    settings = controller.settings_service.load()
    settings.trading.max_open_risk_pct = 1.5
    controller.settings_service.load = lambda: settings

    first = controller.execute_order_candidate(_proposal())
    second_proposal = {
        **_proposal(),
        "symbol": "GBP/USD",
        "broker_symbol": "GBPUSD",
    }
    second = controller.execute_order_candidate(second_proposal)

    assert first["success"] is True
    assert second["success"] is False
    assert second["portfolio_guard"]["current_open_risk_pct"] > 0
    assert "PORTFOLIO_RISK_EXCEEDED" in second["portfolio_guard"]["block_codes"]
    assert "PORTFOLIO_RISK_EXCEEDED" in second["message"]
    assert len(mt5.place_calls) == 1


def test_concurrent_order_requests_are_serialized_against_portfolio_state():
    class SlowMT5(_MT5):
        def place_market_order(self, **kwargs):
            time.sleep(0.05)
            return super().place_market_order(**kwargs)

    mt5 = SlowMT5()
    controller = _controller(mt5, _News())
    settings = controller.settings_service.load()
    settings.trading.max_open_risk_pct = 1.5
    controller.settings_service.load = lambda: settings
    eur = _proposal()
    gbp = {
        **_proposal(),
        "symbol": "GBP/USD",
        "broker_symbol": "GBPUSD",
    }

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(controller.execute_order_candidate, (eur, gbp)))

    assert sum(bool(result["success"]) for result in results) == 1
    assert len(mt5.place_calls) == 1
    blocked = next(result for result in results if not result["success"])
    assert "PORTFOLIO_RISK_EXCEEDED" in blocked["portfolio_guard"]["block_codes"]


def test_scanner_has_no_order_path_bypassing_shared_revalidation():
    """Architecture guard: scanner order_send has exactly one owner."""

    project_root = Path(__file__).resolve().parent.parent
    controller_path = project_root / "controllers" / "scanner_controller.py"
    screen_path = project_root / "ui" / "screens" / "scanner_screen.py"

    controller_tree = ast.parse(controller_path.read_text(encoding="utf-8"))
    screen_tree = ast.parse(screen_path.read_text(encoding="utf-8"))

    controller_calls = _attribute_call_owners(
        controller_tree,
        "place_market_order",
    )
    screen_calls = _attribute_call_owners(screen_tree, "place_market_order")
    shared_gate_calls = _attribute_call_owners(
        controller_tree,
        "execute_order_candidate",
    )
    manual_gate_calls = _attribute_call_owners(
        screen_tree,
        "execute_order_candidate",
    )

    assert controller_calls == ["execute_order_candidate"]
    assert screen_calls == []
    assert "_execute_auto_trades" in shared_gate_calls
    assert "execute_manual_order" in manual_gate_calls


def test_revalidation_occurs_before_the_only_mt5_order_call():
    project_root = Path(__file__).resolve().parent.parent
    source = (
        project_root / "controllers" / "scanner_controller.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "execute_order_candidate"
    )
    revalidation_line = next(
        node.lineno
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "revalidate_execution"
    )
    order_line = next(
        node.lineno
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "place_market_order"
    )

    assert revalidation_line < order_line
    assert "if not validation.allowed:" in source


def _attribute_call_owners(tree: ast.AST, attribute: str) -> list[str]:
    owners: list[str] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.functions: list[str] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.functions.append(node.name)
            self.generic_visit(node)
            self.functions.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self.functions.append(node.name)
            self.generic_visit(node)
            self.functions.pop()

        def visit_Call(self, node: ast.Call) -> None:
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == attribute
            ):
                owners.append(self.functions[-1] if self.functions else "<module>")
            self.generic_visit(node)

    Visitor().visit(tree)
    return owners
