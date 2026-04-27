"""
Parse UTPB-style unofficial transcript PDFs (Banner-style layout).

Text extraction order can vary by PDF generator; regexes are intentionally
lenient. Callers should treat numeric fields as best-effort when layout shifts.
"""

from __future__ import annotations

import io
import json
import math
import re
from pathlib import Path
from typing import BinaryIO

from pypdf import PdfReader

# Avoid pathological regex runtimes on huge one-line PDF extracts.
_MAX_COURSE_RECORD_MATCHES_PER_CHUNK = 500

_COURSE_CODE = re.compile(r"\b([A-Z]{2,5})\s+(\d{4})\b")
_MAJOR = re.compile(r"([A-Za-z][A-Za-z\s,&'\-]{2,60}?)\s+Major\b")
_MINOR = re.compile(r"([A-Za-z][A-Za-z\s,&'\-]{2,60}?)\s+Minor\b")
_SEASON = r"(?:Fall|Spring|Summer|Winter)"
# Must capture year + season separately (group 1 / group 2) for all call sites.
_SEASON_CAP = r"(Fall|Spring|Summer|Winter)"
_TERM_HEADER = re.compile(
    rf"^\s*(\d{{4}})\s+{_SEASON_CAP}(?:\s+Semester)?\s*$",
    re.MULTILINE | re.IGNORECASE,
)
_TERM_HEADER_SEASON_FIRST = re.compile(
    rf"^\s*{_SEASON_CAP}(?:\s+Semester)?\s+(\d{{4}})\s*$",
    re.MULTILINE | re.IGNORECASE,
)
# Inline (same line as other text — common when PDF merges lines)
_TERM_INLINE_YEAR_FIRST = re.compile(
    rf"\b(\d{{4}})\s+({_SEASON})\b(?:\s+Semester)?",
    re.IGNORECASE,
)
_TERM_INLINE_SEASON_FIRST = re.compile(
    rf"\b({_SEASON})\s+(?:Semester\s+)?(\d{{4}})\b",
    re.IGNORECASE,
)
# Banner-style compact codes: SP26, FA25, etc.
_TERM_COMPACT = re.compile(r"\b(SP|FA|SU|WI)(\d{2})\b", re.IGNORECASE)
_COMPACT_SEASON = {"SP": "Spring", "FA": "Fall", "SU": "Summer", "WI": "Winter"}
# Multiple Banner variants; last institutional term block is used downstream.
_TERM_GPA_PATTERNS = (
    re.compile(r"(?:Term|Session)\s*GPA\s*[:.]?\s*(\d+\.\d{1,4})", re.IGNORECASE),
    re.compile(r"Term\s*\n\s*GPA\s*[:.]?\s*(\d+\.\d{1,4})", re.IGNORECASE),
    re.compile(r"(?:Previous|Prior)\s+Term\s*GPA\s*[:.]?\s*(\d+\.\d{1,4})", re.IGNORECASE),
    re.compile(r"TGPA\s*[:.]?\s*(\d+\.\d{1,4})", re.IGNORECASE),
    re.compile(r"Semester\s*GPA\s*[:.]?\s*(\d+\.\d{1,4})", re.IGNORECASE),
    # "GPA" column near term subtotals (label may be far in table extracts)
    re.compile(r"Term\s+[^\d]{0,40}GPA\s*[:.]?\s*(\d+\.\d{1,4})", re.IGNORECASE),
    re.compile(
        r"(?:Inst(?:itutional)?|Inst\.?)\s*Term\s+GPA\s*[:.]?\s*(\d+\.\d{1,4})",
        re.IGNORECASE,
    ),
)
# Term Totals: Attempted Earned GPA Points — third number is often term GPA (Banner-style).
_TERM_TOTALS_GPA = re.compile(
    r"Term\s+Totals?\s*:?\s*(\d+\.\d{2,4})\s+(\d+\.\d{2,4})\s+(\d+\.\d{2,4})\b",
    re.IGNORECASE,
)
# PDFs sometimes break "Term" and "Totals" across lines.
_TERM_TOTALS_GPA_MULTILINE = re.compile(
    r"Term\s*[\n\r]+\s*Totals?\s*:?\s*(\d+\.\d{2,4})\s+(\d+\.\d{2,4})\s+(\d+\.\d{2,4})\b",
    re.IGNORECASE,
)
# "Term Totals" on one line, numbers on the next.
_TERM_TOTALS_GPA_SPLIT_NUMS = re.compile(
    r"Term\s+Totals?\s*:?\s*[\n\r]+\s*(\d+\.\d{2,4})\s+(\d+\.\d{2,4})\s+(\d+\.\d{2,4})\b",
    re.IGNORECASE,
)
_GRADE_POINTS: dict[str, float] = {
    "A+": 4.0,
    "A": 4.0,
    "A-": 3.67,
    "B+": 3.33,
    "B": 3.0,
    "B-": 2.67,
    "C+": 2.33,
    "C": 2.0,
    "C-": 1.67,
    "D+": 1.33,
    "D": 1.0,
    "D-": 0.67,
    "F": 0.0,
}
_EXCLUDE_FROM_TERM_GPA = frozenset({"W", "I", "IP"})
_NON_GPA_GRADES = frozenset({"P", "CR", "S", "U", "NC"})
_FINAL_GRADE = re.compile(
    r"^(?:[ABCDF][+-]?|P|CR|NC|S|U|W)$",
    re.IGNORECASE,
)
_CUM_GPA = re.compile(r"Cum(?:ulative)?\s*GPA\s*:?\s*(\d+\.\d+)", re.IGNORECASE)
_FLOAT3 = re.compile(r"\b(\d+\.\d{3})\b")
_TRANSFER_TOTALS = re.compile(
    r"Transfer\s+Totals:\s*Attempted\s*(\d+\.\d{3})\s*Earned\s*(\d+\.\d{3})\s*Points\s*(\d+\.\d{3})",
    re.IGNORECASE,
)
_TRANSFER_BLOCK = re.compile(r"Transfer\s+Totals:.*?(?=(Transfer\s+Credit|Beginning\s+of|$))", re.IGNORECASE | re.DOTALL)
_TRANSFER_GPA = re.compile(
    r"(?:Course\s+)?Trans(?:fer)?\s*GPA\s*:?\s*(\d+\.\d+)", re.IGNORECASE
)
# Course row: SUBJ #### title attempted earned grade [quality points]
_COURSE_LINE = re.compile(
    r"^\s*([A-Z]{2,5})\s+(\d{4})\s+(.+?)\s+(\d+\.\d{3})\s+(\d+\.\d{3})\s+"
    r"([A-Z]{1,2}[+-]?|IP|I|F|W|CR|NC|P|S|U)?(?:\s+(\d+\.\d{3}))?\s*$",
    re.IGNORECASE,
)
# Same fields when PDF glues multiple rows / headers on one line (no reliable line breaks).
_COURSE_RECORD = re.compile(
    r"\b([A-Z]{2,5})\s+(\d{4})\b\s+"
    r"(.+?)\s+"
    r"(\d+\.\d{3})\s+(\d+\.\d{3})\s+"
    r"([A-Z]{1,2}[+-]?|IP|I|F|W|CR|NC|P|S|U)?"
    r"(?:\s+(\d+\.\d{3}))?"
    r"(?=\s+[A-Z]{2,5}\s+\d{4}\b|\s*Term\b|[\n\r]|$)",
    re.IGNORECASE | re.DOTALL,
)
_INSTITUTION_START = re.compile(
    r"Beginning\s+of\s+Record|Beginning\s+of\s+the\s+Undergraduate\s+Transcript",
    re.IGNORECASE,
)


def _extract_pdf_text_from_reader(reader: PdfReader) -> str:
    parts = []
    for page in reader.pages:
        t = ""
        try:
            t = page.extract_text(extraction_mode="layout") or ""
        except Exception:  # noqa: BLE001 — layout mode is optional; plain extract is fallback
            t = ""
        if not (t or "").strip():
            try:
                t = page.extract_text() or ""
            except Exception:  # noqa: BLE001
                t = ""
        parts.append(t or "")
    return "\n".join(parts)


def _extract_pdf_text_from_stream(stream: BinaryIO) -> str:
    return _extract_pdf_text_from_reader(PdfReader(stream))


def _extract_pdf_text(path: Path) -> str:
    with path.open("rb") as f:
        return _extract_pdf_text_from_stream(f)


def sanitize_transcript_dict_for_json(obj):
    """Ensure sqlite + strict JSON encoders never choke on NaN/Inf or odd types."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {str(k): sanitize_transcript_dict_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_transcript_dict_for_json(v) for v in obj]
    if isinstance(obj, (str, int, bool)) or obj is None:
        return obj
    return str(obj)


def transcript_dict_to_json(obj: dict) -> str:
    return json.dumps(sanitize_transcript_dict_for_json(obj), allow_nan=False)


def scrub_invalid_profile_floats(d: dict) -> None:
    """SQLite / JSON dislike NaN; strip from top-level transcript fields."""
    for k, v in list(d.items()):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            d[k] = None


def _clean_course_title(raw: str) -> str:
    s = re.sub(r"\s+", " ", (raw or "").strip())
    return s


def _clean_major_minor_name(raw: str) -> str:
    s = raw.strip()
    for bad in (
        "Active in Program",
        "Undergraduate",
        "Graduate",
        "Status",
    ):
        if s.lower() == bad.lower():
            return ""
    return s


def _institutional_transcript_tail(text: str) -> str:
    """Return text after transfer work; course rows here are usually UTPB-only."""
    m = _INSTITUTION_START.search(text)
    if m:
        return text[m.end() :]
    block_matches = list(_TRANSFER_BLOCK.finditer(text))
    if block_matches:
        return text[block_matches[-1].end() :]
    totals_matches = list(_TRANSFER_TOTALS.finditer(text))
    if totals_matches:
        return text[totals_matches[-1].end() :]
    return text


def _sum_positive_earned(rows: list[dict]) -> float:
    return sum(r["earned"] for r in rows if r.get("earned", 0) > 0)


def _level_split_from_rows(rows: list[dict]) -> tuple[float, float]:
    lower = 0.0
    upper = 0.0
    for row in rows:
        if row["earned"] <= 0:
            continue
        lvl = row["course_number"][0]
        if lvl in ("1", "2"):
            lower += row["earned"]
        elif lvl in ("3", "4"):
            upper += row["earned"]
    return lower, upper


def _term_label_from_line(line: str) -> str | None:
    s = line.strip()
    m = _TERM_HEADER.match(s)
    if m:
        return f"{m.group(1)} {m.group(2).title()}"
    m = _TERM_HEADER_SEASON_FIRST.match(s)
    if m:
        season = m.group(1).title()
        return f"{m.group(2)} {season}"
    return None


def _all_term_spans(inst_tail: str) -> list[tuple[int, str]]:
    """Term start positions in document order (line-start and inline)."""
    spans: list[tuple[int, str]] = []
    for m in _TERM_HEADER.finditer(inst_tail):
        spans.append((m.start(), f"{m.group(1)} {m.group(2).title()}"))
    for m in _TERM_HEADER_SEASON_FIRST.finditer(inst_tail):
        season = m.group(1).title()
        spans.append((m.start(), f"{m.group(2)} {season}"))
    for m in _TERM_INLINE_YEAR_FIRST.finditer(inst_tail):
        spans.append((m.start(), f"{m.group(1)} {m.group(2).title()}"))
    for m in _TERM_INLINE_SEASON_FIRST.finditer(inst_tail):
        season = m.group(1).title()
        spans.append((m.start(), f"{m.group(2)} {season}"))
    for m in _TERM_COMPACT.finditer(inst_tail):
        code = m.group(1).upper()
        season = _COMPACT_SEASON.get(code)
        if not season:
            continue
        yy = int(m.group(2))
        year = 2000 + yy if yy < 70 else 1900 + yy
        spans.append((m.start(), f"{year} {season}"))
    spans.sort(key=lambda x: x[0])
    deduped: list[tuple[int, str]] = []
    for st, lbl in spans:
        if deduped and st - deduped[-1][0] < 8 and deduped[-1][1] == lbl:
            continue
        if deduped and 0 <= st - deduped[-1][0] < 20 and lbl == deduped[-1][1]:
            continue
        deduped.append((st, lbl))
    return deduped


def _institutional_term_starts(inst_tail: str) -> list[tuple[int, str]]:
    return _all_term_spans(inst_tail)


def _is_plausible_undergrad_term_gpa(v: float) -> bool:
    """Banner term GPA is never a literal 0.000 on meaningful rows; reject placeholders."""
    return 0.01 < v <= 4.5


def _gpa_candidates_in_block(block: str) -> list[tuple[int, float]]:
    """Collect GPA-like floats. Ignore 0.000 placeholders from in-progress / PDF noise."""
    candidates: list[tuple[int, float]] = []
    for pat in _TERM_GPA_PATTERNS:
        for m in pat.finditer(block):
            try:
                v = float(m.group(1))
                if _is_plausible_undergrad_term_gpa(v):
                    candidates.append((m.end(), v))
            except ValueError:
                continue
    for rx in (_TERM_TOTALS_GPA, _TERM_TOTALS_GPA_MULTILINE, _TERM_TOTALS_GPA_SPLIT_NUMS):
        for m in rx.finditer(block):
            try:
                gpa = float(m.group(3))
                if _is_plausible_undergrad_term_gpa(gpa):
                    candidates.append((m.end(), gpa))
            except (ValueError, IndexError):
                continue
    return candidates


def _gpa_from_term_courses(rows: list[dict]) -> float | None:
    """Term GPA from course rows: quality points / earned hrs, or grade-point table."""
    if not rows:
        return None
    total_pts = 0.0
    total_earn = 0.0
    included_grades: list[str] = []
    for r in rows:
        g = (r.get("grade") or "").strip().upper()
        try:
            ear = float(r.get("earned") or 0)
        except (TypeError, ValueError):
            continue
        if ear <= 0:
            continue
        if g in _EXCLUDE_FROM_TERM_GPA or not g:
            continue
        if g in _NON_GPA_GRADES:
            continue
        qp = r.get("quality_points")
        if qp is not None:
            try:
                total_pts += float(qp)
                total_earn += ear
                included_grades.append(g)
            except (TypeError, ValueError):
                continue
            continue
        gp = _GRADE_POINTS.get(g)
        if gp is None:
            return None
        total_pts += gp * ear
        total_earn += ear
        included_grades.append(g)
    if total_earn <= 0:
        return None
    gpa = total_pts / total_earn
    if _is_plausible_undergrad_term_gpa(gpa):
        return round(gpa, 3)
    if (
        gpa == 0
        and included_grades
        and all(gg == "F" for gg in included_grades)
    ):
        return 0.0
    return None


def _extract_previous_term_gpa(inst_tail: str, courses_w_terms: list[dict]) -> float | None:
    """Regex on each term block (newest→oldest), then compute from course rows for that term."""
    spans = _institutional_term_starts(inst_tail)
    if spans:
        for idx in range(len(spans) - 1, -1, -1):
            start = spans[idx][0]
            end = spans[idx + 1][0] if idx + 1 < len(spans) else len(inst_tail)
            block = inst_tail[start:end]
            label = spans[idx][1]
            candidates = _gpa_candidates_in_block(block)
            if candidates:
                candidates.sort(key=lambda x: x[0])
                return candidates[-1][1]
            rows = [r for r in courses_w_terms if r.get("term") == label]
            gpa = _gpa_from_term_courses(rows)
            if gpa is not None:
                return gpa
    candidates = _gpa_candidates_in_block(inst_tail)
    if candidates:
        candidates.sort(key=lambda x: x[0])
        return candidates[-1][1]
    # No term headers but we have courses tagged with a term label
    seen: list[str] = []
    for r in courses_w_terms:
        t = r.get("term")
        if t and t not in seen:
            seen.append(t)
    for label in reversed(seen):
        rows = [r for r in courses_w_terms if r.get("term") == label]
        gpa = _gpa_from_term_courses(rows)
        if gpa is not None:
            return gpa
    return None


def _parse_course_match(m: re.Match) -> dict | None:
    try:
        attempted = float(m.group(4))
        earned = float(m.group(5))
    except (TypeError, ValueError):
        return None
    title = _clean_course_title(m.group(3) or "")
    row = {
        "subject": m.group(1).upper(),
        "course_number": m.group(2),
        "course_name": title if title else None,
        "attempted": attempted,
        "earned": earned,
        "grade": (m.group(6) or "").strip().upper(),
    }
    try:
        qpt = m.group(7)
        if qpt:
            row["quality_points"] = float(qpt)
    except (IndexError, TypeError, ValueError):
        pass
    return row


def _extract_course_rows(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        m = _COURSE_LINE.match(line.strip())
        if not m:
            continue
        row = _parse_course_match(m)
        if row:
            rows.append(row)
    return rows


def _extract_courses_line_by_line(text: str) -> list[dict]:
    current_term: str | None = None
    rows: list[dict] = []
    for line in text.splitlines():
        stripped = line.strip()
        lbl = _term_label_from_line(stripped)
        if lbl:
            current_term = lbl
            continue
        m = _COURSE_LINE.match(stripped)
        if not m or not current_term:
            continue
        row = _parse_course_match(m)
        if row:
            row["term"] = current_term
            rows.append(row)
    return rows


def _extract_courses_segmented(inst_tail: str) -> list[dict]:
    spans = _all_term_spans(inst_tail)
    if not spans:
        return []
    rows: list[dict] = []
    for i, (start, label) in enumerate(spans):
        end = spans[i + 1][0] if i + 1 < len(spans) else len(inst_tail)
        chunk = inst_tail[start:end]
        n_found = 0
        for m in _COURSE_RECORD.finditer(chunk):
            row = _parse_course_match(m)
            if row:
                row["term"] = label
                rows.append(row)
            n_found += 1
            if n_found >= _MAX_COURSE_RECORD_MATCHES_PER_CHUNK:
                break
    return rows


def _course_row_key(r: dict) -> tuple:
    return (
        r.get("term"),
        r.get("subject"),
        r.get("course_number"),
        r.get("attempted"),
        r.get("earned"),
        r.get("grade"),
    )


def _merge_course_row_fields(existing: dict, incoming: dict) -> None:
    """When the same course row appears from two extractors, keep the richer title."""
    old = (existing.get("course_name") or "").strip()
    new = (incoming.get("course_name") or "").strip()
    if new and (not old or len(new) > len(old)):
        existing["course_name"] = incoming["course_name"]


def _extract_courses_with_terms(text: str) -> list[dict]:
    segmented = _extract_courses_segmented(text)
    line_based = _extract_courses_line_by_line(text)
    if len(segmented) >= len(line_based):
        primary = segmented
        secondary = line_based
    else:
        primary = line_based
        secondary = segmented
    merged: dict[tuple, dict] = {}
    for r in primary + secondary:
        k = _course_row_key(r)
        if k not in merged:
            merged[k] = r
        else:
            _merge_course_row_fields(merged[k], r)
    return list(merged.values())


def _is_likely_enrolled(row: dict) -> bool:
    """In-progress / not final-graded row on the latest term (from transcript snapshot)."""
    g = (row.get("grade") or "").strip().upper()
    try:
        att = float(row.get("attempted") or 0)
        ear = float(row.get("earned") or 0)
    except (TypeError, ValueError):
        return False
    if att <= 0:
        return False
    if g == "IP" or g == "I":
        return True
    if not g:
        return ear <= 0
    if _FINAL_GRADE.match(g):
        return False
    return ear <= 0


def parse_utpb_transcript_pdf(source: str | Path | bytes | bytearray) -> dict:
    """Parse a transcript from a file path or raw PDF bytes (nothing is written to disk)."""
    result = {
        "source": "transcript_pdf",
        "warnings": [],
        "majors_found": [],
        "minors_found": [],
        "major": None,
        "minor": None,
        "cumulative_gpa": None,
        "last_term_gpa": None,
        "credits_attempted": None,
        "credits_earned": None,
        "transfer_attempted_total": None,
        "transfer_earned_total": None,
        "utpb_credits_earned": None,
        "total_credit_hours": None,
        "lower_level_credits_earned": None,
        "upper_level_credits_earned": None,
        "terms": [],
        "transfer_blocks": [],
        "last_term_label": None,
        "enrolled_courses": [],
        "latest_term_courses": [],
        "course_history": [],
    }

    try:
        if isinstance(source, (str, Path)):
            text = _extract_pdf_text(Path(source))
        else:
            text = _extract_pdf_text_from_stream(io.BytesIO(bytes(source)))
    except Exception as exc:  # noqa: BLE001
        result["warnings"].append(f"Could not read PDF: {exc}")
        return result

    if not text.strip():
        result["warnings"].append("No text extracted from PDF (may be image-only).")
        return result

    try:
        _parse_transcript_body(text, result)
    except Exception as exc:  # noqa: BLE001
        result["warnings"].append(
            f"Transcript parsing stopped early (partial data saved): {exc}"
        )
    scrub_invalid_profile_floats(result)
    return result


def _parse_transcript_body(text: str, result: dict) -> None:
    # --- Majors / minors (Academic Program History) ---
    for m in _MAJOR.finditer(text):
        name = _clean_major_minor_name(m.group(1))
        if name:
            result["majors_found"].append(name)
    for m in _MINOR.finditer(text):
        name = _clean_major_minor_name(m.group(1))
        if name:
            result["minors_found"].append(name)
    if result["majors_found"]:
        result["major"] = result["majors_found"][-1]
    if result["minors_found"]:
        result["minor"] = result["minors_found"][-1]

    # --- Term labels (chronological blocks) ---
    for m in _TERM_HEADER.finditer(text):
        result["terms"].append(f"{m.group(1)} {m.group(2).title()}")
    for m in _TERM_HEADER_SEASON_FIRST.finditer(text):
        result["terms"].append(f"{m.group(2)} {m.group(1).title()}")

    if result["terms"]:
        _seen = set()
        _uniq: list[str] = []
        for t in result["terms"]:
            if t not in _seen:
                _seen.add(t)
                _uniq.append(t)
        result["terms"] = _uniq

    # --- GPA: use last cumulative in document; last term GPA excluding transfer lines ---
    cum_matches = list(_CUM_GPA.finditer(text))
    if cum_matches:
        try:
            result["cumulative_gpa"] = float(cum_matches[-1].group(1))
        except ValueError:
            pass

    # --- Cumulative credit totals: numbers after last "Cum GPA" ---
    if cum_matches:
        anchor = cum_matches[-1].start()
        snippet = text[anchor : anchor + 600]
        nums = [float(x) for x in _FLOAT3.findall(snippet)]
        if len(nums) >= 3:
            # Typical Banner row: GPA, Attempted, Earned, GPA Units, Points
            result["credits_attempted"] = nums[1]
            result["credits_earned"] = nums[2]
        elif len(nums) == 2:
            result["credits_attempted"] = nums[1]

    # --- Transfer summary (best-effort) ---
    gpa_vals = []
    for g in _TRANSFER_GPA.finditer(text):
        try:
            gpa_vals.append(float(g.group(1)))
        except ValueError:
            continue

    total_attempted = 0.0
    total_earned = 0.0

    totals_matches = list(_TRANSFER_TOTALS.finditer(text))
    if not totals_matches:
        # Fallback for PDFs where labels/values are split across lines.
        block_matches = list(_TRANSFER_BLOCK.finditer(text))
        for bm in block_matches:
            block_text = bm.group(0)
            nums = re.findall(r"\d+\.\d{3}", block_text)
            # Typical block has attempted, earned, points; sometimes may include extra values.
            # Prefer first two values as attempted/earned in transfer summary area.
            if len(nums) >= 2:
                fake_attempted = nums[0]
                fake_earned = nums[1]
                # Build lightweight match-like tuple behavior.
                class _M:
                    def __init__(self, a, e):
                        self._a = a
                        self._e = e

                    def group(self, idx):
                        if idx == 1:
                            return self._a
                        if idx == 2:
                            return self._e
                        return "0.000"

                totals_matches.append(_M(fake_attempted, fake_earned))

    for idx, m in enumerate(totals_matches):
        block = {"note": "transfer_section", "gpa": None, "attempted": None, "earned": None}
        if idx < len(gpa_vals):
            block["gpa"] = gpa_vals[idx]
        try:
            block["attempted"] = float(m.group(1))
            block["earned"] = float(m.group(2))
            total_attempted += block["attempted"]
            total_earned += block["earned"]
        except ValueError:
            pass
        result["transfer_blocks"].append(block)

    if result["transfer_blocks"]:
        result["transfer_attempted_total"] = total_attempted
        result["transfer_earned_total"] = total_earned

    # --- Level splits and UTPB totals from institutional course lines only ---
    inst_tail = _institutional_transcript_tail(text)

    courses_w_terms = _extract_courses_with_terms(inst_tail)
    inst_term_spans = _institutional_term_starts(inst_tail)
    lt_gpa = _extract_previous_term_gpa(inst_tail, courses_w_terms)
    if lt_gpa is not None:
        result["last_term_gpa"] = lt_gpa

    term_rank: dict[str, int] = {lbl: i for i, (_, lbl) in enumerate(inst_term_spans)}
    if not term_rank and courses_w_terms:
        _order: list[str] = []
        for r in courses_w_terms:
            t = r.get("term")
            if t and t not in _order:
                _order.append(t)
        term_rank = {t: i for i, t in enumerate(_order)}

    for row in courses_w_terms:
        lbl = row.get("term")
        result["course_history"].append(
            {
                "subject": row["subject"],
                "course_number": row["course_number"],
                "course": f"{row['subject']} {row['course_number']}",
                "course_name": row.get("course_name") or None,
                "attempted": row["attempted"],
                "earned": row["earned"],
                "grade": row.get("grade") or None,
                "term": lbl,
            }
        )
    result["course_history"].sort(
        key=lambda e: (
            term_rank.get(e.get("term") or "", 999),
            e.get("subject") or "",
            e.get("course_number") or "",
        )
    )
    if inst_term_spans:
        result["last_term_label"] = inst_term_spans[-1][1]
        last_lbl = result["last_term_label"]
        for row in courses_w_terms:
            if row.get("term") != last_lbl:
                continue
            entry = {
                "subject": row["subject"],
                "course_number": row["course_number"],
                "course": f"{row['subject']} {row['course_number']}",
                "course_name": row.get("course_name") or None,
                "attempted": row["attempted"],
                "earned": row["earned"],
                "grade": row["grade"] or None,
                "term": row["term"],
            }
            result["latest_term_courses"].append(entry)
            if _is_likely_enrolled(row):
                result["enrolled_courses"].append(entry)

    course_rows_inst = _extract_course_rows(inst_tail)
    utpb_from_rows = _sum_positive_earned(course_rows_inst)
    lower, upper = _level_split_from_rows(course_rows_inst)

    if lower > 0 or upper > 0:
        result["lower_level_credits_earned"] = lower
        result["upper_level_credits_earned"] = upper

    transfer_earned = float(result["transfer_earned_total"] or 0.0)
    cum_earned = result["credits_earned"]

    # Prefer summing institutional course rows when we have them.
    if utpb_from_rows > 0:
        result["utpb_credits_earned"] = utpb_from_rows
        if cum_earned is not None:
            # Banner "earned" is usually overall total; prefer it when consistent.
            if cum_earned + 0.5 >= utpb_from_rows + transfer_earned:
                result["total_credit_hours"] = cum_earned
            else:
                result["total_credit_hours"] = utpb_from_rows + transfer_earned
        else:
            result["total_credit_hours"] = utpb_from_rows + transfer_earned
    elif cum_earned is not None:
        # Cumulative earned may be overall (incl. transfer) or institutional-only.
        if transfer_earned > 0 and cum_earned + 1e-3 < transfer_earned:
            # Can't be "overall earned" if smaller than transfer — treat as UTPB-only.
            result["utpb_credits_earned"] = max(cum_earned, 0.0)
            result["total_credit_hours"] = cum_earned + transfer_earned
        elif transfer_earned > 0:
            result["utpb_credits_earned"] = max(cum_earned - transfer_earned, 0.0)
            result["total_credit_hours"] = cum_earned
        else:
            result["utpb_credits_earned"] = cum_earned
            result["total_credit_hours"] = cum_earned
    else:
        # Last resort: all course lines (may mix transfer + UTPB)
        course_rows_all = _extract_course_rows(text)
        fallback = _sum_positive_earned(course_rows_all)
        if fallback > 0:
            result["utpb_credits_earned"] = max(fallback - transfer_earned, 0.0)
            result["total_credit_hours"] = (
                result["utpb_credits_earned"] + transfer_earned
            )

    if result["cumulative_gpa"] is None:
        result["warnings"].append(
            "Could not find cumulative GPA; PDF text layout may differ."
        )
    if result["major"] is None:
        result["warnings"].append(
            "Could not detect major from program history; check PDF text."
        )
