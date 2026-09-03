#!/usr/bin/env python3
"""Platform URL policy, arch/sha copy-paste guards, and version-token
boundary guards across Formula/*.rb.

Split from test_validate_formulae.py (classes moved verbatim).
"""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from formula_test_fixtures import FORMULA_DIR

class TestFormulaPlatformURLPolicy(unittest.TestCase):
    """Cross-formula copy-paste guards on every Formula/*.rb.

    The drift checker enforces that a formula's `url` embeds its own
    `version` string, but it does NOT check that:

      * every formula ships both an `on_macos` and an `on_linux` block
        (a GoReleaser regression that drops one whole platform would
        leave the tap silently broken on that OS),
      * a URL inside an `on_macos` block actually points at a darwin
        artifact (and same for linux),
      * a formula's URLs actually reference that formula's own tarball
        stem (a copy-paste of, say, a `kc-agent_*.tar.gz` URL into
        `kubestellar-ops.rb` would pass every existing check because
        the version string still matches).

    These are the three failure modes most likely to slip past a
    version-only drift audit, so we assert them here on real files.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.formula_files = sorted(FORMULA_DIR.glob("*.rb"))
        if not cls.formula_files:
            raise unittest.SkipTest(f"no .rb files in {FORMULA_DIR}")

    def test_every_formula_has_both_macos_and_linux_blocks(self):
        # Homebrew supports macOS and Linux. Every formula in this
        # tap ships binaries for both today; a regression that drops
        # one platform should be caught here, not by an end-user
        # `brew install` failing on their laptop.
        missing = []
        for f in self.formula_files:
            body = f.read_text()
            has_macos = bool(re.search(r'^\s*on_macos\s+do\b', body, re.MULTILINE))
            has_linux = bool(re.search(r'^\s*on_linux\s+do\b', body, re.MULTILINE))
            if not (has_macos and has_linux):
                missing.append((f.name, {"macos": has_macos, "linux": has_linux}))
        self.assertEqual(
            missing, [],
            msg=(
                "Formula(e) missing an on_macos/on_linux block. If a "
                "formula is intentionally single-platform, exclude it "
                "from this test explicitly. Offenders: " + repr(missing)
            ),
        )

    def test_url_platform_token_matches_enclosing_block(self):
        # Walk each formula line by line, track whether we're inside
        # an `on_macos do` or `on_linux do` block, and require that
        # each `url` inside those blocks embeds the matching platform
        # token (`darwin` for macOS, `linux` for Linux). This is the
        # single most likely copy-paste bug: a darwin tarball URL
        # accidentally landing in the on_linux branch. `sha256`
        # comparison alone can't catch it because the sha of the
        # darwin artifact IS a valid 64-hex sha.
        offenders = []
        for f in self.formula_files:
            lines = f.read_text().splitlines()
            # depth counters: nesting inside on_macos / on_linux
            in_macos = 0
            in_linux = 0
            # We don't fully parse Ruby; we just track `on_macos do`
            # / `on_linux do` opens and end-of-block closes by
            # matching indentation of the paired `end`. Homebrew
            # formula style keeps these top-level with consistent
            # indent, so this simple heuristic is sufficient for the
            # tap's actual files.
            block_stack: list[str] = []
            for line in lines:
                stripped = line.strip()
                if re.match(r'^on_macos\s+do\b', stripped):
                    block_stack.append("macos")
                    in_macos += 1
                    continue
                if re.match(r'^on_linux\s+do\b', stripped):
                    block_stack.append("linux")
                    in_linux += 1
                    continue
                # A top-level `end` (2-space indent) closes an
                # on_macos/on_linux block. Inner `end`s (for `if`,
                # `define_method`) sit at deeper indent.
                if stripped == "end" and re.match(r'^  end\s*$', line):
                    if block_stack:
                        closed = block_stack.pop()
                        if closed == "macos":
                            in_macos -= 1
                        else:
                            in_linux -= 1
                    continue

                url_match = re.match(r'^\s*url\s+"([^"]+)"', line)
                if not url_match:
                    continue
                url = url_match.group(1)
                if in_macos > 0 and "darwin" not in url:
                    offenders.append((f.name, "on_macos", url))
                if in_linux > 0 and "linux" not in url:
                    offenders.append((f.name, "on_linux", url))
        self.assertEqual(
            offenders, [],
            msg=(
                "url() inside on_macos must contain 'darwin' and "
                "url() inside on_linux must contain 'linux'. This "
                "test guards against a copy-paste where a URL for "
                "one platform lands in the other platform's block "
                "— the sha256 would still be a valid 64-hex string "
                "but `brew install` would download the wrong "
                "binary. Offenders: " + repr(offenders)
            ),
        )

    def test_url_filename_references_formula_stem(self):
        # GoReleaser names artifacts `<binary>_<version>_<os>_<arch>.tar.gz`.
        # A formula's URL filename must therefore reference that
        # formula's own binary name — i.e. its file stem, with
        # dashes/underscores treated as equivalent (GoReleaser
        # replaces `-` with `_` in some templates and not others).
        # Without this check, a PR that copy-pastes a `kc-agent`
        # release URL into `kubestellar-ops.rb` would pass every
        # existing test provided the version strings match.
        offenders = []
        for f in self.formula_files:
            body = f.read_text()
            stem = f.stem  # e.g. "kc-agent"
            # Accept either the exact stem or its `_`-normalized form
            # in the URL's tarball basename (last path segment).
            variants = {stem, stem.replace("-", "_"), stem.replace("_", "-")}
            for m in re.finditer(r'^\s*url\s+"([^"]+)"', body, re.MULTILINE):
                url = m.group(1)
                basename = url.rsplit("/", 1)[-1]
                if not any(v in basename for v in variants):
                    offenders.append((f.name, url, sorted(variants)))
        self.assertEqual(
            offenders, [],
            msg=(
                "Formula URL tarball basename must reference the "
                "formula's own stem (dashes/underscores equivalent). "
                "This catches copy-paste of one formula's release "
                "URL into another formula. Offenders: " + repr(offenders)
            ),
        )


class TestFormulaArchAndShaCopyPasteGuards(unittest.TestCase):
    """Additional cross-formula copy-paste guards on Formula/*.rb.

    Two failure modes not caught by any existing policy test:

      * A GoReleaser template regression (or manual copy-paste) that
        leaves the same URL — and therefore the same sha256 — under
        two different arch branches. Version and platform tokens
        would still match, but the arm64 shelf would silently install
        the amd64 binary (or vice versa).
      * Duplicate sha256 values across different URLs inside a single
        formula: a strong signal that two artifacts were accidentally
        pointed at the same tarball. sha256 collisions between
        genuinely different binaries are cryptographically negligible,
        so duplicates in real files are always mistakes.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.formula_files = sorted(FORMULA_DIR.glob("*.rb"))
        if not cls.formula_files:
            raise unittest.SkipTest(f"no .rb files in {FORMULA_DIR}")

    def _iter_arch_scoped_urls(self, body: str):
        """Yield (arch_token_expected, url) for each url() inside a
        Hardware::CPU.intel?/arm? branch of an on_macos/on_linux block.

        Uses the same line-by-line stack heuristic as
        TestFormulaPlatformURLPolicy: it is deliberately shallow
        because homebrew formula style is regular, and it is verified
        by the mutation tests below.
        """
        block_stack: list[str] = []  # tracks on_macos/on_linux + arch
        arch: str | None = None
        for line in body.splitlines():
            stripped = line.strip()
            if re.match(r"^on_macos\s+do\b", stripped) or re.match(
                r"^on_linux\s+do\b", stripped
            ):
                block_stack.append("platform")
                continue
            # `if Hardware::CPU.intel?` or `if Hardware::CPU.arm?`
            m = re.match(r"^if\s+Hardware::CPU\.(intel|arm)\?", stripped)
            if m:
                arch = "amd64" if m.group(1) == "intel" else "arm64"
                block_stack.append("arch")
                continue
            # A generic `if ... do`-less `if` opens a block too; catch
            # any other `if ` at deeper indent so our stack stays sane.
            if re.match(r"^if\b", stripped):
                block_stack.append("other")
                continue
            if stripped == "end":
                if block_stack:
                    kind = block_stack.pop()
                    if kind == "arch":
                        arch = None
                continue
            url_match = re.match(r'^\s*url\s+"([^"]+)"', line)
            if url_match and arch is not None:
                yield arch, url_match.group(1)

    def test_url_arch_token_matches_hardware_cpu_branch(self):
        # Inside `if Hardware::CPU.intel?` the URL must reference an
        # `amd64` artifact; inside `if Hardware::CPU.arm?` it must
        # reference `arm64`. This catches the specific copy-paste
        # where an arm64 URL is dropped into the intel branch (or
        # vice versa) — the platform token stays correct so
        # TestFormulaPlatformURLPolicy wouldn't fire.
        offenders = []
        for f in self.formula_files:
            for expected_arch, url in self._iter_arch_scoped_urls(f.read_text()):
                other = "arm64" if expected_arch == "amd64" else "amd64"
                if expected_arch not in url or other in url:
                    offenders.append((f.name, expected_arch, url))
        self.assertEqual(
            offenders,
            [],
            msg=(
                "url() inside `if Hardware::CPU.intel?` must contain "
                "'amd64'; inside `Hardware::CPU.arm?` must contain "
                "'arm64'. Guards against copy-paste of an arch URL "
                "into the wrong CPU branch. Offenders: " + repr(offenders)
            ),
        )

    def test_url_arch_check_would_fire_on_swapped_arch_token(self):
        # Meta-check: prove the arch guard actually catches a swap.
        # Take one real formula, flip 'amd64' -> 'arm64' in an
        # intel-branch URL, and verify the same policy rejects it.
        real = None
        for f in self.formula_files:
            for expected_arch, url in self._iter_arch_scoped_urls(f.read_text()):
                if expected_arch == "amd64" and "amd64" in url:
                    real = (f, url)
                    break
            if real:
                break
        if real is None:
            self.skipTest("no amd64-tagged intel-branch URL to mutate")
        f, orig_url = real
        mutated = f.read_text().replace(orig_url, orig_url.replace("amd64", "arm64"), 1)
        offenders_after_mutation = []
        for expected_arch, url in self._iter_arch_scoped_urls(mutated):
            other = "arm64" if expected_arch == "amd64" else "amd64"
            if expected_arch not in url or other in url:
                offenders_after_mutation.append((f.name, expected_arch, url))
        self.assertTrue(
            offenders_after_mutation,
            msg=(
                "Arch guard failed to catch a synthetic amd64→arm64 "
                "swap in an intel branch of "
                f"{f.name}; the guard is a no-op and would let a "
                "real regression through."
            ),
        )

    def test_sha256_values_are_unique_within_each_formula(self):
        # A goreleaser template regression that emits the same URL
        # under two arch/platform branches would also emit the same
        # sha256. sha256 collisions between distinct real binaries
        # are cryptographically impossible, so any duplicate within a
        # single formula is a copy-paste bug.
        dup_offenders = []
        for f in self.formula_files:
            body = f.read_text()
            shas = re.findall(r'^\s*sha256\s+"([0-9a-f]{64})"', body, re.MULTILINE)
            seen: dict[str, int] = {}
            for s in shas:
                seen[s] = seen.get(s, 0) + 1
            dups = {s: n for s, n in seen.items() if n > 1}
            if dups:
                dup_offenders.append((f.name, dups))
        self.assertEqual(
            dup_offenders,
            [],
            msg=(
                "Each sha256 in a formula must be unique — duplicates "
                "mean two branches point at the same tarball, which is "
                "always a mistake. Offenders: " + repr(dup_offenders)
            ),
        )

    def test_sha256_values_are_lowercase_64_hex(self):
        # Homebrew accepts uppercase hex but goreleaser and the wider
        # ecosystem emit lowercase. Enforce lowercase-64-hex here so
        # a diff that normalises casing (or accidentally truncates)
        # is caught before merge.
        offenders = []
        for f in self.formula_files:
            body = f.read_text()
            for line_no, line in enumerate(body.splitlines(), start=1):
                m = re.match(r'^\s*sha256\s+"([^"]+)"', line)
                if not m:
                    continue
                value = m.group(1)
                if not re.fullmatch(r"[0-9a-f]{64}", value):
                    offenders.append((f.name, line_no, value))
        self.assertEqual(
            offenders,
            [],
            msg=(
                "sha256 values must be exactly 64 lowercase hex "
                "characters. Offenders: " + repr(offenders)
            ),
        )


class TestFormulaVersionTokenBoundaryGuards(unittest.TestCase):
    """Partial-version-bump copy-paste guard on Formula/*.rb.

    validate_formulae.parse_formula enforces that the top-level
    ``version "X"`` substring appears somewhere in each url. Because
    that check uses a bare ``in`` substring test, a partial bump
    would silently pass — e.g. formula ``version "0.3.4"`` with a
    URL containing ``v0.3.44/`` (bumped by hand) satisfies
    ``"0.3.4" in url`` even though the URL and the declared version
    disagree.

    These tests upgrade the check to boundary-token form. Every url
    inside every formula must contain BOTH:

      * ``v<VERSION>/`` — the version as a distinct path segment
        (release tag directory), not a prefix
      * ``_<VERSION>_`` — the version wrapped by underscore
        delimiters inside the tarball filename, so a shorter
        version string can't match a longer one

    The mutation test below verifies that flipping either delimiter
    off actually causes the guard to fire, so the guard cannot
    silently rot into a no-op.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.formula_files = sorted(FORMULA_DIR.glob("*.rb"))
        if not cls.formula_files:
            raise unittest.SkipTest(f"no .rb files in {FORMULA_DIR}")

    @staticmethod
    def _extract_version(body: str) -> str | None:
        m = re.search(r'^\s*version\s+"([^"]+)"', body, re.MULTILINE)
        return m.group(1) if m else None

    def _iter_urls(self, body: str):
        for m in re.finditer(r'url\s+"([^"]+)"', body):
            yield m.group(1)

    def test_url_contains_version_path_segment(self):
        offenders = []
        for f in self.formula_files:
            body = f.read_text()
            v = self._extract_version(body)
            self.assertIsNotNone(v, f"{f.name} has no version declaration")
            seg = f"v{v}/"
            for url in self._iter_urls(body):
                if seg not in url:
                    offenders.append((f.name, seg, url))
        self.assertFalse(
            offenders,
            "url missing 'v<VERSION>/' path segment (partial-bump "
            f"drift?): {offenders}",
        )

    def test_url_contains_version_filename_token(self):
        offenders = []
        for f in self.formula_files:
            body = f.read_text()
            v = self._extract_version(body)
            self.assertIsNotNone(v, f"{f.name} has no version declaration")
            tok = f"_{v}_"
            for url in self._iter_urls(body):
                if tok not in url:
                    offenders.append((f.name, tok, url))
        self.assertFalse(
            offenders,
            "url missing '_<VERSION>_' filename token (partial-bump "
            f"drift?): {offenders}",
        )

    def test_boundary_guard_catches_partial_bump_mutation(self):
        # Meta-test: prove the guard actually distinguishes a partial
        # bump from an exact one. Take a real formula, replace one
        # url so the version segment becomes v<VERSION>4/ (i.e. the
        # declared version is a proper prefix of the URL version).
        # The bare ``version in url`` check would still pass; the
        # boundary-token check must NOT.
        sample = self.formula_files[0].read_text()
        v = self._extract_version(sample)
        self.assertIsNotNone(v)
        good_seg = f"v{v}/"
        bad_seg = f"v{v}4/"

        self.assertIn(good_seg, sample, "sample formula must contain the "
                      "canonical version segment for this test to be valid")

        mutated = sample.replace(good_seg, bad_seg, 1)
        # The bare substring check would still hold: v<VERSION> is a
        # prefix of v<VERSION>4. Confirm that so the meta-test proves
        # the boundary is what saves us.
        self.assertIn(f"v{v}", mutated,
                      "prefix substring must still be present in mutant")
        # The boundary check MUST catch it.
        urls_in_mutant = list(re.finditer(r'url\s+"([^"]+)"', mutated))
        offenders = [u.group(1) for u in urls_in_mutant if good_seg not in u.group(1)]
        self.assertTrue(
            offenders,
            "boundary-token guard failed to detect a partial-bump "
            "mutation; the guard has degraded to a no-op",
        )



if __name__ == "__main__":
    unittest.main()
