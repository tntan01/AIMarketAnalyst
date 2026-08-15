"""Scanner V4 backtest safety-data audit (Bước 09; target-only).

Mục 9B: inventory dữ liệu **historical point-in-time** cho năm sub-gate safety —
connectivity, candle freshness, spread, news/event, volatility.  Nếu có dữ liệu
PIT hợp lệ thì phát evidence + provenance; không có thì ``MISSING``/``UNKNOWN``
và **tuyệt đối không** được thay missing bằng normal/no-news/PASS để tăng sample
calibration.

The audit looks at declared data sources only.  A valid source must state its
timestamp coverage (``observed_from``/``observed_to``), a ``checked_at``, a
provenance path, and every observation must carry its own timestamp
(``point_in_time=True`` — the raw data preserves per-observation time, so a
replay can reproduce the gate input exactly).  Anything outside a point-in-time
boundary or missing a timestamp is excluded and the category is reported
``MISSING``/``UNKNOWN``.

The result of the audit is a report, not a gate.  Whether a ``MISSING`` category
drives the production safety gate to ``UNKNOWN`` is the gate's own fail-closed
behaviour; this module records that the data does NOT exist so nothing downstream
may assume it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, TypeAlias

from core.reason_codes import (
    SCANNER_V4_SAFETY_AUDIT_MISSING,
    SCANNER_V4_SAFETY_AUDIT_NON_PIT,
    SCANNER_V4_SAFETY_AUDIT_UNKNOWN,
)

SCANNER_V4_SAFETY_AUDIT_VERSION = "scanner-v4-safety-audit-v1"

SAFETY_AUDIT_CATEGORIES = (
    "connectivity",
    "data_freshness",
    "spread",
    "news",
    "volatility",
)

AVAILABLE = "AVAILABLE"
MISSING = "MISSING"
NON_PIT = "NON_PIT"
UNKNOWN = "UNKNOWN"

SafetyAuditStatus: TypeAlias = Literal["AVAILABLE", "MISSING", "NON_PIT", "UNKNOWN"]


@dataclass(frozen=True, slots=True)
class SafetyDataSource:
    """One declared historical data source for one safety category.

    ``observed_from`` / ``observed_to`` delimit the raw-data time coverage;
    ``point_in_time`` is True only when every observation keeps its own
    timestamp (so point-in-time replay is possible).  ``checked_at`` is when
    the source was verified as present and parseable.
    """

    category: str
    source: str
    observed_from: datetime
    observed_to: datetime
    point_in_time: bool
    provenance: str
    checked_at: datetime
    sample_count: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "source": self.source,
            "observed_from": self.observed_from.isoformat(),
            "observed_to": self.observed_to.isoformat(),
            "point_in_time": self.point_in_time,
            "provenance": self.provenance,
            "checked_at": self.checked_at.isoformat(),
            "sample_count": self.sample_count,
        }


@dataclass(frozen=True, slots=True)
class SafetyAuditItem:
    category: str
    status: SafetyAuditStatus
    sources: tuple[SafetyDataSource, ...]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "status": self.status,
            "sources": [s.to_dict() for s in self.sources],
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True, slots=True)
class SafetyDataAuditReport:
    audit_version: str
    pit_boundary: datetime
    items: tuple[SafetyAuditItem, ...]
    sufficient_for_calibration: bool
    blockers: tuple[str, ...]

    def by_category(self) -> dict[str, SafetyAuditItem]:
        return {item.category: item for item in self.items}

    def to_dict(self) -> dict[str, object]:
        return {
            "audit_version": self.audit_version,
            "pit_boundary": self.pit_boundary.isoformat(),
            "items": [item.to_dict() for item in self.items],
            "sufficient_for_calibration": self.sufficient_for_calibration,
            "blockers": list(self.blockers),
        }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def audit_safety_data(
    declared: tuple[SafetyDataSource, ...],
    *,
    pit_boundary: datetime,
    minimum_required: dict[str, int] | None = None,
) -> SafetyDataAuditReport:
    """Inventory declared safety data against a point-in-time boundary.

    Rules (fail-closed):

    * a source covering the boundary with ``point_in_time=True`` → the category
      is ``AVAILABLE`` (with one or more eligible sources);
    * sources that exist but break PIT (missing per-observation timestamps or
      type-coerced) → the category is recorded ``NON_PIT`` (never AVAILABLE);
    * ``point_in_time=True`` sources may still be excluded when they do not
      cover the calibration boundary — the category then reports ``MISSING``
      for that boundary (source listed, not eligible);
    * no declaration at all → ``MISSING``.
    """
    minimum_required = minimum_required or {}
    items: list[SafetyAuditItem] = []
    blockers: list[str] = []
    sufficient = True

    for category in SAFETY_AUDIT_CATEGORIES:
        category_sources = [s for s in declared if s.category == category]
        reasons: list[str] = []
        status: SafetyAuditStatus = MISSING
        eligible: list[SafetyDataSource] = []

        for source in category_sources:
            if not source.point_in_time:
                reasons.append(SCANNER_V4_SAFETY_AUDIT_NON_PIT)
                status = NON_PIT if status != MISSING or not eligible else NON_PIT
                continue
            # A PIT source still must actually cover the calibration boundary.
            if source.observed_from <= pit_boundary <= source.observed_to:
                eligible.append(source)
            else:
                reasons.append(SCANNER_V4_SAFETY_AUDIT_UNKNOWN)

        if eligible:
            status = AVAILABLE
        else:
            if not category_sources:
                reasons = [SCANNER_V4_SAFETY_AUDIT_MISSING]
                status = MISSING
            elif status != NON_PIT:
                status = UNKNOWN if reasons else MISSING

        minimum = minimum_required.get(category, 0)
        coverage = sum(max(0, (s.observed_to - s.observed_from).days) for s in eligible)
        if status == AVAILABLE:
            if minimum and coverage < minimum:
                sufficient = False
                blockers.append(
                    f"{category}: coverage {coverage}d < minimum {minimum}d"
                )
        else:
            sufficient = False
            blockers.append(f"{category}: {status} (no PIT data at boundary)")

        items.append(
            SafetyAuditItem(
                category=category,
                status=status,
                sources=tuple(eligible) or tuple(category_sources),
                reason_codes=tuple(dict.fromkeys(reasons)),
            )
        )

    return SafetyDataAuditReport(
        audit_version=SCANNER_V4_SAFETY_AUDIT_VERSION,
        pit_boundary=pit_boundary,
        items=tuple(items),
        sufficient_for_calibration=sufficient,
        blockers=tuple(blockers),
    )


def is_eligible_for_entry(item: SafetyAuditItem) -> bool:
    """Whether a category's historical data is usable for auto-entry evidence.

    Only ``AVAILABLE`` qualifies.  ``NON_PIT``/``UNKNOWN``/``MISSING`` all return
    False — none of them may be treated as normal/no-news/PASS.
    """
    return item.status == AVAILABLE