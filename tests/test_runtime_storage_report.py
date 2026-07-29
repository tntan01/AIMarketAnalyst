"""Tests for the read-only runtime storage inventory tool."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

from tools.runtime_storage_report import (
    build_parser,
    collect_report,
    format_bytes,
    render_text,
)


def _write(path: Path, payload: bytes, modified_at: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    timestamp = modified_at.timestamp()
    os.utime(path, (timestamp, timestamp))


def test_collect_report_groups_categories_extensions_and_recent_days(tmp_path: Path) -> None:
    now = datetime(2026, 7, 29, 12, tzinfo=timezone.utc)
    _write(tmp_path / "logs" / "app.log", b"x" * 20, now)
    _write(tmp_path / "scanner_analysis" / "scan-1" / "EURUSD.json", b"x" * 40, now)
    _write(
        tmp_path / "scanner_snapshots" / "scan.json",
        b"x" * 10,
        now - timedelta(days=9),
    )
    _write(tmp_path / "settings.json", b"{}", now)

    report = collect_report(tmp_path, top_files=2, recent_days=7, now=now)

    assert report.exists is True
    assert report.file_count == 4
    assert report.bytes == 72
    assert [(item.name, item.bytes) for item in report.categories] == [
        ("scanner_analysis", 40),
        ("logs", 20),
        ("scanner_snapshots", 10),
        ("[root files]", 2),
    ]
    assert [(item.name, item.bytes) for item in report.extensions] == [
        (".json", 52),
        (".log", 20),
    ]
    assert [(item.name, item.bytes) for item in report.recent_days] == [
        ("2026-07-29", 62)
    ]
    assert [item.bytes for item in report.largest_files] == [40, 20]
    assert "scanner_analysis" in render_text(report)


def test_collect_report_handles_missing_directory(tmp_path: Path) -> None:
    report = collect_report(tmp_path / "missing")

    assert report.exists is False
    assert report.file_count == 0
    assert report.categories == ()


def test_cli_defaults_are_read_only_inventory() -> None:
    args = build_parser().parse_args(["--dry-run", "--format", "json"])

    assert args.dry_run is True
    assert args.format == "json"
    assert args.top_files == 20
    assert args.recent_days == 7


def test_format_bytes() -> None:
    assert format_bytes(12) == "12 B"
    assert format_bytes(1024) == "1.00 KiB"
    assert format_bytes(3 * 1024 * 1024) == "3.00 MiB"
