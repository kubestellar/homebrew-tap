"""
Parity test for the coverage ratchet include list.

The set of production Python modules held to the 100% coverage ratchet is
declared in two places:

  1. `.coveragerc`'s `[run] include =` list — read by every direct
     `coverage run` / `coverage report` invocation the repo makes,
     including the CI step in `.github/workflows/validate-formulae.yml`.
  2. `scripts/coverage_gate.py`'s hard-coded `--include` default — used
     when the gate helper is invoked without an explicit `--include`
     flag (local dev, and any future CI wiring that omits the flag).

If those two lists drift, the local `coverage_gate.py` run and the
CI `.coveragerc`-driven run silently measure different modules. Concretely,
adding `scripts/new_helper.py` to `.coveragerc` but forgetting to update
`coverage_gate.py`'s default (or vice versa) would let a regression in
the missed module slip past whichever runner didn't track it.

This test parses both sources of truth and asserts they list exactly the
same modules — nothing more (unrelated tests already guard the
individual thresholds and behavior of `coverage_gate.py`).
"""
from __future__ import annotations

import ast
import configparser
import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COVERAGERC_PATH = REPO_ROOT / ".coveragerc"
COVERAGE_GATE_PATH = REPO_ROOT / "scripts" / "coverage_gate.py"


def _coveragerc_include() -> list[str]:
    """Return the `[run] include =` list from .coveragerc, sorted."""
    parser = configparser.ConfigParser()
    with COVERAGERC_PATH.open(encoding="utf-8") as f:
        parser.read_file(f)
    raw = parser["run"]["include"]
    entries = [line.strip() for line in raw.strip().splitlines() if line.strip()]
    return sorted(entries)


def _coverage_gate_default_include() -> list[str]:
    """Return the `--include` argparse default from coverage_gate.py, sorted.

    Uses AST parsing (not import + argparse.parse_args) so the assertion
    fails on the raw declaration in source — the exact string a
    maintainer would edit — rather than on a post-parse computed value
    that could be identical for two different declarations.
    """
    source = COVERAGE_GATE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "attr", None) != "add_argument":
            continue
        # Positional arg 0 must be the "--include" flag name.
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        if node.args[0].value != "--include":
            continue
        for kw in node.keywords:
            if kw.arg == "default":
                value = ast.literal_eval(kw.value)
                entries = [p.strip() for p in value.split(",") if p.strip()]
                return sorted(entries)
        raise AssertionError(
            "coverage_gate.py: --include add_argument call has no `default=` kwarg"
        )
    raise AssertionError(
        "coverage_gate.py: no add_argument('--include', ...) call found"
    )


class CoverageIncludeParityTests(unittest.TestCase):
    def test_coveragerc_and_coverage_gate_include_match(self):
        rc = _coveragerc_include()
        gate = _coverage_gate_default_include()
        self.assertEqual(
            rc,
            gate,
            msg=(
                "The ratchet include list has drifted between .coveragerc "
                "[run] include and scripts/coverage_gate.py's --include "
                "default. Update BOTH so local `python3 scripts/coverage_gate.py` "
                "and CI's `.coveragerc`-driven run measure the same modules.\n"
                f"  .coveragerc:       {rc}\n"
                f"  coverage_gate.py:  {gate}"
            ),
        )

    def test_include_list_is_non_empty(self):
        # A silently-emptied list would let both sources agree while
        # measuring zero modules — coverage would trivially pass at 100%.
        self.assertGreater(len(_coveragerc_include()), 0)
        self.assertGreater(len(_coverage_gate_default_include()), 0)

    def test_every_included_file_actually_exists(self):
        # Guards against a typo like `scripts/coverate_gate.py` that would
        # be silently ignored by coverage.py's glob (no matched files → no
        # measurement), letting a regression in the misspelled module slip
        # past the 100% ratchet.
        for path in _coveragerc_include():
            self.assertTrue(
                (REPO_ROOT / path).is_file(),
                msg=f".coveragerc lists missing file: {path}",
            )
        for path in _coverage_gate_default_include():
            self.assertTrue(
                (REPO_ROOT / path).is_file(),
                msg=f"coverage_gate.py --include default lists missing file: {path}",
            )


if __name__ == "__main__":
    unittest.main()
