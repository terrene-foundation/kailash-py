"""Regression: `kaizen.research` must not eagerly import GitPython.

GitPython (`git`) is an OPTIONAL extra — `research-validator` in
`packages/kailash-kaizen/pyproject.toml`. `kaizen/research/validator.py`
previously did an unconditional module-scope `import git`, and
`kaizen/research/__init__.py` eagerly imports `validator` — so importing
anything under `kaizen.research` raised `ModuleNotFoundError: No module
named 'git'` on every environment without the optional extra installed,
including the kaizen regression-test collection gate (it blocked
`pytest --collect-only` on `tests/regression/`).

Fix: `import git` is now lazy — inside `ResearchValidator._clone_repository`,
the single call site — with a clear install hint raised on `ImportError`.
The module imports clean without the extra; the GitPython requirement
surfaces (loudly, with a fix instruction) only when repository cloning runs.

These tests run regardless of whether GitPython is installed: they assert
the IMPORT graph does not pull `git` in, which holds either way.
"""

from __future__ import annotations

import importlib
import sys

import pytest


def _drop_from_sys_modules(*prefixes: str) -> None:
    """Evict cached modules so the next import is exercised fresh."""
    for name in list(sys.modules):
        for prefix in prefixes:
            if name == prefix or name.startswith(prefix + "."):
                del sys.modules[name]
                break


@pytest.mark.regression
def test_research_validator_module_imports_without_eager_git():
    """Importing the validator module MUST NOT pull `git` into sys.modules."""
    _drop_from_sys_modules("git", "kaizen.research.validator")

    importlib.import_module("kaizen.research.validator")

    assert "git" not in sys.modules, (
        "kaizen.research.validator eagerly imported GitPython — `import git` "
        "must stay lazy (inside ResearchValidator._clone_repository) so the "
        "optional `research-validator` extra is not required to import it."
    )


@pytest.mark.regression
def test_research_package_imports_without_eager_git():
    """`import kaizen.research` eagerly imports validator — still no `git`."""
    _drop_from_sys_modules("git", "kaizen.research")

    importlib.import_module("kaizen.research")

    assert "git" not in sys.modules, (
        "import kaizen.research transitively eager-imported GitPython via "
        "kaizen/research/__init__.py -> .validator -> import git."
    )
