#!/usr/bin/env python3
"""In-process unit tests for validate_formulae._write_step_summary.

The sibling scripts/test_validate_formulae_step_summary.py exercises
the same behaviour by invoking the script as a subprocess. Subprocess
runs do not contribute to coverage.py's in-process measurement, which
is why scripts/validate_formulae.py's _write_step_summary body
(lines 124-146) currently reports uncovered even though the behaviour
is exercised end-to-end.

These tests call _write_step_summary directly so the branches inside
it are attributed to the module. Behaviour is asserted from the file
content it writes; no subprocess is spawned.
"""

import os
import tempfile
import unittest
from pathlib import Path

from validate_formulae import MAX_STEP_SUMMARY_ERRORS, _write_step_summary


class WriteStepSummaryTests(unittest.TestCase):
    def setUp(self):
        self._saved_env = os.environ.get("GITHUB_STEP_SUMMARY")
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.summary_path = Path(self._tmp.name) / "summary.md"

    def tearDown(self):
        if self._saved_env is None:
            os.environ.pop("GITHUB_STEP_SUMMARY", None)
        else:
            os.environ["GITHUB_STEP_SUMMARY"] = self._saved_env

    def _set_env(self):
        os.environ["GITHUB_STEP_SUMMARY"] = str(self.summary_path)

    def test_no_op_when_env_unset(self):
        os.environ.pop("GITHUB_STEP_SUMMARY", None)
        _write_step_summary("pass", 5, 0, [])
        self.assertFalse(self.summary_path.exists())

    def test_pass_status_writes_check_icon_and_no_details(self):
        self._set_env()
        _write_step_summary("pass", 7, 0, [])
        content = self.summary_path.read_text(encoding="utf-8")
        self.assertIn("### Formula drift check", content)
        self.assertIn("✅ pass", content)
        self.assertIn("| 7 | 0 |", content)
        self.assertNotIn("<details>", content)

    def test_fail_status_writes_cross_icon(self):
        self._set_env()
        _write_step_summary("fail", 3, 2, ["boom-a", "boom-b"])
        content = self.summary_path.read_text(encoding="utf-8")
        self.assertIn("❌ fail", content)
        self.assertIn("| 3 | 2 |", content)
        self.assertIn("<details><summary>Error details</summary>", content)
        self.assertIn("- boom-a", content)
        self.assertIn("- boom-b", content)
        self.assertIn("</details>", content)

    def test_errors_truncated_with_overflow_notice(self):
        self._set_env()
        errors = [f"err-{i}" for i in range(MAX_STEP_SUMMARY_ERRORS + 5)]
        _write_step_summary("fail", 10, len(errors), errors)
        content = self.summary_path.read_text(encoding="utf-8")
        # First MAX_STEP_SUMMARY_ERRORS entries appear individually.
        self.assertIn(f"- err-0", content)
        self.assertIn(f"- err-{MAX_STEP_SUMMARY_ERRORS - 1}", content)
        # Anything past the cap is collapsed into an "...and N more" line.
        self.assertNotIn(f"- err-{MAX_STEP_SUMMARY_ERRORS}", content)
        self.assertIn(f"- ...and 5 more (see step log)", content)

    def test_errors_at_exactly_cap_no_overflow_notice(self):
        self._set_env()
        errors = [f"err-{i}" for i in range(MAX_STEP_SUMMARY_ERRORS)]
        _write_step_summary("fail", 10, len(errors), errors)
        content = self.summary_path.read_text(encoding="utf-8")
        self.assertIn(f"- err-{MAX_STEP_SUMMARY_ERRORS - 1}", content)
        self.assertNotIn("more (see step log)", content)

    def test_appends_rather_than_overwrites(self):
        self._set_env()
        self.summary_path.write_text("PRE-EXISTING\n", encoding="utf-8")
        _write_step_summary("pass", 1, 0, [])
        content = self.summary_path.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("PRE-EXISTING\n"))
        self.assertIn("### Formula drift check", content)


if __name__ == "__main__":
    unittest.main()
