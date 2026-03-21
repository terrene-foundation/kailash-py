# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP Biscuit Interop -- Biscuit-inspired token format for EATP constraints.

Provides functions to serialize EATP ConstraintEnvelopes into a compact binary
token format inspired by the Biscuit authorization token specification.  Tokens
use Ed25519 signatures (via ``eatp.crypto``) and support delegation-style
*attenuation*: anyone holding a token can add restrictions without needing the
original authority signing key.

This is a **simplified, Biscuit-inspired** format -- not a full Biscuit spec
implementation.  No external biscuit library is required.

Binary Layout::

    version (1 byte)
    authority_block_len (4 bytes, big-endian uint32)
    authority_block (JSON bytes -- facts, rules, constraints from envelope)
    num_attenuation_blocks (4 bytes, big-endian uint32)
    [
        attenuation_block_len (4 bytes, big-endian uint32)
        attenuation_block (JSON bytes -- additional constraints)
    ] * num_attenuation_blocks
    num_signatures (4 bytes, big-endian uint32)
    [
        public_key (32 bytes -- Ed25519 raw public key)
        signature (64 bytes -- Ed25519 signature)
    ] * num_signatures

Signature chain:
    - Signature 0 (authority): signs ``version + authority_block_len + authority_block``
    - Signature N (attenuator N): signs ``previous_signature (64 bytes) + attenuation_block_N``

Usage::

    from kailash.trust.interop.biscuit import to_biscuit, from_biscuit, attenuate, verify_biscuit
    from kailash.trust.signing.crypto import generate_keypair

    private_key, public_key = generate_keypair()
    token = to_biscuit(envelope, private_key)

    # Add restrictions without the original key
    att_private, _ = generate_keypair()
    restricted = attenuate(token, ["read_only"], att_private)

    # Verify and import
    if verify_biscuit(restricted, public_key):
        restored = from_biscuit(restricted, public_key)
"""

import base64
import json
import logging
import struct
from typing import Any, Dict, List, Tuple

from kailash.trust.chain import Constraint, ConstraintEnvelope, ConstraintType
from kailash.trust.exceptions import InvalidSignatureError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

BISCUIT_VERSION: int = 1
"""Binary format version.  Incremented on breaking layout changes."""

_SIGNATURE_BYTES: int = 64
"""Length of an Ed25519 signature in bytes."""

_PUBLIC_KEY_BYTES: int = 32
"""Length of an Ed25519 public key in bytes."""

_UINT32_BYTES: int = 4
"""Length of a big-endian uint32 field."""

# ---------------------------------------------------------------------------
# Guarded import of PyNaCl (required for Ed25519)
# ---------------------------------------------------------------------------

try:
    from nacl.exceptions import BadSignatureError
    from nacl.signing import SigningKey, VerifyKey

    _NACL_AVAILABLE = True
except ImportError:
    _NACL_AVAILABLE = False
    SigningKey = None  # type: ignore[assignment,misc]
    VerifyKey = None  # type: ignore[assignment,misc]
    BadSignatureError = Exception  # type: ignore[assignment,misc]


def _require_nacl() -> None:
    """Raise ImportError if PyNaCl is not installed."""
    if not _NACL_AVAILABLE:
        raise ImportError("PyNaCl is required for Biscuit token operations. Install with: pip install pynacl")


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_signing_key(signing_key: str) -> None:
    """Raise ValueError if the signing key is empty or missing."""
    if not signing_key:
        raise ValueError(
            "signing_key must be a non-empty base64-encoded Ed25519 private key. "
            "Generate one with eatp.crypto.generate_keypair()."
        )


def _validate_public_key(public_key: str) -> None:
    """Raise ValueError if the public key is empty or missing."""
    if not public_key:
        raise ValueError(
            "public_key must be a non-empty base64-encoded Ed25519 public key. "
            "Generate one with eatp.crypto.generate_keypair()."
        )


def _validate_attenuator_key(attenuator_key: str) -> None:
    """Raise ValueError if the attenuator key is empty or missing."""
    if not attenuator_key:
        raise ValueError(
            "attenuator_key must be a non-empty base64-encoded Ed25519 private key. "
            "Generate one with eatp.crypto.generate_keypair()."
        )


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _serialize_authority_block(envelope: ConstraintEnvelope) -> bytes:
    """Build the JSON authority block from a ConstraintEnvelope.

    Returns:
        UTF-8 encoded JSON bytes.
    """
    constraint_facts: List[Dict[str, Any]] = []
    for c in envelope.active_constraints:
        constraint_facts.append(
            {
                "id": c.id,
                "constraint_type": c.constraint_type.value,
                "value": c.value,
                "source": c.source,
                "priority": c.priority,
            }
        )

    block: Dict[str, Any] = {
        "facts": {
            "envelope_id": envelope.id,
            "agent_id": envelope.agent_id,
            "constraint_hash": envelope.constraint_hash,
        },
        "rules": {},
        "constraints": constraint_facts,
    }

    return json.dumps(block, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _deserialize_authority_block(data: bytes) -> ConstraintEnvelope:
    """Reconstruct a ConstraintEnvelope from authority block JSON bytes."""
    block = json.loads(data.decode("utf-8"))

    facts = block["facts"]
    constraint_list: List[Constraint] = []
    for cf in block.get("constraints", []):
        constraint_list.append(
            Constraint(
                id=cf["id"],
                constraint_type=ConstraintType(cf["constraint_type"]),
                value=cf["value"],
                source=cf["source"],
                priority=cf.get("priority", 0),
            )
        )

    return ConstraintEnvelope(
        id=facts["envelope_id"],
        agent_id=facts["agent_id"],
        active_constraints=constraint_list,
        constraint_hash=facts.get("constraint_hash", ""),
    )


# ---------------------------------------------------------------------------
# Low-level signing / verification
# ---------------------------------------------------------------------------


def _sign_bytes(payload: bytes, private_key_b64: str) -> Tuple[bytes, bytes]:
    """Sign payload with Ed25519 and return (public_key_raw, signature_raw).

    Args:
        payload: Bytes to sign.
        private_key_b64: Base64-encoded 32-byte Ed25519 private key seed.

    Returns:
        Tuple of (32-byte public key, 64-byte signature).
    """
    _require_nacl()
    private_key_bytes = base64.b64decode(private_key_b64)
    signing_key = SigningKey(private_key_bytes)
    signed = signing_key.sign(payload)
    public_key_raw = bytes(signing_key.verify_key)
    return public_key_raw, signed.signature


def _verify_bytes(payload: bytes, signature: bytes, public_key_raw: bytes) -> bool:
    """Verify an Ed25519 signature.

    Returns:
        True if valid, False otherwise.
    """
    _require_nacl()
    try:
        verify_key = VerifyKey(public_key_raw)
        verify_key.verify(payload, signature)
        return True
    except BadSignatureError:
        return False
    except Exception as exc:
        logger.debug("Signature verification error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Token parsing helpers
# ---------------------------------------------------------------------------


def _parse_token(
    token: bytes,
) -> Tuple[
    int,  # version
    bytes,  # authority_block_bytes
    List[bytes],  # attenuation_blocks
    List[Tuple[bytes, bytes]],  # signatures: [(pub_key, sig), ...]
]:
    """Parse a Biscuit-inspired token into its constituent parts.

    Raises:
        ValueError: If the token is malformed or too short.
    """
    if len(token) < 1 + _UINT32_BYTES:
        raise ValueError(
            f"Token too short ({len(token)} bytes). "
            "A valid Biscuit token requires at least 5 bytes (version + authority block length)."
        )

    offset = 0

    # Version
    version = token[offset]
    offset += 1

    # Authority block
    authority_block_len = struct.unpack(">I", token[offset : offset + _UINT32_BYTES])[0]
    offset += _UINT32_BYTES

    if offset + authority_block_len > len(token):
        raise ValueError(
            f"Token truncated: authority block claims {authority_block_len} bytes "
            f"but only {len(token) - offset} bytes remain."
        )
    authority_block_bytes = token[offset : offset + authority_block_len]
    offset += authority_block_len

    # Number of attenuation blocks
    if offset + _UINT32_BYTES > len(token):
        raise ValueError("Token truncated: missing attenuation block count field.")
    num_attenuation = struct.unpack(">I", token[offset : offset + _UINT32_BYTES])[0]
    offset += _UINT32_BYTES

    attenuation_blocks: List[bytes] = []
    for i in range(num_attenuation):
        if offset + _UINT32_BYTES > len(token):
            raise ValueError(f"Token truncated: missing length field for attenuation block {i}.")
        att_block_len = struct.unpack(">I", token[offset : offset + _UINT32_BYTES])[0]
        offset += _UINT32_BYTES

        if offset + att_block_len > len(token):
            raise ValueError(
                f"Token truncated: attenuation block {i} claims {att_block_len} bytes "
                f"but only {len(token) - offset} bytes remain."
            )
        attenuation_blocks.append(token[offset : offset + att_block_len])
        offset += att_block_len

    # Number of signatures
    if offset + _UINT32_BYTES > len(token):
        raise ValueError("Token truncated: missing signature count field.")
    num_signatures = struct.unpack(">I", token[offset : offset + _UINT32_BYTES])[0]
    offset += _UINT32_BYTES

    signatures: List[Tuple[bytes, bytes]] = []
    for i in range(num_signatures):
        needed = _PUBLIC_KEY_BYTES + _SIGNATURE_BYTES
        if offset + needed > len(token):
            raise ValueError(
                f"Token truncated: signature entry {i} needs {needed} bytes "
                f"but only {len(token) - offset} bytes remain."
            )
        pub_key = token[offset : offset + _PUBLIC_KEY_BYTES]
        offset += _PUBLIC_KEY_BYTES
        sig = token[offset : offset + _SIGNATURE_BYTES]
        offset += _SIGNATURE_BYTES
        signatures.append((pub_key, sig))

    return version, authority_block_bytes, attenuation_blocks, signatures


def _build_authority_payload(version_byte: int, authority_block: bytes) -> bytes:
    """Build the payload that the authority signature covers.

    Layout: version(1) + authority_block_len(4) + authority_block
    """
    return struct.pack("B", version_byte) + struct.pack(">I", len(authority_block)) + authority_block


# ===================================================================
# Public API
# ===================================================================


def to_biscuit(envelope: ConstraintEnvelope, signing_key: str) -> bytes:
    """Export a ConstraintEnvelope as a Biscuit-inspired binary token.

    The token contains:
    - An authority block encoding the envelope's constraint facts.
    - Zero attenuation blocks (initially).
    - A single Ed25519 signature over the authority block.

    Args:
        envelope: The ConstraintEnvelope to serialize.
        signing_key: Base64-encoded Ed25519 private key.

    Returns:
        Binary token bytes.

    Raises:
        ValueError: If signing_key is empty.
        ImportError: If PyNaCl is not installed.
    """
    _validate_signing_key(signing_key)
    _require_nacl()

    authority_block = _serialize_authority_block(envelope)

    # Build the payload that the authority signs
    authority_payload = _build_authority_payload(BISCUIT_VERSION, authority_block)
    pub_key_raw, signature = _sign_bytes(authority_payload, signing_key)

    # Assemble token
    parts: List[bytes] = []

    # 1. Version byte
    parts.append(struct.pack("B", BISCUIT_VERSION))

    # 2. Authority block length + block
    parts.append(struct.pack(">I", len(authority_block)))
    parts.append(authority_block)

    # 3. Number of attenuation blocks (0 initially)
    parts.append(struct.pack(">I", 0))

    # 4. Signatures: count + entries
    parts.append(struct.pack(">I", 1))
    parts.append(pub_key_raw)
    parts.append(signature)

    token = b"".join(parts)

    logger.debug(
        "Created Biscuit token for envelope=%s agent=%s (%d bytes)",
        envelope.id,
        envelope.agent_id,
        len(token),
    )

    return token


def from_biscuit(token: bytes, public_key: str) -> ConstraintEnvelope:
    """Import a Biscuit-inspired token and return the ConstraintEnvelope.

    Verifies the full signature chain before deserializing.  If verification
    fails, raises an error rather than returning potentially tampered data.

    Args:
        token: Binary token bytes produced by ``to_biscuit`` or ``attenuate``.
        public_key: Base64-encoded Ed25519 public key of the original authority.

    Returns:
        The deserialized ConstraintEnvelope from the authority block.

    Raises:
        ValueError: If public_key is empty, token is malformed, or version is wrong.
        InvalidSignatureError: If any signature in the chain is invalid.
        ImportError: If PyNaCl is not installed.
    """
    _validate_public_key(public_key)
    _require_nacl()

    version, authority_block_bytes, attenuation_blocks, signatures = _parse_token(token)

    if version != BISCUIT_VERSION:
        raise ValueError(
            f"Unsupported Biscuit token version: {version}. "
            f"Expected version {BISCUIT_VERSION}. "
            "The token may have been created with a newer version of the EATP SDK."
        )

    # Verify the full signature chain
    if not _verify_signature_chain(version, authority_block_bytes, attenuation_blocks, signatures, public_key):
        raise InvalidSignatureError(
            "Biscuit token signature verification failed. "
            "The token may have been tampered with or signed by a different key.",
            record_type="biscuit_token",
        )

    envelope = _deserialize_authority_block(authority_block_bytes)

    logger.debug(
        "Imported Biscuit token for envelope=%s agent=%s",
        envelope.id,
        envelope.agent_id,
    )

    return envelope


def attenuate(
    token: bytes,
    additional_constraints: List[str],
    attenuator_key: str,
) -> bytes:
    """Add restrictions to a token without needing the original signing key.

    Creates a new attenuation block with the given constraints and signs it
    using the attenuator's key.  The resulting token carries the full history
    of attenuations, forming a signature chain.

    Args:
        token: Existing Biscuit token bytes.
        additional_constraints: List of constraint strings to add.
        attenuator_key: Base64-encoded Ed25519 private key of the attenuator.

    Returns:
        New token bytes with the attenuation block appended.

    Raises:
        ValueError: If additional_constraints is empty or attenuator_key is empty.
        ImportError: If PyNaCl is not installed.
    """
    if not additional_constraints:
        raise ValueError(
            "additional_constraints must be a non-empty list. Attenuation with zero constraints serves no purpose."
        )
    _validate_attenuator_key(attenuator_key)
    _require_nacl()

    version, authority_block_bytes, attenuation_blocks, signatures = _parse_token(token)

    # Build the new attenuation block
    att_block_data: Dict[str, Any] = {
        "additional_constraints": additional_constraints,
    }
    att_block_bytes = json.dumps(att_block_data, separators=(",", ":"), sort_keys=True).encode("utf-8")

    # The attenuator signs: previous_signature(64 bytes) + new_attenuation_block
    # The previous signature is the last signature in the chain
    if not signatures:
        raise ValueError("Token has no signatures. Cannot attenuate an unsigned token.")
    previous_signature = signatures[-1][1]  # the 64-byte signature

    attenuation_payload = previous_signature + att_block_bytes
    att_pub_key_raw, att_signature = _sign_bytes(attenuation_payload, attenuator_key)

    # Rebuild the token with the new attenuation block and signature
    new_attenuation_blocks = attenuation_blocks + [att_block_bytes]
    new_signatures = signatures + [(att_pub_key_raw, att_signature)]

    parts: List[bytes] = []

    # 1. Version byte
    parts.append(struct.pack("B", version))

    # 2. Authority block
    parts.append(struct.pack(">I", len(authority_block_bytes)))
    parts.append(authority_block_bytes)

    # 3. Attenuation blocks
    parts.append(struct.pack(">I", len(new_attenuation_blocks)))
    for ab in new_attenuation_blocks:
        parts.append(struct.pack(">I", len(ab)))
        parts.append(ab)

    # 4. Signatures
    parts.append(struct.pack(">I", len(new_signatures)))
    for pub_key, sig in new_signatures:
        parts.append(pub_key)
        parts.append(sig)

    new_token = b"".join(parts)

    logger.debug(
        "Attenuated Biscuit token: added %d constraints, now %d attenuation blocks, %d signatures (%d bytes)",
        len(additional_constraints),
        len(new_attenuation_blocks),
        len(new_signatures),
        len(new_token),
    )

    return new_token


def verify_biscuit(token: bytes, public_key: str) -> bool:
    """Verify the integrity of a Biscuit-inspired token.

    Checks:
    1. Token format is valid and parseable.
    2. Version byte matches the expected version.
    3. Authority signature is valid against the provided public key.
    4. Each attenuation signature is valid (chained to the previous signature).

    Args:
        token: Binary token bytes.
        public_key: Base64-encoded Ed25519 public key of the original authority.

    Returns:
        True if the token is valid, False otherwise.

    Raises:
        ValueError: If public_key is empty.
    """
    _validate_public_key(public_key)

    if not token:
        return False

    try:
        _require_nacl()
    except ImportError:
        logger.error("PyNaCl not available; cannot verify Biscuit token")
        return False

    try:
        version, authority_block_bytes, attenuation_blocks, signatures = _parse_token(token)
    except ValueError as exc:
        logger.debug("Biscuit token parse failed: %s", exc)
        return False

    if version != BISCUIT_VERSION:
        logger.debug(
            "Biscuit token version mismatch: got %d, expected %d",
            version,
            BISCUIT_VERSION,
        )
        return False

    return _verify_signature_chain(version, authority_block_bytes, attenuation_blocks, signatures, public_key)


# ---------------------------------------------------------------------------
# Internal signature chain verification
# ---------------------------------------------------------------------------


def _verify_signature_chain(
    version: int,
    authority_block_bytes: bytes,
    attenuation_blocks: List[bytes],
    signatures: List[Tuple[bytes, bytes]],
    public_key_b64: str,
) -> bool:
    """Verify the complete signature chain of a Biscuit token.

    Args:
        version: Token version byte.
        authority_block_bytes: Raw authority block bytes.
        attenuation_blocks: List of raw attenuation block bytes.
        signatures: List of (public_key_raw, signature_raw) tuples.
        public_key_b64: Base64-encoded public key of the authority.

    Returns:
        True if all signatures are valid, False otherwise.
    """
    expected_sig_count = 1 + len(attenuation_blocks)
    if len(signatures) != expected_sig_count:
        logger.debug(
            "Signature count mismatch: expected %d, got %d",
            expected_sig_count,
            len(signatures),
        )
        return False

    # Verify authority signature (signature 0)
    authority_pub_key_raw = base64.b64decode(public_key_b64)
    token_pub_key_raw, authority_sig = signatures[0]

    # The public key in the token must match the provided public key
    if token_pub_key_raw != authority_pub_key_raw:
        logger.debug("Authority public key mismatch in token vs provided key")
        return False

    authority_payload = _build_authority_payload(version, authority_block_bytes)
    if not _verify_bytes(authority_payload, authority_sig, authority_pub_key_raw):
        logger.debug("Authority signature verification failed")
        return False

    # Verify each attenuation signature
    previous_sig = authority_sig
    for i, att_block in enumerate(attenuation_blocks):
        att_pub_key, att_sig = signatures[i + 1]
        attenuation_payload = previous_sig + att_block
        if not _verify_bytes(attenuation_payload, att_sig, att_pub_key):
            logger.debug("Attenuation signature %d verification failed", i)
            return False
        previous_sig = att_sig

    return True
