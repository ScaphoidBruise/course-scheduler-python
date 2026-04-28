"""
Tests for scheduler/models.py.

Verifies CourseSection, ConflictReport, and TermSchedule work correctly
as an object-oriented layer on top of conflict.py.
"""

import sys
import unittest
from pathlib import Path

SCHEDULER = Path(__file__).resolve().parents[1] / "scheduler"
if str(SCHEDULER) not in sys.path:
    sys.path.insert(0, str(SCHEDULER))

from models import ConflictReport, CourseSection, TermSchedule  # noqa: E402


def _section(sid, code, days, start, end, session="1", credits=3.0):
    return CourseSection(
        section_id=sid,
        course_code=code,
        section_code="001",
        days=days,
        session=session,
        start_time=start,
        end_time=end,
        credits=credits,
    )


class CourseSectionTests(unittest.TestCase):
    def test_from_db_row(self):
        row = {
            "id": 42,
            "course_code": "COSC 3320",
            "section_code": "001",
            "days": "MW",
            "session": "1",
            "start_time": "9:00 AM",
            "end_time": "10:15 AM",
            "credits": "3.00",
            "mode": "Face-to-Face",
            "location": "MESA 100",
            "course_name": "Python Programming",
        }
        sec = CourseSection.from_db_row(row)
        self.assertEqual(sec.section_id, 42)
        self.assertEqual(sec.course_code, "COSC 3320")
        self.assertAlmostEqual(sec.credits, 3.0)
        self.assertEqual(sec.mode, "Face-to-Face")

    def test_from_db_row_invalid_credits_defaults_zero(self):
        row = {"id": 1, "course_code": "COSC 3320", "credits": "N/A"}
        sec = CourseSection.from_db_row(row)
        self.assertEqual(sec.credits, 0.0)

    def test_from_db_row_missing_credits_defaults_zero(self):
        row = {"id": 1, "course_code": "COSC 3320"}
        sec = CourseSection.from_db_row(row)
        self.assertEqual(sec.credits, 0.0)

    def test_is_online_true_when_no_days(self):
        sec = _section(1, "COSC 3320", "", "9:00 AM", "10:15 AM")
        self.assertTrue(sec.is_online)

    def test_is_online_false_when_has_days(self):
        sec = _section(1, "COSC 3320", "MW", "9:00 AM", "10:15 AM")
        self.assertFalse(sec.is_online)

    def test_start_minutes(self):
        sec = _section(1, "COSC 3320", "MW", "9:00 AM", "10:15 AM")
        self.assertEqual(sec.start_minutes, 540)

    def test_end_minutes(self):
        sec = _section(1, "COSC 3320", "MW", "9:00 AM", "10:15 AM")
        self.assertEqual(sec.end_minutes, 615)

    def test_start_minutes_none_for_no_time(self):
        sec = _section(1, "COSC 3320", "MW", None, None)
        self.assertIsNone(sec.start_minutes)

    def test_as_dict_roundtrip(self):
        sec = _section(99, "MATH 2413", "TR", "11:00 AM", "12:15 PM")
        d = sec.as_dict()
        self.assertEqual(d["id"], 99)
        self.assertEqual(d["course_code"], "MATH 2413")
        self.assertEqual(d["days"], "TR")

    def test_str_representation(self):
        sec = _section(1, "COSC 3320", "MW", "9:00 AM", "10:15 AM")
        s = str(sec)
        self.assertIn("COSC 3320", s)
        self.assertIn("MW", s)


class ConflictReportTests(unittest.TestCase):
    def test_no_conflicts(self):
        sec = _section(1, "COSC 3320", "MW", "9:00 AM", "10:15 AM")
        report = ConflictReport(new_section=sec, conflicts=[])
        self.assertFalse(report.has_conflicts)
        self.assertEqual(report.conflicting_codes, [])

    def test_has_conflicts(self):
        sec_a = _section(1, "COSC 3320", "MW", "9:00 AM", "10:15 AM")
        sec_b = _section(2, "MATH 2413", "MW", "9:30 AM", "10:45 AM")
        report = ConflictReport(new_section=sec_b, conflicts=[sec_a])
        self.assertTrue(report.has_conflicts)
        self.assertIn("COSC 3320", report.conflicting_codes)

    def test_str_no_conflicts(self):
        sec = _section(1, "COSC 3320", "MW", "9:00 AM", "10:15 AM")
        report = ConflictReport(new_section=sec)
        self.assertIn("No conflicts", str(report))

    def test_str_with_conflicts(self):
        sec_a = _section(1, "COSC 3320", "MW", "9:00 AM", "10:15 AM")
        sec_b = _section(2, "MATH 2413", "MW", "9:30 AM", "10:45 AM")
        report = ConflictReport(new_section=sec_b, conflicts=[sec_a])
        s = str(report)
        self.assertIn("MATH 2413", s)
        self.assertIn("COSC 3320", s)


class TermScheduleTests(unittest.TestCase):
    def test_initial_state(self):
        schedule = TermSchedule("Fall 2026")
        self.assertEqual(schedule.term_label, "Fall 2026")
        self.assertEqual(schedule.section_count, 0)
        self.assertEqual(schedule.total_credits, 0.0)

    def test_add_single_section(self):
        schedule = TermSchedule("Fall 2026")
        sec = _section(1, "COSC 3320", "MW", "9:00 AM", "10:15 AM", credits=3.0)
        report = schedule.add(sec)
        self.assertFalse(report.has_conflicts)
        self.assertEqual(schedule.section_count, 1)
        self.assertEqual(schedule.total_credits, 3.0)

    def test_add_non_conflicting_sections(self):
        schedule = TermSchedule("Fall 2026")
        sec_a = _section(1, "COSC 3320", "MW", "9:00 AM", "10:15 AM")
        sec_b = _section(2, "MATH 2413", "TR", "9:00 AM", "10:15 AM")
        schedule.add(sec_a)
        report = schedule.add(sec_b)
        self.assertFalse(report.has_conflicts)
        self.assertEqual(schedule.section_count, 2)

    def test_add_conflicting_section_detected(self):
        schedule = TermSchedule("Fall 2026")
        sec_a = _section(1, "COSC 3320", "MW", "9:00 AM", "10:15 AM")
        sec_b = _section(2, "MATH 2413", "MW", "9:30 AM", "10:45 AM")
        schedule.add(sec_a)
        report = schedule.add(sec_b)
        self.assertTrue(report.has_conflicts)
        self.assertIn("COSC 3320", report.conflicting_codes)

    def test_add_does_not_reject_conflict(self):
        schedule = TermSchedule("Fall 2026")
        sec_a = _section(1, "COSC 3320", "MW", "9:00 AM", "10:15 AM")
        sec_b = _section(2, "MATH 2413", "MW", "9:30 AM", "10:45 AM")
        schedule.add(sec_a)
        schedule.add(sec_b)
        self.assertEqual(schedule.section_count, 2)

    def test_remove_section(self):
        schedule = TermSchedule("Fall 2026")
        sec = _section(1, "COSC 3320", "MW", "9:00 AM", "10:15 AM")
        schedule.add(sec)
        removed = schedule.remove(1)
        self.assertTrue(removed)
        self.assertEqual(schedule.section_count, 0)

    def test_remove_nonexistent_returns_false(self):
        schedule = TermSchedule("Fall 2026")
        self.assertFalse(schedule.remove(999))

    def test_clear(self):
        schedule = TermSchedule("Fall 2026")
        schedule.add(_section(1, "COSC 3320", "MW", "9:00 AM", "10:15 AM"))
        schedule.add(_section(2, "MATH 2413", "TR", "9:00 AM", "10:15 AM"))
        schedule.clear()
        self.assertEqual(schedule.section_count, 0)
        self.assertEqual(schedule.total_credits, 0.0)

    def test_sections_property_returns_copy(self):
        schedule = TermSchedule("Fall 2026")
        sec = _section(1, "COSC 3320", "MW", "9:00 AM", "10:15 AM")
        schedule.add(sec)
        copy = schedule.sections
        copy.clear()
        self.assertEqual(schedule.section_count, 1)

    def test_total_credits_multiple(self):
        schedule = TermSchedule("Fall 2026")
        schedule.add(_section(1, "COSC 3320", "MW", "9:00 AM", "10:15 AM", credits=3.0))
        schedule.add(_section(2, "MATH 2413", "TR", "9:00 AM", "10:15 AM", credits=4.0))
        self.assertEqual(schedule.total_credits, 7.0)

    def test_conflicts_in_schedule_none(self):
        schedule = TermSchedule("Fall 2026")
        schedule.add(_section(1, "COSC 3320", "MW", "9:00 AM", "10:15 AM"))
        schedule.add(_section(2, "MATH 2413", "TR", "9:00 AM", "10:15 AM"))
        self.assertEqual(schedule.conflicts_in_schedule(), [])

    def test_conflicts_in_schedule_found(self):
        schedule = TermSchedule("Fall 2026")
        schedule.add(_section(1, "COSC 3320", "MW", "9:00 AM", "10:15 AM"))
        schedule.add(_section(2, "MATH 2413", "MW", "9:30 AM", "10:45 AM"))
        pairs = schedule.conflicts_in_schedule()
        self.assertEqual(len(pairs), 1)

    def test_repr(self):
        schedule = TermSchedule("Fall 2026")
        r = repr(schedule)
        self.assertIn("Fall 2026", r)
        self.assertIn("sections=0", r)

    def test_online_section_no_conflict_with_in_person(self):
        schedule = TermSchedule("Fall 2026")
        in_person = _section(1, "COSC 3320", "MW", "9:00 AM", "10:15 AM")
        online = _section(2, "MATH 2413", "", "9:00 AM", "10:15 AM")
        schedule.add(in_person)
        report = schedule.add(online)
        self.assertFalse(report.has_conflicts)

    def test_half_semester_no_conflict_between_sessions(self):
        schedule = TermSchedule("Fall 2026")
        s1 = _section(1, "COSC 3320", "MW", "9:00 AM", "10:15 AM", session="8W1")
        s2 = _section(2, "MATH 2413", "MW", "9:00 AM", "10:15 AM", session="8W2")
        schedule.add(s1)
        report = schedule.add(s2)
        self.assertFalse(report.has_conflicts)


if __name__ == "__main__":
    unittest.main(verbosity=2)
