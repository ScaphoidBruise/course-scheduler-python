import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCHEDULER = ROOT / "scheduler"
if str(SCHEDULER) not in sys.path:
    sys.path.insert(0, str(SCHEDULER))

import db  # noqa: E402


class PrerequisiteParserTests(unittest.TestCase):
    def check_text(self, text, completed):
        with patch("db._lookup_prereq_text", return_value=text):
            return db.check_prerequisites("COSC 3320", set(completed))

    def test_and_requires_all_courses(self):
        result = self.check_text("COSC 1336 and MATH 2413", {"COSC 1336"})
        self.assertFalse(result["met"])
        self.assertEqual(result["missing"], ["MATH 2413"])

    def test_or_accepts_either_course(self):
        result = self.check_text("COSC 1336 or COSC 1436", {"COSC 1436"})
        self.assertTrue(result["met"])
        self.assertEqual(result["missing"], [])

    def test_parentheses_are_ignored_around_groups(self):
        result = self.check_text("(COSC 1336 or COSC 1436) and MATH 2413", {"COSC 1336"})
        self.assertFalse(result["met"])
        self.assertEqual(result["missing"], ["MATH 2413"])

    def test_free_text_consent_is_marked_unparseable_but_met(self):
        result = self.check_text("consent of instructor", set())
        self.assertTrue(result["met"])
        self.assertTrue(result["could_not_parse"])
        self.assertEqual(result["missing"], [])

    def test_realistic_mixed_string(self):
        text = "Prerequisite: COSC 1336 or COSC 1436 and MATH 2413 or MATH 2414; consent recommended."
        result = self.check_text(text, {"COSC 1336", "MATH 2414"})
        self.assertTrue(result["met"])
        self.assertFalse(result["could_not_parse"])


if __name__ == "__main__":
    unittest.main()
