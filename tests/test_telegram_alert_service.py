from __future__ import annotations

from services.telegram_alert_service import TelegramAlertService


def _ready_row() -> dict[str, object]:
    return {
        "symbol": "XAU/USD",
        "broker_symbol": "XAUUSD.r",
        "scanner_action": "ready",
        "trade_permission": "allowed",
        "best_side": "buy",
        "best_score": 86,
        "risk_reward": "1:2.0",
        "short_reason": "Đủ điều kiện vào lệnh.",
        "analysis_result": {
            "mode": "scanner",
            "scenarios": [
                {
                    "type": "buy",
                    "entry_zone": [2340.5, 2342.0],
                    "stop_loss": 2334.0,
                    "take_profit": [2355.0, 2368.0],
                    "risk_reward": "1:2.0",
                    "position_sizing": {"suggested_lot": 0.12, "account_balance": 12345.67},
                }
            ],
        },
    }


def test_telegram_alert_formats_ready_trade_message() -> None:
    message = TelegramAlertService().format_trade_alert(_ready_row())

    assert "Mã: XAU/USD (XAUUSD.r)" in message
    assert "Entry: 2340.5 - 2342.0" in message
    assert "Stop loss: 2334.0" in message
    assert "Take profit: 2355.0, 2368.0" in message
    assert "Lot: 0.12" in message
    assert "Vốn MT5: 12345.67" in message


def test_telegram_alert_sends_only_ready_allowed_rows(monkeypatch) -> None:
    sent: list[tuple[str, str, str]] = []
    service = TelegramAlertService()
    monkeypatch.setattr(service, "_send_message", lambda token, chat_id, text: sent.append((token, chat_id, text)))

    result = service.send_ready_trade_alerts(
        [_ready_row(), {**_ready_row(), "scanner_action": "watch"}],
        bot_token="token",
        chat_ids=["100", "200"],
    )

    assert result.attempted == 2
    assert result.sent == 2
    assert len(sent) == 2
    assert sent[0][0] == "token"
