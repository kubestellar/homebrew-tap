"""Structural regression tests for Formula/*.rb.

These tests guard against copy-paste and codegen regressions that
validate_formulae.py does not catch:

  * Each formula must ship the full platform matrix
    (darwin_amd64, darwin_arm64, linux_amd64, linux_arm64) — a dropped
    on_linux/on_macos block or an accidentally deleted CPU arm would
    otherwise pass validate_formulae.py silently.
  * The four sha256 values inside one formula must all differ — if a
    codegen bug pastes the same digest for every platform, every
    non-primary-platform install would fail with a checksum error.
  * Every formula must declare its own `bin.install "<binary>"` matching
    the file stem, so a renamed formula does not accidentally install the
    wrong binary from an unrelated tarball.
  * Every formula must have `desc`, `homepage`, and a `test do` block —
    `brew audit` requires all three and a nightly regen that drops them
    would leave the tap unauditable.
"""

import re
from pathlib import Path

import pytest

FORMULA_DIR = Path(__file__).resolve().parent.parent / "Formula"

REQUIRED_PLATFORMS = {
    ("darwin", "amd64"),
    ("darwin", "arm64"),
    ("linux", "amd64"),
    ("linux", "arm64"),
}

# URL segment "<binary>_<version>_<os>_<arch>.tar.gz"
URL_PLATFORM_RE = re.compile(
    r'url\s+"[^"]*_(darwin|linux)_(amd64|arm64)\.tar\.gz"'
)
SHA256_LINE_RE = re.compile(r'sha256\s+"([0-9a-f]{64})"')


@pytest.fixture(scope="module")
def formulae():
    files = sorted(FORMULA_DIR.glob("*.rb"))
    assert files, f"no formulae found under {FORMULA_DIR}"
    return {p.stem: p.read_text() for p in files}


def test_all_formulae_are_readable(formulae):
    for name, text in formulae.items():
        assert text.strip(), f"{name}.rb is empty"


def test_each_formula_covers_all_four_platforms(formulae):
    for name, text in formulae.items():
        found = set(URL_PLATFORM_RE.findall(text))
        missing = REQUIRED_PLATFORMS - found
        assert not missing, (
            f"{name}.rb is missing platform URL(s): "
            f"{sorted(missing)} (found {sorted(found)})"
        )


def test_each_formula_has_four_distinct_sha256_values(formulae):
    for name, text in formulae.items():
        shas = SHA256_LINE_RE.findall(text)
        assert len(shas) == 4, (
            f"{name}.rb: expected exactly 4 sha256 lines, got {len(shas)}"
        )
        assert len(set(shas)) == 4, (
            f"{name}.rb: sha256 duplicates detected across platforms "
            f"(codegen copy-paste bug): {shas}"
        )


def test_each_formula_installs_matching_binary(formulae):
    for name, text in formulae.items():
        pattern = re.compile(rf'bin\.install\s+"{re.escape(name)}"')
        # Each platform arm should install the binary named after the formula.
        matches = pattern.findall(text)
        assert len(matches) == 4, (
            f"{name}.rb: expected 4 'bin.install \"{name}\"' lines "
            f"(one per platform), got {len(matches)}"
        )


def test_each_formula_declares_metadata(formulae):
    for name, text in formulae.items():
        assert re.search(r'^\s*desc\s+"[^"]+"', text, re.MULTILINE), \
            f"{name}.rb missing desc"
        assert re.search(
            r'^\s*homepage\s+"https://github\.com/kubestellar/[^"]+"',
            text, re.MULTILINE,
        ), f"{name}.rb missing/invalid homepage"
        assert re.search(r'^\s*test\s+do\s*$', text, re.MULTILINE), \
            f"{name}.rb missing 'test do' block"
        assert re.search(r'^\s*license\s+"[^"]+"', text, re.MULTILINE), \
            f"{name}.rb missing license"


def test_desc_length_within_homebrew_guideline(formulae):
    # Homebrew's `brew audit` warns when desc is missing or >80 chars.
    for name, text in formulae.items():
        m = re.search(r'^\s*desc\s+"([^"]+)"', text, re.MULTILINE)
        assert m, f"{name}.rb missing desc"
        desc = m.group(1)
        assert 1 <= len(desc) <= 80, (
            f"{name}.rb desc length {len(desc)} outside 1..80: {desc!r}"
        )


def test_url_binary_prefix_matches_formula_name(formulae):
    # The URL basename must start with "<formula-name>_" so that a rename
    # doesn't leave a stale tarball prefix pointing at the old binary.
    url_re = re.compile(r'url\s+"([^"]+)"')
    for name, text in formulae.items():
        urls = url_re.findall(text)
        assert urls, f"{name}.rb has no url lines"
        for url in urls:
            basename = url.rsplit("/", 1)[-1]
            assert basename.startswith(f"{name}_"), (
                f"{name}.rb: url basename {basename!r} does not start "
                f"with formula name prefix '{name}_'"
            )
