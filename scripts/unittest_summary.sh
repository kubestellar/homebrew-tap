#!/usr/bin/env bash
# unittest_summary.sh — run the same `unittest discover` invocation used by
# validate-formulae.yml's "Run all scripts/test_*.py unit tests" step,
# unchanged, and append a single machine-readable summary line, mirroring
# the VALIDATE_FORMULAE_SUMMARY: pattern in validate_formulae.py,
# VERIFY_RELEASE_HEALTH_SUMMARY: in verify_release_health.sh, BREW_CI_SUMMARY:
# in brew_ci_summary.sh, and FUZZ_SUMMARY: in fuzz_summary.sh.
#
# validate-formulae.yml's unit-test step today has no grep-able, fixed-shape
# outcome record — only unittest's own free-text "OK" / "FAILED
# (failures=N, errors=M)" tail line, which also silently folds the distinct
# "no tests ran" outcome (unittest exit code 5) into an undifferentiated
# non-zero exit, the same silent-skip failure class as #268.
#
# This is a standalone script, not wired into any workflow here: wiring it
# into validate-formulae.yml requires editing
# .github/workflows/validate-formulae.yml, which needs the `workflows`
# permission this script does not assume. See
# runbooks/proposed-validate-formulae-unittest-summary-step.yml for the
# ready-to-apply step a maintainer with that permission can add.
#
# Stdout-only structured output: no exporter, metrics backend, or off-box
# data flow is added, and labels are bounded (status/counts only). Full
# unittest verbose output is preserved unchanged ahead of the summary line.
#
# Usage: scripts/unittest_summary.sh
#   Optional:
#     SCRIPTS_DIR - override the scripts/ directory searched for
#                   test_*.py files (used by tests).
#
# Exit status: 0 if the summary status is "pass", 1 otherwise (matching
# unittest's own convention that "no tests ran" is not a pass).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS_DIR="${SCRIPTS_DIR:-$REPO_ROOT/scripts}"

output_file="$(mktemp)"
trap 'rm -f "$output_file"' EXIT

python3 -u -m unittest discover -v --buffer -s "$SCRIPTS_DIR" -p 'test_*.py' 2>&1 | tee "$output_file"
unittest_exit=${PIPESTATUS[0]}

tests_run=0
failures=0
errors=0

# unittest's own summary tail line is one of:
#   Ran N test(s) in X.YYYs
#   OK
#   FAILED (failures=N)
#   FAILED (failures=N, errors=M)
#   NO TESTS RAN
ran_line="$(grep -E '^Ran [0-9]+ tests? in ' "$output_file" | tail -1 || true)"
if [ -n "$ran_line" ]; then
  tests_run="$(printf '%s' "$ran_line" | sed -E 's/^Ran ([0-9]+) tests? in .*/\1/')"
fi

failed_line="$(grep -E '^FAILED \(' "$output_file" | tail -1 || true)"
if [ -n "$failed_line" ]; then
  failures="$(printf '%s' "$failed_line" | sed -n 's/.*failures=\([0-9]\+\).*/\1/p')"
  errors="$(printf '%s' "$failed_line" | sed -n 's/.*errors=\([0-9]\+\).*/\1/p')"
  [ -n "$failures" ] || failures=0
  [ -n "$errors" ] || errors=0
fi

status="pass"
if grep -qE '^NO TESTS RAN' "$output_file" || [ "$unittest_exit" -eq 5 ]; then
  status="no_tests"
elif [ "$unittest_exit" -ne 0 ]; then
  status="fail"
fi

printf 'UNITTEST_SUMMARY: {"status":"%s","tests_run":%s,"failures":%s,"errors":%s}\n' \
  "$status" "$tests_run" "$failures" "$errors"

if [ "$status" = "pass" ]; then
  exit 0
fi
exit 1
