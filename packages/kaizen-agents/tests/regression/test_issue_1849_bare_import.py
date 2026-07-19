"""Regression test for issue #1849 — bare kaizen-agents install unimportable.

Bug: ``import kaizen_agents.agents`` (and any ``kaizen_agents.agents.specialized.*``
agent) raised ``ImportError`` on a bare ``pip install kailash-kaizen-agents`` because
an unguarded module-scope import chain eager-loaded numpy:

    agents/__init__.py       -> from kaizen_agents.agents import register_builtin
    register_builtin.py      -> from ...specialized.rag_research import RAGResearchAgent
    specialized/__init__.py  -> from ...rag_research import RAGResearchAgent
    rag_research.py          -> from kaizen.retrieval.vector_store import SimpleVectorStore
    vector_store.py          -> import numpy as np

numpy is declared by NO manifest on a bare kaizen-agents install — it ships only
under ``kailash-kaizen[rag]``. So every non-RAG specialized agent (chain_of_thought,
etc.) was collateral-damaged by RAGResearchAgent's optional dependency.

The fix lazy-loads RAGResearchAgent (PEP 562 ``__getattr__``) and guards its
registration behind ``try/except ImportError`` so importing any other agent — or
the registry — never requires numpy. RAGResearchAgent itself keeps working when
numpy IS present.

These tests exercise the REAL import with numpy GENUINELY ABSENT: each runs in a
fresh subprocess whose ``sys.meta_path`` blocks numpy (and every ``numpy.*``
submodule) before the target import, and drops any preloaded numpy from
``sys.modules``. numpy is not mocked — it is made unavailable, exactly as a bare
install would leave it. They FAIL on pre-fix main (eager numpy import) and PASS
with the fix.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

# Prelude installed in every child interpreter: block numpy for real.
_BLOCK_NUMPY = """
import sys

class _NumpyBlocker:
    def find_spec(self, name, path=None, target=None):
        if name == "numpy" or name.startswith("numpy."):
            raise ImportError(
                "numpy blocked (issue #1849 regression: simulating a bare "
                "kaizen-agents install without kailash-kaizen[rag])"
            )
        return None

sys.meta_path.insert(0, _NumpyBlocker())
for _m in [m for m in sys.modules if m == "numpy" or m.startswith("numpy.")]:
    del sys.modules[_m]

# Sanity: numpy must genuinely be unavailable in this interpreter.
try:
    import numpy  # noqa: F401
except ImportError:
    pass
else:  # pragma: no cover - defensive
    raise AssertionError("numpy blocker failed; test would be vacuous")
"""


def _run_without_numpy(body: str) -> subprocess.CompletedProcess:
    """Run ``body`` in a fresh interpreter with numpy blocked for real."""
    script = _BLOCK_NUMPY + textwrap.dedent(body)
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
    )


@pytest.mark.regression
def test_specialized_agent_imports_without_numpy():
    """A non-RAG specialized agent imports with numpy absent (the core defect)."""
    result = _run_without_numpy(
        """
        import kaizen_agents.agents.specialized.chain_of_thought as cot
        assert hasattr(cot, "ChainOfThoughtAgent")
        print("OK: specialized import without numpy")
        """
    )
    assert result.returncode == 0, (
        "importing a non-RAG specialized agent must not require numpy\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "OK: specialized import without numpy" in result.stdout


@pytest.mark.regression
def test_agents_registry_imports_without_numpy():
    """``import kaizen_agents.agents`` (the registry) succeeds with numpy absent."""
    result = _run_without_numpy(
        """
        import kaizen_agents.agents as agents
        from kaizen_agents.agents import is_agent_type_registered

        # The registry loads and non-RAG agents register without numpy.
        assert is_agent_type_registered("simple")
        assert is_agent_type_registered("cot")
        # "rag" is skipped (guarded) when numpy is unavailable.
        assert not is_agent_type_registered("rag")
        print("OK: registry import without numpy")
        """
    )
    assert result.returncode == 0, (
        "importing kaizen_agents.agents must not require numpy\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "OK: registry import without numpy" in result.stdout


@pytest.mark.regression
def test_direct_rag_import_raises_actionable_error_without_numpy():
    """The AC-named direct import raises an ACTIONABLE ImportError (issue #1849 AC2).

    ``from kaizen_agents.agents.specialized.rag_research import RAGResearchAgent``
    on a bare install (no numpy) must fail with guidance naming
    ``kailash-kaizen[rag]`` — NOT a raw ``ModuleNotFoundError: No module named
    'numpy'``. The original cause stays chained (``raise ... from exc``), so this
    is an actionable re-raise, not a silent swallow.
    """
    result = _run_without_numpy(
        """
        try:
            from kaizen_agents.agents.specialized.rag_research import (
                RAGResearchAgent,  # noqa: F401
            )
        except ImportError as exc:
            msg = str(exc)
            assert "kailash-kaizen[rag]" in msg, f"not actionable: {msg!r}"
            assert msg != "No module named 'numpy'", "still a bare ModuleNotFoundError"
            assert exc.__cause__ is not None, "original cause not chained"
            print("OK: actionable ImportError on direct RAGResearchAgent import")
        else:
            raise AssertionError("expected ImportError with numpy absent")
        """
    )
    assert result.returncode == 0, (
        "direct RAGResearchAgent import must raise an actionable ImportError\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert (
        "OK: actionable ImportError on direct RAGResearchAgent import" in result.stdout
    )


@pytest.mark.regression
def test_top_level_kaizen_agents_imports_without_numpy():
    """``import kaizen_agents`` (top-level package) succeeds with numpy absent."""
    result = _run_without_numpy(
        """
        import kaizen_agents  # noqa: F401
        print("OK: top-level import without numpy")
        """
    )
    assert result.returncode == 0, (
        "importing kaizen_agents must not require numpy\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "OK: top-level import without numpy" in result.stdout
