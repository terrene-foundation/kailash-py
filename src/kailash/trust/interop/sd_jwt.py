# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP SD-JWT Selective Disclosure -- Export EATP records with selective claim disclosure.

Implements the IETF SD-JWT specification (draft-ietf-oauth-selective-disclosure-jwt)
for EATP trust chains and capability attestations.  Allows holders to present
only a subset of claims to verifiers while maintaining cryptographic integrity.

The implementation uses Ed25519 signing from ``eatp.crypto`` and does NOT depend
on any external SD-JWT library.  All encoding, hashing, and disclosure logic is
built from standard library primitives (base64, hashlib, json, secrets).

Key concepts:

- **Disclosure**: A base64url-encoded JSON array ``[salt, claim_name, claim_value]``
  that reveals a single claim.  Only disclosures included in the combined token
  are visible to the verifier.
- **_sd array**: The JWT payload contains an ``_sd`` array of SHA-256 hashes
  (base64url-encoded) -- one per selectively disclosable claim.  The verifier
  matches disclosure hashes against this array.
- **Combined format**: ``<JWT>~<disc1>~<disc2>~...~`` -- the JWT followed by
  tilde-separated disclosures and a trailing tilde.

Usage::

    from kailash.trust.interop.sd_jwt import create_sd_jwt, verify_sd_jwt

    token = create_sd_jwt(
        claims={"name": "agent-001", "role": "analyst", "secret": "x"},
        signing_key=private_key,
        disclosed_claims=["name", "role"],
        always_visible=["name"],
    )
    result = verify_sd_jwt(token, public_key)
    # result contains only the claims revealed by disclosures + always_visible
"""

import base64
import copy
import hashlib
import json
import logging
import secrets
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from nacl.exceptions import BadSignatureError
    from nacl.signing import SigningKey, VerifyKey

    NACL_AVAILABLE = True
except ImportError:
    NACL_AVAILABLE = False
    SigningKey = None  # type: ignore[assignment, misc]
    VerifyKey = None  # type: ignore[assignment, misc]
    BadSignatureError = Exception  # type: ignore[assignment, misc]

from kailash.trust.chain import CapabilityAttestation, TrustLineageChain
from kailash.trust.signing.crypto import hash_reasoning_trace
from kailash.trust.exceptions import InvalidSignatureError
from kailash.trust.reasoning.traces import ConfidentialityLevel, ReasoningTrace

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _b64url_encode_bytes(data: bytes) -> str:
    """Base64url-encode bytes with no padding (per RFC 7515)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode_str(s: str) -> bytes:
    """Base64url-decode a string, adding padding as needed."""
    padded = s + "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(padded)


def _b64url_encode_json(obj: Any) -> str:
    """JSON-serialize then base64url-encode an object."""
    json_bytes = json.dumps(obj, separators=(",", ":"), sort_keys=False).encode("utf-8")
    return _b64url_encode_bytes(json_bytes)


def _generate_salt() -> str:
    """Generate a 128-bit random salt encoded as base64url."""
    return _b64url_encode_bytes(secrets.token_bytes(16))


def _hash_disclosure(disclosure_b64: str) -> str:
    """Compute SHA-256 hash of a disclosure string, returned as base64url (no padding)."""
    digest = hashlib.sha256(disclosure_b64.encode("ascii")).digest()
    return _b64url_encode_bytes(digest)


def _create_disclosure(claim_name: str, claim_value: Any) -> tuple[str, str]:
    """Create a single disclosure for a claim.

    Returns:
        Tuple of (base64url_disclosure_string, sha256_hash_of_disclosure).
    """
    salt = _generate_salt()
    disclosure_array = [salt, claim_name, claim_value]
    disclosure_b64 = _b64url_encode_json(disclosure_array)
    disclosure_hash = _hash_disclosure(disclosure_b64)
    return disclosure_b64, disclosure_hash


def _ed25519_sign(payload_bytes: bytes, private_key_b64: str) -> bytes:
    """Sign bytes with Ed25519 private key, returning raw 64-byte signature."""
    if not NACL_AVAILABLE:
        raise ImportError(
            "PyNaCl is required for SD-JWT signing. Install with: pip install pynacl"
        )
    private_key_bytes = base64.b64decode(private_key_b64)
    signing_key = SigningKey(private_key_bytes)  # type: ignore[misc]
    signed = signing_key.sign(payload_bytes)
    return signed.signature


def _ed25519_verify(
    payload_bytes: bytes, signature_bytes: bytes, public_key_b64: str
) -> None:
    """Verify Ed25519 signature.  Raises on failure."""
    if not NACL_AVAILABLE:
        raise ImportError(
            "PyNaCl is required for SD-JWT verification. Install with: pip install pynacl"
        )
    public_key_bytes = base64.b64decode(public_key_b64)
    verify_key = VerifyKey(public_key_bytes)  # type: ignore[misc]
    try:
        verify_key.verify(payload_bytes, signature_bytes)
    except BadSignatureError as exc:
        raise InvalidSignatureError(
            f"SD-JWT signature verification failed: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Serialization helpers for EATP types
# ---------------------------------------------------------------------------


def _serialize_chain_claims(chain: TrustLineageChain) -> Dict[str, Any]:
    """Convert a TrustLineageChain to flat claims dict for SD-JWT."""
    chain_dict = chain.to_dict()
    return chain_dict


def _serialize_capability_claims(attestation: CapabilityAttestation) -> Dict[str, Any]:
    """Convert a CapabilityAttestation to flat claims dict for SD-JWT."""
    return {
        "id": attestation.id,
        "capability": attestation.capability,
        "capability_type": attestation.capability_type.value,
        "constraints": attestation.constraints,
        "attester_id": attestation.attester_id,
        "attested_at": attestation.attested_at.isoformat(),
        "expires_at": (
            attestation.expires_at.isoformat() if attestation.expires_at else None
        ),
        "signature": attestation.signature,
        "scope": attestation.scope,
    }


# ===================================================================
# Public API
# ===================================================================


def create_sd_jwt(
    claims: Dict[str, Any],
    signing_key: str,
    disclosed_claims: List[str],
    always_visible: Optional[List[str]] = None,
) -> str:
    """Create an SD-JWT with selectively disclosable claims.

    Builds a JWT whose payload contains an ``_sd`` array of SHA-256 hashes
    (one per selectively disclosable claim).  Claims listed in
    ``disclosed_claims`` are additionally emitted as tilde-separated
    disclosures appended to the JWT.  Claims in ``always_visible`` are
    placed directly in the JWT payload (never hashed).

    Args:
        claims: Dictionary of claim name -> claim value.
        signing_key: Base64-encoded Ed25519 private key.
        disclosed_claims: Claim names whose disclosures are included in the
            combined token (the verifier will see these).
        always_visible: Claim names placed directly in the JWT payload,
            never hashed into ``_sd``.  Defaults to empty list.

    Returns:
        SD-JWT combined format string: ``<JWT>~<disc1>~<disc2>~...~``

    Raises:
        ValueError: If signing_key is empty, claims is empty, or a requested
            claim does not exist in the claims dict.
        ImportError: If PyNaCl is not installed.
    """
    if not signing_key:
        raise ValueError(
            "signing_key must be a non-empty string. Provide a base64-encoded Ed25519 private key."
        )
    if not claims:
        raise ValueError(
            "claims must be a non-empty dictionary. Provide at least one claim for the SD-JWT."
        )

    if always_visible is None:
        always_visible = []

    # Validate that all disclosed_claims exist in claims
    for claim_name in disclosed_claims:
        if claim_name not in claims:
            raise ValueError(
                f"Disclosed claim '{claim_name}' not found in claims. Available claims: {sorted(claims.keys())}"
            )

    # Validate that all always_visible exist in claims
    for claim_name in always_visible:
        if claim_name not in claims:
            raise ValueError(
                f"Always-visible claim '{claim_name}' not found in claims. Available claims: {sorted(claims.keys())}"
            )

    # Separate claims into categories
    always_visible_set = set(always_visible)
    disclosed_set = set(disclosed_claims)

    # Build the JWT payload
    payload: Dict[str, Any] = {
        "_sd_alg": "sha-256",
    }

    # Add always_visible claims directly to payload
    for name in always_visible:
        payload[name] = claims[name]

    # Build _sd array and disclosures
    sd_hashes: List[str] = []
    disclosures: List[str] = []

    # Process all claims that are NOT always_visible
    # Every non-visible claim gets a disclosure and hash; only disclosed_claims
    # have their disclosure included in the combined token
    for claim_name, claim_value in claims.items():
        if claim_name in always_visible_set:
            continue

        # Create disclosure for this claim
        disc_b64, disc_hash = _create_disclosure(claim_name, claim_value)
        sd_hashes.append(disc_hash)

        # Only include the disclosure in the combined format if it's in disclosed_claims
        if claim_name in disclosed_set:
            disclosures.append(disc_b64)

    payload["_sd"] = sd_hashes

    # Build the JWT: header.payload.signature
    header = {"alg": "EdDSA", "typ": "sd+jwt"}

    header_b64 = _b64url_encode_json(header)
    payload_b64 = _b64url_encode_json(payload)

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature_bytes = _ed25519_sign(signing_input, signing_key)
    signature_b64 = _b64url_encode_bytes(signature_bytes)

    jwt_token = f"{header_b64}.{payload_b64}.{signature_b64}"

    # Combined format: JWT~disc1~disc2~...~
    combined = jwt_token + "~" + "~".join(disclosures) + "~"

    logger.debug(
        "Created SD-JWT with %d disclosures (%d claims total, %d always-visible)",
        len(disclosures),
        len(claims),
        len(always_visible),
    )

    return combined


def verify_sd_jwt(token: str, public_key: str) -> Dict[str, Any]:
    """Verify an SD-JWT and return the disclosed claims.

    Performs Ed25519 signature verification on the JWT portion, then
    processes each disclosure:

    1. Decode the disclosure to ``[salt, claim_name, claim_value]``
    2. Compute its SHA-256 hash
    3. Verify the hash exists in the JWT's ``_sd`` array
    4. Add the claim to the result

    Claims placed directly in the JWT payload (``always_visible``) are
    included in the result automatically.  The ``_sd``, ``_sd_alg``
    metadata keys are excluded from the result.

    Args:
        token: SD-JWT combined format string.
        public_key: Base64-encoded Ed25519 public key.

    Returns:
        Dictionary of disclosed + always-visible claims.

    Raises:
        ValueError: If the token is malformed, a disclosure hash does not
            match the ``_sd`` array, or the public_key is empty.
        InvalidSignatureError: If the JWT signature is invalid.
        ImportError: If PyNaCl is not installed.
    """
    if not public_key:
        raise ValueError(
            "public_key must be a non-empty string. Provide a base64-encoded Ed25519 public key."
        )

    if not token or "~" not in token:
        raise ValueError(
            "Invalid SD-JWT token format. Expected combined format: <JWT>~<disc1>~...~"
        )

    # Split into JWT and disclosures
    parts = token.split("~")
    jwt_part = parts[0]
    disclosure_strings = [p for p in parts[1:] if p]

    # Parse and verify the JWT
    jwt_segments = jwt_part.split(".")
    if len(jwt_segments) != 3:
        raise ValueError(
            f"Invalid JWT format: expected 3 segments (header.payload.signature), got {len(jwt_segments)}"
        )

    header_b64, payload_b64, signature_b64 = jwt_segments

    # Verify signature
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature_bytes = _b64url_decode_str(signature_b64)
    _ed25519_verify(signing_input, signature_bytes, public_key)

    # Decode payload
    payload = json.loads(_b64url_decode_str(payload_b64))

    sd_hashes = set(payload.get("_sd", []))

    # Process disclosures
    result: Dict[str, Any] = {}

    for disc_str in disclosure_strings:
        # Verify disclosure hash matches an entry in _sd
        disc_hash = _hash_disclosure(disc_str)
        if disc_hash not in sd_hashes:
            raise ValueError(
                f"Disclosure hash mismatch: computed hash '{disc_hash}' "
                f"not found in _sd array. The disclosure may have been tampered with."
            )

        # Decode disclosure: [salt, claim_name, claim_value]
        disc_bytes = _b64url_decode_str(disc_str)
        disclosure = json.loads(disc_bytes)

        if not isinstance(disclosure, list) or len(disclosure) != 3:
            raise ValueError(
                f"Invalid disclosure format: expected [salt, name, value], "
                f"got {type(disclosure).__name__} with {len(disclosure) if isinstance(disclosure, list) else 'N/A'} elements"
            )

        _salt, claim_name, claim_value = disclosure
        result[claim_name] = claim_value

    # Add always-visible claims from payload (everything except _sd metadata)
    _metadata_keys = {"_sd", "_sd_alg"}
    for key, value in payload.items():
        if key not in _metadata_keys:
            result[key] = value

    logger.debug(
        "Verified SD-JWT: %d claims from disclosures, %d from payload",
        len(disclosure_strings),
        sum(1 for k in payload if k not in _metadata_keys),
    )

    return result


def export_chain_as_sd_jwt(
    chain: TrustLineageChain,
    signing_key: str,
    disclosed_claims: List[str],
) -> str:
    """Export a TrustLineageChain as an SD-JWT with selective disclosure.

    Serializes the chain via ``chain.to_dict()`` and creates an SD-JWT
    where each top-level key (``genesis``, ``capabilities``,
    ``delegations``, ``constraint_envelope``, ``chain_hash``) is a
    selectively disclosable claim.

    Args:
        chain: The TrustLineageChain to export.
        signing_key: Base64-encoded Ed25519 private key.
        disclosed_claims: Which top-level chain fields to disclose
            (e.g., ``["genesis", "capabilities"]``).

    Returns:
        SD-JWT combined format string.

    Raises:
        ValueError: If signing_key is empty or a disclosed claim is invalid.
        ImportError: If PyNaCl is not installed.
    """
    claims = _serialize_chain_claims(chain)

    logger.debug(
        "Exporting trust chain for agent=%s as SD-JWT with %d disclosed claims",
        chain.genesis.agent_id,
        len(disclosed_claims),
    )

    return create_sd_jwt(
        claims=claims,
        signing_key=signing_key,
        disclosed_claims=disclosed_claims,
    )


def export_capability_as_sd_jwt(
    attestation: CapabilityAttestation,
    signing_key: str,
    disclosed_claims: List[str],
) -> str:
    """Export a CapabilityAttestation as an SD-JWT with selective disclosure.

    Serializes the attestation to a flat claims dict and creates an
    SD-JWT where each field (``id``, ``capability``, ``constraints``,
    ``scope``, etc.) is a selectively disclosable claim.

    Args:
        attestation: The CapabilityAttestation to export.
        signing_key: Base64-encoded Ed25519 private key.
        disclosed_claims: Which capability fields to disclose
            (e.g., ``["capability", "scope"]``).

    Returns:
        SD-JWT combined format string.

    Raises:
        ValueError: If signing_key is empty or a disclosed claim is invalid.
        ImportError: If PyNaCl is not installed.
    """
    claims = _serialize_capability_claims(attestation)

    logger.debug(
        "Exporting capability '%s' (id=%s) as SD-JWT with %d disclosed claims",
        attestation.capability,
        attestation.id,
        len(disclosed_claims),
    )

    return create_sd_jwt(
        claims=claims,
        signing_key=signing_key,
        disclosed_claims=disclosed_claims,
    )


# ---------------------------------------------------------------------------
# Confidentiality-driven reasoning trace helpers
# ---------------------------------------------------------------------------


def _apply_reasoning_confidentiality(
    delegation_dict: Dict[str, Any],
    disclose_reasoning: bool,
) -> Dict[str, Any]:
    """Apply confidentiality-driven disclosure rules to a single delegation dict.

    Transforms the reasoning_trace fields in a delegation dictionary based on
    the confidentiality level of the reasoning trace:

    - **PUBLIC**: Reasoning trace remains fully intact (all fields visible).
    - **RESTRICTED**: Reasoning trace is hidden by default (removed, hash kept).
      When ``disclose_reasoning`` is True, the full trace is included.
    - **CONFIDENTIAL**: Reasoning trace is hidden by default (removed, hash kept).
      When ``disclose_reasoning`` is True, the trace is included but
      ``alternatives_considered`` is stripped.
    - **SECRET / TOP_SECRET**: Reasoning trace is permanently stripped. Only
      ``reasoning_trace_hash`` is included. ``disclose_reasoning`` has no effect.

    Args:
        delegation_dict: A serialized delegation record (mutable dict).
        disclose_reasoning: Whether the holder requests reasoning disclosure.

    Returns:
        The (possibly mutated) delegation dict.
    """
    reasoning_data = delegation_dict.get("reasoning_trace")
    if reasoning_data is None:
        # No reasoning trace on this delegation -- nothing to do
        return delegation_dict

    # Determine confidentiality level from the serialized trace
    confidentiality_str = reasoning_data.get("confidentiality")
    if confidentiality_str is None:
        raise ValueError(
            "reasoning_trace is missing 'confidentiality' field. "
            "Cannot determine disclosure policy for delegation "
            f"'{delegation_dict.get('id', '<unknown>')}'."
        )

    try:
        level = ConfidentialityLevel(confidentiality_str)
    except ValueError:
        raise ValueError(
            f"Unknown confidentiality level '{confidentiality_str}' "
            f"in reasoning_trace for delegation '{delegation_dict.get('id', '<unknown>')}'. "
            f"Valid levels: {[lv.value for lv in ConfidentialityLevel]}"
        )

    # Compute hash if not already present -- needed for all non-PUBLIC levels
    if (
        "reasoning_trace_hash" not in delegation_dict
        or delegation_dict["reasoning_trace_hash"] is None
    ):
        trace_obj = ReasoningTrace.from_dict(reasoning_data)
        delegation_dict["reasoning_trace_hash"] = hash_reasoning_trace(trace_obj)

    # --- Apply policy ---

    if level == ConfidentialityLevel.PUBLIC:
        # PUBLIC: full trace visible, nothing to strip
        return delegation_dict

    if level in (ConfidentialityLevel.SECRET, ConfidentialityLevel.TOP_SECRET):
        # SECRET / TOP_SECRET: trace always stripped, only hash survives
        delegation_dict.pop("reasoning_trace", None)
        delegation_dict.pop("reasoning_signature", None)
        return delegation_dict

    # RESTRICTED or CONFIDENTIAL
    if not disclose_reasoning:
        # Hidden by default -- remove trace, keep hash
        delegation_dict.pop("reasoning_trace", None)
        delegation_dict.pop("reasoning_signature", None)
        return delegation_dict

    # Disclosed: include trace (possibly redacted for CONFIDENTIAL)
    if level == ConfidentialityLevel.CONFIDENTIAL:
        # Strip alternatives_considered at CONFIDENTIAL level (copy to avoid mutation)
        delegation_dict["reasoning_trace"] = {
            k: v
            for k, v in delegation_dict["reasoning_trace"].items()
            if k != "alternatives_considered"
        }

    return delegation_dict


def create_reasoning_sd_jwt(
    chain: TrustLineageChain,
    signing_key: str,
    disclosed_claims: List[str],
    disclose_reasoning: bool = False,
) -> str:
    """Create an SD-JWT for a TrustLineageChain with confidentiality-driven reasoning disclosure.

    Serializes the chain and applies per-delegation confidentiality rules to
    reasoning traces before building the SD-JWT.  The confidentiality level
    on each delegation's reasoning trace determines which fields survive:

    - **PUBLIC**: All reasoning fields are included in the claims.
    - **RESTRICTED**: Reasoning trace is hidden by default; only
      ``reasoning_trace_hash`` is visible.  Pass ``disclose_reasoning=True``
      to include the full trace.
    - **CONFIDENTIAL**: Same as RESTRICTED, but when disclosed the
      ``alternatives_considered`` field is stripped from the trace.
    - **SECRET / TOP_SECRET**: Only ``reasoning_trace_hash`` is included.
      ``disclose_reasoning`` has no effect -- the trace is never included.

    Delegations without reasoning traces are unaffected.

    Token size note: Reasoning traces can be verbose. If the resulting SD-JWT
    exceeds ~8 KB (the practical limit for JWT in HTTP headers), consider
    storing the full trace externally and referencing it via
    ``reasoning_trace_hash``.

    Args:
        chain: The TrustLineageChain to export.
        signing_key: Base64-encoded Ed25519 private key.
        disclosed_claims: Which top-level chain fields to disclose
            (e.g., ``["genesis", "delegations"]``).
        disclose_reasoning: If True, include reasoning traces for RESTRICTED
            and CONFIDENTIAL delegations.  Has no effect on PUBLIC (always
            included) or SECRET/TOP_SECRET (never included).  Default: False.

    Returns:
        SD-JWT combined format string.

    Raises:
        ValueError: If signing_key is empty, a disclosed claim is invalid,
            or a reasoning trace has an unknown confidentiality level.
        ImportError: If PyNaCl is not installed.
    """
    # Serialize chain to claims dict
    claims = _serialize_chain_claims(chain)

    # Deep-copy delegations so we don't mutate the chain's cached dict
    if "delegations" in claims:
        claims["delegations"] = copy.deepcopy(claims["delegations"])
        for deleg_dict in claims["delegations"]:
            _apply_reasoning_confidentiality(deleg_dict, disclose_reasoning)

    logger.debug(
        "Creating reasoning SD-JWT for agent=%s with disclose_reasoning=%s, %d disclosed claims",
        chain.genesis.agent_id,
        disclose_reasoning,
        len(disclosed_claims),
    )

    return create_sd_jwt(
        claims=claims,
        signing_key=signing_key,
        disclosed_claims=disclosed_claims,
    )
