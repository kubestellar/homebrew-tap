#!/usr/bin/env python3
"""Unit tests for the $GITHUB_STEP_SUMMARY output added to
scripts/validate_formulae.py's emit_summary() (see docs/slo.md and
homebrew-tap#367). Kept in its own file rather than growing the already
oversized scripts/test_validate_formulae.py (homebrew-tap#324)."""

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parent / "validate_formulae.py"

VALID_OPS = textwrap.dedent("""\
    # typed: false
    # frozen_string_literal: true
    class KubestellarOps < Formula
      version "1.2.3"
      on_linux do
        url "https://example.com/releases/v1.2.3/ops_1.2.3_linux_amd64.tar.gz"
        sha256 "aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899"
      end
    end
""")

BROKEN_SHA = textwrap.dedent("""\
    # typed: false
    # frozen_string_literal: true
    class KubestellarOps < Formula
      version "1.2.3"
      on_linux do
        url "https://example.com/releases/v1.2.3/ops_1.2.3_linux_amd64.tar.gz"
        sha256 "not-a-valid-sha256"
      end
    end
""")


def _write(directory: Path, name: str, content: str) -> Path:
    p = directory / name
    p.write_text(content)
    return p


def _run(formula_dir: Path, summary_path: Path | None):
    env = {"PATH": "/usr/bin:/bin"}
    if summary_path is not None:
        env["GITHUB_STEP_SUMMARY"] = str(summary_path)
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(formula_dir)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


class TestStepSummaryPass(unittest.TestCase):
    def test_pass_writes_markdown_table(self):
        with tempfile.TemporaryDirectory() as d:
            _write(Path(d), "kubestellar-ops.rb", VALID_OPS)
            summary_file = Path(d) / "step_summary.md"
            summary_file.write_text("")
            result = _run(Path(d), summary_file)
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            content = summary_file.read_text()
            self.assertIn("### Formula drift check", content)
            self.assertIn("✅ pass", content)
            self.assertIn("| 1 | 0 |", content)
            # No error details section on a clean pass.
            self.assertNotIn("<details>", content)


class TestStepSummaryFail(unittest.TestCase):
    def test_fail_writes_error_details(self):
        with tempfile.TemporaryDirectory() as d:
            _write(Path(d), "kubestellar-ops.rb", BROKEN_SHA)
            summary_file = Path(d) / "step_summary.md"
            summary_file.write_text("")
            result = _run(Path(d), summary_file)
            self.assertEqual(result.returncode, 1)
            content = summary_file.read_text()
            self.assertIn("❌ fail", content)
            self.assertIn("<details><summary>Error details</summary>", content)
            self.assertIn("malformed sha256", content)

    def test_no_formula_files_writes_error_status(self):
        with tempfile.TemporaryDirectory() as d:
            empty_dir = Path(d) / "empty"
            empty_dir.mkdir()
            summary_file = Path(d) / "step_summary.md"
            summary_file.write_text("")
            result = _run(empty_dir, summary_file)
            self.assertEqual(result.returncode, 1)
            content = summary_file.read_text()
            self.assertIn("❌ error", content)
            self.assertIn("no .rb files found", content)


class TestStepSummaryDisabled(unittest.TestCase):
    def test_no_env_var_is_a_no_op(self):
        """Without GITHUB_STEP_SUMMARY set (e.g. local runs), the script
        must not attempt to write anywhere or fail."""
        with tempfile.TemporaryDirectory() as d:
            _write(Path(d), "kubestellar-ops.rb", VALID_OPS)
            result = _run(Path(d), summary_path=None)
            self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_many_errors_are_capped_in_summary(self):
        # 25 broken formulae > MAX_STEP_SUMMARY_ERRORS (20); verify the
        # table stays bounded and reports an overflow count instead of
        # rendering every error.
        with tempfile.TemporaryDirectory() as d:
            for i in range(25):
                _write(Path(d), f"broken-{i}.rb", BROKEN_SHA.replace(
                    "KubestellarOps", f"Broken{i}"
                ))
            summary_file = Path(d) / "step_summary.md"
            summary_file.write_text("")
            result = _run(Path(d), summary_file)
            self.assertEqual(result.returncode, 1)
            content = summary_file.read_text()
            self.assertIn("...and 5 more (see step log)", content)


if __name__ == "__main__":
    unittest.main()
