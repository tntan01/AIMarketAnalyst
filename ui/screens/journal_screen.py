from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import QAbstractTableModel, QDate, QModelIndex, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QHeaderView,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
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
    "closed": "Đã đóng",
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
        ("result_r", "K.quả R"),
        ("result_amount", "Lợi nhuận"),
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
            if key in {"buy_score", "sell_score", "result_r", "result_amount", "open"}:
                return Qt.AlignmentFlag.AlignCenter
            return Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        if role == Qt.ItemDataRole.ForegroundRole:
            if key == "open":
                return QColor("#38bdf8")
            if key == "decision":
                return {"ready": QColor("#5eead4"), "watch": QColor("#93c5fd"), "wait_for_confirmation": QColor("#facc15")}.get(entry.decision)
            if key == "trade_permission":
                return {"allowed": QColor("#5eead4"), "caution": QColor("#facc15"), "blocked": QColor("#94a3b8")}.get(entry.trade_permission)
            if key == "direction_bias":
                return {"buy": QColor("#22c55e"), "sell": QColor("#fb7185")}.get(entry.direction_bias)
            if key in {"result_r", "result_amount"}:
                val = getattr(entry, key)
                if val is not None:
                    if val > 0:
                        return QColor("#5eead4")
                    elif val < 0:
                        return QColor("#fb7185")
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
            return "Chi tiết ↗"
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
        if key == "result_r":
            if entry.result_r is not None:
                return f"{entry.result_r:+.2f}R"
            return "--"
        if key == "result_amount":
            if entry.result_amount is not None:
                return f"{entry.result_amount:+.2f}"
            return "--"
        value = getattr(entry, key)
        return str(value if value not in (None, "") else "--")


class JournalScreen(QWidget):
    def __init__(self, navigate=None, *, app=None) -> None:
        super().__init__()
        self.navigate = navigate
        self.app = app
        self.journal_controller = (
            app.journal_controller if app else JournalController()
        )
        self.table_model = JournalTableModel()
        self.setObjectName("FormScreen")
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)
        root.addWidget(page_header("Nhật ký phân tích", "Lọc, mở lại và ghi chú các phân tích đã lưu.", "SQLite"))

        tabs = QTabWidget()
        tabs.setObjectName("ContentTabs")

        tab1 = QWidget()
        tab1_layout = QVBoxLayout(tab1)
        tab1_layout.setContentsMargins(0, 8, 0, 0)
        tab1_layout.setSpacing(10)
        tab1_layout.addWidget(self._filters())
        tab1_layout.addWidget(self._table_card(), 1)
        tabs.addTab(tab1, "Nhật ký Phân tích")

        tab2 = QWidget()
        tab2_layout = QVBoxLayout(tab2)
        tab2_layout.setContentsMargins(0, 8, 0, 0)
        tab2_layout.setSpacing(10)
        tab2_layout.addWidget(self._stats_bar())
        tab2_layout.addWidget(self._performance_card(), 1)
        tabs.addTab(tab2, "Thống kê Hiệu suất")

        root.addWidget(tabs, 1)
        self.refresh_status()

    def _filters(self) -> QFrame:
        frame = card()  # Không tiêu đề để giao diện thoáng đãng
        frame.layout().setContentsMargins(12, 8, 12, 8)
        layout = QHBoxLayout()
        layout.setSpacing(10)
        frame.layout().addLayout(layout)

        self.date_from_input = QDateEdit()
        self.date_from_input.setMinimumWidth(135)
        self.date_from_input.setCalendarPopup(True)
        self.date_from_input.setButtonSymbols(QDateEdit.ButtonSymbols.NoButtons)
        self.date_from_input.setDate(QDate.currentDate().addMonths(-1))
        self.date_from_input.setDisplayFormat("dd/MM/yyyy")
        self.date_to_input = QDateEdit()
        self.date_to_input.setMinimumWidth(135)
        self.date_to_input.setCalendarPopup(True)
        self.date_to_input.setButtonSymbols(QDateEdit.ButtonSymbols.NoButtons)
        self.date_to_input.setDate(QDate.currentDate())
        self.date_to_input.setDisplayFormat("dd/MM/yyyy")
        self.symbol_input = QComboBox()
        self.decision_input = QComboBox()
        self.decision_input.addItems(["Tất cả", "Sẵn sàng", "Theo dõi", "Chờ", "Đứng ngoài"])
        self.permission_input = QComboBox()
        self.permission_input.addItems(["Tất cả", "Được phép", "Cẩn trọng", "Bị chặn"])
        self.min_score_input = QSpinBox()
        self.min_score_input.setRange(0, 100)
        self.min_score_input.setValue(0)

        for field in [self.date_from_input, self.date_to_input, self.symbol_input, self.decision_input, self.permission_input, self.min_score_input]:
            field.setObjectName("FilterField")

        layout.addWidget(self._compact_field_horizontal("Từ", self.date_from_input))
        layout.addWidget(self._compact_field_horizontal("Đến", self.date_to_input))
        layout.addWidget(self._compact_field_horizontal("Mã", self.symbol_input))
        layout.addWidget(self._compact_field_horizontal("K.luận", self.decision_input))
        layout.addWidget(self._compact_field_horizontal("Quyền", self.permission_input))
        layout.addWidget(self._compact_field_horizontal("Điểm >=", self.min_score_input))

        layout.addStretch(1)

        apply_button = action_button("✅ Áp dụng", primary=True, color="success")
        clear_button = action_button("🧹 Xóa lọc")
        apply_button.clicked.connect(self._apply_filters)
        clear_button.clicked.connect(self._clear_filters)

        layout.addWidget(apply_button)
        layout.addWidget(clear_button)
        return frame

    def _compact_field_horizontal(self, label: str, field: QWidget) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        lbl = QLabel(label)
        lbl.setObjectName("FormLabel")
        layout.addWidget(lbl)
        layout.addWidget(field)
        return widget

    def _table_card(self) -> QFrame:
        frame = card("Danh sách nhật ký")
        self.table = QTableView()
        self.table.setObjectName("DataTable")
        self.table.setModel(self.table_model)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.clicked.connect(self._table_clicked)
        frame.layout().addWidget(self.table, 1)

        self.empty_label = QLabel("")
        self.empty_label.setObjectName("HelperText")
        self.empty_label.setWordWrap(True)
        frame.layout().addWidget(self.empty_label)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.open_button = action_button("🔍 Mở chi tiết", primary=True)
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_selected)
        actions.addWidget(self.open_button)
        frame.layout().addLayout(actions)
        return frame

    def _stats_bar(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        self.stat_labels: dict[str, QLabel] = {}
        for title in ["Tổng", "Sẵn sàng", "Theo dõi", "Chờ", "Đứng ngoài", "Mã nhiều nhất"]:
            item = self._compact_metric(title, "--", is_stat=True)
            layout.addWidget(item)
        layout.addStretch(1)
        return widget

    def _performance_card(self) -> QFrame:
        frame = card("Bảng hiệu suất")
        actions = QHBoxLayout()
        self.performance_scope_label = QLabel("Chỉ tính lệnh đã đóng. Cần Result R để tính các chỉ số hiệu suất theo R.")
        self.performance_scope_label.setObjectName("HelperText")
        self.performance_scope_label.setWordWrap(True)
        actions.addWidget(self.performance_scope_label, 1)
        actions.addStretch(1)
        
        explain_button = action_button("📖 Giải thích")
        explain_button.clicked.connect(self._show_explanation_dialog)
        actions.addWidget(explain_button)
        
        refresh_button = action_button("🔄 Làm mới", primary=True)
        refresh_button.clicked.connect(self._refresh_performance)
        actions.addWidget(refresh_button)
        
        self.sync_mt5_button = action_button("⬇️ Đồng bộ MT5", primary=True, color="info")
        self.sync_mt5_button.setToolTip("Nhập các lệnh đã đóng từ lịch sử MT5 trong 90 ngày gần nhất.")
        self.sync_mt5_button.clicked.connect(self._sync_mt5_history)
        actions.addWidget(self.sync_mt5_button)
        frame.layout().addLayout(actions)

        self.performance_labels: dict[str, QLabel] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)
        metrics = [
            ("Đã đóng", "0"),
            ("Tỷ lệ thắng", "0%"),
            ("Kỳ vọng", "0R"),
            ("Tổng R", "0R"),
            ("Lãi/lỗ ròng", "0"),
            ("Hệ số lợi nhuận", "0"),
            ("DD tối đa", "0R"),
            ("Thắng TB", "0R"),
            ("Thua TB", "0R"),
            ("Chất lượng thực thi", "0"),
        ]
        for index, (title, value) in enumerate(metrics):
            item = self._compact_metric(title, value, is_stat=False)
            grid.addWidget(item, index // 5, index % 5)
        frame.layout().addLayout(grid)

        tables = QHBoxLayout()
        tables.setSpacing(10)
        self.performance_group_table = QTableWidget()
        self.performance_group_table.setObjectName("DataTable")
        self.performance_group_table.setColumnCount(7)
        self.performance_group_table.setHorizontalHeaderLabels(["Nhóm", "Tên", "Lệnh", "Thắng %", "Kỳ vọng R", "Tổng R", "P/L"])
        self.performance_group_table.verticalHeader().setVisible(False)
        self.performance_group_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.performance_group_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.performance_group_table.setAlternatingRowColors(True)
        self.performance_group_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.performance_group_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in range(2, 7):
            self.performance_group_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        tables.addWidget(self.performance_group_table, 3)

        self.recent_trade_table = QTableWidget()
        self.recent_trade_table.setObjectName("DataTable")
        self.recent_trade_table.setColumnCount(6)
        self.recent_trade_table.setHorizontalHeaderLabels(["Đóng lúc", "Mã", "Hướng", "R", "P/L", "CL"])
        self.recent_trade_table.verticalHeader().setVisible(False)
        self.recent_trade_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.recent_trade_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.recent_trade_table.setAlternatingRowColors(True)
        self.recent_trade_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.recent_trade_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3, 5):
            self.recent_trade_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        tables.addWidget(self.recent_trade_table, 2)
        frame.layout().addLayout(tables, 1)

        self.performance_empty_label = QLabel("")
        self.performance_empty_label.setObjectName("HelperText")
        self.performance_empty_label.setWordWrap(True)
        frame.layout().addWidget(self.performance_empty_label)
        self.performance_sync_label = QLabel("")
        self.performance_sync_label.setObjectName("HelperText")
        self.performance_sync_label.setWordWrap(True)
        frame.layout().addWidget(self.performance_sync_label)
        return frame

    def _show_explanation_dialog(self) -> None:
        dialog = MetricsExplanationDialog(self)
        dialog.exec()

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
        self._refresh_performance()

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

    def _refresh_performance(self) -> None:
        data = self.journal_controller.performance_summary()
        summary = data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}
        values = {
            "Đã đóng": summary.get("closed_trades", 0),
            "Tỷ lệ thắng": format_metric(summary.get("win_rate"), "%"),
            "Kỳ vọng": format_metric(summary.get("expectancy_r"), "R"),
            "Tổng R": format_metric(summary.get("total_r"), "R"),
            "Lãi/lỗ ròng": format_metric(summary.get("net_amount")),
            "Hệ số lợi nhuận": format_metric(summary.get("profit_factor")),
            "DD tối đa": format_metric(summary.get("max_drawdown_r"), "R"),
            "Thắng TB": format_metric(summary.get("average_win_r"), "R"),
            "Thua TB": format_metric(summary.get("average_loss_r"), "R"),
            "Chất lượng thực thi": format_metric(summary.get("average_execution_quality")),
        }
        for title, label in self.performance_labels.items():
            label.setText(str(values.get(title, "--")))
            if title == "Lãi/lỗ ròng":
                net_amount = summary.get("net_amount")
                if isinstance(net_amount, (int, float)):
                    if net_amount > 0:
                        label.setStyleSheet("color: #10b981;")
                    elif net_amount < 0:
                        label.setStyleSheet("color: #ef4444;")
                    else:
                        label.setStyleSheet("")
                else:
                    label.setStyleSheet("")
        self._fill_group_table(data)
        recent = data.get("recent", []) if isinstance(data.get("recent"), list) else []
        self._fill_recent_trade_table(recent)
        closed = int(summary.get("closed_trades", 0) or 0)
        r_trades = int(summary.get("r_trades", 0) or 0)
        if not closed:
            message = "Chưa có lệnh đã đóng. Hãy đóng một lệnh trong nhật ký hoặc dùng Đồng bộ MT5."
        elif not r_trades:
            message = "Đã có lệnh đóng, nhưng chưa có lệnh nào có Result R. Hãy điền SL/entry/giá thoát để tính kỳ vọng theo R."
        else:
            message = ""
        self.performance_empty_label.setText(message)

    def _fill_group_table(self, data: dict[str, object]) -> None:
        rows: list[tuple[str, dict[str, object]]] = []
        for group_key, title in [
            ("by_symbol", "Mã"),
            ("by_setup", "Setup"),
            ("by_regime", "Regime"),
            ("by_session", "Phiên"),
            ("by_direction", "Hướng"),
        ]:
            group_rows = data.get(group_key, [])
            if not isinstance(group_rows, list):
                continue
            for row in group_rows:
                if isinstance(row, dict):
                    rows.append((title, row))
        self.performance_group_table.setRowCount(len(rows))
        for row_index, (group, row) in enumerate(rows):
            values = [
                group,
                row.get("label", "--"),
                row.get("trades", 0),
                format_metric(row.get("win_rate"), "%"),
                format_metric(row.get("expectancy_r"), "R"),
                format_metric(row.get("total_r"), "R"),
                format_metric(row.get("net_amount")),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column >= 2:
                    item.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter))
                if column in {4, 5, 6}:
                    color_item_by_number(item, str(value))
                self.performance_group_table.setItem(row_index, column, item)

    def _fill_recent_trade_table(self, rows: list[object]) -> None:
        clean_rows = [row for row in rows if isinstance(row, dict)]
        self.recent_trade_table.setRowCount(len(clean_rows))
        for row_index, row in enumerate(clean_rows):
            values = [
                format_short_time(str(row.get("closed_at") or "")),
                row.get("symbol", "--"),
                row.get("direction", "--"),
                format_metric(row.get("result_r"), "R"),
                format_metric(row.get("result_amount")),
                row.get("execution_quality_score") if row.get("execution_quality_score") is not None else "--",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column in {2, 3, 5}:
                    item.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter))
                if column in {3, 4}:
                    color_item_by_number(item, str(value))
                self.recent_trade_table.setItem(row_index, column, item)

    def _sync_mt5_history(self) -> None:
        self.sync_mt5_button.setEnabled(False)
        self.sync_mt5_button.setText("Đang đồng bộ...")
        try:
            result = self.journal_controller.sync_mt5_history(days=90)
        except Exception as exc:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Đồng bộ MT5 thất bại")
            msg_box.setText(str(exc))
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.addButton(action_button("❌ Đóng"), QMessageBox.ButtonRole.AcceptRole)
            msg_box.exec()
            return
        finally:
            self.sync_mt5_button.setText("Đồng bộ MT5")
            self.sync_mt5_button.setEnabled(True)
        self.refresh_status()
        self.performance_sync_label.setText(
            f"Lần đồng bộ MT5 gần nhất: nhận {result.get('received', 0)}, tạo mới {result.get('created', 0)}, cập nhật {result.get('updated', 0)}, bỏ qua {result.get('skipped', 0)}."
        )
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Đồng bộ MT5 hoàn tất")
        msg_box.setText(
            f"Nhận: {result.get('received', 0)}\n"
            f"Tạo mới: {result.get('created', 0)}\n"
            f"Cập nhật: {result.get('updated', 0)}\n"
            f"Bỏ qua: {result.get('skipped', 0)}\n"
            f"Lỗi: {len(result.get('errors', [])) if isinstance(result.get('errors'), list) else 0}"
        )
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.addButton(action_button("❌ Đóng"), QMessageBox.ButtonRole.AcceptRole)
        msg_box.exec()

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
        widths = {
            0: 135,  # Thời gian
            1: 75,   # Mã
            2: 85,   # Chế độ
            3: 90,   # Kết luận
            4: 95,   # Thiên hướng
            5: 48,   # Mua (score)
            6: 48,   # Bán (score)
            7: 90,   # Quyền
            8: 85,   # Kết quả R
            9: 90,   # Lợi nhuận
            11: 80,  # Mở
        }
        for column, width in widths.items():
            if column < len(JournalTableModel.COLUMNS):
                header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
                self.table.setColumnWidth(column, width)
        if len(JournalTableModel.COLUMNS) > 10:
            header.setSectionResizeMode(10, QHeaderView.ResizeMode.Stretch)

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

    def _compact_metric(self, title: str, val: str, is_stat: bool = False) -> QWidget:
        w = QWidget()
        l = QHBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(6)
        t = QLabel(f"{title}:")
        t.setObjectName("FormLabel")
        v = QLabel(val)
        v.setObjectName("MiniStatValue")
        if is_stat:
            self.stat_labels[title] = v
        else:
            self.performance_labels[title] = v
        l.addWidget(t)
        l.addWidget(v)
        l.addStretch(1)
        return w


class MetricsExplanationDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Giải thích các chỉ số")
        self.setMinimumSize(800, 600)
        self.setObjectName("AnalysisDetailDialog")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        
        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setObjectName("ChartPanel")
        
        html = """
        <style>
            body { font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; font-size: 13px; color: #e5e7eb; }
            table { width: 100%; border-collapse: collapse; margin-bottom: 24px; }
            th { text-align: left; padding: 10px; border-bottom: 1px solid #38bdf8; color: #38bdf8; font-weight: normal; font-size: 14px;}
            td { padding: 8px 10px; border-bottom: 1px solid #2b3545; vertical-align: top; }
            .term { color: #5eead4; }
            .highlight { color: #facc15; }
            .section-title { color: #38bdf8; font-weight: normal; font-size: 16px; margin-top: 10px; margin-bottom: 10px; }
        </style>
        <body>
            <div class='section-title'>Chỉ số hiệu suất (Performance Metrics)</div>
            <table>
                <tr>
                    <th width="30%">Chỉ số</th>
                    <th>Ý nghĩa & Ứng dụng</th>
                </tr>
                <tr>
                    <td><span class="term">Đã đóng</span></td>
                    <td>Tổng số lệnh giao dịch đã kết thúc và có kết quả cuối cùng.</td>
                </tr>
                <tr>
                    <td><span class="term">Tỷ lệ thắng (Win rate)</span></td>
                    <td>Tỉ lệ phần trăm các lệnh mang lại lợi nhuận. Chỉ số này cần được kết hợp với <span class="highlight">Kỳ vọng</span> để biết hệ thống có thực sự sinh lời hay không.</td>
                </tr>
                <tr>
                    <td><span class="term">Kỳ vọng (Expectancy)</span></td>
                    <td>Trung bình mỗi lệnh bạn mang về bao nhiêu <span class="highlight">đơn vị rủi ro (R)</span>. Nếu giá trị này lớn hơn 0, hệ thống của bạn có lợi thế toán học trong dài hạn.</td>
                </tr>
                <tr>
                    <td><span class="term">Tổng R</span></td>
                    <td>Tổng lợi nhuận được quy đổi ra <span class="highlight">đơn vị R</span>. Đây là thước đo chuẩn xác nhất về hiệu suất độc lập với quy mô vốn.</td>
                </tr>
                <tr>
                    <td><span class="term">Lãi/lỗ ròng (Net P/L)</span></td>
                    <td>Tổng số tiền lợi nhuận hoặc thua lỗ thực tế thu về tài khoản.</td>
                </tr>
                <tr>
                    <td><span class="term">Hệ số lợi nhuận (Profit Factor)</span></td>
                    <td>Tỉ lệ giữa tổng số tiền kiếm được và tổng số tiền mất đi. Giá trị <span class="highlight">trên 1.0</span> cho thấy chiến lược đang có lãi.</td>
                </tr>
                <tr>
                    <td><span class="term">DD tối đa (Max Drawdown)</span></td>
                    <td>Chuỗi sụt giảm tài khoản sâu nhất từ mức đỉnh (tính theo R). Dùng để đánh giá <span class="highlight">mức độ rủi ro</span> của hệ thống.</td>
                </tr>
                <tr>
                    <td><span class="term">Thắng TB / Thua TB</span></td>
                    <td>Số R trung bình đạt được khi lệnh thắng, và số R trung bình mất đi khi lệnh thua (Reward/Risk Ratio thực tế).</td>
                </tr>
                <tr>
                    <td><span class="term">Chất lượng thực thi</span></td>
                    <td>Điểm số đánh giá mức độ <span class="highlight">tuân thủ kỷ luật</span> và khả năng bám sát đúng kế hoạch giao dịch đã đề ra.</td>
                </tr>
            </table>

            <div class='section-title'>Các cột dữ liệu Bảng nhóm & Bảng lệnh</div>
            <table>
                <tr>
                    <th width="30%">Tên cột</th>
                    <th>Giải thích chi tiết</th>
                </tr>
                <tr>
                    <td><span class="term">Nhóm / Tên</span></td>
                    <td>Tiêu chí dùng để phân loại và gom nhóm dữ liệu (Ví dụ: theo Mã giao dịch, Setup, Phiên giao dịch...).</td>
                </tr>
                <tr>
                    <td><span class="term">Lệnh</span></td>
                    <td>Khối lượng (số lượng) lệnh giao dịch thuộc về nhóm tương ứng.</td>
                </tr>
                <tr>
                    <td><span class="term">Đóng lúc</span></td>
                    <td>Thời gian thực tế mà lệnh giao dịch được thanh lý (đóng).</td>
                </tr>
                <tr>
                    <td><span class="term">R / P/L</span></td>
                    <td>Kết quả cuối cùng của lệnh tính theo <span class="highlight">tỉ lệ rủi ro (R)</span> và theo <span class="highlight">tiền mặt (P/L)</span>.</td>
                </tr>
                <tr>
                    <td><span class="term">CL (Chất lượng)</span></td>
                    <td>Điểm chất lượng thực thi của riêng lệnh đó, giúp rà soát lại các lệnh có lỗi tâm lý hoặc vi phạm nguyên tắc.</td>
                </tr>
            </table>
        </body>
        """
        browser.setHtml(html)
        layout.addWidget(browser)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        close_btn = action_button("❌ Đóng")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)


def decision_value(text: str) -> str | None:
    return {"Sẵn sàng": "ready", "Theo dõi": "watch", "Chờ": "wait_for_confirmation", "Đứng ngoài": "stand_aside"}.get(text)


def permission_value(text: str) -> str | None:
    return {"Được phép": "allowed", "Cẩn trọng": "caution", "Bị chặn": "blocked"}.get(text)


def format_time(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
        return parsed.strftime("%d/%m/%Y %H:%M:%S")
    except ValueError:
        return value


def format_short_time(value: str) -> str:
    if not value or value == "--":
        return "--"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
        return parsed.strftime("%m-%d %H:%M")
    except ValueError:
        return value[:16]


def format_metric(value: object, suffix: str = "") -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "--"
    text = f"{number:.2f}".rstrip("0").rstrip(".")
    return f"{text}{suffix}"


def color_item_by_number(item: QTableWidgetItem, value: str) -> None:
    try:
        number = float(value.replace("R", "").replace("%", "").strip())
    except ValueError:
        return
    if number > 0:
        item.setForeground(QColor("#5eead4"))
    elif number < 0:
        item.setForeground(QColor("#fb7185"))
