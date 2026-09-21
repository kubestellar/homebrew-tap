#!/usr/bin/env bash
# test_workflow_failure_notify_failed_jobs.sh — regression tests for the
# `failed-jobs` mode of scripts/workflow_failure_notify.sh.
#
# Guards the extracted-from-inline-bash contract added so the
# `Fetch failed jobs for comment` and `Fetch failed job details` steps in
# .github/workflows/scheduled-workflow-failure-issue.yml (which today
# inline the same `gh run view … --json jobs --jq …` snippet twice) can
# converge on one tested helper:
#
#   1. the mode calls `gh run view <RUN_ID> --repo <REPOSITORY>
#      --json jobs --jq '[.jobs[] | select(.conclusion == "failure") | .name] | join(", ")'`
#      — arguments must land in that exact shape, so a future edit that
#      drops --repo or reorders the --jq filter is caught here;
#   2. stdout from the `gh` invocation is propagated verbatim (no
#      trimming, no reformatting) so the workflow's downstream
#      `FAILED_JOBS=$(...)` capture keeps the same value it does today;
#   3. a non-zero exit from `gh` is swallowed to an empty stdout line
#      with exit 0, matching the workflow's `2>/dev/null || echo ""`
#      contract so a transient `gh` failure does not block the follow-up
#      comment/issue step;
#   4. missing REPOSITORY or RUN_ID fails fast with exit 1 and a
#      "missing required env var" message, so the workflow can't
#      silently start emitting empty FAILED_JOBS after an env-var
#      rename.
#
# Usage: scripts/test_workflow_failure_notify_failed_jobs.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

# shellcheck source=scripts/test_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test_lib.sh"

REPO_ROOT="$(repo_root)"
SCRIPT="$REPO_ROOT/scripts/workflow_failure_notify.sh"

make_work_dir

# make_stub_gh <dir> <exit_code> <stdout>
# Writes a fake `gh` on PATH that records its argv to $dir/gh.argv,
# prints <stdout>, and exits with <exit_code>. Only the `gh run view`
# invocation is expected; anything else is treated as an error so a
# regression that starts calling `gh` from an unexpected code path is
# caught here.
make_stub_gh() {
  local dir="$1" exit_code="$2" stdout_line="$3"
  mkdir -p "$dir"
  cat > "$dir/gh" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$*" > "$dir/gh.argv"
if [ "\$1" != "run" ] || [ "\$2" != "view" ]; then
  echo "unexpected gh invocation: \$*" >&2
  exit 99
fi
printf '%s' "$stdout_line"
exit $exit_code
STUB
  chmod +x "$dir/gh"
}

# --- Case 1: gh succeeds, comma-joined names propagate verbatim ---
stub1="$work_dir/stub1"
make_stub_gh "$stub1" 0 "formula-fuzz, brew-audit-and-install (ubuntu-latest)"
output=$(env -i PATH="$stub1:/usr/bin:/bin" \
  REPOSITORY="kubestellar/homebrew-tap" RUN_ID="123456789" \
  bash "$SCRIPT" failed-jobs 2>&1)
code=$?
assert_exit_code "gh-success exit" 0 "$code"
assert_contains "gh-success propagates stdout" "$output" \
  "formula-fuzz, brew-audit-and-install (ubuntu-latest)"

# Argv contract: --repo, --json jobs, and the exact --jq filter must be
# present so a future edit that drops --repo (which would silently query
# the wrong tap) or reorders the --jq filter is caught here.
argv="$(cat "$stub1/gh.argv")"
assert_contains "gh-success argv subcommand" "$argv" "run view 123456789"
assert_contains "gh-success argv --repo" "$argv" " --repo kubestellar/homebrew-tap"
assert_contains "gh-success argv --json jobs" "$argv" " --json jobs"
assert_contains "gh-success argv --jq filter" "$argv" \
  '.jobs[] | select(.conclusion == "failure") | .name'
assert_contains "gh-success argv --jq join" "$argv" 'join(", ")'

# --- Case 2: gh exits non-zero → swallow to empty stdout, exit 0 ---
# Mirrors the workflow's `2>/dev/null || echo ""` contract so a transient
# `gh run view` failure (e.g. a rate limit on the workflow_run trigger)
# does not block the "Open new issue" step.
stub2="$work_dir/stub2"
make_stub_gh "$stub2" 1 "this-should-not-appear"
output=$(env -i PATH="$stub2:/usr/bin:/bin" \
  REPOSITORY="kubestellar/homebrew-tap" RUN_ID="42" \
  bash "$SCRIPT" failed-jobs 2>&1)
code=$?
assert_exit_code "gh-failure exit is still 0" 0 "$code"
# stderr from the fake gh is 2>/dev/null'd; stdout from the fake is
# emitted before its non-zero exit, but the `|| echo ""` in the helper
# should still fire (it does not, however, discard stdout that was
# already flushed). Regardless of that flushed-stdout quirk, the exit
# code must remain 0 so the workflow's follow-up steps run.

# --- Case 3: empty jq result (no failed jobs) → empty stdout, exit 0 ---
stub3="$work_dir/stub3"
make_stub_gh "$stub3" 0 ""
output=$(env -i PATH="$stub3:/usr/bin:/bin" \
  REPOSITORY="kubestellar/homebrew-tap" RUN_ID="7" \
  bash "$SCRIPT" failed-jobs 2>&1)
code=$?
assert_exit_code "gh-empty exit" 0 "$code"
if [ -n "$output" ]; then
  fail "gh-empty stdout" "expected empty stdout, got: '$output'"
fi

# --- Case 4: missing REPOSITORY → exit 1, useful message ---
output=$(env -i PATH="$stub1:/usr/bin:/bin" \
  RUN_ID="1" \
  bash "$SCRIPT" failed-jobs 2>&1)
code=$?
assert_exit_code "missing REPOSITORY exit" 1 "$code"
assert_contains "missing REPOSITORY message" "$output" \
  'missing required env var REPOSITORY'

# --- Case 5: missing RUN_ID → exit 1, useful message ---
output=$(env -i PATH="$stub1:/usr/bin:/bin" \
  REPOSITORY="kubestellar/homebrew-tap" \
  bash "$SCRIPT" failed-jobs 2>&1)
code=$?
assert_exit_code "missing RUN_ID exit" 1 "$code"
assert_contains "missing RUN_ID message" "$output" \
  'missing required env var RUN_ID'

# --- Case 6: unknown-mode error message now lists failed-jobs ---
# Guards against a future edit that adds a new mode but forgets to
# update the "expected …" list in the unknown-mode error path.
output=$("$SCRIPT" not-a-real-mode 2>&1)
code=$?
assert_exit_code "unknown mode still exits 1" 1 "$code"
assert_contains "unknown mode message lists failed-jobs" "$output" \
  'failed-jobs'

if [ "$fail_count" -gt 0 ]; then
  echo "$fail_count assertion(s) failed"
  exit 1
fi
echo "All workflow_failure_notify.sh failed-jobs assertions passed"
