"""
Tests for scripts/formula_test_fixtures.py.

`formula_test_fixtures` is imported by ~20 invariant test modules — its
`load_formulae()` loader is on the hot path for every `test_formula_*.py`
run, and its "no formulae found" assertion is the one signal that a bad
`FORMULA_DIR` (empty checkout, wrong cwd, path typo) produces a clear
error rather than an empty-dict false negative that would trivially pass
every invariant.

These tests cover:
  * happy path: sorted `.rb` stems load with UTF-8 text
  * empty-dir path: `AssertionError` includes the offending directory
  * non-`.rb` files are ignored by the glob
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import formula_test_fixtures  # noqa: E402


class LoadFormulaeTests(unittest.TestCase):
    def test_returns_stem_to_text_map_for_populated_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "alpha.rb").write_text("class Alpha < Formula\nend\n", encoding="utf-8")
            (tmp_path / "beta.rb").write_text("class Beta < Formula\nend\n", encoding="utf-8")
            with mock.patch.object(formula_test_fixtures, "FORMULA_DIR", tmp_path):
                result = formula_test_fixtures.load_formulae()
            self.assertEqual(set(result.keys()), {"alpha", "beta"})
            self.assertIn("class Alpha", result["alpha"])
            self.assertIn("class Beta", result["beta"])

    def test_empty_formula_dir_raises_assertion_error_with_path(self):
        # Exercises the `raise AssertionError(...)` branch. The message
        # must name the directory searched so a mis-cwd'd CI run is
        # self-diagnosing rather than manifesting as a silent no-op.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with mock.patch.object(formula_test_fixtures, "FORMULA_DIR", tmp_path):
                with self.assertRaises(AssertionError) as cm:
                    formula_test_fixtures.load_formulae()
            self.assertIn(str(tmp_path), str(cm.exception))

    def test_non_rb_files_are_ignored(self):
        # The glob is `*.rb` — README.md, .DS_Store, JSON snapshots etc.
        # sitting under Formula/ must not leak into the map (or every
        # invariant test would trip over them as invalid formula text).
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "real.rb").write_text("class Real < Formula\nend\n", encoding="utf-8")
            (tmp_path / "notes.md").write_text("# ignored", encoding="utf-8")
            (tmp_path / "data.json").write_text("{}", encoding="utf-8")
            with mock.patch.object(formula_test_fixtures, "FORMULA_DIR", tmp_path):
                result = formula_test_fixtures.load_formulae()
            self.assertEqual(list(result.keys()), ["real"])


class ListFormulaPathsTests(unittest.TestCase):
    def test_returns_sorted_paths_for_populated_dir(self):
        # The 17 setUpClass sites this helper replaces all sorted the
        # glob; preserve that so per-formula subtests keep running in a
        # deterministic order.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "beta.rb").write_text("class Beta < Formula\nend\n", encoding="utf-8")
            (tmp_path / "alpha.rb").write_text("class Alpha < Formula\nend\n", encoding="utf-8")
            with mock.patch.object(formula_test_fixtures, "FORMULA_DIR", tmp_path):
                result = formula_test_fixtures.list_formula_paths()
            self.assertEqual([p.name for p in result], ["alpha.rb", "beta.rb"])
            for p in result:
                self.assertIsInstance(p, Path)

    def test_empty_formula_dir_raises_assertion_error_with_path(self):
        # Mirror the load_formulae() empty-case contract exactly: the
        # whole point of extracting this helper (see homebrew-tap#559)
        # is to make bad-FORMULA_DIR states self-diagnosing instead of
        # producing silent SkipTest.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with mock.patch.object(formula_test_fixtures, "FORMULA_DIR", tmp_path):
                with self.assertRaises(AssertionError) as cm:
                    formula_test_fixtures.list_formula_paths()
            self.assertIn(str(tmp_path), str(cm.exception))

    def test_non_rb_files_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "real.rb").write_text("class Real < Formula\nend\n", encoding="utf-8")
            (tmp_path / "notes.md").write_text("# ignored", encoding="utf-8")
            with mock.patch.object(formula_test_fixtures, "FORMULA_DIR", tmp_path):
                result = formula_test_fixtures.list_formula_paths()
            self.assertEqual([p.name for p in result], ["real.rb"])


if __name__ == "__main__":
    unittest.main()
