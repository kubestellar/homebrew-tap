#!/usr/bin/env bash
# brew_audit_all.sh — run `brew audit --strict` against every formula,
# extracted from brew-ci.yml's "brew audit --strict (all formulae)" step.
#
# Matches the run-step's original semantics under GitHub Actions' default
# `bash -e` behavior for `run:` blocks: `set -e` here means the loop stops
# and this script exits with the failing formula's own exit code as soon
# as one `brew audit` call fails, without printing that formula's
# `::endgroup::` marker or auditing any later formula.
#
# Usage: scripts/brew_audit_all.sh
#   FORMULA_DIR - directory of *.rb formulae (default: <repo root>/Formula)
#   TAP_NAME    - tap prefix passed to `brew audit` (default: kubestellar/tap)
#
# Exit status: 0 if every formula audits clean; otherwise the exit code
# of the first failing `brew audit --strict` call.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FORMULA_DIR="${FORMULA_DIR:-$REPO_ROOT/Formula}"
TAP_NAME="${TAP_NAME:-kubestellar/tap}"

for formula in "$FORMULA_DIR"/*.rb; do
  [ -e "$formula" ] || continue
  name="$(basename "$formula" .rb)"
  echo "::group::brew audit --strict $TAP_NAME/$name"
  brew audit --strict "$TAP_NAME/$name"
  echo "::endgroup::"
done
