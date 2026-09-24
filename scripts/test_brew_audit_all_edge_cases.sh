#!/usr/bin/env bash
# test_brew_audit_all_edge_cases.sh — supplementary regression tests for
# scripts/brew_audit_all.sh covering summary-line contracts not
# exercised by scripts/test_brew_audit_all.sh:
#
#   1. FORMULA_DIR exists but contains no *.rb files. The `for formula
#      in "$FORMULA_DIR"/*.rb; do [ -e "$formula" ] || continue` guard
#      must skip the loop cleanly, and the script must still emit the
#      trailing BREW_AUDIT_SUMMARY: status="pass" line with
#      formula_count=0 — otherwise a repo that temporarily has no
#      formulae (or a misconfigured FORMULA_DIR override) would produce
#      no summary at all and downstream grep-based tooling would silently
#      see an empty record.
#
#   2. FORMULA_DIR does not exist at all. Same contract as (1): the glob
#      expands to a literal path that `[ -e ]` rejects, the loop is
#      skipped, and the pass summary with formula_count=0 is emitted.
#      This documents the current best-effort behavior — a
#      typo'd/removed FORMULA_DIR is treated as "no formulae" rather
#      than a hard error, matching how brew-ci.yml's original inline
#      loop behaved.
#
#   3. The very first formula fails. scripts/test_brew_audit_all.sh
#      only exercises `beta` failing (the second of three), so the
#      formula_count in the fail summary is always 2. A regression that
#      accidentally pre-increments formula_count after the audit call
#      (instead of before) would still pass that case with 1 vs 2, but
#      would report 0 here — so exercising a first-formula failure
#      pins the counter's ordering.
#
# Stubs `brew` via a PATH-shim, mirroring scripts/test_brew_audit_all.sh
# and scripts/test_brew_ci_summary_brew_path.sh.
#
# Usage: scripts/test_brew_audit_all_edge_cases.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

# shellcheck disable=SC2016  # literal backtick/markdown strings in single quotes, not variable expansion
set -uo pipefail

# shellcheck source=scripts/test_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test_lib.sh"

REPO_ROOT="$(repo_root)"
SCRIPT="$REPO_ROOT/scripts/brew_audit_all.sh"

make_work_dir

# make_stub_brew <dir> <failing_formula_or_empty> <exit_code> [<output>]
# Mirrors the helper in scripts/test_brew_audit_all.sh: `brew audit
# --strict <tap>/<name>` fails with <exit_code> only when <name> ==
# <failing_formula_or_empty>; every other formula (and an empty
# <failing_formula_or_empty>) always succeeds.
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

# --- Case 1: FORMULA_DIR exists but is empty ---
empty_dir="$work_dir/Formula-empty"
mkdir -p "$empty_dir"
stub1="$work_dir/stub1"
make_stub_brew "$stub1" "" 0
output=$(env -i PATH="$stub1:/usr/bin:/bin" FORMULA_DIR="$empty_dir" bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "empty-formula-dir exit" 0 "$code"
assert_contains "empty-formula-dir summary line" "$output" \
  'BREW_AUDIT_SUMMARY: {"status":"pass","formula_count":0,"warned_count":0,"failed_formula":null}'
assert_not_contains "empty-formula-dir no ::group::" "$output" '::group::'

# --- Case 2: FORMULA_DIR does not exist ---
missing_dir="$work_dir/Formula-missing"
stub2="$work_dir/stub2"
make_stub_brew "$stub2" "" 0
output=$(env -i PATH="$stub2:/usr/bin:/bin" FORMULA_DIR="$missing_dir" bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "missing-formula-dir exit" 0 "$code"
assert_contains "missing-formula-dir summary line" "$output" \
  'BREW_AUDIT_SUMMARY: {"status":"pass","formula_count":0,"warned_count":0,"failed_formula":null}'
assert_not_contains "missing-formula-dir no ::group::" "$output" '::group::'

# --- Case 3: the very first formula fails -> formula_count=1 in the
# fail summary, and no later formula is audited ---
formula_dir="$work_dir/Formula"
make_fake_formulae "$formula_dir" alpha beta gamma
stub3="$work_dir/stub3"
make_stub_brew "$stub3" "alpha" 5
output=$(env -i PATH="$stub3:/usr/bin:/bin" FORMULA_DIR="$formula_dir" bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "alpha-fails propagates exit code" 5 "$code"
assert_contains "alpha-fails summary counts only alpha" "$output" \
  'BREW_AUDIT_SUMMARY: {"status":"fail","formula_count":1,"warned_count":0,"failed_formula":"alpha"}'
assert_not_contains "alpha-fails does not reach beta" "$output" "kubestellar/tap/beta"
assert_not_contains "alpha-fails does not reach gamma" "$output" "kubestellar/tap/gamma"
endgroup_count=$(printf '%s\n' "$output" | grep -c '^::endgroup::$')
assert_exit_code "alpha-fails no endgroup printed" 0 "$endgroup_count"

if [ "$fail_count" -gt 0 ]; then
  echo "$fail_count assertion(s) failed"
  exit 1
fi
echo "All brew_audit_all.sh edge-case assertions passed"
