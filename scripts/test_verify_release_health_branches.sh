#!/usr/bin/env bash
# test_verify_release_health_branches.sh — additional branch coverage for
# scripts/verify_release_health.sh.
#
# The existing scripts/test_verify_release_health.sh covers the six top-
# level behaviors (missing brew, success, failure, missing formula file,
# auto-discovery, and the VERIFY_RELEASE_HEALTH_SUMMARY: JSON shape),
# but three narrower branches inside verify_release_health.sh had no
# regression guard:
#
#   1. The `last commit: ${last_commit:-<unknown>}` fallback that fires
#      when `git -C "$REPO_ROOT" log` returns no output — e.g. the script
#      is invoked in a checkout that is not a git repo, or the formula
#      file exists on disk but has never been committed. A refactor that
#      dropped the `${...:-<unknown>}` default would print a blank
#      "last commit:" line instead, and no existing test would catch it.
#
#   2. On a failed fetch, the script prints `fetch: FAILED (see below)`
#      and replays the captured brew stdout+stderr indented four spaces
#      via `sed 's/^/    /'`. The existing Case 3 asserts only on the
#      "fetch: FAILED" substring, so a regression that dropped the
#      "(see below)" suffix or the indented replay (e.g. cleanup order
#      change that removed the log file before sed ran) would go
#      unnoticed.
#
#   3. Mixed SKIP + successful fetch — one nonexistent formula plus one
#      real one on the CLI. Case 4 exercises SKIP alone (one arg, no
#      real formula), and Case 5 exercises auto-discovery with two real
#      formulae. Neither locks in that a SKIP on one formula still lets
#      the other formula's fetch proceed AND that failed_count counts
#      the SKIP alongside status=fail even though the fetch itself
#      succeeded — the exact "one bad formula shouldn't hide the healthy
#      ones" property the runbook cares about.
#
# Each case builds its own fixture and does not touch the ones in
# test_verify_release_health.sh, so the two files can run in either
# order or in parallel via run_shell_tests.sh.
#
# Usage: scripts/test_verify_release_health_branches.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

# shellcheck source=scripts/test_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test_lib.sh"

REPO_ROOT="$(repo_root)"
SCRIPT_SOURCE="$REPO_ROOT/scripts/verify_release_health.sh"

if [ ! -f "$SCRIPT_SOURCE" ]; then
  echo "FAIL (setup): script not found at $SCRIPT_SOURCE"
  exit 1
fi

make_work_dir
work_root="$work_dir"

# ---------------------------------------------------------------------------
# Helper: build a fixture WITHOUT initialising a git repo, so `git log`
# returns nothing and the "<unknown>" branch fires.
# ---------------------------------------------------------------------------
_make_ungitted_fixture() {
  local dir="$1"; shift
  mkdir -p "$dir/scripts" "$dir/Formula"
  cp "$SCRIPT_SOURCE" "$dir/scripts/verify_release_health.sh"
  chmod +x "$dir/scripts/verify_release_health.sh"
  for name in "$@"; do
    printf 'class %s < Formula\nend\n' "$name" > "$dir/Formula/${name}.rb"
  done
  # Deliberately NO `git init` here — that is the point of this fixture.
}

# ---------------------------------------------------------------------------
# Helper: same as test_verify_release_health.sh's _make_fixture, but
# duplicated here so the two files stay independent.
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
# Helper: brew stub that succeeds and emits a fixed marker string on
# stderr so the failed-fetch replay case can assert on the indented copy.
# ---------------------------------------------------------------------------
_stub_brew_failing_with_marker() {
  local dir="$1" marker="$2"
  mkdir -p "$dir/bin"
  cat > "$dir/bin/brew" <<EOF
#!/usr/bin/env bash
printf 'BREW_STDERR_MARKER=%s\n' "$marker" >&2
exit 1
EOF
  chmod +x "$dir/bin/brew"
}

# ---------------------------------------------------------------------------
# Helper: brew stub that always succeeds (needed for the SKIP-mixed case).
# ---------------------------------------------------------------------------
_stub_brew_ok() {
  local dir="$1"
  mkdir -p "$dir/bin"
  cat > "$dir/bin/brew" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
  chmod +x "$dir/bin/brew"
}

echo "verify_release_health.sh — branch coverage"
echo "-------------------------------------------"

# ===========================================================================
# Case B1: `last commit: <unknown>` fallback when the tap dir is not a
# git repo. Locks the `${last_commit:-<unknown>}` default in place.
# ===========================================================================
case_dir="$work_root/b1"
_make_ungitted_fixture "$case_dir" foo
_stub_brew_ok "$case_dir"
output=$(PATH="$case_dir/bin:/usr/bin:/bin" \
  "$case_dir/scripts/verify_release_health.sh" foo 2>&1)
exit_code=$?
assert_exit ungitted-last-commit "$exit_code" 0 \
  "expected exit=0 on ungitted fixture with successful fetch, got $exit_code. Output: $output" || :
assert_grep ungitted-last-commit "$output" "last commit: <unknown>" \
  "expected 'last commit: <unknown>' fallback; got: $output" || :
# And the summary should still be pass, since the fetch itself worked.
assert_grep ungitted-last-commit "$output" '"status":"pass"' \
  "ungitted fixture with OK fetch should still report status=pass; got: $output" || :

# ===========================================================================
# Case B2: failed-fetch replay — assert both the "(see below)" marker
# AND the indented (four-space) reproduction of the brew stub's stderr.
# ===========================================================================
case_dir="$work_root/b2"
_make_fixture "$case_dir" foo
_stub_brew_failing_with_marker "$case_dir" "unit-test-123"
output=$(PATH="$case_dir/bin:/usr/bin:/bin" \
  "$case_dir/scripts/verify_release_health.sh" foo 2>&1)
exit_code=$?
assert_exit failed-fetch-replay "$exit_code" 1 \
  "expected exit=1 on failed fetch, got $exit_code. Output: $output" || :
assert_grep failed-fetch-replay "$output" "fetch: FAILED (see below)" \
  "expected 'fetch: FAILED (see below)' suffix; got: $output" || :
# The captured stub output is indented four spaces by `sed 's/^/    /'`.
# grep -F -q for a literal 4-space + marker prefix locks the exact
# indent width in place, so a refactor that changed to two spaces or
# dropped sed entirely would fail here.
if ! printf '%s' "$output" | grep -qF "    BREW_STDERR_MARKER=unit-test-123"; then
  fail failed-fetch-replay \
    "expected 4-space-indented replay of brew stderr marker; got: $output"
fi

# ===========================================================================
# Case B3: mixed SKIP + successful fetch. One nonexistent formula name
# and one real formula, both passed explicitly on the CLI. Locks the
# "one bad formula doesn't hide the good ones" property + failed_count
# still tallies the SKIP even though the real fetch succeeded.
# ===========================================================================
case_dir="$work_root/b3"
_make_fixture "$case_dir" foo   # only foo.rb exists on disk
_stub_brew_ok "$case_dir"
output=$(PATH="$case_dir/bin:/usr/bin:/bin" \
  "$case_dir/scripts/verify_release_health.sh" ghost foo 2>&1)
exit_code=$?
assert_exit mixed-skip-success "$exit_code" 1 \
  "expected exit=1 (SKIP contributes to failed_count), got $exit_code. Output: $output" || :
assert_grep mixed-skip-success "$output" "SKIP: no such formula file" \
  "expected SKIP diagnostic for ghost; got: $output" || :
assert_grep mixed-skip-success "$output" "fetch: OK" \
  "expected fetch: OK for the real formula; got: $output" || :
assert_grep mixed-skip-success "$output" '"formula_count":2' \
  "expected formula_count=2 (both args processed); got: $output" || :
assert_grep mixed-skip-success "$output" '"failed_count":1' \
  "expected failed_count=1 (only the SKIP); got: $output" || :
assert_grep mixed-skip-success "$output" '"status":"fail"' \
  "expected status=fail (any nonzero failed_count → fail); got: $output" || :

finish "verify_release_health.sh branch"
