"""bond_yield_producer tests (plan lô B2, contract §4.7/§6.6/§4.6).

The FRED and Yahoo transports are mocked — ``requests.get`` in the producer
namespace.  No real HTTP, no waiting and ``%APPDATA%`` is never touched: every
round runs against a throwaway temp DB and the real news migration folder.

Checklist covered here (plan B2; wave 6 §6.6):

* FRED ok -> **every** observation of the three series (``2y``/``10y``/
  ``be10y``) is written with ``source='fred'``, run ``ok`` and one
  ``ingest_runs`` row ``producer='bond_yield'`` - the wave-6 change from the
  "one row per maturity per round" rule (deliberate, §6.6 đợt 6);
* ``limit=130`` is the FRED request and a full daily history (~390 rows) is
  recorded in one round;
* FRED dead -> ``2y``/``10y`` come from Yahoo (``source='yahoo'``), every valid
  day kept (last close of a repeated day wins), ``be10y`` stays missing, run
  ``partial``;
* both channels dead -> run ``failed`` and nothing written (B4);
* a malformed FRED record is dropped (never dated/valued by guesswork) and the
  round is ``partial``;
* two rounds on the same day do not add new rows (UNIQUE §4.7; the repeat
  upserts the same keys);
* ``be10y`` never carries a Yahoo source (no fallback channel);
* the producer touches only ``bond_yields`` (never the other news tables).
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pytest

from config.paths import PROJECT_ROOT
from core.news_models import (
    BondYieldMaturity,
    BondYieldSource,
    IngestProducer,
    IngestRunStatus,
)
from core.news_policy import NewsPolicy
from services.news_producers import bond_yield_producer as bondmod
from services.news_producers.bond_yield_producer import (
    FRED_BOND_SERIES,
    FRED_HISTORY_LIMIT,
    YAHOO_BOND_TICKERS,
    BondYieldProducer,
)
from services.news_repository import NewsRepository

NEWS_MIGRATIONS_DIR = PROJECT_ROOT / "data" / "migrations" / "news"

_DGS2, _DGS10, _T10YIE = "DGS2", "DGS10", "T10YIE"
_YAHOO_2Y, _YAHOO_10Y = "2YY=F", "^TNX"


@pytest.fixture(autouse=True)
def _hermetic_transport():
    """No test may reach the network: an unmocked request raises."""
    with mock.patch.object(
        bondmod.requests,
        "get",
        side_effect=AssertionError("HTTP called without a mock"),
    ):
        yield


# ---- fixture scaffolding (temp DB + fully mocked transport) ---------------------


class _Response:
    """Minimal stand-in for a ``requests`` response (status + JSON body)."""

    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        if isinstance(self._payload, BaseException):
            raise self._payload
        return self._payload


def _fred_payload(rows: list[tuple[str, object]]) -> dict[str, object]:
    return {"observations": [{"date": date, "value": value} for date, value in rows]}


def _fred_history(base: float, count: int) -> dict[str, object]:
    """A FRED payload of ``count`` consecutive daily observations (newest first)."""
    rows = [
        ((date(2026, 9, 20) - timedelta(days=offset)).isoformat(), f"{base + offset:.2f}")
        for offset in range(count)
    ]
    return _fred_payload(rows)


def _yahoo_payload(points: list[tuple[str, float]]) -> dict[str, object]:
    timestamps = [
        int(datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
        for date, _ in points
    ]
    closes = [close for _, close in points]
    return {
        "chart": {
            "result": [
                {
                    "timestamp": timestamps,
                    "indicators": {"quote": [{"close": closes}]},
                }
            ]
        }
    }


_FRED_OK = {
    _DGS2: _fred_payload([("2026-09-20", "4.50"), ("2026-09-19", "4.40")]),
    _DGS10: _fred_payload([("2026-09-20", "4.20"), ("2026-09-19", "4.10")]),
    _T10YIE: _fred_payload([("2026-09-20", "2.30"), ("2026-09-19", "2.20")]),
}

_YAHOO_OK = {
    _YAHOO_2Y: _yahoo_payload([("2026-09-20", 4.45)]),
    _YAHOO_10Y: _yahoo_payload([("2026-09-20", 4.15)]),
}


def _mock(fred=None, yahoo=None):
    """Mock ``requests.get`` in the producer namespace.  ``fred``/``yahoo`` map a
    series id / ticker to a payload dict, a status code or an exception to
    raise; a key absent from the spec returns an empty payload."""
    calls: list[dict[str, object]] = []

    def fake_get(url, params=None, timeout=None, headers=None):
        params = dict(params or {})
        calls.append({"url": url, "params": params, "timeout": timeout})
        if url == bondmod.FRED_OBSERVATIONS_URL:
            spec = fred or {}
            item = spec.get(str(params.get("series_id", "")))
            if item is None:
                return _Response(200, {"observations": []})
        else:
            ticker = str(url).rsplit("/", 1)[-1]
            spec = yahoo or {}
            item = spec.get(ticker)
            if item is None:
                return _Response(200, {"chart": {"result": []}})
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, int):
            return _Response(item, {})
        return _Response(200, item)

    return fake_get, calls


def _policy(**overrides) -> NewsPolicy:
    data: dict[str, object] = {
        "policy_version": "news-policy",
        "rss_poll_interval_minutes": 15,
        "rss_window_hours": 24,
        "fred_refresh_hours": 6,
        "bond_yield_refresh_hours": 6,
        "event_stale_grace_minutes": 15,
        "ingest_freshness_hours": 2,
        "event_freshness_hours": 24,
        "event_coverage_hours": 24,
        "ingest_runs_retention_days": 30,
        "ai_window_days": 7,
        "ai_horizon_windows": {
            "short": {"days": 7},
            "mid": {"days": 42},
            "long": {"days": 180},
        },
        "ai_long_window_max_rows": 50,
        "ai_min_items": 3,
        "ai_horizons": {
            "short": {"unit": "day", "min": 0, "max": 3},
            "mid": {"unit": "week", "min": 1, "max": 4},
            "long": {"unit": "month", "min": 1, "max": 6},
        },
    }
    data.update(overrides)
    return NewsPolicy.from_dict(data)


def _repo(tmp_path: Path) -> NewsRepository:
    return NewsRepository(
        db_path=tmp_path / "news.db", migrations_dir=NEWS_MIGRATIONS_DIR
    )


def _producer(
    tmp_path: Path,
    *,
    api_key: str | None = "test-key",
    policy: NewsPolicy | None = None,
) -> BondYieldProducer:
    return BondYieldProducer(
        _repo(tmp_path),
        policy if policy is not None else _policy(),
        api_key=api_key,
    )


def _rows(db_path: Path, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


# ---- tests ----------------------------------------------------------------------


class TestFredPrimary:
    def test_fred_ok_writes_every_observation_of_each_series(self, tmp_path):
        # Wave 6 (§6.6 đợt 6) deliberate change: the whole history of each
        # series is recorded, not only its newest reading.
        producer = _producer(tmp_path)
        fake, calls = _mock(fred=_FRED_OK, yahoo=_YAHOO_OK)

        with mock.patch.object(bondmod.requests, "get", fake):
            result = producer.fetch_round()

        assert result.run_status is IngestRunStatus.OK
        assert result.fred_observations == 6
        assert result.yahoo_observations == 0
        assert result.written == 6
        assert result.maturities_covered == ("USD:10y", "USD:2y", "USD:be10y")
        assert result.errors == ()

        rows = _rows(
            producer._repo.db_path,
            "SELECT maturity, source, value, observed_at FROM bond_yields "
            "ORDER BY maturity, observed_at",
        )
        assert [
            (r["maturity"], r["source"], r["value"], r["observed_at"]) for r in rows
        ] == [
            ("10y", "fred", 4.10, "2026-09-19"),
            ("10y", "fred", 4.20, "2026-09-20"),
            ("2y", "fred", 4.40, "2026-09-19"),
            ("2y", "fred", 4.50, "2026-09-20"),
            ("be10y", "fred", 2.20, "2026-09-19"),
            ("be10y", "fred", 2.30, "2026-09-20"),
        ]
        # no Yahoo request was made: FRED covered the whole scope
        assert all(c["url"] == bondmod.FRED_OBSERVATIONS_URL for c in calls)
        # the FRED request carries the wave-6 history limit (source config, §6.6)
        assert all(c["params"].get("limit") == FRED_HISTORY_LIMIT for c in calls)

    def test_fred_limit_130_records_the_whole_daily_history(self, tmp_path):
        producer = _producer(tmp_path)
        fred = {
            _DGS2: _fred_history(4.00, 130),
            _DGS10: _fred_history(4.20, 130),
            _T10YIE: _fred_history(2.30, 130),
        }
        fake, _ = _mock(fred=fred, yahoo=_YAHOO_OK)

        with mock.patch.object(bondmod.requests, "get", fake):
            result = producer.fetch_round()

        assert result.run_status is IngestRunStatus.OK
        assert result.fred_observations == 390
        assert result.written == 390
        per_maturity = _rows(
            producer._repo.db_path,
            "SELECT maturity, COUNT(*) AS n FROM bond_yields GROUP BY maturity",
        )
        assert {r["maturity"]: r["n"] for r in per_maturity} == {
            "2y": 130,
            "10y": 130,
            "be10y": 130,
        }

    def test_run_row_is_logged_with_the_bond_yield_producer(self, tmp_path):
        producer = _producer(tmp_path)
        fake, _ = _mock(fred=_FRED_OK, yahoo=_YAHOO_OK)

        with mock.patch.object(bondmod.requests, "get", fake):
            result = producer.fetch_round()

        runs = _rows(producer._repo.db_path, "SELECT * FROM ingest_runs")
        assert len(runs) == 1
        assert runs[0]["producer"] == IngestProducer.BOND_YIELD.value
        assert runs[0]["status"] == "ok"
        assert runs[0]["items_written"] == 6
        assert result.run_id == runs[0]["id"]

    def test_two_rounds_same_day_do_not_add_new_rows(self, tmp_path):
        producer = _producer(tmp_path)
        fake, _ = _mock(fred=_FRED_OK, yahoo=_YAHOO_OK)

        with mock.patch.object(bondmod.requests, "get", fake):
            first = producer.fetch_round()
            second = producer.fetch_round()

        # items_written counts the upserted rows; the UNIQUE key means the
        # repeat round adds no NEW row (DB count unchanged).
        assert first.written == 6
        assert second.written == 6
        rows = _rows(producer._repo.db_path, "SELECT COUNT(*) AS n FROM bond_yields")
        assert rows[0]["n"] == 6

    def test_producer_touches_only_bond_yields(self, tmp_path):
        producer = _producer(tmp_path)
        fake, _ = _mock(fred=_FRED_OK, yahoo=_YAHOO_OK)

        with mock.patch.object(bondmod.requests, "get", fake):
            producer.fetch_round()

        for table in ("interest_rates", "news_events", "news_items"):
            rows = _rows(producer._repo.db_path, f"SELECT COUNT(*) AS n FROM {table}")
            assert rows[0]["n"] == 0

    def test_missing_api_key_falls_back_to_yahoo(self, tmp_path):
        producer = _producer(tmp_path, api_key=None)
        fake, _ = _mock(fred=_FRED_OK, yahoo=_YAHOO_OK)

        with mock.patch.object(bondmod.requests, "get", fake):
            result = producer.fetch_round()

        # FRED skipped wholesale (NoApiKey) -> Yahoo fills 2y/10y, be10y missing
        assert result.fred_observations == 0
        assert result.run_status is IngestRunStatus.PARTIAL
        assert result.errors[0].error_type == "NoApiKey"


class TestYahooFallback:
    def test_fred_down_uses_yahoo_for_two_and_ten_year(self, tmp_path):
        producer = _producer(tmp_path)
        fred_down = {series: RuntimeError("FRED down") for series in FRED_BOND_SERIES.values()}
        fake, _ = _mock(fred=fred_down, yahoo=_YAHOO_OK)

        with mock.patch.object(bondmod.requests, "get", fake):
            result = producer.fetch_round()

        assert result.fred_observations == 0
        assert result.yahoo_observations == 2
        assert result.run_status is IngestRunStatus.PARTIAL

        rows = _rows(
            producer._repo.db_path,
            "SELECT maturity, source FROM bond_yields ORDER BY maturity",
        )
        assert [(r["maturity"], r["source"]) for r in rows] == [
            ("10y", "yahoo"),
            ("2y", "yahoo"),
        ]
        # be10y has no fallback channel -> absent
        assert all(r["maturity"] != "be10y" for r in rows)

    def test_yahoo_records_every_valid_day_of_the_range(self, tmp_path):
        # Wave 6 (§6.6 đợt 6): range=1y, every valid close kept per day.
        producer = _producer(tmp_path)
        fred_down = {series: RuntimeError("FRED down") for series in FRED_BOND_SERIES.values()}
        yahoo = {
            _YAHOO_2Y: _yahoo_payload(
                [("2026-09-18", 4.40), ("2026-09-19", 4.42), ("2026-09-20", 4.45)]
            ),
            _YAHOO_10Y: _yahoo_payload([("2026-09-20", 4.15)]),
        }
        fake, calls = _mock(fred=fred_down, yahoo=yahoo)

        with mock.patch.object(bondmod.requests, "get", fake):
            result = producer.fetch_round()

        assert result.yahoo_observations == 4
        rows = _rows(
            producer._repo.db_path,
            "SELECT observed_at FROM bond_yields WHERE maturity='2y' "
            "ORDER BY observed_at",
        )
        assert [r["observed_at"] for r in rows] == [
            "2026-09-18",
            "2026-09-19",
            "2026-09-20",
        ]
        # the Yahoo request carries the wave-6 range (source config, §6.6)
        assert all(
            c["params"].get("range") == "1y"
            for c in calls
            if c["url"] != bondmod.FRED_OBSERVATIONS_URL
        )

    def test_yahoo_same_day_multiple_closes_keeps_the_last(self, tmp_path):
        producer = _producer(tmp_path)
        fred_down = {series: RuntimeError("FRED down") for series in FRED_BOND_SERIES.values()}
        yahoo = {
            _YAHOO_2Y: _yahoo_payload([("2026-09-20", 4.40), ("2026-09-20", 4.99)]),
            _YAHOO_10Y: _yahoo_payload([("2026-09-20", 4.15)]),
        }
        fake, _ = _mock(fred=fred_down, yahoo=yahoo)

        with mock.patch.object(bondmod.requests, "get", fake):
            producer.fetch_round()

        rows = _rows(
            producer._repo.db_path,
            "SELECT value, observed_at FROM bond_yields WHERE maturity='2y'",
        )
        assert len(rows) == 1
        assert rows[0]["value"] == 4.99  # last close of the repeated day wins

    def test_be10y_is_never_sourced_from_yahoo(self, tmp_path):
        # Structural guarantee: the ticker map has no be10y entry.
        assert all(
            maturity != BondYieldMaturity.BREAKEVEN_10Y.value
            for _, maturity in YAHOO_BOND_TICKERS
        )
        producer = _producer(tmp_path)
        fred_down = {series: RuntimeError("FRED down") for series in FRED_BOND_SERIES.values()}
        fake, _ = _mock(fred=fred_down, yahoo=_YAHOO_OK)

        with mock.patch.object(bondmod.requests, "get", fake):
            producer.fetch_round()

        rows = _rows(
            producer._repo.db_path,
            "SELECT source FROM bond_yields WHERE maturity='be10y'",
        )
        assert rows == []

    def test_malformed_fred_record_is_dropped_and_round_is_partial(self, tmp_path):
        producer = _producer(tmp_path)
        fred = dict(_FRED_OK)
        # DGS2's only record has no date -> dropped, never dated by guesswork
        fred[_DGS2] = _fred_payload([("", "4.50")])
        fake, _ = _mock(fred=fred, yahoo=_YAHOO_OK)

        with mock.patch.object(bondmod.requests, "get", fake):
            result = producer.fetch_round()

        assert result.run_status is IngestRunStatus.PARTIAL
        rows = _rows(
            producer._repo.db_path,
            "SELECT maturity, source, observed_at FROM bond_yields ORDER BY maturity",
        )
        assert all(r["observed_at"] != "" for r in rows)
        two_year = next(r for r in rows if r["maturity"] == "2y")
        assert two_year["source"] == "yahoo"  # FRED record unusable -> fallback
        assert any(e.error_type == "InvalidObservation" for e in result.errors)

    def test_unreadable_fred_value_is_dropped(self, tmp_path):
        producer = _producer(tmp_path)
        fred = dict(_FRED_OK)
        fred[_DGS10] = _fred_payload([("2026-09-20", "not-a-number")])
        fake, _ = _mock(fred=fred, yahoo=_YAHOO_OK)

        with mock.patch.object(bondmod.requests, "get", fake):
            result = producer.fetch_round()

        rows = _rows(
            producer._repo.db_path,
            "SELECT source FROM bond_yields WHERE maturity='10y'",
        )
        assert rows[0]["source"] == "yahoo"
        assert result.run_status is IngestRunStatus.PARTIAL


class TestBothChannelsDown:
    def test_all_channels_dead_is_failed_and_writes_nothing(self, tmp_path):
        producer = _producer(tmp_path)
        dead = RuntimeError("channel down")
        fred_down = {series: dead for series in FRED_BOND_SERIES.values()}
        yahoo_down = {ticker: dead for ticker in YAHOO_BOND_TICKERS.values()}
        fake, _ = _mock(fred=fred_down, yahoo=yahoo_down)

        with mock.patch.object(bondmod.requests, "get", fake):
            result = producer.fetch_round()

        assert result.run_status is IngestRunStatus.FAILED
        assert result.written == 0
        assert _rows(producer._repo.db_path, "SELECT COUNT(*) AS n FROM bond_yields")[0]["n"] == 0
        runs = _rows(producer._repo.db_path, "SELECT * FROM ingest_runs")
        assert runs[0]["status"] == "failed"
        assert runs[0]["error_type"] is not None


class TestPolicyCadence:
    def test_refresh_hours_comes_from_the_bond_yield_policy_key(self, tmp_path):
        producer = _producer(tmp_path, policy=_policy(bond_yield_refresh_hours=9))
        assert producer.refresh_hours == 9
