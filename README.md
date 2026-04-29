# UTPB Academic Scheduler

<<<<<<< HEAD
Flask app for planning classes at UTPB. You get scraped catalog/sections, PDF transcript import, prereqs and time conflicts, degree progress vs scraped requirements, and an optional planner bot if you add an Anthropic API key.
=======
Python web app for UTPB students: live catalog and sections, unofficial transcript import, prerequisite and conflict checks, degree-progress tracking from scraped requirements, and optional AI planning advice (Anthropic).
>>>>>>> aedae32 (Revise README and document unofficial transcript source on my.utpb.edu)

## Table of Contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [Object-Oriented Design](#object-oriented-design)
4. [Installation](#installation)
5. [Configuration](#configuration)
6. [Populating the Database](#populating-the-database)
7. [Running the Application](#running-the-application)
8. [Unofficial transcript PDF (my.utpb.edu)](#unofficial-transcript-pdf-myutpbedu)
9. [Running Tests](#running-tests)
10. [Project Structure](#project-structure)
11. [Database Schema](#database-schema)
12. [API Overview](#api-overview)
13. [Team](#team)

---

## Features

<<<<<<< HEAD
- **Schedule:** Search sections by term, subject, session, mode; build a week grid; server checks overlaps (including 8W1/8W2 style sessions).
- **Transcript:** Upload [the unofficial PDF from my.utpb.edu](#unofficial-transcript-pdf-myutpbedu). Parsing stays in memory (nothing written as an uploaded file). Pulls GPA/credits, what's done, major/minor when present.
- **Prereqs:** Uses transcript plus any courses you mark completed by hand.
- **Degree audit:** Lines your major up with scraped program requirement rows (done / in progress / left).
- **Planner:** Multiple saved schedule scenarios per term; one timeline view with rough credit math.
- **Anthropic hook:** Profile summary goes to the Messages API if `ANTHROPIC_API_KEY` is set; otherwise you get simple rule-based tips.
- **Account:** Change login, export JSON bundle, or delete everything.
- **ICS:** Export a calendar file from a saved schedule.
=======
- **Live Schedule Builder** — Search and filter sections by term, subject, session, and mode; add them to a weekly conflict-aware grid.
- **Conflict Detection** — Overlapping class times, including half-semester sessions (8W1/8W2); rules mirrored on the server.
- **Transcript Import** — Parses unofficial UTPB PDF transcripts in memory (no transcript file kept on disk) for GPA, credits, enrolled courses, and major/minor. See [Unofficial transcript PDF](#unofficial-transcript-pdf-myutpbedu) for where to get that PDF.
- **Prerequisite Checking** — Uses completed transcript courses plus manual completion overrides.
- **Degree Progress** — Matches the student’s major to scraped program requirements (completed, in-progress, remaining).
- **Multi-Scenario Planning** — Named schedule scenarios per term; Planner rolls saved terms into a graduation timeline with credit projections.
- **AI Planner Advisor** — Anthropic Messages API with a compact profile summary; rule-based fallback when no API key is set.
- **Account Self-Service** — Change password/username, export data as JSON, or delete the account.
- **ICS Export** — Download a `.ics` calendar for a saved schedule.
>>>>>>> aedae32 (Revise README and document unofficial transcript source on my.utpb.edu)

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

<<<<<<< HEAD
No React/Vue/etc.: pages are static HTML and `fetch` against the API.
=======
The frontend uses no frameworks: each page is plain HTML that calls the JSON API with `fetch`.
>>>>>>> aedae32 (Revise README and document unofficial transcript source on my.utpb.edu)

---

## Object-Oriented Design

<<<<<<< HEAD
Most of the OO stuff sits in `scheduler/models.py`:
=======
Primary domain types live in `scheduler/models.py`:
>>>>>>> aedae32 (Revise README and document unofficial transcript source on my.utpb.edu)

| Class | Role |
|---|---|
<<<<<<< HEAD
| `CourseSection` | One section row from SQLite; helpers like `is_online`, times as minutes, `as_dict()`. |
| `ConflictReport` | What `TermSchedule.add()` returns if something clashes; lists conflicting sections. |
| `TermSchedule` | Holds sections for one term and talks to `conflict.py`. |

`scrapers/program_requirements.py` has dataclasses for programs/blocks/courses (`ProgramRef`, `RequirementCourse`, and friends).
=======
| `CourseSection` | Immutable section snapshot from a DB row; `is_online`, `start_minutes`, `end_minutes`, `as_dict()`. |
| `ConflictReport` | From `TermSchedule.add()`; new section plus conflicting `CourseSection`s; `has_conflicts`, `conflicting_codes`. |
| `TermSchedule` | Sections for one term; uses `conflict.py`; `add`, `remove`, `clear`, `total_credits`, `conflicts_in_schedule()`. |

`scrapers/program_requirements.py` defines `ProgramRef`, `RequirementCourse`, `RequirementBlock`, and `ProgramRequirements` for hierarchical degree requirements.
>>>>>>> aedae32 (Revise README and document unofficial transcript source on my.utpb.edu)

---

## Installation

<<<<<<< HEAD
You want Python 3.11 or newer.
=======
**Prerequisites:** Python 3.11+.
>>>>>>> aedae32 (Revise README and document unofficial transcript source on my.utpb.edu)

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

<<<<<<< HEAD
`requirements.txt` lists minimum versions (Flask, PyPDF, Werkzeug, pytest stack).
=======
`requirements.txt` sets minimum versions for Flask, PyPDF, Werkzeug, pytest, and pytest-cov.
>>>>>>> aedae32 (Revise README and document unofficial transcript source on my.utpb.edu)

---

## Configuration

Copy `.env.example` to `.env`:

```bash
copy .env.example .env   # Windows
cp .env.example .env     # macOS / Linux
```

| Variable | Required? | Notes |
|---|---|---|
<<<<<<< HEAD
| `ANTHROPIC_API_KEY` | No | Without it, planner advice is rule-based only. |
| `ANTHROPIC_MODEL` | No | Defaults to `claude-haiku-4-5-20251001`. |
| `SCHEDULER_SECRET_KEY` | No | Signs Flask cookies. Left unset, the app generates one at startup (fine locally; set it yourself for prod). |
=======
| `ANTHROPIC_API_KEY` | Optional | Enables AI Planner Advisor; otherwise rule-based advice only. |
| `ANTHROPIC_MODEL` | Optional | Defaults to `claude-haiku-4-5-20251001`. |
| `SCHEDULER_SECRET_KEY` | Optional | Flask session signing key. Generated at startup if omitted; set explicitly for production or multiple workers. |
>>>>>>> aedae32 (Revise README and document unofficial transcript source on my.utpb.edu)

---

## Populating the Database

<<<<<<< HEAD
Run from repo root:
=======
From the **project root**:
>>>>>>> aedae32 (Revise README and document unofficial transcript source on my.utpb.edu)

```bash
# One shot
python -m scrapers sync

# Or piece by piece
python -m scrapers catalog --all-subjects
python -m scrapers program-requirements --all-programs
python -m scrapers infer-terms
python -m scrapers sections
python -m scrapers session-dates
```

<<<<<<< HEAD
SQLite path defaults to `data/courses.db` (`--db` overrides). `--quiet` trims logs. Catalog has `--backup-db` if you want a copy before it stomps course rows.

Preview program requirements without writing:
=======
Defaults to `data/courses.db`; use `--db PATH` to override. Add `--quiet` for less logging. The catalog scraper supports `--backup-db` before overwriting course rows.

Dry-run review for program requirements:
>>>>>>> aedae32 (Revise README and document unofficial transcript source on my.utpb.edu)

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

<<<<<<< HEAD
Browse to [http://127.0.0.1:5000](http://127.0.0.1:5000). Change port with `PORT`. Turn debug off with `FLASK_DEBUG=0` or by unsetting it.

### Quick tour
=======
Open [http://127.0.0.1:5000](http://127.0.0.1:5000). Set `PORT` to change the port; omit `FLASK_DEBUG` or use `FLASK_DEBUG=0` for a non-debug run.
>>>>>>> aedae32 (Revise README and document unofficial transcript source on my.utpb.edu)

1. **Schedule:** Add sections and watch for conflicts/prereq hints.
2. **Profile:** Drop in the unofficial transcript PDF ([steps below](#unofficial-transcript-pdf-myutpbedu)).
3. **Progress:** See audit rows and tweak transfer-style overrides if needed.
4. **Planner:** Timeline + optional API advice.
5. Grab **ICS** from the Schedule page if you want a calendar file.

<<<<<<< HEAD
=======
1. **Schedule** — Pick a term, search sections, add to the grid; note conflicts and prerequisite warnings.
2. **Profile** — Upload the unofficial transcript PDF from [my.utpb.edu](#unofficial-transcript-pdf-myutpbedu); review parsed GPA and credits.
3. **Progress** — Degree requirements and transfer overrides.
4. **Planner** — Timeline across saved terms; optional AI advisor.
5. **Export** — `.ics` download from the Schedule page.

>>>>>>> aedae32 (Revise README and document unofficial transcript source on my.utpb.edu)
---

## Unofficial transcript PDF (my.utpb.edu)

<<<<<<< HEAD
Use the real unofficial transcript PDF from the portal. Screenshots and Word exports usually fail parsing.

1. Log into **[my.utpb.edu](https://my.utpb.edu)**.
2. Sidebar: **Academic Records**.
3. Look for **Unofficial Transcript** (wording might vary slightly) and get the PDF download/view.
4. Save as PDF if your browser asks.
5. In our app, open **Profile** and upload it there.

If it errors out, open the PDF locally first to make sure it's not corrupted, and double-check it's the actual unofficial transcript from that menu (not a degree audit PDF from somewhere else).
=======
The parser expects the **unofficial transcript** issued as a PDF through UTPB’s student portal—not a screenshot, photo, or Word document.

1. Sign in to **[my.utpb.edu](https://my.utpb.edu)**.
2. In the sidebar, open **Academic Records**.
3. In that area, find **Unofficial Transcript** (or the equivalent link to view or download the unofficial transcript).
4. Download or save the file as a **PDF**.
5. In this app, go to **Profile** and upload that PDF using the transcript upload control.

If upload fails, confirm the file is the portal-generated unofficial transcript PDF and that it opens correctly in a PDF reader.
>>>>>>> aedae32 (Revise README and document unofficial transcript source on my.utpb.edu)

---

## Running Tests

```bash
python -m pytest tests/ -v

<<<<<<< HEAD
python -m pytest tests/ --cov=scheduler --cov=scrapers --cov-config=.coveragerc --cov-report=term-missing
```

Coverage config focuses on `scheduler/` plus `scrapers/program_requirements.py` and skips scrapers that hit the live network.

| File | Roughly what it hits |
|---|---|
| `test_conflict.py` | Time/conflict helpers |
| `test_models.py` | `CourseSection`, `ConflictReport`, `TermSchedule` |
| `test_transcript_parser.py` | `transcript_pdf.py` |
| `test_api_routes.py` | Routes, APIs, auth, wishlist, profile, planner tip endpoint |
| `test_planner_api.py` | Planner JSON |
| `test_progress_overview.py` | Degree overview endpoint |
| `test_scenarios.py` | Scenario CRUD-style flows |
| `test_account_api.py` | Password/username/export/delete |
| `test_prereqs.py` | Prerequisite logic |
| `test_program_requirements.py` | Requirements scraper + structs |
=======
# Coverage (≥ 80 % required for the measured paths)
python -m pytest tests/ --cov=scheduler --cov=scrapers --cov-config=.coveragerc --cov-report=term-missing
```

`.coveragerc` includes `scheduler/` and `scrapers/program_requirements.py` and excludes network-only scrapers.

| File | Coverage focus |
|---|---|
| `test_conflict.py` | `conflict.py` helpers |
| `test_models.py` | `CourseSection`, `ConflictReport`, `TermSchedule` |
| `test_transcript_parser.py` | `transcript_pdf.py` (strings + mocked PDF I/O) |
| `test_api_routes.py` | Routes, catalog/sections/courses API, auth, wishlist, profile, AI advice |
| `test_planner_api.py` | Planner overview and graduation estimates |
| `test_progress_overview.py` | Degree-progress audit |
| `test_scenarios.py` | Schedule scenarios (create, duplicate, rename, activate, delete) |
| `test_account_api.py` | Account flows |
| `test_prereqs.py` | Prerequisite parsing and checks |
| `test_program_requirements.py` | Program-requirements scraper and dataclasses |
>>>>>>> aedae32 (Revise README and document unofficial transcript source on my.utpb.edu)

---

## Project Structure

```
project/
├── data/
<<<<<<< HEAD
│   └── courses.db              SQLite (everything app + scrapers)
├── scrapers/
├── scheduler/
=======
│   └── courses.db              SQLite (catalog, sections, app data)
├── scrapers/                   CLI scrapers → data/courses.db
├── scheduler/                  Flask app, pages, static assets
>>>>>>> aedae32 (Revise README and document unofficial transcript source on my.utpb.edu)
├── tests/
├── .coveragerc
├── pytest.ini
├── requirements.txt
├── .env.example
└── README.md
```

<<<<<<< HEAD
`data/uploads/` is ignored so random uploads don't land in git.
=======
Runtime uploads are not stored under `data/` in git (`data/uploads/` is gitignored).
>>>>>>> aedae32 (Revise README and document unofficial transcript source on my.utpb.edu)

---

## Database Schema

<<<<<<< HEAD
Same file as above: `data/courses.db`.
=======
Data lives in `data/courses.db`:
>>>>>>> aedae32 (Revise README and document unofficial transcript source on my.utpb.edu)

| Table | What it holds |
|---|---|
<<<<<<< HEAD
| `courses` | Catalog rows + prereqs + inferred term field |
| `sections` | Meeting times, modality, etc. |
| `session_calendar` | Session date ranges |
| `program_requirements` | Scraped requirement trees |
| `academic_program_names` | Strings used to match majors |
| `users` | Login |
| `schedule_scenarios` | Named plans |
| `user_schedules` | Saved picks per scenario |
| `user_profiles` | Major/minor + transcript JSON blob |
| `course_wishlist` | Saved catalog codes |
| `completed_overrides` | Extra “counts as done” rows |
| `user_settings` | Misc prefs (credit targets and similar) |
=======
| `courses` | Catalog: code, name, URL, prerequisites, inferred term |
| `sections` | Sections: term, days, times, location, mode, session |
| `session_calendar` | Session start/end dates per term |
| `program_requirements` | Scraped degree requirements by program and block |
| `academic_program_names` | Canonical program names for major matching |
| `users` | Accounts (hashed passwords) |
| `schedule_scenarios` | Named scenarios per user and term |
| `user_schedules` | Saved section IDs per user, term, scenario |
| `user_profiles` | Major, minor, transcript metadata, parsed transcript JSON |
| `course_wishlist` | Saved catalog courses |
| `completed_overrides` | Manual completions (e.g. transfer credit) |
| `user_settings` | Per-user settings (e.g. credits target) |
>>>>>>> aedae32 (Revise README and document unofficial transcript source on my.utpb.edu)

---

## API Overview

<<<<<<< HEAD
During dev, base URL is usually `http://127.0.0.1:5000`.

**No login**

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/terms` | Terms |
| `GET` | `/api/sections` | Sections (query params filter) |
| `GET` | `/api/courses` | Catalog |
| `GET` | `/api/courses/<id>` | One course + sections |
| `GET` | `/api/subjects`, `/api/course-subjects` | Subject codes |
| `GET` | `/api/modes` | Delivery modes |
| `GET` | `/api/session-dates` | Calendar rows |
| `GET` | `/api/academic-programs` | Program labels |
| `POST` | `/api/register` | Sign up |
| `POST` | `/api/login` | Session cookie |
| `POST` | `/api/logout` | Drop session |

**Needs session cookie**

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/me` | Who am I |
| `GET/POST` | `/api/profile` | Profile / transcript POST |
| `GET/POST/DELETE` | `/api/wishlist` | Wishlist |
| `GET/POST` | `/api/planner-target` | Credit goal |
| `GET` | `/api/term-timeline` | Planner data |
| `GET` | `/api/degree-progress` | Audit payload |
| `POST` | `/api/ai/planner-advice` | Tips |
| `POST` | `/api/prereq-check` | Check codes |
| `GET` | `/api/account/summary` | Stats |
| `GET` | `/api/account/export` | Full JSON dump |
| `POST` | `/api/account/change-password` | |
| `POST` | `/api/account/change-username` | |
| `POST` | `/api/account/delete` | Hard delete user |
=======
Base URL while developing: `http://127.0.0.1:5000`.

**Public**

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/terms` | Available terms |
| `GET` | `/api/sections` | Sections (filters: term, subject, mode, …) |
| `GET` | `/api/courses` | Course catalog |
| `GET` | `/api/courses/<id>` | Course detail + sections |
| `GET` | `/api/subjects`, `/api/course-subjects` | Subject codes |
| `GET` | `/api/modes` | Delivery modes |
| `GET` | `/api/session-dates` | Session calendar |
| `GET` | `/api/academic-programs` | Program names |
| `POST` | `/api/register` | Register |
| `POST` | `/api/login` | Login |
| `POST` | `/api/logout` | Logout |

**Authenticated**

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/me` | Current user |
| `GET/POST` | `/api/profile` | Profile and transcript upload |
| `GET/POST/DELETE` | `/api/wishlist` | Wishlist |
| `GET/POST` | `/api/planner-target` | Credits target |
| `GET` | `/api/term-timeline` | Planner timeline |
| `GET` | `/api/degree-progress` | Degree audit |
| `POST` | `/api/ai/planner-advice` | AI advice (fallback rules if no key) |
| `POST` | `/api/prereq-check` | Prerequisite check |
| `GET` | `/api/account/summary` | Account stats |
| `GET` | `/api/account/export` | JSON export |
| `POST` | `/api/account/change-password` | Change password |
| `POST` | `/api/account/change-username` | Change username |
| `POST` | `/api/account/delete` | Delete account |
>>>>>>> aedae32 (Revise README and document unofficial transcript source on my.utpb.edu)

---

## Team

Fill in names and who did what for your submission.

| Name | Contributions |
|---|---|
<<<<<<< HEAD
| | |
| | |
| | |
=======
| *(member 1)* | *(e.g., scrapers, database)* |
| *(member 2)* | *(e.g., Flask API, conflicts)* |
| *(member 3)* | *(e.g., HTML/CSS/JS)* |
| *(member 4)* | *(e.g., transcript parser, degree progress)* |
| *(member 5)* | *(e.g., tests, models, docs)* |
>>>>>>> aedae32 (Revise README and document unofficial transcript source on my.utpb.edu)
