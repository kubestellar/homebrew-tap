#!/usr/bin/env python3
"""Unit tests for scripts/lib_emit_summary.py, the Python owner of the
'<PREFIX>: {json}' CI summary contract (kubestellar/homebrew-tap#581).

The sibling scripts/test_lib_emit_summary.sh owns the same invariants for
the bash lib; scripts/test_emit_summary_parity.py asserts the two agree.
This module covers the Python side in-process so .coveragerc's 100%
ratchet sees every branch:

  1. field order follows insertion order (never sorted), compact JSON;
  2. type rendering — int/float -> number, None -> null, str -> escaped
     string; bool and containers are rejected with TypeError;
  3. escaping of `"`, `\\`, short-escape control characters, other
     control characters (including DEL) as \\u00XX, and non-ASCII
     passthrough;
  4. empty prefix / empty key are rejected with ValueError;
  5. every emitted line round-trips through json.loads;
  6. emit_summary_line prints to stdout by default or to a given stream;
  7. $GITHUB_STEP_SUMMARY: unset or empty -> no-op; otherwise the generic
     table (heading, header row, value row, ✅/❌ on status, `|`
     escaped) is APPENDED; an empty field mapping renders only the
     heading.
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
import lib_emit_summary as les  # noqa: E402


class TestFormatSummaryLine(unittest.TestCase):
    def test_insertion_order_and_compact_json(self):
        line = les.format_summary_line(
            "T_SUMMARY", {"status": "pass", "b": 2, "a": 1}
        )
        self.assertEqual(line, 'T_SUMMARY: {"status":"pass","b":2,"a":1}')

    def test_types_number_null_string_float(self):
        line = les.format_summary_line(
            "T", {"n": -3, "f": 2.5, "z": None, "s": "12", "e": ""}
        )
        self.assertEqual(line, 'T: {"n":-3,"f":2.5,"z":null,"s":"12","e":""}')
        self.assertEqual(
            json.loads(line[len("T: "):]),
            {"n": -3, "f": 2.5, "z": None, "s": "12", "e": ""},
        )

    def test_float_never_uses_scientific_notation(self):
        # repr() would give 1e+20 / 1e-07 / 1.5e+16; the bash lib only
        # type-infers fixed-point decimals, so those must be expanded.
        cases = {
            1e20: "100000000000000000000.0",
            -1e20: "-100000000000000000000.0",
            1e-7: "0.0000001",
            1.5e16: "15000000000000000.0",
            2.5: "2.5",
            -0.0: "-0.0",
            0.1: "0.1",
            123456789.123: "123456789.123",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                rendered = les.json_value(value)
                self.assertEqual(rendered, expected)
                self.assertEqual(float(rendered), value)
                self.assertRegex(rendered, r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$")

    def test_non_finite_float_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    les.json_value(value)
                with self.assertRaises(ValueError):
                    les.format_summary_line("T", {"f": value})

    def test_empty_fields_render_empty_object(self):
        self.assertEqual(les.format_summary_line("T", {}), "T: {}")

    def test_escaping_matches_bash_lib(self):
        value = 'q"b\\n\nr\rt\tb\bf\f' + "\x01" + "\x7f" + "é"
        line = les.format_summary_line("T", {"k": value})
        self.assertEqual(
            line,
            'T: {"k":"q\\"b\\\\n\\nr\\rt\\tb\\bf\\f\\u0001\\u007fé"}',
        )
        self.assertEqual(json.loads(line[len("T: "):]), {"k": value})

    def test_key_is_escaped(self):
        line = les.format_summary_line("T", {'we"ird': 1})
        self.assertEqual(line, 'T: {"we\\"ird":1}')
        self.assertEqual(json.loads(line[len("T: "):]), {'we"ird': 1})

    def test_bool_rejected(self):
        with self.assertRaises(TypeError):
            les.format_summary_line("T", {"k": True})

    def test_container_rejected(self):
        with self.assertRaises(TypeError):
            les.format_summary_line("T", {"k": {"nested": 1}})

    def test_empty_prefix_rejected(self):
        with self.assertRaises(ValueError):
            les.format_summary_line("", {"k": 1})

    def test_empty_key_rejected(self):
        with self.assertRaises(ValueError):
            les.format_summary_line("T", {"": 1})


class TestEmitSummaryLine(unittest.TestCase):
    def test_prints_to_stdout_by_default_and_returns_line(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            line = les.emit_summary_line("T", {"status": "pass"})
        self.assertEqual(buf.getvalue(), 'T: {"status":"pass"}\n')
        self.assertEqual(line, 'T: {"status":"pass"}')

    def test_prints_to_given_stream(self):
        buf = io.StringIO()
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            les.emit_summary_line("T", {"status": "fail"}, stream=buf)
        self.assertEqual(buf.getvalue(), 'T: {"status":"fail"}\n')
        self.assertEqual(stdout.getvalue(), "")


class TestHelpers(unittest.TestCase):
    def test_humanize(self):
        self.assertEqual(les.humanize("BREW_CI_SUMMARY"), "Brew ci summary")
        self.assertEqual(les.humanize("formula_count"), "Formula count")
        self.assertEqual(les.humanize(""), "")

    def test_status_cell(self):
        self.assertEqual(les.status_cell("pass"), "✅ pass")
        self.assertEqual(les.status_cell("success"), "✅ success")
        self.assertEqual(les.status_cell("fail"), "❌ fail")
        self.assertEqual(les.status_cell("error"), "❌ error")


class TestStepSummary(unittest.TestCase):
    def _tmp(self, initial: str = "") -> str:
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".md") as f:
            f.write(initial)
            path = f.name
        self.addCleanup(os.unlink, path)
        return path

    def test_unset_env_is_noop(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GITHUB_STEP_SUMMARY", None)
            self.assertIsNone(les.step_summary_path())
            self.assertFalse(les.append_step_summary(["x"]))

    def test_empty_env_is_noop(self):
        with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": ""}):
            self.assertIsNone(les.step_summary_path())
            self.assertFalse(les.append_step_summary(["x"]))

    def test_append_preserves_prior_content(self):
        path = self._tmp("PRIOR\n")
        with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": path}):
            self.assertTrue(les.append_step_summary(["a", "b"]))
        self.assertEqual(Path(path).read_text(encoding="utf-8"), "PRIOR\na\nb\n")

    def test_format_table_shape_matches_bash_lib(self):
        lines = les.format_step_summary_table(
            "BREW_CI_SUMMARY",
            {"status": "pass", "os": "mac|os", "formula_count": 3, "x": None},
        )
        self.assertEqual(
            lines,
            [
                "### Brew ci summary",
                "",
                "| Status | Os | Formula count | X |",
                "|--------|--------|--------|--------|",
                "| ✅ pass | mac\\|os | 3 | null |",
                "",
            ],
        )

    def test_format_table_fail_icon(self):
        lines = les.format_step_summary_table("T", {"status": "fail"})
        self.assertIn("| ❌ fail |", lines)

    def test_format_table_empty_fields_heading_only(self):
        self.assertEqual(les.format_step_summary_table("T_X", {}), ["### T x", "", ""])

    def test_emit_ci_summary_prints_and_appends_table(self):
        path = self._tmp()
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": path}):
            with redirect_stdout(buf):
                line = les.emit_ci_summary("T", {"status": "pass", "n": 1})
        self.assertEqual(line, 'T: {"status":"pass","n":1}')
        self.assertEqual(buf.getvalue(), line + "\n")
        content = Path(path).read_text(encoding="utf-8")
        self.assertEqual(
            content,
            "### T\n\n| Status | N |\n|--------|--------|\n| ✅ pass | 1 |\n\n",
        )

    def test_emit_ci_summary_without_env_only_prints(self):
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GITHUB_STEP_SUMMARY", None)
            with redirect_stdout(buf):
                les.emit_ci_summary("T", {"status": "fail"}, stream=buf)
        self.assertEqual(buf.getvalue(), 'T: {"status":"fail"}\n')


if __name__ == "__main__":
    unittest.main()
