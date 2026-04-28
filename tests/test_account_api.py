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
    conn.commit()
    conn.close()


def _register(client, username, password="password123"):
    return client.post(
        "/api/register",
        json={
            "username": username,
            "password": password,
            "confirm_password": password,
        },
    )


class AccountApiTest(unittest.TestCase):
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

    def test_account_summary_shape(self):
        register = _register(self.client, "alice")
        self.assertEqual(register.status_code, 201)

        summary = self.client.get("/api/account/summary")
        self.assertEqual(summary.status_code, 200)
        data = summary.get_json()
        self.assertEqual(data["username"], "alice")
        self.assertIn("created_at", data)
        self.assertEqual(data["transcript_on_file"], False)
        self.assertEqual(data["saved_schedules_count"], 0)
        self.assertEqual(data["total_sections_in_schedules"], 0)

    def test_change_password_wrong_current(self):
        _register(self.client, "alice")
        result = self.client.post(
            "/api/account/change-password",
            json={
                "current_password": "WRONG",
                "new_password": "newsecret123",
                "confirm_password": "newsecret123",
            },
        )
        self.assertEqual(result.status_code, 401)

    def test_change_password_mismatch(self):
        _register(self.client, "alice")
        result = self.client.post(
            "/api/account/change-password",
            json={
                "current_password": "password123",
                "new_password": "newsecret123",
                "confirm_password": "differentSecret",
            },
        )
        self.assertEqual(result.status_code, 400)

    def test_change_password_success(self):
        _register(self.client, "alice")
        result = self.client.post(
            "/api/account/change-password",
            json={
                "current_password": "password123",
                "new_password": "newsecret123",
                "confirm_password": "newsecret123",
            },
        )
        self.assertEqual(result.status_code, 200)

        self.client.post("/api/logout", json={})
        bad = self.client.post("/api/login", json={"username": "alice", "password": "password123"})
        self.assertEqual(bad.status_code, 401)
        good = self.client.post("/api/login", json={"username": "alice", "password": "newsecret123"})
        self.assertEqual(good.status_code, 200)

    def test_change_username_collision(self):
        _register(self.client, "alice")
        self.client.post("/api/logout", json={})

        _register(self.client, "bob")
        result = self.client.post(
            "/api/account/change-username",
            json={"new_username": "alice", "current_password": "password123"},
        )
        self.assertEqual(result.status_code, 409)

    def test_change_username_success(self):
        _register(self.client, "alice")
        result = self.client.post(
            "/api/account/change-username",
            json={"new_username": "alicia", "current_password": "password123"},
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.get_json()["user"]["username"], "alicia")

        me = self.client.get("/api/me").get_json()
        self.assertEqual(me["user"]["username"], "alicia")

    def test_delete_wrong_confirm(self):
        _register(self.client, "alice")
        result = self.client.post(
            "/api/account/delete",
            json={"confirm": "delete", "current_password": "password123"},
        )
        self.assertEqual(result.status_code, 400)

    def test_delete_success_clears_session(self):
        _register(self.client, "alice")
        result = self.client.post(
            "/api/account/delete",
            json={"confirm": "DELETE", "current_password": "password123"},
        )
        self.assertEqual(result.status_code, 200)

        me = self.client.get("/api/me").get_json()
        self.assertFalse(me["authenticated"])

    def test_export_returns_attachment_with_expected_keys(self):
        _register(self.client, "alice")
        result = self.client.get("/api/account/export")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.mimetype, "application/json")
        disposition = result.headers.get("Content-Disposition", "")
        self.assertIn("attachment", disposition)
        self.assertIn(".json", disposition)
        body = json.loads(result.get_data(as_text=True))
        for key in ("user", "profile", "scenarios", "wishlist", "completed_overrides", "user_settings"):
            self.assertIn(key, body)
        self.assertEqual(body["user"]["username"], "alice")


if __name__ == "__main__":
    unittest.main(verbosity=2)
