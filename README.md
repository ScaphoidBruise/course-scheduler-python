# UTPB Course Scraper & Scheduler

A tool that scrapes course data from the UTPB website and lets you build
a weekly class schedule in the browser. Built for COSC 3320.

## Getting started

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Populating the database

Run from the **project root** so paths like `data/courses.db` resolve correctly.

**One command (full refresh):** runs catalog (all subjects), infer-terms, sections, and session-dates in order.

```bash
python -m scrapers sync [--db PATH] [--quiet] [--backup-db]
```

**Step by step:** implementation lives under `scrapers/`; you can call either the unified CLI or the legacy scripts (they are thin wrappers).

```bash
python -m scrapers catalog [--db PATH] [--subject COSC | --all-subjects] [--backup-db]
python -m scrapers infer-terms [--db PATH] [--falcon-url URL] [--quiet]
python -m scrapers sections [--db PATH] [--quiet]
python -m scrapers session-dates [--db PATH] [--calendar-url URL] [--quiet]
```

(`PATH` defaults to `data/courses.db` for every command; omit `--db` when the default is fine.)

Equivalent legacy entry points (same flags and defaults as `python -m scrapers …`):

```bash
python scraper.py                              # catalog: interactive unless --all-subjects / --subject / --db …
python infer_term_from_degree_maps.py [--db PATH]
python scrape_sections.py [--db PATH]
python scrape_session_dates.py [--db PATH]
```

Add `--quiet` to infer-terms, sections, or session-dates to cut down on log output. The catalog step has no `--quiet` flag.

### Course scraper and the rest of the database

`data/courses.db` holds **catalog data, section data, and app data** (user accounts, saved schedules, profiles) in one file.

- **`python scraper.py` / `python -m scrapers catalog` update only the `courses` table** in place (target file is `--db`, default `data/courses.db`). They do not delete the database file, so **users, `sections`, `session_calendar`, and other tables are left intact.**
- **`--subject CODE` or interactive single-subject runs** replace rows for **that subject only** (other subjects in `courses` are unchanged).
- **`--all-subjects`** clears the entire `courses` table, then inserts the full catalog (still does not remove other tables).
- Optional **`--backup-db`** (catalog only): before changing `courses`, copies the **entire** SQLite file you are writing to into `data/archive/` (timestamped filename). Use this before a big scrape if you want a full snapshot on disk.

Transcript PDFs are **not stored** on the server: the app reads the upload in memory, parses it, and saves the structured result in the user profile.

## Running the scheduler

```bash
cd scheduler
set FLASK_DEBUG=1
python app.py
```

Then go to http://127.0.0.1:5000.

For local development, set `FLASK_DEBUG=1` (Windows) or `export FLASK_DEBUG=1` (Unix) to enable the Flask debug server. Omit it (or set to `0`) for a non-debug run. Override the port with `PORT` if needed.

Set `SCHEDULER_SECRET_KEY` to a long random string if the app is reachable outside your own machine (session security).

You can register an account, pick a term, search/filter sections, and add them to a weekly grid.
It will warn you if two classes conflict. Half-semester sessions (8W1, 8W2, etc.)
are handled separately so they will not false-flag each other.

There is a catalog page to browse all courses, a profile page (transcript import for GPA/course lists), plus about/help pages.

## Planner dashboard

The Planner page at `/planner` shows every saved term plan in one graduation-focused view. It summarizes completed, planned, and target credits, estimates a graduation term, flags term conflicts, and charts credits per term without any external chart library.

## Multiple schedules & sharing

Each term can have multiple named schedule scenarios. The active scenario is what the older `/api/my-schedule` endpoint reads and writes, so existing clients still work while the UI can create, duplicate, rename, delete, and switch plans.

Use **Export .ics** to download calendar events for in-person meeting times. Use **Copy share link** to create a public read-only snapshot URL for the selected scenario.

## Running tests

From the repo root:

```bash
python -m pytest tests/ -v
# or, if pytest is unavailable in your environment:
python -m unittest discover -s tests -v
```

The suite covers prereq parsing, the planner overview API, scenario lifecycle, the new degree-progress overview endpoint, and the new account self-service flow.

## Degree progress & prereq awareness

After a transcript is imported, the `/progress` page uses parsed course history to show completed, in-progress, and still-needed courses for the detected program subjects. You can manually mark a remaining course as completed for transfer or parser misses. The Profile page keeps a compact overview tile that links into `/progress`.

The Schedule page checks visible section cards against completed transcript courses and manual overrides. When catalog prerequisite text can be parsed as `SUBJ ####` course requirements, missing prerequisites appear as red chips; free-text-only requirements such as instructor consent are treated as unparseable instead of blocking.

## Catalog detail & wishlist

The catalog page supports subject, level, typical-term, and text filters. Course rows open a detail modal with prerequisites, catalog link, and all known sections across terms with session dates from `session_calendar`.

Signed-in users can add catalog courses to a personal wishlist. Wishlist rows are stored in `course_wishlist` and also appear on the profile page below Past & current credits.

## /progress (dedicated degree-progress page)

Detailed degree progress lives on its own `/progress` page. The Profile page now keeps a compact overview tile (credits earned vs target, courses still required, progress bar) with a "View full progress →" link.

The full page renders three cards:

- **Completed** — table view with per-row "Remove" buttons for entries you added via the manual completed-overrides flow (transcript-derived rows show "From transcript" and are not removable).
- **In progress** — read-only list of in-progress courses detected from the transcript.
- **Remaining** — Bootstrap accordion grouped by Spring / Summer / Fall / Unscheduled. Each course pill opens a popover with a grade picker (A through D and P/CR/S) and a "Mark as completed" save button that posts to `/api/completed-overrides`.

The header strip lets you edit the credits target inline (POST `/api/planner-target`). A new `GET /api/degree-progress/overview` endpoint returns just the summary stats (credits completed, target, percent complete, courses remaining count, scope subjects, transcript flag, major / minor) for the profile tile so the lighter page does not pay for full progress detail.

## Account self-service

The Account page now offers self-service for signed-in users:

- **Account overview** — username, member-since date, transcript flag, and saved schedule plan count.
- **Change password** — re-confirms the current password before accepting a new password (≥ 8 chars, must match confirmation).
- **Change username** — lowercase, ≥ 3 characters, gated by current password, and rejected with `409 Conflict` when the name is taken.
- **Export my data** — downloads a JSON bundle (`utpb-export-<username>-<YYYYMMDD>.json`) containing the user record, profile, scenarios with section ids, wishlist, completed-course overrides, and saved settings.
- **Delete account** — destructive flow gated by typing the literal word `DELETE` plus the current password. On success the session is cleared and `/api/me` reports `authenticated=False`.

The endpoints are `GET /api/account/summary`, `POST /api/account/change-password`, `POST /api/account/change-username`, `POST /api/account/delete`, and `GET /api/account/export`. They live alongside the existing `/api/login`, `/api/register`, and `/api/logout` endpoints and reuse `werkzeug.security.check_password_hash` to re-verify the current password before any mutation.

## How it's built

Flask serves the HTML pages and a JSON API. The frontend is plain HTML, CSS,
and vanilla JS — no frameworks or templating. While signed in, your schedule
for each term is stored in the database and loaded from the API.

```
scrapers/                 # default DB path: data/courses.db (--db overrides)
├── __init__.py
├── catalog.py            # SmartCatalog -> courses
├── infer_terms.py        # Falcon Maps PDFs -> term_infered
├── sections.py           # Registrar -> sections
├── session_dates.py      # Academic calendar -> session_calendar
└── __main__.py           # python -m scrapers ...

scheduler/
├── app.py              API endpoints and page routes
├── db.py               SQLite queries
├── conflict.py         Conflict detection (matches browser rules for 8-week sessions)
├── transcript_pdf.py   Transcript PDF parsing
├── pages/              HTML files
└── static/             CSS and JS
```

## Database tables

Everything lives in `data/courses.db`:

- **courses** — code, name, URL, prerequisites, inferred term
- **sections** — term, section code, days, times, location, mode, session
- **session_calendar** — start/end dates per session per term
- **users** — accounts (hashed passwords)
- **schedule_scenarios** — named schedule scenarios per user and term, including share tokens
- **user_schedules** — saved section ids per user, term, and scenario
- **user_profiles** — major, minor, original upload name (`transcript_original_name`), and **`transcript_parsed_json`** (parsed GPA, credits, course rows, etc.; the PDF itself is not kept on disk)
