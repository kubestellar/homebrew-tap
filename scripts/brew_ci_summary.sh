#!/usr/bin/env bash
# brew_ci_summary.sh — emit a single-line, machine-readable summary of a
# brew-ci.yml (Homebrew CI) job run, mirroring the VALIDATE_FORMULAE_SUMMARY:
# pattern in validate_formulae.py and VERIFY_RELEASE_HEALTH_SUMMARY in
# verify_release_health.sh.
#
# brew-ci.yml's brew-audit-and-install job is the one CI job in this repo
# without an equivalent structured outcome record: a reader has to scroll
# ::group:: blocks to see whether/why a given OS's audit+install+test run
# passed, which is the "Formula CI health" SLI tracked in docs/slo.md.
#
# This is a standalone script, not wired into any workflow here: wiring it
# into brew-ci.yml requires editing .github/workflows/brew-ci.yml, which
# needs the `workflows` permission this script does not assume. See
# runbooks/proposed-brew-ci-observability-summary-step.yml for the
# ready-to-apply step a maintainer with that permission can add.
#
# Stdout-only structured output: no exporter, metrics backend, or off-box
# data flow is added, and labels are bounded (status/os/counts only).
#
# Usage: JOB_STATUS=success MATRIX_OS=ubuntu-latest scripts/brew_ci_summary.sh
#   Required inputs (fall back to "unknown" if unset, mirroring
#   fuzz_summary.sh's outcome defaults):
#     JOB_STATUS   - e.g. ${{ job.status }}
#     MATRIX_OS    - e.g. ${{ matrix.os }}
#   Optional:
#     FORMULA_DIR       - override the Formula/ directory (used by tests).
#     INSTALLED_FORMULAE - newline-separated list of installed formula
#                          names, used instead of querying `brew list
#                          --formula` (used by tests, or by callers without
#                          `brew` on PATH).
#
# Exit status: 0 if JOB_STATUS is "success", 1 otherwise.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FORMULA_DIR="${FORMULA_DIR:-$REPO_ROOT/Formula}"

JOB_STATUS="${JOB_STATUS:-unknown}"
MATRIX_OS="${MATRIX_OS:-unknown}"

formula_count=0
if [ -d "$FORMULA_DIR" ]; then
  for f in "$FORMULA_DIR"/*.rb; do
    [ -e "$f" ] || continue
    formula_count=$((formula_count + 1))
  done
fi

installed_list=""
if [ -n "${INSTALLED_FORMULAE+x}" ]; then
  installed_list="$INSTALLED_FORMULAE"
elif command -v brew >/dev/null 2>&1; then
  installed_list="$(brew list --formula 2>/dev/null || true)"
fi

installed_count=0
if [ -d "$FORMULA_DIR" ]; then
  for f in "$FORMULA_DIR"/*.rb; do
    [ -e "$f" ] || continue
    name="$(basename "$f" .rb)"
    if printf '%s\n' "$installed_list" | grep -qx "$name"; then
      installed_count=$((installed_count + 1))
    fi
  done
fi

printf 'BREW_CI_SUMMARY: {"status":"%s","os":"%s","formula_count":%s,"installed_count":%s}\n' \
  "$JOB_STATUS" "$MATRIX_OS" "$formula_count" "$installed_count"

if [ "$JOB_STATUS" != "success" ]; then
  exit 1
fi
