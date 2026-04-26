# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 — ``MLAwareAgent`` constructs tools from ``km.list_engines()``.

Spec ``specs/kaizen-ml-integration.md §2.4.7`` mandates this wiring
test: a real :class:`~kaizen.ml.MLAwareAgent` is constructed against
the live ``kailash_ml`` registry, the LLM-visible tool-spec list is
inspected, and the version-sync invariant (§2.4.4 / §E11.3 MUST 3) is
asserted on the observable tool surface — not just on the
``EngineInfo.version`` field.

Per ``rules/orphan-detection.md`` §1 + ``rules/facade-manager-detection.md``
§1, this test proves that the discovery surface
(:func:`kaizen.ml.discover_ml_tools`) is invoked from the framework's
production hot path (:class:`MLAwareAgent.__init__`), not just from
isolated tests.

Skip semantics: the registry helpers ship in the kailash-ml 1.0 wave;
when they are not yet installed, the test asserts the typed-error
contract per §2.4.5 instead of silent-skipping.
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_ml_aware_agent_builds_tools_from_km_registry() -> None:
    """Spec §2.4.7 wiring test.

    Per spec §2.4.7 the test:

    1. Constructs a real :class:`MLAwareAgent` (with the canonical
       ``mock`` LLM provider so we don't make external API calls).
    2. Asserts the agent's ``ml_tools`` contains one entry per
       ``MethodSignature`` across every registered engine.
    3. Asserts every tool's ``description`` field embeds the runtime
       ``kailash_ml.__version__`` — the version-sync invariant
       observable on the LLM-visible tool surface.

    When the registry is NOT yet shipped, asserts the
    :class:`MLRegistryUnavailableError` contract per §2.4.5 (no
    direct-import fallback).
    """
    from kaizen.core.config import BaseAgentConfig
    from kaizen.ml import MLAwareAgent, MLRegistryUnavailableError

    try:
        import kailash_ml as km
    except ImportError:
        pytest.skip("kailash-ml not installed (infra-conditional)")

    has_registry = hasattr(km, "engine_info") and hasattr(km, "list_engines")

    config = BaseAgentConfig(llm_provider="mock")

    if not has_registry:
        # Spec §2.4.5: hardcoded engine imports are BLOCKED. The agent
        # MUST surface MLRegistryUnavailableError, not silently fall
        # back to direct imports.
        with pytest.raises(MLRegistryUnavailableError) as exc_info:
            MLAwareAgent(config=config)
        message = str(exc_info.value).lower()
        assert (
            "engine_info" in message and "list_engines" in message
        ), "registry-missing error must name the helpers (actionable)"
        return

    # Registry is live — exercise the discovery + tool-construction
    # path through the framework's production hot path.
    agent = MLAwareAgent(config=config)

    # 1. Tool count parity — one tool per MethodSignature across
    #    every registered engine.
    expected_tool_count = sum(
        len(engine_info.signatures) for engine_info in km.list_engines()
    )
    assert len(agent.ml_tools) == expected_tool_count, (
        f"expected {expected_tool_count} tools (one per MethodSignature "
        f"across {len(km.list_engines())} engines), got {len(agent.ml_tools)}"
    )

    # 2. Engine count parity — agent.ml_engines mirrors km.list_engines()
    #    when no clearance filter is active (single-tenant default).
    assert len(agent.ml_engines) == len(km.list_engines()), (
        f"engine snapshot drift: agent.ml_engines={len(agent.ml_engines)} "
        f"!= km.list_engines()={len(km.list_engines())}"
    )

    # 3. Version-sync invariant on the LLM-visible tool surface.
    #    Spec §2.4.4 / §E11.3 MUST 3: the tool description MUST embed
    #    kailash_ml.__version__ so a future kailash-ml bump that does
    #    NOT propagate to the tool surface flips this test red.
    for tool in agent.ml_tools:
        assert km.__version__ in tool.description, (
            f"tool {tool.name!r} description missing runtime "
            f"kailash_ml.__version__ {km.__version__!r} — §2.4.4 "
            f"version-sync invariant violation: {tool.description!r}"
        )


@pytest.mark.integration
def test_ml_aware_agent_tool_names_are_engine_dot_method() -> None:
    """Spec §2.4.6: tool names follow ``{engine.name}.{method_name}``.

    The naming convention is the LLM-visible binding from a tool call
    back to the canonical engine + method, so the agent runtime can
    resolve a tool selection back to the engine via
    :attr:`MLAwareAgent.ml_engines` (no hardcoded import needed).
    """
    from kaizen.core.config import BaseAgentConfig
    from kaizen.ml import MLAwareAgent, MLRegistryUnavailableError

    config = BaseAgentConfig(llm_provider="mock")

    try:
        agent = MLAwareAgent(config=config)
    except MLRegistryUnavailableError:
        pytest.skip("ml registry not yet shipped — covered in symbols suite")
    except ImportError:
        pytest.skip("kailash-ml not installed")

    for tool in agent.ml_tools:
        # Every tool name MUST be "engine.method" (exactly one dot
        # — engine names from §E1.1 are simple identifiers, never
        # contain dots themselves).
        assert tool.name.count(".") == 1, (
            f"tool name {tool.name!r} must follow 'engine.method' "
            f"convention per spec §2.4.6"
        )
        engine_part, method_part = tool.name.split(".")
        assert engine_part, "engine part of tool name is empty"
        assert method_part, "method part of tool name is empty"

        # The engine part MUST resolve to a real engine in the
        # snapshot — proves the construction path didn't fabricate
        # tool names from a hardcoded list.
        engine_names = {e.name for e in agent.ml_engines}
        assert engine_part in engine_names, (
            f"tool {tool.name!r} references engine {engine_part!r} "
            f"not in km.list_engines() snapshot {sorted(engine_names)}"
        )


@pytest.mark.integration
def test_ml_aware_agent_tools_immutable_across_turn() -> None:
    """Spec §2.4.6: tool snapshot captured at agent start stays consistent.

    A tuple is immutable; this test asserts the contract is enforced
    structurally (tuple, not list) so the LLM tool-spec list captured
    at the start of a turn cannot be mutated mid-turn.
    """
    from kaizen.core.config import BaseAgentConfig
    from kaizen.ml import MLAwareAgent, MLRegistryUnavailableError

    config = BaseAgentConfig(llm_provider="mock")

    try:
        agent = MLAwareAgent(config=config)
    except MLRegistryUnavailableError:
        pytest.skip("ml registry not yet shipped — covered in symbols suite")
    except ImportError:
        pytest.skip("kailash-ml not installed")

    # Tuple guarantee — mutation operations MUST raise.
    assert isinstance(
        agent.ml_tools, tuple
    ), f"ml_tools must be tuple for immutability; got {type(agent.ml_tools)}"
    assert isinstance(
        agent.ml_engines, tuple
    ), f"ml_engines must be tuple for immutability; got {type(agent.ml_engines)}"

    # Sanity: tuples have no append/extend (a mutation attempt would
    # AttributeError, not silently mutate).
    with pytest.raises(AttributeError):
        agent.ml_tools.append(None)  # type: ignore[attr-defined]


@pytest.mark.integration
def test_ml_aware_agent_tenant_id_recorded() -> None:
    """Spec §2.4.3: tenant_id flows through to discovery.

    Without a clearance_filter, every engine is exposed — but the
    tenant_id MUST still be recorded for downstream PACT layers to
    consume.
    """
    from kaizen.core.config import BaseAgentConfig
    from kaizen.ml import MLAwareAgent, MLRegistryUnavailableError

    config = BaseAgentConfig(llm_provider="mock")

    try:
        single = MLAwareAgent(config=config)  # tenant_id=None
    except MLRegistryUnavailableError:
        pytest.skip("ml registry not yet shipped — covered in symbols suite")
    except ImportError:
        pytest.skip("kailash-ml not installed")

    multi = MLAwareAgent(config=config, tenant_id="acme")

    assert single._tenant_id is None
    assert multi._tenant_id == "acme"
    # Without a clearance_filter, both agents see the same engine set
    # — single-tenant mode is the spec §2.4.3 default behavior.
    assert len(single.ml_engines) == len(multi.ml_engines)
