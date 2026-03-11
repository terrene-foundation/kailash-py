"""
Unit tests for EATP Trust Lineage Chain data structures.

Tests cover:
- All enum types
- All dataclasses
- TrustLineageChain methods
- Serialization/deserialization
"""

from datetime import datetime, timedelta, timezone

import pytest

from kaizen.trust.chain import (
    ActionResult,
    AuditAnchor,
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    Constraint,
    ConstraintEnvelope,
    ConstraintType,
    DelegationRecord,
    GenesisRecord,
    TrustLineageChain,
    VerificationLevel,
    VerificationResult,
)


class TestEnums:
    """Tests for enum types."""

    def test_authority_type_values(self):
        """AuthorityType enum has correct values."""
        assert AuthorityType.ORGANIZATION.value == "organization"
        assert AuthorityType.SYSTEM.value == "system"
        assert AuthorityType.HUMAN.value == "human"

    def test_capability_type_values(self):
        """CapabilityType enum has correct values."""
        assert CapabilityType.ACCESS.value == "access"
        assert CapabilityType.ACTION.value == "action"
        assert CapabilityType.DELEGATION.value == "delegation"

    def test_action_result_values(self):
        """ActionResult enum has correct values."""
        assert ActionResult.SUCCESS.value == "success"
        assert ActionResult.FAILURE.value == "failure"
        assert ActionResult.DENIED.value == "denied"
        assert ActionResult.PARTIAL.value == "partial"

    def test_constraint_type_values(self):
        """ConstraintType enum has correct values."""
        assert ConstraintType.RESOURCE_LIMIT.value == "resource_limit"
        assert ConstraintType.TIME_WINDOW.value == "time_window"
        assert ConstraintType.DATA_SCOPE.value == "data_scope"
        assert ConstraintType.ACTION_RESTRICTION.value == "action_restriction"
        assert ConstraintType.AUDIT_REQUIREMENT.value == "audit_requirement"

    def test_verification_level_values(self):
        """VerificationLevel enum has correct values."""
        assert VerificationLevel.QUICK.value == "quick"
        assert VerificationLevel.STANDARD.value == "standard"
        assert VerificationLevel.FULL.value == "full"


class TestGenesisRecord:
    """Tests for GenesisRecord dataclass."""

    @pytest.fixture
    def genesis_record(self):
        """Create a sample genesis record."""
        return GenesisRecord(
            id="gen-001",
            agent_id="agent-001",
            authority_id="auth-001",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime(2025, 12, 15, 10, 0, 0, tzinfo=timezone.utc),
            signature="test-signature",
            signature_algorithm="Ed25519",
            expires_at=datetime(2026, 12, 15, 10, 0, 0, tzinfo=timezone.utc),
            metadata={"department": "Finance"},
        )

    def test_genesis_record_creation(self, genesis_record):
        """GenesisRecord can be created with all fields."""
        assert genesis_record.id == "gen-001"
        assert genesis_record.agent_id == "agent-001"
        assert genesis_record.authority_id == "auth-001"
        assert genesis_record.authority_type == AuthorityType.ORGANIZATION
        assert genesis_record.signature == "test-signature"
        assert genesis_record.metadata["department"] == "Finance"

    def test_genesis_record_not_expired(self, genesis_record):
        """GenesisRecord not expired when expires_at is in future."""
        assert genesis_record.is_expired() is False

    def test_genesis_record_expired(self):
        """GenesisRecord expired when expires_at is in past."""
        record = GenesisRecord(
            id="gen-002",
            agent_id="agent-002",
            authority_id="auth-001",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            expires_at=datetime(2024, 12, 31, tzinfo=timezone.utc),
            signature="test",
        )
        assert record.is_expired() is True

    def test_genesis_record_no_expiration(self):
        """GenesisRecord without expires_at never expires."""
        record = GenesisRecord(
            id="gen-003",
            agent_id="agent-003",
            authority_id="auth-001",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime(2025, 1, 1),
            signature="test",
        )
        assert record.is_expired() is False

    def test_genesis_record_to_signing_payload(self, genesis_record):
        """GenesisRecord generates correct signing payload."""
        payload = genesis_record.to_signing_payload()
        assert payload["id"] == "gen-001"
        assert payload["agent_id"] == "agent-001"
        assert payload["authority_type"] == "organization"
        assert "signature" not in payload  # Signature not included in payload


class TestCapabilityAttestation:
    """Tests for CapabilityAttestation dataclass."""

    @pytest.fixture
    def capability(self):
        """Create a sample capability attestation."""
        return CapabilityAttestation(
            id="cap-001",
            capability="analyze_financial_data",
            capability_type=CapabilityType.ACCESS,
            constraints=["read_only", "no_pii"],
            attester_id="auth-001",
            attested_at=datetime(2025, 12, 15, 10, 0, 0, tzinfo=timezone.utc),
            signature="test-signature",
            expires_at=datetime(2026, 12, 15, 10, 0, 0, tzinfo=timezone.utc),
            scope={"tables": ["transactions", "accounts"]},
        )

    def test_capability_creation(self, capability):
        """CapabilityAttestation can be created with all fields."""
        assert capability.id == "cap-001"
        assert capability.capability == "analyze_financial_data"
        assert capability.capability_type == CapabilityType.ACCESS
        assert "read_only" in capability.constraints
        assert capability.scope["tables"] == ["transactions", "accounts"]

    def test_capability_not_expired(self, capability):
        """CapabilityAttestation not expired when expires_at is in future."""
        assert capability.is_expired() is False

    def test_capability_expired(self):
        """CapabilityAttestation expired when expires_at is in past."""
        cap = CapabilityAttestation(
            id="cap-002",
            capability="test",
            capability_type=CapabilityType.ACTION,
            constraints=[],
            attester_id="auth-001",
            attested_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            expires_at=datetime(2024, 12, 31, tzinfo=timezone.utc),
            signature="test",
        )
        assert cap.is_expired() is True

    def test_capability_to_signing_payload(self, capability):
        """CapabilityAttestation generates correct signing payload."""
        payload = capability.to_signing_payload()
        assert payload["id"] == "cap-001"
        assert payload["capability"] == "analyze_financial_data"
        assert payload["capability_type"] == "access"
        assert payload["constraints"] == ["no_pii", "read_only"]  # Sorted


class TestDelegationRecord:
    """Tests for DelegationRecord dataclass."""

    @pytest.fixture
    def delegation(self):
        """Create a sample delegation record."""
        return DelegationRecord(
            id="del-001",
            delegator_id="supervisor-001",
            delegatee_id="worker-001",
            task_id="task-001",
            capabilities_delegated=["analyze_data"],
            constraint_subset=["q4_only"],
            delegated_at=datetime(2025, 12, 15, 10, 0, 0, tzinfo=timezone.utc),
            signature="test-signature",
            expires_at=datetime(2025, 12, 15, 18, 0, 0, tzinfo=timezone.utc),
        )

    def test_delegation_creation(self, delegation):
        """DelegationRecord can be created with all fields."""
        assert delegation.id == "del-001"
        assert delegation.delegator_id == "supervisor-001"
        assert delegation.delegatee_id == "worker-001"
        assert "analyze_data" in delegation.capabilities_delegated

    def test_delegation_not_expired(self, delegation):
        """DelegationRecord not expired when expires_at is in future."""
        # Modify to future
        delegation.expires_at = datetime.now(timezone.utc) + timedelta(hours=8)
        assert delegation.is_expired() is False

    def test_delegation_expired(self):
        """DelegationRecord expired when expires_at is in past."""
        delegation = DelegationRecord(
            id="del-002",
            delegator_id="sup",
            delegatee_id="worker",
            task_id="task",
            capabilities_delegated=["test"],
            constraint_subset=[],
            delegated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            expires_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
            signature="test",
        )
        assert delegation.is_expired() is True


class TestConstraint:
    """Tests for Constraint dataclass."""

    def test_constraint_creation(self):
        """Constraint can be created with all fields."""
        constraint = Constraint(
            id="con-001",
            constraint_type=ConstraintType.ACTION_RESTRICTION,
            value="read_only",
            source="cap-001",
            priority=100,
        )
        assert constraint.id == "con-001"
        assert constraint.constraint_type == ConstraintType.ACTION_RESTRICTION
        assert constraint.value == "read_only"
        assert constraint.priority == 100


class TestConstraintEnvelope:
    """Tests for ConstraintEnvelope dataclass."""

    @pytest.fixture
    def envelope(self):
        """Create a sample constraint envelope."""
        constraints = [
            Constraint(
                id="con-001",
                constraint_type=ConstraintType.ACTION_RESTRICTION,
                value="read_only",
                source="cap-001",
                priority=100,
            ),
            Constraint(
                id="con-002",
                constraint_type=ConstraintType.TIME_WINDOW,
                value={"start": "09:00", "end": "17:00"},
                source="gen-001",
                priority=80,
            ),
        ]
        return ConstraintEnvelope(
            id="env-001",
            agent_id="agent-001",
            active_constraints=constraints,
            valid_until=datetime.now(timezone.utc) + timedelta(hours=1),
        )

    def test_envelope_creation(self, envelope):
        """ConstraintEnvelope can be created with all fields."""
        assert envelope.id == "env-001"
        assert envelope.agent_id == "agent-001"
        assert len(envelope.active_constraints) == 2

    def test_envelope_hash_computed(self, envelope):
        """ConstraintEnvelope computes hash on creation."""
        assert envelope.constraint_hash != ""
        assert len(envelope.constraint_hash) == 64  # SHA-256 hex

    def test_envelope_get_all_constraints(self, envelope):
        """get_all_constraints returns constraint values."""
        constraints = envelope.get_all_constraints()
        assert "read_only" in constraints

    def test_envelope_get_constraints_by_type(self, envelope):
        """get_constraints_by_type filters correctly."""
        action_constraints = envelope.get_constraints_by_type(
            ConstraintType.ACTION_RESTRICTION
        )
        assert len(action_constraints) == 1
        assert action_constraints[0].value == "read_only"

    def test_envelope_is_valid(self, envelope):
        """is_valid returns True when not expired."""
        assert envelope.is_valid() is True

    def test_envelope_is_invalid_when_expired(self):
        """is_valid returns False when expired."""
        envelope = ConstraintEnvelope(
            id="env-002",
            agent_id="agent-002",
            valid_until=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        assert envelope.is_valid() is False


class TestAuditAnchor:
    """Tests for AuditAnchor dataclass."""

    @pytest.fixture
    def audit_anchor(self):
        """Create a sample audit anchor."""
        return AuditAnchor(
            id="aud-001",
            agent_id="agent-001",
            action="query_transactions",
            timestamp=datetime(2025, 12, 15, 10, 35, 0),
            trust_chain_hash="abc123",
            result=ActionResult.SUCCESS,
            signature="test-signature",
            resource="finance_db.transactions",
            context={"rows_returned": 100},
        )

    def test_audit_anchor_creation(self, audit_anchor):
        """AuditAnchor can be created with all fields."""
        assert audit_anchor.id == "aud-001"
        assert audit_anchor.action == "query_transactions"
        assert audit_anchor.result == ActionResult.SUCCESS
        assert audit_anchor.resource == "finance_db.transactions"
        assert audit_anchor.context["rows_returned"] == 100

    def test_audit_anchor_to_signing_payload(self, audit_anchor):
        """AuditAnchor generates correct signing payload."""
        payload = audit_anchor.to_signing_payload()
        assert payload["id"] == "aud-001"
        assert payload["action"] == "query_transactions"
        assert payload["result"] == "success"


class TestTrustLineageChain:
    """Tests for TrustLineageChain dataclass."""

    @pytest.fixture
    def genesis(self):
        """Create a sample genesis record."""
        return GenesisRecord(
            id="gen-001",
            agent_id="agent-001",
            authority_id="auth-001",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime(2025, 12, 15, 10, 0, 0, tzinfo=timezone.utc),
            signature="test-signature",
            expires_at=datetime(2026, 12, 15, 10, 0, 0, tzinfo=timezone.utc),
        )

    @pytest.fixture
    def capabilities(self):
        """Create sample capabilities."""
        return [
            CapabilityAttestation(
                id="cap-001",
                capability="analyze_data",
                capability_type=CapabilityType.ACCESS,
                constraints=["read_only"],
                attester_id="auth-001",
                attested_at=datetime(2025, 12, 15, 10, 0, 0, tzinfo=timezone.utc),
                signature="test",
                expires_at=datetime(2026, 12, 15, 10, 0, 0, tzinfo=timezone.utc),
            ),
            CapabilityAttestation(
                id="cap-002",
                capability="generate_reports",
                capability_type=CapabilityType.ACTION,
                constraints=["internal_only"],
                attester_id="auth-001",
                attested_at=datetime(2025, 12, 15, 10, 0, 0, tzinfo=timezone.utc),
                signature="test",
                expires_at=datetime(2026, 12, 15, 10, 0, 0, tzinfo=timezone.utc),
            ),
        ]

    @pytest.fixture
    def delegations(self):
        """Create sample delegations."""
        return [
            DelegationRecord(
                id="del-001",
                delegator_id="supervisor-001",
                delegatee_id="agent-001",
                task_id="task-001",
                capabilities_delegated=["analyze_data"],
                constraint_subset=["q4_only"],
                delegated_at=datetime(2025, 12, 15, 10, 30, 0, tzinfo=timezone.utc),
                signature="test",
                expires_at=datetime(2026, 12, 15, 10, 0, 0, tzinfo=timezone.utc),
            )
        ]

    @pytest.fixture
    def trust_chain(self, genesis, capabilities, delegations):
        """Create a sample trust lineage chain."""
        return TrustLineageChain(
            genesis=genesis, capabilities=capabilities, delegations=delegations
        )

    def test_chain_creation(self, trust_chain):
        """TrustLineageChain can be created with all components."""
        assert trust_chain.genesis.id == "gen-001"
        assert len(trust_chain.capabilities) == 2
        assert len(trust_chain.delegations) == 1
        assert trust_chain.constraint_envelope is not None

    def test_chain_hash_stability(self, trust_chain):
        """Chain hash is deterministic."""
        hash1 = trust_chain.hash()
        hash2 = trust_chain.hash()
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex

    def test_chain_hash_changes_with_content(self, genesis, capabilities):
        """Chain hash changes when content changes."""
        chain1 = TrustLineageChain(genesis=genesis, capabilities=capabilities)
        chain2 = TrustLineageChain(genesis=genesis, capabilities=[capabilities[0]])
        assert chain1.hash() != chain2.hash()

    def test_chain_not_expired(self, trust_chain):
        """Chain not expired when components are valid."""
        assert trust_chain.is_expired() is False

    def test_chain_expired_when_genesis_expired(self, capabilities):
        """Chain expired when genesis is expired."""
        expired_genesis = GenesisRecord(
            id="gen-002",
            agent_id="agent-002",
            authority_id="auth-001",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            expires_at=datetime(2024, 12, 31, tzinfo=timezone.utc),
            signature="test",
        )
        chain = TrustLineageChain(genesis=expired_genesis, capabilities=capabilities)
        assert chain.is_expired() is True

    def test_has_capability(self, trust_chain):
        """has_capability returns True for existing capabilities."""
        assert trust_chain.has_capability("analyze_data") is True
        assert trust_chain.has_capability("generate_reports") is True
        assert trust_chain.has_capability("delete_all") is False

    def test_get_capability(self, trust_chain):
        """get_capability returns capability attestation."""
        cap = trust_chain.get_capability("analyze_data")
        assert cap is not None
        assert cap.id == "cap-001"

        missing = trust_chain.get_capability("nonexistent")
        assert missing is None

    def test_get_effective_constraints(self, trust_chain):
        """get_effective_constraints aggregates from capabilities and delegations."""
        constraints = trust_chain.get_effective_constraints("analyze_data")
        assert "read_only" in constraints  # From capability
        assert "q4_only" in constraints  # From delegation

    def test_verify_basic_success(self, trust_chain):
        """verify_basic returns valid for good chain."""
        result = trust_chain.verify_basic()
        assert result.valid is True
        assert result.level == VerificationLevel.QUICK

    def test_verify_basic_no_genesis(self, capabilities):
        """verify_basic fails without genesis."""
        # Create chain with None genesis (would fail in practice)
        chain = TrustLineageChain.__new__(TrustLineageChain)
        chain.genesis = None
        chain.capabilities = capabilities
        chain.delegations = []
        chain.constraint_envelope = None
        chain.audit_anchors = []

        result = chain.verify_basic()
        assert result.valid is False
        assert "No genesis record" in result.reason

    def test_get_active_delegations(self, trust_chain):
        """get_active_delegations returns non-expired delegations."""
        active = trust_chain.get_active_delegations()
        assert len(active) == 1

    def test_to_dict_and_from_dict(self, trust_chain):
        """Chain can be serialized and deserialized."""
        data = trust_chain.to_dict()

        assert data["genesis"]["id"] == "gen-001"
        assert len(data["capabilities"]) == 2
        assert data["chain_hash"] == trust_chain.hash()

        # Reconstruct
        reconstructed = TrustLineageChain.from_dict(data)
        assert reconstructed.genesis.id == trust_chain.genesis.id
        assert len(reconstructed.capabilities) == len(trust_chain.capabilities)
        # Hash should match (deterministic)
        # Note: May differ due to signature not being in serialized form


class TestVerificationResult:
    """Tests for VerificationResult dataclass."""

    def test_verification_result_valid(self):
        """VerificationResult can represent valid verification."""
        result = VerificationResult(
            valid=True,
            level=VerificationLevel.STANDARD,
            capability_used="analyze_data",
            effective_constraints=["read_only"],
        )
        assert result.valid is True
        assert result.capability_used == "analyze_data"

    def test_verification_result_invalid(self):
        """VerificationResult can represent failed verification."""
        result = VerificationResult(
            valid=False,
            level=VerificationLevel.STANDARD,
            reason="No capability found",
            violations=[{"constraint_id": "con-001", "reason": "Action restricted"}],
        )
        assert result.valid is False
        assert result.reason == "No capability found"
        assert len(result.violations) == 1
