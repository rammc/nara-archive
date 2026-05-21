#!/usr/bin/env python3
"""Produce placeholder icons for the macOS .app bundle.

Run when ``build/actari.icns`` is missing so the PyInstaller build
doesn't fail on a fresh checkout. The output is intentionally simple — a
flat amber square with "N" centred — so it's visually obvious it's a
placeholder and triggers the "design the icon" prompt for the maintainer.

Usage:
    python build/generate-placeholder-icons.py

Output:
    build/actari.iconset/icon_{16,32,128,256,512}x{...}{,@2x}.png
    build/menubar-icon.png (22x22 black on transparent — for the menubar)

After this, run `iconutil -c icns build/actari.iconset \
  -o build/actari.icns` to produce the .icns file (the Makefile
does both steps automatically).
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as e:  # pragma: no cover — Pillow is a hard dep
    raise SystemExit(
        "Pillow is required (already a project dependency). Activate the venv and try again."
    ) from e

ROOT = Path(__file__).resolve().parent
ICONSET_DIR = ROOT / "actari.iconset"
MENUBAR_PATH = ROOT / "menubar-icon.png"

ACCENT = (217, 119, 6, 255)  # matches the web UI's accent colour
FG = (26, 18, 6, 255)


def _font(size: int) -> ImageFont.ImageFont:
    """Best-effort system font; falls back to PIL default if nothing is found."""
    for candidate in (
        "/System/Library/Fonts/SFNS.ttf",  # macOS
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
    ):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_app_icon(size: int, dest: Path) -> None:
    img = Image.new("RGBA", (size, size), ACCENT)
    draw = ImageDraw.Draw(img)
    font_size = int(size * 0.6)
    font = _font(font_size)
    text = "N"
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]), text, fill=FG, font=font)
    except AttributeError:  # very old Pillow
        draw.text((size * 0.2, size * 0.1), text, fill=FG, font=font)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, format="PNG")


def make_menubar_icon(size: int, dest: Path) -> None:
    """Black-on-transparent template image — macOS handles dark/light inversion."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font_size = int(size * 0.75)
    font = _font(font_size)
    text = "N"
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            ((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]),
            text,
            fill=(0, 0, 0, 255),
            font=font,
        )
    except AttributeError:
        draw.text((size * 0.2, size * 0.05), text, fill=(0, 0, 0, 255), font=font)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, format="PNG")


def main() -> int:
    pairs = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]
    print(f"writing {len(pairs)} app-icon PNGs → {ICONSET_DIR}")
    for size, name in pairs:
        make_app_icon(size, ICONSET_DIR / name)

    print(f"writing menubar template icon → {MENUBAR_PATH}")
    make_menubar_icon(44, MENUBAR_PATH)

    print("done. Run `iconutil -c icns build/actari.iconset -o build/actari.icns` next.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
