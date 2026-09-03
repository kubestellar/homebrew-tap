#!/usr/bin/env python3
"""Shared fixtures for the test_validate_formulae / formula-invariant suites.

Not collected by unittest discover (filename does not match test_*.py).
"""

import re
import textwrap
from pathlib import Path

FORMULA_DIR = Path(__file__).resolve().parent.parent / "Formula"

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
