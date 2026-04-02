"""
Fetch COSC course metadata from UTPB SmartCatalog (public JSON + HTML pages).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Iterator

import requests
from bs4 import BeautifulSoup

from backend.config import CATALOG_JSON_URL, SMARTCATALOG_BASE


@dataclass
class CourseRecord:
    course_code: str
    title: str
    credits: int
    description: str
    prereq_codes: list[str]


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": "UtpbSchedulerCourseSync/1.0 (educational; +local)",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return s


def load_catalog_tree(session: requests.Session) -> dict:
    r = session.get(CATALOG_JSON_URL, timeout=60)
    r.raise_for_status()
    return r.json()


def _find_cosc_root(node: dict) -> dict | None:
    path = node.get("Path") or ""
    if path.rstrip("/").endswith("/Courses/COSC-Computer-Science"):
        return node
    for child in node.get("Children") or []:
        found = _find_cosc_root(child)
        if found is not None:
            return found
    return None


def _iter_course_paths(node: dict) -> Iterator[str]:
    """Leaf paths under COSC subject (e.g. .../1000/COSC-1335)."""
    children = node.get("Children") or []
    if not children:
        p = node.get("Path") or ""
        if p:
            yield p
        return
    for child in children:
        yield from _iter_course_paths(child)


def _iter_cosc_course_nodes(node: dict) -> Iterator[tuple[str, str]]:
    """Yield (Path, Name) for each catalog leaf under the given COSC root."""
    children = node.get("Children") or []
    if not children:
        p = node.get("Path") or ""
        n = (node.get("Name") or "").strip()
        if p:
            yield p, n
        return
    for child in children:
        yield from _iter_cosc_course_nodes(child)


_CATALOG_NAME_CODE = re.compile(r"^([A-Z]{2,5})\s+(\d{4})$")


def catalog_name_to_course_code(name: str) -> str | None:
    m = _CATALOG_NAME_CODE.match((name or "").strip())
    if m:
        return f"{m.group(1)} {m.group(2)}"
    return None


def fetch_catalog_for_course_codes(
    session: requests.Session,
    codes: set[str],
    delay_sec: float = 0.35,
) -> list[CourseRecord]:
    """Fetch SmartCatalog HTML only for course codes in ``codes`` (prereqs + descriptions)."""
    tree = load_catalog_tree(session)
    cosc = _find_cosc_root(tree)
    if not cosc:
        raise RuntimeError("Could not find COSC-Computer-Science branch in catalog JSON.")

    records: list[CourseRecord] = []
    seen: set[str] = set()
    for path, name in _iter_cosc_course_nodes(cosc):
        cc = catalog_name_to_course_code(name)
        if not cc or cc not in codes or cc in seen:
            continue
        seen.add(cc)
        url = path_to_public_url(path)
        r = session.get(url, timeout=45)
        r.raise_for_status()
        rec = parse_course_page(r.text)
        if rec and rec.course_code in codes:
            records.append(rec)
        time.sleep(delay_sec)
    return records



def path_to_public_url(path: str) -> str:
    """Map JSON Path to browser URL."""
    p = path.strip("/").lower()
    return f"{SMARTCATALOG_BASE}/en/{p}"


_CODE_IN_SPAN = re.compile(r"^([A-Z]{2,5}\s+\d{4})\s*$")


def parse_course_page(html: str) -> CourseRecord | None:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    if not h1:
        return None

    span = h1.find("span")
    code = (span.get_text(strip=True) if span else "").strip()
    if span:
        title_rest = h1.get_text(" ", strip=True)
        code_from_span = span.get_text(strip=True)
        title = title_rest.replace(code_from_span, "", 1).strip()
    else:
        title = h1.get_text(" ", strip=True)
        m = re.match(r"^([A-Z]{2,5}\s+\d{4})\s+(.+)$", title)
        if m:
            code, title = m.group(1), m.group(2).strip()
        else:
            return None

    if not _CODE_IN_SPAN.match(code or ""):
        m = re.match(r"^([A-Z]{2,5})(\d{4})$", code.replace(" ", ""))
        if m:
            code = f"{m.group(1)} {m.group(2)}"

    desc_el = soup.select_one(".desc p")
    description = desc_el.get_text(" ", strip=True) if desc_el else ""

    credits_el = soup.select_one(".sc_credits .credits")
    credits_txt = credits_el.get_text(strip=True) if credits_el else "0"
    try:
        credits = int(re.sub(r"\D", "", credits_txt) or 0)
    except ValueError:
        credits = 0

    prereqs: list[str] = []
    for a in soup.select(".sc_prereqs a.sc-courselink"):
        text = a.get_text(strip=True)
        if re.match(r"^[A-Z]{2,5}\s+\d{4}$", text):
            prereqs.append(text)

    return CourseRecord(
        course_code=code,
        title=title[:255] if len(title) > 255 else title,
        credits=credits,
        description=description,
        prereq_codes=prereqs,
    )


def fetch_cosc_courses(
    session: requests.Session, delay_sec: float = 0.35
) -> list[CourseRecord]:
    tree = load_catalog_tree(session)
    cosc = _find_cosc_root(tree)
    if not cosc:
        raise RuntimeError("Could not find COSC-Computer-Science branch in catalog JSON.")

    records: list[CourseRecord] = []
    for path in _iter_course_paths(cosc):
        url = path_to_public_url(path)
        r = session.get(url, timeout=45)
        r.raise_for_status()
        rec = parse_course_page(r.text)
        if rec:
            records.append(rec)
        time.sleep(delay_sec)
    return records
