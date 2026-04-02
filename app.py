"""
Small Flask web app for the course project.
Run from this folder:  python app.py
Then open the URL shown in the terminal (usually http://127.0.0.1:5000).
"""
import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from backend.config import anthropic_api_key
from backend.db import connect, rows_as_dicts

BASE_DIR = Path(__file__).resolve().parent
app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)


def fix_time(value):
    if value is None:
        return None
    if isinstance(value, datetime.timedelta):
        secs = int(value.total_seconds()) % 86400
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        value = datetime.time(h, m, s)
    if isinstance(value, datetime.time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, str):
        return value
    return str(value)


def section_to_json(row):
    return {
        "section_id": row.get("section_id"),
        "section_code": row.get("section_code"),
        "semester": row.get("semester"),
        "instructor": row.get("instructor"),
        "days": row.get("days"),
        "start_time": fix_time(row.get("start_time")),
        "end_time": fix_time(row.get("end_time")),
        "room_number": row.get("room_number"),
        "delivery_mode": row.get("delivery_mode"),
        "enrolled": row.get("enrolled"),
        "seat_limit": row.get("seat_limit"),
    }


@app.route("/")
def index():
    return render_template("index.html", active_page="courses")


@app.route("/planner")
def planner():
    return render_template("planner.html", active_page="planner")


@app.route("/api/courses")
def api_courses():
    try:
        conn, backend = connect()
    except Exception as e:
        return jsonify({"error": str(e)}), 503

    if backend == "mysql":
        prereq_sql = "GROUP_CONCAT(p.prereq_code ORDER BY p.prereq_code SEPARATOR ', ')"
    else:
        prereq_sql = "GROUP_CONCAT(p.prereq_code, ', ' ORDER BY p.prereq_code)"

    try:
        if backend == "mysql":
            cur = conn.cursor(dictionary=True)
        else:
            cur = conn.cursor()

        cur.execute(
            f"""
            SELECT c.course_code, c.title, c.credits, c.description,
                   {prereq_sql} AS prerequisites
            FROM courses c
            LEFT JOIN prerequisites p ON p.course_code = c.course_code
            GROUP BY c.course_code, c.title, c.credits, c.description
            ORDER BY c.course_code
            """
        )
        rows = cur.fetchall() if backend == "mysql" else rows_as_dicts(cur, backend)
        for row in rows:
            raw = row.get("prerequisites")
            row["prerequisites"] = raw.split(", ") if raw else []

        cur.execute(
            """
            SELECT section_id, course_code, semester, section_code, instructor, days,
                   start_time, end_time, room_number, delivery_mode, enrolled, seat_limit
            FROM sections
            ORDER BY semester, course_code, section_code
            """
        )
        sec_rows = cur.fetchall() if backend == "mysql" else rows_as_dicts(cur, backend)

        by_course = {}
        for s in sec_rows:
            code = s["course_code"]
            if code not in by_course:
                by_course[code] = []
            by_course[code].append(section_to_json(s))

        for row in rows:
            row["sections"] = by_course.get(row["course_code"], [])

        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.post("/api/schedule-assist")
def schedule_assist():
    if not anthropic_api_key():
        return jsonify({"error": "Add your API key in the .env file first."}), 503

    body = request.get_json(silent=True) or {}
    msg = (body.get("message") or "").strip()
    if not msg:
        return jsonify({"error": "Please type a question."}), 400

    semester = (body.get("semester") or "").strip() or None

    try:
        from backend.schedule_assist import run_schedule_assistant

        return jsonify(run_schedule_assistant(msg, semester))
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
