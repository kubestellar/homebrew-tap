#!/usr/bin/env bash
# brew_install_smoke.sh — `brew fetch` + `brew install` smoke test for
# every formula, extracted from brew-ci.yml's "brew install smoke test
# (available formulae)" step.
#
# A `brew fetch` failure means the formula's release artifact is not
# available yet. On a `pull_request` event that is tolerated (the
# artifact for an in-flight PR may not have been published): the formula
# is skipped with an `::notice::` and the loop continues. On any other
# event (push, schedule, workflow_dispatch) a missing artifact is a hard
# failure: an `::error::` is emitted and the script exits 1 immediately,
# matching the run-step's original `bash -e`-free `exit 1`.
#
# Usage: EVENT_NAME=push scripts/brew_install_smoke.sh
#   EVENT_NAME  - ${{ github.event_name }} (default: push, the strict path)
#   FORMULA_DIR - directory of *.rb formulae (default: <repo root>/Formula)
#   TAP_NAME    - tap prefix passed to brew (default: kubestellar/tap)
#
# Exit status: 0 if every formula fetched (and installed) or was
# skippably absent on a pull_request event; 1 if a fetch failed outside
# a pull_request event, or if `brew install` itself failed.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FORMULA_DIR="${FORMULA_DIR:-$REPO_ROOT/Formula}"
TAP_NAME="${TAP_NAME:-kubestellar/tap}"
EVENT_NAME="${EVENT_NAME:-push}"

for formula in "$FORMULA_DIR"/*.rb; do
  [ -e "$formula" ] || continue
  name="$(basename "$formula" .rb)"
  echo "::group::brew fetch $TAP_NAME/$name"
  if brew fetch --formula "$TAP_NAME/$name"; then
    echo "::endgroup::"
    echo "::group::brew install $TAP_NAME/$name"
    if brew install --formula "$TAP_NAME/$name"; then
      :
    else
      rc=$?
      echo "::endgroup::"
      exit "$rc"
    fi
  else
    echo "::endgroup::"
    if [ "$EVENT_NAME" = "pull_request" ]; then
      echo "::notice title=Skipping install::Release artifact for $TAP_NAME/$name is not available yet"
      continue
    fi
    echo "::error title=Missing release artifact::$TAP_NAME/$name could not be fetched"
    exit 1
  fi
  echo "::endgroup::"
done
