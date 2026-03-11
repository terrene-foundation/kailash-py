"""
Integration tests for CARE-036: Knowledge Entry Structures.

Tests knowledge entries with REAL trust infrastructure (NO MOCKING).
Uses InMemoryTrustStore and manually created trust chains to verify
knowledge entry integration.

Note: These tests do NOT require PostgreSQL - they use InMemoryTrustStore
for Tier 2 integration testing of knowledge entries with trust chains.
"""

from datetime import datetime, timedelta, timezone

import pytest
from kaizen.trust.chain import (
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    GenesisRecord,
    TrustLineageChain,
)
from kaizen.trust.crypto import generate_keypair, sign
from kaizen.trust.knowledge import KnowledgeEntry, KnowledgeType


class TestKnowledgeEntryWithTrustChain:
    """Integration tests for knowledge entries with trust chains."""

    @pytest.fixture
    def test_keypair(self):
        """Generate a test keypair for signing."""
        return generate_keypair()

    def create_trust_chain(
        self,
        agent_id: str,
        authority_id: str,
        private_key: str,
        capabilities: list[str],
    ) -> TrustLineageChain:
        """
        Create a real trust chain with signed genesis and capabilities.

        This is a helper to create valid trust chains without requiring
        TrustOperations (which needs PostgreSQL).
        """
        # Create signed genesis record
        genesis = GenesisRecord(
            id=f"genesis-{agent_id}",
            agent_id=agent_id,
            authority_id=authority_id,
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            signature=sign({"agent_id": agent_id}, private_key),
            expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        )

        # Create capability attestations
        attestations = []
        for i, cap in enumerate(capabilities):
            attestation = CapabilityAttestation(
                id=f"cap-{agent_id}-{i}",
                capability=cap,
                capability_type=CapabilityType.ACTION,
                constraints=[],
                attester_id=authority_id,
                attested_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(days=365),
                signature=sign({"capability": cap}, private_key),
            )
            attestations.append(attestation)

        return TrustLineageChain(genesis=genesis, capabilities=attestations)

    def test_knowledge_entry_with_trust_chain(self, test_keypair):
        """
        Create a trust chain for an agent, create KnowledgeEntry referencing
        the chain, verify entry validates.
        """
        private_key, public_key = test_keypair
        authority_id = "org-test"
        agent_id = "knowledge-agent-001"

        # Create trust chain with real signatures
        chain = self.create_trust_chain(
            agent_id=agent_id,
            authority_id=authority_id,
            private_key=private_key,
            capabilities=["contribute_knowledge"],
        )

        # Get the chain hash as trust reference
        trust_chain_ref = chain.hash()

        # Create knowledge entry referencing the trust chain
        entry = KnowledgeEntry.create(
            content="The system supports up to 10,000 concurrent users",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id=agent_id,
            trust_chain_ref=trust_chain_ref,
            confidence_score=0.95,
            metadata={"domain": "infrastructure"},
        )

        # Verify entry is valid
        assert entry.validate() is True
        assert entry.is_valid() is True

        # Verify the entry references the correct agent
        assert entry.source_agent_id == agent_id

        # Verify the trust chain reference is set
        assert entry.trust_chain_ref == trust_chain_ref
        assert len(trust_chain_ref) == 64  # SHA-256 hex string

        # Verify the chain itself is valid
        verification = chain.verify_basic()
        assert verification.valid is True

        # Verify chain hash matches entry reference
        assert chain.hash() == entry.trust_chain_ref

    def test_knowledge_verification_workflow(self, test_keypair):
        """
        Agent A creates entry, Agents B and C verify it,
        check verified_by list.
        """
        private_key, public_key = test_keypair
        authority_id = "org-test-verify"

        # Create agents
        agents = {
            "creator": "agent-creator",
            "verifier_b": "agent-verifier-b",
            "verifier_c": "agent-verifier-c",
        }

        # Create trust chain for creator
        creator_chain = self.create_trust_chain(
            agent_id=agents["creator"],
            authority_id=authority_id,
            private_key=private_key,
            capabilities=["contribute_knowledge"],
        )

        # Create trust chains for verifiers
        verifier_b_chain = self.create_trust_chain(
            agent_id=agents["verifier_b"],
            authority_id=authority_id,
            private_key=private_key,
            capabilities=["verify_knowledge"],
        )

        verifier_c_chain = self.create_trust_chain(
            agent_id=agents["verifier_c"],
            authority_id=authority_id,
            private_key=private_key,
            capabilities=["verify_knowledge"],
        )

        # Agent A (creator) creates a knowledge entry
        entry = KnowledgeEntry.create(
            content="Best practice: Always validate input before processing",
            content_type=KnowledgeType.PROCEDURAL,
            source_agent_id=agents["creator"],
            trust_chain_ref=creator_chain.hash(),
            confidence_score=0.85,
        )

        # Verify initial state - no verifiers
        assert entry.verified_by == []

        # Agent B verifies the entry (simulating verification workflow)
        # In real scenario, verifier would check the trust chain reference
        assert verifier_b_chain.verify_basic().valid is True
        entry.add_verification(agents["verifier_b"])
        assert agents["verifier_b"] in entry.verified_by
        assert len(entry.verified_by) == 1

        # Agent C verifies the entry
        assert verifier_c_chain.verify_basic().valid is True
        entry.add_verification(agents["verifier_c"])
        assert agents["verifier_c"] in entry.verified_by
        assert len(entry.verified_by) == 2

        # Verify order is preserved
        assert entry.verified_by[0] == agents["verifier_b"]
        assert entry.verified_by[1] == agents["verifier_c"]

        # Attempt duplicate verification - should not add
        entry.add_verification(agents["verifier_b"])
        assert len(entry.verified_by) == 2

        # Serialize and deserialize - verifiers should be preserved
        data = entry.to_dict()
        restored = KnowledgeEntry.from_dict(data)

        assert restored.verified_by == [agents["verifier_b"], agents["verifier_c"]]

    def test_knowledge_entry_with_constraint_envelope(self, test_keypair):
        """
        Create knowledge entry with constraint envelope reference.
        """
        private_key, public_key = test_keypair
        authority_id = "org-test-constraint"
        agent_id = "constrained-agent"

        # Create trust chain with constrained capability
        genesis = GenesisRecord(
            id=f"genesis-{agent_id}",
            agent_id=agent_id,
            authority_id=authority_id,
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            signature=sign({"agent_id": agent_id}, private_key),
        )

        attestation = CapabilityAttestation(
            id=f"cap-{agent_id}",
            capability="contribute_knowledge",
            capability_type=CapabilityType.ACTION,
            constraints=["read_only", "internal_only"],
            attester_id=authority_id,
            attested_at=datetime.now(timezone.utc),
            signature=sign({"capability": "contribute_knowledge"}, private_key),
        )

        chain = TrustLineageChain(genesis=genesis, capabilities=[attestation])

        # Get constraint envelope ID if it exists
        constraint_envelope_ref = None
        if chain.constraint_envelope:
            constraint_envelope_ref = chain.constraint_envelope.id

        # Create knowledge entry with constraint envelope reference
        entry = KnowledgeEntry.create(
            content="Internal API endpoint: /api/v2/internal/users",
            content_type=KnowledgeType.FACTUAL,
            source_agent_id=agent_id,
            trust_chain_ref=chain.hash(),
            constraint_envelope_ref=constraint_envelope_ref,
            confidence_score=0.99,
            metadata={"sensitivity": "internal", "api_version": "v2"},
        )

        # Verify entry is valid
        assert entry.validate() is True

        # Verify constraint envelope is referenced
        if constraint_envelope_ref:
            assert entry.constraint_envelope_ref == constraint_envelope_ref

        # Verify the constraints are in the capability
        assert chain.capabilities[0].constraints == ["read_only", "internal_only"]

    def test_multiple_knowledge_types_with_trust(self, test_keypair):
        """
        Create entries of different knowledge types with trust chain.
        """
        private_key, public_key = test_keypair
        authority_id = "org-test-types"
        agent_id = "multi-type-agent"

        # Create trust chain
        chain = self.create_trust_chain(
            agent_id=agent_id,
            authority_id=authority_id,
            private_key=private_key,
            capabilities=["contribute_all_knowledge"],
        )
        trust_chain_ref = chain.hash()

        # Create entries of each type
        entries = []
        for kt in KnowledgeType:
            entry = KnowledgeEntry.create(
                content=f"Knowledge of type {kt.value}",
                content_type=kt,
                source_agent_id=agent_id,
                trust_chain_ref=trust_chain_ref,
            )
            entries.append(entry)

        # Verify all entries are valid and reference the same chain
        assert len(entries) == 5
        for entry in entries:
            assert entry.validate() is True
            assert entry.trust_chain_ref == trust_chain_ref
            assert entry.source_agent_id == agent_id

        # Verify each type is represented
        types_created = {e.content_type for e in entries}
        assert types_created == set(KnowledgeType)

    def test_knowledge_entry_serialization_with_trust_context(self, test_keypair):
        """
        Verify serialization preserves trust chain reference.
        """
        private_key, public_key = test_keypair
        authority_id = "org-test-serial"
        agent_id = "serialization-agent"

        # Create trust chain
        chain = self.create_trust_chain(
            agent_id=agent_id,
            authority_id=authority_id,
            private_key=private_key,
            capabilities=["contribute_knowledge"],
        )

        # Create entry
        original = KnowledgeEntry.create(
            content="Decision: Use async/await for I/O operations",
            content_type=KnowledgeType.DECISION_RATIONALE,
            source_agent_id=agent_id,
            trust_chain_ref=chain.hash(),
            confidence_score=0.88,
            metadata={"decision_id": "D-2025-001", "approved_by": "tech-lead"},
        )
        original.add_verification("reviewer-1")

        # Serialize
        data = original.to_dict()

        # Verify trust chain ref is in serialized data
        assert data["trust_chain_ref"] == chain.hash()

        # Deserialize
        restored = KnowledgeEntry.from_dict(data)

        # Verify trust chain ref is preserved
        assert restored.trust_chain_ref == chain.hash()

        # Verify we can compute matching hash from the chain
        assert chain.hash() == restored.trust_chain_ref
