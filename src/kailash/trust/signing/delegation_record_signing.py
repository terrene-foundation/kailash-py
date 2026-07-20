# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Version-gated delegation signing/verify bridge for ``DelegationRecord``.

This module is the version-discriminated boundary between a
:class:`kailash.trust.chain.DelegationRecord` and the two pre-image families a
delegation signature can be produced over:

* the pre-migration **legacy** Python schema (``legacy-python-v0``), emitted by
  ``DelegationRecord.to_signing_payload()`` and encoded with the trust-plane
  signing encoder ``serialize_for_signing`` (issue #959); and
* the cross-SDK **engine** pre-images (``v2-complete`` / ``v3-complete``) built
  by :func:`kailash.trust.signing.delegation_payload.delegation_signing_payload`,
  which mirror the kailash-rs byte contract (EATP §5.3).

Two surfaces, one dispatch (#1841 shard 2):

1. :func:`delegation_canonical_payload_str` is the SINGLE shared entry point that
   EVERY delegation sign/verify call site routes through. It returns the legacy
   canonical string for a ``legacy-python-v0`` record (byte-identical to the
   pre-migration behaviour), and FAILS CLOSED
   (:class:`~kailash.trust.exceptions.UnsupportedSigningPayloadVersionError`) for
   any other version — because the engine (v2/v3) pre-image requires structured
   constraint / resource-limit / scope / multi-sig data a ``DelegationRecord``
   does not yet persist, so a non-legacy record MUST NOT fall through to the
   legacy verifier (which would sign/verify the WRONG pre-image). Wiring the
   record-persisted v2/v3 path is a later shard (S2b).

2. :func:`build_delegation_signing_input` / :func:`delegation_record_signing_payload`
   are the ADDITIVE engine bridge: they MAP a ``DelegationRecord``'s carried
   fields onto the engine's :class:`DelegationSigningInput` and emit the byte-exact
   v2/v3 engine pre-image. They are exercised directly (with the caller supplying
   the structured constraints / resource_limits / scope the record lacks) and are
   the mapping S2b will call from the sign/verify path once the structured fields
   are persisted on the record. They fail closed on missing structured data and
   on a scoped record whose ``dimension_scope`` binding is not yet cross-SDK-pinned
   (see :func:`build_delegation_signing_input`), never emitting guessed bytes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from kailash.trust.exceptions import UnsupportedSigningPayloadVersionError
from kailash.trust.signing.crypto import serialize_for_signing
from kailash.trust.signing.delegation_payload import (
    ConstraintDimensions,
    DelegationScope,
    DelegationSigningInput,
    MultiSigSigningPolicy,
    ResourceLimits,
    SigningPayloadVersion,
    delegation_signing_payload,
)

if TYPE_CHECKING:
    from kailash.trust.chain import DelegationRecord

__all__ = [
    "delegation_canonical_payload_str",
    "build_delegation_signing_input",
    "delegation_record_signing_payload",
]


def delegation_canonical_payload_str(record: "DelegationRecord") -> str:
    """Return the canonical signing string a delegation record is signed/verified over.

    The SINGLE shared dispatch every delegation sign/verify call site routes
    through, so the version gate has ONE source of truth (``rules/security.md``
    § Multi-Site Kwarg Plumbing).

    Args:
        record: The delegation record whose canonical pre-image is requested.

    Returns:
        The ``serialize_for_signing`` string of the legacy
        ``to_signing_payload()`` pre-image (for a ``legacy-python-v0`` record).

    Raises:
        UnsupportedSigningPayloadVersionError: If the record declares any version
            other than ``legacy-python-v0``. The engine-backed v2/v3 pre-images
            require record-persisted structured data this build does not yet
            carry (#1841 shard 2b); falling through to the legacy verifier would
            sign/verify the WRONG pre-image, so this fails closed.
    """
    # Import lazily to avoid a chain <-> signing import cycle: chain.py imports
    # kailash.trust.signing.crypto at module load, which initialises the signing
    # package; a top-level `from kailash.trust.chain import ...` here would run
    # before chain's module-level constants are defined.
    from kailash.trust.chain import DELEGATION_SIGNING_VERSION_LEGACY

    version = getattr(
        record, "signing_payload_version", DELEGATION_SIGNING_VERSION_LEGACY
    )
    if version == DELEGATION_SIGNING_VERSION_LEGACY:
        return serialize_for_signing(record.to_signing_payload())

    raise UnsupportedSigningPayloadVersionError(
        version, record_id=getattr(record, "id", None)
    )


def build_delegation_signing_input(
    record: "DelegationRecord",
    *,
    constraints: ConstraintDimensions,
    resource_limits: ResourceLimits,
    scope: DelegationScope,
    multi_sig: bool = False,
    multi_sig_policy: Optional[MultiSigSigningPolicy] = None,
) -> DelegationSigningInput:
    """Map a ``DelegationRecord`` onto the engine's ``DelegationSigningInput``.

    ``DelegationRecord`` carries the identity / capability / timestamp fields the
    engine base needs, but NOT the structured constraint / resource-limit / scope
    (and multi-sig policy) the v2/v3 fold requires — those are supplied by the
    caller. This is the mapping table (record field -> engine field):

    ======================  ===============================
    DelegationRecord         DelegationSigningInput
    ======================  ===============================
    ``id``                   ``delegation_id``
    ``delegator_id``         ``delegator``
    ``delegatee_id``         ``delegate``
    ``capabilities_delegated`` ``capabilities`` (order preserved)
    ``delegated_at``         ``created_at``
    ``expires_at``           ``expires_at``
    ``parent_delegation_id`` ``parent_delegation_id``
    ``reasoning_trace_hash`` ``reasoning_trace_hash``
    (caller-supplied)        ``constraints`` / ``resource_limits`` / ``scope``
    (caller-supplied)        ``multi_sig`` / ``multi_sig_policy``
    ======================  ===============================

    Fail-closed guards (matching the engine's own posture — never emit guessed
    bytes):

    * ``constraints`` / ``resource_limits`` / ``scope`` are REQUIRED (the engine
      folds them into every v2/v3 pre-image); a ``None`` raises rather than
      fabricating a default.
    * A record whose ``dimension_scope`` is narrower than the full CARE set is
      REFUSED for the engine pre-image: the Python ``dimension_scope`` is a
      security-relevant scoping the legacy ``to_signing_payload`` binds, but its
      fold into the cross-SDK v2/v3 pre-image is not yet pinned (rs#1795), and
      the engine byte-verifies only ``dimension_scope=None``. Signing such a
      record under v2/v3 without binding its scope would silently drop a
      widening-attack defence, so it fails closed here.

    Args:
        record: The delegation record to map.
        constraints: The structured constraint dimensions to fold (required).
        resource_limits: The structured resource-limit ceilings to fold (required).
        scope: The delegation scope to fold (required).
        multi_sig: Whether the record is multi-sig (v3).
        multi_sig_policy: The M-of-N policy to fold (required when ``multi_sig``).

    Returns:
        A :class:`DelegationSigningInput` ready for
        :func:`delegation_signing_payload`.

    Raises:
        ValueError: If a required structured field is missing, or the record
            carries a narrowed ``dimension_scope`` whose v2/v3 binding is not
            cross-SDK-pinned.
    """
    from kailash.trust.chain import ALL_DIMENSIONS

    if constraints is None:
        raise ValueError(
            "build_delegation_signing_input: 'constraints' is required for the "
            "engine (v2/v3) pre-image; DelegationRecord does not persist "
            "structured ConstraintDimensions, so the caller MUST supply it "
            "(fail-closed — no guessed defaults)"
        )
    if resource_limits is None:
        raise ValueError(
            "build_delegation_signing_input: 'resource_limits' is required for "
            "the engine (v2/v3) pre-image; DelegationRecord does not persist "
            "structured ResourceLimits, so the caller MUST supply it "
            "(fail-closed — no guessed defaults)"
        )
    if scope is None:
        raise ValueError(
            "build_delegation_signing_input: 'scope' is required for the engine "
            "(v2/v3) pre-image; DelegationRecord does not persist a structured "
            "DelegationScope, so the caller MUST supply it (fail-closed — no "
            "guessed defaults)"
        )

    # A narrowed dimension_scope is a security-relevant scoping the legacy
    # pre-image binds; its cross-SDK v2/v3 fold is un-pinned (rs#1795) and the
    # engine byte-verifies only dimension_scope=None. Refuse rather than sign a
    # scoped record whose scope the engine pre-image would silently drop.
    record_scope = getattr(record, "dimension_scope", ALL_DIMENSIONS)
    if frozenset(record_scope) != frozenset(ALL_DIMENSIONS):
        raise ValueError(
            "build_delegation_signing_input: record.dimension_scope is narrowed "
            f"({sorted(record_scope)}); its fold into the cross-SDK v2/v3 "
            "pre-image is not yet pinned (rs#1795), and the engine byte-verifies "
            "only the unscoped (all-dimensions) form. Signing a scoped record "
            "under v2/v3 would drop its scope binding (a widening-attack defence) "
            "— fail closed until a scoped vector is pinned in lockstep"
        )

    return DelegationSigningInput(
        delegation_id=record.id,
        delegator=record.delegator_id,
        delegate=record.delegatee_id,
        capabilities=tuple(record.capabilities_delegated),
        created_at=record.delegated_at,
        constraints=constraints,
        resource_limits=resource_limits,
        scope=scope,
        expires_at=record.expires_at,
        parent_delegation_id=record.parent_delegation_id,
        multi_sig=multi_sig,
        multi_sig_policy=multi_sig_policy,
        reasoning_trace_hash=record.reasoning_trace_hash,
    )


def delegation_record_signing_payload(
    record: "DelegationRecord",
    version: SigningPayloadVersion,
    *,
    constraints: ConstraintDimensions,
    resource_limits: ResourceLimits,
    scope: DelegationScope,
    multi_sig: bool = False,
    multi_sig_policy: Optional[MultiSigSigningPolicy] = None,
) -> bytes:
    """Build the byte-exact engine (v2/v3) signing pre-image for a delegation record.

    Maps the record via :func:`build_delegation_signing_input`, then delegates to
    the cross-SDK engine :func:`delegation_signing_payload` for the byte contract.
    The engine enforces its own fail-closed posture (non-ASCII content, sub-second
    timestamps, ``V2_COMPLETE`` + ``multi_sig=True``, ``V3_COMPLETE`` without a
    policy, populated ``dimension_scope``); this function adds the
    DelegationRecord-side guards (missing structured data, narrowed scope).

    Args:
        record: The delegation record.
        version: ``SigningPayloadVersion.V2_COMPLETE`` or ``.V3_COMPLETE``.
        constraints: Structured constraint dimensions to fold (required).
        resource_limits: Structured resource-limit ceilings to fold (required).
        scope: Delegation scope to fold (required).
        multi_sig: Whether the record is multi-sig (v3).
        multi_sig_policy: The M-of-N policy to fold (required when ``multi_sig``).

    Returns:
        The canonical JCS engine pre-image as UTF-8 bytes.

    Raises:
        ValueError: On any DelegationRecord-side or engine fail-closed guard.
    """
    signing_input = build_delegation_signing_input(
        record,
        constraints=constraints,
        resource_limits=resource_limits,
        scope=scope,
        multi_sig=multi_sig,
        multi_sig_policy=multi_sig_policy,
    )
    return delegation_signing_payload(signing_input, version)
