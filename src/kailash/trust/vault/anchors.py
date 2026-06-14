# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""EATP-12 vault-binding audit-envelope schema + builders (W2-D2).

This module owns the per-subtype ``event_payload`` envelope construction
(issue #1312, shard W2-D2). It does NOT dispatch (that is D1's
:mod:`kailash.trust.vault.dispatch`) and it does NOT sign — it builds the
canonical ``event_payload`` dict whose ``content_signing_bytes`` pre-image is
byte-identical to the §12.4-§12.11 golden fixtures. The caller (I1's
backup/restore path) signs ``content_signing_bytes(event_type, payload,
signer.delegate_id)`` and dispatches the result through D1.

Conformance IDs owned here (EATP-12 §4.5/§4.5.1):

- **N12-AU-01** — OUTCOME and DENIAL are DIFFERENT schemas. Outcome anchors
  carry the per-subtype field set; denial anchors carry EXACTLY
  ``{subtype, principal, missing_capability_or_scope, target_handle_ref,
  timestamp, time_attested}`` (``vault_id`` / ``kek_generation`` /
  commitments / KCV / ritual EXPLICITLY OMITTED, not null-filled). The
  denial-summary is its own schema.
- **N12-AU-03** — the binding (NOT the engine) validates
  ``event_payload["subtype"]`` against the closed ``vault_*`` set before
  emit, rejecting an unrecognized subtype OR one colliding with a
  substrate-reserved subtype
  (``{dispatch_invocation, cascade_emission, lifecycle_transition,
  posture_ratchet, sovereign_handover}``). The signed pre-image is
  ``content_signing_bytes`` with ``event_type="external_side_effect"``;
  ``alg_id`` rides ``event_payload.alg_id`` (NO top-level slot — N12-AU-02).
- **N12-AU-04** — the exact per-subtype required/forbidden field set + the
  shared field encodings. JCS sorts keys at encode time, so the builders
  return un-sorted dicts; required-field presence + forbidden-field absence
  is enforced per subtype, fail-closed on a missing required field.
- **N12-AU-04a** — the two-state ``timestamp`` + ``time_attested`` grammar:
  ``time_attested`` is ALWAYS present (bool). When ``True`` → ``timestamp``
  is the caller-supplied RFC3339-UTC-second-precision value with trailing
  ``Z``. When ``False`` → ``timestamp`` is forced to the fixed sentinel
  ``"unverified"`` (NOT omitted, NOT null). The builders take the timestamp
  + attested flag as inputs and ENFORCE the grammar; they do NOT implement
  the trust clock (a later concern).
- **N12-CRY-SC** — ``side_channel_hardened`` bool, default ``False``.
- **N12-CRY-PIN(d)** — ``slip39_params`` recorded as
  ``{"extendable": True, "iteration_exponent": <int>, "group_threshold": 1,
  "master_secret_bits": <128|256>}``.

The §12.4-§12.11 materialized fixtures are the byte-pin targets; the builders
reproduce them exactly for the §12.1 fixed inputs.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Mapping, Sequence

from kailash.trust.vault.errors import N12FT01Code, VaultBindingError

logger = logging.getLogger(__name__)

__all__ = [
    "VAULT_SUBTYPES",
    "SUBSTRATE_RESERVED_SUBTYPES",
    "UNVERIFIED_SENTINEL",
    "validate_subtype",
    "build_anchor_payload",
    "build_backup_anchor",
    "build_restore_anchor",
    "build_restore_forced_stale_anchor",
    "build_restore_raw_anchor",
    "build_kek_rotation_anchor",
    "build_holder_rotation_anchor",
    "build_kek_recommit_anchor",
    "build_kek_retire_anchor",
    "build_denial_anchor",
    "build_denial_summary_anchor",
]


# ---------------------------------------------------------------------------
# Subtype namespace (N12-AU-03)
# ---------------------------------------------------------------------------

#: The closed ``vault_*`` outcome + denial + summary subtypes the binding
#: emits. Any ``event_payload["subtype"]`` NOT in this set is rejected before
#: emit (N12-AU-03) so the V6 golden-fixture pre-image is defined over a
#: reserved, validated discriminator rather than an unguarded field.
VAULT_SUBTYPES: frozenset[str] = frozenset(
    {
        "vault_key_backup",
        "vault_key_restore",
        "vault_key_restore_forced_stale",
        "vault_key_restore_raw",
        "vault_kek_rotation",
        "vault_kek_recommit",
        "vault_kek_retire",
        "vault_holder_rotation",
        "vault_key_backup_denied",
        "vault_key_restore_denied",
        "vault_denial_summary",
    }
)

#: The substrate-reserved subtypes (``delegate/audit.py:228-236`` migration
#: map) the ``vault_`` namespace MUST NOT collide with (N12-AU-03 /
#: F-XSDK-12). Every vault subtype begins ``vault_`` AND is none of these.
SUBSTRATE_RESERVED_SUBTYPES: frozenset[str] = frozenset(
    {
        "dispatch_invocation",
        "cascade_emission",
        "lifecycle_transition",
        "posture_ratchet",
        "sovereign_handover",
    }
)

#: The fixed two-state-grammar sentinel for ``timestamp`` when
#: ``time_attested`` is False (N12-AU-04a). NOT omitted, NOT null.
UNVERIFIED_SENTINEL: str = "unverified"

#: RFC3339 UTC second-precision with trailing ``Z`` (the only attested form,
#: N12-AU-04a). e.g. ``2026-06-12T00:00:00Z``.
_RFC3339_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

_LOWER_HEX = re.compile(r"^[0-9a-f]+$")


def validate_subtype(subtype: object) -> str:
    """Validate ``subtype`` against the closed ``vault_*`` set (N12-AU-03).

    The BINDING validates the subtype — ``AuditChainEngine.emit_event``
    validates only ``event_type``, never ``subtype`` — so this gate is the
    only mechanism guaranteeing the signed pre-image is defined over a
    reserved, validated discriminator. Fail-closed.

    Args:
        subtype: The candidate ``event_payload["subtype"]`` value.

    Returns:
        The validated subtype string.

    Raises:
        VaultBindingError: ``subtype`` is not a ``str``, does NOT begin
            ``vault_``, collides with a substrate-reserved subtype, or is not
            in the closed :data:`VAULT_SUBTYPES` set. Carries
            ``N12FT01Code.PARAMETER_MISMATCH`` (the closest taxonomy code; the
            enum has no dedicated subtype-error code, and a colliding /
            unrecognized subtype IS a parameter disagreement against the
            pinned schema).
    """
    if not isinstance(subtype, str):
        raise VaultBindingError(
            N12FT01Code.PARAMETER_MISMATCH,
            f"vault anchor subtype MUST be a str; got " f"{type(subtype).__name__}",
            details={"subtype": repr(subtype)},
        )
    if subtype in SUBSTRATE_RESERVED_SUBTYPES:
        raise VaultBindingError(
            N12FT01Code.PARAMETER_MISMATCH,
            f"vault anchor subtype {subtype!r} collides with a "
            f"substrate-reserved subtype (N12-AU-03 / F-XSDK-12); the "
            f"vault namespace is disjoint from "
            f"{sorted(SUBSTRATE_RESERVED_SUBTYPES)}",
            details={"subtype": subtype},
        )
    if not subtype.startswith("vault_"):
        raise VaultBindingError(
            N12FT01Code.PARAMETER_MISMATCH,
            f"vault anchor subtype {subtype!r} MUST begin 'vault_' "
            f"(N12-AU-03 reserved namespace)",
            details={"subtype": subtype},
        )
    if subtype not in VAULT_SUBTYPES:
        raise VaultBindingError(
            N12FT01Code.PARAMETER_MISMATCH,
            f"vault anchor subtype {subtype!r} is not in the closed vault "
            f"subtype set (N12-AU-03); valid: {sorted(VAULT_SUBTYPES)}",
            details={"subtype": subtype},
        )
    return subtype


# ---------------------------------------------------------------------------
# Shared field-encoding helpers (N12-AU-04 "Shared field encodings")
# ---------------------------------------------------------------------------


def _enforce_two_state_timestamp(
    payload: dict[str, Any],
    *,
    timestamp: str,
    time_attested: bool,
) -> None:
    """Enforce the N12-AU-04a two-state ``timestamp`` + ``time_attested`` grammar.

    Mutates ``payload`` in place, setting both fields. ``time_attested`` is
    ALWAYS present (bool). When True, ``timestamp`` MUST be RFC3339 UTC
    second-precision with trailing ``Z``. When False, ``timestamp`` is forced
    to the :data:`UNVERIFIED_SENTINEL`, regardless of the supplied value
    (a forgeable host time MUST NOT leak through).

    Raises:
        VaultBindingError: ``time_attested`` is not a bool, or
            ``time_attested`` is True and ``timestamp`` is not RFC3339-Z.
    """
    if not isinstance(time_attested, bool):
        raise VaultBindingError(
            N12FT01Code.PARAMETER_MISMATCH,
            f"time_attested MUST be a bool (N12-AU-04a always-present); got "
            f"{type(time_attested).__name__}",
            details={"time_attested": repr(time_attested)},
        )
    if time_attested:
        if not isinstance(timestamp, str) or not _RFC3339_Z.match(timestamp):
            raise VaultBindingError(
                N12FT01Code.PARAMETER_MISMATCH,
                f"time_attested=True requires an RFC3339 UTC second-precision "
                f"timestamp with trailing 'Z' (N12-AU-04a); got "
                f"{timestamp!r}",
                details={"timestamp": repr(timestamp)},
            )
        payload["timestamp"] = timestamp
    else:
        # Degraded: force the fixed sentinel; a host-supplied value is NOT
        # trusted when the trust clock is unavailable (N12-AU-04a / SG-03/05).
        payload["timestamp"] = UNVERIFIED_SENTINEL
    payload["time_attested"] = time_attested


def _coerce_int(name: str, value: object) -> int:
    """Validate ``value`` is a non-bool JSON integer (N12-AU-04 int fields).

    ``bool`` is a subclass of ``int`` in Python but encodes as ``true`` /
    ``false`` under JSON, so it is rejected — an int field MUST be a JSON
    integer, never a boolean.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise VaultBindingError(
            N12FT01Code.PARAMETER_MISMATCH,
            f"{name} MUST be a JSON integer (N12-AU-04); got "
            f"{type(value).__name__}={value!r}",
            details={"field": name, "value": repr(value)},
        )
    return value


def _coerce_str(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise VaultBindingError(
            N12FT01Code.PARAMETER_MISMATCH,
            f"{name} MUST be a str (N12-AU-04); got {type(value).__name__}",
            details={"field": name, "value": repr(value)},
        )
    return value


def _coerce_lower_hex(name: str, value: object, *, length: int | None = None) -> str:
    """Validate ``value`` is a lowercase-hex string (N12-AU-04 hex fields).

    Args:
        length: when set, the EXACT required hex length (e.g. 16 for the KCV,
            64 for a SHA-256 commitment).
    """
    s = _coerce_str(name, value)
    if not _LOWER_HEX.match(s):
        raise VaultBindingError(
            N12FT01Code.PARAMETER_MISMATCH,
            f"{name} MUST be lowercase hex (N12-AU-04); got {s!r}",
            details={"field": name, "value": s},
        )
    if length is not None and len(s) != length:
        raise VaultBindingError(
            N12FT01Code.PARAMETER_MISMATCH,
            f"{name} MUST be {length} hex chars (N12-AU-04); got {len(s)}",
            details={"field": name, "value": s, "expected_length": length},
        )
    return s


def _coerce_holders(value: object) -> list[str]:
    """Validate ``holders`` is an ordered array of holder-ID strings.

    Order is preserved verbatim (N12-AU-04 "ordered JSON array of stable
    holder-ID strings"); NOT sorted — the distribution order is recorded.
    """
    if not isinstance(value, (list, tuple)):
        raise VaultBindingError(
            N12FT01Code.PARAMETER_MISMATCH,
            f"holders MUST be an ordered array (N12-AU-04); got "
            f"{type(value).__name__}",
            details={"holders": repr(value)},
        )
    out: list[str] = []
    for i, h in enumerate(value):
        out.append(_coerce_str(f"holders[{i}]", h))
    return out


def _coerce_shard_commitments(value: object) -> list[str]:
    """Validate ``shard_commitments`` is an ordered array of lowercase-hex strings."""
    if not isinstance(value, (list, tuple)):
        raise VaultBindingError(
            N12FT01Code.PARAMETER_MISMATCH,
            f"shard_commitments MUST be an ordered array (N12-AU-04); got "
            f"{type(value).__name__}",
            details={"shard_commitments": repr(value)},
        )
    return [
        _coerce_lower_hex(f"shard_commitments[{i}]", c) for i, c in enumerate(value)
    ]


def _build_slip39_params(value: Mapping[str, Any]) -> dict[str, Any]:
    """Build the pinned ``slip39_params`` object (N12-CRY-PIN(d) / F-XSDK-10).

    Shape is EXACTLY ``{"extendable": True, "iteration_exponent": <int>,
    "group_threshold": 1, "master_secret_bits": <128|256>}``. ``extendable``
    MUST be True; ``group_threshold`` MUST be 1; ``master_secret_bits`` MUST
    be 128 or 256; ``(k,n)`` is NOT duplicated here (it lives in the sibling
    ``{"k","n"}`` field).
    """
    if not isinstance(value, Mapping):
        raise VaultBindingError(
            N12FT01Code.PARAMETER_MISMATCH,
            f"slip39_params MUST be a mapping (N12-CRY-PIN(d)); got "
            f"{type(value).__name__}",
            details={"slip39_params": repr(value)},
        )
    extendable = value.get("extendable")
    if extendable is not True:
        raise VaultBindingError(
            N12FT01Code.PARAMETER_MISMATCH,
            f"slip39_params.extendable MUST be True (N12-CRY-PIN(d)); got "
            f"{extendable!r}",
            details={"extendable": repr(extendable)},
        )
    iteration_exponent = _coerce_int(
        "slip39_params.iteration_exponent", value.get("iteration_exponent")
    )
    group_threshold = value.get("group_threshold")
    if group_threshold != 1:
        raise VaultBindingError(
            N12FT01Code.PARAMETER_MISMATCH,
            f"slip39_params.group_threshold MUST be 1 (N12-CRY-PIN(d)); got "
            f"{group_threshold!r}",
            details={"group_threshold": repr(group_threshold)},
        )
    master_secret_bits = _coerce_int(
        "slip39_params.master_secret_bits", value.get("master_secret_bits")
    )
    if master_secret_bits not in (128, 256):
        raise VaultBindingError(
            N12FT01Code.PARAMETER_MISMATCH,
            f"slip39_params.master_secret_bits MUST be 128 or 256 "
            f"(N12-CRY-PIN(d)); got {master_secret_bits!r}",
            details={"master_secret_bits": master_secret_bits},
        )
    return {
        "extendable": True,
        "iteration_exponent": iteration_exponent,
        "group_threshold": 1,
        "master_secret_bits": master_secret_bits,
    }


def _coerce_bool(name: str, value: object) -> bool:
    if not isinstance(value, bool):
        raise VaultBindingError(
            N12FT01Code.PARAMETER_MISMATCH,
            f"{name} MUST be a bool (N12-AU-04); got {type(value).__name__}",
            details={"field": name, "value": repr(value)},
        )
    return value


#: The canonical key triples for the Complete-level governance sub-objects
#: embedded into the signed ``event_payload`` (N12-CL-03(c) / N12-CL-05). These
#: MUST match :meth:`GovernanceApproval.to_payload` /
#: :meth:`CeremonyWitness.to_payload` in :mod:`kailash.trust.vault.complete`.
_APPROVAL_SUBOBJECT_KEYS: tuple[str, str, str] = (
    "approver_principal",
    "approver_delegate_id",
    "approval_signature",
)
_WITNESS_SUBOBJECT_KEYS: tuple[str, str, str] = (
    "witness_principal",
    "witness_delegate_id",
    "witness_signature",
)


def _coerce_governance_subobject(
    name: str, value: object, *, keys: tuple[str, str, str]
) -> dict[str, str]:
    """Validate a Complete-level approval/witness sub-object (N12-CL-03(c)/CL-05).

    The sub-object is bound into the signed ``event_payload`` (covered by
    ``content_signing_bytes``), so a missing/forged token is cryptographically
    detectable. Enforces EXACTLY the three canonical keys (``*_principal``,
    ``*_delegate_id``, ``*_signature``), each a str, with the signature a 128-hex
    Ed25519 signature — extra or missing keys are rejected fail-closed so the
    embedded shape cannot drift from the verifier's ``to_payload`` contract.
    """
    if not isinstance(value, Mapping):
        raise VaultBindingError(
            N12FT01Code.PARAMETER_MISMATCH,
            f"{name} MUST be a mapping (N12-CL-03(c)/CL-05); got "
            f"{type(value).__name__}",
            details={"field": name, "value": repr(value)},
        )
    present = set(value)
    expected = set(keys)
    if present != expected:
        raise VaultBindingError(
            N12FT01Code.PARAMETER_MISMATCH,
            f"{name} MUST carry EXACTLY {sorted(expected)} (N12-CL-03(c)/CL-05); "
            f"got {sorted(present)}",
            details={
                "field": name,
                "missing": sorted(expected - present),
                "unexpected": sorted(present - expected),
            },
        )
    principal_key, delegate_key, signature_key = keys
    return {
        principal_key: _coerce_str(f"{name}.{principal_key}", value[principal_key]),
        delegate_key: _coerce_str(f"{name}.{delegate_key}", value[delegate_key]),
        signature_key: _coerce_lower_hex(
            f"{name}.{signature_key}", value[signature_key], length=128
        ),
    }


# ---------------------------------------------------------------------------
# Per-subtype required/forbidden field enforcement (N12-AU-04)
# ---------------------------------------------------------------------------

# Each entry: subtype -> (required field names, explicitly-forbidden field
# names). The two-state timestamp pair (`timestamp` + `time_attested`) is
# REQUIRED on every subtype and is enforced separately by
# `_enforce_two_state_timestamp`, so it is omitted from these required sets.
_FORBIDDEN_ON_DENIAL: frozenset[str] = frozenset(
    {"vault_id", "kek_generation", "kek_identity_commitment", "kcv", "k", "n"}
)


def _forbid_absent(payload: Mapping[str, Any], forbidden: frozenset[str]) -> None:
    """Fail-closed if a forbidden field is present (N12-AU-01 denial schema)."""
    present = sorted(forbidden & set(payload))
    if present:
        raise VaultBindingError(
            N12FT01Code.PARAMETER_MISMATCH,
            f"vault denial payload MUST NOT carry {present} (N12-AU-01: "
            f"explicitly OMITTED, not null-filled)",
            details={"subtype": payload.get("subtype"), "forbidden_present": present},
        )


# ---------------------------------------------------------------------------
# Builders — one per subtype (N12-AU-04 per-subtype rows)
# ---------------------------------------------------------------------------


def build_backup_anchor(
    *,
    alg_id: str,
    k: int,
    n: int,
    holders: Sequence[str],
    shard_count: int,
    vault_id: str,
    kek_generation: int,
    kek_identity_commitment: str,
    kek_commitment_alg: str,
    kcv: str,
    shard_commitments: Sequence[str],
    slip39_params: Mapping[str, Any],
    principal: str,
    timestamp: str,
    time_attested: bool,
    side_channel_hardened: bool = False,
    approver: Mapping[str, Any] | None = None,
    witness: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a ``vault_key_backup`` outcome ``event_payload`` (§12.4 / N12-AU-04).

    The full backup field set: ``alg_id``, ``{k,n}``, ``holders``,
    ``shard_count``, ``vault_id``, ``kek_generation``,
    ``kek_identity_commitment``, ``kek_commitment_alg``, ``kcv``,
    ``shard_commitments``, ``slip39_params``, ``side_channel_hardened``,
    ``principal``, ``timestamp`` + ``time_attested``, and — at Complete level
    (N12-CL-03/CL-05) — the embedded ``approver`` / ``witness`` governance
    sub-objects (``{*_principal, *_delegate_id, *_signature}``, the verifier's
    ``to_payload`` shape). Both are absent at Conformant, so the Conformant
    pre-image is byte-unchanged (§12.4 golden fixture preserved).
    """
    payload: dict[str, Any] = {
        "subtype": "vault_key_backup",
        "alg_id": _coerce_str("alg_id", alg_id),
        "k": _coerce_int("k", k),
        "n": _coerce_int("n", n),
        "holders": _coerce_holders(holders),
        "shard_count": _coerce_int("shard_count", shard_count),
        "vault_id": _coerce_str("vault_id", vault_id),
        "kek_generation": _coerce_int("kek_generation", kek_generation),
        "kek_identity_commitment": _coerce_lower_hex(
            "kek_identity_commitment", kek_identity_commitment, length=64
        ),
        "kek_commitment_alg": _coerce_str("kek_commitment_alg", kek_commitment_alg),
        "kcv": _coerce_lower_hex("kcv", kcv, length=16),
        "shard_commitments": _coerce_shard_commitments(shard_commitments),
        "slip39_params": _build_slip39_params(slip39_params),
        "side_channel_hardened": _coerce_bool(
            "side_channel_hardened", side_channel_hardened
        ),
        "principal": _coerce_str("principal", principal),
    }
    if approver is not None:
        payload["approver"] = _coerce_governance_subobject(
            "approver", approver, keys=_APPROVAL_SUBOBJECT_KEYS
        )
    if witness is not None:
        payload["witness"] = _coerce_governance_subobject(
            "witness", witness, keys=_WITNESS_SUBOBJECT_KEYS
        )
    _enforce_two_state_timestamp(
        payload, timestamp=timestamp, time_attested=time_attested
    )
    validate_subtype(payload["subtype"])
    return payload


def build_restore_anchor(
    *,
    alg_id: str,
    re_established_handle_ref: str,
    vault_id: str,
    kek_generation: int,
    generation_checked: int,
    kek_identity_commitment: str,
    kek_commitment_alg: str,
    holders: Sequence[str],
    shard_count: int,
    shard_commitments: Sequence[str],
    principal: str,
    timestamp: str,
    time_attested: bool,
    raw: bool = False,
    approval: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a ``vault_key_restore`` (or ``vault_key_restore_raw``) ``event_payload``.

    Restore-class shape (§12.8 / N12-AU-04, fix [18]/[19]): a restore READS
    shards; it does NOT create a ritual, so ``{k,n}``, ``kcv``,
    ``slip39_params``, ``side_channel_hardened`` are NOT carried.
    ``holders`` / ``shard_count`` / ``shard_commitments`` MUST be copied from
    the current-generation distribution (the latest backup / holder-rotation
    / kek-rotation distribution anchor), NOT the presenting k-shard subset.

    Args:
        raw: when True, the subtype is ``vault_key_restore_raw`` (the
            raw-bytes escape-hatch restore, §4.1); else ``vault_key_restore``.
        approval: the Complete-level governance-approval sub-object
            (N12-CL-03(c), the verifier's ``to_payload`` shape) bound into the
            signed ``event_payload``; absent at Conformant (byte-unchanged) and
            mandatory for the high-risk restore paths (raw / forced-stale /
            cooling-off) at Complete.
    """
    subtype = "vault_key_restore_raw" if raw else "vault_key_restore"
    payload: dict[str, Any] = {
        "subtype": subtype,
        "alg_id": _coerce_str("alg_id", alg_id),
        "re_established_handle_ref": _coerce_str(
            "re_established_handle_ref", re_established_handle_ref
        ),
        "vault_id": _coerce_str("vault_id", vault_id),
        "kek_generation": _coerce_int("kek_generation", kek_generation),
        "generation_checked": _coerce_int("generation_checked", generation_checked),
        "kek_identity_commitment": _coerce_lower_hex(
            "kek_identity_commitment", kek_identity_commitment, length=64
        ),
        "kek_commitment_alg": _coerce_str("kek_commitment_alg", kek_commitment_alg),
        "holders": _coerce_holders(holders),
        "shard_count": _coerce_int("shard_count", shard_count),
        "shard_commitments": _coerce_shard_commitments(shard_commitments),
        "principal": _coerce_str("principal", principal),
    }
    if approval is not None:
        payload["approval"] = _coerce_governance_subobject(
            "approval", approval, keys=_APPROVAL_SUBOBJECT_KEYS
        )
    _enforce_two_state_timestamp(
        payload, timestamp=timestamp, time_attested=time_attested
    )
    validate_subtype(payload["subtype"])
    return payload


def build_restore_raw_anchor(**kwargs: Any) -> dict[str, Any]:
    """Build a ``vault_key_restore_raw`` ``event_payload`` (§4.1 escape-hatch).

    Convenience wrapper over :func:`build_restore_anchor` with ``raw=True``.
    """
    kwargs.pop("raw", None)
    return build_restore_anchor(raw=True, **kwargs)


def build_restore_forced_stale_anchor(
    *,
    alg_id: str,
    re_established_handle_ref: str,
    vault_id: str,
    kek_generation: int,
    generation_checked: int,
    restored_generation: int,
    overridden_current_generation: int,
    kek_identity_commitment: str,
    kek_commitment_alg: str,
    holders: Sequence[str],
    shard_count: int,
    shard_commitments: Sequence[str],
    principal: str,
    timestamp: str,
    time_attested: bool,
    approval: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a ``vault_key_restore_forced_stale`` ``event_payload`` (§12.11 / N12-SG-03).

    Forced-stale rollback: its OWN row, separated from the ordinary restore.
    Carries the two net-new generation fields ``restored_generation`` (the
    captured/installed OLD generation) and ``overridden_current_generation``
    (the current generation overridden) IN ADDITION to ``kek_generation`` /
    ``generation_checked`` (fix [7]). The canonical mapping is exactly
    ``kek_generation == generation_checked == restored_generation`` and
    ``overridden_current_generation > restored_generation``.
    ``holders`` / ``shard_count`` / ``shard_commitments`` MUST be copied from
    the CAPTURED (restored, old-generation) distribution (fix [2]).

    Args:
        approval: the Complete-level governance-approval sub-object
            (N12-CL-03(c)) bound into the signed ``event_payload``. Forced-stale
            is a CL-03 high-risk path: at Complete the approval is MANDATORY (the
            hot path rejects a missing/forged approval ``missing-clearance``
            BEFORE the KEK is treated as re-established).
    """
    payload: dict[str, Any] = {
        "subtype": "vault_key_restore_forced_stale",
        "alg_id": _coerce_str("alg_id", alg_id),
        "re_established_handle_ref": _coerce_str(
            "re_established_handle_ref", re_established_handle_ref
        ),
        "vault_id": _coerce_str("vault_id", vault_id),
        "kek_generation": _coerce_int("kek_generation", kek_generation),
        "generation_checked": _coerce_int("generation_checked", generation_checked),
        "restored_generation": _coerce_int("restored_generation", restored_generation),
        "overridden_current_generation": _coerce_int(
            "overridden_current_generation", overridden_current_generation
        ),
        "kek_identity_commitment": _coerce_lower_hex(
            "kek_identity_commitment", kek_identity_commitment, length=64
        ),
        "kek_commitment_alg": _coerce_str("kek_commitment_alg", kek_commitment_alg),
        "holders": _coerce_holders(holders),
        "shard_count": _coerce_int("shard_count", shard_count),
        "shard_commitments": _coerce_shard_commitments(shard_commitments),
        "principal": _coerce_str("principal", principal),
    }
    # Canonical-mapping invariants (N12-AU-04 forced-stale row).
    if not (
        payload["kek_generation"]
        == payload["generation_checked"]
        == payload["restored_generation"]
    ):
        raise VaultBindingError(
            N12FT01Code.PARAMETER_MISMATCH,
            "forced-stale anchor requires kek_generation == generation_checked "
            "== restored_generation (N12-AU-04 canonical mapping)",
            details={
                "kek_generation": payload["kek_generation"],
                "generation_checked": payload["generation_checked"],
                "restored_generation": payload["restored_generation"],
            },
        )
    if payload["overridden_current_generation"] <= payload["restored_generation"]:
        raise VaultBindingError(
            N12FT01Code.PARAMETER_MISMATCH,
            "forced-stale anchor requires overridden_current_generation > "
            "restored_generation (the rollback went backward, N12-AU-04)",
            details={
                "overridden_current_generation": payload[
                    "overridden_current_generation"
                ],
                "restored_generation": payload["restored_generation"],
            },
        )
    if approval is not None:
        payload["approval"] = _coerce_governance_subobject(
            "approval", approval, keys=_APPROVAL_SUBOBJECT_KEYS
        )
    _enforce_two_state_timestamp(
        payload, timestamp=timestamp, time_attested=time_attested
    )
    validate_subtype(payload["subtype"])
    return payload


def build_kek_rotation_anchor(
    *,
    alg_id: str,
    prior_kek_generation: int,
    kek_generation: int,
    vault_id: str,
    k: int,
    n: int,
    holders: Sequence[str],
    shard_count: int,
    shard_commitments: Sequence[str],
    kek_identity_commitment: str,
    kek_commitment_alg: str,
    slip39_params: Mapping[str, Any],
    for_cause: bool,
    principal: str,
    timestamp: str,
    time_attested: bool,
    side_channel_hardened: bool = False,
) -> dict[str, Any]:
    """Build a ``vault_kek_rotation`` ``event_payload`` (§12.6 / N12-RT-06).

    Generation-advance + re-shard: the generation-advance fields AND the new
    generation's re-shard distribution (``{k,n}``, ``holders``,
    ``shard_count``, ``shard_commitments``, the new ``kek_identity_commitment``
    + ``kek_commitment_alg``, ``slip39_params``, ``side_channel_hardened``)
    plus ``for_cause`` (bool). NO ``kcv`` on this subtype (fix [3]).
    """
    payload: dict[str, Any] = {
        "subtype": "vault_kek_rotation",
        "alg_id": _coerce_str("alg_id", alg_id),
        "prior_kek_generation": _coerce_int(
            "prior_kek_generation", prior_kek_generation
        ),
        "kek_generation": _coerce_int("kek_generation", kek_generation),
        "vault_id": _coerce_str("vault_id", vault_id),
        "k": _coerce_int("k", k),
        "n": _coerce_int("n", n),
        "holders": _coerce_holders(holders),
        "shard_count": _coerce_int("shard_count", shard_count),
        "shard_commitments": _coerce_shard_commitments(shard_commitments),
        "kek_identity_commitment": _coerce_lower_hex(
            "kek_identity_commitment", kek_identity_commitment, length=64
        ),
        "kek_commitment_alg": _coerce_str("kek_commitment_alg", kek_commitment_alg),
        "slip39_params": _build_slip39_params(slip39_params),
        "side_channel_hardened": _coerce_bool(
            "side_channel_hardened", side_channel_hardened
        ),
        "for_cause": _coerce_bool("for_cause", for_cause),
        "principal": _coerce_str("principal", principal),
    }
    _enforce_two_state_timestamp(
        payload, timestamp=timestamp, time_attested=time_attested
    )
    validate_subtype(payload["subtype"])
    return payload


def build_holder_rotation_anchor(
    *,
    alg_id: str,
    old_k: int,
    old_n: int,
    new_k: int,
    new_n: int,
    departing_holder: str,
    holders: Sequence[str],
    vault_id: str,
    kek_generation: int,
    shard_commitments: Sequence[str],
    for_cause: bool,
    principal: str,
    timestamp: str,
    time_attested: bool,
) -> dict[str, Any]:
    """Build a ``vault_holder_rotation`` ``event_payload`` (N12-RT-02).

    Amicable holder rotation: ``{old:{k,n}, new:{k,n}}``, ``departing_holder``,
    the new ``holders`` distribution, ``vault_id``, ``kek_generation``
    (unchanged by amicable rotation), the new ``shard_commitments``,
    ``for_cause`` (False for the amicable rotation this row records — a
    for-cause departure escalates to a generation-advancing
    ``vault_kek_rotation`` carrying ``for_cause=True``, fix [4]). NO ``kcv`` /
    ``side_channel_hardened`` unless re-derived.
    """
    payload: dict[str, Any] = {
        "subtype": "vault_holder_rotation",
        "alg_id": _coerce_str("alg_id", alg_id),
        "k": {
            "old": {"k": _coerce_int("old_k", old_k), "n": _coerce_int("old_n", old_n)},
            "new": {"k": _coerce_int("new_k", new_k), "n": _coerce_int("new_n", new_n)},
        },
        "departing_holder": _coerce_str("departing_holder", departing_holder),
        "holders": _coerce_holders(holders),
        "vault_id": _coerce_str("vault_id", vault_id),
        "kek_generation": _coerce_int("kek_generation", kek_generation),
        "shard_commitments": _coerce_shard_commitments(shard_commitments),
        "for_cause": _coerce_bool("for_cause", for_cause),
        "principal": _coerce_str("principal", principal),
    }
    _enforce_two_state_timestamp(
        payload, timestamp=timestamp, time_attested=time_attested
    )
    validate_subtype(payload["subtype"])
    return payload


def build_kek_recommit_anchor(
    *,
    alg_id: str,
    vault_id: str,
    kek_generation: int,
    prior_kek_commitment_alg: str,
    prior_kek_identity_commitment: str,
    new_kek_commitment_alg: str,
    new_kek_identity_commitment: str,
    principal: str,
    timestamp: str,
    time_attested: bool,
) -> dict[str, Any]:
    """Build a ``vault_kek_recommit`` ``event_payload`` (§12.7 / N12-CB-04(c)).

    Commitment-algorithm advance carrying the from-to pair, ``kek_generation``
    UNCHANGED, NO re-shard fields. EXACTLY ``alg_id``, ``vault_id``,
    ``kek_generation``, ``prior_kek_commitment_alg``,
    ``prior_kek_identity_commitment``, ``new_kek_commitment_alg``,
    ``new_kek_identity_commitment``, ``principal``, ``timestamp`` +
    ``time_attested``.
    """
    payload: dict[str, Any] = {
        "subtype": "vault_kek_recommit",
        "alg_id": _coerce_str("alg_id", alg_id),
        "vault_id": _coerce_str("vault_id", vault_id),
        "kek_generation": _coerce_int("kek_generation", kek_generation),
        "prior_kek_commitment_alg": _coerce_str(
            "prior_kek_commitment_alg", prior_kek_commitment_alg
        ),
        "prior_kek_identity_commitment": _coerce_lower_hex(
            "prior_kek_identity_commitment", prior_kek_identity_commitment, length=64
        ),
        "new_kek_commitment_alg": _coerce_str(
            "new_kek_commitment_alg", new_kek_commitment_alg
        ),
        "new_kek_identity_commitment": _coerce_lower_hex(
            "new_kek_identity_commitment", new_kek_identity_commitment, length=64
        ),
        "principal": _coerce_str("principal", principal),
    }
    _enforce_two_state_timestamp(
        payload, timestamp=timestamp, time_attested=time_attested
    )
    validate_subtype(payload["subtype"])
    return payload


def build_kek_retire_anchor(
    *,
    alg_id: str,
    vault_id: str,
    kek_generation: int,
    retired_kek_commitment_alg: str,
    retired_kek_identity_commitment: str,
    principal: str,
    timestamp: str,
    time_attested: bool,
) -> dict[str, Any]:
    """Build a ``vault_kek_retire`` ``event_payload`` (N12-CB-04(e)).

    Commitment-algorithm retirement marking a specific
    ``(algorithm -> commitment)`` registry entry non-verifiable,
    ``kek_generation`` UNCHANGED, NO re-shard fields. EXACTLY ``alg_id``,
    ``vault_id``, ``kek_generation``, ``retired_kek_commitment_alg``,
    ``retired_kek_identity_commitment``, ``principal``, ``timestamp`` +
    ``time_attested``.
    """
    payload: dict[str, Any] = {
        "subtype": "vault_kek_retire",
        "alg_id": _coerce_str("alg_id", alg_id),
        "vault_id": _coerce_str("vault_id", vault_id),
        "kek_generation": _coerce_int("kek_generation", kek_generation),
        "retired_kek_commitment_alg": _coerce_str(
            "retired_kek_commitment_alg", retired_kek_commitment_alg
        ),
        "retired_kek_identity_commitment": _coerce_lower_hex(
            "retired_kek_identity_commitment",
            retired_kek_identity_commitment,
            length=64,
        ),
        "principal": _coerce_str("principal", principal),
    }
    _enforce_two_state_timestamp(
        payload, timestamp=timestamp, time_attested=time_attested
    )
    validate_subtype(payload["subtype"])
    return payload


def build_denial_anchor(
    *,
    subtype: str,
    principal: str,
    missing_capability_or_scope: str,
    target_handle_ref: str,
    timestamp: str,
    time_attested: bool,
) -> dict[str, Any]:
    """Build a denial ``event_payload`` (§12.5 / §12.10 / N12-AU-01).

    Denial schema carries EXACTLY ``{subtype, principal,
    missing_capability_or_scope, target_handle_ref, timestamp,
    time_attested}``. ``vault_id`` / ``kek_generation`` / commitments / KCV /
    ritual are EXPLICITLY OMITTED (a restore denied before handle/shard
    resolution has no such values) — never null-filled.

    Args:
        subtype: ``vault_key_backup_denied`` or ``vault_key_restore_denied``.
    """
    if subtype not in ("vault_key_backup_denied", "vault_key_restore_denied"):
        raise VaultBindingError(
            N12FT01Code.PARAMETER_MISMATCH,
            f"denial anchor subtype MUST be vault_key_backup_denied or "
            f"vault_key_restore_denied (N12-AU-01); got {subtype!r}",
            details={"subtype": subtype},
        )
    payload: dict[str, Any] = {
        "subtype": subtype,
        "principal": _coerce_str("principal", principal),
        "missing_capability_or_scope": _coerce_str(
            "missing_capability_or_scope", missing_capability_or_scope
        ),
        "target_handle_ref": _coerce_str("target_handle_ref", target_handle_ref),
    }
    _enforce_two_state_timestamp(
        payload, timestamp=timestamp, time_attested=time_attested
    )
    _forbid_absent(payload, _FORBIDDEN_ON_DENIAL)
    validate_subtype(payload["subtype"])
    return payload


def build_denial_summary_anchor(
    *,
    window_start: str,
    window_end: str,
    distinct_principals: Sequence[str],
    distinct_missing_capabilities: Sequence[str],
    principal_set_root: str,
    coalesced_count: int,
    timestamp: str,
    time_attested: bool,
) -> dict[str, Any]:
    """Build a ``vault_denial_summary`` ``event_payload`` (§12.9 / N12-AU-01).

    Windowed denial summary (safety tier). ``distinct_principals`` and
    ``distinct_missing_capabilities`` MUST be sorted ascending so the JCS
    canonical form is byte-deterministic across SDKs; ``principal_set_root``
    is the lowercase-hex sorted-hash/Merkle digest over the FULL
    distinct-principal set; ``coalesced_count`` is the total coalesced count.
    ``window_start`` / ``window_end`` are RFC3339-Z.
    """
    principals = sorted(
        _coerce_str(f"distinct_principals[{i}]", p)
        for i, p in enumerate(distinct_principals)
    )
    capabilities = sorted(
        _coerce_str(f"distinct_missing_capabilities[{i}]", c)
        for i, c in enumerate(distinct_missing_capabilities)
    )
    for label, value in (("window_start", window_start), ("window_end", window_end)):
        if not isinstance(value, str) or not _RFC3339_Z.match(value):
            raise VaultBindingError(
                N12FT01Code.PARAMETER_MISMATCH,
                f"{label} MUST be RFC3339 UTC second-precision with trailing "
                f"'Z' (N12-AU-04 denial-summary); got {value!r}",
                details={"field": label, "value": repr(value)},
            )
    payload: dict[str, Any] = {
        "subtype": "vault_denial_summary",
        "window_start": window_start,
        "window_end": window_end,
        "distinct_principals": principals,
        "distinct_missing_capabilities": capabilities,
        "principal_set_root": _coerce_lower_hex(
            "principal_set_root", principal_set_root
        ),
        "coalesced_count": _coerce_int("coalesced_count", coalesced_count),
    }
    _enforce_two_state_timestamp(
        payload, timestamp=timestamp, time_attested=time_attested
    )
    validate_subtype(payload["subtype"])
    return payload


# ---------------------------------------------------------------------------
# Single dispatching builder (convenience for I1's call sites)
# ---------------------------------------------------------------------------

_BUILDERS = {
    "vault_key_backup": build_backup_anchor,
    "vault_key_restore": build_restore_anchor,
    "vault_key_restore_raw": build_restore_raw_anchor,
    "vault_key_restore_forced_stale": build_restore_forced_stale_anchor,
    "vault_kek_rotation": build_kek_rotation_anchor,
    "vault_holder_rotation": build_holder_rotation_anchor,
    "vault_kek_recommit": build_kek_recommit_anchor,
    "vault_kek_retire": build_kek_retire_anchor,
    "vault_denial_summary": build_denial_summary_anchor,
    "vault_key_backup_denied": build_denial_anchor,
    "vault_key_restore_denied": build_denial_anchor,
}


def build_anchor_payload(subtype: str, **fields: Any) -> dict[str, Any]:
    """Dispatch to the per-subtype builder by ``subtype`` (N12-AU-04).

    Validates ``subtype`` against the closed ``vault_*`` set (N12-AU-03)
    BEFORE dispatching, then delegates to the matching builder. The denial
    subtypes route to :func:`build_denial_anchor` with ``subtype`` forwarded.

    Args:
        subtype: a ``vault_*`` subtype string.
        **fields: the per-subtype builder kwargs.

    Returns:
        The canonical ``event_payload`` dict (un-sorted; JCS sorts at encode).

    Raises:
        VaultBindingError: ``subtype`` is unrecognized / colliding (N12-AU-03)
            or a required field is missing / malformed (N12-AU-04).
    """
    validate_subtype(subtype)
    builder = _BUILDERS[subtype]
    if subtype in ("vault_key_backup_denied", "vault_key_restore_denied"):
        return builder(subtype=subtype, **fields)
    return builder(**fields)
