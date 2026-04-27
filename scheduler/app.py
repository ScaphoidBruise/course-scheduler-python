import os

from flask import Flask, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from db import (
    get_terms, get_subjects, get_modes, get_sections,
    get_sections_by_ids, get_all_courses, get_all_subjects,
    get_session_dates,
    init_auth_tables, init_profile_tables, create_user, get_user_by_username,
    get_user_by_id, get_saved_schedule_ids, save_schedule_ids,
    get_user_profile, update_user_profile,
)
from transcript_pdf import parse_utpb_transcript_pdf, transcript_dict_to_json

app = Flask(__name__, static_folder="static")
app.config["SECRET_KEY"] = os.environ.get("SCHEDULER_SECRET_KEY", "dev-change-me")
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024

init_auth_tables()
init_profile_tables()


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


@app.route("/api/terms")
def api_terms():
    return jsonify(get_terms())

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
    return jsonify(get_sections_by_ids(ids))

@app.route("/api/courses")
def api_courses():
    return jsonify(get_all_courses(
        subject_code=request.args.get("subject") or None,
        search=request.args.get("search") or None,
    ))

@app.route("/api/course-subjects")
def api_course_subjects():
    return jsonify(get_all_subjects())

@app.route("/api/session-dates")
def api_session_dates():
    term = request.args.get("term", "")
    if not term:
        return jsonify([])
    return jsonify(get_session_dates(term))


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
    return jsonify({"ok": True, "parsed": parsed})


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


@app.route("/api/my-schedule")
def api_get_my_schedule():
    user, auth_error = require_auth()
    if auth_error:
        return auth_error

    term = request.args.get("term", "").strip()
    if not term:
        return jsonify({"error": "term is required"}), 400

    return jsonify({"term": term, "ids": get_saved_schedule_ids(user["id"], term)})


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

    clean_ids = []
    for value in ids:
        try:
            clean_ids.append(int(value))
        except (TypeError, ValueError):
            return jsonify({"error": "ids must contain integers"}), 400

    save_schedule_ids(user["id"], term, clean_ids)
    return jsonify({"ok": True})


if __name__ == "__main__":
    _debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    _port = int(os.environ.get("PORT", "5000"))
    app.run(debug=_debug, port=_port)
