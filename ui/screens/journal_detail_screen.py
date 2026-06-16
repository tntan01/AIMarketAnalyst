from __future__ import annotations

import json

from datetime import UTC, datetime

from PyQt6.QtCore import QDateTime, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from controllers.journal_controller import JournalController
from services.journal_service import JournalEntry
from ui.screens.journal_screen import BIAS_TEXT, DECISION_TEXT, MODE_TEXT, PERMISSION_TEXT, format_time
from ui.screens.shared import action_button, card, labeled_value, page_header


class JournalDetailScreen(QWidget):
    def __init__(self, navigate=None) -> None:
        super().__init__()
        self.navigate = navigate
        self.journal_controller = JournalController()
        self.entry: JournalEntry | None = None
        self.setObjectName("FormScreen")
        self._build_ui()

    def _build_ui(self) -> None:
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(18, 14, 18, 14)
        self.root.setSpacing(10)
        self.header_slot = QVBoxLayout()
        self.root.addLayout(self.header_slot)

        self.general_grid = QGridLayout()
        self.general_grid.setSpacing(10)
        self.general_labels = {}
        for index, title in enumerate(["Thời gian lưu", "Mã", "Mã broker", "Chế độ", "Nguồn dữ liệu", "Quyền"]):
            item = labeled_value(title, "--")
            self.general_labels[title] = item.findChildren(__import__("PyQt6.QtWidgets").QtWidgets.QLabel)[1]
            self.general_grid.addWidget(item, index // 3, index % 3)

        left_col = QVBoxLayout()
        left_col.setSpacing(10)
        left_col.addLayout(self.general_grid)
        
        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)
        cards_row.addWidget(self._saved_analysis(), 1)
        
        note_col = QVBoxLayout()
        note_col.setSpacing(10)
        note_col.addWidget(self._mt5_card(), 0)
        note_col.addWidget(self._note_card(), 1)
        cards_row.addLayout(note_col, 1)
        
        left_col.addLayout(cards_row, 1)

        body = QHBoxLayout()
        body.setSpacing(10)
        body.addLayout(left_col, 2)
        
        side = QVBoxLayout()
        side.setSpacing(10)
        side.addWidget(self._lifecycle_card(), 1)
        body.addLayout(side, 1)
        self.root.addLayout(body, 1)

        actions = QHBoxLayout()
        self.back_button = action_button("⬅️ Quay lại")
        self.export_button = action_button("📤 Xuất JSON")
        self.delete_button = action_button("🗑️ Xóa bản ghi", primary=True, color="danger")
        if self.navigate:
            self.back_button.clicked.connect(lambda: self.navigate("journal"))
        self.export_button.clicked.connect(self._export_json)
        self.delete_button.clicked.connect(self._delete_entry)
        actions.addWidget(self.back_button)
        actions.addStretch(1)
        actions.addWidget(self.export_button)
        actions.addWidget(self.delete_button)
        self.root.addLayout(actions)
        self._render()

    def set_analysis_result(self, payload: dict[str, object]) -> None:
        entry_id = payload.get("journal_id")
        self.entry = self.journal_controller.get_entry(int(entry_id)) if entry_id else None
        self._render()

    def _saved_analysis(self):
        frame = card("Phân tích đã lưu")
        self.analysis_text = QTextEdit()
        self.analysis_text.setObjectName("ReadonlyText")
        self.analysis_text.setReadOnly(True)
        frame.layout().addWidget(self.analysis_text)
        return frame

    def _mt5_card(self):
        from ui.screens.shared import card
        frame = card("Thông tin đồng bộ MT5")
        
        self.mt5_deal_id_edit = QLineEdit()
        self.mt5_deal_id_edit.setReadOnly(True)
        self.mt5_order_id_edit = QLineEdit()
        self.mt5_order_id_edit.setReadOnly(True)
        self.mt5_position_id_edit = QLineEdit()
        self.mt5_position_id_edit.setReadOnly(True)

        layout = QGridLayout()
        layout.setSpacing(6)
        layout.addWidget(QLabel("Deal ID"), 0, 0)
        layout.addWidget(self.mt5_deal_id_edit, 0, 1)
        layout.addWidget(QLabel("Order ID"), 0, 2)
        layout.addWidget(self.mt5_order_id_edit, 0, 3)
        layout.addWidget(QLabel("Position ID"), 1, 0)
        layout.addWidget(self.mt5_position_id_edit, 1, 1, 1, 3)

        frame.layout().addLayout(layout)
        return frame

    def _note_card(self):
        frame = card("Ghi chú cá nhân")
        self.note_input = QTextEdit()
        self.note_input.setObjectName("ReadonlyText")
        frame.layout().addWidget(self.note_input, 1)
        self.save_note_button = action_button("💾 Lưu ghi chú", primary=True, color="success")
        self.save_note_button.clicked.connect(self._save_note)
        frame.layout().addWidget(self.save_note_button)
        return frame

    def _lifecycle_card(self):
        frame = card("Vòng đời giao dịch")

        # Status input (Planned, Opened, Closed, Cancelled, Missed)
        self.status_input = QComboBox()
        for text, value in [
            ("Đã lập kế hoạch", "planned"),
            ("Đã mở lệnh", "opened"),
            ("Đã đóng lệnh", "closed"),
            ("Đã hủy", "cancelled"),
            ("Bỏ lỡ", "missed"),
        ]:
            self.status_input.addItem(text, value)

        def create_section(title_text, is_grid=True):
            group = QWidget()
            vbox = QVBoxLayout(group)
            vbox.setContentsMargins(0, 16, 0, 0)
            vbox.setSpacing(8)
            
            title = QLabel(title_text)
            title.setStyleSheet("color: #38bdf8; font-size: 13px; font-weight: bold; border-bottom: 1px solid #334155; padding-bottom: 6px;")
            vbox.addWidget(title)
            
            inner = QWidget()
            layout = QGridLayout(inner) if is_grid else QVBoxLayout(inner)
            layout.setContentsMargins(2, 2, 2, 4)
            layout.setSpacing(6)
            vbox.addWidget(inner)
            
            return group, layout

        # Group 1: Kế hoạch (Planned - Read-only)
        planned_group, planned_layout = create_section("KẾ HOẠCH PHÂN TÍCH", True)

        self.planned_lot_edit = QLineEdit()
        self.planned_lot_edit.setReadOnly(True)
        self.planned_entry_edit = QLineEdit()
        self.planned_entry_edit.setReadOnly(True)
        self.planned_sl_edit = QLineEdit()
        self.planned_sl_edit.setReadOnly(True)
        self.planned_tp_edit = QLineEdit()
        self.planned_tp_edit.setReadOnly(True)

        planned_layout.addWidget(QLabel("Lot"), 0, 0)
        planned_layout.addWidget(self.planned_lot_edit, 0, 1)
        planned_layout.addWidget(QLabel("Entry"), 0, 2)
        planned_layout.addWidget(self.planned_entry_edit, 0, 3)
        planned_layout.addWidget(QLabel("SL"), 1, 0)
        planned_layout.addWidget(self.planned_sl_edit, 1, 1)
        planned_layout.addWidget(QLabel("TP"), 1, 2)
        planned_layout.addWidget(self.planned_tp_edit, 1, 3)

        # Group 2: Thực tế & Kết quả (Execution & Results)
        exec_group, exec_layout = create_section("THỰC TẾ & KẾT QUẢ", True)

        self.opened_at_chk = QCheckBox()
        self.opened_at_edit = QDateTimeEdit(QDateTime.currentDateTime())
        self.opened_at_edit.setCalendarPopup(True)
        self.opened_at_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.opened_at_edit.setEnabled(False)
        self.opened_at_chk.toggled.connect(self.opened_at_edit.setEnabled)

        self.closed_at_chk = QCheckBox()
        self.closed_at_edit = QDateTimeEdit(QDateTime.currentDateTime())
        self.closed_at_edit.setCalendarPopup(True)
        self.closed_at_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.closed_at_edit.setEnabled(False)
        self.closed_at_chk.toggled.connect(self.closed_at_edit.setEnabled)

        self.actual_lot_edit = QDoubleSpinBox()
        self.actual_lot_edit.setRange(0.0, 100.0)
        self.actual_lot_edit.setSingleStep(0.01)
        self.actual_lot_edit.setDecimals(2)

        self.actual_entry_edit = QDoubleSpinBox()
        self.actual_entry_edit.setRange(0.0, 1000000.0)
        self.actual_entry_edit.setDecimals(5)

        self.actual_sl_edit = QDoubleSpinBox()
        self.actual_sl_edit.setRange(0.0, 1000000.0)
        self.actual_sl_edit.setDecimals(5)

        self.actual_tp_edit = QDoubleSpinBox()
        self.actual_tp_edit.setRange(0.0, 1000000.0)
        self.actual_tp_edit.setDecimals(5)

        self.actual_exit_edit = QDoubleSpinBox()
        self.actual_exit_edit.setRange(0.0, 1000000.0)
        self.actual_exit_edit.setDecimals(5)

        self.result_amount_edit = QDoubleSpinBox()
        self.result_amount_edit.setRange(-1000000.0, 1000000.0)
        self.result_amount_edit.setDecimals(2)

        self.exit_reason_edit = QLineEdit()

        # Ẩn nút tăng giảm spinner thô kệch
        for spin in [self.actual_lot_edit, self.actual_entry_edit, self.actual_sl_edit, self.actual_tp_edit, self.actual_exit_edit, self.result_amount_edit]:
            spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)

        exec_layout.addWidget(QLabel("TG mở"), 0, 0)
        opened_layout = QHBoxLayout()
        opened_layout.setContentsMargins(0, 0, 0, 0)
        opened_layout.addWidget(self.opened_at_chk)
        opened_layout.addWidget(self.opened_at_edit, 1)
        exec_layout.addLayout(opened_layout, 0, 1, 1, 3)

        exec_layout.addWidget(QLabel("TG đóng"), 1, 0)
        closed_layout = QHBoxLayout()
        closed_layout.setContentsMargins(0, 0, 0, 0)
        closed_layout.addWidget(self.closed_at_chk)
        closed_layout.addWidget(self.closed_at_edit, 1)
        exec_layout.addLayout(closed_layout, 1, 1, 1, 3)

        exec_layout.addWidget(QLabel("Lot"), 2, 0)
        exec_layout.addWidget(self.actual_lot_edit, 2, 1)
        exec_layout.addWidget(QLabel("Entry"), 2, 2)
        exec_layout.addWidget(self.actual_entry_edit, 2, 3)
        
        exec_layout.addWidget(QLabel("SL"), 3, 0)
        exec_layout.addWidget(self.actual_sl_edit, 3, 1)
        exec_layout.addWidget(QLabel("TP"), 3, 2)
        exec_layout.addWidget(self.actual_tp_edit, 3, 3)
        
        exec_layout.addWidget(QLabel("Thoát"), 4, 0)
        exec_layout.addWidget(self.actual_exit_edit, 4, 1)
        exec_layout.addWidget(QLabel("Lãi/lỗ"), 4, 2)
        exec_layout.addWidget(self.result_amount_edit, 4, 3)
        
        exec_layout.addWidget(QLabel("Lý do thoát"), 5, 0)
        exec_layout.addWidget(self.exit_reason_edit, 5, 1, 1, 3)

        # Group 4: Mistake Tags Selector (Chips)
        tags_group, tags_layout = create_section("SAI LẦM GIAO DỊCH (TAGS)", False)

        tags_chips_layout = QGridLayout()
        tags_chips_layout.setSpacing(6)

        self.tag_buttons = {}
        row, col = 0, 0
        for tag_label, tag_code in [
            ("FOMO", "fomo"),
            ("Chốt non", "early_exit"),
            ("Gồng lỗ", "holding_loss"),
            ("Vào sớm", "early_entry"),
            ("Overtrade", "overtrade"),
            ("Sai Lot", "wrong_lot"),
        ]:
            btn = QPushButton(tag_label)
            btn.setCheckable(True)
            btn.setObjectName("TagChip")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton#TagChip {
                    background-color: #1e293b;
                    border: 1px solid #334155;
                    border-radius: 12px;
                    padding: 4px 10px;
                    color: #94a3b8;
                    font-size: 11px;
                }
                QPushButton#TagChip:checked {
                    background-color: rgba(251, 113, 133, 0.2);
                    border: 1px solid #fb7185;
                    color: #fb7185;
                    font-weight: bold;
                }
            """)
            tags_chips_layout.addWidget(btn, row, col)
            self.tag_buttons[tag_code] = btn
            col += 1
            if col > 2:
                col = 0
                row += 1

        tags_layout.addLayout(tags_chips_layout)

        # Assemble layout
        card_layout = QVBoxLayout()
        card_layout.setSpacing(8)

        status_row = QHBoxLayout()
        status_row.addWidget(QLabel("Trạng thái"))
        status_row.addWidget(self.status_input, 1)
        card_layout.addLayout(status_row)

        card_layout.addWidget(planned_group)
        card_layout.addWidget(exec_group)
        card_layout.addWidget(tags_group)

        self.lifecycle_result_label = QLabel("--")
        self.lifecycle_result_label.setObjectName("HelperText")
        self.lifecycle_result_label.setWordWrap(True)
        card_layout.addWidget(self.lifecycle_result_label)

        helper = QLabel("Result R được tính khi có hướng lệnh, entry, SL và giá thoát. Thời gian đóng sẽ tự điền khi trạng thái là Đã đóng lệnh.")
        helper.setObjectName("HelperText")
        helper.setWordWrap(True)
        card_layout.addWidget(helper)

        scroll_area = __import__("PyQt6.QtWidgets").QtWidgets.QScrollArea()
        scroll_area.setObjectName("LifecycleScroll")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(__import__("PyQt6.QtWidgets").QtWidgets.QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(__import__("PyQt6.QtCore").QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        scroll_widget = QWidget()
        scroll_widget.setObjectName("LifecycleScrollWidget")
        scroll_widget.setStyleSheet("#LifecycleScrollWidget { background: transparent; }")
        scroll_widget.setLayout(card_layout)
        scroll_area.setWidget(scroll_widget)

        frame.layout().addWidget(scroll_area)

        self.save_lifecycle_button = action_button("💾 Lưu kết quả lệnh", primary=True, color="success")
        self.save_lifecycle_button.clicked.connect(self._save_lifecycle)
        frame.layout().addWidget(self.save_lifecycle_button)

        return frame

    def _render(self) -> None:
        while self.header_slot.count():
            item = self.header_slot.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        symbol = self.entry.symbol if self.entry else "--"
        self.header_slot.addWidget(
            page_header("Chi tiết nhật ký", "Bản chụp phân tích tại thời điểm đã lưu.", symbol)
        )
        if not self.entry:
            self.analysis_text.setHtml("<div style='color: #94a3b8; font-size: 13px;'>Chọn một bản ghi trong màn Nhật ký để xem chi tiết.</div>")
            self.note_input.setPlainText("")
            self._clear_lifecycle_form()
            return
        values = {
            "Thời gian lưu": format_time(self.entry.saved_at_utc),
            "Mã": self.entry.symbol,
            "Mã broker": self.entry.broker_symbol or "--",
            "Chế độ": MODE_TEXT.get(self.entry.mode, self.entry.mode),
            "Nguồn dữ liệu": self.entry.data_source,
            "Quyền": PERMISSION_TEXT.get(self.entry.trade_permission, self.entry.trade_permission),
        }
        for title, label in self.general_labels.items():
            label.setText(str(values.get(title, "--")))
        self.analysis_text.setHtml(self._analysis_html())
        self.note_input.setPlainText(self.entry.note)
        self._load_lifecycle_form()

    def _analysis_html(self) -> str:
        entry = self.entry
        if not entry:
            return ""

        decision_val = entry.decision
        decision_txt = DECISION_TEXT.get(decision_val, decision_val)
        decision_color = {
            "ready": "#5eead4",
            "watch": "#93c5fd",
            "wait": "#facc15",
            "wait_for_confirmation": "#facc15",
        }.get(decision_val, "#94a3b8")

        bias_val = entry.direction_bias
        bias_txt = BIAS_TEXT.get(bias_val, bias_val)
        bias_color = {
            "buy": "#5eead4",
            "sell": "#fb7185",
        }.get(bias_val, "#cbd5e1")

        perm_val = entry.trade_permission
        perm_txt = PERMISSION_TEXT.get(perm_val, perm_val)
        perm_color = {
            "allowed": "#5eead4",
            "caution": "#facc15",
        }.get(perm_val, "#94a3b8")

        regime_val = entry.market_regime or ""
        regime_txt = {
            "trend_up": "Xu hướng tăng",
            "trend_down": "Xu hướng giảm",
            "range": "Đi ngang (Range)",
            "volatile": "Biến động mạnh",
        }.get(regime_val, regime_val) if regime_val else "--"

        scenario_val = entry.selected_scenario or ""
        scenario_txt = {
            "buy_at_support": "Mua tại Hỗ trợ",
            "sell_at_resistance": "Bán tại Kháng cự",
            "breakout_buy": "Mua phá vỡ (Breakout)",
            "breakout_sell": "Bán phá vỡ (Breakdown)",
            "counter_trend_buy": "Mua ngược xu hướng",
            "counter_trend_sell": "Bán ngược xu hướng"
        }.get(scenario_val, scenario_val) if scenario_val else "--"

        entry_zone_txt = format_json_text(entry.entry_zone)
        take_profit_txt = format_json_text(entry.take_profit)

        # Trực quan hóa R:R
        rr_bar_html = ""
        try:
            sl = float(entry.stop_loss) if entry.stop_loss else 0.0
            tp_list = json.loads(entry.take_profit) if entry.take_profit else []
            tp = float(tp_list[0]) if tp_list else 0.0
            entry_zone_list = json.loads(entry.entry_zone) if entry.entry_zone else []
            entry_price = float(entry_zone_list[0] + entry_zone_list[1]) / 2 if len(entry_zone_list) >= 2 else 0.0

            if sl > 0 and tp > 0 and entry_price > 0:
                total_span = abs(tp - sl)
                if total_span > 0:
                    if bias_val == "buy":
                        red_pct = min(100, max(0, int(abs(entry_price - sl) / total_span * 100)))
                        green_pct = 100 - red_pct
                    else:
                        green_pct = min(100, max(0, int(abs(entry_price - tp) / total_span * 100)))
                        red_pct = 100 - green_pct

                    rr_bar_html = f"""
                    <div style="margin: 8px 0; font-size: 11px; color: #94a3b8;">Trực quan R:R:</div>
                    <table style="width: 100%; table-layout: fixed; height: 10px; border-collapse: collapse; margin-bottom: 2px;">
                        <tr style="height: 10px;">
                            <td style="background-color: #fb7185; width: {red_pct}%; border-radius: 5px 0 0 5px; height: 10px;"></td>
                            <td style="background-color: #5eead4; width: {green_pct}%; border-radius: 0 5px 5px 0; height: 10px;"></td>
                        </tr>
                    </table>
                    <div style="display: flex; justify-content: space-between; font-size: 10px; color: #64748b; margin-top: 2px;">
                        <span>SL ({sl:.5f})</span>
                        <span>Entry ({entry_price:.5f})</span>
                        <span>TP ({tp:.5f})</span>
                    </div>
                    """
        except Exception:
            pass

        suggested_lot_txt = f"{entry.suggested_lot:.2f}" if entry.suggested_lot is not None else "--"

        return f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial; color: #e5e7eb; line-height: 1.5; font-size: 13px;">
          <!-- Section 1: Decision & Score -->
          <div style="background-color: #0f172a; border-radius: 8px; padding: 12px; margin-bottom: 12px; border: 1px solid #334155;">
            <h3 style="margin-top: 0; margin-bottom: 8px; color: #38bdf8; font-size: 13px; border-bottom: 1px solid #334155; padding-bottom: 6px;">KẾT LUẬN PHÂN TÍCH</h3>
            <table style="width: 100%; table-layout: fixed; border-collapse: collapse;">
              <tr>
                <td style="color: #94a3b8; width: 45%; padding: 4px 0;">Kết luận:</td>
                <td style="font-weight: bold; width: 55%; color: {decision_color}; padding: 4px 0;">{decision_txt}</td>
              </tr>
              <tr>
                <td style="color: #94a3b8; padding: 4px 0;">Thiên hướng:</td>
                <td style="font-weight: bold; color: {bias_color}; padding: 4px 0;">{bias_txt}</td>
              </tr>
              <tr>
                <td style="color: #94a3b8; padding: 4px 0;">Trạng thái thị trường:</td>
                <td style="font-weight: bold; color: #cbd5e1; padding: 4px 0;">{regime_txt}</td>
              </tr>
              <tr>
                <td style="color: #94a3b8; padding: 4px 0;">Quyền giao dịch:</td>
                <td style="font-weight: bold; color: {perm_color}; padding: 4px 0;">{perm_txt}</td>
              </tr>
              <tr>
                <td style="color: #94a3b8; padding: 4px 0;">Điểm Mua / Bán:</td>
                <td style="font-weight: bold; padding: 4px 0;"><span style="color: #5eead4;">{entry.buy_score}</span> / <span style="color: #fb7185;">{entry.sell_score}</span></td>
              </tr>
            </table>
          </div>

          <!-- Section 2: Trade Plan -->
          <div style="background-color: #0f172a; border-radius: 8px; padding: 12px; margin-bottom: 12px; border: 1px solid #334155;">
            <h3 style="margin-top: 0; margin-bottom: 8px; color: #38bdf8; font-size: 13px; border-bottom: 1px solid #334155; padding-bottom: 6px;">KẾ HOẠCH GIAO DỊCH</h3>
            <table style="width: 100%; table-layout: fixed; border-collapse: collapse;">
              <tr>
                <td style="color: #94a3b8; width: 45%; padding: 4px 0;">Kịch bản chọn:</td>
                <td style="font-weight: bold; width: 55%; color: #cbd5e1; padding: 4px 0;">{scenario_txt}</td>
              </tr>
              <tr>
                <td style="color: #94a3b8; padding: 4px 0;">Vùng vào lệnh:</td>
                <td style="color: #facc15; font-weight: bold; padding: 4px 0;">{entry_zone_txt}</td>
              </tr>
              <tr>
                <td style="color: #94a3b8; padding: 4px 0;">Stop Loss (SL):</td>
                <td style="color: #fb7185; font-weight: bold; padding: 4px 0;">{entry.stop_loss or '--'}</td>
              </tr>
              <tr>
                <td style="color: #94a3b8; padding: 4px 0;">Take Profit (TP):</td>
                <td style="color: #5eead4; font-weight: bold; padding: 4px 0;">{take_profit_txt}</td>
              </tr>
              <tr>
                <td style="color: #94a3b8; padding: 4px 0;">Tỷ lệ R:R:</td>
                <td style="font-weight: bold; color: #cbd5e1; padding: 4px 0;">{entry.risk_reward or '--'}</td>
              </tr>
              <tr>
                <td style="color: #94a3b8; padding: 4px 0;">Lot đề xuất:</td>
                <td style="font-weight: bold; color: #cbd5e1; padding: 4px 0;">{suggested_lot_txt}</td>
              </tr>
            </table>
            {rr_bar_html}
          </div>

          <!-- Section 3: AI Commentary -->
          <div style="background-color: #0f172a; border-radius: 8px; padding: 12px; border: 1px solid #334155;">
            <h3 style="margin-top: 0; margin-bottom: 8px; color: #38bdf8; font-size: 13px; border-bottom: 1px solid #334155; padding-bottom: 6px;">NHẬN ĐỊNH CỦA AI</h3>
            <div style="color: #cbd5e1; white-space: pre-wrap; font-size: 12px; margin-top: 6px;">{entry.ai_commentary or '--'}</div>
          </div>
        </div>
        """

    def _clear_lifecycle_form(self) -> None:
        if hasattr(self, "status_input"):
            self.status_input.setCurrentIndex(0)
        self.planned_lot_edit.setText("")
        self.planned_entry_edit.setText("")
        self.planned_sl_edit.setText("")
        self.planned_tp_edit.setText("")
        self.opened_at_chk.setChecked(False)
        self.closed_at_chk.setChecked(False)
        self.actual_lot_edit.setValue(0.0)
        self.actual_entry_edit.setValue(0.0)
        self.actual_sl_edit.setValue(0.0)
        self.actual_tp_edit.setValue(0.0)
        self.actual_exit_edit.setValue(0.0)
        self.result_amount_edit.setValue(0.0)
        self.exit_reason_edit.setText("")
        self.mt5_deal_id_edit.setText("")
        self.mt5_order_id_edit.setText("")
        self.mt5_position_id_edit.setText("")
        for btn in self.tag_buttons.values():
            btn.setChecked(False)
        if hasattr(self, "lifecycle_result_label"):
            self.lifecycle_result_label.setText("--")

    def _load_lifecycle_form(self) -> None:
        entry = self.entry
        if not entry:
            self._clear_lifecycle_form()
            return
        status = entry.trade_status or "planned"
        index = self.status_input.findData(status)
        self.status_input.setCurrentIndex(index if index >= 0 else 0)

        # Điền Kế hoạch (Read-only)
        self.planned_lot_edit.setText("" if entry.planned_lot is None else f"{entry.planned_lot:.2f}")
        self.planned_entry_edit.setText("" if entry.planned_entry is None else f"{entry.planned_entry:.5f}")
        self.planned_sl_edit.setText("" if entry.planned_sl is None else f"{entry.planned_sl:.5f}")
        self.planned_tp_edit.setText("" if entry.planned_tp is None else f"{entry.planned_tp:.5f}")

        # Điền Thời gian
        if entry.opened_at:
            dt = QDateTime.fromString(entry.opened_at.replace("Z", "+00:00"), Qt.DateFormat.ISODate)
            if dt.isValid():
                self.opened_at_edit.setDateTime(dt)
                self.opened_at_chk.setChecked(True)
                self.opened_at_edit.setEnabled(True)
            else:
                self.opened_at_chk.setChecked(False)
                self.opened_at_edit.setEnabled(False)
        else:
            self.opened_at_chk.setChecked(False)
            self.opened_at_edit.setEnabled(False)

        if entry.closed_at:
            dt = QDateTime.fromString(entry.closed_at.replace("Z", "+00:00"), Qt.DateFormat.ISODate)
            if dt.isValid():
                self.closed_at_edit.setDateTime(dt)
                self.closed_at_chk.setChecked(True)
                self.closed_at_edit.setEnabled(True)
            else:
                self.closed_at_chk.setChecked(False)
                self.closed_at_edit.setEnabled(False)
        else:
            self.closed_at_chk.setChecked(False)
            self.closed_at_edit.setEnabled(False)

        # Định dạng decimals động theo symbol
        decimals = 5
        symbol_upper = str(entry.symbol).upper()
        if any(keyword in symbol_upper for keyword in ["JPY", "XAU", "BTC"]):
            decimals = 2
        elif "XAG" in symbol_upper:
            decimals = 3

        for spin in [self.actual_entry_edit, self.actual_sl_edit, self.actual_tp_edit, self.actual_exit_edit]:
            spin.setDecimals(decimals)

        # Điền Thực tế (QDoubleSpinBox)
        self.actual_lot_edit.setValue(entry.actual_lot or 0.0)
        self.actual_entry_edit.setValue(entry.actual_entry or 0.0)
        self.actual_sl_edit.setValue(entry.actual_sl or 0.0)
        self.actual_tp_edit.setValue(entry.actual_tp or 0.0)
        self.actual_exit_edit.setValue(entry.actual_exit or 0.0)
        self.result_amount_edit.setValue(entry.result_amount or 0.0)

        self.exit_reason_edit.setText(entry.exit_reason or "")

        # Điền MT5
        self.mt5_deal_id_edit.setText("" if entry.mt5_deal_id is None else str(entry.mt5_deal_id))
        self.mt5_order_id_edit.setText("" if entry.mt5_order_id is None else str(entry.mt5_order_id))
        self.mt5_position_id_edit.setText("" if entry.mt5_position_id is None else str(entry.mt5_position_id))

        # Điền Tag lỗi
        from services.journal_service import tags_from_json
        tags = tags_from_json(entry.manual_mistake_tags)
        for tag_code, btn in self.tag_buttons.items():
            btn.setChecked(tag_code in tags)

        # Cập nhật kết quả R
        result = entry.result_r if entry.result_r is not None else "--"
        pct = entry.result_pct if entry.result_pct is not None else "--"
        quality = entry.execution_quality_score if entry.execution_quality_score is not None else "--"
        self.lifecycle_result_label.setText(f"Kết quả: {result}R | {pct}% | Chất lượng thực thi: {quality}")

    def _save_lifecycle(self) -> None:
        if not self.entry or self.entry.id is None:
            return

        updates: dict[str, object] = {"trade_status": self.status_input.currentData()}

        # Xử lý thời gian
        if self.opened_at_chk.isChecked():
            updates["opened_at"] = self.opened_at_edit.dateTime().toUTC().toString("yyyy-MM-ddTHH:mm:ssZ")
        else:
            updates["opened_at"] = ""

        if self.closed_at_chk.isChecked():
            updates["closed_at"] = self.closed_at_edit.dateTime().toUTC().toString("yyyy-MM-ddTHH:mm:ssZ")
        else:
            updates["closed_at"] = ""

        # Xử lý các trường số từ SpinBox
        updates["actual_lot"] = self.actual_lot_edit.value() if self.actual_lot_edit.value() > 0 else None
        updates["actual_entry"] = self.actual_entry_edit.value() if self.actual_entry_edit.value() > 0 else None
        updates["actual_sl"] = self.actual_sl_edit.value() if self.actual_sl_edit.value() > 0 else None
        updates["actual_tp"] = self.actual_tp_edit.value() if self.actual_tp_edit.value() > 0 else None
        updates["actual_exit"] = self.actual_exit_edit.value() if self.actual_exit_edit.value() > 0 else None
        updates["result_amount"] = self.result_amount_edit.value() if self.result_amount_edit.value() != 0.0 else None

        updates["exit_reason"] = self.exit_reason_edit.text().strip()

        # Xử lý Tag lỗi từ Chip buttons
        selected_tags = [tag_code for tag_code, btn in self.tag_buttons.items() if btn.isChecked()]
        from services.journal_service import tags_to_json
        updates["manual_mistake_tags"] = tags_to_json(selected_tags)

        self.journal_controller.update_lifecycle(self.entry.id, updates)
        self.entry = self.journal_controller.get_entry(self.entry.id)
        self._render()
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Đã lưu")
        msg_box.setText("Đã lưu vòng đời/kết quả giao dịch.")
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.addButton(action_button("❌ Đóng"), QMessageBox.ButtonRole.AcceptRole)
        msg_box.exec()

    def _save_note(self) -> None:
        if not self.entry or self.entry.id is None:
            return
        self.journal_controller.update_note(self.entry.id, self.note_input.toPlainText())
        self.entry = self.journal_controller.get_entry(self.entry.id)
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Đã lưu")
        msg_box.setText("Đã lưu ghi chú cá nhân.")
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.addButton(action_button("❌ Đóng"), QMessageBox.ButtonRole.AcceptRole)
        msg_box.exec()

    def _export_json(self) -> None:
        if not self.entry:
            return
        path = self.journal_controller.export_entry_json(self.entry)
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Đã xuất JSON")
        msg_box.setText(f"Đã xuất dữ liệu vào:\n{path}")
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.addButton(action_button("❌ Đóng"), QMessageBox.ButtonRole.AcceptRole)
        msg_box.exec()

    def _delete_entry(self) -> None:
        if not self.entry or self.entry.id is None:
            return
        self.journal_controller.delete_entry(self.entry.id)
        if self.navigate:
            self.navigate("journal")


def format_json_text(value: str) -> str:
    if not value:
        return "--"
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return value
    if isinstance(parsed, list):
        return " - ".join(str(item) for item in parsed) if parsed else "--"
    return str(parsed or "--")


def parse_optional_float(value: str) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None
