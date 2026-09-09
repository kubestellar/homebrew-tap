#!/usr/bin/env bash
# brew_ci_summary.sh — emits a bounded, stdout-only BREW_CI_SUMMARY JSON
# line for CI-log observability, mirroring the VALIDATE_FORMULAE_SUMMARY
# (scripts/validate_formulae.py) and VERIFY_RELEASE_HEALTH_SUMMARY
# (scripts/verify_release_health.sh) patterns already in this repo (see
# docs/slo.md's Formula CI health SLI).
#
# `.github/workflows/brew-ci.yml` is the one CI job in this repo without an
# equivalent structured outcome record; this script is the tested,
# standalone extraction of the logic previously proposed only as inline
# bash prose in
# ../runbooks/proposed-brew-ci-observability-summary-step.yml
# (see homebrew-tap#380). It does not modify or get invoked from
# brew-ci.yml itself — wiring a step that calls this script into that
# workflow requires `workflows` permission this agent's GitHub App
# installation lacks; a maintainer can do so per the runbook.
#
# No exporter, metrics backend, or external data flow is added: output is a
# single bounded JSON line (status/os/formula_count/installed_count only,
# no unbounded labels).
#
# Env vars (both required, matching what a workflow step would provide):
#   JOB_STATUS  - overall job status, e.g. "${{ job.status }}"
#   MATRIX_OS   - the matrix OS this run is for, e.g. "${{ matrix.os }}"
# Optional:
#   FORMULA_DIR - override the Formula directory (defaults to
#                 <repo root>/Formula). Used by tests to stub input without
#                 touching the real Formula/ directory.
#
# 'brew' must be on PATH so `brew list --formula` can report which
# formulae are actually installed; tests stub this by prepending a fake
# `brew` script to PATH (see test_brew_ci_summary.sh).
#
# Exit status: 0 on success; 2 if a required env var is unset or 'brew' is
# not on PATH.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FORMULA_DIR="${FORMULA_DIR:-$REPO_ROOT/Formula}"

if [ -z "${JOB_STATUS:-}" ]; then
  echo "brew_ci_summary.sh: JOB_STATUS must be set (e.g. \${{ job.status }})" >&2
  exit 2
fi
if [ -z "${MATRIX_OS:-}" ]; then
  echo "brew_ci_summary.sh: MATRIX_OS must be set (e.g. \${{ matrix.os }})" >&2
  exit 2
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "brew_ci_summary.sh: 'brew' is not on PATH — install Homebrew first, or stub it for tests." >&2
  exit 2
fi

formula_count=0
installed_count=0
installed_list="$(brew list --formula 2>/dev/null || true)"

for formula in "$FORMULA_DIR"/*.rb; do
  [ -e "$formula" ] || continue
  name="$(basename "${formula%.rb}")"
  formula_count=$((formula_count + 1))
  if grep -qx "$name" <<<"$installed_list"; then
    installed_count=$((installed_count + 1))
  fi
done

echo "BREW_CI_SUMMARY: {\"status\":\"${JOB_STATUS}\",\"os\":\"${MATRIX_OS}\",\"formula_count\":${formula_count},\"installed_count\":${installed_count}}"
