#!/usr/bin/env python3
"""Direct coverage for the nightly-rollover tolerance branch inside
``CrossFormulaInvariants.test_ops_and_deploy_share_a_single_version``.

The parent test in ``test_crossformula_invariants.py`` runs against
the real ``Formula/*.rb`` files; in steady state they share an
identical version string, which means the entire ``versions differ``
branch (lines ~177-205) — the code that tolerates a one-day nightly
rollover gap and rejects everything else — is **never executed** by
the existing suite.

That branch guards against a silent regression: if the tolerance
regex or the ``gap == 1`` check breaks, CI would still stay green
until a real rollover happens in production, and then either

  * mask a legitimate drift (bug goes green when it should be red), or
  * red-storm every night for two weeks until someone patches the
    invariant.

Either failure mode is a quiet regression risk in a guardrail we
depend on. This module drives the parent test method with synthetic
in-memory formulae so every branch of the tolerance logic is
exercised:

  * identical versions — passes silently (short-circuit at line ~175)
  * one-day nightly gap — passes (tolerance window)
  * two-day nightly gap — fails
  * seven-day nightly gap — fails
  * same base, same-day nightly stamps but different — passes
    (identical) — sanity anchor
  * different base semver with matching nightly stamps — fails
  * one nightly + one non-nightly version — fails (nightly regex miss)
  * both non-nightly versions but different — fails

Runnable the same way as the sibling test modules::

    python3 scripts/test_lockstep_nightly_tolerance_invariants.py
"""

import textwrap
import unittest

from test_crossformula_invariants import CrossFormulaInvariants


def _synthetic_formula(name: str, version: str) -> str:
    """Return a minimal Ruby formula body just complete enough for the
    ``VERSION_RE`` scan inside the parent test to find the version.
    The parent test never parses URLs or sha256 for this check, so a
    stub body is sufficient.
    """
    class_name = "".join(part.capitalize() for part in name.split("-"))
    return textwrap.dedent(
        f"""\
        # frozen_string_literal: true
        class {class_name} < Formula
          desc "stub"
          homepage "https://example.invalid/"
          version "{version}"
          license "Apache-2.0"
        end
        """
    )


def _run_lockstep_check(versions: dict) -> None:
    """Instantiate CrossFormulaInvariants and drive the lockstep test
    with the supplied synthetic version map. Re-raises whatever
    assertion the parent test raises so the caller can assert on it.
    """
    tc = CrossFormulaInvariants("test_ops_and_deploy_share_a_single_version")
    tc.formulae = {
        name: _synthetic_formula(name, ver) for name, ver in versions.items()
    }
    tc.test_ops_and_deploy_share_a_single_version()


class NightlyRolloverToleranceBranch(unittest.TestCase):
    """Exercises the ``versions differ`` branch of the lockstep check."""

    def test_identical_versions_pass(self):
        # Short-circuit at ``if len(distinct) == 1: return`` — never
        # enters the tolerance parser.
        _run_lockstep_check({
            "kubestellar-ops": "0.3.39-nightly.20260829",
            "kubestellar-deploy": "0.3.39-nightly.20260829",
        })

    def test_one_day_nightly_gap_is_tolerated(self):
        # This is the rollover-window branch. Same base semver, dates
        # differ by exactly one calendar day: the parent test must
        # accept it silently.
        _run_lockstep_check({
            "kubestellar-ops": "0.3.39-nightly.20260829",
            "kubestellar-deploy": "0.3.39-nightly.20260830",
        })

    def test_one_day_gap_across_month_boundary_is_tolerated(self):
        # Guards the ``date`` arithmetic — the tolerance must be a real
        # calendar-day diff, not a string subtraction. 2026-08-31 -> 2026-09-01
        # is a one-day gap even though the numeric stamp jumps by 71.
        _run_lockstep_check({
            "kubestellar-ops": "0.3.39-nightly.20260831",
            "kubestellar-deploy": "0.3.39-nightly.20260901",
        })

    def test_two_day_nightly_gap_fails(self):
        # First day outside the tolerance window: must fail loudly.
        with self.assertRaises(AssertionError) as ctx:
            _run_lockstep_check({
                "kubestellar-ops": "0.3.39-nightly.20260829",
                "kubestellar-deploy": "0.3.39-nightly.20260831",
            })
        # The parent test's failure message names the gap.
        self.assertIn("2 day", str(ctx.exception))

    def test_seven_day_nightly_gap_fails(self):
        with self.assertRaises(AssertionError) as ctx:
            _run_lockstep_check({
                "kubestellar-ops": "0.3.39-nightly.20260822",
                "kubestellar-deploy": "0.3.39-nightly.20260829",
            })
        self.assertIn("7 day", str(ctx.exception))

    def test_different_base_semver_fails_even_with_nightly_stamps(self):
        # Same nightly date but different base version. The parent
        # test's base-equality check must reject this.
        with self.assertRaises(AssertionError) as ctx:
            _run_lockstep_check({
                "kubestellar-ops": "0.3.39-nightly.20260829",
                "kubestellar-deploy": "0.3.40-nightly.20260829",
            })
        self.assertIn("base versions", str(ctx.exception))

    def test_nightly_plus_non_nightly_fails(self):
        # One nightly + one stable version. The nightly regex fails on
        # the stable side, and the parent test takes the ``not a
        # nightly`` fallback and calls self.fail(...).
        with self.assertRaises(AssertionError) as ctx:
            _run_lockstep_check({
                "kubestellar-ops": "0.3.39",
                "kubestellar-deploy": "0.3.39-nightly.20260829",
            })
        self.assertIn("must share the same version", str(ctx.exception))

    def test_two_distinct_non_nightly_versions_fail(self):
        # Neither side is a nightly build — the tolerance logic never
        # applies and the parent test must fail hard.
        with self.assertRaises(AssertionError) as ctx:
            _run_lockstep_check({
                "kubestellar-ops": "0.3.39",
                "kubestellar-deploy": "0.3.40",
            })
        self.assertIn("must share the same version", str(ctx.exception))

    def test_missing_lockstep_formula_fails(self):
        # The parent test asserts both lockstep formulae are present
        # before it inspects versions. This anchors that pre-check so a
        # future refactor cannot silently drop the guard.
        with self.assertRaises(AssertionError) as ctx:
            _run_lockstep_check({
                "kubestellar-ops": "0.3.39-nightly.20260829",
                # kubestellar-deploy intentionally absent
            })
        self.assertIn("lockstep formulae", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
