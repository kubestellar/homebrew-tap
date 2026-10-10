#!/usr/bin/env bash
# shell_coverage_gate.sh — kcov-based branch coverage gate for the
# scripts/test_*.sh regression suite, mirroring scripts/coverage_gate.py's
# shape for the Python side.
#
# Why: scripts/coverage_gate.py enforces a 100% coverage ratchet on the
# production Python helpers, but the ~2.6K LOC of production bash under
# scripts/ (verify_release_health.sh, formula_fuzz.sh, brew_install_smoke.sh,
# brew_ci_summary.sh, and 10 other prod shell scripts) has never been
# measured. A shell script can grow an entirely dead `case` arm or an
# `if guard` whose false path is never exercised, and CI would land it
# green — the exact regression the Python ratchet was written to prevent.
# See kubestellar/homebrew-tap#597 for the full rationale.
#
# What this does: discover scripts/test_*.sh, run each under kcov with
# the same include/exclude filters, merge the per-test coverage into
# coverage/kcov-merged, parse the merged coverage.json for
# percent_covered, and fail the workflow if it falls below --min.
#
# Why this file rather than editing the workflow directly: the quality-
# lane GitHub App does not carry the `workflows` permission scope, so any
# push that touches .github/workflows/*.yml is rejected server-side.
# Landing this helper first lets a maintainer wire it into
# validate-formulae.yml with a one-line workflow change:
#
#     - name: Install kcov
#       run: sudo apt-get update && sudo apt-get install -y kcov
#     - name: Enforce shell coverage gate
#       env:
#         SHELL_COVERAGE_MIN: "0"   # measure once, then ratchet up
#       run: bash scripts/shell_coverage_gate.sh
#
# kcov is NOT preinstalled on GitHub-hosted ubuntu-latest runners (the
# image moved to Ubuntu 24.04 in Dec 2024/Jan 2025 and trimmed its
# preinstalled package set — see actions/runner-images'
# Ubuntu2404-Readme.md, which lists no kcov). An explicit
# `sudo apt-get install -y kcov` step is required; omitting it makes
# this gate hard-fail with exit code 3 ("kcov not found") on every run.
#
# Usage:
#     scripts/shell_coverage_gate.sh                   # default threshold
#     scripts/shell_coverage_gate.sh --min 80          # override threshold
#     SHELL_COVERAGE_MIN=75 scripts/shell_coverage_gate.sh
#     scripts/shell_coverage_gate.sh --out coverage_dir
#
# Env vars:
#     SHELL_COVERAGE_MIN    integer 0-100, overrides the built-in default
#                           of 0. Start at the observed baseline and
#                           ratchet up over time — do not lower it.
#     SHELL_COVERAGE_OUT    output directory (default: coverage/shell)
#     KCOV                  path to kcov binary (default: kcov on $PATH)
#
# Exit codes:
#     0  — every test passed AND coverage >= threshold
#     1  — one or more scripts/test_*.sh failed
#     2  — tests passed but coverage below threshold
#     3  — kcov not installed / not on $PATH (or --kcov path missing)
#     4  — no scripts/test_*.sh discovered (empty-suite regression guard)
#     5  — kcov emitted no parseable coverage.json (tooling regression)

set -uo pipefail

usage() {
  sed -n '2,59p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=scripts/lib_emit_summary.sh
. "$repo_root/scripts/lib_emit_summary.sh"

# Defaults.
threshold_default="${SHELL_COVERAGE_MIN:-0}"
threshold="$threshold_default"
out_dir="${SHELL_COVERAGE_OUT:-$repo_root/coverage/shell}"
kcov_bin="${KCOV:-kcov}"
tests_dir="$repo_root/scripts"

while [ $# -gt 0 ]; do
  case "$1" in
    --min)
      shift
      if [ $# -eq 0 ]; then
        echo "shell_coverage_gate: --min requires an integer argument" >&2
        exit 64
      fi
      threshold="$1"
      shift
      ;;
    --min=*)
      threshold="${1#--min=}"
      shift
      ;;
    --out)
      shift
      if [ $# -eq 0 ]; then
        echo "shell_coverage_gate: --out requires a directory argument" >&2
        exit 64
      fi
      out_dir="$1"
      shift
      ;;
    --out=*)
      out_dir="${1#--out=}"
      shift
      ;;
    --kcov)
      shift
      if [ $# -eq 0 ]; then
        echo "shell_coverage_gate: --kcov requires a path argument" >&2
        exit 64
      fi
      kcov_bin="$1"
      shift
      ;;
    --kcov=*)
      kcov_bin="${1#--kcov=}"
      shift
      ;;
    --tests-dir)
      shift
      if [ $# -eq 0 ]; then
        echo "shell_coverage_gate: --tests-dir requires a directory argument" >&2
        exit 64
      fi
      tests_dir="$1"
      shift
      ;;
    --tests-dir=*)
      tests_dir="${1#--tests-dir=}"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "shell_coverage_gate: unknown argument: $1" >&2
      echo "run '$0 --help' for usage" >&2
      exit 64
      ;;
  esac
done

# Validate threshold is a plain non-negative integer in 0..100.
case "$threshold" in
  ''|*[!0-9]*)
    echo "shell_coverage_gate: --min/SHELL_COVERAGE_MIN must be a non-negative integer, got: $threshold" >&2
    exit 64
    ;;
esac
if [ "$threshold" -gt 100 ]; then
  echo "shell_coverage_gate: --min/SHELL_COVERAGE_MIN must be <= 100, got: $threshold" >&2
  exit 64
fi

# Locate kcov. This is a hard-fail path (exit 3) rather than a silent
# skip so a CI runner that loses kcov gets caught immediately instead
# of degrading to "no coverage measurement" without a signal.
if ! command -v "$kcov_bin" >/dev/null 2>&1; then
  echo "shell_coverage_gate: kcov not found (looked for: $kcov_bin)" >&2
  echo "  install with: sudo apt-get install -y kcov" >&2
  echo "  or set KCOV=/path/to/kcov" >&2
  exit 3
fi

if [ ! -d "$tests_dir" ]; then
  echo "shell_coverage_gate: tests dir does not exist: $tests_dir" >&2
  exit 64
fi

# Discover scripts/test_*.sh — same shape as scripts/run_shell_tests.sh
# (find -maxdepth 1, sort deterministically, skip test_lib.sh which is
# the sourced scaffolding, not a runnable test).
mapfile -d '' -t test_files < <(
  find "$tests_dir" -maxdepth 1 -type f -name 'test_*.sh' -print0 | sort -z
)

filtered=()
for f in "${test_files[@]}"; do
  case "$(basename "$f")" in
    test_lib.sh) continue ;;
    *) filtered+=("$f") ;;
  esac
done
test_files=("${filtered[@]}")

total="${#test_files[@]}"
if [ "$total" -eq 0 ]; then
  echo "shell_coverage_gate: no scripts/test_*.sh discovered under $tests_dir" >&2
  exit 4
fi

rm -rf "$out_dir"
mkdir -p "$out_dir"

fail_count=0
failed_names=()

for tfile in "${test_files[@]}"; do
  tname="$(basename "$tfile" .sh)"
  per_test_dir="$out_dir/$tname"
  mkdir -p "$per_test_dir"

  # kcov flags mirror the include/exclude shape recommended by #597:
  # instrument only production scripts under scripts/, and exclude
  # scripts/test_*.sh themselves so the ratio measures prod code, not
  # the tests exercising it.
  if ! "$kcov_bin" \
        --include-path="$repo_root/scripts" \
        --exclude-pattern=/test_,/coverage/ \
        "$per_test_dir" \
        "$tfile" >"$per_test_dir/kcov.stdout" 2>"$per_test_dir/kcov.stderr"; then
    fail_count=$((fail_count + 1))
    failed_names+=("$tname")
    echo "FAIL ($tname):"
    sed 's/^/  /' "$per_test_dir/kcov.stdout" "$per_test_dir/kcov.stderr" 2>/dev/null || true
  else
    echo "PASS ($tname)"
  fi
done

if [ "$fail_count" -ne 0 ]; then
  echo
  echo "shell_coverage_gate: $fail_count/$total test(s) failed:" >&2
  for name in "${failed_names[@]}"; do
    echo "  - $name" >&2
  done
  exit 1
fi

# Merge per-test coverage into a single aggregate report. kcov writes
# each run's summary into <out>/<tname>/coverage.json, but the aggregate
# for gating purposes is kcov-merged/coverage.json. Newer kcov auto-
# creates the merged dir; older kcov needs an explicit --merge pass.
# kcov nests its report one level deeper than the output dir it is given
# (<out>/<exe-name>/coverage.json, and <merge-out>/<name>/coverage.json),
# so locate coverage.json with find instead of assuming a fixed path.
find_coverage_json() {
  find "$1" -type f -name coverage.json -print 2>/dev/null | sort | head -n1
}

merged_json="$(find_coverage_json "$out_dir/kcov-merged")"
if [ -z "$merged_json" ]; then
  # Explicit merge over every per-test dir; keep stderr for diagnostics.
  per_test_dirs=()
  for d in "$out_dir"/*/; do
    case "$d" in */kcov-merged/) continue ;; esac
    per_test_dirs+=("${d%/}")
  done
  "$kcov_bin" --merge "$out_dir/kcov-merged" "${per_test_dirs[@]}" \
    >"$out_dir/kcov-merge.stdout" 2>"$out_dir/kcov-merge.stderr" || true
  merged_json="$(find_coverage_json "$out_dir/kcov-merged")"
fi

if [ -z "$merged_json" ]; then
  # Degrade to a per-test summary rather than failing opaquely.
  merged_json="$(
    find "$out_dir" -type f -name coverage.json -not -path '*/kcov-merged/*' -print 2>/dev/null \
      | sort | tail -n1
  )"
fi

if [ -z "$merged_json" ] || [ ! -f "$merged_json" ]; then
  echo "shell_coverage_gate: kcov produced no coverage.json under $out_dir" >&2
  echo "--- kcov output tree ---" >&2
  find "$out_dir" -maxdepth 3 2>/dev/null | head -n 50 >&2
  for f in "$out_dir"/kcov-merge.stderr "$out_dir"/*/kcov.stderr; do
    [ -s "$f" ] && { echo "--- $f ---" >&2; head -n 20 "$f" >&2; }
  done
  exit 5
fi

# Parse percent_covered from coverage.json. Prefer python3's json
# module: kcov's "files" array (one "percent_covered" per instrumented
# file) is written BEFORE the top-level aggregate "percent_covered"
# field, so a naive grep that takes the *first* match silently reports
# one file's coverage (often 0.00 for an uninstrumented file) instead
# of the aggregate — see kubestellar/homebrew-tap#697 fallout, where
# this regressed the gate to "coverage 0.00% >= threshold 0%" passing
# silently on every run despite ~59% real aggregate coverage. Only
# fall back to grep if python3 is unavailable, and take the *last*
# match there (the top-level field is always written last).
percent="$(
  python3 - "$merged_json" <<'PY' 2>/dev/null || true
import json, sys
try:
    with open(sys.argv[1]) as f:
        data = json.load(f)
except Exception:
    sys.exit(0)
val = data.get("percent_covered")
if val is None:
    files = data.get("files") or []
    covered = sum(int(f.get("covered_lines", 0)) for f in files)
    total = sum(int(f.get("total_lines", 0)) for f in files)
    if total > 0:
        val = f"{100.0 * covered / total:.2f}"
if val is not None:
    print(val)
PY
)"

if [ -z "$percent" ]; then
  percent="$(
    grep -o '"percent_covered"[[:space:]]*:[[:space:]]*"[0-9.]*"' "$merged_json" \
      | tail -n1 \
      | sed 's/.*"\([0-9.]*\)".*/\1/'
  )"
fi

if [ -z "$percent" ]; then
  echo "shell_coverage_gate: could not parse percent_covered from $merged_json" >&2
  exit 5
fi

# Integer comparison — round percent down to floor so a 79.9 doesn't
# sneak past an 80 threshold. Use awk so we don't depend on bc.
percent_floor="$(awk -v p="$percent" 'BEGIN { printf "%d", p }')"

emit_ci_summary SHELL_COVERAGE_SUMMARY \
  percent_covered:str="$percent" \
  threshold="$threshold" \
  tests="$total" \
  report:str="$merged_json"

if [ "$percent_floor" -lt "$threshold" ]; then
  echo "shell_coverage_gate: coverage $percent% is below threshold $threshold%" >&2
  exit 2
fi

echo "shell_coverage_gate: coverage $percent% >= threshold $threshold% (over $total test file(s))"
exit 0
