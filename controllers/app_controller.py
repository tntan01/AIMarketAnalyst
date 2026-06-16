"""Application controller — dependency-injection container (CT-4).

Owns singleton instances of all services and controllers so they are
created exactly once and shared across screens.  Every screen receives
the same ``AppController`` via ``MainWindow`` and pulls the services it
needs from it.
"""

from __future__ import annotations

from controllers.backtest_controller import BacktestController
from controllers.journal_controller import JournalController
from controllers.scanner_controller import ScannerController
from controllers.settings_controller import SettingsController
from services.ai_provider_catalog_service import AIProviderCatalogService
from services.ai_service import AIService
from services.journal_service import JournalService
from services.mt5_service import MT5Service
from services.news_service import NewsService
from services.settings_service import SettingsService
from services.telegram_alert_service import TelegramAlertService


class AppController:
    """Central DI container — every service is a lazy singleton property.

    Usage in ``main.py``::

        app_ctrl = AppController()
        window = MainWindow(app_ctrl)

    Usage in a screen::

        self.mt5 = self.app.mt5_service
        self.settings = self.app.settings_service
    """

    def __init__(self) -> None:
        # Lazy-initialised singletons
        self._settings_service: SettingsService | None = None
        self._mt5_service: MT5Service | None = None
        self._news_service: NewsService | None = None
        self._journal_service: JournalService | None = None
        self._ai_service: AIService | None = None
        self._ai_catalog_service: AIProviderCatalogService | None = None
        self._telegram_service: TelegramAlertService | None = None

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
    def mt5_service(self) -> MT5Service:
        if self._mt5_service is None:
            self._mt5_service = MT5Service()
        return self._mt5_service

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

    @property
    def ai_service(self) -> AIService:
        if self._ai_service is None:
            self._ai_service = AIService()
        return self._ai_service

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

    # -- controllers -------------------------------------------------------

    @property
    def scanner_controller(self) -> ScannerController:
        if self._scanner_controller is None:
            self._scanner_controller = ScannerController(
                settings_service=self.settings_service,
                mt5_service=self.mt5_service,
                news_service=self.news_service,
                telegram_service=self.telegram_service,
                journal_service=self.journal_service,
            )
        return self._scanner_controller

    @property
    def backtest_controller(self) -> BacktestController:
        if self._backtest_controller is None:
            self._backtest_controller = BacktestController(
                settings_service=self.settings_service,
                mt5_service=self.mt5_service,
            )
        return self._backtest_controller

    @property
    def journal_controller(self) -> JournalController:
        if self._journal_controller is None:
            self._journal_controller = JournalController(
                journal_service=self.journal_service,
                mt5_service=self.mt5_service,
            )
        return self._journal_controller

    @property
    def settings_controller(self) -> SettingsController:
        if self._settings_controller is None:
            self._settings_controller = SettingsController(service=self.settings_service)
        return self._settings_controller
