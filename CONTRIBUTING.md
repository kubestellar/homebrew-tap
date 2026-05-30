# Contributing to KubeStellar Homebrew Tap

Thanks for helping keep this tap up to date.

## Adding or updating formulae

- Put each formula in `Formula/<name>.rb`.
- Keep formula names aligned with the published binary name.
- Prefer small, targeted edits when updating release assets or metadata.

## Local validation

- Use `brew install --build-from-source <formula>` to smoke-test changes.
- Run `brew audit --strict <formula>` before opening a PR.
- Use `brew test <formula>` when the formula defines a meaningful test block.

## Release sync

Formula versions and URLs should track the corresponding upstream release.
If a release process exists upstream, update this tap from that source of
truth instead of hand-editing versioned files repeatedly.

## Sign-off and review

- All commits must include DCO sign-off (`git commit -s`).
- Open a PR for review after the tap changes are ready.
- Maintainers listed in `OWNERS` review tap changes.
