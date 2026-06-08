from __future__ import annotations

from config.settings import AppSettings
from services.settings_service import SettingsService


class SettingsController:
    def __init__(self, service: SettingsService | None = None) -> None:
        self.service = service or SettingsService()

    def save(self, settings: AppSettings) -> None:
        self.service.save(settings)
