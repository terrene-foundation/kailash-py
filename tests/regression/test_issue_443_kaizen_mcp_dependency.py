"""Regression tests for issue #443 — kailash-kaizen missing kailash-mcp dependency.

Issue: https://github.com/terrene-foundation/kailash-py/issues/443

kailash-kaizen >= 2.7.0 imports `from kailash_mcp.client import MCPClient` in
`kaizen/core/base_agent.py` (top-level, unconditional). Without `kailash-mcp`
declared as a dependency, fresh PyPI installs of kailash-kaizen fail with
ModuleNotFoundError on `import kaizen`.

These tests are behavioral (per rules/testing.md): they exercise the actual
import path AND verify the dependency declaration via importlib.metadata
(install-time config, not source-grep).
"""

from __future__ import annotations

import importlib.metadata

import pytest


@pytest.mark.regression
def test_kailash_mcp_module_imports():
    """Issue #443: kailash_mcp must be importable in the kailash-kaizen runtime."""
    import kailash_mcp  # noqa: F401

    assert kailash_mcp is not None


@pytest.mark.regression
def test_kaizen_base_agent_imports():
    """Issue #443: kaizen.core.base_agent imports kailash_mcp.client at top level.

    If kailash-mcp is missing from the runtime, this import raises
    ModuleNotFoundError because base_agent.py:34 imports MCPClient
    unconditionally at module load time.
    """
    from kaizen.core.base_agent import BaseAgent

    assert BaseAgent is not None


@pytest.mark.regression
def test_kaizen_agents_delegate_imports():
    """Issue #443: kaizen_agents.Delegate is the canonical async agent entry point.

    kaizen_agents.Delegate inherits from kaizen.core BaseAgent, so the same
    import chain that broke base_agent broke every Delegate consumer.
    """
    from kaizen_agents import Delegate

    assert Delegate is not None


@pytest.mark.regression
def test_kailash_kaizen_declares_kailash_mcp_dependency():
    """Issue #443: kailash-kaizen's package metadata MUST list kailash-mcp.

    Reading install-time requirements via importlib.metadata is the
    canonical way to verify a dependency declaration. This is NOT source-grep
    (per rules/testing.md) — it reads the actual install metadata that pip
    and uv use at install time.
    """
    from packaging.requirements import Requirement

    requires = importlib.metadata.requires("kailash-kaizen")
    assert (
        requires is not None
    ), "kailash-kaizen has no requires metadata — package may be broken"

    # Use the canonical requirement parser instead of hand-rolled split()
    # chains: handles >=, <=, ~=, !=, ==, extras, environment markers,
    # and combined specifiers like "kailash-mcp>=0.2.3,<1.0".
    declared_names = {Requirement(req).name for req in requires}
    assert "kailash-mcp" in declared_names, (
        f"kailash-kaizen does NOT declare kailash-mcp as a dependency. "
        f"Declared: {sorted(declared_names)}"
    )
