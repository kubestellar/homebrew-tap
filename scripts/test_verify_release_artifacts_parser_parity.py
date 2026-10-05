#!/usr/bin/env python3
"""Parity test: the bash and Python owners of the "every per-arch release
branch's (url, sha256, bin_name) triple" extraction must agree on every
real Formula/*.rb.

scripts/verify_release_artifacts.sh's extract_triples() (bash) and
scripts/formula_parser.extract_release_triples() (Python) each
independently scan a formula body for `url "..."` / `sha256 "..."` /
`bin.install "..."` lines and pair them into triples. Until this module
nothing asserted the two agreed — a GoReleaser template change that one
side's regex/case-pattern was updated to handle, but not the other,
would silently desync them (see kubestellar/homebrew-tap#647). This
mirrors the existing bash/Python parity test for the CI-summary contract
(scripts/test_emit_summary_parity.py).

Runs scripts/verify_release_artifacts.sh --list (no network access; it
only extracts and prints, never downloads) over the real Formula/*.rb
tree and compares its output to formula_parser.extract_release_triples()
called directly.
"""

import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from formula_parser import extract_release_triples, load_formulae  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "verify_release_artifacts.sh"


class VerifyReleaseArtifactsParserParityTest(unittest.TestCase):
    def test_bash_and_python_extraction_agree_on_every_formula(self):
        formulae = load_formulae()

        proc = subprocess.run(
            ["bash", str(SCRIPT), "--list"],
            capture_output=True,
            text=True,
            check=True,
        )

        bash_by_name: dict[str, list[tuple[str, str, str]]] = {}
        for line in proc.stdout.splitlines():
            name, url, sha, bin_name = line.split("\t")
            bash_by_name.setdefault(name, []).append((url, sha, bin_name))

        for name, text in formulae.items():
            python_triples = extract_release_triples(text)
            with self.subTest(formula=name):
                self.assertEqual(
                    bash_by_name.get(name, []),
                    python_triples,
                    f"bash extract_triples() and Python "
                    f"extract_release_triples() disagree for {name}.rb",
                )

        self.assertEqual(
            set(bash_by_name),
            set(formulae),
            "verify_release_artifacts.sh --list and load_formulae() "
            "discovered a different set of formulae",
        )

    def test_extraction_is_non_empty_for_a_real_formula(self):
        # Regression guard: an empty-everywhere result (e.g. a silently
        # broken regex) would make the parity test above vacuously pass.
        formulae = load_formulae()
        any_name = next(iter(formulae))
        triples = extract_release_triples(formulae[any_name])
        self.assertEqual(
            len(triples),
            4,
            f"{any_name}.rb should declare exactly 4 (url, sha256, "
            f"bin_name) triples, one per Hardware::CPU branch",
        )


if __name__ == "__main__":
    unittest.main()
