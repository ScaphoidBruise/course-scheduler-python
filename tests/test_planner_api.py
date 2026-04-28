import importlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEDULER_DIR = ROOT / "scheduler"
if str(SCHEDULER_DIR) not in sys.path:
    sys.path.insert(0, str(SCHEDULER_DIR))


def seed_catalog(db_path):
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_code TEXT NOT NULL,
            course_number TEXT NOT NULL,
            course_code TEXT NOT NULL,
            course_name TEXT,
            course_url TEXT,
            prerequisites TEXT,
            term_infered TEXT
        );
        CREATE TABLE sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            term_label TEXT NOT NULL,
            schedule_url TEXT NOT NULL,
            class_nbr TEXT,
            subject_code TEXT NOT NULL,
            course_number TEXT NOT NULL,
            course_code TEXT NOT NULL,
            section_code TEXT,
            credits TEXT,
            days TEXT,
            session TEXT,
            start_time TEXT,
            end_time TEXT,
            location TEXT,
            mode TEXT
        );
        CREATE TABLE session_calendar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            term_label TEXT NOT NULL,
            session TEXT NOT NULL,
            session_start_date TEXT,
            session_end_date TEXT,
            source_url TEXT NOT NULL
        );
        """
    )
    courses = [
        ("COSC", "3320", "COSC 3320", "Python Programming", "", "", "Fall"),
        ("MATH", "2413", "MATH 2413", "Calculus I", "", "", "Fall"),
        ("ENGL", "1301", "ENGL 1301", "Composition", "", "", "Spring"),
    ]
    conn.executemany(
        """
        INSERT INTO courses (
            subject_code, course_number, course_code, course_name, course_url, prerequisites, term_infered
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        courses,
    )
    sections = [
        (
            "Fall 2026", "https://example.test", "1001", "COSC", "3320", "COSC 3320",
            "001", "3.00", "MW", "1", "9:00 AM", "10:15 AM", "MESA 100", "Face-to-Face",
        ),
        (
            "Fall 2026", "https://example.test", "1002", "MATH", "2413", "MATH 2413",
            "002", "3.00", "MW", "1", "9:30 AM", "10:45 AM", "ST 100", "Face-to-Face",
        ),
        (
            "Spring 2027", "https://example.test", "1003", "ENGL", "1301", "ENGL 1301",
            "003", "4.00", "TR", "1", "11:00 AM", "12:15 PM", "MB 200", "Face-to-Face",
        ),
    ]
    conn.executemany(
        """
        INSERT INTO sections (
            term_label, schedule_url, class_nbr, subject_code, course_number, course_code,
            section_code, credits, days, session, start_time, end_time, location, mode
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        sections,
    )
    calendars = [
        ("Spring 2026", "1", "2026-01-12", "2026-05-08", "https://example.test"),
        ("Fall 2026", "1", "2026-08-24", "2026-12-11", "https://example.test"),
        ("Spring 2027", "1", "2027-01-11", "2027-05-07", "https://example.test"),
    ]
    conn.executemany(
        """
        INSERT INTO session_calendar (
            term_label, session, session_start_date, session_end_date, source_url
        ) VALUES (?, ?, ?, ?, ?)
        """,
        calendars,
    )
    conn.commit()
    conn.close()


class PlannerApiTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.db"
        seed_catalog(self.db_path)

        import db

        db.DB_PATH = self.db_path
        if "app" in sys.modules:
            self.app_module = importlib.reload(sys.modules["app"])
        else:
            self.app_module = importlib.import_module("app")
        self.app_module.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.client = self.app_module.app.test_client()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_planner_overview_credits_and_conflicts(self):
        register = self.client.post(
            "/api/register",
            json={
                "username": "planner_user",
                "password": "password123",
                "confirm_password": "password123",
            },
        )
        self.assertEqual(register.status_code, 201)
        user_id = register.get_json()["user"]["id"]

        self.app_module.update_user_profile(
            user_id,
            transcript_parsed_json=json.dumps(
                {
                    "credits_earned": 60.0,
                    "cumulative_gpa": 3.4,
                    "last_term_gpa": 3.6,
                }
            ),
        )

        fall_saved = self.client.post(
            "/api/my-schedule",
            json={"term": "Fall 2026", "ids": [1, 2]},
        )
        self.assertEqual(fall_saved.status_code, 200)
        spring_saved = self.client.post(
            "/api/my-schedule",
            json={"term": "Spring 2027", "ids": [3]},
        )
        self.assertEqual(spring_saved.status_code, 200)

        overview = self.client.get("/api/planner-overview")
        self.assertEqual(overview.status_code, 200)
        data = overview.get_json()
        terms = {term["label"]: term for term in data["terms"]}

        self.assertEqual(terms["Fall 2026"]["credits"], 6)
        self.assertTrue(terms["Fall 2026"]["has_conflicts"])
        self.assertEqual(terms["Fall 2026"]["section_count"], 2)
        self.assertIn("session_start_date", terms["Fall 2026"]["sections"][0])

        self.assertEqual(terms["Spring 2027"]["credits"], 4)
        self.assertFalse(terms["Spring 2027"]["has_conflicts"])
        self.assertEqual(data["totals"]["credits_completed"], 60)
        self.assertEqual(data["totals"]["credits_planned"], 10)

        target = self.client.post("/api/planner-target", json={"credits_target": 132})
        self.assertEqual(target.status_code, 200)
        self.assertEqual(target.get_json()["credits_target"], 132)


if __name__ == "__main__":
    unittest.main(verbosity=2)
