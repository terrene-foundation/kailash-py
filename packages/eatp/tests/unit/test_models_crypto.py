"""Unit tests for EATP models, crypto, and serialization.

Covers:
- Model Validation (30+ tests): All required fields, optional fields, invalid values,
  expiration logic, to_signing_payload, to_dict/from_dict round-trips
- Crypto Operations (20+ tests): Keypair generation, sign/verify cycle, tampered message
  rejection, hash_chain for str/dict/bytes, Merkle tree build/proof/verify, challenge-response
- Serialization (15+ tests): JSON round-trip for every model, optional fields,
  deterministic serialization
"""

import hashlib
import json
import math

import pytest
from datetime import datetime, timedelta, timezone

from eatp.chain import (
    GenesisRecord,
    CapabilityAttestation,
    DelegationRecord,
    ConstraintEnvelope,
    Constraint,
    AuditAnchor,
    VerificationResult,
    TrustLineageChain,
    LinkedHashChain,
    LinkedHashEntry,
    DelegationLimits,
    AuthorityType,
    CapabilityType,
    ActionResult,
    ConstraintType,
    VerificationLevel,
)
from eatp.crypto import (
    generate_keypair,
    sign,
    verify_signature,
    serialize_for_signing,
    hash_chain,
    generate_salt,
    derive_key_with_salt,
    hash_trust_chain_state,
    hash_trust_chain_state_salted,
)
from eatp.merkle import (
    MerkleTree,
    MerkleProof,
    MerkleNode,
    verify_merkle_proof,
    compute_merkle_root,
    get_proof_length,
)
from eatp.exceptions import (
    TrustError,
    AuthorityNotFoundError,
    TrustChainNotFoundError,
    InvalidTrustChainError,
    CapabilityNotFoundError,
    ConstraintViolationError,
    DelegationError,
    DelegationCycleError,
    InvalidSignatureError,
    VerificationFailedError,
    DelegationExpiredError,
    AgentAlreadyEstablishedError,
    TrustStoreError,
    TrustChainInvalidError,
    TrustStoreDatabaseError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOW = datetime.now(timezone.utc)
PAST = datetime(2020, 1, 1, tzinfo=timezone.utc)
FUTURE = datetime(2099, 12, 31, tzinfo=timezone.utc)


@pytest.fixture
def keypair():
    """Generate a fresh Ed25519 keypair for each test."""
    private_key, public_key = generate_keypair()
    return private_key, public_key


@pytest.fixture
def genesis_record(keypair):
    """A minimal valid GenesisRecord."""
    _, public_key = keypair
    return GenesisRecord(
        id="gen-001",
        agent_id="agent-001",
        authority_id="auth-001",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=NOW,
        signature="sig-placeholder",
        signature_algorithm="Ed25519",
        expires_at=FUTURE,
        metadata={"department": "engineering"},
    )


@pytest.fixture
def capability_attestation():
    """A minimal valid CapabilityAttestation."""
    return CapabilityAttestation(
        id="cap-001",
        capability="analyze_data",
        capability_type=CapabilityType.ACTION,
        constraints=["read_only"],
        attester_id="auth-001",
        attested_at=NOW,
        signature="sig-placeholder",
        expires_at=FUTURE,
        scope={"tables": ["transactions"]},
    )


@pytest.fixture
def delegation_record():
    """A minimal valid DelegationRecord."""
    return DelegationRecord(
        id="del-001",
        delegator_id="agent-001",
        delegatee_id="agent-002",
        task_id="task-001",
        capabilities_delegated=["analyze_data"],
        constraint_subset=["read_only", "no_pii"],
        delegated_at=NOW,
        signature="sig-placeholder",
        expires_at=FUTURE,
        parent_delegation_id=None,
    )


@pytest.fixture
def audit_anchor():
    """A minimal valid AuditAnchor."""
    return AuditAnchor(
        id="audit-001",
        agent_id="agent-001",
        action="analyze_data",
        timestamp=NOW,
        trust_chain_hash="abc123hash",
        result=ActionResult.SUCCESS,
        signature="sig-placeholder",
        resource="transactions_table",
        context={"rows_processed": 100},
    )


@pytest.fixture
def trust_chain(genesis_record, capability_attestation, delegation_record):
    """A fully populated TrustLineageChain."""
    return TrustLineageChain(
        genesis=genesis_record,
        capabilities=[capability_attestation],
        delegations=[delegation_record],
    )


# ===========================================================================
# Section 1: Model Validation Tests (30+ tests)
# ===========================================================================


class TestEnums:
    """Test enum definitions and values."""

    def test_authority_type_values(self):
        assert AuthorityType.ORGANIZATION.value == "organization"
        assert AuthorityType.SYSTEM.value == "system"
        assert AuthorityType.HUMAN.value == "human"

    def test_capability_type_values(self):
        assert CapabilityType.ACCESS.value == "access"
        assert CapabilityType.ACTION.value == "action"
        assert CapabilityType.DELEGATION.value == "delegation"

    def test_action_result_values(self):
        assert ActionResult.SUCCESS.value == "success"
        assert ActionResult.FAILURE.value == "failure"
        assert ActionResult.DENIED.value == "denied"
        assert ActionResult.PARTIAL.value == "partial"

    def test_constraint_type_values(self):
        assert ConstraintType.RESOURCE_LIMIT.value == "resource_limit"
        assert ConstraintType.TIME_WINDOW.value == "time_window"
        assert ConstraintType.DATA_SCOPE.value == "data_scope"
        assert ConstraintType.ACTION_RESTRICTION.value == "action_restriction"
        assert ConstraintType.AUDIT_REQUIREMENT.value == "audit_requirement"

    def test_verification_level_values(self):
        assert VerificationLevel.QUICK.value == "quick"
        assert VerificationLevel.STANDARD.value == "standard"
        assert VerificationLevel.FULL.value == "full"


class TestDelegationLimits:
    """Test DelegationLimits validation."""

    def test_default_values(self):
        limits = DelegationLimits()
        assert limits.max_depth == 10
        assert limits.max_chain_length == 50
        assert limits.require_expiry is True
        assert limits.default_expiry_hours == 24

    def test_custom_valid_values(self):
        limits = DelegationLimits(max_depth=5, max_chain_length=20)
        assert limits.max_depth == 5
        assert limits.max_chain_length == 20

    def test_max_depth_must_be_at_least_one(self):
        with pytest.raises(ValueError, match="max_depth must be at least 1"):
            DelegationLimits(max_depth=0)

    def test_negative_max_depth_rejected(self):
        with pytest.raises(ValueError, match="max_depth must be at least 1"):
            DelegationLimits(max_depth=-1)

    def test_chain_length_must_be_gte_depth(self):
        with pytest.raises(ValueError, match="max_chain_length must be >= max_depth"):
            DelegationLimits(max_depth=10, max_chain_length=5)

    def test_equal_depth_and_chain_length_accepted(self):
        limits = DelegationLimits(max_depth=3, max_chain_length=3)
        assert limits.max_depth == 3
        assert limits.max_chain_length == 3


class TestGenesisRecord:
    """Test GenesisRecord fields and methods."""

    def test_required_fields(self, genesis_record):
        assert genesis_record.id == "gen-001"
        assert genesis_record.agent_id == "agent-001"
        assert genesis_record.authority_id == "auth-001"
        assert genesis_record.authority_type == AuthorityType.ORGANIZATION
        assert genesis_record.signature == "sig-placeholder"

    def test_optional_fields_defaults(self):
        record = GenesisRecord(
            id="gen-002",
            agent_id="agent-002",
            authority_id="auth-002",
            authority_type=AuthorityType.HUMAN,
            created_at=NOW,
            signature="sig",
        )
        assert record.expires_at is None
        assert record.metadata == {}
        assert record.signature_algorithm == "Ed25519"

    def test_is_expired_with_past_date(self):
        record = GenesisRecord(
            id="gen-exp",
            agent_id="agent-exp",
            authority_id="auth-exp",
            authority_type=AuthorityType.SYSTEM,
            created_at=PAST,
            signature="sig",
            expires_at=PAST,
        )
        assert record.is_expired() is True

    def test_is_expired_with_future_date(self, genesis_record):
        assert genesis_record.is_expired() is False

    def test_is_expired_with_no_expiry(self):
        record = GenesisRecord(
            id="gen-no-exp",
            agent_id="agent-no-exp",
            authority_id="auth-no-exp",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=NOW,
            signature="sig",
            expires_at=None,
        )
        assert record.is_expired() is False

    def test_to_signing_payload(self, genesis_record):
        payload = genesis_record.to_signing_payload()
        assert payload["id"] == "gen-001"
        assert payload["agent_id"] == "agent-001"
        assert payload["authority_type"] == "organization"
        assert payload["created_at"] == genesis_record.created_at.isoformat()
        assert payload["expires_at"] == genesis_record.expires_at.isoformat()
        assert payload["metadata"] == {"department": "engineering"}

    def test_to_signing_payload_no_expiry(self):
        record = GenesisRecord(
            id="gen-np",
            agent_id="a",
            authority_id="b",
            authority_type=AuthorityType.HUMAN,
            created_at=NOW,
            signature="s",
        )
        payload = record.to_signing_payload()
        assert payload["expires_at"] is None


class TestCapabilityAttestation:
    """Test CapabilityAttestation fields and methods."""

    def test_required_fields(self, capability_attestation):
        assert capability_attestation.id == "cap-001"
        assert capability_attestation.capability == "analyze_data"
        assert capability_attestation.capability_type == CapabilityType.ACTION

    def test_is_expired_past(self):
        cap = CapabilityAttestation(
            id="cap-exp",
            capability="expired_cap",
            capability_type=CapabilityType.ACCESS,
            constraints=[],
            attester_id="auth",
            attested_at=PAST,
            signature="sig",
            expires_at=PAST,
        )
        assert cap.is_expired() is True

    def test_is_expired_future(self, capability_attestation):
        assert capability_attestation.is_expired() is False

    def test_is_expired_none(self):
        cap = CapabilityAttestation(
            id="cap-none",
            capability="no_expiry",
            capability_type=CapabilityType.DELEGATION,
            constraints=["c1"],
            attester_id="auth",
            attested_at=NOW,
            signature="sig",
            expires_at=None,
        )
        assert cap.is_expired() is False

    def test_to_signing_payload(self, capability_attestation):
        payload = capability_attestation.to_signing_payload()
        assert payload["id"] == "cap-001"
        assert payload["capability"] == "analyze_data"
        assert payload["capability_type"] == "action"
        assert payload["constraints"] == ["read_only"]
        assert payload["scope"] == {"tables": ["transactions"]}

    def test_to_signing_payload_constraints_sorted(self):
        cap = CapabilityAttestation(
            id="cap-sort",
            capability="test",
            capability_type=CapabilityType.ACTION,
            constraints=["z_constraint", "a_constraint", "m_constraint"],
            attester_id="auth",
            attested_at=NOW,
            signature="sig",
        )
        payload = cap.to_signing_payload()
        assert payload["constraints"] == [
            "a_constraint",
            "m_constraint",
            "z_constraint",
        ]


class TestDelegationRecord:
    """Test DelegationRecord fields and methods."""

    def test_required_fields(self, delegation_record):
        assert delegation_record.id == "del-001"
        assert delegation_record.delegator_id == "agent-001"
        assert delegation_record.delegatee_id == "agent-002"
        assert delegation_record.task_id == "task-001"

    def test_eatp_enhancement_defaults(self):
        dr = DelegationRecord(
            id="del-default",
            delegator_id="a",
            delegatee_id="b",
            task_id="t",
            capabilities_delegated=["cap"],
            constraint_subset=[],
            delegated_at=NOW,
            signature="s",
        )
        assert dr.human_origin is None
        assert dr.delegation_chain == []
        assert dr.delegation_depth == 0

    def test_is_expired_past(self):
        dr = DelegationRecord(
            id="del-exp",
            delegator_id="a",
            delegatee_id="b",
            task_id="t",
            capabilities_delegated=[],
            constraint_subset=[],
            delegated_at=PAST,
            signature="s",
            expires_at=PAST,
        )
        assert dr.is_expired() is True

    def test_is_expired_none(self, delegation_record):
        dr = DelegationRecord(
            id="del-ne",
            delegator_id="a",
            delegatee_id="b",
            task_id="t",
            capabilities_delegated=[],
            constraint_subset=[],
            delegated_at=NOW,
            signature="s",
            expires_at=None,
        )
        assert dr.is_expired() is False

    def test_to_signing_payload(self, delegation_record):
        payload = delegation_record.to_signing_payload()
        assert payload["id"] == "del-001"
        assert payload["delegator_id"] == "agent-001"
        assert payload["delegatee_id"] == "agent-002"
        assert payload["capabilities_delegated"] == ["analyze_data"]
        assert payload["constraint_subset"] == ["no_pii", "read_only"]
        assert payload["parent_delegation_id"] is None

    def test_to_dict_round_trip(self, delegation_record):
        d = delegation_record.to_dict()
        restored = DelegationRecord.from_dict(d)
        assert restored.id == delegation_record.id
        assert restored.delegator_id == delegation_record.delegator_id
        assert restored.delegatee_id == delegation_record.delegatee_id
        assert restored.task_id == delegation_record.task_id
        assert (
            restored.capabilities_delegated == delegation_record.capabilities_delegated
        )
        assert restored.constraint_subset == delegation_record.constraint_subset

    def test_from_dict_backward_compatible(self):
        """from_dict handles records without EATP fields gracefully."""
        data = {
            "id": "del-old",
            "delegator_id": "a",
            "delegatee_id": "b",
            "task_id": "t",
            "capabilities_delegated": ["cap"],
            "delegated_at": NOW.isoformat(),
            "signature": "sig",
        }
        dr = DelegationRecord.from_dict(data)
        assert dr.delegation_chain == []
        assert dr.delegation_depth == 0
        assert dr.human_origin is None


class TestConstraint:
    """Test Constraint dataclass."""

    def test_creation(self):
        c = Constraint(
            id="c-001",
            constraint_type=ConstraintType.RESOURCE_LIMIT,
            value=100,
            source="cap-001",
            priority=5,
        )
        assert c.id == "c-001"
        assert c.constraint_type == ConstraintType.RESOURCE_LIMIT
        assert c.value == 100
        assert c.source == "cap-001"
        assert c.priority == 5

    def test_default_priority(self):
        c = Constraint(
            id="c-002",
            constraint_type=ConstraintType.DATA_SCOPE,
            value="department_only",
            source="cap-002",
        )
        assert c.priority == 0


class TestConstraintEnvelope:
    """Test ConstraintEnvelope fields and methods."""

    def test_creation_auto_computed_at(self):
        env = ConstraintEnvelope(id="env-001", agent_id="agent-001")
        assert env.computed_at is not None
        assert env.constraint_hash == ""

    def test_auto_hash_computation(self):
        constraints = [
            Constraint(
                id="c-1",
                constraint_type=ConstraintType.RESOURCE_LIMIT,
                value=100,
                source="cap-001",
            ),
        ]
        env = ConstraintEnvelope(
            id="env-002",
            agent_id="agent-002",
            active_constraints=constraints,
        )
        assert env.constraint_hash != ""

    def test_get_constraints_by_type(self):
        constraints = [
            Constraint(
                id="c-1",
                constraint_type=ConstraintType.RESOURCE_LIMIT,
                value=100,
                source="s",
            ),
            Constraint(
                id="c-2",
                constraint_type=ConstraintType.DATA_SCOPE,
                value="dept",
                source="s",
            ),
            Constraint(
                id="c-3",
                constraint_type=ConstraintType.RESOURCE_LIMIT,
                value=50,
                source="s",
            ),
        ]
        env = ConstraintEnvelope(
            id="env-003", agent_id="a", active_constraints=constraints
        )
        resource_limits = env.get_constraints_by_type(ConstraintType.RESOURCE_LIMIT)
        assert len(resource_limits) == 2

    def test_is_valid_no_expiry(self):
        env = ConstraintEnvelope(id="env-004", agent_id="a")
        assert env.is_valid() is True

    def test_is_valid_past(self):
        env = ConstraintEnvelope(id="env-005", agent_id="a", valid_until=PAST)
        assert env.is_valid() is False

    def test_is_valid_future(self):
        env = ConstraintEnvelope(id="env-006", agent_id="a", valid_until=FUTURE)
        assert env.is_valid() is True

    def test_get_all_constraints(self):
        constraints = [
            Constraint(
                id="c-1",
                constraint_type=ConstraintType.RESOURCE_LIMIT,
                value=100,
                source="s",
            ),
            Constraint(
                id="c-2",
                constraint_type=ConstraintType.DATA_SCOPE,
                value="dept",
                source="s",
            ),
        ]
        env = ConstraintEnvelope(
            id="env-007", agent_id="a", active_constraints=constraints
        )
        all_c = env.get_all_constraints()
        assert "100" in all_c
        assert "dept" in all_c


class TestAuditAnchor:
    """Test AuditAnchor fields and methods."""

    def test_required_fields(self, audit_anchor):
        assert audit_anchor.id == "audit-001"
        assert audit_anchor.agent_id == "agent-001"
        assert audit_anchor.result == ActionResult.SUCCESS

    def test_to_signing_payload(self, audit_anchor):
        payload = audit_anchor.to_signing_payload()
        assert payload["id"] == "audit-001"
        assert payload["action"] == "analyze_data"
        assert payload["result"] == "success"
        assert payload["resource"] == "transactions_table"
        assert payload["context"] == {"rows_processed": 100}

    def test_to_dict_round_trip(self, audit_anchor):
        d = audit_anchor.to_dict()
        restored = AuditAnchor.from_dict(d)
        assert restored.id == audit_anchor.id
        assert restored.agent_id == audit_anchor.agent_id
        assert restored.action == audit_anchor.action
        assert restored.result == audit_anchor.result
        assert restored.resource == audit_anchor.resource
        assert restored.context == audit_anchor.context

    def test_from_dict_backward_compatible(self):
        data = {
            "id": "audit-old",
            "agent_id": "a",
            "action": "read",
            "timestamp": NOW.isoformat(),
            "trust_chain_hash": "hash123",
            "result": "success",
        }
        anchor = AuditAnchor.from_dict(data)
        assert anchor.human_origin is None
        assert anchor.resource is None
        assert anchor.context == {}


class TestVerificationResult:
    """Test VerificationResult dataclass."""

    def test_valid_field_name(self):
        """VerificationResult uses .valid, NOT .verified."""
        result = VerificationResult(valid=True)
        assert result.valid is True

    def test_defaults(self):
        result = VerificationResult(valid=False)
        assert result.level == VerificationLevel.STANDARD
        assert result.reason is None
        assert result.capability_used is None
        assert result.effective_constraints == []
        assert result.violations == []

    def test_full_construction(self):
        result = VerificationResult(
            valid=False,
            level=VerificationLevel.FULL,
            reason="expired",
            capability_used="analyze_data",
            effective_constraints=["read_only"],
            violations=[{"type": "expiry", "message": "chain expired"}],
        )
        assert result.valid is False
        assert result.level == VerificationLevel.FULL
        assert result.reason == "expired"
        assert len(result.violations) == 1


class TestTrustLineageChain:
    """Test TrustLineageChain methods."""

    def test_auto_constraint_envelope(self, genesis_record):
        chain = TrustLineageChain(genesis=genesis_record)
        assert chain.constraint_envelope is not None
        assert chain.constraint_envelope.agent_id == "agent-001"

    def test_hash_deterministic(self, trust_chain):
        h1 = trust_chain.hash()
        h2 = trust_chain.hash()
        assert h1 == h2
        assert len(h1) == 64

    def test_hash_with_previous_hash(self, trust_chain):
        h_without = trust_chain.hash()
        h_with = trust_chain.hash(previous_hash="prev_abc123")
        assert h_without != h_with

    def test_is_expired_genesis_expired(self):
        genesis = GenesisRecord(
            id="gen-exp",
            agent_id="a",
            authority_id="auth",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=PAST,
            signature="sig",
            expires_at=PAST,
        )
        chain = TrustLineageChain(genesis=genesis)
        assert chain.is_expired() is True

    def test_is_expired_all_capabilities_expired(self):
        genesis = GenesisRecord(
            id="gen-ok",
            agent_id="a",
            authority_id="auth",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=NOW,
            signature="sig",
        )
        expired_cap = CapabilityAttestation(
            id="cap-exp",
            capability="test",
            capability_type=CapabilityType.ACTION,
            constraints=[],
            attester_id="auth",
            attested_at=PAST,
            signature="sig",
            expires_at=PAST,
        )
        chain = TrustLineageChain(genesis=genesis, capabilities=[expired_cap])
        assert chain.is_expired() is True

    def test_is_expired_false_when_some_capabilities_valid(self):
        genesis = GenesisRecord(
            id="gen-ok",
            agent_id="a",
            authority_id="auth",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=NOW,
            signature="sig",
        )
        valid_cap = CapabilityAttestation(
            id="cap-valid",
            capability="test",
            capability_type=CapabilityType.ACTION,
            constraints=[],
            attester_id="auth",
            attested_at=NOW,
            signature="sig",
            expires_at=FUTURE,
        )
        expired_cap = CapabilityAttestation(
            id="cap-exp",
            capability="old",
            capability_type=CapabilityType.ACTION,
            constraints=[],
            attester_id="auth",
            attested_at=PAST,
            signature="sig",
            expires_at=PAST,
        )
        chain = TrustLineageChain(
            genesis=genesis, capabilities=[valid_cap, expired_cap]
        )
        assert chain.is_expired() is False

    def test_has_capability(self, trust_chain):
        assert trust_chain.has_capability("analyze_data") is True
        assert trust_chain.has_capability("nonexistent_cap") is False

    def test_has_capability_ignores_expired(self):
        genesis = GenesisRecord(
            id="gen-hc",
            agent_id="a",
            authority_id="auth",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=NOW,
            signature="sig",
        )
        expired_cap = CapabilityAttestation(
            id="cap-hc-exp",
            capability="stale_cap",
            capability_type=CapabilityType.ACTION,
            constraints=[],
            attester_id="auth",
            attested_at=PAST,
            signature="sig",
            expires_at=PAST,
        )
        chain = TrustLineageChain(genesis=genesis, capabilities=[expired_cap])
        assert chain.has_capability("stale_cap") is False

    def test_verify_basic_valid(self, trust_chain):
        result = trust_chain.verify_basic()
        assert result.valid is True
        assert result.level == VerificationLevel.QUICK

    def test_verify_basic_expired(self):
        genesis = GenesisRecord(
            id="gen-vb-exp",
            agent_id="a",
            authority_id="auth",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=PAST,
            signature="sig",
            expires_at=PAST,
        )
        chain = TrustLineageChain(genesis=genesis)
        result = chain.verify_basic()
        assert result.valid is False
        assert "expired" in result.reason.lower()

    def test_get_delegation_chain_empty(self, genesis_record):
        chain = TrustLineageChain(genesis=genesis_record)
        assert chain.get_delegation_chain() == []

    def test_get_delegation_chain_ordered(self, genesis_record):
        d1 = DelegationRecord(
            id="del-root",
            delegator_id="a",
            delegatee_id="b",
            task_id="t",
            capabilities_delegated=["c"],
            constraint_subset=[],
            delegated_at=NOW,
            signature="s",
        )
        d2 = DelegationRecord(
            id="del-leaf",
            delegator_id="b",
            delegatee_id="c",
            task_id="t",
            capabilities_delegated=["c"],
            constraint_subset=[],
            delegated_at=NOW,
            signature="s",
            parent_delegation_id="del-root",
        )
        chain = TrustLineageChain(genesis=genesis_record, delegations=[d1, d2])
        ordered = chain.get_delegation_chain()
        assert ordered[0].id == "del-root"
        assert ordered[1].id == "del-leaf"

    def test_get_delegation_chain_cycle_detection(self, genesis_record):
        d1 = DelegationRecord(
            id="del-a",
            delegator_id="a",
            delegatee_id="b",
            task_id="t",
            capabilities_delegated=["c"],
            constraint_subset=[],
            delegated_at=NOW,
            signature="s",
            parent_delegation_id="del-b",
        )
        d2 = DelegationRecord(
            id="del-b",
            delegator_id="b",
            delegatee_id="a",
            task_id="t",
            capabilities_delegated=["c"],
            constraint_subset=[],
            delegated_at=NOW,
            signature="s",
            parent_delegation_id="del-a",
        )
        chain = TrustLineageChain(genesis=genesis_record, delegations=[d1, d2])
        with pytest.raises(DelegationCycleError):
            chain.get_delegation_chain()

    def test_get_effective_constraints(self, trust_chain):
        constraints = trust_chain.get_effective_constraints("analyze_data")
        assert "read_only" in constraints

    def test_get_active_delegations(self, genesis_record):
        active = DelegationRecord(
            id="del-active",
            delegator_id="a",
            delegatee_id="b",
            task_id="t",
            capabilities_delegated=["c"],
            constraint_subset=[],
            delegated_at=NOW,
            signature="s",
            expires_at=FUTURE,
        )
        expired = DelegationRecord(
            id="del-expired",
            delegator_id="a",
            delegatee_id="c",
            task_id="t",
            capabilities_delegated=["c"],
            constraint_subset=[],
            delegated_at=PAST,
            signature="s",
            expires_at=PAST,
        )
        chain = TrustLineageChain(genesis=genesis_record, delegations=[active, expired])
        active_dels = chain.get_active_delegations()
        assert len(active_dels) == 1
        assert active_dels[0].id == "del-active"

    def test_to_dict_and_from_dict_round_trip(self, trust_chain):
        d = trust_chain.to_dict()
        restored = TrustLineageChain.from_dict(d)
        assert restored.genesis.id == trust_chain.genesis.id
        assert restored.genesis.agent_id == trust_chain.genesis.agent_id
        assert len(restored.capabilities) == len(trust_chain.capabilities)
        assert len(restored.delegations) == len(trust_chain.delegations)
        assert restored.hash() == trust_chain.hash()


# ===========================================================================
# Section 2: Crypto Operations Tests (20+ tests)
# ===========================================================================


class TestKeypairGeneration:
    """Test Ed25519 keypair generation."""

    def test_generates_two_strings(self):
        private_key, public_key = generate_keypair()
        assert isinstance(private_key, str)
        assert isinstance(public_key, str)

    def test_private_key_first(self):
        """generate_keypair returns (private, public) order."""
        private_key, public_key = generate_keypair()
        assert len(private_key) > 0
        assert len(public_key) > 0
        assert private_key != public_key

    def test_unique_keys_each_call(self):
        kp1 = generate_keypair()
        kp2 = generate_keypair()
        assert kp1[0] != kp2[0]
        assert kp1[1] != kp2[1]

    def test_keys_are_base64(self, keypair):
        import base64

        private_key, public_key = keypair
        base64.b64decode(private_key)
        base64.b64decode(public_key)


class TestSignAndVerify:
    """Test sign and verify_signature cycle."""

    def test_sign_returns_string(self, keypair):
        private_key, _ = keypair
        sig = sign("hello", private_key)
        assert isinstance(sig, str)
        assert len(sig) > 0

    def test_verify_valid_string_payload(self, keypair):
        private_key, public_key = keypair
        sig = sign("test message", private_key)
        assert verify_signature("test message", sig, public_key) is True

    def test_verify_dict_payload(self, keypair):
        private_key, public_key = keypair
        payload = {"action": "test", "value": 42}
        sig = sign(payload, private_key)
        assert verify_signature(payload, sig, public_key) is True

    def test_verify_bytes_payload(self, keypair):
        private_key, public_key = keypair
        payload = b"binary data"
        sig = sign(payload, private_key)
        assert verify_signature(payload, sig, public_key) is True

    def test_tampered_message_rejected(self, keypair):
        private_key, public_key = keypair
        sig = sign("original", private_key)
        assert verify_signature("tampered", sig, public_key) is False

    def test_wrong_key_rejected(self):
        priv1, pub1 = generate_keypair()
        _, pub2 = generate_keypair()
        sig = sign("data", priv1)
        assert verify_signature("data", sig, pub2) is False

    def test_invalid_private_key_raises(self):
        with pytest.raises(ValueError, match="Invalid private key"):
            sign("data", "not-a-valid-key!!!")

    def test_sign_verify_with_genesis_payload(self, keypair, genesis_record):
        private_key, public_key = keypair
        payload = genesis_record.to_signing_payload()
        sig = sign(payload, private_key)
        assert verify_signature(payload, sig, public_key) is True


class TestSerializeForSigning:
    """Test deterministic serialization."""

    def test_sorted_keys(self):
        result = serialize_for_signing({"b": 2, "a": 1})
        assert result == '{"a":1,"b":2}'

    def test_no_spaces(self):
        result = serialize_for_signing({"key": "value"})
        assert " " not in result

    def test_deterministic_across_calls(self):
        obj = {"x": [1, 2, 3], "a": {"nested": True}}
        r1 = serialize_for_signing(obj)
        r2 = serialize_for_signing(obj)
        assert r1 == r2

    def test_datetime_serialized_as_isoformat(self):
        dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = serialize_for_signing({"ts": dt})
        assert dt.isoformat() in result

    def test_enum_serialized_as_value(self):
        result = serialize_for_signing({"type": AuthorityType.ORGANIZATION})
        assert '"organization"' in result

    def test_bytes_serialized_as_base64(self):
        import base64

        data = b"\x00\x01\x02"
        result = serialize_for_signing({"data": data})
        expected_b64 = base64.b64encode(data).decode("utf-8")
        assert expected_b64 in result


class TestHashChain:
    """Test hash_chain for different input types."""

    def test_string_input(self):
        result = hash_chain("hello")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_dict_input(self):
        result = hash_chain({"key": "value"})
        assert len(result) == 64

    def test_bytes_input(self):
        result = hash_chain(b"\x00\x01\x02")
        assert len(result) == 64

    def test_same_input_same_hash(self):
        h1 = hash_chain("deterministic")
        h2 = hash_chain("deterministic")
        assert h1 == h2

    def test_different_input_different_hash(self):
        h1 = hash_chain("input_a")
        h2 = hash_chain("input_b")
        assert h1 != h2

    def test_dict_hash_is_deterministic_regardless_of_key_order(self):
        h1 = hash_chain({"b": 2, "a": 1})
        h2 = hash_chain({"a": 1, "b": 2})
        assert h1 == h2


class TestHashTrustChainState:
    """Test hash_trust_chain_state and salted variant."""

    def test_deterministic(self):
        h1 = hash_trust_chain_state("gen-001", ["cap-001"], ["del-001"], "hash")
        h2 = hash_trust_chain_state("gen-001", ["cap-001"], ["del-001"], "hash")
        assert h1 == h2

    def test_different_inputs_different_hash(self):
        h1 = hash_trust_chain_state("gen-001", ["cap-001"], [], "hash")
        h2 = hash_trust_chain_state("gen-002", ["cap-001"], [], "hash")
        assert h1 != h2

    def test_capability_ids_sorted(self):
        h1 = hash_trust_chain_state("gen-001", ["cap-002", "cap-001"], [], "hash")
        h2 = hash_trust_chain_state("gen-001", ["cap-001", "cap-002"], [], "hash")
        assert h1 == h2

    def test_salted_returns_tuple(self):
        result = hash_trust_chain_state_salted("gen-001", ["cap-001"], [], "hash")
        assert isinstance(result, tuple)
        assert len(result) == 2
        hash_hex, salt_b64 = result
        assert len(hash_hex) == 64
        assert isinstance(salt_b64, str)

    def test_salted_with_explicit_salt(self):
        h1, s1 = hash_trust_chain_state_salted(
            "gen-001", [], [], "hash", salt="fixed_salt"
        )
        h2, s2 = hash_trust_chain_state_salted(
            "gen-001", [], [], "hash", salt="fixed_salt"
        )
        assert h1 == h2
        assert s1 == s2 == "fixed_salt"

    def test_salted_different_salts_different_hashes(self):
        h1, _ = hash_trust_chain_state_salted("gen-001", [], [], "hash", salt="salt_a")
        h2, _ = hash_trust_chain_state_salted("gen-001", [], [], "hash", salt="salt_b")
        assert h1 != h2

    def test_salted_with_previous_state_hash(self):
        h1, _ = hash_trust_chain_state_salted(
            "gen-001", [], [], "hash", previous_state_hash="prev_123", salt="s"
        )
        h2, _ = hash_trust_chain_state_salted(
            "gen-001", [], [], "hash", previous_state_hash=None, salt="s"
        )
        assert h1 != h2


class TestGenerateSalt:
    """Test salt generation."""

    def test_returns_bytes(self):
        salt = generate_salt()
        assert isinstance(salt, bytes)

    def test_length_32_bytes(self):
        salt = generate_salt()
        assert len(salt) == 32

    def test_unique_each_call(self):
        s1 = generate_salt()
        s2 = generate_salt()
        assert s1 != s2


class TestDeriveKeyWithSalt:
    """Test PBKDF2 key derivation."""

    def test_returns_tuple(self):
        salt = generate_salt()
        result = derive_key_with_salt(b"master_key", salt)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_derived_key_length(self):
        salt = generate_salt()
        key, _ = derive_key_with_salt(b"master", salt, key_length=32)
        assert len(key) == 32

    def test_same_inputs_same_output(self):
        salt = generate_salt()
        k1, _ = derive_key_with_salt(b"master", salt)
        k2, _ = derive_key_with_salt(b"master", salt)
        assert k1 == k2

    def test_different_salts_different_keys(self):
        k1, _ = derive_key_with_salt(b"master", generate_salt())
        k2, _ = derive_key_with_salt(b"master", generate_salt())
        assert k1 != k2


# ===========================================================================
# Section 3: Merkle Tree Tests
# ===========================================================================


class TestMerkleNode:
    """Test MerkleNode basics."""

    def test_leaf_node(self):
        node = MerkleNode(hash="abc123", data_index=0)
        assert node.is_leaf() is True

    def test_internal_node(self):
        node = MerkleNode(hash="abc123")
        assert node.is_leaf() is False


class TestMerkleTree:
    """Test MerkleTree build, proof, and verify."""

    def test_empty_tree(self):
        tree = MerkleTree()
        assert tree.root_hash is None
        assert tree.leaf_count == 0

    def test_single_leaf(self):
        tree = MerkleTree(["hash_a"])
        assert tree.root_hash == "hash_a"
        assert tree.leaf_count == 1

    def test_two_leaves(self):
        tree = MerkleTree(["hash_a", "hash_b"])
        assert tree.root_hash is not None
        expected = hashlib.sha256(("hash_a" + "hash_b").encode("utf-8")).hexdigest()
        assert tree.root_hash == expected

    def test_four_leaves(self):
        leaves = ["h1", "h2", "h3", "h4"]
        tree = MerkleTree(leaves)
        assert tree.leaf_count == 4
        assert tree.root_hash is not None

    def test_odd_leaves_duplicates_last(self):
        tree = MerkleTree(["h1", "h2", "h3"])
        assert tree.root_hash is not None
        assert tree.leaf_count == 3

    def test_add_leaf_rebuilds(self):
        tree = MerkleTree(["h1", "h2"])
        old_root = tree.root_hash
        tree.add_leaf("h3")
        assert tree.leaf_count == 3
        assert tree.root_hash != old_root

    def test_get_leaf(self):
        tree = MerkleTree(["h1", "h2", "h3"])
        assert tree.get_leaf(0) == "h1"
        assert tree.get_leaf(2) == "h3"

    def test_get_leaf_out_of_range(self):
        tree = MerkleTree(["h1"])
        with pytest.raises(IndexError):
            tree.get_leaf(5)

    def test_generate_proof(self):
        tree = MerkleTree(["h1", "h2", "h3", "h4"])
        proof = tree.generate_proof(1)
        assert proof is not None
        assert proof.leaf_hash == "h2"
        assert proof.leaf_index == 1
        assert proof.root_hash == tree.root_hash
        assert proof.tree_size == 4

    def test_generate_proof_empty_tree(self):
        tree = MerkleTree()
        proof = tree.generate_proof(0)
        assert proof is None

    def test_generate_proof_out_of_range(self):
        tree = MerkleTree(["h1"])
        with pytest.raises(IndexError):
            tree.generate_proof(5)

    def test_verify_proof_valid(self):
        tree = MerkleTree(["h1", "h2", "h3", "h4"])
        for i in range(4):
            proof = tree.generate_proof(i)
            assert tree.verify_proof(proof) is True

    def test_verify_proof_none_returns_false(self):
        tree = MerkleTree(["h1"])
        assert tree.verify_proof(None) is False

    def test_verify_proof_invalidated_by_tree_change(self):
        tree = MerkleTree(["h1", "h2"])
        proof = tree.generate_proof(0)
        tree.add_leaf("h3")
        assert tree.verify_proof(proof) is False

    def test_to_dict_round_trip(self):
        leaves = ["h1", "h2", "h3", "h4"]
        tree = MerkleTree(leaves)
        d = tree.to_dict()
        restored = MerkleTree.from_dict(d)
        assert restored.root_hash == tree.root_hash
        assert restored.leaf_count == tree.leaf_count

    def test_to_dict_contains_version(self):
        tree = MerkleTree(["h1"])
        d = tree.to_dict()
        assert d["version"] == "1.0"


class TestMerkleProof:
    """Test MerkleProof serialization."""

    def test_to_dict_from_dict_round_trip(self):
        proof = MerkleProof(
            leaf_hash="abc",
            leaf_index=2,
            proof_hashes=[("hash1", "left"), ("hash2", "right")],
            root_hash="root123",
            tree_size=4,
        )
        d = proof.to_dict()
        restored = MerkleProof.from_dict(d)
        assert restored.leaf_hash == proof.leaf_hash
        assert restored.leaf_index == proof.leaf_index
        assert restored.root_hash == proof.root_hash
        assert restored.tree_size == proof.tree_size
        assert restored.proof_hashes == proof.proof_hashes


class TestVerifyMerkleProofStandalone:
    """Test the standalone verify_merkle_proof function."""

    def test_valid_proof(self):
        tree = MerkleTree(["h1", "h2", "h3", "h4"])
        proof = tree.generate_proof(2)
        assert verify_merkle_proof(proof.leaf_hash, proof) is True

    def test_wrong_leaf_hash(self):
        tree = MerkleTree(["h1", "h2", "h3", "h4"])
        proof = tree.generate_proof(0)
        assert verify_merkle_proof("wrong_hash", proof) is False

    def test_empty_root_hash(self):
        proof = MerkleProof(
            leaf_hash="abc",
            leaf_index=0,
            proof_hashes=[],
            root_hash="",
            tree_size=0,
        )
        assert verify_merkle_proof("abc", proof) is False


class TestComputeMerkleRoot:
    """Test compute_merkle_root utility."""

    def test_empty_list(self):
        assert compute_merkle_root([]) is None

    def test_single_hash(self):
        assert compute_merkle_root(["abc"]) == "abc"

    def test_matches_tree(self):
        leaves = ["h1", "h2", "h3"]
        root = compute_merkle_root(leaves)
        tree = MerkleTree(leaves)
        assert root == tree.root_hash


class TestGetProofLength:
    """Test get_proof_length utility."""

    def test_single_leaf(self):
        assert get_proof_length(1) == 0

    def test_zero_leaves(self):
        assert get_proof_length(0) == 0

    def test_power_of_two(self):
        assert get_proof_length(4) == 2
        assert get_proof_length(8) == 3

    def test_non_power_of_two(self):
        assert get_proof_length(3) == 2
        assert get_proof_length(5) == 3


# ===========================================================================
# Section 4: LinkedHashChain Tests
# ===========================================================================


class TestLinkedHashChain:
    """Test LinkedHashChain tamper detection."""

    def test_add_hash_returns_linked_hash(self):
        chain = LinkedHashChain()
        linked = chain.add_hash("agent-1", "state_hash_abc")
        assert isinstance(linked, str)
        assert len(linked) == 64

    def test_chain_length(self):
        chain = LinkedHashChain()
        chain.add_hash("a1", "h1")
        chain.add_hash("a2", "h2")
        assert len(chain) == 2

    def test_entries_property(self):
        chain = LinkedHashChain()
        chain.add_hash("a1", "h1")
        entries = chain.entries
        assert len(entries) == 1
        assert entries[0].agent_id == "a1"

    def test_verify_integrity_empty_chain(self):
        chain = LinkedHashChain()
        valid, break_idx = chain.verify_integrity()
        assert valid is True
        assert break_idx is None

    def test_verify_integrity_valid_chain(self):
        chain = LinkedHashChain()
        chain.add_hash("a1", "h1")
        chain.add_hash("a2", "h2")
        valid, break_idx = chain.verify_integrity()
        assert valid is True
        assert break_idx is None

    def test_verify_integrity_strict_raises(self):
        chain = LinkedHashChain()
        chain.add_hash("a1", "h1")
        with pytest.raises(ValueError, match="verify_integrity.*strict=True"):
            chain.verify_integrity(strict=True)

    def test_verify_chain_linkage_valid(self):
        chain = LinkedHashChain()
        chain.add_hash("a1", "hash_1")
        chain.add_hash("a2", "hash_2")
        valid, break_idx = chain.verify_chain_linkage(["hash_1", "hash_2"])
        assert valid is True
        assert break_idx is None

    def test_verify_chain_linkage_tampered(self):
        chain = LinkedHashChain()
        chain.add_hash("a1", "hash_1")
        chain.add_hash("a2", "hash_2")
        valid, break_idx = chain.verify_chain_linkage(["hash_1", "TAMPERED"])
        assert valid is False
        assert break_idx == 1

    def test_verify_chain_linkage_length_mismatch(self):
        chain = LinkedHashChain()
        chain.add_hash("a1", "h1")
        valid, break_idx = chain.verify_chain_linkage(["h1", "h2"])
        assert valid is False

    def test_detect_tampering_valid(self):
        chain = LinkedHashChain()
        linked = chain.add_hash("agent-1", "state_hash")
        assert chain.detect_tampering("agent-1", linked) is False

    def test_detect_tampering_invalid(self):
        chain = LinkedHashChain()
        chain.add_hash("agent-1", "state_hash")
        assert chain.detect_tampering("agent-1", "wrong_hash") is True

    def test_detect_tampering_agent_not_found(self):
        chain = LinkedHashChain()
        chain.add_hash("agent-1", "h")
        assert chain.detect_tampering("agent-999", "any_hash") is True

    def test_get_entry(self):
        chain = LinkedHashChain()
        chain.add_hash("agent-1", "h1")
        entry = chain.get_entry("agent-1")
        assert entry is not None
        assert entry.agent_id == "agent-1"

    def test_get_entry_not_found(self):
        chain = LinkedHashChain()
        assert chain.get_entry("nonexistent") is None

    def test_get_previous_hash(self):
        chain = LinkedHashChain()
        chain.add_hash("a1", "h1")
        chain.add_hash("a2", "h2")
        prev = chain.get_previous_hash("a2")
        assert prev is not None
        first_entry = chain.get_entry("a1")
        assert prev == first_entry.hash

    def test_get_previous_hash_first_entry(self):
        chain = LinkedHashChain()
        chain.add_hash("a1", "h1")
        assert chain.get_previous_hash("a1") is None

    def test_to_dict_round_trip(self):
        chain = LinkedHashChain()
        chain.add_hash("a1", "h1")
        chain.add_hash("a2", "h2")
        d = chain.to_dict()
        assert d["version"] == "1.0"
        assert d["chain_type"] == "linked_hash_chain"
        assert len(d["entries"]) == 2

        restored = LinkedHashChain.from_dict(d)
        assert len(restored) == 2
        assert restored.entries[0].agent_id == "a1"
        assert restored.entries[1].agent_id == "a2"


# ===========================================================================
# Section 5: Exception Hierarchy Tests
# ===========================================================================


class TestExceptionHierarchy:
    """Test exception hierarchy and attributes."""

    def test_trust_error_base(self):
        err = TrustError("base error")
        assert str(err) == "base error"
        assert err.message == "base error"
        assert err.details == {}

    def test_trust_error_with_details(self):
        err = TrustError("error", details={"key": "val"})
        assert "Details" in str(err)
        assert err.details == {"key": "val"}

    def test_authority_not_found(self):
        err = AuthorityNotFoundError("auth-123")
        assert err.authority_id == "auth-123"
        assert "auth-123" in str(err)
        assert isinstance(err, TrustError)

    def test_trust_chain_not_found(self):
        err = TrustChainNotFoundError("agent-42")
        assert err.agent_id == "agent-42"
        assert isinstance(err, TrustError)

    def test_invalid_trust_chain(self):
        err = InvalidTrustChainError("agent-1", "bad genesis", violations=["v1", "v2"])
        assert err.agent_id == "agent-1"
        assert err.reason == "bad genesis"
        assert err.violations == ["v1", "v2"]

    def test_capability_not_found(self):
        err = CapabilityNotFoundError("agent-1", "read_data")
        assert err.agent_id == "agent-1"
        assert err.capability == "read_data"

    def test_constraint_violation(self):
        err = ConstraintViolationError("limit exceeded", agent_id="a", action="write")
        assert err.agent_id == "a"
        assert err.action == "write"

    def test_delegation_error(self):
        err = DelegationError("failed", delegator_id="a", delegatee_id="b")
        assert err.delegator_id == "a"
        assert err.delegatee_id == "b"
        assert isinstance(err, TrustError)

    def test_delegation_cycle_error(self):
        err = DelegationCycleError(["a", "b", "a"])
        assert err.cycle_path == ["a", "b", "a"]
        assert "a -> b -> a" in str(err)
        assert isinstance(err, DelegationError)

    def test_invalid_signature_error(self):
        err = InvalidSignatureError("bad sig", record_type="genesis", record_id="gen-1")
        assert err.record_type == "genesis"
        assert err.record_id == "gen-1"
        assert isinstance(err, TrustError)

    def test_verification_failed_error(self):
        err = VerificationFailedError("agent-1", "delete", "no permission")
        assert err.agent_id == "agent-1"
        assert err.action == "delete"
        assert err.reason == "no permission"

    def test_delegation_expired_error(self):
        err = DelegationExpiredError("del-1", "2024-01-01T00:00:00")
        assert err.delegation_id == "del-1"
        assert err.expired_at == "2024-01-01T00:00:00"
        assert isinstance(err, DelegationError)

    def test_agent_already_established(self):
        err = AgentAlreadyEstablishedError("agent-1")
        assert err.agent_id == "agent-1"

    def test_trust_store_error_hierarchy(self):
        base = TrustStoreError("store error")
        assert isinstance(base, TrustError)

    def test_trust_chain_invalid_error(self):
        err = TrustChainInvalidError("invalid chain", agent_id="agent-1")
        assert err.agent_id == "agent-1"
        assert isinstance(err, TrustStoreError)

    def test_trust_store_database_error(self):
        err = TrustStoreDatabaseError("connection failed", operation="insert")
        assert err.operation == "insert"
        assert isinstance(err, TrustStoreError)


# ===========================================================================
# Section 6: Serialization Round-Trip Tests (15+ tests)
# ===========================================================================


class TestSerializationRoundTrips:
    """Test JSON round-trips for all models."""

    def test_genesis_record_signing_payload_is_json_serializable(self, genesis_record):
        payload = genesis_record.to_signing_payload()
        json_str = json.dumps(payload)
        restored = json.loads(json_str)
        assert restored["id"] == "gen-001"

    def test_capability_signing_payload_is_json_serializable(
        self, capability_attestation
    ):
        payload = capability_attestation.to_signing_payload()
        json_str = json.dumps(payload)
        restored = json.loads(json_str)
        assert restored["capability"] == "analyze_data"

    def test_delegation_signing_payload_is_json_serializable(self, delegation_record):
        payload = delegation_record.to_signing_payload()
        json_str = json.dumps(payload)
        restored = json.loads(json_str)
        assert restored["delegator_id"] == "agent-001"

    def test_audit_anchor_signing_payload_is_json_serializable(self, audit_anchor):
        payload = audit_anchor.to_signing_payload()
        json_str = json.dumps(payload)
        restored = json.loads(json_str)
        assert restored["result"] == "success"

    def test_trust_lineage_chain_json_round_trip(self, trust_chain):
        d = trust_chain.to_dict()
        json_str = json.dumps(d)
        restored_dict = json.loads(json_str)
        restored_chain = TrustLineageChain.from_dict(restored_dict)
        assert restored_chain.genesis.id == trust_chain.genesis.id

    def test_linked_hash_chain_json_round_trip(self):
        chain = LinkedHashChain()
        chain.add_hash("a1", "h1")
        chain.add_hash("a2", "h2")
        d = chain.to_dict()
        json_str = json.dumps(d)
        restored_dict = json.loads(json_str)
        restored = LinkedHashChain.from_dict(restored_dict)
        assert len(restored) == 2

    def test_merkle_tree_json_round_trip(self):
        tree = MerkleTree(["h1", "h2", "h3", "h4"])
        d = tree.to_dict()
        json_str = json.dumps(d)
        restored_dict = json.loads(json_str)
        restored = MerkleTree.from_dict(restored_dict)
        assert restored.root_hash == tree.root_hash

    def test_merkle_proof_json_round_trip(self):
        tree = MerkleTree(["h1", "h2", "h3", "h4"])
        proof = tree.generate_proof(2)
        d = proof.to_dict()
        json_str = json.dumps(d)
        restored_dict = json.loads(json_str)
        restored_proof = MerkleProof.from_dict(restored_dict)
        assert verify_merkle_proof(restored_proof.leaf_hash, restored_proof) is True

    def test_verification_result_fields_json(self):
        vr = VerificationResult(
            valid=True,
            level=VerificationLevel.FULL,
            reason="ok",
            capability_used="read",
            effective_constraints=["ro"],
            violations=[],
        )
        d = {
            "valid": vr.valid,
            "level": vr.level.value,
            "reason": vr.reason,
            "capability_used": vr.capability_used,
            "effective_constraints": vr.effective_constraints,
            "violations": vr.violations,
        }
        json_str = json.dumps(d)
        restored = json.loads(json_str)
        assert restored["valid"] is True
        assert restored["level"] == "full"

    def test_delegation_record_from_dict_with_optional_fields(self):
        """Round-trip preserves optional fields like parent_delegation_id."""
        dr = DelegationRecord(
            id="del-opt",
            delegator_id="a",
            delegatee_id="b",
            task_id="t",
            capabilities_delegated=["cap"],
            constraint_subset=["c1", "c2"],
            delegated_at=NOW,
            signature="sig",
            expires_at=FUTURE,
            parent_delegation_id="del-parent",
            delegation_chain=["human", "agent-a", "agent-b"],
            delegation_depth=2,
        )
        d = dr.to_dict()
        json_str = json.dumps(d)
        restored_dict = json.loads(json_str)
        restored = DelegationRecord.from_dict(restored_dict)
        assert restored.parent_delegation_id == "del-parent"
        assert restored.delegation_chain == ["human", "agent-a", "agent-b"]
        assert restored.delegation_depth == 2

    def test_audit_anchor_from_dict_preserves_all_fields(self, audit_anchor):
        d = audit_anchor.to_dict()
        json_str = json.dumps(d)
        restored_dict = json.loads(json_str)
        restored = AuditAnchor.from_dict(restored_dict)
        assert restored.resource == "transactions_table"
        assert restored.parent_anchor_id is None
        assert restored.context == {"rows_processed": 100}

    def test_trust_chain_from_dict_with_constraints(self):
        genesis = GenesisRecord(
            id="gen-c",
            agent_id="a",
            authority_id="auth",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=NOW,
            signature="sig",
        )
        constraint = Constraint(
            id="c-1",
            constraint_type=ConstraintType.RESOURCE_LIMIT,
            value=100,
            source="cap-001",
            priority=5,
        )
        env = ConstraintEnvelope(
            id="env-c",
            agent_id="a",
            active_constraints=[constraint],
        )
        chain = TrustLineageChain(genesis=genesis, constraint_envelope=env)
        d = chain.to_dict()
        json_str = json.dumps(d)
        restored_dict = json.loads(json_str)
        restored = TrustLineageChain.from_dict(restored_dict)
        assert restored.constraint_envelope is not None
        assert len(restored.constraint_envelope.active_constraints) == 1
        rc = restored.constraint_envelope.active_constraints[0]
        assert rc.id == "c-1"
        assert rc.constraint_type == ConstraintType.RESOURCE_LIMIT
        assert rc.priority == 5

    def test_serialize_for_signing_used_in_sign_verify(self, keypair):
        """Demonstrates that serialize_for_signing produces consistent bytes
        that can be signed and verified deterministically."""
        private_key, public_key = keypair
        payload = {"z": 1, "a": 2, "m": [3, 2, 1]}
        sig = sign(payload, private_key)
        assert verify_signature(payload, sig, public_key) is True
        serialized = serialize_for_signing(payload)
        assert verify_signature(serialized, sig, public_key) is True

    def test_constraint_envelope_hash_deterministic(self):
        constraints = [
            Constraint(
                id="c-1",
                constraint_type=ConstraintType.RESOURCE_LIMIT,
                value=100,
                source="s",
            ),
            Constraint(
                id="c-2",
                constraint_type=ConstraintType.DATA_SCOPE,
                value="dept",
                source="s",
            ),
        ]
        env1 = ConstraintEnvelope(
            id="env", agent_id="a", active_constraints=constraints
        )
        env2 = ConstraintEnvelope(
            id="env", agent_id="a", active_constraints=constraints
        )
        assert env1.constraint_hash == env2.constraint_hash
        assert len(env1.constraint_hash) == 64

    def test_empty_merkle_tree_dict_round_trip(self):
        tree = MerkleTree()
        d = tree.to_dict()
        restored = MerkleTree.from_dict(d)
        assert restored.root_hash is None
        assert restored.leaf_count == 0
