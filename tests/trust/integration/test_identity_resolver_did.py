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

from pathlib import Path

import pytest

from kailash.trust.identity import (
    DIDResolver,
    FileSystemDIDRegistry,
    IdentityResolutionError,
    ResolvedIdentity,
)
from kailash.trust.interop.did import create_did_document, generate_did
from kailash.trust.signing.crypto import generate_keypair


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
