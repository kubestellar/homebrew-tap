# CI / Scheduled-Scan Failure Detection Runbook

**Repository:** `kubestellar/homebrew-tap`
**Applies to:** `brew-ci.yml`, `validate-formulae.yml`, `codeql.yml` (weekly
schedule), `scorecard.yml` (weekly schedule)

---

## Why This Exists

None of the watched workflows currently have an `if: failure()` notification
step, and `brew-ci.yml` / `validate-formulae.yml` only trigger on `Formula/**`
changes rather than on a schedule (see #316, #318, #337). That means:

- A failing `main`-branch CI run produces only a red check on a commit that
  nobody is necessarily looking at.
- A failing weekly `codeql.yml` or `scorecard.yml` scheduled scan produces no
  notification at all — the only surface is the Actions tab.
- If Formula files go untouched for a while, drift (e.g. an upstream
  URL/checksum going stale) between `brew-ci.yml` runs is invisible until the
  next Formula PR.

Adding automated `if: failure()` alerting requires editing files under
`.github/workflows/`, which needs the GitHub App `workflows` permission that
agent tokens in this repo do not carry. This runbook documents the manual
detection workaround in the meantime; the automated fix (following the same
`actions/github-script`-based failure-issue pattern used for the equivalent
gap in other kubestellar repos) still needs a maintainer with `workflows`
scope to apply directly to the four files above.

---

## Manual Detection Steps

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

## Closing the Loop (for the eventual automated fix)

When a maintainer with `workflows` permission implements the automated
alert, it should:

- Trigger on `workflow_run` (or an `if: failure()` step) for `brew-ci.yml`,
  `validate-formulae.yml`, `codeql.yml`, and `scorecard.yml`.
- File (or comment on) a single open tracking issue per workflow to avoid
  duplicate noise on repeat failures.
- Link back to this runbook from the issue body.

Once that lands, this file should be updated to describe the automated flow
instead of the manual steps above.
