#!/usr/bin/env bash
# brew_audit_all.sh — run `brew audit --strict` against every formula,
# extracted from brew-ci.yml's "brew audit --strict (all formulae)" step.
#
# Matches the run-step's original semantics under GitHub Actions' default
# `bash -e` behavior for `run:` blocks: a genuine failure stops the loop
# and this script exits with the failing formula's own exit code as soon
# as one `brew audit` call fails, without printing that formula's
# `::endgroup::` marker or auditing any later formula.
#
# Known false positive (see issue #513): every stable (non-nightly)
# version bump trips Homebrew's `redundant_version` strict-audit rule
# ("`version X.Y.Z` is redundant with version scanned from URL"), because
# GoReleaser's `brews` template always writes an explicit `version` line
# even though it is inferable from the tag in the download URL. When that
# is the *only* problem `brew audit --strict` reports for a formula, it is
# treated as non-fatal here (logged as an `::warning::` instead) so the
# audit stays strict for every other regression class. Any other finding
# — alone or alongside the redundant-version one — still fails the script.
#
# Usage: scripts/brew_audit_all.sh
#   FORMULA_DIR - directory of *.rb formulae (default: <repo root>/Formula)
#   TAP_NAME    - tap prefix passed to `brew audit` (default: kubestellar/tap)
#
# Exit status: 0 if every formula audits clean or only trips the known
# redundant-version false positive; otherwise the exit code of the first
# failing `brew audit --strict` call.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FORMULA_DIR="${FORMULA_DIR:-$REPO_ROOT/Formula}"
TAP_NAME="${TAP_NAME:-kubestellar/tap}"

# Matches brew audit --strict's `* ` problem-line bullets, e.g.:
#   * Stable: `version 0.9.15` is redundant with version scanned from URL
REDUNDANT_VERSION_PATTERN='is redundant with version scanned from URL'

for formula in "$FORMULA_DIR"/*.rb; do
  [ -e "$formula" ] || continue
  name="$(basename "$formula" .rb)"
  echo "::group::brew audit --strict $TAP_NAME/$name"

  output="$(brew audit --strict "$TAP_NAME/$name" 2>&1)"
  exit_code=$?
  printf '%s\n' "$output"

  if [ "$exit_code" -eq 0 ]; then
    echo "::endgroup::"
    continue
  fi

  problem_lines="$(printf '%s\n' "$output" | grep -c '^\s*\*\s')"
  if [ "$problem_lines" -eq 1 ] \
    && printf '%s\n' "$output" | grep -q "$REDUNDANT_VERSION_PATTERN"; then
    echo "::warning::$TAP_NAME/$name: ignoring known redundant_version false positive (see issue #513)"
    echo "::endgroup::"
    continue
  fi

  exit "$exit_code"
done
