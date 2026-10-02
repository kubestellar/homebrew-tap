#!/usr/bin/env python3
"""Invariant tests for .github/workflows/scheduled-workflow-failure-issue.yml.

This workflow is the single alert gate for the 7 scheduled / main-push
workflow failures named by ``docs/slo.md`` lines 16-18:

    CodeQL Analysis, OpenSSF Scorecard, Fuzzing, Homebrew CI,
    Validate Formulae, Stale Issues, actionlint

Its two load-bearing invariants were previously untested:

1. The ``on.workflow_run.workflows:`` list must contain exactly those
   7 workflow names — a dropped entry silently removes alerting for
   that workflow. ``scripts/test_workflow_failure_notify*.sh`` only
   exercise the body-rendering helper, never the trigger definition.
2. The job-level ``if:`` condition must fire on ``main``-push for every
   watched workflow (not a hard-coded ``name == '...'`` subset).
   kubestellar/homebrew-tap#620 just widened this from a 2-name allow-
   list back to the whole set; a future edit could silently re-narrow
   it, re-opening the alert gap for up to 5 workflows at once.

A third invariant guards the SLO doc from going out of sync with the
workflow itself: every workflow name mentioned in the workflow's
``workflows:`` list must also appear verbatim in ``docs/slo.md``'s
alert-watch paragraph (lines 16-18).

Written as a standalone ``unittest`` module (no third-party dependencies
— avoids introducing PyYAML into ``requirements-dev.in``) so it is
discovered by ``scripts/unittest_summary.sh`` from
``.github/workflows/validate-formulae.yml`` exactly like the other
``scripts/test_formula_*_invariants.py`` modules.
"""

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_FILE = (
    REPO_ROOT / ".github" / "workflows" / "scheduled-workflow-failure-issue.yml"
)
SLO_DOC = REPO_ROOT / "docs" / "slo.md"


EXPECTED_WATCHED_WORKFLOWS = {
    "CodeQL Analysis",
    "OpenSSF Scorecard",
    "Fuzzing",
    "Homebrew CI",
    "Validate Formulae",
    "Stale Issues",
    "actionlint",
}


# Matches the `workflows:` list under `on.workflow_run:` — a run of
# `      - "<name>"` lines terminated by the first non-list line
# (`types:` in this file). Using plain-text matching keeps the test
# dependency-free; see module docstring.
_WORKFLOWS_BLOCK_RE = re.compile(
    r"^\s*workflows:\s*\n((?:\s+-\s+\"[^\"]+\"\s*\n)+)",
    re.MULTILINE,
)
_WORKFLOW_NAME_RE = re.compile(r'^\s*-\s+"([^"]+)"\s*$', re.MULTILINE)

# Matches the job-level `if:` block (a folded `>-` scalar). Captures the
# entire multi-line expression up to the next top-level job key
# (`steps:`), with surrounding whitespace preserved.
_JOB_IF_BLOCK_RE = re.compile(
    r"^\s*if:\s*>-\s*\n((?:[ \t]+[^\n]*\n)+?)(?=^\s*steps:\s*$)",
    re.MULTILINE,
)


def _load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class ScheduledWorkflowFailureIssueInvariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow_text = _load(WORKFLOW_FILE)
        cls.slo_text = _load(SLO_DOC)

        block_match = _WORKFLOWS_BLOCK_RE.search(cls.workflow_text)
        if block_match is None:
            raise AssertionError(
                "could not locate `workflows:` list under `on.workflow_run:` "
                f"in {WORKFLOW_FILE.relative_to(REPO_ROOT)} — the regex that "
                "underlies every invariant below could not anchor"
            )
        cls.watched = [
            m.group(1) for m in _WORKFLOW_NAME_RE.finditer(block_match.group(1))
        ]

        if_match = _JOB_IF_BLOCK_RE.search(cls.workflow_text)
        if if_match is None:
            raise AssertionError(
                "could not locate the job-level `if: >-` block in "
                f"{WORKFLOW_FILE.relative_to(REPO_ROOT)} — the alert-gate "
                "condition cannot be verified"
            )
        cls.if_block = if_match.group(1)

    # ------------------------------------------------------------------
    # Invariant 1: watched set matches the authoritative SLO list.
    # ------------------------------------------------------------------
    def test_watched_workflow_list_matches_slo_doc(self):
        self.assertEqual(
            set(self.watched),
            EXPECTED_WATCHED_WORKFLOWS,
            "`on.workflow_run.workflows:` drifted from docs/slo.md's "
            "alert-watch list — dropping an entry silently removes "
            "alerting for that workflow; adding an unlisted one hides a "
            "stale/undocumented alert source",
        )

    def test_watched_workflow_list_has_no_duplicates(self):
        self.assertEqual(
            len(self.watched),
            len(set(self.watched)),
            "`on.workflow_run.workflows:` has duplicate entries: "
            f"{self.watched!r}",
        )

    # ------------------------------------------------------------------
    # Invariant 2: main-push alert gate is not re-narrowed to a subset.
    # Regression test for kubestellar/homebrew-tap#620.
    # ------------------------------------------------------------------
    def test_if_block_fires_on_main_push_unconditionally(self):
        self.assertIn(
            "github.event.workflow_run.head_branch == 'main'",
            self.if_block,
            "job `if:` no longer references head_branch == 'main' — "
            "main-push failures of every watched workflow will stop "
            "opening the kind/bug alert issue (regression of #620)",
        )

    def test_if_block_does_not_subset_main_push_by_workflow_name(self):
        # kubestellar/homebrew-tap#620's whole point was removing the
        # `(name == 'Homebrew CI' || name == 'Validate Formulae')`
        # subset clause from the main-push arm. Any reappearance of a
        # `workflow_run.name == '...'` *filter* in the main-push arm
        # re-opens the alert gap for the other 5 workflows.
        self.assertNotRegex(
            self.if_block,
            r"github\.event\.workflow_run\.name\s*==",
            "job `if:` reintroduced a `workflow_run.name == '...'` "
            "subset filter on the main-push arm — this silently drops "
            "main-push alerts for every workflow name not listed. "
            "Regression of kubestellar/homebrew-tap#620.",
        )

    def test_if_block_covers_schedule_and_workflow_dispatch(self):
        for event in ("schedule", "workflow_dispatch"):
            with self.subTest(event=event):
                self.assertIn(
                    f"github.event.workflow_run.event == '{event}'",
                    self.if_block,
                    f"job `if:` dropped the `{event}` arm — scheduled / "
                    "manually-dispatched failures of watched workflows "
                    "will no longer open the kind/bug alert issue",
                )

    def test_if_block_requires_failure_conclusion(self):
        self.assertIn(
            "github.event.workflow_run.conclusion == 'failure'",
            self.if_block,
            "job `if:` dropped the `conclusion == 'failure'` guard — "
            "the alert issue would open on every workflow_run event, "
            "including successes and cancellations",
        )

    # ------------------------------------------------------------------
    # Invariant 3: SLO doc stays in sync with the workflow file.
    # ------------------------------------------------------------------
    def test_slo_doc_mentions_every_watched_workflow(self):
        for name in self.watched:
            with self.subTest(workflow=name):
                self.assertIn(
                    name,
                    self.slo_text,
                    f"docs/slo.md does not mention {name!r} — the "
                    "SLO doc's alert-watch paragraph (lines 16-18) "
                    "must list every workflow the workflow file "
                    "actually watches, or the SLO documentation "
                    "silently misstates alert coverage",
                )


if __name__ == "__main__":
    unittest.main()
