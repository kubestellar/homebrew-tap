#!/usr/bin/env python3
"""In-process unit tests for the private _write_step_summary() helper in
scripts/validate_formulae.py.

The sibling test_validate_formulae_step_summary.py exercises the same
helper via subprocess (running the whole script), which does NOT get
picked up by `pytest --cov=validate_formulae` because coverage.py only
sees the parent process. As a result lines 124-146 (the entire body of
_write_step_summary that fires when GITHUB_STEP_SUMMARY is set) show as
uncovered, so a regression in the summary formatting or the error-
truncation path would slip past `pytest --cov` even though CI would
render broken output.

These tests import validate_formulae directly and call the helper (and
emit_summary() as a thin wrapper) so the branches are attributed to the
module. No production code changes.

Branches guarded:
  1. GITHUB_STEP_SUMMARY unset -> early return, no file created.
  2. status='pass' with no errors -> writes ✅ icon and header row only
     (no <details> block).
  3. status='fail' with a short error list -> writes ❌ icon and full
     <details> block with every error rendered.
  4. status='error' with a formula_count of 0 (the "no .rb files" path
     in validate()) -> also uses ❌ icon.
  5. errors longer than MAX_STEP_SUMMARY_ERRORS -> truncates the list
     AND appends the "...and N more" footer.
  6. emit_summary() forwards its errors kwarg to _write_step_summary
     (defaulting to []) so callers that omit errors on success don't
     crash the helper.
  7. Existing content in the summary file is preserved: the helper
     APPENDS a table rather than overwriting.
"""

import importlib.util
import os
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parent / "validate_formulae.py"

# The script filename contains a dash, so import via importlib rather
# than a plain `import validate_formulae`.
_spec = importlib.util.spec_from_file_location("validate_formulae_mod", SCRIPT)
vf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vf)


class WriteStepSummaryBranches(unittest.TestCase):
    def setUp(self):
        # Isolate from any real CI env var that the harness may have set.
        self._saved_env = os.environ.pop("GITHUB_STEP_SUMMARY", None)

    def tearDown(self):
        if self._saved_env is not None:
            os.environ["GITHUB_STEP_SUMMARY"] = self._saved_env
        else:
            os.environ.pop("GITHUB_STEP_SUMMARY", None)

    def test_no_env_var_is_a_no_op(self):
        # No GITHUB_STEP_SUMMARY -> early return, no file created,
        # no exception. This is the local-dev / non-Actions path.
        vf._write_step_summary("pass", 3, 0, [])
        # Nothing to assert beyond "did not raise"; the guard is the
        # early return itself.

    def test_pass_writes_icon_and_header_only(self):
        # Success path with no errors must produce the header table but
        # NOT the <details> block. A regression that always emitted the
        # <details> block would render "Error details" on green runs
        # and confuse reviewers.
        import tempfile
        with tempfile.NamedTemporaryFile(
            "w+", delete=False, suffix=".md"
        ) as tmp:
            tmp_path = tmp.name
        try:
            os.environ["GITHUB_STEP_SUMMARY"] = tmp_path
            vf._write_step_summary("pass", 5, 0, [])
            content = Path(tmp_path).read_text(encoding="utf-8")
            self.assertIn("### Formula drift check", content)
            self.assertIn("| ✅ pass | 5 | 0 |", content)
            self.assertNotIn("<details>", content)
            self.assertNotIn("Error details", content)
        finally:
            os.unlink(tmp_path)

    def test_fail_writes_error_details_block(self):
        import tempfile
        with tempfile.NamedTemporaryFile(
            "w+", delete=False, suffix=".md"
        ) as tmp:
            tmp_path = tmp.name
        try:
            os.environ["GITHUB_STEP_SUMMARY"] = tmp_path
            errors = [
                "foo.rb: malformed sha256 'xyz'",
                "bar.rb: url does not embed version '1.2.3'",
            ]
            vf._write_step_summary("fail", 2, len(errors), errors)
            content = Path(tmp_path).read_text(encoding="utf-8")
            self.assertIn("| ❌ fail | 2 | 2 |", content)
            self.assertIn("<details><summary>Error details</summary>", content)
            self.assertIn("</details>", content)
            for e in errors:
                self.assertIn(e, content)
            # No truncation footer when the list fits under the cap.
            self.assertNotIn("more (see step log)", content)
        finally:
            os.unlink(tmp_path)

    def test_error_status_uses_fail_icon(self):
        # validate() calls emit_summary(status="error", ...) when there
        # are no .rb files. Any non-"pass" status must render ❌ so a
        # future author can't accidentally emit ✅ on an error state.
        import tempfile
        with tempfile.NamedTemporaryFile(
            "w+", delete=False, suffix=".md"
        ) as tmp:
            tmp_path = tmp.name
        try:
            os.environ["GITHUB_STEP_SUMMARY"] = tmp_path
            vf._write_step_summary(
                "error", 0, 1, ["no .rb files found in ."]
            )
            content = Path(tmp_path).read_text(encoding="utf-8")
            self.assertIn("| ❌ error | 0 | 1 |", content)
        finally:
            os.unlink(tmp_path)

    def test_many_errors_are_capped_and_footer_added(self):
        # Exceed MAX_STEP_SUMMARY_ERRORS and check both halves of the
        # cap: the visible list is truncated AND a "...and N more"
        # footer is emitted. Missing either half of this branch would
        # blow up the summary or hide the overflow.
        import tempfile
        cap = vf.MAX_STEP_SUMMARY_ERRORS
        errors = [f"formula-{i}.rb: err {i}" for i in range(cap + 5)]
        with tempfile.NamedTemporaryFile(
            "w+", delete=False, suffix=".md"
        ) as tmp:
            tmp_path = tmp.name
        try:
            os.environ["GITHUB_STEP_SUMMARY"] = tmp_path
            vf._write_step_summary("fail", 100, len(errors), errors)
            content = Path(tmp_path).read_text(encoding="utf-8")
            self.assertIn(f"- formula-{cap - 1}.rb: err {cap - 1}", content)
            self.assertNotIn(f"- formula-{cap}.rb", content)
            self.assertIn(f"...and 5 more (see step log)", content)
        finally:
            os.unlink(tmp_path)

    def test_emit_summary_defaults_errors_to_empty_list(self):
        # emit_summary(errors=None) must forward [] to
        # _write_step_summary and never propagate None into the list
        # slice, which would raise TypeError.
        import tempfile
        import io
        import contextlib
        with tempfile.NamedTemporaryFile(
            "w+", delete=False, suffix=".md"
        ) as tmp:
            tmp_path = tmp.name
        try:
            os.environ["GITHUB_STEP_SUMMARY"] = tmp_path
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                vf.emit_summary(
                    status="pass", formula_count=1, error_count=0
                )
            self.assertIn("VALIDATE_FORMULAE_SUMMARY:", buf.getvalue())
            content = Path(tmp_path).read_text(encoding="utf-8")
            self.assertIn("| ✅ pass | 1 | 0 |", content)
            self.assertNotIn("<details>", content)
        finally:
            os.unlink(tmp_path)

    def test_summary_appends_and_does_not_overwrite(self):
        # The helper opens with mode "a"; if a future refactor flipped
        # to "w" it would clobber whatever the prior step wrote to the
        # same summary file. Guard that behavioural contract explicitly.
        import tempfile
        with tempfile.NamedTemporaryFile(
            "w+", delete=False, suffix=".md"
        ) as tmp:
            tmp.write("prior-step-output\n")
            tmp_path = tmp.name
        try:
            os.environ["GITHUB_STEP_SUMMARY"] = tmp_path
            vf._write_step_summary("pass", 2, 0, [])
            content = Path(tmp_path).read_text(encoding="utf-8")
            self.assertIn("prior-step-output", content)
            self.assertIn("### Formula drift check", content)
        finally:
            os.unlink(tmp_path)


if __name__ == "__main__":
    unittest.main()
