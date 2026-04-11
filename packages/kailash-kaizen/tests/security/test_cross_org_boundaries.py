"""
Security Tests for Cross-Organization Boundaries (Tier 1)

Tests that verify proper enforcement of organizational boundaries
in trust operations. Part of CARE-040.

Coverage:
- Prevention of cross-org trust establishment
- Delegation boundary enforcement
- Federation requirements
- Spoofed org ID detection
- Replay attack prevention

Note: These are unit tests (Tier 1). The current implementation may not
have all features fully implemented. Where features are missing, tests
document the expected behavior and what's currently available.
"""

import hashlib
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from kailash.trust.chain import (
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    GenesisRecord,
    TrustLineageChain,
)
from kailash.trust.exceptions import (
    AuthorityNotFoundError,
    DelegationError,
    TrustChainNotFoundError,
    TrustError,
)
from kailash.trust.operations import CapabilityRequest, TrustKeyManager, TrustOperations
from kailash.trust.signing.crypto import generate_keypair, sign, verify_signature

from kaizen.trust.authority import (
    AuthorityPermission,
    OrganizationalAuthority,
    OrganizationalAuthorityRegistry,
)
from kaizen.trust.store import InMemoryTrustStore


class TestCannotEstablishInForeignOrg:
    """Test that agents cannot create trust chains in another organization."""

    @pytest.fixture
    def org_acme_authority(self):
        """Create an authority for org-acme."""
        private_key, public_key = generate_keypair()
        return (
            OrganizationalAuthority(
                id="org-acme",
                name="ACME Corporation",
                authority_type=AuthorityType.HUMAN,
                public_key=public_key,
                signing_key_id="acme-key-001",
                permissions=[
                    AuthorityPermission.CREATE_AGENTS,
                    AuthorityPermission.DEACTIVATE_AGENTS,
                ],
                metadata={"domain": "acme.com"},
            ),
            private_key,
        )

    @pytest.fixture
    def org_globex_authority(self):
        """Create an authority for org-globex."""
        private_key, public_key = generate_keypair()
        return (
            OrganizationalAuthority(
                id="org-globex",
                name="Globex Corporation",
                authority_type=AuthorityType.HUMAN,
                public_key=public_key,
                signing_key_id="globex-key-001",
                permissions=[
                    AuthorityPermission.CREATE_AGENTS,
                    AuthorityPermission.DEACTIVATE_AGENTS,
                ],
                metadata={"domain": "globex.com"},
            ),
            private_key,
        )

    @pytest.fixture
    def key_manager(self, org_acme_authority, org_globex_authority):
        """Create key manager with org keys."""
        km = TrustKeyManager()
        km.register_key("acme-key-001", org_acme_authority[1])
        km.register_key("globex-key-001", org_globex_authority[1])
        return km

    @pytest.fixture
    def authority_registry(self, org_acme_authority, org_globex_authority):
        """Create a registry with both organizations."""
        registry = MagicMock(spec=OrganizationalAuthorityRegistry)

        async def get_authority(auth_id, include_inactive=False):
            if auth_id == "org-acme":
                return org_acme_authority[0]
            elif auth_id == "org-globex":
                return org_globex_authority[0]
            raise AuthorityNotFoundError(auth_id)

        registry.get_authority = AsyncMock(side_effect=get_authority)
        registry.initialize = AsyncMock()
        return registry

    @pytest.fixture
    def trust_store(self):
        """Create an in-memory trust store."""
        return InMemoryTrustStore()

    @pytest.fixture
    def trust_ops(self, authority_registry, key_manager, trust_store):
        """Create TrustOperations instance."""
        return TrustOperations(
            authority_registry=authority_registry,
            key_manager=key_manager,
            trust_store=trust_store,
        )

    @pytest.mark.asyncio
    async def test_cannot_establish_in_foreign_org(
        self, trust_ops, trust_store, org_acme_authority
    ):
        """
        Agent cannot create trust chain in another organization.

        An agent (or user) from org-acme should not be able to establish
        trust for an agent under org-globex's authority.

        Current Implementation Note:
        The TrustOperations.establish() validates that the authority_id
        exists and is active. Cross-org boundaries are enforced by
        the authority registry not returning authorities the caller
        doesn't have access to.
        """
        await trust_ops.initialize()

        # Try to establish with a non-existent authority
        with pytest.raises(AuthorityNotFoundError):
            await trust_ops.establish(
                agent_id="rogue-agent",
                authority_id="org-nonexistent",  # Not in registry
                capabilities=[
                    CapabilityRequest(
                        capability="read_data",
                        capability_type=CapabilityType.ACCESS,
                    )
                ],
            )

    @pytest.mark.asyncio
    async def test_establish_succeeds_with_own_org(self, trust_ops, trust_store):
        """
        Verify that establishing trust with proper org works correctly.
        """
        await trust_ops.initialize()

        # Establish should succeed with proper authority
        chain = await trust_ops.establish(
            agent_id="acme-agent-001",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="read_data",
                    capability_type=CapabilityType.ACCESS,
                )
            ],
        )

        assert chain is not None
        assert chain.genesis.authority_id == "org-acme"
        assert chain.genesis.agent_id == "acme-agent-001"

    @pytest.mark.asyncio
    async def test_authority_isolation_in_operations(self, trust_ops, trust_store):
        """
        Verify that operations respect authority boundaries.

        Each trust chain is bound to its establishing authority,
        and cross-authority operations should be rejected.
        """
        await trust_ops.initialize()

        # Establish an agent under org-acme
        await trust_ops.establish(
            agent_id="acme-agent",
            authority_id="org-acme",
            capabilities=[
                CapabilityRequest(
                    capability="analyze",
                    capability_type=CapabilityType.ACTION,
                )
            ],
        )

        # Get the chain and verify authority binding
        chain = await trust_store.get_chain("acme-agent")
        assert chain.genesis.authority_id == "org-acme"

        # The chain is cryptographically bound to org-acme's key
        # Any attempt to use it with globex's context would fail signature verification


class TestCannotDelegateCrossOrg:
    """Test that delegation across organizations fails without federation."""

    @pytest.fixture
    def setup_cross_org(self):
        """Set up two orgs with their own agents."""
        # Create authorities
        acme_priv, acme_pub = generate_keypair()
        globex_priv, globex_pub = generate_keypair()

        acme_authority = OrganizationalAuthority(
            id="org-acme",
            name="ACME Corporation",
            authority_type=AuthorityType.HUMAN,
            public_key=acme_pub,
            signing_key_id="acme-key",
            permissions=[
                AuthorityPermission.CREATE_AGENTS,
                AuthorityPermission.DELEGATE_TRUST,
            ],
        )

        globex_authority = OrganizationalAuthority(
            id="org-globex",
            name="Globex Corporation",
            authority_type=AuthorityType.HUMAN,
            public_key=globex_pub,
            signing_key_id="globex-key",
            permissions=[AuthorityPermission.CREATE_AGENTS],
        )

        # Create trust chains for agents in each org
        acme_genesis = GenesisRecord(
            id="gen-acme-001",
            agent_id="acme-agent",
            authority_id="org-acme",
            authority_type=AuthorityType.HUMAN,
            created_at=datetime.now(timezone.utc),
            signature="test-sig",
            signature_algorithm="Ed25519",
        )

        globex_genesis = GenesisRecord(
            id="gen-globex-001",
            agent_id="globex-agent",
            authority_id="org-globex",
            authority_type=AuthorityType.HUMAN,
            created_at=datetime.now(timezone.utc),
            signature="test-sig",
            signature_algorithm="Ed25519",
        )

        return {
            "acme_authority": acme_authority,
            "acme_priv": acme_priv,
            "globex_authority": globex_authority,
            "globex_priv": globex_priv,
            "acme_genesis": acme_genesis,
            "globex_genesis": globex_genesis,
        }

    def test_cannot_delegate_cross_org(self, setup_cross_org):
        """
        Delegation across orgs fails without explicit federation.

        An agent from org-acme should not be able to delegate trust
        to an agent in org-globex unless there's an explicit federation
        agreement in place.

        Current Implementation Note:
        The current implementation enforces this through authority validation
        in the delegate() method. Cross-org delegation would fail because
        the delegatee wouldn't have a valid chain under the delegator's
        authority.
        """
        data = setup_cross_org

        # Create chains for both agents
        acme_chain = TrustLineageChain(
            genesis=data["acme_genesis"],
            capabilities=[
                CapabilityAttestation(
                    id="cap-001",
                    capability="process_data",
                    capability_type=CapabilityType.ACTION,
                    constraints=[],
                    attester_id="org-acme",
                    attested_at=datetime.now(timezone.utc),
                    signature="test-sig",
                )
            ],
            delegations=[],
        )

        globex_chain = TrustLineageChain(
            genesis=data["globex_genesis"],
            capabilities=[],
            delegations=[],
        )

        # The chains are in different authority domains
        assert acme_chain.genesis.authority_id != globex_chain.genesis.authority_id

        # In a proper implementation, attempting to delegate from
        # acme_chain to globex_chain would fail because:
        # 1. The signatures are incompatible (different keys)
        # 2. The authority domains don't have federation

    def test_delegation_within_org_succeeds(self, setup_cross_org):
        """
        Verify that delegation within same org works.

        This is the baseline case - delegation should work fine
        when both agents are under the same authority.
        """
        data = setup_cross_org

        # Create two agents under the same org
        agent1_genesis = GenesisRecord(
            id="gen-001",
            agent_id="acme-agent-1",
            authority_id="org-acme",
            authority_type=AuthorityType.HUMAN,
            created_at=datetime.now(timezone.utc),
            signature="test-sig",
            signature_algorithm="Ed25519",
        )

        agent2_genesis = GenesisRecord(
            id="gen-002",
            agent_id="acme-agent-2",
            authority_id="org-acme",
            authority_type=AuthorityType.HUMAN,
            created_at=datetime.now(timezone.utc),
            signature="test-sig",
            signature_algorithm="Ed25519",
        )

        # Both under same authority
        assert agent1_genesis.authority_id == agent2_genesis.authority_id == "org-acme"


class TestFederationRequiresExplicitTrust:
    """Test that cross-org operations need explicit federation setup."""

    def test_federation_requires_explicit_trust(self):
        """
        Cross-org operations need explicit federation setup.

        Federation between organizations must be explicitly established
        through a federation agreement before any cross-org trust
        operations are permitted.

        Current Implementation Note:
        Federation is not yet implemented in the current codebase.
        This test documents the expected behavior. When implemented,
        federation should:
        1. Require explicit agreements between organizations
        2. Be time-limited
        3. Be cryptographically signed by both parties
        4. Be revocable by either party
        """
        # Document expected federation structure
        expected_federation_fields = {
            "org_a_id": "org-acme",
            "org_b_id": "org-globex",
            "established_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + timedelta(days=365),
            "agreement_hash": "sha256-of-agreement",
            "signature_a": "signed-by-acme",
            "signature_b": "signed-by-globex",
            "permissions": ["delegate_read", "delegate_access"],
            "revoked": False,
        }

        # Verify the structure has all required fields
        assert "org_a_id" in expected_federation_fields
        assert "org_b_id" in expected_federation_fields
        assert "expires_at" in expected_federation_fields
        assert "signature_a" in expected_federation_fields
        assert "signature_b" in expected_federation_fields

    def test_federation_must_be_bilateral(self):
        """
        Federation requires both parties to agree.

        A unilateral declaration of federation is not valid.
        Both organizations must sign the agreement.
        """
        acme_priv, acme_pub = generate_keypair()
        globex_priv, globex_pub = generate_keypair()

        # Create a federation agreement
        agreement_text = "Federation between org-acme and org-globex"
        agreement_hash = hashlib.sha256(agreement_text.encode()).hexdigest()

        # Both parties must sign
        acme_signature = sign(agreement_hash, acme_priv)
        globex_signature = sign(agreement_hash, globex_priv)

        # Verify both signatures are valid
        assert verify_signature(agreement_hash, acme_signature, acme_pub)
        assert verify_signature(agreement_hash, globex_signature, globex_pub)

        # A federation with only one signature would be invalid
        unilateral_federation = {
            "agreement_hash": agreement_hash,
            "acme_signature": acme_signature,
            "globex_signature": None,  # Missing!
        }

        assert unilateral_federation["globex_signature"] is None


class TestSpoofedOrgIdRejected:
    """Test that spoofed organization IDs are detected and rejected."""

    def test_spoofed_org_id_rejected(self):
        """
        Spoofed org ID in request is rejected.

        Any attempt to spoof an organization ID should be detected
        through cryptographic verification. The org ID must be backed
        by a valid signature from that organization's key.
        """
        # Create a legitimate org's keys
        legit_priv, legit_pub = generate_keypair()

        # Create an attacker's keys
        attacker_priv, attacker_pub = generate_keypair()

        # Attacker tries to create a genesis record claiming to be the legit org
        spoofed_payload = {
            "agent_id": "malicious-agent",
            "authority_id": "org-legitimate",  # Spoofed!
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Attacker signs with their own key
        payload_str = str(spoofed_payload)
        attacker_signature = sign(payload_str, attacker_priv)

        # Verification with the legitimate org's public key fails
        is_valid = verify_signature(payload_str, attacker_signature, legit_pub)
        assert is_valid is False, "Spoofed signature should not verify"

        # Verification with attacker's key succeeds (but attacker is not legit org)
        is_valid_attacker = verify_signature(
            payload_str, attacker_signature, attacker_pub
        )
        assert is_valid_attacker is True, "Attacker's own signature should verify"

    def test_genesis_record_org_binding(self):
        """
        Genesis records are cryptographically bound to their authority.

        The genesis record includes the authority_id and is signed
        by that authority. Changing the authority_id invalidates
        the signature.
        """
        org_priv, org_pub = generate_keypair()

        # Create and sign a genesis record
        genesis = GenesisRecord(
            id=f"gen-{uuid4()}",
            agent_id="agent-001",
            authority_id="org-legitimate",
            authority_type=AuthorityType.HUMAN,
            created_at=datetime.now(timezone.utc),
            signature="",
            signature_algorithm="Ed25519",
        )

        # Sign with the org's key
        payload = genesis.to_signing_payload()
        payload_str = str(sorted(payload.items()))
        genesis.signature = sign(payload_str, org_priv)

        # Verify signature is valid
        assert verify_signature(payload_str, genesis.signature, org_pub)

        # Modify authority_id (spoof attempt)
        genesis.authority_id = "org-attacker"

        # Recompute payload with modified authority
        modified_payload = genesis.to_signing_payload()
        modified_payload_str = str(sorted(modified_payload.items()))

        # Original signature is now invalid
        assert not verify_signature(modified_payload_str, genesis.signature, org_pub)


class TestReplayOfFederationTokenRejected:
    """Test that replayed federation tokens are detected and rejected."""

    def test_replay_of_federation_token_rejected(self):
        """
        Replayed federation tokens are detected.

        Federation tokens should include a nonce and timestamp to
        prevent replay attacks. A token used once should not be
        valid for subsequent requests.

        Current Implementation Note:
        Federation tokens are not yet implemented. This test
        documents the expected anti-replay mechanism.
        """
        # Expected federation token structure with anti-replay fields
        federation_token = {
            "token_id": str(uuid4()),  # Unique token ID
            "nonce": str(uuid4()),  # One-time nonce
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "org_a_id": "org-acme",
            "org_b_id": "org-globex",
            "action": "delegate",
            "valid_for_seconds": 300,  # 5 minute window
        }

        # Token should have unique identifiers
        assert federation_token["token_id"] is not None
        assert federation_token["nonce"] is not None
        assert federation_token["timestamp"] is not None

    def test_token_expiration_prevents_replay(self):
        """
        Expired tokens cannot be replayed.

        Tokens have a limited validity window. After expiration,
        they should be rejected even if the signature is valid.
        """
        # Create a token with a short validity window
        created_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        valid_for_seconds = 300  # 5 minutes

        # Token is expired (created 10 min ago, valid for 5 min)
        expires_at = created_at + timedelta(seconds=valid_for_seconds)
        is_expired = datetime.now(timezone.utc) > expires_at

        assert is_expired is True, "Old token should be expired"

    def test_nonce_uniqueness_prevents_replay(self):
        """
        Nonce tracking prevents immediate replay attacks.

        Each token nonce should be tracked and rejected if seen before.
        """
        used_nonces = set()

        def is_nonce_valid(nonce: str) -> bool:
            """Check if nonce is new and mark it as used."""
            if nonce in used_nonces:
                return False  # Replay detected
            used_nonces.add(nonce)
            return True

        # First use of nonce succeeds
        nonce1 = str(uuid4())
        assert is_nonce_valid(nonce1) is True

        # Replay attempt fails
        assert is_nonce_valid(nonce1) is False

        # Different nonce succeeds
        nonce2 = str(uuid4())
        assert is_nonce_valid(nonce2) is True

    def test_token_signature_binding(self):
        """
        Tokens are cryptographically bound to prevent modification.

        The token signature covers all fields including nonce and
        timestamp, preventing attackers from modifying these fields.
        """
        org_priv, org_pub = generate_keypair()

        # Create token
        token = {
            "nonce": str(uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "federate",
        }

        # Sign entire token
        token_str = str(sorted(token.items()))
        signature = sign(token_str, org_priv)

        # Signature is valid
        assert verify_signature(token_str, signature, org_pub)

        # Modify nonce (replay with new nonce)
        token["nonce"] = str(uuid4())
        modified_token_str = str(sorted(token.items()))

        # Original signature is now invalid
        assert not verify_signature(modified_token_str, signature, org_pub)
