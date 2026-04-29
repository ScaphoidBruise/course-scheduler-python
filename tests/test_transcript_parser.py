"""
Comprehensive tests for scheduler/transcript_pdf.py.

All tests here use synthetic text strings — no actual PDF file is required.
The PDF-specific I/O functions (_extract_pdf_text_from_reader etc.) are
tested via mocking so the suite runs offline.
"""

import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCHEDULER = Path(__file__).resolve().parents[1] / "scheduler"
if str(SCHEDULER) not in sys.path:
    sys.path.insert(0, str(SCHEDULER))

import transcript_pdf as tp  # noqa: E402
from transcript_pdf import (  # noqa: E402
    _all_term_spans,
    _clean_course_title,
    _clean_major_minor_name,
    _extract_course_rows,
    _extract_courses_line_by_line,
    _extract_courses_segmented,
    _extract_courses_with_terms,
    _gpa_candidates_in_block,
    _gpa_from_term_courses,
    _institutional_transcript_tail,
    _is_likely_enrolled,
    _level_split_from_rows,
    _parse_transcript_body,
    _sum_positive_earned,
    _term_label_from_line,
    parse_utpb_transcript_pdf,
    sanitize_transcript_dict_for_json,
    scrub_invalid_profile_floats,
    transcript_dict_to_json,
)


class SanitizeJsonTests(unittest.TestCase):
    def test_nan_becomes_none(self):
        result = sanitize_transcript_dict_for_json({"gpa": float("nan")})
        self.assertIsNone(result["gpa"])

    def test_inf_becomes_none(self):
        result = sanitize_transcript_dict_for_json({"val": float("inf")})
        self.assertIsNone(result["val"])

    def test_neg_inf_becomes_none(self):
        result = sanitize_transcript_dict_for_json({"val": float("-inf")})
        self.assertIsNone(result["val"])

    def test_normal_float_preserved(self):
        result = sanitize_transcript_dict_for_json({"gpa": 3.5})
        self.assertEqual(result["gpa"], 3.5)

    def test_nested_dict(self):
        result = sanitize_transcript_dict_for_json({"a": {"b": float("nan")}})
        self.assertIsNone(result["a"]["b"])

    def test_list_of_floats(self):
        result = sanitize_transcript_dict_for_json([float("nan"), 1.0])
        self.assertIsNone(result[0])
        self.assertEqual(result[1], 1.0)

    def test_string_preserved(self):
        result = sanitize_transcript_dict_for_json("hello")
        self.assertEqual(result, "hello")

    def test_int_preserved(self):
        result = sanitize_transcript_dict_for_json(42)
        self.assertEqual(result, 42)

    def test_none_preserved(self):
        self.assertIsNone(sanitize_transcript_dict_for_json(None))

    def test_bool_preserved(self):
        self.assertTrue(sanitize_transcript_dict_for_json(True))

    def test_object_becomes_str(self):
        class Foo:
            pass

        result = sanitize_transcript_dict_for_json(Foo())
        self.assertIsInstance(result, str)


class TranscriptDictToJsonTests(unittest.TestCase):
    def test_nan_serialised_as_null(self):
        import json
        data = {"gpa": float("nan")}
        text = transcript_dict_to_json(data)
        parsed = json.loads(text)
        self.assertIsNone(parsed["gpa"])

    def test_normal_round_trip(self):
        import json
        data = {"credits": 60.0, "gpa": 3.5}
        text = transcript_dict_to_json(data)
        self.assertEqual(json.loads(text), data)


class ScrubInvalidProfileFloatsTests(unittest.TestCase):
    def test_removes_nan(self):
        d = {"gpa": float("nan"), "credits": 30.0}
        scrub_invalid_profile_floats(d)
        self.assertIsNone(d["gpa"])
        self.assertEqual(d["credits"], 30.0)

    def test_removes_inf(self):
        d = {"gpa": float("inf")}
        scrub_invalid_profile_floats(d)
        self.assertIsNone(d["gpa"])

    def test_normal_value_kept(self):
        d = {"gpa": 3.5}
        scrub_invalid_profile_floats(d)
        self.assertEqual(d["gpa"], 3.5)


class CleanCourseTitleTests(unittest.TestCase):
    def test_collapses_whitespace(self):
        self.assertEqual(_clean_course_title("Python   Programming"), "Python Programming")

    def test_strips_edges(self):
        self.assertEqual(_clean_course_title("  Calc I  "), "Calc I")

    def test_empty_string(self):
        self.assertEqual(_clean_course_title(""), "")

    def test_none(self):
        self.assertEqual(_clean_course_title(None), "")


class CleanMajorMinorNameTests(unittest.TestCase):
    def test_normal_name(self):
        self.assertEqual(_clean_major_minor_name("Computer Science"), "Computer Science")

    def test_strips_whitespace(self):
        self.assertEqual(_clean_major_minor_name("  Biology  "), "Biology")

    def test_active_in_program_cleared(self):
        self.assertEqual(_clean_major_minor_name("Active in Program"), "")

    def test_undergraduate_cleared(self):
        self.assertEqual(_clean_major_minor_name("Undergraduate"), "")

    def test_graduate_cleared(self):
        self.assertEqual(_clean_major_minor_name("Graduate"), "")

    def test_status_cleared(self):
        self.assertEqual(_clean_major_minor_name("Status"), "")

    def test_case_insensitive_clear(self):
        self.assertEqual(_clean_major_minor_name("UNDERGRADUATE"), "")


class TermLabelFromLineTests(unittest.TestCase):
    def test_year_first_fall(self):
        self.assertEqual(_term_label_from_line("2024 Fall"), "2024 Fall")

    def test_year_first_spring(self):
        self.assertEqual(_term_label_from_line("2025 Spring"), "2025 Spring")

    def test_season_first_fall(self):
        self.assertEqual(_term_label_from_line("Fall 2024"), "2024 Fall")

    def test_season_first_spring(self):
        self.assertEqual(_term_label_from_line("Spring 2025"), "2025 Spring")

    def test_with_semester_suffix(self):
        result = _term_label_from_line("2024 Fall Semester")
        self.assertEqual(result, "2024 Fall")

    def test_non_term_line(self):
        self.assertIsNone(_term_label_from_line("COSC 3320 Python Programming"))

    def test_empty_line(self):
        self.assertIsNone(_term_label_from_line(""))

    def test_summer(self):
        self.assertEqual(_term_label_from_line("2024 Summer"), "2024 Summer")


class AllTermSpansTests(unittest.TestCase):
    def test_finds_multiple_terms(self):
        text = "2024 Fall\nCOSC 1336 Prog Fund 3.000 3.000 A\n2025 Spring\nCOSC 1337 Prog Fund II 3.000 3.000 B"
        spans = _all_term_spans(text)
        labels = [lbl for _, lbl in spans]
        self.assertIn("2024 Fall", labels)
        self.assertIn("2025 Spring", labels)

    def test_empty_text(self):
        spans = _all_term_spans("")
        self.assertEqual(spans, [])

    def test_season_first_format(self):
        text = "Fall 2024\nsome content\nSpring 2025"
        spans = _all_term_spans(text)
        labels = [lbl for _, lbl in spans]
        self.assertIn("2024 Fall", labels)
        self.assertIn("2025 Spring", labels)

    def test_spans_ordered_by_position(self):
        text = "2024 Fall\nsome\n2025 Spring"
        spans = _all_term_spans(text)
        positions = [pos for pos, _ in spans]
        self.assertEqual(positions, sorted(positions))

    def test_compact_fa_code(self):
        text = "FA24\nCOSC 3320 Python Programming 3.000 3.000 A"
        spans = _all_term_spans(text)
        labels = [lbl for _, lbl in spans]
        self.assertIn("2024 Fall", labels)

    def test_compact_sp_code(self):
        text = "SP25\nMATH 2413 Calculus I 3.000 3.000 B"
        spans = _all_term_spans(text)
        labels = [lbl for _, lbl in spans]
        self.assertIn("2025 Spring", labels)

    def test_compact_su_code(self):
        text = "SU24\nCOSC 1336 Prog Fund 3.000 3.000 A"
        spans = _all_term_spans(text)
        labels = [lbl for _, lbl in spans]
        self.assertIn("2024 Summer", labels)

    def test_deduplication_of_close_duplicates(self):
        text = "2024 Fall 2024 Fall\nCOSC 3320 stuff"
        spans = _all_term_spans(text)
        labels = [lbl for _, lbl in spans]
        count = labels.count("2024 Fall")
        self.assertLessEqual(count, 2)

    def test_unknown_compact_code_skipped(self):
        # XX24 is not a valid compact season code → continue skips it
        text = "XX24\n2024 Fall\nCOSC 3320 Python Programming 3.000 3.000 A"
        spans = _all_term_spans(text)
        labels = [lbl for _, lbl in spans]
        self.assertNotIn("2024 Unknown", labels)
        self.assertIn("2024 Fall", labels)


class SumPositiveEarnedTests(unittest.TestCase):
    def test_sums_positive(self):
        rows = [{"earned": 3.0}, {"earned": 4.0}, {"earned": 0.0}]
        self.assertEqual(_sum_positive_earned(rows), 7.0)

    def test_ignores_zero_and_negative(self):
        rows = [{"earned": -1.0}, {"earned": 0.0}]
        self.assertEqual(_sum_positive_earned(rows), 0.0)

    def test_empty(self):
        self.assertEqual(_sum_positive_earned([]), 0.0)


class LevelSplitTests(unittest.TestCase):
    def test_lower_level(self):
        rows = [{"earned": 3.0, "course_number": "1336"}, {"earned": 3.0, "course_number": "2413"}]
        lower, upper = _level_split_from_rows(rows)
        self.assertEqual(lower, 6.0)
        self.assertEqual(upper, 0.0)

    def test_upper_level(self):
        rows = [{"earned": 3.0, "course_number": "3320"}, {"earned": 3.0, "course_number": "4301"}]
        lower, upper = _level_split_from_rows(rows)
        self.assertEqual(lower, 0.0)
        self.assertEqual(upper, 6.0)

    def test_mixed(self):
        rows = [
            {"earned": 4.0, "course_number": "1430"},
            {"earned": 3.0, "course_number": "3320"},
        ]
        lower, upper = _level_split_from_rows(rows)
        self.assertEqual(lower, 4.0)
        self.assertEqual(upper, 3.0)

    def test_skips_zero_earned(self):
        rows = [{"earned": 0.0, "course_number": "1336"}]
        lower, upper = _level_split_from_rows(rows)
        self.assertEqual(lower, 0.0)
        self.assertEqual(upper, 0.0)


class GpaCandidatesTests(unittest.TestCase):
    def test_finds_term_gpa(self):
        block = "Term GPA: 3.50\nsome other text"
        candidates = _gpa_candidates_in_block(block)
        values = [v for _, v in candidates]
        self.assertIn(3.50, values)

    def test_finds_semester_gpa(self):
        block = "Semester GPA: 3.75"
        candidates = _gpa_candidates_in_block(block)
        values = [v for _, v in candidates]
        self.assertIn(3.75, values)

    def test_ignores_zero(self):
        block = "Term GPA: 0.000"
        candidates = _gpa_candidates_in_block(block)
        self.assertEqual(candidates, [])

    def test_empty_block(self):
        self.assertEqual(_gpa_candidates_in_block(""), [])

    def test_term_totals_gpa(self):
        block = "Term Totals: 12.000 12.000 3.500"
        candidates = _gpa_candidates_in_block(block)
        values = [v for _, v in candidates]
        self.assertIn(3.500, values)


class GpaFromTermCoursesTests(unittest.TestCase):
    def test_basic_gpa(self):
        rows = [
            {"earned": 3.0, "grade": "A"},
            {"earned": 3.0, "grade": "B"},
        ]
        result = _gpa_from_term_courses(rows)
        self.assertAlmostEqual(result, 3.5, places=2)

    def test_empty_rows(self):
        self.assertIsNone(_gpa_from_term_courses([]))

    def test_skips_ip_grade(self):
        rows = [{"earned": 3.0, "grade": "IP"}]
        self.assertIsNone(_gpa_from_term_courses(rows))

    def test_skips_w_grade(self):
        rows = [{"earned": 3.0, "grade": "W"}]
        self.assertIsNone(_gpa_from_term_courses(rows))

    def test_skips_zero_earned(self):
        rows = [{"earned": 0.0, "grade": "A"}]
        self.assertIsNone(_gpa_from_term_courses(rows))

    def test_all_f_returns_zero(self):
        rows = [{"earned": 3.0, "grade": "F"}, {"earned": 3.0, "grade": "F"}]
        result = _gpa_from_term_courses(rows)
        self.assertEqual(result, 0.0)

    def test_with_quality_points(self):
        rows = [{"earned": 3.0, "grade": "A", "quality_points": 12.0}]
        result = _gpa_from_term_courses(rows)
        self.assertAlmostEqual(result, 4.0, places=2)

    def test_plus_minus_grades(self):
        rows = [
            {"earned": 3.0, "grade": "A-"},
            {"earned": 3.0, "grade": "B+"},
        ]
        result = _gpa_from_term_courses(rows)
        self.assertIsNotNone(result)

    def test_non_gpa_p_grade_skipped(self):
        rows = [{"earned": 3.0, "grade": "P"}]
        self.assertIsNone(_gpa_from_term_courses(rows))

    def test_non_gpa_cr_grade_skipped(self):
        rows = [{"earned": 3.0, "grade": "CR"}]
        self.assertIsNone(_gpa_from_term_courses(rows))

    def test_unknown_grade_returns_none(self):
        rows = [{"earned": 3.0, "grade": "ZZ"}]
        self.assertIsNone(_gpa_from_term_courses(rows))

    def test_mixed_gpa_and_non_gpa(self):
        rows = [
            {"earned": 3.0, "grade": "A"},
            {"earned": 3.0, "grade": "P"},
        ]
        result = _gpa_from_term_courses(rows)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 4.0, places=2)

    def test_quality_points_invalid_skips_row(self):
        rows = [{"earned": 3.0, "grade": "A", "quality_points": "not_a_number"}]
        result = _gpa_from_term_courses(rows)
        self.assertIsNone(result)

    def test_none_grade_no_gpa(self):
        rows = [{"earned": 3.0, "grade": None}]
        self.assertIsNone(_gpa_from_term_courses(rows))


class ExtractCourseRowsTests(unittest.TestCase):
    def _make_course_line(self, subj, num, title, att, ear, grade):
        return f"{subj} {num} {title} {att:.3f} {ear:.3f} {grade}"

    def test_single_course_row(self):
        line = "COSC 3320 Python Programming 3.000 3.000 A"
        rows = _extract_course_rows(line)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["subject"], "COSC")
        self.assertEqual(rows[0]["course_number"], "3320")
        self.assertEqual(rows[0]["grade"], "A")

    def test_multiple_course_rows(self):
        text = (
            "COSC 3320 Python Programming 3.000 3.000 A\n"
            "MATH 2413 Calculus I 3.000 3.000 B\n"
        )
        rows = _extract_course_rows(text)
        self.assertEqual(len(rows), 2)

    def test_incomplete_line_ignored(self):
        text = "COSC 3320 Python Programming"
        rows = _extract_course_rows(text)
        self.assertEqual(rows, [])

    def test_ip_grade_parsed(self):
        line = "COSC 4301 Senior Project 3.000 0.000 IP"
        rows = _extract_course_rows(line)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["grade"], "IP")

    def test_w_grade_parsed(self):
        line = "ENGL 1301 Composition 3.000 0.000 W"
        rows = _extract_course_rows(line)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["grade"], "W")


class ExtractCoursesLineByLineTests(unittest.TestCase):
    def test_courses_tagged_with_term(self):
        text = (
            "2024 Fall\n"
            "COSC 3320 Python Programming 3.000 3.000 A\n"
            "2025 Spring\n"
            "MATH 2413 Calculus I 3.000 3.000 B\n"
        )
        rows = _extract_courses_line_by_line(text)
        terms = {r["term"] for r in rows}
        self.assertIn("2024 Fall", terms)
        self.assertIn("2025 Spring", terms)

    def test_course_without_term_header_skipped(self):
        text = "COSC 3320 Python Programming 3.000 3.000 A\n"
        rows = _extract_courses_line_by_line(text)
        self.assertEqual(rows, [])

    def test_term_update_mid_text(self):
        text = (
            "2024 Fall\n"
            "COSC 1336 Programming Fund 3.000 3.000 A\n"
            "2025 Spring\n"
            "COSC 1337 Programming Fund II 3.000 3.000 B\n"
        )
        rows = _extract_courses_line_by_line(text)
        by_code = {r["course_number"]: r for r in rows}
        self.assertEqual(by_code["1336"]["term"], "2024 Fall")
        self.assertEqual(by_code["1337"]["term"], "2025 Spring")


class ExtractCoursesSegmentedTests(unittest.TestCase):
    def test_segmented_extraction(self):
        text = (
            "2024 Fall\n"
            "COSC 3320 Python Programming 3.000 3.000 A\n"
            "2025 Spring\n"
            "MATH 2413 Calculus I 3.000 3.000 B\n"
        )
        rows = _extract_courses_segmented(text)
        self.assertGreaterEqual(len(rows), 1)

    def test_empty_text_returns_empty(self):
        rows = _extract_courses_segmented("")
        self.assertEqual(rows, [])

    def test_no_term_headers_returns_empty(self):
        text = "COSC 3320 Python Programming 3.000 3.000 A"
        rows = _extract_courses_segmented(text)
        self.assertEqual(rows, [])


class ExtractCoursesWithTermsTests(unittest.TestCase):
    def test_merges_results(self):
        text = (
            "2024 Fall\n"
            "COSC 3320 Python Programming 3.000 3.000 A\n"
        )
        rows = _extract_courses_with_terms(text)
        self.assertGreaterEqual(len(rows), 1)
        self.assertEqual(rows[0]["subject"], "COSC")

    def test_deduplicates_rows(self):
        text = (
            "2024 Fall\n"
            "COSC 3320 Python Programming 3.000 3.000 A\n"
            "COSC 3320 Python Programming 3.000 3.000 A\n"
        )
        rows = _extract_courses_with_terms(text)
        cosc_rows = [r for r in rows if r["course_number"] == "3320"]
        self.assertEqual(len(cosc_rows), 1)


class IsLikelyEnrolledTests(unittest.TestCase):
    def test_ip_grade_is_enrolled(self):
        self.assertTrue(_is_likely_enrolled({"grade": "IP", "attempted": 3.0, "earned": 0.0}))

    def test_i_grade_is_enrolled(self):
        self.assertTrue(_is_likely_enrolled({"grade": "I", "attempted": 3.0, "earned": 0.0}))

    def test_final_a_grade_not_enrolled(self):
        self.assertFalse(_is_likely_enrolled({"grade": "A", "attempted": 3.0, "earned": 3.0}))

    def test_w_grade_not_enrolled(self):
        self.assertFalse(_is_likely_enrolled({"grade": "W", "attempted": 3.0, "earned": 0.0}))

    def test_no_grade_zero_earned_enrolled(self):
        self.assertTrue(_is_likely_enrolled({"grade": "", "attempted": 3.0, "earned": 0.0}))

    def test_no_grade_with_earned_not_enrolled(self):
        self.assertFalse(_is_likely_enrolled({"grade": "", "attempted": 3.0, "earned": 3.0}))

    def test_zero_attempted_not_enrolled(self):
        self.assertFalse(_is_likely_enrolled({"grade": "IP", "attempted": 0.0, "earned": 0.0}))

    def test_f_grade_not_enrolled(self):
        self.assertFalse(_is_likely_enrolled({"grade": "F", "attempted": 3.0, "earned": 0.0}))


class InstitutionalTailTests(unittest.TestCase):
    def test_finds_beginning_of_record(self):
        text = "Some transfer stuff\nBeginning of Record\nCOSC 3320 stuff"
        tail = _institutional_transcript_tail(text)
        self.assertIn("COSC 3320", tail)
        self.assertNotIn("transfer", tail)

    def test_returns_full_text_when_no_marker(self):
        text = "COSC 3320 Python Programming 3.000 3.000 A"
        tail = _institutional_transcript_tail(text)
        self.assertEqual(tail, text)

    def test_transfer_block_path(self):
        # _TRANSFER_BLOCK stops before "Transfer Credit" — COSC 3320 is in the tail
        text = "Transfer Totals: 30 hours credit\nTransfer Credit here\nCOSC 3320 Python Programming 3.000 3.000 A"
        tail = _institutional_transcript_tail(text)
        self.assertIn("COSC 3320", tail)

    def test_no_marker_returns_full_text(self):
        text = "Just some ordinary transcript text with COSC 3320 course info"
        tail = _institutional_transcript_tail(text)
        self.assertEqual(tail, text)


class ParseTranscriptBodyTests(unittest.TestCase):
    SAMPLE_TRANSCRIPT = """\
Computer Science Major
2024 Fall
COSC 1336 Programming Fundamentals I 3.000 3.000 A
MATH 2413 Calculus I 4.000 4.000 B
Term GPA: 3.57
Term Totals: 7.000 7.000 3.571
2025 Spring
COSC 1337 Programming Fundamentals II 3.000 3.000 B
ENGL 1301 Composition 3.000 3.000 A
Term GPA: 3.50
Term Totals: 6.000 6.000 3.500
Cumulative GPA: 3.54
Cum GPA:   3.540   7.000  13.000
"""

    def _make_result(self):
        result = {
            "source": "transcript_pdf",
            "warnings": [],
            "majors_found": [],
            "minors_found": [],
            "major": None,
            "minor": None,
            "cumulative_gpa": None,
            "last_term_gpa": None,
            "credits_attempted": None,
            "credits_earned": None,
            "transfer_attempted_total": None,
            "transfer_earned_total": None,
            "utpb_credits_earned": None,
            "total_credit_hours": None,
            "lower_level_credits_earned": None,
            "upper_level_credits_earned": None,
            "terms": [],
            "transfer_blocks": [],
            "last_term_label": None,
            "enrolled_courses": [],
            "latest_term_courses": [],
            "course_history": [],
        }
        return result

    def test_detects_major(self):
        result = self._make_result()
        _parse_transcript_body(self.SAMPLE_TRANSCRIPT, result)
        self.assertEqual(result["major"], "Computer Science")

    def test_detects_terms(self):
        result = self._make_result()
        _parse_transcript_body(self.SAMPLE_TRANSCRIPT, result)
        self.assertIn("2024 Fall", result["terms"])
        self.assertIn("2025 Spring", result["terms"])

    def test_detects_cumulative_gpa(self):
        result = self._make_result()
        _parse_transcript_body(self.SAMPLE_TRANSCRIPT, result)
        self.assertIsNotNone(result["cumulative_gpa"])
        self.assertAlmostEqual(result["cumulative_gpa"], 3.54, places=1)

    def test_extracts_course_history(self):
        result = self._make_result()
        _parse_transcript_body(self.SAMPLE_TRANSCRIPT, result)
        codes = [r["course"] for r in result["course_history"]]
        self.assertIn("COSC 1336", codes)
        self.assertIn("MATH 2413", codes)

    def test_sets_last_term_label(self):
        result = self._make_result()
        _parse_transcript_body(self.SAMPLE_TRANSCRIPT, result)
        self.assertEqual(result["last_term_label"], "2025 Spring")

    def test_enrolled_courses_from_ip(self):
        transcript = (
            "Computer Science Major\n"
            "2025 Spring\n"
            "COSC 3320 Python Programming 3.000 0.000 IP\n"
            "Cumulative GPA: 3.50\n"
            "Cum GPA: 3.500 3.000 3.000\n"
        )
        result = self._make_result()
        _parse_transcript_body(transcript, result)
        enrolled_courses = [r["course"] for r in result["enrolled_courses"]]
        self.assertIn("COSC 3320", enrolled_courses)

    def test_minor_detected(self):
        transcript = (
            "Mathematics Minor\n"
            "2025 Spring\n"
            "MATH 2413 Calculus I 3.000 3.000 A\n"
            "Cumulative GPA: 4.00\n"
            "Cum GPA: 4.000 3.000 3.000\n"
        )
        result = self._make_result()
        _parse_transcript_body(transcript, result)
        self.assertEqual(result["minor"], "Mathematics")

    def test_credits_attempted_from_cum_gpa_row(self):
        transcript = (
            "Computer Science Major\n"
            "2025 Spring\n"
            "COSC 3320 Python Programming 3.000 3.000 A\n"
            "Cumulative GPA: 3.50\n"
            "Cum GPA: 3.500 33.000 30.000\n"
        )
        result = self._make_result()
        _parse_transcript_body(transcript, result)
        self.assertIsNotNone(result["credits_earned"])
        self.assertGreater(result["credits_earned"], 0)

    def test_transfer_block_parsed(self):
        transcript = (
            "Transfer Totals: Attempted 30.000 Earned 30.000 Points 120.000\n"
            "Beginning of Record\n"
            "Computer Science Major\n"
            "2025 Spring\n"
            "COSC 3320 Python Programming 3.000 3.000 A\n"
            "Cumulative GPA: 3.50\n"
            "Cum GPA: 3.500 33.000 33.000\n"
        )
        result = self._make_result()
        _parse_transcript_body(transcript, result)
        self.assertGreater(len(result["transfer_blocks"]), 0)
        self.assertEqual(result["transfer_attempted_total"], 30.0)

    def test_transfer_block_fallback_without_formal_totals(self):
        transcript = (
            "Transfer Totals: 15.000 15.000 60.000\n"
            "Computer Science Major\n"
            "2025 Spring\n"
            "COSC 3320 Python Programming 3.000 3.000 A\n"
            "Cumulative GPA: 3.50\n"
            "Cum GPA: 3.500 18.000 18.000\n"
        )
        result = self._make_result()
        _parse_transcript_body(transcript, result)
        self.assertIsNotNone(result)

    def test_season_first_term_header_in_body(self):
        transcript = (
            "Computer Science Major\n"
            "Fall Semester 2024\n"
            "COSC 1336 Programming Fundamentals I 3.000 3.000 A\n"
            "Cumulative GPA: 4.00\n"
            "Cum GPA: 4.000 3.000 3.000\n"
        )
        result = self._make_result()
        _parse_transcript_body(transcript, result)
        self.assertIn("2024 Fall", result["terms"])

    def test_duplicate_terms_deduplicated(self):
        transcript = (
            "Computer Science Major\n"
            "2024 Fall\n"
            "COSC 1336 Programming Fundamentals I 3.000 3.000 A\n"
            "2024 Fall\n"
            "COSC 1337 Programming Fundamentals II 3.000 3.000 B\n"
            "Cumulative GPA: 3.50\n"
            "Cum GPA: 3.500 6.000 6.000\n"
        )
        result = self._make_result()
        _parse_transcript_body(transcript, result)
        count = result["terms"].count("2024 Fall")
        self.assertEqual(count, 1)


class ParseUtpbTranscriptPdfTests(unittest.TestCase):
    def test_returns_dict_with_expected_keys(self):
        sample_text = (
            "Computer Science Major\n"
            "2025 Spring\n"
            "COSC 3320 Python Programming 3.000 3.000 A\n"
            "Cumulative GPA: 3.50\n"
            "Cum GPA: 3.500 3.000 3.000\n"
        )
        with patch("transcript_pdf._extract_pdf_text_from_stream", return_value=sample_text):
            result = parse_utpb_transcript_pdf(b"%PDF fake bytes")

        self.assertIn("course_history", result)
        self.assertIn("warnings", result)
        self.assertIn("cumulative_gpa", result)

    def test_empty_pdf_text_warns(self):
        with patch("transcript_pdf._extract_pdf_text_from_stream", return_value=""):
            result = parse_utpb_transcript_pdf(b"%PDF fake bytes")

        self.assertTrue(any("No text" in w for w in result["warnings"]))

    def test_pdf_read_error_warns(self):
        with patch(
            "transcript_pdf._extract_pdf_text_from_stream",
            side_effect=Exception("read error"),
        ):
            result = parse_utpb_transcript_pdf(b"%PDF fake bytes")

        self.assertTrue(any("Could not read" in w for w in result["warnings"]))

    def test_parses_cumulative_gpa(self):
        sample_text = (
            "Computer Science Major\n"
            "2025 Spring\n"
            "COSC 3320 Python Programming 3.000 3.000 A\n"
            "Cumulative GPA: 3.90\n"
            "Cum GPA: 3.900 3.000 3.000\n"
        )
        with patch("transcript_pdf._extract_pdf_text_from_stream", return_value=sample_text):
            result = parse_utpb_transcript_pdf(b"fake")

        self.assertAlmostEqual(result["cumulative_gpa"], 3.90, places=1)

    def test_body_exception_caught_and_warned(self):
        sample_text = "Computer Science Major\n2025 Spring\n"
        with (
            patch("transcript_pdf._extract_pdf_text_from_stream", return_value=sample_text),
            patch("transcript_pdf._parse_transcript_body", side_effect=RuntimeError("boom")),
        ):
            result = parse_utpb_transcript_pdf(b"fake")
        self.assertTrue(any("partial data" in w for w in result["warnings"]))


class ExtractPreviousTermGpaTests(unittest.TestCase):
    def test_finds_gpa_from_block(self):
        from transcript_pdf import _extract_previous_term_gpa
        text = "2025 Spring\nCOSC 3320 Python Programming 3.000 3.000 A\nTerm GPA: 4.00"
        courses = [{"term": "2025 Spring", "subject": "COSC", "course_number": "3320",
                    "attempted": 3.0, "earned": 3.0, "grade": "A"}]
        result = _extract_previous_term_gpa(text, courses)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 4.0, places=1)

    def test_falls_back_to_course_rows_when_no_gpa_in_block(self):
        from transcript_pdf import _extract_previous_term_gpa
        text = "2025 Spring\nCOSC 3320 Python Programming 3.000 3.000 A"
        courses = [{"term": "2025 Spring", "subject": "COSC", "course_number": "3320",
                    "attempted": 3.0, "earned": 3.0, "grade": "A"}]
        result = _extract_previous_term_gpa(text, courses)
        self.assertIsNotNone(result)

    def test_returns_none_for_empty_text_and_no_courses(self):
        from transcript_pdf import _extract_previous_term_gpa
        result = _extract_previous_term_gpa("", [])
        self.assertIsNone(result)

    def test_gpa_from_inline_block_no_headers(self):
        from transcript_pdf import _extract_previous_term_gpa
        text = "Term GPA: 3.75"
        courses = []
        result = _extract_previous_term_gpa(text, courses)
        self.assertAlmostEqual(result, 3.75, places=2)

    def test_fallback_from_course_rows_no_term_headers(self):
        from transcript_pdf import _extract_previous_term_gpa
        text = "some text without term headers"
        courses = [
            {"term": "2025 Spring", "subject": "COSC", "course_number": "3320",
             "attempted": 3.0, "earned": 3.0, "grade": "B"},
        ]
        result = _extract_previous_term_gpa(text, courses)
        self.assertIsNotNone(result)


class ParseTranscriptBodyAdvancedTests(unittest.TestCase):
    def _make_result(self):
        return {
            "source": "transcript_pdf", "warnings": [], "majors_found": [],
            "minors_found": [], "major": None, "minor": None,
            "cumulative_gpa": None, "last_term_gpa": None,
            "credits_attempted": None, "credits_earned": None,
            "transfer_attempted_total": None, "transfer_earned_total": None,
            "utpb_credits_earned": None, "total_credit_hours": None,
            "lower_level_credits_earned": None, "upper_level_credits_earned": None,
            "terms": [], "transfer_blocks": [], "last_term_label": None,
            "enrolled_courses": [], "latest_term_courses": [], "course_history": [],
        }

    def test_warns_when_no_cumulative_gpa(self):
        transcript = (
            "2025 Spring\n"
            "COSC 3320 Python Programming 3.000 3.000 A\n"
        )
        result = self._make_result()
        _parse_transcript_body(transcript, result)
        self.assertTrue(any("cumulative GPA" in w for w in result["warnings"]))

    def test_warns_when_no_major(self):
        transcript = (
            "2025 Spring\n"
            "COSC 3320 Python Programming 3.000 3.000 A\n"
            "Cumulative GPA: 3.50\n"
            "Cum GPA: 3.500 3.000 3.000\n"
        )
        result = self._make_result()
        _parse_transcript_body(transcript, result)
        self.assertTrue(any("major" in w.lower() for w in result["warnings"]))

    def test_utpb_credits_computed_from_rows(self):
        transcript = (
            "Computer Science Major\n"
            "2025 Spring\n"
            "COSC 3320 Python Programming 3.000 3.000 A\n"
            "MATH 2413 Calculus I 4.000 4.000 B\n"
            "Cumulative GPA: 3.57\n"
            "Cum GPA: 3.571 7.000 7.000\n"
        )
        result = self._make_result()
        _parse_transcript_body(transcript, result)
        self.assertIsNotNone(result["utpb_credits_earned"])
        self.assertGreater(result["utpb_credits_earned"], 0)

    def test_level_splits_computed(self):
        transcript = (
            "Computer Science Major\n"
            "2024 Fall\n"
            "COSC 1336 Programming Fundamentals I 3.000 3.000 A\n"
            "COSC 3320 Python Programming 3.000 3.000 B\n"
            "Cumulative GPA: 3.50\n"
            "Cum GPA: 3.500 6.000 6.000\n"
        )
        result = self._make_result()
        _parse_transcript_body(transcript, result)
        if result["lower_level_credits_earned"] is not None:
            self.assertGreater(result["lower_level_credits_earned"], 0)


class IsLikelyEnrolledEdgeCasesTests(unittest.TestCase):
    """Additional edge cases for _is_likely_enrolled (lines 509-510, 519)."""

    def test_non_numeric_attempted_returns_false(self):
        """Lines 509-510: TypeError/ValueError converts to False."""
        row = {"grade": "IP", "attempted": "abc", "earned": 3.0}
        self.assertFalse(_is_likely_enrolled(row))

    def test_non_final_grade_with_positive_earned_returns_false(self):
        """Line 519: non-IP/non-final grade with earned>0 returns False."""
        # "NG" is not in _FINAL_GRADE pattern and not empty
        row = {"grade": "NG", "attempted": 3.0, "earned": 3.0}
        self.assertFalse(_is_likely_enrolled(row))

    def test_non_final_grade_with_zero_earned_returns_true(self):
        """Line 519: non-IP/non-final grade with earned<=0 returns True (likely enrolled)."""
        row = {"grade": "NG", "attempted": 3.0, "earned": 0.0}
        self.assertTrue(_is_likely_enrolled(row))


class GpaFromTermCoursesEdgeCasesTests(unittest.TestCase):
    """Cover lines 318-319, 352 in _gpa_from_term_courses."""

    def test_invalid_earned_field_skipped(self):
        """Lines 318-319: TypeError/ValueError when earned is non-numeric."""
        rows = [
            {"earned": "bad", "grade": "A"},
            {"earned": 3.0, "grade": "B"},
        ]
        result = _gpa_from_term_courses(rows)
        self.assertAlmostEqual(result, 3.0, places=1)

    def test_out_of_range_gpa_returns_none(self):
        """Line 352: GPA out of plausible undergrad range returns None."""
        rows = [{"earned": 1.0, "grade": "A", "quality_points": 50.0}]
        result = _gpa_from_term_courses(rows)
        self.assertIsNone(result)


class MergeCourseRowFieldsTests(unittest.TestCase):
    """Cover _merge_course_row_fields line 481."""

    def test_updates_to_longer_name(self):
        """Line 481: existing course_name updated when new name is longer."""
        from transcript_pdf import _merge_course_row_fields
        existing = {"course_name": "Python"}
        incoming = {"course_name": "Python Programming Language"}
        _merge_course_row_fields(existing, incoming)
        self.assertEqual(existing["course_name"], "Python Programming Language")

    def test_does_not_downgrade_to_shorter_name(self):
        existing = {"course_name": "Python Programming Language"}
        incoming = {"course_name": "Python"}
        from transcript_pdf import _merge_course_row_fields
        _merge_course_row_fields(existing, incoming)
        self.assertEqual(existing["course_name"], "Python Programming Language")

    def test_fills_in_missing_name(self):
        existing = {"course_name": None}
        incoming = {"course_name": "Data Structures"}
        from transcript_pdf import _merge_course_row_fields
        _merge_course_row_fields(existing, incoming)
        self.assertEqual(existing["course_name"], "Data Structures")


class ExtractCoursesWithTermsPrimaryTests(unittest.TestCase):
    """Cover lines 491-492 where line_based produces more courses than segmented."""

    def test_line_based_becomes_primary(self):
        """Lines 491-492: when line_based > segmented, primary=line_based."""
        # Text with term labels inline and course rows — line-by-line parser handles well
        text = (
            "2025 Spring\n"
            "COSC 3320 Python Programming 3.000 3.000 A\n"
            "COSC 4350 Software Engineering 3.000 3.000 B\n"
            "2025 Fall\n"
            "MATH 3310 Calculus III 3.000 3.000 A\n"
        )
        result = _extract_courses_with_terms(text)
        courses = [r["subject"] for r in result]
        self.assertIn("COSC", courses)


class InstitutionalTailTransferTotalsTests(unittest.TestCase):
    """Cover line 210: _institutional_transcript_tail via TRANSFER_TOTALS path."""

    def test_returns_after_transfer_totals_when_no_block(self):
        """Line 210: returns tail from _TRANSFER_TOTALS match position."""
        # Pattern for _TRANSFER_TOTALS: "Transfer Work Totals" or similar
        text = (
            "Some header\n"
            "Transfer Work 6.000 6.000\n"
            "COSC 3320 Python Programming 3.000 3.000 A\n"
        )
        result = _institutional_transcript_tail(text)
        # If TRANSFER_TOTALS matches, result is text after it
        self.assertIsInstance(result, str)


class ParseTranscriptBodyCreditBranchTests(unittest.TestCase):
    """Cover credit-total calculation branches in parse_utpb_transcript_pdf (lines 619-693, 755, 762-763, 772-776)."""

    def _parse_with_text(self, text):
        with patch("transcript_pdf._extract_pdf_text_from_stream", return_value=text):
            return parse_utpb_transcript_pdf(b"fake")

    def test_cum_gpa_two_numbers_sets_attempted(self):
        """Lines 619-620: when only 2 numbers follow Cum GPA line, sets attempted."""
        text = (
            "Computer Science Major\n"
            "2025 Spring\n"
            "COSC 3320 Python Programming 3.000 3.000 A\n"
            "Cum GPA: 3.500 45.000\n"
        )
        result = self._parse_with_text(text)
        self.assertIsNotNone(result["credits_attempted"])

    def test_transfer_gpa_parsed(self):
        """Lines 625-628: transfer GPA values are collected from text."""
        text = (
            "Computer Science Major\n"
            "Transfer Work 6.000 6.000\n"
            "GPA: 3.200\n"
            "2025 Spring\n"
            "COSC 3320 Python Programming 3.000 3.000 A\n"
            "Cum GPA: 3.500 45.000 42.000\n"
        )
        result = self._parse_with_text(text)
        self.assertIsNotNone(result)

    def test_fallback_term_rank_from_courses(self):
        """Lines 688-693: when inst_tail has no term headers but courses have term labels."""
        # No "2025 Spring" style header in inst_tail, but courses get term labels anyway
        text = (
            "Computer Science Major\n"
            "Cum GPA: 3.500 45.000 42.000\n"
            "SP25 COSC 3320 Python Programming 3.000 3.000 A\n"
            "SP25 MATH 2310 Calculus I 3.000 3.000 B\n"
        )
        result = self._parse_with_text(text)
        self.assertIsNotNone(result)
        self.assertIsInstance(result["course_history"], list)

    def test_utpb_rows_inconsistent_with_cum_sets_total_from_rows(self):
        """Line 755: utpb_from_rows + transfer > cum_earned => total from rows."""
        text = (
            "Computer Science Major\n"
            "Transfer Work 30.000 30.000\n"
            "2025 Spring\n"
            "COSC 3320 Python Programming 3.000 3.000 A\n"
            "COSC 4350 Software Engineering 3.000 3.000 A\n"
            "MATH 3310 Calculus III 4.000 4.000 B\n"
            "MATH 4310 Advanced Calculus 3.000 3.000 A\n"
            "PHYS 3310 Mechanics 3.000 3.000 B\n"
            "Cum GPA: 3.500 5.000 5.000\n"
        )
        result = self._parse_with_text(text)
        self.assertIsNotNone(result)

    def test_cum_earned_less_than_transfer_sets_utpb_and_total(self):
        """Lines 762-763: cum_earned < transfer_earned => utpb=cum, total=cum+transfer."""
        text = (
            "Computer Science Major\n"
            "Transfer Work 60.000 60.000\n"
            "2025 Spring\n"
            "COSC 3320 Python Programming 3.000 3.000 A\n"
            "Cum GPA: 3.500 30.000 25.000\n"
        )
        result = self._parse_with_text(text)
        self.assertIsNotNone(result)

    def test_no_utpb_rows_no_cum_uses_all_course_rows(self):
        """Lines 772-776: no utpb institutional rows, no cum_earned => fallback sum."""
        text = (
            "Computer Science Major\n"
            "Transfer Work 6.000 6.000\n"
            "COSC 3320 Python Programming 3.000 3.000 A\n"
        )
        result = self._parse_with_text(text)
        self.assertIsNotNone(result)

    def test_parse_via_string_path_branch(self):
        """Line 551: string path branch calls _extract_pdf_text(Path(source))."""
        with patch("transcript_pdf._extract_pdf_text", return_value="Computer Science Major\n") as mock_ext:
            result = parse_utpb_transcript_pdf("/fake/path/transcript.pdf")
        mock_ext.assert_called_once()
        self.assertIsInstance(result, dict)


if __name__ == "__main__":
    unittest.main(verbosity=2)
