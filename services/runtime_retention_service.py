"""Bounded retention for scanner runtime artifacts.

The first launch after this service is installed records a retention epoch.
Older artifacts are treated as legacy evidence and are never removed by the
automatic job.  They remain available for the explicit, reviewed cleanup step.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
from typing import Iterable

MIB = 1024 * 1024
RETENTION_MARKER_NAME = ".scanner-retention-v1.json"
APP_ID = "ai-market-analyst"


@dataclass(frozen=True)
class ScannerRetentionPolicy:
    full_max_age: timedelta = timedelta(hours=24)
    summary_max_age: timedelta = timedelta(days=7)
    max_full_scans: int = 50
    max_summary_scans: int = 500
    max_full_bytes: int = 500 * MIB
    max_summary_bytes: int = 300 * MIB
    max_total_bytes: int = 800 * MIB


@dataclass(frozen=True)
class ScannerArtifact:
    scan_id: str
    analysis_dir: Path | None
    summary_path: Path | None
    analysis_bytes: int
    summary_bytes: int
    oldest_modified: datetime
    newest_modified: datetime

    @property
    def total_bytes(self) -> int:
        return self.analysis_bytes + self.summary_bytes


@dataclass(frozen=True)
class RetentionResult:
    dry_run: bool
    managed_since: str
    examined_scans: int
    protected_legacy_scans: int
    removed_scan_ids: tuple[str, ...]
    reclaimed_bytes: int
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "dry_run": self.dry_run,
            "managed_since": self.managed_since,
            "examined_scans": self.examined_scans,
            "protected_legacy_scans": self.protected_legacy_scans,
            "removed_scan_ids": list(self.removed_scan_ids),
            "reclaimed_bytes": self.reclaimed_bytes,
            "errors": list(self.errors),
        }


class RuntimeRetentionService:
    def __init__(
        self,
        root: Path | None = None,
        *,
        policy: ScannerRetentionPolicy = ScannerRetentionPolicy(),
    ) -> None:
        self.root = root
        self.policy = policy

    def runtime_root(self) -> Path:
        return (self.root or _default_runtime_root()).resolve()

    def marker_path(self) -> Path:
        return self.runtime_root() / RETENTION_MARKER_NAME

    def ensure_started(self, *, now: datetime | None = None) -> datetime:
        """Return the retention epoch, creating it only when absent."""
        existing = self._load_epoch()
        if existing is not None:
            return existing
        started_at = _as_utc(now or datetime.now(timezone.utc))
        marker = self.marker_path()
        marker.parent.mkdir(parents=True, exist_ok=True)
        temporary = marker.with_name(f"{marker.name}.tmp")
        temporary.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "managed_since": started_at.isoformat(),
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(marker)
        return started_at

    def prune(
        self,
        *,
        dry_run: bool = False,
        include_legacy: bool = False,
        now: datetime | None = None,
    ) -> RetentionResult:
        """Prune managed scanner pairs while preserving legacy artifacts by default."""
        current_time = _as_utc(now or datetime.now(timezone.utc))
        managed_since = (
            datetime.min.replace(tzinfo=timezone.utc)
            if include_legacy
            else (
                self._load_epoch()
                or (current_time if dry_run else self.ensure_started(now=current_time))
            )
        )
        artifacts = list(self._collect_artifacts())
        managed = [
            artifact
            for artifact in artifacts
            if include_legacy or artifact.oldest_modified >= managed_since
        ]
        protected_legacy = len(artifacts) - len(managed)
        selected = self._select_for_removal(managed, current_time)
        selected = sorted(selected, key=lambda item: (item.newest_modified, item.scan_id))

        errors: list[str] = []
        removed_ids: list[str] = []
        reclaimed_bytes = 0
        for artifact in selected:
            if dry_run:
                removed_ids.append(artifact.scan_id)
                reclaimed_bytes += artifact.total_bytes
                continue
            try:
                self._delete_pair(artifact)
            except OSError as exc:
                errors.append(f"{artifact.scan_id}: {exc}")
                continue
            removed_ids.append(artifact.scan_id)
            reclaimed_bytes += artifact.total_bytes

        return RetentionResult(
            dry_run=dry_run,
            managed_since=managed_since.isoformat(),
            examined_scans=len(artifacts),
            protected_legacy_scans=protected_legacy,
            removed_scan_ids=tuple(removed_ids),
            reclaimed_bytes=reclaimed_bytes,
            errors=tuple(errors),
        )

    def _load_epoch(self) -> datetime | None:
        marker = self.marker_path()
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
            raw = data.get("managed_since") if isinstance(data, dict) else None
            if not isinstance(raw, str):
                return None
            return _as_utc(datetime.fromisoformat(raw))
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    def _collect_artifacts(self) -> Iterable[ScannerArtifact]:
        root = self.runtime_root()
        analysis_root = root / "scanner_analysis"
        snapshot_root = root / "scanner_snapshots"
        analysis_dirs = {
            path.name: path
            for path in analysis_root.iterdir()
            if path.is_dir() and not path.is_symlink()
        } if analysis_root.is_dir() else {}
        summaries = {
            _scan_id_from_summary(path): path
            for path in snapshot_root.glob("scanner_*.json")
            if path.is_file() and not path.is_symlink() and _scan_id_from_summary(path)
        } if snapshot_root.is_dir() else {}

        for scan_id in sorted(set(analysis_dirs) | set(summaries)):
            analysis_dir = analysis_dirs.get(scan_id)
            summary_path = summaries.get(scan_id)
            analysis_bytes, analysis_times = _directory_stats(analysis_dir)
            summary_bytes, summary_times = _file_stats(summary_path)
            timestamps = analysis_times + summary_times
            if not timestamps:
                continue
            yield ScannerArtifact(
                scan_id=scan_id,
                analysis_dir=analysis_dir,
                summary_path=summary_path,
                analysis_bytes=analysis_bytes,
                summary_bytes=summary_bytes,
                oldest_modified=min(timestamps),
                newest_modified=max(timestamps),
            )

    def _select_for_removal(
        self,
        artifacts: list[ScannerArtifact],
        now: datetime,
    ) -> set[ScannerArtifact]:
        selected: set[ScannerArtifact] = set()

        for artifact in artifacts:
            if (
                artifact.analysis_dir is not None
                and artifact.newest_modified < now - self.policy.full_max_age
            ):
                selected.add(artifact)
            elif (
                artifact.summary_path is not None
                and artifact.newest_modified < now - self.policy.summary_max_age
            ):
                selected.add(artifact)

        self._select_by_count(
            artifacts,
            selected,
            self.policy.max_full_scans,
            lambda artifact: artifact.analysis_dir is not None,
        )
        self._select_by_count(
            artifacts,
            selected,
            self.policy.max_summary_scans,
            lambda artifact: artifact.summary_path is not None,
        )
        self._select_by_bytes(
            artifacts,
            selected,
            self.policy.max_full_bytes,
            lambda artifact: artifact.analysis_bytes,
        )
        self._select_by_bytes(
            artifacts,
            selected,
            self.policy.max_summary_bytes,
            lambda artifact: artifact.summary_bytes,
        )
        self._select_by_bytes(
            artifacts,
            selected,
            self.policy.max_total_bytes,
            lambda artifact: artifact.total_bytes,
        )
        return selected

    @staticmethod
    def _select_by_count(
        artifacts: list[ScannerArtifact],
        selected: set[ScannerArtifact],
        limit: int,
        matches,
    ) -> None:
        candidates = sorted(
            (artifact for artifact in artifacts if matches(artifact) and artifact not in selected),
            key=lambda artifact: (artifact.newest_modified, artifact.scan_id),
            reverse=True,
        )
        selected.update(candidates[max(0, limit):])

    @staticmethod
    def _select_by_bytes(
        artifacts: list[ScannerArtifact],
        selected: set[ScannerArtifact],
        limit: int,
        size_of,
    ) -> None:
        remaining = [artifact for artifact in artifacts if artifact not in selected]
        total = sum(size_of(artifact) for artifact in remaining)
        for artifact in sorted(
            remaining,
            key=lambda item: (item.newest_modified, item.scan_id),
        ):
            if total <= limit:
                break
            selected.add(artifact)
            total -= size_of(artifact)

    def _delete_pair(self, artifact: ScannerArtifact) -> None:
        root = self.runtime_root()
        for path in (artifact.summary_path, artifact.analysis_dir):
            if path is None:
                continue
            _assert_within(path, root)
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)


def _scan_id_from_summary(path: Path) -> str:
    prefix = "scanner_"
    if not path.name.startswith(prefix) or path.suffix != ".json":
        return ""
    return path.name[len(prefix):-len(path.suffix)]


def _default_runtime_root() -> Path:
    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / APP_ID
    return Path.home() / f".{APP_ID}"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _file_stats(path: Path | None) -> tuple[int, list[datetime]]:
    if path is None:
        return 0, []
    stat = path.stat()
    return stat.st_size, [datetime.fromtimestamp(stat.st_mtime, timezone.utc)]


def _directory_stats(path: Path | None) -> tuple[int, list[datetime]]:
    if path is None:
        return 0, []
    timestamps = [datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)]
    total = 0
    for current, dirnames, filenames in os.walk(path, followlinks=False):
        current_path = Path(current)
        dirnames[:] = [
            name for name in dirnames if not (current_path / name).is_symlink()
        ]
        for filename in filenames:
            file_path = current_path / filename
            try:
                stat = file_path.stat()
            except OSError:
                continue
            total += stat.st_size
            timestamps.append(datetime.fromtimestamp(stat.st_mtime, timezone.utc))
    return total, timestamps


def _assert_within(path: Path, root: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise OSError(f"Refusing to remove path outside runtime root: {path}") from exc


scanner_retention = RuntimeRetentionService()
