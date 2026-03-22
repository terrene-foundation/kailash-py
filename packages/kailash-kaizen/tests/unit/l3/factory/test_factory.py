# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for M1-04: AgentFactory.

Covers:
- spawn() with no parent (root agent)
- spawn() with parent (child agent)
- spawn() preconditions: parent state, max_children, max_depth, tool subsetting
- Cascade termination (I-02): deepest-first, all descendants terminated
- Idempotent termination: already-terminal = no-op
- Spawn blocked during cascade termination (AD-L3-10)
- Required context keys validation
- Delegation to registry for state/lineage/descendants/count
"""

from __future__ import annotations

import asyncio

import pytest

from kaizen.l3.factory.errors import (
    InstanceNotFound,
    MaxChildrenExceeded,
    MaxDepthExceeded,
    ToolNotInParent,
)
from kaizen.l3.factory.factory import AgentFactory
from kaizen.l3.factory.instance import (
    AgentInstance,
    AgentLifecycleState,
    TerminationReason,
    WaitReason,
)
from kaizen.l3.factory.registry import AgentInstanceRegistry
from kaizen.l3.factory.spec import AgentSpec


def _make_spec(
    spec_id: str = "spec-a",
    tool_ids: list[str] | None = None,
    max_children: int | None = None,
    max_depth: int | None = None,
    required_context_keys: list[str] | None = None,
) -> AgentSpec:
    """Helper to create a test AgentSpec."""
    return AgentSpec(
        spec_id=spec_id,
        name=f"Agent {spec_id}",
        description=f"Test agent for {spec_id}",
        tool_ids=tool_ids or [],
        max_children=max_children,
        max_depth=max_depth,
        required_context_keys=required_context_keys or [],
    )


class TestFactorySpawnRoot:
    """spawn() with no parent — root agent creation."""

    @pytest.mark.asyncio
    async def test_spawn_root_agent(self):
        """Spawning without parent_id creates a root agent."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        spec = _make_spec("root-spec")
        instance = await factory.spawn(spec)
        assert instance.spec_id == "root-spec"
        assert instance.parent_id is None
        assert instance.state.name == "pending"
        assert instance.instance_id  # UUID generated

    @pytest.mark.asyncio
    async def test_spawn_root_registered_in_registry(self):
        """Spawned root is retrievable from registry."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        instance = await factory.spawn(_make_spec("root-spec"))
        found = await registry.get(instance.instance_id)
        assert found is instance

    @pytest.mark.asyncio
    async def test_spawn_root_increments_live_count(self):
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        assert await registry.count_live() == 0
        await factory.spawn(_make_spec())
        assert await registry.count_live() == 1


class TestFactorySpawnChild:
    """spawn() with parent_id — child agent creation."""

    @pytest.mark.asyncio
    async def test_spawn_child_with_running_parent(self):
        """Parent in Running state can spawn children."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        parent = await factory.spawn(_make_spec("parent-spec"))
        await registry.update_state(parent.instance_id, AgentLifecycleState.running())

        child_spec = _make_spec("child-spec")
        child = await factory.spawn(child_spec, parent_id=parent.instance_id)
        assert child.parent_id == parent.instance_id
        assert child.spec_id == "child-spec"

    @pytest.mark.asyncio
    async def test_spawn_child_with_waiting_parent(self):
        """Parent in Waiting state can spawn children."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        parent = await factory.spawn(_make_spec("parent-spec"))
        await registry.update_state(parent.instance_id, AgentLifecycleState.running())
        await registry.update_state(
            parent.instance_id,
            AgentLifecycleState.waiting(WaitReason.DELEGATION_RESPONSE),
        )
        child = await factory.spawn(
            _make_spec("child-spec"), parent_id=parent.instance_id
        )
        assert child.parent_id == parent.instance_id

    @pytest.mark.asyncio
    async def test_spawn_child_with_pending_parent_raises(self):
        """Parent in Pending state cannot spawn children."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        parent = await factory.spawn(_make_spec("parent-spec"))
        # Parent is Pending — cannot spawn children
        with pytest.raises(ValueError, match="[Rr]unning|[Ww]aiting"):
            await factory.spawn(_make_spec("child-spec"), parent_id=parent.instance_id)

    @pytest.mark.asyncio
    async def test_spawn_child_with_terminal_parent_raises(self):
        """Terminal parent cannot spawn children."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        parent = await factory.spawn(_make_spec("parent-spec"))
        await registry.update_state(parent.instance_id, AgentLifecycleState.running())
        await registry.update_state(parent.instance_id, AgentLifecycleState.completed())
        with pytest.raises(ValueError, match="[Rr]unning|[Ww]aiting"):
            await factory.spawn(_make_spec("child-spec"), parent_id=parent.instance_id)

    @pytest.mark.asyncio
    async def test_spawn_child_nonexistent_parent_raises(self):
        """Nonexistent parent raises InstanceNotFound."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        with pytest.raises(InstanceNotFound):
            await factory.spawn(_make_spec("child-spec"), parent_id="nonexistent")

    @pytest.mark.asyncio
    async def test_spawn_child_appears_in_children_of(self):
        """Spawned children appear in children_of query."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        parent = await factory.spawn(_make_spec("parent"))
        await registry.update_state(parent.instance_id, AgentLifecycleState.running())
        c1 = await factory.spawn(_make_spec("c1"), parent_id=parent.instance_id)
        c2 = await factory.spawn(_make_spec("c2"), parent_id=parent.instance_id)
        children = await factory.children_of(parent.instance_id)
        ids = {c.instance_id for c in children}
        assert ids == {c1.instance_id, c2.instance_id}


class TestFactoryMaxChildren:
    """max_children enforcement at spawn time."""

    @pytest.mark.asyncio
    async def test_max_children_exceeded_raises(self):
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        parent_spec = _make_spec("parent", max_children=2)
        parent = await factory.spawn(parent_spec)
        await registry.update_state(parent.instance_id, AgentLifecycleState.running())

        await factory.spawn(_make_spec("c1"), parent_id=parent.instance_id)
        await factory.spawn(_make_spec("c2"), parent_id=parent.instance_id)
        with pytest.raises(MaxChildrenExceeded) as exc_info:
            await factory.spawn(_make_spec("c3"), parent_id=parent.instance_id)
        assert exc_info.value.details["limit"] == 2
        assert exc_info.value.details["current"] == 2

    @pytest.mark.asyncio
    async def test_no_max_children_unlimited(self):
        """max_children=None means no limit."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        parent = await factory.spawn(_make_spec("parent", max_children=None))
        await registry.update_state(parent.instance_id, AgentLifecycleState.running())
        for i in range(10):
            await factory.spawn(_make_spec(f"c{i}"), parent_id=parent.instance_id)
        assert len(await factory.children_of(parent.instance_id)) == 10


class TestFactoryMaxDepth:
    """max_depth enforcement at spawn time."""

    @pytest.mark.asyncio
    async def test_max_depth_exceeded_raises(self):
        """If any ancestor has max_depth that would be violated, spawn fails."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        # Root with max_depth=1 — can have children but not grandchildren
        root = await factory.spawn(_make_spec("root", max_depth=1))
        await registry.update_state(root.instance_id, AgentLifecycleState.running())
        child = await factory.spawn(_make_spec("child"), parent_id=root.instance_id)
        await registry.update_state(child.instance_id, AgentLifecycleState.running())
        with pytest.raises(MaxDepthExceeded):
            await factory.spawn(_make_spec("grandchild"), parent_id=child.instance_id)

    @pytest.mark.asyncio
    async def test_max_depth_allows_within_limit(self):
        """max_depth=2 allows children and grandchildren."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        root = await factory.spawn(_make_spec("root", max_depth=2))
        await registry.update_state(root.instance_id, AgentLifecycleState.running())
        child = await factory.spawn(_make_spec("child"), parent_id=root.instance_id)
        await registry.update_state(child.instance_id, AgentLifecycleState.running())
        grandchild = await factory.spawn(
            _make_spec("grandchild"), parent_id=child.instance_id
        )
        assert grandchild.parent_id == child.instance_id

    @pytest.mark.asyncio
    async def test_max_depth_none_unlimited(self):
        """max_depth=None means no limit."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        parent = await factory.spawn(_make_spec("root", max_depth=None))
        await registry.update_state(parent.instance_id, AgentLifecycleState.running())
        current_parent_id = parent.instance_id
        for i in range(10):
            child = await factory.spawn(
                _make_spec(f"child-{i}"), parent_id=current_parent_id
            )
            await registry.update_state(
                child.instance_id, AgentLifecycleState.running()
            )
            current_parent_id = child.instance_id
        # 10 levels deep — should work
        lineage = await factory.lineage(current_parent_id)
        assert len(lineage) == 11  # root + 10 children

    @pytest.mark.asyncio
    async def test_max_depth_checked_against_all_ancestors(self):
        """Intermediate ancestor's max_depth also limits deeper descendants."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        root = await factory.spawn(_make_spec("root", max_depth=5))
        await registry.update_state(root.instance_id, AgentLifecycleState.running())

        # Intermediate node at depth 1 with max_depth=1
        child = await factory.spawn(
            _make_spec("child", max_depth=1), parent_id=root.instance_id
        )
        await registry.update_state(child.instance_id, AgentLifecycleState.running())

        # Grandchild at depth 2 (within root's limit of 5 but child allows max_depth=1)
        grandchild = await factory.spawn(
            _make_spec("grandchild"), parent_id=child.instance_id
        )
        await registry.update_state(
            grandchild.instance_id, AgentLifecycleState.running()
        )

        # Great-grandchild at depth 3 — violates child's max_depth=1
        with pytest.raises(MaxDepthExceeded):
            await factory.spawn(
                _make_spec("great-grandchild"), parent_id=grandchild.instance_id
            )


class TestFactoryToolSubset:
    """Tool ID subsetting at spawn time."""

    @pytest.mark.asyncio
    async def test_child_tools_subset_of_parent(self):
        """Child tool_ids must be a subset of parent's spec tool_ids."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        parent = await factory.spawn(
            _make_spec("parent", tool_ids=["tool-a", "tool-b", "tool-c"])
        )
        await registry.update_state(parent.instance_id, AgentLifecycleState.running())
        child = await factory.spawn(
            _make_spec("child", tool_ids=["tool-a", "tool-b"]),
            parent_id=parent.instance_id,
        )
        assert child.spec_id == "child"

    @pytest.mark.asyncio
    async def test_child_tool_not_in_parent_raises(self):
        """Child requesting a tool not in parent's spec is rejected."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        parent = await factory.spawn(
            _make_spec("parent", tool_ids=["tool-a", "tool-b"])
        )
        await registry.update_state(parent.instance_id, AgentLifecycleState.running())
        with pytest.raises(ToolNotInParent) as exc_info:
            await factory.spawn(
                _make_spec("child", tool_ids=["tool-a", "tool-x"]),
                parent_id=parent.instance_id,
            )
        assert exc_info.value.details["tool_id"] == "tool-x"

    @pytest.mark.asyncio
    async def test_child_empty_tools_always_valid(self):
        """Empty tool_ids is always a valid subset."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        parent = await factory.spawn(_make_spec("parent", tool_ids=["tool-a"]))
        await registry.update_state(parent.instance_id, AgentLifecycleState.running())
        child = await factory.spawn(
            _make_spec("child", tool_ids=[]),
            parent_id=parent.instance_id,
        )
        assert child.spec_id == "child"

    @pytest.mark.asyncio
    async def test_root_agent_any_tools_allowed(self):
        """Root agents (no parent) can have any tools."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        root = await factory.spawn(
            _make_spec("root", tool_ids=["any-tool", "another-tool"])
        )
        assert root.parent_id is None


class TestFactoryCascadeTermination:
    """Cascade termination (I-02): all descendants terminated deepest-first."""

    @pytest.mark.asyncio
    async def test_terminate_leaf_node(self):
        """Terminating a leaf with no children."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        root = await factory.spawn(_make_spec("root"))
        await registry.update_state(root.instance_id, AgentLifecycleState.running())
        await factory.terminate(
            root.instance_id, TerminationReason.EXPLICIT_TERMINATION
        )
        inst = await registry.get(root.instance_id)
        assert inst.is_terminal
        assert inst.state.termination_reason == TerminationReason.EXPLICIT_TERMINATION

    @pytest.mark.asyncio
    async def test_cascade_terminates_children(self):
        """Terminating a parent cascades to all children."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        root = await factory.spawn(_make_spec("root"))
        await registry.update_state(root.instance_id, AgentLifecycleState.running())

        c1 = await factory.spawn(_make_spec("c1"), parent_id=root.instance_id)
        await registry.update_state(c1.instance_id, AgentLifecycleState.running())

        c2 = await factory.spawn(_make_spec("c2"), parent_id=root.instance_id)
        await registry.update_state(c2.instance_id, AgentLifecycleState.running())

        await factory.terminate(root.instance_id, TerminationReason.TIMEOUT)

        for iid in [c1.instance_id, c2.instance_id]:
            inst = await registry.get(iid)
            assert inst.is_terminal
            assert inst.state.termination_reason == TerminationReason.PARENT_TERMINATED

    @pytest.mark.asyncio
    async def test_cascade_terminates_grandchildren(self):
        """Cascade termination is recursive — grandchildren also terminated."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        root = await factory.spawn(_make_spec("root"))
        await registry.update_state(root.instance_id, AgentLifecycleState.running())

        child = await factory.spawn(_make_spec("child"), parent_id=root.instance_id)
        await registry.update_state(child.instance_id, AgentLifecycleState.running())

        grandchild = await factory.spawn(
            _make_spec("grandchild"), parent_id=child.instance_id
        )
        await registry.update_state(
            grandchild.instance_id, AgentLifecycleState.running()
        )

        await factory.terminate(root.instance_id, TerminationReason.BUDGET_EXHAUSTED)

        gc_inst = await registry.get(grandchild.instance_id)
        assert gc_inst.is_terminal
        assert gc_inst.state.termination_reason == TerminationReason.PARENT_TERMINATED

        c_inst = await registry.get(child.instance_id)
        assert c_inst.is_terminal
        assert c_inst.state.termination_reason == TerminationReason.PARENT_TERMINATED

        r_inst = await registry.get(root.instance_id)
        assert r_inst.is_terminal
        assert r_inst.state.termination_reason == TerminationReason.BUDGET_EXHAUSTED

    @pytest.mark.asyncio
    async def test_idempotent_termination(self):
        """Terminating an already-terminated instance is a no-op."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        root = await factory.spawn(_make_spec("root"))
        await registry.update_state(root.instance_id, AgentLifecycleState.running())
        await factory.terminate(root.instance_id, TerminationReason.TIMEOUT)

        # Second termination should be a no-op, not raise
        await factory.terminate(
            root.instance_id, TerminationReason.EXPLICIT_TERMINATION
        )
        inst = await registry.get(root.instance_id)
        # Original reason preserved
        assert inst.state.termination_reason == TerminationReason.TIMEOUT

    @pytest.mark.asyncio
    async def test_terminate_nonexistent_raises(self):
        """Terminating a nonexistent instance raises InstanceNotFound."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        with pytest.raises(InstanceNotFound):
            await factory.terminate("nonexistent", TerminationReason.TIMEOUT)

    @pytest.mark.asyncio
    async def test_terminate_pending_instance(self):
        """Pending instances can be terminated (Pending -> Terminated is valid)."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        root = await factory.spawn(_make_spec("root"))
        # root is Pending
        await factory.terminate(
            root.instance_id, TerminationReason.EXPLICIT_TERMINATION
        )
        inst = await registry.get(root.instance_id)
        assert inst.is_terminal

    @pytest.mark.asyncio
    async def test_cascade_skips_already_terminal_descendants(self):
        """During cascade, already-terminal descendants are skipped."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        root = await factory.spawn(_make_spec("root"))
        await registry.update_state(root.instance_id, AgentLifecycleState.running())

        c1 = await factory.spawn(_make_spec("c1"), parent_id=root.instance_id)
        await registry.update_state(c1.instance_id, AgentLifecycleState.running())
        await registry.update_state(c1.instance_id, AgentLifecycleState.completed())

        c2 = await factory.spawn(_make_spec("c2"), parent_id=root.instance_id)
        await registry.update_state(c2.instance_id, AgentLifecycleState.running())

        # c1 is already Completed. cascade should skip it.
        await factory.terminate(root.instance_id, TerminationReason.TIMEOUT)
        c1_inst = await registry.get(c1.instance_id)
        assert c1_inst.state.name == "completed"  # unchanged

        c2_inst = await registry.get(c2.instance_id)
        assert c2_inst.state.termination_reason == TerminationReason.PARENT_TERMINATED


class TestFactorySpawnDuringTermination:
    """AD-L3-10: Spawn blocked during cascade termination."""

    @pytest.mark.asyncio
    async def test_spawn_blocked_during_cascade(self):
        """Cannot spawn children under an ancestor being terminated."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        root = await factory.spawn(_make_spec("root"))
        await registry.update_state(root.instance_id, AgentLifecycleState.running())

        child = await factory.spawn(_make_spec("child"), parent_id=root.instance_id)
        await registry.update_state(child.instance_id, AgentLifecycleState.running())

        # Terminate root — after this, spawning under root or child should fail
        await factory.terminate(root.instance_id, TerminationReason.TIMEOUT)

        # Both root and child are now terminal — spawn should fail
        with pytest.raises((ValueError, InstanceNotFound)):
            await factory.spawn(_make_spec("new-child"), parent_id=root.instance_id)


class TestFactoryDelegation:
    """Factory delegates to registry for read operations."""

    @pytest.mark.asyncio
    async def test_get_state(self):
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        inst = await factory.spawn(_make_spec("s"))
        state = await factory.get_state(inst.instance_id)
        assert state.name == "pending"

    @pytest.mark.asyncio
    async def test_lineage(self):
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        root = await factory.spawn(_make_spec("root"))
        await registry.update_state(root.instance_id, AgentLifecycleState.running())
        child = await factory.spawn(_make_spec("child"), parent_id=root.instance_id)
        lineage = await factory.lineage(child.instance_id)
        assert lineage == [root.instance_id, child.instance_id]

    @pytest.mark.asyncio
    async def test_all_descendants(self):
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        root = await factory.spawn(_make_spec("root"))
        await registry.update_state(root.instance_id, AgentLifecycleState.running())
        c1 = await factory.spawn(_make_spec("c1"), parent_id=root.instance_id)
        desc = await factory.all_descendants(root.instance_id)
        assert desc == [c1.instance_id]

    @pytest.mark.asyncio
    async def test_count_live(self):
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        await factory.spawn(_make_spec("a"))
        await factory.spawn(_make_spec("b"))
        assert await factory.count_live() == 2

    @pytest.mark.asyncio
    async def test_update_state(self):
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        inst = await factory.spawn(_make_spec("s"))
        await factory.update_state(inst.instance_id, AgentLifecycleState.running())
        state = await factory.get_state(inst.instance_id)
        assert state.name == "running"
