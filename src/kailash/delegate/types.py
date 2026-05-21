# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Canonical type substrate for ``kailash.delegate`` (#1035).

Mirrors the kailash-rs ``kailash-delegate-types`` crate's M2-01 substrate-
composition wrappers. Per the /autonomize Option A decision (rs-shipped
impl is the de facto spec until the authored Delegate Spec lands), this
module restructures S2's initial flat-anchor types into the canonical
rs shape:

- ``DelegateIdentity`` mirrors rs ``identity.rs:91-126`` — opaque
  ``delegate_id: UUID`` + three eager-required ref strings.
- ``Role`` mirrors rs ``role.rs:126-154`` — opaque ``role_id: UUID`` +
  display name + structured ``RoleScope(domain, capabilities)`` +
  ``RoleLifecycleState``. ``CapabilitySet`` carries explicit
  ``intersect()`` (multi-role membership MUST intersect, never union —
  rs B1 / privilege-escalation guard).
- ``DelegateGenesisRecord`` COMPOSES the existing
  :class:`kailash.trust.chain.GenesisRecord` per rs ``composition.rs:51-88``
  ("§249 compose, NEVER re-derive"). The composed block is held in a public
  field; spine-level extensions (``spec_version``, ``capabilities``) live
  alongside, never replacing.
- ``LifecycleState`` is the D3 single linear chain ``Proposed →
  Instantiated → PostureGraded → Active → Retired → Archived`` (rs
  ``lifecycle.rs:91-103``).
- ``PrincipalDirectory`` keys lookups on ``delegate_id: UUID`` post-
  restructure (was string ``principal_id`` pre-Option-A).

Cross-SDK byte-canonical fixtures emitted by either implementation can be
verified by the other via :func:`kailash.trust._json.canonical_json_dumps`.

All dataclasses are ``frozen=True, slots=True`` because runtime composition
is tighten-only (F5 invariant — see :mod:`kailash.delegate.envelope`).
"""

from __future__ import annotations

import dataclasses
import logging
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from kailash.trust.chain import GenesisRecord as SubstrateGenesisRecord

logger = logging.getLogger(__name__)

__all__ = [
    "CapabilitySet",
    "DelegateGenesisRecord",
    "DelegateIdentity",
    "LifecycleError",
    "LifecycleState",
    "PrincipalDirectory",
    "Role",
    "RoleLifecycleState",
    "RoleScope",
]


# ---------------------------------------------------------------------------
# Hex validation helpers (F6)
# ---------------------------------------------------------------------------

_HEX_RE = re.compile(r"^[0-9a-f]+$")


def _validate_hex(value: str, *, expected_len: int, field_name: str) -> None:
    """Validate a lowercase-hex string is exactly ``expected_len`` chars.

    Cross-SDK byte-canonical fixtures depend on a single uniform hex form
    (lowercase, no ``0x`` prefix, exact length per algorithm). Drift here
    silently breaks rs↔py round-trip parity (per ``cross-sdk-inspection.md``
    Rule 4).

    Args:
        value: The hex string to validate.
        expected_len: Required character length (64 for SHA-256, 128 for
            Ed25519 signatures).
        field_name: Field name used in the error message for actionability.

    Raises:
        ValueError: If ``value`` is not exactly ``expected_len`` lowercase
            hex characters.
    """
    if len(value) != expected_len:
        raise ValueError(
            f"{field_name} MUST be exactly {expected_len} hex chars "
            f"(got {len(value)}); cross-SDK fixture parity requires the "
            f"exact algorithm-derived length."
        )
    if not _HEX_RE.fullmatch(value):
        raise ValueError(
            f"{field_name} MUST be lowercase hex [0-9a-f]+ "
            f"(uppercase or non-hex chars break canonical wire format)."
        )


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


class RoleLifecycleState(str, Enum):
    """Role lifecycle (rs ``role.rs:50-61``).

    Distinct from :class:`LifecycleState` (which governs a Delegate's
    lifecycle). A role MAY be Draft (defined, not active), Active (bindings
    permitted), Suspended (existing bindings hold, no new ones), or Retired
    (no further bindings).
    """

    DRAFT = "draft"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    RETIRED = "retired"


# ---------------------------------------------------------------------------
# Identity (F2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DelegateIdentity:
    """Substrate-composition wrapper for a Delegate identity.

    Mirrors rs ``DelegateIdentity`` (``identity.rs:91-126``). The
    ``delegate_id`` is a bare opaque UUID — deliberately NOT a
    ``(organization_id, role_id, spec_version)`` tuple. Keying identity
    on that triple would re-root the Genesis chain whenever any of those
    moved (rs ratified A1).

    All three ``*_ref`` fields are EAGER REQUIRED (never ``Option`` / None
    in rs). A Delegate that cannot name its sovereign / role binding /
    genesis is not a valid identity.

    Args:
        delegate_id: Opaque Delegate identifier (``uuid.UUID``).
        sovereign_ref: Reference to the sovereign authority. EAGER REQUIRED
            — empty string rejected.
        role_binding_ref: Reference to the role binding that scopes this
            Delegate. EAGER REQUIRED — empty string rejected.
        genesis_ref: Reference to the genesis record that roots this
            Delegate's authority chain. EAGER REQUIRED — empty string
            rejected.
    """

    delegate_id: uuid.UUID
    sovereign_ref: str
    role_binding_ref: str
    genesis_ref: str

    def __post_init__(self) -> None:
        if not isinstance(self.delegate_id, uuid.UUID):
            raise TypeError(
                "DelegateIdentity.delegate_id MUST be a uuid.UUID; got "
                f"{type(self.delegate_id).__name__}"
            )
        if not self.sovereign_ref:
            raise ValueError(
                "DelegateIdentity.sovereign_ref MUST be a non-empty string "
                "(EAGER REQUIRED per rs identity.rs:91-126)"
            )
        if not self.role_binding_ref:
            raise ValueError(
                "DelegateIdentity.role_binding_ref MUST be a non-empty string"
            )
        if not self.genesis_ref:
            raise ValueError("DelegateIdentity.genesis_ref MUST be a non-empty string")


# ---------------------------------------------------------------------------
# Role / RoleScope / CapabilitySet (F3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CapabilitySet:
    """Capability set held by a :class:`RoleScope`.

    Mirrors rs ``CapabilitySet`` (``role.rs:69-96``). The ``capabilities``
    field is a frozen tuple of capability tokens (Python proxy for rs's
    ``Vec<Capability>``; the EATP ``Capability`` taxonomy is not yet
    surfaced in kailash-py, so spine-declared string tokens are used —
    aligned with rs ``GenesisRecord.capabilities: Vec<String>`` per
    ``composition.rs:62``).

    The :meth:`intersect` method composes two capability sets via set
    intersection — the privilege-non-escalation primitive multi-role
    binding requires (rs ratified B1). Union is deliberately NOT provided:
    accumulating roles MUST NOT accumulate capabilities (that is a
    privilege-escalation primitive).
    """

    capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.capabilities, tuple):
            object.__setattr__(self, "capabilities", tuple(self.capabilities))

    def intersect(self, other: CapabilitySet) -> CapabilitySet:
        """Return the INTERSECTION of two capability sets.

        Multi-role membership composes role scopes via intersection (rs B1)
        — a Delegate bound to two roles holds only the capabilities BOTH
        roles grant. Union is intentionally not provided; widening
        capability by accumulating roles is a privilege-escalation
        primitive the intersection rule structurally closes.
        """
        if not isinstance(other, CapabilitySet):
            raise TypeError(
                "CapabilitySet.intersect requires a CapabilitySet; got "
                f"{type(other).__name__}"
            )
        # Preserve order from self; rs uses Vec.contains which is O(n) but
        # order-stable; python tuple comprehension mirrors that.
        other_set = set(other.capabilities)
        kept = tuple(c for c in self.capabilities if c in other_set)
        return CapabilitySet(capabilities=kept)


@dataclass(frozen=True, slots=True)
class RoleScope:
    """Scope of a role — BOTH axes (rs ratified B4).

    Mirrors rs ``RoleScope`` (``role.rs:107-113``). Carries BOTH a domain
    address AND a capability set. rs composes ``kailash_governance::
    Address`` (the PACT D/T/R addressing primitive); the kailash-py
    counterpart isn't yet exposed as a structured type, so we accept a
    string domain identifier and document the cross-SDK gap. When the
    Python PACT Address type lands, this field MUST be tightened to that
    type (tracking surface: align with rs role.rs::Address).

    Args:
        domain: PACT D/T/R domain identifier the role operates within.
            Empty string rejected.
        capabilities: The :class:`CapabilitySet` this role grants within
            its domain.
    """

    domain: str
    capabilities: CapabilitySet = field(default_factory=CapabilitySet)

    def __post_init__(self) -> None:
        if not self.domain:
            raise ValueError("RoleScope.domain MUST be a non-empty string")
        if not isinstance(self.capabilities, CapabilitySet):
            raise TypeError(
                "RoleScope.capabilities MUST be a CapabilitySet; got "
                f"{type(self.capabilities).__name__}"
            )


@dataclass(frozen=True, slots=True)
class Role:
    """A net-new first-class spine role (rs ratified B3).

    Mirrors rs ``Role`` (``role.rs:126-154``).

    Args:
        role_id: Opaque per-tenant role identifier (``uuid.UUID``).
        display_name: Human-readable display name. Empty string rejected.
        scope: The :class:`RoleScope` — domain + capabilities (both axes).
        lifecycle: The :class:`RoleLifecycleState` this role is in.
    """

    role_id: uuid.UUID
    display_name: str
    scope: RoleScope
    lifecycle: RoleLifecycleState

    def __post_init__(self) -> None:
        if not isinstance(self.role_id, uuid.UUID):
            raise TypeError(
                "Role.role_id MUST be a uuid.UUID; got "
                f"{type(self.role_id).__name__}"
            )
        if not self.display_name:
            raise ValueError("Role.display_name MUST be a non-empty string")
        if not isinstance(self.scope, RoleScope):
            raise TypeError(
                f"Role.scope MUST be a RoleScope; got {type(self.scope).__name__}"
            )
        if not isinstance(self.lifecycle, RoleLifecycleState):
            raise TypeError(
                "Role.lifecycle MUST be a RoleLifecycleState; got "
                f"{type(self.lifecycle).__name__}"
            )


# ---------------------------------------------------------------------------
# DelegateGenesisRecord — composes substrate kailash.trust.chain.GenesisRecord (F4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DelegateGenesisRecord:
    """Substrate-composition anchor for a Delegate's lifetime.

    Mirrors rs ``GenesisRecord`` (``composition.rs:51-88``) per the §249
    "compose, NEVER re-derive" contract. The kailash-py substrate genesis
    block at :class:`kailash.trust.chain.GenesisRecord` (chain.py:121) is
    held verbatim in the public :attr:`block` field; this wrapper adds
    exactly the two spine-level fields rs adds on top:

    - ``spec_version`` — Delegate Spec version (rs ledger row 14.3).
    - ``capabilities`` — spine-declared capability identifiers, distinct
      from any EATP capability enum the substrate may carry separately.

    Signing remains the substrate's responsibility: a
    ``DelegateGenesisRecord`` is constructed from an already-shaped
    substrate ``GenesisRecord``; this wrapper does NOT re-implement block
    hashing or signature computation.

    The :meth:`to_canonical_dict` method emits a nested
    ``{"block": {...substrate...}, "spec_version": "...", "capabilities":
    [...]}`` shape suitable for routing through
    :func:`kailash.trust._json.canonical_json_dumps` to achieve byte-
    canonical parity with rs reference fixtures.

    Note: the existing :class:`kailash.trust.chain.GenesisRecord` does NOT
    currently expose all the cryptographic fields rs's substrate
    ``GenesisBlock`` carries (``principal_directory_anchor``,
    ``initial_envelope_hash``, ``delegation_proof`` — these were the flat
    fields S2 invented before Option A). Closing that gap is a separate
    workstream (tracking surface: align substrate chain.GenesisRecord
    with rs GenesisBlock cryptographic fields). For now the wrapper
    composes the existing block as-is.
    """

    block: SubstrateGenesisRecord
    spec_version: str = "1"
    capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.block, SubstrateGenesisRecord):
            raise TypeError(
                "DelegateGenesisRecord.block MUST be a "
                "kailash.trust.chain.GenesisRecord; got "
                f"{type(self.block).__name__}"
            )
        if not self.spec_version:
            raise ValueError(
                "DelegateGenesisRecord.spec_version MUST be a non-empty string"
            )
        if self.block.created_at.tzinfo is None:
            raise ValueError(
                "DelegateGenesisRecord.block.created_at MUST be "
                "timezone-aware (naive datetimes break cross-SDK wire-"
                "format parity)"
            )
        # F6: hex length + format validation on the cryptographic
        # signature surface. The substrate block carries an Ed25519
        # signature; the default algorithm is "Ed25519" per chain.py:148.
        if self.block.signature_algorithm == "Ed25519":
            _validate_hex(
                self.block.signature,
                expected_len=128,
                field_name="DelegateGenesisRecord.block.signature (Ed25519)",
            )
        # B4 (Round 2 sec M-2): snapshot the composed substrate block so
        # post-construction mutation of the original is invisible through
        # the wrapper. Without this, a caller can mutate ``block.signature``
        # AFTER construction; ``_validate_hex`` fires once and never re-fires,
        # leaving the wrapper holding a now-invalid hex signature with no
        # signal. ``dataclasses.replace`` produces a new instance with the
        # same field values — same canonical bytes, isolated identity.
        snapshot = dataclasses.replace(self.block)
        object.__setattr__(self, "block", snapshot)
        # Coerce iterable to tuple for frozen immutability.
        if not isinstance(self.capabilities, tuple):
            object.__setattr__(self, "capabilities", tuple(self.capabilities))

    @property
    def genesis_id(self) -> str:
        """Convenience accessor for the composed block's id (audit surface)."""
        return self.block.id

    def to_canonical_dict(self) -> dict[str, Any]:
        """Return a canonical-JSON-ready dict for cross-SDK byte parity.

        Includes the signature. Use :meth:`to_signing_dict` for the
        pre-signature payload (F7 — sign/verify split).

        Routes through :func:`kailash.trust._json.canonical_json_dumps` at
        the call site; field NAMES and value TYPES MUST match the rs side
        exactly. The nested ``"block"`` key mirrors rs ``composition.rs::
        GenesisRecord::block``.
        """
        block_payload = self.block.to_signing_payload()
        block_payload["signature"] = self.block.signature
        block_payload["signature_algorithm"] = self.block.signature_algorithm
        return {
            "block": block_payload,
            "spec_version": self.spec_version,
            "capabilities": list(self.capabilities),
        }

    def to_signing_dict(self) -> dict[str, Any]:
        """Return the pre-signature canonical dict (F7 — sign/verify split).

        EXCLUDES the signature field. Used by the signer/verifier to
        compute or verify the signature over a deterministic byte payload.

        Mirrors the substrate ``GenesisRecord.to_signing_payload()`` shape
        (chain.py:158) extended with the spine-level ``spec_version`` and
        ``capabilities``. The signature is computed over THIS dict's
        canonical-JSON encoding; :meth:`to_canonical_dict` then adds the
        signature for transport.
        """
        return {
            "block": self.block.to_signing_payload(),
            "spec_version": self.spec_version,
            "capabilities": list(self.capabilities),
        }


# ---------------------------------------------------------------------------
# Principal directory (F5)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PrincipalDirectory:
    """Signer registry for a Delegate's tenant scope.

    Post-F2 (Option A restructure), identities are :class:`DelegateIdentity`
    keyed on ``delegate_id: UUID``. Mirrors rs ``directory.rs:21-62``
    (deterministic, audit-stable iteration over ``BTreeMap<DelegateId, _>``).
    Python uses a frozen tuple snapshot and exposes :meth:`resolve` for
    UUID-keyed lookups.

    The directory is frozen so the principal set at genesis is structurally
    immutable. To extend the directory, construct a new instance and re-
    anchor a new :class:`DelegateGenesisRecord`.
    """

    identities: tuple[DelegateIdentity, ...] = ()

    def __post_init__(self) -> None:
        # Coerce iterable to tuple for frozen immutability.
        if not isinstance(self.identities, tuple):
            object.__setattr__(self, "identities", tuple(self.identities))
        # Reject duplicate delegate_ids — the audit contract requires a
        # 1:1 mapping; duplicates would silently shadow each other on
        # resolution. F5: post-F2, key is delegate_id alone.
        seen: set[uuid.UUID] = set()
        for ident in self.identities:
            if ident.delegate_id in seen:
                raise ValueError(
                    f"PrincipalDirectory: duplicate identity "
                    f"(delegate_id={ident.delegate_id!r})"
                )
            seen.add(ident.delegate_id)

    def resolve(self, delegate_id: uuid.UUID) -> DelegateIdentity | None:
        """Return the identity matching ``delegate_id`` or ``None`` on miss.

        Returns ``None`` rather than raising on miss — callers decide
        whether an unknown principal is fatal (cascade integrity check)
        or expected (lookup against a possibly-stale snapshot).
        """
        if not isinstance(delegate_id, uuid.UUID):
            raise TypeError(
                "PrincipalDirectory.resolve requires a uuid.UUID; got "
                f"{type(delegate_id).__name__}"
            )
        for ident in self.identities:
            if ident.delegate_id == delegate_id:
                return ident
        return None
