from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os

from PyQt6.QtCore import QDate, QEvent, QLocale, QObject, QThread, Qt, QUrl, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QDoubleSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config.constants import SUPPORTED_SYMBOLS
from controllers.backtest_controller import BacktestController
from core.param_sensitivity import (
    DEFAULT_PERIODS,
    DEFAULT_SWEEP_CONFIGS,
    SECONDARY_SWEEP_CONFIGS,
    MarketPeriod,
    ParamSweepConfig,
    export_results,
)
from ui.screens.shared import action_button, card, page_header


class _AIAnalyzeWorker(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, ai_service: object, prompt: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._ai = ai_service
        self._prompt = prompt

    def run(self) -> None:
        try:
            response = self._ai.analyze(self._prompt)
            self.finished.emit(response)
        except Exception as exc:
            self.error.emit(str(exc))


class BacktestScreen(QWidget):
    TRADE_COLUMNS = [
        ("stt", "STT"),
        ("entry_time", "Thời gian vào"),
        ("side", "Hướng"),
        ("result", "Kết quả"),
        ("result_r", "R"),
        ("final_score", "Điểm"),
        ("market_regime", "Regime"),
        ("expected_effective_rr", "RR kỳ vọng"),
    ]
    TRADE_COLUMN_WEIGHTS = {
        "stt": 4,
        "entry_time": 22,
        "side": 8,
        "result": 10,
        "result_r": 8,
        "final_score": 8,
        "market_regime": 14,
        "expected_effective_rr": 12,
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
        self.selected_symbol: str = "EUR/USD"
        self.setObjectName("FormScreen")
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)
        root.addWidget(
            page_header(
                "Backtest",
                "",
            )
        )
        root.addWidget(self._settings_card())
        root.addWidget(self._trades_card(), 1)
        self._refresh_theme_styles()

    def _settings_card(self) -> QFrame:
        frame = card(None)
        self.settings_frame = frame
        self.settings_frame.setStyleSheet(self._backtest_form_stylesheet())
        frame.layout().setContentsMargins(12, 8, 12, 8)
        frame.layout().setSpacing(6)

        # Row 1: Inputs and Execution Controls
        inputs_row = QHBoxLayout()
        inputs_row.setContentsMargins(0, 0, 0, 0)
        inputs_row.setSpacing(8)
        frame.layout().addLayout(inputs_row)

        def create_form_label(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setObjectName("FormLabel")
            lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            return lbl

        self.symbol_summary = QLabel("EUR/USD")
        self.symbol_summary.setObjectName("BacktestSymbolSummary")
        self.symbol_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.symbol_summary.setFixedWidth(65)
        self.symbol_summary.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.symbol_button = action_button("🔍 Chọn", primary=True, color="info")
        self.symbol_button.setProperty("btnSize", "small")
        self.symbol_button.clicked.connect(self._show_symbol_dialog)

        today = QDate.currentDate()
        self.start_date = QDateEdit(today.addMonths(-6))
        self.start_date.setCalendarPopup(True)
        self.start_date.setDisplayFormat("dd/MM/yyyy")
        self.start_date.setFixedWidth(110)

        self.end_date = QDateEdit(today)
        self.end_date.setCalendarPopup(True)
        self.end_date.setDisplayFormat("dd/MM/yyyy")
        self.end_date.setFixedWidth(110)

        self.balance_input = QDoubleSpinBox()
        self._apply_number_format(self.balance_input)
        self.balance_input.setRange(100, 100_000_000)
        self.balance_input.setDecimals(2)
        self.balance_input.setValue(10_000)
        self.balance_input.setFixedWidth(95)

        self.risk_input = QDoubleSpinBox()
        self._apply_number_format(self.risk_input)
        self.risk_input.setRange(0.01, 10.0)
        self.risk_input.setDecimals(2)
        self.risk_input.setValue(1.0)
        self.risk_input.setSuffix(" %")
        self.risk_input.setFixedWidth(65)

        for field in (self.start_date, self.end_date, self.balance_input, self.risk_input):
            field.setObjectName("BacktestField")

        inputs_row.addWidget(create_form_label("Mã:"))
        inputs_row.addWidget(self.symbol_summary)
        inputs_row.addWidget(self.symbol_button)
        
        inputs_row.addWidget(self._vertical_separator())
        
        inputs_row.addWidget(create_form_label("Từ:"))
        inputs_row.addWidget(self.start_date)
        inputs_row.addWidget(create_form_label("Đến:"))
        inputs_row.addWidget(self.end_date)
        
        inputs_row.addWidget(self._vertical_separator())
        
        inputs_row.addWidget(create_form_label("Vốn:"))
        inputs_row.addWidget(self.balance_input)
        inputs_row.addWidget(create_form_label("Rủi ro:"))
        inputs_row.addWidget(self.risk_input)

        inputs_row.addWidget(self._vertical_separator())

        self.run_button = action_button("▶️ Chạy", primary=True, color="success")
        self.run_button.setProperty("btnSize", "small")
        self.run_button.clicked.connect(self._run_backtest)
        
        self.apply_config_btn = action_button("📋 Áp dụng cấu hình", primary=True, color="warning")
        self.apply_config_btn.setProperty("btnSize", "small")
        self.apply_config_btn.clicked.connect(self._apply_scanner_config)
        self.apply_config_btn.setToolTip("Phân tích kết quả backtest và áp dụng cấu hình đề xuất vào Scanner settings.")
        self.apply_config_btn.hide()


        self.progress = QProgressBar()
        self.progress.setObjectName("BacktestProgress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFixedHeight(16)

        self.status_label = QLabel("Sẵn sàng")
        self.status_label.setObjectName("HelperText")

        inputs_row.addWidget(self.run_button)
        inputs_row.addWidget(self.apply_config_btn)

        self.walk_forward_checkbox = QCheckBox("Walk-Forward")
        self.walk_forward_checkbox.setObjectName("BacktestField")
        self.walk_forward_checkbox.setToolTip("Bật Walk-Forward Analysis để kiểm tra tính ổn định qua thời gian (IS/OOS cuốn chiếu).")
        inputs_row.addWidget(self.walk_forward_checkbox)
        
        self.wf_help_btn = self._help_button(
            "Walk-Forward Analysis (WFA) là phương pháp tối ưu hóa cuốn chiếu:\n"
            "• Chia dữ liệu lịch sử thành nhiều đoạn In-Sample (tối ưu hóa) và Out-of-Sample (kiểm thử thực tế).\n"
            "• Giúp phát hiện hiện tượng quá khớp (overfitting) và đánh giá khả năng sinh lời thực tế của chiến thuật."
        )
        inputs_row.addWidget(self.wf_help_btn)

        inputs_row.addStretch(1)

        # Row 2: Progress and Status Bar
        progress_row = QHBoxLayout()
        progress_row.setContentsMargins(0, 2, 0, 2)
        progress_row.setSpacing(10)
        frame.layout().addLayout(progress_row)
        
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.status_label)

        # Row 2: Results Display
        results_row = QHBoxLayout()
        results_row.setContentsMargins(0, 2, 0, 0)
        results_row.setSpacing(8)
        frame.layout().addLayout(results_row)

        results_label = create_form_label("Kết quả:")
        results_label.setStyleSheet("font-weight: 800; color: #ea580c;")
        results_row.addWidget(results_label)

        self.summary_row = QHBoxLayout()
        self.summary_row.setContentsMargins(0, 0, 0, 0)
        self.summary_row.setSpacing(6)
        results_row.addLayout(self.summary_row)
        self._set_summary({})

        self.snapshot_label = QLabel("")
        self.snapshot_label.setObjectName("HelperText")
        self.snapshot_label.setFixedHeight(16)
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
        frame.setObjectName("MiniStatCompact")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(4)
        title_label = QLabel(f"{title}:")
        title_label.setObjectName("MiniStatTitleCompact")
        value_label = QLabel(value)
        value_label.setObjectName("MiniStatValueCompact")
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

        # --- Verdict banner (hidden until backtest) ---
        self.verdict_banner = QLabel("")
        self.verdict_banner.setObjectName("BacktestVerdict")
        self.verdict_banner.setWordWrap(False)
        self.verdict_banner.setTextFormat(Qt.TextFormat.RichText)
        self.verdict_banner.hide()
        layout.addWidget(self.verdict_banner)

        # --- Tab widget: Kết quả | Đường cong vốn | Danh sách lệnh ---
        self.tabs = QTabWidget()
        self.tabs.setObjectName("BacktestTabs")
        self.tabs.tabBar().setObjectName("BacktestTabBar")

        # Corner widget containing load_btn and analyze_btn
        corner_widget = QWidget()
        corner_layout = QHBoxLayout(corner_widget)
        corner_layout.setContentsMargins(0, 0, 0, 0)
        corner_layout.setSpacing(6)

        load_btn = action_button("📂 Xem lại kết quả", primary=True, color="success")
        load_btn.setProperty("btnSize", "small")
        load_btn.clicked.connect(self._load_backtest_file)

        analyze_btn = action_button("🤖 Phân tích", primary=True, color="info")
        analyze_btn.setProperty("btnSize", "small")
        analyze_btn.clicked.connect(self._analyze_loaded_result)
        self.analyze_btn = analyze_btn

        corner_layout.addWidget(load_btn)
        corner_layout.addWidget(analyze_btn)
        self.tabs.setCornerWidget(corner_widget, Qt.Corner.TopRightCorner)

        # Tab 0: Kết quả (HTML)
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setObjectName("BacktestResultText")
        self.tabs.addTab(self.result_text, "📊 Kết quả")

        # Tab 1: Đường cong vốn
        self._setup_equity_tab()
        self.tabs.addTab(self._equity_tab, "📈 Đường cong vốn")

        # Tab 2: Danh sách lệnh
        self.table = QTableWidget(0, len(self.TRADE_COLUMNS))
        self.table.setObjectName("EconTable")
        self.table.setHorizontalHeaderLabels([label for _, label in self.TRADE_COLUMNS])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.table.viewport().installEventFilter(self)
        self._apply_trade_table_layout()
        self.tabs.addTab(self.table, "📋 Danh sách lệnh")

        # Tab 3: Điều chỉnh tham số (Param Sensitivity)
        self._build_param_tuning_tab()
        self.tabs.addTab(self._sweep_tab, "🔧 Điều chỉnh tham số")

        self.tabs.currentChanged.connect(self._on_tab_changed)

        layout.addWidget(self.tabs, 1)
        return frame

    def _setup_equity_tab(self) -> None:
        self._equity_tab = QWidget()
        layout = QVBoxLayout(self._equity_tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        try:
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
            from matplotlib.figure import Figure
        except ImportError:
            fallback = QLabel("Biểu đồ yêu cầu matplotlib.\nCài: pip install matplotlib")
            fallback.setObjectName("EmptyText")
            fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fallback.setWordWrap(True)
            layout.addWidget(fallback)
            self._equity_canvas = None
            return
        self._equity_figure = Figure(tight_layout=True)
        self._equity_canvas = FigureCanvas(self._equity_figure)
        self._equity_canvas.setMinimumHeight(200)
        layout.addWidget(self._equity_canvas)

    def _on_tab_changed(self, index: int) -> None:
        pass

    # ── Param Tuning Tab ─────────────────────────────────────────────────

    def _build_param_tuning_tab(self) -> None:
        """Dựng tab Điều chỉnh tham số với form chọn + progress + kết quả."""
        self._sweep_tab = QWidget()
        layout = QVBoxLayout(self._sweep_tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # ── Form row ──
        form_row = QHBoxLayout()
        form_row.setContentsMargins(0, 0, 0, 0)
        form_row.setSpacing(8)

        # Nhãn + combobox chọn bộ tham số
        params_label = QLabel("Tham số:")
        params_label.setObjectName("FormLabel")
        form_row.addWidget(params_label)

        self.sweep_params_combo = QComboBox()
        self.sweep_params_combo.setObjectName("BacktestField")
        self.sweep_params_combo.setFixedWidth(200)
        self.sweep_params_combo.addItem("4 tham số ưu tiên", "priority4")
        self.sweep_params_combo.addItem("6 tham số ưu tiên", "priority6")
        self.sweep_params_combo.addItem("Tất cả (10 tham số)", "all")
        self.sweep_params_combo.setCurrentIndex(0)
        form_row.addWidget(self.sweep_params_combo)

        form_row.addWidget(self._help_button(
            "Chọn bộ tham số cần quét:\n"
            "• 4 tham số ưu tiên: SL distance, Zone SL buffer, Entry aggressiveness, TP selection\n"
            "• 6 tham số: thêm Swing SL buffer, SL Floor buffer\n"
            "• Tất cả: bao gồm cả secondary params (EQ TP max RR, TP2 min gap, Entry zone ATR, Min stop distance)"
        ))

        # Nhãn + combobox chọn giai đoạn
        period_label = QLabel("Giai đoạn:")
        period_label.setObjectName("FormLabel")
        form_row.addWidget(period_label)

        self.sweep_period_combo = QComboBox()
        self.sweep_period_combo.setObjectName("BacktestField")
        self.sweep_period_combo.setFixedWidth(180)
        self.sweep_period_combo.addItem("Tất cả giai đoạn", "all")
        for p in DEFAULT_PERIODS:
            self.sweep_period_combo.addItem(p.name, p.name)
        self.sweep_period_combo.setCurrentIndex(0)
        form_row.addWidget(self.sweep_period_combo)

        form_row.addWidget(self._help_button(
            "Chọn giai đoạn thị trường để test:\n"
            "• Trending 2023: thị trường có xu hướng rõ ràng\n"
            "• Range 2024: thị trường đi ngang, ít xu hướng\n"
            "• Volatile 2025: thị trường biến động cao (tariff news)\n"
            "• Mixed Full 2024: cả năm, đủ mọi chế độ\n"
            "• Tất cả: quét qua tất cả giai đoạn"
        ))

        # Nút chạy
        self.sweep_run_btn = action_button("▶️ Chạy quét", primary=True, color="success")
        self.sweep_run_btn.setProperty("btnSize", "small")
        self.sweep_run_btn.clicked.connect(self._run_param_sweep)
        form_row.addWidget(self.sweep_run_btn)

        # Nút mở báo cáo HTML
        self.sweep_report_btn = action_button("📂 Mở báo cáo", primary=True, color="info")
        self.sweep_report_btn.setProperty("btnSize", "small")
        self.sweep_report_btn.setFixedWidth(120)
        self.sweep_report_btn.clicked.connect(self._open_sweep_report)
        self.sweep_report_btn.hide()
        form_row.addWidget(self.sweep_report_btn)

        form_row.addWidget(self._help_button(
            "Quét (sweep) từng hằng số ATR qua nhiều giá trị khác nhau, "
            "chạy backtest trên mỗi tổ hợp để đo độ ổn định.\n\n"
            "STABLE = giá trị hiện tại tốt trên mọi giai đoạn.\n"
            "OVERFIT = mỗi giai đoạn tối ưu ở 1 giá trị khác nhau → cần chọn giá trị an toàn.\n"
            "INSENSITIVE = tham số ít ảnh hưởng → không cần ưu tiên."
        ))

        form_row.addStretch(1)
        layout.addLayout(form_row)

        # ── Progress ──
        progress_row = QHBoxLayout()
        progress_row.setContentsMargins(0, 0, 0, 0)
        progress_row.setSpacing(8)
        self.sweep_progress = QProgressBar()
        self.sweep_progress.setRange(0, 100)
        self.sweep_progress.setValue(0)
        self.sweep_progress.setFixedHeight(16)
        self.sweep_progress.setObjectName("BacktestProgress")
        progress_row.addWidget(self.sweep_progress, 1)

        self.sweep_status = QLabel("Sẵn sàng")
        self.sweep_status.setObjectName("HelperText")
        progress_row.addWidget(self.sweep_status)
        layout.addLayout(progress_row)

        # ── Results ──
        self.sweep_result_text = QTextEdit()
        self.sweep_result_text.setReadOnly(True)
        self.sweep_result_text.setObjectName("BacktestResultText")
        self.sweep_result_text.setHtml(
            '<p style="color:#94a3b8;text-align:center;padding:32px">'
            'Chọn tham số và bấm <b>▶️ Chạy quét</b> để bắt đầu.</p>'
        )
        layout.addWidget(self.sweep_result_text, 1)

    @staticmethod
    def _help_button(tooltip: str) -> QPushButton:
        """Tạo nút '?' tròn nhỏ — bấm vào hiện popup giải thích."""
        btn = QPushButton("?")
        btn.setFixedSize(20, 20)
        btn.setStyleSheet("""
            QPushButton {
                background: #e2e8f0; color: #475569; border: none;
                border-radius: 10px; font-size: 12px; font-weight: 700;
                padding: 0; margin: 0;
            }
            QPushButton:hover { background: #f39c12; color: #fff; }
        """)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        def _show_tip():
            from PyQt6.QtWidgets import QToolTip
            QToolTip.showText(btn.mapToGlobal(btn.rect().bottomRight()), tooltip, btn)

        btn.clicked.connect(_show_tip)
        return btn

    def _get_sweep_settings(self) -> dict:
        """Lấy cấu hình backtest từ form chính để dùng cho sweep."""
        try:
            if hasattr(self, 'app') and self.app:
                s = self.app.settings_service.load()
            else:
                s = self.controller.settings_service.load()
            return {
                "initial_balance": self.balance_input.value(),
                "risk_percent": self.risk_input.value(),
                "account_currency": s.trading.account_currency,
                "lot_step": s.trading.lot_step,
                "minimum_lot": s.trading.minimum_lot,
                "contract_size_override": s.trading.contract_size_override,
            }
        except Exception:
            return {
                "initial_balance": 10000, "risk_percent": 1.0,
                "account_currency": "USD", "lot_step": 0.01,
                "minimum_lot": 0.01, "contract_size_override": None,
            }

    def _run_param_sweep(self) -> None:
        """Bắt đầu quét tham số trên background thread."""
        try:
            # Chọn configs
            mode = self.sweep_params_combo.currentData()
            if mode == "priority4":
                configs = list(DEFAULT_SWEEP_CONFIGS[:4])
            elif mode == "priority6":
                configs = list(DEFAULT_SWEEP_CONFIGS[:6])
            else:
                configs = list(DEFAULT_SWEEP_CONFIGS) + list(SECONDARY_SWEEP_CONFIGS)

            # Chọn periods
            period_key = self.sweep_period_combo.currentData()
            if period_key == "all":
                periods = list(DEFAULT_PERIODS)
            else:
                periods = [p for p in DEFAULT_PERIODS if p.name == period_key]

            # Symbol từ form chính
            symbols = [self.selected_symbol]

            # Settings
            settings = self._get_sweep_settings()

            # UI state
            self.sweep_run_btn.setEnabled(False)
            self.sweep_report_btn.hide()
            self.sweep_progress.setValue(0)
            self.sweep_status.setText("Đang khởi động...")
            self.sweep_result_text.setHtml(
                '<p style="color:#94a3b8;text-align:center;padding:32px">'
                'Đang chạy... vui lòng đợi.</p>'
            )

            # Worker + thread
            from workers.param_sweep_worker import ParamSweepThread

            self._sweep_thread = ParamSweepThread(configs, periods, symbols, settings)
            self._sweep_thread.progress.connect(self._on_sweep_progress)
            self._sweep_thread.succeeded.connect(self._on_sweep_success)
            self._sweep_thread.failed.connect(self._on_sweep_failed)
            self._sweep_thread.finished.connect(lambda: self.sweep_run_btn.setEnabled(True))
            self._sweep_thread.finished.connect(self._sweep_thread.deleteLater)

            self._sweep_thread.start()

        except Exception as exc:
            import traceback
            self.sweep_status.setText(f"Lỗi khởi động: {exc}")
            self.sweep_run_btn.setEnabled(True)
            QMessageBox.critical(
                self, "Lỗi quét tham số",
                f"Không thể khởi động quét tham số:\n\n{exc}\n\n{traceback.format_exc()}",
            )

    def _on_sweep_progress(self, percent: int, message: str) -> None:
        self.sweep_progress.setValue(percent)
        self.sweep_status.setText(message)

    def _on_sweep_success(self, results: list) -> None:
        self._sweep_results = results
        self.sweep_status.setText("Hoàn tất quét tham số.")
        html = self._build_sweep_results_html(results)
        self.sweep_result_text.setHtml(html)

        # Export báo cáo ra file
        try:
            report_path = export_results(results)
            self._sweep_report_path = str(report_path)
            self.sweep_report_btn.show()
        except Exception:
            self._sweep_report_path = None

    def _on_sweep_failed(self, error_msg: str) -> None:
        self.sweep_status.setText(f"Lỗi: {error_msg}")
        self.sweep_result_text.setHtml(
            f'<p style="color:#e74c3c;text-align:center;padding:32px">'
            f'<b>Lỗi khi quét tham số:</b><br>{html.escape(error_msg)}</p>'
        )

    def _open_sweep_report(self) -> None:
        """Mở báo cáo HTML đã export bằng browser."""
        if getattr(self, '_sweep_report_path', None):
            import webbrowser
            webbrowser.open(self._sweep_report_path)

    def _build_sweep_results_html(self, results: list) -> str:
        """Tạo bảng HTML tổng quan kết quả sweep."""
        verdict_colors = {
            "STABLE": "#2ecc71", "OVERFIT": "#e74c3c",
            "SUSPECT": "#f39c12", "INSENSITIVE": "#95a5a6",
            "INCONCLUSIVE": "#95a5a6", "UNKNOWN": "#95a5a6",
        }

        rows_html = ""
        for r in results:
            vc = verdict_colors.get(r.verdict, "#95a5a6")
            score = f"{r.stability_score:.0f}" if r.stability_score is not None else "—"

            # Tìm giá trị hiện tại
            import core.risk_engine as _re
            current = getattr(_re, r.attr_name, "N/A")

            # Tìm best value
            valid_runs = [run for run in r.runs if run.error is None and run.total_trades > 0]
            best_val = "—"
            if valid_runs:
                from collections import defaultdict
                by_val: dict[float, list[float]] = defaultdict(list)
                for run in valid_runs:
                    by_val[run.param_value].append(run.expectancy_r)
                if by_val:
                    avg_by_val = {v: sum(exs)/len(exs) for v, exs in by_val.items()}
                    best_val = f"{max(avg_by_val, key=avg_by_val.get):.3f}"

            rec_text = html.escape(r.recommendation or "—")

            rows_html += f"""
            <tr>
                <td style="white-space:nowrap"><code>{r.attr_name}</code></td>
                <td style="white-space:nowrap"><code>{r.json_key}</code></td>
                <td style="text-align:center"><code>{current}</code></td>
                <td style="text-align:center"><code>{best_val}</code></td>
                <td style="text-align:center;color:{vc};font-weight:700">{r.verdict}</td>
                <td style="text-align:center">{score}</td>
                <td style="max-width:420px;font-size:11px">{rec_text}</td>
            </tr>"""

        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head><body style="font-family:-apple-system,'Segoe UI',sans-serif;margin:0;color:#1f2937">
<h3 style="margin:0 0 8px;font-size:12px">Quét tham số</h3>
<table style="border-collapse:collapse;width:100%;font-size:11px">
<thead><tr style="background:#f5f5f5">
    <th style="padding:6px 10px;text-align:left;border:1px solid #ddd">Biến</th>
    <th style="padding:6px 10px;text-align:left;border:1px solid #ddd">JSON Key</th>
    <th style="padding:6px 10px;text-align:center;border:1px solid #ddd">Hiện tại</th>
    <th style="padding:6px 10px;text-align:center;border:1px solid #ddd">Đề xuất</th>
    <th style="padding:6px 10px;text-align:center;border:1px solid #ddd">Đánh giá</th>
    <th style="padding:6px 10px;text-align:center;border:1px solid #ddd">Ổn định</th>
    <th style="padding:6px 10px;text-align:left;border:1px solid #ddd">Khuyến nghị</th>
</tr></thead><tbody>{rows_html}</tbody></table>
<p style="color:#94a3b8;font-size:11px;margin-top:12px">
<b>STABLE</b> = giữ nguyên &nbsp;|&nbsp;
<b>OVERFIT</b> = đổi sang giá trị an toàn &nbsp;|&nbsp;
<b>INSENSITIVE</b> = không cần tối ưu<br>
Bấm <b>📂 Mở báo cáo</b> để xem bảng chi tiết từng giá trị × từng giai đoạn.
</p>
</body></html>"""

    def _build_equity_curve_html(self, equity_curve: list) -> str:
        import json as _json
        data_json = _json.dumps(equity_curve, ensure_ascii=False)
        is_light = "true" if self._is_light_theme() else "false"
        return """<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { width: 100%; height: 100%; background: transparent; overflow: hidden; font-family: Arial, sans-serif; }
#chart-container { width: 100%; height: 100%; }
#empty-state { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: #6b7280; font-size: 14px; display: none; z-index: 5; pointer-events: none; text-align: center; }
#error-state { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: #e11d48; font-size: 14px; display: none; z-index: 5; pointer-events: none; text-align: center; }
</style>
</head>
<body>
<div id="chart-container"></div>
<div id="empty-state">Không đủ dữ liệu để vẽ biểu đồ</div>
<div id="error-state"></div>
<script src="lightweight-charts.standalone.production.js"></script>
<script>
(function() {
  var DATA = __EQUITY_DATA__;
  if (!DATA || DATA.length < 2) {
    document.getElementById('empty-state').style.display = 'block';
    return;
  }
  try {
    if (typeof LightweightCharts === 'undefined') {
      throw new Error('Thu vien LightweightCharts khong load duoc.');
    }
    var isLight = __IS_LIGHT__;
    var bg = isLight ? '#ffffff' : '#101214';
    var textColor = isLight ? '#111827' : '#f3f4f6';
    var gridColor = isLight ? '#f3f4f6' : '#1e2227';
    var borderColor = isLight ? '#e5e7eb' : '#2d3238';
    var container = document.getElementById('chart-container');
    var w = container.clientWidth || container.offsetWidth || 800;
    var h = container.clientHeight || container.offsetHeight || 400;
    if (w < 10) w = 800;
    if (h < 10) h = 400;
    var chart = LightweightCharts.createChart(container, {
      width: w,
      height: h,
      layout: { background: { type: 'solid', color: bg }, textColor: textColor },
      grid: { vertLines: { color: gridColor }, horzLines: { color: gridColor } },
      rightPriceScale: { borderColor: borderColor },
      timeScale: { borderColor: borderColor, timeVisible: true },
      crosshair: { mode: 0 },
      autoSize: true,
    });
    var cumData = [];
    var ddData = [];
    for (var i = 0; i < DATA.length; i++) {
      var d = DATA[i];
      var t = d.time;
      if (typeof t === 'string') {
        t = Math.floor(new Date(t).getTime() / 1000);
        if (isNaN(t)) t = d.time;
      }
      cumData.push({ time: t, value: d.cumulative_r });
      ddData.push({ time: t, value: d.drawdown_r });
    }
    var cumSeries = chart.addSeries(LightweightCharts.LineSeries, {
      color: '#2196F3',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
    });
    cumSeries.setData(cumData);
    var ddSeries = chart.addSeries(LightweightCharts.AreaSeries, {
      lineColor: 'rgba(244, 67, 54, 0.6)',
      topColor: 'rgba(244, 67, 54, 0.10)',
      bottomColor: 'rgba(244, 67, 54, 0.22)',
      priceLineVisible: false,
      lastValueVisible: false,
    });
    ddSeries.setData(ddData);
    chart.timeScale().fitContent();
    if (window.ResizeObserver) {
      new ResizeObserver(function() {
        var cw = container.clientWidth || container.offsetWidth || w;
        var ch = container.clientHeight || container.offsetHeight || h;
        if (cw > 0 && ch > 0) chart.resize(cw, ch);
      }).observe(container);
    }
  } catch(e) {
    var err = document.getElementById('error-state');
    err.textContent = 'Loi bieu do: ' + (e && e.message ? e.message : e);
    err.style.display = 'block';
  }
})();
</script>
</body>
</html>""".replace("__EQUITY_DATA__", data_json).replace("__IS_LIGHT__", is_light)

    def _refresh_equity_curve(self) -> None:
        if not hasattr(self, '_equity_canvas') or self._equity_canvas is None:
            return
        if not self.result:
            self._equity_figure.clear()
            self._equity_canvas.draw()
            return
        equity_curve = self.result.get("equity_curve", [])
        if not isinstance(equity_curve, list):
            equity_curve = []
        self._equity_figure.clear()
        ax = self._equity_figure.add_subplot(111)
        light = self._is_light_theme()
        bg = '#ffffff' if light else '#101214'
        fg = '#111827' if light else '#f3f4f6'
        grid_c = '#e5e7eb' if light else '#1e2227'
        self._equity_figure.set_facecolor(bg)
        ax.set_facecolor(bg)
        if len(equity_curve) < 2:
            ax.text(0.5, 0.5, 'Không đủ dữ liệu để vẽ biểu đồ',
                    transform=ax.transAxes, ha='center', va='center',
                    color='#6b7280', fontsize=12)
            ax.set_xticks([])
            ax.set_yticks([])
        else:
            from datetime import datetime
            times = []
            cum_r = []
            dd_r = []
            for d in equity_curve:
                t = d.get("time", "")
                try:
                    times.append(datetime.fromisoformat(t.replace("Z", "+00:00")))
                except (ValueError, TypeError):
                    times.append(t)
                cum_r.append(d.get("cumulative_r", 0))
                dd_r.append(d.get("drawdown_r", 0))
            ax.plot(times, cum_r, color='#2196F3', linewidth=2, label='Cumulative R')
            ax.fill_between(times, [0] * len(dd_r), dd_r,
                            color='#F44336', alpha=0.2, label='Drawdown R')
            ax.axhline(y=0, color=grid_c, linewidth=0.5)
            ax.legend(loc='upper left', fontsize=9)
        ax.tick_params(colors=fg, labelsize=9)
        for spine in ax.spines.values():
            spine.set_color(grid_c)
        ax.set_ylabel('R', color=fg)
        ax.grid(True, color=grid_c, linewidth=0.5, alpha=0.5)
        self._equity_figure.autofmt_xdate()
        self._equity_canvas.draw()

    def set_equity_chart_visible(self, visible: bool) -> None:
        pass

    def _refresh_result_text(self) -> None:
        if not self.result:
            self.result_text.setHtml("")
            return
        self._analysis_light = self._is_light_theme()
        self._refresh_result_text_style()
        try:
            html = self._generate_stats_html()
            self.result_text.setHtml(html)
        except Exception:
            self.result_text.setHtml("<p style='color:#888;text-align:center;padding:40px;'>Không thể hiển thị kết quả.</p>")

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
            self._update_verdict()
            self.apply_config_btn.show()
            self.status_label.setText(f"Đã tải: {len(trades)} lệnh")
            self.snapshot_label.setText(f"File: {path}")
            self.snapshot_label.show()
            self._refresh_result_text()
            self._refresh_equity_curve()
        except Exception as exc:
            QMessageBox.warning(self, "Lỗi đọc file", f"Không đọc được file:\n{exc}")

    def _analyze_loaded_result(self) -> None:
        if not self.result:
            QMessageBox.information(self, "Phân tích", "Chưa có dữ liệu backtest. Hãy chạy backtest hoặc tải file trước.")
            return
        from services.ai_service import AIService, AIProviderConfig

        settings = (
            self.app.settings_service.load()
            if self.app
            else self.controller.settings_service.load()
        )
        active = settings.ai.active_provider()
        if not active or not active.api_key:
            QMessageBox.warning(self, "Phân tích", "Chưa cấu hình AI. Vào Cài đặt để chọn nhà cung cấp và nhập API key.")
            return

        try:
            self._analysis_light = (settings.display.theme == "light")
        except Exception:
            self._analysis_light = False

        self.analyze_btn.setText("⏳ Đang phân tích...")
        self.analyze_btn.setEnabled(False)

        prompt = self._build_analysis_prompt()
        config = AIProviderConfig(provider=active.provider, model=active.model, api_key=active.api_key)
        ai = self.app.create_ai_service(config) if self.app else AIService(config)

        self._ai_thread = QThread()
        self._ai_worker = _AIAnalyzeWorker(ai, prompt)
        self._ai_worker.moveToThread(self._ai_thread)
        self._ai_thread.started.connect(self._ai_worker.run)
        self._ai_worker.finished.connect(self._on_ai_analysis_done)
        self._ai_worker.error.connect(self._on_ai_analysis_error)
        self._ai_thread.finished.connect(self._ai_thread.deleteLater)
        self._ai_thread.finished.connect(self._ai_worker.deleteLater)
        self._ai_thread.start()

    def _on_ai_analysis_done(self, response: str) -> None:
        if not response or not response.strip():
            QMessageBox.warning(self, "Phân tích", "AI không trả về nội dung phân tích. Vui lòng thử lại.")
            self.analyze_btn.setText("🤖 Phân tích")
            self.analyze_btn.setEnabled(True)
            self._ai_thread.quit()
            self._ai_thread.wait()
            return

        try:
            light = getattr(self, '_analysis_light', False)

            dlg = QDialog(self)
            dlg.setWindowTitle("Phân tích kết quả backtest")
            dlg.setMinimumSize(800, 600)
            if light:
                dlg.setStyleSheet("QDialog { background: #FAF9F5; }")
            else:
                dlg.setStyleSheet("QDialog { background: #1a1f2e; }")
            layout = QVBoxLayout(dlg)
            layout.setContentsMargins(16, 14, 16, 12)
            layout.setSpacing(0)

            text = QTextEdit()
            text.setReadOnly(True)
            if light:
                text.setStyleSheet(
                    "QTextEdit { background: #ffffff; color: #1e293b; font-size: 13px; "
                    "border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 16px; }"
                    "QScrollBar:vertical { width: 8px; background: transparent; }"
                )
            else:
                text.setStyleSheet(
                    "QTextEdit { background: #0f172a; color: #e2e8f0; font-size: 13px; "
                    "border: 1px solid #1e293b; border-radius: 8px; padding: 14px 16px; }"
                    "QScrollBar:vertical { width: 8px; background: transparent; }"
                )

            stats_html = self._generate_stats_html()
            ai_html = self._format_ai_to_html(response, light)

            hr_color = "#cbd5e1" if light else "#334155"
            header_color = "#c2410c" if light else "#f59e0b"
            final_html = (
                f"{stats_html}"
                f"<div style='margin:20px 0;border-top:1px dashed {hr_color};'></div>"
                f"<h2 style='color:{header_color};margin:0 0 10px 0;font-size:15px;'>AI Nhận xét & Khuyến nghị</h2>"
                f"{ai_html}"
            )

            text.setHtml(final_html)
            layout.addWidget(text, 1)
            layout.addSpacing(8)

            close_btn = action_button("Đóng")
            close_btn.clicked.connect(dlg.accept)
            btn_row = QHBoxLayout()
            btn_row.setContentsMargins(0, 0, 0, 0)
            btn_row.addStretch()
            btn_row.addWidget(close_btn)
            layout.addLayout(btn_row)
            dlg.exec()
        finally:
            self.analyze_btn.setText("🤖 Phân tích")
            self.analyze_btn.setEnabled(True)
            self._ai_thread.quit()
            self._ai_thread.wait()

    def _on_ai_analysis_error(self, error_msg: str) -> None:
        if len(error_msg) > 500:
            error_msg = error_msg[:500] + "..."
        QMessageBox.warning(self, "Lỗi phân tích", error_msg)
        self.analyze_btn.setText("🤖 Phân tích")
        self.analyze_btn.setEnabled(True)
        self._ai_thread.quit()
        self._ai_thread.wait()

    def _apply_scanner_config(self) -> None:
        """Show current vs recommended scanner config with checkboxes to apply."""
        if not self.result:
            QMessageBox.information(self, "Đề xuất", "Chưa có dữ liệu backtest. Hãy chạy backtest hoặc tải file trước.")
            return

        from core.backtest_to_scanner_config import recommend_scanner_configs

        try:
            recs = recommend_scanner_configs(self.result)
        except Exception as exc:
            QMessageBox.warning(self, "Lỗi phân tích", f"Không thể phân tích backtest:\n{exc}")
            return

        try:
            settings = (
                self.app.settings_service.load()
                if self.app else self.controller.settings_service.load()
            )
        except Exception as exc:
            QMessageBox.warning(self, "Lỗi", f"Không đọc được Settings:\n{exc}")
            return

        try:
            light = (self.app.settings_service.load().display.theme == "light"
                     if self.app else self.controller.settings_service.load().display.theme == "light")
        except Exception:
            light = False

        if light:
            text_color = "#1c1917"
            muted_color = "#78716c"
            border_color = "#e7e5e4"
            title_color = "#c2410c"
            current_color = "#57534e"
            proposed_color = "#ea580c"
            evidence_color = "#78716c"
            bg_color = "#faf8f5"
        else:
            text_color = "#ebdcd0"
            muted_color = "#a8a29e"
            border_color = "#3f2c25"
            title_color = "#f97316"
            current_color = "#d6d3d1"
            proposed_color = "#fb923c"
            evidence_color = "#a8a29e"
            bg_color = "#17120f"

        dlg = QDialog(self)
        dlg.setWindowTitle("Áp dụng cấu hình Scanner từ Backtest")
        dlg.setMinimumSize(820, 260)
        dlg.setStyleSheet(f"QDialog {{ background: {bg_color}; }}")
        
        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.setContentsMargins(24, 20, 24, 20)
        dlg_layout.setSpacing(16)

        title_widget = QLabel("")
        title_widget.setTextFormat(Qt.TextFormat.RichText)
        title_widget.setText(
            f"<h2 style='color:{title_color};margin:0 0 6px;font-size:18px;'>"
            f"Cấu hình Scanner cho {self.selected_symbol}</h2>"
            f"<p style='color:{muted_color};font-size:12px;margin:0;'>"
            "So sánh cấu hình hiện tại trong Settings với đề xuất từ kết quả backtest."
            "</p>"
        )
        dlg_layout.addWidget(title_widget)

        symbol = self.selected_symbol
        existing = settings.trading.symbol_settings.get(symbol)
        cfg = recs.get(symbol)

        if cfg is None:
            no_data = QLabel(
                f"<span style='color:{muted_color};font-size:13px;'>"
                f"{symbol}: không đủ dữ liệu để đề xuất "
                f"(cần ≥10 lệnh, kỳ vọng &gt;+0.10R, PF &gt;1.2)</span>"
            )
            no_data.setTextFormat(Qt.TextFormat.RichText)
            dlg_layout.addWidget(no_data)
        else:
            evidence = cfg.get("_evidence", "")
            current_regime = existing.auto_trade_regime if existing else "--"
            current_side = existing.auto_trade_side if existing else "--"
            current_score = str(existing.min_score) if existing else "--"
            current_rr = f"{existing.min_expected_rr:.1f}" if existing else "--"

            table = QTableWidget(3, 2)
            table.setObjectName("LuuTrungHoaTable")
            table.verticalHeader().setVisible(False)
            table.horizontalHeader().setVisible(False)
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
            table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            table.setShowGrid(False)
            table.setWordWrap(True)
            table.setMinimumHeight(140)
            
            table.setStyleSheet(
                f"QTableWidget#LuuTrungHoaTable {{"
                f"  background: transparent;"
                f"  border: 1px solid {border_color};"
                f"  border-radius: 8px;"
                f"  outline: none;"
                f"}}"
                f"QTableWidget#LuuTrungHoaTable::item {{"
                f"  border-bottom: 1px solid {border_color};"
                f"  padding: 12px 16px;"
                f"}}"
            )

            rows = [
                ("Cấu hình hiện tại",
                 f"<span style='color:{current_color}; font-size: 13px;'>"
                 f"<b>Regime:</b> {current_regime} &nbsp;&nbsp;&nbsp; "
                 f"<b>Side:</b> {current_side} &nbsp;&nbsp;&nbsp; "
                 f"<b>MinScore:</b> {current_score} &nbsp;&nbsp;&nbsp; "
                 f"<b>MinRR:</b> {current_rr}</span>"),
                 
                ("Đề xuất từ backtest",
                 f"<span style='color:{proposed_color}; font-size: 14px;'>"
                 f"<b>Regime:</b> {cfg['regime']} &nbsp;&nbsp;&nbsp; "
                 f"<b>Side:</b> {cfg['side'].upper()} &nbsp;&nbsp;&nbsp; "
                 f"<b>MinScore:</b> {cfg['min_score']} &nbsp;&nbsp;&nbsp; "
                 f"<b>MinRR:</b> {cfg['min_rr']}</span>"),
                 
                ("Bằng chứng", 
                 f"<span style='color:{evidence_color}; font-size: 12px; font-style: italic; line-height: 1.4;'>"
                 f"{evidence}</span>"),
            ]
            
            for row_idx, (label, html_value) in enumerate(rows):
                lbl_title = QLabel(label)
                lbl_title.setStyleSheet(f"color: {text_color}; font-weight: bold; font-size: 13px; padding-left: 8px;")
                table.setCellWidget(row_idx, 0, lbl_title)
                
                lbl_val = QLabel(html_value)
                lbl_val.setTextFormat(Qt.TextFormat.RichText)
                lbl_val.setWordWrap(True)
                lbl_val.setStyleSheet("padding-right: 8px; background: transparent;")
                table.setCellWidget(row_idx, 1, lbl_val)
                
                table.setRowHeight(row_idx, 48)

            table.resizeRowsToContents()

            header = table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(0, 180)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

            dlg_layout.addWidget(table, 1)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 8, 0, 0)
        apply_btn = action_button("🔥 Áp dụng cấu hình", primary=True)
        apply_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {proposed_color};"
            f"  color: white;"
            f"  border: none;"
            f"  border-radius: 6px;"
            f"  font-weight: bold;"
            f"  padding: 4px 16px;"
            f"  min-height: 26px;"
            f"  max-height: 26px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {title_color};"
            f"}}"
        )
        apply_btn.setEnabled(cfg is not None)
        apply_btn.clicked.connect(lambda: self._do_apply_config_direct(cfg, dlg))
        
        cancel_btn = action_button("Hủy")
        cancel_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: transparent;"
            f"  color: {muted_color};"
            f"  border: 1px solid {border_color};"
            f"  border-radius: 6px;"
            f"  padding: 4px 16px;"
            f"  min-height: 26px;"
            f"  max-height: 26px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: rgba(120, 113, 108, 0.1);"
            f"  color: {text_color};"
            f"}}"
        )
        cancel_btn.clicked.connect(dlg.reject)
        
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(apply_btn)
        dlg_layout.addLayout(btn_row)
        dlg.exec()

    def _do_apply_config_direct(self, cfg: dict | None, dlg: QDialog) -> None:
        """Apply recommendation directly (single symbol, no checkbox)."""
        if cfg is None:
            return
        try:
            settings = (
                self.app.settings_service.load()
                if self.app else self.controller.settings_service.load()
            )

            symbol = self.selected_symbol
            sym_settings = settings.trading.symbol_settings.get(symbol)
            if sym_settings is None:
                from config.settings import SymbolScanSettings
                sym_settings = SymbolScanSettings()
                settings.trading.symbol_settings[symbol] = sym_settings

            sym_settings.backtest = True
            sym_settings.auto_trade_regime = cfg["regime"]
            sym_settings.auto_trade_side = cfg["side"]
            sym_settings.min_score = int(cfg["min_score"])
            sym_settings.min_expected_rr = float(cfg["min_rr"])

            if symbol not in settings.trading.enabled_symbols:
                settings.trading.enabled_symbols.append(symbol)

            if self.app:
                self.app.settings_service.save(settings)
            else:
                self.controller.settings_service.save(settings)

            dlg.accept()
            QMessageBox.information(
                self, "Đã áp dụng",
                f"Đã cập nhật cấu hình Scanner cho {symbol}.\n\n"
                f"Regime: {cfg['regime']}    Side: {cfg['side'].upper()}\n"
                f"MinScore: {cfg['min_score']}    MinRR: {cfg['min_rr']}\n\n"
                "Lần quét tiếp theo sẽ dùng cấu hình mới."
            )
        except Exception as exc:
            QMessageBox.warning(self, "Lỗi áp dụng", f"Không thể lưu cấu hình:\n{exc}")

    def _do_apply_config(self, recs: dict, checkboxes: dict, dlg: QDialog) -> None:
        """Apply checked recommendations to settings."""
        configs = {}
        for symbol, cb in checkboxes.items():
            if not cb.isChecked():
                continue
            cfg = recs.get(symbol)
            if cfg is None:
                continue
            configs[symbol] = {
                "regime": cfg["regime"],
                "side": cfg["side"],
                "min_score": cfg["min_score"],
                "min_rr": cfg["min_rr"],
            }

        if not configs:
            QMessageBox.information(self, "Áp dụng", "Không có đề xuất nào được chọn để áp dụng.")
            return

        try:
            settings = (
                self.app.settings_service.load()
                if self.app else self.controller.settings_service.load()
            )
        except Exception as exc:
            QMessageBox.warning(self, "Lỗi", f"Không đọc được Settings:\n{exc}")
            return

        updated = 0
        for symbol, cfg in configs.items():
            sym_settings = settings.trading.symbol_settings.get(symbol)
            if sym_settings is None:
                from config.settings import SymbolScanSettings
                sym_settings = SymbolScanSettings()
                settings.trading.symbol_settings[symbol] = sym_settings

            sym_settings.backtest = True
            sym_settings.auto_trade_regime = cfg["regime"]
            sym_settings.auto_trade_side = cfg["side"]
            sym_settings.min_score = int(cfg["min_score"])
            sym_settings.min_expected_rr = float(cfg["min_rr"])
            updated += 1

            if symbol not in settings.trading.enabled_symbols:
                settings.trading.enabled_symbols.append(symbol)

        try:
            if self.app:
                self.app.settings_service.save(settings)
            else:
                self.controller.settings_service.save(settings)
        except Exception as exc:
            QMessageBox.warning(self, "Lỗi", f"Không lưu được Settings:\n{exc}")
            return

        dlg.accept()
        QMessageBox.information(
            self, "Đã áp dụng",
            f"Đã cập nhật cấu hình Scanner cho {updated} mã.\n\n"
            "Lần quét tiếp theo sẽ dùng cấu hình mới."
        )

    def _build_analysis_prompt(self) -> str:
        summary = self.result.get("summary", {}) if isinstance(self.result.get("summary"), dict) else {}
        breakdowns = self.result.get("breakdowns", {}) if isinstance(self.result.get("breakdowns"), dict) else {}
        diagnostics = self.result.get("diagnostics", {}) if isinstance(self.result.get("diagnostics"), dict) else {}
        request_info = self.result.get("request", {}) if isinstance(self.result.get("request"), dict) else {}
        symbol = request_info.get("symbol", "") or request_info.get("symbols", "")
        start = request_info.get("start", "")
        end = request_info.get("end", "")

        if not (summary.get("total_trades", 0) or 0):
            return (
                f"=== BÁO CÁO PHÂN TÍCH BACKTEST ===\n\n"
                f"Mã: {symbol or 'Không xác định'} | Khoảng thời gian: {start[:10] if start else '?'} → {end[:10] if end else '?'}\n\n"
                f"KẾT QUẢ: 0 lệnh được mở trong suốt khoảng thời gian backtest.\n\n"
                f"===\n\n"
                f"QUY ĐỊNH: TẤT CẢ nội dung PHẢI bằng TIẾNG VIỆT CÓ DẤU. TUYỆT ĐỐI KHÔNG dùng tiếng Anh. KHÔNG dùng ký tự đặc biệt (*, #, _, `).\n\n"
                f"Dựa trên thông tin trên, hãy phân tích:\n"
                f"1. Tại sao không có lệnh nào được mở? Có thể do điều kiện thị trường, tham số scanner quá chặt, "
                f"hay thiếu dữ liệu?\n"
                f"2. Nếu là do cấu hình, đề xuất thay đổi tham số nào để hệ thống có thể tìm thấy cơ hội giao dịch?\n"
            )

        def fmt_stats(s, prefix=""):
            if not isinstance(s, dict):
                return "N/A"
            return (
                f"{prefix}{s.get('total_trades', 0) or 0} lệnh, "
                f"thắng {s.get('win_rate', 0) or 0:.1f}%, "
                f"kỳ vọng {s.get('expectancy_r', 0) or 0:+.2f}R, "
                f"PF {s.get('profit_factor', 0) or 0:.2f}, "
                f"DD {s.get('max_drawdown_r', 0) or 0:.1f}R, "
                f"tổng {s.get('total_r', 0) or 0:+.1f}R"
            )

        lines = [
            "=== BÁO CÁO PHÂN TÍCH BACKTEST ===",
            "",
            f"Mã: {symbol or 'Không xác định'} | Khoảng thời gian: {start[:10] if start else '?'} → {end[:10] if end else '?'}",
            "",
            "TỔNG QUAN:",
            f"  {fmt_stats(summary)}",
            f"  Thắng: {summary.get('wins', 0)} | Thua: {summary.get('losses', 0)} | "
            f"Hết hạn: {summary.get('expired', 0)} | Hòa: {summary.get('breakeven', 0)}",
            f"  Chuỗi thắng tối đa: {summary.get('max_consecutive_wins', 0)} | "
            f"Chuỗi thua tối đa: {summary.get('max_consecutive_losses', 0)}",
            f"  Trung bình R thắng: {summary.get('average_win_r', 0):+.2f}R | "
            f"Trung bình R thua: {summary.get('average_loss_r', 0):+.2f}R",
            f"  Số nến giữ lệnh TB: {summary.get('average_holding_bars', 0):.0f} nến",
        ]

        # ---- By Regime ----
        by_regime = breakdowns.get("by_market_regime", {})
        if by_regime:
            lines.append("")
            lines.append("PHÂN TÍCH THEO REGIME:")
            for regime in sorted(by_regime, key=lambda r: by_regime[r].get('profit_factor', 0), reverse=True):
                lines.append(f"  [{regime}] {fmt_stats(by_regime[regime])}")

        # ---- By Side ----
        by_side = breakdowns.get("by_side", {})
        if by_side:
            lines.append("")
            lines.append("PHÂN TÍCH THEO HƯỚNG (BUY/SELL):")
            for side in sorted(by_side, key=lambda s: by_side[s].get('profit_factor', 0), reverse=True):
                lines.append(f"  [{side}] {fmt_stats(by_side[side])}")

        # ---- By Decision ----
        by_decision = breakdowns.get("by_decision", {})
        if by_decision:
            lines.append("")
            lines.append("PHÂN TÍCH THEO LOẠI QUYẾT ĐỊNH:")
            for dec in sorted(by_decision, key=lambda d: by_decision[d].get('profit_factor', 0), reverse=True):
                lines.append(f"  [{dec}] {fmt_stats(by_decision[dec])}")

        # ---- By Score Bucket ----
        by_score = breakdowns.get("by_final_score_bucket", {})
        if by_score:
            lines.append("")
            lines.append("PHÂN TÍCH THEO ĐIỂM SỐ (FINAL SCORE):")
            for bucket in sorted(by_score):
                lines.append(f"  [Score {bucket}] {fmt_stats(by_score[bucket])}")

        # ---- By Entry Zone Score ----
        by_entry_zone = breakdowns.get("by_entry_zone_score", {})
        if by_entry_zone:
            lines.append("")
            lines.append("PHÂN TÍCH THEO ĐIỂM ENTRY ZONE:")
            for bucket in sorted(by_entry_zone):
                lines.append(f"  [EntryZone {bucket}] {fmt_stats(by_entry_zone[bucket])}")

        # ---- By RR bucket ----
        by_rr = breakdowns.get("by_expected_effective_rr", {})
        if by_rr:
            lines.append("")
            lines.append("PHÂN TÍCH THEO RR KỲ VỌNG:")
            for bucket in sorted(by_rr):
                lines.append(f"  [RR {bucket}] {fmt_stats(by_rr[bucket])}")

        # ---- By SMC Zone Score ----
        by_smc = breakdowns.get("by_smc_zone_score", {})
        if by_smc:
            lines.append("")
            lines.append("PHÂN TÍCH THEO CHẤT LƯỢNG VÙNG SMC:")
            for bucket in sorted(by_smc):
                lines.append(f"  [SMC {bucket}] {fmt_stats(by_smc[bucket])}")

        # ---- Best combinations (top 5 by profit factor) ----
        lines.append("")
        lines.append("CÁC TỔ HỢP TỐT NHẤT (theo Profit Factor, có ít nhất 5 lệnh):")
        combos = []
        for dim_name, dim_data in [
            ("Regime", by_regime), ("Hướng", by_side), ("Điểm số", by_score),
            ("RR", by_rr), ("SMC Zone", by_smc),
        ]:
            for key, stats in dim_data.items():
                if isinstance(stats, dict) and stats.get('total_trades', 0) >= 5:
                    combos.append((dim_name, key, stats))
        combos.sort(key=lambda x: x[2].get('profit_factor', 0), reverse=True)
        for dim, key, stats in combos[:10]:
            lines.append(f"  {dim}={key}: {fmt_stats(stats)}")

        # ---- Funnel diagnostics ----
        funnel = diagnostics.get("gate_funnel", {})
        if funnel:
            lines.append("")
            lines.append("CHẨN ĐOÁN PHỄU GIAO DỊCH:")
            lines.append(f"  Snapshots: {funnel.get('snapshots_evaluated', 0)}")
            lines.append(f"  Setup phát hiện: {funnel.get('setup_detected', 0)} "
                         f"(fallback: {funnel.get('fallback_scenario', 0)})")
            lines.append(f"  Lệnh mở: {funnel.get('trade_opened', 0)}")
            blocked = []
            for k, v in funnel.items():
                if k.startswith("blocked_") and v > 0:
                    blocked.append(f"{k}={v}")
            if blocked:
                lines.append(f"  Bị chặn: {', '.join(blocked)}")
            other_skip = []
            for k in ("no_trade_scenario", "entry_zone_not_touched", "invalid_trade_plan"):
                v = funnel.get(k, 0)
                if v > 0:
                    other_skip.append(f"{k}={v}")
            if other_skip:
                lines.append(f"  Khác: {', '.join(other_skip)}")

        lines.append("")
        lines.append("===")
        lines.append("")
        lines.append("QUY ĐỊNH BẮT BUỘC VỀ NGÔN NGỮ VÀ ĐỊNH DẠNG:")
        lines.append("- TẤT CẢ nội dung trả lời PHẢI viết bằng TIẾNG VIỆT CÓ DẤU, không được dùng tiếng Anh dù chỉ một từ.")
        lines.append("- TUYỆT ĐỐI KHÔNG dùng bất kỳ ký tự đặc biệt nào: không dấu sao (*), không dấu thăng (#), không dấu gạch dưới (_), không dấu nháy ngược (`), không dấu gạch ngang kép (--).")
        lines.append("- Không viết tắt, không dùng từ tiếng Anh, không dùng thuật ngữ không phổ biến.")
        lines.append("- Mỗi ý bắt đầu bằng dấu gạch ngang (-) và theo sau là một khoảng trắng.")
        lines.append("- Mỗi ý là MỘT câu hoàn chỉnh bằng tiếng Việt, có số liệu cụ thể để dẫn chứng.")
        lines.append("- Trước mỗi phần/phân đoạn, viết tiêu đề IN HOA trên một dòng riêng, kết thúc bằng dấu hai chấm (:).")
        lines.append("")
        lines.append("Dựa trên số liệu đã cung cấp, hãy phân tích theo ĐÚNG trình tự các phần sau:")
        lines.append("")
        lines.append("PHẦN 1 - TỔNG QUAN KẾT QUẢ BACKTEST:")
        lines.append("- Nhận xét tổng quan: có bao nhiêu lệnh, tỉ lệ thắng, kỳ vọng, tổng R, hệ số lợi nhuận.")
        lines.append("- Đánh giá sơ bộ: hệ thống có lợi thế thống kê hay không, bằng chứng cụ thể.")
        lines.append("")
        if by_score:
            lines.append("PHẦN 2 - PHÂN TÍCH CHI TIẾT THEO TỪNG KHOẢNG ĐIỂM (FINAL SCORE):")
            lines.append("- Với MỖI khoảng điểm trong dữ liệu, ghi rõ: khoảng điểm đó có bao nhiêu lệnh, trong đó bao nhiêu lệnh thắng, bao nhiêu lệnh thua, bao nhiêu lệnh hòa, bao nhiêu lệnh hết hạn.")
            lines.append("- Với MỖI khoảng điểm, ghi rõ: tổng lãi được bao nhiêu R, kỳ vọng trung bình bao nhiêu R mỗi lệnh, hệ số lợi nhuận là bao nhiêu.")
            lines.append("- So sánh các khoảng điểm với nhau: khoảng điểm nào cho kết quả tốt nhất, khoảng nào tệ nhất.")
            lines.append("- Trả lời: điểm số càng cao có thực sự cho kết quả càng tốt không? Nếu không, đâu là khoảng điểm tối ưu?")
            lines.append("")
        if by_side:
            lines.append("PHẦN 3 - PHÂN TÍCH CHI TIẾT THEO HƯỚNG GIAO DỊCH (BUY và SELL):")
            lines.append("- Hướng BUY: tổng bao nhiêu lệnh, thắng bao nhiêu, thua bao nhiêu, tổng lãi bao nhiêu R, kỳ vọng bao nhiêu R mỗi lệnh, hệ số lợi nhuận bao nhiêu.")
            lines.append("- Hướng SELL: tổng bao nhiêu lệnh, thắng bao nhiêu, thua bao nhiêu, tổng lãi bao nhiêu R, kỳ vọng bao nhiêu R mỗi lệnh, hệ số lợi nhuận bao nhiêu.")
            lines.append("- So sánh: hướng nào có lợi thế rõ rệt hơn? Chênh lệch cụ thể về tổng R và kỳ vọng giữa hai hướng.")
            lines.append("- Khuyến nghị: có nên chỉ giao dịch một hướng hay giao dịch cả hai?")
            lines.append("")
        if by_regime:
            lines.append("PHẦN 4 - PHÂN TÍCH THEO REGIME THỊ TRƯỜNG:")
            lines.append("- Với MỖI regime, ghi rõ số lệnh, tỉ lệ thắng, kỳ vọng R, tổng R, hệ số lợi nhuận.")
            lines.append("- Regime nào cho kết quả tốt nhất, regime nào tệ nhất?")
            lines.append("- Có nên lọc theo regime không? Nếu có thì chọn regime nào?")
            lines.append("")
        if by_rr:
            lines.append("PHẦN 5 - PHÂN TÍCH THEO NGƯỠNG RR KỲ VỌNG:")
            lines.append("- Với MỖI khoảng RR, ghi rõ số lệnh, tỉ lệ thắng, kỳ vọng, tổng R.")
            lines.append("- Ngưỡng RR tối ưu là bao nhiêu? Lọc RR cao hơn có cải thiện kỳ vọng không?")
            lines.append("")
        lines.append("PHẦN 6 - ĐÁNH GIÁ RỦI RO:")
        lines.append("- Mức sụt giảm tối đa là bao nhiêu R, có ở mức chấp nhận được không?")
        lines.append("- Chuỗi thua liên tiếp tối đa là bao nhiêu lệnh? Chuỗi thắng liên tiếp tối đa?")
        lines.append("- Tỉ lệ lệnh hết hạn có cao bất thường không? Có điểm gì bất thường khác trong dữ liệu không?")
        lines.append("")
        lines.append("PHẦN 7 - KHUYẾN NGHỊ CỤ THỂ CHO GIAO DỊCH THỰC TẾ:")
        lines.append("- Đề xuất bộ tham số tối ưu: chọn regime nào, hướng nào (BUY hay SELL hay cả hai), điểm tối thiểu (min_score) là bao nhiêu, RR tối thiểu (min_rr) là bao nhiêu.")
        lines.append("- Giải thích lý do cho từng lựa chọn, dựa trên số liệu cụ thể từ các phần phân tích trên.")
        lines.append("- Ước tính: nếu áp dụng bộ tham số đề xuất, kỳ vọng sẽ được bao nhiêu R mỗi lệnh, tỉ lệ thắng khoảng bao nhiêu phần trăm.")
        lines.append("- Cảnh báo: những rủi ro nào cần lưu ý khi giao dịch thực tế với bộ tham số này?")
        return "\n".join(lines)

    def _generate_stats_html(self) -> str:
        if not self.result:
            return ""
        summary = self.result.get("summary", {}) if isinstance(self.result.get("summary"), dict) else {}

        light = getattr(self, '_analysis_light', False)

        if light:
            text_color = "#111827"
            value_color = "#111827"
            muted_color = "#57534E"
            border_color = "#cbd5e1"
            row_border = "#e2e8f0"
            card_bg = "#f1f5f9"
            card_title = "#0f172a"
            panel_title_color = "#c2410c"
            pipeline_title_color = "#c2410c"
            details_title_color = "#b45309"
        else:
            text_color = "#e2e8f0"
            value_color = "#f8fafc"
            muted_color = "#94a3b8"
            border_color = "#334155"
            row_border = "#1e293b"
            card_bg = "#1e293b"
            card_title = "#f8fafc"
            panel_title_color = "#ea580c"
            pipeline_title_color = "#f97316"
            details_title_color = "#f59e0b"

        def get_stat(d, k, fallback="--"):
            val = d.get(k)
            if val is None: return fallback
            try:
                if float(str(val)) == int(float(str(val))):
                    return f"{int(float(str(val))):,}"
                return f"{float(str(val)):,.2f}"
            except (TypeError, ValueError):
                return str(val)

        def eval_winrate(wr_val):
            if wr_val >= 55: return "<span style='color:#10b981;font-weight:bold;'>🔥 Tuyệt vời</span>"
            if wr_val >= 45: return "<span style='color:#ea580c;font-weight:bold;'>✅ Tốt</span>"
            if wr_val >= 35: return "<span style='color:#f59e0b;'>⚠️ Đạt</span>"
            return "<span style='color:#e11d48;font-weight:bold;'>❌ Thấp</span>"

        def eval_profit_factor(pf_val):
            if pf_val >= 1.6: return "<span style='color:#10b981;font-weight:bold;'>🔥 Rất cao</span>"
            if pf_val >= 1.2: return "<span style='color:#ea580c;font-weight:bold;'>✅ Khá</span>"
            if pf_val >= 1.0: return "<span style='color:#f59e0b;'>⚠️ Hòa vốn</span>"
            return "<span style='color:#e11d48;font-weight:bold;'>❌ Lỗ</span>"

        def eval_drawdown(dd_val):
            val = -abs(dd_val)
            if val > -10: return "<span style='color:#10b981;font-weight:bold;'>🛡️ An toàn</span>"
            if val > -20: return "<span style='color:#f59e0b;'>⚠️ Cần theo dõi</span>"
            return "<span style='color:#e11d48;font-weight:bold;'>🆘 Nguy hiểm</span>"

        html = [
            "<div style='font-family:-apple-system,Segoe UI,sans-serif;'>",
            f"<h2 style='color:{panel_title_color}; margin-top: 0; margin-bottom: 12px; font-size: 12px;'>📊 BẢNG KẾT QUẢ TỔNG HỢP</h2>",
        ]
        
        html.extend(self._build_stats_overview_html(
            summary,
            text_color, value_color, muted_color, border_color, row_border,
            get_stat, eval_winrate, eval_profit_factor, eval_drawdown,
        ))

        symbol_stats = self.result.get("symbol_stats", {})
        if isinstance(symbol_stats, dict) and len(symbol_stats) > 1:
            html.append(f"<h2 style='color:{details_title_color}; margin-bottom: 16px; margin-top: 24px; font-size: 12px;'>🌍 CHI TIẾT TỪNG CẶP</h2>")
            html.append("<div style='display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px;'>")
            for symbol, sym_stats in sorted(symbol_stats.items()):
                if not isinstance(sym_stats, dict):
                    continue
                sym_wr = float(sym_stats.get("win_rate", 0) or 0)
                sym_pf = float(sym_stats.get("profit_factor", 0) or 0)
                
                html.append(
                    f"<div style='background-color: {card_bg}; border-radius: 8px; padding: 14px; width: calc(50% - 6px); box-sizing: border-box; border-left: 4px solid #ea580c; border: 1px solid {border_color};'>"
                    f"<div style='font-size: 11px; font-weight: bold; color: {card_title}; margin-bottom: 10px;'>✨ {symbol}</div>"
                    f"<table style='width: 100%; border-collapse: collapse; font-size: 11px;'>"
                    f"<tr>"
                    f"<td style='padding: 4px 0;'><span style='color: {muted_color};'>Lệnh:</span> <span style='color: {text_color}; font-weight: bold;'>{get_stat(sym_stats, 'total_trades', '0')}</span></td>"
                    f"<td style='padding: 4px 0;'><span style='color: {muted_color};'>Kỳ vọng:</span> <span style='color: {text_color}; font-weight: bold;'>{get_stat(sym_stats, 'expectancy_r')}R</span></td>"
                    f"</tr>"
                    f"<tr>"
                    f"<td style='padding: 4px 0;'><span style='color: {muted_color};'>Tỷ lệ thắng:</span> <span style='color: {text_color}; font-weight: bold;'>{get_stat(sym_stats, 'win_rate')}%</span> {eval_winrate(sym_wr)}</td>"
                    f"<td style='padding: 4px 0;'><span style='color: {muted_color};'>PF:</span> <span style='color: {text_color}; font-weight: bold;'>{get_stat(sym_stats, 'profit_factor')}</span> {eval_profit_factor(sym_pf)}</td>"
                    f"</tr>"
                    f"<tr>"
                    f"<td style='padding: 4px 0;'><span style='color: #10b981; font-weight: bold;'>Tổng R:</span> <span style='color: #10b981; font-weight: bold;'>{get_stat(sym_stats, 'total_r')}R</span></td>"
                    f"<td style='padding: 4px 0;'><span style='color: #e11d48; font-weight: bold;'>DD:</span> <span style='color: #e11d48; font-weight: bold;'>{get_stat(sym_stats, 'max_drawdown_r')}R</span></td>"
                    f"</tr>"
                    f"</table>"
                    f"</div>"
                )
            html.append("</div>")

        # --- Walk-Forward Analysis ---
        wf = (self.result or {}).get("walk_forward")
        if wf and isinstance(wf, dict) and wf.get("aggregate_is") is not None:
            is_agg = wf.get("aggregate_is", {})
            oos_agg = wf.get("aggregate_oos", {})
            is_exp = float(is_agg.get("expectancy_r", 0) or 0)
            oos_exp = float(oos_agg.get("expectancy_r", 0) or 0)
            ratio = float(wf.get("oos_is_expectancy_ratio", 0) or 0)
            score = float(wf.get("robustness_score", 0) or 0)
            verdict = str(wf.get("verdict", ""))
            v_color = "#10b981" if verdict == "ROBUST" else ("#f59e0b" if verdict == "SUSPECT" else "#e11d48")
            v_text = {
                "ROBUST": "ROBUST — Hệ thống ổn định qua thời gian",
                "SUSPECT": "SUSPECT — Cần kiểm tra thêm",
                "OVERFITTING": "OVERFITTING — Hệ thống có dấu hiệu overfit",
                "INCONCLUSIVE": "INCONCLUSIVE — Không đủ dữ liệu để kết luận",
            }.get(verdict, verdict)

            html.append(f"<h2 style='color:{text_color}; margin-bottom: 10px; margin-top: 6px; font-size: 12px;'>🔄 Walk-Forward Analysis</h2>")
            html.append(f"<table style='width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 11px;'>")
            row = lambda label, value, clr=None: (
                f"<tr>"
                f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>{label}</td>"
                f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {clr or text_color}; font-weight: 600;'>{value}</td>"
                f"</tr>"
            )
            html.append(row("Số window", str(wf.get("window_count", 0))))
            html.append(row("Tổng lệnh IS (In-Sample — dữ liệu học)", f"{is_agg.get('total_trades', 0)} lệnh"))
            html.append(row("Tổng lệnh OOS (Out-of-Sample — dữ liệu kiểm tra)", f"{oos_agg.get('total_trades', 0)} lệnh"))
            html.append(row("Kỳ vọng IS", f"{is_exp:+.2f}R/lệnh"))
            html.append(row("Kỳ vọng OOS", f"{oos_exp:+.2f}R/lệnh"))
            html.append(row("Tỷ lệ OOS/IS", f"{ratio:.2f} (càng gần 1 càng tốt)"))
            html.append(row("Điểm robustness", f"{score:.0f}/100"))
            html.append(row("Kết luận", v_text, v_color))
            html.append("</table>")

        diagnostics = self.result.get("diagnostics", {}) if isinstance(self.result.get("diagnostics"), dict) else {}
        html.extend(self._build_stats_diagnostics_html(
            diagnostics,
            text_color, muted_color, border_color, row_border, pipeline_title_color,
        ))

        html.append("</div>")
        return "".join(html)

    def _build_stats_overview_html(
        self,
        summary,
        text_color, value_color, muted_color, border_color, row_border,
        get_stat, eval_winrate, eval_profit_factor, eval_drawdown,
    ):
        html = []
        wr = float(summary.get("win_rate", 0) or 0)
        pf = float(summary.get("profit_factor", 0) or 0)
        dd = float(summary.get("max_drawdown_r", 0) or 0)

        html.append(
            f"<table style='width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 11px;'>"
            f"<tr>"
            f"<th style='text-align: left; padding: 6px 10px; border-bottom: 2px solid {border_color}; color: {muted_color};'>Chỉ số</th>"
            f"<th style='text-align: right; padding: 6px 10px; border-bottom: 2px solid {border_color}; color: {muted_color};'>Giá trị</th>"
            f"<th style='text-align: right; padding: 6px 10px; border-bottom: 2px solid {border_color}; color: {muted_color};'>Đánh giá</th>"
            f"</tr>"

            f"<tr>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>🔢 Tổng số lệnh</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {value_color}; font-weight: bold;'>{get_stat(summary, 'total_trades', '0')}</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {muted_color};'>-</td>"
            f"</tr>"

            f"<tr>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>🎯 Tỷ lệ thắng</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {value_color}; font-weight: bold;'>{get_stat(summary, 'win_rate')}%</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border};'>{eval_winrate(wr)}</td>"
            f"</tr>"

            f"<tr>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>💎 Hệ số lợi nhuận</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {value_color}; font-weight: bold;'>{get_stat(summary, 'profit_factor')}</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border};'>{eval_profit_factor(pf)}</td>"
            f"</tr>"

            f"<tr>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>🚀 Kỳ vọng</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {value_color}; font-weight: bold;'>{get_stat(summary, 'expectancy_r')}R</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {muted_color};'>-</td>"
            f"</tr>"

            f"<tr>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>📉 Drawdown tối đa</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {value_color}; font-weight: bold;'>{get_stat(summary, 'max_drawdown_r')}R</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border};'>{eval_drawdown(dd)}</td>"
            f"</tr>"

            f"<tr>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>💰 Tổng R</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: #10b981; font-weight: bold;'>{get_stat(summary, 'total_r')}R</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {muted_color};'>-</td>"
            f"</tr>"
            f"</table>"
        )

        wins = int(summary.get("wins", 0) or 0)
        losses = int(summary.get("losses", 0) or 0)
        breakeven_count = int(summary.get("breakeven", 0) or 0)
        expired_count = int(summary.get("expired", 0) or 0)
        avg_win_r = float(summary.get("average_win_r", 0) or 0)
        avg_loss_r = float(summary.get("average_loss_r", 0) or 0)
        max_consec_wins = int(summary.get("max_consecutive_wins", 0) or 0)
        max_consec_losses = int(summary.get("max_consecutive_losses", 0) or 0)
        avg_holding = float(summary.get("average_holding_bars", 0) or 0)

        html.append(
            f"<table style='width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 11px;'>"
            f"<tr>"
            f"<th style='text-align: left; padding: 8px 10px; border-bottom: 2px solid {border_color}; color: {muted_color};'>Chi tiết thắng/thua</th>"
            f"<th style='text-align: right; padding: 8px 10px; border-bottom: 2px solid {border_color}; color: {muted_color}; width: 60px;'>Số lượng</th>"
            f"<th style='text-align: left; padding: 8px 10px; border-bottom: 2px solid {border_color}; color: {muted_color};'>Chỉ số bổ sung</th>"
            f"<th style='text-align: right; padding: 8px 10px; border-bottom: 2px solid {border_color}; color: {muted_color}; width: 80px;'>Giá trị</th>"
            f"</tr>"

            f"<tr>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: #10b981;'>🟢 Thắng</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: #10b981; font-weight: bold;'>{wins}</td>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>Trung bình R thắng</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: #10b981; font-weight: bold;'>{avg_win_r:+.2f}R</td>"
            f"</tr>"

            f"<tr>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: #e11d48;'>🔴 Thua</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: #e11d48; font-weight: bold;'>{losses}</td>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>Trung bình R thua</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: #e11d48; font-weight: bold;'>{avg_loss_r:+.2f}R</td>"
            f"</tr>"

            f"<tr>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {muted_color};'>⚪ Hòa</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {muted_color}; font-weight: bold;'>{breakeven_count}</td>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>Chuỗi thắng tối đa</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: #10b981; font-weight: bold;'>{max_consec_wins}</td>"
            f"</tr>"

            f"<tr>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {muted_color};'>⏰ Hết hạn</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {muted_color}; font-weight: bold;'>{expired_count}</td>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>Chuỗi thua tối đa</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: #e11d48; font-weight: bold;'>{max_consec_losses}</td>"
            f"</tr>"

            f"<tr>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {muted_color};'>&nbsp;</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border};'>&nbsp;</td>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>Số nến giữ lệnh TB</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {muted_color}; font-weight: bold;'>{avg_holding:.0f} nến</td>"
            f"</tr>"
            f"</table>"
        )

        # --- Monthly heatmap ---
        by_month = (self.result or {}).get("breakdowns", {}).get("by_month")
        if by_month and isinstance(by_month, dict) and len(by_month) > 0:
            years: dict[str, dict[int, float]] = {}
            max_abs = 0.0
            for key, val in by_month.items():
                if not isinstance(val, dict):
                    continue
                try:
                    y_str, m_str = key.split("-")
                    yr = y_str
                    mo = int(m_str)
                except (ValueError, AttributeError):
                    continue
                total_r = float(val.get("total_r", 0) or 0)
                years.setdefault(yr, {})[mo] = total_r
                max_abs = max(max_abs, abs(total_r))
            if years and max_abs > 0:
                light_theme = self._is_light_theme()
                no_data_bg = "#f3f4f6" if light_theme else "#1f2937"
                head_bg = "#e5e7eb" if light_theme else "#1e293b"
                head_text = "#374151" if light_theme else "#9ca3af"
                def _heat_bg(value, max_v):
                    if value is None:
                        return no_data_bg
                    ratio = min(1.0, abs(value) / max_v) if max_v > 0 else 0
                    if value > 0:
                        r = int(209 - ratio * 203)
                        g = int(250 - ratio * 204)
                        b = int(229 - ratio * 210)
                    elif value < 0:
                        r = int(254 - ratio * 127)
                        g = int(226 - ratio * 195)
                        b = int(226 - ratio * 195)
                    else:
                        return no_data_bg
                    return f"#{max(0,min(255,r)):02x}{max(0,min(255,g)):02x}{max(0,min(255,b)):02x}"
                def _text(value, max_v):
                    if value is None:
                        return "-", text_color
                    ratio = min(1.0, abs(value) / max_v) if max_v > 0 else 0
                    txt = f"+{value:.2f}" if value > 0 else f"{value:.2f}"
                    clr = "#ffffff" if ratio > 0.65 else text_color
                    return txt, clr
                html.append(f"<h2 style='color:{text_color}; margin-bottom: 10px; margin-top: 6px; font-size: 12px;'>📅 Bảng nhiệt lời/lỗ theo tháng</h2>")
                html.append(f"<table style='width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 11px;'>")
                hdr = [f"<th style='text-align: left; padding: 6px 8px; border-bottom: 2px solid {border_color}; color: {head_text}; background: {head_bg};'>Năm</th>"]
                for m in range(1, 13):
                    hdr.append(f"<th style='text-align: center; padding: 4px 3px; border-bottom: 2px solid {border_color}; color: {head_text}; background: {head_bg}; width: 44px;'>T{m}</th>")
                hdr.append(f"<th style='text-align: center; padding: 6px 8px; border-bottom: 2px solid {border_color}; color: {head_text}; background: {head_bg};'>Cả năm</th>")
                html.append("<tr>" + "".join(hdr) + "</tr>")
                for year in sorted(years.keys()):
                    month_data = years[year]
                    yearly_total = 0.0
                    row = [f"<td style='padding: 4px 8px; border-bottom: 1px solid {row_border}; color: {text_color}; font-weight: 600;'>{year}</td>"]
                    for m in range(1, 13):
                        val = month_data.get(m)
                        bg = _heat_bg(val, max_abs)
                        t, tc = _text(val, max_abs)
                        if val is not None:
                            yearly_total += val
                        row.append(f"<td style='text-align: center; padding: 3px 2px; border-bottom: 1px solid {row_border}; background: {bg}; color: {tc}; font-size: 10px;'>{t}</td>")
                    yc = "#10b981" if yearly_total > 0 else ("#e11d48" if yearly_total < 0 else text_color)
                    row.append(f"<td style='text-align: center; padding: 4px 6px; border-bottom: 1px solid {row_border}; color: {yc}; font-weight: 700; font-size: 11px;'>{yearly_total:+.1f}R</td>")
                    html.append("<tr>" + "".join(row) + "</tr>")
                html.append("</table>")

        # --- Monte Carlo confidence intervals ---
        mc = (self.result or {}).get("monte_carlo")
        if mc and isinstance(mc, dict) and mc.get("expectancy_r", {}).get("mean") is not None:
            def _mc_color(low, high):
                if low is not None and low > 0:
                    return "#10b981"
                if high is not None and high < 0:
                    return "#e11d48"
                return "#f59e0b"

            def _mc_fmt(val, suffix):
                if val is None:
                    return "--"
                return f"+{val:.2f}{suffix}" if val >= 0 else f"{val:.2f}{suffix}"

            def _mc_row(label, data, suffix="R"):
                mean_v = data.get("mean")
                low_v = data.get("p95_low")
                high_v = data.get("p95_high")
                clr = _mc_color(low_v, high_v)
                return (
                    f"<td style='padding: 5px 10px; border-bottom: 1px solid {row_border}; color: {text_color}; font-size: 11px;'>{label}</td>"
                    f"<td style='text-align: right; padding: 5px 10px; border-bottom: 1px solid {row_border}; color: {clr}; font-weight: 600; font-size: 11px;'>{_mc_fmt(mean_v, suffix)}</td>"
                    f"<td style='text-align: right; padding: 5px 10px; border-bottom: 1px solid {row_border}; color: {clr}; font-size: 11px;'>{_mc_fmt(low_v, suffix)} → {_mc_fmt(high_v, suffix)}</td>"
                )

            html.append(f"<h2 style='color:{text_color}; margin-bottom: 10px; margin-top: 6px; font-size: 12px;'>🎲 Khoảng tin cậy Monte Carlo</h2>")
            html.append(f"<table style='width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 11px;'>")
            html.append(
                f"<tr>"
                f"<th style='text-align: left; padding: 6px 10px; border-bottom: 2px solid {border_color}; color: {muted_color};'>Chỉ số</th>"
                f"<th style='text-align: right; padding: 6px 10px; border-bottom: 2px solid {border_color}; color: {muted_color};'>Giá trị TB</th>"
                f"<th style='text-align: right; padding: 6px 10px; border-bottom: 2px solid {border_color}; color: {muted_color};'>Khoảng 95%</th>"
                f"</tr>"
            )

            html.append("<tr>" + _mc_row("Kỳ vọng", mc.get("expectancy_r", {})) + "</tr>")

            # Drawdown row with P(DD > 10R) note
            dd = mc.get("max_drawdown_r", {})
            dd_clr = _mc_color(dd.get("p95_low"), dd.get("p95_high"))
            prob_dd = mc.get("prob_dd_exceed_10r")
            dd_note = f" <span style='font-size:10px;color:{muted_color};'>(P(DD&gt;10R)={prob_dd}%)</span>" if prob_dd is not None else ""
            html.append(
                f"<tr>"
                f"<td style='padding:5px 10px;border-bottom:1px solid {row_border};color:{text_color};font-size:11px;'>Drawdown tối đa</td>"
                f"<td style='text-align:right;padding:5px 10px;border-bottom:1px solid {row_border};color:{dd_clr};font-weight:600;font-size:11px;'>{_mc_fmt(dd.get('mean'), 'R')}{dd_note}</td>"
                f"<td style='text-align:right;padding:5px 10px;border-bottom:1px solid {row_border};color:{dd_clr};font-size:11px;'>{_mc_fmt(dd.get('p95_low'), 'R')} → {_mc_fmt(dd.get('p95_high'), 'R')}</td>"
                f"</tr>"
            )

            html.append("<tr>" + _mc_row("Hệ số lợi nhuận", mc.get("profit_factor", {}), "") + "</tr>")
            html.append("<tr>" + _mc_row("Tỷ lệ thắng", mc.get("win_rate", {}), "%") + "</tr>")

            # Max consecutive losses: mean (max: p95_high)
            cl = mc.get("max_consecutive_losses", {})
            cl_mean = cl.get("mean")
            cl_high = cl.get("p95_high")
            cl_clr = "#10b981" if (cl_mean or 0) <= 3 else ("#f59e0b" if (cl_mean or 0) <= 6 else "#e11d48")
            html.append(
                f"<tr>"
                f"<td style='padding:5px 10px;border-bottom:1px solid {row_border};color:{text_color};font-size:11px;'>Chuỗi thua dài nhất</td>"
                f"<td style='text-align:right;padding:5px 10px;border-bottom:1px solid {row_border};color:{cl_clr};font-weight:600;font-size:11px;'>{cl_mean:.0f} lệnh (tối đa: {cl_high:.0f})</td>"
                f"<td style='text-align:right;padding:5px 10px;border-bottom:1px solid {row_border};color:{muted_color};font-size:11px;'>—</td>"
                f"</tr>"
            )

            # Bottom row: P(expectancy < 0)
            prob_neg = mc.get("prob_negative_expectancy")
            if prob_neg is not None:
                pn_color = "#10b981" if prob_neg < 20 else ("#f59e0b" if prob_neg <= 50 else "#e11d48")
                html.append(
                    f"<tr>"
                    f"<td colspan='3' style='padding:6px 10px;border-bottom:1px solid {row_border};color:{pn_color};font-weight:700;font-size:11px;text-align:center;'>"
                    f"P(kỳ vọng &lt; 0) = {prob_neg}%"
                    f"</td>"
                    f"</tr>"
                )

            html.append("</table>")
        return html

    def _build_stats_diagnostics_html(
        self,
        diagnostics,
        text_color, muted_color, border_color, row_border, pipeline_title_color,
    ):
        html = []
        pipeline_stats = diagnostics.get("pipeline_stats", {})
        gate_fail_counts = diagnostics.get("gate_fail_counts", {})
        if pipeline_stats:
            html.append(f"<h2 style='color:{pipeline_title_color}; margin-bottom: 12px; margin-top: 24px; font-size: 12px;'>🔬 CHẨN ĐOÁN PIPELINE</h2>")
            html.append(
                f"<table style='width: 100%; border-collapse: collapse; margin-bottom: 16px; font-size: 11px;'>"
                f"<tr>"
                f"<th style='text-align: left; padding: 8px 10px; border-bottom: 2px solid {border_color}; color: {muted_color};'>Bước</th>"
                f"<th style='text-align: center; padding: 8px 10px; border-bottom: 2px solid {border_color}; color: #10b981;'>Pass</th>"
                f"<th style='text-align: center; padding: 8px 10px; border-bottom: 2px solid {border_color}; color: #e11d48;'>Fail</th>"
                f"<th style='text-align: center; padding: 8px 10px; border-bottom: 2px solid {border_color}; color: #f59e0b;'>Warning</th>"
                f"<th style='text-align: left; padding: 8px 10px; border-bottom: 2px solid {border_color}; color: {muted_color};'>Trạng thái</th>"
                f"</tr>"
            )
            step_labels = {
                "validate": "1. Validate",
                "correlation": "2. Correlation",
                "score": "3. Score",
                "scenarios": "4. Scenarios",
                "direction": "5. Direction",
                "gate": "6. Gate",
                "final_score": "7. Final Score",
            }
            for step_key, label in step_labels.items():
                stats = pipeline_stats.get(step_key, {})
                if not stats:
                    continue
                p = stats.get("pass", 0)
                f = stats.get("fail", 0)
                w = stats.get("warning", 0)
                total = p + f + w
                if total == 0:
                    continue
                if f > 0:
                    status_icon = "🔴"
                    status_text = "Có lỗi"
                elif w > 0:
                    status_icon = "🟡"
                    status_text = "Cảnh báo"
                else:
                    status_icon = "🟢"
                    status_text = "OK"
                html.append(
                    f"<tr>"
                    f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>{label}</td>"
                    f"<td style='text-align: center; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: #10b981;'>{p}</td>"
                    f"<td style='text-align: center; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: #e11d48;'>{f}</td>"
                    f"<td style='text-align: center; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: #f59e0b;'>{w}</td>"
                    f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>{status_icon} {status_text}</td>"
                    f"</tr>"
                )
            html.append("</table>")

            ev = diagnostics.get("snapshots_evaluated", 0)
            blk = diagnostics.get("blocked_by_gate", 0)
            low = diagnostics.get("score_below_50_count", 0)
            html.append(
                f"<div style='display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 12px; font-size: 11px; color: {muted_color};'>"
                f"<span>📊 Tổng snapshot: <b style='color:{text_color};'>{ev}</b></span>"
                f"<span>🚫 Bị gate chặn: <b style='color:#e11d48;'>{blk}</b></span>"
                f"<span>⚠️ Điểm {'<'}50: <b style='color:#f59e0b;'>{low}</b></span>"
                f"</div>"
            )

        if gate_fail_counts:
            html.append(f"<h3 style='color:{pipeline_title_color}; margin-bottom: 8px; margin-top: 16px; font-size: 12px;'>🚧 Chi tiết Gate</h3>")
            html.append(
                f"<table style='width: 100%; border-collapse: collapse; margin-bottom: 12px; font-size: 11px;'>"
                f"<tr>"
                f"<th style='text-align: left; padding: 6px 10px; border-bottom: 1px solid {border_color}; color: {muted_color};'>Gate</th>"
                f"<th style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {border_color}; color: {muted_color};'>Số lần chặn/cảnh báo</th>"
                f"</tr>"
            )
            for gate_name, count in sorted(gate_fail_counts.items(), key=lambda x: -x[1]):
                html.append(
                    f"<tr>"
                    f"<td style='padding: 4px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>{gate_name}</td>"
                    f"<td style='text-align: right; padding: 4px 10px; border-bottom: 1px solid {row_border}; color: #fb7185; font-weight: bold;'>{count}</td>"
                    f"</tr>"
                )
            html.append("</table>")
        return html

    @staticmethod
    def _format_ai_to_html(raw: str, light: bool = False) -> str:
        lines = raw.splitlines()
        html_lines: list[str] = []
        _esc = html.escape

        if light:
            h_color = "#0f172a"
            t_color = "#334155"
            m_color = "#64748b"
            acc_color = "#c2410c"
            b_color = "#f1f5f9"
            b_border = "#e2e8f0"
        else:
            h_color = "#f8fafc"
            t_color = "#cbd5e1"
            m_color = "#94a3b8"
            acc_color = "#f59e0b"
            b_color = "#1e293b"
            b_border = "#334155"

        def _highlight_numbers(text: str) -> str:
            """Wrap numbers and key metrics in styled spans."""
            import re as _re
            # Highlight R values: +0.15R, -1.0R, 2.54R
            text = _re.sub(r'([+-]?\d+\.?\d*R)', r'<b style="color:' + acc_color + r';">\1</b>', text)
            # Highlight percentages: 45.5%
            text = _re.sub(r'(\d+\.?\d*%)', r'<b style="color:' + acc_color + r';">\1</b>', text)
            # Highlight profit factor numbers: PF 1.5, PF=2.54
            text = _re.sub(r'(PF\s*=?\s*)(\d+\.?\d*)',
                          r'\1<b style="color:' + acc_color + r';">\2</b>', text)
            return text

        in_list = False
        list_type = None

        def _end_list():
            nonlocal in_list, list_type
            if in_list:
                html_lines.append("</ul>" if list_type == "ul" else "</ol>")
                in_list = False
                list_type = None

        for line in lines:
            stripped = line.strip()

            if not stripped:
                _end_list()
                continue

            # Detect heading: ends with colon, or is UPPERCASE, or starts with number+dot+space pattern like "1."
            is_heading = False
            if stripped.endswith(":") and len(stripped) < 55 and len(stripped[:-1].split()) <= 7:
                is_heading = True
            elif stripped.isupper() and len(stripped) > 5:
                is_heading = True

            if is_heading:
                _end_list()
                clean = _esc(stripped.replace("*", "").replace("#", "").replace("_", "").replace("`", ""))
                html_lines.append(
                    f"<div style='font-weight:700;font-size:14px;color:{h_color};"
                    f"margin:16px 0 4px 0;padding-bottom:4px;"
                    f"border-bottom:1px solid {b_border};'>{clean}</div>"
                )
                continue

            # Numbered items: "1. text" or "1) text"
            m = re.match(r"^(\d+)[.)]\s+(.*)", stripped)
            if m:
                if not in_list or list_type != "ol":
                    _end_list()
                    html_lines.append(f"<ol style='margin:4px 0;padding-left:20px;color:{t_color};font-size:13px;line-height:1.55;'>")
                    in_list = True
                    list_type = "ol"
                content = _highlight_numbers(_esc(m.group(2).replace("*", "").replace("#", "").replace("_", "").replace("`", "")))
                html_lines.append(f"<li style='margin:2px 0;'>{content}</li>")
                continue

            # Bullet items: "- text", "* text", "• text"
            m = re.match(r"^[-*•]\s+(.*)", stripped)
            if m:
                if not in_list or list_type != "ul":
                    _end_list()
                    html_lines.append(f"<ul style='margin:4px 0;padding-left:20px;color:{t_color};font-size:13px;line-height:1.55;'>")
                    in_list = True
                    list_type = "ul"
                content = _highlight_numbers(_esc(m.group(1).replace("*", "").replace("#", "").replace("_", "").replace("`", "")))
                html_lines.append(f"<li style='margin:2px 0;'>{content}</li>")
                continue

            # Regular text
            _end_list()
            clean = _highlight_numbers(_esc(stripped.replace("*", "").replace("#", "").replace("_", "").replace("`", "")))
            html_lines.append(
                f"<p style='margin:4px 0;color:{t_color};font-size:13px;line-height:1.55;'>{clean}</p>"
            )

        _end_list()
        body = "\n".join(html_lines)
        return (
            f"<div style='font-family:-apple-system,Segoe UI,Helvetica,sans-serif;font-size:13px;'>"
            f"{body}</div>"
        )

    def _show_input_help(self) -> None:
        dialog = BacktestInputHelpDialog(self)
        dialog.exec()

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if hasattr(self, "table") and watched is self.table.viewport() and event.type() == QEvent.Type.Resize:
            self._resize_trade_columns_to_viewport()
        return super().eventFilter(watched, event)

    def _run_backtest(self) -> None:
        try:
            requests = self.controller.build_requests(
                symbols=[self.selected_symbol],
                start=self._qdate_to_utc_start(self.start_date.date()),
                end=self._qdate_to_utc_end(self.end_date.date()),
                initial_balance=self.balance_input.value(),
                risk_percent=self.risk_input.value(),
            )
        except Exception as exc:
            QMessageBox.warning(self, "Không tạo được request", str(exc))
            return

        self.run_button.setEnabled(False)
        self.analyze_btn.setEnabled(False)
        self.apply_config_btn.hide()
        self.progress.setValue(0)
        self.status_label.setText("Đang chạy backtest...")
        self.backtest_thread, self.backtest_worker = self.controller.create_backtest_worker(
            requests, walk_forward_enabled=self.walk_forward_checkbox.isChecked()
        )
        self.backtest_worker.progress.connect(self._on_progress)
        self.backtest_worker.succeeded.connect(self._on_success)
        self.backtest_worker.failed.connect(self._on_failed)
        self.backtest_worker.finished.connect(lambda: self.run_button.setEnabled(True))
        self.backtest_worker.finished.connect(lambda: self.analyze_btn.setEnabled(True))
        self.backtest_thread.start()

    def _on_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(percent)
        self.status_label.setText(message)

    def _show_symbol_dialog(self) -> None:
        dialog = SymbolSelectionDialog(self.selected_symbol, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.selected_symbol = dialog.selected_symbol()
            self.symbol_summary.setText(self.selected_symbol)
            self.symbol_summary.setToolTip(self.selected_symbol)

    def _on_success(self, result: dict) -> None:
        self.result = result
        self.status_label.setText("Hoàn tất backtest.")
        self._set_summary(result.get("summary", {}) if isinstance(result.get("summary"), dict) else {})
        self._set_trades(result.get("trades", []) if isinstance(result.get("trades"), list) else [])
        self._update_verdict()
        self.apply_config_btn.show()
        self.snapshot_label.setText(f"File kết quả: {result.get('snapshot_path', '')}")
        self.snapshot_label.show()
        self._refresh_result_text()
        self._refresh_equity_curve()

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
            ("Lệnh", self._format_integer(summary.get("total_trades", 0))),
            ("Thắng", self._format_decimal(summary.get("win_rate", 0), 1, "%")),
            ("Kỳ vọng", self._format_decimal(summary.get("expectancy_r", 0), 2, "R")),
            ("Hệ số LN", self._format_decimal(summary.get("profit_factor", 0), 2)),
            ("DD tối đa", self._format_decimal(summary.get("max_drawdown_r", 0), 1, "R")),
            ("Tổng R", self._format_decimal(summary.get("total_r", 0), 1, "R")),
            ("Thắng TB", self._format_decimal(summary.get("average_win_r", 0), 2, "R")),
            ("Thua TB", self._format_decimal(summary.get("average_loss_r", 0), 2, "R")),
            ("Thua max", str(int(summary.get("max_consecutive_losses", 0) or 0))),
        ]
        for title, value in items:
            self.summary_row.addWidget(self._stat_cell(str(title), str(value)))
        self.summary_row.addStretch(1)

    def _set_trades(self, trades: list[dict[str, object]]) -> None:
        self.trades = trades
        self.table.setRowCount(len(trades))
        for row, trade in enumerate(trades):
            for col, (key, _label) in enumerate(self.TRADE_COLUMNS):
                if key == "stt":
                    value = str(row + 1)
                else:
                    value = self._format_trade_value(key, trade.get(key, "--"))
                item = QTableWidgetItem(value)
                if key in {"stt", "result_r", "final_score", "expected_effective_rr"}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, col, item)
        self._refresh_trade_table_style()
        self._apply_trade_table_layout()
        self.table.viewport().update()

    def _update_verdict(self) -> None:
        """Show a compact verdict badge inline in the header row."""
        if not self.result:
            self.verdict_banner.hide()
            return
        summary = self.result.get("summary", {}) if isinstance(self.result.get("summary"), dict) else {}

        total = int(summary.get("total_trades", 0) or 0)
        wr = float(summary.get("win_rate", 0) or 0)
        exp_r = float(summary.get("expectancy_r", 0) or 0)
        pf = float(summary.get("profit_factor", 0) or 0)
        dd = float(summary.get("max_drawdown_r", 0) or 0)
        total_r = float(summary.get("total_r", 0) or 0)

        has_edge = exp_r > 0.10
        good_pf = pf > 1.2
        positive_total = total_r > 0

        light = self._is_light_theme()

        if light:
            if total == 0:
                accent, bg, border, separator, text = "#475569", "#f1f5f9", "#cbd5e1", "#cbd5e1", "#334155"
                line = "Chưa có lệnh nào"
            elif has_edge and good_pf:
                accent, bg, border, separator, text = "#047857", "#d1fae5", "#a7f3d0", "#a7f3d0", "#065f46"
                line = f"CÓ LỢI THẾ · Kỳ vọng +{exp_r:.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"
            elif has_edge and not good_pf:
                accent, bg, border, separator, text = "#b45309", "#fef3c7", "#fde68a", "#fde68a", "#78350f"
                line = f"LỢI THẾ YẾU · Kỳ vọng +{exp_r:.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"
            elif positive_total and not has_edge:
                accent, bg, border, separator, text = "#ea580c", "#ffedd5", "#fed7aa", "#fed7aa", "#7c2d12"
                line = f"CHƯA RÕ · Kỳ vọng {exp_r:+.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"
            else:
                accent, bg, border, separator, text = "#be123c", "#ffe4e6", "#fecdd3", "#fecdd3", "#9f1239"
                line = f"HỆ THỐNG ÂM · Kỳ vọng {exp_r:+.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"
        else:
            if total == 0:
                accent, bg, border, separator, text = "#94a3b8", "#0f172a", "#1e293b", "#334155", "#cbd5e1"
                line = "Chưa có lệnh nào"
            elif has_edge and good_pf:
                accent, bg, border, separator, text = "#10b981", "#064e3b", "#065f46", "#334155", "#cbd5e1"
                line = f"CÓ LỢI THẾ · Kỳ vọng +{exp_r:.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"
            elif has_edge and not good_pf:
                accent, bg, border, separator, text = "#f59e0b", "#451a03", "#78350f", "#334155", "#cbd5e1"
                line = f"LỢI THẾ YẾU · Kỳ vọng +{exp_r:.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"
            elif positive_total and not has_edge:
                accent, bg, border, separator, text = "#fb923c", "#431407", "#7c2d12", "#334155", "#cbd5e1"
                line = f"CHƯA RÕ · Kỳ vọng {exp_r:+.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"
            else:
                accent, bg, border, separator, text = "#e11d48", "#4c0519", "#881337", "#334155", "#cbd5e1"
                line = f"HỆ THỐNG ÂM · Kỳ vọng {exp_r:+.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"

        self.verdict_banner.setStyleSheet(
            f"QLabel#BacktestVerdict {{"
            f"  background: {bg};"
            f"  border: 1px solid {border};"
            f"  border-radius: 6px;"
            f"  padding: 4px 10px;"
            f"}}"
        )

        self.verdict_banner.setText(
            f"<span style='font-size:11px;font-family:-apple-system,Segoe UI,sans-serif;white-space:nowrap;'>"
            f"<b style='color:{accent};'>{line}</b>"
            f"<span style='color:{separator};'>&nbsp;&nbsp;│&nbsp;&nbsp;</span>"
            f"<span style='color:{text};font-weight:500;'>"
            f"{total} lệnh &nbsp;·&nbsp; TL thắng {wr:.1f}% &nbsp;·&nbsp; DD {dd:.1f}R"
            f"</span>"
            f"</span>"
        )
        self.verdict_banner.show()


    def _is_light_theme(self) -> bool:
        try:
            settings = (
                self.app.settings_service.load()
                if self.app
                else self.controller.settings_service.load()
            )
            return settings.display.theme == "light"
        except Exception:
            return False

    def _refresh_progress_bar_style(self) -> None:
        pass

    def _refresh_trade_table_style(self) -> None:
        if not hasattr(self, "trades") or not self.trades:
            return
        
        from PyQt6.QtGui import QBrush, QColor
        
        for row, trade in enumerate(self.trades):
            for col, (key, _label) in enumerate(self.TRADE_COLUMNS):
                cell = self.table.item(row, col)
                if not cell:
                    continue
                
                # Reset background to let alternating colors show
                cell.setBackground(QBrush())
                
                # Apply foreground (text) color based on column and value
                fg_color = None
                
                if key == "stt":
                    fg_color = QColor("#9ca3af")
                elif key == "side":
                    side = str(trade.get("side", "")).lower()
                    if side == "buy": fg_color = QColor("#ea580c")
                    elif side == "sell": fg_color = QColor("#f43f5e")
                elif key in ("result", "result_r", "expected_effective_rr"):
                    val_str = str(trade.get(key, "")).lower()
                    if key == "result":
                        if val_str == "win": fg_color = QColor("#10b981")
                        elif val_str == "loss": fg_color = QColor("#e11d48")
                        elif val_str == "breakeven": fg_color = QColor("#f59e0b")
                    else:
                        try:
                            val_num = float(val_str.replace("r", "").strip())
                            if val_num > 0: fg_color = QColor("#10b981")
                            elif val_num < 0: fg_color = QColor("#e11d48")
                            else: fg_color = QColor("#9ca3af")
                        except ValueError:
                            fg_color = QColor("#9ca3af")
                elif key == "final_score":
                    try:
                        score = int(trade.get("final_score", 0))
                        if score >= 65: fg_color = QColor("#10b981")
                        elif score >= 50: fg_color = QColor("#f59e0b")
                        else: fg_color = QColor("#9ca3af")
                    except (TypeError, ValueError):
                        fg_color = QColor("#9ca3af")
                elif key == "market_regime":
                    regime = str(trade.get("market_regime", "")).lower()
                    if regime == "aligned": fg_color = QColor("#10b981")
                    elif regime == "divergent": fg_color = QColor("#e11d48")
                    elif regime == "neutral": fg_color = QColor("#f59e0b")
                    else: fg_color = QColor("#9ca3af")
                
                if fg_color:
                    cell.setForeground(fg_color)
                else:
                    cell.setForeground(QBrush())


    def refresh_theme_styles(self) -> None:
        self._refresh_theme_styles()

    def _refresh_theme_styles(self) -> None:
        self._refresh_progress_bar_style()
        self._refresh_verdict_banner_style()
        self._refresh_trade_table_style()
        if hasattr(self, "settings_frame") and self.settings_frame:
            self.settings_frame.setStyleSheet(self._backtest_form_stylesheet())
        self._refresh_tab_styles()
        self._refresh_result_text_style()

    def _refresh_tab_styles(self) -> None:
        pass

    def _refresh_result_text_style(self) -> None:
        if not hasattr(self, 'result_text'):
            return
        light = self._is_light_theme()
        if light:
            style = (
                "QTextEdit#BacktestResultText { background: #ffffff; color: #1e293b; font-size: 11px; "
                "border: none; border-radius: 6px; padding: 8px; }"
            )
        else:
            style = (
                "QTextEdit#BacktestResultText { background: #0f172a; color: #e2e8f0; font-size: 11px; "
                "border: none; border-radius: 6px; padding: 8px; }"
            )
        self.result_text.setStyleSheet(style)
        if hasattr(self, 'sweep_result_text'):
            self.sweep_result_text.setStyleSheet(style)

    def _refresh_verdict_banner_style(self) -> None:
        self._update_verdict()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_theme_styles()

    def _apply_trade_table_layout(self) -> None:
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        for column, (_key, _label) in enumerate(self.TRADE_COLUMNS):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        self._resize_trade_columns_to_viewport()

    def _resize_trade_columns_to_viewport(self) -> None:
        viewport_width = self.table.viewport().width()
        if viewport_width <= 0:
            return

        weights = [self.TRADE_COLUMN_WEIGHTS[key] for key, _label in self.TRADE_COLUMNS]
        total_weight = sum(weights)
        # Last column gets the remainder via stretch
        for column in range(len(self.TRADE_COLUMNS) - 1):
            width = max(20, int(viewport_width * weights[column] / total_weight))
            self.table.setColumnWidth(column, width)

    @staticmethod
    def _apply_number_format(spinbox: QDoubleSpinBox | QSpinBox) -> None:
        spinbox.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        spinbox.setGroupSeparatorShown(True)
        spinbox.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)

    def _backtest_form_stylesheet(self) -> str:
        light = self._is_light_theme()
        if light:
            text_color = "#1f2937"
            title_color = "#111827"
            border_color = "#cbd5e1"
            input_bg = "#ffffff"
            input_border = "#d1d5db"
            stat_bg = "#f3f4f6"
            stat_border = "#e5e7eb"
            stat_title = "#4b5563"
            stat_val = "#111827"
        else:
            text_color = "#e5e7eb"
            title_color = "#f9fafb"
            border_color = "#334155"
            input_bg = "#111827"
            input_border = "#475569"
            stat_bg = "#1e293b"
            stat_border = "#334155"
            stat_title = "#94a3b8"
            stat_val = "#f8fafc"
            
        return f"""
        QFrame#MiniStatCompact {{
            background-color: {stat_bg};
            border: 1px solid {stat_border};
            border-radius: 4px;
        }}
        QLabel#MiniStatTitleCompact {{
            color: {stat_title};
            font-size: 11px;
            font-weight: 600;
        }}
        QLabel#MiniStatValueCompact {{
            color: {stat_val};
            font-size: 11px;
            font-weight: 800;
        }}
        #BacktestField {{
            background: {input_bg};
            border: 1px solid {input_border};
            border-radius: 4px;
            color: {text_color};
            padding: 1px 6px;
            min-height: 18px;
            max-height: 18px;
            font-size: 11px;
        }}
        #BacktestField:hover {{
            border: 1px solid {"#94a3b8" if light else "#64748b"};
            background: {"#f9fafb" if light else "#151f2e"};
        }}
        #BacktestField:focus {{
            border: 1px solid #38bdf8;
            background: {input_bg};
        }}
        QComboBox#BacktestField {{
            padding: 1px 22px 1px 6px;
        }}
        QComboBox#BacktestField::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 18px;
            border-left: 1px solid {input_border};
            border-top-right-radius: 4px;
            border-bottom-right-radius: 4px;
            background: transparent;
        }}
        QComboBox#BacktestField::drop-down:hover {{
            background: {"#e5e7eb" if light else "#1e293b"};
        }}
        QComboBox#BacktestField::down-arrow {{
            image: url(assets/icons/chevron-down.svg);
            width: 10px;
            height: 10px;
        }}
        #BacktestSymbolSummary {{
            color: {title_color};
            font-size: 11px;
            font-weight: 700;
            background: {"#e5e7eb" if light else "#0f172a"};
            border: 1px solid {border_color};
            border-radius: 4px;
            padding: 1px 6px;
            min-height: 18px;
            max-height: 18px;
        }}
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
        if key == "expected_effective_rr":
            return self._format_decimal(value, 1)
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
            return gmt7.strftime("%d/%m/%Y %H:%M")
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
            "Min Score",
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
    def __init__(self, selected_symbol: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Chọn mã kiểm thử")
        self.setObjectName("ScannerHelpDialog")
        self.setModal(True)
        self.setMinimumSize(360, 400)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        label = QLabel("Chọn một mã để backtest:")
        label.setObjectName("FormLabel")
        root.addWidget(label)

        scroll = QScrollArea()
        scroll.setObjectName("SymbolSelectionScroll")
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("SymbolSelectionContent")
        grid = QGridLayout(content)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)

        self._button_group = QButtonGroup(self)
        symbols = sorted(SUPPORTED_SYMBOLS)
        for index, symbol in enumerate(symbols):
            radio = QRadioButton(symbol)
            if symbol == selected_symbol:
                radio.setChecked(True)
            self._button_group.addButton(radio)
            grid.addWidget(radio, index // 3, index % 3)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 8, 0, 0)
        buttons_layout.setSpacing(8)
        buttons_layout.addStretch(1)
        cancel_btn = action_button("❌ Hủy", primary=False, color="danger")
        cancel_btn.setProperty("btnSize", "small")
        ok_btn = action_button("✅ Chọn", primary=True, color="success")
        ok_btn.setProperty("btnSize", "small")
        buttons_layout.addWidget(cancel_btn)
        buttons_layout.addWidget(ok_btn)
        root.addLayout(buttons_layout)

        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

    def selected_symbol(self) -> str:
        checked = self._button_group.checkedButton()
        return checked.text() if checked else "EUR/USD"
