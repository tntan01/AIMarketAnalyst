"""Read-only storage inventory for AI Market Analyst runtime data.

This tool is intentionally safe to run before any cleanup work.  It never
creates, moves, or deletes files; ``--dry-run`` is accepted to make that
guarantee explicit in operational runbooks.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import heapq
import json
import os
from pathlib import Path
from typing import Iterable


APP_ID = "ai-market-analyst"
ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class StorageBucket:
    name: str
    file_count: int
    bytes: int


@dataclass(frozen=True)
class StorageFile:
    path: str
    bytes: int
    modified_at: str


@dataclass(frozen=True)
class StorageReport:
    root: str
    exists: bool
    collected_at: str
    file_count: int
    bytes: int
    unreadable_entries: int
    categories: tuple[StorageBucket, ...]
    extensions: tuple[StorageBucket, ...]
    recent_days: tuple[StorageBucket, ...]
    largest_files: tuple[StorageFile, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def default_runtime_root() -> Path:
    """Return the current application's Roaming AppData directory without I/O."""
    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / APP_ID
    return Path.home() / f".{APP_ID}"


def format_bytes(value: int) -> str:
    value = max(0, int(value))
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.2f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    raise AssertionError("unreachable")


def _bucket_rows(values: dict[str, list[int]]) -> tuple[StorageBucket, ...]:
    return tuple(
        StorageBucket(name=name, file_count=count, bytes=size)
        for name, (count, size) in sorted(
            values.items(), key=lambda item: (-item[1][1], item[0].lower())
        )
    )


def _iter_files(root: Path) -> Iterable[Path]:
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        dirnames[:] = [
            name for name in dirnames if not (current_path / name).is_symlink()
        ]
        for filename in filenames:
            yield current_path / filename


def collect_report(
    root: Path,
    *,
    top_files: int = 20,
    recent_days: int = 7,
    now: datetime | None = None,
) -> StorageReport:
    """Collect a bounded, read-only inventory for *root*.

    Files that cannot be stat'ed are counted and skipped so a locked runtime
    file cannot make the report unusable.
    """
    root = root.expanduser().resolve()
    collected_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if not root.is_dir():
        return StorageReport(
            root=str(root),
            exists=False,
            collected_at=collected_at.isoformat(),
            file_count=0,
            bytes=0,
            unreadable_entries=0,
            categories=(),
            extensions=(),
            recent_days=(),
            largest_files=(),
        )

    category_totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    extension_totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    day_totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    largest: list[tuple[int, str, str]] = []
    total_bytes = 0
    file_count = 0
    unreadable = 0
    day_cutoff = collected_at - timedelta(days=max(0, recent_days - 1))

    for path in _iter_files(root):
        try:
            stat = path.stat()
            if not path.is_file():
                continue
        except OSError:
            unreadable += 1
            continue

        size = int(stat.st_size)
        modified_at = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
        relative = path.relative_to(root)
        category = relative.parts[0] if len(relative.parts) > 1 else "[root files]"
        extension = path.suffix.lower() or "[no extension]"

        total_bytes += size
        file_count += 1
        category_totals[category][0] += 1
        category_totals[category][1] += size
        extension_totals[extension][0] += 1
        extension_totals[extension][1] += size
        if modified_at >= day_cutoff:
            day = modified_at.date().isoformat()
            day_totals[day][0] += 1
            day_totals[day][1] += size

        candidate = (size, relative.as_posix(), modified_at.isoformat())
        if len(largest) < max(0, top_files):
            heapq.heappush(largest, candidate)
        elif largest and candidate[0] > largest[0][0]:
            heapq.heapreplace(largest, candidate)

    largest_files = tuple(
        StorageFile(path=path, bytes=size, modified_at=modified_at)
        for size, path, modified_at in sorted(largest, reverse=True)
    )
    return StorageReport(
        root=str(root),
        exists=True,
        collected_at=collected_at.isoformat(),
        file_count=file_count,
        bytes=total_bytes,
        unreadable_entries=unreadable,
        categories=_bucket_rows(category_totals),
        extensions=_bucket_rows(extension_totals),
        recent_days=_bucket_rows(day_totals),
        largest_files=largest_files,
    )


def render_text(report: StorageReport) -> str:
    lines = [
        f"Runtime root: {report.root}",
        f"Exists: {report.exists}",
        f"Collected (UTC): {report.collected_at}",
        f"Total: {format_bytes(report.bytes)} across {report.file_count:,} files",
        f"Unreadable entries: {report.unreadable_entries}",
    ]
    if not report.exists:
        return "\n".join(lines)

    def append_buckets(title: str, buckets: tuple[StorageBucket, ...]) -> None:
        lines.append("")
        lines.append(title)
        for bucket in buckets:
            lines.append(
                f"  {bucket.name}: {format_bytes(bucket.bytes)} "
                f"({bucket.file_count:,} files)"
            )

    append_buckets("By top-level category:", report.categories)
    append_buckets("By extension:", report.extensions)
    append_buckets("Created/modified in recent days:", report.recent_days)
    if report.largest_files:
        lines.append("")
        lines.append("Largest files:")
        for item in report.largest_files:
            lines.append(
                f"  {format_bytes(item.bytes)}  {item.modified_at}  {item.path}"
            )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only inventory of AI Market Analyst runtime storage."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=default_runtime_root(),
        help="Runtime directory to inspect (default: %%APPDATA%%/ai-market-analyst).",
    )
    parser.add_argument("--top-files", type=int, default=20)
    parser.add_argument("--recent-days", type=int, default=7)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicitly confirm that the inventory makes no file changes.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = collect_report(
        args.root,
        top_files=max(0, args.top_files),
        recent_days=max(0, args.recent_days),
    )
    if args.format == "json":
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        if args.dry_run:
            print("DRY RUN: this command only reads file metadata and contents are not changed.")
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
