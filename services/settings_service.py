from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from config.paths import settings_path
from config.constants import DEEPSEEK_MODELS, DEFAULT_DEEPSEEK_MODEL
from config.settings import (
    AdvancedSettings,
    AppSettings,
    AIProviderSettings,
    AISettings,
    DisplaySettings,
    NotificationSettings,
    SymbolScanSettings,
    TradingSettings,
    default_settings,
)
from services.storage_service import JsonStorage


class SettingsService:
    def __init__(self, path: Path | None = None) -> None:
        self.storage = JsonStorage(path or settings_path())

    def load(self) -> AppSettings:
        data = self.storage.load()
        if not data:
            return default_settings()
        ai = self._load_ai_settings(data.get("ai", {}))
        return AppSettings(
            ai=ai,
            trading=self._load_trading_settings(data.get("trading", {})),
            display=self._load_display_settings(data.get("display", {}), data.get("language", "vi")),
            advanced=self._load_advanced_settings(data.get("advanced", {})),
            notifications=self._load_notification_settings(data.get("notifications", {})),
            default_symbol=data.get("default_symbol", "EUR/USD"),
            default_timeframe=data.get("default_timeframe", "H1"),
            language=data.get("language", "vi"),
        )

    def save(self, settings: AppSettings) -> None:
        self.storage.save(asdict(settings))

    def _load_ai_settings(self, data: dict | None) -> AISettings:
        data = data or {}
        providers = [
            AIProviderSettings(
                provider=item.get("provider", ""),
                model=self._normalize_ai_model(item.get("provider", ""), item.get("model", "")),
                api_key=item.get("api_key", ""),
                api_key_ref=item.get("api_key_ref"),
                is_active=bool(item.get("is_active", False)),
            )
            for item in data.get("providers", [])
            if item.get("provider") and item.get("model")
        ]

        if not providers and data.get("provider") and data.get("model"):
            providers.append(
                AIProviderSettings(
                    provider=data.get("provider", ""),
                    model=self._normalize_ai_model(data.get("provider", ""), data.get("model", "")),
                    api_key_ref=data.get("api_key_ref"),
                    is_active=True,
                )
            )

        active = next((item for item in providers if item.is_active), None)
        if providers and active is None:
            providers[0].is_active = True
            active = providers[0]

        return AISettings(
            provider=(active.provider if active else data.get("provider", "DeepSeek")),
            model=(
                active.model
                if active
                else self._normalize_ai_model(data.get("provider", "DeepSeek"), data.get("model", DEFAULT_DEEPSEEK_MODEL))
            ),
            api_key_ref=(active.api_key_ref if active else data.get("api_key_ref")),
            providers=providers,
        )

    def _normalize_ai_model(self, provider: str, model: str) -> str:
        provider_name = str(provider or "").strip().lower()
        model_name = str(model or "").strip()
        if provider_name == "deepseek" and model_name not in DEEPSEEK_MODELS:
            return DEFAULT_DEEPSEEK_MODEL
        return model_name

    def _load_trading_settings(self, data: dict | None) -> TradingSettings:
        data = data or {}
        raw_enabled = data.get("enabled_symbols")
        enabled: list[str] = []
        if isinstance(raw_enabled, list):
            enabled = [str(s) for s in raw_enabled if isinstance(s, str) and s.strip()]
        raw_symbol_settings = data.get("symbol_settings", {})
        symbol_settings: dict[str, SymbolScanSettings] = {}
        if isinstance(raw_symbol_settings, dict):
            for symbol, item in raw_symbol_settings.items():
                if not isinstance(symbol, str) or not symbol.strip() or not isinstance(item, dict):
                    continue
                try:
                    min_score = int(item.get("min_score", 0))
                except (TypeError, ValueError):
                    min_score = 0
                symbol_settings[symbol] = SymbolScanSettings(
                    backtest=bool(item.get("backtest", False)),
                    min_score=max(0, min(100, min_score)),
                )
        return TradingSettings(
            account_balance=float(data.get("account_balance", 10000)),
            account_currency=data.get("account_currency", "USD"),
            default_risk_percent=float(data.get("default_risk_percent", 1.0)),
            max_risk_percent=float(data.get("max_risk_percent", 2.0)),
            lot_step=float(data.get("lot_step", 0.01)),
            minimum_lot=float(data.get("minimum_lot", 0.01)),
            contract_size_override=float(data.get("contract_size_override", 100000)),
            enabled_symbols=enabled,
            symbol_settings=symbol_settings,
        )

    def _load_display_settings(self, data: dict | None, legacy_language: str) -> DisplaySettings:
        data = data or {}
        return DisplaySettings(
            language=data.get("language", legacy_language or "vi"),
            timezone=data.get("timezone", "Asia/Ho_Chi_Minh"),
            term_explanation_mode=data.get("term_explanation_mode", "always_show"),
            theme=data.get("theme", "dark"),
        )

    def _load_advanced_settings(self, data: dict | None) -> AdvancedSettings:
        data = data or {}
        return AdvancedSettings(
            d1_bars=int(data.get("d1_bars", 500)),
            h4_bars=int(data.get("h4_bars", 500)),
            h1_bars=int(data.get("h1_bars", 500)),
            scanner_ai_detail_limit=int(data.get("scanner_ai_detail_limit", 3)),
            high_impact_news_block_before_minutes=int(data.get("high_impact_news_block_before_minutes", 30)),
            high_impact_news_block_after_minutes=int(data.get("high_impact_news_block_after_minutes", 30)),
            sqlite_database_path=data.get("sqlite_database_path", "./data/journal.db"),
            settings_storage=data.get("settings_storage", "settings.json"),
            block_high_impact_news=bool(data.get("block_high_impact_news", True)),
        )

    def _load_notification_settings(self, data: dict | None) -> NotificationSettings:
        data = data or {}
        raw_chat_ids = data.get("telegram_chat_ids", [])
        if isinstance(raw_chat_ids, str):
            chat_ids = [item.strip() for item in raw_chat_ids.replace("\n", ",").split(",") if item.strip()]
        elif isinstance(raw_chat_ids, list):
            chat_ids = [str(item).strip() for item in raw_chat_ids if str(item).strip()]
        else:
            chat_ids = []
        interval = int(data.get("auto_scan_interval_minutes", 15))
        allowed = {1, 5, 15, 30, 60, 240, 1440}
        if interval not in allowed:
            interval = 15
        return NotificationSettings(
            telegram_bot_token=str(data.get("telegram_bot_token", "")).strip(),
            telegram_chat_ids=chat_ids,
            auto_scan_interval_minutes=interval,
        )
