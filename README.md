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

Note:
- `--all-subjects` skips per-course detail-page fetches for speed/stability, so `prerequisites` may be empty in that mode.

## Degree map term inference

To infer a fallback term label from UTPB degree-map PDFs:

```bash
python infer_term_from_degree_maps.py --db data/courses.db
```

This script writes to `courses.term_infered` only.
It requires `courses` table to already exist (run `scraper.py` first).
By default it prints progress for each PDF. Use `--quiet` to suppress per-PDF logs.

## Schedule sections scraper

To scrape sections from the three current/upcoming schedule links (Spring/Summer/Fall cards):

```bash
python scrape_sections.py --db data/courses.db
```

Use `--quiet` to reduce logs:

```bash
python scrape_sections.py --db data/courses.db --quiet
```

This script writes to `sections` and keeps the following fields for each section:
- `subject_code`
- `course_number`
- `course_code`
- `credits` (`Hrs`)
- `days`
- `session` (including values like `8W1` and `8W2`)
- `start_time`
- `end_time`
- `location`
- `mode`

## Session-date linker

To map calendar start/end dates to each section session (`1`, `8W1`/`7W1`, `8W2`/`7W2`):

```bash
python scrape_session_dates.py --db data/courses.db
```

Use `--quiet` for less logging:

```bash
python scrape_session_dates.py --db data/courses.db --quiet
```

This reads `Classes Begin` and `Semester Ends` from the UTPB academic calendar and writes:
- `session_calendar.term_label`
- `session_calendar.session`
- `session_calendar.session_start_date`
- `session_calendar.session_end_date`

Use joins when you need section dates:

```sql
SELECT s.course_code, s.term_label, s.session, c.session_start_date, c.session_end_date
FROM sections s
LEFT JOIN session_calendar c
  ON c.term_label = s.term_label
 AND c.session = s.session;
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
  - `term_infered`
- `sections`
  - `id`
  - `term_label`
  - `schedule_url`
  - `class_nbr`
  - `subject_code`
  - `course_number`
  - `course_code`
  - `section_code`
  - `credits`
  - `days`
  - `session`
  - `start_time`
  - `end_time`
  - `location`
  - `mode`
- `session_calendar`
  - `id`
  - `term_label`
  - `session`
  - `session_start_date`
  - `session_end_date`
  - `source_url`

## Archive behavior

Before each run:
- if `data/courses.db` already exists, it is moved to `data/archive/`
- archive name format: `courses_YYYYMMDD_HHMMSS.db`
- if that name already exists, `_1`, `_2`, etc. is appended

Then a fresh `data/courses.db` is created and loaded.
