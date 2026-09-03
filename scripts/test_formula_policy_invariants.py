#!/usr/bin/env python3
"""Repo-wide formula policy invariants: URL host allowlist, https-only,
sha256 supply-chain hygiene, and class-name/desc/license metadata checks.

Split from test_validate_formulae.py (classes moved verbatim).
"""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate_formulae import validate
from formula_test_fixtures import FORMULA_DIR, _extract_url_hosts

# Homebrew formulae in this tap may pull artifacts only from these hosts.
# Extend this set with a code change (reviewed) when a new upstream lands.
ALLOWED_URL_HOSTS = {
    "github.com",
    "objects.githubusercontent.com",  # GH release CDN redirects land here
}


class TestFormulaPolicy(unittest.TestCase):
    """Whole-repo policy checks on Formula/*.rb — run against real files."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.formula_files = sorted(FORMULA_DIR.glob("*.rb"))
        if not cls.formula_files:
            raise unittest.SkipTest(f"no .rb files in {FORMULA_DIR}")

    def test_every_formula_has_a_test_block(self):
        # `brew audit --strict` requires a `test do` block on every
        # formula; if someone deletes one during a refactor, we want to
        # catch it in unit tests before it reaches `brew` in CI.
        missing = []
        for f in self.formula_files:
            body = f.read_text()
            if not re.search(r'^\s*test\s+do\b', body, re.MULTILINE):
                missing.append(f.name)
        self.assertEqual(
            missing, [],
            msg=f"Formula(e) missing `test do` block: {missing}",
        )

    def test_every_url_uses_https(self):
        # `http://` / `ftp://` / `file://` / `git+ssh://` in a release
        # URL would be a downgrade attack surface. Homebrew accepts
        # them but our tap does not.
        offenders = []
        for f in self.formula_files:
            for url, scheme, _host in _extract_url_hosts(f.read_text()):
                if scheme != "https":
                    offenders.append((f.name, url, scheme))
        self.assertEqual(
            offenders, [],
            msg=f"Formula url(s) not using https: {offenders}",
        )

    def test_every_url_host_is_in_allowlist(self):
        # Supply-chain guard: a malicious PR could point `url` at
        # attacker-controlled infrastructure. This test fails loudly
        # if any host outside ALLOWED_URL_HOSTS shows up.
        offenders = []
        for f in self.formula_files:
            for url, _scheme, host in _extract_url_hosts(f.read_text()):
                if host not in ALLOWED_URL_HOSTS:
                    offenders.append((f.name, host, url))
        self.assertEqual(
            offenders, [],
            msg=(
                "Formula url(s) point at hosts not in ALLOWED_URL_HOSTS. "
                "If this is legitimate, add the host to the allowlist in "
                f"this test file. Offenders: {offenders}"
            ),
        )

    def test_lockstep_groups_reference_real_formulae(self):
        # Guards against a typo in LOCKSTEP_GROUPS silently making a
        # lockstep pair partially skipped in production — since
        # `validate()` returns without complaint when only 1 partner
        # exists. If we intended a group of 2 but only 1 name matches
        # a file, that's a bug in the constant, not in the tap.
        from validate_formulae import LOCKSTEP_GROUPS
        formula_stems = {f.stem for f in self.formula_files}
        for group in LOCKSTEP_GROUPS:
            missing = group - formula_stems
            self.assertEqual(
                missing, set(),
                msg=(
                    f"LOCKSTEP_GROUPS entry {sorted(group)} references "
                    f"formulae that do not exist in {FORMULA_DIR}: "
                    f"{sorted(missing)}"
                ),
            )

    def test_every_formula_has_at_least_one_url(self):
        # A formula with no `url` line would be caught by `brew audit`
        # but not by our drift checker (no urls -> no url iteration ->
        # no errors). Assert every formula has at least one release URL.
        empty = []
        for f in self.formula_files:
            hosts = _extract_url_hosts(f.read_text())
            if not hosts:
                empty.append(f.name)
        self.assertEqual(
            empty, [],
            msg=f"Formula(e) with no url line: {empty}",
        )

    def test_drift_check_passes_on_real_formula_dir(self):
        # Integration: the exact command CI runs
        # (`python3 -u scripts/validate_formulae.py Formula`) must exit 0
        # on every commit. This test is a belt-and-suspenders duplicate
        # of TestValidateEndToEnd.test_real_formulae but framed as a
        # policy test so it appears in the policy failure cluster if
        # someone accidentally introduces drift while adding a formula.
        from validate_formulae import validate
        rc = validate(FORMULA_DIR)
        self.assertEqual(rc, 0, msg="drift check failed on real Formula/")


class TestFormulaSupplyChainPolicy(unittest.TestCase):
    """Additional supply-chain policy checks on Formula/*.rb.

    These guard against real regression classes that the drift checker and
    the existing TestFormulaPolicy do not cover:

      * distinct platform bottles must have distinct sha256 values (a
        copy-paste bug that reuses e.g. the darwin_amd64 checksum for
        darwin_arm64 would let brew install the wrong archive silently)
      * the `homepage` line must use https (parity with url policy)
      * every `sha256 "..."` in the file must be a valid 64-char lowercase
        hex string — enforced by the parser only for sha256 lines that
        immediately follow a url, but a stray malformed sha256 elsewhere
        would still ship in the tap and mislead brew's own audit output
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.formula_files = sorted(FORMULA_DIR.glob("*.rb"))
        if not cls.formula_files:
            raise unittest.SkipTest(f"no .rb files in {FORMULA_DIR}")

    def test_sha256_values_unique_within_each_formula(self):
        # Two `url` lines in the same formula that resolve to distinct
        # release archives (different arch, different OS) MUST have
        # distinct sha256 values. If they match, someone likely
        # copy-pasted a stanza and forgot to update the checksum — brew
        # will happily "verify" the wrong archive against the pasted
        # digest for one architecture.
        offenders = []
        for f in self.formula_files:
            text = f.read_text()
            urls = [m.group(1) for m in re.finditer(r'^\s*url\s+"([^"]+)"', text, re.MULTILINE)]
            shas = [m.group(1) for m in re.finditer(r'^\s*sha256\s+"([^"]+)"', text, re.MULTILINE)]
            if len(urls) < 2 or len(urls) != len(shas):
                # Structural mismatches are the drift checker's job.
                continue
            unique_urls = len(set(urls))
            unique_shas = len(set(shas))
            if unique_urls > 1 and unique_shas < unique_urls:
                # Find the specific duplicate sha and the urls it maps to.
                pairs = list(zip(urls, shas))
                seen: dict[str, list[str]] = {}
                for u, s in pairs:
                    seen.setdefault(s, []).append(u)
                dups = {s: us for s, us in seen.items() if len({*us}) > 1}
                offenders.append((f.name, dups))
        self.assertEqual(
            offenders, [],
            msg=(
                "Formula(e) reuse the same sha256 across distinct release "
                f"URLs (copy-paste bug): {offenders}"
            ),
        )

    def test_homepage_uses_https(self):
        # A homepage over plain http shows up in `brew info` and in the
        # GitHub taps directory — same downgrade concern as `url`.
        offenders = []
        for f in self.formula_files:
            for m in re.finditer(r'^\s*homepage\s+"([^"]+)"', f.read_text(), re.MULTILINE):
                homepage = m.group(1)
                scheme = homepage.partition("://")[0]
                if scheme != "https":
                    offenders.append((f.name, homepage))
        self.assertEqual(
            offenders, [],
            msg=f"Formula homepage(s) not using https: {offenders}",
        )

    def test_every_sha256_line_is_well_formed(self):
        # Whole-file sweep: catches malformed sha256 tokens even in
        # positions the drift checker doesn't inspect (e.g. a resource
        # block, a comment-based override — anywhere `sha256 "..."`
        # appears). Homebrew's own audit would reject these, but our
        # unit tests should fail first.
        offenders = []
        sha_line_re = re.compile(r'^\s*sha256\s+"([^"]+)"', re.MULTILINE)
        good = re.compile(r'^[0-9a-f]{64}$')
        for f in self.formula_files:
            for m in sha_line_re.finditer(f.read_text()):
                digest = m.group(1)
                if not good.match(digest):
                    offenders.append((f.name, digest))
        self.assertEqual(
            offenders, [],
            msg=(
                "Formula(e) contain sha256 token(s) that are not 64 "
                f"lowercase hex chars: {offenders}"
            ),
        )


def _expected_class_name(stem: str) -> str:
    """Homebrew derives a formula's Ruby class name from its filename by
    splitting on '-' and '_' and PascalCasing each segment. For example:
      ``kc-agent``            -> ``KcAgent``
      ``kubestellar-deploy``  -> ``KubestellarDeploy``
      ``my_thing``            -> ``MyThing``
    """
    parts = re.split(r'[-_]', stem)
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


class TestFormulaClassAndMetadataPolicy(unittest.TestCase):
    """Repo-wide checks for structural fields that ``brew audit --strict``
    treats as fatal but the drift checker does not currently inspect:

      * class-name-must-match-filename — ``brew install`` fails outright if
        the class token differs from Homebrew's PascalCased filename, so a
        typo like ``class Kcagent`` instead of ``class KcAgent`` bricks the
        tap for every user until reverted
      * every formula must declare a ``desc`` line — required by
        ``brew audit --strict`` and shown in ``brew info``
      * every formula must declare a ``license`` line — required by
        ``brew audit --strict`` for the core tap and highly recommended for
        third-party taps

    Failing these tests locally is cheaper than discovering them in the
    macOS-only ``brew-ci.yml`` job on a PR.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.formula_files = sorted(FORMULA_DIR.glob("*.rb"))
        if not cls.formula_files:
            raise unittest.SkipTest(f"no .rb files in {FORMULA_DIR}")

    def test_class_name_matches_filename(self):
        offenders = []
        class_re = re.compile(r'^\s*class\s+([A-Za-z0-9_]+)\s*<\s*Formula\b',
                              re.MULTILINE)
        for f in self.formula_files:
            expected = _expected_class_name(f.stem)
            m = class_re.search(f.read_text())
            if not m:
                offenders.append((f.name, None, expected))
                continue
            if m.group(1) != expected:
                offenders.append((f.name, m.group(1), expected))
        self.assertEqual(
            offenders, [],
            msg=(
                "Formula(e) whose Ruby class name does not match "
                "Homebrew's PascalCased filename (brew install will "
                f"fail): {offenders}"
            ),
        )

    def test_every_formula_has_desc(self):
        missing = [
            f.name for f in self.formula_files
            if not re.search(r'^\s*desc\s+"[^"]+"', f.read_text(), re.MULTILINE)
        ]
        self.assertEqual(
            missing, [],
            msg=f"Formula(e) missing `desc` line: {missing}",
        )

    def test_every_formula_has_license(self):
        missing = [
            f.name for f in self.formula_files
            if not re.search(r'^\s*license\s+"[^"]+"', f.read_text(), re.MULTILINE)
        ]
        self.assertEqual(
            missing, [],
            msg=f"Formula(e) missing `license` line: {missing}",
        )


class TestExpectedClassName(unittest.TestCase):
    """Direct coverage for the ``_expected_class_name`` helper."""

    def test_single_word(self):
        self.assertEqual(_expected_class_name("solo"), "Solo")

    def test_hyphenated(self):
        self.assertEqual(_expected_class_name("kc-agent"), "KcAgent")
        self.assertEqual(
            _expected_class_name("kubestellar-deploy"), "KubestellarDeploy"
        )

    def test_underscore(self):
        self.assertEqual(_expected_class_name("my_thing"), "MyThing")

    def test_mixed_separators(self):
        self.assertEqual(_expected_class_name("a-b_c"), "ABC")

    def test_double_separator_is_ignored(self):
        # Empty segments are skipped, mirroring Homebrew's behaviour.
        self.assertEqual(_expected_class_name("a--b"), "AB")

    def test_preserves_internal_capitalization(self):
        # PascalCase only lifts the first character; internal casing (e.g.
        # an acronym typed as `MCP`) survives untouched.
        self.assertEqual(_expected_class_name("kMCP-agent"), "KMCPAgent")


# =========================================================================
# Consistency policy — bin.install ↔ test block; url ↔ homepage owner/repo.
# Both are supply-chain / brew-audit regression classes not covered by the
# prior TestFormulaPolicy / TestFormulaClassAndMetadataPolicy suites.
# =========================================================================




if __name__ == "__main__":
    unittest.main()
