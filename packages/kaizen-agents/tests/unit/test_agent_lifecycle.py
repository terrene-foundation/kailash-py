# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for kaizen_agents._agent_lifecycle — AgentLifecycleManager.

Tier 1: Unit tests. Uses real SDK AgentFactory + AgentInstanceRegistry (no mocking
of SDK). Tests agent spawning, termination, state transitions, child tracking,
lineage, and local-to-SDK spec conversion.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from kaizen.l3.factory.factory import AgentFactory
from kaizen.l3.factory.instance import (
    AgentInstance as SdkAgentInstance,
    AgentLifecycleState,
    TerminationReason as SdkTerminationReason,
    _StateTag,
)
from kaizen.l3.factory.registry import AgentInstanceRegistry
from kaizen.l3.factory.spec import AgentSpec as SdkAgentSpec

from kaizen_agents._agent_lifecycle import AgentLifecycleManager
from kaizen_agents.types import (
    AgentSpec as LocalAgentSpec,
    ConstraintEnvelope,
    make_envelope,
    MemoryConfig,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_local_spec(
    spec_id: str = "spec-test",
    name: str = "test-agent",
    capabilities: list[str] | None = None,
    tool_ids: list[str] | None = None,
    envelope: ConstraintEnvelope | None = None,
    memory_config: MemoryConfig | None = None,
    max_lifetime: timedelta | None = None,
    max_children: int | None = None,
    max_depth: int | None = None,
    required_context_keys: list[str] | None = None,
    produced_context_keys: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> LocalAgentSpec:
    """Create a local AgentSpec with sensible defaults for testing."""
    return LocalAgentSpec(
        spec_id=spec_id,
        name=name,
        description=f"Agent: {name}",
        capabilities=capabilities or ["test"],
        tool_ids=tool_ids or [],
        envelope=envelope or make_envelope(financial={"limit": 5.0}),
        memory_config=memory_config or MemoryConfig(session=True, shared=False, persistent=False),
        max_lifetime=max_lifetime,
        max_children=max_children,
        max_depth=max_depth,
        required_context_keys=required_context_keys or [],
        produced_context_keys=produced_context_keys or [],
        metadata=metadata or {},
    )


def _make_lifecycle_manager() -> tuple[AgentLifecycleManager, AgentFactory, AgentInstanceRegistry]:
    """Create an AgentLifecycleManager with fresh factory and registry."""
    registry = AgentInstanceRegistry()
    factory = AgentFactory(registry)
    manager = AgentLifecycleManager(factory=factory, registry=registry)
    return manager, factory, registry


# ---------------------------------------------------------------------------
# Test: spawn_agent creates instance via SDK factory
# ---------------------------------------------------------------------------


class TestSpawnAgent:
    """spawn_agent should convert local spec to SDK spec and spawn via factory."""

    async def test_spawn_root_agent_returns_sdk_instance(self) -> None:
        """Spawning a root agent (no parent) returns a valid SDK AgentInstance."""
        manager, factory, registry = _make_lifecycle_manager()
        local_spec = _make_local_spec(spec_id="spec-root", name="root-agent")

        instance = await manager.spawn_agent(local_spec)

        assert isinstance(instance, SdkAgentInstance)
        assert instance.spec_id == "spec-root"
        assert instance.parent_id is None
        assert instance.state.tag == _StateTag.PENDING

    async def test_spawn_child_agent_with_parent(self) -> None:
        """Spawning a child agent with a valid parent links them in the hierarchy."""
        manager, factory, registry = _make_lifecycle_manager()

        # Spawn root and transition to running (required for spawning children)
        parent_spec = _make_local_spec(spec_id="spec-parent", name="parent")
        parent = await manager.spawn_agent(parent_spec)
        await manager.mark_running(parent.instance_id)

        # Spawn child under parent
        child_spec = _make_local_spec(spec_id="spec-child", name="child")
        child = await manager.spawn_agent(child_spec, parent_id=parent.instance_id)

        assert isinstance(child, SdkAgentInstance)
        assert child.parent_id == parent.instance_id
        assert child.spec_id == "spec-child"

    async def test_spawn_agent_registers_in_registry(self) -> None:
        """Spawned agents should be retrievable from the registry."""
        manager, factory, registry = _make_lifecycle_manager()
        local_spec = _make_local_spec(spec_id="spec-reg", name="registered")

        instance = await manager.spawn_agent(local_spec)

        # Should be findable in registry
        fetched = await registry.get(instance.instance_id)
        assert fetched.instance_id == instance.instance_id
        assert fetched.spec_id == "spec-reg"

    async def test_spawn_multiple_children(self) -> None:
        """Multiple children can be spawned under the same parent."""
        manager, factory, registry = _make_lifecycle_manager()

        parent_spec = _make_local_spec(spec_id="spec-parent", name="parent")
        parent = await manager.spawn_agent(parent_spec)
        await manager.mark_running(parent.instance_id)

        child_ids = []
        for i in range(3):
            child_spec = _make_local_spec(spec_id=f"spec-child-{i}", name=f"child-{i}")
            child = await manager.spawn_agent(child_spec, parent_id=parent.instance_id)
            child_ids.append(child.instance_id)

        children = await manager.get_children(parent.instance_id)
        assert len(children) == 3
        assert {c.instance_id for c in children} == set(child_ids)


# ---------------------------------------------------------------------------
# Test: terminate_agent cascades to children
# ---------------------------------------------------------------------------


class TestTerminateAgent:
    """terminate_agent should cascade termination to all descendants."""

    async def test_terminate_root_agent(self) -> None:
        """Terminating a root agent moves it to terminated state."""
        manager, factory, registry = _make_lifecycle_manager()
        spec = _make_local_spec(spec_id="spec-term", name="term-agent")
        instance = await manager.spawn_agent(spec)
        await manager.mark_running(instance.instance_id)

        await manager.terminate_agent(instance.instance_id, reason="explicit_termination")

        fetched = await registry.get(instance.instance_id)
        assert fetched.is_terminal
        assert fetched.state.tag == _StateTag.TERMINATED

    async def test_terminate_cascades_to_children(self) -> None:
        """Terminating a parent cascades to all its children (deepest first)."""
        manager, factory, registry = _make_lifecycle_manager()

        # Build hierarchy: root -> child -> grandchild
        root_spec = _make_local_spec(spec_id="spec-root", name="root")
        root = await manager.spawn_agent(root_spec)
        await manager.mark_running(root.instance_id)

        child_spec = _make_local_spec(spec_id="spec-child", name="child")
        child = await manager.spawn_agent(child_spec, parent_id=root.instance_id)
        await manager.mark_running(child.instance_id)

        grandchild_spec = _make_local_spec(spec_id="spec-grandchild", name="grandchild")
        grandchild = await manager.spawn_agent(grandchild_spec, parent_id=child.instance_id)
        await manager.mark_running(grandchild.instance_id)

        # Terminate root — should cascade to child and grandchild
        await manager.terminate_agent(root.instance_id, reason="explicit_termination")

        root_fetched = await registry.get(root.instance_id)
        child_fetched = await registry.get(child.instance_id)
        grandchild_fetched = await registry.get(grandchild.instance_id)

        assert root_fetched.is_terminal
        assert child_fetched.is_terminal
        assert grandchild_fetched.is_terminal

        # Children should have PARENT_TERMINATED reason
        assert child_fetched.state.termination_reason == SdkTerminationReason.PARENT_TERMINATED
        assert grandchild_fetched.state.termination_reason == SdkTerminationReason.PARENT_TERMINATED

    async def test_terminate_with_explicit_reason(self) -> None:
        """Termination reason should be propagated to the terminated instance."""
        manager, factory, registry = _make_lifecycle_manager()
        spec = _make_local_spec(spec_id="spec-explicit", name="explicit")
        instance = await manager.spawn_agent(spec)
        await manager.mark_running(instance.instance_id)

        await manager.terminate_agent(instance.instance_id, reason="explicit_termination")

        fetched = await registry.get(instance.instance_id)
        assert fetched.state.termination_reason == SdkTerminationReason.EXPLICIT_TERMINATION

    async def test_terminate_with_timeout_reason(self) -> None:
        """Termination with 'timeout' reason should use TerminationReason.TIMEOUT."""
        manager, factory, registry = _make_lifecycle_manager()
        spec = _make_local_spec(spec_id="spec-timeout", name="timeout")
        instance = await manager.spawn_agent(spec)
        await manager.mark_running(instance.instance_id)

        await manager.terminate_agent(instance.instance_id, reason="timeout")

        fetched = await registry.get(instance.instance_id)
        assert fetched.state.termination_reason == SdkTerminationReason.TIMEOUT

    async def test_terminate_with_unknown_reason_falls_back(self) -> None:
        """An unknown reason string should fall back to EXPLICIT_TERMINATION."""
        manager, factory, registry = _make_lifecycle_manager()
        spec = _make_local_spec(spec_id="spec-unknown", name="unknown")
        instance = await manager.spawn_agent(spec)
        await manager.mark_running(instance.instance_id)

        await manager.terminate_agent(instance.instance_id, reason="some_unknown_reason")

        fetched = await registry.get(instance.instance_id)
        assert fetched.state.termination_reason == SdkTerminationReason.EXPLICIT_TERMINATION


# ---------------------------------------------------------------------------
# Test: mark_running transitions agent state
# ---------------------------------------------------------------------------


class TestMarkRunning:
    """mark_running should transition an agent from Pending to Running."""

    async def test_pending_to_running(self) -> None:
        """A newly spawned (Pending) agent can transition to Running."""
        manager, factory, registry = _make_lifecycle_manager()
        spec = _make_local_spec(spec_id="spec-run", name="run-agent")
        instance = await manager.spawn_agent(spec)

        assert instance.state.tag == _StateTag.PENDING

        await manager.mark_running(instance.instance_id)

        fetched = await registry.get(instance.instance_id)
        assert fetched.state.tag == _StateTag.RUNNING

    async def test_running_to_running_raises(self) -> None:
        """Transitioning Running -> Running should raise (invalid transition)."""
        from kaizen.l3.factory.instance import InvalidStateTransitionError

        manager, factory, registry = _make_lifecycle_manager()
        spec = _make_local_spec(spec_id="spec-double-run", name="double-run")
        instance = await manager.spawn_agent(spec)
        await manager.mark_running(instance.instance_id)

        with pytest.raises(InvalidStateTransitionError):
            await manager.mark_running(instance.instance_id)


# ---------------------------------------------------------------------------
# Test: mark_completed transitions with result
# ---------------------------------------------------------------------------


class TestMarkCompleted:
    """mark_completed should transition a Running agent to Completed with result."""

    async def test_running_to_completed(self) -> None:
        """A Running agent can transition to Completed."""
        manager, factory, registry = _make_lifecycle_manager()
        spec = _make_local_spec(spec_id="spec-complete", name="complete-agent")
        instance = await manager.spawn_agent(spec)
        await manager.mark_running(instance.instance_id)

        await manager.mark_completed(instance.instance_id, result={"status": "done"})

        fetched = await registry.get(instance.instance_id)
        assert fetched.state.tag == _StateTag.COMPLETED
        assert fetched.state.result == {"status": "done"}
        assert fetched.is_terminal

    async def test_completed_with_none_result(self) -> None:
        """Completing without a result should still work."""
        manager, factory, registry = _make_lifecycle_manager()
        spec = _make_local_spec(spec_id="spec-none-result", name="none-result")
        instance = await manager.spawn_agent(spec)
        await manager.mark_running(instance.instance_id)

        await manager.mark_completed(instance.instance_id)

        fetched = await registry.get(instance.instance_id)
        assert fetched.state.tag == _StateTag.COMPLETED
        assert fetched.is_terminal

    async def test_pending_to_completed_raises(self) -> None:
        """Transitioning Pending -> Completed should raise (invalid transition)."""
        from kaizen.l3.factory.instance import InvalidStateTransitionError

        manager, factory, registry = _make_lifecycle_manager()
        spec = _make_local_spec(spec_id="spec-bad-complete", name="bad-complete")
        instance = await manager.spawn_agent(spec)

        with pytest.raises(InvalidStateTransitionError):
            await manager.mark_completed(instance.instance_id)


# ---------------------------------------------------------------------------
# Test: get_children returns spawned children
# ---------------------------------------------------------------------------


class TestGetChildren:
    """get_children should return direct children of a parent."""

    async def test_no_children(self) -> None:
        """A parent with no children should return empty list."""
        manager, factory, registry = _make_lifecycle_manager()
        spec = _make_local_spec(spec_id="spec-lonely", name="lonely")
        instance = await manager.spawn_agent(spec)

        children = await manager.get_children(instance.instance_id)
        assert children == []

    async def test_returns_direct_children_only(self) -> None:
        """get_children should return only direct children, not grandchildren."""
        manager, factory, registry = _make_lifecycle_manager()

        root_spec = _make_local_spec(spec_id="spec-root", name="root")
        root = await manager.spawn_agent(root_spec)
        await manager.mark_running(root.instance_id)

        child_spec = _make_local_spec(spec_id="spec-child", name="child")
        child = await manager.spawn_agent(child_spec, parent_id=root.instance_id)
        await manager.mark_running(child.instance_id)

        grandchild_spec = _make_local_spec(spec_id="spec-gc", name="grandchild")
        await manager.spawn_agent(grandchild_spec, parent_id=child.instance_id)

        children = await manager.get_children(root.instance_id)
        assert len(children) == 1
        assert children[0].instance_id == child.instance_id


# ---------------------------------------------------------------------------
# Test: get_lineage returns ancestry path
# ---------------------------------------------------------------------------


class TestGetLineage:
    """get_lineage should return root-to-instance ancestry path."""

    async def test_root_lineage(self) -> None:
        """A root agent's lineage should contain only itself."""
        manager, factory, registry = _make_lifecycle_manager()
        spec = _make_local_spec(spec_id="spec-root", name="root")
        root = await manager.spawn_agent(spec)

        lineage = await manager.get_lineage(root.instance_id)
        assert lineage == [root.instance_id]

    async def test_three_level_lineage(self) -> None:
        """A grandchild's lineage should be [root, child, grandchild]."""
        manager, factory, registry = _make_lifecycle_manager()

        root_spec = _make_local_spec(spec_id="spec-root", name="root")
        root = await manager.spawn_agent(root_spec)
        await manager.mark_running(root.instance_id)

        child_spec = _make_local_spec(spec_id="spec-child", name="child")
        child = await manager.spawn_agent(child_spec, parent_id=root.instance_id)
        await manager.mark_running(child.instance_id)

        grandchild_spec = _make_local_spec(spec_id="spec-gc", name="grandchild")
        grandchild = await manager.spawn_agent(grandchild_spec, parent_id=child.instance_id)

        lineage = await manager.get_lineage(grandchild.instance_id)
        assert lineage == [root.instance_id, child.instance_id, grandchild.instance_id]


# ---------------------------------------------------------------------------
# Test: Local AgentSpec -> SDK AgentSpec conversion
# ---------------------------------------------------------------------------


class TestSpecConversion:
    """_convert_spec should produce a valid SDK AgentSpec from a local one."""

    async def test_basic_fields_mapped(self) -> None:
        """Core fields (spec_id, name, description, capabilities, tool_ids) should map."""
        manager, _, _ = _make_lifecycle_manager()
        local = _make_local_spec(
            spec_id="spec-conv",
            name="converter",
            capabilities=["search", "analyze"],
            tool_ids=["tool-a", "tool-b"],
        )

        sdk_spec = manager._convert_spec(local)

        assert isinstance(sdk_spec, SdkAgentSpec)
        assert sdk_spec.spec_id == "spec-conv"
        assert sdk_spec.name == "converter"
        assert sdk_spec.description == "Agent: converter"
        assert sdk_spec.capabilities == ["search", "analyze"]
        assert sdk_spec.tool_ids == ["tool-a", "tool-b"]

    async def test_envelope_converted_to_dict(self) -> None:
        """ConstraintEnvelope should be serialized to a plain dict."""
        manager, _, _ = _make_lifecycle_manager()
        envelope = make_envelope(
            financial={"limit": 50.0},
            operational={"allowed": ["search"], "blocked": ["delete"]},
        )
        local = _make_local_spec(spec_id="spec-env", name="env-agent", envelope=envelope)

        sdk_spec = manager._convert_spec(local)

        assert isinstance(sdk_spec.envelope, dict)
        assert sdk_spec.envelope["financial"]["max_spend_usd"] == 50.0
        assert sdk_spec.envelope["operational"]["allowed_actions"] == ["search"]
        assert sdk_spec.envelope["operational"]["blocked_actions"] == ["delete"]

    async def test_memory_config_converted_to_dict(self) -> None:
        """MemoryConfig should be serialized to a plain dict with session/shared/persistent keys."""
        manager, _, _ = _make_lifecycle_manager()
        mem = MemoryConfig(session=True, shared=True, persistent=False)
        local = _make_local_spec(spec_id="spec-mem", name="mem-agent", memory_config=mem)

        sdk_spec = manager._convert_spec(local)

        assert isinstance(sdk_spec.memory_config, dict)
        assert sdk_spec.memory_config["session"] is True
        assert sdk_spec.memory_config["shared"] is True
        assert sdk_spec.memory_config["persistent"] is False

    async def test_timedelta_max_lifetime_converted_to_seconds(self) -> None:
        """timedelta max_lifetime should be converted to float seconds."""
        manager, _, _ = _make_lifecycle_manager()
        local = _make_local_spec(
            spec_id="spec-lifetime",
            name="lifetime-agent",
            max_lifetime=timedelta(hours=2),
        )

        sdk_spec = manager._convert_spec(local)

        assert sdk_spec.max_lifetime == 7200.0

    async def test_none_max_lifetime_stays_none(self) -> None:
        """None max_lifetime should remain None."""
        manager, _, _ = _make_lifecycle_manager()
        local = _make_local_spec(spec_id="spec-no-lt", name="no-lt-agent", max_lifetime=None)

        sdk_spec = manager._convert_spec(local)

        assert sdk_spec.max_lifetime is None

    async def test_max_children_and_depth_mapped(self) -> None:
        """max_children and max_depth should map directly."""
        manager, _, _ = _make_lifecycle_manager()
        local = _make_local_spec(
            spec_id="spec-limits",
            name="limits-agent",
            max_children=5,
            max_depth=3,
        )

        sdk_spec = manager._convert_spec(local)

        assert sdk_spec.max_children == 5
        assert sdk_spec.max_depth == 3

    async def test_context_keys_mapped(self) -> None:
        """required_context_keys and produced_context_keys should map directly."""
        manager, _, _ = _make_lifecycle_manager()
        local = _make_local_spec(
            spec_id="spec-ctx",
            name="ctx-agent",
            required_context_keys=["input_data", "config"],
            produced_context_keys=["result", "metrics"],
        )

        sdk_spec = manager._convert_spec(local)

        assert sdk_spec.required_context_keys == ["input_data", "config"]
        assert sdk_spec.produced_context_keys == ["result", "metrics"]

    async def test_metadata_mapped(self) -> None:
        """metadata dict should map directly."""
        manager, _, _ = _make_lifecycle_manager()
        local = _make_local_spec(
            spec_id="spec-meta",
            name="meta-agent",
            metadata={"version": "1.0", "priority": 5},
        )

        sdk_spec = manager._convert_spec(local)

        assert sdk_spec.metadata == {"version": "1.0", "priority": 5}

    async def test_full_round_trip_spawn(self) -> None:
        """spawn_agent should use _convert_spec internally and produce a valid instance."""
        manager, _, registry = _make_lifecycle_manager()
        envelope = make_envelope(
            financial={"limit": 100.0},
            operational={"allowed": ["read", "write"], "blocked": []},
            temporal={"window_start": "08:00", "window_end": "18:00"},
            data_access={"ceiling": "confidential", "scopes": ["analytics"]},
            communication={"recipients": ["supervisor"], "channels": ["internal"]},
        )
        mem = MemoryConfig(session=True, shared=True, persistent=True)
        local = _make_local_spec(
            spec_id="spec-full",
            name="full-agent",
            capabilities=["research", "coding"],
            tool_ids=["search", "editor"],
            envelope=envelope,
            memory_config=mem,
            max_lifetime=timedelta(minutes=30),
            max_children=10,
            max_depth=5,
            required_context_keys=["task"],
            produced_context_keys=["output"],
            metadata={"domain": "testing"},
        )

        instance = await manager.spawn_agent(local)

        assert instance.spec_id == "spec-full"
        assert instance.parent_id is None

        # Verify it's in the registry
        fetched = await registry.get(instance.instance_id)
        assert fetched.instance_id == instance.instance_id
