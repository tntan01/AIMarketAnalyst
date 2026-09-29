"""bond_yield_producer - bond-yield observations of the covered currencies
(plan batch B2, contract sections 4.7/6.6).

Sole owner of "thu thập lợi suất trái phiếu 2 năm/10 năm + breakeven 10 năm
thành ``BondYieldObservation``" (contract §6.6 / §11b, identity M5, đợt 5 -
Owner duyệt 28/09/2026).  One entry point, ``fetch_round`` = ONE refresh round =
one ``ingest_runs`` row (producer ``bond_yield``, §4.6).  Observations go to
``NewsRepository.add_bond_observations`` - the ``bond_yields`` table keyed by
``(currency, maturity, observed_at, source)`` (§4.7).

**Source chain per maturity: ``fred`` -> ``yahoo`` fallback** (contract §6.6):
FRED series ``DGS2``/``DGS10``/``T10YIE`` are the primary channel; when FRED
cannot deliver a maturity the Yahoo tickers ``2YY=F`` (2y) / ``^TNX`` (10y)
fill in.  ``be10y`` has NO fallback channel (only FRED).  A maturity keeps
exactly one source per round - the primary FRED reading wins, the Yahoo one is
used only for a maturity FRED did not cover.  Run status is ``ok`` when FRED
covered the whole scope (three maturities), ``partial`` when observations were
written without full primary coverage, ``failed`` when nothing was written
(B4 - the status never claims a healthy primary source it did not have).

Scope of phase 1 is **USD only** (contract §6.6, §13 đợt 5): extending to other
currencies needs an Owner-approved FRED series catalogue, so no series is
invented (B5).

Trend/delta/spread/real yield are NEVER derived here (§6.6/§11b:
``core/yield_context.py`` owns the derivation and the consumer calls
``NewsRepository.latest_bond_yields``).  **Wave 6 (§6.6 đợt 6):** each round
fetches and records the **whole history** the source returns - FRED
``limit=130`` and Yahoo ``range=1y`` - one row per observation date, not only
the newest reading.  The read-time derivation then has the depth for the
3-month/6-month deltas within the very first round, instead of waiting for the
history to accumulate across rounds.  The database UNIQUE key
``(currency, maturity, observed_at, source)`` deduplicates across rounds; this
producer computes no delta itself.

Governance:

* **No timer, no in-memory cache.**  The cadence key
  ``bond_yield_refresh_hours`` is the single owner of the frequency (R4 - never
  hard-coded in logic) and the timer belongs to the B2 worker.  ``refresh_hours``
  exposes that key; a round is never suppressed by wall-clock time.
* **Raw rows never leave the converters** (R8/C2): the FRED JSON observations
  and the Yahoo chart payload are visible only inside ``_fred_observations`` /
  ``_yahoo_observations``.
* **Yahoo transport copied, not imported** (B7 §3.1, plan §6 risk 3): the
  minimal chart request of ``services/market_data_service._fetch_via_requests``
  is reproduced here (same endpoint, params, user-agent, one 429 retry) with the
  same tickers ``2YY=F``/``^TNX`` - ``market_data_service`` is read-only
  reference and is never imported into the news data path.
* **No fabricated reading (B4/B5).**  A malformed row (missing date, unreadable
  or non-finite value) is dropped with a typed error - never dated or valued by
  guesswork - and a maturity that ends with no usable observation makes the
  round ``partial`` (or ``failed`` when nothing at all was written).
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import requests

from core.news_models import (
    BondYieldMaturity,
    BondYieldObservation,
    BondYieldSource,
    IngestProducer,
    IngestRun,
    IngestRunStatus,
)
from core.news_policy import NewsPolicy, load_news_policy
from services.news_producers.fred_rate_producer import FRED_OBSERVATIONS_URL
from services.news_repository import NewsRepository

__all__ = [
    "FRED_BOND_SERIES",
    "YAHOO_BOND_TICKERS",
    "BondYieldChannelError",
    "BondYieldFetchResult",
    "BondYieldProducer",
]


# ---------------------------------------------------------------------------
# Inherited runtime data (B5: kế thừa runtime hiện hành - không bịa)
# ---------------------------------------------------------------------------

# FRED series per (currency, maturity) - contract §6.6, the DGS2/DGS10/T10YIE
# verbatim identifiers (phase 1 covers USD only).
FRED_BOND_SERIES: dict[tuple[str, str], str] = {
    ("USD", BondYieldMaturity.TWO_YEAR.value): "DGS2",
    ("USD", BondYieldMaturity.TEN_YEAR.value): "DGS10",
    ("USD", BondYieldMaturity.BREAKEVEN_10Y.value): "T10YIE",
}

# Source configuration fixed by the contract, NOT a section 7 policy key:
# FRED ``limit=130`` daily observations, so one round records ~6 months of daily
# history - the depth the 3-month/6-month yield deltas of §9.1 need from the
# first round (contract §6.6 đợt 6).  Endpoint/params stay the inherited
# ``fred_rate_producer`` ones; only the limit changes.
FRED_HISTORY_LIMIT = 130

# Yahoo fallback tickers per (currency, maturity) - inherited verbatim from the
# running ``market_data_service`` (``US2Y``: "2YY=F", ``US10Y``: "^TNX",
# services/market_data_service.py:20-21).  ``be10y`` deliberately absent: the
# breakeven has no fallback channel (§6.6).
YAHOO_BOND_TICKERS: dict[tuple[str, str], str] = {
    ("USD", BondYieldMaturity.TWO_YEAR.value): "2YY=F",
    ("USD", BondYieldMaturity.TEN_YEAR.value): "^TNX",
}

# Yahoo Finance chart endpoint - the inherited transport of
# ``market_data_service._fetch_via_requests`` (services/market_data_service.py:68).
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
# Yahoo ``range=1y`` (contract §6.6 đợt 6 - the same no-policy-key source
# configuration as ``FRED_HISTORY_LIMIT``); the endpoint/params are the
# inherited ``market_data_service`` ones, only the range changes.
YAHOO_RANGE = "1y"
YAHOO_INTERVAL = "1d"
YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0"}

# Channel names = the §4.7 source enum values (single vocabulary source).
_CHANNEL_FRED = BondYieldSource.FRED.value
_CHANNEL_YAHOO = BondYieldSource.YAHOO.value


# ---------------------------------------------------------------------------
# Typed results (C3 - không dict trần qua ranh giới)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BondYieldChannelError:
    """One typed failure of a bond-yield round (contract §4.6 style: the
    channel name plus the inherited transport classification -
    ``Http<code>``/``UrlError``/``InvalidYahooStructure``/``InvalidObservation``/
    ``NoObservations``/``NoApiKey``).

    ``maturity`` is empty for a channel-wide failure and one of the §4.7
    maturities otherwise."""

    channel: str
    maturity: str
    error_type: str
    detail: str


@dataclass(frozen=True, slots=True)
class BondYieldFetchResult:
    """Typed outcome of one bond-yield refresh round (contract §6.6/§4.6).

    Per-source observation counts (never a bare dict, C3), the maturities the
    FRED primary channel covered, the run status logged into ``ingest_runs``
    and the typed channel errors.  No raw FRED/Yahoo row crosses this boundary
    (R8)."""

    fred_observations: int
    yahoo_observations: int
    maturities_covered: tuple[str, ...]
    run_status: IngestRunStatus
    run_id: int
    errors: tuple[BondYieldChannelError, ...]

    @property
    def written(self) -> int:
        """Total observations handed to ``add_bond_observations`` (typed count)."""
        return self.fred_observations + self.yahoo_observations


class BondYieldProducer:
    """Sole owner of collecting bond-yield observations into
    ``BondYieldObservation`` (M5, contract §6.6)."""

    def __init__(
        self,
        repo: NewsRepository,
        policy: NewsPolicy | None = None,
        api_key: str | None = None,
    ) -> None:
        self._repo = repo
        # Injected for testability; loaded fail-closed when absent (R4 - the
        # cadence key lives in config/news_policy.json, never in this file).
        self._policy = policy if policy is not None else load_news_policy()
        # The FRED key is passed in by the caller (khuôn ``fred_rate_producer``:
        # DI is the controller's job - no settings read here).
        self._api_key = api_key

    @property
    def refresh_hours(self) -> int:
        """The bond-yield refresh cadence, read from the policy key
        ``bond_yield_refresh_hours`` (contract §7, R4).

        Exposed for the worker that owns the timer; this producer never
        schedules itself and never suppresses a round by wall-clock time."""
        return self._policy.bond_yield_refresh_hours

    # --- public round (contract §6.6, plan B2) -----------------------------------

    def fetch_round(self) -> BondYieldFetchResult:
        """One refresh round over the covered maturities: FRED first, Yahoo
        fallback for a maturity FRED could not deliver (contract §6.6).

        Every observation of the round is written through
        ``NewsRepository.add_bond_observations`` (§4.7 - a duplicate
        ``(currency, maturity, observed_at, source)`` overwrites instead of
        duplicating), and exactly one ``ingest_runs`` row (producer
        ``bond_yield``) is logged (§4.6/§10), including a round that wrote
        nothing.  Channels never retry beyond the inherited single shot
        (Yahoo keeps the inherited one 429 retry)."""
        fetched_at = _utc_now()
        errors: list[BondYieldChannelError] = []

        fred_observations: list[BondYieldObservation] = []
        primary_maturities: set[tuple[str, str]] = set()
        for (currency, maturity), series_id in FRED_BOND_SERIES.items():
            observations, series_errors = self._fetch_fred_series(
                currency, maturity, series_id, fetched_at
            )
            errors.extend(series_errors)
            fred_observations.extend(observations)
            if observations:
                primary_maturities.add((currency, maturity))

        yahoo_observations: list[BondYieldObservation] = []
        for (currency, maturity), ticker in YAHOO_BOND_TICKERS.items():
            if (currency, maturity) in primary_maturities:
                continue
            observations, series_errors = self._fetch_yahoo_series(
                currency, maturity, ticker, fetched_at
            )
            errors.extend(series_errors)
            yahoo_observations.extend(observations)

        fred_observations = _dedupe(fred_observations)
        yahoo_observations = _dedupe(yahoo_observations)
        observations = [*fred_observations, *yahoo_observations]
        written = self._repo.add_bond_observations(observations)

        run_status = _run_status(
            len(primary_maturities), len(FRED_BOND_SERIES), written
        )
        first_error = errors[0] if errors else None
        run_id = self._repo.record_run(
            IngestRun(
                producer=IngestProducer.BOND_YIELD,
                started_at=fetched_at,
                finished_at=_utc_now(),
                status=run_status,
                items_written=written,
                error_type=first_error.error_type if first_error else None,
                error_detail=_describe(first_error) if first_error else None,
            )
        )
        return BondYieldFetchResult(
            fred_observations=len(fred_observations),
            yahoo_observations=len(yahoo_observations),
            maturities_covered=tuple(
                sorted(f"{currency}:{maturity}" for currency, maturity in primary_maturities)
            ),
            run_status=run_status,
            run_id=run_id,
            errors=tuple(errors),
        )

    # --- FRED channel (khuôn fred_rate_producer._fetch_from_fred) ----------------

    def _fetch_fred_series(
        self, currency: str, maturity: str, series_id: str, fetched_at: str
    ) -> tuple[list[BondYieldObservation], list[BondYieldChannelError]]:
        """Fetch the history of one FRED series.

        Inherited transport (khuôn ``fred_rate_producer``): ``requests.get`` on
        the observations endpoint with ``series_id``/``api_key``/
        ``file_type=json``/``sort_order=desc``/``limit=FRED_HISTORY_LIMIT``/
        ``timeout=5``; a non-200 response or an exception fails that maturity
        alone.  Sentinel values (``"."``) are filtered out before anything is
        read from the payload; every valid observation is recorded with its own
        ``date`` as ``observed_at`` (§4.7/§6.6 đợt 6)."""
        if not self._api_key:
            return [], [
                BondYieldChannelError(
                    _CHANNEL_FRED,
                    maturity,
                    "NoApiKey",
                    f"{series_id}: no FRED API key configured",
                )
            ]

        try:
            response = requests.get(
                FRED_OBSERVATIONS_URL,
                params={
                    "series_id": series_id,
                    "api_key": self._api_key,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": FRED_HISTORY_LIMIT,
                },
                timeout=5,
            )
            if response.status_code != 200:
                return [], [
                    BondYieldChannelError(
                        _CHANNEL_FRED,
                        maturity,
                        f"Http{response.status_code}",
                        f"{series_id}: HTTP {response.status_code}",
                    )
                ]
            payload = response.json().get("observations", [])
            valid = [row for row in payload if row.get("value", ".") != "."]
            if not valid:
                return [], [
                    BondYieldChannelError(
                        _CHANNEL_FRED,
                        maturity,
                        "NoObservations",
                        f"{series_id}: no usable observation",
                    )
                ]
            return _fred_observations(currency, maturity, valid, fetched_at)
        except Exception as exc:  # transport/data fault - maturity fails alone
            return [], [
                BondYieldChannelError(
                    _CHANNEL_FRED,
                    maturity,
                    _classify_error(exc),
                    f"{series_id}: {exc}",
                )
            ]

    # --- Yahoo fallback channel (converter at the boundary, B7 §3.1) -------------

    def _fetch_yahoo_series(
        self, currency: str, maturity: str, ticker: str, fetched_at: str
    ) -> tuple[list[BondYieldObservation], list[BondYieldChannelError]]:
        """Fetch the Yahoo Finance history of one fallback ticker.

        Transport copied from ``services/market_data_service._fetch_via_requests``
        (same chart endpoint, ``interval=1d``/``range=YAHOO_RANGE`` (1 year),
        user-agent and the inherited single 429 retry) with the inherited
        tickers - the service is never imported into the news data path
        (B7 §3.1).  Raw payload stays in ``_yahoo_observations`` (R8)."""
        try:
            response = requests.get(
                YAHOO_CHART_URL.format(ticker=ticker),
                params={"interval": YAHOO_INTERVAL, "range": YAHOO_RANGE},
                headers=YAHOO_HEADERS,
                timeout=10,
            )
            if response.status_code == 429:
                time.sleep(2)
                response = requests.get(
                    YAHOO_CHART_URL.format(ticker=ticker),
                    params={"interval": YAHOO_INTERVAL, "range": YAHOO_RANGE},
                    headers=YAHOO_HEADERS,
                    timeout=10,
                )
            if response.status_code != 200:
                return [], [
                    BondYieldChannelError(
                        _CHANNEL_YAHOO,
                        maturity,
                        f"Http{response.status_code}",
                        f"{ticker}: HTTP {response.status_code}",
                    )
                ]
            return _yahoo_observations(currency, maturity, response.json(), fetched_at)
        except Exception as exc:  # transport/data fault - maturity fails alone
            return [], [
                BondYieldChannelError(
                    _CHANNEL_YAHOO,
                    maturity,
                    _classify_error(exc),
                    f"{ticker}: {exc}",
                )
            ]


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    """Current UTC time in the khuôn ISO-8601 form: ``YYYY-MM-DDTHH:MM:SSZ``."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _dedupe(
    observations: list[BondYieldObservation],
) -> list[BondYieldObservation]:
    """Collapse observations that share the §4.7 key
    ``(currency, maturity, observed_at, source)`` - first one wins, order
    preserved.  The write count of the round must stay the number of rows
    actually written (§4.6)."""
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[BondYieldObservation] = []
    for observation in observations:
        key = (
            observation.currency,
            observation.maturity.value,
            observation.observed_at,
            observation.source.value,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(observation)
    return unique


def _finite_value(raw: object) -> float | None:
    """Read a finite float; an unreadable or non-finite value is ``None`` (the
    record is then dropped rather than written with a fabricated number)."""
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _fred_observations(
    currency: str, maturity: str, valid: list[dict[str, object]], fetched_at: str
) -> tuple[list[BondYieldObservation], list[BondYieldChannelError]]:
    """Convert every valid FRED observation of one series (R8 boundary).

    Wave 6 (§6.6 đợt 6): the whole history fetched in the round is recorded -
    one row per observation date - not only the newest reading.  A record whose
    ``date`` is missing/empty or whose value cannot be read as a finite number is
    dropped with a typed ``InvalidObservation`` error; the remaining records are
    still kept (a bad row never discards the good ones).  Only when no record
    survives is a ``NoObservations`` error reported, so the maturity falls to the
    fallback (or stays uncovered) and the round cannot claim a primary source it
    lacks."""
    observations: list[BondYieldObservation] = []
    errors: list[BondYieldChannelError] = []
    for row in valid:
        observed_at = str(row.get("date", "")).strip()
        if not observed_at:
            errors.append(
                BondYieldChannelError(
                    _CHANNEL_FRED,
                    maturity,
                    "InvalidObservation",
                    f"{currency}:{maturity}: FRED observation without a date",
                )
            )
            continue
        value = _finite_value(row.get("value"))
        if value is None:
            errors.append(
                BondYieldChannelError(
                    _CHANNEL_FRED,
                    maturity,
                    "InvalidObservation",
                    f"{currency}:{maturity}: unreadable FRED value",
                )
            )
            continue
        observations.append(
            BondYieldObservation(
                currency=currency,
                maturity=BondYieldMaturity(maturity),
                value=value,
                observed_at=observed_at,
                source=BondYieldSource.FRED,
                fetched_at=fetched_at,
            )
        )
    if not observations:
        errors.append(
            BondYieldChannelError(
                _CHANNEL_FRED,
                maturity,
                "NoObservations",
                f"{currency}:{maturity}: no usable FRED observation",
            )
        )
    return observations, errors


def _yahoo_observations(
    currency: str,
    maturity: str,
    payload: object,
    fetched_at: str,
) -> tuple[list[BondYieldObservation], list[BondYieldChannelError]]:
    """Convert a Yahoo chart payload into one observation per valid day (R8).

    The inherited chart shape is read (``chart.result[0].timestamp`` paired
    with ``indicators.quote[0].close``); ``None``/unreadable closes are skipped
    and a close is dated by its UTC calendar day.  Wave 6 (§6.6 đợt 6): every
    valid day is kept - not only the newest close - and when a day carries
    several closes the last one of that day wins.  A payload without any usable
    close is a typed ``NoObservations``/``InvalidYahooStructure`` error - no
    reading is invented (B4)."""
    if not isinstance(payload, dict):
        return [], [
            BondYieldChannelError(
                _CHANNEL_YAHOO,
                maturity,
                "InvalidYahooStructure",
                f"{currency}:{maturity}: Yahoo payload is not an object",
            )
        ]
    result = payload.get("chart", {}).get("result", [])
    if not isinstance(result, list) or not result:
        return [], [
            BondYieldChannelError(
                _CHANNEL_YAHOO,
                maturity,
                "NoObservations",
                f"{currency}:{maturity}: empty Yahoo chart result",
            )
        ]
    timestamps = result[0].get("timestamp", [])
    quotes = result[0].get("indicators", {}).get("quote", [])
    if not quotes or not timestamps:
        return [], [
            BondYieldChannelError(
                _CHANNEL_YAHOO,
                maturity,
                "NoObservations",
                f"{currency}:{maturity}: Yahoo chart without quotes",
            )
        ]
    closes = quotes[0].get("close", [])
    by_day: dict[str, BondYieldObservation] = {}
    errors: list[BondYieldChannelError] = []
    for index, timestamp in enumerate(timestamps):
        close = closes[index] if index < len(closes) else None
        if close is None:
            continue
        value = _finite_value(close)
        if value is None:
            errors.append(
                BondYieldChannelError(
                    _CHANNEL_YAHOO,
                    maturity,
                    "InvalidObservation",
                    f"{currency}:{maturity}: unreadable Yahoo close",
                )
            )
            continue
        try:
            observed_at = datetime.fromtimestamp(
                float(timestamp), tz=timezone.utc
            ).strftime("%Y-%m-%d")
        except (TypeError, ValueError, OverflowError, OSError):
            errors.append(
                BondYieldChannelError(
                    _CHANNEL_YAHOO,
                    maturity,
                    "InvalidObservation",
                    f"{currency}:{maturity}: unreadable Yahoo timestamp",
                )
            )
            continue
        # Several bars of one day -> the last close of that day wins.
        by_day[observed_at] = BondYieldObservation(
            currency=currency,
            maturity=BondYieldMaturity(maturity),
            value=value,
            observed_at=observed_at,
            source=BondYieldSource.YAHOO,
            fetched_at=fetched_at,
        )
    if not by_day:
        errors.append(
            BondYieldChannelError(
                _CHANNEL_YAHOO,
                maturity,
                "NoObservations",
                f"{currency}:{maturity}: no usable Yahoo close",
            )
        )
        return [], errors
    observations = sorted(by_day.values(), key=lambda obs: obs.observed_at)
    return observations, errors


def _run_status(
    primary_maturities: int, scope_maturities: int, written: int
) -> IngestRunStatus:
    """Round status (contract §4.6, B4): ``ok`` only when the primary FRED
    channel covered every maturity of the scope, ``partial`` when the fallback
    had to fill in, ``failed`` when the round produced nothing."""
    if primary_maturities >= scope_maturities:
        return IngestRunStatus.OK
    if written:
        return IngestRunStatus.PARTIAL
    return IngestRunStatus.FAILED


def _classify_error(exc: Exception) -> str:
    """Inherited classification: a payload/value that cannot be read is
    ``InvalidObservation``, anything else keeps its exception name (khuôn
    ``fred_rate_producer``, contract §4.6 style)."""
    if isinstance(exc, (KeyError, TypeError, ValueError)):
        return "InvalidObservation"
    return type(exc).__name__


def _describe(error: BondYieldChannelError) -> str:
    """Compact machine-readable detail of the first round error for the
    ``ingest_runs.error_detail`` column (contract §4.6)."""
    where = f"{error.channel}/{error.maturity}" if error.maturity else error.channel
    return f"{where}: {error.detail}"
