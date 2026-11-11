#!/usr/bin/env bash
# test_verify_release_artifacts.sh — regression tests for
# scripts/verify_release_artifacts.sh.
#
# Guards the three failure modes a stale/corrupt per-arch release
# artifact can hit — download failure, sha256 mismatch, and a tarball
# missing the binary `bin.install` expects — plus the happy path and the
# empty-Formula-dir regression guard. Stubs `curl` via a PATH-shim
# (mirroring scripts/test_brew_install_smoke.sh's `brew` stub) so no
# real network access is needed; `tar`/`sha256sum`/`shasum` run for
# real since they are deterministic given the fixture tarball.
#
# Usage: scripts/test_verify_release_artifacts.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

# shellcheck source=scripts/test_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test_lib.sh"

REPO_ROOT="$(repo_root)"
SCRIPT="$REPO_ROOT/scripts/verify_release_artifacts.sh"

real_sha256() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

# make_fixture_tarball <path> <binary-name> — build a real gzip tarball
# containing a single file named <binary-name>, mirroring the flat
# (no-subdirectory) layout GoReleaser produces.
make_fixture_tarball() {
  local path="$1" bin_name="$2"
  local build_dir
  build_dir="$(mktemp -d)"
  printf '#!/bin/sh\necho fake\n' > "$build_dir/$bin_name"
  chmod +x "$build_dir/$bin_name"
  tar -C "$build_dir" -czf "$path" "$bin_name"
  rm -rf "$build_dir"
}

# make_stub_curl <dir> <url-to-tarball-map-file-or-empty> <fail> [<argv-log-file>]
#   <url-to-tarball-map-file>: a file with lines "<url><TAB><tarball-path>"
#   <fail>: "1" to make every invocation fail (simulated download error)
#   <argv-log-file>: when non-empty, every invocation's full argv is
#     appended to this file (one invocation per line), so a caller can
#     assert on the exact curl flags the script passed (e.g. --retry).
make_stub_curl() {
  local dir="$1" map_file="$2" fail="$3" argv_log="${4:-}"
  mkdir -p "$dir"
  cat > "$dir/curl" <<STUB
#!/usr/bin/env bash
fail="$fail"
argv_log="$argv_log"
if [ -n "\$argv_log" ]; then
  printf '%s\n' "\$*" >> "\$argv_log"
fi
if [ "\$fail" = "1" ]; then
  exit 22
fi
out=""
url=""
args=("\$@")
for ((i=0; i<\${#args[@]}; i++)); do
  if [ "\${args[i]}" = "-o" ]; then
    out="\${args[i+1]}"
  fi
done
url="\${args[-1]}"
map_file="$map_file"
src="\$(awk -F'\t' -v u="\$url" '\$1 == u {print \$2}' "\$map_file")"
if [ -z "\$src" ]; then
  exit 22
fi
cp "\$src" "\$out"
exit 0
STUB
  chmod +x "$dir/curl"
}

make_work_dir

formula_dir="$work_dir/Formula"
mkdir -p "$formula_dir"

good_tarball="$work_dir/good.tar.gz"
make_fixture_tarball "$good_tarball" "widget"
good_sha="$(real_sha256 "$good_tarball")"

wrong_bin_tarball="$work_dir/wrong_bin.tar.gz"
make_fixture_tarball "$wrong_bin_tarball" "not-widget"
wrong_bin_sha="$(real_sha256 "$wrong_bin_tarball")"

cat > "$formula_dir/widget.rb" <<RB
class Widget < Formula
  on_macos do
    if Hardware::CPU.arm?
      url "https://example.invalid/widget_darwin_arm64.tar.gz"
      sha256 "$good_sha"

      define_method(:install) do
        bin.install "widget"
      end
    end
  end
end
RB

stub_dir="$work_dir/stub"
map_file="$work_dir/map.tsv"
printf 'https://example.invalid/widget_darwin_arm64.tar.gz\t%s\n' "$good_tarball" > "$map_file"
make_stub_curl "$stub_dir" "$map_file" "0"

# --- Case 1: happy path — sha256 + binary both match ---
output=$(env -i PATH="$stub_dir:/usr/bin:/bin" FORMULA_DIR="$formula_dir" "${SHELL_COVERAGE_BASH:-bash}" "$SCRIPT" 2>&1)
code=$?
assert_exit_code "happy-path-exit" 0 "$code"
assert_contains "happy-path-output" "$output" "verified: widget (widget)"
assert_grep "happy-path-summary-shape" "$output" \
  '^VERIFY_RELEASE_ARTIFACTS_SUMMARY: {"status":"pass","checked_count":[0-9][0-9]*,"fail_count":0}$' \
  "expected a pass-status VERIFY_RELEASE_ARTIFACTS_SUMMARY line matching the bounded-integer JSON contract"

# --- Case 2: sha256 mismatch ---
cat > "$formula_dir/widget.rb" <<RB
class Widget < Formula
  on_macos do
    if Hardware::CPU.arm?
      url "https://example.invalid/widget_darwin_arm64.tar.gz"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000"

      define_method(:install) do
        bin.install "widget"
      end
    end
  end
end
RB
output=$(env -i PATH="$stub_dir:/usr/bin:/bin" FORMULA_DIR="$formula_dir" "${SHELL_COVERAGE_BASH:-bash}" "$SCRIPT" 2>&1)
code=$?
assert_exit_code "sha-mismatch-exit" 1 "$code"
assert_contains "sha-mismatch-output" "$output" "sha256 mismatch"
assert_grep "sha-mismatch-summary-shape" "$output" \
  '^VERIFY_RELEASE_ARTIFACTS_SUMMARY: {"status":"fail","checked_count":[0-9][0-9]*,"fail_count":[1-9][0-9]*}$' \
  "expected a fail-status VERIFY_RELEASE_ARTIFACTS_SUMMARY line matching the bounded-integer JSON contract"

# --- Case 3: binary missing from archive ---
printf 'https://example.invalid/widget_darwin_arm64.tar.gz\t%s\n' "$wrong_bin_tarball" > "$map_file"
cat > "$formula_dir/widget.rb" <<RB
class Widget < Formula
  on_macos do
    if Hardware::CPU.arm?
      url "https://example.invalid/widget_darwin_arm64.tar.gz"
      sha256 "$wrong_bin_sha"

      define_method(:install) do
        bin.install "widget"
      end
    end
  end
end
RB
output=$(env -i PATH="$stub_dir:/usr/bin:/bin" FORMULA_DIR="$formula_dir" "${SHELL_COVERAGE_BASH:-bash}" "$SCRIPT" 2>&1)
code=$?
assert_exit_code "missing-binary-exit" 1 "$code"
assert_contains "missing-binary-output" "$output" "Binary missing from archive"

# --- Case 4: download failure ---
printf 'https://example.invalid/widget_darwin_arm64.tar.gz\t%s\n' "$good_tarball" > "$map_file"
cat > "$formula_dir/widget.rb" <<RB
class Widget < Formula
  on_macos do
    if Hardware::CPU.arm?
      url "https://example.invalid/widget_darwin_arm64.tar.gz"
      sha256 "$good_sha"

      define_method(:install) do
        bin.install "widget"
      end
    end
  end
end
RB
fail_stub_dir="$work_dir/stub_fail"
make_stub_curl "$fail_stub_dir" "$map_file" "1"
output=$(env -i PATH="$fail_stub_dir:/usr/bin:/bin" FORMULA_DIR="$formula_dir" "${SHELL_COVERAGE_BASH:-bash}" "$SCRIPT" 2>&1)
code=$?
assert_exit_code "download-fail-exit" 1 "$code"
assert_contains "download-fail-output" "$output" "Download failed"

# --- Case 5: empty Formula dir — regression guard ---
empty_dir="$work_dir/EmptyFormula"
mkdir -p "$empty_dir"
output=$(env -i PATH="$stub_dir:/usr/bin:/bin" FORMULA_DIR="$empty_dir" "${SHELL_COVERAGE_BASH:-bash}" "$SCRIPT" 2>&1)
code=$?
assert_exit_code "empty-dir-exit" 2 "$code"
assert_contains "empty-dir-output" "$output" "No formulae found"

# --- Case 6: parser invocation fails (PYTHON=/bin/false) must not pass ---
cat > "$formula_dir/widget.rb" <<RB
class Widget < Formula
  on_macos do
    if Hardware::CPU.arm?
      url "https://example.invalid/widget_darwin_arm64.tar.gz"
      sha256 "$good_sha"

      define_method(:install) do
        bin.install "widget"
      end
    end
  end
end
RB
output=$(env -i PATH="$stub_dir:/usr/bin:/bin" PYTHON=/bin/false FORMULA_DIR="$formula_dir" "${SHELL_COVERAGE_BASH:-bash}" "$SCRIPT" 2>&1)
code=$?
assert_exit_code "parser-fail-exit" 1 "$code"
assert_contains "parser-fail-output" "$output" "Triple extraction failed"
output=$(env -i PATH="$stub_dir:/usr/bin:/bin" PYTHON=/bin/false FORMULA_DIR="$formula_dir" "${SHELL_COVERAGE_BASH:-bash}" "$SCRIPT" --list 2>&1)
code=$?
assert_exit_code "parser-fail-list-exit" 1 "$code"

# --- Case 7: formula yielding zero triples fails verify mode ---
printf 'class Widget < Formula\nend\n' > "$formula_dir/widget.rb"
output=$(env -i PATH="$stub_dir:/usr/bin:/bin" FORMULA_DIR="$formula_dir" "${SHELL_COVERAGE_BASH:-bash}" "$SCRIPT" 2>&1)
code=$?
assert_exit_code "zero-triples-exit" 1 "$code"
assert_contains "zero-triples-output" "$output" "Triple extraction failed"

# --- Case 8: curl is invoked with the transient-error retry flags
#   (--retry/--retry-delay/--retry-connrefused) — regression guard for
#   #784/#787: a scheduled Validate Formulae run failed on a transient
#   GitHub CDN 504 because the original single-shot curl call had no
#   retry flags. Asserting the literal argv (rather than only the
#   happy-path exit code, which a single-shot curl would also satisfy)
#   is required so a future edit that silently drops the flags fails
#   this test instead of only failing intermittently in CI months later.
cat > "$formula_dir/widget.rb" <<RB
class Widget < Formula
  on_macos do
    if Hardware::CPU.arm?
      url "https://example.invalid/widget_darwin_arm64.tar.gz"
      sha256 "$good_sha"

      define_method(:install) do
        bin.install "widget"
      end
    end
  end
end
RB
printf 'https://example.invalid/widget_darwin_arm64.tar.gz\t%s\n' "$good_tarball" > "$map_file"
retry_stub_dir="$work_dir/stub_retry"
argv_log="$work_dir/curl_argv.log"
rm -f "$argv_log"
make_stub_curl "$retry_stub_dir" "$map_file" "0" "$argv_log"
output=$(env -i PATH="$retry_stub_dir:/usr/bin:/bin" FORMULA_DIR="$formula_dir" "${SHELL_COVERAGE_BASH:-bash}" "$SCRIPT" 2>&1)
code=$?
assert_exit_code "retry-flags-exit" 0 "$code"
argv="$(cat "$argv_log" 2>/dev/null)"
# Leading space on each needle keeps grep -F from parsing a "--..." needle
# as one of its own options.
assert_contains "retry-flags-retry" "$argv" " --retry 4"
assert_contains "retry-flags-delay" "$argv" " --retry-delay 5"
assert_contains "retry-flags-connrefused" "$argv" " --retry-connrefused"

finish "verify_release_artifacts"
