#!/usr/bin/env bash
# run_shell_tests.sh — discover-and-run wrapper for scripts/test_*.sh.
#
# The 10 shell test files in scripts/ (109 assertions total) are runnable
# standalone but no workflow enumerates them, so regressions to the five
# CI-observability helpers they cover (brew_ci_summary, fuzz_summary,
# unittest_summary, verify_release_health, workflow_failure_notify) can
# land silently. See kubestellar-tap#411 for context.
#
# This wrapper mirrors what validate-formulae.yml already does for the
# Python side (`python3 -m unittest discover -s scripts -p 'test_*.py'`):
# it discovers `scripts/test_*.sh`, executes each, and reports a
# summary. Wiring the wrapper into CI still needs a workflow edit
# (out of reach for the quality lane's tier — see the issue), but the
# wrapper itself is repository code and can be dropped in with one line
# from that future workflow step: `bash scripts/run_shell_tests.sh`.
#
# Exit status: 0 if every discovered test exits 0, 1 otherwise (or if
# no tests are discovered — the empty-suite case is treated as a
# regression, since it would mean the scripts/ dir was inadvertently
# wiped or renamed).
#
# Usage:
#   scripts/run_shell_tests.sh                 # discover under scripts/
#   scripts/run_shell_tests.sh path/to/dir     # discover under that dir
#
# Env vars:
#   SHELL_TEST_PATTERN  glob for discovery, default 'test_*.sh'
#   SHELL_TEST_QUIET    if set to '1', suppress per-test PASS lines
#                       (failing tests always print their stdout+stderr)

set -uo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
search_dir="${1:-$repo_root/scripts}"
pattern="${SHELL_TEST_PATTERN:-test_*.sh}"
quiet="${SHELL_TEST_QUIET:-0}"

self_basename="$(basename "${BASH_SOURCE[0]}")"

if [ ! -d "$search_dir" ]; then
  echo "run_shell_tests.sh: search dir does not exist: $search_dir" >&2
  exit 1
fi

# Discover. Use find (not a glob) so an empty directory doesn't leave
# the literal pattern in the list under `set -u` + no-nullglob defaults.
# -maxdepth 1 keeps discovery non-recursive to match the Python
# `unittest discover -s scripts` behavior wired in validate-formulae.yml.
mapfile -d '' -t test_files < <(
  find "$search_dir" -maxdepth 1 -type f -name "$pattern" -print0 | sort -z
)

# Guard against a runner accidentally executing itself if someone
# renames it to match the discovery pattern (e.g. test_runner.sh).
filtered=()
for f in "${test_files[@]}"; do
  if [ "$(basename "$f")" = "$self_basename" ]; then
    continue
  fi
  filtered+=("$f")
done
test_files=("${filtered[@]}")

total="${#test_files[@]}"
if [ "$total" -eq 0 ]; then
  echo "run_shell_tests.sh: no tests matched '$pattern' under $search_dir" >&2
  exit 1
fi

pass=0
fail=0
failed_names=()

for tfile in "${test_files[@]}"; do
  tname="$(basename "$tfile")"
  # Capture stdout+stderr — we replay it on failure so the caller can
  # see which assertion tripped without re-running by hand.
  output="$(bash "$tfile" 2>&1)"
  rc=$?
  if [ "$rc" -eq 0 ]; then
    pass=$((pass + 1))
    if [ "$quiet" != "1" ]; then
      echo "PASS $tname"
    fi
  else
    fail=$((fail + 1))
    failed_names+=("$tname")
    echo "FAIL $tname (exit $rc)"
    # Indent replay so it doesn't get confused with the runner's own
    # top-level PASS/FAIL/summary lines.
    printf '%s\n' "$output" | sed 's/^/    /'
  fi
done

echo
echo "run_shell_tests.sh summary: $pass passed, $fail failed, $total total"
if [ "$fail" -ne 0 ]; then
  echo "Failed tests:"
  for n in "${failed_names[@]}"; do
    echo "  - $n"
  done
  exit 1
fi
exit 0
