from config.settings import AdvancedSettings, AIProviderSettings, AISettings, AppSettings, DisplaySettings, NotificationSettings, SymbolScanSettings, TradingSettings
from services.settings_service import SettingsService


def test_settings_roundtrip(tmp_path) -> None:
    path = tmp_path / "settings.json"
    service = SettingsService(path)
    settings = AppSettings(ai=AISettings(provider="OpenAI", model="gpt-4.1", api_key_ref="key"))

    service.save(settings)
    loaded = service.load()

    assert loaded.ai.provider == "OpenAI"
    assert loaded.default_symbol == "EUR/USD"


def test_settings_roundtrip_multiple_ai_providers(tmp_path) -> None:
    path = tmp_path / "settings.json"
    service = SettingsService(path)
    settings = AppSettings(
        ai=AISettings(
            provider="OpenAI",
            model="gpt-4.1",
            api_key_ref="sk-****abcd",
            providers=[
                AIProviderSettings(
                    provider="DeepSeek",
                    model="deepseek-v4-flash",
                    api_key="deep-key",
                    api_key_ref="dee-****-key",
                ),
                AIProviderSettings(
                    provider="OpenAI",
                    model="gpt-4.1",
                    api_key="sk-test-abcd",
                    api_key_ref="sk-****abcd",
                    is_active=True,
                ),
            ],
        )
    )

    service.save(settings)
    loaded = service.load()

    assert len(loaded.ai.providers) == 2
    assert loaded.ai.provider == "OpenAI"
    assert loaded.ai.model == "gpt-4.1"
    assert loaded.ai.providers[1].api_key == "sk-test-abcd"
    assert loaded.ai.providers[1].is_active is True


def test_settings_migrates_legacy_ai_settings_to_provider_list(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        """
        {
          "ai": {
            "provider": "OpenAI",
            "model": "gpt-4.1",
            "api_key_ref": "sk-****abcd"
          }
        }
        """,
        encoding="utf-8",
    )
    service = SettingsService(path)

    loaded = service.load()

    assert loaded.ai.provider == "OpenAI"
    assert loaded.ai.providers[0].provider == "OpenAI"
    assert loaded.ai.providers[0].is_active is True


def test_settings_roundtrip_trading_and_display(tmp_path) -> None:
    path = tmp_path / "settings.json"
    service = SettingsService(path)
    settings = AppSettings(
        ai=AISettings(),
        trading=TradingSettings(
            account_balance=25000,
            account_currency="USD",
            default_risk_percent=1.5,
            max_risk_percent=3.0,
            lot_step=0.05,
            minimum_lot=0.01,
            contract_size_override=100,
            enabled_symbols=["EUR/USD"],
            symbol_settings={"EUR/USD": SymbolScanSettings(backtest=True, min_score=72)},
        ),
        display=DisplaySettings(
            language="vi",
            timezone="Asia/Bangkok",
            term_explanation_mode="tooltip",
            theme="dark",
        ),
    )

    service.save(settings)
    loaded = service.load()

    assert loaded.trading.account_balance == 25000
    assert loaded.trading.default_risk_percent == 1.5
    assert loaded.trading.contract_size_override == 100
    assert loaded.trading.enabled_symbols == ["EUR/USD"]
    assert loaded.trading.symbol_settings["EUR/USD"].backtest is True
    assert loaded.trading.symbol_settings["EUR/USD"].min_score == 72
    assert loaded.display.timezone == "Asia/Bangkok"
    assert loaded.display.term_explanation_mode == "tooltip"


def test_settings_roundtrip_advanced(tmp_path) -> None:
    path = tmp_path / "settings.json"
    service = SettingsService(path)
    settings = AppSettings(
        ai=AISettings(),
        advanced=AdvancedSettings(
            d1_bars=700,
            h4_bars=600,
            h1_bars=550,
            scanner_ai_detail_limit=5,
            high_impact_news_block_before_minutes=45,
            high_impact_news_block_after_minutes=60,
            sqlite_database_path="./data/custom.db",
            settings_storage="settings.json",
            block_high_impact_news=False,
        ),
    )

    service.save(settings)
    loaded = service.load()

    assert loaded.advanced.d1_bars == 700
    assert loaded.advanced.scanner_ai_detail_limit == 5
    assert loaded.advanced.high_impact_news_block_before_minutes == 45
    assert loaded.advanced.sqlite_database_path == "./data/custom.db"
    assert loaded.advanced.block_high_impact_news is False


def test_settings_roundtrip_notifications(tmp_path) -> None:
    path = tmp_path / "settings.json"
    service = SettingsService(path)
    settings = AppSettings(
        ai=AISettings(),
        notifications=NotificationSettings(
            telegram_bot_token="token",
            telegram_chat_ids=["123", "456"],
            auto_scan_interval_minutes=30,
        ),
    )

    service.save(settings)
    loaded = service.load()

    assert loaded.notifications.telegram_bot_token == "token"
    assert loaded.notifications.telegram_chat_ids == ["123", "456"]
    assert loaded.notifications.auto_scan_interval_minutes == 30


def test_settings_migrates_legacy_deepseek_models(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        """
        {
          "ai": {
            "provider": "DeepSeek",
            "model": "custom-deepseek",
            "providers": [
              {
                "provider": "DeepSeek",
                "model": "deepseek-reasoner",
                "api_key": "deep-key",
                "is_active": true
              }
            ]
          }
        }
        """,
        encoding="utf-8",
    )
    service = SettingsService(path)

    loaded = service.load()

    assert loaded.ai.model == "deepseek-v4-flash"
    assert loaded.ai.providers[0].model == "deepseek-v4-flash"
