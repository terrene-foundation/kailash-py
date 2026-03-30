# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP Cryptographic Utilities.

Provides Ed25519 signing and verification for trust chain integrity.
Uses PyNaCl for cryptographic operations.
"""

import base64
import hashlib
import json
import secrets
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, Tuple, Union

try:
    from nacl.exceptions import BadSignatureError
    from nacl.signing import SigningKey, VerifyKey

    NACL_AVAILABLE = True
except ImportError:
    NACL_AVAILABLE = False
    SigningKey = None
    VerifyKey = None
    BadSignatureError = Exception

from kailash.trust.exceptions import InvalidSignatureError
from kailash.trust.reasoning.traces import ReasoningTrace

# Salt configuration for CARE-001
SALT_LENGTH = 32  # 256 bits for cryptographic security


def generate_keypair() -> Tuple[str, str]:
    """
    Generate an Ed25519 key pair for signing.

    Returns:
        Tuple of (private_key_base64, public_key_base64)

    Raises:
        ImportError: If PyNaCl is not installed

    Example:
        >>> private_key, public_key = generate_keypair()
        >>> len(private_key) > 0
        True
    """
    if not NACL_AVAILABLE:
        raise ImportError(
            "PyNaCl is required for cryptographic operations. Install with: pip install pynacl"
        )

    signing_key = SigningKey.generate()  # type: ignore[union-attr]
    private_key_bytes = bytes(signing_key)
    public_key_bytes = bytes(signing_key.verify_key)

    return (
        base64.b64encode(private_key_bytes).decode("utf-8"),
        base64.b64encode(public_key_bytes).decode("utf-8"),
    )


def generate_salt() -> bytes:
    """
    Generate cryptographically secure random salt.

    Returns:
        Random bytes of SALT_LENGTH (32 bytes / 256 bits)

    Example:
        >>> salt = generate_salt()
        >>> len(salt) == 32
        True
    """
    return secrets.token_bytes(SALT_LENGTH)


def derive_key_with_salt(
    master_key: bytes,
    salt: bytes,
    key_length: int = 32,
    iterations: int = 100000,
) -> Tuple[bytes, bytes]:
    """
    Derive key using PBKDF2-HMAC-SHA256 with per-key salt.

    This is the CARE-001 secure key derivation function that replaces
    static salt usage with per-key random salts.

    Args:
        master_key: Master key bytes
        salt: Per-key random salt (should be 32 bytes)
        key_length: Desired key length in bytes (default: 32)
        iterations: PBKDF2 iteration count (default: 100000)

    Returns:
        Tuple of (derived_key, salt_used)

    Example:
        >>> salt = generate_salt()
        >>> key, used_salt = derive_key_with_salt(b"master", salt)
        >>> len(key) == 32
        True
    """
    derived_key = hashlib.pbkdf2_hmac(
        "sha256",
        master_key,
        salt,
        iterations,
        dklen=key_length,
    )
    return derived_key, salt


def sign(payload: Union[bytes, str, dict], private_key: str) -> str:
    """
    Sign a payload with Ed25519 private key.

    Args:
        payload: Data to sign (bytes, string, or dict)
        private_key: Base64-encoded private key

    Returns:
        Base64-encoded signature

    Raises:
        ImportError: If PyNaCl is not installed
        ValueError: If private key is invalid

    Example:
        >>> private_key, public_key = generate_keypair()
        >>> signature = sign({"action": "test"}, private_key)
        >>> len(signature) > 0
        True
    """
    if not NACL_AVAILABLE:
        raise ImportError(
            "PyNaCl is required for cryptographic operations. Install with: pip install pynacl"
        )

    # Convert payload to bytes
    if isinstance(payload, dict):
        payload_bytes = serialize_for_signing(payload).encode("utf-8")
    elif isinstance(payload, str):
        payload_bytes = payload.encode("utf-8")
    else:
        payload_bytes = payload

    # Decode private key
    try:
        private_key_bytes = base64.b64decode(private_key)
        signing_key = SigningKey(private_key_bytes)  # type: ignore[misc]
    except Exception as e:
        raise ValueError(f"Invalid private key: {e}")

    # Sign
    signed = signing_key.sign(payload_bytes)
    signature = signed.signature

    return base64.b64encode(signature).decode("utf-8")


def verify_signature(
    payload: Union[bytes, str, dict], signature: str, public_key: str
) -> bool:
    """
    Verify an Ed25519 signature.

    Args:
        payload: Original data that was signed
        signature: Base64-encoded signature
        public_key: Base64-encoded public key

    Returns:
        True if signature is valid, False otherwise

    Raises:
        ImportError: If PyNaCl is not installed
        InvalidSignatureError: If signature verification fails with error

    Example:
        >>> private_key, public_key = generate_keypair()
        >>> signature = sign("test", private_key)
        >>> verify_signature("test", signature, public_key)
        True
        >>> verify_signature("tampered", signature, public_key)
        False
    """
    if not NACL_AVAILABLE:
        raise ImportError(
            "PyNaCl is required for cryptographic operations. Install with: pip install pynacl"
        )

    # Convert payload to bytes
    if isinstance(payload, dict):
        payload_bytes = serialize_for_signing(payload).encode("utf-8")
    elif isinstance(payload, str):
        payload_bytes = payload.encode("utf-8")
    else:
        payload_bytes = payload

    try:
        # Decode signature and public key
        signature_bytes = base64.b64decode(signature)
        public_key_bytes = base64.b64decode(public_key)
        verify_key = VerifyKey(public_key_bytes)  # type: ignore[misc]

        # Verify
        verify_key.verify(payload_bytes, signature_bytes)
        return True

    except BadSignatureError:
        return False
    except Exception as e:
        raise InvalidSignatureError(f"Signature verification error: {e}")


def serialize_for_signing(obj: Any) -> str:
    """
    Serialize an object for signing in a deterministic way.

    Converts dataclasses, dicts, and other types to a canonical JSON string
    that will produce the same output for equivalent inputs.

    Args:
        obj: Object to serialize (dataclass, dict, or primitive)

    Returns:
        Canonical JSON string

    Example:
        >>> serialize_for_signing({"b": 2, "a": 1})
        '{"a":1,"b":2}'
    """

    def convert(item: Any) -> Any:
        """Recursively convert objects to JSON-serializable types."""
        if is_dataclass(item) and not isinstance(item, type):
            return convert(asdict(item))
        elif isinstance(item, dict):
            return {k: convert(v) for k, v in sorted(item.items())}
        elif isinstance(item, (frozenset, set)):
            return [convert(i) for i in sorted(item)]
        elif isinstance(item, (list, tuple)):
            return [convert(i) for i in item]
        elif isinstance(item, datetime):
            return item.isoformat()
        elif isinstance(item, Enum):
            return item.value
        elif isinstance(item, bytes):
            return base64.b64encode(item).decode("utf-8")
        else:
            return item

    converted = convert(obj)
    return json.dumps(converted, separators=(",", ":"), sort_keys=True)


def hash_chain(data: Union[str, dict, bytes]) -> str:
    """
    Compute SHA-256 hash of data for trust chain integrity.

    Args:
        data: Data to hash (string, dict, or bytes)

    Returns:
        Hex-encoded SHA-256 hash

    Example:
        >>> hash_chain({"id": "test"})
        'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'[:64]
    """
    if isinstance(data, dict):
        data_bytes = serialize_for_signing(data).encode("utf-8")
    elif isinstance(data, str):
        data_bytes = data.encode("utf-8")
    else:
        data_bytes = data

    return hashlib.sha256(data_bytes).hexdigest()


def hash_trust_chain_state(
    genesis_id: str, capability_ids: list, delegation_ids: list, constraint_hash: str
) -> str:
    """
    Compute hash of current trust chain state.

    This hash changes when any component of the trust chain changes,
    enabling quick verification of chain integrity.

    Args:
        genesis_id: ID of the genesis record
        capability_ids: List of capability attestation IDs
        delegation_ids: List of delegation record IDs
        constraint_hash: Hash of constraint envelope

    Returns:
        Hex-encoded SHA-256 hash of trust chain state

    Example:
        >>> hash_trust_chain_state("gen-001", ["cap-001"], [], "abc123")
        # Returns deterministic hash
    """
    state = {
        "genesis_id": genesis_id,
        "capability_ids": sorted(capability_ids),
        "delegation_ids": sorted(delegation_ids),
        "constraint_hash": constraint_hash,
    }
    return hash_chain(state)


def hash_trust_chain_state_salted(
    genesis_id: str,
    capability_ids: list,
    delegation_ids: list,
    constraint_hash: str,
    previous_state_hash: Optional[str] = None,
    salt: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Compute salted hash of trust chain state (CARE-001).

    Enhanced version that includes per-chain salt and optional
    previous state hash for linked hashing. This provides protection
    against rainbow table attacks and enables chain linking.

    Args:
        genesis_id: ID of the genesis record
        capability_ids: List of capability attestation IDs
        delegation_ids: List of delegation record IDs
        constraint_hash: Hash of constraint envelope
        previous_state_hash: Previous chain state hash (for linking)
        salt: Base64-encoded salt (auto-generated if None)

    Returns:
        Tuple of (hash_hex, salt_base64)

    Example:
        >>> hash_hex, salt_b64 = hash_trust_chain_state_salted(
        ...     "gen-001", ["cap-001"], [], "abc123"
        ... )
        >>> len(hash_hex) == 64
        True
    """
    if salt is None:
        salt = base64.b64encode(generate_salt()).decode("utf-8")

    state = {
        "genesis_id": genesis_id,
        "capability_ids": sorted(capability_ids),
        "delegation_ids": sorted(delegation_ids),
        "constraint_hash": constraint_hash,
        "salt": salt,
    }

    if previous_state_hash is not None:
        state["previous_state_hash"] = previous_state_hash

    return hash_chain(state), salt


def hash_reasoning_trace(trace: ReasoningTrace) -> str:
    """
    Compute SHA-256 hash of a reasoning trace's signing payload.

    Uses the trace's deterministic signing payload (sorted keys, serialized
    enum/datetime values) for canonical representation, then computes the
    SHA-256 hash of the serialized payload.

    Args:
        trace: ReasoningTrace instance to hash

    Returns:
        Hex-encoded SHA-256 hash string (64 characters)

    Example:
        >>> from kailash.trust.reasoning.traces import ReasoningTrace, ConfidentialityLevel
        >>> from datetime import datetime, timezone
        >>> trace = ReasoningTrace(
        ...     decision="approve", rationale="valid",
        ...     confidentiality=ConfidentialityLevel.PUBLIC,
        ...     timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ... )
        >>> len(hash_reasoning_trace(trace)) == 64
        True
    """
    payload = trace.to_signing_payload()
    serialized = serialize_for_signing(payload)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def sign_reasoning_trace(
    trace: ReasoningTrace, private_key: str, context_id: Optional[str] = None
) -> str:
    """
    Sign a reasoning trace using an agent's Ed25519 private key.

    Uses the trace's deterministic signing payload as the data to sign,
    producing a signature that is SEPARATE from the parent record's
    signature (backward compatible).

    Args:
        trace: ReasoningTrace instance to sign
        private_key: Base64-encoded Ed25519 private key
        context_id: Optional parent record ID to bind the signature to.
            When provided, the signed payload includes the parent record ID,
            preventing signature transplant attacks.

    Returns:
        Base64-encoded Ed25519 signature string

    Raises:
        ImportError: If PyNaCl is not installed
        ValueError: If private key is invalid

    Example:
        >>> from kailash.trust.signing.crypto import generate_keypair
        >>> private_key, public_key = generate_keypair()
        >>> from kailash.trust.reasoning.traces import ReasoningTrace, ConfidentialityLevel
        >>> from datetime import datetime, timezone
        >>> trace = ReasoningTrace(
        ...     decision="approve", rationale="valid",
        ...     confidentiality=ConfidentialityLevel.PUBLIC,
        ...     timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ... )
        >>> sig = sign_reasoning_trace(trace, private_key)
        >>> len(sig) > 0
        True
    """
    payload = trace.to_signing_payload()
    if context_id is not None:
        payload = {"parent_record_id": context_id, "reasoning": payload}
    return sign(payload, private_key)


def verify_reasoning_signature(
    trace: ReasoningTrace,
    signature: str,
    public_key: str,
    context_id: Optional[str] = None,
) -> bool:
    """
    Verify a reasoning trace's Ed25519 signature.

    Reconstructs the signing payload from the trace and verifies
    that the signature matches using the provided public key.

    Args:
        trace: ReasoningTrace instance to verify against
        signature: Base64-encoded Ed25519 signature
        public_key: Base64-encoded Ed25519 public key
        context_id: Optional parent record ID that the signature is bound to.
            Must match the context_id used during signing.

    Returns:
        True if the signature is valid for this trace, False otherwise

    Raises:
        ImportError: If PyNaCl is not installed
        InvalidSignatureError: If verification encounters an unexpected error

    Example:
        >>> from kailash.trust.signing.crypto import generate_keypair
        >>> private_key, public_key = generate_keypair()
        >>> from kailash.trust.reasoning.traces import ReasoningTrace, ConfidentialityLevel
        >>> from datetime import datetime, timezone
        >>> trace = ReasoningTrace(
        ...     decision="approve", rationale="valid",
        ...     confidentiality=ConfidentialityLevel.PUBLIC,
        ...     timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ... )
        >>> sig = sign_reasoning_trace(trace, private_key)
        >>> verify_reasoning_signature(trace, sig, public_key)
        True
    """
    payload = trace.to_signing_payload()
    if context_id is not None:
        payload = {"parent_record_id": context_id, "reasoning": payload}
    return verify_signature(payload, signature, public_key)


# ---------------------------------------------------------------------------
# Dual Signature System (Phase 5 G6)
# ---------------------------------------------------------------------------


@dataclass
class DualSignature:
    """Dual signature: Ed25519 (mandatory) + optional HMAC-SHA256.

    Ed25519 is the primary signature for external/compliance verification.
    HMAC is an optional fast-path for internal verification between trusted
    services sharing a symmetric key.

    HMAC is never sufficient alone for external verification. Document this clearly.
    """

    ed25519_signature: str  # Base64-encoded Ed25519 signature (always present)
    hmac_signature: Optional[str] = None  # Base64-encoded HMAC-SHA256 (optional)
    hmac_algorithm: str = "sha256"

    @property
    def has_hmac(self) -> bool:
        """Return True if an HMAC signature is present."""
        return self.hmac_signature is not None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict. Omits hmac_signature when None."""
        result: Dict[str, Any] = {
            "ed25519_signature": self.ed25519_signature,
            "hmac_algorithm": self.hmac_algorithm,
        }
        if self.hmac_signature is not None:
            result["hmac_signature"] = self.hmac_signature
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DualSignature":
        """Reconstruct from dict.

        Raises:
            KeyError: If ``ed25519_signature`` key is missing.
            ValueError: If ``ed25519_signature`` is not a non-empty string,
                or ``hmac_algorithm`` is not in the allowed set.
        """
        ed25519_sig = data["ed25519_signature"]
        if not isinstance(ed25519_sig, str) or not ed25519_sig:
            raise ValueError("ed25519_signature must be a non-empty string")

        hmac_algo = data.get("hmac_algorithm", "sha256")
        if hmac_algo not in {"sha256", "sha384", "sha512"}:
            raise ValueError(f"Unsupported hmac_algorithm: {hmac_algo}")

        return cls(
            ed25519_signature=ed25519_sig,
            hmac_signature=data.get("hmac_signature"),
            hmac_algorithm=hmac_algo,
        )


def hmac_sign(payload: Union[bytes, str, dict], hmac_key: bytes) -> str:
    """
    Compute HMAC-SHA256 of payload.

    Args:
        payload: Data to sign (bytes, string, or dict).
            Dicts are canonicalized via serialize_for_signing before hashing.
        hmac_key: Symmetric key for HMAC computation.

    Returns:
        Base64-encoded HMAC-SHA256 digest (32 bytes decoded).
    """
    import hmac as hmac_mod

    if isinstance(payload, dict):
        payload_bytes = serialize_for_signing(payload).encode("utf-8")
    elif isinstance(payload, str):
        payload_bytes = payload.encode("utf-8")
    else:
        payload_bytes = payload
    mac = hmac_mod.new(hmac_key, payload_bytes, hashlib.sha256)
    return base64.b64encode(mac.digest()).decode("utf-8")


def hmac_verify(
    payload: Union[bytes, str, dict], hmac_signature: str, hmac_key: bytes
) -> bool:
    """
    Verify HMAC-SHA256 signature.

    Uses constant-time comparison (hmac.compare_digest) to prevent
    timing side-channel attacks. NEVER uses == for comparison.

    Args:
        payload: Original data that was signed.
        hmac_signature: Base64-encoded HMAC-SHA256 to verify against.
        hmac_key: Symmetric key used for HMAC computation.

    Returns:
        True if the HMAC is valid, False otherwise.
    """
    import hmac as hmac_mod

    expected = hmac_sign(payload, hmac_key)
    return hmac_mod.compare_digest(expected, hmac_signature)


def dual_sign(
    payload: Union[bytes, str, dict],
    private_key: str,
    hmac_key: Optional[bytes] = None,
) -> DualSignature:
    """
    Sign with Ed25519 and optionally HMAC-SHA256.

    Ed25519 signing is always performed. HMAC-SHA256 is computed only
    when hmac_key is provided.

    Args:
        payload: Data to sign (bytes, string, or dict).
        private_key: Base64-encoded Ed25519 private key.
        hmac_key: Optional symmetric key for HMAC-SHA256.

    Returns:
        DualSignature with Ed25519 signature (always) and HMAC (if key provided).

    Raises:
        ImportError: If PyNaCl is not installed.
        ValueError: If private key is invalid.
    """
    ed25519_sig = sign(payload, private_key)
    hmac_sig = hmac_sign(payload, hmac_key) if hmac_key is not None else None
    return DualSignature(ed25519_signature=ed25519_sig, hmac_signature=hmac_sig)


def dual_verify(
    payload: Union[bytes, str, dict],
    dual_sig: DualSignature,
    public_key: str,
    hmac_key: Optional[bytes] = None,
) -> bool:
    """
    Verify dual signature. Ed25519 always checked. HMAC checked if present and key provided.

    Ed25519 verification is mandatory and always performed first. If it fails,
    the function returns False immediately without checking HMAC.

    HMAC verification is performed only when BOTH:
    1. The DualSignature contains an HMAC signature (has_hmac is True)
    2. An hmac_key is provided to this function

    Args:
        payload: Original data that was signed.
        dual_sig: DualSignature to verify.
        public_key: Base64-encoded Ed25519 public key.
        hmac_key: Optional symmetric key for HMAC verification.

    Returns:
        True if all applicable verifications pass, False otherwise.

    Raises:
        ImportError: If PyNaCl is not installed.
        InvalidSignatureError: If Ed25519 verification encounters an unexpected error.
    """
    # Ed25519 is mandatory
    if not verify_signature(payload, dual_sig.ed25519_signature, public_key):
        return False
    # HMAC verification (if present and key available)
    if (
        dual_sig.has_hmac
        and hmac_key is not None
        and dual_sig.hmac_signature is not None
    ):
        if not hmac_verify(payload, dual_sig.hmac_signature, hmac_key):
            return False
    return True


__all__ = [
    # Constants
    "NACL_AVAILABLE",
    "SALT_LENGTH",
    # Key generation
    "generate_keypair",
    "generate_salt",
    "derive_key_with_salt",
    # Ed25519 signing and verification
    "sign",
    "verify_signature",
    # Serialization and hashing
    "serialize_for_signing",
    "hash_chain",
    "hash_trust_chain_state",
    "hash_trust_chain_state_salted",
    # Reasoning trace crypto
    "hash_reasoning_trace",
    "sign_reasoning_trace",
    "verify_reasoning_signature",
    # Dual signature system (Phase 5 G6)
    "DualSignature",
    "hmac_sign",
    "hmac_verify",
    "dual_sign",
    "dual_verify",
]
