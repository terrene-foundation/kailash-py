# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Canonical type substrate for ``kailash.delegate`` (#1035).

Mirrors the kailash-rs ``kailash-delegate-types`` crate's M2-01 substrate-
composition wrappers (identity, role, lifecycle, genesis record, principal
directory). The Python types here are designed so cross-SDK byte-canonical
fixtures emitted by either implementation can be verified by the other via
:func:`kailash.trust._json.canonical_json_dumps`.

Per the rs reference extraction report (``workspaces/issue-1035-delegate-py/
01-analysis/02-kailash-rs-reference-extraction.md`` § "Per-crate report" §1):

- ``Identity`` / ``Role`` are frozen substrate-composition wrappers.
- ``LifecycleState`` is the D3 single linear chain ``Proposed → Instantiated
  → PostureGraded → Active → Retired → Archived`` (rs ``lifecycle.rs:91-103``).
- ``LifecycleError`` is the typed exception raised before any audit write per
  rs runtime invariant #3.
- ``GenesisRecord`` is the M2-01 substrate-composition anchor (rs
  ``composition.rs:51-88``).
- ``PrincipalDirectory`` is the deterministic signer registry (rs
  ``directory.rs:21-62``).

All dataclasses are ``frozen=True, slots=True`` because runtime composition
is tighten-only (F5 invariant — see :mod:`kailash.delegate.envelope`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "Identity",
    "Role",
    "LifecycleState",
    "LifecycleError",
    "GenesisRecord",
    "PrincipalDirectory",
]


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class LifecycleState(str, Enum):
    """The D3 single linear lifecycle chain for a Delegate.

    Mirrors the rs ``LifecycleState`` enum (``rs/.../lifecycle.rs:91-103``):
    ``Proposed → Instantiated → PostureGraded → Active → Retired → Archived``.

    The wire format is the lowercase string value (cross-SDK canonical) so
    JSON round-trip against rs fixtures is byte-identical — same convention
    as :class:`kailash.trust.envelope.AgentPosture` (``envelope.py:551``).
    """

    PROPOSED = "proposed"
    INSTANTIATED = "instantiated"
    POSTURE_GRADED = "posture_graded"
    ACTIVE = "active"
    RETIRED = "retired"
    ARCHIVED = "archived"


class LifecycleError(Exception):
    """Raised for illegal lifecycle transitions BEFORE any audit write.

    Mirrors the rs ``LifecycleError { from, to, expected }`` struct
    (``runtime/.../lifecycle.rs::LifecycleError``). Carrying ``from_state``,
    ``to_state``, and ``expected`` lets callers report the only legal
    successor in the error message.
    """

    def __init__(
        self,
        from_state: LifecycleState,
        to_state: LifecycleState,
        expected: LifecycleState | None = None,
    ) -> None:
        self.from_state = from_state
        self.to_state = to_state
        self.expected = expected
        if expected is not None:
            msg = (
                f"illegal lifecycle transition: {from_state.value} → "
                f"{to_state.value}; only legal successor is {expected.value}"
            )
        else:
            msg = (
                f"illegal lifecycle transition: {from_state.value} → "
                f"{to_state.value}; no legal successor exists"
            )
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Identity / Role
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Identity:
    """Substrate-composition wrapper for a Delegate identity.

    Per rs reference report §1 ``identity.rs:91-126`` — ``DelegateIdentity``
    carries the tenant scope and the principal id as eager required fields.

    Args:
        tenant_id: The tenant scope this identity is bound to. Empty string
            rejected — the unscoped case is encoded by a sentinel tenant id
            (e.g. ``"global"``), never by an empty string.
        principal_id: Opaque per-tenant principal identifier. Empty string
            rejected.
        display_name: Optional human-facing display name (NOT identity).
    """

    tenant_id: str
    principal_id: str
    display_name: str | None = None

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError(
                "Identity.tenant_id MUST be a non-empty string "
                "(use a sentinel like 'global' for the unscoped case)"
            )
        if not self.principal_id:
            raise ValueError("Identity.principal_id MUST be a non-empty string")


@dataclass(frozen=True, slots=True)
class Role:
    """Substrate-composition wrapper for a role binding.

    Per rs reference report §1 ``role.rs:126-154`` — a ``Role`` carries an
    opaque id, the tenant scope it lives in, and a frozenset of capability
    scope tokens. The ``scope`` is a ``frozenset`` (immutable per rs); the
    intersection of scopes is the only widening-preventing operator.

    Args:
        role_id: Opaque per-tenant role identifier. Empty string rejected.
        tenant_id: The tenant scope this role is bound to. Empty string
            rejected.
        scope: Frozen set of capability tokens granted to this role.
    """

    role_id: str
    tenant_id: str
    scope: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.role_id:
            raise ValueError("Role.role_id MUST be a non-empty string")
        if not self.tenant_id:
            raise ValueError("Role.tenant_id MUST be a non-empty string")
        # Coerce list/tuple/set to frozenset for frozen immutability.
        if not isinstance(self.scope, frozenset):
            object.__setattr__(self, "scope", frozenset(self.scope))


# ---------------------------------------------------------------------------
# Genesis record
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GenesisRecord:
    """Substrate-composition anchor for a Delegate's lifetime.

    Per rs reference report §1 ``composition.rs:51-88`` — ``GenesisRecord``
    wraps the substrate ``GenesisBlock`` and adds a ``spec_version`` plus
    capability list. Signing remains the substrate's responsibility (the rs
    side uses ``CareChain::sign()``).

    Python composes:
    - ``genesis_id``: opaque UUID-shaped identifier (string).
    - ``created_at``: tz-aware UTC timestamp; naive datetimes rejected.
    - ``principal_directory_anchor``: SHA-256 hex digest of the principal
      directory at genesis time (32 hex chars × 2 = 64).
    - ``initial_envelope_hash``: SHA-256 hex digest of the genesis-seeded
      ``ConstraintEnvelope`` (the load-bearing F5 anchor — see
      :mod:`kailash.delegate.envelope`).
    - ``delegation_proof``: opaque proof bytes (hex) — substrate signs.
    - ``signature``: hex-encoded Ed25519 signature over the canonical-JSON
      serialization of this record minus the signature field.

    The :meth:`to_canonical_dict` method emits a dict suitable for routing
    through :func:`kailash.trust._json.canonical_json_dumps` so byte-canonical
    comparison against rs reference fixtures works.
    """

    genesis_id: str
    created_at: datetime
    principal_directory_anchor: str
    initial_envelope_hash: str
    delegation_proof: str
    signature: str
    spec_version: str = "1"
    capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.genesis_id:
            raise ValueError("GenesisRecord.genesis_id MUST be non-empty")
        if self.created_at.tzinfo is None:
            raise ValueError(
                "GenesisRecord.created_at MUST be timezone-aware "
                "(naive datetimes break cross-SDK wire-format parity)"
            )
        if not self.principal_directory_anchor:
            raise ValueError(
                "GenesisRecord.principal_directory_anchor MUST be non-empty"
            )
        if not self.initial_envelope_hash:
            raise ValueError("GenesisRecord.initial_envelope_hash MUST be non-empty")
        if not self.delegation_proof:
            raise ValueError("GenesisRecord.delegation_proof MUST be non-empty")
        if not self.signature:
            raise ValueError("GenesisRecord.signature MUST be non-empty")
        if not self.spec_version:
            raise ValueError("GenesisRecord.spec_version MUST be non-empty")
        # Coerce list/iterable to tuple for frozen immutability.
        if not isinstance(self.capabilities, tuple):
            object.__setattr__(self, "capabilities", tuple(self.capabilities))

    def to_canonical_dict(self) -> dict[str, Any]:
        """Return a canonical-JSON-ready dict for cross-SDK byte parity.

        Routes through :func:`kailash.trust._json.canonical_json_dumps` at
        the call site. Field ordering does NOT matter (the encoder sorts
        keys); field NAMES and value TYPES MUST match the rs side exactly.
        """
        # Use UTC ISO-8601 with explicit offset for cross-SDK timestamp shape.
        created_at_iso = self.created_at.astimezone(timezone.utc).isoformat()
        return {
            "genesis_id": self.genesis_id,
            "created_at": created_at_iso,
            "principal_directory_anchor": self.principal_directory_anchor,
            "initial_envelope_hash": self.initial_envelope_hash,
            "delegation_proof": self.delegation_proof,
            "signature": self.signature,
            "spec_version": self.spec_version,
            "capabilities": list(self.capabilities),
        }


# ---------------------------------------------------------------------------
# Principal directory
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PrincipalDirectory:
    """Signer registry for a Delegate's tenant scope.

    Per rs reference report §1 ``directory.rs:21-62`` — the rs side stores a
    ``BTreeMap<String, DelegateId>`` for deterministic audit-stable iteration.
    Python uses a frozen mapping (``dict`` snapshot kept private via copy at
    construction) and exposes :meth:`resolve` for lookups.

    The directory is frozen so the principal set at genesis is structurally
    immutable. To extend the directory, construct a new instance and re-anchor
    a new ``GenesisRecord``.
    """

    identities: tuple[Identity, ...] = ()

    def __post_init__(self) -> None:
        # Coerce iterable to tuple for frozen immutability.
        if not isinstance(self.identities, tuple):
            object.__setattr__(self, "identities", tuple(self.identities))
        # Reject duplicate principal_ids per tenant scope — the audit
        # contract requires a 1:1 mapping; duplicates would silently
        # shadow each other on resolution.
        seen: set[tuple[str, str]] = set()
        for ident in self.identities:
            key = (ident.tenant_id, ident.principal_id)
            if key in seen:
                raise ValueError(
                    f"PrincipalDirectory: duplicate identity "
                    f"({ident.tenant_id!r}, {ident.principal_id!r})"
                )
            seen.add(key)

    def resolve(self, principal_id: str) -> Identity | None:
        """Return the first identity matching ``principal_id`` or ``None``.

        Returns ``None`` rather than raising on miss — callers decide whether
        an unknown principal is fatal (cascade integrity check) or expected
        (lookup against a possibly-stale snapshot).
        """
        for ident in self.identities:
            if ident.principal_id == principal_id:
                return ident
        return None
