#!/usr/bin/env python3
"""Install/test-block and homepage/URL consistency invariants, plus CLI
entrypoint coverage for validate_formulae.py.

Split from test_validate_formulae.py (classes moved verbatim).
"""

import re
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from formula_test_fixtures import FORMULA_DIR, _extract_url_hosts

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
