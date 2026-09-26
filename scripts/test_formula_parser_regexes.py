"""
Tests for the stanza-line regexes exposed by scripts/formula_parser.py.

The compiled regexes (VERSION_LINE_RE, URL_LINE_RE, URL_INLINE_RE,
HOMEPAGE_LINE_RE, DESC_LINE_RE, LICENSE_LINE_RE, SHA256_LINE_RE,
RELEASE_URL_RE) are the single production source of stanza matching for
scripts/validate_formulae.py (which Homebrew CI's *Validate Formulae*
job runs) AND for ~14 test_formula_*_invariants.py modules — 16 files
in this tap import at least one of them (see
`grep -l URL_LINE_RE scripts/*.py`).

The existing dedicated tests only cover load_formulae() /
list_formula_paths() (test_formula_test_fixtures.py) and
_extract_url_hosts (test_formula_test_fixtures_url_hosts.py); every
regex above is otherwise pinned only by the real Formula/*.rb bodies,
all of which currently use one canonical shape per stanza. So a
regression that widens or narrows a regex silently passes today until
an adversarial or rare formula shape actually lands under Formula/.

The single most load-bearing regex distinction — the anchored
`URL_LINE_RE` (`^\\s*url "..."` with re.MULTILINE) vs the inline
`URL_INLINE_RE` (bare `url "..."` with no MULTILINE) — is called out
explicitly by the formula_parser.py module docstring as "kept here,
named distinctly, so callers keep whichever behavior they previously
relied on instead of silently changing which lines match (a real
behavior change, not just deduplication)." No test in this tap
currently pins that distinction; these do.

These tests exercise each regex directly against synthetic strings
(no Formula/ dependency, no network), and pin:

  * per-regex: at least one positive match with the expected capture
    group, at least one negative case that must NOT match
  * anchored-form contract: leading whitespace tolerated, mid-line
    (post-`#` comment, embedded in another stanza) rejected
  * URL_LINE_RE vs URL_INLINE_RE: same input, divergent expected match
    behavior, per the formula_parser.py module docstring
  * SHA256_LINE_RE: unanchored — matches whether at start-of-line or
    embedded after `on_macos do` / other indent
  * RELEASE_URL_RE: named groups `tag` / `file` capture the expected
    fields from a real GH release URL, and it rejects non-release URLs
  * MULTILINE finditer: all url/version/sha256 stanzas in a
    multi-block body are recovered in source order
"""
from __future__ import annotations

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import formula_parser  # noqa: E402


class SingleStanzaRegexTests(unittest.TestCase):
    """Anchored `^\\s*<stanza> "..."` regexes: version/homepage/desc/license."""

    def test_version_line_re_matches_leading_indent_and_captures_value(self):
        body = '  version "0.3.42"\n'
        m = formula_parser.VERSION_LINE_RE.search(body)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "0.3.42")

    def test_version_line_re_rejects_commented_out_line(self):
        # The anchor is `^\s*version`, so a `#` before `version` breaks
        # the anchor — a commented-out stanza must not be picked up as a
        # real version declaration.
        body = '# version "9.9.9-fake"\n'
        self.assertIsNone(formula_parser.VERSION_LINE_RE.search(body))

    def test_version_line_re_rejects_mid_line_occurrence(self):
        # Anchored form must reject `version "..."` embedded in another
        # stanza (e.g. inside a `desc "... version 2 ..."` string).
        body = 'desc "the version \\"1.0\\" release"\n'
        self.assertIsNone(formula_parser.VERSION_LINE_RE.search(body))

    def test_homepage_line_re_captures_url(self):
        body = '  homepage "https://kubestellar.io"\n'
        m = formula_parser.HOMEPAGE_LINE_RE.search(body)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "https://kubestellar.io")

    def test_desc_line_re_captures_description(self):
        body = '  desc "Multicluster config plane"\n'
        m = formula_parser.DESC_LINE_RE.search(body)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "Multicluster config plane")

    def test_license_line_re_captures_spdx_id(self):
        body = '  license "Apache-2.0"\n'
        m = formula_parser.LICENSE_LINE_RE.search(body)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "Apache-2.0")

    def test_homepage_desc_license_reject_commented_lines(self):
        for regex, name in (
            (formula_parser.HOMEPAGE_LINE_RE, "homepage"),
            (formula_parser.DESC_LINE_RE, "desc"),
            (formula_parser.LICENSE_LINE_RE, "license"),
        ):
            with self.subTest(stanza=name):
                self.assertIsNone(regex.search(f'# {name} "commented"\n'))


class UrlAnchoredVsInlineTests(unittest.TestCase):
    """Pins the URL_LINE_RE (anchored) vs URL_INLINE_RE (inline) contract.

    This distinction is spelled out in the formula_parser.py module
    docstring as intentional and load-bearing. A refactor that
    accidentally normalized both to the same form would silently
    change which lines the two callers match.
    """

    def test_url_line_re_matches_indented_url_and_captures_value(self):
        body = '  url "https://github.com/kubestellar/kubestellar/releases/download/v0.28.0/kubectl-plugin.tar.gz"\n'
        m = formula_parser.URL_LINE_RE.search(body)
        self.assertIsNotNone(m)
        self.assertEqual(
            m.group(1),
            "https://github.com/kubestellar/kubestellar/releases/download/v0.28.0/kubectl-plugin.tar.gz",
        )

    def test_url_line_re_rejects_url_after_hash_comment(self):
        # `# url "..."` is a commented-out declaration; the anchored
        # form must not treat it as active.
        body = '  # url "https://evil.example/pwn.tar.gz"\n'
        self.assertIsNone(formula_parser.URL_LINE_RE.search(body))

    def test_url_inline_re_matches_url_after_hash_comment(self):
        # The inline form, by contract (see formula_parser.py module
        # docstring), does match a `url "..."` embedded mid-line. This
        # pins that divergent behavior against silent normalization.
        body = '  # url "https://evil.example/pwn.tar.gz"\n'
        m = formula_parser.URL_INLINE_RE.search(body)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "https://evil.example/pwn.tar.gz")

    def test_url_line_re_finds_every_url_across_multiple_blocks(self):
        # Real formulae carry per-platform `on_macos do ... url "..." ... end`
        # blocks. finditer with re.MULTILINE must recover them all in
        # source order — invariant tests iterate over the resulting list.
        body = (
            'class Foo < Formula\n'
            '  on_macos do\n'
            '    on_arm do\n'
            '      url "https://github.com/x/y/releases/download/v1/darwin-arm64.tgz"\n'
            '    end\n'
            '    on_intel do\n'
            '      url "https://github.com/x/y/releases/download/v1/darwin-amd64.tgz"\n'
            '    end\n'
            '  end\n'
            '  on_linux do\n'
            '    url "https://github.com/x/y/releases/download/v1/linux-amd64.tgz"\n'
            '  end\n'
            'end\n'
        )
        matches = [m.group(1) for m in formula_parser.URL_LINE_RE.finditer(body)]
        self.assertEqual(
            matches,
            [
                "https://github.com/x/y/releases/download/v1/darwin-arm64.tgz",
                "https://github.com/x/y/releases/download/v1/darwin-amd64.tgz",
                "https://github.com/x/y/releases/download/v1/linux-amd64.tgz",
            ],
        )

    def test_url_line_re_is_multiline(self):
        # Guard against a future refactor dropping re.MULTILINE from
        # URL_LINE_RE — without it, `^` only matches the very start of
        # the input and per-block `url "..."` lines silently disappear.
        self.assertTrue(formula_parser.URL_LINE_RE.flags & re.MULTILINE)

    def test_url_inline_re_is_not_multiline(self):
        # And guard the inverse for URL_INLINE_RE, whose deliberate
        # lack of re.MULTILINE is what lets it catch mid-line urls.
        self.assertFalse(formula_parser.URL_INLINE_RE.flags & re.MULTILINE)


class Sha256LineReTests(unittest.TestCase):
    """SHA256_LINE_RE is unanchored — matches indented and mid-line."""

    def test_captures_hash_when_indented(self):
        expected = "0123456789abcdef" * 4
        body = f'    sha256 "{expected}"\n'
        m = formula_parser.SHA256_LINE_RE.search(body)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), expected)

    def test_finds_every_sha256_across_platform_blocks(self):
        body = (
            '    sha256 "' + "a" * 64 + '"\n'
            '    sha256 "' + "b" * 64 + '"\n'
            '    sha256 "' + "c" * 64 + '"\n'
        )
        hashes = [m.group(1) for m in formula_parser.SHA256_LINE_RE.finditer(body)]
        self.assertEqual(hashes, ["a" * 64, "b" * 64, "c" * 64])

    def test_does_not_match_bare_sha256_without_quoted_value(self):
        body = '  sha256\n'  # missing the "..."
        self.assertIsNone(formula_parser.SHA256_LINE_RE.search(body))


class ReleaseUrlReTests(unittest.TestCase):
    """RELEASE_URL_RE extracts <tag>/<file> from GitHub release URLs."""

    def test_captures_named_groups_tag_and_file(self):
        url = "https://github.com/kubestellar/kubestellar/releases/download/v0.28.0/kubectl-plugin-darwin-arm64.tar.gz"
        m = formula_parser.RELEASE_URL_RE.search(url)
        self.assertIsNotNone(m)
        self.assertEqual(m.group("tag"), "v0.28.0")
        self.assertEqual(m.group("file"), "kubectl-plugin-darwin-arm64.tar.gz")

    def test_captures_nightly_style_tag(self):
        url = "https://github.com/kubestellar/kubestellar/releases/download/v0.9.16-nightly.20260926/kubestellar-mcp-linux-amd64.tar.gz"
        m = formula_parser.RELEASE_URL_RE.search(url)
        self.assertIsNotNone(m)
        self.assertEqual(m.group("tag"), "v0.9.16-nightly.20260926")
        self.assertEqual(m.group("file"), "kubestellar-mcp-linux-amd64.tar.gz")

    def test_rejects_non_release_url(self):
        # A homepage-style URL (no `/releases/download/<tag>/<file>` path
        # segment) must NOT match — otherwise consumers would treat the
        # trailing path segment as a filename.
        for non_release in (
            "https://github.com/kubestellar/kubestellar",
            "https://kubestellar.io",
            "https://github.com/kubestellar/kubestellar/archive/refs/tags/v0.28.0.tar.gz",
        ):
            with self.subTest(url=non_release):
                self.assertIsNone(formula_parser.RELEASE_URL_RE.search(non_release))

    def test_requires_filename_after_tag(self):
        # `/releases/download/<tag>/` alone (no filename) must not match.
        self.assertIsNone(
            formula_parser.RELEASE_URL_RE.search(
                "https://github.com/o/r/releases/download/v1.0.0/"
            )
        )


class AllowedUrlHostsTests(unittest.TestCase):
    """The ALLOWED_URL_HOSTS set is the security allowlist.

    Any add/remove is a policy change, not a refactor. Pin the exact
    current membership so a silent widening (e.g. a stray edit that
    adds a mirror host) fails the test rather than the allowlist.
    """

    def test_membership_is_exactly_github_and_gh_release_cdn(self):
        self.assertEqual(
            formula_parser.ALLOWED_URL_HOSTS,
            {"github.com", "objects.githubusercontent.com"},
        )

    def test_is_a_set_not_a_list(self):
        # Membership checks in callers use `in`; a list would still
        # work but a set makes the intent (unordered allowlist) and
        # O(1) lookup explicit — pin it so a future refactor keeps it.
        self.assertIsInstance(formula_parser.ALLOWED_URL_HOSTS, set)


if __name__ == "__main__":
    unittest.main()
