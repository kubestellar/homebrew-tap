# Scheduled Workflow Failure Runbook

**Repository:** `kubestellar/homebrew-tap`
**Applies to:** `CodeQL Analysis`, `OpenSSF Scorecard`, `Fuzzing`, `Homebrew CI`, `Validate Formulae`

---

## When to Use This Runbook

Use this runbook once a maintainer has applied
[`proposed-scheduled-workflow-failure-issue.yml`](proposed-scheduled-workflow-failure-issue.yml)
under `.github/workflows/` (this repo's operations-agent GitHub App
installation lacks the `workflows` permission needed to do so itself — see
that file's header) and you are assigned, or notice, an auto-filed issue
titled `Workflow failure: <workflow name>` and labeled `workflow-failure`.
That issue is created whenever:

- A scheduled (`cron`) or manually (`workflow_dispatch`) triggered run of
  `CodeQL Analysis`, `OpenSSF Scorecard`, or `Fuzzing` fails, or
- `Homebrew CI` or `Validate Formulae` fails on `main`.

This closes the alert gap described in [`docs/slo.md`](../docs/slo.md#slos-service-level-objectives):
previously these scheduled/`main` runs could fail silently, with detection
depending on someone noticing a red check.

## Immediate Triage

1. Open the linked run from the auto-filed issue and read the failing step's
   logs.
2. Classify the failure:
   - **Infrastructure/transient** (runner outage, network timeout, upstream
     rate limit) — re-run the workflow (`gh run rerun <run-id> --repo
     kubestellar/homebrew-tap`) and comment the outcome on the issue.
   - **Real regression** (formula syntax/structure break, dependency scan
     finding, drift check failure) — proceed to step 3.
3. For `Homebrew CI` / `Validate Formulae` failures on `main`, treat as a
   candidate incident per [`docs/slo.md`](../docs/slo.md) and follow the
   [Formula Rollback Runbook](formula-rollback.md) if user installs are
   affected.
4. For `CodeQL Analysis` / `OpenSSF Scorecard` failures, distinguish a scan
   *execution* failure (the job itself errored — fix the workflow/config)
   from a scan *finding* (a security alert was reported — triage under
   normal vulnerability handling, not this runbook).
5. For `Fuzzing` failures, check whether a recent `Formula/**` change or an
   unrelated shared-script change (e.g. to `scripts/validate_formulae.py`)
   caused the regression, then fix and re-run.

## Closing the Loop

- Fix the underlying cause and confirm the workflow passes on `main` (or via
  `workflow_dispatch`).
- **Do not close** the auto-filed issue until that passing run is confirmed —
  the workflow does not auto-close issues; a maintainer must close it once
  green.
- If the same workflow keeps failing repeatedly for unrelated causes,
  consider whether the workflow itself needs to be fixed or split, and file a
  tracking issue for that separately.

## Notes

- The alert workflow only fires for `schedule`/`workflow_dispatch` events (for
  `CodeQL Analysis`, `OpenSSF Scorecard`, `Fuzzing`) or `main`-branch runs (for
  `Homebrew CI`, `Validate Formulae`) — pull-request failures are already
  visible via the PR's own status checks and do not need a duplicate issue.
- No runtime backend or metrics exporter is added by this mechanism; it is a
  GitHub Actions `workflow_run` → `gh issue create`/`comment` job only, per the
  no-backend-configured scope of this repository (see `docs/slo.md`).
