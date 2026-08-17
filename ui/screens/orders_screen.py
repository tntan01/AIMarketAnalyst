from __future__ import annotations

from datetime import datetime, timezone
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QCursor
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QTabBar,
    QToolTip,
)
from services.order_management_models import SnapshotStatus
from services.settings_service import SettingsService
from ui.layout_system import configure_table
from ui.theme.fonts import get_body_font, get_subtitle_font
from ui.theme_manager import current_palette, is_light_theme, set_dynamic_property
from ui.screens.shared import action_button, card, page_header, labeled_value
class OrdersScreen(QWidget):
    def __init__(self, navigate=None, *, app=None) -> None:
        super().__init__()
        self.navigate = navigate
        self.app = app
        self.order_manager = app.order_management_service if app else None
        self.settings_service = app.settings_service if app else SettingsService()
        self._light = self._is_light_theme()
        self._active_tab = "positions"
        self._positions: list[dict] = []
        self._pending_orders: list[dict] = []
        self._positions_snapshot_status = SnapshotStatus.UNAVAILABLE
        self._pending_snapshot_status = SnapshotStatus.UNAVAILABLE
        self._last_broker_refresh: datetime | None = None
        self._snapshot_message = ""
        self._account_currency = ""
        self._pending_ui_operation: dict[str, object] | None = None
        self._trailing_configs: dict[int, dict] = {}  # key = position_id
        self._position_original_sl: dict[int, float] = {}  # position_id -> original SL (captured once, never overwritten)
        self.setObjectName("FormScreen")
        self._build_ui()

        # Restore protection state before the first broker refresh/timer tick.
        self._save_debounce = QTimer(self)
        self._save_debounce.setSingleShot(True)
        self._save_debounce.setInterval(2000)
        self._save_debounce.timeout.connect(self._save_trailing_state)
        if self.order_manager is None:
            self._load_trailing_state()

        if self.order_manager is not None:
            self.order_manager.snapshot_updated.connect(
                self._on_order_management_snapshot
            )
            self.order_manager.state_changed.connect(
                self._on_order_management_state
            )
            self.order_manager.health_changed.connect(
                self._on_order_management_health
            )
            self.order_manager.operation_completed.connect(
                self._on_order_management_operation
            )
            self.order_manager.operation_failed.connect(
                self._on_order_management_failure
            )

        self.refresh_orders()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(5000)
        self._refresh_timer.timeout.connect(self.refresh_orders)
        self._refresh_timer.start()

        self._trail_timer = QTimer(self)
        self._trail_timer.setInterval(1500)
        self._trail_timer.timeout.connect(self._trailing_tick)
        # The legacy in-widget engine is never restored when V2 is disabled.
        # App-owned OrderManagementService schedules the production loop.

    def _is_light_theme(self) -> bool:
        return is_light_theme(self.settings_service)

    def refresh_theme_styles(self) -> None:
        self._light = self._is_light_theme()

    # ------------------------------------------------------------------
    # UI build
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)
        root.addWidget(page_header(
            "Quản lý lệnh",
            "",
            "",
        ))
        root.addWidget(self._build_status_bar())

        content_card = card()
        content_card.layout().setContentsMargins(16, 14, 16, 14)
        content_card.layout().setSpacing(10)
        content_card.layout().addLayout(self._build_tab_bar())
        content_card.layout().addWidget(self._build_order_table(), 1)
        content_card.layout().addLayout(self._build_action_bar())
        root.addWidget(content_card, 1)

    def _build_status_bar(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.balance_card = labeled_value("💰 Số dư", "--")
        self.balance_label = self.balance_card.findChild(QLabel, "MiniStatValue")

        self.position_count_card = labeled_value("📊 Đang mở", "0")
        self.position_count_label = self.position_count_card.findChild(QLabel, "MiniStatValue")

        self.pending_count_card = labeled_value("⏳ Lệnh chờ", "0")
        self.pending_count_label = self.pending_count_card.findChild(QLabel, "MiniStatValue")

        self.pl_card = labeled_value("💵 Lãi/lỗ", "--")
        self.pl_label = self.pl_card.findChild(QLabel, "MiniStatValue")

        self.trail_count_card = labeled_value("🎯 Trail", "0")
        self.trail_count_label = self.trail_count_card.findChild(QLabel, "MiniStatValue")

        self.protection_card = labeled_value("🛡️ Bảo vệ", "STALE")
        self.protection_label = self.protection_card.findChild(QLabel, "MiniStatValue")

        for card_widget in (self.balance_card, self.position_count_card, self.pending_count_card, self.pl_card, self.trail_count_card, self.protection_card):
            card_widget.setMinimumHeight(50)
            card_layout = card_widget.layout()
            if card_layout:
                card_layout.setContentsMargins(10, 4, 10, 4)
                card_layout.setSpacing(2)
            val_lbl = card_widget.findChild(QLabel, "MiniStatValue")
            if val_lbl:
                val_lbl.setProperty("compactStatus", True)
        self.pl_label.setProperty("metricRole", "profit")

        layout.addWidget(self.balance_card)
        layout.addWidget(self.position_count_card)
        layout.addWidget(self.pending_count_card)
        layout.addWidget(self.pl_card)
        layout.addWidget(self.trail_count_card)
        layout.addWidget(self.protection_card)

        return container

    def _build_tab_bar(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(10)

        self.orders_tab_bar = QTabBar()
        self.orders_tab_bar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.orders_tab_keys = ["positions", "pending"]
        self.orders_tab_bar.addTab("Vị thế đang mở")
        self.orders_tab_bar.addTab("Lệnh chờ")
        self.orders_tab_bar.setCurrentIndex(0) # Default to positions
        self.orders_tab_bar.currentChanged.connect(self._on_orders_tab_changed)
        layout.addWidget(self.orders_tab_bar)

        layout.addStretch(1)
        self._update_tab_styles()
        return layout

    def _build_order_table(self) -> QTableWidget:
        table = QTableWidget()
        configure_table(table)
        table.setColumnCount(11)
        table.setHorizontalHeaderLabels([
            "Mã", "Hướng", "KL", "Entry", "Hiện tại", "SL", "TP", "P/L", "R", "Trailing", ""
        ])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(10, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(0, 120)
        table.setColumnWidth(1, 65)
        table.setColumnWidth(2, 65)
        table.setColumnWidth(3, 110)
        table.setColumnWidth(4, 110)
        table.setColumnWidth(5, 110)
        table.setColumnWidth(6, 110)
        table.setColumnWidth(7, 95)
        table.setColumnWidth(8, 65)
        table.setColumnWidth(10, 105)

        self.order_table = table
        table.itemSelectionChanged.connect(self._update_clear_trail_visibility)
        return table

    def _build_action_bar(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(8)

        self.refresh_btn = action_button("🔄 Làm mới", primary=True, color="info")
        self.refresh_btn.clicked.connect(self.refresh_orders)
        layout.addWidget(self.refresh_btn)

        self.trail_btn = action_button("🎯 Trailing Stop", primary=True, color="warning")
        self.trail_btn.setToolTip("Bật/tắt trailing stop cho vị thế đã chọn")
        self.trail_btn.clicked.connect(self._show_trailing_dialog)
        layout.addWidget(self.trail_btn)

        self.clear_trail_btn = action_button("🗑️ Xóa trailing", primary=True, color="danger")
        self.clear_trail_btn.setToolTip("Xóa cấu hình trailing stop của vị thế đã chọn")
        self.clear_trail_btn.clicked.connect(self._clear_trailing)
        self.clear_trail_btn.setVisible(False)
        layout.addWidget(self.clear_trail_btn)

        self.modify_position_btn = action_button(
            "✏️ Sửa SL/TP", primary=True, color="warning"
        )
        self.modify_position_btn.clicked.connect(self._modify_selected_position)
        layout.addWidget(self.modify_position_btn)

        self.partial_close_btn = action_button(
            "◐ Đóng một phần", primary=True, color="warning"
        )
        self.partial_close_btn.clicked.connect(self._partial_close_selected)
        layout.addWidget(self.partial_close_btn)

        self.close_selected_btn = action_button("❌ Đóng lệnh đã chọn", primary=True, color="danger")
        self.close_selected_btn.setToolTip("Đóng vị thế đang chọn trong bảng")
        self.close_selected_btn.clicked.connect(self._close_selected)
        layout.addWidget(self.close_selected_btn)

        self.close_all_btn = action_button("❌ Đóng tất cả", primary=True, color="danger")
        self.close_all_btn.setToolTip("Đóng toàn bộ vị thế đang mở (có xác nhận)")
        self.close_all_btn.clicked.connect(self._close_all)
        layout.addWidget(self.close_all_btn)

        self.modify_pending_btn = action_button(
            "✏️ Sửa lệnh chờ", primary=True, color="warning"
        )
        self.modify_pending_btn.clicked.connect(self._modify_selected_pending)
        self.modify_pending_btn.setVisible(False)
        layout.addWidget(self.modify_pending_btn)

        self.cancel_pending_btn = action_button(
            "🗑️ Hủy lệnh chờ", primary=True, color="danger"
        )
        self.cancel_pending_btn.clicked.connect(self._cancel_selected_pending)
        self.cancel_pending_btn.setVisible(False)
        layout.addWidget(self.cancel_pending_btn)

        self.flatten_btn = action_button(
            "⚠️ Flatten tài khoản", primary=True, color="danger"
        )
        self.flatten_btn.setToolTip(
            "Đóng tất cả positions và hủy tất cả pending orders trong snapshot xác nhận"
        )
        self.flatten_btn.clicked.connect(self._flatten_account)
        layout.addWidget(self.flatten_btn)

        layout.addStretch(1)
        return layout

    # ------------------------------------------------------------------
    # Tab switching
    # ------------------------------------------------------------------
    def _on_orders_tab_changed(self, index: int) -> None:
        if 0 <= index < len(self.orders_tab_keys):
            self._switch_tab(self.orders_tab_keys[index])

    def _switch_tab(self, tab_key: str) -> None:
        self._active_tab = tab_key
        self._update_tab_styles()
        self._render_table()

    def _update_tab_styles(self) -> None:
        if hasattr(self, "orders_tab_bar"):
            try:
                idx = self.orders_tab_keys.index(self._active_tab)
                self.orders_tab_bar.blockSignals(True)
                self.orders_tab_bar.setCurrentIndex(idx)
                self.orders_tab_bar.blockSignals(False)
            except ValueError:
                pass

    def _sync_managed_views(self) -> None:
        """Project service state into the legacy table view without owning it."""

        if self.order_manager is None:
            return
        broker_by_id = {
            int(position.get("position_id", 0)): position
            for position in self._positions
        }
        projected: dict[int, dict] = {}
        for view in self.order_manager.cached_states():
            position = broker_by_id.get(view.position_id, {})
            broker_sl = float(position.get("sl", 0) or 0)
            be_done = view.phase in {
                "be_active",
                "trail_wide",
                "trail_tight",
            }
            projected[view.position_id] = {
                "position_id": view.position_id,
                "symbol": view.broker_symbol,
                "side": view.side,
                "enabled": view.phase not in {
                    "paused",
                    "closed",
                    "unmanaged",
                    "error_non_retryable",
                },
                "phase": (
                    "atr_unavailable"
                    if view.last_error == "atr_unavailable"
                    else view.phase
                ),
                "entry_price": view.entry_price,
                "initial_sl": view.initial_sl,
                "current_sl": broker_sl,
                "extreme_price": view.extreme_price or 0.0,
                "be_done": be_done,
                "trail_mode": (
                    "tight" if view.phase == "trail_tight" else "wide"
                ),
                "atr_h1": view.atr or 0.0,
                "retry_count": view.retry_count,
                "last_error": view.last_error,
                "last_confirmed_at_utc": view.last_confirmed_at_utc,
            }
            self._position_original_sl[view.position_id] = view.initial_sl
        self._trailing_configs = projected

    def _on_order_management_snapshot(self, _payload: object) -> None:
        self.refresh_orders()

    def _on_order_management_state(self, _payload: object) -> None:
        self.refresh_orders()

    def _on_order_management_health(self, health: object) -> None:
        status = getattr(health, "snapshot_status", SnapshotStatus.UNAVAILABLE)
        # Fully live since 2026-08-15: no stage ladder remains. The label now
        # reflects whether protection changes may actually reach the broker
        # (feature flag + account.trade_allowed).
        execution_allowed = bool(getattr(health, "execution_allowed", False))
        account = getattr(health, "account", None)
        if getattr(self, "protection_label", None):
            if status is not SnapshotStatus.AVAILABLE:
                self.protection_label.setText("STALE")
            elif execution_allowed:
                self.protection_label.setText("LIVE")
            else:
                self.protection_label.setText("BLOCKED")
            account_text = ""
            if account is not None:
                account_text = (
                    f"\nTài khoản: {account.login} @ {account.server} "
                    f"({account.trade_mode.value})"
                )
            self.protection_card.setToolTip(
                str(getattr(health, "message", "") or "") + account_text
            )

    def _on_order_management_failure(self, payload: object) -> None:
        if getattr(self, "protection_label", None):
            self.protection_label.setText("ERROR")
            self.protection_card.setToolTip(str(payload))

    def _on_order_management_operation(self, payload: object) -> None:
        self.refresh_orders()
        context = self._pending_ui_operation
        if not context or not isinstance(payload, dict):
            return
        result = payload.get("result")
        if not isinstance(result, dict):
            return
        context["remaining"] = max(int(context.get("remaining", 1)) - 1, 0)
        status = str(result.get("status") or "unknown")
        if result.get("success"):
            context["confirmed"] = int(context.get("confirmed", 0)) + 1
        elif status == "partial":
            context["partial"] = int(context.get("partial", 0)) + 1
        else:
            context["failed"] = int(context.get("failed", 0)) + 1
        if int(context["remaining"]) > 0:
            return
        confirmed = int(context.get("confirmed", 0))
        partial = int(context.get("partial", 0))
        failed = int(context.get("failed", 0))
        QMessageBox.information(
            self,
            "Kết quả thao tác",
            f"Đã xác nhận: {confirmed}\nKhớp một phần: {partial}\nThất bại/chưa rõ: {failed}",
        )
        self._pending_ui_operation = None

    # ------------------------------------------------------------------
    # Data refresh
    # ------------------------------------------------------------------
    def refresh_orders(self) -> None:
        self._light = self._is_light_theme()
        positions_are_fresh = False
        if self.order_manager is not None:
            # Cache-only UI path. All MT5 reads were produced by the service's
            # single worker executor and delivered through queued Qt signals.
            self._positions = [
                position.to_legacy_dict()
                for position in self.order_manager.cached_positions()
            ]
            self._pending_orders = [
                order.to_legacy_dict()
                for order in self.order_manager.cached_pending_orders()
            ]
            health = self.order_manager.cached_health()
            self._positions_snapshot_status = health.snapshot_status
            self._snapshot_message = health.message
            self._last_broker_refresh = health.observed_at_utc
            positions_are_fresh = (
                health.snapshot_status is SnapshotStatus.AVAILABLE
            )
            self._sync_managed_views()
            if getattr(self, "balance_label", None):
                account = health.account
                self._account_currency = (
                    str(account.currency or "") if account is not None else ""
                )
                balance = account.balance if account is not None else None
                self.balance_label.setText(
                    f"{balance:,.2f} {self._account_currency}".strip()
                    if balance is not None
                    else "--"
                )
        else:
            # Fail-safe standalone mode: no service means no broker I/O from
            # QWidget. The screen remains a read-only empty/stale view.
            self._snapshot_message = "Order Management Service chưa sẵn sàng."
            if getattr(self, "balance_label", None):
                self.balance_label.setText("--")

        if getattr(self, "protection_label", None):
            if positions_are_fresh:
                self.protection_label.setText("HEALTHY")
                self.protection_card.setToolTip(
                    "Broker snapshot đã xác nhận lúc "
                    + (
                        self._last_broker_refresh.astimezone().strftime("%H:%M:%S")
                        if self._last_broker_refresh is not None
                        else "hiện tại"
                    )
                )
            else:
                self.protection_label.setText("STALE")
                self.protection_card.setToolTip(
                    self._snapshot_message
                    or "Không xác nhận được trạng thái broker; tracking được giữ nguyên."
                )

        # Capture original SL for newly detected positions (once, never overwrite)
        for pos in self._positions:
            pos_id = int(pos.get("position_id", 0))
            if pos_id and pos_id not in self._position_original_sl:
                sl = float(pos.get("sl", 0) or 0)
                if sl > 0:
                    self._position_original_sl[pos_id] = sl

        # A failed/unknown read is not proof that a broker position closed.
        if positions_are_fresh and self.order_manager is None:
            self._cleanup_trailing()

        if getattr(self, "position_count_label", None):
            self.position_count_label.setText(f"{len(self._positions)}")
        if getattr(self, "pending_count_label", None):
            self.pending_count_label.setText(f"{len(self._pending_orders)}")

        total_pl = sum(float(p.get("profit", 0) or 0) + float(p.get("swap", 0) or 0) + float(p.get("commission", 0) or 0) for p in self._positions)
        if getattr(self, "pl_label", None):
            self.pl_label.setText(
                f"{total_pl:+,.2f} {self._account_currency}".strip()
            )
            set_dynamic_property(
                self.pl_label,
                "metricTone",
                "negative" if total_pl < 0 else "positive",
            )

        active_trails = sum(1 for cfg in self._trailing_configs.values() if cfg.get("enabled"))
        if getattr(self, "trail_count_label", None):
            self.trail_count_label.setText(f"{active_trails}")

        self._render_table()

    # ------------------------------------------------------------------
    # Table rendering
    # ------------------------------------------------------------------
    def _render_table(self) -> None:
        table = self.order_table

        # Save current selection to restore after rebuild
        selected_pos_id = None
        if self._active_tab == "positions":
            sel_pos = self._get_selected_position()
            if sel_pos:
                selected_pos_id = int(sel_pos.get("position_id", 0))

        table.blockSignals(True)
        table.setRowCount(0)

        if self._active_tab == "positions":
            data = self._positions
            table.setHorizontalHeaderLabels([
                "Mã", "Hướng", "KL", "Entry", "Hiện tại", "SL", "TP",
                "P/L", "R", "Bảo vệ", "Ticket",
            ])
            self.close_selected_btn.setVisible(True)
            self.close_all_btn.setVisible(True)
            self.trail_btn.setVisible(True)
            self.modify_position_btn.setVisible(True)
            self.partial_close_btn.setVisible(True)
            self.modify_pending_btn.setVisible(False)
            self.cancel_pending_btn.setVisible(False)
            # Show clear trail button only if selected position has trailing
            pos = self._get_selected_position()
            has_trail = bool(pos and int(pos.get("position_id", 0)) in self._trailing_configs)
            self.clear_trail_btn.setVisible(has_trail)
        else:
            data = self._pending_orders
            table.setHorizontalHeaderLabels([
                "Mã", "Hướng", "KL", "Entry", "Hiện tại", "SL", "TP",
                "P/L", "R", "Loại lệnh", "Ticket",
            ])
            self.close_selected_btn.setVisible(False)
            self.close_all_btn.setVisible(False)
            self.trail_btn.setVisible(False)
            self.modify_position_btn.setVisible(False)
            self.partial_close_btn.setVisible(False)
            self.clear_trail_btn.setVisible(False)
            self.modify_pending_btn.setVisible(True)
            self.cancel_pending_btn.setVisible(True)

        palette = current_palette(self.settings_service)
        if not data:
            table.setRowCount(1)
            table.setSpan(0, 0, 1, table.columnCount())
            item = QTableWidgetItem("Không có lệnh nào.")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setForeground(QColor(palette.text_muted))
            table.setItem(0, 0, item)
            table.blockSignals(False)
            return

        buy_color = QColor(palette.buy)
        sell_color = QColor(palette.sell)
        neutral_fg = QColor(palette.text_muted)
        self._table_semantic_colors = {
            "success": QColor(palette.success),
            "warning": QColor(palette.warning),
            "info": QColor(palette.info),
            "muted": QColor(palette.text_muted),
        }

        table.setRowCount(len(data))
        for idx, row in enumerate(data):
            if self._active_tab == "positions":
                self._render_position_row(table, idx, row, buy_color, sell_color, neutral_fg)
            else:
                self._render_pending_row(table, idx, row, buy_color, sell_color, neutral_fg)
        # Restore previous selection
        if selected_pos_id and self._active_tab == "positions":
            for r in range(table.rowCount()):
                item = table.item(r, 0)
                # Find row by position_id (stored as custom data in col 0)
                row_data = self._positions[r] if r < len(self._positions) else None
                if row_data and int(row_data.get("position_id", 0)) == selected_pos_id:
                    table.selectRow(r)
                    break

        table.blockSignals(False)

    def _render_position_row(self, table, idx, row, buy_color, sell_color, neutral_fg) -> None:
        def sitem(text, align=Qt.AlignmentFlag.AlignCenter):
            item = QTableWidgetItem(str(text))
            item.setTextAlignment(align)
            return item

        side = str(row.get("side", ""))
        is_buy = side == "buy"
        pos_id = int(row.get("position_id", 0))
        symbol = str(row.get("symbol", "--"))
        digits = max(0, int(row.get("digits", 5) or 5))
        price_format = f".{digits}f"

        def price_text(value: object) -> str:
            return format(float(value or 0), price_format)

        table.setItem(idx, 0, sitem(symbol))
        symbol_font = get_body_font()
        symbol_font.setBold(True)
        table.item(idx, 0).setFont(symbol_font)

        dir_item = sitem("MUA" if is_buy else "BÁN")
        dir_item.setForeground(buy_color if is_buy else sell_color)
        direction_font = get_body_font()
        direction_font.setBold(True)
        dir_item.setFont(direction_font)
        table.setItem(idx, 1, dir_item)

        table.setItem(idx, 2, sitem(f"{float(row.get('volume', 0)):.2f}"))
        table.setItem(idx, 3, sitem(price_text(row.get("open_price", 0))))
        table.setItem(idx, 4, sitem(price_text(row.get("current_price", 0))))

        sl_val = float(row.get("sl", 0) or 0)
        sl_item = sitem(format(sl_val, price_format) if sl_val else "--")
        if sl_val: sl_item.setForeground(sell_color)
        table.setItem(idx, 5, sl_item)

        tp_val = float(row.get("tp", 0) or 0)
        tp_item = sitem(format(tp_val, price_format) if tp_val else "--")
        if tp_val: tp_item.setForeground(buy_color)
        table.setItem(idx, 6, tp_item)

        profit = float(row.get("profit", 0) or 0) + float(row.get("swap", 0) or 0) + float(row.get("commission", 0) or 0)
        pl_item = sitem(f"{profit:+,.2f} {self._account_currency}".strip())
        pl_item.setForeground(buy_color if profit >= 0 else sell_color)
        table.setItem(idx, 7, pl_item)

        # R column: profit / risk
        open_p = float(row.get("open_price", 0) or row.get("price", 0) or 0)
        cur_p = float(row.get("current_price", 0) or 0)
        sl_for_r = float(row.get("sl", 0) or 0)
        # Use captured original SL as Single Source of Truth for R
        orig_sl = self._position_original_sl.get(pos_id)
        if orig_sl is not None and orig_sl > 0:
            sl_for_r = orig_sl
        cfg_r = self._trailing_configs.get(pos_id)
        if cfg_r:
            open_p = float(cfg_r.get("entry_price", open_p) or open_p)
        if open_p and sl_for_r:
            risk = abs(open_p - sl_for_r)
            if is_buy:
                pnl_price = cur_p - open_p
            else:
                pnl_price = open_p - cur_p
            if risk > 0:
                r_val = pnl_price / risk
                r_item = sitem(f"{r_val:+.1f}R")
                r_item.setForeground(buy_color if r_val >= 0 else sell_color)
            else:
                r_item = sitem("--")
        else:
            r_item = sitem("--")
            r_item.setForeground(neutral_fg)
        table.setItem(idx, 8, r_item)

        # Trailing / BE status
        cfg = self._trailing_configs.get(pos_id)
        semantic = self._table_semantic_colors
        phase = str(cfg.get("phase", "") if cfg else "")
        phase_display = {
            "waiting_be": ("⏳ Chờ BE", semantic["muted"]),
            "be_active": ("✅ BE đã xác nhận", semantic["success"]),
            "trail_wide": ("🟢 Trail Wide", semantic["info"]),
            "trail_tight": ("🔒 Trail Tight", semantic["warning"]),
            "paused": ("⏸️ Tạm dừng", semantic["muted"]),
            "stale": ("⚠️ Stale", semantic["warning"]),
            "error_retryable": ("↻ Đang retry", semantic["warning"]),
            "error_non_retryable": ("❌ Lỗi broker", semantic["warning"]),
            "atr_unavailable": ("⚠️ Thiếu ATR H1", semantic["warning"]),
        }
        if phase in phase_display:
            trail_text, trail_color = phase_display[phase]
        elif cfg and cfg.get("enabled"):
            be_done = cfg.get("be_done", False)
            trail_mode = str(cfg.get("trail_mode", "wide"))
            if not be_done:
                trail_text = "⏳ Chờ BE"
                trail_color = semantic["muted"]
            else:
                entry = float(cfg.get("entry_price", 0) or 0)
                current_sl_val = float(cfg.get("current_sl", 0) or 0)
                pip_m = float(cfg.get("pip_multiplier", 10000) or 10000)
                be_sl = entry + (2.0 / pip_m) if cfg.get("side") == "buy" else entry - (2.0 / pip_m)
                if abs(current_sl_val - be_sl) < (1.0 / pip_m):
                    trail_text = "✅ BE"
                    trail_color = semantic["success"]
                elif trail_mode == "tight":
                    trail_text = "🔒 Tight"
                    trail_color = semantic["warning"]
                else:
                    trail_text = "🟢 Wide"
                    trail_color = semantic["info"]
        elif cfg and not cfg.get("enabled"):
            trail_text = "⏸️ Tạm dừng"
            trail_color = semantic["muted"]
        else:
            trail_text = "--"
            trail_color = semantic["muted"]
        trail_item = sitem(trail_text)
        if cfg:
            trail_item.setForeground(trail_color)
        table.setItem(idx, 9, trail_item)
        table.setItem(idx, 10, sitem(str(pos_id)))

    def _render_pending_row(self, table, idx, row, buy_color, sell_color, neutral_fg) -> None:
        def sitem(text, align=Qt.AlignmentFlag.AlignCenter):
            item = QTableWidgetItem(str(text))
            item.setTextAlignment(align)
            return item

        otype = str(row.get("type", ""))
        is_buy_type = "buy" in otype
        digits = max(0, int(row.get("digits", 5) or 5))
        price_format = f".{digits}f"

        sym = sitem(str(row.get("symbol", "--")))
        symbol_font = get_body_font()
        symbol_font.setBold(True)
        sym.setFont(symbol_font)
        table.setItem(idx, 0, sym)

        dir_item = sitem("MUA" if is_buy_type else "BÁN")
        dir_item.setForeground(buy_color if is_buy_type else sell_color)
        direction_font = get_body_font()
        direction_font.setBold(True)
        dir_item.setFont(direction_font)
        table.setItem(idx, 1, dir_item)

        table.setItem(idx, 2, sitem(f"{float(row.get('volume', 0)):.2f}"))
        table.setItem(idx, 3, sitem(format(float(row.get("price", 0) or 0), price_format)))
        table.setItem(idx, 4, sitem("--"))

        sl_val = float(row.get("sl", 0) or 0)
        sl_item = sitem(format(sl_val, price_format) if sl_val else "--")
        if sl_val: sl_item.setForeground(sell_color)
        table.setItem(idx, 5, sl_item)

        tp_val = float(row.get("tp", 0) or 0)
        tp_item = sitem(format(tp_val, price_format) if tp_val else "--")
        if tp_val: tp_item.setForeground(buy_color)
        table.setItem(idx, 6, tp_item)

        table.setItem(idx, 7, sitem("--"))
        table.setItem(idx, 8, sitem("--"))
        table.setItem(idx, 9, sitem(otype.replace("_", " ").upper() or "--"))
        order_id = int(row.get("order_id", 0) or 0)
        ticket_item = sitem(str(order_id) if order_id else "--")
        setup_time = int(row.get("setup_time", 0) or 0)
        comment = str(row.get("comment", "") or "")
        ticket_item.setToolTip(
            f"Magic: {int(row.get('magic', 0) or 0)}\n"
            f"Setup time: {setup_time or '--'}\nComment: {comment or '--'}"
        )
        table.setItem(idx, 10, ticket_item)

    # ------------------------------------------------------------------
    # Trailing stop engine
    # ------------------------------------------------------------------
    def _cleanup_trailing(self) -> None:
        open_ids = {int(p.get("position_id", 0)) for p in self._positions}
        stale = [pid for pid in self._trailing_configs if pid not in open_ids]
        for pid in stale:
            del self._trailing_configs[pid]
        # Also clean up original SL entries for closed positions
        stale_sl = [pid for pid in self._position_original_sl if pid not in open_ids]
        for pid in stale_sl:
            del self._position_original_sl[pid]
        if stale or stale_sl:
            self._debounce_save()

    def _trailing_tick(self) -> None:
        """Compatibility hook: schedule the service, never execute MT5 in UI."""

        if self.order_manager is not None:
            self.order_manager.request_refresh()

    def _show_trailing_dialog(self) -> None:
        pos = self._get_selected_position()
        if not pos:
            QMessageBox.information(self, "Trailing Stop", "Chọn một vị thế trong bảng trước.")
            return

        pos_id = int(pos.get("position_id", 0))
        symbol = str(pos.get("symbol", "--"))
        side = str(pos.get("side", ""))
        is_buy = side == "buy"
        current_sl = float(pos.get("sl", 0) or 0)
        volume = float(pos.get("volume", 0))
        profit = float(pos.get("profit", 0) or 0) + float(pos.get("swap", 0) or 0)

        # ---- Fetch live Bid/Ask ----
        _dlg_bid = 0.0
        _dlg_ask = 0.0
        _tick_snapshot = (
            self.order_manager.latest_tick(symbol)
            if self.order_manager is not None
            else None
        )
        if _tick_snapshot is not None and _tick_snapshot.available:
            _dlg_bid = float(_tick_snapshot.tick.bid)
            _dlg_ask = float(_tick_snapshot.tick.ask)
        else:
            cached_price = float(pos.get("current_price", 0) or 0)
            _dlg_bid = cached_price
            _dlg_ask = cached_price
        current_price = _dlg_bid if side == "buy" else _dlg_ask if side == "sell" else 0.0

        existing = self._trailing_configs.get(pos_id)
        default_pips = existing.get("trail_pips", 20) if existing else 20
        trail_enabled = bool(existing and existing.get("enabled"))

        # ---- Dirty state: snapshot initial config for change detection ----
        self._dlg_trail_mode = existing.get("trail_mode", "wide") if existing else "wide"
        _initial_snapshot = {
            "trail_mode": self._dlg_trail_mode,
            "trail_pips": default_pips,
        }

        def _current_snapshot():
            return {
                "trail_mode": getattr(self, "_dlg_trail_mode", "wide"),
                "trail_pips": self._dlg_pip_spin.value(),
            }

        def _is_dirty():
            return _current_snapshot() != _initial_snapshot

        light = is_light_theme(self.settings_service)

        dlg = QDialog(self)
        dlg.setWindowTitle(f"🎯 Trailing Stop — {symbol} ({'MUA' if is_buy else 'BÁN'} {volume:.2f})")
        dlg.setMinimumWidth(650)
        dlg.setObjectName("AnalysisDetailDialog")
        dlg.setProperty("trailingDialog", True)

        root = QVBoxLayout(dlg)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(14)

        # Title
        title = QLabel(f"🎯 Cấu hình Trailing Stop")
        title.setObjectName("ActionTitle")
        root.addWidget(title)

        # 1. Position summary card
        summary_card = card("Thông tin lệnh")
        summary_card.layout().setContentsMargins(16, 12, 16, 12)

        entry_price = float(pos.get("open_price", 0) or 0)
        digits = int(pos.get("digits", 5) or 5)
        point = float(pos.get("point", 0) or 10 ** (-digits))
        tick_size = float(pos.get("trade_tick_size", 0) or point)
        pip_size = max(tick_size, point * (10 if digits in {3, 5} else 1))
        pip_m = 1.0 / pip_size

        # ---- Single Source of Truth: effective initial SL ----
        # Priority: cfg["initial_sl"] (set when trailing was enabled)
        # Fallback: current_sl from MT5 (valid when trailing not yet enabled)
        _cfg_for_sl = existing if isinstance(existing, dict) else {}
        # Priority: _position_original_sl > cfg.initial_sl > current MT5 SL
        _orig_sl = self._position_original_sl.get(pos_id)
        _cfg_initial_sl = _cfg_for_sl.get("initial_sl")
        if _orig_sl is not None and _orig_sl > 0:
            effective_initial_sl = _orig_sl
        elif _cfg_initial_sl is not None and float(_cfg_initial_sl) > 0:
            effective_initial_sl = float(_cfg_initial_sl)
        else:
            effective_initial_sl = current_sl if current_sl > 0 else float(pos.get("sl", 0) or 0)

        risk_1r = abs(entry_price - effective_initial_sl) if entry_price and effective_initial_sl else 0.0

        # Helpers for live-updating labels
        def _profit_pips(cp: float) -> float:
            p = abs(entry_price - cp) / pip_size
            return p if (is_buy and cp >= entry_price) or (not is_buy and cp <= entry_price) else -p

        def _r_multiple(cp: float) -> float:
            r = (abs(entry_price - cp) / risk_1r) if risk_1r > 0 else 0.0
            return r if _profit_pips(cp) >= 0 else -r

        profit_pips_signed = _profit_pips(current_price)
        r_multiple_signed = _r_multiple(current_price)

        # Row 1: static info
        row1 = QHBoxLayout()
        row1.setSpacing(20)
        row1.addWidget(labeled_value("MÃ GIAO DỊCH", symbol))
        row1.addWidget(labeled_value("HƯỚNG", "MUA" if is_buy else "BÁN"))
        row1.addWidget(labeled_value("KHỐI LƯỢNG", f"{volume:.2f}"))
        row1.addWidget(labeled_value("ENTRY", f"{entry_price:.5f}"))
        row1.addWidget(labeled_value("SL HIỆN TẠI", f"{current_sl:.5f}" if current_sl else "Chưa đặt"))
        row1.addStretch()
        summary_card.layout().addLayout(row1)

        # Row 2: live-updating data — store labels for timer refresh
        row2 = QHBoxLayout()
        row2.setSpacing(20)

        info_cp = labeled_value("GIÁ HIỆN TẠI", f"{current_price:.5f}" if current_price > 0 else "--")
        self._dlg_cp_label = info_cp.findChild(QLabel, "MiniStatValue")
        row2.addWidget(info_cp)

        info_pl = labeled_value(
            "P/L", f"{profit:+,.2f} {self._account_currency}".strip()
        )
        self._dlg_pl_label = info_pl.findChild(QLabel, "MiniStatValue")
        row2.addWidget(info_pl)

        info_pips = labeled_value("P/L PIP", f"{profit_pips_signed:+.1f} pip")
        self._dlg_pips_label = info_pips.findChild(QLabel, "MiniStatValue")
        row2.addWidget(info_pips)

        info_r = labeled_value("R", f"{r_multiple_signed:+.2f}R")
        self._dlg_r_label = info_r.findChild(QLabel, "MiniStatValue")
        row2.addWidget(info_r)

        row2.addStretch()
        summary_card.layout().addLayout(row2)

        def _refresh_live_labels(cp: float, prof: float, pips_signed: float, r_signed: float) -> None:
            """Update labels in real-time. Safe to call from timer."""
            if self._dlg_cp_label and cp > 0:
                self._dlg_cp_label.setText(f"{cp:.5f}")
                set_dynamic_property(self._dlg_cp_label, "metricTone", "positive")

            if self._dlg_pl_label:
                self._dlg_pl_label.setText(
                    f"{prof:+,.2f} {self._account_currency}".strip()
                )
                set_dynamic_property(
                    self._dlg_pl_label,
                    "metricTone",
                    "positive" if prof >= 0 else "negative",
                )

            if self._dlg_pips_label:
                self._dlg_pips_label.setText(f"{pips_signed:+.1f} pip")
                set_dynamic_property(
                    self._dlg_pips_label,
                    "metricTone",
                    "positive" if pips_signed >= 0 else "negative",
                )

            if self._dlg_r_label:
                self._dlg_r_label.setText(f"{r_signed:+.2f}R")
                r_tone = (
                    "positive"
                    if r_signed >= 1.0
                    else "warning"
                    if r_signed >= 0.5
                    else "negative"
                    if r_signed < 0
                    else "positive"
                )
                set_dynamic_property(self._dlg_r_label, "metricTone", r_tone)

        _refresh_live_labels(current_price, profit, profit_pips_signed, r_multiple_signed)

        root.addWidget(summary_card)

        # 2. Settings card -- unified manual + AI
        settings_card = card("Cài đặt khoảng cách")
        settings_card.layout().setContentsMargins(16, 12, 16, 12)
        settings_card.layout().setSpacing(10)

        # Cache ATR H1 once for preview
        # ATR is supplied by the closed-H1 Scanner analysis and persisted by
        # OrderManagementService. The UI never fetches a forming candle.
        _dlg_atr_h1 = float(existing.get("atr_h1", 0) or 0) if existing else 0.0

        initial_sl_raw = effective_initial_sl
        # Row 0: Trail mode radio buttons
        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)
        mode_row.addWidget(QLabel("Chế độ:"))
        self._dlg_mode_group = QButtonGroup(dlg)
        self._dlg_mode_wide = QRadioButton("Wide (2.5× ATR)")
        self._dlg_mode_tight = QRadioButton("Tight (1.5× ATR)")
        self._dlg_mode_fixed = QRadioButton("Cố định (pip)")
        if self.order_manager is not None:
            self._dlg_mode_fixed.setEnabled(False)
            self._dlg_mode_fixed.setToolTip(
                "Order Management V2 dùng ATR H1 đã đóng; fixed-pip không được fallback âm thầm."
            )
        existing_mode = existing.get("trail_mode", "wide") if existing else "wide"
        self._dlg_mode_wide.setChecked(existing_mode == "wide")
        self._dlg_mode_tight.setChecked(existing_mode == "tight")
        self._dlg_mode_fixed.setChecked(existing_mode == "fixed")
        self._dlg_mode_group.addButton(self._dlg_mode_wide, 0)
        self._dlg_mode_group.addButton(self._dlg_mode_tight, 1)
        self._dlg_mode_group.addButton(self._dlg_mode_fixed, 2)

        # Tooltips content for each mode
        help_wide_txt = (
            "Wide (2.5× ATR)\n\n"
            "Sử dụng khoảng cách Trailing Stop bằng khoảng 2.5 lần ATR.\n\n"
            "Ưu điểm:\n"
            "• Ít bị quét Stop Loss.\n"
            "• Phù hợp thị trường biến động mạnh.\n"
            "• Giữ lệnh lâu hơn.\n\n"
            "Nhược điểm:\n"
            "• Chốt lời chậm hơn.\n"
            "• Khoảng lỗ tạm thời có thể lớn hơn.\n\n"
            "Khuyến nghị:\n"
            "Swing Trading hoặc xu hướng mạnh."
        )
        
        help_tight_txt = (
            "Tight (1.5× ATR)\n\n"
            "Trailing Stop gần giá hơn.\n\n"
            "Ưu điểm:\n"
            "• Khóa lợi nhuận nhanh.\n"
            "• Phù hợp thị trường ổn định.\n\n"
            "Nhược điểm:\n"
            "• Dễ bị đá khỏi lệnh khi giá rung.\n\n"
            "Khuyến nghị:\n"
            "Scalping hoặc Intraday."
        )
        
        help_fixed_txt = (
            "Cố định (pip)\n\n"
            "Khoảng cách Trailing Stop do người dùng nhập.\n\n"
            "Ưu điểm:\n"
            "• Chủ động.\n"
            "• Phù hợp khi đã có chiến lược riêng.\n\n"
            "Lưu ý:\n"
            "Khoảng cách quá nhỏ có thể làm lệnh đóng sớm."
        )

        def create_help_btn(tooltip_text: str) -> QPushButton:
            btn = QPushButton("?")
            btn.setObjectName("HelpButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tooltip_text)
            btn.clicked.connect(lambda: QToolTip.showText(QCursor.pos(), tooltip_text, btn))
            return btn

        self._dlg_help_wide = create_help_btn(help_wide_txt)
        self._dlg_help_tight = create_help_btn(help_tight_txt)
        self._dlg_help_fixed = create_help_btn(help_fixed_txt)

        # Add to layout
        mode_row.addWidget(self._dlg_mode_wide)
        mode_row.addWidget(self._dlg_help_wide)
        mode_row.addSpacing(10)
        mode_row.addWidget(self._dlg_mode_tight)
        mode_row.addWidget(self._dlg_help_tight)
        mode_row.addSpacing(10)
        mode_row.addWidget(self._dlg_mode_fixed)
        mode_row.addWidget(self._dlg_help_fixed)

        mode_row.addStretch()
        settings_card.layout().addLayout(mode_row)

        def _on_mode_changed():
            is_fixed = self._dlg_mode_fixed.isChecked()
            self._dlg_pip_spin.setEnabled(is_fixed)
            # Update preview with new mode
            if self._dlg_mode_wide.isChecked():
                self._dlg_trail_mode = "wide"
            elif self._dlg_mode_tight.isChecked():
                self._dlg_trail_mode = "tight"
            else:
                self._dlg_trail_mode = "fixed"
            _update_preview()

        self._dlg_mode_wide.toggled.connect(_on_mode_changed)
        self._dlg_mode_tight.toggled.connect(_on_mode_changed)
        self._dlg_mode_fixed.toggled.connect(_on_mode_changed)

        # Row 1: spinbox + presets
        pip_layout = QHBoxLayout()
        pip_layout.setSpacing(8)
        self._dlg_pip_spin = QSpinBox()
        self._dlg_pip_spin.setRange(5, 200)
        self._dlg_pip_spin.setValue(default_pips)
        self._dlg_pip_spin.setSuffix(" pip")
        self._dlg_pip_spin.setMinimumWidth(100)
        self._dlg_pip_spin.setEnabled(existing_mode == "fixed")
        pip_layout.addWidget(self._dlg_pip_spin)
        pip_layout.addWidget(QLabel("Nhanh:"))
        for pips in [10, 20, 30, 50]:
            btn = QPushButton(f"{pips}p")
            btn.setFixedWidth(48)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, v=pips: self._dlg_pip_spin.setValue(v))
            pip_layout.addWidget(btn)
        pip_layout.addStretch()
        settings_card.layout().addLayout(pip_layout)

        root.addWidget(settings_card)

        # 3. Preview card: BE + Trail (live update)
        preview_card = card("Xem trước")
        preview_card.layout().setContentsMargins(16, 10, 16, 10)
        preview_card.layout().setSpacing(5)

        # BE section
        self._dlg_be_title = QLabel("🎯 Break Even")
        self._dlg_be_title.setObjectName("CardDetail")
        self._dlg_be_title.setFont(get_subtitle_font())
        preview_card.layout().addWidget(self._dlg_be_title)

        self._dlg_be_sl_label = QLabel("")
        self._dlg_be_sl_label.setObjectName("CardDetail")
        preview_card.layout().addWidget(self._dlg_be_sl_label)

        self._dlg_be_trigger_label = QLabel("")
        self._dlg_be_trigger_label.setObjectName("CardDetail")
        preview_card.layout().addWidget(self._dlg_be_trigger_label)

        self._dlg_be_status_label = QLabel("")
        self._dlg_be_status_label.setObjectName("CardDetail")
        preview_card.layout().addWidget(self._dlg_be_status_label)

        self._dlg_be_distance_label = QLabel("")
        self._dlg_be_distance_label.setObjectName("CardDetail")
        preview_card.layout().addWidget(self._dlg_be_distance_label)

        # Separator
        sep = QLabel("")
        sep.setObjectName("CardDetail")
        preview_card.layout().addWidget(sep)

        # Trail section
        self._dlg_trail_title = QLabel("📐 Trailing Stop")
        self._dlg_trail_title.setObjectName("CardDetail")
        self._dlg_trail_title.setFont(get_subtitle_font())
        preview_card.layout().addWidget(self._dlg_trail_title)

        self._dlg_trail_mode_label = QLabel("")
        self._dlg_trail_mode_label.setObjectName("CardDetail")
        preview_card.layout().addWidget(self._dlg_trail_mode_label)

        self._dlg_trail_dist_label = QLabel("")
        self._dlg_trail_dist_label.setObjectName("CardDetail")
        preview_card.layout().addWidget(self._dlg_trail_dist_label)

        def _update_preview(pips_val=None):
            if pips_val is None:
                pips_val = self._dlg_pip_spin.value()

            # ---- Break Even ----
            be_trigger = 2.0 * entry_price - initial_sl_raw if entry_price and initial_sl_raw else 0
            be_sl = entry_price + (2.0 / pip_m) if is_buy else entry_price - (2.0 / pip_m)

            if be_trigger:
                self._dlg_be_sl_label.setText(f"SL sẽ dời về:  {be_sl:.5f}")
                self._dlg_be_trigger_label.setText(f"Điểm kích hoạt:  {be_trigger:.5f}")
            else:
                self._dlg_be_sl_label.setText("SL sẽ dời về:  chưa đủ dữ liệu entry/SL")
                self._dlg_be_trigger_label.setText("")

            # ---- Trailing ----
            mode = getattr(self, "_dlg_trail_mode", None) or "wide"
            mode_labels = {"wide": "Wide (2.5× ATR)", "tight": "Tight (1.5× ATR)", "fixed": "Cố định (pip)"}
            self._dlg_trail_mode_label.setText(f"Chế độ:  {mode_labels.get(mode, mode)}")

            if _dlg_atr_h1 > 0 and mode != "fixed":
                mult = 2.5 if mode == "wide" else 1.5
                trail_price = _dlg_atr_h1 * mult
                trail_pip = trail_price / pip_size
                self._dlg_trail_dist_label.setText(
                    f"Khoảng cách trail:  {trail_price:.5f}  (~{trail_pip:.0f} pip)"
                )
            else:
                self._dlg_trail_dist_label.setText(f"Khoảng cách trail:  {pips_val} pip  (thủ công)")

        def _update_be_live(cp: float, live_sl: float = 0.0) -> None:
            """Update only the BE status & distance labels. Called by timer.

            If be_done=True but MT5 SL no longer equals BE SL (e.g. user moved
            it manually), show a mild warning instead of claiming BE is active.
            """
            be_trigger = 2.0 * entry_price - initial_sl_raw if entry_price and initial_sl_raw else 0
            if not be_trigger or cp <= 0:
                return

            be_sl = entry_price + (2.0 / pip_m) if is_buy else entry_price - (2.0 / pip_m)
            sl_tolerance = 1.0 / pip_m  # 0.1 pip

            # Check if BE has already been activated (source: trailing config)
            be_already_done = bool(_cfg_for_sl.get("be_done", False)) if _cfg_for_sl else False
            # Verify MT5 SL still matches BE SL (may differ if user moved SL manually)
            sl_matches_be = live_sl > 0 and abs(live_sl - be_sl) < sl_tolerance

            if is_buy:
                dist = be_trigger - cp
            else:
                dist = cp - be_trigger

            dist_pips = dist * pip_m
            if be_already_done and sl_matches_be:
                self._dlg_be_status_label.setText("✅ Đã kích hoạt Break Even")
                set_dynamic_property(self._dlg_be_status_label, "statusTone", "success")
                self._dlg_be_distance_label.setText("")
            elif be_already_done and not sl_matches_be:
                self._dlg_be_status_label.setText("⚠️ Break Even đã kích hoạt trước đó — SL hiện tại không còn ở vị trí BE")
                set_dynamic_property(self._dlg_be_status_label, "statusTone", "warning")
                self._dlg_be_distance_label.setText("")
            elif dist <= 0:
                self._dlg_be_status_label.setText("🟢 Đã sẵn sàng kích hoạt Break Even")
                set_dynamic_property(self._dlg_be_status_label, "statusTone", "success")
                self._dlg_be_distance_label.setText("")
            else:
                self._dlg_be_status_label.setText("🟡 Chưa kích hoạt Break Even")
                set_dynamic_property(self._dlg_be_status_label, "statusTone", "warning")
                self._dlg_be_distance_label.setText(f"Còn:  {dist_pips:.1f} pip")
                set_dynamic_property(
                    self._dlg_be_distance_label,
                    "statusTone",
                    "warning" if dist_pips < 3 else "neutral",
                )

        _update_preview(default_pips)
        _update_be_live(current_price, current_sl)
        self._dlg_pip_spin.valueChanged.connect(_update_preview)
        root.addWidget(preview_card)

        # ---- Auto-refresh timer: update live data every 2s ----
        _live_timer = QTimer(dlg)
        _live_timer.setInterval(2000)

        def _on_live_tick():
            """Render only service cache; broker I/O remains on its executor."""

            latest = next(
                (
                    item
                    for item in self._positions
                    if int(item.get("position_id", 0)) == pos_id
                ),
                None,
            )
            if latest is None:
                return
            tick_snapshot = (
                self.order_manager.latest_tick(symbol)
                if self.order_manager is not None
                else None
            )
            if tick_snapshot is not None and tick_snapshot.available:
                tick = tick_snapshot.tick
                _cp = float(tick.bid) if side == "buy" else float(tick.ask)
            else:
                _cp = float(latest.get("current_price", 0) or 0)
            if _cp <= 0:
                return
            _prof = float(latest.get("profit", 0) or 0) + float(
                latest.get("swap", 0) or 0
            )
            _live_sl = float(latest.get("sl", 0) or 0)
            _pips = _profit_pips(_cp)
            _r = _r_multiple(_cp)
            _refresh_live_labels(_cp, _prof, _pips, _r)
            _update_be_live(_cp, _live_sl)

        _live_timer.timeout.connect(_on_live_tick)
        _live_timer.start()
        dlg.finished.connect(_live_timer.stop)

        # --- Buttons ---
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        # Store button refs and original texts for loading-state management
        self._dlg_btns: list[tuple[QPushButton, str]] = []

        def _begin_op(*btns: QPushButton):
            """Disable buttons & change text during an operation."""
            self._dlg_btns.clear()
            for b in btns:
                self._dlg_btns.append((b, b.text()))
                b.setEnabled(False)

        def _end_op():
            """Restore all buttons to their pre-operation state."""
            for b, old_text in self._dlg_btns:
                b.setEnabled(True)
                b.setText(old_text)
            self._dlg_btns.clear()

        close_btn = action_button("❌ Đóng", primary=False, color="danger")
        close_btn.clicked.connect(dlg.accept)

        if trail_enabled:
            # Trailing is active → show Update + Disable
            self._dlg_update_btn = action_button("🔄 Cập nhật Trailing Stop", primary=True, color="success")
            self._dlg_update_btn.setEnabled(False)
            self._dlg_update_btn.setToolTip("Chưa có thay đổi để cập nhật.")
            self._dlg_update_btn.clicked.connect(
                lambda: self._handle_update_trailing(pos_id, dlg, _current_snapshot, _initial_snapshot, _begin_op, _end_op, close_btn))
            btn_layout.addWidget(self._dlg_update_btn)

            self._dlg_disable_btn = action_button("⏹️ Tắt Trailing Stop", primary=True, color="danger")
            self._dlg_disable_btn.clicked.connect(
                lambda: self._handle_disable_trailing(pos_id, dlg, _begin_op, _end_op, self._dlg_update_btn, close_btn))
            btn_layout.addWidget(self._dlg_disable_btn)

            # ---- Dirty state: enable/disable update button based on changes ----
            def _refresh_dirty_state():
                dirty = _is_dirty()
                self._dlg_update_btn.setEnabled(dirty)
                if dirty:
                    self._dlg_update_btn.setToolTip("Áp dụng cấu hình trailing mới ngay lập tức.")
                else:
                    self._dlg_update_btn.setToolTip("Chưa có thay đổi để cập nhật.")

            _refresh_dirty_state()
            self._dlg_pip_spin.valueChanged.connect(lambda v: _refresh_dirty_state())
            self._dlg_mode_wide.toggled.connect(lambda: _refresh_dirty_state())
            self._dlg_mode_tight.toggled.connect(lambda: _refresh_dirty_state())
            self._dlg_mode_fixed.toggled.connect(lambda: _refresh_dirty_state())
        else:
            # Trailing not active → show Enable
            self._dlg_enable_btn = action_button("✅ Bật Trailing Stop", primary=True)
            self._dlg_enable_btn.clicked.connect(
                lambda: self._handle_enable_trailing(pos_id, symbol, side, dlg, _begin_op, _end_op, close_btn))
            btn_layout.addWidget(self._dlg_enable_btn)

        btn_layout.addWidget(close_btn)

        root.addLayout(btn_layout)

        dlg.exec()

    # ------------------------------------------------------------------
    # Trailing Stop operation handlers (unified feedback)
    # ------------------------------------------------------------------

    def _handle_enable_trailing(self, pos_id: int, symbol: str, side: str,
                                  dlg: QDialog, _begin_op, _end_op,
                                  close_btn: QPushButton) -> None:
        """Bật Trailing Stop mới — có loading state + feedback."""
        enable_btn = self._dlg_enable_btn
        _begin_op(enable_btn, close_btn)
        enable_btn.setText("Đang bật...")

        try:
            trail_pips = self._dlg_pip_spin.value()
            pos = self._get_selected_position()
            if not pos:
                raise ValueError("Không tìm thấy vị thế đã chọn (có thể đã bị đóng).")

            entry_price = float(pos.get("open_price", 0) or pos.get("price", 0) or 0)
            initial_sl = self._position_original_sl.get(pos_id) or float(pos.get("sl", 0) or 0)
            if entry_price <= 0:
                raise ValueError("Không xác định được giá entry.")
            if initial_sl <= 0:
                raise ValueError("Vị thế chưa có Stop Loss — cần đặt SL trước khi bật Trailing Stop.")
            digits = int(pos.get("digits", 5) or 5)
            point = float(pos.get("point", 0) or 10 ** (-digits))
            tick_size = float(pos.get("trade_tick_size", 0) or point)
            pip_size = max(
                tick_size,
                point * (10 if digits in {3, 5} else 1),
            )
            pip_m = 1.0 / pip_size

            trail_mode = getattr(self, "_dlg_trail_mode", None) or "wide"
            be_trigger_price = 2.0 * entry_price - initial_sl

            atr_h1 = float(
                (self._trailing_configs.get(pos_id) or {}).get("atr_h1", 0)
                or 0
            )

            if self.order_manager is not None:
                self.order_manager.register_position(
                    verified_ticket=pos_id,
                    broker_symbol=str(pos.get("broker_symbol") or symbol),
                    side=side,
                    actual_entry_price=entry_price,
                    initial_sl=initial_sl,
                    atr=atr_h1 or None,
                    magic=int(pos.get("magic", 0) or 0) or None,
                    correlation_id=str(pos.get("comment") or ""),
                )
                self.order_manager.resume_position(pos_id)
                self._sync_managed_views()
                projected = self._trailing_configs.get(pos_id) or {}
                if projected.get("phase") in {"trail_wide", "trail_tight"}:
                    trail_mode = str(projected.get("trail_mode") or trail_mode)
            else:
                self._trailing_configs[pos_id] = {
                    "position_id": pos_id, "symbol": symbol, "side": side,
                    "enabled": True, "trail_pips": trail_pips,
                    "extreme_price": 0.0, "current_sl": 0.0, "be_done": False,
                    "be_trigger_price": be_trigger_price,
                    "entry_price": entry_price, "initial_sl": initial_sl,
                    "atr_h1": atr_h1, "trail_mode": trail_mode,
                    "pip_multiplier": pip_m,
                }
                self._debounce_save()
            self._render_table()

            mode_labels = {"wide": "Wide (2.5× ATR)", "tight": "Tight (1.5× ATR)", "fixed": "Cố định"}
            mode_display = mode_labels.get(trail_mode, trail_mode)
            detail = (f"Đã bật Trailing Stop cho {symbol}.\n\n"
                      f"Chế độ: {mode_display}\n"
                      f"Khoảng cách: {trail_pips} pip\n"
                      f"BE tại: {be_trigger_price:.5f}")
            QMessageBox.information(dlg, "Đã bật Trailing Stop", detail)
            dlg.accept()

        except Exception as exc:
            QMessageBox.warning(dlg, "Lỗi bật Trailing Stop",
                                f"Không thể bật Trailing Stop cho {symbol}.\n\nChi tiết: {exc}")
            _end_op()

    def _handle_update_trailing(self, pos_id: int, dlg: QDialog,
                                  _get_snapshot, _initial_snapshot,
                                  _begin_op, _end_op,
                                  close_btn: QPushButton) -> None:
        """Cập nhật Trailing Stop đang chạy — có guard no-change + loading state + feedback."""
        cfg = self._trailing_configs.get(pos_id)
        if not cfg:
            QMessageBox.warning(dlg, "Lỗi cập nhật",
                                "Trailing Stop không còn tồn tại (có thể lệnh đã bị đóng).")
            return

        # Guard: no actual change
        new_snapshot = _get_snapshot()
        if new_snapshot == _initial_snapshot:
            QMessageBox.information(dlg, "Không có thay đổi",
                                    "Cấu hình Trailing Stop không thay đổi so với hiện tại.")
            return

        update_btn = self._dlg_update_btn
        disable_btn = self._dlg_disable_btn
        _begin_op(update_btn, disable_btn, close_btn)
        update_btn.setText("Đang cập nhật...")

        try:
            trail_pips = self._dlg_pip_spin.value()
            trail_mode = getattr(self, "_dlg_trail_mode", None) or "wide"
            symbol = str(cfg.get("symbol", ""))

            old_mode = str(cfg.get("trail_mode", "wide"))
            old_pips = int(cfg.get("trail_pips", 20))

            # ATR is broker/scanner-service data, never fetched in the dialog.
            atr_h1 = float(cfg.get("atr_h1", 0) or 0)

            # Cập nhật config in-place — giữ nguyên runtime state
            cfg["trail_pips"] = trail_pips
            cfg["trail_mode"] = trail_mode
            cfg["atr_h1"] = atr_h1

            # Đồng bộ snapshot
            _initial_snapshot["trail_mode"] = trail_mode
            _initial_snapshot["trail_pips"] = trail_pips

            self._debounce_save()
            self._render_table()

            # Restore buttons
            _end_op()
            update_btn.setEnabled(False)
            update_btn.setToolTip("Chưa có thay đổi để cập nhật.")

            mode_labels = {"wide": "Wide (2.5× ATR)", "tight": "Tight (1.5× ATR)", "fixed": "Cố định"}
            old_mode_disp = mode_labels.get(old_mode, old_mode)
            new_mode_disp = mode_labels.get(trail_mode, trail_mode)

            changed_parts = []
            if old_mode != trail_mode:
                changed_parts.append(f"Chế độ: {old_mode_disp} → {new_mode_disp}")
            if old_pips != trail_pips:
                changed_parts.append(f"Khoảng cách: {old_pips} pip → {trail_pips} pip")

            detail = f"Đã cập nhật Trailing Stop cho {symbol}.\n\n" + "\n".join(changed_parts)
            QMessageBox.information(dlg, "Đã cập nhật", detail)

        except Exception as exc:
            QMessageBox.warning(dlg, "Lỗi cập nhật",
                                f"Không thể cập nhật Trailing Stop.\n\nChi tiết: {exc}")
            _end_op()
            # Re-evaluate dirty state
            is_dirty = _get_snapshot() != _initial_snapshot
            self._dlg_update_btn.setEnabled(is_dirty)
            if is_dirty:
                self._dlg_update_btn.setToolTip("Áp dụng cấu hình trailing mới ngay lập tức.")
            else:
                self._dlg_update_btn.setToolTip("Chưa có thay đổi để cập nhật.")

    def _handle_disable_trailing(self, pos_id: int, dlg: QDialog,
                                   _begin_op, _end_op,
                                   update_btn: QPushButton,
                                   close_btn: QPushButton) -> None:
        """Tắt Trailing Stop — có loading state + feedback."""
        cfg = self._trailing_configs.get(pos_id)
        if not cfg:
            QMessageBox.warning(dlg, "Lỗi", "Trailing Stop không còn tồn tại.")
            return

        disable_btn = self._dlg_disable_btn
        _begin_op(update_btn, disable_btn, close_btn)
        disable_btn.setText("Đang tắt...")
        symbol = str(cfg.get("symbol", "--"))

        try:
            if self.order_manager is not None:
                self.order_manager.pause_position(pos_id)
                self._sync_managed_views()
            else:
                cfg["enabled"] = False
                cfg["extreme_price"] = 0.0
                cfg["current_sl"] = 0.0
                self._debounce_save()
            self._render_table()

            QMessageBox.information(dlg, "Đã tắt Trailing Stop",
                                    f"Đã tắt Trailing Stop cho {symbol}.\n"
                                    f"Cấu hình vẫn được lưu — có thể bật lại sau.")
            dlg.accept()

        except Exception as exc:
            QMessageBox.warning(dlg, "Lỗi tắt Trailing Stop",
                                f"Không thể tắt Trailing Stop cho {symbol}.\n\nChi tiết: {exc}")
            _end_op()

    # ------------------------------------------------------------------
    # Legacy methods (kept for backward compatibility with auto-trade)
    # ------------------------------------------------------------------

    def auto_enable_tracking(self, pos_id: int, symbol: str, side: str,
                             entry: float, sl: float, atr_h1: float) -> None:
        manager = self.__dict__.get("order_manager")
        if manager is not None:
            manager.register_position(
                verified_ticket=pos_id,
                broker_symbol=symbol,
                side=side,
                actual_entry_price=entry,
                initial_sl=sl,
                atr=atr_h1 or None,
            )
            self._sync_managed_views()
            self._render_table()
            return
        pip_multiplier = 100.0 if "JPY" in symbol.upper() else 10000.0
        self._position_original_sl[pos_id] = sl
        self._trailing_configs[pos_id] = {
            "position_id": pos_id,
            "symbol": symbol,
            "side": side,
            "enabled": True,
            "trail_pips": 20,
            "extreme_price": 0.0,
            "current_sl": sl,
            "be_done": False,
            "be_trigger_price": 2.0 * entry - sl,
            "entry_price": entry,
            "initial_sl": sl,
            "atr_h1": atr_h1,
            "trail_mode": "wide",
            "pip_multiplier": pip_multiplier,
        }
        self._debounce_save()
        try:
            self._render_table()
        except Exception:
            pass

    def _clear_trailing(self) -> None:
        pos = self._get_selected_position()
        if not pos:
            return
        pos_id = int(pos.get("position_id", 0))
        if self.__dict__.get("order_manager") is not None:
            self.order_manager.unregister_position(pos_id)
            self._sync_managed_views()
            self._render_table()
            return
        if pos_id in self._trailing_configs:
            del self._trailing_configs[pos_id]
            self._debounce_save()
        self._render_table()

    def _update_clear_trail_visibility(self) -> None:
        pos = self._get_selected_position()
        has_trail = bool(pos and int(pos.get("position_id", 0)) in self._trailing_configs)
        self.clear_trail_btn.setVisible(has_trail)



    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _state_path(self):
        from pathlib import Path
        from config.paths import app_data_dir
        d = app_data_dir()
        d.mkdir(parents=True, exist_ok=True)
        return d / "be_trailing_state.json"

    def _save_trailing_state(self) -> None:
        if self.__dict__.get("order_manager") is not None:
            return
        import json as _json
        try:
            if not self._trailing_configs and not self._position_original_sl:
                p = self._state_path()
                if p.exists():
                    p.unlink()
                return
            data = {
                "positions": {str(k): v for k, v in self._trailing_configs.items()},
                "original_sl": {str(k): v for k, v in self._position_original_sl.items()},
            }
            self._state_path().write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load_trailing_state(self) -> None:
        if self.__dict__.get("order_manager") is not None:
            return
        import json as _json
        try:
            p = self._state_path()
            if not p.exists():
                return
            data = _json.loads(p.read_text(encoding="utf-8"))
            positions = data.get("positions", {})
            if isinstance(positions, dict):
                for key, cfg in positions.items():
                    pos_id = int(key)
                    if pos_id not in self._trailing_configs:
                        self._trailing_configs[pos_id] = cfg
            original_sl = data.get("original_sl", {})
            if isinstance(original_sl, dict):
                for key, sl in original_sl.items():
                    pos_id = int(key)
                    if pos_id not in self._position_original_sl:
                        self._position_original_sl[pos_id] = float(sl)
        except Exception:
            pass

    def _debounce_save(self) -> None:
        save_timer = self.__dict__.get("_save_debounce")
        if self.__dict__.get("order_manager") is None and save_timer is not None:
            save_timer.start()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _get_selected_position(self) -> dict | None:
        row_idx = self.order_table.currentRow()
        if self._active_tab == "pending" or row_idx < 0 or row_idx >= len(self._positions):
            return None
        return self._positions[row_idx]

    def _get_selected_pending_order(self) -> dict | None:
        row_idx = self.order_table.currentRow()
        if (
            self._active_tab != "pending"
            or row_idx < 0
            or row_idx >= len(self._pending_orders)
        ):
            return None
        return self._pending_orders[row_idx]

    def _modify_selected_position(self) -> None:
        position = self._get_selected_position()
        if position is None:
            QMessageBox.information(
                self, "Sửa SL/TP", "Chọn một vị thế trong bảng trước."
            )
            return
        if self.order_manager is None:
            QMessageBox.warning(
                self, "Không hỗ trợ", "Order Management Service chưa sẵn sàng."
            )
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Sửa Stop Loss / Take Profit")
        layout = QVBoxLayout(dialog)
        sl_input = QLineEdit(str(float(position.get("sl", 0) or 0)))
        tp_input = QLineEdit(str(float(position.get("tp", 0) or 0)))
        for label, control in (("Stop Loss", sl_input), ("Take Profit", tp_input)):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addWidget(control, 1)
            layout.addLayout(row)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        submit = QPushButton("Gửi thay đổi")
        cancel = QPushButton("Hủy")
        submit.clicked.connect(dialog.accept)
        cancel.clicked.connect(dialog.reject)
        buttons.addWidget(submit)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            sl = float(sl_input.text().strip())
            tp = float(tp_input.text().strip())
        except ValueError:
            QMessageBox.warning(
                self, "Dữ liệu không hợp lệ", "SL và TP phải là số."
            )
            return
        future = self.order_manager.modify_position(
            int(position.get("position_id", 0)), sl=sl, tp=tp
        )
        if future is None:
            QMessageBox.warning(self, "Không hỗ trợ", "Không thể xếp hàng thao tác.")
            return
        self._pending_ui_operation = {
            "kind": "modify_position",
            "remaining": 1,
            "confirmed": 0,
            "partial": 0,
            "failed": 0,
        }

    def _partial_close_selected(self) -> None:
        position = self._get_selected_position()
        if position is None:
            QMessageBox.information(
                self, "Đóng một phần", "Chọn một vị thế trong bảng trước."
            )
            return
        if self.order_manager is None:
            QMessageBox.warning(
                self, "Không hỗ trợ", "Order Management Service chưa sẵn sàng."
            )
            return
        current_volume = float(position.get("volume", 0) or 0)
        dialog = QDialog(self)
        dialog.setWindowTitle("Đóng một phần vị thế")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"Volume đang mở: {current_volume:g}"))
        volume_input = QLineEdit(str(current_volume / 2))
        row = QHBoxLayout()
        row.addWidget(QLabel("Volume cần đóng"))
        row.addWidget(volume_input, 1)
        layout.addLayout(row)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        submit = QPushButton("Xác nhận")
        cancel = QPushButton("Hủy")
        submit.clicked.connect(dialog.accept)
        cancel.clicked.connect(dialog.reject)
        buttons.addWidget(submit)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            volume = float(volume_input.text().strip())
        except ValueError:
            volume = 0.0
        if volume <= 0 or volume >= current_volume:
            QMessageBox.warning(
                self,
                "Volume không hợp lệ",
                "Volume đóng một phần phải lớn hơn 0 và nhỏ hơn volume đang mở.",
            )
            return
        future = self.order_manager.close_position(
            int(position.get("position_id", 0)), volume=volume
        )
        if future is None:
            QMessageBox.warning(self, "Không hỗ trợ", "Không thể xếp hàng thao tác.")
            return
        self._pending_ui_operation = {
            "kind": "partial_close",
            "remaining": 1,
            "confirmed": 0,
            "partial": 0,
            "failed": 0,
        }

    def _cancel_selected_pending(self) -> None:
        order = self._get_selected_pending_order()
        if order is None:
            QMessageBox.information(
                self, "Hủy lệnh chờ", "Chọn một lệnh chờ trong bảng trước."
            )
            return
        order_id = int(order.get("order_id", 0) or 0)
        symbol = str(order.get("symbol", "--"))
        reply = QMessageBox.question(
            self,
            "Xác nhận hủy lệnh chờ",
            f"Hủy pending order {symbol} (ticket={order_id})?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self.order_manager is None:
            QMessageBox.warning(
                self, "Không hỗ trợ", "Order Management Service chưa sẵn sàng."
            )
            return
        future = self.order_manager.cancel_pending_order(order_id)
        if future is None:
            QMessageBox.warning(
                self, "Không hỗ trợ", "Broker không hỗ trợ hủy pending order."
            )
            return
        self._pending_ui_operation = {
            "kind": "cancel_pending",
            "remaining": 1,
            "confirmed": 0,
            "partial": 0,
            "failed": 0,
        }

    def _modify_selected_pending(self) -> None:
        order = self._get_selected_pending_order()
        if order is None:
            QMessageBox.information(
                self, "Sửa lệnh chờ", "Chọn một lệnh chờ trong bảng trước."
            )
            return
        if self.order_manager is None:
            QMessageBox.warning(
                self, "Không hỗ trợ", "Order Management Service chưa sẵn sàng."
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Sửa pending order")
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 16, 18, 16)
        inputs: dict[str, QLineEdit] = {}
        fields = (
            ("price", "Entry", order.get("price", 0)),
            ("sl", "Stop Loss", order.get("sl", 0)),
            ("tp", "Take Profit", order.get("tp", 0)),
            (
                "expiration",
                "Expiration (Unix time, 0 = GTC)",
                order.get("expiration_time", 0),
            ),
        )
        for key, label, value in fields:
            control = QLineEdit(str(value or 0))
            inputs[key] = control
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            row.addWidget(control, 1)
            layout.addLayout(row)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        save_button = QPushButton("Gửi thay đổi")
        cancel_button = QPushButton("Hủy")
        save_button.clicked.connect(dialog.accept)
        cancel_button.clicked.connect(dialog.reject)
        buttons.addWidget(save_button)
        buttons.addWidget(cancel_button)
        layout.addLayout(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            changes = {
                "price": float(inputs["price"].text().strip()),
                "sl": float(inputs["sl"].text().strip()),
                "tp": float(inputs["tp"].text().strip()),
                "expiration": int(inputs["expiration"].text().strip()),
            }
        except ValueError:
            QMessageBox.warning(
                self, "Dữ liệu không hợp lệ", "Entry/SL/TP/expiration phải là số."
            )
            return
        order_id = int(order.get("order_id", 0) or 0)
        future = self.order_manager.modify_pending_order(order_id, **changes)
        if future is None:
            QMessageBox.warning(
                self, "Không hỗ trợ", "Broker không hỗ trợ sửa pending order."
            )
            return
        self._pending_ui_operation = {
            "kind": "modify_pending",
            "remaining": 1,
            "confirmed": 0,
            "partial": 0,
            "failed": 0,
        }

    def _flatten_account(self) -> None:
        """Freeze and flatten the exact position + pending snapshot."""

        positions = tuple(dict(item) for item in self._positions)
        pending = tuple(dict(item) for item in self._pending_orders)
        if not positions and not pending:
            QMessageBox.information(
                self, "Flatten tài khoản", "Tài khoản không có lệnh để flatten."
            )
            return
        reply = QMessageBox.question(
            self,
            "⚠️ Xác nhận FLATTEN tài khoản",
            "Hành động này tác động toàn bộ snapshot tài khoản, gồm cả lệnh "
            "manual/EA khác.\n\n"
            f"Đóng positions: {len(positions)}\n"
            f"Hủy pending orders: {len(pending)}\n\n"
            "Các lệnh mở mới sau hộp thoại này sẽ không bị đưa vào target.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self.order_manager is None:
            QMessageBox.warning(
                self, "Không hỗ trợ", "Order Management Service chưa sẵn sàng."
            )
            return
        queued = 0
        for position in positions:
            ticket = int(position.get("position_id", 0) or 0)
            if ticket and self.order_manager.close_position(ticket) is not None:
                queued += 1
        for order in pending:
            ticket = int(order.get("order_id", 0) or 0)
            if ticket and self.order_manager.cancel_pending_order(ticket) is not None:
                queued += 1
        if queued == 0:
            QMessageBox.warning(
                self, "Không hỗ trợ", "Không có thao tác nào được xếp hàng."
            )
            return
        self._pending_ui_operation = {
            "kind": "flatten",
            "remaining": queued,
            "confirmed": 0,
            "partial": 0,
            "failed": 0,
        }

    def _close_selected(self) -> None:
        pos = self._get_selected_position()
        if not pos:
            QMessageBox.information(self, "Đóng lệnh", "Chọn một vị thế trong bảng trước.")
            return

        pos_id = int(pos.get("position_id", 0))
        symbol = str(pos.get("symbol", "--"))
        volume = float(pos.get("volume", 0))

        reply = QMessageBox.question(
            self, "Xác nhận đóng lệnh",
            f"Đóng vị thế {symbol} (ticket={pos_id}, vol={volume:.2f})?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if self.order_manager is not None:
            future = self.order_manager.close_position(pos_id)
            if future is None:
                QMessageBox.warning(
                    self, "Không hỗ trợ", "Không thể xếp hàng thao tác đóng lệnh."
                )
                return
            self._pending_ui_operation = {
                "kind": "close_selected",
                "remaining": 1,
                "confirmed": 0,
                "partial": 0,
                "failed": 0,
            }
            return

        QMessageBox.warning(
            self,
            "Không hỗ trợ",
            "Không đóng lệnh trực tiếp từ UI khi Order Management Service chưa sẵn sàng.",
        )

    def _close_all(self) -> None:
        if not self._positions:
            QMessageBox.information(self, "Đóng tất cả", "Không có vị thế nào đang mở.")
            return

        # Only one scope since 2026-08-16 (ALL): the bulk close always targets
        # every open position. Freeze the exact set before confirmation — a
        # position opened while the modal dialog is visible never joins it.
        targets = tuple(dict(position) for position in self._positions)
        if not targets:
            QMessageBox.information(
                self,
                "Đóng tất cả",
                "Không có vị thế nào đang hiển thị.",
            )
            return
        total_pl = sum(float(p.get("profit", 0) or 0) + float(p.get("swap", 0) or 0) + float(p.get("commission", 0) or 0) for p in targets)
        reply = QMessageBox.question(
            self, "Xác nhận đóng tất cả",
            f"Đóng toàn bộ {len(targets)} vị thế?\n"
            f"Tổng P/L hiện tại: {total_pl:+,.2f} {self._account_currency}".strip(),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if self.order_manager is not None:
            queued = 0
            for pos in targets:
                pos_id = int(pos.get("position_id", 0))
                if pos_id and self.order_manager.close_position(pos_id) is not None:
                    queued += 1
            if queued == 0:
                QMessageBox.warning(
                    self, "Không hỗ trợ", "Không thể xếp hàng thao tác đóng lệnh."
                )
                return
            self._pending_ui_operation = {
                "kind": "close_all",
                "remaining": queued,
                "confirmed": 0,
                "partial": 0,
                "failed": 0,
            }
            return

        QMessageBox.warning(
            self,
            "Không hỗ trợ",
            "Không đóng lệnh trực tiếp từ UI khi Order Management Service chưa sẵn sàng.",
        )

    def refresh_status(self) -> None:
        self.refresh_orders()
