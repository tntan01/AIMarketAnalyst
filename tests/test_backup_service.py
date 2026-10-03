from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

from services.backup_service import (
    MANIFEST_NAME,
    PENDING_DIR,
    REQUEST_NAME,
    BackupService,
)
from services.journal_service import JournalService

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "data" / "migrations"


def _seed_user_data(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "settings.json").write_text('{"language": "vi"}', encoding="utf-8")
    (root / "be_trailing_state.json").write_text(
        '{"positions": []}', encoding="utf-8"
    )
    (root / "scan_health").mkdir(exist_ok=True)
    (root / "scan_health" / "scan-health.json").write_text(
        '{"scans": 1}', encoding="utf-8"
    )
    (root / "scanner_snapshots").mkdir(exist_ok=True)
    (root / "scanner_snapshots" / "scanner_scan-1.json").write_text(
        '{"rank": 1}', encoding="utf-8"
    )
    # rác — phải bị loại khỏi backup (Q1: "đầy đủ trừ rác")
    (root / "logs").mkdir(exist_ok=True)
    (root / "logs" / "app.log").write_text("log", encoding="utf-8")
    (root / "cache").mkdir(exist_ok=True)
    (root / "cache" / "provider.json").write_text("{}", encoding="utf-8")


def _seed_news_db(path: Path, rows: int = 2) -> sqlite3.Connection:
    """DB WAL + connection vẫn mở — mô phỏng producer news đang ghi."""

    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE news_items (id INTEGER PRIMARY KEY, title TEXT)")
    conn.executemany(
        "INSERT INTO news_items (title) VALUES (?)",
        [(f"title-{index}",) for index in range(rows)],
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version TEXT PRIMARY KEY, applied_at_utc TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO schema_migrations VALUES ('001_create_news_db', '2026-01-01T00:00:00Z')"
    )
    conn.commit()
    return conn


def _copy_zip(source: Path, target: Path, *, replace: dict[str, bytes] | None = None,
              drop: set[str] | None = None) -> None:
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(target, "w") as dst:
        for name in src.namelist():
            if drop and name in drop:
                continue
            data = (replace or {}).get(name, src.read(name))
            dst.writestr(name, data)


def test_backup_snapshot_is_wal_safe_and_scope_excludes_junk(tmp_path):
    root = tmp_path / "appdata"
    _seed_user_data(root)
    writer = _seed_news_db(root / "news.db")
    try:
        result = BackupService(app_data_root=root).create_backup(
            dest_dir=tmp_path / "dest"
        )
    finally:
        writer.close()

    assert result.zip_path.is_file()
    with zipfile.ZipFile(result.zip_path) as archive:
        names = archive.namelist()
        assert "news.db" in names
        assert MANIFEST_NAME in names
        assert "settings.json" in names
        assert "be_trailing_state.json" in names
        assert "scan_health/scan-health.json" in names
        assert "scanner_snapshots/scanner_scan-1.json" in names
        # rác bị loại
        assert not any(name.startswith(("logs/", "cache/")) for name in names)
        assert not any(name.endswith(("-wal", "-shm")) for name in names)

        manifest = json.loads(archive.read(MANIFEST_NAME))
        assert manifest["database_migrations"]["news.db"] == "001_create_news_db"
        entries = {entry["path"]: entry for entry in manifest["entries"]}
        assert entries["news.db"]["size_bytes"] > 0

        # snapshot phải mở được và đủ dữ liệu đang nằm trong WAL của DB nguồn
        archive.extract("news.db", tmp_path / "extracted")
        check = sqlite3.connect(tmp_path / "extracted" / "news.db")
        try:
            count = check.execute("SELECT COUNT(*) FROM news_items").fetchone()[0]
        finally:
            check.close()
        assert count == 2

    validation = BackupService(app_data_root=root).validate_backup(result.zip_path)
    assert validation.ok, validation.errors


def test_validate_rejects_corrupt_package(tmp_path):
    root = tmp_path / "appdata"
    _seed_user_data(root)
    service = BackupService(app_data_root=root)
    result = service.create_backup(dest_dir=tmp_path / "dest")

    tampered = tmp_path / "tampered.zip"
    _copy_zip(
        result.zip_path,
        tampered,
        replace={"settings.json": b'{"language": "en"}'},
    )
    bad = service.validate_backup(tampered)
    assert not bad.ok
    assert any("SHA-256" in error for error in bad.errors)

    no_manifest = tmp_path / "no_manifest.zip"
    _copy_zip(result.zip_path, no_manifest, drop={MANIFEST_NAME})
    missing = service.validate_backup(no_manifest)
    assert not missing.ok

    absent = service.validate_backup(tmp_path / "khong-co.zip")
    assert not absent.ok


def test_stage_and_apply_roundtrip_with_safety_backup(tmp_path):
    root = tmp_path / "appdata"
    _seed_user_data(root)
    writer = _seed_news_db(root / "news.db")
    writer.close()
    service = BackupService(app_data_root=root)
    backup = service.create_backup(dest_dir=tmp_path / "out")

    # dữ liệu hiện tại đổi khác so với bản backup
    (root / "settings.json").write_text('{"language": "en"}', encoding="utf-8")
    (root / "scanner_snapshots" / "scanner_extra.json").write_text(
        "{}", encoding="utf-8"
    )
    (root / "scan_health" / "scan-health.json").unlink()

    staged = service.stage_restore(backup.zip_path)
    assert staged.ok, staged.errors
    assert (root / PENDING_DIR / REQUEST_NAME).is_file()
    assert staged.safety_backup is not None and staged.safety_backup.is_file()

    # trước khi apply: dữ liệu gốc chưa bị đụng; sidecar WAL cũ tồn tại
    assert json.loads((root / "settings.json").read_text(encoding="utf-8"))[
        "language"
    ] == "en"
    (root / "news.db-wal").write_text("stale-wal", encoding="utf-8")

    applied = service.apply_pending_restore()
    assert applied.applied, applied.errors
    assert applied.safety_backup == staged.safety_backup

    # dữ liệu trở về đúng bản backup
    assert json.loads((root / "settings.json").read_text(encoding="utf-8"))[
        "language"
    ] == "vi"
    assert (root / "scan_health" / "scan-health.json").is_file()
    # thư mục bằng chứng được thay nguyên thư mục: tệp lẻ biến mất
    assert not (root / "scanner_snapshots" / "scanner_extra.json").exists()
    # DB được thay → sidecar WAL cũ của bản cũ phải đi theo
    assert not (root / "news.db-wal").exists()
    assert not (root / PENDING_DIR).exists()

    # idempotent: không marker → không làm gì
    assert service.apply_pending_restore().applied is False


def test_apply_refuses_when_staged_corrupted(tmp_path):
    root = tmp_path / "appdata"
    _seed_user_data(root)
    service = BackupService(app_data_root=root)
    backup = service.create_backup(dest_dir=tmp_path / "out")
    (root / "settings.json").write_text('{"language": "en"}', encoding="utf-8")

    staged = service.stage_restore(backup.zip_path)
    assert staged.ok, staged.errors
    (root / PENDING_DIR / "settings.json").write_text("hong", encoding="utf-8")

    result = service.apply_pending_restore()
    assert not result.applied
    assert result.errors
    # fail-closed: dữ liệu gốc giữ nguyên, thư mục chờ giữ lại để truy vết
    assert json.loads((root / "settings.json").read_text(encoding="utf-8"))[
        "language"
    ] == "en"
    assert (root / PENDING_DIR / REQUEST_NAME).is_file()


def test_retention_keeps_five_generations(tmp_path):
    root = tmp_path / "appdata"
    _seed_user_data(root)
    service = BackupService(app_data_root=root)
    for _ in range(7):
        service.create_backup()
    backups = list((root / "backups").glob("backup-*.zip"))
    assert len(backups) == 5


def test_restore_old_journal_db_migrates_on_open(tmp_path):
    # DB "cũ" chỉ có migration 001 — restore lên máy mới rồi mở bằng
    # JournalService: migrations tự nâng cấp idempotent (hành vi hiện có).
    root = tmp_path / "appdata"
    root.mkdir(parents=True)
    old_db = root / "journal.db"
    conn = sqlite3.connect(old_db)
    conn.executescript((MIGRATIONS_DIR / "001_create_journal.sql").read_text(encoding="utf-8"))
    conn.execute(
        "CREATE TABLE schema_migrations "
        "(version TEXT PRIMARY KEY, applied_at_utc TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO schema_migrations VALUES ('001_create_journal', '2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO journal_entries (timestamp_utc, saved_at_utc, symbol, mode, analysis_json) "
        "VALUES ('2026-06-15T15:00:00Z', '2026-06-15T15:00:01Z', 'EUR/USD', 'scanner_detail', '{}')"
    )
    conn.commit()
    conn.close()

    backup = BackupService(app_data_root=root).create_backup(
        dest_dir=tmp_path / "out"
    )

    new_root = tmp_path / "newapp"
    new_service = BackupService(app_data_root=new_root)
    staged = new_service.stage_restore(backup.zip_path)
    assert staged.ok, staged.errors
    applied = new_service.apply_pending_restore()
    assert applied.applied, applied.errors

    JournalService(db_path=new_root / "journal.db")
    with sqlite3.connect(new_root / "journal.db") as check:
        versions = {row[0] for row in check.execute("SELECT version FROM schema_migrations")}
        expected = {path.stem for path in MIGRATIONS_DIR.glob("*.sql")}
        assert expected <= versions
        rows = check.execute("SELECT symbol FROM journal_entries").fetchall()
    assert rows == [("EUR/USD",)]
