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


class TestFormulaSupplyChainPolicy(unittest.TestCase):
    """Additional supply-chain policy checks on Formula/*.rb.

    These guard against real regression classes that the drift checker and
    the existing TestFormulaPolicy do not cover:

      * distinct platform bottles must have distinct sha256 values (a
        copy-paste bug that reuses e.g. the darwin_amd64 checksum for
        darwin_arm64 would let brew install the wrong archive silently)
      * the `homepage` line must use https (parity with url policy)
      * every `sha256 "..."` in the file must be a valid 64-char lowercase
        hex string — enforced by the parser only for sha256 lines that
        immediately follow a url, but a stray malformed sha256 elsewhere
        would still ship in the tap and mislead brew's own audit output
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.formula_files = sorted(FORMULA_DIR.glob("*.rb"))
        if not cls.formula_files:
            raise unittest.SkipTest(f"no .rb files in {FORMULA_DIR}")

    def test_sha256_values_unique_within_each_formula(self):
        # Two `url` lines in the same formula that resolve to distinct
        # release archives (different arch, different OS) MUST have
        # distinct sha256 values. If they match, someone likely
        # copy-pasted a stanza and forgot to update the checksum — brew
        # will happily "verify" the wrong archive against the pasted
        # digest for one architecture.
        offenders = []
        for f in self.formula_files:
            text = f.read_text()
            urls = [m.group(1) for m in re.finditer(r'^\s*url\s+"([^"]+)"', text, re.MULTILINE)]
            shas = [m.group(1) for m in re.finditer(r'^\s*sha256\s+"([^"]+)"', text, re.MULTILINE)]
            if len(urls) < 2 or len(urls) != len(shas):
                # Structural mismatches are the drift checker's job.
                continue
            unique_urls = len(set(urls))
            unique_shas = len(set(shas))
            if unique_urls > 1 and unique_shas < unique_urls:
                # Find the specific duplicate sha and the urls it maps to.
                pairs = list(zip(urls, shas))
                seen: dict[str, list[str]] = {}
                for u, s in pairs:
                    seen.setdefault(s, []).append(u)
                dups = {s: us for s, us in seen.items() if len({*us}) > 1}
                offenders.append((f.name, dups))
        self.assertEqual(
            offenders, [],
            msg=(
                "Formula(e) reuse the same sha256 across distinct release "
                f"URLs (copy-paste bug): {offenders}"
            ),
        )

    def test_homepage_uses_https(self):
        # A homepage over plain http shows up in `brew info` and in the
        # GitHub taps directory — same downgrade concern as `url`.
        offenders = []
        for f in self.formula_files:
            for m in re.finditer(r'^\s*homepage\s+"([^"]+)"', f.read_text(), re.MULTILINE):
                homepage = m.group(1)
                scheme = homepage.partition("://")[0]
                if scheme != "https":
                    offenders.append((f.name, homepage))
        self.assertEqual(
            offenders, [],
            msg=f"Formula homepage(s) not using https: {offenders}",
        )

    def test_every_sha256_line_is_well_formed(self):
        # Whole-file sweep: catches malformed sha256 tokens even in
        # positions the drift checker doesn't inspect (e.g. a resource
        # block, a comment-based override — anywhere `sha256 "..."`
        # appears). Homebrew's own audit would reject these, but our
        # unit tests should fail first.
        offenders = []
        sha_line_re = re.compile(r'^\s*sha256\s+"([^"]+)"', re.MULTILINE)
        good = re.compile(r'^[0-9a-f]{64}$')
        for f in self.formula_files:
            for m in sha_line_re.finditer(f.read_text()):
                digest = m.group(1)
                if not good.match(digest):
                    offenders.append((f.name, digest))
        self.assertEqual(
            offenders, [],
            msg=(
                "Formula(e) contain sha256 token(s) that are not 64 "
                f"lowercase hex chars: {offenders}"
            ),
        )


def _expected_class_name(stem: str) -> str:
    """Homebrew derives a formula's Ruby class name from its filename by
    splitting on '-' and '_' and PascalCasing each segment. For example:
      ``kc-agent``            -> ``KcAgent``
      ``kubestellar-deploy``  -> ``KubestellarDeploy``
      ``my_thing``            -> ``MyThing``
    """
    parts = re.split(r'[-_]', stem)
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


class TestFormulaClassAndMetadataPolicy(unittest.TestCase):
    """Repo-wide checks for structural fields that ``brew audit --strict``
    treats as fatal but the drift checker does not currently inspect:

      * class-name-must-match-filename — ``brew install`` fails outright if
        the class token differs from Homebrew's PascalCased filename, so a
        typo like ``class Kcagent`` instead of ``class KcAgent`` bricks the
        tap for every user until reverted
      * every formula must declare a ``desc`` line — required by
        ``brew audit --strict`` and shown in ``brew info``
      * every formula must declare a ``license`` line — required by
        ``brew audit --strict`` for the core tap and highly recommended for
        third-party taps

    Failing these tests locally is cheaper than discovering them in the
    macOS-only ``brew-ci.yml`` job on a PR.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.formula_files = sorted(FORMULA_DIR.glob("*.rb"))
        if not cls.formula_files:
            raise unittest.SkipTest(f"no .rb files in {FORMULA_DIR}")

    def test_class_name_matches_filename(self):
        offenders = []
        class_re = re.compile(r'^\s*class\s+([A-Za-z0-9_]+)\s*<\s*Formula\b',
                              re.MULTILINE)
        for f in self.formula_files:
            expected = _expected_class_name(f.stem)
            m = class_re.search(f.read_text())
            if not m:
                offenders.append((f.name, None, expected))
                continue
            if m.group(1) != expected:
                offenders.append((f.name, m.group(1), expected))
        self.assertEqual(
            offenders, [],
            msg=(
                "Formula(e) whose Ruby class name does not match "
                "Homebrew's PascalCased filename (brew install will "
                f"fail): {offenders}"
            ),
        )

    def test_every_formula_has_desc(self):
        missing = [
            f.name for f in self.formula_files
            if not re.search(r'^\s*desc\s+"[^"]+"', f.read_text(), re.MULTILINE)
        ]
        self.assertEqual(
            missing, [],
            msg=f"Formula(e) missing `desc` line: {missing}",
        )

    def test_every_formula_has_license(self):
        missing = [
            f.name for f in self.formula_files
            if not re.search(r'^\s*license\s+"[^"]+"', f.read_text(), re.MULTILINE)
        ]
        self.assertEqual(
            missing, [],
            msg=f"Formula(e) missing `license` line: {missing}",
        )


class TestExpectedClassName(unittest.TestCase):
    """Direct coverage for the ``_expected_class_name`` helper."""

    def test_single_word(self):
        self.assertEqual(_expected_class_name("solo"), "Solo")

    def test_hyphenated(self):
        self.assertEqual(_expected_class_name("kc-agent"), "KcAgent")
        self.assertEqual(
            _expected_class_name("kubestellar-deploy"), "KubestellarDeploy"
        )

    def test_underscore(self):
        self.assertEqual(_expected_class_name("my_thing"), "MyThing")

    def test_mixed_separators(self):
        self.assertEqual(_expected_class_name("a-b_c"), "ABC")

    def test_double_separator_is_ignored(self):
        # Empty segments are skipped, mirroring Homebrew's behaviour.
        self.assertEqual(_expected_class_name("a--b"), "AB")

    def test_preserves_internal_capitalization(self):
        # PascalCase only lifts the first character; internal casing (e.g.
        # an acronym typed as `MCP`) survives untouched.
        self.assertEqual(_expected_class_name("kMCP-agent"), "KMCPAgent")


# =========================================================================
# Consistency policy — bin.install ↔ test block; url ↔ homepage owner/repo.
# Both are supply-chain / brew-audit regression classes not covered by the
# prior TestFormulaPolicy / TestFormulaClassAndMetadataPolicy suites.
# =========================================================================


def _bin_install_names(text: str) -> set[str]:
    """Return the set of binary names installed by any `bin.install "<name>"`
    statement in the formula body (may appear in multiple platform blocks)."""
    return {m.group(1) for m in re.finditer(r'bin\.install\s+"([^"]+)"', text)}


def _test_block_binary_refs(text: str) -> set[str]:
    """Return the set of binary basenames referenced inside the `test do`
    block via `bin/"<name>"` — one entry per distinct name referenced."""
    m = re.search(r'^\s*test\s+do\b(.*?)^\s*end\b', text, re.DOTALL | re.MULTILINE)
    if not m:
        return set()
    return {r.group(1) for r in re.finditer(r'bin/"([^"]+)"', m.group(1))}


def _github_repo_from_url(url: str) -> tuple[str, str] | None:
    """Extract (owner, repo) from a github.com URL, or None if the URL is
    not a github.com URL. Works for both `https://github.com/<o>/<r>/…` and
    `https://<repo>.github.io/…` (which resolves to (repo, "") — but this
    tap never uses that form for release artifacts)."""
    m = re.match(r'^https?://github\.com/([^/]+)/([^/]+)(?:/|$)', url)
    if m:
        return (m.group(1), m.group(2))
    return None


class TestFormulaInstallTestConsistency(unittest.TestCase):
    """Every formula's `test do` block must reference at least one binary
    that was actually installed by a `bin.install "..."` statement in the
    formula body. If they diverge (e.g. `bin.install "kubestellar-ops"`
    coexists with `system bin/"kc-ops", "version"`) `brew test` fails on
    install — but only after CI has already pushed the bottle. This unit
    test catches it locally."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.formula_files = sorted(FORMULA_DIR.glob("*.rb"))
        if not cls.formula_files:
            raise unittest.SkipTest(f"no .rb files in {FORMULA_DIR}")

    def test_test_block_references_an_installed_binary(self):
        offenders = []
        for f in self.formula_files:
            text = f.read_text()
            installed = _bin_install_names(text)
            referenced = _test_block_binary_refs(text)
            if not installed:
                # A formula that installs nothing is a separate bug that
                # other tests (or `brew audit`) will surface; don't
                # cross-contaminate this check.
                continue
            if not referenced:
                offenders.append((f.name, "test block references no bin/\"...\""))
                continue
            unknown = referenced - installed
            if unknown:
                offenders.append((f.name, sorted(unknown), sorted(installed)))
        self.assertEqual(
            offenders, [],
            msg=(
                "Formula(e) reference binaries in `test do` that are not "
                "installed by any `bin.install`. brew test would fail on "
                f"install. Offenders: {offenders}"
            ),
        )


class TestFormulaHomepageURLRepoConsistency(unittest.TestCase):
    """Guards against a supply-chain redirect where a formula's `homepage`
    claims one github.com repository but its release `url` lines point at
    a different one. Both endpoints stay on the allowlisted host so
    `test_every_url_host_is_in_allowlist` would still pass, but the
    artifacts a user gets no longer belong to the advertised project.

    We only enforce the invariant when BOTH sides are on github.com
    (the release CDN redirect target `objects.githubusercontent.com`
    is already the ALLOWED_URL_HOSTS carve-out, so URLs on that host
    are skipped here rather than incorrectly flagged)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.formula_files = sorted(FORMULA_DIR.glob("*.rb"))
        if not cls.formula_files:
            raise unittest.SkipTest(f"no .rb files in {FORMULA_DIR}")

    def test_release_url_repo_matches_homepage_repo(self):
        offenders = []
        for f in self.formula_files:
            text = f.read_text()

            hp_matches = re.findall(r'^\s*homepage\s+"([^"]+)"', text, re.MULTILINE)
            if len(hp_matches) != 1:
                # No homepage or duplicate homepage — other checks cover.
                continue
            hp_repo = _github_repo_from_url(hp_matches[0])
            if hp_repo is None:
                # Homepage isn't a github.com URL — not our invariant to
                # enforce (some projects legitimately host docs elsewhere).
                continue

            for url, _scheme, _host in _extract_url_hosts(text):
                url_repo = _github_repo_from_url(url)
                if url_repo is None:
                    # e.g. objects.githubusercontent.com — skip.
                    continue
                if url_repo != hp_repo:
                    offenders.append((f.name, hp_repo, url_repo, url))

        self.assertEqual(
            offenders, [],
            msg=(
                "Formula release url(s) point at a github.com repo that "
                "differs from the formula's homepage repo. This is a "
                "supply-chain smell — the advertised project and the "
                f"served artifacts diverge. Offenders: {offenders}"
            ),
        )


class TestFormulaConsistencyHelpers(unittest.TestCase):
    """Direct unit tests for the pure helpers used by the two consistency
    suites above. Cheap, deterministic, and guard against a helper
    regression that would silently make the whole-repo checks vacuous."""

    def test_bin_install_names_extracts_multiple(self):
        body = textwrap.dedent("""\
            on_macos do
              bin.install "foo"
            end
            on_linux do
              bin.install "foo"
              bin.install "bar"
            end
        """)
        self.assertEqual(_bin_install_names(body), {"foo", "bar"})

    def test_bin_install_names_empty_when_no_installs(self):
        self.assertEqual(_bin_install_names("class X < Formula\nend\n"), set())

    def test_test_block_binary_refs_extracts_bin_slash(self):
        body = textwrap.dedent("""\
            class X < Formula
              test do
                system bin/"foo", "version"
                system bin/"bar", "--help"
              end
            end
        """)
        self.assertEqual(_test_block_binary_refs(body), {"foo", "bar"})

    def test_test_block_binary_refs_ignores_bin_refs_outside_block(self):
        # A `bin/"foo"` outside a `test do` block must not be counted —
        # otherwise a bare bin reference in a comment or in the install
        # block would spuriously satisfy the consistency check.
        body = textwrap.dedent("""\
            class X < Formula
              def install
                # bin/"foo" is not a test reference
                bin.install "foo"
              end
            end
        """)
        self.assertEqual(_test_block_binary_refs(body), set())

    def test_test_block_binary_refs_empty_when_no_test_block(self):
        self.assertEqual(_test_block_binary_refs("class X < Formula\nend\n"), set())

    def test_github_repo_from_url_parses_release_path(self):
        self.assertEqual(
            _github_repo_from_url("https://github.com/kubestellar/kubestellar-mcp/releases/download/v1.0.0/foo.tar.gz"),
            ("kubestellar", "kubestellar-mcp"),
        )

    def test_github_repo_from_url_ignores_non_github_hosts(self):
        self.assertIsNone(_github_repo_from_url("https://objects.githubusercontent.com/xyz"))
        self.assertIsNone(_github_repo_from_url("https://example.com/kubestellar/kubestellar-mcp"))

    def test_github_repo_from_url_bare_repo_root(self):
        # `https://github.com/<o>/<r>` (no trailing slash / path) is still
        # a valid GitHub repo URL — used as `homepage`.
        self.assertEqual(
            _github_repo_from_url("https://github.com/kubestellar/kubestellar-mcp"),
            ("kubestellar", "kubestellar-mcp"),
        )


class TestCLIEntrypoint(unittest.TestCase):
    """
    Exercise `if __name__ == "__main__": validate(...)` at the tail of
    validate_formulae.py by running the module in-process with runpy.
    Covers the argv-parsing branch (custom dir vs default 'Formula/') and
    the sys.exit(...) return-code plumbing.
    """

    SCRIPT = Path(__file__).resolve().parent / "validate_formulae.py"

    def _run_as_main(self, argv):
        """Invoke the script's __main__ guard with the given argv.

        runpy.run_path executes the file with __name__ == "__main__", so
        the tail block runs in this process and is picked up by
        coverage.py. sys.exit inside the block raises SystemExit, which we
        catch and return the code from.
        """
        import runpy
        old_argv = sys.argv[:]
        sys.argv = argv
        try:
            try:
                runpy.run_path(str(self.SCRIPT), run_name="__main__")
                return 0
            except SystemExit as e:
                code = e.code
                if code is None:
                    return 0
                if isinstance(code, int):
                    return code
                return 1
        finally:
            sys.argv = old_argv

    def _write_valid_formula(self, tmpdir, name="valid-tool"):
        klass = name.replace('-', '').capitalize()
        (tmpdir / f"{name}.rb").write_text(textwrap.dedent(f"""
            class {klass} < Formula
              desc "test tool"
              homepage "https://github.com/kubestellar/kubestellar"
              version "1.2.3"
              url "https://github.com/kubestellar/kubestellar/releases/download/v1.2.3/{name}-1.2.3.tar.gz"
              sha256 "0000000000000000000000000000000000000000000000000000000000000000"
              license "Apache-2.0"
              def install
                bin.install "{name}"
              end
              test do
                system "true"
              end
            end
            """).strip() + "\n")

    def test_cli_uses_argv_when_provided(self):
        # Explicit dir via argv[1]: exits 0.
        with tempfile.TemporaryDirectory() as td:
            formula_dir = Path(td) / "custom-formula-dir"
            formula_dir.mkdir()
            self._write_valid_formula(formula_dir, name="valid-tool")

            rc = self._run_as_main(["validate_formulae.py", str(formula_dir)])

            self.assertEqual(rc, 0)

    def test_cli_defaults_to_Formula_when_no_argv(self):
        # No argv[1]: falls back to Path("Formula") resolved against CWD.
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / "Formula").mkdir()
            self._write_valid_formula(tmp / "Formula", name="default-tool")

            old_cwd = Path.cwd()
            try:
                import os
                os.chdir(tmp)
                rc = self._run_as_main(["validate_formulae.py"])
            finally:
                os.chdir(old_cwd)

            self.assertEqual(rc, 0)

    def test_cli_returns_nonzero_on_validation_failure(self):
        # Directory missing → validate() returns 1 → SystemExit(1).
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "does-not-exist"

            rc = self._run_as_main(["validate_formulae.py", str(missing)])

            self.assertNotEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
