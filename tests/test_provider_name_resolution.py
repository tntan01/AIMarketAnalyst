"""Test that AIService/catalog resolve BOTH the display name and the internal
key for every provider — new "OpenAI Compatible (Tùy chỉnh)" included.

Regression: callers (settings screen, dashboard, scanner, news) pass the
display name (e.g. ``"OpenAI Compatible (Tùy chỉnh)"``) into
``AIProviderConfig``, but the catalog looked up by internal key only
(``"openai_compatible"``).  The four original providers worked by accident
("DeepSeek".lower() == "deepseek"); the new one failed with "không được hỗ
trợ".  The fix makes ``provider_catalog.get()/get_adapter()`` resolve both.

Run directly:  python tests/test_provider_name_resolution.py
  → prints per-check results and a final ✅ PASS / ❌ FAIL.
Also runnable under pytest.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# (internal key, display name, expected adapter class)
PROVIDERS = [
    ("deepseek", "DeepSeek", "DeepSeekAdapter"),
    ("openai", "OpenAI", "OpenAIAdapter"),
    ("anthropic", "Anthropic", "AnthropicAdapter"),
    ("gemini", "Gemini", "GeminiAdapter"),
    ("openai_compatible", "OpenAI Compatible (Tùy chỉnh)", "OpenAICompatibleAdapter"),
]


def _adapter_class_name(provider_name: str) -> str:
    from services.ai_service import AIService, AIProviderConfig
    return type(AIService(AIProviderConfig(provider_name, "m", "k"))._adapter).__name__


def test_each_provider_resolves_by_internal_key_and_display_name():
    for key, display, expected in PROVIDERS:
        assert _adapter_class_name(key) == expected, f"key {key!r} -> {_adapter_class_name(key)}"
        assert _adapter_class_name(display) == expected, (
            f"display {display!r} -> {_adapter_class_name(display)}"
        )


def test_catalog_get_resolves_both_forms():
    from services.ai import provider_catalog
    for key, display, _ in PROVIDERS:
        assert provider_catalog.get(key).name == key
        assert provider_catalog.get(display).name == key


def test_catalog_get_adapter_resolves_both_forms():
    from services.ai import provider_catalog
    for key, display, expected in PROVIDERS:
        assert type(provider_catalog.get_adapter(key)).__name__ == expected
        assert type(provider_catalog.get_adapter(display)).__name__ == expected
        # display and key map to the same cached instance
        assert provider_catalog.get_adapter(key) is provider_catalog.get_adapter(display)


def test_unknown_provider_still_raises():
    from services.ai_service import AIService, AIProviderConfig
    try:
        AIService(AIProviderConfig("không-tồn-tại", "m", "k"))
    except RuntimeError as exc:
        assert "không được hỗ trợ" in str(exc)
    else:
        raise AssertionError("unknown provider must raise RuntimeError")


# ---------------------------------------------------------------------------
# Runner — prints ✅ PASS / ❌ FAIL
# ---------------------------------------------------------------------------

_CHECKS = [
    test_each_provider_resolves_by_internal_key_and_display_name,
    test_catalog_get_resolves_both_forms,
    test_catalog_get_adapter_resolves_both_forms,
    test_unknown_provider_still_raises,
]


def main() -> int:
    failed = 0
    for check in _CHECKS:
        try:
            check()
            print(f"  ✅ {check.__name__}")
        except Exception as exc:  # noqa: BLE001 — report any failure
            failed += 1
            print(f"  ❌ {check.__name__}: {exc}")

    print()
    if failed == 0:
        print(f"✅ PASS — all {len(_CHECKS)} checks passed.")
        return 0
    print(f"❌ FAIL — {failed}/{len(_CHECKS)} checks failed.")
    return 1


if __name__ == "__main__":
    # Windows consoles default to a non-UTF-8 code page (e.g. cp1258) that
    # cannot encode the ✅/❌ markers — force UTF-8 so direct runs don't crash.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001 — stdout may not support reconfigure
        pass
    raise SystemExit(main())