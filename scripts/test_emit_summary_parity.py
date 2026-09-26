#!/usr/bin/env python3
"""Parity test: the bash and Python owners of the '<PREFIX>: {json}' CI
summary contract must produce byte-identical lines for the same inputs.

scripts/lib_emit_summary.sh (bash, kubestellar/homebrew-tap#577) and
scripts/lib_emit_summary.py (Python, kubestellar/homebrew-tap#581) each
have their own unit tests, but until this module nothing asserted that the
two emitters agreed. Consumers grep `<PREFIX>_SUMMARY:` across CI logs from
both languages and rely on one record shape, so a divergence in key order,
JSON separators, number/null typing, or string escaping must fail here.

Each case feeds the same prefix and ordered (key, value) pairs to:

  - bash:   emit_ci_summary "$prefix" key=value ...  (via a subprocess
            that sources the lib; `key:str=` when the Python value is a
            str that would otherwise look like a number or null),
  - Python: lib_emit_summary.format_summary_line(prefix, fields),

and asserts the stdout line equals the Python string exactly, and that it
parses back to the same JSON object. $GITHUB_STEP_SUMMARY is unset for
the subprocess so only the wire line is compared — the markdown rendering
is allowed to differ per emitter by design.

The generic step-summary table is also checked once: for the same fields,
the Python format_step_summary_table() must match what the bash lib
appends to $GITHUB_STEP_SUMMARY, since callers that use the generic
rendering from either language should get the same checks-UI output.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lib_emit_summary as les  # noqa: E402

BASH_LIB = Path(__file__).parent / "lib_emit_summary.sh"

# (prefix, ordered fields) — one entry per hazard the contract must agree
# on: field order, number vs. string typing, null, escaping, non-ASCII,
# an empty string, a decimal, and floats whose repr() would be scientific
# notation (the bash lib only type-infers fixed-point decimals).
CASES = [
    ("VALIDATE_FORMULAE_SUMMARY", {"status": "pass", "formula_count": 3, "error_count": 0}),
    ("VALIDATE_FORMULAE_SUMMARY", {"status": "fail", "formula_count": 2, "error_count": 1}),
    ("VALIDATE_FORMULAE_SUMMARY", {"status": "error", "formula_count": 0, "error_count": 1}),
    ("BREW_CI_SUMMARY", {"status": "success", "os": "macos-14", "formula_count": 4, "installed_count": 4}),
    ("BREW_AUDIT_SUMMARY", {"status": "fail", "formula_count": 3, "warned_count": 1, "failed_formula": "kc-agent"}),
    ("BREW_AUDIT_SUMMARY", {"status": "pass", "formula_count": 3, "warned_count": 0, "failed_formula": None}),
    ("T", {"forced": "123", "also": "null", "neg": -7, "dec": 2.5, "empty": ""}),
    ("T", {"big": 1e20, "tiny": 1e-7, "mid": 1.5e16, "negbig": -1e20, "negzero": -0.0, "whole": 3.0}),
    ("T", {"k": 'quote" back\\slash', "ctl": "a\tb\nc\rd\be\ff\x01g\x7f", "uni": "héllo ✅"}),
]


def _bash_args(fields: dict) -> list[str]:
    """Translate the Python mapping to the bash lib's key=value argv,
    forcing `:str` when the string value would be type-inferred otherwise."""
    args = []
    for key, value in fields.items():
        if value is None:
            args.append(f"{key}=null")
        elif isinstance(value, str) and (value == "null" or _looks_numeric(value)):
            args.append(f"{key}:str={value}")
        elif isinstance(value, float):
            # A bash caller writes the number positionally (2.5, not 2.5e0);
            # str()/repr() would hand bash "1e+20", which it must quote.
            args.append(f"{key}={les.format_float(value)}")
        else:
            args.append(f"{key}={value}")
    return args


def _looks_numeric(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def _run_bash(prefix: str, fields: dict, step_summary: str | None = None) -> str:
    env = {k: v for k, v in os.environ.items() if k != "GITHUB_STEP_SUMMARY"}
    if step_summary is not None:
        env["GITHUB_STEP_SUMMARY"] = step_summary
    proc = subprocess.run(
        ["bash", "-c", 'source "$1"; shift; emit_ci_summary "$@"', "_", str(BASH_LIB), prefix, *_bash_args(fields)],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return proc.stdout


class TestWireLineParity(unittest.TestCase):
    def test_bash_and_python_lines_are_byte_identical(self):
        for prefix, fields in CASES:
            with self.subTest(prefix=prefix, fields=fields):
                bash_out = _run_bash(prefix, fields)
                py_line = les.format_summary_line(prefix, fields)
                self.assertEqual(bash_out, py_line + "\n")
                self.assertEqual(json.loads(py_line[len(prefix) + 2:]), fields)


class TestStepSummaryTableParity(unittest.TestCase):
    def test_generic_table_matches_bash_lib(self):
        prefix = "BREW_CI_SUMMARY"
        fields = {"status": "success", "os": "mac|os", "formula_count": 4, "failed": None}
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".md") as f:
            path = f.name
        self.addCleanup(os.unlink, path)
        _run_bash(prefix, fields, step_summary=path)
        bash_table = Path(path).read_text(encoding="utf-8")
        py_table = "\n".join(les.format_step_summary_table(prefix, fields)) + "\n"
        self.assertEqual(bash_table, py_table)


if __name__ == "__main__":
    unittest.main()
