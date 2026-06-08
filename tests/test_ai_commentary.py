from __future__ import annotations

from config.settings import AIProviderSettings
from controllers.analysis_controller import AnalysisController


def _result() -> dict[str, object]:
    return {
        "symbol": "EUR/USD",
        "macro": {"alignment_source": "fallback_neutral"},
        "economic_events": [{"event": "CPI", "time_vn": "19:30", "impact": "high", "hours_until": 3}],
        "market_regime": {"primary": "trend_up", "structure": "HH/HL"},
        "direction_bias": "buy",
        "trade_permission": {"status": "caution", "reason": "Có tin CPI trong 3 giờ tới."},
        "decision_summary": {"best_scenario": "buy", "best_score": 76, "action": "watch"},
        "technical": {"price": 1.1, "atr_h4": 0.01, "support_zones": [{"level": 1.09}], "resistance_zones": [{"level": 1.12}]},
        "scenario_scores": {
            "buy": {"total": 76, "macro_alignment": 7},
            "sell": {"total": 42, "macro_alignment": 7},
        },
        "scenarios": [
            {
                "type": "buy",
                "entry_zone": [1.095, 1.1],
                "stop_loss": 1.09,
                "take_profit": [1.12],
                "risk_reward": "1:2.1",
                "entry_status": "waiting_confirmation",
                "watch_zone": [1.09, 1.105],
                "confirmation_score": 55,
                "position_sizing": {"suggested_lot": 0.1},
            }
        ],
        "data_quality": {"price_source": "MT5", "spread_status": "normal"},
        "risk_management": {"warnings": ["Không vào lệnh sát tin đỏ."]},
        "why_not_opposite": {"sell": "Sell yếu hơn."},
        "confidence_reason": ["Buy/Sell score: 76 / 42."],
    }


def test_ai_writer_prompt_requires_macro_events_calculated_advice(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_analyze(self, prompt: str) -> str:
        captured["prompt"] = prompt
        return "1. Tình hình vĩ mô\n- ok\n\n2. Sự kiện kinh tế sắp tới\n- CPI"

    monkeypatch.setattr("controllers.analysis_controller.AIService.analyze", fake_analyze)
    controller = AnalysisController()
    active = AIProviderSettings("DeepSeek", "deepseek-v4-flash", "key", is_active=True)

    text = controller._write_ai_commentary(_result(), active)

    assert "Tình hình vĩ mô" in captured["prompt"]
    assert "Sự kiện kinh tế sắp tới" in captured["prompt"]
    assert "Nhận định theo số liệu tính toán" in captured["prompt"]
    assert "Lời khuyên hành động" in captured["prompt"]
    assert "upcoming_economic_events_from_app" in captured["prompt"]
    assert "entry_context" in captured["prompt"]
    assert '"price_vs_zone": "in_zone"' in captured["prompt"]
    assert '"entry_status": "waiting_confirmation"' in captured["prompt"]
    assert "Không tự tạo giá" in captured["prompt"]
    assert "CPI" in captured["prompt"]
    assert text.startswith("1. Tình hình vĩ mô")


def test_ai_commentary_normalizer_keeps_four_sections_and_removes_asterisks(monkeypatch) -> None:
    def fake_analyze(self, prompt: str) -> str:
        return "**1. Tình hình vĩ mô**\n- Có dữ liệu.\n\n**3. Nhận định theo số liệu tính toán**\n- Theo dõi."

    monkeypatch.setattr("controllers.analysis_controller.AIService.analyze", fake_analyze)
    controller = AnalysisController()
    active = AIProviderSettings("DeepSeek", "deepseek-v4-flash", "key", is_active=True)

    text = controller._write_ai_commentary(_result(), active)

    assert "*" not in text
    assert "1. Tình hình vĩ mô" in text
    assert "2. Sự kiện kinh tế sắp tới" in text
    assert "3. Nhận định theo số liệu tính toán" in text
    assert "4. Lời khuyên hành động" in text
    assert "CPI" in text


def test_ai_commentary_states_no_event_data_when_missing() -> None:
    result = _result()
    result["economic_events"] = []
    result["macro"]["driver_context"] = {"warning": "Không có dữ liệu sự kiện kinh tế sắp tới khớp cặp tiền."}
    controller = AnalysisController()

    text = controller._write_ai_commentary(result, None)

    assert "2. Sự kiện kinh tế sắp tới" in text
    assert "Không có dữ liệu" in text


def test_fallback_ai_commentary_is_structured_when_ai_not_configured() -> None:
    controller = AnalysisController()

    text = controller._write_ai_commentary(_result(), None)

    assert "1. Tình hình vĩ mô" in text
    assert "2. Sự kiện kinh tế sắp tới" in text
    assert "3. Nhận định theo số liệu tính toán" in text
    assert "4. Lời khuyên hành động" in text


def test_ai_commentary_removes_reasoning_preamble_and_compacts(monkeypatch) -> None:
    def fake_analyze(self, prompt: str) -> str:
        return "\n".join(
            [
                "Chung ta can viet cau tra loi theo du lieu JSON.",
                "Truoc het, xac dinh mui gio va kiem tra du lieu.",
                "1. Tình hình vĩ mô",
                "- Dong 1.",
                "- Dong 2.",
                "- Dong 3.",
                "- Dong 4 bi cat.",
                "2. Sự kiện kinh tế sắp tới",
                "- CPI luc 19:30.",
                "3. Nhận định theo số liệu tính toán",
                "- Market Regime con yeu.",
                "- Direction Bias la neutral.",
                "- Trade Permission la caution.",
                "- Buy Score thap.",
                "- Sell Score chua du manh.",
                "- Dong 6 bi cat.",
                "4. Lời khuyên hành động",
                "- No clean setup, nen dung ngoai.",
            ]
        )

    monkeypatch.setattr("controllers.analysis_controller.AIService.analyze", fake_analyze)
    controller = AnalysisController()
    active = AIProviderSettings("DeepSeek", "deepseek-v4-flash", "key", is_active=True)

    text = controller._write_ai_commentary(_result(), active)

    assert text.startswith("1. Tình hình vĩ mô")
    assert "Chung ta can" not in text
    assert "Dong 4 bi cat" not in text
    assert "Dong 6 bi cat" not in text
    assert "Market Regime (trạng thái thị trường)" in text
    assert "Direction Bias (thiên hướng giao dịch)" in text
    assert "Trade Permission (quyền giao dịch)" in text
    assert "No clean setup (không có thiết lập giao dịch sạch)" in text
