#!/usr/bin/env python3
"""Validate Homebrew formula metadata for drift: version/URL mismatch,
malformed sha256, missing sha256 after url, and paired formula lockstep."""

import json
import os
import re
import sys
from pathlib import Path

from formula_parser import (
    SHA256_LINE_RE,
    URL_INLINE_RE,
    VERSION_LINE_RE,
)

# Validates the *value* captured by SHA256_LINE_RE (64 lowercase hex chars),
# not the sha256 stanza itself; kept local because it has no fixtures peer.
SHA256_VALUE_RE = re.compile(r'^[0-9a-f]{64}$')

# Prefix for the machine-readable CI summary line (see emit_summary()).
# Grep this marker in CI logs to get a structured pass/fail count without
# parsing the free-text OK:/FAIL: lines.
SUMMARY_PREFIX = "VALIDATE_FORMULAE_SUMMARY:"

# Cap on how many individual errors are rendered in the $GITHUB_STEP_SUMMARY
# table so a pathological run (e.g. every formula broken) can't blow up the
# job summary size; the full list is still on stderr/stdout above.
MAX_STEP_SUMMARY_ERRORS = 20

# Formulae that must share the same version string
LOCKSTEP_GROUPS = [
    {"kubestellar-ops", "kubestellar-deploy"},
]

# Formulae published from a single upstream goreleaser `brews` target with
# no dedicated nightly counterpart (unlike kubestellar-ops/kubestellar-deploy,
# which always move in lockstep with each other). For these, a nightly
# goreleaser run and a stable release both publish to the *same* .rb file,
# so whichever ran most recently silently wins and the tap can serve a
# nightly build under the stable channel for the rest of the day. See
# kubestellar/homebrew-tap#423. This is a WARN, not a FAIL: the actual fix
# (publish nightlies to a separate formula, or skip brew publish for
# nightlies) must land in the upstream repo's goreleaser config, which this
# repo cannot enforce; the check only surfaces the current channel state so
# it isn't a silent surprise.
SINGLE_CHANNEL_FORMULAE = {"kc-agent"}

NIGHTLY_VERSION_RE = re.compile(r'-nightly\.\d+$')


def parse_formula(path: Path) -> dict:
    """Return parsed metadata for a single .rb file."""
    text = path.read_text()
    lines = text.splitlines()

    # version
    version_matches = VERSION_LINE_RE.findall(text)
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
        url_match = URL_INLINE_RE.search(lines[idx])
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

        sha_match = SHA256_LINE_RE.search(lines[sha_idx])
        if not sha_match:
            errors.append(
                f"{path.name}: expected sha256 after url (line {idx + 1}), "
                f"got: {lines[sha_idx].strip()!r}"
            )
            continue

        sha = sha_match.group(1)
        if not SHA256_VALUE_RE.match(sha):
            errors.append(
                f"{path.name}: malformed sha256 '{sha}' (must be 64 lowercase hex chars)"
            )

    return {"version": version, "errors": errors, "name": path.stem}


def find_nightly_channel_warnings(parsed: dict) -> list[str]:
    """Return a warning for every formula in SINGLE_CHANNEL_FORMULAE whose
    version currently looks like a nightly build (e.g. "0.3.42-nightly.20260916").

    These formulae have no dedicated nightly counterpart, so a nightly
    goreleaser run overwrites the same .rb file a stable release publishes
    to; `brew install`/`brew upgrade` then serves nightly builds under the
    stable channel until the next stable release happens to run. This is a
    warning, not a validation error, because the fix belongs in the
    upstream repo's goreleaser `brews` config (kubestellar/homebrew-tap#423),
    not in this tap; it only makes the current channel state visible
    instead of a silent surprise.
    """
    warnings = []
    for name in sorted(SINGLE_CHANNEL_FORMULAE):
        data = parsed.get(name)
        if data is None:
            continue
        version = data["version"]
        if NIGHTLY_VERSION_RE.search(version):
            warnings.append(
                f"{name}.rb is currently serving a nightly build ({version}) "
                "on its stable channel; the upstream goreleaser config must "
                "publish nightlies to a separate formula instead of "
                "overwriting this one (see kubestellar/homebrew-tap#423)"
            )
    return warnings


def emit_summary(
    status: str,
    formula_count: int,
    error_count: int,
    errors: list[str] | None = None,
) -> None:
    """Print a single-line JSON summary for CI-log observability, and also
    render it as a markdown table to $GITHUB_STEP_SUMMARY when running in
    GitHub Actions (that env var is set by the runner for every step; no
    workflow YAML edit is needed to opt in).

    Both outputs are stdout/file-only (no external data flow, no exporter):
    the JSON line lets CI tooling grep a structured pass/fail record instead
    of parsing the free-text OK:/FAIL: lines above it, and the step summary
    surfaces the same bounded fields in the GitHub Actions checks UI instead
    of requiring a reviewer to open the raw log.
    """
    summary = {
        "status": status,
        "formula_count": formula_count,
        "error_count": error_count,
    }
    print(f"{SUMMARY_PREFIX} {json.dumps(summary, sort_keys=True)}")
    _write_step_summary(status, formula_count, error_count, errors or [])


def _write_step_summary(
    status: str, formula_count: int, error_count: int, errors: list[str]
) -> None:
    """Append a markdown table to $GITHUB_STEP_SUMMARY, if set. No-op
    outside GitHub Actions (e.g. local runs, unit tests)."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    icon = "✅" if status == "pass" else "❌"
    lines = [
        "### Formula drift check",
        "",
        "| Status | Formulae checked | Errors |",
        "|--------|-------------------|--------|",
        f"| {icon} {status} | {formula_count} | {error_count} |",
    ]
    if errors:
        shown = errors[:MAX_STEP_SUMMARY_ERRORS]
        lines.append("")
        lines.append("<details><summary>Error details</summary>")
        lines.append("")
        for e in shown:
            lines.append(f"- {e}")
        if len(errors) > len(shown):
            lines.append(f"- ...and {len(errors) - len(shown)} more (see step log)")
        lines.append("")
        lines.append("</details>")
    lines.append("")

    with open(summary_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _write_step_summary_warnings(warnings: list[str]) -> None:
    """Append a markdown callout of non-fatal channel warnings (see
    find_nightly_channel_warnings()) to $GITHUB_STEP_SUMMARY, if set.
    No-op outside GitHub Actions, or when there are no warnings, so a
    clean run's summary is unchanged."""
    if not warnings:
        return
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    lines = ["### ⚠️ Nightly channel warnings", ""]
    for w in warnings:
        lines.append(f"- {w}")
    lines.append("")

    with open(summary_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def validate(formula_dir: Path) -> int:
    """Run all checks; return exit code (0 = pass, 1 = fail)."""
    rb_files = sorted(formula_dir.glob("*.rb"))
    if not rb_files:
        msg = f"no .rb files found in {formula_dir}"
        print(f"ERROR: {msg}", file=sys.stderr)
        emit_summary(status="error", formula_count=0, error_count=1, errors=[msg])
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

    # non-fatal nightly-channel warnings (kubestellar/homebrew-tap#423):
    # printed and surfaced in the step summary regardless of pass/fail,
    # but never affect the exit code.
    channel_warnings = find_nightly_channel_warnings(parsed)
    for w in channel_warnings:
        print(f"WARN: {w}", file=sys.stderr)
    _write_step_summary_warnings(channel_warnings)

    if all_errors:
        for e in all_errors:
            print(f"FAIL: {e}", file=sys.stderr)
        emit_summary(
            status="fail",
            formula_count=len(rb_files),
            error_count=len(all_errors),
            errors=all_errors,
        )
        return 1

    names = [p.stem for p in rb_files]
    print(f"OK: {len(rb_files)} formula(e) validated: {', '.join(names)}")
    emit_summary(status="pass", formula_count=len(rb_files), error_count=0)
    return 0


if __name__ == "__main__":
    formula_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("Formula")
    sys.exit(validate(formula_dir))
