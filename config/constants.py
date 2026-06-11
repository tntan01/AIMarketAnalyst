from __future__ import annotations

import json
from pathlib import Path

APP_NAME = "AI Market Analyst"
APP_ID = "ai-market-analyst"

SUPPORTED_SYMBOLS = [
    "EUR/USD",
    "GBP/USD",
    "AUD/USD",
    "NZD/USD",
    "USD/JPY",
    "USD/CHF",
    "USD/CAD",
    "EUR/GBP",
    "EUR/JPY",
    "EUR/CHF",
    "EUR/AUD",
    "EUR/NZD",
    "EUR/CAD",
    "GBP/JPY",
    "GBP/CHF",
    "GBP/AUD",
    "GBP/NZD",
    "GBP/CAD",
    "CHF/JPY",
    "AUD/JPY",
    "NZD/JPY",
    "CAD/JPY",
    "AUD/CHF",
    "NZD/CHF",
    "CAD/CHF",
    "AUD/NZD",
    "AUD/CAD",
    "NZD/CAD",
    "XAU/USD",
    "XAG/USD",
    "BTC/USD",
]

def active_symbols(enabled: list[str] | None = None) -> list[str]:
    """Return symbols that are enabled for scanning/analysis.

    If ``enabled`` is empty or None, all SUPPORTED_SYMBOLS are active.
    Otherwise only the intersection of enabled and SUPPORTED_SYMBOLS is returned.
    """
    if not enabled:
        return list(SUPPORTED_SYMBOLS)
    lookup = set(enabled)
    return [s for s in SUPPORTED_SYMBOLS if s in lookup]


DEFAULT_TIMEFRAMES = ["D1", "H4", "H1", "M15"]
PRIMARY_ANALYSIS_TIMEFRAMES = ["D1", "H4", "H1"]
MT5_SYMBOL_SUFFIXES = ["", "m", "c"]
DEEPSEEK_MODELS = ["deepseek-v4-flash", "deepseek-v4-pro"]
DEFAULT_DEEPSEEK_MODEL = DEEPSEEK_MODELS[0]

_FALLBACK_AI_MODELS = {
    "DeepSeek": DEEPSEEK_MODELS,
    "OpenAI": ["gpt-4.1", "gpt-4.1-mini", "o4-mini"],
    "Anthropic": ["claude-3-5-sonnet-latest", "claude-3-5-haiku-latest"],
    "Gemini": ["gemini-2.5-flash", "gemini-2.5-pro"],
}


def _load_ai_models() -> dict[str, list[str]]:
    path = Path(__file__).with_name("ai_providers.json")
    if not path.exists():
        return _FALLBACK_AI_MODELS
    data = json.loads(path.read_text(encoding="utf-8"))
    models = {
        item.get("provider", ""): item.get("models", [])
        for item in data.get("providers", [])
        if item.get("provider") and isinstance(item.get("models"), list)
    }
    return models or _FALLBACK_AI_MODELS


DEFAULT_AI_MODELS = _load_ai_models()
AI_PROVIDERS = list(DEFAULT_AI_MODELS)
