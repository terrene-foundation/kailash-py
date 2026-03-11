# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP UCAN Interop -- Export and import delegation records as UCAN v0.10.0 tokens.

Provides functions to serialize EATP DelegationRecords into UCAN (User
Controlled Authorization Networks) tokens following the v0.10.0 specification.
UCAN tokens use a JWT-like three-segment format (header.payload.signature)
with Ed25519 (EdDSA) signing.

This module implements UCAN encoding and decoding directly using base64 and
json -- no external UCAN library is required. Ed25519 cryptographic operations
are delegated to ``eatp.crypto``.

UCAN v0.10.0 specification: https://github.com/ucan-wg/spec

Key mapping from EATP to UCAN:

- ``iss`` (issuer): DID of the delegator
- ``aud`` (audience): DID of the delegatee
- ``att`` (attenuations): Delegated capabilities as UCAN resource/ability pairs
- ``exp`` (expiration): Delegation expiry as POSIX timestamp
- ``nnc`` (nonce): Unique token identifier for replay protection
- ``prf`` (proofs): Proof chain (empty for root UCANs)
- ``fct`` (facts): EATP-specific metadata (delegation ID, task, constraints)

Usage::

    from eatp.interop.ucan import to_ucan, from_ucan
    from eatp.crypto import generate_keypair

    private_key, public_key = generate_keypair()

    # Export delegation as UCAN token
    token = to_ucan(delegation, private_key)

    # Import and verify UCAN token
    restored = from_ucan(token, public_key)
"""

import base64
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from eatp.reasoning import ConfidentialityLevel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

UCAN_VERSION: str = "0.10.0"
"""UCAN specification version used for encoding tokens."""

UCAN_HEADER: Dict[str, str] = {
    "alg": "EdDSA",
    "typ": "JWT",
    "ucv": UCAN_VERSION,
}
"""Canonical UCAN header for Ed25519 signed tokens."""

# ---------------------------------------------------------------------------
# Internal helpers: base64url encoding/decoding
# ---------------------------------------------------------------------------


def _b64url_encode(data: bytes) -> str:
    """Encode bytes to base64url without padding.

    UCAN tokens use unpadded base64url encoding for all three segments,
    matching the JWT convention defined in RFC 7515 Section 2.

    Args:
        data: Raw bytes to encode.

    Returns:
        Base64url-encoded string without trailing '=' padding.
    """
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    """Decode a base64url string, adding padding as needed.

    Handles both padded and unpadded input, which is necessary because
    UCAN tokens strip padding from base64url segments.

    Args:
        s: Base64url-encoded string (with or without padding).

    Returns:
        Decoded raw bytes.

    Raises:
        ValueError: If the string is not valid base64url.
    """
    # Add padding to make length a multiple of 4
    padded = s + "=" * (4 - len(s) % 4)
    try:
        return base64.urlsafe_b64decode(padded)
    except Exception as e:
        raise ValueError(f"Invalid base64url encoding: {e}") from e


def _json_encode_canonical(obj: Any) -> bytes:
    """Encode a Python object to canonical JSON bytes.

    Uses compact separators and sorted keys for deterministic output,
    which is critical for signature verification -- the same payload
    must produce the same byte sequence every time.

    Args:
        obj: JSON-serializable Python object.

    Returns:
        UTF-8 encoded canonical JSON bytes.
    """
    return json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8")


# ---------------------------------------------------------------------------
# Internal helpers: DID derivation
# ---------------------------------------------------------------------------


def _derive_did(agent_id: str) -> str:
    """Derive a did:eatp DID from an EATP agent ID.

    This is the default DID derivation when no explicit DID is provided.
    Uses the ``did:eatp`` method defined in the EATP DID specification.

    Args:
        agent_id: EATP agent identifier.

    Returns:
        DID string in the format ``did:eatp:<agent_id>``.
    """
    return f"did:eatp:{agent_id}"


# ---------------------------------------------------------------------------
# Internal helpers: validation
# ---------------------------------------------------------------------------


def _validate_signing_key(signing_key: str) -> None:
    """Validate that the signing key is a non-empty, valid base64 Ed25519 key.

    Args:
        signing_key: Base64-encoded Ed25519 private key.

    Raises:
        ValueError: If the key is empty or not valid base64.
    """
    if not signing_key:
        raise ValueError(
            "signing_key must be a non-empty base64-encoded Ed25519 private key. "
            "Generate one with eatp.crypto.generate_keypair()."
        )
    try:
        key_bytes = base64.b64decode(signing_key)
        if len(key_bytes) != 32:
            raise ValueError(
                f"signing_key must decode to exactly 32 bytes for Ed25519, "
                f"got {len(key_bytes)} bytes. Provide a valid Ed25519 private key."
            )
    except Exception as e:
        if "signing_key" in str(e):
            raise
        raise ValueError(
            f"signing_key is not valid base64: {e}. "
            f"Provide a base64-encoded Ed25519 private key."
        ) from e


def _validate_public_key(public_key: str) -> None:
    """Validate that the public key is a non-empty, valid base64 Ed25519 key.

    Args:
        public_key: Base64-encoded Ed25519 public key.

    Raises:
        ValueError: If the key is empty or not valid base64.
    """
    if not public_key:
        raise ValueError(
            "public_key must be a non-empty base64-encoded Ed25519 public key. "
            "Obtain one from eatp.crypto.generate_keypair()."
        )
    try:
        key_bytes = base64.b64decode(public_key)
        if len(key_bytes) != 32:
            raise ValueError(
                f"public_key must decode to exactly 32 bytes for Ed25519, "
                f"got {len(key_bytes)} bytes. Provide a valid Ed25519 public key."
            )
    except Exception as e:
        if "public_key" in str(e):
            raise
        raise ValueError(
            f"public_key is not valid base64: {e}. "
            f"Provide a base64-encoded Ed25519 public key."
        ) from e


# ---------------------------------------------------------------------------
# Internal helpers: Ed25519 signing via PyNaCl
# ---------------------------------------------------------------------------


def _ed25519_sign(message: bytes, private_key_b64: str) -> bytes:
    """Sign a message with Ed25519 using the PyNaCl library.

    Args:
        message: Raw bytes to sign.
        private_key_b64: Base64-encoded 32-byte Ed25519 seed/private key.

    Returns:
        64-byte Ed25519 signature.

    Raises:
        ImportError: If PyNaCl is not installed.
        ValueError: If the private key is invalid.
    """
    try:
        from nacl.signing import SigningKey
    except ImportError as e:
        raise ImportError(
            "PyNaCl is required for UCAN Ed25519 signing. "
            "Install with: pip install pynacl"
        ) from e

    private_key_bytes = base64.b64decode(private_key_b64)
    signing_key = SigningKey(private_key_bytes)
    signed = signing_key.sign(message)
    return signed.signature


def _ed25519_verify(message: bytes, signature: bytes, public_key_b64: str) -> bool:
    """Verify an Ed25519 signature using the PyNaCl library.

    Args:
        message: Original message bytes that were signed.
        signature: 64-byte Ed25519 signature to verify.
        public_key_b64: Base64-encoded 32-byte Ed25519 public key.

    Returns:
        True if the signature is valid.

    Raises:
        ValueError: If signature verification fails.
        ImportError: If PyNaCl is not installed.
    """
    try:
        from nacl.exceptions import BadSignatureError
        from nacl.signing import VerifyKey
    except ImportError as e:
        raise ImportError(
            "PyNaCl is required for UCAN Ed25519 verification. "
            "Install with: pip install pynacl"
        ) from e

    public_key_bytes = base64.b64decode(public_key_b64)
    verify_key = VerifyKey(public_key_bytes)

    try:
        verify_key.verify(message, signature)
        return True
    except BadSignatureError:
        raise ValueError(
            "Signature verification failed: the UCAN token signature does not match "
            "the provided public key. The token may have been tampered with or signed "
            "by a different key."
        )


# ---------------------------------------------------------------------------
# UCAN Payload construction
# ---------------------------------------------------------------------------


def _build_attenuations(
    capabilities: List[str],
    task_id: str,
) -> List[Dict[str, str]]:
    """Build UCAN attenuations from EATP delegated capabilities.

    Maps each EATP capability to a UCAN attenuation with:
    - ``with``: Resource identifier (``eatp:task:<task_id>``)
    - ``can``: Ability namespace (``eatp/<capability>``)

    This mapping follows the UCAN attenuation model where resources
    are scoped to EATP tasks and abilities correspond to EATP capabilities.

    Args:
        capabilities: List of EATP capability strings.
        task_id: EATP task identifier to use as resource scope.

    Returns:
        List of UCAN attenuation dicts with 'with' and 'can' keys.
    """
    resource = f"eatp:task:{task_id}"
    return [{"with": resource, "can": f"eatp/{cap}"} for cap in capabilities]


def _build_facts(
    delegation: "DelegationRecord",
) -> Dict[str, Any]:
    """Build UCAN facts claim from EATP delegation metadata.

    The ``fct`` (facts) claim carries EATP-specific metadata that is
    not represented in standard UCAN claims. This enables full
    round-trip fidelity when importing a UCAN back to a DelegationRecord.

    Args:
        delegation: Source DelegationRecord.

    Returns:
        Dict of EATP fact claims for the fct field.
    """
    return {
        "eatp_delegation_id": delegation.id,
        "eatp_delegator_id": delegation.delegator_id,
        "eatp_delegatee_id": delegation.delegatee_id,
        "eatp_task_id": delegation.task_id,
        "eatp_constraints": delegation.constraint_subset,
        "eatp_delegation_chain": delegation.delegation_chain,
        "eatp_delegation_depth": delegation.delegation_depth,
        "eatp_delegated_at": delegation.delegated_at.isoformat(),
        "eatp_expires_at": (
            delegation.expires_at.isoformat() if delegation.expires_at else None
        ),
        "eatp_parent_delegation_id": delegation.parent_delegation_id,
        "eatp_original_signature": delegation.signature,
        # Reasoning trace extension (confidentiality-filtered)
        **(
            {"eatp_reasoning_trace": delegation.reasoning_trace.to_dict()}
            if delegation.reasoning_trace
            and delegation.reasoning_trace.confidentiality
            <= ConfidentialityLevel.RESTRICTED
            else {}
        ),
        **(
            {"eatp_reasoning_trace_hash": delegation.reasoning_trace_hash}
            if delegation.reasoning_trace_hash
            else {}
        ),
        **(
            {"eatp_reasoning_signature": delegation.reasoning_signature}
            if delegation.reasoning_signature
            else {}
        ),
    }


# ===================================================================
# Public API
# ===================================================================


def to_ucan(
    delegation: "DelegationRecord",
    signing_key: str,
    delegator_did: Optional[str] = None,
    delegatee_did: Optional[str] = None,
) -> str:
    """Export an EATP DelegationRecord as a UCAN v0.10.0 token.

    Produces a three-segment token in the format::

        base64url(header).base64url(payload).base64url(signature)

    The token is signed with Ed25519 (EdDSA) using the provided signing key.

    UCAN claim mapping:

    - ``iss``: DID of the delegator (derived from delegator_id or explicit)
    - ``aud``: DID of the delegatee (derived from delegatee_id or explicit)
    - ``att``: Capabilities as UCAN attenuations (resource + ability)
    - ``exp``: POSIX timestamp of delegation expiry (omitted if no expiry)
    - ``nnc``: Cryptographic nonce for replay protection
    - ``prf``: Empty list (root UCAN -- no parent proofs)
    - ``fct``: EATP metadata (delegation ID, task, constraints, chain info)

    Args:
        delegation: The DelegationRecord to export as a UCAN token.
        signing_key: Base64-encoded Ed25519 private key for signing.
        delegator_did: Optional explicit DID for the issuer. If not provided,
            derived as ``did:eatp:<delegator_id>``.
        delegatee_did: Optional explicit DID for the audience. If not provided,
            derived as ``did:eatp:<delegatee_id>``.

    Returns:
        UCAN v0.10.0 token string.

    Raises:
        ValueError: If signing_key is empty or invalid.
        ImportError: If PyNaCl is not installed.

    Example::

        from eatp.interop.ucan import to_ucan
        from eatp.crypto import generate_keypair

        private_key, public_key = generate_keypair()
        token = to_ucan(delegation, private_key)
    """
    from eatp.chain import DelegationRecord as _DelegationRecord

    _validate_signing_key(signing_key)

    # Resolve DIDs
    iss = delegator_did if delegator_did else _derive_did(delegation.delegator_id)
    aud = delegatee_did if delegatee_did else _derive_did(delegation.delegatee_id)

    # Build payload
    payload: Dict[str, Any] = {
        "iss": iss,
        "aud": aud,
        "att": _build_attenuations(
            delegation.capabilities_delegated, delegation.task_id
        ),
        "nnc": secrets.token_hex(16),
        "prf": [],
        "fct": _build_facts(delegation),
    }

    if delegation.expires_at is not None:
        payload["exp"] = int(delegation.expires_at.timestamp())

    # Encode header and payload
    header_bytes = _json_encode_canonical(UCAN_HEADER)
    payload_bytes = _json_encode_canonical(payload)

    header_b64 = _b64url_encode(header_bytes)
    payload_b64 = _b64url_encode(payload_bytes)

    # Sign the header.payload string
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = _ed25519_sign(signing_input, signing_key)
    signature_b64 = _b64url_encode(signature)

    token = f"{header_b64}.{payload_b64}.{signature_b64}"

    logger.debug(
        "Exported UCAN token for delegation %s -> %s (id=%s, capabilities=%d)",
        delegation.delegator_id,
        delegation.delegatee_id,
        delegation.id,
        len(delegation.capabilities_delegated),
    )

    return token


def from_ucan(
    token: str,
    public_key: str,
) -> "DelegationRecord":
    """Import and verify a UCAN v0.10.0 token, returning an EATP DelegationRecord.

    Performs full verification:
    1. Token structure validation (3 segments, valid base64url)
    2. Header validation (alg=EdDSA, typ=JWT, ucv=0.10.0)
    3. Ed25519 signature verification against the provided public key
    4. Expiration checking (rejects expired tokens)
    5. EATP fact extraction to reconstruct DelegationRecord

    Args:
        token: UCAN v0.10.0 token string.
        public_key: Base64-encoded Ed25519 public key for signature verification.

    Returns:
        Reconstructed DelegationRecord from the UCAN token.

    Raises:
        ValueError: If the token is malformed, signature is invalid,
            token is expired, or required claims are missing.
        ImportError: If PyNaCl is not installed.

    Example::

        from eatp.interop.ucan import from_ucan

        delegation = from_ucan(token, public_key)
        assert delegation.delegator_id == "agent-alpha"
    """
    from eatp.chain import DelegationRecord as _DelegationRecord

    _validate_public_key(public_key)

    # --- Step 1: Validate token structure ---
    if not isinstance(token, str) or token.count(".") != 2:
        raise ValueError(
            "Token must be a string with exactly 3 dot-separated segments "
            "(header.payload.signature). "
            f"Got {token.count('.') + 1 if isinstance(token, str) else 0} segment(s)."
        )

    parts = token.split(".")
    header_b64, payload_b64, signature_b64 = parts[0], parts[1], parts[2]

    # --- Step 2: Decode and validate header ---
    try:
        header_bytes = _b64url_decode(header_b64)
        header = json.loads(header_bytes)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(
            f"Invalid UCAN token: header segment could not be decoded as "
            f"base64url JSON. {e}"
        ) from e

    if header.get("alg") != "EdDSA":
        raise ValueError(
            f"Invalid UCAN header: expected alg='EdDSA', "
            f"got alg='{header.get('alg')}'. "
            f"Only Ed25519 (EdDSA) signing is supported."
        )

    if header.get("typ") != "JWT":
        raise ValueError(
            f"Invalid UCAN header: expected typ='JWT', "
            f"got typ='{header.get('typ')}'."
        )

    ucv = header.get("ucv")
    if ucv != UCAN_VERSION:
        raise ValueError(
            f"Unsupported UCAN version: expected ucv='{UCAN_VERSION}', "
            f"got ucv='{ucv}'. "
            f"This module only supports UCAN v{UCAN_VERSION}."
        )

    # --- Step 3: Verify Ed25519 signature ---
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")

    try:
        signature_bytes = _b64url_decode(signature_b64)
    except ValueError as e:
        raise ValueError(
            f"Invalid UCAN signature segment: could not decode base64url. {e}"
        ) from e

    _ed25519_verify(signing_input, signature_bytes, public_key)

    # --- Step 4: Decode payload ---
    try:
        payload_bytes = _b64url_decode(payload_b64)
        payload = json.loads(payload_bytes)
    except (ValueError, json.JSONDecodeError) as e:
        raise ValueError(
            f"Invalid UCAN payload: could not decode base64url or parse JSON. {e}"
        ) from e

    # --- Step 5: Check expiration ---
    exp = payload.get("exp")
    if exp is not None:
        now_ts = int(datetime.now(timezone.utc).timestamp())
        if exp <= now_ts:
            raise ValueError(
                f"UCAN token has expired: exp={exp} "
                f"({datetime.fromtimestamp(exp, tz=timezone.utc).isoformat()}), "
                f"current time={now_ts} "
                f"({datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()}). "
                f"Expired tokens cannot be used for delegation."
            )

    # --- Step 6: Extract EATP facts and reconstruct DelegationRecord ---
    fct = payload.get("fct")
    if not isinstance(fct, dict):
        raise ValueError(
            "UCAN token is missing the 'fct' (facts) claim or it is not a dict. "
            "This token was not created by an EATP-compatible UCAN exporter."
        )

    required_fct_fields = [
        "eatp_delegation_id",
        "eatp_delegator_id",
        "eatp_delegatee_id",
        "eatp_task_id",
        "eatp_delegated_at",
        "eatp_original_signature",
    ]
    missing_fields = [f for f in required_fct_fields if f not in fct]
    if missing_fields:
        raise ValueError(
            f"UCAN fct claim is missing required EATP fields: {missing_fields}. "
            f"Available fields: {list(fct.keys())}."
        )

    # Parse expiration from fct for the DelegationRecord
    eatp_expires_at = fct.get("eatp_expires_at")
    expires_at = datetime.fromisoformat(eatp_expires_at) if eatp_expires_at else None

    # Reconstruct capabilities from att claim
    att = payload.get("att", [])
    capabilities_delegated = []
    for attenuation in att:
        can = attenuation.get("can", "")
        # Strip the "eatp/" prefix to recover the original capability name
        if can.startswith("eatp/"):
            capabilities_delegated.append(can[5:])
        else:
            capabilities_delegated.append(can)

    # Reasoning trace extension (backward compatible)
    reasoning_trace = None
    if fct.get("eatp_reasoning_trace"):
        from eatp.reasoning import ReasoningTrace

        reasoning_trace = ReasoningTrace.from_dict(fct["eatp_reasoning_trace"])

    delegation = _DelegationRecord(
        id=fct["eatp_delegation_id"],
        delegator_id=fct["eatp_delegator_id"],
        delegatee_id=fct["eatp_delegatee_id"],
        task_id=fct["eatp_task_id"],
        capabilities_delegated=capabilities_delegated,
        constraint_subset=fct.get("eatp_constraints", []),
        delegated_at=datetime.fromisoformat(fct["eatp_delegated_at"]),
        expires_at=expires_at,
        signature=fct["eatp_original_signature"],
        parent_delegation_id=fct.get("eatp_parent_delegation_id"),
        delegation_chain=fct.get("eatp_delegation_chain", []),
        delegation_depth=fct.get("eatp_delegation_depth", 0),
        reasoning_trace=reasoning_trace,
        reasoning_trace_hash=fct.get("eatp_reasoning_trace_hash"),
        reasoning_signature=fct.get("eatp_reasoning_signature"),
    )

    logger.debug(
        "Imported UCAN token: delegation %s -> %s (id=%s, capabilities=%d)",
        delegation.delegator_id,
        delegation.delegatee_id,
        delegation.id,
        len(delegation.capabilities_delegated),
    )

    return delegation
