# Formula Rollback Runbook

**Repository:** `kubestellar/homebrew-tap`  
**Applies to formulae:** `kubestellar-ops`, `kubestellar-deploy`, `kc-agent`

---

## Table of Contents

1. [When to Use This Runbook](#when-to-use-this-runbook)
2. [Detecting a Broken Release](#detecting-a-broken-release)
3. [Immediate Triage](#immediate-triage)
4. [Rolling Back a Formula](#rolling-back-a-formula)
5. [User Self-Service Recovery](#user-self-service-recovery)
6. [Pinning a Formula During an Incident](#pinning-a-formula-during-an-incident)
7. [Communicating to Users](#communicating-to-users)
8. [Post-Incident: Removing the Pin and Re-releasing](#post-incident-removing-the-pin-and-re-releasing)

---

## When to Use This Runbook

Use this runbook when a formula update ships and one or more of the following is true:

- `brew install kubestellar/tap/<formula>` fails with a download error (bad URL, 404, or incorrect SHA256)
- `brew install` succeeds but the installed binary crashes on startup or produces incorrect output
- A security vulnerability is discovered in a released binary that requires pulling the release
- CI (`brew-ci.yml`) passes but real installs fail in the field

---

## Detecting a Broken Release

### Signals

| Signal | Where to look |
|--------|--------------|
| CI failure on `main` | [brew-ci.yml](../.github/workflows/brew-ci.yml) run results |
| User-reported install failures | [Issues](https://github.com/kubestellar/homebrew-tap/issues) tagged `kind/bug` |
| GoReleaser run with bad artifacts | [kubestellar-mcp releases](https://github.com/kubestellar/kubestellar-mcp/releases) |
| SHA256 mismatch error | `brew install` output: `SHA256 mismatch` |
| 404 download error | `brew install` output: `curl: (22) The requested URL returned error: 404` |

### Verify manually

```bash
# Fetch the affected formula without installing
brew fetch --formula kubestellar/tap/<formula-name>

# Example
brew fetch --formula kubestellar/tap/kubestellar-ops
```

A fetch failure confirms a broken release. A successful fetch with smoke-test failure confirms a bad binary.

---

## Immediate Triage

1. **Identify the affected formula(e).** Run `brew fetch` for each of the three formulae.
2. **Identify the last known-good commit** in this repo:
   ```bash
   git log --oneline Formula/<formula-name>.rb | head -10
   ```
3. **Identify the last known-good release tag** in the upstream repo:
   - https://github.com/kubestellar/kubestellar-mcp/releases
4. **Assess scope:** Is it one formula, or all three? Is it all platforms (macOS/Linux, amd64/arm64)?

---

## Rolling Back a Formula

### Option A: Revert the formula commit

```bash
# Clone the tap (or use an existing checkout)
git clone https://github.com/kubestellar/homebrew-tap
cd homebrew-tap

# Find the last good commit for the formula
git log --oneline Formula/<formula-name>.rb

# Create a rollback branch
git checkout -b rollback/<formula-name>-<date>

# Restore the formula to the last known-good commit
git checkout <good-commit-sha> -- Formula/<formula-name>.rb

# Verify the formula content points to a valid release
grep -A3 'url' Formula/<formula-name>.rb

# Commit with DCO sign-off
git commit -s -m "rollback: revert <formula-name> to <version> (fixes broken release)"

# Push and open a PR immediately
git push origin rollback/<formula-name>-<date>
gh pr create --repo kubestellar/homebrew-tap \
  --head rollback/<formula-name>-<date> \
  --base main \
  --title "rollback: revert <formula-name> to <version>" \
  --body "Emergency rollback. See issue #<issue-number>."
```

### Option B: Manually fix the URL and SHA256

If only the URL or SHA256 is wrong (e.g., a GoReleaser naming glitch):

1. Find the correct download URL from the upstream release:
   ```
   https://github.com/kubestellar/kubestellar-mcp/releases/tag/<version>
   ```

2. Compute the correct SHA256:
   ```bash
   curl -sL <url> | sha256sum
   ```

3. Edit the formula:
   ```bash
   # Edit Formula/<formula-name>.rb
   # Update url and sha256 for the affected platform(s)
   ```

4. Verify locally:
   ```bash
   brew fetch --formula Formula/<formula-name>.rb
   brew install --formula Formula/<formula-name>.rb
   ```

5. Commit, push, and open a PR.

---

## User Self-Service Recovery

If users are affected before a rollback PR is merged, share this recovery procedure in the tracking issue and on any community channels:

### Option 1: Install a specific older version from git

```bash
# Uninstall the broken version
brew uninstall kubestellar/tap/<formula-name>

# Install from a specific commit of the tap
brew install https://raw.githubusercontent.com/kubestellar/homebrew-tap/<good-commit-sha>/Formula/<formula-name>.rb
```

### Option 2: Install from a specific upstream release URL directly

```bash
# Download and install the binary manually from a known-good release
VERSION=<last-good-version>  # e.g., v0.8.21
ARCH=$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')
OS=$(uname -s | tr '[:upper:]' '[:lower:]')

curl -sL "https://github.com/kubestellar/kubestellar-mcp/releases/download/${VERSION}/kubestellar-ops_${VERSION#v}_${OS}_${ARCH}.tar.gz" \
  | tar -xz kubestellar-ops

sudo mv kubestellar-ops /usr/local/bin/
```

### Option 3: Pin to the current version to stop future upgrades

```bash
brew pin kubestellar/tap/<formula-name>
```

(See also [Pinning a Formula During an Incident](#pinning-a-formula-during-an-incident).)

---

## Pinning a Formula During an Incident

To prevent users from auto-upgrading to a broken version while a fix is in progress, advise users to pin:

```bash
brew pin kubestellar/tap/kubestellar-ops
brew pin kubestellar/tap/kubestellar-deploy
brew pin kubestellar/tap/kc-agent
```

**After the fix is merged and validated**, users should unpin:

```bash
brew unpin kubestellar/tap/kubestellar-ops
brew upgrade kubestellar/tap/kubestellar-ops
```

---

## Communicating to Users

When a broken release is confirmed:

1. **File a tracking issue** titled `[incident] broken brew install for <formula-name> <version>` using the [incident template](../.github/ISSUE_TEMPLATE/).
2. **Post a comment** on the tracking issue with the [User Self-Service Recovery](#user-self-service-recovery) steps above.
3. **Update the issue** when the rollback PR is merged and the fix is live.

---

## Post-Incident: Removing the Pin and Re-releasing

After the upstream release is fixed and a new formula has been merged to `main`:

1. Verify the new release is healthy:
   ```bash
   brew fetch --formula kubestellar/tap/<formula-name>
   brew install --formula kubestellar/tap/<formula-name>
   <formula-name> version
   ```

2. Announce on the tracking issue that the fix is live and users can upgrade:
   ```
   brew unpin kubestellar/tap/<formula-name>
   brew update && brew upgrade kubestellar/tap/<formula-name>
   ```

3. Close the tracking issue.

4. Consider a postmortem if the incident lasted more than 2 hours or affected more than a handful of users. Use the [postmortem template](https://github.com/kubestellar/kubestellar-mcp/blob/main/docs/postmortem-template.md) as a starting point.
