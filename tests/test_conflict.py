"""
Comprehensive tests for scheduler/conflict.py.

Covers is_half_semester, parse_days, parse_time, sections_conflict, and
find_conflicts, including edge cases for online sections, half-semester
sessions, boundary times, and missing/None data.
"""

import sys
import unittest
from pathlib import Path

SCHEDULER = Path(__file__).resolve().parents[1] / "scheduler"
if str(SCHEDULER) not in sys.path:
    sys.path.insert(0, str(SCHEDULER))

from conflict import (  # noqa: E402
    find_conflicts,
    is_half_semester,
    parse_days,
    parse_time,
    sections_conflict,
)


class IsHalfSemesterTests(unittest.TestCase):
    def test_8w1_upper(self):
        self.assertTrue(is_half_semester("8W1"))

    def test_8w2_upper(self):
        self.assertTrue(is_half_semester("8W2"))

    def test_8w1_lower(self):
        self.assertTrue(is_half_semester("8w1"))

    def test_8w2_mixed(self):
        self.assertTrue(is_half_semester("8W2"))

    def test_full_semester_1(self):
        self.assertFalse(is_half_semester("1"))

    def test_full_semester_2(self):
        self.assertFalse(is_half_semester("2"))

    def test_empty_string(self):
        self.assertFalse(is_half_semester(""))

    def test_whitespace_only(self):
        self.assertFalse(is_half_semester("   "))

    def test_none(self):
        self.assertFalse(is_half_semester(None))

    def test_summer_session(self):
        self.assertFalse(is_half_semester("SUM"))


class ParseDaysTests(unittest.TestCase):
    def test_mw(self):
        self.assertEqual(parse_days("MW"), {"M", "W"})

    def test_tr(self):
        self.assertEqual(parse_days("TR"), {"T", "R"})

    def test_mwf(self):
        self.assertEqual(parse_days("MWF"), {"M", "W", "F"})

    def test_mtwrf(self):
        self.assertEqual(parse_days("MTWRF"), {"M", "T", "W", "R", "F"})

    def test_lowercase(self):
        self.assertEqual(parse_days("mwf"), {"M", "W", "F"})

    def test_mixed_case(self):
        self.assertEqual(parse_days("Mw"), {"M", "W"})

    def test_empty_string(self):
        self.assertEqual(parse_days(""), set())

    def test_whitespace_only(self):
        self.assertEqual(parse_days("  "), set())

    def test_none(self):
        self.assertEqual(parse_days(None), set())

    def test_single_day(self):
        self.assertEqual(parse_days("M"), {"M"})

    def test_duplicate_days_deduplicated(self):
        result = parse_days("MMW")
        self.assertEqual(result, {"M", "W"})

    def test_non_day_chars_ignored(self):
        result = parse_days("MX1W")
        self.assertEqual(result, {"M", "W"})


class ParseTimeTests(unittest.TestCase):
    def test_9am(self):
        self.assertEqual(parse_time("9:00 AM"), 540)

    def test_10_15am(self):
        self.assertEqual(parse_time("10:15 AM"), 615)

    def test_1_30pm(self):
        self.assertEqual(parse_time("1:30 PM"), 810)

    def test_noon(self):
        self.assertEqual(parse_time("12:00 PM"), 720)

    def test_midnight(self):
        self.assertEqual(parse_time("12:00 AM"), 0)

    def test_11_59pm(self):
        # 11:59 PM = 23:59 = 23*60+59 = 1439 minutes since midnight
        self.assertEqual(parse_time("11:59 PM"), 1439)

    def test_none(self):
        self.assertIsNone(parse_time(None))

    def test_empty_string(self):
        self.assertIsNone(parse_time(""))

    def test_whitespace_only(self):
        self.assertIsNone(parse_time("   "))

    def test_invalid_no_colon(self):
        self.assertIsNone(parse_time("9AM"))

    def test_invalid_multiple_colons(self):
        self.assertIsNone(parse_time("9:00:00 AM"))

    def test_invalid_alpha_parts(self):
        self.assertIsNone(parse_time("9:xx AM"))

    def test_3pm(self):
        self.assertEqual(parse_time("3:00 PM"), 900)

    def test_lowercase_am(self):
        result = parse_time("9:00 am")
        self.assertEqual(result, 540)


class SectionsConflictTests(unittest.TestCase):
    def _section(self, days, start, end, session="1"):
        return {
            "days": days,
            "start_time": start,
            "end_time": end,
            "session": session,
        }

    def test_overlapping_same_days(self):
        a = self._section("MW", "9:00 AM", "10:15 AM")
        b = self._section("MW", "9:30 AM", "10:45 AM")
        self.assertTrue(sections_conflict(a, b))

    def test_non_overlapping_same_days(self):
        a = self._section("MW", "9:00 AM", "10:15 AM")
        b = self._section("MW", "11:00 AM", "12:15 PM")
        self.assertFalse(sections_conflict(a, b))

    def test_adjacent_times_no_overlap(self):
        a = self._section("MW", "9:00 AM", "10:15 AM")
        b = self._section("MW", "10:15 AM", "11:30 AM")
        self.assertFalse(sections_conflict(a, b))

    def test_different_days_same_time(self):
        a = self._section("MW", "9:00 AM", "10:15 AM")
        b = self._section("TR", "9:00 AM", "10:15 AM")
        self.assertFalse(sections_conflict(a, b))

    def test_one_online_no_days(self):
        a = self._section("", "9:00 AM", "10:15 AM")
        b = self._section("MW", "9:00 AM", "10:15 AM")
        self.assertFalse(sections_conflict(a, b))

    def test_both_online_no_conflict(self):
        a = self._section("", "9:00 AM", "10:15 AM")
        b = self._section("", "9:00 AM", "10:15 AM")
        self.assertFalse(sections_conflict(a, b))

    def test_no_start_time_no_conflict(self):
        a = {"days": "MW", "start_time": None, "end_time": None, "session": "1"}
        b = {"days": "MW", "start_time": None, "end_time": None, "session": "1"}
        self.assertFalse(sections_conflict(a, b))

    def test_8w1_vs_8w2_same_time_no_conflict(self):
        a = self._section("MW", "9:00 AM", "10:15 AM", session="8W1")
        b = self._section("MW", "9:00 AM", "10:15 AM", session="8W2")
        self.assertFalse(sections_conflict(a, b))

    def test_8w1_vs_8w1_overlapping_conflict(self):
        a = self._section("MW", "9:00 AM", "10:15 AM", session="8W1")
        b = self._section("MW", "9:30 AM", "10:45 AM", session="8W1")
        self.assertTrue(sections_conflict(a, b))

    def test_8w2_vs_8w2_overlapping_conflict(self):
        a = self._section("MW", "9:00 AM", "10:15 AM", session="8W2")
        b = self._section("MW", "9:30 AM", "10:45 AM", session="8W2")
        self.assertTrue(sections_conflict(a, b))

    def test_full_vs_half_semester_conflict(self):
        a = self._section("MW", "9:00 AM", "10:15 AM", session="1")
        b = self._section("MW", "9:30 AM", "10:45 AM", session="8W1")
        self.assertTrue(sections_conflict(a, b))

    def test_partial_day_overlap_conflict(self):
        a = self._section("MWF", "9:00 AM", "10:15 AM")
        b = self._section("MF", "9:30 AM", "10:45 AM")
        self.assertTrue(sections_conflict(a, b))

    def test_symmetrical_a_vs_b_equals_b_vs_a(self):
        a = self._section("MW", "9:00 AM", "10:15 AM")
        b = self._section("MW", "9:30 AM", "10:45 AM")
        self.assertEqual(sections_conflict(a, b), sections_conflict(b, a))

    def test_one_minute_overlap(self):
        a = self._section("MW", "9:00 AM", "10:01 AM")
        b = self._section("MW", "10:00 AM", "11:15 AM")
        self.assertTrue(sections_conflict(a, b))


class FindConflictsTests(unittest.TestCase):
    def _section(self, days, start, end, session="1"):
        return {
            "days": days,
            "start_time": start,
            "end_time": end,
            "session": session,
        }

    def test_finds_one_conflict(self):
        new = self._section("MW", "9:30 AM", "10:45 AM")
        existing = [
            self._section("MW", "9:00 AM", "10:15 AM"),
            self._section("TR", "9:30 AM", "10:45 AM"),
        ]
        result = find_conflicts(new, existing)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["days"], "MW")

    def test_empty_schedule_no_conflicts(self):
        new = self._section("MW", "9:00 AM", "10:15 AM")
        self.assertEqual(find_conflicts(new, []), [])

    def test_finds_multiple_conflicts(self):
        new = self._section("MW", "9:00 AM", "11:00 AM")
        existing = [
            self._section("MW", "9:00 AM", "10:15 AM"),
            self._section("MW", "10:00 AM", "11:30 AM"),
        ]
        result = find_conflicts(new, existing)
        self.assertEqual(len(result), 2)

    def test_online_new_section_no_conflict(self):
        new = self._section("", "9:00 AM", "10:15 AM")
        existing = [self._section("MW", "9:00 AM", "10:15 AM")]
        self.assertEqual(find_conflicts(new, existing), [])

    def test_no_conflict_different_days(self):
        new = self._section("MW", "9:00 AM", "10:15 AM")
        existing = [self._section("TR", "9:00 AM", "10:15 AM")]
        self.assertEqual(find_conflicts(new, existing), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
