# Postmortem Template

> Copy this template when writing a postmortem for a `kubestellar/homebrew-tap` incident.
> File it as a new document in `docs/postmortems/YYYY-MM-DD-<short-title>.md`.

---

## Postmortem: \<Title\>

**Date of incident:**  
**Date of postmortem:**  
**Authors:**  
**Severity:** <!-- P1 / P2 / P3 / P4 -->

---

## Summary

One paragraph describing what happened, the user impact, and how it was resolved.

---

## Impact

- **Duration:**
- **Affected formula(e):** <!-- kubestellar-ops / kubestellar-deploy / kc-agent -->
- **Affected platforms:** <!-- macOS/Linux, amd64/arm64 -->
- **Users affected:**
- **Functionality lost:** <!-- e.g., brew install/upgrade failing, broken binary at runtime -->

---

## Root Cause

Technical description of the root cause (e.g., bad URL, incorrect SHA256, broken upstream
release artifact, a regression in the installed binary). Reference the commit, PR, or
upstream release as appropriate.

---

## Detection

How was the incident detected? (CI failure on `main`, a user-reported issue, a security
report.) How long did it take from the start of impact to detection?

---

## Response

Narrative of the response — who did what, in what order. Reference the incident timeline
and note which steps of the [Formula Rollback Runbook](../runbooks/formula-rollback.md)
were followed.

---

## Timeline

| Time (UTC) | Event |
|------------|-------|
|            |       |

---

## What Went Well

-

---

## What Went Poorly

-

---

## Where We Got Lucky

-

---

## Action Items

| Action | Type | Owner | Due | Issue |
|--------|------|-------|-----|-------|
|        | prevent/detect/mitigate/process | | | |
