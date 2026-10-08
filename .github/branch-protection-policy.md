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

**Path-filter caveat (resolved):** `brew-ci.yml` and `validate-formulae.yml`
previously triggered their `pull_request` jobs only on
`paths: ['Formula/**', ...]`. Per [GitHub's own troubleshooting
docs](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks#handling-skipped-but-required-checks),
GitHub does **not** treat a required status check as skipped-and-passing when
its workflow's path filter doesn't match — the check stays "Pending" forever
and **blocks merge indefinitely**. This was tracked in
[#640](https://github.com/kubestellar/homebrew-tap/issues/640) and fixed by
[#642](https://github.com/kubestellar/homebrew-tap/pull/642): the `paths:`
filter was removed from both workflows' `pull_request` triggers, and each
workflow now starts with a `detect-changes` job
(`dorny/paths-filter`) that the main job gates on via a job-level `if:`, so
the workflow always registers a status check — including a real "success"
for doc-only PRs that don't touch `Formula/**` — instead of staying
"Pending" forever. The three required contexts below are safe to enable as
of that fix; #640 is closed.

## Applying

The path-filter blocker above is resolved (see "Path-filter caveat
(resolved)"), so the three contexts below can now be enabled as required
status checks without deadlocking doc-only PRs. A repository administrator
must still apply these settings via the GitHub Settings > Branches UI, or
via:

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

## Known exception: automated GoReleaser formula updates

`Formula/**` version/URL/checksum updates are pushed directly to `main` by
`goreleaserbot` on every upstream release, with no associated pull request or
review (see `CONTRIBUTING.md`'s "Release sync" section). This is a real,
recurring exception to the "only maintainers via PR merge" rule above, not
covered by any documented bypass at the time of writing (originally tracked
in [#414](https://github.com/kubestellar/homebrew-tap/issues/414), which is
now closed — only its documentation items were resolved; the branch-protection
action item below remains open, tracked in
[#678](https://github.com/kubestellar/homebrew-tap/issues/678)). If this
automated flow is intended to remain a direct push, it should be scoped as an
explicit, narrow branch-protection exception for that bot identity; if not,
the flow should be moved behind a PR. Until a maintainer resolves this, do not
assume every commit on `main` touching `Formula/**` has had human review —
`brew-ci.yml`'s post-push run on `main` is the only automated check these
commits currently receive, and it has no Linux signal at all during outages
like the one tracked in [#409](https://github.com/kubestellar/homebrew-tap/issues/409).
