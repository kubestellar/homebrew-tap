# SLOs / SLIs — kubestellar/homebrew-tap

This tap has no runtime backend of its own — it ships Homebrew formulae
(`kubestellar-ops`, `kubestellar-deploy`, `kc-agent`) that resolve, at
`brew install`/`brew upgrade` time, to release artifacts published by the
upstream [`kubestellar-mcp`](https://github.com/kubestellar/kubestellar-mcp)
repository. Because `main` is served live to every `brew install` the moment a
formula change merges, CI health on `main` is the primary user-facing signal
for this repo. No exporter, metrics backend, or external data flow is added by
this document — it defines SLIs derived from existing GitHub Actions checks
and recommends how to interpret them operationally. It also links the active
`workflow_run`-based alert
([`.github/workflows/scheduled-workflow-failure-issue.yml`](../.github/workflows/scheduled-workflow-failure-issue.yml),
applied in #441; see the
[Scheduled Workflow Failure Runbook](../runbooks/scheduled-workflow-failure.md))
that closes most of the alert gaps described below — it watches `CodeQL
Analysis`, `OpenSSF Scorecard`, `Fuzzing`, `Homebrew CI`, `Validate Formulae`,
and `Stale Issues`. The remaining gaps (missing `schedule:` triggers on
`brew-ci.yml`/`validate-formulae.yml`/`fuzz.yml`, and the structured
per-run summary lines below) still require a maintainer with `workflows`
permission to apply.

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
| **Stale-triage health** | Fraction of scheduled `Stale Issues` (`stale.yml`, daily `0 0 * * *`) runs that complete successfully | [stale.yml](../.github/workflows/stale.yml) run history |

## SLOs (Service Level Objectives)

- **Formula CI health ≥ 99%** measured over a rolling 30-day window of merges to `main`.
  A red `main` check on `brew-ci.yml` or `validate-formulae.yml` means the next
  `brew install`/`brew upgrade` for at least one formula is very likely broken for
  end users — treat every `main` failure as a candidate incident, not routine noise.
- **Formula CI health is currently 0% on `ubuntu-latest`, not just red-but-informative:**
  as of the `2026-09-12` daily run window (45 consecutive failing `main` runs
  since the last success on `2026-08-31T05:29:36Z`, ~12 days), `brew-ci.yml`'s
  `Set up Homebrew tap` step itself fails ("`Refusing to load formula ... from
  untrusted tap`") before `brew audit --strict`/install/test ever execute, on
  both `main` and pull request runs — see
  [#373](https://github.com/kubestellar/homebrew-tap/issues/373).
  This is a more severe escalation of the cleanup-only symptom tracked in
  [#322](https://github.com/kubestellar/homebrew-tap/issues/322): today there is
  **no automated Linux signal at all** for `Formula/**` changes, so a real
  regression landing right now would only be caught by the `macos-latest` leg
  of the same job or by a user report. Treat this as blocking the ≤15-minute
  detection SLO below until a maintainer applies the `brew trust` fix proposed
  in #373 (requires `workflows` permission this agent's credentials lack).
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
  is reported. An automated `workflow_run`-triggered job that files a
  `kind/bug` tracking issue on a `Homebrew CI`/`Validate Formulae` `main`
  failure (linking this doc and the
  [Scheduled Workflow Failure Runbook](../runbooks/scheduled-workflow-failure.md))
  is now active at
  [`.github/workflows/scheduled-workflow-failure-issue.yml`](../.github/workflows/scheduled-workflow-failure-issue.yml)
  (applied in #441, closing the gap previously tracked in
  [#316](https://github.com/kubestellar/homebrew-tap/issues/316)).
- **This detection window does not include a pre-merge gate for most
  `Formula/**` changes.** `goreleaserbot` pushes formula updates directly to
  `main` on every upstream release, with no associated PR or review (see
  [#414](https://github.com/kubestellar/homebrew-tap/issues/414), which also
  flags that this contradicts `.github/branch-protection-policy.md`'s stated
  "only maintainers via PR merge" rule). `brew-ci.yml`'s `on: push` run for
  that commit is the first automated check it receives, and it runs *after*
  the change is already live to `brew install`/`brew upgrade` — so "Time to
  detect a broken release" for these bot commits starts from an
  already-user-facing state, not from a review gate, and has zero signal at
  all on whichever platform `brew-ci.yml` itself is currently degraded on
  (see the Linux outage in [#409](https://github.com/kubestellar/homebrew-tap/issues/409)).
- **Time to rollback/mitigate ≤ 2 hours** for a confirmed broken release, using the
  [Formula Rollback Runbook](../runbooks/formula-rollback.md). Incidents exceeding
  this budget, or affecting more than a handful of users, should get a
  [postmortem](postmortem-template.md). See
  [`docs/severity-levels.md`](severity-levels.md) for how this budget maps to
  the P1–P4 severity field on the [incident](../.github/ISSUE_TEMPLATE/incident.md)
  and [postmortem](postmortem-template.md) templates.
  **This budget is currently being missed:** the ongoing `brew-ci.yml`
  Linux "untrusted tap" outage (see above, and
  [#373](https://github.com/kubestellar/homebrew-tap/issues/373)) has run
  13+ days past this 2-hour threshold with no incident issue or postmortem
  filed until
  [`docs/postmortems/2026-08-31-brew-ci-linux-untrusted-tap.md`](postmortems/2026-08-31-brew-ci-linux-untrusted-tap.md)
  ([#409](https://github.com/kubestellar/homebrew-tap/issues/409)).
- **Weekly security-scan health ≥ 99%** for the scheduled `CodeQL Analysis` and
  `Scorecard analysis` runs. Both already run on a weekly `schedule:` trigger,
  and — unlike when this gap was first tracked in
  [#337](https://github.com/kubestellar/homebrew-tap/issues/337) — an
  automated alert now fires if a scheduled run itself fails to complete (as
  opposed to reporting findings), via
  [`.github/workflows/scheduled-workflow-failure-issue.yml`](../.github/workflows/scheduled-workflow-failure-issue.yml)
  (applied in #441; also watches `Fuzzing`, `Homebrew CI`, `Validate
  Formulae`, and `Stale Issues` — see the
  [Scheduled Workflow Failure Runbook](../runbooks/scheduled-workflow-failure.md)).
- **Weekly security-scan health for `Scorecard analysis` was 0% between
  `2026-09-10T05:33:06Z` and 2026-09-17**, not just unalerted: every
  `scorecard.yml` run in that window failed at the `Pull
  gcr.io/openssf/scorecard-action:v2.4.0` step, before checkout or analysis
  ever ran, with `denied: This API method requires billing to be enabled`
  — Google's deprecation of legacy `gcr.io` image hosting, not a
  KubeStellar-side regression. `CodeQL Analysis` was unaffected. The fix
  (pulling the GHCR-mirrored image) landed in the pinned reusable workflow
  `kubestellar/infra/.github/workflows/reusable-scorecard.yml`, which this
  repo now consumes via an updated pin
  (`cfe3dcacb317e67ccf3701c98bc0416a7712cfbf`); `scorecard.yml` runs on
  `main` have been green since the pin bump — see
  [#417](https://github.com/kubestellar/homebrew-tap/issues/417) for the
  failing-run evidence and fix confirmation.
- **Formula fuzz health ≥ 99%**, and detection latency for a fuzz regression should
  match the ≤ 15 minute target above. `fuzz.yml` now has a weekly `schedule:`
  trigger (`0 8 * * 1`, offset from `codeql.yml`'s `0 4 * * 1` and
  `scorecard.yml`'s `0 6 * * 1`), closing the gap tracked in
  [#337](https://github.com/kubestellar/homebrew-tap/issues/337) where nothing
  re-validated formula syntax, structure, or URL/checksum format between
  `Formula/**` diffs.
  [`.github/workflows/scheduled-workflow-failure-issue.yml`](../.github/workflows/scheduled-workflow-failure-issue.yml)
  already watches `Fuzzing` for failed runs, so the existing alert now has a
  scheduled run to watch.
- **Stale-triage health ≥ 99%** for the scheduled `Stale Issues` run. Like the
  security scans above, `stale.yml` already runs on a daily `schedule:`
  trigger, and an automated alert now fires if the scheduled run itself fails
  (infra/runner failure, reusable-workflow breakage, permissions regression)
  via
  [`.github/workflows/scheduled-workflow-failure-issue.yml`](../.github/workflows/scheduled-workflow-failure-issue.yml)
  (applied in #441, closing the gap previously tracked in
  [#365](https://github.com/kubestellar/homebrew-tap/issues/365)).
- **Formula CI health** is the one SLI above without a grep-able, structured
  per-run outcome record in the CI log itself: `validate-formulae.yml`'s
  `validate_formulae.py` already emits a `VALIDATE_FORMULAE_SUMMARY:` JSON
  line, and `verify_release_health.sh` emits `VERIFY_RELEASE_HEALTH_SUMMARY:`,
  but `brew-ci.yml` only prints free-text `::group::` blocks, so a reader has
  to scroll them to see whether/why a given OS's run passed.
  **Recommendation:** apply the ready-to-apply step in
  [`runbooks/proposed-brew-ci-observability-summary-step.yml`](../runbooks/proposed-brew-ci-observability-summary-step.yml),
  which adds a matching `BREW_CI_SUMMARY:` line (bounded to job status, OS,
  and formula counts — no exporter, no external data flow). Applying it
  requires the same `workflows` permission gap noted for the scheduled-failure
  alert above.
- **Formula fuzz health** has the same structured-summary gap as `brew-ci.yml`
  above: `fuzz.yml`'s final "Fuzzing summary" step only echoes fixed free text
  ("Fuzzing completed successfully!" plus a checklist), with no grep-able
  outcome record, and — unlike the free text — it has no `if: always()` guard,
  so it does not even run when an earlier step in the job fails.
  **Recommendation:** apply the ready-to-apply step in
  [`runbooks/proposed-fuzz-observability-summary-step.yml`](../runbooks/proposed-fuzz-observability-summary-step.yml),
  which adds a matching `FUZZ_SUMMARY:` line (bounded to job status and
  formula count — no exporter, no external data flow) and always runs.
  `scripts/fuzz_summary.sh` (tested in `scripts/test_fuzz_summary.sh`)
  already implements and tests this logic. Applying it requires the same
  `workflows` permission gap noted above.
- **Formula drift health** has the same structured-summary gap for its
  unit-test step specifically: `validate-formulae.yml`'s "Run all
  scripts/test_\*.py unit tests" step runs `unittest discover` directly, so
  the only pass/fail record is unittest's own free-text `OK` / `FAILED
  (failures=N, errors=M)` tail line — unlike the drift-check script in the
  very same job, which already emits `VALIDATE_FORMULAE_SUMMARY:`. This also
  silently folds the distinct "no tests ran" outcome (unittest exit code 5)
  into an undifferentiated non-zero exit, the same silent-skip failure class
  as #268. **Recommendation:** apply the ready-to-apply step in
  [`runbooks/proposed-validate-formulae-unittest-summary-step.yml`](../runbooks/proposed-validate-formulae-unittest-summary-step.yml),
  which adds a matching `UNITTEST_SUMMARY:` line (bounded to status/counts —
  no exporter, no external data flow) while preserving the full verbose
  unittest output unchanged. `scripts/unittest_summary.sh` (tested in
  `scripts/test_unittest_summary.sh`) already implements and tests this
  logic. Applying it requires the same `workflows` permission gap noted
  above.

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
