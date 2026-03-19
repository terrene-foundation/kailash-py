# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP DID (Decentralized Identifier) Identity Layer.

Implements the ``did:eatp`` method for EATP-native agent identity, plus
``did:key`` interop for cross-system compatibility.

DID documents follow the W3C DID Core specification (https://www.w3.org/TR/did-core/)
with Ed25519VerificationKey2020 as the verification method type.

DID Method Syntax
-----------------
    did:eatp:<agent_id>

Where ``<agent_id>`` is the EATP agent or authority identifier, which must
not contain colons (DID delimiters) or whitespace.

did:key Interop
---------------
``generate_did_key`` produces a ``did:key`` URI from an Ed25519 public key
using multicodec (0xed01) + multibase (base58btc / z-prefix) encoding,
per the did:key specification (https://w3c-ccg.github.io/did-method-key/).
"""

import base64
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from eatp.authority import OrganizationalAuthority

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DID_METHOD_EATP = "eatp"
DID_METHOD_KEY = "key"
SUPPORTED_DID_METHODS = {DID_METHOD_EATP, DID_METHOD_KEY}

# W3C DID Core JSON-LD context
W3C_DID_CONTEXT = "https://www.w3.org/ns/did/v1"
ED25519_SUITE_CONTEXT = "https://w3id.org/security/suites/ed25519-2020/v1"

# Ed25519 multicodec prefix (varint-encoded 0xed = 0xed01 in unsigned varint)
_ED25519_MULTICODEC_PREFIX = bytes([0xED, 0x01])

# Base58btc alphabet (Bitcoin alphabet)
_BASE58_ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DIDValidationError(ValueError):
    """Raised when a DID or DID document fails validation."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class DIDResolutionError(LookupError):
    """Raised when a DID cannot be resolved to a document."""

    def __init__(self, did: str, reason: str):
        super().__init__(f"Cannot resolve DID '{did}': {reason}")
        self.did = did
        self.reason = reason


# ---------------------------------------------------------------------------
# Data classes (W3C DID Core aligned)
# ---------------------------------------------------------------------------


@dataclass
class VerificationMethod:
    """
    A verification method as defined by W3C DID Core.

    For EATP, this is always Ed25519VerificationKey2020 backed by
    the same Ed25519 keys used throughout the trust chain.

    Attributes:
        id: Fully-qualified identifier, e.g. ``did:eatp:agent-001#key-1``
        type: Verification suite, always ``Ed25519VerificationKey2020``
        controller: DID of the entity that controls this key
        public_key_multibase: Multibase-encoded (z = base58btc) public key
    """

    id: str
    type: str
    controller: str
    public_key_multibase: str


@dataclass
class ServiceEndpoint:
    """
    A service endpoint associated with a DID subject.

    Attributes:
        id: Fully-qualified identifier, e.g. ``did:eatp:agent-001#trust-api``
        type: Service type string (e.g. ``TrustVerification``)
        service_endpoint: URL of the service
    """

    id: str
    type: str
    service_endpoint: str


@dataclass
class DIDDocument:
    """
    W3C DID Core compliant DID Document for an EATP agent.

    Attributes:
        id: The DID (e.g. ``did:eatp:agent-001``)
        verification_method: List of Ed25519 verification methods
        authentication: References to verification methods used for authentication
        assertion_method: References to verification methods used for VC signing
        service: Optional service endpoints
        controller: Authority DID if this agent's key is controlled by another entity
    """

    id: str
    verification_method: List[VerificationMethod]
    authentication: List[str]
    assertion_method: List[str]
    service: List[ServiceEndpoint] = field(default_factory=list)
    controller: Optional[str] = None


# ---------------------------------------------------------------------------
# Base58btc encoding (no external dependency)
# ---------------------------------------------------------------------------


def _base58_encode(data: bytes) -> str:
    """
    Encode bytes to base58btc (Bitcoin alphabet).

    This is a pure-Python implementation to avoid requiring an external
    base58 dependency. It handles leading zero bytes correctly.

    Args:
        data: Raw bytes to encode.

    Returns:
        Base58btc-encoded string.
    """
    # Count leading zero bytes (they map to '1' in base58)
    n_leading_zeros = 0
    for byte in data:
        if byte == 0:
            n_leading_zeros += 1
        else:
            break

    # Convert bytes to a big integer
    num = int.from_bytes(data, "big")

    # Encode the integer in base58
    result_bytes = bytearray()
    while num > 0:
        num, remainder = divmod(num, 58)
        result_bytes.append(_BASE58_ALPHABET[remainder])

    # Reverse (we built least-significant first)
    result_bytes.reverse()

    # Prepend '1' characters for leading zero bytes
    return ("1" * n_leading_zeros) + result_bytes.decode("ascii")


def _base58_decode(encoded: str) -> bytes:
    """
    Decode a base58btc (Bitcoin alphabet) string to bytes.

    Args:
        encoded: Base58btc-encoded string.

    Returns:
        Decoded raw bytes.

    Raises:
        DIDValidationError: If the string contains invalid characters.
    """
    # Count leading '1' characters (they map to zero bytes)
    n_leading_ones = 0
    for char in encoded:
        if char == "1":
            n_leading_ones += 1
        else:
            break

    # Decode base58 to integer
    num = 0
    for char in encoded:
        idx = _BASE58_ALPHABET.find(char.encode("ascii"))
        if idx < 0:
            raise DIDValidationError(
                f"Invalid base58btc character: '{char}'",
                details={"encoded": encoded},
            )
        num = num * 58 + idx

    # Convert integer to bytes
    if num == 0:
        result = b""
    else:
        # Calculate needed byte length
        byte_length = (num.bit_length() + 7) // 8
        result = num.to_bytes(byte_length, "big")

    # Prepend zero bytes for leading '1' characters
    return b"\x00" * n_leading_ones + result


# ---------------------------------------------------------------------------
# Multibase / multicodec helpers
# ---------------------------------------------------------------------------


def _public_key_to_multibase(public_key_b64: str) -> str:
    """
    Encode an Ed25519 public key as a multibase (base58btc) string.

    The encoding is: 'z' prefix + base58btc( multicodec_prefix + raw_key ).
    The multicodec prefix for Ed25519 public keys is 0xed01.

    Args:
        public_key_b64: Base64-encoded Ed25519 public key (32 bytes).

    Returns:
        Multibase-encoded string starting with 'z'.
    """
    raw_key = base64.b64decode(public_key_b64)
    prefixed = _ED25519_MULTICODEC_PREFIX + raw_key
    return "z" + _base58_encode(prefixed)


def _multibase_to_public_key_b64(multibase: str) -> str:
    """
    Decode a multibase (base58btc) string back to a base64-encoded public key.

    Args:
        multibase: Multibase-encoded string (must start with 'z').

    Returns:
        Base64-encoded Ed25519 public key.

    Raises:
        DIDValidationError: If the encoding is invalid.
    """
    if not multibase.startswith("z"):
        raise DIDValidationError(
            f"Expected multibase 'z' prefix (base58btc), got '{multibase[:1]}'",
            details={"multibase": multibase},
        )

    decoded = _base58_decode(multibase[1:])

    if not decoded.startswith(_ED25519_MULTICODEC_PREFIX):
        raise DIDValidationError(
            "Expected Ed25519 multicodec prefix (0xed01) in decoded bytes",
            details={"multibase": multibase},
        )

    raw_key = decoded[len(_ED25519_MULTICODEC_PREFIX) :]
    return base64.b64encode(raw_key).decode("utf-8")


# ---------------------------------------------------------------------------
# DID validation helpers
# ---------------------------------------------------------------------------


def _validate_agent_id(agent_id: str) -> None:
    """
    Validate an agent_id for use in a DID.

    Raises DIDValidationError if the agent_id is empty, contains only
    whitespace, contains colons (DID delimiter), or contains whitespace.

    Args:
        agent_id: The agent identifier to validate.

    Raises:
        DIDValidationError: If the agent_id is invalid.
    """
    if not agent_id or not agent_id.strip():
        raise DIDValidationError(
            "agent_id must not be empty or whitespace-only",
            details={"agent_id": repr(agent_id)},
        )

    if ":" in agent_id:
        raise DIDValidationError(
            "agent_id must not contain a colon (':') — colons are DID delimiters",
            details={"agent_id": agent_id},
        )

    if any(c.isspace() for c in agent_id):
        raise DIDValidationError(
            "agent_id must not contain whitespace characters",
            details={"agent_id": agent_id},
        )


def _validate_public_key_b64(public_key: str) -> None:
    """
    Validate a base64-encoded Ed25519 public key.

    Args:
        public_key: Base64-encoded public key string.

    Raises:
        DIDValidationError: If the key is empty or not valid base64.
    """
    if not public_key or not public_key.strip():
        raise DIDValidationError(
            "public_key must not be empty",
            details={"public_key": repr(public_key)},
        )

    try:
        decoded = base64.b64decode(public_key, validate=True)
    except Exception as exc:
        raise DIDValidationError(
            f"public_key is not valid base64: {exc}",
            details={"public_key": public_key},
        ) from exc

    if len(decoded) != 32:
        raise DIDValidationError(
            f"Ed25519 public key must be exactly 32 bytes, got {len(decoded)}",
            details={"public_key": public_key, "byte_length": len(decoded)},
        )


def _validate_did_string(did: str) -> tuple[str, str]:
    """
    Parse and validate a DID string.

    Returns the (method, method_specific_id) tuple.

    Args:
        did: Full DID string (e.g. ``did:eatp:agent-001``).

    Returns:
        Tuple of (method, method_specific_id).

    Raises:
        DIDValidationError: If the DID format is invalid or method unsupported.
    """
    if not did or not did.startswith("did:"):
        raise DIDValidationError(
            f"Invalid DID format: must start with 'did:', got '{did}'",
            details={"did": did},
        )

    parts = did.split(":", 2)
    if len(parts) < 3 or not parts[2]:
        raise DIDValidationError(
            f"Invalid DID format: expected 'did:<method>:<id>', got '{did}'",
            details={"did": did},
        )

    method = parts[1]
    method_specific_id = parts[2]

    if method not in SUPPORTED_DID_METHODS:
        raise DIDValidationError(
            f"Unsupported DID method '{method}'. Supported methods: {', '.join(sorted(SUPPORTED_DID_METHODS))}",
            details={"did": did, "method": method},
        )

    return method, method_specific_id


# ---------------------------------------------------------------------------
# Public API: DID generation
# ---------------------------------------------------------------------------


def generate_did(agent_id: str) -> str:
    """
    Generate an EATP-native DID from an agent identifier.

    Produces a DID of the form ``did:eatp:<agent_id>``.

    Args:
        agent_id: EATP agent identifier. Must not be empty, contain colons,
                  or contain whitespace.

    Returns:
        The DID string.

    Raises:
        DIDValidationError: If agent_id is invalid.

    Example:
        >>> generate_did("agent-001")
        'did:eatp:agent-001'
    """
    _validate_agent_id(agent_id)
    return f"did:{DID_METHOD_EATP}:{agent_id}"


def generate_did_key(public_key: str) -> str:
    """
    Generate a ``did:key`` DID from an Ed25519 public key.

    Uses multicodec (0xed01 for Ed25519) + multibase (base58btc / z-prefix)
    encoding per the did:key specification.

    Args:
        public_key: Base64-encoded Ed25519 public key (32 bytes).

    Returns:
        A ``did:key:z6Mk...`` DID string.

    Raises:
        DIDValidationError: If the public key is empty or invalid.

    Example:
        >>> from eatp.crypto import generate_keypair
        >>> _, pub = generate_keypair()
        >>> did = generate_did_key(pub)
        >>> did.startswith('did:key:z6Mk')
        True
    """
    _validate_public_key_b64(public_key)
    multibase_key = _public_key_to_multibase(public_key)
    return f"did:{DID_METHOD_KEY}:{multibase_key}"


# ---------------------------------------------------------------------------
# Public API: DID Document creation
# ---------------------------------------------------------------------------


def create_did_document(
    agent_id: str,
    public_key: str,
    authority_id: Optional[str] = None,
) -> DIDDocument:
    """
    Create a full DID document for an EATP agent.

    The document conforms to W3C DID Core and uses Ed25519VerificationKey2020
    for the verification method.

    Args:
        agent_id: EATP agent identifier.
        public_key: Base64-encoded Ed25519 public key.
        authority_id: Optional authority identifier. If provided, the document's
                      ``controller`` field is set to ``did:eatp:<authority_id>``.

    Returns:
        A populated DIDDocument dataclass.

    Raises:
        DIDValidationError: If agent_id or public_key is invalid.

    Example:
        >>> from eatp.crypto import generate_keypair
        >>> _, pub = generate_keypair()
        >>> doc = create_did_document("agent-001", pub)
        >>> doc.id
        'did:eatp:agent-001'
    """
    _validate_agent_id(agent_id)
    _validate_public_key_b64(public_key)

    did = generate_did(agent_id)
    key_id = f"{did}#key-1"
    multibase_key = _public_key_to_multibase(public_key)

    verification_method = VerificationMethod(
        id=key_id,
        type="Ed25519VerificationKey2020",
        controller=did,
        public_key_multibase=multibase_key,
    )

    controller = None
    if authority_id is not None:
        _validate_agent_id(authority_id)
        controller = generate_did(authority_id)

    return DIDDocument(
        id=did,
        verification_method=[verification_method],
        authentication=[key_id],
        assertion_method=[key_id],
        service=[],
        controller=controller,
    )


# ---------------------------------------------------------------------------
# Public API: Authority DID
# ---------------------------------------------------------------------------


def did_from_authority(authority: OrganizationalAuthority) -> str:
    """
    Generate a DID from an OrganizationalAuthority.

    The authority must be active. Inactive authorities cannot have DIDs
    generated because they are no longer valid trust roots.

    Args:
        authority: An active OrganizationalAuthority instance.

    Returns:
        The DID string ``did:eatp:<authority.id>``.

    Raises:
        DIDValidationError: If the authority is inactive.

    Example:
        >>> from eatp.authority import OrganizationalAuthority
        >>> from eatp.chain import AuthorityType
        >>> auth = OrganizationalAuthority(
        ...     id="org-acme", name="ACME", authority_type=AuthorityType.ORGANIZATION,
        ...     public_key="...", signing_key_id="k1",
        ... )
        >>> did_from_authority(auth)
        'did:eatp:org-acme'
    """
    if not authority.is_active:
        raise DIDValidationError(
            f"Cannot generate DID for inactive authority '{authority.id}'",
            details={"authority_id": authority.id, "is_active": authority.is_active},
        )

    return generate_did(authority.id)


# ---------------------------------------------------------------------------
# Public API: DID resolution
# ---------------------------------------------------------------------------


def resolve_did(
    did: str,
    registry: Dict[str, DIDDocument],
) -> DIDDocument:
    """
    Resolve a DID to its DIDDocument using a provided registry.

    Both ``did:eatp`` and ``did:key`` methods are supported for resolution,
    but the document must exist in the supplied registry.

    Args:
        did: The DID to resolve.
        registry: Mapping of DID strings to DIDDocument instances.

    Returns:
        The resolved DIDDocument.

    Raises:
        DIDValidationError: If the DID format is invalid or method unsupported.
        DIDResolutionError: If the DID is not found in the registry.

    Example:
        >>> from eatp.crypto import generate_keypair
        >>> _, pub = generate_keypair()
        >>> doc = create_did_document("agent-001", pub)
        >>> resolved = resolve_did(doc.id, registry={doc.id: doc})
        >>> resolved.id == doc.id
        True
    """
    _method, _method_id = _validate_did_string(did)

    if did not in registry:
        raise DIDResolutionError(
            did=did,
            reason=f"DID not found in registry (method={_method}, id={_method_id})",
        )

    logger.debug(
        "Resolved DID '%s' to document with %d verification methods",
        did,
        len(registry[did].verification_method),
    )

    return registry[did]


# ---------------------------------------------------------------------------
# Public API: Serialization / Deserialization
# ---------------------------------------------------------------------------


def did_document_to_dict(doc: DIDDocument) -> Dict[str, Any]:
    """
    Serialize a DIDDocument to a JSON-LD-compatible dictionary.

    The output follows W3C DID Core serialization conventions:
    - ``@context`` includes the DID and Ed25519 suite contexts
    - Verification methods use camelCase field names
    - Service endpoints use ``serviceEndpoint`` (camelCase)

    Args:
        doc: The DIDDocument to serialize.

    Returns:
        A dictionary suitable for ``json.dumps()``.

    Example:
        >>> from eatp.crypto import generate_keypair
        >>> _, pub = generate_keypair()
        >>> doc = create_did_document("agent-001", pub)
        >>> data = did_document_to_dict(doc)
        >>> data["@context"]
        ['https://www.w3.org/ns/did/v1', 'https://w3id.org/security/suites/ed25519-2020/v1']
    """
    result: Dict[str, Any] = {
        "@context": [W3C_DID_CONTEXT, ED25519_SUITE_CONTEXT],
        "id": doc.id,
        "verificationMethod": [
            {
                "id": vm.id,
                "type": vm.type,
                "controller": vm.controller,
                "publicKeyMultibase": vm.public_key_multibase,
            }
            for vm in doc.verification_method
        ],
        "authentication": list(doc.authentication),
        "assertionMethod": list(doc.assertion_method),
    }

    if doc.controller is not None:
        result["controller"] = doc.controller

    if doc.service:
        result["service"] = [
            {
                "id": svc.id,
                "type": svc.type,
                "serviceEndpoint": svc.service_endpoint,
            }
            for svc in doc.service
        ]
    else:
        result["service"] = []

    return result


def did_document_from_dict(data: Dict[str, Any]) -> DIDDocument:
    """
    Deserialize a dictionary to a DIDDocument.

    Validates that required fields are present and correctly structured.

    Args:
        data: Dictionary (typically from ``json.loads()``).

    Returns:
        A DIDDocument instance.

    Raises:
        DIDValidationError: If required fields are missing or malformed.

    Example:
        >>> from eatp.crypto import generate_keypair
        >>> _, pub = generate_keypair()
        >>> doc = create_did_document("agent-001", pub)
        >>> data = did_document_to_dict(doc)
        >>> restored = did_document_from_dict(data)
        >>> restored.id == doc.id
        True
    """
    if "id" not in data:
        raise DIDValidationError(
            "DID document dict missing required field 'id'",
            details={"keys_present": list(data.keys())},
        )

    if "verificationMethod" not in data:
        raise DIDValidationError(
            "DID document dict missing required field 'verificationMethod'",
            details={"keys_present": list(data.keys())},
        )

    verification_methods = []
    for vm_data in data["verificationMethod"]:
        verification_methods.append(
            VerificationMethod(
                id=vm_data["id"],
                type=vm_data["type"],
                controller=vm_data["controller"],
                public_key_multibase=vm_data["publicKeyMultibase"],
            )
        )

    services = []
    for svc_data in data.get("service", []):
        services.append(
            ServiceEndpoint(
                id=svc_data["id"],
                type=svc_data["type"],
                service_endpoint=svc_data["serviceEndpoint"],
            )
        )

    controller = data.get("controller")

    return DIDDocument(
        id=data["id"],
        verification_method=verification_methods,
        authentication=data.get("authentication", []),
        assertion_method=data.get("assertionMethod", []),
        service=services,
        controller=controller,
    )
