#!/usr/bin/env python3
"""Extra stray-stanza guards for Formula/*.rb.

The existing structural test file (test_formula_structural_further_invariants.py)
forbids `depends_on`, `resource`, `livecheck`, `revision`, `keg_only`,
`deprecate!`, `disable!`, `patch do`, and `option "..."`. The release-artifact
test file forbids `bottle do` blocks.

Several other Homebrew stanzas are equally invalid for these GoReleaser-
generated binary tap formulae but are NOT guarded anywhere in the suite yet.
A codegen template rewrite (or a hand-edit merged past review) that added any
of them would break the tap in different, user-visible ways:

  * `conflicts_with "..."` — would refuse to install alongside an unrelated
    formula and leak a diagnostic that has nothing to do with these CLIs.
  * `caveats` — Homebrew prints them on every install/upgrade; a template
    regression that emits caveats would spam every user for the life of the
    release.
  * `service do` — turns a plain CLI into a background service; users would
    silently get a launchd/systemd unit they never asked for.
  * `head "..."` line or `head do` block — points brew at an unpinned git
    ref; `brew install --HEAD` would then bypass the pinned release tarball
    and its sha256 pin, defeating the whole point of shipping binary tap
    formulae.
  * `plist_options` — legacy launchd hook; Homebrew deprecated it in favor
    of `service do`, and it has no place in a CLI shim either way.
  * `post_install do` — the tarballs are already the fully installable
    artifact; any post_install block indicates hand-edited logic that would
    be clobbered on the next GoReleaser regeneration.
  * `env :std` / `env :userpaths` — these are build-env selectors for
    from-source formulae; on a pre-built-binary formula they are inert at
    best and confuse `brew audit` at worst.
  * `bottle :unneeded` / `bottle :any` (single-line form) — the existing
    guard only catches multi-line `bottle do` blocks, but the single-line
    symbol form is equally a codegen artifact from source-formula templates
    and should not appear on a tap that ships its own tarballs.

Each guard here uses the same MULTILINE regex + `subTest(formula=name)`
pattern as the existing structural invariant file so failures name the
offending formula individually.
"""

import re
import unittest
from pathlib import Path

FORMULA_DIR = Path(__file__).resolve().parent.parent / "Formula"


CONFLICTS_WITH_RE = re.compile(r'^\s*conflicts_with\b', re.MULTILINE)
CAVEATS_RE = re.compile(r'^\s*(?:def\s+caveats\b|caveats\s+do\b)', re.MULTILINE)
SERVICE_BLOCK_RE = re.compile(r'^\s*service\s+do\b', re.MULTILINE)
HEAD_LINE_RE = re.compile(r'^\s*head\s+"', re.MULTILINE)
HEAD_BLOCK_RE = re.compile(r'^\s*head\s+do\b', re.MULTILINE)
PLIST_OPTIONS_RE = re.compile(r'^\s*plist_options\b', re.MULTILINE)
PLIST_DEF_RE = re.compile(r'^\s*def\s+plist\b', re.MULTILINE)
POST_INSTALL_RE = re.compile(r'^\s*(?:def\s+post_install\b|post_install\s+do\b)',
                             re.MULTILINE)
ENV_STANZA_RE = re.compile(r'^\s*env\s+:[a-z_]+\b', re.MULTILINE)
BOTTLE_SYMBOL_RE = re.compile(r'^\s*bottle\s+:[a-z_]+\b', re.MULTILINE)


class FormulaLoader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.formulae = {
            p.stem: p.read_text(encoding="utf-8")
            for p in sorted(FORMULA_DIR.glob("*.rb"))
        }
        assert cls.formulae, "no formulae found under Formula/"


class StrayStanzaGuards(FormulaLoader):
    """Stanzas that must never appear in these binary tap formulae."""

    def test_no_conflicts_with_stanza(self):
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                self.assertIsNone(
                    CONFLICTS_WITH_RE.search(text),
                    f"{name}.rb has a `conflicts_with` stanza — these CLIs "
                    f"do not conflict with any Homebrew formula; a stray "
                    f"conflicts_with would refuse installs with an "
                    f"unrelated diagnostic",
                )

    def test_no_caveats_stanza(self):
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                self.assertIsNone(
                    CAVEATS_RE.search(text),
                    f"{name}.rb has a `caveats` stanza — Homebrew prints "
                    f"caveats on every install/upgrade; a codegen leak "
                    f"would spam every user for the life of the release",
                )

    def test_no_service_block(self):
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                self.assertIsNone(
                    SERVICE_BLOCK_RE.search(text),
                    f"{name}.rb has a `service do` block — these are "
                    f"one-shot CLIs; a service block would silently install "
                    f"a launchd/systemd unit the user never asked for",
                )

    def test_no_head_stanza(self):
        # Both the single-line `head "<git-url>"` form and the multi-line
        # `head do` block would let `brew install --HEAD` bypass the
        # pinned release tarball + sha256, defeating the whole tap model.
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                self.assertIsNone(
                    HEAD_LINE_RE.search(text),
                    f"{name}.rb has a `head \"...\"` line — `brew install "
                    f"--HEAD` would bypass the pinned release tarball and "
                    f"its sha256 pin",
                )
                self.assertIsNone(
                    HEAD_BLOCK_RE.search(text),
                    f"{name}.rb has a `head do` block — `brew install "
                    f"--HEAD` would bypass the pinned release tarball and "
                    f"its sha256 pin",
                )

    def test_no_plist_stanzas(self):
        # `plist_options` and a `def plist` method are the legacy launchd
        # hook Homebrew deprecated in favour of `service do`. Neither has
        # any place in a CLI shim.
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                self.assertIsNone(
                    PLIST_OPTIONS_RE.search(text),
                    f"{name}.rb has a `plist_options` stanza — legacy "
                    f"launchd hook; invalid on a plain CLI formula",
                )
                self.assertIsNone(
                    PLIST_DEF_RE.search(text),
                    f"{name}.rb defines a `plist` method — legacy launchd "
                    f"hook; invalid on a plain CLI formula",
                )

    def test_no_post_install_stanza(self):
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                self.assertIsNone(
                    POST_INSTALL_RE.search(text),
                    f"{name}.rb has a `post_install` block/method — the "
                    f"tarballs are the complete installable artifact; any "
                    f"post_install is a hand-edit that will be clobbered "
                    f"on the next GoReleaser regeneration",
                )

    def test_no_env_stanza(self):
        # env :std / env :userpaths select build-env behaviour for
        # from-source formulae; a pre-built binary formula has no build
        # step, so the stanza is at best inert and at worst confuses
        # `brew audit`.
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                self.assertIsNone(
                    ENV_STANZA_RE.search(text),
                    f"{name}.rb has an `env :...` build-env stanza — "
                    f"pre-built binary formulae have no build step; the "
                    f"stanza is meaningless here and trips `brew audit`",
                )

    def test_no_single_line_bottle_symbol(self):
        # The existing release-artifact test forbids `bottle do` blocks,
        # but the single-line symbol form (`bottle :unneeded`,
        # `bottle :any_skip_relocation`, ...) is a distinct legacy stanza
        # emitted by from-source templates and is equally invalid on a
        # tap that ships its own tarballs.
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                self.assertIsNone(
                    BOTTLE_SYMBOL_RE.search(text),
                    f"{name}.rb has a `bottle :symbol` stanza — the tap "
                    f"ships its own release tarballs; single-line bottle "
                    f"symbols are a from-source template artifact",
                )


if __name__ == "__main__":
    unittest.main()
