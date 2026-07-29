from pathlib import Path

from tools.runtime_log_archive import archive_logs


def test_preview_does_not_change_logs(tmp_path: Path):
    log = tmp_path / "logs" / "app.log"
    log.parent.mkdir()
    log.write_text("event\n", encoding="utf-8")

    result = archive_logs(tmp_path, tmp_path / "backup", apply=False)

    assert result["dry_run"] is True
    assert log.read_text(encoding="utf-8") == "event\n"
    assert not (tmp_path / "backup").exists()


def test_apply_archives_then_resets_only_known_logs(tmp_path: Path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "app.log").write_text("app event\n", encoding="utf-8")
    (logs / "scanner-events.jsonl").write_text('{"event": 1}\n', encoding="utf-8")
    unrelated = logs / "keep.txt"
    unrelated.write_text("keep", encoding="utf-8")

    backup = tmp_path / "backup"
    result = archive_logs(tmp_path, backup, apply=True)

    assert result["errors"] == []
    assert (logs / "app.log").stat().st_size == 0
    assert (logs / "scanner-events.jsonl").stat().st_size == 0
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert (backup / "app.log.gz").exists()
    assert (backup / "scanner-events.jsonl.gz").exists()
    assert (backup / "manifest.json").exists()
