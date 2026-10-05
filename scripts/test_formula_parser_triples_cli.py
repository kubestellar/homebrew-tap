#!/usr/bin/env python3
"""Tests for formula_parser's `--triples` CLI (`_main`).

scripts/verify_release_artifacts.sh shells out to
`formula_parser.py --triples <formula.rb>` instead of keeping its own
bash parser (see kubestellar/homebrew-tap#647). These tests exercise
`_main` in-process — usage-error path and happy path — so the CLI shim
stays on the 100% coverage ratchet alongside extract_release_triples()
itself (covered by test_verify_release_artifacts_parser_parity.py).
"""

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from formula_parser import _main  # noqa: E402

FORMULA_BODY = """\
class Demo < Formula
  if Hardware::CPU.arm?
    url "https://example.com/demo_arm64.tar.gz"
    sha256 "aaaa"
    define_method(:install) { bin.install "demo" }
  else
    url "https://example.com/demo_amd64.tar.gz"
    sha256 "bbbb"
    define_method(:install) { bin.install "demo" }
  end
end
"""


class FormulaParserTriplesCliTest(unittest.TestCase):
    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = _main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_happy_path_prints_one_tsv_line_per_triple(self):
        with tempfile.TemporaryDirectory() as tmp:
            formula = Path(tmp) / "demo.rb"
            formula.write_text(FORMULA_BODY, encoding="utf-8")
            code, out, err = self._run(["--triples", str(formula)])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertEqual(
            out.splitlines(),
            [
                "https://example.com/demo_arm64.tar.gz\taaaa\tdemo",
                "https://example.com/demo_amd64.tar.gz\tbbbb\tdemo",
            ],
        )

    def test_wrong_argument_count_is_a_usage_error(self):
        code, out, err = self._run([])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("usage:", err)

    def test_unknown_flag_is_a_usage_error(self):
        code, out, err = self._run(["--frobnicate", "x.rb"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("usage:", err)


if __name__ == "__main__":
    unittest.main()
