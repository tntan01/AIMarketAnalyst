from __future__ import annotations

from dataclasses import dataclass, field

from config.constants import DEFAULT_DEEPSEEK_MODEL


@dataclass(slots=True)
class AIProviderSettings:
    provider: str
    model: str
    api_key: str = ""
    api_key_ref: str | None = None
    is_active: bool = False


@dataclass(slots=True)
class AISettings:
    provider: str = "DeepSeek"
    model: str = DEFAULT_DEEPSEEK_MODEL
    api_key_ref: str | None = None
    providers: list[AIProviderSettings] = field(default_factory=list)

    def active_provider(self) -> AIProviderSettings | None:
        for provider in self.providers:
            if provider.is_active:
                return provider
        return self.providers[0] if self.providers else None


@dataclass(slots=True)
class SymbolScanSettings:
    backtest: bool = False
    min_score: int = 0


@dataclass(slots=True)
class TradingSettings:
    account_balance: float = 10000
    account_currency: str = "USD"
    default_risk_percent: float = 1.0
    max_risk_percent: float = 2.0
    lot_step: float = 0.01
    minimum_lot: float = 0.01
    contract_size_override: float = 100000
    enabled_symbols: list[str] = field(default_factory=list)
    symbol_settings: dict[str, SymbolScanSettings] = field(default_factory=dict)


@dataclass(slots=True)
class DisplaySettings:
    language: str = "vi"
    timezone: str = "Asia/Ho_Chi_Minh"
    term_explanation_mode: str = "always_show"
    theme: str = "dark"


@dataclass(slots=True)
class AdvancedSettings:
    d1_bars: int = 500
    h4_bars: int = 500
    h1_bars: int = 500
    scanner_ai_detail_limit: int = 3
    high_impact_news_block_before_minutes: int = 30
    high_impact_news_block_after_minutes: int = 30
    sqlite_database_path: str = "./data/journal.db"
    settings_storage: str = "settings.json"
    block_high_impact_news: bool = True


@dataclass(slots=True)
class NotificationSettings:
    telegram_bot_token: str = ""
    telegram_chat_ids: list[str] = field(default_factory=list)
    auto_scan_interval_minutes: int = 15


@dataclass(slots=True)
class AppSettings:
    ai: AISettings
    trading: TradingSettings = field(default_factory=TradingSettings)
    display: DisplaySettings = field(default_factory=DisplaySettings)
    advanced: AdvancedSettings = field(default_factory=AdvancedSettings)
    notifications: NotificationSettings = field(default_factory=NotificationSettings)
    default_symbol: str = "EUR/USD"
    default_timeframe: str = "H1"
    language: str = "vi"


def default_settings() -> AppSettings:
    return AppSettings(ai=AISettings())
