#!/usr/bin/env bash
# test_brew_ci_summary.sh — regression tests for scripts/brew_ci_summary.sh.
#
# Guards against the summary line silently losing its stdout-only,
# always-emitted contract: success and failure job statuses must each still
# produce exactly one BREW_CI_SUMMARY: JSON line with the correct counts,
# and the script's own exit status must reflect JOB_STATUS so a future edit
# can't reintroduce a "no structured record on failure" gap.
#
# Usage: scripts/test_brew_ci_summary.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/brew_ci_summary.sh"

fail_count=0
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

mkdir -p "$work_dir/Formula"
printf 'class Foo < Formula\nend\n' > "$work_dir/Formula/foo.rb"
printf 'class Bar < Formula\nend\n' > "$work_dir/Formula/bar.rb"

assert_case() {
  local name="$1" job_status="$2" matrix_os="$3" installed="$4" expected_exit="$5" expected_installed_count="$6"
  local output exit_code

  output=$(FORMULA_DIR="$work_dir/Formula" JOB_STATUS="$job_status" MATRIX_OS="$matrix_os" \
    INSTALLED_FORMULAE="$installed" "$SCRIPT" 2>&1)
  exit_code=$?

  if ! printf '%s' "$output" | grep -q '^BREW_CI_SUMMARY: {'; then
    echo "FAIL ($name): missing BREW_CI_SUMMARY: line. Got: $output"
    fail_count=$((fail_count + 1))
    return
  fi
  if ! printf '%s' "$output" | grep -q "\"status\":\"$job_status\""; then
    echo "FAIL ($name): expected status=$job_status. Got: $output"
    fail_count=$((fail_count + 1))
    return
  fi
  if ! printf '%s' "$output" | grep -q "\"os\":\"$matrix_os\""; then
    echo "FAIL ($name): expected os=$matrix_os. Got: $output"
    fail_count=$((fail_count + 1))
    return
  fi
  if ! printf '%s' "$output" | grep -q '"formula_count":2'; then
    echo "FAIL ($name): expected formula_count=2. Got: $output"
    fail_count=$((fail_count + 1))
    return
  fi
  if ! printf '%s' "$output" | grep -q "\"installed_count\":$expected_installed_count"; then
    echo "FAIL ($name): expected installed_count=$expected_installed_count. Got: $output"
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

assert_case "success-both-installed" "success" "ubuntu-latest" "$(printf 'foo\nbar')" 0 2
assert_case "success-one-installed" "success" "macos-latest" "foo" 0 1
assert_case "failure-none-installed" "failure" "ubuntu-latest" "" 1 0

# The summary line must still appear, with its own distinct "unknown"
# fallback, when JOB_STATUS/MATRIX_OS are unset (never silently omitted).
output=$(FORMULA_DIR="$work_dir/Formula" INSTALLED_FORMULAE="" "$SCRIPT" 2>&1)
exit_code=$?
if printf '%s' "$output" | grep -q '"status":"unknown".*"os":"unknown"' && [ "$exit_code" -eq 1 ]; then
  echo "OK (defaults-when-unset)"
else
  echo "FAIL (defaults-when-unset): expected status=unknown, os=unknown, exit=1. Got: $output (exit=$exit_code)"
  fail_count=$((fail_count + 1))
fi

if [ "$fail_count" -eq 0 ]; then
  echo "All brew_ci_summary.sh tests passed."
  exit 0
else
  echo "$fail_count brew_ci_summary.sh test(s) failed."
  exit 1
fi
