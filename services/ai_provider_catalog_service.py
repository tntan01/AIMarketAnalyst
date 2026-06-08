from __future__ import annotations

from pathlib import Path

from config.paths import CONFIG_DIR
from config.constants import DEEPSEEK_MODELS
from services.storage_service import JsonStorage

FIXED_AI_PROVIDERS = ["DeepSeek", "OpenAI", "Anthropic", "Gemini"]


class AIProviderCatalogService:
    def __init__(self, path: Path | None = None) -> None:
        self.storage = JsonStorage(path or CONFIG_DIR / "ai_providers.json")

    def load(self) -> dict[str, list[str]]:
        data = self.storage.load({"providers": []})
        providers: dict[str, list[str]] = {provider: [] for provider in FIXED_AI_PROVIDERS}
        for item in data.get("providers", []):
            provider = item.get("provider", "").strip()
            models = item.get("models", [])
            provider_key = self._matching_provider_key(providers, provider)
            if not provider_key or not isinstance(models, list):
                continue
            providers[provider_key] = sorted(
                {str(model).strip() for model in models if str(model).strip()},
                key=str.lower,
            )
        providers["DeepSeek"] = list(DEEPSEEK_MODELS)
        return providers

    def add_provider_model(self, provider: str, model: str) -> dict[str, list[str]]:
        provider = provider.strip()
        model = model.strip()
        if not provider or not model:
            return self.load()

        providers = self.load()
        provider_key = self._matching_provider_key(providers, provider)
        if not provider_key:
            return providers
        if provider_key == "DeepSeek":
            return providers
        models = providers.setdefault(provider_key, [])
        if not any(existing.lower() == model.lower() for existing in models):
            models.append(model)
            models.sort(key=str.lower)
        self.save(providers)
        return providers

    def remove_provider_model(self, provider: str, model: str) -> dict[str, list[str]]:
        provider = provider.strip()
        model = model.strip()
        providers = self.load()
        provider_key = self._matching_provider_key(providers, provider)
        if not provider_key:
            return providers
        if provider_key == "DeepSeek":
            return providers

        providers[provider_key] = [
            existing for existing in providers[provider_key] if existing.lower() != model.lower()
        ]
        self.save(providers)
        return providers

    def update_provider_model(
        self,
        old_provider: str,
        old_model: str,
        new_provider: str,
        new_model: str,
    ) -> dict[str, list[str]]:
        provider = new_provider.strip()
        model = new_model.strip()
        if not provider or not model:
            return self.load()
        providers = self.load()
        old_provider_key = self._matching_provider_key(providers, old_provider)
        new_provider_key = self._matching_provider_key(providers, provider)
        if not old_provider_key or not new_provider_key:
            return providers
        if old_provider_key == "DeepSeek" or new_provider_key == "DeepSeek":
            return providers
        providers[old_provider_key] = [
            existing for existing in providers[old_provider_key] if existing.lower() != old_model.strip().lower()
        ]
        models = providers.setdefault(new_provider_key, [])
        if not any(existing.lower() == model.lower() for existing in models):
            models.append(model)
        self.save(providers)
        return self.load()

    def save(self, providers: dict[str, list[str]]) -> None:
        providers = {**providers, "DeepSeek": list(DEEPSEEK_MODELS)}
        rows = [
            {
                "provider": provider,
                "models": sorted(set(models), key=str.lower),
            }
            for provider, models in sorted(providers.items(), key=lambda item: FIXED_AI_PROVIDERS.index(item[0]))
            if provider in FIXED_AI_PROVIDERS
        ]
        self.storage.save({"providers": rows})

    def _matching_provider_key(self, providers: dict[str, list[str]], provider: str) -> str | None:
        for existing in providers:
            if existing.lower() == provider.lower():
                return existing
        return None
