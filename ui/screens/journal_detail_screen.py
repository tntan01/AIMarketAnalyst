from __future__ import annotations

import json

from datetime import UTC, datetime

from PyQt6.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QTextEdit, QVBoxLayout, QWidget

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
        side = QVBoxLayout()
        side.setSpacing(10)
        side.addWidget(self._note_card(), 1)
        side.addWidget(self._lifecycle_card(), 2)
        body.addLayout(side, 1)
        self.root.addLayout(body, 1)

        actions = QHBoxLayout()
        self.back_button = action_button("Quay lại nhật ký")
        self.export_button = action_button("Xuất JSON")
        self.delete_button = action_button("Xóa bản ghi")
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

    def _note_card(self):
        frame = card("Ghi chú cá nhân")
        self.note_input = QTextEdit()
        self.note_input.setObjectName("ReadonlyText")
        frame.layout().addWidget(self.note_input, 1)
        self.save_note_button = action_button("Lưu ghi chú", primary=True)
        self.save_note_button.clicked.connect(self._save_note)
        frame.layout().addWidget(self.save_note_button)
        return frame

    def _lifecycle_card(self):
        frame = card("Vòng đời giao dịch")
        self.status_input = QComboBox()
        for text, value in [
            ("Đã lập kế hoạch", "planned"),
            ("Đã mở lệnh", "opened"),
            ("Đã đóng lệnh", "closed"),
            ("Đã hủy", "cancelled"),
            ("Bỏ lỡ", "missed"),
        ]:
            self.status_input.addItem(text, value)

        self.lifecycle_inputs: dict[str, QLineEdit] = {}
        fields = [
            ("opened_at", "Thời gian mở"),
            ("closed_at", "Thời gian đóng"),
            ("planned_lot", "Lot kế hoạch"),
            ("actual_lot", "Lot thực tế"),
            ("planned_entry", "Entry kế hoạch"),
            ("actual_entry", "Entry thực tế"),
            ("planned_sl", "SL kế hoạch"),
            ("actual_sl", "SL thực tế"),
            ("planned_tp", "TP kế hoạch"),
            ("actual_tp", "TP thực tế"),
            ("actual_exit", "Giá thoát thực tế"),
            ("result_amount", "Lãi/lỗ"),
            ("exit_reason", "Lý do thoát"),
            ("manual_mistake_tags", "Tag lỗi"),
        ]
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        grid.addWidget(QLabel("Trạng thái"), 0, 0)
        grid.addWidget(self.status_input, 0, 1)
        for index, (key, label) in enumerate(fields, start=1):
            field = QLineEdit()
            field.setPlaceholderText("Thời gian ISO" if key in {"opened_at", "closed_at"} else "")
            self.lifecycle_inputs[key] = field
            grid.addWidget(QLabel(label), index, 0)
            grid.addWidget(field, index, 1)
        frame.layout().addLayout(grid)

        self.lifecycle_result_label = QLabel("--")
        self.lifecycle_result_label.setObjectName("HelperText")
        self.lifecycle_result_label.setWordWrap(True)
        frame.layout().addWidget(self.lifecycle_result_label)
        helper = QLabel("Result R được tính khi có hướng lệnh, entry, SL và giá thoát. Thời gian đóng sẽ tự điền khi trạng thái là Đã đóng lệnh.")
        helper.setObjectName("HelperText")
        helper.setWordWrap(True)
        frame.layout().addWidget(helper)

        self.save_lifecycle_button = action_button("Lưu kết quả lệnh", primary=True)
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
            self.analysis_text.setPlainText("Chọn một bản ghi trong màn Nhật ký để xem chi tiết.")
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
        self.analysis_text.setPlainText(self._analysis_text())
        self.note_input.setPlainText(self.entry.note)
        self._load_lifecycle_form()

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

    def _clear_lifecycle_form(self) -> None:
        if hasattr(self, "status_input"):
            self.status_input.setCurrentIndex(0)
        for field in getattr(self, "lifecycle_inputs", {}).values():
            field.setText("")
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
        for key, field in self.lifecycle_inputs.items():
            value = getattr(entry, key, None)
            field.setText("" if value in (None, "") else str(value))
        result = entry.result_r if entry.result_r is not None else "--"
        pct = entry.result_pct if entry.result_pct is not None else "--"
        quality = entry.execution_quality_score if entry.execution_quality_score is not None else "--"
        self.lifecycle_result_label.setText(f"Kết quả: {result}R | {pct}% | Chất lượng thực thi: {quality}")

    def _save_lifecycle(self) -> None:
        if not self.entry or self.entry.id is None:
            return
        updates: dict[str, object] = {"trade_status": self.status_input.currentData()}
        number_fields = {
            "planned_lot",
            "actual_lot",
            "planned_entry",
            "actual_entry",
            "planned_sl",
            "actual_sl",
            "planned_tp",
            "actual_tp",
            "actual_exit",
            "result_amount",
        }
        for key, field in self.lifecycle_inputs.items():
            text = field.text().strip()
            updates[key] = parse_optional_float(text) if key in number_fields else text
        if updates.get("trade_status") == "closed" and not updates.get("closed_at"):
            updates["closed_at"] = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        self.journal_controller.update_lifecycle(self.entry.id, updates)
        self.entry = self.journal_controller.get_entry(self.entry.id)
        self._render()
        QMessageBox.information(self, "Đã lưu", "Đã lưu vòng đời/kết quả giao dịch.")

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
