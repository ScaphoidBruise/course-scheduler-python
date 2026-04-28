# UTPB Academic Scheduler

A full-stack Python web application that helps University of Texas Permian Basin (UTPB) students plan their academic career. It scrapes live course catalog and section data, parses unofficial transcripts, checks prerequisites and schedule conflicts, tracks degree progress against scraped program requirements, and provides AI-powered planning advice via the Anthropic Messages API.

---

## Table of Contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [Object-Oriented Design](#object-oriented-design)
4. [Installation](#installation)
5. [Configuration](#configuration)
6. [Populating the Database](#populating-the-database)
7. [Running the Application](#running-the-application)
8. [Running Tests](#running-tests)
9. [Project Structure](#project-structure)
10. [Database Schema](#database-schema)
11. [API Overview](#api-overview)
12. [Team](#team)

---

## Features

- **Live Schedule Builder** — Search and filter sections by term, subject, session, and mode; add them to a weekly conflict-aware grid.
- **Conflict Detection** — Identifies overlapping class times including half-semester sessions (8W1/8W2); mirrors browser-side rules on the server.
- **Transcript Import** — Parses unofficial UTPB PDF transcripts in memory (no file stored on disk) to extract GPA, credit history, enrolled courses, and major/minor.
- **Prerequisite Checking** — Flags missing prerequisites using completed transcript courses plus manual completion overrides.
- **Degree Progress** — Matches the student's major to scraped program requirements and categorises courses as completed, in-progress, or remaining.
- **Multi-Scenario Planning** — Each term supports named schedule scenarios; the Planner page rolls all saved terms into a graduation timeline with credit projections.
- **AI Planner Advisor** — Sends a compact server-side profile summary to the Anthropic Messages API for personalised advice; falls back to rule-based tips when no key is configured.
- **Account Self-Service** — Change password/username, export all user data as JSON, or permanently delete an account.
- **ICS Export** — Download a `.ics` calendar file for any saved schedule.

---

## Architecture

```
Browser (HTML + vanilla JS/CSS)
        │  REST JSON API
        ▼
Flask application (scheduler/app.py)
  ├── Auth & session management       (werkzeug, Flask sessions)
  ├── Schedule & conflict endpoints   (conflict.py)
  ├── Transcript parsing endpoints    (transcript_pdf.py)
  ├── Degree-progress endpoints       (db.py + program_requirements scraper)
  ├── AI planner endpoint             (Anthropic Messages API via urllib)
  └── SQLite data layer               (db.py → data/courses.db)

Scrapers (scrapers/)  ← run separately, populate data/courses.db
  ├── catalog.py          UTPB SmartCatalog → courses table
  ├── program_requirements.py  SmartCatalog Programs of Study → requirements tables
  ├── infer_terms.py      Falcon Maps PDFs → term_infered column
  ├── sections.py         Registrar schedule → sections table
  └── session_dates.py    Academic calendar → session_calendar table
```

The frontend uses no frameworks — every page is a plain HTML file that calls the JSON API with `fetch`.

---

## Object-Oriented Design

The project uses Python dataclasses and classes throughout. The three primary interacting domain model classes live in `scheduler/models.py`:

| Class | Responsibility |
|---|---|
| `CourseSection` | Immutable snapshot of a section's scheduling data; wraps a DB row; exposes `is_online`, `start_minutes`, `end_minutes`, and `as_dict()`. |
| `ConflictReport` | Returned by `TermSchedule.add()`; holds the new section and every conflicting `CourseSection`; exposes `has_conflicts` and `conflicting_codes`. |
| `TermSchedule` | Manages a collection of `CourseSection` objects for one term; calls `conflict.py` helpers internally; supports `add`, `remove`, `clear`, `total_credits`, and `conflicts_in_schedule()`. |

The scrapers module also uses four dataclasses (`ProgramRef`, `RequirementCourse`, `RequirementBlock`, `ProgramRequirements`) in `scrapers/program_requirements.py` for hierarchical degree-requirement modeling.

---

## Installation

**Prerequisites:** Python 3.11 or later.

```bash
# 1. Clone or download the repository
git clone <repo-url>
cd project

# 2. Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

`requirements.txt` pins:

```
flask>=3.1
pypdf>=6.9
werkzeug>=3.0
pytest>=7.0
pytest-cov>=4.0
```

---

## Configuration

Copy `.env.example` to `.env` and fill in values:

```bash
copy .env.example .env   # Windows
cp .env.example .env     # macOS / Linux
```

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Optional | Enables the AI Planner Advisor. Without it the endpoint returns rule-based advice. |
| `ANTHROPIC_MODEL` | Optional | Defaults to `claude-haiku-4-5-20251001`. |
| `SCHEDULER_SECRET_KEY` | Optional | Flask session key. Auto-generated at startup if omitted; set a fixed value for multi-process/production deployments. |

---

## Populating the Database

Run all scrapers in order from the **project root**:

```bash
# Full refresh (catalog + infer-terms + sections + session-dates)
python -m scrapers sync

# Individual steps
python -m scrapers catalog --all-subjects
python -m scrapers program-requirements --all-programs
python -m scrapers infer-terms
python -m scrapers sections
python -m scrapers session-dates
```

All commands default to `data/courses.db`; override with `--db PATH`. Add `--quiet` to reduce log output. Use `--backup-db` with the catalog scraper to snapshot the database file before overwriting course rows.

The `program-requirements` scraper supports a dry-run review mode:

```bash
python -m scrapers program-requirements --dry-run --output-json data/requirements_review.json
```

---

## Running the Application

```bash
cd scheduler

# Windows
set FLASK_DEBUG=1
python app.py

# macOS / Linux
FLASK_DEBUG=1 python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in a browser.

Set `PORT` to change the port. Set `FLASK_DEBUG=0` (or omit `FLASK_DEBUG`) for a non-debug run.

### Demo walkthrough

1. **Schedule** — pick a term, search sections, add to grid; observe conflict and prerequisite warnings.
2. **Profile** — upload an unofficial UTPB transcript PDF; view parsed GPA and credit summary.
3. **Progress** — review completed, in-progress, and remaining degree requirements; mark transfer equivalencies.
4. **Planner** — view all saved terms on a graduation timeline; interact with the AI Planner Advisor.
5. **Export** — download an `.ics` calendar file from the Schedule page.

---

## Running Tests

```bash
# From the project root — run the full test suite
python -m pytest tests/ -v

# With code coverage (≥ 80 % required)
python -m pytest tests/ --cov=scheduler --cov=scrapers --cov-config=.coveragerc --cov-report=term-missing
```

Coverage is configured in `.coveragerc` to measure `scheduler/` and `scrapers/program_requirements.py` while omitting network-dependent scrapers that require live internet access.

### Test suite summary

| File | What is tested |
|---|---|
| `test_conflict.py` | `is_half_semester`, `parse_days`, `parse_time`, `sections_conflict`, `find_conflicts` — 100 % coverage |
| `test_models.py` | `CourseSection`, `ConflictReport`, `TermSchedule` — 100 % coverage |
| `test_transcript_parser.py` | All pure-text functions in `transcript_pdf.py` via synthetic strings and mocked PDF I/O |
| `test_api_routes.py` | Page routes, catalog/sections/courses API, auth flow, wishlist, profile, AI planner advice |
| `test_planner_api.py` | Planner overview and graduation-estimate endpoints |
| `test_progress_overview.py` | Degree-progress audit endpoint |
| `test_scenarios.py` | Schedule scenario lifecycle (create, duplicate, rename, activate, delete) |
| `test_account_api.py` | Account change-password, change-username, export, and delete flows |
| `test_prereqs.py` | Prerequisite parsing and checking logic |
| `test_program_requirements.py` | SmartCatalog program-requirements scraper and dataclasses |

---

## Project Structure

```
project/
├── data/
│   └── courses.db              SQLite database (catalog + sections + app data)
├── scrapers/
│   ├── __init__.py
│   ├── __main__.py             python -m scrapers entry point
│   ├── catalog.py              Course catalog scraper
│   ├── program_requirements.py Degree-requirement scraper + dataclasses
│   ├── infer_terms.py          Term inference from degree maps
│   ├── sections.py             Section schedule scraper
│   └── session_dates.py        Academic calendar scraper
├── scheduler/
│   ├── app.py                  Flask application, all API and page routes
│   ├── db.py                   SQLite connection, schema init, all queries
│   ├── conflict.py             Schedule conflict detection
│   ├── transcript_pdf.py       PDF transcript parsing (in-memory, no file storage)
│   ├── models.py               OOP domain models: CourseSection, ConflictReport, TermSchedule
│   ├── reference_programs.py   Static program-reference data
│   ├── pages/                  HTML page templates
│   └── static/                 CSS and JavaScript
├── tests/
│   └── test_*.py               pytest test suite (308 tests, ≥ 80 % coverage)
├── .coveragerc                 Coverage configuration
├── pytest.ini                  pytest discovery settings
├── requirements.txt            Python dependencies
├── .env.example                Environment variable template
└── README.md
```

---

## Database Schema

All data lives in `data/courses.db`:

| Table | Purpose |
|---|---|
| `courses` | Course catalog: code, name, URL, prerequisites, inferred term |
| `sections` | Section schedule: term, days, times, location, mode, session |
| `session_calendar` | Session start/end dates per term |
| `program_requirements` | Scraped degree requirements grouped by program and block |
| `academic_program_names` | Canonical program names for major matching |
| `users` | User accounts with hashed passwords |
| `schedule_scenarios` | Named schedule scenarios per user and term |
| `user_schedules` | Saved section IDs per user, term, and scenario |
| `user_profiles` | Major, minor, transcript metadata, and parsed transcript JSON |
| `course_wishlist` | Saved catalog courses per user |
| `completed_overrides` | Manually marked completed courses (transfer equivalencies, etc.) |
| `user_settings` | Per-user key/value settings (credits target, etc.) |

---

## API Overview

All endpoints are served by the Flask app at `http://127.0.0.1:5000`.

**Public endpoints** (no authentication required):

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/terms` | Available terms |
| `GET` | `/api/sections` | Sections (filterable by term, subject, mode, etc.) |
| `GET` | `/api/courses` | Course catalog (filterable) |
| `GET` | `/api/courses/<id>` | Course detail with sections |
| `GET` | `/api/subjects` / `/api/course-subjects` | Subject codes |
| `GET` | `/api/modes` | Delivery modes |
| `GET` | `/api/session-dates` | Session calendar |
| `GET` | `/api/academic-programs` | Program names |
| `POST` | `/api/register` | Create account |
| `POST` | `/api/login` | Authenticate |
| `POST` | `/api/logout` | End session |

**Authenticated endpoints** (session required):

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/me` | Current user info |
| `GET/POST` | `/api/profile` | Transcript upload and profile data |
| `GET/POST/DELETE` | `/api/wishlist` | Course wishlist |
| `GET/POST` | `/api/planner-target` | Credits target setting |
| `GET` | `/api/term-timeline` | Full planner term overview |
| `GET` | `/api/degree-progress` | Degree audit (completed/in-progress/remaining) |
| `POST` | `/api/ai/planner-advice` | AI planning advice (falls back to rule-based) |
| `POST` | `/api/prereq-check` | Prerequisite check for a set of course codes |
| `GET` | `/api/account/summary` | Account overview stats |
| `GET` | `/api/account/export` | Download full data bundle as JSON |
| `POST` | `/api/account/change-password` | Change password |
| `POST` | `/api/account/change-username` | Change username |
| `POST` | `/api/account/delete` | Permanently delete account |

---

## Team

| Name | Contributions |
|---|---|
| *(member 1)* | *(e.g., scraper modules, database schema)* |
| *(member 2)* | *(e.g., Flask API, conflict detection)* |
| *(member 3)* | *(e.g., frontend HTML/CSS/JS)* |
| *(member 4)* | *(e.g., transcript parser, degree progress)* |
| *(member 5)* | *(e.g., testing, OOP models, documentation)* |
