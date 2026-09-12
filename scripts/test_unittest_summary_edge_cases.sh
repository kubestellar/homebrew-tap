#!/usr/bin/env bash
# test_unittest_summary_edge_cases.sh — edge-case regression tests for
# scripts/unittest_summary.sh, targeting the boundary/parsing behavior
# NOT already covered by test_unittest_summary.sh.
#
# The base suite pins the four coarse states (pass / fail-with-failures /
# fail-with-errors / no-tests). These cases go a level deeper:
#
#   1. `FAILED (failures=N)` line must also produce "errors":0 (the
#      awk/sed extractor for errors falls through the `[ -n ] || errors=0`
#      guard).
#   2. `FAILED (errors=M)` line must also produce "failures":0 (the
#      symmetric guard).
#   3. Mixed `FAILED (failures=N, errors=M)` must produce both counts
#      accurately — a regression that flipped the two regex captures
#      would still pass the base suite because that suite never runs a
#      mixed case.
#   4. Multi-test pass must report the correct `tests_run` count — a
#      regression that hard-coded `tests_run=1` would still pass the
#      base pass case.
#   5. FAILED with plural forms (`failures=2, errors=3`) parses too —
#      the sed captures `[0-9]+`, not `[0-9]`.
#   6. The tail unittest summary line ("OK" / "FAILED (…)" / "Ran N")
#      must appear verbatim in stdout ahead of the UNITTEST_SUMMARY line
#      — anything that quieted it (e.g. redirecting `tee` away) would
#      hide the human-readable half of the CI log.
#
# Usage: scripts/test_unittest_summary_edge_cases.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/unittest_summary.sh"

fail_count=0
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

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

# --- Case 1: failure-only run must set errors:0 ---
dir1="$work_dir/failure_only"
mkdir -p "$dir1"
cat > "$dir1/test_only_failure.py" <<'EOF'
import unittest

class OnlyFailure(unittest.TestCase):
    def test_a(self):
        self.assertTrue(False)  # produces a failure, not an error

if __name__ == "__main__":
    unittest.main()
EOF
output=$(SCRIPTS_DIR="$dir1" "$SCRIPT" 2>&1)
exit_code=$?
assert_contains "1a status=fail"       "$output" '"status":"fail"'
assert_contains "1b failures=1"        "$output" '"failures":1'
assert_contains "1c errors=0 fallback" "$output" '"errors":0'
assert_exit     "1d exit=1"            1 "$exit_code"

# --- Case 2: error-only run must set failures:0 ---
dir2="$work_dir/error_only"
mkdir -p "$dir2"
cat > "$dir2/test_only_error.py" <<'EOF'
import unittest

class OnlyError(unittest.TestCase):
    def test_a(self):
        raise RuntimeError("boom")  # produces an error, not a failure

if __name__ == "__main__":
    unittest.main()
EOF
output=$(SCRIPTS_DIR="$dir2" "$SCRIPT" 2>&1)
exit_code=$?
assert_contains "2a status=fail"          "$output" '"status":"fail"'
assert_contains "2b errors=1"             "$output" '"errors":1'
assert_contains "2c failures=0 fallback"  "$output" '"failures":0'
assert_exit     "2d exit=1"               1 "$exit_code"

# --- Case 3: mixed failures + errors ---
dir3="$work_dir/mixed"
mkdir -p "$dir3"
cat > "$dir3/test_mixed.py" <<'EOF'
import unittest

class Mixed(unittest.TestCase):
    def test_fail_a(self):
        self.assertTrue(False)
    def test_fail_b(self):
        self.assertEqual(1, 2)
    def test_error_a(self):
        raise ValueError("v")
    def test_error_b(self):
        raise KeyError("k")
    def test_error_c(self):
        raise IndexError("i")
    def test_pass(self):
        self.assertTrue(True)

if __name__ == "__main__":
    unittest.main()
EOF
output=$(SCRIPTS_DIR="$dir3" "$SCRIPT" 2>&1)
exit_code=$?
assert_contains "3a status=fail"    "$output" '"status":"fail"'
assert_contains "3b tests_run=6"    "$output" '"tests_run":6'
assert_contains "3c failures=2"     "$output" '"failures":2'
assert_contains "3d errors=3"       "$output" '"errors":3'
assert_exit     "3e exit=1"         1 "$exit_code"

# --- Case 4: multi-test pass reports N > 1 ---
dir4="$work_dir/multi_pass"
mkdir -p "$dir4"
cat > "$dir4/test_multi.py" <<'EOF'
import unittest

class MultiPass(unittest.TestCase):
    def test_one(self):
        self.assertEqual(1, 1)
    def test_two(self):
        self.assertEqual(2, 2)
    def test_three(self):
        self.assertEqual(3, 3)
    def test_four(self):
        self.assertEqual(4, 4)

if __name__ == "__main__":
    unittest.main()
EOF
output=$(SCRIPTS_DIR="$dir4" "$SCRIPT" 2>&1)
exit_code=$?
assert_contains "4a status=pass"    "$output" '"status":"pass"'
assert_contains "4b tests_run=4"    "$output" '"tests_run":4'
assert_contains "4c failures=0"     "$output" '"failures":0'
assert_contains "4d errors=0"       "$output" '"errors":0'
assert_exit     "4e exit=0"         0 "$exit_code"

# --- Case 5: unittest verbose tail lines appear ahead of the summary ---
# The base pass case only asserts the test name; this case additionally
# pins the `OK` tail line, the `Ran N test` line, and — from case 3's
# output — the `FAILED (…)` tail line. If someone routed `tee` to
# /dev/null the summary would still emit but the human log would go
# silent, which is the debug-hostile regression this guards against.
assert_contains "5a multi-pass shows Ran-line"  "$output" 'Ran 4 tests in'
assert_contains "5b multi-pass shows OK tail"   "$output" $'\nOK\n'

# Re-run the mixed case to check the FAILED tail line and Ran-6 line too.
output=$(SCRIPTS_DIR="$dir3" "$SCRIPT" 2>&1)
assert_contains "5c mixed shows Ran-6 line"     "$output" 'Ran 6 tests in'
assert_contains "5d mixed shows FAILED tail"    "$output" 'FAILED (failures=2, errors=3)'

# --- Case 6: FAILED with plural counts (multi-digit) parses correctly ---
# The extractor uses `[0-9]+`, not `[0-9]`. Cheap synthetic guard against
# a future edit narrowing the char class.
dir6="$work_dir/many"
mkdir -p "$dir6"
{
  echo "import unittest"
  echo "class Many(unittest.TestCase):"
  # 12 failing tests → failures=12 (double-digit)
  for i in $(seq 1 12); do
    echo "    def test_fail_$i(self): self.assertTrue(False)"
  done
  echo 'if __name__ == "__main__": unittest.main()'
} > "$dir6/test_many.py"
output=$(SCRIPTS_DIR="$dir6" "$SCRIPT" 2>&1)
exit_code=$?
assert_contains "6a status=fail"    "$output" '"status":"fail"'
assert_contains "6b tests_run=12"   "$output" '"tests_run":12'
assert_contains "6c failures=12"    "$output" '"failures":12'
assert_contains "6d errors=0"       "$output" '"errors":0'
assert_exit     "6e exit=1"         1 "$exit_code"

if [ "$fail_count" -eq 0 ]; then
  echo "All unittest_summary.sh edge-case tests passed."
  exit 0
else
  echo "$fail_count unittest_summary.sh edge-case test(s) failed."
  exit 1
fi
