from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os

from PyQt6.QtCore import QDate, QEvent, QLocale, QObject, QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
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
from core.backtest_config import (
    apply_validated_backtest_config,
    reconcile_enabled_symbol,
)
from core.backtest_contract import (
    BACKTEST_PURPOSE_RESEARCH,
    BACKTEST_PURPOSE_VALIDATION,
)
from core.backtest_execution_parity import (
    EXECUTION_MODE_PARITY,
    EXECUTION_MODE_RESEARCH,
)
from core.backtest_migration import LEGACY_RESEARCH, migrate_snapshot_payload
from core.backtest_presentation import (
    ACTION_APPLY_VALIDATED,
    ACTION_SAVE_DRAFT,
    lifecycle_reason_labels,
    lifecycle_status_label,
    result_action,
    snapshot_symbols,
)
from core.param_sensitivity import (
    DEFAULT_PERIODS,
    DEFAULT_SWEEP_CONFIGS,
    SECONDARY_SWEEP_CONFIGS,
    MarketPeriod,
    ParamSweepConfig,
    export_results,
)
from ui.layout_system import (
    LayoutTokens,
    configure_button,
    configure_checkbox,
    configure_control,
    configure_dialog,
    configure_form_grid,
    configure_form_label,
    configure_help_button,
    configure_layout,
    configure_progress,
    configure_table,
)
from ui.rich_text import empty_state_html, set_rich_html
from ui.matplotlib_theme import (
    apply_axes_theme,
    apply_figure_theme,
    apply_legend_theme,
)
from ui.screens.shared import action_button, card, page_header
from ui.theme.fonts import QSS_BODY, QSS_NUMBER, QSS_SMALL, QSS_SUBTITLE, QSS_TITLE
from ui.theme_manager import current_palette, is_light_theme, set_dynamic_property


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
    _DATE_FIELD_WIDTH = 184  # dd/MM/yyyy + calendar affordance at the current UI font
    _BACKTEST_TIMESTAMP_RE = re.compile(
        r"(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2})\s*\|\s*(.+?)\s*$"
    )
    _BACKTEST_TIMESTAMP_LEGACY_RE = re.compile(
        r"(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2})\s*$"
    )

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
        self.selected_symbols: list[str] = ["EUR/USD"]
        self.setObjectName("FormScreen")
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        configure_layout(
            root,
            margins=LayoutTokens.PAGE_MARGIN,
            spacing=LayoutTokens.SPACE_2,
        )
        root.addWidget(
            page_header(
                "Backtest",
                "",
            )
        )
        root.addWidget(self._settings_card())
        root.addWidget(self._trades_card(), 1)
        self._connect_compact_size_signals()
        self._refresh_theme_styles()

    def _connect_compact_size_signals(self) -> None:
        self.start_date.dateChanged.connect(self._refresh_compact_control_sizes)
        self.end_date.dateChanged.connect(self._refresh_compact_control_sizes)
        self.balance_input.textChanged.connect(self._refresh_compact_control_sizes)
        self.risk_input.textChanged.connect(self._refresh_compact_control_sizes)
        self.purpose_combo.currentTextChanged.connect(
            self._refresh_compact_control_sizes
        )
        self.advanced_execution_combo.currentTextChanged.connect(
            self._refresh_compact_control_sizes
        )
        self.sweep_params_combo.currentTextChanged.connect(
            self._refresh_compact_control_sizes
        )
        self.sweep_period_combo.currentTextChanged.connect(
            self._refresh_compact_control_sizes
        )

    def _refresh_compact_control_sizes(self, *_args: object) -> None:
        if not hasattr(self, "sweep_period_combo"):
            return
        configure_control(self.symbol_summary, width=LayoutTokens.FIELD_SM)
        configure_control(self.start_date, width=self._DATE_FIELD_WIDTH)
        self.start_date.setMinimumWidth(self._DATE_FIELD_WIDTH)
        self.start_date.setMaximumWidth(self._DATE_FIELD_WIDTH)
        configure_control(self.end_date, width=self._DATE_FIELD_WIDTH)
        self.end_date.setMinimumWidth(self._DATE_FIELD_WIDTH)
        self.end_date.setMaximumWidth(self._DATE_FIELD_WIDTH)
        configure_control(self.balance_input, width=120)
        self.balance_input.setMinimumWidth(120)
        self.balance_input.setMaximumWidth(120)
        configure_control(self.risk_input, width=80)
        configure_control(self.purpose_combo, width=LayoutTokens.FIELD_MD)
        configure_control(
            self.advanced_execution_combo, width=LayoutTokens.FIELD_LG
        )
        configure_control(self.sweep_params_combo, width=LayoutTokens.FIELD_LG)
        configure_control(self.sweep_period_combo, width=LayoutTokens.FIELD_XL)

    def _settings_card(self) -> QFrame:
        frame = card(None)
        self.settings_frame = frame
        configure_layout(
            frame.layout(),
            margins=(14, 8, 14, 8),
            spacing=4,
        )

        inputs_layout = QGridLayout()
        self.settings_input_layout = inputs_layout
        configure_layout(
            inputs_layout,
            margins=(0, 0, 0, 0),
            spacing=LayoutTokens.SPACE_2,
        )
        frame.layout().addLayout(inputs_layout)

        def create_form_label(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setObjectName("FormLabel")
            lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            return lbl

        self.symbol_summary = QLabel("EUR/USD")
        self.symbol_summary.setObjectName("ConditionBadge")
        self.symbol_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.symbol_summary.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred
        )
        self.symbol_summary.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.symbol_button = action_button("🔍 Chọn", primary=True, color="info")
        self._configure_compact_button(self.symbol_button)
        self.symbol_button.clicked.connect(self._show_symbol_dialog)

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

        for field in (self.start_date, self.end_date, self.balance_input, self.risk_input):
            field.setObjectName("FilterField")
            field.setSizePolicy(
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred
            )

        self.purpose_combo = QComboBox()
        self.purpose_combo.setObjectName("FilterField")
        self.purpose_combo.addItem("Nghiên cứu", BACKTEST_PURPOSE_RESEARCH)
        self.purpose_combo.addItem("Kiểm chứng", BACKTEST_PURPOSE_VALIDATION)
        self.purpose_combo.setToolTip(
            "Nghiên cứu tạo kết quả RESEARCH_ONLY. Kiểm chứng tự động chạy "
            "IS/OOS và Walk-Forward để tạo đủ bằng chứng backtest."
        )
        self.purpose_combo.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred
        )
        self.purpose_combo.currentIndexChanged.connect(
            self._sync_backtest_mode_ui
        )

        self.mode_summary_label = QLabel("MT5 • Chỉ nghiên cứu")
        self.mode_summary_label.setObjectName("HelperText")
        self.mode_summary_label.setToolTip(
            "Luồng thông thường luôn dùng mô phỏng chi phí MT5. Nghiên cứu "
            "nhanh chỉ có trong tab Nghiên cứu nâng cao."
        )
        self.mode_summary_label.setWordWrap(False)
        self.mode_summary_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        self.mode_summary_label.setFixedWidth(0)

        self.run_button = action_button("▶️ Chạy", primary=True, color="success")
        self._configure_compact_button(self.run_button)
        self.run_button.clicked.connect(self._run_backtest)

        self.cancel_backtest_btn = action_button("Hủy", primary=False, color="danger")
        self._configure_compact_button(self.cancel_backtest_btn)
        self.cancel_backtest_btn.clicked.connect(self._cancel_backtest)
        self.cancel_backtest_btn.hide()
        
        self.apply_config_btn = action_button("📋 Áp dụng cấu hình", primary=True, color="warning")
        self._configure_compact_button(self.apply_config_btn)
        self.apply_config_btn.clicked.connect(self._apply_scanner_config)
        self.apply_config_btn.setToolTip("Phân tích kết quả backtest và áp dụng cấu hình đề xuất vào Scanner settings.")
        self.apply_config_btn.hide()

        actions_group = QHBoxLayout()
        configure_layout(actions_group, margins=(0, 0, 0, 0), spacing=LayoutTokens.SPACE_2)
        actions_group.addWidget(self.run_button)
        actions_group.addWidget(self.cancel_backtest_btn)
        actions_group.addWidget(self.apply_config_btn)

        configuration_fields = QHBoxLayout()
        configure_layout(
            configuration_fields,
            margins=(0, 0, 0, 0),
            spacing=LayoutTokens.SPACE_2,
        )
        configuration_fields.addWidget(create_form_label("Mã:"))
        configuration_fields.addWidget(self.symbol_summary)
        configuration_fields.addWidget(self.symbol_button)
        configuration_fields.addWidget(create_form_label("Vốn:"))
        configuration_fields.addWidget(self.balance_input)
        configuration_fields.addWidget(create_form_label("Từ:"))
        configuration_fields.addWidget(self.start_date)
        configuration_fields.addWidget(create_form_label("Đến:"))
        configuration_fields.addWidget(self.end_date)
        configuration_fields.addWidget(create_form_label("Rủi ro:"))
        configuration_fields.addWidget(self.risk_input)
        configuration_fields.addWidget(create_form_label("Mục đích:"))
        configuration_fields.addWidget(self.purpose_combo)
        configuration_fields.addWidget(self.mode_summary_label)
        configuration_fields.addStretch(1)

        self.configuration_fields_layout = configuration_fields
        inputs_layout.addLayout(configuration_fields, 0, 0)

        # Row 2: Progress — chiếm 100% chiều rộng
        progress_row = QHBoxLayout()
        configure_layout(progress_row, spacing=LayoutTokens.SPACE_3)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("0%")
        self.progress.setTextVisible(True)
        self.progress.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        configure_progress(self.progress)
        progress_row.addWidget(self.progress, 1)
        progress_row.addLayout(actions_group)

        frame.layout().addLayout(progress_row)

        # Hidden labels — kept as instance vars for test/logic compat,
        # not added to any visible layout.
        self.status_label = QLabel("Sẵn sàng")
        self.status_label.setObjectName("HelperText")
        self.status_label.setWordWrap(True)
        self.status_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
        )
        self.status_label.hide()

        # Row 3: Results Display
        results_row = QHBoxLayout()
        configure_layout(results_row, spacing=LayoutTokens.SPACE_2)
        results_row.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        frame.layout().addLayout(results_row)

        results_label = create_form_label("Kết quả:")
        results_label.setObjectName("PanelTitle")
        results_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        results_row.addWidget(results_label, 0, Qt.AlignmentFlag.AlignVCenter)

        self.summary_row = QHBoxLayout()
        configure_layout(self.summary_row, spacing=LayoutTokens.SPACE_2)
        self.summary_row.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        results_row.addLayout(self.summary_row)
        results_row.addStretch(1)
        self._set_summary({})

        self.snapshot_label = QLabel("")
        self.snapshot_label.setObjectName("HelperText")
        self.snapshot_label.setWordWrap(True)
        self.snapshot_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.snapshot_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.snapshot_label.hide()
        frame.layout().addWidget(self.snapshot_label)
        return frame

    def _stat_cell(self, title: str, value: str, tone: str | None = None) -> QFrame:
        frame = QFrame()
        frame.setObjectName("MiniStatCompact")
        frame.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        layout = QHBoxLayout(frame)
        configure_layout(
            layout,
            margins=(0, 0, 0, 0),
            spacing=LayoutTokens.SPACE_1,
        )
        layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        title_label = QLabel(f"{title}:")
        title_label.setObjectName("MiniStatTitleCompact")
        title_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        value_label = QLabel(value)
        value_label.setObjectName("MiniStatValueCompact")
        value_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        if tone:
            value_label.setProperty("metricTone", tone)
        layout.addWidget(title_label, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(value_label, 0, Qt.AlignmentFlag.AlignVCenter)
        return frame

    def _vertical_separator(self) -> QFrame:
        line = QFrame()
        line.setObjectName("VerticalSeparator")
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setLineWidth(1)
        return line

    @staticmethod
    def _configure_compact_button(button: QPushButton) -> None:
        configure_button(button)

    def _trades_card(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("PanelCard")
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(frame)
        configure_layout(
            layout,
            margins=LayoutTokens.CARD_MARGIN,
            spacing=LayoutTokens.SPACE_2,
        )

        # --- Verdict banner (hidden until backtest) ---
        self.verdict_banner = QLabel("")
        self.verdict_banner.setObjectName("BacktestVerdict")
        self.verdict_banner.setWordWrap(True)
        self.verdict_banner.setTextFormat(Qt.TextFormat.RichText)
        self.verdict_banner.hide()
        layout.addWidget(self.verdict_banner)

        # --- Tab widget: Kết quả | Đường cong vốn | Danh sách lệnh ---
        self.tabs = QTabWidget()
        self.tabs.setObjectName("BacktestTabs")
        self.tabs.tabBar().setObjectName("BacktestTabBar")

        # Keep the main result area focused on reviewing existing results.
        # AI analysis is an optional research tool and lives in the advanced tab.
        corner_widget = QWidget()
        corner_layout = QHBoxLayout(corner_widget)
        configure_layout(corner_layout, spacing=LayoutTokens.SPACE_2)

        load_btn = action_button("📂 Mở kết quả", primary=True, color="success")
        self.load_result_button = load_btn
        self._configure_compact_button(load_btn)
        load_btn.setToolTip("Mở lại một file kết quả backtest đã lưu")
        load_btn.clicked.connect(self._load_backtest_file)

        corner_layout.addWidget(load_btn)
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
        configure_table(self.table)
        self.table.setHorizontalHeaderLabels([label for _, label in self.TRADE_COLUMNS])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.table.viewport().installEventFilter(self)
        self._apply_trade_table_layout()
        self.tabs.addTab(self.table, "📋 Lệnh")

        # Tab 3: Điều chỉnh tham số (Param Sensitivity)
        self._build_param_tuning_tab()
        self.tabs.addTab(self._sweep_tab, "🧪 Nghiên cứu nâng cao")

        layout.addWidget(self.tabs, 1)
        return frame

    def _setup_equity_tab(self) -> None:
        self._equity_tab = QWidget()
        layout = QVBoxLayout(self._equity_tab)
        configure_layout(layout, spacing=0)
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
        self._equity_figure = Figure(
            tight_layout=True,
            facecolor=current_palette().background,
        )
        apply_figure_theme(self._equity_figure)
        self._equity_canvas = FigureCanvas(self._equity_figure)
        self._equity_canvas.setObjectName("MatplotlibCanvas")
        self._equity_canvas.setMinimumHeight(LayoutTokens.CHART_MIN_HEIGHT)
        layout.addWidget(self._equity_canvas)
        self._refresh_equity_curve()

    # ── Param Tuning Tab ─────────────────────────────────────────────────

    def _build_param_tuning_tab(self) -> None:
        """Dựng khu vực nghiên cứu nâng cao và điều chỉnh tham số."""
        container = QWidget()
        layout = QVBoxLayout(container)
        configure_layout(layout, spacing=LayoutTokens.SPACE_2)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMinimumWidth(0)
        scroll.setWidget(container)
        self._sweep_tab = scroll

        controls_row = QHBoxLayout()
        configure_layout(controls_row, spacing=LayoutTokens.SPACE_2)
        layout.addLayout(controls_row)

        research_card = card("Nghiên cứu nâng cao")
        self.research_card = research_card
        configure_layout(
            research_card.layout(),
            margins=(14, 8, 14, 8),
            spacing=4,
        )
        controls_row.addWidget(research_card, 1)

        advanced_row = QGridLayout()
        self.advanced_options_grid = advanced_row
        configure_layout(advanced_row, spacing=4)
        advanced_row.setHorizontalSpacing(10)
        advanced_row.setVerticalSpacing(4)
        advanced_row.setColumnStretch(1, 1)

        advanced_label = QLabel("Chế độ:")
        advanced_label.setObjectName("FormLabel")
        advanced_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        advanced_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        advanced_row.addWidget(advanced_label, 0, 0)

        self.advanced_execution_combo = QComboBox()
        self.advanced_execution_combo.setObjectName("FilterField")
        self.advanced_execution_combo.addItem(
            "MT5 parity", EXECUTION_MODE_PARITY
        )
        self.advanced_execution_combo.addItem(
            "Research nhanh", EXECUTION_MODE_RESEARCH
        )
        self.advanced_execution_combo.setToolTip(
            "Nghiên cứu nhanh bỏ mô hình chi phí execution-parity và luôn là "
            "RESEARCH_ONLY. Kiểm chứng không cho phép chế độ này."
        )
        self.advanced_execution_combo.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred
        )
        self.advanced_execution_combo.currentIndexChanged.connect(
            self._sync_backtest_mode_ui
        )

        self.research_validation_checkbox = QCheckBox(
            "IS/OOS + Walk-Forward"
        )
        configure_checkbox(self.research_validation_checkbox)
        self.research_validation_checkbox.setToolTip(
            "Chỉ là phân tích bổ sung cho Research; không biến kết quả thành "
            "config có thể phát hành. Validation luôn tự chạy hai bước này."
        )

        self.analyze_btn = action_button(
            "🤖 Phân tích AI", primary=True, color="info"
        )
        self._configure_compact_button(self.analyze_btn)
        self.analyze_btn.setToolTip(
            "Phân tích kết quả đang hiển thị. Đây là công cụ nghiên cứu, không phát hành cấu hình."
        )
        self.analyze_btn.clicked.connect(self._analyze_loaded_result)

        # Row 0: Chế độ — label + combobox CÙNG HÀNG
        advanced_row.addWidget(self.advanced_execution_combo, 0, 1, Qt.AlignmentFlag.AlignLeft)

        # Row 1: Tùy chọn — label + 4 checkboxes dạng lưới 2x2 CÙNG HÀNG
        options_label = QLabel("Tùy chọn:")
        options_label.setObjectName("FormLabel")
        options_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        options_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        advanced_row.addWidget(options_label, 1, 0, Qt.AlignmentFlag.AlignTop)

        self.portfolio_mode_checkbox = QCheckBox(
            "Đánh giá danh mục nhiều mã"
        )
        configure_checkbox(self.portfolio_mode_checkbox)
        self.portfolio_mode_checkbox.setToolTip(
            "Chỉ dùng cho Research. Kết quả danh mục luôn RESEARCH_ONLY và không thể áp cấu hình cho một mã."
        )
        self.portfolio_mode_checkbox.stateChanged.connect(
            self._sync_backtest_mode_ui
        )

        self.monte_carlo_checkbox = QCheckBox(
            "Chạy Monte Carlo"
        )
        configure_checkbox(self.monte_carlo_checkbox)
        self.monte_carlo_checkbox.setToolTip(
            "Nếu không chọn, Monte Carlo chỉ tự chạy khi có ít nhất 30 lệnh."
        )

        self.sweep_all_symbols_checkbox = QCheckBox(
            "Quét tất cả mã đã chọn"
        )
        configure_checkbox(self.sweep_all_symbols_checkbox)
        self.sweep_all_symbols_checkbox.setToolTip(
            "Mặc định sweep chỉ chạy mã chính; bật tùy chọn này để chạy toàn bộ các mã đã chọn."
        )

        checkbox_grid = QGridLayout()
        checkbox_grid.setSpacing(4)
        checkbox_grid.addWidget(self.research_validation_checkbox, 0, 0)
        checkbox_grid.addWidget(self.portfolio_mode_checkbox, 1, 0)
        checkbox_grid.addWidget(self.monte_carlo_checkbox, 2, 0)
        checkbox_grid.addWidget(self.sweep_all_symbols_checkbox, 3, 0)
        advanced_row.addLayout(checkbox_grid, 1, 1, Qt.AlignmentFlag.AlignLeft)

        # Row 2: Nút Phân tích AI — riêng 1 hàng dưới cùng
        advanced_row.addWidget(self.analyze_btn, 2, 1, Qt.AlignmentFlag.AlignLeft)

        research_card.layout().addLayout(advanced_row)
        research_card.layout().addStretch(1)

        self._sync_backtest_mode_ui()

        # ── Sweep controls ──
        sweep_card = card("Quét độ nhạy tham số")
        self.sweep_card = sweep_card
        configure_layout(
            sweep_card.layout(),
            margins=(14, 8, 14, 8),
            spacing=4,
        )
        controls_row.addWidget(sweep_card, 1)

        form_row = QGridLayout()
        self.sweep_controls_grid = form_row
        configure_layout(form_row, spacing=4)
        form_row.setHorizontalSpacing(10)
        form_row.setVerticalSpacing(4)
        form_row.setColumnStretch(1, 1)

        # Nhãn + combobox chọn bộ tham số
        params_label = QLabel("Tham số:")
        params_label.setObjectName("FormLabel")
        params_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        params_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        form_row.addWidget(params_label, 0, 0)

        self.sweep_params_combo = QComboBox()
        self.sweep_params_combo.setObjectName("FilterField")
        self.sweep_params_combo.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred
        )
        self.sweep_params_combo.addItem("4 ưu tiên", "priority4")
        self.sweep_params_combo.addItem("6 ưu tiên", "priority6")
        self.sweep_params_combo.addItem("Tất cả 10", "all")
        self.sweep_params_combo.setCurrentIndex(0)

        params_control_row = QHBoxLayout()
        configure_layout(params_control_row, spacing=4)
        params_control_row.addWidget(self.sweep_params_combo)
        params_control_row.addWidget(self._help_button(
            "Chọn bộ tham số cần quét:\n"
            "• 4 tham số ưu tiên: SL distance, Zone SL buffer, Entry aggressiveness, TP selection\n"
            "• 6 tham số: thêm Swing SL buffer, SL Floor buffer\n"
            "• Tất cả: bao gồm cả secondary params (EQ TP max RR, TP2 min gap, Entry zone ATR, Min stop distance)"
        ))
        params_control_row.addStretch(1)
        form_row.addLayout(params_control_row, 0, 1)

        # Nhãn + combobox chọn giai đoạn
        period_label = QLabel("Giai đoạn:")
        period_label.setObjectName("FormLabel")
        period_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        period_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        form_row.addWidget(period_label, 1, 0)

        self.sweep_period_combo = QComboBox()
        self.sweep_period_combo.setObjectName("FilterField")
        self.sweep_period_combo.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred
        )
        self.sweep_period_combo.addItem("Ngày đang chọn", "selected")
        self.sweep_period_combo.addItem("Tất cả mẫu", "all")
        for p in DEFAULT_PERIODS:
            self.sweep_period_combo.addItem(p.name, p.name)
        self.sweep_period_combo.setCurrentIndex(0)

        period_control_row = QHBoxLayout()
        configure_layout(period_control_row, spacing=4)
        period_control_row.addWidget(self.sweep_period_combo)
        period_control_row.addWidget(self._help_button(
            "Mặc định dùng đúng khoảng ngày trên form Backtest chính. Hoặc chọn giai đoạn mẫu để nghiên cứu:\n"
            "• Trending 2023: thị trường có xu hướng rõ ràng\n"
            "• Range 2024: thị trường đi ngang, ít xu hướng\n"
            "• Volatile 2025: thị trường biến động cao (tariff news)\n"
            "• Mixed Full 2024: cả năm, đủ mọi chế độ\n"
            "• Tất cả: quét qua tất cả giai đoạn"
        ))
        period_control_row.addStretch(1)
        form_row.addLayout(period_control_row, 1, 1)

        # Nút chạy
        self.sweep_run_btn = action_button("▶️ Chạy quét", primary=True, color="success")
        self._configure_compact_button(self.sweep_run_btn)
        self.sweep_run_btn.clicked.connect(self._run_param_sweep)
        actions_label = QLabel("Thao tác:")
        actions_label.setObjectName("FormLabel")
        actions_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        actions_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        form_row.addWidget(actions_label, 2, 0)
        sweep_actions = QHBoxLayout()
        configure_layout(sweep_actions, spacing=LayoutTokens.SPACE_2)
        sweep_actions.addWidget(self.sweep_run_btn)

        self.sweep_cancel_btn = action_button("Hủy", primary=False, color="danger")
        self._configure_compact_button(self.sweep_cancel_btn)
        self.sweep_cancel_btn.clicked.connect(self._cancel_param_sweep)
        self.sweep_cancel_btn.hide()
        sweep_actions.addWidget(self.sweep_cancel_btn)

        # Nút mở báo cáo HTML
        self.sweep_report_btn = action_button("📂 Mở báo cáo", primary=True, color="info")
        self._configure_compact_button(self.sweep_report_btn)
        self.sweep_report_btn.clicked.connect(self._open_sweep_report)
        self.sweep_report_btn.hide()
        sweep_actions.addWidget(self.sweep_report_btn)

        sweep_actions.addWidget(self._help_button(
            "Quét (sweep) từng hằng số ATR qua nhiều giá trị khác nhau, "
            "chạy backtest trên mỗi tổ hợp để đo độ ổn định.\n\n"
            "STABLE = giá trị hiện tại tốt trên mọi giai đoạn.\n"
            "OVERFIT = mỗi giai đoạn tối ưu ở 1 giá trị khác nhau → cần chọn giá trị an toàn.\n"
            "INSENSITIVE = tham số ít ảnh hưởng → không cần ưu tiên."
        ))
        sweep_actions.addStretch(1)
        form_row.addLayout(
            sweep_actions,
            2,
            1,
            1,
            2,
            Qt.AlignmentFlag.AlignLeft,
        )

        sweep_card.layout().addLayout(form_row)

        # ── Progress ──
        progress_row = QHBoxLayout()
        configure_layout(progress_row, spacing=LayoutTokens.SPACE_2)
        self.sweep_progress = QProgressBar()
        self.sweep_progress.setRange(0, 100)
        self.sweep_progress.setValue(0)
        configure_progress(self.sweep_progress)
        progress_row.addWidget(self.sweep_progress, 1)

        self.sweep_status = QLabel("Sẵn sàng")
        self.sweep_status.setObjectName("HelperText")
        self.sweep_status.setWordWrap(True)
        self.sweep_status.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.sweep_status.hide()
        sweep_card.layout().addLayout(progress_row)
        sweep_card.layout().addStretch(1)


        # ── Results ──
        self.sweep_result_text = QTextEdit()
        self.sweep_result_text.setReadOnly(True)
        self.sweep_result_text.setObjectName("BacktestResultText")
        set_rich_html(
            self.sweep_result_text,
            empty_state_html(
                "Chọn tham số và bấm ▶️ Chạy quét để bắt đầu."
            ),
        )
        layout.addWidget(self.sweep_result_text, 1)

    @staticmethod
    def _help_button(tooltip: str) -> QPushButton:
        """Tạo nút '?' tròn nhỏ — bấm vào hiện popup giải thích."""
        from ui.screens.shared import HelpButton
        button = HelpButton(tooltip)
        configure_help_button(button)
        return button

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
            if period_key == "selected":
                start = self._qdate_to_utc_start(self.start_date.date())
                end = self._qdate_to_utc_end(self.end_date.date())
                periods = [MarketPeriod(
                    "Khoảng ngày đã chọn",
                    start.date().isoformat(),
                    end.date().isoformat(),
                    "user_selected",
                )]
            elif period_key == "all":
                periods = list(DEFAULT_PERIODS)
            else:
                periods = [p for p in DEFAULT_PERIODS if p.name == period_key]

            # Symbol từ form chính
            symbols = (
                list(self.selected_symbols)
                if self.sweep_all_symbols_checkbox.isChecked()
                else [self.selected_symbol]
            )

            # Settings
            settings = self._get_sweep_settings()
            start = self._qdate_to_utc_start(self.start_date.date())
            end = self._qdate_to_utc_end(self.end_date.date())
            templates = self.controller.build_requests(
                symbols=symbols,
                start=start,
                end=end,
                initial_balance=self.balance_input.value(),
                risk_percent=self.risk_input.value(),
                purpose=BACKTEST_PURPOSE_RESEARCH,
                execution_mode=self._selected_execution_mode(
                    BACKTEST_PURPOSE_RESEARCH
                ),
            )
            request_templates = {
                request.symbol: request for request in templates
            }

            # UI state
            self.sweep_run_btn.setEnabled(False)
            self.sweep_run_btn.setText("⏳ Đang chạy...")
            self.sweep_cancel_btn.setEnabled(True)
            self.sweep_cancel_btn.show()
            self.sweep_report_btn.hide()
            self.sweep_progress.setValue(0)
            self.sweep_status.setText("Đang khởi động...")
            set_rich_html(
                self.sweep_result_text,
                empty_state_html("Đang chạy... vui lòng đợi."),
            )

            # Worker + thread
            from workers.param_sweep_worker import ParamSweepThread

            self._sweep_thread = ParamSweepThread(
                configs,
                periods,
                symbols,
                settings,
                request_templates=request_templates,
            )
            self._sweep_thread.progress.connect(self._on_sweep_progress)
            self._sweep_thread.succeeded.connect(self._on_sweep_success)
            self._sweep_thread.failed.connect(self._on_sweep_failed)
            self._sweep_thread.cancelled.connect(self._on_sweep_cancelled)
            self._sweep_thread.finished.connect(lambda: self.sweep_run_btn.setEnabled(True))
            self._sweep_thread.finished.connect(lambda: self.sweep_run_btn.setText("▶️ Chạy quét"))
            self._sweep_thread.finished.connect(self.sweep_cancel_btn.hide)
            self._sweep_thread.finished.connect(self._sweep_thread.deleteLater)

            self._sweep_thread.start()

        except Exception as exc:
            import traceback
            self.sweep_status.setText(f"Lỗi khởi động: {exc}")
            self.sweep_run_btn.setEnabled(True)
            self.sweep_run_btn.setText("▶️ Chạy quét")
            QMessageBox.critical(
                self, "Lỗi quét tham số",
                f"Không thể khởi động quét tham số:\n\n{exc}\n\n{traceback.format_exc()}",
            )

    def _on_sweep_progress(self, percent: int, message: str) -> None:
        self.sweep_progress.setValue(percent)
        self.sweep_status.setText(message)

    def _cancel_param_sweep(self) -> None:
        thread = getattr(self, "_sweep_thread", None)
        if thread is not None:
            self.sweep_cancel_btn.setEnabled(False)
            self.sweep_status.setText("Đang hủy process sweep...")
            thread.cancel()

    def _on_sweep_cancelled(self, message: str) -> None:
        self.sweep_status.setText(message)
        QMessageBox.information(self, "Đã hủy", message)

    def _on_sweep_success(self, results: list) -> None:
        self._sweep_results = results
        self.sweep_status.setText("Hoàn tất quét tham số.")
        html = self._build_sweep_results_html(results)
        set_rich_html(self.sweep_result_text, html)

        # Export báo cáo ra file
        try:
            report_path = export_results(results)
            self._sweep_report_path = str(report_path)
            self.sweep_report_btn.show()
        except Exception:
            self._sweep_report_path = None

    def _on_sweep_failed(self, error_msg: str) -> None:
        self.sweep_status.setText(f"Lỗi: {error_msg}")
        set_rich_html(
            self.sweep_result_text,
            empty_state_html(
                f"Lỗi khi quét tham số: {error_msg}",
                tone="danger",
            ),
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
                <td style="max-width:420px;{QSS_BODY}">{rec_text}</td>
            </tr>"""

        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head><body style="{QSS_BODY}margin:0;color:#1f2937">
<h3 style="margin:0 0 8px;{QSS_SUBTITLE}">Quét tham số</h3>
<table style="border-collapse:collapse;width:100%;{QSS_BODY}">
<thead><tr style="background:#f5f5f5">
    <th style="padding:6px 10px;text-align:left;border:1px solid #ddd">Biến</th>
    <th style="padding:6px 10px;text-align:left;border:1px solid #ddd">JSON Key</th>
    <th style="padding:6px 10px;text-align:center;border:1px solid #ddd">Hiện tại</th>
    <th style="padding:6px 10px;text-align:center;border:1px solid #ddd">Đề xuất</th>
    <th style="padding:6px 10px;text-align:center;border:1px solid #ddd">Đánh giá</th>
    <th style="padding:6px 10px;text-align:center;border:1px solid #ddd">Ổn định</th>
    <th style="padding:6px 10px;text-align:left;border:1px solid #ddd">Khuyến nghị</th>
</tr></thead><tbody>{rows_html}</tbody></table>
<p style="color:#94a3b8;{QSS_SMALL}margin-top:12px">
<b>STABLE</b> = giữ nguyên &nbsp;|&nbsp;
<b>OVERFIT</b> = đổi sang giá trị an toàn &nbsp;|&nbsp;
<b>INSENSITIVE</b> = không cần tối ưu<br>
Bấm <b>📂 Mở báo cáo</b> để xem bảng chi tiết từng giá trị × từng giai đoạn.
</p>
</body></html>"""

    def _refresh_equity_curve(self) -> None:
        if not hasattr(self, '_equity_canvas') or self._equity_canvas is None:
            return
        equity_curve = self.result.get("equity_curve", []) if self.result else []
        if not isinstance(equity_curve, list):
            equity_curve = []
        self._equity_figure.clear()
        colors = apply_figure_theme(self._equity_figure)
        ax = self._equity_figure.add_subplot(111)
        fg = colors["text"]
        grid_c = colors["grid"]
        apply_axes_theme(ax, colors)
        if not self.result:
            ax.text(0.5, 0.5, 'Chưa có kết quả backtest để vẽ biểu đồ',
                    transform=ax.transAxes, ha='center', va='center',
                    color=colors["neutral"], fontsize=12)
            ax.set_xticks([])
            ax.set_yticks([])
        elif len(equity_curve) < 2:
            ax.text(0.5, 0.5, 'Không đủ dữ liệu để vẽ biểu đồ',
                    transform=ax.transAxes, ha='center', va='center',
                    color=colors["neutral"], fontsize=12)
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
            ax.plot(
                times,
                cum_r,
                color=colors["equity"],
                linewidth=2,
                label='Cumulative R',
            )
            ax.fill_between(times, [0] * len(dd_r), dd_r,
                            color=colors["drawdown"], alpha=0.2,
                            label='Drawdown R')
            ax.axhline(y=0, color=grid_c, linewidth=0.5)
            legend = ax.legend(loc='upper left', fontsize=9)
            apply_legend_theme(legend, colors)
        ax.tick_params(colors=fg, labelsize=9)
        ax.set_ylabel('R', color=fg)
        ax.grid(True, color=grid_c, linewidth=0.5, alpha=0.5)
        apply_axes_theme(ax, colors)
        if len(equity_curve) >= 2:
            self._equity_figure.autofmt_xdate()
        self._equity_canvas.draw()

    def _refresh_result_text(self) -> None:
        if not self.result:
            set_rich_html(self.result_text, "")
            return
        self._analysis_light = self._is_light_theme()
        try:
            html = self._generate_stats_html()
            set_rich_html(self.result_text, html)
        except Exception:
            set_rich_html(
                self.result_text,
                empty_state_html(
                    "Không thể hiển thị kết quả.",
                    tone="danger",
                ),
            )

    def _load_backtest_file(self) -> None:
        from PyQt6.QtWidgets import QApplication
        from config.paths import app_data_dir
        default_dir = app_data_dir() / "backtests"
        default_dir.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(
            self, "Tải file backtest", str(default_dir),
            "Tệp JSON (*.json);;Tất cả tệp (*)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return
        try:
            import json
            raw_data = json.loads(Path(path).read_text(encoding="utf-8"))
            data = migrate_snapshot_payload(raw_data, source_path=path)
            summary = data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}
            trades = data.get("trades", []) if isinstance(data.get("trades"), list) else []
            self.result = data
            self._sync_symbols_from_result(data)
            self._set_summary(summary)
            self._set_trades(trades)
            self._update_verdict()
            lifecycle = (
                data.get("lifecycle")
                if isinstance(data.get("lifecycle"), dict)
                else {}
            )
            legacy = lifecycle.get("status") == LEGACY_RESEARCH
            self._update_result_action()
            contract = (
                data.get("backtest_contract")
                if isinstance(data.get("backtest_contract"), dict)
                else {}
            )
            result_kind = (
                "legacy - chỉ xem/phân tích, phải chạy lại bằng engine mới"
                if legacy
                else (
                    "validation"
                    if contract.get("validation_eligible") is True
                    else "nghiên cứu"
                )
            )
            lifecycle_label = lifecycle_status_label(lifecycle.get("status"))
            reason_text = " ".join(
                lifecycle_reason_labels(lifecycle.get("reasons"))
            )
            status = f"Đã tải {len(trades)} lệnh — {result_kind}. {lifecycle_label}."
            if reason_text:
                status += f" {reason_text}"
            self.status_label.setText(status)
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

        self._analysis_light = self._is_light_theme()

        self.analyze_btn.setText("⏳ Đang phân tích")
        self.analyze_btn.setEnabled(False)

        prompt = self._build_analysis_prompt()
        config = AIProviderConfig(provider=active.provider, model=active.model, api_key=active.api_key, base_url=active.base_url)
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
            self.analyze_btn.setText("🤖 Phân tích AI")
            self.analyze_btn.setEnabled(True)
            self._ai_thread.quit()
            self._ai_thread.wait()
            return

        try:
            light = self.__dict__.get('_analysis_light', False)

            dlg = QDialog(self)
            dlg.setWindowTitle("Phân tích kết quả backtest")
            dlg.setObjectName("BacktestAnalysisDialog")
            configure_dialog(
                dlg,
                minimum_width=LayoutTokens.DIALOG_MD_WIDTH,
                minimum_height=LayoutTokens.DIALOG_MD_HEIGHT,
            )
            layout = QVBoxLayout(dlg)
            configure_layout(
                layout,
                margins=LayoutTokens.DIALOG_MARGIN,
                spacing=LayoutTokens.SPACE_3,
            )

            text = QTextEdit()
            text.setObjectName("BacktestAnalysisText")
            text.setReadOnly(True)

            stats_html = self._generate_stats_html()
            ai_html = self._format_ai_to_html(response, light)

            hr_color = "#cbd5e1" if light else "#334155"
            header_color = "#c2410c" if light else "#f59e0b"
            final_html = (
                f"{stats_html}"
                f"<div style='margin:20px 0;border-top:1px dashed {hr_color};'></div>"
                f'<h2 style="color:{header_color};margin:0 0 10px 0;{QSS_SUBTITLE}">AI Nhận xét & Khuyến nghị</h2>'
                f"{ai_html}"
            )

            set_rich_html(
                text,
                final_html,
                theme="light" if light else "dark",
            )
            layout.addWidget(text, 1)

            close_btn = action_button("Đóng")
            configure_button(close_btn)
            close_btn.clicked.connect(dlg.accept)
            btn_row = QHBoxLayout()
            configure_layout(btn_row, spacing=LayoutTokens.SPACE_2)
            btn_row.addStretch()
            btn_row.addWidget(close_btn)
            layout.addLayout(btn_row)
            dlg.exec()
        finally:
            self.analyze_btn.setText("🤖 Phân tích AI")
            self.analyze_btn.setEnabled(True)
            self._ai_thread.quit()
            self._ai_thread.wait()

    def _on_ai_analysis_error(self, error_msg: str) -> None:
        if len(error_msg) > 500:
            error_msg = error_msg[:500] + "..."
        QMessageBox.warning(self, "Lỗi phân tích", error_msg)
        self.analyze_btn.setText("🤖 Phân tích AI")
        self.analyze_btn.setEnabled(True)
        self._ai_thread.quit()
        self._ai_thread.wait()

    def _apply_scanner_config(self) -> None:
        """Save a draft or apply a validated single-symbol config safely."""
        if not self.result:
            QMessageBox.information(self, "Đề xuất", "Chưa có dữ liệu backtest. Hãy chạy backtest hoặc tải file trước.")
            return

        action = result_action(
            self.result,
            selected_symbol=self.selected_symbol,
        )
        if not action.visible:
            QMessageBox.information(
                self,
                "Không thể dùng kết quả này",
                "Kết quả hiện tại chỉ dùng để xem hoặc nghiên cứu, hoặc mã trên "
                "màn hình không khớp với mã trong snapshot.",
            )
            self._update_result_action()
            return

        from core.backtest_config_validation import build_backtest_config

        try:
            config = build_backtest_config(
                self.result,
                symbol=self.selected_symbol,
            )
            recs = {self.selected_symbol: config}
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

        light = self._is_light_theme()

        if light:
            text_color = "#1c1917"
            muted_color = "#78716c"
            border_color = "#e7e5e4"
            title_color = "#c2410c"
            current_color = "#57534e"
            proposed_color = "#ea580c"
            evidence_color = "#78716c"
        else:
            text_color = "#ebdcd0"
            muted_color = "#a8a29e"
            border_color = "#3f2c25"
            title_color = "#f97316"
            current_color = "#d6d3d1"
            proposed_color = "#fb923c"
            evidence_color = "#a8a29e"

        dlg = QDialog(self)
        dlg.setWindowTitle(action.label.replace("📋 ", "").replace("💾 ", ""))
        dlg.setObjectName("BacktestConfigDialog")
        configure_dialog(
            dlg,
            minimum_width=LayoutTokens.DIALOG_LG_WIDTH,
            minimum_height=320,
        )
        dlg_layout = QVBoxLayout(dlg)
        configure_layout(
            dlg_layout,
            margins=LayoutTokens.DIALOG_MARGIN,
            spacing=LayoutTokens.SPACE_3,
        )

        title_widget = QLabel("")
        title_widget.setTextFormat(Qt.TextFormat.RichText)
        title_widget.setText(
            f'<h2 style="color:{title_color};margin:0 0 6px;{QSS_TITLE}">'
            f"Cấu hình Scanner cho {self.selected_symbol}</h2>"
            f'<p style="color:{muted_color};{QSS_BODY}margin:0;">'
            "So sánh cấu hình hiện tại trong Settings với đề xuất từ kết quả backtest."
            "</p>"
        )
        dlg_layout.addWidget(title_widget)

        symbol = self.selected_symbol
        existing = settings.trading.symbol_settings.get(symbol)
        cfg = recs.get(symbol)

        if cfg is None:
            no_data = QLabel(
                f'<span style="color:{muted_color};{QSS_BODY}">'
                f"{symbol}: không đủ dữ liệu để đề xuất "
                f"(cần ≥18 lệnh; hãy chạy mục đích Kiểm chứng để hệ thống tự "
                f"tạo IS/OOS và Walk-Forward)</span>"
            )
            no_data.setTextFormat(Qt.TextFormat.RichText)
            dlg_layout.addWidget(no_data)
        else:
            evidence = cfg.get("_evidence", "")
            current_regime = existing.auto_trade_regime if existing else "--"
            current_side = existing.auto_trade_side if existing else "--"
            current_score = str(existing.min_score) if existing else "--"
            current_rr = f"{existing.min_expected_rr:.1f}" if existing else "--"

            table = QTableWidget(4, 2)
            configure_table(table)
            table.horizontalHeader().setVisible(False)
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
            table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            
            rows = [
                ("Cấu hình hiện tại",
                 f'<span style="color:{current_color}; {QSS_BODY}">'
                 f"<b>Regime:</b> {current_regime} &nbsp;&nbsp;&nbsp; "
                 f"<b>Side:</b> {current_side} &nbsp;&nbsp;&nbsp; "
                 f"<b>MinScore:</b> {current_score} &nbsp;&nbsp;&nbsp; "
                 f"<b>MinRR:</b> {current_rr}</span>"),
                 
                ("Đề xuất từ backtest",
                 f'<span style="color:{proposed_color}; {QSS_SUBTITLE}">'
                 f"<b>Regime:</b> {cfg['regime']} &nbsp;&nbsp;&nbsp; "
                 f"<b>Side:</b> {cfg['side'].upper()} &nbsp;&nbsp;&nbsp; "
                 f"<b>MinScore:</b> {cfg['min_score']} &nbsp;&nbsp;&nbsp; "
                 f"<b>MinRR:</b> {cfg['min_rr']}</span>"),
                 
                ("Bằng chứng", 
                 f'<span style="color:{evidence_color}; {QSS_SMALL} font-style: italic; line-height: 1.4;">'
                 f"{evidence}</span>"),
                (
                    "Trạng thái validation",
                    f'<span style="color:{proposed_color}; {QSS_BODY}">'
                    f"<b>{cfg.get('status', 'DRAFT')}</b>"
                    f" &nbsp; OOS: {cfg.get('out_of_sample_trades', 0)} lệnh"
                    f" &nbsp; WF: {cfg.get('walk_forward_windows', 0)} cửa sổ"
                    f"<br><span style='color:{evidence_color};'>"
                    f"{' '.join(lifecycle_reason_labels(cfg.get('validation_reasons', []))) or 'Đủ bằng chứng OOS/Walk-Forward'}"
                    "</span></span>",
                ),
            ]
            
            for row_idx, (label, html_value) in enumerate(rows):
                lbl_title = QLabel(label)
                lbl_title.setObjectName("BacktestConfigRowTitle")
                table.setCellWidget(row_idx, 0, lbl_title)
                
                lbl_val = QLabel(html_value)
                lbl_val.setObjectName("BacktestConfigRowValue")
                lbl_val.setTextFormat(Qt.TextFormat.RichText)
                lbl_val.setWordWrap(True)
                table.setCellWidget(row_idx, 1, lbl_val)
                
            table.resizeRowsToContents()

            header = table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(0, LayoutTokens.FIELD_LG)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

            dlg_layout.addWidget(table, 1)

        btn_row = QHBoxLayout()
        configure_layout(
            btn_row,
            margins=(0, LayoutTokens.SPACE_2, 0, 0),
            spacing=LayoutTokens.SPACE_2,
        )
        apply_btn = action_button(action.label, primary=True)
        configure_button(apply_btn)
        config_status = str(cfg.get("status") or "") if isinstance(cfg, dict) else ""
        status_matches_action = (
            action.kind == ACTION_SAVE_DRAFT and config_status == "DRAFT"
        ) or (
            action.kind == ACTION_APPLY_VALIDATED
            and config_status == "VALIDATED"
        )
        apply_btn.setEnabled(cfg is not None and status_matches_action)
        apply_btn.clicked.connect(lambda: self._do_apply_config_direct(cfg, dlg))
        
        cancel_btn = action_button("Hủy")
        configure_button(cancel_btn)
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
        action = result_action(
            self.result,
            selected_symbol=self.selected_symbol,
        )
        config_status = str(cfg.get("status") or "")
        if not action.visible or (
            action.kind == ACTION_SAVE_DRAFT and config_status != "DRAFT"
        ) or (
            action.kind == ACTION_APPLY_VALIDATED
            and config_status != "VALIDATED"
        ):
            QMessageBox.warning(
                self,
                "Không thể lưu cấu hình",
                "Lifecycle của snapshot, mã giao dịch và trạng thái cấu hình "
                "không còn khớp. Hãy tải hoặc chạy lại backtest.",
            )
            self._update_result_action()
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

            apply_validated_backtest_config(
                sym_settings,
                symbol=symbol,
                recommendation=cfg,
            )

            settings.trading.enabled_symbols = reconcile_enabled_symbol(
                settings.trading.enabled_symbols,
                symbol=symbol,
                backtest_active=sym_settings.backtest,
                lifecycle_status=sym_settings.backtest_status,
            )

            if self.app:
                self.app.settings_service.save(settings)
            else:
                self.controller.settings_service.save(settings)

            dlg.accept()
            QMessageBox.information(
                self, "Đã áp dụng",
                f"Đã cập nhật cấu hình Scanner cho {symbol}.\n\n"
                f"Regime: {cfg['regime']}    Side: {cfg['side'].upper()}\n"
                f"MinScore: {cfg['min_score']}    MinRR: {cfg['min_rr']}\n"
                f"Trạng thái: {sym_settings.backtest_status}\n\n"
                + (
                    "Config đã đủ bằng chứng và có thể được Strategy Router sử dụng."
                    if sym_settings.backtest_status == "VALIDATED"
                    else "Config được lưu ở DRAFT và không được phép auto-trade."
                )
            )
        except Exception as exc:
            QMessageBox.warning(self, "Lỗi áp dụng", f"Không thể lưu cấu hình:\n{exc}")

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
                f"gross {s.get('gross_r', s.get('total_r', 0)) or 0:+.1f}R, "
                f"chi phí {s.get('cost_r', 0) or 0:+.1f}R, "
                f"net {s.get('net_r', s.get('total_r', 0)) or 0:+.1f}R"
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

        light = self.__dict__.get('_analysis_light', False)

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
            f'<div style="{QSS_BODY}">',
            f'<h2 style="color:{panel_title_color}; margin-top: 0; margin-bottom: 12px; {QSS_SUBTITLE}">📊 BẢNG KẾT QUẢ TỔNG HỢP</h2>',
        ]
        
        html.extend(self._build_stats_overview_html(
            summary,
            text_color, value_color, muted_color, border_color, row_border,
            get_stat, eval_winrate, eval_profit_factor, eval_drawdown,
        ))

        symbol_stats = self.result.get("symbol_stats", {})
        if isinstance(symbol_stats, dict) and len(symbol_stats) > 1:
            html.append(f'<h2 style="color:{details_title_color}; margin-bottom: 16px; margin-top: 24px; {QSS_SUBTITLE}">🌍 CHI TIẾT TỪNG CẶP</h2>')
            html.append("<div style='display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px;'>")
            for symbol, sym_stats in sorted(symbol_stats.items()):
                if not isinstance(sym_stats, dict):
                    continue
                sym_wr = float(sym_stats.get("win_rate", 0) or 0)
                sym_pf = float(sym_stats.get("profit_factor", 0) or 0)
                
                html.append(
                    f"<div style='background-color: {card_bg}; border-radius: 8px; padding: 14px; width: calc(50% - 6px); box-sizing: border-box; border-left: 4px solid #ea580c; border: 1px solid {border_color};'>"
                    f'<div style="{QSS_BODY} font-weight: bold; color: {card_title}; margin-bottom: 10px;">✨ {symbol}</div>'
                    f'<table style="width: 100%; border-collapse: collapse; {QSS_BODY}">'
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

            html.append(f'<h2 style="color:{text_color}; margin-bottom: 10px; margin-top: 6px; {QSS_SUBTITLE}">🔄 Walk-Forward Analysis</h2>')
            html.append(f'<table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; {QSS_BODY}">')
            row = lambda label, value, clr=None: (
                f"<tr>"
                f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>{label}</td>"
                f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {clr or text_color}; font-weight: 600;'>{value}</td>"
                f"</tr>"
            )
            html.append(row("Số window", str(wf.get("window_count", 0))))
            html.append(row(
                "Window replay OOS thành công",
                str(wf.get("successful_window_count", 0)),
            ))
            html.append(row("Tổng lệnh IS (In-Sample — dữ liệu học)", f"{is_agg.get('total_trades', 0)} lệnh"))
            html.append(row("Tổng lệnh OOS (Out-of-Sample — dữ liệu kiểm tra)", f"{oos_agg.get('total_trades', 0)} lệnh"))
            html.append(row(
                "Lệnh OOS trùng đã loại khỏi tổng hợp",
                str(wf.get("duplicate_oos_trade_count", 0)),
            ))
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
            f'<table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; {QSS_BODY}">'
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
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>Gross R trước chi phí</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {value_color}; font-weight: bold;'>{get_stat(summary, 'gross_r')}R</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {muted_color};'>-</td>"
            f"</tr>"

            f"<tr>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>Chi phí execution</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: #f59e0b; font-weight: bold;'>{get_stat(summary, 'cost_r')}R</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {muted_color};'>spread + trượt giá + phí + swap</td>"
            f"</tr>"

            f"<tr>"
            f"<td style='padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>Net R sau chi phí</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: #10b981; font-weight: bold;'>{get_stat(summary, 'net_r')}R</td>"
            f"<td style='text-align: right; padding: 6px 10px; border-bottom: 1px solid {row_border}; color: {muted_color};'>kết quả dùng cho equity/account guard</td>"
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
            f'<table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; {QSS_BODY}">'
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
                html.append(f'<h2 style="color:{text_color}; margin-bottom: 10px; margin-top: 6px; {QSS_SUBTITLE}">📅 Bảng nhiệt lời/lỗ theo tháng</h2>')
                html.append(f'<table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; {QSS_BODY}">')
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
                        row.append(f'<td style="text-align: center; padding: 3px 2px; border-bottom: 1px solid {row_border}; background: {bg}; color: {tc}; {QSS_NUMBER}">{t}</td>')
                    yc = "#10b981" if yearly_total > 0 else ("#e11d48" if yearly_total < 0 else text_color)
                    row.append(f'<td style="text-align: center; padding: 4px 6px; border-bottom: 1px solid {row_border}; color: {yc}; {QSS_NUMBER} font-weight: 700;">{yearly_total:+.1f}R</td>')
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
                    f'<td style="padding: 5px 10px; border-bottom: 1px solid {row_border}; color: {text_color}; {QSS_BODY}">{label}</td>'
                    f'<td style="text-align: right; padding: 5px 10px; border-bottom: 1px solid {row_border}; color: {clr}; {QSS_NUMBER} font-weight: 600;">{_mc_fmt(mean_v, suffix)}</td>'
                    f'<td style="text-align: right; padding: 5px 10px; border-bottom: 1px solid {row_border}; color: {clr}; {QSS_NUMBER}">{_mc_fmt(low_v, suffix)} → {_mc_fmt(high_v, suffix)}</td>'
                )

            html.append(f'<h2 style="color:{text_color}; margin-bottom: 10px; margin-top: 6px; {QSS_SUBTITLE}">🎲 Monte Carlo: Bootstrap uncertainty và permutation sequence risk</h2>')
            html.append(f'<table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; {QSS_BODY}">')
            html.append(
                f"<tr>"
                f"<th style='text-align: left; padding: 6px 10px; border-bottom: 2px solid {border_color}; color: {muted_color};'>Chỉ số</th>"
                f"<th style='text-align: right; padding: 6px 10px; border-bottom: 2px solid {border_color}; color: {muted_color};'>Trung bình mô phỏng</th>"
                f"<th style='text-align: right; padding: 6px 10px; border-bottom: 2px solid {border_color}; color: {muted_color};'>Khoảng 95%</th>"
                f"</tr>"
            )

            html.append("<tr>" + _mc_row("Kỳ vọng", mc.get("expectancy_r", {})) + "</tr>")

            # Drawdown row with P(DD > 10R) note
            dd = mc.get("max_drawdown_r", {})
            dd_clr = _mc_color(dd.get("p95_low"), dd.get("p95_high"))
            prob_dd = mc.get("prob_dd_exceed_10r")
            dd_note = f' <span style="{QSS_SMALL}color:{muted_color};">(P(DD&gt;10R)={prob_dd}%)</span>' if prob_dd is not None else ""
            html.append(
                f"<tr>"
                f'<td style="padding:5px 10px;border-bottom:1px solid {row_border};color:{text_color};{QSS_BODY}">Drawdown tối đa</td>'
                f'<td style="text-align:right;padding:5px 10px;border-bottom:1px solid {row_border};color:{dd_clr};{QSS_NUMBER}font-weight:600;">{_mc_fmt(dd.get("mean"), "R")}{dd_note}</td>'
                f'<td style="text-align:right;padding:5px 10px;border-bottom:1px solid {row_border};color:{dd_clr};{QSS_NUMBER}">{_mc_fmt(dd.get("p95_low"), "R")} → {_mc_fmt(dd.get("p95_high"), "R")}</td>'
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
                f'<td style="padding:5px 10px;border-bottom:1px solid {row_border};color:{text_color};{QSS_BODY}">Chuỗi thua dài nhất</td>'
                f'<td style="text-align:right;padding:5px 10px;border-bottom:1px solid {row_border};color:{cl_clr};{QSS_NUMBER}font-weight:600;">{cl_mean:.0f} lệnh (tối đa: {cl_high:.0f})</td>'
                f'<td style="text-align:right;padding:5px 10px;border-bottom:1px solid {row_border};color:{muted_color};{QSS_BODY}">—</td>'
                f"</tr>"
            )

            # Bottom row: P(expectancy < 0)
            prob_neg = mc.get("prob_negative_expectancy")
            if prob_neg is not None:
                prob_positive = mc.get("probability_positive_edge_pct")
                p_value = mc.get("one_sided_p_value")
                if prob_positive is None:
                    prob_positive = round(100.0 - float(prob_neg), 2)
                if p_value is None:
                    p_value = round(float(prob_neg) / 100.0, 4)
                pn_color = "#10b981" if prob_neg < 20 else ("#f59e0b" if prob_neg <= 50 else "#e11d48")
                html.append(
                    f"<tr>"
                    f'<td colspan="3" style="padding:6px 10px;border-bottom:1px solid {row_border};color:{pn_color};{QSS_NUMBER}font-weight:700;text-align:center;">'
                    f"Xác suất edge dương = {prob_positive}% · "
                    f"P(edge không dương) = {prob_neg}% · p một phía = {p_value}"
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
            html.append(f'<h2 style="color:{pipeline_title_color}; margin-bottom: 12px; margin-top: 24px; {QSS_SUBTITLE}">🔬 CHẨN ĐOÁN PIPELINE</h2>')
            html.append(
                f'<table style="width: 100%; border-collapse: collapse; margin-bottom: 16px; {QSS_BODY}">'
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
                f'<div style="display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 12px; {QSS_SMALL} color: {muted_color};">'
                f"<span>📊 Tổng snapshot: <b style='color:{text_color};'>{ev}</b></span>"
                f"<span>🚫 Bị gate chặn: <b style='color:#e11d48;'>{blk}</b></span>"
                f"<span>⚠️ Điểm {'<'}50: <b style='color:#f59e0b;'>{low}</b></span>"
                f"</div>"
            )

        if gate_fail_counts:
            html.append(f'<h3 style="color:{pipeline_title_color}; margin-bottom: 8px; margin-top: 16px; {QSS_SUBTITLE}">🚧 Chi tiết Gate</h3>')
            html.append(
                f'<table style="width: 100%; border-collapse: collapse; margin-bottom: 12px; {QSS_BODY}">'
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
                    f'<div style="{QSS_SUBTITLE}font-weight:700;color:{h_color};'
                    f'margin:16px 0 4px 0;padding-bottom:4px;'
                    f'border-bottom:1px solid {b_border};">{clean}</div>'
                )
                continue

            # Numbered items: "1. text" or "1) text"
            m = re.match(r"^(\d+)[.)]\s+(.*)", stripped)
            if m:
                if not in_list or list_type != "ol":
                    _end_list()
                    html_lines.append(f'<ol style="margin:4px 0;padding-left:20px;color:{t_color};{QSS_BODY}line-height:1.55;">')
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
                    html_lines.append(f'<ul style="margin:4px 0;padding-left:20px;color:{t_color};{QSS_BODY}line-height:1.55;">')
                    in_list = True
                    list_type = "ul"
                content = _highlight_numbers(_esc(m.group(1).replace("*", "").replace("#", "").replace("_", "").replace("`", "")))
                html_lines.append(f"<li style='margin:2px 0;'>{content}</li>")
                continue

            # Regular text
            _end_list()
            clean = _highlight_numbers(_esc(stripped.replace("*", "").replace("#", "").replace("_", "").replace("`", "")))
            html_lines.append(
                f'<p style="margin:4px 0;color:{t_color};{QSS_BODY}line-height:1.55;">{clean}</p>'
            )

        _end_list()
        body = "\n".join(html_lines)
        return (
            f'<div style="{QSS_BODY}">'
            f"{body}</div>"
        )

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if hasattr(self, "table") and watched is self.table.viewport() and event.type() == QEvent.Type.Resize:
            self._resize_trade_columns_to_viewport()
        return super().eventFilter(watched, event)

    def _run_backtest(self) -> None:
        purpose = str(self.purpose_combo.currentData())
        execution_mode = self._selected_execution_mode(purpose)
        portfolio_enabled = (
            purpose == BACKTEST_PURPOSE_RESEARCH
            and hasattr(self, "portfolio_mode_checkbox")
            and self.portfolio_mode_checkbox.isEnabled()
            and self.portfolio_mode_checkbox.isChecked()
        )
        if portfolio_enabled and len(self.selected_symbols) < 2:
            QMessageBox.information(
                self,
                "Chưa đủ mã cho danh mục",
                "Đánh giá danh mục cần ít nhất 2 mã. Hãy chọn thêm mã hoặc tắt tùy chọn danh mục.",
            )
            return
        run_symbols = (
            list(self.selected_symbols)
            if portfolio_enabled
            else [self.selected_symbol]
        )
        build_args = {
            "symbols": run_symbols,
            "start": self._qdate_to_utc_start(self.start_date.date()),
            "end": self._qdate_to_utc_end(self.end_date.date()),
            "initial_balance": self.balance_input.value(),
            "risk_percent": self.risk_input.value(),
            "purpose": purpose,
            "execution_mode": execution_mode,
        }

        self.run_button.setEnabled(False)
        self.run_button.setText("⏳ Đang chạy...")
        self.cancel_backtest_btn.show()
        self.analyze_btn.setEnabled(False)
        self.apply_config_btn.hide()
        self.progress.setValue(0)
        self.progress.setFormat("0%")
        self.status_label.setText("Đang chạy backtest...")
        self.backtest_thread, self.backtest_worker = self.controller.create_backtest_worker_from_inputs(
            build_args=build_args,
            research_validation_enabled=(
                purpose == BACKTEST_PURPOSE_RESEARCH
                and self.research_validation_checkbox.isEnabled()
                and self.research_validation_checkbox.isChecked()
            ),
            monte_carlo_requested=(
                hasattr(self, "monte_carlo_checkbox")
                and self.monte_carlo_checkbox.isChecked()
            ),
        )
        self.backtest_worker.progress.connect(self._on_progress)
        self.backtest_worker.succeeded.connect(self._on_success)
        self.backtest_worker.failed.connect(self._on_failed)
        self.backtest_worker.cancelled.connect(self._on_backtest_cancelled)
        self.backtest_worker.finished.connect(lambda: self.run_button.setEnabled(True))
        self.backtest_worker.finished.connect(lambda: self.run_button.setText("▶️ Chạy"))
        self.backtest_worker.finished.connect(self.cancel_backtest_btn.hide)
        self.backtest_worker.finished.connect(lambda: self.analyze_btn.setEnabled(True))
        self.backtest_thread.start()

    def _selected_execution_mode(self, purpose: str) -> str:
        if purpose == BACKTEST_PURPOSE_VALIDATION:
            return EXECUTION_MODE_PARITY
        if hasattr(self, "advanced_execution_combo"):
            return str(self.advanced_execution_combo.currentData())
        return EXECUTION_MODE_PARITY

    def _sync_backtest_mode_ui(self, *_args: object) -> None:
        purpose = str(self.purpose_combo.currentData())
        is_validation = purpose == BACKTEST_PURPOSE_VALIDATION
        if hasattr(self, "advanced_execution_combo"):
            if is_validation:
                parity_index = self.advanced_execution_combo.findData(
                    EXECUTION_MODE_PARITY
                )
                self.advanced_execution_combo.setCurrentIndex(parity_index)
            self.advanced_execution_combo.setEnabled(not is_validation)
        if hasattr(self, "research_validation_checkbox"):
            research_fast = (
                not is_validation
                and self._selected_execution_mode(purpose)
                == EXECUTION_MODE_RESEARCH
            )
            if is_validation or research_fast:
                self.research_validation_checkbox.setChecked(False)
            self.research_validation_checkbox.setEnabled(
                not is_validation and not research_fast
            )
        if hasattr(self, "portfolio_mode_checkbox"):
            if is_validation:
                self.portfolio_mode_checkbox.setChecked(False)
            self.portfolio_mode_checkbox.setEnabled(not is_validation)
        if hasattr(self, "mode_summary_label"):
            if is_validation:
                summary = "MT5 • IS/OOS + Walk-Forward"
            elif self._selected_execution_mode(purpose) == EXECUTION_MODE_RESEARCH:
                summary = "Nhanh • Chỉ nghiên cứu"
            else:
                summary = "MT5 • Chỉ nghiên cứu"
            if (
                not is_validation
                and hasattr(self, "portfolio_mode_checkbox")
                and self.portfolio_mode_checkbox.isChecked()
            ):
                summary = "MT5 • Danh mục nghiên cứu"
            self.mode_summary_label.setText(summary)
            self._refresh_compact_control_sizes()

    def _on_progress(self, percent: int, message: str) -> None:
        bounded_percent = max(0, min(100, int(percent)))
        self.progress.setValue(bounded_percent)
        self.progress.setFormat(
            self._progress_bar_text(bounded_percent, message)
        )
        self.status_label.setText(message)

    @classmethod
    def _progress_bar_text(cls, percent: int, message: str) -> str:
        """Return the compact progress-bar label without changing run logic."""
        if percent >= 100:
            return "Hoàn tất - 100%"
        if percent <= 0:
            return "0%"
        msg = str(message or "")
        match = cls._BACKTEST_TIMESTAMP_RE.search(msg)
        if match:
            timestamp = match.group(1)
            phase = match.group(2).strip()
            return f"Đang quét: {phase} - {timestamp} - {percent}%"
        match = cls._BACKTEST_TIMESTAMP_LEGACY_RE.search(msg)
        if match:
            return f"Đang quét: {match.group(1)} - {percent}%"
        return f"{percent}%"

    def _cancel_backtest(self) -> None:
        if self.backtest_worker is not None:
            self.cancel_backtest_btn.setEnabled(False)
            self.status_label.setText("Đang hủy an toàn...")
            self.backtest_worker.cancel()

    def _on_backtest_cancelled(self, message: str) -> None:
        self.status_label.setText(message)
        self.cancel_backtest_btn.setEnabled(True)
        QMessageBox.information(self, "Đã hủy", message)

    def _show_symbol_dialog(self) -> None:
        dialog = SymbolSelectionDialog(self.selected_symbols, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._set_selected_symbols(dialog.selected_symbols())
            self._update_result_action()

    def _set_selected_symbols(self, symbols: list[str] | tuple[str, ...]) -> None:
        normalized = list(dict.fromkeys(
            str(symbol or "").strip()
            for symbol in symbols
            if str(symbol or "").strip()
        ))
        if not normalized:
            return
        self.selected_symbols = normalized
        self.selected_symbol = normalized[0]
        summary = (
            self.selected_symbol
            if len(normalized) == 1
            else f"{self.selected_symbol} +{len(normalized) - 1}"
        )
        self.symbol_summary.setText(summary)
        self.symbol_summary.setToolTip(", ".join(normalized))

    def _sync_symbols_from_result(self, result: dict) -> None:
        symbols = snapshot_symbols(result)
        if symbols:
            self._set_selected_symbols(symbols)

    def _update_result_action(self) -> None:
        action = result_action(
            self.result,
            selected_symbol=self.selected_symbol,
        )
        self.apply_config_btn.setVisible(action.visible)
        if not action.visible:
            return
        self.apply_config_btn.setText(action.label)
        if action.kind == ACTION_SAVE_DRAFT:
            self.apply_config_btn.setToolTip(
                "Lưu đề xuất để tiếp tục xem xét; bản nháp không được Strategy "
                "Router dùng để giao dịch."
            )
        else:
            self.apply_config_btn.setToolTip(
                "Áp dụng cấu hình đã đủ bằng chứng và sẵn sàng phát hành cho "
                "đúng mã trong snapshot."
            )

    def _on_success(self, result: dict) -> None:
        self.progress.setValue(100)
        self.progress.setFormat("Hoàn tất - 100%")
        self.result = result
        self._sync_symbols_from_result(result)
        lifecycle = (
            result.get("lifecycle")
            if isinstance(result.get("lifecycle"), dict)
            else {"status": "RESEARCH_ONLY", "reasons": []}
        )
        data_manifest = (
            result.get("data_manifest")
            if isinstance(result.get("data_manifest"), dict)
            else {}
        )
        data_status = str(data_manifest.get("quality_status") or "UNKNOWN")
        data_issues = (
            data_manifest.get("issues")
            if isinstance(data_manifest.get("issues"), list)
            else []
        )
        lifecycle_status = str(lifecycle.get("status") or "RESEARCH_ONLY")
        lifecycle_reasons = lifecycle.get("reasons", [])
        lifecycle_label = lifecycle_status_label(lifecycle_status)
        status = f"Hoàn tất backtest. {lifecycle_label}."
        if result.get("mode") == "portfolio_backtest":
            symbols = result.get("request", {}).get("symbols", [])
            status = f"Hoàn tất backtest danh mục {len(symbols)} mã. {lifecycle_label}."
        if lifecycle_reasons:
            status += " " + " ".join(
                lifecycle_reason_labels(lifecycle_reasons)
            )
        if data_status in {"WARNING", "INVALID"}:
            status += (
                f" Dữ liệu: {data_status}, {len(data_issues)} vấn đề; "
                "chi tiết nằm trong DataManifest."
            )
        self.status_label.setText(status)
        self._set_summary(result.get("summary", {}) if isinstance(result.get("summary"), dict) else {})
        self._set_trades(result.get("trades", []) if isinstance(result.get("trades"), list) else [])
        self._update_verdict()
        self._update_result_action()
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
            ("Lệnh", self._format_integer(summary.get("total_trades", 0)), "info"),
            ("Kỳ vọng", self._format_decimal(summary.get("expectancy_r", 0), 2, "R"), "success"),
            ("Hệ số LN", self._format_decimal(summary.get("profit_factor", 0), 2), "warning"),
            ("DD tối đa", self._format_decimal(summary.get("max_drawdown_r", 0), 1, "R"), "danger"),
            ("Net", self._format_decimal(summary.get("net_r", summary.get("total_r", 0)), 1, "R"), "accent"),
        ]
        for idx, (title, value, tone) in enumerate(items):
            if idx > 0:
                sep_label = QLabel("|")
                sep_label.setObjectName("BacktestSummarySeparator")
                sep_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                sep_label.setSizePolicy(
                    QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
                )
                self.summary_row.addWidget(
                    sep_label, 0, Qt.AlignmentFlag.AlignVCenter
                )
            self.summary_row.addWidget(
                self._stat_cell(str(title), str(value), tone=tone),
                0,
                Qt.AlignmentFlag.AlignVCenter,
            )
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
                verdict_state = "empty"
                accent, separator, text = "#475569", "#cbd5e1", "#334155"
                line = "Chưa có lệnh nào"
            elif has_edge and good_pf:
                verdict_state = "success"
                accent, separator, text = "#047857", "#a7f3d0", "#065f46"
                line = f"CÓ LỢI THẾ · Kỳ vọng +{exp_r:.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"
            elif has_edge and not good_pf:
                verdict_state = "warning"
                accent, separator, text = "#b45309", "#fde68a", "#78350f"
                line = f"LỢI THẾ YẾU · Kỳ vọng +{exp_r:.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"
            elif positive_total and not has_edge:
                verdict_state = "unclear"
                accent, separator, text = "#ea580c", "#fed7aa", "#7c2d12"
                line = f"CHƯA RÕ · Kỳ vọng {exp_r:+.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"
            else:
                verdict_state = "danger"
                accent, separator, text = "#be123c", "#fecdd3", "#9f1239"
                line = f"HỆ THỐNG ÂM · Kỳ vọng {exp_r:+.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"
        else:
            if total == 0:
                verdict_state = "empty"
                accent, separator, text = "#94a3b8", "#334155", "#cbd5e1"
                line = "Chưa có lệnh nào"
            elif has_edge and good_pf:
                verdict_state = "success"
                accent, separator, text = "#10b981", "#334155", "#cbd5e1"
                line = f"CÓ LỢI THẾ · Kỳ vọng +{exp_r:.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"
            elif has_edge and not good_pf:
                verdict_state = "warning"
                accent, separator, text = "#f59e0b", "#334155", "#cbd5e1"
                line = f"LỢI THẾ YẾU · Kỳ vọng +{exp_r:.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"
            elif positive_total and not has_edge:
                verdict_state = "unclear"
                accent, separator, text = "#fb923c", "#334155", "#cbd5e1"
                line = f"CHƯA RÕ · Kỳ vọng {exp_r:+.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"
            else:
                verdict_state = "danger"
                accent, separator, text = "#e11d48", "#334155", "#cbd5e1"
                line = f"HỆ THỐNG ÂM · Kỳ vọng {exp_r:+.2f}R · Hệ số LN {pf:.2f} · Tổng {total_r:+.1f}R"

        set_dynamic_property(
            self.verdict_banner,
            "verdictState",
            verdict_state,
        )

        self.verdict_banner.setText(
            f'<span style="{QSS_BODY}">'
            f"<b style='color:{accent};'>{line}</b>"
            f"<span style='color:{separator};'>&nbsp;&nbsp;│&nbsp;&nbsp;</span>"
            f"<span style='color:{text};font-weight:500;'>"
            f"{total} lệnh &nbsp;·&nbsp; TL thắng {wr:.1f}% &nbsp;·&nbsp; DD {dd:.1f}R"
            f"</span>"
            f"</span>"
        )
        self.verdict_banner.show()


    def _is_light_theme(self) -> bool:
        state = self.__dict__
        app = state.get("app")
        controller = state.get("controller")
        settings_service = (
            getattr(app, "settings_service", None)
            if app
            else getattr(controller, "settings_service", None)
        )
        if settings_service is None:
            return bool(state.get("_analysis_light", False))
        return is_light_theme(settings_service)

    def _refresh_trade_table_style(self) -> None:
        if not hasattr(self, "trades") or not self.trades:
            return
        
        from PyQt6.QtGui import QBrush, QColor
        palette = current_palette()
        semantic_colors = {
            "muted": QColor(palette.text_muted),
            "buy": QColor(palette.buy),
            "sell": QColor(palette.sell),
            "success": QColor(palette.success),
            "danger": QColor(palette.danger),
            "warning": QColor(palette.warning),
        }
        
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
                    fg_color = semantic_colors["muted"]
                elif key == "side":
                    side = str(trade.get("side", "")).lower()
                    if side == "buy": fg_color = semantic_colors["buy"]
                    elif side == "sell": fg_color = semantic_colors["sell"]
                elif key in ("result", "result_r", "expected_effective_rr"):
                    val_str = str(trade.get(key, "")).lower()
                    if key == "result":
                        if val_str == "win": fg_color = semantic_colors["success"]
                        elif val_str == "loss": fg_color = semantic_colors["danger"]
                        elif val_str == "breakeven": fg_color = semantic_colors["warning"]
                    else:
                        try:
                            val_num = float(val_str.replace("r", "").strip())
                            if val_num > 0: fg_color = semantic_colors["success"]
                            elif val_num < 0: fg_color = semantic_colors["danger"]
                            else: fg_color = semantic_colors["muted"]
                        except ValueError:
                            fg_color = semantic_colors["muted"]
                elif key == "final_score":
                    try:
                        score = int(trade.get("final_score", 0))
                        if score >= 65: fg_color = semantic_colors["success"]
                        elif score >= 50: fg_color = semantic_colors["warning"]
                        else: fg_color = semantic_colors["muted"]
                    except (TypeError, ValueError):
                        fg_color = semantic_colors["muted"]
                elif key == "market_regime":
                    regime = str(trade.get("market_regime", "")).lower()
                    if regime == "aligned": fg_color = semantic_colors["success"]
                    elif regime == "divergent": fg_color = semantic_colors["danger"]
                    elif regime == "neutral": fg_color = semantic_colors["warning"]
                    else: fg_color = semantic_colors["muted"]
                
                if fg_color:
                    cell.setForeground(fg_color)
                else:
                    cell.setForeground(QBrush())


    def refresh_theme_styles(self) -> None:
        self._refresh_theme_styles()

    def _refresh_theme_styles(self) -> None:
        self._refresh_verdict_banner_style()
        self._refresh_trade_table_style()
        self._refresh_compact_control_sizes()
        self._refresh_equity_curve()

    def _refresh_verdict_banner_style(self) -> None:
        self._update_verdict()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_theme_styles()

    def _apply_trade_table_layout(self) -> None:
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
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
        for column in range(len(self.TRADE_COLUMNS)):
            label = self.TRADE_COLUMNS[column][1]
            label_width = (
                self.table.horizontalHeader().fontMetrics().horizontalAdvance(
                    label
                )
                + LayoutTokens.SPACE_6
            )
            width = max(
                label_width,
                int(viewport_width * weights[column] / total_weight),
            )
            self.table.setColumnWidth(column, width)

    @staticmethod
    def _apply_number_format(spinbox: QDoubleSpinBox | QSpinBox) -> None:
        spinbox.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        spinbox.setGroupSeparatorShown(True)
        spinbox.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)

    def _backtest_form_stylesheet(self) -> str:
        """Return the shared app QSS for legacy layout checks."""
        qss_name = "light.qss" if self._is_light_theme() else "dark.qss"
        return (Path(__file__).resolve().parents[1] / "styles" / qss_name).read_text(
            encoding="utf-8"
        )

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
        # Backtest uses [start, end), so midnight of the following day keeps
        # the user-selected end date fully included without a 23:59:59 edge.
        return datetime(
            value.year(),
            value.month(),
            value.day(),
            tzinfo=timezone.utc,
        ) + timedelta(days=1)


class SymbolSelectionDialog(QDialog):
    def __init__(self, selected_symbols: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Chọn mã kiểm thử")
        self.setObjectName("ScannerHelpDialog")
        self.setModal(True)
        configure_dialog(
            self,
            minimum_width=LayoutTokens.DIALOG_SM_WIDTH,
            minimum_height=400,
        )

        root = QVBoxLayout(self)
        configure_layout(
            root,
            margins=LayoutTokens.DIALOG_MARGIN,
            spacing=LayoutTokens.SPACE_3,
        )

        label = QLabel("Chọn một hoặc nhiều mã để backtest portfolio:")
        label.setObjectName("FormLabel")
        label.setWordWrap(True)
        root.addWidget(label)

        scroll = QScrollArea()
        scroll.setObjectName("SymbolSelectionScroll")
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("SymbolSelectionContent")
        grid = QGridLayout(content)
        configure_layout(
            grid,
            margins=LayoutTokens.SPACE_1,
            spacing=LayoutTokens.SPACE_2,
        )
        grid.setHorizontalSpacing(LayoutTokens.SPACE_3)
        column_count = 2
        for column in range(column_count):
            grid.setColumnStretch(column, 1)

        self._symbol_checks: list[QCheckBox] = []
        symbols = sorted(SUPPORTED_SYMBOLS)
        for index, symbol in enumerate(symbols):
            checkbox = QCheckBox(symbol)
            configure_checkbox(checkbox)
            checkbox.setChecked(symbol in selected_symbols)
            self._symbol_checks.append(checkbox)
            grid.addWidget(
                checkbox,
                index // column_count,
                index % column_count,
            )
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        buttons_layout = QHBoxLayout()
        configure_layout(
            buttons_layout,
            margins=(0, LayoutTokens.SPACE_2, 0, 0),
            spacing=LayoutTokens.SPACE_2,
        )
        buttons_layout.addStretch(1)
        cancel_btn = action_button("❌ Hủy", primary=False, color="danger")
        ok_btn = action_button("✅ Chọn", primary=True, color="success")
        configure_button(cancel_btn)
        configure_button(ok_btn)
        buttons_layout.addWidget(cancel_btn)
        buttons_layout.addWidget(ok_btn)
        root.addLayout(buttons_layout)

        ok_btn.clicked.connect(self._accept_selection)
        cancel_btn.clicked.connect(self.reject)

    def _accept_selection(self) -> None:
        if not self.selected_symbols():
            QMessageBox.warning(self, "Chưa chọn mã", "Hãy chọn ít nhất một mã.")
            return
        self.accept()

    def selected_symbols(self) -> list[str]:
        return [box.text() for box in self._symbol_checks if box.isChecked()]

    def selected_symbol(self) -> str:
        symbols = self.selected_symbols()
        return symbols[0] if symbols else "EUR/USD"
