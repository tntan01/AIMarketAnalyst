from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import QAbstractTableModel, QDate, QModelIndex, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QHeaderView,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from controllers.journal_controller import JournalController
from services.journal_service import JournalEntry, JournalFilter
from ui.screens.shared import action_button, card, labeled_value, page_header


DECISION_TEXT = {
    "ready": "Sẵn sàng",
    "watch": "Theo dõi",
    "wait": "Chờ",
    "wait_for_confirmation": "Chờ",
    "stand_aside": "Đứng ngoài",
    "skip": "Bỏ qua",
}
BIAS_TEXT = {"buy": "Mua", "sell": "Bán", "neutral": "Trung lập", "stand_aside": "Đứng ngoài"}
PERMISSION_TEXT = {"allowed": "Được phép", "caution": "Cẩn trọng", "blocked": "Bị chặn"}
MODE_TEXT: dict[str, str] = {}


class JournalTableModel(QAbstractTableModel):
    COLUMNS = [
        ("timestamp_utc", "Thời gian"),
        ("symbol", "Mã"),
        ("mode", "Chế độ"),
        ("decision", "Kết luận"),
        ("direction_bias", "Thiên hướng"),
        ("buy_score", "Mua"),
        ("sell_score", "Bán"),
        ("trade_permission", "Quyền"),
        ("note", "Ghi chú"),
        ("open", "Mở"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.entries: list[JournalEntry] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.entries)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        entry = self.entries[index.row()]
        key = self.COLUMNS[index.column()][0]
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display(entry, key)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if key in {"buy_score", "sell_score", "open"}:
                return Qt.AlignmentFlag.AlignCenter
            return Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        if role == Qt.ItemDataRole.ForegroundRole:
            if key == "decision":
                return {"ready": QColor("#5eead4"), "watch": QColor("#93c5fd"), "wait_for_confirmation": QColor("#facc15")}.get(entry.decision)
            if key == "trade_permission":
                return {"allowed": QColor("#5eead4"), "caution": QColor("#facc15"), "blocked": QColor("#94a3b8")}.get(entry.trade_permission)
        if role == Qt.ItemDataRole.ToolTipRole:
            return entry.note or entry.ai_commentary
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self.COLUMNS[section][1]
        return str(section + 1)

    def set_entries(self, entries: list[JournalEntry]) -> None:
        self.beginResetModel()
        self.entries = entries
        self.endResetModel()

    def entry_at(self, row: int) -> JournalEntry | None:
        if 0 <= row < len(self.entries):
            return self.entries[row]
        return None

    def _display(self, entry: JournalEntry, key: str) -> str:
        if key == "open":
            return "Mở"
        if key == "timestamp_utc":
            return format_time(entry.timestamp_utc)
        if key == "mode":
            return MODE_TEXT.get(entry.mode, entry.mode)
        if key == "decision":
            return DECISION_TEXT.get(entry.decision, entry.decision)
        if key == "direction_bias":
            return BIAS_TEXT.get(entry.direction_bias, entry.direction_bias)
        if key == "trade_permission":
            return PERMISSION_TEXT.get(entry.trade_permission, entry.trade_permission)
        value = getattr(entry, key)
        return str(value if value not in (None, "") else "--")


class JournalScreen(QWidget):
    def __init__(self, navigate=None) -> None:
        super().__init__()
        self.navigate = navigate
        self.journal_controller = JournalController()
        self.table_model = JournalTableModel()
        self.setObjectName("FormScreen")
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)
        root.addWidget(page_header("Nhật ký phân tích", "Lọc, mở lại và ghi chú các phân tích đã lưu.", "SQLite"))
        root.addWidget(self._filters())
        root.addWidget(self._table_card(), 1)
        root.addWidget(self._stats_bar())
        self.refresh_status()

    def _filters(self) -> QFrame:
        frame = card("Bộ lọc")
        frame.layout().setSpacing(8)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        self.date_from_input = QDateEdit()
        self.date_from_input.setCalendarPopup(True)
        self.date_from_input.setDate(QDate.currentDate().addMonths(-1))
        self.date_to_input = QDateEdit()
        self.date_to_input.setCalendarPopup(True)
        self.date_to_input.setDate(QDate.currentDate())
        self.symbol_input = QComboBox()
        self.decision_input = QComboBox()
        self.decision_input.addItems(["Tất cả", "Sẵn sàng", "Theo dõi", "Chờ", "Đứng ngoài"])
        self.permission_input = QComboBox()
        self.permission_input.addItems(["Tất cả", "Được phép", "Cẩn trọng", "Bị chặn"])
        self.min_score_input = QDoubleSpinBox()
        self.min_score_input.setRange(0, 100)
        self.min_score_input.setDecimals(0)
        self.min_score_input.setValue(0)

        fields = [
            ("Từ ngày", self.date_from_input),
            ("Đến ngày", self.date_to_input),
            ("Mã", self.symbol_input),
            ("Kết luận", self.decision_input),
            ("Quyền", self.permission_input),
            ("Điểm tối thiểu", self.min_score_input),
        ]
        for index, (label, field) in enumerate(fields):
            grid.addWidget(self._compact_field(label, field), index // 3, index % 3)
        frame.layout().addLayout(grid)

        actions = QHBoxLayout()
        actions.addStretch(1)
        apply_button = action_button("Áp dụng", primary=True)
        clear_button = action_button("Xóa bộ lọc")
        apply_button.clicked.connect(self._apply_filters)
        clear_button.clicked.connect(self._clear_filters)
        actions.addWidget(apply_button)
        actions.addWidget(clear_button)
        frame.layout().addLayout(actions)
        return frame

    def _table_card(self) -> QFrame:
        frame = card("Danh sách nhật ký")
        self.table = QTableView()
        self.table.setObjectName("DataTable")
        self.table.setModel(self.table_model)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.clicked.connect(self._table_clicked)
        frame.layout().addWidget(self.table, 1)

        self.empty_label = QLabel("")
        self.empty_label.setObjectName("HelperText")
        self.empty_label.setWordWrap(True)
        frame.layout().addWidget(self.empty_label)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.open_button = action_button("Mở chi tiết", primary=True)
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_selected)
        actions.addWidget(self.open_button)
        frame.layout().addLayout(actions)
        return frame

    def _stats_bar(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.stat_labels: dict[str, QLabel] = {}
        for title in ["Tổng", "Sẵn sàng", "Theo dõi", "Chờ", "Đứng ngoài", "Mã nhiều nhất"]:
            item = labeled_value(title, "--")
            self.stat_labels[title] = item.findChildren(QLabel)[1]
            layout.addWidget(item)
        return widget

    def refresh_status(self) -> None:
        self._refresh_symbol_filter()
        self._apply_filters()

    def _refresh_symbol_filter(self) -> None:
        current = self.symbol_input.currentText() if hasattr(self, "symbol_input") else "Tất cả"
        self.symbol_input.blockSignals(True)
        self.symbol_input.clear()
        self.symbol_input.addItem("Tất cả", None)
        for symbol in self.journal_controller.symbols():
            self.symbol_input.addItem(symbol, symbol)
        if current:
            index = self.symbol_input.findText(current)
            if index >= 0:
                self.symbol_input.setCurrentIndex(index)
        self.symbol_input.blockSignals(False)

    def _apply_filters(self) -> None:
        filters = JournalFilter(
            date_from=self.date_from_input.date().toString("yyyy-MM-dd"),
            date_to=self.date_to_input.date().toString("yyyy-MM-dd"),
            symbol=self.symbol_input.currentData(),
            decision=decision_value(self.decision_input.currentText()),
            permission=permission_value(self.permission_input.currentText()),
            min_score=int(self.min_score_input.value()),
        )
        entries = self.journal_controller.list_entries(filters)
        self.table_model.set_entries(entries)
        self.empty_label.setText("" if entries else "Chưa có bản ghi phù hợp bộ lọc.")
        self.open_button.setEnabled(False)
        self._configure_table_columns()
        self._refresh_stats()

    def _clear_filters(self) -> None:
        self.date_from_input.setDate(QDate.currentDate().addYears(-10))
        self.date_to_input.setDate(QDate.currentDate())
        self.symbol_input.setCurrentIndex(0)
        self.decision_input.setCurrentIndex(0)
        self.permission_input.setCurrentIndex(0)
        self.min_score_input.setValue(0)
        self._apply_filters()

    def _refresh_stats(self) -> None:
        stats = self.journal_controller.stats()
        values = {
            "Tổng": stats.get("total", 0),
            "Sẵn sàng": stats.get("ready", 0),
            "Theo dõi": stats.get("watch", 0),
            "Chờ": stats.get("wait", 0),
            "Đứng ngoài": stats.get("stand_aside", 0),
            "Mã nhiều nhất": stats.get("top_symbol", "--"),
        }
        for title, label in self.stat_labels.items():
            label.setText(str(values.get(title, "--")))

    def _table_clicked(self, index: QModelIndex) -> None:
        self.open_button.setEnabled(index.isValid())
        if index.column() == len(JournalTableModel.COLUMNS) - 1:
            self._open_row(index.row())

    def _open_selected(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        if selected:
            self._open_row(selected[0].row())

    def _open_row(self, row_index: int) -> None:
        entry = self.table_model.entry_at(row_index)
        if entry and self.navigate:
            self.navigate("journal_detail", {"journal_id": entry.id})

    def _configure_table_columns(self) -> None:
        header = self.table.horizontalHeader()
        widths = {0: 132, 1: 72, 2: 112, 3: 82, 4: 82, 5: 48, 6: 48, 7: 84, 9: 48}
        for column, width in widths.items():
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(column, width)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)

    def _compact_field(self, label: str, field: QWidget) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label_widget = QLabel(label)
        label_widget.setObjectName("FormLabel")
        label_widget.setMinimumWidth(90)
        layout.addWidget(label_widget)
        layout.addWidget(field, 1)
        return widget


def decision_value(text: str) -> str | None:
    return {"Sẵn sàng": "ready", "Theo dõi": "watch", "Chờ": "wait_for_confirmation", "Đứng ngoài": "stand_aside"}.get(text)


def permission_value(text: str) -> str | None:
    return {"Được phép": "allowed", "Cẩn trọng": "caution", "Bị chặn": "blocked"}.get(text)


def format_time(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
        return parsed.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value
