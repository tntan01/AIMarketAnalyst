from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.screens.single_analysis_result_screen import SingleAnalysisResultScreen

APP = QApplication.instance() or QApplication([])


def _screen() -> SingleAnalysisResultScreen:
    return SingleAnalysisResultScreen()


def test_result_tabs_translate_common_analysis_terms() -> None:
    screen = _screen()
    result = {
        "symbol": "EUR/USD",
        "decision_summary": {
            "main_view": "EUR/USD: No clean setup / stand aside better.",
            "action": "stand_aside",
        },
        "market_regime": {"primary": "unknown", "structure": "LH/LL"},
        "direction_bias": "neutral",
        "trade_permission": {"status": "caution"},
        "scenario_scores": {"buy": {"total": 45, "macro_alignment": 7}, "sell": {"total": 50, "macro_alignment": 6}},
        "scenarios": [
            {
                "type": "sell",
                "entry_status": "waiting_confirmation",
                "trigger_type": "h1_bearish_break",
                "entry_zone": [1.1, 1.2],
                "stop_loss": 1.21,
                "take_profit": [1.05],
                "risk_reward": "1:2",
                "position_sizing": {"suggested_lot": 0.1},
                "condition": "wait confirmation",
                "invalid_reason": "No clean setup",
                "invalidation": "zone broken",
                "reason": "No clean setup / stand aside better.",
            }
        ],
        "entry_checklist": [
            {"label": "Spread", "status": "wait", "value": "normal", "note": "Spread must be normal."}
        ],
        "backtest": {
            "summary": {
                "trade_count": 1,
                "win_rate": 50,
                "expectancy_r": 0.2,
                "average_r": 0.2,
                "average_mfe_r": 1.0,
                "average_mae_r": -0.4,
                "max_drawdown_r": 0.5,
            },
            "by_session": {"Asia": {"trade_count": 1, "win_rate": 50, "expectancy_r": 0.2}},
            "reason": "No clean setup",
        },
        "macro": {
            "ai_summary": "Market Regime neutral. No clean setup.",
            "driver_context": {
                "macro_themes": [{"currency": "USD", "stance": "hawkish", "headline_count": 2}],
                "latest_headlines": [{"title": "Fed rate cut expectations and bearish price action", "source": "Test", "published_utc": "now"}],
                "geopolitical_hotspots": [{"title": "central bank inflation risk", "source": "Test"}],
            },
        },
        "economic_events": [{"currency": "USD", "event": "Non-Farm Employment Change", "impact": "high", "event_time_local": "19:15"}],
    }

    screen.set_analysis_result(result)

    combined = "\n".join(
        [
            screen.scenario_text.toPlainText(),
            screen.plan_text.toPlainText(),
            screen.replay_text.toPlainText(),
            screen.macro_text.toPlainText(),
            screen.ai_text.toPlainText(),
        ]
    )
    assert "Không có thiết lập giao dịch sạch" in combined
    assert "Tỷ lệ thắng" in combined
    assert "Kỳ vọng" in combined
    assert "Chủ đề vĩ mô" in combined
    assert "Fed (Cục Dự trữ Liên bang Mỹ)" in combined
    assert "Trạng thái thị trường" in combined
    assert "No clean setup" not in combined
    assert "Win rate" not in combined
    assert "Expectancy" not in combined
    assert "Macro theme" not in combined
    assert screen.header_symbol_badge.text() == "EUR/USD"


def test_latest_news_line_only_shows_impact_when_specific() -> None:
    screen = _screen()

    neutral_line = screen._format_news_line(
        {"published_local": "26-05-2026 18:07", "title": "FX Weekly - MUFG Research"}
    )
    impact_line = screen._format_news_line(
        {
            "published_local": "26-05-2026 18:07",
            "title": "Fed official warns on inflation",
            "impact_note": "Có thể tác động trực tiếp tới USD.",
        }
    )

    assert neutral_line == "26-05-2026 18:07: FX Weekly - MUFG Research"
    assert "->" not in neutral_line
    assert impact_line.endswith("-> Có thể tác động trực tiếp tới USD.")
