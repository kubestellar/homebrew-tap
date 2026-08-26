#!/usr/bin/env python3
"""Unit tests for scripts/validate_formulae.py."""

import re
import subprocess
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

MULTI_URL_OPS = textwrap.dedent("""\
    # typed: false
    # frozen_string_literal: true
    class KubestellarOps < Formula
      version "1.2.3"
      on_macos do
        if Hardware::CPU.intel?
          url "https://example.com/releases/v1.2.3/ops_1.2.3_darwin_amd64.tar.gz"
          sha256 "1111111111111111111111111111111111111111111111111111111111111111"
        end
        if Hardware::CPU.arm?
          url "https://example.com/releases/v1.2.3/ops_1.2.3_darwin_arm64.tar.gz"
          sha256 "2222222222222222222222222222222222222222222222222222222222222222"
        end
      end
      on_linux do
        if Hardware::CPU.intel? && Hardware::CPU.is_64_bit?
          url "https://example.com/releases/v1.2.3/ops_1.2.3_linux_amd64.tar.gz"
          sha256 "3333333333333333333333333333333333333333333333333333333333333333"
        end
        if Hardware::CPU.arm? && Hardware::CPU.is_64_bit?
          url "https://example.com/releases/v1.2.3/ops_1.2.3_linux_arm64.tar.gz"
          sha256 "4444444444444444444444444444444444444444444444444444444444444444"
        end
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

FORMULA_DIR = Path(__file__).resolve().parent.parent / "Formula"

# Homebrew formulae in this tap may pull artifacts only from these hosts.
# Extend this set with a code change (reviewed) when a new upstream lands.
ALLOWED_URL_HOSTS = {
    "github.com",
    "objects.githubusercontent.com",  # GH release CDN redirects land here
}


def _extract_url_hosts(text: str) -> list[str]:
    """Return hosts of every `url "..."` in a formula body, in order."""
    hosts = []
    for m in re.finditer(r'^\s*url\s+"([^"]+)"', text, re.MULTILINE):
        url = m.group(1)
        # crude but sufficient: strip scheme, take everything before the
        # next `/`. Formulae never use userinfo or non-default ports.
        scheme, _, rest = url.partition("://")
        host = rest.split("/", 1)[0]
        hosts.append((url, scheme, host))
    return hosts


class TestFormulaPolicy(unittest.TestCase):
    """Whole-repo policy checks on Formula/*.rb — run against real files."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.formula_files = sorted(FORMULA_DIR.glob("*.rb"))
        if not cls.formula_files:
            raise unittest.SkipTest(f"no .rb files in {FORMULA_DIR}")

    def test_every_formula_has_a_test_block(self):
        # `brew audit --strict` requires a `test do` block on every
        # formula; if someone deletes one during a refactor, we want to
        # catch it in unit tests before it reaches `brew` in CI.
        missing = []
        for f in self.formula_files:
            body = f.read_text()
            if not re.search(r'^\s*test\s+do\b', body, re.MULTILINE):
                missing.append(f.name)
        self.assertEqual(
            missing, [],
            msg=f"Formula(e) missing `test do` block: {missing}",
        )

    def test_every_url_uses_https(self):
        # `http://` / `ftp://` / `file://` / `git+ssh://` in a release
        # URL would be a downgrade attack surface. Homebrew accepts
        # them but our tap does not.
        offenders = []
        for f in self.formula_files:
            for url, scheme, _host in _extract_url_hosts(f.read_text()):
                if scheme != "https":
                    offenders.append((f.name, url, scheme))
        self.assertEqual(
            offenders, [],
            msg=f"Formula url(s) not using https: {offenders}",
        )

    def test_every_url_host_is_in_allowlist(self):
        # Supply-chain guard: a malicious PR could point `url` at
        # attacker-controlled infrastructure. This test fails loudly
        # if any host outside ALLOWED_URL_HOSTS shows up.
        offenders = []
        for f in self.formula_files:
            for url, _scheme, host in _extract_url_hosts(f.read_text()):
                if host not in ALLOWED_URL_HOSTS:
                    offenders.append((f.name, host, url))
        self.assertEqual(
            offenders, [],
            msg=(
                "Formula url(s) point at hosts not in ALLOWED_URL_HOSTS. "
                "If this is legitimate, add the host to the allowlist in "
                f"this test file. Offenders: {offenders}"
            ),
        )

    def test_lockstep_groups_reference_real_formulae(self):
        # Guards against a typo in LOCKSTEP_GROUPS silently making a
        # lockstep pair partially skipped in production — since
        # `validate()` returns without complaint when only 1 partner
        # exists. If we intended a group of 2 but only 1 name matches
        # a file, that's a bug in the constant, not in the tap.
        from validate_formulae import LOCKSTEP_GROUPS
        formula_stems = {f.stem for f in self.formula_files}
        for group in LOCKSTEP_GROUPS:
            missing = group - formula_stems
            self.assertEqual(
                missing, set(),
                msg=(
                    f"LOCKSTEP_GROUPS entry {sorted(group)} references "
                    f"formulae that do not exist in {FORMULA_DIR}: "
                    f"{sorted(missing)}"
                ),
            )

    def test_every_formula_has_at_least_one_url(self):
        # A formula with no `url` line would be caught by `brew audit`
        # but not by our drift checker (no urls -> no url iteration ->
        # no errors). Assert every formula has at least one release URL.
        empty = []
        for f in self.formula_files:
            hosts = _extract_url_hosts(f.read_text())
            if not hosts:
                empty.append(f.name)
        self.assertEqual(
            empty, [],
            msg=f"Formula(e) with no url line: {empty}",
        )

    def test_drift_check_passes_on_real_formula_dir(self):
        # Integration: the exact command CI runs
        # (`python3 -u scripts/validate_formulae.py Formula`) must exit 0
        # on every commit. This test is a belt-and-suspenders duplicate
        # of TestValidateEndToEnd.test_real_formulae but framed as a
        # policy test so it appears in the policy failure cluster if
        # someone accidentally introduces drift while adding a formula.
        from validate_formulae import validate
        rc = validate(FORMULA_DIR)
        self.assertEqual(rc, 0, msg="drift check failed on real Formula/")


if __name__ == "__main__":
    unittest.main()
