from __future__ import annotations

from config.constants import AI_PROVIDERS, DEFAULT_AI_MODELS, DEFAULT_DEEPSEEK_MODEL, SUPPORTED_SYMBOLS
from config.settings import AdvancedSettings, AIProviderSettings, AISettings, DisplaySettings, NotificationSettings, SymbolScanSettings, TradingSettings
from PyQt6.QtCore import QThread, Qt
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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

from services.ai_provider_catalog_service import AIProviderCatalogService, FIXED_AI_PROVIDERS
from services.ai_service import AIProviderConfig
from services.data_provider import ConnectionStatus, DataProvider
from services.mt5_service import MT5ConnectionStatus, MT5Service
from services.settings_service import SettingsService
from ui.screens.shared import action_button, card, form_row, page_header
from workers.ai_test_worker import AITestWorker


class SettingsScreen(QWidget):
    def __init__(self, navigate=None, *, app=None) -> None:
        super().__init__()
        self.navigate = navigate
        self.app = app
        self.settings_service = app.settings_service if app else SettingsService()
        self.ai_catalog_service = app.ai_catalog_service if app else AIProviderCatalogService()
        self.data_provider: DataProvider = app.data_provider if app else MT5Service()
        self.ai_model_catalog = self.ai_catalog_service.load() or dict(DEFAULT_AI_MODELS)
        self.app_settings = self.settings_service.load()
        self.ai_test_thread = None
        self.ai_test_worker = None
        self.setObjectName("FormScreen")
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(14)
        root.addWidget(page_header("Cài đặt", "Cấu hình AI, MT5, giao dịch và hiển thị.", "Đơn giản"))
        tabs = QTabWidget()
        tabs.setObjectName("ContentTabs")
        tabs.addTab(self._ai_tab(), "AI")
        tabs.addTab(self._mt5_tab(), "Dữ liệu")
        tabs.addTab(self._trading_tab(), "Giao dịch")
        tabs.addTab(self._display_tab(), "Hiển thị")
        tabs.addTab(self._advanced_tab(), "Nâng cao")
        root.addWidget(tabs, 1)

    def _ai_tab(self) -> QFrame:
        frame = card()
        frame.layout().setSpacing(14)

        catalog_panel = QFrame()
        catalog_panel.setObjectName("CompactFormPanel")
        catalog_panel.setMinimumWidth(360)
        catalog_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        catalog_layout = QVBoxLayout(catalog_panel)
        catalog_layout.setContentsMargins(0, 0, 18, 0)
        catalog_layout.setSpacing(8)
        catalog_title = QLabel("1. Quản lý model theo nhà cung cấp")
        catalog_title.setObjectName("PanelTitle")
        catalog_layout.addWidget(catalog_title)

        self.ai_catalog_table = QTableWidget(0, 2)
        self.ai_catalog_table.setObjectName("DataTable")
        self.ai_catalog_table.setHorizontalHeaderLabels(["Nhà cung cấp", "Mô hình"])
        self.ai_catalog_table.verticalHeader().setVisible(False)
        self.ai_catalog_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.ai_catalog_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.ai_catalog_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.ai_catalog_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.ai_catalog_table.verticalHeader().setDefaultSectionSize(28)
        self.ai_catalog_table.setMinimumHeight(130)
        catalog_layout.addWidget(self.ai_catalog_table)

        self.ai_catalog_provider_input = QComboBox()
        self.ai_catalog_provider_input.addItems(FIXED_AI_PROVIDERS)
        self.ai_catalog_provider_input.setEditable(False)
        self.ai_catalog_model_input = QLineEdit()
        self.ai_catalog_model_input.setPlaceholderText("Nhập model")
        catalog_layout.addWidget(form_row("Nhà cung cấp", self.ai_catalog_provider_input))
        catalog_layout.addWidget(form_row("Mô hình", self.ai_catalog_model_input))

        catalog_button_container, catalog_button_row = self._aligned_button_row()
        self.ai_catalog_add_button = action_button("➕ Thêm", primary=True)
        self.ai_catalog_update_button = action_button("✏️ Sửa")
        self.ai_catalog_delete_button = action_button("🗑️ Xóa", primary=True, color="danger")
        catalog_button_row.addWidget(self.ai_catalog_add_button)
        catalog_button_row.addWidget(self.ai_catalog_update_button)
        catalog_button_row.addWidget(self.ai_catalog_delete_button)
        catalog_button_row.addStretch(1)
        catalog_layout.addWidget(catalog_button_container)

        api_panel = QFrame()
        api_panel.setObjectName("CompactFormPanel")
        api_panel.setMinimumWidth(420)
        api_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        api_layout = QVBoxLayout(api_panel)
        api_layout.setContentsMargins(18, 0, 0, 0)
        api_layout.setSpacing(8)
        api_title = QLabel("2. API key và cấu hình đang sử dụng")
        api_title.setObjectName("PanelTitle")
        api_layout.addWidget(api_title)

        self.ai_search_input = QLineEdit()
        self.ai_search_input.setPlaceholderText("Tìm nhà cung cấp, model hoặc khóa API")
        api_layout.addWidget(form_row("Tìm kiếm", self.ai_search_input))

        self.ai_table = QTableWidget(0, 4)
        self.ai_table.setObjectName("DataTable")
        self.ai_table.setHorizontalHeaderLabels(["Dùng", "Nhà cung cấp", "Mô hình", "Khóa API"])
        self.ai_table.verticalHeader().setVisible(False)
        self.ai_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.ai_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.ai_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.ai_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.ai_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.ai_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.ai_table.setMinimumHeight(150)
        self.ai_table.verticalHeader().setDefaultSectionSize(28)
        api_layout.addWidget(self.ai_table)

        self.ai_provider_combo = QComboBox()
        self.ai_provider_combo.addItems(self._ai_provider_names())
        self.ai_provider_combo.setEditable(False)
        self.ai_model_combo = QComboBox()
        self.ai_model_combo.setEditable(False)
        self.ai_api_key_input = QLineEdit()
        self.ai_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.ai_api_key_input.setPlaceholderText("Nhập khóa API")
        self._refresh_ai_models(self.app_settings.ai.provider, self.app_settings.ai.model)
        api_layout.addWidget(form_row("Nhà cung cấp", self.ai_provider_combo))
        api_layout.addWidget(form_row("Mô hình", self.ai_model_combo))
        api_layout.addWidget(form_row("Khóa API", self.ai_api_key_input))

        api_button_container, api_button_row = self._aligned_button_row()
        self.ai_test_button = action_button("🧪 Kiểm tra", primary=True, color="info")
        self.ai_save_button = action_button("💾 Lưu", primary=True, color="success")
        self.ai_delete_button = action_button("🗑️ Xóa", primary=True, color="danger")
        api_button_row.addWidget(self.ai_test_button)
        api_button_row.addWidget(self.ai_save_button)
        api_button_row.addWidget(self.ai_delete_button)
        api_button_row.addStretch(1)
        api_layout.addWidget(api_button_container)

        self.ai_status_label = QLabel("")
        self.ai_status_label.setObjectName("HelperText")
        self.ai_status_label.setWordWrap(True)
        self.ai_status_label.setVisible(False)
        api_layout.addWidget(self.ai_status_label)

        ai_splitter = QSplitter(Qt.Orientation.Horizontal)
        ai_splitter.setObjectName("SettingsAiSplitter")
        ai_splitter.setChildrenCollapsible(False)
        ai_splitter.addWidget(catalog_panel)
        ai_splitter.addWidget(api_panel)
        ai_splitter.setStretchFactor(0, 1)
        ai_splitter.setStretchFactor(1, 1)
        ai_splitter.setSizes([520, 620])

        frame.layout().addWidget(ai_splitter, 1)
        frame.layout().addStretch(1)

        self.ai_catalog_table.itemSelectionChanged.connect(self._load_selected_ai_catalog_item)
        self.ai_catalog_provider_input.currentTextChanged.connect(self._update_ai_button_state)
        self.ai_catalog_model_input.textChanged.connect(self._update_ai_button_state)
        self.ai_catalog_add_button.clicked.connect(self._add_ai_catalog_item)
        self.ai_catalog_update_button.clicked.connect(self._update_ai_catalog_item)
        self.ai_catalog_delete_button.clicked.connect(self._delete_ai_catalog_item)
        self.ai_provider_combo.currentTextChanged.connect(self._on_ai_provider_changed)
        self.ai_api_key_input.textChanged.connect(self._update_ai_button_state)
        self.ai_model_combo.currentTextChanged.connect(self._update_ai_button_state)
        self.ai_search_input.textChanged.connect(self._refresh_ai_table)
        self.ai_table.itemSelectionChanged.connect(self._load_selected_ai_provider)
        self.ai_test_button.clicked.connect(self._test_ai_key)
        self.ai_save_button.clicked.connect(self._save_ai_provider)
        self.ai_delete_button.clicked.connect(self._delete_ai_provider)
        self._refresh_ai_catalog_table()
        self._refresh_ai_table()
        self._update_ai_button_state()
        return frame

    def _aligned_button_row(self) -> tuple[QWidget, QHBoxLayout]:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 2, 0, 0)
        row.setSpacing(10)
        spacer = QWidget()
        spacer.setMinimumWidth(150)
        row.addWidget(spacer)
        return container, row

    def _set_compact_action_button(self, button: QPushButton) -> None:
        button.setProperty("compactPrimary", True)
        button.setProperty("compactSize", "add" if button.text() == "Thêm" else "save")
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        button.style().unpolish(button)
        button.style().polish(button)

    def _compact_form_row(self, label: str, field: QWidget, label_width: int = 132, field_width: int = 220) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        label_widget = QLabel(label)
        label_widget.setObjectName("FormLabel")
        label_widget.setFixedWidth(label_width)
        field.setFixedWidth(field_width)
        layout.addWidget(label_widget)
        layout.addWidget(field)
        layout.addStretch(1)
        return widget

    def _on_ai_provider_changed(self, provider: str) -> None:
        self._refresh_ai_models(provider)
        self._update_ai_button_state()

    def _refresh_ai_models(self, provider: str, selected_model: str | None = None) -> None:
        if not hasattr(self, "ai_model_combo"):
            return
        self.ai_model_combo.blockSignals(True)
        self.ai_model_combo.clear()
        models = self.ai_model_catalog.get(provider, [])
        self.ai_model_combo.addItems(models)
        if selected_model and selected_model in models:
            self.ai_model_combo.setCurrentText(selected_model)
        self.ai_model_combo.blockSignals(False)

    def _refresh_ai_catalog_table(self, select_provider: str | None = None, select_model: str | None = None) -> None:
        rows = [
            (provider, model)
            for provider, models in sorted(self.ai_model_catalog.items(), key=lambda item: item[0].lower())
            for model in sorted(models, key=str.lower)
        ]
        self.ai_catalog_table.blockSignals(True)
        self.ai_catalog_table.setRowCount(len(rows))
        selected_row = -1
        for row, (provider, model) in enumerate(rows):
            for col, value in enumerate([provider, model]):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, (provider, model))
                self.ai_catalog_table.setItem(row, col, item)
            if provider == select_provider and model == select_model:
                selected_row = row
        self.ai_catalog_table.blockSignals(False)
        if selected_row >= 0:
            self.ai_catalog_table.selectRow(selected_row)

    def _selected_ai_catalog_item(self) -> tuple[str, str] | None:
        if not hasattr(self, "ai_catalog_table"):
            return None
        row = self.ai_catalog_table.currentRow()
        if row < 0:
            return None
        item = self.ai_catalog_table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _load_selected_ai_catalog_item(self) -> None:
        selected = self._selected_ai_catalog_item()
        if selected:
            provider, model = selected
            self.ai_catalog_provider_input.setCurrentText(provider)
            self.ai_catalog_model_input.setText(model)
        self._update_ai_button_state()

    def _add_ai_catalog_item(self) -> None:
        provider = self.ai_catalog_provider_input.currentText().strip()
        model = self.ai_catalog_model_input.text().strip()
        if not provider or not model:
            self._set_ai_status("Nhập nhà cung cấp và mô hình trước khi thêm.", "error")
            return
        self.ai_catalog_table.clearSelection()
        self.ai_model_catalog = self.ai_catalog_service.add_provider_model(provider, model)
        provider = self._catalog_provider_key(provider)
        self._refresh_after_catalog_change(provider, model)
        self._set_ai_status("Đã thêm nhà cung cấp và model vào file JSON.", "ok")

    def _update_ai_catalog_item(self) -> None:
        selected = self._selected_ai_catalog_item()
        provider = self.ai_catalog_provider_input.currentText().strip()
        model = self.ai_catalog_model_input.text().strip()
        if not selected:
            self._set_ai_status("Chọn một dòng danh mục trước khi sửa.", "error")
            return
        if not provider or not model:
            self._set_ai_status("Nhập nhà cung cấp và mô hình trước khi sửa.", "error")
            return
        old_provider, old_model = selected
        self.ai_model_catalog = self.ai_catalog_service.update_provider_model(old_provider, old_model, provider, model)
        self._rename_ai_settings_provider_model(old_provider, old_model, provider, model)
        provider = self._catalog_provider_key(provider)
        self._refresh_after_catalog_change(provider, model)
        self._set_ai_status("Đã sửa nhà cung cấp và model trong file JSON.", "ok")

    def _delete_ai_catalog_item(self) -> None:
        selected = self._selected_ai_catalog_item()
        if not selected:
            self._set_ai_status("Chọn một dòng danh mục trước khi xóa.", "error")
            return
        provider, model = selected
        self.ai_model_catalog = self.ai_catalog_service.remove_provider_model(provider, model)
        providers = [
            item
            for item in self.app_settings.ai.providers
            if not (item.provider.lower() == provider.lower() and item.model.lower() == model.lower())
        ]
        if providers and not any(item.is_active for item in providers):
            providers[0].is_active = True
        self._save_ai_providers(providers)
        self._refresh_after_catalog_change()
        self._set_ai_status("Đã xóa nhà cung cấp/model và các API key liên quan.", "ok")

    def _refresh_after_catalog_change(self, select_provider: str | None = None, select_model: str | None = None) -> None:
        self._refresh_ai_catalog_table(select_provider, select_model)
        self._refresh_ai_provider_options(select_provider)
        self._refresh_ai_models(select_provider or self.ai_provider_combo.currentText(), select_model)
        self._refresh_ai_table(select_provider, select_model)
        self._update_ai_button_state()

    def _rename_ai_settings_provider_model(self, old_provider: str, old_model: str, new_provider: str, new_model: str) -> None:
        for item in self.app_settings.ai.providers:
            if item.provider.lower() == old_provider.lower() and item.model.lower() == old_model.lower():
                item.provider = new_provider
                item.model = new_model
        self._save_ai_providers(self.app_settings.ai.providers)

    def _update_ai_button_state(self) -> None:
        if not hasattr(self, "ai_provider_combo"):
            return
        selected_api = self._selected_ai_provider()
        has_key = bool(self.ai_api_key_input.text().strip() or (selected_api and selected_api.api_key))
        has_provider_model = bool(self.ai_provider_combo.currentText().strip() and self.ai_model_combo.currentText().strip())
        has_catalog_text = bool(self.ai_catalog_provider_input.currentText().strip() and self.ai_catalog_model_input.text().strip())
        self.ai_test_button.setEnabled(has_provider_model and has_key and self.ai_test_thread is None)
        self.ai_save_button.setEnabled(has_provider_model)
        self.ai_delete_button.setEnabled(self.ai_table.currentRow() >= 0)
        self.ai_catalog_add_button.setEnabled(has_catalog_text)
        self.ai_catalog_update_button.setEnabled(has_catalog_text and self.ai_catalog_table.currentRow() >= 0)
        self.ai_catalog_delete_button.setEnabled(self.ai_catalog_table.currentRow() >= 0)

    def _test_ai_key(self) -> None:
        if self.ai_test_thread is not None:
            return
        api_key = self.ai_api_key_input.text().strip()
        if not api_key:
            selected = self._selected_ai_provider()
            api_key = selected.api_key if selected else ""
        config = AIProviderConfig(
            provider=self.ai_provider_combo.currentText().strip(),
            model=self.ai_model_combo.currentText().strip(),
            api_key=api_key,
        )
        if not config.provider or not config.model or not config.api_key:
            self._set_ai_status("Thiếu nhà cung cấp, mô hình hoặc khóa API.", "error")
            return
        self.ai_test_button.setEnabled(False)
        self.ai_test_button.setText("Đang kiểm tra...")
        self._set_ai_status("Đang kiểm tra model AI...", "ok")

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
        self._set_ai_status("Khóa API hợp lệ.", "ok")

    def _ai_test_failed(self, message: str) -> None:
        self._set_ai_status(f"Không kiểm tra được khóa API: {message}", "error")

    def _ai_test_finished(self) -> None:
        self.ai_test_button.setText("Kiểm tra")
        self.ai_test_thread = None
        self.ai_test_worker = None
        self._update_ai_button_state()

    def _save_ai_provider(self) -> None:
        provider = self.ai_provider_combo.currentText().strip()
        model = self.ai_model_combo.currentText().strip()
        api_key = self.ai_api_key_input.text().strip()
        if not provider or not model:
            self._set_ai_status("Chọn nhà cung cấp và mô hình trước khi lưu API key.", "error")
            return
        if not api_key and not self._selected_ai_provider():
            self._set_ai_status("Nhập khóa API trước khi lưu cấu hình mới.", "error")
            return

        providers = list(self.app_settings.ai.providers)
        existing = next(
            (
                item
                for item in providers
                if item.provider.lower() == provider.lower() and item.model.lower() == model.lower()
            ),
            None,
        )
        if existing:
            if api_key:
                existing.api_key = api_key
                existing.api_key_ref = self._mask_api_key(api_key)
        else:
            providers.append(
                AIProviderSettings(
                    provider=provider,
                    model=model,
                    api_key=api_key,
                    api_key_ref=self._mask_api_key(api_key),
                    is_active=not providers,
                )
            )

        self._save_ai_providers(providers)
        self.ai_api_key_input.clear()
        self._refresh_ai_table(select_provider=provider, select_model=model)
        self._set_ai_status("Đã lưu API key theo nhà cung cấp và model.", "ok")

    def _delete_ai_provider(self) -> None:
        selected = self._selected_ai_provider()
        if not selected:
            return
        providers = [item for item in self.app_settings.ai.providers if item is not selected]
        if providers and not any(item.is_active for item in providers):
            providers[0].is_active = True
        self._save_ai_providers(providers)
        self.ai_api_key_input.clear()
        self._refresh_ai_table()
        self._set_ai_status("Đã xóa API key khỏi danh sách cấu hình.", "ok")

    def _save_ai_providers(self, providers: list[AIProviderSettings]) -> None:
        active = next((item for item in providers if item.is_active), providers[0] if providers else None)
        self.app_settings.ai = AISettings(
            provider=active.provider if active else "DeepSeek",
            model=active.model if active else DEFAULT_DEEPSEEK_MODEL,
            api_key_ref=active.api_key_ref if active else None,
            providers=providers,
        )
        self.settings_service.save(self.app_settings)

    def _ai_provider_names(self) -> list[str]:
        return list(FIXED_AI_PROVIDERS)

    def _catalog_provider_key(self, provider: str) -> str:
        return next((name for name in self.ai_model_catalog if name.lower() == provider.lower()), provider)

    def _refresh_ai_provider_options(self, selected_provider: str | None = None) -> None:
        self.ai_provider_combo.blockSignals(True)
        self.ai_provider_combo.clear()
        self.ai_provider_combo.addItems(self._ai_provider_names())
        if selected_provider and selected_provider in self._ai_provider_names():
            self.ai_provider_combo.setCurrentText(selected_provider)
        self.ai_provider_combo.blockSignals(False)

    def _mask_api_key(self, api_key: str) -> str | None:
        if not api_key:
            return None
        if len(api_key) <= 8:
            return "****"
        return f"{api_key[:3]}-****{api_key[-4:]}"

    def _refresh_ai_table(self, select_provider: str | None = None, select_model: str | None = None) -> None:
        if not hasattr(self, "ai_table"):
            return
        query = self.ai_search_input.text().strip().lower() if hasattr(self, "ai_search_input") else ""
        providers = [
            item
            for item in self.app_settings.ai.providers
            if not query
            or query in item.provider.lower()
            or query in item.model.lower()
            or query in (item.api_key_ref or "").lower()
        ]

        self.ai_table.blockSignals(True)
        self.ai_table.setRowCount(len(providers))
        selected_row = -1
        for row, item in enumerate(providers):
            active_item = QTableWidgetItem("")
            active_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            active_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            active_item.setData(Qt.ItemDataRole.UserRole, item)
            self.ai_table.setItem(row, 0, active_item)
            self.ai_table.setCellWidget(row, 0, self._active_provider_cell(item))

            values = [item.provider, item.model, item.api_key_ref or self._mask_api_key(item.api_key) or "Chưa có"]
            for col, value in enumerate(values, start=1):
                table_item = QTableWidgetItem(value)
                table_item.setData(Qt.ItemDataRole.UserRole, item)
                self.ai_table.setItem(row, col, table_item)

            if select_provider == item.provider and select_model == item.model:
                selected_row = row

        self.ai_table.blockSignals(False)
        if selected_row >= 0:
            self.ai_table.selectRow(selected_row)
        elif providers:
            self.ai_table.selectRow(0)
        self._update_ai_button_state()

    def _selected_ai_provider(self) -> AIProviderSettings | None:
        if not hasattr(self, "ai_table"):
            return None
        row = self.ai_table.currentRow()
        if row < 0:
            return None
        item = self.ai_table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _load_selected_ai_provider(self) -> None:
        selected = self._selected_ai_provider()
        if not selected:
            self._update_ai_button_state()
            return
        self.ai_provider_combo.blockSignals(True)
        self.ai_provider_combo.setCurrentText(selected.provider)
        self.ai_provider_combo.blockSignals(False)
        self._refresh_ai_models(selected.provider, selected.model)
        self.ai_api_key_input.clear()
        self._update_ai_button_state()

    def _active_provider_cell(self, provider: AIProviderSettings) -> QWidget:
        cell = QWidget()
        cell.setObjectName("ActiveProviderCell")
        layout = QHBoxLayout(cell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        button = QPushButton("✓")
        button.setObjectName("ActiveProviderCheck")
        button.setCheckable(True)
        button.setChecked(provider.is_active)
        button.setFixedSize(14, 14)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(
            lambda checked, selected=provider: self._activate_ai_provider(selected)
            if checked
            else self._refresh_ai_table(select_provider=selected.provider, select_model=selected.model)
        )
        layout.addStretch(1)
        layout.addWidget(button)
        layout.addStretch(1)
        return cell

    def _activate_ai_provider(self, selected: AIProviderSettings) -> None:
        providers = self.app_settings.ai.providers
        for provider in providers:
            provider.is_active = provider is selected
        self._save_ai_providers(providers)
        self._refresh_ai_table(select_provider=selected.provider, select_model=selected.model)
        self._set_ai_status(f"Đang sử dụng {selected.provider} / {selected.model}.", "ok")

    def _set_ai_status(self, text: str, state: str) -> None:
        self.ai_status_label.setText(text)
        self.ai_status_label.setProperty("state", state)
        self.ai_status_label.setVisible(bool(text))
        self.ai_status_label.style().unpolish(self.ai_status_label)
        self.ai_status_label.style().polish(self.ai_status_label)

    def _mt5_tab(self) -> QWidget:
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(16)
        
        frame = card("Nguồn dữ liệu")
        frame.layout().setSpacing(8)
        
        def _col(t, w):
            l = QLabel(t)
            l.setObjectName("FormLabel")
            l.setStyleSheet("color: #9CA3AF; font-size: 11px;")
            v = QVBoxLayout()
            v.setSpacing(4)
            v.setContentsMargins(0, 0, 0, 0)
            v.addWidget(l)
            v.addWidget(w)
            return v

        top_grid = QGridLayout()
        top_grid.setContentsMargins(0, 0, 0, 0)
        top_grid.setSpacing(12)
        
        self.data_source_combo = QComboBox()
        self.data_source_combo.addItems(["MetaTrader 5", "cTrader"])
        self.data_source_combo.setFixedWidth(160)
        current_ds = self.app_settings.data_source
        if current_ds == "ctrader":
            self.data_source_combo.setCurrentText("cTrader")
        else:
            self.data_source_combo.setCurrentText("MetaTrader 5")
            
        top_grid.addLayout(_col("Nguồn dữ liệu", self.data_source_combo), 0, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        
        # cTrader credentials
        self.ctrader_panel = QFrame()
        
        ctrader_layout = QHBoxLayout(self.ctrader_panel)
        ctrader_layout.setContentsMargins(0, 0, 0, 0)
        ctrader_layout.setSpacing(12)
        
        self.ctrader_env = QComboBox()
        self.ctrader_env.addItems(["Demo", "Live"])
        self.ctrader_env.setCurrentText("Live" if self.app_settings.ctrader.environment == "live" else "Demo")
        
        self.ctrader_id = QLineEdit(self.app_settings.ctrader.client_id)
        self.ctrader_id.setPlaceholderText("Nhập Client ID")
        
        self.ctrader_secret = QLineEdit(self.app_settings.ctrader.client_secret)
        self.ctrader_secret.setPlaceholderText("Nhập Client Secret")
        self.ctrader_secret.setEchoMode(QLineEdit.EchoMode.Password)
        
        self.ctrader_token = QLineEdit(self.app_settings.ctrader.access_token)
        self.ctrader_token.setPlaceholderText("Nhập Access Token")
        self.ctrader_token.setEchoMode(QLineEdit.EchoMode.Password)
        
        acc_id = self.app_settings.ctrader.account_id
        self.ctrader_acc = QLineEdit("" if not acc_id else str(acc_id))
        self.ctrader_acc.setPlaceholderText("Ví dụ: 12345678")

        ctrader_layout.addLayout(_col("Môi trường", self.ctrader_env), 1)
        ctrader_layout.addLayout(_col("Account ID", self.ctrader_acc), 1)
        ctrader_layout.addLayout(_col("Client ID", self.ctrader_id), 2)
        ctrader_layout.addLayout(_col("Client Secret", self.ctrader_secret), 3)
        ctrader_layout.addLayout(_col("Access Token", self.ctrader_token), 3)
        
        top_grid.addWidget(self.ctrader_panel, 0, 1)
        top_grid.setColumnStretch(1, 1)
        
        # Row 1: Buttons
        btn_layout = QHBoxLayout()
        self.creds_save_btn = action_button("💾 Lưu cấu hình nguồn", primary=True)
        self.creds_save_btn.clicked.connect(self._save_credentials)
        btn_layout.addWidget(self.creds_save_btn)
        
        self.app_restart_btn = action_button("🔄 Khởi động lại", primary=True, color="danger")
        self.app_restart_btn.clicked.connect(self._restart_app)
        self.app_restart_btn.setVisible(False)
        btn_layout.addWidget(self.app_restart_btn)
        btn_layout.addStretch(1)
        
        top_grid.addLayout(btn_layout, 1, 0, 1, 2)
        
        # Row 2: Status
        self.data_source_status_label = QLabel("")
        self.data_source_status_label.setObjectName("HelperText")
        self.data_source_status_label.setWordWrap(True)
        self.data_source_status_label.setVisible(False)
        top_grid.addWidget(self.data_source_status_label, 2, 0, 1, 2)
        
        frame.layout().addLayout(top_grid)
        
        main_layout.addWidget(frame)
        
        frame2 = card("Kiểm tra & Cấu hình mã")
        frame2.layout().setSpacing(8)
        
        # Connect visibility toggle
        self.data_source_combo.currentTextChanged.connect(self._toggle_ctrader_panel)
        self._toggle_ctrader_panel(self.data_source_combo.currentText())

        self.mt5_status_label = QLabel("Đang kiểm tra dữ liệu...")
        self.mt5_status_label.setObjectName("HelperText")
        self.mt5_detail_label = QLabel("")
        self.mt5_detail_label.setObjectName("HelperText")
        self.mt5_detail_label.setWordWrap(True)
        self.mt5_retry_button = action_button("🔄 Thử kết nối lại", primary=True, color="info")
        self.mt5_retry_button.clicked.connect(self.refresh_mt5_status)

        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        status_text = QVBoxLayout()
        status_text.setSpacing(3)
        status_text.addWidget(self.mt5_status_label)
        status_text.addWidget(self.mt5_detail_label)
        status_row.addLayout(status_text, 1)
        status_row.addWidget(self.mt5_retry_button)
        frame2.layout().addLayout(status_row)

        self.mt5_display_symbols = sorted(SUPPORTED_SYMBOLS)
        self.mt5_symbols_table = QTableWidget(len(self.mt5_display_symbols), 10)
        self.mt5_symbols_table.setObjectName("DataTable")
        self.mt5_symbols_table.setProperty("tableRole", "mt5Symbols")
        self.mt5_symbols_table.setHorizontalHeaderLabels([
            "STT", "Mã hiển thị", "Mã broker trong MT5", "Trạng thái",
            "Kiểm tra", "Kiểm thử", "Điểm tối thiểu", "Regime tự động", "Hướng tự động", "RR tối thiểu",
        ])
        self.mt5_symbols_table.verticalHeader().setVisible(False)
        self.mt5_symbols_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.mt5_symbols_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.mt5_symbols_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.mt5_symbols_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.mt5_symbols_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.mt5_symbols_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.mt5_symbols_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.mt5_symbols_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.mt5_symbols_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self.mt5_symbols_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        self.mt5_symbols_table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)
        self.mt5_symbols_table.horizontalHeader().setSectionResizeMode(9, QHeaderView.ResizeMode.Fixed)
        self.mt5_symbols_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.mt5_symbols_table.horizontalHeader().setMinimumSectionSize(56)
        self.mt5_symbols_table.setColumnWidth(6, 112)
        self.mt5_symbols_table.setColumnWidth(7, 144)
        self.mt5_symbols_table.setColumnWidth(8, 116)
        self.mt5_symbols_table.setColumnWidth(9, 118)
        for row, symbol in enumerate(self.mt5_display_symbols):
            for col, value in enumerate([str(row + 1), symbol, "--", "Chưa kiểm tra", "--", "", ""]):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.mt5_symbols_table.setItem(row, col, item)
            symbol_config = self.app_settings.trading.symbol_settings.get(symbol, SymbolScanSettings())
            backtest_box = QCheckBox()
            backtest_box.setChecked(symbol_config.backtest)
            backtest_box.setToolTip("Tick nếu mã này đã backtest và được phép đưa vào scanner.")
            self.mt5_symbols_table.setCellWidget(row, 5, self._centered_cell(backtest_box))
            min_score = QLineEdit(str(symbol_config.min_score))
            min_score.setObjectName("Mt5MinScoreInput")
            min_score.setValidator(QIntValidator(0, 100, min_score))
            min_score.setMaxLength(3)
            min_score.setFixedWidth(76)
            min_score.setAlignment(Qt.AlignmentFlag.AlignCenter)
            min_score.setEnabled(symbol_config.backtest)
            min_score.setToolTip("Ngưỡng final score nhỏ nhất để scanner coi là đủ điều kiện. 0 = không lọc.")
            backtest_box.toggled.connect(min_score.setEnabled)
            self.mt5_symbols_table.setCellWidget(row, 6, self._centered_cell(min_score))

            # Auto Regime dropdown
            regime_combo = QComboBox()
            regime_combo.addItems(["", "range", "trend_up", "trend_down", "volatile"])
            regime_combo.setCurrentText(symbol_config.auto_trade_regime or "")
            regime_combo.setEnabled(symbol_config.backtest)
            regime_combo.setFixedWidth(122)
            regime_combo.setToolTip("Chỉ auto-trade khi market regime khớp. Để trống nếu không lọc.")
            backtest_box.toggled.connect(regime_combo.setEnabled)
            self.mt5_symbols_table.setCellWidget(row, 7, self._centered_cell(regime_combo))

            # Auto Side dropdown
            side_combo = QComboBox()
            side_combo.addItems(["best", "buy", "sell"])
            side_combo.setCurrentText(symbol_config.auto_trade_side or "best")
            side_combo.setEnabled(symbol_config.backtest)
            side_combo.setFixedWidth(92)
            side_combo.setToolTip("Hướng auto-trade. 'best' = dùng best_side từ phân tích.")
            backtest_box.toggled.connect(side_combo.setEnabled)
            self.mt5_symbols_table.setCellWidget(row, 8, self._centered_cell(side_combo))

            # Min RR spinbox
            min_rr = QDoubleSpinBox()
            min_rr.setRange(0.0, 10.0)
            min_rr.setSingleStep(0.1)
            min_rr.setDecimals(1)
            min_rr.setValue(symbol_config.auto_trade_min_rr)
            min_rr.setEnabled(symbol_config.backtest)
            min_rr.setObjectName("Mt5MinRrInput")
            min_rr.setFixedWidth(96)
            min_rr.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
            min_rr.setAlignment(Qt.AlignmentFlag.AlignCenter)
            min_rr.setToolTip("R:R kỳ vọng tối thiểu để auto-trade. 0 = không lọc.")
            backtest_box.toggled.connect(min_rr.setEnabled)
            self.mt5_symbols_table.setCellWidget(row, 9, self._centered_cell(min_rr))
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
            "trong màn hình Backtest) và tự động điền vào bảng."
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
        status = self.data_provider.connection_status()
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

        available_symbols = self.data_provider.available_symbols(market_watch_only=True)
        if not available_symbols:
            for row, symbol in enumerate(self.mt5_display_symbols):
                self._set_mt5_symbol_row(row, symbol, "--", "Không có mã khả dụng", "Kiểm tra nguồn dữ liệu")
            return

        for row, symbol in enumerate(self.mt5_display_symbols):
            broker_symbol = self.data_provider.resolve_symbol(symbol, available_symbols)
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
            if col == 0:
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

    def _centered_cell(self, widget: QWidget, *, vertical_margin: int = 0) -> QWidget:
        cell = QWidget()
        layout = QHBoxLayout(cell)
        layout.setContentsMargins(0, vertical_margin, 0, vertical_margin)
        layout.addStretch(1)
        layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)
        return cell

    def _save_credentials(self) -> None:
        ds_map = {"MetaTrader 5": "mt5", "cTrader": "ctrader"}
        self.app_settings.data_source = ds_map.get(self.data_source_combo.currentText(), "mt5")
        self.app_settings.ctrader.client_id = self.ctrader_id.text().strip()
        self.app_settings.ctrader.client_secret = self.ctrader_secret.text().strip()
        self.app_settings.ctrader.access_token = self.ctrader_token.text().strip()
        self.app_settings.ctrader.account_id = int(self.ctrader_acc.text().strip() or 0)
        self.app_settings.ctrader.environment = "live" if self.ctrader_env.currentText() == "Live" else "demo"
        self.settings_service.save(self.app_settings)
        if self.app:
            self.app.switch_data_source(self.app_settings.data_source)
        if hasattr(self, "data_source_status_label"):
            self.data_source_status_label.setText("Đã lưu cấu hình. Hãy khởi động lại ứng dụng nếu đổi nguồn dữ liệu.")
            self.data_source_status_label.setProperty("state", "ok")
            self.data_source_status_label.setVisible(True)
            self.data_source_status_label.style().unpolish(self.data_source_status_label)
            self.data_source_status_label.style().polish(self.data_source_status_label)
        if hasattr(self, "app_restart_btn"):
            self.app_restart_btn.setVisible(True)

    def _toggle_ctrader_panel(self, text: str) -> None:
        if hasattr(self, "ctrader_panel"):
            self.ctrader_panel.setVisible(text == "cTrader")
            
    def _restart_app(self) -> None:
        import sys
        import subprocess
        from PyQt6.QtWidgets import QApplication
        subprocess.Popen([sys.executable] + sys.argv)
        QApplication.quit()

    def _paste_backtest_configs(self) -> None:
        """Read backtest config JSON from clipboard and fill the MT5 symbols table."""
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

        updated = 0
        for row, symbol in enumerate(self.mt5_display_symbols):
            cfg = configs.get(symbol)
            if cfg is None or not isinstance(cfg, dict):
                continue

            # Tick "Kiểm thử" checkbox (col 5)
            backtest_cell = self.mt5_symbols_table.cellWidget(row, 5)
            if isinstance(backtest_cell, QWidget):
                cb = backtest_cell.findChild(QCheckBox)
                if cb and not cb.isChecked():
                    cb.setChecked(True)

            # Set "Điểm tối thiểu" (col 6)
            min_score_val = cfg.get("min_score", 0)
            if min_score_val:
                min_score_cell = self.mt5_symbols_table.cellWidget(row, 6)
                if isinstance(min_score_cell, QWidget):
                    le = min_score_cell.findChild(QLineEdit)
                    if le:
                        le.setText(str(min_score_val))

            # Set "Regime tự động" (col 7)
            regime_val = cfg.get("regime", "")
            if regime_val:
                regime_cell = self.mt5_symbols_table.cellWidget(row, 7)
                if isinstance(regime_cell, QWidget):
                    combo = regime_cell.findChild(QComboBox)
                    if combo:
                        idx = combo.findText(regime_val)
                        if idx >= 0:
                            combo.setCurrentIndex(idx)

            # Set "Hướng tự động" (col 8)
            side_val = cfg.get("side", "")
            if side_val:
                side_cell = self.mt5_symbols_table.cellWidget(row, 8)
                if isinstance(side_cell, QWidget):
                    combo = side_cell.findChild(QComboBox)
                    if combo:
                        idx = combo.findText(side_val)
                        if idx >= 0:
                            combo.setCurrentIndex(idx)

            # Set "RR tối thiểu" (col 9)
            rr_val = cfg.get("min_rr", 0)
            if rr_val:
                rr_cell = self.mt5_symbols_table.cellWidget(row, 9)
                if isinstance(rr_cell, QWidget):
                    spin = rr_cell.findChild(QDoubleSpinBox)
                    if spin:
                        spin.setValue(float(rr_val))

            updated += 1

        if updated:
            QMessageBox.information(
                self, "Đã dán",
                f"Đã cập nhật cấu hình cho {updated} cặp.\n"
                "Nhấn '💾 Lưu cấu hình mã quét' để lưu lại."
            )
        else:
            QMessageBox.information(
                self, "Không khớp",
                "Không tìm thấy cặp nào trong bảng khớp với dữ liệu clipboard."
            )

    def _save_mt5_symbol_settings(self) -> None:
        symbol_settings: dict[str, SymbolScanSettings] = {}
        enabled_symbols: list[str] = []
        for row, symbol in enumerate(self.mt5_display_symbols):
            backtest_cell = self.mt5_symbols_table.cellWidget(row, 5)
            min_score_cell = self.mt5_symbols_table.cellWidget(row, 6)
            regime_cell = self.mt5_symbols_table.cellWidget(row, 7)
            side_cell = self.mt5_symbols_table.cellWidget(row, 8)
            min_rr_cell = self.mt5_symbols_table.cellWidget(row, 9)
            backtest_box = backtest_cell.findChild(QCheckBox) if backtest_cell else None
            min_score_input = min_score_cell.findChild(QLineEdit) if min_score_cell else None
            regime_combo = regime_cell.findChild(QComboBox) if regime_cell else None
            side_combo = side_cell.findChild(QComboBox) if side_cell else None
            min_rr_spin = min_rr_cell.findChild(QDoubleSpinBox) if min_rr_cell else None
            backtested = bool(backtest_box and backtest_box.isChecked())
            min_score = int(min_score_input.text() or 0) if min_score_input else 0
            regime = str(regime_combo.currentText() or "").strip() if regime_combo else ""
            side = str(side_combo.currentText() or "").strip() if side_combo else ""
            min_rr = float(min_rr_spin.value() or 0) if min_rr_spin else 0.0
            symbol_settings[symbol] = SymbolScanSettings(
                backtest=backtested,
                min_score=min_score,
                auto_trade_regime=regime,
                auto_trade_side=side,
                auto_trade_min_rr=min_rr,
            )
            if backtested:
                enabled_symbols.append(symbol)
        self.app_settings.trading.symbol_settings = symbol_settings
        self.app_settings.trading.enabled_symbols = enabled_symbols
        self.settings_service.save(self.app_settings)
        self.mt5_status_label.setText("Đã lưu cấu hình mã quét.")
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
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(6)

        balance = QDoubleSpinBox()
        balance.setRange(0, 1_000_000_000)
        balance.setDecimals(0)
        balance.setGroupSeparatorShown(True)
        balance.setSingleStep(100)
        mt5_balance = self.data_provider.account_balance()
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

        contract_size = QDoubleSpinBox()
        contract_size.setRange(0, 100_000_000)
        contract_size.setDecimals(0)
        contract_size.setGroupSeparatorShown(True)
        contract_size.setSingleStep(1000)
        contract_size.setValue(trading.contract_size_override)
        contract_size.setSuffix(" units")

        self.trading_balance_input = balance
        self.trading_currency_input = currency
        self.trading_risk_input = risk
        self.trading_max_risk_input = max_risk
        self.trading_lot_step_input = lot_step
        self.trading_minimum_lot_input = minimum_lot
        self.trading_contract_size_input = contract_size

        form_layout.addWidget(self._compact_form_row("Số dư MT5", balance))
        form_layout.addWidget(self._compact_form_row("Đồng tiền", currency))
        form_layout.addWidget(self._compact_form_row("Rủi ro mỗi lệnh", risk))
        form_layout.addWidget(self._compact_form_row("Rủi ro tối đa", max_risk))
        form_layout.addWidget(self._compact_form_row("Bước lot", lot_step))
        form_layout.addWidget(self._compact_form_row("Lot tối thiểu", minimum_lot))
        form_layout.addWidget(self._compact_form_row("Quy mô hợp đồng", contract_size))

        button_container = QWidget()
        button_row = QHBoxLayout(button_container)
        button_row.setContentsMargins(0, 2, 0, 0)
        button_row.setSpacing(8)
        button_spacer = QWidget()
        button_spacer.setFixedWidth(132)
        button_row.addWidget(button_spacer)
        self.trading_save_button = action_button("💾 Lưu cài đặt giao dịch", primary=True, color="success")
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
            contract_size_override=self.trading_contract_size_input.value(),
            max_daily_loss_pct=self.app_settings.trading.max_daily_loss_pct,
            max_weekly_loss_pct=self.app_settings.trading.max_weekly_loss_pct,
            max_consecutive_losses=self.app_settings.trading.max_consecutive_losses,
            max_open_risk_pct=self.app_settings.trading.max_open_risk_pct,
            enabled_symbols=self.app_settings.trading.enabled_symbols,
            symbol_settings=self.app_settings.trading.symbol_settings,
        )
        self.settings_service.save(self.app_settings)
        self.trading_status_label.setText("Đã lưu cài đặt giao dịch.")
        self.trading_status_label.setProperty("state", "ok")
        self.trading_status_label.style().unpolish(self.trading_status_label)
        self.trading_status_label.style().polish(self.trading_status_label)

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
