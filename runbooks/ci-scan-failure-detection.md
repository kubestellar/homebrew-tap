# CI / Scheduled-Scan Failure Detection Runbook (superseded)

**Repository:** `kubestellar/homebrew-tap`
**Applies to:** `brew-ci.yml`, `validate-formulae.yml`, `codeql.yml` (weekly
schedule), `scorecard.yml` (weekly schedule)

> **Superseded by automation.** The gap this runbook was written to work
> around is closed: `.github/workflows/scheduled-workflow-failure-issue.yml`
> (applied in #441, extended in #479/#508/#551/#580) now auto-files a
> `kind/bug` + `workflow-failure` tracking issue on a failing scheduled or
> `main`-branch run of `CodeQL Analysis`, `OpenSSF Scorecard`, `Fuzzing`,
> `Homebrew CI`, `Validate Formulae`, `Stale Issues`, and `actionlint` — see
> [`docs/slo.md`](../docs/slo.md) and the
> [Scheduled Workflow Failure Runbook](./scheduled-workflow-failure.md), which
> is now the primary runbook for these failures. **Use that runbook, not the
> manual steps below**, which are kept only as historical background on why
> this gap originally existed (#316, #318, #337).

---

## Why This Existed (background only)

None of the watched workflows had an `if: failure()` notification step, and
`brew-ci.yml` / `validate-formulae.yml` only triggered on `Formula/**`
changes rather than on a schedule (see #316, #318, #337). That means:

- A failing `main`-branch CI run produced only a red check on a commit that
  nobody was necessarily looking at.
- A failing weekly `codeql.yml` or `scorecard.yml` scheduled scan produced no
  notification at all — the only surface was the Actions tab.
- If Formula files went untouched for a while, drift (e.g. an upstream
  URL/checksum going stale) between `brew-ci.yml` runs was invisible until the
  next Formula PR.

This has since been closed by
[`.github/workflows/scheduled-workflow-failure-issue.yml`](../.github/workflows/scheduled-workflow-failure-issue.yml),
which required a maintainer with the `workflows` permission to apply (agent
tokens in this repo don't carry it) — that landing is why this document is
now superseded rather than actively maintained.

---

## Manual Detection Steps (historical — superseded, see banner above)

Run this check periodically (recommended: weekly, and immediately after any
Formula change lands):

1. **Scheduled scans** — open the Actions tab and filter by workflow:
   - `CodeQL Analysis` — confirm the most recent run (cron `0 4 * * 1`)
     succeeded.
   - `OpenSSF Scorecard` — confirm the most recent run (cron `0 6 * * 1`)
     succeeded.
   A missing run entirely for the expected week is itself a signal — it means
   the schedule stopped firing (e.g. from 60+ days of repo inactivity, which
   GitHub Actions treats as a reason to disable scheduled workflows).

2. **Push-triggered CI** — for `brew-ci.yml` and `validate-formulae.yml`,
   check the status of the latest run on `main`. Since these only trigger on
   `Formula/**`, `README.md`, or workflow-file changes, also check whether the
   last run predates any change to those paths that should have retriggered
   it — a large gap indicates the trigger paths need review, not just the
   run result.

3. **Fuzzing** — `fuzz.yml` only runs on `Formula/**` changes and
   `workflow_dispatch`; there is no weekly schedule for it. If no Formula
   change has landed recently, manually trigger it via `workflow_dispatch` to
   confirm formulae still pass the fuzz checks.

---

## Triage

- **Flaky infra** (transient `setup-homebrew` failure, runner image issue,
  upstream timeout) — re-run the failed job from the Actions tab.
- **Real regression** (formula syntax/structure error, failing unit test, new
  CodeQL/Scorecard finding) — file or update a tracking issue, fix the
  underlying code/formula, and confirm the next run is green. Do not close
  out based on the fix landing alone.
- **Security finding** (CodeQL/Scorecard) — treat as highest priority; do not
  disable the check or weaken permissions to make it pass.
- If a failure affects a **released** formula, cross-reference
  [`runbooks/formula-rollback.md`](./formula-rollback.md) to decide whether a
  rollback is also needed.

---

## Closing the Loop (done)

The automated alert described above landed and now:

- Triggers on `workflow_run` for `CodeQL Analysis`, `OpenSSF Scorecard`,
  `Fuzzing`, `Homebrew CI`, `Validate Formulae`, `Stale Issues`, and
  `actionlint`.
- Files (or comments on) a single open `kind/bug` + `workflow-failure`
  tracking issue per workflow to avoid duplicate noise on repeat failures.
- Links back to the [Scheduled Workflow Failure Runbook](./scheduled-workflow-failure.md).

Follow that runbook for any new scheduled/`main` failure. This file is kept
only for historical context on why the gap originally existed.
