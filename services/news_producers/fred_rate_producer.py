"""fred_rate_producer — policy-rate observations of the eight currencies (plan batch L2.6).

Sole owner of "thu thập lãi suất điều hành 8 đồng tiền thành ``RateObservation``"
(contract §6.3 / §11b, identity M5 — QĐ-1 phương án A, Owner duyệt 21/09/2026).
This batch absorbs ``services/interest_rate_service.py`` into a new file and
leaves the old file untouched (QĐ-1A: its rate cache keeps feeding the legacy
macro path until connect-time b): ``FRED_SERIES`` (d.17-26), ``_fetch_from_fred``
(d.155-204) and the JSON fallback ``_load_fallback`` (d.207-212).

One entry point, ``fetch_round`` = ONE refresh round = one ``ingest_runs`` row
(producer ``fred``, contract §4.6/§10).  The write destination is the only
thing that changes (plan L2.6 review point): observations go to
``NewsRepository.add_rate_observations`` — the ``interest_rates`` table keyed by
``(currency, observed_at, source)`` (§4.4) — instead of the legacy in-memory
``_CACHE`` dict plus the ``config/interest_rates.json`` write-back.

**Source chain per currency: ``fred`` → ``config_fallback``** (from đợt 3,
24/09/2026 — contract §6.3: the ForexFactory-HTML rate channel
``_update_from_forexfactory`` inherited from the legacy file was REMOVED because
Cloudflare blocks non-browser clients (§6.1 căn cứ); ``ff_html`` observations
now arise only through the human-pasted page-source channel of §6.1 bước 4).
Every currency of ``FRED_SERIES`` the primary FRED channel could not deliver is
offered to the local JSON fallback.  A currency carries exactly one source per
round.  The run status is ``ok`` when the FRED channel covered the whole scope,
``partial`` when observations were written without full primary coverage,
``failed`` when nothing was written (B4 — the status never claims a healthy
primary source it did not have).

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
* **Raw rows never leave the converters** (R8/C2): the FRED JSON observations
  are visible only inside ``_fred_observations``.
* **Deviations, plan-sanctioned (V2):** (a) transport and channel failures are
  recorded as typed errors in ``ingest_runs`` (§4.6/§10) instead of being
  swallowed by ``logger.debug``; (b) a fallback entry without any observation
  date is skipped — ``observed_at`` is NOT NULL and part of the §4.4 key, and
  no date is ever invented (B4/B5).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
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

# interest_rate_service.py:157 — endpoint FRED (nguyên văn).
FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"

# interest_rate_service.py:43 — tệp fallback cục bộ (đọc, không bao giờ ghi).
FALLBACK_FILENAME = "interest_rates.json"

# Kênh ghi = giá trị enum của §4.4 (một nguồn từ vựng duy nhất).  Kênh FF-HTML
# qua mạng đã bị gỡ (đợt 3 — chỉ đường dán mã nguồn trang của §6.1 phát sinh
# ``ff_html`` nữa, và nó đi thẳng qua repository, không qua producer này).
_CHANNEL_FRED = RateSource.FRED.value
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
    channel errors.  No raw FRED row crosses this boundary (R8)."""

    fred_observations: int
    config_fallback_observations: int
    currencies_covered: tuple[str, ...]
    run_status: IngestRunStatus
    run_id: int
    errors: tuple[RateChannelError, ...]

    @property
    def written(self) -> int:
        """Total observations handed to ``add_rate_observations`` (typed count)."""
        return self.fred_observations + self.config_fallback_observations


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
        """One refresh round over the 8 currencies: FRED, then the local JSON
        fallback (đợt 3 chain order ``fred → config_fallback`` — contract §6.3:
        the inherited ForexFactory-HTML channel was removed with the FF
        automatic channels).

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


def _describe(error: RateChannelError) -> str:
    """Compact machine-readable detail of the first round error for the
    ``ingest_runs.error_detail`` column (contract §4.6)."""
    where = f"{error.channel}/{error.currency}" if error.currency else error.channel
    return f"{where}: {error.detail}"
