"""AI Provider Catalog Service — runtime model discovery with disk cache.

Models are no longer stored in ``ai_providers.json``.  Instead:

1. **Defaults** come from :data:`services.ai.provider_catalog.provider_catalog`.
2. **Runtime discovery** happens when the user clicks the refresh icon —
   the adapter's ``discover_models()`` is called and results are cached
   to disk (``cache/provider_runtime/{provider}.json``).
3. **Offline fallback** — if the API is unreachable, the disk cache is
   used regardless of age.
4. **No API keys** are ever written to cache files.
"""

from __future__ import annotations

import json as _json
import time as _time
from pathlib import Path

from config.paths import app_data_dir
from services.ai import provider_catalog
from services.ai.provider_catalog import ProviderCapability

# Backward-compatible exports
FIXED_AI_PROVIDERS: list[str] = provider_catalog.list_display_names()
_GEMINI_FALLBACK_MODELS: list[str] = provider_catalog.default_models_for("gemini")

_DISCOVERY_CACHE_TTL = 1800  # 30 minutes — after this cache is "stale" but still usable


def _cache_dir() -> Path:
    d = app_data_dir() / "cache" / "provider_runtime"
    d.mkdir(parents=True, exist_ok=True)
    return d


class AIProviderCatalogService:
    """Runtime model catalog with disk-backed cache.

    Provider names and capabilities come from :data:`provider_catalog`
    (static).  Model lists are discovered at runtime and cached to disk
    so they survive app restarts.
    """

    def __init__(self, path: Path | None = None) -> None:
        # path is ignored — kept for backward compat with old callers
        self._discovery_cache: dict[str, dict] = {}  # provider_key -> {models, ts, source}
        # Pre-load disk cache into memory
        self._load_all_from_disk()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> dict[str, list[str]]:
        """Return ``{display_name: [model_names]}`` for all providers.

        Prefers runtime discovery cache (memory + disk), falling back to
        catalog defaults.
        """
        result: dict[str, list[str]] = {}
        for info in provider_catalog.list_infos():
            cached = self._cache_get(info.name)
            if cached:
                result[info.display_name] = cached
            else:
                result[info.display_name] = list(info.default_models)
        return result

    def refresh_models(self, provider_name: str, api_key: str) -> dict[str, list[str]]:
        """Discover models from *provider_name*'s API and cache to disk.

        On API error, falls back to disk cache (offline mode).  Only raises
        when there is no cache at all.
        """
        adapter = provider_catalog.get_adapter(provider_name)
        info = provider_catalog.get(provider_name)
        if info is None:
            return self.load()

        if adapter is None or ProviderCapability.MODEL_DISCOVERY not in info.capabilities:
            self._cache_set(info.name, list(info.default_models))
            return self.load()

        # Try API — on failure, fall back to disk cache
        try:
            discovered = adapter.discover_models(api_key)
        except Exception:
            disk = self._load_from_disk(info.name)
            if disk:
                # Offline fallback: use cached models regardless of age
                self._cache_set(info.name, disk["models"])
                return self.load()
            raise  # No cache → propagate error

        if discovered:
            model_names = self._filter_models(info.name, discovered)
            if model_names:
                self._cache_set(info.name, model_names)
            else:
                raise RuntimeError(
                    f"API {info.display_name} trả về model nhưng không có model "
                    f"nào phù hợp."
                )
        else:
            raise RuntimeError(
                f"API {info.display_name} không trả về model nào. "
                f"Kiểm tra API Key hoặc kết nối mạng."
            )

        return self.load()

    def is_cache_stale(self, provider_name: str) -> bool:
        """Return True if the cache for *provider_name* is older than TTL."""
        entry = self._discovery_cache.get(provider_name)
        if entry is None:
            return True
        return _time.time() - entry["ts"] > _DISCOVERY_CACHE_TTL

    # Backward-compatible alias
    def refresh_gemini_models(self, api_key: str) -> dict[str, list[str]]:
        return self.refresh_models("gemini", api_key)

    # ------------------------------------------------------------------
    # Backward-compatible stubs (former CRUD — now no-ops)
    # ------------------------------------------------------------------

    def save(self, providers: dict[str, list[str]]) -> None:
        pass

    def add_provider_model(self, provider: str, model: str) -> dict[str, list[str]]:
        return self.load()

    def remove_provider_model(self, provider: str, model: str) -> dict[str, list[str]]:
        return self.load()

    def update_provider_model(
        self, old_provider: str, old_model: str,
        new_provider: str, new_model: str,
    ) -> dict[str, list[str]]:
        return self.load()

    # ------------------------------------------------------------------
    # Cache internals — memory
    # ------------------------------------------------------------------

    def _cache_get(self, provider_key: str) -> list[str] | None:
        entry = self._discovery_cache.get(provider_key)
        if entry is None:
            return None
        # Stale entries are still returned (caller decides), but marked
        return entry["models"]

    def _cache_set(self, provider_key: str, models: list[str]) -> None:
        entry = {
            "models": sorted(set(models), key=str.lower),
            "ts": _time.time(),
            "source": "api",
        }
        self._discovery_cache[provider_key] = entry
        self._save_to_disk(provider_key, entry)

    # ------------------------------------------------------------------
    # Cache internals — disk
    # ------------------------------------------------------------------

    def _disk_path(self, provider_key: str) -> Path:
        return _cache_dir() / f"{provider_key}.json"

    def _save_to_disk(self, provider_key: str, entry: dict) -> None:
        """Persist cache entry to disk.  NEVER writes API keys."""
        payload = {
            "provider": provider_key,
            "models": entry["models"],
            "last_sync": entry["ts"],
            "metadata": {
                "model_count": len(entry["models"]),
                "source": entry.get("source", "api"),
            },
        }
        try:
            self._disk_path(provider_key).write_text(
                _json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass  # Disk full or permission error — non-fatal

    def _load_from_disk(self, provider_key: str) -> dict | None:
        """Load a single provider cache from disk.  Returns None on any error."""
        try:
            path = self._disk_path(provider_key)
            if not path.exists():
                return None
            data = _json.loads(path.read_text(encoding="utf-8"))
            models = data.get("models", [])
            ts = data.get("last_sync", 0)
            if not isinstance(models, list) or not models:
                return None
            return {"models": models, "ts": float(ts), "source": "disk"}
        except Exception:
            return None

    def _load_all_from_disk(self) -> None:
        """Pre-load all disk caches into memory on startup."""
        try:
            for path in sorted(_cache_dir().glob("*.json")):
                provider_key = path.stem
                if provider_key in self._discovery_cache:
                    continue  # Already loaded (shouldn't happen at startup)
                entry = self._load_from_disk(provider_key)
                if entry:
                    self._discovery_cache[provider_key] = entry
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Filter
    # ------------------------------------------------------------------

    @staticmethod
    def _filter_models(provider_name: str, discovered: list[dict[str, object]]) -> list[str]:
        """Extract model names from discovery results."""
        return [m["name"] for m in discovered]
