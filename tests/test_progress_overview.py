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
        ("COSC", "1336", "COSC 1336", "Programming Fundamentals I", "", "", "Fall"),
        ("COSC", "1337", "COSC 1337", "Programming Fundamentals II", "", "", "Spring"),
        ("COSC", "3320", "COSC 3320", "Python Programming", "", "", "Spring"),
    ]
    conn.executemany(
        """
        INSERT INTO courses (
            subject_code, course_number, course_code, course_name, course_url, prerequisites, term_infered
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        courses,
    )
    conn.commit()
    conn.close()


class ProgressOverviewTest(unittest.TestCase):
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

    def _register(self, username="prog_user"):
        return self.client.post(
            "/api/register",
            json={
                "username": username,
                "password": "password123",
                "confirm_password": "password123",
            },
        )

    def test_overview_no_transcript(self):
        register = self._register()
        self.assertEqual(register.status_code, 201)

        result = self.client.get("/api/degree-progress/overview")
        self.assertEqual(result.status_code, 200)
        body = result.get_json()
        self.assertFalse(body["has_transcript"])
        self.assertGreaterEqual(body["courses_remaining_count"], 0)
        self.assertEqual(body["percent_complete"], 0)
        self.assertEqual(body["credits_target"], 120)

    def test_overview_after_transcript_and_target_change(self):
        register = self._register()
        self.assertEqual(register.status_code, 201)
        user_id = register.get_json()["user"]["id"]

        transcript = {
            "credits_earned": 9.0,
            "cumulative_gpa": 3.5,
            "last_term_gpa": 3.6,
            "course_history": [
                {
                    "term": "Fall 2025",
                    "subject": "COSC",
                    "course_number": "1336",
                    "course": "COSC 1336",
                    "course_name": "Programming Fundamentals I",
                    "attempted": 3.0,
                    "earned": 3.0,
                    "grade": "A",
                },
                {
                    "term": "Fall 2025",
                    "subject": "COSC",
                    "course_number": "1337",
                    "course": "COSC 1337",
                    "course_name": "Programming Fundamentals II",
                    "attempted": 3.0,
                    "earned": 3.0,
                    "grade": "B",
                },
            ],
        }
        self.app_module.update_user_profile(
            user_id,
            major="Bachelor of Science in Computer Science",
            transcript_parsed_json=json.dumps(transcript),
        )
        target = self.client.post("/api/planner-target", json={"credits_target": 120})
        self.assertEqual(target.status_code, 200)

        result = self.client.get("/api/degree-progress/overview")
        self.assertEqual(result.status_code, 200)
        body = result.get_json()
        self.assertTrue(body["has_transcript"])
        self.assertGreater(float(body["credits_completed"]), 0)
        self.assertGreater(body["percent_complete"], 0)
        self.assertEqual(body["credits_target"], 120)
        self.assertIn("COSC", body["scope_subjects"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
