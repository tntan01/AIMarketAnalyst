"""Đồng bộ icon ứng dụng từ bộ thiết kế gốc.

Nguồn duy nhất: ``assets/icons/AIMA_Logo_Assets/`` do thiết kế cung cấp —
``AIMA.ico`` (ICO nhiều cỡ 16..256, 32bpp alpha) kèm các bản render PNG từng cỡ.

Script này:
  * xác minh ``AIMA.ico`` đủ các cỡ Windows cần (16..256) và có kênh alpha,
  * đồng bộ nó vào ``assets/icons/app.ico`` — đường dẫn mà ``main.py`` và
    ``packaging/pyinstaller.spec`` đã trỏ tới, nên không cần đổi code,
  * ``--preview`` sinh ``assets/icons/build/icon-preview.html`` để duyệt
    icon trên nền sáng/tối ở mọi kích thước.

Cách dùng:
    python tools/generate_app_icon.py             # validate + sync app.ico
    python tools/generate_app_icon.py --preview   # thêm preview và mở trình duyệt
"""
from __future__ import annotations

import argparse
import base64
import os
import shutil
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT / "assets" / "icons" / "AIMA_Logo_Assets"
SRC_ICO = ASSETS_DIR / "AIMA.ico"
APP_ICO = ASSETS_DIR.parent / "app.ico"
BUILD_DIR = ASSETS_DIR.parent / "build"

# Các cỡ Windows dùng: taskbar 16, title bar 16/24, Explorer 32/48, Alt+Tab 64+.
REQUIRED_SIZES = {16, 24, 32, 48, 64, 128, 256}
PREVIEW_SIZES = (16, 32, 64, 128, 256)


def parse_ico(path: Path) -> list[tuple[int, int, int, str]]:
    """Trả về danh sách (width, height, bpp, kind) của từng entry trong ICO."""
    data = path.read_bytes()
    _reserved, kind, count = struct.unpack("<HHH", data[:6])
    if kind != 1:
        raise ValueError(f"{path.name}: not an icon file (type={kind})")
    entries = []
    for i in range(count):
        off = 6 + 16 * i
        w, h, _colors, _res, _planes, bpp, size, img_off = struct.unpack(
            "<BBBBHHII", data[off : off + 16]
        )
        w = w or 256
        h = h or 256
        img_kind = (
            "PNG" if data[img_off : img_off + 8] == b"\x89PNG\r\n\x1a\n" else "BMP"
        )
        entries.append((w, h, bpp, img_kind))
    return entries


def validate(entries: list[tuple[int, int, int, str]]) -> None:
    sizes = {w for w, _h, _bpp, _k in entries}
    missing = REQUIRED_SIZES - sizes
    if missing:
        raise ValueError(f"AIMA.ico missing sizes: {sorted(missing)}")
    non_alpha = [(w, h) for w, h, bpp, _k in entries if bpp != 32]
    if non_alpha:
        raise ValueError(f"AIMA.ico entries without 32bpp alpha: {non_alpha}")


def build_preview() -> Path:
    """Sinh trang preview nhúng base64 các bản PNG trên nền sáng/tối."""
    rows = []
    for size in PREVIEW_SIZES:
        png = ASSETS_DIR / f"AIMA_{size}.png"
        b64 = base64.b64encode(png.read_bytes()).decode()
        tag = f'<img src="data:image/png;base64,{b64}" width="{size}" height="{size}" />'
        rows.append(
            f'<div class="row"><span class="lbl">{size}px</span>'
            f'<div class="cell light">{tag}</div><div class="cell dark">{tag}</div></div>'
        )
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>AI Market Analyst — Icon Preview</title>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; margin: 32px; background: #1a1d23; color: #e5e7eb; }}
  h1 {{ font-size: 20px; }}
  .row {{ display: flex; align-items: center; gap: 24px; margin: 14px 0; }}
  .lbl {{ width: 56px; color: #9ca3af; font-size: 12px; }}
  .cell {{ padding: 16px 24px; border-radius: 10px; display: inline-flex; }}
  .light {{ background: #f3f4f6; }}
  .dark {{ background: #0b0d12; }}
</style></head><body>
<h1>AI Market Analyst — duyệt icon ứng dụng (AIMA_Logo_Assets)</h1>
{''.join(rows)}
</body></html>"""
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    out = BUILD_DIR / "icon-preview.html"
    out.write_text(html, encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and sync the app icon from assets/icons/AIMA_Logo_Assets"
    )
    parser.add_argument("--preview", action="store_true", help="generate + open preview page")
    args = parser.parse_args()

    if not SRC_ICO.exists():
        print(f"[error] missing design source: {SRC_ICO}")
        return 1

    try:
        validate(parse_ico(SRC_ICO))
    except ValueError as exc:
        print(f"[error] {exc}")
        return 1

    shutil.copyfile(SRC_ICO, APP_ICO)
    print(f"[ok] synced {APP_ICO.name} from AIMA_Logo_Assets/AIMA.ico "
          f"({len(REQUIRED_SIZES)} sizes)")

    if args.preview:
        out = build_preview()
        print(f"[ok] preview -> {out}")
        os.startfile(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
