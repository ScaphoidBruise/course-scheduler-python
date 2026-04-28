"""Generate presentation/system_design.drawio.

Two diagram tabs:
    1. "System architecture" — same lanes/icons/arrows as slide 4 of the deck.
    2. "Database schema"     — same 8-table ER chart as slide 6.

Tech logos and favicons are pulled from presentation/icons/ (run
_fetch_icons.py first if the folder is empty) and embedded as base64
data URIs so the .drawio file is fully self-contained.

Run from project root:

    python presentation\\build_drawio.py
"""
from __future__ import annotations

import base64
from pathlib import Path

HERE = Path(__file__).resolve().parent
ICONS_DIR = HERE / "icons"
OUT_PATH = HERE / "system_design.drawio"

# ---------------------------------------------------------------------------
# Palette (matches scheduler/static/style.css and the deck)
# ---------------------------------------------------------------------------

NAVY_DEEP = "#0A1628"
NAVY_MID = "#1B2A4A"
ACCENT = "#E8562A"
TEXT_LIGHT = "#E2E8F0"
TEXT_BODY = "#2C3E52"
MUTED = "#8899AA"
SURFACE = "#F0F2F5"
CARD = "#FFFFFF"
GRID = "#E2E8F0"

FONT_SANS = "Segoe UI"
FONT_MONO = "Consolas"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )


def icon_data_uri(slug: str) -> str | None:
    path = ICONS_DIR / f"{slug}.png"
    if not path.exists() or path.stat().st_size == 0:
        return None
    blob = base64.b64encode(path.read_bytes()).decode("ascii")
    # draw.io accepts the `image/png,base64,` form (comma in place of the
    # standard data-URI semicolon) because the style separator is `;`.
    return f"data:image/png,base64,{blob}"


class CellSink:
    """Accumulator that hands out unique cell IDs and builds mxCell XML."""

    def __init__(self, prefix: str):
        self._prefix = prefix
        self._n = 0
        self.cells: list[str] = []

    def new_id(self) -> str:
        self._n += 1
        return f"{self._prefix}{self._n}"

    # --- shape factories --------------------------------------------------

    def rect(self, value: str, x: int, y: int, w: int, h: int, *,
             fill: str, stroke: str | None = None,
             font_color: str = "#000", font_family: str = FONT_SANS,
             font_size: int = 12, bold: bool = False, italic: bool = False,
             align: str = "center", valign: str = "middle",
             parent: str = "1") -> str:
        font_style = (1 if bold else 0) + (2 if italic else 0)
        style_parts = [
            "rounded=0", "whiteSpace=wrap", "html=1",
            f"fillColor={fill}",
            f"strokeColor={stroke}" if stroke else "strokeColor=none",
            f"fontColor={font_color}",
            f"fontFamily={font_family}",
            f"fontSize={font_size}",
            f"fontStyle={font_style}",
            f"align={align}",
            f"verticalAlign={valign}",
        ]
        style = ";".join(style_parts) + ";"
        cid = self.new_id()
        self.cells.append(
            f'<mxCell id="{cid}" value="{xml_escape(value)}" '
            f'style="{style}" vertex="1" parent="{parent}">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/>'
            f'</mxCell>'
        )
        return cid

    def text(self, value: str, x: int, y: int, w: int, h: int, *,
             color: str = TEXT_BODY, font: str = FONT_MONO, size: int = 11,
             bold: bool = False, italic: bool = False,
             align: str = "center", valign: str = "middle",
             parent: str = "1") -> str:
        font_style = (1 if bold else 0) + (2 if italic else 0)
        style = (
            f"text;html=1;align={align};verticalAlign={valign};"
            f"fontFamily={font};fontSize={size};fontColor={color};"
            f"fontStyle={font_style};"
        )
        cid = self.new_id()
        self.cells.append(
            f'<mxCell id="{cid}" value="{xml_escape(value)}" '
            f'style="{style}" vertex="1" parent="{parent}">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/>'
            f'</mxCell>'
        )
        return cid

    def image(self, slug: str, x: int, y: int, w: int, h: int, *,
              parent: str = "1") -> str | None:
        uri = icon_data_uri(slug)
        if uri is None:
            return None
        style = (
            "shape=image;verticalLabelPosition=bottom;labelBackgroundColor=none;"
            "verticalAlign=top;aspect=fixed;imageAspect=0;"
            f"image={uri};"
        )
        cid = self.new_id()
        self.cells.append(
            f'<mxCell id="{cid}" value="" '
            f'style="{style}" vertex="1" parent="{parent}">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/>'
            f'</mxCell>'
        )
        return cid

    def edge(self, source: str, target: str, *, color: str = ACCENT,
             stroke_width: int = 2, dashed: bool = False,
             exit_x: float = 1.0, exit_y: float = 0.5,
             entry_x: float = 0.0, entry_y: float = 0.5,
             arrow_end: str = "classic", arrow_start: str = "none",
             parent: str = "1") -> str:
        style_parts = [
            f"endArrow={arrow_end}",
            f"startArrow={arrow_start}",
            "html=1", "rounded=0",
            f"strokeColor={color}",
            f"strokeWidth={stroke_width}",
            f"exitX={exit_x}", f"exitY={exit_y}", "exitDx=0", "exitDy=0",
            f"entryX={entry_x}", f"entryY={entry_y}", "entryDx=0", "entryDy=0",
        ]
        if dashed:
            style_parts.append("dashed=1")
        style = ";".join(style_parts) + ";"
        cid = self.new_id()
        self.cells.append(
            f'<mxCell id="{cid}" value="" style="{style}" '
            f'edge="1" parent="{parent}" source="{source}" target="{target}">'
            f'<mxGeometry relative="1" as="geometry"/>'
            f'</mxCell>'
        )
        return cid


# ---------------------------------------------------------------------------
# Page 1 — System architecture
# ---------------------------------------------------------------------------

ARCH_PAGE_W = 1500
ARCH_PAGE_H = 900
ARCH_LANES = [
    {
        "header": "UTPB Sources",
        "header_color": NAVY_DEEP,
        "logos": [],
        "items": [
            ("site_smartcatalog", "SmartCatalog"),
            ("site_utpb", "Registrar"),
            ("site_utpb", "Academic Calendar"),
            ("site_utpb", "Falcon Maps"),
        ],
        "footer": None,
    },
    {
        "header": "scrapers/",
        "header_color": NAVY_DEEP,
        "logos": ["python"],
        "items": [
            (None, "catalog.py"),
            (None, "sections.py"),
            (None, "session_dates.py"),
            (None, "infer_terms.py"),
            (None, "program_reqs.py"),
        ],
        "footer": "stdlib only · urllib + re + html",
    },
    {
        "header": "data/courses.db",
        "header_color": NAVY_MID,
        "logos": ["sqlite"],
        "items": [
            (None, "SQLite"),
            (None, "single file"),
            (None, "8 tables"),
            (None, "catalog + app data"),
        ],
        "footer": "the hub",
    },
    {
        "header": "scheduler/",
        "header_color": NAVY_DEEP,
        "logos": ["flask"],
        "items": [
            (None, "app.py · 50+ routes"),
            (None, "db.py · SQL helpers"),
            (None, "conflict.py"),
            (None, "transcript_pdf.py"),
        ],
        "footer": "Flask · JSON API",
    },
    {
        "header": "Browser",
        "header_color": NAVY_DEEP,
        "logos": ["html5", "css", "javascript"],
        "items": [
            (None, "pages/*.html"),
            (None, "static/*.js"),
            (None, "style.css"),
            (None, "vanilla JS only"),
        ],
        "footer": None,
    },
]


def build_architecture_page() -> str:
    sink = CellSink("a")

    # Title bar at top of page
    sink.rect(
        "System architecture", 60, 30, ARCH_PAGE_W - 120, 40,
        fill=NAVY_DEEP, font_color=TEXT_LIGHT, font_size=18, bold=True,
        align="left",
    )
    sink.rect(
        "", 60, 76, 120, 6, fill=ACCENT,
    )
    sink.text(
        "Five layers, one SQLite file. Data flows left → right; control stays on your machine.",
        60, 92, ARCH_PAGE_W - 120, 28,
        color=MUTED, font=FONT_SANS, size=12, italic=True, align="left",
    )

    # Lanes
    n_lanes = len(ARCH_LANES)
    lane_w = 240
    lane_h = 540
    lane_y = 150
    lane_gap = 36
    total_w = n_lanes * lane_w + (n_lanes - 1) * lane_gap
    lanes_x0 = (ARCH_PAGE_W - total_w) // 2

    header_h = 40
    strip_h = 90
    footer_h = 32
    item_pad_x = 16

    lane_card_ids: list[str] = []

    for i, lane in enumerate(ARCH_LANES):
        lane_x = lanes_x0 + i * (lane_w + lane_gap)

        card_id = sink.rect(
            "", lane_x, lane_y, lane_w, lane_h,
            fill=CARD, stroke=GRID, font_color=TEXT_BODY,
        )
        lane_card_ids.append(card_id)

        sink.rect(
            lane["header"], lane_x, lane_y, lane_w, header_h,
            fill=lane["header_color"], font_color=TEXT_LIGHT,
            font_family=FONT_SANS, font_size=14, bold=True,
        )

        cursor_y = lane_y + header_h
        if lane["logos"]:
            n_logos = len(lane["logos"])
            max_icon = min(64, (lane_w - 40) // n_logos)
            gap = 10
            row_w = n_logos * max_icon + (n_logos - 1) * gap
            x0 = lane_x + (lane_w - row_w) // 2
            y0 = cursor_y + (strip_h - max_icon) // 2
            for j, slug in enumerate(lane["logos"]):
                sink.image(slug, x0 + j * (max_icon + gap), y0, max_icon, max_icon)
            cursor_y += strip_h
        else:
            cursor_y += 12

        items = lane["items"]
        has_footer = lane["footer"] is not None
        item_area_h = (lane_y + lane_h) - cursor_y - (footer_h if has_footer else 0)
        n_items = max(len(items), 1)
        per_item = item_area_h // n_items

        for j, (icon_slug, text) in enumerate(items):
            row_y = cursor_y + j * per_item
            if icon_slug:
                ico_size = min(per_item - 8, 24)
                ico_x = lane_x + item_pad_x
                ico_y = row_y + (per_item - ico_size) // 2
                sink.image(icon_slug, ico_x, ico_y, ico_size, ico_size)
                text_x = ico_x + ico_size + 10
                text_w = lane_x + lane_w - text_x - item_pad_x
                sink.text(text, text_x, row_y, text_w, per_item,
                          color=TEXT_BODY, align="left", size=12)
            else:
                sink.text(text, lane_x + item_pad_x, row_y,
                          lane_w - 2 * item_pad_x, per_item,
                          color=TEXT_BODY, align="center", size=12)

        if has_footer:
            sink.text(lane["footer"], lane_x, lane_y + lane_h - footer_h,
                      lane_w, footer_h,
                      color=ACCENT, font=FONT_SANS, italic=True, size=11)

    # Arrows between lanes
    for i in range(n_lanes - 1):
        sink.edge(lane_card_ids[i], lane_card_ids[i + 1])

    # Anthropic API box hanging off the scheduler/ lane (lane index 3)
    flask_x = lanes_x0 + 3 * (lane_w + lane_gap)
    ant_x = flask_x
    ant_y = lane_y + lane_h + 60
    ant_w = lane_w
    ant_h = 80

    ant_card = sink.rect(
        "", ant_x, ant_y, ant_w, ant_h,
        fill=SURFACE, stroke=MUTED,
    )
    sink.image("anthropic", ant_x + 14, ant_y + 16, 48, 48)
    sink.text("Anthropic API", ant_x + 76, ant_y + 8, ant_w - 86, 32,
              color=NAVY_DEEP, font=FONT_SANS, size=14, bold=True,
              align="left")
    sink.text("optional · falls back to local rules",
              ant_x + 76, ant_y + 40, ant_w - 86, 28,
              color=MUTED, font=FONT_SANS, italic=True, size=11,
              align="left")

    # Dashed connector from scheduler lane bottom-center to anthropic top-center
    sink.edge(
        lane_card_ids[3], ant_card,
        color=MUTED, stroke_width=1, dashed=True,
        exit_x=0.5, exit_y=1.0, entry_x=0.5, entry_y=0.0,
        arrow_end="none", arrow_start="none",
    )

    # Legend bottom-right
    legend_x = lanes_x0 + total_w - 320
    legend_y = lane_y + lane_h + 60
    sink.rect("", legend_x, legend_y, 320, 80,
              fill=CARD, stroke=GRID)
    sink.text("Legend", legend_x + 12, legend_y + 6, 300, 22,
              color=NAVY_DEEP, font=FONT_SANS, size=12, bold=True, align="left")
    sink.rect("", legend_x + 14, legend_y + 38, 24, 4, fill=ACCENT)
    sink.text("data flow (HTTP / disk)",
              legend_x + 46, legend_y + 30, 260, 22,
              color=TEXT_BODY, font=FONT_SANS, size=11, align="left")
    sink.rect("", legend_x + 14, legend_y + 60, 24, 2, fill=MUTED)
    sink.text("optional / dashed = on demand",
              legend_x + 46, legend_y + 52, 260, 22,
              color=TEXT_BODY, font=FONT_SANS, size=11, align="left")

    return wrap_diagram("sys-arch", "System architecture",
                        ARCH_PAGE_W, ARCH_PAGE_H, sink.cells)


# ---------------------------------------------------------------------------
# Page 2 — Database schema
# ---------------------------------------------------------------------------

DB_PAGE_W = 1400
DB_PAGE_H = 900

DB_TABLES = {
    (0, 0): ("users", [
        ("id", "PK"), ("username", "TEXT"),
        ("password_hash", "TEXT"), ("created_at", "TS"),
    ], NAVY_DEEP),
    (0, 1): ("user_profiles", [
        ("user_id", "PK/FK"), ("major", "TEXT"),
        ("minor", "TEXT"), ("transcript_json", "JSON"),
    ], NAVY_DEEP),
    (0, 2): ("course_wishlist", [
        ("id", "PK"), ("user_id", "FK"), ("course_id", "FK"),
    ], NAVY_DEEP),
    (1, 0): ("schedule_scenarios", [
        ("id", "PK"), ("user_id", "FK"),
        ("term", "TEXT"), ("name", "TEXT"), ("is_active", "BOOL"),
    ], NAVY_DEEP),
    (1, 1): ("user_schedules", [
        ("id", "PK"), ("scenario_id", "FK"),
        ("user_id", "FK"), ("section_id", "FK"),
    ], NAVY_DEEP),
    (2, 0): ("courses", [
        ("id", "PK"), ("code", "TEXT"), ("name", "TEXT"),
        ("prereqs", "TEXT"), ("term_inferred", "TEXT"),
    ], NAVY_MID),
    (2, 1): ("sections", [
        ("id", "PK"), ("term", "TEXT"), ("section_code", "TEXT"),
        ("days/times", "TEXT"), ("session", "TEXT"),
    ], NAVY_MID),
    (2, 2): ("session_calendar", [
        ("term", "TEXT"), ("session", "TEXT"),
        ("start_date", "DATE"), ("end_date", "DATE"),
    ], NAVY_MID),
}

# (from, to) — relationships drawn as plain lines
DB_RELS = [
    ((0, 0), (0, 1)),
    ((0, 0), (1, 0)),
    ((1, 0), (1, 1)),
    ((1, 1), (2, 1)),
    ((2, 0), (2, 1)),
    ((2, 1), (2, 2)),
    ((0, 0), (0, 2)),
]


def build_database_page() -> str:
    sink = CellSink("d")

    # Title
    sink.rect(
        "Database schema · data/courses.db", 60, 30, DB_PAGE_W - 120, 40,
        fill=NAVY_DEEP, font_color=TEXT_LIGHT, font_size=18, bold=True,
        align="left",
    )
    sink.rect("", 60, 76, 120, 6, fill=ACCENT)
    sink.text(
        "Eight tables in one SQLite file. Catalog tables (right) and app tables (left/center) "
        "co-exist; scrapers update only their own tables.",
        60, 92, DB_PAGE_W - 120, 28,
        color=MUTED, font=FONT_SANS, size=12, italic=True, align="left",
    )

    # 3x3 grid of tables
    cols = 3
    rows = 3
    grid_x0 = 100
    grid_y0 = 160
    cell_w = 360
    cell_h = 200
    h_gap = 60
    v_gap = 50
    header_h = 36

    cell_ids: dict[tuple[int, int], str] = {}

    for (col, row), (name, columns, header_color) in DB_TABLES.items():
        x = grid_x0 + col * (cell_w + h_gap)
        y = grid_y0 + row * (cell_h + v_gap)

        outer = sink.rect("", x, y, cell_w, cell_h,
                          fill=CARD, stroke=GRID)
        cell_ids[(col, row)] = outer

        sink.rect(name, x, y, cell_w, header_h,
                  fill=header_color, font_color=TEXT_LIGHT,
                  font_family=FONT_MONO, font_size=14, bold=True)

        rows_top = y + header_h + 4
        per_row = (cell_h - header_h - 8) // max(len(columns), 1)
        for i, (col_name, col_type) in enumerate(columns):
            row_y = rows_top + i * per_row
            sink.text(col_name, x + 16, row_y, cell_w - 110, per_row,
                      color=TEXT_BODY, font=FONT_MONO, size=12,
                      align="left")
            sink.text(col_type, x + cell_w - 110, row_y, 92, per_row,
                      color=MUTED, font=FONT_MONO, size=11,
                      align="right")

    # Relationships (simple lines, no arrowheads — ER style)
    for src_pos, dst_pos in DB_RELS:
        sink.edge(
            cell_ids[src_pos], cell_ids[dst_pos],
            color=NAVY_MID, stroke_width=1.5,
            arrow_end="none", arrow_start="none",
            exit_x=0.5, exit_y=1.0, entry_x=0.5, entry_y=0.0,
        )

    return wrap_diagram("sys-db", "Database schema",
                        DB_PAGE_W, DB_PAGE_H, sink.cells)


# ---------------------------------------------------------------------------
# Document scaffolding
# ---------------------------------------------------------------------------

def wrap_diagram(diagram_id: str, name: str, width: int, height: int,
                 cells: list[str]) -> str:
    body = "".join(cells)
    return (
        f'<diagram id="{diagram_id}" name="{xml_escape(name)}">'
        f'<mxGraphModel dx="{width}" dy="{height}" grid="1" gridSize="10" '
        f'guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" '
        f'pageScale="1" pageWidth="{width}" pageHeight="{height}" math="0" shadow="0">'
        '<root>'
        '<mxCell id="0"/>'
        '<mxCell id="1" parent="0"/>'
        f'{body}'
        '</root>'
        '</mxGraphModel>'
        '</diagram>'
    )


def main() -> int:
    print("Building system_design.drawio …")
    pages = [
        build_architecture_page(),
        build_database_page(),
    ]
    doc = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<mxfile host="presentation/build_drawio.py" '
        'agent="build_drawio.py 1.0" version="24.0.0" type="device">'
        f'{"".join(pages)}'
        '</mxfile>'
    )
    OUT_PATH.write_text(doc, encoding="utf-8")
    size_kb = OUT_PATH.stat().st_size // 1024
    print(f"  + wrote {OUT_PATH.relative_to(HERE.parent)}  ({size_kb} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
