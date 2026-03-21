"""
Integration tests for EATP SDK lifecycle operations.

Tests the full ESTABLISH -> DELEGATE -> VERIFY -> AUDIT lifecycle
using real stores (InMemoryTrustStore, FilesystemStore) with NO mocking.

Covers:
- Full lifecycle with InMemoryTrustStore
- Full lifecycle with FilesystemStore (with persistence verification)
- Multi-level delegation (3 levels deep)
- Expired credential rejection
- Enforcement integration (StrictEnforcer, ShadowEnforcer)
- Interop integration (JWT, W3C VC, DID)
- Decorator integration (@verified, @audited)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import pytest

from kailash.trust.authority import AuthorityPermission, OrganizationalAuthority
from kailash.trust.chain import (
    ActionResult,
    AuthorityType,
    CapabilityType,
    VerificationLevel,
)
from kailash.trust.signing.crypto import generate_keypair
from kailash.trust.enforce.shadow import ShadowEnforcer
from kailash.trust.enforce.strict import (
    EATPBlockedError,
    EATPHeldError,
    StrictEnforcer,
    Verdict,
)
from kailash.trust.exceptions import TrustChainNotFoundError
from kailash.trust.execution_context import ExecutionContext, HumanOrigin
from kailash.trust.interop.did import (
    create_did_document,
    did_from_authority,
    generate_did,
    generate_did_key,
)
from kailash.trust.interop.jwt import export_chain_as_jwt, export_capability_as_jwt
from kailash.trust.interop.w3c_vc import (
    export_as_verifiable_credential,
    export_capability_as_vc,
    verify_credential,
)
from kailash.trust.operations import (
    CapabilityRequest,
    TrustKeyManager,
    TrustOperations,
)
from kailash.trust.chain_store.filesystem import FilesystemStore
from kailash.trust.chain_store.memory import InMemoryTrustStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Simple Authority Registry (real implementation, NOT a mock)
# ---------------------------------------------------------------------------


class SimpleAuthorityRegistry:
    """
    A real in-memory authority registry implementing AuthorityRegistryProtocol.

    This is NOT a mock -- it stores and retrieves real OrganizationalAuthority
    objects in memory, fully implementing the protocol contract.
    """

    def __init__(self) -> None:
        self._authorities: Dict[str, OrganizationalAuthority] = {}

    async def initialize(self) -> None:
        """Initialize the registry (no-op for in-memory)."""
        pass

    def register(self, authority: OrganizationalAuthority) -> None:
        """Register an authority in the registry."""
        self._authorities[authority.id] = authority

    async def get_authority(
        self,
        authority_id: str,
        include_inactive: bool = False,
    ) -> OrganizationalAuthority:
        """
        Retrieve an authority by ID.

        Raises:
            KeyError: If authority not found (matches AuthorityRegistryProtocol)
        """
        authority = self._authorities.get(authority_id)
        if authority is None:
            from kailash.trust.exceptions import AuthorityNotFoundError

            raise AuthorityNotFoundError(authority_id)
        if not authority.is_active and not include_inactive:
            from kailash.trust.exceptions import AuthorityInactiveError

            raise AuthorityInactiveError(authority_id)
        return authority

    async def update_authority(self, authority: OrganizationalAuthority) -> None:
        """Persist changes to an authority record."""
        self._authorities[authority.id] = authority


# ---------------------------------------------------------------------------
# Shared Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def keypair():
    """Generate a fresh Ed25519 keypair for tests."""
    private_key, public_key = generate_keypair()
    return private_key, public_key


@pytest.fixture
def authority(keypair):
    """Create a real OrganizationalAuthority with valid keys."""
    _, public_key = keypair
    return OrganizationalAuthority(
        id="org-acme",
        name="ACME Corporation",
        authority_type=AuthorityType.ORGANIZATION,
        public_key=public_key,
        signing_key_id="acme-key-001",
        permissions=[
            AuthorityPermission.CREATE_AGENTS,
            AuthorityPermission.DELEGATE_TRUST,
            AuthorityPermission.GRANT_CAPABILITIES,
        ],
    )


@pytest.fixture
def registry(authority):
    """Create a real authority registry with the test authority registered."""
    reg = SimpleAuthorityRegistry()
    reg.register(authority)
    return reg


@pytest.fixture
def key_manager(keypair):
    """Create a TrustKeyManager with the test private key registered."""
    private_key, _ = keypair
    km = TrustKeyManager()
    km.register_key("acme-key-001", private_key)
    return km


@pytest.fixture
async def memory_store():
    """Create and initialize an InMemoryTrustStore."""
    store = InMemoryTrustStore()
    await store.initialize()
    return store


@pytest.fixture
async def ops(registry, key_manager, memory_store):
    """Create an initialized TrustOperations instance with in-memory store."""
    operations = TrustOperations(
        authority_registry=registry,
        key_manager=key_manager,
        trust_store=memory_store,
    )
    await operations.initialize()
    return operations


@pytest.fixture
def human_origin():
    """Create a HumanOrigin for delegation/audit tests."""
    return HumanOrigin(
        human_id="alice@acme.com",
        display_name="Alice Chen",
        auth_provider="okta",
        session_id="sess-integration-001",
        authenticated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def execution_ctx(human_origin):
    """Create an ExecutionContext wrapping the human origin."""
    return ExecutionContext(
        human_origin=human_origin,
        delegation_chain=["pseudo:alice@acme.com"],
        delegation_depth=0,
    )


# ---------------------------------------------------------------------------
# Test 1: Full Lifecycle with InMemoryTrustStore
# ---------------------------------------------------------------------------


class TestFullLifecycleInMemory:
    """Full ESTABLISH -> VERIFY -> DELEGATE -> VERIFY -> AUDIT lifecycle."""

    async def test_establish_creates_trust_chain(self, ops):
        """ESTABLISH creates a valid trust chain for a new agent."""
        chain = await ops.establish(
            agent_id="agent-001",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="analyze_data",
                    capability_type=CapabilityType.ACTION,
                ),
                CapabilityRequest(
                    capability="read_reports",
                    capability_type=CapabilityType.ACCESS,
                ),
            ],
        )

        assert chain is not None
        assert chain.genesis.agent_id == "agent-001"
        assert chain.genesis.authority_id == "org-acme"
        assert chain.genesis.authority_type == AuthorityType.ORGANIZATION
        assert chain.genesis.signature != ""
        assert len(chain.capabilities) == 2
        assert chain.capabilities[0].signature != ""
        assert chain.capabilities[1].signature != ""
        assert chain.constraint_envelope is not None

    async def test_verify_established_agent_succeeds(self, ops):
        """VERIFY succeeds for an established agent performing a known action."""
        await ops.establish(
            agent_id="agent-001",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="analyze_data",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
        )

        result = await ops.verify(agent_id="agent-001", action="analyze_data")

        assert result.valid is True
        assert result.capability_used is not None

    async def test_verify_unknown_action_fails(self, ops):
        """VERIFY fails for an action not in the agent's capabilities."""
        await ops.establish(
            agent_id="agent-001",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="analyze_data",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
        )

        result = await ops.verify(agent_id="agent-001", action="delete_records")

        assert result.valid is False
        assert "No capability found" in result.reason

    async def test_verify_nonexistent_agent_fails(self, ops):
        """VERIFY fails for an agent that was never established."""
        result = await ops.verify(agent_id="ghost-agent", action="anything")

        assert result.valid is False
        assert "No trust chain found" in result.reason

    async def test_delegate_creates_sub_agent(self, ops, execution_ctx):
        """DELEGATE creates a trust chain for the delegatee agent."""
        await ops.establish(
            agent_id="agent-001",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="analyze_data",
                    capability_type=CapabilityType.ACTION,
                ),
                CapabilityRequest(
                    capability="read_reports",
                    capability_type=CapabilityType.ACCESS,
                ),
            ],
        )

        delegation = await ops.delegate(
            delegator_id="agent-001",
            delegatee_id="agent-002",
            task_id="task-data-analysis",
            capabilities=["analyze_data"],
            context=execution_ctx,
        )

        assert delegation is not None
        assert delegation.delegator_id == "agent-001"
        assert delegation.delegatee_id == "agent-002"
        assert delegation.task_id == "task-data-analysis"
        assert "analyze_data" in delegation.capabilities_delegated
        assert delegation.signature != ""
        assert delegation.human_origin is not None
        assert delegation.human_origin.human_id == "alice@acme.com"

    async def test_verify_delegatee_succeeds(self, ops, execution_ctx):
        """VERIFY succeeds for a delegated agent on its delegated capability."""
        await ops.establish(
            agent_id="agent-001",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="analyze_data",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
        )
        await ops.delegate(
            delegator_id="agent-001",
            delegatee_id="agent-002",
            task_id="task-001",
            capabilities=["analyze_data"],
            context=execution_ctx,
        )

        result = await ops.verify(agent_id="agent-002", action="analyze_data")

        assert result.valid is True

    async def test_audit_records_action(self, ops, execution_ctx):
        """AUDIT creates a signed audit anchor for an agent action."""
        await ops.establish(
            agent_id="agent-001",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="analyze_data",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
        )

        anchor = await ops.audit(
            agent_id="agent-001",
            action="analyze_data",
            resource="finance_db",
            result=ActionResult.SUCCESS,
            context_data={"query": "SELECT * FROM transactions"},
            context=execution_ctx,
        )

        assert anchor is not None
        assert anchor.agent_id == "agent-001"
        assert anchor.action == "analyze_data"
        assert anchor.resource == "finance_db"
        assert anchor.result == ActionResult.SUCCESS
        assert anchor.signature != ""
        assert anchor.trust_chain_hash != ""
        assert anchor.human_origin is not None
        assert anchor.human_origin.human_id == "alice@acme.com"

    async def test_audit_stored_in_chain(self, ops, execution_ctx):
        """AUDIT appends the anchor to the agent's trust chain."""
        chain = await ops.establish(
            agent_id="agent-001",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="analyze_data",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
        )

        assert len(chain.audit_anchors) == 0

        await ops.audit(
            agent_id="agent-001",
            action="analyze_data",
            result=ActionResult.SUCCESS,
            context=execution_ctx,
        )

        # Fetch chain again from store to verify (audit modifies the in-memory chain)
        updated_chain = await ops.trust_store.get_chain("agent-001")
        assert len(updated_chain.audit_anchors) == 1
        assert updated_chain.audit_anchors[0].action == "analyze_data"

    async def test_full_lifecycle_end_to_end(self, ops, execution_ctx):
        """Complete ESTABLISH -> VERIFY -> DELEGATE -> VERIFY -> AUDIT flow."""
        # ESTABLISH
        chain = await ops.establish(
            agent_id="root-agent",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="analyze_data",
                    capability_type=CapabilityType.ACTION,
                ),
                CapabilityRequest(
                    capability="read_reports",
                    capability_type=CapabilityType.ACCESS,
                ),
            ],
        )
        assert chain.genesis.agent_id == "root-agent"

        # VERIFY root agent
        verify_result = await ops.verify(agent_id="root-agent", action="analyze_data")
        assert verify_result.valid is True

        # DELEGATE to sub-agent
        delegation = await ops.delegate(
            delegator_id="root-agent",
            delegatee_id="sub-agent",
            task_id="task-report-gen",
            capabilities=["analyze_data"],
            context=execution_ctx,
        )
        assert delegation.delegator_id == "root-agent"

        # VERIFY sub-agent
        sub_verify = await ops.verify(agent_id="sub-agent", action="analyze_data")
        assert sub_verify.valid is True

        # AUDIT both agents
        root_audit = await ops.audit(
            agent_id="root-agent",
            action="analyze_data",
            result=ActionResult.SUCCESS,
            context=execution_ctx,
        )
        assert root_audit.signature != ""

        sub_audit = await ops.audit(
            agent_id="sub-agent",
            action="analyze_data",
            result=ActionResult.SUCCESS,
            parent_anchor_id=root_audit.id,
            context=execution_ctx,
        )
        assert sub_audit.parent_anchor_id == root_audit.id

    async def test_full_verification_with_signatures(self, ops):
        """VERIFY at FULL level validates all cryptographic signatures."""
        await ops.establish(
            agent_id="agent-001",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="analyze_data",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
        )

        result = await ops.verify(
            agent_id="agent-001",
            action="analyze_data",
            level=VerificationLevel.FULL,
        )

        assert result.valid is True


# ---------------------------------------------------------------------------
# Test 2: Full Lifecycle with FilesystemStore
# ---------------------------------------------------------------------------


class TestFullLifecycleFilesystem:
    """Full lifecycle using FilesystemStore with persistence verification."""

    @pytest.fixture
    async def fs_store(self, tmp_path):
        """Create and initialize a FilesystemStore in a temp directory."""
        store = FilesystemStore(str(tmp_path / "eatp_chains"))
        await store.initialize()
        return store

    @pytest.fixture
    async def fs_ops(self, registry, key_manager, fs_store):
        """Create TrustOperations backed by FilesystemStore."""
        operations = TrustOperations(
            authority_registry=registry,
            key_manager=key_manager,
            trust_store=fs_store,
        )
        await operations.initialize()
        return operations

    async def test_establish_persists_to_filesystem(self, fs_ops, fs_store):
        """ESTABLISH stores the chain as a JSON file on disk."""
        chain = await fs_ops.establish(
            agent_id="fs-agent-001",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="analyze_data",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
        )

        # Verify chain can be retrieved
        retrieved = await fs_store.get_chain("fs-agent-001")
        assert retrieved.genesis.agent_id == "fs-agent-001"
        assert retrieved.genesis.authority_id == "org-acme"
        assert len(retrieved.capabilities) == 1
        assert retrieved.capabilities[0].capability == "analyze_data"

    async def test_persistence_survives_close_and_reopen(self, registry, key_manager, tmp_path):
        """Data persists after closing and reopening the FilesystemStore."""
        store_dir = str(tmp_path / "persist_test")

        # Phase 1: Create store, establish agent, close
        store1 = FilesystemStore(store_dir)
        await store1.initialize()
        ops1 = TrustOperations(
            authority_registry=registry,
            key_manager=key_manager,
            trust_store=store1,
        )
        await ops1.initialize()

        chain = await ops1.establish(
            agent_id="persist-agent",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="read_data",
                    capability_type=CapabilityType.ACCESS,
                ),
            ],
        )
        original_genesis_id = chain.genesis.id
        await store1.close()

        # Phase 2: Reopen store and verify data survived
        store2 = FilesystemStore(store_dir)
        await store2.initialize()

        recovered = await store2.get_chain("persist-agent")
        assert recovered.genesis.agent_id == "persist-agent"
        assert recovered.genesis.id == original_genesis_id
        assert recovered.genesis.authority_id == "org-acme"
        assert len(recovered.capabilities) == 1
        assert recovered.capabilities[0].capability == "read_data"
        await store2.close()

    async def test_full_lifecycle_on_filesystem(self, fs_ops, fs_store, execution_ctx):
        """Complete lifecycle operations work correctly with filesystem persistence."""
        # ESTABLISH
        await fs_ops.establish(
            agent_id="fs-root",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="process_data",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
        )

        # VERIFY
        result = await fs_ops.verify(agent_id="fs-root", action="process_data")
        assert result.valid is True

        # DELEGATE
        delegation = await fs_ops.delegate(
            delegator_id="fs-root",
            delegatee_id="fs-worker",
            task_id="task-fs-001",
            capabilities=["process_data"],
            context=execution_ctx,
        )
        assert delegation.signature != ""

        # VERIFY delegatee
        worker_result = await fs_ops.verify(agent_id="fs-worker", action="process_data")
        assert worker_result.valid is True

        # AUDIT
        anchor = await fs_ops.audit(
            agent_id="fs-root",
            action="process_data",
            result=ActionResult.SUCCESS,
            context=execution_ctx,
        )
        assert anchor.signature != ""

    async def test_count_and_list_chains(self, fs_ops, fs_store):
        """FilesystemStore correctly counts and lists stored chains."""
        await fs_ops.establish(
            agent_id="list-agent-1",
            authority_id="org-acme",
            capabilities=[CapabilityRequest(capability="read", capability_type=CapabilityType.ACCESS)],
        )
        await fs_ops.establish(
            agent_id="list-agent-2",
            authority_id="org-acme",
            capabilities=[CapabilityRequest(capability="write", capability_type=CapabilityType.ACTION)],
        )

        count = await fs_store.count_chains()
        assert count == 2

        chains = await fs_store.list_chains()
        assert len(chains) == 2

        agent_ids = {c.genesis.agent_id for c in chains}
        assert "list-agent-1" in agent_ids
        assert "list-agent-2" in agent_ids


# ---------------------------------------------------------------------------
# Test 3: Multi-Level Delegation (3 levels)
# ---------------------------------------------------------------------------


class TestMultiLevelDelegation:
    """Tests for 3-level delegation: root -> agent-2 -> agent-3."""

    async def test_three_level_delegation_chain(self, ops, human_origin):
        """Delegation works across 3 levels with constraints tightening."""
        # Level 0: ESTABLISH root agent
        await ops.establish(
            agent_id="root",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="analyze_data",
                    capability_type=CapabilityType.ACTION,
                ),
                CapabilityRequest(
                    capability="read_reports",
                    capability_type=CapabilityType.ACCESS,
                ),
                CapabilityRequest(
                    capability="write_reports",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
        )

        # Level 1: root -> agent-2 (delegate 2 of 3 capabilities)
        ctx_level0 = ExecutionContext(
            human_origin=human_origin,
            delegation_chain=["pseudo:alice@acme.com"],
            delegation_depth=0,
        )
        delegation_1 = await ops.delegate(
            delegator_id="root",
            delegatee_id="agent-2",
            task_id="task-level-1",
            capabilities=["analyze_data", "read_reports"],
            additional_constraints=["read_only"],
            context=ctx_level0,
        )
        assert delegation_1.delegation_depth == 1

        # Level 2: agent-2 -> agent-3 (delegate 1 of 2 capabilities)
        ctx_level1 = ctx_level0.with_delegation("agent-2")
        delegation_2 = await ops.delegate(
            delegator_id="agent-2",
            delegatee_id="agent-3",
            task_id="task-level-2",
            capabilities=["analyze_data"],
            additional_constraints=["no_pii_export"],
            context=ctx_level1,
        )
        assert delegation_2.delegation_depth == 2

        # Verify each agent has correct capabilities
        root_caps = await ops.get_agent_capabilities("root")
        assert "analyze_data" in root_caps
        assert "read_reports" in root_caps
        assert "write_reports" in root_caps

        agent2_caps = await ops.get_agent_capabilities("agent-2")
        assert "analyze_data" in agent2_caps
        assert "read_reports" in agent2_caps

        agent3_caps = await ops.get_agent_capabilities("agent-3")
        assert "analyze_data" in agent3_caps

        # Verify agent-3 cannot perform undelegated actions
        result = await ops.verify(agent_id="agent-3", action="read_reports")
        assert result.valid is False

        # Verify agent-3 CAN perform delegated action
        result = await ops.verify(agent_id="agent-3", action="analyze_data")
        assert result.valid is True

    async def test_delegation_constraints_accumulate(self, ops, human_origin):
        """Each delegation level adds constraints; they tighten, never loosen."""
        await ops.establish(
            agent_id="root",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="analyze_data",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
        )

        ctx = ExecutionContext(
            human_origin=human_origin,
            delegation_chain=["pseudo:alice@acme.com"],
            delegation_depth=0,
        )

        # Delegate root -> child with constraint "read_only"
        await ops.delegate(
            delegator_id="root",
            delegatee_id="child",
            task_id="task-constrained",
            capabilities=["analyze_data"],
            additional_constraints=["read_only"],
            context=ctx,
        )

        # Verify child agent's constraints include the added constraint
        child_constraints = await ops.get_agent_constraints("child")
        assert "read_only" in child_constraints

    async def test_delegation_human_origin_propagates(self, ops, human_origin):
        """Human origin propagates through the entire delegation chain."""
        await ops.establish(
            agent_id="root",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="analyze_data",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
        )

        ctx_0 = ExecutionContext(
            human_origin=human_origin,
            delegation_chain=["pseudo:alice@acme.com"],
            delegation_depth=0,
        )

        del_1 = await ops.delegate(
            delegator_id="root",
            delegatee_id="agent-2",
            task_id="task-1",
            capabilities=["analyze_data"],
            context=ctx_0,
        )
        assert del_1.human_origin.human_id == "alice@acme.com"

        ctx_1 = ctx_0.with_delegation("agent-2")
        del_2 = await ops.delegate(
            delegator_id="agent-2",
            delegatee_id="agent-3",
            task_id="task-2",
            capabilities=["analyze_data"],
            context=ctx_1,
        )
        assert del_2.human_origin.human_id == "alice@acme.com"
        assert del_2.delegation_depth == 2


# ---------------------------------------------------------------------------
# Test 4: Expired Credential Rejection
# ---------------------------------------------------------------------------


class TestExpiredCredentialRejection:
    """Tests that expired credentials are properly rejected."""

    async def test_expired_genesis_rejected_on_quick_verify(self, ops):
        """VERIFY rejects an agent whose genesis has expired."""
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        await ops.establish(
            agent_id="expired-agent",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="analyze_data",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
            expires_at=past,
        )

        # QUICK verification checks expiration
        result = await ops.verify(
            agent_id="expired-agent",
            action="analyze_data",
            level=VerificationLevel.QUICK,
        )
        assert result.valid is False
        assert "expired" in result.reason.lower()

    async def test_expired_agent_standard_verify_fails(self, ops):
        """VERIFY at STANDARD level rejects expired capabilities."""
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        await ops.establish(
            agent_id="expired-agent",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="analyze_data",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
            expires_at=past,
        )

        result = await ops.verify(
            agent_id="expired-agent",
            action="analyze_data",
            level=VerificationLevel.STANDARD,
        )
        # Expired capabilities should not match
        assert result.valid is False


# ---------------------------------------------------------------------------
# Test 5: Enforcement Integration
# ---------------------------------------------------------------------------


class TestEnforcementIntegration:
    """Tests StrictEnforcer and ShadowEnforcer with real TrustOperations."""

    async def test_strict_enforcer_blocks_invalid_agent(self, ops):
        """StrictEnforcer raises EATPBlockedError for invalid verification."""
        # Verify a nonexistent agent => invalid result
        result = await ops.verify(agent_id="no-such-agent", action="read")

        enforcer = StrictEnforcer()
        with pytest.raises(EATPBlockedError) as exc_info:
            enforcer.enforce(agent_id="no-such-agent", action="read", result=result)
        assert exc_info.value.agent_id == "no-such-agent"
        assert exc_info.value.action == "read"

    async def test_strict_enforcer_approves_valid_agent(self, ops):
        """StrictEnforcer returns AUTO_APPROVED for valid verification."""
        await ops.establish(
            agent_id="valid-agent",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="read_data",
                    capability_type=CapabilityType.ACCESS,
                ),
            ],
        )

        result = await ops.verify(agent_id="valid-agent", action="read_data")
        enforcer = StrictEnforcer()
        verdict = enforcer.enforce(agent_id="valid-agent", action="read_data", result=result)

        assert verdict == Verdict.AUTO_APPROVED

    async def test_strict_enforcer_records_enforcement(self, ops):
        """StrictEnforcer keeps an audit trail of enforcement decisions."""
        await ops.establish(
            agent_id="audit-agent",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="read_data",
                    capability_type=CapabilityType.ACCESS,
                ),
            ],
        )

        result = await ops.verify(agent_id="audit-agent", action="read_data")
        enforcer = StrictEnforcer()
        enforcer.enforce(agent_id="audit-agent", action="read_data", result=result)

        assert len(enforcer.records) == 1
        assert enforcer.records[0].agent_id == "audit-agent"
        assert enforcer.records[0].verdict == Verdict.AUTO_APPROVED

    async def test_shadow_enforcer_logs_without_blocking(self, ops):
        """ShadowEnforcer returns verdict but never raises exceptions."""
        # Invalid agent - would be blocked in strict mode
        invalid_result = await ops.verify(agent_id="ghost-agent", action="anything")

        shadow = ShadowEnforcer()
        verdict = shadow.check(agent_id="ghost-agent", action="anything", result=invalid_result)

        # Returns BLOCKED verdict but does NOT raise
        assert verdict == Verdict.BLOCKED
        assert shadow.metrics.total_checks == 1
        assert shadow.metrics.blocked_count == 1

    async def test_shadow_enforcer_tracks_metrics(self, ops):
        """ShadowEnforcer collects accurate metrics across multiple checks."""
        await ops.establish(
            agent_id="metrics-agent",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="read_data",
                    capability_type=CapabilityType.ACCESS,
                ),
            ],
        )

        shadow = ShadowEnforcer()

        # Valid check
        valid_result = await ops.verify(agent_id="metrics-agent", action="read_data")
        shadow.check(agent_id="metrics-agent", action="read_data", result=valid_result)

        # Invalid check
        invalid_result = await ops.verify(agent_id="no-agent", action="nothing")
        shadow.check(agent_id="no-agent", action="nothing", result=invalid_result)

        assert shadow.metrics.total_checks == 2
        assert shadow.metrics.auto_approved_count == 1
        assert shadow.metrics.blocked_count == 1
        assert shadow.metrics.pass_rate == 50.0
        assert shadow.metrics.block_rate == 50.0

    async def test_shadow_enforcer_report(self, ops):
        """ShadowEnforcer generates a human-readable report."""
        invalid_result = await ops.verify(agent_id="ghost", action="anything")
        shadow = ShadowEnforcer()
        shadow.check(agent_id="ghost", action="anything", result=invalid_result)

        report = shadow.report()
        assert "Shadow Enforcement Report" in report
        assert "Total checks" in report
        assert "Would block" in report


# ---------------------------------------------------------------------------
# Test 6: Interop Integration (JWT, W3C VC, DID)
# ---------------------------------------------------------------------------


class TestInteropIntegration:
    """Tests JWT export, W3C VC export, and DID generation with real chains."""

    async def test_export_chain_as_jwt(self, ops):
        """Export a real trust chain as a signed JWT."""
        chain = await ops.establish(
            agent_id="jwt-agent",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="analyze_data",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
        )

        # JWT export with HS256 (symmetric key for simplicity)
        jwt_secret = "test-secret-key-for-jwt-signing"
        token = export_chain_as_jwt(chain, signing_key=jwt_secret, algorithm="HS256")

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
        # JWT has 3 parts separated by dots
        assert token.count(".") == 2

    async def test_export_capability_as_jwt(self, ops):
        """Export a single capability attestation as JWT."""
        chain = await ops.establish(
            agent_id="cap-jwt-agent",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="read_data",
                    capability_type=CapabilityType.ACCESS,
                ),
            ],
        )

        jwt_secret = "test-secret-key-for-jwt-signing"
        token = export_capability_as_jwt(
            chain.capabilities[0],
            signing_key=jwt_secret,
            algorithm="HS256",
        )

        assert token is not None
        assert token.count(".") == 2

    async def test_export_chain_as_w3c_vc(self, ops, keypair):
        """Export a real trust chain as a W3C Verifiable Credential."""
        private_key, public_key = keypair

        chain = await ops.establish(
            agent_id="vc-agent",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="analyze_data",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
        )

        vc = export_as_verifiable_credential(
            chain=chain,
            issuer_did="did:eatp:org-acme",
            signing_key=private_key,
        )

        assert vc is not None
        assert "@context" in vc
        assert "credentialSubject" in vc
        assert "proof" in vc
        assert vc["issuer"] == "did:eatp:org-acme"
        assert "EATPTrustChain" in vc["type"]
        assert vc["proof"]["type"] == "Ed25519Signature2020"

    async def test_verify_w3c_vc_signature(self, ops, keypair):
        """Verify the cryptographic signature of an exported W3C VC."""
        private_key, public_key = keypair

        chain = await ops.establish(
            agent_id="vc-verify-agent",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="read_data",
                    capability_type=CapabilityType.ACCESS,
                ),
            ],
        )

        vc = export_as_verifiable_credential(
            chain=chain,
            issuer_did="did:eatp:org-acme",
            signing_key=private_key,
        )

        is_valid = verify_credential(vc, public_key)
        assert is_valid is True

    async def test_export_capability_as_w3c_vc(self, ops, keypair):
        """Export a single capability as a W3C VC."""
        private_key, _ = keypair

        chain = await ops.establish(
            agent_id="cap-vc-agent",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="write_data",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
        )

        vc = export_capability_as_vc(
            attestation=chain.capabilities[0],
            issuer_did="did:eatp:org-acme",
            signing_key=private_key,
        )

        assert vc is not None
        assert "EATPCapabilityAttestation" in vc["type"]
        assert "proof" in vc

    async def test_generate_did_from_agent(self):
        """Generate a DID for an agent ID."""
        did = generate_did("agent-001")
        assert did == "did:eatp:agent-001"

    async def test_generate_did_key_from_public_key(self, keypair):
        """Generate a did:key DID from an Ed25519 public key."""
        _, public_key = keypair

        did = generate_did_key(public_key)
        assert did.startswith("did:key:z")

    async def test_create_did_document(self, keypair):
        """Create a full DID document for an agent."""
        _, public_key = keypair

        doc = create_did_document(
            agent_id="agent-001",
            public_key=public_key,
            authority_id="org-acme",
        )

        assert doc.id == "did:eatp:agent-001"
        assert len(doc.verification_method) == 1
        assert doc.verification_method[0].type == "Ed25519VerificationKey2020"
        assert doc.controller == "did:eatp:org-acme"
        assert len(doc.authentication) == 1
        assert len(doc.assertion_method) == 1

    async def test_did_from_authority(self, authority):
        """Generate a DID from an OrganizationalAuthority."""
        did = did_from_authority(authority)
        assert did == "did:eatp:org-acme"


# ---------------------------------------------------------------------------
# Test 7: Decorator Integration
# ---------------------------------------------------------------------------


class TestDecoratorIntegration:
    """Tests for @verified and @audited decorators with real TrustOperations."""

    async def test_verified_decorator_passes_valid_agent(self, ops):
        """@verified allows execution when agent has required capability."""
        from kailash.trust.enforce.decorators import verified

        await ops.establish(
            agent_id="dec-agent",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="process_data",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
        )

        @verified(agent_id="dec-agent", action="process_data", ops=ops)
        async def process_data():
            return {"status": "processed"}

        result = await process_data()
        assert result == {"status": "processed"}

    async def test_verified_decorator_blocks_invalid_agent(self, ops):
        """@verified raises EATPBlockedError when agent lacks capability."""
        from kailash.trust.enforce.decorators import verified

        await ops.establish(
            agent_id="limited-agent",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="read_data",
                    capability_type=CapabilityType.ACCESS,
                ),
            ],
        )

        @verified(agent_id="limited-agent", action="delete_all", ops=ops)
        async def dangerous_operation():
            return {"status": "deleted"}

        with pytest.raises(EATPBlockedError):
            await dangerous_operation()

    async def test_verified_decorator_blocks_nonexistent_agent(self, ops):
        """@verified raises EATPBlockedError for nonexistent agent."""
        from kailash.trust.enforce.decorators import verified

        @verified(agent_id="ghost", action="anything", ops=ops)
        async def ghost_operation():
            return {"status": "should not run"}

        with pytest.raises(EATPBlockedError):
            await ghost_operation()

    async def test_audited_decorator_records_action(self, ops, execution_ctx):
        """@audited creates an audit trail after function execution."""
        from kailash.trust.enforce.decorators import audited

        await ops.establish(
            agent_id="audited-agent",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="transform_data",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
        )

        @audited(agent_id="audited-agent", ops=ops)
        async def transform_data(data):
            return {"transformed": True, "input": data}

        from kailash.trust.execution_context import execution_context

        with execution_context(execution_ctx):
            result = await transform_data({"value": 42})

        assert result == {"transformed": True, "input": {"value": 42}}

        # Verify audit was recorded on the chain
        chain = await ops.trust_store.get_chain("audited-agent")
        assert len(chain.audit_anchors) == 1
        assert "transform_data" in chain.audit_anchors[0].action

    async def test_verified_decorator_set_ops_later(self, ops):
        """@verified allows setting ops after decoration via set_ops()."""
        from kailash.trust.enforce.decorators import verified

        await ops.establish(
            agent_id="late-ops-agent",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="query_data",
                    capability_type=CapabilityType.ACCESS,
                ),
            ],
        )

        @verified(agent_id="late-ops-agent", action="query_data")
        async def query_data():
            return {"results": [1, 2, 3]}

        # Without ops set, should raise RuntimeError
        with pytest.raises(RuntimeError, match="TrustOperations not configured"):
            await query_data()

        # Set ops later
        query_data.set_ops(ops)

        # Now it should work
        result = await query_data()
        assert result == {"results": [1, 2, 3]}

    async def test_shadow_decorator_never_blocks(self, ops):
        """@shadow decorator runs verification in shadow mode without blocking."""
        from kailash.trust.enforce.decorators import shadow
        from kailash.trust.enforce.shadow import ShadowEnforcer

        shared_shadow = ShadowEnforcer()

        # This agent does NOT exist, so verification would fail
        @shadow(
            agent_id="ghost-shadow",
            action="anything",
            ops=ops,
            shadow_enforcer=shared_shadow,
        )
        async def shadow_operation():
            return {"executed": True}

        # Should succeed even though verification fails
        result = await shadow_operation()
        assert result == {"executed": True}

        # Shadow enforcer should have recorded the check
        assert shared_shadow.metrics.total_checks == 1
        assert shared_shadow.metrics.blocked_count == 1
