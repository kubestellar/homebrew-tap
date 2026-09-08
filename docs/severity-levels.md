# Incident Severity Levels

This defines the P1–P4 scale referenced by the
[Incident Report template](../.github/ISSUE_TEMPLATE/incident.md) and the
[Postmortem template](postmortem-template.md), anchored to the SLOs in
[`docs/slo.md`](slo.md) and the
[Formula Rollback Runbook](../runbooks/formula-rollback.md). Pick the
**highest** level that any criterion below applies to.

| Level | Criteria | Response expectation |
|-------|----------|----------------------|
| **P1** | `brew install`/`brew upgrade` broken for **all** platforms (macOS + Linux, amd64 + arm64) for **any** formula, or a security vulnerability in a released binary | Begin rollback immediately per the [Formula Rollback Runbook](../runbooks/formula-rollback.md); target the SLO's **≤ 2 hour** time-to-rollback budget |
| **P2** | `brew install`/`brew upgrade` broken for **one or more, but not all,** platform/arch combinations for a formula, or affects more than a handful of users | Rollback/mitigate within the same **≤ 2 hour** SLO budget as P1 |
| **P3** | A formula installs but a **non-critical** feature is degraded (e.g. a warning, a slow path, a cosmetic defect), or the break is confirmed but affects only a handful of users | Fix on a normal PR cadence; rollback optional if a workaround exists |
| **P4** | Cosmetic, documentation-only, or CI-infrastructure noise (see [Distinguish a broken formula from CI infrastructure noise](../runbooks/formula-rollback.md#distinguish-a-broken-formula-from-ci-infrastructure-noise)) with no confirmed user-facing install/runtime impact | Track as a normal issue; no incident response needed |

## When to write a postmortem

Per `docs/slo.md`, any **P1** or **P2** incident — or any incident that
exceeds the 2-hour rollback budget regardless of level — should get a
[postmortem](postmortem-template.md). P3/P4 findings do not require one.
