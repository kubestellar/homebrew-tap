#!/usr/bin/env python3
"""Unit tests for scripts/validate_formulae.py::_write_step_summary.

Closes coverage gap on lines 124-146 of validate_formulae.py (the
$GITHUB_STEP_SUMMARY renderer), which had 0% coverage prior to this
file. Tests exercise the no-op path, the pass/fail icon selection, the
error-list truncation at MAX_STEP_SUMMARY_ERRORS, and the append-only
semantics of the summary file.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate_formulae import MAX_STEP_SUMMARY_ERRORS, _write_step_summary


class TestWriteStepSummaryNoop(unittest.TestCase):
    """When GITHUB_STEP_SUMMARY is unset the function must be a no-op."""

    def test_env_unset_writes_nothing(self):
        prev = os.environ.pop("GITHUB_STEP_SUMMARY", None)
        try:
            _write_step_summary("pass", 2, 0, [])
        finally:
            if prev is not None:
                os.environ["GITHUB_STEP_SUMMARY"] = prev
        self.assertNotIn("GITHUB_STEP_SUMMARY", os.environ)

    def test_env_empty_string_writes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            probe = Path(td) / "should-not-exist"
            os.environ["GITHUB_STEP_SUMMARY"] = ""
            try:
                _write_step_summary("fail", 3, 5, ["boom"])
            finally:
                os.environ.pop("GITHUB_STEP_SUMMARY", None)
            self.assertFalse(probe.exists())


class TestWriteStepSummaryContent(unittest.TestCase):
    """Rendered markdown must include the correct icon, counts, and rows."""

    def _run(self, status, formula_count, error_count, errors):
        td = tempfile.mkdtemp()
        summary_path = Path(td) / "summary.md"
        os.environ["GITHUB_STEP_SUMMARY"] = str(summary_path)
        try:
            _write_step_summary(status, formula_count, error_count, errors)
        finally:
            os.environ.pop("GITHUB_STEP_SUMMARY", None)
        return summary_path.read_text(encoding="utf-8")

    def test_pass_no_errors_renders_check_icon(self):
        text = self._run("pass", 2, 0, [])
        self.assertIn("### Formula drift check", text)
        self.assertIn("✅ pass", text)
        self.assertIn("| 2 | 0 |", text)
        self.assertNotIn("<details>", text)
        self.assertTrue(text.endswith("\n"))

    def test_fail_with_errors_renders_x_icon_and_details(self):
        errors = ["ops: bad sha", "deploy: missing url"]
        text = self._run("fail", 2, 2, errors)
        self.assertIn("❌ fail", text)
        self.assertIn("| 2 | 2 |", text)
        self.assertIn("<details><summary>Error details</summary>", text)
        self.assertIn("- ops: bad sha", text)
        self.assertIn("- deploy: missing url", text)
        self.assertIn("</details>", text)
        self.assertNotIn("...and", text)

    def test_error_list_truncated_to_max(self):
        overflow = 7
        errors = [f"err-{i}" for i in range(MAX_STEP_SUMMARY_ERRORS + overflow)]
        text = self._run("fail", 99, len(errors), errors)
        for i in range(MAX_STEP_SUMMARY_ERRORS):
            self.assertIn(f"- err-{i}", text)
        self.assertNotIn(f"- err-{MAX_STEP_SUMMARY_ERRORS}", text)
        self.assertIn(
            f"- ...and {overflow} more (see step log)",
            text,
        )

    def test_at_boundary_no_truncation_notice(self):
        errors = [f"e{i}" for i in range(MAX_STEP_SUMMARY_ERRORS)]
        text = self._run("fail", 1, len(errors), errors)
        self.assertIn(f"- e{MAX_STEP_SUMMARY_ERRORS - 1}", text)
        self.assertNotIn("...and", text)


class TestWriteStepSummaryAppendSemantics(unittest.TestCase):
    """The function must append; a second call must not clobber the first."""

    def test_append_preserves_prior_content(self):
        td = tempfile.mkdtemp()
        summary_path = Path(td) / "summary.md"
        summary_path.write_text("PRE-EXISTING\n", encoding="utf-8")
        os.environ["GITHUB_STEP_SUMMARY"] = str(summary_path)
        try:
            _write_step_summary("pass", 1, 0, [])
            _write_step_summary("fail", 1, 1, ["oops"])
        finally:
            os.environ.pop("GITHUB_STEP_SUMMARY", None)
        text = summary_path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("PRE-EXISTING\n"))
        self.assertEqual(text.count("### Formula drift check"), 2)
        self.assertIn("✅ pass", text)
        self.assertIn("❌ fail", text)


if __name__ == "__main__":
    unittest.main()
