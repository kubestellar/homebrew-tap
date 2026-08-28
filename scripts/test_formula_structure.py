#!/usr/bin/env python3
"""Structural regression tests for Formula/*.rb.

These tests guard against copy-paste and codegen regressions that
validate_formulae.py does not catch:

  * Each formula must ship the full platform matrix
    (darwin_amd64, darwin_arm64, linux_amd64, linux_arm64) — a dropped
    on_linux/on_macos block or an accidentally deleted CPU arm would
    otherwise pass validate_formulae.py silently.
  * The four sha256 values inside one formula must all differ — if a
    codegen bug pastes the same digest for every platform, every
    non-primary-platform install would fail with a checksum error.
  * Every formula must declare its own `bin.install "<binary>"` matching
    the file stem, so a renamed formula does not accidentally install the
    wrong binary from an unrelated tarball.
  * Every formula must have `desc`, `homepage`, `license`, and a
    `test do` block — `brew audit` requires all of these and a nightly
    regen that drops them would leave the tap unauditable.

Written as a standalone `unittest` module (no third-party dependencies)
so it can be invoked from CI the same way as test_validate_formulae.py:

    python3 scripts/test_formula_structure.py
"""

import re
import unittest
from pathlib import Path

FORMULA_DIR = Path(__file__).resolve().parent.parent / "Formula"

REQUIRED_PLATFORMS = {
    ("darwin", "amd64"),
    ("darwin", "arm64"),
    ("linux", "amd64"),
    ("linux", "arm64"),
}

# URL segment "<binary>_<version>_<os>_<arch>.tar.gz"
URL_PLATFORM_RE = re.compile(
    r'url\s+"[^"]*_(darwin|linux)_(amd64|arm64)\.tar\.gz"'
)
SHA256_LINE_RE = re.compile(r'sha256\s+"([0-9a-f]{64})"')


def _load_formulae():
    files = sorted(FORMULA_DIR.glob("*.rb"))
    if not files:
        raise AssertionError(f"no formulae found under {FORMULA_DIR}")
    return {p.stem: p.read_text() for p in files}


class FormulaStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.formulae = _load_formulae()

    def test_all_formulae_are_readable(self):
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                self.assertTrue(text.strip(), f"{name}.rb is empty")

    def test_each_formula_covers_all_four_platforms(self):
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                found = set(URL_PLATFORM_RE.findall(text))
                missing = REQUIRED_PLATFORMS - found
                self.assertFalse(
                    missing,
                    f"{name}.rb is missing platform URL(s): "
                    f"{sorted(missing)} (found {sorted(found)})",
                )

    def test_each_formula_has_four_distinct_sha256_values(self):
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                shas = SHA256_LINE_RE.findall(text)
                self.assertEqual(
                    len(shas), 4,
                    f"{name}.rb: expected exactly 4 sha256 lines, got {len(shas)}",
                )
                self.assertEqual(
                    len(set(shas)), 4,
                    f"{name}.rb: sha256 duplicates detected across platforms "
                    f"(codegen copy-paste bug): {shas}",
                )

    def test_each_formula_installs_matching_binary(self):
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                pattern = re.compile(rf'bin\.install\s+"{re.escape(name)}"')
                matches = pattern.findall(text)
                self.assertEqual(
                    len(matches), 4,
                    f"{name}.rb: expected 4 'bin.install \"{name}\"' lines "
                    f"(one per platform), got {len(matches)}",
                )

    def test_each_formula_declares_metadata(self):
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                self.assertRegex(
                    text, r'(?m)^\s*desc\s+"[^"]+"',
                    f"{name}.rb missing desc",
                )
                self.assertRegex(
                    text,
                    r'(?m)^\s*homepage\s+"https://github\.com/kubestellar/[^"]+"',
                    f"{name}.rb missing/invalid homepage",
                )
                self.assertRegex(
                    text, r'(?m)^\s*test\s+do\s*$',
                    f"{name}.rb missing 'test do' block",
                )
                self.assertRegex(
                    text, r'(?m)^\s*license\s+"[^"]+"',
                    f"{name}.rb missing license",
                )

    def test_desc_length_within_homebrew_guideline(self):
        # Homebrew's `brew audit` warns when desc is missing or >80 chars.
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                m = re.search(r'^\s*desc\s+"([^"]+)"', text, re.MULTILINE)
                self.assertIsNotNone(m, f"{name}.rb missing desc")
                desc = m.group(1)
                self.assertTrue(
                    1 <= len(desc) <= 80,
                    f"{name}.rb desc length {len(desc)} outside 1..80: {desc!r}",
                )

    def test_url_binary_prefix_matches_formula_name(self):
        # The URL basename must start with "<formula-name>_" so that a
        # rename does not leave a stale tarball prefix pointing at the
        # old binary.
        url_re = re.compile(r'url\s+"([^"]+)"')
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                urls = url_re.findall(text)
                self.assertTrue(urls, f"{name}.rb has no url lines")
                for url in urls:
                    basename = url.rsplit("/", 1)[-1]
                    self.assertTrue(
                        basename.startswith(f"{name}_"),
                        f"{name}.rb: url basename {basename!r} does not "
                        f"start with formula name prefix '{name}_'",
                    )

    def test_every_url_embeds_declared_version(self):
        # The URL for every platform must contain the formula's own
        # `version` string. A codegen bug that bumps `version` while
        # leaving stale URLs (or vice-versa) would produce a formula
        # that installs the wrong tarball — `brew install` would fetch
        # yesterday's artefact, verify against today's sha256, and
        # error out cryptically ("SHA256 mismatch"). This test surfaces
        # that drift at PR time.
        ver_re = re.compile(r'^\s*version\s+"([^"]+)"', re.MULTILINE)
        url_re = re.compile(r'url\s+"([^"]+)"')
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                vm = ver_re.search(text)
                self.assertIsNotNone(vm, f"{name}.rb has no version line")
                version = vm.group(1)
                for url in url_re.findall(text):
                    self.assertIn(
                        version, url,
                        f"{name}.rb: url {url!r} does not contain "
                        f"declared version {version!r} — codegen drift",
                    )
                    # The GoReleaser convention also puts a `v` prefix
                    # on the tag path ("releases/download/v<version>/"),
                    # so the URL must also contain "v<version>/" —
                    # otherwise the tag path is stale even though the
                    # tarball basename happens to match.
                    self.assertIn(
                        f"/v{version}/", url,
                        f"{name}.rb: url {url!r} does not contain tag "
                        f"segment /v{version}/ — release tag drift",
                    )

    def test_url_host_is_github_releases(self):
        # Every download URL must resolve through
        # github.com/<owner>/<repo>/releases/download/... . A codegen
        # bug that emits raw.githubusercontent.com or a mirror would
        # produce a formula that bypasses the GitHub Releases audit
        # trail (no download counts, no artefact signature checks) and,
        # in some cases, would not survive brew audit --strict.
        url_re = re.compile(r'url\s+"([^"]+)"')
        allowed_prefix = re.compile(
            r'^https://github\.com/kubestellar/[^/]+/releases/download/'
        )
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                for url in url_re.findall(text):
                    self.assertRegex(
                        url, allowed_prefix,
                        f"{name}.rb: url {url!r} is not a "
                        f"github.com/kubestellar/<repo>/releases/download URL",
                    )

    def test_sha256_immediately_follows_url(self):
        # Every `url "..."` line must be followed on the next non-blank
        # line by a `sha256 "<hex>"` line. Homebrew's DSL binds sha256
        # to the *most recent* url; a stray blank line + comment that
        # separates them still works, but a codegen bug that swaps or
        # drops one of the four url/sha256 pairs would silently reuse
        # the previous sha256 for a different tarball.
        url_or_sha_re = re.compile(
            r'^\s*(?P<kind>url|sha256)\s+"[^"]+"', re.MULTILINE
        )
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                kinds = [m.group("kind") for m in url_or_sha_re.finditer(text)]
                # Expected shape: url, sha256, url, sha256, ... exactly
                # 4 pairs (one per platform slot).
                self.assertEqual(
                    len(kinds), 8,
                    f"{name}.rb: expected 8 url/sha256 lines, got "
                    f"{len(kinds)}: {kinds}",
                )
                for i, kind in enumerate(kinds):
                    expected = "url" if i % 2 == 0 else "sha256"
                    self.assertEqual(
                        kind, expected,
                        f"{name}.rb: url/sha256 order broken at index "
                        f"{i} (got {kind}, expected {expected}); "
                        f"full sequence: {kinds}",
                    )

    def test_test_block_actually_exercises_installed_binary(self):
        # A `test do` block that never touches `bin/"<binary>"` passes
        # brew audit but proves nothing — the install could ship a
        # broken artefact and `brew test` would still be green. Require
        # every test block to reference `bin/"<expected-binary>"`.
        test_block_re = re.compile(
            r'test\s+do\s*\n(?P<body>[^}]*?)\n\s*end\s*\n',
            re.DOTALL,
        )
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                m = test_block_re.search(text)
                self.assertIsNotNone(m, f"{name}.rb missing 'test do' block")
                body = m.group("body")
                self.assertIn(
                    f'bin/"{name}"', body,
                    f"{name}.rb: test block does not exercise "
                    f'bin/"{name}" — a broken install would still pass '
                    f"brew test",
                )
                # And it must actually run something — at least one
                # `system` or `assert_` invocation.
                self.assertTrue(
                    re.search(r'\bsystem\b|\bassert_\w+', body),
                    f"{name}.rb: test block has no system/assert_* "
                    f"invocation — brew test is a no-op",
                )

    def test_all_formulae_share_apache_license(self):
        # This tap ships Apache-2.0 binaries. A codegen bug that emits
        # a different SPDX id per formula would create an inconsistent
        # legal story for downstream consumers. Guard against silent
        # drift; if we ever intentionally take on a formula with a
        # different license, this test is the reminder to review the
        # change.
        license_re = re.compile(r'^\s*license\s+"([^"]+)"', re.MULTILINE)
        seen = {}
        for name, text in self.formulae.items():
            m = license_re.search(text)
            self.assertIsNotNone(m, f"{name}.rb missing license line")
            seen[name] = m.group(1)
        self.assertEqual(
            len(set(seen.values())), 1,
            f"formulae disagree on license id: {seen}",
        )
        self.assertEqual(
            list(seen.values())[0], "Apache-2.0",
            f"unexpected license id: {seen}",
        )


if __name__ == "__main__":
    unittest.main()
