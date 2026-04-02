from flask import Flask, jsonify, request, send_from_directory

from db import (
    get_terms, get_subjects, get_modes, get_sections,
    get_sections_by_ids, get_all_courses, get_all_subjects,
    get_session_dates,
)

app = Flask(__name__, static_folder="static")


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


if __name__ == "__main__":
    app.run(debug=True, port=5000)
