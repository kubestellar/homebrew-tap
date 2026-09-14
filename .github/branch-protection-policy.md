# Branch Protection Policy

The `main` branch of this repository must have the following protection rules enabled:

- Require pull request review before merging
  - Required approving reviews: **1**
  - Dismiss stale approvals when new commits are pushed
- Restrict who can push to matching branches: only maintainers via PR merge
- Do not allow force pushes
- Do not allow deletions
- Require linear history (recommended)

## Applying

A repository administrator must apply these settings via the GitHub Settings > Branches UI, or via:

```bash
gh api -X PUT "repos/kubestellar/homebrew-tap/branches/main/protection" --input policy.json
```

Where `policy.json` contains:

```json
{
  "required_status_checks": null,
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

## Known exception: automated GoReleaser formula updates

`Formula/**` version/URL/checksum updates are pushed directly to `main` by
`goreleaserbot` on every upstream release, with no associated pull request or
review (see `CONTRIBUTING.md`'s "Release sync" section). This is a real,
recurring exception to the "only maintainers via PR merge" rule above, not
covered by any documented bypass at the time of writing (see
[#414](https://github.com/kubestellar/homebrew-tap/issues/414)). If this
automated flow is intended to remain a direct push, it should be scoped as an
explicit, narrow branch-protection exception for that bot identity; if not,
the flow should be moved behind a PR. Until a maintainer resolves this, do not
assume every commit on `main` touching `Formula/**` has had human review —
`brew-ci.yml`'s post-push run on `main` is the only automated check these
commits currently receive, and it has no Linux signal at all during outages
like the one tracked in [#409](https://github.com/kubestellar/homebrew-tap/issues/409).
