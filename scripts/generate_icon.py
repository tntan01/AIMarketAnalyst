"""Generate app icon for AI Market Analyst — clean multi-resolution .ico file."""
from __future__ import annotations

import math
import struct
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "assets" / "icons" / "app.ico"
OUT.parent.mkdir(parents=True, exist_ok=True)

SIZES = [256, 128, 64, 48, 32, 16]

BG_COLOR = (21, 31, 76)       # deep navy #151f4c
ACCENT_GREEN = (0, 200, 83)   # #00c853
ACCENT_WHITE = (240, 240, 250)
CORNER_RADIUS_RATIO = 0.18


def rounded_rect(draw, xy, r, fill):
    """Draw a rounded rectangle."""
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle(xy, radius=r, fill=fill)


def make_frame(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = max(0, int(size * 0.02))
    r = max(1, int(size * CORNER_RADIUS_RATIO))
    draw.rounded_rectangle((pad, pad, size - pad, size - pad), radius=r, fill=BG_COLOR)

    # Chart area — smaller y = top of chart = higher price
    margin = max(1, int(size * 0.18))
    top = margin + int(size * 0.04)
    bot = size - margin
    mid = (top + bot) / 2.0

    # 5 candles: red, red, green, green, green (uptrend)
    n = 5
    spacing = (size - 2 * margin) / (n + 1)
    body_w = max(1, int(size * 0.05))
    wick_w = max(1, int(size * 0.015))

    # Each candle: (open, close, high, low) — all as fraction 0..1 where 0=top, 1=bottom
    # Bullish candles have close < open (close higher on screen = smaller y)
    candles = [
        # (open,  close, high,  low)  — fractions from top
        (0.55,  0.75,  0.40,  0.82),   # bearish red
        (0.50,  0.68,  0.38,  0.74),   # bearish red
        (0.30,  0.60,  0.18,  0.66),   # bullish green
        (0.25,  0.52,  0.14,  0.58),   # bullish green
        (0.15,  0.38,  0.08,  0.44),   # bullish green
    ]

    for i, (o_frac, c_frac, h_frac, l_frac) in enumerate(candles):
        cx = int(margin + spacing * (i + 1))
        o = top + (bot - top) * o_frac
        c = top + (bot - top) * c_frac
        h = top + (bot - top) * h_frac
        l = top + (bot - top) * l_frac

        is_bull = c < o
        color = ACCENT_GREEN if is_bull else (220, 60, 60)

        # Wick (high to low)
        x0, x1 = int(cx - wick_w), int(cx + wick_w)
        y0, y1 = int(h), int(l)
        if y1 < y0:
            y0, y1 = y1, y0
        if y1 == y0:
            y1 += 1
        draw.rectangle((x0, y0, x1, y1), fill=color)

        # Body (open to close)
        y0, y1 = int(min(o, c)), int(max(o, c))
        if y1 == y0:
            y1 += 1
        draw.rectangle((int(cx - body_w), y0, int(cx + body_w), y1), fill=color + (255,))

    # Green up-arrow — only for sizes >= 48
    if size >= 48:
        ax = size - int(margin * 0.7)
        ay = int(margin * 0.7)
        s = max(2, int(size * 0.07))
        pts = [
            (ax, ay - s),
            (ax - int(s * 0.7), ay + int(s * 0.5)),
            (ax, ay),
            (ax + int(s * 0.7), ay + int(s * 0.5)),
        ]
        draw.polygon(pts, fill=ACCENT_GREEN + (255,))

    return img


def save_multi_ico(frames: list[Image.Image], path: Path) -> None:
    frames = sorted(frames, key=lambda im: im.size[0], reverse=True)
    ico_images: list[tuple[int, int, int, bytes]] = []

    buf = BytesIO()
    for im in frames:
        w, h = im.size
        if im.mode != "RGBA":
            im = im.convert("RGBA")
        png_buf = BytesIO()
        im.save(png_buf, format="PNG")
        png_data = png_buf.getvalue()
        ico_images.append((w, h, len(png_data), png_data))

    buf.write(struct.pack("<HHH", 0, 1, len(ico_images)))
    offset = 6 + 16 * len(ico_images)
    for w, h, size, _ in ico_images:
        b_w = 0 if w >= 256 else w
        b_h = 0 if h >= 256 else h
        buf.write(struct.pack(
            "<BBBBHHII",
            b_w, b_h, 0, 0,
            1, 32,
            size, offset,
        ))
        offset += size
    for _, _, _, data in ico_images:
        buf.write(data)

    path.write_bytes(buf.getvalue())
    print(f"[OK] {path} ({path.stat().st_size:,} bytes, {len(frames)} resolutions)")


def main() -> None:
    frames = [make_frame(s) for s in SIZES]
    save_multi_ico(frames, OUT)


if __name__ == "__main__":
    main()
