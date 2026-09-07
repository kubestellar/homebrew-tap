#!/usr/bin/env bash
# unittest_summary.sh — run `unittest discover` and emit a single-line,
# machine-readable summary of the result, mirroring the
# VALIDATE_FORMULAE_SUMMARY: pattern already emitted by
# scripts/validate_formulae.py and VERIFY_RELEASE_HEALTH_SUMMARY: emitted by
# scripts/verify_release_health.sh.
#
# validate-formulae.yml's "Run all scripts/test_*.py unit tests" step
# currently only runs `python3 -u -m unittest discover -v --buffer -s
# scripts -p 'test_*.py'` directly, so the only pass/fail record in CI logs
# is unittest's own free-text "OK" / "FAILED (failures=N, errors=M)" tail
# line — there is no grep-able, fixed-shape record a reader or future CI
# tool can rely on for the "Formula drift health" SLI tracked in
# docs/slo.md, unlike the drift-check script that already runs in the very
# same job.
#
# This script wraps the same `unittest discover` invocation, preserves its
# full verbose output unchanged (nothing is hidden or summarized away), and
# appends one additional UNITTEST_SUMMARY: JSON line derived from unittest's
# own final "Ran N tests" / "OK"|"FAILED (...)" report. Stdout-only: no
# exporter, metrics backend, or off-box data flow is added.
#
# This is a standalone script, not wired into any workflow here: wiring it
# into validate-formulae.yml requires editing
# .github/workflows/validate-formulae.yml, which needs the `workflows`
# permission this script does not assume. A maintainer can wire it in by
# replacing the step's `run:` line with:
#
#   - name: Run all scripts/test_*.py unit tests
#     run: scripts/unittest_summary.sh
#
# Usage: scripts/unittest_summary.sh [-s discover-dir] [-p pattern]
#   Defaults match validate-formulae.yml: -s scripts -p 'test_*.py'
#
# Exit status: mirrors `unittest discover`'s own exit status (0 pass,
# 1 fail, 5 if the discover pattern matches zero test files).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

start_dir="scripts"
pattern="test_*.py"
while getopts "s:p:" opt; do
  case "$opt" in
    s) start_dir="$OPTARG" ;;
    p) pattern="$OPTARG" ;;
    *) ;;
  esac
done

out_file="$(mktemp)"
trap 'rm -f "$out_file"' EXIT

(cd "$REPO_ROOT" && python3 -u -m unittest discover -v --buffer -s "$start_dir" -p "$pattern") >"$out_file" 2>&1
exit_code=$?

# Print the full, unmodified unittest output so nothing is lost from the CI log.
cat "$out_file"

# unittest's final report is one of:
#   Ran N tests in Xs
#
#   OK
# or, on failure:
#   Ran N tests in Xs
#
#   FAILED (failures=X, errors=Y)
# (either of failures=/errors= may be absent depending on which occurred)
# or, when the pattern matches zero files (e.g. an empty/renamed -s dir):
#   Ran 0 tests in Xs
#
#   NO TESTS RAN
# which unittest itself treats as distinct from "OK" (exit status 5) — a
# silent-skip regression (see #268) should be visible as its own status,
# not folded into "pass".
tests_run="$(grep -oE '^Ran [0-9]+ test' "$out_file" | tail -1 | grep -oE '[0-9]+' || true)"
tests_run="${tests_run:-0}"

if grep -qE '^NO TESTS RAN' "$out_file"; then
  status="no_tests"
  failures=0
  errors=0
elif grep -qE '^OK(\s|$)' "$out_file"; then
  status="pass"
  failures=0
  errors=0
else
  status="fail"
  failed_line="$(grep -E '^FAILED' "$out_file" | tail -1)"
  failures="$(printf '%s' "$failed_line" | grep -oE 'failures=[0-9]+' | grep -oE '[0-9]+' || true)"
  errors="$(printf '%s' "$failed_line" | grep -oE 'errors=[0-9]+' | grep -oE '[0-9]+' || true)"
  failures="${failures:-0}"
  errors="${errors:-0}"
fi

printf 'UNITTEST_SUMMARY: {"status":"%s","tests_run":%s,"failures":%s,"errors":%s}\n' \
  "$status" "$tests_run" "$failures" "$errors"

exit "$exit_code"
