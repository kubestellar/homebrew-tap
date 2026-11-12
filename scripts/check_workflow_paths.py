#!/usr/bin/env python3
"""Gate: a workflow's ``paths:`` filter must cover every file it depends on.

For every ``.github/workflows/*.yml`` that declares a ``paths:`` filter on
``push`` or ``pull_request``, this script collects the repository files the
workflow depends on and fails if any of them would not re-trigger it:

* the workflow file itself;
* every ``scripts/…`` / ``.github/…`` file the workflow names (``run:``
  lines, ``uses: ./…`` local actions);
* top-level config files it names (``.coveragerc``, ``requirements-dev.txt``,
  ``jscpd-baseline.json``, …);
* one level of transitive dependencies: ``lib_*.sh`` sourced by a referenced
  shell script, and local ``scripts/*.py`` modules imported by a referenced
  Python script.

A PR that edits only a delegated helper script must still run the CI that
exercises it (kubestellar/homebrew-tap#539, #566, #790). No third-party YAML
parser is needed: the extraction is line-based and deliberately conservative
(a token only counts when it names a file that exists in the checkout).

Usage: ``python3 scripts/check_workflow_paths.py [--root DIR]``
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

WORKFLOW_DIR = ".github/workflows"
SCRIPTS_DIR = "scripts"
TRIGGERS = ("push", "pull_request")

PATHS_LINE_RE = re.compile(r"^(\s*)paths:\s*$")
LIST_ITEM_RE = re.compile(r"""^(\s*)-\s*['"]?([^'"#]+?)['"]?\s*(?:#.*)?$""")
KEY_LINE_RE = re.compile(r"^(\s*)([A-Za-z_][\w-]*):")
# Repo-relative paths a workflow may invoke or read.
REPO_PATH_RE = re.compile(r"(?<![\w/.-])(?:\./)?((?:\.github/[\w-]+|scripts)/[\w./-]+)")
# Root-level config files a workflow may read (`.coveragerc`, `foo.json`, …).
ROOT_FILE_RE = re.compile(
    r"(?<![\w/.-])(\.?[\w-]+(?:\.(?:txt|json|in|toml|cfg|ini|yml|yaml)|rc))(?![\w/.-])"
)
COMMENT_RE = re.compile(r"(^|\s)#.*$", re.M)
LIB_SOURCE_RE = re.compile(r"\b(lib_\w+\.sh)\b")
PY_IMPORT_RE = re.compile(r"^\s*(?:from\s+(\w+)\s+import|import\s+(\w+))", re.M)


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a GitHub path-filter glob into a regex.

    ``**`` matches any characters including ``/``; ``*`` and ``?`` do not
    cross a path separator — the same rules GitHub applies to ``paths:``.
    """
    out = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        if c == "*":
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile("^" + "".join(out) + "$")


def path_covered(path: str, patterns: list[str]) -> bool:
    """True when ``path`` matches the filter list (honouring ``!`` negations)."""
    covered = False
    for pattern in patterns:
        negate = pattern.startswith("!")
        regex = glob_to_regex(pattern[1:] if negate else pattern)
        if regex.match(path):
            covered = not negate
    return covered


def parse_path_filters(text: str) -> dict[str, list[str]]:
    """Return ``{trigger: [patterns]}`` for each ``paths:`` block under ``on:``.

    The owning trigger is the nearest preceding key with a shallower indent
    than the ``paths:`` line.
    """
    lines = text.splitlines()
    filters: dict[str, list[str]] = {}
    for idx, line in enumerate(lines):
        m = PATHS_LINE_RE.match(line)
        if not m:
            continue
        indent = len(m.group(1))
        trigger = None
        for prev in reversed(lines[:idx]):
            km = KEY_LINE_RE.match(prev)
            if km and len(km.group(1)) < indent:
                trigger = km.group(2)
                break
        if trigger not in TRIGGERS:
            continue
        items: list[str] = []
        for nxt in lines[idx + 1 :]:
            im = LIST_ITEM_RE.match(nxt)
            if not im or len(im.group(1)) < indent:
                break
            items.append(im.group(2).strip())
        filters[trigger] = items
    return filters


def _existing(root: Path, candidates: set[str]) -> set[str]:
    found = set()
    for rel in candidates:
        rel = rel.rstrip("/.")
        target = root / rel
        if target.is_file():
            found.add(rel)
        elif target.is_dir():
            # A local action directory: any file under it should re-trigger.
            found.add(rel + "/")
    return found


def transitive_deps(root: Path, rel: str) -> set[str]:
    """Direct helpers a referenced script pulls in (one level only)."""
    deps: set[str] = set()
    body = (root / rel).read_text(encoding="utf-8", errors="replace")
    if rel.endswith(".sh"):
        deps.update(f"{SCRIPTS_DIR}/{name}" for name in LIB_SOURCE_RE.findall(body))
    elif rel.endswith(".py"):
        for a, b in PY_IMPORT_RE.findall(body):
            deps.add(f"{SCRIPTS_DIR}/{a or b}.py")
    return {d for d in deps if (root / d).is_file() and d != rel}


def referenced_files(root: Path, workflow_rel: str, text: str) -> set[str]:
    """Files ``workflow_rel`` depends on, including itself."""
    text = COMMENT_RE.sub(r"\1", text)
    refs = _existing(root, set(REPO_PATH_RE.findall(text)))
    refs |= _existing(root, {t for t in ROOT_FILE_RE.findall(text) if "/" not in t})
    for rel in list(refs):
        if rel.startswith(SCRIPTS_DIR + "/"):
            refs |= transitive_deps(root, rel)
    refs.add(workflow_rel)
    return refs


def check_workflow(root: Path, workflow_rel: str) -> list[str]:
    """Return human-readable violations for one workflow (empty = clean)."""
    text = (root / workflow_rel).read_text(encoding="utf-8")
    filters = parse_path_filters(text)
    if not filters:
        return []
    violations = []
    for rel in sorted(referenced_files(root, workflow_rel, text)):
        probe = rel + "action.yml" if rel.endswith("/") else rel
        for trigger, patterns in sorted(filters.items()):
            if not path_covered(probe, patterns):
                violations.append(f"{workflow_rel}: {trigger}.paths does not cover {rel}")
    return violations


def check_all(root: Path) -> list[str]:
    violations: list[str] = []
    wf_dir = root / WORKFLOW_DIR
    for path in sorted(wf_dir.glob("*.yml")) + sorted(wf_dir.glob("*.yaml")):
        violations.extend(check_workflow(root, os.path.relpath(path, root)))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="repository root (default: cwd)")
    args = parser.parse_args(argv)
    violations = check_all(Path(args.root).resolve())
    if violations:
        print("workflow path-filter gate: FAIL", file=sys.stderr)
        for line in violations:
            print(f"  {line}", file=sys.stderr)
        print(
            "\nAdd the missing files to the workflow's `paths:` filter(s) so a change "
            "to them re-runs the workflow.",
            file=sys.stderr,
        )
        return 1
    print("workflow path-filter gate: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
