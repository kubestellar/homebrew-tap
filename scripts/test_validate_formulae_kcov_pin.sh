#!/usr/bin/env bash
# test_validate_formulae_kcov_pin.sh — regression test asserting that
# validate-formulae.yml's "Install kcov" step fetches kcov by an
# immutable 40-hex-char commit SHA, not a mutable tag/branch name.
#
# Every other external artifact this repo's CI fetches is pinned by
# digest: GitHub Actions `uses:` refs by commit SHA, and
# requirements-dev.txt's pip wheels by --require-hashes (see that file's
# header). A `git clone --branch v43 ...` is the one exception — a git
# tag can be force-moved by the upstream maintainer (or an attacker who
# compromises their account) to point at different, potentially
# malicious source, which this step then builds and installs with sudo.
# This test fails if that step ever regresses back to cloning by a
# non-SHA ref.
#
# Usage: scripts/test_validate_formulae_kcov_pin.sh
# Exit status: 0 if the kcov clone is pinned to a commit SHA, 1 otherwise.

set -uo pipefail

# shellcheck source=scripts/test_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test_lib.sh"

REPO_ROOT="$(repo_root)"
WORKFLOW="$REPO_ROOT/.github/workflows/validate-formulae.yml"

if [[ ! -f "$WORKFLOW" ]]; then
  fail "workflow-exists" "$WORKFLOW not found"
  finish "validate_formulae_kcov_pin"
fi

kcov_clone_line="$(grep -E 'git clone .*SimonKagstrom/kcov\.git' "$WORKFLOW" || true)"

if [[ -z "$kcov_clone_line" ]]; then
  fail "kcov-clone-present" "no 'git clone ... SimonKagstrom/kcov.git' line found in $WORKFLOW"
elif grep -qF -- "--branch" <<<"$kcov_clone_line"; then
  fail "no-branch-flag" "kcov clone still uses a mutable --branch ref: $kcov_clone_line"
else
  echo "kcov clone has no --branch flag: $kcov_clone_line"
fi

# The checkout immediately following the clone (same heredoc step) must
# reference a full 40-hex-char commit SHA, matching the one `git clone`
# fetches via `fetch --depth 1 origin <sha>`.
fetch_line="$(grep -E 'fetch --depth 1 origin [0-9a-f]{40}' "$WORKFLOW" || true)"
if [[ -z "$fetch_line" ]]; then
  fail "kcov-pinned-to-sha" "expected a 'fetch --depth 1 origin <40-hex-char-sha>' line pinning kcov in $WORKFLOW"
else
  echo "found pinned kcov fetch: $fetch_line"
fi

finish "validate_formulae_kcov_pin"
