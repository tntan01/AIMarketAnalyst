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
    OrderManagementSettings,
    SymbolScanSettings,
    TradingSettings,
    default_settings,
)
from core.symbol_scan_config import (
    has_new_permission_keys,
    migrate_analysis_min_rr,
    migrate_permission_flags,
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
            order_management=self._load_order_management(
                data.get("order_management", {})
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
                # Bước 2/4b gỡ Backtest: đọc cờ phân quyền độc lập + ngưỡng
                # Decision Engine tường minh. Entry legacy (chưa có khóa mới)
                # được suy dẫn bảo toàn hành vi cũ — migration thuần đọc,
                # chạy lại bao nhiêu lần cũng cho cùng kết quả; lần save kế
                # tiếp sẽ ghi cấu trúc mới.
                if has_new_permission_keys(item):
                    scan_enabled = item.get("scan_enabled") is True
                    auto_trade_permitted = (
                        item.get("auto_trade_permitted") is True
                    )
                else:
                    scan_enabled, auto_trade_permitted = (
                        migrate_permission_flags(item)
                    )
                analysis_min_rr = migrate_analysis_min_rr(item)
                loaded_symbol = SymbolScanSettings(
                    scan_enabled=scan_enabled,
                    auto_trade_permitted=auto_trade_permitted,
                    analysis_min_rr=analysis_min_rr,
                    min_score=max(0, min(100, min_score)),
                    auto_trade_regime=str(item.get("auto_trade_regime", "")).strip(),
                    auto_trade_side=str(item.get("auto_trade_side", "")).strip(),
                    decision_ready=max(0, min(100, int(item.get("decision_ready", 65)))),
                    decision_watch=max(0, min(100, int(item.get("decision_watch", 60)))),
                    decision_wait=max(0, min(100, int(item.get("decision_wait", 55)))),
                    min_expected_rr=float(item.get("min_expected_rr", 1.3) or 1.3),
                )
                # Bước 4b gỡ Backtest: KHÔNG còn tái kiểm định bằng chứng khi
                # load. Quyền auto-trade là lựa chọn tường minh của người dùng
                # (auto_trade_permitted) — hết hạn/version drift không tự tước
                # quyền; dữ liệu bằng chứng cũ được đọc nguyên trạng (data
                # compat). An toàn thực thi do Router lean + order policy +
                # các gate khi vào lệnh đảm nhiệm (không đổi).
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
                    # Bước 2 gỡ Backtest: danh sách mã bật quét theo cờ
                    # scan_enabled độc lập (không còn gate bằng cờ backtest).
                    and symbol_settings[symbol].scan_enabled
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
            block_high_impact_news=bool(data.get("block_high_impact_news", True)),
            brave_api_key=data.get("brave_api_key", ""),
            fred_api_key=data.get("fred_api_key", ""),
            vix_pair_aware_enabled=bool(data.get("vix_pair_aware_enabled", False)),
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
        # ``scanner_architecture_v2``/``auto_trade_v2``/``scanner_fast_tier2``
        # đã xóa khỏi model (16/08/2026); ``order_management_v2`` đã xóa cùng
        # ngày khi OM không còn feature flag — key còn sót trên disk bị bỏ qua.
        return FeatureFlagSettings(
            scanner_fast_tier1=bool(data.get("scanner_fast_tier1", False)),
            scanner_mt5_history_cache=bool(
                data.get("scanner_mt5_history_cache", False)
            ),
            scanner_core_result_early=bool(
                data.get("scanner_core_result_early", False)
            ),
        )

    def _load_order_management(
        self,
        data: dict | None,
    ) -> OrderManagementSettings:
        data = data if isinstance(data, dict) else {}
        # The rollout stage ladder and kill switch were removed (2026-08-15,
        # fully live): leftover on-disk keys for them are ignored here. The
        # ``manage_scope`` selector was removed 2026-08-16 (only ALL scope).
        return OrderManagementSettings(
            poll_interval_seconds=min(
                max(_safe_float(data.get("poll_interval_seconds", 1.5)), 0.5),
                60.0,
            ),
            refresh_interval_seconds=min(
                max(_safe_float(data.get("refresh_interval_seconds", 5.0)), 1.0),
                300.0,
            ),
            be_trigger_r=min(
                max(_safe_float(data.get("be_trigger_r", 1.0)), 0.1),
                10.0,
            ),
            be_plus_pips=min(
                max(_safe_float(data.get("be_plus_pips", 2.0)), 0.0),
                100.0,
            ),
            trail_wide_atr_multiplier=min(
                max(
                    _safe_float(data.get("trail_wide_atr_multiplier", 2.5)),
                    0.1,
                ),
                20.0,
            ),
            trail_tight_atr_multiplier=min(
                max(
                    _safe_float(data.get("trail_tight_atr_multiplier", 1.5)),
                    0.1,
                ),
                20.0,
            ),
            trail_tight_trigger_r=min(
                max(_safe_float(data.get("trail_tight_trigger_r", 2.0)), 0.1),
                20.0,
            ),
            retry_initial_seconds=min(
                max(_safe_float(data.get("retry_initial_seconds", 2.0)), 0.1),
                60.0,
            ),
            retry_max_seconds=min(
                max(_safe_float(data.get("retry_max_seconds", 30.0)), 1.0),
                600.0,
            ),
            max_retry_attempts=min(
                max(_safe_int(data.get("max_retry_attempts", 5)), 1),
                100,
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

