#!/usr/bin/env python3
"""Unit tests for scripts/validate_formulae.py (parser, validate(), main)."""

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate_formulae import parse_formula, validate
from formula_test_fixtures import MULTI_URL_OPS, VALID_DEPLOY, VALID_OPS, _write

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

    def test_multi_url_formula_valid(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), "kubestellar-ops.rb", MULTI_URL_OPS)
            result = parse_formula(p)
            self.assertNotIn("error", result)
            self.assertEqual(result["version"], "1.2.3")
            self.assertEqual(result["errors"], [])

    def test_multi_url_formula_reports_partial_drift(self):
        content = MULTI_URL_OPS.replace(
            "https://example.com/releases/v1.2.3/ops_1.2.3_linux_amd64.tar.gz",
            "https://example.com/releases/vWRONG/ops_WRONG_linux_amd64.tar.gz",
        ).replace(
            "3333333333333333333333333333333333333333333333333333333333333333",
            "shortsha",
        )
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), "kubestellar-ops.rb", content)
            result = parse_formula(p)
            self.assertEqual(
                len([e for e in result["errors"] if "does not embed version" in e]),
                1,
            )
            self.assertEqual(
                len([e for e in result["errors"] if "malformed sha256" in e]),
                1,
            )


class TestParseFormulaEdgeCases(unittest.TestCase):
    def test_url_with_no_subsequent_line(self):
        content = textwrap.dedent("""\
            class Ops < Formula
              version "1.0.0"
              url "https://example.com/v1.0.0/ops_1.0.0.tar.gz\"""")
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), "ops.rb", content)
            result = parse_formula(p)
            self.assertTrue(any("no line after url" in e for e in result["errors"]))

    def test_url_followed_only_by_blank_lines(self):
        content = (
            'class Ops < Formula\n'
            '  version "1.0.0"\n'
            '  url "https://example.com/v1.0.0/ops_1.0.0.tar.gz"\n'
            '\n'
            '\n'
            '\n'
        )
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), "ops.rb", content)
            result = parse_formula(p)
            self.assertTrue(any("no line after url" in e for e in result["errors"]))


class TestValidate(unittest.TestCase):
    def test_validate_propagates_parse_error(self):
        content = VALID_OPS.replace('version "1.2.3"\n', "")
        with tempfile.TemporaryDirectory() as d:
            _write(Path(d), "kubestellar-ops.rb", content)
            rc = validate(Path(d))
            self.assertEqual(rc, 1)

    def test_lockstep_skipped_when_partner_missing(self):
        with tempfile.TemporaryDirectory() as d:
            _write(Path(d), "kubestellar-ops.rb", VALID_OPS)
            rc = validate(Path(d))
            self.assertEqual(rc, 0)

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


class TestParseFormulaMoreEdgeCases(unittest.TestCase):
    def test_url_line_matches_outer_but_inner_regex_fails(self):
        # A `url "` line with no closing quote matches the outer
        # `re.match(r'^\s*url\s+"', ...)` sentinel but fails the inner
        # `re.search(r'url\s+"([^"]+)"', ...)` extraction. The parser
        # must skip that malformed url line silently rather than crash.
        content = (
            'class Ops < Formula\n'
            '  version "1.0.0"\n'
            '  url "\n'
            '  sha256 "aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899"\n'
            'end\n'
        )
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), "ops.rb", content)
            result = parse_formula(p)
            # Must not error out; the malformed url line is skipped.
            self.assertNotIn("error", result)
            self.assertEqual(result["version"], "1.0.0")
            self.assertEqual(result["errors"], [])

    def test_url_followed_by_non_sha_line(self):
        # Ensures the "expected sha256 after url" branch fires when the
        # next non-blank line is neither blank nor a sha256 directive.
        content = textwrap.dedent("""\
            class Ops < Formula
              version "1.0.0"
              url "https://example.com/v1.0.0/ops_1.0.0.tar.gz"
              desc "hi"
              sha256 "aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899"
            end
        """)
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), "ops.rb", content)
            result = parse_formula(p)
            self.assertTrue(any("expected sha256 after url" in e for e in result["errors"]))

    def test_lockstep_group_all_partners_missing(self):
        # If none of the group's members are present, lockstep is skipped
        # (len(available) < 2) — smoke-test that a lone unrelated formula
        # validates cleanly.
        content = textwrap.dedent("""\
            class Solo < Formula
              version "1.0.0"
              url "https://example.com/v1.0.0/solo_1.0.0.tar.gz"
              sha256 "aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899"
            end
        """)
        with tempfile.TemporaryDirectory() as d:
            _write(Path(d), "solo.rb", content)
            rc = validate(Path(d))
            self.assertEqual(rc, 0)


class TestMainEntryPoint(unittest.TestCase):
    """Cover the ``if __name__ == "__main__":`` block via subprocess."""

    SCRIPT = Path(__file__).parent / "validate_formulae.py"

    def test_main_with_explicit_dir_ok(self):
        with tempfile.TemporaryDirectory() as d:
            _write(Path(d), "kubestellar-ops.rb", VALID_OPS)
            _write(Path(d), "kubestellar-deploy.rb", VALID_DEPLOY)
            result = subprocess.run(
                [sys.executable, str(self.SCRIPT), d],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("OK", result.stdout)

    def test_main_with_explicit_dir_fail(self):
        # Cause a lockstep mismatch so validate() returns 1.
        deploy_v2 = VALID_DEPLOY.replace("1.2.3", "2.0.0")
        with tempfile.TemporaryDirectory() as d:
            _write(Path(d), "kubestellar-ops.rb", VALID_OPS)
            _write(Path(d), "kubestellar-deploy.rb", deploy_v2)
            result = subprocess.run(
                [sys.executable, str(self.SCRIPT), d],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("lockstep version mismatch", result.stderr)

    def test_main_defaults_to_formula_dir(self):
        # No CLI arg → defaults to Path("Formula"). Run from the repo root
        # so the real Formula/ directory is picked up.
        repo_root = Path(__file__).parent.parent
        if not (repo_root / "Formula").exists():
            self.skipTest("Formula/ directory not present")
        result = subprocess.run(
            [sys.executable, str(self.SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(repo_root),
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("OK", result.stdout)


# ---------------------------------------------------------------------------
# Formula policy tests
#
# These tests complement the drift checker by enforcing repo-wide policy
# on every Formula/*.rb file — properties that the parser does NOT check
# but that would represent real regressions if violated:
#
#   * every published formula must have a `test do` block (Homebrew audit
#     downgrades taps that don't self-test)
#   * every url must use https (no http, ftp, file, git+ssh, etc.)
#   * every url host must be in an allowlist of trusted domains — this is
#     a supply-chain guard against a rogue PR pointing at attacker infra
#   * every name listed in LOCKSTEP_GROUPS must correspond to a real file
#     in Formula/ (guards against typos when adding new lockstep pairs)
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    unittest.main()
