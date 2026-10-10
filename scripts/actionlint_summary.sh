#!/usr/bin/env bash
# actionlint_summary.sh — emit a single-line, machine-readable summary of
# an actionlint.yml job run, mirroring the FUZZ_SUMMARY:/BREW_CI_SUMMARY:
# pattern in fuzz_summary.sh/brew_ci_summary.sh.
#
# actionlint.yml's two jobs ("lint workflows" and "lint shell scripts")
# are the only scheduled, alert-covered workflow in this repo (see
# docs/slo.md and runbooks/scheduled-workflow-failure.md — both jobs'
# conclusions roll up into the "actionlint" workflow_run watched by
# scheduled-workflow-failure-issue.yml) with no structured per-run
# outcome record: a reader has to open the raw actionlint/shellcheck
# tool output to see whether/why a given run passed, unlike every
# sibling scheduled workflow (brew-ci.yml, fuzz.yml, validate-formulae.yml).
#
# This script is invoked once per job (JOB_NAME=actionlint for the "lint
# workflows" job, JOB_NAME=shellcheck for the "lint shell scripts" job)
# from an "Emit CI-observability summary" step, analogous to
# fuzz_summary.sh's usage in fuzz.yml.
#
# The summary line (and its $GITHUB_STEP_SUMMARY table) is emitted via the
# shared scripts/lib_emit_summary.sh, which owns the JSON shape/escaping
# contract for every *_SUMMARY: marker in this repo.
#
# Stdout-only structured output: no exporter, metrics backend, or off-box
# data flow is added, and labels are bounded (status/job/counts only).
#
# Usage: JOB_STATUS=success JOB_NAME=actionlint scripts/actionlint_summary.sh
#   Required inputs (fall back to "unknown" if unset, mirroring
#   fuzz_summary.sh's outcome defaults):
#     JOB_STATUS   - e.g. ${{ job.status }}
#     JOB_NAME     - "actionlint" or "shellcheck"
#   Optional:
#     WORKFLOWS_DIR - override the .github/workflows/ directory (used by
#                     tests), counted when JOB_NAME=actionlint.
#     SCRIPTS_DIR   - override the scripts/ directory (used by tests),
#                     counted when JOB_NAME=shellcheck.
#
# Exit status: 0 if JOB_STATUS is "success", 1 otherwise.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKFLOWS_DIR="${WORKFLOWS_DIR:-$REPO_ROOT/.github/workflows}"
SCRIPTS_DIR="${SCRIPTS_DIR:-$REPO_ROOT/scripts}"

# shellcheck source=scripts/lib_emit_summary.sh
. "$REPO_ROOT/scripts/lib_emit_summary.sh"

JOB_STATUS="${JOB_STATUS:-unknown}"
JOB_NAME="${JOB_NAME:-unknown}"

file_count=0
case "$JOB_NAME" in
  actionlint)
    if [ -d "$WORKFLOWS_DIR" ]; then
      for f in "$WORKFLOWS_DIR"/*.yml "$WORKFLOWS_DIR"/*.yaml; do
        [ -e "$f" ] || continue
        file_count=$((file_count + 1))
      done
    fi
    ;;
  shellcheck)
    if [ -d "$SCRIPTS_DIR" ]; then
      for f in "$SCRIPTS_DIR"/*.sh; do
        [ -e "$f" ] || continue
        file_count=$((file_count + 1))
      done
    fi
    ;;
  *)
    ;;
esac

emit_ci_summary ACTIONLINT_SUMMARY \
  status="$JOB_STATUS" job:str="$JOB_NAME" file_count="$file_count"

if [ "$JOB_STATUS" != "success" ]; then
  exit 1
fi
