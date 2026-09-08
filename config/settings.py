from __future__ import annotations

from dataclasses import dataclass, field

from config.constants import DEFAULT_DEEPSEEK_MODEL


@dataclass(slots=True)
class AIProviderSettings:
    provider: str
    model: str
    api_key: str = ""
    api_key_ref: str | None = None
    base_url: str = ""
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
    # Cấu hình Scanner per-symbol (Backtest removal — Bước 2/4b/6):
    # - scan_enabled: mã được đưa vào danh sách quét của Scanner.
    # - auto_trade_permitted: mã được phép auto-trade — quyền do người dùng
    #   cấp tường minh, mặc định False (fail-closed); không phụ thuộc kiểm định.
    # - analysis_min_rr: ngưỡng R:R tối thiểu của Decision Engine cho mã.
    # Các khóa ``backtest_*`` legacy (bằng chứng kiểm định) đã GỠ khỏi model
    # (Bước 6, 2026-09-09): file settings.json cũ vẫn ĐỌC được — loader bỏ
    # qua khóa lạ, và migration trong ``core.symbol_scan_config`` suy dẫn
    # quyền/ngưỡng từ raw JSON trước khi lưu cấu trúc mới. Kết quả Backtest
    # đã lưu (snapshot app_data/backtests) và Nhật ký không bị đụng.
    scan_enabled: bool = False
    auto_trade_permitted: bool = False
    analysis_min_rr: float = 1.3
    min_score: int = 0
    auto_trade_regime: str = ""       # "range", "trend_up", etc. Empty = no filter
    auto_trade_side: str = ""         # "buy", "sell", "best". Empty = use best_side
    decision_ready: int = 65          # final_score >= this → READY_TO_TRADE
    decision_watch: int = 60          # final_score >= this → WATCH_ONLY
    decision_wait: int = 55           # final_score >= this → WAITING_CONFIRMATION
    min_expected_rr: float = 1.3      # min expected_effective_rr for gate


@dataclass(slots=True)
class TradingSettings:
    account_balance: float = 10000
    account_currency: str = "USD"
    default_risk_percent: float = 1.0
    max_risk_percent: float = 2.0
    lot_step: float = 0.01
    minimum_lot: float = 0.01
    maximum_lot: float = 100.0
    contract_size_override: float = 100000
    max_daily_loss_pct: float = 2.0
    max_weekly_loss_pct: float = 5.0
    max_consecutive_losses: int = 3
    max_open_risk_pct: float = 3.0
    max_symbol_risk_pct: float = 2.0
    max_currency_exposure_pct: float = 2.0
    max_correlated_risk_pct: float = 2.0
    max_concurrent_orders: int = 5
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
    block_high_impact_news: bool = True
    brave_api_key: str = ""
    fred_api_key: str = ""
    vix_pair_aware_enabled: bool = False


@dataclass(slots=True)
class NotificationSettings:
    telegram_bot_token: str = ""
    telegram_chat_ids: list[str] = field(default_factory=list)
    auto_scan_interval_minutes: int = 15


@dataclass(slots=True)
class FeatureFlagSettings:
    """Runtime feature switches.

    Phase-0 safety invariants are always enabled.  These flags only select
    optional optimisations/emissions and must never restore unsafe auto-trade
    behavior.  The old ``scanner_architecture_v2``/``auto_trade_v2`` rollout
    flags were removed on 2026-08-16: Scanner V4 and auto-trade are the
    unconditional live path, and ``scanner_fast_tier2`` never branched
    anywhere (only tier1 is wired).
    """

    # Fast reject remains opt-in until its offline A/B gates pass.
    scanner_fast_tier1: bool = False
    scanner_mt5_history_cache: bool = False
    # Phase 3: emit core result to the UI before Telegram/persistence run.
    scanner_core_result_early: bool = False


@dataclass(slots=True)
class OrderManagementSettings:
    """Runtime policy for Order Management (fully live since 2026-08-15).

    The rollout stage ladder and kill switch were removed by owner decision;
    the OM feature flag was removed 2026-08-16 so the subsystem is always on.
    Protection changes are applied directly to broker positions; execution is
    gated only by the broker account's own ``account.trade_allowed``.
    ``manage_scope`` was removed 2026-08-16 — there is only one scope (ALL):
    "Đóng tất cả" always targets every open position.
    """

    poll_interval_seconds: float = 1.5
    refresh_interval_seconds: float = 5.0
    be_trigger_r: float = 1.0
    be_plus_pips: float = 2.0
    trail_wide_atr_multiplier: float = 2.5
    trail_tight_atr_multiplier: float = 1.5
    trail_tight_trigger_r: float = 2.0
    retry_initial_seconds: float = 2.0
    retry_max_seconds: float = 30.0
    max_retry_attempts: int = 5


@dataclass(slots=True)
class AppSettings:
    ai: AISettings
    trading: TradingSettings = field(default_factory=TradingSettings)
    display: DisplaySettings = field(default_factory=DisplaySettings)
    advanced: AdvancedSettings = field(default_factory=AdvancedSettings)
    notifications: NotificationSettings = field(default_factory=NotificationSettings)
    features: FeatureFlagSettings = field(default_factory=FeatureFlagSettings)
    order_management: OrderManagementSettings = field(
        default_factory=OrderManagementSettings
    )
    default_symbol: str = "EUR/USD"
    default_timeframe: str = "H1"
    language: str = "vi"


def default_settings() -> AppSettings:
    return AppSettings(ai=AISettings())
