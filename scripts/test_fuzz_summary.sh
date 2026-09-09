#!/usr/bin/env bash
# test_fuzz_summary.sh — regression tests for scripts/fuzz_summary.sh.
#
# Guards against the summary line silently losing its stdout-only,
# always-emitted contract: success and failure job statuses must each still
# produce exactly one FUZZ_SUMMARY: JSON line with the correct formula
# count, and the script's own exit status must reflect JOB_STATUS so a
# future edit can't reintroduce a "no structured record on failure" gap.
#
# Usage: scripts/test_fuzz_summary.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/fuzz_summary.sh"

fail_count=0
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

mkdir -p "$work_dir/Formula"
printf 'class Foo < Formula\nend\n' > "$work_dir/Formula/foo.rb"
printf 'class Bar < Formula\nend\n' > "$work_dir/Formula/bar.rb"

assert_case() {
  local name="$1" job_status="$2" expected_exit="$3"
  local output exit_code

  output=$(FORMULA_DIR="$work_dir/Formula" JOB_STATUS="$job_status" "$SCRIPT" 2>&1)
  exit_code=$?

  if ! printf '%s' "$output" | grep -q '^FUZZ_SUMMARY: {'; then
    echo "FAIL ($name): missing FUZZ_SUMMARY: line. Got: $output"
    fail_count=$((fail_count + 1))
    return
  fi
  if ! printf '%s' "$output" | grep -q "\"status\":\"$job_status\""; then
    echo "FAIL ($name): expected status=$job_status. Got: $output"
    fail_count=$((fail_count + 1))
    return
  fi
  if ! printf '%s' "$output" | grep -q '"formula_count":2'; then
    echo "FAIL ($name): expected formula_count=2. Got: $output"
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

assert_case "success" "success" 0
assert_case "failure" "failure" 1

# FORMULA_DIR pointing at a nonexistent path must not error under
# `set -uo pipefail`; formula_count should fall back to 0.
output=$(FORMULA_DIR="$work_dir/does-not-exist" JOB_STATUS="success" "$SCRIPT" 2>&1)
exit_code=$?
if printf '%s' "$output" | grep -q '"formula_count":0' && [ "$exit_code" -eq 0 ]; then
  echo "OK (missing-formula-dir)"
else
  echo "FAIL (missing-formula-dir): expected formula_count=0, exit=0. Got: $output (exit=$exit_code)"
  fail_count=$((fail_count + 1))
fi

# The summary line must still appear, with its own distinct "unknown"
# fallback, when JOB_STATUS is unset (never silently omitted).
output=$(FORMULA_DIR="$work_dir/Formula" "$SCRIPT" 2>&1)
exit_code=$?
if printf '%s' "$output" | grep -q '"status":"unknown"' && [ "$exit_code" -eq 1 ]; then
  echo "OK (defaults-when-unset)"
else
  echo "FAIL (defaults-when-unset): expected status=unknown, exit=1. Got: $output (exit=$exit_code)"
  fail_count=$((fail_count + 1))
fi

if [ "$fail_count" -eq 0 ]; then
  echo "All fuzz_summary.sh tests passed."
  exit 0
else
  echo "$fail_count fuzz_summary.sh test(s) failed."
  exit 1
fi
