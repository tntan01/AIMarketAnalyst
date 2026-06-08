from __future__ import annotations

from services.settings_service import SettingsService


class AppController:
    def __init__(self, settings_service: SettingsService | None = None) -> None:
        self.settings_service = settings_service or SettingsService()
        self.settings = self.settings_service.load()
