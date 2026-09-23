"""services/news_file_transfer.py — CSV/JSON export/import of the News domain (plan batch L3.4).

Contract section 10 + screen_design "Hành vi xuất file"/"Hành vi nhập file":
export CSV/JSON of the filtered date range into ``config/paths.exports_dir()``;
import upserts by ``dedupe_key`` with ``source=import`` (compensating days the
app did not run); import must NOT overwrite an ``actual`` already recorded from
an authoritative source (ff_json/ff_html) unless the destination row is
currently ``stale``.  This module is the **sole owner** of every file
serializer/parser — the screen never parses ("Nguyên tắc", screen_design).
Data crossing this boundary is the typed ``core/news_models`` dataclasses (C3 —
results are typed, never bare dicts); staleness classification comes from
`core/news_freshness` through the repository's section-8 read (S1 — this module
installs no classification of its own).

Declared readings (V2 — decided here on purpose, recorded in the commit message):

* **One file covers both tables** — columns are the schema column names of
  sections 4.2/4.3 (frozen strings, V3(a)) plus the ``record_type``
  discriminator (``event``/``item``); a single-file round-trip restores both
  ``news_events`` and ``news_items`` of the filtered range.  ``id`` is never
  exported (assigned by the database on insert, section 5).
* **Event dedupe keys come from the file verbatim** (the section 4.2 formula
  owner stays ``ff_calendar_producer``; QD-4 scopes section 4.3 only); **item
  dedupe keys are ALWAYS recomputed** via
  ``core.news_models.news_item_dedupe_key`` from url/title/published_utc
  (QD-4 clause 3 — the import path calls the SAME core function; no third copy,
  and a drifted key inside a file is healed).
* **Required fields** — event rows: ``record_type/event_time_utc/currency/
  title/impact/source/dedupe_key``; item rows: ``record_type/kind/title/
  published_utc/source``.  A missing ``day_key`` is derived from
  ``event_time_utc``; ``status`` cannot be pinned by a file (the repository
  always re-classifies at upsert via ``news_freshness``, B4) — the file only
  supplies the SCHEDULED model placeholder.  A row missing a required field /
  carrying an unparseable value / an invalid enum **fails the WHOLE file**
  (``NewsFileTransferError``, nothing is written — DB stays intact): a
  round-trip file is always complete and a partial write would silently corrupt
  the user's data.
* **"Bỏ qua trùng" (screen_design d.1601) = rows of the import file whose
  ``dedupe_key`` already appeared earlier IN THE SAME FILE**; the first
  occurrence is imported, later ones are counted into ``skipped_duplicates``.
* **Import never writes an ``ingest_runs`` row** — the section 4.6 producer enum
  is frozen with no ``import`` value (R6); a file restore is a user action, not
  a producer turn.
* **Actual protection (section 10):** when an event's destination row already
  has an ``actual`` recorded from ff_json/ff_html and is NOT classified
  ``stale`` at read time, the import keeps that ``actual``/``actual_updated_at``
  (the other columns still update); ``stale`` rows (actual NULL, past grace)
  and rows imported earlier take the file's actual.  ``source=user`` rows are
  protected by the repository's merge rule 2.
* An empty file (no records) is rejected with a friendly error — an export of a
  real filtered range always carries records.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from config.paths import exports_dir
from core.news_models import (
    CalendarEvent,
    EventImpact,
    EventSource,
    EventStatus,
    ImpactHint,
    NewsItem,
    NewsItemKind,
    NewsItemSource,
    news_item_dedupe_key,
)
from services.news_repository import NewsRepository

__all__ = [
    "FileExportResult",
    "FileImportResult",
    "NewsFileTransferError",
    "export_news_range",
    "import_news_file",
]

# File columns = the schema column names of sections 4.2 + 4.3 (frozen, V3(a)) + record_type.
_COLUMNS: tuple[str, ...] = (
    "record_type",
    "day_key",
    "event_time_utc",
    "currency",
    "title",
    "impact",
    "forecast",
    "previous",
    "actual",
    "actual_updated_at",
    "status",
    "source",
    "dedupe_key",
    "raw_json",
    "fetched_at",
    "kind",
    "content",
    "url",
    "published_utc",
    "currencies_json",
    "impact_hint",
    "speaker_role",
    "excluded",
)

_SUPPORTED_FORMATS = ("csv", "json")


class NewsFileTransferError(Exception):
    """Friendly, typed parse/validation failure — NOTHING was written (DB intact)."""


@dataclass(frozen=True, slots=True)
class FileExportResult:
    """Outcome of one export turn (contract section 10) — file path + record counts."""

    path: str
    events_written: int
    items_written: int


@dataclass(frozen=True, slots=True)
class FileImportResult:
    """Outcome of one import turn (screen_design d.1601) — new / updated / skipped-duplicates.

    ``inserted``/``updated`` are the repository's typed numbers
    (``UpsertEventsResult``/``UpsertItemsResult`` — C3); ``skipped_duplicates``
    counts rows whose ``dedupe_key`` repeated earlier within the same file."""

    inserted: int
    updated: int
    skipped_duplicates: int


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export_news_range(
    repo: NewsRepository,
    from_utc: str,
    to_utc: str,
    file_format: str,
    out_dir: Path | None = None,
) -> FileExportResult:
    """Export both ``news_events`` + ``news_items`` of the date range to one CSV/JSON file.

    Reads through the repository (section 8 — ``events_in_range`` +
    ``items_in_range`` with ``exclude_flagged=False`` so the exclusion flag
    round-trips), writes into ``config/paths.exports_dir()`` by default
    (``out_dir`` exists for tests only).
    """
    fmt = str(file_format).lower()
    if fmt not in _SUPPORTED_FORMATS:
        raise NewsFileTransferError(
            f"định dạng không hỗ trợ: {file_format!r} (chỉ 'csv'/'json')"
        )
    events = repo.events_in_range(from_utc, to_utc)
    items = repo.items_in_range(from_utc, to_utc, exclude_flagged=False)
    target = (out_dir if out_dir is not None else exports_dir()) / f"news_export_{_file_stamp()}.{fmt}"
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = [_event_record(event) for event in events] + [_item_record(item) for item in items]
    if fmt == "csv":
        _write_csv(target, rows)
    else:
        _write_json(target, rows)
    return FileExportResult(path=str(target), events_written=len(events), items_written=len(items))


def _event_record(event: CalendarEvent) -> dict[str, object]:
    return {
        "record_type": "event",
        "day_key": event.day_key,
        "event_time_utc": event.event_time_utc,
        "currency": event.currency,
        "title": event.title,
        "impact": event.impact.value,
        "forecast": event.forecast,
        "previous": event.previous,
        "actual": event.actual,
        "actual_updated_at": event.actual_updated_at,
        "status": event.status.value,
        "source": event.source.value,
        "dedupe_key": event.dedupe_key,
        "raw_json": event.raw_json,
        "fetched_at": event.fetched_at,
        "kind": "",
        "content": "",
        "url": "",
        "published_utc": "",
        "currencies_json": "",
        "impact_hint": "",
        "speaker_role": "",
        "excluded": "",
    }


def _item_record(item: NewsItem) -> dict[str, object]:
    return {
        "record_type": "item",
        "day_key": "",
        "event_time_utc": "",
        "currency": "",
        "title": item.title,
        "impact": "",
        "forecast": "",
        "previous": "",
        "actual": "",
        "actual_updated_at": "",
        "status": "",
        "source": item.source.value,
        "dedupe_key": item.dedupe_key,
        "raw_json": "",
        "fetched_at": item.fetched_at,
        "kind": item.kind.value,
        "content": item.content,
        "url": item.url,
        "published_utc": item.published_utc,
        "currencies_json": json.dumps(item.currencies),
        "impact_hint": item.impact_hint.value if item.impact_hint is not None else "",
        "speaker_role": item.speaker_role,
        "excluded": 1 if item.excluded else 0,
    }


def _write_csv(target: Path, rows: list[dict[str, object]]) -> None:
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)


def _write_json(target: Path, rows: list[dict[str, object]]) -> None:
    with target.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=2)


def _file_stamp() -> str:
    """UTC stamp for the export file name (no ':' — safe on Windows)."""
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def import_news_file(repo: NewsRepository, path: str | Path) -> FileImportResult:
    """Import one CSV/JSON file — upsert by ``dedupe_key``, ``source=import``.

    The whole file is parsed + validated before any record is written (one bad
    row fails the whole file, DB intact).  No ``ingest_runs`` row is written
    (the section 4.6 producer enum is frozen without ``import`` — R6).
    """
    source = Path(path)
    if not source.is_file():
        raise NewsFileTransferError(f"file không tồn tại: {source}")
    suffix = source.suffix.lower()
    if suffix == ".csv":
        rows = _read_csv(source)
    elif suffix == ".json":
        rows = _read_json(source)
    else:
        raise NewsFileTransferError(f"định dạng không hỗ trợ: {suffix} (chỉ .csv/.json)")
    if not rows:
        raise NewsFileTransferError(f"file không chứa bản ghi nào: {source}")

    events: list[CalendarEvent] = []
    items: list[NewsItem] = []
    seen_events: set[str] = set()
    seen_items: set[str] = set()
    skipped_duplicates = 0
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise NewsFileTransferError(f"bản ghi {index} không phải đối tượng")
        row = dict(row)
        record_type = str(row.get("record_type") or "").strip()
        if record_type == "event":
            event = _event_from_row(row, index)
            if event.dedupe_key in seen_events:
                skipped_duplicates += 1
                continue
            seen_events.add(event.dedupe_key)
            events.append(event)
        elif record_type == "item":
            item = _item_from_row(row, index)
            if item.dedupe_key in seen_items:
                skipped_duplicates += 1
                continue
            seen_items.add(item.dedupe_key)
            items.append(item)
        else:
            raise NewsFileTransferError(
                f"bản ghi {index}: record_type phải là 'event' hoặc 'item' (được {record_type!r})"
            )

    events = _protect_authoritative_actuals(repo, events)
    inserted = 0
    updated = 0
    if events:
        event_result = repo.upsert_events(events)
        inserted += event_result.inserted
        updated += event_result.updated
    if items:
        item_result = repo.upsert_items(items)
        inserted += item_result.inserted
        updated += item_result.updated
    return FileImportResult(
        inserted=inserted,
        updated=updated,
        skipped_duplicates=skipped_duplicates,
    )


def _protect_authoritative_actuals(
    repo: NewsRepository, events: list[CalendarEvent]
) -> list[CalendarEvent]:
    """Contract section 10: keep an authoritative (ff_json/ff_html) ``actual``
    unless the destination row is currently ``stale``.

    Staleness comes from the repository's section-8 read, which re-classifies
    at read time through ``core/news_freshness`` (S1 — no classification
    installed here).  ``source=user`` rows are already protected by the
    repository's merge rule 2; rows imported earlier are not an authoritative
    source, so they take the file's actual.
    """
    if not events:
        return events
    window_start = min(event.event_time_utc for event in events)
    window_end = max(event.event_time_utc for event in events)
    existing = {
        event.dedupe_key: event for event in repo.events_in_range(window_start, window_end)
    }
    protected: list[CalendarEvent] = []
    for event in events:
        dest = existing.get(event.dedupe_key)
        if (
            dest is not None
            and dest.actual is not None
            and dest.source in (EventSource.FF_JSON, EventSource.FF_HTML)
            and dest.status != EventStatus.STALE
        ):
            protected.append(
                replace(event, actual=dest.actual, actual_updated_at=dest.actual_updated_at)
            )
        else:
            protected.append(event)
    return protected


def _read_csv(source: Path) -> list[dict[str, object]]:
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _read_json(source: Path) -> list[object]:
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise NewsFileTransferError(f"JSON không đọc được: {exc}") from exc
    if not isinstance(payload, list):
        raise NewsFileTransferError("JSON phải là mảng các bản ghi")
    return payload


# ---------------------------------------------------------------------------
# Row parsing (whole-file validation before any write — DB intact)
# ---------------------------------------------------------------------------


def _event_from_row(row: dict[str, object], row_no: int) -> CalendarEvent:
    event_time_utc = _time_cell(row, "event_time_utc", row_no, required=True)
    currency = _required_cell(row, "currency", row_no)
    title = _required_cell(row, "title", row_no)
    impact = _enum_cell(row, "impact", EventImpact, row_no)
    source = _enum_cell(row, "source", EventSource, row_no)
    dedupe_key = _required_cell(row, "dedupe_key", row_no)
    day_key = str(row.get("day_key") or "").strip() or event_time_utc[:10]
    raw_status = str(row.get("status") or "").strip()
    status = _parse_optional_enum(raw_status, EventStatus, row_no, "status")
    if status is None and raw_status:
        raise NewsFileTransferError(
            f"bản ghi {row_no}: giá trị {raw_status!r} của status không hợp lệ"
        )
    return CalendarEvent(
        day_key=day_key,
        event_time_utc=event_time_utc,
        currency=currency,
        title=title,
        impact=impact,
        status=status or EventStatus.SCHEDULED,
        source=source,
        dedupe_key=dedupe_key,
        fetched_at=_time_cell(row, "fetched_at", row_no, required=False) or "",
        forecast=_empty_to_none(row.get("forecast")),
        previous=_empty_to_none(row.get("previous")),
        actual=_empty_to_none(row.get("actual")),
        actual_updated_at=_time_cell(row, "actual_updated_at", row_no, required=False),
        raw_json=_empty_to_none(row.get("raw_json")),
    )


def _item_from_row(row: dict[str, object], row_no: int) -> NewsItem:
    kind = _enum_cell(row, "kind", NewsItemKind, row_no)
    source = _enum_cell(row, "source", NewsItemSource, row_no)
    title = _required_cell(row, "title", row_no)
    published_utc = _time_cell(row, "published_utc", row_no, required=True)
    url = _empty_to_none(row.get("url"))
    currencies = _currencies_cell(row, row_no)
    # QD-4 clause 3 — the import path calls the SAME core function (a third
    # copy is banned); a key drifted inside the file is healed by recomputation.
    dedupe_key = news_item_dedupe_key(url=url, title=title, published_utc=published_utc)
    raw_hint = str(row.get("impact_hint") or "").strip()
    hint = _parse_optional_enum(raw_hint, ImpactHint, row_no, "impact_hint")
    if hint is None and raw_hint:
        raise NewsFileTransferError(
            f"bản ghi {row_no}: giá trị {raw_hint!r} của impact_hint không hợp lệ"
        )
    return NewsItem(
        kind=kind,
        source=source,
        title=title,
        published_utc=published_utc,
        currencies=currencies,
        dedupe_key=dedupe_key,
        fetched_at=_time_cell(row, "fetched_at", row_no, required=False) or "",
        content=_empty_to_none(row.get("content")),
        url=url,
        impact_hint=hint,
        speaker_role=_empty_to_none(row.get("speaker_role")),
        excluded=_excluded_cell(row, row_no),
    )


def _required_cell(row: dict[str, object], key: str, row_no: int) -> str:
    raw = str(row.get(key) or "").strip()
    if not raw:
        raise NewsFileTransferError(f"bản ghi {row_no}: thiếu trường bắt buộc {key!r}")
    return raw


def _enum_cell(row: dict[str, object], key: str, member_type, row_no: int):
    raw = str(row.get(key) or "").strip()
    parsed = _parse_optional_enum(raw, member_type, row_no, key)
    if parsed is None:
        reason = "thiếu trường bắt buộc" if not raw else f"giá trị {raw!r} không hợp lệ"
        raise NewsFileTransferError(f"bản ghi {row_no}: {key} — {reason}")
    return parsed


def _parse_optional_enum(raw: str, member_type, row_no: int, key: str):
    if not raw:
        return None
    try:
        return member_type(raw)
    except ValueError:
        return None


def _time_cell(row: dict[str, object], key: str, row_no: int, *, required: bool) -> str | None:
    raw = str(row.get(key) or "").strip()
    if not raw:
        if required:
            raise NewsFileTransferError(f"bản ghi {row_no}: thiếu trường bắt buộc {key!r}")
        return None
    normalized = _normalize_ts(raw)
    if normalized is None:
        raise NewsFileTransferError(f"bản ghi {row_no}: {key} không đọc được ({raw!r})")
    return normalized


def _normalize_ts(value: str) -> str | None:
    """A timestamp normalized to the domain's ISO-8601 UTC khuôn
    (``YYYY-MM-DDTHH:MM:SSZ``) — a naive value is read as UTC."""
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _currencies_cell(row: dict[str, object], row_no: int) -> list[str]:
    raw = str(row.get("currencies_json") or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise NewsFileTransferError(
            f"bản ghi {row_no}: currencies_json không đọc được ({exc})"
        ) from exc
    if not isinstance(parsed, list):
        raise NewsFileTransferError(f"bản ghi {row_no}: currencies_json phải là mảng mã")
    return [str(code).strip() for code in parsed if str(code).strip()]


def _excluded_cell(row: dict[str, object], row_no: int) -> bool:
    raw = str(row.get("excluded") or "").strip().lower()
    if raw in ("1", "true"):
        return True
    if raw in ("", "0", "false"):
        return False
    raise NewsFileTransferError(
        f"bản ghi {row_no}: excluded phải là 0/1 hoặc true/false (được {raw!r})"
    )


def _empty_to_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text.strip() else None