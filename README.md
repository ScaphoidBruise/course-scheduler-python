# UTPB Course Scraper 

This project scrapes UTPB course data and stores it in SQLite.

It supports:
- one subject (`--subject COSC`),
- all subjects (`--all-subjects`),
- or interactive selection (no flags).

## Run

From this project folder:

```bash
python scraper.py
```

Or:

```bash
python scraper.py --subject COSC
python scraper.py --all-subjects
```

## What gets saved

Database file:
- `data/courses.db`

Table:
- `courses`
  - `id`
  - `subject_code`
  - `course_number`
  - `course_code`
  - `course_name`
  - `course_url` (full URL to the catalog course page)
  - `prerequisites`
  - `term_offered`

## Archive behavior

Before each run:
- if `data/courses.db` already exists, it is moved to `data/archive/`
- archive name format: `courses_YYYYMMDD_HHMMSS.db`
- if that name already exists, `_1`, `_2`, etc. is appended

Then a fresh `data/courses.db` is created and loaded.
