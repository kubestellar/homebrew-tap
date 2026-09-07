# Branch Protection Policy

The `main` branch of this repository must have the following protection rules enabled:

- Require pull request review before merging
  - Required approving reviews: **1**
  - Dismiss stale approvals when new commits are pushed
- Require the following status checks to pass before merging (see "Required
  status checks" below for why these three, and the path-filter caveat)
- Restrict who can push to matching branches: only maintainers via PR merge
- Do not allow force pushes
- Do not allow deletions
- Require linear history (recommended)

## Required status checks

`docs/slo.md` treats a red `main` check on `brew-ci.yml` ("Homebrew CI") or
`validate-formulae.yml` ("Validate Formulae") as a likely user-impacting
incident, not routine noise — but that premise only holds if those checks are
actually required before a PR can merge to `main`. Required contexts:

- `brew audit + install smoke test (ubuntu-latest)`
- `brew audit + install smoke test (macos-latest)`
- `unit tests + drift check`

**Path-filter caveat (correction):** `brew-ci.yml` and `validate-formulae.yml`
both trigger only on `paths: ['Formula/**', ...]`. Per [GitHub's own
troubleshooting docs](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks#handling-skipped-but-required-checks),
GitHub does **not** treat a required status check as skipped-and-passing when
its workflow's path filter doesn't match — the check stays "Pending" forever
and **blocks merge indefinitely**. This is the opposite of what an earlier
draft of this doc assumed. Concretely, most of this operations agent's own
`runbooks/**`/`docs/**`-only PRs would never trigger `brew-ci.yml` or
`validate-formulae.yml`, so enabling the three contexts below as required
**today, as-is, would deadlock every doc-only PR**. Before enabling them,
whoever applies this policy must first remove the `paths:` filter from these
workflows' `pull_request` trigger and instead gate the actual work with a
job/step-level `if:` that checks for changed paths (so the workflow always
runs and reports a real "success" for non-matching PRs, satisfying the
required check) — see GitHub's guidance linked above for the pattern.

## Applying

**Do not enable the three contexts above as required until the path-filter
fix described above lands** — doing so first would deadlock every PR that
doesn't touch `Formula/**` (including this repo's own `docs/**`/`runbooks/**`
operations PRs). A repository administrator must apply these settings via the
GitHub Settings > Branches UI, or via:

```bash
gh api -X PUT "repos/kubestellar/homebrew-tap/branches/main/protection" --input policy.json
```

Where `policy.json` contains:

```json
{
  "required_status_checks": {
    "strict": false,
    "contexts": [
      "brew audit + install smoke test (ubuntu-latest)",
      "brew audit + install smoke test (macos-latest)",
      "unit tests + drift check"
    ]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false
  },
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false
}
```

## Rationale

Addresses security findings tracked in issue #177 (branch protection) and #178 (mandatory code review).

`required_status_checks: null` was previously applied, meaning no CI check
gated merges to `main` — a PR could be approved and merged while `brew-ci.yml`
or `validate-formulae.yml` was still running or had already failed, letting a
broken formula reach `main` (and therefore every live `brew install`/`brew
upgrade`) purely on review approval. Requiring the three contexts above closes
that gap; see issue #340 for the full finding.
