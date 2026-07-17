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
from services.mt5_service import MT5Service
from services.settings_service import SettingsService
from ui.screens.shared import action_button, card, page_header, labeled_value


# ------------------------------------------------------------------
# Trailing stop fallback formula
# ------------------------------------------------------------------
def suggest_trail_pips(symbol: str, atr_h4: float, regime: str, profit_pips: float) -> int:
    """Compute a suggested trailing stop distance in pips (no AI required)."""
    base_atr = max(atr_h4 or 0.0020, 0.0010) * _pip_multiplier(symbol)

    if regime in ("trend_up", "trend_down", "trending"):
        trail = base_atr * 0.8
    elif regime == "volatile":
        trail = base_atr * 0.5
    else:
        trail = base_atr * 0.6  # range / unknown

    if profit_pips > base_atr * 2:
        trail *= 0.7  # tighten when deep in profit

    return max(round(trail), 5)


def _pip_multiplier(symbol: str) -> float:
    """Return pip multiplier: 10000 for non-JPY, 100 for JPY pairs."""
    return 100.0 if "JPY" in symbol.upper() else 10000.0


def _pips_to_price(pips: int, symbol: str) -> float:
    return pips / _pip_multiplier(symbol)


def _price_to_pips(price_diff: float, symbol: str) -> float:
    return price_diff * _pip_multiplier(symbol)


class OrdersScreen(QWidget):
    def __init__(self, navigate=None, *, app=None) -> None:
        super().__init__()
        self.navigate = navigate
        self.app = app
        self.mt5 = app.mt5 if app else MT5Service()
        self.settings_service = app.settings_service if app else SettingsService()
        self._light = self._is_light_theme()
        self._active_tab = "positions"
        self._positions: list[dict] = []
        self._pending_orders: list[dict] = []
        self._trailing_configs: dict[int, dict] = {}  # key = position_id
        self.setObjectName("FormScreen")
        self._build_ui()
        self.refresh_orders()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(5000)
        self._refresh_timer.timeout.connect(self.refresh_orders)
        self._refresh_timer.start()

        self._trail_timer = QTimer(self)
        self._trail_timer.setInterval(1500)
        self._trail_timer.timeout.connect(self._trailing_tick)
        self._trail_timer.start()

        self._save_debounce = QTimer(self)
        self._save_debounce.setSingleShot(True)
        self._save_debounce.setInterval(2000)
        self._save_debounce.timeout.connect(self._save_trailing_state)
        self._load_trailing_state()

    def _is_light_theme(self) -> bool:
        try:
            return self.settings_service.load().display.theme == "light"
        except Exception:
            return False

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

        for card_widget in (self.balance_card, self.position_count_card, self.pending_count_card, self.pl_card, self.trail_count_card):
            card_widget.setMinimumHeight(50)
            card_layout = card_widget.layout()
            if card_layout:
                card_layout.setContentsMargins(10, 4, 10, 4)
                card_layout.setSpacing(2)
            val_lbl = card_widget.findChild(QLabel, "MiniStatValue")
            if val_lbl:
                val_lbl.setStyleSheet("padding-top: 1px; padding-bottom: 1px;")

        layout.addWidget(self.balance_card)
        layout.addWidget(self.position_count_card)
        layout.addWidget(self.pending_count_card)
        layout.addWidget(self.pl_card)
        layout.addWidget(self.trail_count_card)

        return container

    def _build_tab_bar(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(10)

        self.orders_tab_bar = QTabBar()
        self.orders_tab_bar.setStyleSheet("background: transparent; border: none;")
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
        table.setObjectName("EconTable")
        table.setColumnCount(11)
        table.setHorizontalHeaderLabels([
            "Mã", "Hướng", "KL", "Entry", "Hiện tại", "SL", "TP", "P/L", "R", "Trailing", ""
        ])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setWordWrap(True)
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(10, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(0, 105)
        table.setColumnWidth(1, 75)
        table.setColumnWidth(2, 65)
        table.setColumnWidth(3, 105)
        table.setColumnWidth(4, 105)
        table.setColumnWidth(5, 105)
        table.setColumnWidth(6, 105)
        table.setColumnWidth(7, 85)
        table.setColumnWidth(8, 65)
        table.setColumnWidth(10, 0)

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

        self.close_selected_btn = action_button("❌ Đóng lệnh đã chọn", primary=True, color="danger")
        self.close_selected_btn.setToolTip("Đóng vị thế đang chọn trong bảng")
        self.close_selected_btn.clicked.connect(self._close_selected)
        layout.addWidget(self.close_selected_btn)

        self.close_all_btn = action_button("❌ Đóng tất cả", primary=True, color="danger")
        self.close_all_btn.setToolTip("Đóng toàn bộ vị thế đang mở (có xác nhận)")
        self.close_all_btn.clicked.connect(self._close_all)
        layout.addWidget(self.close_all_btn)

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

    # ------------------------------------------------------------------
    # Data refresh
    # ------------------------------------------------------------------
    def refresh_orders(self) -> None:
        self._light = self._is_light_theme()
        try:
            balance = self.mt5.account_balance()
            if self.balance_label:
                self.balance_label.setText(f"${balance:,.2f}" if balance is not None else "--")
        except Exception:
            if getattr(self, "balance_label", None):
                self.balance_label.setText("--")

        self._positions = self.mt5.get_open_positions() if hasattr(self.mt5, "get_open_positions") else []
        self._pending_orders = self.mt5.get_pending_orders() if hasattr(self.mt5, "get_pending_orders") else []
        self._cleanup_trailing()

        if getattr(self, "position_count_label", None):
            self.position_count_label.setText(f"{len(self._positions)}")
        if getattr(self, "pending_count_label", None):
            self.pending_count_label.setText(f"{len(self._pending_orders)}")

        total_pl = sum(float(p.get("profit", 0) or 0) + float(p.get("swap", 0) or 0) + float(p.get("commission", 0) or 0) for p in self._positions)
        if getattr(self, "pl_label", None):
            self.pl_label.setText(f"${total_pl:+,.2f}")
            pl_color = "#059669" if self._light else "#10b981"
            if total_pl < 0:
                pl_color = "#b91c1c" if self._light else "#f87171"
            self.pl_label.setStyleSheet(f"font-weight:700;font-size:16px;color:{pl_color}; padding-top: 2px; padding-bottom: 2px;")

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
            self.close_selected_btn.setVisible(True)
            self.close_all_btn.setVisible(True)
            self.trail_btn.setVisible(True)
            # Show clear trail button only if selected position has trailing
            pos = self._get_selected_position()
            has_trail = bool(pos and int(pos.get("position_id", 0)) in self._trailing_configs)
            self.clear_trail_btn.setVisible(has_trail)
        else:
            data = self._pending_orders
            self.close_selected_btn.setVisible(False)
            self.close_all_btn.setVisible(False)
            self.trail_btn.setVisible(False)
            self.clear_trail_btn.setVisible(False)

        if not data:
            table.setRowCount(1)
            table.setSpan(0, 0, 1, table.columnCount())
            item = QTableWidgetItem("Không có lệnh nào.")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setForeground(QColor("#78716C" if self._light else "#94a3b8"))
            table.setItem(0, 0, item)
            table.setRowHeight(0, 40)
            return

        buy_color = QColor("#059669" if self._light else "#10b981")
        sell_color = QColor("#b91c1c" if self._light else "#f87171")
        neutral_fg = QColor("#4b5563" if self._light else "#9ca3af")

        table.setRowCount(len(data))
        for idx, row in enumerate(data):
            if self._active_tab == "positions":
                self._render_position_row(table, idx, row, buy_color, sell_color, neutral_fg)
            else:
                self._render_pending_row(table, idx, row, buy_color, sell_color, neutral_fg)
            table.setRowHeight(idx, 30)

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

        table.setItem(idx, 0, sitem(symbol))
        f = table.item(idx, 0).font(); f.setBold(True); table.item(idx, 0).setFont(f)

        dir_item = sitem("MUA" if is_buy else "BAN")
        dir_item.setForeground(buy_color if is_buy else sell_color)
        f = dir_item.font(); f.setBold(True); dir_item.setFont(f)
        table.setItem(idx, 1, dir_item)

        table.setItem(idx, 2, sitem(f"{float(row.get('volume', 0)):.2f}"))
        table.setItem(idx, 3, sitem(f"{float(row.get('open_price', 0)):.5f}"))
        table.setItem(idx, 4, sitem(f"{float(row.get('current_price', 0)):.5f}"))

        sl_val = float(row.get("sl", 0) or 0)
        sl_item = sitem(f"{sl_val:.5f}" if sl_val else "--")
        if sl_val: sl_item.setForeground(sell_color)
        table.setItem(idx, 5, sl_item)

        tp_val = float(row.get("tp", 0) or 0)
        tp_item = sitem(f"{tp_val:.5f}" if tp_val else "--")
        if tp_val: tp_item.setForeground(buy_color)
        table.setItem(idx, 6, tp_item)

        profit = float(row.get("profit", 0) or 0) + float(row.get("swap", 0) or 0) + float(row.get("commission", 0) or 0)
        pl_item = sitem(f"${profit:+,.2f}")
        pl_item.setForeground(buy_color if profit >= 0 else sell_color)
        table.setItem(idx, 7, pl_item)

        # R column: profit / risk
        open_p = float(row.get("open_price", 0) or row.get("price", 0) or 0)
        cur_p = float(row.get("current_price", 0) or 0)
        sl_for_r = float(row.get("sl", 0) or 0)
        cfg_r = self._trailing_configs.get(pos_id)
        if cfg_r:
            open_p = float(cfg_r.get("entry_price", open_p) or open_p)
            sl_for_r = float(cfg_r.get("initial_sl", sl_for_r) or sl_for_r)
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
            r_item.setForeground(QColor("#9ca3af"))
        table.setItem(idx, 8, r_item)

        # Trailing / BE status
        cfg = self._trailing_configs.get(pos_id)
        if cfg and cfg.get("enabled"):
            be_done = cfg.get("be_done", False)
            trail_mode = str(cfg.get("trail_mode", "wide"))
            if not be_done:
                trail_text = "⏳ Chờ BE"
                trail_color = QColor("#9ca3af")
            else:
                entry = float(cfg.get("entry_price", 0) or 0)
                current_sl_val = float(cfg.get("current_sl", 0) or 0)
                pip_m = float(cfg.get("pip_multiplier", 10000) or 10000)
                be_sl = entry + (2.0 / pip_m) if cfg.get("side") == "buy" else entry - (2.0 / pip_m)
                if abs(current_sl_val - be_sl) < (1.0 / pip_m):
                    trail_text = "✅ BE"
                    trail_color = QColor("#10b981")
                elif trail_mode == "tight":
                    trail_text = "🔒 Tight"
                    trail_color = QColor("#f59e0b")
                else:
                    trail_text = "🟢 Wide"
                    trail_color = QColor("#3b82f6")
        elif cfg and not cfg.get("enabled"):
            trail_text = "⏸️ Tạm dừng"
            trail_color = QColor("#9ca3af")
        else:
            trail_text = "--"
            trail_color = QColor("#9ca3af")
        trail_item = sitem(trail_text)
        if cfg:
            trail_item.setForeground(trail_color)
        table.setItem(idx, 9, trail_item)

    def _render_pending_row(self, table, idx, row, buy_color, sell_color, neutral_fg) -> None:
        def sitem(text, align=Qt.AlignmentFlag.AlignCenter):
            item = QTableWidgetItem(str(text))
            item.setTextAlignment(align)
            return item

        otype = str(row.get("type", ""))
        is_buy_type = "buy" in otype

        sym = sitem(str(row.get("symbol", "--")))
        f = sym.font(); f.setBold(True); sym.setFont(f)
        table.setItem(idx, 0, sym)

        type_labels = {"buy_limit": "BUY LIMIT", "sell_limit": "SELL LIMIT",
                       "buy_stop": "BUY STOP", "sell_stop": "SELL STOP"}
        type_item = sitem(type_labels.get(otype, otype.upper()))
        type_item.setForeground(buy_color if is_buy_type else sell_color)
        f = type_item.font(); f.setBold(True); type_item.setFont(f)
        table.setItem(idx, 1, type_item)

        table.setItem(idx, 2, sitem(f"{float(row.get('volume', 0)):.2f}"))
        table.setItem(idx, 3, sitem(f"{float(row.get('price', 0)):.5f}"))
        table.setItem(idx, 4, sitem("--"))

        sl_val = float(row.get("sl", 0) or 0)
        sl_item = sitem(f"{sl_val:.5f}" if sl_val else "--")
        if sl_val: sl_item.setForeground(sell_color)
        table.setItem(idx, 5, sl_item)

        tp_val = float(row.get("tp", 0) or 0)
        tp_item = sitem(f"{tp_val:.5f}" if tp_val else "--")
        if tp_val: tp_item.setForeground(buy_color)
        table.setItem(idx, 6, tp_item)

        table.setItem(idx, 7, sitem("--"))
        table.setItem(idx, 8, sitem("--"))
        table.setItem(idx, 9, sitem("--"))

    # ------------------------------------------------------------------
    # Trailing stop engine
    # ------------------------------------------------------------------
    def _cleanup_trailing(self) -> None:
        open_ids = {int(p.get("position_id", 0)) for p in self._positions}
        stale = [pid for pid in self._trailing_configs if pid not in open_ids]
        for pid in stale:
            del self._trailing_configs[pid]
        if stale:
            self._debounce_save()

    def _trailing_tick(self) -> None:
        """Called every 1.5s: update extreme price & adjust SL if needed."""
        if not hasattr(self.mt5, "modify_position_sltp"):
            return
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return

        for pos_id, cfg in list(self._trailing_configs.items()):
            if not cfg.get("enabled"):
                continue
            symbol = str(cfg.get("symbol", ""))
            side = str(cfg.get("side", ""))
            trail_pips = int(cfg.get("trail_pips", 20))

            try:
                tick = mt5.symbol_info_tick(symbol)
                if not tick:
                    continue
                current = float(tick.bid) if side == "sell" else float(tick.ask)
            except Exception:
                continue

            # --- BE (Breakeven) logic ---
            if not cfg.get("be_done"):
                be_trigger = cfg.get("be_trigger_price")
                entry_price = cfg.get("entry_price")
                if be_trigger is None or entry_price is None:
                    entry_price = float(cfg.get("entry_price", 0) or 0)
                    initial_sl = float(cfg.get("initial_sl", 0) or 0)
                    be_trigger = 2.0 * entry_price - initial_sl
                    cfg["be_trigger_price"] = be_trigger
                    cfg["entry_price"] = entry_price
                    cfg["initial_sl"] = initial_sl
                if entry_price and be_trigger:
                    triggered = (side == "buy" and current >= be_trigger) or \
                                (side == "sell" and current <= be_trigger)
                    if triggered:
                        pip_m = float(cfg.get("pip_multiplier", 10000) or 10000)
                        be_plus = 2.0 / pip_m
                        be_sl = entry_price + be_plus if side == "buy" else entry_price - be_plus
                        result = self.mt5.modify_position_sltp(pos_id, sl=be_sl)
                        if result.get("success"):
                            cfg["current_sl"] = be_sl
                        cfg["be_done"] = True
                        cfg["extreme_price"] = current
                        self._debounce_save()
                        continue

            if trail_pips <= 0:
                continue

            # --- ATR-based trail distance ---
            atr_h1 = float(cfg.get("atr_h1", 0) or 0)
            entry_price = float(cfg.get("entry_price", 0) or 0)
            initial_sl = float(cfg.get("initial_sl", 0) or 0)
            one_r = abs(entry_price - initial_sl) if entry_price and initial_sl else 0.0

            # Switch trail_mode when profit >= 2R (only for ATR modes, not fixed)
            trail_mode = str(cfg.get("trail_mode", "wide"))
            if trail_mode != "fixed" and one_r > 0:
                profit = (current - entry_price) if side == "buy" else (entry_price - current)
                if profit >= 2.0 * one_r and trail_mode != "tight":
                    cfg["trail_mode"] = "tight"
                    trail_mode = "tight"

            if trail_mode == "fixed":
                trail_price = _pips_to_price(trail_pips, symbol)
            elif atr_h1 > 0:
                multiplier = 2.5 if trail_mode == "wide" else 1.5
                trail_price = atr_h1 * multiplier
            else:
                trail_price = _pips_to_price(trail_pips, symbol)

            extreme = float(cfg.get("extreme_price", 0) or 0)
            if extreme == 0:
                extreme = current
                cfg["extreme_price"] = extreme

            if side == "buy":
                if current > extreme:
                    extreme = current
                    cfg["extreme_price"] = extreme
                new_sl = extreme - trail_price
            else:
                if current < extreme:
                    extreme = current
                    cfg["extreme_price"] = extreme
                new_sl = extreme + trail_price

            current_sl = float(cfg.get("current_sl", 0) or 0)
            if current_sl == 0:
                # First tick: read actual SL from MT5
                pos_info = mt5.positions_get(ticket=pos_id)
                if pos_info:
                    current_sl = float(getattr(pos_info[0], "sl", 0) or 0)
                    cfg["current_sl"] = current_sl

            should_update = (side == "buy" and new_sl > current_sl + trail_price * 0.2) or \
                            (side == "sell" and new_sl < current_sl - trail_price * 0.2)

            if should_update:
                result = self.mt5.modify_position_sltp(pos_id, sl=new_sl)
                if result.get("success"):
                    cfg["current_sl"] = new_sl

    def _show_trailing_dialog(self) -> None:
        pos = self._get_selected_position()
        if not pos:
            QMessageBox.information(self, "Trailing Stop", "Chọn một vị thế trong bảng trước.")
            return

        pos_id = int(pos.get("position_id", 0))
        symbol = str(pos.get("symbol", "--"))
        side = str(pos.get("side", ""))
        is_buy = side == "buy"
        current_price = float(pos.get("current_price", 0))
        current_sl = float(pos.get("sl", 0) or 0)
        volume = float(pos.get("volume", 0))
        profit = float(pos.get("profit", 0) or 0) + float(pos.get("swap", 0) or 0)

        existing = self._trailing_configs.get(pos_id)
        default_pips = existing.get("trail_pips", 20) if existing else 20

        try:
            light = self.settings_service.load().display.theme == "light"
        except Exception:
            light = False

        dlg = QDialog(self)
        dlg.setWindowTitle(f"🎯 Trailing Stop — {symbol} ({'MUA' if is_buy else 'BAN'} {volume:.2f})")
        dlg.setMinimumWidth(650)
        dlg.setObjectName("AnalysisDetailDialog")

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
        summary_layout = QHBoxLayout()
        summary_layout.setSpacing(20)
        
        entry_price = current_price - (profit / (volume * _pip_multiplier(symbol))) if volume > 0 else 0
        
        info_sym = labeled_value("MÃ GIAO DỊCH", symbol)
        info_dir = labeled_value("HƯỚNG", "MUA" if is_buy else "BÁN")
        info_vol = labeled_value("KHỐI LƯỢNG", f"{volume:.2f}")
        info_entry = labeled_value("ENTRY", f"{entry_price:.5f}")
        info_sl = labeled_value("SL HIỆN TẠI", f"{current_sl:.5f}" if current_sl else "Chưa đặt")
        info_pl = labeled_value("P/L", f"${profit:+,.2f}")
        
        pl_val = info_pl.findChild(QLabel, "MiniStatValue")
        if pl_val:
            pl_color = "#059669" if light else "#10b981"
            if profit < 0:
                pl_color = "#b91c1c" if light else "#f87171"
            pl_val.setStyleSheet(f"font-weight:700; color:{pl_color};")
            
        dir_val = info_dir.findChild(QLabel, "MiniStatValue")
        if dir_val:
            dir_color = "#059669" if light and is_buy else "#10b981" if is_buy else "#dc2626" if light else "#ef4444"
            dir_val.setStyleSheet(f"font-weight:700; color:{dir_color};")
            
        summary_layout.addWidget(info_sym)
        summary_layout.addWidget(info_dir)
        summary_layout.addWidget(info_vol)
        summary_layout.addWidget(info_entry)
        summary_layout.addWidget(info_sl)
        summary_layout.addWidget(info_pl)
        summary_layout.addStretch()
        
        summary_card.layout().addLayout(summary_layout)
        root.addWidget(summary_card)

        # 2. Settings card -- unified manual + AI
        settings_card = card("Cai dat khoang cach")
        settings_card.layout().setContentsMargins(16, 12, 16, 12)
        settings_card.layout().setSpacing(10)

        # Cache ATR H1 once for preview
        _dlg_atr_h1 = 0.0
        try:
            import MetaTrader5 as _mt5
            _rates = _mt5.copy_rates_from_pos(symbol, _mt5.TIMEFRAME_H1, 0, 30)
            if _rates is not None and len(_rates) >= 14:
                _highs = [float(r[2]) for r in _rates[-14:]]
                _lows = [float(r[3]) for r in _rates[-14:]]
                _closes = [float(r[4]) for r in _rates[-15:-1]]
                _trs = []
                for _i in range(14):
                    _trs.append(max(_highs[_i] - _lows[_i], abs(_highs[_i] - _closes[_i]), abs(_lows[_i] - _closes[_i])))
                _dlg_atr_h1 = sum(_trs) / len(_trs)
        except Exception:
            pass

        entry_price = float(pos.get("open_price", 0) or pos.get("price", 0) or 0)
        initial_sl_raw = current_sl if current_sl > 0 else float(pos.get("sl", 0) or 0)
        pip_m = 100.0 if "JPY" in symbol.upper() else 10000.0

        # Row 0: Trail mode radio buttons
        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)
        mode_row.addWidget(QLabel("Chế độ:"))
        self._dlg_mode_group = QButtonGroup(dlg)
        self._dlg_mode_wide = QRadioButton("Wide (2.5× ATR)")
        self._dlg_mode_tight = QRadioButton("Tight (1.5× ATR)")
        self._dlg_mode_fixed = QRadioButton("Cố định (pip)")
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
                self._dlg_ai_trail_mode = "wide"
            elif self._dlg_mode_tight.isChecked():
                self._dlg_ai_trail_mode = "tight"
            else:
                self._dlg_ai_trail_mode = "fixed"
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
        self._dlg_pip_spin.setMinimumHeight(32)
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

        # Row 2: AI button + compact response area
        ai_row = QHBoxLayout()
        ai_row.setSpacing(8)
        self._dlg_ai_refresh_btn = action_button("🤖 AI gợi ý", primary=True, color="info")
        self._dlg_ai_refresh_btn.setToolTip("Gọi DeepSeek/Gemini để nhận gợi ý trailing stop")
        self._dlg_ai_refresh_btn.clicked.connect(lambda: self._ai_suggest_trail(
            symbol, side, current_price, pos, light, dlg,
        ))
        ai_row.addWidget(self._dlg_ai_refresh_btn)
        self._dlg_ai_label = QLabel("")
        self._dlg_ai_label.setObjectName("CardDetail")
        self._dlg_ai_label.setWordWrap(True)
        self._dlg_ai_label.setMinimumHeight(20)
        ai_row.addWidget(self._dlg_ai_label, 1)
        settings_card.layout().addLayout(ai_row)

        # Row 3: AI reasoning text box
        self._dlg_ai_text = QTextEdit()
        self._dlg_ai_text.setObjectName("ReadonlyText")
        self._dlg_ai_text.setReadOnly(True)
        self._dlg_ai_text.setMinimumHeight(80)
        self._dlg_ai_text.setMaximumHeight(120)
        self._dlg_ai_text.setPlaceholderText("Bấm '🤖 AI gợi ý' để nhận phân tích từ AI...")
        settings_card.layout().addWidget(self._dlg_ai_text)

        root.addWidget(settings_card)

        # 3. Preview card: BE + Trail distance (live update with spinbox)
        preview_card = card("Xem trước BE + Trail")
        preview_card.layout().setContentsMargins(16, 10, 16, 10)
        preview_card.layout().setSpacing(4)
        self._dlg_be_label = QLabel("")
        self._dlg_be_label.setObjectName("CardDetail")
        self._dlg_be_label.setWordWrap(True)
        self._dlg_trail_label = QLabel("")
        self._dlg_trail_label.setObjectName("CardDetail")
        self._dlg_trail_label.setWordWrap(True)
        preview_card.layout().addWidget(self._dlg_be_label)
        preview_card.layout().addWidget(self._dlg_trail_label)

        def _update_preview(pips_val=None):
            if pips_val is None:
                pips_val = self._dlg_pip_spin.value()
            # BE preview
            be_trigger = 2.0 * entry_price - initial_sl_raw if entry_price and initial_sl_raw else 0
            be_sl = entry_price + (2.0 / pip_m) if is_buy else entry_price - (2.0 / pip_m)
            if be_trigger:
                self._dlg_be_label.setText(
                    f"BE sẽ dời về: {be_sl:.5f} (khi giá chạm {be_trigger:.5f})"
                )
            else:
                self._dlg_be_label.setText("BE: chưa đủ dữ liệu entry/SL")
            # Trail distance preview
            trail_price = _pips_to_price(pips_val, symbol) if not _dlg_atr_h1 else (
                _dlg_atr_h1 * (2.5 if getattr(self, "_dlg_ai_trail_mode", None) == "wide" else 1.5)
            )
            if _dlg_atr_h1 > 0:
                mode = getattr(self, "_dlg_ai_trail_mode", None) or "wide"
                mult = 2.5 if mode == "wide" else 1.5
                trail_price = _dlg_atr_h1 * mult
                trail_pip = _price_to_pips(trail_price, symbol)
                self._dlg_trail_label.setText(
                    f"Khoảng cách trail: {trail_price:.5f} ({trail_pip:.0f} pip) — ATR {mode}"
                )
            else:
                trail_pip = pips_val
                self._dlg_trail_label.setText(
                    f"Khoảng cách trail: {pips_val} pip (thủ công, không có ATR)"
                )

        _update_preview(default_pips)
        self._dlg_pip_spin.valueChanged.connect(_update_preview)
        root.addWidget(preview_card)

        # --- Buttons ---
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        if existing and existing.get("enabled"):
            disable_btn = action_button("⏹️ Tắt Trailing Stop", primary=True, color="danger")
            disable_btn.clicked.connect(lambda: self._toggle_trailing(pos_id, False, dlg))
            btn_layout.addWidget(disable_btn)
        else:
            enable_btn = action_button("✅ Bật Trailing Stop", primary=True)
            enable_btn.clicked.connect(lambda: self._apply_trailing(pos_id, symbol, side, dlg))
            btn_layout.addWidget(enable_btn)

        close_btn = action_button("❌ Đóng", primary=False, color="danger")
        close_btn.clicked.connect(dlg.accept)
        btn_layout.addWidget(close_btn)
        
        root.addLayout(btn_layout)

        if light:
            dlg.setStyleSheet("QDialog { background: #F4F1EA; }")
        else:
            dlg.setStyleSheet("QDialog { background: #1a1f2e; }")
        dlg.exec()

    def _apply_trailing(self, pos_id: int, symbol: str, side: str, dlg: QDialog) -> None:
        trail_pips = self._dlg_pip_spin.value()
        pos = self._get_selected_position()
        entry_price = float(pos.get("open_price", 0) or pos.get("price", 0) or 0) if pos else 0.0
        initial_sl = float(pos.get("sl", 0) or 0) if pos else 0.0
        pip_multiplier = 100.0 if "JPY" in symbol.upper() else 10000.0
        if side == "buy":
            be_trigger_price = 2.0 * entry_price - initial_sl
        else:
            be_trigger_price = 2.0 * entry_price - initial_sl
        trail_mode = getattr(self, "_dlg_ai_trail_mode", None) or "wide"
        # Lấy ATR H1 thực từ MT5
        atr_h1 = 0.0
        try:
            import MetaTrader5 as mt5
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 30)
            if rates is not None and len(rates) >= 14:
                highs = [float(r[2]) for r in rates[-14:]]
                lows = [float(r[3]) for r in rates[-14:]]
                closes = [float(r[4]) for r in rates[-15:-1]]
                trs = []
                for i in range(14):
                    trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i]), abs(lows[i] - closes[i])))
                atr_h1 = sum(trs) / len(trs)
        except Exception:
            pass
        self._trailing_configs[pos_id] = {
            "position_id": pos_id,
            "symbol": symbol,
            "side": side,
            "enabled": True,
            "trail_pips": trail_pips,
            "extreme_price": 0.0,
            "current_sl": 0.0,
            "be_done": False,
            "be_trigger_price": be_trigger_price,
            "entry_price": entry_price,
            "initial_sl": initial_sl,
            "atr_h1": atr_h1,
            "trail_mode": trail_mode,
            "pip_multiplier": pip_multiplier,
        }
        dlg.accept()
        self._debounce_save()
        self._render_table()

    def _toggle_trailing(self, pos_id: int, enabled: bool, dlg: QDialog) -> None:
        cfg = self._trailing_configs.get(pos_id)
        if cfg:
            cfg["enabled"] = enabled
            if not enabled:
                cfg["extreme_price"] = 0.0
                cfg["current_sl"] = 0.0
        dlg.accept()
        self._debounce_save()
        self._render_table()

    def auto_enable_tracking(self, pos_id: int, symbol: str, side: str,
                             entry: float, sl: float, atr_h1: float) -> None:
        pip_multiplier = 100.0 if "JPY" in symbol.upper() else 10000.0
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
        if pos_id in self._trailing_configs:
            del self._trailing_configs[pos_id]
            self._debounce_save()
        self._render_table()

    def _update_clear_trail_visibility(self) -> None:
        pos = self._get_selected_position()
        has_trail = bool(pos and int(pos.get("position_id", 0)) in self._trailing_configs)
        self.clear_trail_btn.setVisible(has_trail)

    def _ai_suggest_trail(self, symbol: str, side: str, current_price: float,
                          pos: dict, light: bool, dlg: QDialog) -> None:
        """Call AI for trailing stop suggestion, fallback to formula."""
        self._dlg_ai_refresh_btn.setEnabled(False)
        self._dlg_ai_refresh_btn.setText("⏳ Đang gọi AI...")
        QApplication.processEvents()

        entry_price = float(pos.get("open_price", 0))
        # Signed profit: positive = in profit, negative = in loss
        if side == "buy":
            profit_pips = _price_to_pips(current_price - entry_price, symbol)
        else:
            profit_pips = _price_to_pips(entry_price - current_price, symbol)
        regime = "unknown"

        # Try to get ATR from MT5
        atr_h4 = 0.0
        try:
            import MetaTrader5 as mt5
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 30)
            if rates is not None and len(rates) >= 14:
                highs = [float(r[2]) for r in rates[-14:]]
                lows = [float(r[3]) for r in rates[-14:]]
                closes = [float(r[4]) for r in rates[-15:-1]]
                trs = []
                for i in range(14):
                    trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i]), abs(lows[i] - closes[i])))
                atr_h4 = sum(trs) / len(trs)
        except Exception:
            pass

        # Try AI first, fallback to formula
        ai_result = None
        ai_error = ""
        try:
            settings = self.settings_service.load()
            active = settings.ai.active_provider()
            if active and (active.api_key or active.api_key_ref):
                from services.ai_service import AIService, AIProviderConfig

                ai_config = AIProviderConfig(
                    provider=active.provider,
                    model=active.model,
                    api_key=active.api_key,
                )
                ai = AIService(ai_config)
                atr_h4_pips = _price_to_pips(atr_h4, symbol) if atr_h4 > 0 else "N/A"
                profit_sign = "+" if profit_pips >= 0 else ""

                # Get additional context: ATR H1, spread
                atr_h1 = 0.0
                spread_pips = "N/A"
                try:
                    import MetaTrader5 as mt5
                    rates_h1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 30)
                    if rates_h1 is not None and len(rates_h1) >= 14:
                        highs = [float(r[2]) for r in rates_h1[-14:]]
                        lows = [float(r[3]) for r in rates_h1[-14:]]
                        closes = [float(r[4]) for r in rates_h1[-15:-1]]
                        trs = []
                        for i in range(14):
                            trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i]), abs(lows[i] - closes[i])))
                        atr_h1 = sum(trs) / len(trs)
                    info = mt5.symbol_info(symbol)
                    if info:
                        spread_pips = str(round((info.ask - info.bid) / (0.0001 if "JPY" not in symbol.upper() else 0.01), 1))
                except Exception:
                    pass
                atr_h1_pips = _price_to_pips(atr_h1, symbol) if atr_h1 > 0 else "N/A"

                # Volatility regime
                if atr_h4 > 0:
                    vol_ratio = atr_h1 / atr_h4 if atr_h1 > 0 else 1.0
                    if vol_ratio > 1.3:
                        vol_regime = "cao (H1 ATR > 1.3x H4 ATR)"
                    elif vol_ratio < 0.7:
                        vol_regime = "thấp (H1 ATR < 0.7x H4 ATR)"
                    else:
                        vol_regime = "bình thường"
                else:
                    vol_regime = "không xác định"

                prompt = (
                    f"Bạn là chuyên gia quản lý rủi ro Forex. Phân tích vị thế sau và đề xuất "
                    f"khoảng cách trailing stop tối ưu:\n\n"
                    f"- Mã: {symbol}\n"
                    f"- Hướng: {side.upper()}\n"
                    f"- Entry: {entry_price:.5f}\n"
                    f"- Giá hiện tại: {current_price:.5f}\n"
                    f"- Lợi nhuận hiện tại: {profit_sign}{profit_pips:.0f} pip\n"
                    f"- ATR(H4): {atr_h4_pips} pip\n"
                    f"- ATR(H1): {atr_h1_pips} pip\n"
                    f"- Volatility regime: {vol_regime}\n"
                    f"- Spread: {spread_pips} pip\n\n"
                    f"Trả lời CHỈ một dòng JSON, không thêm gì khác:\n"
                    f'{{"trail_pips":<số pip>,"confidence":"high/medium/low","trail_mode":"wide/tight","reason":"<lý do tiếng Việt>"}}'
                )
                raw = ai.analyze(prompt, max_tokens=500)

                # Parse JSON from response
                import json as _json

                trail_pips = None
                confidence = "medium"
                trail_mode = "wide"
                reason = ""

                # Clean response: strip markdown fences, collapse whitespace
                json_text = raw.strip()
                for fence in ("```json", "```"):
                    json_text = json_text.removeprefix(fence).removesuffix(fence).strip()
                json_text = " ".join(json_text.split())

                # Extract and fix JSON
                import re
                start = json_text.find("{")
                end = json_text.rfind("}")
                if start >= 0 and end > start:
                    candidate = json_text[start:end + 1]
                    # Fix common AI JSON mistakes
                    candidate = re.sub(r",\s*}", "}", candidate)
                    candidate = re.sub(r",\s*\]", "]", candidate)
                    try:
                        parsed = _json.loads(candidate)
                        trail_pips = int(parsed.get("trail_pips", 0) or 0)
                        confidence = str(parsed.get("confidence", "medium")).lower()
                        trail_mode = str(parsed.get("trail_mode", "wide")).lower()
                        reason = str(parsed.get("reason", ""))
                    except (_json.JSONDecodeError, ValueError):
                        pass

                # Regex fallback: extract number near trail/pip
                if not trail_pips:
                    nums = re.findall(r"(?<!\d)(\d{1,3})(?!\d)", raw)
                    if nums:
                        trail_pips = int(nums[0])
                        reason = "(số từ AI)"

                if trail_pips and trail_pips > 0:
                    ai_result = {"trail_pips": trail_pips, "confidence": confidence,
                                 "trail_mode": trail_mode, "reason": reason}
                else:
                    ai_error = raw[:150].replace("\n", " ") if raw else "(AI không trả về kết quả)"
            else:
                ai_error = "Chưa cấu hình API key"
        except Exception as exc:
            ai_error = str(exc)[:120]

        if ai_result and ai_result.get("trail_pips"):
            trail = int(ai_result["trail_pips"])
            confidence = str(ai_result.get("confidence", "medium"))
            trail_mode = str(ai_result.get("trail_mode", "wide"))
            reason = str(ai_result.get("reason", ""))
            self._dlg_ai_trail_mode = trail_mode
            conf_icon = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(confidence, "🟡")
            mode_text = {"wide": "rộng", "tight": "chặt"}.get(trail_mode, trail_mode)
            self._dlg_ai_label.setText(
                f"🧠 AI gợi ý: {trail} pip — trail {mode_text} ({conf_icon} {confidence.upper()})"
            )
            self._dlg_ai_text.setMarkdown(
                f"**AI gợi ý: {trail} pip** — trail {mode_text} ({conf_icon} {confidence.upper()})\n\n{reason}"
            )
        else:
            trail = suggest_trail_pips(symbol, atr_h4, regime, profit_pips)
            self._dlg_ai_trail_mode = None
            note = ai_error if ai_error else "AI không khả dụng"
            self._dlg_ai_label.setText(f"📐 Công thức: {trail} pip")
            self._dlg_ai_text.setPlainText(
                f"📐 Công thức: {trail} pip\n\n"
                f"AI không trả về kết quả hợp lệ. Dùng công thức tính từ ATR.\n"
                f"Phản hồi thô từ AI: {note}"
            )

        self._dlg_pip_spin.setValue(trail)
        self._dlg_ai_refresh_btn.setText("🤖 AI gợi ý")
        self._dlg_ai_refresh_btn.setEnabled(True)

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
        import json as _json
        try:
            if not self._trailing_configs:
                p = self._state_path()
                if p.exists():
                    p.unlink()
                return
            data = {"positions": {str(k): v for k, v in self._trailing_configs.items()}}
            self._state_path().write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load_trailing_state(self) -> None:
        import json as _json
        try:
            p = self._state_path()
            if not p.exists():
                return
            data = _json.loads(p.read_text(encoding="utf-8"))
            positions = data.get("positions", {})
            if not isinstance(positions, dict):
                return
            for key, cfg in positions.items():
                pos_id = int(key)
                if pos_id not in self._trailing_configs:
                    self._trailing_configs[pos_id] = cfg
        except Exception:
            pass

    def _debounce_save(self) -> None:
        if hasattr(self, "_save_debounce"):
            self._save_debounce.start()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _get_selected_position(self) -> dict | None:
        row_idx = self.order_table.currentRow()
        if self._active_tab == "pending" or row_idx < 0 or row_idx >= len(self._positions):
            return None
        return self._positions[row_idx]

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

        if hasattr(self.mt5, "close_position"):
            result = self.mt5.close_position(pos_id)
            # Clean up trailing config
            self._trailing_configs.pop(pos_id, None)
            if result.get("success"):
                QMessageBox.information(self, "Thành công", f"Đã đóng {symbol}.\n{result.get('message', '')}")
            else:
                QMessageBox.warning(self, "Thất bại", f"Không thể đóng {symbol}:\n{result.get('message', '')}")
        else:
            QMessageBox.warning(self, "Không hỗ trợ", "Data provider không hỗ trợ đóng lệnh.")
        self.refresh_orders()

    def _close_all(self) -> None:
        if not self._positions:
            QMessageBox.information(self, "Đóng tất cả", "Không có vị thế nào đang mở.")
            return

        total_pl = sum(float(p.get("profit", 0) or 0) + float(p.get("swap", 0) or 0) + float(p.get("commission", 0) or 0) for p in self._positions)
        reply = QMessageBox.question(
            self, "Xác nhận đóng tất cả",
            f"Đóng toàn bộ {len(self._positions)} vị thế?\nTổng P/L hiện tại: ${total_pl:+,.2f}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if not hasattr(self.mt5, "close_position"):
            QMessageBox.warning(self, "Không hỗ trợ", "Data provider không hỗ trợ đóng lệnh.")
            return

        closed = 0
        failed = 0
        for pos in self._positions:
            pos_id = int(pos.get("position_id", 0))
            if not pos_id:
                continue
            result = self.mt5.close_position(pos_id)
            self._trailing_configs.pop(pos_id, None)
            if result.get("success"):
                closed += 1
            else:
                failed += 1

        msg = f"Đã đóng: {closed}"
        if failed:
            msg += f"\nThất bại: {failed}"
        QMessageBox.information(self, "Kết quả đóng tất cả", msg)
        self.refresh_orders()

    def refresh_status(self) -> None:
        self.refresh_orders()
