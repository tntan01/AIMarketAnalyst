"""NewsController — the thin orchestration layer of the News domain (plan batch L2.7).

Owner of "tiếp nhận và xác thực tin người dùng nhập" (contract §6.4 / §11b) and
the orchestrator registered in the contract §3 layer table: it schedules the
producers per policy, serves queries to consumers, accepts manual entries and
coordinates the AI call inside a worker (contract §9.1).

This module **delegates**.  It owns no formula, no status classification, no
trend derivation and no display string (C3/S2, L1/L3): every read and write goes
to ``NewsRepository`` (the single access point, §8), the values crossing its
boundary are the typed models of ``core/news_models.py``, and every operational
number comes from the policy via ``core/news_policy.load_news_policy`` (R4).

**Đợt 3 (24/09/2026 — ca "Nguồn dán FF", plan F1):** tất cả đường ForexFactory
tự động và xuất/nhập file đã bị BỎ khỏi controller này: hai lượt fetch nút của
đường thu cũ (kênh lịch JSON và kênh actual HTML), seam on-demand lookup (kênh
của producer lịch cũ cắm vào repository) và delegate một-sự-kiện kèm lookup,
và hai lượt đối ngoại của đường xuất/nhập file (contract §13 / §10 đợt 3 — "Bỏ
thu tự động FF; app không phát request mạng nào tới ForexFactory" + "Bãi bỏ
xuất/nhập file"; sao lưu = tệp ``news.db``).  Kênh duy nhất của lịch kinh tế +
actual là **mã nguồn trang người dùng dán**, tiếp nhận tại lô F3 qua luồng 2
pha ``parse_pasted_source`` (pha 1 — bóc tách + xem trước, không ghi) và
``commit_pasted_source`` (pha 2 — xác nhận, ghi qua repository), contract §6.1
đợt 3+4.  ``run_startup_turn`` chỉ còn purge retention + khởi động lịch
producer RSS/FRED (L3.6/L3.7 giữ nguyên — QĐ-F2).

Delivered by this batch (plan L2.7):

* **Producer schedule per policy** — ``poll_news`` runs one ``rss_producer``
  round (cadence key ``rss_poll_interval_minutes``) and ``refresh_rates`` one
  ``fred_rate_producer`` round (cadence read from that producer's
  ``refresh_hours``, i.e. the ``fred_refresh_hours`` key).  Both cadences are
  exposed for the timer owner, ``workers/news_worker.py``.
* **Manual entry** (§6.4) — ``add_user_note`` validates the four mandatory form
  fields (publish time, kind, content, currency) and writes **nothing** when one
  of them is missing or unusable; otherwise it upserts
  ``NewsItem(kind=user_note, source=user)`` and logs the turn's ``ingest_runs``
  row (producer ``user`` — §3 lists the manual form in the producer column and
  §10 gives every producer turn a run row).
* **Exclusion / deletion** (§6.4) — ``set_excluded`` applies to any item (it is
  the only write path that keeps an automatic item's provenance) while
  ``delete_user_note`` exists for manual notes only; the kind guard itself stays
  in the repository.

**App-startup turn (plan L3.6):** ``run_startup_turn`` implements QĐ-F2 — one
turn per session, no FF channel of any kind: it purges expired ``ingest_runs``
(retention from the policy key, §4.6) and starts the periodic RSS/FRED rounds
(plan L3.7); the ``_fetched_this_session`` session flag (khuôn
``_auto_scanned_this_session`` của Scanner) makes repeated calls typed no-ops so
the boot hook in ``main.py`` never purges/starts twice.  ``StartupTurnResult``
carries only ``ran`` + ``purged_runs`` (the retired json/html fields were
removed with the FF channels).

**Producer schedule (plan L3.7):** contract §6.2/§6.3/§13 keep both RSS and FRED
"tự động định kỳ".  ``NewsController`` takes an optional ``schedule_starter``
seam (injected in tests; ``None`` resolves to the real starter, which builds a
``QThread`` + ``NewsWorker`` per the caller khuôn in ``workers/news_worker.py``
and imports PyQt/``NewsWorker`` at function level to avoid the ``news_worker ↔
news_controller`` import cycle).  The startup-turn session guard starts it
exactly once; ``stop_producer_schedule`` (wired to ``aboutToQuit`` at start
time, QĐ-7) stops the timers via a queued call on the worker's own thread and
joins the thread with a bounded wait.  No immediate RSS/FRED round at boot —
the contract only asks for periodics, the first round fires at the end of the
first cadence (V2).

**AI trend judgement (plan L3.5):** ``ai_scope_preview``/``analyze_trend``
implement contract §9.1 in the controller — read the repo (calendar events +
text items touching the scope's currencies, ``excluded=0``, inside
``ai_window_days``) → floor check via ``core/trend_prompt_builder`` (below
``ai_min_items`` no prompt exists and no AI call is made, B4) → build the
prompt → ``AIService.analyze`` inside the dialog's worker → parse via
``core/trend_verdict_parser`` → one retry on the parser's ``retryable`` signal
→ on final failure a friendly message and nothing stored → compose the three
``TrendVerdict`` rows (``input_snapshot`` = prompt snapshot, ``prompt_hash``,
provider/model provenance) and store via ``add_verdicts`` (§8).  The parser
never retries and never builds messages; ``friendly_error()``-translated
provider exceptions surface as-is (the adapters translate at raise time).
``verdicts_for`` is now delegated (the news screen is the *only* allowed
consumer of verdict history, §9.2).  The AI service and the settings provider
are constructor seams (khuôn d.275-282); the production default resolves
``settings.ai.active_provider()`` lazily exactly like ``scanner_controller``
(d.720-728).

**Pasted page-source channel (đợt 3+4, 24/09/2026 — ca "Nguồn dán FF", plan
F3, contract §6.1):** the only channel of calendar events + actual is the
user-pasted ForexFactory page source.  ``parse_pasted_source`` implements pha 1
(§6.1 bước 2 + 5): it hands the raw text to the sole parser owner
``services/ff_source_parser`` (this layer never self-extracts — S2), reads the
existing rows through ``events_in_range`` (window = the batch's min→max
``event_time_utc``, §8 — no repository method is added) and classifies each
row via the parser's pure ``classify_incoming_events`` (`Mới` / `Sẽ cập nhật`
/ `Xung đột — giữ nhập tay`).  **Pha 1 writes nothing** — no
``upsert_events``/``add_rate_observations``, no ``ok`` run; a parse error
returns a typed preview error and logs one ``failed`` run (§4.6/§6.1 — lỗi có
kiểu).  ``commit_pasted_source`` implements pha 2 (§6.1 bước 6 đợt 4): it
receives the preview plus the actuals the user edited (only ``actual`` may
differ from the parsed value — QĐ-F6), calls the parser's pure
``finalize_edited_batch`` (edited rows → ``source=user`` + the original FF
actual kept in ``raw_json``; untouched rows keep ``ff_html``; rate observations
in the inherited list resync to the edited actual with ``ff_html`` source;
``dedupe_key`` immutable), then writes through the repository:
``upsert_events`` + ``add_rate_observations`` (the 3 merge rules stay in the
repository, never copied here) + ``record_run`` (producer ``user``,
``items_written`` = events + rates) and returns the REAL new/updated/conflict
counts from ``UpsertEventsResult`` plus the rate count; rule-3 conflicts are
logged into the run's ``error_type``/``error_detail`` (``ActualConflict`` —
khuôn the retired ``ff_calendar_producer``).  Cancel = the UI never calls
``commit_pasted_source`` → nothing written, no run, edits discarded (§6.1).

Declared readings (V2 — decided here on purpose, not silently):

* §6.4 makes the form supply "loại tin" while the write in the same sentence
  fixes ``kind=user_note``.  The manual path therefore *validates* that a kind
  was supplied **and** that it is the manual kind: an automatic kind
  (``headline``/``statement``) is rejected rather than silently rewritten.
* The form has no title field (§6.4 and screen_design "Hành vi nhập/sửa tin")
  while ``news_items.title`` is NOT NULL (§4.3) and ``content`` is mandatory for
  a ``user_note`` (§4.3/§6.4): the one required text field is stored as both
  ``title`` and ``content`` — a manual note's text is its own headline.
* ``set_excluded`` carries no kind guard: §6.4 allows an automatic item to be
  excluded, and only *deletion* is restricted to manual notes.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from core.news_models import (
    CalendarEvent,
    ImpactHint,
    IngestProducer,
    IngestRun,
    IngestRunStatus,
    NewsItem,
    NewsItemKind,
    NewsItemSource,
    RateObservation,
    StoreState,
    TrendVerdict,
    VerdictScopeType,
    news_item_dedupe_key,
)
from core.news_policy import NewsPolicy, load_news_policy
from core.trend_prompt_builder import TrendPrompt, TrendPromptOutcome, build_trend_prompt
from core.trend_verdict_parser import TrendParseOutcome, parse_trend_verdict
from services.ai_service import AIProviderConfig, AIService
from services.ff_source_parser import (
    ParseError,
    RowDisposition,
    classify_incoming_events,
    finalize_edited_batch,
    parse_calendar_source,
)
from services.news_producers.fred_rate_producer import FredRateProducer, RateFetchResult
from services.news_producers.rss_producer import RssCollectionResult, RssProducer
from services.news_repository import (
    ActualConflict,
    CurrencyRateTrend,
    NewsRepository,
    UpsertEventsResult,
    UpsertItemsResult,
)

__all__ = [
    "AiScopePreview",
    "NewsController",
    "SourceIngestResult",
    "SourcePreview",
    "StartupTurnResult",
    "TrendAnalysisResult",
    "UserNoteFieldError",
    "UserNoteResult",
]


# ---------------------------------------------------------------------------
# Typed results of the manual-entry path (C3 — no bare dict across the boundary)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UserNoteFieldError:
    """One rejected form field of a manual entry (§6.4).

    Machine-readable pair: ``field`` is the form field name and ``reason`` the
    finding (``missing``/``not_manual_note``/``invalid_timestamp``/
    ``invalid_currency``/``invalid_impact_hint``).  Vietnamese labels shown to
    the user are the screen's job (L3 — no display string here)."""

    field: str
    reason: str


@dataclass(frozen=True, slots=True)
class UserNoteResult:
    """Typed outcome of ``add_user_note`` (§6.4).

    ``errors`` is empty exactly when the note was written; a rejected draft
    carries its field errors and **nothing** was written — no item and no run
    row (screen_design: "thiếu trường bắt buộc → báo lỗi ngay trên form, không
    ghi DB").  ``inserted``/``updated`` come straight from the repository's
    ``UpsertItemsResult`` (a repeated identical note updates its row instead of
    duplicating it — the §4.3 ``dedupe_key`` does that, not this layer) and
    ``run_id`` is the ``ingest_runs`` row of the manual turn."""

    errors: tuple[UserNoteFieldError, ...]
    inserted: int = 0
    updated: int = 0
    run_id: int | None = None

    @property
    def ok(self) -> bool:
        """True when the note passed validation and was written."""
        return not self.errors


# ---------------------------------------------------------------------------
# Typed results of the AI trend path (plan L3.5 — C3, no bare dict)
# ---------------------------------------------------------------------------

# Friendly messages of the AI path (repo strings — khuôn scanner):
#  - "Chưa cấu hình AI Provider hoặc API key trong Settings." scanner_controller d.2943
#  - "AI không trả về JSON hợp lệ."                       scanner_detail_screen d.2881
NO_AI_CONFIG_TEXT = "Chưa cấu hình AI Provider hoặc API key trong Settings."
PARSE_FAIL_TEXT = "AI không trả về JSON hợp lệ."


@dataclass(frozen=True, slots=True)
class AiScopePreview:
    """§9.1 step 2 — the data counts of one scope, WITHOUT calling the AI.

    The dialog shows the count line before judging ("Cửa sổ tin: <ai_window_days>
    ngày gần nhất — <N> tin/sự kiện liên quan", screen_design d.1629) and only
    then offers the judge button; ``insufficient`` (below ``ai_min_items``) is
    fail-closed — no prompt exists, so the AI is never called (B4)."""

    scope_type: str
    scope_value: str
    window_days: int
    event_count: int
    item_count: int
    min_items: int

    @property
    def insufficient(self) -> bool:
        """True when the considered rows are below ``ai_min_items``."""
        return self.event_count + self.item_count < self.min_items


@dataclass(frozen=True, slots=True)
class TrendAnalysisResult:
    """Typed outcome of one ``analyze_trend`` run (§9.1 steps 2-6, C3).

    ``ok`` holds exactly when the three verdict rows were composed and stored
    (``inserted`` from the repository's typed count); ``insufficient`` is the
    fail-closed report (no AI call); ``verdicts`` carries the composed rows for
    the dialog to render; ``error_message`` is the friendly text (never a bare
    parser detail) when the run failed — and in every failure case nothing was
    stored (§9.1: "không lưu verdict rác")."""

    ok: bool
    verdicts: tuple[TrendVerdict, ...] = ()
    inserted: int = 0
    insufficient: bool = False
    event_count: int = 0
    item_count: int = 0
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Typed result of the app-startup turn (plan L3.6 — C3, no bare dict)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StartupTurnResult:
    """Typed outcome of the app-startup turn (plan L3.6, QĐ-F2 — đợt 3, 24/09/2026).

    ``ran`` is False when the turn was skipped because this session already
    ran it (the ``_fetched_this_session`` guard — exactly one turn per session).
    When it ran: ``purged_runs`` is the number of expired ``ingest_runs`` rows
    the retention policy removed (contract §4.6 — only the operational log;
    news and verdicts are never touched) and the RSS/FRED producer schedule is
    started exactly once (plan L3.7).  The two ForexFactory channel results of
    the old turn were removed with the FF channels (đợt 3 — no FF request of
    any kind remains)."""

    ran: bool
    purged_runs: int = 0


# ---------------------------------------------------------------------------
# Typed results of the pasted page-source path (plan F3 — C3, no bare dict)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SourcePreview:
    """Kết quả có kiểu của ``parse_pasted_source`` — pha 1 (§6.1 bước 2 + 5 đợt 4).

    ``error`` None đúng khi lô dán bóc được trọn vẹn (``events``/``rates`` đầy
    đủ và ``dispositions`` phân loại từng dòng cùng thứ tự); khi parse lỗi thì
    cả ba rỗng và ``error`` mang lỗi có kiểu của parser (không bảng — L3).
    ``fetched_at`` là mốc thời gian của lượt bóc (parser không tự bịa mốc — do
    caller F3 cấp), giữ lại để pha 2 ghi đúng cùng provenance khi chung thiện
    lô."""

    events: list[CalendarEvent]
    rates: list[RateObservation]
    dispositions: tuple[RowDisposition, ...]
    error: ParseError | None
    fetched_at: str


@dataclass(frozen=True, slots=True)
class SourceIngestResult:
    """Kết quả có kiểu của ``commit_pasted_source`` — pha 2 (§6.1 bước 6 đợt 4).

    ``inserted``/``updated``/``conflicts`` là số **THẬT** từ ``UpsertEventsResult``
    của lần ghi (không dùng số dự đoán của preview); ``rates_written`` là số
    quan sát lãi suất đã ghi; ``run_id`` là dòng ``ingest_runs`` của lượt dán
    (producer ``user``, status ``ok``).  Xung đột quy tắc 3 cũng nằm trong
    ``error_type``/``error_detail`` của run (``ActualConflict``)."""

    inserted: int
    updated: int
    conflicts: tuple[ActualConflict, ...]
    rates_written: int
    run_id: int


# ---------------------------------------------------------------------------
# Manual-entry helpers (pure — validation only, no I/O)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Draft:
    """The validated payload of one manual entry (internal to this module)."""

    published_utc: str
    content: str
    currencies: list[str]
    url: str | None
    impact_hint: ImpactHint | None


def _validate_user_note(
    *,
    kind: object,
    published_utc: object,
    content: object,
    currencies: object,
    url: object,
    impact_hint: object,
) -> tuple[_Draft | None, tuple[UserNoteFieldError, ...]]:
    """Validate one manual-entry draft (§6.4) — pure, no repository call.

    The four mandatory fields are the four the form must supply.  Every finding
    is collected (the form shows them together), and a draft with any finding is
    never written."""
    errors: list[UserNoteFieldError] = []

    kind_value = str(kind or "").strip()
    if not kind_value:
        errors.append(UserNoteFieldError("kind", "missing"))
    elif kind_value != NewsItemKind.USER_NOTE.value:
        errors.append(UserNoteFieldError("kind", "not_manual_note"))

    text = str(content or "").strip()
    if not text:
        errors.append(UserNoteFieldError("content", "missing"))

    published = _normalize_published_utc(published_utc) or ""
    if not published:
        # Rỗng và không đọc được là hai nhánh lỗi khác nhau của form (§6.4).
        reason = "missing" if not str(published_utc or "").strip() else "invalid_timestamp"
        errors.append(UserNoteFieldError("published_utc", reason))

    codes: list[str] = _normalize_currencies(currencies) or []
    if not codes:
        reason = "missing" if currencies is None else "invalid_currency"
        errors.append(UserNoteFieldError("currencies", reason))

    hint: ImpactHint | None = None
    hint_value = str(impact_hint or "").strip()
    if hint_value:
        try:
            hint = ImpactHint(hint_value)
        except ValueError:
            errors.append(UserNoteFieldError("impact_hint", "invalid_impact_hint"))

    if errors:
        return None, tuple(errors)
    return (
        _Draft(
            published_utc=published,
            content=text,
            currencies=codes,
            url=str(url or "").strip() or None,
            impact_hint=hint,
        ),
        (),
    )


def _normalize_published_utc(value: object) -> str | None:
    """Normalize a publish moment to the ISO-8601 UTC khuôn every producer
    writes (``YYYY-MM-DDTHH:MM:SSZ``) — ``published_utc`` is stored and compared
    as a string (§4.1/§4.3), so the form's moment must land in that khuôn.  A
    ``datetime`` (what a Qt widget hands over) or an ISO string is accepted; a
    naive value is read as UTC (khuôn ``parse_event_time``/``parse_rss_time``)."""
    if isinstance(value, datetime):
        moment = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    text = str(value or "").strip()
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalize_currencies(value: object) -> list[str] | None:
    """Read the currency list of the form: ``None`` when nothing was supplied at
    all, otherwise the stripped non-empty codes in order — an empty list means
    the field carried no usable code (a bare string is not accepted as one code,
    it is not a list of codes).  Codes are NOT re-cased: the domain vocabulary is
    the caller's (screen pickers use the §4.3 codes)."""
    if value is None:
        return None
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return []
    return [str(code).strip() for code in value if str(code).strip()]


def _utc_now() -> str:
    """Current UTC time in the khuôn ISO-8601 form: ``YYYY-MM-DDTHH:MM:SSZ``."""
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _conflicts_detail(conflicts: tuple[ActualConflict, ...]) -> str:
    """Compact machine-readable summary of rule-3 conflicts (contract §6.1 quy
    tắc 3 — user actual wins and the conflict is written into ``ingest_runs``).

    Khuôn của bộ sản xuất lịch cũ ``ff_calendar_producer`` (đã xóa ở F1) —
    chuỗi máy đọc cho log vận hành, không phải chuỗi hiển thị (L3)."""
    return "; ".join(
        f"{c.dedupe_key}|{c.currency}|{c.title}|user={c.user_actual}|auto={c.incoming_actual}"
        for c in conflicts
    )


def _run_error_fields(
    conflicts: tuple[ActualConflict, ...],
) -> tuple[str | None, str | None]:
    """Map rule-3 conflicts onto the ``ingest_runs`` error fields (§4.6/§6.1).

    Quy tắc merge 3 nằm trong ``NewsRepository`` — controller chỉ chuyển tiếp
    ``UpsertEventsResult.conflicts`` do repository báo về, không bao giờ tự
    suy diễn lại (L2.1).  Không xung đột → run không có lỗi."""
    if not conflicts:
        return None, None
    return "ActualConflict", _conflicts_detail(conflicts)


def _fred_api_key() -> str | None:
    """The FRED key from the current settings — the same single source
    ``news_service`` and ``interest_rate_service`` use
    (``settings.advanced.fred_api_key``).  An unreadable/absent key yields
    ``None``, which makes the FRED channel skip itself (inherited behavior,
    batch L2.6)."""
    try:
        from services.settings_service import SettingsService

        return getattr(SettingsService().load().advanced, "fred_api_key", "") or None
    except Exception:
        return None


def _read_active_ai_provider() -> object | None:
    """The settings AI provider for this turn (khuôn scanner_controller d.720-728
    ``settings.ai.active_provider()``); a read failure yields ``None`` (fail-
    closed — the AI path reports "Chưa cấu hình" without calling anything)."""
    try:
        from services.settings_service import SettingsService

        return SettingsService().load().ai.active_provider()
    except Exception:
        return None


class NewsController:
    """Thin orchestration over ``NewsRepository`` + the three producers (M5/§3)."""

    def __init__(
        self,
        repo: NewsRepository | None = None,
        policy: NewsPolicy | None = None,
        rss_producer: RssProducer | None = None,
        fred_producer: FredRateProducer | None = None,
        *,
        ai_service: object | None = None,
        ai_config_provider: Callable[[], object] | None = None,
        schedule_starter: Callable[["NewsController"], object] | None = None,
    ) -> None:
        self._repo = repo if repo is not None else NewsRepository()
        self._policy = policy if policy is not None else load_news_policy()
        self._rss_producer = (
            rss_producer if rss_producer is not None else RssProducer(self._repo, self._policy)
        )
        self._fred_producer = fred_producer
        # AI seams (L3.5 — khuôn d.275-282): injected fakes for tests; the
        # production default resolves settings.ai.active_provider() lazily per
        # analyze turn (khuôn scanner_controller d.720-728).
        self._ai_service = ai_service
        self._ai_config_provider = ai_config_provider
        # Session guard of the app-startup turn (plan L3.6, khuôn
        # ``_auto_scanned_this_session`` của Scanner): the hook in ``main.py``
        # runs the turn exactly once per session — purge + schedule start
        # (QĐ-F2, đợt 3: no FF fetch remains in this turn).
        self._fetched_this_session = False
        # Producer-schedule seam (plan L3.7): ``None`` resolves to the real
        # QThread starter (built on use — needs a live QApplication); tests
        # inject a countable fake.  ``_schedule_*`` hold the running owner.
        self._schedule_starter = schedule_starter
        self._schedule_thread: object | None = None
        self._schedule_worker: object | None = None
        self._schedule: object | None = None

    # --- producer schedule per policy (§6.1 lượt 1-3, §7 keys) --------------------

    @property
    def rss_poll_interval_minutes(self) -> int:
        """RSS poll cadence — the ``rss_poll_interval_minutes`` policy key (R4).
        Exposed for the timer owner; this class never schedules itself."""
        return self._policy.rss_poll_interval_minutes

    @property
    def rates_refresh_hours(self) -> int:
        """FRED refresh cadence — read from the rate producer's ``refresh_hours``,
        i.e. the ``fred_refresh_hours`` policy key (R4)."""
        return self._rates_producer().refresh_hours

    def poll_news(self) -> RssCollectionResult:
        """Run ONE text-news collection round (delegated to ``rss_producer``).

        The cadence is the caller's (``rss_poll_interval_minutes``); this method
        performs exactly one round so the timer owner stays in charge of the
        schedule."""
        return self._rss_producer.fetch_round()

    def refresh_rates(self) -> RateFetchResult:
        """Run ONE policy-rate refresh round (delegated to ``fred_rate_producer``).

        The API key is read from the settings when this producer is first built
        (``_rates_producer``) — the caller passes nothing, exactly like the
        legacy ``get_latest_rates(fred_api_key=...)`` call site did."""
        return self._rates_producer().fetch_round()

    def _rates_producer(self) -> FredRateProducer:
        """The FRED producer, built on first use so its API key is current at
        round time; an injected producer wins (tests, alternate deployments)."""
        if self._fred_producer is None:
            self._fred_producer = FredRateProducer(
                self._repo, self._policy, api_key=_fred_api_key()
            )
        return self._fred_producer

    # --- app-startup turn (plan L3.6, QĐ-F2 — đợt 3: purge + schedule only) ------

    def run_startup_turn(self) -> StartupTurnResult:
        """Run the app-startup turn (QĐ-F2, plan L3.6) — once per session.

        The hook in ``main.py`` calls this at boot; the ``_fetched_this_session``
        session guard (khuôn ``_auto_scanned_this_session`` của Scanner) makes
        every further call a typed no-op, so exactly one turn happens per
        session.  The turn:

        1. purges expired ``ingest_runs`` — retention read from the policy key
           ``ingest_runs_retention_days`` via the loader (R4, contract §4.6:
           only the operational log; news and verdicts are never touched);
        2. starts the periodic RSS/FRED producer schedule (plan L3.7 — the two
           "tự động định kỳ" channels contract §6.2/§6.3/§13 keep).

        The ForexFactory parts of the old turn (JSON calendar + HTML actual
        channels) were removed with the FF automatic channels (đợt 3 — no
        request to ForexFactory remains anywhere; the only FF channel is the
        human-pasted page-source path ``parse_pasted_source``/
        ``commit_pasted_source``, tiếp nhận tại F3).  This layer
        delegates (C3 — no display string, no added retry)."""
        if self._fetched_this_session:
            return StartupTurnResult(ran=False)
        self._fetched_this_session = True
        purged = self._repo.purge_expired_runs(self._policy.ingest_runs_retention_days)
        self._start_producer_schedule()
        return StartupTurnResult(ran=True, purged_runs=purged)

    # --- producer schedule (contract §6.2/§6.3/§13, plan L3.7) ----------------

    def _start_producer_schedule(self) -> None:
        """Start the periodic RSS/FRED rounds — called by the first startup turn.

        The starter is the test seam ``schedule_starter`` if one was injected,
        otherwise the real QThread starter is built and started on use.  The
        session guard in ``run_startup_turn`` guarantees this runs at most once
        per session, so the schedule is never double-started."""
        if self._schedule_starter is not None:
            self._schedule = self._schedule_starter(self)
            return
        self._schedule = self._build_producer_schedule()

    def _build_producer_schedule(self) -> object:
        """The real starter: a ``QThread`` running a ``NewsWorker``.

        Imports PyQt and ``NewsWorker`` at function level (khuôn
        ``services.settings_service`` import ngay trong file, tránh import vòng
        ``news_worker ↔ news_controller``; tiền lệ controller-Qt:
        ``scanner_controller`` d.18).  Follows the caller khuôn documented in
        ``workers/news_worker.py``: ``moveToThread(thread)``,
        ``thread.started → worker.start``, ``thread.finished → deleteLater``.
        The controller keeps a strong reference (``_schedule_worker``) so the
        thread never outlives the controller silently.

        Fail-closed (B4): without a live ``QApplication`` the schedule cannot
        run safely, so the starter raises instead of silently skipping — the
        production boot (``main.py``) always creates the app before the QĐ-5
        hook.  Shutdown is wired here (no old file is touched to register it):
        ``aboutToQuit → stop_producer_schedule``."""
        from PyQt6.QtCore import QThread
        from PyQt6.QtWidgets import QApplication
        from workers.news_worker import NewsWorker

        app = QApplication.instance()
        if app is None:
            raise RuntimeError(
                "Không thể lên lịch producer RSS/FRED: thiếu QApplication. "
                "Lượt khởi động phải chạy sau khi Qt app được tạo (main.py)."
            )
        thread: QThread = QThread()
        thread.setObjectName("news-producer-schedule")
        worker: NewsWorker = NewsWorker(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.start)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        # Shutdown seam: wired at start time, so no other file needs to change
        # (QĐ-7 — app_controller.py is not touched).
        app.aboutToQuit.connect(self.stop_producer_schedule)

        self._schedule_worker = worker
        self._schedule_thread = thread
        thread.start()
        return thread

    def stop_producer_schedule(self) -> None:
        """Stop the periodic producer rounds and join their thread (bounded).

        Connected to ``aboutToQuit`` when the schedule starts; a second call
        (or a call with no running schedule) is a deterministic no-op.  The
        worker's timers are stopped via a queued call that runs in the worker's
        own thread (``QMetaObject.invokeMethod(BlockingQueuedConnection)``),
        then the thread is ``quit``-ed and ``wait``-ed with a ceiling (khuôn
        bounded wait của ``AppController.shutdown``) so teardown never hangs.
        """
        thread = getattr(self, "_schedule_thread", None)
        if thread is None:
            return
        self._schedule_thread = None
        self._schedule = None
        try:
            from PyQt6.QtCore import QMetaObject, Qt

            worker = getattr(self, "_schedule_worker", None)
            if worker is not None:
                QMetaObject.invokeMethod(
                    worker,
                    "stop",
                    Qt.ConnectionType.BlockingQueuedConnection,
                )
        except Exception:
            # The worker may already be gone — thread.quit() below still
            # releases the thread safely (never a hidden hang).
            pass
        self._schedule_worker = None
        thread.quit()
        thread.wait(5000)

    # --- pasted page-source channel (§6.1 đợt 3+4, plan F3 — luồng 2 pha) ------

    def parse_pasted_source(self, source_text: str) -> SourcePreview:
        """Pha 1 — bóc tách + xem trước của kênh dán mã nguồn (§6.1 bước 2 + 5).

        Nhận văn bản source (không tự bóc — S2) và giao cho chủ sở hữu duy nhất
        ``services/ff_source_parser.parse_calendar_source``; đọc sự kiện hiện hữu
        qua ``events_in_range`` (cửa sổ = min→max ``event_time_utc`` của lô dán,
        §8 — không thêm method hợp đồng nào) và nhờ hàm thuần phân loại dòng của
        parser ``classify_incoming_events`` (mới / sẽ cập nhật / xung đột-giữ-
        nhập-tay, §11b).  Trả ``SourcePreview`` có kiểu.

        **PHA 1 KHÔNG GHI DỮ LIỆU** — không ``upsert_events``, không
        ``add_rate_observations``, không run ``ok`` (DB nguyên trạng).  Parse
        lỗi → ``record_run(status=failed)`` với ``error_type``/``error_detail``
        có kiểu (§4.6/§6.1 — lỗi không tìm thấy lịch, lỗi JSON hỏng/cắt cụt)
        + lỗi trong preview (không bảng)."""
        fetched_at = _utc_now()
        outcome = parse_calendar_source(source_text, fetched_at=fetched_at)
        if outcome.error is not None:
            self._record_failed_parse(outcome.error, fetched_at)
            return SourcePreview(
                events=[],
                rates=[],
                dispositions=(),
                error=outcome.error,
                fetched_at=fetched_at,
            )
        existing = self._existing_in_paste_window(outcome.events)
        dispositions = tuple(classify_incoming_events(outcome.events, existing))
        return SourcePreview(
            events=list(outcome.events),
            rates=list(outcome.rates),
            dispositions=dispositions,
            error=None,
            fetched_at=fetched_at,
        )

    def commit_pasted_source(
        self,
        preview: SourcePreview,
        edited_actuals: Mapping[str, str],
    ) -> SourceIngestResult:
        """Pha 2 — xác nhận ghi của kênh dán mã nguồn (§6.1 bước 6 đợt 4).

        Nhận preview (lô đã bóc pha 1) + bản actual người dùng đã sửa (chỉ
        ``actual`` được khác giá trị bóc — QĐ-F6); gọi hàm thuần chung thiện lô
        của parser ``finalize_edited_batch`` (dòng sửa → ``source=user`` + actual
        FF gốc giữ trong ``raw_json``; dòng không sửa giữ ``ff_html``; quan sát
        lãi suất trong danh mục đồng bộ theo actual đã sửa, stamp ``ff_html``;
        ``dedupe_key`` BẤT BIẾN — §11b), rồi GHI qua repository:
        ``upsert_events`` + ``add_rate_observations`` (3 quy tắc merge nằm trong
        repository — không nhân bản, L2.1) + ``record_run(IngestRun(producer=
        user, status=ok, items_written=tổng sự kiện + lãi suất))``.  Trả tóm tắt
        mới/cập nhật/xung đột THẬT từ ``UpsertEventsResult`` của lần ghi (không
        dùng số dự đoán của preview) + số lãi suất đã ghi; xung đột quy tắc 3
        được ghi vào ``error_type``/``error_detail`` của run.  Hủy = UI không
        gọi method này → không ghi, không run, chỉnh sửa bị loại bỏ (§6.1)."""
        started_at = _utc_now()
        finalized = finalize_edited_batch(
            preview.events,
            edited_actuals=edited_actuals,
            fetched_at=preview.fetched_at,
        )
        upsert = self._repo.upsert_events(list(finalized.events))
        rates_written = self._repo.add_rate_observations(list(finalized.rates))
        error_type, error_detail = _run_error_fields(upsert.conflicts)
        run_id = self._repo.record_run(
            IngestRun(
                producer=IngestProducer.USER,
                started_at=started_at,
                finished_at=_utc_now(),
                status=IngestRunStatus.OK,
                items_written=upsert.inserted + upsert.updated + rates_written,
                error_type=error_type,
                error_detail=error_detail,
            )
        )
        return SourceIngestResult(
            inserted=upsert.inserted,
            updated=upsert.updated,
            conflicts=tuple(upsert.conflicts),
            rates_written=rates_written,
            run_id=run_id,
        )

    def reclassify_pasted_rows(
        self,
        preview: SourcePreview,
        edited_actuals: Mapping[str, str],
    ) -> tuple[RowDisposition, ...]:
        """Phân loại lại từng dòng sau khi người dùng sửa actual (QĐ-F9 — PO
        duyệt 25/09/2026; screen_design d.1602 "được phân loại lại so với
        database"; UI không tự phân loại — S2).

        Áp actual đã sửa lên bản sao của ``preview.events`` (chỉ
        ``replace(actual=...)`` — cùng quy ước ``finalize_edited_batch``, chỉ
        actual được khác giá trị bóc; ``dedupe_key`` BẤT BIẾN), đọc sự kiện hiện
        hữu qua ``events_in_range`` (cửa sổ = min→max ``event_time_utc`` của lô
        dán — §8, không method repo mới) rồi gọi hàm thuần
        ``classify_incoming_events`` của parser (§11b).  **KHÔNG GHI, KHÔNG run**
        — bản sao chỉ phục vụ hiển thị preview, không chạm DB."""
        if not preview.events:
            return ()
        edited_events = [
            replace(
                event,
                actual=str(edited_actuals[event.dedupe_key]).strip() or None,
            )
            if event.dedupe_key in edited_actuals
            else event
            for event in preview.events
        ]
        existing = self._existing_in_paste_window(preview.events)
        return tuple(classify_incoming_events(edited_events, existing))

    def _existing_in_paste_window(
        self, events: Sequence[CalendarEvent]
    ) -> list[CalendarEvent]:
        """Các bản ghi hiện hữu trong cửa sổ thời gian của lô dán (min→max
        ``event_time_utc``) — chính là đọc ``events_in_range`` §8 đã có; các
        chuỗi ISO-8601 UTC mang hậu tố ``Z`` so sánh đúng thứ tự thời gian."""
        if not events:
            return []
        from_utc = min(event.event_time_utc for event in events)
        to_utc = max(event.event_time_utc for event in events)
        return self._repo.events_in_range(from_utc, to_utc)

    def _record_failed_parse(self, error: ParseError, started_at: str) -> None:
        """Một dòng ``ingest_runs`` cho lượt bóc lỗi (§4.6/§6.1 — fail-closed:
        lỗi có kiểu, không ghi dữ liệu nào, all-or-nothing)."""
        self._repo.record_run(
            IngestRun(
                producer=IngestProducer.USER,
                started_at=started_at,
                finished_at=_utc_now(),
                status=IngestRunStatus.FAILED,
                items_written=0,
                error_type=error.kind.value,
                error_detail=error.detail,
            )
        )

    # --- manual entry (§6.4) ------------------------------------------------------

    def add_user_note(
        self,
        *,
        kind: str | None,
        published_utc: str | datetime | None,
        content: str | None,
        currencies: Sequence[str] | None,
        url: str | None = None,
        impact_hint: str | None = None,
    ) -> UserNoteResult:
        """Validate and write one manual note (§6.4).

        The four mandatory fields are required keyword arguments so a caller
        cannot forget one silently.  An invalid draft returns its typed field
        errors and writes nothing.  A valid draft becomes
        ``NewsItem(kind=user_note, source=user)``, is upserted through the
        repository (a repeated identical note updates its row — the §4.3
        ``dedupe_key`` decides that, not this layer) and logs one
        ``ingest_runs`` row for the manual turn (producer ``user``): contract §3
        lists the manual form in the producer column and §10 requires every
        producer turn to have its run row.  ``core/news_freshness`` deliberately
        ignores that producer when it classifies the store (a manual note is not
        a freshness signal)."""
        started_at = _utc_now()
        draft, errors = _validate_user_note(
            kind=kind,
            published_utc=published_utc,
            content=content,
            currencies=currencies,
            url=url,
            impact_hint=impact_hint,
        )
        if draft is None:
            return UserNoteResult(errors=errors)
        item = NewsItem(
            kind=NewsItemKind.USER_NOTE,
            source=NewsItemSource.USER,
            title=draft.content,
            published_utc=draft.published_utc,
            currencies=draft.currencies,
            dedupe_key=news_item_dedupe_key(
                url=draft.url,
                title=draft.content,
                published_utc=draft.published_utc,
            ),
            fetched_at=started_at,
            content=draft.content,
            url=draft.url,
            impact_hint=draft.impact_hint,
        )
        upsert: UpsertItemsResult = self._repo.upsert_items([item])
        run_id = self._repo.record_run(
            IngestRun(
                producer=IngestProducer.USER,
                started_at=started_at,
                finished_at=_utc_now(),
                status=IngestRunStatus.OK,
                items_written=upsert.inserted + upsert.updated,
            )
        )
        return UserNoteResult(
            errors=(),
            inserted=upsert.inserted,
            updated=upsert.updated,
            run_id=run_id,
        )

    def set_excluded(self, item_id: int, excluded: bool) -> int:
        """Flag/unflag one item (§6.4) — delegated; the controller takes no
        kind decision here because §6.4 lets an automatic item be excluded (its
        provenance survives, nothing is deleted).  Returns the rows flagged."""
        return self._repo.set_excluded(item_id, bool(excluded))

    def delete_user_note(self, item_id: int) -> int:
        """Delete one manual note (§6.4) — delegated; the repository holds the
        ``kind=user_note`` guard, so an automatic item is never deleted and the
        call reports 0 rows.  Returns the rows deleted."""
        return self._repo.delete_user_note(item_id)

    def update_user_note(
        self,
        item_id: int,
        *,
        kind: str | None,
        published_utc: str | datetime | None,
        content: str | None,
        currencies: Sequence[str] | None,
        url: str | None = None,
        impact_hint: str | None = None,
    ) -> UserNoteResult:
        """Replace one manual note (§6.4) — the "Sửa" path of the news screen.

        The contract §8 has no update-by-id method, so the edit is composed from
        the write methods it does expose and the §4.3 ``dedupe_key`` formula is
        NOT copied into the screen (QĐ-4 owns it in ``core/news_models.py``,
        L3.4).  The draft is validated through the SAME pure path
        ``add_user_note`` uses **before** anything is removed: a broken draft
        returns its typed field errors and nothing is written — the existing row
        is never deleted.  A valid draft deletes the old manual note and writes
        the replacement through the same ``add_user_note`` path (upsert +
        ``ingest_runs`` producer ``user``), so it uses only repository methods of
        §8.  Returns the ``UserNoteResult`` of the new write."""
        _draft, errors = _validate_user_note(
            kind=kind,
            published_utc=published_utc,
            content=content,
            currencies=currencies,
            url=url,
            impact_hint=impact_hint,
        )
        if errors:
            return UserNoteResult(errors=errors)
        self.delete_user_note(item_id)
        return self.add_user_note(
            kind=kind,
            published_utc=published_utc,
            content=content,
            currencies=currencies,
            url=url,
            impact_hint=impact_hint,
        )

    # --- reads served to consumers (§3 role, §8 read contract) --------------------

    def events_in_range(
        self,
        from_utc: str,
        to_utc: str,
        currencies: list[str] | None = None,
        include_non_impact: bool = True,
    ) -> list[CalendarEvent]:
        """Calendar events in a closed window (§8) — delegated, classified by
        the repository at read time."""
        return self._repo.events_in_range(from_utc, to_utc, currencies, include_non_impact)

    def items_in_range(
        self,
        from_utc: str,
        to_utc: str | None = None,
        kinds: list[str] | None = None,
        currencies: list[str] | None = None,
        exclude_flagged: bool = True,
    ) -> list[NewsItem]:
        """Text items in a window (§8) — delegated."""
        return self._repo.items_in_range(from_utc, to_utc, kinds, currencies, exclude_flagged)

    def latest_rates(self, currencies: list[str]) -> list[CurrencyRateTrend]:
        """Latest observation + derived trend per currency (§8/§4.4) — delegated;
        the trend comes from ``core/rate_trend.py``, never from this layer."""
        return self._repo.latest_rates(currencies)

    def store_state(self) -> StoreState:
        """Freshness of each signal (§8/§6.5) — delegated; the classification
        comes from ``core/news_freshness.py``."""
        return self._repo.store_state()

    def display_timezone(self) -> str:
        """Múi giờ hiển thị của tầng trình bày (Owner quyết 25/09/2026).

        Đọc khóa ``settings.display.timezone`` (Settings cho chọn
        ``Asia/Ho_Chi_Minh`` / ``Asia/Bangkok`` / ``UTC``) — seam trình bày cho
        News UI (news_screen không được import ``services`` — L1/E2, khuôn
        ``_fred_api_key`` d.473-484); khóa thiếu/hỏng → fallback
        ``Asia/Ho_Chi_Minh`` (B4 — không im lặng lạc quan).  Dữ liệu lưu vẫn UTC
        (§4.2/§6.1 bước 3) — chỉ tầng trình bày đổi múi giờ khi hiển thị."""
        try:
            from services.settings_service import SettingsService

            name = str(SettingsService().load().display.timezone or "")
        except Exception:
            name = ""
        return name or "Asia/Ho_Chi_Minh"

    # --- AI trend judgement (§9.1, plan L3.5) --------------------------------------

    def ai_scope_preview(self, scope_type: str, scope_value: str, now: datetime | None = None) -> AiScopePreview:
        """§9.1 step 2 — counts + floor of one scope, NO AI call.

        The dialog shows "Cửa sổ tin: <window_days> ngày gần nhất — <N> tin/sự
        kiện liên quan" (d.1629) from this preview and, when ``insufficient``,
        shows "Không đủ dữ liệu nhận định" (d.1642) and never calls the AI
        (fail-closed, B4 — the same floor the builder enforces)."""
        outcome = self._ai_outcome(scope_type, scope_value, now)
        return AiScopePreview(
            scope_type=scope_type,
            scope_value=scope_value,
            window_days=self._policy.ai_window_days,
            event_count=outcome.event_count,
            item_count=outcome.item_count,
            min_items=outcome.min_items,
        )

    def analyze_trend(
        self, scope_type: str, scope_value: str, now: datetime | None = None
    ) -> TrendAnalysisResult:
        """One AI trend run for one scope (§9.1 steps 2-6).

        Runs inside the dialog's background worker (the screen never calls this
        synchronously from a GUI callback).  Reads the repo for the scope's
        currencies inside ``ai_window_days`` (``excluded=0``), builds the prompt
        through ``core/trend_prompt_builder``, fails closed below
        ``ai_min_items`` (no AI call), calls ``AIService.analyze`` inside the
        worker, parses through ``core/trend_verdict_parser``, retries exactly
        ONCE on the parser's ``retryable`` signal, and stores nothing on final
        failure (§9.1 step 5 — friendly message instead).  On success composes
        the three ``TrendVerdict`` rows (``input_snapshot`` = prompt snapshot,
        ``prompt_hash``, provider/model provenance) and stores via
        ``repo.add_verdicts`` (§8)."""
        outcome = self._ai_outcome(scope_type, scope_value, now)
        prompt = outcome.prompt
        if prompt is None:
            # Below ai_min_items — no prompt exists, the AI must not be called.
            return TrendAnalysisResult(
                ok=False,
                insufficient=True,
                event_count=outcome.event_count,
                item_count=outcome.item_count,
            )
        resolved = self._resolve_ai_service()
        if resolved is None:
            return TrendAnalysisResult(
                ok=False,
                error_message=NO_AI_CONFIG_TEXT,
                event_count=outcome.event_count,
                item_count=outcome.item_count,
            )
        service, provider, model = resolved
        try:
            parsed = self._analyze_answer(service, prompt)
            if parsed.error is not None and parsed.error.retryable:
                # §9.1 bước 5 — retry ĐÚNG MỘT lần theo tín hiệu retryable
                # của parser (parser không bao giờ tự retry).
                parsed = self._analyze_answer(service, prompt)
        except Exception as exc:
            # Provider lỗi — các adapter đã dịch qua friendly_error() khi raise.
            return TrendAnalysisResult(
                ok=False,
                error_message=str(exc),
                event_count=outcome.event_count,
                item_count=outcome.item_count,
            )
        if not parsed.ok:
            # Thất bại cuối (retry cạn hoặc câu trả lời không hợp lệ) — không
            # lưu verdict rác (§9.1).
            return TrendAnalysisResult(
                ok=False,
                error_message=PARSE_FAIL_TEXT,
                event_count=outcome.event_count,
                item_count=outcome.item_count,
            )
        verdicts = self._compose_verdicts(scope_type, scope_value, prompt, parsed, provider, model)
        inserted = self._repo.add_verdicts(verdicts)
        return TrendAnalysisResult(
            ok=True,
            verdicts=tuple(verdicts),
            inserted=inserted,
            event_count=outcome.event_count,
            item_count=outcome.item_count,
        )

    def verdicts_for(self, scope_type: str, scope_value: str, limit: int) -> list[TrendVerdict]:
        """Verdict history of one scope, newest first (§8) — the news screen is
        the ONLY consumer of verdict history (contract §9.2).  ``limit`` is a
        presentation value of the dialog (B5 — no policy key involved)."""
        return self._repo.verdicts_for(VerdictScopeType(scope_type), scope_value, limit)

    # --- AI helpers ---------------------------------------------------------------

    def _ai_outcome(
        self, scope_type: str, scope_value: str, now: datetime | None
    ) -> TrendPromptOutcome:
        """The prompt outcome for one scope — the single data-read path shared
        by the preview and the analysis (they agree on counts and the floor)."""
        moment = now if now is not None else datetime.now(UTC)
        events, items = self._ai_rows(scope_type, scope_value, moment)
        return build_trend_prompt(
            scope_type=scope_type,
            scope_value=scope_value,
            events=events,
            items=items,
            now=moment,
            window_days=self._policy.ai_window_days,
            horizons=self._policy.ai_horizons,
            min_items=self._policy.ai_min_items,
        )

    def _ai_rows(
        self, scope_type: str, scope_value: str, moment: datetime
    ) -> tuple[list[CalendarEvent], list[NewsItem]]:
        """Rows relevant to one scope inside ``ai_window_days``: events and text
        items touching the scope's currencies, ``excluded=0`` (§9.1 bước 2).
        The scope value is the dialog's contract (pairs come from the
        SUPPORTED_SYMBOLS combo — no invented list)."""
        if scope_type == "currency":
            currencies = [str(scope_value)]
        else:
            currencies = [part.strip() for part in str(scope_value).split("/") if part.strip()]
        from_utc = _normalize_published_utc(moment - timedelta(days=self._policy.ai_window_days))
        to_utc = _normalize_published_utc(moment)
        events = self._repo.events_in_range(from_utc, to_utc, currencies=currencies)
        items = self._repo.items_in_range(
            from_utc, to_utc, currencies=currencies, exclude_flagged=True
        )
        return list(events), list(items)

    def _resolve_ai_service(self) -> tuple[AIService, str, str] | None:
        """Resolve the AI service for this turn (khuôn scanner d.720-728): the
        settings provider, or None when unconfigured / keyless — fail-closed,
        no call, friendly message (V2 declared)."""
        if self._ai_config_provider is None:
            provider = _read_active_ai_provider()
        else:
            provider = self._ai_config_provider()
        if provider is None or not getattr(provider, "api_key", ""):
            return None
        name = str(getattr(provider, "provider", ""))
        model = str(getattr(provider, "model", ""))
        if self._ai_service is not None:
            return self._ai_service, name, model
        return (
            AIService(
                AIProviderConfig(
                    provider=name,
                    model=model,
                    api_key=str(getattr(provider, "api_key", "")),
                    base_url=str(getattr(provider, "base_url", "") or ""),
                )
            ),
            name,
            model,
        )

    def _analyze_answer(self, service: object, prompt: TrendPrompt) -> TrendParseOutcome:
        """One analyze+parse round; the caller owns the retry decision."""
        raw = service.analyze(prompt.text)  # type: ignore[attr-defined]
        return parse_trend_verdict(
            raw,
            horizons=tuple(self._policy.ai_horizons),
            evidence_item_ids=prompt.evidence_item_ids,
        )

    def _compose_verdicts(
        self,
        scope_type: str,
        scope_value: str,
        prompt: TrendPrompt,
        parsed: TrendParseOutcome,
        provider: str,
        model: str,
    ) -> list[TrendVerdict]:
        """Compose the three verdict rows of one accepted answer (§9.1 bước 6 —
        "composing the three rows is the controller's job (L3.5)")."""
        created_at = _utc_now()
        return [
            TrendVerdict(
                created_at=created_at,
                scope_type=VerdictScopeType(scope_type),
                scope_value=scope_value,
                horizon=verdict.horizon,
                direction=verdict.direction,
                confidence=verdict.confidence,
                rationale=verdict.rationale,
                evidence_item_ids=list(verdict.evidence_item_ids),
                input_snapshot=dict(prompt.snapshot),
                provider=provider,
                model=model,
                prompt_hash=prompt.prompt_hash,
            )
            for verdict in parsed.verdicts
        ]
