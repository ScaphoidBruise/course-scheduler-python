"""
Integration tests for untested API endpoints and page routes in scheduler/app.py.

Tests cover: page routes, catalog/courses, sections, subjects, modes,
session-dates, wishlist, profile, AI planner advice (fallback), and
the planner-target GET endpoint.
"""

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


def seed_db(db_path):
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
    conn.executemany(
        """
        INSERT INTO courses (
            subject_code, course_number, course_code, course_name,
            course_url, prerequisites, term_infered
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("COSC", "3320", "COSC 3320", "Python Programming", "https://example.test", "", "Fall"),
            ("COSC", "1336", "COSC 1336", "Programming Fundamentals I", "", "MATH 1000", "Fall"),
            ("MATH", "2413", "MATH 2413", "Calculus I", "", "", "Fall"),
        ],
    )
    conn.executemany(
        """
        INSERT INTO sections (
            term_label, schedule_url, class_nbr, subject_code, course_number,
            course_code, section_code, credits, days, session,
            start_time, end_time, location, mode
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "Fall 2026", "https://example.test", "1001",
                "COSC", "3320", "COSC 3320", "001", "3.00",
                "MW", "1", "9:00 AM", "10:15 AM", "MESA 100", "Face-to-Face",
            ),
            (
                "Fall 2026", "https://example.test", "1002",
                "MATH", "2413", "MATH 2413", "001", "3.00",
                "TR", "1", "11:00 AM", "12:15 PM", "ST 100", "Face-to-Face",
            ),
            (
                "Fall 2026", "https://example.test", "1003",
                "COSC", "1336", "COSC 1336", "001", "3.00",
                "", "1", "", "", "ONLINE", "100-Percent Online",
            ),
        ],
    )
    conn.executemany(
        """
        INSERT INTO session_calendar (
            term_label, session, session_start_date, session_end_date, source_url
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("Fall 2026", "1", "2026-08-24", "2026-12-11", "https://example.test"),
        ],
    )
    conn.commit()
    conn.close()


class ApiRoutesTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.db"
        seed_db(self.db_path)

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

    def _register_and_login(self, username="test_user"):
        resp = self.client.post(
            "/api/register",
            json={
                "username": username,
                "password": "password123",
                "confirm_password": "password123",
            },
        )
        self.assertEqual(resp.status_code, 201)
        return resp.get_json()["user"]

    # ------------------------------------------------------------------
    # Page routes
    # ------------------------------------------------------------------

    def test_schedule_page(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"html", r.data.lower())

    def test_catalog_page(self):
        r = self.client.get("/catalog")
        self.assertEqual(r.status_code, 200)

    def test_about_page(self):
        r = self.client.get("/about")
        self.assertEqual(r.status_code, 200)

    def test_help_page(self):
        r = self.client.get("/help")
        self.assertEqual(r.status_code, 200)

    def test_account_page(self):
        r = self.client.get("/account")
        self.assertEqual(r.status_code, 200)

    def test_profile_page(self):
        r = self.client.get("/profile")
        self.assertEqual(r.status_code, 200)

    def test_planner_page(self):
        r = self.client.get("/planner")
        self.assertEqual(r.status_code, 200)

    def test_progress_page(self):
        r = self.client.get("/progress")
        self.assertEqual(r.status_code, 200)

    # ------------------------------------------------------------------
    # Data API endpoints (no auth required)
    # ------------------------------------------------------------------

    def test_api_terms_returns_list(self):
        r = self.client.get("/api/terms")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIsInstance(data, list)
        self.assertIn("Fall 2026", data)

    def test_api_sections_empty_without_term(self):
        r = self.client.get("/api/sections")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), [])

    def test_api_sections_returns_data_for_term(self):
        r = self.client.get("/api/sections?term=Fall%202026")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertGreater(len(data), 0)
        codes = {s["course_code"] for s in data}
        self.assertIn("COSC 3320", codes)

    def test_api_sections_filter_by_subject(self):
        r = self.client.get("/api/sections?term=Fall%202026&subject=COSC")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        for s in data:
            self.assertEqual(s["subject_code"], "COSC")

    def test_api_sections_filter_by_mode(self):
        r = self.client.get("/api/sections?term=Fall%202026&mode=Face-to-Face")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        for s in data:
            self.assertIn("Face", s["mode"])

    def test_api_sections_batch_empty(self):
        r = self.client.get("/api/sections/batch")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), [])

    def test_api_sections_batch_returns_sections(self):
        r = self.client.get("/api/sections/batch?ids=1,2")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertGreater(len(data), 0)

    def test_api_courses_returns_catalog(self):
        r = self.client.get("/api/courses")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        codes = {c["course_code"] for c in data}
        self.assertIn("COSC 3320", codes)

    def test_api_courses_filter_subject(self):
        r = self.client.get("/api/courses?subject=COSC")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        for c in data:
            self.assertEqual(c["subject_code"], "COSC")

    def test_api_courses_filter_search(self):
        r = self.client.get("/api/courses?search=Python")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(any("Python" in c.get("course_name", "") for c in data))

    def test_api_courses_detail_found(self):
        r = self.client.get("/api/courses/1")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("course_code", data)

    def test_api_courses_detail_not_found(self):
        r = self.client.get("/api/courses/99999")
        self.assertEqual(r.status_code, 404)

    def test_api_course_subjects_returns_list(self):
        r = self.client.get("/api/course-subjects")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIsInstance(data, list)

    def test_api_subjects_returns_list(self):
        r = self.client.get("/api/subjects?term=Fall%202026")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIsInstance(data, list)

    def test_api_modes_returns_list(self):
        r = self.client.get("/api/modes?term=Fall%202026")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIsInstance(data, list)

    def test_api_session_dates_empty_without_term(self):
        r = self.client.get("/api/session-dates")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), [])

    def test_api_session_dates_with_term(self):
        r = self.client.get("/api/session-dates?term=Fall%202026")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIsInstance(data, list)

    def test_api_academic_programs_returns_list(self):
        r = self.client.get("/api/academic-programs")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIsInstance(data, list)

    def test_api_me_unauthenticated(self):
        r = self.client.get("/api/me")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["authenticated"])

    def test_api_me_authenticated(self):
        self._register_and_login("me_user")
        r = self.client.get("/api/me")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data["authenticated"])
        self.assertEqual(data["user"]["username"], "me_user")

    # ------------------------------------------------------------------
    # Auth-gated endpoints
    # ------------------------------------------------------------------

    def test_api_prereq_check_unauthenticated(self):
        # /api/prereq-check requires auth
        r = self.client.get("/api/prereq-check?codes=COSC3320")
        self.assertEqual(r.status_code, 401)

    def test_api_prereq_check_authenticated(self):
        self._register_and_login("conflict_user")
        r = self.client.get("/api/prereq-check?codes=COSC3320")
        self.assertEqual(r.status_code, 200)

    def test_api_profile_requires_auth(self):
        r = self.client.get("/api/profile")
        self.assertEqual(r.status_code, 401)

    def test_api_profile_get(self):
        self._register_and_login("profile_user")
        r = self.client.get("/api/profile")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("profile", data)
        self.assertFalse(data["profile"]["has_transcript"])

    def test_api_profile_info_post(self):
        self._register_and_login("prof_info_user")
        r = self.client.post(
            "/api/profile/info",
            json={"major": "Computer Science", "minor": "Mathematics"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

        profile = self.client.get("/api/profile").get_json()
        self.assertEqual(profile["profile"]["major"], "Computer Science")

    def test_api_wishlist_empty(self):
        self._register_and_login("wishlist_user")
        r = self.client.get("/api/wishlist")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json(), [])

    def test_api_wishlist_add_and_get(self):
        self._register_and_login("wl_add_user")
        add = self.client.post("/api/wishlist", json={"course_id": 1})
        self.assertEqual(add.status_code, 200)
        self.assertTrue(add.get_json()["ok"])

        wl = self.client.get("/api/wishlist").get_json()
        self.assertEqual(len(wl), 1)
        self.assertEqual(wl[0]["course_id"], 1)

    def test_api_wishlist_add_invalid_course(self):
        self._register_and_login("wl_bad_user")
        r = self.client.post("/api/wishlist", json={"course_id": 99999})
        self.assertEqual(r.status_code, 404)

    def test_api_wishlist_add_missing_course_id(self):
        self._register_and_login("wl_missing_user")
        r = self.client.post("/api/wishlist", json={})
        self.assertEqual(r.status_code, 400)

    def test_api_wishlist_delete(self):
        self._register_and_login("wl_del_user")
        self.client.post("/api/wishlist", json={"course_id": 1})
        r = self.client.delete("/api/wishlist/1")
        self.assertEqual(r.status_code, 200)
        wl = self.client.get("/api/wishlist").get_json()
        self.assertEqual(len(wl), 0)

    def test_api_program_requirements_me_no_major(self):
        self._register_and_login("pr_user")
        r = self.client.get("/api/program-requirements/me")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIsNone(data["program"])

    def test_api_planner_target_get(self):
        self._register_and_login("target_user")
        r = self.client.get("/api/planner-target")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("credits_target", data)

    def test_api_planner_target_invalid_value(self):
        self._register_and_login("target_invalid_user")
        r = self.client.post("/api/planner-target", json={"credits_target": "abc"})
        self.assertEqual(r.status_code, 400)

    def test_api_planner_target_out_of_range(self):
        self._register_and_login("target_range_user")
        r = self.client.post("/api/planner-target", json={"credits_target": 500})
        self.assertEqual(r.status_code, 400)

    def test_api_term_timeline(self):
        self._register_and_login("timeline_user")
        r = self.client.get("/api/term-timeline")
        self.assertEqual(r.status_code, 200)

    def test_api_transcript_term(self):
        self._register_and_login("transcript_term_user")
        r = self.client.get("/api/transcript-term?term=Fall%202026")
        self.assertEqual(r.status_code, 200)

    def test_api_ai_advice_fallback(self):
        self._register_and_login("ai_user")
        r = self.client.post(
            "/api/ai/planner-advice",
            json={"messages": [{"role": "user", "content": "What should I take next?"}]},
        )
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("reply", data)
        self.assertIn("source", data)

    def test_api_sections_search(self):
        r = self.client.get("/api/sections?term=Fall%202026&search=Python")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIsInstance(data, list)

    def test_api_wishlist_requires_auth(self):
        r = self.client.get("/api/wishlist")
        self.assertEqual(r.status_code, 401)

    def test_api_term_timeline_requires_auth(self):
        r = self.client.get("/api/term-timeline")
        self.assertEqual(r.status_code, 401)

    def test_api_ai_advice_with_profile_and_schedule(self):
        import json
        user = self._register_and_login("ai_detailed_user")
        self.app_module.update_user_profile(
            user["id"],
            major="Computer Science",
            transcript_parsed_json=json.dumps({
                "credits_earned": 45.0,
                "cumulative_gpa": 3.2,
                "last_term_gpa": 3.4,
                "transfer_earned_total": 15.0,
                "transfer_attempted_total": 15.0,
            }),
        )
        self.client.post("/api/planner-target", json={"credits_target": 120})
        r = self.client.post(
            "/api/ai/planner-advice",
            json={"messages": [{"role": "user", "content": "How many credits do I have left?"}]},
        )
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("reply", data)

    def test_api_register_login_logout_flow(self):
        reg = self.client.post(
            "/api/register",
            json={"username": "flow_user", "password": "pass1234", "confirm_password": "pass1234"},
        )
        self.assertEqual(reg.status_code, 201)

        login = self.client.post("/api/login", json={"username": "flow_user", "password": "pass1234"})
        self.assertEqual(login.status_code, 200)

        me = self.client.get("/api/me").get_json()
        self.assertTrue(me["authenticated"])

        logout = self.client.post("/api/logout", json={})
        self.assertEqual(logout.status_code, 200)

        me2 = self.client.get("/api/me").get_json()
        self.assertFalse(me2["authenticated"])

    def test_api_register_duplicate_user(self):
        self.client.post(
            "/api/register",
            json={"username": "dup_user", "password": "pass1234", "confirm_password": "pass1234"},
        )
        r = self.client.post(
            "/api/register",
            json={"username": "dup_user", "password": "pass1234", "confirm_password": "pass1234"},
        )
        self.assertEqual(r.status_code, 409)

    def test_api_register_password_mismatch(self):
        r = self.client.post(
            "/api/register",
            json={"username": "new_user", "password": "pass1234", "confirm_password": "different"},
        )
        self.assertEqual(r.status_code, 400)

    def test_api_login_bad_credentials(self):
        r = self.client.post("/api/login", json={"username": "noone", "password": "wrong"})
        self.assertEqual(r.status_code, 401)

    # ------------------------------------------------------------------
    # Direct tests for _fallback_planner_advice (covers lines 602-642)
    # ------------------------------------------------------------------

    def test_fallback_advice_no_transcript_no_major(self):
        """Covers the no-transcript and no-major branches, tips < 2 fallback."""
        fn = self.app_module._fallback_planner_advice
        context = {
            "student_profile": {
                "has_transcript": False,
                "major": None,
                "transfer_credits_earned": None,
            },
            "planner": {"totals": {}, "planned_terms": []},
            "degree_progress": {"remaining_by_typical_term": {}},
        }
        result = fn(context)
        self.assertIsInstance(result, str)
        self.assertIn("transcript", result.lower())

    def test_fallback_advice_with_major_and_transfer(self):
        """Covers major branch and transfer credits branch."""
        import os
        fn = self.app_module._fallback_planner_advice
        saved_key = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            context = {
                "student_profile": {
                    "has_transcript": True,
                    "major": "Computer Science",
                    "transfer_credits_earned": 12.0,
                },
                "planner": {
                    "totals": {
                        "credits_completed": 45,
                        "credits_target": 120,
                        "credits_planned": 15,
                        "expected_graduation_label": "Spring 2028",
                    },
                    "planned_terms": [],
                },
                "degree_progress": {"remaining_by_typical_term": {}},
            }
            result = fn(context, prompt="What should I do next?")
            self.assertIn("Computer Science", result)
            self.assertIn("transfer", result.lower())
        finally:
            if saved_key:
                os.environ["ANTHROPIC_API_KEY"] = saved_key

    def test_fallback_advice_conflict_and_heavy_terms(self):
        """Covers conflict_terms branch and heavy_terms branch."""
        fn = self.app_module._fallback_planner_advice
        context = {
            "student_profile": {
                "has_transcript": True,
                "major": "Math",
                "transfer_credits_earned": 0,
            },
            "planner": {
                "totals": {
                    "credits_completed": 30,
                    "credits_target": 120,
                    "credits_planned": 33,
                    "expected_graduation_label": "Fall 2028",
                },
                "planned_terms": [
                    {"label": "Fall 2026", "has_conflicts": True, "credits": 15},
                    {"label": "Spring 2027", "has_conflicts": False, "credits": 18},
                ],
            },
            "degree_progress": {"remaining_by_typical_term": {}},
        }
        result = fn(context)
        self.assertIn("conflict", result.lower())
        self.assertIn("Spring 2027", result)

    def test_fallback_advice_remaining_courses(self):
        """Covers the remaining courses (degree_progress) branch."""
        fn = self.app_module._fallback_planner_advice
        context = {
            "student_profile": {
                "has_transcript": True,
                "major": "Biology",
                "transfer_credits_earned": 0,
            },
            "planner": {
                "totals": {
                    "credits_completed": 60,
                    "credits_target": 120,
                    "credits_planned": 18,
                    "expected_graduation_label": "Fall 2027",
                },
                "planned_terms": [],
            },
            "degree_progress": {
                "remaining_by_typical_term": {
                    "Fall": [{"course": "BIOL 4010", "course_name": "Cell Biology"}],
                }
            },
        }
        result = fn(context)
        self.assertIn("Fall", result)

    def test_normalized_chat_messages_filters_invalid(self):
        """Covers _normalized_chat_messages with non-dict items (line 649)."""
        fn = self.app_module._normalized_chat_messages
        messages = [
            "not a dict",
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"no_role": "bad"},
        ]
        result = fn(messages)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["role"], "user")


if __name__ == "__main__":
    unittest.main(verbosity=2)
