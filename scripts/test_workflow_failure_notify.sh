#!/usr/bin/env bash
# test_workflow_failure_notify.sh — regression tests for
# scripts/workflow_failure_notify.sh.
#
# Guards the markdown-rendering contract used by
# runbooks/proposed-scheduled-workflow-failure-issue.yml: both modes must
# include the workflow name, run link, and timestamp, the issue-body mode
# must always render the detail table plus the file row, and the optional
# "Failed jobs" row must appear only when FAILED_JOBS is non-empty in
# either mode. Also guards the exit-1 contract for a missing mode or a
# missing required env var, so a future edit can't silently start
# rendering a blank/wrong body during a real scheduled-workflow failure.
#
# Usage: scripts/test_workflow_failure_notify.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/workflow_failure_notify.sh"

fail_count=0

assert_contains() {
  local name="$1" haystack="$2" needle="$3"
  if ! printf '%s' "$haystack" | grep -qF "$needle"; then
    echo "FAIL ($name): expected output to contain: $needle"
    echo "--- output ---"
    printf '%s\n' "$haystack"
    echo "--------------"
    fail_count=$((fail_count + 1))
  fi
}

assert_not_contains() {
  local name="$1" haystack="$2" needle="$3"
  if printf '%s' "$haystack" | grep -qF "$needle"; then
    echo "FAIL ($name): expected output to NOT contain: $needle"
    fail_count=$((fail_count + 1))
  fi
}

assert_exit_code() {
  local name="$1" expected="$2" actual="$3"
  if [ "$actual" -ne "$expected" ]; then
    echo "FAIL ($name): expected exit $expected, got $actual"
    fail_count=$((fail_count + 1))
  fi
}

# --- comment-body: base case, no failed jobs ---
output=$(NOW="2026-09-10 12:00 UTC" WORKFLOW_NAME="Fuzzing" RUN_ID="111" \
  RUN_URL="https://example.test/runs/111" "$SCRIPT" comment-body 2>&1)
code=$?
assert_exit_code "comment-body base exit" 0 "$code"
assert_contains "comment-body base workflow name" "$output" '`Fuzzing` failed again'
assert_contains "comment-body base run link" "$output" '[#111](https://example.test/runs/111)'
assert_contains "comment-body base time" "$output" '2026-09-10 12:00 UTC'
assert_not_contains "comment-body base no failed jobs row" "$output" 'Failed jobs'

# --- comment-body: with failed jobs ---
output=$(NOW="2026-09-10 12:00 UTC" WORKFLOW_NAME="Fuzzing" RUN_ID="112" \
  RUN_URL="https://example.test/runs/112" FAILED_JOBS="formula-fuzz" \
  "$SCRIPT" comment-body 2>&1)
code=$?
assert_exit_code "comment-body failed-jobs exit" 0 "$code"
assert_contains "comment-body failed-jobs row" "$output" '**Failed jobs:** `formula-fuzz`'

# --- issue-body: base case, no failed jobs ---
output=$(NOW="2026-09-10 12:00 UTC" WORKFLOW_NAME="Homebrew CI" RUN_ID="200" \
  RUN_URL="https://example.test/runs/200" WORKFLOW_FILE=".github/workflows/brew-ci.yml" \
  "$SCRIPT" issue-body 2>&1)
code=$?
assert_exit_code "issue-body base exit" 0 "$code"
assert_contains "issue-body base heading" "$output" '## Workflow Failure'
assert_contains "issue-body base workflow row" "$output" '| **Workflow** | `Homebrew CI` |'
assert_contains "issue-body base run row" "$output" '[#200](https://example.test/runs/200)'
assert_contains "issue-body base file row" "$output" '| **File** | `.github/workflows/brew-ci.yml` |'
assert_contains "issue-body base time row" "$output" '2026-09-10 12:00 UTC'
assert_contains "issue-body base next steps" "$output" 'Do not close'
assert_not_contains "issue-body base no failed jobs row" "$output" 'Failed jobs'

# --- issue-body: with failed jobs ---
output=$(NOW="2026-09-10 12:00 UTC" WORKFLOW_NAME="Homebrew CI" RUN_ID="201" \
  RUN_URL="https://example.test/runs/201" WORKFLOW_FILE=".github/workflows/brew-ci.yml" \
  FAILED_JOBS="brew-audit-and-install (ubuntu-latest), brew-audit-and-install (macos-latest)" \
  "$SCRIPT" issue-body 2>&1)
code=$?
assert_exit_code "issue-body failed-jobs exit" 0 "$code"
assert_contains "issue-body failed-jobs row" "$output" \
  '| **Failed jobs** | `brew-audit-and-install (ubuntu-latest), brew-audit-and-install (macos-latest)` |'

# --- error contract: unknown mode ---
output=$("$SCRIPT" bogus-mode 2>&1)
code=$?
assert_exit_code "unknown mode exit" 1 "$code"
assert_contains "unknown mode message" "$output" "unknown mode 'bogus-mode'"

# --- error contract: missing required env var ---
output=$(WORKFLOW_NAME="Fuzzing" "$SCRIPT" comment-body 2>&1)
code=$?
assert_exit_code "missing env var exit" 1 "$code"
assert_contains "missing env var message" "$output" 'missing required env var RUN_ID'

if [ "$fail_count" -gt 0 ]; then
  echo "$fail_count assertion(s) failed"
  exit 1
fi
echo "All workflow_failure_notify.sh assertions passed"
