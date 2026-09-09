#!/usr/bin/env bash
# test_brew_ci_summary.sh — regression tests for brew_ci_summary.sh (see
# homebrew-tap#380). Stubs `brew list --formula` via a fake `brew` prepended
# to PATH so these tests don't require a real Homebrew install, and stubs
# FORMULA_DIR with throwaway fixture .rb files so they don't touch this
# repo's real Formula/ directory.
#
# Plain-bash assertions (no bats dependency) to match this repo's existing
# scripts/*.sh, which likewise avoid adding new test tooling.
#
# Usage: scripts/test_brew_ci_summary.sh
# Exit status: 0 if every case passes, 1 otherwise.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/brew_ci_summary.sh"

pass_count=0
fail_count=0

assert_contains() {
  local haystack="$1" needle="$2" case_name="$3"
  if [[ "$haystack" == *"$needle"* ]]; then
    pass_count=$((pass_count + 1))
  else
    fail_count=$((fail_count + 1))
    echo "FAIL: $case_name"
    echo "  expected to find: $needle"
    echo "  in output:        $haystack"
  fi
}

assert_exit_code() {
  local actual="$1" expected="$2" case_name="$3"
  if [ "$actual" -eq "$expected" ]; then
    pass_count=$((pass_count + 1))
  else
    fail_count=$((fail_count + 1))
    echo "FAIL: $case_name (expected exit $expected, got $actual)"
  fi
}

# Fixture: a fake `brew` on PATH so tests never invoke the real Homebrew.
# BREW_STUB_INSTALLED (newline-separated) controls what `brew list
# --formula` reports as installed.
setup_fake_brew() {
  local bindir="$1"
  mkdir -p "$bindir"
  cat >"$bindir/brew" <<'EOF'
#!/usr/bin/env bash
if [ "$1" = "list" ] && [ "$2" = "--formula" ]; then
  printf '%s\n' "${BREW_STUB_INSTALLED:-}"
  exit 0
fi
echo "fake brew: unsupported args: $*" >&2
exit 1
EOF
  chmod +x "$bindir/brew"
}

make_formula_dir() {
  local dir="$1"
  shift
  mkdir -p "$dir"
  for name in "$@"; do
    echo "class $name < Formula; end" >"$dir/$name.rb"
  done
}

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

FAKE_BIN="$WORKDIR/bin"
setup_fake_brew "$FAKE_BIN"

# Case 1: all formulae installed.
FORMULA_DIR="$WORKDIR/all-installed"
make_formula_dir "$FORMULA_DIR" kc-agent kubestellar-deploy
out="$(PATH="$FAKE_BIN:$PATH" BREW_STUB_INSTALLED=$'kc-agent\nkubestellar-deploy' \
  JOB_STATUS=success MATRIX_OS=ubuntu-latest FORMULA_DIR="$FORMULA_DIR" "$SCRIPT")"
rc=$?
assert_exit_code "$rc" 0 "all-installed: exit code"
assert_contains "$out" '"status":"success"' "all-installed: status field"
assert_contains "$out" '"os":"ubuntu-latest"' "all-installed: os field"
assert_contains "$out" '"formula_count":2' "all-installed: formula_count"
assert_contains "$out" '"installed_count":2' "all-installed: installed_count"

# Case 2: partial install (one of two formulae installed).
FORMULA_DIR="$WORKDIR/partial-installed"
make_formula_dir "$FORMULA_DIR" kc-agent kubestellar-ops
out="$(PATH="$FAKE_BIN:$PATH" BREW_STUB_INSTALLED='kc-agent' \
  JOB_STATUS=failure MATRIX_OS=macos-latest FORMULA_DIR="$FORMULA_DIR" "$SCRIPT")"
rc=$?
assert_exit_code "$rc" 0 "partial-installed: exit code"
assert_contains "$out" '"status":"failure"' "partial-installed: status field"
assert_contains "$out" '"formula_count":2' "partial-installed: formula_count"
assert_contains "$out" '"installed_count":1' "partial-installed: installed_count"

# Case 3: empty Formula directory.
FORMULA_DIR="$WORKDIR/empty"
mkdir -p "$FORMULA_DIR"
out="$(PATH="$FAKE_BIN:$PATH" BREW_STUB_INSTALLED='' \
  JOB_STATUS=success MATRIX_OS=ubuntu-latest FORMULA_DIR="$FORMULA_DIR" "$SCRIPT")"
rc=$?
assert_exit_code "$rc" 0 "empty-dir: exit code"
assert_contains "$out" '"formula_count":0' "empty-dir: formula_count"
assert_contains "$out" '"installed_count":0' "empty-dir: installed_count"

# Case 4: missing JOB_STATUS should fail with exit 2, no summary line.
FORMULA_DIR="$WORKDIR/all-installed"
set +e
out="$(PATH="$FAKE_BIN:$PATH" BREW_STUB_INSTALLED='' \
  MATRIX_OS=ubuntu-latest FORMULA_DIR="$FORMULA_DIR" "$SCRIPT" 2>&1)"
rc=$?
set -e
assert_exit_code "$rc" 2 "missing-JOB_STATUS: exit code"

# Case 5: 'brew' missing from PATH should fail with exit 2.
set +e
out="$(PATH="/usr/bin:/bin" JOB_STATUS=success MATRIX_OS=ubuntu-latest \
  FORMULA_DIR="$FORMULA_DIR" "$SCRIPT" 2>&1)"
rc=$?
set -e
assert_exit_code "$rc" 2 "missing-brew: exit code"

echo "TEST_BREW_CI_SUMMARY: {\"status\":\"$([ "$fail_count" -eq 0 ] && echo pass || echo fail)\",\"pass_count\":${pass_count},\"fail_count\":${fail_count}}"

[ "$fail_count" -eq 0 ]
