#!/usr/bin/env bash
# test_lib_emit_summary.sh — regression tests for scripts/lib_emit_summary.sh.
#
# lib_emit_summary.sh is the single bash owner of the '<PREFIX>: {json}'
# CI summary contract shared by brew_ci_summary.sh, fuzz_summary.sh,
# unittest_summary.sh, brew_audit_all.sh and verify_release_health.sh
# (see kubestellar/homebrew-tap#577). This file owns the invariants that
# the per-script tests therefore no longer need to re-assert:
#   1. field order follows argument order, so callers' grep-marker regexes
#      stay stable;
#   2. type inference — integers/decimals become JSON numbers, the word
#      `null` becomes JSON null, everything else a JSON string;
#   3. `key:str=` forces the string type for caller-controlled values;
#   4. `"`, `\`, and control characters are escaped so the line is always
#      valid JSON (the brew_audit_all.sh failed_formula hazard);
#   5. every emitted line parses with python3 -c json.loads;
#   6. exactly one stdout line per call, nothing on stdout when the
#      arguments are malformed (non-zero return, message on stderr);
#   7. $GITHUB_STEP_SUMMARY: no-op when unset, otherwise a markdown table
#      (heading + header row + value row, ✅/❌ on status) is appended —
#      appended, not truncated, so earlier steps' content survives.
#
# Usage: scripts/test_lib_emit_summary.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

# shellcheck source=scripts/test_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test_lib.sh"

REPO_ROOT="$(repo_root)"
# shellcheck source=scripts/lib_emit_summary.sh
source "$REPO_ROOT/scripts/lib_emit_summary.sh"

make_work_dir

# assert_valid_json <name> <line> — strip the '<PREFIX>: ' marker and
# check the remainder parses as JSON.
assert_valid_json() {
  local name="$1" line="$2"
  if ! printf '%s' "${line#*: }" | python3 -c 'import json, sys; json.load(sys.stdin)' 2>/dev/null; then
    fail "$name" "line is not valid JSON: $line"
    return 1
  fi
  return 0
}

# assert_eq <name> <actual> <expected>
assert_eq() {
  local name="$1" actual="$2" expected="$3"
  if [ "$actual" != "$expected" ]; then
    fail "$name" "expected: $expected"$'\n'"     got: $actual"
    return 1
  fi
  return 0
}

# ---------------------------------------------------------------------------
# Case 1: field order, number vs string inference, exact byte shape.
# ---------------------------------------------------------------------------
unset GITHUB_STEP_SUMMARY
out="$(emit_ci_summary BREW_CI_SUMMARY status=success os=ubuntu-latest formula_count=3 installed_count=2)"
assert_eq "field-order" "$out" \
  'BREW_CI_SUMMARY: {"status":"success","os":"ubuntu-latest","formula_count":3,"installed_count":2}' \
  && assert_valid_json "field-order" "$out" && echo "OK (field-order)"

# ---------------------------------------------------------------------------
# Case 2: numeric inference edge cases — negatives and decimals are
# numbers; leading zeros, empty and mixed strings are strings.
# ---------------------------------------------------------------------------
out="$(emit_ci_summary T zero=0 neg=-1 dec=2.5 lead=007 empty= mixed=1a plus=+1)"
assert_eq "number-inference" "$out" \
  'T: {"zero":0,"neg":-1,"dec":2.5,"lead":"007","empty":"","mixed":"1a","plus":"+1"}' \
  && assert_valid_json "number-inference" "$out" && echo "OK (number-inference)"

# ---------------------------------------------------------------------------
# Case 3: null inference, and :str forcing the string type.
# ---------------------------------------------------------------------------
out="$(emit_ci_summary BREW_AUDIT_SUMMARY status=pass formula_count=0 warned_count=0 failed_formula=null)"
assert_eq "null-inference" "$out" \
  'BREW_AUDIT_SUMMARY: {"status":"pass","formula_count":0,"warned_count":0,"failed_formula":null}' \
  && echo "OK (null-inference)"

out="$(emit_ci_summary T a:str=null b:str=123 c:str=plain)"
assert_eq "force-string" "$out" 'T: {"a":"null","b":"123","c":"plain"}' \
  && assert_valid_json "force-string" "$out" && echo "OK (force-string)"

# ---------------------------------------------------------------------------
# Case 4: escaping — quote, backslash, tab, newline and a raw control
# byte in a caller-controlled string must yield valid JSON that
# round-trips to the original value.
# ---------------------------------------------------------------------------
hazard="$(printf 'a"b\\c\td\ne\001f')"
out="$(emit_ci_summary BREW_AUDIT_SUMMARY status=fail formula_count=1 warned_count=0 failed_formula:str="$hazard")"
line_count="$(printf '%s\n' "$out" | wc -l | tr -d ' ')"
assert_eq "escape-one-line" "$line_count" "1"
assert_valid_json "escape-valid-json" "$out"
roundtrip="$(printf '%s' "${out#*: }" | python3 -c 'import json, sys; sys.stdout.write(json.load(sys.stdin)["failed_formula"])')"
assert_eq "escape-roundtrip" "$roundtrip" "$hazard" && echo "OK (escape)"

# Keys are escaped too, so a stray quote cannot break the object.
out="$(emit_ci_summary T 'we"ird=1')"
assert_eq "escape-key" "$out" 'T: {"we\"ird":1}' && assert_valid_json "escape-key" "$out" && echo "OK (escape-key)"

# A value containing '=' keeps everything after the first '='.
out="$(emit_ci_summary T expr=a=b)"
assert_eq "value-with-equals" "$out" 'T: {"expr":"a=b"}' && echo "OK (value-with-equals)"

# ---------------------------------------------------------------------------
# Case 5: no fields still yields a well-formed (empty) object.
# ---------------------------------------------------------------------------
out="$(emit_ci_summary EMPTY_SUMMARY)"
assert_eq "empty-object" "$out" 'EMPTY_SUMMARY: {}' && assert_valid_json "empty-object" "$out" && echo "OK (empty-object)"

# ---------------------------------------------------------------------------
# Case 6: malformed argument — non-zero return, nothing on stdout, a
# diagnostic on stderr. Run in a subshell so the return code is captured
# without tripping the caller.
# ---------------------------------------------------------------------------
stdout_file="$work_dir/malformed.out"
stderr_file="$work_dir/malformed.err"
(emit_ci_summary T status=pass not-a-pair >"$stdout_file" 2>"$stderr_file")
rc=$?
assert_exit_code "malformed-rc" 2 "$rc"
assert_eq "malformed-stdout-empty" "$(cat "$stdout_file")" ""
assert_contains "malformed-stderr" "$(cat "$stderr_file")" "not key=value"
(emit_ci_summary T =1 >"$stdout_file" 2>"$stderr_file")
rc=$?
assert_exit_code "empty-key-rc" 2 "$rc"
assert_eq "empty-key-stdout-empty" "$(cat "$stdout_file")" ""
echo "OK (malformed)"

# ---------------------------------------------------------------------------
# Case 7: $GITHUB_STEP_SUMMARY unset -> no file side effects at all.
# ---------------------------------------------------------------------------
before="$(find "$work_dir" -mindepth 1 | sort)"
emit_ci_summary FUZZ_SUMMARY status=success formula_count=2 >/dev/null
after="$(find "$work_dir" -mindepth 1 | sort)"
assert_eq "no-step-summary-when-unset" "$after" "$before" && echo "OK (no-step-summary-when-unset)"

# ---------------------------------------------------------------------------
# Case 8: $GITHUB_STEP_SUMMARY set -> markdown table appended (not
# truncated), ✅ for pass/success, ❌ otherwise, `|` in values escaped.
# ---------------------------------------------------------------------------
step_file="$work_dir/step_summary.md"
printf 'earlier step content\n' > "$step_file"
GITHUB_STEP_SUMMARY="$step_file" emit_ci_summary BREW_CI_SUMMARY status=success os=ubuntu-latest formula_count=3 installed_count=2 >/dev/null
GITHUB_STEP_SUMMARY="$step_file" emit_ci_summary VERIFY_RELEASE_HEALTH_SUMMARY status=fail formula_count=1 failed_count=1 >/dev/null
GITHUB_STEP_SUMMARY="$step_file" emit_ci_summary T note='a|b' >/dev/null
step_contents="$(cat "$step_file")"
assert_contains "step-summary-preserves-existing" "$step_contents" "earlier step content"
assert_contains "step-summary-heading" "$step_contents" "### Brew ci summary"
assert_contains "step-summary-header-row" "$step_contents" "| Status | Os | Formula count | Installed count |"
assert_contains "step-summary-divider" "$step_contents" "|--------|--------|--------|--------|"
assert_contains "step-summary-pass-row" "$step_contents" "| ✅ success | ubuntu-latest | 3 | 2 |"
assert_contains "step-summary-fail-heading" "$step_contents" "### Verify release health summary"
assert_contains "step-summary-fail-row" "$step_contents" "| ❌ fail | 1 | 1 |"
assert_contains "step-summary-pipe-escaped" "$step_contents" '| a\|b |'
echo "OK (step-summary)"

# The stdout line is unaffected by the step-summary side channel.
out="$(GITHUB_STEP_SUMMARY="$step_file" emit_ci_summary FUZZ_SUMMARY status=failure formula_count=0)"
assert_eq "step-summary-stdout-unchanged" "$out" 'FUZZ_SUMMARY: {"status":"failure","formula_count":0}' \
  && echo "OK (step-summary-stdout-unchanged)"

finish "lib_emit_summary.sh"
