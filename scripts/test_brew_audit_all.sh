#!/usr/bin/env bash
# test_brew_audit_all.sh — regression tests for scripts/brew_audit_all.sh.
#
# Guards the "stop on first failure, propagate its exit code" contract
# that brew-ci.yml's "brew audit --strict (all formulae)" step relied on
# implicitly via GitHub Actions' default `bash -e` for `run:` blocks: a
# failing `brew audit --strict` must (a) not print that formula's
# `::endgroup::`, (b) skip auditing any later formula, and (c) propagate
# that formula's own exit code. Also guards the happy path emitting one
# `::group::`/`::endgroup::` pair per formula, and the trailing
# `BREW_AUDIT_SUMMARY: {...}` structured record (status/formula_count/
# warned_count/failed_formula) on both the pass and fail paths. Stubs
# `brew` via a PATH-shim, mirroring scripts/test_brew_ci_summary_brew_path.sh.
#
# Usage: scripts/test_brew_audit_all.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

# shellcheck disable=SC2016  # literal backtick/markdown strings in single quotes, not variable expansion
set -uo pipefail

# shellcheck source=scripts/test_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test_lib.sh"

REPO_ROOT="$(repo_root)"
SCRIPT="$REPO_ROOT/scripts/brew_audit_all.sh"

make_work_dir

# make_stub_brew <dir> <failing_formula_or_empty> <exit_code> [<output>]
# Creates a `brew audit --strict <tap>/<name>` stub that fails with
# <exit_code> only when <name> == <failing_formula_or_empty>; every other
# formula (and an empty <failing_formula_or_empty>) always succeeds. When
# given, <output> is printed to stdout (as brew audit's problem report)
# before the stub exits with <exit_code> for the failing formula.
make_stub_brew() {
  local dir="$1" failing="$2" exit_code="$3" formula_output="${4:-}"
  mkdir -p "$dir"
  cat > "$dir/brew" <<STUB
#!/usr/bin/env bash
if [ "\$1" = "audit" ]; then
  name="\${3##*/}"
  if [ "\$name" = "$failing" ]; then
    printf '%s\n' "$formula_output"
    exit $exit_code
  fi
  exit 0
fi
exit 0
STUB
  chmod +x "$dir/brew"
}

formula_dir="$work_dir/Formula"
make_fake_formulae "$formula_dir" alpha beta gamma

# --- Case 1: happy path, every formula passes ---
stub1="$work_dir/stub1"
make_stub_brew "$stub1" "" 0
output=$(env -i PATH="$stub1:/usr/bin:/bin" FORMULA_DIR="$formula_dir" bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "happy path exit" 0 "$code"
group_count=$(printf '%s\n' "$output" | grep -c '^::group::brew audit --strict')
endgroup_count=$(printf '%s\n' "$output" | grep -c '^::endgroup::$')
assert_exit_code "happy path group count" 3 "$group_count"
assert_exit_code "happy path endgroup count" 3 "$endgroup_count"
assert_contains "happy path includes alpha" "$output" "kubestellar/tap/alpha"
assert_contains "happy path includes beta" "$output" "kubestellar/tap/beta"
assert_contains "happy path includes gamma" "$output" "kubestellar/tap/gamma"
assert_contains "happy path summary line" "$output" \
  'BREW_AUDIT_SUMMARY: {"status":"pass","formula_count":3,"warned_count":0,"failed_formula":null}'

# --- Case 2: beta fails -> stop before gamma, propagate exit code ---
stub2="$work_dir/stub2"
make_stub_brew "$stub2" "beta" 7
output=$(env -i PATH="$stub2:/usr/bin:/bin" FORMULA_DIR="$formula_dir" bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "beta-fails propagates exit code" 7 "$code"
assert_not_contains "beta-fails does not reach gamma" "$output" "kubestellar/tap/gamma"
endgroup_count=$(printf '%s\n' "$output" | grep -c '^::endgroup::$')
assert_exit_code "beta-fails only alpha's endgroup printed" 1 "$endgroup_count"
assert_contains "beta-fails summary line names beta" "$output" \
  'BREW_AUDIT_SUMMARY: {"status":"fail","formula_count":2,"warned_count":0,"failed_formula":"beta"}'

# --- Case 3: TAP_NAME override is honored ---
stub3="$work_dir/stub3"
make_stub_brew "$stub3" "" 0
output=$(env -i PATH="$stub3:/usr/bin:/bin" FORMULA_DIR="$formula_dir" TAP_NAME="other/tap" \
  bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "tap-name-override exit" 0 "$code"
assert_contains "tap-name-override used in output" "$output" "other/tap/alpha"
assert_not_contains "tap-name-override default tap absent" "$output" "kubestellar/tap/alpha"

# --- Case 4: sole redundant_version finding is a non-fatal known false
# positive (issue #513) -> exit 0, warning emitted, all formulae audited ---
stub4="$work_dir/stub4"
redundant_output='kubestellar/tap/beta
  * Stable: `version 1.2.3` is redundant with version scanned from URL'
make_stub_brew "$stub4" "beta" 1 "$redundant_output"
output=$(env -i PATH="$stub4:/usr/bin:/bin" FORMULA_DIR="$formula_dir" bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "redundant-version-only exit" 0 "$code"
assert_contains "redundant-version-only warns" "$output" "::warning::"
assert_contains "redundant-version-only mentions issue" "$output" "#513"
assert_contains "redundant-version-only still reaches gamma" "$output" "kubestellar/tap/gamma"
endgroup_count=$(printf '%s\n' "$output" | grep -c '^::endgroup::$')
assert_exit_code "redundant-version-only all three endgroups printed" 3 "$endgroup_count"
assert_contains "redundant-version-only summary counts the warning" "$output" \
  'BREW_AUDIT_SUMMARY: {"status":"pass","formula_count":3,"warned_count":1,"failed_formula":null}'

# --- Case 5: redundant_version finding alongside another problem line
# still fails loudly (only a *sole* redundant_version finding is absorbed) ---
stub5="$work_dir/stub5"
mixed_output='kubestellar/tap/beta
  * Stable: `version 1.2.3` is redundant with version scanned from URL
  * some other real audit problem'
make_stub_brew "$stub5" "beta" 3 "$mixed_output"
output=$(env -i PATH="$stub5:/usr/bin:/bin" FORMULA_DIR="$formula_dir" bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "redundant-version-plus-other propagates exit code" 3 "$code"
assert_not_contains "redundant-version-plus-other does not reach gamma" "$output" "kubestellar/tap/gamma"
assert_contains "redundant-version-plus-other summary names beta as failed" "$output" \
  'BREW_AUDIT_SUMMARY: {"status":"fail","formula_count":2,"warned_count":0,"failed_formula":"beta"}'

if [ "$fail_count" -gt 0 ]; then
  echo "$fail_count assertion(s) failed"
  exit 1
fi
echo "All brew_audit_all.sh assertions passed"
