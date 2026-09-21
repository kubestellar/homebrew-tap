#!/usr/bin/env bash
# test_brew_untap_self.sh — regression tests for
# scripts/brew_untap_self.sh.
#
# Guards the four regression scenarios behind the #322/#426/#486
# postmortems documented in the script itself: the tap directory left
# non-empty after retapping (#322), formulae still installed blocking a
# plain `brew untap` (#426), the tap directory removed but a symlink
# still expected by setup-homebrew's post-cleanup (#486), and the happy
# path. Also guards that this step never fails (mirrors the workflow's
# `if: always()` best-effort cleanup contract) even when every brew
# subcommand it calls fails. Stubs `brew` via a PATH-shim, mirroring
# scripts/test_brew_ci_summary_brew_path.sh.
#
# Usage: scripts/test_brew_untap_self.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

# shellcheck source=scripts/test_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test_lib.sh"

REPO_ROOT="$(repo_root)"
SCRIPT="$REPO_ROOT/scripts/brew_untap_self.sh"

make_work_dir

# make_stub_brew <dir> <tap_dir> <untap_exit> <repo_exit>
# Creates a `brew` executable recording every call to <dir>/calls.log.
# `brew uninstall` and `brew untap` exit with <untap_exit> (simulating
# #426's "refusing to untap" failure when non-zero); `brew --repo`
# prints <tap_dir> and exits with <repo_exit> (simulating an unknown tap
# when non-zero, in which case it prints nothing).
make_stub_brew() {
  local dir="$1" tap_dir="$2" untap_exit="$3" repo_exit="${4:-0}"
  mkdir -p "$dir"
  cat > "$dir/brew" <<STUB
#!/usr/bin/env bash
echo "\$*" >> "$dir/calls.log"
case "\$1" in
  uninstall)
    exit 0
    ;;
  untap)
    exit $untap_exit
    ;;
  --repo)
    if [ $repo_exit -eq 0 ]; then
      printf '%s' "$tap_dir"
    fi
    exit $repo_exit
    ;;
esac
exit 0
STUB
  chmod +x "$dir/brew"
}

formula_dir="$work_dir/Formula"
make_fake_formulae "$formula_dir" alpha beta

workspace="$work_dir/workspace"
mkdir -p "$workspace"

# --- Case 1 (#322): tap dir exists as a non-empty directory -> removed
# and replaced with a symlink to GITHUB_WORKSPACE ---
tap_dir1="$work_dir/tapdir1"
mkdir -p "$tap_dir1/some-stale-file-dir"
stub1="$work_dir/stub1"
make_stub_brew "$stub1" "$tap_dir1" 0 0
output=$(env -i PATH="$stub1:/usr/bin:/bin" FORMULA_DIR="$formula_dir" GITHUB_WORKSPACE="$workspace" \
  bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "nonempty-dir always exits 0" 0 "$code"
if [ -L "$tap_dir1" ]; then
  echo "OK (nonempty-dir replaced with symlink)"
else
  fail "nonempty-dir replaced with symlink" "expected $tap_dir1 to be a symlink"
fi
assert_contains "nonempty-dir uninstalls alpha" "$(cat "$stub1/calls.log")" "uninstall --force --ignore-dependencies kubestellar/tap/alpha"

# --- Case 2 (#426): `brew untap` fails (formulae still installed) ->
# tolerated, tap dir still forced-removed and symlink recreated ---
tap_dir2="$work_dir/tapdir2"
mkdir -p "$tap_dir2/leftover"
stub2="$work_dir/stub2"
make_stub_brew "$stub2" "$tap_dir2" 1 0
output=$(env -i PATH="$stub2:/usr/bin:/bin" FORMULA_DIR="$formula_dir" GITHUB_WORKSPACE="$workspace" \
  bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "untap-fails still exits 0" 0 "$code"
if [ -L "$tap_dir2" ] && [ "$(readlink "$tap_dir2")" = "$workspace" ]; then
  echo "OK (untap-fails symlink points at workspace)"
else
  fail "untap-fails symlink points at workspace" "expected $tap_dir2 -> $workspace"
fi

# --- Case 3 (#486): tap dir already removed, but a symlink is still
# expected by setup-homebrew's post-cleanup -> recreated ---
tap_dir3="$work_dir/tapdir3"
mkdir -p "$(dirname "$tap_dir3")"
# tap_dir3 itself does not exist yet.
stub3="$work_dir/stub3"
make_stub_brew "$stub3" "$tap_dir3" 0 0
output=$(env -i PATH="$stub3:/usr/bin:/bin" FORMULA_DIR="$formula_dir" GITHUB_WORKSPACE="$workspace" \
  bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "already-removed exits 0" 0 "$code"
if [ -L "$tap_dir3" ] && [ "$(readlink "$tap_dir3")" = "$workspace" ]; then
  echo "OK (already-removed symlink recreated)"
else
  fail "already-removed symlink recreated" "expected $tap_dir3 -> $workspace to exist"
fi

# --- Case 4: happy path, `brew --repo` reports no tap (already gone) ->
# script exits 0 without touching any path ---
stub4="$work_dir/stub4"
make_stub_brew "$stub4" "" 0 1
# shellcheck disable=SC2034  # captured for parity with other cases; only the exit code matters here
output=$(env -i PATH="$stub4:/usr/bin:/bin" FORMULA_DIR="$formula_dir" GITHUB_WORKSPACE="$workspace" \
  bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "no-tap-reported exits 0" 0 "$code"

if [ "$fail_count" -gt 0 ]; then
  echo "$fail_count assertion(s) failed"
  exit 1
fi
echo "All brew_untap_self.sh assertions passed"
