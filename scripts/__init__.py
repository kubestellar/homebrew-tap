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
grow ``sys.path``.

Not itself a test module (does not match the ``test_*.py`` discovery
pattern) and not on the ``.coveragerc`` 100% ratchet: it carries no
production logic, only the import-path setup the test modules need.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)

if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
