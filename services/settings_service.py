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
    FeatureFlagSettings,
    NotificationSettings,
    ScannerRolloutSettings,
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
            features=self._load_feature_flags(data.get("features", {})),
            scanner_rollout=self._load_scanner_rollout(
                data.get("scanner_rollout", {})
            ),
            default_symbol=data.get("default_symbol", "EUR/USD"),
            default_timeframe=data.get("default_timeframe", "H1"),
            language=data.get("language", "vi"),
        )

    def save(self, settings: AppSettings) -> None:
        # Persist API keys to OS credential store, then save WITHOUT plaintext
        # keys to disk.  In-memory settings are NOT modified — runtime
        # consumers continue to see api_key as usual.
        from dataclasses import replace
        from services.credential_service import credential_service

        # Mirror API keys to credential store
        for provider in settings.ai.providers:
            if provider.api_key:
                credential_service.save_api_key(provider.provider, provider.api_key)

        # Build a safe copy with api_key cleared for disk serialization
        safe_providers = [
            replace(p, api_key="") if p.api_key else p
            for p in settings.ai.providers
        ]
        safe_ai = replace(settings.ai, providers=safe_providers)
        safe_settings = replace(settings, ai=safe_ai)

        self.storage.save(asdict(safe_settings))

    def _load_ai_settings(self, data: dict | None) -> AISettings:
        data = data or {}
        providers = [
            AIProviderSettings(
                provider=item.get("provider", ""),
                model=self._normalize_ai_model(item.get("provider", ""), item.get("model", "")),
                api_key=item.get("api_key", ""),
                api_key_ref=item.get("api_key_ref"),
                base_url=str(item.get("base_url", "") or ""),
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

        # Populate API keys from OS credential store (transparent to consumers)
        from services.credential_service import credential_service

        for provider in providers:
            if not provider.api_key:
                stored = credential_service.get_api_key(provider.provider)
                if stored:
                    provider.api_key = stored

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
                raw_reasons = item.get("backtest_validation_reasons", [])
                loaded_symbol = SymbolScanSettings(
                    backtest=bool(item.get("backtest", False)),
                    backtest_config_id=str(
                        item.get("backtest_config_id", "") or ""
                    ).strip(),
                    backtest_status=str(
                        item.get("backtest_status", "") or ""
                    ).strip().upper(),
                    backtest_schema_version=_safe_int(
                        item.get("backtest_schema_version")
                    ),
                    backtest_validation_version=str(
                        item.get("backtest_validation_version", "") or ""
                    ).strip(),
                    backtest_engine_contract_version=str(
                        item.get(
                            "backtest_engine_contract_version", ""
                        ) or ""
                    ).strip(),
                    backtest_engine_version=str(
                        item.get("backtest_engine_version", "") or ""
                    ).strip(),
                    backtest_purpose=str(
                        item.get("backtest_purpose", "") or ""
                    ).strip().upper(),
                    backtest_execution_parity=(
                        item.get("backtest_execution_parity") is True
                    ),
                    backtest_data_manifest_version=str(
                        item.get(
                            "backtest_data_manifest_version", ""
                        ) or ""
                    ).strip(),
                    backtest_point_in_time_data=(
                        item.get("backtest_point_in_time_data") is True
                    ),
                    backtest_dataset_hash=str(
                        item.get("backtest_dataset_hash", "") or ""
                    ).strip().lower(),
                    backtest_data_quality_status=str(
                        item.get(
                            "backtest_data_quality_status", ""
                        ) or ""
                    ).strip().upper(),
                    backtest_execution_policy_version=str(
                        item.get(
                            "backtest_execution_policy_version", ""
                        ) or ""
                    ).strip(),
                    backtest_entry_fill_model=str(
                        item.get("backtest_entry_fill_model", "") or ""
                    ).strip(),
                    backtest_exit_evaluation_model=str(
                        item.get(
                            "backtest_exit_evaluation_model", ""
                        ) or ""
                    ).strip(),
                    backtest_same_bar_ambiguity_policy=str(
                        item.get(
                            "backtest_same_bar_ambiguity_policy", ""
                        ) or ""
                    ).strip().upper(),
                    backtest_execution_timeframe=str(
                        item.get(
                            "backtest_execution_timeframe", ""
                        ) or ""
                    ).strip().upper(),
                    backtest_synthetic_trades_allowed=(
                        item.get(
                            "backtest_synthetic_trades_allowed"
                        ) is True
                    ),
                    backtest_execution_mode=str(
                        item.get("backtest_execution_mode", "") or ""
                    ),
                    backtest_execution_model_version=str(
                        item.get(
                            "backtest_execution_model_version", ""
                        ) or ""
                    ),
                    backtest_cost_model_version=str(
                        item.get("backtest_cost_model_version", "") or ""
                    ),
                    backtest_quote_conversion_model_version=str(
                        item.get(
                            "backtest_quote_conversion_model_version", ""
                        ) or ""
                    ),
                    backtest_cost_model_fingerprint=str(
                        item.get(
                            "backtest_cost_model_fingerprint", ""
                        ) or ""
                    ),
                    backtest_quote_conversion_fingerprint=str(
                        item.get(
                            "backtest_quote_conversion_fingerprint", ""
                        ) or ""
                    ),
                    backtest_candidate_ledger_version=str(
                        item.get(
                            "backtest_candidate_ledger_version", ""
                        ) or ""
                    ),
                    backtest_candidate_replay_version=str(
                        item.get(
                            "backtest_candidate_replay_version", ""
                        ) or ""
                    ),
                    backtest_frozen_strategy_version=str(
                        item.get(
                            "backtest_frozen_strategy_version", ""
                        ) or ""
                    ),
                    backtest_frozen_strategy_applied=(
                        item.get("backtest_frozen_strategy_applied") is True
                    ),
                    backtest_oos_replay=(
                        item.get("backtest_oos_replay") is True
                    ),
                    backtest_provenance_version=str(
                        item.get("backtest_provenance_version", "") or ""
                    ),
                    backtest_code_revision=str(
                        item.get("backtest_code_revision", "") or ""
                    ),
                    backtest_request_fingerprint=str(
                        item.get("backtest_request_fingerprint", "") or ""
                    ),
                    backtest_execution_fingerprint=str(
                        item.get("backtest_execution_fingerprint", "") or ""
                    ),
                    backtest_provenance_fingerprint=str(
                        item.get("backtest_provenance_fingerprint", "") or ""
                    ),
                    backtest_scorer_version=str(
                        item.get("backtest_scorer_version", "") or ""
                    ).strip(),
                    backtest_feature_version=str(
                        item.get("backtest_feature_version", "") or ""
                    ).strip(),
                    backtest_smc_scorer_version=str(
                        item.get("backtest_smc_scorer_version", "") or ""
                    ).strip(),
                    backtest_score_metric=str(
                        item.get("backtest_score_metric", "") or ""
                    ).strip(),
                    backtest_trained_from=str(
                        item.get("backtest_trained_from", "") or ""
                    ).strip(),
                    backtest_trained_to=str(
                        item.get("backtest_trained_to", "") or ""
                    ).strip(),
                    backtest_validated_from=str(
                        item.get("backtest_validated_from", "") or ""
                    ).strip(),
                    backtest_validated_to=str(
                        item.get("backtest_validated_to", "") or ""
                    ).strip(),
                    backtest_in_sample_trades=_safe_int(
                        item.get("backtest_in_sample_trades")
                    ),
                    backtest_out_of_sample_trades=_safe_int(
                        item.get("backtest_out_of_sample_trades")
                    ),
                    backtest_oos_expectancy_r=_safe_float(
                        item.get("backtest_oos_expectancy_r")
                    ),
                    backtest_oos_profit_factor=_safe_float(
                        item.get("backtest_oos_profit_factor")
                    ),
                    backtest_oos_max_drawdown_r=_safe_float(
                        item.get("backtest_oos_max_drawdown_r")
                    ),
                    backtest_expectancy_ci_low=_safe_optional_float(
                        item.get("backtest_expectancy_ci_low")
                    ),
                    backtest_expectancy_ci_high=_safe_optional_float(
                        item.get("backtest_expectancy_ci_high")
                    ),
                    backtest_statistics_version=str(
                        item.get("backtest_statistics_version", "") or ""
                    ),
                    backtest_probability_positive_edge_pct=_safe_optional_float(
                        item.get("backtest_probability_positive_edge_pct")
                    ),
                    backtest_one_sided_p_value=_safe_optional_float(
                        item.get("backtest_one_sided_p_value")
                    ),
                    backtest_minimum_required_trades=_safe_int(
                        item.get("backtest_minimum_required_trades")
                    ),
                    backtest_statistical_power_passed=(
                        item.get("backtest_statistical_power_passed") is True
                    ),
                    backtest_walk_forward_windows=_safe_int(
                        item.get("backtest_walk_forward_windows")
                    ),
                    backtest_walk_forward_verdict=str(
                        item.get("backtest_walk_forward_verdict", "") or ""
                    ).strip().upper(),
                    backtest_validation_fingerprint=str(
                        item.get("backtest_validation_fingerprint", "") or ""
                    ).strip(),
                    backtest_validation_reasons=(
                        [
                            str(value)
                            for value in raw_reasons
                            if str(value).strip()
                        ]
                        if isinstance(raw_reasons, list)
                        else []
                    ),
                    backtest_validated_at=str(
                        item.get("backtest_validated_at", "") or ""
                    ).strip(),
                    backtest_expires_at=str(
                        item.get("backtest_expires_at", "") or ""
                    ).strip(),
                    backtest_release_report=(
                        dict(item.get("backtest_release_report"))
                        if isinstance(item.get("backtest_release_report"), dict)
                        else {}
                    ),
                    min_score=max(0, min(100, min_score)),
                    auto_trade_regime=str(item.get("auto_trade_regime", "")).strip(),
                    auto_trade_side=str(item.get("auto_trade_side", "")).strip(),
                    decision_ready=max(0, min(100, int(item.get("decision_ready", 65)))),
                    decision_watch=max(0, min(100, int(item.get("decision_watch", 60)))),
                    decision_wait=max(0, min(100, int(item.get("decision_wait", 55)))),
                    min_expected_rr=float(item.get("min_expected_rr", 1.3) or 1.3),
                )
                if (
                    loaded_symbol.backtest
                    or loaded_symbol.backtest_status
                    or loaded_symbol.backtest_config_id
                ):
                    from core.backtest_config import serialize_backtest_config
                    from core.scanner_models import (
                        CONFIG_DRAFT,
                        CONFIG_EXPIRED,
                        CONFIG_INVALID,
                        CONFIG_VALIDATED,
                        CONFIG_VERSION_MISMATCH,
                    )
                    from core.backtest_config_validation import (
                        BACKTEST_CONFIG_SCHEMA_VERSION,
                    )
                    from core.scanner_strategy_router import validate_backtest_config

                    if loaded_symbol.backtest_status == CONFIG_VALIDATED:
                        payload = serialize_backtest_config(
                            loaded_symbol,
                            symbol=symbol,
                        )
                        lifecycle_status, lifecycle_reasons = (
                            validate_backtest_config(payload, {"symbol": symbol})
                        )
                        if lifecycle_status != CONFIG_VALIDATED:
                            loaded_symbol.backtest_status = (
                                CONFIG_EXPIRED
                                if lifecycle_status == CONFIG_EXPIRED
                                else (
                                    CONFIG_VERSION_MISMATCH
                                    if lifecycle_status == CONFIG_VERSION_MISMATCH
                                    else (
                                        CONFIG_INVALID
                                        if (
                                            loaded_symbol.backtest_schema_version
                                            == BACKTEST_CONFIG_SCHEMA_VERSION
                                        )
                                        else CONFIG_DRAFT
                                    )
                                )
                            )
                            # Keep the historical fingerprint for audit and
                            # migration. The non-VALIDATED lifecycle and
                            # backtest=False below remain the fail-closed
                            # execution boundary.
                            loaded_symbol.backtest_validation_reasons = list(
                                lifecycle_reasons
                            )
                    elif not loaded_symbol.backtest_status:
                        loaded_symbol.backtest_status = CONFIG_DRAFT
                    # Fail closed: retained DRAFT/INVALID/EXPIRED evidence is
                    # useful for a later backtest, but must not create a live
                    # BACKTEST_INVALID branch. Scanner will use DEFAULT_RULES.
                    if loaded_symbol.backtest_status != CONFIG_VALIDATED:
                        loaded_symbol.backtest = False
                symbol_settings[symbol] = loaded_symbol
        return TradingSettings(
            account_balance=float(data.get("account_balance", 10000)),
            account_currency=data.get("account_currency", "USD"),
            default_risk_percent=float(data.get("default_risk_percent", 1.0)),
            max_risk_percent=float(data.get("max_risk_percent", 2.0)),
            lot_step=float(data.get("lot_step", 0.01)),
            minimum_lot=float(data.get("minimum_lot", 0.01)),
            maximum_lot=max(
                float(data.get("minimum_lot", 0.01)),
                float(data.get("maximum_lot", 100.0)),
            ),
            contract_size_override=float(data.get("contract_size_override", 100000)),
            backtest_slippage_price=max(
                0.0, float(data.get("backtest_slippage_price", 0.0))
            ),
            backtest_commission_per_lot_round_turn=max(
                0.0,
                float(data.get("backtest_commission_per_lot_round_turn", 0.0)),
            ),
            backtest_swap_long_per_lot_day=max(
                0.0, float(data.get("backtest_swap_long_per_lot_day", 0.0))
            ),
            backtest_swap_short_per_lot_day=max(
                0.0, float(data.get("backtest_swap_short_per_lot_day", 0.0))
            ),
            max_daily_loss_pct=float(data.get("max_daily_loss_pct", 2.0)),
            max_weekly_loss_pct=float(data.get("max_weekly_loss_pct", 5.0)),
            max_consecutive_losses=int(data.get("max_consecutive_losses", 3)),
            max_open_risk_pct=float(data.get("max_open_risk_pct", 3.0)),
            max_symbol_risk_pct=max(
                0.1,
                float(data.get("max_symbol_risk_pct", 2.0)),
            ),
            max_currency_exposure_pct=max(
                0.1,
                float(data.get("max_currency_exposure_pct", 2.0)),
            ),
            max_correlated_risk_pct=max(
                0.1,
                float(data.get("max_correlated_risk_pct", 2.0)),
            ),
            max_concurrent_orders=max(
                1,
                int(data.get("max_concurrent_orders", 5)),
            ),
            enabled_symbols=[
                symbol
                for symbol in enabled
                if (
                    symbol in symbol_settings
                    and symbol_settings[symbol].backtest
                )
            ],
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
            brave_api_key=data.get("brave_api_key", ""),
            fred_api_key=data.get("fred_api_key", ""),
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

    def _load_feature_flags(self, data: dict | None) -> FeatureFlagSettings:
        data = data if isinstance(data, dict) else {}
        # Key mode cũ trong settings JSON được bỏ qua; không còn
        # config path nào kích hoạt scorer khác ngoài SMC canonical.
        return FeatureFlagSettings(
            scanner_architecture_v2=bool(data.get("scanner_architecture_v2", False)),
            auto_trade_v2=bool(data.get("auto_trade_v2", False)),
            scanner_fast_tier1=bool(data.get("scanner_fast_tier1", False)),
            scanner_fast_tier2=bool(data.get("scanner_fast_tier2", False)),
            scanner_mt5_history_cache=bool(
                data.get("scanner_mt5_history_cache", False)
            ),
            scanner_core_result_early=bool(
                data.get("scanner_core_result_early", False)
            ),
        )

    def _load_scanner_rollout(
        self,
        data: dict | None,
    ) -> ScannerRolloutSettings:
        data = data if isinstance(data, dict) else {}
        stage = str(data.get("stage", "SHADOW") or "SHADOW").upper()
        allowed_stages = {
            "DISABLED",
            "SHADOW",
            "DEMO_LIMITED",
            "DEMO_FULL",
            "CANARY",
            "PRODUCTION",
        }
        if stage not in allowed_stages:
            stage = "SHADOW"
        raw_symbols = data.get("allowed_symbols", [])
        symbols = (
            [
                str(symbol).strip().upper()
                for symbol in raw_symbols
                if str(symbol).strip()
            ]
            if isinstance(raw_symbols, list)
            else []
        )
        return ScannerRolloutSettings(
            stage=stage,
            kill_switch=bool(data.get("kill_switch", False)),
            allowed_symbols=list(dict.fromkeys(symbols)),
            canary_risk_percent=min(
                max(_safe_float(data.get("canary_risk_percent", 0.1)), 0.01),
                1.0,
            ),
            require_demo_account=bool(
                data.get("require_demo_account", True)
            ),
            production_approved=bool(
                data.get("production_approved", False)
            ),
            min_demo_orders=max(
                _safe_int(data.get("min_demo_orders", 20)),
                1,
            ),
            min_canary_orders=max(
                _safe_int(data.get("min_canary_orders", 5)),
                1,
            ),
            max_revalidation_failure_rate=min(
                max(
                    _safe_float(
                        data.get("max_revalidation_failure_rate", 0.05)
                    ),
                    0.0,
                ),
                1.0,
            ),
            max_performance_degradation_pct=min(
                max(
                    _safe_float(
                        data.get(
                            "max_performance_degradation_pct",
                            15.0,
                        )
                    ),
                    0.0,
                ),
                100.0,
            ),
        )


def _safe_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: object) -> float:
    return _safe_optional_float(value) or 0.0


def _safe_optional_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None

