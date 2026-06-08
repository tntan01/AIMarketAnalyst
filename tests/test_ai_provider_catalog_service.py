import json

from services.ai_provider_catalog_service import AIProviderCatalogService


def test_add_provider_model_creates_json_catalog(tmp_path) -> None:
    path = tmp_path / "ai_providers.json"
    service = AIProviderCatalogService(path)

    providers = service.add_provider_model("OpenAI", "gpt-new")

    assert providers["OpenAI"] == ["gpt-new"]
    assert set(providers) == {"DeepSeek", "OpenAI", "Anthropic", "Gemini"}
    data = json.loads(path.read_text(encoding="utf-8"))
    openai = next(item for item in data["providers"] if item["provider"] == "OpenAI")
    assert openai["models"] == ["gpt-new"]


def test_add_provider_model_appends_without_duplicates(tmp_path) -> None:
    path = tmp_path / "ai_providers.json"
    path.write_text(
        json.dumps({"providers": [{"provider": "OpenAI", "models": ["gpt-4.1"]}]}),
        encoding="utf-8",
    )
    service = AIProviderCatalogService(path)

    providers = service.add_provider_model("openai", "GPT-4.1")
    providers = service.add_provider_model("OpenAI", "gpt-5")

    assert providers["OpenAI"] == ["gpt-4.1", "gpt-5"]


def test_remove_provider_model_removes_empty_provider(tmp_path) -> None:
    path = tmp_path / "ai_providers.json"
    path.write_text(
        json.dumps(
            {
                "providers": [
                    {"provider": "OpenAI", "models": ["gpt-4.1", "gpt-5"]},
                    {"provider": "DeepSeek", "models": ["deepseek-chat"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    service = AIProviderCatalogService(path)

    providers = service.remove_provider_model("openai", "GPT-4.1")
    assert providers["OpenAI"] == ["gpt-5"]

    providers = service.remove_provider_model("OpenAI", "gpt-5")
    assert providers["OpenAI"] == []
    assert providers["DeepSeek"] == ["deepseek-v4-flash", "deepseek-v4-pro"]


def test_deepseek_catalog_is_fixed_to_supported_v4_models(tmp_path) -> None:
    path = tmp_path / "ai_providers.json"
    path.write_text(
        json.dumps({"providers": [{"provider": "DeepSeek", "models": ["deepseek-chat", "custom"]}]}),
        encoding="utf-8",
    )
    service = AIProviderCatalogService(path)

    providers = service.add_provider_model("DeepSeek", "another-model")
    providers = service.remove_provider_model("DeepSeek", "deepseek-v4-pro")
    providers = service.update_provider_model("DeepSeek", "deepseek-v4-flash", "DeepSeek", "renamed")

    assert providers["DeepSeek"] == ["deepseek-v4-flash", "deepseek-v4-pro"]


def test_update_provider_model_renames_provider_and_model(tmp_path) -> None:
    path = tmp_path / "ai_providers.json"
    path.write_text(
        json.dumps({"providers": [{"provider": "OpenAI", "models": ["gpt-old"]}]}),
        encoding="utf-8",
    )
    service = AIProviderCatalogService(path)

    providers = service.update_provider_model("OpenAI", "gpt-old", "OpenAI", "gpt-new")

    assert providers["OpenAI"] == ["gpt-new"]
    assert set(providers) == {"DeepSeek", "OpenAI", "Anthropic", "Gemini"}


def test_unknown_provider_is_ignored(tmp_path) -> None:
    path = tmp_path / "ai_providers.json"
    service = AIProviderCatalogService(path)

    providers = service.add_provider_model("Custom", "custom-model")

    assert "Custom" not in providers
