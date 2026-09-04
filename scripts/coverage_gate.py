#!/usr/bin/env python3
"""
Local coverage gate for scripts/validate_formulae.py and the scripts/test_*.py
unittest discovery suite.

Wraps the CI-side invocation from .github/workflows/validate-formulae.yml
(`python3 -u -m unittest discover -v --buffer -s scripts -p 'test_*.py'`)
with coverage measurement and a configurable minimum threshold. Runs
identically locally and in CI — see kubestellar/homebrew-tap#334.

Why this file rather than editing the workflow directly: the quality-lane
GitHub App does not carry the `workflows` permission scope, so any push
that touches `.github/workflows/*.yml` is rejected. Landing this helper
first lets a maintainer wire it into `validate-formulae.yml` with a
one-line workflow change (see #334 comment thread for the exact diff)
without needing the App to gain workflow-scope credentials.

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
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
DEFAULT_THRESHOLD = 95


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
    p.add_argument(
        "--include",
        default="scripts/validate_formulae.py",
        help="Comma-separated glob(s) to include in the coverage report (default: scripts/validate_formulae.py).",
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
    include_args: list[str] = []
    for pattern in include.split(","):
        pattern = pattern.strip()
        if pattern:
            include_args.extend(["--include", pattern])

    report_rc = subprocess.call(
        [
            sys.executable,
            "-m",
            "coverage",
            "report",
            f"--fail-under={threshold}",
            *include_args,
        ],
        cwd=str(REPO_ROOT),
    )
    if want_xml:
        subprocess.call(
            [sys.executable, "-m", "coverage", "xml", "-o", "coverage.xml", *include_args],
            cwd=str(REPO_ROOT),
        )
    if report_rc == 0:
        return 0
    if report_rc == 2:
        return 2
    return report_rc


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if not _import_coverage():
        return 3
    if not SCRIPTS_DIR.is_dir():
        sys.stderr.write(f"coverage_gate: scripts/ not found at {SCRIPTS_DIR}\n")
        return 1

    tests_rc = _run_tests_under_coverage()
    if tests_rc != 0:
        return 1
    return _report(args.min, args.include, args.xml)


if __name__ == "__main__":
    sys.exit(main())
