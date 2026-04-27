import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "courses.db"


def get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_auth_tables():
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_schedules (
            user_id INTEGER NOT NULL,
            term_label TEXT NOT NULL,
            section_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, term_label, section_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    conn.commit()
    conn.close()


def init_profile_tables():
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id INTEGER PRIMARY KEY,
            major TEXT,
            minor TEXT,
            cumulative_gpa REAL,
            last_term_gpa REAL,
            credits_attempted REAL,
            credits_earned REAL,
            transcript_path TEXT,
            transcript_original_name TEXT,
            degree_plan_path TEXT,
            degree_plan_original_name TEXT,
            transcript_parsed_json TEXT,
            degree_plan_parsed_json TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    conn.commit()
    conn.close()


def ensure_user_profile(user_id):
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)",
        (user_id,),
    )
    conn.commit()
    conn.close()


def get_user_profile(user_id):
    ensure_user_profile(user_id)
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM user_profiles WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    data = dict(row)
    for key in ("transcript_parsed_json", "degree_plan_parsed_json"):
        raw = data.get(key)
        if raw:
            try:
                data[key] = json.loads(raw)
            except json.JSONDecodeError:
                data[key] = None
        else:
            data[key] = None
    return data


_PROFILE_UPDATE_FIELDS = frozenset(
    {
        "major",
        "minor",
        "cumulative_gpa",
        "last_term_gpa",
        "credits_attempted",
        "credits_earned",
        "transcript_path",
        "transcript_original_name",
        "degree_plan_path",
        "degree_plan_original_name",
        "transcript_parsed_json",
        "degree_plan_parsed_json",
    }
)


def update_user_profile(user_id, **fields):
    ensure_user_profile(user_id)
    cols = []
    vals = []
    for key, value in fields.items():
        if key not in _PROFILE_UPDATE_FIELDS:
            continue
        cols.append(f"{key} = ?")
        vals.append(value)
    if not cols:
        return
    vals.append(user_id)
    conn = get_connection()
    conn.execute(
        f"""
        UPDATE user_profiles
        SET {", ".join(cols)}, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
        """,
        vals,
    )
    conn.commit()
    conn.close()


def create_user(username, password_hash):
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def get_user_by_username(username):
    conn = get_connection()
    row = conn.execute(
        "SELECT id, username, password_hash, created_at FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT id, username, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_saved_schedule_ids(user_id, term_label):
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT section_id
        FROM user_schedules
        WHERE user_id = ? AND term_label = ?
        ORDER BY section_id
        """,
        (user_id, term_label),
    ).fetchall()
    conn.close()
    return [r["section_id"] for r in rows]


def save_schedule_ids(user_id, term_label, section_ids):
    conn = get_connection()
    conn.execute(
        "DELETE FROM user_schedules WHERE user_id = ? AND term_label = ?",
        (user_id, term_label),
    )
    if section_ids:
        conn.executemany(
            """
            INSERT OR IGNORE INTO user_schedules (user_id, term_label, section_id)
            VALUES (?, ?, ?)
            """,
            [(user_id, term_label, sid) for sid in section_ids],
        )
    conn.commit()
    conn.close()


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
