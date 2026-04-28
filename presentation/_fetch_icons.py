"""Download tech logos (simpleicons.org) and UTPB site favicons (Google s2)
into presentation/icons/ for use by build_deck.py.

Idempotent: skips files that already exist. Run from project root:

    python presentation\\_fetch_icons.py
"""
from __future__ import annotations

from pathlib import Path

import requests
from reportlab.graphics import renderPM
from svglib.svglib import svg2rlg

HERE = Path(__file__).resolve().parent
ICONS = HERE / "icons"
ICONS.mkdir(exist_ok=True)

# (slug, brand-hex-color, target-pixels)
SIMPLE_ICONS = [
    ("python", "3776AB"),
    ("flask", "000000"),
    ("sqlite", "003B57"),
    ("html5", "E34F26"),
    ("css", "1572B6"),
    ("javascript", "F7DF1E"),
    ("anthropic", "191919"),
    ("git", "F05032"),
]

# (label, domain)
FAVICONS = [
    ("smartcatalog", "utpb.smartcatalogiq.com"),
    ("utpb", "utpb.edu"),
]

USER_AGENT = "deck-icons/1.0 (presentation builder)"
TIMEOUT = 20


def http_get(url: str) -> bytes:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.content


def svg_bytes_to_png(svg_path: Path, png_path: Path, target_px: int = 256) -> bool:
    drawing = svg2rlg(str(svg_path))
    if drawing is None:
        return False
    bbox_w = max(drawing.width or 24, 1)
    bbox_h = max(drawing.height or 24, 1)
    scale = target_px / max(bbox_w, bbox_h)
    drawing.width = bbox_w * scale
    drawing.height = bbox_h * scale
    drawing.scale(scale, scale)
    renderPM.drawToFile(drawing, str(png_path), fmt="PNG", dpi=144)
    return True


def fetch_simple_icon(slug: str, color_hex: str) -> None:
    png = ICONS / f"{slug}.png"
    if png.exists() and png.stat().st_size > 0:
        print(f"  - {slug}.png (cached)")
        return
    svg_url = f"https://cdn.simpleicons.org/{slug}/{color_hex}"
    try:
        svg_data = http_get(svg_url)
    except requests.RequestException as exc:
        print(f"  ! {slug}: download failed: {exc}")
        return
    svg_path = ICONS / f"{slug}.svg"
    svg_path.write_bytes(svg_data)
    try:
        if svg_bytes_to_png(svg_path, png):
            print(f"  + {slug}.png")
        else:
            print(f"  ! {slug}: svglib could not parse {svg_path.name}")
    except Exception as exc:  # svglib/reportlab can raise many
        print(f"  ! {slug}: convert failed: {exc}")


def fetch_favicon(label: str, domain: str) -> None:
    png = ICONS / f"site_{label}.png"
    if png.exists() and png.stat().st_size > 0:
        print(f"  - site_{label}.png (cached)")
        return
    url = f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
    try:
        data = http_get(url)
    except requests.RequestException as exc:
        print(f"  ! {domain}: {exc}")
        return
    if not data or len(data) < 64:
        print(f"  ! {domain}: empty response")
        return
    png.write_bytes(data)
    print(f"  + site_{label}.png")


def main() -> int:
    print("Tech logos (simpleicons) …")
    for slug, color in SIMPLE_ICONS:
        fetch_simple_icon(slug, color)
    print("Site favicons (Google s2) …")
    for label, domain in FAVICONS:
        fetch_favicon(label, domain)
    print(f"\nIcons in {ICONS.relative_to(HERE.parent)}:")
    for f in sorted(ICONS.iterdir()):
        if f.suffix.lower() == ".png":
            print(f"  - {f.name}  ({f.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
