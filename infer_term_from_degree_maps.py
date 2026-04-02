import argparse
import io
import re
import sqlite3
from urllib.parse import urljoin
from urllib.request import urlopen


DEFAULT_DB = "data/courses.db"
DEFAULT_FALCON_URL = "https://www.utpb.edu/falcon-maps/"


def parse_args():
    parser = argparse.ArgumentParser(description="Infer term_infered from UTPB degree map PDFs.")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to SQLite DB")
    parser.add_argument("--falcon-url", default=DEFAULT_FALCON_URL, help="Falcon Maps page URL")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-PDF progress logs")
    return parser.parse_args()


def fetch_text(url):
    return urlopen(url).read().decode("utf-8", "ignore")


def extract_pdf_links(html, base_url):
    links = []
    seen = set()
    for token in re.split(r"[\"']", html):
        t = token.strip()
        if ".pdf" not in t.lower():
            continue
        if "/falcon-maps/" not in t.lower() and "utpb.edu" not in t.lower():
            continue
        full = urljoin(base_url, t)
        if full in seen:
            continue
        seen.add(full)
        links.append(full)
    return links


def normalize_code(raw):
    match = re.search(r"\b([A-Z]{3,4})\s*-?\s*(\d{4}[A-Z]?)\b", raw.upper())
    if not match:
        return ""
    return f"{match.group(1)} {match.group(2)}"


def infer_for_pdf(pdf_url, reader_cls):
    data = urlopen(pdf_url).read()
    if not data.lstrip().startswith(b"%PDF"):
        return {}
    reader = reader_cls(io.BytesIO(data))

    # Most map page 1 is advising fluff; page 2+ usually has semester grid.
    pages = reader.pages[1:] if len(reader.pages) > 1 else reader.pages
    text = "\n".join((page.extract_text() or "") for page in pages)
    if not text.strip():
        return {}

    # Focus on the semester grid region to avoid falsely assigning
    # trailing track/elective notes to the last semester.
    work = text
    start_idx = re.search(r"Education\s+Requirements", work, flags=re.IGNORECASE)
    if start_idx:
        work = work[start_idx.start() :]

    stop_markers = [
        r"Three\s+Tracks\s+are\s+offered",
        r"Skills\s+Learned\s+Upon\s+Graduation",
        r"Career\s+Opportunities",
        r"Complete\s+a\s+total\s+of\s+at\s+least",
    ]
    stop_pos = len(work)
    for marker in stop_markers:
        m = re.search(marker, work, flags=re.IGNORECASE)
        if m and m.start() < stop_pos:
            stop_pos = m.start()
    work = work[:stop_pos]

    local_hits = {}  # course_code -> {"Fall": int, "Spring": int}
    star_term_map = {}  # "*" / "**" / "***" -> {"Fall","Spring"}

    def add_term_hit(code, term):
        if code not in local_hits:
            local_hits[code] = {"Fall": 0, "Spring": 0}
        local_hits[code][term] += 1

    def add_codes(chunk, term):
        raw_codes = re.findall(r"\b[A-Z]{3,4}\s*-?\s*\d{4}[A-Z]?\b", chunk.upper())
        for raw in raw_codes:
            code = normalize_code(raw)
            if not code:
                continue
            add_term_hit(code, term)

    # Preferred parsing: semester pairs ("Semester 1 Semester 2").
    pair_marks = list(re.finditer(r"Semester\s+(\d+)\s+Semester\s+(\d+)", work, flags=re.IGNORECASE))
    if pair_marks:
        for i, mark in enumerate(pair_marks):
            sem_a = int(mark.group(1))
            sem_b = int(mark.group(2))
            term_a = "Fall" if sem_a % 2 == 1 else "Spring"
            term_b = "Fall" if sem_b % 2 == 1 else "Spring"

            start = mark.end()
            end = pair_marks[i + 1].start() if i + 1 < len(pair_marks) else len(work)
            pair_chunk = work[start:end]

            # In these maps, HOURS separators usually split semester columns.
            hour_marks = list(re.finditer(r"\b\d+\s+HOURS\b", pair_chunk, flags=re.IGNORECASE))
            if hour_marks:
                sem_a_chunk = pair_chunk[: hour_marks[0].start()]
                if len(hour_marks) > 1:
                    sem_b_chunk = pair_chunk[hour_marks[0].end() : hour_marks[1].start()]
                else:
                    sem_b_chunk = pair_chunk[hour_marks[0].end() :]
            else:
                # Fallback if HOURS markers are missing.
                midpoint = len(pair_chunk) // 2
                sem_a_chunk = pair_chunk[:midpoint]
                sem_b_chunk = pair_chunk[midpoint:]

            add_codes(sem_a_chunk, term_a)
            add_codes(sem_b_chunk, term_b)

            # Capture star placeholders (Technical Elective*, **, ***).
            for star in re.findall(r"Technical\s+Elective\s*(\*{1,3})", sem_a_chunk, flags=re.IGNORECASE):
                star_term_map.setdefault(star, set()).add(term_a)
            for star in re.findall(r"Technical\s+Elective\s*(\*{1,3})", sem_b_chunk, flags=re.IGNORECASE):
                star_term_map.setdefault(star, set()).add(term_b)
    else:
        # Fallback parsing for maps without paired semester headings.
        sem_marks = list(re.finditer(r"Semester\s+(\d+)", work, flags=re.IGNORECASE))
        for i, mark in enumerate(sem_marks):
            sem_num = int(mark.group(1))
            term = "Fall" if sem_num % 2 == 1 else "Spring"
            start = mark.end()
            end = sem_marks[i + 1].start() if i + 1 < len(sem_marks) else len(work)
            chunk = work[start:end]
            add_codes(chunk, term)
            for star in re.findall(r"Technical\s+Elective\s*(\*{1,3})", chunk, flags=re.IGNORECASE):
                star_term_map.setdefault(star, set()).add(term)

    # Optional star-course mapping from track section.
    # Example: COSC 4470 ... ** should map to semester term of ** placeholder.
    track_start = re.search(r"Three\s+Tracks\s+are\s+offered", text, flags=re.IGNORECASE)
    if track_start and star_term_map:
        track_text = text[track_start.start() :]
        end_m = re.search(r"Complete\s+a\s+total\s+of\s+at\s+least", track_text, flags=re.IGNORECASE)
        if end_m:
            track_text = track_text[: end_m.start()]

        segments = re.split(r"[,;\n]+", track_text)
        for seg in segments:
            code = normalize_code(seg)
            if not code:
                continue
            stars = re.findall(r"(\*{1,3})", seg)
            if not stars:
                continue
            for star in stars:
                if star not in star_term_map:
                    continue
                for term in star_term_map[star]:
                    add_term_hit(code, term)

    return local_hits


def main():
    args = parse_args()

    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        print("Missing dependency: pypdf")
        print("Install with: .\\.venv\\Scripts\\pip install pypdf")
        return

    html = fetch_text(args.falcon_url)
    pdf_links = extract_pdf_links(html, args.falcon_url)
    if not args.quiet:
        print(f"Found {len(pdf_links)} PDF links on Falcon Maps.")
        print("PDF links to parse:")
        for idx, pdf_url in enumerate(pdf_links, start=1):
            pdf_name = pdf_url.rstrip("/").split("/")[-1]
            print(f"  {idx:>2}. {pdf_name}")
        print("")

    all_hits = {}  # course_code -> {"Fall": int, "Spring": int, "sources": set()}
    parsed = 0
    for idx, pdf_url in enumerate(pdf_links, start=1):
        if not args.quiet:
            print(f"[{idx}/{len(pdf_links)}] Parsing: {pdf_url}")
        try:
            pdf_hits = infer_for_pdf(pdf_url, PdfReader)
        except Exception as ex:
            if not args.quiet:
                print(f"  -> skipped ({ex})")
            continue

        parsed += 1
        if not args.quiet:
            print(f"  -> parsed, inferred codes in file: {len(pdf_hits)}")
        for code, terms in pdf_hits.items():
            if code not in all_hits:
                all_hits[code] = {"Fall": 0, "Spring": 0, "sources": set()}
            all_hits[code]["Fall"] += terms["Fall"]
            all_hits[code]["Spring"] += terms["Spring"]
            all_hits[code]["sources"].add(pdf_url)

    conn = sqlite3.connect(args.db)
    has_courses = conn.execute(
        "SELECT COUNT(1) FROM sqlite_master WHERE type='table' AND name='courses'"
    ).fetchone()[0]
    if not has_courses:
        conn.close()
        print("No 'courses' table found in DB.")
        print("Run scraper first: python scraper.py --all-subjects")
        return

    cols = [row[1] for row in conn.execute("PRAGMA table_info(courses)").fetchall()]
    if "term_infered" not in cols:
        conn.execute("ALTER TABLE courses ADD COLUMN term_infered TEXT")

    updated = 0
    for code, ev in all_hits.items():
        labels = []
        if ev["Fall"] > 0:
            labels.append("Fall")
        if ev["Spring"] > 0:
            labels.append("Spring")
        inferred = "/".join(labels) if labels else ""
        if not inferred:
            continue

        cursor = conn.execute(
            "UPDATE courses SET term_infered = ? WHERE course_code = ?",
            (inferred, code),
        )
        updated += cursor.rowcount

    conn.commit()
    conn.close()

    print("Done.")
    print("PDF links found:", len(pdf_links))
    print("PDFs parsed:", parsed)
    print("Courses with inferred evidence:", len(all_hits))
    print("Courses updated:", updated)


if __name__ == "__main__":
    main()
