#!/usr/bin/env python3
"""Test-only synthetic Formula/*.rb bodies shared by
scripts/test_validate_formulae.py and its split-off sibling
scripts/test_validate_formulae_step_summary.py (see kubestellar/homebrew-
tap#541).

Historical note (kubestellar/homebrew-tap#565, #570): this module
previously also held the stanza regexes, the ``Formula/`` glob
(``FORMULA_DIR``), ``load_formulae()`` / ``list_formula_paths()``, and
``ALLOWED_URL_HOSTS`` / ``_extract_url_hosts()``. Those symbols were
imported by production ``scripts/validate_formulae.py`` (the module
Homebrew CI's *Validate Formulae* job runs) as well as by the
``test_formula_*_invariants.py`` suites, so a file named
``formula_test_fixtures.py`` was silently doubling as a production
helper. They now live in :mod:`formula_parser`; the backward-compatible
re-export block that briefly bridged the two homes was retired in
kubestellar/homebrew-tap#570 after every consumer had been migrated to
import from :mod:`formula_parser` directly. This file is now what its
name promises: test-only fixtures, nothing else.

Not itself a test module (does not match the ``test_*.py`` discovery
pattern), so ``unittest discover`` never picks it up directly.
"""

import textwrap


# Synthetic Formula/*.rb bodies shared by scripts/test_validate_formulae.py
# and its split-off sibling scripts/test_validate_formulae_step_summary.py
# (see kubestellar/homebrew-tap#541). The step-summary sibling was carved
# out of test_validate_formulae.py to keep that file's size manageable
# (see homebrew-tap#324 / #367); the fixture itself belongs in the shared
# module so both suites keep asserting against the same synthetic ops
# formula. Do not inline these back into the test modules — the whole
# point of the split is to prevent silent drift of "what a valid ops
# formula looks like" between the two suites.
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
