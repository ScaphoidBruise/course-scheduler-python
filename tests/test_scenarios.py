import importlib
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
    conn.execute(
        """
        INSERT INTO courses (
            subject_code, course_number, course_code, course_name, course_url, prerequisites, term_infered
        ) VALUES ('COSC', '3320', 'COSC 3320', 'Python Programming', '', '', 'Spring')
        """
    )
    conn.execute(
        """
        INSERT INTO courses (
            subject_code, course_number, course_code, course_name, course_url, prerequisites, term_infered
        ) VALUES ('MATH', '2413', 'MATH 2413', 'Calculus I', '', '', 'Spring')
        """
    )
    conn.execute(
        """
        INSERT INTO sections (
            term_label, schedule_url, class_nbr, subject_code, course_number, course_code,
            section_code, credits, days, session, start_time, end_time, location, mode
        ) VALUES (
            'Spring 2026', 'https://example.test', '1001', 'COSC', '3320', 'COSC 3320',
            '001', '3.00', 'MW', '1', '9:00 AM', '10:15 AM', 'MESA 100', 'Face-to-Face'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO sections (
            term_label, schedule_url, class_nbr, subject_code, course_number, course_code,
            section_code, credits, days, session, start_time, end_time, location, mode
        ) VALUES (
            'Spring 2026', 'https://example.test', '1002', 'MATH', '2413', 'MATH 2413',
            '002', '4.00', '', '8W1', '', '', 'ONLINE', '100-Percent Online'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO session_calendar (
            term_label, session, session_start_date, session_end_date, source_url
        ) VALUES ('Spring 2026', '1', '2026-01-12', '2026-05-08', 'https://example.test')
        """
    )
    conn.execute(
        """
        INSERT INTO session_calendar (
            term_label, session, session_start_date, session_end_date, source_url
        ) VALUES ('Spring 2026', '8W1', '2026-01-12', '2026-03-06', 'https://example.test')
        """
    )
    conn.commit()
    conn.close()


class ScenarioApiTest(unittest.TestCase):
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

    def test_legacy_schedule_rows_migrate_to_active_scenario(self):
        import db

        with tempfile.TemporaryDirectory() as tmp:
            legacy_path = Path(tmp) / "legacy.db"
            conn = sqlite3.connect(legacy_path)
            conn.executescript(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE user_schedules (
                    user_id INTEGER NOT NULL,
                    term_label TEXT NOT NULL,
                    section_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, term_label, section_id),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                INSERT INTO users (id, username, password_hash) VALUES (1, 'legacy', 'x');
                INSERT INTO user_schedules (user_id, term_label, section_id) VALUES (1, 'Spring 2026', 42);
                """
            )
            conn.commit()
            conn.close()

            db.DB_PATH = legacy_path
            db.init_auth_tables()

            conn = sqlite3.connect(legacy_path)
            conn.row_factory = sqlite3.Row
            scenario = conn.execute(
                "SELECT * FROM schedule_scenarios WHERE user_id = 1 AND term_label = 'Spring 2026'"
            ).fetchone()
            saved = conn.execute("SELECT * FROM user_schedules").fetchone()
            conn.close()

            self.assertIsNotNone(scenario)
            self.assertEqual(scenario["name"], "My schedule")
            self.assertEqual(scenario["is_active"], 1)
            self.assertEqual(saved["scenario_id"], scenario["id"])

    def test_scenario_lifecycle_and_export(self):
        register = self.client.post(
            "/api/register",
            json={
                "username": "scenario_user",
                "password": "password123",
                "confirm_password": "password123",
            },
        )
        self.assertEqual(register.status_code, 201)

        created = self.client.post(
            "/api/scenarios",
            json={"term": "Spring 2026", "name": "Plan A"},
        )
        self.assertEqual(created.status_code, 201)
        scenario_id = created.get_json()["scenario"]["id"]

        saved = self.client.post(
            "/api/my-schedule",
            json={"term": "Spring 2026", "scenario_id": scenario_id, "ids": [1, 2]},
        )
        self.assertEqual(saved.status_code, 200)

        duplicated = self.client.post(f"/api/scenarios/{scenario_id}/duplicate")
        self.assertEqual(duplicated.status_code, 201)
        duplicate_id = duplicated.get_json()["scenario"]["id"]

        renamed = self.client.post(
            f"/api/scenarios/{duplicate_id}/rename",
            json={"name": "Plan B"},
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.get_json()["scenario"]["name"], "Plan B")

        activated = self.client.post(f"/api/scenarios/{scenario_id}/activate")
        self.assertEqual(activated.status_code, 200)
        self.assertEqual(activated.get_json()["scenario"]["id"], scenario_id)

        ics = self.client.get(f"/api/scenarios/{scenario_id}/ics")
        self.assertEqual(ics.status_code, 200)
        self.assertEqual(ics.mimetype, "text/calendar")
        text = ics.get_data(as_text=True)
        self.assertIn("BEGIN:VCALENDAR", text)
        self.assertIn("RRULE:FREQ=WEEKLY", text)
        self.assertIn("COSC 3320", text)
        self.assertNotIn("MATH 2413", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
