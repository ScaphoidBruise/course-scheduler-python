import argparse
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urljoin
from urllib.request import urlopen


BASE_URL = "https://utpb.smartcatalogiq.com"
CATALOG_YEAR = "2025-2026"
CATALOG_JSON_URL = (
    "https://utpb.smartcatalogiq.com/Institutions/The-University-of-Texas-Permian-Basin/"
    "json/2025-2026/2025-2026-Undergraduate-Catalog.json"
)
PROGRAMS_PATH = "/2025-2026/2025-2026-Undergraduate-Catalog/Programs-of-Study"
DEFAULT_DB = "data/courses.db"
REQUEST_TIMEOUT_SECONDS = 20
COURSE_CODE_RE = re.compile(r"\b([A-Z]{2,5})\s*([0-9]{4}[A-Z]?)\b")
OPTION_WORD_RE = re.compile(r"\b(choose|select|option|track|elective|concentration|minor)\b", re.IGNORECASE)
DEGREE_TOTAL_RE = re.compile(
    r"\b(?:minimum of|requires|require|complete|completion of|consists of|total of)?\s*"
    r"(\d+(?:\.\d+)?)\s*(?:semester\s*)?(?:credit hours|credits|hours|sch)\b",
    re.IGNORECASE,
)
DEGREE_TOTAL_IS_RE = re.compile(
    r"\b(?:minimum\s+)?total\s+credits\s+required\b.{0,80}?\bis\s+(\d+(?:\.\d+)?)\b",
    re.IGNORECASE,
)


PROGRAM_REQUIREMENTS_DDL = """
CREATE TABLE IF NOT EXISTS program_requirements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    catalog_year TEXT NOT NULL,
    program_name TEXT NOT NULL,
    program_path TEXT NOT NULL,
    source_url TEXT NOT NULL,
    total_credits REAL,
    degree_total_credits REAL,
    fetched_at TEXT NOT NULL,
    UNIQUE(catalog_year, program_path)
)
"""

PROGRAM_BLOCKS_DDL = """
CREATE TABLE IF NOT EXISTS program_requirement_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    program_id INTEGER NOT NULL,
    parent_block_id INTEGER,
    heading TEXT NOT NULL,
    level INTEGER NOT NULL,
    display_order INTEGER NOT NULL,
    requirement_type TEXT NOT NULL DEFAULT 'required_all',
    choice_group TEXT,
    is_optional INTEGER NOT NULL DEFAULT 0,
    min_credits REAL,
    raw_notes TEXT,
    FOREIGN KEY (program_id) REFERENCES program_requirements(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_block_id) REFERENCES program_requirement_blocks(id) ON DELETE CASCADE
)
"""

PROGRAM_COURSES_DDL = """
CREATE TABLE IF NOT EXISTS program_requirement_courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    block_id INTEGER NOT NULL,
    course_code TEXT NOT NULL,
    course_title TEXT,
    credits REAL,
    display_order INTEGER NOT NULL,
    FOREIGN KEY (block_id) REFERENCES program_requirement_blocks(id) ON DELETE CASCADE
)
"""


@dataclass
class ProgramRef:
    name: str
    path: str

    @property
    def url(self) -> str:
        return urljoin(BASE_URL, "/en/" + self.path.strip("/").lower() + "/")


@dataclass
class RequirementCourse:
    course_code: str
    course_title: str
    credits: float | None
    display_order: int


@dataclass
class RequirementBlock:
    heading: str
    level: int
    display_order: int
    requirement_type: str = "required_all"
    choice_group: str | None = None
    is_optional: bool = False
    min_credits: float | None = None
    raw_notes: list[str] = field(default_factory=list)
    courses: list[RequirementCourse] = field(default_factory=list)
    parent_index: int | None = None


@dataclass
class ProgramRequirements:
    name: str
    path: str
    source_url: str
    total_credits: float | None
    degree_total_credits: float | None
    fetched_at: str
    blocks: list[RequirementBlock]
    warnings: list[str]


def build_parser():
    parser = argparse.ArgumentParser(description="Scrape UTPB SmartCatalog program requirements.")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to SQLite DB")
    parser.add_argument("--program", action="append", help="Program name/path substring. Can be repeated.")
    parser.add_argument("--all-programs", action="store_true", help="Scrape all Programs of Study")
    parser.add_argument("--dry-run", action="store_true", help="Parse and report without writing to the database")
    parser.add_argument("--limit", type=int, help="Limit selected programs, useful while reviewing parser output")
    parser.add_argument("--output-json", help="Write parsed program data to this JSON file")
    parser.add_argument("--catalog-json-url", default=CATALOG_JSON_URL, help="SmartCatalog root JSON URL")
    parser.add_argument("--quiet", action="store_true", help="Only print summary lines")
    return parser


def parse_args(argv=None):
    return build_parser().parse_args(argv)


def get_json(url):
    with urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def get_text(url):
    with urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8", "ignore")


def _clean_text(value: str) -> str:
    return unescape(re.sub(r"\s+", " ", str(value or ""))).strip()


def _credit_value(value: str | None) -> float | None:
    match = re.search(r"\d+(?:\.\d+)?", str(value or ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _normalize_course_code(value: str) -> str | None:
    match = COURSE_CODE_RE.search(str(value or "").upper())
    if not match:
        return None
    return f"{match.group(1)} {match.group(2)}"


def _degree_total_from_text(text: str) -> float | None:
    candidates: list[float] = []
    for regex in (DEGREE_TOTAL_RE, DEGREE_TOTAL_IS_RE):
        for match in regex.finditer(text or ""):
            try:
                value = float(match.group(1))
            except ValueError:
                continue
            if 90 <= value <= 140:
                candidates.append(value)
    return max(candidates) if candidates else None


def _degree_total_from_blocks(blocks: list[RequirementBlock]) -> float | None:
    children_by_parent: dict[int, list[RequirementBlock]] = {}
    for block in blocks:
        if block.parent_index is not None:
            children_by_parent.setdefault(block.parent_index, []).append(block)

    total = 0.0
    for block in blocks:
        if block.is_optional or block.display_order in children_by_parent:
            continue
        if block.min_credits is None:
            continue
        total += block.min_credits
    if 90 <= total <= 140:
        return total
    return None


def _infer_requirement_type(block: RequirementBlock) -> tuple[str, bool, str | None]:
    text = _clean_text(" ".join([block.heading, *block.raw_notes])).casefold()
    heading = block.heading.casefold()
    credits_sum = sum(course.credits or 0 for course in block.courses)

    if re.search(r"\b(optional|not required)\b", text) or "teacher certification" in text:
        return "optional", True, None
    if "minor" in heading and ("optional" in text or "not required" in text):
        return "optional", True, None
    if "track" in heading or re.search(r"\b(choose|select)\s+one\s+track\b", text):
        return "choice_option", False, "track"
    if "choose" in text or "select" in text or "one of" in text:
        return "choose_from", False, None
    if block.min_credits is not None and credits_sum > block.min_credits > 0:
        return "choose_from", False, None
    return "required_all", False, None


def _apply_requirement_classification(blocks: list[RequirementBlock]):
    for block in blocks:
        requirement_type, is_optional, choice_group = _infer_requirement_type(block)
        block.requirement_type = requirement_type
        block.is_optional = is_optional
        block.choice_group = choice_group


def _content_blocks_with_ancestors(blocks: list[RequirementBlock]) -> list[RequirementBlock]:
    include_indexes = {
        block.display_order
        for block in blocks
        if block.courses or block.min_credits is not None or block.raw_notes
    }
    parent_by_index = {block.display_order: block.parent_index for block in blocks}
    for index in list(include_indexes):
        parent = parent_by_index.get(index)
        while parent is not None:
            include_indexes.add(parent)
            parent = parent_by_index.get(parent)
    return [block for block in blocks if block.display_order in include_indexes]


def _find_node_by_path(node, path: str):
    if not isinstance(node, dict):
        return None
    if str(node.get("Path") or "").rstrip("/") == path.rstrip("/"):
        return node
    for child in node.get("Children") or []:
        found = _find_node_by_path(child, path)
        if found:
            return found
    return None


def discover_programs(catalog_json) -> list[ProgramRef]:
    node = _find_node_by_path(catalog_json, PROGRAMS_PATH)
    if not node:
        raise ValueError("Could not find Programs of Study in SmartCatalog JSON.")
    programs = []

    def visit(child):
        children = child.get("Children") or []
        if children:
            for grandchild in children:
                visit(grandchild)
            return
        name = _clean_text(child.get("Name") or "")
        path = str(child.get("Path") or "").strip()
        if name and path:
            programs.append(ProgramRef(name=name, path=path))

    for child in node.get("Children") or []:
        visit(child)
    return programs


class ProgramHTMLParser(HTMLParser):
    def __init__(self, program: ProgramRef):
        super().__init__(convert_charrefs=True)
        self.program = program
        self.blocks: list[RequirementBlock] = []
        self.warnings: list[str] = []
        self._heading_tag: str | None = None
        self._heading_parts: list[str] = []
        self._note_tag: str | None = None
        self._note_parts: list[str] = []
        self._in_table = False
        self._in_tr = False
        self._cell_tag: str | None = None
        self._cell_parts: list[str] = []
        self._row_cells: list[str] = []
        self._level_stack: dict[int, int] = {}
        self.text_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag in {"h2", "h3", "h4"}:
            self._heading_tag = tag
            self._heading_parts = []
        elif tag == "table":
            self._in_table = True
        elif tag == "tr" and self._in_table:
            self._in_tr = True
            self._row_cells = []
        elif tag in {"td", "th"} and self._in_tr:
            self._cell_tag = tag
            self._cell_parts = []
        elif tag in {"p", "li"} and not self._in_table:
            self._note_tag = tag
            self._note_parts = []
        if tag == "br" and self._cell_tag:
            self._cell_parts.append(" ")
        if tag == "br" and self._note_tag:
            self._note_parts.append(" ")
        if attrs_dict.get("class") and "sc-courselink" in attrs_dict.get("class", "") and self._cell_tag:
            self._cell_parts.append(" ")

    def handle_endtag(self, tag):
        if self._heading_tag == tag:
            self._add_heading(_clean_text(" ".join(self._heading_parts)))
            self._heading_tag = None
            self._heading_parts = []
        elif tag == "table":
            self._in_table = False
        elif tag in {"td", "th"} and self._cell_tag == tag:
            self._row_cells.append(_clean_text(" ".join(self._cell_parts)))
            self._cell_tag = None
            self._cell_parts = []
        elif tag == "tr" and self._in_tr:
            self._handle_row(self._row_cells)
            self._in_tr = False
            self._row_cells = []
        elif self._note_tag == tag:
            self._add_note(_clean_text(" ".join(self._note_parts)))
            self._note_tag = None
            self._note_parts = []

    def handle_data(self, data):
        if data:
            self.text_parts.append(data)
        if self._heading_tag:
            self._heading_parts.append(data)
        elif self._cell_tag:
            self._cell_parts.append(data)
        elif self._note_tag:
            self._note_parts.append(data)

    def _add_heading(self, heading: str):
        if not heading:
            return
        level = int(self._heading_tag[1]) if self._heading_tag else 3
        parent_index = None
        for candidate in range(level - 1, 1, -1):
            if candidate in self._level_stack:
                parent_index = self._level_stack[candidate]
                break
        block = RequirementBlock(
            heading=heading,
            level=level,
            display_order=len(self.blocks),
            parent_index=parent_index,
        )
        self.blocks.append(block)
        self._level_stack[level] = block.display_order
        for stale in [key for key in self._level_stack if key > level]:
            del self._level_stack[stale]

    def _current_block(self) -> RequirementBlock | None:
        if not self.blocks:
            return None
        return self.blocks[-1]

    def _add_note(self, note: str):
        if not note or len(note) < 3:
            return
        if "total credit hours" in note.lower():
            credit = _credit_value(note)
            if credit is not None:
                self._assign_total_credit(credit)
                return
        block = self._current_block()
        if block:
            block.raw_notes.append(note)

    def _parent_block(self, block: RequirementBlock) -> RequirementBlock | None:
        if block.parent_index is None:
            return None
        for candidate in self.blocks:
            if candidate.display_order == block.parent_index:
                return candidate
        return None

    def _assign_total_credit(self, credit: float):
        block = self._current_block()
        if not block:
            return
        course_credits = sum(course.credits or 0 for course in block.courses)
        parent = self._parent_block(block)
        if parent and (not block.courses or credit > course_credits):
            parent.min_credits = credit
        else:
            block.min_credits = credit

    def _handle_row(self, cells: list[str]):
        if len(cells) < 2:
            return
        block = self._current_block()
        if not block:
            return
        joined = " ".join(cells)
        if "course number" in joined.lower() and "course title" in joined.lower():
            return
        if "total credit hours" in joined.lower():
            credit = _credit_value(cells[-1])
            if credit is not None:
                self._assign_total_credit(credit)
            return
        code = _normalize_course_code(cells[0])
        if not code:
            if any(_normalize_course_code(cell) for cell in cells):
                self.warnings.append(f"Possible course row with unexpected layout under {block.heading}: {joined[:120]}")
            return
        title = cells[1] if len(cells) > 1 else ""
        credits = _credit_value(cells[2] if len(cells) > 2 else None)
        block.courses.append(
            RequirementCourse(
                course_code=code,
                course_title=title,
                credits=credits,
                display_order=len(block.courses),
            )
        )


def parse_program_html(program: ProgramRef, html: str, fetched_at: str | None = None) -> ProgramRequirements:
    parser = ProgramHTMLParser(program)
    parser.feed(html)
    blocks = _content_blocks_with_ancestors(parser.blocks)
    warnings = list(parser.warnings)
    if not blocks:
        warnings.append("No requirement blocks were parsed.")
    if not any(block.courses for block in blocks):
        warnings.append("No course rows were parsed.")
    if not any(block.min_credits is not None for block in blocks):
        warnings.append("No Total Credit Hours rows were parsed.")
    for block in blocks:
        option_text = " ".join([block.heading, *block.raw_notes])
        if OPTION_WORD_RE.search(option_text):
            warnings.append(f"Option-like text preserved for review under: {block.heading}")
    _apply_requirement_classification(blocks)
    total_credits = None
    for block in blocks:
        if block.heading.lower() == "degree requirements" and block.min_credits is not None:
            total_credits = block.min_credits
            break
    if total_credits is None:
        totals = [block.min_credits for block in blocks if block.min_credits is not None]
        total_credits = max(totals) if totals else None
    degree_total_credits = _degree_total_from_text(_clean_text(" ".join(parser.text_parts)))
    if degree_total_credits is None:
        degree_total_credits = _degree_total_from_blocks(blocks)
    if degree_total_credits is None and total_credits is not None and total_credits >= 90:
        degree_total_credits = total_credits
    if degree_total_credits is None and re.search(r"\b(BS|BA|BBA|BFA|BM|BSN|BSW)\b", program.name):
        degree_total_credits = 120.0
        warnings.append("Whole-degree credit total inferred as 120 for undergraduate degree.")
    if degree_total_credits is None:
        warnings.append("No whole-degree credit total was parsed.")
    elif total_credits != degree_total_credits:
        warnings.append(
            "Whole-degree credit total differs from table total; using degree_total_credits for audits."
        )
    return ProgramRequirements(
        name=program.name,
        path=program.path,
        source_url=program.url,
        total_credits=total_credits,
        degree_total_credits=degree_total_credits,
        fetched_at=fetched_at or datetime.now(UTC).isoformat(timespec="seconds"),
        blocks=blocks,
        warnings=warnings,
    )


def program_to_dict(program: ProgramRequirements) -> dict:
    return {
        "name": program.name,
        "path": program.path,
        "source_url": program.source_url,
        "total_credits": program.total_credits,
        "degree_total_credits": program.degree_total_credits,
        "fetched_at": program.fetched_at,
        "warnings": program.warnings,
        "blocks": [
            {
                "heading": block.heading,
                "level": block.level,
                "display_order": block.display_order,
                "parent_index": block.parent_index,
                "requirement_type": block.requirement_type,
                "choice_group": block.choice_group,
                "is_optional": block.is_optional,
                "min_credits": block.min_credits,
                "raw_notes": block.raw_notes,
                "courses": [
                    {
                        "course_code": course.course_code,
                        "course_title": course.course_title,
                        "credits": course.credits,
                        "display_order": course.display_order,
                    }
                    for course in block.courses
                ],
            }
            for block in program.blocks
        ],
    }


def _program_requirement_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def ensure_schema(conn: sqlite3.Connection):
    conn.execute("PRAGMA foreign_keys = ON")
    existing_program_cols = _program_requirement_columns(conn, "program_requirements")
    existing_block_cols = _program_requirement_columns(conn, "program_requirement_blocks")
    needs_rebuild = (
        existing_program_cols
        and (
            "degree_total_credits" not in existing_program_cols
            or "requirement_type" not in existing_block_cols
        )
    )
    if needs_rebuild:
        conn.execute("DROP TABLE IF EXISTS program_requirement_courses")
        conn.execute("DROP TABLE IF EXISTS program_requirement_blocks")
        conn.execute("DROP TABLE IF EXISTS program_requirements")
    conn.execute(PROGRAM_REQUIREMENTS_DDL)
    conn.execute(PROGRAM_BLOCKS_DDL)
    conn.execute(PROGRAM_COURSES_DDL)


def save_programs(db_path: Path, programs: list[ProgramRequirements]):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        ensure_schema(conn)
        paths = [program.path for program in programs]
        if paths:
            placeholders = ",".join("?" for _ in paths)
            rows = conn.execute(
                f"""
                SELECT id FROM program_requirements
                WHERE catalog_year = ? AND program_path IN ({placeholders})
                """,
                [CATALOG_YEAR, *paths],
            ).fetchall()
            ids = [row["id"] if isinstance(row, sqlite3.Row) else row[0] for row in rows]
            if ids:
                id_placeholders = ",".join("?" for _ in ids)
                block_rows = conn.execute(
                    f"SELECT id FROM program_requirement_blocks WHERE program_id IN ({id_placeholders})",
                    ids,
                ).fetchall()
                block_ids = [row["id"] if isinstance(row, sqlite3.Row) else row[0] for row in block_rows]
                if block_ids:
                    conn.execute(
                        f"DELETE FROM program_requirement_courses WHERE block_id IN ({','.join('?' for _ in block_ids)})",
                        block_ids,
                    )
                conn.execute(f"DELETE FROM program_requirement_blocks WHERE program_id IN ({id_placeholders})", ids)
                conn.execute(f"DELETE FROM program_requirements WHERE id IN ({id_placeholders})", ids)

        for program in programs:
            cursor = conn.execute(
                """
                INSERT INTO program_requirements (
                    catalog_year, program_name, program_path, source_url,
                    total_credits, degree_total_credits, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    CATALOG_YEAR,
                    program.name,
                    program.path,
                    program.source_url,
                    program.total_credits,
                    program.degree_total_credits,
                    program.fetched_at,
                ),
            )
            program_id = cursor.lastrowid
            block_id_by_index: dict[int, int] = {}
            for block in program.blocks:
                parent_id = block_id_by_index.get(block.parent_index) if block.parent_index is not None else None
                cursor = conn.execute(
                    """
                    INSERT INTO program_requirement_blocks (
                        program_id, parent_block_id, heading, level, display_order,
                        requirement_type, choice_group, is_optional, min_credits, raw_notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        program_id,
                        parent_id,
                        block.heading,
                        block.level,
                        block.display_order,
                        block.requirement_type,
                        block.choice_group,
                        1 if block.is_optional else 0,
                        block.min_credits,
                        "\n".join(block.raw_notes),
                    ),
                )
                block_id = cursor.lastrowid
                block_id_by_index[block.display_order] = block_id
                for course in block.courses:
                    conn.execute(
                        """
                        INSERT INTO program_requirement_courses (
                            block_id, course_code, course_title, credits, display_order
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            block_id,
                            course.course_code,
                            course.course_title,
                            course.credits,
                            course.display_order,
                        ),
                    )
        conn.commit()
    finally:
        conn.close()


def _select_programs(programs: list[ProgramRef], args) -> list[ProgramRef]:
    if args.all_programs:
        selected = list(programs)
    elif args.program:
        selected = []
        needles = [item.casefold() for item in args.program]
        for program in programs:
            haystack = f"{program.name} {program.path}".casefold()
            if any(needle in haystack for needle in needles):
                selected.append(program)
        if not selected:
            raise SystemExit("No programs matched --program filters.")
    else:
        print("Use --all-programs or --program NAME. Available programs:")
        for program in programs:
            print(f"  - {program.name}")
        raise SystemExit(2)
    if args.limit:
        selected = selected[: args.limit]
    return selected


def _print_report(programs: list[ProgramRequirements], quiet: bool = False):
    total_blocks = sum(len(program.blocks) for program in programs)
    total_courses = sum(len(block.courses) for program in programs for block in program.blocks)
    total_warnings = sum(len(program.warnings) for program in programs)
    print(f"Programs parsed: {len(programs)}")
    print(f"Requirement blocks: {total_blocks}")
    print(f"Requirement courses: {total_courses}")
    print(f"Warnings: {total_warnings}")
    if quiet:
        return
    for program in programs:
        print(
            f"- {program.name}: {len(program.blocks)} blocks, "
            f"{sum(len(block.courses) for block in program.blocks)} courses, "
            f"total credits={program.total_credits if program.total_credits is not None else 'unknown'}, "
            f"warnings={len(program.warnings)}"
        )
        for warning in program.warnings[:3]:
            print(f"  warning: {warning}")


def run(args):
    catalog = get_json(args.catalog_json_url)
    available = discover_programs(catalog)
    selected = _select_programs(available, args)
    fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
    parsed: list[ProgramRequirements] = []
    for index, program in enumerate(selected, start=1):
        if not args.quiet:
            print(f"[{index}/{len(selected)}] {program.name}")
        html = get_text(program.url)
        parsed.append(parse_program_html(program, html, fetched_at=fetched_at))

    if args.output_json:
        out_path = Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps([program_to_dict(p) for p in parsed], indent=2), encoding="utf-8")
        print(f"JSON review output: {out_path}")

    _print_report(parsed, quiet=args.quiet)
    if args.dry_run:
        print("Dry run: database was not modified.")
        return
    save_programs(Path(args.db), parsed)
    print(f"Database updated: {Path(args.db).resolve()}")


def main(argv=None):
    run(parse_args(argv))


if __name__ == "__main__":
    main()
