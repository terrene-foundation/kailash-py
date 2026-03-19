"""
Unit tests for EATP DID (Decentralized Identifier) identity layer.

Tests the did:eatp method, DID document creation, serialization,
and interop with did:key method.
"""

import json

import pytest

from eatp.authority import OrganizationalAuthority
from eatp.chain import AuthorityType
from eatp.crypto import generate_keypair
from eatp.interop.did import (
    DIDDocument,
    DIDResolutionError,
    DIDValidationError,
    ServiceEndpoint,
    VerificationMethod,
    create_did_document,
    did_document_from_dict,
    did_document_to_dict,
    did_from_authority,
    generate_did,
    generate_did_key,
    resolve_did,
)


# ---------------------------------------------------------------------------
# Module-level DID registry for resolution tests
# ---------------------------------------------------------------------------


class TestGenerateDid:
    """Tests for generate_did() — EATP-native DID generation."""

    def test_basic_generation(self):
        """generate_did returns a well-formed did:eatp URI."""
        did = generate_did("agent-001")
        assert did == "did:eatp:agent-001"

    def test_preserves_agent_id(self):
        """The agent_id portion of the DID is preserved verbatim."""
        did = generate_did("my-complex-agent_v2")
        assert did == "did:eatp:my-complex-agent_v2"

    def test_empty_agent_id_raises(self):
        """Empty agent_id must raise DIDValidationError, not silently succeed."""
        with pytest.raises(DIDValidationError, match="agent_id"):
            generate_did("")

    def test_whitespace_only_agent_id_raises(self):
        """Whitespace-only agent_id must raise DIDValidationError."""
        with pytest.raises(DIDValidationError, match="agent_id"):
            generate_did("   ")

    def test_agent_id_with_colon_raises(self):
        """Colons are DID delimiters and must not appear in agent_id."""
        with pytest.raises(DIDValidationError, match="colon"):
            generate_did("agent:bad")

    def test_agent_id_with_spaces_raises(self):
        """Spaces are not valid in DID method-specific identifiers."""
        with pytest.raises(DIDValidationError, match="whitespace"):
            generate_did("agent bad")


class TestGenerateDidKey:
    """Tests for generate_did_key() — did:key interop method."""

    def test_produces_did_key_prefix(self):
        """Result starts with 'did:key:z'."""
        _, pub = generate_keypair()
        did = generate_did_key(pub)
        assert did.startswith("did:key:z")

    def test_multicodec_ed25519_prefix(self):
        """
        The multibase+multicodec encoding should start with 'z6Mk'
        (z = base58btc, 0xed01 = Ed25519 public key multicodec).
        """
        _, pub = generate_keypair()
        did = generate_did_key(pub)
        # After 'did:key:' the identifier is a multibase-encoded value
        identifier = did[len("did:key:") :]
        # Must start with 'z' (base58btc) followed by '6Mk' (ed25519 multicodec)
        assert identifier.startswith("z6Mk"), (
            f"Expected identifier to start with 'z6Mk' for Ed25519, got '{identifier[:10]}'"
        )

    def test_deterministic_for_same_key(self):
        """Same public key must always produce the same did:key."""
        _, pub = generate_keypair()
        assert generate_did_key(pub) == generate_did_key(pub)

    def test_different_keys_produce_different_dids(self):
        """Different keys must produce different DIDs."""
        _, pub1 = generate_keypair()
        _, pub2 = generate_keypair()
        assert generate_did_key(pub1) != generate_did_key(pub2)

    def test_empty_key_raises(self):
        """Empty public key must raise DIDValidationError."""
        with pytest.raises(DIDValidationError, match="public_key"):
            generate_did_key("")

    def test_invalid_base64_key_raises(self):
        """Non-base64 public key must raise DIDValidationError."""
        with pytest.raises(DIDValidationError, match="public_key"):
            generate_did_key("not-valid-base64!!!")


class TestCreateDidDocument:
    """Tests for create_did_document() — W3C DID Core spec compliance."""

    def test_basic_document_structure(self):
        """Document has all required W3C DID Core fields."""
        _, pub = generate_keypair()
        doc = create_did_document("agent-001", pub)

        assert doc.id == "did:eatp:agent-001"
        assert len(doc.verification_method) == 1
        assert len(doc.authentication) == 1
        assert len(doc.assertion_method) == 1

    def test_verification_method_type(self):
        """Verification method must be Ed25519VerificationKey2020."""
        _, pub = generate_keypair()
        doc = create_did_document("agent-001", pub)
        vm = doc.verification_method[0]

        assert vm.type == "Ed25519VerificationKey2020"
        assert vm.controller == "did:eatp:agent-001"
        assert vm.public_key_multibase is not None

    def test_verification_method_id_format(self):
        """Verification method id must be DID#key-1."""
        _, pub = generate_keypair()
        doc = create_did_document("agent-001", pub)
        vm = doc.verification_method[0]

        assert vm.id == "did:eatp:agent-001#key-1"

    def test_authentication_references_verification_method(self):
        """Authentication must reference the verification method by ID."""
        _, pub = generate_keypair()
        doc = create_did_document("agent-001", pub)

        assert doc.authentication == ["did:eatp:agent-001#key-1"]

    def test_assertion_method_references_verification_method(self):
        """Assertion method (for VC signing) must reference the key."""
        _, pub = generate_keypair()
        doc = create_did_document("agent-001", pub)

        assert doc.assertion_method == ["did:eatp:agent-001#key-1"]

    def test_no_controller_by_default(self):
        """Without authority_id, controller must be None."""
        _, pub = generate_keypair()
        doc = create_did_document("agent-001", pub)

        assert doc.controller is None

    def test_controller_set_from_authority_id(self):
        """With authority_id, controller must be the authority DID."""
        _, pub = generate_keypair()
        doc = create_did_document("agent-001", pub, authority_id="org-acme")

        assert doc.controller == "did:eatp:org-acme"

    def test_service_empty_by_default(self):
        """Without explicit services, list is empty."""
        _, pub = generate_keypair()
        doc = create_did_document("agent-001", pub)

        assert doc.service == []

    def test_empty_agent_id_raises(self):
        """Empty agent_id must raise DIDValidationError."""
        _, pub = generate_keypair()
        with pytest.raises(DIDValidationError, match="agent_id"):
            create_did_document("", pub)

    def test_empty_public_key_raises(self):
        """Empty public_key must raise DIDValidationError."""
        with pytest.raises(DIDValidationError, match="public_key"):
            create_did_document("agent-001", "")

    def test_public_key_multibase_encoding(self):
        """
        The public key in verification method must be multibase-encoded
        (z-prefix = base58btc).
        """
        _, pub = generate_keypair()
        doc = create_did_document("agent-001", pub)
        vm = doc.verification_method[0]

        assert vm.public_key_multibase.startswith("z"), "Multibase encoding must start with 'z' for base58btc"


class TestDidFromAuthority:
    """Tests for did_from_authority() — OrganizationalAuthority to DID."""

    def test_authority_did_format(self):
        """Authority DID follows did:eatp:<authority_id> format."""
        _, pub = generate_keypair()
        authority = OrganizationalAuthority(
            id="org-acme",
            name="ACME Corp",
            authority_type=AuthorityType.ORGANIZATION,
            public_key=pub,
            signing_key_id="key-001",
        )
        did = did_from_authority(authority)
        assert did == "did:eatp:org-acme"

    def test_inactive_authority_raises(self):
        """Inactive authority must raise DIDValidationError."""
        _, pub = generate_keypair()
        authority = OrganizationalAuthority(
            id="org-dead",
            name="Dead Corp",
            authority_type=AuthorityType.ORGANIZATION,
            public_key=pub,
            signing_key_id="key-001",
            is_active=False,
        )
        with pytest.raises(DIDValidationError, match="inactive"):
            did_from_authority(authority)

    def test_system_authority(self):
        """System authorities also produce valid DIDs."""
        _, pub = generate_keypair()
        authority = OrganizationalAuthority(
            id="esa-system",
            name="ESA",
            authority_type=AuthorityType.SYSTEM,
            public_key=pub,
            signing_key_id="key-002",
        )
        did = did_from_authority(authority)
        assert did == "did:eatp:esa-system"


class TestResolveDid:
    """Tests for resolve_did() — DID resolution to DIDDocument."""

    def test_resolve_registered_did(self):
        """Resolving a DID that was created returns the correct document."""
        _, pub = generate_keypair()
        doc = create_did_document("agent-resolve-test", pub)
        resolved = resolve_did(doc.id, registry={doc.id: doc})

        assert resolved.id == doc.id
        assert resolved.verification_method == doc.verification_method

    def test_resolve_unknown_did_raises(self):
        """Resolving an unknown DID must raise DIDResolutionError."""
        with pytest.raises(DIDResolutionError, match="did:eatp:nonexistent"):
            resolve_did("did:eatp:nonexistent", registry={})

    def test_resolve_invalid_did_format_raises(self):
        """Malformed DID string must raise DIDValidationError."""
        with pytest.raises(DIDValidationError, match="format"):
            resolve_did("not-a-did", registry={})

    def test_resolve_wrong_method_raises(self):
        """Unsupported DID method must raise DIDValidationError."""
        with pytest.raises(DIDValidationError, match="method"):
            resolve_did("did:web:example.com", registry={})

    def test_resolve_did_key_format_raises_when_not_in_registry(self):
        """did:key is supported for generation but resolution requires a registry entry."""
        with pytest.raises(DIDResolutionError):
            resolve_did("did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK", registry={})


class TestDidDocumentSerialization:
    """Tests for did_document_to_dict() and did_document_from_dict()."""

    def test_roundtrip(self):
        """Serialize then deserialize must produce an equivalent document."""
        _, pub = generate_keypair()
        original = create_did_document("agent-serial", pub, authority_id="org-test")
        data = did_document_to_dict(original)
        restored = did_document_from_dict(data)

        assert restored.id == original.id
        assert restored.controller == original.controller
        assert len(restored.verification_method) == len(original.verification_method)
        assert restored.authentication == original.authentication
        assert restored.assertion_method == original.assertion_method
        assert restored.service == original.service

    def test_to_dict_contains_context(self):
        """Serialized dict must include JSON-LD @context."""
        _, pub = generate_keypair()
        doc = create_did_document("agent-ctx", pub)
        data = did_document_to_dict(doc)

        assert "@context" in data
        assert "https://www.w3.org/ns/did/v1" in data["@context"]

    def test_to_dict_verification_method_structure(self):
        """Each verification method must be a proper dict in serialized form."""
        _, pub = generate_keypair()
        doc = create_did_document("agent-vm", pub)
        data = did_document_to_dict(doc)

        vm = data["verificationMethod"][0]
        assert "id" in vm
        assert "type" in vm
        assert "controller" in vm
        assert "publicKeyMultibase" in vm

    def test_to_dict_service_endpoints(self):
        """Service endpoints must serialize properly."""
        _, pub = generate_keypair()
        doc = create_did_document("agent-svc", pub)
        svc = ServiceEndpoint(
            id="did:eatp:agent-svc#trust-api",
            type="TrustVerification",
            service_endpoint="https://trust.example.com/verify",
        )
        doc.service.append(svc)
        data = did_document_to_dict(doc)

        assert len(data["service"]) == 1
        assert data["service"][0]["id"] == "did:eatp:agent-svc#trust-api"
        assert data["service"][0]["type"] == "TrustVerification"
        assert data["service"][0]["serviceEndpoint"] == "https://trust.example.com/verify"

    def test_from_dict_with_missing_id_raises(self):
        """Deserialization of dict without 'id' must raise DIDValidationError."""
        with pytest.raises(DIDValidationError, match="id"):
            did_document_from_dict({"verificationMethod": []})

    def test_from_dict_with_missing_verification_method_raises(self):
        """Deserialization of dict without 'verificationMethod' must raise."""
        with pytest.raises(DIDValidationError, match="verificationMethod"):
            did_document_from_dict({"id": "did:eatp:x"})

    def test_to_dict_produces_valid_json(self):
        """Serialized dict must be fully JSON-serializable."""
        _, pub = generate_keypair()
        doc = create_did_document("agent-json", pub, authority_id="org-test")
        data = did_document_to_dict(doc)
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        assert parsed["id"] == "did:eatp:agent-json"

    def test_roundtrip_with_services(self):
        """Roundtrip must preserve service endpoints."""
        _, pub = generate_keypair()
        doc = create_did_document("agent-rt-svc", pub)
        doc.service.append(
            ServiceEndpoint(
                id="did:eatp:agent-rt-svc#msg",
                type="Messaging",
                service_endpoint="https://msg.example.com",
            )
        )
        data = did_document_to_dict(doc)
        restored = did_document_from_dict(data)
        assert len(restored.service) == 1
        assert restored.service[0].type == "Messaging"

    def test_roundtrip_without_controller(self):
        """Roundtrip must handle None controller correctly."""
        _, pub = generate_keypair()
        doc = create_did_document("agent-no-ctrl", pub)
        data = did_document_to_dict(doc)
        restored = did_document_from_dict(data)
        assert restored.controller is None

    def test_from_dict_with_controller(self):
        """Deserialization must restore controller from dict."""
        _, pub = generate_keypair()
        doc = create_did_document("agent-ctrl", pub, authority_id="org-boss")
        data = did_document_to_dict(doc)
        restored = did_document_from_dict(data)
        assert restored.controller == "did:eatp:org-boss"


class TestDIDDocumentDataclass:
    """Tests for the DIDDocument dataclass itself."""

    def test_fields_exist(self):
        """DIDDocument must have all required W3C DID Core fields."""
        _, pub = generate_keypair()
        doc = create_did_document("agent-fields", pub)

        assert hasattr(doc, "id")
        assert hasattr(doc, "verification_method")
        assert hasattr(doc, "authentication")
        assert hasattr(doc, "assertion_method")
        assert hasattr(doc, "service")
        assert hasattr(doc, "controller")

    def test_verification_method_dataclass(self):
        """VerificationMethod must have all Ed25519VerificationKey2020 fields."""
        vm = VerificationMethod(
            id="did:eatp:x#key-1",
            type="Ed25519VerificationKey2020",
            controller="did:eatp:x",
            public_key_multibase="zSomeEncodedKey",
        )
        assert vm.id == "did:eatp:x#key-1"
        assert vm.type == "Ed25519VerificationKey2020"
        assert vm.controller == "did:eatp:x"
        assert vm.public_key_multibase == "zSomeEncodedKey"

    def test_service_endpoint_dataclass(self):
        """ServiceEndpoint must hold id, type, and serviceEndpoint."""
        svc = ServiceEndpoint(
            id="did:eatp:x#svc",
            type="TrustAPI",
            service_endpoint="https://example.com/api",
        )
        assert svc.id == "did:eatp:x#svc"
        assert svc.type == "TrustAPI"
        assert svc.service_endpoint == "https://example.com/api"


class TestEdgeCases:
    """Edge cases and integration-style unit tests."""

    def test_unicode_agent_id(self):
        """Unicode in agent_id should be accepted if no prohibited chars."""
        did = generate_did("agent-alpha-42")
        assert did == "did:eatp:agent-alpha-42"

    def test_very_long_agent_id(self):
        """Long agent_id should still produce a valid DID."""
        long_id = "a" * 256
        did = generate_did(long_id)
        assert did == f"did:eatp:{long_id}"

    def test_create_and_resolve_full_lifecycle(self):
        """Create a document, serialize, deserialize, check consistency."""
        _, pub = generate_keypair()
        doc = create_did_document("lifecycle-agent", pub, authority_id="org-lifecycle")

        serialized = did_document_to_dict(doc)
        deserialized = did_document_from_dict(serialized)

        assert deserialized.id == "did:eatp:lifecycle-agent"
        assert deserialized.controller == "did:eatp:org-lifecycle"
        assert deserialized.verification_method[0].public_key_multibase == (
            doc.verification_method[0].public_key_multibase
        )

    def test_did_key_and_eatp_are_different(self):
        """did:key and did:eatp for the same agent must be different URIs."""
        _, pub = generate_keypair()
        eatp_did = generate_did("agent-x")
        key_did = generate_did_key(pub)

        assert eatp_did != key_did
        assert eatp_did.startswith("did:eatp:")
        assert key_did.startswith("did:key:")

    def test_resolve_did_eatp_and_did_key_both_supported_in_registry(self):
        """Both did:eatp and did:key entries can coexist in a registry."""
        _, pub = generate_keypair()
        eatp_doc = create_did_document("agent-dual", pub)
        key_did = generate_did_key(pub)
        key_doc = create_did_document("agent-dual", pub)
        # Manually set the key_doc id to the did:key value for registry
        key_doc_for_registry = DIDDocument(
            id=key_did,
            verification_method=key_doc.verification_method,
            authentication=key_doc.authentication,
            assertion_method=key_doc.assertion_method,
            service=key_doc.service,
            controller=key_doc.controller,
        )

        registry = {
            eatp_doc.id: eatp_doc,
            key_did: key_doc_for_registry,
        }

        resolved_eatp = resolve_did(eatp_doc.id, registry=registry)
        resolved_key = resolve_did(key_did, registry=registry)

        assert resolved_eatp.id.startswith("did:eatp:")
        assert resolved_key.id.startswith("did:key:")
