from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PyQt6.QtCore import QDate, QEvent, QLocale, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
        QAbstractSpinBox,
        QDialog,
        QDialogButtonBox,
        QFileDialog,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QCheckBox,
        QScrollArea,
        QSizePolicy,
        QSpinBox,
        QTableWidget,
        QTableWidgetItem,
        QTextEdit,
        QVBoxLayout,
        QWidget,
)

from config.constants import SUPPORTED_SYMBOLS
from controllers.backtest_controller import BacktestController
from ui.screens.shared import action_button, card, page_header


class BacktestScreen(QWidget):
    TRADE_COLUMNS = [
        ("stt", "STT"),
        ("symbol", "Mã"),
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
        "stt": 0.40,
        "symbol": 0.68,
        "entry_time": 1.55,
        "side": 0.60,
        "result": 0.70,
        "result_r": 0.48,
        "entry_price": 0.78,
        "stop_loss": 0.78,
        "take_profit": 0.78,
        "final_score": 0.64,
        "signal_score": 0.64,
        "m15_quality": 0.58,
        "market_regime": 0.82,
        "selected_zone_score": 0.48,
    }

    def __init__(self, navigate=None, *, app=None) -> None:
        super().__init__()
        self.navigate = navigate
        self.app = app
        self.controller = (
            app.backtest_controller if app else BacktestController()
        )
        self.backtest_thread = None
        self.backtest_worker = None
        self.result: dict[str, object] | None = None
        self.selected_symbols = ["EUR/USD"]
        self.setObjectName("FormScreen")
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)
        root.addWidget(
            page_header(
                "Kiểm thử hệ thống",
                "Chạy lại pipeline phân tích trên dữ liệu lịch sử để đo kỳ vọng, drawdown và lợi thế theo nhóm.",
            )
        )
        root.addWidget(self._settings_card())
        root.addWidget(self._trades_card(), 1)

    def _settings_card(self) -> QFrame:
        frame = card(None)
        frame.setStyleSheet(self._backtest_form_stylesheet())
        frame.layout().setContentsMargins(12, 10, 12, 4)
        frame.layout().setSpacing(2)
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

        account_box = self._section_box("Tài khoản")
        account_grid = QGridLayout()
        account_grid.setContentsMargins(0, 0, 0, 0)
        account_grid.setHorizontalSpacing(0)
        account_grid.setVerticalSpacing(6)
        account_box.layout().addLayout(account_grid)

        simulation_box = self._section_box("Mô phỏng")
        simulation_grid = QGridLayout()
        simulation_grid.setContentsMargins(0, 0, 0, 0)
        simulation_grid.setHorizontalSpacing(6)
        simulation_grid.setVerticalSpacing(6)
        simulation_grid.setColumnMinimumWidth(0, 76)
        simulation_grid.setColumnStretch(1, 1)
        simulation_grid.setColumnMinimumWidth(2, 68)
        simulation_grid.setColumnStretch(3, 1)
        simulation_box.layout().addLayout(simulation_grid)

        self.symbol_summary = QLabel("")
        self.symbol_summary.setObjectName("BacktestSymbolSummary")
        self.symbol_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.symbol_button = action_button("🔍 Chọn mã", primary=True, color="info")
        self.symbol_button.clicked.connect(self._show_symbol_dialog)
        self._update_symbol_summary()

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
        self.mode_combo.addItem("Balanced", "balanced")
        self.mode_combo.addItem("Legacy", "legacy")
        self.mode_combo.addItem("Research", "research")
        self.mode_combo.addItem("Kiểm thử (nới lỏng nhất)", "backtest")

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
        self.max_holding_input.setFixedWidth(72)

        self.min_score_input = QSpinBox()
        self._apply_number_format(self.min_score_input)
        self.min_score_input.setRange(0, 100)
        self.min_score_input.setValue(0)
        self.min_score_input.setToolTip("Điểm final_score tối thiểu để vào lệnh. 0 = không lọc.")
        self.min_score_input.setFixedWidth(64)

        self.guard_checkbox = QCheckBox("Bảo vệ tài khoản")
        self.guard_checkbox.setObjectName("BacktestField")
        self.guard_checkbox.setToolTip("Bật giới hạn thua lỗ thực tế (daily loss, consecutive losses)")

        self.max_daily_loss_input = QDoubleSpinBox()
        self._apply_number_format(self.max_daily_loss_input)
        self.max_daily_loss_input.setRange(0.1, 100.0)
        self.max_daily_loss_input.setDecimals(1)
        self.max_daily_loss_input.setValue(2.0)
        self.max_daily_loss_input.setSuffix(" %")
        self.max_daily_loss_input.setEnabled(False)

        self.max_consecutive_loss_input = QSpinBox()
        self._apply_number_format(self.max_consecutive_loss_input)
        self.max_consecutive_loss_input.setRange(1, 100)
        self.max_consecutive_loss_input.setValue(3)
        self.max_consecutive_loss_input.setEnabled(False)

        self.guard_checkbox.toggled.connect(self._on_guard_toggled)

        self.macro_checkbox = QCheckBox("Dùng macro/correlation thật")
        self.macro_checkbox.setObjectName("BacktestField")
        self.macro_checkbox.setToolTip("Lấy dữ liệu DXY/VIX/US10Y và macro alignment hiện tại thay vì neutral. Làm backtest thực tế hơn.")

        for field in (
            self.start_date,
            self.end_date,
            self.balance_input,
            self.risk_input,
            self.mode_combo,
            self.max_holding_input,
            self.min_score_input,
            self.spread_input,
            self.slippage_input,
            self.max_daily_loss_input,
            self.max_consecutive_loss_input,
        ):
            field.setObjectName("BacktestField")

        market_grid.addWidget(self._symbol_cell(), 0, 0)
        market_grid.addWidget(self._field_cell("Từ ngày", self.start_date, 58), 1, 0)
        market_grid.addWidget(self._field_cell("Đến ngày", self.end_date, 58), 2, 0)
        market_grid.addWidget(self._field_cell("Chế độ", self.mode_combo, 58), 3, 0)

        params_label_width = 76
        account_grid.addWidget(self._field_cell("Số dư", self.balance_input, params_label_width), 0, 0)
        account_grid.addWidget(self._field_cell("Rủi ro", self.risk_input, params_label_width), 1, 0)
        account_grid.addWidget(self.guard_checkbox, 2, 0)
        account_grid.addWidget(self._field_cell("Lỗ ngày tối đa", self.max_daily_loss_input, 104), 3, 0)
        account_grid.addWidget(self._field_cell("Chuỗi thua tối đa", self.max_consecutive_loss_input, 104), 4, 0)
        simulation_grid.addWidget(self._grid_label("Số nến"), 0, 0)
        simulation_grid.addWidget(self.max_holding_input, 0, 1)
        simulation_grid.addWidget(self._grid_label("Điểm tối thiểu"), 0, 2)
        simulation_grid.addWidget(self.min_score_input, 0, 3)
        simulation_grid.addWidget(self._grid_label("Spread"), 1, 0)
        simulation_grid.addWidget(self.spread_input, 1, 1, 1, 3)
        simulation_grid.addWidget(self._grid_label("Slippage"), 2, 0)
        simulation_grid.addWidget(self.slippage_input, 2, 1, 1, 3)
        simulation_grid.addWidget(self.macro_checkbox, 3, 0, 1, 4)

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

        top_row.addWidget(market_box, 2, Qt.AlignmentFlag.AlignTop)
        top_row.addWidget(self._vertical_separator())
        top_row.addWidget(account_box, 2, Qt.AlignmentFlag.AlignTop)
        top_row.addWidget(self._vertical_separator())
        top_row.addWidget(simulation_box, 2, Qt.AlignmentFlag.AlignTop)
        top_row.addWidget(self._vertical_separator())
        top_row.addWidget(summary_box, 3, Qt.AlignmentFlag.AlignTop)

        run_bar = QWidget()
        controls = QHBoxLayout(run_bar)
        controls.setContentsMargins(0, 10, 0, 10)
        controls.setSpacing(10)
        self.run_button = action_button("▶️ Chạy backtest", primary=True, color="success")
        self.run_button.clicked.connect(self._run_backtest)
        self.help_button = action_button("❓ Giải thích", primary=True, color="info")
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
        self.snapshot_label.setFixedHeight(24)
        self.snapshot_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.snapshot_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.snapshot_label.hide()
        frame.layout().addWidget(self.snapshot_label)
        return frame

    def _section_box(self, title: str) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        header = QLabel(title)
        header.setObjectName("BacktestSectionTitle")
        header.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(header)
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return box

    def _field_cell(self, label: str, field: QWidget, label_width: int = 64) -> QWidget:
        cell = QWidget()
        layout = QHBoxLayout(cell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        title = QLabel(label)
        title.setObjectName("FormLabel")
        title.setFixedWidth(label_width)
        title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        field.setMinimumWidth(0)
        layout.addWidget(title)
        layout.addWidget(field, 1)
        return cell

    def _grid_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("FormLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return label

    def _two_small_fields_cell(
        self,
        first_label: str,
        first_field: QWidget,
        second_label: str,
        second_field: QWidget,
        *,
        first_label_width: int,
        second_label_width: int,
    ) -> QWidget:
        cell = QWidget()
        layout = QHBoxLayout(cell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for label_text, field, width in (
            (first_label, first_field, first_label_width),
            (second_label, second_field, second_label_width),
        ):
            title = QLabel(label_text)
            title.setObjectName("FormLabel")
            title.setFixedWidth(width)
            title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(title)
            layout.addWidget(field)
        layout.addStretch(1)
        return cell

    def _symbol_cell(self) -> QWidget:
        cell = QWidget()
        layout = QHBoxLayout(cell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        title = QLabel("Mã")
        title.setObjectName("FormLabel")
        title.setFixedWidth(58)
        title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(title)
        layout.addWidget(self.symbol_summary, 1)
        layout.addWidget(self.symbol_button)
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
        frame = QFrame()
        frame.setObjectName("PanelCard")
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        title = QLabel("Danh sách lệnh")
        title.setObjectName("PanelTitle")
        header.addWidget(title)
        header.addStretch(1)

        load_btn = action_button("📂 Xem lại kết quả", primary=True, color="success")
        load_btn.clicked.connect(self._load_backtest_file)

        analyze_btn = action_button("🤖 Phân tích", primary=True, color="info")
        analyze_btn.clicked.connect(self._analyze_loaded_result)
        self.analyze_btn = analyze_btn

        
        header.addWidget(load_btn)
        header.addWidget(analyze_btn)
        layout.addLayout(header)

        self.table = QTableWidget(0, len(self.TRADE_COLUMNS))
        self.table.setObjectName("DataTable")
        self.table.setHorizontalHeaderLabels([label for _, label in self.TRADE_COLUMNS])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.viewport().installEventFilter(self)
        self._apply_trade_table_layout()
        layout.addWidget(self.table, 1)
        return frame

    def _load_backtest_file(self) -> None:
        from PyQt6.QtWidgets import QApplication
        from config.paths import app_data_dir
        default_dir = app_data_dir() / "backtests"
        default_dir.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(
            self, "Tải file backtest", str(default_dir),
            "Tệp JSON (*.json);;Tất cả tệp (*)",
        )
        if not path:
            return
        try:
            import json
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            summary = data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}
            trades = data.get("trades", []) if isinstance(data.get("trades"), list) else []
            self.result = data
            self._set_summary(summary)
            self._set_trades(trades)
            self.status_label.setText(f"Đã tải: {len(trades)} lệnh")
            self.snapshot_label.setText(f"File: {path}")
            self.snapshot_label.show()
        except Exception as exc:
            QMessageBox.warning(self, "Lỗi đọc file", f"Không đọc được file:\n{exc}")

    def _analyze_loaded_result(self) -> None:
        if not self.result:
            QMessageBox.information(self, "Phân tích", "Chưa có dữ liệu backtest. Hãy chạy backtest hoặc tải file trước.")
            return
        from PyQt6.QtWidgets import QApplication
        from services.ai_service import AIService, AIProviderConfig

        settings = (
            self.app.settings_service.load()
            if self.app
            else self.controller.settings_service.load()
        )
        active = settings.ai.active_provider()
        if not active or not (active.api_key or active.api_key_ref):
            QMessageBox.warning(self, "Phân tích", "Chưa cấu hình AI. Vào Cài đặt để chọn nhà cung cấp và nhập API key.")
            return

        self.analyze_btn.setText("⏳ Đang phân tích...")
        self.analyze_btn.setEnabled(False)
        QApplication.processEvents()

        try:
            prompt = self._build_analysis_prompt()
            config = AIProviderConfig(provider=active.provider, model=active.model, api_key=active.api_key)
            ai = self.app.create_ai_service(config) if self.app else AIService(config)
            response = ai.analyze(prompt)

            dlg = QDialog(self)
            dlg.setWindowTitle("Phân tích kết quả backtest")
            dlg.setMinimumSize(740, 560)
            dlg.setStyleSheet("QDialog { background: #1a1f2e; }")
            layout = QVBoxLayout(dlg)
            layout.setContentsMargins(20, 18, 20, 16)
            text = QTextEdit()
            text.setReadOnly(True)
            text.setStyleSheet(
                "QTextEdit { background: #171c24; color: #e5e7eb; font-size: 13px; border: 1px solid #2b3545; border-radius: 6px; padding: 16px; }"
            )
            
            stats_html = self._generate_stats_html()
            ai_html = self._format_ai_to_html(response)
            
            final_html = (
                f"{stats_html}"
                f"<hr style='border: 0; border-top: 1px dashed #334155; margin: 24px 0;' />"
                f"<div style='font-family:-apple-system,Segoe UI,sans-serif;'>"
                f"<h2 style='color:#a78bfa; margin-bottom: 12px; font-size: 16px;'>🤖 AI NHẬN XÉT & ĐÁNH GIÁ</h2>"
                f"{ai_html}"
                f"</div>"
            )
            
            text.setHtml(final_html)
            layout.addWidget(text, 1)
            close_btn = action_button("❌ Đóng")
            close_btn.clicked.connect(dlg.accept)
            btn_row = QHBoxLayout()
            btn_row.addStretch()
            btn_row.addWidget(close_btn)
            layout.addLayout(btn_row)
            dlg.exec()
        except Exception as exc:
            QMessageBox.warning(self, "Lỗi phân tích", str(exc))
        finally:
            self.analyze_btn.setText("🤖 Phân tích")
            self.analyze_btn.setEnabled(True)

    def _build_analysis_prompt(self) -> str:
        summary = self.result.get("summary", {}) if isinstance(self.result.get("summary"), dict) else {}
        breakdowns = self.result.get("breakdowns", {}) if isinstance(self.result.get("breakdowns"), dict) else {}
        by_symbol = breakdowns.get("by_symbol", {}) if isinstance(breakdowns, dict) else {}

        lines = [
            "Dựa vào các số liệu backtest sau, hãy đưa ra NHẬN XÉT VÀ ĐÁNH GIÁ (không cần lặp lại số liệu):",
            "",
            "TỔNG HỢP TẤT CẢ MÃ:",
            f"  Tổng số lệnh: {summary.get('total_trades', 'N/A')}",
            f"  Tỷ lệ thắng: {summary.get('win_rate', 'N/A')}%",
            f"  Kỳ vọng: {summary.get('expectancy_r', 'N/A')}R",
            f"  Hệ số lợi nhuận: {summary.get('profit_factor', 'N/A')}",
            f"  Drawdown tối đa: {summary.get('max_drawdown_r', 'N/A')}R",
            f"  Tổng R: {summary.get('total_r', 'N/A')}R",
        ]

        if by_symbol:
            lines.append("")
            lines.append("PHÂN TÍCH THEO TỪNG CẶP:")
            for symbol, sym_stats in by_symbol.items():
                if not isinstance(sym_stats, dict):
                    continue
                lines.append(f"  {symbol}:")
                lines.append(f"    Số lệnh: {sym_stats.get('total_trades', 'N/A')}")
                lines.append(f"    Tỷ lệ thắng: {sym_stats.get('win_rate', 'N/A')}%")
                lines.append(f"    Kỳ vọng: {sym_stats.get('expectancy_r', 'N/A')}R")
                lines.append(f"    Hệ số lợi nhuận: {sym_stats.get('profit_factor', 'N/A')}")
                lines.append(f"    Drawdown tối đa: {sym_stats.get('max_drawdown_r', 'N/A')}R")
                lines.append(f"    Tổng R: {sym_stats.get('total_r', 'N/A')}R")

        lines.extend([
            "",
            "Yêu cầu Đánh giá:",
            "1. Hệ thống này có edge (lợi thế) không?",
            "2. Rủi ro chính là gì?",
            "3. Có nên trade live không? Nếu có thì cần điều kiện gì?",
            "4. So sánh hiệu suất giữa các cặp (nếu có nhiều cặp), cặp nào tốt nhất/tệ nhất?",
            "",
            "Trả lời ngắn gọn, bullet point, KHÔNG dùng ký tự * hay markdown. KHÔNG CẦN CHÉP LẠI BẢNG THỐNG KÊ, CHỈ ĐƯA RA NHẬN XÉT.",
        ])
        return "\n".join(lines)

    def _generate_stats_html(self) -> str:
        summary = self.result.get("summary", {}) if isinstance(self.result.get("summary"), dict) else {}
        breakdowns = self.result.get("breakdowns", {}) if isinstance(self.result.get("breakdowns"), dict) else {}
        by_symbol = breakdowns.get("by_symbol", {}) if isinstance(breakdowns, dict) else {}

        def get_stat(data: dict, key: str, default: str = "0.00") -> str:
            val = data.get(key)
            if val is None:
                return default
            if isinstance(val, (int, float)):
                return f"{val:.2f}" if isinstance(val, float) else str(val)
            return str(val)

        def eval_winrate(wr: float) -> str:
            if wr >= 55: return "🟢 Tốt"
            if wr >= 45: return "🟡 Ổn định"
            return "🔴 Cảnh báo"

        def eval_profit_factor(pf: float) -> str:
            if pf >= 1.5: return "🔥 Tuyệt vời"
            if pf >= 1.1: return "👍 Khả quan"
            return "⚠️ Rủi ro"

        def eval_drawdown(dd: float) -> str:
            if dd > -10: return "🛡️ An toàn"
            if dd > -20: return "⚠️ Cần theo dõi"
            return "🆘 Nguy hiểm"

        html = [
            "<div style='font-family:-apple-system,Segoe UI,sans-serif;'>",
            "<h2 style='color:#38bdf8; margin-top: 0; margin-bottom: 12px; font-size: 16px;'>📊 BẢNG KẾT QUẢ TỔNG HỢP</h2>",
        ]
        
        wr = float(summary.get("win_rate", 0) or 0)
        pf = float(summary.get("profit_factor", 0) or 0)
        dd = float(summary.get("max_drawdown_r", 0) or 0)
        
        html.append(
            f"<table style='width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 13px;'>"
            f"<tr>"
            f"<th style='text-align: left; padding: 10px; border-bottom: 2px solid #334155; color: #94a3b8;'>Chỉ số</th>"
            f"<th style='text-align: right; padding: 10px; border-bottom: 2px solid #334155; color: #94a3b8;'>Giá trị</th>"
            f"<th style='text-align: right; padding: 10px; border-bottom: 2px solid #334155; color: #94a3b8;'>Đánh giá</th>"
            f"</tr>"
            
            f"<tr>"
            f"<td style='padding: 10px; border-bottom: 1px solid #1e293b; color: #e2e8f0;'>🔢 Tổng số lệnh</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid #1e293b; color: #f8fafc; font-weight: bold;'>{get_stat(summary, 'total_trades', '0')}</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid #1e293b; color: #94a3b8;'>-</td>"
            f"</tr>"
            
            f"<tr>"
            f"<td style='padding: 10px; border-bottom: 1px solid #1e293b; color: #e2e8f0;'>🎯 Tỷ lệ thắng</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid #1e293b; color: #f8fafc; font-weight: bold;'>{get_stat(summary, 'win_rate')}%</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid #1e293b;'>{eval_winrate(wr)}</td>"
            f"</tr>"
            
            f"<tr>"
            f"<td style='padding: 10px; border-bottom: 1px solid #1e293b; color: #e2e8f0;'>💎 Hệ số lợi nhuận</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid #1e293b; color: #f8fafc; font-weight: bold;'>{get_stat(summary, 'profit_factor')}</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid #1e293b;'>{eval_profit_factor(pf)}</td>"
            f"</tr>"

            f"<tr>"
            f"<td style='padding: 10px; border-bottom: 1px solid #1e293b; color: #e2e8f0;'>🚀 Kỳ vọng</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid #1e293b; color: #f8fafc; font-weight: bold;'>{get_stat(summary, 'expectancy_r')}R</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid #1e293b; color: #94a3b8;'>-</td>"
            f"</tr>"
            
            f"<tr>"
            f"<td style='padding: 10px; border-bottom: 1px solid #1e293b; color: #e2e8f0;'>📉 Drawdown tối đa</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid #1e293b; color: #f8fafc; font-weight: bold;'>{get_stat(summary, 'max_drawdown_r')}R</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid #1e293b;'>{eval_drawdown(dd)}</td>"
            f"</tr>"
            
            f"<tr>"
            f"<td style='padding: 10px; border-bottom: 1px solid #1e293b; color: #e2e8f0;'>💰 Tổng R</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid #1e293b; color: #22c55e; font-weight: bold;'>{get_stat(summary, 'total_r')}R</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid #1e293b; color: #94a3b8;'>-</td>"
            f"</tr>"
            f"</table>"
        )

        if by_symbol and len(by_symbol) > 0:
            html.append("<h2 style='color:#fbbf24; margin-bottom: 16px; margin-top: 24px; font-size: 16px;'>🌍 CHI TIẾT TỪNG CẶP</h2>")
            html.append("<div style='display: flex; flex-wrap: wrap; gap: 12px;'>")
            
            for symbol, sym_stats in by_symbol.items():
                if not isinstance(sym_stats, dict):
                    continue
                sym_wr = float(sym_stats.get("win_rate", 0) or 0)
                sym_pf = float(sym_stats.get("profit_factor", 0) or 0)
                sym_dd = float(sym_stats.get("max_drawdown_r", 0) or 0)
                
                html.append(
                    f"<div style='background-color: #1e293b; border-radius: 8px; padding: 14px; width: calc(50% - 6px); box-sizing: border-box; border-left: 4px solid #38bdf8;'>"
                    f"<div style='font-size: 15px; font-weight: bold; color: #f8fafc; margin-bottom: 10px;'>✨ {symbol}</div>"
                    f"<table style='width: 100%; border-collapse: collapse; font-size: 13px;'>"
                    f"<tr>"
                    f"<td style='padding: 4px 0;'><span style='color: #94a3b8;'>Lệnh:</span> <span style='color: #e2e8f0; font-weight: bold;'>{get_stat(sym_stats, 'total_trades', '0')}</span></td>"
                    f"<td style='padding: 4px 0;'><span style='color: #94a3b8;'>Kỳ vọng:</span> <span style='color: #e2e8f0; font-weight: bold;'>{get_stat(sym_stats, 'expectancy_r')}R</span></td>"
                    f"</tr>"
                    f"<tr>"
                    f"<td style='padding: 4px 0;'><span style='color: #94a3b8;'>Tỷ lệ thắng:</span> <span style='color: #e2e8f0; font-weight: bold;'>{get_stat(sym_stats, 'win_rate')}%</span> {eval_winrate(sym_wr)}</td>"
                    f"<td style='padding: 4px 0;'><span style='color: #94a3b8;'>PF:</span> <span style='color: #e2e8f0; font-weight: bold;'>{get_stat(sym_stats, 'profit_factor')}</span> {eval_profit_factor(sym_pf)}</td>"
                    f"</tr>"
                    f"<tr>"
                    f"<td style='padding: 4px 0;'><span style='color: #94a3b8;'>Tổng R:</span> <span style='color: #22c55e; font-weight: bold;'>{get_stat(sym_stats, 'total_r')}R</span></td>"
                    f"<td style='padding: 4px 0;'><span style='color: #94a3b8;'>DD:</span> <span style='color: #ef4444; font-weight: bold;'>{get_stat(sym_stats, 'max_drawdown_r')}R</span></td>"
                    f"</tr>"
                    f"</table>"
                    f"</div>"
                )
            html.append("</div>")

        html.append("</div>")
        return "".join(html)

    @staticmethod
    def _format_ai_to_html(raw: str) -> str:
        lines = raw.splitlines()
        html_lines: list[str] = []
        in_ul = False
        in_ol = False

        def _close_lists():
            nonlocal in_ul, in_ol
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            if in_ol:
                html_lines.append("</ol>")
                in_ol = False

        i = 0
        while i < len(lines):
            line = lines[i]

            # Strip ** markers
            line = line.replace("**", "")

            stripped = line.strip()

            # Empty line -> close lists, add paragraph break
            if not stripped:
                _close_lists()
                html_lines.append("<br>")
                i += 1
                continue

            # Bold heading-like lines (all caps or ending with colon, short)
            is_heading = (
                stripped.isupper()
                or (stripped.endswith(":") and len(stripped) < 80 and not stripped.startswith(("-", "•", "*", "1.", "2.", "3.", "4.", "5.")))
            )

            if is_heading:
                _close_lists()
                html_lines.append(f"<p style='margin:14px 0 6px;font-weight:700;color:#f8fafc;font-size:14px;'>{stripped}</p>")
                i += 1
                continue

            # Bullet lines: -, *, •, or numbered 1. 2. etc.
            bullet_match = False
            prefix = ""

            m = re.match(r"^(\s*)([-*•])\s+(.*)", stripped)
            if m:
                bullet_match = True
                prefix = "ul"
                content = m.group(3)
            else:
                m = re.match(r"^(\s*)(\d+)[.)]\s+(.*)", stripped)
                if m:
                    bullet_match = True
                    prefix = "ol"
                    content = m.group(3)
                else:
                    # Check for bare * at start (italic marker)
                    m = re.match(r"^\*\s*(.*?)\*$", stripped)
                    if m:
                        # *text* -> italic
                        _close_lists()
                        html_lines.append(f"<p style='margin:4px 0;font-style:italic;color:#cbd5e1;'>{m.group(1)}</p>")
                        i += 1
                        continue
                    # Line starting with * but not a bullet - strip leading *
                    if stripped.startswith("*") and not stripped.startswith("* "):
                        stripped = stripped.lstrip("*")

            if bullet_match:
                if prefix == "ul" and not in_ul:
                    _close_lists()
                    html_lines.append("<ul style='margin-top:8px; margin-bottom:8px; padding-left:24px; color:#d1d5db;'>")
                    in_ul = True
                elif prefix == "ol" and not in_ol:
                    _close_lists()
                    html_lines.append("<ol style='margin-top:8px; margin-bottom:8px; padding-left:24px; color:#d1d5db;'>")
                    in_ol = True
                # Strip remaining * in content
                content = content.replace("*", "")
                html_lines.append(f"<li style='margin-top:8px; margin-bottom:8px;'>{content}</li>")
                i += 1
                continue

            # Regular paragraph line
            _close_lists()
            # Strip any remaining standalone * markers
            clean = stripped.replace("*", "")
            html_lines.append(f"<p style='margin-top:8px; margin-bottom:8px; color:#d1d5db;'>{clean}</p>")
            i += 1

        _close_lists()

        body = "\n".join(html_lines)
        return (
            "<div style='font-family:-apple-system,Segoe UI,sans-serif; font-size:13px;'>"
            + body
            + "</div>"
        )

    def _show_input_help(self) -> None:
        dialog = BacktestInputHelpDialog(self)
        dialog.exec()

    def _show_symbol_dialog(self) -> None:
        dialog = SymbolSelectionDialog(self.selected_symbols, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.selected_symbols = dialog.selected_symbols()
            self._update_symbol_summary()

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if hasattr(self, "table") and watched is self.table.viewport() and event.type() == QEvent.Type.Resize:
            self._resize_trade_columns_to_viewport()
        return super().eventFilter(watched, event)

    def _run_backtest(self) -> None:
        try:
            requests = self.controller.build_requests(
                symbols=self._selected_symbols(),
                start=self._qdate_to_utc_start(self.start_date.date()),
                end=self._qdate_to_utc_end(self.end_date.date()),
                initial_balance=self.balance_input.value(),
                risk_percent=self.risk_input.value(),
                mode=str(self.mode_combo.currentData()),
                spread_price=self.spread_input.value(),
                slippage_price=self.slippage_input.value(),
                max_holding_bars=self.max_holding_input.value(),
                min_final_score=self.min_score_input.value(),
                account_guard_enabled=self.guard_checkbox.isChecked(),
                max_daily_loss_pct=self.max_daily_loss_input.value(),
                max_consecutive_losses=self.max_consecutive_loss_input.value(),
                allow_macro=self.macro_checkbox.isChecked(),
            )
        except Exception as exc:
            QMessageBox.warning(self, "Không tạo được request", str(exc))
            return

        self.run_button.setEnabled(False)
        self.progress.setValue(0)
        self.status_label.setText("Đang chạy backtest...")
        self.backtest_thread, self.backtest_worker = self.controller.create_backtest_worker(requests)
        self.backtest_worker.progress.connect(self._on_progress)
        self.backtest_worker.succeeded.connect(self._on_success)
        self.backtest_worker.failed.connect(self._on_failed)
        self.backtest_worker.finished.connect(lambda: self.run_button.setEnabled(True))
        self.backtest_thread.start()

    def _on_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(percent)
        self.status_label.setText(message)

    def _on_guard_toggled(self, checked: bool) -> None:
        self.max_daily_loss_input.setEnabled(checked)
        self.max_consecutive_loss_input.setEnabled(checked)

    def _on_success(self, result: dict) -> None:
        self.result = result
        self.status_label.setText("Hoàn tất backtest.")
        self._set_summary(result.get("summary", {}) if isinstance(result.get("summary"), dict) else {})
        self._set_trades(result.get("trades", []) if isinstance(result.get("trades"), list) else [])
        self.snapshot_label.setText(f"File kết quả: {result.get('snapshot_path', '')}")
        self.snapshot_label.show()

    def _on_failed(self, message: str) -> None:
        self.status_label.setText("Kiểm thử thất bại.")
        QMessageBox.critical(self, "Kiểm thử thất bại", message)

    def _set_summary(self, summary: dict[str, object]) -> None:
        while self.summary_row.count():
            item = self.summary_row.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        items = [
            ("Số lệnh", self._format_integer(summary.get("total_trades", 0))),
            ("Tỷ lệ thắng", self._format_decimal(summary.get("win_rate", 0), 2, "%")),
            ("Kỳ vọng", self._format_decimal(summary.get("expectancy_r", 0), 2, "R")),
            ("Hệ số lợi nhuận", self._format_decimal(summary.get("profit_factor", 0), 2)),
            ("DD tối đa", self._format_decimal(summary.get("max_drawdown_r", 0), 2, "R")),
            ("Tổng R", self._format_decimal(summary.get("total_r", 0), 2, "R")),
        ]
        for index, (title, value) in enumerate(items):
            self.summary_row.addWidget(self._stat_cell(str(title), str(value)), index // 3, index % 3)

    def _set_trades(self, trades: list[dict[str, object]]) -> None:
        self.table.setRowCount(len(trades))
        for row, trade in enumerate(trades):
            for col, (key, _label) in enumerate(self.TRADE_COLUMNS):
                if key == "stt":
                    value = str(row + 1)
                else:
                    value = self._format_trade_value(key, trade.get(key, "--"))
                item = QTableWidgetItem(value)
                if key in {"stt", "result_r", "final_score", "signal_score", "selected_zone_score"}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, col, item)
        self._apply_trade_table_layout()

    def _selected_symbols(self) -> list[str]:
        return list(self.selected_symbols)

    def _update_symbol_summary(self) -> None:
        count = len(self.selected_symbols)
        if count <= 3:
            text = ", ".join(self.selected_symbols)
        else:
            text = f"{count} mã: " + ", ".join(self.selected_symbols[:3]) + "..."
        self.symbol_summary.setText(text or "Chưa chọn mã")
        self.symbol_summary.setToolTip(", ".join(self.selected_symbols))

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
        QLabel#BacktestSectionTitle {
            color: #f8fafc;
            font-size: 13px;
            font-weight: 800;
            padding-bottom: 2px;
            border-bottom: 1px solid #334155;
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
            "Chọn một hoặc nhiều mã để chạy backtest.",
            "Nên test nhiều mã cùng nhóm để biết chiến lược có ổn định hay chỉ tốt trên một mã riêng lẻ.",
        ),
        (
            "Từ ngày",
            "Ngày bắt đầu lấy dữ liệu lịch sử.",
            "Khoảng thời gian càng dài thì kết quả càng đáng tin hơn, nhưng thời gian chạy cũng lâu hơn.",
        ),
        (
            "Đến ngày",
            "Ngày kết thúc vùng dữ liệu backtest.",
            "Dùng để kiểm tra một giai đoạn cụ thể, ví dụ 6 tháng gần nhất hoặc một năm thị trường biến động mạnh.",
        ),
        (
            "Chế độ",
            "Mức độ nới/lọc tín hiệu trước khi cho phép vào lệnh.",
            "Strict lọc chặt nhất. Balanced cân bằng hơn. Research dùng để khảo sát rộng. Kiểm thử nới lỏng hơn để đo hệ thống nhưng vẫn loại WATCH_ONLY.",
        ),
        (
            "Số dư",
            "Vốn giả định ban đầu của tài khoản.",
            "Dùng để quy đổi rủi ro theo tiền. Ví dụ tài khoản 10,000 USD thì nhập 10,000.",
        ),
        (
            "Rủi ro",
            "Phần trăm tài khoản chấp nhận mất nếu một lệnh chạm stop loss.",
            "Ví dụ 1% với tài khoản 10,000 nghĩa là mỗi lệnh rủi ro khoảng 100.",
        ),
        (
            "Bảo vệ tài khoản",
            "Công tắc bật/tắt giới hạn rủi ro tài khoản.",
            "Không tick thì hai ô Lỗ ngày tối đa và Chuỗi thua tối đa không có tác dụng. Tick vào thì kiểm thử sẽ áp dụng hai giới hạn này.",
        ),
        (
            "Lỗ ngày tối đa",
            "Mức lỗ tối đa trong một ngày, tính theo phần trăm tài khoản.",
            "Chỉ có tác dụng khi tick Bảo vệ tài khoản. Ví dụ 2% nghĩa là nếu trong ngày lỗ tới ngưỡng này thì hệ thống dừng nhận thêm lệnh trong ngày đó.",
        ),
        (
            "Chuỗi thua tối đa",
            "Số lệnh thua liên tiếp tối đa được phép.",
            "Chỉ có tác dụng khi tick Bảo vệ tài khoản. Ví dụ 3 nghĩa là sau 3 lệnh thua liên tiếp, hệ thống dừng theo quy tắc bảo vệ.",
        ),
        (
            "Số nến",
            "Số nến tối đa một lệnh được giữ sau khi vào.",
            "Nếu hết số nến mà chưa chạm TP/SL, backtest sẽ thoát theo quy tắc thời gian. Số lớn giữ lệnh lâu hơn.",
        ),
        (
            "Điểm tối thiểu",
            "Điểm final_score tối thiểu để được vào lệnh.",
            "Đặt 0 nghĩa là không lọc theo điểm. Tăng số này sẽ ít lệnh hơn nhưng kỳ vọng chất lượng setup cao hơn.",
        ),
        (
            "Spread",
            "Chi phí chênh lệch mua/bán, tính trực tiếp theo đơn vị giá.",
            "Spread càng cao thì kết quả càng khó tốt. Nên nhập gần điều kiện broker thực tế.",
        ),
        (
            "Slippage",
            "Mức trượt giá giả định khi khớp lệnh.",
            "Dùng để mô phỏng lúc lệnh không khớp đúng giá mong muốn, nhất là khi thị trường chạy nhanh.",
        ),
        (
            "Macro/correlation",
            "Cho phép dùng dữ liệu DXY, VIX, US10Y và tương quan thật thay vì giả định trung lập.",
            "Bật lên thì backtest sát bối cảnh thị trường hơn, nhưng phụ thuộc vào dữ liệu macro/correlation có sẵn.",
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
            "Dialog này giải thích từng ô trong form backtest. "
            "Cách hiểu nhanh: Dữ liệu chọn mã/thời gian/chế độ, Tài khoản mô phỏng vốn và giới hạn rủi ro, "
            "Mô phỏng chỉnh điều kiện khớp lệnh, Kết quả hiển thị thống kê sau khi chạy."
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
        self.table.verticalHeader().setDefaultSectionSize(76)
        layout.addWidget(self.table, 1)

        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 8, 0, 0)
        buttons_layout.addStretch(1)
        close_btn = action_button("❌ Đóng")
        close_btn.clicked.connect(self.accept)
        buttons_layout.addWidget(close_btn)
        layout.addLayout(buttons_layout)


class SymbolSelectionDialog(QDialog):
    def __init__(self, selected_symbols: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Chọn mã kiểm thử")
        self.setObjectName("ScannerHelpDialog")
        self.setModal(True)
        self.setMinimumSize(520, 620)
        self.checkboxes: dict[str, QCheckBox] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.select_all_button = action_button("✅ Chọn tất cả", primary=True, color="success")
        self.clear_button = action_button("❌ Bỏ chọn", primary=True, color="danger")
        self.forex_button = action_button("💱 Forex", primary=True, color="info")
        self.metal_crypto_button = action_button("🪙 Kim loại/Crypto", primary=True, color="info")
        for button in (self.select_all_button, self.clear_button, self.forex_button, self.metal_crypto_button):
            controls.addWidget(button)
        root.addLayout(controls)

        scroll = QScrollArea()
        scroll.setObjectName("SymbolSelectionScroll")
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("SymbolSelectionContent")
        grid = QGridLayout(content)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        selected_set = set(selected_symbols)
        symbols = sorted(SUPPORTED_SYMBOLS)
        for index, symbol in enumerate(symbols):
            checkbox = QCheckBox(symbol)
            checkbox.setChecked(symbol in selected_set)
            self.checkboxes[symbol] = checkbox
            grid.addWidget(checkbox, index // 3, index % 3)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 8, 0, 0)
        buttons_layout.setSpacing(8)
        buttons_layout.addStretch(1)
        cancel_btn = action_button("❌ Hủy", primary=False, color="danger")
        ok_btn = action_button("✅ Áp dụng", primary=True, color="success")
        buttons_layout.addWidget(cancel_btn)
        buttons_layout.addWidget(ok_btn)
        root.addLayout(buttons_layout)

        self.select_all_button.clicked.connect(lambda: self._set_all(True))
        self.clear_button.clicked.connect(lambda: self._set_all(False))
        self.forex_button.clicked.connect(self._select_forex)
        self.metal_crypto_button.clicked.connect(self._select_metal_crypto)
        ok_btn.clicked.connect(self._accept_if_valid)
        cancel_btn.clicked.connect(self.reject)

    def selected_symbols(self) -> list[str]:
        return [symbol for symbol, checkbox in self.checkboxes.items() if checkbox.isChecked()]

    def _set_all(self, checked: bool) -> None:
        for checkbox in self.checkboxes.values():
            checkbox.setChecked(checked)

    def _select_forex(self) -> None:
        for symbol, checkbox in self.checkboxes.items():
            checkbox.setChecked(symbol not in {"XAU/USD", "XAG/USD", "BTC/USD"})

    def _select_metal_crypto(self) -> None:
        for symbol, checkbox in self.checkboxes.items():
            checkbox.setChecked(symbol in {"XAU/USD", "XAG/USD", "BTC/USD"})

    def _accept_if_valid(self) -> None:
        if not self.selected_symbols():
            QMessageBox.warning(self, "Chưa chọn mã", "Cần chọn ít nhất một mã để backtest.")
            return
        self.accept()
