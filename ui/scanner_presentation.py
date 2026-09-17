"""Presentation helpers for the scanner UI.

Two responsibilities, both display-only:

* :func:`sort_scanner_rows_for_display` — a pure reorder so that SMC zones
  appear above Technical, which appear above Fallback, while preserving the
  relative backend execution order within each group.
* :func:`present_smc_row` / :func:`present_smc_selection` — render the
  **canonical** SMC verdict of one side (score, selected zone, state and at most
  three reasons) as user language.

**Precondition**: *execution_rows* must already be canonical-sorted by the
backend (``rank_scanner_rows`` / ``sort_scanner_rows``).  The reorder helper only
applies the presentation priority on top; it does **not** compute or alter
execution order.

Display rules locked by the compatibility spec §7 (tasks 121/125):

* The score is called "Điểm SMC" and is **never** a win rate, a probability or a
  percentage.  ``quality_raw`` is an integer on the canonical ``0..15`` scale.
* ``raw = 0`` (evaluated, no eligible setup) and ``raw = null`` (core data
  unavailable) are two different results and never render the same way.
* A confirmed zone that is not ready shows "Chờ xác nhận"/"Theo dõi", never
  "sẵn sàng"; ``READY_NOW`` shows "Đủ điều kiện kiểm tra lần cuối" because
  execution revalidation is still mandatory.
* No version, engine or cache-compatibility label reaches the user.

Every value is read from the canonical selection; this module never scores,
re-selects a zone, rebuilds a confirmation or falls back to legacy fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

# The read boundary owns whether a payload may be presented as the CURRENT
# result (task 128 P0); this module only maps its verdict to display text.
from core.smc_consumer_contract import SMC_READ_CURRENT, SMC_READ_HISTORICAL
from core.scanner_zone_origin import (
    ZONE_ORIGIN_FALLBACK,
    ZONE_ORIGIN_NONE,
    ZONE_ORIGIN_SMC,
    ZONE_ORIGIN_TECHNICAL,
    zone_origin_from_row,
)

# ---------------------------------------------------------------------------
# Presentation priority (UI-only — NOT for canonical / auto-trade ordering)
# ---------------------------------------------------------------------------

PRESENTATION_ZONE_ORIGIN_PRIORITY: dict[str, int] = {
    ZONE_ORIGIN_SMC: 0,
    ZONE_ORIGIN_TECHNICAL: 1,
    ZONE_ORIGIN_FALLBACK: 2,
    ZONE_ORIGIN_NONE: 3,
}


# ---------------------------------------------------------------------------
# Public helper
# ---------------------------------------------------------------------------

def sort_scanner_rows_for_display(
    execution_rows: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Return a new list of display-row copies, stable-sorted by zone origin.

    * Input ``None`` or non-list → ``[]``.
    * Non-dict items are silently dropped (same spirit as the ranking engine).
    * Each row is shallow-copied via ``dict(row)`` so the original
      ``scan_result["rows"]`` is never mutated.
    * Sort is **stable** — relative execution order is preserved within each
      ``zone_origin_class`` group.
    * Does **not** call ``rank_scanner_rows``, ``sort_scanner_rows``, or read
      any private ranking internals.
    """
    if not isinstance(execution_rows, list):
        return []

    display_rows: list[dict[str, Any]] = []
    for row in execution_rows:
        if not isinstance(row, dict):
            continue
        display_rows.append(dict(row))

    display_rows.sort(
        key=lambda row: PRESENTATION_ZONE_ORIGIN_PRIORITY.get(
            zone_origin_from_row(row),
            PRESENTATION_ZONE_ORIGIN_PRIORITY[ZONE_ORIGIN_NONE],
        ),
    )
    return display_rows


# ---------------------------------------------------------------------------
# SMC display vocabulary (tasks 121/125)
# ---------------------------------------------------------------------------

# The score is shown as a bare quality point count, NOT as a probability.
SMC_SCORE_LABEL = "Điểm SMC"
SMC_RAW_MAX = 15
# How many reasons the main screen is allowed to show for one side.
SMC_MAX_REASONS = 3

# Where the presented verdict came from.  ``canonical`` is the only source that
# may be presented as the SMC result of this scan.
SMC_SOURCE_CANONICAL = "canonical"
SMC_SOURCE_HISTORICAL = "historical"
SMC_SOURCE_MISSING = "missing"
# Stored bytes that exist but cannot be certified for the running rules: the
# absence is stated on its own line, never as "no data" (task 128 P0).
SMC_SOURCE_UNUSABLE = "unusable"

# Canonical readiness status → user language (readiness spec §1).
SMC_STATUS_TEXT: dict[str, str] = {
    "READY_NOW": "Đủ điều kiện kiểm tra lần cuối",
    "WAITING_CONFIRMATION": "Chờ xác nhận",
    "WATCH_ZONE": "Theo dõi vùng",
    "OUT_OF_STRATEGY": "Chưa đạt quy tắc",
    "BLOCKED": "Bị chặn",
    "DATA_UNAVAILABLE": "Thiếu dữ liệu",
}

# Canonical selection state → user language, used when the readiness verdict is
# not carried by the payload.
SMC_SELECTION_STATE_TEXT: dict[str, str] = {
    "evaluated": "Đã chọn được vùng",
    "watch_zone": "Theo dõi vùng, chưa có kế hoạch",
    "no_zone": "Chưa có setup hợp lệ",
    "out_of_strategy": "Chưa đạt quy tắc",
    "data_unavailable": "Thiếu dữ liệu",
    "blocked": "Bị chặn",
}

# M15 confirmation status → user language (task 78/125).
SMC_CONFIRMATION_TEXT: dict[str, str] = {
    "confirmed": "Đã có xác nhận vào lệnh",
    "waiting": "Đang chờ xác nhận vào lệnh",
    "zone_not_tested": "Vùng chưa được kiểm tra lại",
    "invalidated": "Xác nhận đã bị vô hiệu",
    "expired": "Xác nhận đã hết hạn",
    "insufficient_data": "Thiếu dữ liệu để xác nhận",
}

# Zone lifecycle → user language.
SMC_LIFECYCLE_TEXT: dict[str, str] = {
    "candidate": "Vùng mới hình thành, chưa dùng được",
    "confirmed": "Vùng đã xác nhận",
    "usable": "Vùng dùng được",
    "watch": "Vùng đang theo dõi",
    "invalid": "Vùng đã bị phá",
    "expired": "Vùng đã hết hạn",
}

# Zone family → user language.
SMC_FAMILY_TEXT: dict[str, str] = {
    "ob": "Order Block",
    "fvg": "FVG",
    "supply_demand": "Cung/Cầu",
}

# Canonical reason codes → user language.  A code that is not listed falls back
# to the shared reason-code table and finally to the code itself, so nothing is
# silently dropped.
SMC_REASON_TEXT: dict[str, str] = {
    "SMC_READY_FOR_REVALIDATION": "Đủ điều kiện để kiểm tra lần cuối trước khi vào lệnh.",
    "SMC_CORE_DATA_UNAVAILABLE": "Thiếu dữ liệu D1/H4/H1 nên chưa kết luận được.",
    "SMC_NO_VALID_SETUP": "Đã xét đủ dữ liệu nhưng không có setup hợp lệ.",
    "SMC_ZONE_PENDING_CONFIRMATION": "Vùng đang chờ xác nhận vào lệnh.",
    "SMC_ZONE_NOT_AVAILABLE_YET": "Vùng chưa sẵn sàng để sử dụng.",
    "SMC_ZONE_INVALID_OR_EXPIRED": "Vùng đã bị phá hoặc hết hạn.",
    "SMC_WAITING_FOR_ZONE_VISIT": "Đang chờ giá quay lại vùng.",
    "SMC_WAITING_REACTION": "Đang chờ phản ứng của giá tại vùng.",
    "TRIGGER_EXPIRED": "Xác nhận vào lệnh đã hết hạn, cần chờ tín hiệu mới.",
    "SMC_COUNTERTREND_UNCONFIRMED": "Vùng ngược xu hướng chưa được xác nhận.",
    "SMC_PLAN_UNAVAILABLE": "Chưa dựng được kế hoạch vào lệnh cho vùng này.",
    "M15_DATA_UNAVAILABLE": "Thiếu dữ liệu M15 nên chưa xác nhận được.",
    "M15_INSUFFICIENT_DATA": "Dữ liệu M15 chưa đủ để xác nhận.",
    "M15_NO_CONFIRMATION": "M15 chưa xác nhận tín hiệu vào lệnh.",
    "M15_CONFIRMATION": "M15 đã xác nhận tín hiệu vào lệnh.",
    "M15_NEW_VISIT": "Giá vừa mở một lần vào vùng mới trên M15, cần chờ xác nhận.",
    "M15_ENTRY_TOO_FAR": "Giá đã đi quá xa vùng vào lệnh, không còn phù hợp để vào lệnh.",
    "M15_RECLAIM_AGAINST": "Giá lấy lại vùng theo hướng ngược, xác nhận bị vô hiệu.",
    "M15_ZONE_NOT_TESTED": "Giá chưa quay lại kiểm tra vùng này trên M15.",
    "SMC_M15_CONFIRMED_PARENT_OPEN": "M15 đã xác nhận nhưng vùng lớn còn đang mở.",
    "SMC_ZONE_HARD_INVALID": "Vùng đã bị vô hiệu hoàn toàn.",
    "SMC_EXTERNAL_GATE_BLOCKED": "Bị cổng bên ngoài chặn.",
    # F-LA-01: the stored summary and the certified result disagree about the
    # protected level, so the level is withheld.  A user must never see the raw
    # code, and must never see a line this message says is missing.
    "SMC_READ_PROTECTED_SWING_MISMATCH": (
        "Mức bảo vệ trong bản đang đọc không khớp với kết quả đã được chứng "
        "nhận, nên không hiển thị mức đó."
    ),
    "QUALITY_RANK": "Được chọn vì chất lượng cao nhất trong các vùng cùng hướng.",
    "NEXT_CANDIDATE_AFTER_REJECT": "Vùng đầu tiên không dựng được kế hoạch, đã xét vùng kế tiếp.",
    "WATCH_NO_PLAN": "Giữ vùng để theo dõi nhưng chưa có kế hoạch vào lệnh.",
}


def smc_reason_text(code: object) -> str:
    """User language for one canonical reason code (never an empty string)."""

    text = str(code or "").strip()
    if not text:
        return ""
    known = SMC_REASON_TEXT.get(text)
    if known:
        return known
    from core.reason_codes import REASON_CODE_MESSAGES

    return REASON_CODE_MESSAGES.get(text, text)


# ---------------------------------------------------------------------------
# Canonical SMC selection lookup (read-only)
# ---------------------------------------------------------------------------

def _as_mapping(value: object) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def smc_selection_from_analysis(analysis: object, side: str) -> Mapping[str, Any] | None:
    """The CURRENT canonical SMC selection of *side* carried by a payload.

    Thin wrapper over :func:`core.smc_consumer_contract.canonical_selection_of`,
    which owns the carrier resolution, the final-invariant check and the
    persisted-document verdict (task 128 P0).  ``None`` means the payload is not
    the current logic's result for this side — no canonical verdict at all, a
    stored payload another identity produced, or unusable bytes.  The legacy
    ``selected_zone``/``smc_quality`` fields are deliberately NOT read: they
    belong to a historical payload and are never presented as the SMC result of
    the current scan.
    """

    from core.smc_consumer_contract import canonical_selection_of

    if not isinstance(analysis, Mapping):
        return None
    return canonical_selection_of(dict(analysis), side)


def read_smc_selection(source: object, side: str):
    """The full read outcome (status + reasons) of one side of a payload.

    ``source`` is a row/document or an analysis result; the boundary decides
    whether it may be presented as current.  Exposed so a caller can tell a
    readable-but-older record from unusable bytes instead of collapsing both.
    """

    from core.smc_consumer_contract import read_canonical_selection

    if not isinstance(source, Mapping):
        return read_canonical_selection(None, side)
    return read_canonical_selection(dict(source), side)


def _carries_legacy_smc(analysis: object, side: str) -> bool:
    """Whether the payload carries SMC evidence in the pre-canonical shape.

    Used only to tell "this row was written before the canonical verdict
    existed" from "this row has no SMC information at all" — never to render a
    legacy score as if it were the current one.

    The ONLY signal that separates the two is the legacy zone/score INSIDE the
    consumer contract side (``selected_zone`` / ``selected_zone_quality_score``):
    the canonical finalizer never fills them.  Two tempting signals were measured
    and rejected because they are present on canonical payloads too — the legacy
    zone dump under ``analysis["smc"]`` and the ``scenario_scores`` projection
    (both are still produced next to the canonical result), so neither says
    anything about the payload's age.
    """

    payload = _as_mapping(analysis)
    if payload is None:
        return False
    consumer = _as_mapping(payload.get("smc_consumer"))
    if consumer is None:
        return False
    sides = _as_mapping(consumer.get("sides"))
    item = _as_mapping(sides.get(side)) if sides is not None else None
    if item is None:
        return False
    return (
        _as_mapping(item.get("selected_zone")) is not None
        or item.get("selected_zone_quality_score") is not None
    )


# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class SmcPresentation:
    """One side's SMC verdict, ready to render (never a probability)."""

    side: str
    source: str
    available: bool
    score_text: str
    score_raw: int | None
    state_text: str
    zone_text: str
    reasons: tuple[str, ...] = ()
    selection_state: str = ""
    readiness_status: str = ""
    confirmation_text: str = ""
    # The technical codes behind a non-canonical read (task 128 P0): kept for
    # traceability in the detail panel, never shown as a user sentence.
    read_reason_codes: tuple[str, ...] = ()
    confirmation: Mapping[str, Any] | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "source": self.source,
            "available": self.available,
            "score_text": self.score_text,
            "score_raw": self.score_raw,
            "state_text": self.state_text,
            "zone_text": self.zone_text,
            "reasons": list(self.reasons),
            "selection_state": self.selection_state,
            "readiness_status": self.readiness_status,
            "confirmation_text": self.confirmation_text,
            "read_reason_codes": list(self.read_reason_codes),
        }

    def tooltip_text(self) -> str:
        """The same verdict as plain lines (main-screen hover)."""

        lines = [f"{SMC_SCORE_LABEL}: {self.score_text}"]
        if self.zone_text:
            lines.append(f"Vùng: {self.zone_text}")
        lines.append(f"Trạng thái: {self.state_text}")
        if self.confirmation_text:
            lines.append(f"Xác nhận: {self.confirmation_text}")
        for reason in self.reasons:
            lines.append(f"· {reason}")
        return "\n".join(lines)


def _score_text(selection: Mapping[str, Any]) -> str:
    """``raw/15``, or the two distinct "no result" texts (0 vs null)."""

    raw = selection.get("quality_raw")
    if raw is None:
        # ``state`` separates a legitimate data gap from a malformed payload.
        return "Thiếu dữ liệu"
    if isinstance(raw, bool) or not isinstance(raw, int):
        return "Thiếu dữ liệu"
    if raw == 0:
        return f"0/{SMC_RAW_MAX} · chưa có setup hợp lệ"
    return f"{raw}/{SMC_RAW_MAX}"


def _zone_text(selection: Mapping[str, Any]) -> str:
    """``timeframe · family · low–high`` of the SELECTED candidate, or ``""``."""

    parts: list[str] = []
    timeframe = str(selection.get("timeframe") or "").strip()
    if timeframe:
        parts.append(timeframe)
    family = SMC_FAMILY_TEXT.get(str(selection.get("family") or "").strip().lower())
    if family:
        parts.append(family)
    low = selection.get("zone_low")
    high = selection.get("zone_high")
    if _is_price(low) and _is_price(high) and float(high) > float(low):
        parts.append(f"{float(low):.5f} – {float(high):.5f}")
    return " · ".join(parts)


def _is_price(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _effective_confirmation_status(selection: Mapping[str, Any]) -> str:
    """The confirmation status of this selection, from its strongest evidence.

    The typed M15 record is the evidence task 117 stores verbatim, so when the
    payload carries one its ``status`` is the answer.  The readiness projection
    (``m15_status``) is read only when no record is present — it is a separate
    vocabulary and must not overrule the record it projects.
    """

    record = _as_mapping(selection.get("confirmation"))
    if record is not None:
        status = str(record.get("status") or "").strip().lower()
        if status:
            return status
    return str(selection.get("m15_status") or "").strip().lower()


def _state_text(selection: Mapping[str, Any]) -> str:
    """The most specific canonical state sentence for this side."""

    readiness = str(selection.get("readiness_status") or "").strip().upper()
    confirmation = _effective_confirmation_status(selection)
    lifecycle = str(selection.get("lifecycle_status") or "").strip().lower()
    smc_state = str(selection.get("smc_state") or "").strip().upper()

    # A broken/expired zone describes the result better than "waiting".
    if lifecycle in ("invalid", "expired"):
        return SMC_LIFECYCLE_TEXT[lifecycle]
    if confirmation in ("invalidated", "expired"):
        return SMC_CONFIRMATION_TEXT[confirmation]
    # An evaluated side with nothing to trade is not "watching a zone": the
    # canonical SMC state says there is no candidate at all.
    if smc_state == "NO_ZONE":
        return SMC_SELECTION_STATE_TEXT["no_zone"]
    if readiness:
        return SMC_STATUS_TEXT.get(readiness, readiness)
    state = str(selection.get("state") or "").strip().lower()
    return SMC_SELECTION_STATE_TEXT.get(state, state or "Chưa xác định")


def _confirmation_text(selection: Mapping[str, Any]) -> str:
    return SMC_CONFIRMATION_TEXT.get(_effective_confirmation_status(selection), "")


def smc_reason_texts(selection: Mapping[str, Any], limit: int | None = None) -> tuple[str, ...]:
    """User-language reasons of one selection, order preserved and deduplicated.

    The typed confirmation's own reason codes come first when the payload carries
    a record: they explain the most specific state (why a confirmation was
    invalidated, expired or is still waiting), and the readiness/selection codes
    follow as the wider verdict.  ``limit`` caps how many are returned (the main
    screen shows at most :data:`SMC_MAX_REASONS`; the detail panel may ask for
    all of them).
    """

    codes: list[object] = []
    record = _as_mapping(selection.get("confirmation"))
    if record is not None and isinstance(record.get("reason_codes"), (list, tuple)):
        codes.extend(record["reason_codes"])
    for key in ("readiness_reason_codes", "selection_reason_codes"):
        values = selection.get(key)
        if isinstance(values, (list, tuple)):
            codes.extend(values)
    texts: list[str] = []
    for code in codes:
        text = smc_reason_text(code)
        if text and text not in texts:
            texts.append(text)
        if limit is not None and len(texts) >= limit:
            break
    return tuple(texts)


def present_smc_selection(
    selection: object,
    *,
    side: str = "",
    source: str = SMC_SOURCE_CANONICAL,
    max_reasons: int | None = SMC_MAX_REASONS,
    read_reason_codes: tuple[str, ...] = (),
) -> SmcPresentation:
    """Render one canonical SMC selection (read-only)."""

    payload = _as_mapping(selection)
    if payload is None:
        if source == SMC_SOURCE_UNUSABLE:
            return SmcPresentation(
                side=side,
                source=source,
                available=False,
                score_text="Không đọc được kết quả SMC đã lưu",
                score_raw=None,
                state_text=(
                    "Kết quả SMC lưu cho lần quét này không còn hợp lệ với quy "
                    "tắc đang chạy; cần quét lại trước khi dùng."
                ),
                zone_text="",
                read_reason_codes=tuple(read_reason_codes),
            )
        return SmcPresentation(
            side=side,
            source=source,
            available=False,
            # "Chưa có dữ liệu SMC" is NOT the same as an evaluated zero.
            score_text="Chưa có dữ liệu SMC",
            score_raw=None,
            state_text="Chưa có dữ liệu SMC",
            zone_text="",
            read_reason_codes=tuple(read_reason_codes),
        )
    raw = payload.get("quality_raw")
    return SmcPresentation(
        side=str(payload.get("side") or side),
        source=source,
        available=True,
        score_text=_score_text(payload),
        score_raw=raw if isinstance(raw, int) and not isinstance(raw, bool) else None,
        state_text=_state_text(payload),
        zone_text=_zone_text(payload),
        reasons=smc_reason_texts(payload, max_reasons),
        selection_state=str(payload.get("state") or ""),
        readiness_status=str(payload.get("readiness_status") or ""),
        confirmation_text=_confirmation_text(payload),
        confirmation=_as_mapping(payload.get("confirmation")),
    )


def present_smc_row(
    row: object,
    side: str | None = None,
    *,
    max_reasons: int | None = SMC_MAX_REASONS,
) -> SmcPresentation:
    """Present the canonical SMC verdict of one Scanner row.

    ``side`` defaults to the row's selected side.  Four outcomes, from the shared
    read boundary:

    * ``canonical`` — the selection is current and is presented;
    * ``historical`` — no current verdict, only pre-canonical SMC evidence, or a
      stored payload another identity produced: shown as a record of its time,
      never as the current result of the scan;
    * ``unusable`` — stored bytes exist but cannot be certified for the running
      rules: the absence is stated as such;
    * ``missing`` — the row carries no SMC information at all.

    The side is respected when the row names one: the verdict presented is that
    side's, never the other side's.  Only a row without a selected side (no
    decision yet) falls back to whichever side carries a verdict, and then the
    presentation reports the side it actually read.
    """

    payload = _as_mapping(row)
    if payload is None:
        return present_smc_selection(None, max_reasons=max_reasons)
    analysis = _as_mapping(payload.get("analysis_result"))
    chosen = str(side or payload.get("selected_side") or "").strip().lower()
    if chosen not in ("buy", "sell"):
        chosen = ""

    # The verdict is read from the payload the UI was handed — a row, a stored
    # document, or an analysis result already unwrapped out of one (task 128
    # follow-up: unwrapping must not bypass the gate).  The boundary splits the
    # shapes itself, and a payload carrying the Scanner carrier without the
    # canonical block is refused there instead of being read as live.
    source = payload
    if analysis is None:
        analysis = payload

    worst: Mapping[str, Any] | None = None
    for candidate_side in ([chosen] if chosen else ["buy", "sell"]):
        read = read_smc_selection(source, candidate_side)
        if read.is_current:
            return present_smc_selection(
                read.selection, side=candidate_side, max_reasons=max_reasons
            )
        if worst is None or read.status == SMC_READ_HISTORICAL:
            worst = read

    if worst is not None and worst.status == SMC_READ_HISTORICAL:
        return SmcPresentation(
            side=chosen or worst.side,
            source=SMC_SOURCE_HISTORICAL,
            available=False,
            score_text="Kết quả lưu theo định dạng cũ",
            score_raw=None,
            state_text=(
                "Dòng này được lưu trước khi có kết quả SMC hiện hành; "
                "chỉ xem lại lịch sử, không dùng để vào lệnh."
            ),
            zone_text="",
            read_reason_codes=worst.reason_codes,
        )

    if chosen and _carries_legacy_smc(analysis, chosen):
        return SmcPresentation(
            side=chosen,
            source=SMC_SOURCE_HISTORICAL,
            available=False,
            score_text="Kết quả lưu theo định dạng cũ",
            score_raw=None,
            state_text=(
                "Dòng này được lưu trước khi có kết quả SMC hiện hành; "
                "chỉ xem lại lịch sử, không dùng để vào lệnh."
            ),
            zone_text="",
            read_reason_codes=worst.reason_codes if worst is not None else (),
        )

    if _is_stored_document(source):
        # Stored bytes that cannot be certified: said as such, not as "no data".
        return SmcPresentation(
            side=chosen,
            source=SMC_SOURCE_UNUSABLE,
            available=False,
            score_text="Không đọc được kết quả SMC đã lưu",
            score_raw=None,
            state_text=(
                "Kết quả SMC lưu cho lần quét này không còn hợp lệ với quy tắc "
                "đang chạy; cần quét lại trước khi dùng."
            ),
            zone_text="",
            read_reason_codes=worst.reason_codes if worst is not None else (),
        )
    return present_smc_selection(
        None,
        side=chosen,
        source=SMC_SOURCE_MISSING,
        max_reasons=max_reasons,
        read_reason_codes=worst.reason_codes if worst is not None else (),
    )


def _is_stored_document(source: object) -> bool:
    """Whether the payload came off disk (it carries the writer's envelope)."""

    payload = _as_mapping(source)
    return payload is not None and "observability_version" in payload


# ---------------------------------------------------------------------------
# Chart overlay labels (task 124/126)
# ---------------------------------------------------------------------------
#
# The chart draws the canonical layer built by ``core.chart_payload``.  The
# canonical payload carries codes (not sentences), so the SAME vocabulary used
# by the text panels is applied here before the payload reaches the page: the
# chart's caption and the detail screen then say the same thing about the same
# canonical source.

SMC_ZONE_STATUS_TEXT: dict[str, str] = {
    "selected": "Vùng đã chọn",
    "watch": "Vùng đang theo dõi",
    "invalid": "Vùng không còn hiệu lực",
}

# M15 trigger kinds → user language.
SMC_TRIGGER_KIND_TEXT: dict[str, str] = {
    "micro_break": "Phá cấu trúc nhỏ kèm nến đẩy ra khỏi vùng",
    "rejection": "Giá từ chối tại vùng kèm nến tiếp diễn",
}

SMC_OVERLAY_ABSENT_TEXT = "Chưa có kết quả SMC cho khung này"


def smc_zone_status_text(status: object) -> str:
    """User language for one canonical chart zone status."""

    key = str(status or "").strip().lower()
    return SMC_ZONE_STATUS_TEXT.get(key, SMC_OVERLAY_ABSENT_TEXT)


def smc_lifecycle_text(lifecycle: object) -> str:
    """User language for one canonical zone lifecycle status (``""`` if none)."""

    key = str(lifecycle or "").strip().lower()
    if not key:
        return ""
    return SMC_LIFECYCLE_TEXT.get(key, key)


def smc_trigger_kind_text(kind: object) -> str:
    """User language for one canonical M15 trigger kind (``""`` if none)."""

    key = str(kind or "").strip().lower()
    if not key:
        return ""
    return SMC_TRIGGER_KIND_TEXT.get(key, key)


def smc_overlay_caption(layer: Mapping[str, Any] | None) -> str:
    """One caption for a timeframe of the canonical overlay.

    It names the side and the state of the zone drawn on this timeframe, in the
    same words the detail screen uses.
    """

    payload = _as_mapping(layer)
    if payload is None:
        return SMC_OVERLAY_ABSENT_TEXT
    zones = payload.get("zones")
    if not isinstance(zones, (list, tuple)) or not zones:
        return SMC_OVERLAY_ABSENT_TEXT
    parts: list[str] = []
    for zone in zones:
        item = _as_mapping(zone)
        if item is None:
            continue
        side = {"buy": "MUA", "sell": "BÁN"}.get(
            str(item.get("side") or "").strip().lower(), ""
        )
        status = smc_zone_status_text(item.get("status"))
        parts.append(f"{side} · {status}" if side else status)
    return "SMC: " + " | ".join(parts) if parts else SMC_OVERLAY_ABSENT_TEXT


def present_smc_overlay(overlay: object) -> dict[str, Any]:
    """Attach display labels to a canonical overlay, per timeframe.

    Returns a NEW mapping (the canonical payload is never mutated): each
    timeframe layer gets ``caption`` plus a ``label`` on every zone, trigger and
    protected swing, and the read verdict of the payload is carried through so
    the report and the tests can state WHY nothing was drawn (task 128 P0).
    Nothing is recomputed — only text is added.
    """

    payload = _as_mapping(overlay)
    source = _as_mapping(payload) if payload is not None else None
    timeframes_raw = source.get("timeframes") if source is not None else None
    timeframes: dict[str, Any] = {}
    if isinstance(timeframes_raw, Mapping):
        for timeframe, layer in timeframes_raw.items():
            item = _as_mapping(layer)
            if item is None:
                continue
            zones = []
            for zone in item.get("zones") or ():
                zone_map = _as_mapping(zone)
                if zone_map is None:
                    continue
                enriched = dict(zone_map)
                enriched["label"] = smc_zone_status_text(zone_map.get("status"))
                zones.append(enriched)
            trigger = _as_mapping(item.get("trigger"))
            protected = _as_mapping(item.get("protected_swing"))
            timeframes[str(timeframe)] = {
                **dict(item),
                "zones": zones,
                "caption": smc_overlay_caption({**dict(item), "zones": zones}),
                "trigger": (
                    {**dict(trigger), "label": "Xác nhận M15"} if trigger else None
                ),
                "protected_swing": (
                    {**dict(protected), "label": "Đỉnh/đáy bảo vệ"}
                    if protected
                    else None
                ),
            }
    read_status = (
        str(source.get("read_status") or SMC_READ_CURRENT) if source else SMC_READ_CURRENT
    )
    reason_codes = (
        [str(code) for code in source.get("reason_codes") or ()] if source else []
    )
    sides = (
        {str(side): dict(read) for side, read in (source.get("sides") or {}).items()}
        if source and isinstance(source.get("sides"), Mapping)
        else {}
    )
    return {
        "available": bool(source.get("available")) if source else False,
        "source": str(source.get("source") or SMC_SOURCE_MISSING) if source else SMC_SOURCE_MISSING,
        # The verdict travels with the labels: the caption says what was drawn,
        # this says whether the payload was even allowed to be drawn.
        "read_status": read_status,
        "reason_codes": reason_codes,
        "sides": sides,
        "timeframes": timeframes,
    }
