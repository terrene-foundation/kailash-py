"""
Tests for TrustExecutionContext - Trust state propagation through workflows.

Test Intent:
- Verify trust contexts can only delegate capabilities they hold (no privilege escalation)
- Verify constraints can only be tightened, never loosened (security by design)
- Verify delegation chains maintain complete audit trail
- Verify parallel context merging preserves security guarantees
"""

from datetime import datetime

import pytest
from kaizen.trust.orchestration.exceptions import (
    ConstraintLooseningError,
    ContextPropagationError,
    DelegationChainError,
)
from kaizen.trust.orchestration.execution_context import (
    ContextMergeStrategy,
    DelegationEntry,
    TrustExecutionContext,
)


class TestTrustExecutionContextCreation:
    """Test context creation and initialization."""

    def test_create_context_with_capabilities(self):
        """Context should be created with specified capabilities."""
        context = TrustExecutionContext.create(
            parent_agent_id="supervisor-001",
            task_id="task-001",
            delegated_capabilities=["read_data", "analyze_data"],
        )

        assert context.parent_agent_id == "supervisor-001"
        assert context.current_agent_id == "supervisor-001"  # Initially same
        assert context.task_id == "task-001"
        assert context.has_capability("read_data")
        assert context.has_capability("analyze_data")
        assert not context.has_capability("write_data")

    def test_create_context_with_constraints(self):
        """Context should carry inherited constraints."""
        context = TrustExecutionContext.create(
            parent_agent_id="supervisor-001",
            task_id="task-001",
            delegated_capabilities=["read_data"],
            inherited_constraints={
                "max_records": 1000,
                "allowed_tables": ["users", "orders"],
            },
        )

        assert context.get_constraint("max_records") == 1000
        assert context.get_constraint("allowed_tables") == ["users", "orders"]
        assert context.get_constraint("nonexistent", "default") == "default"

    def test_create_context_generates_unique_id(self):
        """Each context should have a unique identifier."""
        ctx1 = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=[],
        )
        ctx2 = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=[],
        )

        assert ctx1.context_id != ctx2.context_id

    def test_context_starts_with_empty_delegation_chain(self):
        """New contexts should have empty delegation chains."""
        context = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["cap1"],
        )

        assert len(context.delegation_chain) == 0
        assert context.get_chain_length() == 0


class TestCapabilityChecks:
    """Test capability verification methods."""

    def test_has_capability_returns_true_for_delegated(self):
        """has_capability should return True for capabilities the context holds."""
        context = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read", "write", "delete"],
        )

        assert context.has_capability("read") is True
        assert context.has_capability("write") is True
        assert context.has_capability("delete") is True

    def test_has_capability_returns_false_for_missing(self):
        """has_capability should return False for capabilities not held."""
        context = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read"],
        )

        assert context.has_capability("write") is False
        assert context.has_capability("admin") is False

    def test_has_all_capabilities_checks_multiple(self):
        """has_all_capabilities should verify all specified capabilities exist."""
        context = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read", "write", "analyze"],
        )

        assert context.has_all_capabilities(["read", "write"]) is True
        assert context.has_all_capabilities(["read", "admin"]) is False
        assert context.has_all_capabilities([]) is True  # Empty list


class TestContextPropagation:
    """Test trust context propagation to child agents."""

    def test_propagate_to_child_with_subset_capabilities(self):
        """Child can receive subset of parent's capabilities."""
        parent_context = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="parent-task",
            delegated_capabilities=["read", "write", "delete"],
        )

        child_context = parent_context.propagate_to_child(
            child_agent_id="worker-001",
            task_id="child-task",
            capabilities=["read", "write"],
        )

        assert child_context.current_agent_id == "worker-001"
        assert child_context.parent_agent_id == "supervisor"
        assert child_context.has_capability("read")
        assert child_context.has_capability("write")
        assert not child_context.has_capability("delete")  # Not delegated

    def test_propagate_fails_for_undelegated_capabilities(self):
        """Cannot delegate capabilities the parent doesn't hold."""
        parent_context = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="parent-task",
            delegated_capabilities=["read"],
        )

        with pytest.raises(ContextPropagationError) as exc_info:
            parent_context.propagate_to_child(
                child_agent_id="worker",
                task_id="child-task",
                capabilities=["read", "admin"],  # admin not held
            )

        assert "Cannot delegate capabilities not held" in str(exc_info.value)
        assert "admin" in str(exc_info.value)

    def test_propagate_without_explicit_capabilities_inherits_all(self):
        """Without explicit capabilities, child inherits all parent capabilities."""
        parent_context = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="parent-task",
            delegated_capabilities=["read", "write"],
        )

        child_context = parent_context.propagate_to_child(
            child_agent_id="worker",
            task_id="child-task",
        )

        assert child_context.has_capability("read")
        assert child_context.has_capability("write")

    def test_propagate_adds_delegation_entry(self):
        """Propagation should add entry to delegation chain."""
        parent_context = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="parent-task",
            delegated_capabilities=["read"],
        )

        child_context = parent_context.propagate_to_child(
            child_agent_id="worker",
            task_id="child-task",
            capabilities=["read"],
        )

        assert len(child_context.delegation_chain) == 1
        entry = child_context.delegation_chain[0]
        assert entry.delegator_id == "supervisor"
        assert entry.delegatee_id == "worker"
        assert entry.task_id == "child-task"


class TestConstraintTightening:
    """Test that constraints can only be tightened, never loosened."""

    def test_numeric_constraint_can_be_tightened(self):
        """Numeric limits can be reduced (tightened)."""
        parent_context = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read"],
            inherited_constraints={"max_records": 1000},
        )

        child_context = parent_context.propagate_to_child(
            child_agent_id="worker",
            task_id="child-task",
            additional_constraints={"max_records": 500},
        )

        assert child_context.get_constraint("max_records") == 500

    def test_numeric_constraint_cannot_be_loosened(self):
        """Cannot increase numeric limits (would loosen constraint)."""
        parent_context = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read"],
            inherited_constraints={"max_records": 1000},
        )

        with pytest.raises(ConstraintLooseningError) as exc_info:
            parent_context.propagate_to_child(
                child_agent_id="worker",
                task_id="child-task",
                additional_constraints={"max_records": 2000},  # Loosening!
            )

        assert "Cannot loosen" in str(exc_info.value)
        assert "max_records" in str(exc_info.value)

    def test_list_constraint_can_be_subset(self):
        """List constraints can be reduced to subsets."""
        parent_context = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read"],
            inherited_constraints={"allowed_tables": ["users", "orders", "products"]},
        )

        child_context = parent_context.propagate_to_child(
            child_agent_id="worker",
            task_id="child-task",
            additional_constraints={"allowed_tables": ["users", "orders"]},
        )

        allowed = child_context.get_constraint("allowed_tables")
        assert set(allowed) == {"users", "orders"}

    def test_list_constraint_cannot_add_elements(self):
        """Cannot add elements to list constraints (would loosen)."""
        parent_context = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read"],
            inherited_constraints={"allowed_tables": ["users", "orders"]},
        )

        with pytest.raises(ConstraintLooseningError) as exc_info:
            parent_context.propagate_to_child(
                child_agent_id="worker",
                task_id="child-task",
                additional_constraints={"allowed_tables": ["users", "orders", "admin"]},
            )

        assert "admin" in str(exc_info.value)

    def test_boolean_constraint_can_tighten_to_false(self):
        """Boolean True can be tightened to False."""
        parent_context = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read"],
            inherited_constraints={"allow_exports": True},
        )

        child_context = parent_context.propagate_to_child(
            child_agent_id="worker",
            task_id="child-task",
            additional_constraints={"allow_exports": False},
        )

        assert child_context.get_constraint("allow_exports") is False

    def test_boolean_constraint_cannot_loosen_from_false(self):
        """Cannot change False to True (would loosen constraint)."""
        parent_context = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read"],
            inherited_constraints={"allow_exports": False},
        )

        with pytest.raises(ConstraintLooseningError) as exc_info:
            parent_context.propagate_to_child(
                child_agent_id="worker",
                task_id="child-task",
                additional_constraints={"allow_exports": True},
            )

        assert "allow_exports" in str(exc_info.value)

    def test_new_constraints_can_be_added(self):
        """New constraints not present in parent can be added."""
        parent_context = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read"],
            inherited_constraints={"max_records": 1000},
        )

        child_context = parent_context.propagate_to_child(
            child_agent_id="worker",
            task_id="child-task",
            additional_constraints={"timeout_seconds": 30},
        )

        assert child_context.get_constraint("max_records") == 1000
        assert child_context.get_constraint("timeout_seconds") == 30


class TestDelegationChain:
    """Test delegation chain tracking and traversal."""

    def test_multi_level_delegation_chain(self):
        """Delegation chain should track all levels of delegation."""
        # Level 0: Root supervisor
        root = TrustExecutionContext.create(
            parent_agent_id="root-supervisor",
            task_id="main-task",
            delegated_capabilities=["read", "write", "delete"],
        )

        # Level 1: Team lead
        team_lead = root.propagate_to_child(
            child_agent_id="team-lead",
            task_id="subtask-1",
            capabilities=["read", "write"],
        )

        # Level 2: Worker
        worker = team_lead.propagate_to_child(
            child_agent_id="worker",
            task_id="subtask-2",
            capabilities=["read"],
        )

        assert worker.get_chain_length() == 2
        path = worker.get_delegation_path()
        assert path == ["root-supervisor", "team-lead", "worker"]

    def test_find_root_delegator(self):
        """Should be able to find original delegator."""
        root = TrustExecutionContext.create(
            parent_agent_id="root",
            task_id="task",
            delegated_capabilities=["read"],
        )
        child = root.propagate_to_child(
            child_agent_id="child",
            task_id="subtask",
        )
        grandchild = child.propagate_to_child(
            child_agent_id="grandchild",
            task_id="subsubtask",
        )

        assert grandchild.find_root_delegator() == "root"

    def test_root_context_returns_parent_as_root(self):
        """Root context should return its parent_agent_id as root."""
        root = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read"],
        )

        assert root.find_root_delegator() == "supervisor"
        assert root.get_delegation_path() == ["supervisor"]


class TestParallelContextMerging:
    """Test merging contexts from parallel execution branches."""

    def test_merge_with_intersection_strategy(self):
        """INTERSECTION strategy takes common capabilities only."""
        ctx1 = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read", "write", "analyze"],
        )
        ctx2 = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read", "delete"],
        )

        merged = TrustExecutionContext.merge_parallel_contexts(
            [ctx1, ctx2],
            strategy=ContextMergeStrategy.INTERSECTION,
        )

        assert merged.has_capability("read")
        assert not merged.has_capability("write")
        assert not merged.has_capability("analyze")
        assert not merged.has_capability("delete")

    def test_merge_with_union_strategy(self):
        """UNION strategy combines all capabilities."""
        ctx1 = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read", "write"],
        )
        ctx2 = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read", "delete"],
        )

        merged = TrustExecutionContext.merge_parallel_contexts(
            [ctx1, ctx2],
            strategy=ContextMergeStrategy.UNION,
        )

        assert merged.has_capability("read")
        assert merged.has_capability("write")
        assert merged.has_capability("delete")

    def test_merge_takes_most_restrictive_constraints(self):
        """Merged constraints should be most restrictive from all sources."""
        ctx1 = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read"],
            inherited_constraints={"max_records": 1000},
        )
        ctx2 = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read"],
            inherited_constraints={"max_records": 500},
        )

        merged = TrustExecutionContext.merge_parallel_contexts([ctx1, ctx2])

        assert merged.get_constraint("max_records") == 500  # More restrictive

    def test_merge_empty_list_raises_error(self):
        """Cannot merge empty context list."""
        with pytest.raises(DelegationChainError) as exc_info:
            TrustExecutionContext.merge_parallel_contexts([])

        assert "empty" in str(exc_info.value).lower()

    def test_merge_single_context_returns_same(self):
        """Merging single context returns it unchanged."""
        ctx = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read"],
        )

        merged = TrustExecutionContext.merge_parallel_contexts([ctx])

        assert merged is ctx

    def test_first_wins_strategy(self):
        """FIRST_WINS strategy returns first context."""
        ctx1 = TrustExecutionContext.create(
            parent_agent_id="supervisor-1",
            task_id="task-1",
            delegated_capabilities=["read"],
        )
        ctx2 = TrustExecutionContext.create(
            parent_agent_id="supervisor-2",
            task_id="task-2",
            delegated_capabilities=["write"],
        )

        merged = TrustExecutionContext.merge_parallel_contexts(
            [ctx1, ctx2],
            strategy=ContextMergeStrategy.FIRST_WINS,
        )

        assert merged is ctx1


class TestSerialization:
    """Test context serialization and deserialization."""

    def test_to_dict_and_from_dict_roundtrip(self):
        """Context should survive serialization roundtrip."""
        original = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task-001",
            delegated_capabilities=["read", "write"],
            inherited_constraints={"max_records": 500},
            metadata={"source": "test"},
        )

        data = original.to_dict()
        restored = TrustExecutionContext.from_dict(data)

        assert restored.context_id == original.context_id
        assert restored.parent_agent_id == original.parent_agent_id
        assert restored.task_id == original.task_id
        assert restored.delegated_capabilities == original.delegated_capabilities
        assert restored.inherited_constraints == original.inherited_constraints
        assert restored.metadata == original.metadata

    def test_to_json_and_from_json_roundtrip(self):
        """Context should survive JSON serialization roundtrip."""
        original = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task-001",
            delegated_capabilities=["analyze"],
            inherited_constraints={"timeout": 30},
        )

        json_str = original.to_json()
        restored = TrustExecutionContext.from_json(json_str)

        assert restored.context_id == original.context_id
        assert restored.has_capability("analyze")

    def test_delegation_chain_survives_serialization(self):
        """Delegation chain should be preserved in serialization."""
        root = TrustExecutionContext.create(
            parent_agent_id="root",
            task_id="task",
            delegated_capabilities=["read"],
        )
        child = root.propagate_to_child(
            child_agent_id="child",
            task_id="subtask",
        )

        data = child.to_dict()
        restored = TrustExecutionContext.from_dict(data)

        assert len(restored.delegation_chain) == 1
        assert restored.delegation_chain[0].delegator_id == "root"
        assert restored.delegation_chain[0].delegatee_id == "child"


class TestContextHash:
    """Test context hashing for verification."""

    def test_identical_contexts_have_same_hash(self):
        """Contexts with same state should have same hash."""
        # Create two contexts with same data but different context_ids
        # Note: Hash includes context_id so truly identical contexts have same hash
        ctx = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read"],
        )

        hash1 = ctx.compute_hash()
        hash2 = ctx.compute_hash()

        assert hash1 == hash2

    def test_different_capabilities_have_different_hash(self):
        """Contexts with different capabilities should have different hashes."""
        ctx1 = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read"],
        )
        ctx2 = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read", "write"],
        )

        assert ctx1.compute_hash() != ctx2.compute_hash()

    def test_hash_is_deterministic(self):
        """Hash should be deterministic for same context."""
        ctx = TrustExecutionContext.create(
            parent_agent_id="supervisor",
            task_id="task",
            delegated_capabilities=["read", "write"],
            inherited_constraints={"max": 100},
        )

        hashes = [ctx.compute_hash() for _ in range(10)]
        assert len(set(hashes)) == 1  # All same


class TestDelegationEntry:
    """Test DelegationEntry dataclass."""

    def test_delegation_entry_creation(self):
        """DelegationEntry should store all fields."""
        entry = DelegationEntry(
            delegator_id="supervisor",
            delegatee_id="worker",
            task_id="task-001",
            capabilities=["read", "write"],
            metadata={"reason": "task assignment"},
        )

        assert entry.delegator_id == "supervisor"
        assert entry.delegatee_id == "worker"
        assert entry.task_id == "task-001"
        assert entry.capabilities == ["read", "write"]
        assert entry.metadata["reason"] == "task assignment"
        assert isinstance(entry.timestamp, datetime)

    def test_delegation_entry_serialization(self):
        """DelegationEntry should serialize and deserialize."""
        original = DelegationEntry(
            delegator_id="supervisor",
            delegatee_id="worker",
            task_id="task-001",
            capabilities=["read"],
        )

        data = original.to_dict()
        restored = DelegationEntry.from_dict(data)

        assert restored.delegator_id == original.delegator_id
        assert restored.delegatee_id == original.delegatee_id
        assert restored.task_id == original.task_id
        assert restored.capabilities == original.capabilities
