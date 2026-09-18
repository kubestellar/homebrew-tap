#!/usr/bin/env bash
# test_verify_pr_title.sh — regression tests for scripts/verify_pr_title.sh.
#
# Covers every branch of the CONVENTIONAL and EMOJI_STYLE regexes the
# script (and, until the workflow is rewired, pr-verifier.yml) uses to
# gate PR titles:
#   - bare Conventional Commits titles
#   - Conventional Commits with an optional (scope)
#   - Conventional Commits with a "!" breaking-change marker
#   - Conventional Commits with an optional [lane] prefix
#   - Conventional Commits with an optional leading emoji
#   - the emoji-only convention with and without a lane prefix
#   - lane in either the outer or inner position of the emoji form
#   - each of the six accepted emoji (✨ 🐛 📖 📝 ⚠️ 🌱, plus the
#     variation-selector-free ⚠)
#   - rejection paths: missing colon, unknown Conventional type, bare
#     lane with no emoji or type, empty title, lane with uppercase, etc.
#   - error path emits the ::error:: annotation and the help block
#     (so a workflow rewired to call this script keeps the same
#     GitHub Actions annotation as today's inlined step)
#   - stdin/argv parity: PR_TITLE env var and $1 both work

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=./test_lib.sh
. "$REPO_ROOT/scripts/test_lib.sh"

SCRIPT="$REPO_ROOT/scripts/verify_pr_title.sh"

run() {
  # run <title> — invoke the script under test with the given PR title
  # via the PR_TITLE env var (the shape pr-verifier.yml uses). Prints
  # combined stdout+stderr and returns the script's exit code.
  PR_TITLE="$1" bash "$SCRIPT" 2>&1
}

assert_accept() {
  # assert_accept <case-name> <title>
  local name="$1" title="$2"
  local out rc
  out="$(run "$title")"
  rc=$?
  assert_exit_code "$name" 0 "$rc"
  assert_contains "$name" "$out" "PR title is valid"
}

assert_reject() {
  # assert_reject <case-name> <title>
  local name="$1" title="$2"
  local out rc
  out="$(run "$title")"
  rc=$?
  assert_exit_code "$name" 1 "$rc"
  assert_contains "$name" "$out" "::error::"
  assert_contains "$name" "$out" "Allowed types:"
}

# -----------------------------------------------------------------------
# Conventional Commits — happy paths
# -----------------------------------------------------------------------
assert_accept "cc-bare"          "fix: correct typo"
assert_accept "cc-scope"         "feat(scope): add feature"
assert_accept "cc-breaking"      "feat(scope)!: breaking"
assert_accept "cc-scope-no-bang" "refactor(agents): drop dead branch"
assert_accept "cc-docs"          "docs: refresh SLO doc"
assert_accept "cc-chore"         "chore: dependency bump"
assert_accept "cc-perf"          "perf: shave 20ms"
assert_accept "cc-revert"        "revert: back out c0ffee1"
assert_accept "cc-lane"          "[operations] docs: refresh SLO doc"
assert_accept "cc-lane-scope"    "[scanner] refactor(ci): dedupe step"
assert_accept "cc-lane-emoji"    "🌱 [scanner] ci: coverage for validate-formulae"
assert_accept "cc-leading-emoji" "🐛 fix: repair broken tap"
assert_accept "cc-emoji-warn-vs" "⚠️ [operations] feat: breaking API change"
assert_accept "cc-emoji-warn-no" "⚠ [operations] feat: breaking API change"

# -----------------------------------------------------------------------
# Emoji convention — happy paths (with and without lanes)
# -----------------------------------------------------------------------
assert_accept "emoji-bare-seed"   "🌱 Document the release-sync gap"
assert_accept "emoji-bare-book"   "📖 Document the release-sync gap"
assert_accept "emoji-bare-memo"   "📝 Propose the release-sync doc"
assert_accept "emoji-bare-spark"  "✨ new tap formula"
assert_accept "emoji-bare-bug"    "🐛 tap symlink race"
assert_accept "emoji-outer-lane"  "[scanner] 🌱 ci: coverage for validate-formulae"
assert_accept "emoji-inner-lane"  "🌱 [scanner] ci: coverage for validate-formulae"

# -----------------------------------------------------------------------
# Rejections
# -----------------------------------------------------------------------
assert_reject "rej-no-prefix"         "no colon here"
assert_reject "rej-unknown-type"      "random: not a real type"
assert_reject "rej-empty"             ""
assert_reject "rej-cc-empty-subject"  "chore: "
assert_reject "rej-random-words"      "foo bar baz"
assert_reject "rej-bare-lane"         "[scanner] plain sentence"
assert_reject "rej-uppercase-lane"    "[Scanner] fix: uppercase lane"
assert_reject "rej-wrong-emoji"       "🎉 party: not an accepted emoji"
assert_reject "rej-cc-missing-space"  "fix:notypo"
# Verify the emoji-form REJECTS a bare lane with no emoji and no type —
# guards against a regex rewrite that would let "[lane] anything" through.
assert_reject "rej-lane-only"         "[quality] no gate at all"

# -----------------------------------------------------------------------
# Interface parity: $1 must work equivalently to PR_TITLE.
# -----------------------------------------------------------------------
argv_accept_out="$(bash "$SCRIPT" "fix: correct typo" 2>&1)"
argv_accept_rc=$?
assert_exit_code "argv-accept" 0 "$argv_accept_rc"
assert_contains "argv-accept" "$argv_accept_out" "PR title is valid"

argv_reject_out="$(bash "$SCRIPT" "not a valid title" 2>&1)"
argv_reject_rc=$?
assert_exit_code "argv-reject" 1 "$argv_reject_rc"
assert_contains "argv-reject" "$argv_reject_out" "::error::"

# -----------------------------------------------------------------------
# Help-block shape: preserve the exact top annotation so a workflow
# rewired to call this script keeps producing the identical GitHub
# Actions error annotation seen today from the inline step.
# -----------------------------------------------------------------------
reject_out="$(run "no prefix")"
assert_contains "help-block-annotation" "$reject_out" \
  "::error::PR title must use Conventional Commits or the KubeStellar emoji prefix."
assert_contains "help-block-examples"   "$reject_out" "feat(scope): add feature"
assert_contains "help-block-emoji-list" "$reject_out" \
  "Allowed emoji: ✨ feature | 🐛 fix | 📖 docs | 📝 proposal | ⚠️ breaking | 🌱 other"

finish "test_verify_pr_title.sh"
