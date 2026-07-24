#!/usr/bin/env python3
"""Build a Phase-7 SMC replay/calibration report from JSON or JSONL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.smc_validation import (  # noqa: E402
    DEFAULT_MIN_CALIBRATION_BUCKET_SAMPLES,
    DEFAULT_MIN_OOS_SAMPLES,
    DEFAULT_MIN_WALK_FORWARD_SAMPLES,
    DEFAULT_MIN_WALK_FORWARD_WINDOWS,
    DEFAULT_OOS_DEGRADATION_TOLERANCE_R,
    build_smc_validation_report,
    replay_sample_from_analysis_document,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Tạo báo cáo replay, OOS và calibration cho SMC legacy/v2."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Tệp JSON/JSONL chứa replay samples hoặc analysis documents.",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Đường dẫn JSON report đầu ra.",
    )
    parser.add_argument(
        "--min-oos-samples",
        type=int,
        default=DEFAULT_MIN_OOS_SAMPLES,
    )
    parser.add_argument(
        "--min-bucket-samples",
        type=int,
        default=DEFAULT_MIN_CALIBRATION_BUCKET_SAMPLES,
    )
    parser.add_argument(
        "--oos-tolerance-r",
        type=float,
        default=DEFAULT_OOS_DEGRADATION_TOLERANCE_R,
    )
    parser.add_argument(
        "--min-walk-forward-windows",
        type=int,
        default=DEFAULT_MIN_WALK_FORWARD_WINDOWS,
    )
    parser.add_argument(
        "--min-walk-forward-samples",
        type=int,
        default=DEFAULT_MIN_WALK_FORWARD_SAMPLES,
    )
    parser.add_argument(
        "--fail-on-block",
        action="store_true",
        help="Trả exit code 2 nếu release gate chưa đạt.",
    )
    return parser


def load_validation_samples(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"Input file does not exist: {path}")
    if path.suffix.lower() == ".jsonl":
        values = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            values = payload
        elif isinstance(payload, dict) and isinstance(
            payload.get("samples"), list
        ):
            values = payload["samples"]
        else:
            values = [payload]

    samples: list[dict[str, Any]] = []
    for value in values:
        if not isinstance(value, dict):
            samples.append({})
            continue
        if (
            isinstance(value.get("analysis_result"), dict)
            and not isinstance(value.get("legacy_scores"), dict)
        ):
            metadata = (
                value.get("validation_metadata")
                if isinstance(value.get("validation_metadata"), dict)
                else {}
            )
            samples.append(replay_sample_from_analysis_document(
                value,
                result_r=_optional_float(
                    metadata.get("result_r", value.get("result_r"))
                ),
                dataset_split=str(
                    metadata.get(
                        "dataset_split",
                        value.get("dataset_split", "unknown"),
                    )
                ),
                asset_class=str(
                    metadata.get(
                        "asset_class",
                        value.get("asset_class", "unknown"),
                    )
                ),
                v2_status=str(
                    metadata.get(
                        "v2_status",
                        value.get("v2_status", ""),
                    )
                    or ""
                )
                or None,
            ))
        else:
            samples.append(value)
    return samples


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        samples = load_validation_samples(args.input)
        report = build_smc_validation_report(
            samples,
            min_oos_samples=args.min_oos_samples,
            min_calibration_bucket_samples=args.min_bucket_samples,
            oos_degradation_tolerance_r=args.oos_tolerance_r,
            min_walk_forward_windows=args.min_walk_forward_windows,
            min_walk_forward_samples=args.min_walk_forward_samples,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"SMC validation input error: {exc}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    gate = report["release_gate"]
    print(
        f"SMC validation report: {args.output} | "
        f"samples={report['sample_count']} | ready={gate['ready']}"
    )
    if args.fail_on_block and not gate["ready"]:
        return 2
    return 0


def _optional_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
