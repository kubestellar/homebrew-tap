#!/usr/bin/env python3
"""lib_emit_summary.py — Python owner of the single-line, machine-readable
'<PREFIX>: {json}' CI summary record, mirroring scripts/lib_emit_summary.sh.

scripts/lib_emit_summary.sh is the one *bash* owner of this contract
(kubestellar/homebrew-tap#577); this module is the one *Python* owner
(kubestellar/homebrew-tap#581). validate_formulae.py used to hand-roll its
own copy of the wire format, so any change to the record shape had to be
made twice, in two languages, with no test asserting both sides agreed.
Now every Python emitter calls into here, and
scripts/test_emit_summary_parity.py asserts that, for the same inputs, the
bash ``emit_ci_summary`` and the Python ``format_summary_line`` produce
byte-identical lines.

The shared contract is the JSON line only. The ``$GITHUB_STEP_SUMMARY``
markdown rendering is deliberately allowed to differ per emitter
(validate_formulae.py renders a fixed drift table plus an errors
``<details>`` block; the bash lib renders one column per key), so this
module offers the generic bash-shaped table as a convenience but does not
require callers to use it.

Wire format (identical to the bash lib):

  - exactly one line: ``<PREFIX>: {"k1":v1,"k2":v2,...}`` — compact
    separators, keys in caller-supplied insertion order (NOT sorted), so
    consumers' grep-marker regexes stay stable across both languages;
  - ``int``/``float`` values become JSON numbers, ``None`` becomes JSON
    null, ``str`` values become JSON strings with ``"``, ``\\`` and control
    characters escaped (``\\n \\r \\t \\b \\f`` short escapes, any other
    control character including DEL as ``\\u00XX``); non-ASCII text is
    passed through verbatim, exactly as the bash lib does;
  - anything else (bool, nested containers, ...) is rejected with
    ``TypeError`` — the bash lib cannot produce those, so accepting them
    here would let the two emitters silently diverge.

Stdout/file-only structured output: no exporter, metrics backend, or
off-box data flow is added.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from typing import TextIO

# Values a summary field may carry; mirrors what the bash lib can render.
SummaryValue = str | int | float | None

# Short JSON escapes, matching _emit_summary_json_escape in the bash lib.
_SHORT_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\b": "\\b",
    "\f": "\\f",
}

# Anything below 0x20 plus DEL (0x7f): bash's [[:cntrl:]] class.
_CONTROL_MAX = 0x1F
_DEL = 0x7F


def json_escape(text: str) -> str:
    """Return ``text`` as the body of a JSON string literal (no quotes),
    escaped exactly as the bash lib's ``_emit_summary_json_escape``."""
    out = []
    for ch in text:
        if ch in _SHORT_ESCAPES:
            out.append(_SHORT_ESCAPES[ch])
        elif ord(ch) <= _CONTROL_MAX or ord(ch) == _DEL:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return "".join(out)


def json_value(value: SummaryValue) -> str:
    """Render one field value as a JSON literal (number / null / string)."""
    if value is None:
        return "null"
    # bool is an int subclass; the bash lib has no boolean type, so reject
    # it rather than emit 1/0 or true/false and drift from the shell side.
    if isinstance(value, bool):
        raise TypeError("summary values must be str, int, float or None, not bool")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return f'"{json_escape(value)}"'
    raise TypeError(
        f"summary values must be str, int, float or None, not {type(value).__name__}"
    )


def format_summary_line(prefix: str, fields: Mapping[str, SummaryValue]) -> str:
    """Return ``'<PREFIX>: {json}'`` (without a trailing newline) for
    ``fields`` in insertion order — byte-identical to the bash lib's
    ``emit_ci_summary "$prefix" k1=v1 k2=v2 ...``."""
    if not prefix:
        raise ValueError("summary prefix must be non-empty")
    body = []
    for key, value in fields.items():
        if not key:
            raise ValueError("summary field keys must be non-empty")
        body.append(f'"{json_escape(key)}":{json_value(value)}')
    return f"{prefix}: {{{','.join(body)}}}"


def emit_summary_line(
    prefix: str,
    fields: Mapping[str, SummaryValue],
    stream: TextIO | None = None,
) -> str:
    """Print the summary line to ``stream`` (default: stdout) and return it."""
    line = format_summary_line(prefix, fields)
    print(line, file=stream if stream is not None else sys.stdout)
    return line


def humanize(identifier: str) -> str:
    """``BREW_CI_SUMMARY`` -> ``Brew ci summary``; ``formula_count`` ->
    ``Formula count`` (mirrors ``_emit_summary_humanize`` in the bash lib)."""
    text = identifier.lower().replace("_", " ")
    return text[:1].upper() + text[1:]


def status_cell(status: str) -> str:
    """Prefix a status value with the ✅/❌ icon convention shared with the
    bash lib: ``pass``/``success`` are green, anything else is red."""
    icon = "✅" if status in ("pass", "success") else "❌"
    return f"{icon} {status}"


def step_summary_path() -> str | None:
    """Return ``$GITHUB_STEP_SUMMARY`` when set to a non-empty value, else
    ``None`` (local runs and unit tests: every step-summary write is a
    no-op)."""
    return os.environ.get("GITHUB_STEP_SUMMARY") or None


def append_step_summary(lines: list[str]) -> bool:
    """Append ``lines`` (plus a trailing newline) to ``$GITHUB_STEP_SUMMARY``.
    Returns ``False`` without writing when the variable is unset. Always
    appends — the file is shared across steps."""
    path = step_summary_path()
    if path is None:
        return False
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return True


def format_step_summary_table(prefix: str, fields: Mapping[str, SummaryValue]) -> list[str]:
    """Render the generic bash-shaped table: ``### <Prefix>`` heading, one
    header row of humanized keys, one row of values (✅/❌ on ``status``),
    ``|`` escaped so a value cannot break the layout."""
    lines = [f"### {humanize(prefix)}", ""]
    if fields:
        header = "|"
        divider = "|"
        row = "|"
        for key, value in fields.items():
            cell = "null" if value is None else str(value)
            cell = cell.replace("|", "\\|")
            if key == "status":
                cell = status_cell(cell)
            header += f" {humanize(key)} |"
            divider += "--------|"
            row += f" {cell} |"
        lines.extend([header, divider, row])
    lines.append("")
    return lines


def emit_ci_summary(
    prefix: str,
    fields: Mapping[str, SummaryValue],
    stream: TextIO | None = None,
) -> str:
    """The Python twin of the bash ``emit_ci_summary``: print the JSON line
    and, when ``$GITHUB_STEP_SUMMARY`` is set, append the generic markdown
    table. Returns the printed line."""
    line = emit_summary_line(prefix, fields, stream)
    if step_summary_path() is not None:
        append_step_summary(format_step_summary_table(prefix, fields))
    return line
