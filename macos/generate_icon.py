#!/usr/bin/env python3
"""Generate a square, full-bleed AppIcon.png (no margins — macOS adds its own mask)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
BG = (0x2D, 0x6A, 0x4F)
WHITE = (255, 255, 255)
OUT = Path(__file__).resolve().parent / "AppIcon.png"


def _person(draw: ImageDraw.ImageDraw, cx: int, top: int, scale: float = 1.0) -> None:
    r = int(52 * scale)
    body_w = int(88 * scale)
    body_h = int(110 * scale)
    neck = top + int(95 * scale)
    draw.ellipse([cx - r, top, cx + r, top + 2 * r], fill=WHITE)
    draw.rounded_rectangle(
        [cx - body_w // 2, neck, cx + body_w // 2, neck + body_h],
        radius=int(18 * scale),
        fill=WHITE,
    )


def main() -> None:
    img = Image.new("RGB", (SIZE, SIZE), BG)
    draw = ImageDraw.Draw(img)

    # Three people — fill upper ~55% of canvas
    row_y = 130
    for cx in (250, 512, 774):
        _person(draw, cx, row_y, scale=1.45)

    # Folder — thick, wide, anchored low
    pad_x = 96
    top = 520
    bottom = 920
    tab_left = 180
    tab_right = 500
    tab_top = 450
    stroke = 44

    draw.rounded_rectangle(
        [pad_x, top, SIZE - pad_x, bottom],
        radius=48,
        outline=WHITE,
        width=stroke,
    )
    draw.rounded_rectangle(
        [tab_left, tab_top, tab_right, top + 20],
        radius=28,
        fill=WHITE,
    )

    img.save(OUT, format="PNG", optimize=True)
    print(f"Wrote {OUT} ({SIZE}×{SIZE})")


if __name__ == "__main__":
    main()
