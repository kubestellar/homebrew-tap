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

# make_stub_curl <dir> <url-to-tarball-map-file-or-empty> <fail>
#   <url-to-tarball-map-file>: a file with lines "<url><TAB><tarball-path>"
#   <fail>: "1" to make every invocation fail (simulated download error)
make_stub_curl() {
  local dir="$1" map_file="$2" fail="$3"
  mkdir -p "$dir"
  cat > "$dir/curl" <<STUB
#!/usr/bin/env bash
fail="$fail"
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
output=$(env -i PATH="$stub_dir:/usr/bin:/bin" FORMULA_DIR="$formula_dir" bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "happy-path-exit" 0 "$code"
assert_contains "happy-path-output" "$output" "verified: widget (widget)"

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
output=$(env -i PATH="$stub_dir:/usr/bin:/bin" FORMULA_DIR="$formula_dir" bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "sha-mismatch-exit" 1 "$code"
assert_contains "sha-mismatch-output" "$output" "sha256 mismatch"

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
output=$(env -i PATH="$stub_dir:/usr/bin:/bin" FORMULA_DIR="$formula_dir" bash "$SCRIPT" 2>&1)
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
output=$(env -i PATH="$fail_stub_dir:/usr/bin:/bin" FORMULA_DIR="$formula_dir" bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "download-fail-exit" 1 "$code"
assert_contains "download-fail-output" "$output" "Download failed"

# --- Case 5: empty Formula dir — regression guard ---
empty_dir="$work_dir/EmptyFormula"
mkdir -p "$empty_dir"
output=$(env -i PATH="$stub_dir:/usr/bin:/bin" FORMULA_DIR="$empty_dir" bash "$SCRIPT" 2>&1)
code=$?
assert_exit_code "empty-dir-exit" 2 "$code"
assert_contains "empty-dir-output" "$output" "No formulae found"

finish "verify_release_artifacts"
