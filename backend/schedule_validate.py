"""
Detect time conflicts between class sections using days + start/end times.
Online / TBA-style rows (no concrete meeting pattern) are treated as non-conflicting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


DAY_INDEX = {"M": 0, "T": 1, "W": 2, "R": 3, "F": 4, "S": 5, "U": 6}


def parse_days(raw: str | None) -> frozenset[int]:
    if not raw:
        return frozenset()
    u = raw.strip().upper()
    if u == "ONLINE" or u == "TBA":
        return frozenset()
    found: set[int] = set()
    for ch in u:
        if ch in DAY_INDEX:
            found.add(DAY_INDEX[ch])
    return frozenset(found)


def parse_seconds(hms: str | None) -> int | None:
    if not hms:
        return None
    parts = str(hms).split(":")
    try:
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        s = int(parts[2]) if len(parts) > 2 else 0
        return h * 3600 + m * 60 + s
    except (ValueError, IndexError):
        return None


def has_meeting_pattern(days: frozenset[int], start: int | None, end: int | None) -> bool:
    return bool(days) and start is not None and end is not None and start < end


def intervals_overlap(a0: int, a1: int, b0: int, b1: int) -> bool:
    return not (a1 <= b0 or b1 <= a0)


def sections_conflict(
    days_a: frozenset[int],
    start_a: int | None,
    end_a: int | None,
    days_b: frozenset[int],
    start_b: int | None,
    end_b: int | None,
) -> bool:
    if not has_meeting_pattern(days_a, start_a, end_a):
        return False
    if not has_meeting_pattern(days_b, start_b, end_b):
        return False
    common = days_a & days_b
    if not common:
        return False
    return intervals_overlap(start_a, end_a, start_b, end_b)


@dataclass(frozen=True)
class SectionLite:
    section_id: int
    course_code: str
    section_code: str | None
    days: str | None
    start_time: str | None
    end_time: str | None
    delivery_mode: str | None


def find_conflicts(sections: Iterable[SectionLite]) -> list[tuple[SectionLite, SectionLite]]:
    lst = list(sections)
    out: list[tuple[SectionLite, SectionLite]] = []
    for i in range(len(lst)):
        for j in range(i + 1, len(lst)):
            a, b = lst[i], lst[j]
            da, db = parse_days(a.days), parse_days(b.days)
            sa, ea = parse_seconds(a.start_time), parse_seconds(a.end_time)
            sb, eb = parse_seconds(b.start_time), parse_seconds(b.end_time)
            if sections_conflict(da, sa, ea, db, sb, eb):
                out.append((a, b))
    return out
