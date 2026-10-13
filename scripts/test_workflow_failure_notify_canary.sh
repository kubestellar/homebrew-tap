#!/usr/bin/env bash
# test_workflow_failure_notify_canary.sh — regression tests for the
# `canary-body` mode of scripts/workflow_failure_notify.sh.
#
# .github/workflows/alert-canary.yml (the canary for
# scheduled-workflow-failure-issue.yml itself) inlines its BODY= message
# untested — the same gap `check-existing-issue` closed for the sibling
# workflow (kubestellar/homebrew-tap#727). alert-canary.yml is the one
# place a silent formatting regression in this family of scripts would
# have no other alerting layer to catch it, since it IS the alerting
# layer's own watchdog.
#
# Guards:
#   1. the body contains the alert file name (backtick-quoted), the
#      workflows URL built from REPOSITORY + ALERT_FILE, the runbook
#      link, and the canary run URL built from GITHUB_SERVER_URL +
#      REPOSITORY + GITHUB_RUN_ID — so a future edit can't silently drop
#      one of those four pieces of context an on-call reader needs;
#   2. output is a single line (matching alert-canary.yml's plain
#      `gh issue comment --body "$BODY"` / `gh issue create --body
#      "$BODY"` usage, not a body-file);
#   3. missing ALERT_FILE, REPOSITORY, GITHUB_SERVER_URL, or
#      GITHUB_RUN_ID fails fast with exit 1 and a "missing required env
#      var" message.
#
# Usage: scripts/test_workflow_failure_notify_canary.sh
# Exit status: 0 if all assertions pass, 1 otherwise.
# shellcheck disable=SC2016  # literal backtick/markdown strings in single quotes, not variable expansion

set -uo pipefail

# shellcheck source=scripts/test_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test_lib.sh"

REPO_ROOT="$(repo_root)"
SCRIPT="$REPO_ROOT/scripts/workflow_failure_notify.sh"

# --- canary-body: base case ---
output=$(ALERT_FILE="scheduled-workflow-failure-issue.yml" \
  REPOSITORY="kubestellar/homebrew-tap" \
  GITHUB_SERVER_URL="https://github.com" \
  GITHUB_RUN_ID="999" \
  "$SCRIPT" canary-body 2>&1)
code=$?
assert_exit_code "canary-body base exit" 0 "$code"
assert_contains "canary-body base alert file" "$output" \
  '`scheduled-workflow-failure-issue.yml`'
assert_contains "canary-body base workflows url" "$output" \
  'https://github.com/kubestellar/homebrew-tap/actions/workflows/scheduled-workflow-failure-issue.yml'
assert_contains "canary-body base runbook link" "$output" \
  'runbooks/scheduled-workflow-failure.md'
assert_contains "canary-body base run url" "$output" \
  'https://github.com/kubestellar/homebrew-tap/actions/runs/999'

line_count=$(printf '%s\n' "$output" | wc -l | tr -d ' ')
if [ "$line_count" != "1" ]; then
  echo "FAIL: canary-body base single line (got $line_count lines)"
  fail_count=$((fail_count + 1))
fi

# --- error contract: missing required env vars ---
output=$(REPOSITORY="kubestellar/homebrew-tap" \
  GITHUB_SERVER_URL="https://github.com" \
  GITHUB_RUN_ID="999" \
  "$SCRIPT" canary-body 2>&1)
code=$?
assert_exit_code "canary-body missing ALERT_FILE exit" 1 "$code"
assert_contains "canary-body missing ALERT_FILE message" "$output" \
  'missing required env var ALERT_FILE'

output=$(ALERT_FILE="scheduled-workflow-failure-issue.yml" \
  GITHUB_SERVER_URL="https://github.com" \
  GITHUB_RUN_ID="999" \
  "$SCRIPT" canary-body 2>&1)
code=$?
assert_exit_code "canary-body missing REPOSITORY exit" 1 "$code"
assert_contains "canary-body missing REPOSITORY message" "$output" \
  'missing required env var REPOSITORY'

output=$(env -u GITHUB_SERVER_URL \
  ALERT_FILE="scheduled-workflow-failure-issue.yml" \
  REPOSITORY="kubestellar/homebrew-tap" \
  GITHUB_RUN_ID="999" \
  "$SCRIPT" canary-body 2>&1)
code=$?
assert_exit_code "canary-body missing GITHUB_SERVER_URL exit" 1 "$code"
assert_contains "canary-body missing GITHUB_SERVER_URL message" "$output" \
  'missing required env var GITHUB_SERVER_URL'

output=$(env -u GITHUB_RUN_ID \
  ALERT_FILE="scheduled-workflow-failure-issue.yml" \
  REPOSITORY="kubestellar/homebrew-tap" \
  GITHUB_SERVER_URL="https://github.com" \
  "$SCRIPT" canary-body 2>&1)
code=$?
assert_exit_code "canary-body missing GITHUB_RUN_ID exit" 1 "$code"
assert_contains "canary-body missing GITHUB_RUN_ID message" "$output" \
  'missing required env var GITHUB_RUN_ID'

if [ "$fail_count" -gt 0 ]; then
  echo "$fail_count assertion(s) failed"
  exit 1
fi
echo "All workflow_failure_notify.sh canary-body assertions passed"
