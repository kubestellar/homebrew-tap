# lib_formula_iter.sh — shared formula-stem iteration for scripts that
# walk a directory of *.rb formula files.
#
# brew_audit_all.sh, brew_install_smoke.sh, brew_test_installed.sh, and
# brew_untap_self.sh each independently duplicated the same three-line
# glob/skip/basename sequence to turn FORMULA_DIR into a list of formula
# stems (e.g. "Formula/kubestellar.rb" -> "kubestellar"). This file
# centralizes that walk so it exists in exactly one place.
#
# Usage: source this file, then:
#   while IFS= read -r name; do
#     ...
#   done < <(list_formula_names "$FORMULA_DIR")
#
# This file is meant to be sourced, not executed directly.

# list_formula_names <formula_dir> — print one formula stem per line for
# every "<formula_dir>/*.rb" file, skipping the literal glob when the
# directory has no *.rb files (the `[ -e ]` guard against an unexpanded
# glob pattern).
list_formula_names() {
  local formula_dir="$1"
  local formula
  for formula in "$formula_dir"/*.rb; do
    [ -e "$formula" ] || continue
    basename "$formula" .rb
  done
}
