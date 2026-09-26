#!/usr/bin/env bash
# test_compile_requirements_dev.sh — regression tests for
# scripts/compile_requirements_dev.sh.
#
# Guards the header-preservation contract: regenerating the lockfile
# must keep the existing leading comment block of requirements-dev.txt
# byte-identical above the compiled output (pip-compile itself runs with
# --no-header, so without the wrapper the header is silently lost). Also
# guards that a header-less lockfile is refused rather than rewritten,
# and that a failing pip-compile leaves the lockfile untouched. Stubs
# `pip-compile` via a PATH shim, mirroring
# scripts/test_brew_ci_summary_brew_path.sh.
#
# Usage: scripts/test_compile_requirements_dev.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

# shellcheck source=scripts/test_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test_lib.sh"

REPO_ROOT="$(repo_root)"
SCRIPT="$REPO_ROOT/scripts/compile_requirements_dev.sh"

make_work_dir

# make_stub_pip_compile <dir> <exit_code> — create a `pip-compile` shim
# that records its argv, writes a fixed compiled body to the
# --output-file argument, and exits with <exit_code>.
make_stub_pip_compile() {
  local dir="$1" exit_code="$2"
  mkdir -p "$dir"
  cat > "$dir/pip-compile" <<STUB
#!/usr/bin/env bash
echo "\$*" > "$dir/argv.log"
out=""
for a in "\$@"; do
  case "\$a" in
    --output-file=*) out="\${a#--output-file=}" ;;
  esac
done
if [ "$exit_code" -ne 0 ]; then
  exit "$exit_code"
fi
printf 'pytest==9.1.1 \\\\\n    --hash=sha256:aaaa\ncoverage==7.16.1 \\\\\n    --hash=sha256:bbbb\n' > "\$out"
exit 0
STUB
  chmod +x "$dir/pip-compile"
}

header=$'# Line one of the header.\n#\n# Line three, mentions --require-hashes.'

write_lockfile() {
  local path="$1"
  printf '%s\n\nold-package==0.0.1 \\\n    --hash=sha256:0000\n' "$header" > "$path"
}

req_in="$work_dir/requirements-dev.in"
printf 'pytest==9.1.1\ncoverage==7.16.1\n' > "$req_in"

# --- Case 1: happy path preserves the header and replaces the body ---
stub_ok="$work_dir/stub_ok"
make_stub_pip_compile "$stub_ok" 0
lock1="$work_dir/case1.txt"
write_lockfile "$lock1"

out="$(PIP_COMPILE="$stub_ok/pip-compile" REQ_IN="$req_in" REQ_OUT="$lock1" bash "$SCRIPT" 2>&1)"
rc=$?
assert_exit_code "happy-exit" 0 "$rc"
assert_contains "happy-msg" "$out" "header preserved"

got_header="$(awk '/^#/ { print; next } { exit }' "$lock1")"
if [ "$got_header" != "$header" ]; then
  fail "happy-header" "header not preserved verbatim; got: $got_header"
fi
body="$(cat "$lock1")"
assert_contains "happy-body-new" "$body" "pytest==9.1.1"
assert_contains "happy-body-hash" "$body" "hash=sha256:bbbb"
assert_not_contains "happy-body-old" "$body" "old-package"
# Header and body must be separated by exactly one blank line.
line4="$(sed -n 4p "$lock1")"
line5="$(sed -n 5p "$lock1")"
if [ -n "$line4" ] || [ -z "$line5" ]; then
  fail "happy-separator" "expected blank line 4 then body on line 5; got '$line4' / '$line5'"
fi

# pip-compile must be invoked with the hash-pin flags and the .in file.
argv="$(cat "$stub_ok/argv.log")"
assert_contains "argv-hashes" "$argv" "generate-hashes --no-annotate"
assert_contains "argv-noheader" "$argv" "no-header --output-file="
assert_contains "argv-in" "$argv" "$req_in"

# --- Case 2: extra args are forwarded to pip-compile ---
PIP_COMPILE="$stub_ok/pip-compile" REQ_IN="$req_in" REQ_OUT="$lock1" bash "$SCRIPT" --upgrade >/dev/null 2>&1
argv="$(cat "$stub_ok/argv.log")"
assert_contains "argv-forward" "$argv" "requirements-dev.in --upgrade"

# --- Case 3: header-less lockfile is refused, not rewritten ---
lock3="$work_dir/case3.txt"
printf 'old-package==0.0.1 \\\n    --hash=sha256:0000\n' > "$lock3"
before="$(cat "$lock3")"
out="$(PIP_COMPILE="$stub_ok/pip-compile" REQ_IN="$req_in" REQ_OUT="$lock3" bash "$SCRIPT" 2>&1)"
rc=$?
assert_exit_code "noheader-exit" 1 "$rc"
assert_contains "noheader-msg" "$out" "no leading header comment block"
if [ "$(cat "$lock3")" != "$before" ]; then
  fail "noheader-untouched" "header-less lockfile was modified"
fi

# --- Case 4: pip-compile failure leaves the lockfile untouched ---
stub_fail="$work_dir/stub_fail"
make_stub_pip_compile "$stub_fail" 3
lock4="$work_dir/case4.txt"
write_lockfile "$lock4"
before="$(cat "$lock4")"
PIP_COMPILE="$stub_fail/pip-compile" REQ_IN="$req_in" REQ_OUT="$lock4" bash "$SCRIPT" >/dev/null 2>&1
rc=$?
if [ "$rc" -eq 0 ]; then
  fail "compile-fail-exit" "expected non-zero exit when pip-compile fails"
fi
if [ "$(cat "$lock4")" != "$before" ]; then
  fail "compile-fail-untouched" "lockfile modified despite pip-compile failure"
fi

# --- Case 5: missing pip-compile gives an actionable error ---
out="$(PIP_COMPILE="$work_dir/does-not-exist" REQ_IN="$req_in" REQ_OUT="$lock1" bash "$SCRIPT" 2>&1)"
rc=$?
assert_exit_code "missing-tool-exit" 1 "$rc"
assert_contains "missing-tool-msg" "$out" "pip install pip-tools"

# --- Case 6: the checked-in lockfile has a header the script can find ---
real_header="$(awk '/^#/ { print; next } { exit }' "$REPO_ROOT/requirements-dev.txt")"
assert_contains "real-header" "$real_header" "GENERATED from requirements-dev.in"

finish "compile_requirements_dev.sh"
