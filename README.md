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

Run the scrapers in order. Each one builds on the last.

```bash
python scraper.py                        # grab all courses (or use --subject COSC)
python infer_term_from_degree_maps.py --db data/courses.db   # guess typical terms from degree maps
python scrape_sections.py --db data/courses.db               # pull Spring/Summer/Fall 2026 sections
python scrape_session_dates.py --db data/courses.db          # link session start/end dates from the calendar
```

All four write to `data/courses.db`. Add `--quiet` to any of them to cut down on log output.

If the database already exists when you run `scraper.py`, the old one gets moved to `data/archive/`.

## Running the scheduler

```bash
cd scheduler
python app.py
```

Then go to http://127.0.0.1:5000.

You can pick a term, search/filter sections, and add them to a weekly grid.
It'll warn you if two classes conflict. Half-semester sessions (8W1, 8W2, etc.)
are handled separately so they won't false-flag each other.

There's also a catalog page to browse all courses, plus about/help pages.

## How it's built

Flask serves the HTML pages and a JSON API. The frontend is plain HTML, CSS,
and vanilla JS — no frameworks or templating. Your schedule is saved per-term
in localStorage so it sticks between page reloads.

```
scheduler/
├── app.py            API endpoints and page routes
├── db.py             SQLite queries
├── conflict.py       Conflict detection logic
├── pages/            HTML files
└── static/           CSS and JS
```

## Database tables

Everything lives in `data/courses.db`:

- **courses** — code, name, URL, prerequisites, inferred term
- **sections** — term, section code, days, times, location, mode, session
- **session_calendar** — start/end dates per session per term
