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
- **user_schedules** — saved section ids per user and term
- **user_profiles** — major, minor, original upload name (`transcript_original_name`), and **`transcript_parsed_json`** (parsed GPA, credits, course rows, etc.; the PDF itself is not kept on disk)
