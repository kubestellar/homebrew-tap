#!/usr/bin/env python3
"""Cross-formula invariants that complement the per-file checks in
test_formula_structure.py and test_formula_codegen_invariants.py.

The existing suites verify each `.rb` file in isolation. This module
guards against three classes of drift that only surface when comparing
formulae to each other or comparing a URL to the block it lives in:

  * All 12 sha256 digests across the tap (3 formulae × 4 platforms)
    must be globally unique. Per-formula distinctness is already
    tested; a codegen bug that copy-pastes a digest from a sibling
    formula would slip past that check.

  * Each release URL's platform tuple must match the on_macos /
    on_linux block it lives in *and* the surrounding
    `Hardware::CPU.intel?` / `arm?` branch — i.e. a URL inside
    on_macos + intel must end with `_darwin_amd64.tar.gz`, not
    `_linux_amd64.tar.gz`. A shuffle bug in the template would
    silently ship the wrong tarball for a platform.

  * `kubestellar-ops` and `kubestellar-deploy` release from the same
    kubestellar-mcp binary set and must share a single `version`
    string. This lockstep is enforced by scripts/validate_formulae.py
    at CI time; making it a direct pytest invariant means a
    developer running `pytest scripts/` locally sees the same
    failure without going through the validator entrypoint.

Runnable the same way as the sibling test modules:

    python3 scripts/test_crossformula_invariants.py
"""

import re
import unittest
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

FORMULA_DIR = Path(__file__).resolve().parent.parent / "Formula"

URL_RE = re.compile(r'url\s+"([^"]+)"')
SHA256_RE = re.compile(r'sha256\s+"([^"]+)"')
VERSION_RE = re.compile(r'^\s*version\s+"([^"]+)"', re.MULTILINE)


def _load_formulae():
    files = sorted(FORMULA_DIR.glob("*.rb"))
    if not files:
        raise AssertionError(f"no formulae found under {FORMULA_DIR}")
    return {p.stem: p.read_text() for p in files}


def _platform_slots(text):
    """Yield (os, arch, url) triples in the order they appear in the
    Ruby source. os is 'macos'/'linux' from the surrounding on_* block;
    arch is 'amd64'/'arm64' from the surrounding Hardware::CPU branch.
    """
    current_os = None
    current_arch = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("on_macos"):
            current_os = "macos"
            continue
        if line.startswith("on_linux"):
            current_os = "linux"
            continue
        if "Hardware::CPU.intel?" in line:
            current_arch = "amd64"
            continue
        if "Hardware::CPU.arm?" in line:
            current_arch = "arm64"
            continue
        m = URL_RE.search(line)
        if m and current_os and current_arch:
            yield current_os, current_arch, m.group(1)


class CrossFormulaInvariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.formulae = _load_formulae()

    def test_all_sha256_digests_are_globally_unique(self):
        # Per-formula distinctness is already asserted in
        # test_each_formula_has_four_distinct_sha256_values. This is
        # the tap-wide analogue: 3 formulae × 4 platform slots = 12
        # digests, and all 12 must be distinct. A copy-paste from a
        # sibling formula would slip past the per-file test but is
        # still a drift bug.
        digests = []
        for name, text in self.formulae.items():
            digests.extend((name, d) for d in SHA256_RE.findall(text))
        self.assertEqual(
            len(digests), 12,
            f"expected 12 sha256 lines across the tap, got {len(digests)}: "
            f"{digests}",
        )
        just_digests = [d for _, d in digests]
        counts = Counter(just_digests)
        dupes = {d: c for d, c in counts.items() if c > 1}
        self.assertFalse(
            dupes,
            f"duplicate sha256 digests across formulae: {dupes}. "
            f"Owning formulae: "
            f"{[(n, d) for n, d in digests if d in dupes]}",
        )

    def test_url_platform_tuple_matches_surrounding_block(self):
        # Every url line lives inside on_macos + Hardware::CPU.intel?
        # (etc). The URL's own basename encodes the platform tuple as
        # <name>_<version>_<os>_<arch>.tar.gz. A codegen shuffle bug
        # that placed the darwin_arm64 URL inside the on_linux + intel
        # branch would install the wrong tarball on that host. This
        # test cross-checks both.
        for name, text in self.formulae.items():
            slots = list(_platform_slots(text))
            with self.subTest(formula=name):
                self.assertEqual(
                    len(slots), 4,
                    f"{name}.rb: expected 4 url slots wrapped in "
                    f"on_* + Hardware::CPU.* blocks, got {len(slots)}: "
                    f"{slots}",
                )
                seen = set()
                for os_name, arch, url in slots:
                    basename = url.rsplit("/", 1)[-1]
                    expected_os = "darwin" if os_name == "macos" else "linux"
                    self.assertTrue(
                        basename.endswith(f"_{expected_os}_{arch}.tar.gz"),
                        f"{name}.rb: url {basename!r} inside on_{os_name} "
                        f"+ {arch} block does not end with "
                        f"'_{expected_os}_{arch}.tar.gz'",
                    )
                    seen.add((os_name, arch))
                self.assertEqual(
                    seen,
                    {("macos", "amd64"), ("macos", "arm64"),
                     ("linux", "amd64"), ("linux", "arm64")},
                    f"{name}.rb: url slots do not cover all four platforms "
                    f"exactly once: {seen}",
                )

    def test_ops_and_deploy_share_a_single_version(self):
        # kubestellar-ops and kubestellar-deploy release from the same
        # kubestellar-mcp binary set. scripts/validate_formulae.py's
        # LOCKSTEP_GROUPS enforces this at CI time; assert the same
        # invariant directly so a lone `pytest scripts/` run catches
        # the drift.
        #
        # Nightly-cut tolerance: the upstream release pipeline bumps the two
        # formulae in separate commits, creating a ~10-15 min window where the
        # nightly.YYYYMMDD suffix differs by exactly one day. We allow that
        # narrow gap (both must be nightly versions, base semver must match,
        # and the date gap must be exactly 1 day) so that CI does not go red
        # every night during the rollover window. Any other mismatch still
        # fails hard.
        need = {"kubestellar-ops", "kubestellar-deploy"}
        available = need & set(self.formulae)
        self.assertEqual(
            available, need,
            f"expected both lockstep formulae to exist, missing: "
            f"{need - available}",
        )
        versions = {}
        for stem in sorted(available):
            m = VERSION_RE.search(self.formulae[stem])
            self.assertIsNotNone(
                m, f"{stem}.rb: no version line found",
            )
            versions[stem] = m.group(1)
        distinct = set(versions.values())
        if len(distinct) == 1:
            return  # identical — always passes

        # Versions differ; check for the permitted one-day nightly drift.
        nightly_re = re.compile(
            r'^(?P<base>.+)-nightly\.(?P<yyyymmdd>\d{8})$'
        )
        parsed = {}
        for stem, ver in versions.items():
            m = nightly_re.match(ver)
            if m is None:
                # Not a nightly version — any mismatch is a hard failure.
                self.fail(
                    f"kubestellar-ops and kubestellar-deploy must share the "
                    f"same version (they release from a single kubestellar-mcp "
                    f"binary set); got {versions}",
                )
            parsed[stem] = (m.group("base"), m.group("yyyymmdd"))

        stems = sorted(parsed)
        base_a, date_a = parsed[stems[0]]
        base_b, date_b = parsed[stems[1]]

        self.assertEqual(
            base_a, base_b,
            f"kubestellar-ops and kubestellar-deploy nightly base versions "
            f"differ (expected identical semver prefix); got {versions}",
        )

        day_a = date(int(date_a[:4]), int(date_a[4:6]), int(date_a[6:8]))
        day_b = date(int(date_b[:4]), int(date_b[4:6]), int(date_b[6:8]))
        gap = abs((day_b - day_a).days)
        self.assertEqual(
            gap, 1,
            f"kubestellar-ops and kubestellar-deploy nightly versions differ "
            f"by {gap} day(s); only a one-day gap during the nightly rollover "
            f"window is tolerated; got {versions}",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
