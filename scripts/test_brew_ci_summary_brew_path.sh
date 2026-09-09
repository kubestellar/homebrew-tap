#!/usr/bin/env bash
# test_brew_ci_summary_brew_path.sh — branch coverage for the
# `command -v brew` arm of scripts/brew_ci_summary.sh.
#
# The existing tests cover:
#   test_brew_ci_summary.sh
#     - INSTALLED_FORMULAE set (empty / non-empty / matching / non-matching)
#     - defaults-when-unset (JOB_STATUS/MATRIX_OS)
#   test_brew_ci_summary_branches.sh
#     - missing / empty FORMULA_DIR
#     - INSTALLED_FORMULAE unset AND `brew` NOT on PATH (env -i)
#     - INSTALLED_FORMULAE names a formula not in FORMULA_DIR
#
# What NONE of them cover is the elif arm at the middle of the script:
#
#   if [ -n "${INSTALLED_FORMULAE+x}" ]; then
#     installed_list="$INSTALLED_FORMULAE"
#   elif command -v brew >/dev/null 2>&1; then
#     installed_list="$(brew list --formula 2>/dev/null || true)"
#   fi
#
# That branch fires only when INSTALLED_FORMULAE is UNSET *and* `brew` is
# on PATH — the realistic runtime path in the GitHub Actions runner, since
# brew-ci.yml never sets INSTALLED_FORMULAE. Every existing test either
# sets INSTALLED_FORMULAE (even to "") or strips brew from PATH, so this
# arm is dead as far as CI is concerned. The tests below install a stub
# `brew` and exercise it.
#
# Six sub-cases mirror the harness style already in place:
#   1. stub `brew list --formula` returns nothing  -> installed_count=0
#   2. stub returns one matching formula          -> installed_count=1
#   3. stub returns both matching formulae        -> installed_count=2
#   4. stub returns unrelated formulae only       -> installed_count=0
#   5. stub `brew list` exits non-zero            -> installed_count=0
#                                                    (the `|| true` guard)
#   6. INSTALLED_FORMULAE=""  (set but empty)     -> installed_count=0,
#      even with a stub brew that would report matches — the "set" arm
#      wins over the `elif command -v brew` arm.
#
# Usage: scripts/test_brew_ci_summary_brew_path.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/brew_ci_summary.sh"

fail_count=0
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

# ---------------------------------------------------------------------
# Fixture: a 2-formula Formula directory (foo + bar), matching the shape
# used by test_brew_ci_summary.sh.
# ---------------------------------------------------------------------
formula_dir="$work_dir/Formula"
mkdir -p "$formula_dir"
printf 'class Foo < Formula\nend\n' > "$formula_dir/foo.rb"
printf 'class Bar < Formula\nend\n' > "$formula_dir/bar.rb"

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

# make_stub_brew <dir> <list_output> <exit_code>
# Creates a `brew` executable that, given the `list --formula` subcommand,
# prints <list_output> (newline-joined string) and exits with <exit_code>.
# Any other subcommand yields exit 0 with no output.
make_stub_brew() {
  local dir="$1" list_output="$2" exit_code="$3"
  mkdir -p "$dir"
  cat > "$dir/brew" <<STUB
#!/usr/bin/env bash
if [ "\$1" = "list" ] && [ "\$2" = "--formula" ]; then
  printf '%s' "$list_output"
  exit $exit_code
fi
exit 0
STUB
  chmod +x "$dir/brew"
}

# run_case <name> <installed_formulae_arg> <stub_dir> <expected_exit> <expected_installed_count>
# installed_formulae_arg is either "-" (unset) or a literal string
# (including "" for set-empty). Uses env -i so INSTALLED_FORMULAE cannot
# leak from the surrounding shell.
run_case() {
  local name="$1" installed="$2" stub_dir="$3" \
    expected_exit="$4" expected_installed_count="$5"

  local output exit_code
  if [ "$installed" = "-" ]; then
    # Unset: do NOT pass INSTALLED_FORMULAE at all.
    output=$(env -i PATH="$stub_dir:/usr/bin:/bin" \
      FORMULA_DIR="$formula_dir" JOB_STATUS="success" MATRIX_OS="ubuntu-latest" \
      bash "$SCRIPT" 2>&1)
  else
    output=$(env -i PATH="$stub_dir:/usr/bin:/bin" \
      FORMULA_DIR="$formula_dir" JOB_STATUS="success" MATRIX_OS="ubuntu-latest" \
      INSTALLED_FORMULAE="$installed" bash "$SCRIPT" 2>&1)
  fi
  exit_code=$?

  if ! printf '%s' "$output" | grep -q '^BREW_CI_SUMMARY: {'; then
    echo "FAIL ($name): missing BREW_CI_SUMMARY: line. Got: $output"
    fail_count=$((fail_count + 1)); return
  fi
  if ! printf '%s' "$output" | grep -q '"formula_count":2'; then
    echo "FAIL ($name): expected formula_count=2. Got: $output"
    fail_count=$((fail_count + 1)); return
  fi
  if ! printf '%s' "$output" | grep -q "\"installed_count\":$expected_installed_count"; then
    echo "FAIL ($name): expected installed_count=$expected_installed_count. Got: $output"
    fail_count=$((fail_count + 1)); return
  fi
  if [ "$exit_code" -ne "$expected_exit" ]; then
    echo "FAIL ($name): expected exit=$expected_exit, got exit=$exit_code"
    fail_count=$((fail_count + 1)); return
  fi
  local line_count
  line_count=$(printf '%s' "$output" | grep -c '^BREW_CI_SUMMARY: {')
  if [ "$line_count" -ne 1 ]; then
    echo "FAIL ($name): expected exactly 1 summary line, got $line_count"
    fail_count=$((fail_count + 1)); return
  fi
  echo "OK ($name)"
}

# ---------------------------------------------------------------------
# Case 1: `brew list --formula` returns nothing.
# ---------------------------------------------------------------------
stub1="$work_dir/stub1"
make_stub_brew "$stub1" "" 0
run_case "brew-list-empty" "-" "$stub1" 0 0

# ---------------------------------------------------------------------
# Case 2: `brew list --formula` returns one matching formula.
# ---------------------------------------------------------------------
stub2="$work_dir/stub2"
make_stub_brew "$stub2" "foo" 0
run_case "brew-list-one-match" "-" "$stub2" 0 1

# ---------------------------------------------------------------------
# Case 3: `brew list --formula` returns both matching formulae.
# ---------------------------------------------------------------------
stub3="$work_dir/stub3"
make_stub_brew "$stub3" "$(printf 'foo\nbar')" 0
run_case "brew-list-both-match" "-" "$stub3" 0 2

# ---------------------------------------------------------------------
# Case 4: `brew list --formula` returns only unrelated formulae.
# ---------------------------------------------------------------------
stub4="$work_dir/stub4"
make_stub_brew "$stub4" "$(printf 'jq\nripgrep\ngit')" 0
run_case "brew-list-no-overlap" "-" "$stub4" 0 0

# ---------------------------------------------------------------------
# Case 5: `brew list --formula` exits non-zero (the `|| true` guard).
# ---------------------------------------------------------------------
stub5="$work_dir/stub5"
make_stub_brew "$stub5" "" 1
run_case "brew-list-exits-nonzero" "-" "$stub5" 0 0

# ---------------------------------------------------------------------
# Case 6: INSTALLED_FORMULAE="" wins over stub brew.
# The elif arm must NOT run when the variable is set-but-empty.
# ---------------------------------------------------------------------
stub6="$work_dir/stub6"
make_stub_brew "$stub6" "$(printf 'foo\nbar')" 0
run_case "installed-empty-shadows-brew" "" "$stub6" 0 0

# ---------------------------------------------------------------------
if [ "$fail_count" -eq 0 ]; then
  echo "All brew_ci_summary.sh brew-PATH branch tests passed."
  exit 0
else
  echo "$fail_count brew_ci_summary.sh brew-PATH branch test(s) failed."
  exit 1
fi
