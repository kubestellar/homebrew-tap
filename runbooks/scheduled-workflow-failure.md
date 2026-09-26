# Scheduled Workflow Failure Runbook

**Repository:** `kubestellar/homebrew-tap`
**Applies to:** `CodeQL Analysis`, `OpenSSF Scorecard`, `Fuzzing`, `Homebrew CI`, `Validate Formulae`, `Stale Issues`
**Known gap:** `actionlint` also runs on a weekly `schedule:` but is not yet
watched by this alert — a failed scheduled `actionlint` run currently has no
automated notification; see [#549](https://github.com/kubestellar/homebrew-tap/issues/549)
for the ready-to-apply fix.

---

## When to Use This Runbook

Use this runbook when you are assigned, or notice, an auto-filed issue
titled `Workflow failure: <workflow name>` and labeled `workflow-failure`.
These issues are created by
[`.github/workflows/scheduled-workflow-failure-issue.yml`](../.github/workflows/scheduled-workflow-failure-issue.yml)
(applied in #441) whenever:

- A scheduled (`cron`) or manually (`workflow_dispatch`) triggered run of
  `CodeQL Analysis`, `OpenSSF Scorecard`, `Fuzzing`, or `Stale Issues` fails, or
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
   - **Known recurring signature** — check the
     [Known Recurring Failure Signatures](#known-recurring-failure-signatures)
     table below before investigating from scratch.
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
6. For `Stale Issues` failures, this is an infra/permissions/reusable-workflow
   break in the stale-triage automation itself (see
   [#365](https://github.com/kubestellar/homebrew-tap/issues/365)), not a
   formula or code regression — issues/PRs due for stale-marking or
   auto-closing per policy simply won't be, with no other signal until this
   alert fires. Fix the workflow/permissions issue and re-run.

## Known Recurring Failure Signatures

These `Homebrew CI` failures have a confirmed root cause and a known outcome —
check here before re-investigating from scratch.

| Signature | Root cause | Expected outcome |
|-----------|------------|-------------------|
| `brew audit --strict` fails on exactly one formula with `` Stable: `version X.Y.Z` is redundant with version scanned from URL `` (no other finding) | `goreleaserbot`'s formula-bump commits always emit an explicit `version "X.Y.Z"` line. Homebrew's `redundant_version` strict-audit rule flags this whenever the tag is a plain semver (a stable release, e.g. `v0.9.15`) because the version is then also inferable from the download URL. It does **not** fire for nightly tags (e.g. `v0.9.15-nightly.20260920`), whose suffix isn't trivially URL-inferable — so this is specific to stable-version bump commits, confirmed recurring at [#426](https://github.com/kubestellar/homebrew-tap/issues/426) (`kc-agent` v0.3.41, 2026-09-13) and [#511](https://github.com/kubestellar/homebrew-tap/issues/511) (`kubestellar-deploy`, v0.9.15, 2026-09-20). | `brew audit --strict` is a lint, not an install check — `brew install`/`brew upgrade` are unaffected. In every observed case, main went green again within minutes once the next commit (usually a same-day nightly bump) superseded the flagged stable-version commit. **Confirm `main`'s current `Homebrew CI` run is green before closing** the auto-filed issue as resolved-by-supersession; do not treat it as a live incident once confirmed. A permanent fix (accepting this specific audit finding as non-fatal in `scripts/brew_audit_all.sh`) is out of `operations`' scope — filed for `quality`/`ci-maintainer` or a maintainer to pick up. |
| `Validate Formulae` → `unit tests + drift check` fails only `test_formula_test_block_readonly_invariants...test_test_block_chains_at_least_two_readonly_system_calls` for `kubestellar-deploy` and/or `kubestellar-ops` with `test do body has 1 read-only ... invocations, want at least 2` | `goreleaserbot`'s nightly formula-bump commits regenerate the whole `.rb` from the `brews[].test` template in [kubestellar-mcp `.goreleaser.yaml`](https://github.com/kubestellar/kubestellar-mcp/blob/main/.goreleaser.yaml), which only emits `system bin/"<tool>", "version"`. Every in-tap re-add of the second `--help` call ([#532](https://github.com/kubestellar/homebrew-tap/pull/532), [#556](https://github.com/kubestellar/homebrew-tap/pull/556), [#564](https://github.com/kubestellar/homebrew-tap/pull/564), [#572](https://github.com/kubestellar/homebrew-tap/issues/572)) is therefore wiped by the next bump. | Re-adding `system bin/"<tool>", "--help"` after the `version` line turns `main` green immediately, but only the upstream template fix is durable: the `brews[].test` block in kubestellar-mcp must chain both calls. Do **not** weaken the invariant in `scripts/test_formula_test_block_readonly_invariants.py`. |

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
  `CodeQL Analysis`, `OpenSSF Scorecard`, `Fuzzing`, `Stale Issues`) or
  `main`-branch runs (for `Homebrew CI`, `Validate Formulae`) — pull-request
  failures are already visible via the PR's own status checks and do not need
  a duplicate issue.
- No runtime backend or metrics exporter is added by this mechanism; it is a
  GitHub Actions `workflow_run` → `gh issue create`/`comment` job only, per the
  no-backend-configured scope of this repository (see `docs/slo.md`).
