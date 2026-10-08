# Apply `main` branch protection (admin runbook)

Tracks [#678](https://github.com/kubestellar/homebrew-tap/issues/678). Requires
repo admin; the GitHub App used by agents gets 403 on this endpoint.

## Apply

Replace `goreleaserbot` in `restrictions.users` with the actual identity of the
token GoReleaser uses to push (user or app; use `apps` for an app).

```bash
gh api -X PUT repos/kubestellar/homebrew-tap/branches/main/protection --input - <<'JSON'
{
  "required_status_checks": {"strict": false, "contexts": [
    "brew audit + install smoke test (ubuntu-latest)",
    "brew audit + install smoke test (macos-latest)",
    "unit tests + drift check"]},
  "enforce_admins": false,
  "required_pull_request_reviews": {"required_approving_review_count": 1},
  "restrictions": {"users": ["goreleaserbot"], "teams": [], "apps": []}
}
JSON
```

Alternative: set GoReleaser `brews.repository.pull_request.enabled: true` so
formula updates go through PRs.

## Verify

```bash
gh api repos/kubestellar/homebrew-tap/branches/main/protection \
  --jq '{checks: .required_status_checks.contexts, reviews: .required_pull_request_reviews.required_approving_review_count, push: .restrictions.users[].login}'
```

## Afterwards

Update the "Known exception" section of `.github/branch-protection-policy.md`
to describe the scoped bypass, then close #678.
