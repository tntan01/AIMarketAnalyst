from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

from services.runtime_retention_service import (
    MIB,
    RuntimeRetentionService,
    ScannerRetentionPolicy,
)


NOW = datetime(2026, 7, 29, 12, tzinfo=timezone.utc)


def _set_mtime(path: Path, value: datetime) -> None:
    timestamp = value.timestamp()
    os.utime(path, (timestamp, timestamp))


def _create_scan(root: Path, scan_id: str, *, size: int, modified_at: datetime) -> None:
    analysis_dir = root / "scanner_analysis" / scan_id
    analysis_dir.mkdir(parents=True)
    analysis = analysis_dir / "EURUSD.json"
    analysis.write_bytes(b"x" * size)
    summary = root / "scanner_snapshots" / f"scanner_{scan_id}.json"
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text("{}", encoding="utf-8")
    _set_mtime(analysis, modified_at)
    _set_mtime(analysis_dir, modified_at)
    _set_mtime(summary, modified_at)


def test_retention_preserves_legacy_and_prunes_expired_managed_pair(tmp_path: Path) -> None:
    service = RuntimeRetentionService(
        tmp_path,
        policy=ScannerRetentionPolicy(full_max_age=timedelta(hours=1)),
    )
    service.ensure_started(now=NOW - timedelta(days=2))
    _create_scan(tmp_path, "legacy", size=10, modified_at=NOW - timedelta(days=3))
    _create_scan(tmp_path, "managed", size=10, modified_at=NOW - timedelta(days=1))

    result = service.prune(now=NOW)

    assert result.removed_scan_ids == ("managed",)
    assert result.protected_legacy_scans == 1
    assert (tmp_path / "scanner_analysis" / "legacy").exists()
    assert (tmp_path / "scanner_snapshots" / "scanner_legacy.json").exists()
    assert not (tmp_path / "scanner_analysis" / "managed").exists()
    assert not (tmp_path / "scanner_snapshots" / "scanner_managed.json").exists()


def test_retention_prunes_oldest_pairs_to_meet_count_and_byte_limits(tmp_path: Path) -> None:
    policy = ScannerRetentionPolicy(
        full_max_age=timedelta(days=30),
        summary_max_age=timedelta(days=30),
        max_full_scans=2,
        max_summary_scans=2,
        max_full_bytes=2 * MIB,
        max_summary_bytes=2 * MIB,
        max_total_bytes=2 * MIB + 1024,
    )
    service = RuntimeRetentionService(tmp_path, policy=policy)
    service.ensure_started(now=NOW - timedelta(days=1))
    _create_scan(tmp_path, "old", size=MIB, modified_at=NOW - timedelta(hours=3))
    _create_scan(tmp_path, "middle", size=MIB, modified_at=NOW - timedelta(hours=2))
    _create_scan(tmp_path, "new", size=MIB, modified_at=NOW - timedelta(hours=1))

    result = service.prune(now=NOW)

    assert result.removed_scan_ids == ("old",)
    assert not (tmp_path / "scanner_analysis" / "old").exists()
    assert (tmp_path / "scanner_analysis" / "middle").exists()
    assert (tmp_path / "scanner_analysis" / "new").exists()


def test_retention_dry_run_does_not_delete_managed_artifacts(tmp_path: Path) -> None:
    service = RuntimeRetentionService(
        tmp_path,
        policy=ScannerRetentionPolicy(full_max_age=timedelta(hours=1)),
    )
    service.ensure_started(now=NOW - timedelta(days=2))
    _create_scan(tmp_path, "expired", size=10, modified_at=NOW - timedelta(days=1))

    result = service.prune(dry_run=True, now=NOW)

    assert result.dry_run is True
    assert result.removed_scan_ids == ("expired",)
    assert (tmp_path / "scanner_analysis" / "expired").exists()
    assert (tmp_path / "scanner_snapshots" / "scanner_expired.json").exists()
