# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Shared serialization for the #1912 capability signing-payload version.

#1912 Wave 1 added the ``signing_payload_version`` discriminator to
``CapabilityAttestation`` (``legacy-python-v0`` / ``v1-subject-bound``). A v1
cap's signature verifies ONLY if the version survives persistence: the
reconstructed cap MUST recompute the SAME (subject-bound) pre-image the
signature was made over. If ANY serializer drops the version key, a v1 cap
reloads as legacy → the legacy verify recomputes WITHOUT the subject → the v1
signature fails (``security.md`` § "Multi-Site Kwarg Plumbing" — the field
plumbed through one serializer, missed the siblings).

This module is the SINGLE shared helper every capability serializer routes
through — ``TrustLineageChain.to_dict`` (the chain-level path every persistent
store uses), the JWT / W3C VC / SD-JWT interop serializers — so the encode and
decode halves cannot drift (``security.md`` § "Pre-Encoder Consolidation").

Prune-when-unset: a legacy cap (version at its ``legacy-python-v0`` default)
serializes to a dict with NO ``signing_payload_version`` key, byte-identical to
a pre-#1912 cap (``cross-sdk-inspection.md`` Rule 4d). A v1 cap emits the key,
and on reconstruction it is bound back so the subject-bound pre-image
re-verifies. The snake_case shape matches ``TrustLineageChain.to_dict`` / JWT;
the camelCase shape matches the W3C VC convention.
"""

from __future__ import annotations

from typing import Any, Dict, Protocol

__all__ = [
    "serialize_capability_fold_fields",
    "deserialize_capability_fold_fields",
]


class _CapabilityFoldSource(Protocol):
    """Structural type for the cap field ``serialize_capability_fold_fields`` reads.

    A LOCAL Protocol (not an import of
    ``kailash.trust.chain.CapabilityAttestation``) mirrors the sibling
    ``delegation_fold_serde._FoldSourceRecord`` shape; ``CapabilityAttestation``
    satisfies it structurally. The one carried field is the authoritative
    fold-field set the structural-parity test derives non-circularly.
    """

    signing_payload_version: str


# Attribute name -> serialized key, per case convention. The chain-level + JWT
# serializers emit snake_case; the W3C VC serializer emits camelCase.
_SNAKE_KEYS = {"signing_payload_version": "signing_payload_version"}
_CAMEL_KEYS = {"signing_payload_version": "signingPayloadVersion"}


def _keys(camel: bool) -> Dict[str, str]:
    return _CAMEL_KEYS if camel else _SNAKE_KEYS


def serialize_capability_fold_fields(
    cap: _CapabilityFoldSource, *, camel: bool = False
) -> Dict[str, Any]:
    """Serialize the capability signing-payload version prune-when-unset.

    The version key is emitted ONLY when NON-legacy, so a legacy cap yields an
    empty dict (no new key — byte-identical to a pre-#1912 cap).

    Args:
        cap: The capability to read ``signing_payload_version`` from.
        camel: Emit camelCase keys (W3C VC convention) instead of snake_case.

    Returns:
        A dict carrying ``{signing_payload_version: <value>}`` for a v1 cap, or
        an empty dict for a legacy cap.
    """
    # Import lazily so this low-level serde never imports the high-level ``chain``
    # module at module scope — chain.py imports THIS module at module scope, so a
    # back-edge here would form a load-time cycle (mirrors delegation_fold_serde's
    # one-way dependency; keeps CodeQL py/unsafe-cyclic-import clear).
    from kailash.trust.chain import CAPABILITY_SIGNING_VERSION_LEGACY

    k = _keys(camel)
    if cap.signing_payload_version != CAPABILITY_SIGNING_VERSION_LEGACY:
        return {k["signing_payload_version"]: cap.signing_payload_version}
    return {}


def deserialize_capability_fold_fields(
    data: Dict[str, Any], *, camel: bool = False
) -> Dict[str, Any]:
    """Reconstruct the capability signing-payload version from a serialized dict.

    Backward-compatible: a pre-#1912 dict has no version key, so the field
    resolves to ``legacy-python-v0`` and the cap verifies as legacy.

    Args:
        data: The serialized capability dict.
        camel: Read camelCase keys (W3C VC convention) instead of snake_case.

    Returns:
        A kwargs dict ``{signing_payload_version: <value>}`` suitable for the
        ``CapabilityAttestation`` constructor.
    """
    # Lazy import (see serialize_capability_fold_fields) — avoids a load-time
    # cycle with the high-level ``chain`` module.
    from kailash.trust.chain import CAPABILITY_SIGNING_VERSION_LEGACY

    k = _keys(camel)
    return {
        "signing_payload_version": data.get(
            k["signing_payload_version"], CAPABILITY_SIGNING_VERSION_LEGACY
        )
    }
