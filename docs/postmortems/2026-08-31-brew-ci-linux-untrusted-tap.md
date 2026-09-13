# Postmortem: `brew-ci.yml` Linux leg refuses to load any formula ("untrusted tap")

**Date of incident:** 2026-08-31 (root-cause escalation confirmed 2026-09-08)
**Date of postmortem:** 2026-09-13
**Authors:** operations (automated audit)
**Severity:** P2 — see [severity-levels.md](../severity-levels.md)

> **Status at time of writing: ONGOING, unresolved.** This postmortem is filed
> per the `docs/slo.md` / `docs/severity-levels.md` policy that any P1/P2
> incident — or any incident exceeding the 2-hour rollback SLO — gets a
> postmortem, regardless of whether mitigation has landed yet. See
> [#409](https://github.com/kubestellar/homebrew-tap/issues/409) (no incident
> issue or postmortem previously existed despite meeting this threshold) and
> [#373](https://github.com/kubestellar/homebrew-tap/issues/373) (root cause
> and escalation detail). The **Action Items** table below tracks what still
> needs to happen; this document should be updated in place once a fix lands
> and the incident is formally closed.

---

## Summary

Since the `main` run at `2026-08-31T19:03:03Z`, every `brew-ci.yml`
("Homebrew CI") run on `ubuntu-latest` — both on `main` and on pull requests —
fails during the `Set up Homebrew tap` step, before `brew audit --strict` or
any install/smoke-test step executes. The job's `macos-latest` leg is
unaffected and continues to pass. As of the most recent completed run
(`main`, 2026-09-13), the outage has lasted **13 consecutive days** with
**zero successful Linux CI runs**, far exceeding the 2-hour time-to-rollback
SLO defined in [`docs/slo.md`](../slo.md). No incident issue or postmortem
tracked this until the operations audit filed
[#409](https://github.com/kubestellar/homebrew-tap/issues/409) on 2026-09-12.

---

## Impact

- **Duration:** Ongoing since 2026-08-31T19:03:03Z (13+ days as of this writing); not yet resolved.
- **Affected formula(e):** `kubestellar-ops`, `kubestellar-deploy`, `kc-agent` (all three — the tap itself is refused, so every formula in it is affected)
- **Affected platforms:** Linux (amd64 and arm64 bottle tags), on both `ubuntu-latest` CI runners. macOS (`macos-latest`) CI is unaffected.
- **Users affected:** No confirmed end-user `brew install` breakage reported to date — the failure is in the CI job's own tap-registration step, not in the published bottles. However, CI on Linux has provided **zero validation signal** for `Formula/**` changes for the full duration, so a real Linux-targeting regression landing during this window would go undetected by CI.
- **Functionality lost:** All CI-based `brew audit --strict` / install / smoke-test coverage for `ubuntu-latest`, on both `main` and PR runs.

---

## Root Cause

Between the `2026-09-07T05:28Z` and `2026-09-08T05:20Z` daily scheduled runs,
the version of Homebrew installed by the pinned
`Homebrew/actions/setup-homebrew@3cdb78d` action (the action SHA is pinned,
but it always installs whatever the *current* Homebrew release is, so the
underlying Homebrew version drifts run-to-run) began enforcing a **tap-trust**
model. `brew-ci.yml`'s `Set up Homebrew tap` step registers this repo as a
local tap with `brew tap kubestellar/tap "$(pwd)"` (no `brew trust` call), and
newer Homebrew now refuses to load any formula from a tap registered this way:

```
==> Tapping kubestellar/tap
Cloning into '.../Taps/kubestellar/homebrew-tap'...
##[error]Invalid formula (golden_gate): .../Formula/kc-agent.rb
Refusing to load formula kubestellar/tap/kc-agent from untrusted tap kubestellar/tap.
Run `brew trust --formula kubestellar/tap/kc-agent` or `brew trust kubestellar/tap` to trust it.
```

This repeats for all three formulae, across every bottle tag (`golden_gate`,
`arm64_golden_gate`, `tahoe`, ...), and is a strict escalation of the
previously-tracked, cosmetic-only cleanup failure in
[#322](https://github.com/kubestellar/homebrew-tap/issues/322) (where audit/
install/test still passed and only a post-run `rm` cleanup step failed).
Since 2026-09-08, **no Linux step beyond tap registration runs at all**.

---

## Detection

Detected by the operations agent's recurring CI-health audit
([#373](https://github.com/kubestellar/homebrew-tap/issues/373), filed
2026-09-08, ~9 hours after the escalation window) via direct inspection of
`brew-ci.yml` run logs — not by an automated alert. **No workflow-level
alert exists** for `brew-ci.yml` failures on `main`
([#316](https://github.com/kubestellar/homebrew-tap/issues/316),
[#318](https://github.com/kubestellar/homebrew-tap/issues/318)), so detection
depended entirely on manual/agent audit rather than a page or issue-bot.
Time from root-cause escalation (`2026-09-08T05:20Z`) to first tracked report
(`2026-09-08T14:42Z`) was ~9.5 hours; time from the original first-red run
(`2026-08-31T19:03:03Z`) to any tracking issue was over a week.

---

## Response

- 2026-09-08: [#373](https://github.com/kubestellar/homebrew-tap/issues/373)
  filed identifying the escalation, root cause, and proposed fix (`brew trust`
  call, or an alternate tap-registration method compatible with current
  Homebrew).
- 2026-09-10: Re-verified still active and unaddressed (no `brew trust` call
  added), confirmed via a fresh run's full step log.
- 2026-09-12: [#409](https://github.com/kubestellar/homebrew-tap/issues/409)
  filed noting the incident had crossed the repo's own P1/P2 + >2h SLO
  threshold with no incident issue or postmortem on file.
- 2026-09-13: This postmortem filed to close that documentation gap. **No
  code fix has landed yet** — the fix itself is a change to
  `.github/workflows/brew-ci.yml`, which is out of reach for this agent (see
  [#373](https://github.com/kubestellar/homebrew-tap/issues/373) for the
  proposed replacement text) and requires a maintainer or an agent with
  `workflows` permission to apply and merge.
- No rollback per the [Formula Rollback Runbook](../../runbooks/formula-rollback.md)
  was applicable: the incident is a CI-infrastructure break, not a bad
  formula release, so there is nothing user-facing to roll back.

---

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 2026-08-31T05:29:36Z | Last known-good `brew-ci.yml` run on `main` (`ubuntu-latest` passing) |
| 2026-08-31T19:03:03Z | First failing `main` run in the current streak (initially the #322-class cleanup-only symptom) |
| 2026-09-07T05:28:11Z | Last run where audit/install/test steps still passed (only cleanup step red) |
| 2026-09-08T05:20:0xZ | First run with the new "untrusted tap" failure — `Set up Homebrew tap` step itself fails, no audit/install/test steps execute |
| 2026-09-08T14:42:31Z | [#373](https://github.com/kubestellar/homebrew-tap/issues/373) filed |
| 2026-09-10T~05:33Z | Re-verified still failing identically, no fix applied |
| 2026-09-12T05:33:49Z | [#409](https://github.com/kubestellar/homebrew-tap/issues/409) filed (SLO/incident-tracking gap) |
| 2026-09-13T~05:18Z | Latest confirmed failing run at time of writing; `macos-latest` leg still green |
| — | **Not yet resolved.** |

---

## What Went Well

- The `macos-latest` leg of `brew-ci.yml` continued providing partial CI
  signal throughout, so formula changes were not entirely unvalidated.
- Once flagged, the root cause was identified precisely (exact failing step,
  exact underlying Homebrew behavior change) from run logs alone, without
  needing to reproduce locally.

---

## What Went Poorly

- No automated alert exists for `brew-ci.yml` failures on `main`
  ([#316](https://github.com/kubestellar/homebrew-tap/issues/316)/[#318](https://github.com/kubestellar/homebrew-tap/issues/318)),
  so a full week passed between the first red run and any tracking issue, and
  the more severe escalation on 2026-09-08 still relied on manual/agent audit
  for detection rather than a page.
- Because the failing action (`setup-homebrew@3cdb78d`) is pinned by SHA but
  installs an unpinned, always-current Homebrew release, the workflow's
  behavior changed underneath a supposedly-stable pin with no warning.
- No incident issue or postmortem was opened for 13+ days despite clearly
  exceeding the repo's own P2 severity + 2-hour SLO thresholds — this
  postmortem is the first artifact tracking the incident as an incident
  rather than as a bare CI-health issue.

---

## Where We Got Lucky

- The break is in CI's own tap-registration mechanism, not in a published
  formula or bottle — no evidence to date of an actual broken end-user
  `brew install`/`brew upgrade` during this window.

---

## Action Items

| Action | Type | Owner | Due | Issue |
|--------|------|-------|-----|-------|
| Add `brew trust kubestellar/tap` (or equivalent) to `brew-ci.yml`'s `Set up Homebrew tap` step so `ubuntu-latest` CI resumes validating formulae | mitigate | maintainer / `workflows`-permission agent | ASAP — 13+ days past SLO | [#373](https://github.com/kubestellar/homebrew-tap/issues/373) |
| Add a scheduled/`workflow_run` failure alert for `brew-ci.yml` and `validate-formulae.yml` on `main` so future breaks are detected without manual audit | detect | maintainer / `workflows`-permission agent | — | [#316](https://github.com/kubestellar/homebrew-tap/issues/316), [#318](https://github.com/kubestellar/homebrew-tap/issues/318) |
| Pin the Homebrew version installed by `setup-homebrew`, or add a smoke check that fails loudly (rather than silently degrading) if tap-registration behavior changes | prevent | maintainer | — | [#373](https://github.com/kubestellar/homebrew-tap/issues/373) |
| Once the fix lands, update this postmortem's Status/Timeline/Impact with the resolution time and close [#409](https://github.com/kubestellar/homebrew-tap/issues/409) | process | maintainer | after fix merges | [#409](https://github.com/kubestellar/homebrew-tap/issues/409) |
