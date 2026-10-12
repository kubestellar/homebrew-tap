#!/usr/bin/env python3
"""
Local coverage gate for the tap's production helper modules
(scripts/validate_formulae.py, scripts/formula_parser.py,
scripts/formula_test_fixtures.py, and scripts/lib_emit_summary.py) and the
scripts/test_*.py unittest
discovery suite.

Wraps the CI-side invocation from .github/workflows/validate-formulae.yml
(`python3 -u -m unittest discover -v --buffer -s scripts -p 'test_*.py'`)
with coverage measurement and a configurable minimum threshold. Runs
identically locally and in CI — see kubestellar/homebrew-tap#334.

Already wired into CI: `.github/workflows/validate-formulae.yml`'s
"Enforce 100% coverage gate" step runs
`python3 scripts/coverage_gate.py --min 100 --report-only` (landed via
#614/#618; the original gap this closed is tracked, closed, in #334).
This module is not an unwired standalone helper awaiting a maintainer
edit — it runs in CI on every push and pull request.

Usage:
    python3 scripts/coverage_gate.py                        # default threshold (95)
    python3 scripts/coverage_gate.py --min 90               # relax threshold
    python3 scripts/coverage_gate.py --min 95 --xml         # also emit coverage.xml
    COVERAGE_MIN=100 python3 scripts/coverage_gate.py       # env-driven override

Exit codes:
    0  — tests passed AND coverage >= threshold
    1  — tests failed
    2  — tests passed but coverage below threshold
    3  — coverage tool not importable (install with: pip install coverage)

Structured output: every exit path prints a bounded, grep-friendly
``COVERAGE_GATE_SUMMARY: {...}`` line (status/threshold/percent_covered)
via the shared scripts/lib_emit_summary.py contract, matching the
``VALIDATE_FORMULAE_SUMMARY:``/``SHELL_COVERAGE_SUMMARY:`` pattern used
elsewhere in this repo. Before this, a reader had to open the raw
``coverage report`` table to tell whether/why this step passed, failed, or
could not run at all — stdout-only; no exporter, metrics backend, or
off-box data flow is added.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from lib_emit_summary import emit_ci_summary

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
DEFAULT_THRESHOLD = 95

# Matches `coverage report`'s final totals row, e.g.:
#   TOTAL                                338      0    126      0   100%
# Captures the trailing percentage so the summary line can carry a real
# number instead of forcing a reader back to the raw table.
_TOTAL_PERCENT_RE = re.compile(r"^TOTAL\s+.*\s(\d+(?:\.\d+)?)%\s*$", re.MULTILINE)


def _parse_total_percent(report_output: str) -> float | None:
    """Extract the aggregate coverage percentage from a `coverage report`
    table, or None if the TOTAL row isn't present (e.g. "No data to
    report.")."""
    match = _TOTAL_PERCENT_RE.search(report_output)
    if match is None:
        return None
    return float(match.group(1))


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run the scripts/test_*.py suite under coverage and enforce a minimum threshold.",
    )
    env_min = os.environ.get("COVERAGE_MIN")
    default_min = int(env_min) if env_min and env_min.strip().isdigit() else DEFAULT_THRESHOLD
    p.add_argument(
        "--min",
        type=int,
        default=default_min,
        help=f"Minimum coverage percentage to require (default: {DEFAULT_THRESHOLD}, or $COVERAGE_MIN).",
    )
    p.add_argument(
        "--xml",
        action="store_true",
        help="Also emit coverage.xml for CI artifact upload.",
    )
    env_report_only = os.environ.get("COVERAGE_GATE_REPORT_ONLY", "")
    default_report_only = env_report_only.strip().lower() in ("1", "true", "yes")
    p.add_argument(
        "--report-only",
        dest="report_only",
        action="store_true",
        default=default_report_only,
        help=(
            "Skip re-running the test suite and report on the existing "
            ".coverage file (also enabled by COVERAGE_GATE_REPORT_ONLY=1). "
            "Use this when a prior step already produced .coverage via "
            "`coverage run -m unittest discover ...` (e.g. "
            "scripts/unittest_summary.sh with COVERAGE_SOURCE=scripts), so "
            "CI does not run the suite twice. See kubestellar/homebrew-tap#612."
        ),
    )
    p.add_argument(
        "--include",
        default=(
            "scripts/validate_formulae.py,"
            "scripts/formula_parser.py,"
            "scripts/formula_test_fixtures.py,"
            "scripts/lib_emit_summary.py,"
            "scripts/coverage_gate.py"
        ),
        help=(
            "Comma-separated glob(s) to include in the coverage report "
            "(default: scripts/validate_formulae.py,"
            "scripts/formula_parser.py,"
            "scripts/formula_test_fixtures.py,scripts/lib_emit_summary.py,"
            "scripts/coverage_gate.py)."
        ),
    )
    return p.parse_args(argv)


def _import_coverage():
    try:
        import coverage  # noqa: F401

        return True
    except ImportError:
        sys.stderr.write(
            "coverage_gate: python 'coverage' package not installed.\n"
            "  Install with:  pip install coverage\n"
        )
        return False


def _run_tests_under_coverage() -> int:
    # Match the CI invocation exactly (unittest discover, buffered, verbose)
    # so that "runs green locally" implies "runs green in CI".
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "coverage",
            "run",
            "--source=scripts",
            "-m",
            "unittest",
            "discover",
            "-v",
            "--buffer",
            "-s",
            "scripts",
            "-p",
            "test_*.py",
        ],
        cwd=str(REPO_ROOT),
    )


def _report(threshold: int, include: str, want_xml: bool) -> int:
    # `coverage report --fail-under=N` returns 2 when coverage < N. We
    # translate that to our own exit code (also 2) for a clean CLI contract.
    #
    # `coverage report` only honors the LAST `--include` flag (later ones
    # silently override earlier ones), so we join the patterns into a
    # single comma-separated value and emit exactly one `--include` arg.
    # See coverage.py CoverageConfig.include semantics — the CLI parser
    # assigns rather than appends.
    patterns = [p.strip() for p in include.split(",") if p.strip()]
    include_args: list[str] = []
    if patterns:
        include_args = ["--include", ",".join(patterns)]

    # Captured (not `subprocess.call`) so the TOTAL row can be parsed for
    # the summary line below; stdout/stderr are still re-emitted verbatim
    # immediately after so the human-readable table is unchanged in CI
    # logs and local runs.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "coverage",
            "report",
            f"--fail-under={threshold}",
            *include_args,
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    report_rc = result.returncode
    percent_covered = _parse_total_percent(result.stdout)

    if want_xml:
        subprocess.call(
            [sys.executable, "-m", "coverage", "xml", "-o", "coverage.xml", *include_args],
            cwd=str(REPO_ROOT),
        )

    status = "pass" if report_rc == 0 else ("fail" if report_rc == 2 else "error")
    emit_ci_summary(
        "COVERAGE_GATE_SUMMARY",
        {"status": status, "threshold": threshold, "percent_covered": percent_covered},
    )

    if report_rc == 0:
        return 0
    if report_rc == 2:
        return 2
    return report_rc


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if not _import_coverage():
        emit_ci_summary(
            "COVERAGE_GATE_SUMMARY",
            {"status": "error", "threshold": args.min, "percent_covered": None},
        )
        return 3
    if not SCRIPTS_DIR.is_dir():
        sys.stderr.write(f"coverage_gate: scripts/ not found at {SCRIPTS_DIR}\n")
        emit_ci_summary(
            "COVERAGE_GATE_SUMMARY",
            {"status": "error", "threshold": args.min, "percent_covered": None},
        )
        return 1

    tests_rc = 0 if args.report_only else _run_tests_under_coverage()
    if tests_rc != 0:
        emit_ci_summary(
            "COVERAGE_GATE_SUMMARY",
            {"status": "fail", "threshold": args.min, "percent_covered": None},
        )
        return 1
    return _report(args.min, args.include, args.xml)


if __name__ == "__main__":
    sys.exit(main())
