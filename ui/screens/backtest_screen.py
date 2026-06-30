from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PyQt6.QtCore import QDate, QEvent, QLocale, Qt
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QButtonGroup,
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
                "Chạy lại pipeline phân tích trên dữ liệu lịch sử để đo kỳ vọng, drawdown và lợi thế theo nhóm.",
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
        self.symbol_button.clicked.connect(self._show_symbol_dialog)
        self.symbol_button.setFixedWidth(60)

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
        self.run_button.clicked.connect(self._run_backtest)
        self.run_button.setFixedWidth(75)
        
        self.apply_config_btn = action_button("📋 Áp dụng cấu hình", primary=True, color="warning")
        self.apply_config_btn.clicked.connect(self._apply_scanner_config)
        self.apply_config_btn.setToolTip("Phân tích kết quả backtest và áp dụng cấu hình đề xuất vào Scanner settings.")
        btn_width = self.apply_config_btn.fontMetrics().horizontalAdvance(self.apply_config_btn.text()) + 60
        self.apply_config_btn.setFixedWidth(btn_width)
        self.apply_config_btn.hide()


        self.progress = QProgressBar()
        self.progress.setObjectName("BacktestProgress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFixedHeight(16)

        self.status_label = QLabel("Sẵn sàng")
        self.status_label.setObjectName("HelperText")
        self.status_label.setMinimumWidth(100)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        inputs_row.addWidget(self.run_button)
        inputs_row.addWidget(self.apply_config_btn)

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

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        title = QLabel("Danh sách lệnh")
        title.setObjectName("PanelTitle")
        header.addWidget(title)

        # --- Verdict banner inline in header (hidden until backtest) ---
        self.verdict_banner = QLabel("")
        self.verdict_banner.setObjectName("BacktestVerdict")
        self.verdict_banner.setWordWrap(False)
        self.verdict_banner.setTextFormat(Qt.TextFormat.RichText)
        self.verdict_banner.hide()
        header.addWidget(self.verdict_banner, 1)

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
            self._update_verdict()
            self.apply_config_btn.show()
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

            try:
                light = (self.app.settings_service.load().display.theme == "light" 
                         if self.app else self.controller.settings_service.load().display.theme == "light")
            except Exception:
                light = False

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
        except Exception as exc:
            QMessageBox.warning(self, "Lỗi phân tích", str(exc))
        finally:
            self.analyze_btn.setText("🤖 Phân tích")
            self.analyze_btn.setEnabled(True)

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

        def fmt_stats(s, prefix=""):
            if not isinstance(s, dict):
                return "N/A"
            return (
                f"{prefix}{s.get('total_trades', 0)} lệnh, "
                f"thắng {s.get('win_rate', 0):.1f}%, "
                f"kỳ vọng {s.get('expectancy_r', 0):+.2f}R, "
                f"PF {s.get('profit_factor', 0):.2f}, "
                f"DD {s.get('max_drawdown_r', 0):.1f}R, "
                f"tổng {s.get('total_r', 0):+.1f}R"
            )

        lines = [
            "=== BÁO CÁO PHÂN TÍCH BACKTEST ===",
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

        lines.extend([
            "",
            "===",
            "",
            "Dựa trên số liệu trên, hãy phân tích và trả lời các câu hỏi sau:",
            "",
            "1. REGIME nào cho kết quả tốt nhất? Regime nào tệ nhất? Có nên lọc theo regime không, nếu có thì chọn regime nào?",
            "2. HƯỚNG (BUY/SELL) nào có lợi thế? Có nên chỉ trade 1 hướng không?",
            "3. NGƯỠNG ĐIỂM (min_score) tối ưu là bao nhiêu? Ở mỗi khoảng điểm, hiệu suất thay đổi thế nào? Điểm càng cao có thực sự càng tốt không?",
            "4. NGƯỠNG RR (min_rr) tối ưu là bao nhiêu? Lọc RR cao hơn có cải thiện kỳ vọng không?",
            "5. CHẤT LƯỢNG VÙNG (SMC zone score, entry zone score) ảnh hưởng thế nào đến kết quả? Vùng điểm cao có thực sự cho lệnh tốt hơn không?",
            "6. Hệ thống có EDGE (lợi thế thống kê) không? Bằng chứng cụ thể?",
            "7. RỦI RO chính là gì? Drawdown, chuỗi thua, tỉ lệ hết hạn?",
            "8. KHUYẾN NGHỊ CỤ THỂ: Nếu trade live, nên cấu hình thế nào? Đưa ra bộ tham số tối ưu (regime + side + min_score + min_rr) kèm lý do.",
            "9. Có điểm gì BẤT THƯỜNG trong dữ liệu không? (vd: quá nhiều lệnh hết hạn, phân bố lệnh không đều, thiếu dữ liệu ở 1 chiều...)",
            "",
            "Trả lời bằng tiếng Việt, ngắn gọn theo bullet point, KHÔNG dùng markdown (*, **, __).",
            "Mỗi bullet point là 1 câu hoàn chỉnh, có số liệu cụ thể để dẫn chứng.",
            "Ưu tiên đưa ra KHUYẾN NGHỊ CÓ THỂ HÀNH ĐỘNG NGAY (chọn regime nào, side nào, min_score bao nhiêu, min_rr bao nhiêu).",
        ])
        return "\n".join(lines)

    def _generate_stats_html(self) -> str:
        if not self.result:
            return ""
        summary = self.result.get("summary", {}) if isinstance(self.result.get("summary"), dict) else {}

        try:
            light = (self.app.settings_service.load().display.theme == "light" 
                     if self.app else self.controller.settings_service.load().display.theme == "light")
        except Exception:
            light = False

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
            f"<h2 style='color:{panel_title_color}; margin-top: 0; margin-bottom: 12px; font-size: 16px;'>📊 BẢNG KẾT QUẢ TỔNG HỢP</h2>",
        ]
        
        wr = float(summary.get("win_rate", 0) or 0)
        pf = float(summary.get("profit_factor", 0) or 0)
        dd = float(summary.get("max_drawdown_r", 0) or 0)
        
        html.append(
            f"<table style='width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 13px;'>"
            f"<tr>"
            f"<th style='text-align: left; padding: 10px; border-bottom: 2px solid {border_color}; color: {muted_color};'>Chỉ số</th>"
            f"<th style='text-align: right; padding: 10px; border-bottom: 2px solid {border_color}; color: {muted_color};'>Giá trị</th>"
            f"<th style='text-align: right; padding: 10px; border-bottom: 2px solid {border_color}; color: {muted_color};'>Đánh giá</th>"
            f"</tr>"
            
            f"<tr>"
            f"<td style='padding: 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>🔢 Tổng số lệnh</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid {row_border}; color: {value_color}; font-weight: bold;'>{get_stat(summary, 'total_trades', '0')}</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid {row_border}; color: {muted_color};'>-</td>"
            f"</tr>"
            
            f"<tr>"
            f"<td style='padding: 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>🎯 Tỷ lệ thắng</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid {row_border}; color: {value_color}; font-weight: bold;'>{get_stat(summary, 'win_rate')}%</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid {row_border};'>{eval_winrate(wr)}</td>"
            f"</tr>"
            
            f"<tr>"
            f"<td style='padding: 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>💎 Hệ số lợi nhuận</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid {row_border}; color: {value_color}; font-weight: bold;'>{get_stat(summary, 'profit_factor')}</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid {row_border};'>{eval_profit_factor(pf)}</td>"
            f"</tr>"
 
            f"<tr>"
            f"<td style='padding: 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>🚀 Kỳ vọng</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid {row_border}; color: {value_color}; font-weight: bold;'>{get_stat(summary, 'expectancy_r')}R</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid {row_border}; color: {muted_color};'>-</td>"
            f"</tr>"
            
            f"<tr>"
            f"<td style='padding: 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>📉 Drawdown tối đa</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid {row_border}; color: {value_color}; font-weight: bold;'>{get_stat(summary, 'max_drawdown_r')}R</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid {row_border};'>{eval_drawdown(dd)}</td>"
            f"</tr>"
            
            f"<tr>"
            f"<td style='padding: 10px; border-bottom: 1px solid {row_border}; color: {text_color};'>💰 Tổng R</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid {row_border}; color: #10b981; font-weight: bold;'>{get_stat(summary, 'total_r')}R</td>"
            f"<td style='text-align: right; padding: 10px; border-bottom: 1px solid {row_border}; color: {muted_color};'>-</td>"
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
            f"<table style='width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 12px;'>"
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
 
        symbol_stats = self.result.get("symbol_stats", {})
        if isinstance(symbol_stats, dict) and len(symbol_stats) > 1:
            html.append(f"<h2 style='color:{details_title_color}; margin-bottom: 16px; margin-top: 24px; font-size: 16px;'>🌍 CHI TIẾT TỪNG CẶP</h2>")
            html.append("<div style='display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px;'>")
            for symbol, sym_stats in sorted(symbol_stats.items()):
                if not isinstance(sym_stats, dict):
                    continue
                sym_wr = float(sym_stats.get("win_rate", 0) or 0)
                sym_pf = float(sym_stats.get("profit_factor", 0) or 0)
                
                html.append(
                    f"<div style='background-color: {card_bg}; border-radius: 8px; padding: 14px; width: calc(50% - 6px); box-sizing: border-box; border-left: 4px solid #ea580c; border: 1px solid {border_color};'>"
                    f"<div style='font-size: 15px; font-weight: bold; color: {card_title}; margin-bottom: 10px;'>✨ {symbol}</div>"
                    f"<table style='width: 100%; border-collapse: collapse; font-size: 13px;'>"
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
 
        diagnostics = self.result.get("diagnostics", {}) if isinstance(self.result.get("diagnostics"), dict) else {}
        pipeline_stats = diagnostics.get("pipeline_stats", {})
        gate_fail_counts = diagnostics.get("gate_fail_counts", {})
        if pipeline_stats:
            html.append(f"<h2 style='color:{pipeline_title_color}; margin-bottom: 12px; margin-top: 24px; font-size: 16px;'>🔬 CHẨN ĐOÁN PIPELINE</h2>")
            html.append(
                f"<table style='width: 100%; border-collapse: collapse; margin-bottom: 16px; font-size: 13px;'>"
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
                f"<div style='display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 12px; font-size: 12px; color: {muted_color};'>"
                f"<span>📊 Tổng snapshot: <b style='color:{text_color};'>{ev}</b></span>"
                f"<span>🚫 Bị gate chặn: <b style='color:#e11d48;'>{blk}</b></span>"
                f"<span>⚠️ Điểm {'<'}50: <b style='color:#f59e0b;'>{low}</b></span>"
                f"</div>"
            )
 
        if gate_fail_counts:
            html.append(f"<h3 style='color:{pipeline_title_color}; margin-bottom: 8px; margin-top: 16px; font-size: 14px;'>🚧 Chi tiết Gate</h3>")
            html.append(
                f"<table style='width: 100%; border-collapse: collapse; margin-bottom: 12px; font-size: 12px;'>"
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
 
        html.append("</div>")
        return "".join(html)

    @staticmethod
    def _format_ai_to_html(raw: str, light: bool = False) -> str:
        lines = raw.splitlines()
        html_lines: list[str] = []

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
            if stripped.endswith(":") and len(stripped) < 100:
                is_heading = True
            elif stripped.isupper() and len(stripped) > 5:
                is_heading = True

            if is_heading:
                _end_list()
                clean = stripped.replace("*", "").replace("#", "")
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
                content = _highlight_numbers(m.group(2))
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
                content = _highlight_numbers(m.group(1))
                html_lines.append(f"<li style='margin:2px 0;'>{content}</li>")
                continue

            # Regular text
            _end_list()
            clean = _highlight_numbers(stripped.replace("*", ""))
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
        self.apply_config_btn.hide()
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

        self.verdict_banner.setText(
            f"<span style='display:inline-block;padding:6px 16px;border-radius:16px;background:{bg};"
            f"border: 1px solid {border};"
            f"font-size:13px;font-family:-apple-system,Segoe UI,sans-serif;white-space:nowrap;'>"
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
        light = self._is_light_theme()
        if light:
            bg_color = "#e2e8f0"
            border_color = "#cbd5e1"
            chunk_color = "#ea580c"
            text_color = "#1f2937"
        else:
            bg_color = "#0f172a"
            border_color = "#334155"
            chunk_color = "#ea580c"
            text_color = "#f9fafb"
            
        self.progress.setStyleSheet(
            f"QProgressBar#BacktestProgress {{"
            f"background: {bg_color};"
            f"border: 1px solid {border_color};"
            f"border-radius: 5px;"
            f"color: {text_color};"
            f"font-size: 11px;"
            f"font-weight: bold;"
            f"text-align: center;"
            f"}}"
            f"QProgressBar#BacktestProgress::chunk {{"
            f"background: {chunk_color};"
            f"border-radius: 4px;"
            f"}}"
        )

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


    def _refresh_theme_styles(self) -> None:
        self._refresh_progress_bar_style()
        self._refresh_verdict_banner_style()
        self._refresh_trade_table_style()
        if hasattr(self, "settings_frame") and self.settings_frame:
            self.settings_frame.setStyleSheet(self._backtest_form_stylesheet())

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
        ok_btn = action_button("✅ Chọn", primary=True, color="success")
        buttons_layout.addWidget(cancel_btn)
        buttons_layout.addWidget(ok_btn)
        root.addLayout(buttons_layout)

        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

    def selected_symbol(self) -> str:
        checked = self._button_group.checkedButton()
        return checked.text() if checked else "EUR/USD"
