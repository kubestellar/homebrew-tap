# Branch Protection Policy

The `main` branch of this repository must have the following protection rules enabled:

- Require pull request review before merging
  - Required approving reviews: **1**
  - Dismiss stale approvals when new commits are pushed
- Require status checks to pass before merging (see `required_status_checks` below) —
  a merge must not bypass the CI checks the [SLOs](../docs/slo.md) assume are
  gating `main`
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
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "brew audit + install smoke test (macos-latest)",
      "brew audit + install smoke test (ubuntu-latest)",
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

The three contexts are the job names produced by
[brew-ci.yml](../.github/workflows/brew-ci.yml) (matrixed over `macos-latest`/
`ubuntu-latest`) and [validate-formulae.yml](../.github/workflows/validate-formulae.yml).
If either workflow's job name or matrix changes, update `contexts` to match —
a stale context that never reports blocks merges forever, and a dropped context
silently stops gating. `strict: true` additionally requires the branch be
up to date with `main` before merging, so an already-green PR can't merge a
stale diff that never re-ran CI against the latest `main`.

## Rationale

Addresses security findings tracked in issue #177 (branch protection) and #178 (mandatory code review).

`required_status_checks` was previously `null`, meaning even a correctly
applied policy did not actually require `brew-ci.yml`/`validate-formulae.yml`
to pass before merge — the [SLOs](../docs/slo.md) assume CI is a merge gate,
but nothing enforced it. See the tracking issue for this gap.
