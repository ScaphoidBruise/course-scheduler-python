"""
Build the database from COSC rows on general.utpb.edu/schedule (not the full catalog).

For each term in SCHEDULE_TERM_MAP, downloads the public schedule and imports sections.
Course rows are only those that appear on the schedule. Descriptions and prerequisites
are backfilled from SmartCatalog when a matching COSC page exists.

  python scripts/sync_catalog_to_mysql.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import schedule_subject, schedule_term_specs
from backend.db import connect, sql_placeholder
from scraper.catalog_scraper import _session as catalog_session, fetch_catalog_for_course_codes
from scraper.schedule_scraper import fetch_schedule_sections


def main() -> None:
    specs = schedule_term_specs()
    subj = schedule_subject()
    if not specs:
        print(
            "Set SCHEDULE_TERM_MAP in .env, e.g.\n"
            "  SCHEDULE_TERM_MAP=2262:Spring 2026|2265:Summer 2026|2268:Fall 2026\n"
            "or set SCHEDULE_TERM + SCHEDULE_SEMESTER_LABEL for a single term."
        )
        return

    all_sections: list = []
    for term, label in specs:
        rows = fetch_schedule_sections(term, label, subj)
        all_sections.extend(rows)
        print(f"Fetched {len(rows)} {subj} sections for {label} (term={term}).")

    if not all_sections:
        print("No schedule rows found; check term codes on utpb.edu course schedules page.")
        return

    codes = {s.course_code for s in all_sections}
    course_title_credits: dict[str, tuple[str, int]] = {}
    for s in all_sections:
        if s.course_code not in course_title_credits:
            course_title_credits[s.course_code] = (s.schedule_title, s.credits)

    cat_by_code: dict = {}
    sess = catalog_session()
    try:
        try:
            recs = fetch_catalog_for_course_codes(sess, codes)
            for r in recs:
                cat_by_code[r.course_code] = r
            print(f"Catalog backfill: {len(cat_by_code)} courses with descriptions/prereqs.")
        except Exception as e:
            print(f"Catalog backfill skipped ({e}); using schedule titles only.")
    finally:
        sess.close()

    conn, backend = connect()
    ph = sql_placeholder(backend)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM prerequisites")
        cur.execute("DELETE FROM sections")
        cur.execute("DELETE FROM courses")

        insert_course = f"""
            INSERT INTO courses (course_code, title, credits, description)
            VALUES ({ph}, {ph}, {ph}, {ph})
            """
        for code in sorted(codes):
            title, cr = course_title_credits[code]
            desc = None
            if code in cat_by_code:
                c = cat_by_code[code]
                title = c.title
                if c.credits:
                    cr = c.credits
                desc = c.description or None
            cur.execute(insert_course, (code, title, cr, desc))

        ignore = "INSERT OR IGNORE INTO" if backend == "sqlite" else "INSERT IGNORE INTO"
        insert_prereq = f"""
            {ignore} prerequisites (course_code, prereq_code)
            VALUES ({ph}, {ph})
            """
        for code, c in cat_by_code.items():
            for pq in c.prereq_codes:
                if pq not in codes:
                    continue
                cur.execute(insert_prereq, (code, pq))

        insert_sec = f"""
            INSERT INTO sections (
                course_code, semester, section_code, instructor, days,
                start_time, end_time, room_number, delivery_mode,
                enrolled, seat_limit
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
            """
        for sec in all_sections:
            cur.execute(
                insert_sec,
                (
                    sec.course_code,
                    sec.semester_label,
                    sec.section_code,
                    sec.instructor,
                    sec.days,
                    sec.start_time,
                    sec.end_time,
                    sec.room_number,
                    sec.delivery_mode,
                    sec.enrolled,
                    sec.seat_limit,
                ),
            )

        conn.commit()
        print(
            f"Done: {len(codes)} courses, {len(all_sections)} sections ({backend}). "
            "Source: UTPB public schedule + optional SmartCatalog backfill."
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
