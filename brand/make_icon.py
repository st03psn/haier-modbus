"""Erzeugt ein neutrales, markenrechtlich unkritisches Integrations-Icon.

Flaches Design: abgerundetes blaues Quadrat + weißer Wassertropfen (Brauchwasser).
Ausgabe in den vom home-assistant/brands-Repo geforderten Größen.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).parent
BG = (12, 110, 170, 255)      # ruhiges Wasserblau
WHITE = (255, 255, 255, 255)


def _drop(draw: ImageDraw.ImageDraw, n: int) -> None:
    cx = n / 2
    r = n * 0.24
    cy = n * 0.62
    # runder Boden
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE)
    # spitzer oberer Teil
    apex = (cx, n * 0.20)
    base_y = cy - r * 0.55
    draw.polygon([apex, (cx - r * 0.86, base_y), (cx + r * 0.86, base_y)], fill=WHITE)
    # kleine "Glanz"-Aussparung für etwas Tiefe (blau)
    draw.ellipse([cx - r * 0.18, cy - r * 0.1, cx + r * 0.42, cy + r * 0.5], fill=BG)


def render(n: int) -> Image.Image:
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rad = int(n * 0.22)
    d.rounded_rectangle([0, 0, n - 1, n - 1], radius=rad, fill=BG)
    _drop(d, n)
    return img


def main() -> None:
    render(256).save(OUT / "icon.png")
    render(512).save(OUT / "icon@2x.png")
    print("wrote", OUT / "icon.png", "and icon@2x.png")


if __name__ == "__main__":
    main()
