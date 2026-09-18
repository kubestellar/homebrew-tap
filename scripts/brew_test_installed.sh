#!/usr/bin/env bash
# brew_test_installed.sh — run `brew test` against every formula that was
# actually installed, extracted from brew-ci.yml's "brew test (installed
# formulae)" step.
#
# A formula that was skipped by brew_install_smoke.sh (e.g. its release
# artifact wasn't available on a pull_request event) won't be in `brew
# list --formula`, so it is skipped here too with an `::notice::` rather
# than failing on a formula that was never installed.
#
# Usage: scripts/brew_test_installed.sh
#   FORMULA_DIR - directory of *.rb formulae (default: <repo root>/Formula)
#   TAP_NAME    - tap prefix passed to `brew test` (default: kubestellar/tap)
#   INSTALLED_FORMULAE - newline-separated list of installed formula names,
#                        used instead of querying `brew list --formula`
#                        (used by tests, or by callers without `brew` on
#                        PATH).
#
# Exit status: 0 if every installed formula's `brew test` passes (absent
# formulae are skipped, not failed); otherwise the exit code of the first
# failing `brew test` call.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FORMULA_DIR="${FORMULA_DIR:-$REPO_ROOT/Formula}"
TAP_NAME="${TAP_NAME:-kubestellar/tap}"

installed_list="${INSTALLED_FORMULAE-}"
if [ -z "${INSTALLED_FORMULAE+x}" ]; then
  installed_list="$(brew list --formula 2>/dev/null || true)"
fi

for formula in "$FORMULA_DIR"/*.rb; do
  [ -e "$formula" ] || continue
  name="$(basename "$formula" .rb)"
  if ! printf '%s\n' "$installed_list" | grep -qx "$name"; then
    echo "::notice title=Skipping test::$TAP_NAME/$name was not installed"
    continue
  fi
  echo "::group::brew test $TAP_NAME/$name"
  if brew test "$TAP_NAME/$name"; then
    :
  else
    rc=$?
    echo "::endgroup::"
    exit "$rc"
  fi
  echo "::endgroup::"
done
