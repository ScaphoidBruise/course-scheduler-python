import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scrapers.program_requirements import (  # noqa: E402
    ProgramRef,
    discover_programs,
    parse_program_html,
    save_programs,
)


SAMPLE_HTML = """
<html>
<body>
<h1>Computer Science, BS</h1>
<h2>Degree Requirements</h2>
<p>Students must select one track option.</p>
<table>
  <tr><th>Course Number</th><th>Course Title</th><th>Credits</th></tr>
  <tr>
    <td class="sc-coursenumber"><a class="sc-courselink">COSC 1430</a></td>
    <td class="sc-coursetitle">Introduction To Computer Science I</td>
    <td class="sc-credits"><p class="credits">4</p></td>
  </tr>
  <tr><td class="sc-totalcreditslabel" colspan="2">Total Credit Hours:</td><td class="sc-totalcredits">120</td></tr>
</table>
<h3>Upper Level Required Courses</h3>
<table>
  <tr><th>Course Number</th><th>Course Title</th><th>Credits</th></tr>
  <tr><td>COSC 3320</td><td>Python Programming</td><td>3</td></tr>
  <tr><td class="sc-totalcreditslabel" colspan="2">Total Credit Hours:</td><td>3</td></tr>
</table>
</body>
</html>
"""


class ProgramRequirementsTests(unittest.TestCase):
    def test_discover_programs_from_catalog_tree(self):
        catalog = {
            "Name": "Root",
            "Path": "/root",
            "Children": [
                {
                    "Name": "Programs of Study",
                    "Path": "/2025-2026/2025-2026-Undergraduate-Catalog/Programs-of-Study",
                    "Children": [
                        {
                            "Name": "Computer Science, BS",
                            "Path": "/2025-2026/2025-2026-Undergraduate-Catalog/Programs-of-Study/Computer-Science-BS",
                        },
                        {
                            "Name": "Biology, BS",
                            "Path": "/2025-2026/2025-2026-Undergraduate-Catalog/Programs-of-Study/Biology-BS",
                            "Children": [
                                {
                                    "Name": "Biology, BS - Molecular Biology Track",
                                    "Path": "/2025-2026/2025-2026-Undergraduate-Catalog/Programs-of-Study/Biology-BS/Biology-BS-Molecular-Biology-Track",
                                }
                            ],
                        }
                    ],
                }
            ],
        }

        programs = discover_programs(catalog)

        self.assertEqual(len(programs), 2)
        self.assertEqual(programs[0].name, "Computer Science, BS")
        self.assertEqual(programs[1].name, "Biology, BS - Molecular Biology Track")

    def test_parse_program_html_blocks_courses_and_warnings(self):
        program = ProgramRef(
            name="Computer Science, BS",
            path="/2025-2026/2025-2026-Undergraduate-Catalog/Programs-of-Study/Computer-Science-BS",
        )

        parsed = parse_program_html(program, SAMPLE_HTML, fetched_at="2026-01-01T00:00:00+00:00")

        self.assertEqual(parsed.total_credits, 120)
        self.assertEqual(parsed.degree_total_credits, 120)
        self.assertEqual(len(parsed.blocks), 2)
        self.assertEqual(parsed.blocks[0].heading, "Degree Requirements")
        self.assertEqual(parsed.blocks[0].requirement_type, "choice_option")
        self.assertEqual(parsed.blocks[0].courses[0].course_code, "COSC 1430")
        self.assertEqual(parsed.blocks[1].courses[0].course_title, "Python Programming")
        self.assertTrue(any("Option-like text" in warning for warning in parsed.warnings))

    def test_section_total_bubbles_to_parent_heading(self):
        program = ProgramRef(
            name="Computer Science, BS",
            path="/2025-2026/2025-2026-Undergraduate-Catalog/Programs-of-Study/Computer-Science-BS",
        )
        html = """
        <h2>General Education Requirements</h2>
        <h3>Language, Philosophy, and Culture</h3>
        <table>
          <tr><th>Course Number</th><th>Course Title</th><th>Credits</th></tr>
          <tr><td>ENGL 2322</td><td>British Literature To 1800</td><td>3</td></tr>
          <tr><td>PHIL 2300</td><td>Introduction to Philosophy</td><td>3</td></tr>
          <tr><td class="sc-totalcreditslabel">Total Credit Hours:</td><td>3</td></tr>
        </table>
        <p>Total Credit Hours: 42</p>
        <h2>Major Requirements</h2>
        <h3>Capstone Course</h3>
        <table>
          <tr><th>Course Number</th><th>Course Title</th><th>Credits</th></tr>
          <tr><td>NTSC 4311</td><td>History and Philosophy of Science</td><td>3</td></tr>
          <tr><td class="sc-totalcreditslabel">Total Credit Hours:</td><td>37</td></tr>
        </table>
        """

        parsed = parse_program_html(program, html, fetched_at="2026-01-01T00:00:00+00:00")
        by_heading = {block.heading: block for block in parsed.blocks}

        self.assertEqual(by_heading["General Education Requirements"].min_credits, 42)
        self.assertEqual(by_heading["Language, Philosophy, and Culture"].min_credits, 3)
        self.assertEqual(by_heading["Major Requirements"].min_credits, 37)
        self.assertIsNone(by_heading["Capstone Course"].min_credits)

    def test_save_programs_replaces_existing_program_rows(self):
        program = ProgramRef(
            name="Computer Science, BS",
            path="/2025-2026/2025-2026-Undergraduate-Catalog/Programs-of-Study/Computer-Science-BS",
        )
        parsed = parse_program_html(program, SAMPLE_HTML, fetched_at="2026-01-01T00:00:00+00:00")

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "requirements.db"
            save_programs(db_path, [parsed])
            save_programs(db_path, [parsed])

            conn = sqlite3.connect(db_path)
            try:
                program_count = conn.execute("SELECT COUNT(*) FROM program_requirements").fetchone()[0]
                block_count = conn.execute("SELECT COUNT(*) FROM program_requirement_blocks").fetchone()[0]
                course_count = conn.execute("SELECT COUNT(*) FROM program_requirement_courses").fetchone()[0]
                degree_total = conn.execute(
                    "SELECT degree_total_credits FROM program_requirements"
                ).fetchone()[0]
                block_type = conn.execute(
                    "SELECT requirement_type FROM program_requirement_blocks ORDER BY display_order LIMIT 1"
                ).fetchone()[0]
            finally:
                conn.close()

        self.assertEqual(program_count, 1)
        self.assertEqual(block_count, 2)
        self.assertEqual(course_count, 2)
        self.assertEqual(degree_total, 120)
        self.assertEqual(block_type, "choice_option")


if __name__ == "__main__":
    unittest.main()
