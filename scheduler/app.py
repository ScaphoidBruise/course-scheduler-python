import json
import os
import uuid
from datetime import UTC, date, datetime, timedelta

from flask import Flask, Response, jsonify, render_template_string, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from db import (
    get_terms, get_subjects, get_modes, get_sections,
    get_sections_by_ids, get_all_courses, get_all_subjects,
    get_session_dates, get_course_detail,
    get_wishlist, add_wishlist_course, delete_wishlist_course,
    init_auth_tables, init_profile_tables, init_reference_tables, init_wishlist_tables, create_user, get_user_by_username,
    get_user_by_id, get_saved_schedule_ids, save_schedule_ids,
    get_saved_schedule_ids_by_term, get_user_setting, set_user_setting,
    get_scenarios, get_scenario, create_scenario, duplicate_scenario, rename_scenario,
    activate_scenario, delete_scenario, set_scenario_share_token, get_scenario_by_token,
    get_user_profile, update_user_profile, get_term_timeline,
    get_transcript_courses_for_term,
    get_academic_program_names,
    get_completed_course_codes, check_prerequisites, get_degree_progress,
    list_completed_overrides, add_completed_override, delete_completed_override,
    normalize_course_code,
    change_password, change_username, delete_user_cascade,
    account_summary, export_user_bundle,
    get_connection,
)
from conflict import sections_conflict
from transcript_pdf import parse_utpb_transcript_pdf, transcript_dict_to_json

app = Flask(__name__, static_folder="static")
app.config["SECRET_KEY"] = os.environ.get("SCHEDULER_SECRET_KEY", "dev-change-me")
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024

init_auth_tables()
init_profile_tables()
init_reference_tables()
init_wishlist_tables()


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_user_by_id(user_id)


def require_auth():
    user = current_user()
    if not user:
        return None, (jsonify({"error": "Authentication required"}), 401)
    return user, None


DAY_TO_ICS = {"M": "MO", "T": "TU", "W": "WE", "R": "TH", "F": "FR"}
DAY_TO_WEEKDAY = {"M": 0, "T": 1, "W": 2, "R": 3, "F": 4}
TERM_SEASON_ORDER = {"Spring": 0, "Summer": 1, "Fall": 2}
PLANNER_TARGET_KEY = "planner_credits_target"
DEFAULT_PLANNER_TARGET = 120


def _term_parts(label):
    bits = str(label or "").strip().split()
    if len(bits) != 2:
        return None, None
    season = bits[0].title()
    try:
        year = int(bits[1])
    except ValueError:
        return season, None
    return season, year


def _term_sort_key(label):
    season, year = _term_parts(label)
    return (year if year is not None else 9999, TERM_SEASON_ORDER.get(season, 99), str(label or ""))


def _next_term_label(label):
    season, year = _term_parts(label)
    if year is None or season not in TERM_SEASON_ORDER:
        return "Spring " + str(date.today().year)
    if season == "Spring":
        return f"Summer {year}"
    if season == "Summer":
        return f"Fall {year}"
    return f"Spring {year + 1}"


def _credit_value(raw):
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _format_credit_number(value):
    value = float(value or 0)
    if value.is_integer():
        return int(value)
    return round(value, 1)


def _planner_target_for_user(user_id):
    raw = get_user_setting(user_id, PLANNER_TARGET_KEY)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = float(DEFAULT_PLANNER_TARGET)
    if value <= 0:
        value = float(DEFAULT_PLANNER_TARGET)
    return value


def _schedule_term_label(value):
    text = " ".join(str(value or "").split())
    season, year = _term_parts(text)
    if season in TERM_SEASON_ORDER and year is not None:
        return f"{season} {year}"
    bits = text.split()
    if len(bits) == 2 and bits[0].isdigit():
        flipped = f"{bits[1].title()} {bits[0]}"
        season, year = _term_parts(flipped)
        if season in TERM_SEASON_ORDER and year is not None:
            return f"{season} {year}"
    return None


def _is_current_transcript_row(row):
    grade = str(row.get("grade") if row.get("grade") is not None else row.get("Grade") or "").strip().upper()
    if grade in {"IP", "I"}:
        return True
    if grade:
        return False
    try:
        attempted = float(row.get("attempted") or row.get("credits") or 0)
        earned = float(row.get("earned") or 0)
    except (TypeError, ValueError):
        return True
    return attempted > 0 and earned <= 0


def _current_transcript_courses(parsed):
    if not isinstance(parsed, dict):
        return None, []
    term = _schedule_term_label(parsed.get("last_term_label"))
    rows = [r for r in parsed.get("enrolled_courses") or [] if isinstance(r, dict)]
    if not rows:
        rows = [
            r for r in parsed.get("latest_term_courses") or []
            if isinstance(r, dict) and _is_current_transcript_row(r)
        ]
    if not rows:
        rows = [
            r for r in parsed.get("course_history") or []
            if isinstance(r, dict) and _is_current_transcript_row(r)
        ]
    if not term:
        for row in rows:
            term = _schedule_term_label(row.get("term"))
            if term:
                break
    if term:
        rows = [r for r in rows if not _schedule_term_label(r.get("term")) or _schedule_term_label(r.get("term")) == term]
    return term, rows


def _term_label_variants_for_schedule(term_label):
    out = {term_label}
    season, year = _term_parts(term_label)
    if season in TERM_SEASON_ORDER and year is not None:
        out.add(f"{year} {season}")
    return list(out)


def _seed_current_term_schedule_from_transcript(user_id, parsed):
    term, rows = _current_transcript_courses(parsed)
    if not term or not rows:
        return {"term": term, "added_count": 0, "course_codes": []}

    codes = []
    seen = set()
    for row in rows:
        code = normalize_course_code(row.get("course") or f"{row.get('subject', '')} {row.get('course_number', '')}")
        if code and code not in seen:
            seen.add(code)
            codes.append(code)
    if not codes:
        return {"term": term, "added_count": 0, "course_codes": []}

    existing_ids = get_saved_schedule_ids(user_id, term)
    existing_codes = {
        normalize_course_code(row.get("course_code"))
        for row in get_sections_by_ids(existing_ids, term_label=term)
        if row.get("course_code")
    }
    variants = _term_label_variants_for_schedule(term)
    term_placeholders = ",".join("?" for _ in variants)

    new_ids = []
    added_codes = []
    conn = get_connection()
    try:
        for code in codes:
            if code in existing_codes:
                continue
            compact = code.replace(" ", "")
            course = conn.execute(
                """
                SELECT id
                FROM courses
                WHERE REPLACE(UPPER(course_code), ' ', '') = ?
                ORDER BY id
                LIMIT 1
                """,
                (compact,),
            ).fetchone()
            if not course:
                continue
            sections = conn.execute(
                f"""
                SELECT id
                FROM sections
                WHERE term_label IN ({term_placeholders})
                  AND REPLACE(UPPER(course_code), ' ', '') = ?
                ORDER BY id
                """,
                [*variants, compact],
            ).fetchall()
            if len(sections) == 1:
                new_ids.append(int(sections[0]["id"]))
            else:
                new_ids.append(-int(course["id"]))
            added_codes.append(code)
    finally:
        conn.close()

    if new_ids:
        save_schedule_ids(user_id, term, existing_ids + new_ids)
    return {"term": term, "added_count": len(new_ids), "course_codes": added_codes}


def _sections_have_conflicts(sections):
    for i in range(len(sections)):
        for j in range(i + 1, len(sections)):
            if sections_conflict(sections[i], sections[j]):
                return True
    return False


def _estimate_graduation_label(terms, credits_completed, credits_target):
    remaining = float(credits_target or 0) - float(credits_completed or 0)
    if remaining <= 0:
        return "Completed"

    running = float(credits_completed or 0)
    planned_loads = []
    last_label = None
    fallback_label = None
    for term in sorted(terms, key=lambda t: _term_sort_key(t["label"])):
        fallback_label = term["label"]
        credits = float(term.get("credits") or 0)
        if credits > 0:
            planned_loads.append(credits)
            last_label = term["label"]
        running += credits
        if running >= credits_target:
            return term["label"]

    avg_load = sum(planned_loads) / len(planned_loads) if planned_loads else 15.0
    if avg_load <= 0:
        avg_load = 15.0
    cursor = last_label or fallback_label or f"Spring {date.today().year}"
    guard = 0
    while running < credits_target and guard < 24:
        cursor = _next_term_label(cursor)
        running += avg_load
        guard += 1
    return cursor


def _parse_days(days):
    out = []
    for ch in (days or "").upper():
        if ch in DAY_TO_ICS and ch not in out:
            out.append(ch)
    return out


def _parse_time_value(text):
    raw = (text or "").strip().upper()
    if not raw:
        return None
    raw = raw.replace(" ", "")
    suffix = None
    if raw.endswith("AM") or raw.endswith("PM"):
        suffix = raw[-2:]
        raw = raw[:-2]
    parts = raw.split(":")
    if len(parts) != 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return None
    if suffix == "PM" and hour != 12:
        hour += 12
    if suffix == "AM" and hour == 12:
        hour = 0
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return hour, minute


def _session_window_for_section(section, term_dates):
    start_raw = section.get("session_start_date")
    end_raw = section.get("session_end_date")
    if not start_raw or not end_raw:
        sec_session = (section.get("session") or "").strip()
        for row in term_dates:
            if (row.get("session") or "").strip() == sec_session:
                start_raw = row.get("session_start_date")
                end_raw = row.get("session_end_date")
                break
    if not start_raw or not end_raw:
        valid = [
            (r.get("session_start_date"), r.get("session_end_date"))
            for r in term_dates
            if r.get("session_start_date") and r.get("session_end_date")
        ]
        if valid:
            start_raw = min(v[0] for v in valid)
            end_raw = max(v[1] for v in valid)
    try:
        return date.fromisoformat(start_raw), date.fromisoformat(end_raw)
    except (TypeError, ValueError):
        return None, None


def _first_weekday_on_or_after(start_date, weekday):
    offset = (weekday - start_date.weekday()) % 7
    return start_date + timedelta(days=offset)


def _ics_escape(value):
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fold_ics_line(line):
    if len(line) <= 75:
        return [line]
    out = []
    rest = line
    while len(rest) > 75:
        out.append(rest[:75])
        rest = " " + rest[75:]
    out.append(rest)
    return out


def _build_scenario_ics(scenario, sections):
    term_dates = get_session_dates(scenario["term_label"])
    now = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//UTPB Scheduler//Scenario Export//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_ics_escape(scenario['term_label'] + ' - ' + scenario['name'])}",
    ]
    for sec in sections:
        days = _parse_days(sec.get("days"))
        start_time = _parse_time_value(sec.get("start_time"))
        end_time = _parse_time_value(sec.get("end_time"))
        if not days or not start_time or not end_time:
            continue
        session_start, session_end = _session_window_for_section(sec, term_dates)
        if not session_start or not session_end:
            continue
        for day in days:
            first_day = _first_weekday_on_or_after(session_start, DAY_TO_WEEKDAY[day])
            if first_day > session_end:
                continue
            dt_start = datetime.combine(first_day, datetime.min.time()).replace(
                hour=start_time[0],
                minute=start_time[1],
            )
            dt_end = datetime.combine(first_day, datetime.min.time()).replace(
                hour=end_time[0],
                minute=end_time[1],
            )
            summary = f"{sec.get('course_code') or 'Course'} {sec.get('section_code') or ''}".strip()
            description = sec.get("course_name") or ""
            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:{uuid.uuid4().hex}@utpb-scheduler",
                    f"DTSTAMP:{now}",
                    f"DTSTART:{dt_start.strftime('%Y%m%dT%H%M%S')}",
                    f"DTEND:{dt_end.strftime('%Y%m%dT%H%M%S')}",
                    f"RRULE:FREQ=WEEKLY;UNTIL:{session_end.strftime('%Y%m%d')}T235959;BYDAY={DAY_TO_ICS[day]}",
                    f"SUMMARY:{_ics_escape(summary)}",
                    f"LOCATION:{_ics_escape(sec.get('location') or '')}",
                    f"DESCRIPTION:{_ics_escape(description)}",
                    "END:VEVENT",
                ]
            )
    lines.append("END:VCALENDAR")
    folded = []
    for line in lines:
        folded.extend(_fold_ics_line(line))
    return "\r\n".join(folded) + "\r\n"


@app.route("/")
def schedule_page():
    return send_from_directory("pages", "schedule.html")

@app.route("/catalog")
def catalog_page():
    return send_from_directory("pages", "catalog.html")

@app.route("/about")
def about_page():
    return send_from_directory("pages", "about.html")

@app.route("/help")
def help_page():
    return send_from_directory("pages", "help.html")

@app.route("/account")
def account_page():
    return send_from_directory("pages", "account.html")

@app.route("/profile")
def profile_page():
    return send_from_directory("pages", "profile.html")


@app.route("/planner")
def planner_page():
    return send_from_directory("pages", "planner.html")


@app.route("/progress")
def progress_page():
    return send_from_directory("pages", "progress.html")


@app.route("/share/<token>")
def share_page(token):
    scenario = get_scenario_by_token(token)
    if not scenario:
        return "Shared schedule not found.", 404
    ids = get_saved_schedule_ids(scenario["user_id"], scenario["term_label"], scenario["id"])
    sections = get_sections_by_ids(ids, term_label=scenario["term_label"])
    share_data = {
        "scenario": scenario,
        "ids": ids,
        "sections": sections,
    }
    return render_template_string(
        """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Shared Schedule - UTPB Scheduler</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="/static/style.css" rel="stylesheet">
</head>
<body class="share-page">
    <nav class="navbar navbar-expand-lg main-nav">
        <div class="container-fluid px-4">
            <a class="navbar-brand" href="/"><span class="brand-accent">UTPB</span> Scheduler</a>
            <span class="navbar-text text-light small">Read-only shared schedule</span>
        </div>
    </nav>
    <div class="content-area">
        <div class="container-fluid px-4 py-3">
            <div id="alertBox"></div>
            <div id="summaryBar" class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-2">
                <div>
                    <span class="fw-bold" id="termLabel"></span>
                    <span class="mx-1 text-muted">&middot;</span>
                    <span class="fw-bold" id="sectionCount">0</span>
                    <span class="text-muted small">sections</span>
                    <span class="mx-1 text-muted">&middot;</span>
                    <span class="fw-bold" id="creditCount">0.0</span>
                    <span class="text-muted small">credit hrs</span>
                    <span id="conflictBadge" class="mx-1 d-none">
                        <span class="mx-1 text-muted">&middot;</span>
                        <span class="text-danger fw-bold small" id="conflictText"></span>
                    </span>
                </div>
                <span class="badge rounded-pill bg-light text-muted border">Read only</span>
            </div>
            <div class="grid-wrapper">
                <div class="weekly-grid" id="weeklyGrid"></div>
            </div>
            <div id="addedTableWrap" class="mt-3 d-none">
                <h6>Added Sections</h6>
                <div class="table-responsive">
                    <table class="table table-sm section-table align-middle">
                        <thead>
                            <tr>
                                <th></th><th>Course</th><th>Title</th><th>&sect;</th>
                                <th>Session</th><th>Dates</th><th>Days</th><th>Time</th>
                                <th>Location</th><th>Mode</th><th>Hrs</th><th class="schedule-edit-col"></th>
                            </tr>
                        </thead>
                        <tbody id="addedBody"></tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
    <script>
        window.SCHEDULE_SHARE_DATA = {{ share_json|safe }};
    </script>
    <script src="/static/schedule.js"></script>
</body>
</html>
        """,
        share_json=json.dumps(share_data).replace("</", "<\\/"),
    )


@app.route("/api/terms")
def api_terms():
    return jsonify(get_terms())


@app.route("/api/term-timeline")
def api_term_timeline():
    user, auth_error = require_auth()
    if auth_error:
        return auth_error
    try:
        return jsonify(get_term_timeline(user["id"]))
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": "Could not build term list.", "detail": str(exc)}), 500


@app.route("/api/planner-overview")
def api_planner_overview():
    user, auth_error = require_auth()
    if auth_error:
        return auth_error

    try:
        timeline = get_term_timeline(user["id"])
        saved_by_term = get_saved_schedule_ids_by_term(user["id"])
        saved_by_label = {str(k): v for k, v in saved_by_term.items()}
        entries_by_label = {}

        for item in timeline.get("past_terms") or []:
            if item.get("has_saved_schedule"):
                label = item.get("label")
                entries_by_label[label] = dict(item, is_past=True)

        for item in timeline.get("terms") or []:
            label = item.get("label")
            entries_by_label[label] = dict(item, is_past=False)

        for label in saved_by_label:
            if label not in entries_by_label:
                season, year = _term_parts(label)
                entries_by_label[label] = {
                    "label": label,
                    "year": year,
                    "season": season,
                    "is_past": _term_sort_key(label) < _term_sort_key(timeline.get("scheduling_floor_label")),
                }

        terms = []
        current_label = timeline.get("current_term") or timeline.get("scheduling_floor_label")
        for label, entry in sorted(entries_by_label.items(), key=lambda kv: _term_sort_key(kv[0])):
            section_ids = saved_by_label.get(label, [])
            sections = get_sections_by_ids(section_ids, term_label=label)
            credits = sum(_credit_value(s.get("credits")) for s in sections)
            season, year = _term_parts(label)
            terms.append(
                {
                    "label": label,
                    "year": entry.get("year") if entry.get("year") is not None else year,
                    "season": entry.get("season") or season,
                    "is_past": bool(entry.get("is_past")),
                    "is_current": bool(current_label and label == current_label),
                    "section_count": len(sections),
                    "credits": _format_credit_number(credits),
                    "has_conflicts": _sections_have_conflicts(sections),
                    "sections": sections,
                }
            )

        prof = get_user_profile(user["id"])
        credits_completed = _credit_value(prof.get("credits_earned"))
        credits_planned = sum(float(t.get("credits") or 0) for t in terms)
        credits_target = _planner_target_for_user(user["id"])
        return jsonify(
            {
                "terms": terms,
                "totals": {
                    "credits_planned": _format_credit_number(credits_planned),
                    "credits_completed": _format_credit_number(credits_completed),
                    "credits_target": _format_credit_number(credits_target),
                    "expected_graduation_label": _estimate_graduation_label(
                        terms,
                        credits_completed,
                        credits_target,
                    ),
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": "Could not build planner overview.", "detail": str(exc)}), 500


@app.route("/api/planner-target", methods=["GET", "POST"])
def api_planner_target():
    user, auth_error = require_auth()
    if auth_error:
        return auth_error

    if request.method == "GET":
        return jsonify({"credits_target": _format_credit_number(_planner_target_for_user(user["id"]))})

    payload = request.get_json(silent=True) or {}
    try:
        credits_target = float(payload.get("credits_target"))
    except (TypeError, ValueError):
        return jsonify({"error": "credits_target must be a number"}), 400
    if credits_target <= 0 or credits_target > 300:
        return jsonify({"error": "credits_target must be between 1 and 300"}), 400
    set_user_setting(user["id"], PLANNER_TARGET_KEY, str(_format_credit_number(credits_target)))
    return jsonify({"ok": True, "credits_target": _format_credit_number(credits_target)})


@app.route("/api/transcript-term")
def api_transcript_term():
    user, auth_error = require_auth()
    if auth_error:
        return auth_error
    term = request.args.get("term") or ""
    return jsonify(get_transcript_courses_for_term(user["id"], term))

@app.route("/api/subjects")
def api_subjects():
    term = request.args.get("term")
    return jsonify(get_subjects(term))

@app.route("/api/modes")
def api_modes():
    term = request.args.get("term")
    return jsonify(get_modes(term))

@app.route("/api/sections")
def api_sections():
    term = request.args.get("term", "")
    if not term:
        return jsonify([])
    return jsonify(get_sections(
        term,
        subject_code=request.args.get("subject") or None,
        mode=request.args.get("mode") or None,
        level=request.args.get("level") or None,
        search=request.args.get("search") or None,
    ))

@app.route("/api/sections/batch")
def api_sections_batch():
    raw = request.args.get("ids", "")
    if not raw:
        return jsonify([])
    try:
        ids = [int(x) for x in raw.split(",") if x.strip()]
    except ValueError:
        return jsonify([])
    term = (request.args.get("term") or "").strip()
    return jsonify(get_sections_by_ids(ids, term_label=term or None))

@app.route("/api/courses")
def api_courses():
    return jsonify(get_all_courses(
        subject_code=request.args.get("subject") or None,
        search=request.args.get("search") or None,
        level=request.args.get("level") or None,
        term=request.args.get("term") or None,
    ))


@app.route("/api/courses/<int:course_id>")
def api_course_detail(course_id):
    course = get_course_detail(course_id)
    if not course:
        return jsonify({"error": "Course not found"}), 404
    return jsonify(course)


@app.route("/api/wishlist")
def api_wishlist():
    user, auth_error = require_auth()
    if auth_error:
        return auth_error
    return jsonify(get_wishlist(user["id"]))


@app.route("/api/wishlist", methods=["POST"])
def api_add_wishlist():
    user, auth_error = require_auth()
    if auth_error:
        return auth_error

    payload = request.get_json(silent=True) or {}
    try:
        course_id = int(payload.get("course_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "course_id is required"}), 400

    ok = add_wishlist_course(
        user["id"],
        course_id,
        notes=payload.get("notes"),
        priority=payload.get("priority", 0),
    )
    if not ok:
        return jsonify({"error": "Course not found"}), 404
    return jsonify({"ok": True, "wishlist": get_wishlist(user["id"])})


@app.route("/api/wishlist/<int:course_id>", methods=["DELETE"])
def api_delete_wishlist(course_id):
    user, auth_error = require_auth()
    if auth_error:
        return auth_error
    delete_wishlist_course(user["id"], course_id)
    return jsonify({"ok": True, "wishlist": get_wishlist(user["id"])})

@app.route("/api/course-subjects")
def api_course_subjects():
    return jsonify(get_all_subjects())

@app.route("/api/session-dates")
def api_session_dates():
    term = request.args.get("term", "")
    if not term:
        return jsonify([])
    return jsonify(get_session_dates(term))


@app.route("/api/academic-programs")
def api_academic_programs():
    return jsonify(get_academic_program_names())


@app.route("/api/me")
def api_me():
    user = current_user()
    return jsonify({"authenticated": bool(user), "user": user})


@app.route("/api/profile")
def api_profile():
    user, auth_error = require_auth()
    if auth_error:
        return auth_error

    prof = get_user_profile(user["id"])
    return jsonify(
        {
            "user": user,
            "profile": {
                "major": prof["major"],
                "minor": prof["minor"],
                "cumulative_gpa": prof["cumulative_gpa"],
                "last_term_gpa": prof["last_term_gpa"],
                "credits_attempted": prof["credits_attempted"],
                "credits_earned": prof["credits_earned"],
                "transcript_original_name": prof["transcript_original_name"],
                "has_transcript": bool(prof.get("transcript_parsed_json")),
                "updated_at": prof.get("updated_at"),
                "transcript_parsed": prof.get("transcript_parsed_json"),
            },
        }
    )


@app.route("/api/profile/info", methods=["POST"])
def api_profile_info():
    user, auth_error = require_auth()
    if auth_error:
        return auth_error

    payload = request.get_json(silent=True) or {}
    major = (payload.get("major") or "").strip()
    minor = (payload.get("minor") or "").strip()

    update_user_profile(
        user["id"],
        major=major or None,
        minor=minor or None,
    )
    return jsonify({"ok": True})


@app.route("/api/profile/transcript", methods=["POST"])
def api_profile_transcript():
    user, auth_error = require_auth()
    if auth_error:
        return auth_error

    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify({"error": "No file uploaded."}), 400
    if not upload.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Please upload a PDF transcript."}), 400

    raw = upload.read()
    if not raw:
        return jsonify({"error": "Empty file."}), 400

    try:
        parsed = parse_utpb_transcript_pdf(raw)
        parsed_json = transcript_dict_to_json(parsed)
    except Exception as exc:
        return jsonify({"error": f"Could not process transcript: {exc}"}), 500
    orig_name = secure_filename(upload.filename) or "transcript.pdf"
    updates = {
        "transcript_original_name": orig_name,
        "transcript_parsed_json": parsed_json,
    }
    prof = get_user_profile(user["id"])
    if parsed.get("major") and not (prof.get("major") or "").strip():
        updates["major"] = parsed["major"]
    if parsed.get("minor") and not (prof.get("minor") or "").strip():
        updates["minor"] = parsed["minor"]
    update_user_profile(user["id"], **updates)
    seeded_schedule = _seed_current_term_schedule_from_transcript(user["id"], parsed)
    return jsonify({"ok": True, "parsed": parsed, "seeded_schedule": seeded_schedule})


@app.route("/api/degree-progress")
def api_degree_progress():
    user, auth_error = require_auth()
    if auth_error:
        return auth_error
    return jsonify(get_degree_progress(user["id"]))


@app.route("/api/degree-progress/overview")
def api_degree_progress_overview():
    user, auth_error = require_auth()
    if auth_error:
        return auth_error

    progress = get_degree_progress(user["id"])
    profile = get_user_profile(user["id"])

    completed_rows = progress.get("completed") or []
    credits_completed = 0.0
    for row in completed_rows:
        credits_completed += _credit_value(row.get("attempted") or row.get("earned"))
    if credits_completed <= 0:
        credits_completed = _credit_value(profile.get("credits_earned"))

    credits_target = _planner_target_for_user(user["id"])
    if credits_target <= 0:
        credits_target = float(DEFAULT_PLANNER_TARGET)

    remaining_buckets = progress.get("remaining_by_typical_term") or {}
    courses_remaining_count = 0
    for season in ("Spring", "Summer", "Fall", "Unscheduled"):
        bucket = remaining_buckets.get(season) or []
        courses_remaining_count += len(bucket)

    percent = 0.0
    if credits_target > 0:
        percent = (float(credits_completed) / float(credits_target)) * 100.0
    if percent < 0:
        percent = 0.0
    if percent > 100:
        percent = 100.0

    scope_subjects: list[str] = []
    seen: set[str] = set()
    for row in completed_rows:
        subj = (row.get("subject") or "").upper()
        if subj and subj not in seen:
            seen.add(subj)
            scope_subjects.append(subj)
    if not scope_subjects:
        for season in ("Spring", "Summer", "Fall", "Unscheduled"):
            for row in remaining_buckets.get(season) or []:
                subj = (row.get("subject_code") or "").upper()
                if subj and subj not in seen:
                    seen.add(subj)
                    scope_subjects.append(subj)

    has_transcript = bool(profile.get("transcript_parsed_json"))

    return jsonify(
        {
            "credits_completed": _format_credit_number(credits_completed),
            "credits_target": int(round(float(credits_target))),
            "percent_complete": round(percent, 1),
            "courses_remaining_count": courses_remaining_count,
            "scope_subjects": scope_subjects,
            "has_transcript": has_transcript,
            "major": profile.get("major"),
            "minor": profile.get("minor"),
        }
    )


@app.route("/api/prereq-check")
def api_prereq_check():
    user, auth_error = require_auth()
    if auth_error:
        return auth_error
    completed = get_completed_course_codes(user["id"])
    raw_codes = request.args.get("codes")
    if raw_codes:
        out = {}
        for code in [c.strip() for c in raw_codes.split(",") if c.strip()]:
            out[normalize_course_code(code)] = check_prerequisites(code, completed)
        return jsonify(out)
    code = request.args.get("course_code") or request.args.get("code") or ""
    if not code.strip():
        return jsonify({"error": "course_code is required"}), 400
    return jsonify(check_prerequisites(code, completed))


@app.route("/api/completed-overrides")
def api_completed_overrides():
    user, auth_error = require_auth()
    if auth_error:
        return auth_error
    return jsonify(list_completed_overrides(user["id"]))


@app.route("/api/completed-overrides", methods=["POST"])
def api_add_completed_override():
    user, auth_error = require_auth()
    if auth_error:
        return auth_error
    payload = request.get_json(silent=True) or {}
    course_code = (payload.get("course_code") or "").strip()
    grade = (payload.get("grade") or "").strip() or None
    if not course_code:
        return jsonify({"error": "course_code is required"}), 400
    try:
        row = add_completed_override(user["id"], course_code, grade)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "override": row}), 201


@app.route("/api/completed-overrides/<int:override_id>", methods=["DELETE"])
def api_delete_completed_override(override_id):
    user, auth_error = require_auth()
    if auth_error:
        return auth_error
    if not delete_completed_override(user["id"], override_id):
        return jsonify({"error": "Override not found"}), 404
    return jsonify({"ok": True})


@app.route("/api/register", methods=["POST"])
def api_register():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip().lower()
    password = payload.get("password") or ""
    confirm_password = payload.get("confirm_password") or ""

    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters."}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400
    if password != confirm_password:
        return jsonify({"error": "Passwords do not match."}), 400

    user_id = create_user(username, generate_password_hash(password))
    if user_id is None:
        return jsonify({"error": "That username is already taken."}), 409

    session["user_id"] = user_id
    user = get_user_by_id(user_id)
    return jsonify({"ok": True, "user": user}), 201


@app.route("/api/login", methods=["POST"])
def api_login():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip().lower()
    password = payload.get("password") or ""

    user = get_user_by_username(username)
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid username or password."}), 401

    session["user_id"] = user["id"]
    return jsonify({"ok": True, "user": get_user_by_id(user["id"])})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/account/summary")
def api_account_summary():
    user, auth_error = require_auth()
    if auth_error:
        return auth_error
    summary = account_summary(user["id"])
    if not summary:
        return jsonify({"error": "User not found"}), 404
    return jsonify(summary)


def _user_with_password_hash(user_id):
    """Fetch the password_hash for a user (not returned by /api/me)."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id, username, password_hash FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


@app.route("/api/account/change-password", methods=["POST"])
def api_account_change_password():
    user, auth_error = require_auth()
    if auth_error:
        return auth_error
    payload = request.get_json(silent=True) or {}
    current_password = payload.get("current_password") or ""
    new_password = payload.get("new_password") or ""
    confirm_password = payload.get("confirm_password") or ""

    user_with_hash = _user_with_password_hash(user["id"])
    if not user_with_hash or not check_password_hash(user_with_hash["password_hash"], current_password):
        return jsonify({"error": "Current password is incorrect."}), 401
    if len(new_password) < 8:
        return jsonify({"error": "New password must be at least 8 characters."}), 400
    if new_password != confirm_password:
        return jsonify({"error": "New passwords do not match."}), 400

    change_password(user["id"], generate_password_hash(new_password))
    return jsonify({"ok": True})


@app.route("/api/account/change-username", methods=["POST"])
def api_account_change_username():
    user, auth_error = require_auth()
    if auth_error:
        return auth_error
    payload = request.get_json(silent=True) or {}
    current_password = payload.get("current_password") or ""
    new_username = (payload.get("new_username") or "").strip().lower()

    user_with_hash = _user_with_password_hash(user["id"])
    if not user_with_hash or not check_password_hash(user_with_hash["password_hash"], current_password):
        return jsonify({"error": "Current password is incorrect."}), 401
    if len(new_username) < 3:
        return jsonify({"error": "Username must be at least 3 characters."}), 400
    if new_username == user["username"]:
        return jsonify({"ok": True, "user": user})

    if not change_username(user["id"], new_username):
        return jsonify({"error": "That username is already taken."}), 409

    refreshed = get_user_by_id(user["id"])
    return jsonify({"ok": True, "user": refreshed})


@app.route("/api/account/delete", methods=["POST"])
def api_account_delete():
    user, auth_error = require_auth()
    if auth_error:
        return auth_error
    payload = request.get_json(silent=True) or {}
    current_password = payload.get("current_password") or ""
    confirm = payload.get("confirm") or ""

    if confirm != "DELETE":
        return jsonify({"error": 'Type "DELETE" to confirm.'}), 400

    user_with_hash = _user_with_password_hash(user["id"])
    if not user_with_hash or not check_password_hash(user_with_hash["password_hash"], current_password):
        return jsonify({"error": "Current password is incorrect."}), 401

    delete_user_cascade(user["id"])
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/account/export")
def api_account_export():
    user, auth_error = require_auth()
    if auth_error:
        return auth_error
    bundle = export_user_bundle(user["id"])
    if not bundle:
        return jsonify({"error": "User not found"}), 404
    today = date.today().strftime("%Y%m%d")
    filename = f'utpb-export-{user["username"]}-{today}.json'
    body = json.dumps(bundle, default=str, indent=2)
    return Response(
        body,
        mimetype="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route("/api/scenarios")
def api_list_scenarios():
    user, auth_error = require_auth()
    if auth_error:
        return auth_error
    term = request.args.get("term", "").strip()
    if not term:
        return jsonify({"error": "term is required"}), 400
    return jsonify({"term": term, "scenarios": get_scenarios(user["id"], term)})


@app.route("/api/scenarios", methods=["POST"])
def api_create_scenario():
    user, auth_error = require_auth()
    if auth_error:
        return auth_error
    payload = request.get_json(silent=True) or {}
    term = (payload.get("term") or "").strip()
    name = (payload.get("name") or "").strip()
    if not term:
        return jsonify({"error": "term is required"}), 400
    scenario = create_scenario(user["id"], term, name or "New scenario")
    return jsonify({"ok": True, "scenario": scenario}), 201


@app.route("/api/scenarios/<int:scenario_id>/duplicate", methods=["POST"])
def api_duplicate_scenario(scenario_id):
    user, auth_error = require_auth()
    if auth_error:
        return auth_error
    payload = request.get_json(silent=True) or {}
    scenario = duplicate_scenario(user["id"], scenario_id, payload.get("name"))
    if not scenario:
        return jsonify({"error": "Scenario not found"}), 404
    return jsonify({"ok": True, "scenario": scenario}), 201


@app.route("/api/scenarios/<int:scenario_id>/rename", methods=["POST"])
def api_rename_scenario(scenario_id):
    user, auth_error = require_auth()
    if auth_error:
        return auth_error
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    scenario = rename_scenario(user["id"], scenario_id, name)
    if not scenario:
        return jsonify({"error": "Scenario not found"}), 404
    return jsonify({"ok": True, "scenario": scenario})


@app.route("/api/scenarios/<int:scenario_id>/activate", methods=["POST"])
def api_activate_scenario(scenario_id):
    user, auth_error = require_auth()
    if auth_error:
        return auth_error
    scenario = activate_scenario(user["id"], scenario_id)
    if not scenario:
        return jsonify({"error": "Scenario not found"}), 404
    return jsonify({"ok": True, "scenario": scenario})


@app.route("/api/scenarios/<int:scenario_id>", methods=["DELETE"])
def api_delete_scenario(scenario_id):
    user, auth_error = require_auth()
    if auth_error:
        return auth_error
    active = delete_scenario(user["id"], scenario_id)
    if not active:
        return jsonify({"error": "Scenario not found"}), 404
    return jsonify({"ok": True, "active_scenario": active})


@app.route("/api/scenarios/<int:scenario_id>/ics")
def api_scenario_ics(scenario_id):
    user, auth_error = require_auth()
    if auth_error:
        return auth_error
    scenario = get_scenario(user["id"], scenario_id)
    if not scenario:
        return jsonify({"error": "Scenario not found"}), 404
    ids = get_saved_schedule_ids(user["id"], scenario["term_label"], scenario_id)
    sections = get_sections_by_ids(ids, term_label=scenario["term_label"])
    ics = _build_scenario_ics(scenario, sections)
    filename = f"{scenario['term_label']}-{scenario['name']}.ics".replace(" ", "-")
    return Response(
        ics,
        mimetype="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route("/api/scenarios/<int:scenario_id>/share", methods=["POST"])
def api_share_scenario(scenario_id):
    user, auth_error = require_auth()
    if auth_error:
        return auth_error
    scenario = set_scenario_share_token(user["id"], scenario_id, uuid.uuid4().hex)
    if not scenario:
        return jsonify({"error": "Scenario not found"}), 404
    return jsonify(
        {
            "ok": True,
            "share_token": scenario["share_token"],
            "url": f"/share/{scenario['share_token']}",
        }
    )


@app.route("/api/my-schedule")
def api_get_my_schedule():
    user, auth_error = require_auth()
    if auth_error:
        return auth_error

    term = request.args.get("term", "").strip()
    if not term:
        return jsonify({"error": "term is required"}), 400
    scenario_id = request.args.get("scenario_id")
    if scenario_id:
        try:
            scenario_id = int(scenario_id)
        except ValueError:
            return jsonify({"error": "scenario_id must be an integer"}), 400
        scenario = get_scenario(user["id"], scenario_id)
        if not scenario or scenario["term_label"] != term:
            return jsonify({"error": "Scenario not found"}), 404
    else:
        scenario_id = None

    return jsonify({"term": term, "ids": get_saved_schedule_ids(user["id"], term, scenario_id)})


@app.route("/api/my-schedule", methods=["POST"])
def api_save_my_schedule():
    user, auth_error = require_auth()
    if auth_error:
        return auth_error

    payload = request.get_json(silent=True) or {}
    term = (payload.get("term") or "").strip()
    ids = payload.get("ids")

    if not term:
        return jsonify({"error": "term is required"}), 400
    if not isinstance(ids, list):
        return jsonify({"error": "ids must be a list"}), 400
    scenario_id = payload.get("scenario_id")
    if scenario_id is not None:
        try:
            scenario_id = int(scenario_id)
        except (TypeError, ValueError):
            return jsonify({"error": "scenario_id must be an integer"}), 400
        scenario = get_scenario(user["id"], scenario_id)
        if not scenario or scenario["term_label"] != term:
            return jsonify({"error": "Scenario not found"}), 404

    clean_ids = []
    for value in ids:
        try:
            clean_ids.append(int(value))
        except (TypeError, ValueError):
            return jsonify({"error": "ids must contain integers"}), 400

    save_schedule_ids(user["id"], term, clean_ids, scenario_id)
    return jsonify({"ok": True})


if __name__ == "__main__":
    _debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    _port = int(os.environ.get("PORT", "5000"))
    app.run(debug=_debug, port=_port)
