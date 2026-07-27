"""Detect unexpectedly large neutral-bright surfaces in dark-theme screenshots.

The audit deliberately looks for connected bright areas instead of counting
all bright pixels. Text, icons and chart labels are expected to be bright in a
dark theme, but they form small disconnected components. A light viewport or
canvas forms a much larger connected component and is therefore actionable.
"""

from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from PyQt6.QtGui import QImage


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    ROOT / "docs" / "ui-baseline" / "current" / "screenshot-manifest.json"
)
DEFAULT_OUTPUT = ROOT / "docs" / "dark-surface-report.json"


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def _rgb_array(path: Path) -> np.ndarray:
    image = QImage(str(path))
    if image.isNull():
        raise ValueError(f"Cannot load screenshot: {path}")
    image = image.convertToFormat(QImage.Format.Format_RGB888)
    width = image.width()
    height = image.height()
    stride = image.bytesPerLine()
    bits = image.bits()
    bits.setsize(stride * height)
    rows = np.frombuffer(bits, dtype=np.uint8).reshape(height, stride)
    return rows[:, : width * 3].reshape(height, width, 3).copy()


def _largest_component(mask: np.ndarray) -> tuple[int, tuple[int, int, int, int]]:
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=np.bool_)
    largest_area = 0
    largest_bounds = (0, 0, 0, 0)

    for start_y, start_x in zip(*np.nonzero(mask)):
        y = int(start_y)
        x = int(start_x)
        if visited[y, x]:
            continue
        queue: deque[tuple[int, int]] = deque([(y, x)])
        visited[y, x] = True
        area = 0
        min_x = max_x = x
        min_y = max_y = y
        while queue:
            current_y, current_x = queue.popleft()
            area += 1
            min_x = min(min_x, current_x)
            max_x = max(max_x, current_x)
            min_y = min(min_y, current_y)
            max_y = max(max_y, current_y)
            for next_y, next_x in (
                (current_y - 1, current_x),
                (current_y + 1, current_x),
                (current_y, current_x - 1),
                (current_y, current_x + 1),
            ):
                if (
                    0 <= next_y < height
                    and 0 <= next_x < width
                    and mask[next_y, next_x]
                    and not visited[next_y, next_x]
                ):
                    visited[next_y, next_x] = True
                    queue.append((next_y, next_x))
        if area > largest_area:
            largest_area = area
            largest_bounds = (
                min_x,
                min_y,
                max_x - min_x + 1,
                max_y - min_y + 1,
            )
    return largest_area, largest_bounds


def analyze_image(
    path: Path,
    *,
    brightness_threshold: int = 215,
    neutral_tolerance: int = 30,
    max_sample_dimension: int = 800,
    component_ratio_threshold: float = 0.005,
) -> dict[str, Any]:
    rgb = _rgb_array(path)
    original_height, original_width, _ = rgb.shape
    sample_step = max(
        1,
        math.ceil(max(original_width, original_height) / max_sample_dimension),
    )
    sampled = rgb[::sample_step, ::sample_step]
    channel_min = sampled.min(axis=2)
    channel_max = sampled.max(axis=2)
    mask = (channel_min >= brightness_threshold) & (
        channel_max - channel_min <= neutral_tolerance
    )
    bright_pixels = int(mask.sum())
    sample_pixels = int(mask.size)
    largest_area, bounds = _largest_component(mask)
    scale_x = original_width / sampled.shape[1]
    scale_y = original_height / sampled.shape[0]
    scaled_bounds = {
        "x": round(bounds[0] * scale_x),
        "y": round(bounds[1] * scale_y),
        "width": round(bounds[2] * scale_x),
        "height": round(bounds[3] * scale_y),
    }
    bright_ratio = bright_pixels / sample_pixels if sample_pixels else 0.0
    component_ratio = largest_area / sample_pixels if sample_pixels else 0.0
    return {
        "path": _relative(path),
        "width": original_width,
        "height": original_height,
        "sample_step": sample_step,
        "neutral_bright_ratio": round(bright_ratio, 6),
        "largest_component_ratio": round(component_ratio, 6),
        "largest_component": scaled_bounds,
        "flagged": component_ratio >= component_ratio_threshold,
    }


def build_report(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    component_ratio_threshold: float = 0.005,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    for capture in manifest.get("captures", []):
        if capture.get("theme") != "dark":
            continue
        image_path = ROOT / str(capture["path"])
        result = analyze_image(
            image_path,
            component_ratio_threshold=component_ratio_threshold,
        )
        result.update(
            {
                "name": capture.get("name", image_path.stem),
                "kind": capture.get("kind", "unknown"),
            }
        )
        results.append(result)
    flagged = [item for item in results if item["flagged"]]
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_manifest": _relative(manifest_path),
        "theme": "dark",
        "policy": {
            "brightness_threshold": 215,
            "neutral_tolerance": 30,
            "largest_component_ratio_threshold": component_ratio_threshold,
            "note": (
                "Flagged means a connected neutral-bright surface occupies "
                "at least the configured share of the screenshot; manual "
                "classification is still required."
            ),
        },
        "capture_count": len(results),
        "flagged_count": len(flagged),
        "flagged_names": [item["name"] for item in flagged],
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--write", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--component-ratio-threshold",
        type=float,
        default=0.005,
    )
    args = parser.parse_args()
    report = build_report(
        args.manifest,
        component_ratio_threshold=args.component_ratio_threshold,
    )
    args.write.parent.mkdir(parents=True, exist_ok=True)
    args.write.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Dark surface audit: {report['capture_count']} captures, "
        f"{report['flagged_count']} flagged; report={args.write}"
    )
    return 1 if report["flagged_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
