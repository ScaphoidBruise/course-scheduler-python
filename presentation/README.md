# Demo presentation deck

Generated 10-slide PowerPoint deck for the COSC 3320 final-project demo.
Sized 16:9, designed for a ~10-minute slot (5 min slides + 4 min live demo + 1 min Q&A).

## What's in here

| Path                          | What it is                                                          |
| ----------------------------- | ------------------------------------------------------------------- |
| `slides.pptx`                 | The deliverable. Open in PowerPoint, edit anything, present.        |
| `system_design.drawio`        | Standalone draw.io file — same architecture chart + DB schema.      |
| `build_deck.py`               | Regenerates `slides.pptx` from scratch.                             |
| `build_drawio.py`             | Regenerates `system_design.drawio` from scratch.                    |
| `diagrams/architecture.mmd`   | Mermaid source for the architecture diagram (reference only).       |
| `diagrams/database.mmd`       | Mermaid source for the ER diagram (reference only).                 |
| `icons/`                      | Tech logos and UTPB favicons used by slide 4 and the .drawio.       |
| `screenshots/`                | Drop your real screenshots here — see `SCREENSHOTS.md`.             |
| `previews/`                   | PNG renders of each slide for quick review.                         |
| `SCREENSHOTS.md`              | Filename checklist for screenshots the deck looks for.              |
| `_fetch_icons.py`             | Dev tool: downloads tech logos + UTPB favicons into `icons/`.       |
| `_inspect.py`                 | Dev tool: prints a structural summary of `slides.pptx`.             |
| `_render_previews.py`         | Dev tool: re-renders `previews/*.png` via PowerPoint COM (Windows). |
| `_validate_drawio.py`         | Dev tool: parses `system_design.drawio` and prints cell counts.     |

## Regenerating after edits

```powershell
python presentation\_fetch_icons.py        # one time — downloads icons (idempotent)
python presentation\build_deck.py          # rebuilds slides.pptx
python presentation\build_drawio.py        # rebuilds system_design.drawio
python presentation\_render_previews.py    # optional — refresh preview PNGs
```

The build scripts are deterministic. The architecture and database diagrams
are drawn natively as PowerPoint shapes (in the deck) and as mxCell shapes
(in the .drawio), so they're fully editable inside PowerPoint and draw.io
respectively. No external image dependency at runtime.

## The standalone .drawio file

`system_design.drawio` is a self-contained draw.io document with two pages:

1. **System architecture** — the same five-lane chart as slide 4 (UTPB
   Sources → scrapers → SQLite → Flask → Browser) with embedded brand
   logos and UTPB favicons, plus the optional Anthropic API callout.
2. **Database schema** — the same eight-table ER diagram as slide 6 with
   foreign-key lines between tables.

All icons are embedded as base64 PNGs inside the XML, so you can hand the
file to anyone without shipping the `icons/` folder. Open it via:

- the desktop app: <https://www.drawio.com/>
- in-browser: <https://app.diagrams.net/> → File → Open from Device
- VS Code: install the *Draw.io Integration* extension and open the file

## How the icons work

Slide 4 (System architecture) shows real logos for each layer of the stack:

- **UTPB Sources** — Google s2 favicons for `utpb.smartcatalogiq.com` and `utpb.edu`,
  one per scraped source (SmartCatalog, Registrar, Academic Calendar, Falcon Maps).
- **scrapers/** — Python logo (since these are pure stdlib Python scripts).
- **data/courses.db** — SQLite logo.
- **scheduler/** — Flask logo.
- **Browser** — HTML5, CSS, JavaScript logos.
- **Anthropic API box** — Anthropic/Claude logo.

Logos are pulled from `cdn.simpleicons.org` in brand colors and converted from SVG
to PNG via `svglib` + `reportlab`. Favicons come from Google's s2 service.
All assets are cached under `icons/`; the fetcher re-runs are idempotent.

## What still needs your touch

1. Replace `Your Name` on slide 1.
2. Capture and drop screenshots into `screenshots/` per `SCREENSHOTS.md`.
3. Update the GitHub URL on slide 10.
4. Run a 10-minute dry-run with a timer before the real presentation.

## Slide map (timing)

| #  | Title                          | Time    |
| -- | ------------------------------ | ------- |
| 1  | Title                          | 0:20    |
| 2  | Why this exists                | 0:40    |
| 3  | What it does (feature tour)    | 0:50    |
| 4  | System architecture            | 0:50    |
| 5  | Tech stack                     | 0:30    |
| 6  | Database schema                | 0:50    |
| 7  | Live demo (frame slide)        | 4:00    |
| 8  | Python design highlights       | 0:40    |
| 9  | Testing & data safety          | 0:30    |
| 10 | Wrap & questions               | 0:50    |
|    | **Total**                      | ~10:00  |
