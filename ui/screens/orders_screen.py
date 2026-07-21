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
        self._position_original_sl: dict[int, float] = {}  # position_id -> original SL (captured once, never overwritten)
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

        # Capture original SL for newly detected positions (once, never overwrite)
        for pos in self._positions:
            pos_id = int(pos.get("position_id", 0))
            if pos_id and pos_id not in self._position_original_sl:
                sl = float(pos.get("sl", 0) or 0)
                if sl > 0:
                    self._position_original_sl[pos_id] = sl

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

        dir_item = sitem("MUA" if is_buy else "BÁN")
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

        dir_item = sitem("MUA" if is_buy_type else "BÁN")
        dir_item.setForeground(buy_color if is_buy_type else sell_color)
        f = dir_item.font(); f.setBold(True); dir_item.setFont(f)
        table.setItem(idx, 1, dir_item)

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
        # Also clean up original SL entries for closed positions
        stale_sl = [pid for pid in self._position_original_sl if pid not in open_ids]
        for pid in stale_sl:
            del self._position_original_sl[pid]
        if stale or stale_sl:
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
        current_sl = float(pos.get("sl", 0) or 0)
        volume = float(pos.get("volume", 0))
        profit = float(pos.get("profit", 0) or 0) + float(pos.get("swap", 0) or 0)

        # ---- Fetch live Bid/Ask ----
        _dlg_bid = 0.0
        _dlg_ask = 0.0
        try:
            import MetaTrader5 as _mt5
            _tick = _mt5.symbol_info_tick(symbol)
            if _tick is not None:
                _dlg_bid = float(_tick.bid)
                _dlg_ask = float(_tick.ask)
        except Exception:
            pass
        current_price = _dlg_bid if side == "sell" else _dlg_ask if side == "buy" else 0.0

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

        try:
            light = self.settings_service.load().display.theme == "light"
        except Exception:
            light = False

        dlg = QDialog(self)
        dlg.setWindowTitle(f"🎯 Trailing Stop — {symbol} ({'MUA' if is_buy else 'BÁN'} {volume:.2f})")
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

        entry_price = float(pos.get("open_price", 0) or 0)

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
            p = _price_to_pips(abs(entry_price - cp), symbol)
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

        info_pl = labeled_value("P/L", f"${profit:+,.2f}")
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
            green = "#059669" if light else "#10b981"
            red = "#b91c1c" if light else "#f87171"

            if self._dlg_cp_label and cp > 0:
                self._dlg_cp_label.setText(f"{cp:.5f}")
                self._dlg_cp_label.setStyleSheet(f"font-weight:700; color:{green};")

            if self._dlg_pl_label:
                self._dlg_pl_label.setText(f"${prof:+,.2f}")
                self._dlg_pl_label.setStyleSheet(f"font-weight:700; color:{green if prof >= 0 else red};")

            if self._dlg_pips_label:
                self._dlg_pips_label.setText(f"{pips_signed:+.1f} pip")
                self._dlg_pips_label.setStyleSheet(f"font-weight:700; color:{green if pips_signed >= 0 else red};")

            if self._dlg_r_label:
                self._dlg_r_label.setText(f"{r_signed:+.2f}R")
                if r_signed >= 1.0:
                    r_c = green
                elif r_signed >= 0.5:
                    r_c = "#f59e0b"
                elif r_signed < 0:
                    r_c = red
                else:
                    r_c = green
                self._dlg_r_label.setStyleSheet(f"font-weight:700; color:{r_c};")

        _refresh_live_labels(current_price, profit, profit_pips_signed, r_multiple_signed)

        root.addWidget(summary_card)

        # 2. Settings card -- unified manual + AI
        settings_card = card("Cài đặt khoảng cách")
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

        initial_sl_raw = effective_initial_sl
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

        root.addWidget(settings_card)

        # 3. Preview card: BE + Trail (live update)
        preview_card = card("Xem trước")
        preview_card.layout().setContentsMargins(16, 10, 16, 10)
        preview_card.layout().setSpacing(5)

        # BE section
        self._dlg_be_title = QLabel("🎯 Break Even")
        self._dlg_be_title.setObjectName("CardDetail")
        be_font = self._dlg_be_title.font(); be_font.setBold(True); self._dlg_be_title.setFont(be_font)
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
        tr_font = self._dlg_trail_title.font(); tr_font.setBold(True); self._dlg_trail_title.setFont(tr_font)
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
                trail_pip = _price_to_pips(trail_price, symbol)
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
            green = "#059669" if light else "#10b981"
            orange = "#f59e0b"
            neutral = "#9ca3af"

            if be_already_done and sl_matches_be:
                self._dlg_be_status_label.setText("✅ Đã kích hoạt Break Even")
                self._dlg_be_status_label.setStyleSheet(f"color:{green};font-weight:700;")
                self._dlg_be_distance_label.setText("")
            elif be_already_done and not sl_matches_be:
                self._dlg_be_status_label.setText("⚠️ Break Even đã kích hoạt trước đó — SL hiện tại không còn ở vị trí BE")
                self._dlg_be_status_label.setStyleSheet(f"color:{orange};font-weight:700;")
                self._dlg_be_distance_label.setText("")
            elif dist <= 0:
                self._dlg_be_status_label.setText("🟢 Đã sẵn sàng kích hoạt Break Even")
                self._dlg_be_status_label.setStyleSheet(f"color:{green};font-weight:700;")
                self._dlg_be_distance_label.setText("")
            else:
                self._dlg_be_status_label.setText("🟡 Chưa kích hoạt Break Even")
                self._dlg_be_status_label.setStyleSheet(f"color:{orange};font-weight:700;")
                dist_color = orange if dist_pips < 3 else neutral
                self._dlg_be_distance_label.setText(f"Còn:  {dist_pips:.1f} pip")
                self._dlg_be_distance_label.setStyleSheet(f"color:{dist_color};font-weight:700;")

        _update_preview(default_pips)
        _update_be_live(current_price, current_sl)
        self._dlg_pip_spin.valueChanged.connect(_update_preview)
        root.addWidget(preview_card)

        # ---- Auto-refresh timer: update live data every 2s ----
        _live_timer = QTimer(dlg)
        _live_timer.setInterval(2000)

        def _on_live_tick():
            """Fetch fresh tick + position, update live labels and BE status."""
            try:
                import MetaTrader5 as _mt5
                _t = _mt5.symbol_info_tick(symbol)
                if _t is None:
                    return
                _cp = float(_t.bid) if side == "sell" else float(_t.ask)
                if _cp <= 0:
                    return

                # Re-read position for updated P/L and SL
                _positions = _mt5.positions_get(ticket=pos_id)
                if _positions and len(_positions) > 0:
                    _p = _positions[0]
                    _prof = float(getattr(_p, "profit", 0) or 0) + float(getattr(_p, "swap", 0) or 0)
                    _live_sl = float(getattr(_p, "sl", 0) or 0)
                else:
                    return

                _pips = _profit_pips(_cp)
                _r = _r_multiple(_cp)
                _refresh_live_labels(_cp, _prof, _pips, _r)
                _update_be_live(_cp, _live_sl)
            except Exception:
                pass

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

        if light:
            dlg.setStyleSheet("QDialog { background: #F4F1EA; }")
        else:
            dlg.setStyleSheet("QDialog { background: #1a1f2e; }")
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
        pip_m = 100.0 if "JPY" in symbol.upper() else 10000.0

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

            trail_mode = getattr(self, "_dlg_trail_mode", None) or "wide"
            be_trigger_price = 2.0 * entry_price - initial_sl

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

            # Tính lại ATR H1
            atr_h1 = float(cfg.get("atr_h1", 0) or 0)
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
