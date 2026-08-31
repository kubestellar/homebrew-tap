"""
Source-file hygiene invariants for the generated Homebrew formulae.

The existing suites cover semantic and structural properties of every
formula (magic comments, class name / filename mapping, per-platform
URL/sha256 shape, forbidden stanzas, cross-formula lockstep, etc.).

They do NOT cover the low-level BYTE-LEVEL hygiene of the emitted
source files:

  * **Placeholder tokens leaking from templates.** A GoReleaser template
    or partial regen that ships an unrendered ``TODO`` / ``FIXME`` /
    ``XXX`` / ``TBD`` inside a formula would parse as a bare Ruby
    constant lookup at load time and crash ``brew install``. It would
    also be an obvious sign that a codegen step half-finished. Nothing
    in the current suite scans for those tokens.

  * **UTF-8 byte-order mark.** Ruby's ``# frozen_string_literal: true``
    magic comment only takes effect when it is the FIRST line of the
    file. A stray U+FEFF prepended by a Windows editor pushes the magic
    comment to logical line 2, silently disabling the frozen-string
    semantics tap-wide. The existing
    ``test_magic_comments_lead_every_formula`` compares against the
    stripped text and would not catch a BOM.

  * **CRLF line endings.** Homebrew rubocop rejects CRLF, and any
    subsequent regeneration on a Unix host would produce a diff purely
    from line-ending churn. The existing
    ``test_no_trailing_whitespace_on_any_line`` treats ``\\r`` as
    non-whitespace (``.rstrip`` strips it), so a full-file CRLF drift
    would pass that check silently.

  * **Non-ASCII bytes.** Every current formula is pure 7-bit ASCII.
    A stray smart-quote or non-breaking space introduced by an editor
    would still parse under Ruby (since the file has no ``# encoding``
    pragma and defaults to UTF-8), but would silently break naive
    string comparisons in downstream tooling. Locking to ASCII catches
    the smart-quote drift up front.

All four invariants pass on the current tap; they exist to prevent
silent regression from codegen template changes or editor churn.
"""

from __future__ import annotations

import pathlib
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
FORMULA_DIR = REPO_ROOT / "Formula"

# Tokens that indicate an unrendered template or an in-progress edit.
# Match the whole word only (case-insensitive) so it does not fire on
# innocuous substrings inside a URL or sha256 hex digest.
PLACEHOLDER_TOKENS = ("TODO", "FIXME", "XXX", "TBD")

UTF8_BOM = b"\xef\xbb\xbf"


def _formula_files() -> list[pathlib.Path]:
    files = sorted(FORMULA_DIR.glob("*.rb"))
    if not files:
        raise AssertionError(f"no formulae found under {FORMULA_DIR}")
    return files


class FormulaSourceHygieneInvariants(unittest.TestCase):
    def test_no_placeholder_tokens(self):
        # Whole-word case-insensitive scan. If GoReleaser ever ships a
        # formula with an unrendered TODO/FIXME/XXX/TBD, `brew install`
        # will fail at load time with `NameError: uninitialized
        # constant TODO`. Catch it before it lands.
        import re

        for path in _formula_files():
            text = path.read_text(encoding="utf-8")
            for token in PLACEHOLDER_TOKENS:
                pattern = re.compile(rf"\b{token}\b", re.IGNORECASE)
                with self.subTest(formula=path.stem, token=token):
                    self.assertIsNone(
                        pattern.search(text),
                        f"{path.name} contains placeholder token "
                        f"{token!r} (likely an unrendered template "
                        f"fragment)",
                    )

    def test_no_utf8_byte_order_mark(self):
        # A BOM prepended to the file shifts the `# typed: false`
        # magic comment off line 1, silently disabling Sorbet's
        # typed-false directive. The existing magic-comment test
        # reads via `str.splitlines()` and would not see the BOM.
        for path in _formula_files():
            with self.subTest(formula=path.stem):
                head = path.read_bytes()[: len(UTF8_BOM)]
                self.assertNotEqual(
                    head, UTF8_BOM,
                    f"{path.name} starts with a UTF-8 BOM "
                    f"(hex {head.hex()}); Ruby magic comments require "
                    f"no leading BOM",
                )

    def test_no_crlf_line_endings(self):
        # Homebrew rubocop rejects CRLF. `test_no_trailing_whitespace_on_any_line`
        # uses `.rstrip()` which strips `\r` — a full-file CRLF drift
        # would pass that check silently. Scan the raw bytes here.
        for path in _formula_files():
            with self.subTest(formula=path.stem):
                raw = path.read_bytes()
                self.assertNotIn(
                    b"\r\n", raw,
                    f"{path.name} contains CRLF line endings; formulas "
                    f"must be LF-only (Homebrew rubocop policy)",
                )
                self.assertNotIn(
                    b"\r", raw,
                    f"{path.name} contains a bare CR byte; formulas "
                    f"must be LF-only",
                )

    def test_all_bytes_are_ascii(self):
        # Every current formula is pure 7-bit ASCII. A smart-quote or
        # non-breaking space from a copy-paste would parse under Ruby
        # (files default to UTF-8) but silently break naive string
        # comparisons in downstream tooling. Lock to ASCII up front.
        for path in _formula_files():
            with self.subTest(formula=path.stem):
                raw = path.read_bytes()
                offenders = [
                    (i, b) for i, b in enumerate(raw) if b > 0x7F
                ]
                self.assertFalse(
                    offenders,
                    f"{path.name} contains non-ASCII bytes at "
                    f"offsets {[(off, hex(b)) for off, b in offenders[:5]]}"
                    f"{' ...' if len(offenders) > 5 else ''}",
                )


if __name__ == "__main__":
    unittest.main()
