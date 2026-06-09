#!/usr/bin/env python3
"""Generate the PWA / home-screen app icons for the Value Flow site.

Writes a small set of PNG icons into web/static/ that the web manifest and the
Apple home-screen tags point at. Re-run this if the brand mark or colours change:

    python make_icons.py

Brand: ink-navy background, emerald baseline accent, white "VF" wordmark — the
same identity as the site masthead.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "web" / "static"

NAVY = (20, 37, 58)        # --ink   #14253A
EMERALD = (14, 124, 102)   # --emerald #0E7C66
WHITE = (255, 255, 255)

# Candidate bold serif fonts (macOS first), fall back to PIL's bundled font.
FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
    "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
    "/System/Library/Fonts/Supplemental/Palatino.ttc",
    "/Library/Fonts/Georgia Bold.ttf",
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _render(size: int, *, safe: float = 1.0) -> Image.Image:
    """Draw one square icon. ``safe`` (<=1) shrinks the mark toward the centre so
    a maskable icon survives Android's circular/rounded crop."""
    img = Image.new("RGB", (size, size), NAVY)
    d = ImageDraw.Draw(img)

    # Emerald baseline bar sitting under the wordmark.
    bar_w = int(size * 0.42 * safe)
    bar_h = max(2, int(size * 0.05 * safe))
    bar_x = (size - bar_w) // 2
    bar_y = int(size * 0.66)
    radius = bar_h // 2
    d.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h],
                        radius=radius, fill=EMERALD)

    # "VF" wordmark, centred above the bar.
    font = _font(int(size * 0.46 * safe))
    d.text((size / 2, size * 0.42), "VF", font=font, fill=WHITE, anchor="mm")
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = [
        ("icon-192.png", 192, 1.0),
        ("icon-512.png", 512, 1.0),
        ("icon-512-maskable.png", 512, 0.78),  # extra padding for safe zone
        ("apple-touch-icon.png", 180, 1.0),    # iOS home-screen icon
        ("favicon-32.png", 32, 1.0),
    ]
    for name, size, safe in jobs:
        _render(size, safe=safe).save(OUT / name, "PNG")
        print(f"wrote {name} ({size}x{size})")


if __name__ == "__main__":
    main()
