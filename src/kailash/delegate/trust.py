# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
# pyright: reportUnnecessaryIsInstance=false
"""Trust-cascade composition layer for ``kailash.delegate`` (S3 of #1035).

Mirrors the kailash-rs ``kailash-delegate-trust`` crate's M3-01 + M3-02
shipped surface (issue #1035 § trust-cascade):

- :class:`TenantScope` — typed 2-variant tagged union mirroring rs
  ``TenantScope`` (``cascade.rs:101-149``). Either :class:`TenantScope.global_`
  (no boundary) or :class:`TenantScope.for_tenant("id")`. The
  ``Global``/``Tenant`` distinction is STRUCTURAL — "no isolation" is the
  explicit ``Global`` variant, never an implicit ``None`` default that
  silently disables the tenant boundary in a deployment that should have
  been tenant-scoped (rs M-1 misconfiguration guard).
- :class:`TenantScopedCascade` — the load-bearing cascade gate enforcing
  fail-closed (1) tenant-first isolation (rs Option A RATIFIED), (2) F1
  downward-only scope subset, (3) pairwise envelope tightening across
  every PACT dimension via the existing
  :meth:`kailash.delegate.envelope.DelegateConstraintEnvelope.tighten_with`
  (which inherits the S2.5 F5 widening-raise gate). On success it emits a
  :class:`GrantMoment` chain-of-custody record.
- :class:`GrantMoment` — mirrors rs ``GrantMoment`` (``grant.rs:186-198``).
  Frozen, tz-aware, hex-signature-validated, with ``to_canonical_dict()``
  + ``to_signing_dict()`` (sign/verify split per S2.5 F7) suitable for
  routing through :func:`kailash.trust._json.canonical_json_dumps` for
  cross-SDK byte-canonical parity with rs reference fixtures.

The cascade is fail-closed at EVERY step; an error in any step raises a
typed error BEFORE the next step runs. Mirrors rs ``cascade_child``'s
fixed-order check sequence at ``cascade.rs:276-313``.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from kailash.delegate.envelope import DelegateConstraintEnvelope, EnvelopeWideningError
from kailash.delegate.types import (
    CapabilitySet,
    DelegateIdentity,
    RoleScope,
    _validate_hex,
)
from kailash.delegate.verifier import NullVerifier, Verifier
from kailash.trust._json import canonical_json_dumps

logger = logging.getLogger(__name__)

__all__ = [
    "CascadeScopeExpansionError",
    "CascadeSignatureError",
    "CascadeTenantViolationError",
    "GrantMoment",
    "TenantScope",
    "TenantScopedCascade",
]


# ---------------------------------------------------------------------------
# Typed errors (Option A RATIFIED + F1)
# ---------------------------------------------------------------------------


class CascadeTenantViolationError(ValueError):
    """Raised when :meth:`TenantScopedCascade.cascade_child` crosses tenant.

    Mirrors the rs ``TrustGateError::TenantIsolation`` variant (``error.rs:
    51-65``). Tenant-first isolation per Option A RATIFIED: a Tenant-A
    cascade cannot admit a Tenant-B child even when the scope subset +
    envelope tightening would otherwise pass.

    ``ValueError``-derived because the cross-tenant cascade is a contract
    violation by the caller, not a system fault.
    """

    def __init__(
        self,
        parent_tenant: str | None,
        child_tenant: str | None,
    ) -> None:
        self.parent_tenant = parent_tenant
        self.child_tenant = child_tenant
        # B1 (sec H-2): hash tenant IDs in the user-facing message per
        # observability.md MUST Rule 8 (schema-revealing field names MUST be
        # DEBUG or hashed). Raw tenant IDs remain on the exception
        # attributes for in-process handling (tested), but the str(exc) form
        # that may bleed into logs / cross-tenant error returns / aggregator
        # surfaces carries only the 8-char SHA-256 prefix.
        super().__init__(
            f"tenant isolation violated: "
            f"parent_tenant_hash={_tenant_id_hash(parent_tenant)} != "
            f"child_tenant_hash={_tenant_id_hash(child_tenant)} (Option A "
            f"RATIFIED — a cross-tenant cascade is fail-closed regardless of "
            f"scope/envelope tightening)"
        )


def _tenant_id_hash(tenant_id: str | None) -> str:
    """Return a short SHA-256 prefix of a tenant id for log-safe display.

    ``None`` returns the literal sentinel ``"<none>"`` (the Global variant has
    no tenant id). Otherwise the first 8 hex chars of the SHA-256 digest of
    the UTF-8 bytes — enough to disambiguate ~4×10^9 tenants in audit
    correlation while not leaking the raw id into log aggregators (per
    ``observability.md`` MUST Rule 8).
    """
    if tenant_id is None:
        return "<none>"
    return hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()[:8]


class CascadeScopeExpansionError(ValueError):
    """Raised when a child's :class:`RoleScope` expands its parent's scope.

    Mirrors the rs ``TrustGateError::CascadeWidening`` variant (``error.rs:
    44-49``). F1 (ratified): the cascade is downward-only — a child scope
    that is not a subset of its parent is rejected here.

    Subset semantics:
    - **Domain**: child MUST equal parent's domain (no cross-domain cascade).
    - **Capabilities**: child :class:`CapabilitySet` MUST be a subset of
      parent's (the intersection of parent ∩ child MUST equal child —
      mirrors rs ``DelegationScope::is_subset_of`` operations check).

    ``ValueError``-derived per the same caller-fault rationale as
    :class:`CascadeTenantViolationError`.
    """

    def __init__(
        self,
        parent_domain: str,
        child_domain: str,
        added_capabilities: tuple[str, ...] = (),
    ) -> None:
        self.parent_domain = parent_domain
        self.child_domain = child_domain
        self.added_capabilities = added_capabilities
        if parent_domain != child_domain:
            msg = (
                f"cascade scope expansion: child domain {child_domain!r} "
                f"differs from parent domain {parent_domain!r} (F1 "
                f"downward-only requires identical domain)"
            )
        else:
            msg = (
                f"cascade scope expansion: child added capabilities "
                f"{sorted(added_capabilities)!r} not in parent's capability "
                f"set (F1 downward-only requires subset; widening blocked)"
            )
        super().__init__(msg)


class CascadeSignatureError(ValueError):
    """Raised when ``grant_proof`` fails cryptographic verification.

    Closes #1035 /redteam Round-1 C1 (CRITICAL) on the cascade surface:
    prior :meth:`TenantScopedCascade.cascade_child` accepted any
    128-char hex ``grant_proof`` and validated it as shape-only — the
    same "fake encryption" failure mode the audit-chain surface
    carried. Per :class:`kailash.delegate.verifier.Verifier`, the
    cascade now consults a real Ed25519 verifier against the canonical
    grant-signing bytes; a verify miss raises this typed error BEFORE
    any cascade state mutates.

    ``ValueError``-derived, like the sibling cascade errors. The
    error message names the parent identity whose grant failed
    verification; the verifier itself never raises (it returns
    False) so this is the only signal the cascade emits on signature
    failure.
    """

    def __init__(
        self,
        parent_delegate_id: uuid.UUID,
        verifier_class: str,
    ) -> None:
        self.parent_delegate_id = parent_delegate_id
        self.verifier_class = verifier_class
        super().__init__(
            f"cascade grant signature verification failed for parent "
            f"delegate_id={parent_delegate_id!r} (verifier={verifier_class}). "
            f"Either the grant_proof is invalid for the canonical grant-"
            f"signing bytes, the parent is not registered in the "
            f"PrincipalDirectory, or the verifier is fail-closed (wire "
            f"an Ed25519Verifier with a populated directory)."
        )


# ---------------------------------------------------------------------------
# TenantScope — typed 2-variant tagged union (M-1 misconfiguration guard)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TenantScope:
    """The spine's tenant scope key (rs Option A RATIFIED).

    Mirrors rs ``TenantScope`` (``cascade.rs:101-149``). A typed 2-variant
    tagged union, NOT an ``Optional[str]``: "global / unscoped" is the
    explicit :meth:`TenantScope.global_` variant, never an implicit
    ``None``-default that silently disables the tenant boundary in a
    deployment that should have been tenant-scoped (M-1 guard).

    Construction MUST go through the classmethod factories
    (:meth:`global_` or :meth:`for_tenant`) so the "Global vs Tenant"
    choice is auditable at the call site.

    Equality is structural — two scopes with the same ``tenant_id`` compare
    equal; Global compares equal only to Global; Global never equals
    ``Tenant("global")`` (the typed enum makes the distinction structural,
    not stringly).
    """

    # Private discriminant: True = Global, False = Tenant
    # Public callers MUST use the classmethods, never construct directly.
    _is_global: bool
    _tenant_id: str | None

    def __post_init__(self) -> None:
        # Defense-in-depth: the dataclass invariant is global xor tenant_id.
        if self._is_global and self._tenant_id is not None:
            raise ValueError(
                "TenantScope: Global variant MUST NOT carry a tenant_id "
                "(construct via TenantScope.global_() or .for_tenant(id))"
            )
        if not self._is_global and self._tenant_id is None:
            raise ValueError(
                "TenantScope: Tenant variant MUST carry a non-None tenant_id "
                "(construct via TenantScope.for_tenant(id))"
            )
        if not self._is_global and self._tenant_id is not None and not self._tenant_id:
            raise ValueError("TenantScope.for_tenant requires a non-empty tenant id")

    @classmethod
    def global_(cls) -> TenantScope:
        """Return the explicit unscoped / global variant.

        This is the DELIBERATE "no tenant boundary" choice — a tenant-scoped
        deployment MUST NOT seed this. The classmethod name is ``global_``
        (trailing underscore) because ``global`` is a Python keyword.
        """
        return cls(_is_global=True, _tenant_id=None)

    @classmethod
    def for_tenant(cls, tenant_id: str) -> TenantScope:
        """Return a concrete tenant boundary keyed on ``tenant_id``.

        A cascade bound to ``for_tenant("a")`` rejects a child claiming
        ``for_tenant("b")`` (or ``global_()``) fail-closed via
        :class:`CascadeTenantViolationError`.
        """
        if not isinstance(tenant_id, str):
            raise TypeError(
                "TenantScope.for_tenant requires a str tenant_id; got "
                f"{type(tenant_id).__name__}"
            )
        return cls(_is_global=False, _tenant_id=tenant_id)

    @property
    def tenant_id(self) -> str | None:
        """Borrow the tenant id (``None`` = unscoped / global).

        Preserved verbatim from the rs accessor shape so cross-SDK consumers
        of the M3-01 tenant scope-key surface keep their idioms.
        """
        return self._tenant_id

    @property
    def is_global(self) -> bool:
        """``True`` iff this scope is the explicit unscoped / global variant.

        A conformance helper for tenant-scoped deployments: ``assert not
        scope.is_global`` makes a misconfigured global seed a loud test
        failure rather than a silent contamination surface (M-1 guard).
        """
        return self._is_global

    def to_dict(self) -> dict[str, Any]:
        """Serialize this :class:`TenantScope` to its canonical wire dict.

        B2 (sec H-3): promoted from the private module-level
        ``_tenant_to_dict`` helper to a public instance method per the EATP
        SDK convention that every public dataclass exposes ``to_dict`` +
        ``from_dict``. Cross-SDK ingest/emit paths route through this method
        (and :meth:`from_dict`) instead of the now-removed private helper.

        Cross-SDK wire format mirrors rs's tagged-union JSON: ``{"type":
        "Global"}`` or ``{"type": "Tenant", "tenant_id": "..."}``. The
        discriminator key is ``type`` for compatibility with rs serde's
        default tagged-enum representation.

        CROSS-SDK note (B6): rs ``cascade.rs::TenantScope`` does NOT yet
        declare serde derives, so the rs wire format is UNDEFINED. When rs
        adds serde, this wire format MUST be reconciled.
        """
        if self.is_global:
            return {"type": "Global"}
        return {"type": "Tenant", "tenant_id": self.tenant_id}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> TenantScope:
        """Deserialize a :class:`TenantScope` from its canonical wire dict.

        B2 (sec H-3): promoted from the private module-level
        ``_tenant_from_dict`` helper to a public classmethod per the EATP SDK
        convention. Inverse of :meth:`to_dict`.

        Raises:
            TypeError: if ``payload`` is not a dict.
            ValueError: on missing/unknown discriminator or missing /
                non-string ``tenant_id`` for the Tenant variant.
        """
        if not isinstance(payload, dict):
            raise TypeError(
                f"TenantScope.from_dict requires a dict; got "
                f"{type(payload).__name__}"
            )
        discriminator = payload.get("type")
        if discriminator == "Global":
            return cls.global_()
        if discriminator == "Tenant":
            tenant_id = payload.get("tenant_id")
            if not isinstance(tenant_id, str):
                raise ValueError(
                    "TenantScope.from_dict payload type=Tenant requires a "
                    "string tenant_id"
                )
            return cls.for_tenant(tenant_id)
        raise ValueError(
            f"TenantScope.from_dict: unknown discriminator: {discriminator!r} "
            f"(expected 'Global' or 'Tenant')"
        )


# ---------------------------------------------------------------------------
# TenantScopedCascade — the F1/F5/Option-A gate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TenantScopedCascade:
    """A delegation cascade scoped to a single :class:`TenantScope`.

    Mirrors rs ``TenantScopedCascade`` (``cascade.rs:196-335``). The cascade
    is fail-closed at every step; each :meth:`cascade_child` call validates
    the parent→child edge in fixed order:

    1. **Tenant boundary** (Option A RATIFIED) — child tenant MUST equal
       this cascade's tenant. Checked FIRST so a Tenant-A cascade cannot
       even reach the scope/envelope checks for a Tenant-B child. Raises
       :class:`CascadeTenantViolationError`.
    2. **Scope subset** (F1 downward-only) — child :class:`RoleScope`'s
       domain MUST equal parent's; child capabilities MUST be a subset of
       parent's. Raises :class:`CascadeScopeExpansionError`.
    3. **Envelope tightening** (F5) — delegates to the existing
       :meth:`DelegateConstraintEnvelope.tighten_with`, which carries the
       S2.5 pre-intersection widening check. Raises
       :class:`EnvelopeWideningError` on any dimension widening.
    4. **Register child + emit GrantMoment** — on success, the child's
       ``delegate_id`` is appended to the internal grantee registry AND a
       fully-formed :class:`GrantMoment` chain-of-custody record is
       returned.

    The cascade is bound to a single tenant at construction; cascading a
    cross-tenant child requires a NEW cascade for that tenant.

    Grantee Registry (#1146 H1)
    ---------------------------
    The cascade carries an internal mutable set of authorized grantee
    ``delegate_id``\\s exposed read-only via :attr:`grantees`. The registry
    is populated by:

    * :meth:`register_root_grantee` — explicit seeding of the root sovereign
      who anchors the cascade; called by infrastructure at cascade-setup
      time. The first identity authorized to dispatch under this cascade.
    * :meth:`cascade_child` — on success (all 3 validation steps pass), both
      ``parent_identity.delegate_id`` and ``child_identity.delegate_id`` are
      registered as grantees BEFORE the :class:`GrantMoment` is emitted.

    The registry is the structural anchor :class:`DispatchSurface` checks at
    bind + dispatch time: a DispatchSurface constructed with an identity
    whose ``delegate_id`` is not in ``cascade.grantees`` is refused with
    :class:`DispatchCascadeViolationError`. This closes PR #1144 holistic
    /redteam HIGH finding H1 — previously any caller with ANY
    :class:`DelegateIdentity` and a tenant-matching cascade could construct
    a DispatchSurface that audited as that identity; now only identities
    that have been registered with this cascade (via
    :meth:`register_root_grantee` or as a parent/child side-effect of a
    successful :meth:`cascade_child` call) are admissible. Registration
    is the structural gate; the cascade reference itself is the trust
    authority for seeding (see trust-boundary note below + README #1147
    disclosure for durable-attestation roadmap).

    The internal set is mutable BUT carried via ``object.__setattr__`` so
    the frozen-dataclass shape (equality, hashability, serialization) is
    preserved. The :attr:`grantees` property returns a frozenset snapshot
    suitable for read-only consumption (the snapshot itself cannot be
    mutated to inject grantees back into the source).

    **Trust boundary.** The cascade reference IS the trust authority. Any
    caller holding a reference to this ``TenantScopedCascade`` is, by
    construction, the operator who constructed it (or an heir of that
    operator's authorization). Operators MUST scope cascade references
    behind their own authorization gate — see README §"What the primitive
    does NOT promise" → `issue #1147 <https://github.com/terrene-foundation/kailash-py/issues/1147>`_
    for the durable-registry roadmap. The internal set is exposed under
    Python's name-mangled attribute (``_TenantScopedCascade__grantees``)
    rather than a single-underscore convention; the mangled form means
    direct attribute access like ``cascade._grantees`` raises
    ``AttributeError`` rather than silently leaking the mutable set.
    Determined adversaries holding a cascade reference can still spell
    the mangled form, but the spelling is loud and intentional — the
    cascade reference is itself the authorization, so this matches the
    documented trust boundary.

    Note: this dataclass uses ``frozen=True`` but NOT ``slots=True`` (the
    sibling S2/S3 dataclasses use both). ``slots=True`` reserves only the
    declared fields, blocking ``object.__setattr__`` of the internal
    grantee slot in ``__post_init__``. Dropping ``slots=True`` preserves
    the frozen-equality contract (the wire-format contract is unchanged —
    the grantee registry is internal state, not serialized) while
    permitting the internal mutable set the H1 closure requires.
    """

    tenant: TenantScope
    # #1035 C1 closure: cascade emits GrantMoments signed with grant_proof;
    # the verifier cryptographically validates that proof against the
    # parent's public key. Default NullVerifier (fail-closed) — a cascade
    # built without an explicit verifier rejects EVERY cascade_child call
    # at the C1 gate. compare=False keeps frozen-equality / hashability
    # contract unchanged (verifier is wiring, not identity).
    verifier: Verifier = field(default_factory=NullVerifier, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.tenant, TenantScope):
            raise TypeError(
                "TenantScopedCascade.tenant MUST be a TenantScope; got "
                f"{type(self.tenant).__name__}"
            )
        if not isinstance(self.verifier, Verifier):
            raise TypeError(
                "TenantScopedCascade.verifier MUST satisfy the Verifier "
                f"protocol; got {type(self.verifier).__name__}"
            )
        # #1146 H1 — internal mutable grantee registry. Frozen dataclass
        # bypass via object.__setattr__ keeps the registry isolated from
        # the frozen-shape contract (equality / hashability / wire format
        # do not include the registry). The set is populated by
        # register_root_grantee + cascade_child; external readers see a
        # frozenset snapshot via the grantees property.
        object.__setattr__(self, "_TenantScopedCascade__grantees", set())

    @property
    def grantees(self) -> frozenset[uuid.UUID]:
        """Borrow the current grantee registry as a read-only frozenset.

        #1146 H1 — the snapshot is frozen, so external code holding a
        reference cannot mutate the registry. Each property access returns
        a fresh frozenset reflecting the current registry state at call
        time; subsequent :meth:`cascade_child` calls do NOT mutate prior
        snapshots.

        :class:`DispatchSurface.__init__` consumes this property to check
        ``identity.delegate_id in cascade.grantees`` and raises
        :class:`DispatchCascadeViolationError` on mismatch (the H1 gate).
        """
        # The slot is set in __post_init__; bypass __getattr__ via
        # __getattribute__ on the slot name for symmetry with __setattr__.
        return frozenset(
            object.__getattribute__(self, "_TenantScopedCascade__grantees")
        )

    def register_root_grantee(
        self,
        identity: DelegateIdentity,
        *,
        grant_proof: str | None = None,
    ) -> None:
        """Seed the registry with the root sovereign / origin identity.

        #1146 H1 + #1035 C1 closure (H2): the cascade's grantee registry
        is empty at construction; an identity that anchors the cascade
        MUST be explicitly registered before it can construct a
        :class:`DispatchSurface` against this cascade.

        Optional cryptographic gate. When a real
        :class:`~kailash.delegate.verifier.Ed25519Verifier` is wired
        AND ``grant_proof`` is supplied, the proof is verified against
        the canonical root-grant signing bytes (the identity's
        ``delegate_id`` + the cascade's tenant). When ``grant_proof``
        is omitted AND the wired verifier is the fail-closed
        :class:`~kailash.delegate.verifier.NullVerifier`, the
        registration proceeds without crypto — this is the
        transitional path for cascades constructed before C1 (no
        verifier wired). When ``grant_proof`` is omitted AND a real
        verifier is wired, the registration is REFUSED with
        :class:`CascadeSignatureError` — a wired verifier signals the
        caller has committed to cryptographic gating and an unsigned
        root-seed is the H2 attack surface this gate closes.

        Idempotent — calling with the same identity twice is a no-op.
        The optional grant_proof is verified on EACH call (so a
        verified root-seed retries are safe; an unsigned retry on a
        verified-cascade still refuses).

        **Trust boundary.** With a real verifier wired, the cascade is
        cryptographically gated; with NullVerifier (default), the
        cascade reference remains the trust authority and the operator
        scopes references behind their own authorization layer per
        ``README``.

        Args:
            identity: The :class:`DelegateIdentity` whose ``delegate_id``
                anchors the cascade. Typed at the boundary so the registry
                cannot accept stray strings / UUIDs.
            grant_proof: Optional 128-char hex Ed25519 signature over
                the canonical root-grant bytes. Required when a real
                verifier is wired; refused (when None) on such
                cascades. Verified against the canonical
                ``{"delegate_id": ..., "tenant": ...}`` signing bytes.

        Raises:
            TypeError: if ``identity`` is not a :class:`DelegateIdentity`.
            CascadeSignatureError: a real verifier is wired AND
                ``grant_proof`` is None, OR ``grant_proof`` fails
                cryptographic verification.
        """
        if not isinstance(identity, DelegateIdentity):
            raise TypeError(
                "TenantScopedCascade.register_root_grantee identity MUST "
                f"be a DelegateIdentity; got {type(identity).__name__}"
            )
        # C1 closure (H2): a real verifier signals the caller has
        # committed to cryptographic gating; an unsigned root-seed on
        # such a cascade is the H2 attack surface. NullVerifier is the
        # transitional default; allow unsigned seeding ONLY when the
        # verifier itself is the fail-closed default.
        is_real_verifier = not isinstance(self.verifier, NullVerifier)
        if is_real_verifier or grant_proof is not None:
            if grant_proof is None:
                raise CascadeSignatureError(
                    parent_delegate_id=identity.delegate_id,
                    verifier_class=type(self.verifier).__name__,
                )
            grant_canonical = canonical_json_dumps(
                {
                    "delegate_id": str(identity.delegate_id),
                    "tenant": self.tenant.tenant_id,
                }
            ).encode("utf-8")
            try:
                grant_proof_bytes = bytes.fromhex(grant_proof)
            except (ValueError, TypeError) as exc:
                raise CascadeSignatureError(
                    parent_delegate_id=identity.delegate_id,
                    verifier_class=type(self.verifier).__name__,
                ) from exc
            if not self.verifier.verify(
                grant_canonical,
                grant_proof_bytes,
                str(identity.delegate_id),
            ):
                raise CascadeSignatureError(
                    parent_delegate_id=identity.delegate_id,
                    verifier_class=type(self.verifier).__name__,
                )
        object.__getattribute__(self, "_TenantScopedCascade__grantees").add(
            identity.delegate_id
        )

    def cascade_child(
        self,
        parent_envelope: DelegateConstraintEnvelope,
        child_envelope: DelegateConstraintEnvelope,
        *,
        parent_identity: DelegateIdentity,
        child_identity: DelegateIdentity,
        parent_scope: RoleScope,
        child_scope: RoleScope,
        child_tenant: TenantScope,
        grant_proof: str,
        granted_at: datetime | None = None,
    ) -> GrantMoment:
        """Validate one downward cascade edge and emit a :class:`GrantMoment`.

        Steps 1-3 are fail-closed in the fixed order described in the class
        docstring. On success (all three steps pass) step 4 emits the
        chain-of-custody record.

        Args:
            parent_envelope: The parent's :class:`DelegateConstraintEnvelope`.
                Carries the F5 envelope-tightening contract.
            child_envelope: The child's raw
                :class:`kailash.trust.envelope.ConstraintEnvelope` wrapped in
                a :class:`DelegateConstraintEnvelope` (the wrapper carries
                the genesis_id contract). The child's envelope MUST be at-
                least-as-tight as the parent on every dimension.
            parent_identity: Identity of the granting authority (used in the
                emitted :class:`GrantMoment.parent_delegate_id`).
            child_identity: Identity of the receiving delegate (used in the
                emitted :class:`GrantMoment.child_delegate_id`).
            parent_scope: Parent's :class:`RoleScope` (domain + capabilities).
            child_scope: Child's :class:`RoleScope`; MUST be subset of parent.
            child_tenant: The child's tenant scope. MUST equal
                ``self.tenant`` (Option A RATIFIED).
            grant_proof: Hex-encoded Ed25519 signature (128 lowercase hex
                chars). Validated at the GrantMoment level.
            granted_at: tz-aware UTC datetime; defaults to now() if None.

        Returns:
            A :class:`GrantMoment` recording WHO granted (parent) to WHOM
            (child), under WHAT tenant, at WHEN, with the supplied
            grant_proof signature.

        Raises:
            CascadeTenantViolationError: cross-tenant cascade attempt.
            CascadeScopeExpansionError: child scope expands parent.
            EnvelopeWideningError: child envelope widens parent on any dim.
            TypeError: any argument fails its isinstance check.
        """
        # Type discipline at the boundary — defense-in-depth on top of
        # the dataclass post_init in each composed type.
        if not isinstance(parent_envelope, DelegateConstraintEnvelope):
            raise TypeError(
                "cascade_child.parent_envelope MUST be a "
                f"DelegateConstraintEnvelope; got {type(parent_envelope).__name__}"
            )
        if not isinstance(child_envelope, DelegateConstraintEnvelope):
            raise TypeError(
                "cascade_child.child_envelope MUST be a "
                f"DelegateConstraintEnvelope; got {type(child_envelope).__name__}"
            )
        if not isinstance(parent_identity, DelegateIdentity):
            raise TypeError(
                "cascade_child.parent_identity MUST be a DelegateIdentity; "
                f"got {type(parent_identity).__name__}"
            )
        if not isinstance(child_identity, DelegateIdentity):
            raise TypeError(
                "cascade_child.child_identity MUST be a DelegateIdentity; "
                f"got {type(child_identity).__name__}"
            )
        if not isinstance(parent_scope, RoleScope):
            raise TypeError(
                "cascade_child.parent_scope MUST be a RoleScope; got "
                f"{type(parent_scope).__name__}"
            )
        if not isinstance(child_scope, RoleScope):
            raise TypeError(
                "cascade_child.child_scope MUST be a RoleScope; got "
                f"{type(child_scope).__name__}"
            )
        if not isinstance(child_tenant, TenantScope):
            raise TypeError(
                "cascade_child.child_tenant MUST be a TenantScope; got "
                f"{type(child_tenant).__name__}"
            )

        # Step 1 (Option A RATIFIED): tenant-first isolation, fail-closed
        # BEFORE any scope/envelope work. The structural equality here
        # implements the rs `child_tenant != &self.tenant` check.
        if child_tenant != self.tenant:
            raise CascadeTenantViolationError(
                parent_tenant=self.tenant.tenant_id,
                child_tenant=child_tenant.tenant_id,
            )

        # Step 2 (F1 downward-only): scope subset. Domain MUST equal; child
        # capabilities MUST be a subset of parent's.
        if parent_scope.domain != child_scope.domain:
            raise CascadeScopeExpansionError(
                parent_domain=parent_scope.domain,
                child_domain=child_scope.domain,
            )
        added = _capability_diff(parent_scope.capabilities, child_scope.capabilities)
        if added:
            raise CascadeScopeExpansionError(
                parent_domain=parent_scope.domain,
                child_domain=child_scope.domain,
                added_capabilities=added,
            )

        # Step 3 (F5): envelope tightening — delegated to the existing
        # wrapper that already carries the pre-intersection widening check
        # per S2.5 F1. Propagates EnvelopeWideningError verbatim.
        #
        # B3 (analyst H-1): the tightened envelope is now carried on the
        # emitted GrantMoment instead of being discarded. Downstream
        # consumers (S5/S6 runtime spine) MUST observe the post-tightening
        # envelope as part of the chain-of-custody — recomputing it at
        # every consumer doubled the tighten_with cost AND risked one site
        # computing differently than another (silent drift). Carrying it
        # on the GrantMoment keeps the cascade as the single source of
        # truth for the F5 tightening result.
        tightened = parent_envelope.tighten_with(child_envelope.inner)

        # Step 3.5 (#1035 C1 closure): cryptographically verify
        # ``grant_proof`` against the canonical grant-signing bytes
        # using the wired Verifier. Prior shape-only hex check let any
        # 128-char hex string fall through (fake-encryption pattern per
        # zero-tolerance.md Rule 2). The verifier consults the
        # PrincipalDirectory the cascade's verifier was constructed
        # with; a NullVerifier-defaulted cascade rejects every call.
        # Fires BEFORE Step 4 registration so a failed verify does NOT
        # pollute the grantee registry.
        #
        # The canonical signing payload mirrors the GrantMoment.
        # to_signing_dict() shape — same bytes the parent signed when
        # issuing the grant. The cascade_id field is omitted because it
        # is allocated below (post-verify); the grant is over the
        # parent/child/tenant/granted_at/tightened tuple, which is the
        # auditable chain-of-custody anchor.
        granted_at_resolved = (
            granted_at if granted_at is not None else datetime.now(timezone.utc)
        )
        grant_canonical = canonical_json_dumps(
            {
                "parent_delegate_id": str(parent_identity.delegate_id),
                "child_delegate_id": str(child_identity.delegate_id),
                "tenant": self.tenant.tenant_id,
                "granted_at": granted_at_resolved.isoformat(),
            }
        ).encode("utf-8")
        try:
            grant_proof_bytes = bytes.fromhex(grant_proof)
        except (ValueError, TypeError) as exc:
            raise CascadeSignatureError(
                parent_delegate_id=parent_identity.delegate_id,
                verifier_class=type(self.verifier).__name__,
            ) from exc
        if not self.verifier.verify(
            grant_canonical,
            grant_proof_bytes,
            str(parent_identity.delegate_id),
        ):
            raise CascadeSignatureError(
                parent_delegate_id=parent_identity.delegate_id,
                verifier_class=type(self.verifier).__name__,
            )

        # Step 4 (#1146 H1): register BOTH parent and child as authorized
        # grantees of this cascade. Registration happens AFTER all three
        # validation gates pass — a cross-tenant or widening-scope or
        # widening-envelope attempt does NOT pollute the registry. The
        # parent is auto-registered idempotently to support multi-edge
        # cascades that descend from the same root (the root sovereign is
        # seeded once via register_root_grantee; subsequent grandchildren
        # observe the parent already in the set).
        #
        # Trust-boundary note: cascade_child does NOT require parent_identity
        # to be pre-registered as a grantee — the cascade reference itself
        # is the trust authority (see class docstring + register_root_grantee).
        # Post-C1 the grant_proof IS verified cryptographically (Step 3.5
        # above), so cascade_child is no longer "shape-only" — but the
        # cascade reference still controls the trust authority for seeding
        # (a caller holding the cascade can call register_root_grantee
        # directly without a grant_proof). Durable signed attestation
        # roadmap tracked at #1147.
        _grantees = object.__getattribute__(self, "_TenantScopedCascade__grantees")
        _grantees.add(parent_identity.delegate_id)
        _grantees.add(child_identity.delegate_id)

        # Step 5: emit the chain-of-custody GrantMoment. Reuse the
        # ``granted_at_resolved`` from Step 3.5 so the GrantMoment's
        # timestamp is BYTE-IDENTICAL to the value the verifier checked
        # the grant_proof against — any divergence here would let a
        # caller signed-and-stored two GrantMoments with timestamps the
        # verifier never inspected.
        return GrantMoment(
            cascade_id=uuid.uuid4(),
            parent_delegate_id=parent_identity.delegate_id,
            child_delegate_id=child_identity.delegate_id,
            tenant=self.tenant,
            granted_at=granted_at_resolved,
            grant_proof=grant_proof,
            tightened_envelope=tightened,
        )


def _capability_diff(parent: CapabilitySet, child: CapabilitySet) -> tuple[str, ...]:
    """Return capabilities present in ``child`` but missing from ``parent``.

    Order-stable: returns tokens in the order they appear in ``child``.
    Empty result means ``child`` is a subset of ``parent``.
    """
    parent_set = set(parent.capabilities)
    return tuple(c for c in child.capabilities if c not in parent_set)


# ---------------------------------------------------------------------------
# GrantMoment — chain-of-custody record (M3-02)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GrantMoment:
    """A signed Grant Moment recording one cascade edge.

    Mirrors rs ``GrantMoment`` (``grant.rs:186-198``). Frozen, tz-aware,
    Ed25519-hex-validated. The canonical chain-of-custody record on
    success of :meth:`TenantScopedCascade.cascade_child` — records WHO
    granted (parent), WHOM (child), under WHAT tenant, WHEN, with what
    signature proof.

    Cross-SDK byte-canonical fixtures emitted by py or rs are verified
    via :func:`kailash.trust._json.canonical_json_dumps` on the dicts
    returned by :meth:`to_canonical_dict` / :meth:`to_signing_dict`.

    Args:
        cascade_id: Unique per-cascade identifier (``uuid.UUID``).
        parent_delegate_id: Granting authority's :attr:`DelegateIdentity.delegate_id`.
        child_delegate_id: Receiving delegate's :attr:`DelegateIdentity.delegate_id`.
        tenant: The :class:`TenantScope` this cascade edge is bound to
            (same on parent + child by Option A — Step 1 enforces this).
        granted_at: Timezone-aware UTC datetime. Naive datetimes rejected
            (cross-SDK wire-format parity per S2.5 F6).
        grant_proof: Hex-encoded Ed25519 signature, exactly 128 lowercase
            hex chars. Validated via the substrate
            :func:`kailash.delegate.types._validate_hex` helper.
        tightened_envelope: B3 (analyst H-1) — the post-cascade tightened
            envelope produced by Step 3 (F5). Defaults to ``None`` when the
            GrantMoment is constructed outside the cascade pipeline (e.g.
            replayed from a wire-format payload that pre-dates the field).
            S5/S6 runtime spine consumers observe the post-tightening
            envelope from this attribute rather than re-calling
            ``tighten_with`` at every site.

    CROSS-SDK note (B7): py ``GrantMoment`` is a flat record; rs
    ``GrantMoment::issue`` walks a ``DelegationChain`` substrate that py
    does not yet expose. The py contract is structurally reduced — chain
    composition lands in a separate workstream tracked against issue
    #1035.
    """

    cascade_id: uuid.UUID
    parent_delegate_id: uuid.UUID
    child_delegate_id: uuid.UUID
    tenant: TenantScope
    granted_at: datetime
    grant_proof: str
    tightened_envelope: DelegateConstraintEnvelope | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.cascade_id, uuid.UUID):
            raise TypeError(
                "GrantMoment.cascade_id MUST be a uuid.UUID; got "
                f"{type(self.cascade_id).__name__}"
            )
        if not isinstance(self.parent_delegate_id, uuid.UUID):
            raise TypeError(
                "GrantMoment.parent_delegate_id MUST be a uuid.UUID; got "
                f"{type(self.parent_delegate_id).__name__}"
            )
        if not isinstance(self.child_delegate_id, uuid.UUID):
            raise TypeError(
                "GrantMoment.child_delegate_id MUST be a uuid.UUID; got "
                f"{type(self.child_delegate_id).__name__}"
            )
        if not isinstance(self.tenant, TenantScope):
            raise TypeError(
                "GrantMoment.tenant MUST be a TenantScope; got "
                f"{type(self.tenant).__name__}"
            )
        if not isinstance(self.granted_at, datetime):
            raise TypeError(
                "GrantMoment.granted_at MUST be a datetime; got "
                f"{type(self.granted_at).__name__}"
            )
        if self.granted_at.tzinfo is None:
            raise ValueError(
                "GrantMoment.granted_at MUST be timezone-aware (naive "
                "datetimes break cross-SDK wire-format parity per S2.5 F6)"
            )
        # Ed25519 signature shape — 128 lowercase hex chars.
        _validate_hex(
            self.grant_proof,
            expected_len=128,
            field_name="GrantMoment.grant_proof (Ed25519)",
        )
        if self.tightened_envelope is not None and not isinstance(
            self.tightened_envelope, DelegateConstraintEnvelope
        ):
            raise TypeError(
                "GrantMoment.tightened_envelope MUST be a "
                "DelegateConstraintEnvelope or None; got "
                f"{type(self.tightened_envelope).__name__}"
            )

    def to_signing_dict(self) -> dict[str, Any]:
        """Return the pre-signature canonical dict (F7 — sign/verify split).

        EXCLUDES :attr:`grant_proof`. Used by the signer/verifier to compute
        or verify the signature over a deterministic byte payload. The
        signature is computed over THIS dict's canonical-JSON encoding;
        :meth:`to_canonical_dict` adds the signature for transport.

        Mirrors the S2.5 :meth:`DelegateGenesisRecord.to_signing_dict`
        shape; same convention for cross-SDK consumers.

        B5 (sec M-3) — cross-SDK byte-canonical contract: callers MUST route
        the returned dict through
        :func:`kailash.trust._json.canonical_json_dumps` for signing.
        Direct ``json.dumps()`` (without ``sort_keys=True`` +
        ``separators=(",", ":")``) breaks cross-SDK parity per
        ``cross-sdk-inspection.md`` Rule 4 (helpers claiming byte-shape
        parity with the sibling SDK MUST pin byte vectors). See
        :meth:`to_signing_bytes` for a one-call convenience that returns
        the canonical bytes directly.
        """
        payload: dict[str, Any] = {
            "cascade_id": str(self.cascade_id),
            "parent_delegate_id": str(self.parent_delegate_id),
            "child_delegate_id": str(self.child_delegate_id),
            "tenant": self.tenant.to_dict(),
            "granted_at": self.granted_at.isoformat(),
        }
        # B3 (analyst H-1): include the tightened envelope when present so
        # cross-SDK byte-canonical fixtures reflect the post-cascade
        # envelope state. None → omit the key entirely, preserving the
        # pre-B3 wire format for GrantMoment instances constructed outside
        # the cascade pipeline (e.g. replay paths that pre-date the field).
        if self.tightened_envelope is not None:
            payload["tightened_envelope"] = self.tightened_envelope.to_dict()
        return payload

    def to_canonical_dict(self) -> dict[str, Any]:
        """Return the canonical-JSON-ready dict for cross-SDK byte parity.

        Includes :attr:`grant_proof` (the Ed25519 signature). Routes through
        :func:`kailash.trust._json.canonical_json_dumps` at the call site;
        field NAMES and value TYPES MUST match the rs side exactly. Pairs
        with :meth:`to_signing_dict` (F7 sign/verify split).
        """
        payload = self.to_signing_dict()
        payload["grant_proof"] = self.grant_proof
        return payload

    def to_signing_bytes(self) -> bytes:
        """Return the canonical-JSON bytes ready for Ed25519 signing.

        B5 (sec M-3) — convenience wrapper around
        :meth:`to_signing_dict` + :func:`kailash.trust._json.canonical_json_dumps`.
        Returning bytes directly closes the cross-SDK divergence trap where
        a caller might use ``json.dumps()`` without canonical settings and
        produce non-canonical bytes that break rs↔py verification.
        """
        # Lazy import to avoid a hot-path circular through trust._json if it
        # ever grows a delegate dep; trust._json is otherwise foundational.
        from kailash.trust._json import canonical_json_dumps

        return canonical_json_dumps(self.to_signing_dict()).encode("utf-8")


# Note: B2 (sec H-3) — the prior module-level _tenant_to_dict /
# _tenant_from_dict helpers were promoted to TenantScope.to_dict (instance
# method) and TenantScope.from_dict (classmethod) above. The private helpers
# were internal-only (no external callers), so promotion is API-additive.
