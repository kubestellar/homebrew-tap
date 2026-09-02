#!/usr/bin/env python3
"""Structural invariants that lock each platform arm's URL segment to its
enclosing hardware guard in Formula/*.rb.

Every formula in this tap ships four platform arms:

    on_macos do
      if Hardware::CPU.intel? ... url "..._darwin_amd64.tar.gz" ... end
      if Hardware::CPU.arm?   ... url "..._darwin_arm64.tar.gz" ... end
    end
    on_linux do
      if Hardware::CPU.intel? && Hardware::CPU.is_64_bit?
        ... url "..._linux_amd64.tar.gz" ... end
      if Hardware::CPU.arm?   && Hardware::CPU.is_64_bit?
        ... url "..._linux_arm64.tar.gz" ... end
    end

The existing tests prove that all four platform URL segments appear in
the file and that each sha256 is distinct, but they do NOT prove that
each URL segment sits under the CORRECT block. A codegen bug that
paste-swaps two urls (e.g. the `_darwin_arm64` URL under the
`if Hardware::CPU.arm? && Hardware::CPU.is_64_bit?` guard inside
`on_linux do`) leaves:

  * platform set {darwin_amd64, darwin_arm64, linux_amd64, linux_arm64}
    still complete (the darwin_arm64 URL is still in the file);
  * all four sha256 values still distinct;
  * `bin.install` still lists the right binary name.

Every existing structural test therefore passes, and only the users on
that specific platform notice — via a checksum mismatch at install
time — that something has drifted. These tests catch that drift at PR
review.

Invariants locked:

  1. Every url that contains `_darwin_` sits inside an `on_macos do`
     block (never inside `on_linux`), and vice versa for `_linux_`.

  2. Inside `on_macos`, the `_amd64` URL sits under the
     `Hardware::CPU.intel?` arm, and the `_arm64` URL sits under the
     `Hardware::CPU.arm?` arm.

  3. Inside `on_linux`, the `_amd64` URL sits under the
     `Hardware::CPU.intel? && Hardware::CPU.is_64_bit?` arm, and the
     `_arm64` URL sits under the `Hardware::CPU.arm? && Hardware::CPU.is_64_bit?`
     arm.

  4. The `sha256` line paired with each URL sits between that URL and
     the next `if`/`end` closer — i.e. every arm has its own url + sha256
     pair, never sharing a sha256 across arms via a stray placement.

Run:

    python3 scripts/test_formula_platform_arm_url_alignment_invariants.py
"""

import re
import unittest
from pathlib import Path

FORMULA_DIR = Path(__file__).resolve().parent.parent / "Formula"

ON_MACOS_START_RE = re.compile(r"^\s*on_macos\s+do\b")
ON_LINUX_START_RE = re.compile(r"^\s*on_linux\s+do\b")

# One `if Hardware::CPU.<something>? ... end` arm.
CPU_ARM_RE = re.compile(
    r"^\s*if\s+Hardware::CPU\.(?P<cpu>intel|arm)\?"
    r"(?P<guard_tail>[^\n]*)\n"
    r"(?P<body>.*?)\n\s*end\b",
    re.MULTILINE | re.DOTALL,
)

URL_RE = re.compile(r'url\s+"[^"]*_(?P<os>darwin|linux)_(?P<arch>amd64|arm64)\.tar\.gz"')
SHA256_RE = re.compile(r'sha256\s+"[0-9a-f]{64}"')


def _load_formulae():
    files = sorted(FORMULA_DIR.glob("*.rb"))
    if not files:
        raise AssertionError(f"no formulae under {FORMULA_DIR}")
    return {p.stem: p.read_text(encoding="utf-8") for p in files}


class PlatformArmAlignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.formulae = _load_formulae()

    def _extract_block(self, text: str, start_re):
        """Return the body of the first ``on_<x> do ... end`` block, using
        depth-tracked line scanning so nested ``do``/``if``/``end`` don't
        close the outer block prematurely."""
        lines = text.splitlines(keepends=True)
        i = 0
        while i < len(lines):
            if start_re.match(lines[i]):
                break
            i += 1
        if i >= len(lines):
            return None
        # We are on the `on_<x> do` line. Start scanning from the next line.
        body_lines = []
        depth = 1
        j = i + 1
        while j < len(lines):
            stripped = lines[j].strip()
            is_opener = (
                re.match(r"if\b", stripped) is not None
                or re.search(r"\bdo\b(\s*\|[^|]*\|)?\s*$", stripped) is not None
            )
            is_closer = stripped == "end"
            if is_closer:
                depth -= 1
                if depth == 0:
                    return "".join(body_lines)
                body_lines.append(lines[j])
            else:
                if is_opener:
                    depth += 1
                body_lines.append(lines[j])
            j += 1
        return None

    def _extract_arms(self, block_body: str):
        """Return list of (cpu, guard_tail, body) tuples for each `if
        Hardware::CPU.<cpu>? ... end` arm in the given block body.

        The arm body contains a nested `define_method(:install) do ... end`,
        so we must match the OUTER `end` (the second one). We walk the
        block line-by-line and track depth of any `do`/`if` opener.
        """
        arms = []
        lines = block_body.splitlines(keepends=True)
        current = None  # dict with cpu, guard_tail, body_lines
        depth = 0
        for line in lines:
            stripped = line.strip()
            if current is None:
                m = re.match(r"if\s+Hardware::CPU\.(intel|arm)\?(.*)$", stripped)
                if m:
                    current = {
                        "cpu": m.group(1),
                        "guard_tail": m.group(2),
                        "body_lines": [],
                    }
                    depth = 1
                continue
            # We are inside an arm.  Track openers/closers to find the
            # outer `end` — openers are `if `, `do`, or a trailing ` do`.
            is_opener = (
                re.match(r"if\b", stripped) is not None
                or re.search(r"\bdo\b(\s*\|[^|]*\|)?\s*$", stripped) is not None
            )
            is_closer = stripped == "end"
            if is_opener and not is_closer:
                depth += 1
                current["body_lines"].append(line)
            elif is_closer:
                depth -= 1
                if depth == 0:
                    arms.append(
                        (current["cpu"], current["guard_tail"], "".join(current["body_lines"]))
                    )
                    current = None
                else:
                    current["body_lines"].append(line)
            else:
                current["body_lines"].append(line)
        return arms

    def test_darwin_urls_live_only_under_on_macos(self):
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                mac_body = self._extract_block(text, ON_MACOS_START_RE)
                lin_body = self._extract_block(text, ON_LINUX_START_RE)
                self.assertIsNotNone(mac_body, f"{name}.rb: no on_macos block")
                self.assertIsNotNone(lin_body, f"{name}.rb: no on_linux block")
                mac_urls = URL_RE.findall(mac_body)
                lin_urls = URL_RE.findall(lin_body)
                for os_seg, arch in mac_urls:
                    self.assertEqual(
                        os_seg, "darwin",
                        f"{name}.rb: on_macos block contains a "
                        f"{os_seg!r} URL (_{os_seg}_{arch}). "
                        f"Only darwin URLs may live under on_macos.",
                    )
                for os_seg, arch in lin_urls:
                    self.assertEqual(
                        os_seg, "linux",
                        f"{name}.rb: on_linux block contains a "
                        f"{os_seg!r} URL (_{os_seg}_{arch}). "
                        f"Only linux URLs may live under on_linux.",
                    )

    def test_macos_intel_arm_carries_amd64_and_arm_arm_carries_arm64(self):
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                mac_body = self._extract_block(text, ON_MACOS_START_RE)
                self.assertIsNotNone(mac_body, f"{name}.rb: no on_macos block")
                arms = self._extract_arms(mac_body)
                self.assertEqual(
                    len(arms), 2,
                    f"{name}.rb: on_macos block must contain exactly "
                    f"2 CPU arms (intel, arm), got {len(arms)}",
                )
                by_cpu = {cpu: (guard_tail, body) for cpu, guard_tail, body in arms}
                self.assertIn("intel", by_cpu, f"{name}.rb: on_macos missing intel arm")
                self.assertIn("arm", by_cpu, f"{name}.rb: on_macos missing arm arm")

                intel_urls = URL_RE.findall(by_cpu["intel"][1])
                self.assertEqual(
                    intel_urls, [("darwin", "amd64")],
                    f"{name}.rb: on_macos intel arm URL(s) = {intel_urls!r}, "
                    f"expected exactly one _darwin_amd64 URL. "
                    f"A copy-paste swap that puts _darwin_arm64 here would "
                    f"ship an arm64 binary to Intel Macs.",
                )
                arm_urls = URL_RE.findall(by_cpu["arm"][1])
                self.assertEqual(
                    arm_urls, [("darwin", "arm64")],
                    f"{name}.rb: on_macos arm arm URL(s) = {arm_urls!r}, "
                    f"expected exactly one _darwin_arm64 URL.",
                )

    def test_linux_intel_arm_carries_amd64_and_arm_arm_carries_arm64(self):
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                lin_body = self._extract_block(text, ON_LINUX_START_RE)
                self.assertIsNotNone(lin_body, f"{name}.rb: no on_linux block")
                arms = self._extract_arms(lin_body)
                self.assertEqual(
                    len(arms), 2,
                    f"{name}.rb: on_linux block must contain exactly "
                    f"2 CPU arms (intel, arm), got {len(arms)}",
                )
                by_cpu = {cpu: (guard_tail, body) for cpu, guard_tail, body in arms}
                self.assertIn("intel", by_cpu, f"{name}.rb: on_linux missing intel arm")
                self.assertIn("arm", by_cpu, f"{name}.rb: on_linux missing arm arm")

                intel_urls = URL_RE.findall(by_cpu["intel"][1])
                self.assertEqual(
                    intel_urls, [("linux", "amd64")],
                    f"{name}.rb: on_linux intel arm URL(s) = {intel_urls!r}, "
                    f"expected exactly one _linux_amd64 URL.",
                )
                arm_urls = URL_RE.findall(by_cpu["arm"][1])
                self.assertEqual(
                    arm_urls, [("linux", "arm64")],
                    f"{name}.rb: on_linux arm arm URL(s) = {arm_urls!r}, "
                    f"expected exactly one _linux_arm64 URL. "
                    f"An arm64 tarball on the intel arm here would checksum "
                    f"mismatch every time a user installs on aarch64 Linux.",
                )
                # Belt-and-braces: linux guards MUST include is_64_bit?
                # (we do not publish 32-bit tarballs). The existing
                # test_formula_hardware_guard_invariants.py checks this
                # for the whole file; here we lock it PER ARM.
                for cpu, (guard_tail, _body) in by_cpu.items():
                    self.assertIn(
                        "Hardware::CPU.is_64_bit?", guard_tail,
                        f"{name}.rb: on_linux {cpu} arm guard "
                        f"{guard_tail!r} is missing "
                        f"`&& Hardware::CPU.is_64_bit?`. Without it "
                        f"32-bit Linux would try (and fail) to install "
                        f"the 64-bit tarball.",
                    )

    def test_every_arm_has_its_own_url_and_sha256_pair(self):
        # Each CPU arm inside on_macos / on_linux must contain exactly
        # one url and exactly one sha256 line — a stray sha256 outside
        # any arm (or two shas in one arm) would silently associate the
        # wrong checksum with a tarball.
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                for start_re, label in (
                    (ON_MACOS_START_RE, "on_macos"),
                    (ON_LINUX_START_RE, "on_linux"),
                ):
                    body = self._extract_block(text, start_re)
                    self.assertIsNotNone(body, f"{name}.rb: no {label} block")
                    arms = self._extract_arms(body)
                    for cpu, _guard_tail, body in arms:
                        urls = URL_RE.findall(body)
                        shas = SHA256_RE.findall(body)
                        self.assertEqual(
                            len(urls), 1,
                            f"{name}.rb: {label} {cpu} arm has "
                            f"{len(urls)} url lines, want 1",
                        )
                        self.assertEqual(
                            len(shas), 1,
                            f"{name}.rb: {label} {cpu} arm has "
                            f"{len(shas)} sha256 lines, want 1",
                        )


if __name__ == "__main__":
    unittest.main()
