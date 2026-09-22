#!/usr/bin/env python3
"""Shared fixtures for the Formula/*.rb policy/consistency/platform test
modules split out of test_validate_formulae.py (see kubestellar/homebrew-
tap#324). Not itself a test module (does not match the `test_*.py`
discovery pattern), so `unittest discover` never picks it up directly."""

import re
from pathlib import Path

FORMULA_DIR = Path(__file__).resolve().parent.parent / "Formula"

# Canonical stanza regexes shared by the test_formula_*_invariants.py /
# test_crossformula_*_invariants.py modules (see kubestellar/homebrew-
# tap#450). These used to be re-declared independently in ~16 files —
# most copies were character-for-character identical, but `url`/`version`
# had two divergent forms in the wild:
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


# Homebrew formulae in this tap may pull artifacts only from these hosts.
# Extend this set with a code change (reviewed) when a new upstream lands.
ALLOWED_URL_HOSTS = {
    "github.com",
    "objects.githubusercontent.com",  # GH release CDN redirects land here
}


def _extract_url_hosts(text: str) -> list[str]:
    """Return hosts of every `url "..."` in a formula body, in order."""
    hosts = []
    for m in URL_LINE_RE.finditer(text):
        url = m.group(1)
        # crude but sufficient: strip scheme, take everything before the
        # next `/`. Formulae never use userinfo or non-default ports.
        scheme, _, rest = url.partition("://")
        host = rest.split("/", 1)[0]
        hosts.append((url, scheme, host))
    return hosts
