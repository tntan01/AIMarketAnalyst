"""fred_rate_producer — policy-rate observations of the eight currencies (plan batch L2.6).

Sole owner of "thu thập lãi suất điều hành 8 đồng tiền thành ``RateObservation``"
(contract §6.3 / §11b, identity M5 — QĐ-1 phương án A, Owner duyệt 21/09/2026).
This batch absorbs ``services/interest_rate_service.py`` into a new file and
leaves the old file untouched (QĐ-1A: its rate cache keeps feeding the legacy
macro path until connect-time b): ``FRED_SERIES`` (d.17-26),
``_fetch_from_fred`` (d.155-204), the ForexFactory-HTML rate channel
``_update_from_forexfactory`` + ``_FOREX_RATE_EVENTS`` (d.76-139 / d.29-38) and
the JSON fallback ``_load_fallback`` (d.207-212).

One entry point, ``fetch_round`` = ONE refresh round = one ``ingest_runs`` row
(producer ``fred``, contract §4.6/§10).  The write destination is the only
thing that changes (plan L2.6 review point): observations go to
``NewsRepository.add_rate_observations`` — the ``interest_rates`` table keyed by
``(currency, observed_at, source)`` (§4.4) — instead of the legacy in-memory
``_CACHE`` dict plus the ``config/interest_rates.json`` write-back.

**Source chain per currency: ``fred`` → ``ff_html`` → ``config_fallback``**
(plan L2.6 "fallback chain đúng thứ tự").  Every currency of ``FRED_SERIES``
the primary FRED channel could not deliver is offered to the HTML channel, and
whatever is still missing at the end is filled from the local JSON file.  A
currency carries exactly one source per round.  The run status is ``ok`` when
the FRED channel covered the whole scope, ``partial`` when observations were
written without full primary coverage, ``failed`` when nothing was written
(B4 — the status never claims a healthy primary source it did not have).

Trend (hike/cut/hold) is NEVER derived here (§4.4/§11b: ``core/rate_trend.py``
owns the derivation and the consumer calls ``NewsRepository.latest_rates``).
That is why the FRED channel records the two nearest observations it fetched
(``limit=2``/``sort_order=desc`` verbatim) instead of collapsing them into the
legacy's inline trend field: the two-nearest-observation read reproduces the
legacy trend exactly (B3, function level).

Governance:

* **No timer, no in-memory cache.**  The legacy ``_CACHE``/``_CACHE_TIME``/
  ``_CACHE_TTL`` (6 h, d.40-42) and ``_FF_LAST_SCAN``/``_FF_SCAN_TTL`` (3 h,
  d.44-45) are deliberately NOT ported: the cadence key ``fred_refresh_hours``
  is the single owner of the frequency (R4 — never hard-coded in logic) and the
  timer belongs to the L2.7 worker.  ``refresh_hours`` exposes that key to the
  caller; a round is never suppressed by wall-clock time.
* **No write-back.**  ``_save_fallback`` is NOT ported (B7 §3.1.2: the new
  system writes only ``news.db``; R1: the JSON file is read-only input, never a
  data path shared with the legacy system).
* **No display strings** (contract §8): the legacy ``rate_label`` and
  ``central_bank`` have no ``interest_rates`` column (§4.4) and are dropped —
  only the five §4.4 columns are written.
* **Raw rows never leave the converters** (R8/C2): the ForexFactory HTML row
  shape (``currency``/``event``/``actual``/``time_utc``) is visible only inside
  ``_rate_observations_from_html``, the FRED JSON observations only inside
  ``_fred_observations``.
* **The HTML channel reuses the inherited client** exactly as the legacy
  function does — ``services/forex_factory_client.ForexFactoryClient``
  (read-only, untouched, one shot per week page, no retry: §6.1 anti-abuse).
  Its parser is the same code the old file ran, so the HTML link is
  B3-identical by construction; the connect-time batch b that deletes that
  client (contract §12) must rewire this link.
* **Deviations, plan-sanctioned (V2):** (a) the legacy FF gate
  ``new_rate != old_rate`` (d.122) compared the HTML reading against a
  cross-source merged value and only mutated a dict — the plan's chain hands
  the HTML channel the currencies FRED left empty, so that gate has no
  counterpart in a source-separated store and is not ported; (b) transport and
  channel failures are recorded as typed errors in ``ingest_runs`` (§4.6/§10)
  instead of being swallowed by ``logger.debug``; (c) a fallback entry without
  any observation date is skipped — ``observed_at`` is NOT NULL and part of the
  §4.4 key, and no date is ever invented (B4/B5).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timezone
from pathlib import Path

import requests

from core.news_models import (
    IngestProducer,
    IngestRun,
    IngestRunStatus,
    RateObservation,
    RateSource,
)
from core.news_policy import NewsPolicy, load_news_policy
from services.news_repository import NewsRepository

__all__ = [
    "FRED_SERIES",
    "FredRateProducer",
    "RateChannelError",
    "RateFetchResult",
]


# ---------------------------------------------------------------------------
# Inherited runtime data (B5: kế thừa runtime hiện hành — không bịa)
# ---------------------------------------------------------------------------

# interest_rate_service.py:17-26 — tiền tệ → series ID trên FRED (nguyên văn).
FRED_SERIES: dict[str, str] = {
    "USD": "FEDFUNDS",           # Fed Funds Rate
    "EUR": "ECBDFR",             # ECB Deposit Facility Rate
    "GBP": "BOEBR",              # Bank of England Base Rate
    "JPY": "IRSTCI01JPM156N",    # BOJ Policy Rate
    "AUD": "RBATCTR",            # RBA Cash Rate
    "NZD": "RBNZ_OCR",           # RBNZ OCR
    "CAD": "BOCWATCH",           # BOC Rate
    "CHF": "SNPOLICYR",          # SNB Policy Rate
}

# interest_rate_service.py:29-38 — tiền tệ → mẫu tên sự kiện trên ForexFactory
# (nguyên văn; khớp bằng ``p in event_name`` trên tên đã lower()).
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

# interest_rate_service.py:157 — endpoint FRED (nguyên văn).
FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"

# interest_rate_service.py:88-91 — hai trang tuần ForexFactory của đường lãi suất
# ("this" + "last"; nguyên văn — khác bộ URL của ff_calendar_producer).
FF_WEEK_URLS: tuple[str, ...] = (
    "https://www.forexfactory.com/calendar?week=this",
    "https://www.forexfactory.com/calendar?week=last",
)

# interest_rate_service.py:43 — tệp fallback cục bộ (đọc, không bao giờ ghi).
FALLBACK_FILENAME = "interest_rates.json"

# Kênh ghi = giá trị enum của §4.4 (một nguồn từ vựng duy nhất).
_CHANNEL_FRED = RateSource.FRED.value
_CHANNEL_FF_HTML = RateSource.FF_HTML.value
_CHANNEL_CONFIG_FALLBACK = RateSource.CONFIG_FALLBACK.value


# ---------------------------------------------------------------------------
# Typed results (C3 — không dict trần qua ranh giới)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RateChannelError:
    """One typed failure of a rate round (contract §4.6 style: the channel name
    plus the inherited transport classification — ``Http<code>``/``UrlError``/
    ``InvalidHtmlTable``/``InvalidObservation``/``NoApiKey``).

    ``currency`` is empty for a channel-wide failure (a week page that did not
    load, a missing API key, an unreadable fallback file)."""

    channel: str
    currency: str
    error_type: str
    detail: str


@dataclass(frozen=True, slots=True)
class RateFetchResult:
    """Typed outcome of one rate refresh round (contract §6.3/§4.6).

    Per-source observation counts (never a bare dict, C3), the currencies the
    round covered, the run status logged into ``ingest_runs`` and the typed
    channel errors.  No raw FRED/HTML row crosses this boundary (R8)."""

    fred_observations: int
    ff_html_observations: int
    config_fallback_observations: int
    currencies_covered: tuple[str, ...]
    run_status: IngestRunStatus
    run_id: int
    errors: tuple[RateChannelError, ...]

    @property
    def written(self) -> int:
        """Total observations handed to ``add_rate_observations`` (typed count)."""
        return (
            self.fred_observations
            + self.ff_html_observations
            + self.config_fallback_observations
        )


class FredRateProducer:
    """Sole owner of collecting policy-rate observations into ``RateObservation``
    (M5, contract §6.3)."""

    def __init__(
        self,
        repo: NewsRepository,
        policy: NewsPolicy | None = None,
        api_key: str | None = None,
        fallback_path: str | Path | None = None,
    ) -> None:
        self._repo = repo
        # Injected for testability; loaded fail-closed when absent (R4 — the
        # cadence key lives in config/news_policy.json, never in this file).
        self._policy = policy if policy is not None else load_news_policy()
        # The FRED key is passed in by the caller (the legacy signature took it
        # as ``get_latest_rates(fred_api_key=...)``; DI is the L2.7 controller's
        # job — no settings read here).
        self._api_key = api_key
        self._fallback_path = Path(fallback_path) if fallback_path is not None else None

    @property
    def refresh_hours(self) -> int:
        """The FRED refresh cadence, read from the policy key
        ``fred_refresh_hours`` (contract §7, R4).

        Exposed for the L2.7 worker/controller that owns the timer; this
        producer never schedules itself and never suppresses a round by
        wall-clock time (the legacy 6 h in-memory cache is not ported)."""
        return self._policy.fred_refresh_hours

    # --- public round (contract §6.3, plan L2.6) ---------------------------------

    def fetch_round(self) -> RateFetchResult:
        """One refresh round over the 8 currencies: FRED, then the ForexFactory
        HTML channel, then the local JSON fallback (plan L2.6 chain order).

        Every observation of the round is written through
        ``NewsRepository.add_rate_observations`` (§4.4 — a duplicate
        ``(currency, observed_at, source)`` overwrites instead of duplicating),
        and exactly one ``ingest_runs`` row (producer ``fred``) is logged
        (§4.6/§10), including a round that wrote nothing.  Channels never retry
        beyond the inherited single shot (§6.1 anti-abuse)."""
        fetched_at = _utc_now()
        errors: list[RateChannelError] = []

        fred_observations, fred_errors = self._fetch_from_fred(fetched_at)
        fred_observations = _dedupe(fred_observations)
        errors.extend(fred_errors)
        covered = {observation.currency for observation in fred_observations}

        ff_html_observations: list[RateObservation] = []
        remaining = [currency for currency in FRED_SERIES if currency not in covered]
        if remaining:
            ff_html_observations, ff_errors = self._update_from_forexfactory(
                fetched_at, remaining
            )
            ff_html_observations = _dedupe(ff_html_observations)
            errors.extend(ff_errors)
            covered.update(observation.currency for observation in ff_html_observations)

        fallback_observations: list[RateObservation] = []
        remaining = [currency for currency in FRED_SERIES if currency not in covered]
        if remaining:
            fallback_observations, fallback_errors = self._load_fallback(
                fetched_at, remaining
            )
            fallback_observations = _dedupe(fallback_observations)
            errors.extend(fallback_errors)

        observations = [
            *fred_observations,
            *ff_html_observations,
            *fallback_observations,
        ]
        written = self._repo.add_rate_observations(observations)

        primary_currencies = {observation.currency for observation in fred_observations}
        run_status = _run_status(len(primary_currencies), len(FRED_SERIES), written)
        first_error = errors[0] if errors else None
        run_id = self._repo.record_run(
            IngestRun(
                producer=IngestProducer.FRED,
                started_at=fetched_at,
                finished_at=_utc_now(),
                status=run_status,
                items_written=written,
                error_type=first_error.error_type if first_error else None,
                error_detail=_describe(first_error) if first_error else None,
            )
        )
        return RateFetchResult(
            fred_observations=len(fred_observations),
            ff_html_observations=len(ff_html_observations),
            config_fallback_observations=len(fallback_observations),
            currencies_covered=tuple(sorted(covered)),
            run_status=run_status,
            run_id=run_id,
            errors=tuple(errors),
        )

    # --- FRED channel (port of interest_rate_service._fetch_from_fred, d.155-204) --

    def _fetch_from_fred(
        self, fetched_at: str
    ) -> tuple[list[RateObservation], list[RateChannelError]]:
        """Fetch the latest FRED observations for the 8 series.

        Inherited transport verbatim (d.163-169): ``requests.get`` on the
        observations endpoint with ``series_id``/``api_key``/``file_type=json``/
        ``sort_order=desc``/``limit=2``/``timeout=5``; a non-200 response skips
        that currency, an exception skips that currency (the legacy swallowed it
        with ``logger.debug`` — here it becomes a typed error of the round).
        Sentinel values (``"."``) are filtered out before anything is read from
        the payload; the two nearest valid observations are recorded with their
        own ``date`` as ``observed_at`` (§4.4 — trend is derived at read time
        from the two nearest observations, never here)."""
        if not self._api_key:
            # Nguyên hành vi cũ (d.58): không có khóa ⇒ bỏ qua hẳn kênh FRED.
            return [], [
                RateChannelError(
                    _CHANNEL_FRED,
                    "",
                    "NoApiKey",
                    "no FRED API key configured",
                )
            ]

        observations: list[RateObservation] = []
        errors: list[RateChannelError] = []
        for currency, series_id in FRED_SERIES.items():
            try:
                response = requests.get(
                    FRED_OBSERVATIONS_URL,
                    params={
                        "series_id": series_id,
                        "api_key": self._api_key,
                        "file_type": "json",
                        "sort_order": "desc",
                        "limit": 2,  # B3: hai điểm gần nhất
                    },
                    timeout=5,
                )
                if response.status_code != 200:
                    errors.append(
                        RateChannelError(
                            _CHANNEL_FRED,
                            currency,
                            f"Http{response.status_code}",
                            f"{series_id}: HTTP {response.status_code}",
                        )
                    )
                    continue

                payload = response.json().get("observations", [])
                valid = [row for row in payload if row.get("value", ".") != "."]
                if not valid:
                    errors.append(
                        RateChannelError(
                            _CHANNEL_FRED,
                            currency,
                            "NoObservations",
                            f"{series_id}: no usable observation",
                        )
                    )
                    continue

                observations.extend(_fred_observations(currency, valid, fetched_at))
            except Exception as exc:  # transport/data fault — currency fails alone
                errors.append(
                    RateChannelError(
                        _CHANNEL_FRED,
                        currency,
                        _classify_error(exc),
                        f"{series_id}: {exc}",
                    )
                )
                continue
        return observations, errors

    # --- ForexFactory HTML channel (port of _update_from_forexfactory, d.76-139) ---

    def _update_from_forexfactory(
        self, fetched_at: str, currencies: list[str]
    ) -> tuple[list[RateObservation], list[RateChannelError]]:
        """Scan the two ForexFactory week pages for central-bank rate decisions
        of ``currencies`` — the inherited HTML link of the rate channel.

        Paged verbatim (d.88-96): the ``this`` and ``last`` week URLs, each
        fetched by the inherited client, a failing week never blocking the
        other.  Rows that match ``_FOREX_RATE_EVENTS`` with a readable actual
        become ``ff_html`` observations; the raw rows are consumed by the
        converter here and never leave this module (R8).  The HTML transport is
        one shot per page — a failure is recorded, never re-polled (§6.1
        anti-abuse)."""
        rows: list[dict[str, object]] = []
        errors: list[RateChannelError] = []
        for week_url in FF_WEEK_URLS:
            try:
                rows.extend(self._fetch_html_week(week_url))
            except Exception as exc:  # một tuần hỏng không chặn tuần kia (d.92-96)
                errors.append(
                    RateChannelError(
                        _CHANNEL_FF_HTML,
                        "",
                        _classify_html_error(exc),
                        f"{week_url}: {exc}",
                    )
                )
                continue
        if not rows:
            return [], errors
        return _rate_observations_from_html(rows, currencies, fetched_at), errors

    def _fetch_html_week(self, week_url: str) -> list[dict[str, object]]:
        """One-shot fetch+parse of a single ForexFactory week page.

        Uses the inherited client exactly as the legacy function did (d.84-94):
        a fresh ``ForexFactoryClient`` per round, its HTML URL pointed at the
        requested week, then ``_fetch_html_events`` (UA
        ``Mozilla/5.0 (compatible; AI Market Analyst/1.0)``, ``timeout=10``, no
        retry — HTTPError/URLError become ``RuntimeError("HTTP <code>")``/
        ``RuntimeError(str(reason))``, an unparseable page becomes
        ``RuntimeError("không đọc được bảng HTML")``).  The client is read-only
        and untouched (QĐ-1A); its parsed rows stay inside this module (R8)."""
        from services.forex_factory_client import ForexFactoryClient

        client = ForexFactoryClient()
        client.FOREX_FACTORY_HTML_URL = week_url
        return client._fetch_html_events()

    # --- JSON fallback channel (port of interest_rate_service._load_fallback) -----

    def _load_fallback(
        self, fetched_at: str, currencies: list[str]
    ) -> tuple[list[RateObservation], list[RateChannelError]]:
        """Read the local ``config/interest_rates.json`` last-resort channel.

        Inherited read (d.207-212): the ``currencies`` block of the file, any
        read/parse failure yielding nothing instead of raising.  Only the
        currencies still missing after the FRED and HTML channels are filled
        (plan L2.6 chain order), only as ``config_fallback`` observations.  A
        currency whose entry carries no usable observation date is skipped —
        ``observed_at`` is NOT NULL and part of the §4.4 key, so no date is ever
        invented (B4/B5)."""
        raw = self._read_fallback_file()
        entries = raw.get("currencies", {})
        if not isinstance(entries, dict):
            entries = {}
        file_last_updated = raw.get("_last_updated")

        observations: list[RateObservation] = []
        errors: list[RateChannelError] = []
        for currency in currencies:
            entry = entries.get(currency)
            if not isinstance(entry, dict):
                errors.append(
                    RateChannelError(
                        _CHANNEL_CONFIG_FALLBACK,
                        currency,
                        "MissingFallbackEntry",
                        f"{FALLBACK_FILENAME}: no entry for {currency}",
                    )
                )
                continue
            rate = _parse_rate(entry.get("rate"))
            if rate is None:
                errors.append(
                    RateChannelError(
                        _CHANNEL_CONFIG_FALLBACK,
                        currency,
                        "InvalidFallbackRate",
                        f"{FALLBACK_FILENAME}: unreadable rate for {currency}",
                    )
                )
                continue
            observed_at = _fallback_observed_at(entry, file_last_updated)
            if observed_at is None:
                errors.append(
                    RateChannelError(
                        _CHANNEL_CONFIG_FALLBACK,
                        currency,
                        "MissingObservationDate",
                        f"{FALLBACK_FILENAME}: no observation date for {currency}",
                    )
                )
                continue
            observations.append(
                RateObservation(
                    currency=currency,
                    rate=rate,
                    observed_at=observed_at,
                    source=RateSource.CONFIG_FALLBACK,
                    fetched_at=fetched_at,
                )
            )
        return observations, errors

    def _read_fallback_file(self) -> dict[str, object]:
        """Parse the fallback JSON file; any fault yields ``{}`` (inherited
        ``_load_fallback`` behavior, d.207-212 — a missing file is not an
        exception in the legacy code, it is simply no fallback data)."""
        try:
            raw = json.loads(self._fallback_file().read_text(encoding="utf-8"))
        except Exception:
            return {}
        return raw if isinstance(raw, dict) else {}

    def _fallback_file(self) -> Path:
        """The fallback file to read: the injected path (tests, alternate
        deployments), else ``config/interest_rates.json`` — the legacy
        ``_FALLBACK_PATH`` (d.43) resolved through ``config.paths`` so the
        domain keeps one config root (D5)."""
        if self._fallback_path is not None:
            return self._fallback_path
        from config.paths import CONFIG_DIR

        return CONFIG_DIR / FALLBACK_FILENAME


# ---------------------------------------------------------------------------
# Module helpers (ported verbatim from interest_rate_service, B3)
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    """Current UTC time in the khuôn ISO-8601 form: ``YYYY-MM-DDTHH:MM:SSZ``."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _dedupe(observations: list[RateObservation]) -> list[RateObservation]:
    """Collapse observations that share the §4.4 key ``(currency, observed_at,
    source)`` — first one wins, order preserved.

    The two ForexFactory week pages overlap (an event of the current week appears
    on both), so the same reading can be converted twice in one round; the
    legacy dict collapsed that naturally, and the write count of the round must
    stay the number of rows actually written (§4.6)."""
    seen: set[tuple[str, str, str]] = set()
    unique: list[RateObservation] = []
    for observation in observations:
        key = (observation.currency, observation.observed_at, observation.source.value)
        if key in seen:
            continue
        seen.add(key)
        unique.append(observation)
    return unique


def _parse_rate(value: object) -> float | None:
    """Rate reader (d.116/178): strip a trailing ``%`` then ``float`` — an
    unreadable value is ``None`` (the legacy skipped that row/currency)."""
    try:
        return float(str(value).replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _fred_observations(
    currency: str, valid: list[dict[str, object]], fetched_at: str
) -> list[RateObservation]:
    """Convert the valid FRED observations of one series (R8 boundary).

    B3: ``valid`` is the inherited sentinel-filtered list and the read is
    verbatim (d.178-179) — the newest point is ``valid[0]`` and the previous one
    ``valid[1]``; both are recorded, each with its own ``date`` as
    ``observed_at``, because §4.4 derives the trend at read time from the two
    nearest observations (the legacy collapsed the same two points into an
    inline ``trend`` field).  A value that does not read, a missing ``date``
    key or an empty date raises, so the whole currency is skipped — exactly the
    legacy control flow (its ``float(valid[1]["value"])`` raised inside the
    per-currency ``try``)."""
    observations: list[RateObservation] = []
    for row in valid[:2]:
        observed_at = str(row["date"]).strip()
        if not observed_at:
            raise ValueError(f"{currency}: FRED observation without a date")
        rate = float(row["value"])  # ném ⇒ bỏ cả currency (B3, d.178-179)
        observations.append(
            RateObservation(
                currency=currency,
                rate=rate,
                observed_at=observed_at,
                source=RateSource.FRED,
                fetched_at=fetched_at,
            )
        )
    return observations


def _rate_observations_from_html(
    rows: list[dict[str, object]], currencies: list[str], fetched_at: str
) -> list[RateObservation]:
    """Convert raw ForexFactory HTML rows into ``ff_html`` observations (R8).

    Port of the matching block of ``_update_from_forexfactory`` (d.104-131): the
    currency must be one of the currencies this round still needs, the event
    name must contain one of its ``_FOREX_RATE_EVENTS`` patterns
    (case-insensitive), the actual must be non-empty and read as a float.  The
    observation date is the day of the event's ``time_utc`` (d.130), falling
    back to the fetch day when the row carries none — both verbatim from the
    legacy.  Every matched decision is recorded (the §4.4 table stores
    observations, not one value per currency); rows that match nothing are
    dropped, never guessed."""
    today = fetched_at[:10]
    observations: list[RateObservation] = []
    for row in rows:
        currency = str(row.get("currency", "")).strip()
        if currency not in currencies:
            continue
        event_name = str(row.get("event", "")).strip().lower()
        patterns = _FOREX_RATE_EVENTS[currency]
        if not any(pattern in event_name for pattern in patterns):
            continue
        actual = str(row.get("actual", "")).strip()
        if not actual:
            continue
        rate = _parse_rate(actual)
        if rate is None:
            continue
        observed_at = str(row.get("time_utc", ""))[:10] or today
        observations.append(
            RateObservation(
                currency=currency,
                rate=rate,
                observed_at=observed_at,
                source=RateSource.FF_HTML,
                fetched_at=fetched_at,
            )
        )
    return observations


def _fallback_observed_at(entry: dict[str, object], file_last_updated: object) -> str | None:
    """Observation date of one fallback entry: its own ``_updated`` (the legacy
    ``_save_fallback``/``_fetch_from_fred`` wrote the data's date there, d.130/
    d.196), else the file-level ``_last_updated`` (d.149); ``None`` when neither
    is an ISO date — the currency is then skipped rather than dated by guesswork
    (B4/B5)."""
    for candidate in (entry.get("_updated"), file_last_updated):
        date = _as_iso_date(candidate)
        if date is not None:
            return date
    return None


def _as_iso_date(value: object) -> str | None:
    """Read a ``YYYY-MM-DD`` date (a ``_last_updated`` stamp is truncated to its
    day); anything that is not a real calendar date is ``None``."""
    text = str(value or "").strip()[:10]
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None
    return text


def _run_status(
    primary_currencies: int, scope_currencies: int, written: int
) -> IngestRunStatus:
    """Round status (contract §4.6, B4): ``ok`` only when the primary FRED
    channel covered every currency of the scope, ``partial`` when the other
    channels had to fill in, ``failed`` when the round produced nothing."""
    if primary_currencies >= scope_currencies:
        return IngestRunStatus.OK
    if written:
        return IngestRunStatus.PARTIAL
    return IngestRunStatus.FAILED


def _classify_error(exc: Exception) -> str:
    """Inherited classification for the FRED channel: a value/date that cannot
    be read is ``InvalidObservation``, anything else keeps its exception name
    (khuôn ``type(exc).__name__`` of the rss producer, contract §4.6 style)."""
    if isinstance(exc, (KeyError, TypeError, ValueError)):
        return "InvalidObservation"
    return type(exc).__name__


def _classify_html_error(exc: Exception) -> str:
    """Inherited transport classification for the HTML channel (khuôn
    ``_classify_html_error`` of ``ff_calendar_producer``): ``Http<code>`` for a
    failed response, ``UrlError`` for a connection fault, ``InvalidHtmlTable``
    when the page carried no parseable rows, otherwise the exception name."""
    if isinstance(exc, RuntimeError):
        message = str(exc)
        if message.startswith("HTTP "):
            return "Http" + message[len("HTTP ") :]
        if message.startswith("không đọc được bảng HTML"):
            return "InvalidHtmlTable"
        return "UrlError"
    return type(exc).__name__


def _describe(error: RateChannelError) -> str:
    """Compact machine-readable detail of the first round error for the
    ``ingest_runs.error_detail`` column (contract §4.6)."""
    where = f"{error.channel}/{error.currency}" if error.currency else error.channel
    return f"{where}: {error.detail}"
