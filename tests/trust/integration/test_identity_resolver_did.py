# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Tier-2 integration tests for the external DID identity resolver.

Exercises invariant 3 (the external DID resolver resolves a real DID and fails
closed on an unknown / unreachable one) and invariant 4 (a backend error
resolves to DENY, never a permissive default) against a REAL filesystem
authority -- no mocking. ``FileSystemDIDRegistry`` reads DID documents an
external authority has published into a directory on disk; a separate
``DIDResolver`` consults it exactly as a cross-organization caller would.

Real Ed25519 key material (``generate_keypair``) and real DID documents
(``create_did_document``) are used throughout.
"""

import hashlib
from pathlib import Path

import pytest

from kailash.trust.identity import (
    DIDResolver,
    FileSystemDIDRegistry,
    IdentityResolutionError,
    ResolvedIdentity,
)
from kailash.trust.interop.did import (
    DIDDocument,
    VerificationMethod,
    create_did_document,
    generate_did,
    generate_did_key,
)
from kailash.trust.signing.crypto import generate_keypair


def _write_raw(authority_dir: Path, did: str, content: str) -> None:
    """Write raw bytes at the exact path the backend reads for ``did``."""
    name = hashlib.sha256(did.encode("utf-8")).hexdigest()
    (authority_dir / f"{name}.json").write_text(content)


def _did_key_doc(multibase: str, key_multibase: str) -> DIDDocument:
    """Build a did:key document whose single verification method carries
    ``key_multibase`` (which may or may not match the identifier-embedded key).
    """
    did = f"did:key:{multibase}"
    key_id = f"{did}#{multibase}"
    vm = VerificationMethod(
        id=key_id,
        type="Ed25519VerificationKey2020",
        controller=did,
        public_key_multibase=key_multibase,
    )
    return DIDDocument(
        id=did,
        verification_method=[vm],
        authentication=[key_id],
        assertion_method=[key_id],
    )


def _multibase_of(public_key: str) -> str:
    """The z-prefixed multibase key embedded in this key's did:key identifier."""
    return generate_did_key(public_key)[len("did:key:") :]


@pytest.fixture
def authority_dir(tmp_path: Path) -> Path:
    """A real on-disk directory standing in for an external DID authority."""
    d = tmp_path / "did-registry"
    d.mkdir()
    return d


@pytest.fixture
def published_did(authority_dir: Path) -> str:
    """Publish a real DID document into the external authority; return its DID."""
    _, public_key = generate_keypair()
    doc = create_did_document("partner-agent", public_key, authority_id="partner-org")
    FileSystemDIDRegistry(authority_dir).publish(doc)
    return doc.id


# ---------------------------------------------------------------------------
# Invariant 3 -- external resolve + fail-closed on unknown / unreachable
# ---------------------------------------------------------------------------


class TestExternalDIDResolution:
    async def test_resolves_published_did(self, authority_dir, published_did):
        resolver = DIDResolver(FileSystemDIDRegistry(authority_dir))

        identity = await resolver.resolve_identity(published_did)

        assert isinstance(identity, ResolvedIdentity)
        assert identity.counterparty_ref == published_did
        assert identity.resolver == "did"
        assert identity.is_external is True
        # The published DID document's Ed25519 verification key is surfaced.
        assert len(identity.public_keys) == 1
        assert identity.public_keys[0].startswith("z")
        assert identity.metadata["controller"] == generate_did("partner-org")

    async def test_unknown_did_returns_none(self, authority_dir):
        resolver = DIDResolver(FileSystemDIDRegistry(authority_dir))
        # A well-formed DID the authority never published.
        assert await resolver.resolve_identity("did:eatp:ghost-agent") is None

    async def test_malformed_did_returns_none(self, authority_dir):
        resolver = DIDResolver(FileSystemDIDRegistry(authority_dir))
        assert await resolver.resolve_identity("not-a-did") is None
        assert await resolver.resolve_identity("did:unsupported:x") is None

    async def test_unreachable_authority_returns_none(self, tmp_path):
        # Directory does not exist -> the authority cannot be consulted.
        missing = tmp_path / "does-not-exist"
        resolver = DIDResolver(FileSystemDIDRegistry(missing))
        assert await resolver.resolve_identity("did:eatp:partner-agent") is None


# ---------------------------------------------------------------------------
# Invariant 4 -- backend error / corruption -> DENY, never permissive default
# ---------------------------------------------------------------------------


class TestExternalResolverFailsClosed:
    async def test_corrupt_document_denies(self, authority_dir):
        backend = FileSystemDIDRegistry(authority_dir)
        # Write a corrupt document under the exact path the backend will read.
        import hashlib

        did = "did:eatp:corrupt-agent"
        name = hashlib.sha256(did.encode("utf-8")).hexdigest()
        (authority_dir / f"{name}.json").write_text("{ this is not valid json ")

        resolver = DIDResolver(backend)
        assert await resolver.resolve_identity(did) is None

    async def test_backend_error_surfaces_as_typed_error_then_denies(
        self, authority_dir
    ):
        # The backend signals a genuine transport error via a typed exception;
        # the resolver converts it to a fail-closed None.
        class _FailingBackend(FileSystemDIDRegistry):
            def fetch(self, did):  # type: ignore[override]
                raise IdentityResolutionError(did, "authority unreachable")

        resolver = DIDResolver(_FailingBackend(authority_dir))
        assert await resolver.resolve_identity("did:eatp:partner-agent") is None

    async def test_empty_reference_denies(self, authority_dir):
        resolver = DIDResolver(FileSystemDIDRegistry(authority_dir))
        assert await resolver.resolve_identity("") is None

    async def test_requires_a_backend(self):
        with pytest.raises(ValueError):
            DIDResolver(None)  # type: ignore[arg-type]

    async def test_never_returns_permissive_default(self, authority_dir):
        resolver = DIDResolver(FileSystemDIDRegistry(authority_dir))
        result = await resolver.resolve_identity("did:eatp:never-published")
        assert result is None
        assert not isinstance(result, ResolvedIdentity)


# ---------------------------------------------------------------------------
# Cross-organization scenario -- local misses, external resolves
# ---------------------------------------------------------------------------


class TestCrossOrgHandoff:
    async def test_external_resolves_what_local_cannot(
        self, authority_dir, published_did
    ):
        from kailash.trust.identity import LocalRegistryResolver
        from kailash.trust.registry.store import InMemoryAgentRegistryStore

        local = LocalRegistryResolver(InMemoryAgentRegistryStore())
        external = DIDResolver(FileSystemDIDRegistry(authority_dir))

        # The local registry has never seen this cross-org counterparty.
        assert await local.resolve_identity("partner-agent") is None
        # The external DID authority can resolve it.
        identity = await external.resolve_identity(published_did)
        assert identity is not None
        assert identity.is_external is True


# ---------------------------------------------------------------------------
# did:key self-certification -- a hostile authority cannot spoof a key
# ---------------------------------------------------------------------------


class TestDIDKeySelfCertification:
    async def test_self_consistent_did_key_resolves(self, authority_dir):
        # A did:key whose verification method carries exactly the
        # identifier-embedded key resolves normally.
        _, public_key = generate_keypair()
        multibase = _multibase_of(public_key)
        doc = _did_key_doc(multibase, multibase)
        FileSystemDIDRegistry(authority_dir).publish(doc)

        resolver = DIDResolver(FileSystemDIDRegistry(authority_dir))
        identity = await resolver.resolve_identity(doc.id)

        assert identity is not None
        assert identity.public_keys == (multibase,)

    async def test_spoofed_did_key_rejected(self, authority_dir):
        # The authority publishes a document under the VICTIM's did:key
        # identifier but carries the ATTACKER's key in the verification method.
        # The identifier embeds the victim's key (did:key is self-certifying),
        # so the resolver MUST detect the mismatch and DENY.
        _, victim_key = generate_keypair()
        _, attacker_key = generate_keypair()
        victim_mb = _multibase_of(victim_key)
        attacker_mb = _multibase_of(attacker_key)
        assert victim_mb != attacker_mb

        spoof = _did_key_doc(victim_mb, attacker_mb)  # id=victim, vm=attacker
        FileSystemDIDRegistry(authority_dir).publish(spoof)

        resolver = DIDResolver(FileSystemDIDRegistry(authority_dir))
        result = await resolver.resolve_identity(spoof.id)
        assert result is None  # spoof rejected -- no bootstrap from attacker key
        assert not isinstance(result, ResolvedIdentity)


# ---------------------------------------------------------------------------
# Malformed-document containment -- no exception escapes the None contract
# ---------------------------------------------------------------------------


class TestMalformedDocumentContainment:
    async def test_non_string_document_id_denies(self, authority_dir):
        # A document whose id is not a string cannot key the resolve_did
        # registry; the resolver must contain it, not raise.
        did = "did:eatp:nonhashable"
        _write_raw(
            authority_dir,
            did,
            '{"id": {"nested": 1}, "verificationMethod": [], '
            '"authentication": [], "assertionMethod": []}',
        )
        resolver = DIDResolver(FileSystemDIDRegistry(authority_dir))
        assert await resolver.resolve_identity(did) is None

    async def test_deeply_nested_json_denies(self, authority_dir):
        # Deeply nested JSON raises RecursionError inside json.load (a
        # RuntimeError, not a ValueError); the resolver's fail-closed boundary
        # MUST contain it -> None, never an escaping exception.
        did = "did:eatp:nested"
        _write_raw(authority_dir, did, "[" * 20_000 + "]" * 20_000)
        resolver = DIDResolver(FileSystemDIDRegistry(authority_dir))
        assert await resolver.resolve_identity(did) is None

    async def test_zero_verification_methods_denies(self, authority_dir):
        # A document with no verification method is not a usable trust anchor.
        did = generate_did("empty-vm-agent")
        doc = DIDDocument(
            id=did,
            verification_method=[],
            authentication=[],
            assertion_method=[],
        )
        FileSystemDIDRegistry(authority_dir).publish(doc)

        resolver = DIDResolver(FileSystemDIDRegistry(authority_dir))
        assert await resolver.resolve_identity(did) is None
