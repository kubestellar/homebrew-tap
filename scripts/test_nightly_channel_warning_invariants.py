#!/usr/bin/env python3
"""Unit tests for the nightly-channel warning added for
kubestellar/homebrew-tap#423: kc-agent.rb has no dedicated nightly
formula, so a nightly goreleaser run overwrites the same file a stable
release publishes to. find_nightly_channel_warnings() / validate()
surface that as a non-fatal WARN (exit code and error_count are
unaffected) since the real fix must land in the upstream repo's
goreleaser config, not in this tap.
"""

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from validate_formulae import (
    _write_step_summary_warnings,
    find_nightly_channel_warnings,
    validate,
)


def _parsed(name: str, version: str) -> dict:
    return {"version": version, "errors": [], "name": name}


class TestFindNightlyChannelWarnings(unittest.TestCase):
    def test_stable_kc_agent_has_no_warning(self):
        parsed = {"kc-agent": _parsed("kc-agent", "0.3.42")}
        self.assertEqual(find_nightly_channel_warnings(parsed), [])

    def test_nightly_kc_agent_is_warned(self):
        parsed = {"kc-agent": _parsed("kc-agent", "0.3.42-nightly.20260916")}
        warnings = find_nightly_channel_warnings(parsed)
        self.assertEqual(len(warnings), 1)
        self.assertIn("kc-agent.rb", warnings[0])
        self.assertIn("0.3.42-nightly.20260916", warnings[0])
        self.assertIn("homebrew-tap#423", warnings[0])

    def test_missing_kc_agent_has_no_warning(self):
        # e.g. a directory that only holds the ops/deploy pair.
        parsed = {"kubestellar-ops": _parsed("kubestellar-ops", "0.9.15-nightly.20260916")}
        self.assertEqual(find_nightly_channel_warnings(parsed), [])

    def test_lockstep_formulae_are_not_single_channel(self):
        # kubestellar-ops/kubestellar-deploy always move in lockstep with
        # each other, so they are intentionally excluded from
        # SINGLE_CHANNEL_FORMULAE even when nightly-tagged.
        parsed = {
            "kubestellar-ops": _parsed("kubestellar-ops", "0.9.15-nightly.20260916"),
            "kubestellar-deploy": _parsed("kubestellar-deploy", "0.9.15-nightly.20260916"),
        }
        self.assertEqual(find_nightly_channel_warnings(parsed), [])


class TestWriteStepSummaryWarnings(unittest.TestCase):
    def setUp(self):
        self._saved_env = os.environ.pop("GITHUB_STEP_SUMMARY", None)

    def tearDown(self):
        if self._saved_env is not None:
            os.environ["GITHUB_STEP_SUMMARY"] = self._saved_env
        else:
            os.environ.pop("GITHUB_STEP_SUMMARY", None)

    def test_no_warnings_is_a_no_op_even_with_env_set(self):
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".md") as tmp:
            tmp_path = tmp.name
        try:
            os.environ["GITHUB_STEP_SUMMARY"] = tmp_path
            _write_step_summary_warnings([])
            self.assertEqual(Path(tmp_path).read_text(encoding="utf-8"), "")
        finally:
            os.unlink(tmp_path)

    def test_no_env_var_is_a_no_op(self):
        # Warnings present but GITHUB_STEP_SUMMARY unset: must not raise.
        _write_step_summary_warnings(["kc-agent.rb is nightly"])

    def test_warnings_rendered_when_env_set(self):
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".md") as tmp:
            tmp_path = tmp.name
        try:
            os.environ["GITHUB_STEP_SUMMARY"] = tmp_path
            _write_step_summary_warnings(["kc-agent.rb is currently nightly"])
            content = Path(tmp_path).read_text(encoding="utf-8")
            self.assertIn("### ⚠️ Nightly channel warnings", content)
            self.assertIn("- kc-agent.rb is currently nightly", content)
        finally:
            os.unlink(tmp_path)


class TestValidateIntegration(unittest.TestCase):
    """The warning must never flip validate()'s exit code or error_count."""

    KC_AGENT_STABLE = (
        '# typed: false\n'
        'class KcAgent < Formula\n'
        '  version "0.3.42"\n'
        'end\n'
    )
    KC_AGENT_NIGHTLY = (
        '# typed: false\n'
        'class KcAgent < Formula\n'
        '  version "0.3.42-nightly.20260916"\n'
        'end\n'
    )

    def test_nightly_kc_agent_still_passes_but_warns(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "kc-agent.rb").write_text(self.KC_AGENT_NIGHTLY)
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                rc = validate(Path(d))
            self.assertEqual(rc, 0)
            self.assertIn("WARN:", stderr.getvalue())
            self.assertIn("kc-agent.rb", stderr.getvalue())

    def test_stable_kc_agent_has_no_warning_output(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "kc-agent.rb").write_text(self.KC_AGENT_STABLE)
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                rc = validate(Path(d))
            self.assertEqual(rc, 0)
            self.assertNotIn("WARN:", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
