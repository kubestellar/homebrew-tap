#!/usr/bin/env python3
"""Cross-consistency invariants tying each formula's `version "..."` line
to the version tokens embedded in its release URLs.

Existing tests check the version line, the URL shape, and the release
tarball filename shape independently — but nothing asserts they refer
to the *same* version. A GoReleaser bug (or a hand edit) that bumps
`version` but leaves the URL path stale would ship a formula whose
`brew fetch` downloads the wrong tarball for the wrong tag; `brew
install` would then either 404 or install the wrong binary.

Currently asserted here:

  * Every URL's `.../releases/download/v<TAG>/...` segment carries the
    tag `v<version-from-formula>`.
  * Every URL's tarball filename embeds the same `<version-from-formula>`
    in its second `_`-separated segment.
"""

import re
import unittest
from pathlib import Path

FORMULA_DIR = Path(__file__).resolve().parent.parent / "Formula"

VERSION_LINE_RE = re.compile(r'^\s*version\s+"([^"]+)"', re.MULTILINE)
URL_LINE_RE = re.compile(r'^\s*url\s+"([^"]+)"', re.MULTILINE)

RELEASE_URL_RE = re.compile(
    r"/releases/download/(?P<tag>[^/]+)/(?P<file>[^/]+)$"
)

# <name>_<version>_<os>_<arch>.tar.gz
FILENAME_VERSION_RE = re.compile(
    r"^[a-z][a-z0-9-]*[a-z0-9]_(?P<version>[^_]+)_(?:darwin|linux)_"
    r"(?:amd64|arm64)\.tar\.gz$"
)


class TestFormulaURLVersionLockstep(unittest.TestCase):
    """Every URL in a formula must reference the same version its
    `version "..."` line declares."""

    @classmethod
    def setUpClass(cls):
        cls.formulae = sorted(FORMULA_DIR.glob("*.rb"))
        assert cls.formulae, f"no formulae discovered under {FORMULA_DIR}"

    def test_release_url_tag_matches_declared_version(self):
        for f in self.formulae:
            src = f.read_text()
            vm = VERSION_LINE_RE.search(src)
            self.assertIsNotNone(vm, f"{f.name}: no version line")
            version = vm.group(1)
            expected_tag = f"v{version}"

            urls = URL_LINE_RE.findall(src)
            self.assertEqual(
                len(urls), 4,
                f"{f.name}: expected 4 URLs, got {len(urls)}",
            )
            for url in urls:
                m = RELEASE_URL_RE.search(url)
                self.assertIsNotNone(
                    m,
                    f"{f.name}: URL {url!r} does not look like a "
                    f"GitHub /releases/download/<tag>/<file> URL",
                )
                self.assertEqual(
                    m.group("tag"), expected_tag,
                    f"{f.name}: URL {url!r} uses tag "
                    f"{m.group('tag')!r} but `version` line declares "
                    f"{version!r} (expected tag {expected_tag!r}). "
                    "A GoReleaser bug or hand edit has left the URL "
                    "path stale relative to the `version` line — "
                    "`brew fetch` would download the wrong tarball.",
                )

    def test_release_url_filename_matches_declared_version(self):
        for f in self.formulae:
            src = f.read_text()
            vm = VERSION_LINE_RE.search(src)
            self.assertIsNotNone(vm, f"{f.name}: no version line")
            version = vm.group(1)

            urls = URL_LINE_RE.findall(src)
            for url in urls:
                m = RELEASE_URL_RE.search(url)
                self.assertIsNotNone(m, f"{f.name}: URL {url!r} unparsable")
                filename = m.group("file")
                fm = FILENAME_VERSION_RE.match(filename)
                self.assertIsNotNone(
                    fm,
                    f"{f.name}: tarball filename {filename!r} does not "
                    f"match <name>_<version>_<os>_<arch>.tar.gz",
                )
                self.assertEqual(
                    fm.group("version"), version,
                    f"{f.name}: tarball filename {filename!r} embeds "
                    f"version {fm.group('version')!r} but `version` "
                    f"line declares {version!r}. Fix the URL filename "
                    "so `brew fetch` resolves the correct artifact.",
                )


if __name__ == "__main__":
    unittest.main()
