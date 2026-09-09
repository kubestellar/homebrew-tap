#!/usr/bin/env bash
# test_verify_release_health.sh — regression tests for
# scripts/verify_release_health.sh.
#
# Guards against the summary line silently losing its stdout-only,
# always-emitted contract (VERIFY_RELEASE_HEALTH_SUMMARY: mirrors the
# BREW_CI_SUMMARY / VALIDATE_FORMULAE_SUMMARY pattern), and against
# regressions in the script's exit-status contract:
#
#   - exit 0 when every checked formula fetched successfully
#   - exit 1 when any fetch failed or any named formula was missing
#   - exit 2 when `brew` is not on PATH (unrunnable environment)
#
# Homebrew is stubbed via a PATH-prepended fake `brew` script so this
# test never touches the network or the real brew cache, and the script
# is copied into a self-contained work tree so REPO_ROOT resolves to a
# synthetic Formula/ directory instead of the repo's real formulae.
#
# Usage: scripts/test_verify_release_health.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/verify_release_health.sh"

if [ ! -f "$SCRIPT" ]; then
  echo "FAIL (setup): missing $SCRIPT" >&2
  exit 1
fi

fail_count=0
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

# Build a synthetic repo tree: scripts/, Formula/, bin/.
mkdir -p "$work_dir/scripts" "$work_dir/Formula" "$work_dir/bin"
cp "$SCRIPT" "$work_dir/scripts/verify_release_health.sh"
chmod +x "$work_dir/scripts/verify_release_health.sh"
printf 'class Foo < Formula\nend\n' > "$work_dir/Formula/foo.rb"
printf 'class Bar < Formula\nend\n' > "$work_dir/Formula/bar.rb"

# Give `git log` something to report so the script's "last commit" line is
# not <unknown>. The script still runs fine either way — this just exercises
# the populated branch.
(
  cd "$work_dir"
  git init -q
  git config user.email "test@example.com"
  git config user.name "test"
  git add -A
  git commit -q -m "init"
) >/dev/null 2>&1

# Fake `brew` stub: exits with $FAKE_BREW_EXIT (default 0). Also honors
# $FAKE_BREW_FAIL_ON — a formula path substring that forces exit 1 for
# just that fetch, so we can test the mixed pass+fail path.
cat > "$work_dir/bin/brew" <<'STUB'
#!/usr/bin/env bash
if [ -n "${FAKE_BREW_FAIL_ON:-}" ]; then
  for arg in "$@"; do
    case "$arg" in
      *"$FAKE_BREW_FAIL_ON"*)
        echo "fake brew: forced failure on $arg" >&2
        exit 1
        ;;
    esac
  done
fi
exit "${FAKE_BREW_EXIT:-0}"
STUB
chmod +x "$work_dir/bin/brew"

STUB_PATH="$work_dir/bin:/usr/bin:/bin"

# ── Test 1: every fetch succeeds — exit 0, status:pass, failed_count:0 ──
output=$(PATH="$STUB_PATH" "$work_dir/scripts/verify_release_health.sh" 2>&1)
exit_code=$?
if [ "$exit_code" -eq 0 ] \
  && printf '%s' "$output" | grep -q 'VERIFY_RELEASE_HEALTH_SUMMARY: {' \
  && printf '%s' "$output" | grep -q '"status":"pass"' \
  && printf '%s' "$output" | grep -q '"formula_count":2' \
  && printf '%s' "$output" | grep -q '"failed_count":0'; then
  echo "OK (all-fetch-success)"
else
  echo "FAIL (all-fetch-success): exit=$exit_code. Output:"
  printf '%s\n' "$output" | sed 's/^/  /'
  fail_count=$((fail_count + 1))
fi

# ── Test 2: every fetch fails — exit 1, status:fail, failed_count:2 ──
output=$(FAKE_BREW_EXIT=1 PATH="$STUB_PATH" "$work_dir/scripts/verify_release_health.sh" 2>&1)
exit_code=$?
if [ "$exit_code" -eq 1 ] \
  && printf '%s' "$output" | grep -q '"status":"fail"' \
  && printf '%s' "$output" | grep -q '"formula_count":2' \
  && printf '%s' "$output" | grep -q '"failed_count":2'; then
  echo "OK (all-fetch-fail)"
else
  echo "FAIL (all-fetch-fail): exit=$exit_code. Output:"
  printf '%s\n' "$output" | sed 's/^/  /'
  fail_count=$((fail_count + 1))
fi

# ── Test 3: mixed pass+fail — exit 1, failed_count:1 ─────────────────
output=$(FAKE_BREW_FAIL_ON="foo.rb" PATH="$STUB_PATH" "$work_dir/scripts/verify_release_health.sh" 2>&1)
exit_code=$?
if [ "$exit_code" -eq 1 ] \
  && printf '%s' "$output" | grep -q '"status":"fail"' \
  && printf '%s' "$output" | grep -q '"failed_count":1' \
  && printf '%s' "$output" | grep -q '"formula_count":2'; then
  echo "OK (mixed-pass-fail)"
else
  echo "FAIL (mixed-pass-fail): exit=$exit_code. Output:"
  printf '%s\n' "$output" | sed 's/^/  /'
  fail_count=$((fail_count + 1))
fi

# ── Test 4: explicit missing-formula argument — SKIP + failed_count += 1 ──
output=$(PATH="$STUB_PATH" "$work_dir/scripts/verify_release_health.sh" foo does-not-exist 2>&1)
exit_code=$?
if [ "$exit_code" -eq 1 ] \
  && printf '%s' "$output" | grep -q "SKIP: no such formula file" \
  && printf '%s' "$output" | grep -q '"status":"fail"' \
  && printf '%s' "$output" | grep -q '"formula_count":2' \
  && printf '%s' "$output" | grep -q '"failed_count":1'; then
  echo "OK (missing-formula-arg-skips-and-fails)"
else
  echo "FAIL (missing-formula-arg): exit=$exit_code. Output:"
  printf '%s\n' "$output" | sed 's/^/  /'
  fail_count=$((fail_count + 1))
fi

# ── Test 5: `brew` not on PATH — exit 2, no summary line emitted ─────
# PATH intentionally omits the stub bin/ and any /usr/local, /opt/homebrew,
# etc. where a real `brew` might live, but keeps /usr/bin:/bin so the
# shebang and shell builtins still resolve.
output=$(PATH="/usr/bin:/bin" "$work_dir/scripts/verify_release_health.sh" 2>&1)
exit_code=$?
if [ "$exit_code" -eq 2 ] \
  && printf '%s' "$output" | grep -q "'brew' is not on PATH"; then
  echo "OK (no-brew-on-path-exit-2)"
else
  echo "FAIL (no-brew-on-path): exit=$exit_code. Output:"
  printf '%s\n' "$output" | sed 's/^/  /'
  fail_count=$((fail_count + 1))
fi

if [ "$fail_count" -eq 0 ]; then
  echo "All verify_release_health.sh tests passed."
  exit 0
else
  echo "$fail_count verify_release_health.sh test(s) failed."
  exit 1
fi
