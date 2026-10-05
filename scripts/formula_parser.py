#!/usr/bin/env python3
"""Shared production-side parser and discovery helpers for Formula/*.rb.

Split out of scripts/formula_test_fixtures.py (see kubestellar/homebrew-
tap#565) so that production code (scripts/validate_formulae.py, which
Homebrew CI's `Validate Formulae` job runs) and the ~25 policy /
consistency / cross-formula invariant test modules can share the same
stanza regexes, `Formula/` glob, and load helpers without importing
from a module whose *name* announces "test fixtures".

Only pure test-only synthetic bodies (VALID_OPS / VALID_DEPLOY) remain in
scripts/formula_test_fixtures.py — everything else lives here.

Not itself a test module (does not match the `test_*.py` discovery
pattern), so `unittest discover` never picks it up directly.
"""

import re
import sys
from pathlib import Path

FORMULA_DIR = Path(__file__).resolve().parent.parent / "Formula"


# Canonical stanza regexes shared by scripts/validate_formulae.py and the
# test_formula_*_invariants.py / test_crossformula_*_invariants.py modules
# (see kubestellar/homebrew-tap#450). These used to be re-declared
# independently in ~16 files — most copies were character-for-character
# identical, but `url`/`version` had two divergent forms in the wild:
#
#   * anchored, multiline: r'^\s*url\s+"([^"]+)"' with re.MULTILINE —
#     only matches a `url "..."` that starts its own line (e.g. does not
#     match inside a commented-out line unless the `#` itself is
#     stripped by the caller).
#   * inline/unanchored: r'url\s+"([^"]+)"' with no re.MULTILINE — also
#     matches `url "..."` embedded mid-line (e.g. after a `#` comment
#     marker), which the anchored form does not.
#
# Both forms are kept here, named distinctly, so callers keep whichever
# behavior they previously relied on instead of silently changing which
# lines match (a real behavior change, not just deduplication).
VERSION_LINE_RE = re.compile(r'^\s*version\s+"([^"]+)"', re.MULTILINE)
URL_LINE_RE = re.compile(r'^\s*url\s+"([^"]+)"', re.MULTILINE)
HOMEPAGE_LINE_RE = re.compile(r'^\s*homepage\s+"([^"]+)"', re.MULTILINE)
DESC_LINE_RE = re.compile(r'^\s*desc\s+"([^"]+)"', re.MULTILINE)
LICENSE_LINE_RE = re.compile(r'^\s*license\s+"([^"]+)"', re.MULTILINE)
SHA256_LINE_RE = re.compile(r'sha256\s+"([^"]+)"')

# Unanchored/inline variants — intentionally distinct from the anchored
# forms above (see note above); do not merge them.
URL_INLINE_RE = re.compile(r'url\s+"([^"]+)"')

# .../releases/download/<TAG>/<FILENAME>
RELEASE_URL_RE = re.compile(r"/releases/download/(?P<tag>[^/]+)/(?P<file>[^/]+)$")


def load_formulae() -> dict[str, str]:
    """Return every Formula/*.rb file as {stem: text}.

    Shared loader for the test_*.py invariant modules (see kubestellar/
    homebrew-tap#328 and #329): they used to each re-implement this glob
    + non-empty assertion independently, with several slightly divergent
    variants (some encoded reads, some didn't; some raised, some didn't
    check at all). Behavior here matches the strictest of those variants
    unchanged: sorted glob of "*.rb", UTF-8 text, raise if none found.
    """
    files = sorted(FORMULA_DIR.glob("*.rb"))
    if not files:
        raise AssertionError(f"no formulae found under {FORMULA_DIR}")
    return {p.stem: p.read_text(encoding="utf-8") for p in files}


def list_formula_paths() -> list[Path]:
    """Return every Formula/*.rb as a sorted ``list[Path]``.

    Path-shaped sibling of ``load_formulae()`` for setUpClass callers
    that need the paths themselves (typically to read the body later, or
    to use ``path.name`` in a failure message). Matches ``load_formulae()``'s
    empty-case policy: sorted glob of ``*.rb``, raise if none found.

    Motivating history (see kubestellar/homebrew-tap#559): 17
    ``test_formula_*.py`` modules previously re-implemented this glob
    independently in their own ``setUpClass`` with divergent empty-case
    behavior — some ``raise unittest.SkipTest(...)`` (silently skipping
    the module on an empty tap), some ``assert cls.formulae, ...``
    (hard-failing with slightly different wording). This helper picks
    the same "raise on empty" direction the ``load_formulae()`` docstring
    already documents, so a bad ``FORMULA_DIR`` produces one clear error
    across every invariant module instead of a mixed skip/fail signal.
    """
    files = sorted(FORMULA_DIR.glob("*.rb"))
    if not files:
        raise AssertionError(f"no formulae found under {FORMULA_DIR}")
    return files


# Homebrew formulae in this tap may pull artifacts only from these hosts.
# Extend this set with a code change (reviewed) when a new upstream lands.
ALLOWED_URL_HOSTS = {
    "github.com",
    "objects.githubusercontent.com",  # GH release CDN redirects land here
}


def _extract_url_hosts(text: str) -> list[tuple[str, str, str]]:
    """Return `(url, scheme, host)` for every `url "..."` in a formula body,
    in order of appearance."""
    hosts = []
    for m in URL_LINE_RE.finditer(text):
        url = m.group(1)
        # crude but sufficient: strip scheme, take everything before the
        # next `/`. Formulae never use userinfo or non-default ports.
        scheme, _, rest = url.partition("://")
        host = rest.split("/", 1)[0]
        hosts.append((url, scheme, host))
    return hosts


# `bin.install "<name>"` — closes out the (url, sha256) pair most recently
# seen above it into a triple; see extract_release_triples() below.
BIN_INSTALL_LINE_RE = re.compile(r'bin\.install\s+"([^"]+)"')


def extract_release_triples(text: str) -> list[tuple[str, str, str]]:
    """Return `(url, sha256, bin_name)` for every per-arch release branch
    in a formula body, in order of appearance.

    Single owner of the (url, sha256, bin_name) extraction contract.
    scripts/verify_release_artifacts.sh (which downloads and verifies the
    actual release tarballs) shells out to this function via the
    `--triples` CLI below instead of keeping its own bash parser, and
    scripts/test_verify_release_artifacts_parser_parity.py asserts that
    shell-out path agrees with calling this function in-process on every
    real Formula/*.rb (see kubestellar/homebrew-tap#647).

    Scans line-by-line, tracking the most recently seen `url "..."` /
    `sha256 "..."` pair until the next `bin.install "..."` closes it into
    a triple — matching the GoReleaser-generated shape: url, then sha256,
    then `define_method(:install) { bin.install "<name>" }`, repeated
    once per Hardware::CPU branch.
    """
    triples: list[tuple[str, str, str]] = []
    url = ""
    sha = ""
    for line in text.splitlines():
        url_match = URL_INLINE_RE.search(line)
        if url_match is not None:
            url = url_match.group(1)
            sha = ""
            continue
        sha_match = SHA256_LINE_RE.search(line)
        if sha_match is not None:
            sha = sha_match.group(1)
            continue
        bin_match = BIN_INSTALL_LINE_RE.search(line)
        if bin_match is not None:
            bin_name = bin_match.group(1)
            if url and sha:
                triples.append((url, sha, bin_name))
            url = ""
            sha = ""
    return triples


def _main(argv: list[str]) -> int:
    """CLI: `formula_parser.py --triples <Formula/foo.rb>` prints one
    `url\\tsha256\\tbin_name` TSV line per extract_release_triples() triple,
    for scripts/verify_release_artifacts.sh to consume without keeping a
    second, un-sync'd bash implementation of the extraction (see
    kubestellar/homebrew-tap#647)."""
    if len(argv) != 2 or argv[0] != "--triples":
        print("usage: formula_parser.py --triples <formula.rb>", file=sys.stderr)
        return 2
    text = Path(argv[1]).read_text(encoding="utf-8")
    for url, sha, bin_name in extract_release_triples(text):
        print(f"{url}\t{sha}\t{bin_name}")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
