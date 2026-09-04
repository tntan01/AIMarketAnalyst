"""Contract test cho bộ icon phẳng `ui/icons.py`.

Khóa hành vi của registry + renderer + FlatIconEngine trước khi tích hợp vào
UI: glyph render đúng màu role, Normal/Disabled/Active mode tách biệt, lazy
re-tint khi đổi theme, cache bounded. Chạy headless với QT_QPA_PLATFORM=offscreen.
"""

from __future__ import annotations

import base64
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys

import pytest
from PyQt6.QtGui import QIcon, QImage
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

from ui.icons import (  # noqa: E402
    ICONS,
    FlatIconEngine,
    _renderer_cache,
    _svg_bytes,
    clear_icon_caches,
    flat_icon,
    flat_pixmap,
)
from ui.theme import DARK_PALETTE, LIGHT_PALETTE, color_for_role  # noqa: E402
from ui.theme_manager import APP_THEME_PROPERTY, current_palette  # noqa: E402

REQUIRED_GLYPHS = {
    "refresh",
    "help-circle",
    "map-pin",
    "bot",
    "x",
    "plug",
    "user",
    "bar-chart",
    "external-link",
    "calendar",
    "zap",
    "eye",
}


def _first_visible_pixel(pixmap) -> tuple[int, int, int] | None:
    image = pixmap.toImage()
    for x in range(image.width()):
        for y in range(image.height()):
            color = image.pixelColor(x, y)
            if color.alpha() > 100:
                return (color.red(), color.green(), color.blue())
    return None


def _approx(actual: tuple[int, int, int], expected_hex: str, tolerance: int = 14) -> bool:
    expected_hex = expected_hex.lstrip("#")
    expected = tuple(int(expected_hex[i : i + 2], 16) for i in (0, 2, 4))
    return all(abs(a - e) <= tolerance for a, e in zip(actual, expected))


@pytest.fixture(autouse=True)
def _reset_caches():
    clear_icon_caches()
    yield
    clear_icon_caches()


# ---------------------------------------------------------------------------
# Registry invariants
# ---------------------------------------------------------------------------

def test_registry_has_required_glyphs():
    missing = REQUIRED_GLYPHS - set(ICONS)
    assert not missing, f"Thiếu glyph bắt buộc: {sorted(missing)}"


def test_registry_entries_render_valid_svg():
    for name in ICONS:
        doc = _svg_bytes(name, color_for_role(DARK_PALETTE, "text"))
        renderer = QSvgRenderer(doc)
        assert renderer.isValid(), f"Glyph {name} render SVG không hợp lệ"


def test_registry_svg_has_no_currentcolor_after_tint():
    doc = _svg_bytes("refresh", color_for_role(DARK_PALETTE, "danger")).decode("utf-8")
    assert "currentColor" not in doc


# ---------------------------------------------------------------------------
# flat_pixmap
# ---------------------------------------------------------------------------

def test_flat_pixmap_size_and_content():
    pixmap = flat_pixmap("x", "success", size=16, palette=DARK_PALETTE)
    assert not pixmap.isNull()
    # size logic = 16 (device pixels có thể lớn hơn theo DPR)
    assert abs(pixmap.width() / pixmap.devicePixelRatio() - 16) < 1.5
    pixel = _first_visible_pixel(pixmap)
    assert pixel is not None, "Pixmap rỗng — glyph chưa vẽ gì"
    assert _approx(pixel, DARK_PALETTE.success), f"Màu {pixel} không khớp success dark"


def test_flat_pixmap_role_changes_color():
    success = _first_visible_pixel(flat_pixmap("x", "success", palette=DARK_PALETTE))
    danger = _first_visible_pixel(flat_pixmap("x", "danger", palette=DARK_PALETTE))
    assert success != danger
    assert _approx(success, DARK_PALETTE.success)
    assert _approx(danger, DARK_PALETTE.danger)


def test_flat_pixmap_light_palette_differs():
    dark = _first_visible_pixel(flat_pixmap("x", "danger", palette=DARK_PALETTE))
    light = _first_visible_pixel(flat_pixmap("x", "danger", palette=LIGHT_PALETTE))
    assert dark != light
    assert _approx(light, LIGHT_PALETTE.danger)


def test_flat_pixmap_cache_hit_and_clear():
    first = flat_pixmap("x", "text", palette=DARK_PALETTE)
    second = flat_pixmap("x", "text", palette=DARK_PALETTE)
    assert first is second
    clear_icon_caches()
    third = flat_pixmap("x", "text", palette=DARK_PALETTE)
    assert not third.isNull()


def test_flat_pixmap_unknown_glyph_raises():
    with pytest.raises(KeyError):
        flat_pixmap("glyph-khong-ton-tai")


# ---------------------------------------------------------------------------
# flat_icon / FlatIconEngine
# ---------------------------------------------------------------------------

def test_flat_icon_modes_differ():
    icon = flat_icon("x", "text")
    normal = _first_visible_pixel(icon.pixmap(16, QIcon.Mode.Normal, QIcon.State.Off))
    disabled = _first_visible_pixel(icon.pixmap(16, QIcon.Mode.Disabled, QIcon.State.Off))
    assert normal is not None and disabled is not None
    assert normal != disabled, "Disabled phải render màu muted riêng, không grayscale"


def test_flat_icon_active_role():
    icon = flat_icon("x", "text", active_role="danger")
    normal = _first_visible_pixel(icon.pixmap(16, QIcon.Mode.Normal, QIcon.State.Off))
    active = _first_visible_pixel(icon.pixmap(16, QIcon.Mode.Active, QIcon.State.Off))
    assert normal != active
    assert _approx(active, current_palette().danger)


def test_flat_icon_lazy_retint_on_theme_switch():
    start = "light" if current_palette().name == "light" else "dark"
    target = "dark" if start == "light" else "light"
    app.setProperty(APP_THEME_PROPERTY, start)
    icon = flat_icon("x", "text")
    before = _first_visible_pixel(icon.pixmap(16, QIcon.Mode.Normal, QIcon.State.Off))
    app.setProperty(APP_THEME_PROPERTY, target)
    try:
        after = _first_visible_pixel(icon.pixmap(16, QIcon.Mode.Normal, QIcon.State.Off))
        assert before != after, "QIcon giữ pixmap cũ sau khi đổi theme"
    finally:
        app.setProperty(APP_THEME_PROPERTY, start)


def test_engine_clone_preserves_roles():
    engine = FlatIconEngine("x", "text", 16, "muted", "accent")
    clone = engine.clone()
    assert isinstance(clone, FlatIconEngine)
    assert (clone.name, clone.role, clone.size) == ("x", "text", 16)
    assert clone.disabled_role == "muted"
    assert clone.active_role == "accent"
    assert engine.key() == "FlatIconEngine/x"


def test_renderer_cache_bounded():
    icon = flat_icon("x", "text")
    icon.pixmap(16, QIcon.Mode.Normal, QIcon.State.Off)
    before = len(_renderer_cache)
    for _ in range(200):
        icon.pixmap(16, QIcon.Mode.Normal, QIcon.State.Off)
    assert len(_renderer_cache) == before


def test_module_contains_no_hex_literals():
    import pathlib
    import re

    source = pathlib.Path("ui/icons.py").read_text(encoding="utf-8")
    assert not re.search(r"#[0-9a-fA-F]{3,6}", source), "ui/icons.py cấm hardcode hex"


def test_flat_data_uri_is_valid_png():
    from ui.icons import flat_data_uri

    uri = flat_data_uri("check", "success", size=12)
    assert uri.startswith("data:image/png;base64,")
    payload = base64.b64decode(uri.split(",", 1)[1])
    assert payload[:4] == b"\x89PNG", "payload phải là PNG hợp lệ"


def test_flat_data_uri_color_follows_role():
    from ui.icons import flat_data_uri

    palette = current_palette()
    success = flat_data_uri("check", "success", size=12)
    danger = flat_data_uri("check", "danger", size=12)
    assert success != danger
    for uri, expected in ((success, palette.success), (danger, palette.danger)):
        payload = base64.b64decode(uri.split(",", 1)[1])
        image = QImage()
        assert image.loadFromData(payload)
        found = None
        for x in range(image.width()):
            for y in range(image.height()):
                color = image.pixelColor(x, y)
                if color.alpha() > 100:
                    found = (color.red(), color.green(), color.blue())
                    break
            if found:
                break
        assert found is not None
        assert _approx(found, expected), f"{found} không khớp role {expected}"


def test_flat_data_uri_cache_hit():
    from ui.icons import flat_data_uri

    first = flat_data_uri("check", "success", size=12)
    second = flat_data_uri("check", "success", size=12)
    assert first is second
