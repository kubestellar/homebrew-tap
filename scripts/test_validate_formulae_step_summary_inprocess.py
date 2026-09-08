#!/usr/bin/env python3
"""In-process unit tests for `_write_step_summary` and `emit_summary` in
scripts/validate_formulae.py.

The sibling test file test_validate_formulae_step_summary.py exercises the
same code path end-to-end via `subprocess.run(...)`, which is the right
integration test but is invisible to `coverage.py` when it's tracking the
parent process only — the step-summary function body then shows up as an
uncovered block (validate_formulae.py lines 124-146) even though every
behavior is verified.

These tests import the helpers directly and drive each branch in-process
so that (a) the coverage report reflects reality and (b) any future
`coverage --fail-under` gate on the drift script can be raised safely
without a bogus regression.

No production code is changed by this file.
"""

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


def _load_module():
    """Load validate_formulae.py as a module without executing __main__."""
    script = Path(__file__).parent / "validate_formulae.py"
    spec = importlib.util.spec_from_file_location("validate_formulae", script)
    module = importlib.util.module_from_spec(spec)
    # Register so dataclasses / type hints resolve if ever added.
    sys.modules["validate_formulae"] = module
    spec.loader.exec_module(module)
    return module


VF = _load_module()


class _EnvGuard:
    """Restore GITHUB_STEP_SUMMARY exactly, whether it was set or not."""

    def __init__(self, value):
        self.value = value
        self._had = None
        self._prev = None

    def __enter__(self):
        self._had = "GITHUB_STEP_SUMMARY" in os.environ
        self._prev = os.environ.get("GITHUB_STEP_SUMMARY")
        if self.value is None:
            os.environ.pop("GITHUB_STEP_SUMMARY", None)
        else:
            os.environ["GITHUB_STEP_SUMMARY"] = self.value
        return self

    def __exit__(self, *exc):
        if self._had:
            os.environ["GITHUB_STEP_SUMMARY"] = self._prev
        else:
            os.environ.pop("GITHUB_STEP_SUMMARY", None)


class TestWriteStepSummaryNoEnv(unittest.TestCase):
    def test_no_env_var_is_a_no_op(self):
        # Covers the early-return branch at validate_formulae.py:121-122
        # (summary_path falsy → function returns without touching disk).
        with _EnvGuard(None):
            # Must not raise even though nothing else is set up.
            VF._write_step_summary("pass", 1, 0, [])

    def test_empty_env_var_is_a_no_op(self):
        # `os.environ.get(...) or None` semantics: an empty string counts
        # as "not set" for our purposes and must not write anywhere.
        with _EnvGuard(""):
            VF._write_step_summary("pass", 1, 0, [])


class TestWriteStepSummaryPass(unittest.TestCase):
    def test_pass_no_errors_omits_details_block(self):
        with tempfile.TemporaryDirectory() as d:
            summary = Path(d) / "summary.md"
            summary.write_text("")
            with _EnvGuard(str(summary)):
                VF._write_step_summary("pass", 3, 0, [])
            content = summary.read_text()
        self.assertIn("### Formula drift check", content)
        self.assertIn("| ✅ pass | 3 | 0 |", content)
        self.assertNotIn("<details>", content)
        self.assertNotIn("Error details", content)

    def test_append_not_truncate(self):
        # $GITHUB_STEP_SUMMARY is append-only across steps; prior content
        # written by earlier steps must survive our append.
        with tempfile.TemporaryDirectory() as d:
            summary = Path(d) / "summary.md"
            summary.write_text("### Prior step\n")
            with _EnvGuard(str(summary)):
                VF._write_step_summary("pass", 1, 0, [])
            content = summary.read_text()
        self.assertTrue(content.startswith("### Prior step\n"))
        self.assertIn("### Formula drift check", content)


class TestWriteStepSummaryFail(unittest.TestCase):
    def test_fail_with_errors_renders_details(self):
        errors = ["kubestellar-ops.rb: malformed sha256 'xyz'"]
        with tempfile.TemporaryDirectory() as d:
            summary = Path(d) / "summary.md"
            summary.write_text("")
            with _EnvGuard(str(summary)):
                VF._write_step_summary("fail", 2, 1, errors)
            content = summary.read_text()
        self.assertIn("| ❌ fail | 2 | 1 |", content)
        self.assertIn("<details><summary>Error details</summary>", content)
        self.assertIn("- kubestellar-ops.rb: malformed sha256 'xyz'", content)
        self.assertIn("</details>", content)
        # No overflow line when errors <= cap.
        self.assertNotIn("more (see step log)", content)

    def test_errors_capped_by_max_step_summary_errors(self):
        # Drive the `len(errors) > len(shown)` branch: request one more
        # error than MAX_STEP_SUMMARY_ERRORS and verify the overflow tail.
        cap = VF.MAX_STEP_SUMMARY_ERRORS
        errors = [f"err-{i}" for i in range(cap + 3)]
        with tempfile.TemporaryDirectory() as d:
            summary = Path(d) / "summary.md"
            summary.write_text("")
            with _EnvGuard(str(summary)):
                VF._write_step_summary("fail", cap + 3, cap + 3, errors)
            content = summary.read_text()
        self.assertIn(f"- err-{cap - 1}", content)  # last shown
        self.assertNotIn(f"- err-{cap}", content)   # first hidden
        self.assertIn(f"...and 3 more (see step log)", content)

    def test_exact_cap_boundary_has_no_overflow_line(self):
        # Boundary case: exactly MAX_STEP_SUMMARY_ERRORS errors → all
        # rendered, no "more" line. Guards against an off-by-one in the
        # `len(errors) > len(shown)` check.
        cap = VF.MAX_STEP_SUMMARY_ERRORS
        errors = [f"err-{i}" for i in range(cap)]
        with tempfile.TemporaryDirectory() as d:
            summary = Path(d) / "summary.md"
            summary.write_text("")
            with _EnvGuard(str(summary)):
                VF._write_step_summary("fail", cap, cap, errors)
            content = summary.read_text()
        self.assertIn(f"- err-{cap - 1}", content)
        self.assertNotIn("more (see step log)", content)


class TestEmitSummary(unittest.TestCase):
    def test_emit_summary_prints_json_line_with_prefix(self):
        # emit_summary() writes both stdout (structured) and the step
        # summary file; here we only assert the stdout contract, which
        # CI grep tooling depends on.
        buf = io.StringIO()
        with _EnvGuard(None), redirect_stdout(buf):
            VF.emit_summary(status="pass", formula_count=5, error_count=0)
        out = buf.getvalue().strip().splitlines()
        self.assertEqual(len(out), 1)
        line = out[0]
        self.assertTrue(line.startswith(VF.SUMMARY_PREFIX + " "))
        payload = json.loads(line[len(VF.SUMMARY_PREFIX) + 1:])
        self.assertEqual(
            payload,
            {"status": "pass", "formula_count": 5, "error_count": 0},
        )

    def test_emit_summary_writes_step_summary_when_env_set(self):
        with tempfile.TemporaryDirectory() as d:
            summary = Path(d) / "summary.md"
            summary.write_text("")
            buf = io.StringIO()
            with _EnvGuard(str(summary)), redirect_stdout(buf):
                VF.emit_summary(
                    status="fail",
                    formula_count=1,
                    error_count=1,
                    errors=["boom"],
                )
            content = summary.read_text()
        self.assertIn("| ❌ fail | 1 | 1 |", content)
        self.assertIn("- boom", content)

    def test_emit_summary_default_errors_arg_is_empty_list(self):
        # Regression guard for the `errors or []` fallback: passing no
        # errors kwarg on a pass path must not render a details block.
        with tempfile.TemporaryDirectory() as d:
            summary = Path(d) / "summary.md"
            summary.write_text("")
            with _EnvGuard(str(summary)), redirect_stdout(io.StringIO()):
                VF.emit_summary(status="pass", formula_count=2, error_count=0)
            content = summary.read_text()
        self.assertNotIn("<details>", content)


if __name__ == "__main__":
    unittest.main()
