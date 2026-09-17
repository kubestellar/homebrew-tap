"""
Tests for scripts/formula_test_fixtures.py::_extract_url_hosts.

`_extract_url_hosts` is the single choke point between "a `url "..."` line
inside Formula/*.rb" and "a hostname compared against the ALLOWED_URL_HOSTS
allowlist" (used by test_formula_policy_invariants.py:65-71 and
test_formula_consistency_invariants.py:123). Any change to how it partitions
scheme/host silently moves the security boundary.

The existing test_formula_test_fixtures.py only covers load_formulae(). The
parser's behavior is otherwise pinned only by the real Formula/*.rb files,
all of which currently use standard https://github.com/... release URLs — so
a parser regression on a rare/adversarial URL shape produces no test failure
until a bad host actually lands in Formula/. See kubestellar/homebrew-tap#491.

These tests exercise the parser directly with synthetic formula bodies (no
network, no Formula/ dependency) and pin each behavior against a matching
ALLOWED_URL_HOSTS decision so a normalization regression (RFC-style userinfo
stripping, lowercasing the host, defaulting the scheme, treating a missing
scheme as https://) fails a test rather than silently weakening the allowlist.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import formula_test_fixtures  # noqa: E402
from formula_test_fixtures import ALLOWED_URL_HOSTS, _extract_url_hosts  # noqa: E402


class ExtractUrlHostsHappyPathTests(unittest.TestCase):
    """URL shapes that must keep parsing to a host that IS in ALLOWED_URL_HOSTS."""

    def test_standard_github_release_url_parses_to_github_com(self):
        body = 'url "https://github.com/kubestellar/kubestellar/archive/refs/tags/v0.1.0.tar.gz"\n'
        self.assertEqual(
            _extract_url_hosts(body),
            [(
                "https://github.com/kubestellar/kubestellar/archive/refs/tags/v0.1.0.tar.gz",
                "https",
                "github.com",
            )],
        )
        self.assertIn("github.com", ALLOWED_URL_HOSTS)

    def test_github_release_cdn_parses_to_objects_githubusercontent_com(self):
        body = 'url "https://objects.githubusercontent.com/github-production-release-asset/abc"\n'
        hosts = _extract_url_hosts(body)
        self.assertEqual(len(hosts), 1)
        self.assertEqual(hosts[0][1], "https")
        self.assertEqual(hosts[0][2], "objects.githubusercontent.com")
        self.assertIn("objects.githubusercontent.com", ALLOWED_URL_HOSTS)

    def test_leading_whitespace_is_tolerated(self):
        body = '    url "https://github.com/x/y"\n'
        hosts = _extract_url_hosts(body)
        self.assertEqual(len(hosts), 1)
        self.assertEqual(hosts[0][2], "github.com")


class ExtractUrlHostsRejectionPathTests(unittest.TestCase):
    """URL shapes that MUST parse to a host that is NOT in ALLOWED_URL_HOSTS,
    so the policy invariant continues to reject them."""

    def test_plain_http_scheme_is_preserved_verbatim(self):
        body = 'url "http://evil.example.com/x"\n'
        hosts = _extract_url_hosts(body)
        self.assertEqual(hosts, [("http://evil.example.com/x", "http", "evil.example.com")])
        self.assertNotIn("evil.example.com", ALLOWED_URL_HOSTS)

    def test_missing_scheme_yields_empty_host_not_defaulted(self):
        # If the parser ever grows a "helpful" default (e.g. assume https://
        # when scheme is absent), it would leak scheme-less strings into the
        # host allowlist comparison. This test pins that missing "://" keeps
        # the host empty, which is guaranteed not in ALLOWED_URL_HOSTS.
        body = 'url "github.com/no-scheme/x"\n'
        hosts = _extract_url_hosts(body)
        self.assertEqual(len(hosts), 1)
        self.assertEqual(hosts[0][1], "github.com/no-scheme/x")
        self.assertEqual(hosts[0][2], "")
        self.assertNotIn("", ALLOWED_URL_HOSTS)

    def test_userinfo_is_kept_in_host_string_not_stripped(self):
        # https://github.com@evil.com/x resolves to evil.com per RFC 3986,
        # but the crude parser keeps the userinfo attached to the host
        # string. That is the SAFE behavior for a set-membership allowlist:
        # "github.com@evil.com" is not in the set, so the URL is rejected.
        # An RFC-conformant "strip userinfo" refactor would silently open
        # this bypass — this test fails such a refactor.
        body = 'url "https://github.com@evil.com/x"\n'
        hosts = _extract_url_hosts(body)
        self.assertEqual(hosts, [("https://github.com@evil.com/x", "https", "github.com@evil.com")])
        self.assertNotIn("github.com@evil.com", ALLOWED_URL_HOSTS)

    def test_port_stays_in_host_string_not_stripped(self):
        # Same shape as userinfo: a "helpful" `host, _, _ = host.partition(":")`
        # refactor would collapse `github.com:8080` down to `github.com` and
        # let non-default-port URLs through. Pin the current behavior.
        body = 'url "https://github.com:8080/x"\n'
        hosts = _extract_url_hosts(body)
        self.assertEqual(hosts, [("https://github.com:8080/x", "https", "github.com:8080")])
        self.assertNotIn("github.com:8080", ALLOWED_URL_HOSTS)

    def test_host_comparison_is_case_sensitive(self):
        # ALLOWED_URL_HOSTS is a Python set of lowercase strings; membership
        # is case-sensitive. A .lower() normalization in the parser would
        # cause `gitHub.com` to match — this pins that it does not, so any
        # such refactor is a visible test failure paired with an explicit
        # decision about case handling.
        body = 'url "https://gitHub.com/X"\n'
        hosts = _extract_url_hosts(body)
        self.assertEqual(hosts, [("https://gitHub.com/X", "https", "gitHub.com")])
        self.assertNotIn("gitHub.com", ALLOWED_URL_HOSTS)


class ExtractUrlHostsRegexAnchoringTests(unittest.TestCase):
    """The parser uses an anchored `^\\s*url\\s+"..."` regex (re.MULTILINE).
    These tests pin what that anchoring does and does not match."""

    def test_commented_out_url_line_is_ignored(self):
        # A `# url "..."` line has non-whitespace before `url`, so the
        # anchored regex must not match it. If the anchor were dropped,
        # commented-out URLs would leak into the allowlist scan.
        body = '# url "https://commented.example.com/x"\n'
        self.assertEqual(_extract_url_hosts(body), [])

    def test_multiple_url_lines_preserve_source_order(self):
        # Both callers (`test_formula_policy_invariants.py:65` and
        # `test_formula_consistency_invariants.py:123`) iterate the returned
        # list in order and cite the offending URL in failure messages by
        # index. Pin that ordering is preserved.
        body = (
            'url "https://github.com/a/b"\n'
            'url "https://objects.githubusercontent.com/c/d"\n'
            'url "http://evil.example.com/e"\n'
        )
        hosts = [h for (_url, _scheme, h) in _extract_url_hosts(body)]
        self.assertEqual(hosts, ["github.com", "objects.githubusercontent.com", "evil.example.com"])

    def test_url_embedded_mid_line_is_not_matched(self):
        # The anchored form only matches at line start (after optional
        # whitespace). If a Ruby comment or heredoc snippet contains a
        # trailing `url "..."` mid-line, it must not be picked up.
        body = 'system bin/"x", "--config" # url "https://embedded.example.com/x"\n'
        self.assertEqual(_extract_url_hosts(body), [])


class ExtractUrlHostsAllowlistShapeTests(unittest.TestCase):
    """Cross-checks between the parser and the allowlist constant so a
    refactor that touches either without touching the other trips a test."""

    def test_allowlist_contains_only_github_hosts_today(self):
        # If ALLOWED_URL_HOSTS grows, that is a policy change that should be
        # a deliberate, reviewed commit — this test fails on such changes
        # so the diff is forced through review with an explicit rationale
        # (matches the "extend this set with a code change (reviewed)"
        # comment in formula_test_fixtures.py:62).
        self.assertEqual(
            ALLOWED_URL_HOSTS,
            {"github.com", "objects.githubusercontent.com"},
        )

    def test_extract_returns_empty_list_for_body_without_url_stanza(self):
        # Formulae bodies that only appear in `desc`/`homepage`/`sha256`
        # blocks must produce an empty result, not crash and not spuriously
        # extract from adjacent stanzas.
        body = (
            'class X < Formula\n'
            '  desc "example"\n'
            '  homepage "https://homepage.example.com/"\n'
            '  sha256 "abc"\n'
            'end\n'
        )
        self.assertEqual(_extract_url_hosts(body), [])

    def test_module_exports_expected_public_surface(self):
        # Guards against a rename that would silently break the two
        # callers cited in the module docstring.
        self.assertTrue(hasattr(formula_test_fixtures, "_extract_url_hosts"))
        self.assertTrue(hasattr(formula_test_fixtures, "ALLOWED_URL_HOSTS"))
        self.assertTrue(hasattr(formula_test_fixtures, "load_formulae"))


if __name__ == "__main__":
    unittest.main()
