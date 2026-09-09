#!/usr/bin/env bash
# test_fuzz_summary_empty_dir.sh — regression guard for one branch of
# scripts/fuzz_summary.sh that the existing scripts/test_fuzz_summary.sh
# does not exercise: FORMULA_DIR EXISTS but contains no *.rb files
# (i.e. the `for f in "$FORMULA_DIR"/*.rb; do [ -e "$f" ] || continue`
# glob-no-match guard).
#
# Coverage layout right now:
#   - scripts/test_fuzz_summary.sh has a `missing-formula-dir` case that
#     covers the outer `[ -d "$FORMULA_DIR" ]` FALSE arm.
#   - Its other three cases (success/failure/defaults) all populate the
#     directory with two .rb files, so the loop-body is always taken.
#   - Neither case reaches "FORMULA_DIR exists but is empty". Under
#     `set -uo pipefail` with nullglob unset, the glob expands to the
#     literal `"$FORMULA_DIR"/*.rb`, which fails the `[ -e "$f" ]` test
#     — the branch guard is the only reason formula_count stays at 0
#     instead of the loop body running once with a nonexistent file.
#
# A regression that dropped that guard (or replaced it with `[ -f "$f" ]`
# and forgot the outer skip) would silently over-count formulae by 1 on
# empty tap checkouts, and the resulting FUZZ_SUMMARY: line would carry
# `formula_count:1` for a Formula/ directory that actually has zero
# .rb files. That would corrupt the SLI mentioned in docs/slo.md
# ("Formula fuzz health"). This test locks the guard behavior.
#
# Usage: scripts/test_fuzz_summary_empty_dir.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/fuzz_summary.sh"

fail_count=0
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

mkdir -p "$work_dir/Formula"
# Deliberately do NOT create any .rb file — this is the whole point of
# the test: an empty but existing Formula/ directory.

# Sanity check: our fixture really is empty of .rb files.
if [ -n "$(find "$work_dir/Formula" -maxdepth 1 -name '*.rb' 2>/dev/null)" ]; then
  echo "FAIL (fixture): work_dir Formula/ unexpectedly contains .rb files"
  exit 1
fi

# 1. success + empty Formula/ dir: script must NOT crash, formula_count
#    must be 0, and exit code must be 0 (JOB_STATUS=success).
output=$(FORMULA_DIR="$work_dir/Formula" JOB_STATUS="success" "$SCRIPT" 2>&1)
exit_code=$?
if ! printf '%s' "$output" | grep -q '^FUZZ_SUMMARY: {'; then
  echo "FAIL (empty-dir-success): missing FUZZ_SUMMARY: line. Got: $output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q '"formula_count":0'; then
  echo "FAIL (empty-dir-success): expected formula_count=0. Got: $output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q '"status":"success"'; then
  echo "FAIL (empty-dir-success): expected status=success. Got: $output"
  fail_count=$((fail_count + 1))
elif [ "$exit_code" -ne 0 ]; then
  echo "FAIL (empty-dir-success): expected exit=0, got exit=$exit_code"
  fail_count=$((fail_count + 1))
else
  echo "OK (empty-dir-success)"
fi

# 2. failure + empty Formula/ dir: same accounting shape, exit 1.
output=$(FORMULA_DIR="$work_dir/Formula" JOB_STATUS="failure" "$SCRIPT" 2>&1)
exit_code=$?
if ! printf '%s' "$output" | grep -q '"formula_count":0'; then
  echo "FAIL (empty-dir-failure): expected formula_count=0. Got: $output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q '"status":"failure"'; then
  echo "FAIL (empty-dir-failure): expected status=failure. Got: $output"
  fail_count=$((fail_count + 1))
elif [ "$exit_code" -ne 1 ]; then
  echo "FAIL (empty-dir-failure): expected exit=1, got exit=$exit_code"
  fail_count=$((fail_count + 1))
else
  echo "OK (empty-dir-failure)"
fi

# 3. Non-.rb files present but no .rb files: still formula_count=0.
#    Guards against a future maintainer widening the glob to `*` and
#    breaking the "only .rb formulae count" contract.
printf 'notes\n' > "$work_dir/Formula/README.md"
printf '{}\n' > "$work_dir/Formula/manifest.json"
output=$(FORMULA_DIR="$work_dir/Formula" JOB_STATUS="success" "$SCRIPT" 2>&1)
exit_code=$?
if ! printf '%s' "$output" | grep -q '"formula_count":0'; then
  echo "FAIL (non-rb-only): expected formula_count=0. Got: $output"
  fail_count=$((fail_count + 1))
elif [ "$exit_code" -ne 0 ]; then
  echo "FAIL (non-rb-only): expected exit=0, got exit=$exit_code"
  fail_count=$((fail_count + 1))
else
  echo "OK (non-rb-only)"
fi

if [ "$fail_count" -eq 0 ]; then
  echo "All fuzz_summary.sh empty-dir tests passed."
  exit 0
else
  echo "$fail_count fuzz_summary.sh empty-dir test(s) failed."
  exit 1
fi
