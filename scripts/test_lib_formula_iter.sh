#!/usr/bin/env bash
# test_lib_formula_iter.sh — regression tests for scripts/lib_formula_iter.sh.
#
# lib_formula_iter.sh centralizes the formula-stem walk shared by
# brew_audit_all.sh, brew_install_smoke.sh, brew_test_installed.sh, and
# brew_untap_self.sh (kubestellar/homebrew-tap#681), but none of those
# four callers' own test files exercise list_formula_names() directly —
# they only assert on each caller script's higher-level behavior with a
# fixed Formula/ fixture. This file closes that gap by sourcing
# lib_formula_iter.sh and calling list_formula_names() in isolation,
# covering: multiple .rb files, non-.rb files mixed in, an empty
# directory (the `[ -e ]` unexpanded-glob guard), and a nonexistent
# directory (same guard, since the glob simply never matches).
#
# Usage: scripts/test_lib_formula_iter.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

# shellcheck source=scripts/test_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test_lib.sh"

REPO_ROOT="$(repo_root)"
LIB="$REPO_ROOT/scripts/lib_formula_iter.sh"

# shellcheck source=scripts/lib_formula_iter.sh
source "$LIB"

make_work_dir

# --- Case 1: multiple .rb files yield one stem per line, sorted by the
# underlying glob's lexical order ---
dir1="$work_dir/case1"
make_fake_formulae "$dir1" kc-agent kubestellar-deploy kubestellar-ops
got="$(list_formula_names "$dir1")"
expected=$'kc-agent\nkubestellar-deploy\nkubestellar-ops'
if [ "$got" != "$expected" ]; then
  fail "multi-stems" "expected '$expected', got '$got'"
fi

# --- Case 2: non-.rb files in the same directory are ignored ---
dir2="$work_dir/case2"
make_fake_formulae "$dir2" kc-agent
printf 'not a formula\n' > "$dir2/README.md"
: > "$dir2/kc-agent.rb.bak"
got="$(list_formula_names "$dir2")"
if [ "$got" != "kc-agent" ]; then
  fail "ignores-non-rb" "expected only 'kc-agent', got '$got'"
fi

# --- Case 3: an empty directory (no *.rb files) produces no output,
# guarded by `[ -e ]` against the literal unexpanded glob pattern ---
dir3="$work_dir/case3-empty"
mkdir -p "$dir3"
got="$(list_formula_names "$dir3")"
if [ -n "$got" ]; then
  fail "empty-dir" "expected no output for an empty directory, got '$got'"
fi

# --- Case 4: a nonexistent directory also produces no output rather
# than an error (same unexpanded-glob guard) ---
dir4="$work_dir/does-not-exist"
out="$(list_formula_names "$dir4" 2>&1)"
rc=$?
assert_exit_code "missing-dir-exit" 0 "$rc"
if [ -n "$out" ]; then
  fail "missing-dir-output" "expected no output for a missing directory, got '$out'"
fi

# --- Case 5: a single formula round-trips through basename stripping
# exactly (no partial match on an embedded '.rb') ---
dir5="$work_dir/case5"
make_fake_formulae "$dir5" "foo.rb-looking"
got="$(list_formula_names "$dir5")"
if [ "$got" != "foo.rb-looking" ]; then
  fail "dotted-stem" "expected 'foo.rb-looking', got '$got'"
fi

finish "lib_formula_iter.sh"
