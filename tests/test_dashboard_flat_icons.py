"""Khóa giao diện icon phẳng của dashboard.

Bắt regression: ai thêm emoji button mới vào dashboard, hoặc làm vỡ icon
phẳng (pixmap rỗng, sai size, state không propagate, không re-tint khi đổi
theme) sẽ bị test này chặn. Chạy headless với QT_QPA_PLATFORM=offscreen.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import re
import sys

import pytest
from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

from ui.screens.dashboard_screen import DashboardScreen  # noqa: E402
from ui.screens.shared import action_button  # noqa: E402
from ui.theme_manager import APP_THEME_PROPERTY, resolve_theme  # noqa: E402

# Các emoji đã di cư sang icon phẳng (không được xuất hiện lại trên widget).
MIGRATED_EMOJI = "🔄❓📍🤖❌🔗📅🔌👤⚡⏳"
EMOJI_RE = re.compile(f"[{re.escape(MIGRATED_EMOJI)}]")


class MockStateEvent(QEvent):
    def __init__(self):
        super().__init__(QEvent.Type.DynamicPropertyChange)

    def propertyName(self):
        return b"state"


def _make_screen() -> DashboardScreen:
    return DashboardScreen(None, app=None)


def _first_visible_pixel(pixmap):
    image = pixmap.toImage()
    for x in range(image.width()):
        for y in range(image.height()):
            color = image.pixelColor(x, y)
            if color.alpha() > 100:
                return (color.red(), color.green(), color.blue())
    return None


# ---------------------------------------------------------------------------
# Không còn emoji trên bề mặt đã di cư
# ---------------------------------------------------------------------------

def test_no_emoji_on_buttons():
    screen = _make_screen()
    for btn in screen.findChildren(QPushButton):
        assert not EMOJI_RE.search(btn.text()), (
            f"Nút '{btn.text()}' còn emoji — phải dùng icon phẳng (ui/icons.py)"
        )


def test_no_emoji_on_briefing_panel():
    screen = _make_screen()
    assert screen.briefing_section is not None, "Dashboard phải có panel bản tin AI"
    for label in screen.briefing_section.findChildren(QLabel):
        assert not EMOJI_RE.search(label.text()), (
            f"Label '{label.text()}' còn emoji — phải dùng icon phẳng (ui/icons.py)"
        )


# ---------------------------------------------------------------------------
# Status cards — pixmap phẳng theo state
# ---------------------------------------------------------------------------

def test_status_icons_are_flat_pixmaps():
    screen = _make_screen()
    assert len(screen.status_cards) == 4
    for key, (frame, _v, _d) in screen.status_cards.items():
        icons = [
            child
            for child in frame.findChildren(QLabel)
            if child.objectName() == "StatusIcon"
        ]
        assert len(icons) == 1, f"Card '{key}' thiếu StatusIcon"
        icon = icons[0]
        assert icon.text() == "", f"StatusIcon '{key}' phải bỏ emoji text"
        assert icon.width() == 28 and icon.height() == 28
        assert icon.pixmap() is not None and not icon.pixmap().isNull(), (
            f"StatusIcon '{key}' chưa có pixmap phẳng"
        )
        assert _first_visible_pixel(icon.pixmap()) is not None


def test_status_icon_state_propagation_changes_tint():
    screen = _make_screen()
    frame, _v, _d = screen.status_cards["Kết nối"]
    icon = next(
        c for c in frame.findChildren(QLabel) if c.objectName() == "StatusIcon"
    )
    event_filter = next(
        c for c in frame.children() if c.__class__.__name__ == "StatusCardEventFilter"
    )
    seen = {}
    for state in ("ok", "warning", "danger"):
        frame.setProperty("state", state)
        event_filter.eventFilter(frame, MockStateEvent())
        assert icon.property("state") == state
        seen[state] = _first_visible_pixel(icon.pixmap())
    assert len(set(seen.values())) == 3, "Pixmap không đổi màu theo state"


def test_status_icons_retint_on_theme_switch():
    screen = _make_screen()
    start = resolve_theme()
    target = "dark" if start != "dark" else "light"
    frame, _v, _d = screen.status_cards["Kết nối"]
    icon = next(
        c for c in frame.findChildren(QLabel) if c.objectName() == "StatusIcon"
    )
    before = _first_visible_pixel(icon.pixmap())
    app.setProperty(APP_THEME_PROPERTY, target)
    try:
        screen._retint_status_icons()
        after = _first_visible_pixel(icon.pixmap())
        assert before != after, "Đổi theme không re-tint pixmap status icon"
    finally:
        app.setProperty(APP_THEME_PROPERTY, start)


# ---------------------------------------------------------------------------
# Nút chính — icon gắn qua action_button
# ---------------------------------------------------------------------------

def test_top_level_buttons_have_flat_icons():
    screen = _make_screen()
    assert not screen.briefing_button.icon().isNull()
    assert screen.briefing_button.iconSize().width() == 16

    primary = {b.text(): b for b in screen.findChildren(QPushButton) if b.objectName() == "PrimaryButton"}
    for label in ("Thử lại", "Giải thích chỉ số", "Tạo bản tin"):
        assert label in primary, f"Thiếu nút chính '{label}'"
        assert not primary[label].icon().isNull(), f"Nút '{label}' thiếu icon phẳng"
        assert primary[label].iconSize().width() == 16

    secondary = {
        b.text(): b for b in screen.findChildren(QPushButton)
        if b.objectName() == "SecondaryButton"
    }
    assert "Xem tin tức đầy đủ" in secondary, "Thiếu nút phụ 'Xem tin tức đầy đủ'"
    assert not secondary["Xem tin tức đầy đủ"].icon().isNull()


def test_action_button_backward_compat():
    plain = action_button("Kiểm tra")
    assert plain.icon().isNull(), "action_button không icon phải giữ hành vi cũ"
    with_icon = action_button("Kiểm tra", icon="refresh")
    assert not with_icon.icon().isNull()


# ---------------------------------------------------------------------------
# Panel "Bản tin AI hôm nay" — empty state dùng glyph phẳng, không emoji
# ---------------------------------------------------------------------------

#_ranges emoji như tests/test_phase2_flat_icons.py — panel không còn emoji.
_DIALOG_EMOJI_RANGES = (
    (0x1F000, 0x1FAFF),
    (0x2600, 0x27BF),
    (0x2300, 0x23FF),
    (0x2B00, 0x2BFF),
)


def _emoji_hits(source: str) -> list[str]:
    # Bỏ qua dòng prompt AI chứa "###" (heading markdown gửi cho LLM, không
    # phải icon hiển thị trên UI).
    lines = [line for line in source.splitlines() if "###" not in line]
    return sorted(
        ch
        for line in lines
        for ch in line
        if any(lo <= ord(ch) <= hi for lo, hi in _DIALOG_EMOJI_RANGES)
    )


def test_briefing_methods_are_emoji_free_and_use_rich_states():
    import inspect

    from ui.screens import dashboard_screen as mod

    for method in (
        mod.DashboardScreen._build_briefing_section,
        mod.DashboardScreen._start_briefing,
        mod.DashboardScreen._on_briefing_finished,
        mod.DashboardScreen._show_briefing_empty,
    ):
        source = inspect.getsource(method)
        hits = _emoji_hits(source)
        assert not hits, f"{method.__name__} còn emoji: {hits}"

    empty_source = inspect.getsource(mod.DashboardScreen._show_briefing_empty)
    assert "empty_state_html" in empty_source, (
        "_show_briefing_empty phải render empty state qua rich text glyph phẳng"
    )
