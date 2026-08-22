#!/usr/bin/env python3
"""Unit tests for scripts/validate_formulae.py."""

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate_formulae import parse_formula, validate

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

VALID_DEPLOY = textwrap.dedent("""\
    # typed: false
    # frozen_string_literal: true
    class KubestellarDeploy < Formula
      version "1.2.3"
      on_linux do
        url "https://example.com/releases/v1.2.3/deploy_1.2.3_linux_amd64.tar.gz"
        sha256 "aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899"
      end
    end
""")


def _write(directory: Path, name: str, content: str) -> Path:
    p = directory / name
    p.write_text(content)
    return p


class TestParseFormula(unittest.TestCase):
    def test_valid_formula(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), "kubestellar-ops.rb", VALID_OPS)
            result = parse_formula(p)
            self.assertNotIn("error", result)
            self.assertEqual(result["version"], "1.2.3")
            self.assertEqual(result["errors"], [])

    def test_missing_version(self):
        content = VALID_OPS.replace('version "1.2.3"\n', "")
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), "ops.rb", content)
            result = parse_formula(p)
            self.assertIn("error", result)
            self.assertIn("no version line", result["error"])

    def test_multiple_versions(self):
        content = VALID_OPS + '  version "9.9.9"\n'
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), "ops.rb", content)
            result = parse_formula(p)
            self.assertIn("error", result)
            self.assertIn("multiple version", result["error"])

    def test_url_missing_version(self):
        # Replace the version in both the path and filename so nothing remains
        content = VALID_OPS.replace(
            "https://example.com/releases/v1.2.3/ops_1.2.3_linux_amd64.tar.gz",
            "https://example.com/releases/vWRONG/ops_WRONG_linux_amd64.tar.gz",
        )
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), "ops.rb", content)
            result = parse_formula(p)
            self.assertTrue(any("does not embed version" in e for e in result["errors"]))

    def test_malformed_sha256_too_short(self):
        content = VALID_OPS.replace(
            "aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899",
            "deadbeef"
        )
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), "ops.rb", content)
            result = parse_formula(p)
            self.assertTrue(any("malformed sha256" in e for e in result["errors"]))

    def test_malformed_sha256_uppercase(self):
        content = VALID_OPS.replace(
            "aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899",
            "AABBCCDDEEFF00112233445566778899AABBCCDDEEFF00112233445566778899"
        )
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), "ops.rb", content)
            result = parse_formula(p)
            self.assertTrue(any("malformed sha256" in e for e in result["errors"]))

    def test_missing_sha256_after_url(self):
        content = textwrap.dedent("""\
            class Ops < Formula
              version "1.0.0"
              url "https://example.com/v1.0.0/ops_1.0.0.tar.gz"
              desc "missing sha"
            end
        """)
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), "ops.rb", content)
            result = parse_formula(p)
            self.assertTrue(any("expected sha256 after url" in e for e in result["errors"]))


class TestValidate(unittest.TestCase):
    def test_valid_directory(self):
        with tempfile.TemporaryDirectory() as d:
            _write(Path(d), "kubestellar-ops.rb", VALID_OPS)
            _write(Path(d), "kubestellar-deploy.rb", VALID_DEPLOY)
            rc = validate(Path(d))
            self.assertEqual(rc, 0)

    def test_lockstep_mismatch(self):
        deploy_v2 = VALID_DEPLOY.replace("1.2.3", "2.0.0")
        with tempfile.TemporaryDirectory() as d:
            _write(Path(d), "kubestellar-ops.rb", VALID_OPS)
            _write(Path(d), "kubestellar-deploy.rb", deploy_v2)
            rc = validate(Path(d))
            self.assertEqual(rc, 1)

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as d:
            rc = validate(Path(d))
            self.assertEqual(rc, 1)

    def test_real_formulae(self):
        formula_dir = Path(__file__).parent.parent / "Formula"
        if formula_dir.exists():
            rc = validate(formula_dir)
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
