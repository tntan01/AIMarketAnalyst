"""Application controller — dependency-injection container (CT-4).

Owns singleton instances of app-wide services and controllers so they are
created exactly once and shared across screens.  Every screen receives
the same ``AppController`` via ``MainWindow`` and pulls the dependencies it
needs from it. Per-provider clients such as ``AIService`` are created by
factory method because their config changes at runtime.
"""

from __future__ import annotations

from controllers.backtest_controller import BacktestController
from controllers.journal_controller import JournalController
from controllers.scanner_controller import ScannerController
from controllers.settings_controller import SettingsController
from services.ai_provider_catalog_service import AIProviderCatalogService
from services.ai_service import AIProviderConfig, AIService
from services.journal_service import JournalService
from services.mt5_service import MT5Service
from services.news_service import NewsService
from services.order_management_service import OrderManagementService
from services.settings_service import SettingsService
from services.telegram_alert_service import TelegramAlertService


class AppController:
    """Central DI container — every service is a lazy singleton property.

    Usage in ``main.py``::

        app_ctrl = AppController()
        window = MainWindow(app_ctrl)

    Usage in a screen::

        self.mt5 = self.app.mt5
        self.settings = self.app.settings_service
    """

    def __init__(self) -> None:
        # Lazy-initialised singletons
        self._settings_service: SettingsService | None = None
        self._mt5: MT5Service | None = None
        self._news_service: NewsService | None = None
        self._journal_service: JournalService | None = None
        self._ai_catalog_service: AIProviderCatalogService | None = None
        self._telegram_service: TelegramAlertService | None = None
        self._order_management_service: OrderManagementService | None = None

        # Controllers (also lazy)
        self._scanner_controller: ScannerController | None = None
        self._backtest_controller: BacktestController | None = None
        self._journal_controller: JournalController | None = None
        self._settings_controller: SettingsController | None = None

        # Load settings eagerly — nearly every screen needs them
        self.settings = self.settings_service.load()

    # -- services ----------------------------------------------------------

    @property
    def settings_service(self) -> SettingsService:
        if self._settings_service is None:
            self._settings_service = SettingsService()
        return self._settings_service

    @property
    def mt5(self) -> MT5Service:
        if self._mt5 is None:
            self._mt5 = MT5Service()
        return self._mt5

    @property
    def news_service(self) -> NewsService:
        if self._news_service is None:
            self._news_service = NewsService()
        return self._news_service

    @property
    def journal_service(self) -> JournalService:
        if self._journal_service is None:
            self._journal_service = JournalService()
        return self._journal_service

    def create_ai_service(self, config: AIProviderConfig) -> AIService:
        return AIService(config)

    @property
    def ai_catalog_service(self) -> AIProviderCatalogService:
        if self._ai_catalog_service is None:
            self._ai_catalog_service = AIProviderCatalogService()
        return self._ai_catalog_service

    @property
    def telegram_service(self) -> TelegramAlertService:
        if self._telegram_service is None:
            self._telegram_service = TelegramAlertService()
        return self._telegram_service

    @property
    def order_management_service(self) -> OrderManagementService:
        if self._order_management_service is None:
            self._order_management_service = OrderManagementService(
                self.mt5,
                feature_enabled=self.settings.features.order_management_v2,
                rollout_settings=self.settings.order_management,
            )
        return self._order_management_service

    def shutdown(self) -> None:
        """Release application-owned resources without creating new services.

        First waits (bounded) for an in-flight scanner aftercare persistence
        job so a scan running while the app closes cannot corrupt its snapshot;
        jobs that exceed the budget are recorded as interrupted (mục 19.2).
        MT5 is always disconnected, even if the wait fails unexpectedly.
        """
        try:
            try:
                if self._scanner_controller is not None:
                    self._scanner_controller.wait_for_aftercare_shutdown()
            finally:
                if self._order_management_service is not None:
                    self._order_management_service.shutdown()
        finally:
            if self._mt5 is not None:
                self._mt5.disconnect()

    # -- controllers -------------------------------------------------------

    @property
    def scanner_controller(self) -> ScannerController:
        if self._scanner_controller is None:
            self._scanner_controller = ScannerController(
                settings_service=self.settings_service,
                mt5=self.mt5,
                news_service=self.news_service,
                telegram_service=self.telegram_service,
                journal_service=self.journal_service,
                order_management_service=self.order_management_service,
            )
        return self._scanner_controller

    @property
    def backtest_controller(self) -> BacktestController:
        if self._backtest_controller is None:
            self._backtest_controller = BacktestController(
                settings_service=self.settings_service,
                mt5=self.mt5,
            )
        return self._backtest_controller

    @property
    def journal_controller(self) -> JournalController:
        if self._journal_controller is None:
            self._journal_controller = JournalController(
                journal_service=self.journal_service,
                mt5=self.mt5,
            )
        return self._journal_controller

    @property
    def settings_controller(self) -> SettingsController:
        if self._settings_controller is None:
            self._settings_controller = SettingsController(service=self.settings_service)
        return self._settings_controller
