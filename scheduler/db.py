import json
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "courses.db"

PASSING_COMPLETION_GRADES = frozenset(
    {"A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "P", "CR", "S"}
)
GPA_POINTS = {
    "A": 4.0,
    "A-": 3.7,
    "B+": 3.3,
    "B": 3.0,
    "B-": 2.7,
    "C+": 2.3,
    "C": 2.0,
    "C-": 1.7,
    "D+": 1.3,
    "D": 1.0,
    "D-": 0.7,
    "F": 0.0,
}
NON_GPA_GRADES = frozenset({"P", "CR", "S", "W", "IP", "I", ""})
COURSE_TOKEN_RE = re.compile(r"\b([A-Z]{2,5})\s*([0-9]{4})\b")


def normalize_course_code(value: object) -> str:
    text = " ".join(str(value or "").upper().replace("-", " ").split())
    m = COURSE_TOKEN_RE.search(text)
    if not m:
        compact = re.sub(r"[^A-Z0-9]", "", text)
        m = re.match(r"^([A-Z]{2,5})([0-9]{4})$", compact)
    if not m:
        return text
    return f"{m.group(1)} {m.group(2)}"


def compact_course_code(value: object) -> str:
    return normalize_course_code(value).replace(" ", "")


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
        CREATE TABLE IF NOT EXISTS schedule_scenarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            term_label TEXT NOT NULL,
            name TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 0,
            share_token TEXT UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_schedules (
            user_id INTEGER NOT NULL,
            term_label TEXT NOT NULL,
            scenario_id INTEGER,
            section_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, term_label, scenario_id, section_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (scenario_id) REFERENCES schedule_scenarios(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            PRIMARY KEY (user_id, key),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    conn.commit()
    _migrate_user_schedules_to_scenarios(conn)
    conn.close()


def init_wishlist_tables():
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS course_wishlist (
            user_id INTEGER NOT NULL,
            course_id INTEGER NOT NULL,
            priority INTEGER DEFAULT 0,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, course_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
        )
        """
    )
    conn.commit()
    conn.close()


def _user_schedule_columns(conn):
    return [r[1] for r in conn.execute("PRAGMA table_info(user_schedules)").fetchall()]


def _user_schedule_pk_columns(conn):
    rows = conn.execute("PRAGMA table_info(user_schedules)").fetchall()
    return [r[1] for r in sorted((r for r in rows if r[5]), key=lambda r: r[5])]


def _create_user_schedules_new(conn):
    conn.execute(
        """
        CREATE TABLE user_schedules__new (
            user_id INTEGER NOT NULL,
            term_label TEXT NOT NULL,
            scenario_id INTEGER,
            section_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, term_label, scenario_id, section_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (scenario_id) REFERENCES schedule_scenarios(id) ON DELETE CASCADE
        )
        """
    )


def _ensure_legacy_scenario_conn(conn, user_id, term_label):
    row = conn.execute(
        """
        SELECT id
        FROM schedule_scenarios
        WHERE user_id = ? AND term_label = ? AND name = ?
        ORDER BY is_active DESC, id
        LIMIT 1
        """,
        (user_id, term_label, "My schedule"),
    ).fetchone()
    if row:
        scenario_id = row["id"]
    else:
        cur = conn.execute(
            """
            INSERT INTO schedule_scenarios (user_id, term_label, name, is_active)
            VALUES (?, ?, ?, 1)
            """,
            (user_id, term_label, "My schedule"),
        )
        scenario_id = cur.lastrowid
    conn.execute(
        """
        UPDATE schedule_scenarios
        SET is_active = CASE WHEN id = ? THEN 1 ELSE 0 END
        WHERE user_id = ? AND term_label = ?
        """,
        (scenario_id, user_id, term_label),
    )
    return scenario_id


def _migrate_user_schedules_to_scenarios(conn):
    cols = _user_schedule_columns(conn)
    pk_cols = _user_schedule_pk_columns(conn)
    needs_rebuild = "scenario_id" not in cols or pk_cols != [
        "user_id",
        "term_label",
        "scenario_id",
        "section_id",
    ]
    if not needs_rebuild:
        rows = conn.execute(
            """
            SELECT DISTINCT user_id, term_label
            FROM user_schedules
            WHERE scenario_id IS NULL
            """
        ).fetchall()
        for row in rows:
            scenario_id = _ensure_legacy_scenario_conn(conn, row["user_id"], row["term_label"])
            conn.execute(
                """
                UPDATE user_schedules
                SET scenario_id = ?
                WHERE user_id = ? AND term_label = ? AND scenario_id IS NULL
                """,
                (scenario_id, row["user_id"], row["term_label"]),
            )
        conn.commit()
        return

    old_rows = conn.execute("SELECT * FROM user_schedules").fetchall()
    old_cols = cols
    conn.execute("BEGIN")
    try:
        _create_user_schedules_new(conn)
        for row in old_rows:
            d = {old_cols[i]: row[i] for i in range(len(old_cols))}
            scenario_id = d.get("scenario_id")
            if scenario_id is None:
                scenario_id = _ensure_legacy_scenario_conn(conn, d["user_id"], d["term_label"])
            conn.execute(
                """
                INSERT OR IGNORE INTO user_schedules__new (
                    user_id, term_label, scenario_id, section_id, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    d["user_id"],
                    d["term_label"],
                    scenario_id,
                    d["section_id"],
                    d.get("created_at")
                    or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
        conn.execute("DROP TABLE user_schedules")
        conn.execute("ALTER TABLE user_schedules__new RENAME TO user_schedules")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS completed_overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            course_code TEXT NOT NULL,
            grade TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    conn.commit()
    conn.close()
    _migrate_user_profiles_slim()


def init_reference_tables():
    """Catalog of program names used for Major/Minor autocomplete; seeded once when empty."""
    import sys
    from pathlib import Path

    _here = Path(__file__).resolve().parent
    if str(_here) not in sys.path:
        sys.path.insert(0, str(_here))

    from reference_programs import DEFAULT_UTPB_PROGRAM_NAMES

    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS academic_program_names (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
        """
    )
    conn.commit()
    n_existing = conn.execute("SELECT COUNT(1) AS c FROM academic_program_names").fetchone()[0]
    if n_existing == 0:
        conn.executemany(
            "INSERT INTO academic_program_names (name) VALUES (?)",
            [(nm,) for nm in DEFAULT_UTPB_PROGRAM_NAMES],
        )
        conn.commit()
    conn.close()


def get_academic_program_names() -> list[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT name FROM academic_program_names ORDER BY name COLLATE NOCASE"
    ).fetchall()
    conn.close()
    return [r["name"] for r in rows]


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


def _grade_from_row(row: dict) -> str:
    grade = row.get("grade") if row.get("grade") is not None else row.get("Grade")
    return str(grade or "").strip().upper()


def _course_code_from_transcript_row(row: dict) -> str:
    raw = row.get("course")
    if not raw and row.get("subject") and row.get("course_number"):
        raw = f"{row.get('subject')} {row.get('course_number')}"
    return normalize_course_code(raw)


def _transcript_course_history(user_id: int) -> list[dict]:
    prof = get_user_profile(user_id)
    tp = prof.get("transcript_parsed_json")
    if not isinstance(tp, dict):
        return []
    rows = tp.get("course_history") or []
    return [dict(r) for r in rows if isinstance(r, dict)]


def _row_attempted_credits(row: dict) -> float:
    for key in ("attempted", "credits", "credit_hours"):
        try:
            value = row.get(key)
            if value is not None and value != "":
                return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _course_row_for_progress(row: dict) -> dict:
    code = _course_code_from_transcript_row(row)
    return {
        "course_code": code,
        "course": code,
        "subject": row.get("subject") or (code.split(" ")[0] if " " in code else None),
        "course_number": row.get("course_number") or (code.split(" ")[1] if " " in code else None),
        "course_name": row.get("course_name"),
        "attempted": row.get("attempted"),
        "earned": row.get("earned"),
        "grade": _grade_from_row(row) or None,
        "term": row.get("term"),
    }


def list_completed_overrides(user_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT id, user_id, course_code, grade, created_at
        FROM completed_overrides
        WHERE user_id = ?
        ORDER BY course_code COLLATE NOCASE, id
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_completed_override(user_id: int, course_code: str, grade: str | None = None) -> dict:
    code = normalize_course_code(course_code)
    if not code:
        raise ValueError("course_code is required")
    grade_norm = str(grade or "").strip().upper() or None
    conn = get_connection()
    cur = conn.execute(
        """
        INSERT INTO completed_overrides (user_id, course_code, grade)
        VALUES (?, ?, ?)
        """,
        (user_id, code, grade_norm),
    )
    conn.commit()
    row = conn.execute(
        """
        SELECT id, user_id, course_code, grade, created_at
        FROM completed_overrides
        WHERE id = ?
        """,
        (cur.lastrowid,),
    ).fetchone()
    conn.close()
    return dict(row)


def delete_completed_override(user_id: int, override_id: int) -> bool:
    conn = get_connection()
    cur = conn.execute(
        "DELETE FROM completed_overrides WHERE user_id = ? AND id = ?",
        (user_id, override_id),
    )
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def get_completed_course_codes(user_id: int) -> set[str]:
    completed: set[str] = set()
    for row in _transcript_course_history(user_id):
        if _grade_from_row(row) in PASSING_COMPLETION_GRADES:
            code = _course_code_from_transcript_row(row)
            if code:
                completed.add(code)
    for row in list_completed_overrides(user_id):
        code = normalize_course_code(row.get("course_code"))
        if code:
            completed.add(code)
    return completed


def _course_tokens_from_text(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for m in COURSE_TOKEN_RE.finditer(str(text or "").upper()):
        code = f"{m.group(1)} {m.group(2)}"
        if code not in seen:
            out.append(code)
            seen.add(code)
    return out


def _lookup_prereq_text(course_code: str) -> str:
    code = normalize_course_code(course_code)
    conn = get_connection()
    row = conn.execute(
        """
        SELECT prerequisites
        FROM courses
        WHERE REPLACE(UPPER(course_code), ' ', '') = ?
        LIMIT 1
        """,
        (compact_course_code(code),),
    ).fetchone()
    conn.close()
    return (row["prerequisites"] if row else None) or ""


def check_prerequisites(course_code: str, completed_codes: set[str]) -> dict:
    """
    Best-effort parser for catalog prerequisite free text.

    It only understands course tokens shaped like SUBJ #### and lowercase
    " and " / " or " separators. Free-text requirements that do not contain
    any SUBJ #### token are reported as met with could_not_parse=True.
    """
    prereq_text = _lookup_prereq_text(course_code)
    completed = {normalize_course_code(c) for c in completed_codes}
    tokens = _course_tokens_from_text(prereq_text)
    if not tokens:
        return {
            "course_code": normalize_course_code(course_code),
            "met": True,
            "missing": [],
            "prerequisites": prereq_text,
            "could_not_parse": bool(prereq_text.strip()),
        }

    text = str(prereq_text or "")
    normalized = re.sub(r"[(),;]", " ", text)
    parts = re.split(r"\s+and\s+", normalized)
    missing: list[str] = []
    for part in parts:
        choices = _course_tokens_from_text(part)
        if not choices:
            continue
        if any(choice in completed for choice in choices):
            continue
        missing.append(" or ".join(choices))

    if not parts:
        missing = [code for code in tokens if code not in completed]

    return {
        "course_code": normalize_course_code(course_code),
        "met": len(missing) == 0,
        "missing": missing,
        "prerequisites": prereq_text,
        "could_not_parse": False,
    }


def _subjects_for_degree_progress(profile: dict, completed_rows: list[dict]) -> set[str]:
    subjects: set[str] = set()
    major = str(profile.get("major") or "")
    minor = str(profile.get("minor") or "")
    if "computer science" in major.lower():
        subjects.add("COSC")
    if "mathematics" in minor.lower():
        subjects.add("MATH")
    if subjects:
        return subjects
    for row in completed_rows:
        subj = row.get("subject")
        if subj:
            subjects.add(str(subj).upper())
    return subjects


def _typical_season(term_infered: object) -> str:
    text = str(term_infered or "").strip()
    low = text.lower()
    if "spring" in low:
        return "Spring"
    if "summer" in low:
        return "Summer"
    if "fall" in low:
        return "Fall"
    return "Unscheduled"


def get_degree_progress(user_id: int) -> dict:
    profile = get_user_profile(user_id)
    rows = _transcript_course_history(user_id)
    completed_rows: list[dict] = []
    in_progress_rows: list[dict] = []
    completed_codes = get_completed_course_codes(user_id)
    in_progress_codes: set[str] = set()

    for row in rows:
        grade = _grade_from_row(row)
        code = _course_code_from_transcript_row(row)
        if not code:
            continue
        if grade in PASSING_COMPLETION_GRADES:
            completed_rows.append(_course_row_for_progress(row))
        elif grade in {"", "IP", "I"}:
            in_progress_rows.append(_course_row_for_progress(row))
            in_progress_codes.add(code)

    for row in list_completed_overrides(user_id):
        code = normalize_course_code(row.get("course_code"))
        if code and code not in {r["course_code"] for r in completed_rows}:
            completed_rows.append(
                {
                    "course_code": code,
                    "course": code,
                    "subject": code.split(" ")[0] if " " in code else None,
                    "course_number": code.split(" ")[1] if " " in code else None,
                    "course_name": None,
                    "attempted": None,
                    "earned": None,
                    "grade": row.get("grade") or "override",
                    "term": "Manual override",
                    "override_id": row.get("id"),
                }
            )

    subjects = _subjects_for_degree_progress(profile, completed_rows)
    conn = get_connection()
    query = """
        SELECT id, subject_code, course_number, course_code, course_name, prerequisites, term_infered
        FROM courses
        WHERE 1=1
    """
    params: list = []
    if subjects:
        placeholders = ",".join("?" for _ in subjects)
        query += f" AND UPPER(subject_code) IN ({placeholders})"
        params.extend(sorted(subjects))
    query += " ORDER BY subject_code, course_number, course_name"
    course_rows = conn.execute(query, params).fetchall()
    conn.close()

    remaining_by_typical_term: dict[str, list[dict]] = {
        "Spring": [],
        "Summer": [],
        "Fall": [],
        "Unscheduled": [],
    }
    blocked = completed_codes | in_progress_codes
    for r in course_rows:
        code = normalize_course_code(r["course_code"])
        if code in blocked:
            continue
        d = dict(r)
        d["course_code"] = code
        remaining_by_typical_term[_typical_season(r["term_infered"])].append(d)

    return {
        "completed": completed_rows,
        "in_progress": in_progress_rows,
        "remaining_by_typical_term": remaining_by_typical_term,
    }


def _credits_for_course(user_id: int, course_code: str) -> float:
    code = normalize_course_code(course_code)
    for row in _transcript_course_history(user_id):
        if _course_code_from_transcript_row(row) == code:
            credits = _row_attempted_credits(row)
            if credits > 0:
                return credits
    conn = get_connection()
    row = conn.execute(
        """
        SELECT credits FROM sections
        WHERE REPLACE(UPPER(course_code), ' ', '') = ?
          AND TRIM(COALESCE(credits, '')) != ''
        LIMIT 1
        """,
        (compact_course_code(code),),
    ).fetchone()
    conn.close()
    if row:
        try:
            return float(row["credits"])
        except (TypeError, ValueError):
            pass
    return 3.0


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


def change_password(user_id, new_password_hash):
    conn = get_connection()
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (new_password_hash, user_id),
    )
    conn.commit()
    conn.close()


def change_username(user_id, new_username):
    """Returns False if the new username is already taken (UNIQUE constraint)."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE users SET username = ? WHERE id = ?",
            (new_username, user_id),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def delete_user_cascade(user_id):
    """Remove all rows owned by user_id, then the users row itself.

    Most child tables already declare ``ON DELETE CASCADE`` against ``users(id)``,
    but PRAGMA foreign_keys is not always honored on legacy databases, so we
    delete from each table explicitly to be safe and idempotent.
    """
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        for stmt in (
            "DELETE FROM user_schedules WHERE user_id = ?",
            "DELETE FROM schedule_scenarios WHERE user_id = ?",
            "DELETE FROM completed_overrides WHERE user_id = ?",
            "DELETE FROM user_settings WHERE user_id = ?",
            "DELETE FROM course_wishlist WHERE user_id = ?",
            "DELETE FROM user_profiles WHERE user_id = ?",
            "DELETE FROM users WHERE id = ?",
        ):
            try:
                conn.execute(stmt, (user_id,))
            except sqlite3.OperationalError:
                # Table may not exist on very old DBs; skip gracefully.
                continue
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def account_summary(user_id):
    user = get_user_by_id(user_id)
    if not user:
        return None
    profile = get_user_profile(user_id)
    has_transcript = bool(profile.get("transcript_parsed_json"))

    conn = get_connection()
    try:
        saved_count_row = conn.execute(
            """
            SELECT COUNT(DISTINCT term_label) AS c
            FROM schedule_scenarios
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        saved_count = int(saved_count_row["c"] or 0) if saved_count_row else 0

        sections_row = conn.execute(
            "SELECT COUNT(1) AS c FROM user_schedules WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        sections_count = int(sections_row["c"] or 0) if sections_row else 0
    finally:
        conn.close()

    return {
        "username": user.get("username"),
        "created_at": user.get("created_at"),
        "transcript_on_file": has_transcript,
        "saved_schedules_count": saved_count,
        "total_sections_in_schedules": sections_count,
    }


def export_user_bundle(user_id):
    """Aggregate everything a user owns for the /api/account/export endpoint."""
    user = get_user_by_id(user_id)
    if not user:
        return None
    profile = get_user_profile(user_id)
    overrides = list_completed_overrides(user_id)
    wishlist = get_wishlist(user_id)

    conn = get_connection()
    try:
        scenario_rows = conn.execute(
            """
            SELECT id, user_id, term_label, name, is_active, share_token, created_at
            FROM schedule_scenarios
            WHERE user_id = ?
            ORDER BY term_label, id
            """,
            (user_id,),
        ).fetchall()
        scenarios = []
        for row in scenario_rows:
            sec_rows = conn.execute(
                """
                SELECT section_id
                FROM user_schedules
                WHERE user_id = ? AND term_label = ? AND scenario_id = ?
                ORDER BY section_id
                """,
                (user_id, row["term_label"], row["id"]),
            ).fetchall()
            entry = dict(row)
            entry["section_ids"] = [r["section_id"] for r in sec_rows]
            scenarios.append(entry)

        settings_rows = conn.execute(
            "SELECT key, value FROM user_settings WHERE user_id = ? ORDER BY key",
            (user_id,),
        ).fetchall()
        settings = [dict(r) for r in settings_rows]
    finally:
        conn.close()

    return {
        "user": {
            "id": user.get("id"),
            "username": user.get("username"),
            "created_at": user.get("created_at"),
        },
        "profile": {
            "major": profile.get("major"),
            "minor": profile.get("minor"),
            "transcript_original_name": profile.get("transcript_original_name"),
            "transcript_parsed_json": profile.get("transcript_parsed_json"),
        },
        "completed_overrides": overrides,
        "scenarios": scenarios,
        "wishlist": wishlist,
        "user_settings": settings,
    }


def _scenario_dict(row):
    return dict(row) if row else None


def get_scenarios(user_id, term_label):
    conn = get_connection()
    try:
        ensure_active_scenario(user_id, term_label, conn=conn)
        conn.commit()
        rows = conn.execute(
            """
            SELECT id, user_id, term_label, name, is_active, share_token, created_at
            FROM schedule_scenarios
            WHERE user_id = ? AND term_label = ?
            ORDER BY is_active DESC, created_at, id
            """,
            (user_id, term_label),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_scenario(user_id, scenario_id):
    conn = get_connection()
    row = conn.execute(
        """
        SELECT id, user_id, term_label, name, is_active, share_token, created_at
        FROM schedule_scenarios
        WHERE id = ? AND user_id = ?
        """,
        (scenario_id, user_id),
    ).fetchone()
    conn.close()
    return _scenario_dict(row)


def get_scenario_by_token(share_token):
    conn = get_connection()
    row = conn.execute(
        """
        SELECT id, user_id, term_label, name, is_active, share_token, created_at
        FROM schedule_scenarios
        WHERE share_token = ?
        """,
        (share_token,),
    ).fetchone()
    conn.close()
    return _scenario_dict(row)


def ensure_active_scenario(user_id, term_label, conn=None):
    owns_conn = conn is None
    if conn is None:
        conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT id
            FROM schedule_scenarios
            WHERE user_id = ? AND term_label = ? AND is_active = 1
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id, term_label),
        ).fetchone()
        if row:
            return row["id"]
        row = conn.execute(
            """
            SELECT id
            FROM schedule_scenarios
            WHERE user_id = ? AND term_label = ?
            ORDER BY id
            LIMIT 1
            """,
            (user_id, term_label),
        ).fetchone()
        if row:
            scenario_id = row["id"]
        else:
            cur = conn.execute(
                """
                INSERT INTO schedule_scenarios (user_id, term_label, name, is_active)
                VALUES (?, ?, ?, 1)
                """,
                (user_id, term_label, "My schedule"),
            )
            scenario_id = cur.lastrowid
        conn.execute(
            """
            UPDATE schedule_scenarios
            SET is_active = CASE WHEN id = ? THEN 1 ELSE 0 END
            WHERE user_id = ? AND term_label = ?
            """,
            (scenario_id, user_id, term_label),
        )
        if owns_conn:
            conn.commit()
        return scenario_id
    finally:
        if owns_conn:
            conn.close()


def create_scenario(user_id, term_label, name):
    clean_name = " ".join((name or "").split()) or "New scenario"
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        conn.execute(
            """
            UPDATE schedule_scenarios
            SET is_active = 0
            WHERE user_id = ? AND term_label = ?
            """,
            (user_id, term_label),
        )
        cur = conn.execute(
            """
            INSERT INTO schedule_scenarios (user_id, term_label, name, is_active)
            VALUES (?, ?, ?, 1)
            """,
            (user_id, term_label, clean_name),
        )
        conn.commit()
        return get_scenario(user_id, cur.lastrowid)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def duplicate_scenario(user_id, scenario_id, name=None):
    src = get_scenario(user_id, scenario_id)
    if not src:
        return None
    new_name = " ".join((name or "").split()) or f"{src['name']} copy"
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        conn.execute(
            """
            UPDATE schedule_scenarios
            SET is_active = 0
            WHERE user_id = ? AND term_label = ?
            """,
            (user_id, src["term_label"]),
        )
        cur = conn.execute(
            """
            INSERT INTO schedule_scenarios (user_id, term_label, name, is_active)
            VALUES (?, ?, ?, 1)
            """,
            (user_id, src["term_label"], new_name),
        )
        new_id = cur.lastrowid
        rows = conn.execute(
            """
            SELECT section_id
            FROM user_schedules
            WHERE user_id = ? AND term_label = ? AND scenario_id = ?
            ORDER BY section_id
            """,
            (user_id, src["term_label"], scenario_id),
        ).fetchall()
        if rows:
            conn.executemany(
                """
                INSERT OR IGNORE INTO user_schedules (
                    user_id, term_label, scenario_id, section_id
                ) VALUES (?, ?, ?, ?)
                """,
                [(user_id, src["term_label"], new_id, r["section_id"]) for r in rows],
            )
        conn.commit()
        return get_scenario(user_id, new_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def rename_scenario(user_id, scenario_id, name):
    clean_name = " ".join((name or "").split())
    if not clean_name:
        return None
    conn = get_connection()
    conn.execute(
        """
        UPDATE schedule_scenarios
        SET name = ?
        WHERE id = ? AND user_id = ?
        """,
        (clean_name, scenario_id, user_id),
    )
    conn.commit()
    conn.close()
    return get_scenario(user_id, scenario_id)


def activate_scenario(user_id, scenario_id):
    scenario = get_scenario(user_id, scenario_id)
    if not scenario:
        return None
    conn = get_connection()
    conn.execute(
        """
        UPDATE schedule_scenarios
        SET is_active = CASE WHEN id = ? THEN 1 ELSE 0 END
        WHERE user_id = ? AND term_label = ?
        """,
        (scenario_id, user_id, scenario["term_label"]),
    )
    conn.commit()
    conn.close()
    return get_scenario(user_id, scenario_id)


def delete_scenario(user_id, scenario_id):
    scenario = get_scenario(user_id, scenario_id)
    if not scenario:
        return None
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        conn.execute(
            "DELETE FROM schedule_scenarios WHERE id = ? AND user_id = ?",
            (scenario_id, user_id),
        )
        fallback = conn.execute(
            """
            SELECT id
            FROM schedule_scenarios
            WHERE user_id = ? AND term_label = ?
            ORDER BY id
            LIMIT 1
            """,
            (user_id, scenario["term_label"]),
        ).fetchone()
        if fallback:
            active_id = fallback["id"]
        else:
            cur = conn.execute(
                """
                INSERT INTO schedule_scenarios (user_id, term_label, name, is_active)
                VALUES (?, ?, ?, 1)
                """,
                (user_id, scenario["term_label"], "My schedule"),
            )
            active_id = cur.lastrowid
        conn.execute(
            """
            UPDATE schedule_scenarios
            SET is_active = CASE WHEN id = ? THEN 1 ELSE 0 END
            WHERE user_id = ? AND term_label = ?
            """,
            (active_id, user_id, scenario["term_label"]),
        )
        conn.commit()
        return get_scenario(user_id, active_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def set_scenario_share_token(user_id, scenario_id, share_token):
    scenario = get_scenario(user_id, scenario_id)
    if not scenario:
        return None
    conn = get_connection()
    conn.execute(
        """
        UPDATE schedule_scenarios
        SET share_token = COALESCE(share_token, ?)
        WHERE id = ? AND user_id = ?
        """,
        (share_token, scenario_id, user_id),
    )
    conn.commit()
    conn.close()
    return get_scenario(user_id, scenario_id)


def get_saved_schedule_ids(user_id, term_label, scenario_id=None):
    if scenario_id is None:
        scenario_id = ensure_active_scenario(user_id, term_label)
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT section_id
        FROM user_schedules
        WHERE user_id = ? AND term_label = ? AND scenario_id = ?
        ORDER BY section_id
        """,
        (user_id, term_label, scenario_id),
    ).fetchall()
    conn.close()
    return [r["section_id"] for r in rows]


def get_saved_schedule_ids_by_term(user_id):
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT us.term_label, us.section_id
        FROM user_schedules us
        JOIN schedule_scenarios sc ON sc.id = us.scenario_id
        WHERE us.user_id = ? AND sc.is_active = 1
        ORDER BY us.term_label, us.section_id
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    by_term = {}
    for row in rows:
        by_term.setdefault(row["term_label"], []).append(row["section_id"])
    return by_term


def get_user_setting(user_id, key, default=None):
    conn = get_connection()
    row = conn.execute(
        """
        SELECT value
        FROM user_settings
        WHERE user_id = ? AND key = ?
        """,
        (user_id, key),
    ).fetchone()
    conn.close()
    if not row:
        return default
    return row["value"]


def set_user_setting(user_id, key, value):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO user_settings (user_id, key, value)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value
        """,
        (user_id, key, value),
    )
    conn.commit()
    conn.close()


def save_schedule_ids(user_id, term_label, section_ids, scenario_id=None):
    if scenario_id is None:
        scenario_id = ensure_active_scenario(user_id, term_label)
    conn = get_connection()
    conn.execute(
        """
        DELETE FROM user_schedules
        WHERE user_id = ? AND term_label = ? AND scenario_id = ?
        """,
        (user_id, term_label, scenario_id),
    )
    if section_ids:
        conn.executemany(
            """
            INSERT OR IGNORE INTO user_schedules (
                user_id, term_label, scenario_id, section_id
            ) VALUES (?, ?, ?, ?)
            """,
            [(user_id, term_label, scenario_id, sid) for sid in section_ids],
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


_TERM_LABEL_RE = re.compile(r"^(Spring|Summer|Fall)\s+(\d{4})$", re.IGNORECASE)
_SEASON_ORDER = {"Spring": 0, "Summer": 1, "Fall": 2}


def _normalize_term_label(text: str | None) -> str | None:
    if not text or not isinstance(text, str):
        return None
    text = " ".join(text.split())
    m = _TERM_LABEL_RE.match(text)
    if not m:
        return None
    return f"{m.group(1).title()} {m.group(2)}"


def _term_sort_key(label: str) -> tuple:
    m = _TERM_LABEL_RE.match(label.strip())
    if not m:
        return (9999, 99, label)
    y = int(m.group(2))
    season = m.group(1).title()
    return (y, _SEASON_ORDER[season], "")


def _next_season_year(y: int, season: str) -> tuple[int, str]:
    if season == "Spring":
        return y, "Summer"
    if season == "Summer":
        return y, "Fall"
    return y + 1, "Spring"


def _label_from_year_season(y: int, season: str) -> str:
    return f"{season} {y}"


def _estimated_semester_label_from_date(today: date) -> str:
    """Rough Banner-style label for the academic period containing today."""
    m = today.month
    y = today.year
    if m in (1, 2, 3, 4, 5):
        return _label_from_year_season(y, "Spring")
    if m in (6, 7, 8):
        return _label_from_year_season(y, "Summer")
    return _label_from_year_season(y, "Fall")


def _bootstrap_terms_if_empty() -> set[str]:
    """When the DB has no terms yet, offer a few projected terms around today."""
    t = date.today()
    m = t.month
    if m in (1, 2, 3, 4, 5):
        y, s = t.year, "Spring"
    elif m in (6, 7, 8):
        y, s = t.year, "Summer"
    else:
        y, s = t.year, "Fall"
    out = set()
    for _ in range(12):
        out.add(_label_from_year_season(y, s))
        y, s = _next_season_year(y, s)
    return out


def _term_label_variants(term_label: str) -> list[str]:
    raw = (term_label or "").strip()
    if not raw:
        return []
    out: set[str] = {raw}
    n = _normalize_term_label(raw)
    if n:
        out.add(n)
    return list(out)


def _section_count_for_term_conn(conn: sqlite3.Connection, term_label: str) -> int:
    variants = _term_label_variants(term_label)
    if not variants:
        return 0
    ph = ",".join("?" * len(variants))
    row = conn.execute(
        f"SELECT COUNT(1) AS c FROM sections WHERE term_label IN ({ph})",
        variants,
    ).fetchone()
    return int(row["c"] or 0)


def _season_from_term_label(term_label: str) -> str | None:
    n = _normalize_term_label(term_label) or (term_label or "").strip()
    m = _TERM_LABEL_RE.match(n)
    if not m:
        return None
    return m.group(1).title()


def _term_infered_sql_condition(season: str | None) -> str:
    """SQL for matching courses.term_infered to a calendar season (degree-map inference)."""
    if not season:
        return "TRIM(COALESCE(term_infered,'')) != ''"
    st = season.title()
    col = "LOWER(COALESCE(term_infered,''))"
    if st == "Spring":
        return f"({col} LIKE '%spring%' AND TRIM(COALESCE(term_infered,'')) != '')"
    if st == "Fall":
        return f"({col} LIKE '%fall%' AND TRIM(COALESCE(term_infered,'')) != '')"
    if st == "Summer":
        return (
            f"(( {col} LIKE '%summer%' OR {col} LIKE '%fall%' OR {col} LIKE '%spring%' ) "
            f"AND TRIM(COALESCE(term_infered,'')) != '')"
        )
    return "TRIM(COALESCE(term_infered,'')) != ''"


# Negative IDs reference courses.id (synthetic "section" rows for planning when Banner has no term).


def _placeholder_dict_from_course_row(r: sqlite3.Row, term_label: str) -> dict:
    cid = int(r["id"])
    return {
        "id": -cid,
        "term_label": term_label,
        "class_nbr": None,
        "subject_code": r["subject_code"],
        "course_number": r["course_number"],
        "course_code": r["course_code"],
        "section_code": "",
        "credits": "",
        "days": "",
        "session": "",
        "start_time": "",
        "end_time": "",
        "location": "",
        "mode": "",
        "course_name": r["course_name"],
        "prerequisites": r["prerequisites"],
        "term_infered": r["term_infered"],
        "session_start_date": None,
        "session_end_date": None,
        "is_inferred_placeholder": True,
    }


def _inferred_placeholder_sections(
    conn: sqlite3.Connection,
    term_label: str,
    subject_code: str | None,
    level: str | None,
    search: str | None,
) -> list[dict]:
    """Catalog rows shaped like section API objects when no sections exist for this term."""
    season = _season_from_term_label(term_label)
    cond = _term_infered_sql_condition(season)
    query = f"""
        SELECT id, subject_code, course_number, course_code, course_name, prerequisites, term_infered
        FROM courses
        WHERE {cond}
    """
    params: list = []
    if subject_code:
        query += " AND subject_code = ?"
        params.append(subject_code)
    if level:
        query += " AND course_number LIKE ?"
        params.append(f"{level}%")
    if search:
        query += " AND (course_code LIKE ? OR course_name LIKE ?)"
        params.append(f"%{search}%")
        params.append(f"%{search}%")

    query += " ORDER BY subject_code, course_number"
    rows = conn.execute(query, params).fetchall()
    return [_placeholder_dict_from_course_row(r, term_label) for r in rows]


def _terms_from_transcript(tp) -> set[str]:
    if not isinstance(tp, dict):
        return set()
    out: set[str] = set()
    for raw in tp.get("terms") or []:
        n = _normalize_term_label(str(raw))
        if n:
            out.add(n)
    n = _normalize_term_label(tp.get("last_term_label") or None)
    if n:
        out.add(n)
    for row in tp.get("course_history") or []:
        if isinstance(row, dict):
            n = _normalize_term_label(row.get("term") or None)
            if n:
                out.add(n)
    return out


def _transcript_row_for_api(row: dict) -> dict:
    subj = row.get("subject")
    num = row.get("course_number")
    alt_code = row.get("course") or (f"{subj} {num}" if subj is not None and num is not None else None)
    g = row.get("grade") if row.get("grade") is not None else row.get("Grade")
    return {
        "subject": subj,
        "course_number": num,
        "course": alt_code,
        "course_name": row.get("course_name"),
        "attempted": row.get("attempted"),
        "earned": row.get("earned"),
        "grade": g,
        "term": row.get("term"),
    }


def get_transcript_courses_for_term(user_id: int, term_label: str) -> dict:
    """Return institutional transcript rows matching one Banner-style term label."""
    raw_tl = " ".join(str(term_label or "").split())
    target = _normalize_term_label(raw_tl) or raw_tl
    prof = get_user_profile(user_id)
    tp = prof.get("transcript_parsed_json")
    parsed_ok = isinstance(tp, dict)
    has_file = bool(prof.get("transcript_original_name"))

    def row_matches(row_term: object) -> bool:
        if row_term is None or row_term == "":
            return False
        n = _normalize_term_label(str(row_term))
        if n and target:
            return n == target
        return " ".join(str(row_term).split()) == target

    rows_out: list[dict] = []
    partial = False

    if parsed_ok:
        partial = bool(tp.get("course_history_is_partial"))
        ch = tp.get("course_history")
        if isinstance(ch, list):
            for row in ch:
                if not isinstance(row, dict):
                    continue
                if row_matches(row.get("term")):
                    rows_out.append(_transcript_row_for_api(row))
        if not rows_out:
            lt_lbl = tp.get("last_term_label")
            nlt = _normalize_term_label(str(lt_lbl)) if lt_lbl else None
            if nlt and nlt == target:
                for row in tp.get("latest_term_courses") or []:
                    if isinstance(row, dict):
                        rows_out.append(_transcript_row_for_api(row))

    return {
        "term": raw_tl or str(term_label or ""),
        "normalized_term": target,
        "courses": rows_out,
        "has_transcript_file": has_file,
        "has_parsed_transcript": parsed_ok,
        "course_history_partial": partial,
    }


def _expand_projected_forward(merged: set[str], count: int = 9) -> set[str]:
    """Add near-future terms for planning; caps a few years beyond the current year."""
    if not merged:
        merged = _bootstrap_terms_if_empty()
    max_year = date.today().year + 2
    labels = sorted(merged, key=_term_sort_key)
    m = _TERM_LABEL_RE.match(labels[-1])
    if not m:
        y, s = date.today().year, "Spring"
    else:
        y, s = int(m.group(2)), m.group(1).title()
        y, s = _next_season_year(y, s)
    projected: set[str] = set()
    added = 0
    while added < count and y <= max_year + 1:
        if y > max_year:
            break
        label = _label_from_year_season(y, s)
        if label not in merged:
            projected.add(label)
            added += 1
        y, s = _next_season_year(y, s)
    return projected




def get_term_timeline(user_id: int) -> dict:
    """
    Build (1) scheduling terms — current semester and forward for planning —
    excluding prior semesters from the picker, and (2) past_terms for transcript /
    archival context. Uses session_calendar where possible to anchor “now”; otherwise
    estimates the semester containing today for the split.
    """
    today = date.today()
    conn = get_connection()
    from_sections = {r["term_label"] for r in conn.execute("SELECT DISTINCT term_label FROM sections")}
    from_calendar = {r["term_label"] for r in conn.execute("SELECT DISTINCT term_label FROM session_calendar")}
    from_saved_raw: set[str] = set()
    if user_id is not None:
        from_saved_raw = {
            r["term_label"]
            for r in conn.execute(
                "SELECT DISTINCT term_label FROM user_schedules WHERE user_id = ?",
                (user_id,),
            )
        }

    floor_rows = conn.execute(
        """
        SELECT term_label,
               MIN(session_start_date) AS d0,
               MAX(session_end_date) AS d1
        FROM session_calendar
        WHERE session_start_date != '' AND session_end_date != ''
        GROUP BY term_label
        """
    ).fetchall()
    span_early: dict[str, tuple[str, str]] = {}
    for r in floor_rows:
        tl = (r["term_label"] or "").strip()
        span_early[tl] = (r["d0"] or "", r["d1"] or "")
        nn = _normalize_term_label(tl)
        if nn and nn != tl:
            span_early.setdefault(nn, (r["d0"] or "", r["d1"] or ""))

    current_from_calendar: str | None = None
    for tl, sp in span_early.items():
        d0, d1 = sp[0], sp[1]
        if not d0 or not d1:
            continue
        try:
            a, b = date.fromisoformat(d0), date.fromisoformat(d1)
            if a <= today <= b:
                current_from_calendar = _normalize_term_label(tl) or tl
                break
        except ValueError:
            continue

    scheduling_floor_label = current_from_calendar or _estimated_semester_label_from_date(today)
    floor_k = _term_sort_key(scheduling_floor_label)

    conn.close()

    from_transcript: set[str] = set()
    if user_id is not None:
        prof = get_user_profile(user_id)
        from_transcript = _terms_from_transcript(prof.get("transcript_parsed_json") or {})

    merged = set()
    merged |= from_sections
    merged |= from_calendar
    merged |= from_saved_raw
    merged |= from_transcript
    if not merged:
        merged = _bootstrap_terms_if_empty()

    labels_sorted = sorted(merged, key=_term_sort_key)
    by_norm: dict[str, str] = {}
    for raw in labels_sorted:
        norm = _normalize_term_label(raw)
        key = norm or raw
        if key not in by_norm:
            by_norm[key] = _normalize_term_label(raw) or raw
        else:
            prefer = _normalize_term_label(raw) or raw
            if prefer == key:
                by_norm[key] = prefer

    ordered_full = sorted(by_norm.values(), key=_term_sort_key)
    scheduling_candidates = [l for l in ordered_full if _term_sort_key(l) >= floor_k]
    past_candidates = [l for l in ordered_full if _term_sort_key(l) < floor_k]

    if scheduling_candidates:
        seed_sched = set(scheduling_candidates)
    else:
        seed_sched = {scheduling_floor_label}

    projected_f = _expand_projected_forward(seed_sched, count=9)
    merged_sched = seed_sched | set(projected_f)
    projected_canon = {_normalize_term_label(x) or x for x in projected_f}

    canon_sched_sorted = sorted(merged_sched, key=_term_sort_key)
    by_ns: dict[str, str] = {}
    for raw in canon_sched_sorted:
        norm = _normalize_term_label(raw)
        nk = norm or raw
        if nk not in by_ns:
            by_ns[nk] = _normalize_term_label(raw) or raw
        elif (_normalize_term_label(raw) or raw) == nk:
            by_ns[nk] = nk

    ordered = sorted(by_ns.values(), key=_term_sort_key)

    conn = get_connection()
    date_rows = conn.execute(
        """
        SELECT term_label,
               MIN(session_start_date) AS d0,
               MAX(session_end_date) AS d1
        FROM session_calendar
        WHERE session_start_date != '' AND session_end_date != ''
        GROUP BY term_label
        """
    ).fetchall()
    span_by_label: dict[str, tuple[str, str]] = {}
    for r in date_rows:
        tl = (r["term_label"] or "").strip()
        span_by_label[tl] = (r["d0"] or "", r["d1"] or "")
        n = _normalize_term_label(tl)
        if n and n != tl:
            span_by_label.setdefault(n, (r["d0"] or "", r["d1"] or ""))
    has_sections_by: dict[str, int] = {}
    for r in conn.execute("SELECT term_label, COUNT(1) AS c FROM sections GROUP BY term_label"):
        tl = (r["term_label"] or "").strip()
        c = r["c"] or 0
        key = _normalize_term_label(tl) or tl
        has_sections_by[key] = c
    saved_count_by: dict[str, int] = {}
    if user_id is not None:
        for r in conn.execute(
            "SELECT term_label, COUNT(1) AS c FROM user_schedules WHERE user_id = ? GROUP BY term_label",
            (user_id,),
        ):
            tl = (r["term_label"] or "").strip()
            key = _normalize_term_label(tl) or tl
            saved_count_by[key] = r["c"] or 0
    conn.close()

    def span_for(tl: str) -> tuple[str, str] | None:
        s = span_by_label.get(tl)
        if s and s[0] and s[1]:
            return s
        n = _normalize_term_label(tl)
        if n:
            s = span_by_label.get(n)
            if s and s[0] and s[1]:
                return s
        return None

    def nsec(tl: str) -> int:
        key = _normalize_term_label(tl) or tl
        return has_sections_by.get(key, 0)

    def has_saved(tl: str) -> bool:
        key = _normalize_term_label(tl) or tl
        return saved_count_by.get(key, 0) > 0

    terms_out: list[dict] = []
    current_label: str | None = None
    for label in ordered:
        norm = _normalize_term_label(label) or label
        m = _TERM_LABEL_RE.match(label)
        year = int(m.group(2)) if m else None
        season = m.group(1).title() if m else None
        sp = span_for(label)
        d0 = d1 = None
        if sp:
            d0, d1 = sp[0], sp[1]
        nsec_c = nsec(label)
        is_projected = norm in projected_canon
        has_cal = sp is not None
        from_tr = norm in from_transcript
        entry = {
            "label": label,
            "year": year,
            "season": season,
            "has_sections": nsec_c > 0,
            "section_count": nsec_c,
            "has_calendar": has_cal,
            "date_start": d0,
            "date_end": d1,
            "from_transcript": from_tr,
            "has_saved_schedule": has_saved(label),
            "is_projected": bool(is_projected),
        }
        terms_out.append(entry)
        if current_label is None and d0 and d1:
            try:
                a, b = date.fromisoformat(d0), date.fromisoformat(d1)
                if a <= today <= b:
                    current_label = label
            except ValueError:
                pass

    past_terms_out: list[dict] = []
    for label in sorted(past_candidates, key=_term_sort_key, reverse=True):
        norm_p = _normalize_term_label(label) or label
        mp = _TERM_LABEL_RE.match(label)
        py = int(mp.group(2)) if mp else None
        pseason = mp.group(1).title() if mp else None
        sp_p = span_for(label)
        de = sp_p[1] if sp_p else None
        past_terms_out.append(
            {
                "label": label,
                "year": py,
                "season": pseason,
                "from_transcript": norm_p in from_transcript,
                "has_saved_schedule": has_saved(label),
                "had_catalog": nsec(label) > 0,
                "date_end": de,
            }
        )

    def pick_default() -> str:
        if current_label and any(t["label"] == current_label for t in terms_out):
            return current_label
        for t in terms_out:
            if t["has_sections"]:
                return t["label"]
        for t in terms_out:
            if t["from_transcript"] or t["has_saved_schedule"]:
                return t["label"]
        if terms_out:
            return terms_out[0]["label"]
        return ""

    return {
        "terms": terms_out,
        "past_terms": past_terms_out,
        "scheduling_floor_label": scheduling_floor_label,
        "current_term": current_label,
        "default_term": pick_default(),
        "server_date": today.isoformat(),
    }


def get_subjects(term_label=None):
    conn = get_connection()
    if term_label:
        variants = _term_label_variants(term_label)
        if variants:
            ph = ",".join("?" * len(variants))
            rows = conn.execute(
                f"SELECT DISTINCT subject_code FROM sections WHERE term_label IN ({ph}) ORDER BY subject_code",
                variants,
            ).fetchall()
        else:
            rows = []
        if not rows and _section_count_for_term_conn(conn, term_label) == 0:
            season = _season_from_term_label(term_label)
            cond = _term_infered_sql_condition(season)
            rows = conn.execute(
                f"""
                SELECT DISTINCT subject_code FROM courses
                WHERE {cond}
                ORDER BY subject_code
                """
            ).fetchall()
        conn.close()
        return [r["subject_code"] for r in rows]
    rows = conn.execute(
        "SELECT DISTINCT subject_code FROM sections ORDER BY subject_code"
    ).fetchall()
    conn.close()
    return [r["subject_code"] for r in rows]


def get_modes(term_label=None):
    conn = get_connection()
    if term_label:
        if _section_count_for_term_conn(conn, term_label) == 0:
            conn.close()
            return []
        variants = _term_label_variants(term_label)
        ph = ",".join("?" * len(variants))
        rows = conn.execute(
            f"""
            SELECT DISTINCT mode FROM sections
            WHERE term_label IN ({ph}) AND mode != '' ORDER BY mode
            """,
            variants,
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT DISTINCT mode FROM sections WHERE mode != '' ORDER BY mode"
        ).fetchall()
    conn.close()
    return [r["mode"] for r in rows]


def get_sections(term_label, subject_code=None, mode=None, level=None, search=None):
    conn = get_connection()
    try:
        has_real = _section_count_for_term_conn(conn, term_label) > 0
        if not has_real:
            return _inferred_placeholder_sections(
                conn,
                term_label,
                subject_code,
                level,
                search,
            )

        variants = _term_label_variants(term_label)
        ph = ",".join("?" * len(variants))
        query = f"""
            SELECT s.id, s.term_label, s.class_nbr, s.subject_code, s.course_number,
                   s.course_code, s.section_code, s.credits, s.days, s.session,
                   s.start_time, s.end_time, s.location, s.mode,
                   c.course_name, c.prerequisites, c.term_infered,
                   cal.session_start_date, cal.session_end_date
            FROM sections s
            LEFT JOIN courses c ON c.course_code = s.course_code
            LEFT JOIN session_calendar cal
              ON cal.term_label = s.term_label AND cal.session = s.session
            WHERE s.term_label IN ({ph})
        """
        params: list = list(variants)

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
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_sections_by_ids(section_ids, term_label: str | None = None):
    """Resolve saved rows. Positive IDs are real sections; negative IDs are planning placeholders (-courses.id)."""
    if not section_ids:
        return []
    tl = " ".join((term_label or "").split())
    conn = get_connection()
    try:
        real_ids = [i for i in section_ids if i > 0]
        ph_ids = [-i for i in section_ids if i < 0]
        by_sid: dict[int, dict] = {}

        if real_ids:
            placeholders = ",".join("?" for _ in real_ids)
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
                """,
                real_ids,
            ).fetchall()
            for r in rows:
                by_sid[int(r["id"])] = dict(r)

        if ph_ids:
            placeholders = ",".join("?" for _ in ph_ids)
            crows = conn.execute(
                f"""
                SELECT id, subject_code, course_number, course_code, course_name, prerequisites, term_infered
                FROM courses WHERE id IN ({placeholders})
                """,
                ph_ids,
            ).fetchall()
            for r in crows:
                d = _placeholder_dict_from_course_row(r, tl)
                if tl:
                    variants = _term_label_variants(tl)
                    if variants:
                        vph = ",".join("?" for _ in variants)
                        credit_row = conn.execute(
                            f"""
                            SELECT credits
                            FROM sections
                            WHERE term_label IN ({vph})
                              AND REPLACE(UPPER(course_code), ' ', '') = ?
                              AND TRIM(COALESCE(credits, '')) != ''
                            ORDER BY id
                            LIMIT 1
                            """,
                            [*variants, compact_course_code(r["course_code"])],
                        ).fetchone()
                        if credit_row:
                            d["credits"] = credit_row["credits"]
                by_sid[d["id"]] = d

        return [by_sid[sid] for sid in section_ids if sid in by_sid]
    finally:
        conn.close()


def _season_from_term_filter(term_label: str | None) -> str | None:
    season = _season_from_term_label(term_label or "")
    if season:
        return season
    text = (term_label or "").lower()
    for candidate in ("spring", "summer", "fall"):
        if candidate in text:
            return candidate.title()
    return None


def get_all_courses(subject_code=None, search=None, level=None, term=None):
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
    if level and str(level) in {"1", "2", "3", "4"}:
        query += " AND course_number LIKE ?"
        params.append(f"{level}%")
    if term:
        query += f" AND {_term_infered_sql_condition(_season_from_term_filter(term))}"
    query += " ORDER BY subject_code, course_number"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _section_row_for_course_detail(row: sqlite3.Row) -> dict:
    data = dict(row)
    start = data.get("session_start_date") or ""
    end = data.get("session_end_date") or ""
    data["dates"] = f"{start} - {end}" if start and end else ""
    return data


def get_course_detail(course_id: int):
    conn = get_connection()
    try:
        course = conn.execute(
            """
            SELECT id, subject_code, course_number, course_code, course_name,
                   course_url, prerequisites, term_infered
            FROM courses
            WHERE id = ?
            """,
            (course_id,),
        ).fetchone()
        if not course:
            return None

        rows = conn.execute(
            """
            SELECT s.id, s.term_label, s.class_nbr, s.subject_code, s.course_number,
                   s.course_code, s.section_code, s.credits, s.days, s.session,
                   s.start_time, s.end_time, s.location, s.mode,
                   cal.session_start_date, cal.session_end_date
            FROM sections s
            LEFT JOIN session_calendar cal
              ON cal.term_label = s.term_label AND cal.session = s.session
            WHERE s.course_code = ?
            """,
            (course["course_code"],),
        ).fetchall()

        sections = [_section_row_for_course_detail(r) for r in rows]
        sections.sort(
            key=lambda r: (_term_sort_key(r.get("term_label") or ""), r.get("section_code") or ""),
            reverse=True,
        )

        grouped: dict[str, list[dict]] = {}
        for section in sections:
            grouped.setdefault(section.get("term_label") or "Unknown term", []).append(section)

        terms = [
            {"term_label": label, "sections": grouped[label]}
            for label in sorted(grouped, key=_term_sort_key, reverse=True)
        ]

        data = dict(course)
        data["sections"] = sections
        data["sections_by_term"] = grouped
        data["terms"] = terms
        return data
    finally:
        conn.close()


def get_wishlist(user_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT w.user_id, w.course_id, w.priority, w.notes, w.created_at,
               c.subject_code, c.course_number, c.course_code, c.course_name,
               c.course_url, c.prerequisites, c.term_infered
        FROM course_wishlist w
        JOIN courses c ON c.id = w.course_id
        WHERE w.user_id = ?
        ORDER BY w.priority DESC, w.created_at DESC, c.subject_code, c.course_number
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_wishlist_course(user_id: int, course_id: int, notes=None, priority=0) -> bool:
    try:
        priority_int = int(priority or 0)
    except (TypeError, ValueError):
        priority_int = 0
    clean_notes = str(notes).strip() if notes is not None else None
    conn = get_connection()
    try:
        exists = conn.execute("SELECT 1 FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not exists:
            return False
        conn.execute(
            """
            INSERT INTO course_wishlist (user_id, course_id, priority, notes)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, course_id) DO UPDATE SET
                priority = excluded.priority,
                notes = excluded.notes
            """,
            (user_id, course_id, priority_int, clean_notes or None),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def delete_wishlist_course(user_id: int, course_id: int) -> bool:
    conn = get_connection()
    try:
        cur = conn.execute(
            "DELETE FROM course_wishlist WHERE user_id = ? AND course_id = ?",
            (user_id, course_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


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
