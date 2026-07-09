# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Identity resolution interface for the trust plane.

This module defines the pluggable ``IdentityResolver`` contract: given a
counterparty reference (an agent id, or a cross-organization DID), resolve it
to a ``ResolvedIdentity`` carrying the counterparty's verification key material.

Resolution is the "who is this?" step that precedes any trust or access
decision. It is deliberately separate from authorization: resolving an
identity establishes that a counterparty exists and produces its key material;
whether that counterparty is *trusted* is decided downstream by the governance
and revocation layers.

Fail-closed contract:
    ``resolve_identity`` returns ``None`` for every unresolvable input --
    unknown reference, unreachable authority, malformed identifier, or backend
    error. An unresolvable counterparty is *untrusted*; a resolver MUST NEVER
    return a permissive default identity. Callers treat ``None`` as DENY.

Implementations:
    - ``LocalRegistryResolver`` (``kailash.trust.identity.local``): resolves
      against the in-process ``AgentRegistryStore`` (same-organization path).
    - ``DIDResolver`` (``kailash.trust.identity.did_resolver``): resolves an
      unknown counterparty's identity via an external DID authority
      (cross-organization path).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from kailash.trust.exceptions import TrustError

logger = logging.getLogger(__name__)

__all__ = [
    "ResolvedIdentity",
    "IdentityResolver",
    "IdentityResolutionError",
]


class IdentityResolutionError(TrustError):
    """
    Raised by a resolution backend on a transport / backend error.

    This signals that the authority itself could not be consulted (unreadable
    store, network failure, corrupt document) -- NOT that a counterparty was
    simply absent. Absence is signalled by returning ``None``. The owning
    ``IdentityResolver`` catches this error, logs it, and converts it to a
    fail-closed ``None`` so callers uniformly treat unresolvable as DENY.

    Inherits ``TrustError`` so it is caught by trust-layer handlers and carries
    a structured ``.details`` payload.
    """

    def __init__(self, ref: str, reason: str, details: Optional[Dict[str, Any]] = None):
        merged: Dict[str, Any] = {"ref": ref, "reason": reason}
        if details:
            merged.update(details)
        super().__init__(f"Identity resolution failed for '{ref}': {reason}", merged)
        self.ref = ref
        self.reason = reason


@dataclass(frozen=True)
class ResolvedIdentity:
    """
    The resolved identity of a counterparty.

    Immutable (``frozen=True``) per the trust-plane constraint-dataclass
    convention -- an identity record MUST NOT be mutated after resolution.

    Attributes:
        counterparty_ref: The reference that was resolved (agent id or DID).
        resolver: Name of the resolver that produced this record
            (e.g. ``"local-registry"``, ``"did"``). Provenance for audit.
        is_external: ``True`` when resolved via an external / cross-organization
            authority (DID); ``False`` for the in-process registry path.
        public_keys: Verification key material for this counterparty. Multibase
            (``z...``) for DID-resolved identities, base64 for registry-resolved
            identities. Empty tuple when the authority published no key.
        metadata: Additional non-authoritative context (agent type, status,
            controller DID, ...). MUST NOT be relied on for a trust decision.
    """

    counterparty_ref: str
    resolver: str
    is_external: bool
    public_keys: Tuple[str, ...] = ()
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "counterparty_ref": self.counterparty_ref,
            "resolver": self.resolver,
            "is_external": self.is_external,
            "public_keys": list(self.public_keys),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResolvedIdentity":
        """Reconstruct from a dictionary produced by ``to_dict``."""
        return cls(
            counterparty_ref=data["counterparty_ref"],
            resolver=data["resolver"],
            is_external=bool(data["is_external"]),
            public_keys=tuple(data.get("public_keys", ())),
            metadata=dict(data.get("metadata", {})),
        )


class IdentityResolver(ABC):
    """
    Abstract interface for resolving a counterparty reference to an identity.

    An identity resolver answers "who is this counterparty and what key material
    proves it?" It is the resolution layer beneath governance: the D/T/R access
    machinery and revocation checks consume a ``ResolvedIdentity`` but do not
    perform resolution themselves.

    Concrete resolvers vary by *authority*: the in-process agent registry
    (same-organization) versus an external DID authority (cross-organization).
    The interface lets callers hold one or more resolvers behind a single
    contract and fail closed uniformly.

    Contract:
        ``resolve_identity`` returns a ``ResolvedIdentity`` on success and
        ``None`` on every unresolvable input. A ``None`` return is the DENY
        signal; implementations MUST NEVER return a permissive default.
    """

    @abstractmethod
    async def resolve_identity(
        self, counterparty_ref: str
    ) -> Optional[ResolvedIdentity]:
        """
        Resolve a counterparty reference to its identity.

        Args:
            counterparty_ref: The identity reference to resolve -- an agent id
                for the registry path, or a DID (``did:<method>:<id>``) for the
                external path.

        Returns:
            The resolved identity, or ``None`` if the reference cannot be
            resolved (unknown, unreachable, malformed, or backend error).
            ``None`` MUST be treated by the caller as DENY.
        """
        ...
