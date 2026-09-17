#!/usr/bin/env bash
# formula_fuzz.sh — Formula/**/*.rb syntax, structure, and URL/checksum
# fuzzing extracted from `.github/workflows/fuzz.yml`.
#
# The three fuzzing phases used to live as ~60 lines of inline bash in
# fuzz.yml, in three separate `run:` blocks. That made the fuzzing logic
# untestable: any regression (e.g. weakening a guard, dropping a check,
# breaking the http-vs-https regex) could only be caught by watching a
# live fuzz.yml run, not by scripts/run_shell_tests.sh in CI. This
# script consolidates the same logic into a single testable entry point
# so scripts/test_formula_fuzz.sh (auto-discovered by
# scripts/run_shell_tests.sh) locks the behavior down. See #465 / #479
# for the same extraction pattern applied to run_shell_tests.sh,
# unittest_summary.sh, and the summary emitters — this closes the last
# fuzz-workflow instance of that pattern.
#
# Behavior is byte-equivalent to the current inline steps:
#   1. Every Formula/*.rb must pass `ruby -c` (syntax fuzzing).
#   2. Every Formula/*.rb must define a Formula subclass, contain at
#      least one of `desc|homepage|url`, and declare an install method.
#   3. Every `url "…"` must match `^https?://`, and any file declaring
#      a `url "…"` must also declare at least one `sha256` line.
# Any failure across the three phases exits 1; all-pass exits 0. Errors
# are logged to stderr with the same ❌/✅ markers the workflow used so
# CI logs stay grep-comparable.
#
# Usage: scripts/formula_fuzz.sh [FORMULA_DIR]
#   FORMULA_DIR defaults to "Formula". A missing/empty directory is a
#   hard failure (exit 1) — matches the workflow, where a Formula/*.rb
#   glob that expanded to the literal "Formula/*.rb" would `ruby -c`
#   that nonexistent path and fail.

set -uo pipefail

formula_dir="${1:-Formula}"

if ! compgen -G "$formula_dir"/*.rb >/dev/null; then
  echo "❌ No formula files found in $formula_dir" >&2
  exit 1
fi

failed=0

echo "Validating Ruby syntax for all formula files..."
for formula in "$formula_dir"/*.rb; do
  echo "Checking $formula..."
  if ! ruby -c "$formula" >/dev/null 2>&1; then
    echo "❌ Syntax error in $formula"
    ruby -c "$formula"
    failed=1
  else
    echo "✅ $formula is valid"
  fi
done

echo "Fuzzing formula structure..."
for formula in "$formula_dir"/*.rb; do
  echo "Testing $formula..."

  if ! grep -q "class.*< Formula" "$formula"; then
    echo "❌ Missing Formula class in $formula"
    failed=1
    continue
  fi

  if ! grep -E -q "desc|homepage|url" "$formula"; then
    echo "❌ Missing metadata in $formula"
    failed=1
  fi

  if ! grep -q "def install\|define_method(:install)" "$formula"; then
    echo "❌ Missing install method in $formula"
    failed=1
  fi

  echo "✅ $formula passed structure checks"
done

echo "Fuzzing URLs and checksums..."
for formula in "$formula_dir"/*.rb; do
  echo "Testing URLs in $formula..."

  # Extract URLs and validate format (process substitution keeps exit
  # status in this shell, not a subshell)
  while read -r line; do
    url=$(echo "$line" | sed -n 's/.*url\s*"\([^"]*\)".*/\1/p')
    if [ -n "$url" ]; then
      if [[ ! "$url" =~ ^https?:// ]]; then
        echo "❌ Invalid URL format: $url"
        failed=1
      else
        echo "✅ Valid URL format: $url"
      fi
    fi
  done < <(grep -E 'url\s+"[^"]+"' "$formula")

  if grep -q "url\s*\"" "$formula"; then
    if ! grep -q "sha256" "$formula"; then
      echo "❌ Missing sha256 checksum in $formula"
      failed=1
    fi
  fi
done

if [ "$failed" -eq 1 ]; then
  echo "Formula fuzzing failed"
  exit 1
fi

echo "✅ Formula fuzzing passed"
exit 0
