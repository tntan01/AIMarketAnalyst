"""Archive oversized active runtime logs before resetting them.

The default is a read-only preview.  ``--apply`` first writes gzip archives and
a manifest, then truncates only the two active log files named below.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil


LOG_NAMES = ("app.log", "scanner-events.jsonl")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_logs(root: Path, backup_root: Path, *, apply: bool) -> dict[str, object]:
    logs_dir = root / "logs"
    targets = [logs_dir / name for name in LOG_NAMES if (logs_dir / name).is_file()]
    report: dict[str, object] = {
        "dry_run": not apply,
        "runtime_root": str(root),
        "backup_root": str(backup_root),
        "targets": [{"path": str(path), "bytes": path.stat().st_size} for path in targets],
        "archived": [],
        "errors": [],
    }
    if not apply:
        return report

    backup_root.mkdir(parents=True, exist_ok=True)
    archived: list[dict[str, object]] = []
    for source in targets:
        destination = backup_root / f"{source.name}.gz"
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        try:
            with source.open("rb") as input_handle, gzip.open(temporary, "wb") as output_handle:
                shutil.copyfileobj(input_handle, output_handle, length=1024 * 1024)
            temporary.replace(destination)
            archived.append({
                "source": str(source),
                "source_bytes": source.stat().st_size,
                "archive": str(destination),
                "archive_bytes": destination.stat().st_size,
                "archive_sha256": _sha256(destination),
            })
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            report["errors"].append(f"{source}: {exc}")

    if report["errors"]:
        report["archived"] = archived
        return report

    manifest = backup_root / "manifest.json"
    manifest.write_text(json.dumps({"archived_at": datetime.now(timezone.utc).isoformat(), "files": archived}, indent=2), encoding="utf-8")
    for source in targets:
        with source.open("wb"):
            pass
    report["archived"] = archived
    return report


def main() -> int:
    appdata = Path(os.environ.get("APPDATA", Path.home())) / "ai-market-analyst"
    localappdata = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AI Market Analyst Backups"
    parser = argparse.ArgumentParser(description="Archive and reset active runtime logs.")
    parser.add_argument("--root", type=Path, default=appdata)
    parser.add_argument("--backup-root", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("phase6-%Y%m%dT%H%M%SZ")
    backup_root = args.backup_root or localappdata / stamp
    result = archive_logs(args.root, backup_root, apply=args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
