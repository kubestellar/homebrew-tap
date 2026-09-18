#!/usr/bin/env bash
# test_brew_install_smoke.sh — regression tests for
# scripts/brew_install_smoke.sh.
#
# Guards the pull_request-vs-push divergence: a `brew fetch` failure must
# be tolerated (skip + `::notice::` + exit 0 + continue to the next
# formula) only when EVENT_NAME=pull_request, and must hard-fail
# (`::error::` + exit 1, stopping before any later formula) for every
# other event. Also guards that a successful fetch proceeds to `brew
# install`, and that an `install` failure propagates its exit code.
# Stubs `brew` via a PATH-shim, mirroring
# scripts/test_brew_ci_summary_brew_path.sh.
#
# Usage: scripts/test_brew_install_smoke.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

# shellcheck source=scripts/test_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test_lib.sh"

REPO_ROOT="$(repo_root)"
SCRIPT="$REPO_ROOT/scripts/brew_install_smoke.sh"

make_work_dir

# make_stub_brew <dir> <fetch_fail_formula_or_empty> <install_fail_formula_or_empty> <install_exit>
make_stub_brew() {
  local dir="$1" fetch_fail="$2" install_fail="$3" install_exit="$4"
  mkdir -p "$dir"
  cat > "$dir/brew" <<STUB
#!/usr/bin/env bash
if [ "\$1" = "fetch" ]; then
  name="\${3##*/}"
  if [ "\$name" = "$fetch_fail" ]; then
    exit 1
  fi
  exit 0
fi
if [ "\$1" = "install" ]; then
  name="\${3##*/}"
  if [ "\$name" = "$install_fail" ]; then
    exit $install_exit
  fi
  exit 0
fi
exit 0
STUB
  chmod +x "$dir/brew"
}

formula_dir="$work_dir/Formula"
make_fake_formulae "$formula_dir" alpha beta gamma

# --- Case 1: happy path, all fetch+install succeed ---
stub1="$work_dir/stub1"
make_stub_brew "$stub1" "" "" 0
output=$(env -i PATH="$stub1:/usr/bin:/bin" FORMULA_DIR="$formula_dir" EVENT_NAME="push" \
  bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "happy path exit" 0 "$code"
assert_contains "happy path installs alpha" "$output" "brew install"

# --- Case 2: beta fetch fails, EVENT_NAME=pull_request -> skip + continue ---
stub2="$work_dir/stub2"
make_stub_brew "$stub2" "beta" "" 0
output=$(env -i PATH="$stub2:/usr/bin:/bin" FORMULA_DIR="$formula_dir" EVENT_NAME="pull_request" \
  bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "pr-skip exit" 0 "$code"
assert_contains "pr-skip notice for beta" "$output" "::notice title=Skipping install::Release artifact for kubestellar/tap/beta is not available yet"
assert_contains "pr-skip reaches gamma" "$output" "kubestellar/tap/gamma"

# --- Case 3: beta fetch fails, EVENT_NAME=push -> hard fail, stop before gamma ---
stub3="$work_dir/stub3"
make_stub_brew "$stub3" "beta" "" 0
output=$(env -i PATH="$stub3:/usr/bin:/bin" FORMULA_DIR="$formula_dir" EVENT_NAME="push" \
  bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "push-hard-fail exit" 1 "$code"
assert_contains "push-hard-fail error message" "$output" "::error title=Missing release artifact::kubestellar/tap/beta could not be fetched"
assert_not_contains "push-hard-fail does not reach gamma" "$output" "kubestellar/tap/gamma"

# --- Case 4: beta fetch fails, EVENT_NAME=schedule -> also hard fail ---
stub4="$work_dir/stub4"
make_stub_brew "$stub4" "beta" "" 0
output=$(env -i PATH="$stub4:/usr/bin:/bin" FORMULA_DIR="$formula_dir" EVENT_NAME="schedule" \
  bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "schedule-hard-fail exit" 1 "$code"

# --- Case 5: fetch succeeds but install fails -> propagate install's exit code ---
stub5="$work_dir/stub5"
make_stub_brew "$stub5" "" "alpha" 5
output=$(env -i PATH="$stub5:/usr/bin:/bin" FORMULA_DIR="$formula_dir" EVENT_NAME="push" \
  bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "install-fails propagates exit code" 5 "$code"

if [ "$fail_count" -gt 0 ]; then
  echo "$fail_count assertion(s) failed"
  exit 1
fi
echo "All brew_install_smoke.sh assertions passed"
