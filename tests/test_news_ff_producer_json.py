"""ff_calendar_producer JSON-channel tests (plan lô L2.3, contract §6.1/§4.6).

Behavioral parity with the inherited runtime (B3): the transport retry/backoff/
UA/timeout is ported verbatim from ``forex_factory_client.py`` and every test
mocks the network entirely (no real HTTP) and the backoff sleep entirely (no
real waiting).  Fixture payloads keep the old shape seen by
``test_forex_factory_client.py`` (``country``/``date``/``title``/``impact``/
``forecast``/``previous``).  The DB is a throwaway temp DB — ``%APPDATA%`` is
never touched.
"""

from __future__ import annotations

import io
import json
import sqlite3
from pathlib import Path
from unittest import mock

from urllib.error import HTTPError, URLError

from config.paths import PROJECT_ROOT
from core.news_models import (
    EventImpact,
    EventSource,
    EventStatus,
    IngestProducer,
    IngestRunStatus,
)
from services.news_producers import ff_calendar_producer as ffmod
from services.news_producers.ff_calendar_producer import (
    FFCalendarProducer,
    JsonCalendarFetchError,
    JsonCalendarResult,
)
from services.news_repository import NewsRepository

NEWS_MIGRATIONS_DIR = PROJECT_ROOT / "data" / "migrations" / "news"

THISWEEK_URL = FFCalendarProducer.THISWEEK_URL
NEXTWEEK_URL = FFCalendarProducer.NEXTWEEK_URL


# ---- fixture scaffolding (temp DB + fully mocked transport) ---------------------


class _FakeResponse:
    def __init__(self, raw: bytes) -> None:
        self._raw = raw

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def read(self) -> bytes:
        return self._raw


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _http(code: int) -> HTTPError:
    return HTTPError("https://nfs.faireconomy.media/x", code, "x", {}, io.BytesIO(b""))


def _repo(tmp_path: Path) -> NewsRepository:
    return NewsRepository(
        db_path=tmp_path / "news.db",
        migrations_dir=NEWS_MIGRATIONS_DIR,
    )


def _producer(tmp_path: Path) -> FFCalendarProducer:
    return FFCalendarProducer(_repo(tmp_path))


def _mock_transport(sequence: list[object]):
    """Mock ``urlopen`` and ``time.sleep`` in the producer module namespace.
    Each item is raw bytes (a response body) or an exception to raise."""
    queue = list(sequence)
    urlopen_calls: list[str] = []
    sleeps: list[float] = []

    def fake_urlopen(request, timeout=10):
        urlopen_calls.append(getattr(request, "full_url", str(request)))
        item = queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return _FakeResponse(item)

    def fake_sleep(seconds):
        sleeps.append(seconds)

    return (
        mock.patch.object(ffmod, "urlopen", fake_urlopen),
        mock.patch.object(ffmod.time, "sleep", fake_sleep),
        urlopen_calls,
        sleeps,
    )


def _read(db_path: Path, sql: str, params: tuple = ()):
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


_PAYLOAD_THIS = [
    {
        "country": "USD",
        "date": "2026-06-15T14:30:00Z",
        "title": "FOMC Meeting",
        "impact": "high",
        "forecast": "5.5%",
        "previous": "5.4%",
        "actual": "5.5%",  # kênh JSON: actual bị bỏ qua
    },
    {
        "country": "EUR",
        "date": "2026-06-16T10:00:00Z",
        "title": "Non-Economic Day",
        "impact": "holiday",
        "forecast": "",
        "previous": "2026M",
    },
    {
        "currency": "GBP",
        "date": "2026-06-15T13:00:00Z",
        "title": "CPI",
        "impact": "Medium",
        "forecast": "—",
        "previous": "2.0%",
    },
]

_PAYLOAD_NEXT = [
    {
        "country": "JPY",
        "date": "2026-06-22T09:00:00Z",
        "title": "BOJ Rate Decision",
        "impact": "medium",
        "forecast": "0.1%",
        "previous": "0.0%",
    }
]

_FETCHED_AT = "2026-06-15T00:00:00Z"


# ---- 1. converter: đủ trường (mục 3.1) -----------------------------------------


class TestConverterFields:
    def test_field_mapping_is_verbatim(self, tmp_path):
        producer = _producer(tmp_path)
        events = producer._convert_payload(_PAYLOAD_THIS, _FETCHED_AT)
        assert len(events) == 3

        fomc = events[0]
        assert fomc.day_key == "2026-06-15"
        assert fomc.event_time_utc == "2026-06-15T14:30Z"
        assert fomc.currency == "USD"
        assert fomc.title == "FOMC Meeting"
        assert fomc.impact == EventImpact.HIGH
        assert fomc.forecast == "5.5%"
        assert fomc.previous == "5.4%"
        assert fomc.actual is None  # payload có "actual" nhưng kênh JSON bỏ qua
        assert fomc.source == EventSource.FF_JSON
        assert fomc.status == EventStatus.SCHEDULED
        assert fomc.fetched_at == _FETCHED_AT
        assert json.loads(fomc.raw_json) == _PAYLOAD_THIS[0]

        non_econ = events[1]
        assert non_econ.impact == EventImpact.NON  # nhãn "holiday" -> non
        assert non_econ.forecast is None  # "": "" -> None (cột NULL)
        assert non_econ.previous == "—"  # "2026M" vô hiệu -> sentinel kế thừa giữ nguyên

        gbp = events[2]
        assert gbp.currency == "GBP"  # fallback từ khóa "currency"
        assert gbp.impact == EventImpact.MEDIUM  # "Medium" -> medium (strip+lower)
        assert gbp.forecast == "—"  # raw "—" giữ nguyên (không bịa semantics)

    def test_dedupe_is_stable_across_two_conversions(self, tmp_path):
        producer = _producer(tmp_path)
        first = producer._convert_payload(_PAYLOAD_THIS, _FETCHED_AT)
        second = producer._convert_payload(_PAYLOAD_THIS, _FETCHED_AT)
        assert [e.dedupe_key for e in first] == [e.dedupe_key for e in second]
        # cùng một dedupe phải khác nhau cho sự kiện khác nhau
        assert len({e.dedupe_key for e in first}) == 3


# ---- 2-3. transport: 429 / URLError / JSON hỏng --------------------------------


class TestTransport:
    def test_ok_both_weeks_writes_full_run(self, tmp_path):
        producer = _producer(tmp_path)
        p1, p2, calls, sleeps = _mock_transport(
            [_json_bytes(_PAYLOAD_THIS), _json_bytes(_PAYLOAD_NEXT)]
        )
        with p1, p2:
            result = producer.fetch_calendar_json()

        assert isinstance(result, JsonCalendarResult)
        assert result.inserted == 4
        assert result.updated == 0
        assert result.run_status == IngestRunStatus.OK
        assert result.run_id > 0
        assert result.feed_errors == ()
        assert calls == [THISWEEK_URL, NEXTWEEK_URL]
        assert sleeps == []

        assert _read(
            producer._repo.db_path,
            "SELECT COUNT(*) AS n FROM news_events",
        )["n"] == 4
        run = _read(
            producer._repo.db_path,
            "SELECT producer, status, items_written, error_type, error_detail "
            "FROM ingest_runs WHERE id=?",
            (result.run_id,),
        )
        assert run["producer"] == IngestProducer.FF_CRAWLER.value
        assert run["status"] == "ok"
        assert run["items_written"] == 4
        assert run["error_type"] is None
        assert run["error_detail"] is None

    def test_429_twice_then_ok_backoff_2_4(self, tmp_path):
        producer = _producer(tmp_path)
        p1, p2, _calls, sleeps = _mock_transport(
            [_http(429), _http(429), _json_bytes(_PAYLOAD_THIS), _json_bytes(_PAYLOAD_NEXT)]
        )
        with p1, p2:
            result = producer.fetch_calendar_json()
        assert result.run_status == IngestRunStatus.OK
        assert result.inserted == 4
        assert sleeps == [2.0, 4.0]

    def test_one_week_429_thrice_other_ok_partial(self, tmp_path):
        producer = _producer(tmp_path)
        p1, p2, _calls, sleeps = _mock_transport(
            [_http(429), _http(429), _http(429), _json_bytes(_PAYLOAD_NEXT)]
        )
        with p1, p2:
            result = producer.fetch_calendar_json()
        assert result.run_status == IngestRunStatus.PARTIAL
        assert result.inserted == 1
        assert len(result.feed_errors) == 1
        err = result.feed_errors[0]
        assert isinstance(err, JsonCalendarFetchError)
        assert err.feed == "thisweek"
        assert err.error_type == "Http429"
        assert err.detail == "HTTP 429"
        run = _read(
            producer._repo.db_path,
            "SELECT status, items_written, error_type FROM ingest_runs ORDER BY id DESC LIMIT 1",
        )
        assert run["status"] == "partial"
        assert run["items_written"] == 1
        assert run["error_type"] == "Http429"

    def test_both_weeks_429_failed_no_rows_written(self, tmp_path):
        producer = _producer(tmp_path)
        p1, p2, _calls, sleeps = _mock_transport(
            [_http(429)] * 6
        )
        with p1, p2:
            result = producer.fetch_calendar_json()
        assert result.run_status == IngestRunStatus.FAILED
        assert result.inserted == 0
        assert len(result.feed_errors) == 2
        run = _read(
            producer._repo.db_path,
            "SELECT status, items_written FROM ingest_runs ORDER BY id DESC LIMIT 1",
        )
        assert run["status"] == "failed"
        assert run["items_written"] == 0

    def test_url_error_retries_then_ok(self, tmp_path):
        producer = _producer(tmp_path)
        p1, p2, _calls, sleeps = _mock_transport(
            [URLError("boom"), _json_bytes(_PAYLOAD_THIS), _json_bytes(_PAYLOAD_NEXT)]
        )
        with p1, p2:
            result = producer.fetch_calendar_json()
        assert result.run_status == IngestRunStatus.OK
        assert sleeps == [1.0]

    def test_url_error_exhausted_partial(self, tmp_path):
        producer = _producer(tmp_path)
        p1, p2, _calls, sleeps = _mock_transport(
            [URLError("boom"), URLError("boom"), URLError("boom"), _json_bytes(_PAYLOAD_NEXT)]
        )
        with p1, p2:
            result = producer.fetch_calendar_json()
        assert result.run_status == IngestRunStatus.PARTIAL
        err = result.feed_errors[0]
        assert err.error_type == "UrlError"
        assert err.detail == "boom"

    def test_invalid_json_payload_classified(self, tmp_path):
        producer = _producer(tmp_path)
        p1, p2, _calls, sleeps = _mock_transport(
            [b"<not json>", _json_bytes(_PAYLOAD_NEXT)]
        )
        with p1, p2:
            result = producer.fetch_calendar_json()
        assert result.run_status == IngestRunStatus.PARTIAL
        assert result.feed_errors[0].error_type == "InvalidJsonPayload"
        assert result.inserted == 1

    def test_non_list_payload_treated_as_empty_fetch(self, tmp_path):
        producer = _producer(tmp_path)
        p1, p2, _calls, sleeps = _mock_transport(
            [_json_bytes({"not": "a list"}), _json_bytes(_PAYLOAD_NEXT)]
        )
        with p1, p2:
            result = producer.fetch_calendar_json()
        assert result.run_status == IngestRunStatus.OK
        assert result.inserted == 1


# ---- 4. luôn upsert đè ---------------------------------------------------------


class TestAlwaysOverwrite:
    def test_second_run_updates_same_dedupe_not_inserts(self, tmp_path):
        producer = _producer(tmp_path)
        feed = [{"country": "USD", "date": "2026-06-15T14:30:00Z",
                 "title": "FOMC Meeting", "impact": "high", "forecast": "5.5%"}]
        p1, p2, _calls, sleeps = _mock_transport([_json_bytes(feed), _json_bytes([])])
        with p1, p2:
            first = producer.fetch_calendar_json()
        assert first.inserted == 1

        p1, p2, _calls, sleeps = _mock_transport([_json_bytes(feed), _json_bytes([])])
        with p1, p2:
            second = producer.fetch_calendar_json()
        assert second.inserted == 0
        assert second.updated == 1
        assert _read(
            producer._repo.db_path,
            "SELECT COUNT(*) AS n FROM news_events",
        )["n"] == 1

    def test_feed_change_overwrites_forecast_and_impact(self, tmp_path):
        producer = _producer(tmp_path)
        def feed(forecast: str, impact: str):
            return [{"country": "USD", "date": "2026-06-15T14:30:00Z",
                     "title": "FOMC Meeting", "impact": impact, "forecast": forecast}]
        p1, p2, *_ = _mock_transport([_json_bytes(feed("5.5%", "high")), _json_bytes([])])
        with p1, p2:
            producer.fetch_calendar_json()

        p1, p2, *_ = _mock_transport([_json_bytes(feed("6.0%", "low")), _json_bytes([])])
        with p1, p2:
            changed = producer.fetch_calendar_json()
        assert changed.updated == 1
        row = _read(
            producer._repo.db_path,
            "SELECT forecast, impact FROM news_events",
        )
        assert row["forecast"] == "6.0%"
        assert row["impact"] == "low"


# ---- 5. actual không bị kênh JSON xóa (quy tắc 1 end-to-end) -------------------


class TestActualPreserved:
    def test_json_channel_never_blanks_existing_actual(self, tmp_path):
        producer = _producer(tmp_path)
        feed = [{"country": "USD", "date": "2026-06-15T14:30:00Z",
                 "title": "FOMC Meeting", "impact": "high"}]
        p1, p2, *_ = _mock_transport([_json_bytes(feed), _json_bytes([])])
        with p1, p2:
            producer.fetch_calendar_json()

        conn = sqlite3.connect(producer._repo.db_path)
        try:
            conn.execute(
                "UPDATE news_events SET actual='1.234', actual_updated_at='2026-06-15T15:00:00Z'"
            )
            conn.commit()
        finally:
            conn.close()

        p1, p2, *_ = _mock_transport([_json_bytes(feed), _json_bytes([])])
        with p1, p2:
            producer.fetch_calendar_json()
        row = _read(producer._repo.db_path, "SELECT actual FROM news_events")
        assert row["actual"] == "1.234"


# ---- 6. skip không chặn các dòng còn lại ----------------------------------------


class TestSkip:
    def test_dirty_rows_skipped_valid_kept(self, tmp_path):
        producer = _producer(tmp_path)
        dirty = [
            "not a dict",
            {"title": "No currency", "date": "2026-06-15T14:30:00Z"},
            {"country": "USD", "date": "garbage-date", "title": "Bad time"},
            {"country": "GBP", "date": "2026-06-15T14:30:00Z", "title": "Good one"},
        ]
        p1, p2, *_ = _mock_transport([_json_bytes(dirty), _json_bytes([])])
        with p1, p2:
            result = producer.fetch_calendar_json()
        assert result.inserted == 1
        row = _read(producer._repo.db_path, "SELECT title FROM news_events")
        assert row["title"] == "Good one"


# ---- 7. kết quả có kiểu, không dict thô ----------------------------------------


class TestTypedResult:
    def test_result_is_typed_not_raw_dict(self, tmp_path):
        producer = _producer(tmp_path)
        p1, p2, *_ = _mock_transport(
            [_json_bytes(_PAYLOAD_THIS), _json_bytes(_PAYLOAD_NEXT)]
        )
        with p1, p2:
            result = producer.fetch_calendar_json()
        assert not isinstance(result, dict)
        assert isinstance(result, JsonCalendarResult)
        assert isinstance(result.inserted, int)
        assert isinstance(result.updated, int)
        assert isinstance(result.conflicts, tuple)
        assert isinstance(result.run_status, IngestRunStatus)
        assert isinstance(result.feed_errors, tuple)
        assert all(isinstance(e, JsonCalendarFetchError) for e in result.feed_errors)


# ---- 8. không cache đĩa (B7) ----------------------------------------------------


class TestNoDiskCache:
    def test_only_news_db_created_no_cache_file(self, tmp_path):
        producer = _producer(tmp_path)
        p1, p2, *_ = _mock_transport(
            [_json_bytes(_PAYLOAD_THIS), _json_bytes(_PAYLOAD_NEXT)]
        )
        with p1, p2:
            producer.fetch_calendar_json()
        files = {p.name for p in tmp_path.iterdir()}
        assert files <= {"news.db", "news.db-wal", "news.db-shm"}