"""Xuất/nhập file CSV-JSON của miền Tin tức (plan lô L3.4) + QĐ-4.

Kiểm theo plan: round-trip CSV/JSON (cả ``news_events`` + ``news_items``); quy
tắc ``stale`` của contract §10 (giữ ``actual`` chính thống của FF, đè khi đích
đang ``stale``); file hỏng → lỗi thân thiện, DB nguyên vẹn; test thuần cho hàm
§4.3 mới trong ``core/news_models`` + test ghim "chỉ một định nghĩa §4.3"
(grep toàn miền) — QĐ-4 khoản 5 (giá trị khóa không đổi).

Repository là **thật** trên DB tạm (``tmp_path``) — không chạm ``%APPDATA%``;
mọi file sinh ra trong ``tmp_path``.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from core.news_models import (
    CalendarEvent,
    EventImpact,
    EventSource,
    EventStatus,
    NewsItem,
    NewsItemKind,
    NewsItemSource,
    news_item_dedupe_key,
)
from services import news_file_transfer as transfer
from services.news_file_transfer import (
    FileExportResult,
    FileImportResult,
    NewsFileTransferError,
    export_news_range,
    import_news_file,
)
from services.news_repository import NewsRepository

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NEWS_MIGRATIONS_DIR = PROJECT_ROOT / "data" / "migrations" / "news"

WIDE_FROM = "2000-01-01T00:00:00Z"
WIDE_TO = "2100-01-01T00:00:00Z"


def _repo(tmp_path: Path) -> NewsRepository:
    return NewsRepository(db_path=tmp_path / "news.db", migrations_dir=NEWS_MIGRATIONS_DIR)


def _event(**overrides: object) -> CalendarEvent:
    values: dict[str, object] = dict(
        day_key="2026-09-20",
        event_time_utc="2026-09-20T14:30:00Z",
        currency="USD",
        title="FOMC Meeting",
        impact=EventImpact.HIGH,
        status=EventStatus.SCHEDULED,
        source=EventSource.FF_JSON,
        dedupe_key="ev-1",
        fetched_at="2026-09-20T15:00:00Z",
        forecast="5.50%",
        previous="5.25%",
        actual=None,
        actual_updated_at=None,
        raw_json=None,
    )
    values.update(overrides)
    return CalendarEvent(**values)


def _item(**overrides: object) -> NewsItem:
    title = str(overrides.get("title", "Fed signals patience"))
    published_utc = str(overrides.get("published_utc", "2026-09-21T08:00:00Z"))
    url_raw = overrides.get("url", "https://example.com/fed")
    url = str(url_raw) if url_raw is not None else None
    values: dict[str, object] = dict(
        kind=NewsItemKind.HEADLINE,
        source=NewsItemSource.GOOGLE_NEWS_RSS,
        title=title,
        published_utc=published_utc,
        currencies=["USD"],
        dedupe_key=news_item_dedupe_key(url=url, title=title, published_utc=published_utc),
        fetched_at="2026-09-21T09:00:00Z",
        content=None,
        url=url,
        impact_hint=None,
        speaker_role=None,
        excluded=False,
    )
    values.update(overrides)
    return NewsItem(**values)


def _past_utc(days: int = 30) -> str:
    """Mốc quá khứ chắc chắn qua ân hạn ``stale`` (15 phút) — khuôn ISO của miền."""
    moment = datetime.now(UTC) - timedelta(days=days)
    return moment.isoformat(timespec="minutes").replace("+00:00", "Z")


def _rewrite_csv(path: Path, mutate) -> None:
    """Sửa nội dung file CSV bằng csv module (an toàn với cột chứa dấu phẩy)."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    mutate(rows)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else transfer._COLUMNS)
        writer.writeheader()
        if rows:
            writer.writerows(rows)


# ---------------------------------------------------------------------------
# 1. QĐ-4 — hàm thuần §4.3 trong core + ghim "chỉ một định nghĩa"
# ---------------------------------------------------------------------------


class TestSection43Formula:
    def test_core_function_covers_both_branches_and_matches_pinned_values(self):
        url_key = news_item_dedupe_key(
            url="https://news.example.com/fed-powell", title="T", published_utc="P"
        )
        assert url_key == hashlib.sha256(
            "https://news.example.com/fed-powell".encode()
        ).hexdigest()
        no_url = news_item_dedupe_key(
            url=None, title="Title X", published_utc="2026-07-20T06:00Z"
        )
        assert no_url == hashlib.sha256("Title X|2026-07-20T06:00Z".encode()).hexdigest()
        assert no_url != news_item_dedupe_key(
            url=None, title="Title X", published_utc="2026-07-20T07:00Z"
        )
        # Đường gọi cũ nối về cùng giá trị — test ghim L2.5 xanh nguyên trạng (B3).
        import services.news_producers.rss_producer as rss_module

        assert rss_module._dedupe_key(
            url="https://news.example.com/fed-powell", title="T", published_utc="P"
        ) == url_key
        assert rss_module._dedupe_key(
            url=None, title="Title X", published_utc="2026-07-20T06:00Z"
        ) == no_url

    def test_controller_copy_was_removed(self):
        from controllers import news_controller as controller_module

        assert not hasattr(controller_module, "_user_note_dedupe_key")
        source = Path(controller_module.__file__).read_text(encoding="utf-8")
        assert "def _user_note_dedupe_key" not in source
        assert "news_item_dedupe_key" in source  # gọi hàm core (QĐ-4 khoản 2)

    def test_only_one_definition_of_the_news_items_dedupe_formula(self):
        """QĐ-4 — grep toàn miền Tin tức: đúng MỘT định nghĩa công thức §4.3."""
        domains = ("core", "services", "controllers", "workers", "ui")
        sources: dict[str, str] = {}
        for package in domains:
            for path in (PROJECT_ROOT / package).rglob("*.py"):
                sources[path.relative_to(PROJECT_ROOT).as_posix()] = path.read_text(
                    encoding="utf-8"
                )
        # Công thức nằm đúng một chỗ: seed ``f"{title}|{published_utc}"``.
        with_seed = [rel for rel, text in sources.items() if 'f"{title}|{published_utc}"' in text]
        assert with_seed == ["core/news_models.py"]
        defined = [rel for rel, text in sources.items() if "def news_item_dedupe_key" in text]
        assert defined == with_seed
        # Không còn bản sao cũ ở bất kỳ mô-đun nào.
        for rel, text in sources.items():
            assert "_user_note_dedupe_key" not in text, rel
        # ``rss_producer`` giữ TÊN ghim L2.5 nhưng chỉ như delegation (không chứa công thức).
        rss = sources["services/news_producers/rss_producer.py"]
        assert "def _dedupe_key" in rss
        assert "news_item_dedupe_key" in rss
        assert 'f"{title}|{published_utc}"' not in rss


# ---------------------------------------------------------------------------
# 2. Xuất — file + nội dung
# ---------------------------------------------------------------------------


class TestExport:
    def test_export_writes_into_the_exports_directory(self, tmp_path, monkeypatch):
        from config import paths

        monkeypatch.setattr(paths, "app_data_dir", lambda: tmp_path / "appdata")
        repo = _repo(tmp_path / "src")
        repo.upsert_events([_event()])
        result = export_news_range(repo, WIDE_FROM, WIDE_TO, "csv")

        path = Path(result.path)
        assert path.parent == tmp_path / "appdata" / "exports"  # contract §10
        assert path.exists()
        assert path.suffix == ".csv"

    def test_export_rejects_an_unknown_format(self, tmp_path):
        repo = _repo(tmp_path)
        with pytest.raises(NewsFileTransferError):
            export_news_range(repo, WIDE_FROM, WIDE_TO, "xlsx")


# ---------------------------------------------------------------------------
# 3. Round-trip CSV/JSON
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def _seed(self, tmp_path: Path) -> NewsRepository:
        repo = _repo(tmp_path)
        event = _event(
            actual="5.50%",
            actual_updated_at="2026-09-20T16:00:00Z",
            raw_json='{"country": "USD", "title": "FOMC Meeting"}',
        )
        item = _item()
        note = _item(
            title="Ghi chú nội bộ",
            published_utc="2026-09-22T07:00:00Z",
            url=None,
            kind=NewsItemKind.USER_NOTE,
            source=NewsItemSource.USER,
            content="Theo dõi thêm.",
            excluded=True,
        )
        repo.upsert_events([event])
        repo.upsert_items([item, note])
        return repo

    def _assert_equivalent(self, target: NewsRepository) -> None:
        events = target.events_in_range(WIDE_FROM, WIDE_TO)
        assert len(events) == 1
        got = events[0]
        assert got.dedupe_key == "ev-1"
        assert got.event_time_utc == "2026-09-20T14:30:00Z"
        assert (got.currency, got.title, got.impact.value) == ("USD", "FOMC Meeting", "high")
        assert (got.forecast, got.previous, got.actual) == ("5.50%", "5.25%", "5.50%")
        assert got.actual_updated_at == "2026-09-20T16:00:00Z"
        assert got.raw_json == '{"country": "USD", "title": "FOMC Meeting"}'
        assert got.fetched_at == "2026-09-20T15:00:00Z"

        items = target.items_in_range(WIDE_FROM, None, exclude_flagged=False)
        by_title = {item.title: item for item in items}
        assert set(by_title) == {"Fed signals patience", "Ghi chú nội bộ"}
        head = by_title["Fed signals patience"]
        assert head.dedupe_key == news_item_dedupe_key(
            url="https://example.com/fed",
            title="Fed signals patience",
            published_utc="2026-09-21T08:00:00Z",
        )
        assert head.kind is NewsItemKind.HEADLINE
        assert head.source is NewsItemSource.GOOGLE_NEWS_RSS
        assert head.currencies == ["USD"]
        assert head.fetched_at == "2026-09-21T09:00:00Z"
        assert head.excluded is False
        note = by_title["Ghi chú nội bộ"]
        assert note.kind is NewsItemKind.USER_NOTE
        assert note.source is NewsItemSource.USER
        assert note.excluded is True
        assert note.content == "Theo dõi thêm."

    @pytest.mark.parametrize("fmt", ["csv", "json"])
    def test_round_trip_restores_events_and_items(self, tmp_path, fmt):
        source = self._seed(tmp_path / "src")
        result = export_news_range(source, WIDE_FROM, WIDE_TO, fmt, out_dir=tmp_path / "out")
        assert isinstance(result, FileExportResult)
        assert (result.events_written, result.items_written) == (1, 2)

        path = Path(result.path)
        assert path.exists()
        if fmt == "json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            assert isinstance(payload, list) and len(payload) == 3
            assert {item["record_type"] for item in payload} == {"event", "item"}

        target = _repo(tmp_path / "dst")
        imported = import_news_file(target, str(path))
        assert isinstance(imported, FileImportResult)
        assert (imported.inserted, imported.updated, imported.skipped_duplicates) == (3, 0, 0)
        self._assert_equivalent(target)

        # Nhập lại lần nữa → toàn bộ thành "cập nhật", không nhân bản.
        again = import_news_file(target, str(path))
        assert (again.inserted, again.updated, again.skipped_duplicates) == (0, 3, 0)


# ---------------------------------------------------------------------------
# 4. Quy tắc stale của §10 — bảo vệ actual chính thống (FF)
# ---------------------------------------------------------------------------


class TestImportActualRule:
    def test_keeps_an_authoritative_actual_when_destination_is_not_stale(self, tmp_path):
        # Đích: dòng có actual của FF (ff_html), quá khứ nhưng có actual → released.
        target = _repo(tmp_path / "target")
        target.upsert_events(
            [
                _event(
                    dedupe_key="keep-1",
                    actual="5.50%",
                    source=EventSource.FF_HTML,
                    status=EventStatus.RELEASED,
                )
            ]
        )
        # File mang actual khác — thư mục "file" là repo khác có deviating forecast.
        source = _repo(tmp_path / "source")
        source.upsert_events(
            [_event(dedupe_key="keep-1", actual="5.75%", forecast="6.00%", source=EventSource.FF_HTML)]
        )
        result = export_news_range(source, WIDE_FROM, WIDE_TO, "csv", out_dir=tmp_path / "out")

        imported = import_news_file(target, result.path)
        assert (imported.inserted, imported.updated, imported.skipped_duplicates) == (0, 1, 0)

        got = target.events_in_range(WIDE_FROM, WIDE_TO)[0]
        assert got.actual == "5.50%"  # actual của FF không bị đè
        assert got.forecast == "6.00%"  # các cột khác vẫn cập nhật từ file
        assert got.status == EventStatus.RELEASED

    def test_overwrites_actual_when_the_destination_row_is_stale(self, tmp_path):
        past = _past_utc()
        # Đích: dòng quá khứ không actual → phân loại stale (qua news_freshness).
        target = _repo(tmp_path / "target")
        target.upsert_events(
            [_event(dedupe_key="stale-1", event_time_utc=past, day_key=past[:10], actual=None)]
        )
        source = _repo(tmp_path / "source")
        source.upsert_events(
            [
                _event(
                    dedupe_key="stale-1",
                    event_time_utc=past,
                    day_key=past[:10],
                    actual="5.75%",
                    status=EventStatus.RELEASED,
                )
            ]
        )
        result = export_news_range(source, WIDE_FROM, WIDE_TO, "json", out_dir=tmp_path / "out")

        imported = import_news_file(target, result.path)
        assert (imported.inserted, imported.updated, imported.skipped_duplicates) == (0, 1, 0)

        got = target.events_in_range(WIDE_FROM, WIDE_TO)[0]
        assert got.actual == "5.75%"  # đích stale → actual của file được đè lên
        assert got.status == EventStatus.RELEASED
        assert got.dedupe_key == "stale-1"


# ---------------------------------------------------------------------------
# 5. Trùng trong file + dedupe items tính lại qua hàm core
# ---------------------------------------------------------------------------


class TestImportDedupe:
    def test_within_file_duplicates_are_skipped_and_counted(self, tmp_path):
        source = _repo(tmp_path / "src")
        source.upsert_items(
            [
                _item(),
                _item(title="Second", published_utc="2026-09-22T08:00:00Z", url=None),
            ]
        )
        result = export_news_range(source, WIDE_FROM, WIDE_TO, "csv", out_dir=tmp_path / "out")
        path = Path(result.path)

        # Nhân đôi bản ghi item cuối — trùng dedupe_key ngay trong file.
        def duplicate_last(rows):
            rows.append(dict(rows[-1]))

        _rewrite_csv(path, duplicate_last)

        target = _repo(tmp_path / "dst")
        imported = import_news_file(target, str(path))
        assert (imported.inserted, imported.updated, imported.skipped_duplicates) == (2, 0, 1)
        assert len(target.items_in_range(WIDE_FROM, None)) == 2

    def test_duplicate_event_rows_in_file_are_skipped_too(self, tmp_path):
        source = _repo(tmp_path / "src")
        source.upsert_events([_event(dedupe_key="a"), _event(dedupe_key="b")])
        result = export_news_range(source, WIDE_FROM, WIDE_TO, "csv", out_dir=tmp_path / "out")
        path = Path(result.path)

        def duplicate_first(rows):
            rows.insert(0, dict(rows[0]))

        _rewrite_csv(path, duplicate_first)

        target = _repo(tmp_path / "dst")
        imported = import_news_file(target, str(path))
        assert (imported.inserted, imported.updated, imported.skipped_duplicates) == (2, 0, 1)
        assert len(target.events_in_range(WIDE_FROM, WIDE_TO)) == 2

    def test_item_dedupe_is_recomputed_through_the_core_formula(self, tmp_path):
        """QĐ-4 khoản 3 — đường import gọi CÙNG hàm core; khóa trong file bị bỏ qua."""
        source = _repo(tmp_path / "src")
        source.upsert_items([_item()])
        result = export_news_range(source, WIDE_FROM, WIDE_TO, "csv", out_dir=tmp_path / "out")
        path = Path(result.path)

        def corrupt_dedupe(rows):
            rows[0]["dedupe_key"] = "WRONG-KEY"

        _rewrite_csv(path, corrupt_dedupe)

        target = _repo(tmp_path / "dst")
        imported = import_news_file(target, str(path))
        assert imported.inserted == 1
        got = target.items_in_range(WIDE_FROM, None)[0]
        assert got.dedupe_key == news_item_dedupe_key(
            url="https://example.com/fed",
            title="Fed signals patience",
            published_utc="2026-09-21T08:00:00Z",
        )
        assert got.dedupe_key != "WRONG-KEY"

    def test_event_dedupe_key_is_taken_from_the_file(self, tmp_path):
        """Sự kiện không có hàm core (§4.2 thuộc ff_calendar_producer) — khóa
        bản ghi event lấy nguyên từ file (round-trip mang sẵn khóa)."""
        source = _repo(tmp_path / "src")
        source.upsert_events([_event(dedupe_key="db-key")])
        result = export_news_range(source, WIDE_FROM, WIDE_TO, "json", out_dir=tmp_path / "out")
        path = Path(result.path)

        payload = json.loads(path.read_text(encoding="utf-8"))
        payload[0]["dedupe_key"] = "custom-file-key"
        path.write_text(json.dumps(payload), encoding="utf-8")

        target = _repo(tmp_path / "dst")
        imported = import_news_file(target, str(path))
        assert imported.inserted == 1
        got = target.events_in_range(WIDE_FROM, WIDE_TO)[0]
        assert got.dedupe_key == "custom-file-key"


# ---------------------------------------------------------------------------
# 6. File hỏng → lỗi thân thiện, DB nguyên vẹn
# ---------------------------------------------------------------------------


class TestImportErrors:
    def test_missing_file_raises_friendly_error(self, tmp_path):
        repo = _repo(tmp_path)
        with pytest.raises(NewsFileTransferError, match="không tồn tại"):
            import_news_file(repo, str(tmp_path / "none.csv"))

    def test_unsupported_extension_raises(self, tmp_path):
        repo = _repo(tmp_path)
        bad = tmp_path / "data.txt"
        bad.write_text("x", encoding="utf-8")
        with pytest.raises(NewsFileTransferError, match="định dạng không hỗ trợ"):
            import_news_file(repo, str(bad))

    def test_file_without_records_is_rejected(self, tmp_path):
        repo = _repo(tmp_path)
        empty = tmp_path / "empty.csv"
        empty.write_text("report_type\n", encoding="utf-8")
        with pytest.raises(NewsFileTransferError, match="không chứa bản ghi"):
            import_news_file(repo, str(empty))

    def test_broken_json_aborts_and_keeps_db_intact(self, tmp_path):
        target = _repo(tmp_path / "target")
        target.upsert_events([_event(dedupe_key="keep-me")])
        bad = tmp_path / "bad.json"
        bad.write_text('{"not": ', encoding="utf-8")

        with pytest.raises(NewsFileTransferError, match="JSON không đọc được"):
            import_news_file(target, str(bad))

        rows = target.events_in_range(WIDE_FROM, WIDE_TO)
        assert [row.dedupe_key for row in rows] == ["keep-me"]  # DB nguyên vẹn

    def test_json_of_the_wrong_shape_is_rejected(self, tmp_path):
        target = _repo(tmp_path / "target")
        target.upsert_items([_item()])
        wrong_shape = tmp_path / "shape.json"
        wrong_shape.write_text('{"records": []}', encoding="utf-8")

        with pytest.raises(NewsFileTransferError, match="mảng các bản ghi"):
            import_news_file(target, str(wrong_shape))
        rows = target.items_in_range(WIDE_FROM, None)
        assert [item.dedupe_key for item in rows] == [
            news_item_dedupe_key(
                url="https://example.com/fed",
                title="Fed signals patience",
                published_utc="2026-09-21T08:00:00Z",
            )
        ]  # DB nguyên vẹn

    def test_one_invalid_row_aborts_the_whole_file_unchanged(self, tmp_path):
        source = _repo(tmp_path / "src")
        source.upsert_events([_event(dedupe_key="ok"), _event(dedupe_key="bad")])
        result = export_news_range(source, WIDE_FROM, WIDE_TO, "csv", out_dir=tmp_path / "out")
        path = Path(result.path)

        def corrupt_impact(rows):
            rows[1]["impact"] = "BOGUS"

        _rewrite_csv(path, corrupt_impact)

        target = _repo(tmp_path / "dst")
        with pytest.raises(NewsFileTransferError, match="impact"):
            import_news_file(target, str(path))

        assert target.events_in_range(WIDE_FROM, WIDE_TO) == []  # không ghi gì
        assert target.items_in_range(WIDE_FROM, None) == []

    def test_missing_required_field_is_reported(self, tmp_path):
        source = _repo(tmp_path / "src")
        source.upsert_items([_item()])
        result = export_news_range(source, WIDE_FROM, WIDE_TO, "csv", out_dir=tmp_path / "out")
        path = Path(result.path)

        def drop_kind(rows):
            rows[0]["kind"] = ""

        _rewrite_csv(path, drop_kind)

        target = _repo(tmp_path / "dst")
        with pytest.raises(NewsFileTransferError, match="kind"):
            import_news_file(target, str(path))
        assert target.items_in_range(WIDE_FROM, None) == []


# ---------------------------------------------------------------------------
# 7. Import không ghi ingest_runs (enum producer §4.6 đóng băng — R6)
# ---------------------------------------------------------------------------


def test_import_never_writes_an_ingest_run_row(tmp_path):
    source = _repo(tmp_path / "src")
    source.upsert_events([_event()])
    source.upsert_items([_item()])
    result = export_news_range(source, WIDE_FROM, WIDE_TO, "csv", out_dir=tmp_path / "out")

    target = _repo(tmp_path / "dst")
    import_news_file(target, result.path)

    conn = target._connect()
    try:
        count = conn.execute("SELECT COUNT(*) AS n FROM ingest_runs").fetchone()["n"]
    finally:
        conn.close()
    assert count == 0