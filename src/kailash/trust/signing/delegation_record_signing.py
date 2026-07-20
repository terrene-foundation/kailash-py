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
   pre-migration behaviour), the cross-SDK V2Complete engine pre-image for a
   ``v2-complete`` record (folding the record-persisted structured constraint /
   resource-limit / scope — #1841 S2b-1), and the cross-SDK V3Complete engine
   pre-image for a ``v3-complete`` (multi-sig) record (the V2Complete fold PLUS
   the record-persisted ``multi_sig_policy`` — #1841 S2b-2). It FAILS CLOSED
   (:class:`~kailash.trust.exceptions.UnsupportedSigningPayloadVersionError`) for
   any UNRECOGNISED version, and (via a ``ValueError`` from the engine bridge)
   for a v2/v3-labelled record missing the structured fold data — a non-legacy
   record MUST NOT fall through to the legacy verifier (which would sign/verify
   the WRONG pre-image).

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
    "select_signing_version",
    "build_delegation_signing_input",
    "delegation_record_signing_payload",
]


def select_signing_version(record: "DelegationRecord") -> str:
    """Select which canonical pre-image a delegation record signs (#1841 S2b-1/S2b-2).

    The structured engine-fold fields (``constraints`` / ``resource_limits`` /
    ``scope``) are ALL-OR-NOTHING: supply all three (→ v2, or v3 when multi-sig)
    or none (→ legacy).

    Returns:
        * ``legacy-python-v0`` (the DEFAULT) when NONE of the structured fields
          is supplied on a NON-multi-sig record, OR (all three supplied but) a
          non-multi-sig record carries a NARROWED ``dimension_scope`` (whose
          cross-SDK v2/v3 fold is not yet pinned — rs#1795).
        * ``v2-complete`` when ALL structured fields are present AND the record
          is NON-multi-sig AND ``dimension_scope`` is the full (unscoped) CARE
          set — so it signs the cross-SDK V2Complete engine pre-image.
        * ``v3-complete`` when the record is MULTI-SIG (``multi_sig=True`` with a
          ``multi_sig_policy``) AND all three structured fields are present AND
          ``dimension_scope`` is the full (unscoped) CARE set — so it signs the
          cross-SDK V3Complete pre-image, folding the quorum policy into the
          signature (#1841 S2b-2, the quorum-integrity headline).

    Raises:
        ValueError: (a) If SOME but not ALL of the three structured fields are
            supplied on a non-multi-sig record (partial supply) — a partial
            record would silently downgrade to legacy (dropping the supplied
            fields from the signature) while ``to_dict`` still persists them
            UNSIGNED, a fail-open secure-default (``rules/security.md`` §
            "Secure-Default … Never A Silent No-Op"). (b) If the multi-sig flags
            are INCONSISTENT (``multi_sig=True`` without a policy, OR a policy
            with ``multi_sig=False``) — a mis-constructed record. (c) If a
            MULTI-SIG record lacks the structured fold fields OR carries a
            narrowed ``dimension_scope`` — a multi-sig record MUST sign v3 (never
            legacy/v2, which drop the quorum binding); when v3 bytes are not
            producible it fails closed rather than silently downgrading.

    The record's ``signing_payload_version`` is set from this at ``delegate()``
    sign time; :func:`delegation_canonical_payload_str` then dispatches on that
    persisted field. Kept a pure function of the record so it is safe to call
    from both the sign path and any pre-persistence classification.
    """
    from kailash.trust.chain import (
        ALL_DIMENSIONS,
        DELEGATION_SIGNING_VERSION_LEGACY,
        DELEGATION_SIGNING_VERSION_V2,
        DELEGATION_SIGNING_VERSION_V3,
    )

    multi_sig = getattr(record, "multi_sig", False)
    multi_sig_policy = getattr(record, "multi_sig_policy", None)

    # Multi-sig flag/policy consistency (fail-closed on a mis-constructed record).
    # A record with ONE of the two set is inconsistent: silently downgrading it
    # would drop the quorum binding the v3 fold exists to provide.
    if multi_sig and multi_sig_policy is None:
        raise ValueError(
            "multi_sig=True requires a multi_sig_policy; a multi-sig record with "
            "no policy cannot bind its quorum (threshold + authorized_signers) "
            "into the signature (fail-closed)"
        )
    if multi_sig_policy is not None and not multi_sig:
        raise ValueError(
            "multi_sig_policy is set but multi_sig=False; a policy with no "
            "multi-sig flag is a mis-constructed record (fail-closed)"
        )

    structured = {
        "constraints": getattr(record, "constraints", None),
        "resource_limits": getattr(record, "resource_limits", None),
        "scope": getattr(record, "scope", None),
    }
    supplied = [name for name, val in structured.items() if val is not None]
    record_scope = getattr(record, "dimension_scope", ALL_DIMENSIONS)
    unscoped = frozenset(record_scope) == frozenset(ALL_DIMENSIONS)

    if multi_sig:
        # A multi-sig record MUST sign V3Complete — NEVER legacy/v2 (which do not
        # fold the quorum policy, so a store-write actor could weaken quorum
        # undetected). It REQUIRES all three structured fields AND the full
        # (unscoped) CARE set; anything else is not producible as v3 bytes and
        # fails closed rather than silently downgrading.
        if len(supplied) != len(structured):
            missing = sorted(name for name, val in structured.items() if val is None)
            raise ValueError(
                "multi-sig record requires constraints, resource_limits, and "
                f"scope for the V3Complete fold; missing {missing} (fail-closed — "
                "a multi-sig record must sign v3, never legacy/v2 which drop the "
                "quorum binding)"
            )
        if not unscoped:
            raise ValueError(
                "multi-sig record carries a narrowed dimension_scope "
                f"({sorted(record_scope)}); its cross-SDK V3 fold is not yet "
                "pinned (rs#1795) and the engine byte-verifies only the unscoped "
                "form — fail closed rather than downgrade a multi-sig record to "
                "legacy/v2 (which would drop the quorum binding)"
            )
        return DELEGATION_SIGNING_VERSION_V3

    # --- Non-multi-sig (S2b-1 logic, byte-identical) -------------------------
    if not supplied:
        # None supplied → legacy (byte-identical to pre-S2b).
        return DELEGATION_SIGNING_VERSION_LEGACY
    if len(supplied) != len(structured):
        # Partial supply is fail-open: it would sign legacy bytes (dropping the
        # supplied fields from the signature) yet persist them unsigned. Refuse.
        missing = sorted(name for name, val in structured.items() if val is None)
        raise ValueError(
            "structured signing fields (constraints, resource_limits, scope) "
            "must be supplied together or all omitted; got "
            f"{sorted(supplied)} without {missing}"
        )

    # The engine byte-verifies only the all-dimensions form; a narrowed
    # dimension_scope stays legacy (its scope-widening defence lives in the
    # legacy payload, chain.py:to_signing_payload). See build_delegation_signing_input.
    if not unscoped:
        return DELEGATION_SIGNING_VERSION_LEGACY

    return DELEGATION_SIGNING_VERSION_V2


def delegation_canonical_payload_str(record: "DelegationRecord") -> str:
    """Return the canonical signing string a delegation record is signed/verified over.

    The SINGLE shared dispatch every delegation sign/verify call site routes
    through, so the version gate has ONE source of truth (``rules/security.md``
    § Multi-Site Kwarg Plumbing).

    Args:
        record: The delegation record whose canonical pre-image is requested.

    Returns:
        For a ``legacy-python-v0`` record, the ``serialize_for_signing`` string
        of the legacy ``to_signing_payload()`` pre-image (byte-identical to the
        pre-migration behaviour). For a ``v2-complete`` record, the canonical
        cross-SDK V2Complete engine pre-image (folding the record-persisted
        ``constraints`` / ``resource_limits`` / ``scope``) as a UTF-8 string
        (#1841 S2b-1). For a ``v3-complete`` (multi-sig) record, the canonical
        cross-SDK V3Complete engine pre-image (the V2Complete fold PLUS the
        record-persisted ``multi_sig_policy`` — threshold + canonically-sorted
        authorized_signers) as a UTF-8 string (#1841 S2b-2).

    Raises:
        UnsupportedSigningPayloadVersionError: If the record declares an
            UNRECOGNISED version (not legacy / v2 / v3). Falling through to the
            legacy verifier would sign/verify the WRONG pre-image, so this fails
            closed.
        ValueError: If a ``v2``/``v3``-labelled record is missing the structured
            fold fields (or a ``v3`` record lacks a valid multi_sig policy) — the
            engine bridge fails closed rather than emitting guessed bytes. The
            verify path catches this and returns ``valid=False`` (never lets it
            escape as a DoS-via-exception).
    """
    # Import lazily to avoid a chain <-> signing import cycle: chain.py imports
    # kailash.trust.signing.crypto at module load, which initialises the signing
    # package; a top-level `from kailash.trust.chain import ...` here would run
    # before chain's module-level constants are defined.
    from kailash.trust.chain import (
        DELEGATION_SIGNING_VERSION_LEGACY,
        DELEGATION_SIGNING_VERSION_V2,
        DELEGATION_SIGNING_VERSION_V3,
    )

    version = getattr(
        record, "signing_payload_version", DELEGATION_SIGNING_VERSION_LEGACY
    )
    if version == DELEGATION_SIGNING_VERSION_LEGACY:
        return serialize_for_signing(record.to_signing_payload())

    if version == DELEGATION_SIGNING_VERSION_V2:
        # v2-complete: fold the record-persisted structured constraints /
        # resource_limits / scope into the cross-SDK V2Complete engine pre-image
        # (#1841 S2b-1). The engine emits ASCII-only canonical JCS bytes for the
        # §5.3 inputs; decode to str for the signer (byte-identical on re-encode).
        payload_bytes = delegation_record_signing_payload(
            record,
            SigningPayloadVersion.V2_COMPLETE,
            constraints=record.constraints,
            resource_limits=record.resource_limits,
            scope=record.scope,
        )
        return payload_bytes.decode("utf-8")

    if version == DELEGATION_SIGNING_VERSION_V3:
        # v3-complete: the V2Complete fold PLUS the record-persisted multi-sig
        # policy (threshold + canonically-sorted authorized_signers) folded into
        # the signed pre-image (#1841 S2b-2 — the quorum-integrity headline). The
        # record's own multi_sig / multi_sig_policy are passed faithfully: a
        # record LABELLED v3 that is not a genuine multi-sig record (multi_sig
        # False or policy None) fails closed at the engine (which requires a
        # multi-sig record with a policy for V3_COMPLETE) rather than emitting
        # guessed bytes.
        payload_bytes = delegation_record_signing_payload(
            record,
            SigningPayloadVersion.V3_COMPLETE,
            constraints=record.constraints,
            resource_limits=record.resource_limits,
            scope=record.scope,
            multi_sig=getattr(record, "multi_sig", False),
            multi_sig_policy=getattr(record, "multi_sig_policy", None),
        )
        return payload_bytes.decode("utf-8")

    # Any UNRECOGNISED version (not legacy / v2 / v3) fails closed — falling
    # through to the legacy verifier would check the WRONG pre-image.
    raise UnsupportedSigningPayloadVersionError(
        version, record_id=getattr(record, "id", None)
    )


def build_delegation_signing_input(
    record: "DelegationRecord",
    *,
    constraints: Optional[ConstraintDimensions],
    resource_limits: Optional[ResourceLimits],
    scope: Optional[DelegationScope],
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
    constraints: Optional[ConstraintDimensions],
    resource_limits: Optional[ResourceLimits],
    scope: Optional[DelegationScope],
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
