#!/usr/bin/env bash
# fuzz_summary.sh — emit a single-line, machine-readable summary of a
# fuzz.yml run, mirroring the VALIDATE_FORMULAE_SUMMARY: pattern already
# emitted by scripts/validate_formulae.py.
#
# fuzz.yml's final "Fuzzing summary" step currently only prints decorative
# free-text ("Fuzzing completed successfully!") and is skipped entirely
# whenever an earlier fuzz step fails (no `if: always()`), so there is no
# structured pass/fail record in CI logs for the "Formula fuzz health" SLI
# tracked in docs/slo.md.
#
# This is a standalone script, not wired into any workflow here: wiring it
# into fuzz.yml requires editing .github/workflows/fuzz.yml, which needs the
# `workflows` permission this script does not assume. A maintainer can wire
# it in with a final step along these lines:
#
#   - name: Fuzzing summary
#     if: always()
#     env:
#       SYNTAX_OUTCOME: ${{ steps.syntax.outcome }}
#       STRUCTURE_OUTCOME: ${{ steps.structure.outcome }}
#       URL_CHECKSUM_OUTCOME: ${{ steps.url_checksum.outcome }}
#     run: scripts/fuzz_summary.sh
#
# (which requires adding `id: syntax` / `id: structure` / `id: url_checksum`
# to the three preceding fuzz steps).
#
# Stdout-only structured output: no exporter, metrics backend, or off-box
# data flow is added.
#
# Usage: SYNTAX_OUTCOME=success STRUCTURE_OUTCOME=success \
#        URL_CHECKSUM_OUTCOME=success scripts/fuzz_summary.sh
#
# Exit status: 0 if every outcome is "success", 1 otherwise.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FORMULA_DIR="${FORMULA_DIR:-$REPO_ROOT/Formula}"

SYNTAX_OUTCOME="${SYNTAX_OUTCOME:-unknown}"
STRUCTURE_OUTCOME="${STRUCTURE_OUTCOME:-unknown}"
URL_CHECKSUM_OUTCOME="${URL_CHECKSUM_OUTCOME:-unknown}"

formula_count=0
if [ -d "$FORMULA_DIR" ]; then
  for f in "$FORMULA_DIR"/*.rb; do
    [ -e "$f" ] || continue
    formula_count=$((formula_count + 1))
  done
fi

overall_status="success"
for outcome in "$SYNTAX_OUTCOME" "$STRUCTURE_OUTCOME" "$URL_CHECKSUM_OUTCOME"; do
  if [ "$outcome" != "success" ]; then
    overall_status="failure"
  fi
done

printf 'FUZZ_SUMMARY: {"status":"%s","formula_count":%s,"syntax":"%s","structure":"%s","url_checksum":"%s"}\n' \
  "$overall_status" "$formula_count" "$SYNTAX_OUTCOME" "$STRUCTURE_OUTCOME" "$URL_CHECKSUM_OUTCOME"

if [ "$overall_status" != "success" ]; then
  exit 1
fi
