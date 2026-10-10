#!/usr/bin/env bash
# test_actionlint_summary.sh — regression tests for
# scripts/actionlint_summary.sh.
#
# Guards against the summary line silently losing its stdout-only,
# always-emitted contract: success and failure job statuses must each
# still produce exactly one ACTIONLINT_SUMMARY: JSON line with the
# correct job label and file count for both the "actionlint" and
# "shellcheck" job names, and the script's own exit status must reflect
# JOB_STATUS so a future edit can't reintroduce a "no structured record
# on failure" gap.
#
# Usage: scripts/test_actionlint_summary.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

# shellcheck source=scripts/test_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test_lib.sh"

REPO_ROOT="$(repo_root)"
SCRIPT="$REPO_ROOT/scripts/actionlint_summary.sh"

make_work_dir
mkdir -p "$work_dir/workflows" "$work_dir/scripts"
printf 'name: a\n' > "$work_dir/workflows/one.yml"
printf 'name: b\n' > "$work_dir/workflows/two.yml"
printf '#!/usr/bin/env bash\n' > "$work_dir/scripts/foo.sh"

assert_case() {
  local name="$1" job_name="$2" job_status="$3" expected_count="$4" expected_exit="$5"
  local output exit_code

  output=$(
    WORKFLOWS_DIR="$work_dir/workflows" SCRIPTS_DIR="$work_dir/scripts" \
      JOB_NAME="$job_name" JOB_STATUS="$job_status" "$SCRIPT" 2>&1
  )
  exit_code=$?

  assert_grep "$name" "$output" '^ACTIONLINT_SUMMARY: {' "missing ACTIONLINT_SUMMARY: line. Got: $output" || return
  assert_grep "$name" "$output" "\"status\":\"$job_status\"" "expected status=$job_status. Got: $output" || return
  assert_grep "$name" "$output" "\"job\":\"$job_name\"" "expected job=$job_name. Got: $output" || return
  assert_grep "$name" "$output" "\"file_count\":$expected_count" "expected file_count=$expected_count. Got: $output" || return
  assert_exit_code "$name" "$expected_exit" "$exit_code" "expected exit=$expected_exit, got exit=$exit_code" || return
  echo "OK ($name)"
}

assert_case "actionlint-success" "actionlint" "success" 2 0
assert_case "actionlint-failure" "actionlint" "failure" 2 1
assert_case "shellcheck-success" "shellcheck" "success" 1 0
assert_case "shellcheck-failure" "shellcheck" "failure" 1 1

# An unrecognized JOB_NAME must not error under `set -uo pipefail`;
# file_count should fall back to 0 rather than silently counting either
# directory.
output=$(
  WORKFLOWS_DIR="$work_dir/workflows" SCRIPTS_DIR="$work_dir/scripts" \
    JOB_NAME="bogus" JOB_STATUS="success" "$SCRIPT" 2>&1
)
exit_code=$?
if printf '%s' "$output" | grep -q '"file_count":0' && [ "$exit_code" -eq 0 ]; then
  echo "OK (unknown-job-name)"
else
  echo "FAIL (unknown-job-name): expected file_count=0, exit=0. Got: $output (exit=$exit_code)"
  fail_count=$((fail_count + 1))
fi

# The summary line must still appear, with its own distinct "unknown"
# fallbacks, when JOB_STATUS/JOB_NAME are unset (never silently omitted).
output=$(WORKFLOWS_DIR="$work_dir/workflows" SCRIPTS_DIR="$work_dir/scripts" "$SCRIPT" 2>&1)
exit_code=$?
if printf '%s' "$output" | grep -q '"status":"unknown"' \
  && printf '%s' "$output" | grep -q '"job":"unknown"' \
  && [ "$exit_code" -eq 1 ]; then
  echo "OK (defaults-when-unset)"
else
  echo "FAIL (defaults-when-unset): expected status=unknown, job=unknown, exit=1. Got: $output (exit=$exit_code)"
  fail_count=$((fail_count + 1))
fi

finish "actionlint_summary.sh"
