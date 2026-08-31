"""Structural invariants for the ``test do`` block body.

Existing tests already assert:

* every formula has exactly one ``test do`` block
  (``test_every_formula_has_exactly_one_test_do_block``);
* the block references ``bin/"<formula-name>"``
  (``test_test_block_actually_exercises_installed_binary``,
  ``test_test_block_invokes_matching_binary``);
* the block uses ``system`` and not ``shell_output``
  (``test_test_block_uses_system_form``).

The invariants below cover a distinct gap: what argument does the
installed binary get invoked with?  ``brew test`` runs on every user's
laptop as part of ``brew install --HEAD``-style workflows and on the
Homebrew CI sandbox.  It must be a **read-only introspection call**
(``version`` / ``--version`` / ``--help`` / ``-h`` / ``-v`` / ``help``) —
never a mutating subcommand such as ``install``, ``deploy``, ``apply``,
``create``, ``delete``, ``upgrade``, ``run``, ``exec``, ``start``, or
``stop``.  A codegen bug or a careless hand-edit that shipped
``system bin/"kubestellar-deploy", "install"`` inside ``test do`` would
turn ``brew test`` into a live cluster mutation on every downstream
machine.  That failure mode is invisible to ``brew audit`` — it only
checks that a ``test do`` block exists and that ``system`` is called;
it does not inspect what ``system`` is being asked to run.

We also lock the block to a **single** ``system`` invocation.  All three
formulae today are one-liners of the form
``system bin/"<name>", "<readonly-verb>"``.  A second ``system`` call
appearing after a nightly release bump would be a strong signal that
someone hand-edited the generated file, and next release the extra line
will silently vanish.
"""
from __future__ import annotations

import pathlib
import re
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
FORMULA_DIR = REPO_ROOT / "Formula"

# Match a ``test do ... end`` block.  We stop at the *last* ``end`` before
# the outer ``class ... end`` closer — in practice ``test do`` is always
# the last stanza so a non-greedy match up to the next ``end`` is enough.
TEST_BLOCK_RE = re.compile(
    r"^\s*test\s+do\s*\n(?P<body>.*?)\n\s*end\s*$",
    re.DOTALL | re.MULTILINE,
)

# Match a ``system bin/"<name>", "<arg>"`` invocation.  The Ruby form
# allows either ``bin/"foo"`` or ``bin/"foo",`` with optional trailing
# comma-separated string arguments.  We only need to capture the first
# string arg after the binary reference.
SYSTEM_CALL_RE = re.compile(
    r'system\s+bin/"(?P<binary>[^"]+)"(?:\s*,\s*"(?P<arg>[^"]*)")?',
)

# Any ``system`` invocation, whether or not it targets bin/"...".  Used
# to count invocations inside the test block.
ANY_SYSTEM_RE = re.compile(r"\bsystem\b")

# Read-only introspection tokens.  These do not connect to a cluster,
# open a socket, write to $HOME, or otherwise mutate state — they only
# ask the binary to print information about itself.  If we ever need a
# new one (e.g. ``--version-json``), add it here consciously.
READONLY_ARGS = frozenset({
    "version", "--version", "-v",
    "help", "--help", "-h",
})

# Verbs that would turn ``brew test`` into a state-mutating operation on
# every downstream machine.  Not exhaustive — the allowlist above is the
# real guard — but calling these out gives a much better failure message
# than "arg X not in allowlist" when a codegen bug slips one through.
DANGEROUS_ARG_SUBSTRINGS = (
    "install", "uninstall", "upgrade", "downgrade",
    "deploy", "undeploy",
    "apply", "delete", "destroy", "remove",
    "create", "update", "patch",
    "run", "exec", "start", "stop", "restart",
    "login", "logout", "auth",
    "push", "pull", "fetch", "clone",
)


class TestBlockReadonlyInvariants(unittest.TestCase):
    """Guard the semantics of every formula's ``test do`` body."""

    @classmethod
    def setUpClass(cls):
        cls.formulae = {
            p.stem: p.read_text(encoding="utf-8")
            for p in sorted(FORMULA_DIR.glob("*.rb"))
        }
        assert cls.formulae, f"no formulae under {FORMULA_DIR}"

    def _test_body(self, text: str) -> str:
        m = TEST_BLOCK_RE.search(text)
        self.assertIsNotNone(m, "formula has no `test do` block")
        return m.group("body")

    # ------------------------------------------------------------------
    # Real formulae
    # ------------------------------------------------------------------

    def test_test_block_contains_exactly_one_system_invocation(self):
        # A second ``system`` line is a red flag for hand-editing.
        # Codegen emits exactly one; the next nightly bump would
        # silently drop the extra line and leave a broken PR diff.
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                body = self._test_body(text)
                count = len(ANY_SYSTEM_RE.findall(body))
                self.assertEqual(
                    count, 1,
                    f"{name}.rb: test do body has {count} `system` "
                    f"invocations, want exactly 1. Body: {body!r}",
                )

    def test_test_block_invokes_binary_with_readonly_argument(self):
        # The single ``system bin/"<name>", "<arg>"`` call must pass a
        # read-only introspection token.  Anything mutating would turn
        # ``brew test`` into a live-cluster operation on every user's
        # machine — invisible to ``brew audit``.
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                body = self._test_body(text)
                m = SYSTEM_CALL_RE.search(body)
                self.assertIsNotNone(
                    m,
                    f"{name}.rb: test body has no "
                    f'`system bin/"...", "..."` invocation. '
                    f"Body: {body!r}",
                )
                self.assertEqual(
                    m.group("binary"), name,
                    f"{name}.rb: test invokes bin/{m.group('binary')!r}, "
                    f"expected bin/{name!r}",
                )
                arg = m.group("arg")
                self.assertIsNotNone(
                    arg,
                    f"{name}.rb: test invokes bin/{name!r} with no "
                    f"argument — cannot verify it is read-only",
                )
                self.assertIn(
                    arg, READONLY_ARGS,
                    f"{name}.rb: test invokes bin/{name!r} with "
                    f"{arg!r}, which is not a read-only introspection "
                    f"token. Allowed: {sorted(READONLY_ARGS)}. A "
                    f"mutating argument here would run on every "
                    f"downstream `brew test`.",
                )

    def test_test_block_body_contains_no_dangerous_verbs(self):
        # Belt-and-braces layer on top of the allowlist above: even if a
        # ``system`` call were replaced by something else (Ruby block,
        # comment, etc.), the presence of a mutating verb as an isolated
        # token inside ``test do`` is worth flagging.  Words like
        # "install" appear routinely in docs/comments, so we only look
        # for them as *quoted strings* — the form they would take as a
        # subcommand argument.
        for name, text in self.formulae.items():
            with self.subTest(formula=name):
                body = self._test_body(text)
                for verb in DANGEROUS_ARG_SUBSTRINGS:
                    self.assertNotIn(
                        f'"{verb}"', body,
                        f"{name}.rb: test do body contains the quoted "
                        f"mutating verb {verb!r}. `brew test` runs on "
                        f"every downstream machine — this must not "
                        f"trigger a state change. Body: {body!r}",
                    )

    # ------------------------------------------------------------------
    # Regex self-tests — a mis-authored guard is worse than none.
    # ------------------------------------------------------------------

    def test_regex_matches_canonical_one_line_block(self):
        canonical = (
            'class Foo < Formula\n'
            '  test do\n'
            '    system bin/"foo", "--version"\n'
            '  end\n'
            'end\n'
        )
        m = TEST_BLOCK_RE.search(canonical)
        self.assertIsNotNone(m)
        self.assertIn('system bin/"foo", "--version"', m.group("body"))
        call = SYSTEM_CALL_RE.search(m.group("body"))
        self.assertIsNotNone(call)
        self.assertEqual(call.group("binary"), "foo")
        self.assertEqual(call.group("arg"), "--version")

    def test_regex_flags_a_two_system_body(self):
        two_calls = (
            '  test do\n'
            '    system bin/"foo", "--version"\n'
            '    system bin/"foo", "--help"\n'
            '  end\n'
        )
        m = TEST_BLOCK_RE.search(two_calls)
        self.assertIsNotNone(m)
        # Two system calls — this is exactly the state the invariant
        # above is meant to catch.
        self.assertEqual(len(ANY_SYSTEM_RE.findall(m.group("body"))), 2)

    def test_dangerous_arg_substrings_cover_common_mutating_verbs(self):
        # Regression check on the allowlist itself: verbs that would be
        # catastrophic in a ``brew test`` context must be listed.
        for must_be_listed in ("install", "deploy", "apply", "delete",
                               "create", "run", "start"):
            self.assertIn(must_be_listed, DANGEROUS_ARG_SUBSTRINGS)

    def test_readonly_args_are_all_short_flag_or_verb_forms(self):
        # No entry in the allowlist should smuggle in a subcommand with
        # side effects — every token is either a flag (``-*``) or a
        # bare-word introspection verb.
        for arg in READONLY_ARGS:
            with self.subTest(arg=arg):
                self.assertTrue(
                    arg.startswith("-") or arg in {"version", "help"},
                    f"allowlist entry {arg!r} is not obviously "
                    f"read-only",
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
