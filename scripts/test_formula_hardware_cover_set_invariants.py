#!/usr/bin/env python3
"""Cover-set invariant for Formula/*.rb Hardware::CPU branches.

Existing structural tests verify:

  * exactly 4 (on_os, if Hardware::CPU) blocks per formula
    (test_every_url_sits_in_matching_os_and_arch_block, in
    test_formula_structural_further_invariants.py);
  * every URL sits inside a block whose declared os/arch match its own
    tarball basename tokens.

Neither test independently asserts that the SET of (os, arch) combos
covered by the four blocks is exactly

    {(macos, intel), (macos, arm), (linux, intel), (linux, arm)}.

A codegen bug that emitted, say, TWO ``if Hardware::CPU.arm?`` guards
inside ``on_macos`` (and zero intel-arm guards inside ``on_linux``) would
still ship four blocks and — depending on which URLs also drifted — could
still satisfy the URL/block cross-check when it looks up URLs by their
tarball tokens. Users on x86 Linux would then either get NO tap install
path at all, or worse, silently fall through to the wrong tarball.

This test locks the cover set down explicitly. It is the smallest
statement of "the tap supports amd64 + arm64 on both macOS and Linux."
"""

import re
import unittest
from pathlib import Path

FORMULA_DIR = Path(__file__).resolve().parent.parent / "Formula"

# Same regex shape as the sibling structural tests use (see
# test_formula_structural_further_invariants.py) so both files agree on
# what an "on_os block" and an "if Hardware::CPU" block look like.
_ON_OS_BLOCK_RE = re.compile(
    r'^  on_(?P<os>macos|linux)\s+do\b(?P<body>[\s\S]*?)^  end\s*$',
    re.MULTILINE,
)
_IF_HW_BLOCK_RE = re.compile(
    r'^    if Hardware::CPU\.(?P<primary>intel|arm)\?'
    r'(?:\s+&&\s+Hardware::CPU\.[^\n]*)?'
    r'\s*\n(?P<body>[\s\S]*?)^    end\s*$',
    re.MULTILINE,
)

EXPECTED_COVER_SET = frozenset(
    [
        ("macos", "intel"),
        ("macos", "arm"),
        ("linux", "intel"),
        ("linux", "arm"),
    ]
)


def _guard_pairs(text: str) -> list[tuple[str, str]]:
    """Return the (on_os, primary_arch) pair for every Hardware::CPU
    guard, in source order."""
    pairs: list[tuple[str, str]] = []
    for os_match in _ON_OS_BLOCK_RE.finditer(text):
        os_name = os_match.group("os")
        body = os_match.group("body")
        for arch_match in _IF_HW_BLOCK_RE.finditer(body):
            pairs.append((os_name, arch_match.group("primary")))
    return pairs


class HardwareGuardCoverSetInvariants(unittest.TestCase):
    """Every Formula covers the full four-way (os, arch) cover set exactly."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.formula_files = sorted(FORMULA_DIR.glob("*.rb"))
        assert cls.formula_files, f"no Formula/*.rb under {FORMULA_DIR}"

    def test_each_formula_covers_the_expected_four_way_platform_set_exactly(self):
        # The tap is a pre-built-binary tap for the four Homebrew targets
        # actually shipped by KubeStellar releases. Any deviation — a
        # missing combo (users on that platform silently lose the install
        # path) or a duplicate combo (one URL wins, the other is dead
        # code) — must fail loudly at test time, not at brew-install time
        # on a contributor's laptop.
        for f in self.formula_files:
            with self.subTest(formula=f.name):
                pairs = _guard_pairs(f.read_text())
                self.assertEqual(
                    len(pairs), 4,
                    f"{f.name}: expected 4 Hardware::CPU guards, got {len(pairs)}: {pairs}",
                )
                self.assertEqual(
                    frozenset(pairs), EXPECTED_COVER_SET,
                    f"{f.name}: (on_os, Hardware::CPU) cover set is "
                    f"{sorted(frozenset(pairs))}, expected "
                    f"{sorted(EXPECTED_COVER_SET)}",
                )
                # Duplicate detection: a duplicate combo would coincide
                # with a missing combo (since len == 4 and the frozenset
                # check would already fail), but making it explicit keeps
                # the failure message readable.
                self.assertEqual(
                    len(pairs), len(set(pairs)),
                    f"{f.name}: duplicate Hardware::CPU guard combo(s) "
                    f"in source order: {pairs}",
                )

    def test_guard_pairs_helper_ignores_stray_hardware_cpu_calls_outside_on_os_blocks(self):
        # Regression guard on the helper itself: any Hardware::CPU
        # reference that lives OUTSIDE an on_macos/on_linux block (for
        # instance, in a stray top-level `if Hardware::CPU.arm?` guard a
        # future refactor might introduce) must be ignored by
        # _guard_pairs — only guards inside a platform block count
        # toward the cover set.
        synthetic = (
            "class Foo < Formula\n"
            "  version \"1.0.0\"\n"
            "  # A rogue top-level guard that should NOT be counted.\n"
            "  if Hardware::CPU.arm?\n"
            "    puts \"noise\"\n"
            "  end\n"
            "  on_macos do\n"
            "    if Hardware::CPU.intel?\n"
            "      url \"x\"\n"
            "    end\n"
            "    if Hardware::CPU.arm?\n"
            "      url \"y\"\n"
            "    end\n"
            "  end\n"
            "  on_linux do\n"
            "    if Hardware::CPU.intel? && Hardware::CPU.is_64_bit?\n"
            "      url \"z\"\n"
            "    end\n"
            "    if Hardware::CPU.arm? && Hardware::CPU.is_64_bit?\n"
            "      url \"w\"\n"
            "    end\n"
            "  end\n"
            "end\n"
        )
        pairs = _guard_pairs(synthetic)
        # Exactly four inside-block guards, no stray sixth entry from
        # the top-level `if Hardware::CPU.arm?`.
        self.assertEqual(
            frozenset(pairs), EXPECTED_COVER_SET,
            f"cover set drift on synthetic fixture: {pairs}",
        )
        self.assertEqual(len(pairs), 4, f"expected 4 pairs, got {pairs}")


if __name__ == "__main__":
    unittest.main()
