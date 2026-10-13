#!/usr/bin/env bash
# workflow_failure_notify.sh — render the markdown bodies used by
# .github/workflows/scheduled-workflow-failure-issue.yml's "Comment on
# existing issue" and "Open new issue" steps (applied in #441).
#
# Its inline printf/heredoc body-building logic had zero test coverage,
# unlike every other CI-log script in this repo (fuzz_summary.sh,
# brew_ci_summary.sh, verify_release_health.sh all have companion
# test_*.sh files). This script extracts that formatting so it can be
# regression-tested here and reused verbatim by the applied workflow.
#
# Stdout-only: no exporter, metrics backend, or off-box data flow.
#
# Usage:
#   workflow_failure_notify.sh comment-body
#   workflow_failure_notify.sh issue-body
#   workflow_failure_notify.sh failed-jobs
#   workflow_failure_notify.sh check-existing-issue
#   workflow_failure_notify.sh canary-body
#
# Required env vars (mirroring the workflow_run event context):
#   WORKFLOW_NAME   - e.g. "Fuzzing"
#   RUN_ID          - e.g. "123456789"
#   RUN_URL         - e.g. "https://github.com/.../actions/runs/123456789"
# issue-body also uses:
#   WORKFLOW_FILE   - e.g. ".github/workflows/fuzz.yml"
# Optional for comment-body / issue-body:
#   FAILED_JOBS     - comma-joined failed job names; omitted row if unset/empty.
#   NOW             - override the timestamp line (used by tests); defaults
#                     to the current UTC time.
#
# failed-jobs mode uses (called by the `Fetch failed jobs for comment` and
# `Fetch failed job details` steps in
# .github/workflows/scheduled-workflow-failure-issue.yml, which previously
# inlined the same `gh run view … --jq …` snippet twice):
#   REPOSITORY      - e.g. "kubestellar/homebrew-tap"
#   RUN_ID          - e.g. "123456789"
# failed-jobs prints the comma-joined names of jobs whose conclusion is
# "failure" for that run, or the empty string if `gh run view` errors
# (matching the `2>/dev/null || echo ""` swallow-on-error contract the
# workflow already relies on so the follow-up step is not blocked).
#
# check-existing-issue mode uses (called by the `Check for existing open
# issue` step in .github/workflows/scheduled-workflow-failure-issue.yml,
# which previously inlined the same `gh issue list … --jq …` dedup
# snippet untested):
#   REPOSITORY      - e.g. "kubestellar/homebrew-tap"
#   WORKFLOW_NAME   - e.g. "Fuzzing"
# check-existing-issue prints two lines, mirroring the step's
# $GITHUB_OUTPUT contract:
#   exists=true|false
#   issue_number=<N>        (second line only when exists=true)
# It searches open issues labeled "workflow-failure" whose title is
# exactly "Workflow failure: <WORKFLOW_NAME>" (the `--search` full-text
# query narrows the candidate set; the `select(.title == …)` jq filter
# then enforces an exact match so a workflow name that is a substring of
# another, e.g. "CodeQL" vs. "CodeQL Analysis", cannot dedup onto the
# wrong issue).
#
# canary-body mode uses (called by the "Check alert workflow ran in last
# 24h" step in .github/workflows/alert-canary.yml, which inlines the same
# BODY= message untested — alert-canary.yml is itself the canary for
# scheduled-workflow-failure-issue.yml, i.e. the one place a silent
# formatting regression would have no other alerting layer to catch it):
#   ALERT_FILE        - e.g. "scheduled-workflow-failure-issue.yml"
#   REPOSITORY        - e.g. "kubestellar/homebrew-tap"
#   GITHUB_SERVER_URL - e.g. "https://github.com"
#   GITHUB_RUN_ID     - e.g. "123456789"
# canary-body prints the single-line issue/comment body used when the
# alert workflow itself hasn't run in 24h. The dedup check ahead of it
# reuses the existing check-existing-issue mode verbatim (same
# "Workflow failure: <WORKFLOW_NAME>" title contract), with
# WORKFLOW_NAME="Open Issue on Scheduled Workflow Failure" — no new mode
# needed for that half.
#
# Exit status: 0 on success (including failed-jobs' swallow-on-error
# case), 1 on missing mode or missing required env var.

# shellcheck disable=SC2016  # literal backtick/markdown strings in single quotes, not variable expansion
set -uo pipefail

mode="${1:-}"
now="${NOW:-$(date -u '+%Y-%m-%d %H:%M UTC')}"

require() {
  local var_name="$1"
  if [ -z "${!var_name:-}" ]; then
    echo "workflow_failure_notify.sh: missing required env var $var_name" >&2
    exit 1
  fi
}

case "$mode" in
  comment-body)
    require WORKFLOW_NAME
    require RUN_ID
    require RUN_URL
    printf '**Still failing** — `%s` failed again.\n\n' "$WORKFLOW_NAME"
    printf -- '- **Run:** [#%s](%s)\n' "$RUN_ID" "$RUN_URL"
    printf -- '- **Time:** %s\n' "$now"
    if [ -n "${FAILED_JOBS:-}" ]; then
      printf -- '- **Failed jobs:** `%s`\n' "$FAILED_JOBS"
    fi
    ;;
  issue-body)
    require WORKFLOW_NAME
    require RUN_ID
    require RUN_URL
    require WORKFLOW_FILE
    printf '## Workflow Failure\n\n'
    printf 'The **%s** workflow failed.\n\n' "$WORKFLOW_NAME"
    printf '| Detail | Value |\n'
    printf '|--------|-------|\n'
    printf '| **Workflow** | `%s` |\n' "$WORKFLOW_NAME"
    printf '| **Run** | [#%s](%s) |\n' "$RUN_ID" "$RUN_URL"
    printf '| **File** | `%s` |\n' "$WORKFLOW_FILE"
    printf '| **Time** | %s |\n' "$now"
    if [ -n "${FAILED_JOBS:-}" ]; then
      printf '| **Failed jobs** | `%s` |\n' "$FAILED_JOBS"
    fi
    printf '\n### Next Steps\n'
    printf '1. Check the [failed run](%s) for error details\n' "$RUN_URL"
    printf '2. Follow the [Scheduled Workflow Failure runbook](https://github.com/kubestellar/homebrew-tap/blob/main/runbooks/scheduled-workflow-failure.md)\n'
    printf '3. Fix the underlying issue\n'
    printf '4. **Do not close** this issue until the workflow passes on `main`\n\n'
    printf -- '---\n'
    printf '*This issue was automatically created by the scheduled workflow failure monitor.*\n'
    ;;
  failed-jobs)
    require REPOSITORY
    require RUN_ID
    # Preserve the contract of the snippet formerly inlined (twice,
    # byte-identically) in scheduled-workflow-failure-issue.yml's
    # `Fetch failed jobs for comment` / `Fetch failed job details` steps:
    # swallow any `gh run view` failure to an empty string so the calling
    # workflow step keeps its exit-0 contract and downstream steps still run.
    #
    # Unlike the snippet it replaced, a `gh` failure is still logged (to
    # this script's own stderr, which the calling workflow step does not
    # redirect) instead of being fully discarded via `2>/dev/null`. Before
    # this, a `gh run view` failure here (auth hiccup, rate limit, API
    # outage) left no trace at all: the comment/issue body would just
    # silently omit the "Failed jobs" row with nothing in the CI log
    # explaining why.
    if ! jobs_output=$(gh run view "$RUN_ID" \
      --repo "$REPOSITORY" \
      --json jobs \
      --jq '[.jobs[] | select(.conclusion == "failure") | .name] | join(", ")' \
      2>&1); then
      echo "workflow_failure_notify.sh: failed-jobs: gh run view failed for repo=$REPOSITORY run=$RUN_ID: ${jobs_output}" >&2
      echo ""
    else
      printf '%s\n' "$jobs_output"
    fi
    ;;
  check-existing-issue)
    require REPOSITORY
    require WORKFLOW_NAME
    search_title="Workflow failure: ${WORKFLOW_NAME}"
    export SEARCH_TITLE="$search_title"
    existing=$(gh issue list \
      --repo "$REPOSITORY" \
      --state open \
      --label "workflow-failure" \
      --search "in:title \"${search_title}\"" \
      --json number,title \
      --jq '.[] | select(.title == env.SEARCH_TITLE) | .number' \
    )
    if [ -n "$existing" ]; then
      printf 'exists=true\n'
      printf 'issue_number=%s\n' "$existing"
    else
      printf 'exists=false\n'
    fi
    ;;
  canary-body)
    require ALERT_FILE
    require REPOSITORY
    require GITHUB_SERVER_URL
    require GITHUB_RUN_ID
    printf 'No run of `%s` in the last 24h. It may be disabled (60 days of inactivity), have a broken `workflow_run.workflows` list, or be failing before it starts. Check https://github.com/%s/actions/workflows/%s and see runbooks/scheduled-workflow-failure.md. Canary run: %s/%s/actions/runs/%s\n' \
      "$ALERT_FILE" "$REPOSITORY" "$ALERT_FILE" "$GITHUB_SERVER_URL" "$REPOSITORY" "$GITHUB_RUN_ID"
    ;;
  *)
    echo "workflow_failure_notify.sh: unknown mode '$mode' (expected comment-body|issue-body|failed-jobs|check-existing-issue|canary-body)" >&2
    exit 1
    ;;
esac
