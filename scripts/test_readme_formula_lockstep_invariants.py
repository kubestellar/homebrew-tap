"""
README ↔ Formula/ lockstep invariants.

The tap's ``README.md`` doubles as user-facing install documentation:

  * The **Installation** section prints one ``brew install <name>`` line
    per formula the tap ships.
  * The **Formula status** table names every formula and marks it either
    "✅ Available" (shipped from ``Formula/<name>.rb``) or
    "❌ Not planned" (documented explicitly so users don't file the same
    "why isn't <foo> in the tap?" question over and over).

Nothing in the existing ``scripts/`` suite guards the README against
drifting out of sync with ``Formula/``:

  * A silently-added formula (e.g. GoReleaser starts emitting a fourth
    binary) would ship with no ``brew install`` example, so users would
    never discover it.
  * A silently-removed formula (e.g. one of the current three gets
    dropped from GoReleaser) would leave stale, non-working
    ``brew install <foo>`` instructions in the README.
  * A rename would break both directions at once.
  * An "❌ Not planned" row for a name that *does* ship as a real
    formula file would actively mislead users.

The invariants below are pure text scans of the checked-in
``Formula/`` and ``README.md`` — no network, no ``brew`` execution.
"""
from __future__ import annotations

import pathlib
import re
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
FORMULA_DIR = REPO_ROOT / "Formula"
README_PATH = REPO_ROOT / "README.md"

# Match `brew install <name>` where <name> is a bare formula (no tap
# prefix, no path). We ignore lines like `brew tap kubestellar/tap`
# and negative examples such as `brew install kubestellar/tap/foo` —
# the latter is explicitly documented as "not planned" and is not a
# real install instruction.
BREW_INSTALL_LINE_RE = re.compile(
    r"^\s*brew\s+install\s+([A-Za-z0-9][A-Za-z0-9._+\-\s]*?)\s*$",
    re.MULTILINE,
)

# `| \`<name>\` | ✅ Available | ...` — Available rows in the status table.
STATUS_AVAILABLE_ROW_RE = re.compile(
    r"^\s*\|\s*`([^`]+)`\s*\|\s*✅\s*Available\b.*$",
    re.MULTILINE,
)

# `| \`<name>\` | ❌ Not planned | ...` — explicit not-planned rows.
STATUS_NOT_PLANNED_ROW_RE = re.compile(
    r"^\s*\|\s*`([^`]+)`\s*\|\s*❌\s*Not planned\b.*$",
    re.MULTILINE,
)


def _formula_names() -> list[str]:
    return sorted(p.stem for p in FORMULA_DIR.glob("*.rb"))


def _brew_install_names(readme_text: str) -> list[str]:
    """Return every bare formula name mentioned in a ``brew install ...`` line.

    A single line may install multiple formulae:
        ``brew install kubestellar-ops kubestellar-deploy``
    We split on whitespace so each name is checked individually.
    """
    names: list[str] = []
    for match in BREW_INSTALL_LINE_RE.finditer(readme_text):
        for tok in match.group(1).split():
            # Skip tap-qualified installs like `kubestellar/tap/foo` —
            # those are always the "not planned" negative-example form
            # and MUST NOT be interpreted as a real install target.
            if "/" in tok:
                continue
            names.append(tok)
    return names


class TestReadmeFormulaLockstep(unittest.TestCase):
    """README.md must document every real formula and only real formulae."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.readme = README_PATH.read_text(encoding="utf-8")
        cls.formulae = _formula_names()
        cls.assertTrue = unittest.TestCase().assertTrue  # for static tooling

    def test_readme_exists_and_is_nonempty(self):
        # Trip-wire so a truncated / missing README doesn't cause every
        # downstream regex assertion to spuriously "pass" via empty input.
        self.assertTrue(README_PATH.is_file(), "README.md is missing")
        self.assertGreater(
            len(self.readme.strip()), 0, "README.md is empty"
        )

    def test_readme_contains_at_least_one_brew_install_line(self):
        # Anchors the regex — if a future edit rewrites the install
        # section in a way that stops matching, every subsequent
        # lockstep assertion would trivially pass. Fail loudly instead.
        names = _brew_install_names(self.readme)
        self.assertGreater(
            len(names), 0,
            "README.md has no `brew install <name>` lines the "
            "BREW_INSTALL_LINE_RE recognises — the regex may need "
            "updating, or the install section was removed.",
        )

    def test_every_formula_file_has_a_brew_install_example(self):
        # Users who read the README and never `ls Formula/` should be
        # able to discover every tool the tap ships.
        installed = set(_brew_install_names(self.readme))
        missing = [name for name in self.formulae if name not in installed]
        self.assertEqual(
            missing, [],
            f"Formula(e) with no `brew install <name>` example in "
            f"README.md: {missing}. Add an install line so users can "
            f"discover the tool.",
        )

    def test_every_brew_install_line_points_at_a_real_formula(self):
        # A stale `brew install <foo>` line that no longer corresponds
        # to a Formula/<foo>.rb file gives users a broken install command.
        formulae = set(self.formulae)
        offenders = [
            name
            for name in _brew_install_names(self.readme)
            if name not in formulae
        ]
        self.assertEqual(
            offenders, [],
            f"README.md advertises `brew install <name>` for formulae "
            f"that don't exist in Formula/: {sorted(set(offenders))}. "
            f"Either add the formula or remove the stale install line.",
        )

    def test_every_formula_has_an_available_status_row(self):
        # The "Formula status" table must acknowledge every shipped
        # formula as ✅ Available. A missing row means we shipped a
        # tool the status table doesn't know about.
        rows = set(STATUS_AVAILABLE_ROW_RE.findall(self.readme))
        missing = [name for name in self.formulae if name not in rows]
        self.assertEqual(
            missing, [],
            f"Formula(e) with no ✅ Available row in the README "
            f"Formula-status table: {missing}. Add a row so the table "
            f"stays exhaustive.",
        )

    def test_available_status_rows_map_to_real_formulae(self):
        # A ✅ Available row for a name that doesn't correspond to a
        # real Formula/<name>.rb misleads users into `brew install`ing
        # something that doesn't exist.
        formulae = set(self.formulae)
        offenders = [
            name
            for name in STATUS_AVAILABLE_ROW_RE.findall(self.readme)
            if name not in formulae
        ]
        self.assertEqual(
            offenders, [],
            f"README Formula-status table marks these as ✅ Available "
            f"but they have no Formula/<name>.rb file: "
            f"{sorted(set(offenders))}",
        )

    def test_not_planned_status_rows_are_not_real_formulae(self):
        # An "❌ Not planned" row for a name that actually ships as a
        # formula is a documentation lie — it tells users the tool
        # isn't available while the tap in fact installs it.
        formulae = set(self.formulae)
        offenders = [
            name
            for name in STATUS_NOT_PLANNED_ROW_RE.findall(self.readme)
            if name in formulae
        ]
        self.assertEqual(
            offenders, [],
            f"README Formula-status table marks these as ❌ Not planned "
            f"but Formula/<name>.rb DOES exist: "
            f"{sorted(set(offenders))}. Flip the row to ✅ Available "
            f"or remove the formula.",
        )


if __name__ == "__main__":
    unittest.main()
