#!/usr/bin/env python3
"""Further metadata invariants for Formula/*.rb.

Complements existing formula test suites with three specific guarantees:

* ``desc`` length ≤ 80 characters — ``brew audit --strict`` rejects longer
  values; a slightly-over-80 desc ships silently from GoReleaser until the
  tap is submitted upstream.
* All formulae declare the same ``license`` value — tap-wide policy must
  not drift silently from a partial template regen.
* The current tap-wide license value is exactly ``Apache-2.0`` — change
  this assertion intentionally when the whole tap relicenses.
* Each formula file contains exactly one ``class <Name> < Formula`` header
  — ``re.search()`` in sibling tests finds the FIRST match; a duplicate
  class block from a bad merge is silently accepted by those checks but
  causes ``brew`` to load only the LAST definition while the first ships
  dead code.

Standalone ``unittest`` module for parity with the sibling test files.
"""

import re
import unittest
from pathlib import Path

FORMULA_DIR = Path(__file__).resolve().parent.parent / "Formula"

DESC_LINE_RE = re.compile(r'^\s*desc\s+"([^"]+)"', re.MULTILINE)
LICENSE_LINE_RE = re.compile(r'^\s*license\s+"([^"]+)"', re.MULTILINE)
CLASS_HEADER_RE = re.compile(r"^\s*class\s+\w+\s*<\s*Formula\b", re.MULTILINE)

EXPECTED_LICENSE = "Apache-2.0"


class TestFormulaMetadataFurtherInvariants(unittest.TestCase):
    """Metadata invariants not covered by existing formula test suites."""

    @classmethod
    def setUpClass(cls):
        cls.formulae = sorted(FORMULA_DIR.glob("*.rb"))
        assert cls.formulae, f"no formulae discovered under {FORMULA_DIR}"

    def test_every_formula_desc_is_at_most_80_characters(self):
        for f in self.formulae:
            with self.subTest(formula=f.name):
                m = DESC_LINE_RE.search(f.read_text())
                self.assertIsNotNone(m, f"{f.name}: no desc line found")
                desc = m.group(1)
                self.assertLessEqual(
                    len(desc),
                    80,
                    f"{f.name}: desc is {len(desc)} chars (max 80): {desc!r}",
                )

    def test_all_formulae_declare_the_same_license(self):
        licenses: dict[str, str] = {}
        for f in self.formulae:
            m = LICENSE_LINE_RE.search(f.read_text())
            self.assertIsNotNone(m, f"{f.name}: no license line found")
            licenses[f.name] = m.group(1)
        unique = set(licenses.values())
        self.assertEqual(
            len(unique),
            1,
            f"formulae declare different licenses — tap policy must be "
            f"uniform: {licenses}",
        )

    def test_declared_license_is_apache_2_0(self):
        for f in self.formulae:
            with self.subTest(formula=f.name):
                m = LICENSE_LINE_RE.search(f.read_text())
                self.assertIsNotNone(m, f"{f.name}: no license line found")
                self.assertEqual(
                    m.group(1),
                    EXPECTED_LICENSE,
                    f"{f.name}: license={m.group(1)!r} must be "
                    f"{EXPECTED_LICENSE!r}",
                )

    def test_each_formula_has_exactly_one_class_formula_header(self):
        for f in self.formulae:
            text = f.read_text()
            with self.subTest(formula=f.name):
                matches = CLASS_HEADER_RE.findall(text)
                self.assertEqual(
                    len(matches),
                    1,
                    f"{f.name}: expected exactly one 'class <Name> < Formula' "
                    f"header, found {len(matches)}",
                )


if __name__ == "__main__":
    unittest.main()
