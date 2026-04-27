"""Link section sessions to calendar start/end dates."""

import argparse
from datetime import datetime
from html import unescape
import re
import sqlite3
from urllib.request import urlopen


DEFAULT_DB = "data/courses.db"
ACADEMIC_CALENDAR_URL = "https://www.utpb.edu/academics/academic-calendar/"
REQUEST_TIMEOUT_SECONDS = 20


def build_parser():
    parser = argparse.ArgumentParser(description="Add session start/end dates to sections from academic calendar.")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to SQLite DB")
    parser.add_argument("--calendar-url", default=ACADEMIC_CALENDAR_URL, help="Academic calendar URL")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-term progress logs")
    return parser


def parse_args(argv=None):
    return build_parser().parse_args(argv)


def fetch_text(url):
    return urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS).read().decode("utf-8", "ignore")


def clean_html_text(raw):
    text = re.sub(r"<[^>]+>", " ", raw)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_date(raw):
    text = (raw or "").strip()
    if not text:
        return ""

    text = text.replace("-", "/")
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def align_to_term_year(date_iso, term_label):
    if not date_iso:
        return ""
    term_year_match = re.search(r"\b(\d{4})\b", term_label)
    if not term_year_match:
        return date_iso
    term_year = term_year_match.group(1)
    return f"{term_year}-{date_iso[5:]}"


def parse_calendar_terms(html):
    table_match = re.search(r"<table[^>]*>(.*?)</table>", html, flags=re.IGNORECASE | re.DOTALL)
    if not table_match:
        return {}

    tr_blocks = re.findall(r"<tr[^>]*>(.*?)</tr>", table_match.group(1), flags=re.IGNORECASE | re.DOTALL)
    rows = []
    for tr in tr_blocks:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.IGNORECASE | re.DOTALL)
        if not cells:
            continue
        rows.append([clean_html_text(c) for c in cells])

    terms = {}
    idx = 0
    while idx < len(rows):
        row = rows[idx]
        first = row[0] if row else ""
        term_match = re.fullmatch(r"(Spring|Summer|Fall)\s+\d{4}", first, flags=re.IGNORECASE)
        if not term_match:
            idx += 1
            continue

        term_label = term_match.group(0).title()
        classes_begin = ["", "", ""]
        semester_ends = ["", "", ""]
        idx += 1

        while idx < len(rows):
            current = rows[idx]
            title = current[0] if current else ""
            if re.fullmatch(r"(Spring|Summer|Fall)\s+\d{4}", title, flags=re.IGNORECASE):
                break

            if title.lower() == "classes begin":
                classes_begin[0] = align_to_term_year(normalize_date(current[1] if len(current) > 1 else ""), term_label)
                classes_begin[1] = align_to_term_year(normalize_date(current[2] if len(current) > 2 else ""), term_label)
                classes_begin[2] = align_to_term_year(normalize_date(current[3] if len(current) > 3 else ""), term_label)

            if title.lower() == "semester ends":
                semester_ends[0] = align_to_term_year(normalize_date(current[1] if len(current) > 1 else ""), term_label)
                semester_ends[1] = align_to_term_year(normalize_date(current[2] if len(current) > 2 else ""), term_label)
                semester_ends[2] = align_to_term_year(normalize_date(current[3] if len(current) > 3 else ""), term_label)

            idx += 1

        terms[term_label] = {"classes_begin": classes_begin, "semester_ends": semester_ends}

    return terms


def run(args):
    html = fetch_text(args.calendar_url)
    term_map = parse_calendar_terms(html)
    if not term_map:
        print("No term calendar data found.")
        return

    conn = sqlite3.connect(args.db)
    has_sections = conn.execute(
        "SELECT COUNT(1) FROM sqlite_master WHERE type='table' AND name='sections'"
    ).fetchone()[0]
    if not has_sections:
        conn.close()
        print("No 'sections' table found in DB.")
        print("Run sections scraper first: python -m scrapers sections --db data/courses.db")
        return

    conn.execute("CREATE TABLE IF NOT EXISTS session_calendar (id INTEGER PRIMARY KEY AUTOINCREMENT, term_label TEXT NOT NULL, session TEXT NOT NULL, session_start_date TEXT, session_end_date TEXT, source_url TEXT NOT NULL, UNIQUE(term_label, session))")

    rows_written = 0
    terms_applied = 0
    for term_label, data in term_map.items():
        term_sessions = conn.execute("SELECT DISTINCT COALESCE(session, '') FROM sections WHERE term_label = ?", (term_label,)).fetchall()
        if not term_sessions:
            continue

        if not args.quiet:
            print(f"Applying dates for {term_label}")

        for session_row in term_sessions:
            session = (session_row[0] or "").strip()
            session_up = session.upper()
            slot = 0
            if session_up.endswith("W1"):
                slot = 1
            elif session_up.endswith("W2"):
                slot = 2

            start_date = data["classes_begin"][slot]
            end_date = data["semester_ends"][slot]
            conn.execute(
                "INSERT INTO session_calendar (term_label, session, session_start_date, session_end_date, source_url) VALUES (?, ?, ?, ?, ?) ON CONFLICT(term_label, session) DO UPDATE SET session_start_date = excluded.session_start_date, session_end_date = excluded.session_end_date, source_url = excluded.source_url",
                (term_label, session, start_date, end_date, args.calendar_url),
            )
            rows_written += 1

        terms_applied += 1

    conn.commit()
    conn.close()

    print("Done.")
    print("Calendar terms parsed:", len(term_map))
    print("Calendar terms applied to DB:", terms_applied)
    print("Session calendar rows upserted:", rows_written)
    print("Database:", args.db)


def main(argv=None):
    run(parse_args(argv))


if __name__ == "__main__":
    main()
