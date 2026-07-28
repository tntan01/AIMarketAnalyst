from __future__ import annotations

from config.constants import DEFAULT_DEEPSEEK_MODEL, SUPPORTED_SYMBOLS
from config.settings import AdvancedSettings, AIProviderSettings, AISettings, DisplaySettings, NotificationSettings, ScannerRolloutSettings, SymbolScanSettings, TradingSettings
from core.backtest_config import (
    backtest_activation_status,
    merge_symbol_scan_settings,
    reconcile_enabled_symbol,
)
from core.scanner_models import (
    CONFIG_DRAFT,
    CONFIG_EXPIRED,
    CONFIG_INVALID,
    CONFIG_NOT_CONFIGURED,
    CONFIG_VALIDATED,
    CONFIG_VERSION_MISMATCH,
)
from PyQt6.QtCore import QThread, Qt, QEvent, QObject
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.ai_provider_catalog_service import AIProviderCatalogService
from services.ai_service import AIProviderConfig
from services.ai.provider_catalog import ProviderCapability, capability_labels, provider_catalog
from services.data_provider import ConnectionStatus
from services.mt5_service import MT5Service
from services.settings_service import SettingsService
from ui.layout_system import configure_table
from ui.layout_system import (
    LayoutTokens,
    configure_button,
    configure_control,
    configure_form_label,
    configure_layout,
)
from ui.screens.shared import action_button, card, form_row, page_header
from workers.ai_test_worker import AITestWorker

class SettingsScreen(QWidget):
    def __init__(self, navigate=None, *, app=None) -> None:
        super().__init__()
        self.navigate = navigate
        self.app = app
        self.settings_service = app.settings_service if app else SettingsService()
        self.ai_catalog_service = app.ai_catalog_service if app else AIProviderCatalogService()
        self.mt5: MT5Service = app.mt5 if app else MT5Service()
        self.app_settings = self.settings_service.load()
        self._pending_backtest_configs: dict[str, dict] = {}
        self.ai_test_thread = None
        self.ai_test_worker = None
        self.setObjectName("FormScreen")
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(14)
        root.addWidget(page_header("Cài đặt", "", "Đơn giản"))
        tabs = QTabWidget()
        tabs.setObjectName("ContentTabs")
        tabs.addTab(self._ai_tab(), "🤖 AI")
        tabs.addTab(self._mt5_tab(), "🔌 Dữ liệu")
        tabs.addTab(self._trading_tab(), "💼 Giao dịch")
        tabs.addTab(self._rollout_tab(), "🚦 Rollout")
        tabs.addTab(self._display_tab(), "🎨 Hiển thị")
        tabs.addTab(self._advanced_tab(), "⚙️ Nâng cao")
        root.addWidget(tabs, 1)

    def _ai_tab(self) -> QFrame:
        frame = card()
        frame.layout().setSpacing(14)

        # -- Left panel: Provider list ---------------------------------------
        left_panel = QFrame()
        left_panel.setObjectName("CompactFormPanel")
        left_panel.setMinimumWidth(220)
        left_panel.setMaximumWidth(300)
        left_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 14, 0)
        left_layout.setSpacing(8)
        left_layout.addWidget(QLabel("Nhà cung cấp"))
        self.ai_provider_list = QListWidget()
        self.ai_provider_list.setObjectName("DataTable")
        self.ai_provider_list.setMinimumHeight(200)
        self.ai_provider_list.currentRowChanged.connect(self._on_provider_list_changed)
        self._populate_provider_list()
        left_layout.addWidget(self.ai_provider_list, 1)

        # -- Right panel: Provider config ------------------------------------
        right_panel = QFrame()
        right_panel.setObjectName("CompactFormPanel")
        right_panel.setMinimumWidth(380)
        right_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(14, 0, 0, 0)
        right_layout.setSpacing(10)

        # Provider name + capabilities
        self.ai_detail_name = QLabel("")
        self.ai_detail_name.setObjectName("PanelTitle")
        right_layout.addWidget(self.ai_detail_name)

        self.ai_detail_caps = QLabel("")
        self.ai_detail_caps.setObjectName("HelperText")
        self.ai_detail_caps.setWordWrap(True)
        right_layout.addWidget(self.ai_detail_caps)

        # Default provider toggle
        self.ai_default_check = QCheckBox("Đặt làm nhà cung cấp mặc định")
        self.ai_default_check.setCursor(Qt.CursorShape.PointingHandCursor)
        right_layout.addWidget(self.ai_default_check)

        right_layout.addSpacing(6)

        # API Key
        right_layout.addWidget(QLabel("API Key"))
        self.ai_api_key_input = QLineEdit()
        self.ai_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.ai_api_key_input.setPlaceholderText("Nhập khóa API")
        self.ai_api_key_input.setFixedWidth(200)
        self.ai_api_key_input.textChanged.connect(self._update_ai_button_state)
        right_layout.addWidget(self.ai_api_key_input)

        # Model row: combobox + sync button
        right_layout.addWidget(QLabel("Model"))
        model_row = QHBoxLayout()
        model_row.setSpacing(6)
        self.ai_model_combo = QComboBox()
        self.ai_model_combo.setEditable(True)
        self.ai_model_combo.setFixedWidth(200)
        self.ai_model_combo.lineEdit().setPlaceholderText("Chọn hoặc nhập model")
        self.ai_model_combo.currentTextChanged.connect(self._update_ai_button_state)
        model_row.addWidget(self.ai_model_combo)
        self.ai_refresh_models_btn = action_button("↻ Đồng bộ model", primary=True, color="info")
        self.ai_refresh_models_btn.setToolTip("Lấy model mới nhất từ API")
        self.ai_refresh_models_btn.clicked.connect(self._refresh_provider_models)
        self.ai_refresh_models_btn.setVisible(False)
        model_row.addWidget(self.ai_refresh_models_btn)
        model_row.addStretch(1)
        right_layout.addLayout(model_row)

        # Buttons
        btn_container, btn_row = self._aligned_button_row()
        self.ai_test_button = action_button("🧪 Kiểm tra", primary=True, color="info")
        self.ai_save_button = action_button("💾 Lưu", primary=True, color="success")
        btn_row.addWidget(self.ai_test_button)
        btn_row.addWidget(self.ai_save_button)
        btn_row.addStretch(1)
        right_layout.addWidget(btn_container)

        # Status
        self.ai_status_label = QLabel("")
        self.ai_status_label.setObjectName("HelperText")
        self.ai_status_label.setWordWrap(True)
        self.ai_status_label.setVisible(False)
        right_layout.addWidget(self.ai_status_label)

        right_layout.addStretch(1)

        # Connect actions
        self.ai_test_button.clicked.connect(self._test_ai_key)
        self.ai_save_button.clicked.connect(self._save_ai_provider)

        # Splitter
        ai_splitter = QSplitter(Qt.Orientation.Horizontal)
        ai_splitter.setObjectName("SettingsAiSplitter")
        ai_splitter.setChildrenCollapsible(False)
        ai_splitter.addWidget(left_panel)
        ai_splitter.addWidget(right_panel)
        ai_splitter.setStretchFactor(0, 0)
        ai_splitter.setStretchFactor(1, 1)
        ai_splitter.setSizes([250, 500])

        frame.layout().addWidget(ai_splitter, 1)
        frame.layout().addStretch(1)

        # Select first provider
        if self.ai_provider_list.count() > 0:
            self.ai_provider_list.setCurrentRow(0)

        self._update_ai_button_state()
        return frame

    # ------------------------------------------------------------------
    # Provider list
    # ------------------------------------------------------------------

    def _populate_provider_list(self) -> None:
        """Fill the provider list from the catalog."""
        self.ai_provider_list.clear()
        for info in provider_catalog.list_infos():
            item = QListWidgetItem(info.display_name)
            item.setData(Qt.ItemDataRole.UserRole, info.name)
            self.ai_provider_list.addItem(item)

    def _on_provider_list_changed(self, row: int) -> None:
        """Load provider details into right panel when selection changes."""
        if row < 0:
            return
        item = self.ai_provider_list.item(row)
        provider_key = item.data(Qt.ItemDataRole.UserRole) if item else ""
        info = provider_catalog.get(provider_key)
        if info is None:
            return

        # Provider name
        self.ai_detail_name.setText(info.display_name)

        # Capabilities — show all active flags from the enum (no hard-coding)
        cap_labels = capability_labels(info.capabilities)
        self.ai_detail_caps.setText(" · ".join(cap_labels) if cap_labels else "Chat")

        # Refresh models button — only for providers with model discovery
        self.ai_refresh_models_btn.setVisible(
            ProviderCapability.MODEL_DISCOVERY in info.capabilities
        )

        # Load saved config for this provider (if any)
        saved = self._saved_config_for(info.display_name)
        if saved:
            self.ai_api_key_input.setText(saved.api_key)
            self.ai_default_check.setChecked(saved.is_active)
        else:
            self.ai_api_key_input.clear()
            self.ai_default_check.setChecked(False)

        # Populate model dropdown
        self._refresh_ai_models(info.display_name, saved.model if saved else None)

        self._update_ai_button_state()

    # ------------------------------------------------------------------
    # Model helpers
    # ------------------------------------------------------------------

    def _refresh_ai_models(self, provider: str, selected_model: str | None = None) -> None:
        """Populate model dropdown with models for *provider* from catalog."""
        if not hasattr(self, "ai_model_combo"):
            return
        catalog = self.ai_catalog_service.load()
        models = catalog.get(provider, [])
        self.ai_model_combo.blockSignals(True)
        current = self.ai_model_combo.currentText().strip()
        self.ai_model_combo.clear()
        self.ai_model_combo.addItems(models)
        # Prefer explicit selected_model, then preserve user-typed text
        target = selected_model or current
        if target:
            self.ai_model_combo.setCurrentText(target)
        self.ai_model_combo.blockSignals(False)

    def _refresh_provider_models(self) -> None:
        """Refresh models for the currently selected provider via its API."""
        row = self.ai_provider_list.currentRow()
        if row < 0:
            return
        item = self.ai_provider_list.item(row)
        provider_key = item.data(Qt.ItemDataRole.UserRole) if item else ""
        api_key = self.ai_api_key_input.text().strip()

        if not api_key:
            self._set_ai_status("Cần nhập API Key trước khi làm mới model.", "error")
            return

        self.ai_refresh_models_btn.setEnabled(False)
        self._set_ai_status("Đang lấy model từ API...", "ok")
        QApplication.processEvents()

        try:
            self.ai_catalog_service.refresh_models(provider_key, api_key)
            info = provider_catalog.get(provider_key)
            display = info.display_name if info else provider_key
            self._refresh_ai_models(display)
            models = self.ai_model_combo.count()
            self._set_ai_status(f"Đã cập nhật {models} model.", "ok")
        except Exception as exc:
            self._set_ai_status(f"Lỗi: {exc}", "error")
        finally:
            self.ai_refresh_models_btn.setEnabled(True)

    # ------------------------------------------------------------------
    # Persist
    # ------------------------------------------------------------------

    def _saved_config_for(self, provider_display: str) -> AIProviderSettings | None:
        """Return the saved AIProviderSettings for *provider_display*, if any."""
        for item in self.app_settings.ai.providers:
            if item.provider.lower() == provider_display.lower():
                return item
        return None

    def _save_ai_provider(self) -> None:
        provider = self._current_provider_display()
        model = self.ai_model_combo.currentText().strip()
        api_key = self.ai_api_key_input.text().strip()
        if not provider:
            return
        if not model:
            self._set_ai_status("Chọn model trước khi lưu.", "error")
            return

        providers = list(self.app_settings.ai.providers)
        existing = self._saved_config_for(provider)

        if api_key:
            if existing:
                existing.api_key = api_key
                existing.model = model
                existing.api_key_ref = self._mask_api_key(api_key)
            else:
                providers.append(AIProviderSettings(
                    provider=provider,
                    model=model,
                    api_key=api_key,
                    api_key_ref=self._mask_api_key(api_key),
                    is_active=not providers,
                ))
        elif existing and not api_key:
            # Keep existing config but update model
            existing.model = model
        else:
            self._set_ai_status("Nhập API Key trước khi lưu.", "error")
            return

        # Apply default toggle
        is_default = self.ai_default_check.isChecked()
        if is_default:
            for p in providers:
                p.is_active = (p.provider.lower() == provider.lower())
        elif existing and existing.is_active and len(providers) > 1:
            # User unchecked default → pick first other provider as active
            existing.is_active = False
            first_other = next((p for p in providers if p is not existing), None)
            if first_other:
                first_other.is_active = True

        self._save_ai_providers(providers)
        self.ai_api_key_input.clear()
        self._set_ai_status(f"Đã lưu cấu hình {provider}.", "ok")

    def _save_ai_providers(self, providers: list[AIProviderSettings]) -> None:
        active = next((item for item in providers if item.is_active), providers[0] if providers else None)
        self.app_settings.ai = AISettings(
            provider=active.provider if active else "DeepSeek",
            model=active.model if active else DEFAULT_DEEPSEEK_MODEL,
            api_key_ref=active.api_key_ref if active else None,
            providers=providers,
        )
        self.settings_service.save(self.app_settings)

    def _current_provider_display(self) -> str:
        row = self.ai_provider_list.currentRow()
        if row < 0:
            return ""
        item = self.ai_provider_list.item(row)
        return item.text() if item else ""

    # ------------------------------------------------------------------
    # Test & Status
    # ------------------------------------------------------------------

    def _test_ai_key(self) -> None:
        if self.ai_test_thread is not None:
            return
        api_key = self.ai_api_key_input.text().strip()
        if not api_key:
            self._set_ai_status("Nhập API Key trước khi kiểm tra.", "error")
            return
        provider = self._current_provider_display()
        model = self.ai_model_combo.currentText().strip()
        if not provider or not model:
            self._set_ai_status("Chọn nhà cung cấp và model.", "error")
            return

        config = AIProviderConfig(provider=provider, model=model, api_key=api_key)
        self.ai_test_button.setEnabled(False)
        self.ai_test_button.setText("Đang kiểm tra...")
        self._set_ai_status("Đang kiểm tra...", "ok")

        thread = QThread(self)
        worker = AITestWorker(config)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.succeeded.connect(self._ai_test_succeeded)
        worker.failed.connect(self._ai_test_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._ai_test_finished)
        thread.finished.connect(thread.deleteLater)

        self.ai_test_thread = thread
        self.ai_test_worker = worker
        thread.start()

    def _ai_test_succeeded(self) -> None:
        self._set_ai_status("Kết nối thành công — API Key hợp lệ.", "ok")
        # Auto-discover models after successful validation
        row = self.ai_provider_list.currentRow()
        if row >= 0:
            item = self.ai_provider_list.item(row)
            provider_key = item.data(Qt.ItemDataRole.UserRole) if item else ""
            info = provider_catalog.get(provider_key)
            if info and ProviderCapability.MODEL_DISCOVERY in info.capabilities:
                self._refresh_provider_models()

    def _ai_test_failed(self, message: str) -> None:
        self._set_ai_status(f"Kiểm tra thất bại: {message}", "error")

    def _ai_test_finished(self) -> None:
        self.ai_test_button.setText("🧪 Kiểm tra")
        self.ai_test_thread = None
        self.ai_test_worker = None
        self._update_ai_button_state()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_ai_button_state(self) -> None:
        if not hasattr(self, "ai_provider_list"):
            return
        provider = self._current_provider_display()
        model = self.ai_model_combo.currentText().strip()
        has_key = bool(self.ai_api_key_input.text().strip())
        has_cfg = bool(provider and model)
        self.ai_test_button.setEnabled(has_cfg and has_key and self.ai_test_thread is None)
        self.ai_save_button.setEnabled(has_cfg)

    def _mask_api_key(self, api_key: str) -> str | None:
        if not api_key:
            return None
        if len(api_key) <= 8:
            return "****"
        return f"{api_key[:3]}-****{api_key[-4:]}"

    def _set_ai_status(self, text: str, state: str) -> None:
        self.ai_status_label.setText(text)
        self.ai_status_label.setProperty("state", state)
        self.ai_status_label.setVisible(bool(text))
        self.ai_status_label.style().unpolish(self.ai_status_label)
        self.ai_status_label.style().polish(self.ai_status_label)

    # ------------------------------------------------------------------
    # Shared layout helpers (used by other tabs)
    # ------------------------------------------------------------------

    def _aligned_button_row(self) -> tuple[QWidget, QHBoxLayout]:
        container = QWidget()
        row = QHBoxLayout(container)
        configure_layout(
            row,
            margins=(0, LayoutTokens.SPACE_1, 0, 0),
            spacing=LayoutTokens.SPACE_3,
        )
        return container, row

    def _compact_form_row(
        self,
        label: str,
        field: QWidget,
        label_width: int = LayoutTokens.SETTINGS_LABEL_WIDTH,
        field_width: int = LayoutTokens.SETTINGS_FIELD_WIDTH,
    ) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        configure_layout(layout, spacing=LayoutTokens.SPACE_2)
        label_widget = QLabel(label)
        label_widget.setObjectName("FormLabel")
        configure_form_label(label_widget, width=label_width)
        configure_control(field, width=field_width)
        layout.addWidget(label_widget)
        layout.addWidget(field)
        layout.addStretch(1)
        return widget

    def _mt5_tab(self) -> QWidget:
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(16)

        frame2 = card()
        frame2.layout().setSpacing(8)

        self.mt5_status_label = QLabel("Đang kiểm tra dữ liệu...")
        self.mt5_status_label.setObjectName("HelperText")
        self.mt5_detail_label = QLabel("")
        self.mt5_detail_label.setObjectName("HelperText")
        self.mt5_detail_label.setWordWrap(False)
        self.mt5_retry_button = action_button("🔄 Thử kết nối lại", primary=True, color="info")
        self.mt5_retry_button.clicked.connect(self.refresh_mt5_status)

        self.creds_save_btn = action_button("💾 Lưu cấu hình", primary=True)
        self.creds_save_btn.clicked.connect(self._save_credentials)
        self.creds_save_btn.setFixedWidth(110)

        self.app_restart_btn = action_button("🔄 Khởi động lại", primary=True, color="danger")
        self.app_restart_btn.clicked.connect(self._restart_app)
        self.app_restart_btn.setVisible(False)
        self.app_restart_btn.setFixedWidth(110)

        header_row = QHBoxLayout()
        header_row.setSpacing(12)
        header_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        header_row.addWidget(self.mt5_status_label)
        header_row.addWidget(self.mt5_detail_label)
        header_row.addStretch(1)
        header_row.addWidget(self.creds_save_btn)
        header_row.addWidget(self.app_restart_btn)
        header_row.addWidget(self.mt5_retry_button)

        frame2.layout().addLayout(header_row)

        self.mt5_display_symbols = sorted(SUPPORTED_SYMBOLS)
        self.mt5_symbols_table = QTableWidget(len(self.mt5_display_symbols), 13)
        configure_table(self.mt5_symbols_table)
        self.mt5_symbols_table.setProperty("tableRole", "mt5Symbols")
        self.mt5_symbols_table.setHorizontalHeaderLabels([
            "STT", "Mã hiển thị", "Mã MT5", "Trạng thái",
            "Kiểm tra", "Dùng BT đã duyệt", "Min Score BT", "Regime BT",
            "Hướng BT", "RR tối thiểu BT", "Ready", "Watch", "Wait",
        ])
        self.mt5_symbols_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.mt5_symbols_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        for col_idx in range(13):
            if col_idx == 2:
                self.mt5_symbols_table.horizontalHeader().setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Stretch)
            else:
                self.mt5_symbols_table.horizontalHeader().setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)
        
        self.mt5_symbols_table.setColumnWidth(0, 40)
        self.mt5_symbols_table.setColumnWidth(1, 85)
        self.mt5_symbols_table.setColumnWidth(3, 100)
        self.mt5_symbols_table.setColumnWidth(4, 170)
        self.mt5_symbols_table.setColumnWidth(5, 125)
        self.mt5_symbols_table.setColumnWidth(6, 85)
        self.mt5_symbols_table.setColumnWidth(7, 130)
        self.mt5_symbols_table.setColumnWidth(8, 150)
        self.mt5_symbols_table.setColumnWidth(9, 95)
        self.mt5_symbols_table.setColumnWidth(10, 90)
        self.mt5_symbols_table.setColumnWidth(11, 90)
        self.mt5_symbols_table.setColumnWidth(12, 90)
        self.mt5_symbols_table.horizontalHeader().setMinimumSectionSize(48)
        for row, symbol in enumerate(self.mt5_display_symbols):
            for col, value in enumerate([str(row + 1), symbol, "--", "Chưa kiểm tra", "--", "", "", "", "", "", "", "", ""]):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.mt5_symbols_table.setItem(row, col, item)
            symbol_config = self.app_settings.trading.symbol_settings.get(symbol, SymbolScanSettings())
            backtest_box = QCheckBox()
            lifecycle_status, lifecycle_reasons = backtest_activation_status(
                symbol_config,
                symbol=symbol,
            )
            can_activate_backtest = lifecycle_status == CONFIG_VALIDATED
            backtest_box.setText(
                self._backtest_status_label(lifecycle_status)
            )
            backtest_box.setChecked(
                bool(symbol_config.backtest and can_activate_backtest)
            )
            backtest_box.setEnabled(can_activate_backtest)
            backtest_box.setToolTip(
                self._backtest_status_tooltip(
                    lifecycle_status,
                    lifecycle_reasons,
                )
            )
            backtest_box.installEventFilter(self)
            self.mt5_symbols_table.setCellWidget(row, 5, self._centered_cell(backtest_box))

            # Backtest-derived fields are evidence, not manual settings.
            _stored_min_score = symbol_config.min_score
            if _stored_min_score > 0:
                min_score_text = str(_stored_min_score)
            else:
                min_score_text = ""
            min_score_input = QLineEdit(min_score_text)
            min_score_input.setObjectName("Mt5MinScoreInput")
            min_score_input.setValidator(QIntValidator(0, 100, min_score_input))
            min_score_input.setMaxLength(3)
            min_score_input.setFixedWidth(48)
            min_score_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
            min_score_input.setEnabled(False)
            min_score_input.setToolTip(
                "Ngưỡng do Backtest tạo và khóa theo bằng chứng validation. "
                "Muốn thay đổi, hãy chạy lại Backtest."
            )
            min_score_input.installEventFilter(self)
            self.mt5_symbols_table.setCellWidget(row, 6, self._centered_cell(min_score_input))

            # Auto Regime dropdown (col 7)
            REGIME_OPTIONS = [
                ("", ""),
                ("range", "Range"),
                ("trend_up", "Trend up"),
                ("trend_down", "Trend down"),
                ("volatile", "Volatile"),
            ]
            regime_combo = QComboBox()
            for _r_key, _r_label in REGIME_OPTIONS:
                regime_combo.addItem(_r_label, _r_key)
            # Set current from stored English key
            _stored_regime = symbol_config.auto_trade_regime or ""
            _regime_idx = next((i for i in range(regime_combo.count()) if regime_combo.itemData(i) == _stored_regime), 0)
            regime_combo.setCurrentIndex(_regime_idx)
            regime_combo.setEnabled(False)
            regime_combo.setToolTip(
                "Chế độ thị trường do Backtest đã duyệt xác định; "
                "không chỉnh tay tại Settings."
            )
            regime_combo.installEventFilter(self)
            self.mt5_symbols_table.setCellWidget(row, 7, self._padded_cell(regime_combo))

            # Auto Side dropdown (col 8)
            SIDE_OPTIONS = [
                ("best", "tốt nhất"),
                ("buy", "mua"),
                ("sell", "bán"),
            ]
            side_combo = QComboBox()
            side_combo.setFixedWidth(125)
            for _s_key, _s_label in SIDE_OPTIONS:
                side_combo.addItem(f"{_s_key} ({_s_label})", _s_key)
            _stored_side = symbol_config.auto_trade_side or "best"
            _side_idx = next((i for i in range(side_combo.count()) if side_combo.itemData(i) == _stored_side), 0)
            side_combo.setCurrentIndex(_side_idx)
            side_combo.setEnabled(False)
            side_combo.setToolTip(
                "Hướng giao dịch do Backtest đã duyệt xác định; "
                "'best' nghĩa là dùng hướng hệ thống phân tích."
            )
            side_combo.installEventFilter(self)
            self.mt5_symbols_table.setCellWidget(row, 8, self._padded_cell(side_combo))

            # Min RR spinbox (col 11)
            min_rr = QDoubleSpinBox()
            min_rr.setRange(0.0, 10.0)
            min_rr.setSingleStep(0.1)
            min_rr.setDecimals(1)
            min_rr.setValue(symbol_config.min_expected_rr)
            min_rr.setEnabled(False)
            min_rr.setObjectName("Mt5MinRrInput")
            min_rr.setFixedWidth(60)
            min_rr.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
            min_rr.setAlignment(Qt.AlignmentFlag.AlignCenter)
            min_rr.setToolTip(
                "Tỷ lệ lợi nhuận/rủi ro tối thiểu do Backtest đã duyệt "
                "xác định; không chỉnh tay tại Settings."
            )
            min_rr.installEventFilter(self)
            self.mt5_symbols_table.setCellWidget(row, 9, self._centered_cell(min_rr))

            # Ready (col 10)
            ready_input = QLineEdit(str(symbol_config.decision_ready))
            ready_input.setValidator(QIntValidator(0, 100, ready_input))
            ready_input.setMaxLength(3)
            ready_input.setFixedWidth(40)
            ready_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ready_input.setObjectName("Mt5ReadyInput")
            ready_input.setToolTip("Điểm cuối ≥ mức này → SẴN SÀNG vào lệnh. Mặc định 65.")
            ready_input.installEventFilter(self)
            self.mt5_symbols_table.setCellWidget(row, 10, self._centered_cell(ready_input))

            # Watch (col 11)
            watch_input = QLineEdit(str(symbol_config.decision_watch))
            watch_input.setValidator(QIntValidator(0, 100, watch_input))
            watch_input.setMaxLength(3)
            watch_input.setFixedWidth(40)
            watch_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
            watch_input.setObjectName("Mt5WatchInput")
            watch_input.setToolTip("Điểm cuối ≥ mức này → THEO DÕI. Mặc định 60.")
            watch_input.installEventFilter(self)
            self.mt5_symbols_table.setCellWidget(row, 11, self._centered_cell(watch_input))

            # Wait (col 12)
            wait_input = QLineEdit(str(symbol_config.decision_wait))
            wait_input.setValidator(QIntValidator(0, 100, wait_input))
            wait_input.setMaxLength(3)
            wait_input.setFixedWidth(40)
            wait_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
            wait_input.setObjectName("Mt5WaitInput")
            wait_input.setToolTip("Điểm cuối ≥ mức này → CHỜ XÁC NHẬN. Mặc định 55.")
            wait_input.installEventFilter(self)
            self.mt5_symbols_table.setCellWidget(row, 12, self._centered_cell(wait_input))

        frame2.layout().addWidget(self.mt5_symbols_table, 1)
        mt5_button_row = QHBoxLayout()
        mt5_button_row.setContentsMargins(0, 0, 0, 0)
        mt5_button_row.setSpacing(10)
        self.mt5_detect_button = action_button("🔍 Tự phát hiện mã broker", primary=True, color="info")
        self.mt5_detect_button.clicked.connect(self.refresh_mt5_status)
        mt5_button_row.addWidget(self.mt5_detect_button)
        self.mt5_paste_config_button = action_button("📋 Dán cấu hình Backtest", color="warning")
        self.mt5_paste_config_button.clicked.connect(self._paste_backtest_configs)
        self.mt5_paste_config_button.setToolTip(
            "Đọc cấu hình JSON từ clipboard (được copy từ nút 'Đề xuất cấu hình Scanner' "
            "trong màn hình Backtest), kiểm tra validation rồi mới cho phép kích hoạt."
        )
        mt5_button_row.addWidget(self.mt5_paste_config_button)
        self.mt5_symbol_settings_button = action_button("💾 Lưu cấu hình mã quét", primary=True, color="success")
        self.mt5_symbol_settings_button.clicked.connect(self._save_mt5_symbol_settings)
        mt5_button_row.addWidget(self.mt5_symbol_settings_button)
        mt5_button_row.addStretch(1)
        frame2.layout().addLayout(mt5_button_row)

        main_layout.addWidget(frame2, 1)

        self.refresh_mt5_status()
        return container

    def refresh_mt5_status(self) -> None:
        if not hasattr(self, "mt5_status_label"):
            return
        status = self.mt5.connection_status()
        self._apply_mt5_status(status)
        self._refresh_mt5_symbol_table(status)

    def _apply_mt5_status(self, status: ConnectionStatus) -> None:
        if status.initialized and status.connected and status.logged_in:
            self.mt5_status_label.setText(f"{status.provider_name} đã kết nối")
            detail = f"Broker: {status.broker or '--'} | Server: {status.server or '--'} | Login: {status.login or '--'}"
            self.mt5_detail_label.setText(detail)
            self.mt5_status_label.setProperty("state", "ok")
        else:
            self.mt5_status_label.setText(f"{status.provider_name or 'Dữ liệu'} chưa kết nối đầy đủ")
            detail = status.message or "Kiểm tra kết nối rồi bấm thử kết nối lại."
            if status.error_code is not None:
                detail = f"{detail} ({status.error_code})"
            self.mt5_detail_label.setText(detail)
            self.mt5_status_label.setProperty("state", "error")
        for label in [self.mt5_status_label, self.mt5_detail_label]:
            label.style().unpolish(label)
            label.style().polish(label)

    def _refresh_mt5_symbol_table(self, status: ConnectionStatus) -> None:
        if not hasattr(self, "mt5_symbols_table"):
            return

        if not status.initialized or not status.connected:
            for row, symbol in enumerate(self.mt5_display_symbols):
                self._set_mt5_symbol_row(row, symbol, "--", "Chưa kết nối", "Kiểm tra kết nối")
            return

        available_symbols = self.mt5.available_symbols(market_watch_only=True)
        if not available_symbols:
            for row, symbol in enumerate(self.mt5_display_symbols):
                self._set_mt5_symbol_row(row, symbol, "--", "Không có mã khả dụng", "Kiểm tra nguồn dữ liệu")
            return

        for row, symbol in enumerate(self.mt5_display_symbols):
            broker_symbol = self.mt5.resolve_symbol(symbol, available_symbols)
            if broker_symbol:
                self._set_mt5_symbol_row(row, symbol, broker_symbol, "Đã khớp", "Có trong hệ thống")
            else:
                self._set_mt5_symbol_row(row, symbol, "--", "Không có mã", "Cần thêm mã")

    def _set_mt5_symbol_row(self, row: int, app_symbol: str, broker_symbol: str, status: str, check: str) -> None:
        values = [str(row + 1), app_symbol, broker_symbol, status, check]
        for col, value in enumerate(values):
            item = self.mt5_symbols_table.item(row, col)
            if item is None:
                item = QTableWidgetItem()
                self.mt5_symbols_table.setItem(row, col, item)
            item.setText(value)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

    def _centered_cell(self, widget: QWidget, *, vertical_margin: int = 0) -> QWidget:
        cell = QWidget()
        layout = QHBoxLayout(cell)
        layout.setContentsMargins(0, vertical_margin, 0, vertical_margin)
        layout.setSpacing(0)
        layout.addStretch(1)
        layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)
        return cell

    def _padded_cell(self, widget: QWidget, *, margin_h: int = 6, margin_v: int = 2) -> QWidget:
        cell = QWidget()
        layout = QHBoxLayout(cell)
        layout.setContentsMargins(margin_h, margin_v, margin_h, margin_v)
        layout.setSpacing(0)
        layout.addWidget(widget)
        return cell

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Tab:
                if self._focus_next_cell_widget(obj, forward=True):
                    return True
            elif event.key() == Qt.Key.Key_Backtab:
                if self._focus_next_cell_widget(obj, forward=False):
                    return True
        return super().eventFilter(obj, event)

    def _focus_next_cell_widget(self, current_widget: QWidget, forward: bool) -> bool:
        # Find row and col for this widget
        target_row = -1
        target_col = -1
        parent_widget = current_widget.parent()

        for r in range(self.mt5_symbols_table.rowCount()):
            for c in [5, 6, 7, 8, 9, 10, 11, 12]:
                cell_w = self.mt5_symbols_table.cellWidget(r, c)
                if cell_w and (cell_w == parent_widget or cell_w == current_widget or cell_w.findChild(QWidget) == current_widget):
                    target_row = r
                    target_col = c
                    break
            if target_row != -1:
                break

        if target_row == -1:
            return False

        cols = [5, 6, 7, 8, 9, 10, 11, 12]
        col_idx = cols.index(target_col)

        if forward:
            if col_idx < len(cols) - 1:
                next_col = cols[col_idx + 1]
                next_row = target_row
            else:
                next_col = cols[0]
                next_row = (target_row + 1) % self.mt5_symbols_table.rowCount()
        else:
            if col_idx > 0:
                next_col = cols[col_idx - 1]
                next_row = target_row
            else:
                next_col = cols[-1]
                next_row = (target_row - 1 + self.mt5_symbols_table.rowCount()) % self.mt5_symbols_table.rowCount()

        next_cell = self.mt5_symbols_table.cellWidget(next_row, next_col)
        if not next_cell:
            return False

        target_input = None
        for child_type in [QCheckBox, QLineEdit, QComboBox, QDoubleSpinBox]:
            child = next_cell.findChild(child_type)
            if child:
                target_input = child
                break

        if not target_input:
            target_input = next_cell

        if target_input:
            target_input.setFocus(Qt.FocusReason.TabFocusReason)
            if isinstance(target_input, QLineEdit):
                target_input.selectAll()
            return True

        return False

    def _save_credentials(self) -> None:
        self.settings_service.save(self.app_settings)
        if hasattr(self, "app_restart_btn"):
            self.app_restart_btn.setVisible(True)

    def _restart_app(self) -> None:
        import sys
        import subprocess
        from PyQt6.QtWidgets import QApplication
        subprocess.Popen([sys.executable] + sys.argv)
        QApplication.quit()

    @staticmethod
    def _backtest_status_label(status: str) -> str:
        return {
            CONFIG_VALIDATED: "Đã duyệt",
            CONFIG_DRAFT: "Bản nháp",
            CONFIG_EXPIRED: "Hết hạn",
            CONFIG_INVALID: "Không hợp lệ",
            CONFIG_VERSION_MISMATCH: "Sai phiên bản",
            CONFIG_NOT_CONFIGURED: "Chưa có",
        }.get(str(status or "").upper(), "Không hợp lệ")

    @classmethod
    def _backtest_status_tooltip(
        cls,
        status: str,
        reasons: tuple[str, ...] | list[str],
    ) -> str:
        if status == CONFIG_VALIDATED:
            return (
                "Cấu hình Backtest đã đủ bằng chứng và đúng phiên bản SMC-v2. "
                "Tick để Strategy Router dùng cấu hình này."
            )
        reason_text = ", ".join(str(reason) for reason in reasons[:5])
        suffix = f"\nChi tiết kỹ thuật: {reason_text}" if reason_text else ""
        return (
            f"Trạng thái: {cls._backtest_status_label(status)}. "
            "Scanner tiếp tục dùng SMC-v2 + luật mặc định; cấu hình này "
            "không được phép tham gia quyết định thật."
            f"{suffix}"
        )

    def _show_backtest_preview(
        self,
        *,
        row: int,
        status: str,
        reasons: tuple[str, ...],
        config: dict,
    ) -> None:
        backtest_cell = self.mt5_symbols_table.cellWidget(row, 5)
        checkbox = (
            backtest_cell.findChild(QCheckBox)
            if isinstance(backtest_cell, QWidget)
            else None
        )
        if checkbox:
            validated = status == CONFIG_VALIDATED
            checkbox.setText(self._backtest_status_label(status))
            checkbox.setEnabled(validated)
            checkbox.setChecked(validated)
            checkbox.setToolTip(
                self._backtest_status_tooltip(status, reasons)
            )

        min_score_cell = self.mt5_symbols_table.cellWidget(row, 6)
        min_score_input = (
            min_score_cell.findChild(QLineEdit)
            if isinstance(min_score_cell, QWidget)
            else None
        )
        if min_score_input:
            value = config.get("min_score", 0)
            min_score_input.setText(str(value) if value else "")

        for column, key in ((7, "regime"), (8, "side")):
            cell = self.mt5_symbols_table.cellWidget(row, column)
            combo = (
                cell.findChild(QComboBox)
                if isinstance(cell, QWidget)
                else None
            )
            value = str(config.get(key, "") or "").strip().lower()
            if combo and value:
                index = next(
                    (
                        item
                        for item in range(combo.count())
                        if combo.itemData(item) == value
                    ),
                    -1,
                )
                if index >= 0:
                    combo.setCurrentIndex(index)

        rr_cell = self.mt5_symbols_table.cellWidget(row, 9)
        rr_input = (
            rr_cell.findChild(QDoubleSpinBox)
            if isinstance(rr_cell, QWidget)
            else None
        )
        if rr_input:
            try:
                rr_input.setValue(float(config.get("min_rr", 0) or 0))
            except (TypeError, ValueError):
                rr_input.setValue(0.0)

    def _paste_backtest_configs(self) -> None:
        """Preview clipboard configs; only validated evidence is activatable."""
        import json

        from PyQt6.QtWidgets import QApplication, QMessageBox

        clipboard_text = QApplication.clipboard().text().strip()
        if not clipboard_text:
            QMessageBox.information(self, "Dán cấu hình", "Clipboard trống.")
            return

        try:
            configs = json.loads(clipboard_text)
        except json.JSONDecodeError as exc:
            QMessageBox.warning(self, "Lỗi JSON", f"Không đọc được dữ liệu clipboard:\n{exc}")
            return

        if not isinstance(configs, dict):
            QMessageBox.warning(self, "Sai định dạng", "Clipboard không chứa cấu hình hợp lệ (cần JSON object).")
            return

        if (
            isinstance(configs.get("symbol"), str)
            and "min_score" in configs
        ):
            configs = {str(configs["symbol"]): configs}

        updated = 0
        validated_count = 0
        for row, symbol in enumerate(self.mt5_display_symbols):
            cfg = configs.get(symbol)
            if cfg is None or not isinstance(cfg, dict):
                continue

            existing = self.app_settings.trading.symbol_settings.get(symbol)
            preview = merge_symbol_scan_settings(
                existing,
                symbol=symbol,
                activate_backtest=True,
                decision_ready=(
                    existing.decision_ready if existing else 65
                ),
                decision_watch=(
                    existing.decision_watch if existing else 60
                ),
                decision_wait=(
                    existing.decision_wait if existing else 55
                ),
                recommendation=cfg,
            )
            status, reasons = backtest_activation_status(
                preview,
                symbol=symbol,
            )
            self._pending_backtest_configs[symbol] = dict(cfg)
            self._show_backtest_preview(
                row=row,
                status=status,
                reasons=reasons,
                config=cfg,
            )
            updated += 1
            if status == CONFIG_VALIDATED:
                validated_count += 1

        if updated:
            retained_count = updated - validated_count
            QMessageBox.information(
                self, "Đã dán",
                f"Đã đọc {updated} cấu hình: {validated_count} đã duyệt, "
                f"{retained_count} chưa đủ điều kiện.\n"
                "Chỉ cấu hình đã duyệt mới được bật. Bản nháp vẫn được "
                "lưu để backtest sau.\n"
                "Nhấn '💾 Lưu cấu hình mã quét' để lưu lại."
            )
        else:
            QMessageBox.information(
                self, "Không khớp",
                "Không tìm thấy cặp nào trong bảng khớp với dữ liệu clipboard."
            )

    def _save_mt5_symbol_settings(self) -> None:
        existing_symbol_settings = dict(
            self.app_settings.trading.symbol_settings
        )
        symbol_settings: dict[str, SymbolScanSettings] = dict(
            existing_symbol_settings
        )
        enabled_symbols: list[str] = list(
            self.app_settings.trading.enabled_symbols
        )
        for row, symbol in enumerate(self.mt5_display_symbols):
            backtest_cell = self.mt5_symbols_table.cellWidget(row, 5)
            ready_cell = self.mt5_symbols_table.cellWidget(row, 10)
            watch_cell = self.mt5_symbols_table.cellWidget(row, 11)
            wait_cell = self.mt5_symbols_table.cellWidget(row, 12)

            backtest_box = backtest_cell.findChild(QCheckBox) if backtest_cell else None
            ready_input = ready_cell.findChild(QLineEdit) if ready_cell else None
            watch_input = watch_cell.findChild(QLineEdit) if watch_cell else None
            wait_input = wait_cell.findChild(QLineEdit) if wait_cell else None

            # Validate Ready / Watch / Wait
            decisions: dict[str, int] = {}
            for field_name, widget in [("Ready", ready_input), ("Watch", watch_input), ("Wait", wait_input)]:
                raw = widget.text().strip() if widget else ""
                if not raw:
                    QMessageBox.warning(self, "Lỗi nhập liệu",
                        f"{field_name} cho {symbol} không được để trống. Nhập số nguyên từ 0-100.")
                    return
                try:
                    val = int(raw)
                    if val < 0 or val > 100:
                        raise ValueError
                except (ValueError, TypeError):
                    QMessageBox.warning(self, "Lỗi nhập liệu",
                        f"{field_name} cho {symbol} phải là số nguyên từ 0-100.")
                    return
                decisions[field_name] = val

            merged = merge_symbol_scan_settings(
                existing_symbol_settings.get(symbol),
                symbol=symbol,
                activate_backtest=bool(
                    backtest_box and backtest_box.isChecked()
                ),
                decision_ready=decisions["Ready"],
                decision_watch=decisions["Watch"],
                decision_wait=decisions["Wait"],
                recommendation=self._pending_backtest_configs.get(symbol),
            )
            symbol_settings[symbol] = merged
            enabled_symbols = reconcile_enabled_symbol(
                enabled_symbols,
                symbol=symbol,
                backtest_active=merged.backtest,
                lifecycle_status=merged.backtest_status,
                confirmed_disable=bool(
                    backtest_box and not backtest_box.isChecked()
                ),
            )
        self.app_settings.trading.symbol_settings = symbol_settings
        self.app_settings.trading.enabled_symbols = enabled_symbols
        self.settings_service.save(self.app_settings)
        self._pending_backtest_configs.clear()
        self.mt5_status_label.setText(
            "Đã lưu cấu hình mã quét. "
            f"{len(enabled_symbols)} cấu hình Backtest đã duyệt đang bật; "
            "các mã còn lại dùng SMC-v2 + luật mặc định."
        )
        self.mt5_status_label.setProperty("state", "ok")
        self.mt5_status_label.style().unpolish(self.mt5_status_label)
        self.mt5_status_label.style().polish(self.mt5_status_label)

    def _trading_tab(self) -> QFrame:
        frame = card("Giao dịch")
        frame.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        trading = self.app_settings.trading

        form_panel = QFrame()
        form_panel.setObjectName("CompactFormPanel")
        form_layout = QVBoxLayout(form_panel)
        configure_layout(form_layout, spacing=LayoutTokens.SPACE_2)

        balance = QDoubleSpinBox()
        balance.setRange(0, 1_000_000_000)
        balance.setDecimals(0)
        balance.setGroupSeparatorShown(True)
        balance.setSingleStep(100)
        mt5_balance = self.mt5.account_balance()
        balance.setValue(mt5_balance if mt5_balance is not None else trading.account_balance)
        balance.setSuffix(f" {trading.account_currency}")
        balance.setEnabled(False)

        currency = QComboBox()
        currency.addItems(["USD", "EUR", "GBP", "AUD", "JPY"])
        currency.setCurrentText(trading.account_currency)

        risk = QDoubleSpinBox()
        risk.setRange(0, 100)
        risk.setDecimals(1)
        risk.setSingleStep(0.1)
        risk.setValue(trading.default_risk_percent)
        risk.setSuffix(" %")

        max_risk = QDoubleSpinBox()
        max_risk.setRange(0, 100)
        max_risk.setDecimals(1)
        max_risk.setSingleStep(0.1)
        max_risk.setValue(trading.max_risk_percent)
        max_risk.setSuffix(" %")

        lot_step = QDoubleSpinBox()
        lot_step.setRange(0.01, 100)
        lot_step.setDecimals(2)
        lot_step.setSingleStep(0.01)
        lot_step.setValue(trading.lot_step)
        lot_step.setSuffix(" lot")

        minimum_lot = QDoubleSpinBox()
        minimum_lot.setRange(0.01, 100)
        minimum_lot.setDecimals(2)
        minimum_lot.setSingleStep(0.01)
        minimum_lot.setValue(trading.minimum_lot)
        minimum_lot.setSuffix(" lot")

        maximum_lot = QDoubleSpinBox()
        maximum_lot.setRange(0.01, 100_000)
        maximum_lot.setDecimals(2)
        maximum_lot.setSingleStep(0.01)
        maximum_lot.setValue(trading.maximum_lot)
        maximum_lot.setSuffix(" lot")

        contract_size = QDoubleSpinBox()
        contract_size.setRange(0, 100_000_000)
        contract_size.setDecimals(0)
        contract_size.setGroupSeparatorShown(True)
        contract_size.setSingleStep(1000)
        contract_size.setValue(trading.contract_size_override)
        contract_size.setSuffix(" units")

        backtest_slippage = QDoubleSpinBox()
        backtest_slippage.setRange(0, 1000)
        backtest_slippage.setDecimals(6)
        backtest_slippage.setSingleStep(0.00001)
        backtest_slippage.setValue(trading.backtest_slippage_price)

        backtest_commission = QDoubleSpinBox()
        backtest_commission.setRange(0, 100_000)
        backtest_commission.setDecimals(2)
        backtest_commission.setValue(
            trading.backtest_commission_per_lot_round_turn
        )
        backtest_commission.setSuffix(" / lot")

        backtest_swap_long = QDoubleSpinBox()
        backtest_swap_long.setRange(0, 100_000)
        backtest_swap_long.setDecimals(2)
        backtest_swap_long.setValue(trading.backtest_swap_long_per_lot_day)
        backtest_swap_long.setSuffix(" / lot/ngày")

        backtest_swap_short = QDoubleSpinBox()
        backtest_swap_short.setRange(0, 100_000)
        backtest_swap_short.setDecimals(2)
        backtest_swap_short.setValue(trading.backtest_swap_short_per_lot_day)
        backtest_swap_short.setSuffix(" / lot/ngày")

        self.trading_balance_input = balance
        self.trading_currency_input = currency
        self.trading_risk_input = risk
        self.trading_max_risk_input = max_risk
        self.trading_lot_step_input = lot_step
        self.trading_minimum_lot_input = minimum_lot
        self.trading_maximum_lot_input = maximum_lot
        self.trading_contract_size_input = contract_size
        self.trading_backtest_slippage_input = backtest_slippage
        self.trading_backtest_commission_input = backtest_commission
        self.trading_backtest_swap_long_input = backtest_swap_long
        self.trading_backtest_swap_short_input = backtest_swap_short

        form_layout.addWidget(self._compact_form_row("Số dư MT5", balance))
        form_layout.addWidget(self._compact_form_row("Đồng tiền", currency))
        form_layout.addWidget(self._compact_form_row("Rủi ro mỗi lệnh", risk))
        form_layout.addWidget(self._compact_form_row("Rủi ro tối đa", max_risk))
        form_layout.addWidget(self._compact_form_row("Bước lot", lot_step))
        form_layout.addWidget(self._compact_form_row("Lot tối thiểu", minimum_lot))
        form_layout.addWidget(self._compact_form_row("Lot tối đa", maximum_lot))
        form_layout.addWidget(self._compact_form_row("Quy mô hợp đồng", contract_size))
        form_layout.addWidget(self._compact_form_row("Trượt giá Backtest", backtest_slippage))
        form_layout.addWidget(self._compact_form_row("Phí khứ hồi Backtest", backtest_commission))
        form_layout.addWidget(self._compact_form_row("Swap BUY Backtest", backtest_swap_long))
        form_layout.addWidget(self._compact_form_row("Swap SELL Backtest", backtest_swap_short))

        button_container, button_row = self._aligned_button_row()
        button_row.addSpacing(
            LayoutTokens.SETTINGS_LABEL_WIDTH + LayoutTokens.SPACE_2
        )
        self.trading_save_button = action_button("💾 Lưu cài đặt giao dịch", primary=True, color="success")
        configure_button(self.trading_save_button)
        self.trading_save_button.clicked.connect(self._save_trading_settings)
        button_row.addWidget(self.trading_save_button)
        button_row.addStretch(1)
        form_layout.addWidget(button_container)
        self.trading_status_label = QLabel("Số dư được lấy trực tiếp từ tài khoản MT5; rủi ro dùng định dạng 1.0 %.")
        self.trading_status_label.setObjectName("HelperText")
        self.trading_status_label.setWordWrap(True)
        form_layout.addWidget(self.trading_status_label)
        form_layout.addStretch(1)

        frame.layout().addWidget(form_panel, 0, Qt.AlignmentFlag.AlignTop)
        frame.layout().addStretch(1)
        return frame

    def _save_trading_settings(self) -> None:
        self.app_settings.trading = TradingSettings(
            account_balance=self.trading_balance_input.value(),
            account_currency=self.trading_currency_input.currentText(),
            default_risk_percent=self.trading_risk_input.value(),
            max_risk_percent=self.trading_max_risk_input.value(),
            lot_step=self.trading_lot_step_input.value(),
            minimum_lot=self.trading_minimum_lot_input.value(),
            maximum_lot=self.trading_maximum_lot_input.value(),
            contract_size_override=self.trading_contract_size_input.value(),
            backtest_slippage_price=(
                self.trading_backtest_slippage_input.value()
            ),
            backtest_commission_per_lot_round_turn=(
                self.trading_backtest_commission_input.value()
            ),
            backtest_swap_long_per_lot_day=(
                self.trading_backtest_swap_long_input.value()
            ),
            backtest_swap_short_per_lot_day=(
                self.trading_backtest_swap_short_input.value()
            ),
            max_daily_loss_pct=self.app_settings.trading.max_daily_loss_pct,
            max_weekly_loss_pct=self.app_settings.trading.max_weekly_loss_pct,
            max_consecutive_losses=self.app_settings.trading.max_consecutive_losses,
            max_open_risk_pct=self.app_settings.trading.max_open_risk_pct,
            max_symbol_risk_pct=self.app_settings.trading.max_symbol_risk_pct,
            max_currency_exposure_pct=self.app_settings.trading.max_currency_exposure_pct,
            max_correlated_risk_pct=self.app_settings.trading.max_correlated_risk_pct,
            max_concurrent_orders=self.app_settings.trading.max_concurrent_orders,
            enabled_symbols=self.app_settings.trading.enabled_symbols,
            symbol_settings=self.app_settings.trading.symbol_settings,
        )
        self.settings_service.save(self.app_settings)
        self.trading_status_label.setText("Đã lưu cài đặt giao dịch.")
        self.trading_status_label.setProperty("state", "ok")
        self.trading_status_label.style().unpolish(self.trading_status_label)
        self.trading_status_label.style().polish(self.trading_status_label)

    def _rollout_tab(self) -> QFrame:
        frame = card("Scanner rollout")
        frame.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        rollout = self.app_settings.scanner_rollout

        form_panel = QFrame()
        form_panel.setObjectName("CompactFormPanel")
        form_layout = QVBoxLayout(form_panel)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(6)

        stage = QComboBox()
        stage.addItems([
            "DISABLED",
            "SHADOW",
            "DEMO_LIMITED",
            "DEMO_FULL",
            "CANARY",
            "PRODUCTION",
        ])
        stage.setCurrentText(rollout.stage)

        smc_mode = QComboBox()
        smc_mode.addItems(["legacy", "shadow", "v2"])
        smc_mode.setCurrentText(
            str(
                getattr(
                    self.app_settings.features,
                    "smc_scoring_mode",
                    "v2",
                )
                or "v2"
            ).lower()
        )
        smc_mode.setToolTip(
            "v2: dùng SMC v2 cho quyết định; shadow: quyết định v1 và "
            "đối chiếu v2; legacy: rollback hoàn toàn về SMC v1."
        )

        kill_switch = QCheckBox("Dừng toàn bộ lệnh từ Scanner")
        kill_switch.setChecked(rollout.kill_switch)
        shadow_compare = QCheckBox("Ghi so sánh V1/V2")
        shadow_compare.setChecked(rollout.shadow_compare_enabled)
        allowed_symbols = QLineEdit()
        allowed_symbols.setPlaceholderText("EURUSD, GBPUSD")
        allowed_symbols.setText(", ".join(rollout.allowed_symbols))

        canary_risk = QDoubleSpinBox()
        canary_risk.setRange(0.01, 1.0)
        canary_risk.setDecimals(2)
        canary_risk.setSingleStep(0.05)
        canary_risk.setSuffix(" %")
        canary_risk.setValue(rollout.canary_risk_percent)

        require_demo = QCheckBox("Bắt buộc tài khoản demo")
        require_demo.setChecked(rollout.require_demo_account)
        production_approved = QCheckBox(
            "Đã phê duyệt production sau khi đạt release gate"
        )
        production_approved.setChecked(rollout.production_approved)

        min_shadow = QSpinBox()
        min_shadow.setRange(1, 1_000_000)
        min_shadow.setValue(rollout.min_shadow_samples)
        min_demo = QSpinBox()
        min_demo.setRange(1, 1_000_000)
        min_demo.setValue(rollout.min_demo_orders)
        min_canary = QSpinBox()
        min_canary.setRange(1, 1_000_000)
        min_canary.setValue(rollout.min_canary_orders)

        max_disagreement = QDoubleSpinBox()
        max_disagreement.setRange(0, 100)
        max_disagreement.setDecimals(1)
        max_disagreement.setSuffix(" %")
        max_disagreement.setValue(rollout.max_disagreement_rate * 100)
        max_revalidation = QDoubleSpinBox()
        max_revalidation.setRange(0, 100)
        max_revalidation.setDecimals(1)
        max_revalidation.setSuffix(" %")
        max_revalidation.setValue(
            rollout.max_revalidation_failure_rate * 100
        )
        max_degradation = QDoubleSpinBox()
        max_degradation.setRange(0, 100)
        max_degradation.setDecimals(1)
        max_degradation.setSuffix(" %")
        max_degradation.setValue(
            rollout.max_performance_degradation_pct
        )

        self.rollout_stage_input = stage
        self.rollout_smc_mode_input = smc_mode
        self.rollout_kill_switch_input = kill_switch
        self.rollout_shadow_compare_input = shadow_compare
        self.rollout_symbols_input = allowed_symbols
        self.rollout_canary_risk_input = canary_risk
        self.rollout_require_demo_input = require_demo
        self.rollout_production_approved_input = production_approved
        self.rollout_min_shadow_input = min_shadow
        self.rollout_min_demo_input = min_demo
        self.rollout_min_canary_input = min_canary
        self.rollout_max_disagreement_input = max_disagreement
        self.rollout_max_revalidation_input = max_revalidation
        self.rollout_max_degradation_input = max_degradation

        form_layout.addWidget(self._compact_form_row("Giai đoạn", stage))
        form_layout.addWidget(
            self._compact_form_row("SMC scoring mode", smc_mode)
        )
        form_layout.addWidget(kill_switch)
        form_layout.addWidget(shadow_compare)
        form_layout.addWidget(
            self._compact_form_row("Mã DEMO_LIMITED", allowed_symbols)
        )
        form_layout.addWidget(
            self._compact_form_row("Canary risk cap", canary_risk)
        )
        form_layout.addWidget(require_demo)
        form_layout.addWidget(production_approved)
        form_layout.addWidget(
            self._compact_form_row("Mẫu shadow tối thiểu", min_shadow)
        )
        form_layout.addWidget(
            self._compact_form_row("Lệnh demo tối thiểu", min_demo)
        )
        form_layout.addWidget(
            self._compact_form_row("Lệnh canary tối thiểu", min_canary)
        )
        form_layout.addWidget(
            self._compact_form_row(
                "Disagreement tối đa",
                max_disagreement,
            )
        )
        form_layout.addWidget(
            self._compact_form_row(
                "Lỗi revalidation tối đa",
                max_revalidation,
            )
        )
        form_layout.addWidget(
            self._compact_form_row(
                "Suy giảm hiệu suất tối đa",
                max_degradation,
            )
        )

        self.rollout_save_button = action_button(
            "💾 Lưu rollout",
            primary=True,
            color="success",
        )
        self.rollout_save_button.clicked.connect(
            self._save_rollout_settings
        )
        form_layout.addWidget(self.rollout_save_button)
        self.rollout_status_label = QLabel(
            "Mặc định SHADOW: V2 chỉ so sánh và tuyệt đối không gửi lệnh."
        )
        self.rollout_status_label.setObjectName("HelperText")
        self.rollout_status_label.setWordWrap(True)
        form_layout.addWidget(self.rollout_status_label)
        form_layout.addStretch(1)
        frame.layout().addWidget(form_panel, 0, Qt.AlignmentFlag.AlignTop)
        frame.layout().addStretch(1)
        return frame

    def _save_rollout_settings(self) -> None:
        symbols = [
            item.strip().upper()
            for item in self.rollout_symbols_input.text().replace(
                "\n",
                ",",
            ).split(",")
            if item.strip()
        ]
        self.app_settings.scanner_rollout = ScannerRolloutSettings(
            stage=self.rollout_stage_input.currentText(),
            kill_switch=self.rollout_kill_switch_input.isChecked(),
            shadow_compare_enabled=(
                self.rollout_shadow_compare_input.isChecked()
            ),
            allowed_symbols=list(dict.fromkeys(symbols)),
            canary_risk_percent=self.rollout_canary_risk_input.value(),
            require_demo_account=self.rollout_require_demo_input.isChecked(),
            production_approved=(
                self.rollout_production_approved_input.isChecked()
            ),
            min_shadow_samples=self.rollout_min_shadow_input.value(),
            min_demo_orders=self.rollout_min_demo_input.value(),
            min_canary_orders=self.rollout_min_canary_input.value(),
            max_disagreement_rate=(
                self.rollout_max_disagreement_input.value() / 100
            ),
            max_revalidation_failure_rate=(
                self.rollout_max_revalidation_input.value() / 100
            ),
            max_performance_degradation_pct=(
                self.rollout_max_degradation_input.value()
            ),
        )
        self.app_settings.features.smc_scoring_mode = (
            self.rollout_smc_mode_input.currentText().strip().lower()
        )
        self.settings_service.save(self.app_settings)
        self.rollout_status_label.setText(
            "Đã lưu rollout và SMC mode. Kill switch và SHADOW luôn chặn "
            "gửi lệnh."
        )
        self.rollout_status_label.setProperty("state", "ok")
        self.rollout_status_label.style().unpolish(
            self.rollout_status_label
        )
        self.rollout_status_label.style().polish(
            self.rollout_status_label
        )

    def _display_tab(self) -> QFrame:
        frame = card("Hiển thị")
        frame.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        display = self.app_settings.display

        form_panel = QFrame()
        form_panel.setObjectName("CompactFormPanel")
        form_layout = QVBoxLayout(form_panel)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(6)

        language = QComboBox()
        language.addItems(["Tiếng Việt"])
        language.setCurrentIndex(0)
        timezone = QComboBox()
        timezone.addItems(["Asia/Ho_Chi_Minh", "Asia/Bangkok", "UTC"])
        timezone.setCurrentText(display.timezone)
        term_mode = QComboBox()
        term_mode.addItems(["Luôn hiển thị", "Chỉ lần đầu", "Tooltip"])
        term_mode_map = {
            "always_show": "Luôn hiển thị",
            "first_time_only": "Chỉ lần đầu",
            "tooltip": "Tooltip",
        }
        term_mode.setCurrentText(term_mode_map.get(display.term_explanation_mode, "Luôn hiển thị"))
        theme = QComboBox()
        theme.addItems(["Tối", "Sáng"])
        theme.setCurrentText("Tối" if display.theme == "dark" else "Sáng")

        self.display_language_input = language
        self.display_timezone_input = timezone
        self.display_term_mode_input = term_mode
        self.display_theme_input = theme

        form_layout.addWidget(self._compact_form_row("Ngôn ngữ", language))
        form_layout.addWidget(self._compact_form_row("Múi giờ", timezone))
        form_layout.addWidget(self._compact_form_row("Giải thích thuật ngữ", term_mode))
        form_layout.addWidget(self._compact_form_row("Giao diện", theme))

        button_container = QWidget()
        button_row = QHBoxLayout(button_container)
        button_row.setContentsMargins(0, 2, 0, 0)
        button_row.setSpacing(8)
        button_spacer = QWidget()
        button_spacer.setFixedWidth(132)
        button_row.addWidget(button_spacer)
        self.display_save_button = action_button("💾 Lưu hiển thị", primary=True, color="success")
        self.display_save_button.clicked.connect(self._save_display_settings)
        button_row.addWidget(self.display_save_button)
        button_row.addStretch(1)
        form_layout.addWidget(button_container)
        self.display_status_label = QLabel("Múi giờ mặc định theo tài liệu: Asia/Ho_Chi_Minh.")
        self.display_status_label.setObjectName("HelperText")
        self.display_status_label.setWordWrap(True)
        form_layout.addWidget(self.display_status_label)
        form_layout.addStretch(1)

        frame.layout().addWidget(form_panel, 0, Qt.AlignmentFlag.AlignTop)
        frame.layout().addStretch(1)
        return frame

    def _save_display_settings(self) -> None:
        term_mode_values = {
            "Luôn hiển thị": "always_show",
            "Chỉ lần đầu": "first_time_only",
            "Tooltip": "tooltip",
        }
        language = "vi"
        self.app_settings.display = DisplaySettings(
            language=language,
            timezone=self.display_timezone_input.currentText(),
            term_explanation_mode=term_mode_values.get(self.display_term_mode_input.currentText(), "always_show"),
            theme="dark" if self.display_theme_input.currentText() == "Tối" else "light",
        )
        self.app_settings.language = language
        self.settings_service.save(self.app_settings)
        self.display_status_label.setText("Đã lưu cài đặt hiển thị.")
        self.display_status_label.setProperty("state", "ok")
        self.display_status_label.style().unpolish(self.display_status_label)
        self.display_status_label.style().polish(self.display_status_label)
        
        # Hot-reload stylesheet
        parent_win = self.window()
        if parent_win and hasattr(parent_win, "_apply_styles"):
            parent_win._apply_styles()

    def _advanced_tab_impl(self) -> QFrame:
        frame = card("Nâng cao")
        frame.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        advanced = self.app_settings.advanced

        form_panel = QFrame()
        form_panel.setObjectName("CompactFormPanel")
        form_layout = QVBoxLayout(form_panel)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(6)

        d1_bars = QSpinBox()
        d1_bars.setRange(100, 5000)
        d1_bars.setSingleStep(50)
        d1_bars.setValue(advanced.d1_bars)
        d1_bars.setSuffix(" nến")

        h4_bars = QSpinBox()
        h4_bars.setRange(100, 5000)
        h4_bars.setSingleStep(50)
        h4_bars.setValue(advanced.h4_bars)
        h4_bars.setSuffix(" nến")

        h1_bars = QSpinBox()
        h1_bars.setRange(100, 5000)
        h1_bars.setSingleStep(50)
        h1_bars.setValue(advanced.h1_bars)
        h1_bars.setSuffix(" nến")

        ai_limit = QSpinBox()
        ai_limit.setRange(1, len(SUPPORTED_SYMBOLS))
        ai_limit.setValue(advanced.scanner_ai_detail_limit)
        ai_limit.setSuffix(" mã")

        block_before = QSpinBox()
        block_before.setRange(0, 240)
        block_before.setSingleStep(5)
        block_before.setValue(advanced.high_impact_news_block_before_minutes)
        block_before.setSuffix(" phút")

        block_after = QSpinBox()
        block_after.setRange(0, 240)
        block_after.setSingleStep(5)
        block_after.setValue(advanced.high_impact_news_block_after_minutes)
        block_after.setSuffix(" phút")

        db_path = QLineEdit()
        db_path.setText(advanced.sqlite_database_path)
        db_path.setPlaceholderText("./data/journal.db")

        storage = QComboBox()
        storage.addItems(["settings.json"])
        storage.setCurrentText(advanced.settings_storage)

        block_news = QCheckBox("Chặn giao dịch quanh tin đỏ")
        block_news.setChecked(advanced.block_high_impact_news)
        notifications = self.app_settings.notifications

        auto_interval = QComboBox()
        auto_interval.addItem("1 phút", 1)
        auto_interval.addItem("5 phút", 5)
        auto_interval.addItem("15 phút", 15)
        auto_interval.addItem("30 phút", 30)
        auto_interval.addItem("1 giờ", 60)
        auto_interval.addItem("4 giờ", 240)
        auto_interval.addItem("1 ngày", 1440)
        selected_index = auto_interval.findData(notifications.auto_scan_interval_minutes)
        auto_interval.setCurrentIndex(selected_index if selected_index >= 0 else 2)

        telegram_token = QLineEdit()
        telegram_token.setEchoMode(QLineEdit.EchoMode.Password)
        telegram_token.setText(notifications.telegram_bot_token)
        telegram_token.setPlaceholderText("Bot token Telegram")

        telegram_chats = QLineEdit()
        telegram_chats.setText(", ".join(notifications.telegram_chat_ids))
        telegram_chats.setPlaceholderText("Chat ID Telegram, cách nhau bằng dấu phẩy")

        self.advanced_d1_bars_input = d1_bars
        self.advanced_h4_bars_input = h4_bars
        self.advanced_h1_bars_input = h1_bars
        self.advanced_ai_limit_input = ai_limit
        self.advanced_block_before_input = block_before
        self.advanced_block_after_input = block_after
        self.advanced_db_path_input = db_path
        self.advanced_storage_input = storage
        self.advanced_block_news_input = block_news
        self.notification_auto_interval_input = auto_interval
        self.telegram_token_input = telegram_token
        self.telegram_chats_input = telegram_chats

        form_layout.addWidget(self._compact_form_row("D1 - nến ngày", d1_bars))
        form_layout.addWidget(self._compact_form_row("H4 - nến 4 giờ", h4_bars))
        form_layout.addWidget(self._compact_form_row("H1 - nến 1 giờ", h1_bars))
        form_layout.addWidget(self._compact_form_row("AI chi tiết scanner", ai_limit))
        form_layout.addWidget(self._compact_form_row("Chặn trước tin đỏ", block_before))
        form_layout.addWidget(self._compact_form_row("Chặn sau tin đỏ", block_after))
        form_layout.addWidget(self._compact_form_row("SQLite database", db_path, field_width=320))
        form_layout.addWidget(self._compact_form_row("Nơi lưu cài đặt", storage))
        form_layout.addWidget(block_news)
        form_layout.addWidget(self._compact_form_row("Auto-scan mặc định", auto_interval))
        form_layout.addWidget(self._compact_form_row("Telegram bot token", telegram_token, field_width=320))
        form_layout.addWidget(self._compact_form_row("Telegram chat ID", telegram_chats, field_width=320))

        button_container = QWidget()
        button_row = QHBoxLayout(button_container)
        button_row.setContentsMargins(0, 2, 0, 0)
        button_row.setSpacing(8)
        button_spacer = QWidget()
        button_spacer.setFixedWidth(132)
        button_row.addWidget(button_spacer)
        self.advanced_save_button = action_button("💾 Lưu nâng cao", primary=True, color="success")
        self.advanced_save_button.clicked.connect(self._save_advanced_settings)
        button_row.addWidget(self.advanced_save_button)
        button_row.addStretch(1)
        form_layout.addWidget(button_container)

        self.advanced_status_label = QLabel("Số nến dùng định dạng 500 nến; thời gian chặn dùng định dạng 30 phút.")
        self.advanced_status_label.setObjectName("HelperText")
        self.advanced_status_label.setWordWrap(True)
        form_layout.addWidget(self.advanced_status_label)
        form_layout.addStretch(1)

        frame.layout().addWidget(form_panel, 0, Qt.AlignmentFlag.AlignTop)
        frame.layout().addStretch(1)
        return frame

    def _save_advanced_settings(self) -> None:
        self.app_settings.advanced = AdvancedSettings(
            d1_bars=self.advanced_d1_bars_input.value(),
            h4_bars=self.advanced_h4_bars_input.value(),
            h1_bars=self.advanced_h1_bars_input.value(),
            scanner_ai_detail_limit=self.advanced_ai_limit_input.value(),
            high_impact_news_block_before_minutes=self.advanced_block_before_input.value(),
            high_impact_news_block_after_minutes=self.advanced_block_after_input.value(),
            sqlite_database_path=self.advanced_db_path_input.text().strip() or "./data/journal.db",
            settings_storage=self.advanced_storage_input.currentText(),
            block_high_impact_news=self.advanced_block_news_input.isChecked(),
        )
        self.app_settings.notifications = NotificationSettings(
            telegram_bot_token=self.telegram_token_input.text().strip(),
            telegram_chat_ids=[
                item.strip()
                for item in self.telegram_chats_input.text().replace("\n", ",").split(",")
                if item.strip()
            ],
            auto_scan_interval_minutes=int(self.notification_auto_interval_input.currentData() or 15),
        )
        self.settings_service.save(self.app_settings)
        self.advanced_status_label.setText("Đã lưu cài đặt nâng cao.")
        self.advanced_status_label.setProperty("state", "ok")
        self.advanced_status_label.style().unpolish(self.advanced_status_label)
        self.advanced_status_label.style().polish(self.advanced_status_label)

    def _advanced_tab(self) -> QFrame:
        return self._advanced_tab_impl()
        frame = card("Nâng cao")
        bars = QSpinBox()
        bars.setRange(100, 5000)
        bars.setValue(500)
        limit = QSpinBox()
        limit.setRange(1, len(SUPPORTED_SYMBOLS))
        limit.setValue(3)
        news = QCheckBox("Chặn giao dịch quanh tin đỏ")
        news.setChecked(True)
        frame.layout().addWidget(form_row("Số nến mỗi khung", bars))
        frame.layout().addWidget(form_row("Số mã gọi AI", limit))
        frame.layout().addWidget(news)
        frame.layout().addWidget(action_button("💾 Lưu nâng cao", primary=True, color="success"))
        return frame
