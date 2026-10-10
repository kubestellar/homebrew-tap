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
#
# Emits one BREW_INSTALL_SMOKE_SUMMARY: {...} line (via
# scripts/lib_emit_summary.sh) before every exit path, mirroring the
# structured record brew_tap_setup.sh/brew_untap_self.sh already emit for
# their steps in the same brew-ci.yml job. Before this, this step (and
# its paired brew_test_installed.sh) were the only two steps in the
# brew-audit-and-install job with zero per-step structured output — a
# reader could see the final BREW_CI_SUMMARY: installed_count, but not
# how many formulae were skipped (pull_request-only) versus attempted.
#
# Stdout/$GITHUB_STEP_SUMMARY-only structured output: no exporter,
# metrics backend, or off-box data flow is added, and labels are bounded
# (status/formula_count/installed_count/skipped_count only).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FORMULA_DIR="${FORMULA_DIR:-$REPO_ROOT/Formula}"
TAP_NAME="${TAP_NAME:-kubestellar/tap}"
EVENT_NAME="${EVENT_NAME:-push}"

# shellcheck source=scripts/lib_formula_iter.sh
. "$REPO_ROOT/scripts/lib_formula_iter.sh"
# shellcheck source=scripts/lib_emit_summary.sh
. "$REPO_ROOT/scripts/lib_emit_summary.sh"

formula_count=0
installed_count=0
skipped_count=0

while IFS= read -r name; do
  formula_count=$((formula_count + 1))
  echo "::group::brew fetch $TAP_NAME/$name"
  if brew fetch --formula "$TAP_NAME/$name"; then
    echo "::endgroup::"
    echo "::group::brew install $TAP_NAME/$name"
    if brew install --formula "$TAP_NAME/$name"; then
      installed_count=$((installed_count + 1))
    else
      rc=$?
      echo "::endgroup::"
      emit_ci_summary BREW_INSTALL_SMOKE_SUMMARY \
        status="failed" formula_count="$formula_count" \
        installed_count="$installed_count" skipped_count="$skipped_count"
      exit "$rc"
    fi
  else
    echo "::endgroup::"
    if [ "$EVENT_NAME" = "pull_request" ]; then
      echo "::notice title=Skipping install::Release artifact for $TAP_NAME/$name is not available yet"
      skipped_count=$((skipped_count + 1))
      continue
    fi
    emit_ci_summary BREW_INSTALL_SMOKE_SUMMARY \
      status="failed" formula_count="$formula_count" \
      installed_count="$installed_count" skipped_count="$skipped_count"
    echo "::error title=Missing release artifact::$TAP_NAME/$name could not be fetched"
    exit 1
  fi
  echo "::endgroup::"
done < <(list_formula_names "$FORMULA_DIR")

emit_ci_summary BREW_INSTALL_SMOKE_SUMMARY \
  status="success" formula_count="$formula_count" \
  installed_count="$installed_count" skipped_count="$skipped_count"
