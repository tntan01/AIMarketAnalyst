"""NewsController — the thin orchestration layer of the News domain (plan batch L2.7).

Owner of "tiếp nhận và xác thực tin người dùng nhập" (contract §6.4 / §11b) and
the orchestrator registered in the contract §3 layer table: it schedules the
producers per policy, serves queries to consumers, accepts manual entries and
— later, in L3.5 — coordinates the AI call inside a worker.

This module **delegates**.  It owns no formula, no status classification, no
trend derivation and no display string (C3/S2, L1/L3): every read and write goes
to ``NewsRepository`` (the single access point, §8), the values crossing its
boundary are the typed models of ``core/news_models.py``, and every operational
number comes from the policy via ``core/news_policy.load_news_policy`` (R4).

Delivered by this batch (plan L2.7):

* **Producer schedule per policy** — ``poll_news`` runs one ``rss_producer``
  round (cadence key ``rss_poll_interval_minutes``) and ``refresh_rates`` one
  ``fred_rate_producer`` round (cadence read from that producer's
  ``refresh_hours``, i.e. the ``fred_refresh_hours`` key).  Both cadences are
  exposed for the timer owner, ``workers/news_worker.py``.  **This batch starts
  nothing**: the app-startup turn of §6.1 is L3.6 and the news-screen buttons
  are L3.3.
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
* **On-demand lookup seam** (§6.1 lượt 4, plan L2.2) — the constructor plugs
  ``ff_calendar_producer.lookup_event_actual`` into the repository.  The
  repository triggers the callable for a ``stale`` event and never touches the
  network itself; the producer owns transport and its ``on_demand_lookup``
  ``ingest_runs`` row.

**No AI path here** (plan L2.7 — the AI call arrives with L3.5), and
``verdicts_for`` is deliberately *not* delegated yet: the verdict history read
belongs to the AI dialog batch (L3.5; contract §9.2 names the news screen and
this controller as the only allowed consumers).

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

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from core.news_models import (
    CalendarEvent,
    ImpactHint,
    IngestProducer,
    IngestRun,
    IngestRunStatus,
    NewsItem,
    NewsItemKind,
    NewsItemSource,
    StoreState,
)
from core.news_policy import NewsPolicy, load_news_policy
from services.news_producers.ff_calendar_producer import FFCalendarProducer
from services.news_producers.fred_rate_producer import FredRateProducer, RateFetchResult
from services.news_producers.rss_producer import RssCollectionResult, RssProducer
from services.news_repository import CurrencyRateTrend, NewsRepository, UpsertItemsResult

__all__ = ["NewsController", "UserNoteFieldError", "UserNoteResult"]


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


def _user_note_dedupe_key(*, url: str | None, title: str, published_utc: str) -> str:
    """The §4.3 dedupe key of a ``news_items`` row: hash of the url, else hash of
    ``title + published_utc`` (stable sha256 hex — the same formula the
    ``rss_producer`` converter applies at its boundary; §4.3 defines it once)."""
    seed = url if url else f"{title}|{published_utc}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    """Current UTC time in the khuôn ISO-8601 form: ``YYYY-MM-DDTHH:MM:SSZ``."""
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


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


class NewsController:
    """Thin orchestration over ``NewsRepository`` + the three producers (M5/§3)."""

    def __init__(
        self,
        repo: NewsRepository | None = None,
        policy: NewsPolicy | None = None,
        rss_producer: RssProducer | None = None,
        fred_producer: FredRateProducer | None = None,
        ff_producer: FFCalendarProducer | None = None,
    ) -> None:
        self._repo = repo if repo is not None else NewsRepository()
        self._policy = policy if policy is not None else load_news_policy()
        self._rss_producer = (
            rss_producer if rss_producer is not None else RssProducer(self._repo, self._policy)
        )
        self._fred_producer = fred_producer
        self._ff_producer = (
            ff_producer if ff_producer is not None else FFCalendarProducer(self._repo)
        )
        # On-demand lookup seam (§6.1 lượt 4, plan L2.2): the producer owns the
        # fetch and its ingest_runs row; the repository only calls the callable
        # when it meets a stale event.
        self._repo.on_demand_lookup = self._ff_producer.lookup_event_actual

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
            dedupe_key=_user_note_dedupe_key(
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

    def events_pending_actual(self, now: datetime) -> list[CalendarEvent]:
        """Events past their grace window without an actual (§8) — the input of
        the HTML actual turns (§6.1)."""
        return self._repo.events_pending_actual(now)

    def event_actual_or_lookup(self, event_id: int) -> CalendarEvent | None:
        """One event; a ``stale`` event triggers the on-demand lookup the
        constructor wired (§6.1 lượt 4).  Returns ``None`` for an unknown id."""
        return self._repo.event_actual_or_lookup(event_id)

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
