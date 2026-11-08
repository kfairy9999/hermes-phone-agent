#!/usr/bin/env python3
"""Render docs/media/demo.txt into a GIF. Requires Pillow, which is not a runtime dependency."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "media" / "demo.txt"
DEST = ROOT / "docs" / "media" / "demo.gif"
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

WIDTH = 960
HEIGHT = 540
MARGIN_X = 20
MARGIN_Y = 16
FONT_SIZE = 13
LINE_GAP = 3
BG = (18, 22, 28)
FG = (214, 220, 214)
DIM = (130, 150, 140)
ACCENT = (232, 196, 104)


def wrap(text: str, limit: int) -> list[str]:
    rows: list[str] = []
    for raw in text.splitlines():
        if raw == "":
            rows.append("")
            continue
        while len(raw) > limit:
            rows.append(raw[:limit])
            raw = raw[limit:]
        rows.append(raw)
    return rows


def main() -> int:
    text = SOURCE.read_text(encoding="utf-8")
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    char_w = probe.textlength("M", font=font)
    line_h = FONT_SIZE + LINE_GAP
    cols = max(40, int((WIDTH - MARGIN_X * 2) / char_w))
    visible = max(8, int((HEIGHT - MARGIN_Y * 2) / line_h))
    rows = wrap(text, cols)
    frames: list[Image.Image] = []
    # Hold the start, scroll, hold the end.
    starts = [0] * 6
    last = max(0, len(rows) - visible)
    starts.extend(range(0, last + 1, 2))
    starts.extend([last] * 10)
    palette_ref = None
    for start in starts:
        image = Image.new("RGB", (WIDTH, HEIGHT), BG)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, WIDTH, 36), fill=(32, 40, 48))
        draw.text((MARGIN_X, 8), "hermes-phone-agent  ·  mock demo  ·  $0", font=font, fill=ACCENT)
        y = 48
        window = rows[start : start + visible - 1]
        for row in window:
            color = ACCENT if row.startswith("You:") or row.startswith("──") or row.startswith("$") else FG
            if row.startswith("(exit"):
                color = DIM
            draw.text((MARGIN_X, y), row, font=font, fill=color)
            y += line_h
        quantized = image.quantize(colors=32, method=Image.Quantize.MEDIANCUT)
        if palette_ref is None:
            palette_ref = quantized
        else:
            quantized = image.quantize(palette=palette_ref, dither=Image.Dither.NONE)
        frames.append(quantized)
    DEST.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        DEST,
        save_all=True,
        append_images=frames[1:],
        duration=90,
        loop=0,
        optimize=True,
    )
    print(f"wrote {DEST} ({DEST.stat().st_size} bytes, {len(frames)} frames)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
