#!/usr/bin/env bash
# test_brew_ci_summary_branches.sh — additional branch coverage for
# scripts/brew_ci_summary.sh.
#
# The existing test_brew_ci_summary.sh covers the success/failure job
# statuses, defaults-when-unset, and INSTALLED_FORMULAE=... cases with a
# fixed 2-formula Formula directory. This file targets four independent
# branches of brew_ci_summary.sh that were not previously exercised:
#
#   1. FORMULA_DIR points to a nonexistent path
#        -> outer `if [ -d "$FORMULA_DIR" ]` false on both loops
#        -> formula_count=0, installed_count=0 emitted, script still
#           produces exactly one summary line.
#   2. FORMULA_DIR exists but contains no *.rb files
#        -> the `[ -e "$f" ] || continue` glob-guard branch fires
#        -> formula_count=0.
#   3. No INSTALLED_FORMULAE AND no `brew` on PATH
#        -> installed_list remains empty, but the summary line still
#           emits installed_count=0 without erroring under `set -uo
#           pipefail`.
#   4. INSTALLED_FORMULAE lists a name that isn't in FORMULA_DIR
#        -> the inner `if printf ... | grep -qx "$name"` guard is false
#           for that formula, so installed_count stays 0 even though
#           INSTALLED_FORMULAE is nonempty.
#
# Usage: scripts/test_brew_ci_summary_branches.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/brew_ci_summary.sh"

fail_count=0
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

check_summary() {
  local name="$1" output="$2" exit_code="$3" \
    expected_exit="$4" expected_formula_count="$5" expected_installed_count="$6"

  if ! printf '%s' "$output" | grep -q '^BREW_CI_SUMMARY: {'; then
    echo "FAIL ($name): missing BREW_CI_SUMMARY: line. Got: $output"
    fail_count=$((fail_count + 1))
    return
  fi
  if ! printf '%s' "$output" | grep -q "\"formula_count\":$expected_formula_count"; then
    echo "FAIL ($name): expected formula_count=$expected_formula_count. Got: $output"
    fail_count=$((fail_count + 1))
    return
  fi
  if ! printf '%s' "$output" | grep -q "\"installed_count\":$expected_installed_count"; then
    echo "FAIL ($name): expected installed_count=$expected_installed_count. Got: $output"
    fail_count=$((fail_count + 1))
    return
  fi
  if [ "$exit_code" -ne "$expected_exit" ]; then
    echo "FAIL ($name): expected exit=$expected_exit, got exit=$exit_code"
    fail_count=$((fail_count + 1))
    return
  fi
  # A well-formed run must emit exactly ONE BREW_CI_SUMMARY line, never
  # multiple, regardless of which branches were taken.
  local line_count
  line_count=$(printf '%s' "$output" | grep -c '^BREW_CI_SUMMARY: {')
  if [ "$line_count" -ne 1 ]; then
    echo "FAIL ($name): expected exactly 1 summary line, got $line_count. Full output: $output"
    fail_count=$((fail_count + 1))
    return
  fi
  echo "OK ($name)"
}

# Case 1: FORMULA_DIR path does not exist at all.
missing_dir="$work_dir/does-not-exist"
output=$(FORMULA_DIR="$missing_dir" JOB_STATUS="success" MATRIX_OS="ubuntu-latest" \
  INSTALLED_FORMULAE="" "$SCRIPT" 2>&1)
exit_code=$?
check_summary "missing-FORMULA_DIR" "$output" "$exit_code" 0 0 0

# Case 2: FORMULA_DIR exists but contains no *.rb files.
empty_dir="$work_dir/empty-formula"
mkdir -p "$empty_dir"
output=$(FORMULA_DIR="$empty_dir" JOB_STATUS="success" MATRIX_OS="ubuntu-latest" \
  INSTALLED_FORMULAE="" "$SCRIPT" 2>&1)
exit_code=$?
check_summary "empty-FORMULA_DIR" "$output" "$exit_code" 0 0 0

# Case 3: No INSTALLED_FORMULAE env var AND no brew on PATH. We must
# NOT set INSTALLED_FORMULAE at all so the `[ -n "${INSTALLED_FORMULAE+x}" ]`
# guard is false; we shrink PATH to exclude any real brew.
one_dir="$work_dir/one-formula"
mkdir -p "$one_dir"
printf 'class Foo < Formula\nend\n' > "$one_dir/foo.rb"
output=$(env -i PATH="/usr/bin:/bin" FORMULA_DIR="$one_dir" \
  JOB_STATUS="failure" MATRIX_OS="ubuntu-latest" bash "$SCRIPT" 2>&1)
exit_code=$?
# JOB_STATUS=failure -> expected exit 1. installed_count should be 0
# because brew is not on PATH and INSTALLED_FORMULAE was not set.
check_summary "no-INSTALLED_FORMULAE-no-brew" "$output" "$exit_code" 1 1 0

# Case 4: INSTALLED_FORMULAE names an unrelated formula.
output=$(FORMULA_DIR="$one_dir" JOB_STATUS="success" MATRIX_OS="macos-latest" \
  INSTALLED_FORMULAE="unrelated-package" "$SCRIPT" 2>&1)
exit_code=$?
check_summary "installed-name-mismatch" "$output" "$exit_code" 0 1 0

if [ "$fail_count" -eq 0 ]; then
  echo "All brew_ci_summary.sh branch tests passed."
  exit 0
else
  echo "$fail_count brew_ci_summary.sh branch test(s) failed."
  exit 1
fi
