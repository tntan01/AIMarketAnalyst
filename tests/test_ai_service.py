from services.ai_service import AIProviderConfig, AIService


def _service() -> AIService:
    return AIService(AIProviderConfig("DeepSeek", "deepseek-v4-flash", "key"))


def test_extracts_chat_completion_content() -> None:
    data = {"choices": [{"message": {"content": " Nhan dinh hop le "}, "finish_reason": "stop"}]}

    assert _service()._extract_chat_completion_text(data) == "Nhan dinh hop le"


def test_extracts_reasoning_content_when_final_content_is_empty() -> None:
    data = {
        "choices": [
            {
                "message": {"content": "", "reasoning_content": " Co phan tich trong reasoning "},
                "finish_reason": "stop",
            }
        ]
    }

    assert _service()._extract_chat_completion_text(data) == "Co phan tich trong reasoning"


def test_empty_chat_completion_reports_finish_reason() -> None:
    data = {"choices": [{"message": {"content": ""}, "finish_reason": "insufficient_system_resource"}]}

    assert "DeepSeek" in _service()._chat_completion_empty_reason(data)


def test_rejects_unsupported_deepseek_model_before_api_call() -> None:
    service = AIService(AIProviderConfig("DeepSeek", "deepseek-chat", "key"))

    try:
        service.analyze("hello")
    except RuntimeError as exc:
        assert "deepseek-v4-flash" in str(exc)
    else:
        raise AssertionError("Expected unsupported DeepSeek model to fail")
