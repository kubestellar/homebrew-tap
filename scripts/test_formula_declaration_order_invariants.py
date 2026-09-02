#!/usr/bin/env python3
"""Top-level stanza ordering invariants for Formula/*.rb.

The individual stanzas (``desc``, ``homepage``, ``version``, ``license``,
``on_macos``, ``on_linux``, ``test do``) are each already checked for
existence and singleton status by other test modules. What no existing
test module locks in is their *relative textual order* — the sequence
in which they appear inside the ``class ... < Formula`` body.

Homebrew does not require any particular order (``brew audit`` accepts
any of the many permutations), so a codegen refactor could easily
reshuffle the emitted stanzas and every existing invariant would still
pass. But the canonical shape emitted by GoReleaser is:

    class <Name> < Formula
      desc      "..."
      homepage  "..."
      version   "..."
      license   "..."

      on_macos do
        ...
      end

      on_linux do
        ...
      end

      test do
        ...
      end
    end

A shuffle (e.g. ``license`` before ``version``, or ``test do`` between
``on_macos`` and ``on_linux``) is a template-drift signal that produces
noisy no-op diffs on every future release and can mask real changes in
code review. This module makes that shuffle a hard failure.

Runnable the same way as the sibling test modules::

    python3 scripts/test_formula_declaration_order_invariants.py
"""

import re
import unittest
from pathlib import Path

FORMULA_DIR = Path(__file__).resolve().parent.parent / "Formula"

# The canonical top-level declaration order emitted by GoReleaser. Each
# entry is (label, regex-that-matches-the-first-occurrence-in-file).
# Regexes anchor to start-of-line + ``\s*`` so an indented occurrence
# still counts (Homebrew formulae are conventionally 2-space indented
# under the class header).
_STANZA_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("class",    re.compile(r'^\s*class\s+\S+\s+<\s+Formula\b',   re.MULTILINE)),
    ("desc",     re.compile(r'^\s*desc\s+"',                     re.MULTILINE)),
    ("homepage", re.compile(r'^\s*homepage\s+"',                 re.MULTILINE)),
    ("version",  re.compile(r'^\s*version\s+"',                  re.MULTILINE)),
    ("license",  re.compile(r'^\s*license\s+"',                  re.MULTILINE)),
    ("on_macos", re.compile(r'^\s*on_macos\s+do\b',              re.MULTILINE)),
    ("on_linux", re.compile(r'^\s*on_linux\s+do\b',              re.MULTILINE)),
    ("test",     re.compile(r'^\s*test\s+do\b',                  re.MULTILINE)),
]


class TopLevelStanzaOrderingInvariants(unittest.TestCase):
    """Every formula file lays out its top-level stanzas in the exact
    canonical order emitted by GoReleaser. A shuffle produces a noisy
    diff on every subsequent release and typically means the file was
    hand-edited outside the codegen path."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.formulae = sorted(FORMULA_DIR.glob("*.rb"))
        assert cls.formulae, f"no formulae discovered under {FORMULA_DIR}"

    def _first_offset(self, text: str, label: str, pat: re.Pattern[str]) -> int:
        m = pat.search(text)
        self.assertIsNotNone(
            m,
            f"stanza {label!r} not found in formula source; "
            f"other invariants should have caught this",
        )
        return m.start()

    def test_canonical_top_level_stanza_order(self):
        for f in self.formulae:
            text = f.read_text()
            with self.subTest(formula=f.name):
                offsets = [
                    (label, self._first_offset(text, label, pat))
                    for label, pat in _STANZA_PATTERNS
                ]
                # Order the observed labels by their file offset — this
                # is the sequence in which they actually appear.
                observed = [label for label, _ in sorted(offsets, key=lambda kv: kv[1])]
                expected = [label for label, _ in _STANZA_PATTERNS]
                self.assertEqual(
                    observed, expected,
                    f"{f.name}: top-level stanzas are out of canonical order.\n"
                    f"  expected: {expected}\n"
                    f"  observed: {observed}\n"
                    f"A codegen refactor that reshuffles stanzas will still "
                    f"pass every other invariant but produces noisy no-op "
                    f"diffs on every release and hides real changes in review."
                )

    def test_platform_blocks_precede_test_block(self):
        # Sanity narrowing of the ordering rule: the ``test do`` block
        # exercises the installed binary, so it must textually follow
        # both ``on_macos do`` and ``on_linux do``. This assertion is
        # implied by the canonical-order test above, but is spelled
        # out here so a future maintainer who touches the ordering test
        # can't silently drop this specific constraint without also
        # breaking a differently-named test.
        for f in self.formulae:
            text = f.read_text()
            with self.subTest(formula=f.name):
                on_macos = _STANZA_PATTERNS[5][1].search(text)
                on_linux = _STANZA_PATTERNS[6][1].search(text)
                test_do  = _STANZA_PATTERNS[7][1].search(text)
                for label, m in (("on_macos", on_macos), ("on_linux", on_linux), ("test do", test_do)):
                    self.assertIsNotNone(m, f"{f.name}: {label} not found")
                assert on_macos and on_linux and test_do  # for type checker
                self.assertLess(
                    on_macos.start(), test_do.start(),
                    f"{f.name}: on_macos block must appear before test do",
                )
                self.assertLess(
                    on_linux.start(), test_do.start(),
                    f"{f.name}: on_linux block must appear before test do",
                )
                self.assertLess(
                    on_macos.start(), on_linux.start(),
                    f"{f.name}: on_macos block must appear before on_linux",
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
