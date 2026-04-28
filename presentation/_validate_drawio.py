"""Sanity check for system_design.drawio.

- Parses the XML strict-mode.
- Confirms every embedded image data URI base64-decodes to a valid PNG
  header (\\x89PNG\\r\\n).
- Prints a per-page cell summary.
"""
from __future__ import annotations

import base64
import re
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
DRAWIO = HERE / "system_design.drawio"

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
IMG_RE = re.compile(r"image=data:image/png,base64,([A-Za-z0-9+/=]+)")


def main() -> int:
    tree = ET.parse(DRAWIO)
    root = tree.getroot()
    print(f"Root: <{root.tag}>")

    diagrams = root.findall("diagram")
    print(f"Pages: {len(diagrams)}")

    total_imgs = 0
    bad_imgs = 0
    for diagram in diagrams:
        name = diagram.attrib.get("name", "?")
        cells = diagram.findall(".//mxCell")
        edges = [c for c in cells if c.attrib.get("edge") == "1"]
        vertices = [c for c in cells if c.attrib.get("vertex") == "1"]
        images = [c for c in vertices
                  if "shape=image" in (c.attrib.get("style") or "")]
        print(f"  {name!r}: {len(cells)} cells "
              f"({len(vertices)} vertices, {len(edges)} edges, {len(images)} images)")

        for img in images:
            total_imgs += 1
            style = img.attrib.get("style") or ""
            m = IMG_RE.search(style)
            if not m:
                bad_imgs += 1
                print(f"    ! cell {img.attrib.get('id')}: no base64 image found")
                continue
            try:
                blob = base64.b64decode(m.group(1))
            except Exception as exc:
                bad_imgs += 1
                print(f"    ! cell {img.attrib.get('id')}: base64 decode failed: {exc}")
                continue
            if not blob.startswith(PNG_MAGIC):
                bad_imgs += 1
                print(f"    ! cell {img.attrib.get('id')}: not a valid PNG header")

    print(f"\nFile size: {DRAWIO.stat().st_size // 1024} KB")
    print(f"Images: {total_imgs} total, {bad_imgs} bad")
    return 0 if bad_imgs == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
