# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Shared serialization for the #1841 S2b signing fold-fields.

#1841 S2b-1/S2b-2 added five structured signing fields to ``DelegationRecord`` —
``constraints`` / ``resource_limits`` / ``scope`` (S2b-1) and ``multi_sig`` /
``multi_sig_policy`` (S2b-2) — which fold into the cross-SDK V2Complete /
V3Complete signing pre-image (:func:`delegation_canonical_payload_str`). A v2/v3
record's signature verifies ONLY if these fields survive persistence: the
reconstructed record MUST recompute the SAME pre-image the signature was made
over.

Every delegation serializer — ``TrustLineageChain._serialize_delegation`` (the
chain-level path every persistent store uses), the W3C VC interop serializer, the
JWT interop serializer, and ``DelegationRecord.to_dict`` itself — MUST carry these
fields through, or a v2/v3 delegation reloads with the fold fields ``None`` and
its signature no longer verifies (``security.md`` § "Multi-Site Kwarg Plumbing" —
the field plumbed through one serializer, missed the siblings). This module is
the SINGLE shared helper both halves of that contract route through, so encode
and decode cannot drift apart (``security.md`` § "Pre-Encoder Consolidation").

Prune-when-unset: a legacy record (all five fields at their None/False default)
serializes to a dict with NO fold-field keys, byte-identical to a pre-S2b record
(``cross-sdk-inspection.md`` Rule 4d). A CONFIGURED value is emitted and, on
reconstruction, cryptographically bound.

The persistence dict is NOT itself a cross-SDK signing pre-image (the signing
bytes come from :func:`delegation_canonical_payload_str` reading the RECORD
FIELDS, not this dict), so the dict shape carries no cross-SDK byte-pin — it just
faithfully round-trips the five fields. The snake_case shape matches
``DelegationRecord.to_dict``; the camelCase shape matches the W3C VC convention.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol

from kailash.trust.signing.delegation_payload import (
    ConstraintDimensions,
    DelegationScope,
    MultiSigSigningPolicy,
    ResourceLimits,
    SigningPayloadVersion,
)

__all__ = [
    "serialize_fold_fields",
    "deserialize_fold_fields",
]


class _FoldSourceRecord(Protocol):
    """Structural type for the record fields ``serialize_fold_fields`` reads.

    A LOCAL Protocol (not an import of ``kailash.trust.chain.DelegationRecord``)
    so this low-level serializer never imports the high-level ``chain`` module —
    not even under ``TYPE_CHECKING``. That one-way dependency (chain → this
    module, never back) is what keeps CodeQL's ``py/unsafe-cyclic-import`` clear;
    ``DelegationRecord`` satisfies this Protocol structurally.
    """

    constraints: "Optional[ConstraintDimensions]"
    resource_limits: "Optional[ResourceLimits]"
    scope: "Optional[DelegationScope]"
    multi_sig: bool
    multi_sig_policy: "Optional[MultiSigSigningPolicy]"


# Attribute name -> serialized key, per case convention. ``constraints`` and
# ``scope`` are identical in both; ``resource_limits`` / ``multi_sig`` /
# ``multi_sig_policy`` differ. The W3C VC serializer emits camelCase; the
# chain-level + JWT serializers (and DelegationRecord.to_dict) emit snake_case.
_SNAKE_KEYS = {
    "constraints": "constraints",
    "resource_limits": "resource_limits",
    "scope": "scope",
    "multi_sig": "multi_sig",
    "multi_sig_policy": "multi_sig_policy",
}
_CAMEL_KEYS = {
    "constraints": "constraints",
    "resource_limits": "resourceLimits",
    "scope": "scope",
    "multi_sig": "multiSig",
    "multi_sig_policy": "multiSigPolicy",
}


def _keys(camel: bool) -> Dict[str, str]:
    return _CAMEL_KEYS if camel else _SNAKE_KEYS


def serialize_fold_fields(
    record: _FoldSourceRecord, *, camel: bool = False
) -> Dict[str, Any]:
    """Serialize the five S2b fold-fields prune-when-unset.

    Only fields with a non-default value are emitted, so a legacy record yields
    an empty dict (no new keys — byte-identical to pre-S2b). Mirrors exactly the
    fold-field emission in ``DelegationRecord.to_dict``.

    Args:
        record: The delegation record to read the fold fields from.
        camel: Emit camelCase keys (W3C VC convention) instead of snake_case.

    Returns:
        A dict carrying only the SET fold fields (empty for a legacy record).
    """
    k = _keys(camel)
    out: Dict[str, Any] = {}
    if record.constraints is not None:
        out[k["constraints"]] = record.constraints.to_dict()
    if record.resource_limits is not None:
        out[k["resource_limits"]] = record.resource_limits.to_dict()
    if record.scope is not None:
        out[k["scope"]] = record.scope.to_dict()
    # multi_sig / multi_sig_policy prune-when-unset so a non-multi-sig record's
    # dict carries NO multi_sig keys (byte-identical to a pre-S2b-2 record).
    if record.multi_sig:
        out[k["multi_sig"]] = True
    if record.multi_sig_policy is not None:
        out[k["multi_sig_policy"]] = record.multi_sig_policy.to_dict()
    return out


def deserialize_fold_fields(
    data: Dict[str, Any],
    *,
    signing_payload_version: str,
    camel: bool = False,
    record_id: Any = None,
) -> Dict[str, Any]:
    """Reconstruct the five S2b fold-fields from a serialized delegation dict.

    Backward-compatible: a pre-S2b dict has no fold-field keys, so every field
    resolves to its None/False default and the record verifies as legacy.
    ``MultiSigSigningPolicy.from_dict`` re-runs ``__post_init__`` (distinct-signer
    / 32-byte / threshold<=N validation), so a store-tampered policy fails closed
    on reconstruction.

    Fail-closed consistency guard (defense in depth against a store-tampered
    record): a multi-sig record MUST carry a policy AND declare the v3 version;
    an isolated ``multi_sig_policy`` with ``multi_sig=False`` is a mis-constructed
    record. These mirror the ``select_signing_version`` sign-time posture so a
    tampered persisted record cannot reconstruct into an inconsistent state.

    Args:
        data: The serialized delegation dict.
        signing_payload_version: The record's resolved signing-payload version
            (already read by the caller), used for the multi_sig/version guard.
        camel: Read camelCase keys (W3C VC convention) instead of snake_case.
        record_id: The record id, for error-message context (optional).

    Returns:
        A kwargs dict ``{constraints, resource_limits, scope, multi_sig,
        multi_sig_policy}`` suitable for the ``DelegationRecord`` constructor.

    Raises:
        ValueError: On an inconsistent multi-sig record (fail-closed).
    """
    # The v3 wire token is sourced from the LOW-LEVEL delegation_payload enum
    # (``SigningPayloadVersion.V3_COMPLETE.value == "v3-complete"``), the same
    # string as ``chain.DELEGATION_SIGNING_VERSION_V3`` — so this module never
    # imports the high-level ``chain`` module (not even lazily), keeping the
    # dependency one-way (chain → this module) and CodeQL's cyclic-import clear.
    v3_version = SigningPayloadVersion.V3_COMPLETE.value

    k = _keys(camel)

    raw_constraints = data.get(k["constraints"])
    constraints = (
        ConstraintDimensions.from_dict(raw_constraints)
        if raw_constraints is not None
        else None
    )
    raw_resource_limits = data.get(k["resource_limits"])
    resource_limits = (
        ResourceLimits.from_dict(raw_resource_limits)
        if raw_resource_limits is not None
        else None
    )
    raw_scope = data.get(k["scope"])
    scope = DelegationScope.from_dict(raw_scope) if raw_scope is not None else None

    multi_sig = bool(data.get(k["multi_sig"], False))
    raw_multi_sig_policy = data.get(k["multi_sig_policy"])
    multi_sig_policy = (
        MultiSigSigningPolicy.from_dict(raw_multi_sig_policy)
        if raw_multi_sig_policy is not None
        else None
    )

    _reject_inconsistent_multi_sig(
        multi_sig=multi_sig,
        multi_sig_policy=multi_sig_policy,
        signing_payload_version=signing_payload_version,
        v3_version=v3_version,
        record_id=record_id,
    )

    return {
        "constraints": constraints,
        "resource_limits": resource_limits,
        "scope": scope,
        "multi_sig": multi_sig,
        "multi_sig_policy": multi_sig_policy,
    }


def _reject_inconsistent_multi_sig(
    *,
    multi_sig: bool,
    multi_sig_policy: Any,
    signing_payload_version: str,
    v3_version: str,
    record_id: Any,
) -> None:
    """Fail closed on a store-tampered / mis-constructed multi-sig record."""
    ctx = f" (record_id={record_id!r})" if record_id is not None else ""
    if multi_sig and multi_sig_policy is None:
        raise ValueError(
            "deserialized multi_sig=True record has no multi_sig_policy; a "
            "multi-sig record cannot reconstruct its quorum binding (threshold + "
            f"authorized_signers) without a policy — fail-closed{ctx}"
        )
    if multi_sig_policy is not None and not multi_sig:
        raise ValueError(
            "deserialized record carries a multi_sig_policy but multi_sig=False; "
            f"a policy with no multi-sig flag is a mis-constructed record{ctx}"
        )
    if multi_sig and signing_payload_version != v3_version:
        raise ValueError(
            "deserialized multi_sig=True record declares signing_payload_version="
            f"{signing_payload_version!r}, not {v3_version!r}; a multi-sig record "
            f"MUST sign v3 (never legacy/v2 which drop the quorum binding){ctx}"
        )
