#!/usr/bin/env python3
"""Structural invariants for the `bin.install` and `define_method(:install)`
stanzas in Formula/*.rb.

Existing tests already assert (see scripts/test_formula_structure.py and
test_formula_codegen_invariants.py):

  * `test_each_formula_installs_matching_binary` — every formula has
    exactly 4 lines of the form `bin.install "<formula-stem>"` (one per
    hardware slot).
  * `test_install_block_uses_define_method_form` — every formula has
    exactly 4 `define_method(:install)` blocks, and does not use the
    top-level `install do` form.

Those two checks together lock down the *matching* install lines and the
*number* of define-method arms, but they do NOT catch two adjacent
regression classes:

  * **Stray `bin.install` lines that install some OTHER binary.**
    `test_each_formula_installs_matching_binary` searches for
    `bin.install "<formula-stem>"` and expects the count to be 4. A
    codegen leak or copy-paste that emits an *extra* line such as
    `bin.install "kubectl"` inside the same arm still leaves 4 matches
    of the stem (so the existing count passes), while silently
    installing a stray binary onto every user's `$HOMEBREW_PREFIX/bin/`
    on every install.
  * **`bin.install` lines that live OUTSIDE the four
    `define_method(:install)` arms.** The existing tests never look at
    where the `bin.install` line sits — a stray `bin.install`
    accidentally placed at class scope, or inside the `test do` block,
    would still be caught by the count check on the primary line but a
    *second, mislocated* line would slip through. A `bin.install`
    inside `test do` in particular would cause `brew test` (which the
    Homebrew CI sandbox runs on every downstream machine) to try to
    write into `HOMEBREW_PREFIX/bin` and fail with a permission /
    sandbox error.

We lock both invariants here.

Runnable the same way as the sibling test modules:

    python3 scripts/test_formula_bin_install_locality_invariants.py
"""
from __future__ import annotations

import pathlib
import re
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
FORMULA_DIR = REPO_ROOT / "Formula"

# `bin.install "<name>"` — capture the binary-name argument. A GoReleaser
# emit is always the double-quoted single-string form; we deliberately do
# not match the array form `bin.install ["a", "b"]` because none of these
# formulae ship more than one binary and a switch to the array form would
# itself be a regression this test should catch.
BIN_INSTALL_RE = re.compile(r'\bbin\.install\s+"([^"]+)"')

# The four `define_method(:install) do ... end` blocks, one per hardware
# slot. We capture the block body so we can check that every `bin.install`
# line lives inside one of these blocks.
DEFINE_METHOD_BLOCK_RE = re.compile(
    r"define_method\(:install\)\s+do\s*\n(?P<body>.*?)\n\s*end\b",
    re.DOTALL,
)

# `test do ... end` — used to prove no `bin.install` line has drifted
# into the test block. The closing `end` is matched non-greedily so we
# stop at the first one after the `test do` header (all three formulae
# ship a single-line body followed by a plain `end`).
TEST_BLOCK_RE = re.compile(
    r"^\s*test\s+do\s*\n(?P<body>.*?)\n\s*end\s*$",
    re.DOTALL | re.MULTILINE,
)


def _load_formulae():
    files = sorted(FORMULA_DIR.glob("*.rb"))
    assert files, f"no formulae found under {FORMULA_DIR}"
    return {p.stem: p.read_text(encoding="utf-8") for p in files}


class BinInstallLocalityInvariants(unittest.TestCase):
    """Every `bin.install` line targets the formula's own binary and sits
    inside a `define_method(:install)` arm — never at class scope,
    never inside `test do`, never with a stray extra name."""

    @classmethod
    def setUpClass(cls):
        cls.formulae = _load_formulae()

    def test_every_bin_install_target_equals_the_formula_stem(self):
        # `test_each_formula_installs_matching_binary` counts matching
        # lines but does not forbid *extra* lines that install some
        # other binary. A codegen leak of e.g.
        #     bin.install "kubestellar-deploy"
        #     bin.install "kubectl"          # stray!
        # would leave the matching count at 4 while silently shipping
        # `kubectl` into every user's `$HOMEBREW_PREFIX/bin/`. Assert
        # that every single `bin.install "<...>"` line names the
        # formula's own stem — no exceptions.
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                targets = BIN_INSTALL_RE.findall(text)
                self.assertTrue(
                    targets,
                    f"{name}.rb: no `bin.install \"...\"` lines found",
                )
                strays = [t for t in targets if t != name]
                self.assertEqual(
                    strays, [],
                    f"{name}.rb has `bin.install` line(s) that install a "
                    f"non-formula-stem binary — codegen leak of a stray "
                    f"binary would ship it onto every user's system: "
                    f"strays={strays!r}, expected all == {name!r}",
                )

    def test_total_bin_install_line_count_is_exactly_four(self):
        # Even if every target matches the formula stem, the *count*
        # must be exactly 4 (one per hardware slot). The existing
        # `test_each_formula_installs_matching_binary` uses the same
        # 4-count, but only for the matching-stem regex; here we lock
        # the TOTAL bin.install count so a codegen bug that emits a 5th
        # matching-stem line (e.g. duplicated on the linux-arm64 arm)
        # is also caught.
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                targets = BIN_INSTALL_RE.findall(text)
                self.assertEqual(
                    len(targets), 4,
                    f"{name}.rb: total `bin.install` line count must be "
                    f"exactly 4 (one per hardware slot), got "
                    f"{len(targets)}: {targets!r}",
                )

    def test_every_bin_install_line_lives_inside_a_define_method_arm(self):
        # A `bin.install` line at class scope or in some other block
        # would still install at brew-install time but would fire on
        # *every* platform (bypassing the per-arch tarball selection)
        # — an obvious codegen regression. Prove every bin.install
        # line's file position sits inside one of the four
        # `define_method(:install) do ... end` bodies.
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                # Collect all define_method block byte-spans.
                arm_spans = [
                    (m.start("body"), m.end("body"))
                    for m in DEFINE_METHOD_BLOCK_RE.finditer(text)
                ]
                self.assertEqual(
                    len(arm_spans), 4,
                    f"{name}.rb: expected 4 define_method(:install) "
                    f"blocks, got {len(arm_spans)} — dependent "
                    f"invariants below cannot run",
                )
                for m in BIN_INSTALL_RE.finditer(text):
                    pos = m.start()
                    inside = any(lo <= pos < hi for lo, hi in arm_spans)
                    self.assertTrue(
                        inside,
                        f"{name}.rb: `bin.install \"{m.group(1)}\"` at "
                        f"byte offset {pos} lives OUTSIDE every "
                        f"`define_method(:install) do ... end` block — "
                        f"would install on every platform / at wrong "
                        f"lifecycle hook",
                    )

    def test_test_do_block_contains_no_bin_install(self):
        # `brew test` runs `test do` in a sandbox that does NOT permit
        # writing into `$HOMEBREW_PREFIX/bin/`. A `bin.install` line
        # accidentally emitted inside `test do` would parse fine at
        # audit time but fail loudly on every downstream `brew test`
        # invocation. Prove the test block has no bin.install line.
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                test_match = TEST_BLOCK_RE.search(text)
                self.assertIsNotNone(
                    test_match,
                    f"{name}.rb: no `test do` block — the sibling "
                    f"metadata invariants cover this; noting it here so "
                    f"a regression is loud in both places",
                )
                body = test_match.group("body")
                self.assertIsNone(
                    BIN_INSTALL_RE.search(body),
                    f"{name}.rb: `test do` body contains a `bin.install` "
                    f"line — `brew test` sandbox rejects writes to "
                    f"$HOMEBREW_PREFIX/bin; would break `brew test` on "
                    f"every downstream machine. Body: {body!r}",
                )


if __name__ == "__main__":
    unittest.main()
