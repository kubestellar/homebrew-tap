# Postmortem: `brew-ci.yml` Linux leg refuses to load any formula ("untrusted tap")

**Date of incident:** 2026-08-31 (root-cause escalation confirmed 2026-09-08)
**Date of postmortem:** 2026-09-13 (last updated 2026-09-14)
**Authors:** operations (automated audit)
**Severity:** P2 — see [severity-levels.md](../severity-levels.md)

> **Status: RESOLVED (updated 2026-09-17).** Both `ubuntu-latest` and
> `macos-latest` legs of `brew-ci.yml` are green again as of the `main` run
> [35210250200](https://github.com/kubestellar/homebrew-tap/actions/runs/35210250200)
> (`102387b`, 2026-09-17T10:23:45Z). The path to resolution went through
> several intermediate mitigations, each of which changed the failure
> signature without fully restoring signal (see "Response" and "Timeline"
> below): [#422](https://github.com/kubestellar/homebrew-tap/pull/422) fixed
> the "untrusted tap" symptom but introduced a Linux formula-resolution
> failure and an unrelated macOS `brew audit --strict` regression
> ([#426](https://github.com/kubestellar/homebrew-tap/issues/426)); a
> follow-up fix restored `ubuntu-latest` audit/install/test signal but then
> hit a `setup-homebrew` post-cleanup `rm` error again
> ([#486](https://github.com/kubestellar/homebrew-tap/issues/486)), which was
> finally resolved by
> [PR #487](https://github.com/kubestellar/homebrew-tap/pull/487) (recreating
> the tap symlink `setup-homebrew` expects before its post-cleanup step
> runs). From first red run (`2026-08-31T19:03:03Z`) to confirmed green on
> both legs (`2026-09-17T10:23:45Z`), total outage duration was **~16.6
> days**, far exceeding the `docs/slo.md` 2-hour time-to-rollback SLO. This
> postmortem is filed per the `docs/slo.md` / `docs/severity-levels.md`
> policy that any P1/P2 incident — or any incident exceeding the 2-hour
> rollback SLO — gets a postmortem. See
> [#409](https://github.com/kubestellar/homebrew-tap/issues/409) (no incident
> issue or postmortem previously existed despite meeting this threshold) and
> [#373](https://github.com/kubestellar/homebrew-tap/issues/373) (root cause
> and escalation detail). The **Action Items** table below tracks remaining
> follow-up work (notably: no automated alert on `brew-ci.yml` failure yet
> exists, per #316/#318, and no `[incident]`-template issue was ever filed for
> this outage, per #409).

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

- **Duration:** 2026-08-31T19:03:03Z → 2026-09-17T10:23:45Z (~16.6 days total, resolved by [PR #487](https://github.com/kubestellar/homebrew-tap/pull/487)). The macOS leg's 2026-09-13T22:16Z regression lasted under 8 hours before incidentally clearing at 2026-09-14T05:29Z (see Status above), but the underlying `brew audit --strict` finding that caused it was never fixed and can recur.
- **Affected formula(e):** `kubestellar-ops`, `kubestellar-deploy`, `kc-agent` (all three — the tap itself is refused, so every formula in it is affected)
- **Affected platforms:** Linux (amd64 and arm64 bottle tags) remains fully broken on `ubuntu-latest`. macOS (`macos-latest`) CI is green again as of 2026-09-14T05:29:14Z, but that is incidental (see Status) rather than a durable fix.
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
- 2026-09-13: This postmortem filed to close that documentation gap. At the
  time of filing, no code fix had landed yet.
- 2026-09-13 (later): [#422](https://github.com/kubestellar/homebrew-tap/pull/422)
  merged a `brew trust kubestellar/tap` mitigation for the "untrusted tap"
  symptom. Its own pre-merge checks were still failing on **both** legs
  ([run 34786285984](https://github.com/kubestellar/homebrew-tap/actions/runs/34786285984))
  — this repo's branch-protection policy intentionally does not require
  status checks to merge (`required_status_checks: null` in
  [`branch-protection-policy.md`](../../.github/branch-protection-policy.md)),
  so this was not a policy violation, but it did mean the merge went in
  without a green signal. The first `main` run after merge
  ([run 34786304650](https://github.com/kubestellar/homebrew-tap/actions/runs/34786304650),
  `9c97b0a`) confirmed the "untrusted tap" step itself is fixed, but **both
  legs still fail with new, different signatures**: `ubuntu-latest` now fails
  at the audit step itself with `No available formula or cask with the name
  "kubestellar/tap/kc-agent"`, and `macos-latest` — previously green
  throughout this entire incident — is now newly red on a real `brew audit
  --strict` finding on `kc-agent.rb` (`Stable: version 0.3.41 is redundant
  with version scanned from URL`), unrelated to the tap-trust root cause.
  **Net effect: Linux CI health is still 0%, and macOS CI health, previously
  100% throughout this incident, is now also 0%.** The fix changed the
  failure mode without restoring signal on either OS.
- 2026-09-14: The routine formula-bump bot rolled `Formula/kc-agent.rb`'s
  `version` to `0.3.42-nightly.20260914`
  ([run 34809809175](https://github.com/kubestellar/homebrew-tap/actions/runs/34809809175),
  `36a4b9f`), and `macos-latest` returned to green. This is **not** a fix for
  the underlying audit finding — `brew audit --strict`'s "version is
  redundant with version scanned from URL" check does not fire on
  `-nightly.*` suffixed versions, only on plain semantic-version strings. The
  same run's `ubuntu-latest` leg is still red with the identical
  `No available formula or cask with the name "kubestellar/tap/kc-agent"`
  failure from the prior run, confirming the Linux formula-resolution
  regression from #422 remains unaddressed.
- Follow-up fixes restored `ubuntu-latest` audit/install/test signal after
  #422/#426, but the job then hit a `setup-homebrew` post-cleanup `rm` error
  again ([#486](https://github.com/kubestellar/homebrew-tap/issues/486), run
  [35204585729](https://github.com/kubestellar/homebrew-tap/actions/runs/35204585729)):
  the "Untap self before post-cleanup" step added to fix #426 deleted the tap
  path outright, leaving nothing for `setup-homebrew`'s own post-cleanup
  `rm` to remove, so the job failed on "No such file or directory" instead.
- 2026-09-17: [PR #487](https://github.com/kubestellar/homebrew-tap/pull/487)
  merged, recreating the tap symlink `setup-homebrew` originally created
  (instead of leaving the path empty after untapping) so its post-cleanup
  step succeeds. The first `main` run after merge
  ([run 35210250200](https://github.com/kubestellar/homebrew-tap/actions/runs/35210250200),
  `102387b`, 2026-09-17T10:23:45Z) is **green on both `ubuntu-latest` and
  `macos-latest`**, resolving the incident.
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
| 2026-09-13T~05:18Z | Last confirmed "untrusted tap" failure before the #422 fix; `macos-latest` leg still green |
| 2026-09-13T~22:16Z | [#422](https://github.com/kubestellar/homebrew-tap/pull/422) merged (`brew trust` mitigation), despite pre-merge checks failing on both legs |
| 2026-09-13T22:16:35Z | First post-merge `main` run ([34786304650](https://github.com/kubestellar/homebrew-tap/actions/runs/34786304650), `9c97b0a`): "untrusted tap" resolved, but `ubuntu-latest` now fails with `No available formula or cask with the name "kubestellar/tap/kc-agent"`, and `macos-latest` is newly red on an unrelated `brew audit --strict` finding in `kc-agent.rb` |
| 2026-09-14T05:29:14Z | `main` run ([34809809175](https://github.com/kubestellar/homebrew-tap/actions/runs/34809809175), `36a4b9f`): `macos-latest` returns to green — incidentally, because the routine formula-bump bot rolled `kc-agent.rb`'s `version` to a `-nightly.*` suffix that no longer trips the redundant-version audit rule, not because the finding was fixed. `ubuntu-latest` still red with the same formula-resolution failure. |
| 2026-09-17T09:20:33Z | `main` run ([35204585729](https://github.com/kubestellar/homebrew-tap/actions/runs/35204585729)): `ubuntu-latest` fails again, this time on `setup-homebrew` post-cleanup ("No such file or directory") after the #426 fix's untap step left the tap path empty ([#486](https://github.com/kubestellar/homebrew-tap/issues/486)) |
| 2026-09-17T10:22Z | [PR #487](https://github.com/kubestellar/homebrew-tap/pull/487) merged: recreates the tap symlink before `setup-homebrew`'s post-cleanup step runs |
| 2026-09-17T10:23:45Z | `main` run ([35210250200](https://github.com/kubestellar/homebrew-tap/actions/runs/35210250200), `102387b`): **both `ubuntu-latest` and `macos-latest` green — incident resolved** |
| — | **Resolved.** Total outage duration ~16.6 days (2026-08-31T19:03Z → 2026-09-17T10:23Z). Remaining follow-ups: add automated alerting for `brew-ci.yml` failures on `main` (#316/#318), and decide whether a backdated `[incident]`-template issue should still be filed (#409). |

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
- A mitigation PR ([#422](https://github.com/kubestellar/homebrew-tap/pull/422))
  was merged with both CI legs still failing at merge time, and turned out not
  to restore green CI on either OS — it fixed the tap-trust symptom but
  surfaced two further, previously-masked problems (a formula-resolution
  failure on Linux, and a real audit finding on macOS that had never been
  reached before because the tap-trust failure short-circuited the job
  earlier). Because no automated alert exists on `main` CI failures
  ([#316](https://github.com/kubestellar/homebrew-tap/issues/316)/[#318](https://github.com/kubestellar/homebrew-tap/issues/318)),
  this regression would again depend on manual/agent audit to notice.

---

## Where We Got Lucky

- The break is in CI's own tap-registration mechanism, not in a published
  formula or bottle — no evidence to date of an actual broken end-user
  `brew install`/`brew upgrade` during this window.
- The `macos-latest` leg's redundant-version audit finding happened to clear
  on its own once the next formula bump produced a `-nightly.*` version
  string — this is not a fix and gives no guarantee against the next plain
  release version re-triggering the same finding, but it means the leg is
  not blocked *right now* while the real fix is still pending.

---

## Action Items

| Action | Type | Owner | Due | Issue |
|--------|------|-------|-----|-------|
| ~~Fix Linux formula resolution (`No available formula or cask with the name "kubestellar/tap/kc-agent"`) surfaced after the #422 tap-trust fix~~ | mitigate | maintainer / `workflows`-permission agent | Done | [#426](https://github.com/kubestellar/homebrew-tap/issues/426) |
| ~~Fix `setup-homebrew` post-cleanup `rm` failure introduced by the #426 untap fix~~ | mitigate | maintainer / `workflows`-permission agent | Done — [PR #487](https://github.com/kubestellar/homebrew-tap/pull/487) | [#486](https://github.com/kubestellar/homebrew-tap/issues/486) |
| Fix the `kc-agent.rb` `brew audit --strict` finding (`Stable: version is redundant with version scanned from URL`) so it doesn't resurface on the next plain (non-nightly) version bump — currently masked, not fixed, by an incidental `-nightly.*` version string | mitigate | maintainer / formula owner | Before the next plain-version bump of `kc-agent.rb` | [#426](https://github.com/kubestellar/homebrew-tap/issues/426) |
| Add a scheduled/`workflow_run` failure alert for `brew-ci.yml` and `validate-formulae.yml` on `main` so future breaks are detected without manual audit | detect | maintainer / `workflows`-permission agent | — | [#316](https://github.com/kubestellar/homebrew-tap/issues/316), [#318](https://github.com/kubestellar/homebrew-tap/issues/318) |
| Decide whether a backdated `[incident]`-template issue (per `.github/ISSUE_TEMPLATE/incident.md`) should still be filed for this now-resolved outage | process | maintainer | — | [#409](https://github.com/kubestellar/homebrew-tap/issues/409) |
| Pin the Homebrew version installed by `setup-homebrew`, or add a smoke check that fails loudly (rather than silently degrading) if tap-registration behavior changes | prevent | maintainer | — | [#373](https://github.com/kubestellar/homebrew-tap/issues/373) |
| Once the Linux leg is green and the `kc-agent.rb` audit finding is durably fixed (not just masked by version format), update this postmortem's Status/Timeline/Impact with the resolution time and close [#409](https://github.com/kubestellar/homebrew-tap/issues/409) | process | maintainer | after fix merges | [#409](https://github.com/kubestellar/homebrew-tap/issues/409) |
