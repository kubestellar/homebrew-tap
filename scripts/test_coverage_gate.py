"""
Tests for scripts/coverage_gate.py.

The helper wraps `coverage run -m unittest discover ...` and enforces a
minimum coverage threshold on scripts/validate_formulae.py. These tests
exercise argument parsing, env-var override, threshold defaults, and the
`_import_coverage()` guard — everything except the actual subprocess call
into `coverage run`, which is validated in CI via a dry green run.
"""
from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import redirect_stderr
from unittest import mock

# The helper lives alongside this test file under scripts/.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coverage_gate  # noqa: E402


class ParseArgsTests(unittest.TestCase):
    def setUp(self):
        # Clear COVERAGE_MIN between tests so a stray env var from the
        # host doesn't skew the "default threshold" assertions.
        self._saved_env = os.environ.pop("COVERAGE_MIN", None)

    def tearDown(self):
        if self._saved_env is not None:
            os.environ["COVERAGE_MIN"] = self._saved_env

    def test_default_threshold_matches_module_constant(self):
        args = coverage_gate._parse_args([])
        self.assertEqual(args.min, coverage_gate.DEFAULT_THRESHOLD)
        self.assertEqual(coverage_gate.DEFAULT_THRESHOLD, 95)

    def test_min_flag_overrides_default(self):
        args = coverage_gate._parse_args(["--min", "80"])
        self.assertEqual(args.min, 80)

    def test_env_var_override_when_flag_absent(self):
        os.environ["COVERAGE_MIN"] = "88"
        args = coverage_gate._parse_args([])
        self.assertEqual(args.min, 88)

    def test_flag_beats_env_var(self):
        os.environ["COVERAGE_MIN"] = "88"
        args = coverage_gate._parse_args(["--min", "99"])
        self.assertEqual(args.min, 99)

    def test_env_var_with_whitespace_or_non_digits_falls_back_to_default(self):
        os.environ["COVERAGE_MIN"] = "  not-a-number  "
        args = coverage_gate._parse_args([])
        self.assertEqual(args.min, coverage_gate.DEFAULT_THRESHOLD)

    def test_xml_flag_default_false(self):
        args = coverage_gate._parse_args([])
        self.assertFalse(args.xml)

    def test_xml_flag_toggles_true(self):
        args = coverage_gate._parse_args(["--xml"])
        self.assertTrue(args.xml)

    def test_include_default_targets_validate_formulae(self):
        args = coverage_gate._parse_args([])
        self.assertEqual(args.include, "scripts/validate_formulae.py")

    def test_include_flag_overrides_default(self):
        args = coverage_gate._parse_args(["--include", "scripts/*.py"])
        self.assertEqual(args.include, "scripts/*.py")


class ImportCoverageTests(unittest.TestCase):
    def test_returns_true_when_coverage_importable(self):
        # `coverage` is a dev-time dep of this repo — in CI it's expected
        # to be installed alongside the coverage_gate.py invocation.
        self.assertTrue(coverage_gate._import_coverage())

    def test_returns_false_and_prints_hint_when_missing(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            with mock.patch.dict(sys.modules, {"coverage": None}):
                # `sys.modules[name] = None` makes `import name` raise ImportError.
                result = coverage_gate._import_coverage()
        self.assertFalse(result)
        self.assertIn("pip install coverage", stderr.getvalue())


class MainGuardTests(unittest.TestCase):
    def test_missing_coverage_returns_exit_code_3(self):
        with mock.patch.object(coverage_gate, "_import_coverage", return_value=False):
            self.assertEqual(coverage_gate.main([]), 3)

    def test_missing_scripts_dir_returns_1(self):
        # Point SCRIPTS_DIR at a nonexistent path to exercise the guard
        # without touching the on-disk layout.
        with mock.patch.object(coverage_gate, "SCRIPTS_DIR", coverage_gate.REPO_ROOT / "nope-does-not-exist"):
            with mock.patch.object(coverage_gate, "_import_coverage", return_value=True):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    rc = coverage_gate.main([])
                self.assertEqual(rc, 1)
                self.assertIn("scripts/ not found", stderr.getvalue())

    def test_tests_failure_returns_1_without_reaching_report(self):
        # If `coverage run` exits non-zero (unittest failure), main() must
        # short-circuit to 1 and NOT invoke the report step (which would
        # otherwise mask the failure by returning a coverage-pass code).
        with mock.patch.object(coverage_gate, "_import_coverage", return_value=True), \
             mock.patch.object(coverage_gate, "_run_tests_under_coverage", return_value=1) as run, \
             mock.patch.object(coverage_gate, "_report") as report:
            rc = coverage_gate.main([])
        self.assertEqual(rc, 1)
        self.assertEqual(run.call_count, 1)
        report.assert_not_called()

    def test_tests_pass_delegates_to_report(self):
        with mock.patch.object(coverage_gate, "_import_coverage", return_value=True), \
             mock.patch.object(coverage_gate, "_run_tests_under_coverage", return_value=0), \
             mock.patch.object(coverage_gate, "_report", return_value=0) as report:
            rc = coverage_gate.main(["--min", "90", "--xml"])
        self.assertEqual(rc, 0)
        report.assert_called_once_with(90, "scripts/validate_formulae.py", True)

    def test_coverage_below_threshold_propagates_exit_code_2(self):
        with mock.patch.object(coverage_gate, "_import_coverage", return_value=True), \
             mock.patch.object(coverage_gate, "_run_tests_under_coverage", return_value=0), \
             mock.patch.object(coverage_gate, "_report", return_value=2):
            rc = coverage_gate.main([])
        self.assertEqual(rc, 2)


class ReportTests(unittest.TestCase):
    def test_report_builds_include_args_from_comma_separated_list(self):
        captured: dict = {}

        def fake_call(cmd, cwd=None):
            captured.setdefault("cmds", []).append(cmd)
            return 0

        with mock.patch.object(coverage_gate.subprocess, "call", side_effect=fake_call):
            rc = coverage_gate._report(95, "scripts/a.py, scripts/b.py", want_xml=False)
        self.assertEqual(rc, 0)
        # Only one call (report); xml was False.
        self.assertEqual(len(captured["cmds"]), 1)
        cmd = captured["cmds"][0]
        # Each include glob must be preceded by its own --include flag —
        # coverage.py accepts this form and mis-joining them silently
        # collapses to a single glob that matches nothing.
        includes = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "--include"]
        self.assertEqual(includes, ["scripts/a.py", "scripts/b.py"])
        self.assertIn("--fail-under=95", cmd)

    def test_report_emits_xml_when_requested(self):
        captured: dict = {}

        def fake_call(cmd, cwd=None):
            captured.setdefault("cmds", []).append(cmd)
            return 0

        with mock.patch.object(coverage_gate.subprocess, "call", side_effect=fake_call):
            coverage_gate._report(95, "scripts/x.py", want_xml=True)
        self.assertEqual(len(captured["cmds"]), 2)
        xml_cmd = captured["cmds"][1]
        self.assertIn("xml", xml_cmd)
        self.assertIn("coverage.xml", xml_cmd)

    def test_report_below_threshold_returns_2(self):
        with mock.patch.object(coverage_gate.subprocess, "call", return_value=2):
            self.assertEqual(coverage_gate._report(95, "scripts/x.py", False), 2)

    def test_report_other_nonzero_exit_propagates_as_is(self):
        with mock.patch.object(coverage_gate.subprocess, "call", return_value=7):
            self.assertEqual(coverage_gate._report(95, "scripts/x.py", False), 7)


if __name__ == "__main__":
    unittest.main()
