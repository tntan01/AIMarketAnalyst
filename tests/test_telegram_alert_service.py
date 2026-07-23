from services.telegram_alert_service import TelegramAlertService


def test_order_alert_formats_base_and_rr_range():
    service = TelegramAlertService()
    text = service.format_order_alert({
        "scanner_action": "ready",
        "symbol": "EUR/USD",
        "broker_symbol": "EURUSDm",
        "side": "buy",
        "entry_zone": [1.095, 1.097],
        "stop_loss": 1.093,
        "take_profit": [1.105],
        "volume": 0.1,
        "risk_reward": "1:2.4",
        "expected_effective_rr_base": 1.7,
        "risk_reward_effective_range": {"best": 2.3, "base": 1.7, "worst": 1.1},
        "best_score": 80,
    })

    assert "base 1.7 sau spread" in text
    assert "dai thuc 1.1-2.3" in text
    assert "danh nghia 1:2.4" in text


def test_order_alert_rr_falls_back_to_nominal():
    service = TelegramAlertService()
    text = service.format_order_alert({
        "scanner_action": "watch",
        "symbol": "EUR/USD",
        "side": "sell",
        "risk_reward": "1:1.8",
    })

    assert "R:R: 1:1.8" in text


# ---------------------------------------------------------------------------
# Phase 7: contract-locking tests
# ---------------------------------------------------------------------------


def test_nominal_risk_reward_always_present():
    """When base/effective context exists, 'danh nghia' must include the
    risk_reward best-case string as reference."""
    service = TelegramAlertService()
    text = service.format_order_alert({
        "scanner_action": "ready",
        "symbol": "EUR/USD",
        "side": "buy",
        "entry_zone": [1.095, 1.097],
        "stop_loss": 1.093,
        "take_profit": [1.105],
        "volume": 0.1,
        "risk_reward": "1:2.4",
        "expected_effective_rr_base": 1.7,
        "expected_effective_rr": 2.3,
        "risk_reward_effective_range": {"best": 2.3, "base": 1.7, "worst": 1.1},
        "best_score": 80,
    })
    # Main display: base effective, range, and nominal reference
    assert "base 1.7 sau spread" in text
    assert "danh nghia 1:2.4" in text


def test_no_rr_fields_does_not_crash():
    """Missing all RR fields → fallback to '--', no crash."""
    service = TelegramAlertService()
    text = service.format_order_alert({
        "scanner_action": "watch",
        "symbol": "EUR/USD",
        "side": "buy",
    })
    # Must contain the R:R line with fallback
    assert "R:R:" in text
    assert "--" in text


def test_current_rr_does_not_replace_main_rr():
    """current_effective_rr=0.5 (very low) must NOT appear as the main RR.
    The main display must still use base + nominal reference."""
    service = TelegramAlertService()
    text = service.format_order_alert({
        "scanner_action": "ready",
        "symbol": "GBP/USD",
        "side": "sell",
        "entry_zone": [1.3020, 1.3040],
        "stop_loss": 1.3060,
        "take_profit": [1.2920],
        "volume": 0.05,
        "risk_reward": "1:2.5",
        "expected_effective_rr_base": 1.8,
        "expected_effective_rr": 2.3,
        "risk_reward_effective_range": {"best": 2.3, "base": 1.8, "worst": 1.2},
        "current_effective_rr": 0.5,        # low — must NOT be the main display
        "current_rr_source": "current_price",
        "best_score": 78,
    })
    # Main RR line must show base effective, not current
    assert "base 1.8 sau spread" in text
    # Nominal reference still there
    assert "danh nghia 1:2.5" in text
    # Current RR must NOT leak into the R:R line
    rr_line = [line for line in text.split("\n") if "R:R:" in line][0]
    assert "0.5" not in rr_line, \
        f"current_effective_rr=0.5 must not appear in R:R line, got: {rr_line}"


def test_summary_candidate_line_does_not_show_rr():
    """Summary candidate lines don't display RR — verified format."""
    service = TelegramAlertService()
    line = service._format_candidate_line({
        "symbol": "EUR/USD",
        "broker_symbol": "EURUSDm",
        "side": "buy",
        "entry_zone": [1.095, 1.097],
        "stop_loss": 1.093,
        "best_score": 80,
        "scanner_action": "ready",
        "risk_reward": "1:2.5",
        "expected_effective_rr_base": 1.8,
    })
    # Summary line format: "{status} {symbol} | {side} | Điểm: {score}/100 | Entry: {entry} | SL: {sl}"
    assert "EUR/USD" in line
    assert "MUA" in line
    assert "Điểm: 80/100" in line
    # RR must NOT appear in the summary candidate line
    assert "1:2.5" not in line
    assert "1.8" not in line


def test_format_risk_reward_base_preferred_over_effective():
    """When both base and best effective are present, base is preferred as
    the main display.  Best effective is only a fallback."""
    service = TelegramAlertService()
    # base present → use base
    result = service._format_risk_reward({
        "risk_reward": "1:2.5",
        "expected_effective_rr_base": 1.8,
        "expected_effective_rr": 2.3,
    })
    assert "base 1.8 sau spread" in result
    assert "danh nghia 1:2.5" in result

    # base missing, best effective present → use best
    result2 = service._format_risk_reward({
        "risk_reward": "1:1.5",
        "expected_effective_rr": 1.4,
    })
    assert "thuc 1.4 sau spread" in result2
    assert "danh nghia 1:1.5" in result2


def test_format_decimal_and_range_helpers():
    """Smoke test for internal formatting helpers."""
    service = TelegramAlertService()

    assert service._format_decimal(2.567) == "2.6"
    assert service._format_decimal(None) == ""
    assert service._format_decimal("abc") == ""

    assert service._format_rr_range({"best": 2.3, "base": 1.7, "worst": 1.1}) == "1.1-2.3"
    assert service._format_rr_range({"best": 1.5, "worst": 1.5}) == "1.5"
    assert service._format_rr_range(None) == ""
    assert service._format_rr_range({}) == ""
