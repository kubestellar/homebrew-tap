#!/usr/bin/env bash
# test_test_lib.sh — regression tests for scripts/test_lib.sh.
#
# scripts/test_lib.sh is the shared scaffolding sourced by every
# scripts/test_*.sh shell test in this repository (see the file's own
# banner). A regression in any of its helpers — e.g. assert_grep
# silently returning 0 when the haystack does not match, or
# make_fake_formulae writing a class name with a lower-cased first
# letter — would false-pass every downstream test that depends on it,
# because those tests trust the helpers to fail loudly on mismatch.
# That is the same "guard the guard" motivation .coveragerc already
# applies to scripts/coverage_gate.py: a silent regression in the
# scaffolding invalidates every gate the scaffolding is used to enforce.
#
# This test file exercises each exported helper in test_lib.sh in a
# clean sub-shell so its own $fail_count accumulator, exit path, and
# EXIT trap cannot leak into this driver. Assertions here are written
# with plain `[ ]` tests and a local counter — NOT with the helpers
# under test — so a regression in the helpers cannot silently pass
# this file.
#
# Usage: scripts/test_test_lib.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/test_lib.sh"

if [ ! -f "$LIB" ]; then
  echo "FAIL: $LIB not found"
  exit 1
fi

driver_fail_count=0

# note <name> <message> — record a failure without using test_lib.sh.
note() {
  local name="$1" message="$2"
  echo "FAIL ($name): $message"
  driver_fail_count=$((driver_fail_count + 1))
}

# run_snippet <bash-snippet> — execute <bash-snippet> in a fresh
# sub-shell after sourcing test_lib.sh, capturing stdout+stderr in
# $out and the exit code in $rc. Uses `set +e` inside so a helper
# that legitimately returns non-zero (fail/assert_* on mismatch) does
# not abort the sub-shell before we can inspect the output.
run_snippet() {
  local snippet="$1"
  local tmp
  tmp="$(mktemp)"
  bash -c "set +e; source '$LIB'; $snippet" >"$tmp" 2>&1
  rc=$?
  out="$(cat "$tmp")"
  rm -f "$tmp"
}

# ------------------------------------------------------------------
# repo_root
# ------------------------------------------------------------------
# Called from a script inside scripts/, repo_root must resolve to the
# directory containing scripts/ (i.e. the repo root), not to scripts/
# itself. Regression here would give every downstream test a wrong
# REPO_ROOT and cause silent path miss-resolution.
expected_root="$(cd "$SCRIPT_DIR/.." && pwd)"
run_snippet 'cd "'"$SCRIPT_DIR"'" && printf "%s" "$(repo_root)"'
if [ "$rc" -ne 0 ]; then
  note "repo_root/exit" "expected 0 exit, got $rc; output: $out"
fi
if [ "$out" != "$expected_root" ]; then
  note "repo_root/value" "expected '$expected_root', got '$out'"
fi

# ------------------------------------------------------------------
# make_work_dir
# ------------------------------------------------------------------
# Must create a directory, assign it to $work_dir, and register an EXIT
# trap that removes it on shell exit.
run_snippet 'make_work_dir; [ -d "$work_dir" ] && printf "%s" "$work_dir"'
if [ "$rc" -ne 0 ]; then
  note "make_work_dir/exit" "expected 0 exit, got $rc; output: $out"
fi
if [ -z "$out" ]; then
  note "make_work_dir/set" "\$work_dir not set or directory not created"
fi
if [ -n "$out" ] && [ -d "$out" ]; then
  note "make_work_dir/cleanup" "sub-shell EXIT trap did not remove $out"
fi

# ------------------------------------------------------------------
# make_fake_formulae — class name upper-cases first letter only
# ------------------------------------------------------------------
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
run_snippet 'make_fake_formulae "'"$work"'" foo barBaz'
if [ "$rc" -ne 0 ]; then
  note "make_fake_formulae/exit" "expected 0 exit, got $rc; output: $out"
fi
if [ ! -f "$work/foo.rb" ]; then
  note "make_fake_formulae/foo" "foo.rb not written under $work"
elif ! grep -q '^class Foo < Formula$' "$work/foo.rb"; then
  note "make_fake_formulae/foo-class" "expected 'class Foo < Formula' in foo.rb, got: $(cat "$work/foo.rb")"
fi
if [ ! -f "$work/barBaz.rb" ]; then
  note "make_fake_formulae/barBaz" "barBaz.rb not written under $work"
elif ! grep -q '^class BarBaz < Formula$' "$work/barBaz.rb"; then
  # Regression guard for the contract "first letter upper-cased,
  # remainder preserved" — a naive `${name^}` or `tr` over the whole
  # name would corrupt camelCase formula names.
  note "make_fake_formulae/barBaz-class" "expected 'class BarBaz < Formula' in barBaz.rb, got: $(cat "$work/barBaz.rb")"
fi

# ------------------------------------------------------------------
# fail — prints FAIL line and increments $fail_count
# ------------------------------------------------------------------
run_snippet 'fail_count=0; fail case-a "boom"; printf "\nfail_count=%s" "$fail_count"'
case "$out" in
  *"FAIL (case-a): boom"*"fail_count=1"*) ;;
  *) note "fail/output" "expected FAIL line and fail_count=1, got: $out" ;;
esac

# ------------------------------------------------------------------
# assert_grep — pass path (regex match) and fail path (mismatch)
# ------------------------------------------------------------------
run_snippet 'fail_count=0; assert_grep case-a "hello world" "wor" "msg"; echo "rc=$?"; echo "fc=$fail_count"'
case "$out" in
  *"rc=0"*"fc=0"*) ;;
  *) note "assert_grep/pass" "expected rc=0 fc=0 on match, got: $out" ;;
esac
if printf '%s' "$out" | grep -q "FAIL"; then
  note "assert_grep/pass-no-fail" "assert_grep printed FAIL on a successful match: $out"
fi

run_snippet 'fail_count=0; assert_grep case-b "hello world" "zzz" "should-see-msg"; echo "rc=$?"; echo "fc=$fail_count"'
case "$out" in
  *"FAIL (case-b): should-see-msg"*"rc=1"*"fc=1"*) ;;
  *) note "assert_grep/fail" "expected FAIL line + rc=1 + fc=1 on mismatch, got: $out" ;;
esac

# ------------------------------------------------------------------
# assert_contains — literal substring match
# ------------------------------------------------------------------
# Pass path must NOT print FAIL and must return 0 without incrementing.
run_snippet 'fail_count=0; assert_contains case-a "abc.def" "c.d"; echo "rc=$?"; echo "fc=$fail_count"'
case "$out" in
  *"rc=0"*"fc=0"*) ;;
  *) note "assert_contains/pass" "expected rc=0 fc=0 on literal match, got: $out" ;;
esac
if printf '%s' "$out" | grep -q "FAIL"; then
  note "assert_contains/pass-no-fail" "assert_contains printed FAIL on a successful match: $out"
fi

# Fail path must dump the haystack between "--- output ---" fences and
# increment fail_count. Also guards that assert_contains is LITERAL:
# passing a regex-meaningful needle that is not a literal substring
# must be treated as a mismatch. A regression to `grep -q` (regex)
# would false-pass this by matching '.' as any char.
run_snippet 'fail_count=0; assert_contains case-b "abcdef" "c.d"; echo "rc=$?"; echo "fc=$fail_count"'
case "$out" in
  *"FAIL (case-b): expected output to contain: c.d"*"--- output ---"*"abcdef"*"--------------"*"rc=1"*"fc=1"*) ;;
  *) note "assert_contains/fail-literal" "expected literal-mismatch FAIL with dump on 'c.d' vs 'abcdef', got: $out" ;;
esac

# ------------------------------------------------------------------
# assert_not_contains — inverse of assert_contains
# ------------------------------------------------------------------
run_snippet 'fail_count=0; assert_not_contains case-a "abcdef" "zzz"; echo "rc=$?"; echo "fc=$fail_count"'
case "$out" in
  *"rc=0"*"fc=0"*) ;;
  *) note "assert_not_contains/pass" "expected rc=0 fc=0 when needle absent, got: $out" ;;
esac
if printf '%s' "$out" | grep -q "FAIL"; then
  note "assert_not_contains/pass-no-fail" "assert_not_contains printed FAIL when needle absent: $out"
fi

run_snippet 'fail_count=0; assert_not_contains case-b "abcdef" "cde"; echo "rc=$?"; echo "fc=$fail_count"'
case "$out" in
  *"FAIL (case-b): expected output to NOT contain: cde"*"--- output ---"*"abcdef"*"--------------"*"rc=1"*"fc=1"*) ;;
  *) note "assert_not_contains/fail" "expected FAIL with dump when needle present, got: $out" ;;
esac

# ------------------------------------------------------------------
# assert_exit_code — argument order is (expected, actual)
# ------------------------------------------------------------------
run_snippet 'fail_count=0; assert_exit_code case-a 0 0; echo "rc=$?"; echo "fc=$fail_count"'
case "$out" in
  *"rc=0"*"fc=0"*) ;;
  *) note "assert_exit_code/pass" "expected rc=0 fc=0 on equal codes, got: $out" ;;
esac

# Guard the (expected, actual) argument order documented in test_lib.sh:
# an accidental swap would silently invert every workflow_failure_notify
# test's exit-code contract. Passing expected=2 actual=7 must FAIL and
# the FAIL line must read "expected 2, got 7" (not the reverse).
run_snippet 'fail_count=0; assert_exit_code case-b 2 7; echo "rc=$?"; echo "fc=$fail_count"'
case "$out" in
  *"FAIL (case-b): expected exit 2, got 7"*"rc=1"*"fc=1"*) ;;
  *) note "assert_exit_code/fail-order" "expected 'expected exit 2, got 7' FAIL line, got: $out" ;;
esac

# ------------------------------------------------------------------
# assert_exit — argument order is (actual, expected, message)
# ------------------------------------------------------------------
# Note: assert_exit predates assert_exit_code and uses the INVERSE
# argument order. Regressing to a common order would break the
# 20+ existing call sites; guard it explicitly.
run_snippet 'fail_count=0; assert_exit case-a 3 3 "msg"; echo "rc=$?"; echo "fc=$fail_count"'
case "$out" in
  *"rc=0"*"fc=0"*) ;;
  *) note "assert_exit/pass" "expected rc=0 fc=0 on equal codes, got: $out" ;;
esac

run_snippet 'fail_count=0; assert_exit case-b 4 5 "wrong-exit"; echo "rc=$?"; echo "fc=$fail_count"'
case "$out" in
  *"FAIL (case-b): wrong-exit"*"rc=1"*"fc=1"*) ;;
  *) note "assert_exit/fail" "expected FAIL with 'wrong-exit' message, got: $out" ;;
esac

# ------------------------------------------------------------------
# finish — exit 0 on fail_count=0, exit 1 otherwise
# ------------------------------------------------------------------
run_snippet 'fail_count=0; finish widget'
if [ "$rc" -ne 0 ]; then
  note "finish/pass-exit" "expected exit 0 when fail_count=0, got $rc"
fi
case "$out" in
  *"All widget tests passed."*) ;;
  *) note "finish/pass-line" "expected 'All widget tests passed.' line, got: $out" ;;
esac

run_snippet 'fail_count=2; finish widget'
if [ "$rc" -ne 1 ]; then
  note "finish/fail-exit" "expected exit 1 when fail_count>0, got $rc"
fi
case "$out" in
  *"2 widget test(s) failed."*) ;;
  *) note "finish/fail-line" "expected '2 widget test(s) failed.' line, got: $out" ;;
esac

# ------------------------------------------------------------------
# summary
# ------------------------------------------------------------------
if [ "$driver_fail_count" -eq 0 ]; then
  echo "All test_lib.sh tests passed."
  exit 0
else
  echo "$driver_fail_count test_lib.sh test(s) failed."
  exit 1
fi
