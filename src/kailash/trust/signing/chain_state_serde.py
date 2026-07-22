# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Shared serialization for the #1912 Wave 2 chain-state signature field.

#1912 Wave 2 added ``chain_state_signature: Optional[str]`` to
``TrustLineageChain`` — ONE Ed25519 signature by the genesis authority over the
canonical chain-state pre-image (``chain_state_signing``). The signature
verifies ONLY if the field survives persistence: the reconstructed chain MUST
carry the SAME signature the pre-image was signed with. If a serializer drops
the field, a signed chain reloads as legacy → Wave-2 verify accepts it with a
WARN instead of enforcing (``security.md`` § "Multi-Site Kwarg Plumbing" — the
field plumbed through one serializer, missed the siblings).

This module is the SINGLE shared helper every chain serializer routes through —
``TrustLineageChain.to_dict`` (the chain-level path every persistent store uses)
— so the encode and decode halves cannot drift (``security.md`` §
"Pre-Encoder Consolidation").

Prune-when-unset: a legacy chain (field at its ``None`` default) serializes to a
dict with NO ``chain_state_signature`` key, byte-identical to a pre-Wave-2 chain
(``cross-sdk-inspection.md`` Rule 4d). A signed chain emits the key, and on
reconstruction it is bound back so the chain-state signature re-verifies. The
snake_case shape matches ``TrustLineageChain.to_dict``; the camelCase shape
matches the W3C VC convention.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol

__all__ = [
    "serialize_chain_state_signature_fields",
    "deserialize_chain_state_signature_fields",
]


class _ChainStateSignatureSource(Protocol):
    """Structural type for the field ``serialize_...`` reads.

    A LOCAL Protocol (not an import of ``kailash.trust.chain.TrustLineageChain``)
    mirrors the sibling ``capability_fold_serde._CapabilityFoldSource`` shape;
    ``TrustLineageChain`` satisfies it structurally.
    """

    chain_state_signature: Optional[str]


_SNAKE_KEYS = {"chain_state_signature": "chain_state_signature"}
_CAMEL_KEYS = {"chain_state_signature": "chainStateSignature"}


def _keys(camel: bool) -> Dict[str, str]:
    return _CAMEL_KEYS if camel else _SNAKE_KEYS


def serialize_chain_state_signature_fields(
    chain: _ChainStateSignatureSource, *, camel: bool = False
) -> Dict[str, Any]:
    """Serialize the chain-state signature prune-when-unset.

    The key is emitted ONLY when the field is set, so a legacy chain yields an
    empty dict (no new key — byte-identical to a pre-Wave-2 chain).

    Args:
        chain: The chain to read ``chain_state_signature`` from.
        camel: Emit camelCase keys (W3C VC convention) instead of snake_case.

    Returns:
        A dict carrying ``{chain_state_signature: <value>}`` for a signed chain,
        or an empty dict for a legacy chain.
    """
    k = _keys(camel)
    if chain.chain_state_signature is not None:
        return {k["chain_state_signature"]: chain.chain_state_signature}
    return {}


def deserialize_chain_state_signature_fields(
    data: Dict[str, Any], *, camel: bool = False
) -> Dict[str, Any]:
    """Reconstruct the chain-state signature from a serialized dict.

    Backward-compatible: a pre-Wave-2 dict has no key, so the field resolves to
    ``None`` and the chain reconstructs as legacy (Wave-2 verify accepts it with
    a WARN).

    Args:
        data: The serialized chain dict.
        camel: Read camelCase keys (W3C VC convention) instead of snake_case.

    Returns:
        A kwargs dict ``{chain_state_signature: <value-or-None>}`` suitable for
        the ``TrustLineageChain`` constructor.
    """
    k = _keys(camel)
    return {"chain_state_signature": data.get(k["chain_state_signature"])}
