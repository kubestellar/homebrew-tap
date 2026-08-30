"""
Metadata invariants complementing test_formula_release_artifact_invariants.py
and test_validate_formulae.py.

The existing suites cover:

  * ``desc`` capitalization and trailing punctuation
    (test_formula_release_artifact_invariants.py::
       test_desc_starts_with_capital_letter /
       test_desc_does_not_end_with_period)
  * ``desc`` and ``license`` presence
    (test_validate_formulae.py::TestFormulaClassAndMetadataPolicy)
  * ``class <Name> < Formula`` matches the PascalCased filename
    (test_validate_formulae.py::
       TestFormulaClassAndMetadataPolicy::test_class_name_matches_filename)

They do NOT cover:

  * ``desc`` length. ``brew audit --strict`` rejects any formula whose
    ``desc`` exceeds 80 characters. A slightly-too-long description ships
    from GoReleaser and every existing test passes; the audit only fails
    when the tap is submitted upstream.

  * ``license`` value lockstep. Every formula presently carries
    ``license "Apache-2.0"``. Someone regenerating one formula from a
    template that says ``MIT`` or ``Apache-2.0 OR MIT`` would drift the
    tap silently — legally significant, tap-wide policy.

  * ``class ... < Formula`` COUNT. ``test_class_name_matches_filename``
    finds the FIRST match; a stray duplicate class block (from a bad
    merge or partial regen) is silently accepted. ``brew`` would load
    the last one; the first one becomes unreachable dead code that
    silently ships wrong shas/urls to nobody.

Every check here is a pure text scan of the checked-in Formula/ tree; no
network, no ``brew`` execution.
"""
from __future__ import annotations

import pathlib
import re
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
FORMULA_DIR = REPO_ROOT / "Formula"

DESC_LINE_RE = re.compile(r'^\s*desc\s+"([^"]+)"', re.MULTILINE)
LICENSE_LINE_RE = re.compile(r'^\s*license\s+"([^"]+)"', re.MULTILINE)
CLASS_HEADER_RE = re.compile(
    r'^\s*class\s+[A-Za-z0-9_]+\s*<\s*Formula\b', re.MULTILINE
)

# brew audit --strict rejects formulae whose desc exceeds 80 characters.
# See: https://docs.brew.sh/Formula-Cookbook#formulae-and-desc
BREW_AUDIT_DESC_MAX_LEN = 80


def _formulae():
    files = sorted(FORMULA_DIR.glob("*.rb"))
    assert files, f"no formulae discovered under {FORMULA_DIR}"
    return files


class TestFormulaDescLength(unittest.TestCase):
    """`brew audit --strict` upper bound on `desc` length."""

    def test_every_formula_desc_is_at_most_80_characters(self):
        offenders = []
        for f in _formulae():
            m = DESC_LINE_RE.search(f.read_text())
            self.assertIsNotNone(m, f"{f.name}: no desc line")
            desc = m.group(1)
            if len(desc) > BREW_AUDIT_DESC_MAX_LEN:
                offenders.append((f.name, len(desc), desc))
        self.assertEqual(
            offenders,
            [],
            msg=(
                "Formula(e) with `desc` exceeding brew audit's "
                f"{BREW_AUDIT_DESC_MAX_LEN}-char limit (each entry: "
                f"(file, length, text)): {offenders}"
            ),
        )


class TestFormulaLicenseLockstep(unittest.TestCase):
    """Every formula in the tap must ship the same license string."""

    def test_all_formulae_declare_the_same_license(self):
        licenses = {}
        for f in _formulae():
            m = LICENSE_LINE_RE.search(f.read_text())
            self.assertIsNotNone(m, f"{f.name}: no license line")
            licenses[f.name] = m.group(1)
        unique = set(licenses.values())
        self.assertEqual(
            len(unique),
            1,
            msg=(
                "Formula(e) declare more than one license value — the "
                "tap should be lockstep on a single license: "
                f"{licenses}"
            ),
        )

    def test_declared_license_is_apache_2_0(self):
        # The tap has historically shipped as Apache-2.0. Pin the value
        # so a template drift to `MIT` or `Apache-2.0 OR MIT` is caught
        # in CI, not by a legal review months later.
        for f in _formulae():
            m = LICENSE_LINE_RE.search(f.read_text())
            self.assertIsNotNone(m, f"{f.name}: no license line")
            self.assertEqual(
                m.group(1),
                "Apache-2.0",
                msg=(
                    f"{f.name}: license={m.group(1)!r}, expected "
                    "'Apache-2.0' (bump this test intentionally if the "
                    "tap-wide license changes)"
                ),
            )


class TestFormulaClassHeaderExactlyOnce(unittest.TestCase):
    """Guard against duplicate `class <Name> < Formula` headers.

    The existing `test_class_name_matches_filename` uses a plain
    `re.search()` — it finds the FIRST match and stops. A stray second
    header (from a bad merge or a partial regen) is silently accepted;
    `brew` then loads the LAST class definition and the first becomes
    dead code whose shas/urls are never used but always shipped.
    """

    def test_each_formula_has_exactly_one_class_formula_header(self):
        offenders = []
        for f in _formulae():
            matches = CLASS_HEADER_RE.findall(f.read_text())
            if len(matches) != 1:
                offenders.append((f.name, len(matches)))
        self.assertEqual(
            offenders,
            [],
            msg=(
                "Formula(e) with a `class <Name> < Formula` count "
                f"other than 1: {offenders}"
            ),
        )


if __name__ == "__main__":
    unittest.main()
