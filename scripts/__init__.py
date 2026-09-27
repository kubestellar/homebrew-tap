"""Package marker for ``scripts/`` that puts this directory on ``sys.path``.

The ``scripts/test_*.py`` modules import their shared helpers by bare
name (``from formula_parser import ...``, ``import coverage_gate``,
``import lib_emit_summary``, ...). Each of them used to carry its own
copy of::

    sys.path.insert(0, str(Path(__file__).parent))

so that bare import resolves regardless of how the test is launched
(kubestellar/homebrew-tap#585). This module is the single replacement
for those per-file copies. Every supported invocation now resolves the
bare imports without a file-local shim:

* ``python3 -m unittest discover -s scripts -p 'test_*.py'`` — the CI
  form (``scripts/unittest_summary.sh``, ``scripts/coverage_gate.py``).
  ``discover`` already inserts the start directory on ``sys.path``; this
  file is not even imported.
* ``python3 scripts/test_foo.py`` — the standalone form documented in
  each test module's docstring. Python puts the script's own directory
  at ``sys.path[0]``; this file is not imported here either.
* ``python3 -m unittest scripts/test_foo.py`` (or ``scripts.test_foo``)
  from the repository root — unittest imports the test as
  ``scripts.test_foo``, which imports this package ``__init__`` first.
  Without it, ``scripts/`` is *not* on ``sys.path`` and the bare
  imports fail; this is the one form the old per-file shim existed for.
  Note that a ``scripts/_testsupport.py`` helper could not serve this
  form: importing it by bare name has the same chicken-and-egg problem
  as the helpers it would be adding to the path.

The insertion is idempotent so repeated imports (e.g. under ``pytest``,
whose default ``prepend`` import mode also loads this package) do not
grow ``sys.path``. It also preserves the *precedence* the per-file shim
had: that shim always ``insert(0, ...)``-ed, so ``scripts/`` shadowed any
same-named module earlier on the path (a stray top-level
``coverage_gate`` or ``formula_parser`` from ``PYTHONPATH``, say). A
plain ``if dir not in sys.path`` guard would skip the insert when the
directory is already present *later* in the path and silently lose that
shadowing, so the shim removes any existing entry for this directory
(compared by real path, since ``discover`` and ``PYTHONPATH`` spell it
differently) and re-inserts it at index 0.

One consequence of the package form is worth knowing: a test module
that imports a *sibling test module* by bare name (today only
``test_lockstep_nightly_tolerance_invariants`` →
``test_crossformula_invariants``) gets the top-level copy of that
module, not ``scripts.test_crossformula_invariants``. That is the same
module object the bare-import helpers resolve to and is harmless for
sharing helpers, but if both spellings are loaded in one process the
sibling's ``TestCase`` classes exist under two module identities. The
CI and standalone forms never import under the package name, so this
only affects ad-hoc ``python3 -m unittest scripts.test_a scripts.test_b``
invocations.

``scripts/test_scripts_package_syspath.py`` pins these guarantees
(precedence, idempotence, the package form) in subprocesses.

Not itself a test module (does not match the ``test_*.py`` discovery
pattern) and not on the ``.coveragerc`` 100% ratchet: it carries no
production logic, only the import-path setup the test modules need.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)


def _is_scripts_dir(entry: str) -> bool:
    # '' means the cwd and is left alone; non-str entries belong to path hooks.
    return isinstance(entry, str) and bool(entry) and os.path.realpath(entry) == _SCRIPTS_DIR


sys.path[:] = [entry for entry in sys.path if not _is_scripts_dir(entry)]
sys.path.insert(0, _SCRIPTS_DIR)
