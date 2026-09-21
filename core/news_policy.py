"""News domain policy — the single versioned config seam of the News domain (S4).

This module owns loading and validating the News domain policy file
(``config/news_policy.json``, contract §7).  Every operational number of the
domain (poll cadence, collection window, refresh cadence, staleness grace,
ingest freshness, retention, AI thresholds, horizon definitions) lives in that
file and nowhere else: no magic number in logic (S4), no second copy of a value
(D5).

Governance:

* **No implicit default.** The contract §7 table is the mandatory key set.  A
  missing file, unreadable JSON, missing key, wrong ``policy_version`` or wrong
  type raises a typed error — nothing is ever filled in silently, so a broken
  policy can never be read as a working one (B4, fail-closed).
* **No fabricated number.** Values inherited from the current runtime carry an
  explicit evidence label in the policy file (B5).  This module only reads.
* Keys prefixed with ``_`` are governance markers (acceptance/provenance notes)
  and are ignored; any other unknown key is rejected, so a renamed or mistyped
  key can never sit in the file "accepted but unused".
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

# Machine-read provenance key (V3(a) exception — never shown on UI, never renamed
# once persisted); the file itself is the runtime source of the values.
NEWS_POLICY_VERSION: Final = "news-policy"

DEFAULT_NEWS_POLICY_FILENAME: Final = "news_policy.json"

# The three AI horizons, fixed by the contract vocabulary (§4.5, §7): one verdict
# row per horizon per scope.
HORIZON_KEYS: Final[tuple[str, ...]] = ("short", "mid", "long")
HORIZON_UNITS: Final[tuple[str, ...]] = ("day", "week", "month")

HORIZON_FIELDS: Final[frozenset[str]] = frozenset({"unit", "min", "max"})

# Contract §7 key set: the policy exists only when every one of these is supplied.
MANDATORY_KEYS: Final[frozenset[str]] = frozenset(
    {
        "policy_version",
        "rss_poll_interval_minutes",
        "rss_window_hours",
        "fred_refresh_hours",
        "event_stale_grace_minutes",
        "ingest_freshness_hours",
        "ingest_runs_retention_days",
        "ai_window_days",
        "ai_min_items",
        "ai_horizons",
    }
)

# Every span/interval key must be a strictly positive whole number of its unit.
POSITIVE_INT_FIELDS: Final[tuple[str, ...]] = (
    "rss_poll_interval_minutes",
    "rss_window_hours",
    "fred_refresh_hours",
    "event_stale_grace_minutes",
    "ingest_freshness_hours",
    "ingest_runs_retention_days",
    "ai_window_days",
    "ai_min_items",
)


class NewsPolicyError(ValueError):
    """Typed misuse: a news policy is not shaped/versioned correctly."""

    def __init__(self, path: str, detail: str) -> None:
        self.path = path
        self.detail = detail
        super().__init__(f"NEWS_POLICY_INVALID at {path}: {detail}")


class NewsPolicyLoadError(NewsPolicyError):
    """Typed fault: the policy file could not be read/parsed as a policy."""


@dataclass(frozen=True, slots=True)
class HorizonDefinition:
    """One AI horizon span as the Owner wrote it (contract §7 ``ai_horizons``).

    The span keeps its original unit (day/week/month) instead of being converted
    to days, so no conversion convention is invented on the way in.
    """

    unit: str
    min_value: int
    max_value: int


def _require_key(data: Mapping[str, Any], key: str) -> Any:
    """Read a mandatory key — an absent key is a defect, never a default."""
    if key not in data:
        raise NewsPolicyError(key, "missing mandatory key")
    return data[key]


def _require_positive_int(value: object, path: str) -> int:
    """Strict int reader: bool/float/str stand-ins are malformed, not coerced."""
    if type(value) is not int or value <= 0:
        raise NewsPolicyError(path, "expected a positive integer")
    return value


def _require_non_negative_int(value: object, path: str) -> int:
    if type(value) is not int or value < 0:
        raise NewsPolicyError(path, "expected a non-negative integer")
    return value


def _require_policy_version(value: object) -> str:
    if value != NEWS_POLICY_VERSION:
        raise NewsPolicyError("policy_version", f"expected {NEWS_POLICY_VERSION!r}")
    return NEWS_POLICY_VERSION


def _freeze_horizons(value: object) -> Mapping[str, HorizonDefinition]:
    """Validate the three typed horizon spans and freeze them (immutable mapping)."""
    if not isinstance(value, Mapping) or set(value) != set(HORIZON_KEYS):
        raise NewsPolicyError("ai_horizons", f"expected exactly {list(HORIZON_KEYS)}")
    horizons: dict[str, HorizonDefinition] = {}
    for key in HORIZON_KEYS:
        span = value[key]
        path = f"ai_horizons.{key}"
        if not isinstance(span, HorizonDefinition):
            raise NewsPolicyError(path, "expected a HorizonDefinition")
        if span.unit not in HORIZON_UNITS:
            raise NewsPolicyError(
                f"{path}.unit", f"expected one of {list(HORIZON_UNITS)}"
            )
        _require_non_negative_int(span.min_value, f"{path}.min")
        _require_positive_int(span.max_value, f"{path}.max")
        if span.min_value >= span.max_value:
            raise NewsPolicyError(path, "min must be lower than max")
        horizons[key] = span
    return MappingProxyType(horizons)


def _horizons_from_raw(value: object) -> Mapping[str, HorizonDefinition]:
    """Read the raw §7 JSON block into typed spans, then validate and freeze them."""
    if not isinstance(value, Mapping) or set(value) != set(HORIZON_KEYS):
        raise NewsPolicyError("ai_horizons", f"expected exactly {list(HORIZON_KEYS)}")
    spans: dict[str, HorizonDefinition] = {}
    for key in HORIZON_KEYS:
        raw = value[key]
        path = f"ai_horizons.{key}"
        if not isinstance(raw, Mapping) or set(raw) != HORIZON_FIELDS:
            raise NewsPolicyError(
                path, f"expected exactly {sorted(HORIZON_FIELDS)}"
            )
        spans[key] = HorizonDefinition(
            unit=raw["unit"], min_value=raw["min"], max_value=raw["max"]
        )
    return _freeze_horizons(spans)


@dataclass(frozen=True, slots=True)
class NewsPolicy:
    """The News domain operational numbers — contract §7, key for key.

    Every field is mandatory: no field carries a default, so a policy object
    cannot exist in a half-decided state.
    """

    policy_version: str
    rss_poll_interval_minutes: int
    rss_window_hours: int
    fred_refresh_hours: int
    event_stale_grace_minutes: int
    ingest_freshness_hours: int
    ingest_runs_retention_days: int
    ai_window_days: int
    ai_min_items: int
    ai_horizons: Mapping[str, HorizonDefinition]

    def __post_init__(self) -> None:
        _require_policy_version(self.policy_version)
        for name in POSITIVE_INT_FIELDS:
            _require_positive_int(getattr(self, name), name)
        object.__setattr__(self, "ai_horizons", _freeze_horizons(self.ai_horizons))

    @classmethod
    def from_dict(cls, data: object) -> "NewsPolicy":
        """Build the policy from a parsed JSON object (strict identity).

        Every contract §7 key must be present and well-typed; unknown keys are
        rejected except ``_``-prefixed governance markers.
        """
        if not isinstance(data, Mapping):
            raise NewsPolicyError("<root>", "expected a JSON object")
        unknown = sorted(
            key
            for key in data
            if not (isinstance(key, str) and key.startswith("_"))
            and key not in MANDATORY_KEYS
        )
        if unknown:
            raise NewsPolicyError("<root>", f"unknown key(s): {unknown}")
        return cls(
            policy_version=_require_policy_version(
                _require_key(data, "policy_version")
            ),
            rss_poll_interval_minutes=_require_positive_int(
                _require_key(data, "rss_poll_interval_minutes"),
                "rss_poll_interval_minutes",
            ),
            rss_window_hours=_require_positive_int(
                _require_key(data, "rss_window_hours"), "rss_window_hours"
            ),
            fred_refresh_hours=_require_positive_int(
                _require_key(data, "fred_refresh_hours"), "fred_refresh_hours"
            ),
            event_stale_grace_minutes=_require_positive_int(
                _require_key(data, "event_stale_grace_minutes"),
                "event_stale_grace_minutes",
            ),
            ingest_freshness_hours=_require_positive_int(
                _require_key(data, "ingest_freshness_hours"),
                "ingest_freshness_hours",
            ),
            ingest_runs_retention_days=_require_positive_int(
                _require_key(data, "ingest_runs_retention_days"),
                "ingest_runs_retention_days",
            ),
            ai_window_days=_require_positive_int(
                _require_key(data, "ai_window_days"), "ai_window_days"
            ),
            ai_min_items=_require_positive_int(
                _require_key(data, "ai_min_items"), "ai_min_items"
            ),
            ai_horizons=_horizons_from_raw(_require_key(data, "ai_horizons")),
        )


def load_news_policy(path: str | Path | None = None) -> NewsPolicy:
    """Load the News domain policy from config (fail-closed).

    Reads ``config/news_policy.json`` by default.  Any failure (missing file,
    unreadable JSON, missing/wrong key, wrong ``policy_version``) raises
    ``NewsPolicyLoadError``; there is no fallback policy object and no implicit
    default, so a broken config surfaces as a typed fault instead of running on
    values nobody decided (B4).
    """
    if path is None:
        from config.paths import CONFIG_DIR

        resolved = CONFIG_DIR / DEFAULT_NEWS_POLICY_FILENAME
    else:
        resolved = Path(path)
    try:
        raw = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        raise NewsPolicyLoadError(str(resolved), f"cannot read file: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise NewsPolicyLoadError(str(resolved), f"invalid JSON: {exc}") from exc
    try:
        return NewsPolicy.from_dict(data)
    except NewsPolicyError as exc:
        raise NewsPolicyLoadError(str(resolved), exc.detail) from exc
