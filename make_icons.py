#!/usr/bin/env python3
"""Generate the PWA / home-screen app icons for the Value Flow site.

Writes a small set of PNG icons into web/static/ that the web manifest and the
Apple home-screen tags point at. Re-run this if the brand mark or colours change:

    python make_icons.py

Brand mark: "The Evergreen" — an abstract conifer drawn as three chevron
strokes (mint, fading upward like layered boughs) over a short cream trunk, on
the ink-navy tile. Chosen for the long-term, evergreen ethos of value
investing; the stroke-based mark matches the site's sparkline language.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "web" / "static"

NAVY = (20, 37, 58)         # --ink   #14253A
MINT = (47, 182, 140)       # bright emerald for dark tiles  #2FB68C
CREAM = (244, 239, 228)     # trunk  #F4EFE4


def _blend(fg: tuple, bg: tuple, alpha: float) -> tuple:
    """Flatten an alpha against the background (icons are opaque PNGs)."""
    return tuple(round(f * alpha + b * (1 - alpha)) for f, b in zip(fg, bg))


def _stroke(d: ImageDraw.ImageDraw, pts: list[tuple], width: int, fill: tuple) -> None:
    """A polyline with round caps and joints (PIL lines are butt-capped)."""
    d.line(pts, fill=fill, width=width, joint="curve")
    r = width / 2
    for (x, y) in (pts[0], pts[-1]):
        d.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def _render(size: int, *, safe: float = 1.0, supersample: int = 4) -> Image.Image:
    """Draw one square icon. ``safe`` (<=1) shrinks the mark toward the centre so
    a maskable icon survives Android's circular/rounded crop. Drawn oversized
    and downscaled for smooth, anti-aliased strokes."""
    S = size * supersample
    img = Image.new("RGB", (S, S), NAVY)
    d = ImageDraw.Draw(img)

    def pt(x: float, y: float) -> tuple:
        # Design coordinates on a 100x100 grid, scaled around the centre.
        return (S / 2 + (x - 50) * S / 100 * safe,
                S / 2 + (y - 50) * S / 100 * safe)

    w = max(2, round(S * 0.07 * safe))           # stroke weight (7% of tile)

    # Three boughs, brightest on top — the same geometry as the approved comp.
    boughs = [
        ([pt(34, 40), pt(50, 24), pt(66, 40)], 1.00),
        ([pt(28, 58), pt(50, 40), pt(72, 58)], 0.80),
        ([pt(22, 76), pt(50, 56), pt(78, 76)], 0.60),
    ]
    for pts, alpha in boughs:
        _stroke(d, pts, w, _blend(MINT, NAVY, alpha))

    # Cream trunk.
    _stroke(d, [pt(50, 70), pt(50, 84)], w, CREAM)

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = [
        ("icon-192.png", 192, 0.92),
        ("icon-512.png", 512, 0.92),
        ("icon-512-maskable.png", 512, 0.72),  # extra padding for safe zone
        ("apple-touch-icon.png", 180, 0.92),   # iOS home-screen icon
        ("favicon-32.png", 32, 1.0),           # tiny: use the full tile
    ]
    for name, size, safe in jobs:
        _render(size, safe=safe).save(OUT / name, "PNG")
        print(f"wrote {name} ({size}x{size})")


if __name__ == "__main__":
    main()
