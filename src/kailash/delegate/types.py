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
from typing import Any, Literal, get_args

from kailash.trust._locking import validate_id as _validate_id
from kailash.trust.chain import GenesisRecord as SubstrateGenesisRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PrincipalKind discriminator (#1143 §10 G1)
# ---------------------------------------------------------------------------
#
# A Delegate acts through a scoped service-account principal distinct from
# the sovereign (human) principal the Delegate acts for. §10 G1 of the
# Terrene Delegate Specification mandates that the runtime MUST reject any
# Connector binding where these principals collapse — impersonation breaks
# the Genesis-to-Delegation attribution chain.
#
# ``PrincipalKind`` discriminates the THREE legitimate principal types:
#
# - ``"sovereign"`` — the human authority the Delegate ultimately acts for
#   (the natural-person sovereign at the root of the Genesis chain).
# - ``"service_account"`` — the scoped, non-human principal a Connector
#   provisions to mediate a specific external surface (e.g. an HTTP API
#   service account, a queue producer account).
# - ``"delegate"`` — the default for a Delegate-bound identity that does
#   NOT terminate at a Connector. Backwards-compatible default for existing
#   call sites that construct identities without an explicit kind.
#
# The :class:`Role.permitted_principal_kinds` field restricts which kinds
# may bind to a given Role; the :class:`DispatchSurface.__init__` gate
# cross-validates the bound identity's ``principal_kind`` against the
# role's permitted set and raises
# :class:`kailash.delegate.dispatch.DispatchEnvelopeViolationError` on
# mismatch. The same check re-fires at every ``execute()`` start per the
# R2 composition re-validation pattern.
PrincipalKind = Literal["sovereign", "service_account", "delegate"]

#: Frozenset of every valid :data:`PrincipalKind` literal, derived
#: structurally from the Literal at module-load. Used at runtime by
#: :class:`Role.__post_init__` to validate ``permitted_principal_kinds``
#: entries and by :class:`DelegateIdentity.__post_init__` to validate the
#: ``principal_kind`` field. ``get_args(PrincipalKind)`` is the canonical
#: structural enumeration — grep-stable, refactor-safe.
_ALL_PRINCIPAL_KINDS: frozenset[str] = frozenset(get_args(PrincipalKind))


__all__ = [
    "CapabilitySet",
    "DelegateGenesisRecord",
    "DelegateIdentity",
    "LifecycleError",
    "LifecycleState",
    "PrincipalDirectory",
    "PrincipalKind",
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

    State-machine enforcement (#1035 H1 / F-11). The D3 chain is enforced
    at the :meth:`advance_to` level: callers MUST traverse the chain edge-
    by-edge; arbitrary transitions raise :class:`LifecycleError`. Mirrors
    the TAOD state machine pattern at ``runtime.py:441-497`` but on the
    LifecycleState (Delegate-lifetime) axis instead of the TAOD (per-run)
    axis. Two complementary state machines run on every Delegate runtime;
    both are append-only / monotonic.
    """

    PROPOSED = "proposed"
    INSTANTIATED = "instantiated"
    POSTURE_GRADED = "posture_graded"
    ACTIVE = "active"
    RETIRED = "retired"
    ARCHIVED = "archived"

    def advance_to(self, target: "LifecycleState") -> "LifecycleState":
        """Transition to ``target`` state iff legal; raise otherwise.

        Closes #1035 /redteam Round-1 H1 / F-11 (HIGH): the D3 lifecycle
        chain (Proposed→Instantiated→PostureGraded→Active→Retired→Archived)
        was declared in the enum, and :class:`LifecycleError` was defined,
        but no edge-enforcer ever raised it. This method is the structural
        defense — every Delegate lifecycle transition routes through this
        gate; arbitrary jumps or backward edges raise loudly.

        Legal transitions form a single linear chain (D3 invariant). No
        backward edges. No skips. ``Archived`` is terminal (no successor).
        Mirrors the rs ``LifecycleState::advance_to`` shape; cross-SDK
        wire-format parity is preserved because the gate only inspects
        the lowercase string value, identical on both sides.

        Args:
            target: The desired next :class:`LifecycleState`.

        Returns:
            ``target`` itself — convenience for the caller pattern
            ``state = state.advance_to(next_state)``.

        Raises:
            LifecycleError: ``target`` is not the unique legal successor
                OR the current state is terminal (``Archived``).
            TypeError: ``target`` is not a :class:`LifecycleState`.
        """
        if not isinstance(target, LifecycleState):
            raise TypeError(
                "LifecycleState.advance_to(target) MUST be a LifecycleState; "
                f"got {type(target).__name__}"
            )
        expected = _LEGAL_LIFECYCLE_EDGES[self]
        if expected is None:
            # Terminal — no further transitions accepted. Mirror the
            # TAOD terminal-state guard at runtime.py:473-478.
            raise LifecycleError(
                from_state=self,
                to_state=target,
                expected=None,
            )
        if target is not expected:
            raise LifecycleError(
                from_state=self,
                to_state=target,
                expected=expected,
            )
        return target

    @property
    def is_terminal(self) -> bool:
        """Return ``True`` iff this state is the terminal ``Archived`` state.

        Used by callers (runtime hot path) to short-circuit out of the
        lifecycle loop without invoking :meth:`advance_to` with an
        invalid target. Mirrors :attr:`TAODState.is_terminal` at
        ``runtime.py:436``.
        """
        return _LEGAL_LIFECYCLE_EDGES[self] is None


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


# D3 single-linear lifecycle edges (#1035 H1/F-11). The legal-edge map is
# defined at module scope, AFTER LifecycleState (so the enum members are
# bound) and BEFORE any class that constructs LifecycleState (so the map
# is available at first :meth:`advance_to` call). Mirrors the
# ``_LEGAL_SUCCESSORS`` map for TAODState at runtime.py:218-228 — single
# source of truth for the legal successor of each state.
_LEGAL_LIFECYCLE_EDGES: dict[LifecycleState, LifecycleState | None] = {
    LifecycleState.PROPOSED: LifecycleState.INSTANTIATED,
    LifecycleState.INSTANTIATED: LifecycleState.POSTURE_GRADED,
    LifecycleState.POSTURE_GRADED: LifecycleState.ACTIVE,
    LifecycleState.ACTIVE: LifecycleState.RETIRED,
    LifecycleState.RETIRED: LifecycleState.ARCHIVED,
    LifecycleState.ARCHIVED: None,  # terminal — no legal successor
}


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

    S3 (#1035) — the H2 deferral closes here: :meth:`from_dict` is the
    audit-grade validating constructor that closes the direct-dataclass-
    construction bypass. Cross-SDK ingest paths route through
    :meth:`from_dict`; the bare ``__init__`` continues to work for in-
    process construction.

    Args:
        delegate_id: Opaque Delegate identifier (``uuid.UUID``).
        sovereign_ref: Reference to the sovereign authority. EAGER REQUIRED
            — empty string rejected.
        role_binding_ref: Reference to the role binding that scopes this
            Delegate. EAGER REQUIRED — empty string rejected.
        genesis_ref: Reference to the genesis record that roots this
            Delegate's authority chain. EAGER REQUIRED — empty string
            rejected.
        principal_kind: The :data:`PrincipalKind` discriminator (#1143 §10
            G1). One of ``"sovereign"``, ``"service_account"``,
            ``"delegate"``. Defaults to ``"delegate"`` for backwards
            compatibility with existing call sites that pre-date the
            discriminator. :class:`DispatchSurface.__init__` cross-validates
            this against :attr:`Role.permitted_principal_kinds` and raises
            :class:`~kailash.delegate.dispatch.DispatchEnvelopeViolationError`
            on mismatch.
    """

    delegate_id: uuid.UUID
    sovereign_ref: str
    role_binding_ref: str
    genesis_ref: str
    principal_kind: PrincipalKind = "delegate"

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
        # #1143 §10 G1 — principal_kind MUST be one of the declared
        # Literal values. We validate at runtime because Python's static
        # Literal check is type-checker-only; a downstream caller passing
        # an arbitrary string would otherwise silently corrupt the
        # discriminator. Validation against ``_ALL_PRINCIPAL_KINDS``
        # (derived structurally from ``get_args(PrincipalKind)``) keeps
        # the source of truth single — the Literal alias.
        if self.principal_kind not in _ALL_PRINCIPAL_KINDS:
            raise ValueError(
                f"DelegateIdentity.principal_kind MUST be one of "
                f"{sorted(_ALL_PRINCIPAL_KINDS)!r}; got "
                f"{self.principal_kind!r} (#1143 §10 G1 — principal-kind "
                "discriminator)"
            )
        # B3 (Round 2 sec M-1): path-traversal / null-byte / unsafe-char
        # rejection on every externally-sourced ref string. Per
        # trust-plane-security.md MUST Rule 2 the canonical helper is
        # kailash.trust._locking.validate_id. Refs are externally-sourced
        # record-identifier surfaces and the trust-plane rule applies.
        try:
            _validate_id(self.sovereign_ref)
        except ValueError as exc:
            raise ValueError(f"DelegateIdentity.sovereign_ref rejected: {exc}") from exc
        try:
            _validate_id(self.role_binding_ref)
        except ValueError as exc:
            raise ValueError(
                f"DelegateIdentity.role_binding_ref rejected: {exc}"
            ) from exc
        try:
            _validate_id(self.genesis_ref)
        except ValueError as exc:
            raise ValueError(f"DelegateIdentity.genesis_ref rejected: {exc}") from exc

    def to_dict(self) -> dict[str, Any]:
        """Return the canonical wire dict for cross-SDK round-trip (S3 H2).

        Mirrors the EATP SDK convention: ``uuid.UUID`` serializes to its
        string form; the three ``*_ref`` fields pass through verbatim
        (already validated as non-empty + path-safe strings).

        Pair with :meth:`from_dict` for round-trip; consumers serialize
        via :func:`kailash.trust._json.canonical_json_dumps` for cross-SDK
        byte parity.
        """
        return {
            "delegate_id": str(self.delegate_id),
            "sovereign_ref": self.sovereign_ref,
            "role_binding_ref": self.role_binding_ref,
            "genesis_ref": self.genesis_ref,
            "principal_kind": self.principal_kind,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DelegateIdentity:
        """Construct from a JSON-native payload with type coercion + field-
        presence validation (S3 H2 deferral closure).

        B4 (analyst H-3) — honest description of what this constructor does
        relative to the bare ``__init__``:

        - The underlying invariants (UUID format on ``delegate_id``,
          non-emptiness of each ``*_ref``, path-traversal rejection via
          ``kailash.trust._locking.validate_id``) are enforced by
          ``__post_init__`` and ALSO fire on the bare ``__init__`` path.
        - This classmethod adds two contributions on top: (1) JSON-native
          ``str`` → Python-native ``uuid.UUID`` coercion for ``delegate_id``,
          and (2) field-presence checks that raise :class:`ValueError` /
          :class:`TypeError` with a missing-field / wrong-type message
          rather than ``KeyError``.

        Convenience loader for cross-SDK JSON ingest. Bare ``__init__``
        remains the in-process path when callers already have UUIDs +
        strings in hand.
        """
        if not isinstance(payload, dict):
            raise TypeError(
                "DelegateIdentity.from_dict requires a dict; got "
                f"{type(payload).__name__}"
            )
        missing = {
            "delegate_id",
            "sovereign_ref",
            "role_binding_ref",
            "genesis_ref",
        } - set(payload)
        if missing:
            raise ValueError(
                f"DelegateIdentity.from_dict missing required field(s): "
                f"{sorted(missing)}"
            )
        raw_id = payload["delegate_id"]
        if isinstance(raw_id, uuid.UUID):
            delegate_id = raw_id
        elif isinstance(raw_id, str):
            try:
                delegate_id = uuid.UUID(raw_id)
            except (ValueError, AttributeError) as exc:
                raise ValueError(
                    f"DelegateIdentity.from_dict: delegate_id is not a "
                    f"valid UUID string ({raw_id!r}); cross-SDK wire "
                    f"format requires canonical UUID hex"
                ) from exc
        else:
            raise TypeError(
                "DelegateIdentity.from_dict: delegate_id MUST be a str or "
                f"uuid.UUID; got {type(raw_id).__name__}"
            )
        # Coerce ref fields to str defensively — JSON natives are already
        # str, but in-process callers may pass non-str by mistake; let the
        # __post_init__ validate_id check do the path-traversal rejection.
        for field_name in ("sovereign_ref", "role_binding_ref", "genesis_ref"):
            if not isinstance(payload[field_name], str):
                raise TypeError(
                    f"DelegateIdentity.from_dict: {field_name} MUST be a str; "
                    f"got {type(payload[field_name]).__name__}"
                )
        # #1143 §10 G1 — principal_kind round-trip. The field is OPTIONAL
        # in the wire payload (back-compat with payloads emitted before
        # the discriminator landed); when absent we default to "delegate"
        # (matching the dataclass default). When present, it MUST be a
        # str — __post_init__ enforces value validity against the
        # Literal alias.
        principal_kind_raw = payload.get("principal_kind", "delegate")
        if not isinstance(principal_kind_raw, str):
            raise TypeError(
                "DelegateIdentity.from_dict: principal_kind MUST be a str; "
                f"got {type(principal_kind_raw).__name__}"
            )
        return cls(
            delegate_id=delegate_id,
            sovereign_ref=payload["sovereign_ref"],
            role_binding_ref=payload["role_binding_ref"],
            genesis_ref=payload["genesis_ref"],
            principal_kind=principal_kind_raw,  # type: ignore[arg-type]
        )


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

    Deferred to S3 (#1035 follow-up): from_dict validating constructor
    closes the direct-dataclass-construction bypass; tracking via
    workspace todos.
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

    Deferred to S3 (#1035 follow-up): from_dict validating constructor
    closes the direct-dataclass-construction bypass; tracking via
    workspace todos.
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
        permitted_principal_kinds: Frozenset of :data:`PrincipalKind`
            literals this role permits an :class:`DelegateIdentity` to
            bind under (#1143 §10 G1). Defaults to ALL kinds
            (``frozenset({"sovereign", "service_account", "delegate"})``)
            for backwards compatibility with roles defined before the
            discriminator landed. :class:`DispatchSurface.__init__`
            cross-validates ``identity.principal_kind in
            role.permitted_principal_kinds`` at bind, and re-fires the
            check at every ``execute()`` start per R2 composition
            re-validation. Empty frozenset is REJECTED — a role that
            permits no principal-kind is structurally unreachable.

    Deferred to S3 (#1035 follow-up): from_dict validating constructor
    closes the direct-dataclass-construction bypass; tracking via
    workspace todos.
    """

    role_id: uuid.UUID
    display_name: str
    scope: RoleScope
    lifecycle: RoleLifecycleState
    permitted_principal_kinds: frozenset[PrincipalKind] = field(
        default_factory=lambda: frozenset(_ALL_PRINCIPAL_KINDS)  # type: ignore[arg-type]
    )

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
        # #1143 §10 G1 — permitted_principal_kinds discipline. Accept
        # any iterable for ergonomic callers (a plain ``set`` or ``tuple``
        # converts cleanly) but coerce to ``frozenset`` for immutability
        # so the role's permitted set cannot be mutated post-bind.
        if not isinstance(self.permitted_principal_kinds, frozenset):
            try:
                object.__setattr__(
                    self,
                    "permitted_principal_kinds",
                    frozenset(self.permitted_principal_kinds),
                )
            except TypeError as exc:
                raise TypeError(
                    "Role.permitted_principal_kinds MUST be a frozenset (or "
                    "iterable coercible to one) of PrincipalKind literals; "
                    f"got {type(self.permitted_principal_kinds).__name__}"
                ) from exc
        # Empty set is structurally unreachable — a role that permits no
        # principal-kind cannot ever be bound. Reject loudly so the
        # misconfiguration surfaces at construction, not at dispatch.
        if not self.permitted_principal_kinds:
            raise ValueError(
                "Role.permitted_principal_kinds MUST be non-empty; an empty "
                "permitted set is structurally unreachable (no identity can "
                "satisfy it). Use the default (all kinds) for unrestricted "
                "roles."
            )
        # Each entry MUST be a valid PrincipalKind literal — the same
        # Literal-derived allowlist DelegateIdentity validates against.
        invalid = {
            k for k in self.permitted_principal_kinds if k not in _ALL_PRINCIPAL_KINDS
        }
        if invalid:
            raise ValueError(
                f"Role.permitted_principal_kinds contains invalid entries "
                f"{sorted(invalid)!r}; valid kinds are "
                f"{sorted(_ALL_PRINCIPAL_KINDS)!r} (#1143 §10 G1)"
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

    Deferred to S3 (#1035 follow-up): from_dict validating constructor
    closes the direct-dataclass-construction bypass; tracking via
    workspace todos.
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
        # B3 (Round 2 sec M-1): path-traversal / null-byte / unsafe-char
        # rejection on the externally-sourced block.id. The composed
        # chain.GenesisRecord does NOT validate its own id; the wrapper
        # closes that gap per trust-plane-security.md MUST Rule 2.
        try:
            _validate_id(self.block.id)
        except ValueError as exc:
            raise ValueError(f"DelegateGenesisRecord.block.id rejected: {exc}") from exc
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

    Verification-key store (#1035 C1 closure). The directory carries an
    OPTIONAL ``verification_keys`` mapping from ``delegate_id`` to the
    32-byte Ed25519 public key bytes for that signer. The mapping is
    independent of :class:`DelegateIdentity` so the wire-format identity
    stays stable while the crypto material is wired alongside.
    :class:`kailash.delegate.verifier.Ed25519Verifier` reads
    :meth:`public_key_for` to obtain the public key for a given signer.
    A directory constructed without ``verification_keys`` returns
    ``None`` from :meth:`public_key_for` for every id; downstream
    verifiers fall closed on the missing key (a NullVerifier-equivalent
    posture per the verifier contract).

    Cross-impl note. Ed25519 32-byte public-key form is the rs canonical
    wire format per
    ``workspaces/issue-1035-delegate-py/01-analysis/02-kailash-rs-reference-extraction.md:289``.
    Byte-match cross-SDK verifier receipts are DEFERRED pending
    rs-library confirmation per ``cross-sdk-inspection.md`` Rule 4.

    Deferred to S3 (#1035 follow-up): from_dict validating constructor
    closes the direct-dataclass-construction bypass; tracking via
    workspace todos.
    """

    identities: tuple[DelegateIdentity, ...] = ()
    verification_keys: dict[uuid.UUID, bytes] = field(default_factory=dict)

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
        # Validate verification_keys shape (#1035 C1): keys MUST be
        # uuid.UUID, values MUST be exactly-32-byte bytes (Ed25519
        # canonical). Wrong shape fails loud at construction so a
        # mis-wired directory cannot silently fall through to "key not
        # found" at verify time.
        if not isinstance(self.verification_keys, dict):
            raise TypeError(
                "PrincipalDirectory.verification_keys MUST be a dict; got "
                f"{type(self.verification_keys).__name__}"
            )
        for key_id, key_bytes in self.verification_keys.items():
            if not isinstance(key_id, uuid.UUID):
                raise TypeError(
                    "PrincipalDirectory.verification_keys keys MUST be "
                    f"uuid.UUID; got {type(key_id).__name__}"
                )
            if not isinstance(key_bytes, (bytes, bytearray)):
                raise TypeError(
                    f"PrincipalDirectory.verification_keys[{key_id!r}] "
                    f"MUST be bytes; got {type(key_bytes).__name__}"
                )
            if len(key_bytes) != 32:
                raise ValueError(
                    f"PrincipalDirectory.verification_keys[{key_id!r}] "
                    f"MUST be exactly 32 bytes (Ed25519 canonical public-"
                    f"key form); got {len(key_bytes)}"
                )

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

    def public_key_for(self, delegate_id: uuid.UUID) -> bytes | None:
        """Return the 32-byte Ed25519 public key for ``delegate_id``.

        Returns ``None`` when (a) the directory was constructed without
        a ``verification_keys`` mapping for that id, OR (b) the id is
        not in the mapping. Used by
        :class:`kailash.delegate.verifier.Ed25519Verifier` to obtain
        the public key; the verifier falls closed on ``None`` so a
        missing key is structurally indistinguishable from an unknown
        signer — both are "cannot verify" in the same way.

        Args:
            delegate_id: The signer's :attr:`DelegateIdentity.delegate_id`.

        Returns:
            32-byte Ed25519 public key bytes, or ``None`` on miss.
        """
        if not isinstance(delegate_id, uuid.UUID):
            raise TypeError(
                "PrincipalDirectory.public_key_for requires a uuid.UUID; "
                f"got {type(delegate_id).__name__}"
            )
        return self.verification_keys.get(delegate_id)
