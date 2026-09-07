#!/usr/bin/env bash
# test_unittest_summary.sh — regression tests for scripts/unittest_summary.sh.
#
# Guards against the summary line silently losing its stdout-only,
# always-emitted contract: an all-pass run, an all-fail run, and a mixed
# failures+errors run must each still produce exactly one UNITTEST_SUMMARY:
# JSON line with the correct counts, and the wrapper's own exit status must
# mirror unittest discover's exit status.
#
# Usage: scripts/test_unittest_summary.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/unittest_summary.sh"

fail_count=0
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

write_fixture() {
  # $1 = subdir name, $2 = test file body
  local dir="$work_dir/$1"
  mkdir -p "$dir"
  printf '%s' "$2" > "$dir/test_fixture.py"
}

assert_case() {
  local name="$1" subdir="$2" expected_status="$3" expected_exit="$4" expected_tests="$5"
  local output exit_code

  output=$("$SCRIPT" -s "$work_dir/$subdir" -p 'test_*.py' 2>&1)
  exit_code=$?

  if ! printf '%s' "$output" | grep -q '^UNITTEST_SUMMARY: {'; then
    echo "FAIL ($name): missing UNITTEST_SUMMARY: line. Got: $output"
    fail_count=$((fail_count + 1))
    return
  fi
  if ! printf '%s' "$output" | grep -q "\"status\":\"$expected_status\""; then
    echo "FAIL ($name): expected status=$expected_status. Got: $output"
    fail_count=$((fail_count + 1))
    return
  fi
  if ! printf '%s' "$output" | grep -q "\"tests_run\":$expected_tests"; then
    echo "FAIL ($name): expected tests_run=$expected_tests. Got: $output"
    fail_count=$((fail_count + 1))
    return
  fi
  if [ "$exit_code" -ne "$expected_exit" ]; then
    echo "FAIL ($name): expected exit=$expected_exit, got exit=$exit_code"
    fail_count=$((fail_count + 1))
    return
  fi
  echo "OK ($name)"
}

write_fixture "all_pass" '
import unittest
class T(unittest.TestCase):
    def test_one(self):
        self.assertTrue(True)
    def test_two(self):
        self.assertTrue(True)
'

write_fixture "all_fail" '
import unittest
class T(unittest.TestCase):
    def test_one(self):
        self.assertTrue(False)
'

write_fixture "mixed_fail_error" '
import unittest
class T(unittest.TestCase):
    def test_fail(self):
        self.assertTrue(False)
    def test_error(self):
        raise ValueError("boom")
    def test_ok(self):
        self.assertTrue(True)
'

assert_case "all-pass" "all_pass" "pass" 0 2
assert_case "all-fail" "all_fail" "fail" 1 1
assert_case "mixed-fail-error" "mixed_fail_error" "fail" 1 3

# The summary line must still appear, as its own distinct "no_tests" status
# (mirroring unittest's own "NO TESTS RAN" / exit 5), when the discover
# pattern matches zero files (e.g. an empty/renamed -s dir) — this must
# never be silently folded into "pass" (regression class of #268).
mkdir -p "$work_dir/empty_dir"
assert_case "no-matching-tests" "empty_dir" "no_tests" 5 0

if [ "$fail_count" -gt 0 ]; then
  echo "test_unittest_summary.sh: $fail_count assertion(s) failed"
  exit 1
fi
echo "test_unittest_summary.sh: all assertions passed"
