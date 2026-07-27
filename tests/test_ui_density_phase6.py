from __future__ import annotations

from itertools import product
import hashlib
import json
from pathlib import Path

import pytest

from tools.ui_layout_audit import (
    DPI_PROFILES,
    SCREEN_FACTORIES,
    VIEWPORT_PROFILES,
)


ROOT = Path(__file__).resolve().parents[1]
RESPONSIVE_REPORT = ROOT / "docs" / "ui-responsive-report.json"
VISUAL_MANIFEST = (
    ROOT
    / "docs"
    / "ui-baseline"
    / "density-phase6"
    / "screenshot-manifest.json"
)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_responsive_matrix_covers_every_theme_dpi_route_and_viewport() -> None:
    report = _json(RESPONSIVE_REPORT)
    assert report["schema_version"] == 2
    assert report["external_services"] == "disabled"
    assert report["issue_count"] == 0
    results = report["results"]
    expected = set(
        product(
            ("dark", "light"),
            DPI_PROFILES,
            SCREEN_FACTORIES,
            VIEWPORT_PROFILES,
        )
    )
    actual = {
        (
            item["theme"],
            item["dpi_profile"],
            item["route"],
            item["profile"],
        )
        for item in results
    }
    assert actual == expected
    assert len(results) == 288

    for item in results:
        assert item["issues"] == []
        assert item["device_pixel_ratio"] == pytest.approx(
            DPI_PROFILES[item["dpi_profile"]]
        )
        assert item["screen_size"]["width"] <= item["viewport"]["width"]
        assert item["screen_size"]["height"] <= item["viewport"]["height"]


def test_visual_manifest_has_a_real_image_for_every_theme_dpi_and_route() -> None:
    manifest = _json(VISUAL_MANIFEST)
    assert manifest["external_services"] == "disabled"
    assert manifest["failures"] == []
    captures = manifest["captures"]
    expected = set(product(("dark", "light"), DPI_PROFILES, SCREEN_FACTORIES))
    actual = {
        (item["theme"], item["dpi_profile"], item["route"])
        for item in captures
    }
    assert actual == expected
    assert len(captures) == 48

    for item in captures:
        path = ROOT / item["path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
        scale = DPI_PROFILES[item["dpi_profile"]]
        assert item["rendered_size"] == {
            "width": round(item["viewport"]["width"] * scale),
            "height": round(item["viewport"]["height"] * scale),
        }
