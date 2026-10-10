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
#
# Emits one BREW_TEST_INSTALLED_SUMMARY: {...} line (via
# scripts/lib_emit_summary.sh) before every exit path, mirroring the
# structured record its paired brew_install_smoke.sh step now emits.
# Before this, both steps in the brew-audit-and-install job produced zero
# structured output of their own — only the final BREW_CI_SUMMARY:
# job-level installed_count, with no way to tell how many installed
# formulae were actually tested versus skipped as never-installed.
#
# Stdout/$GITHUB_STEP_SUMMARY-only structured output: no exporter,
# metrics backend, or off-box data flow is added, and labels are bounded
# (status/formula_count/tested_count/skipped_count only).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FORMULA_DIR="${FORMULA_DIR:-$REPO_ROOT/Formula}"
TAP_NAME="${TAP_NAME:-kubestellar/tap}"

installed_list="${INSTALLED_FORMULAE-}"
if [ -z "${INSTALLED_FORMULAE+x}" ]; then
  installed_list="$(brew list --formula 2>/dev/null || true)"
fi

# shellcheck source=scripts/lib_formula_iter.sh
. "$REPO_ROOT/scripts/lib_formula_iter.sh"
# shellcheck source=scripts/lib_emit_summary.sh
. "$REPO_ROOT/scripts/lib_emit_summary.sh"

formula_count=0
tested_count=0
skipped_count=0

while IFS= read -r name; do
  formula_count=$((formula_count + 1))
  if ! printf '%s\n' "$installed_list" | grep -qx "$name"; then
    echo "::notice title=Skipping test::$TAP_NAME/$name was not installed"
    skipped_count=$((skipped_count + 1))
    continue
  fi
  echo "::group::brew test $TAP_NAME/$name"
  if brew test "$TAP_NAME/$name"; then
    tested_count=$((tested_count + 1))
  else
    rc=$?
    echo "::endgroup::"
    emit_ci_summary BREW_TEST_INSTALLED_SUMMARY \
      status="failed" formula_count="$formula_count" \
      tested_count="$tested_count" skipped_count="$skipped_count"
    exit "$rc"
  fi
  echo "::endgroup::"
done < <(list_formula_names "$FORMULA_DIR")

emit_ci_summary BREW_TEST_INSTALLED_SUMMARY \
  status="success" formula_count="$formula_count" \
  tested_count="$tested_count" skipped_count="$skipped_count"
