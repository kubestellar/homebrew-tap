#!/usr/bin/env bash
# compile_requirements_dev.sh — regenerate the hash-pinned
# requirements-dev.txt lockfile from requirements-dev.in while keeping
# the lockfile's hand-written header comment block intact.
#
# requirements-dev.txt carries a header explaining the hash-pin
# rationale (why CI installs it with --require-hashes). pip-compile is
# run with --no-header because its own header is noisy and embeds the
# absolute invocation, but that means a bare `pip-compile` call
# overwrites the file WITHOUT the explanatory header, immediately
# producing a lockfile inconsistent with the checked-in one. This
# wrapper makes regeneration a single command that reapplies the header
# automatically, so no one has to hand-restore it.
#
# The header is the leading run of `#` comment lines in the existing
# requirements-dev.txt, up to the first blank line. It is preserved
# verbatim; the compiled requirement lines replace everything below it.
#
# Usage:
#   scripts/compile_requirements_dev.sh            # regenerate in place
#   scripts/compile_requirements_dev.sh --upgrade  # extra args go to pip-compile
#
# Env vars:
#   PIP_COMPILE   pip-compile executable (default: pip-compile on PATH;
#                 `pip install pip-tools` provides it)
#   REQ_IN        input file  (default: <repo>/requirements-dev.in)
#   REQ_OUT       output file (default: <repo>/requirements-dev.txt)
#
# Exit status: 0 on success; 1 if the existing lockfile has no header
# comment block to preserve, or if pip-compile fails (in which case the
# lockfile is left untouched).

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pip_compile="${PIP_COMPILE:-pip-compile}"
req_in="${REQ_IN:-$repo_root/requirements-dev.in}"
req_out="${REQ_OUT:-$repo_root/requirements-dev.txt}"

if [ ! -f "$req_in" ]; then
  echo "compile_requirements_dev.sh: input file not found: $req_in" >&2
  exit 1
fi
if [ ! -f "$req_out" ]; then
  echo "compile_requirements_dev.sh: existing lockfile not found: $req_out" >&2
  echo "  (the header comment block is read from it; restore it from git first)" >&2
  exit 1
fi
if ! command -v "$pip_compile" >/dev/null 2>&1; then
  echo "compile_requirements_dev.sh: $pip_compile not found; run: pip install pip-tools" >&2
  exit 1
fi

# Extract the header: leading `#` lines up to (not including) the first
# blank line. Stop at the first non-comment line too, so a lockfile that
# somehow lost its header yields an empty result and we refuse below
# rather than silently writing a header-less file again.
header="$(awk '
  /^#/ { print; next }
  { exit }
' "$req_out")"

if [ -z "$header" ]; then
  echo "compile_requirements_dev.sh: $req_out has no leading header comment block to preserve" >&2
  echo "  (restore it from git — see requirements-dev.in for what it documents)" >&2
  exit 1
fi

tmp_body="$(mktemp)"
trap 'rm -f "$tmp_body"' EXIT

"$pip_compile" --generate-hashes --no-annotate --no-header \
  --output-file="$tmp_body" "$req_in" "$@"

{
  printf '%s\n\n' "$header"
  cat "$tmp_body"
} > "$req_out"

echo "compile_requirements_dev.sh: wrote $req_out (header preserved, $(grep -c '==' "$tmp_body") pinned requirement(s))"
