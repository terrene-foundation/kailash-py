"""Regression test for issue #1071 Gap A — kaizen.api deprecation shim.

The structural-split refactor (#75) moved the unified Agent API from
``kaizen.api`` to ``kaizen_agents.api`` and removed ``kaizen.api`` outright
with no deprecation cycle, so ``from kaizen.api import Agent`` began raising
``ModuleNotFoundError`` on every published release. This test pins the
deprecation-shim contract:

- ``from kaizen.api import Agent`` succeeds AND emits a ``DeprecationWarning``
  naming the new import path (``from kaizen import Agent``).
- Every historical secondary symbol resolves through the shim with its own
  ``DeprecationWarning``.
- Unknown attributes raise ``AttributeError`` (not silent ``None``).

Tier 2 — real imports, no mocking.
"""

import warnings

import pytest


def test_from_kaizen_api_import_agent_succeeds_and_warns():
    """`from kaizen.api import Agent` resolves AND emits a DeprecationWarning."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        from kaizen.api import Agent  # noqa: PLC0415 — exercising the shim

    assert Agent is not None
    # Agent must be the same object kaizen exports (the canonical entry point).
    import kaizen

    assert Agent is kaizen.Agent

    dep_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert dep_warnings, "kaizen.api.Agent access emitted no DeprecationWarning"
    msg = str(dep_warnings[0].message)
    assert "kaizen.api" in msg
    assert "from kaizen import Agent" in msg


def test_kaizen_api_agent_attribute_access_warns():
    """`pytest.warns(DeprecationWarning)` on attribute access (PEP 562)."""
    import kaizen.api

    with pytest.warns(DeprecationWarning, match="from kaizen import Agent"):
        _ = kaizen.api.Agent


@pytest.mark.parametrize(
    "symbol",
    [
        "AgentConfig",
        "AgentResult",
        "ToolCallRecord",
        "CapabilityPresets",
        "AgentCapabilities",
        "ExecutionMode",
        "MemoryDepth",
        "ToolAccess",
        "ConfigurationError",
        "validate_configuration",
        "validate_model_runtime_compatibility",
        "resolve_memory_shortcut",
        "resolve_runtime_shortcut",
        "resolve_tool_access_shortcut",
    ],
)
def test_historical_secondary_symbols_resolve_and_warn(symbol):
    """Every historical secondary symbol resolves through the shim + warns."""
    import kaizen.api

    with pytest.warns(DeprecationWarning, match="kaizen_agents.api"):
        resolved = getattr(kaizen.api, symbol)
    assert resolved is not None

    # Parity: the shim resolves the SAME object as the canonical module.
    import kaizen_agents.api

    assert resolved is getattr(kaizen_agents.api, symbol)


def test_unknown_attribute_raises_attribute_error():
    """Unknown attributes raise AttributeError, never silent None."""
    import kaizen.api

    with pytest.raises(AttributeError, match="has no attribute"):
        _ = kaizen.api.NoSuchSymbol


def test_dunder_all_covers_full_historical_surface():
    """__all__ enumerates the full recovered historical surface (15 symbols)."""
    import kaizen.api

    expected = {
        "Agent",
        "AgentConfig",
        "AgentResult",
        "ToolCallRecord",
        "CapabilityPresets",
        "AgentCapabilities",
        "ExecutionMode",
        "MemoryDepth",
        "ToolAccess",
        "ConfigurationError",
        "validate_configuration",
        "validate_model_runtime_compatibility",
        "resolve_memory_shortcut",
        "resolve_runtime_shortcut",
        "resolve_tool_access_shortcut",
    }
    assert set(kaizen.api.__all__) == expected
