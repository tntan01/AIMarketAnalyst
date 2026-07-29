"""Preview or explicitly apply scanner-runtime retention."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.runtime_retention_service import RuntimeRetentionService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prune scanner artifacts according to the bounded retention policy."
    )
    parser.add_argument("--root", type=Path, help="Override the runtime root.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete only artifacts created after the retention epoch.",
    )
    parser.add_argument(
        "--include-legacy",
        action="store_true",
        help="Include pre-retention artifacts; requires --apply.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.include_legacy and not args.apply:
        raise SystemExit("--include-legacy requires --apply")
    service = RuntimeRetentionService(args.root)
    result = service.prune(
        dry_run=not args.apply,
        include_legacy=args.include_legacy,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
