#!/usr/bin/env bash
# test_verify_release_health.sh — regression guard for scripts/verify_release_health.sh.
#
# The production script had no companion test: every other script under
# scripts/ (brew_ci_summary.sh, fuzz_summary.sh, validate_formulae.py) has
# at least one test_*.sh or test_*.py, but verify_release_health.sh did
# not. That left the following branches unprotected against regression:
#
#   1. `brew` missing on PATH → exit 2, error message.
#   2. Successful fetch path → per-formula "fetch: OK" + summary status=pass.
#   3. Failed fetch path → per-formula "fetch: FAILED" + summary status=fail
#      + failed_count reflecting the count.
#   4. Explicit CLI argument for a formula whose Formula/<name>.rb file
#      does not exist → SKIP branch, failed_count increments, exit 1.
#   5. Auto-discovery loop over Formula/*.rb populates the formulae list
#      when no CLI arguments are given.
#   6. VERIFY_RELEASE_HEALTH_SUMMARY: single-line JSON summary shape —
#      status/formula_count/failed_count — matches the documented
#      "bounded integer counts" contract inside the script header.
#
# Cases 2/3/5 need a stub `brew` on PATH (real Homebrew is not installed
# in CI containers and reaching out to the network is banned anyway), and
# a temp git repo so `git -C ... log` returns a real "last commit" line.
#
# Usage: scripts/test_verify_release_health.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_SOURCE="$REPO_ROOT/scripts/verify_release_health.sh"

if [ ! -f "$SCRIPT_SOURCE" ]; then
  echo "FAIL (setup): script not found at $SCRIPT_SOURCE"
  exit 1
fi

fail_count=0
work_root="$(mktemp -d)"
trap 'rm -rf "$work_root"' EXIT

# ---------------------------------------------------------------------------
# Helper: build a self-contained tap fixture in $1 with the script copied
# in and a real git repo initialised (so `git log` works). Fixture layout:
#   $1/scripts/verify_release_health.sh
#   $1/Formula/<name>.rb          (one per name in $2..$n)
# ---------------------------------------------------------------------------
_make_fixture() {
  local dir="$1"; shift
  mkdir -p "$dir/scripts" "$dir/Formula"
  cp "$SCRIPT_SOURCE" "$dir/scripts/verify_release_health.sh"
  chmod +x "$dir/scripts/verify_release_health.sh"
  for name in "$@"; do
    printf 'class %s < Formula\nend\n' "$name" > "$dir/Formula/${name}.rb"
  done
  git -C "$dir" init -q -b main 2>/dev/null || git -C "$dir" init -q
  git -C "$dir" -c user.email=t@t -c user.name=t add -A
  git -C "$dir" -c user.email=t@t -c user.name=t commit -q -m "seed" >/dev/null
}

# ---------------------------------------------------------------------------
# Helper: write a stub `brew` executable to $1/bin/brew with the exit
# code from $2 (default 0). The stub records its argv into $1/bin/brew.log
# so cases can assert on it if useful.
# ---------------------------------------------------------------------------
_stub_brew() {
  local dir="$1"; local exit_code="${2:-0}"
  mkdir -p "$dir/bin"
  cat > "$dir/bin/brew" <<EOF
#!/usr/bin/env bash
printf '%s ' "\$@" >> "$dir/bin/brew.log"
printf '\n' >> "$dir/bin/brew.log"
exit $exit_code
EOF
  chmod +x "$dir/bin/brew"
}

# ---------------------------------------------------------------------------
# Case 1: brew is not on PATH → exit 2, error to stderr.
# ---------------------------------------------------------------------------
case_dir="$work_root/case1"
_make_fixture "$case_dir" foo
# Restrict PATH to /usr/bin:/bin (no brew) — mktemp, cp, chmod etc. are
# there; git already ran during fixture setup so the subshell doesn't
# need git on PATH.
output=$(PATH="/usr/bin:/bin" "$case_dir/scripts/verify_release_health.sh" 2>&1)
exit_code=$?
if [ "$exit_code" -ne 2 ]; then
  echo "FAIL (no-brew): expected exit=2, got exit=$exit_code. Output: $output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q "'brew' is not on PATH"; then
  echo "FAIL (no-brew): expected 'brew is not on PATH' diagnostic. Got: $output"
  fail_count=$((fail_count + 1))
else
  echo "OK (no-brew)"
fi

# ---------------------------------------------------------------------------
# Case 2: successful fetch (stubbed brew, one formula, explicit arg).
# ---------------------------------------------------------------------------
case_dir="$work_root/case2"
_make_fixture "$case_dir" foo
_stub_brew "$case_dir" 0
output=$(PATH="$case_dir/bin:/usr/bin:/bin" \
  "$case_dir/scripts/verify_release_health.sh" foo 2>&1)
exit_code=$?
if [ "$exit_code" -ne 0 ]; then
  echo "FAIL (success): expected exit=0, got exit=$exit_code. Output: $output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q "fetch: OK"; then
  echo "FAIL (success): expected 'fetch: OK'. Got: $output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q '"status":"pass"'; then
  echo "FAIL (success): expected status=pass. Got: $output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q '"formula_count":1'; then
  echo "FAIL (success): expected formula_count=1. Got: $output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q '"failed_count":0'; then
  echo "FAIL (success): expected failed_count=0. Got: $output"
  fail_count=$((fail_count + 1))
else
  echo "OK (success)"
fi

# ---------------------------------------------------------------------------
# Case 3: failed fetch (stubbed brew returns 1).
# ---------------------------------------------------------------------------
case_dir="$work_root/case3"
_make_fixture "$case_dir" foo
_stub_brew "$case_dir" 1
output=$(PATH="$case_dir/bin:/usr/bin:/bin" \
  "$case_dir/scripts/verify_release_health.sh" foo 2>&1)
exit_code=$?
if [ "$exit_code" -ne 1 ]; then
  echo "FAIL (fetch-fail): expected exit=1, got exit=$exit_code. Output: $output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q "fetch: FAILED"; then
  echo "FAIL (fetch-fail): expected 'fetch: FAILED'. Got: $output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q '"status":"fail"'; then
  echo "FAIL (fetch-fail): expected status=fail. Got: $output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q '"failed_count":1'; then
  echo "FAIL (fetch-fail): expected failed_count=1. Got: $output"
  fail_count=$((fail_count + 1))
else
  echo "OK (fetch-fail)"
fi

# ---------------------------------------------------------------------------
# Case 4: explicit CLI arg for a formula whose file does not exist →
# SKIP branch, failed_count=1, exit 1. The stubbed brew must NOT be
# called (asserted via brew.log absence).
# ---------------------------------------------------------------------------
case_dir="$work_root/case4"
_make_fixture "$case_dir" foo   # only foo.rb exists
_stub_brew "$case_dir" 0
output=$(PATH="$case_dir/bin:/usr/bin:/bin" \
  "$case_dir/scripts/verify_release_health.sh" ghost 2>&1)
exit_code=$?
if [ "$exit_code" -ne 1 ]; then
  echo "FAIL (missing-formula): expected exit=1, got exit=$exit_code. Output: $output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q "SKIP: no such formula file"; then
  echo "FAIL (missing-formula): expected SKIP diagnostic. Got: $output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q '"failed_count":1'; then
  echo "FAIL (missing-formula): expected failed_count=1. Got: $output"
  fail_count=$((fail_count + 1))
elif [ -f "$case_dir/bin/brew.log" ]; then
  echo "FAIL (missing-formula): brew stub was invoked, but SKIP branch should short-circuit before it."
  fail_count=$((fail_count + 1))
else
  echo "OK (missing-formula)"
fi

# ---------------------------------------------------------------------------
# Case 5: auto-discovery — no CLI args, multiple Formula/*.rb files,
# mixed brew fetch results (via a stub whose exit code depends on argv).
# Locks: (a) both formulae are visited, (b) failed_count reflects the
# single failure, (c) status=fail because failed_count > 0.
# ---------------------------------------------------------------------------
case_dir="$work_root/case5"
_make_fixture "$case_dir" alpha beta
# Custom stub: succeed for alpha, fail for beta. Match on the last argv,
# which is the formula path.
mkdir -p "$case_dir/bin"
cat > "$case_dir/bin/brew" <<'EOF'
#!/usr/bin/env bash
# Last arg is the formula path; extract the basename for the routing decision.
last="${!#}"
case "$(basename "$last")" in
  beta.rb) exit 1 ;;
  *)       exit 0 ;;
esac
EOF
chmod +x "$case_dir/bin/brew"
output=$(PATH="$case_dir/bin:/usr/bin:/bin" \
  "$case_dir/scripts/verify_release_health.sh" 2>&1)
exit_code=$?
if [ "$exit_code" -ne 1 ]; then
  echo "FAIL (auto-mixed): expected exit=1, got exit=$exit_code. Output: $output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q '"formula_count":2'; then
  echo "FAIL (auto-mixed): expected formula_count=2 (auto-discovery). Got: $output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q '"failed_count":1'; then
  echo "FAIL (auto-mixed): expected failed_count=1. Got: $output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q '"status":"fail"'; then
  echo "FAIL (auto-mixed): expected status=fail. Got: $output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q "^== alpha ==$"; then
  echo "FAIL (auto-mixed): missing '== alpha ==' header. Got: $output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$output" | grep -q "^== beta ==$"; then
  echo "FAIL (auto-mixed): missing '== beta ==' header. Got: $output"
  fail_count=$((fail_count + 1))
else
  echo "OK (auto-mixed)"
fi

# ---------------------------------------------------------------------------
# Case 6: VERIFY_RELEASE_HEALTH_SUMMARY: JSON shape — bounded integer
# fields + status enum. Guards the contract documented in the script
# header ("bounded integer counts, safe to grep").
# ---------------------------------------------------------------------------
case_dir="$work_root/case6"
_make_fixture "$case_dir" foo
_stub_brew "$case_dir" 0
output=$(PATH="$case_dir/bin:/usr/bin:/bin" \
  "$case_dir/scripts/verify_release_health.sh" foo 2>&1)
summary_line=$(printf '%s\n' "$output" | grep '^VERIFY_RELEASE_HEALTH_SUMMARY: ' || true)
if [ -z "$summary_line" ]; then
  echo "FAIL (summary-shape): missing VERIFY_RELEASE_HEALTH_SUMMARY: line. Got: $output"
  fail_count=$((fail_count + 1))
elif ! printf '%s' "$summary_line" \
      | grep -Eq '^VERIFY_RELEASE_HEALTH_SUMMARY: \{"status":"(pass|fail)","formula_count":[0-9]+,"failed_count":[0-9]+\}$'; then
  echo "FAIL (summary-shape): line does not match expected JSON shape."
  echo "Got: $summary_line"
  fail_count=$((fail_count + 1))
else
  echo "OK (summary-shape)"
fi

if [ "$fail_count" -eq 0 ]; then
  echo "All verify_release_health.sh tests passed."
  exit 0
else
  echo "$fail_count verify_release_health.sh test(s) failed."
  exit 1
fi
