"""Tests for scripts/check_workflow_paths.py (workflow path-filter gate)."""
from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import check_workflow_paths as gate

WORKFLOW = """\
name: demo
on:
  push:
    branches: [main]
    paths:
{push_paths}
  pull_request:
    paths:
{pr_paths}
jobs:
  demo:
    runs-on: ubuntu-latest
    steps:
      - uses: ./.github/actions/local-thing
      - run: bash scripts/run_it.sh
      # scripts/only_in_a_comment.sh must not count
      - run: python3 scripts/tool.py --config .toolrc requirements-dev.txt
"""


def _paths(*patterns: str) -> str:
    return "\n".join(f'      - "{p}"' for p in patterns)


class GlobTests(unittest.TestCase):
    def test_double_star_crosses_separators_single_star_does_not(self):
        self.assertTrue(gate.path_covered("scripts/a/b.sh", ["scripts/**"]))
        self.assertTrue(gate.path_covered("scripts/b.sh", ["scripts/**.sh"]))
        self.assertFalse(gate.path_covered("scripts/a/b.sh", ["scripts/*.sh"]))
        self.assertTrue(gate.path_covered("scripts/lib_x.sh", ["scripts/lib_*.sh"]))

    def test_negation_removes_earlier_match(self):
        self.assertFalse(gate.path_covered("scripts/x.sh", ["scripts/**", "!scripts/x.sh"]))


class ParseTests(unittest.TestCase):
    def test_paths_blocks_are_attributed_to_their_trigger(self):
        text = WORKFLOW.format(push_paths=_paths("a/**"), pr_paths=_paths("b", "c"))
        self.assertEqual(gate.parse_path_filters(text), {"push": ["a/**"], "pull_request": ["b", "c"]})

    def test_workflow_without_filters_is_ignored(self):
        self.assertEqual(gate.parse_path_filters("on:\n  push:\n    branches: [main]\n"), {})


class RepoTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / ".github/workflows").mkdir(parents=True)
        (self.root / ".github/actions/local-thing").mkdir(parents=True)
        (self.root / ".github/actions/local-thing/action.yml").write_text("name: x\n")
        (self.root / "scripts").mkdir()
        (self.root / "scripts/run_it.sh").write_text('. "$ROOT/scripts/lib_helper.sh"\n')
        (self.root / "scripts/lib_helper.sh").write_text("true\n")
        (self.root / "scripts/tool.py").write_text("import helper_mod\nimport json\n")
        (self.root / "scripts/helper_mod.py").write_text("X = 1\n")
        (self.root / "scripts/only_in_a_comment.sh").write_text("true\n")
        (self.root / ".toolrc").write_text("")
        (self.root / "requirements-dev.txt").write_text("")

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, push: tuple[str, ...], pr: tuple[str, ...]) -> None:
        text = WORKFLOW.format(push_paths=_paths(*push), pr_paths=_paths(*pr))
        (self.root / ".github/workflows/demo.yml").write_text(text)

    def test_complete_filter_passes(self):
        full = ("scripts/**", ".github/**", ".toolrc", "requirements-dev.txt")
        self._write(full, full)
        self.assertEqual(gate.check_all(self.root), [])

    def test_missing_files_are_reported_per_trigger(self):
        self._write(("scripts/run_it.sh",), ("scripts/**", ".github/**", ".toolrc", "requirements-dev.txt"))
        violations = gate.check_all(self.root)
        missing = {v.split("does not cover ")[1] for v in violations}
        self.assertEqual(
            missing,
            {
                ".github/workflows/demo.yml",
                ".github/actions/local-thing/",
                "scripts/lib_helper.sh",
                "scripts/tool.py",
                "scripts/helper_mod.py",
                ".toolrc",
                "requirements-dev.txt",
            },
        )
        self.assertTrue(all(v.startswith(".github/workflows/demo.yml: push.paths") for v in violations))
        self.assertNotIn("scripts/only_in_a_comment.sh", missing)

    def test_main_exit_codes(self):
        self._write(("nothing/**",), ("nothing/**",))
        with redirect_stderr(io.StringIO()) as err:
            self.assertEqual(gate.main(["--root", str(self.root)]), 1)
        self.assertIn("workflow path-filter gate: FAIL", err.getvalue())
        full = ("scripts/**", ".github/**", ".toolrc", "requirements-dev.txt")
        self._write(full, full)
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(gate.main(["--root", str(self.root)]), 0)
        self.assertIn("OK", out.getvalue())


if __name__ == "__main__":
    unittest.main()
