#!/usr/bin/env python3
"""Further structural invariants for Formula/*.rb.

Complements test_formula_structure.py / test_formula_codegen_invariants.py /
test_formula_extra_invariants.py with additional guarantees that weren't yet
asserted:

* When ``version`` uses the ``-nightly.YYYYMMDD`` suffix the date component
  parses as a real calendar date and is not in the future — a garbled stamp
  would still match the shape regex but silently point at an inexistent
  release, so validate_formulae.py would download-verify against nothing.
* Every ``homepage`` points at a repository under
  ``https://github.com/kubestellar/`` — a codegen drift that swapped it for a
  personal fork or a docs URL would slip past ``brew audit`` (which only
  checks that the URL is reachable) but silently break the tap's provenance
  story.
* Every formula file contains exactly one ``on_macos do`` and one ``on_linux
  do`` block — a missing block would fail installs on that OS silently, and
  a duplicate block is a codegen bug that would install the same binary
  twice on that platform.
* Every formula has exactly one ``test do`` block and it invokes the
  matching binary. A missing or duplicated test block breaks ``brew test``.

Standalone `unittest` module for parity with the sibling test files.
"""

import re
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

FORMULA_DIR = Path(__file__).resolve().parent.parent / "Formula"

VERSION_LINE_RE = re.compile(r'^\s*version\s+"([^"]+)"', re.MULTILINE)
NIGHTLY_RE = re.compile(r"^\d+\.\d+\.\d+-nightly\.(?P<stamp>\d{8})$")
HOMEPAGE_LINE_RE = re.compile(r'^\s*homepage\s+"([^"]+)"', re.MULTILINE)
ON_MACOS_RE = re.compile(r"^\s*on_macos\s+do\b", re.MULTILINE)
ON_LINUX_RE = re.compile(r"^\s*on_linux\s+do\b", re.MULTILINE)
TEST_BLOCK_RE = re.compile(r"^\s*test\s+do\b", re.MULTILINE)


def _binary_name(formula_path: Path) -> str:
    return formula_path.stem


class TestFormulaFurtherInvariants(unittest.TestCase):
    """Additional invariants on shipped Formula/*.rb files."""

    @classmethod
    def setUpClass(cls):
        cls.formulae = sorted(FORMULA_DIR.glob("*.rb"))
        assert cls.formulae, f"no formulae discovered under {FORMULA_DIR}"

    def test_nightly_stamp_is_a_real_past_or_present_date(self):
        today = datetime.now(timezone.utc).date()
        for f in self.formulae:
            with self.subTest(formula=f.name):
                m = VERSION_LINE_RE.search(f.read_text())
                self.assertIsNotNone(m, f"{f.name}: no version line")
                ver = m.group(1)
                nm = NIGHTLY_RE.match(ver)
                if nm is None:
                    # Stable release without nightly suffix — nothing to check.
                    continue
                stamp = nm.group("stamp")
                try:
                    d = date(int(stamp[0:4]), int(stamp[4:6]), int(stamp[6:8]))
                except ValueError as e:
                    self.fail(
                        f"{f.name}: nightly stamp {stamp!r} is not a real "
                        f"calendar date ({e})"
                    )
                self.assertLessEqual(
                    d,
                    today,
                    f"{f.name}: nightly stamp {stamp!r} is in the future "
                    f"(today={today.isoformat()})",
                )

    def test_homepage_is_under_kubestellar_org(self):
        for f in self.formulae:
            with self.subTest(formula=f.name):
                m = HOMEPAGE_LINE_RE.search(f.read_text())
                self.assertIsNotNone(m, f"{f.name}: no homepage line")
                hp = m.group(1)
                self.assertTrue(
                    hp.startswith("https://github.com/kubestellar/"),
                    f"{f.name}: homepage={hp!r} must be a "
                    "https://github.com/kubestellar/<repo> URL",
                )

    def test_each_formula_has_exactly_one_on_macos_and_on_linux_block(self):
        for f in self.formulae:
            text = f.read_text()
            with self.subTest(formula=f.name):
                self.assertEqual(
                    len(ON_MACOS_RE.findall(text)),
                    1,
                    f"{f.name}: expected exactly one on_macos block",
                )
                self.assertEqual(
                    len(ON_LINUX_RE.findall(text)),
                    1,
                    f"{f.name}: expected exactly one on_linux block",
                )

    def test_test_block_invokes_matching_binary(self):
        for f in self.formulae:
            text = f.read_text()
            with self.subTest(formula=f.name):
                self.assertEqual(
                    len(TEST_BLOCK_RE.findall(text)),
                    1,
                    f"{f.name}: expected exactly one test do block",
                )
                # Extract the test block body and confirm it references the
                # binary that install actually places on PATH.
                idx = TEST_BLOCK_RE.search(text).end()
                # naive scan to matching `end` at column 2 (the block indent).
                # For these small files we just check that the binary name
                # appears somewhere in the remainder of the file after `test`.
                self.assertIn(
                    _binary_name(f),
                    text[idx:],
                    f"{f.name}: test block does not reference the "
                    f"{_binary_name(f)!r} binary",
                )


if __name__ == "__main__":
    unittest.main()
