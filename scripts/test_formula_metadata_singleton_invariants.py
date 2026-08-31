"""Regression coverage for exactly-one metadata singleton invariants.

Homebrew formulae are expected to declare each of ``desc``, ``homepage``,
``license``, and ``version`` exactly once, and to contain exactly one
``test do ... end`` block. When a stanza appears twice, Homebrew silently
uses the *last* occurrence and the first is effectively dead metadata —
users hit ``brew info`` and see the wrong description, or ``brew audit
--strict`` starts flagging the file after a downstream homebrew update.

Existing coverage in this repository:

  * ``desc``/``homepage``/``license`` **presence** is checked
    (``test_every_formula_has_desc``, ``test_every_formula_has_license``,
    ``test_each_formula_declares_metadata``), but only with
    ``re.search`` — a second stanza would still pass.
  * ``version`` uniqueness is enforced inside ``parse_formula`` in
    ``validate_formulae.py`` (returns an error dict when two ``version``
    lines are present), but no test file re-asserts that invariant on
    the *checked-in* formulae — a corrupt commit that lands two
    ``version`` lines would surface only via the CLI drift check,
    not the unit-test job.
  * ``class ... < Formula`` header and ``on_macos``/``on_linux`` blocks
    are already covered with exactly-one assertions
    (``test_each_formula_has_exactly_one_class_formula_header``,
    ``test_each_formula_has_exactly_one_on_macos_and_on_linux_block``).

This module adds the missing exactly-one checks so a codegen regression
that duplicates a metadata line, or a manual edit that leaves an old
stanza in place, fails the unit-test job directly.
"""

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
FORMULA_DIR = REPO_ROOT / "Formula"

DESC_LINE_RE = re.compile(r'^\s*desc\s+"[^"]+"', re.MULTILINE)
HOMEPAGE_LINE_RE = re.compile(r'^\s*homepage\s+"[^"]+"', re.MULTILINE)
LICENSE_LINE_RE = re.compile(r'^\s*license\s+"[^"]+"', re.MULTILINE)
VERSION_LINE_RE = re.compile(r'^\s*version\s+"[^"]+"', re.MULTILINE)
# `test do` at start of a line (allowing indentation). Only the opening
# marker is counted — Homebrew allows exactly one such block per formula.
TEST_DO_RE = re.compile(r'^\s*test\s+do\b', re.MULTILINE)


class TestMetadataSingletons(unittest.TestCase):
    """Each metadata stanza must appear exactly once in every formula."""

    @classmethod
    def setUpClass(cls):
        cls.formulae = sorted(FORMULA_DIR.glob("*.rb"))
        assert cls.formulae, f"no formulae found under {FORMULA_DIR}"

    def _assert_exactly_one(self, pattern, label):
        for f in self.formulae:
            with self.subTest(formula=f.name, stanza=label):
                text = f.read_text()
                matches = pattern.findall(text)
                self.assertEqual(
                    len(matches),
                    1,
                    f"{f.name}: expected exactly one `{label}` line, "
                    f"got {len(matches)}. Homebrew silently prefers the last "
                    f"occurrence, so a duplicate stanza turns the earlier one "
                    f"into dead metadata that still appears in code review.",
                )

    def test_every_formula_declares_desc_exactly_once(self):
        self._assert_exactly_one(DESC_LINE_RE, "desc")

    def test_every_formula_declares_homepage_exactly_once(self):
        self._assert_exactly_one(HOMEPAGE_LINE_RE, "homepage")

    def test_every_formula_declares_license_exactly_once(self):
        self._assert_exactly_one(LICENSE_LINE_RE, "license")

    def test_every_formula_declares_version_exactly_once(self):
        # `validate_formulae.parse_formula` already returns an error dict
        # when two `version` lines are present, but that path is only
        # exercised by the CLI drift check in the CI workflow. This test
        # pins the same invariant into the unit-test job so a bad commit
        # surfaces in `python -m unittest discover` too.
        self._assert_exactly_one(VERSION_LINE_RE, "version")


class TestTestBlockSingleton(unittest.TestCase):
    """Every formula must contain exactly one ``test do`` block.

    A missing block would fail ``brew test`` outright (already covered by
    ``test_test_block_uses_system_form`` which asserts a match). A
    *second* block, on the other hand, would silently duplicate the smoke
    test and still pass every existing assertion because they all match
    on the first occurrence via ``re.search``. Pin the exactly-one
    invariant here.
    """

    @classmethod
    def setUpClass(cls):
        cls.formulae = sorted(FORMULA_DIR.glob("*.rb"))
        assert cls.formulae, f"no formulae found under {FORMULA_DIR}"

    def test_every_formula_has_exactly_one_test_do_block(self):
        for f in self.formulae:
            with self.subTest(formula=f.name):
                text = f.read_text()
                matches = TEST_DO_RE.findall(text)
                self.assertEqual(
                    len(matches),
                    1,
                    f"{f.name}: expected exactly one `test do` block, "
                    f"got {len(matches)}. Duplicate test blocks run twice "
                    f"under `brew test` and hint at a bad codegen merge.",
                )


class TestMetadataSingletonSelfCheck(unittest.TestCase):
    """Belt-and-braces meta-tests: prove the regex assertions above would
    actually catch a duplicated stanza. Guards against a regex-typo
    regression that quietly turns the exactly-one tests into never-fail
    tautologies.
    """

    def _make_synthetic_formula(self, extra_line: str) -> str:
        base = (
            'class KubestellarSynthetic < Formula\n'
            '  desc "Synthetic fixture used for the meta self-check"\n'
            '  homepage "https://github.com/kubestellar/kubestellar-mcp"\n'
            '  version "0.0.0"\n'
            '  license "Apache-2.0"\n'
            '  test do\n'
            '    system bin/"kubestellar-synthetic", "version"\n'
            '  end\n'
            'end\n'
        )
        # Insert the duplicated line right after the first `class` line
        # (indentation matches the surrounding stanzas).
        return base.replace('class KubestellarSynthetic < Formula\n',
                            f'class KubestellarSynthetic < Formula\n  {extra_line}\n')

    def test_desc_regex_finds_a_duplicate(self):
        text = self._make_synthetic_formula('desc "second desc line"')
        self.assertEqual(len(DESC_LINE_RE.findall(text)), 2)

    def test_homepage_regex_finds_a_duplicate(self):
        text = self._make_synthetic_formula(
            'homepage "https://example.com/second"'
        )
        self.assertEqual(len(HOMEPAGE_LINE_RE.findall(text)), 2)

    def test_license_regex_finds_a_duplicate(self):
        text = self._make_synthetic_formula('license "MIT"')
        self.assertEqual(len(LICENSE_LINE_RE.findall(text)), 2)

    def test_version_regex_finds_a_duplicate(self):
        text = self._make_synthetic_formula('version "9.9.9"')
        self.assertEqual(len(VERSION_LINE_RE.findall(text)), 2)

    def test_test_do_regex_finds_a_duplicate(self):
        # Insert a second `test do ... end` block just before the
        # closing `end` of the class.
        base = self._make_synthetic_formula('# no-op')
        text = base.replace(
            'end\n',
            '  test do\n    system bin/"kubestellar-synthetic", "--help"\n  end\nend\n',
            1,
        )
        self.assertEqual(len(TEST_DO_RE.findall(text)), 2)


if __name__ == "__main__":
    unittest.main()
