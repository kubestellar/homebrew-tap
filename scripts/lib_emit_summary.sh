#!/usr/bin/env bash
# lib_emit_summary.sh — shared emitter for the single-line, machine-readable
# '<PREFIX>: {json}' CI summary records used throughout scripts/.
#
# Five bash helpers (brew_ci_summary.sh, fuzz_summary.sh, unittest_summary.sh,
# brew_audit_all.sh, verify_release_health.sh) each used to hand-roll their
# own printf for this line, "mirroring" validate_formulae.emit_summary() on
# the Python side without any shared mechanism to keep the JSON shape,
# quoting, and $GITHUB_STEP_SUMMARY behaviour in lockstep. This library is
# the one bash owner of that contract (see kubestellar/homebrew-tap#577).
#
# Usage: source this file, then call:
#
#   emit_ci_summary <PREFIX> [key=value ...]
#
#   - prints exactly one line to stdout: '<PREFIX>: {"k1":v1,"k2":v2,...}'
#     with the keys in the order given on the command line, so callers'
#     grep-marker regexes stay stable;
#   - infers each value's JSON type: an integer or decimal literal
#     (e.g. 3, -1, 2.5) becomes a JSON number, the literal word `null`
#     becomes JSON null, and anything else becomes a JSON string with `"`,
#     `\` and control characters escaped;
#   - a key may carry an explicit `:str` suffix (`failed_formula:str=123`)
#     to force the string type when the value is caller-controlled and
#     might otherwise look like a number or null;
#   - when $GITHUB_STEP_SUMMARY is set (GitHub Actions sets it for every
#     step), also appends a small markdown table — a "### <Prefix>" heading
#     plus one header row of keys and one row of values, with a ✅/❌ icon
#     on the `status` cell — matching the shape of
#     validate_formulae._write_step_summary(). Outside Actions this is a
#     no-op, so local runs and tests are unaffected.
#
# Stdout/file-only structured output: no exporter, metrics backend, or
# off-box data flow is added.
#
# This file is meant to be sourced, not executed directly. It is kept
# bash-3.2 compatible (no ${var,,}, no associative arrays) because the
# sourcing scripts run under macOS's default /bin/bash in brew-ci.yml.

# _emit_summary_json_escape <string> — print <string> as the body of a JSON
# string literal (without the surrounding quotes): `\` and `"` are
# backslash-escaped, common control characters use their short escapes,
# and any other control character is emitted as \u00XX.
_emit_summary_json_escape() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"
  s="${s//$'\r'/\\r}"
  s="${s//$'\t'/\\t}"
  s="${s//$'\b'/\\b}"
  s="${s//$'\f'/\\f}"
  if [[ "$s" == *[[:cntrl:]]* ]]; then
    local out="" i ch
    for ((i = 0; i < ${#s}; i++)); do
      ch="${s:i:1}"
      if [[ "$ch" == [[:cntrl:]] ]]; then
        out+="$(printf '\\u%04x' "'$ch")"
      else
        out+="$ch"
      fi
    done
    s="$out"
  fi
  printf '%s' "$s"
}

# _emit_summary_json_value <value> [force_string] — print <value> as a JSON
# literal: number when it looks like one, null for the word `null`, and a
# quoted/escaped string otherwise (always a string when force_string=1).
_emit_summary_json_value() {
  local value="$1" force_string="${2:-0}"
  if [ "$force_string" != "1" ]; then
    if [[ "$value" =~ ^-?(0|[1-9][0-9]*)(\.[0-9]+)?$ ]]; then
      printf '%s' "$value"
      return 0
    fi
    if [ "$value" = "null" ]; then
      printf 'null'
      return 0
    fi
  fi
  printf '"%s"' "$(_emit_summary_json_escape "$value")"
}

# _emit_summary_humanize <identifier> — turn BREW_CI_SUMMARY into
# "Brew ci summary" / formula_count into "Formula count" for the markdown
# table so the step summary reads like validate_formulae's headings.
_emit_summary_humanize() {
  local s
  s="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr '_' ' ')"
  printf '%s%s' "$(printf '%s' "${s:0:1}" | tr '[:lower:]' '[:upper:]')" "${s:1}"
}

# _emit_summary_step_table <PREFIX> <keys...> -- <values...> — append the
# markdown table for one summary to $GITHUB_STEP_SUMMARY. Called only when
# that variable is set. Pipe characters in values are escaped so a value
# cannot break the table layout.
_emit_summary_step_table() {
  local prefix="$1"; shift
  local keys=() values=() in_values=0 arg
  for arg in "$@"; do
    if [ "$in_values" -eq 0 ] && [ "$arg" = "--" ]; then
      in_values=1
      continue
    fi
    if [ "$in_values" -eq 0 ]; then
      keys+=("$arg")
    else
      values+=("$arg")
    fi
  done

  local header="|" divider="|" row="|" i key value
  for ((i = 0; i < ${#keys[@]}; i++)); do
    key="${keys[$i]}"
    value="${values[$i]}"
    value="${value//|/\\|}"
    if [ "$key" = "status" ]; then
      case "$value" in
        pass|success) value="✅ $value" ;;
        *) value="❌ $value" ;;
      esac
    fi
    header+=" $(_emit_summary_humanize "$key") |"
    divider+="--------|"
    row+=" $value |"
  done

  {
    printf '### %s\n\n' "$(_emit_summary_humanize "$prefix")"
    if [ "${#keys[@]}" -gt 0 ]; then
      printf '%s\n%s\n%s\n' "$header" "$divider" "$row"
    fi
    printf '\n'
  } >> "$GITHUB_STEP_SUMMARY"
}

# emit_ci_summary <PREFIX> [key=value ...] — see the file header.
emit_ci_summary() {
  local prefix="$1"; shift
  local json="" sep="" pair key value force_string
  local keys=() values=()
  for pair in "$@"; do
    key="${pair%%=*}"
    value="${pair#*=}"
    if [ "$key" = "$pair" ]; then
      echo "emit_ci_summary: argument '$pair' is not key=value" >&2
      return 2
    fi
    force_string=0
    if [[ "$key" == *:str ]]; then
      key="${key%:str}"
      force_string=1
    fi
    if [ -z "$key" ]; then
      echo "emit_ci_summary: empty key in argument '$pair'" >&2
      return 2
    fi
    json+="${sep}\"$(_emit_summary_json_escape "$key")\":$(_emit_summary_json_value "$value" "$force_string")"
    sep=","
    keys+=("$key")
    values+=("$value")
  done

  printf '%s: {%s}\n' "$prefix" "$json"

  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    _emit_summary_step_table "$prefix" "${keys[@]+"${keys[@]}"}" -- "${values[@]+"${values[@]}"}"
  fi
}
