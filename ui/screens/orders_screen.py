from __future__ import annotations

from datetime import datetime, timezone
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
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
        self.data_provider = app.data_provider if app else MT5Service()
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
            "Theo dõi và quản lý các vị thế đang mở, lệnh chờ, đóng lệnh, trailing stop.",
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

        self.balance_card = labeled_value("BALANCE", "--")
        self.balance_label = self.balance_card.findChild(QLabel, "MiniStatValue")

        self.position_count_card = labeled_value("LỆNH MỞ", "0")
        self.position_count_label = self.position_count_card.findChild(QLabel, "MiniStatValue")

        self.pending_count_card = labeled_value("LỆNH CHỜ", "0")
        self.pending_count_label = self.pending_count_card.findChild(QLabel, "MiniStatValue")

        self.pl_card = labeled_value("P/L", "--")
        self.pl_label = self.pl_card.findChild(QLabel, "MiniStatValue")

        self.trail_count_card = labeled_value("TRAILING", "0")
        self.trail_count_label = self.trail_count_card.findChild(QLabel, "MiniStatValue")

        for card_widget in (self.balance_card, self.position_count_card, self.pending_count_card, self.pl_card, self.trail_count_card):
            card_widget.setMinimumHeight(62)
            card_layout = card_widget.layout()
            if card_layout:
                card_layout.setContentsMargins(14, 8, 14, 8)
                card_layout.setSpacing(4)
            val_lbl = card_widget.findChild(QLabel, "MiniStatValue")
            if val_lbl:
                val_lbl.setStyleSheet("padding-top: 2px; padding-bottom: 2px;")

        layout.addWidget(self.balance_card)
        layout.addWidget(self.position_count_card)
        layout.addWidget(self.pending_count_card)
        layout.addWidget(self.pl_card)
        layout.addWidget(self.trail_count_card)

        return container

    def _build_tab_bar(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(4)
        self.tab_buttons: dict[str, QPushButton] = {}
        for tab_key, tab_label in [("positions", "Vị thế đang mở"), ("pending", "Lệnh chờ")]:
            btn = QPushButton(tab_label)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, k=tab_key: self._switch_tab(k))
            self.tab_buttons[tab_key] = btn
            layout.addWidget(btn)
        layout.addStretch(1)
        self._update_tab_styles()
        return layout

    def _build_order_table(self) -> QTableWidget:
        table = QTableWidget()
        table.setObjectName("EconTable")
        table.setColumnCount(10)
        table.setHorizontalHeaderLabels([
            "Mã", "Hướng", "KL", "Entry", "Hiện tại", "SL", "TP", "P/L", "Trailing", ""
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
        header.setStretchLastSection(True)
        table.setColumnWidth(0, 80)
        table.setColumnWidth(1, 60)
        table.setColumnWidth(2, 55)
        table.setColumnWidth(3, 85)
        table.setColumnWidth(4, 85)
        table.setColumnWidth(5, 85)
        table.setColumnWidth(6, 85)
        table.setColumnWidth(7, 90)
        table.setColumnWidth(8, 90)

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
    def _switch_tab(self, tab_key: str) -> None:
        self._active_tab = tab_key
        self._update_tab_styles()
        self._render_table()

    def _update_tab_styles(self) -> None:
        active_bg = "#D94625" if self._light else "#ea580c"
        active_hover = "#E0533C" if self._light else "#f97316"
        inactive_fg = "#4b5563" if self._light else "#9ca3af"
        inactive_border = "#d1d5db" if self._light else "#4b5563"
        inactive_hover_bg = "#fce8e5" if self._light else "#2c1910"
        inactive_hover_fg = "#D94625" if self._light else "#ea580c"
        inactive_hover_border = "#D94625" if self._light else "#ea580c"

        active_style = (
            f"QPushButton {{ font-size:12px; font-weight:700; padding:6px 14px;"
            f"  background:{active_bg}; color:#ffffff; border:none; border-radius:6px; }}"
            f"QPushButton:hover {{ background:{active_hover}; }}"
        )
        inactive_style = (
            f"QPushButton {{ font-size:12px; font-weight:500; padding:6px 14px;"
            f"  background:transparent; color:{inactive_fg};"
            f"  border:1px solid {inactive_border}; border-radius:6px; }}"
            f"QPushButton:hover {{ background:{inactive_hover_bg};"
            f"  color:{inactive_hover_fg}; border:1px solid {inactive_hover_border}; }}"
        )
        for key, btn in self.tab_buttons.items():
            if key == self._active_tab:
                btn.setStyleSheet(active_style)
                btn.setChecked(True)
            else:
                btn.setStyleSheet(inactive_style)
                btn.setChecked(False)

    # ------------------------------------------------------------------
    # Data refresh
    # ------------------------------------------------------------------
    def refresh_orders(self) -> None:
        self._light = self._is_light_theme()
        try:
            balance = self.data_provider.account_balance()
            if self.balance_label:
                self.balance_label.setText(f"${balance:,.2f}" if balance is not None else "--")
        except Exception:
            if getattr(self, "balance_label", None):
                self.balance_label.setText("--")

        self._positions = self.data_provider.get_open_positions() if hasattr(self.data_provider, "get_open_positions") else []
        self._pending_orders = self.data_provider.get_pending_orders() if hasattr(self.data_provider, "get_pending_orders") else []
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

        # Trailing status
        cfg = self._trailing_configs.get(pos_id)
        if cfg and cfg.get("enabled"):
            trail_text = f"🟢 {cfg.get('trail_pips', 0)}pip"
        elif cfg and not cfg.get("enabled"):
            trail_text = "⏸️ Tạm dừng"
        else:
            trail_text = "--"
        trail_item = sitem(trail_text)
        if cfg and cfg.get("enabled"):
            trail_item.setForeground(buy_color)
        table.setItem(idx, 8, trail_item)

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

    # ------------------------------------------------------------------
    # Trailing stop engine
    # ------------------------------------------------------------------
    def _cleanup_trailing(self) -> None:
        open_ids = {int(p.get("position_id", 0)) for p in self._positions}
        stale = [pid for pid in self._trailing_configs if pid not in open_ids]
        for pid in stale:
            del self._trailing_configs[pid]

    def _trailing_tick(self) -> None:
        """Called every 1.5s: update extreme price & adjust SL if needed."""
        if not hasattr(self.data_provider, "modify_position_sltp"):
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
            if trail_pips <= 0:
                continue

            try:
                tick = mt5.symbol_info_tick(symbol)
                if not tick:
                    continue
                current = float(tick.bid) if side == "sell" else float(tick.ask)
            except Exception:
                continue

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
                result = self.data_provider.modify_position_sltp(pos_id, sl=new_sl)
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

        # Row 1: spinbox + presets
        pip_layout = QHBoxLayout()
        pip_layout.setSpacing(8)
        self._dlg_pip_spin = QSpinBox()
        self._dlg_pip_spin.setRange(5, 200)
        self._dlg_pip_spin.setValue(default_pips)
        self._dlg_pip_spin.setSuffix(" pip")
        self._dlg_pip_spin.setMinimumWidth(100)
        self._dlg_pip_spin.setMinimumHeight(32)
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

        close_btn = action_button("❌ Đóng")
        active_bg = "#D94625" if light else "#ea580c"
        close_btn.setStyleSheet(
            f"QPushButton {{ font-size:12px; font-weight:500; padding:0 16px;"
            f"  background:transparent; color:{'#4b5563' if light else '#9ca3af'};"
            f"  border:1px solid {'#d1d5db' if light else '#4b5563'};"
            f"  border-radius:6px; min-height:24px; max-height:24px; }}"
            f"QPushButton:hover {{ background:{'#fce8e5' if light else '#2c1910'};"
            f"  color:{active_bg}; border:1px solid {active_bg}; }}"
        )
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
        self._trailing_configs[pos_id] = {
            "position_id": pos_id,
            "symbol": symbol,
            "side": side,
            "enabled": True,
            "trail_pips": trail_pips,
            "extreme_price": 0.0,
            "current_sl": 0.0,
        }
        dlg.accept()
        self._render_table()

    def _toggle_trailing(self, pos_id: int, enabled: bool, dlg: QDialog) -> None:
        cfg = self._trailing_configs.get(pos_id)
        if cfg:
            cfg["enabled"] = enabled
            if not enabled:
                cfg["extreme_price"] = 0.0
                cfg["current_sl"] = 0.0
        dlg.accept()
        self._render_table()

    def _clear_trailing(self) -> None:
        pos = self._get_selected_position()
        if not pos:
            return
        pos_id = int(pos.get("position_id", 0))
        if pos_id in self._trailing_configs:
            del self._trailing_configs[pos_id]
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
                atr_pips = _price_to_pips(atr_h4, symbol) if atr_h4 > 0 else "N/A"
                profit_sign = "+" if profit_pips >= 0 else ""
                formula_pips = suggest_trail_pips(symbol, atr_h4, regime, profit_pips)
                prompt = (
                    f"Cho vị thế {symbol} {side.upper()} entry={entry_price:.5f} "
                    f"current={current_price:.5f} pnl={profit_sign}{profit_pips:.0f}pip "
                    f"atr_h4={atr_pips}pip.\n"
                    f"Hãy gợi ý khoảng cách trailing stop (pip) phù hợp.\n"
                    f"Trả lời CHỈ một dòng JSON, không thêm gì khác:\n"
                    f'{{"trail_pips":{formula_pips},"confidence":"medium","reason":"..."}}'
                )
                raw = ai.analyze(prompt, max_tokens=200)

                # Parse JSON from response
                import json as _json

                trail_pips = None
                confidence = "medium"
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
                    ai_result = {"trail_pips": trail_pips, "confidence": confidence, "reason": reason}
                else:
                    ai_error = raw[:150].replace("\n", " ") if raw else "(AI không trả về kết quả)"
            else:
                ai_error = "Chưa cấu hình API key"
        except Exception as exc:
            ai_error = str(exc)[:120]

        if ai_result and ai_result.get("trail_pips"):
            trail = int(ai_result["trail_pips"])
            confidence = str(ai_result.get("confidence", "medium"))
            reason = str(ai_result.get("reason", ""))
            conf_icon = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(confidence, "🟡")
            self._dlg_ai_label.setText(
                f"🧠 AI gợi ý: {trail} pip ({conf_icon} {confidence.upper()})"
            )
            self._dlg_ai_text.setMarkdown(
                f"**AI gợi ý: {trail} pip** ({conf_icon} {confidence.upper()})\n\n{reason}"
            )
        else:
            trail = suggest_trail_pips(symbol, atr_h4, regime, profit_pips)
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

        if hasattr(self.data_provider, "close_position"):
            result = self.data_provider.close_position(pos_id)
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

        if not hasattr(self.data_provider, "close_position"):
            QMessageBox.warning(self, "Không hỗ trợ", "Data provider không hỗ trợ đóng lệnh.")
            return

        closed = 0
        failed = 0
        for pos in self._positions:
            pos_id = int(pos.get("position_id", 0))
            if not pos_id:
                continue
            result = self.data_provider.close_position(pos_id)
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
