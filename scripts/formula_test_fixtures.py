#!/usr/bin/env python3
"""Shared fixtures for the Formula/*.rb policy/consistency/platform test
modules split out of test_validate_formulae.py (see kubestellar/homebrew-
tap#324). Not itself a test module (does not match the `test_*.py`
discovery pattern), so `unittest discover` never picks it up directly."""

import re
from pathlib import Path

FORMULA_DIR = Path(__file__).resolve().parent.parent / "Formula"


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
    for m in re.finditer(r'^\s*url\s+"([^"]+)"', text, re.MULTILINE):
        url = m.group(1)
        # crude but sufficient: strip scheme, take everything before the
        # next `/`. Formulae never use userinfo or non-default ports.
        scheme, _, rest = url.partition("://")
        host = rest.split("/", 1)[0]
        hosts.append((url, scheme, host))
    return hosts
