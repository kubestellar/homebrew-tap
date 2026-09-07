#!/usr/bin/env bash
# test_fuzz_summary.sh — regression tests for scripts/fuzz_summary.sh.
#
# Guards against the summary line silently losing its stdout-only,
# always-emitted contract: every combination of step outcomes must produce
# a single FUZZ_SUMMARY: JSON line, and the exit status must reflect
# overall pass/fail so a future edit can't reintroduce the "skipped on
# failure" gap this script was written to close.
#
# Usage: scripts/test_fuzz_summary.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/fuzz_summary.sh"

fail_count=0

assert_case() {
  local name="$1" syntax="$2" structure="$3" url_checksum="$4" expected_status="$5" expected_exit="$6"
  local output exit_code
  output=$(SYNTAX_OUTCOME="$syntax" STRUCTURE_OUTCOME="$structure" URL_CHECKSUM_OUTCOME="$url_checksum" "$SCRIPT" 2>&1)
  exit_code=$?

  if ! printf '%s' "$output" | grep -q '^FUZZ_SUMMARY: {'; then
    echo "FAIL ($name): missing FUZZ_SUMMARY: line. Got: $output"
    fail_count=$((fail_count + 1))
    return
  fi
  if ! printf '%s' "$output" | grep -q "\"status\":\"$expected_status\""; then
    echo "FAIL ($name): expected status=$expected_status. Got: $output"
    fail_count=$((fail_count + 1))
    return
  fi
  if [ "$exit_code" -ne "$expected_exit" ]; then
    echo "FAIL ($name): expected exit=$expected_exit, got exit=$exit_code"
    fail_count=$((fail_count + 1))
    return
  fi
  echo "OK ($name)"
}

assert_case "all-success" success success success success 0
assert_case "syntax-failed" failure success success failure 1
assert_case "structure-failed" success failure success failure 1
assert_case "url-checksum-failed" success success failure failure 1
assert_case "all-failed" failure failure failure failure 1

if [ "$fail_count" -gt 0 ]; then
  echo "test_fuzz_summary.sh: $fail_count assertion(s) failed"
  exit 1
fi
echo "test_fuzz_summary.sh: all assertions passed"
