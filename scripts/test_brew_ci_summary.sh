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

# shellcheck source=scripts/test_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test_lib.sh"

REPO_ROOT="$(repo_root)"
SCRIPT="$REPO_ROOT/scripts/brew_ci_summary.sh"

make_work_dir
make_fake_formulae "$work_dir/Formula" foo bar

assert_case() {
  local name="$1" job_status="$2" matrix_os="$3" installed="$4" expected_exit="$5" expected_installed_count="$6"
  local output exit_code

  output=$(FORMULA_DIR="$work_dir/Formula" JOB_STATUS="$job_status" MATRIX_OS="$matrix_os" \
    INSTALLED_FORMULAE="$installed" "$SCRIPT" 2>&1)
  exit_code=$?

  assert_grep "$name" "$output" '^BREW_CI_SUMMARY: {' "missing BREW_CI_SUMMARY: line. Got: $output" || return
  assert_grep "$name" "$output" "\"status\":\"$job_status\"" "expected status=$job_status. Got: $output" || return
  assert_grep "$name" "$output" "\"os\":\"$matrix_os\"" "expected os=$matrix_os. Got: $output" || return
  assert_grep "$name" "$output" '"formula_count":2' "expected formula_count=2. Got: $output" || return
  assert_grep "$name" "$output" "\"installed_count\":$expected_installed_count" \
    "expected installed_count=$expected_installed_count. Got: $output" || return
  assert_exit "$name" "$exit_code" "$expected_exit" "expected exit=$expected_exit, got exit=$exit_code" || return
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

finish "brew_ci_summary.sh"
