"""
Tests for the ``sys.path`` shim in scripts/__init__.py.

kubestellar/homebrew-tap#585 replaced the per-file

    sys.path.insert(0, str(Path(__file__).parent))

shim at the top of every scripts/test_*.py module with a single
insertion in the ``scripts`` package ``__init__``. Nothing else in the
suite exercises that file: ``unittest discover -s scripts`` (the CI
form) and ``python3 scripts/test_foo.py`` (the standalone form) never
import it, so a regression there is only visible from the one form it
exists for — ``python3 -m unittest scripts.test_foo`` from the
repository root — which CI does not run. These tests run that form, and
the shim itself, in subprocesses so the guarantees are pinned:

* **package form works** — ``python3 -m unittest scripts.<module>``
  from the repository root imports a real test module whose bare
  helper imports resolve only via the shim;
* **precedence** — after ``import scripts``, ``scripts/`` is
  ``sys.path[0]`` even when the same directory was already present
  *later* on the path (via ``PYTHONPATH``), matching the old per-file
  ``insert(0, ...)``, so a same-named module earlier on the path cannot
  shadow the tap's helpers;
* **idempotence** — re-importing the package (pytest's ``prepend``
  import mode does this) leaves exactly one ``scripts/`` entry;
* **cwd entry untouched** — the ``''`` entry Python adds for ``-c`` /
  ``-m`` is not mistaken for ``scripts/`` and removed.

Run standalone with ``python3 scripts/test_scripts_package_syspath.py``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

# A small, network-free test module whose bare imports (formula_parser)
# resolve only because scripts/ is on sys.path.
PACKAGE_FORM_MODULE = "scripts.test_formula_parser_regexes"

_PROBE = """
import json, os, sys
import scripts
entries = [e for e in sys.path if e and os.path.realpath(e) == scripts._SCRIPTS_DIR]
first = sys.path[0]
import importlib
importlib.reload(scripts)
entries_after_reload = [e for e in sys.path if e and os.path.realpath(e) == scripts._SCRIPTS_DIR]
print(json.dumps({
    "scripts_dir": scripts._SCRIPTS_DIR,
    "first": first,
    "first_real": os.path.realpath(first),
    "count": len(entries),
    "count_after_reload": len(entries_after_reload),
    "first_after_reload_real": os.path.realpath(sys.path[0]),
    "has_cwd_entry": "" in sys.path,
}))
"""


def _run(argv: list[str], *, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONSAFEPATH", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, *argv],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _probe(**extra_env: str) -> dict[str, object]:
    proc = _run(["-c", _PROBE], extra_env=extra_env)
    if proc.returncode != 0:
        raise AssertionError(f"probe failed rc={proc.returncode}\n{proc.stderr}")
    result: dict[str, object] = json.loads(proc.stdout)
    return result


class ScriptsPackageSysPathShim(unittest.TestCase):
    def test_package_form_unittest_passes(self) -> None:
        proc = _run(["-m", "unittest", PACKAGE_FORM_MODULE])
        self.assertEqual(
            proc.returncode,
            0,
            f"python3 -m unittest {PACKAGE_FORM_MODULE} failed:\n{proc.stderr}",
        )
        self.assertIn("OK", proc.stderr.strip().splitlines()[-1])

    def test_import_puts_scripts_dir_first(self) -> None:
        info = _probe()
        self.assertEqual(info["scripts_dir"], str(SCRIPTS_DIR))
        self.assertEqual(info["first_real"], str(SCRIPTS_DIR))
        self.assertEqual(info["count"], 1)

    def test_precedence_when_scripts_dir_already_later_on_path(self) -> None:
        # A different spelling of scripts/ (trailing slash, via PYTHONPATH,
        # which lands after the '' cwd entry) must be collapsed and moved
        # to the front, not left behind an earlier same-named module.
        info = _probe(PYTHONPATH=str(SCRIPTS_DIR) + os.sep)
        self.assertEqual(info["first_real"], str(SCRIPTS_DIR))
        self.assertEqual(info["count"], 1, "duplicate scripts/ entries left on sys.path")

    def test_reimport_is_idempotent(self) -> None:
        info = _probe()
        self.assertEqual(info["count_after_reload"], 1)
        self.assertEqual(info["first_after_reload_real"], str(SCRIPTS_DIR))

    def test_cwd_entry_is_preserved(self) -> None:
        info = _probe()
        self.assertTrue(info["has_cwd_entry"], "the '' cwd entry must not be removed")


if __name__ == "__main__":
    unittest.main()
