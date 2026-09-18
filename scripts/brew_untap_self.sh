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

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FORMULA_DIR="${FORMULA_DIR:-$REPO_ROOT/Formula}"
TAP_NAME="${TAP_NAME:-kubestellar/tap}"
GITHUB_WORKSPACE="${GITHUB_WORKSPACE:-$(pwd)}"

for formula in "$FORMULA_DIR"/*.rb; do
  [ -e "$formula" ] || continue
  name="$(basename "$formula" .rb)"
  brew uninstall --force --ignore-dependencies "$TAP_NAME/$name" 2>/dev/null || true
done

brew untap "$TAP_NAME" || true

tap_dir="$(brew --repo "$TAP_NAME" 2>/dev/null || true)"
if [ -n "$tap_dir" ]; then
  if [ -e "$tap_dir" ] || [ -L "$tap_dir" ]; then
    rm -rf "$tap_dir"
  fi
  mkdir -p "$(dirname "$tap_dir")"
  ln -s "$GITHUB_WORKSPACE" "$tap_dir"
fi
