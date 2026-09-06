# SLOs / SLIs — kubestellar/homebrew-tap

This tap has no runtime backend of its own — it ships Homebrew formulae
(`kubestellar-ops`, `kubestellar-deploy`, `kc-agent`) that resolve, at
`brew install`/`brew upgrade` time, to release artifacts published by the
upstream [`kubestellar-mcp`](https://github.com/kubestellar/kubestellar-mcp)
repository. Because `main` is served live to every `brew install` the moment a
formula change merges, CI health on `main` is the primary user-facing signal
for this repo. No exporter, metrics backend, or external data flow is added by
this document — it defines SLIs derived from existing GitHub Actions checks
and recommends how to interpret them operationally. It also links a
ready-to-apply, but not yet active, `workflow_run`-based alert spec (see
[`runbooks/proposed-scheduled-workflow-failure-issue.yml`](../runbooks/proposed-scheduled-workflow-failure-issue.yml)
and the [Scheduled Workflow Failure Runbook](../runbooks/scheduled-workflow-failure.md))
that a maintainer with `workflows` permission can apply to close the alert
gaps described below.

## User-facing service

`brew install kubestellar/tap/<formula>` and `brew upgrade kubestellar/tap/<formula>`,
for all three formulae, on macOS and Linux, amd64 and arm64.

## SLIs (Service Level Indicators)

| SLI | Definition | Source |
|-----|------------|--------|
| **Formula CI health** | Fraction of `brew-ci.yml` runs on `main` that succeed (brew audit --strict + install smoke test, per OS) | [brew-ci.yml](../.github/workflows/brew-ci.yml) run history |
| **Formula drift health** | Fraction of `validate-formulae.yml` runs on `main` that succeed (unit tests + drift check) | [validate-formulae.yml](../.github/workflows/validate-formulae.yml) run history |
| **Time to detect a broken release** | Time from a broken formula merging to `main` until CI reports failure or a `kind/bug` incident issue is filed | CI run timestamp vs. merge timestamp, or issue `created_at` |
| **Time to rollback/mitigate** | Time from incident detection to a rollback PR merged or formula pinned per the [Formula Rollback Runbook](../runbooks/formula-rollback.md) | Incident issue timeline |
| **Weekly security-scan health** | Fraction of scheduled `CodeQL Analysis` (`0 4 * * 1`) and `Scorecard analysis` (`0 6 * * 1`) runs that complete successfully | [codeql.yml](../.github/workflows/codeql.yml) / [scorecard.yml](../.github/workflows/scorecard.yml) run history |
| **Formula fuzz health** | Fraction of `Fuzzing` (`fuzz.yml`: syntax, structure, URL/checksum checks) runs that succeed | [fuzz.yml](../.github/workflows/fuzz.yml) run history |

## SLOs (Service Level Objectives)

- **Formula CI health ≥ 99%** measured over a rolling 30-day window of merges to `main`.
  A red `main` check on `brew-ci.yml` or `validate-formulae.yml` means the next
  `brew install`/`brew upgrade` for at least one formula is very likely broken for
  end users — treat every `main` failure as a candidate incident, not routine noise.
- **Formula CI health** and **Formula drift health** currently only get a data
  point when a `Formula/**` (or related-path) change triggers `brew-ci.yml` /
  `validate-formulae.yml` on `main`. Neither workflow has a `schedule:` trigger,
  so a break with **no matching Formula diff** — e.g. an upstream
  [`kubestellar-mcp`](https://github.com/kubestellar/kubestellar-mcp) release
  being deleted/re-tagged/pruned, a transient CDN/host 404 on the pinned
  release URL, or a yanked binary after its `sha256` was already pinned — goes
  undetected indefinitely between merges, with the ≤15-minute detection SLO
  below having no mechanism behind it for this failure class. **Recommendation:**
  add a daily `schedule:` trigger to `brew-ci.yml` and/or `validate-formulae.yml`
  (see the proposed diff on
  [#318](https://github.com/kubestellar/homebrew-tap/issues/318)) so the tap's
  live installability is re-verified on a cadence, not only on a Formula push.
- **Time to detect a broken `main` release ≤ 15 minutes.** CI on `main` normally
  completes well within this window; a failed run should be triaged as soon as it
  is reported. **Recommendation:** no automated alert currently fires on a `main`
  CI failure here — today, detection relies on someone noticing the red check on
  `main` or a user filing an issue. A ready-to-apply `workflow_run`-triggered job
  that files a `kind/bug` tracking issue on failure (linking this doc and the
  [Scheduled Workflow Failure Runbook](../runbooks/scheduled-workflow-failure.md))
  is checked in at
  [`runbooks/proposed-scheduled-workflow-failure-issue.yml`](../runbooks/proposed-scheduled-workflow-failure-issue.yml) —
  applying it (moving it under `.github/workflows/`) requires `workflows`
  permission this agent's GitHub App installation does not have.
- **Time to rollback/mitigate ≤ 2 hours** for a confirmed broken release, using the
  [Formula Rollback Runbook](../runbooks/formula-rollback.md). Incidents exceeding
  this budget, or affecting more than a handful of users, should get a
  [postmortem](postmortem-template.md).
- **Weekly security-scan health ≥ 99%** for the scheduled `CodeQL Analysis` and
  `Scorecard analysis` runs. Both already run on a weekly `schedule:` trigger, but
  — like the CI failure gap above — **no automated alert currently fires** if a
  scheduled run itself fails to complete (as opposed to reporting findings); a
  silent failure here means a security regression could go undetected for an
  entire week. The proposed
  [`runbooks/proposed-scheduled-workflow-failure-issue.yml`](../runbooks/proposed-scheduled-workflow-failure-issue.yml)
  also watches `CodeQL Analysis` and `Scorecard analysis`.
- **Formula fuzz health ≥ 99%**, and detection latency for a fuzz regression should
  match the ≤ 15 minute target above. Unlike `CodeQL Analysis`/`Scorecard analysis`,
  `fuzz.yml` has **no `schedule:` trigger at all** — it only runs on `push`/`pull_request`
  that touch `Formula/**`. Between such changes, nothing re-validates formula
  syntax, structure, or URL/checksum format on a cadence, so a regression with no
  matching Formula diff (e.g. from a shared script change) would go undetected
  indefinitely. **Recommendation:** add a weekly `schedule:` trigger to `fuzz.yml`
  (e.g. `0 8 * * 1`, offset from `codeql.yml`'s `0 4 * * 1` and `scorecard.yml`'s
  `0 6 * * 1`) and include `Fuzzing` in the proposed
  [`scheduled-workflow-failure-issue.yml`](../runbooks/proposed-scheduled-workflow-failure-issue.yml)
  alert's watch list, as that spec already assumes.

## Recommendations (no backend configured)

No observability backend (metrics/tracing exporter) is confirmed for this repository,
and none is added here. If one is adopted in the future, the SLIs above map cleanly to:

- A counter/ratio of `brew-ci.yml` and `validate-formulae.yml` conclusions per run,
  labeled by workflow and OS.
- A duration metric from merge timestamp to first failing check, for detection latency.
- A duration metric from incident issue `created_at` to rollback PR `merged_at`, for
  mitigation latency.

Until a backend is confirmed, these SLIs should be reviewed manually from GitHub Actions
run history and incident issue timelines.
