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
# Usage: scripts/verify_release_artifacts.sh [--list]
#   FORMULA_DIR  - directory of *.rb formulae (default: <repo root>/Formula)
#   --list       - print "<name>\t<url>\t<sha256>\t<bin_name>" triples to
#                  stdout instead of downloading/verifying anything. Lets
#                  scripts/test_verify_release_artifacts_parser_parity.py
#                  assert this script's shell-out to
#                  formula_parser.extract_release_triples() (the single
#                  owner of the Formula/*.rb triple extraction) keeps
#                  agreeing with calling it in-process (see
#                  kubestellar/homebrew-tap#647).
#
# Exit codes:
#   0 - every (url, sha256, binary) triple verified (or, under --list,
#       triples were printed)
#   1 - a download failure, sha256 mismatch, or missing binary was found
#   2 - no formulae discovered (empty-suite regression guard)

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FORMULA_DIR="${FORMULA_DIR:-$REPO_ROOT/Formula}"
CURL="${CURL:-curl}"
TAR="${TAR:-tar}"
PYTHON="${PYTHON:-python3}"

list_only=0
for arg in "$@"; do
  case "$arg" in
    --list) list_only=1 ;;
    *)
      echo "verify_release_artifacts: unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

# extract_triples <formula-file> — print one
# "<url>\t<sha256>\t<bin_name>" line per (url, sha256, binary) triple
# found in <formula-file>, one per Hardware::CPU branch.
#
# Thin shell-out to scripts/formula_parser.py's extract_release_triples()
# via its `--triples` CLI — the single shared owner of this extraction —
# rather than a second, un-sync'd bash parser (see
# kubestellar/homebrew-tap#647).
# test_verify_release_artifacts_parser_parity.py asserts this script's
# --list output agrees with extract_release_triples() called in-process,
# guarding the shell-out plumbing itself.
extract_triples() {
  local formula="$1"
  "$PYTHON" "$REPO_ROOT/scripts/formula_parser.py" --triples "$formula"
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

  if [ "$list_only" -eq 1 ]; then
    while IFS=$'\t' read -r url sha bin_name; do
      printf '%s\t%s\t%s\t%s\n' "$name" "$url" "$sha" "$bin_name"
    done < <(extract_triples "$formula")
    continue
  fi

  while IFS=$'\t' read -r url sha bin_name; do
    checked_count=$((checked_count + 1))
    echo "::group::verify $name: $(basename "$url")"
    tmp="$(mktemp -d)"
    tarball="$tmp/artifact.tar.gz"
    if ! "$CURL" -fsSL -o "$tarball" "$url"; then
      echo "::error title=Download failed::$name: could not fetch $url"
      fail_count=$((fail_count + 1))
      rm -rf "$tmp"
      echo "::endgroup::"
      continue
    fi
    actual_sha="$(sha256_of "$tarball")"
    if [ "$actual_sha" != "$sha" ]; then
      echo "::error title=sha256 mismatch::$name: $url expected $sha got $actual_sha"
      fail_count=$((fail_count + 1))
      rm -rf "$tmp"
      echo "::endgroup::"
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
  done < <(extract_triples "$formula")
done

if [ "$list_only" -eq 1 ]; then
  exit 0
fi

echo "verify_release_artifacts: checked $checked_count artifact(s), $fail_count failure(s)"
if [ "$fail_count" -gt 0 ]; then
  exit 1
fi
exit 0
