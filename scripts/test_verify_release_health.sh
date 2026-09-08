#!/usr/bin/env bash
# test_verify_release_health.sh — regression tests for
# scripts/verify_release_health.sh.
#
# This script is the one structured-summary emitter in the repo
# (VERIFY_RELEASE_HEALTH_SUMMARY:, alongside VALIDATE_FORMULAE_SUMMARY: and
# FUZZ_SUMMARY:) with no regression coverage of its own, so a future edit
# could silently break the summary line's shape (missing a field, wrong
# exit code on partial failure) with nothing to catch it. Since the script
# always shells out to the real `brew`, these tests stub a fake `brew` on
# PATH so they run without Homebrew installed and without touching the
# real Formula/*.rb release artifacts.
#
# Usage: scripts/test_verify_release_health.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/verify_release_health.sh"

fail_count=0
STUB_DIR="$(mktemp -d)"
trap 'rm -rf "$STUB_DIR"' EXIT

# A fake `brew` that only implements the one subcommand
# verify_release_health.sh calls: `brew fetch --formula <path>`. Which
# formula names fail is controlled by the caller via VRH_TEST_FAIL_NAMES
# (space-separated basenames, without .rb).
cat > "$STUB_DIR/brew" <<'EOF'
#!/usr/bin/env bash
set -u
if [ "$1" = "fetch" ]; then
  path="$3"
  name="$(basename "${path%.rb}")"
  for bad in ${VRH_TEST_FAIL_NAMES:-}; do
    if [ "$bad" = "$name" ]; then
      echo "error: failed to fetch $name" >&2
      exit 1
    fi
  done
  echo "fetching $name... done"
  exit 0
fi
echo "brew stub: unsupported args: $*" >&2
exit 1
EOF
chmod +x "$STUB_DIR/brew"

# Real Formula/ has 3 formulae today; used to assert formula_count with no
# arguments doesn't silently drift without updating this test.
real_formula_count=$(find "$REPO_ROOT/Formula" -maxdepth 1 -name '*.rb' | wc -l | tr -d ' ')

run_script() {
  PATH="$STUB_DIR:$PATH" "$SCRIPT" "$@"
}

assert_contains() {
  local name="$1" haystack="$2" needle="$3"
  if ! printf '%s' "$haystack" | grep -qF "$needle"; then
    echo "FAIL ($name): expected output to contain '$needle'. Got:"
    printf '%s\n' "$haystack"
    fail_count=$((fail_count + 1))
    return 1
  fi
  return 0
}

# Case 1: every formula fetches successfully -> status=pass, exit 0.
output=$(VRH_TEST_FAIL_NAMES="" run_script 2>&1)
exit_code=$?
if ! printf '%s' "$output" | grep -q '^VERIFY_RELEASE_HEALTH_SUMMARY: {'; then
  echo "FAIL (all-pass): missing VERIFY_RELEASE_HEALTH_SUMMARY: line. Got: $output"
  fail_count=$((fail_count + 1))
else
  assert_contains "all-pass status" "$output" "\"status\":\"pass\""
  assert_contains "all-pass formula_count" "$output" "\"formula_count\":${real_formula_count}"
  assert_contains "all-pass failed_count" "$output" '"failed_count":0'
  if [ "$exit_code" -ne 0 ]; then
    echo "FAIL (all-pass): expected exit=0, got exit=$exit_code"
    fail_count=$((fail_count + 1))
  else
    echo "OK (all-pass)"
  fi
fi

# Case 2: one formula fails to fetch -> status=fail, failed_count=1, exit 1.
output=$(VRH_TEST_FAIL_NAMES="kc-agent" run_script 2>&1)
exit_code=$?
if ! printf '%s' "$output" | grep -q '^VERIFY_RELEASE_HEALTH_SUMMARY: {'; then
  echo "FAIL (one-fail): missing VERIFY_RELEASE_HEALTH_SUMMARY: line. Got: $output"
  fail_count=$((fail_count + 1))
else
  assert_contains "one-fail status" "$output" "\"status\":\"fail\""
  assert_contains "one-fail failed_count" "$output" '"failed_count":1'
  if [ "$exit_code" -ne 1 ]; then
    echo "FAIL (one-fail): expected exit=1, got exit=$exit_code"
    fail_count=$((fail_count + 1))
  else
    echo "OK (one-fail)"
  fi
fi

# Case 3: all formulae fail -> failed_count equals total formula_count.
output=$(VRH_TEST_FAIL_NAMES="kc-agent kubestellar-deploy kubestellar-ops" run_script 2>&1)
exit_code=$?
if ! printf '%s' "$output" | grep -q "\"failed_count\":${real_formula_count}"; then
  echo "FAIL (all-fail): expected failed_count=${real_formula_count}. Got: $output"
  fail_count=$((fail_count + 1))
elif [ "$exit_code" -ne 1 ]; then
  echo "FAIL (all-fail): expected exit=1, got exit=$exit_code"
  fail_count=$((fail_count + 1))
else
  echo "OK (all-fail)"
fi

# Case 4: restricting to a single named formula narrows formula_count to 1,
# regardless of how many formulae exist in the repo.
output=$(VRH_TEST_FAIL_NAMES="" run_script kubestellar-ops 2>&1)
exit_code=$?
if ! printf '%s' "$output" | grep -q '"formula_count":1'; then
  echo "FAIL (single-formula): expected formula_count=1. Got: $output"
  fail_count=$((fail_count + 1))
elif [ "$exit_code" -ne 0 ]; then
  echo "FAIL (single-formula): expected exit=0, got exit=$exit_code"
  fail_count=$((fail_count + 1))
else
  echo "OK (single-formula)"
fi

# Case 5: an unknown formula name is reported as a failed SKIP, not silently
# dropped from the count.
output=$(VRH_TEST_FAIL_NAMES="" run_script does-not-exist 2>&1)
exit_code=$?
if ! printf '%s' "$output" | grep -q "SKIP: no such formula file"; then
  echo "FAIL (unknown-formula): expected a SKIP line for the missing formula. Got: $output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q '"failed_count":1'; then
  echo "FAIL (unknown-formula): expected failed_count=1. Got: $output"
  fail_count=$((fail_count + 1))
elif [ "$exit_code" -ne 1 ]; then
  echo "FAIL (unknown-formula): expected exit=1, got exit=$exit_code"
  fail_count=$((fail_count + 1))
else
  echo "OK (unknown-formula)"
fi

if [ "$fail_count" -gt 0 ]; then
  echo "test_verify_release_health.sh: $fail_count assertion(s) failed"
  exit 1
fi
echo "test_verify_release_health.sh: all assertions passed"
