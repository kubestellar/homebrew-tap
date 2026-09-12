#!/usr/bin/env bash
# test_workflow_failure_notify_edge_cases.sh — supplementary regression
# tests for scripts/workflow_failure_notify.sh covering error and branch
# cases not exercised by scripts/test_workflow_failure_notify.sh:
#
#   1. no mode arg at all (falls through to the `*)` case with an empty
#      quoted mode — distinct from an unknown non-empty mode).
#   2. issue-body with WORKFLOW_FILE unset — must exit 1 with the exact
#      "missing required env var WORKFLOW_FILE" message. The base suite
#      only exercises the missing-RUN_ID path in comment-body mode; this
#      guards the issue-body-only require call so a future edit can't
#      silently drop the WORKFLOW_FILE check.
#   3. issue-body with WORKFLOW_NAME unset — must exit 1 before reaching
#      any other require, guarding the require order.
#   4. FAILED_JOBS explicitly set to the empty string (versus unset) —
#      the row must still be omitted in both comment-body and issue-body
#      modes. This guards the `[ -n "${FAILED_JOBS:-}" ]` branch against
#      a future rewrite that swaps in a `-v`/`+x` test which would
#      accept an empty string as "set" and render a broken row.
#
# Usage: scripts/test_workflow_failure_notify_edge_cases.sh
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
    echo "--- output ---"
    printf '%s\n' "$haystack"
    echo "--------------"
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

# --- Case 1: no mode arg at all → empty mode reaches the `*)` case ---
output=$("$SCRIPT" 2>&1)
code=$?
assert_exit_code "no-mode exit" 1 "$code"
assert_contains "no-mode message" "$output" "unknown mode ''"

# --- Case 2: issue-body missing WORKFLOW_FILE ---
output=$(NOW="2026-09-10 12:00 UTC" WORKFLOW_NAME="Homebrew CI" RUN_ID="300" \
  RUN_URL="https://example.test/runs/300" "$SCRIPT" issue-body 2>&1)
code=$?
assert_exit_code "issue-body missing WORKFLOW_FILE exit" 1 "$code"
assert_contains "issue-body missing WORKFLOW_FILE message" "$output" \
  'missing required env var WORKFLOW_FILE'
assert_not_contains "issue-body missing WORKFLOW_FILE no body" "$output" \
  '## Workflow Failure'

# --- Case 3: issue-body missing WORKFLOW_NAME (require order) ---
output=$(NOW="2026-09-10 12:00 UTC" RUN_ID="301" \
  RUN_URL="https://example.test/runs/301" \
  WORKFLOW_FILE=".github/workflows/brew-ci.yml" \
  "$SCRIPT" issue-body 2>&1)
code=$?
assert_exit_code "issue-body missing WORKFLOW_NAME exit" 1 "$code"
assert_contains "issue-body missing WORKFLOW_NAME message" "$output" \
  'missing required env var WORKFLOW_NAME'

# --- Case 4a: comment-body with FAILED_JOBS explicitly empty ---
output=$(NOW="2026-09-10 12:00 UTC" WORKFLOW_NAME="Fuzzing" RUN_ID="400" \
  RUN_URL="https://example.test/runs/400" FAILED_JOBS="" \
  "$SCRIPT" comment-body 2>&1)
code=$?
assert_exit_code "comment-body FAILED_JOBS empty exit" 0 "$code"
assert_not_contains "comment-body FAILED_JOBS empty no row" "$output" \
  'Failed jobs'
# Sanity: the base body still rendered.
assert_contains "comment-body FAILED_JOBS empty still has run link" "$output" \
  '[#400](https://example.test/runs/400)'

# --- Case 4b: issue-body with FAILED_JOBS explicitly empty ---
output=$(NOW="2026-09-10 12:00 UTC" WORKFLOW_NAME="Homebrew CI" RUN_ID="401" \
  RUN_URL="https://example.test/runs/401" \
  WORKFLOW_FILE=".github/workflows/brew-ci.yml" FAILED_JOBS="" \
  "$SCRIPT" issue-body 2>&1)
code=$?
assert_exit_code "issue-body FAILED_JOBS empty exit" 0 "$code"
assert_not_contains "issue-body FAILED_JOBS empty no row" "$output" \
  'Failed jobs'
# Sanity: the base body still rendered.
assert_contains "issue-body FAILED_JOBS empty still has file row" "$output" \
  '| **File** | `.github/workflows/brew-ci.yml` |'

if [ "$fail_count" -gt 0 ]; then
  echo "$fail_count assertion(s) failed"
  exit 1
fi
echo "All workflow_failure_notify.sh edge-case assertions passed"
