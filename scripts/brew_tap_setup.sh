#!/usr/bin/env bash
# brew_tap_setup.sh — rewire the pre-registered kubestellar/tap to this
# checkout, extracted from brew-ci.yml's "Set up Homebrew tap" step.
#
# setup-homebrew on Linux pre-registers kubestellar/tap with the remote
# URL. Newer Homebrew also enforces a tap-trust model: tapping a local
# path exits non-zero ("untrusted tap") until `brew trust` is run. This
# script tolerates the tap failure and trusts the tap when supported,
# only hard-failing when trust is unsupported AND the tap itself failed.
#
# Usage: TAP_DIR=/path/to/checkout scripts/brew_tap_setup.sh
#   TAP_DIR  - path to tap into kubestellar/tap (default: current directory)
#   TAP_NAME - tap name to (re)register (default: kubestellar/tap)
#
# Exit status: 0 on success (tap trusted, or tap succeeded without a
# trust concept); 1 if trust is unsupported and the tap itself failed;
# otherwise propagates `brew trust`'s own exit code if that call fails.
#
# Emits one BREW_TAP_SETUP_SUMMARY: {...} line (via scripts/lib_emit_summary.sh)
# before every exit so which internal branch ran — plain success, the
# trust-tolerant path, or the hard failure — is visible in CI logs/step
# summary instead of being silent. Before this, the entire untrusted-tap
# incident (docs/postmortems/2026-08-31-brew-ci-linux-untrusted-tap.md)
# ran for ~16.6 days with no log output from this step distinguishing
# "tap ok" from "tap failed, tolerated" from "hard failure" — its Action
# Items table calls for "a smoke check that fails loudly (rather than
# silently degrading) if tap-registration behavior changes".
#
# Stdout/$GITHUB_STEP_SUMMARY-only structured output: no exporter, metrics
# backend, or off-box data flow is added, and labels are bounded
# (status/tap_result/trust_supported/tap_name only).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib_emit_summary.sh
. "$REPO_ROOT/scripts/lib_emit_summary.sh"

TAP_DIR="${TAP_DIR:-$(pwd)}"
TAP_NAME="${TAP_NAME:-kubestellar/tap}"

brew untap "$TAP_NAME" || true

tap_failed=0
brew tap "$TAP_NAME" "$TAP_DIR" || tap_failed=1
tap_result="clean"
[ "$tap_failed" -ne 0 ] && tap_result="failed-tolerated"

if brew trust --help >/dev/null 2>&1; then
  trust_exit=0
  brew trust "$TAP_NAME" || trust_exit=$?
  if [ "$trust_exit" -ne 0 ]; then
    emit_ci_summary BREW_TAP_SETUP_SUMMARY \
      status=failure tap_result="$tap_result" trust_supported=yes tap_name="$TAP_NAME"
    exit "$trust_exit"
  fi
  emit_ci_summary BREW_TAP_SETUP_SUMMARY \
    status=success tap_result="$tap_result" trust_supported=yes tap_name="$TAP_NAME"
elif [ "$tap_failed" -ne 0 ]; then
  emit_ci_summary BREW_TAP_SETUP_SUMMARY \
    status=failure tap_result="$tap_result" trust_supported=no tap_name="$TAP_NAME"
  exit 1
else
  emit_ci_summary BREW_TAP_SETUP_SUMMARY \
    status=success tap_result="$tap_result" trust_supported=no tap_name="$TAP_NAME"
fi
