"""fred_rate_producer tests (plan lô L2.6, contract §6.3/§4.4/§4.6).

Behavioral parity with the inherited runtime (B3, function level): the FRED
transport is mocked — ``requests.get`` in the producer namespace.  No real
HTTP, no waiting and ``%APPDATA%`` is never touched (throwaway temp DB); the
fallback JSON is always a temp fixture, never ``config/interest_rates.json``.

Đợt 3 (24/09/2026 — ca "Nguồn dán FF", plan F1): kênh ForexFactory-HTML của
producer bị gỡ (Cloudflare chặn client không-phải-browser — contract §6.3);
nhánh test của kênh đó và mock trình duyệt (``urllib``/client) được gỡ cùng
commit.  Chuỗi nguồn còn đúng hai kênh: **``fred`` → ``config_fallback``**.

Plan L2.6 checklist covered here: FRED mock ok / lỗi → source chain in order
(``fred`` → ``config_fallback``), the written ``source`` enum of each branch,
and a duplicate ``(currency, observed_at, source)`` upserting instead of
duplicating.
"""

from __future__ import annotations

import ast
import inspect
import json
import sqlite3
from pathlib import Path
from unittest import mock

import pytest

from config.paths import PROJECT_ROOT
from core.news_models import (
    IngestProducer,
    IngestRunStatus,
    RateObservation,
    RateSource,
)
from core.news_policy import NewsPolicy
from services.news_producers import fred_rate_producer as fredmod
from services.news_producers.fred_rate_producer import (
    FRED_SERIES,
    FredRateProducer,
    RateChannelError,
    RateFetchResult,
)
from services.news_repository import NewsRepository

NEWS_MIGRATIONS_DIR = PROJECT_ROOT / "data" / "migrations" / "news"


@pytest.fixture(autouse=True)
def _hermetic_transport():
    """No test may reach the network: FRED raises if a test forgot to mock it
    (đợt 3 — the inherited ForexFactory transport of this producer was removed,
    so there is nothing else to patch)."""
    with mock.patch.object(
        fredmod.requests, "get", side_effect=AssertionError("FRED called without a mock")
    ):
        yield


# ---- fixture scaffolding (temp DB + fully mocked transport) ---------------------


class _FredResponse:
    """Minimal stand-in for a ``requests`` response (status + JSON body)."""

    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        if isinstance(self._payload, BaseException):
            raise self._payload
        return self._payload


def _observations(
    value1: str = "5.75",
    value2: str = "5.50",
    date1: str = "2026-06-15",
    date2: str = "2026-05-15",
) -> dict[str, object]:
    """FRED ``observations`` payload shaped like the old tests' fixture."""
    return {
        "observations": [
            {"date": date1, "value": value1},
            {"date": date2, "value": value2},
        ]
    }


def _mock_fred(spec: dict[str, object] | None = None, default: object = None):
    """Mock ``requests.get`` in the producer namespace.

    ``spec`` maps a FRED series id to a payload dict, an int status code or an
    exception to raise; ``default`` applies to every other series (``None``
    means "use the standard two-observation payload").  Returns the fake and
    the recorded calls (url/params/timeout)."""
    calls: list[dict[str, object]] = []

    def fake_get(url, params=None, timeout=None):
        params = dict(params or {})
        calls.append({"url": url, "params": params, "timeout": timeout})
        series_id = str(params.get("series_id", ""))
        item = (spec or {}).get(series_id, default)
        if item is None:
            item = _observations()
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, int):
            return _FredResponse(item, {})
        return _FredResponse(200, item)

    return fake_get, calls


def _policy(**overrides) -> NewsPolicy:
    """A real ``NewsPolicy`` (fail-closed validation runs) with test values."""
    data: dict[str, object] = {
        "policy_version": "news-policy",
        "rss_poll_interval_minutes": 15,
        "rss_window_hours": 24,
        "fred_refresh_hours": 6,
        "event_stale_grace_minutes": 15,
        "ingest_freshness_hours": 2,
        "ingest_runs_retention_days": 30,
        "ai_window_days": 7,
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
        db_path=tmp_path / "news.db",
        migrations_dir=NEWS_MIGRATIONS_DIR,
    )


def _writer(tmp_path: Path, fallback: dict[str, object] | None = None) -> Path:
    """Write a temp fallback JSON file and return its path."""
    path = tmp_path / "interest_rates.json"
    path.write_text(json.dumps(fallback if fallback is not None else {}), encoding="utf-8")
    return path


def _producer(
    tmp_path: Path,
    *,
    api_key: str | None = None,
    fallback: Path | None = None,
    policy: NewsPolicy | None = None,
    repo: NewsRepository | None = None,
) -> FredRateProducer:
    return FredRateProducer(
        repo if repo is not None else _repo(tmp_path),
        policy if policy is not None else _policy(),
        api_key,
        fallback if fallback is not None else tmp_path / "no_such_fallback.json",
    )


def _rows(db_path: Path, sql: str = "SELECT * FROM interest_rates", params: tuple = ()):
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _runs(db_path: Path):
    return _rows(db_path, "SELECT * FROM ingest_runs ORDER BY id")


def _sources_by_currency(rows: list[dict]) -> dict[str, set[str]]:
    sources: dict[str, set[str]] = {}
    for row in rows:
        sources.setdefault(row["currency"], set()).add(row["source"])
    return sources


def _channel_errors(result: RateFetchResult, channel: str) -> set[str]:
    """Error types recorded for one channel of a round (the other channels of
    the same round carry their own errors)."""
    return {error.error_type for error in result.errors if error.channel == channel}


# ---- 1. FRED channel: quan sát + nguồn ghi -------------------------------------


class TestFredChannel:
    def test_fred_ok_writes_two_nearest_observations_per_currency(self, tmp_path):
        fake_get, calls = _mock_fred()
        producer = _producer(tmp_path, api_key="key-1")
        with mock.patch.object(fredmod.requests, "get", fake_get):
            result = producer.fetch_round()

        assert result.run_status == IngestRunStatus.OK
        assert result.fred_observations == 2 * len(FRED_SERIES)
        assert result.config_fallback_observations == 0
        assert result.currencies_covered == tuple(sorted(FRED_SERIES))
        assert result.errors == ()

        rows = _rows(tmp_path / "news.db")
        assert len(rows) == 2 * len(FRED_SERIES)
        assert {row["source"] for row in rows} == {"fred"}
        assert {row["observed_at"] for row in rows} == {"2026-06-15", "2026-05-15"}

    def test_request_parameters_are_verbatim(self, tmp_path):
        """B3: endpoint + tham số nguyên văn của ``_fetch_from_fred`` (d.157-169)."""
        fake_get, calls = _mock_fred()
        producer = _producer(tmp_path, api_key="key-1")
        with mock.patch.object(fredmod.requests, "get", fake_get):
            producer.fetch_round()

        assert len(calls) == len(FRED_SERIES)
        first = calls[0]
        assert first["url"] == "https://api.stlouisfed.org/fred/series/observations"
        assert first["params"]["series_id"] == FRED_SERIES["USD"]
        assert first["params"]["api_key"] == "key-1"
        assert first["params"]["file_type"] == "json"
        assert first["params"]["sort_order"] == "desc"
        assert first["params"]["limit"] == 2
        assert first["timeout"] == 5

    def test_trend_is_derived_at_read_time_not_in_producer(self, tmp_path):
        """B3: hai quan sát gần nhất ⇒ trend hike đúng ngưỡng FRED 0.1 (d.182-187),
        nhưng do ``core/rate_trend`` dẫn xuất lúc đọc — producer không tính (L1.5)."""
        fake_get, _ = _mock_fred()
        repo = _repo(tmp_path)
        producer = _producer(tmp_path, api_key="key-1", repo=repo)
        with mock.patch.object(fredmod.requests, "get", fake_get):
            producer.fetch_round()

        usd = {rate.currency: rate for rate in repo.latest_rates(["USD"])}["USD"]
        assert usd.latest.rate == 5.75
        assert usd.previous.rate == 5.50
        assert usd.trend.value == "hike"

        source = inspect.getsource(fredmod)
        for derived in ('"hike"', '"cut"', '"hold"'):
            assert derived not in source  # không có phép dẫn xuất trend trong producer

    def test_sentinel_values_are_filtered(self, tmp_path):
        payload = {
            "observations": [
                {"date": "2026-06-15", "value": "."},
                {"date": "2026-05-15", "value": "5.50"},
            ]
        }
        fake_get, _ = _mock_fred(default=payload)
        producer = _producer(tmp_path, api_key="key-1")
        with mock.patch.object(fredmod.requests, "get", fake_get):
            result = producer.fetch_round()

        assert result.fred_observations == len(FRED_SERIES)  # chỉ điểm hợp lệ còn lại
        assert {row["observed_at"] for row in _rows(tmp_path / "news.db")} == {"2026-05-15"}

    def test_all_sentinel_observations_skip_currency(self, tmp_path):
        payload = {"observations": [{"date": "2026-06-15", "value": "."}]}
        fake_get, _ = _mock_fred(default=payload)
        producer = _producer(tmp_path, api_key="key-1", fallback=_writer(tmp_path, {}))
        with mock.patch.object(fredmod.requests, "get", fake_get):
            result = producer.fetch_round()

        assert result.fred_observations == 0
        assert _channel_errors(result, "fred") == {"NoObservations"}

    def test_non_200_skips_currency_and_chain_continues(self, tmp_path):
        fallback = _writer(
            tmp_path,
            {"currencies": {currency: {"rate": 3.75, "_updated": "2026-06-01"} for currency in FRED_SERIES}},
        )
        fake_get, _ = _mock_fred(default=500)
        producer = _producer(tmp_path, api_key="key-1", fallback=fallback)
        with mock.patch.object(fredmod.requests, "get", fake_get):
            result = producer.fetch_round()

        assert result.fred_observations == 0
        assert result.config_fallback_observations == len(FRED_SERIES)
        assert result.run_status == IngestRunStatus.PARTIAL
        assert result.errors[0].error_type == "Http500"

    def test_transport_exception_skips_currency(self, tmp_path):
        fake_get, _ = _mock_fred(default=ConnectionError("no net"))
        producer = _producer(tmp_path, api_key="key-1", fallback=_writer(tmp_path, {}))
        with mock.patch.object(fredmod.requests, "get", fake_get):
            result = producer.fetch_round()

        assert result.fred_observations == 0
        assert _channel_errors(result, "fred") == {"ConnectionError"}

    def test_unreadable_value_skips_whole_currency(self, tmp_path):
        """B3: ``float(valid[0]["value"])`` ném ⇒ bỏ cả currency (d.178-179)."""
        payload = {
            "observations": [
                {"date": "2026-06-15", "value": "n/a"},
                {"date": "2026-05-15", "value": "5.50"},
            ]
        }
        fake_get, _ = _mock_fred(default=payload)
        producer = _producer(tmp_path, api_key="key-1", fallback=_writer(tmp_path, {}))
        with mock.patch.object(fredmod.requests, "get", fake_get):
            result = producer.fetch_round()

        assert result.fred_observations == 0
        assert _channel_errors(result, "fred") == {"InvalidObservation"}

    def test_unreadable_previous_value_skips_whole_currency(self, tmp_path):
        payload = {
            "observations": [
                {"date": "2026-06-15", "value": "5.75"},
                {"date": "2026-05-15", "value": "n/a"},
            ]
        }
        fake_get, _ = _mock_fred(default=payload)
        producer = _producer(tmp_path, api_key="key-1", fallback=_writer(tmp_path, {}))
        with mock.patch.object(fredmod.requests, "get", fake_get):
            result = producer.fetch_round()

        assert result.fred_observations == 0
        assert _channel_errors(result, "fred") == {"InvalidObservation"}

    def test_empty_observation_date_skips_currency(self, tmp_path):
        payload = {"observations": [{"date": "", "value": "5.75"}]}
        fake_get, _ = _mock_fred(default=payload)
        producer = _producer(tmp_path, api_key="key-1", fallback=_writer(tmp_path, {}))
        with mock.patch.object(fredmod.requests, "get", fake_get):
            result = producer.fetch_round()

        assert result.fred_observations == 0
        assert _channel_errors(result, "fred") == {"InvalidObservation"}

    def test_missing_api_key_skips_fred_channel(self, tmp_path):
        # Đợt 3: thiếu khóa ⇒ bỏ kênh FRED; không có kênh HTML nữa — fallback
        # lấp trực tiếp (chuỗi fred → config_fallback).
        fake_get, calls = _mock_fred()
        fallback = _writer(
            tmp_path,
            {"currencies": {currency: {"rate": 3.75, "_updated": "2026-06-01"} for currency in FRED_SERIES}},
        )
        producer = _producer(tmp_path, api_key=None, fallback=fallback)
        with mock.patch.object(fredmod.requests, "get", fake_get):
            result = producer.fetch_round()

        assert calls == []  # nguyên hành vi cũ (d.58): không khóa ⇒ không gọi FRED
        assert result.errors[0] == RateChannelError(
            "fred", "", "NoApiKey", "no FRED API key configured"
        )
        assert result.config_fallback_observations == len(FRED_SERIES)
        assert result.run_status == IngestRunStatus.PARTIAL


# ---- 2. Chuỗi nguồn (đợt 3): fred → config_fallback -------------------------


class TestSourceChain:
    def test_fred_covered_currency_is_not_offered_downstream(self, tmp_path):
        """FRED thắng: không có dòng fallback nào cho đồng tiền FRED đã phủ."""
        fake_get, _ = _mock_fred()
        fallback = _writer(
            tmp_path,
            {"currencies": {currency: {"rate": 3.75, "_updated": "2026-06-01"} for currency in FRED_SERIES}},
        )
        producer = _producer(tmp_path, api_key="key-1", fallback=fallback)
        with mock.patch.object(fredmod.requests, "get", fake_get):
            result = producer.fetch_round()

        assert result.run_status == IngestRunStatus.OK
        assert result.config_fallback_observations == 0
        assert _sources_by_currency(_rows(tmp_path / "news.db")) == {
            currency: {"fred"} for currency in FRED_SERIES
        }

    def test_chain_order_fred_then_config_fallback(self, tmp_path):
        # FRED hỏng toàn bộ ⇒ fallback lấp trọn phần còn lại (đợt 3: không còn
        # kênh HTML giữa; ``source`` trả về đúng enum §4.4 của mỗi nhánh).
        fake_get, _ = _mock_fred(default=400)
        fallback = _writer(
            tmp_path,
            {
                "currencies": {
                    currency: {"rate": 3.75, "_updated": "2026-06-01"}
                    for currency in FRED_SERIES
                }
            },
        )
        producer = _producer(tmp_path, api_key="key-1", fallback=fallback)
        with mock.patch.object(fredmod.requests, "get", fake_get):
            result = producer.fetch_round()

        rows = _rows(tmp_path / "news.db")
        assert result.fred_observations == 0
        assert result.config_fallback_observations == len(FRED_SERIES)
        assert result.run_status == IngestRunStatus.PARTIAL
        assert {row["source"] for row in rows} == {"config_fallback"}

    def test_fallback_used_only_when_fred_did_not_cover(self, tmp_path):
        # Chỉ USD lấy được từ FRED; 7 đồng tiền còn lại chuyển thẳng fallback.
        only_usd = {FRED_SERIES["USD"]: _observations()}
        fake_get, _ = _mock_fred(spec=only_usd, default=400)
        fallback = _writer(
            tmp_path,
            {"currencies": {currency: {"rate": 0.10, "_updated": "2026-01-01"} for currency in FRED_SERIES}},
        )
        producer = _producer(tmp_path, api_key="key-1", fallback=fallback)
        with mock.patch.object(fredmod.requests, "get", fake_get):
            result = producer.fetch_round()

        sources = _sources_by_currency(_rows(tmp_path / "news.db"))
        assert sources["USD"] == {"fred"}
        assert sources["JPY"] == {"config_fallback"}
        assert result.fred_observations == 2  # hai điểm gần nhất của USD
        assert result.config_fallback_observations == len(FRED_SERIES) - 1


# ---- 3. (gỡ đợt 3: Kênh FF-HTML — test của hành vi bị xóa; chuỗi nguồn mới
# ----    fred → config_fallback đã ghim ở TestSourceChain) -----------------------

# ---- 4. Kênh fallback JSON ----------------------------------------------------


class TestFallbackChannel:
    def test_entry_date_wins_over_file_date(self, tmp_path):
        fallback = _writer(
            tmp_path,
            {
                "currencies": {
                    "USD": {"rate": 3.75, "_updated": "2026-06-01"},
                    "EUR": {"rate": 2.50},
                },
                "_last_updated": "2026-06-10 08:00 UTC",
            },
        )
        producer = _producer(tmp_path, api_key=None, fallback=fallback)
        result = producer.fetch_round()

        rows = {row["currency"]: row for row in _rows(tmp_path / "news.db")}
        assert result.config_fallback_observations == 2
        assert rows["USD"]["observed_at"] == "2026-06-01"  # ``_updated`` của mục
        assert rows["EUR"]["observed_at"] == "2026-06-10"  # ``_last_updated`` của tệp
        assert {row["source"] for row in rows.values()} == {"config_fallback"}

    def test_entry_without_any_date_is_skipped(self, tmp_path):
        """B4/B5: ``observed_at`` NOT NULL — thiếu ngày ⇒ bỏ, không bịa."""
        fallback = _writer(tmp_path, {"currencies": {"USD": {"rate": 3.75}}})
        producer = _producer(tmp_path, api_key=None, fallback=fallback)
        result = producer.fetch_round()

        assert _rows(tmp_path / "news.db") == []
        assert result.run_status == IngestRunStatus.FAILED
        assert "MissingObservationDate" in _channel_errors(result, "config_fallback")

    def test_missing_file_or_entry_yields_no_row(self, tmp_path):
        producer = _producer(tmp_path, api_key=None, fallback=tmp_path / "absent.json")
        result = producer.fetch_round()

        assert _rows(tmp_path / "news.db") == []
        assert _channel_errors(result, "config_fallback") == {"MissingFallbackEntry"}

    def test_unreadable_rate_is_typed(self, tmp_path):
        fallback = _writer(
            tmp_path,
            {"currencies": {"USD": {"rate": "n/a", "_updated": "2026-06-01"}}},
        )
        producer = _producer(tmp_path, api_key=None, fallback=fallback)
        result = producer.fetch_round()

        assert _channel_errors(result, "config_fallback") == {
            "InvalidFallbackRate",
            "MissingFallbackEntry",
        }


# ---- 5. Ghi repository: UNIQUE (currency, observed_at, source) -----------------


class TestRateWrite:
    def test_duplicate_observation_upserts_instead_of_duplicating(self, tmp_path):
        fake_get, _ = _mock_fred()
        repo = _repo(tmp_path)
        producer = _producer(tmp_path, api_key="key-1", repo=repo)
        with mock.patch.object(fredmod.requests, "get", fake_get):
            first = producer.fetch_round()
            second = producer.fetch_round()

        expected = 2 * len(FRED_SERIES)
        assert first.written == expected and second.written == expected
        rows = _rows(tmp_path / "news.db")
        assert len(rows) == expected  # chạy lại không nhân bản
        keys = {(row["currency"], row["observed_at"], row["source"]) for row in rows}
        assert len(keys) == expected
        assert len(_runs(tmp_path / "news.db")) == 2

    def test_conflicting_value_on_same_key_overwrites(self, tmp_path):
        repo = _repo(tmp_path)
        producer = _producer(tmp_path, api_key="key-1", repo=repo)
        fake_get, _ = _mock_fred()
        with mock.patch.object(fredmod.requests, "get", fake_get):
            producer.fetch_round()
        fake_get, _ = _mock_fred(default=_observations("5.80", "5.50"))
        with mock.patch.object(fredmod.requests, "get", fake_get):
            producer.fetch_round()

        rows = _rows(tmp_path / "news.db", "SELECT * FROM interest_rates WHERE currency='USD'")
        assert len(rows) == 2
        assert {row["rate"] for row in rows} == {5.80, 5.50}


# ---- 6. Run log, trạng thái, chính sách ---------------------------------------


class TestRunLogAndPolicy:
    def test_empty_round_logs_a_failed_run(self, tmp_path):
        producer = _producer(tmp_path, api_key=None, fallback=tmp_path / "absent.json")
        result = producer.fetch_round()

        assert result.run_status == IngestRunStatus.FAILED
        assert result.written == 0
        runs = _runs(tmp_path / "news.db")
        assert len(runs) == 1
        assert runs[0]["producer"] == IngestProducer.FRED.value
        assert runs[0]["status"] == "failed"
        assert runs[0]["items_written"] == 0
        assert runs[0]["error_type"] == "NoApiKey"
        assert runs[0]["error_detail"].startswith("fred: ")

    def test_partial_run_records_the_first_error(self, tmp_path):
        fake_get, _ = _mock_fred(default=500)
        fallback = _writer(
            tmp_path,
            {"currencies": {currency: {"rate": 3.75, "_updated": "2026-06-01"} for currency in FRED_SERIES}},
        )
        producer = _producer(tmp_path, api_key="key-1", fallback=fallback)
        with mock.patch.object(fredmod.requests, "get", fake_get):
            result = producer.fetch_round()

        runs = _runs(tmp_path / "news.db")
        assert runs[0]["status"] == "partial"
        assert runs[0]["items_written"] == len(FRED_SERIES)
        assert runs[0]["error_type"] == "Http500"
        assert "fred/USD" in runs[0]["error_detail"]
        assert result.run_id == runs[0]["id"]

    def test_refresh_hours_comes_from_the_policy_key(self, tmp_path):
        producer = _producer(tmp_path, policy=_policy(fred_refresh_hours=3))
        assert producer.refresh_hours == 3

    def test_policy_is_loaded_fail_closed_when_not_injected(self, tmp_path):
        with mock.patch.object(fredmod, "load_news_policy", return_value=_policy()) as loader:
            producer = FredRateProducer(_repo(tmp_path))
        loader.assert_called_once_with()
        assert producer.refresh_hours == 6

    def test_no_hard_coded_cadence_or_cache_in_module(self):
        """R4: chu kỳ đọc từ khóa ``fred_refresh_hours``; cache in-memory cũ
        (6 h/3 h) không được port ⇒ không hằng thời gian nào trong mã chạy
        (kiểm bằng AST: lời văn giải thích trong docstring không tính)."""
        tree = ast.parse(inspect.getsource(fredmod))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
        assert "timedelta" not in imported  # không có TTL/chu kỳ cứng nào

        assigned = {
            target.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        assert not {name for name in assigned if name.isupper() and "TTL" in name}
        assert not {name for name in assigned if "CACHE" in name or "LAST_SCAN" in name}
        assert "fred_refresh_hours" in inspect.getsource(fredmod)

    def test_consecutive_rounds_never_suppressed_by_time(self, tmp_path):
        """Không cache in-memory: hai lượt liền nhau đều chạm mạng (R4/B7)."""
        fake_get, calls = _mock_fred()
        producer = _producer(tmp_path, api_key="key-1")
        with mock.patch.object(fredmod.requests, "get", fake_get):
            producer.fetch_round()
            producer.fetch_round()

        assert len(calls) == 2 * len(FRED_SERIES)


# ---- 7. Ranh giới công khai (R8/C3) -------------------------------------------


class TestBoundary:
    def test_round_result_is_typed_and_raw_free(self, tmp_path):
        fake_get, _ = _mock_fred()
        producer = _producer(tmp_path, api_key="key-1")
        with mock.patch.object(fredmod.requests, "get", fake_get):
            result = producer.fetch_round()

        assert isinstance(result, RateFetchResult)
        assert isinstance(result.run_status, IngestRunStatus)
        assert isinstance(result.currencies_covered, tuple)
        assert all(isinstance(currency, str) for currency in result.currencies_covered)
        assert all(isinstance(error, RateChannelError) for error in result.errors)
        assert isinstance(result.written, int)

    def test_error_objects_carry_no_payload(self, tmp_path):
        producer = _producer(tmp_path, api_key=None, fallback=tmp_path / "absent.json")
        result = producer.fetch_round()

        for error in result.errors:
            assert isinstance(error, RateChannelError)
            assert isinstance(error.detail, str)

    def test_fred_series_covers_the_inherited_eight_currencies(self):
        assert FRED_SERIES == {
            "USD": "FEDFUNDS",
            "EUR": "ECBDFR",
            "GBP": "BOEBR",
            "JPY": "IRSTCI01JPM156N",
            "AUD": "RBATCTR",
            "NZD": "RBNZ_OCR",
            "CAD": "BOCWATCH",
            "CHF": "SNPOLICYR",
        }
        assert set(RateSource) == {
            RateSource.FRED,
            RateSource.FF_HTML,
            RateSource.CONFIG_FALLBACK,
        }
