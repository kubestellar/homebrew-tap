#!/usr/bin/env python3
"""In-process unit tests for scripts/validate_formulae.py::_write_step_summary.

The existing scripts/test_validate_formulae_step_summary.py exercises this
function by shelling out to `python3 validate_formulae.py <dir>` in a
subprocess. That correctly asserts end-to-end file contents, but the
subprocess coverage is not visible to `pytest --cov=validate_formulae`,
which is why lines 124-146 (all of _write_step_summary) still report
as uncovered by our CI coverage tool.

These tests import _write_step_summary directly and drive it through
each branch of its markdown-table generator:

  1. GITHUB_STEP_SUMMARY unset -> no-op (return without writing).
  2. status='pass', no errors -> table + pass icon, NO <details> block.
  3. status='fail' with errors below MAX_STEP_SUMMARY_ERRORS ->
     every error rendered as a <details> list item, no overflow line.
  4. status='fail' with errors above MAX_STEP_SUMMARY_ERRORS ->
     only the first N shown, plus an "...and K more" overflow line.
  5. status='error' with no errors -> error icon, table only, no
     <details> block, matches the empty-dir path from the subprocess
     suite from within the module for coverage attribution.
  6. Appending to a pre-populated summary file preserves existing
     content (open mode is "a", not "w").
"""

import io
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import validate_formulae as vf


class WriteStepSummaryBranches(unittest.TestCase):
    def setUp(self):
        # Remove any leftover env from other tests / the CI harness so
        # the no-op branch is testable.
        self._saved = os.environ.pop("GITHUB_STEP_SUMMARY", None)

    def tearDown(self):
        if self._saved is not None:
            os.environ["GITHUB_STEP_SUMMARY"] = self._saved

    def test_no_env_var_is_a_no_op(self):
        # Must not raise, must not touch anything. If it did, it would
        # raise FileNotFoundError on the missing summary path.
        vf._write_step_summary("pass", 3, 0, [])

    def test_pass_writes_table_without_details(self):
        with TemporaryDirectory() as d:
            summary = Path(d) / "step.md"
            os.environ["GITHUB_STEP_SUMMARY"] = str(summary)
            vf._write_step_summary("pass", 5, 0, [])
            content = summary.read_text()
        self.assertIn("### Formula drift check", content)
        self.assertIn("✅ pass", content)
        # Header row + one data row.
        self.assertIn("| Status | Formulae checked | Errors |", content)
        self.assertIn("| 5 | 0 |", content)
        # Pass path must NOT emit a details block.
        self.assertNotIn("<details>", content)

    def test_fail_with_few_errors_renders_every_error_and_no_overflow(self):
        errors = ["malformed sha256 in a.rb", "missing url in b.rb"]
        with TemporaryDirectory() as d:
            summary = Path(d) / "step.md"
            os.environ["GITHUB_STEP_SUMMARY"] = str(summary)
            vf._write_step_summary("fail", 2, len(errors), errors)
            content = summary.read_text()
        self.assertIn("❌ fail", content)
        self.assertIn("<details><summary>Error details</summary>", content)
        for e in errors:
            self.assertIn(f"- {e}", content)
        # Below the cap -> no overflow line.
        self.assertNotIn("more (see step log)", content)
        self.assertIn("</details>", content)

    def test_fail_with_many_errors_caps_at_max_and_reports_overflow(self):
        # MAX_STEP_SUMMARY_ERRORS+3 exercises the "shown" slice AND
        # the `len(errors) > len(shown)` overflow branch.
        overflow = 3
        errors = [f"err-{i}" for i in range(vf.MAX_STEP_SUMMARY_ERRORS + overflow)]
        with TemporaryDirectory() as d:
            summary = Path(d) / "step.md"
            os.environ["GITHUB_STEP_SUMMARY"] = str(summary)
            vf._write_step_summary("fail", 100, len(errors), errors)
            content = summary.read_text()
        # Only the first MAX are rendered.
        for i in range(vf.MAX_STEP_SUMMARY_ERRORS):
            self.assertIn(f"- err-{i}", content)
        # The overflowed ones are NOT rendered individually.
        for i in range(vf.MAX_STEP_SUMMARY_ERRORS, vf.MAX_STEP_SUMMARY_ERRORS + overflow):
            self.assertNotIn(f"- err-{i}\n", content)
        self.assertIn(f"...and {overflow} more (see step log)", content)

    def test_error_status_uses_fail_icon(self):
        # Any non-'pass' status resolves to the ❌ icon; verifies the
        # ternary at the top of the function reaches its else arm for a
        # status other than 'fail'.
        with TemporaryDirectory() as d:
            summary = Path(d) / "step.md"
            os.environ["GITHUB_STEP_SUMMARY"] = str(summary)
            vf._write_step_summary("error", 0, 1, ["no .rb files found in the given path"])
            content = summary.read_text()
        self.assertIn("❌ error", content)
        self.assertIn("no .rb files found in the given path", content)

    def test_appends_to_existing_summary_file(self):
        # open(..., "a") — the function must NOT truncate a pre-existing
        # summary file. A regression to "w" would silently discard other
        # steps' summaries.
        with TemporaryDirectory() as d:
            summary = Path(d) / "step.md"
            summary.write_text("### previous step\n\nprior content\n")
            os.environ["GITHUB_STEP_SUMMARY"] = str(summary)
            vf._write_step_summary("pass", 1, 0, [])
            content = summary.read_text()
        self.assertIn("### previous step", content)
        self.assertIn("prior content", content)
        self.assertIn("### Formula drift check", content)


if __name__ == "__main__":
    unittest.main()
