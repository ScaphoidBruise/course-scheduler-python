"""
LLM-backed schedule suggestions using the Anthropic Messages API (Claude).
"""

from __future__ import annotations

import json
import re
from typing import Any

from dotenv import load_dotenv

from .config import PROJECT_ROOT, anthropic_api_key, anthropic_base_url, anthropic_model
from .db import connect, rows_as_dicts
from .schedule_validate import SectionLite, find_conflicts


def _normalize_time_value(v):
    import datetime

    if v is None:
        return None
    if isinstance(v, datetime.timedelta):
        secs = int(v.total_seconds()) % 86400
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        v = datetime.time(h, m, s)
    if isinstance(v, datetime.time):
        return v.strftime("%H:%M:%S")
    if isinstance(v, str):
        return v
    return str(v)


def load_schedule_context(semester: str | None) -> dict[str, Any]:
    conn, backend = connect()
    prereq_agg = (
        "GROUP_CONCAT(p.prereq_code ORDER BY p.prereq_code SEPARATOR ', ')"
        if backend == "mysql"
        else "GROUP_CONCAT(p.prereq_code, ', ' ORDER BY p.prereq_code)"
    )
    try:
        cur = (
            conn.cursor(dictionary=True)
            if backend == "mysql"
            else conn.cursor()
        )
        cur.execute(
            f"""
            SELECT c.course_code, c.title, c.credits, c.description,
                   {prereq_agg} AS prerequisites
            FROM courses c
            LEFT JOIN prerequisites p ON p.course_code = c.course_code
            GROUP BY c.course_code, c.title, c.credits, c.description
            ORDER BY c.course_code
            """
        )
        courses = cur.fetchall() if backend == "mysql" else rows_as_dicts(cur, backend)
        for r in courses:
            raw = r.get("prerequisites")
            r["prerequisites"] = raw.split(", ") if raw else []

        q = """
            SELECT section_id, course_code, semester, section_code, instructor,
                   days, start_time, end_time, room_number, delivery_mode,
                   enrolled, seat_limit
            FROM sections
            """
        args: tuple = ()
        if semester:
            q += " WHERE semester = %s" if backend == "mysql" else " WHERE semester = ?"
            args = (semester,)
        q += " ORDER BY course_code, section_code"
        cur.execute(q, args)
        sections = cur.fetchall() if backend == "mysql" else rows_as_dicts(cur, backend)
        for s in sections:
            s["start_time"] = _normalize_time_value(s.get("start_time"))
            s["end_time"] = _normalize_time_value(s.get("end_time"))

        return {"courses": courses, "sections": sections}
    finally:
        conn.close()


def build_llm_context_blob(ctx: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("COURSES (course_code, title, credits, prerequisites, description snippet):")
    for c in ctx["courses"]:
        pq = ", ".join(c["prerequisites"]) if c["prerequisites"] else "none"
        desc = (c.get("description") or "").strip()
        snip = (desc[:160] + "…") if len(desc) > 160 else desc
        lines.append(
            f"- {c['course_code']}: {c['title']} | {c['credits']} cr | prereqs: {pq}"
            + (f" | {snip}" if snip else "")
        )
    lines.append("")
    lines.append(
        "SECTIONS (section_id, course_code, semester, section_code, instructor, "
        "days, start_time, end_time, room, mode, enrolled, seat_limit):"
    )
    for s in ctx["sections"]:
        en = s.get("enrolled")
        cap = s.get("seat_limit")
        enroll_s = (
            f"{en}/{cap}" if en is not None and cap is not None else "—"
        )
        lines.append(
            f"- id={s['section_id']} | {s['course_code']} | {s.get('semester') or ''} | "
            f"sec {s.get('section_code') or ''} | {s.get('instructor') or ''} | "
            f"days={s.get('days') or '—'} | {s.get('start_time') or '—'}–{s.get('end_time') or '—'} | "
            f"{s.get('room_number') or '—'} | {s.get('delivery_mode') or '—'} | "
            f"enrolled/limit={enroll_s}"
        )
    return "\n".join(lines)


SYSTEM_PROMPT = """You are an academic scheduling assistant for UTPB COSC (Computer Science) courses.

You receive a list of courses with prerequisites (only prerequisites that appear in this same catalog are listed; others may exist in real life).

You also receive SECTION rows. Each row has a numeric section_id you MUST use when recommending specific sections.

Rules:
1. Suggest section_id values that appear exactly in the data. Never invent ids.
2. Include every section_id you want to recommend (for example alternate meeting times). For a conflict-free full schedule, prefer one section per course; extra ids can be alternatives—say so in the reply.
3. Avoid time conflicts: two sections that meet on the same weekday with overlapping clock times cannot both be chosen. Rows with no meeting days or no start/end times are usually online/async and generally do not conflict with timed classes.
4. If the user asks for impossible combinations, explain briefly and suggest the closest valid alternative.
5. Mention prerequisite gaps as warnings (e.g. if they want a course whose prereq they did not list as already taken).
6. Sections may span multiple semesters (Spring / Summer / Fall). Prefer sections in the semester the student asked for; note enrolled/seat_limit when advising on full classes.
7. List every course you recommend. Use suggested_section_ids for specific sections. If you recommend a course but want the student to pick among sections, also add its catalog code to suggested_course_codes (exact codes from the data, e.g. "COSC 2315").

Respond with a single JSON object only, no markdown code fences or other wrapping:
{
  "reply": string (friendly, concise advice for the student),
  "suggested_section_ids": array of integers (can be empty),
  "suggested_course_codes": array of strings (optional; courses to highlight when not every pick has a section_id),
  "warnings": array of short strings (optional)
}
"""


def _parse_json_from_model_text(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```\s*$", "", text)
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            return json.loads(m.group(0))
        raise


def _reload_project_env() -> None:
    load_dotenv(PROJECT_ROOT / ".env", override=True)


def _anthropic_model_candidates() -> list[str]:
    _reload_project_env()
    primary = anthropic_model()
    fallbacks = [
        "claude-haiku-4-5-20251001",
        "claude-sonnet-4-20250514",
    ]
    out: list[str] = []
    for m in [primary, *fallbacks]:
        if m and m not in out:
            out.append(m)
    return out


def call_schedule_llm(user_message: str, data_blob: str) -> tuple[dict[str, Any], str]:
    _reload_project_env()
    api_key = anthropic_api_key()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    try:
        import anthropic
    except ImportError as e:
        raise RuntimeError("Install the anthropic package: pip install anthropic") from e

    client_kwargs: dict[str, Any] = {"api_key": api_key}
    base = anthropic_base_url()
    if base:
        client_kwargs["base_url"] = base
    client = anthropic.Anthropic(**client_kwargs)

    user_content = f"Schedule data:\n\n{data_blob}\n\nStudent request:\n{user_message}"

    candidates = _anthropic_model_candidates()
    last_err: Exception | None = None
    used_model = ""
    for model in candidates:
        try:
            msg = client.messages.create(
                model=model,
                max_tokens=1200,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
                temperature=0.4,
            )
            used_model = model
            break
        except Exception as e:
            err_s = str(e).lower()
            if "404" in str(e) and "model" in err_s:
                last_err = e
                continue
            raise
    else:
        raise RuntimeError(
            f"No working Claude model. Tried: {candidates!r}. Last error: {last_err}"
        ) from last_err
    parts: list[str] = []
    for block in msg.content:
        if hasattr(block, "text"):
            parts.append(block.text)
    text = "".join(parts).strip()
    try:
        return _parse_json_from_model_text(text), used_model
    except json.JSONDecodeError as e:
        raise RuntimeError("The model returned invalid JSON.") from e


def _norm_course_code_key(value: str) -> str:
    return " ".join(str(value).strip().split()).lower()


def _section_row_to_api_dict(sid: int, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "section_id": sid,
        "course_code": row["course_code"],
        "section_code": row.get("section_code"),
        "semester": row.get("semester"),
        "instructor": row.get("instructor"),
        "days": row.get("days"),
        "start_time": row.get("start_time"),
        "end_time": row.get("end_time"),
        "room_number": row.get("room_number"),
        "delivery_mode": row.get("delivery_mode"),
        "enrolled": row.get("enrolled"),
        "seat_limit": row.get("seat_limit"),
    }


def sections_for_suggested_ids(ids: list[int], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """One API row per valid model id (multiple rows per course allowed)."""
    sections_by_id = {int(s["section_id"]): s for s in ctx["sections"]}
    out: list[dict[str, Any]] = []
    seen_sid: set[int] = set()
    for sid in ids:
        try:
            sid_int = int(sid)
        except (TypeError, ValueError):
            continue
        if sid_int in seen_sid:
            continue
        seen_sid.add(sid_int)
        row = sections_by_id.get(sid_int)
        if row is None:
            continue
        out.append(_section_row_to_api_dict(sid_int, row))
    return out


def resolve_extra_course_codes(
    raw_codes: list[str],
    ctx: dict[str, Any],
    codes_from_sections: set[str],
) -> list[str]:
    """Catalog course_code strings for model hints not already covered by section rows."""
    catalog_by_norm = {
        _norm_course_code_key(c["course_code"]): c["course_code"] for c in ctx["courses"]
    }
    resolved: list[str] = []
    seen: set[str] = set()
    for x in raw_codes:
        s = str(x).strip()
        if not s:
            continue
        key = _norm_course_code_key(s)
        canon = catalog_by_norm.get(key)
        if not canon:
            continue
        if _norm_course_code_key(canon) in codes_from_sections:
            continue
        nk = _norm_course_code_key(canon)
        if nk in seen:
            continue
        seen.add(nk)
        resolved.append(canon)
    return resolved


def validate_suggestion(
    suggested_ids: list[int],
    ctx: dict[str, Any],
) -> dict[str, Any]:
    sections_by_id = {int(s["section_id"]): s for s in ctx["sections"]}
    errors: list[str] = []
    seen_courses: set[str] = set()
    resolved: list[dict[str, Any]] = []

    for sid in suggested_ids:
        if sid not in sections_by_id:
            errors.append(f"Section id {sid} is not in the current schedule data.")
            continue
        row = sections_by_id[sid]
        cc = row["course_code"]
        if cc in seen_courses:
            errors.append(f"More than one section chosen for {cc} (ids include {sid}).")
            continue
        seen_courses.add(cc)
        resolved.append(
            {
                "section_id": sid,
                "course_code": cc,
                "section_code": row.get("section_code"),
                "semester": row.get("semester"),
                "instructor": row.get("instructor"),
                "days": row.get("days"),
                "start_time": row.get("start_time"),
                "end_time": row.get("end_time"),
                "room_number": row.get("room_number"),
                "delivery_mode": row.get("delivery_mode"),
                "enrolled": row.get("enrolled"),
                "seat_limit": row.get("seat_limit"),
            }
        )

    lites = [
        SectionLite(
            section_id=r["section_id"],
            course_code=r["course_code"],
            section_code=r.get("section_code"),
            days=r.get("days"),
            start_time=r.get("start_time"),
            end_time=r.get("end_time"),
            delivery_mode=r.get("delivery_mode"),
        )
        for r in resolved
    ]
    conflicts = find_conflicts(lites)
    conflict_msgs: list[str] = []
    for a, b in conflicts:
        conflict_msgs.append(
            f"Time conflict between {a.course_code} sec {a.section_code} and "
            f"{b.course_code} sec {b.section_code}."
        )

    return {
        "sections": resolved,
        "errors": errors,
        "conflicts": conflict_msgs,
    }


def run_schedule_assistant(user_message: str, semester: str | None) -> dict[str, Any]:
    sem = (semester or "").strip() or None
    ctx = load_schedule_context(sem)
    if not ctx["sections"]:
        raise RuntimeError(
            "No sections in the database. Run scripts/sync_catalog_to_mysql.py with "
            "SCHEDULE_TERM_MAP set, or pass ?semester= in the API body to filter."
        )

    blob = build_llm_context_blob(ctx)
    parsed, model_used = call_schedule_llm(user_message, blob)
    raw_ids = parsed.get("suggested_section_ids")
    if not isinstance(raw_ids, list):
        raw_ids = []
    ids_int: list[int] = []
    for x in raw_ids:
        try:
            ids_int.append(int(x))
        except (TypeError, ValueError):
            pass

    display_sections = sections_for_suggested_ids(ids_int, ctx)
    validation = validate_suggestion(ids_int, ctx)
    reply = parsed.get("reply")
    if not isinstance(reply, str):
        reply = str(reply or "")
    warnings = parsed.get("warnings")
    if not isinstance(warnings, list):
        warnings = []

    raw_cc = parsed.get("suggested_course_codes")
    if not isinstance(raw_cc, list):
        raw_cc = []
    codes_from_sections = {
        _norm_course_code_key(r["course_code"]) for r in display_sections
    }
    suggested_course_codes = resolve_extra_course_codes(
        [str(x) for x in raw_cc],
        ctx,
        codes_from_sections,
    )

    return {
        "reply": reply,
        "warnings": [str(w) for w in warnings],
        "suggested_section_ids": ids_int,
        "sections": display_sections,
        "suggested_course_codes": suggested_course_codes,
        "errors": validation["errors"],
        "conflicts": validation["conflicts"],
        "semester": sem or "all terms",
        "model": model_used,
    }
