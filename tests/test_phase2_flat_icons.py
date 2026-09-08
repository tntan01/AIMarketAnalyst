"""Khóa di cư icon phẳng phase 2 (7 màn hình + main_window).

Hai lớp bảo vệ:
1. Static (AST): không còn emoji trong literal text của `action_button(...)`
   và `QPushButton(...)` ở 7 screens + main_window.
2. Runtime: instantiate vài màn offscreen với `_fake_app` — mọi PrimaryButton
   phải có QIcon phẳng non-null; tab titles sạch emoji.
"""

from __future__ import annotations

import ast
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from contextlib import ExitStack
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication, QPushButton, QTabWidget

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.capture_ui_style_baseline import (  # noqa: E402
    _fake_app,
    _patch_external_activity,
)
from ui.icons import flat_pixmap_fixed  # noqa: E402
from ui.screens.journal_screen import JournalScreen  # noqa: E402
from ui.screens.orders_screen import OrdersScreen  # noqa: E402
from ui.screens.scanner_screen import ScannerScreen  # noqa: E402
from ui.screens.settings_screen import SettingsScreen  # noqa: E402
from ui.theme import DARK_PALETTE  # noqa: E402

SCREEN_FILES = [
    "ui/screens/scanner_screen.py",
    "ui/screens/orders_screen.py",
    "ui/screens/settings_screen.py",
    "ui/screens/journal_screen.py",
    "ui/screens/journal_detail_screen.py",
    "ui/screens/scanner_detail_screen.py",
    "ui/main_window.py",
]

# Emoji ranges đã di cư (KHÔNG gồm KPI badge ▲▼ — follow-up riêng).
EMOJI_RANGES = (
    (0x1F000, 0x1FAFF),
    (0x2600, 0x27BF),
    (0x2300, 0x23FF),
    (0x2B00, 0x2BFF),
)


def _has_emoji(text: str) -> bool:
    return any(lo <= ord(ch) <= hi for ch in text for lo, hi in EMOJI_RANGES)


def _button_text_literals(rel_path: str) -> list[str]:
    tree = ast.parse((ROOT / rel_path).read_text(encoding="utf-8"))
    texts: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name not in ("action_button", "QPushButton"):
            continue
        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(
            node.args[0].value, str
        ):
            texts.append(node.args[0].value)
    return texts


class _ExternalActivityPatched:
    """Patch ngoại hoạt (mạng/MT5/timer) giống tools/ui_layout_audit."""

    def __enter__(self):
        self._stack = ExitStack()
        _patch_external_activity(self._stack)
        return self._stack

    def __exit__(self, *exc):
        return self._stack.__exit__(*exc)


# ---------------------------------------------------------------------------
# Static: không emoji trong text literal của nút
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rel_path", SCREEN_FILES)
def test_no_emoji_in_button_literals(rel_path: str) -> None:
    for text in _button_text_literals(rel_path):
        assert not _has_emoji(text), (
            f"{rel_path}: nút còn emoji trong text '{text}' — dùng icon phẳng ui/icons.py"
        )


# ---------------------------------------------------------------------------
# Runtime: PrimaryButton có icon phẳng, tabs sạch emoji
# ---------------------------------------------------------------------------

def _primary_buttons_without_icon(screen) -> list[str]:
    bad = []
    for btn in screen.findChildren(QPushButton):
        if btn.objectName() == "PrimaryButton" and btn.icon().isNull():
            bad.append(btn.text())
    return bad


def _tab_texts(screen) -> list[str]:
    texts = []
    for tabs in screen.findChildren(QTabWidget):
        for i in range(tabs.count()):
            texts.append(tabs.tabText(i))
    return texts


def test_scanner_primary_buttons_have_flat_icons() -> None:
    with _ExternalActivityPatched():
        screen = ScannerScreen(None, app=_fake_app("dark"))
        assert not _primary_buttons_without_icon(screen)


def test_orders_primary_buttons_have_flat_icons() -> None:
    with _ExternalActivityPatched():
        screen = OrdersScreen(None, app=_fake_app("dark"))
        assert not _primary_buttons_without_icon(screen)


def test_journal_primary_buttons_and_tabs_clean() -> None:
    with _ExternalActivityPatched():
        screen = JournalScreen(None, app=_fake_app("dark"))
        assert not _primary_buttons_without_icon(screen)
        for text in _tab_texts(screen):
            assert not _has_emoji(text), f"Tab journal còn emoji: {text}"


def test_settings_tabs_clean() -> None:
    with _ExternalActivityPatched():
        screen = SettingsScreen(None, app=_fake_app("dark"))
        for text in _tab_texts(screen):
            assert not _has_emoji(text), f"Tab settings còn emoji: {text}"


def test_flat_pixmap_fixed_uses_given_color() -> None:
    pixmap = flat_pixmap_fixed("message-square", DARK_PALETTE.accent_hover, size=16)
    assert not pixmap.isNull()
    image = pixmap.toImage()
    found = any(
        image.pixelColor(x, y).alpha() > 100
        for x in range(image.width())
        for y in range(image.height())
    )
    assert found
