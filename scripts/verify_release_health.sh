#!/usr/bin/env bash
# verify_release_health.sh — operationalizes the "Detecting a Broken Release"
# and "Immediate Triage" steps of ../runbooks/formula-rollback.md into a single
# command: fetch every formula and report the last commit that touched it, so
# a triager doesn't have to run `brew fetch`/`git log` by hand for each one.
#
# This is a local safeguard script, not a scheduled job: no exporter, metrics
# backend, or external data flow is added, and it is not wired into CI here
# (adding it to a workflow requires `workflows` permission this script does
# not assume). Run it manually, or from a workflow a maintainer wires up.
#
# Usage: scripts/verify_release_health.sh [formula-name ...]
#   With no arguments, checks every Formula/*.rb in the repo.
#
# Exit status: 0 if every checked formula fetched successfully, 1 otherwise.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FORMULA_DIR="$REPO_ROOT/Formula"

if ! command -v brew >/dev/null 2>&1; then
  echo "verify_release_health.sh: 'brew' is not on PATH — install Homebrew first." >&2
  exit 2
fi

if [ "$#" -gt 0 ]; then
  formulae=("$@")
else
  formulae=()
  for f in "$FORMULA_DIR"/*.rb; do
    formulae+=("$(basename "${f%.rb}")")
  done
fi

overall_status=0

for name in "${formulae[@]}"; do
  path="$FORMULA_DIR/${name}.rb"
  echo "== ${name} =="

  if [ ! -f "$path" ]; then
    echo "  SKIP: no such formula file: $path"
    overall_status=1
    continue
  fi

  last_commit="$(git -C "$REPO_ROOT" log -1 --format='%h %ad %s' --date=short -- "$path" 2>/dev/null)"
  echo "  last commit: ${last_commit:-<unknown>}"

  if brew fetch --formula "$path" >/tmp/verify_release_health.$$.log 2>&1; then
    echo "  fetch: OK"
  else
    echo "  fetch: FAILED (see below)"
    sed 's/^/    /' /tmp/verify_release_health.$$.log
    overall_status=1
  fi
  rm -f /tmp/verify_release_health.$$.log
done

exit "$overall_status"
