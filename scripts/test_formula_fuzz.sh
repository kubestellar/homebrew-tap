#!/usr/bin/env bash
# test_formula_fuzz.sh — regression tests for scripts/formula_fuzz.sh.
#
# Guards each fuzzing phase the workflow used to inline: Ruby syntax
# check, structural requirements (Formula subclass, metadata, install
# method), and URL/sha256 shape. A future edit that drops or weakens any
# of these guards must show up as a failing case here, since
# scripts/run_shell_tests.sh is wired into validate-formulae.yml and
# will fail CI on it.
#
# Usage: scripts/test_formula_fuzz.sh
# Exit status: 0 if all assertions pass, 1 otherwise.

set -uo pipefail

# shellcheck source=scripts/test_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test_lib.sh"

REPO_ROOT="$(repo_root)"
SCRIPT="$REPO_ROOT/scripts/formula_fuzz.sh"

# The script's syntax phase shells out to `ruby -c`. Ubuntu GitHub
# Actions runners ship ruby preinstalled, so validate-formulae.yml's
# `Run scripts/test_*.sh shell regression tests` step exercises every
# case below in CI. On a dev machine without ruby(1), skip the whole
# file with a clear message so the shell-test wrapper still exits 0.
if ! command -v ruby >/dev/null 2>&1; then
  echo "SKIP (formula_fuzz.sh): ruby(1) not on PATH — install ruby to run this test locally"
  finish "formula_fuzz.sh"
fi

make_work_dir

# ---------- helpers for building tailored fixtures ----------

write_good_formula() {
  local path="$1" class_name="$2"
  cat > "$path" <<RUBY
class $class_name < Formula
  desc "test"
  homepage "https://example.invalid"
  url "https://example.invalid/${class_name}.tar.gz"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  def install
    bin.install "${class_name}"
  end
end
RUBY
}

# ---------- happy path ----------

good_dir="$work_dir/good"
mkdir -p "$good_dir"
write_good_formula "$good_dir/kc-agent.rb" KcAgent
write_good_formula "$good_dir/kubestellar-ops.rb" KubestellarOps

output=$("$SCRIPT" "$good_dir" 2>&1)
exit_code=$?
assert_exit "happy-path" "$exit_code" 0 "expected exit=0 with well-formed formulae. Got exit=$exit_code, output: $output"
assert_grep "happy-path" "$output" "Formula fuzzing passed" "expected success marker. Got: $output"

# ---------- empty / missing formula dir ----------

output=$("$SCRIPT" "$work_dir/does-not-exist" 2>&1)
exit_code=$?
assert_exit "missing-formula-dir" "$exit_code" 1 "expected exit=1 for missing dir. Got exit=$exit_code, output: $output"
assert_grep "missing-formula-dir" "$output" "No formula files found" "expected explicit no-formulae message. Got: $output"

empty_dir="$work_dir/empty"
mkdir -p "$empty_dir"
output=$("$SCRIPT" "$empty_dir" 2>&1)
exit_code=$?
assert_exit "empty-formula-dir" "$exit_code" 1 "expected exit=1 for empty dir. Got exit=$exit_code, output: $output"

# ---------- syntax fuzzing ----------
# Ruby availability was guarded at the top of the file, so these cases
# always run in CI (ubuntu-latest ships ruby preinstalled).

syntax_dir="$work_dir/syntax"
mkdir -p "$syntax_dir"
write_good_formula "$syntax_dir/good.rb" Good
# Missing `end` and unterminated string — ruby -c must reject.
cat > "$syntax_dir/broken.rb" <<'RUBY'
class Broken < Formula
  desc "broken
RUBY

output=$("$SCRIPT" "$syntax_dir" 2>&1)
exit_code=$?
assert_exit "syntax-error-fails" "$exit_code" 1 "expected exit=1 when ruby -c fails. Got exit=$exit_code, output: $output"
assert_grep "syntax-error-fails" "$output" "Syntax error in" "expected 'Syntax error in' log. Got: $output"

# ---------- structure fuzzing ----------

struct_dir="$work_dir/struct"
mkdir -p "$struct_dir"
# No `class ... < Formula`
cat > "$struct_dir/no-class.rb" <<'RUBY'
# not a formula at all
puts "hi"
RUBY

output=$("$SCRIPT" "$struct_dir" 2>&1)
exit_code=$?
assert_exit "missing-formula-class" "$exit_code" 1 "expected exit=1 when Formula class is absent. Got exit=$exit_code, output: $output"
assert_grep "missing-formula-class" "$output" "Missing Formula class in" "expected 'Missing Formula class' log. Got: $output"

struct_dir2="$work_dir/struct2"
mkdir -p "$struct_dir2"
# Has class + metadata but no install method
cat > "$struct_dir2/no-install.rb" <<'RUBY'
class NoInstall < Formula
  desc "x"
  homepage "https://example.invalid"
  url "https://example.invalid/x.tar.gz"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
end
RUBY

output=$("$SCRIPT" "$struct_dir2" 2>&1)
exit_code=$?
assert_exit "missing-install-method" "$exit_code" 1 "expected exit=1 when install method is missing. Got exit=$exit_code, output: $output"
assert_grep "missing-install-method" "$output" "Missing install method in" "expected 'Missing install method' log. Got: $output"

# `define_method(:install)` must count as a valid install method (this
# is the shape all current Formula/*.rb use — a regression that only
# accepted `def install` would silently break every real formula).
struct_dir3="$work_dir/struct3"
mkdir -p "$struct_dir3"
cat > "$struct_dir3/define-method.rb" <<'RUBY'
class DefineMethod < Formula
  desc "x"
  homepage "https://example.invalid"
  url "https://example.invalid/x.tar.gz"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  define_method(:install) do
    bin.install "x"
  end
end
RUBY

output=$("$SCRIPT" "$struct_dir3" 2>&1)
exit_code=$?
assert_exit "define-method-install-accepted" "$exit_code" 0 "define_method(:install) must satisfy the install-method guard. Got exit=$exit_code, output: $output"

# ---------- URL / checksum fuzzing ----------

url_dir="$work_dir/urls"
mkdir -p "$url_dir"
# non-http(s) URL scheme must fail
cat > "$url_dir/ftp.rb" <<'RUBY'
class Ftp < Formula
  desc "x"
  homepage "https://example.invalid"
  url "ftp://example.invalid/x.tar.gz"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  def install
    bin.install "x"
  end
end
RUBY

output=$("$SCRIPT" "$url_dir" 2>&1)
exit_code=$?
assert_exit "bad-url-scheme-fails" "$exit_code" 1 "expected exit=1 when a url uses a non-http(s) scheme. Got exit=$exit_code, output: $output"
assert_grep "bad-url-scheme-fails" "$output" "Invalid URL format" "expected 'Invalid URL format' log. Got: $output"

# plain http:// (unencrypted downgrade) must also fail — see #493
http_dir="$work_dir/http-scheme"
mkdir -p "$http_dir"
cat > "$http_dir/plainhttp.rb" <<'RUBY'
class Plainhttp < Formula
  desc "x"
  homepage "https://example.invalid"
  url "http://example.invalid/x.tar.gz"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  def install
    bin.install "x"
  end
end
RUBY

output=$("$SCRIPT" "$http_dir" 2>&1)
exit_code=$?
assert_exit "plain-http-url-fails" "$exit_code" 1 "expected exit=1 when a url uses plain http:// (see #493). Got exit=$exit_code, output: $output"
assert_grep "plain-http-url-fails" "$output" "Invalid URL format" "expected 'Invalid URL format' log. Got: $output"

# url declared but no sha256 must fail
sha_dir="$work_dir/nosha"
mkdir -p "$sha_dir"
cat > "$sha_dir/nosha.rb" <<'RUBY'
class Nosha < Formula
  desc "x"
  homepage "https://example.invalid"
  url "https://example.invalid/x.tar.gz"
  def install
    bin.install "x"
  end
end
RUBY

output=$("$SCRIPT" "$sha_dir" 2>&1)
exit_code=$?
assert_exit "missing-sha256-fails" "$exit_code" 1 "expected exit=1 when a url has no sha256. Got exit=$exit_code, output: $output"
assert_grep "missing-sha256-fails" "$output" "Missing sha256 checksum in" "expected 'Missing sha256 checksum' log. Got: $output"

# ---------- real Formula/ directory must pass ----------
# This is the strongest end-to-end guarantee: the extracted script must
# accept every real in-tree formula, so a swap in fuzz.yml can never
# regress the workflow. Only run if the checkout actually has Formula/.
if [ -d "$REPO_ROOT/Formula" ] && compgen -G "$REPO_ROOT/Formula/*.rb" >/dev/null; then
  output=$("$SCRIPT" "$REPO_ROOT/Formula" 2>&1)
  exit_code=$?
  assert_exit "real-formulae-pass" "$exit_code" 0 "in-tree Formula/*.rb must satisfy fuzz guards. Got exit=$exit_code, output: $output"
fi

# ---------- default argument ----------
# When called with no argument, it must fuzz ./Formula relative to $PWD.
# Change to a work dir with its own Formula/ so this test doesn't depend
# on the repo checkout.
default_arg_dir="$work_dir/default"
mkdir -p "$default_arg_dir/Formula"
write_good_formula "$default_arg_dir/Formula/kc-agent.rb" KcAgent
output=$(cd "$default_arg_dir" && "$SCRIPT" 2>&1)
exit_code=$?
assert_exit "default-formula-dir" "$exit_code" 0 "expected default arg to resolve to ./Formula. Got exit=$exit_code, output: $output"

finish "formula_fuzz.sh"
