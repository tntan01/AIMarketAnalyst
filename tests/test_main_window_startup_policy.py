"""R1 — owner startup/restore/persist của cửa sổ chính (offscreen, không MT5).

Mọi test dùng `QSettings` INI trong thư mục tạm và `availableGeometry` được bơm
vào, nên không phụ thuộc monitor thật và không ghi state của người dùng.
"""

from __future__ import annotations

import os
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PyQt6.QtCore import QRect, QSettings
from PyQt6.QtWidgets import QApplication, QStyle

from tools.capture_ui_style_baseline import _fake_app, _patch_external_activity
from ui.main_window import MainWindow
from ui.window_state import (
    MINIMUM_WINDOW_SIZE,
    SETTINGS_GROUP,
    REASON_CLAMPED,
    REASON_FAUX_MAXIMIZED,
    REASON_FIRST_LAUNCH,
    REASON_SAVED_MAXIMIZED,
    REASON_SAVED_NORMAL,
    WindowStateStore,
)

FULL_HD_150 = QRect(0, 0, 1280, 688)
FULL_HD = QRect(0, 0, 1920, 1080)
# Vùng làm việc logical của máy báo lỗi F-R5-01 (1920×1200 @150%, có taskbar).
WORK_AREA_1280x760 = QRect(0, 0, 1280, 760)
REPO_ROOT = Path(__file__).resolve().parents[1]


class _FakeScreen:
    def __init__(self, rect: QRect) -> None:
        self._rect = QRect(rect)

    def availableGeometry(self) -> QRect:
        return QRect(self._rect)


def _inject_screens(stack: ExitStack, *rects: QRect) -> None:
    screens = [_FakeScreen(rect) for rect in rects]
    stack.enter_context(
        patch.object(QApplication, "screens", staticmethod(lambda: list(screens)))
    )


@pytest.fixture
def settings(tmp_path: Path) -> QSettings:
    return QSettings(str(tmp_path / "window-state.ini"), QSettings.Format.IniFormat)


@pytest.fixture
def store(settings: QSettings) -> WindowStateStore:
    return WindowStateStore(settings)


def _qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _persist(
    settings: QSettings,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    maximized: bool,
) -> None:
    """Ghi state cửa sổ vào INI tạm đúng như production ghi."""
    settings.beginGroup(SETTINGS_GROUP)
    for key, value in {
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "maximized": maximized,
    }.items():
        settings.setValue(key, value)
    settings.endGroup()
    settings.sync()


def _open_window(stack: ExitStack, store: WindowStateStore) -> MainWindow:
    _patch_external_activity(stack)
    window = MainWindow(_fake_app("dark"), window_state=store)
    stack.callback(_dispose, window)
    return window


def _dispose(window: MainWindow) -> None:
    window.close()
    window.deleteLater()
    app = QApplication.instance()
    if app is not None:
        app.processEvents()


# --- constructor không được là policy ----------------------------------------


def test_construction_neither_shows_nor_writes_settings(store, settings) -> None:
    app = _qt_app()
    with ExitStack() as stack:
        window = _open_window(stack, store)
        app.processEvents()

        # Chưa gọi entry point ⇒ không show, không maximize, không ghi state.
        assert window.isVisible() is False
        assert window.isMaximized() is False
        assert settings.allKeys() == []


def test_app_shell_minimum_and_rail_are_unchanged(store) -> None:
    app = _qt_app()
    with ExitStack() as stack:
        window = _open_window(stack, store)
        app.processEvents()

        assert MINIMUM_WINDOW_SIZE == (800, 500)
        assert window.minimumSize().width() == 800
        assert window.minimumSize().height() == 500
        # R1 không đụng sidebar/rail (48px, 6 mục điều hướng).
        assert window.sidebar_width == 48
        assert window.sidebar.width() == 48
        assert len(window.nav_buttons) == 6


# --- startup / restore --------------------------------------------------------


def test_first_launch_maximizes(store, settings) -> None:
    app = _qt_app()
    with ExitStack() as stack:
        _inject_screens(stack, FULL_HD_150)
        window = _open_window(stack, store)
        decision = window.apply_startup_policy()
        app.processEvents()

        assert decision.maximized is True
        assert decision.reason == REASON_FIRST_LAUNCH
        assert window.isMaximized() is True


def test_saved_maximized_reopens_maximized(store, settings) -> None:
    app = _qt_app()
    settings.beginGroup(SETTINGS_GROUP)
    settings.setValue("x", 40)
    settings.setValue("y", 40)
    settings.setValue("width", 1200)
    settings.setValue("height", 700)
    settings.setValue("maximized", True)
    settings.endGroup()
    settings.sync()

    with ExitStack() as stack:
        _inject_screens(stack, FULL_HD)
        window = _open_window(stack, store)
        decision = window.apply_startup_policy()
        app.processEvents()

        assert decision.maximized is True
        assert decision.reason == REASON_SAVED_MAXIMIZED
        assert window.isMaximized() is True


def test_saved_normal_geometry_is_restored(store, settings) -> None:
    app = _qt_app()
    settings.beginGroup(SETTINGS_GROUP)
    settings.setValue("x", 120)
    settings.setValue("y", 80)
    settings.setValue("width", 1000)
    settings.setValue("height", 600)
    settings.setValue("maximized", False)
    settings.endGroup()
    settings.sync()

    with ExitStack() as stack:
        _inject_screens(stack, FULL_HD)
        window = _open_window(stack, store)
        decision = window.apply_startup_policy()
        app.processEvents()

        assert decision.maximized is False
        assert decision.reason == REASON_SAVED_NORMAL
        assert window.isMaximized() is False
        assert window.geometry() == QRect(120, 80, 1000, 600)


def test_close_then_new_instance_restores_the_same_geometry(settings) -> None:
    app = _qt_app()
    with ExitStack() as stack:
        _inject_screens(stack, FULL_HD)
        first = _open_window(stack, WindowStateStore(settings))
        first.apply_startup_policy()
        first.showNormal()
        first.setGeometry(QRect(140, 90, 1024, 640))
        app.processEvents()
        first.close()

    saved = WindowStateStore(settings).load()
    assert saved is not None
    assert saved.maximized is False
    assert saved.rect == QRect(140, 90, 1024, 640)

    with ExitStack() as stack:
        _inject_screens(stack, FULL_HD)
        second = _open_window(stack, WindowStateStore(settings))
        decision = second.apply_startup_policy()
        app.processEvents()

        assert decision.maximized is False
        assert decision.rect == QRect(140, 90, 1024, 640)
        assert second.geometry() == QRect(140, 90, 1024, 640)


def test_saved_maximized_is_persisted_when_closed_while_maximized(store, settings) -> None:
    app = _qt_app()
    with ExitStack() as stack:
        _inject_screens(stack, FULL_HD)
        window = _open_window(stack, store)
        window.apply_startup_policy()
        app.processEvents()
        window.close()

    persisted = WindowStateStore(settings).load()
    assert persisted is not None
    assert persisted.maximized is True


# --- fail-safe -----------------------------------------------------------------


def test_corrupt_ini_state_maximizes_without_crashing(store, settings, tmp_path) -> None:
    app = _qt_app()
    settings.sync()
    (tmp_path / "window-state.ini").write_text(
        f"[{SETTINGS_GROUP}]\n"
        "x=khong-phai-so\n"
        "y=\n"
        "width=0\n"
        "height=-5\n"
        "maximized=co-le\n",
        encoding="utf-8",
    )

    with ExitStack() as stack:
        _inject_screens(stack, FULL_HD)
        window = _open_window(stack, store)
        decision = window.apply_startup_policy()
        app.processEvents()

        assert decision.maximized is True
        assert decision.reason == REASON_FIRST_LAUNCH
        assert window.isMaximized() is True


def test_obsolete_settings_version_is_ignored(store, settings, tmp_path) -> None:
    app = _qt_app()
    settings.sync()
    (tmp_path / "window-state.ini").write_text(
        "[ui/main_window/v0]\n"
        "x=10\n"
        "y=10\n"
        "width=1200\n"
        "height=700\n"
        "maximized=false\n",
        encoding="utf-8",
    )

    with ExitStack() as stack:
        _inject_screens(stack, FULL_HD)
        window = _open_window(stack, store)
        decision = window.apply_startup_policy()
        app.processEvents()

        assert store.load() is None
        assert decision.maximized is True
        assert decision.reason == REASON_FIRST_LAUNCH


def test_geometry_outside_every_screen_maximizes(store, settings) -> None:
    app = _qt_app()
    settings.beginGroup(SETTINGS_GROUP)
    for key, value in {
        "x": 4000,
        "y": 200,
        "width": 1200,
        "height": 700,
        "maximized": False,
    }.items():
        settings.setValue(key, value)
    settings.endGroup()
    settings.sync()

    with ExitStack() as stack:
        _inject_screens(stack, FULL_HD)
        window = _open_window(stack, store)
        decision = window.apply_startup_policy()
        app.processEvents()

        assert decision.maximized is True
        assert window.isMaximized() is True


def test_geometry_shifted_by_a_monitor_change_is_clamped(store, settings) -> None:
    app = _qt_app()
    settings.beginGroup(SETTINGS_GROUP)
    for key, value in {
        "x": 400,
        "y": 120,
        "width": 1000,
        "height": 600,
        "maximized": False,
    }.items():
        settings.setValue(key, value)
    settings.endGroup()
    settings.sync()

    with ExitStack() as stack:
        _inject_screens(stack, FULL_HD_150)
        window = _open_window(stack, store)
        decision = window.apply_startup_policy()
        app.processEvents()

        assert decision.maximized is False
        assert decision.reason == REASON_CLAMPED
        assert decision.rect == QRect(280, 88, 1000, 600)
        assert window.geometry() == QRect(280, 88, 1000, 600)
        assert FULL_HD_150.contains(window.geometry())


# --- Full HD / 150% ------------------------------------------------------------


def test_full_hd_150_never_exceeds_the_available_height(store, settings) -> None:
    """Lỗi R0: minimum 700 đẩy cửa sổ cao 700 trên vùng làm việc 688."""
    app = _qt_app()
    settings.beginGroup(SETTINGS_GROUP)
    for key, value in {
        "x": 0,
        "y": 0,
        "width": 900,
        "height": 700,
        "maximized": False,
    }.items():
        settings.setValue(key, value)
    settings.endGroup()
    settings.sync()

    with ExitStack() as stack:
        _inject_screens(stack, FULL_HD_150)
        window = _open_window(stack, store)
        decision = window.apply_startup_policy()
        app.processEvents()

        assert window.minimumSize().height() <= FULL_HD_150.height()
        assert decision.rect.height() == FULL_HD_150.height()
        # Lỗi R0 là cửa sổ cao 700 trên vùng làm việc 688; giờ không vượt nữa.
        assert window.height() <= FULL_HD_150.height()


# --- F-R5-01: geometry normal "giả maximized" ---------------------------------


def test_faux_maximized_saved_state_opens_maximized(store, settings) -> None:
    """Nghiệm thu F-R5-01 qua entry production: state thật của máy báo lỗi.

    `QRect(30, 0, 1250, 752), maximized=False` trên vùng làm việc 1280×760 —
    cao đúng bằng vùng làm việc, mép trên/mép phải áp sát, lệch 30px trái.
    """
    app = _qt_app()
    _persist(settings, x=30, y=0, width=1250, height=752, maximized=False)

    with ExitStack() as stack:
        _inject_screens(stack, WORK_AREA_1280x760)
        window = _open_window(stack, store)
        decision = window.apply_startup_policy()
        app.processEvents()

        assert decision.maximized is True
        assert decision.rect is None
        assert decision.reason == REASON_FAUX_MAXIMIZED
        assert window.isMaximized() is True


def test_genuinely_normal_saved_state_is_still_restored(store, settings) -> None:
    """Nghiệm thu F-R5-01: cửa sổ normal thật (giữa màn hình) vẫn restore."""
    app = _qt_app()
    _persist(settings, x=240, y=120, width=800, height=520, maximized=False)

    with ExitStack() as stack:
        _inject_screens(stack, WORK_AREA_1280x760)
        window = _open_window(stack, store)
        decision = window.apply_startup_policy()
        app.processEvents()

        assert decision.maximized is False
        assert decision.reason == REASON_SAVED_NORMAL
        assert decision.rect == QRect(240, 120, 800, 520)
        assert window.isMaximized() is False
        assert window.geometry() == QRect(240, 120, 800, 520)


def test_startup_policy_uses_the_style_title_bar_metric(store, settings) -> None:
    """F-R5-01: dải chrome lấy từ Qt style pixel metric ở `MainWindow`.

    Cửa sổ chừa 12px phía trên vùng làm việc chỉ bị coi là chạm dải chrome khi
    metric thật của style cao hơn 12px — tức metric nền tảng thực sự được truyền
    vào policy, không hard-code 30/32px và không cố định bằng 0.
    """
    app = _qt_app()
    _persist(settings, x=0, y=12, width=1280, height=748, maximized=False)

    with ExitStack() as stack:
        _inject_screens(stack, WORK_AREA_1280x760)
        window = _open_window(stack, store)
        inset = window._title_bar_inset()
        decision = window.apply_startup_policy()
        app.processEvents()

        expected = window.style().pixelMetric(
            QStyle.PixelMetric.PM_TitleBarHeight, None, window
        )
        assert inset == max(int(expected), 0)
        assert inset > 12  # style offscreen báo 24px logical
        assert decision.maximized is True
        assert decision.reason == REASON_FAUX_MAXIMIZED
        assert window.isMaximized() is True


def test_full_coverage_geometry_taller_than_the_work_area_opens_maximized(
    store, settings
) -> None:
    """F-R5-01: bản phủ trọn bề ngang của cùng state R0 nay là faux-maximized."""
    app = _qt_app()
    _persist(settings, x=0, y=0, width=1280, height=700, maximized=False)

    with ExitStack() as stack:
        _inject_screens(stack, FULL_HD_150)
        window = _open_window(stack, store)
        decision = window.apply_startup_policy()
        app.processEvents()

        assert decision.maximized is True
        assert decision.reason == REASON_FAUX_MAXIMIZED
        assert window.isMaximized() is True
        # Bảo đảm R0 vẫn giữ: app shell không bao giờ cao hơn vùng làm việc.
        assert window.minimumSize().height() <= FULL_HD_150.height()


# --- dev/test normal window path ----------------------------------------------


def test_normal_window_path_is_explicit_and_does_not_persist(store, settings) -> None:
    app = _qt_app()
    with ExitStack() as stack:
        _inject_screens(stack, FULL_HD)
        window = _open_window(stack, store)
        decision = window.apply_startup_policy(normal_window=True)
        app.processEvents()

        assert decision.maximized is False
        assert window.isMaximized() is False
        assert window.width() <= 1440
        assert window.height() <= 900
        window.close()

    # Policy test/dev không được ghi state người dùng.
    assert settings.allKeys() == []


def test_normal_window_path_never_overrides_a_valid_saved_state(store, settings) -> None:
    settings.beginGroup(SETTINGS_GROUP)
    for key, value in {
        "x": 300,
        "y": 200,
        "width": 1100,
        "height": 640,
        "maximized": False,
    }.items():
        settings.setValue(key, value)
    settings.endGroup()
    settings.sync()

    app = _qt_app()
    with ExitStack() as stack:
        _inject_screens(stack, FULL_HD)
        window = _open_window(stack, store)
        decision = window.apply_startup_policy()
        app.processEvents()
        assert decision.rect == QRect(300, 200, 1100, 640)
        window.close()

    assert store.load().rect == QRect(300, 200, 1100, 640)


# --- một owner duy nhất --------------------------------------------------------


def test_main_py_has_exactly_one_startup_policy_owner() -> None:
    source = (REPO_ROOT / "main.py").read_text(encoding="utf-8")

    assert "apply_startup_policy" in source
    assert source.count("apply_startup_policy") == 1
    # main.py không còn tự quyết định trạng thái cửa sổ.
    assert "showMaximized" not in source
    assert ".show()" not in source


def test_main_window_constructor_has_no_dead_geometry_policy() -> None:
    source = (REPO_ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")

    assert "resize(1280, 800)" not in source
    assert "setMinimumSize(1024, 700)" not in source
    assert "showMaximized()" in source  # chỉ còn bên trong apply_startup_policy


def test_window_state_group_is_versioned_and_separate(store, settings) -> None:
    store.save(QRect(10, 20, 1000, 600), maximized=False)

    keys = set(settings.allKeys())
    assert keys == {
        f"{SETTINGS_GROUP}/x",
        f"{SETTINGS_GROUP}/y",
        f"{SETTINGS_GROUP}/width",
        f"{SETTINGS_GROUP}/height",
        f"{SETTINGS_GROUP}/maximized",
    }
    # Không đụng tới settings nghiệp vụ (settings.json của SettingsService).
    assert "settings" not in " ".join(keys)


def test_default_store_is_a_private_ini_not_the_business_settings() -> None:
    from ui.window_state import default_settings

    settings = default_settings()
    name = settings.fileName().replace("\\", "/")

    assert name.endswith(".ini")
    assert "ai-market-analyst" in name
    assert "settings.json" not in name
    # Mọi khóa đọc được (nếu có) đều nằm trong group versioned của UI.
    assert all(key.startswith(SETTINGS_GROUP) for key in settings.allKeys())
