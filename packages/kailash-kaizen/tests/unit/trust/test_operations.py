"""
Unit tests for TrustOperations.

Tests cover:
- TrustKeyManager
- CapabilityRequest dataclass
- Capability matching logic
- Constraint evaluation logic
- Verification levels

Note: Integration tests with real database are in tests/integration/trust/
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

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
from kaizen.trust.crypto import NACL_AVAILABLE, generate_keypair
from kaizen.trust.operations import (
    CapabilityRequest,
    ConstraintEvaluationResult,
    TrustKeyManager,
    TrustOperations,
)

# Skip crypto tests if PyNaCl not available
pytestmark = pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not installed")


class TestTrustKeyManager:
    """Tests for TrustKeyManager."""

    def test_key_manager_creation(self):
        """TrustKeyManager initializes with empty keys."""
        km = TrustKeyManager()
        assert km._keys == {}

    def test_register_key(self):
        """Can register a key."""
        km = TrustKeyManager()
        private_key, _ = generate_keypair()
        km.register_key("test-key", private_key)

        assert "test-key" in km._keys
        assert km._keys["test-key"] == private_key

    def test_get_key_existing(self):
        """Can get an existing key."""
        km = TrustKeyManager()
        private_key, _ = generate_keypair()
        km.register_key("test-key", private_key)

        assert km.get_key("test-key") == private_key

    def test_get_key_nonexistent(self):
        """Getting nonexistent key returns None."""
        km = TrustKeyManager()
        assert km.get_key("nonexistent") is None

    @pytest.mark.asyncio
    async def test_sign(self):
        """Can sign a payload."""
        km = TrustKeyManager()
        private_key, public_key = generate_keypair()
        km.register_key("test-key", private_key)

        signature = await km.sign("test payload", "test-key")

        assert isinstance(signature, str)
        assert len(signature) > 0

    @pytest.mark.asyncio
    async def test_sign_nonexistent_key_raises(self):
        """Signing with nonexistent key raises ValueError."""
        km = TrustKeyManager()

        with pytest.raises(ValueError, match="Key not found"):
            await km.sign("test payload", "nonexistent")

    @pytest.mark.asyncio
    async def test_verify(self):
        """Can verify a signature."""
        km = TrustKeyManager()
        private_key, public_key = generate_keypair()
        km.register_key("test-key", private_key)

        signature = await km.sign("test payload", "test-key")
        is_valid = await km.verify("test payload", signature, public_key)

        assert is_valid is True

    @pytest.mark.asyncio
    async def test_verify_invalid_signature(self):
        """Invalid signature returns False."""
        km = TrustKeyManager()
        private_key, public_key = generate_keypair()

        # Register key first, then sign
        km.register_key("test-key", private_key)
        signature = await km.sign("original payload", "test-key")

        # Verification with different payload should fail
        is_valid = await km.verify("different payload", signature, public_key)

        assert is_valid is False


class TestCapabilityRequest:
    """Tests for CapabilityRequest dataclass."""

    def test_capability_request_creation(self):
        """CapabilityRequest stores attributes correctly."""
        request = CapabilityRequest(
            capability="analyze_data",
            capability_type=CapabilityType.ACCESS,
            constraints=["read_only", "audit_required"],
            scope={"databases": ["finance_db"]},
        )

        assert request.capability == "analyze_data"
        assert request.capability_type == CapabilityType.ACCESS
        assert request.constraints == ["read_only", "audit_required"]
        assert request.scope == {"databases": ["finance_db"]}

    def test_capability_request_defaults(self):
        """CapabilityRequest has correct defaults."""
        request = CapabilityRequest(
            capability="test",
            capability_type=CapabilityType.ACTION,
        )

        assert request.constraints == []
        assert request.scope == {}


class TestCapabilityMatching:
    """Tests for capability matching logic."""

    @pytest.fixture
    def trust_ops(self):
        """Create TrustOperations with mocked dependencies."""
        authority_registry = MagicMock()
        key_manager = TrustKeyManager()
        trust_store = MagicMock()
        return TrustOperations(authority_registry, key_manager, trust_store)

    def test_capability_matches_pattern_exact(self, trust_ops):
        """Exact pattern matches exactly."""
        assert trust_ops._capability_matches_pattern("read_data", "read_data") is True
        assert trust_ops._capability_matches_pattern("read_data", "write_data") is False

    def test_capability_matches_pattern_wildcard_suffix(self, trust_ops):
        """Suffix wildcard matches correctly."""
        assert trust_ops._capability_matches_pattern("read_*", "read_data") is True
        assert trust_ops._capability_matches_pattern("read_*", "read_users") is True
        assert trust_ops._capability_matches_pattern("read_*", "write_data") is False

    def test_capability_matches_pattern_wildcard_prefix(self, trust_ops):
        """Prefix wildcard matches correctly."""
        assert trust_ops._capability_matches_pattern("*_admin", "user_admin") is True
        assert trust_ops._capability_matches_pattern("*_admin", "system_admin") is True
        assert trust_ops._capability_matches_pattern("*_admin", "admin_user") is False

    def test_capability_matches_pattern_full_wildcard(self, trust_ops):
        """Full wildcard matches everything."""
        assert trust_ops._capability_matches_pattern("*", "anything") is True
        assert trust_ops._capability_matches_pattern("*", "read_data") is True

    def test_capability_matches_pattern_middle_wildcard(self, trust_ops):
        """Middle wildcard matches correctly."""
        assert (
            trust_ops._capability_matches_pattern("read_*_data", "read_user_data")
            is True
        )
        assert (
            trust_ops._capability_matches_pattern("read_*_data", "read_system_data")
            is True
        )
        assert (
            trust_ops._capability_matches_pattern("read_*_data", "write_user_data")
            is False
        )

    def test_match_capability_direct(self, trust_ops):
        """Direct capability match works."""
        # Create a mock chain with capabilities
        cap = CapabilityAttestation(
            id="cap-001",
            capability="analyze_data",
            capability_type=CapabilityType.ACCESS,
            constraints=[],
            attester_id="org-acme",
            attested_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=365),
            signature="sig",
        )

        genesis = GenesisRecord(
            id="gen-001",
            agent_id="agent-001",
            authority_id="org-acme",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            signature="sig",
        )

        chain = TrustLineageChain(
            genesis=genesis,
            capabilities=[cap],
        )

        result = trust_ops._match_capability(chain, "analyze_data")
        assert result is not None
        assert result.capability == "analyze_data"

    def test_match_capability_no_match(self, trust_ops):
        """No capability match returns None."""
        genesis = GenesisRecord(
            id="gen-001",
            agent_id="agent-001",
            authority_id="org-acme",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            signature="sig",
        )

        chain = TrustLineageChain(genesis=genesis, capabilities=[])

        result = trust_ops._match_capability(chain, "nonexistent")
        assert result is None


class TestConstraintEvaluation:
    """Tests for constraint evaluation logic."""

    @pytest.fixture
    def trust_ops(self):
        """Create TrustOperations with mocked dependencies."""
        authority_registry = MagicMock()
        key_manager = TrustKeyManager()
        trust_store = MagicMock()
        return TrustOperations(authority_registry, key_manager, trust_store)

    def test_evaluate_single_constraint_business_hours_allowed(self, trust_ops):
        """Business hours constraint passes during business hours."""
        constraint = Constraint(
            id="con-001",
            constraint_type=ConstraintType.TIME_WINDOW,
            value="business_hours_only",
            source="genesis",
        )

        # 2 PM is within business hours
        context = {"current_time": datetime(2025, 1, 15, 14, 0, 0)}

        result = trust_ops._evaluate_single_constraint(
            constraint, "test_action", None, context
        )

        assert result["permitted"] is True

    def test_evaluate_single_constraint_business_hours_denied(self, trust_ops):
        """Business hours constraint fails outside business hours."""
        constraint = Constraint(
            id="con-001",
            constraint_type=ConstraintType.TIME_WINDOW,
            value="business_hours_only",
            source="genesis",
        )

        # 8 PM is outside business hours
        context = {"current_time": datetime(2025, 1, 15, 20, 0, 0)}

        result = trust_ops._evaluate_single_constraint(
            constraint, "test_action", None, context
        )

        assert result["permitted"] is False
        assert "business hours" in result["reason"].lower()

    def test_evaluate_single_constraint_read_only_allowed(self, trust_ops):
        """Read only constraint passes for read actions."""
        constraint = Constraint(
            id="con-001",
            constraint_type=ConstraintType.ACTION_RESTRICTION,
            value="read_only",
            source="genesis",
        )

        result = trust_ops._evaluate_single_constraint(
            constraint, "read_data", None, {}
        )

        assert result["permitted"] is True

    def test_evaluate_single_constraint_read_only_denied(self, trust_ops):
        """Read only constraint fails for write actions."""
        constraint = Constraint(
            id="con-001",
            constraint_type=ConstraintType.ACTION_RESTRICTION,
            value="read_only",
            source="genesis",
        )

        result = trust_ops._evaluate_single_constraint(
            constraint, "write_data", None, {}
        )

        assert result["permitted"] is False
        assert "read_only" in result["reason"]

    def test_evaluate_single_constraint_no_pii_export_allowed(self, trust_ops):
        """No PII export constraint passes when no PII present."""
        constraint = Constraint(
            id="con-001",
            constraint_type=ConstraintType.ACTION_RESTRICTION,
            value="no_pii_export",
            source="genesis",
        )

        result = trust_ops._evaluate_single_constraint(
            constraint, "export_data", None, {"contains_pii": False}
        )

        assert result["permitted"] is True

    def test_evaluate_single_constraint_no_pii_export_denied(self, trust_ops):
        """No PII export constraint fails when PII present."""
        constraint = Constraint(
            id="con-001",
            constraint_type=ConstraintType.ACTION_RESTRICTION,
            value="no_pii_export",
            source="genesis",
        )

        result = trust_ops._evaluate_single_constraint(
            constraint, "export_data", None, {"contains_pii": True}
        )

        assert result["permitted"] is False
        assert "PII" in result["reason"]

    def test_evaluate_constraints_all_pass(self, trust_ops):
        """All constraints passing returns permitted."""
        envelope = ConstraintEnvelope(
            id="env-001",
            agent_id="agent-001",
            active_constraints=[
                Constraint(
                    id="con-001",
                    constraint_type=ConstraintType.AUDIT_REQUIREMENT,
                    value="audit_required",
                    source="genesis",
                ),
            ],
            computed_at=datetime.now(timezone.utc),
            valid_until=datetime.now(timezone.utc) + timedelta(days=365),
        )

        result = trust_ops._evaluate_constraints(envelope, "read_data", None, {})

        assert result.permitted is True
        assert result.violations == []

    def test_evaluate_constraints_some_fail(self, trust_ops):
        """Some constraints failing returns violations."""
        envelope = ConstraintEnvelope(
            id="env-001",
            agent_id="agent-001",
            active_constraints=[
                Constraint(
                    id="con-001",
                    constraint_type=ConstraintType.ACTION_RESTRICTION,
                    value="read_only",
                    source="genesis",
                ),
            ],
            computed_at=datetime.now(timezone.utc),
            valid_until=datetime.now(timezone.utc) + timedelta(days=365),
        )

        result = trust_ops._evaluate_constraints(envelope, "write_data", None, {})

        assert result.permitted is False
        assert len(result.violations) == 1


class TestVerificationLevels:
    """Tests for verification level behavior."""

    def test_verification_level_values(self):
        """VerificationLevel has expected values."""
        assert VerificationLevel.QUICK.value == "quick"
        assert VerificationLevel.STANDARD.value == "standard"
        assert VerificationLevel.FULL.value == "full"


class TestVerificationResult:
    """Tests for VerificationResult dataclass."""

    def test_verification_result_valid(self):
        """Valid VerificationResult stores data correctly."""
        result = VerificationResult(
            valid=True,
            level=VerificationLevel.STANDARD,
            capability_used="cap-001",
            effective_constraints=["read_only", "audit_required"],
        )

        assert result.valid is True
        assert result.level == VerificationLevel.STANDARD
        assert result.capability_used == "cap-001"
        assert result.effective_constraints == ["read_only", "audit_required"]

    def test_verification_result_invalid(self):
        """Invalid VerificationResult stores violation info."""
        result = VerificationResult(
            valid=False,
            reason="Constraint violation",
            violations=[{"constraint_id": "con-001", "reason": "time violation"}],
            level=VerificationLevel.STANDARD,
        )

        assert result.valid is False
        assert result.reason == "Constraint violation"
        assert len(result.violations) == 1


class TestComputeConstraintEnvelope:
    """Tests for constraint envelope computation."""

    @pytest.fixture
    def trust_ops(self):
        """Create TrustOperations with mocked dependencies."""
        authority_registry = MagicMock()
        key_manager = TrustKeyManager()
        trust_store = MagicMock()
        return TrustOperations(authority_registry, key_manager, trust_store)

    def test_compute_envelope_basic(self, trust_ops):
        """Basic envelope computation creates valid envelope."""
        genesis = GenesisRecord(
            id="gen-001",
            agent_id="agent-001",
            authority_id="org-acme",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            signature="sig",
        )

        envelope = trust_ops._compute_constraint_envelope("agent-001", genesis, [], [])

        assert envelope.agent_id == "agent-001"
        assert envelope.active_constraints == []

    def test_compute_envelope_with_capabilities(self, trust_ops):
        """Envelope computation includes capability constraints."""
        genesis = GenesisRecord(
            id="gen-001",
            agent_id="agent-001",
            authority_id="org-acme",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            signature="sig",
        )

        cap = CapabilityAttestation(
            id="cap-001",
            capability="analyze_data",
            capability_type=CapabilityType.ACCESS,
            constraints=["read_only", "audit_required"],
            attester_id="org-acme",
            attested_at=datetime.now(timezone.utc),
            signature="sig",
        )

        envelope = trust_ops._compute_constraint_envelope(
            "agent-001", genesis, [cap], []
        )

        # Should have constraints from capability
        constraint_values = [str(c.value) for c in envelope.active_constraints]
        assert "read_only" in constraint_values
        assert "audit_required" in constraint_values


class TestDelegateOperation:
    """Tests for DELEGATE operation logic."""

    @pytest.fixture
    def trust_ops(self):
        """Create TrustOperations with mocked dependencies."""
        authority_registry = MagicMock()
        key_manager = TrustKeyManager()
        trust_store = MagicMock()
        return TrustOperations(authority_registry, key_manager, trust_store)

    def test_delegate_constraint_tightening(self, trust_ops):
        """Delegation can only add constraints, never remove them."""
        # Create a delegator chain with some constraints
        genesis = GenesisRecord(
            id="gen-001",
            agent_id="delegator-001",
            authority_id="org-acme",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.now(timezone.utc),
            signature="sig",
        )

        cap = CapabilityAttestation(
            id="cap-001",
            capability="analyze_data",
            capability_type=CapabilityType.ACCESS,
            constraints=["read_only"],  # Delegator has read_only
            attester_id="org-acme",
            attested_at=datetime.now(timezone.utc),
            signature="sig",
        )

        envelope = trust_ops._compute_constraint_envelope(
            "delegator-001", genesis, [cap], []
        )

        # Delegator's constraints
        delegator_constraint_values = [
            str(c.value) for c in envelope.active_constraints
        ]
        assert "read_only" in delegator_constraint_values

        # When delegating with additional constraints, they should be added
        # not replace existing ones (constraint tightening principle)
        from kaizen.trust.chain import DelegationRecord

        delegation = DelegationRecord(
            id="del-001",
            delegator_id="delegator-001",
            delegatee_id="delegatee-001",
            task_id="task-001",
            capabilities_delegated=["analyze_data"],
            constraint_subset=["read_only", "no_export"],  # Additional constraint
            delegated_at=datetime.now(timezone.utc),
            signature="sig",
        )

        # Compute envelope with delegation
        delegatee_envelope = trust_ops._compute_constraint_envelope(
            "delegatee-001", genesis, [cap], [delegation]
        )

        # Delegatee should have both capability constraints AND delegation constraints
        delegatee_constraint_values = [
            str(c.value) for c in delegatee_envelope.active_constraints
        ]
        assert "read_only" in delegatee_constraint_values  # From capability
        assert "no_export" in delegatee_constraint_values  # From delegation

    def test_delegation_record_creation(self):
        """DelegationRecord correctly stores delegation details."""
        from kaizen.trust.chain import DelegationRecord

        delegation = DelegationRecord(
            id="del-001",
            delegator_id="agent-A",
            delegatee_id="agent-B",
            task_id="analysis-task-001",
            capabilities_delegated=["analyze_data", "export_results"],
            constraint_subset=["read_only", "no_pii_export"],
            delegated_at=datetime(2025, 1, 15, 10, 0, 0),
            expires_at=datetime(2025, 1, 15, 18, 0, 0),
            signature="delegation-sig",
        )

        assert delegation.id == "del-001"
        assert delegation.delegator_id == "agent-A"
        assert delegation.delegatee_id == "agent-B"
        assert delegation.task_id == "analysis-task-001"
        assert "analyze_data" in delegation.capabilities_delegated
        assert "export_results" in delegation.capabilities_delegated
        assert "read_only" in delegation.constraint_subset
        assert "no_pii_export" in delegation.constraint_subset

    def test_delegation_expiry_check(self):
        """Delegation correctly identifies expired delegations."""
        from kaizen.trust.chain import DelegationRecord

        # Non-expired delegation
        future_delegation = DelegationRecord(
            id="del-001",
            delegator_id="agent-A",
            delegatee_id="agent-B",
            task_id="task-001",
            capabilities_delegated=["analyze_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            signature="sig",
        )
        assert future_delegation.is_expired() is False

        # Expired delegation
        expired_delegation = DelegationRecord(
            id="del-002",
            delegator_id="agent-A",
            delegatee_id="agent-B",
            task_id="task-002",
            capabilities_delegated=["analyze_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc) - timedelta(days=1),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            signature="sig",
        )
        assert expired_delegation.is_expired() is True

        # No expiry (never expires)
        no_expiry_delegation = DelegationRecord(
            id="del-003",
            delegator_id="agent-A",
            delegatee_id="agent-B",
            task_id="task-003",
            capabilities_delegated=["analyze_data"],
            constraint_subset=[],
            delegated_at=datetime.now(timezone.utc),
            expires_at=None,
            signature="sig",
        )
        assert no_expiry_delegation.is_expired() is False


class TestAuditOperation:
    """Tests for AUDIT operation logic."""

    def test_audit_anchor_creation(self):
        """AuditAnchor correctly stores audit information."""
        anchor = AuditAnchor(
            id="aud-001",
            agent_id="agent-001",
            action="analyze_data",
            resource="finance_db.transactions",
            timestamp=datetime(2025, 1, 15, 10, 30, 0),
            trust_chain_hash="abc123hash",
            result=ActionResult.SUCCESS,
            parent_anchor_id=None,
            signature="anchor-sig",
            context={"tool_call": "sql_query", "query": "SELECT ..."},
        )

        assert anchor.id == "aud-001"
        assert anchor.agent_id == "agent-001"
        assert anchor.action == "analyze_data"
        assert anchor.resource == "finance_db.transactions"
        assert anchor.trust_chain_hash == "abc123hash"
        assert anchor.result == ActionResult.SUCCESS
        assert anchor.parent_anchor_id is None
        assert anchor.context["tool_call"] == "sql_query"

    def test_audit_anchor_chaining(self):
        """Audit anchors can be chained via parent_anchor_id."""
        # Root anchor
        root_anchor = AuditAnchor(
            id="aud-001",
            agent_id="agent-001",
            action="start_analysis",
            timestamp=datetime(2025, 1, 15, 10, 0, 0),
            trust_chain_hash="hash1",
            result=ActionResult.SUCCESS,
            signature="sig1",
        )

        # Child anchor linked to root
        child_anchor = AuditAnchor(
            id="aud-002",
            agent_id="agent-001",
            action="query_database",
            timestamp=datetime(2025, 1, 15, 10, 1, 0),
            trust_chain_hash="hash2",
            result=ActionResult.SUCCESS,
            parent_anchor_id="aud-001",  # Links to root
            signature="sig2",
        )

        # Grandchild anchor
        grandchild_anchor = AuditAnchor(
            id="aud-003",
            agent_id="agent-001",
            action="generate_report",
            timestamp=datetime(2025, 1, 15, 10, 2, 0),
            trust_chain_hash="hash3",
            result=ActionResult.SUCCESS,
            parent_anchor_id="aud-002",  # Links to child
            signature="sig3",
        )

        assert root_anchor.parent_anchor_id is None
        assert child_anchor.parent_anchor_id == "aud-001"
        assert grandchild_anchor.parent_anchor_id == "aud-002"

    def test_audit_anchor_action_results(self):
        """AuditAnchor supports all ActionResult types."""
        results = [
            ActionResult.SUCCESS,
            ActionResult.FAILURE,
            ActionResult.DENIED,
            ActionResult.PARTIAL,
        ]

        for result in results:
            anchor = AuditAnchor(
                id=f"aud-{result.value}",
                agent_id="agent-001",
                action="test_action",
                timestamp=datetime.now(timezone.utc),
                trust_chain_hash="hash",
                result=result,
                signature="sig",
            )
            assert anchor.result == result

    def test_audit_anchor_to_signing_payload(self):
        """AuditAnchor generates consistent signing payload."""
        anchor = AuditAnchor(
            id="aud-001",
            agent_id="agent-001",
            action="analyze_data",
            resource="database",
            timestamp=datetime(2025, 1, 15, 10, 0, 0),
            trust_chain_hash="abc123",
            result=ActionResult.SUCCESS,
            parent_anchor_id="aud-000",
            signature="sig",
            context={"key": "value"},
        )

        payload = anchor.to_signing_payload()

        assert payload["id"] == "aud-001"
        assert payload["agent_id"] == "agent-001"
        assert payload["action"] == "analyze_data"
        assert payload["resource"] == "database"
        assert payload["trust_chain_hash"] == "abc123"
        assert payload["result"] == "success"
        assert payload["parent_anchor_id"] == "aud-000"

    def test_action_result_values(self):
        """ActionResult enum has expected values."""
        assert ActionResult.SUCCESS.value == "success"
        assert ActionResult.FAILURE.value == "failure"
        assert ActionResult.DENIED.value == "denied"
        assert ActionResult.PARTIAL.value == "partial"


class TestAuditStoreAbstraction:
    """Tests for audit store abstraction."""

    def test_audit_store_immutability_error(self):
        """AuditStoreImmutabilityError conveys immutability violation."""
        from kaizen.trust.audit_store import AuditStoreImmutabilityError

        error = AuditStoreImmutabilityError("update")
        assert "immutable" in str(error).lower()
        assert "update" in str(error)
        assert error.operation == "update"

    def test_audit_anchor_not_found_error(self):
        """AuditAnchorNotFoundError conveys missing anchor."""
        from kaizen.trust.audit_store import AuditAnchorNotFoundError

        error = AuditAnchorNotFoundError("aud-nonexistent")
        assert "not found" in str(error).lower()
        assert "aud-nonexistent" in str(error)
        assert error.anchor_id == "aud-nonexistent"


class TestAuditQueryServiceDataClasses:
    """Tests for audit query service data classes."""

    def test_action_summary_creation(self):
        """ActionSummary stores action statistics."""
        from kaizen.trust.audit_service import ActionSummary

        summary = ActionSummary(
            action="analyze_data",
            total_count=100,
            success_count=85,
            failure_count=10,
            denied_count=3,
            partial_count=2,
            first_occurrence=datetime(2025, 1, 1, 9, 0, 0),
            last_occurrence=datetime(2025, 1, 15, 17, 0, 0),
        )

        assert summary.action == "analyze_data"
        assert summary.total_count == 100
        assert summary.success_count == 85
        assert summary.failure_count == 10
        assert summary.denied_count == 3
        assert summary.partial_count == 2

    def test_agent_audit_summary_creation(self):
        """AgentAuditSummary stores agent-level statistics."""
        from kaizen.trust.audit_service import ActionSummary, AgentAuditSummary

        action_summary = ActionSummary(
            action="analyze_data",
            total_count=50,
            success_count=45,
            failure_count=5,
            denied_count=0,
            partial_count=0,
        )

        summary = AgentAuditSummary(
            agent_id="agent-001",
            total_actions=50,
            unique_actions=["analyze_data"],
            action_summaries={"analyze_data": action_summary},
            first_action=datetime(2025, 1, 1, 9, 0, 0),
            last_action=datetime(2025, 1, 15, 17, 0, 0),
            success_rate=0.90,
        )

        assert summary.agent_id == "agent-001"
        assert summary.total_actions == 50
        assert "analyze_data" in summary.unique_actions
        assert summary.success_rate == 0.90

    def test_compliance_report_creation(self):
        """ComplianceReport stores compliance statistics."""
        from kaizen.trust.audit_service import ComplianceReport

        report = ComplianceReport(
            start_time=datetime(2025, 1, 1, 0, 0, 0),
            end_time=datetime(2025, 1, 31, 23, 59, 59),
            total_actions=1000,
            total_agents=10,
            unique_actions=15,
            success_count=900,
            failure_count=80,
            denied_count=15,
            partial_count=5,
        )

        assert report.total_actions == 1000
        assert report.total_agents == 10
        assert report.unique_actions == 15
        assert report.success_rate == 0.90  # 900/1000
        assert report.any_violations is False

    def test_compliance_report_success_rate_zero_actions(self):
        """ComplianceReport handles zero actions gracefully."""
        from kaizen.trust.audit_service import ComplianceReport

        report = ComplianceReport(
            start_time=datetime(2025, 1, 1, 0, 0, 0),
            end_time=datetime(2025, 1, 31, 23, 59, 59),
            total_actions=0,
        )

        assert report.success_rate == 0.0

    def test_compliance_report_to_dict(self):
        """ComplianceReport serializes correctly."""
        from kaizen.trust.audit_service import ComplianceReport

        report = ComplianceReport(
            start_time=datetime(2025, 1, 1, 0, 0, 0),
            end_time=datetime(2025, 1, 31, 23, 59, 59),
            total_actions=100,
            success_count=80,
            any_violations=True,
            violation_details=[{"anchor_id": "aud-001", "reason": "denied"}],
        )

        data = report.to_dict()

        assert "start_time" in data
        assert data["total_actions"] == 100
        assert data["success_rate"] == 0.80
        assert data["any_violations"] is True
        assert data["violation_count"] == 1
