#!/usr/bin/env bash
# test_unittest_summary.sh — regression tests for scripts/unittest_summary.sh.
#
# Guards against the summary line silently losing its stdout-only,
# always-emitted contract: passing, failing, erroring, and empty test
# suites must each still produce exactly one UNITTEST_SUMMARY: JSON line
# with the correct status/counts, the underlying unittest verbose output
# must still appear unmodified, and the script's own exit status must
# reflect the summary status (0 only for "pass") so a future edit can't
# reintroduce a silent no-tests-ran gap like #268.
#
# Usage: scripts/test_unittest_summary.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/unittest_summary.sh"

fail_count=0
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

write_case_dir() {
  local dir="$1"
  mkdir -p "$dir"
}

assert_contains() {
  local name="$1" haystack="$2" needle="$3"
  if printf '%s' "$haystack" | grep -qF "$needle"; then
    echo "OK ($name)"
  else
    echo "FAIL ($name): expected to find '$needle'. Got: $haystack"
    fail_count=$((fail_count + 1))
  fi
}

assert_exit() {
  local name="$1" expected="$2" actual="$3"
  if [ "$actual" -eq "$expected" ]; then
    echo "OK ($name)"
  else
    echo "FAIL ($name): expected exit=$expected, got exit=$actual"
    fail_count=$((fail_count + 1))
  fi
}

# --- Case 1: a single passing test ---
pass_dir="$work_dir/pass"
write_case_dir "$pass_dir"
cat > "$pass_dir/test_ok.py" <<'EOF'
import unittest

class OkTest(unittest.TestCase):
    def test_true(self):
        self.assertTrue(True)

if __name__ == "__main__":
    unittest.main()
EOF
output=$(SCRIPTS_DIR="$pass_dir" "$SCRIPT" 2>&1)
exit_code=$?
assert_contains "pass-summary-line" "$output" 'UNITTEST_SUMMARY: {"status":"pass"'
assert_contains "pass-tests-run" "$output" '"tests_run":1'
assert_contains "pass-failures" "$output" '"failures":0'
assert_contains "pass-verbose-preserved" "$output" "test_true"
assert_exit "pass-exit" 0 "$exit_code"

# --- Case 2: a failing test ---
fail_dir="$work_dir/fail"
write_case_dir "$fail_dir"
cat > "$fail_dir/test_bad.py" <<'EOF'
import unittest

class BadTest(unittest.TestCase):
    def test_false(self):
        self.assertTrue(False)

if __name__ == "__main__":
    unittest.main()
EOF
output=$(SCRIPTS_DIR="$fail_dir" "$SCRIPT" 2>&1)
exit_code=$?
assert_contains "fail-summary-line" "$output" 'UNITTEST_SUMMARY: {"status":"fail"'
assert_contains "fail-tests-run" "$output" '"tests_run":1'
assert_contains "fail-failures" "$output" '"failures":1'
assert_exit "fail-exit" 1 "$exit_code"

# --- Case 3: an erroring test ---
error_dir="$work_dir/error"
write_case_dir "$error_dir"
cat > "$error_dir/test_error.py" <<'EOF'
import unittest

class ErrorTest(unittest.TestCase):
    def test_raises(self):
        raise ValueError("boom")

if __name__ == "__main__":
    unittest.main()
EOF
output=$(SCRIPTS_DIR="$error_dir" "$SCRIPT" 2>&1)
exit_code=$?
assert_contains "error-summary-line" "$output" 'UNITTEST_SUMMARY: {"status":"fail"'
assert_contains "error-errors" "$output" '"errors":1'
assert_exit "error-exit" 1 "$exit_code"

# --- Case 4: no matching test_*.py files at all ---
empty_dir="$work_dir/empty"
write_case_dir "$empty_dir"
output=$(SCRIPTS_DIR="$empty_dir" "$SCRIPT" 2>&1)
exit_code=$?
assert_contains "no-tests-summary-line" "$output" 'UNITTEST_SUMMARY: {"status":"no_tests"'
assert_contains "no-tests-run-zero" "$output" '"tests_run":0'
assert_exit "no-tests-exit" 1 "$exit_code"

if [ "$fail_count" -eq 0 ]; then
  echo "All unittest_summary.sh tests passed."
  exit 0
else
  echo "$fail_count unittest_summary.sh test(s) failed."
  exit 1
fi
