#!/usr/bin/env bash
# verify_pr_title.sh — validate a pull-request title against the
# repository's title convention (Conventional Commits OR the KubeStellar
# emoji convention, both with an optional agent-lane prefix).
#
# The regex logic here was previously inlined into
# .github/workflows/pr-verifier.yml with no regression tests, so a title
# format that legitimately should have been accepted (e.g. a new emoji or
# a title starting with a bare lane prefix) could only be verified by
# opening a PR against main and watching the check fail. Extracting the
# logic here lets scripts/test_verify_pr_title.sh cover every branch of
# the regex with no CI round-trip.
#
# The workflow now calls this script directly (see
# .github/workflows/pr-verifier.yml — the "Validate PR title" step runs
# `scripts/verify_pr_title.sh`, no regex is inlined), so this script is
# the single source of truth for the PR-title convention and a regex
# change here does not require a paired workflow edit.
#
# Usage:
#   PR_TITLE='fix: correct typo' scripts/verify_pr_title.sh
#   scripts/verify_pr_title.sh 'fix: correct typo'
#
# Exit status: 0 if the title is valid, 1 otherwise (and a
# ::error::-annotated help block is written to stdout for GitHub Actions
# to surface as a check annotation).
#
# On every exit path this also emits a single-line
# 'VERIFY_PR_TITLE_SUMMARY: {status,title_length}' record via the shared
# scripts/lib_emit_summary.sh helper (the same contract every other
# scripts/ gate uses: BREW_CI_SUMMARY, FUZZ_SUMMARY, UNITTEST_SUMMARY,
# COVERAGE_GATE_SUMMARY, RUN_SHELL_TESTS_SUMMARY, VERIFY_RELEASE_HEALTH_SUMMARY).
# Previously this was the one pass/fail gate in scripts/ whose only
# machine-checkable outcome was its process exit code — a reader had to
# re-run the script (or dig through the raw workflow log) to learn
# whether a given CI run's title check passed or failed. `title_length`
# (not the title text itself, which may be arbitrary/unbounded) is
# included as a bounded integer so the record stays a fixed, grep-able
# shape with no unbounded label values.
#
# Stdout-only structured output: no exporter, metrics backend, or
# off-box data flow is added.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib_emit_summary.sh
. "$REPO_ROOT/scripts/lib_emit_summary.sh"

pr_title="${1-${PR_TITLE-}}"

# A title is valid if it is either:
#   (a) Conventional Commits            -> "docs: ..." / "feat(scope)!: ..."
#   (b) the KubeStellar emoji convention -> "🌱 ..." / "🐛 ..."
# Both forms may carry an optional agent-lane prefix such as
# "[operations] " or "[scanner] ". The lane is matched generically
# instead of from a fixed allowlist: the previous allowlist named only
# scanner/agent/ci-maintainer/quality/sec-check, so every PR opened by
# the operations, telemetry and docs lanes failed this gate purely
# because its lane was missing from that list.
EMOJI='(✨|🐛|📖|📝|⚠️|⚠|🌱)'
LANE='\[[a-z][a-z0-9-]*\]'
TYPE='(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\(.+\))?!?'

CONVENTIONAL="^($EMOJI )?($LANE )?($EMOJI )?$TYPE: .+"
EMOJI_STYLE="^($LANE )?$EMOJI ($LANE )?.+"

if printf '%s' "$pr_title" | grep -qE "$CONVENTIONAL" \
  || printf '%s' "$pr_title" | grep -qE "$EMOJI_STYLE"; then
  echo "PR title is valid: $pr_title"
  emit_ci_summary VERIFY_PR_TITLE_SUMMARY \
    status="pass" title_length="${#pr_title}"
  exit 0
fi

echo "::error::PR title must use Conventional Commits or the KubeStellar emoji prefix."
echo ""
echo "Use either form (an optional [lane] prefix is allowed on both):"
echo ""
echo "  Conventional Commits:"
echo "    fix: correct typo"
echo "    feat(scope): add feature"
echo "    [operations] docs: refresh SLO doc"
echo ""
echo "  Emoji convention:"
echo "    🌱 [scanner] ci: coverage for validate-formulae"
echo "    📖 Document the release-sync gap"
echo ""
echo "Allowed types: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert"
echo "Allowed emoji: ✨ feature | 🐛 fix | 📖 docs | 📝 proposal | ⚠️ breaking | 🌱 other"
emit_ci_summary VERIFY_PR_TITLE_SUMMARY \
  status="fail" title_length="${#pr_title}"
exit 1
