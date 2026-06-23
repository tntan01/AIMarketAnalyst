from __future__ import annotations

from core.scanner_ai_auditor import (
    build_ai_setup_audit_prompt,
    parse_ai_setup_audit,
    summarize_ai_setup_audit,
)


def test_parse_ai_setup_audit_accepts_fenced_json_and_clamps_scores():
    raw = """```json
    {
      "agreement": "agree",
      "confidence_score": 120,
      "trade_plan_quality": 72.4,
      "setup_summary": "Setup sạch.",
      "market_context_summary": "Macro trung lập.",
      "risk_flags": ["Spread cần kiểm tra"],
      "missing_confirmations": ["Đợi M15 đóng nến"],
      "do_not_trade_reason": ""
    }
    ```"""

    audit = parse_ai_setup_audit(raw)

    assert audit["agreement"] == "agree"
    assert audit["confidence_score"] == 100
    assert audit["trade_plan_quality"] == 72
    assert audit["risk_flags"] == ["Spread cần kiểm tra"]
    assert "auditor_error" not in audit


def test_parse_ai_setup_audit_returns_safe_error_on_invalid_json():
    audit = parse_ai_setup_audit("không phải json")

    assert audit["agreement"] == "caution"
    assert audit["auditor_error"] == "invalid_json"
    assert audit["raw_response"] == "không phải json"


def test_summarize_ai_setup_audit_uses_structured_conclusion():
    audit = {
        "agreement": "disagree",
        "setup_summary": "Setup bị tin mạnh cản.",
        "do_not_trade_reason": "Không nên vào trước tin.",
    }

    summary = summarize_ai_setup_audit(audit)

    assert summary.startswith("AI không đồng thuận:")
    assert "Không nên vào trước tin" in summary


def test_build_ai_setup_audit_prompt_includes_schema_and_forbids_new_prices():
    row = {
        "symbol": "EUR/USD",
        "scanner_group": "ready_now",
        "best_side": "buy",
        "analysis_result": {
            "trade_gate": {"allowed": True},
            "scenarios": [{"type": "buy", "entry_zone": [1.08, 1.081], "stop_loss": 1.075}],
        },
    }

    prompt = build_ai_setup_audit_prompt(row)

    assert '"agreement": "agree|caution|disagree"' in prompt
    assert "không được tự tạo entry/SL/TP mới" in prompt
    assert "EUR/USD" in prompt
