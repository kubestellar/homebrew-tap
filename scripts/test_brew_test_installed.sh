#!/usr/bin/env bash
# test_brew_test_installed.sh — regression tests for
# scripts/brew_test_installed.sh.
#
# Guards the "skip formulae that were never installed" contract: a
# formula absent from the installed list must be skipped with an
# `::notice::` and exit 0 rather than failing, while an installed
# formula's `brew test` failure must propagate its exit code and stop
# before any later formula. Uses INSTALLED_FORMULAE directly (as
# scripts/test_brew_ci_summary.sh does) rather than a `brew list` stub,
# since that is the script's own test-injection seam.
#
# Usage: scripts/test_brew_test_installed.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

# shellcheck source=scripts/test_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test_lib.sh"

REPO_ROOT="$(repo_root)"
SCRIPT="$REPO_ROOT/scripts/brew_test_installed.sh"

make_work_dir

# make_stub_brew <dir> <test_fail_formula_or_empty> <exit_code>
make_stub_brew() {
  local dir="$1" fail_formula="$2" exit_code="$3"
  mkdir -p "$dir"
  cat > "$dir/brew" <<STUB
#!/usr/bin/env bash
if [ "\$1" = "test" ]; then
  name="\${2##*/}"
  if [ "\$name" = "$fail_formula" ]; then
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

stub="$work_dir/stub"

# --- Case 1: none installed -> every formula skipped, exit 0 ---
make_stub_brew "$stub" "" 0
output=$(env -i PATH="$stub:/usr/bin:/bin" FORMULA_DIR="$formula_dir" INSTALLED_FORMULAE="" \
  bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "none-installed exit" 0 "$code"
assert_contains "none-installed skips alpha" "$output" "::notice title=Skipping test::kubestellar/tap/alpha was not installed"
assert_contains "none-installed skips beta" "$output" "::notice title=Skipping test::kubestellar/tap/beta was not installed"
assert_contains "none-installed skips gamma" "$output" "::notice title=Skipping test::kubestellar/tap/gamma was not installed"

# --- Case 2: all installed, all pass -> exit 0, one group per formula ---
output=$(env -i PATH="$stub:/usr/bin:/bin" FORMULA_DIR="$formula_dir" \
  INSTALLED_FORMULAE="$(printf 'alpha\nbeta\ngamma')" bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "all-installed-pass exit" 0 "$code"
group_count=$(printf '%s\n' "$output" | grep -c '^::group::brew test')
assert_exit_code "all-installed-pass group count" 3 "$group_count"

# --- Case 3: beta installed but its test fails -> propagate exit code, stop before gamma ---
make_stub_brew "$stub" "beta" 9
output=$(env -i PATH="$stub:/usr/bin:/bin" FORMULA_DIR="$formula_dir" \
  INSTALLED_FORMULAE="$(printf 'alpha\nbeta\ngamma')" bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "beta-test-fails propagates exit code" 9 "$code"
assert_not_contains "beta-test-fails does not reach gamma" "$output" "brew test kubestellar/tap/gamma"

# --- Case 4: only alpha installed -> beta/gamma skipped, alpha tested ---
make_stub_brew "$stub" "" 0
output=$(env -i PATH="$stub:/usr/bin:/bin" FORMULA_DIR="$formula_dir" \
  INSTALLED_FORMULAE="alpha" bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "only-alpha-installed exit" 0 "$code"
assert_contains "only-alpha-installed tests alpha" "$output" "::group::brew test kubestellar/tap/alpha"
assert_contains "only-alpha-installed skips beta" "$output" "::notice title=Skipping test::kubestellar/tap/beta was not installed"

if [ "$fail_count" -gt 0 ]; then
  echo "$fail_count assertion(s) failed"
  exit 1
fi
echo "All brew_test_installed.sh assertions passed"
