import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "courses.db"


def get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
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


_USER_PROFILES_SLIM_COLUMNS = (
    "user_id",
    "major",
    "minor",
    "transcript_original_name",
    "transcript_parsed_json",
    "updated_at",
)


def _user_profiles_current_columns(conn):
    return [r[1] for r in conn.execute("PRAGMA table_info(user_profiles)").fetchall()]


def _migrate_user_profiles_slim():
    """
    Rebuild user_profiles to the slim schema. GPA, credits, and full course
    data live in transcript_parsed_json only. Legacy row columns are merged
    into the JSON when the parser never stored them.
    """
    conn = get_connection()
    try:
        has_table = conn.execute(
            "SELECT COUNT(1) FROM sqlite_master WHERE type='table' AND name='user_profiles'"
        ).fetchone()[0]
        if not has_table:
            return
        cols = set(_user_profiles_current_columns(conn))
        want = set(_USER_PROFILES_SLIM_COLUMNS)
        if cols == want:
            return

        cur = conn.execute("SELECT * FROM user_profiles")
        col_names = [d[0] for d in cur.description]
        old_rows = cur.fetchall()
        conn.execute("BEGIN")
        conn.execute(
            """
            CREATE TABLE user_profiles__new (
                user_id INTEGER PRIMARY KEY,
                major TEXT,
                minor TEXT,
                transcript_original_name TEXT,
                transcript_parsed_json TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        for row in old_rows:
            d = {col_names[i]: row[i] for i in range(len(col_names))}
            parsed = d.get("transcript_parsed_json")
            pdict = None
            if isinstance(parsed, str) and parsed.strip():
                try:
                    pdict = json.loads(parsed)
                except json.JSONDecodeError:
                    pdict = {}
            elif parsed is not None and not isinstance(parsed, str):
                pdict = parsed
            if pdict is None:
                pdict = {}
            if not isinstance(pdict, dict):
                pdict = {}
            legacy_keys = (
                "cumulative_gpa",
                "last_term_gpa",
                "credits_attempted",
                "credits_earned",
            )
            for key in legacy_keys:
                if pdict.get(key) is None and d.get(key) is not None:
                    pdict[key] = d[key]
            new_json = json.dumps(pdict, allow_nan=False) if pdict else None
            conn.execute(
                """
                INSERT INTO user_profiles__new (
                    user_id, major, minor, transcript_original_name, transcript_parsed_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    d.get("user_id"),
                    d.get("major"),
                    d.get("minor"),
                    d.get("transcript_original_name"),
                    new_json,
                    d.get("updated_at")
                    or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
        conn.execute("DROP TABLE user_profiles")
        conn.execute("ALTER TABLE user_profiles__new RENAME TO user_profiles")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_profile_tables():
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id INTEGER PRIMARY KEY,
            major TEXT,
            minor TEXT,
            transcript_original_name TEXT,
            transcript_parsed_json TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    conn.commit()
    conn.close()
    _migrate_user_profiles_slim()


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
    raw = data.get("transcript_parsed_json")
    if raw:
        try:
            data["transcript_parsed_json"] = json.loads(raw)
        except json.JSONDecodeError:
            data["transcript_parsed_json"] = None
    else:
        data["transcript_parsed_json"] = None
    _enrich_transcript_parsed(data.get("transcript_parsed_json"))
    _augment_from_transcript_json(data)
    return data


def _enrich_transcript_parsed(parsed):
    """
    Transcripts stored before 'course_history' existed only have latest_term_courses
    and enrolled_courses. Reconstruct a best-effort course list for the UI
    (full multi-term history still requires a fresh PDF import).
    """
    if not isinstance(parsed, dict):
        return
    ch = parsed.get("course_history")
    if isinstance(ch, list) and len(ch) > 0:
        return
    latest = parsed.get("latest_term_courses") or []
    if not isinstance(latest, list) or not latest:
        return
    parsed["course_history"] = [dict(r) for r in latest if isinstance(r, dict)]
    parsed["course_history_is_partial"] = True


def _augment_from_transcript_json(data):
    """Populate top-level *_gpa and credits* for the API (single source: parsed JSON)."""
    tp = data.get("transcript_parsed_json")
    if not isinstance(tp, dict):
        for key in (
            "cumulative_gpa",
            "last_term_gpa",
            "credits_attempted",
            "credits_earned",
        ):
            data[key] = None
        return
    data["cumulative_gpa"] = tp.get("cumulative_gpa")
    data["last_term_gpa"] = tp.get("last_term_gpa")
    data["credits_attempted"] = tp.get("credits_attempted")
    data["credits_earned"] = tp.get("credits_earned")


_PROFILE_UPDATE_FIELDS = frozenset(
    {
        "major",
        "minor",
        "transcript_original_name",
        "transcript_parsed_json",
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
