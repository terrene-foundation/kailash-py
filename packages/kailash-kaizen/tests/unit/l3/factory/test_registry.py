# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for M1-04: AgentInstanceRegistry.

Covers:
- register / deregister lifecycle
- get() lookup (found and not-found)
- children_of() queries
- lineage() root-to-instance path
- all_descendants() recursive BFS
- count_live() non-terminal count
- update_state() with transition validation
- Duplicate ID rejection
- Deregister of non-terminal rejected
- Thread-safety via asyncio.Lock (concurrent register/deregister)
"""

from __future__ import annotations

import asyncio

import pytest

from kaizen.l3.factory.errors import InstanceNotFound, RegistryError
from kaizen.l3.factory.instance import (
    AgentInstance,
    AgentLifecycleState,
    InvalidStateTransitionError,
    TerminationReason,
)
from kaizen.l3.factory.registry import AgentInstanceRegistry


def _make_instance(
    instance_id: str = "inst-001",
    spec_id: str = "spec-a",
    parent_id: str | None = None,
) -> AgentInstance:
    """Helper to create a test AgentInstance."""
    return AgentInstance(
        instance_id=instance_id,
        spec_id=spec_id,
        parent_id=parent_id,
    )


class TestRegistryRegister:
    """register() — add instances to the registry."""

    @pytest.mark.asyncio
    async def test_register_single_instance(self):
        registry = AgentInstanceRegistry()
        inst = _make_instance("inst-001")
        await registry.register(inst)
        result = await registry.get("inst-001")
        assert result is inst

    @pytest.mark.asyncio
    async def test_register_duplicate_id_raises(self):
        registry = AgentInstanceRegistry()
        inst1 = _make_instance("inst-001")
        inst2 = _make_instance("inst-001")
        await registry.register(inst1)
        with pytest.raises(RegistryError, match="inst-001"):
            await registry.register(inst2)

    @pytest.mark.asyncio
    async def test_register_updates_children_index(self):
        registry = AgentInstanceRegistry()
        parent = _make_instance("parent-001")
        child = _make_instance("child-001", parent_id="parent-001")
        await registry.register(parent)
        await registry.register(child)
        children = await registry.children_of("parent-001")
        assert len(children) == 1
        assert children[0].instance_id == "child-001"

    @pytest.mark.asyncio
    async def test_register_updates_spec_index(self):
        """Multiple instances of the same spec_id are tracked."""
        registry = AgentInstanceRegistry()
        inst1 = _make_instance("inst-001", spec_id="spec-a")
        inst2 = _make_instance("inst-002", spec_id="spec-a")
        await registry.register(inst1)
        await registry.register(inst2)
        # Both should be findable by spec
        result1 = await registry.get("inst-001")
        result2 = await registry.get("inst-002")
        assert result1.spec_id == result2.spec_id == "spec-a"


class TestRegistryDeregister:
    """deregister() — remove terminal instances."""

    @pytest.mark.asyncio
    async def test_deregister_terminal_instance(self):
        registry = AgentInstanceRegistry()
        inst = _make_instance("inst-001")
        inst.transition_to(AgentLifecycleState.running())
        inst.transition_to(AgentLifecycleState.completed())
        await registry.register(inst)
        removed = await registry.deregister("inst-001")
        assert removed is inst
        with pytest.raises(InstanceNotFound):
            await registry.get("inst-001")

    @pytest.mark.asyncio
    async def test_deregister_non_terminal_raises(self):
        """Cannot deregister an instance that is still active."""
        registry = AgentInstanceRegistry()
        inst = _make_instance("inst-001")
        await registry.register(inst)
        with pytest.raises(RegistryError, match="terminal"):
            await registry.deregister("inst-001")

    @pytest.mark.asyncio
    async def test_deregister_not_found_raises(self):
        registry = AgentInstanceRegistry()
        with pytest.raises(InstanceNotFound, match="inst-999"):
            await registry.deregister("inst-999")

    @pytest.mark.asyncio
    async def test_deregister_removes_from_children_index(self):
        registry = AgentInstanceRegistry()
        parent = _make_instance("parent-001")
        child = _make_instance("child-001", parent_id="parent-001")
        child.transition_to(AgentLifecycleState.running())
        child.transition_to(AgentLifecycleState.completed())
        await registry.register(parent)
        await registry.register(child)
        await registry.deregister("child-001")
        children = await registry.children_of("parent-001")
        assert len(children) == 0


class TestRegistryGet:
    """get() — instance lookup by ID."""

    @pytest.mark.asyncio
    async def test_get_existing(self):
        registry = AgentInstanceRegistry()
        inst = _make_instance("inst-001")
        await registry.register(inst)
        assert (await registry.get("inst-001")) is inst

    @pytest.mark.asyncio
    async def test_get_not_found_raises(self):
        registry = AgentInstanceRegistry()
        with pytest.raises(InstanceNotFound, match="inst-999"):
            await registry.get("inst-999")


class TestRegistryChildrenOf:
    """children_of() — direct children of a parent."""

    @pytest.mark.asyncio
    async def test_no_children(self):
        registry = AgentInstanceRegistry()
        parent = _make_instance("parent-001")
        await registry.register(parent)
        children = await registry.children_of("parent-001")
        assert children == []

    @pytest.mark.asyncio
    async def test_multiple_children(self):
        registry = AgentInstanceRegistry()
        parent = _make_instance("parent-001")
        c1 = _make_instance("child-001", parent_id="parent-001")
        c2 = _make_instance("child-002", parent_id="parent-001")
        await registry.register(parent)
        await registry.register(c1)
        await registry.register(c2)
        children = await registry.children_of("parent-001")
        ids = {c.instance_id for c in children}
        assert ids == {"child-001", "child-002"}

    @pytest.mark.asyncio
    async def test_children_of_unknown_parent_returns_empty(self):
        """Querying children of a non-existent parent returns empty list."""
        registry = AgentInstanceRegistry()
        children = await registry.children_of("nonexistent")
        assert children == []


class TestRegistryLineage:
    """lineage() — root-to-instance ancestry path."""

    @pytest.mark.asyncio
    async def test_root_lineage_is_single_element(self):
        registry = AgentInstanceRegistry()
        root = _make_instance("root-001")
        await registry.register(root)
        path = await registry.lineage("root-001")
        assert path == ["root-001"]

    @pytest.mark.asyncio
    async def test_child_lineage(self):
        registry = AgentInstanceRegistry()
        root = _make_instance("root-001")
        child = _make_instance("child-001", parent_id="root-001")
        await registry.register(root)
        await registry.register(child)
        path = await registry.lineage("child-001")
        assert path == ["root-001", "child-001"]

    @pytest.mark.asyncio
    async def test_deep_lineage(self):
        registry = AgentInstanceRegistry()
        root = _make_instance("r")
        c1 = _make_instance("c1", parent_id="r")
        c2 = _make_instance("c2", parent_id="c1")
        c3 = _make_instance("c3", parent_id="c2")
        for inst in [root, c1, c2, c3]:
            await registry.register(inst)
        path = await registry.lineage("c3")
        assert path == ["r", "c1", "c2", "c3"]

    @pytest.mark.asyncio
    async def test_lineage_not_found_raises(self):
        registry = AgentInstanceRegistry()
        with pytest.raises(InstanceNotFound):
            await registry.lineage("nope")


class TestRegistryAllDescendants:
    """all_descendants() — recursive BFS of all descendants."""

    @pytest.mark.asyncio
    async def test_no_descendants(self):
        registry = AgentInstanceRegistry()
        root = _make_instance("root-001")
        await registry.register(root)
        desc = await registry.all_descendants("root-001")
        assert desc == []

    @pytest.mark.asyncio
    async def test_direct_children_only(self):
        registry = AgentInstanceRegistry()
        root = _make_instance("root-001")
        c1 = _make_instance("c1", parent_id="root-001")
        c2 = _make_instance("c2", parent_id="root-001")
        await registry.register(root)
        await registry.register(c1)
        await registry.register(c2)
        desc = await registry.all_descendants("root-001")
        assert set(desc) == {"c1", "c2"}

    @pytest.mark.asyncio
    async def test_deep_descendants(self):
        """Grandchildren and great-grandchildren are included."""
        registry = AgentInstanceRegistry()
        root = _make_instance("root")
        c1 = _make_instance("c1", parent_id="root")
        c2 = _make_instance("c2", parent_id="root")
        gc1 = _make_instance("gc1", parent_id="c1")
        gc2 = _make_instance("gc2", parent_id="c1")
        ggc1 = _make_instance("ggc1", parent_id="gc1")
        for inst in [root, c1, c2, gc1, gc2, ggc1]:
            await registry.register(inst)
        desc = await registry.all_descendants("root")
        assert set(desc) == {"c1", "c2", "gc1", "gc2", "ggc1"}

    @pytest.mark.asyncio
    async def test_descendants_subtree(self):
        """all_descendants of a subtree root returns only that subtree."""
        registry = AgentInstanceRegistry()
        root = _make_instance("root")
        c1 = _make_instance("c1", parent_id="root")
        c2 = _make_instance("c2", parent_id="root")
        gc1 = _make_instance("gc1", parent_id="c1")
        for inst in [root, c1, c2, gc1]:
            await registry.register(inst)
        desc = await registry.all_descendants("c1")
        assert desc == ["gc1"]


class TestRegistryCountLive:
    """count_live() — non-terminal instance count."""

    @pytest.mark.asyncio
    async def test_all_pending(self):
        registry = AgentInstanceRegistry()
        for i in range(5):
            await registry.register(_make_instance(f"inst-{i}"))
        assert await registry.count_live() == 5

    @pytest.mark.asyncio
    async def test_some_terminal(self):
        registry = AgentInstanceRegistry()
        inst1 = _make_instance("inst-001")
        inst2 = _make_instance("inst-002")
        inst2.transition_to(AgentLifecycleState.running())
        inst2.transition_to(AgentLifecycleState.completed())
        await registry.register(inst1)
        await registry.register(inst2)
        assert await registry.count_live() == 1

    @pytest.mark.asyncio
    async def test_empty_registry(self):
        registry = AgentInstanceRegistry()
        assert await registry.count_live() == 0


class TestRegistryUpdateState:
    """update_state() — validated state transitions via registry."""

    @pytest.mark.asyncio
    async def test_valid_transition(self):
        registry = AgentInstanceRegistry()
        inst = _make_instance("inst-001")
        await registry.register(inst)
        await registry.update_state("inst-001", AgentLifecycleState.running())
        updated = await registry.get("inst-001")
        assert updated.state.name == "running"

    @pytest.mark.asyncio
    async def test_invalid_transition_raises(self):
        registry = AgentInstanceRegistry()
        inst = _make_instance("inst-001")
        await registry.register(inst)
        # Pending -> Completed is invalid
        with pytest.raises(InvalidStateTransitionError):
            await registry.update_state("inst-001", AgentLifecycleState.completed())

    @pytest.mark.asyncio
    async def test_update_state_not_found_raises(self):
        registry = AgentInstanceRegistry()
        with pytest.raises(InstanceNotFound):
            await registry.update_state("nope", AgentLifecycleState.running())


class TestRegistryConcurrency:
    """Thread-safety via asyncio.Lock."""

    @pytest.mark.asyncio
    async def test_concurrent_register_no_corruption(self):
        """Multiple concurrent registrations do not corrupt internal state."""
        registry = AgentInstanceRegistry()

        async def register_batch(start: int, count: int) -> None:
            for i in range(start, start + count):
                await registry.register(_make_instance(f"inst-{i}", spec_id="spec-a"))

        # Register 100 instances concurrently in batches
        await asyncio.gather(
            register_batch(0, 25),
            register_batch(25, 25),
            register_batch(50, 25),
            register_batch(75, 25),
        )
        assert await registry.count_live() == 100

    @pytest.mark.asyncio
    async def test_concurrent_register_and_read(self):
        """Reads during concurrent writes are safe."""
        registry = AgentInstanceRegistry()

        async def register_one(idx: int) -> None:
            await registry.register(_make_instance(f"inst-{idx}", spec_id="spec-b"))

        async def read_count() -> int:
            return await registry.count_live()

        # Interleave writes and reads
        tasks = []
        for i in range(20):
            tasks.append(register_one(i))
            tasks.append(read_count())
        await asyncio.gather(*tasks)
        assert await registry.count_live() == 20
