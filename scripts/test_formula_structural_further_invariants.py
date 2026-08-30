#!/usr/bin/env python3
"""Additional structural invariants for Formula/*.rb.

These invariants target codegen-drift scenarios that would still pass every
existing test in scripts/ but silently break the tap:

  * A URL landing in the WRONG Hardware::CPU arch block, or in the WRONG
    on_macos/on_linux OS block. The existing platform-coverage test only
    verifies that all four (os, arch) URLs exist somewhere in the file; it
    does NOT check that each URL sits inside a guard whose OS/arch it
    actually matches. A template rewrite that swaps two blocks would still
    ship four distinct URLs, four distinct sha256s, and a matching binary
    name — but users on the swapped arch would download the wrong tarball
    and get a "cannot execute binary file" / arch-mismatch failure.

  * A silent addition of `depends_on`, `resource`, or `livecheck` to one of
    the binary tap formulae. These are pre-built-binary formulae — they
    must not declare Homebrew dependencies (they'd break `brew install`
    without warning by pulling in extra packages), must not carry
    resource bundles (the tarball is complete), and must not carry a
    livecheck stanza (nightly stamps are release-generated, not upstream-
    tracked). None of the existing tests forbid these.

  * A code drift that turns the per-platform install block into anything
    other than the canonical single line `bin.install "<formula>"`.
    Anything else (extra system() calls, PATH manipulation, file writes)
    would sneak arbitrary logic into a tap that is supposed to be a
    pure binary-install shim.

  * A stray trailing whitespace line, missing final newline, or content
    after the class-ending `end`. Homebrew audit does not flag these, but
    they cause spurious diffs on every regenerated formula and hide real
    changes in review.
"""

import re
import unittest
from pathlib import Path

FORMULA_DIR = Path(__file__).resolve().parent.parent / "Formula"

URL_LINE_RE = re.compile(
    r'^\s*url\s+"https://github\.com/[^"]+_(?P<os>darwin|linux)_(?P<arch>amd64|arm64)\.tar\.gz"',
    re.MULTILINE,
)

# on_macos / on_linux are 2-space indented; their matching `end` is at
# the same 2-space indent. Match that specific indent to avoid the
# false-positive matches you'd get from a plain non-greedy [\s\S]*?
# (which would stop at the first nested `end`).
ON_OS_BLOCK_RE = re.compile(
    r'^  on_(?P<os>macos|linux)\s+do\b(?P<body>[\s\S]*?)^  end\s*$',
    re.MULTILINE,
)

# `if Hardware::CPU.<primary>?` guards inside an on_os body are 4-space
# indented; their matching `end` is at 4-space indent.
IF_HW_BLOCK_RE = re.compile(
    r'^    if Hardware::CPU\.(?P<primary>intel|arm)\?'
    r'(?:\s+&&\s+Hardware::CPU\.[^\n]*)?'
    r'\s*\n(?P<body>[\s\S]*?)^    end\s*$',
    re.MULTILINE,
)

DEPENDS_ON_RE = re.compile(r'^\s*depends_on\b', re.MULTILINE)
RESOURCE_BLOCK_RE = re.compile(r'^\s*resource\s+"[^"]+"\s+do\b', re.MULTILINE)
LIVECHECK_RE = re.compile(r'^\s*livecheck\s+do\b', re.MULTILINE)
REVISION_RE = re.compile(r'^\s*revision\s+\d+\b', re.MULTILINE)
KEG_ONLY_RE = re.compile(r'^\s*keg_only\b', re.MULTILINE)
DEPRECATE_RE = re.compile(r'^\s*deprecate!(?=\s|$)', re.MULTILINE)
DISABLE_RE = re.compile(r'^\s*disable!(?=\s|$)', re.MULTILINE)
PATCH_BLOCK_RE = re.compile(r'^\s*patch\s+do\b', re.MULTILINE)
OPTION_RE = re.compile(r'^\s*option\s+"[^"]+"', re.MULTILINE)

# The install body inside `define_method(:install) do ... end`. Non-greedy
# match; body may span multiple lines but should be a single significant
# statement.
DEFINE_INSTALL_RE = re.compile(
    r'define_method\(:install\)\s+do\s*\n(?P<body>[\s\S]*?)^\s*end\s*$',
    re.MULTILINE,
)

BIN_INSTALL_LINE_RE = re.compile(r'^\s*bin\.install\s+"(?P<name>[^"]+)"\s*$')

OS_ARCH_TO_URL_ARCH = {
    ("macos", "intel"): "amd64",
    ("macos", "arm"): "arm64",
    ("linux", "intel"): "amd64",
    ("linux", "arm"): "arm64",
}


class FormulaLoader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.formulae = {
            p.stem: p.read_text(encoding="utf-8")
            for p in sorted(FORMULA_DIR.glob("*.rb"))
        }
        assert cls.formulae, "no formulae found under Formula/"


class UrlArchContextInvariants(FormulaLoader):
    """Every URL must sit inside a Hardware::CPU guard whose OS/arch match
    the URL's own os_arch tail."""

    def _blocks(self, text):
        """Yield (on_os, primary_arch, block_body) for every arch guard
        under every on_os block."""
        for os_match in ON_OS_BLOCK_RE.finditer(text):
            os_name = os_match.group("os")
            body = os_match.group("body")
            for arch_match in IF_HW_BLOCK_RE.finditer(body):
                yield (
                    os_name,
                    arch_match.group("primary"),
                    arch_match.group("body"),
                )

    def test_every_url_sits_in_matching_os_and_arch_block(self):
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                # Collect every URL and where it appears.
                url_matches = list(URL_LINE_RE.finditer(text))
                self.assertEqual(
                    len(url_matches), 4,
                    f"{name}.rb: expected 4 platform URLs, got {len(url_matches)}",
                )
                blocks = list(self._blocks(text))
                self.assertEqual(
                    len(blocks), 4,
                    f"{name}.rb: expected 4 (on_os, Hardware::CPU) blocks, "
                    f"got {len(blocks)}",
                )
                # Every URL must appear inside the block whose OS/arch it names.
                for um in url_matches:
                    url_os = "macos" if um.group("os") == "darwin" else "linux"
                    url_arch = um.group("arch")  # amd64 | arm64
                    url_text = um.group(0)
                    matched_block = None
                    for on_os, primary, body in blocks:
                        if url_text in body:
                            matched_block = (on_os, primary)
                            break
                    self.assertIsNotNone(
                        matched_block,
                        f"{name}.rb: URL not found inside any Hardware::CPU "
                        f"block: {url_text!r}",
                    )
                    on_os, primary = matched_block
                    self.assertEqual(
                        on_os, url_os,
                        f"{name}.rb: URL for {url_os}/{url_arch} is inside "
                        f"on_{on_os} block (should be on_{url_os})",
                    )
                    expected_url_arch = OS_ARCH_TO_URL_ARCH[(on_os, primary)]
                    self.assertEqual(
                        url_arch, expected_url_arch,
                        f"{name}.rb: URL arch {url_arch!r} is inside a "
                        f"Hardware::CPU.{primary}? block (which expects "
                        f"{expected_url_arch!r})",
                    )


class ForbiddenStanzaInvariants(FormulaLoader):
    """Binary tap formulae must not carry depends_on, resource, or livecheck."""

    def test_no_depends_on_stanza(self):
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                self.assertIsNone(
                    DEPENDS_ON_RE.search(text),
                    f"{name}.rb has a depends_on stanza — pre-built-binary "
                    f"formulae must not declare Homebrew dependencies",
                )

    def test_no_resource_stanza(self):
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                self.assertIsNone(
                    RESOURCE_BLOCK_RE.search(text),
                    f"{name}.rb has a `resource \"...\" do` block — the "
                    f"release tarball is complete; no extra resources allowed",
                )

    def test_no_livecheck_stanza(self):
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                self.assertIsNone(
                    LIVECHECK_RE.search(text),
                    f"{name}.rb has a livecheck stanza — nightly stamps are "
                    f"release-generated, not upstream-tracked",
                )

    def test_no_revision_stanza(self):
        # A stray `revision N` (e.g. copy-pasted from a homebrew-core
        # template) would silently break `brew upgrade` — Homebrew treats
        # revision bumps as new installable versions, so shipping a
        # revision on a nightly-based formula would either strand users
        # on a specific rev or churn every nightly with a bogus rev bump.
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                self.assertIsNone(
                    REVISION_RE.search(text),
                    f"{name}.rb has a `revision N` stanza — nightly-based "
                    f"binary formulae must not carry Homebrew revision "
                    f"bumps; the nightly stamp already versions each build",
                )

    def test_no_keg_only_stanza(self):
        # keg_only would silently prevent PATH linking; users would run
        # `brew install kc-agent` successfully and then find no
        # `kc-agent` on their PATH. Never valid for these CLIs.
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                self.assertIsNone(
                    KEG_ONLY_RE.search(text),
                    f"{name}.rb has a `keg_only` stanza — these CLIs must "
                    f"be linked into PATH; keg_only would silently break "
                    f"`brew install`",
                )

    def test_no_deprecate_or_disable_stanza(self):
        # deprecate!/disable! would emit user-visible warnings or block
        # installs on every `brew install`. A codegen template that
        # accidentally emits one would be immediately user-facing.
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                self.assertIsNone(
                    DEPRECATE_RE.search(text),
                    f"{name}.rb has a `deprecate!` stanza — the tap is "
                    f"actively released; deprecation must be an explicit, "
                    f"reviewed decision, not a codegen artifact",
                )
                self.assertIsNone(
                    DISABLE_RE.search(text),
                    f"{name}.rb has a `disable!` stanza — the tap is "
                    f"actively released; disabling installs must be an "
                    f"explicit, reviewed decision, not a codegen artifact",
                )

    def test_no_patch_block(self):
        # Nothing in the GoReleaser codegen path should ever emit a
        # `patch do` block; a stray one indicates hand-editing that will
        # be clobbered on the next release, and would apply arbitrary
        # source patches to a pre-built binary tarball anyway.
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                self.assertIsNone(
                    PATCH_BLOCK_RE.search(text),
                    f"{name}.rb has a `patch do` block — pre-built-binary "
                    f"formulae have no source to patch; the block is a "
                    f"hand-edit that will be clobbered next release",
                )

    def test_no_option_stanza(self):
        # `option "..."` is a deprecated Homebrew feature that
        # `brew audit --strict` flags. A codegen template regression
        # that leaks one in would fail audit on the tap.
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                self.assertIsNone(
                    OPTION_RE.search(text),
                    f"{name}.rb has an `option \"...\"` stanza — options "
                    f"are deprecated by Homebrew and rejected by "
                    f"`brew audit --strict`",
                )


class InstallBodyInvariants(FormulaLoader):
    """Every install block must be exactly one line: bin.install "<name>"."""

    def test_install_body_is_single_bin_install_line(self):
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                bodies = [m.group("body") for m in DEFINE_INSTALL_RE.finditer(text)]
                self.assertEqual(
                    len(bodies), 4,
                    f"{name}.rb: expected 4 define_method(:install) blocks, "
                    f"got {len(bodies)}",
                )
                for i, body in enumerate(bodies):
                    lines = [ln for ln in body.splitlines() if ln.strip()]
                    self.assertEqual(
                        len(lines), 1,
                        f"{name}.rb: install block #{i+1} should contain "
                        f"exactly one non-blank line, got {len(lines)}: {lines!r}",
                    )
                    m = BIN_INSTALL_LINE_RE.match(lines[0])
                    self.assertIsNotNone(
                        m,
                        f"{name}.rb: install block #{i+1} should be exactly "
                        f'bin.install "<name>", got: {lines[0]!r}',
                    )
                    self.assertEqual(
                        m.group("name"), name,
                        f"{name}.rb: install block #{i+1} installs "
                        f"{m.group('name')!r}, expected {name!r}",
                    )


class FileTerminationInvariants(FormulaLoader):
    """Every formula must end with 'end\\n' — no trailing whitespace lines,
    no missing final newline, no content after the class-ending end."""

    def test_file_ends_with_end_and_single_newline(self):
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                self.assertTrue(
                    text.endswith("end\n"),
                    f"{name}.rb does not end with 'end\\n' — either a "
                    f"trailing newline is missing or extra content follows "
                    f"the class-ending end",
                )
                # No trailing blank/whitespace-only line before the final end.
                self.assertFalse(
                    text.endswith("\n\n"),
                    f"{name}.rb has a trailing blank line after the class "
                    f"end — GoReleaser emits exactly one final newline",
                )

    def test_no_trailing_whitespace_on_any_line(self):
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                offenders = [
                    (i + 1, ln)
                    for i, ln in enumerate(text.splitlines())
                    if ln != ln.rstrip()
                ]
                self.assertFalse(
                    offenders,
                    f"{name}.rb has trailing whitespace on line(s): "
                    f"{[i for i, _ in offenders]}",
                )


if __name__ == "__main__":
    unittest.main()
