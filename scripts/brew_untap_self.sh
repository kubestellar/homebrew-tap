#!/usr/bin/env bash
# brew_untap_self.sh — untap kubestellar/tap and leave the tap directory
# in the state setup-homebrew's post-job cleanup expects, extracted from
# brew-ci.yml's "Untap self before post-cleanup" step.
#
# This carries three fix-forward postmortems, each folded into the
# sequence below:
#
#   #322 — setup-homebrew's post-job cleanup on Linux does a plain `rm`
#   (not `rm -rf`) on its pre-registered tap directory. Because
#   brew_tap_setup.sh retaps kubestellar/tap to this checkout earlier in
#   the job, that directory still exists (non-empty) at post-job time
#   and the plain `rm` fails with "Is a directory", failing the whole job
#   even though every audit/install/test step above passed. Untapping
#   here removes the directory before Post-"Set up Homebrew on Linux"
#   runs, since GitHub Actions runs post steps only after all regular
#   steps (including this one) complete.
#
#   #426 — `brew untap` refuses to untap a tap that still has formulae
#   installed from it ("Refusing to untap ... because it contains the
#   following installed formulae"), and that refusal was silently
#   swallowed by `|| true`, leaving the tap directory in place for the
#   post-cleanup `rm` to choke on again. Uninstalling anything installed
#   from this tap first (below), then untapping, then falling back to
#   removing the tap directory directly is belt-and-suspenders in case
#   `brew untap` still doesn't fully clean up.
#
#   #486 — setup-homebrew's own `main.sh` originally left a *symlink* at
#   this path (`Taps/kubestellar/homebrew-tap` -> `$GITHUB_WORKSPACE`),
#   and its `post.sh` cleanup unconditionally does
#   `rm "$STATE_TAP_SYMLINK"; mkdir "$STATE_TAP_SYMLINK"; mv ... into it`,
#   expecting that symlink to still be there. Removing the directory
#   outright (the #426 fix) makes that plain `rm` fail with "No such file
#   or directory", failing the whole job even though every step above
#   passed. Recreating the symlink setup-homebrew expects (below) instead
#   of leaving the path empty fixes that.
#
# Usage: GITHUB_WORKSPACE=/path/to/checkout scripts/brew_untap_self.sh
#   FORMULA_DIR      - directory of *.rb formulae (default: <repo root>/Formula)
#   TAP_NAME         - tap name to untap (default: kubestellar/tap)
#   GITHUB_WORKSPACE - checkout path the recreated symlink should point at
#                      (default: current directory)
#
# This step always runs best-effort cleanup (mirroring the workflow's
# `if: always()`): every command that can legitimately fail in a state
# this script tolerates is guarded with `|| true`, so the exit status is
# always 0.
#
# Emits one BREW_UNTAP_SELF_SUMMARY: {...} line (via
# scripts/lib_emit_summary.sh) before exiting, mirroring the structured
# record brew_tap_setup.sh's BREW_TAP_SETUP_SUMMARY: already emits for the
# paired "Set up Homebrew tap" step. Before this, this step produced zero
# log output on any branch — the same silent-degradation gap the
# untrusted-tap postmortem (docs/postmortems/2026-08-31-brew-ci-linux-untrusted-tap.md)
# called out for its setup-side counterpart, except here a reader could
# not even tell whether `brew untap` succeeded, how many formulae were
# uninstalled first, or whether the tap directory needed to be forcibly
# recreated.
#
# Stdout/$GITHUB_STEP_SUMMARY-only structured output: no exporter, metrics
# backend, or off-box data flow is added, and labels are bounded
# (status/untap_result/uninstalled_count/tap_dir_action only).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FORMULA_DIR="${FORMULA_DIR:-$REPO_ROOT/Formula}"
TAP_NAME="${TAP_NAME:-kubestellar/tap}"
GITHUB_WORKSPACE="${GITHUB_WORKSPACE:-$(pwd)}"

# shellcheck source=scripts/lib_formula_iter.sh
. "$REPO_ROOT/scripts/lib_formula_iter.sh"
# shellcheck source=scripts/lib_emit_summary.sh
. "$REPO_ROOT/scripts/lib_emit_summary.sh"

uninstalled_count=0
while IFS= read -r name; do
  if brew uninstall --force --ignore-dependencies "$TAP_NAME/$name" 2>/dev/null; then
    uninstalled_count=$((uninstalled_count + 1))
  fi
done < <(list_formula_names "$FORMULA_DIR")

untap_result="clean"
brew untap "$TAP_NAME" || untap_result="failed-tolerated"

tap_dir_action="none"
tap_dir="$(brew --repo "$TAP_NAME" 2>/dev/null || true)"
if [ -n "$tap_dir" ]; then
  if [ -e "$tap_dir" ] || [ -L "$tap_dir" ]; then
    rm -rf "$tap_dir"
  fi
  mkdir -p "$(dirname "$tap_dir")"
  ln -s "$GITHUB_WORKSPACE" "$tap_dir"
  tap_dir_action="recreated-symlink"
fi

status="success"
[ "$untap_result" = "failed-tolerated" ] && status="degraded"

emit_ci_summary BREW_UNTAP_SELF_SUMMARY \
  status="$status" untap_result="$untap_result" \
  uninstalled_count="$uninstalled_count" tap_dir_action="$tap_dir_action"
