#!/usr/bin/env bash
# test_workflow_failure_notify_check_existing.sh — regression tests for
# the `check-existing-issue` mode of scripts/workflow_failure_notify.sh.
#
# Guards the extracted-from-inline-bash contract for the "Check for
# existing open issue" step in
# .github/workflows/scheduled-workflow-failure-issue.yml, which (unlike
# the comment-body/issue-body/failed-jobs steps in the same workflow)
# previously inlined its `gh issue list … --jq …` dedup snippet
# untested:
#
#   1. the mode calls `gh issue list --repo <REPOSITORY> --state open
#      --label workflow-failure --search 'in:title "..."' --json
#      number,title --jq '...'` — arguments must land in that exact
#      shape, so a future edit that drops --label or --state is caught
#      here (dropping either would widen the dedup search and risk
#      matching a closed or unrelated issue);
#   2. an exact title match prints `exists=true` followed by
#      `issue_number=<N>` on stdout, matching the workflow's
#      `$GITHUB_OUTPUT` contract;
#   3. no match prints only `exists=false`;
#   4. the `--search` term is built from the exact workflow name (so a
#      future edit cannot widen it and risk a false-positive dedup);
#   5. missing REPOSITORY or WORKFLOW_NAME fails fast with exit 1 and a
#      "missing required env var" message.
#
# Usage: scripts/test_workflow_failure_notify_check_existing.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

# shellcheck source=scripts/test_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test_lib.sh"

REPO_ROOT="$(repo_root)"
SCRIPT="$REPO_ROOT/scripts/workflow_failure_notify.sh"

make_work_dir

# make_stub_gh <dir> <json_result>
# Writes a fake `gh` on PATH that records its argv to $dir/gh.argv and
# prints <json_result> (already-filtered jq output, one issue number per
# line or empty) to emulate `gh issue list ... --jq ...`.
make_stub_gh() {
  local dir="$1" jq_result="$2"
  mkdir -p "$dir"
  cat > "$dir/gh" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$*" > "$dir/gh.argv"
if [ "\$1" != "issue" ] || [ "\$2" != "list" ]; then
  echo "unexpected gh invocation: \$*" >&2
  exit 99
fi
printf '%s' "$jq_result"
exit 0
STUB
  chmod +x "$dir/gh"
}

# --- Case 1: exact match found → exists=true + issue_number ---
stub1="$work_dir/stub1"
make_stub_gh "$stub1" "4321"
output=$(env -i PATH="$stub1:/usr/bin:/bin" \
  REPOSITORY="kubestellar/homebrew-tap" WORKFLOW_NAME="Fuzzing" \
  bash "$SCRIPT" check-existing-issue 2>&1)
code=$?
assert_exit_code "match-found exit" 0 "$code"
assert_contains "match-found exists=true" "$output" "exists=true"
assert_contains "match-found issue_number" "$output" "issue_number=4321"

argv="$(cat "$stub1/gh.argv")"
assert_contains "match-found argv subcommand" "$argv" "issue list"
assert_contains "match-found argv --repo" "$argv" \
  " --repo kubestellar/homebrew-tap"
assert_contains "match-found argv --state" "$argv" " --state open"
assert_contains "match-found argv --label" "$argv" " --label workflow-failure"
assert_contains "match-found argv --search" "$argv" \
  'in:title "Workflow failure: Fuzzing"'
assert_contains "match-found argv --json" "$argv" " --json number,title"

# --- Case 2: no match → exists=false only, no issue_number ---
stub2="$work_dir/stub2"
make_stub_gh "$stub2" ""
output=$(env -i PATH="$stub2:/usr/bin:/bin" \
  REPOSITORY="kubestellar/homebrew-tap" WORKFLOW_NAME="Homebrew CI" \
  bash "$SCRIPT" check-existing-issue 2>&1)
code=$?
assert_exit_code "no-match exit" 0 "$code"
assert_contains "no-match exists=false" "$output" "exists=false"
assert_not_contains "no-match has no issue_number" "$output" "issue_number"

# --- Case 3: argv --search uses the exact workflow name ---
# Guards against a future edit that widens the --search term (e.g. to
# just the workflow name without the "Workflow failure: " prefix),
# which would risk the full-text search surfacing an unrelated issue
# before the jq exact-match filter gets a chance to reject it.
stub3="$work_dir/stub3"
make_stub_gh "$stub3" ""
output=$(env -i PATH="$stub3:/usr/bin:/bin" \
  REPOSITORY="kubestellar/homebrew-tap" WORKFLOW_NAME="CodeQL Analysis" \
  bash "$SCRIPT" check-existing-issue 2>&1)
code=$?
assert_exit_code "search-term exit" 0 "$code"
assert_contains "search-term exists=false" "$output" "exists=false"
argv3="$(cat "$stub3/gh.argv")"
assert_contains "search-term uses full exact workflow name" "$argv3" \
  'in:title "Workflow failure: CodeQL Analysis"'

# --- Case 4: missing REPOSITORY → exit 1, useful message ---
output=$(env -i PATH="$stub1:/usr/bin:/bin" \
  WORKFLOW_NAME="Fuzzing" \
  bash "$SCRIPT" check-existing-issue 2>&1)
code=$?
assert_exit_code "missing REPOSITORY exit" 1 "$code"
assert_contains "missing REPOSITORY message" "$output" \
  'missing required env var REPOSITORY'

# --- Case 5: missing WORKFLOW_NAME → exit 1, useful message ---
output=$(env -i PATH="$stub1:/usr/bin:/bin" \
  REPOSITORY="kubestellar/homebrew-tap" \
  bash "$SCRIPT" check-existing-issue 2>&1)
code=$?
assert_exit_code "missing WORKFLOW_NAME exit" 1 "$code"
assert_contains "missing WORKFLOW_NAME message" "$output" \
  'missing required env var WORKFLOW_NAME'

# --- Case 6: unknown-mode error message now lists check-existing-issue ---
output=$("$SCRIPT" not-a-real-mode 2>&1)
code=$?
assert_exit_code "unknown mode still exits 1" 1 "$code"
assert_contains "unknown mode message lists check-existing-issue" "$output" \
  'check-existing-issue'

if [ "$fail_count" -gt 0 ]; then
  echo "$fail_count assertion(s) failed"
  exit 1
fi
echo "All workflow_failure_notify.sh check-existing-issue assertions passed"
