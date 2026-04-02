"""Single-file UTPB course scraper CLI."""

import argparse
from datetime import datetime
from html import unescape
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urljoin
from urllib.request import urlopen


BASE_URL = "https://utpb.smartcatalogiq.com"
SUBJECTS_URL = "https://utpb.smartcatalogiq.com/Institutions/The-University-of-Texas-Permian-Basin/json/2025-2026/subjects-56458BC7-2887-4C10-9CD8-09BB773BE97A.json"
COURSES_URL = "https://utpb.smartcatalogiq.com/Institutions/The-University-of-Texas-Permian-Basin/json/2025-2026/courses-56458BC7-2887-4C10-9CD8-09BB773BE97A.json"
DB_PATH = Path("data/courses.db")
ARCHIVE_DIR = Path("data/archive")


# just for the CLI arguments, we can just call without argument as well
def parse_args():
    parser = argparse.ArgumentParser(description="Scrape UTPB courses into SQLite.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--subject", help="Subject code (example: COSC)")
    group.add_argument("--all-subjects", action="store_true", help="Scrape all subjects")
    return parser.parse_args()


def get_json(url):
    with urlopen(url) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    args = parse_args()
    subjects_data = get_json(SUBJECTS_URL)
    if not subjects_data:
        print("No subjects found. Exiting.")
        return

    subjects = []
    subject_by_id = {}
    valid_codes = set()
    for item in subjects_data:
        subject = {
            "id": str(item["id"]).strip(),
            "code": str(item["code"]).strip().upper(),
            "name": str(item["name"]).strip(),
        }
        subjects.append(subject)
        subject_by_id[subject["id"]] = subject
        valid_codes.add(subject["code"])

    if args.all_subjects:
        selected_codes = valid_codes
    elif args.subject:
        code = args.subject.strip().upper()
        if code not in valid_codes:
            print(f"Unknown subject code: {code}")
            print("Valid codes:", ", ".join(sorted(valid_codes)))
            raise SystemExit(2)
        selected_codes = {code}
    else:
        sorted_subjects = sorted(subjects, key=lambda s: s["code"])
        print("Available subjects:")
        for i, subject in enumerate(sorted_subjects, start=1):
            print(f"{i:>2}. {subject['name']}")

        all_option = len(sorted_subjects) + 1
        exit_option = len(sorted_subjects) + 2
        print(f"{all_option:>2}. ALL")
        print(f"{exit_option:>2}. EXIT")

        while True:
            user_input = input("\nEnter the number of the subject to scrape: ").strip()
            if not user_input.isdigit():
                print("Please enter a number.")
                continue

            choice = int(user_input)
            if 1 <= choice <= len(sorted_subjects):
                selected_codes = {sorted_subjects[choice - 1]["code"]}
                break
            if choice == all_option:
                selected_codes = valid_codes
                break
            if choice == exit_option:
                print("Exiting.")
                return
            print(f"Please choose a number between 1 and {exit_option}.")

    label = "ALL" if args.all_subjects else ", ".join(sorted(selected_codes))

    print(f"Selected subject scope: {label}")
    print("Loading course data...")
    courses_data = get_json(COURSES_URL)
    rows = []
    seen = set()
    for item in courses_data:
        subject_id = str(item.get("subjectId", "")).strip()
        if subject_id not in subject_by_id:
            continue

        subject = subject_by_id[subject_id]
        if subject["code"] not in selected_codes:
            continue

        course_number = re.sub(r"\s+", " ", str(item.get("number", ""))).strip()
        course_name = re.sub(r"\s+", " ", str(item.get("name", ""))).strip()
        if not course_number or not course_name:
            continue

        course_code = f"{subject['code']} {course_number}"
        relative_or_full_url = re.sub(r"\s+", " ", str(item.get("url", ""))).strip()
        course_url = urljoin(BASE_URL, relative_or_full_url) if relative_or_full_url else ""
        prerequisites = ""
        term_offered = ""
        if course_url:
            try:
                page_html = urlopen(course_url.lower()).read().decode("utf-8", "ignore")
                prereq_match = re.search(r"<div class=\"sc_prereqs\">(.*?)</div>\s*<div class=\"sc_coreqs\">", page_html, re.IGNORECASE | re.DOTALL)
                if prereq_match:
                    prereq_block = prereq_match.group(1)
                    prereq_text = re.sub(r"<[^>]+>", " ", prereq_block)
                    prereq_text = unescape(re.sub(r"\s+", " ", prereq_text)).strip()
                    prerequisites = re.sub(r"^Prerequisites?\s*[:\-]?\s*", "", prereq_text, flags=re.IGNORECASE).strip()

                term_match = re.search(r"<h[23]>\s*Terms?\s+Offered\s*</h[23]>\s*(.*?)</div>", page_html, re.IGNORECASE | re.DOTALL)
                if term_match:
                    term_block = term_match.group(1)
                    term_text = re.sub(r"<[^>]+>", " ", term_block)
                    term_offered = unescape(re.sub(r"\s+", " ", term_text)).strip()
                else:
                    sentence_match = re.search(r"(traditionally offered[^<\.]*\.?)", page_html, re.IGNORECASE)
                    if sentence_match:
                        term_offered = unescape(re.sub(r"\s+", " ", sentence_match.group(1))).strip()
            except Exception:
                prerequisites = ""
                term_offered = ""
        key = (course_code, course_name, course_url)
        if key in seen:
            continue

        seen.add(key)
        rows.append(
            {
                "subject_code": subject["code"],
                "course_number": course_number,
                "course_code": course_code,
                "course_name": course_name,
                "course_url": course_url,
                "prerequisites": prerequisites,
                "term_offered": term_offered,
            }
        )

    def sort_key(row):
        digits = "".join(ch for ch in row["course_number"] if ch.isdigit())
        num = int(digits) if digits else 10**9
        return (row["subject_code"], num, row["course_name"])

    rows.sort(key=sort_key)
    if not rows:
        print("No course rows found for selected scope. Exiting.")
        return

    archived_path = None
    if DB_PATH.exists():
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archived_path = ARCHIVE_DIR / f"courses_{timestamp}.db"
        counter = 1
        while archived_path.exists():
            archived_path = ARCHIVE_DIR / f"courses_{timestamp}_{counter}.db"
            counter += 1
        DB_PATH.replace(archived_path)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    inserted = 0
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS courses (id INTEGER PRIMARY KEY AUTOINCREMENT, subject_code TEXT NOT NULL, course_number TEXT NOT NULL, course_code TEXT NOT NULL, course_name TEXT NOT NULL, course_url TEXT NOT NULL, prerequisites TEXT, term_offered TEXT, UNIQUE(course_code, course_name, course_url))")
        # this should santinze the input even if we don't need to for scrapping 
        for row in rows:
            cursor = conn.execute("INSERT OR IGNORE INTO courses (subject_code, course_number, course_code, course_name, course_url, prerequisites, term_offered) VALUES (?, ?, ?, ?, ?, ?, ?)", (row["subject_code"], row["course_number"], row["course_code"], row["course_name"], row["course_url"], row["prerequisites"], row["term_offered"]))
            inserted += cursor.rowcount
        conn.commit()

    print("\nDone.")
    print(f"Scraped rows: {len(rows)}")
    print(f"Inserted rows: {inserted}")
    print(f"Database: {DB_PATH}")
    print(f"Archived previous DB: {archived_path if archived_path else 'none'}")


if __name__ == "__main__":
    main()
