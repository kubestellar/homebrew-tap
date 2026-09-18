#!/usr/bin/env bash
# test_brew_tap_setup.sh — regression tests for scripts/brew_tap_setup.sh.
#
# Guards the "untrusted tap" tolerance contract (see #322 postmortem
# referenced in brew-ci.yml): brew_tap_setup.sh must trust the tap when
# `brew trust` is supported (regardless of whether the initial `brew tap`
# call itself succeeded or failed), and must only hard-fail with exit 1
# when trust is unsupported AND the tap call failed. Stubs `brew` via a
# PATH-shim, mirroring scripts/test_brew_ci_summary_brew_path.sh.
#
# Usage: scripts/test_brew_tap_setup.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

# shellcheck source=scripts/test_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test_lib.sh"

REPO_ROOT="$(repo_root)"
SCRIPT="$REPO_ROOT/scripts/brew_tap_setup.sh"

make_work_dir

# make_stub_brew <dir> <tap_exit> <trust_help_exit> <trust_exit>
# Creates a `brew` executable and a companion `<dir>/calls.log` recording
# every subcommand invoked (one per line), so tests can assert ordering
# (untap before tap before trust) as well as exit-code propagation.
make_stub_brew() {
  local dir="$1" tap_exit="$2" trust_help_exit="$3" trust_exit="$4"
  mkdir -p "$dir"
  cat > "$dir/brew" <<STUB
#!/usr/bin/env bash
echo "\$*" >> "$dir/calls.log"
case "\$1" in
  untap)
    exit 0
    ;;
  tap)
    exit $tap_exit
    ;;
  trust)
    if [ "\$2" = "--help" ]; then
      exit $trust_help_exit
    fi
    exit $trust_exit
    ;;
esac
exit 0
STUB
  chmod +x "$dir/brew"
}

# --- Case 1: tap succeeds, trust supported -> trust called, exit 0 ---
stub1="$work_dir/stub1"
make_stub_brew "$stub1" 0 0 0
output=$(env -i PATH="$stub1:/usr/bin:/bin" TAP_DIR="$work_dir/checkout1" \
  bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "tap-ok trust-supported exit" 0 "$code"
assert_contains "tap-ok trust-supported trust called" "$(cat "$stub1/calls.log")" "trust kubestellar/tap"

# --- Case 2: tap succeeds, trust unsupported -> exit 0, no trust call ---
stub2="$work_dir/stub2"
make_stub_brew "$stub2" 0 1 0
output=$(env -i PATH="$stub2:/usr/bin:/bin" TAP_DIR="$work_dir/checkout2" \
  bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "tap-ok trust-unsupported exit" 0 "$code"
assert_not_contains "tap-ok trust-unsupported no plain trust call" "$(cat "$stub2/calls.log")" "trust kubestellar/tap"

# --- Case 3: tap fails, trust supported -> trust called, exit 0 ---
stub3="$work_dir/stub3"
make_stub_brew "$stub3" 1 0 0
output=$(env -i PATH="$stub3:/usr/bin:/bin" TAP_DIR="$work_dir/checkout3" \
  bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "tap-failed trust-supported exit" 0 "$code"
assert_contains "tap-failed trust-supported trust called" "$(cat "$stub3/calls.log")" "trust kubestellar/tap"

# --- Case 4: tap fails, trust unsupported -> exit 1 ---
stub4="$work_dir/stub4"
make_stub_brew "$stub4" 1 1 0
output=$(env -i PATH="$stub4:/usr/bin:/bin" TAP_DIR="$work_dir/checkout4" \
  bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "tap-failed trust-unsupported exit" 1 "$code"

# --- Case 5: tap succeeds, trust supported, trust itself fails -> propagate ---
stub5="$work_dir/stub5"
make_stub_brew "$stub5" 0 0 3
output=$(env -i PATH="$stub5:/usr/bin:/bin" TAP_DIR="$work_dir/checkout5" \
  bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "trust-call-fails propagates its exit code" 3 "$code"

# --- Case 6: untap is attempted before tap, and tap before trust ---
stub6="$work_dir/stub6"
make_stub_brew "$stub6" 0 0 0
env -i PATH="$stub6:/usr/bin:/bin" TAP_DIR="$work_dir/checkout6" \
  bash "$SCRIPT" >/dev/null 2>&1
mapfile -t calls < "$stub6/calls.log"
assert_contains "ordering: first call is untap" "${calls[0]}" "untap kubestellar/tap"
assert_contains "ordering: second call is tap" "${calls[1]}" "tap kubestellar/tap"

if [ "$fail_count" -gt 0 ]; then
  echo "$fail_count assertion(s) failed"
  exit 1
fi
echo "All brew_tap_setup.sh assertions passed"
