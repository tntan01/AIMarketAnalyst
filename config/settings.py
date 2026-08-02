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
    backtest_config_id: str = ""
    backtest_status: str = ""
    backtest_schema_version: int = 0
    backtest_validation_version: str = ""
    backtest_engine_contract_version: str = ""
    backtest_engine_version: str = ""
    backtest_purpose: str = ""
    backtest_execution_parity: bool = False
    backtest_data_manifest_version: str = ""
    backtest_point_in_time_data: bool = False
    backtest_dataset_hash: str = ""
    backtest_data_quality_status: str = ""
    backtest_execution_policy_version: str = ""
    backtest_entry_fill_model: str = ""
    backtest_exit_evaluation_model: str = ""
    backtest_same_bar_ambiguity_policy: str = ""
    backtest_execution_timeframe: str = ""
    backtest_synthetic_trades_allowed: bool = False
    backtest_execution_mode: str = ""
    backtest_execution_model_version: str = ""
    backtest_cost_model_version: str = ""
    backtest_quote_conversion_model_version: str = ""
    backtest_cost_model_fingerprint: str = ""
    backtest_quote_conversion_fingerprint: str = ""
    backtest_candidate_ledger_version: str = ""
    backtest_candidate_replay_version: str = ""
    backtest_frozen_strategy_version: str = ""
    backtest_frozen_strategy_applied: bool = False
    backtest_oos_replay: bool = False
    backtest_provenance_version: str = ""
    backtest_code_revision: str = ""
    backtest_request_fingerprint: str = ""
    backtest_execution_fingerprint: str = ""
    backtest_provenance_fingerprint: str = ""
    backtest_scorer_version: str = ""
    backtest_feature_version: str = ""
    backtest_smc_scorer_version: str = ""
    backtest_score_metric: str = ""
    backtest_trained_from: str = ""
    backtest_trained_to: str = ""
    backtest_validated_from: str = ""
    backtest_validated_to: str = ""
    backtest_in_sample_trades: int = 0
    backtest_out_of_sample_trades: int = 0
    backtest_oos_expectancy_r: float = 0.0
    backtest_oos_profit_factor: float = 0.0
    backtest_oos_max_drawdown_r: float = 0.0
    backtest_expectancy_ci_low: float | None = None
    backtest_expectancy_ci_high: float | None = None
    backtest_statistics_version: str = ""
    backtest_probability_positive_edge_pct: float | None = None
    backtest_one_sided_p_value: float | None = None
    backtest_minimum_required_trades: int = 0
    backtest_statistical_power_passed: bool = False
    backtest_walk_forward_windows: int = 0
    backtest_walk_forward_verdict: str = ""
    backtest_validation_fingerprint: str = ""
    backtest_validation_reasons: list[str] = field(default_factory=list)
    backtest_validated_at: str = ""
    backtest_expires_at: str = ""
    backtest_release_report: dict[str, object] = field(default_factory=dict)
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
    backtest_slippage_price: float = 0.0
    backtest_commission_per_lot_round_turn: float = 0.0
    backtest_swap_long_per_lot_day: float = 0.0
    backtest_swap_short_per_lot_day: float = 0.0
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
    sqlite_database_path: str = "./data/journal.db"
    settings_storage: str = "settings.json"
    block_high_impact_news: bool = True
    brave_api_key: str = ""
    fred_api_key: str = ""


@dataclass(slots=True)
class NotificationSettings:
    telegram_bot_token: str = ""
    telegram_chat_ids: list[str] = field(default_factory=list)
    auto_scan_interval_minutes: int = 15


@dataclass(slots=True)
class FeatureFlagSettings:
    """Architecture rollout switches.

    Phase-0 safety invariants are always enabled.  These flags only select
    future implementations and must never restore unsafe auto-trade behavior.
    """

    scanner_architecture_v2: bool = False
    auto_trade_v2: bool = False
    # Fast reject remains opt-in until its offline A/B gates pass.
    scanner_fast_tier1: bool = False
    scanner_fast_tier2: bool = False
    scanner_mt5_history_cache: bool = False
    # Phase 3: emit core result to the UI before Telegram/persistence run.
    scanner_core_result_early: bool = False


@dataclass(slots=True)
class ScannerRolloutSettings:
    """Fail-closed rollout policy for Scanner V2 order execution."""

    stage: str = "SHADOW"
    kill_switch: bool = False
    shadow_compare_enabled: bool = True
    allowed_symbols: list[str] = field(default_factory=list)
    canary_risk_percent: float = 0.1
    require_demo_account: bool = True
    production_approved: bool = False
    min_shadow_samples: int = 100
    min_demo_orders: int = 20
    min_canary_orders: int = 5
    max_disagreement_rate: float = 0.1
    max_revalidation_failure_rate: float = 0.05
    max_performance_degradation_pct: float = 15.0


@dataclass(slots=True)
class AppSettings:
    ai: AISettings
    trading: TradingSettings = field(default_factory=TradingSettings)
    display: DisplaySettings = field(default_factory=DisplaySettings)
    advanced: AdvancedSettings = field(default_factory=AdvancedSettings)
    notifications: NotificationSettings = field(default_factory=NotificationSettings)
    features: FeatureFlagSettings = field(default_factory=FeatureFlagSettings)
    scanner_rollout: ScannerRolloutSettings = field(
        default_factory=ScannerRolloutSettings
    )
    default_symbol: str = "EUR/USD"
    default_timeframe: str = "H1"
    language: str = "vi"


def default_settings() -> AppSettings:
    return AppSettings(ai=AISettings())
