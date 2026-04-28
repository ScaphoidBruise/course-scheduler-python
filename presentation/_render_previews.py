"""Render slides.pptx to PNG previews using PowerPoint COM (Windows)."""
from pathlib import Path
import sys

import pythoncom
import win32com.client

HERE = Path(__file__).resolve().parent
PPTX = (HERE / "slides.pptx").resolve()
OUT = HERE / "previews"
OUT.mkdir(exist_ok=True)

print(f"Opening {PPTX} …")
pythoncom.CoInitialize()
ppt = win32com.client.Dispatch("PowerPoint.Application")
# WithWindow=False not allowed for some Export ops — keep window minimized
pres = ppt.Presentations.Open(str(PPTX), WithWindow=False)
try:
    for i, slide in enumerate(pres.Slides, 1):
        out_path = OUT / f"slide_{i:02d}.png"
        slide.Export(str(out_path), "PNG", 1600, 900)
        print(f"  + {out_path.name}")
finally:
    pres.Close()
    ppt.Quit()
    pythoncom.CoUninitialize()

print(f"Wrote {len(list(OUT.glob('*.png')))} PNGs to {OUT.relative_to(HERE.parent)}")
