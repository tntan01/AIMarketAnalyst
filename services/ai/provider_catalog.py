"""Provider Catalog — static registry of known AI providers and their metadata.

This module replaces the old ``FIXED_AI_PROVIDERS`` list and scattered
hard-coded provider constants.  Every provider registers its
:class:`ProviderInfo` once at import time; the rest of the codebase
queries the catalog instead of branching on provider-name strings.

Design rule
-----------
* **Catalog is static.**  Provider capabilities, default models, and
  display names do not change at runtime (they describe a vendor, not
  a user's configuration).
* **Runtime state lives elsewhere** (API key, selected model,
  connection status are per-user; they belong in settings / runtime
  objects, not here).
* **Adapters live here too.**  Each ``ProviderInfo`` carries its
  adapter class so that :class:`AIService` can obtain the correct
  adapter without an if/elif chain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntFlag, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.ai.provider_adapter import BaseProviderAdapter


class ProviderCapability(IntFlag):
    """Bitmask of features a provider (or specific model) supports.

    Use ``in`` to test::

        if ProviderCapability.STREAM in provider.capabilities:
            ...

    Use :func:`capability_labels` to get human-readable display strings::

        capability_labels(provider.capabilities)
        # → ["Chat", "Streaming", "Vision"]
    """

    CHAT = auto()             # text generation from prompt
    STREAM = auto()           # SSE token streaming
    MODEL_DISCOVERY = auto()  # dynamic model listing from API
    VISION = auto()           # image input
    TOOL_CALLING = auto()     # function / tool calling
    SYSTEM_PROMPT = auto()    # separate system prompt field
    REASONING = auto()        # thinking / reasoning tokens
    JSON_MODE = auto()        # structured JSON output
    EMBEDDING = auto()        # text embedding / vector
    IMAGE_GEN = auto()        # image generation


# Human-readable Vietnamese labels for each capability flag
_CAPABILITY_LABELS: dict[ProviderCapability, str] = {}


def _build_labels() -> None:
    """Populate _CAPABILITY_LABELS after the enum is fully defined."""
    caps = ProviderCapability
    _CAPABILITY_LABELS.update({
        caps.CHAT: "Chat",
        caps.STREAM: "Streaming",
        caps.MODEL_DISCOVERY: "Model Discovery",
        caps.VISION: "Vision",
        caps.TOOL_CALLING: "Tool Calling",
        caps.SYSTEM_PROMPT: "System Prompt",
        caps.REASONING: "Thinking",
        caps.JSON_MODE: "JSON Mode",
        caps.EMBEDDING: "Embedding",
        caps.IMAGE_GEN: "Image Gen",
    })


_build_labels()


def capability_labels(caps: ProviderCapability) -> list[str]:
    """Return Vietnamese display labels for every flag set in *caps*."""
    result: list[str] = []
    for flag in ProviderCapability:
        if flag in caps and flag in _CAPABILITY_LABELS:
            result.append(_CAPABILITY_LABELS[flag])
    return result


def capability_label(cap: ProviderCapability) -> str:
    """Return the display label for a single capability flag."""
    return _CAPABILITY_LABELS.get(cap, cap.name)


@dataclass(frozen=True, slots=True)
class ProviderInfo:
    """Static metadata for one AI provider.

    Registered once at import time via :meth:`ProviderCatalog.register`.
    Never mutated after registration.
    """

    name: str
    """Internal key (lowercase, no spaces).  E.g. ``"deepseek"``, ``"gemini"``."""

    display_name: str
    """Human-readable name shown in UI.  E.g. ``"DeepSeek"``, ``"Gemini"``."""

    capabilities: ProviderCapability
    """Feature bitmask for this provider as a whole."""

    default_models: tuple[str, ...] = ()
    """Fallback model list used when dynamic discovery is unavailable."""

    locked_models: bool = False
    """If True, users cannot add/remove models from this provider's catalog."""

    adapter_class: type[BaseProviderAdapter] | None = field(default=None, compare=False)
    """Adapter class that implements :class:`BaseProviderAdapter` for this provider.

    Set by the adapter module after both Catalog and Adapter classes are defined.
    Not included in equality/hash comparisons.
    """


# ---------------------------------------------------------------------------
# Catalog (module-level singleton)
# ---------------------------------------------------------------------------


class _ProviderCatalog:
    """Thread-safe registry of :class:`ProviderInfo` keyed by ``name``.

    Intended for use through the module-level singleton ``provider_catalog``.
    """

    def __init__(self) -> None:
        self._providers: dict[str, ProviderInfo] = {}
        self._adapters: dict[str, BaseProviderAdapter] = {}

    # -- registration --------------------------------------------------------

    def register(self, info: ProviderInfo) -> None:
        """Register a provider.  Safe to call multiple times (last wins)."""
        key = info.name.lower()
        self._providers[key] = info
        # Clear cached adapter so next get_adapter() picks up new class
        self._adapters.pop(key, None)

    # -- lookup --------------------------------------------------------------

    def _resolve_key(self, name: str) -> str:
        """Map an internal key or a display name to the canonical internal key.

        Callers historically pass display names (e.g. ``"OpenAI Compatible
        (Tùy chỉnh)"``) which do not always equal the internal key
        (``"openai_compatible"``); the four original providers only worked
        because their display names lowercase to their keys.  Unknown names
        are returned as-is so the existing unknown-provider error path holds.
        """
        key = (name or "").strip().lower()
        if key in self._providers:
            return key
        for info in self._providers.values():
            if info.display_name.strip().lower() == key:
                return info.name
        return key

    def get(self, name: str) -> ProviderInfo | None:
        """Look up :class:`ProviderInfo` by internal key or display name (case-insensitive)."""
        return self._providers.get(self._resolve_key(name))

    def get_adapter(self, name: str) -> BaseProviderAdapter | None:
        """Return a cached singleton adapter instance for *name*.

        Accepts either the internal key or the display name.
        Returns ``None`` when the provider is not registered or has no
        ``adapter_class`` set.
        """
        key = self._resolve_key(name)
        if key in self._adapters:
            return self._adapters[key]
        info = self._providers.get(key)
        if info is None or info.adapter_class is None:
            return None
        adapter = info.adapter_class()
        self._adapters[key] = adapter
        return adapter

    # -- iteration -----------------------------------------------------------

    def list_all(self) -> list[str]:
        """Return all registered provider keys in registration order."""
        return list(self._providers.keys())

    def list_display_names(self) -> list[str]:
        """Return display names in registration order (for UI dropdowns)."""
        return [info.display_name for info in self._providers.values()]

    def list_infos(self) -> list[ProviderInfo]:
        """Return all :class:`ProviderInfo` objects in registration order."""
        return list(self._providers.values())

    def default_models_for(self, name: str) -> list[str]:
        """Return default model list for *name*, or empty list."""
        info = self.get(name)
        return list(info.default_models) if info else []

    # -- capabilities --------------------------------------------------------

    def has_capability(self, name: str, cap: ProviderCapability) -> bool:
        """Check whether *name* supports *cap*."""
        info = self.get(name)
        return cap in info.capabilities if info else False

    # -- convenience: build provider→models dict (backward compat) -----------

    def build_model_dict(self, overrides: dict[str, list[str]] | None = None) -> dict[str, list[str]]:
        """Return ``{display_name: [model_names]}`` for all registered providers.

        *overrides* can supply per-provider model lists that take precedence
        over ``default_models`` (used when loading user-configured models
        from JSON).
        """
        result: dict[str, list[str]] = {}
        for info in self._providers.values():
            if overrides and info.display_name in overrides:
                result[info.display_name] = overrides[info.display_name]
            else:
                result[info.display_name] = list(info.default_models)
        return result


# Module-level singleton — the single source of truth for provider metadata
provider_catalog = _ProviderCatalog()
