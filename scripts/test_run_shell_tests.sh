#!/usr/bin/env bash
# test_run_shell_tests.sh — regression guard for scripts/run_shell_tests.sh.
#
# Locks the four contracts the runner must honor for the CI wire-up
# (a future workflow step will invoke it as a single line) to be safe:
#
#   1. exit 0 when every discovered test passes
#   2. exit 1 when any single test fails, and replay that test's output
#   3. exit 1 when nothing was discovered (empty scripts dir), so a
#      renamed/moved test directory is not silently a green build
#   4. skip the runner itself if a copy sits next to the pattern (i.e.
#      the runner won't recursively invoke itself)
#
# Style matches the sibling scripts/test_*.sh files.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="$REPO_ROOT/scripts/run_shell_tests.sh"

fail_count=0
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

# ---------- case 1: all-pass discovery ----------
mkdir -p "$work_dir/all_pass"
cat > "$work_dir/all_pass/test_alpha.sh" <<'EOF'
#!/usr/bin/env bash
echo "alpha ok"
exit 0
EOF
cat > "$work_dir/all_pass/test_beta.sh" <<'EOF'
#!/usr/bin/env bash
echo "beta ok"
exit 0
EOF
chmod +x "$work_dir/all_pass"/*.sh

output=$("$RUNNER" "$work_dir/all_pass" 2>&1)
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "FAIL (all-pass): expected exit 0, got $rc"
  echo "$output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q 'PASS test_alpha.sh'; then
  echo "FAIL (all-pass): missing PASS line for test_alpha.sh"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q 'PASS test_beta.sh'; then
  echo "FAIL (all-pass): missing PASS line for test_beta.sh"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q 'summary: 2 passed, 0 failed, 2 total'; then
  echo "FAIL (all-pass): wrong summary line: $output"
  fail_count=$((fail_count + 1))
else
  echo "OK (all-pass)"
fi

# ---------- case 2: mixed-pass / fail (with output replay) ----------
mkdir -p "$work_dir/mixed"
cat > "$work_dir/mixed/test_ok.sh" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
cat > "$work_dir/mixed/test_broken.sh" <<'EOF'
#!/usr/bin/env bash
echo "assertion X tripped: expected 3, got 4"
exit 7
EOF
chmod +x "$work_dir/mixed"/*.sh

output=$("$RUNNER" "$work_dir/mixed" 2>&1)
rc=$?
if [ "$rc" -ne 1 ]; then
  echo "FAIL (mixed): expected exit 1 on failure, got $rc"
  echo "$output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q 'FAIL test_broken.sh (exit 7)'; then
  echo "FAIL (mixed): missing 'FAIL test_broken.sh (exit 7)'. Got: $output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q 'assertion X tripped: expected 3, got 4'; then
  echo "FAIL (mixed): failing test's stdout was not replayed. Got: $output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q 'summary: 1 passed, 1 failed, 2 total'; then
  echo "FAIL (mixed): wrong summary line: $output"
  fail_count=$((fail_count + 1))
else
  echo "OK (mixed)"
fi

# ---------- case 3: empty discovery ----------
mkdir -p "$work_dir/empty"
# No test_*.sh files in the dir.
output=$("$RUNNER" "$work_dir/empty" 2>&1)
rc=$?
if [ "$rc" -ne 1 ]; then
  echo "FAIL (empty): expected exit 1 for empty suite, got $rc"
  echo "$output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q 'no tests matched'; then
  echo "FAIL (empty): missing 'no tests matched' error. Got: $output"
  fail_count=$((fail_count + 1))
else
  echo "OK (empty)"
fi

# ---------- case 4: runner does not include itself in discovery ----------
# Put a copy of the runner into a test dir and confirm the runner
# skips it (rather than trying to execute it as a test). Otherwise a
# workflow that dumps run_shell_tests.sh into scripts/ would recurse.
mkdir -p "$work_dir/self"
cp "$RUNNER" "$work_dir/self/run_shell_tests.sh"
chmod +x "$work_dir/self/run_shell_tests.sh"
cat > "$work_dir/self/test_sentinel.sh" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$work_dir/self/test_sentinel.sh"

# Invoke the copy so BASH_SOURCE[0]'s basename matches the runner name.
output=$(timeout 10s "$work_dir/self/run_shell_tests.sh" "$work_dir/self" 2>&1)
rc=$?
if [ "$rc" -eq 124 ]; then
  echo "FAIL (self-skip): runner appears to have recursed (timed out)"
  fail_count=$((fail_count + 1))
elif [ "$rc" -ne 0 ]; then
  echo "FAIL (self-skip): expected exit 0, got $rc"
  echo "$output"
  fail_count=$((fail_count + 1))
elif printf '%s' "$output" | grep -qE '(PASS|FAIL) run_shell_tests.sh'; then
  echo "FAIL (self-skip): runner tried to execute itself. Got: $output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q 'PASS test_sentinel.sh'; then
  echo "FAIL (self-skip): sentinel test was not run. Got: $output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q 'summary: 1 passed, 0 failed, 1 total'; then
  echo "FAIL (self-skip): expected 1/0/1 summary (runner excluded). Got: $output"
  fail_count=$((fail_count + 1))
else
  echo "OK (self-skip)"
fi

# ---------- case 5: SHELL_TEST_QUIET suppresses PASS lines ----------
output=$(SHELL_TEST_QUIET=1 "$RUNNER" "$work_dir/all_pass" 2>&1)
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "FAIL (quiet): expected exit 0, got $rc"
  echo "$output"
  fail_count=$((fail_count + 1))
elif printf '%s' "$output" | grep -q '^PASS '; then
  echo "FAIL (quiet): PASS line leaked through despite SHELL_TEST_QUIET=1. Got: $output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q 'summary: 2 passed, 0 failed, 2 total'; then
  echo "FAIL (quiet): summary line missing/wrong. Got: $output"
  fail_count=$((fail_count + 1))
else
  echo "OK (quiet)"
fi

# ---------- summary ----------
if [ "$fail_count" -eq 0 ]; then
  echo "All run_shell_tests.sh regression tests passed."
  exit 0
else
  echo "$fail_count run_shell_tests.sh test(s) failed."
  exit 1
fi
