from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_orders_screen_has_no_native_mt5_or_direct_broker_calls() -> None:
    source = (ROOT / "ui" / "screens" / "orders_screen.py").read_text(
        encoding="utf-8"
    )

    assert "import MetaTrader5" not in source
    assert "self.mt5" not in source
    assert ".positions_get(" not in source
    assert ".order_send(" not in source


def test_scanner_worker_never_calls_orders_qwidget() -> None:
    source = (ROOT / "controllers" / "scanner_controller.py").read_text(
        encoding="utf-8"
    )

    assert "orders_screen.auto_enable_tracking" not in source
    assert "manager.register_position(" in source
    assert "result.get(\"position_id\") or result.get(\"ticket\")" not in source


def test_main_window_starts_app_owned_service_not_widget_engine() -> None:
    source = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")

    assert "self.app.order_management_service.start()" in source
    assert "scanner_controller.orders_screen = orders" not in source
