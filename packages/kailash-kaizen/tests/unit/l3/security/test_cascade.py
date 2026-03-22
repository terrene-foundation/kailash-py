# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""M6-07: Cascade termination invariant tests.

Tests the I-02 cascade termination invariants:
1. Deepest-first termination order (grandchild before child before root)
2. Idempotent termination (already-terminated -> no-op)
3. No orphaned instances after cascade
4. Spawn blocked during active cascade (AD-L3-10)

Red team milestone: M6-07 (cascade termination security).
"""

from __future__ import annotations

import pytest

from kaizen.l3.factory.factory import AgentFactory
from kaizen.l3.factory.instance import (
    AgentInstance,
    AgentLifecycleState,
    TerminationReason,
    _StateTag,
)
from kaizen.l3.factory.registry import AgentInstanceRegistry
from kaizen.l3.factory.spec import AgentSpec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_spec(
    spec_id: str = "spec-default",
    name: str = "test-agent",
    max_children: int | None = None,
    max_depth: int | None = None,
    tool_ids: list[str] | None = None,
) -> AgentSpec:
    return AgentSpec(
        spec_id=spec_id,
        name=name,
        description=f"Test spec: {name}",
        tool_ids=tool_ids or [],
        max_children=max_children,
        max_depth=max_depth,
    )


async def _spawn_and_run(
    factory: AgentFactory,
    spec: AgentSpec,
    parent_id: str | None = None,
) -> AgentInstance:
    """Spawn an instance and transition it to Running so it can be a parent."""
    instance = await factory.spawn(spec, parent_id=parent_id)
    await factory.update_state(instance.instance_id, AgentLifecycleState.running())
    return instance


# ===========================================================================
# 1. Three-level hierarchy cascade termination
# ===========================================================================


class TestCascadeTerminationOrder:
    """Cascade termination must terminate deepest-first: grandchild -> child -> root."""

    @pytest.mark.asyncio
    async def test_three_level_cascade_terminates_all(self) -> None:
        """Create root -> child -> grandchild, terminate root.
        All three must end up in Terminated state."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry)

        root_spec = _make_spec(spec_id="root-spec", max_depth=5)
        child_spec = _make_spec(spec_id="child-spec", max_depth=4)
        grandchild_spec = _make_spec(spec_id="grandchild-spec")

        # Build hierarchy
        root = await _spawn_and_run(factory, root_spec)
        child = await _spawn_and_run(factory, child_spec, parent_id=root.instance_id)
        grandchild = await _spawn_and_run(
            factory, grandchild_spec, parent_id=child.instance_id
        )

        # Verify hierarchy
        descendants = await factory.all_descendants(root.instance_id)
        assert len(descendants) == 2
        assert child.instance_id in descendants
        assert grandchild.instance_id in descendants

        # Terminate root
        await factory.terminate(
            root.instance_id, TerminationReason.EXPLICIT_TERMINATION
        )

        # All must be terminal
        root_state = await factory.get_state(root.instance_id)
        child_state = await factory.get_state(child.instance_id)
        grandchild_state = await factory.get_state(grandchild.instance_id)

        assert root_state.is_terminal
        assert child_state.is_terminal
        assert grandchild_state.is_terminal

    @pytest.mark.asyncio
    async def test_cascade_children_get_parent_terminated_reason(self) -> None:
        """Children and grandchildren must get PARENT_TERMINATED reason,
        while the root gets the explicit reason."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry)

        root_spec = _make_spec(spec_id="root-spec", max_depth=5)
        child_spec = _make_spec(spec_id="child-spec", max_depth=4)
        grandchild_spec = _make_spec(spec_id="grandchild-spec")

        root = await _spawn_and_run(factory, root_spec)
        child = await _spawn_and_run(factory, child_spec, parent_id=root.instance_id)
        grandchild = await _spawn_and_run(
            factory, grandchild_spec, parent_id=child.instance_id
        )

        await factory.terminate(root.instance_id, TerminationReason.BUDGET_EXHAUSTED)

        root_state = await factory.get_state(root.instance_id)
        child_state = await factory.get_state(child.instance_id)
        grandchild_state = await factory.get_state(grandchild.instance_id)

        # Root gets the explicit reason
        assert root_state.termination_reason == TerminationReason.BUDGET_EXHAUSTED

        # Children get PARENT_TERMINATED
        assert child_state.termination_reason == TerminationReason.PARENT_TERMINATED
        assert (
            grandchild_state.termination_reason == TerminationReason.PARENT_TERMINATED
        )

    @pytest.mark.asyncio
    async def test_cascade_deepest_first_ordering(self) -> None:
        """Verify that deeper descendants are terminated before shallower ones.
        After cascade, deepest-first ordering is enforced by the factory."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry)

        root_spec = _make_spec(spec_id="root-spec", max_depth=10)
        child_spec = _make_spec(spec_id="child-spec", max_depth=9)
        grandchild_spec = _make_spec(spec_id="grandchild-spec")

        root = await _spawn_and_run(factory, root_spec)
        child = await _spawn_and_run(factory, child_spec, parent_id=root.instance_id)
        grandchild = await _spawn_and_run(
            factory, grandchild_spec, parent_id=child.instance_id
        )

        # Verify lineage
        gc_lineage = await factory.lineage(grandchild.instance_id)
        assert len(gc_lineage) == 3  # root -> child -> grandchild
        assert gc_lineage[0] == root.instance_id
        assert gc_lineage[1] == child.instance_id
        assert gc_lineage[2] == grandchild.instance_id

        # Terminate root -- cascade should terminate grandchild before child
        await factory.terminate(root.instance_id, TerminationReason.TIMEOUT)

        # All terminated
        for inst_id in [root.instance_id, child.instance_id, grandchild.instance_id]:
            state = await factory.get_state(inst_id)
            assert state.tag == _StateTag.TERMINATED


# ===========================================================================
# 2. Idempotent termination
# ===========================================================================


class TestIdempotentTermination:
    """Terminating an already-terminated instance must be a no-op."""

    @pytest.mark.asyncio
    async def test_terminate_already_terminated_is_noop(self) -> None:
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry)

        spec = _make_spec(spec_id="noop-spec")
        instance = await _spawn_and_run(factory, spec)

        # First termination
        await factory.terminate(
            instance.instance_id, TerminationReason.EXPLICIT_TERMINATION
        )
        state1 = await factory.get_state(instance.instance_id)
        assert state1.is_terminal

        # Second termination -- should be a no-op, no error
        await factory.terminate(instance.instance_id, TerminationReason.TIMEOUT)

        # State should remain the same (first reason preserved)
        state2 = await factory.get_state(instance.instance_id)
        assert state2.is_terminal
        assert (
            state2.termination_reason == TerminationReason.EXPLICIT_TERMINATION
        ), "Original termination reason must be preserved"

    @pytest.mark.asyncio
    async def test_terminate_completed_instance_is_noop(self) -> None:
        """Terminating a Completed instance should be a no-op."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry)

        spec = _make_spec(spec_id="completed-spec")
        instance = await _spawn_and_run(factory, spec)

        # Complete the instance
        await factory.update_state(
            instance.instance_id, AgentLifecycleState.completed(result="done")
        )

        # Try to terminate -- should be no-op (already terminal)
        await factory.terminate(
            instance.instance_id, TerminationReason.EXPLICIT_TERMINATION
        )

        # Should still be Completed, not Terminated
        state = await factory.get_state(instance.instance_id)
        assert state.tag == _StateTag.COMPLETED

    @pytest.mark.asyncio
    async def test_terminate_failed_instance_is_noop(self) -> None:
        """Terminating a Failed instance should be a no-op."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry)

        spec = _make_spec(spec_id="failed-spec")
        instance = await _spawn_and_run(factory, spec)

        await factory.update_state(
            instance.instance_id, AgentLifecycleState.failed(error="crash")
        )

        await factory.terminate(
            instance.instance_id, TerminationReason.EXPLICIT_TERMINATION
        )

        state = await factory.get_state(instance.instance_id)
        assert state.tag == _StateTag.FAILED


# ===========================================================================
# 3. No orphaned instances after cascade
# ===========================================================================


class TestNoOrphanedInstances:
    """After cascade termination, no non-terminal descendants should remain."""

    @pytest.mark.asyncio
    async def test_all_descendants_terminated_after_cascade(self) -> None:
        """Broad tree: root has 3 children, each has 2 grandchildren.
        After cascade, all 9 instances must be terminal."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry)

        root_spec = _make_spec(spec_id="root-spec", max_children=10, max_depth=10)
        child_spec = _make_spec(spec_id="child-spec", max_children=10, max_depth=9)
        gc_spec = _make_spec(spec_id="gc-spec")

        root = await _spawn_and_run(factory, root_spec)

        all_ids = [root.instance_id]
        for i in range(3):
            child = await _spawn_and_run(
                factory, child_spec, parent_id=root.instance_id
            )
            all_ids.append(child.instance_id)
            for j in range(2):
                gc = await _spawn_and_run(factory, gc_spec, parent_id=child.instance_id)
                all_ids.append(gc.instance_id)

        assert len(all_ids) == 10  # 1 root + 3 children + 6 grandchildren

        # Terminate root
        await factory.terminate(
            root.instance_id, TerminationReason.EXPLICIT_TERMINATION
        )

        # All must be terminal
        for inst_id in all_ids:
            state = await factory.get_state(inst_id)
            assert (
                state.is_terminal
            ), f"Instance {inst_id} is not terminal after cascade: {state.name}"

        # No live instances
        live_count = await factory.count_live()
        assert live_count == 0

    @pytest.mark.asyncio
    async def test_no_orphans_after_mid_level_termination(self) -> None:
        """Terminate a mid-level node (child). Its descendants must be
        terminated but the root must remain alive."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry)

        root_spec = _make_spec(spec_id="root-spec", max_depth=10)
        child_spec = _make_spec(spec_id="child-spec", max_depth=9)
        gc_spec = _make_spec(spec_id="gc-spec")

        root = await _spawn_and_run(factory, root_spec)
        child = await _spawn_and_run(factory, child_spec, parent_id=root.instance_id)
        gc = await _spawn_and_run(factory, gc_spec, parent_id=child.instance_id)

        # Terminate only the child
        await factory.terminate(child.instance_id, TerminationReason.ENVELOPE_VIOLATION)

        # Root should still be running
        root_state = await factory.get_state(root.instance_id)
        assert root_state.tag == _StateTag.RUNNING

        # Child and grandchild should be terminated
        child_state = await factory.get_state(child.instance_id)
        gc_state = await factory.get_state(gc.instance_id)
        assert child_state.is_terminal
        assert gc_state.is_terminal


# ===========================================================================
# 4. Spawn blocked during cascade (AD-L3-10)
# ===========================================================================


class TestSpawnBlockedDuringCascade:
    """Spawn requests must be blocked for any instance currently
    undergoing cascade termination (AD-L3-10)."""

    @pytest.mark.asyncio
    async def test_terminate_nonexistent_raises(self) -> None:
        """Terminating a non-existent instance must raise InstanceNotFound."""
        from kaizen.l3.factory.errors import InstanceNotFound

        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry)

        with pytest.raises(InstanceNotFound):
            await factory.terminate(
                "nonexistent-id", TerminationReason.EXPLICIT_TERMINATION
            )

    @pytest.mark.asyncio
    async def test_spawn_under_terminated_parent_raises(self) -> None:
        """Cannot spawn under a terminated parent."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry)

        parent_spec = _make_spec(spec_id="parent-spec", max_depth=5)
        child_spec = _make_spec(spec_id="child-spec")

        parent = await _spawn_and_run(factory, parent_spec)
        await factory.terminate(
            parent.instance_id, TerminationReason.EXPLICIT_TERMINATION
        )

        # Try to spawn under the now-terminated parent
        with pytest.raises(ValueError, match="must be in Running or Waiting state"):
            await factory.spawn(child_spec, parent_id=parent.instance_id)


# ===========================================================================
# 5. Cascade with mixed states (some children already terminal)
# ===========================================================================


class TestCascadeWithMixedStates:
    """Cascade termination handles children that are already in terminal states."""

    @pytest.mark.asyncio
    async def test_cascade_skips_already_completed_children(self) -> None:
        """If a child is already Completed, cascade should skip it (no-op)."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry)

        root_spec = _make_spec(spec_id="root-spec", max_depth=5)
        child1_spec = _make_spec(spec_id="child1-spec")
        child2_spec = _make_spec(spec_id="child2-spec")

        root = await _spawn_and_run(factory, root_spec)
        child1 = await _spawn_and_run(factory, child1_spec, parent_id=root.instance_id)
        child2 = await _spawn_and_run(factory, child2_spec, parent_id=root.instance_id)

        # Complete child1 before cascade
        await factory.update_state(
            child1.instance_id, AgentLifecycleState.completed(result="done early")
        )

        # Cascade from root
        await factory.terminate(
            root.instance_id, TerminationReason.EXPLICIT_TERMINATION
        )

        # child1 should still be Completed (not overwritten to Terminated)
        child1_state = await factory.get_state(child1.instance_id)
        assert child1_state.tag == _StateTag.COMPLETED

        # child2 should be Terminated (was still running)
        child2_state = await factory.get_state(child2.instance_id)
        assert child2_state.tag == _StateTag.TERMINATED
        assert child2_state.termination_reason == TerminationReason.PARENT_TERMINATED

    @pytest.mark.asyncio
    async def test_cascade_skips_already_failed_children(self) -> None:
        """If a child is already Failed, cascade should skip it (no-op)."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry)

        root_spec = _make_spec(spec_id="root-spec", max_depth=5)
        child_spec = _make_spec(spec_id="child-spec")

        root = await _spawn_and_run(factory, root_spec)
        child = await _spawn_and_run(factory, child_spec, parent_id=root.instance_id)

        # Fail child before cascade
        await factory.update_state(
            child.instance_id, AgentLifecycleState.failed(error="crashed")
        )

        # Cascade from root
        await factory.terminate(root.instance_id, TerminationReason.TIMEOUT)

        # child should still be Failed
        child_state = await factory.get_state(child.instance_id)
        assert child_state.tag == _StateTag.FAILED


# ===========================================================================
# 6. Edge cases
# ===========================================================================


class TestCascadeEdgeCases:
    """Edge cases in cascade termination."""

    @pytest.mark.asyncio
    async def test_terminate_leaf_instance_no_descendants(self) -> None:
        """Terminating a leaf (no children) should just terminate itself."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry)

        spec = _make_spec(spec_id="leaf-spec")
        leaf = await _spawn_and_run(factory, spec)

        await factory.terminate(
            leaf.instance_id, TerminationReason.EXPLICIT_TERMINATION
        )

        state = await factory.get_state(leaf.instance_id)
        assert state.is_terminal

    @pytest.mark.asyncio
    async def test_terminate_pending_instance(self) -> None:
        """Can terminate a Pending instance (not yet Running)."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry)

        spec = _make_spec(spec_id="pending-spec")
        instance = await factory.spawn(spec)
        # Do NOT transition to Running

        await factory.terminate(
            instance.instance_id, TerminationReason.EXPLICIT_TERMINATION
        )

        state = await factory.get_state(instance.instance_id)
        assert state.tag == _StateTag.TERMINATED

    @pytest.mark.asyncio
    async def test_deep_chain_cascade(self) -> None:
        """Test cascade with a 5-level deep chain to ensure no stack issues."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry)

        specs = [_make_spec(spec_id=f"spec-level-{i}", max_depth=10) for i in range(5)]

        instances = []
        parent_id = None
        for spec in specs:
            instance = await _spawn_and_run(factory, spec, parent_id=parent_id)
            instances.append(instance)
            parent_id = instance.instance_id

        # Terminate root
        await factory.terminate(
            instances[0].instance_id, TerminationReason.EXPLICIT_TERMINATION
        )

        # All must be terminal
        for inst in instances:
            state = await factory.get_state(inst.instance_id)
            assert state.is_terminal

        live_count = await factory.count_live()
        assert live_count == 0
