"""
Parse UTPB public class schedule HTML (general.utpb.edu/schedule).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from backend.config import schedule_base_url


@dataclass
class ScheduleSection:
    class_nbr: str
    course_code: str
    schedule_title: str
    credits: int
    section_code: str
    instructor: str | None
    days: str | None
    start_time: str | None
    end_time: str | None
    room_number: str | None
    delivery_mode: str | None
    enrolled: int | None
    seat_limit: int | None
    semester_label: str


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": "UtpbSchedulerScheduleSync/1.0 (educational; +local)",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return s


def _parse_time_cell(raw: str) -> str | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        t = datetime.strptime(raw, "%I:%M %p").time()
        return t.strftime("%H:%M:%S")
    except ValueError:
        return None


def _normalize_empty(s: str | None) -> str | None:
    if s is None:
        return None
    s = s.strip()
    return s if s else None


def _parse_int_cell(raw: str) -> int | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def _parse_credits_cell(raw: str) -> int:
    raw = (raw or "").strip()
    if not raw:
        return 0
    try:
        return int(round(float(raw)))
    except ValueError:
        return 0


def fetch_schedule_sections(
    term: str, semester_label: str, subject: str = "COSC"
) -> list[ScheduleSection]:
    session = _session()
    try:
        url = f"{schedule_base_url()}?term={term}"
        r = session.get(url, timeout=90)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        out: list[ScheduleSection] = []

        for tr in soup.find_all("tr"):
            tds = tr.find_all("td", recursive=False)
            if len(tds) < 18:
                continue
            cells = [td.get_text(strip=True) for td in tds]
            if cells[1] != subject:
                continue

            subj, num = cells[1], cells[2]
            course_code = f"{subj} {num}"

            out.append(
                ScheduleSection(
                    class_nbr=cells[0],
                    course_code=course_code,
                    schedule_title=(cells[4] or course_code)[:255],
                    credits=_parse_credits_cell(cells[7]),
                    section_code=cells[3],
                    instructor=_normalize_empty(cells[8]),
                    days=_normalize_empty(cells[9]),
                    start_time=_parse_time_cell(cells[10]),
                    end_time=_parse_time_cell(cells[11]),
                    room_number=_normalize_empty(cells[12]),
                    delivery_mode=_normalize_empty(cells[17]),
                    enrolled=_parse_int_cell(cells[13]),
                    seat_limit=_parse_int_cell(cells[14]),
                    semester_label=semester_label,
                )
            )

        return out
    finally:
        session.close()
