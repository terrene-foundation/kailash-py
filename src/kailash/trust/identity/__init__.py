# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Pluggable identity resolution for the trust plane.

Given a counterparty reference (an agent id, or a cross-organization DID),
resolve it to a ``ResolvedIdentity`` behind a single ``IdentityResolver``
interface. Resolution is the "who is this?" step beneath governance and
access enforcement; it is fail-closed -- an unresolvable counterparty resolves
to ``None`` (DENY), never a permissive default.

Two implementations ship:

- ``LocalRegistryResolver`` -- resolves against the in-process
  ``AgentRegistryStore`` (same-organization path).
- ``DIDResolver`` -- resolves an unknown counterparty via an external DID
  authority (cross-organization path), reusing the trust plane's DID layer.

Example:
    from kailash.trust.identity import (
        LocalRegistryResolver,
        DIDResolver,
        FileSystemDIDRegistry,
    )
    from kailash.trust.registry.store import InMemoryAgentRegistryStore

    local = LocalRegistryResolver(InMemoryAgentRegistryStore())
    external = DIDResolver(FileSystemDIDRegistry(Path("/srv/did-registry")))

    identity = await local.resolve_identity("agent-001")
    if identity is None:
        identity = await external.resolve_identity("did:eatp:partner-agent")
    # identity is None => DENY
"""

from kailash.trust.identity.did_resolver import (
    DIDResolutionBackend,
    DIDResolver,
    FileSystemDIDRegistry,
)
from kailash.trust.identity.local import LocalRegistryResolver
from kailash.trust.identity.resolver import (
    IdentityResolutionError,
    IdentityResolver,
    ResolvedIdentity,
)

__all__ = [
    # Interface + record
    "IdentityResolver",
    "ResolvedIdentity",
    "IdentityResolutionError",
    # Impl #1 -- in-process registry (same-organization)
    "LocalRegistryResolver",
    # Impl #2 -- external DID authority (cross-organization)
    "DIDResolver",
    "DIDResolutionBackend",
    "FileSystemDIDRegistry",
]
