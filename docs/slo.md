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
and `Stale Issues`. The structured per-run summary lines described below are
now applied for all three of `brew-ci.yml`, `fuzz.yml`, and
`validate-formulae.yml` (see [#479](https://github.com/kubestellar/homebrew-tap/pull/479)).
The one remaining gap is a missing `schedule:` trigger on
`validate-formulae.yml` (`brew-ci.yml` and `fuzz.yml` already have one),
which still requires a maintainer with `workflows` permission to apply.

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
- **Formula CI health on `ubuntu-latest` is resolved, not currently 0%:** the
  `brew-ci.yml` "untrusted tap" Linux outage described here previously
  ([#373](https://github.com/kubestellar/homebrew-tap/issues/373), escalating
  [#322](https://github.com/kubestellar/homebrew-tap/issues/322)) was fixed by
  [#487](https://github.com/kubestellar/homebrew-tap/pull/487) and confirmed
  green through [#490](https://github.com/kubestellar/homebrew-tap/pull/490)
  (both `ubuntu-latest` and `macos-latest` legs green on `main`). All three
  referenced issues are closed.
- **Formula drift health** currently only gets a data point when a
  `Formula/**` (or related-path) change triggers `validate-formulae.yml` on
  `main`. `brew-ci.yml` closed this gap for itself with a daily `schedule:`
  trigger (`17 6 * * *`, added in
  [#464](https://github.com/kubestellar/homebrew-tap/pull/464), closing
  [#318](https://github.com/kubestellar/homebrew-tap/issues/318)), but
  `validate-formulae.yml` still has none, so a break with **no matching
  Formula diff** — e.g. an upstream
  [`kubestellar-mcp`](https://github.com/kubestellar/kubestellar-mcp) release
  being deleted/re-tagged/pruned, a transient CDN/host 404 on the pinned
  release URL, or a yanked binary after its `sha256` was already pinned — can
  still go undetected indefinitely between merges for the drift-check side,
  with the ≤15-minute detection SLO below having no mechanism behind it for
  this failure class on `validate-formulae.yml`. **Recommendation:** add a
  daily `schedule:` trigger to `validate-formulae.yml`, mirroring
  `brew-ci.yml`'s and `fuzz.yml`'s existing cadence, so the tap's live
  installability is re-verified on the drift-check side too, not only on a
  Formula push.
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
  **This budget was missed:** the `brew-ci.yml`
  Linux "untrusted tap" outage (see above, and
  [#373](https://github.com/kubestellar/homebrew-tap/issues/373)) ran
  ~16.6 days past this 2-hour threshold — no incident issue or postmortem
  was filed until
  [`docs/postmortems/2026-08-31-brew-ci-linux-untrusted-tap.md`](postmortems/2026-08-31-brew-ci-linux-untrusted-tap.md)
  ([#409](https://github.com/kubestellar/homebrew-tap/issues/409)) — but the
  outage itself is now resolved as of
  [PR #487](https://github.com/kubestellar/homebrew-tap/pull/487) (both
  `ubuntu-latest` and `macos-latest` green on `main` as of
  [run 35210250200](https://github.com/kubestellar/homebrew-tap/actions/runs/35210250200)).
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
- **Formula CI health** now has a grep-able, structured per-run outcome
  record: `brew-ci.yml`'s "Emit CI-observability summary" step (`if:
  always()`) runs `scripts/brew_ci_summary.sh` and emits a bounded
  `BREW_CI_SUMMARY:` line (job status, OS, formula counts — no exporter, no
  external data flow) per matrix OS, matching `validate_formulae.py`'s
  `VALIDATE_FORMULAE_SUMMARY:` and `verify_release_health.sh`'s
  `VERIFY_RELEASE_HEALTH_SUMMARY:`. This was applied in
  [#479](https://github.com/kubestellar/homebrew-tap/pull/479), closing the
  `workflows` permission gap previously tracked here and in
  [#425](https://github.com/kubestellar/homebrew-tap/issues/425).
- **Formula fuzz health** has the matching structured-summary record:
  `fuzz.yml`'s "Emit CI-observability summary" step (`if: always()`, so it
  now runs even when an earlier step in the job fails) runs
  `scripts/fuzz_summary.sh` (tested in `scripts/test_fuzz_summary.sh`) and
  emits a bounded `FUZZ_SUMMARY:` line (job status and formula count — no
  exporter, no external data flow), replacing the old fixed free-text
  "Fuzzing summary" step. This was applied in
  [#479](https://github.com/kubestellar/homebrew-tap/pull/479), closing the
  gap previously tracked in
  [#413](https://github.com/kubestellar/homebrew-tap/issues/413).
- **Formula drift health** has the matching structured-summary record for
  its unit-test step: `validate-formulae.yml`'s "Run all scripts/test_\*.py
  unit tests" step now delegates to `scripts/unittest_summary.sh` (tested in
  `scripts/test_unittest_summary.sh`), which emits a bounded
  `UNITTEST_SUMMARY:` line (status/counts only — no exporter, no external
  data flow) while preserving the full verbose `unittest` output, and
  distinguishes the "no tests ran" outcome (`unittest` exit code 5) from an
  undifferentiated non-zero exit — closing the silent-skip failure class
  tracked in #268. This was applied in
  [#479](https://github.com/kubestellar/homebrew-tap/pull/479), closing the
  gap previously tracked in
  [#425](https://github.com/kubestellar/homebrew-tap/issues/425).

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
