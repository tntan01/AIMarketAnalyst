"""services/ff_source_parser.py — bóc tách mã nguồn trang ForexFactory (plan lô F2, QĐ-F3).

Sole owner của hai phép chuyển đổi thuần của kênh dán mã nguồn (contract §6.1
bước 3-6 đợt 3-4, §11b): mã nguồn trang dán → mô hình miền có kiểu (`CalendarEvent`
+ `RateObservation` lãi suất `ff_html`) và hai thao tác trên lô đã bóc
(phân loại dòng + chung thiện lô đã chỉnh sửa).

**Chỉ hàm thuần** (L2, R7 — không singleton/DI): không I/O, không Qt, không
mạng, không DB, không chuỗi hiển thị (L3).  Văn bản source thô KHÔNG thoát khỏi
parser này (R8): API công khai chỉ nhận `str` và chỉ trả mô hình `core/` + kết
quả có kiểu.  `fetched_at` là tham số thuần do caller (F3) cấp — parser không
tự bịa mốc thời gian.

Module xuất 3 hàm thuần:

1. ``parse_calendar_source(source_text, *, fetched_at)`` — bước bóc tách (§6.1
   bước 3-4): trích các khối nhúng ``window.calendarComponentStates[...]``
   (mọi component id, mọi ngày trong mọi ``days[]``), ánh xạ từng sự kiện đúng
   bước 3, bóc quan sát lãi suất theo danh mục kế thừa
   ``_FOREX_RATE_EVENTS`` (bước 4 — R4/B5: chép nguyên văn
   ``interest_rate_service.py`` d.29-38), trả ``SourceParseOutcome(events,
   rates, error)`` — all-or-nothing (B4): source không chứa dữ liệu lịch →
   ``ParseError(NOT_FOUND, ...)``; JSON hỏng/cắt cụt → ``ParseError(MALFORMED,
   ...)`` và không trả nửa vời.
2. ``classify_incoming_events(events, existing)`` — phân loại dòng §6.1 bước 5
   đợt 4: mỗi sự kiện → ``RowDisposition`` (``new`` / ``will_update`` /
   ``conflict_keep_manual``) khớp theo ``dedupe_key``, không I/O.
3. ``finalize_edited_batch(events, *, edited_actuals, fetched_at)`` — chung
   thiện lô §6.1 bước 6 đợt 4 (QĐ-F6): dòng có actual người dùng đã sửa →
   stamp ``source=user``, giá trị actual FF gốc GIỮ trong ``raw_json``; dòng
   không sửa giữ ``ff_html``; quan sát lãi suất trong danh mục được dẫn lại
   từ actual cuối (stamp ``ff_html`` — enum §4.4 không có ``user``);
   ``dedupe_key`` BẤT BIẾN (gọi hàm core, không tính lại — QD-8).

Khai báo đọc-hiểu (V2 — quyết tại đây có chủ đích, không lặng lẽ):

* **Trùng sự kiện giữa các component:** cùng một sự kiện FF có thể xuất hiện ở
  nhiều view chồng lấn (trang chủ "today" + widget lịch), nên sự kiện được khử
  trùng theo ``id`` thô xuyên mọi ``days[]``/component — lần xuất hiện đầu
  thắng, giữ thứ tự.
* **Dòng không dùng được thì bỏ, không bịa** (B4/B5): sự kiện thiếu ``dateline``
  số hoặc thiếu đồng tiền bị bỏ — soi gương bỏ-theo-dòng của
  ``ff_calendar_producer`` cũ; ``impactName`` ngoài ``high``/``medium``/``low``
  (gồm ``holiday``) ánh xạ ``non`` (§6.1 bước 3: ``holiday`` → ``non``).
* **Khuôn mốc thời gian:** ``dateline`` (Unix epoch, đã chuẩn UTC) →
  ``event_time_utc`` ISO-8601 UTC, độ chính xác giây, hậu tố ``Z`` — cùng khuôn
  mà các producer của repository ghi (``_utc_now``), nên so sánh chuỗi trong
  ``events_in_range`` vẫn đúng thứ tự.
* **``raw_json`` phục vụ provenance:** mỗi sự kiện giữ JSON của các trường
  nguồn đã trích (``id``/``name``/``prefixedName``/``currency``/``impactName``/
  ``dateline``/``forecast``/``previous``/``actual``/``revision``/``notice``/
  ``ebaseId``/``soloUrl``) — bước 3 nêu revision/notice/ebaseId/soloUrl, và
  actual FF gốc phải sống trong ``raw_json`` để duy trì provenance khi dòng bị
  sửa (bước 6 đợt 4).
* **Quan sát lãi suất của dòng đã sửa:** khi sự kiện trong danh mục bị sửa
  actual, ``rate`` của quan sát được parse từ actual cuối (cùng ``_parse_rate``
  lúc bóc), ``observed_at`` giữ ``day_key`` của sự kiện.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import Enum

from core.news_models import (
    CalendarEvent,
    EventImpact,
    EventSource,
    EventStatus,
    RateObservation,
    RateSource,
    calendar_event_dedupe_key,
)

__all__ = [
    "FinalizedBatch",
    "ParseError",
    "ParseErrorKind",
    "RowDisposition",
    "SourceParseOutcome",
    "classify_incoming_events",
    "finalize_edited_batch",
    "parse_calendar_source",
]


# ---------------------------------------------------------------------------
# Dữ liệu runtime kế thừa (R4/B5 — kế thừa runtime hiện hành, không bịa)
# ---------------------------------------------------------------------------

# interest_rate_service.py:29-38 — tiền tệ → mẫu tên sự kiện lãi suất trên
# ForexFactory (nguyên văn; khớp bằng ``pattern in name`` trên tên đã lower()).
_FOREX_RATE_EVENTS: dict[str, list[str]] = {
    "USD": ["federal funds rate", "fed funds rate"],
    "EUR": ["ecb deposit rate", "ecb interest rate", "ecb refinancing rate"],
    "GBP": ["boe official bank rate", "mpc official bank rate", "boe interest rate"],
    "JPY": ["boj policy rate", "boj interest rate"],
    "AUD": ["cash rate"],
    "NZD": ["official cash rate"],
    "CAD": ["overnight rate"],
    "CHF": ["snb policy rate", "snb interest rate"],
}

# ---------------------------------------------------------------------------
# Kết quả có kiểu (C3 — không dict trần qua ranh giới)
# ---------------------------------------------------------------------------


class ParseErrorKind(Enum):
    """Phân loại lỗi bóc tách có kiểu (L3 — không chuỗi hiển thị).

    ``NOT_FOUND``: source không chứa dữ liệu lịch (không có khối
    ``calendarComponentStates`` hoặc không có ``days[]`` nào bóc được).
    ``MALFORMED``: JSON lịch hỏng/cắt cụt (all-or-nothing — không ghi nửa vời)."""

    NOT_FOUND = "not_found"
    MALFORMED = "malformed"


@dataclass(frozen=True, slots=True)
class ParseError(Exception):
    """Một lỗi bóc tách có kiểu (contract §4.6 / §6.1 — mã máy + chi tiết).

    Vừa là giá trị kết quả (``SourceParseOutcome.error``) vừa raise/except
    được trong nội bộ module — nhưng luôn là lỗi CÓ KIỂU, không chuỗi hiển
    thị (L3)."""

    kind: ParseErrorKind
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class SourceParseOutcome:
    """Kết quả có kiểu của ``parse_calendar_source`` (C3).

    ``error`` None đúng khi bóc tách trọn vẹn (``events``/``rates`` đầy đủ);
    khi có lỗi thì all-or-nothing — cả hai danh sách rỗng (B4)."""

    events: list[CalendarEvent]
    rates: list[RateObservation]
    error: ParseError | None = None


class RowDisposition(Enum):
    """Mối quan hệ của MỘT dòng lô dán với database hiện hữu (§6.1 bước 5 đợt 4).

    Giá trị máy đọc; nhãn hiển thị ("Mới" / "Sẽ cập nhật" / "Xung đột — giữ
    nhập tay" / "Đã sửa") thuộc từ điển đã đăng ký của màn."""

    NEW = "new"
    WILL_UPDATE = "will_update"
    CONFLICT_KEEP_MANUAL = "conflict_keep_manual"


@dataclass(frozen=True, slots=True)
class FinalizedBatch:
    """Lô sau khi áp chỉnh sửa actual của người dùng (§6.1 bước 6 đợt 4)."""

    events: list[CalendarEvent]
    rates: list[RateObservation]


_COMPONENT_RE = re.compile(r"window\.calendarComponentStates\[\s*(\d+)\s*\]\s*=\s*")
_DAYS_OPEN_RE = re.compile(r"\bdays\s*:\s*(\[)", re.DOTALL)

# ---------------------------------------------------------------------------
# 1. Bóc tách (§6.1 bước 3-4)
# ---------------------------------------------------------------------------


def parse_calendar_source(source_text: str, *, fetched_at: str) -> SourceParseOutcome:
    """Bóc lịch kinh tế + lãi suất từ mã nguồn trang đã dán (§6.1 bước 3-4).

    Trích mọi khối ``window.calendarComponentStates[...]``, gộp mọi ngày của
    mọi ``days[]`` (khử trùng theo ``id``), ánh xạ từng sự kiện theo bước 3
    (``dateline`` → ``event_time_utc``/``day_key`` UTC; ``prefixedName`` →
    ``title``; ``impactName`` → ``impact``, ``holiday`` → ``non``; chuỗi rỗng
    → NULL; ``revision``/``notice``/``ebaseId``/``soloUrl`` → ``raw_json``;
    stamp ``source=ff_html``; ``dedupe_key`` GỌI hàm ``core/news_models.py``
    — QD-8, không bản sao), rồi bóc quan sát lãi suất theo ``_FOREX_RATE_EVENTS``
    (bước 4).  All-or-nothing (B4): lỗi có kiểu + không ghi gì.
    """
    try:
        raw_events = _extract_raw_events(source_text)
    except ParseError as error:
        return SourceParseOutcome(events=[], rates=[], error=error)
    events = [
        _event_from_raw(raw, fetched_at)
        for raw in raw_events
        if _usable_raw(raw)
    ]
    rates = _rate_observations_from_events(events, fetched_at)
    return SourceParseOutcome(events=events, rates=rates, error=None)


def _extract_raw_events(source_text: str) -> list[dict[str, object]]:
    """Gom các sự kiện thô của mọi component/mọi ngày; ném ParseError khi lịch
    thiếu hoặc hỏng (all-or-nothing)."""
    matches = list(_COMPONENT_RE.finditer(source_text))
    if not matches:
        raise ParseError(
            ParseErrorKind.NOT_FOUND,
            "source contains no window.calendarComponentStates block",
        )
    raw_events: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    any_days_seen = False
    for index, match in enumerate(matches):
        statement = _component_statement(source_text, match.end(), matches, index)
        days_open = _DAYS_OPEN_RE.search(statement)
        if days_open is None:
            continue  # widget không có bảng lịch — không phải dữ liệu lịch
        any_days_seen = True
        try:
            days, _end = json.JSONDecoder().raw_decode(
                statement[days_open.start(1):]
            )
        except (ValueError, json.JSONDecodeError) as exc:
            raise ParseError(
                ParseErrorKind.MALFORMED, f"calendar days JSON: {exc}"
            ) from exc
        if not isinstance(days, list):
            raise ParseError(ParseErrorKind.MALFORMED, "calendar days is not a list")
        for day in days:
            if not isinstance(day, dict):
                continue
            for raw in day.get("events") or []:
                if not isinstance(raw, dict):
                    continue
                event_id = raw.get("id")
                if event_id is not None:
                    key = str(event_id)
                    if key in seen_ids:
                        continue
                    seen_ids.add(key)
                raw_events.append(raw)
    if not any_days_seen:
        raise ParseError(
            ParseErrorKind.NOT_FOUND,
            "no parseable calendar days found in the source",
        )
    return raw_events


def _component_statement(
    source_text: str, start: int, matches: list[re.Match[str]], index: int
) -> str:
    """Đoạn nguồn của MỘT component: từ sau ``=`` tới component kế tiếp (hoặc
    hết text) — giới hạn tìm ``days:`` đúng trong object của component đó."""
    end = matches[index + 1].start() if index + 1 < len(matches) else len(source_text)
    return source_text[start:end]


def _usable_raw(raw: dict[str, object]) -> bool:
    """Dòng có thể ánh xạ: có ``dateline`` số và có đồng tiền (B4/V2 — dòng
    không dùng được bỏ, soi gương producer lịch cũ)."""
    if not str(raw.get("currency") or "").strip():
        return False
    return isinstance(raw.get("dateline"), (int, float))


def _event_from_raw(raw: dict[str, object], fetched_at: str) -> CalendarEvent:
    """Ánh xạ §6.1 bước 3 MỘT sự kiện nguồn → ``CalendarEvent``."""
    event_time_utc = datetime.fromtimestamp(
        int(raw["dateline"]), tz=UTC
    ).isoformat(timespec="seconds").replace("+00:00", "Z")
    currency = str(raw.get("currency") or "").strip()
    title = str(raw.get("prefixedName") or "").strip()
    return CalendarEvent(
        day_key=event_time_utc[:10],
        event_time_utc=event_time_utc,
        currency=currency,
        title=title,
        impact=_map_impact(raw.get("impactName", "")),
        status=EventStatus.SCHEDULED,
        source=EventSource.FF_HTML,
        dedupe_key=calendar_event_dedupe_key(
            event_time_utc=event_time_utc, currency=currency, title=title
        ),
        fetched_at=fetched_at,
        forecast=_clean_value(raw.get("forecast")),
        previous=_clean_value(raw.get("previous")),
        actual=_clean_value(raw.get("actual")),
        raw_json=_raw_json(raw),
    )


def _map_impact(value: object) -> EventImpact:
    """``impactName`` (high/medium/low/holiday) → enum §4.2; ``holiday`` (và mọi
    giá trị bất ngờ khác) → ``non`` (§6.1 bước 3 — không bịa mức mới)."""
    text = str(value or "").strip().lower()
    try:
        return EventImpact(text)
    except ValueError:
        return EventImpact.NON


def _clean_value(value: object) -> str | None:
    """Chuỗi rỗng → NULL; ngược lại giữ nguyên chuỗi đã strip (§6.1 bước 3)."""
    text = str(value or "").strip()
    return text or None


def _raw_json(raw: dict[str, object]) -> str:
    """Provenance từng sự kiện (không lưu cả trang — §6.1 bước 3; actual FF gốc
    nằm đây để duy trì qua chỉnh sửa đợt 4)."""
    fields = {
        key: raw.get(key)
        for key in (
            "id", "name", "prefixedName", "currency", "impactName", "dateline",
            "forecast", "previous", "actual", "revision", "notice", "ebaseId",
            "soloUrl",
        )
    }
    return json.dumps(fields, ensure_ascii=False)


def _rate_observations_from_events(
    events: Sequence[CalendarEvent], fetched_at: str
) -> list[RateObservation]:
    """Bóc quan sát lãi suất (§6.1 bước 4): sự kiện khớp danh mục kế thừa, có
    actual đọc được.  Hàm dùng chung cho parse và cho chung-thiện-lô (kết quả
    sau khi dẫn actual cuối)."""
    observations: list[RateObservation] = []
    for event in events:
        patterns = _FOREX_RATE_EVENTS.get(event.currency)
        if not patterns:
            continue
        name = event.title.lower()
        if not any(pattern in name for pattern in patterns):
            continue
        if event.actual is None:
            continue
        rate = _parse_rate(event.actual)
        if rate is None:
            continue
        observations.append(
            RateObservation(
                currency=event.currency,
                rate=rate,
                observed_at=event.day_key,
                source=RateSource.FF_HTML,
                fetched_at=fetched_at,
            )
        )
    return observations


def _parse_rate(value: str) -> float | None:
    """Đọc ``rate`` từ actual dạng "0.00%" → 0.0 (khuôn d.116/178 của đường lãi
    suất cũ — giá trị không đọc được bị bỏ, không bịa)."""
    try:
        return float(str(value).replace("%", "").strip())
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 2. Phân loại dòng (§6.1 bước 5 đợt 4 — hàm thuần, không I/O)
# ---------------------------------------------------------------------------


def classify_incoming_events(
    events: Sequence[CalendarEvent],
    existing: Sequence[CalendarEvent],
) -> list[RowDisposition]:
    """Phân loại từng dòng của lô dán so với database theo ``dedupe_key``:

    ``new`` — chưa có bản ghi; ``will_update`` — khớp khoá (sẽ cập nhật theo
    3 quy tắc merge); ``conflict_keep_manual`` — bản ghi hiện hữu ``source=user``
    mà actual KHÁC giá trị bóc (§6.1 bước 5 đợt 4).  Trả một disposition cho
    từng event của lô, cùng thứ tự."""
    by_key = {existing_event.dedupe_key: existing_event for existing_event in existing}
    dispositions: list[RowDisposition] = []
    for event in events:
        current = by_key.get(event.dedupe_key)
        if current is None:
            dispositions.append(RowDisposition.NEW)
        elif (
            current.source == EventSource.USER
            and current.actual != event.actual
        ):
            dispositions.append(RowDisposition.CONFLICT_KEEP_MANUAL)
        else:
            dispositions.append(RowDisposition.WILL_UPDATE)
    return dispositions


# ---------------------------------------------------------------------------
# 3. Chung thiện lô đã chỉnh sửa (§6.1 bước 6 đợt 4 — QĐ-F6)
# ---------------------------------------------------------------------------


def finalize_edited_batch(
    events: Sequence[CalendarEvent],
    *,
    edited_actuals: Mapping[str, str],
    fetched_at: str,
) -> FinalizedBatch:
    """Áp chỉnh sửa actual của người dùng lên lô (đợt 4 — chỉ actual được sửa):

    - dòng có ``dedupe_key`` trong ``edited_actuals`` → ``actual`` = giá trị đã
      sửa, stamp ``source=user``, ``raw_json`` GIỮ actual FF gốc (đã có từ lúc
      bóc — không ghi đè), ``dedupe_key`` BẤT BIẾN;
    - dòng không sửa → giữ nguyên (``ff_html``);
    - quan sát lãi suất trong danh mục được dẫn lại từ actual CUỐI cùng
      ``source=ff_html`` (enum §4.4 không có ``user``).

    Khoá của ``edited_actuals`` không khớp sự kiện nào trong lô bị bỏ lặng lẽ
    (UI chỉ gửi khoá của dòng đã hiện trong preview — V2)."""
    edited_keys = set(edited_actuals)
    final_events: list[CalendarEvent] = []
    for event in events:
        if event.dedupe_key in edited_keys:
            actual = str(edited_actuals[event.dedupe_key]).strip() or None
            final_events.append(
                replace(
                    event,
                    actual=actual,
                    source=EventSource.USER,
                )
            )
        else:
            final_events.append(event)
    rates = _rate_observations_from_events(final_events, fetched_at)
    return FinalizedBatch(events=final_events, rates=rates)