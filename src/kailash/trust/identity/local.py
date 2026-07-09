# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
In-process identity resolver backed by the agent registry.

``LocalRegistryResolver`` resolves a counterparty reference against the
existing ``AgentRegistryStore`` -- the same-organization path. It is the
in-process complement to the external ``DIDResolver``: this resolver only knows
agents this organization has itself registered.

The store is supplied explicitly (never looked up from a global, never
self-constructed) so the resolver shares the caller's registry state rather
than a parallel copy -- see ``rules/facade-manager-detection.md`` Rule 3.
"""

from __future__ import annotations

import logging
from typing import Optional

from kailash.trust._locking import validate_id
from kailash.trust.identity.resolver import IdentityResolver, ResolvedIdentity
from kailash.trust.registry.store import AgentRegistryStore

logger = logging.getLogger(__name__)

__all__ = ["LocalRegistryResolver"]

# Upper bound on the reference length we will even attempt to look up. A
# reference longer than any legitimate registered agent id is treated as
# unresolvable rather than passed to the store.
_MAX_REF_LENGTH = 512


class LocalRegistryResolver(IdentityResolver):
    """
    Resolve identities against the in-process agent registry.

    Args:
        store: The ``AgentRegistryStore`` to resolve against. Passed explicitly
            so this resolver shares the caller's registry backend (in-memory or
            Postgres) instead of constructing a parallel one.

    Example:
        >>> from kailash.trust.registry.store import InMemoryAgentRegistryStore
        >>> store = InMemoryAgentRegistryStore()
        >>> resolver = LocalRegistryResolver(store)
        >>> identity = await resolver.resolve_identity("agent-001")
    """

    def __init__(self, store: AgentRegistryStore) -> None:
        if store is None:
            raise ValueError("LocalRegistryResolver requires an AgentRegistryStore")
        self._store = store

    async def resolve_identity(
        self, counterparty_ref: str
    ) -> Optional[ResolvedIdentity]:
        """
        Resolve an agent id to its registered identity.

        Returns ``None`` (DENY) for an empty, over-long, unsafe, or unknown
        reference, and for any store error -- never a permissive default.
        """
        if not counterparty_ref or len(counterparty_ref) > _MAX_REF_LENGTH:
            logger.debug(
                "local identity resolution denied: empty or over-long reference"
            )
            return None

        # Externally-sourced id: reject path-traversal / unsafe characters
        # before it reaches the store. An unsafe reference cannot name a
        # legitimately-registered agent, so treat it as unresolvable (DENY).
        try:
            validate_id(counterparty_ref)
        except ValueError:
            logger.warning(
                "local identity resolution denied: reference is not a safe id"
            )
            return None

        try:
            metadata = await self._store.get_agent(counterparty_ref)
        except Exception as e:  # store/backend error -> fail closed (logged)
            logger.warning(
                "local identity resolution denied: store error for '%s': %s",
                counterparty_ref,
                e,
            )
            return None

        if metadata is None:
            logger.debug("local identity resolution: no agent registered for reference")
            return None

        public_keys = (metadata.public_key,) if metadata.public_key else ()
        return ResolvedIdentity(
            counterparty_ref=counterparty_ref,
            resolver="local-registry",
            is_external=False,
            public_keys=public_keys,
            metadata={
                "agent_type": metadata.agent_type,
                "status": metadata.status.value,
                "trust_chain_hash": metadata.trust_chain_hash,
            },
        )
