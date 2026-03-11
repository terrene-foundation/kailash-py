"""
E2E Integration Tests: Trust Chain Verification.

Test Intent:
- Verify trust chains are established correctly
- Test chain propagation through delegation hierarchy
- Validate capability attestation and constraint inheritance
- Ensure chain verification catches tampering

These tests use real EATP cryptographic operations - NO MOCKING.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from kaizen.trust import (
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    ConstraintLooseningError,
    ContextMergeStrategy,
    ContextPropagationError,
    DelegationEntry,
    GenesisRecord,
    OrganizationalAuthority,
    OrganizationalAuthorityRegistry,
    TrustExecutionContext,
    TrustLineageChain,
    TrustOperations,
    VerificationLevel,
    VerificationResult,
    generate_keypair,
    sign,
)


class TestTrustLineageChainEstablishment:
    """
    Test trust lineage chain creation and establishment.

    Validates that trust chains are properly created with
    cryptographic signatures.
    """

    def test_create_trust_chain_with_genesis(self, test_keypair):
        """Trust chain should be created with genesis record."""
        private_key, public_key = test_keypair

        genesis = GenesisRecord(
            id="genesis-001",
            agent_id="agent-001",
            authority_id="org-001",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            signature=sign({"agent_id": "agent-001"}, private_key),
        )

        chain = TrustLineageChain(genesis=genesis)

        assert chain.genesis.id == "genesis-001"
        assert chain.genesis.agent_id == "agent-001"
        assert chain.genesis.authority_type == AuthorityType.ORGANIZATION

    def test_chain_with_capability_attestations(self, test_keypair):
        """Trust chain should include capability attestations."""
        private_key, public_key = test_keypair

        genesis = GenesisRecord(
            id="genesis-001",
            agent_id="agent-001",
            authority_id="org-001",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            signature=sign({"agent_id": "agent-001"}, private_key),
        )

        attestation = CapabilityAttestation(
            id="cap-001",
            capability="read_data",
            capability_type=CapabilityType.ACCESS,
            constraints=["read_only"],
            attester_id="org-001",
            attested_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=365),
            signature=sign({"capability": "read_data"}, private_key),
        )

        chain = TrustLineageChain(
            genesis=genesis,
            capabilities=[attestation],
        )

        assert len(chain.capabilities) == 1
        assert chain.capabilities[0].capability == "read_data"
        assert chain.has_capability("read_data")

    def test_chain_has_capability_check(self, test_keypair):
        """Chain should correctly report capability presence."""
        private_key, public_key = test_keypair

        genesis = GenesisRecord(
            id="genesis-001",
            agent_id="agent-001",
            authority_id="org-001",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            signature=sign({"agent_id": "agent-001"}, private_key),
        )

        attestation = CapabilityAttestation(
            id="cap-001",
            capability="analyze",
            capability_type=CapabilityType.ACTION,
            constraints=[],
            attester_id="org-001",
            attested_at=datetime.now(timezone.utc),
            signature=sign({"capability": "analyze"}, private_key),
        )

        chain = TrustLineageChain(genesis=genesis, capabilities=[attestation])

        assert chain.has_capability("analyze") is True
        assert chain.has_capability("write") is False

    def test_chain_basic_verification(self, test_keypair):
        """Chain basic verification should pass for valid chain."""
        private_key, public_key = test_keypair

        genesis = GenesisRecord(
            id="genesis-001",
            agent_id="agent-001",
            authority_id="org-001",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            signature=sign({"agent_id": "agent-001"}, private_key),
        )

        chain = TrustLineageChain(genesis=genesis)

        result = chain.verify_basic()

        assert result.valid is True
        assert result.level == VerificationLevel.QUICK


class TestTrustContextPropagation:
    """
    Test trust context propagation through delegation chains.

    Validates that context flows correctly from parent to child
    with proper capability reduction.
    """

    def test_context_propagates_to_child(self, supervisor_context):
        """Parent context should propagate to child."""
        child_context = supervisor_context.propagate_to_child(
            child_agent_id="worker-001",
            task_id="subtask-001",
            capabilities=["analyze"],
        )

        # Child should have reduced capabilities
        assert child_context.has_capability("analyze")
        assert child_context.context_id != supervisor_context.context_id

        # Delegation chain should include parent
        assert len(child_context.delegation_chain) >= 1

    def test_context_cannot_gain_capabilities(self, supervisor_context):
        """Child cannot have capabilities parent doesn't have."""
        # Supervisor has: analyze, report, process, read_data, write_data
        # Trying to give child a capability supervisor doesn't have
        with pytest.raises(ContextPropagationError):
            supervisor_context.propagate_to_child(
                child_agent_id="worker-001",
                task_id="subtask-001",
                capabilities=["admin"],  # Not in supervisor's capabilities
            )

    def test_constraints_can_only_tighten(self, supervisor_context):
        """Constraints can only become more restrictive."""
        # Original constraint: max_records = 10000
        child_context = supervisor_context.propagate_to_child(
            child_agent_id="worker-001",
            task_id="subtask-001",
            additional_constraints={"max_records": 5000},  # More restrictive
        )

        assert child_context.get_constraint("max_records") == 5000

    def test_constraints_cannot_loosen(self, supervisor_context):
        """Constraints cannot become less restrictive."""
        # Original constraint: max_records = 10000
        with pytest.raises(ConstraintLooseningError):
            supervisor_context.propagate_to_child(
                child_agent_id="worker-001",
                task_id="subtask-001",
                additional_constraints={"max_records": 20000},  # Less restrictive
            )

    def test_multi_level_delegation(self, supervisor_context):
        """Context should propagate through multiple levels."""
        # Level 1: Supervisor -> Manager
        manager_context = supervisor_context.propagate_to_child(
            child_agent_id="manager-001",
            task_id="manage-task",
            capabilities=["analyze", "report"],
            additional_constraints={"max_records": 5000},
        )

        # Level 2: Manager -> Worker
        worker_context = manager_context.propagate_to_child(
            child_agent_id="worker-001",
            task_id="work-task",
            capabilities=["analyze"],
            additional_constraints={"max_records": 1000},
        )

        # Worker should have minimal capabilities
        assert worker_context.has_capability("analyze")
        assert not worker_context.has_capability("report")
        assert worker_context.get_constraint("max_records") == 1000

        # Delegation chain should have all levels
        assert len(worker_context.delegation_chain) >= 2


class TestContextMerging:
    """
    Test parallel context merging strategies.

    Validates that contexts from parallel branches merge
    correctly based on strategy.
    """

    def test_intersection_merge_strategy(self, supervisor_context):
        """INTERSECTION keeps only common capabilities."""
        # Create parallel branches with different capabilities
        branch1 = supervisor_context.propagate_to_child(
            child_agent_id="worker-1",
            task_id="task-1",
            capabilities=["analyze", "report"],
        )

        branch2 = supervisor_context.propagate_to_child(
            child_agent_id="worker-2",
            task_id="task-2",
            capabilities=["analyze", "process"],
        )

        # Merge with intersection
        merged = TrustExecutionContext.merge_parallel_contexts(
            contexts=[branch1, branch2],
            strategy=ContextMergeStrategy.INTERSECTION,
        )

        # Only common capability should remain
        assert merged.has_capability("analyze")
        # These are not common:
        assert not merged.has_capability("report")
        assert not merged.has_capability("process")

    def test_union_merge_strategy(self, supervisor_context):
        """UNION combines all capabilities."""
        branch1 = supervisor_context.propagate_to_child(
            child_agent_id="worker-1",
            task_id="task-1",
            capabilities=["analyze"],
        )

        branch2 = supervisor_context.propagate_to_child(
            child_agent_id="worker-2",
            task_id="task-2",
            capabilities=["report"],
        )

        # Merge with union
        merged = TrustExecutionContext.merge_parallel_contexts(
            contexts=[branch1, branch2],
            strategy=ContextMergeStrategy.UNION,
        )

        # All capabilities should be present
        assert merged.has_capability("analyze")
        assert merged.has_capability("report")

    def test_first_wins_merge_strategy(self, supervisor_context):
        """FIRST_WINS uses first context's capabilities."""
        branch1 = supervisor_context.propagate_to_child(
            child_agent_id="worker-1",
            task_id="task-1",
            capabilities=["analyze"],
        )

        branch2 = supervisor_context.propagate_to_child(
            child_agent_id="worker-2",
            task_id="task-2",
            capabilities=["report"],
        )

        # Merge with first wins
        merged = TrustExecutionContext.merge_parallel_contexts(
            contexts=[branch1, branch2],
            strategy=ContextMergeStrategy.FIRST_WINS,
        )

        # First context's capabilities should be used
        assert merged.has_capability("analyze")


class TestDelegationChainIntegrity:
    """
    Test delegation chain integrity verification.

    Validates that delegation chains maintain cryptographic
    integrity and detect tampering.
    """

    def test_delegation_entry_contains_required_fields(self, supervisor_context):
        """Delegation entries should have all required fields."""
        child_context = supervisor_context.propagate_to_child(
            child_agent_id="worker-001",
            task_id="subtask-001",
            capabilities=["analyze"],
        )

        # Check delegation chain entry
        assert len(child_context.delegation_chain) >= 1
        entry = child_context.delegation_chain[-1]

        # DelegationEntry uses delegator_id, delegatee_id, and timestamp
        assert entry.delegator_id is not None
        assert entry.delegatee_id == "worker-001"
        assert entry.timestamp is not None

    def test_delegation_chain_preserves_history(self, supervisor_context):
        """Chain should preserve full delegation history."""
        # Create 3-level delegation
        level1 = supervisor_context.propagate_to_child(
            child_agent_id="manager-001",
            task_id="manage",
            capabilities=["analyze", "report"],
        )

        level2 = level1.propagate_to_child(
            child_agent_id="worker-001",
            task_id="work",
            capabilities=["analyze"],
        )

        level3 = level2.propagate_to_child(
            child_agent_id="subworker-001",
            task_id="subwork",
            capabilities=["analyze"],
        )

        # Full chain should be preserved (delegatee_id is the recipient)
        chain_agents = [e.delegatee_id for e in level3.delegation_chain]
        assert "manager-001" in chain_agents
        assert "worker-001" in chain_agents
        assert "subworker-001" in chain_agents

    def test_context_serialization_roundtrip(self, supervisor_context):
        """Context should survive serialization roundtrip."""
        child_context = supervisor_context.propagate_to_child(
            child_agent_id="worker-001",
            task_id="subtask-001",
            capabilities=["analyze"],
            additional_constraints={"max_records": 5000},
        )

        # Serialize
        data = child_context.to_dict()

        # Deserialize
        restored = TrustExecutionContext.from_dict(data)

        # Should match original
        assert restored.context_id == child_context.context_id
        assert restored.has_capability("analyze")
        assert restored.get_constraint("max_records") == 5000
        assert len(restored.delegation_chain) == len(child_context.delegation_chain)
