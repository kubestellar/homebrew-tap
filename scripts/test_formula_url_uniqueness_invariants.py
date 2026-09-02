#!/usr/bin/env python3
"""URL uniqueness invariants for Formula/*.rb.

Existing tests already assert (see ``test_validate_formulae.py``):

  * ``test_sha256_values_unique_within_each_formula`` — no two ``sha256``
    lines in the same formula share a value **when their URLs differ**.

That check catches the symmetric copy-paste bug of "different URL, same
sha256", but it leaves the mirror bug uncovered: **same URL, different
sha256s**. If a codegen regression or manual copy-paste duplicates a
``url`` line between two hardware arms while the sha256 blocks continue
to be regenerated independently, the four sha256 values remain distinct,
so ``test_sha256_values_unique_within_each_formula`` passes silently —
but ``brew install`` would download the same tarball for two different
arches, verify it against the checksum of whichever arm brew happens to
select first, and then install the wrong binary onto users' machines
whose real arch was never actually served.

We also lock the cross-formula variant: no two distinct formulae in the
tap may point ``url`` at the exact same release tarball. Existing
cross-formula checks assert sha256 uniqueness (12 URLs → 12 sha256s)
and platform-tuple ↔ block position, but do not assert distinctness of
the URL strings themselves. A GoReleaser matrix regression could emit
the same ``kubestellar-ops`` tarball URL under both ``kubestellar-ops.rb``
*and* ``kubestellar-deploy.rb``; the sha256s would still be identical
(caught elsewhere), but the URL duplication itself is the earliest and
clearest signal, and worth locking directly.

Run:

    python3 scripts/test_formula_url_uniqueness_invariants.py
"""
from __future__ import annotations

import pathlib
import re
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
FORMULA_DIR = REPO_ROOT / "Formula"

URL_RE = re.compile(r'^\s*url\s+"([^"]+)"', re.MULTILINE)


class TestFormulaURLUniqueness(unittest.TestCase):
    """Within a single formula, every ``url`` string must be distinct."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.formula_files = sorted(FORMULA_DIR.glob("*.rb"))
        if not cls.formula_files:
            raise unittest.SkipTest(f"no .rb files in {FORMULA_DIR}")

    def test_urls_within_each_formula_are_distinct(self):
        offenders = []
        for f in self.formula_files:
            urls = URL_RE.findall(f.read_text())
            if len(urls) != len(set(urls)):
                seen: dict[str, int] = {}
                for u in urls:
                    seen[u] = seen.get(u, 0) + 1
                dups = {u: n for u, n in seen.items() if n > 1}
                offenders.append((f.name, dups))
        self.assertEqual(
            offenders, [],
            msg=(
                "Formula(e) list the same release URL under more than one "
                "hardware arm. Even if the sha256 blocks were regenerated "
                "independently (so the existing sha uniqueness test passes), "
                "brew will download the same tarball for two different arches "
                "and install the wrong binary on the arch that was never "
                f"actually served. Offenders: {offenders}"
            ),
        )

    def test_each_formula_declares_expected_number_of_urls(self):
        # Guardrail so a regression that drops URL lines doesn't make the
        # uniqueness check trivially pass on a 1-element set.
        for f in self.formula_files:
            with self.subTest(formula=f.name):
                urls = URL_RE.findall(f.read_text())
                self.assertEqual(
                    len(urls), 4,
                    msg=(
                        f"{f.name}: expected 4 url lines (one per hardware "
                        f"slot: macOS×{{intel,arm}}, Linux×{{intel,arm}}), "
                        f"found {len(urls)}. Uniqueness assertions in this "
                        "module assume the full 4-URL matrix."
                    ),
                )


class TestFormulaURLCrossFormulaUniqueness(unittest.TestCase):
    """Across all formulae in the tap, every ``url`` must be distinct."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.formula_files = sorted(FORMULA_DIR.glob("*.rb"))
        if len(cls.formula_files) < 2:
            raise unittest.SkipTest(
                f"cross-formula check needs >=2 formulae; found "
                f"{len(cls.formula_files)} in {FORMULA_DIR}"
            )

    def test_no_url_is_shared_across_formulae(self):
        origin: dict[str, list[str]] = {}
        for f in self.formula_files:
            for url in URL_RE.findall(f.read_text()):
                origin.setdefault(url, []).append(f.name)
        shared = {u: fs for u, fs in origin.items() if len(set(fs)) > 1}
        self.assertEqual(
            shared, {},
            msg=(
                "The same release URL appears in more than one formula in "
                "the tap. Even though a separate cross-formula sha256 "
                "uniqueness check would eventually catch this, the URL "
                "duplication itself is a clearer, earlier signal of a "
                "GoReleaser matrix or copy-paste regression that would "
                "cause two `brew install` targets to fetch the same "
                f"artifact. Shared URLs → formulae: {shared}"
            ),
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
