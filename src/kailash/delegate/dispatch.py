# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
# pyright: reportUnnecessaryIsInstance=false
"""Connector ABC + Dispatch surface for ``kailash.delegate`` (S5 of #1035).

Binds the existing Delegate primitives into the audit-grade composition
``(Connector × Signature × ConstraintEnvelope × Executor)``. This is the
surface a Delegate invocation actually flows through — the Connector is
the external endpoint (HTTP, MCP tool, Kaizen Signature, custom adapter),
the Signature defines the input/output contract, the ConstraintEnvelope
carries the F5 monotonic-tightening invariant, and the
:class:`DispatchSurface` is the bind-time composition that enforces every
invariant at runtime.

Invariants held by :class:`DispatchSurface` (within budget per
``autonomous-execution.md`` MUST Rule 1 — five invariants total):

1. **F5 type-state monotonic envelope** — the envelope passed at
   construction is final; runtime composition is tightening-only via
   :meth:`DelegateConstraintEnvelope.tighten_with` (which inherits the
   S2.5 F1 widening-raise gate). The DispatchSurface MUST NOT loosen
   the envelope between bind and invocation.
2. **Tenant isolation** — the connector's observed tenant_id MUST equal
   the cascade's bound tenant; mismatch raises
   :class:`CascadeTenantViolationError` (re-using the
   :mod:`kailash.delegate.trust` exception so cross-layer audits surface
   one error class per tenant-boundary violation).
3. **Capability gating** — the connector's declared
   ``requires_capabilities`` frozenset MUST be a subset of the bound
   role's :class:`CapabilitySet`. Checked at construction; raises
   :class:`DispatchEnvelopeViolationError` on mismatch.
4. **Audit emission only on audit-visible events** — :meth:`dispatch`
   forwards every event in :attr:`ConnectorInvocationResult.audit_events`
   to :meth:`AuditChainEngine.emit_event`; the engine's
   ``_AUDIT_VISIBLE_EVENT_TYPES`` frozenset rejects any non-visible
   variant. DispatchSurface does NOT re-implement the allowlist — it
   lets :class:`AuditChainEmissionError` propagate (per C3
   founder-ratified audit-visibility classifier).
5. **Lifecycle state** — the bound :class:`Role` MUST be in an
   invocable lifecycle. ``RoleLifecycleState.RETIRED`` and ``SUSPENDED``
   refuse dispatch with :class:`DispatchEnvelopeViolationError`. Only
   ``DRAFT`` and ``ACTIVE`` are invocable (DRAFT is permitted so test
   harnesses can dispatch against pre-activation roles; runtime
   deployments enforce ACTIVE-only via the surrounding deployment
   policy).

The Connector ABC itself is a pure abstract surface — subclasses
provide the actual external endpoint behavior. The ABC enforces
``async def invoke(...)`` as a coroutine, class-level
``connector_id`` + ``connector_kind`` + ``requires_capabilities``
metadata for the bind-time capability check, and refuses direct
instantiation via :class:`abc.ABC`.
"""

from __future__ import annotations

import abc
import hashlib
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from kailash.delegate.audit import AuditChainEngine, DelegateEventType
from kailash.delegate.envelope import DelegateConstraintEnvelope
from kailash.delegate.trust import (
    CascadeTenantViolationError,
    TenantScope,
    TenantScopedCascade,
)
from kailash.delegate.types import DelegateIdentity, Role, RoleLifecycleState
from kailash.trust._json import canonical_json_dumps

logger = logging.getLogger(__name__)

__all__ = [
    "Connector",
    "ConnectorInvocationResult",
    "DispatchCascadeViolationError",
    "DispatchEnvelopeViolationError",
    "DispatchResult",
    "DispatchSignerError",
    "DispatchSurface",
    "DispatchValidationError",
    "SignatureContract",
]

# ---------------------------------------------------------------------------
# Payload-shape limits — Round-1 C6-1 DoS defense
# ---------------------------------------------------------------------------
# Deeply nested payloads trigger O(depth) recursion in canonical_json_dumps
# and per-field type checks; oversize payloads block the dispatch hot path
# while signing the audit envelope. Both limits are conservative defaults
# (well above any legitimate signature payload) and refuse loudly via
# DispatchValidationError so the caller learns at the boundary, not inside
# the canonical-JSON encoder.
_MAX_PAYLOAD_DEPTH = 32
_MAX_PAYLOAD_SERIALIZED_BYTES = 1 * 1024 * 1024  # 1 MiB


def _check_payload_depth(obj: Any, current_depth: int = 0) -> None:
    """Recursive depth check used at dispatch entry (C6-1)."""
    if current_depth > _MAX_PAYLOAD_DEPTH:
        raise DispatchValidationError(
            f"input_payload exceeds maximum nesting depth "
            f"({_MAX_PAYLOAD_DEPTH}); refused to prevent DoS through "
            "recursive canonical-JSON encoding"
        )
    if isinstance(obj, dict):
        for v in obj.values():
            _check_payload_depth(v, current_depth + 1)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _check_payload_depth(v, current_depth + 1)


# ---------------------------------------------------------------------------
# Typed errors — distinct ValueError-derived classes per invariant axis
# ---------------------------------------------------------------------------


class DispatchValidationError(ValueError):
    """Raised when ``input_payload`` violates the bound signature contract.

    Surfaces type or shape mismatches between the actual ``input_payload``
    and the bound :class:`SignatureContract.input_schema`. Distinct from
    :class:`DispatchEnvelopeViolationError` (capability / tenant / lifecycle
    gating, Invariants 3 + 5) and :class:`DispatchCascadeViolationError`
    (trust cascade refuses the principal, Invariant 2).

    ``ValueError``-derived per the S2.5 / S3 / S4 pattern — a signature
    contract violation is a caller fault, not a system fault.
    """


class DispatchSignerError(ValueError):
    """Raised when the injected audit-signer fails or returns a malformed signature.

    The :class:`DispatchSurface` requires a real signer at construction
    (C2-1 zero-tolerance fix — placeholder ``"0" * 128`` is BLOCKED). When
    the signer raises, the exception is re-wrapped with this typed surface
    so callers distinguish signer faults from validation faults
    (:class:`DispatchValidationError`) and envelope faults
    (:class:`DispatchEnvelopeViolationError`).

    Also raised when the signer's return value fails the surface-shape
    check (non-string, too-short hex, non-hex characters). The audit
    engine's own :func:`_validate_hex` is the canonical signature
    validator (128-char lowercase hex for Ed25519); this class surfaces
    the malformed-output failure BEFORE the audit-engine boundary so the
    error attribution is unambiguous (signer fault vs. engine fault).
    """


class DispatchEnvelopeViolationError(ValueError):
    """Raised when the envelope refuses the invocation at bind or dispatch.

    Three sub-classes of violation surface here:

    - **Capability missing** (Invariant 3): the connector's declared
      ``requires_capabilities`` is not a subset of the bound role's
      :class:`CapabilitySet`. Checked at construction so a misconfigured
      DispatchSurface cannot even be built.
    - **Tenant out of envelope scope**: the envelope's bound tenant is
      not the cascade's tenant (cross-validation at construction). This
      is a sibling of the runtime tenant-isolation check that uses
      :class:`CascadeTenantViolationError` for the OBSERVED tenant;
      this error covers the static binding-time mismatch.
    - **Lifecycle state refuses dispatch** (Invariant 5): the bound
      :class:`Role` is in :attr:`RoleLifecycleState.RETIRED` or
      :attr:`RoleLifecycleState.SUSPENDED`. RETIRED is the closest
      semantic to the spec's "REVOKED" (the existing
      :mod:`kailash.delegate.types` enum does not declare REVOKED;
      RETIRED is the canonical "no further bindings" state per
      ``types.py`` :class:`RoleLifecycleState` docstring).
    """


class DispatchCascadeViolationError(ValueError):
    """Raised when the trust cascade refuses the invocation.

    Surfaces when the bound :class:`DelegateIdentity` is not a known
    grantee of the bound :class:`TenantScopedCascade`. Distinct from
    :class:`CascadeTenantViolationError` (Invariant 2 runtime tenant
    mismatch) — this error is the BIND-time check that the principal
    was actually granted by the cascade.

    Note: the current :class:`TenantScopedCascade` does NOT yet expose
    a persistent grantee registry (S3 emits one
    :class:`~kailash.delegate.trust.GrantMoment` per ``cascade_child``
    call but does not retain the grantee set). The construction-time
    check here is structural — the identity's ``delegate_id`` is held
    on the DispatchSurface and the cascade's tenant is cross-checked.
    A future enhancement (S7+) will surface a grantee registry; this
    error class is the stable typed surface that registry will plumb
    into.
    """


# ---------------------------------------------------------------------------
# SignatureContract — minimal Protocol the kailash.delegate package
# does not yet expose a structured Signature primitive (Kaizen has one,
# but Delegate is independent per Foundation Independence rules). We
# declare a minimal Protocol so the dispatch surface has a typed binding
# point. When a structured Delegate Signature primitive lands (S6+),
# this Protocol becomes its conformance gate.
# ---------------------------------------------------------------------------


@runtime_checkable
class SignatureContract(Protocol):
    """Minimal contract a Signature MUST satisfy to bind to DispatchSurface.

    A signature names the connector's input/output schema. The schemas are
    dict-shaped — keys are field names, values are the declared type (e.g.
    ``{"user_id": str, "limit": int}``). DispatchSurface validates
    ``input_payload`` against ``input_schema`` at dispatch time (Invariant
    1, signature contract).

    Per ``foundation-independence.md`` the Delegate spine does NOT couple
    to Kaizen's Signature primitive; this Protocol is the structural
    contract. A future structured Delegate Signature class (S6+) will
    satisfy this Protocol; in the interim, any object exposing the three
    attributes binds.

    Attributes:
        name: Identifier for the signature (e.g. ``"create_user"``).
            Used in audit-event payloads + error messages.
        input_schema: Mapping of input field name → declared type. The
            ``DispatchSurface`` validates ``input_payload.keys()`` ⊆
            ``input_schema.keys()`` and each value is instance-of the
            declared type. Extra payload keys are rejected (closed-world
            schema — per ``zero-tolerance.md`` Rule 3c, silently
            dropping undocumented kwargs is BLOCKED; the equivalent here
            is rejecting undeclared input fields rather than silently
            forwarding them).
        output_schema: Mapping of output field name → declared type. The
            DispatchSurface does NOT enforce output_schema (the
            connector owns its return shape); the field is held for
            audit / observability + downstream consumers that re-derive
            type-checks at the Signature layer.
    """

    name: str
    input_schema: dict[str, type]
    output_schema: dict[str, type]


# ---------------------------------------------------------------------------
# Connector ABC — pure abstract external-surface contract
# ---------------------------------------------------------------------------


class Connector(abc.ABC):
    """Abstract external endpoint a Delegate invocation connects through.

    Cross-impl parity: Mirrors rs ``DelegateConnector`` trait (S5
    substrate). The :meth:`invoke` method signature is the byte-shape
    contract for cross-SDK ``receipts_agree(rs, py)`` verification at
    S7+ — both SDKs MUST produce byte-identical
    :class:`ConnectorInvocationResult` payloads for identical input
    under identical envelopes (per ``cross-sdk-inspection.md`` MUST-3
    EATP D6 semantic-match).

    Subclasses provide the actual external behavior — HTTP request, MCP
    tool call, Kaizen Signature invocation, queue publish, etc. The ABC
    defines exactly the surface :class:`DispatchSurface` needs:

    - Class-level ``connector_id``, ``connector_kind``,
      ``requires_capabilities`` metadata for bind-time gating.
    - Async :meth:`invoke` returning a
      :class:`ConnectorInvocationResult` carrying payload + audit events
      + tenant observation + side-effect flag.

    The ABC refuses direct instantiation via :class:`abc.ABC` + the
    abstract :meth:`invoke`. Per ``orphan-detection.md`` MUST Rule 1,
    this base class lives in the framework hot path:
    :meth:`DispatchSurface.dispatch` calls ``await connector.invoke(...)``
    directly — there is no facade orphan layer.

    Subclass example::

        class HttpConnector(Connector):
            connector_id = "http-create-user"
            connector_kind = "http"
            requires_capabilities = frozenset({"http.write"})

            async def invoke(
                self,
                input_payload,
                *,
                identity,
                envelope,
            ):
                ...  # actual HTTP call
                return ConnectorInvocationResult(
                    payload={"user_id": "u-42"},
                    audit_events=(DelegateEventType.EXTERNAL_SIDE_EFFECT,),
                    tenant_id_observed=envelope.genesis_id,  # or actual tenant
                    external_side_effect=True,
                )
    """

    # Class-level metadata. Subclasses MUST override these — the bind
    # check at DispatchSurface construction reads them. Defaults are
    # intentionally empty / placeholder so a subclass that forgets to
    # set them fails the bind check loudly rather than silently
    # accepting the parent default.
    connector_id: str = ""
    connector_kind: str = ""
    requires_capabilities: frozenset[str] = frozenset()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Defense-in-depth: every concrete subclass MUST declare a
        # non-empty connector_id at the class level so audit events
        # carry a meaningful identifier. Empty string at the subclass
        # level is BLOCKED (the ABC's empty default cannot satisfy this
        # check).
        #
        # __init_subclass__ runs BEFORE ABCMeta computes
        # __abstractmethods__ on the new class; use getattr with a
        # default to handle both ordering paths. The subclass is
        # "concrete" iff it overrode the abstract invoke method (so the
        # abstract set, when populated, will be empty).
        abstract_methods = getattr(cls, "__abstractmethods__", frozenset())
        # Detect concrete subclasses: they MUST have overridden invoke
        # such that it's no longer the ABC's abstract method.
        invoke = cls.__dict__.get("invoke")
        is_concrete = invoke is not None and not getattr(
            invoke, "__isabstractmethod__", False
        )
        # Also concrete if abstract_methods is populated and empty
        # (post-ABCMeta computation path).
        if not is_concrete and abstract_methods == frozenset():
            # Check whether invoke was inherited as abstract.
            inherited_invoke = getattr(cls, "invoke", None)
            if inherited_invoke is not None and not getattr(
                inherited_invoke, "__isabstractmethod__", False
            ):
                is_concrete = True
        if is_concrete:
            # Concrete subclass — enforce metadata declaration. Abstract
            # intermediate base classes may legitimately defer metadata
            # to their own concrete subclasses.
            if not isinstance(cls.connector_id, str) or not cls.connector_id:
                raise TypeError(
                    f"Connector subclass {cls.__name__!r} MUST declare a "
                    f"non-empty class-level connector_id; got "
                    f"{cls.connector_id!r}"
                )
            if not isinstance(cls.connector_kind, str) or not cls.connector_kind:
                raise TypeError(
                    f"Connector subclass {cls.__name__!r} MUST declare a "
                    f"non-empty class-level connector_kind; got "
                    f"{cls.connector_kind!r}"
                )
            if not isinstance(cls.requires_capabilities, frozenset):
                raise TypeError(
                    f"Connector subclass {cls.__name__!r} MUST declare "
                    f"requires_capabilities as a frozenset; got "
                    f"{type(cls.requires_capabilities).__name__}"
                )

    @abc.abstractmethod
    async def invoke(
        self,
        input_payload: dict[str, Any],
        *,
        identity: DelegateIdentity,
        envelope: DelegateConstraintEnvelope,
    ) -> ConnectorInvocationResult:
        """Invoke the external endpoint.

        Subclasses MUST implement this as a coroutine returning a
        :class:`ConnectorInvocationResult`. The DispatchSurface awaits
        this directly; raising propagates to the caller (the DispatchSurface
        does NOT swallow connector exceptions — per ``zero-tolerance.md``
        Rule 3, silent error hiding is BLOCKED).

        Args:
            input_payload: The validated input payload (DispatchSurface
                has already checked it against the bound
                :attr:`SignatureContract.input_schema`).
            identity: The bound :class:`DelegateIdentity`. Connectors may
                use ``identity.delegate_id`` for audit correlation or
                authn/authz checks against their own external surface.
            envelope: The bound :class:`DelegateConstraintEnvelope`.
                Connectors may inspect envelope constraints (budget
                limits, model selection, etc.) to shape their request.

        Returns:
            A :class:`ConnectorInvocationResult` carrying the connector's
            payload, the audit events the connector emitted, the
            tenant_id the connector observed (for cross-validation), and
            the external-side-effect flag.
        """
        raise NotImplementedError  # pragma: no cover (abstract)


# ---------------------------------------------------------------------------
# ConnectorInvocationResult — frozen dataclass returned by Connector.invoke
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConnectorInvocationResult:
    """The result of a single :meth:`Connector.invoke` call.

    Cross-impl parity: Mirrors rs ``ConnectorInvocationResult`` struct.
    The :meth:`to_dict` / :meth:`from_dict` round-trip is the wire-format
    contract for cross-SDK receipt comparison — emits a JSON-serializable
    dict whose keys match the rs serde representation byte-for-byte
    (audit-event variants emitted as their string values per
    :class:`DelegateEventType`).

    Frozen + slots per the S2/S3/S4 dataclass conventions. The
    DispatchSurface inspects every field of this result for the
    cross-validation invariants:

    - ``audit_events`` flows into :meth:`AuditChainEngine.emit_event`
      (Invariant 4 — audit-visible events only).
    - ``tenant_id_observed`` cross-validates against the envelope's
      tenant (Invariant 2 — tenant isolation).
    - ``external_side_effect`` is a structural marker the DispatchSurface
      surfaces in the returned :class:`DispatchResult`; it does NOT
      itself gate audit emission (the connector's ``audit_events`` is
      the explicit declaration of what to emit).

    Attributes:
        payload: The connector's return value (dict-shaped). The
            DispatchSurface returns this verbatim on
            :attr:`DispatchResult.payload`.
        audit_events: Tuple of :class:`DelegateEventType` variants the
            connector emitted during invocation. The DispatchSurface
            forwards each to :meth:`AuditChainEngine.emit_event`;
            non-audit-visible variants (e.g. ``REASONING_SCRATCHPAD``)
            raise :class:`AuditChainEmissionError` from the engine's
            own gate (the DispatchSurface does NOT re-check the
            allowlist — single source of truth per
            ``zero-tolerance.md`` Rule 4).
        tenant_id_observed: The tenant the connector actually touched.
            ``None`` is permitted ONLY when the envelope's bound
            cascade is :class:`TenantScope.global_` (the explicit
            unscoped variant); a non-None observed tenant on a
            for_tenant-bound cascade with a mismatched id raises
            :class:`CascadeTenantViolationError`.
        external_side_effect: ``True`` iff the invocation produced an
            externally-observable mutation (HTTP write, queue publish,
            etc.). The DispatchSurface uses this flag for observability
            but does NOT auto-emit an audit event — the connector
            declares its events explicitly via ``audit_events``.
    """

    payload: dict[str, Any]
    audit_events: tuple[DelegateEventType, ...]
    tenant_id_observed: str | None
    external_side_effect: bool

    def __post_init__(self) -> None:
        if not isinstance(self.payload, dict):
            raise TypeError(
                "ConnectorInvocationResult.payload MUST be a dict; got "
                f"{type(self.payload).__name__}"
            )
        if not isinstance(self.audit_events, tuple):
            raise TypeError(
                "ConnectorInvocationResult.audit_events MUST be a tuple; got "
                f"{type(self.audit_events).__name__}"
            )
        for ev in self.audit_events:
            if not isinstance(ev, DelegateEventType):
                raise TypeError(
                    "ConnectorInvocationResult.audit_events entries MUST be "
                    f"DelegateEventType variants; got {type(ev).__name__}"
                )
        if self.tenant_id_observed is not None and not isinstance(
            self.tenant_id_observed, str
        ):
            raise TypeError(
                "ConnectorInvocationResult.tenant_id_observed MUST be str "
                f"or None; got {type(self.tenant_id_observed).__name__}"
            )
        if not isinstance(self.external_side_effect, bool):
            raise TypeError(
                "ConnectorInvocationResult.external_side_effect MUST be bool; "
                f"got {type(self.external_side_effect).__name__}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-canonical dict (cross-SDK wire-format).

        Cross-impl parity: the returned dict is the byte-shape contract
        with the rs ``ConnectorInvocationResult`` serde encoding.
        ``audit_events`` is emitted as a list of string sentinels (each
        :class:`DelegateEventType` ``.value``) so the encoding is
        portable across languages without depending on Python's enum
        repr.
        """
        return {
            "payload": dict(self.payload),
            "audit_events": [e.value for e in self.audit_events],
            "tenant_id_observed": self.tenant_id_observed,
            "external_side_effect": self.external_side_effect,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConnectorInvocationResult":
        """Reconstruct from a :meth:`to_dict` payload.

        Round-trip lossless: ``ConnectorInvocationResult.from_dict(r.to_dict())``
        reconstructs an equal instance. Validates the
        ``audit_events`` list-of-strings against the
        :class:`DelegateEventType` enum at reconstruction time; unknown
        variants raise ``ValueError`` from the enum constructor.
        """
        if not isinstance(data, dict):
            raise TypeError(
                "ConnectorInvocationResult.from_dict requires a dict; got "
                f"{type(data).__name__}"
            )
        for required in ("payload", "audit_events", "external_side_effect"):
            if required not in data:
                raise ValueError(
                    "ConnectorInvocationResult.from_dict missing required "
                    f"field {required!r}"
                )
        events_raw = data["audit_events"]
        if not isinstance(events_raw, (list, tuple)):
            raise TypeError(
                "ConnectorInvocationResult.from_dict 'audit_events' MUST be a "
                f"list/tuple; got {type(events_raw).__name__}"
            )
        events = tuple(DelegateEventType(e) for e in events_raw)
        return cls(
            payload=dict(data["payload"]),
            audit_events=events,
            tenant_id_observed=data.get("tenant_id_observed"),
            external_side_effect=data["external_side_effect"],
        )


# ---------------------------------------------------------------------------
# DispatchResult — frozen dataclass returned by DispatchSurface.dispatch
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DispatchResult:
    """The chain-of-custody record of one dispatch invocation.

    Cross-impl parity: Mirrors rs ``DispatchResult`` struct. The
    :meth:`to_dict` / :meth:`from_dict` round-trip is the wire-format
    contract for cross-SDK receipt comparison — ``executed_at`` is
    emitted as ISO-8601 UTC, ``dispatch_id`` as a UUID string, the
    audit-chain-entry hashes as a list of hex strings.

    Frozen + slots per conventions. Returned by
    :meth:`DispatchSurface.dispatch` on success — failure paths raise
    typed errors before this is constructed.

    Attributes:
        payload: The connector's return value (verbatim from
            :attr:`ConnectorInvocationResult.payload`).
        audit_chain_entries: Tuple of entry hashes (SHA-256 hex) from
            :meth:`AuditChainEngine.head_hash` after each event emission.
            Empty tuple when the connector emitted no audit events. The
            chain-of-custody invariant: dispatching a single
            :class:`DispatchSurface.dispatch` call produces a contiguous
            run of audit chain entries — consumers can replay the chain
            from these hashes to verify the dispatch's audit trail.
        executed_at: tz-aware UTC datetime of dispatch completion.
        tenant_id: The validated tenant (cascade tenant, or empty string
            for the explicit ``TenantScope.global_`` variant). Carries
            the post-validation tenant for traceability.
        connector_id: The bound connector's ``connector_id`` for
            traceability against the connector subclass.
        dispatch_id: Unique :class:`uuid.UUID` identifying this
            dispatch invocation. Generated at construction by
            :meth:`DispatchSurface.dispatch`; flows through cross-SDK
            receipt correlation as the lookup key.
    """

    payload: dict[str, Any]
    audit_chain_entries: tuple[str, ...]
    executed_at: datetime
    tenant_id: str
    connector_id: str
    dispatch_id: uuid.UUID

    def __post_init__(self) -> None:
        if not isinstance(self.payload, dict):
            raise TypeError(
                "DispatchResult.payload MUST be a dict; got "
                f"{type(self.payload).__name__}"
            )
        if not isinstance(self.audit_chain_entries, tuple):
            raise TypeError(
                "DispatchResult.audit_chain_entries MUST be a tuple; got "
                f"{type(self.audit_chain_entries).__name__}"
            )
        for h in self.audit_chain_entries:
            if not isinstance(h, str):
                raise TypeError(
                    "DispatchResult.audit_chain_entries entries MUST be str; "
                    f"got {type(h).__name__}"
                )
        if not isinstance(self.executed_at, datetime):
            raise TypeError(
                "DispatchResult.executed_at MUST be a datetime; got "
                f"{type(self.executed_at).__name__}"
            )
        if self.executed_at.tzinfo is None:
            raise ValueError(
                "DispatchResult.executed_at MUST be timezone-aware (naive "
                "datetimes break cross-SDK wire-format parity)"
            )
        if not isinstance(self.tenant_id, str):
            raise TypeError(
                f"DispatchResult.tenant_id MUST be a str; got "
                f"{type(self.tenant_id).__name__}"
            )
        if not isinstance(self.connector_id, str) or not self.connector_id:
            raise ValueError(
                "DispatchResult.connector_id MUST be a non-empty str; got "
                f"{self.connector_id!r}"
            )
        if not isinstance(self.dispatch_id, uuid.UUID):
            raise TypeError(
                "DispatchResult.dispatch_id MUST be a uuid.UUID; got "
                f"{type(self.dispatch_id).__name__}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-canonical dict (cross-SDK wire-format).

        Cross-impl parity: the returned dict is the byte-shape contract
        with the rs ``DispatchResult`` serde encoding. ``executed_at``
        is ISO-8601 UTC; ``dispatch_id`` is the canonical UUID string;
        ``audit_chain_entries`` is a list (not tuple) for JSON
        compatibility.
        """
        return {
            "payload": dict(self.payload),
            "audit_chain_entries": list(self.audit_chain_entries),
            "executed_at": self.executed_at.isoformat(),
            "tenant_id": self.tenant_id,
            "connector_id": self.connector_id,
            "dispatch_id": str(self.dispatch_id),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DispatchResult":
        """Reconstruct from a :meth:`to_dict` payload.

        Round-trip lossless on all fields. ``executed_at`` is parsed
        via :meth:`datetime.fromisoformat` (Python 3.11+ accepts the
        full ISO-8601 surface); ``dispatch_id`` is parsed via
        :class:`uuid.UUID`; ``audit_chain_entries`` is re-tupled.
        """
        if not isinstance(data, dict):
            raise TypeError(
                "DispatchResult.from_dict requires a dict; got "
                f"{type(data).__name__}"
            )
        for required in (
            "payload",
            "audit_chain_entries",
            "executed_at",
            "tenant_id",
            "connector_id",
            "dispatch_id",
        ):
            if required not in data:
                raise ValueError(
                    "DispatchResult.from_dict missing required field " f"{required!r}"
                )
        executed_at_raw = data["executed_at"]
        if not isinstance(executed_at_raw, str):
            raise TypeError(
                "DispatchResult.from_dict 'executed_at' MUST be an ISO-8601 "
                f"str; got {type(executed_at_raw).__name__}"
            )
        executed_at = datetime.fromisoformat(executed_at_raw)
        return cls(
            payload=dict(data["payload"]),
            audit_chain_entries=tuple(data["audit_chain_entries"]),
            executed_at=executed_at,
            tenant_id=data["tenant_id"],
            connector_id=data["connector_id"],
            dispatch_id=uuid.UUID(data["dispatch_id"]),
        )


# ---------------------------------------------------------------------------
# DispatchSurface — the (Connector × Signature × Envelope × Identity) bind
# ---------------------------------------------------------------------------


# RoleLifecycleStates that MAY invoke dispatch. DRAFT is permitted so
# test harnesses can dispatch against pre-activation roles; runtime
# deployments enforce ACTIVE-only via the surrounding deployment policy.
# SUSPENDED and RETIRED refuse — SUSPENDED holds existing bindings but
# permits no new operations; RETIRED is the spec's "REVOKED" semantic
# (no further bindings ever).
_INVOCABLE_ROLE_LIFECYCLES: frozenset[RoleLifecycleState] = frozenset(
    {RoleLifecycleState.DRAFT, RoleLifecycleState.ACTIVE}
)


class DispatchSurface:
    """Bind ``(Connector × Signature × Envelope × Identity)`` for dispatch.

    Cross-impl parity: Mirrors rs ``DispatchSurface`` struct (S5
    substrate). The bind-time gating contract (capability + lifecycle
    snapshot at __init__; tenant cross-check at dispatch) is the
    byte-shape contract for cross-SDK ``receipts_agree(rs, py)``
    verification — both SDKs MUST refuse the same set of
    (connector, signature, envelope, identity, role, cascade) tuples
    by raising the same typed error class.

    F5 Monotonicity Invariant
    -------------------------
    Capabilities AND lifecycle are snapshotted at bind. Runtime
    tightening (capability revocation, lifecycle downgrade) is detected
    at :meth:`dispatch` entry and FAILS CLOSED with
    :class:`DispatchEnvelopeViolationError`. Runtime widening
    (capability gain, lifecycle promotion) is IGNORED — the bind-time
    set is the upper bound. The Role is held by reference, so mutations
    on the underlying Role object after construction are reflected in
    runtime checks; this guarantees a revoked capability or
    state-transition to RETIRED/SUSPENDED between bind and dispatch
    refuses the invocation rather than admitting it under the snapshot
    of bind time.

    Construction is the bind-time gate; :meth:`dispatch` is the runtime
    invocation. The five invariants (top-of-module docstring) are split:

    - Invariant 1 (F5 monotonic envelope) — held by the envelope itself
      via :meth:`DelegateConstraintEnvelope.tighten_with`; DispatchSurface
      holds the envelope by reference (frozen dataclass) so it cannot be
      mutated post-bind.
    - Invariant 3 (capability gating) — checked at construction.
    - Invariant 5 (lifecycle state) — checked at construction.
    - Invariant 2 (tenant isolation) — cross-checked at dispatch against
      the connector's observed tenant.
    - Invariant 4 (audit emission) — forwarded to
      :class:`AuditChainEngine` whose own ``_AUDIT_VISIBLE_EVENT_TYPES``
      frozenset is the single source of truth.

    Per ``facade-manager-detection.md`` MUST Rule 3, the
    :class:`AuditChainEngine` and :class:`TenantScopedCascade` are
    explicit constructor dependencies — no global lookup, no
    self-construction. Per ``orphan-detection.md`` MUST Rule 1, the
    DispatchSurface IS the framework hot path that calls
    ``connector.invoke()`` — there is no further indirection.

    Args:
        connector: A concrete :class:`Connector` subclass instance.
        signature: An object satisfying :class:`SignatureContract`.
        envelope: The :class:`DelegateConstraintEnvelope` bound for this
            dispatch surface. Final at construction — runtime
            ``tighten_with`` calls produce a NEW envelope; the
            DispatchSurface's bound envelope does NOT change.
        identity: The :class:`DelegateIdentity` of the principal
            invoking this dispatch.
        audit_engine: The :class:`AuditChainEngine` events flow to.
            EAGER REQUIRED — DispatchSurface cannot be constructed
            without a real engine.
        trust_cascade: The :class:`TenantScopedCascade` whose tenant
            cross-validates against the connector's observed tenant.
            EAGER REQUIRED.
        role: The :class:`Role` bound for the capability + lifecycle
            check (Invariants 3 + 5). DelegateIdentity does NOT yet
            carry a Role attribute (the existing identity primitive
            holds a ``role_binding_ref`` string); the Role is passed
            explicitly so the bind-time check has the actual capability
            set. A future S6+ change may collapse this into
            ``identity.role`` if/when the identity primitive grows that
            attribute.
        signer: Callable producing the Ed25519 signature for each audit
            event. Signature: ``signer(canonical_bytes) -> hex_str``
            where ``canonical_bytes`` is the UTF-8 encoding of the
            canonical-JSON of the audit payload AND the return value
            is a 128-character lowercase-hex string (the audit-engine
            contract). EAGER REQUIRED — Round-1 C2-1 zero-tolerance fix:
            the prior ``"0" * 128`` placeholder is BLOCKED per
            ``zero-tolerance.md`` Rule 2 "fake encryption" pattern.
            Production deployments inject a real signer holding the
            DispatchSurface's signing key; tests inject a deterministic
            signer (e.g. ``lambda b: hashlib.sha256(b).hexdigest()``
            doubled to 128 chars). The signer is called exactly once
            per audit event emitted by the connector.

    Raises:
        DispatchEnvelopeViolationError: connector requires a capability
            the role does not grant, OR role is in a lifecycle that
            refuses dispatch (RETIRED, SUSPENDED).
        DispatchCascadeViolationError: the envelope's tenant binding is
            inconsistent with the cascade's tenant.
        TypeError: any argument fails its type check.
    """

    def __init__(
        self,
        connector: Connector,
        signature: SignatureContract,
        envelope: DelegateConstraintEnvelope,
        identity: DelegateIdentity,
        *,
        audit_engine: AuditChainEngine,
        trust_cascade: TenantScopedCascade,
        role: Role,
        signer: Callable[[bytes], str],
    ) -> None:
        # Type discipline at the boundary — defense-in-depth on top of
        # each composed type's own post_init.
        if not isinstance(connector, Connector):
            raise TypeError(
                "DispatchSurface.connector MUST be a Connector subclass "
                f"instance; got {type(connector).__name__}"
            )
        if not isinstance(envelope, DelegateConstraintEnvelope):
            raise TypeError(
                "DispatchSurface.envelope MUST be a DelegateConstraintEnvelope; "
                f"got {type(envelope).__name__}"
            )
        if not isinstance(identity, DelegateIdentity):
            raise TypeError(
                "DispatchSurface.identity MUST be a DelegateIdentity; got "
                f"{type(identity).__name__}"
            )
        if not isinstance(audit_engine, AuditChainEngine):
            raise TypeError(
                "DispatchSurface.audit_engine MUST be an AuditChainEngine; got "
                f"{type(audit_engine).__name__}"
            )
        if not isinstance(trust_cascade, TenantScopedCascade):
            raise TypeError(
                "DispatchSurface.trust_cascade MUST be a TenantScopedCascade; "
                f"got {type(trust_cascade).__name__}"
            )
        if not isinstance(role, Role):
            raise TypeError(
                f"DispatchSurface.role MUST be a Role; got {type(role).__name__}"
            )
        # C2-1 zero-tolerance fix: signer MUST be a real callable injected
        # at construction. Passing None / a non-callable raises TypeError
        # at bind time, preventing the prior ``"0" * 128`` placeholder
        # ("fake encryption" pattern per zero-tolerance.md Rule 2) from
        # ever reaching the dispatch hot path. The signer's runtime
        # return-value surface is validated at every emission in
        # :meth:`_signed_audit` so a malformed signer fails per-call,
        # not silently for the lifetime of the DispatchSurface.
        if not callable(signer):
            raise TypeError(
                "DispatchSurface.signer MUST be a callable producing "
                "Ed25519 hex signatures; got "
                f"{type(signer).__name__} (None / placeholder forms are "
                "BLOCKED per zero-tolerance.md Rule 2 fake-encryption "
                "fix C2-1)"
            )
        # SignatureContract is a Protocol; runtime_checkable lets isinstance
        # verify the structural shape. Per zero-tolerance Rule 3a (typed
        # delegate guards), surface a typed error instead of an opaque
        # AttributeError later.
        if not isinstance(signature, SignatureContract):
            raise TypeError(
                "DispatchSurface.signature MUST satisfy SignatureContract "
                "(name: str, input_schema: dict[str, type], "
                "output_schema: dict[str, type]); got "
                f"{type(signature).__name__}"
            )

        # Invariant 5 — lifecycle state. RETIRED + SUSPENDED refuse;
        # DRAFT + ACTIVE allow. Checked BEFORE capability so a retired
        # role surfaces the lifecycle failure rather than a downstream
        # capability mismatch.
        if role.lifecycle not in _INVOCABLE_ROLE_LIFECYCLES:
            raise DispatchEnvelopeViolationError(
                f"DispatchSurface refuses bind: role lifecycle "
                f"{role.lifecycle.value!r} is not invocable "
                f"(invocable={sorted(s.value for s in _INVOCABLE_ROLE_LIFECYCLES)}; "
                f"RETIRED/SUSPENDED roles cannot dispatch — Invariant 5)"
            )

        # #1143 §10 G1 — principal-kind discriminator gate. The bound
        # :class:`DelegateIdentity`'s ``principal_kind`` MUST be in the
        # role's :attr:`permitted_principal_kinds` frozenset. A
        # service-account identity binding to a sovereign-only role
        # collapses the Genesis-to-Delegation attribution chain — the
        # exact §10 G1 invariant.
        #
        # Checked AFTER lifecycle so a retired role surfaces the
        # lifecycle failure first (it's the more fundamental refusal).
        # Checked BEFORE capability so a principal-kind mismatch
        # surfaces before downstream capability hashes — the kind
        # mismatch is the load-bearing signal.
        #
        # Defense-in-depth: the same check re-fires at every
        # :meth:`dispatch` start per the F5 / R2 composition pattern,
        # in case the Role's ``permitted_principal_kinds`` is mutated
        # between bind and dispatch (mutation of a frozenset is
        # impossible, but the Role object itself could be swapped via
        # an external reference).
        if identity.principal_kind not in role.permitted_principal_kinds:
            logger.debug(
                "dispatch.envelope_violation",
                extra={
                    "axis": "principal_kind",
                    "connector_id": connector.connector_id,
                    "role_display_name": role.display_name,
                    "identity_principal_kind": identity.principal_kind,
                    "role_permitted_principal_kinds": sorted(
                        role.permitted_principal_kinds
                    ),
                },
            )
            raise DispatchEnvelopeViolationError(
                f"DispatchSurface refuses bind: identity principal_kind "
                f"{identity.principal_kind!r} not in role "
                f"{role.display_name!r} permitted_principal_kinds "
                f"{sorted(role.permitted_principal_kinds)!r} "
                "(#1143 §10 G1 — service-account vs sovereign separation)"
            )

        # Invariant 3 — capability gating. Connector's required
        # capabilities MUST be a subset of the role's capability set.
        # C5-2 error-leakage: hash capability names in the caller-facing
        # message so log-aggregator readers do not see the security
        # vocabulary; full detail is structured-logged at DEBUG for
        # operators investigating with full context.
        role_caps = frozenset(role.scope.capabilities.capabilities)
        missing = connector.requires_capabilities - role_caps
        if missing:
            missing_hash = hashlib.sha256(
                ",".join(sorted(missing)).encode("utf-8")
            ).hexdigest()[:8]
            logger.debug(
                "dispatch.envelope_violation",
                extra={
                    "axis": "missing_capability",
                    "connector_id": connector.connector_id,
                    "required_capabilities": sorted(connector.requires_capabilities),
                    "role_display_name": role.display_name,
                    "granted_capabilities": sorted(role_caps),
                    "missing": sorted(missing),
                },
            )
            raise DispatchEnvelopeViolationError(
                f"DispatchSurface refuses bind: connector "
                f"{connector.connector_id!r} requires {len(missing)} "
                f"capability/ies the role does not grant "
                f"[missing_hash={missing_hash}] (Invariant 3 — see DEBUG "
                "logs for detail)"
            )

        # Bind-time tenant consistency between cascade and identity. The
        # cascade is bound to a single tenant at construction; we hold
        # the cascade by reference and re-validate the OBSERVED tenant
        # at dispatch (Invariant 2 runtime check). The construction-time
        # check here is structural — both cascade and identity exist
        # and the cascade's tenant is captured.
        # Note: identity does not yet carry a tenant_id (the genesis_ref
        # string is the closest proxy); the cascade's tenant is the
        # authoritative bind-time anchor. The runtime cross-check in
        # dispatch() uses ConnectorInvocationResult.tenant_id_observed.

        self._connector = connector
        self._signature = signature
        self._envelope = envelope
        self._identity = identity
        self._audit_engine = audit_engine
        self._trust_cascade = trust_cascade
        self._role = role
        self._signer = signer

        # C4-1 F5 monotonicity snapshot: capture the bind-time
        # capability set and lifecycle so :meth:`dispatch` can refuse
        # invocations where the underlying Role drifted between bind
        # and dispatch (revocation / state transition). frozenset
        # captures by value; the lifecycle enum is immutable.
        self._required_caps: frozenset[str] = frozenset(connector.requires_capabilities)
        self._granted_caps_at_bind: frozenset[str] = frozenset(
            role.scope.capabilities.capabilities
        )
        self._lifecycle_at_bind: RoleLifecycleState = role.lifecycle
        # #1143 §10 G1 — principal-kind snapshots for the dispatch-time
        # re-check. ``identity.principal_kind`` is a Literal string
        # (immutable). ``role.permitted_principal_kinds`` is a frozenset
        # (immutable by construction). The pair forms the bind-time
        # contract the F5 re-check at dispatch defends.
        self._identity_principal_kind: str = identity.principal_kind
        self._permitted_principal_kinds_at_bind: frozenset[str] = frozenset(
            role.permitted_principal_kinds
        )

    @property
    def connector(self) -> Connector:
        """Borrow the bound :class:`Connector` (read-only)."""
        return self._connector

    @property
    def signature(self) -> SignatureContract:
        """Borrow the bound :class:`SignatureContract` (read-only)."""
        return self._signature

    @property
    def envelope(self) -> DelegateConstraintEnvelope:
        """Borrow the bound :class:`DelegateConstraintEnvelope` (read-only).

        The envelope is the F5 monotonic-tightening anchor — runtime
        ``tighten_with`` calls produce a NEW envelope; this attribute
        always returns the original bound envelope (the
        DispatchSurface's contract — Invariant 1).
        """
        return self._envelope

    @property
    def identity(self) -> DelegateIdentity:
        """Borrow the bound :class:`DelegateIdentity` (read-only)."""
        return self._identity

    @property
    def role(self) -> Role:
        """Borrow the bound :class:`Role` (read-only)."""
        return self._role

    @property
    def audit_engine(self) -> AuditChainEngine:
        """Borrow the bound :class:`AuditChainEngine` (read-only)."""
        return self._audit_engine

    @property
    def trust_cascade(self) -> TenantScopedCascade:
        """Borrow the bound :class:`TenantScopedCascade` (read-only)."""
        return self._trust_cascade

    async def dispatch(self, input_payload: dict[str, Any]) -> DispatchResult:
        """Validate, invoke, cross-check, emit audit, return result.

        Sequence (fail-closed at every step — typed error raises BEFORE
        the next step runs):

        1. Validate ``input_payload`` against
           :attr:`SignatureContract.input_schema` (Invariant 1 signature
           contract). Raises :class:`DispatchValidationError`.
        2. (Bind-time invariants 3 + 5 already checked at __init__.)
        3. Invoke ``await connector.invoke(input_payload, identity=...,
           envelope=...)``. Connector exceptions propagate verbatim per
           zero-tolerance Rule 3 (no silent error hiding).
        4. Cross-validate ``result.tenant_id_observed`` against the
           cascade's tenant (Invariant 2). Mismatch raises
           :class:`CascadeTenantViolationError` (re-using trust.py's
           exception so cross-layer audits surface one error class).
        5. Forward every ``result.audit_events`` entry to
           :meth:`AuditChainEngine.emit_event` (Invariant 4). The
           engine's audit-visible allowlist raises
           :class:`AuditChainEmissionError` for non-visible variants —
           DispatchSurface does NOT re-check (single source of truth).
        6. Construct + return :class:`DispatchResult`.

        Args:
            input_payload: The dict-shaped input. Keys MUST be a subset
                of the bound signature's ``input_schema`` keys; values
                MUST be instance-of the declared type. Extra keys are
                rejected (closed-world schema — per zero-tolerance Rule
                3c, silent kwargs drop is BLOCKED).

        Returns:
            A :class:`DispatchResult` carrying payload + audit chain
            entry hashes + executed_at + tenant_id + connector_id.

        Raises:
            DispatchValidationError: input_payload violates the signature.
            CascadeTenantViolationError: connector's observed tenant
                does not match the cascade's tenant.
            AuditChainEmissionError: an event in ``audit_events`` is not
                audit-visible (REASONING_SCRATCHPAD).
            Exception: connector-raised exceptions propagate verbatim.
        """
        # Step 0a — C4-1 F5 monotonicity re-check. The role is held by
        # reference; runtime tightening (capability revocation,
        # lifecycle transition to RETIRED/SUSPENDED) MUST refuse the
        # invocation rather than admit it under the bind-time snapshot.
        # Widening is IGNORED — the bind-time set remains the upper bound.
        current_caps = frozenset(self._role.scope.capabilities.capabilities)
        if not self._required_caps.issubset(current_caps):
            missing_now = self._required_caps - current_caps
            raise DispatchEnvelopeViolationError(
                f"DispatchSurface refuses dispatch: capability set drifted "
                f"after bind; {len(missing_now)} required capability/ies "
                "revoked between bind and dispatch (F5 monotonicity — "
                "Invariant 3 runtime re-check)"
            )
        current_lifecycle = self._role.lifecycle
        if current_lifecycle not in _INVOCABLE_ROLE_LIFECYCLES:
            raise DispatchEnvelopeViolationError(
                f"DispatchSurface refuses dispatch: role lifecycle drifted "
                f"from {self._lifecycle_at_bind.value!r} at bind to "
                f"{current_lifecycle.value!r}; invocation refused (F5 "
                "monotonicity — Invariant 5 runtime re-check)"
            )
        # Step 0a.1 — #1143 §10 G1 principal-kind re-check. Pair to the
        # bind-time gate in __init__. The identity's principal_kind MUST
        # still be in the role's permitted_principal_kinds at dispatch
        # time. Defense-in-depth: if a caller swapped the Role's
        # permitted set via direct attribute assignment (frozen=True
        # blocks normal mutation but ``object.__setattr__`` bypasses)
        # OR mutated the identity's principal_kind via the same
        # bypass, the dispatch-time check refuses.
        current_permitted = frozenset(self._role.permitted_principal_kinds)
        current_kind = self._identity.principal_kind
        if current_kind not in current_permitted:
            raise DispatchEnvelopeViolationError(
                f"DispatchSurface refuses dispatch: principal_kind "
                f"{current_kind!r} not in current role "
                f"permitted_principal_kinds {sorted(current_permitted)!r}; "
                "invocation refused (#1143 §10 G1 — principal-kind "
                "discriminator runtime re-check)"
            )

        # Step 0b — C6-1 DoS defense: depth + serialized-size limits
        # BEFORE per-field type checks. canonical_json_dumps recurses on
        # the payload during audit emission; deeply nested or oversize
        # payloads are refused at the boundary.
        if isinstance(input_payload, dict):
            _check_payload_depth(input_payload)
            try:
                serialized_size = len(
                    canonical_json_dumps(input_payload).encode("utf-8")
                )
            except (TypeError, ValueError) as exc:
                # Non-JSON-serializable payloads surface as DispatchValidationError
                # at the dispatch boundary so callers do not need to introspect
                # canonical_json_dumps exception types.
                raise DispatchValidationError(
                    f"input_payload is not JSON-serializable for cross-SDK "
                    f"canonical encoding: {exc}"
                ) from exc
            if serialized_size > _MAX_PAYLOAD_SERIALIZED_BYTES:
                raise DispatchValidationError(
                    f"input_payload exceeds maximum serialized size "
                    f"({_MAX_PAYLOAD_SERIALIZED_BYTES} bytes); got "
                    f"{serialized_size} bytes; refused to prevent DoS "
                    "through unbounded audit-payload encoding"
                )

        # Step 1 — input_payload validation against signature contract.
        # C5-1 error-leakage fix: every DispatchValidationError surface
        # carries a generic caller-facing message + correlation hash;
        # full schema-revealing detail is structured-logged at DEBUG so
        # log-aggregator readers (per observability.md MUST Rule 8) do
        # not see schema names while operators investigating with debug
        # logging retain full context.
        if not isinstance(input_payload, dict):
            logger.debug(
                "dispatch.validation_error",
                extra={
                    "axis": "payload_type",
                    "signature_name": self._signature.name,
                    "received_type": type(input_payload).__name__,
                },
            )
            raise DispatchValidationError(
                "input_payload type mismatch; expected dict (see DEBUG "
                "logs for detail)"
            )
        # Closed-world schema: every key in input_payload MUST appear in
        # the signature's input_schema. Extra keys are rejected to close
        # the silent-fallback failure mode where a typo'd kwarg silently
        # never reaches the connector.
        extra_keys = set(input_payload.keys()) - set(
            self._signature.input_schema.keys()
        )
        if extra_keys:
            extras_hash = self._field_hash(",".join(sorted(extra_keys)))
            logger.debug(
                "dispatch.validation_error",
                extra={
                    "axis": "undeclared_field",
                    "signature_name": self._signature.name,
                    "extra_keys": sorted(extra_keys),
                    "declared_keys": sorted(self._signature.input_schema.keys()),
                },
            )
            raise DispatchValidationError(
                f"input_payload has undeclared field(s) " f"[extras_hash={extras_hash}]"
            )
        for field_name, declared_type in self._signature.input_schema.items():
            if field_name not in input_payload:
                field_hash = self._field_hash(field_name)
                logger.debug(
                    "dispatch.validation_error",
                    extra={
                        "axis": "missing_field",
                        "signature_name": self._signature.name,
                        "field_name": field_name,
                    },
                )
                raise DispatchValidationError(
                    f"input_payload missing required field "
                    f"[field_hash={field_hash}]"
                )
            value = input_payload[field_name]
            # C6-2 strict type check: isinstance(True, int) is True in
            # Python — reject bool for int-declared fields explicitly so
            # the security.md sanitizer-contract Rule 2 (type-confusion
            # raises, not coerces) holds at the dispatch boundary.
            if declared_type is int and isinstance(value, bool):
                field_hash = self._field_hash(field_name)
                logger.debug(
                    "dispatch.validation_error",
                    extra={
                        "axis": "bool_for_int_field",
                        "signature_name": self._signature.name,
                        "field_name": field_name,
                        "received_type": "bool",
                    },
                )
                raise DispatchValidationError(
                    f"input_payload field [field_hash={field_hash}] "
                    f"declared int; bool BLOCKED (type coercion refused "
                    "per security.md sanitizer Rule 2)"
                )
            # Allow numeric tower: int satisfies float field.
            if (
                declared_type is float
                and isinstance(value, int)
                and not isinstance(value, bool)
            ):
                pass  # accept int as float
            elif not isinstance(value, declared_type):
                field_hash = self._field_hash(field_name)
                logger.debug(
                    "dispatch.validation_error",
                    extra={
                        "axis": "type_mismatch",
                        "signature_name": self._signature.name,
                        "field_name": field_name,
                        "declared_type": declared_type.__name__,
                        "received_type": type(value).__name__,
                    },
                )
                raise DispatchValidationError(
                    f"input_payload field [field_hash={field_hash}] "
                    f"failed schema validation (declared "
                    f"{declared_type.__name__})"
                )

        # Step 3 — invoke the connector. Connector exceptions propagate
        # verbatim; DispatchSurface MUST NOT swallow them per
        # zero-tolerance Rule 3.
        result = await self._connector.invoke(
            input_payload,
            identity=self._identity,
            envelope=self._envelope,
        )
        if not isinstance(result, ConnectorInvocationResult):
            raise DispatchValidationError(
                f"Connector {self._connector.connector_id!r} returned "
                f"{type(result).__name__!r}; MUST return a "
                "ConnectorInvocationResult instance"
            )

        # Step 3b — C2-3 side-effect-without-audit gate. zero-tolerance
        # Rule 2 fake-dispatch class: a connector reporting an external
        # mutation MUST emit at least one audit event documenting it.
        # Mutation without provenance is BLOCKED because the audit trail
        # is the only post-incident record of what actually changed.
        if result.external_side_effect and not result.audit_events:
            raise DispatchValidationError(
                f"connector {self._connector.connector_id!r} reported "
                "external_side_effect=True but emitted zero audit_events; "
                "side-effects without audit trail are BLOCKED "
                "(zero-tolerance.md Rule 2 fake-dispatch class)"
            )

        # Step 4 — cross-validate tenant isolation (Invariant 2).
        cascade_tenant = self._trust_cascade.tenant
        if cascade_tenant.is_global:
            # Global cascade accepts any observed tenant (including None).
            tenant_id_for_result = ""
        else:
            # for_tenant cascade — observed MUST match bound tenant.
            expected_tenant = cascade_tenant.tenant_id
            if result.tenant_id_observed != expected_tenant:
                raise CascadeTenantViolationError(
                    parent_tenant=expected_tenant,
                    child_tenant=result.tenant_id_observed,
                )
            tenant_id_for_result = expected_tenant or ""

        # Step 5 — emit audit events through the engine. The engine's
        # _AUDIT_VISIBLE_EVENT_TYPES frozenset rejects non-visible
        # variants; AuditChainEmissionError propagates verbatim per
        # zero-tolerance Rule 4 (no re-implementation of the allowlist
        # here — single source of truth in audit.py).
        emitted_entry_hashes: list[str] = []
        for event_type in result.audit_events:
            # Build the audit event payload. The structured payload
            # carries the dispatch context for downstream consumers
            # (connector_id, signature.name, external_side_effect).
            # Per observability.md MUST Rule 8 (schema-revealing field
            # names) we keep payload keys generic, not schema-revealing.
            payload: dict[str, Any] = {
                "connector_id": self._connector.connector_id,
                "connector_kind": self._connector.connector_kind,
                "signature_name": self._signature.name,
                "external_side_effect": result.external_side_effect,
            }
            # C2-1 zero-tolerance fix: call the injected signer with the
            # canonical-bytes encoding of the audit payload. A signer
            # fault re-raises as DispatchSignerError so the error
            # taxonomy distinguishes signer faults from
            # AuditChainEmissionError (signature surface-shape) and
            # DispatchValidationError (input-shape).
            canonical_bytes = canonical_json_dumps(payload).encode("utf-8")
            try:
                signature_hex = self._signer(canonical_bytes)
            except Exception as exc:
                raise DispatchSignerError(
                    f"injected signer raised while signing audit event "
                    f"{event_type.value!r}: {type(exc).__name__}: {exc}"
                ) from exc
            if not isinstance(signature_hex, str):
                raise DispatchSignerError(
                    f"injected signer MUST return str; got "
                    f"{type(signature_hex).__name__}"
                )
            # Surface-shape sanity check: the audit engine's
            # _validate_hex requires 128 lowercase-hex chars (Ed25519).
            # A signer that returns less than 32 chars is structurally
            # not a real signature; raise before the engine boundary so
            # the error attribution is unambiguous (signer fault vs.
            # engine fault).
            if len(signature_hex) < 32:
                raise DispatchSignerError(
                    f"injected signer returned a signature shorter than "
                    "32 characters; production signatures are 128-char "
                    f"lowercase hex (Ed25519); got {len(signature_hex)} chars"
                )
            entry = self._audit_engine.emit_event(
                event_type=event_type.value,
                payload=payload,
                signer_identity=self._identity,
                signature=signature_hex,
            )
            # Append the head_hash AFTER the emission so each entry's
            # hash captures the chain state at the moment of that
            # emission.
            head = self._audit_engine.head_hash()
            if head is not None:
                emitted_entry_hashes.append(head)
            else:  # pragma: no cover (defensive — engine always has a head after emit)
                # If head_hash is None despite a successful emit, the
                # engine has a contract regression; surface it loudly
                # rather than silently dropping the entry.
                raise RuntimeError(
                    f"AuditChainEngine.head_hash returned None after "
                    f"emit_event(sequence={entry.sequence}) — contract "
                    "regression in AuditChainEngine"
                )

        # Step 6 — construct + return DispatchResult.
        return DispatchResult(
            payload=result.payload,
            audit_chain_entries=tuple(emitted_entry_hashes),
            executed_at=datetime.now(timezone.utc),
            tenant_id=tenant_id_for_result,
            connector_id=self._connector.connector_id,
            dispatch_id=uuid.uuid4(),
        )

    @staticmethod
    def _field_hash(field_name: str) -> str:
        """C5-1 / C5-2 error-leakage helper.

        Returns the first 8 chars of SHA-256(field_name) as a stable,
        non-reversible correlation token. Used in
        :class:`DispatchValidationError` messages so the caller can
        cross-reference structured DEBUG logs without exposing schema
        field names through log-aggregator surfaces (per
        ``observability.md`` MUST Rule 8).
        """
        return hashlib.sha256(field_name.encode("utf-8")).hexdigest()[:8]
