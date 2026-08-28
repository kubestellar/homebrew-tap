#!/usr/bin/env python3
"""Additional codegen-drift invariants for Formula/*.rb.

test_formula_structure.py checks that each formula covers the four
platforms, has distinct sha256s, installs the right binary, declares
required metadata, and shares a single license. This module guards
against a different class of drift — subtle changes to the *shape* of
the generated Ruby that would silently pass brew audit but signal a
regression in the GoReleaser template:

  * Every formula opens with the same magic comments (`# typed: false`
    and `# frozen_string_literal: true`) — losing them changes Sorbet
    and string-literal semantics tap-wide.
  * The Ruby class name is exactly the CamelCase transform of the
    filename stem (`kc-agent.rb` -> `KcAgent`). A rename that updates
    the file but not the class would produce a formula Homebrew loads
    but cannot install.
  * Every formula subclasses `Formula` directly.
  * The declared `version` string appears verbatim in every one of the
    four release URLs (i.e., the URLs were not templated from a stale
    variable while `version` was bumped).
  * Every URL is HTTPS on github.com (never http, never a mirror host).
  * Every `sha256` digest is 64 lowercase hex chars (already implicit
    in the existing distinctness test, made explicit here so a codegen
    bug emitting uppercase digests fails loudly).
  * Every formula uses `define_method(:install)` inside the `if
    Hardware::CPU.*` block, not the top-level `install do` form —
    consistent shape means grep-based tooling downstream stays sound.

Runnable the same way as the sibling test module:

    python3 scripts/test_formula_codegen_invariants.py
"""

import re
import unittest
from pathlib import Path

FORMULA_DIR = Path(__file__).resolve().parent.parent / "Formula"

MAGIC_COMMENTS = (
    "# typed: false",
    "# frozen_string_literal: true",
)

URL_LINE_RE = re.compile(r'url\s+"([^"]+)"')
SHA256_LINE_RE = re.compile(r'sha256\s+"([^"]+)"')
CLASS_LINE_RE = re.compile(r'^\s*class\s+(\w+)\s*<\s*(\w+)', re.MULTILINE)
VERSION_LINE_RE = re.compile(r'^\s*version\s+"([^"]+)"', re.MULTILINE)


def _load_formulae():
    files = sorted(FORMULA_DIR.glob("*.rb"))
    if not files:
        raise AssertionError(f"no formulae found under {FORMULA_DIR}")
    return {p.stem: p.read_text() for p in files}


def _to_camel(stem: str) -> str:
    return "".join(part.capitalize() for part in stem.split("-"))


class FormulaCodegenInvariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.formulae = _load_formulae()

    def test_magic_comments_lead_every_formula(self):
        # The first two non-blank lines of every formula must be the
        # sigil comments emitted by the GoReleaser template. Dropping
        # them silently changes Sorbet type-checking and string
        # semantics tap-wide.
        for name, text in self.formulae.items():
            non_blank = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
            self.assertGreaterEqual(
                len(non_blank), 2,
                f"{name}.rb has fewer than two non-blank lines",
            )
            self.assertEqual(
                tuple(non_blank[:2]), MAGIC_COMMENTS,
                f"{name}.rb does not begin with the expected magic comments: "
                f"{non_blank[:2]!r}",
            )

    def test_class_name_matches_filename_and_extends_formula(self):
        # A stale codegen that updates the filename but not the class
        # name would still parse under Homebrew, but `brew install`
        # would fail with a "class not found" error. Assert the exact
        # CamelCase mapping and that the parent class is always the
        # Homebrew Formula base type.
        for name, text in self.formulae.items():
            m = CLASS_LINE_RE.search(text)
            self.assertIsNotNone(m, f"{name}.rb has no `class ... < Formula`")
            klass, parent = m.group(1), m.group(2)
            self.assertEqual(
                klass, _to_camel(name),
                f"{name}.rb declares class {klass!r}, expected "
                f"{_to_camel(name)!r}",
            )
            self.assertEqual(
                parent, "Formula",
                f"{name}.rb declares parent class {parent!r}, expected Formula",
            )

    def test_declared_version_appears_in_every_release_url(self):
        # If the codegen bumps `version` but leaves the URL literals
        # stale (or vice-versa), brew will fetch the wrong tarball and
        # the checksum will fail on install. Assert the exact version
        # string is embedded in every one of the four URLs.
        for name, text in self.formulae.items():
            vm = VERSION_LINE_RE.search(text)
            self.assertIsNotNone(vm, f"{name}.rb missing version line")
            version = vm.group(1)
            self.assertTrue(
                version, f"{name}.rb has an empty version string"
            )
            urls = URL_LINE_RE.findall(text)
            self.assertEqual(
                len(urls), 4,
                f"{name}.rb should declare exactly 4 URLs, got {len(urls)}",
            )
            for url in urls:
                self.assertIn(
                    version, url,
                    f"{name}.rb URL {url!r} does not embed declared version "
                    f"{version!r}",
                )

    def test_all_release_urls_are_https_github_com(self):
        # Homebrew accepts non-HTTPS URLs but a codegen regression that
        # switches to plain http (or a mirror host) would degrade
        # security for every tap user simultaneously. Pin the scheme
        # and host explicitly.
        for name, text in self.formulae.items():
            urls = URL_LINE_RE.findall(text)
            for url in urls:
                self.assertTrue(
                    url.startswith("https://github.com/"),
                    f"{name}.rb URL {url!r} must start with "
                    f"https://github.com/",
                )

    def test_every_sha256_is_lowercase_64_hex(self):
        # The existing structure test asserts the four digests inside
        # one formula differ, but says nothing about their shape. Make
        # the invariant explicit so a codegen change that emits
        # uppercase or truncated digests fails loudly rather than
        # letting brew reject them at install time.
        pattern = re.compile(r"^[0-9a-f]{64}$")
        for name, text in self.formulae.items():
            digests = SHA256_LINE_RE.findall(text)
            self.assertEqual(
                len(digests), 4,
                f"{name}.rb should declare exactly 4 sha256 digests, "
                f"got {len(digests)}",
            )
            for digest in digests:
                self.assertRegex(
                    digest, pattern,
                    f"{name}.rb sha256 {digest!r} is not 64 lowercase hex "
                    f"characters",
                )

    def test_install_block_uses_define_method_form(self):
        # The GoReleaser template consistently emits
        # `define_method(:install) do ... end` inside each per-arch
        # branch (rather than the top-level `install do ... end`
        # form). Downstream tooling that greps the tap for install
        # steps relies on this shape; if the template ever regresses
        # to the plain form the tap still works but breaks that
        # tooling. Assert the drift here.
        for name, text in self.formulae.items():
            self.assertIn(
                "define_method(:install)", text,
                f"{name}.rb does not use the expected "
                "`define_method(:install)` form",
            )
            # And there should be exactly one per platform slot: 4.
            self.assertEqual(
                text.count("define_method(:install)"), 4,
                f"{name}.rb should have 4 `define_method(:install)` blocks "
                f"(one per platform), got "
                f"{text.count('define_method(:install)')}",
            )


if __name__ == "__main__":
    unittest.main()
