#!/usr/bin/env python3
"""Additional structural invariants for Formula/*.rb.

Extends test_formula_structure.py / test_formula_codegen_invariants.py with
guarantees not previously asserted:

* `version` matches the tap's semver-with-optional-nightly-suffix shape
  ``X.Y.Z`` or ``X.Y.Z-nightly.YYYYMMDD``. A stray ``v`` prefix, a 4-part
  version, or a malformed nightly stamp would silently break the
  ``version <-> URL`` cross-checks used by validate_formulae.py.
* Every ``url`` declaration ends in ``.tar.gz`` — GoReleaser can be
  reconfigured to ship ``.zip`` archives, but the ``define_method(:install)
  { bin.install ... }`` blocks in every formula assume a plain tarball.
* Every ``desc`` line is Homebrew-audit-clean: starts with an uppercase
  letter and does NOT end with a period. Both are hard rules in
  ``brew audit --strict`` and a regression would leave the tap
  unauditable.
* No formula file uses CRLF line endings. Some brew versions choke on
  mixed-line-ending .rb files, and CRLF is impossible to introduce
  intentionally on a Linux runner — so any occurrence means an editor
  regression.

Standalone `unittest` module for parity with the sibling test files.
"""

import re
import unittest
from pathlib import Path

FORMULA_DIR = Path(__file__).resolve().parent.parent / "Formula"

VERSION_RE = re.compile(r"^(?P<sem>\d+\.\d+\.\d+)(?:-nightly\.\d{8})?$")
URL_RE = re.compile(r'url\s+"([^"]+)"')
VERSION_LINE_RE = re.compile(r'^\s*version\s+"([^"]+)"', re.MULTILINE)
DESC_LINE_RE = re.compile(r'^\s*desc\s+"([^"]+)"', re.MULTILINE)


class TestFormulaExtraInvariants(unittest.TestCase):
    """Additional invariants on shipped Formula/*.rb files."""

    @classmethod
    def setUpClass(cls):
        cls.formulae = sorted(FORMULA_DIR.glob("*.rb"))
        assert cls.formulae, f"no formulae discovered under {FORMULA_DIR}"

    def test_version_matches_semver_or_semver_nightly(self):
        for f in self.formulae:
            with self.subTest(formula=f.name):
                m = VERSION_LINE_RE.search(f.read_text())
                self.assertIsNotNone(m, f"{f.name}: no version line")
                ver = m.group(1)
                self.assertRegex(
                    ver,
                    VERSION_RE,
                    f"{f.name}: version={ver!r} must be X.Y.Z or X.Y.Z-nightly.YYYYMMDD",
                )

    def test_every_release_url_ends_with_tar_gz(self):
        for f in self.formulae:
            urls = URL_RE.findall(f.read_text())
            self.assertTrue(urls, f"{f.name}: no urls found")
            for url in urls:
                with self.subTest(formula=f.name, url=url):
                    self.assertTrue(
                        url.endswith(".tar.gz"),
                        f"{f.name}: url {url!r} does not end with .tar.gz — "
                        "the define_method(:install) blocks assume a tarball payload.",
                    )

    def test_desc_is_homebrew_audit_clean(self):
        """`brew audit --strict` requires desc to start with a capital letter
        and to NOT end in a period. A codegen regression that dropped either
        rule would leave the tap unauditable in CI."""
        for f in self.formulae:
            with self.subTest(formula=f.name):
                m = DESC_LINE_RE.search(f.read_text())
                self.assertIsNotNone(m, f"{f.name}: no desc line")
                desc = m.group(1)
                self.assertTrue(desc, f"{f.name}: empty desc")
                self.assertTrue(
                    desc[0].isupper(),
                    f"{f.name}: desc={desc!r} must start with uppercase letter",
                )
                self.assertFalse(
                    desc.endswith("."),
                    f"{f.name}: desc={desc!r} must not end with a period",
                )

    def test_formula_files_use_lf_line_endings(self):
        """Mixed line endings choke some brew versions and are impossible to
        introduce intentionally on the Linux runners this repo uses."""
        for f in self.formulae:
            with self.subTest(formula=f.name):
                raw = f.read_bytes()
                self.assertNotIn(
                    b"\r\n",
                    raw,
                    f"{f.name}: file contains CRLF line endings",
                )


if __name__ == "__main__":
    unittest.main()
