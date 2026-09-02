---
name: Incident Report
about: Report a broken formula release or other user-impacting incident
title: "[incident] <short description>"
labels: "kind/bug"
assignees: ""
---

## Incident Summary

**Date/Time (UTC):**  
**Duration:**  
**Severity:** <!-- P1 / P2 / P3 / P4 -->  
**Status:** <!-- Investigating / Mitigated / Resolved -->

**Affected formula(e):** <!-- kubestellar-ops / kubestellar-deploy / kc-agent -->

## Impact

<!-- What was affected? How many users? Which platforms (macOS/Linux, amd64/arm64)? What functionality was degraded or unavailable? -->

## Timeline

| Time (UTC) | Event |
|------------|-------|
|            | Incident detected |
|            | Investigation started |
|            | Root cause identified |
|            | Mitigation applied (e.g. pin, rollback PR opened) |
|            | Resolved |

## Root Cause

<!-- Describe the technical root cause. Be specific. -->

## Mitigation / Resolution

<!-- What was done to stop the bleeding and restore service? Link to the rollback runbook steps followed and any rollback PR. -->

See: [Formula Rollback Runbook](../../runbooks/formula-rollback.md)

## Contributing Factors

<!-- What conditions allowed this to happen? (e.g., missing CI check, unvalidated SHA256, no smoke test) -->

## Action Items

| Action | Owner | Due Date | Issue |
|--------|-------|----------|-------|
|        |       |          |       |

## Lessons Learned

<!-- What did we learn? What should we do differently? -->
