from __future__ import annotations

import json

from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QMessageBox, QTextEdit, QVBoxLayout, QWidget

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
        self.root.addLayout(self.general_grid)

        body = QHBoxLayout()
        body.setSpacing(10)
        body.addWidget(self._saved_analysis(), 2)
        body.addWidget(self._note_card(), 1)
        self.root.addLayout(body, 1)

        actions = QHBoxLayout()
        self.back_button = action_button("Quay lại nhật ký")
        self.rerun_button = action_button("Phân tích mới cùng mã", primary=True)
        self.export_button = action_button("Xuất JSON")
        self.delete_button = action_button("Xóa bản ghi")
        if self.navigate:
            self.back_button.clicked.connect(lambda: self.navigate("journal"))
            self.rerun_button.clicked.connect(self._run_new_analysis)
        self.export_button.clicked.connect(self._export_json)
        self.delete_button.clicked.connect(self._delete_entry)
        actions.addWidget(self.back_button)
        actions.addStretch(1)
        actions.addWidget(self.export_button)
        actions.addWidget(self.delete_button)
        actions.addWidget(self.rerun_button)
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

    def _note_card(self):
        frame = card("Ghi chú cá nhân")
        self.note_input = QTextEdit()
        self.note_input.setObjectName("ReadonlyText")
        frame.layout().addWidget(self.note_input, 1)
        self.save_note_button = action_button("Lưu ghi chú", primary=True)
        self.save_note_button.clicked.connect(self._save_note)
        frame.layout().addWidget(self.save_note_button)
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
            self.analysis_text.setPlainText("Chọn một bản ghi trong màn Nhật ký để xem chi tiết.")
            self.note_input.setPlainText("")
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
        self.analysis_text.setPlainText(self._analysis_text())
        self.note_input.setPlainText(self.entry.note)

    def _analysis_text(self) -> str:
        entry = self.entry
        if not entry:
            return ""
        return "\n".join(
            [
                "KẾT LUẬN ĐÃ LƯU",
                f"Kết luận: {DECISION_TEXT.get(entry.decision, entry.decision)}",
                f"Thiên hướng: {BIAS_TEXT.get(entry.direction_bias, entry.direction_bias)}",
                f"Trạng thái thị trường: {entry.market_regime or '--'}",
                f"Điểm mua/bán: {entry.buy_score} / {entry.sell_score}",
                "",
                "KẾ HOẠCH GIAO DỊCH ĐÃ LƯU",
                f"Kịch bản: {entry.selected_scenario or '--'}",
                f"Vùng vào lệnh: {format_json_text(entry.entry_zone)}",
                f"SL: {entry.stop_loss or '--'}",
                f"TP: {format_json_text(entry.take_profit)}",
                f"R:R: {entry.risk_reward or '--'}",
                f"Lot đề xuất: {entry.suggested_lot if entry.suggested_lot is not None else '--'}",
                "",
                "NHẬN ĐỊNH AI ĐÃ LƯU",
                entry.ai_commentary or "--",
            ]
        )

    def _save_note(self) -> None:
        if not self.entry or self.entry.id is None:
            return
        self.journal_controller.update_note(self.entry.id, self.note_input.toPlainText())
        self.entry = self.journal_controller.get_entry(self.entry.id)
        QMessageBox.information(self, "Đã lưu", "Đã lưu ghi chú cá nhân.")

    def _export_json(self) -> None:
        if not self.entry:
            return
        path = self.journal_controller.export_entry_json(self.entry)
        QMessageBox.information(self, "Đã xuất JSON", f"Đã xuất dữ liệu vào:\n{path}")

    def _delete_entry(self) -> None:
        if not self.entry or self.entry.id is None:
            return
        self.journal_controller.delete_entry(self.entry.id)
        if self.navigate:
            self.navigate("journal")

    def _run_new_analysis(self) -> None:
        if self.entry and self.navigate:
            self.navigate("analysis_input", {"symbol": self.entry.symbol, "broker_symbol": self.entry.broker_symbol})


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
