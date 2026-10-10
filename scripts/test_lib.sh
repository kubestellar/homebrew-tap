#!/usr/bin/env bash
# test_lib.sh — shared scaffolding for scripts/test_*.sh regression tests.
#
# Every scripts/test_*.sh file independently re-implemented the same
# handful of blocks: REPO_ROOT resolution, a fail_count accumulator with
# pass/fail exit logic, a mktemp work-dir with an EXIT cleanup trap, and
# byte-identical fake Homebrew formula fixtures. This file centralizes
# that scaffolding so each test file only needs to define its own cases.
#
# Usage: source this file from a scripts/test_*.sh after `set -uo
# pipefail`, then call:
#   REPO_ROOT="$(repo_root)"      — resolve the repository root
#   make_work_dir                 — create $work_dir and register cleanup
#   make_fake_formulae <dir> <name>...   — write minimal <Name> < Formula
#                                          stubs (e.g. foo -> class Foo)
#   make_stub_brew <dir> <failing> <exit_code> [<output>]
#                                  — write a `brew audit --strict` PATH-shim
#                                    that fails only for <failing>
#   fail <name> <message>         — record and print a failure
#   assert_grep <name> <haystack> <pattern> <message>
#   assert_contains <name> <haystack> <needle>
#   assert_not_contains <name> <haystack> <needle>
#   assert_exit_code <name> <expected> <actual> [message]
#   finish <label>                — print the pass/fail summary and exit
#
# This file is meant to be sourced, not executed directly.

# repo_root — print the repository root, resolved relative to the
# sourcing test script's own location (BASH_SOURCE[1] is the caller).
repo_root() {
  (cd "$(dirname "${BASH_SOURCE[1]}")/.." && pwd)
}

fail_count=0

# make_work_dir — create a fresh temp directory in $work_dir and arrange
# for it to be removed on the calling script's exit.
make_work_dir() {
  work_dir="$(mktemp -d)"
  trap 'rm -rf "$work_dir"' EXIT
}

# make_fake_formulae <dir> <name>... — write a minimal Homebrew formula
# stub "<dir>/<name>.rb" for each <name>, with the Ruby class name being
# <name> with its first letter upper-cased (foo -> class Foo < Formula).
make_fake_formulae() {
  local dir="$1"; shift
  mkdir -p "$dir"
  local name class_name
  for name in "$@"; do
    class_name="$(tr '[:lower:]' '[:upper:]' <<< "${name:0:1}")${name:1}"
    printf 'class %s < Formula\nend\n' "$class_name" > "$dir/${name}.rb"
  done
}

# _make_fixture <dir> <name>... — build a self-contained tap fixture in
# <dir> by copying $SCRIPT_SOURCE/$LIB_SOURCE (set by the caller) in and
# initialising a real git repo (so `git log` works). Fixture layout:
#   <dir>/scripts/<basename of $SCRIPT_SOURCE>
#   <dir>/scripts/lib_emit_summary.sh
#   <dir>/Formula/<name>.rb          (one per name in $2..$n)
_make_fixture() {
  local dir="$1"; shift
  mkdir -p "$dir/scripts" "$dir/Formula"
  cp "$SCRIPT_SOURCE" "$dir/scripts/$(basename "$SCRIPT_SOURCE")"
  cp "$LIB_SOURCE" "$dir/scripts/lib_emit_summary.sh"
  chmod +x "$dir/scripts/$(basename "$SCRIPT_SOURCE")"
  for name in "$@"; do
    printf 'class %s < Formula\nend\n' "$name" > "$dir/Formula/${name}.rb"
  done
  git -C "$dir" init -q -b main 2>/dev/null || git -C "$dir" init -q
  git -C "$dir" -c user.email=t@t -c user.name=t add -A
  git -C "$dir" -c user.email=t@t -c user.name=t commit -q -m "seed" >/dev/null
}

# make_stub_brew <dir> <failing_formula_or_empty> <exit_code> [<output>] —
# write a `brew audit --strict <tap>/<name>` PATH-shim to "<dir>/brew" that
# fails with <exit_code> only when <name> == <failing_formula_or_empty>;
# every other formula (and an empty <failing_formula_or_empty>) always
# succeeds. When given, <output> is printed to stdout (as brew audit's
# problem report) before the stub exits with <exit_code> for the failing
# formula. Any other `brew` subcommand always exits 0.
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

# fail <name> <message> — print a FAIL line and increment fail_count.
fail() {
  local name="$1" message="$2"
  echo "FAIL ($name): $message"
  fail_count=$((fail_count + 1))
}

# assert_grep <name> <haystack> <pattern> <message> — fail unless
# <haystack> contains <pattern> (a basic grep -q pattern).
assert_grep() {
  local name="$1" haystack="$2" pattern="$3" message="$4"
  if ! printf '%s' "$haystack" | grep -q "$pattern"; then
    fail "$name" "$message"
    return 1
  fi
  return 0
}

# assert_contains <name> <haystack> <needle> — fail unless <haystack>
# contains the literal substring <needle> (grep -qF). Dumps <haystack>
# on failure so the diagnostic includes the actual rendered output.
assert_contains() {
  local name="$1" haystack="$2" needle="$3"
  if ! printf '%s' "$haystack" | grep -qF "$needle"; then
    echo "FAIL ($name): expected output to contain: $needle"
    echo "--- output ---"
    printf '%s\n' "$haystack"
    echo "--------------"
    fail_count=$((fail_count + 1))
    return 1
  fi
  return 0
}

# assert_not_contains <name> <haystack> <needle> — fail if <haystack>
# contains the literal substring <needle>. Dumps <haystack> on failure
# so the diagnostic shows what leaked in.
assert_not_contains() {
  local name="$1" haystack="$2" needle="$3"
  if printf '%s' "$haystack" | grep -qF "$needle"; then
    echo "FAIL ($name): expected output to NOT contain: $needle"
    echo "--- output ---"
    printf '%s\n' "$haystack"
    echo "--------------"
    fail_count=$((fail_count + 1))
    return 1
  fi
  return 0
}

# assert_exit_code <name> <expected> <actual> [message] — fail unless
# <actual> equals <expected>. The optional [message] replaces the default
# diagnostic.
assert_exit_code() {
  local name="$1" expected="$2" actual="$3" message="${4:-}"
  if [ "$actual" -ne "$expected" ]; then
    fail "$name" "${message:-expected exit $expected, got $actual}"
    return 1
  fi
  return 0
}

# finish <label> — print the final pass/fail summary for <label> and
# exit 0 if no assertions failed, 1 otherwise.
finish() {
  local label="$1"
  if [ "$fail_count" -eq 0 ]; then
    echo "All $label tests passed."
    exit 0
  else
    echo "$fail_count $label test(s) failed."
    exit 1
  fi
}
