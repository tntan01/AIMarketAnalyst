from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PyQt6.QtCore import QDate, QEvent, QLocale, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
        QAbstractSpinBox,
        QDialog,
        QDialogButtonBox,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QSizePolicy,
        QSpinBox,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
)

from config.constants import SUPPORTED_SYMBOLS
from controllers.backtest_controller import BacktestController
from ui.screens.shared import action_button, card, page_header


class BacktestScreen(QWidget):
    TRADE_COLUMNS = [
        ("entry_time", "Thời gian vào"),
        ("side", "Hướng"),
        ("result", "Kết quả"),
        ("result_r", "R"),
        ("entry_price", "Entry"),
        ("stop_loss", "SL"),
        ("take_profit", "TP"),
        ("final_score", "Điểm tổng"),
        ("signal_score", "Tín hiệu"),
        ("m15_quality", "M15"),
        ("market_regime", "Regime"),
        ("selected_zone_score", "Zone"),
    ]
    TRADE_COLUMN_WEIGHTS = {
        "entry_time": 1.65,
        "side": 0.65,
        "result": 0.75,
        "result_r": 0.52,
        "entry_price": 0.82,
        "stop_loss": 0.82,
        "take_profit": 0.82,
        "final_score": 0.68,
        "signal_score": 0.68,
        "m15_quality": 0.62,
        "market_regime": 0.88,
        "selected_zone_score": 0.52,
    }

    def __init__(self, navigate=None) -> None:
        super().__init__()
        self.navigate = navigate
        self.controller = BacktestController()
        self.backtest_thread = None
        self.backtest_worker = None
        self.result: dict[str, object] | None = None
        self.setObjectName("FormScreen")
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)
        root.addWidget(
            page_header(
                "Backtest hệ thống",
                "Replay pipeline phân tích trên dữ liệu lịch sử để đo expectancy, drawdown và edge theo nhóm.",
            )
        )
        root.addWidget(self._settings_card())
        root.addWidget(self._trades_card(), 1)

    def _settings_card(self) -> QFrame:
        frame = card(None)
        frame.setStyleSheet(self._backtest_form_stylesheet())
        frame.layout().setContentsMargins(12, 10, 12, 4)
        frame.layout().setSpacing(6)
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(12)
        frame.layout().addLayout(top_row)

        market_box = self._section_box("Dữ liệu")
        market_grid = QGridLayout()
        market_grid.setContentsMargins(0, 0, 0, 0)
        market_grid.setHorizontalSpacing(0)
        market_grid.setVerticalSpacing(6)
        market_box.layout().addLayout(market_grid)

        params_box = self._section_box("Tham số")
        params_grid = QGridLayout()
        params_grid.setContentsMargins(0, 0, 0, 0)
        params_grid.setHorizontalSpacing(8)
        params_grid.setVerticalSpacing(6)
        params_grid.setColumnStretch(0, 1)
        params_grid.setColumnStretch(1, 1)
        params_box.layout().addLayout(params_grid)

        self.symbol_combo = QComboBox()
        self.symbol_combo.addItems(sorted(SUPPORTED_SYMBOLS))
        self.symbol_combo.setCurrentText("EUR/USD")

        today = QDate.currentDate()
        self.start_date = QDateEdit(today.addMonths(-6))
        self.start_date.setCalendarPopup(True)
        self.start_date.setDisplayFormat("dd/MM/yyyy")
        self.end_date = QDateEdit(today)
        self.end_date.setCalendarPopup(True)
        self.end_date.setDisplayFormat("dd/MM/yyyy")

        self.balance_input = QDoubleSpinBox()
        self._apply_number_format(self.balance_input)
        self.balance_input.setRange(100, 100_000_000)
        self.balance_input.setDecimals(2)
        self.balance_input.setValue(10_000)

        self.risk_input = QDoubleSpinBox()
        self._apply_number_format(self.risk_input)
        self.risk_input.setRange(0.01, 10.0)
        self.risk_input.setDecimals(2)
        self.risk_input.setValue(1.0)
        self.risk_input.setSuffix(" %")

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Strict", "strict")
        self.mode_combo.addItem("Legacy", "legacy")
        self.mode_combo.addItem("Research", "research")

        self.spread_input = QDoubleSpinBox()
        self._apply_number_format(self.spread_input)
        self.spread_input.setRange(0.0, 10.0)
        self.spread_input.setDecimals(5)

        self.slippage_input = QDoubleSpinBox()
        self._apply_number_format(self.slippage_input)
        self.slippage_input.setRange(0.0, 10.0)
        self.slippage_input.setDecimals(5)

        self.max_holding_input = QSpinBox()
        self._apply_number_format(self.max_holding_input)
        self.max_holding_input.setRange(1, 2000)
        self.max_holding_input.setValue(96)
        for field in (
            self.symbol_combo,
            self.start_date,
            self.end_date,
            self.balance_input,
            self.risk_input,
            self.mode_combo,
            self.max_holding_input,
            self.spread_input,
            self.slippage_input,
        ):
            field.setObjectName("BacktestField")

        market_grid.addWidget(self._field_cell("Mã", self.symbol_combo, 58), 0, 0)
        market_grid.addWidget(self._field_cell("Từ ngày", self.start_date, 58), 1, 0)
        market_grid.addWidget(self._field_cell("Đến ngày", self.end_date, 58), 2, 0)

        params_label_width = 76
        params_grid.addWidget(self._field_cell("Số dư", self.balance_input, params_label_width), 0, 0)
        params_grid.addWidget(self._field_cell("Rủi ro", self.risk_input, params_label_width), 0, 1)
        params_grid.addWidget(self._field_cell("Chế độ", self.mode_combo, params_label_width), 1, 0)
        params_grid.addWidget(self._field_cell("Số nến", self.max_holding_input, params_label_width), 1, 1)
        params_grid.addWidget(self._field_cell("Spread", self.spread_input, params_label_width), 2, 0)
        params_grid.addWidget(self._field_cell("Slippage", self.slippage_input, params_label_width), 2, 1)

        summary_box = self._section_box("Kết quả")
        self.summary_row = QGridLayout()
        self.summary_row.setHorizontalSpacing(8)
        self.summary_row.setVerticalSpacing(6)
        self.summary_row.setContentsMargins(0, 0, 0, 0)
        self.summary_row.setColumnStretch(0, 1)
        self.summary_row.setColumnStretch(1, 1)
        self.summary_row.setColumnStretch(2, 1)
        summary_box.layout().addLayout(self.summary_row)
        self._set_summary({})

        top_row.addWidget(market_box, 7)
        top_row.addWidget(self._vertical_separator())
        top_row.addWidget(params_box, 10)
        top_row.addWidget(self._vertical_separator())
        top_row.addWidget(summary_box, 8)

        run_bar = QWidget()
        controls = QHBoxLayout(run_bar)
        controls.setContentsMargins(0, 2, 0, 0)
        controls.setSpacing(10)
        self.run_button = action_button("Chạy backtest", primary=True)
        self.run_button.setFixedSize(148, 32)
        self.run_button.clicked.connect(self._run_backtest)
        self.help_button = QPushButton("Giải thích")
        self.help_button.setObjectName("InlineHelpButton")
        self.help_button.setFixedHeight(32)
        self.help_button.clicked.connect(self._show_input_help)
        self.progress = QProgressBar()
        self.progress.setObjectName("BacktestProgress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(10)
        self.progress.setStyleSheet(
            "QProgressBar#BacktestProgress {"
            "background: #0f172a;"
            "border: 1px solid #334155;"
            "border-radius: 5px;"
            "}"
            "QProgressBar#BacktestProgress::chunk {"
            "background: #14b8a6;"
            "border-radius: 4px;"
            "}"
        )
        self.status_label = QLabel("Sẵn sàng")
        self.status_label.setObjectName("HelperText")
        self.status_label.setMinimumWidth(180)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        controls.addWidget(self.run_button)
        controls.addWidget(self.help_button)
        controls.addWidget(self.progress, 1)
        controls.addWidget(self.status_label)
        frame.layout().addWidget(run_bar)
        self.snapshot_label = QLabel("")
        self.snapshot_label.setObjectName("HelperText")
        self.snapshot_label.setFixedHeight(16)
        self.snapshot_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        frame.layout().addWidget(self.snapshot_label)
        return frame

    def _section_box(self, title: str) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        header = QLabel(title)
        header.setObjectName("MiniStatTitle")
        header.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(header)
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return box

    def _field_cell(self, label: str, field: QWidget, label_width: int = 64) -> QWidget:
        cell = QWidget()
        cell.setFixedHeight(34)
        layout = QHBoxLayout(cell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        title = QLabel(label)
        title.setObjectName("FormLabel")
        title.setFixedWidth(label_width)
        title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        field.setMinimumWidth(0)
        field.setFixedHeight(34)
        layout.addWidget(title)
        layout.addWidget(field, 1)
        return cell

    def _stat_cell(self, title: str, value: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("MiniStat")
        frame.setFixedHeight(50)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("MiniStatTitle")
        value_label = QLabel(value)
        value_label.setObjectName("MiniStatValue")
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        return frame

    def _vertical_separator(self) -> QFrame:
        line = QFrame()
        line.setObjectName("VerticalSeparator")
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setLineWidth(1)
        line.setStyleSheet("color: rgba(148, 163, 184, 0.55); background: rgba(148, 163, 184, 0.35);")
        return line

    def _trades_card(self) -> QFrame:
        frame = card("Danh sách lệnh")
        self.table = QTableWidget(0, len(self.TRADE_COLUMNS))
        self.table.setObjectName("DataTable")
        self.table.setHorizontalHeaderLabels([label for _, label in self.TRADE_COLUMNS])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.viewport().installEventFilter(self)
        self._apply_trade_table_layout()
        frame.layout().addWidget(self.table, 1)
        return frame

    def _show_input_help(self) -> None:
        dialog = BacktestInputHelpDialog(self)
        dialog.exec()

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if hasattr(self, "table") and watched is self.table.viewport() and event.type() == QEvent.Type.Resize:
            self._resize_trade_columns_to_viewport()
        return super().eventFilter(watched, event)

    def _run_backtest(self) -> None:
        try:
            request = self.controller.build_request(
                symbol=self.symbol_combo.currentText(),
                start=self._qdate_to_utc_start(self.start_date.date()),
                end=self._qdate_to_utc_end(self.end_date.date()),
                initial_balance=self.balance_input.value(),
                risk_percent=self.risk_input.value(),
                mode=str(self.mode_combo.currentData()),
                spread_price=self.spread_input.value(),
                slippage_price=self.slippage_input.value(),
                max_holding_bars=self.max_holding_input.value(),
            )
        except Exception as exc:
            QMessageBox.warning(self, "Không tạo được request", str(exc))
            return

        self.run_button.setEnabled(False)
        self.progress.setValue(0)
        self.status_label.setText("Đang chạy backtest...")
        self.backtest_thread, self.backtest_worker = self.controller.create_backtest_worker(request)
        self.backtest_worker.progress.connect(self._on_progress)
        self.backtest_worker.succeeded.connect(self._on_success)
        self.backtest_worker.failed.connect(self._on_failed)
        self.backtest_worker.finished.connect(lambda: self.run_button.setEnabled(True))
        self.backtest_thread.start()

    def _on_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(percent)
        self.status_label.setText(message)

    def _on_success(self, result: dict) -> None:
        self.result = result
        self.status_label.setText("Hoàn tất backtest.")
        self._set_summary(result.get("summary", {}) if isinstance(result.get("summary"), dict) else {})
        self._set_trades(result.get("trades", []) if isinstance(result.get("trades"), list) else [])
        self.snapshot_label.setText(f"File kết quả: {result.get('snapshot_path', '')}")

    def _on_failed(self, message: str) -> None:
        self.status_label.setText("Backtest thất bại.")
        QMessageBox.critical(self, "Backtest thất bại", message)

    def _set_summary(self, summary: dict[str, object]) -> None:
        while self.summary_row.count():
            item = self.summary_row.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        items = [
            ("Số lệnh", self._format_integer(summary.get("total_trades", 0))),
            ("Tỷ lệ thắng", self._format_decimal(summary.get("win_rate", 0), 2, "%")),
            ("Expectancy", self._format_decimal(summary.get("expectancy_r", 0), 2, "R")),
            ("Profit factor", self._format_decimal(summary.get("profit_factor", 0), 2)),
            ("Max DD", self._format_decimal(summary.get("max_drawdown_r", 0), 2, "R")),
            ("Tổng R", self._format_decimal(summary.get("total_r", 0), 2, "R")),
        ]
        for index, (title, value) in enumerate(items):
            self.summary_row.addWidget(self._stat_cell(str(title), str(value)), index // 3, index % 3)

    def _set_trades(self, trades: list[dict[str, object]]) -> None:
        self.table.setRowCount(len(trades))
        for row, trade in enumerate(trades):
            for col, (key, _label) in enumerate(self.TRADE_COLUMNS):
                item = QTableWidgetItem(self._format_trade_value(key, trade.get(key, "--")))
                if key in {"result_r", "final_score", "signal_score", "selected_zone_score"}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, col, item)
        self._apply_trade_table_layout()

    def _apply_trade_table_layout(self) -> None:
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        for column, (_key, _label) in enumerate(self.TRADE_COLUMNS):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        self._resize_trade_columns_to_viewport()

    def _resize_trade_columns_to_viewport(self) -> None:
        viewport_width = self.table.viewport().width()
        if viewport_width <= 0:
            viewport_width = self.table.width()
        if viewport_width <= 0:
            return

        weights = [self.TRADE_COLUMN_WEIGHTS[key] for key, _label in self.TRADE_COLUMNS]
        total_weight = sum(weights)
        exact_widths = [viewport_width * weight / total_weight for weight in weights]
        widths = [max(1, int(width)) for width in exact_widths]
        remaining = viewport_width - sum(widths)

        fractions = sorted(
            enumerate(width - int(width) for width in exact_widths),
            key=lambda item: item[1],
            reverse=True,
        )
        if remaining > 0:
            for index, _fraction in fractions[:remaining]:
                widths[index] += 1
        elif remaining < 0:
            for index, _width in sorted(enumerate(widths), key=lambda item: item[1], reverse=True):
                if remaining == 0:
                    break
                reducible = min(widths[index] - 1, -remaining)
                if reducible > 0:
                    widths[index] -= reducible
                    remaining += reducible

        for column, width in enumerate(widths):
            self.table.setColumnWidth(column, width)

    @staticmethod
    def _apply_number_format(spinbox: QDoubleSpinBox | QSpinBox) -> None:
        spinbox.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        spinbox.setGroupSeparatorShown(True)
        spinbox.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)

    @staticmethod
    def _backtest_form_stylesheet() -> str:
        return """
        QComboBox#BacktestField,
        QDateEdit#BacktestField,
        QDoubleSpinBox#BacktestField,
        QSpinBox#BacktestField {
            background: #111827;
            border: 1px solid #334155;
            border-radius: 6px;
            color: #e5e7eb;
            min-height: 18px;
            padding: 7px 9px;
            selection-background-color: #0d9488;
            selection-color: #ffffff;
        }

        QComboBox#BacktestField,
        QDateEdit#BacktestField {
            padding-right: 34px;
        }

        QComboBox#BacktestField:hover,
        QDateEdit#BacktestField:hover,
        QDoubleSpinBox#BacktestField:hover,
        QSpinBox#BacktestField:hover {
            background: #151f2e;
            border-color: #475569;
        }

        QComboBox#BacktestField:focus,
        QComboBox#BacktestField:on,
        QDateEdit#BacktestField:focus,
        QDateEdit#BacktestField:on,
        QDoubleSpinBox#BacktestField:focus,
        QSpinBox#BacktestField:focus {
            background: #101827;
            border-color: #38bdf8;
        }

        QComboBox#BacktestField::drop-down,
        QDateEdit#BacktestField::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 30px;
            border-left: 1px solid #334155;
            border-top-right-radius: 6px;
            border-bottom-right-radius: 6px;
            background: transparent;
        }

        QComboBox#BacktestField::drop-down:hover,
        QDateEdit#BacktestField::drop-down:hover {
            background: #172235;
            border-left-color: #475569;
        }

        QComboBox#BacktestField::down-arrow,
        QDateEdit#BacktestField::down-arrow {
            image: url(assets/icons/chevron-down.svg);
            width: 14px;
            height: 14px;
            margin-right: 8px;
        }

        QComboBox#BacktestField QAbstractItemView {
            background: #111827;
            border: 1px solid #475569;
            outline: 0;
            color: #e5e7eb;
            selection-background-color: #0d9488;
            selection-color: #ffffff;
            padding: 4px;
        }
        """

    @staticmethod
    def _format_integer(value: object) -> str:
        try:
            return f"{int(value):,}"
        except (TypeError, ValueError):
            return "--"

    @staticmethod
    def _format_decimal(value: object, decimals: int, suffix: str = "") -> str:
        try:
            return f"{float(value):,.{decimals}f}{suffix}"
        except (TypeError, ValueError):
            return "--"

    def _format_trade_value(self, key: str, value: object) -> str:
        if value is None:
            return "--"
        if key == "entry_time":
            return self._format_gmt7_timestamp(value)
        if key in {"entry_price", "stop_loss", "take_profit"}:
            return self._format_decimal(value, 5)
        if key == "result_r":
            return self._format_decimal(value, 2)
        if key in {"final_score", "signal_score", "selected_zone_score"}:
            return self._format_integer(value)
        return str(value)

    @staticmethod
    def _format_gmt7_timestamp(value: object) -> str:
        if not value:
            return "--"
        try:
            raw = str(value).replace("Z", "+00:00")
            parsed = datetime.fromisoformat(raw)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            gmt7 = parsed.astimezone(timezone(timedelta(hours=7)))
            return gmt7.strftime("%d-%m-%Y %H:%M:%S")
        except ValueError:
            return str(value)

    @staticmethod
    def _qdate_to_utc_start(value: QDate) -> datetime:
        return datetime(value.year(), value.month(), value.day(), tzinfo=timezone.utc)

    @staticmethod
    def _qdate_to_utc_end(value: QDate) -> datetime:
        return datetime(value.year(), value.month(), value.day(), 23, 59, 59, tzinfo=timezone.utc)


class BacktestInputHelpDialog(QDialog):
    HELP_ROWS = [
        (
            "Mã",
            "Cặp tiền hoặc sản phẩm cần kiểm tra, ví dụ EUR/USD.",
            "Nên chọn đúng thị trường bạn muốn giao dịch thật. Mỗi mã có spread, biến động và hành vi giá khác nhau nên kết quả backtest không thể dùng lẫn cho mã khác.",
        ),
        (
            "Từ ngày",
            "Ngày bắt đầu lấy dữ liệu lịch sử để chạy lại hệ thống.",
            "Khoảng thời gian càng dài thì thống kê càng đáng tin hơn, nhưng chạy lâu hơn. Với người mới, nên thử tối thiểu vài tháng dữ liệu trước khi đánh giá.",
        ),
        (
            "Đến ngày",
            "Ngày kết thúc vùng dữ liệu lịch sử.",
            "Dùng để kiểm tra một giai đoạn cụ thể, ví dụ chỉ năm 2025 hoặc một giai đoạn thị trường biến động mạnh.",
        ),
        (
            "Số dư",
            "Vốn giả định ban đầu của tài khoản khi backtest.",
            "Thông số này giúp quy đổi rủi ro theo tiền. Nếu bạn thường giao dịch tài khoản 10,000 USD thì nhập 10,000 để kết quả gần thực tế hơn.",
        ),
        (
            "Rủi ro",
            "Phần trăm tài khoản chấp nhận mất nếu một lệnh chạm stop loss.",
            "Ví dụ 1% nghĩa là tài khoản 10,000 chỉ rủi ro khoảng 100 cho mỗi lệnh. Người mới thường nên xem 0.5% đến 1% trước khi thử mức cao hơn.",
        ),
        (
            "Chế độ",
            "Mức độ nghiêm ngặt của bộ lọc setup.",
            "Strict lọc chặt hơn, thường ít lệnh hơn. Legacy giữ gần logic cũ. Research dùng để khảo sát rộng hơn, có thể nhiều lệnh nhưng nhiễu hơn.",
        ),
        (
            "Số nến",
            "Số nến tối đa cho phép một lệnh còn mở sau khi vào lệnh.",
            "Nếu sau số nến này lệnh chưa chạm TP hoặc SL, backtest sẽ đóng/đánh giá theo quy tắc thoát thời gian. Giá trị lớn cho lệnh nhiều thời gian hơn nhưng có thể giữ rủi ro lâu hơn.",
        ),
        (
            "Spread",
            "Chi phí chênh lệch giữa giá mua và giá bán, tính trực tiếp theo đơn vị giá.",
            "Spread càng cao thì kết quả càng khó đẹp vì entry bị bất lợi hơn. Nên nhập gần với điều kiện broker thực tế thay vì để 0 nếu muốn đánh giá sát.",
        ),
        (
            "Slippage",
            "Mức trượt giá giả định khi khớp lệnh.",
            "Slippage mô phỏng trường hợp lệnh không khớp đúng giá mong muốn, thường xảy ra khi thị trường chạy nhanh hoặc thanh khoản thấp.",
        ),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Giải thích tham số backtest")
        self.setObjectName("ScannerHelpDialog")
        self.setModal(True)
        self.setMinimumSize(900, 560)
        self.resize(980, 640)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        intro = QLabel(
            "Các tham số dưới đây quyết định dữ liệu, giả định rủi ro và chi phí giao dịch khi chạy backtest. "
            "Hiểu đúng các ô này giúp kết quả gần với điều kiện giao dịch thật hơn."
        )
        intro.setObjectName("HelperText")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.table = QTableWidget(len(self.HELP_ROWS), 3)
        self.table.setObjectName("DataTable")
        self.table.setHorizontalHeaderLabels(["Ô nhập", "Ý nghĩa", "Cách hiểu cho người mới"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setWordWrap(True)
        self.table.setAlternatingRowColors(True)

        for row, values in enumerate(self.HELP_ROWS):
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                item.setTextAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
                self.table.setItem(row, column, item)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 130)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(82)
        layout.addWidget(self.table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.setText("Đóng")
            close_btn.setObjectName("PrimaryButton")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
