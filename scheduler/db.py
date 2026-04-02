import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "courses.db"


def get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def get_terms():
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT term_label FROM sections ORDER BY term_label"
    ).fetchall()
    conn.close()
    return [r["term_label"] for r in rows]


def get_subjects(term_label=None):
    conn = get_connection()
    if term_label:
        rows = conn.execute(
            "SELECT DISTINCT subject_code FROM sections WHERE term_label = ? ORDER BY subject_code",
            (term_label,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT DISTINCT subject_code FROM sections ORDER BY subject_code"
        ).fetchall()
    conn.close()
    return [r["subject_code"] for r in rows]


def get_modes(term_label=None):
    conn = get_connection()
    if term_label:
        rows = conn.execute(
            "SELECT DISTINCT mode FROM sections WHERE term_label = ? AND mode != '' ORDER BY mode",
            (term_label,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT DISTINCT mode FROM sections WHERE mode != '' ORDER BY mode"
        ).fetchall()
    conn.close()
    return [r["mode"] for r in rows]


def get_sections(term_label, subject_code=None, mode=None, level=None, search=None):
    conn = get_connection()
    query = """
        SELECT s.id, s.term_label, s.class_nbr, s.subject_code, s.course_number,
               s.course_code, s.section_code, s.credits, s.days, s.session,
               s.start_time, s.end_time, s.location, s.mode,
               c.course_name, c.prerequisites, c.term_infered,
               cal.session_start_date, cal.session_end_date
        FROM sections s
        LEFT JOIN courses c ON c.course_code = s.course_code
        LEFT JOIN session_calendar cal
          ON cal.term_label = s.term_label AND cal.session = s.session
        WHERE s.term_label = ?
    """
    params = [term_label]

    if subject_code:
        query += " AND s.subject_code = ?"
        params.append(subject_code)
    if mode:
        query += " AND s.mode = ?"
        params.append(mode)
    if level:
        query += " AND s.course_number LIKE ?"
        params.append(f"{level}%")
    if search:
        query += " AND (s.course_code LIKE ? OR COALESCE(c.course_name, '') LIKE ?)"
        params.append(f"%{search}%")
        params.append(f"%{search}%")

    query += " ORDER BY s.subject_code, s.course_number, s.section_code"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_sections_by_ids(section_ids):
    if not section_ids:
        return []
    conn = get_connection()
    placeholders = ",".join("?" for _ in section_ids)
    rows = conn.execute(
        f"""
        SELECT s.id, s.term_label, s.class_nbr, s.subject_code, s.course_number,
               s.course_code, s.section_code, s.credits, s.days, s.session,
               s.start_time, s.end_time, s.location, s.mode,
               c.course_name, c.prerequisites, c.term_infered,
               cal.session_start_date, cal.session_end_date
        FROM sections s
        LEFT JOIN courses c ON c.course_code = s.course_code
        LEFT JOIN session_calendar cal
          ON cal.term_label = s.term_label AND cal.session = s.session
        WHERE s.id IN ({placeholders})
        ORDER BY s.subject_code, s.course_number, s.section_code
        """,
        list(section_ids),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_courses(subject_code=None, search=None):
    conn = get_connection()
    query = """
        SELECT id, subject_code, course_number, course_code, course_name,
               course_url, prerequisites, term_infered
        FROM courses WHERE 1=1
    """
    params = []
    if subject_code:
        query += " AND subject_code = ?"
        params.append(subject_code)
    if search:
        query += " AND (course_code LIKE ? OR course_name LIKE ?)"
        params.append(f"%{search}%")
        params.append(f"%{search}%")
    query += " ORDER BY subject_code, course_number"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_subjects():
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT subject_code FROM courses ORDER BY subject_code"
    ).fetchall()
    conn.close()
    return [r["subject_code"] for r in rows]


def get_session_dates(term_label):
    conn = get_connection()
    rows = conn.execute(
        "SELECT session, session_start_date, session_end_date FROM session_calendar WHERE term_label = ? ORDER BY session",
        (term_label,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
