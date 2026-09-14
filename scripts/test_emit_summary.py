#!/usr/bin/env python3
"""Unit tests for validate_formulae.emit_summary + _write_step_summary.

These target the GitHub-Actions-facing summary path (`$GITHUB_STEP_SUMMARY`
markdown table), which was uncovered on main: `validate_formulae.py` had
grown from 70 -> 102 statements with the step-summary path landing at 0%
coverage. See #332.
"""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
from validate_formulae import (
    MAX_STEP_SUMMARY_ERRORS,
    SUMMARY_PREFIX,
    emit_summary,
)


class TestEmitSummaryJSONLine(unittest.TestCase):
    """The stdout JSON line must render regardless of GITHUB_STEP_SUMMARY."""

    def test_prints_prefix_and_valid_json(self):
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GITHUB_STEP_SUMMARY", None)
            with redirect_stdout(buf):
                emit_summary(status="pass", formula_count=3, error_count=0)
        line = buf.getvalue().strip()
        self.assertTrue(line.startswith(SUMMARY_PREFIX))
        payload = json.loads(line[len(SUMMARY_PREFIX):].strip())
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["formula_count"], 3)
        self.assertEqual(payload["error_count"], 0)

    def test_json_keys_are_sorted(self):
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GITHUB_STEP_SUMMARY", None)
            with redirect_stdout(buf):
                emit_summary(status="fail", formula_count=2, error_count=1)
        payload_str = buf.getvalue().strip()[len(SUMMARY_PREFIX):].strip()
        # sort_keys=True -> alphabetical: error_count < formula_count < status
        self.assertLess(payload_str.index("error_count"), payload_str.index("formula_count"))
        self.assertLess(payload_str.index("formula_count"), payload_str.index("status"))


class TestWriteStepSummaryNoop(unittest.TestCase):
    """No GITHUB_STEP_SUMMARY -> file write path is skipped cleanly."""

    def test_no_env_var_no_write(self):
        # Also verifies emit_summary does not crash when errors=None.
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GITHUB_STEP_SUMMARY", None)
            with redirect_stdout(io.StringIO()):
                emit_summary(status="pass", formula_count=1, error_count=0)
        # No exception, no file leaked. Nothing more to assert.


class TestWriteStepSummaryPass(unittest.TestCase):
    def test_pass_status_renders_check_icon_and_table(self):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".md") as f:
            summary_path = f.name
        self.addCleanup(os.unlink, summary_path)

        with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": summary_path}):
            with redirect_stdout(io.StringIO()):
                emit_summary(status="pass", formula_count=5, error_count=0)

        content = Path(summary_path).read_text(encoding="utf-8")
        self.assertIn("### Formula drift check", content)
        self.assertIn("✅ pass", content)
        self.assertIn("| 5 | 0 |", content)
        # No <details> block when there are no errors.
        self.assertNotIn("<details>", content)


class TestWriteStepSummaryFail(unittest.TestCase):
    def test_fail_status_renders_x_icon_and_error_details(self):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".md") as f:
            summary_path = f.name
        self.addCleanup(os.unlink, summary_path)

        errors = ["Formula A: bad sha", "Formula B: missing version"]
        with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": summary_path}):
            with redirect_stdout(io.StringIO()):
                emit_summary(
                    status="fail",
                    formula_count=2,
                    error_count=len(errors),
                    errors=errors,
                )

        content = Path(summary_path).read_text(encoding="utf-8")
        self.assertIn("❌ fail", content)
        self.assertIn("<details><summary>Error details</summary>", content)
        self.assertIn("- Formula A: bad sha", content)
        self.assertIn("- Formula B: missing version", content)
        self.assertIn("</details>", content)
        # No truncation footer for a short list.
        self.assertNotIn("...and", content)

    def test_error_list_truncated_at_max_with_footer(self):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".md") as f:
            summary_path = f.name
        self.addCleanup(os.unlink, summary_path)

        errors = [f"err-{i}" for i in range(MAX_STEP_SUMMARY_ERRORS + 5)]
        with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": summary_path}):
            with redirect_stdout(io.StringIO()):
                emit_summary(
                    status="fail",
                    formula_count=1,
                    error_count=len(errors),
                    errors=errors,
                )

        content = Path(summary_path).read_text(encoding="utf-8")
        self.assertIn(f"err-{MAX_STEP_SUMMARY_ERRORS - 1}", content)
        # The first item past the cap must NOT be rendered as a bullet.
        self.assertNotIn(f"- err-{MAX_STEP_SUMMARY_ERRORS}\n", content)
        self.assertIn(f"...and 5 more", content)


class TestWriteStepSummaryAppend(unittest.TestCase):
    """GITHUB_STEP_SUMMARY is shared across steps; writes must append."""

    def test_appends_to_existing_content(self):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".md") as f:
            f.write("PRIOR STEP OUTPUT\n")
            summary_path = f.name
        self.addCleanup(os.unlink, summary_path)

        with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": summary_path}):
            with redirect_stdout(io.StringIO()):
                emit_summary(status="pass", formula_count=1, error_count=0)

        content = Path(summary_path).read_text(encoding="utf-8")
        self.assertTrue(content.startswith("PRIOR STEP OUTPUT\n"))
        self.assertIn("### Formula drift check", content)


if __name__ == "__main__":
    unittest.main()
