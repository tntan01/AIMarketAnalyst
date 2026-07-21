from __future__ import annotations

import json

from datetime import UTC, datetime

from PyQt6.QtCore import QDateTime, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from controllers.journal_controller import JournalController
from services.journal_service import JournalEntry
from services.settings_service import SettingsService
from ui.screens.journal_screen import BIAS_TEXT, DECISION_TEXT, PERMISSION_TEXT, format_time
from ui.screens.shared import action_button, card, page_header


class JournalDetailScreen(QWidget):
    def __init__(self, navigate=None, *, app=None) -> None:
        super().__init__()
        self.navigate = navigate
        self.app = app
        self.journal_controller = (
            app.journal_controller if app else JournalController()
        )
        self.settings_service = app.settings_service if app else SettingsService()
        self.entry: JournalEntry | None = None
        self.setObjectName("FormScreen")
        self._build_ui()

    def _is_light(self) -> bool:
        try:
            return self.settings_service.load().display.theme == "light"
        except Exception:
            return False

    @property
    def _bg(self) -> str:
        return "#ffffff" if self._is_light() else "#1a1f2e"

    @property
    def _border_color(self) -> str:
        return "#d1d5db" if self._is_light() else "#2b3545"

    @property
    def _label_color(self) -> str:
        return "#475569" if self._is_light() else "#94a3b8"

    @property
    def _val_color(self) -> str:
        return "#0f172a" if self._is_light() else "#f1f5f9"

    @property
    def _card_bg(self) -> str:
        return "#f1f5f9" if self._is_light() else "#1e293b"

    @property
    def _accent(self) -> str:
        return "#0284c7" if self._is_light() else "#38bdf8"

    @property
    def _orange_accent(self) -> str:
        return "#ea580c" if self._is_light() else "#f97316"

    def _build_ui(self) -> None:
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(12, 6, 12, 6)
        self.root.setSpacing(6)

        self.header_slot = QVBoxLayout()
        self.root.addLayout(self.header_slot)

        # Hero Summary Banner
        self.hero_summary = self._hero_summary_card()
        self.root.addWidget(self.hero_summary)

        # Main Scroll Area to fit all content nicely without extra blank spaces
        self.main_scroll = QScrollArea()
        self.main_scroll.setObjectName("MainDetailScroll")
        self.main_scroll.setWidgetResizable(True)
        self.main_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.main_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_widget = QWidget()
        scroll_widget.setObjectName("MainDetailScrollWidget")
        scroll_widget.setStyleSheet("#MainDetailScrollWidget { background: transparent; }")

        main_vbox = QVBoxLayout(scroll_widget)
        main_vbox.setContentsMargins(0, 0, 0, 0)
        main_vbox.setSpacing(8)

        # 1. Full-width 3 Analysis Cards (Kết luận, Kế hoạch, AI)
        main_vbox.addWidget(self._saved_analysis())

        # 2. Bottom Row: Vòng đời giao dịch (Left 60%) & Ghi chú cá nhân (Right 40%)
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(12)

        lifecycle_card = self._lifecycle_card()
        note_card = self._note_and_mt5_card()

        bottom_row.addWidget(lifecycle_card, 60)
        bottom_row.addWidget(note_card, 40)

        main_vbox.addLayout(bottom_row)

        self.main_scroll.setWidget(scroll_widget)
        self.root.addWidget(self.main_scroll, 1)

        # Bottom Actions Bar
        actions = QHBoxLayout()
        actions.setSpacing(10)

        self.back_button = action_button("⬅️ Quay lại Nhật ký")
        self.export_button = action_button("📤 Xuất JSON", primary=False)
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

    def _hero_summary_card(self) -> QFrame:
        card_frame = QFrame()
        card_frame.setObjectName("HeroSummaryCard")
        card_frame.setStyleSheet(
            f"""
            QFrame#HeroSummaryCard {{
                background-color: {self._bg};
                border: 1px solid {self._border_color};
                border-radius: 8px;
                padding: 4px 10px;
            }}
            """
        )
        layout = QHBoxLayout(card_frame)
        layout.setContentsMargins(12, 6, 12, 6)

        self.hero_text_lbl = QLabel("--")
        self.hero_text_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {self._val_color}; "
            "font-family: -apple-system, 'Segoe UI', sans-serif;"
        )
        self.hero_text_lbl.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.hero_text_lbl)
        layout.addStretch(1)

        return card_frame

    def _update_hero_summary(self) -> None:
        if not self.entry:
            return

        symbol = self.entry.symbol or "--"
        bias = (self.entry.direction_bias or "").lower()
        val = self._val_color
        label = self._label_color
        sep = f'<span style="color: {label};">|</span>'

        # Time + Direction + Symbol
        saved = format_time(self.entry.saved_at_utc)
        if bias == "buy":
            dir_text = f'<span style="color: #10b981; font-weight: 700;">MUA</span>'
        elif bias == "sell":
            dir_text = f'<span style="color: #ef4444; font-weight: 700;">BÁN</span>'
        else:
            dir_text = ""

        sym_part = f'{dir_text} <span style="font-weight: 700;">{symbol}</span>' if dir_text else f'<span style="font-weight: 700;">{symbol}</span>'
        parts = [sym_part]

        # P/L Amount
        amt = self.entry.result_amount
        if amt is not None:
            if amt > 0:
                parts.append(f'<span style="color: #10b981; font-weight: 700;">+${amt:,.2f}</span>')
            elif amt < 0:
                parts.append(f'<span style="color: #ef4444; font-weight: 700;">-${abs(amt):,.2f}</span>')
            else:
                parts.append(f'<span style="color: {val};">$0.00</span>')
        else:
            parts.append(f'<span style="color: {label};">--</span>')

        # Result R
        res_r = self.entry.result_r
        if isinstance(res_r, (int, float)):
            r_color = "#10b981" if res_r > 0 else ("#ef4444" if res_r < 0 else val)
            parts.append(f'<span style="color: {r_color}; font-weight: 600;">{res_r:+.2f}R</span>')
        else:
            parts.append(f'<span style="color: {label};">--</span>')

        # Status
        status = self.entry.trade_status or "planned"
        status_txt = {
            "planned": "ĐÃ LẬP KẾ HOẠCH",
            "opened": "ĐÃ MỞ LỆNH",
            "closed": "ĐÃ ĐÓNG LỆNH",
            "cancelled": "ĐÃ HỦY",
            "missed": "BỎ LỠ",
        }.get(status, status.upper())
        parts.append(f'<span style="color: {val}; font-weight: 600;">{status_txt}</span>')

        # Quality score
        quality = self.entry.execution_quality_score
        if quality is not None:
            parts.append(f'<span style="color: {self._accent}; font-weight: 600;">CL: {quality}/100</span>')
        else:
            parts.append(f'<span style="color: {label};">CL: --</span>')

        # Timestamp
        parts.append(f'<span style="color: {label};">{saved}</span>')

        self.hero_text_lbl.setText(f" {sep} ".join(parts))

    def set_analysis_result(self, payload: dict[str, object]) -> None:
        entry_id = payload.get("journal_id")
        self.entry = self.journal_controller.get_entry(int(entry_id)) if entry_id else None
        self._render()

    def _saved_analysis(self):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title_style = f"color: {self._orange_accent}; font-size: 12px; font-weight: 700;"

        card1 = card("📊 Kết luận phân tích")
        card1.layout().setContentsMargins(8, 6, 8, 6)
        card1.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        card1.layout().setSpacing(4)
        c1_title = card1.findChild(QLabel, "CardTitle")
        if c1_title:
            c1_title.setStyleSheet(title_style)

        card2 = card("🎯 Kế hoạch giao dịch")
        card2.layout().setContentsMargins(8, 6, 8, 6)
        card2.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        card2.layout().setSpacing(4)
        c2_title = card2.findChild(QLabel, "CardTitle")
        if c2_title:
            c2_title.setStyleSheet(title_style)

        card3 = card("🤖 Nhận định của AI")
        card3.layout().setContentsMargins(8, 6, 8, 6)
        card3.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        card3.layout().setSpacing(4)
        c3_title = card3.findChild(QLabel, "CardTitle")
        if c3_title:
            c3_title.setStyleSheet(title_style)

        self.analysis_dec_text = QTextEdit()
        self.analysis_plan_text = QTextEdit()
        self.analysis_ai_text = QTextEdit()

        for txt in (self.analysis_dec_text, self.analysis_plan_text, self.analysis_ai_text):
            txt.setObjectName("ReadonlyText")
            txt.setReadOnly(True)
            txt.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            txt.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            txt.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
            txt.setMinimumHeight(55)
            txt.setMaximumHeight(75)
            txt.document().setDocumentMargin(0)
            txt.setAlignment(Qt.AlignmentFlag.AlignLeft)
            txt.setStyleSheet(
                "QTextEdit#ReadonlyText { background: transparent; border: none; font-family: -apple-system, 'Segoe UI', sans-serif; text-align: left; padding: 0px; margin: 0px; }"
            )

        card1.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        card2.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        card3.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        card1.layout().addWidget(self.analysis_dec_text)
        card1.layout().addStretch(1)

        card2.layout().addWidget(self.analysis_plan_text)
        card2.layout().addStretch(1)

        card3.layout().addWidget(self.analysis_ai_text)
        card3.layout().addStretch(1)

        layout.addWidget(card1, 1)
        layout.addWidget(card2, 1)
        layout.addWidget(card3, 1)

        self.analysis_text = self.analysis_dec_text
        return container

    def _note_and_mt5_card(self):
        frame = card("📝 Ghi chú cá nhân")
        frame.layout().setContentsMargins(8, 6, 8, 6)
        frame.layout().setSpacing(4)
        c_title = frame.findChild(QLabel, "CardTitle")
        if c_title:
            c_title.setStyleSheet(f"color: {self._orange_accent}; font-size: 12px; font-weight: 700;")

        self.note_input = QTextEdit()
        self.note_input.setObjectName("ReadonlyText")
        self.note_input.setMinimumHeight(80)
        self.note_input.setStyleSheet(
            f"QTextEdit {{ background: {self._card_bg}; border: 1px solid {self._border_color}; border-radius: 6px; color: {self._val_color}; font-family: -apple-system, 'Segoe UI', sans-serif; font-size: 11.5px; padding: 4px; }}"
        )
        frame.layout().addWidget(self.note_input, 1)

        self.save_note_button = action_button("💾 Lưu ghi chú", primary=True, color="success")
        self.save_note_button.clicked.connect(self._save_note)
        frame.layout().addWidget(self.save_note_button)

        return frame

    def _lifecycle_card(self):
        frame = card("📈 Vòng đời giao dịch")
        frame.layout().setContentsMargins(10, 8, 10, 8)
        frame.layout().setSpacing(6)
        c_title = frame.findChild(QLabel, "CardTitle")
        if c_title:
            c_title.setStyleSheet(f"color: {self._orange_accent}; font-size: 13px; font-weight: 700;")

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
            vbox.setContentsMargins(0, 4, 0, 0)
            vbox.setSpacing(4)

            title = QLabel(title_text)
            title.setStyleSheet(f"color: #38bdf8; font-size: 12px; font-weight: bold; padding-bottom: 2px; border-bottom: 1px solid {self._border_color}; margin-bottom: 2px;")
            vbox.addWidget(title)

            inner = QWidget()
            if is_grid:
                layout = QGridLayout(inner)
                layout.setContentsMargins(0, 2, 0, 2)
                layout.setVerticalSpacing(4)
                layout.setHorizontalSpacing(6)
            else:
                layout = QVBoxLayout(inner)
                layout.setContentsMargins(0, 2, 0, 2)
                layout.setSpacing(4)
            vbox.addWidget(inner)

            return group, layout

        # Group 1: Thực tế & Kết quả (Execution & Results)
        exec_group, exec_layout = create_section("THỰC TẾ & KẾT QUẢ", True)
        exec_layout.setColumnStretch(0, 0)
        exec_layout.setColumnStretch(1, 1)
        exec_layout.setColumnStretch(2, 0)
        exec_layout.setColumnStretch(3, 1)
        exec_layout.setHorizontalSpacing(8)
        exec_layout.setVerticalSpacing(4)

        chk_style = "QCheckBox::indicator { width: 16px; height: 16px; }"

        self.opened_at_chk = QCheckBox()
        self.opened_at_chk.setMinimumSize(20, 20)
        self.opened_at_chk.setStyleSheet(chk_style)
        self.opened_at_edit = QDateTimeEdit(QDateTime.currentDateTime())
        self.opened_at_edit.setCalendarPopup(True)
        self.opened_at_edit.setDisplayFormat("dd/MM/yyyy HH:mm:ss")
        self.opened_at_edit.setEnabled(False)
        self.opened_at_edit.setMinimumWidth(175)
        self.opened_at_chk.toggled.connect(self.opened_at_edit.setEnabled)

        self.closed_at_chk = QCheckBox()
        self.closed_at_chk.setMinimumSize(20, 20)
        self.closed_at_chk.setStyleSheet(chk_style)
        self.closed_at_edit = QDateTimeEdit(QDateTime.currentDateTime())
        self.closed_at_edit.setCalendarPopup(True)
        self.closed_at_edit.setDisplayFormat("dd/MM/yyyy HH:mm:ss")
        self.closed_at_edit.setEnabled(False)
        self.closed_at_edit.setMinimumWidth(175)
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

        lbl_style = f"color: {self._label_color}; font-size: 11px; font-weight: 600;"

        l_topen = QLabel("TG mở")
        l_topen.setStyleSheet(lbl_style)
        exec_layout.addWidget(l_topen, 0, 0)
        opened_layout = QHBoxLayout()
        opened_layout.setContentsMargins(0, 0, 0, 0)
        opened_layout.setSpacing(6)
        opened_layout.addWidget(self.opened_at_chk)
        opened_layout.addWidget(self.opened_at_edit, 1)
        exec_layout.addLayout(opened_layout, 0, 1, 1, 3)

        l_tclose = QLabel("TG đóng")
        l_tclose.setStyleSheet(lbl_style)
        exec_layout.addWidget(l_tclose, 1, 0)
        closed_layout = QHBoxLayout()
        closed_layout.setContentsMargins(0, 0, 0, 0)
        closed_layout.setSpacing(6)
        closed_layout.addWidget(self.closed_at_chk)
        closed_layout.addWidget(self.closed_at_edit, 1)
        exec_layout.addLayout(closed_layout, 1, 1, 1, 3)

        l_lot = QLabel("Lot")
        l_lot.setStyleSheet(lbl_style)
        exec_layout.addWidget(l_lot, 2, 0)
        exec_layout.addWidget(self.actual_lot_edit, 2, 1)

        l_entry = QLabel("Entry")
        l_entry.setStyleSheet(lbl_style)
        exec_layout.addWidget(l_entry, 2, 2)
        exec_layout.addWidget(self.actual_entry_edit, 2, 3)

        l_sl = QLabel("SL")
        l_sl.setStyleSheet(lbl_style)
        exec_layout.addWidget(l_sl, 3, 0)
        exec_layout.addWidget(self.actual_sl_edit, 3, 1)

        l_tp = QLabel("TP")
        l_tp.setStyleSheet(lbl_style)
        exec_layout.addWidget(l_tp, 3, 2)
        exec_layout.addWidget(self.actual_tp_edit, 3, 3)

        l_exit = QLabel("Thoát")
        l_exit.setStyleSheet(lbl_style)
        exec_layout.addWidget(l_exit, 4, 0)
        exec_layout.addWidget(self.actual_exit_edit, 4, 1)

        l_pl = QLabel("Lãi/lỗ")
        l_pl.setStyleSheet(lbl_style)
        exec_layout.addWidget(l_pl, 4, 2)
        exec_layout.addWidget(self.result_amount_edit, 4, 3)

        l_reason = QLabel("Lý do thoát")
        l_reason.setStyleSheet(lbl_style)
        exec_layout.addWidget(l_reason, 5, 0)
        exec_layout.addWidget(self.exit_reason_edit, 5, 1, 1, 3)

        # Group 4: Mistake Tags Selector (Chips)
        tags_group, tags_layout = create_section("SAI LẦM GIAO DỊCH (TAGS)", False)

        tags_chips_layout = QGridLayout()
        tags_chips_layout.setSpacing(4)

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
            btn.setStyleSheet(f"""
                QPushButton#TagChip {{
                    background-color: {self._card_bg};
                    border: 1px solid {self._border_color};
                    border-radius: 10px;
                    padding: 3px 8px;
                    color: {self._label_color};
                    font-size: 11px;
                    font-family: -apple-system, 'Segoe UI', sans-serif;
                }}
                QPushButton#TagChip:checked {{
                    background-color: rgba(239, 68, 68, 0.15);
                    border: 1px solid #ef4444;
                    color: #ef4444;
                    font-weight: bold;
                }}
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
        card_layout.setSpacing(4)

        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        status_lbl = QLabel("Trạng thái lệnh:")
        status_lbl.setStyleSheet(f"color: {self._val_color}; font-size: 12px; font-weight: 600;")
        status_row.addWidget(status_lbl)
        status_row.addWidget(self.status_input, 1)
        card_layout.addLayout(status_row)

        card_layout.addWidget(exec_group)
        card_layout.addWidget(tags_group)

        self.lifecycle_result_label = QLabel("--")
        self.lifecycle_result_label.setObjectName("HelperText")
        self.lifecycle_result_label.setWordWrap(True)
        card_layout.addWidget(self.lifecycle_result_label)

        helper = QLabel("Result R được tính khi có hướng lệnh, entry, SL và giá thoát. Thời gian đóng sẽ tự điền khi trạng thái là Đã đóng lệnh.")
        helper.setObjectName("HelperText")
        helper.setWordWrap(True)
        helper.setStyleSheet(f"color: {self._label_color}; font-size: 11px;")
        card_layout.addWidget(helper)

        frame.layout().addLayout(card_layout)

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
            page_header("Chi tiết nhật ký", "", symbol)
        )
        if not self.entry:
            empty_html = f"<div style='color: {self._label_color}; font-size: 12px;'>Chọn một bản ghi trong màn Nhật ký để xem chi tiết.</div>"
            self.analysis_dec_text.setHtml(empty_html)
            self.analysis_plan_text.setHtml(empty_html)
            self.analysis_ai_text.setHtml(empty_html)
            self.note_input.setPlainText("")
            self._clear_lifecycle_form()
            if hasattr(self, "hero_summary"):
                self.hero_summary.setVisible(False)
            return

        if hasattr(self, "hero_summary"):
            self.hero_summary.setVisible(True)
            self._update_hero_summary()
        dec_html, plan_html, ai_html = self._analysis_html_parts()
        self.analysis_dec_text.setHtml(dec_html)
        self.analysis_plan_text.setHtml(plan_html)
        self.analysis_ai_text.setHtml(ai_html)
        self.analysis_ai_text.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.note_input.setPlainText(self.entry.note)
        self._load_lifecycle_form()

    def _analysis_html(self) -> str:
        dec, plan, ai = self._analysis_html_parts()
        return dec + plan + ai

    def _analysis_html_parts(self) -> tuple[str, str, str]:
        entry = self.entry
        if not entry:
            return "", "", ""

        decision_val = entry.decision or ""
        decision_txt = DECISION_TEXT.get(decision_val, decision_val).upper()
        decision_color = {
            "ready": "#10b981",
            "watch": self._accent,
            "wait": "#fbbf24",
            "wait_for_confirmation": "#fbbf24",
        }.get(decision_val, self._label_color)

        bias_val = entry.direction_bias or ""
        bias_txt = BIAS_TEXT.get(bias_val, bias_val).upper()
        bias_color = {
            "buy": "#10b981",
            "sell": "#ef4444",
        }.get(bias_val, self._val_color)

        perm_val = entry.trade_permission or ""
        perm_txt = {
            "allowed": "ĐƯỢC PHÉP",
            "caution": "THẬN TRỌNG",
            "blocked": "CẤM GIAO DỊCH",
        }.get(perm_val, PERMISSION_TEXT.get(perm_val, perm_val).upper()) if perm_val else "--"
        perm_color = {
            "allowed": "#10b981",
            "caution": "#fbbf24",
        }.get(perm_val, "#ef4444")

        regime_val = entry.market_regime or ""
        regime_txt = {
            "trend_up": "XU HƯỚNG TĂNG",
            "trend_down": "XU HƯỚNG GIẢM",
            "range": "ĐI NGANG (RANGE)",
            "volatile": "BIẾN ĐỘNG MẠNH",
            "trend": "XU HƯỚNG",
            "breakout": "BỨT PHÁ",
            "pullback": "HỒI GIÁ",
        }.get(regime_val, regime_val.upper()) if regime_val else "--"

        scenario_val = entry.selected_scenario or ""
        scenario_txt = {
            "buy_at_support": "MUA TẠI HỖ TRỢ",
            "sell_at_resistance": "BÁN TẠI KHÁNG CỰ",
            "breakout_buy": "MUA PHÁ VỠ (BREAKOUT)",
            "breakout_sell": "BÁN PHÁ VỠ (BREAKDOWN)",
            "counter_trend_buy": "MUA NGƯỢC XU HƯỚNG",
            "counter_trend_sell": "BÁN NGƯỢC XU HƯỚNG",
            "buy": "MUA",
            "sell": "BÁN",
        }.get(scenario_val, scenario_val.upper()) if scenario_val else "--"

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
                    <div style="margin: 6px 0 2px;">
                    <table style="width: 100%; table-layout: fixed; height: 8px; border-collapse: collapse; margin-bottom: 2px;">
                        <tr style="height: 8px;">
                            <td style="background-color: #ef4444; width: {red_pct}%; border-radius: 4px 0 0 4px; height: 8px;"></td>
                            <td style="background-color: #10b981; width: {green_pct}%; border-radius: 0 4px 4px 0; height: 8px;"></td>
                        </tr>
                    </table>
                    <div style="display: flex; justify-content: space-between; font-size: 10px; color: {self._label_color};">
                        <span>SL</span><span>Entry</span><span>TP</span>
                    </div>
                    </div>
                    """
        except Exception:
            pass

        suggested_lot_txt = f"{entry.suggested_lot:.2f}" if entry.suggested_lot is not None else "--"

        label = self._label_color
        val = self._val_color

        dec_html = f"""
        <div style="font-family: -apple-system, 'Segoe UI', sans-serif; line-height: 1.25; font-size: 11px; color: {val};">
          <table width="100%" border="0" cellspacing="0" cellpadding="0" style="width: 100%;">
            <tr>
              <td width="20%" style="color: {label}; padding: 1px 0;">Kết luận:</td>
              <td width="30%" style="font-weight: bold; color: {decision_color}; padding: 1px 0;">{decision_txt}</td>
              <td width="20%" style="color: {label}; padding: 1px 0;">Thiên hướng:</td>
              <td width="30%" style="font-weight: bold; color: {bias_color}; padding: 1px 0;">{bias_txt}</td>
            </tr>
            <tr>
              <td width="20%" style="color: {label}; padding: 1px 0;">TT:</td>
              <td width="30%" style="font-weight: bold; color: {val}; padding: 1px 0;">{regime_txt}</td>
              <td width="20%" style="color: {label}; padding: 1px 0;">Quyền GD:</td>
              <td width="30%" style="font-weight: bold; color: {perm_color}; padding: 1px 0;">{perm_txt}</td>
            </tr>
            <tr>
              <td width="20%" style="color: {label}; padding: 1px 0;">Mua/Bán:</td>
              <td width="30%" style="font-weight: bold; padding: 1px 0;"><span style="color: #10b981;">{entry.buy_score}</span> / <span style="color: #ef4444;">{entry.sell_score}</span></td>
              <td width="20%">&nbsp;</td>
              <td width="30%">&nbsp;</td>
            </tr>
          </table>
        </div>
        """

        plan_html = f"""
        <div style="font-family: -apple-system, 'Segoe UI', sans-serif; line-height: 1.25; font-size: 11px; color: {val};">
          <table width="100%" border="0" cellspacing="0" cellpadding="0" style="width: 100%;">
            <tr>
              <td width="20%" style="color: {label}; padding: 1px 0;">Kịch bản:</td>
              <td width="30%" style="font-weight: bold; color: {val}; padding: 1px 0;">{scenario_txt}</td>
              <td width="20%" style="color: {label}; padding: 1px 0;">Vùng vào:</td>
              <td width="30%" style="color: #fbbf24; font-weight: bold; padding: 1px 0;">{entry_zone_txt}</td>
            </tr>
            <tr>
              <td width="20%" style="color: {label}; padding: 1px 0;">SL:</td>
              <td width="30%" style="color: #ef4444; font-weight: bold; padding: 1px 0;">{entry.stop_loss or '--'}</td>
              <td width="20%" style="color: {label}; padding: 1px 0;">TP:</td>
              <td width="30%" style="color: #10b981; font-weight: bold; padding: 1px 0;">{take_profit_txt}</td>
            </tr>
            <tr>
              <td width="20%" style="color: {label}; padding: 1px 0;">R:R:</td>
              <td width="30%" style="font-weight: bold; color: {val}; padding: 1px 0;">{entry.risk_reward or '--'}</td>
              <td width="20%" style="color: {label}; padding: 1px 0;">Lot:</td>
              <td width="30%" style="font-weight: bold; color: {val}; padding: 1px 0;">{suggested_lot_txt}</td>
            </tr>
          </table>
          {rr_bar_html}
        </div>
        """

        ai_text = entry.ai_commentary or '--'
        if "Imported from MT5 history" in ai_text:
            ai_text = ai_text.replace("Imported from MT5 history.", "Đã nhập từ lịch sử MT5.").replace("Imported from MT5 history", "Đã nhập từ lịch sử MT5")

        ai_html = f"""
        <div align="left" style="font-family: -apple-system, 'Segoe UI', sans-serif; line-height: 1.2; font-size: 11.5px; color: {val}; text-align: left; margin: 0; padding: 0;">
          <p align="left" style="text-align: left; margin: 0; padding: 0;">{ai_text}</p>
        </div>
        """

        return dec_html, plan_html, ai_html

    def _clear_lifecycle_form(self) -> None:
        if hasattr(self, "status_input"):
            self.status_input.setCurrentIndex(0)
        self.opened_at_chk.setChecked(False)
        self.closed_at_chk.setChecked(False)
        self.actual_lot_edit.setValue(0.0)
        self.actual_entry_edit.setValue(0.0)
        self.actual_sl_edit.setValue(0.0)
        self.actual_tp_edit.setValue(0.0)
        self.actual_exit_edit.setValue(0.0)
        self.result_amount_edit.setValue(0.0)
        self.exit_reason_edit.setText("")
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
