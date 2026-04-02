"""Scrape UTPB current schedule sections into SQLite."""

import argparse
import re
import sqlite3
from html import unescape
from urllib.request import urlopen


DEFAULT_DB = "data/courses.db"
SCHEDULE_PAGE_URL = "https://www.utpb.edu/academics/registration/course-schedules"
REQUEST_TIMEOUT_SECONDS = 20


def parse_args():
    parser = argparse.ArgumentParser(description="Scrape Spring/Summer/Fall sections into SQLite.")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to SQLite DB")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-page progress logs")
    return parser.parse_args()


def fetch_text(url):
    return urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS).read().decode("utf-8", "ignore")


def clean_html_text(raw):
    text = re.sub(r"<[^>]+>", " ", raw)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def extract_semester_schedule_links(course_schedules_html):
    start_marker = re.search(r"<h2>\s*Current and Upcoming Semester Schedules\s*</h2>", course_schedules_html, flags=re.IGNORECASE)
    end_marker = re.search(r"<h2>\s*Final Exam Schedule\s*</h2>", course_schedules_html, flags=re.IGNORECASE)
    if not start_marker or not end_marker or end_marker.start() <= start_marker.end():
        return []

    section_html = course_schedules_html[start_marker.end() : end_marker.start()]
    cards = re.findall(r"<a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", section_html, flags=re.IGNORECASE | re.DOTALL)

    links = []
    seen = set()
    for href, card_html in cards:
        if "general.utpb.edu/schedule/index.php?term=" not in href.lower():
            continue
        label_match = re.search(r"<h3[^>]*>(.*?)</h3>", card_html, flags=re.IGNORECASE | re.DOTALL)
        term_label = clean_html_text(label_match.group(1)) if label_match else ""
        if not term_label:
            continue
        key = (term_label, href)
        if key in seen:
            continue
        seen.add(key)
        links.append({"term_label": term_label, "url": href})
    return links


def extract_rows_from_schedule_table(schedule_html):
    table_match = re.search(r"<table[^>]*>(.*?)</table>", schedule_html, flags=re.IGNORECASE | re.DOTALL)
    if not table_match:
        return []

    table_html = table_match.group(1)
    tr_blocks = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, flags=re.IGNORECASE | re.DOTALL)
    rows = []
    expected_headers = ["Class NBR", "Subject", "Number", "Section", "Course Title", "Term", "Session", "Hrs", "Instructor", "Days", "Start", "End", "Location", "Enrolled", "Limit", "Status", "Cross Ref", "Mode", "Book"]

    for block in tr_blocks:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", block, flags=re.IGNORECASE | re.DOTALL)
        if not cells:
            continue

        values = [clean_html_text(cell) for cell in cells]
        if len(values) < 19:
            continue
        if values[:19] == expected_headers:
            continue

        rows.append(
            {
                "class_nbr": values[0],
                "subject_code": values[1].upper(),
                "course_number": values[2],
                "section_code": values[3],
                "session": values[6],
                "credits": values[7],
                "days": values[9],
                "start_time": values[10],
                "end_time": values[11],
                "location": values[12],
                "mode": values[17],
            }
        )
    return rows

def main():
    args = parse_args()

    schedule_page_html = fetch_text(SCHEDULE_PAGE_URL)
    term_links = extract_semester_schedule_links(schedule_page_html)
    if not term_links:
        print("No current/upcoming semester links found before Final Exam Schedule.")
        return

    if not args.quiet:
        print("Semester links found:")
        for idx, link in enumerate(term_links, start=1):
            print(f"  {idx}. {link['term_label']} -> {link['url']}")
        print("")

    conn = sqlite3.connect(args.db)
    has_courses = conn.execute(
        "SELECT COUNT(1) FROM sqlite_master WHERE type='table' AND name='courses'"
    ).fetchone()[0]
    if not has_courses:
        conn.close()
        print("No 'courses' table found in DB.")
        print("Run scraper first: python scraper.py --all-subjects")
        return

    conn.execute("CREATE TABLE IF NOT EXISTS sections (id INTEGER PRIMARY KEY AUTOINCREMENT, term_label TEXT NOT NULL, schedule_url TEXT NOT NULL, class_nbr TEXT, subject_code TEXT NOT NULL, course_number TEXT NOT NULL, course_code TEXT NOT NULL, section_code TEXT, credits TEXT, days TEXT, session TEXT, start_time TEXT, end_time TEXT, location TEXT, mode TEXT, UNIQUE(term_label, class_nbr, subject_code, course_number, section_code, session, days, start_time, end_time, location, mode))")

    for link in term_links:
        conn.execute("DELETE FROM sections WHERE term_label = ? AND schedule_url = ?", (link["term_label"], link["url"]))

    inserted = 0
    total_rows = 0
    for link in term_links:
        if not args.quiet:
            print(f"Parsing {link['term_label']}: {link['url']}")
        try:
            page_html = fetch_text(link["url"])
        except Exception as ex:
            if not args.quiet:
                print(f"  -> skipped ({ex})")
            continue

        rows = extract_rows_from_schedule_table(page_html)
        total_rows += len(rows)
        if not args.quiet:
            print(f"  -> rows found: {len(rows)}")

        for row in rows:
            subject_code = row["subject_code"].strip().upper()
            course_number = row["course_number"].strip()
            if not subject_code or not course_number:
                continue
            if not re.fullmatch(r"[A-Z]{2,5}", subject_code):
                continue
            if not re.search(r"\d", course_number):
                continue

            course_code = f"{subject_code} {course_number}"
            cursor = conn.execute(
                "INSERT OR IGNORE INTO sections (term_label, schedule_url, class_nbr, subject_code, course_number, course_code, section_code, credits, days, session, start_time, end_time, location, mode) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    link["term_label"],
                    link["url"],
                    row["class_nbr"],
                    subject_code,
                    course_number,
                    course_code,
                    row["section_code"],
                    row["credits"],
                    row["days"],
                    row["session"],
                    row["start_time"],
                    row["end_time"],
                    row["location"],
                    row["mode"],
                ),
            )
            inserted += cursor.rowcount

    conn.commit()
    conn.close()

    print("Done.")
    print("Semester links found:", len(term_links))
    print("Section rows parsed:", total_rows)
    print("Section rows inserted:", inserted)
    print("Database:", args.db)


if __name__ == "__main__":
    main()
