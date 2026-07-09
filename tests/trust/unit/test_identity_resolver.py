# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Tier-1 unit tests for the pluggable identity resolver.

Covers the four load-bearing invariants of the identity-resolution surface:

1. The ``IdentityResolver`` interface has >= 2 concrete implementations.
2. ``LocalRegistryResolver`` resolves a registered agent and returns ``None``
   for an unknown one.
4. A resolver error resolves to DENY (``None``), never a permissive default.

The external DID resolver's own resolve/fail-closed invariant (3) is exercised
against a real filesystem authority in
``tests/trust/integration/test_identity_resolver_did.py``.

Real infrastructure only: the in-process ``InMemoryAgentRegistryStore`` is the
production storage backend, not a mock.
"""

from datetime import datetime, timezone

import pytest

from kailash.trust.identity import (
    DIDResolver,
    IdentityResolver,
    LocalRegistryResolver,
    ResolvedIdentity,
)
from kailash.trust.registry.models import AgentMetadata, AgentStatus
from kailash.trust.registry.store import AgentRegistryStore, InMemoryAgentRegistryStore


def _metadata(agent_id: str, public_key: str | None = "pub-abc") -> AgentMetadata:
    now = datetime.now(timezone.utc)
    return AgentMetadata(
        agent_id=agent_id,
        agent_type="worker",
        capabilities=["analyze"],
        constraints=["read_only"],
        status=AgentStatus.ACTIVE,
        trust_chain_hash="hash-123",
        registered_at=now,
        last_seen=now,
        metadata={},
        public_key=public_key,
    )


class _RaisingStore(InMemoryAgentRegistryStore):
    """A real store whose lookup path raises -- exercises fail-closed on error."""

    async def get_agent(self, agent_id):  # type: ignore[override]
        raise RuntimeError("simulated backend outage")


# ---------------------------------------------------------------------------
# Invariant 1 -- the interface has >= 2 concrete implementations
# ---------------------------------------------------------------------------


class TestInterfaceHasTwoImpls:
    def test_local_and_did_are_identity_resolvers(self):
        assert issubclass(LocalRegistryResolver, IdentityResolver)
        assert issubclass(DIDResolver, IdentityResolver)

    def test_at_least_two_concrete_impls(self):
        concrete = [
            c
            for c in IdentityResolver.__subclasses__()
            if getattr(c, "__abstractmethods__", None) == frozenset()
        ]
        assert len(concrete) >= 2, f"expected >=2 concrete resolvers, got {concrete}"

    def test_resolvers_are_distinct_not_aliases(self):
        # The external resolver must be a genuine second implementation, not a
        # thin alias of the local one.
        assert LocalRegistryResolver is not DIDResolver
        assert (
            LocalRegistryResolver.resolve_identity is not DIDResolver.resolve_identity
        )


# ---------------------------------------------------------------------------
# Invariant 2 -- LocalRegistryResolver resolve-known / deny-unknown
# ---------------------------------------------------------------------------


class TestLocalRegistryResolver:
    async def test_resolves_registered_agent(self):
        store = InMemoryAgentRegistryStore()
        await store.register_agent(_metadata("agent-001"))
        resolver = LocalRegistryResolver(store)

        identity = await resolver.resolve_identity("agent-001")

        assert isinstance(identity, ResolvedIdentity)
        assert identity.counterparty_ref == "agent-001"
        assert identity.resolver == "local-registry"
        assert identity.is_external is False
        assert identity.public_keys == ("pub-abc",)
        assert identity.metadata["status"] == "ACTIVE"

    async def test_unknown_agent_returns_none(self):
        store = InMemoryAgentRegistryStore()
        resolver = LocalRegistryResolver(store)

        assert await resolver.resolve_identity("nope") is None

    async def test_agent_without_public_key_resolves_with_empty_keys(self):
        store = InMemoryAgentRegistryStore()
        await store.register_agent(_metadata("agent-002", public_key=None))
        resolver = LocalRegistryResolver(store)

        identity = await resolver.resolve_identity("agent-002")
        assert identity is not None
        assert identity.public_keys == ()

    async def test_resolves_colon_and_slash_bearing_agent_id(self):
        # DID-style / colon- and slash-bearing ids are legitimate registry keys
        # (dict/DB keys, never filesystem paths); the resolver MUST NOT
        # false-DENY them (it did under the over-strict validate_id charset).
        store = InMemoryAgentRegistryStore()
        await store.register_agent(_metadata("did:eatp:partner-x"))
        await store.register_agent(_metadata("org/team/agent.7"))
        resolver = LocalRegistryResolver(store)

        did_identity = await resolver.resolve_identity("did:eatp:partner-x")
        assert did_identity is not None
        assert did_identity.counterparty_ref == "did:eatp:partner-x"

        dotted = await resolver.resolve_identity("org/team/agent.7")
        assert dotted is not None
        assert dotted.counterparty_ref == "org/team/agent.7"

    async def test_requires_a_store(self):
        with pytest.raises(ValueError):
            LocalRegistryResolver(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Invariant 4 -- error/malformed input -> DENY, never a permissive default
# ---------------------------------------------------------------------------


class TestLocalResolverFailsClosed:
    async def test_store_error_denies(self):
        resolver = LocalRegistryResolver(_RaisingStore())
        assert await resolver.resolve_identity("agent-001") is None

    async def test_empty_reference_denies(self):
        resolver = LocalRegistryResolver(InMemoryAgentRegistryStore())
        assert await resolver.resolve_identity("") is None

    async def test_path_traversal_reference_denies(self):
        store = InMemoryAgentRegistryStore()
        resolver = LocalRegistryResolver(store)
        # A traversal-shaped ref is not a registered agent -> unresolvable.
        # (It is not a filesystem path here, but it names no registered agent.)
        assert await resolver.resolve_identity("../../etc/shadow") is None

    async def test_control_char_reference_denies(self):
        # Null bytes / control characters are rejected as dict-key hygiene
        # before the reference reaches the store.
        store = InMemoryAgentRegistryStore()
        resolver = LocalRegistryResolver(store)
        assert await resolver.resolve_identity("agent\x00id") is None
        assert await resolver.resolve_identity("agent\x1fid") is None

    async def test_over_long_reference_denies(self):
        resolver = LocalRegistryResolver(InMemoryAgentRegistryStore())
        assert await resolver.resolve_identity("a" * 10_000) is None

    async def test_never_returns_permissive_default_for_unknown(self):
        # The DENY signal is exactly None -- not a placeholder identity object.
        store: AgentRegistryStore = InMemoryAgentRegistryStore()
        resolver = LocalRegistryResolver(store)
        result = await resolver.resolve_identity("ghost-agent")
        assert result is None
        assert not isinstance(result, ResolvedIdentity)


# ---------------------------------------------------------------------------
# ResolvedIdentity record contract
# ---------------------------------------------------------------------------


class TestResolvedIdentityRecord:
    def test_is_frozen(self):
        identity = ResolvedIdentity(
            counterparty_ref="agent-x",
            resolver="local-registry",
            is_external=False,
        )
        with pytest.raises(Exception):
            identity.resolver = "tampered"  # type: ignore[misc]

    def test_metadata_is_immutable(self):
        # metadata is a read-only view (MappingProxyType) -- a resolved record
        # cannot be mutated in place, not even its metadata contents.
        identity = ResolvedIdentity(
            counterparty_ref="agent-x",
            resolver="did",
            is_external=True,
            metadata={"controller": "did:eatp:org"},
        )
        with pytest.raises(TypeError):
            identity.metadata["controller"] = "tampered"  # type: ignore[index]
        assert identity.metadata["controller"] == "did:eatp:org"

    def test_round_trips_through_dict(self):
        identity = ResolvedIdentity(
            counterparty_ref="did:eatp:agent-x",
            resolver="did",
            is_external=True,
            public_keys=("zAbc", "zDef"),
            metadata={"controller": "did:eatp:org"},
        )
        assert ResolvedIdentity.from_dict(identity.to_dict()) == identity
