"""AI subsystem — provider catalog, adapters, and service layer.

Importing this package registers all built-in providers in
:data:`services.ai.provider_catalog.provider_catalog`.
"""

from services.ai.provider_catalog import (
    ProviderCapability,
    ProviderInfo,
    provider_catalog,
)
from services.ai.provider_adapter import BaseProviderAdapter

# Import provider modules to trigger self-registration
from services.ai.providers import deepseek_adapter   # noqa: F401
from services.ai.providers import openai_adapter     # noqa: F401
from services.ai.providers import anthropic_adapter  # noqa: F401
from services.ai.providers import gemini_adapter     # noqa: F401

__all__ = [
    "BaseProviderAdapter",
    "ProviderCapability",
    "ProviderInfo",
    "provider_catalog",
]
