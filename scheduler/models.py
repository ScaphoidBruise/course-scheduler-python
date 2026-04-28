"""
Domain model classes for the UTPB Scheduler.

These three interacting classes provide an object-oriented interface over the
core scheduling logic, complementing the lower-level utilities in conflict.py.

Class relationships:
  - TermSchedule  contains a list of CourseSection objects
  - TermSchedule  uses ConflictReport to report results from .add()
  - ConflictReport references CourseSection objects that caused conflicts
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from conflict import find_conflicts, parse_days, parse_time, sections_conflict


@dataclass
class CourseSection:
    """Immutable snapshot of a course section's scheduling data.

    Constructed either directly or via :meth:`from_db_row` when working with
    rows returned by the database layer.
    """

    section_id: int
    course_code: str
    section_code: str
    days: str
    session: str
    start_time: Optional[str]
    end_time: Optional[str]
    credits: float
    mode: str = ""
    location: str = ""
    course_name: str = ""

    @classmethod
    def from_db_row(cls, row: dict) -> "CourseSection":
        """Construct a CourseSection from a database row dictionary."""
        try:
            credits = float(row.get("credits") or 0)
        except (TypeError, ValueError):
            credits = 0.0
        return cls(
            section_id=row.get("id", 0),
            course_code=row.get("course_code", ""),
            section_code=row.get("section_code", ""),
            days=row.get("days", ""),
            session=row.get("session", ""),
            start_time=row.get("start_time"),
            end_time=row.get("end_time"),
            credits=credits,
            mode=row.get("mode", ""),
            location=row.get("location", ""),
            course_name=row.get("course_name", ""),
        )

    def as_dict(self) -> dict:
        """Convert to a plain dict compatible with the conflict.py helpers."""
        return {
            "id": self.section_id,
            "course_code": self.course_code,
            "section_code": self.section_code,
            "days": self.days,
            "session": self.session,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "credits": str(self.credits),
            "mode": self.mode,
            "location": self.location,
            "course_name": self.course_name,
        }

    @property
    def is_online(self) -> bool:
        """True when the section has no scheduled meeting days (async)."""
        return not bool(parse_days(self.days))

    @property
    def start_minutes(self) -> Optional[int]:
        """Start time as minutes since midnight, or None for async sections."""
        return parse_time(self.start_time)

    @property
    def end_minutes(self) -> Optional[int]:
        """End time as minutes since midnight, or None for async sections."""
        return parse_time(self.end_time)

    def __str__(self) -> str:
        return f"{self.course_code} {self.section_code} ({self.days} {self.start_time}–{self.end_time})"


@dataclass
class ConflictReport:
    """Result of checking a new section against an existing TermSchedule.

    Returned by :meth:`TermSchedule.add` so callers can inspect which existing
    sections (if any) conflict with the one just added.
    """

    new_section: CourseSection
    conflicts: list[CourseSection] = field(default_factory=list)

    @property
    def has_conflicts(self) -> bool:
        """True when at least one existing section conflicts with the new one."""
        return bool(self.conflicts)

    @property
    def conflicting_codes(self) -> list[str]:
        """Course codes of all sections that conflict with the new section."""
        return [s.course_code for s in self.conflicts]

    def __str__(self) -> str:
        if not self.has_conflicts:
            return f"No conflicts for {self.new_section.course_code}"
        codes = ", ".join(self.conflicting_codes)
        return f"{self.new_section.course_code} conflicts with: {codes}"


class TermSchedule:
    """Manages a collection of :class:`CourseSection` objects for one term.

    Wraps the functional helpers in ``conflict.py`` with an object-oriented
    interface.  Sections are stored in insertion order and never silently
    dropped — conflicts are reported but do not prevent enrollment, mirroring
    the behaviour of the web UI.

    Example usage::

        schedule = TermSchedule("Fall 2026")
        sec = CourseSection(1, "COSC 3320", "001", "MW", "1", "9:00 AM", "10:15 AM", 3.0)
        report = schedule.add(sec)
        if report.has_conflicts:
            print(report)
        print(f"Total credits: {schedule.total_credits}")
    """

    def __init__(self, term_label: str) -> None:
        self.term_label = term_label
        self._sections: list[CourseSection] = []

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def add(self, section: CourseSection) -> ConflictReport:
        """Add *section* to the schedule and return a :class:`ConflictReport`.

        The section is always added regardless of conflicts so the schedule
        reflects the user's actual intent.
        """
        existing_dicts = [s.as_dict() for s in self._sections]
        raw_conflicts = find_conflicts(section.as_dict(), existing_dicts)
        conflict_sections = [
            s
            for s in self._sections
            if s.section_id in {c.get("id") for c in raw_conflicts}
        ]
        self._sections.append(section)
        return ConflictReport(new_section=section, conflicts=conflict_sections)

    def remove(self, section_id: int) -> bool:
        """Remove a section by ID.  Returns True if the section was found."""
        before = len(self._sections)
        self._sections = [s for s in self._sections if s.section_id != section_id]
        return len(self._sections) < before

    def clear(self) -> None:
        """Remove all sections from the schedule."""
        self._sections = []

    # ------------------------------------------------------------------
    # Read-only views
    # ------------------------------------------------------------------

    @property
    def sections(self) -> list[CourseSection]:
        """Ordered copy of all sections currently in the schedule."""
        return list(self._sections)

    @property
    def total_credits(self) -> float:
        """Sum of credit hours for all sections in the schedule."""
        return sum(s.credits for s in self._sections)

    @property
    def section_count(self) -> int:
        """Number of sections currently in the schedule."""
        return len(self._sections)

    def conflicts_in_schedule(self) -> list[tuple[CourseSection, CourseSection]]:
        """Return all conflicting pairs within the current schedule.

        Each pair (a, b) appears only once (a before b in insertion order).
        """
        pairs: list[tuple[CourseSection, CourseSection]] = []
        items = self._sections
        for i, a in enumerate(items):
            for b in items[i + 1 :]:
                if sections_conflict(a.as_dict(), b.as_dict()):
                    pairs.append((a, b))
        return pairs

    def __repr__(self) -> str:
        return (
            f"TermSchedule(term={self.term_label!r}, "
            f"sections={self.section_count}, "
            f"credits={self.total_credits})"
        )
