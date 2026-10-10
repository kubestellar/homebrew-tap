#!/usr/bin/env bash
# test_shell_coverage_gate.sh — regression tests for
# scripts/shell_coverage_gate.sh.
#
# Guards the gate's contract without requiring kcov to be installed on
# the test host: kcov is stubbed with a fake shim that writes a
# controlled coverage.json into the output dir. That lets us drive the
# gate through its threshold/parse/exit-code paths deterministically —
# CI still exercises real kcov once the workflow step is wired.
#
# Coverage focus (each numbered case corresponds to a branch of
# shell_coverage_gate.sh):
#   1. --help (exit 0, usage printed)
#   2. unknown flag (exit 64)
#   3. --min without argument (exit 64)
#   4. --min with non-integer (exit 64)
#   5. --min > 100 (exit 64)
#   6. kcov missing on $PATH (exit 3)
#   7. tests dir missing (exit 64)
#   8. no discovered test_*.sh (exit 4) — via empty --tests-dir
#   9. kcov exits non-zero → fail-list surfaced (exit 1)
#  10. kcov produces no coverage.json → tooling regression (exit 5)
#  11. coverage below threshold (exit 2 + summary line)
#  12. coverage >= threshold (exit 0 + summary line)
#  13. SHELL_COVERAGE_MIN env override
#  14. floor rounding: 79.9% must fail an 80 threshold
#  16. realistic kcov JSON (per-file "files" array, 0.00 first entry,
#      true aggregate last) must parse the aggregate, not the first
#      file's percent_covered (regression guard for #697 fallout,
#      where a `grep | head -n1` picked the wrong match and the gate
#      silently reported 0.00% on every run)
#
# Usage: scripts/test_shell_coverage_gate.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

# shellcheck source=scripts/test_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test_lib.sh"

REPO_ROOT="$(repo_root)"
GATE="$REPO_ROOT/scripts/shell_coverage_gate.sh"

make_work_dir

# make_fake_kcov <path> <percent> [exit_code]
# Writes a shim at <path> that emulates kcov: on a normal run it creates
# <output_dir>/coverage.json with the given percent, then exits 0. On
# --merge it writes into <merge_out>/coverage.json. Setting exit_code
# non-zero simulates a failing test run (kcov propagates the child's
# exit code).
make_fake_kcov() {
  local path="$1" percent="$2" exit_code="${3:-0}"
  mkdir -p "$(dirname "$path")"
  cat >"$path" <<EOF
#!/usr/bin/env bash
# Fake kcov used by test_shell_coverage_gate.sh.
set -u
if [ "\${1:-}" = "--merge" ]; then
  out_dir="\$2"
  mkdir -p "\$out_dir"
  printf '{"percent_covered":"%s"}\n' "$percent" > "\$out_dir/coverage.json"
  exit 0
fi
out_dir=""
for arg in "\$@"; do
  case "\$arg" in
    --include-path=*|--exclude-pattern=*) ;;
    -*) ;;
    *)
      if [ -z "\$out_dir" ]; then
        out_dir="\$arg"
      fi
      ;;
  esac
done
mkdir -p "\$out_dir"
printf '{"percent_covered":"%s"}\n' "$percent" > "\$out_dir/coverage.json"
exit $exit_code
EOF
  chmod +x "$path"
}

# make_fake_kcov_no_json — like make_fake_kcov but never writes any
# coverage.json (simulates a kcov version whose output layout changed).
make_fake_kcov_no_json() {
  local path="$1"
  mkdir -p "$(dirname "$path")"
  cat >"$path" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
  chmod +x "$path"
}

# make_tests_dir <dir> <count> — create <count> harmless test_*.sh
# scripts that just `exit 0`, plus a test_lib.sh scaffolding stub the
# discovery filter must skip.
make_tests_dir() {
  local dir="$1" count="$2" i
  mkdir -p "$dir"
  printf '#!/usr/bin/env bash\n:\n' >"$dir/test_lib.sh"
  chmod +x "$dir/test_lib.sh"
  for ((i = 1; i <= count; i++)); do
    printf '#!/usr/bin/env bash\nexit 0\n' >"$dir/test_case${i}.sh"
    chmod +x "$dir/test_case${i}.sh"
  done
}

# 1. --help exits 0 and prints usage-shaped output.
output=$("$GATE" --help 2>&1)
exit_code=$?
assert_exit_code "help-exit-0" 0 "$exit_code"
assert_contains "help-prints-usage" "$output" "Usage:"

# 2. Unknown flag → exit 64 with a diagnostic.
output=$("$GATE" --nope 2>&1)
exit_code=$?
assert_exit_code "unknown-flag-exit-64" 64 "$exit_code"
assert_contains "unknown-flag-diag" "$output" "unknown argument"

# 3. --min without its argument → exit 64.
output=$("$GATE" --min 2>&1)
exit_code=$?
assert_exit_code "min-no-arg-exit-64" 64 "$exit_code"

# 4. --min with a non-integer → exit 64.
output=$("$GATE" --min ninety 2>&1)
exit_code=$?
assert_exit_code "min-non-integer-exit-64" 64 "$exit_code"
assert_contains "min-non-integer-diag" "$output" "non-negative integer"

# 5. --min > 100 → exit 64.
output=$("$GATE" --min 101 2>&1)
exit_code=$?
assert_exit_code "min-over-100-exit-64" 64 "$exit_code"

# 6. kcov missing on $PATH → exit 3.
output=$(KCOV="$work_dir/does-not-exist-kcov" "$GATE" --min 0 2>&1)
exit_code=$?
assert_exit_code "kcov-missing-exit-3" 3 "$exit_code"
assert_contains "kcov-missing-diag" "$output" "kcov not found"

# 7. tests dir missing → exit 64.
make_fake_kcov "$work_dir/kcov" "90.00"
output=$(KCOV="$work_dir/kcov" "$GATE" --tests-dir "$work_dir/no-such-dir" --min 0 2>&1)
exit_code=$?
assert_exit_code "tests-dir-missing-exit-64" 64 "$exit_code"

# 8. Empty tests dir → exit 4 (empty-suite guard).
empty_tests="$work_dir/empty_tests"
mkdir -p "$empty_tests"
output=$(KCOV="$work_dir/kcov" "$GATE" --tests-dir "$empty_tests" --min 0 --out "$work_dir/out8" 2>&1)
exit_code=$?
assert_exit_code "empty-suite-exit-4" 4 "$exit_code"
assert_contains "empty-suite-diag" "$output" "no scripts/test_*.sh discovered"

# 9. Simulated failing test → exit 1 with fail-list surfaced.
make_fake_kcov "$work_dir/kcov_fail" "90.00" 1
tests9="$work_dir/tests9"
make_tests_dir "$tests9" 2
output=$(KCOV="$work_dir/kcov_fail" "$GATE" --tests-dir "$tests9" --min 0 --out "$work_dir/out9" 2>&1)
exit_code=$?
assert_exit_code "kcov-fail-exit-1" 1 "$exit_code"
assert_contains "kcov-fail-lists-name" "$output" "test_case1"

# 10. kcov emits nothing → exit 5.
make_fake_kcov_no_json "$work_dir/kcov_nojson"
tests10="$work_dir/tests10"
make_tests_dir "$tests10" 1
output=$(KCOV="$work_dir/kcov_nojson" "$GATE" --tests-dir "$tests10" --min 0 --out "$work_dir/out10" 2>&1)
exit_code=$?
assert_exit_code "no-json-exit-5" 5 "$exit_code"
assert_contains "no-json-diag" "$output" "no coverage.json"

# 11. Coverage below threshold → exit 2 with summary line.
make_fake_kcov "$work_dir/kcov_low" "42.00"
tests11="$work_dir/tests11"
make_tests_dir "$tests11" 1
output=$(KCOV="$work_dir/kcov_low" "$GATE" --tests-dir "$tests11" --min 80 --out "$work_dir/out11" 2>&1)
exit_code=$?
assert_exit_code "below-threshold-exit-2" 2 "$exit_code"
assert_contains "below-threshold-summary" "$output" "SHELL_COVERAGE_SUMMARY:"
assert_contains "below-threshold-diag" "$output" "below threshold 80%"

# 12. Coverage at/above threshold → exit 0.
make_fake_kcov "$work_dir/kcov_ok" "88.50"
tests12="$work_dir/tests12"
make_tests_dir "$tests12" 3
output=$(KCOV="$work_dir/kcov_ok" "$GATE" --tests-dir "$tests12" --min 80 --out "$work_dir/out12" 2>&1)
exit_code=$?
assert_exit_code "meets-threshold-exit-0" 0 "$exit_code"
assert_contains "meets-threshold-summary" "$output" "SHELL_COVERAGE_SUMMARY:"
assert_grep "meets-threshold-count" "$output" '"tests":3' "expected tests:3 in summary line. Got: $output"

# 13. SHELL_COVERAGE_MIN env override — 50 threshold via env, 42% coverage
#     should still fail (proves env is picked up as the default).
output=$(KCOV="$work_dir/kcov_low" SHELL_COVERAGE_MIN=50 "$GATE" --tests-dir "$tests11" --out "$work_dir/out13" 2>&1)
exit_code=$?
assert_exit_code "env-min-exit-2" 2 "$exit_code"
assert_contains "env-min-diag" "$output" "below threshold 50%"

# 14. Floor rounding: 79.9% must fail an 80 threshold (guards the awk
#     floor cast against a subtle "round to 80" regression).
make_fake_kcov "$work_dir/kcov_edge" "79.90"
tests14="$work_dir/tests14"
make_tests_dir "$tests14" 1
output=$(KCOV="$work_dir/kcov_edge" "$GATE" --tests-dir "$tests14" --min 80 --out "$work_dir/out14" 2>&1)
exit_code=$?
assert_exit_code "floor-79.9-exit-2" 2 "$exit_code"

# make_fake_kcov_realistic <path> <aggregate_percent> — like
# make_fake_kcov, but writes a coverage.json shaped like real kcov
# output: a "files" array (whose first entry is an uninstrumented file
# at 0.00%) followed by the true top-level "percent_covered" field.
# Only used on --merge, matching how shell_coverage_gate.sh reads the
# aggregate exclusively from the merged report.
make_fake_kcov_realistic() {
  local path="$1" aggregate="$2"
  mkdir -p "$(dirname "$path")"
  cat >"$path" <<EOF
#!/usr/bin/env bash
set -u
if [ "\${1:-}" = "--merge" ]; then
  out_dir="\$2"
  mkdir -p "\$out_dir"
  cat >"\$out_dir/coverage.json" <<JSON
{
  "files": [
    {"file": "/repo/scripts/untouched.sh", "percent_covered": "0.00", "covered_lines": "0", "total_lines": "10"},
    {"file": "/repo/scripts/touched.sh", "percent_covered": "100.00", "covered_lines": "5", "total_lines": "5"}
  ],
  "percent_covered": "$aggregate",
  "covered_lines": 5,
  "total_lines": 15
}
JSON
  exit 0
fi
out_dir=""
for arg in "\$@"; do
  case "\$arg" in
    --include-path=*|--exclude-pattern=*) ;;
    -*) ;;
    *)
      if [ -z "\$out_dir" ]; then
        out_dir="\$arg"
      fi
      ;;
  esac
done
mkdir -p "\$out_dir"
printf '{"percent_covered":"0.00"}\n' > "\$out_dir/coverage.json"
exit 0
EOF
  chmod +x "$path"
}

# 15. Same fake, threshold 79 → passes (79.9 floors to 79, which >= 79).
output=$(KCOV="$work_dir/kcov_edge" "$GATE" --tests-dir "$tests14" --min 79 --out "$work_dir/out15" 2>&1)
exit_code=$?
assert_exit_code "floor-79.9-vs-79-exit-0" 0 "$exit_code"

# 16. Realistic kcov JSON: first "files" entry is 0.00%, true aggregate
#     (90.00) is the top-level field written last. The gate must report
#     90, not 0 — guards against the #697 fallout where `head -n1`
#     silently picked the first file's percent_covered instead of the
#     aggregate.
make_fake_kcov_realistic "$work_dir/kcov_realistic" "90.00"
tests16="$work_dir/tests16"
make_tests_dir "$tests16" 1
output=$(KCOV="$work_dir/kcov_realistic" "$GATE" --tests-dir "$tests16" --min 80 --out "$work_dir/out16" 2>&1)
exit_code=$?
assert_exit_code "realistic-json-aggregate-exit-0" 0 "$exit_code"
assert_grep "realistic-json-aggregate-percent" "$output" '"percent_covered":"90.00"' \
  "expected aggregate 90.00 in summary, not the first file's 0.00. Got: $output"

finish "shell_coverage_gate"
