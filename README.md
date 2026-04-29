# UTPB Academic Scheduler

Flask app for UTPB course planning: scraped catalog and sections, PDF transcript parsing, prerequisites and time conflicts, degree progress against scraped requirements, and optional Anthropic-backed planner tips via env configuration.

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

---

## Features

- **Schedule:** Section search by term, subject, session, mode; weekly grid; server-side overlap checks (including 8W1/8W2 sessions).
- **Transcript:** Parses unofficial UTPB transcript PDFs in memory (parsed fields stored in profile JSON; no uploaded file persisted on disk).
- **Prereqs:** Transcript-derived completions plus manual overrides.
- **Degree audit:** Major matched to scraped `program_requirements` rows.
- **Planner:** Named scenarios per term; timeline endpoint with credit estimates.
- **Anthropic:** Optional planner endpoint when `ANTHROPIC_API_KEY` is set; otherwise rule-based responses.
- **Account:** Password/username changes, JSON export, account deletion.
- **ICS:** Calendar export for a saved schedule.

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
  ├── catalog.py               SmartCatalog → courses table
  ├── program_requirements.py  Programs of Study → requirements tables
  ├── infer_terms.py           Falcon Maps PDFs → term_infered column
  ├── sections.py              Registrar schedule → sections table
  └── session_dates.py         Academic calendar → session_calendar table
```

Static HTML pages; JSON API via `fetch` (no SPA framework).

---

## Object-Oriented Design

Main types live in `scheduler/models.py`:

| Class | Role |
|---|---|
| `CourseSection` | Section row from SQLite; helpers (`is_online`, minute-based times, `as_dict()`). |
| `ConflictReport` | Result of `TermSchedule.add()` when overlaps exist. |
| `TermSchedule` | One term’s sections; uses `conflict.py`. |

`scrapers/program_requirements.py` defines `ProgramRef`, `RequirementCourse`, `RequirementBlock`, `ProgramRequirements`.

---

## Installation

Python 3.11+.

```bash
git clone <repo-url>
cd project
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

`requirements.txt` lists minimum versions (Flask, PyPDF, Werkzeug, pytest stack).

---

## Configuration

Copy `.env.example` to `.env`:

```bash
copy .env.example .env   # Windows
cp .env.example .env     # macOS / Linux
```

| Variable | Required? | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | No | Omit for rule-only planner responses. |
| `ANTHROPIC_MODEL` | No | Defaults to `claude-haiku-4-5-20251001`. |
| `SCHEDULER_SECRET_KEY` | No | Flask session signing; generated at startup if unset (set explicitly for production). |

---

## Populating the Database

From repository root:

```bash
python -m scrapers sync

python -m scrapers catalog --all-subjects
python -m scrapers program-requirements --all-programs
python -m scrapers infer-terms
python -m scrapers sections
python -m scrapers session-dates
```

Defaults to `data/courses.db`; `--db PATH` overrides. `--quiet` reduces logging. Catalog scraper supports `--backup-db` before overwriting course rows.

Dry-run program requirements:

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

Development URL: [http://127.0.0.1:5000](http://127.0.0.1:5000). Optional `PORT`; disable debug with `FLASK_DEBUG=0` or unset.

---

## Running Tests

```bash
python -m pytest tests/ -v

python -m pytest tests/ --cov=scheduler --cov=scrapers --cov-config=.coveragerc --cov-report=term-missing
```

`.coveragerc` targets `scheduler/` and `scrapers/program_requirements.py`; network-heavy scrapers are excluded.

| File | Focus |
|---|---|
| `test_conflict.py` | Conflict helpers |
| `test_models.py` | `CourseSection`, `ConflictReport`, `TermSchedule` |
| `test_transcript_parser.py` | `transcript_pdf.py` |
| `test_api_routes.py` | Routes, APIs, auth, wishlist, profile, planner advice |
| `test_planner_api.py` | Planner endpoints |
| `test_progress_overview.py` | Degree overview |
| `test_scenarios.py` | Schedule scenarios |
| `test_account_api.py` | Account flows |
| `test_prereqs.py` | Prerequisites |
| `test_program_requirements.py` | Requirements scraper |

---

## Project Structure

```
project/
├── data/
│   └── courses.db              SQLite (app + scraper data)
├── scrapers/
├── scheduler/                  Flask app, templates, static assets
├── tests/
├── .coveragerc
├── pytest.ini
├── requirements.txt
├── .env.example
└── README.md
```

`data/uploads/` is gitignored.

---

## Database Schema

`data/courses.db`:

| Table | Purpose |
|---|---|
| `courses` | Catalog, prerequisites, inferred term |
| `sections` | Sections |
| `session_calendar` | Session dates |
| `program_requirements` | Scraped requirements |
| `academic_program_names` | Program name strings |
| `users` | Accounts |
| `schedule_scenarios` | Named scenarios |
| `user_schedules` | Saved section IDs |
| `user_profiles` | Profile and parsed transcript JSON |
| `course_wishlist` | Wishlist |
| `completed_overrides` | Manual completion rows |
| `user_settings` | User settings |

---

## API Overview

Base URL (local): `http://127.0.0.1:5000`.

**Unauthenticated**

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/terms` | Terms |
| `GET` | `/api/sections` | Sections |
| `GET` | `/api/courses` | Catalog |
| `GET` | `/api/courses/<id>` | Course + sections |
| `GET` | `/api/subjects`, `/api/course-subjects` | Subjects |
| `GET` | `/api/modes` | Modes |
| `GET` | `/api/session-dates` | Session calendar |
| `GET` | `/api/academic-programs` | Programs |
| `POST` | `/api/register` | Registration |
| `POST` | `/api/login` | Login |
| `POST` | `/api/logout` | Logout |

**Session required**

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/me` | Current user |
| `GET/POST` | `/api/profile` | Profile; transcript POST |
| `GET/POST/DELETE` | `/api/wishlist` | Wishlist |
| `GET/POST` | `/api/planner-target` | Credit target |
| `GET` | `/api/term-timeline` | Planner timeline |
| `GET` | `/api/degree-progress` | Degree audit |
| `POST` | `/api/ai/planner-advice` | Planner advice |
| `POST` | `/api/prereq-check` | Prerequisite check |
| `GET` | `/api/account/summary` | Summary |
| `GET` | `/api/account/export` | JSON export |
| `POST` | `/api/account/change-password` | Change password |
| `POST` | `/api/account/change-username` | Change username |
| `POST` | `/api/account/delete` | Delete account |
