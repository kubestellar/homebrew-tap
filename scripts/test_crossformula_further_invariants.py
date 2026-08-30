#!/usr/bin/env python3
"""Further cross-formula and URL-shape invariants.

Extends the checks in test_crossformula_invariants.py:

  * Lockstep partners must share more than just a version string.
    kubestellar-ops and kubestellar-deploy release from the same
    kubestellar-mcp binary set; their `homepage` and every release
    URL's <org>/<repo> path must therefore also be identical. A
    drift in either — e.g. one formula's release URL still pointing
    at a legacy repo after a homepage bump — would silently install
    the wrong binary set for that formula despite matching version
    strings.

  * No release URL may carry a query string or fragment. Homebrew
    caches the download by URL; a stray `?token=`, `?ref=`, or
    `#anchor` from a bad template would create per-user cache keys,
    fetch through a redirect, or (in the case of tokens) leak
    credentials into `brew fetch` output.

Runnable the same way as the sibling test modules:

    python3 scripts/test_crossformula_further_invariants.py
"""

import re
import unittest
from pathlib import Path
from urllib.parse import urlparse

FORMULA_DIR = Path(__file__).resolve().parent.parent / "Formula"

URL_RE = re.compile(r'^\s*url\s+"([^"]+)"', re.MULTILINE)
HOMEPAGE_RE = re.compile(r'^\s*homepage\s+"([^"]+)"', re.MULTILINE)

# The lockstep pair that this tap treats as a single upstream release.
# Kept in sync with LOCKSTEP_GROUPS in scripts/validate_formulae.py and
# with test_ops_and_deploy_share_a_single_version in
# test_crossformula_invariants.py.
LOCKSTEP_PARTNERS = ("kubestellar-ops", "kubestellar-deploy")


def _load_formulae():
    files = sorted(FORMULA_DIR.glob("*.rb"))
    if not files:
        raise AssertionError(f"no formulae found under {FORMULA_DIR}")
    return {p.stem: p.read_text() for p in files}


def _github_repo_from_url(url: str) -> str:
    """Return the '<owner>/<repo>' segment of a github.com URL.

    Only handles release-download URLs of the shape
    https://github.com/<owner>/<repo>/releases/download/<tag>/<file>.
    Returns "" for URLs that don't match, so callers can .assertNotEqual("").
    """
    parts = urlparse(url)
    if parts.netloc != "github.com":
        return ""
    segments = [s for s in parts.path.split("/") if s]
    if len(segments) < 2:
        return ""
    return f"{segments[0]}/{segments[1]}"


class LockstepGroupShapeInvariants(unittest.TestCase):
    """Invariants that MUST hold across every member of a lockstep group."""

    @classmethod
    def setUpClass(cls):
        cls.formulae = _load_formulae()
        missing = [p for p in LOCKSTEP_PARTNERS if p not in cls.formulae]
        if missing:
            raise unittest.SkipTest(
                f"lockstep partner(s) missing from tap: {missing}"
            )

    def test_lockstep_group_shares_a_single_homepage(self):
        # Ops and deploy release from the same kubestellar-mcp upstream
        # release; their homepage MUST point at the same repo. A drift
        # (ops.homepage != deploy.homepage) usually indicates one of
        # them was manually pointed at a fork or a legacy path — a
        # user landing on the wrong homepage from `brew info` gets
        # confusing docs and can't file a bug against the real repo.
        homepages = {}
        for stem in LOCKSTEP_PARTNERS:
            m = HOMEPAGE_RE.search(self.formulae[stem])
            self.assertIsNotNone(
                m, f"{stem}.rb: no homepage line found",
            )
            homepages[stem] = m.group(1)
        distinct = set(homepages.values())
        self.assertEqual(
            len(distinct), 1,
            f"lockstep partners {LOCKSTEP_PARTNERS} disagree on homepage: "
            f"{homepages}",
        )

    def test_lockstep_group_release_urls_share_a_single_github_repo(self):
        # Every release URL across the lockstep group must resolve to
        # the same `<owner>/<repo>` on github.com. Version lockstep +
        # matching homepage still allows a URL-only drift where, say,
        # deploy's URLs point at `kubestellar/kubestellar-mcp` and
        # ops's URLs point at `kubestellar/legacy-mcp` — same version
        # string, same homepage, entirely different binaries.
        seen = {}
        for stem in LOCKSTEP_PARTNERS:
            urls = URL_RE.findall(self.formulae[stem])
            self.assertTrue(
                urls, f"{stem}.rb: no release URLs found",
            )
            for u in urls:
                repo = _github_repo_from_url(u)
                self.assertNotEqual(
                    repo, "",
                    f"{stem}.rb: URL {u!r} is not a recognizable "
                    f"github.com/<owner>/<repo>/... release URL",
                )
                seen.setdefault(repo, []).append((stem, u))
        by_repo = {repo: [s for s, _ in items] for repo, items in seen.items()}
        self.assertEqual(
            len(seen), 1,
            f"lockstep partners {LOCKSTEP_PARTNERS} pull from more than "
            f"one github repo: {by_repo}",
        )


class UrlShapeInvariants(unittest.TestCase):
    """URL-value invariants that apply to every formula in the tap."""

    @classmethod
    def setUpClass(cls):
        cls.formulae = _load_formulae()

    def test_no_release_url_contains_query_string_or_fragment(self):
        # Homebrew's downloader keys its cache off the URL and shells
        # the URL out to `curl` in a way that surfaces it verbatim in
        # `brew fetch -v` output. A `?token=<secret>` query — even one
        # accidentally captured from a signed GitHub redirect during
        # codegen — would (a) create a per-user cache key that breaks
        # Homebrew's shared-cache assumptions, (b) surface the token
        # in log lines a user might paste into an issue, and (c)
        # invalidate the moment the token expires. A `#fragment` is
        # meaningless for a download URL and, if present, indicates a
        # copy-paste from a browser tab.
        for name, text in self.formulae.items():
            urls = URL_RE.findall(text)
            self.assertTrue(
                urls, f"{name}.rb: no release URLs found",
            )
            for u in urls:
                parts = urlparse(u)
                with self.subTest(formula=name, url=u):
                    self.assertEqual(
                        parts.query, "",
                        f"{name}.rb: url {u!r} carries a query string "
                        f"({parts.query!r}); release URLs must be pure paths",
                    )
                    self.assertEqual(
                        parts.fragment, "",
                        f"{name}.rb: url {u!r} carries a fragment "
                        f"({parts.fragment!r}); release URLs must be pure paths",
                    )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
