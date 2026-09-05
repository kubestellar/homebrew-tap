#!/usr/bin/env python3
"""Validate Homebrew formula metadata for drift: version/URL mismatch,
malformed sha256, missing sha256 after url, and paired formula lockstep."""

import json
import re
import sys
from pathlib import Path

SHA256_RE = re.compile(r'^[0-9a-f]{64}$')

# Prefix for the machine-readable CI summary line (see emit_summary()).
# Grep this marker in CI logs to get a structured pass/fail count without
# parsing the free-text OK:/FAIL: lines.
SUMMARY_PREFIX = "VALIDATE_FORMULAE_SUMMARY:"

# Formulae that must share the same version string
LOCKSTEP_GROUPS = [
    {"kubestellar-ops", "kubestellar-deploy"},
]


def parse_formula(path: Path) -> dict:
    """Return parsed metadata for a single .rb file."""
    text = path.read_text()
    lines = text.splitlines()

    # version
    version_matches = re.findall(r'^\s*version\s+"([^"]+)"', text, re.MULTILINE)
    if len(version_matches) == 0:
        return {"error": f"{path.name}: no version line found"}
    if len(version_matches) > 1:
        return {"error": f"{path.name}: multiple version lines found: {version_matches}"}
    version = version_matches[0]

    errors = []

    # url / sha256 checks
    url_line_indices = [
        i for i, l in enumerate(lines)
        if re.match(r'^\s*url\s+"', l)
    ]
    for idx in url_line_indices:
        url_match = re.search(r'url\s+"([^"]+)"', lines[idx])
        if not url_match:
            continue
        url = url_match.group(1)

        # version must appear in url
        if version not in url:
            errors.append(
                f"{path.name}: url does not embed version '{version}': {url}"
            )

        # find next non-blank line after url
        sha_idx = None
        for j in range(idx + 1, min(idx + 5, len(lines))):
            if lines[j].strip():
                sha_idx = j
                break

        if sha_idx is None:
            errors.append(f"{path.name}: no line after url at line {idx + 1}")
            continue

        sha_match = re.search(r'sha256\s+"([^"]+)"', lines[sha_idx])
        if not sha_match:
            errors.append(
                f"{path.name}: expected sha256 after url (line {idx + 1}), "
                f"got: {lines[sha_idx].strip()!r}"
            )
            continue

        sha = sha_match.group(1)
        if not SHA256_RE.match(sha):
            errors.append(
                f"{path.name}: malformed sha256 '{sha}' (must be 64 lowercase hex chars)"
            )

    return {"version": version, "errors": errors, "name": path.stem}


def emit_summary(status: str, formula_count: int, error_count: int) -> None:
    """Print a single-line JSON summary for CI-log observability.

    This is stdout-only (no external data flow, no exporter) and exists so
    CI tooling can grep a structured pass/fail record instead of parsing the
    free-text OK:/FAIL: lines above it.
    """
    summary = {
        "status": status,
        "formula_count": formula_count,
        "error_count": error_count,
    }
    print(f"{SUMMARY_PREFIX} {json.dumps(summary, sort_keys=True)}")


def validate(formula_dir: Path) -> int:
    """Run all checks; return exit code (0 = pass, 1 = fail)."""
    rb_files = sorted(formula_dir.glob("*.rb"))
    if not rb_files:
        print(f"ERROR: no .rb files found in {formula_dir}", file=sys.stderr)
        emit_summary(status="error", formula_count=0, error_count=1)
        return 1

    all_errors = []
    parsed: dict[str, dict] = {}

    for path in rb_files:
        result = parse_formula(path)
        if "error" in result:
            all_errors.append(result["error"])
        else:
            parsed[path.stem] = result
            all_errors.extend(result["errors"])

    # lockstep version checks
    for group in LOCKSTEP_GROUPS:
        available = {name: parsed[name] for name in group if name in parsed}
        if len(available) < 2:
            continue
        versions = {d["version"] for d in available.values()}
        if len(versions) > 1:
            detail = ", ".join(f"{n}={d['version']}" for n, d in sorted(available.items()))
            all_errors.append(
                f"lockstep version mismatch in group {sorted(group)}: {detail}"
            )

    if all_errors:
        for e in all_errors:
            print(f"FAIL: {e}", file=sys.stderr)
        emit_summary(status="fail", formula_count=len(rb_files), error_count=len(all_errors))
        return 1

    names = [p.stem for p in rb_files]
    print(f"OK: {len(rb_files)} formula(e) validated: {', '.join(names)}")
    emit_summary(status="pass", formula_count=len(rb_files), error_count=0)
    return 0


if __name__ == "__main__":
    formula_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("Formula")
    sys.exit(validate(formula_dir))
