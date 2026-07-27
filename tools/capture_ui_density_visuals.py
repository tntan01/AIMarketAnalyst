"""Capture reproducible Phase-6 screen evidence across theme and DPI profiles."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QCoreApplication, QEvent, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication

from tools.capture_ui_style_baseline import _fake_app, _patch_external_activity
from tools.ui_layout_audit import (
    DPI_PROFILES,
    SCREEN_FACTORIES,
    load_visual_qa_fonts,
)
from ui.theme_manager import ThemeManager


DEFAULT_OUTPUT = ROOT / "docs" / "ui-baseline" / "density-phase6"
VISUAL_VIEWPORT = (1366, 768)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def capture_screen(
    output: Path,
    *,
    theme: str,
    dpi_profile: str,
    route: str,
    viewport: tuple[int, int],
) -> dict[str, object]:
    app = QApplication.instance() or QApplication([])
    load_visual_qa_fonts()
    with ExitStack() as stack:
        _patch_external_activity(stack)
        screen = SCREEN_FACTORIES[route](None, app=_fake_app(theme))
        screen.setAttribute(
            Qt.WidgetAttribute.WA_DontShowOnScreen,
            True,
        )
        ThemeManager().apply(screen, theme=theme)
        screen.resize(*viewport)
        screen.show()
        app.processEvents()
        QCoreApplication.sendPostedEvents(
            None,
            QEvent.Type.DeferredDelete,
        )
        app.processEvents()

        primary_screen = app.primaryScreen()
        dpr = (
            float(primary_screen.devicePixelRatio())
            if primary_screen is not None
            else DPI_PROFILES[dpi_profile]
        )
        physical_width = round(screen.width() * dpr)
        physical_height = round(screen.height() * dpr)
        image = QImage(
            physical_width,
            physical_height,
            QImage.Format.Format_ARGB32,
        )
        image.setDevicePixelRatio(dpr)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        screen.render(painter)
        painter.end()

        target = output / theme / dpi_profile / f"screen-{route}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        if image.isNull() or not image.save(str(target), "PNG"):
            raise RuntimeError(f"Qt could not save {target}")

        result: dict[str, object] = {
            "theme": theme,
            "dpi_profile": dpi_profile,
            "scale_factor": DPI_PROFILES[dpi_profile],
            "device_pixel_ratio": dpr,
            "route": route,
            "viewport": {"width": viewport[0], "height": viewport[1]},
            "rendered_size": {
                "width": physical_width,
                "height": physical_height,
            },
            "path": _manifest_path(target),
            "sha256": _sha256(target),
        }
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
        return result


def _run_suite(
    output: Path,
    *,
    viewport: tuple[int, int],
    workers: int,
    timeout_seconds: int,
    replace: bool,
) -> int:
    jobs = [
        (theme, dpi_profile, route)
        for theme in ("dark", "light")
        for dpi_profile in DPI_PROFILES
        for route in SCREEN_FACTORIES
    ]
    existing = list(output.rglob("*.png"))
    if existing:
        if not replace:
            print(
                f"Visual output must not contain existing PNG files: {output}",
                flush=True,
            )
            return 1
        expected_paths = {
            output / theme / dpi_profile / f"screen-{route}.png"
            for theme, dpi_profile, route in jobs
        }
        unexpected = [path for path in existing if path not in expected_paths]
        if unexpected:
            print(
                "Refusing to replace output containing unexpected PNG files: "
                + ", ".join(str(path) for path in unexpected),
                flush=True,
            )
            return 1
        for path in expected_paths:
            path.unlink(missing_ok=True)

    def run_job(job: tuple[str, str, str]) -> tuple[tuple[str, str, str], str]:
        theme, dpi_profile, route = job
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8:backslashreplace"
        env["QT_FONT_DPI"] = "96"
        env["QT_SCALE_FACTOR"] = str(DPI_PROFILES[dpi_profile])
        env["QT_QPA_PLATFORM"] = "offscreen"
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--output",
            str(output),
            "--theme",
            theme,
            "--dpi",
            dpi_profile,
            "--route",
            route,
            "--viewport",
            f"{viewport[0]}x{viewport[1]}",
        ]
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
            return job, "timeout"
        if completed.returncode:
            return job, f"exit code {completed.returncode}"
        return job, ""

    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {executor.submit(run_job, job): job for job in jobs}
        for future in as_completed(futures):
            job, error = future.result()
            if error:
                failures.append({"job": "/".join(job), "error": error})

    captures: list[dict[str, object]] = []
    for theme, dpi_profile, route in jobs:
        target = output / theme / dpi_profile / f"screen-{route}.png"
        if not target.is_file():
            continue
        dpr = DPI_PROFILES[dpi_profile]
        captures.append(
            {
                "theme": theme,
                "dpi_profile": dpi_profile,
                "scale_factor": dpr,
                "route": route,
                "viewport": {"width": viewport[0], "height": viewport[1]},
                "rendered_size": {
                    "width": round(viewport[0] * dpr),
                    "height": round(viewport[1] * dpr),
                },
                "path": _manifest_path(target),
                "sha256": _sha256(target),
            }
        )

    manifest = {
        "schema_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "external_services": "disabled",
        "viewport": {"width": viewport[0], "height": viewport[1]},
        "themes": ["dark", "light"],
        "dpi_profiles": DPI_PROFILES,
        "captures": captures,
        "failures": failures,
    }
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "screenshot-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    expected = len(jobs)
    print(
        f"Density visual suite: {len(captures)}/{expected} images, "
        f"failures={len(failures)}; manifest={manifest_path}",
        flush=True,
    )
    return 0 if len(captures) == expected and not failures else 1


def _parse_viewport(value: str) -> tuple[int, int]:
    width, separator, height = value.lower().partition("x")
    if separator != "x" or not width.isdigit() or not height.isdigit():
        raise argparse.ArgumentTypeError("viewport must use WIDTHxHEIGHT")
    return int(width), int(height)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--theme", choices=("dark", "light"))
    parser.add_argument("--dpi", choices=tuple(DPI_PROFILES))
    parser.add_argument("--route", choices=tuple(SCREEN_FACTORIES))
    parser.add_argument("--viewport", type=_parse_viewport, default=VISUAL_VIEWPORT)
    parser.add_argument("--suite", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--job-timeout", type=int, default=45)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if args.suite:
        return _run_suite(
            output,
            viewport=args.viewport,
            workers=args.workers,
            timeout_seconds=max(10, args.job_timeout),
            replace=args.replace,
        )
    if not (args.theme and args.dpi and args.route):
        parser.error("single capture requires --theme, --dpi and --route")
    capture = capture_screen(
        output,
        theme=args.theme,
        dpi_profile=args.dpi,
        route=args.route,
        viewport=args.viewport,
    )
    print(json.dumps(capture, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)
