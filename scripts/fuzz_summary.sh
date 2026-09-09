#!/usr/bin/env bash
# fuzz_summary.sh — emit a single-line, machine-readable summary of a
# fuzz.yml (Fuzzing) job run, mirroring the VALIDATE_FORMULAE_SUMMARY:
# pattern in validate_formulae.py, VERIFY_RELEASE_HEALTH_SUMMARY in
# verify_release_health.sh, and BREW_CI_SUMMARY: in brew_ci_summary.sh.
#
# fuzz.yml's final "Fuzzing summary" step only echoes fixed, free-text
# lines ("Fuzzing completed successfully!" plus a checklist) — it carries
# no machine-readable outcome record, so a reader has to scroll the
# preceding syntax/structure/URL-checksum step logs to see whether/why a
# given run passed. This is the "Formula fuzz health" SLI tracked in
# docs/slo.md.
#
# This is a standalone script, not wired into any workflow here: wiring it
# into fuzz.yml requires editing .github/workflows/fuzz.yml, which needs
# the `workflows` permission this script does not assume. See
# runbooks/proposed-fuzz-observability-summary-step.yml for the
# ready-to-apply step a maintainer with that permission can add.
#
# Stdout-only structured output: no exporter, metrics backend, or off-box
# data flow is added, and labels are bounded (status/counts only).
#
# Usage: JOB_STATUS=success scripts/fuzz_summary.sh
#   Required input (falls back to "unknown" if unset):
#     JOB_STATUS   - e.g. ${{ job.status }}
#   Optional:
#     FORMULA_DIR  - override the Formula/ directory (used by tests).
#
# Exit status: 0 if JOB_STATUS is "success", 1 otherwise.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FORMULA_DIR="${FORMULA_DIR:-$REPO_ROOT/Formula}"

JOB_STATUS="${JOB_STATUS:-unknown}"

formula_count=0
if [ -d "$FORMULA_DIR" ]; then
  for f in "$FORMULA_DIR"/*.rb; do
    [ -e "$f" ] || continue
    formula_count=$((formula_count + 1))
  done
fi

printf 'FUZZ_SUMMARY: {"status":"%s","formula_count":%s}\n' \
  "$JOB_STATUS" "$formula_count"

if [ "$JOB_STATUS" != "success" ]; then
  exit 1
fi
