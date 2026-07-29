"""Offscreen responsive-layout audit for the application shell and screens."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import ExitStack
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractButton,
    QAbstractSpinBox,
    QComboBox,
    QLineEdit,
    QScrollArea,
    QWidget,
)

from tools.capture_ui_style_baseline import _fake_app, _patch_external_activity
from ui.screens.backtest_screen import BacktestScreen
from ui.screens.dashboard_screen import DashboardScreen
from ui.screens.journal_detail_screen import JournalDetailScreen
from ui.screens.journal_screen import JournalScreen
from ui.screens.orders_screen import OrdersScreen
from ui.screens.scanner_detail_screen import ScannerDetailScreen
from ui.screens.scanner_screen import ScannerScreen
from ui.screens.settings_screen import SettingsScreen
from ui.theme_manager import ThemeManager


VIEWPORT_PROFILES: dict[str, tuple[int, int]] = {
    "laptop-14": (1366, 768),
    "laptop-15-6": (1536, 864),
    "laptop-16": (1728, 1117),
    "desktop-24": (1920, 1080),
    "desktop-27": (2560, 1440),
    "desktop-32": (3840, 2160),
}

DPI_PROFILES: dict[str, float] = {
    "dpi-100": 1.0,
    "dpi-125": 1.25,
    "dpi-150": 1.5,
}

SCREEN_FACTORIES = {
    "dashboard": DashboardScreen,
    "scanner": ScannerScreen,
    "orders": OrdersScreen,
    "scanner_detail": ScannerDetailScreen,
    "backtest": BacktestScreen,
    "journal": JournalScreen,
    "journal_detail": JournalDetailScreen,
    "settings": SettingsScreen,
}


def load_visual_qa_fonts() -> list[str]:
    """Load deterministic Windows fonts when the offscreen plugin has none."""
    loaded: list[str] = []
    if QFontDatabase.families():
        return loaded
    font_root = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for filename in (
        "segoeui.ttf",
        "segoeuib.ttf",
        "seguisym.ttf",
        "seguiemj.ttf",
        "arial.ttf",
    ):
        path = font_root / filename
        if not path.is_file():
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id >= 0:
            loaded.extend(QFontDatabase.applicationFontFamilies(font_id))
    return sorted(set(loaded))

CONTROL_TYPES = (QAbstractButton, QAbstractSpinBox, QComboBox, QLineEdit)
STANDARD_CONTROL_HEIGHT = 24
COMPACT_CONTROL_HEIGHT = 20
MIN_CONTROL_WIDTH = 18

COMPACT_OBJECT_NAMES = {
    "FloatingSidebarToggle",
    "HelpButton",
    "NewsIconButton",
    "NewsLinkButton",
    "ResultTabArrow",
    "SidebarToggleButton",
    "TagChip",
}


def _inside_scroll_area(widget: QWidget) -> bool:
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QScrollArea):
            return True
        parent = parent.parentWidget()
    return False


def _required_control_height(widget: QWidget) -> int:
    """Return the reviewed density contract for an interactive control."""
    if widget.objectName() in COMPACT_OBJECT_NAMES:
        return COMPACT_CONTROL_HEIGHT

    parent = widget.parentWidget()
    while parent is not None:
        if parent.objectName() == "LifecycleScrollWidget":
            return COMPACT_CONTROL_HEIGHT
        if parent.property("tableRole") == "mt5Symbols":
            return COMPACT_CONTROL_HEIGHT
        if type(parent).__name__ == "QTabBar":
            return COMPACT_CONTROL_HEIGHT
        parent = parent.parentWidget()
    return STANDARD_CONTROL_HEIGHT


def _visible_controls(screen: QWidget) -> list[QWidget]:
    controls: list[QWidget] = []
    for widget in screen.findChildren(QWidget):
        if not isinstance(widget, CONTROL_TYPES) or not widget.isVisibleTo(screen):
            continue
        parent = widget.parentWidget()
        if isinstance(widget, QLineEdit) and isinstance(
            parent,
            (QAbstractSpinBox, QComboBox),
        ):
            continue
        controls.append(widget)
    return controls


def _control_issues(screen: QWidget) -> list[str]:
    issues: list[str] = []
    controls = _visible_controls(screen)

    def identity(widget: QWidget) -> str:
        name = widget.objectName() or type(widget).__name__
        text_getter = getattr(widget, "text", None)
        text = str(text_getter() if callable(text_getter) else "").strip()
        parent = widget.parentWidget()
        parent_name = (
            parent.objectName() or type(parent).__name__
            if parent is not None
            else "no-parent"
        )
        label = f"{name}({text})" if text else name
        return f"{label}@{parent_name}"

    for widget in controls:
        size = widget.size()
        control_identity = identity(widget)
        required_height = _required_control_height(widget)
        if size.height() < required_height:
            issues.append(
                f"{control_identity}: control height "
                f"{size.height()} < {required_height}"
            )
        if size.width() < MIN_CONTROL_WIDTH:
            issues.append(
                f"{control_identity}: control width "
                f"{size.width()} < {MIN_CONTROL_WIDTH}"
            )

    by_parent: dict[QWidget, list[QWidget]] = {}
    for widget in controls:
        parent = widget.parentWidget()
        if parent is None or parent.layout() is None or _inside_scroll_area(widget):
            continue
        by_parent.setdefault(parent, []).append(widget)
    for siblings in by_parent.values():
        for index, left in enumerate(siblings):
            left_rect = left.geometry()
            for right in siblings[index + 1 :]:
                intersection = left_rect.intersected(right.geometry())
                if intersection.width() > 1 and intersection.height() > 1:
                    issues.append(
                        f"{identity(left)}/{identity(right)}: controls overlap "
                        f"{intersection.width()}x{intersection.height()}"
                    )
    return issues


def build_responsive_report(
    themes: tuple[str, ...] = ("dark", "light"),
    *,
    dpi_profiles: tuple[str, ...] = ("dpi-100",),
    routes: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    app = QApplication.instance() or QApplication([])
    load_visual_qa_fonts()
    results: list[dict[str, Any]] = []
    selected_routes = routes or tuple(SCREEN_FACTORIES)
    with ExitStack() as stack:
        _patch_external_activity(stack)
        for theme in themes:
            for dpi_profile in dpi_profiles:
                for route in selected_routes:
                    factory = SCREEN_FACTORIES[route]
                    screen = factory(None, app=_fake_app(theme))
                    screen.setAttribute(
                        Qt.WidgetAttribute.WA_DontShowOnScreen,
                        True,
                    )
                    ThemeManager().apply(screen, theme=theme)
                    screen.show()
                    app.processEvents()
                    for profile, (width, height) in VIEWPORT_PROFILES.items():
                        screen.resize(width, height)
                        app.processEvents()
                        issues: list[str] = []
                        if screen.width() > width or screen.height() > height:
                            issues.append(
                                f"screen minimum size forced "
                                f"{screen.width()}x{screen.height()} above "
                                f"{width}x{height}"
                            )
                        if screen.width() <= 0 or screen.height() <= 0:
                            issues.append("screen has no drawable area")
                        issues.extend(_control_issues(screen))
                        primary_screen = app.primaryScreen()
                        device_pixel_ratio = (
                            primary_screen.devicePixelRatio()
                            if primary_screen is not None
                            else 1.0
                        )
                        results.append(
                            {
                                "theme": theme,
                                "dpi_profile": dpi_profile,
                                "scale_factor": DPI_PROFILES[dpi_profile],
                                "device_pixel_ratio": device_pixel_ratio,
                                "profile": profile,
                                "viewport": {
                                    "width": width,
                                    "height": height,
                                },
                                "route": route,
                                "screen_size": {
                                    "width": screen.width(),
                                    "height": screen.height(),
                                },
                                "issues": sorted(set(issues)),
                            }
                        )
                    for timer_name in (
                        "_debounce_timer",
                        "_refresh_timer",
                        "_trail_timer",
                        "auto_scan_timer",
                    ):
                        timer = getattr(screen, timer_name, None)
                        if timer is not None:
                            timer.stop()
                    screen.close()
                    screen.deleteLater()
                    app.processEvents()
    return {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profiles": {
            name: {"width": size[0], "height": size[1]}
            for name, size in VIEWPORT_PROFILES.items()
        },
        "dpi_profiles": {
            name: {"scale_factor": DPI_PROFILES[name]}
            for name in dpi_profiles
        },
        "themes": list(themes),
        "external_services": "disabled",
        "routes": sorted({item["route"] for item in results}),
        "results": results,
        "issue_count": sum(len(item["issues"]) for item in results),
    }


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _run_isolated_suite(output: Path) -> int:
    return _run_isolated_matrix(output, workers=4, timeout_seconds=45)


def _run_isolated_matrix(
    output: Path,
    *,
    workers: int,
    timeout_seconds: int,
) -> int:
    jobs = [
        (theme, dpi_profile, route)
        for theme in ("dark", "light")
        for dpi_profile in DPI_PROFILES
        for route in SCREEN_FACTORIES
    ]
    fragments = {
        job: output.with_name(
            f"{output.stem}.{job[0]}.{job[1]}.{job[2]}.tmp.json"
        )
        for job in jobs
    }
    for fragment in fragments.values():
        fragment.unlink(missing_ok=True)

    def run_job(job: tuple[str, str, str]) -> tuple[tuple[str, str, str], str]:
        theme, dpi_profile, route = job
        fragment = fragments[job]
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8:backslashreplace"
        env["QT_FONT_DPI"] = "96"
        env["QT_SCALE_FACTOR"] = str(DPI_PROFILES[dpi_profile])
        env["QT_QPA_PLATFORM"] = "offscreen"
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--theme",
            theme,
            "--dpi",
            dpi_profile,
            "--route",
            route,
            "--write",
            str(fragment),
        ]
        last_error = ""
        for attempt in range(1, 3):
            try:
                completed = subprocess.run(
                    command,
                    cwd=ROOT,
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                last_error = f"timeout on attempt {attempt}"
                continue
            if completed.returncode == 0 and fragment.is_file():
                return job, ""
            last_error = f"exit code {completed.returncode}"
        return job, last_error

    reports: list[dict[str, Any]] = []
    try:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            futures = {executor.submit(run_job, job): job for job in jobs}
            for future in as_completed(futures):
                job, error = future.result()
                if error:
                    print(
                        f"Responsive audit {'/'.join(job)} failed: {error}",
                        flush=True,
                    )
                    continue
                reports.append(
                    json.loads(fragments[job].read_text(encoding="utf-8"))
                )
        if len(reports) != len(jobs):
            print(
                f"Responsive audit jobs incomplete: "
                f"{len(reports)} != {len(jobs)}",
                flush=True,
            )
            return 1

        results = [
            item
            for report in reports
            for item in report.get("results", [])
        ]
        expected_results = (
            2 * len(DPI_PROFILES) * len(SCREEN_FACTORIES) * len(VIEWPORT_PROFILES)
        )
        combined = {
            "schema_version": 2,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "profiles": reports[0]["profiles"],
            "dpi_profiles": {
                name: {"scale_factor": scale}
                for name, scale in DPI_PROFILES.items()
            },
            "themes": ["dark", "light"],
            "external_services": "disabled",
            "routes": sorted(SCREEN_FACTORIES),
            "results": sorted(
                results,
                key=lambda item: (
                    item["theme"],
                    item["dpi_profile"],
                    item["route"],
                    item["profile"],
                ),
            ),
            "issue_count": sum(len(item["issues"]) for item in results),
        }
        if len(results) != expected_results:
            print(
                f"Responsive audit coverage mismatch: "
                f"{len(results)} != {expected_results}",
                flush=True,
            )
            return 1
        _write_report(output, combined)
        print(
            f"Responsive UI audit: {len(results)} checks, "
            f"{combined['issue_count']} issues; report={output}",
            flush=True,
        )
        return 1 if combined["issue_count"] else 0
    finally:
        for fragment in fragments.values():
            fragment.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write",
        type=Path,
        default=ROOT / "docs" / "ui" / "reports" / "ui-responsive-report.json",
    )
    parser.add_argument("--theme", choices=("dark", "light"))
    parser.add_argument("--dpi", choices=tuple(DPI_PROFILES), default="dpi-100")
    parser.add_argument("--route", choices=tuple(SCREEN_FACTORIES))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--job-timeout", type=int, default=45)
    args = parser.parse_args()
    if args.theme is None:
        return _run_isolated_matrix(
            args.write,
            workers=args.workers,
            timeout_seconds=max(10, args.job_timeout),
        )

    routes = (args.route,) if args.route else tuple(SCREEN_FACTORIES)
    report = build_responsive_report(
        (args.theme,),
        dpi_profiles=(args.dpi,),
        routes=routes,
    )
    _write_report(args.write, report)
    print(
        f"Responsive UI audit: {len(report['results'])} checks, "
        f"{report['issue_count']} issues; report={args.write}"
    )
    return 1 if report["issue_count"] else 0


if __name__ == "__main__":
    exit_code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)
