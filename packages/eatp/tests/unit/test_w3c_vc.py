"""
Unit tests for EATP W3C Verifiable Credentials interop module.

Tests cover:
- export_as_verifiable_credential: Full chain export as W3C VC
- export_capability_as_vc: Single capability export as W3C VC
- verify_credential: VC signature verification
- import_from_verifiable_credential: Reconstruct chain from VC
- W3C VC Data Model 2.0 structural compliance
- Ed25519Signature2020 proof type
- Round-trip fidelity (export -> import)
- Error handling for invalid inputs
"""

from datetime import datetime, timezone, timedelta

import pytest

from eatp.chain import (
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    ConstraintEnvelope,
    DelegationRecord,
    GenesisRecord,
    TrustLineageChain,
)
from eatp.crypto import generate_keypair, sign, serialize_for_signing
from eatp.interop.w3c_vc import (
    EATP_CONTEXT_URL,
    W3C_CREDENTIALS_V2_CONTEXT,
    export_as_verifiable_credential,
    export_capability_as_vc,
    import_from_verifiable_credential,
    verify_credential,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def keypair():
    """Generate a fresh Ed25519 key pair for tests."""
    private_key, public_key = generate_keypair()
    return private_key, public_key


@pytest.fixture
def issuer_did():
    """Standard DID for test issuer."""
    return "did:eatp:org:test-authority-001"


@pytest.fixture
def genesis_record(keypair):
    """Create a signed GenesisRecord for testing."""
    private_key, _ = keypair
    now = datetime.now(timezone.utc)
    payload = {
        "id": "gen-001",
        "agent_id": "agent-alpha",
        "authority_id": "authority-001",
        "authority_type": "organization",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(days=365)).isoformat(),
        "metadata": {"department": "engineering"},
    }
    signature = sign(payload, private_key)
    return GenesisRecord(
        id="gen-001",
        agent_id="agent-alpha",
        authority_id="authority-001",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=now,
        expires_at=now + timedelta(days=365),
        signature=signature,
        signature_algorithm="Ed25519",
        metadata={"department": "engineering"},
    )


@pytest.fixture
def capability_attestation(keypair):
    """Create a signed CapabilityAttestation for testing."""
    private_key, _ = keypair
    now = datetime.now(timezone.utc)
    payload = {
        "id": "cap-001",
        "capability": "analyze_financial_data",
        "capability_type": "action",
        "constraints": ["no_pii", "read_only"],
        "attester_id": "authority-001",
        "attested_at": now.isoformat(),
        "expires_at": (now + timedelta(days=90)).isoformat(),
        "scope": {"tables": ["transactions"]},
    }
    signature = sign(payload, private_key)
    return CapabilityAttestation(
        id="cap-001",
        capability="analyze_financial_data",
        capability_type=CapabilityType.ACTION,
        constraints=["read_only", "no_pii"],
        attester_id="authority-001",
        attested_at=now,
        expires_at=now + timedelta(days=90),
        signature=signature,
        scope={"tables": ["transactions"]},
    )


@pytest.fixture
def delegation_record(keypair):
    """Create a signed DelegationRecord for testing."""
    private_key, _ = keypair
    now = datetime.now(timezone.utc)
    payload = {
        "id": "del-001",
        "delegator_id": "agent-alpha",
        "delegatee_id": "agent-beta",
        "task_id": "task-001",
        "capabilities_delegated": ["analyze_financial_data"],
        "constraint_subset": ["read_only"],
        "delegated_at": now.isoformat(),
        "expires_at": (now + timedelta(days=30)).isoformat(),
        "parent_delegation_id": None,
    }
    signature = sign(payload, private_key)
    return DelegationRecord(
        id="del-001",
        delegator_id="agent-alpha",
        delegatee_id="agent-beta",
        task_id="task-001",
        capabilities_delegated=["analyze_financial_data"],
        constraint_subset=["read_only"],
        delegated_at=now,
        expires_at=now + timedelta(days=30),
        signature=signature,
        parent_delegation_id=None,
    )


@pytest.fixture
def trust_chain(genesis_record, capability_attestation, delegation_record):
    """Create a full TrustLineageChain for testing."""
    return TrustLineageChain(
        genesis=genesis_record,
        capabilities=[capability_attestation],
        delegations=[delegation_record],
    )


@pytest.fixture
def minimal_chain(genesis_record):
    """Create a minimal TrustLineageChain with only genesis."""
    return TrustLineageChain(genesis=genesis_record)


# ---------------------------------------------------------------------------
# W3C VC Data Model 2.0 Structural Compliance
# ---------------------------------------------------------------------------


class TestVCStructure:
    """Verify W3C VC Data Model 2.0 structural requirements."""

    def test_context_includes_w3c_v2_and_eatp(self, trust_chain, keypair, issuer_did):
        """VC @context MUST include W3C v2 and EATP custom context."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        assert "@context" in vc
        assert W3C_CREDENTIALS_V2_CONTEXT in vc["@context"]
        assert EATP_CONTEXT_URL in vc["@context"]

    def test_type_includes_verifiable_credential_and_eatp(
        self, trust_chain, keypair, issuer_did
    ):
        """VC type MUST include VerifiableCredential and EATPTrustChain."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        assert "type" in vc
        assert "VerifiableCredential" in vc["type"]
        assert "EATPTrustChain" in vc["type"]

    def test_issuer_is_did_string(self, trust_chain, keypair, issuer_did):
        """VC issuer MUST be the DID string provided."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        assert vc["issuer"] == issuer_did

    def test_valid_from_present(self, trust_chain, keypair, issuer_did):
        """VC MUST have validFrom as ISO 8601 datetime string."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        assert "validFrom" in vc
        # Must be parseable as ISO datetime
        parsed = datetime.fromisoformat(vc["validFrom"])
        assert parsed.tzinfo is not None

    def test_valid_until_present_when_chain_expires(
        self, trust_chain, keypair, issuer_did
    ):
        """VC MUST have validUntil when the chain has an expiration."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        assert "validUntil" in vc
        parsed = datetime.fromisoformat(vc["validUntil"])
        assert parsed.tzinfo is not None

    def test_no_valid_until_when_chain_never_expires(self, keypair, issuer_did):
        """VC MUST NOT have validUntil when the chain has no expiration."""
        private_key, _ = keypair
        now = datetime.now(timezone.utc)
        payload = {
            "id": "gen-noexpiry",
            "agent_id": "agent-permanent",
            "authority_id": "authority-001",
            "authority_type": "organization",
            "created_at": now.isoformat(),
            "expires_at": None,
            "metadata": {},
        }
        signature = sign(payload, private_key)
        genesis = GenesisRecord(
            id="gen-noexpiry",
            agent_id="agent-permanent",
            authority_id="authority-001",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=now,
            expires_at=None,
            signature=signature,
        )
        chain = TrustLineageChain(genesis=genesis)
        vc = export_as_verifiable_credential(chain, issuer_did, private_key)

        assert "validUntil" not in vc

    def test_credential_subject_contains_chain_data(
        self, trust_chain, keypair, issuer_did
    ):
        """VC credentialSubject MUST contain EATP chain data."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        subject = vc["credentialSubject"]
        assert "genesis" in subject
        assert "capabilities" in subject
        assert "delegations" in subject
        assert "chainHash" in subject

    def test_credential_subject_genesis_fields(self, trust_chain, keypair, issuer_did):
        """VC credentialSubject genesis MUST contain all genesis fields."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        genesis = vc["credentialSubject"]["genesis"]
        assert genesis["id"] == "gen-001"
        assert genesis["agentId"] == "agent-alpha"
        assert genesis["authorityId"] == "authority-001"
        assert genesis["authorityType"] == "organization"
        assert "createdAt" in genesis
        assert "signatureAlgorithm" in genesis

    def test_credential_subject_capabilities_fields(
        self, trust_chain, keypair, issuer_did
    ):
        """VC credentialSubject capabilities MUST contain all capability fields."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        caps = vc["credentialSubject"]["capabilities"]
        assert len(caps) == 1
        cap = caps[0]
        assert cap["id"] == "cap-001"
        assert cap["capability"] == "analyze_financial_data"
        assert cap["capabilityType"] == "action"
        assert cap["attesterId"] == "authority-001"
        assert "attestedAt" in cap

    def test_credential_subject_delegations_fields(
        self, trust_chain, keypair, issuer_did
    ):
        """VC credentialSubject delegations MUST contain all delegation fields."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        delegations = vc["credentialSubject"]["delegations"]
        assert len(delegations) == 1
        d = delegations[0]
        assert d["id"] == "del-001"
        assert d["delegatorId"] == "agent-alpha"
        assert d["delegateeId"] == "agent-beta"
        assert d["taskId"] == "task-001"

    def test_id_field_present_and_urn(self, trust_chain, keypair, issuer_did):
        """VC MUST have an id field in URN format."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        assert "id" in vc
        assert vc["id"].startswith("urn:eatp:vc:")


# ---------------------------------------------------------------------------
# Ed25519Signature2020 Proof
# ---------------------------------------------------------------------------


class TestProof:
    """Verify Ed25519Signature2020 proof type compliance."""

    def test_proof_present(self, trust_chain, keypair, issuer_did):
        """VC MUST contain a proof object."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        assert "proof" in vc

    def test_proof_type_is_ed25519(self, trust_chain, keypair, issuer_did):
        """Proof type MUST be Ed25519Signature2020."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        assert vc["proof"]["type"] == "Ed25519Signature2020"

    def test_proof_verification_method(self, trust_chain, keypair, issuer_did):
        """Proof MUST reference the issuer's verification method."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        assert vc["proof"]["verificationMethod"].startswith(issuer_did)

    def test_proof_created_timestamp(self, trust_chain, keypair, issuer_did):
        """Proof MUST have a created timestamp."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        assert "created" in vc["proof"]
        parsed = datetime.fromisoformat(vc["proof"]["created"])
        assert parsed.tzinfo is not None

    def test_proof_purpose(self, trust_chain, keypair, issuer_did):
        """Proof MUST have proofPurpose assertionMethod."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        assert vc["proof"]["proofPurpose"] == "assertionMethod"

    def test_proof_value_is_base64(self, trust_chain, keypair, issuer_did):
        """Proof proofValue MUST be a base64-encoded Ed25519 signature."""
        import base64

        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        proof_value = vc["proof"]["proofValue"]
        assert len(proof_value) > 0
        # Must be valid base64
        decoded = base64.b64decode(proof_value)
        # Ed25519 signatures are 64 bytes
        assert len(decoded) == 64


# ---------------------------------------------------------------------------
# export_as_verifiable_credential
# ---------------------------------------------------------------------------


class TestExportChainAsVC:
    """Tests for export_as_verifiable_credential function."""

    def test_export_full_chain(self, trust_chain, keypair, issuer_did):
        """Exporting a full chain should produce a valid VC."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        assert isinstance(vc, dict)
        assert vc["type"] == ["VerifiableCredential", "EATPTrustChain"]

    def test_export_minimal_chain(self, minimal_chain, keypair, issuer_did):
        """Exporting a chain with only genesis should produce a valid VC."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(minimal_chain, issuer_did, private_key)

        assert vc["credentialSubject"]["capabilities"] == []
        assert vc["credentialSubject"]["delegations"] == []

    def test_export_preserves_chain_hash(self, trust_chain, keypair, issuer_did):
        """Exported VC should contain the chain hash."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        expected_hash = trust_chain.hash()
        assert vc["credentialSubject"]["chainHash"] == expected_hash

    def test_export_raises_on_empty_issuer_did(self, trust_chain, keypair):
        """export_as_verifiable_credential MUST raise on empty issuer DID."""
        private_key, _ = keypair
        with pytest.raises(ValueError, match="issuer_did"):
            export_as_verifiable_credential(trust_chain, "", private_key)

    def test_export_raises_on_invalid_signing_key(self, trust_chain, issuer_did):
        """export_as_verifiable_credential MUST raise on invalid signing key."""
        with pytest.raises(ValueError, match="signing_key"):
            export_as_verifiable_credential(trust_chain, issuer_did, "not-a-valid-key")

    def test_export_constraint_envelope_when_present(
        self, trust_chain, keypair, issuer_did
    ):
        """Exported VC should include constraint envelope data when present."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        subject = vc["credentialSubject"]
        assert "constraintEnvelope" in subject


# ---------------------------------------------------------------------------
# export_capability_as_vc
# ---------------------------------------------------------------------------


class TestExportCapabilityAsVC:
    """Tests for export_capability_as_vc function."""

    def test_export_single_capability(
        self, capability_attestation, keypair, issuer_did
    ):
        """Exporting a single capability should produce a valid VC."""
        private_key, _ = keypair
        vc = export_capability_as_vc(capability_attestation, issuer_did, private_key)

        assert isinstance(vc, dict)
        assert "VerifiableCredential" in vc["type"]
        assert "EATPCapabilityAttestation" in vc["type"]

    def test_capability_vc_context(self, capability_attestation, keypair, issuer_did):
        """Capability VC MUST have correct @context."""
        private_key, _ = keypair
        vc = export_capability_as_vc(capability_attestation, issuer_did, private_key)

        assert W3C_CREDENTIALS_V2_CONTEXT in vc["@context"]
        assert EATP_CONTEXT_URL in vc["@context"]

    def test_capability_vc_credential_subject(
        self, capability_attestation, keypair, issuer_did
    ):
        """Capability VC credentialSubject MUST contain capability data."""
        private_key, _ = keypair
        vc = export_capability_as_vc(capability_attestation, issuer_did, private_key)

        subject = vc["credentialSubject"]
        assert subject["id"] == "cap-001"
        assert subject["capability"] == "analyze_financial_data"
        assert subject["capabilityType"] == "action"
        assert subject["attesterId"] == "authority-001"
        assert "constraints" in subject

    def test_capability_vc_has_proof(self, capability_attestation, keypair, issuer_did):
        """Capability VC MUST have Ed25519 proof."""
        private_key, _ = keypair
        vc = export_capability_as_vc(capability_attestation, issuer_did, private_key)

        assert "proof" in vc
        assert vc["proof"]["type"] == "Ed25519Signature2020"

    def test_capability_vc_valid_from(
        self, capability_attestation, keypair, issuer_did
    ):
        """Capability VC MUST have validFrom matching attested_at."""
        private_key, _ = keypair
        vc = export_capability_as_vc(capability_attestation, issuer_did, private_key)

        assert "validFrom" in vc
        valid_from = datetime.fromisoformat(vc["validFrom"])
        assert valid_from == capability_attestation.attested_at

    def test_capability_vc_valid_until_when_expires(
        self, capability_attestation, keypair, issuer_did
    ):
        """Capability VC MUST have validUntil when capability expires."""
        private_key, _ = keypair
        vc = export_capability_as_vc(capability_attestation, issuer_did, private_key)

        assert "validUntil" in vc
        valid_until = datetime.fromisoformat(vc["validUntil"])
        assert valid_until == capability_attestation.expires_at

    def test_capability_vc_raises_on_empty_did(self, capability_attestation, keypair):
        """export_capability_as_vc MUST raise on empty issuer DID."""
        private_key, _ = keypair
        with pytest.raises(ValueError, match="issuer_did"):
            export_capability_as_vc(capability_attestation, "", private_key)


# ---------------------------------------------------------------------------
# verify_credential
# ---------------------------------------------------------------------------


class TestVerifyCredential:
    """Tests for verify_credential function."""

    def test_verify_valid_chain_vc(self, trust_chain, keypair, issuer_did):
        """verify_credential MUST return True for a valid VC."""
        private_key, public_key = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        assert verify_credential(vc, public_key) is True

    def test_verify_valid_capability_vc(
        self, capability_attestation, keypair, issuer_did
    ):
        """verify_credential MUST return True for a valid capability VC."""
        private_key, public_key = keypair
        vc = export_capability_as_vc(capability_attestation, issuer_did, private_key)

        assert verify_credential(vc, public_key) is True

    def test_verify_tampered_credential_subject(self, trust_chain, keypair, issuer_did):
        """verify_credential MUST return False when credentialSubject is tampered."""
        private_key, public_key = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        # Tamper with the credential subject
        vc["credentialSubject"]["chainHash"] = "tampered_hash_value"

        assert verify_credential(vc, public_key) is False

    def test_verify_tampered_issuer(self, trust_chain, keypair, issuer_did):
        """verify_credential MUST return False when issuer is tampered."""
        private_key, public_key = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        vc["issuer"] = "did:eatp:org:attacker"

        assert verify_credential(vc, public_key) is False

    def test_verify_wrong_public_key(self, trust_chain, keypair, issuer_did):
        """verify_credential MUST return False with wrong public key."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        # Generate a different key pair
        _, wrong_public_key = generate_keypair()

        assert verify_credential(vc, wrong_public_key) is False

    def test_verify_missing_proof(self, trust_chain, keypair, issuer_did):
        """verify_credential MUST raise when proof is missing."""
        private_key, public_key = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        del vc["proof"]

        with pytest.raises(ValueError, match="proof"):
            verify_credential(vc, public_key)

    def test_verify_missing_proof_value(self, trust_chain, keypair, issuer_did):
        """verify_credential MUST raise when proofValue is missing."""
        private_key, public_key = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        del vc["proof"]["proofValue"]

        with pytest.raises(ValueError, match="proofValue"):
            verify_credential(vc, public_key)

    def test_verify_invalid_public_key(self, trust_chain, keypair, issuer_did):
        """verify_credential MUST raise on invalid public key format."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        with pytest.raises(ValueError, match="public_key"):
            verify_credential(vc, "not-a-valid-key!!!")

    def test_verify_empty_public_key(self, trust_chain, keypair, issuer_did):
        """verify_credential MUST raise on empty public key."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        with pytest.raises(ValueError, match="public_key"):
            verify_credential(vc, "")


# ---------------------------------------------------------------------------
# import_from_verifiable_credential
# ---------------------------------------------------------------------------


class TestImportFromVC:
    """Tests for import_from_verifiable_credential function."""

    def test_round_trip_full_chain(self, trust_chain, keypair, issuer_did):
        """Exporting then importing should reconstruct an equivalent chain."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        imported = import_from_verifiable_credential(vc)

        assert isinstance(imported, TrustLineageChain)
        assert imported.genesis.id == trust_chain.genesis.id
        assert imported.genesis.agent_id == trust_chain.genesis.agent_id
        assert imported.genesis.authority_id == trust_chain.genesis.authority_id
        assert imported.genesis.authority_type == trust_chain.genesis.authority_type
        assert (
            imported.genesis.signature_algorithm
            == trust_chain.genesis.signature_algorithm
        )

    def test_round_trip_capabilities(self, trust_chain, keypair, issuer_did):
        """Imported chain should have same capabilities."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        imported = import_from_verifiable_credential(vc)

        assert len(imported.capabilities) == len(trust_chain.capabilities)
        for imp_cap, orig_cap in zip(imported.capabilities, trust_chain.capabilities):
            assert imp_cap.id == orig_cap.id
            assert imp_cap.capability == orig_cap.capability
            assert imp_cap.capability_type == orig_cap.capability_type
            assert imp_cap.attester_id == orig_cap.attester_id

    def test_round_trip_delegations(self, trust_chain, keypair, issuer_did):
        """Imported chain should have same delegations."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        imported = import_from_verifiable_credential(vc)

        assert len(imported.delegations) == len(trust_chain.delegations)
        for imp_del, orig_del in zip(imported.delegations, trust_chain.delegations):
            assert imp_del.id == orig_del.id
            assert imp_del.delegator_id == orig_del.delegator_id
            assert imp_del.delegatee_id == orig_del.delegatee_id
            assert imp_del.task_id == orig_del.task_id

    def test_round_trip_minimal_chain(self, minimal_chain, keypair, issuer_did):
        """Minimal chain (genesis only) should round-trip correctly."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(minimal_chain, issuer_did, private_key)

        imported = import_from_verifiable_credential(vc)

        assert imported.genesis.id == minimal_chain.genesis.id
        assert len(imported.capabilities) == 0
        assert len(imported.delegations) == 0

    def test_round_trip_chain_hash_matches(self, trust_chain, keypair, issuer_did):
        """Imported chain hash should match original."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        imported = import_from_verifiable_credential(vc)

        assert imported.hash() == trust_chain.hash()

    def test_import_raises_on_missing_context(self, trust_chain, keypair, issuer_did):
        """import_from_verifiable_credential MUST raise when @context is wrong."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        vc["@context"] = ["https://example.com/wrong"]

        with pytest.raises(ValueError, match="context"):
            import_from_verifiable_credential(vc)

    def test_import_raises_on_missing_type(self, trust_chain, keypair, issuer_did):
        """import_from_verifiable_credential MUST raise when type is wrong."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        vc["type"] = ["VerifiableCredential"]

        with pytest.raises(ValueError, match="type"):
            import_from_verifiable_credential(vc)

    def test_import_raises_on_missing_credential_subject(
        self, trust_chain, keypair, issuer_did
    ):
        """import_from_verifiable_credential MUST raise when credentialSubject missing."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        del vc["credentialSubject"]

        with pytest.raises(ValueError, match="credentialSubject"):
            import_from_verifiable_credential(vc)

    def test_import_raises_on_missing_genesis(self, trust_chain, keypair, issuer_did):
        """import_from_verifiable_credential MUST raise when genesis missing."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        del vc["credentialSubject"]["genesis"]

        with pytest.raises(ValueError, match="genesis"):
            import_from_verifiable_credential(vc)


# ---------------------------------------------------------------------------
# Edge Cases and Error Handling
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_export_with_multiple_capabilities(self, keypair, issuer_did):
        """Chain with multiple capabilities should export all of them."""
        private_key, _ = keypair
        now = datetime.now(timezone.utc)
        genesis = GenesisRecord(
            id="gen-multi",
            agent_id="agent-multi",
            authority_id="authority-001",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=now,
            signature=sign(
                {
                    "id": "gen-multi",
                    "agent_id": "agent-multi",
                    "authority_id": "authority-001",
                    "authority_type": "organization",
                    "created_at": now.isoformat(),
                    "expires_at": None,
                    "metadata": {},
                },
                private_key,
            ),
        )
        cap1 = CapabilityAttestation(
            id="cap-a",
            capability="read_data",
            capability_type=CapabilityType.ACCESS,
            constraints=["read_only"],
            attester_id="authority-001",
            attested_at=now,
            signature=sign({"id": "cap-a"}, private_key),
        )
        cap2 = CapabilityAttestation(
            id="cap-b",
            capability="write_data",
            capability_type=CapabilityType.ACTION,
            constraints=[],
            attester_id="authority-001",
            attested_at=now,
            signature=sign({"id": "cap-b"}, private_key),
        )
        chain = TrustLineageChain(
            genesis=genesis,
            capabilities=[cap1, cap2],
        )

        vc = export_as_verifiable_credential(chain, issuer_did, private_key)

        assert len(vc["credentialSubject"]["capabilities"]) == 2

    def test_export_with_multiple_delegations(self, keypair, issuer_did):
        """Chain with multiple delegations should export all of them."""
        private_key, _ = keypair
        now = datetime.now(timezone.utc)
        genesis = GenesisRecord(
            id="gen-multi-del",
            agent_id="agent-root",
            authority_id="authority-001",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=now,
            signature=sign(
                {
                    "id": "gen-multi-del",
                    "agent_id": "agent-root",
                    "authority_id": "authority-001",
                    "authority_type": "organization",
                    "created_at": now.isoformat(),
                    "expires_at": None,
                    "metadata": {},
                },
                private_key,
            ),
        )
        del1 = DelegationRecord(
            id="del-a",
            delegator_id="agent-root",
            delegatee_id="agent-one",
            task_id="task-a",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=now,
            signature=sign({"id": "del-a"}, private_key),
        )
        del2 = DelegationRecord(
            id="del-b",
            delegator_id="agent-root",
            delegatee_id="agent-two",
            task_id="task-b",
            capabilities_delegated=["write_data"],
            constraint_subset=["audit_required"],
            delegated_at=now,
            signature=sign({"id": "del-b"}, private_key),
            parent_delegation_id="del-a",
        )
        chain = TrustLineageChain(
            genesis=genesis,
            delegations=[del1, del2],
        )

        vc = export_as_verifiable_credential(chain, issuer_did, private_key)

        assert len(vc["credentialSubject"]["delegations"]) == 2

    def test_export_deterministic_for_same_input(
        self, trust_chain, keypair, issuer_did
    ):
        """Two exports of the same chain should produce structurally equivalent VCs
        (proof values will differ due to timestamp)."""
        private_key, _ = keypair
        vc1 = export_as_verifiable_credential(trust_chain, issuer_did, private_key)
        vc2 = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        # Same credential subject
        assert vc1["credentialSubject"] == vc2["credentialSubject"]
        # Same issuer
        assert vc1["issuer"] == vc2["issuer"]
        # Same type
        assert vc1["type"] == vc2["type"]

    def test_verify_then_import_roundtrip(self, trust_chain, keypair, issuer_did):
        """Full workflow: export, verify, then import."""
        private_key, public_key = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        # Verify first
        assert verify_credential(vc, public_key) is True

        # Then import
        imported = import_from_verifiable_credential(vc)
        assert imported.genesis.agent_id == "agent-alpha"

    def test_capability_vc_scope_preserved(
        self, capability_attestation, keypair, issuer_did
    ):
        """Capability VC should preserve scope data in credentialSubject."""
        private_key, _ = keypair
        vc = export_capability_as_vc(capability_attestation, issuer_did, private_key)

        assert vc["credentialSubject"]["scope"] == {"tables": ["transactions"]}

    def test_genesis_metadata_preserved_in_export(
        self, trust_chain, keypair, issuer_did
    ):
        """Genesis metadata should be preserved in the VC export."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        genesis = vc["credentialSubject"]["genesis"]
        assert genesis["metadata"] == {"department": "engineering"}


# ---------------------------------------------------------------------------
# Reasoning Trace in W3C VC (TODO-013)
# ---------------------------------------------------------------------------


class TestReasoningTraceExport:
    """Tests for reasoning trace inclusion in W3C VC exports."""

    def test_export_delegation_with_public_reasoning_trace(self, keypair, issuer_did):
        """Export MUST include full reasoning trace when confidentiality is PUBLIC."""
        private_key, _ = keypair
        now = datetime.now(timezone.utc)
        from eatp.reasoning import ConfidentialityLevel, ReasoningTrace

        trace = ReasoningTrace(
            decision="Delegate financial analysis to agent-beta",
            rationale="Agent-beta has verified financial analysis capabilities",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=now,
            alternatives_considered=["agent-gamma", "agent-delta"],
            evidence=[{"type": "capability_match", "score": 0.95}],
            methodology="capability_matching",
            confidence=0.92,
        )
        genesis = GenesisRecord(
            id="gen-rt-pub",
            agent_id="agent-alpha",
            authority_id="authority-001",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=now,
            signature=sign(
                {"id": "gen-rt-pub", "agent_id": "agent-alpha",
                 "authority_id": "authority-001", "authority_type": "organization",
                 "created_at": now.isoformat(), "expires_at": None, "metadata": {}},
                private_key,
            ),
        )
        delegation = DelegationRecord(
            id="del-rt-pub",
            delegator_id="agent-alpha",
            delegatee_id="agent-beta",
            task_id="task-001",
            capabilities_delegated=["analyze_financial_data"],
            constraint_subset=["read_only"],
            delegated_at=now,
            signature=sign({"id": "del-rt-pub"}, private_key),
            reasoning_trace=trace,
            reasoning_trace_hash="sha256-abc123",
            reasoning_signature="sig-reasoning-001",
        )
        chain = TrustLineageChain(
            genesis=genesis,
            delegations=[delegation],
        )

        vc = export_as_verifiable_credential(chain, issuer_did, private_key)
        d = vc["credentialSubject"]["delegations"][0]

        # Full reasoning trace MUST be present for PUBLIC confidentiality
        assert "reasoning" in d
        reasoning = d["reasoning"]
        assert reasoning["decision"] == "Delegate financial analysis to agent-beta"
        assert reasoning["rationale"] == "Agent-beta has verified financial analysis capabilities"
        assert reasoning["confidentiality"] == "public"
        assert reasoning["methodology"] == "capability_matching"
        assert reasoning["confidence"] == 0.92
        assert reasoning["alternativesConsidered"] == ["agent-gamma", "agent-delta"]
        assert reasoning["evidence"] == [{"type": "capability_match", "score": 0.95}]

        # Hash and signature MUST always be present
        assert d["reasoningTraceHash"] == "sha256-abc123"
        assert d["reasoningSignature"] == "sig-reasoning-001"

    def test_export_delegation_with_restricted_reasoning_trace(self, keypair, issuer_did):
        """Export MUST include full reasoning trace when confidentiality is RESTRICTED."""
        private_key, _ = keypair
        now = datetime.now(timezone.utc)
        from eatp.reasoning import ConfidentialityLevel, ReasoningTrace

        trace = ReasoningTrace(
            decision="Delegate to agent-beta",
            rationale="Restricted rationale",
            confidentiality=ConfidentialityLevel.RESTRICTED,
            timestamp=now,
        )
        genesis = GenesisRecord(
            id="gen-rt-restr",
            agent_id="agent-alpha",
            authority_id="authority-001",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=now,
            signature=sign(
                {"id": "gen-rt-restr", "agent_id": "agent-alpha",
                 "authority_id": "authority-001", "authority_type": "organization",
                 "created_at": now.isoformat(), "expires_at": None, "metadata": {}},
                private_key,
            ),
        )
        delegation = DelegationRecord(
            id="del-rt-restr",
            delegator_id="agent-alpha",
            delegatee_id="agent-beta",
            task_id="task-002",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=now,
            signature=sign({"id": "del-rt-restr"}, private_key),
            reasoning_trace=trace,
            reasoning_trace_hash="sha256-restricted",
            reasoning_signature="sig-reasoning-restricted",
        )
        chain = TrustLineageChain(
            genesis=genesis,
            delegations=[delegation],
        )

        vc = export_as_verifiable_credential(chain, issuer_did, private_key)
        d = vc["credentialSubject"]["delegations"][0]

        # Full reasoning trace MUST be present for RESTRICTED confidentiality
        assert "reasoning" in d
        assert d["reasoning"]["decision"] == "Delegate to agent-beta"
        assert d["reasoning"]["confidentiality"] == "restricted"
        assert d["reasoningTraceHash"] == "sha256-restricted"
        assert d["reasoningSignature"] == "sig-reasoning-restricted"

    def test_export_delegation_with_confidential_reasoning_trace(self, keypair, issuer_did):
        """Export MUST include only hash for CONFIDENTIAL reasoning trace (selective disclosure)."""
        private_key, _ = keypair
        now = datetime.now(timezone.utc)
        from eatp.reasoning import ConfidentialityLevel, ReasoningTrace

        trace = ReasoningTrace(
            decision="Confidential decision about security posture",
            rationale="Classified business reasoning",
            confidentiality=ConfidentialityLevel.CONFIDENTIAL,
            timestamp=now,
            methodology="risk_assessment",
            confidence=0.88,
        )
        genesis = GenesisRecord(
            id="gen-rt-conf",
            agent_id="agent-alpha",
            authority_id="authority-001",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=now,
            signature=sign(
                {"id": "gen-rt-conf", "agent_id": "agent-alpha",
                 "authority_id": "authority-001", "authority_type": "organization",
                 "created_at": now.isoformat(), "expires_at": None, "metadata": {}},
                private_key,
            ),
        )
        delegation = DelegationRecord(
            id="del-rt-conf",
            delegator_id="agent-alpha",
            delegatee_id="agent-beta",
            task_id="task-003",
            capabilities_delegated=["manage_security"],
            constraint_subset=[],
            delegated_at=now,
            signature=sign({"id": "del-rt-conf"}, private_key),
            reasoning_trace=trace,
            reasoning_trace_hash="sha256-confidential",
            reasoning_signature="sig-reasoning-confidential",
        )
        chain = TrustLineageChain(
            genesis=genesis,
            delegations=[delegation],
        )

        vc = export_as_verifiable_credential(chain, issuer_did, private_key)
        d = vc["credentialSubject"]["delegations"][0]

        # Full reasoning trace MUST NOT be present for CONFIDENTIAL
        assert "reasoning" not in d

        # Hash and signature MUST still be present (they are not confidential)
        assert d["reasoningTraceHash"] == "sha256-confidential"
        assert d["reasoningSignature"] == "sig-reasoning-confidential"

    def test_export_delegation_with_secret_reasoning_trace(self, keypair, issuer_did):
        """Export MUST include only hash for SECRET reasoning trace."""
        private_key, _ = keypair
        now = datetime.now(timezone.utc)
        from eatp.reasoning import ConfidentialityLevel, ReasoningTrace

        trace = ReasoningTrace(
            decision="Secret operational decision",
            rationale="Top-level classified reasoning",
            confidentiality=ConfidentialityLevel.SECRET,
            timestamp=now,
        )
        genesis = GenesisRecord(
            id="gen-rt-sec",
            agent_id="agent-alpha",
            authority_id="authority-001",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=now,
            signature=sign(
                {"id": "gen-rt-sec", "agent_id": "agent-alpha",
                 "authority_id": "authority-001", "authority_type": "organization",
                 "created_at": now.isoformat(), "expires_at": None, "metadata": {}},
                private_key,
            ),
        )
        delegation = DelegationRecord(
            id="del-rt-sec",
            delegator_id="agent-alpha",
            delegatee_id="agent-beta",
            task_id="task-004",
            capabilities_delegated=["critical_ops"],
            constraint_subset=[],
            delegated_at=now,
            signature=sign({"id": "del-rt-sec"}, private_key),
            reasoning_trace=trace,
            reasoning_trace_hash="sha256-secret",
            reasoning_signature="sig-reasoning-secret",
        )
        chain = TrustLineageChain(
            genesis=genesis,
            delegations=[delegation],
        )

        vc = export_as_verifiable_credential(chain, issuer_did, private_key)
        d = vc["credentialSubject"]["delegations"][0]

        # Full reasoning trace MUST NOT be present for SECRET
        assert "reasoning" not in d
        # Hash and signature are always present
        assert d["reasoningTraceHash"] == "sha256-secret"
        assert d["reasoningSignature"] == "sig-reasoning-secret"

    def test_export_delegation_with_top_secret_reasoning_trace(self, keypair, issuer_did):
        """Export MUST include only hash for TOP_SECRET reasoning trace."""
        private_key, _ = keypair
        now = datetime.now(timezone.utc)
        from eatp.reasoning import ConfidentialityLevel, ReasoningTrace

        trace = ReasoningTrace(
            decision="Top secret decision",
            rationale="Ultra-classified reasoning",
            confidentiality=ConfidentialityLevel.TOP_SECRET,
            timestamp=now,
        )
        genesis = GenesisRecord(
            id="gen-rt-ts",
            agent_id="agent-alpha",
            authority_id="authority-001",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=now,
            signature=sign(
                {"id": "gen-rt-ts", "agent_id": "agent-alpha",
                 "authority_id": "authority-001", "authority_type": "organization",
                 "created_at": now.isoformat(), "expires_at": None, "metadata": {}},
                private_key,
            ),
        )
        delegation = DelegationRecord(
            id="del-rt-ts",
            delegator_id="agent-alpha",
            delegatee_id="agent-beta",
            task_id="task-005",
            capabilities_delegated=["critical_infra"],
            constraint_subset=[],
            delegated_at=now,
            signature=sign({"id": "del-rt-ts"}, private_key),
            reasoning_trace=trace,
            reasoning_trace_hash="sha256-topsecret",
            reasoning_signature="sig-reasoning-topsecret",
        )
        chain = TrustLineageChain(
            genesis=genesis,
            delegations=[delegation],
        )

        vc = export_as_verifiable_credential(chain, issuer_did, private_key)
        d = vc["credentialSubject"]["delegations"][0]

        # Full reasoning trace MUST NOT be present for TOP_SECRET
        assert "reasoning" not in d
        assert d["reasoningTraceHash"] == "sha256-topsecret"
        assert d["reasoningSignature"] == "sig-reasoning-topsecret"

    def test_export_delegation_without_reasoning_trace(self, trust_chain, keypair, issuer_did):
        """Export MUST NOT include reasoning fields when delegation has no trace."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)
        d = vc["credentialSubject"]["delegations"][0]

        # No reasoning fields when trace is absent
        assert "reasoning" not in d
        assert "reasoningTraceHash" not in d
        assert "reasoningSignature" not in d

    def test_export_hash_and_signature_without_full_trace(self, keypair, issuer_did):
        """Export MUST include hash/signature even when reasoning_trace object is None
        but hash and signature are set (e.g., received from upstream)."""
        private_key, _ = keypair
        now = datetime.now(timezone.utc)
        genesis = GenesisRecord(
            id="gen-rt-hashonly",
            agent_id="agent-alpha",
            authority_id="authority-001",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=now,
            signature=sign(
                {"id": "gen-rt-hashonly", "agent_id": "agent-alpha",
                 "authority_id": "authority-001", "authority_type": "organization",
                 "created_at": now.isoformat(), "expires_at": None, "metadata": {}},
                private_key,
            ),
        )
        delegation = DelegationRecord(
            id="del-rt-hashonly",
            delegator_id="agent-alpha",
            delegatee_id="agent-beta",
            task_id="task-hashonly",
            capabilities_delegated=["read_data"],
            constraint_subset=[],
            delegated_at=now,
            signature=sign({"id": "del-rt-hashonly"}, private_key),
            reasoning_trace=None,
            reasoning_trace_hash="sha256-upstream-hash",
            reasoning_signature="sig-upstream",
        )
        chain = TrustLineageChain(
            genesis=genesis,
            delegations=[delegation],
        )

        vc = export_as_verifiable_credential(chain, issuer_did, private_key)
        d = vc["credentialSubject"]["delegations"][0]

        assert "reasoning" not in d
        assert d["reasoningTraceHash"] == "sha256-upstream-hash"
        assert d["reasoningSignature"] == "sig-upstream"


class TestReasoningTraceImport:
    """Tests for reasoning trace restoration from W3C VCs."""

    def test_import_delegation_with_full_reasoning_trace(self, keypair, issuer_did):
        """Import MUST restore full reasoning trace from VC credentialSubject."""
        private_key, _ = keypair
        now = datetime.now(timezone.utc)
        from eatp.reasoning import ConfidentialityLevel, ReasoningTrace

        trace = ReasoningTrace(
            decision="Delegate financial analysis",
            rationale="Best capability match",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=now,
            alternatives_considered=["agent-gamma"],
            evidence=[{"type": "score", "value": 0.95}],
            methodology="capability_matching",
            confidence=0.91,
        )
        genesis = GenesisRecord(
            id="gen-imp-rt",
            agent_id="agent-alpha",
            authority_id="authority-001",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=now,
            signature=sign(
                {"id": "gen-imp-rt", "agent_id": "agent-alpha",
                 "authority_id": "authority-001", "authority_type": "organization",
                 "created_at": now.isoformat(), "expires_at": None, "metadata": {}},
                private_key,
            ),
        )
        delegation = DelegationRecord(
            id="del-imp-rt",
            delegator_id="agent-alpha",
            delegatee_id="agent-beta",
            task_id="task-imp",
            capabilities_delegated=["analyze_financial_data"],
            constraint_subset=["read_only"],
            delegated_at=now,
            signature=sign({"id": "del-imp-rt"}, private_key),
            reasoning_trace=trace,
            reasoning_trace_hash="sha256-import-hash",
            reasoning_signature="sig-import",
        )
        chain = TrustLineageChain(
            genesis=genesis,
            delegations=[delegation],
        )

        vc = export_as_verifiable_credential(chain, issuer_did, private_key)
        imported = import_from_verifiable_credential(vc)

        imp_del = imported.delegations[0]
        assert imp_del.reasoning_trace is not None
        assert imp_del.reasoning_trace.decision == "Delegate financial analysis"
        assert imp_del.reasoning_trace.rationale == "Best capability match"
        assert imp_del.reasoning_trace.confidentiality == ConfidentialityLevel.PUBLIC
        assert imp_del.reasoning_trace.methodology == "capability_matching"
        assert imp_del.reasoning_trace.confidence == 0.91
        assert imp_del.reasoning_trace.alternatives_considered == ["agent-gamma"]
        assert imp_del.reasoning_trace.evidence == [{"type": "score", "value": 0.95}]
        assert imp_del.reasoning_trace_hash == "sha256-import-hash"
        assert imp_del.reasoning_signature == "sig-import"

    def test_import_delegation_with_hash_only(self, keypair, issuer_did):
        """Import MUST restore hash and signature even when full trace is withheld (CONFIDENTIAL+)."""
        private_key, _ = keypair
        now = datetime.now(timezone.utc)
        from eatp.reasoning import ConfidentialityLevel, ReasoningTrace

        trace = ReasoningTrace(
            decision="Confidential decision",
            rationale="Classified reasoning",
            confidentiality=ConfidentialityLevel.CONFIDENTIAL,
            timestamp=now,
        )
        genesis = GenesisRecord(
            id="gen-imp-hashonly",
            agent_id="agent-alpha",
            authority_id="authority-001",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=now,
            signature=sign(
                {"id": "gen-imp-hashonly", "agent_id": "agent-alpha",
                 "authority_id": "authority-001", "authority_type": "organization",
                 "created_at": now.isoformat(), "expires_at": None, "metadata": {}},
                private_key,
            ),
        )
        delegation = DelegationRecord(
            id="del-imp-hashonly",
            delegator_id="agent-alpha",
            delegatee_id="agent-beta",
            task_id="task-conf",
            capabilities_delegated=["manage_security"],
            constraint_subset=[],
            delegated_at=now,
            signature=sign({"id": "del-imp-hashonly"}, private_key),
            reasoning_trace=trace,
            reasoning_trace_hash="sha256-conf-hash",
            reasoning_signature="sig-conf",
        )
        chain = TrustLineageChain(
            genesis=genesis,
            delegations=[delegation],
        )

        vc = export_as_verifiable_credential(chain, issuer_did, private_key)
        imported = import_from_verifiable_credential(vc)

        imp_del = imported.delegations[0]
        # Full trace was withheld at export due to CONFIDENTIAL level
        assert imp_del.reasoning_trace is None
        # But hash and signature survive the round-trip
        assert imp_del.reasoning_trace_hash == "sha256-conf-hash"
        assert imp_del.reasoning_signature == "sig-conf"

    def test_import_vc_without_reasoning_fields_backward_compat(
        self, trust_chain, keypair, issuer_did
    ):
        """Import MUST handle VCs without reasoning fields (backward compatibility)."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)

        # Verify the VC has no reasoning fields (baseline delegation fixture has none)
        d = vc["credentialSubject"]["delegations"][0]
        assert "reasoning" not in d
        assert "reasoningTraceHash" not in d
        assert "reasoningSignature" not in d

        imported = import_from_verifiable_credential(vc)

        imp_del = imported.delegations[0]
        assert imp_del.reasoning_trace is None
        assert imp_del.reasoning_trace_hash is None
        assert imp_del.reasoning_signature is None


class TestReasoningTraceRoundTrip:
    """Tests for full round-trip fidelity of reasoning traces through W3C VCs."""

    def test_round_trip_public_reasoning_trace(self, keypair, issuer_did):
        """PUBLIC reasoning trace MUST survive full export -> import round-trip."""
        private_key, _ = keypair
        now = datetime.now(timezone.utc)
        from eatp.reasoning import ConfidentialityLevel, ReasoningTrace

        trace = ReasoningTrace(
            decision="Full round-trip decision",
            rationale="This should survive export/import",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=now,
            alternatives_considered=["option-a", "option-b"],
            evidence=[{"type": "test", "value": 42}],
            methodology="test_methodology",
            confidence=0.85,
        )
        genesis = GenesisRecord(
            id="gen-roundtrip",
            agent_id="agent-roundtrip",
            authority_id="authority-001",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=now,
            signature=sign(
                {"id": "gen-roundtrip", "agent_id": "agent-roundtrip",
                 "authority_id": "authority-001", "authority_type": "organization",
                 "created_at": now.isoformat(), "expires_at": None, "metadata": {}},
                private_key,
            ),
        )
        delegation = DelegationRecord(
            id="del-roundtrip",
            delegator_id="agent-roundtrip",
            delegatee_id="agent-target",
            task_id="task-roundtrip",
            capabilities_delegated=["action_a"],
            constraint_subset=[],
            delegated_at=now,
            signature=sign({"id": "del-roundtrip"}, private_key),
            reasoning_trace=trace,
            reasoning_trace_hash="sha256-roundtrip",
            reasoning_signature="sig-roundtrip",
        )
        chain = TrustLineageChain(
            genesis=genesis,
            delegations=[delegation],
        )

        vc = export_as_verifiable_credential(chain, issuer_did, private_key)
        imported = import_from_verifiable_credential(vc)

        orig_del = chain.delegations[0]
        imp_del = imported.delegations[0]

        # All reasoning fields must match
        assert imp_del.reasoning_trace is not None
        assert imp_del.reasoning_trace.decision == orig_del.reasoning_trace.decision
        assert imp_del.reasoning_trace.rationale == orig_del.reasoning_trace.rationale
        assert imp_del.reasoning_trace.confidentiality == orig_del.reasoning_trace.confidentiality
        assert imp_del.reasoning_trace.timestamp == orig_del.reasoning_trace.timestamp
        assert imp_del.reasoning_trace.alternatives_considered == orig_del.reasoning_trace.alternatives_considered
        assert imp_del.reasoning_trace.evidence == orig_del.reasoning_trace.evidence
        assert imp_del.reasoning_trace.methodology == orig_del.reasoning_trace.methodology
        assert imp_del.reasoning_trace.confidence == orig_del.reasoning_trace.confidence
        assert imp_del.reasoning_trace_hash == orig_del.reasoning_trace_hash
        assert imp_del.reasoning_signature == orig_del.reasoning_signature

    def test_round_trip_without_reasoning_trace(self, trust_chain, keypair, issuer_did):
        """Chain without reasoning traces MUST round-trip without any reasoning fields."""
        private_key, _ = keypair
        vc = export_as_verifiable_credential(trust_chain, issuer_did, private_key)
        imported = import_from_verifiable_credential(vc)

        # Basic chain data must still round-trip
        assert imported.genesis.id == trust_chain.genesis.id
        assert len(imported.delegations) == len(trust_chain.delegations)

        # No reasoning traces should appear
        for imp_del in imported.delegations:
            assert imp_del.reasoning_trace is None
            assert imp_del.reasoning_trace_hash is None
            assert imp_del.reasoning_signature is None

    def test_round_trip_chain_hash_stable_with_reasoning(self, keypair, issuer_did):
        """Chain hash MUST remain stable through reasoning-enriched export/import."""
        private_key, _ = keypair
        now = datetime.now(timezone.utc)
        from eatp.reasoning import ConfidentialityLevel, ReasoningTrace

        trace = ReasoningTrace(
            decision="Hash stability test",
            rationale="Hash must be deterministic",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=now,
        )
        genesis = GenesisRecord(
            id="gen-hash-stable",
            agent_id="agent-hash",
            authority_id="authority-001",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=now,
            signature=sign(
                {"id": "gen-hash-stable", "agent_id": "agent-hash",
                 "authority_id": "authority-001", "authority_type": "organization",
                 "created_at": now.isoformat(), "expires_at": None, "metadata": {}},
                private_key,
            ),
        )
        delegation = DelegationRecord(
            id="del-hash-stable",
            delegator_id="agent-hash",
            delegatee_id="agent-target",
            task_id="task-hash",
            capabilities_delegated=["read"],
            constraint_subset=[],
            delegated_at=now,
            signature=sign({"id": "del-hash-stable"}, private_key),
            reasoning_trace=trace,
            reasoning_trace_hash="sha256-hash-stable",
            reasoning_signature="sig-hash-stable",
        )
        chain = TrustLineageChain(
            genesis=genesis,
            delegations=[delegation],
        )

        original_hash = chain.hash()
        vc = export_as_verifiable_credential(chain, issuer_did, private_key)
        imported = import_from_verifiable_credential(vc)

        assert imported.hash() == original_hash
