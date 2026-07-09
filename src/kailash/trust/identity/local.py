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
import unicodedata
from typing import Optional

from kailash.trust.identity.resolver import IdentityResolver, ResolvedIdentity
from kailash.trust.registry.store import AgentRegistryStore

logger = logging.getLogger(__name__)

__all__ = ["LocalRegistryResolver"]

# Upper bound on the reference length we will even attempt to look up. A
# reference longer than any legitimate registered agent id is treated as
# unresolvable rather than passed to the store.
_MAX_REF_LENGTH = 512


def _has_control_chars(ref: str) -> bool:
    """True if the reference contains any control character (Unicode ``Cc``).

    Agent ids in this system are DID-style / colon-bearing and the store
    accepts them unconstrained (a dict / DB key, never a filesystem path), so
    ``validate_id``'s strict ``[A-Za-z0-9_-]`` charset would false-DENY a
    legitimately-registered ``did:eatp:x`` id. Dict-key hygiene only requires
    rejecting null bytes and control characters -- ``.``, ``:``, ``/`` are safe.
    """
    return any(unicodedata.category(c) == "Cc" for c in ref)


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

        # Externally-sourced id hygiene: reject null bytes / control characters
        # before the ref reaches the store. Charset is otherwise unconstrained
        # (colon/dot/slash-bearing DID-style ids are legitimate) -- see
        # _has_control_chars.
        if _has_control_chars(counterparty_ref):
            logger.warning(
                "local identity resolution denied: reference contains control characters"
            )
            return None

        try:
            metadata = await self._store.get_agent(counterparty_ref)
        except Exception as e:  # store/backend error -> fail closed (logged)
            # Log the error type only -- never the reference value
            # (observability.md Rule 8: identity-revealing values stay out of WARN).
            logger.warning(
                "local identity resolution denied: store error (%s)",
                type(e).__name__,
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
