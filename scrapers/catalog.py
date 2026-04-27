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
DEFAULT_DB = "data/courses.db"
ARCHIVE_DIR = Path("data/archive")
REQUEST_TIMEOUT_SECONDS = 10

COURSES_DDL = """
CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_code TEXT NOT NULL,
    course_number TEXT NOT NULL,
    course_code TEXT NOT NULL,
    course_name TEXT NOT NULL,
    course_url TEXT NOT NULL,
    prerequisites TEXT,
    UNIQUE(course_code, course_name, course_url)
)
"""


def _maybe_backup_full_db(db_path: Path, selected_label: str):
    """Optional full-file snapshot (users, sections, and courses stay in one file)."""
    if not db_path.is_file():
        return None
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", selected_label)[:40]
    name = f"courses_full_{timestamp}_{safe}.db" if safe else f"courses_full_{timestamp}.db"
    dest = ARCHIVE_DIR / name
    counter = 1
    while dest.exists():
        dest = ARCHIVE_DIR / f"courses_full_{timestamp}_{counter}.db"
        counter += 1
    dest.write_bytes(db_path.read_bytes())
    return dest


def build_parser():
    parser = argparse.ArgumentParser(description="Scrape UTPB courses into SQLite.")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to SQLite DB")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--subject", help="Subject code (example: COSC)")
    group.add_argument("--all-subjects", action="store_true", dest="all_subjects", help="Scrape all subjects")
    parser.add_argument(
        "--backup-db",
        action="store_true",
        help="Copy the entire database file to data/archive/ before updating the courses table.",
    )
    return parser


def parse_args(argv=None):
    return build_parser().parse_args(argv)


def get_json(url):
    with urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def run(args):
    db_path = Path(args.db)
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

    if selected_codes == valid_codes:
        label = "ALL"
    else:
        label = ", ".join(sorted(selected_codes))
    fetch_details = not args.all_subjects

    print(f"Selected subject scope: {label}")
    print("Loading course data...")
    if not fetch_details:
        print("All-subject mode: skipping slow detail-page fetch for prerequisites.")
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
        if course_url and fetch_details:
            try:
                page_html = urlopen(course_url.lower(), timeout=REQUEST_TIMEOUT_SECONDS).read().decode("utf-8", "ignore")
                prereq_match = re.search(r"<div class=\"sc_prereqs\">(.*?)</div>\s*<div class=\"sc_coreqs\">", page_html, re.IGNORECASE | re.DOTALL)
                if prereq_match:
                    prereq_block = prereq_match.group(1)
                    prereq_text = re.sub(r"<[^>]+>", " ", prereq_block)
                    prereq_text = unescape(re.sub(r"\s+", " ", prereq_text)).strip()
                    prerequisites = re.sub(r"^Prerequisites?\s*[:\-]?\s*", "", prereq_text, flags=re.IGNORECASE).strip()
            except Exception:
                prerequisites = ""
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

    scope_is_all = selected_codes == valid_codes
    scope_key = "ALL" if scope_is_all else ",".join(sorted(selected_codes))

    backup_path = None
    if args.backup_db:
        backup_path = _maybe_backup_full_db(db_path, scope_key)
        if backup_path:
            print(f"Full database backup: {backup_path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)

    inserted = 0
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(COURSES_DDL)
        if scope_is_all:
            conn.execute("DELETE FROM courses")
        else:
            for code in selected_codes:
                conn.execute("DELETE FROM courses WHERE subject_code = ?", (code,))

        for row in rows:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO courses (subject_code, course_number, course_code, course_name, course_url, prerequisites) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    row["subject_code"],
                    row["course_number"],
                    row["course_code"],
                    row["course_name"],
                    row["course_url"],
                    row["prerequisites"],
                ),
            )
            inserted += cursor.rowcount
        conn.commit()

    print("\nDone.")
    print(f"Scraped rows: {len(rows)}")
    print(f"New rows inserted (duplicates in scrape ignored by UNIQUE): {inserted}")
    print(f"Database: {db_path.resolve()}")
    if args.backup_db and not backup_path:
        print("Full database backup: skipped (database file did not exist yet).")
    print("Note: other tables (sections, user accounts, schedules) in this file were not removed.")


def main(argv=None):
    run(parse_args(argv))


if __name__ == "__main__":
    main()
