#!/usr/bin/env bash
# test_verify_release_health.sh — regression tests for
# scripts/verify_release_health.sh, mirroring the test_brew_ci_summary.sh
# / test_fuzz_summary.sh pattern.
#
# Focus: the structured VERIFY_RELEASE_HEALTH_SUMMARY: {...} contract and
# the branches that don't need a real Homebrew install to trigger. `brew`
# is shimmed via PATH so `brew fetch --formula` returns a controllable
# exit code per case; `git log` output is allowed to be empty (the script
# tolerates that already).
#
# Usage: scripts/test_verify_release_health.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/verify_release_health.sh"

fail_count=0
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

# Fake repo root with a Formula/ dir and a two-formula fixture set.
mkdir -p "$work_dir/repo/Formula" "$work_dir/repo/scripts" "$work_dir/bin-ok" "$work_dir/bin-fail" "$work_dir/bin-mixed"
printf 'class Foo < Formula\nend\n' > "$work_dir/repo/Formula/foo.rb"
printf 'class Bar < Formula\nend\n' > "$work_dir/repo/Formula/bar.rb"
cp "$SCRIPT" "$work_dir/repo/scripts/verify_release_health.sh"
chmod +x "$work_dir/repo/scripts/verify_release_health.sh"

# `brew` shim: always-OK variant.
cat > "$work_dir/bin-ok/brew" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$work_dir/bin-ok/brew"

# `brew` shim: always-fail variant (writes to stderr so the sed indent line
# in the script has something to consume).
cat > "$work_dir/bin-fail/brew" <<'EOF'
#!/usr/bin/env bash
echo "fetch: connection refused" >&2
exit 1
EOF
chmod +x "$work_dir/bin-fail/brew"

# `brew` shim: fails only on the "bar" formula path.
cat > "$work_dir/bin-mixed/brew" <<'EOF'
#!/usr/bin/env bash
for arg in "$@"; do
  case "$arg" in
    *bar.rb) exit 1 ;;
  esac
done
exit 0
EOF
chmod +x "$work_dir/bin-mixed/brew"

run_case() {
  local shim_dir="$1"
  shift
  # Run from the fake repo root. PATH shadowing puts our brew first.
  ( cd "$work_dir/repo" && PATH="$shim_dir:$PATH" ./scripts/verify_release_health.sh "$@" ) 2>&1
}

assert_summary() {
  local name="$1" output="$2" exit_code="$3"
  local want_status="$4" want_formula="$5" want_failed="$6" want_exit="$7"

  local summary
  summary=$(printf '%s' "$output" | grep '^VERIFY_RELEASE_HEALTH_SUMMARY: {' | tail -1)
  if [ -z "$summary" ]; then
    echo "FAIL ($name): missing VERIFY_RELEASE_HEALTH_SUMMARY: line. Got: $output"
    fail_count=$((fail_count + 1))
    return
  fi
  if ! printf '%s' "$summary" | grep -q "\"status\":\"$want_status\""; then
    echo "FAIL ($name): expected status=$want_status. Got: $summary"
    fail_count=$((fail_count + 1))
    return
  fi
  if ! printf '%s' "$summary" | grep -q "\"formula_count\":$want_formula"; then
    echo "FAIL ($name): expected formula_count=$want_formula. Got: $summary"
    fail_count=$((fail_count + 1))
    return
  fi
  if ! printf '%s' "$summary" | grep -q "\"failed_count\":$want_failed"; then
    echo "FAIL ($name): expected failed_count=$want_failed. Got: $summary"
    fail_count=$((fail_count + 1))
    return
  fi
  if [ "$exit_code" -ne "$want_exit" ]; then
    echo "FAIL ($name): expected exit=$want_exit, got exit=$exit_code"
    fail_count=$((fail_count + 1))
    return
  fi
  echo "OK ($name)"
}

# Case 1: no args, both formulae fetch OK → status=pass, formula_count=2,
#         failed_count=0, exit=0 (glob-branch of `if [ "$#" -gt 0 ]`).
output=$(run_case "$work_dir/bin-ok")
exit_code=$?
assert_summary "glob-all-ok" "$output" "$exit_code" "pass" 2 0 0

# Case 2: explicit-arg branch, both fetch OK → status=pass, formula_count=2,
#         failed_count=0, exit=0.
output=$(run_case "$work_dir/bin-ok" foo bar)
exit_code=$?
assert_summary "args-all-ok" "$output" "$exit_code" "pass" 2 0 0

# Case 3: brew always fails → status=fail, failed_count=2, exit=1.
output=$(run_case "$work_dir/bin-fail")
exit_code=$?
assert_summary "all-fetch-fail" "$output" "$exit_code" "fail" 2 2 1

# Case 4: mixed — foo OK, bar fails → status=fail, failed_count=1, exit=1.
output=$(run_case "$work_dir/bin-mixed")
exit_code=$?
assert_summary "one-fetch-fail" "$output" "$exit_code" "fail" 2 1 1

# Case 5: missing formula arg — hits the `if [ ! -f "$path" ]` branch that
#         does NOT call brew. formula_count includes the missing one; the
#         SKIP line must appear; status=fail, failed_count=1, exit=1.
output=$(run_case "$work_dir/bin-ok" nope)
exit_code=$?
if ! printf '%s' "$output" | grep -q "SKIP: no such formula file"; then
  echo "FAIL (missing-formula): expected SKIP line. Got: $output"
  fail_count=$((fail_count + 1))
else
  assert_summary "missing-formula" "$output" "$exit_code" "fail" 1 1 1
fi

# Case 6: brew not on PATH → early exit 2 with a message on stderr and NO
#         summary line (the check is above summary emission). Guards the
#         "Homebrew must be installed" contract. Keep a minimal PATH so
#         env / bash / basic coreutils still resolve; only `brew` must be
#         absent from it.
mkdir -p "$work_dir/bin-nobrew"
for cmd in bash env sed rm basename dirname pwd cd git; do
  target=$(command -v "$cmd" 2>/dev/null || true)
  if [ -n "$target" ]; then
    ln -sf "$target" "$work_dir/bin-nobrew/$cmd"
  fi
done
output=$( ( cd "$work_dir/repo" && PATH="$work_dir/bin-nobrew" ./scripts/verify_release_health.sh ) 2>&1 )
exit_code=$?
if [ "$exit_code" -ne 2 ]; then
  echo "FAIL (no-brew-on-path): expected exit=2, got exit=$exit_code"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q "'brew' is not on PATH"; then
  echo "FAIL (no-brew-on-path): expected 'brew not on PATH' message. Got: $output"
  fail_count=$((fail_count + 1))
elif printf '%s' "$output" | grep -q '^VERIFY_RELEASE_HEALTH_SUMMARY:'; then
  echo "FAIL (no-brew-on-path): summary line should NOT appear when brew missing. Got: $output"
  fail_count=$((fail_count + 1))
else
  echo "OK (no-brew-on-path)"
fi

if [ "$fail_count" -eq 0 ]; then
  echo "All verify_release_health.sh tests passed."
  exit 0
else
  echo "$fail_count verify_release_health.sh test(s) failed."
  exit 1
fi
