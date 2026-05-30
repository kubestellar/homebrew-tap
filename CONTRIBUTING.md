# Contributing to kubestellar/homebrew-tap

Thank you for contributing! This repo is the official Homebrew tap for KubeStellar tools.

## How formula versions are kept in sync

Formula files under `Formula/` are **auto-generated** by
[GoReleaser](https://goreleaser.com/) in the upstream
[kubestellar/console](https://github.com/kubestellar/console) repository.
A CI workflow in that repo opens a PR here on every new release.  You should
not edit version strings, URLs, or checksums by hand — let the automation do
it.

## Adding a new formula

1. Create `Formula/<tool-name>.rb` following the
   [Homebrew formula cookbook](https://docs.brew.sh/Formula-Cookbook).
2. Keep the description to **≤ 80 characters**.
3. Use idiomatic Homebrew syntax (e.g., `bin/"tool"` instead of
   `"#{bin}/tool"`).
4. Add a `test do` block that runs the binary with a trivial flag such as
   `--version` or `--help`.

## Testing a formula locally

```bash
# Tap this repo
brew tap kubestellar/tap

# Build from source and run the audit
brew install --build-from-source Formula/<tool>.rb
brew audit --strict kubestellar/tap/<tool>
brew test kubestellar/tap/<tool>
```

All three commands must pass before opening a PR.  The same checks run in CI
(`brew-ci.yml`) on every push.

## Pull request checklist

- [ ] `brew audit --strict` passes with no warnings
- [ ] `brew test` passes
- [ ] Description is ≤ 80 characters
- [ ] No string interpolation in `install` / `test` blocks
      (use `bin/"name"` not `"#{bin}/name"`)
- [ ] Commit is signed off (`git commit -s`) for
      [DCO](https://developercertificate.org/) compliance

## Review process

See `OWNERS` for the current list of approvers and reviewers.  PRs require at
least one approval from an approver before merge.  If you have questions, open
an issue or ping `@clubanderson` in the PR.
