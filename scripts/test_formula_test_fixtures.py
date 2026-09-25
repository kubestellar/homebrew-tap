"""
Tests for scripts/formula_parser.py (and its scripts/formula_test_fixtures.py
backward-compatibility re-export shim).

`formula_parser` is imported directly by scripts/validate_formulae.py (the
module Homebrew CI's *Validate Formulae* job runs) and, via the
`formula_test_fixtures` re-export shim, by ~20 invariant test modules —
its `load_formulae()` loader is on the hot path for every
`test_formula_*.py` run, and its "no formulae found" assertion is the one
signal that a bad `FORMULA_DIR` (empty checkout, wrong cwd, path typo)
produces a clear error rather than an empty-dict false negative that
would trivially pass every invariant.

These tests cover:
  * happy path: sorted `.rb` stems load with UTF-8 text
  * empty-dir path: `AssertionError` includes the offending directory
  * non-`.rb` files are ignored by the glob
  * `formula_test_fixtures` re-exports still bind to the same callables
    (guard for kubestellar/homebrew-tap#565 shim rot).
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import formula_parser  # noqa: E402
import formula_test_fixtures  # noqa: E402  # kept for re-export smoke coverage


class LoadFormulaeTests(unittest.TestCase):
    def test_returns_stem_to_text_map_for_populated_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "alpha.rb").write_text("class Alpha < Formula\nend\n", encoding="utf-8")
            (tmp_path / "beta.rb").write_text("class Beta < Formula\nend\n", encoding="utf-8")
            with mock.patch.object(formula_parser, "FORMULA_DIR", tmp_path):
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
            with mock.patch.object(formula_parser, "FORMULA_DIR", tmp_path):
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
            with mock.patch.object(formula_parser, "FORMULA_DIR", tmp_path):
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
            with mock.patch.object(formula_parser, "FORMULA_DIR", tmp_path):
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
            with mock.patch.object(formula_parser, "FORMULA_DIR", tmp_path):
                with self.assertRaises(AssertionError) as cm:
                    formula_test_fixtures.list_formula_paths()
            self.assertIn(str(tmp_path), str(cm.exception))

    def test_non_rb_files_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "real.rb").write_text("class Real < Formula\nend\n", encoding="utf-8")
            (tmp_path / "notes.md").write_text("# ignored", encoding="utf-8")
            with mock.patch.object(formula_parser, "FORMULA_DIR", tmp_path):
                result = formula_test_fixtures.list_formula_paths()
            self.assertEqual([p.name for p in result], ["real.rb"])


class ReExportShimTests(unittest.TestCase):
    """Guard against silent drift of the ``formula_test_fixtures`` backward-
    compatibility shim introduced in kubestellar/homebrew-tap#565.

    ~20 ``test_formula_*_invariants.py`` modules still import symbols
    under the historical ``from formula_test_fixtures import X`` path.
    If a future refactor accidentally re-declares any of these symbols
    inside ``formula_test_fixtures.py`` (instead of re-exporting them),
    a fix in ``formula_parser.py`` would silently fail to reach those
    tests. Asserting object identity is the cheapest way to catch that.
    """

    def test_reexports_are_same_objects_as_formula_parser(self):
        for name in (
            "ALLOWED_URL_HOSTS",
            "DESC_LINE_RE",
            "FORMULA_DIR",
            "HOMEPAGE_LINE_RE",
            "LICENSE_LINE_RE",
            "RELEASE_URL_RE",
            "SHA256_LINE_RE",
            "URL_INLINE_RE",
            "URL_LINE_RE",
            "VERSION_LINE_RE",
            "_extract_url_hosts",
            "list_formula_paths",
            "load_formulae",
        ):
            with self.subTest(name=name):
                self.assertIs(
                    getattr(formula_test_fixtures, name),
                    getattr(formula_parser, name),
                    f"formula_test_fixtures.{name} drifted from formula_parser.{name}",
                )


if __name__ == "__main__":
    unittest.main()
