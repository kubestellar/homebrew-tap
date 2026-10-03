#!/usr/bin/env bash
# verify_release_artifacts.sh — downloads and inspects every per-arch
# release tarball referenced by Formula/*.rb (all 4 OS/arch branches),
# not just the 2 branches `brew install` ever reaches on CI.
#
# Why: brew-ci.yml's matrix (macos-latest = arm64, ubuntu-latest = amd64)
# only ever executes the `define_method(:install)` branch matching the
# runner's own architecture — macos-arm64 and linux-amd64. The
# macos-intel (`Hardware::CPU.intel?` under `on_macos`) and linux-arm64
# (`Hardware::CPU.arm? && is_64_bit?` under `on_linux`) branches are
# parsed/audited statically by `brew audit --strict` and the
# test_formula_*_invariants.py suite, but their release tarball is never
# actually fetched, sha256-checked, or inspected by CI — a broken,
# missing, or mismatched-binary artifact on those two platforms would
# only surface when a real user on that platform runs `brew install`.
#
# This script closes that gap WITHOUT needing extra runner
# architectures: it downloads every formula's every (url, sha256,
# binary-name) triple directly — no `brew`/Homebrew involved — verifies
# the sha256 against the formula's declared value, extracts the
# tarball, and checks the binary named in that branch's
# `bin.install "<name>"` is present inside the archive. Runs the same
# way on any single runner regardless of its own OS/arch, so it
# exercises all 4 branches even though brew-ci.yml's matrix only ever
# runs 2.
#
# Usage: scripts/verify_release_artifacts.sh
#   FORMULA_DIR  - directory of *.rb formulae (default: <repo root>/Formula)
#
# Exit codes:
#   0 - every (url, sha256, binary) triple verified
#   1 - a download failure, sha256 mismatch, or missing binary was found
#   2 - no formulae discovered (empty-suite regression guard)

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FORMULA_DIR="${FORMULA_DIR:-$REPO_ROOT/Formula}"
CURL="${CURL:-curl}"
TAR="${TAR:-tar}"

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

fail_count=0
checked_count=0

shopt -s nullglob
formulae=("$FORMULA_DIR"/*.rb)
shopt -u nullglob

if [ "${#formulae[@]}" -eq 0 ]; then
  echo "::error title=No formulae found::verify_release_artifacts: no *.rb files under $FORMULA_DIR" >&2
  exit 2
fi

for formula in "${formulae[@]}"; do
  name="$(basename "$formula" .rb)"
  # Pull ordered (url, sha256, bin_name) triples by scanning line-by-line
  # and tracking the most recently seen `url`/`sha256` until the next
  # `bin.install "..."` closes out the triple. Matches the consistent
  # GoReleaser-generated shape: url, then sha256, then
  # `define_method(:install) { bin.install "<name>" }` within the same
  # Hardware::CPU branch, repeated once per branch.
  url="" sha=""
  while IFS= read -r line; do
    case "$line" in
      *'url "'*)
        url="${line#*url \"}"; url="${url%%\"*}"
        sha=""
        ;;
      *'sha256 "'*)
        sha="${line#*sha256 \"}"; sha="${sha%%\"*}"
        ;;
      *'bin.install "'*)
        bin_name="${line#*bin.install \"}"; bin_name="${bin_name%%\"*}"
        if [ -n "$url" ] && [ -n "$sha" ]; then
          checked_count=$((checked_count + 1))
          echo "::group::verify $name: $(basename "$url")"
          tmp="$(mktemp -d)"
          tarball="$tmp/artifact.tar.gz"
          if ! "$CURL" -fsSL -o "$tarball" "$url"; then
            echo "::error title=Download failed::$name: could not fetch $url"
            fail_count=$((fail_count + 1))
            rm -rf "$tmp"
            echo "::endgroup::"
            url="" sha=""
            continue
          fi
          actual_sha="$(sha256_of "$tarball")"
          if [ "$actual_sha" != "$sha" ]; then
            echo "::error title=sha256 mismatch::$name: $url expected $sha got $actual_sha"
            fail_count=$((fail_count + 1))
            rm -rf "$tmp"
            echo "::endgroup::"
            url="" sha=""
            continue
          fi
          if ! "$TAR" -tzf "$tarball" | grep -qx "$bin_name"; then
            echo "::error title=Binary missing from archive::$name: $bin_name not found in $(basename "$url")"
            fail_count=$((fail_count + 1))
          else
            echo "verified: $name ($bin_name) sha256 + archive contents OK"
          fi
          rm -rf "$tmp"
          echo "::endgroup::"
          url="" sha=""
        fi
        ;;
    esac
  done < "$formula"
done

echo "verify_release_artifacts: checked $checked_count artifact(s), $fail_count failure(s)"
if [ "$fail_count" -gt 0 ]; then
  exit 1
fi
exit 0
