#!/usr/bin/env bash
# workflow_failure_notify.sh — render the markdown bodies used by
# runbooks/proposed-scheduled-workflow-failure-issue.yml's "Comment on
# existing issue" and "Open new issue" steps.
#
# That workflow is not yet active (this agent's GitHub App installation
# lacks the `workflows` permission required to add files under
# .github/workflows/ — see docs/slo.md), but its inline printf/heredoc
# body-building logic had zero test coverage, unlike every other CI-log
# script in this repo (fuzz_summary.sh, brew_ci_summary.sh,
# verify_release_health.sh all have companion test_*.sh files). This
# script extracts that formatting so it can be regression-tested here and
# reused verbatim once a maintainer applies the runbook.
#
# Stdout-only: no exporter, metrics backend, or off-box data flow.
#
# Usage:
#   workflow_failure_notify.sh comment-body
#   workflow_failure_notify.sh issue-body
#
# Required env vars (mirroring the workflow_run event context):
#   WORKFLOW_NAME   - e.g. "Fuzzing"
#   RUN_ID          - e.g. "123456789"
#   RUN_URL         - e.g. "https://github.com/.../actions/runs/123456789"
# issue-body also uses:
#   WORKFLOW_FILE   - e.g. ".github/workflows/fuzz.yml"
# Optional for both modes:
#   FAILED_JOBS     - comma-joined failed job names; omitted row if unset/empty.
#   NOW             - override the timestamp line (used by tests); defaults
#                     to the current UTC time.
#
# Exit status: 0 on success, 1 on missing mode or required env var.

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
    printf '2. Follow the [Scheduled Workflow Failure runbook](../../runbooks/scheduled-workflow-failure.md)\n'
    printf '3. Fix the underlying issue\n'
    printf '4. **Do not close** this issue until the workflow passes on `main`\n\n'
    printf -- '---\n'
    printf '*This issue was automatically created by the scheduled workflow failure monitor.*\n'
    ;;
  *)
    echo "workflow_failure_notify.sh: unknown mode '$mode' (expected comment-body|issue-body)" >&2
    exit 1
    ;;
esac
