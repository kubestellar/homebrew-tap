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
# trust concept); 1 if trust is unsupported and the tap itself failed.

set -euo pipefail

TAP_DIR="${TAP_DIR:-$(pwd)}"
TAP_NAME="${TAP_NAME:-kubestellar/tap}"

brew untap "$TAP_NAME" || true

tap_failed=0
brew tap "$TAP_NAME" "$TAP_DIR" || tap_failed=1

if brew trust --help >/dev/null 2>&1; then
  brew trust "$TAP_NAME"
elif [ "$tap_failed" -ne 0 ]; then
  exit 1
fi
