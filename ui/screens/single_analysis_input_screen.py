from __future__ import annotations

from controllers.analysis_controller import AnalysisController
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from services.mt5_service import MT5Service
from services.settings_service import SettingsService
from ui.screens.shared import action_button, card, form_row, labeled_value, page_header


class ReadOnlyValueLineEdit(QLineEdit):
    def __init__(self) -> None:
        super().__init__()
        self._value: float | str = ""
        self.setReadOnly(True)
        self.setEnabled(False)

    def set_value(self, value: float | str, display_text: str | None = None) -> None:
        self._value = value
        self.setText(str(value) if display_text is None else display_text)

    def value(self) -> float | str:
        return self._value

    def currentText(self) -> str:
        return self.text()


class SingleAnalysisInputScreen(QWidget):
    def __init__(self, navigate=None) -> None:
        super().__init__()
        self.navigate = navigate
        self.settings_service = SettingsService()
        self.mt5_service = MT5Service()
        self.analysis_controller = AnalysisController(self.settings_service, self.mt5_service)
        self.analysis_thread = None
        self.analysis_worker = None
        self.symbol_broker_map: dict[str, str] = {}
        self.account_balance_value = 0.0
        self.risk_percent_value = 0.0
        self.timezone_name_value = ""
        self.setObjectName("FormScreen")
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)
        root.addWidget(
            page_header(
                "Phân tích một mã",
                "Chọn mã, khung thời gian và rủi ro trước khi chạy phân tích.",
                "D1 / H4 / H1 / M15",
            )
        )

        self.analysis_risk_card = self._analysis_risk_card()
        root.addWidget(self.analysis_risk_card, alignment=Qt.AlignmentFlag.AlignTop)
        root.addWidget(self._support_cards(), alignment=Qt.AlignmentFlag.AlignTop)
        root.addStretch(1)
        self.refresh_status()
        QTimer.singleShot(0, self._equalize_analysis_risk_sections)

    def _analysis_risk_card(self):
        frame = card()
        frame.setObjectName("AnalysisRiskCard")
        frame.layout().setContentsMargins(16, 12, 16, 12)
        frame.layout().setSpacing(12)

        content = QWidget()
        layout = QHBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        self.analysis_section = self._analysis_section()
        self.risk_section = self._risk_section()
        separator = QFrame()
        separator.setObjectName("VerticalSeparator")
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFixedWidth(1)
        separator.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        layout.addWidget(self.analysis_section, 1)
        layout.addWidget(separator)
        layout.addWidget(self.risk_section, 1)
        frame.layout().addWidget(content)
        return frame

    def _section_title(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("PanelTitle")
        return label

    def _analysis_section(self):
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 14, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._section_title("Cấu hình phân tích"))

        self.symbol_input = QComboBox()
        self.symbol_input.currentTextChanged.connect(self._sync_broker_symbol)

        self.broker_symbol_input = QLineEdit()
        self.broker_symbol_input.setPlaceholderText("Tự dò từ Bảng theo dõi thị trường nếu để trống")

        timeframes = QWidget()
        tf_layout = QHBoxLayout(timeframes)
        tf_layout.setContentsMargins(0, 0, 0, 0)
        for label in ["D1", "H4", "H1", "M15"]:
            box = QCheckBox(label)
            box.setChecked(True)
            box.setEnabled(False)
            tf_layout.addWidget(box)
        tf_layout.addStretch(1)

        layout.addWidget(form_row("Mã giao dịch", self.symbol_input))
        layout.addWidget(form_row("Mã broker", self.broker_symbol_input))
        layout.addWidget(form_row("Khung thời gian", timeframes))
        self.data_source_box = self._compact_data_source()
        layout.addWidget(self.data_source_box)
        layout.addWidget(self._status_badges())
        return section

    def _risk_section(self):
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(14, 0, 0, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._section_title("Tóm tắt rủi ro"))
        settings = self.settings_service.load()

        self.account_balance_value = 0.0
        self.risk_percent_value = settings.trading.default_risk_percent
        self.timezone_name_value = settings.display.timezone

        self.balance_input = ReadOnlyValueLineEdit()
        self.balance_input.set_value(0.0, "--")

        self.risk_input = ReadOnlyValueLineEdit()
        self.risk_input.set_value(self.risk_percent_value, self._format_percent(self.risk_percent_value))

        self.timezone_input = ReadOnlyValueLineEdit()
        self.timezone_input.set_value(self.timezone_name_value)

        self.max_risk_input = ReadOnlyValueLineEdit()
        self.max_risk_input.set_value(0.0, "--")

        layout.addWidget(form_row("Số dư", self.balance_input))
        layout.addWidget(form_row("Rủi ro mỗi lệnh", self.risk_input))
        layout.addWidget(form_row("Rủi ro tối đa", self.max_risk_input))
        layout.addWidget(form_row("Múi giờ", self.timezone_input))
        self.readiness_label = QLabel("Kiểm tra MT5 và broker trước khi phân tích.")
        self.readiness_label.setObjectName("HelperText")
        self.readiness_label.setWordWrap(True)
        layout.addWidget(self.readiness_label)
        layout.addStretch(1)
        self.analyze_button = action_button("Phân tích", primary=True)
        self.analyze_button.clicked.connect(self._run_analysis)
        layout.addWidget(self.analyze_button)
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("AnalysisProgressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(30)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        return section

    def _status_badges(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(8)
        self.data_status_labels: dict[str, QLabel] = {}
        self.data_status_items: list[QWidget] = []
        items = [
            ("MT5", "Chưa kết nối"),
            ("Broker", "Chưa đăng nhập"),
            ("Mã broker", "--"),
            ("Spread", "Kiểm tra khi chạy"),
            ("Quyền phân tích", "Bị chặn"),
        ]
        for title, value in items:
            badge = QFrame()
            badge.setObjectName("AnalysisStatusBadge")
            badge_layout = QHBoxLayout(badge)
            badge_layout.setContentsMargins(10, 6, 10, 6)
            badge_layout.setSpacing(5)
            title_label = QLabel(title)
            title_label.setObjectName("StatusBadgeTitle")
            value_label = QLabel(value)
            value_label.setObjectName("StatusBadgeValue")
            badge_layout.addWidget(title_label)
            badge_layout.addWidget(value_label)
            self.data_status_labels[title] = value_label
            self.data_status_items.append(badge)
            layout.addWidget(badge)
        layout.addStretch(1)
        return row

    def _support_cards(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self._support_card(
            "Trước khi chạy",
            [
                "Đúng mã broker trong MT5",
                "Spread sẽ kiểm tra khi chạy",
                "Không giao dịch gần tin đỏ",
                "Rủi ro đã tính theo số dư MT5",
            ],
            "SupportCardCheck",
        ), 1)
        layout.addWidget(self._support_card(
            "Kết quả phân tích sẽ gồm",
            [
                "Thiên hướng giao dịch",
                "Vùng vào lệnh / vùng theo dõi",
                "Cắt lỗ / chốt lời / khối lượng",
                "R:R / checklist / rủi ro tin tức / biểu đồ",
            ],
            "SupportCardResult",
        ), 1)
        return row

    def _support_card(self, title: str, rows: list[str], object_name: str) -> QFrame:
        frame = card(title, object_name=object_name)
        frame.layout().setContentsMargins(16, 14, 16, 14)
        frame.layout().setSpacing(6)
        for row in rows:
            label = QLabel(f"✓ {row}")
            label.setObjectName("SupportCardLine")
            label.setWordWrap(True)
            frame.layout().addWidget(label)
        return frame

    def _compact_data_source(self) -> QWidget:
        row = QWidget()
        row.setObjectName("CompactInfoRow")
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(8)
        title = QLabel("Nguồn dữ liệu")
        title.setObjectName("CompactInfoTitle")
        value = QLabel("MetaTrader 5")
        value.setObjectName("CompactInfoValue")
        layout.addWidget(title)
        layout.addStretch(1)
        layout.addWidget(value)
        return row

    def _data_check_card(self):
        frame = card("Trạng thái dữ liệu")
        frame.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        frame.layout().setContentsMargins(16, 12, 16, 12)
        frame.layout().setSpacing(8)
        stats = QGridLayout()
        stats.setHorizontalSpacing(8)
        stats.setVerticalSpacing(8)
        stats.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.data_status_labels: dict[str, QLabel] = {}
        self.data_status_items: list[QWidget] = []
        items = [
            ("MT5", "Chưa kết nối"),
            ("Broker", "Chưa đăng nhập"),
            ("Mã broker", "--"),
            ("Rủi ro tối đa", "--"),
            ("Spread", "Kiểm tra khi chạy"),
            ("Quyền phân tích", "Bị chặn"),
        ]
        for index, (title, value) in enumerate(items):
            item = labeled_value(title, value)
            item.setMinimumHeight(54)
            item.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            value_label = item.findChildren(QLabel)[1]
            self.data_status_labels[title] = value_label
            self.data_status_items.append(item)
            stats.addWidget(item, index // 3, index % 3)
        self.data_status_grid = stats
        frame.layout().addLayout(stats)
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("AnalysisProgressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(30)
        self.progress_bar.hide()
        frame.layout().addWidget(self.progress_bar)
        return frame

    def refresh_status(self) -> None:
        status = self.mt5_service.connection_status()
        settings = self.settings_service.load()
        self.risk_percent_value = settings.trading.default_risk_percent
        self.timezone_name_value = settings.display.timezone
        self.risk_input.set_value(self.risk_percent_value, self._format_percent(self.risk_percent_value))
        self.timezone_input.set_value(self.timezone_name_value)
        self._refresh_symbol_dropdown(status)
        self.data_status_labels["MT5"].setText("Đã kết nối" if status.terminal_connected else "Chưa kết nối")
        self.data_status_labels["Broker"].setText("Đã đăng nhập" if status.logged_in else "Chưa đăng nhập")
        self.data_status_labels["Mã broker"].setText(self._current_broker_symbol() or "--")
        self.data_status_labels["Spread"].setText("Kiểm tra khi phân tích")
        can_analyze = status.terminal_connected and status.logged_in
        if status.balance is not None:
            self.account_balance_value = float(status.balance)
            self.balance_input.set_value(self.account_balance_value, self._format_money(self.account_balance_value))
        else:
            self.account_balance_value = 0.0
            self.balance_input.set_value(self.account_balance_value, "--")
        max_risk = self.account_balance_value * self.risk_percent_value / 100
        max_risk_text = self._format_money(max_risk) if max_risk > 0 else "--"
        self.max_risk_input.set_value(max_risk, max_risk_text)
        self.data_status_labels["Quyền phân tích"].setText("Sẵn sàng" if can_analyze else "Bị chặn")
        if can_analyze and self.symbol_input.count() > 0:
            self.readiness_label.setText("Sẵn sàng lấy D1/H4/H1/M15, kiểm tra spread, tin tức và tạo kế hoạch lệnh.")
            self.readiness_label.setProperty("state", "ok")
        else:
            self.readiness_label.setText("Chưa sẵn sàng. Hãy kiểm tra kết nối MT5, broker hoặc mã trong Market Watch.")
            self.readiness_label.setProperty("state", "error")
        self.readiness_label.style().unpolish(self.readiness_label)
        self.readiness_label.style().polish(self.readiness_label)
        self.analyze_button.setEnabled(can_analyze and self.symbol_input.count() > 0)
        self._update_analyze_button_label()

    def set_analysis_result(self, payload: dict[str, object]) -> None:
        symbol = str(payload.get("symbol", ""))
        broker_symbol = str(payload.get("broker_symbol", ""))
        if symbol:
            index = self.symbol_input.findText(symbol)
            if index >= 0:
                self.symbol_input.setCurrentIndex(index)
        if broker_symbol:
            self.broker_symbol_input.setText(broker_symbol)

    def _refresh_symbol_dropdown(self, status) -> None:
        current_symbol = self.symbol_input.currentText()
        matches = self.mt5_service.configured_symbols_in_market_watch() if status.terminal_connected else []
        settings = self.settings_service.load()
        enabled = settings.trading.enabled_symbols
        if enabled:
            enabled_set = set(enabled)
            matches = [(s, b) for s, b in matches if s in enabled_set]
        self.symbol_broker_map = {symbol: broker for symbol, broker in matches}
        self.symbol_input.blockSignals(True)
        self.symbol_input.clear()
        for symbol, broker_symbol in matches:
            self.symbol_input.addItem(symbol, broker_symbol)
        if current_symbol in self.symbol_broker_map:
            self.symbol_input.setCurrentText(current_symbol)
        self.symbol_input.blockSignals(False)
        self._sync_broker_symbol(self.symbol_input.currentText())

    def _sync_broker_symbol(self, symbol: str) -> None:
        aliases = self.mt5_service.aliases_for(symbol)
        self.broker_symbol_input.setPlaceholderText(aliases[0] if aliases else "Tự dò từ Bảng theo dõi thị trường nếu để trống")
        resolved = self.symbol_broker_map.get(symbol)
        self.broker_symbol_input.setText(resolved or (aliases[0] if aliases else ""))
        if hasattr(self, "data_status_labels"):
            self.data_status_labels["Mã broker"].setText(self._current_broker_symbol() or "--")
        self._update_analyze_button_label()

    def _current_broker_symbol(self) -> str:
        return self.broker_symbol_input.text().strip()

    def _update_analyze_button_label(self) -> None:
        if self.analysis_thread is not None:
            return
        symbol = self.symbol_input.currentText().strip()
        self.analyze_button.setText(f"Phân tích {symbol}" if symbol else "Phân tích")

    def _run_analysis(self) -> None:
        self.analyze_button.setEnabled(False)
        self.analyze_button.setText("Đang phân tích...")
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        thread, worker = self.analysis_controller.create_single_analysis_worker(
            symbol=self.symbol_input.currentText(),
            broker_symbol=self._current_broker_symbol(),
            account_balance=self.account_balance_value,
            risk_percent=self.risk_percent_value,
            timezone_name=self.timezone_name_value,
        )
        self.analysis_thread = thread
        self.analysis_worker = worker
        worker.progress.connect(self._analysis_progress)
        worker.succeeded.connect(self._analysis_finished)
        worker.failed.connect(self._analysis_failed)
        thread.finished.connect(self._analysis_thread_finished)
        thread.start()

    def _analysis_progress(self, percent: int, message: str) -> None:
        self.progress_bar.setValue(percent)
        self.analyze_button.setText(message)

    def _equalize_analysis_risk_sections(self) -> None:
        self.analysis_section.layout().activate()
        self.risk_section.layout().activate()
        height = max(self.analysis_section.sizeHint().height(), self.risk_section.sizeHint().height())
        self.analysis_section.setMinimumHeight(height)
        self.risk_section.setMinimumHeight(height)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_compact_layout()

    def _apply_compact_layout(self) -> None:
        if not hasattr(self, "data_status_grid"):
            return
        compact = self.width() < 1450
        self._relayout_grid(self.data_status_grid, self.data_status_items, 2 if compact else 3)

    def _relayout_grid(self, grid: QGridLayout, widgets: list[QWidget], columns: int) -> None:
        for index, widget in enumerate(widgets):
            grid.removeWidget(widget)
            grid.addWidget(widget, index // columns, index % columns)

    def _analysis_finished(self, result: dict[str, object]) -> None:
        if self.navigate:
            self.navigate("analysis_result", result)

    def _analysis_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Không thể phân tích", message)

    def _analysis_thread_finished(self) -> None:
        self.analyze_button.setText("Phân tích")
        self.analyze_button.setEnabled(True)
        self.progress_bar.hide()
        self.analysis_thread = None
        self.analysis_worker = None
        self.refresh_status()

    def _format_money(self, value: float) -> str:
        return f"{value:,.2f}"

    def _format_percent(self, value: float) -> str:
        return f"{value:.2f} %"
