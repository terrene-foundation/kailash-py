# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP JWT Interop -- Export and import trust chains as signed JWTs.

Provides functions to serialize EATP trust lineage chains, capability
attestations, and delegation records into signed JSON Web Tokens (JWTs)
following IETF RFC 7519.  Tokens use standard claims (iss, sub, exp, iat, jti)
plus custom ``eatp_*`` claims for protocol-specific data.

Requires ``pyjwt[crypto]`` for EdDSA (Ed25519) support.  The library is an
optional dependency; a clear ImportError is raised if it is missing when any
function in this module is called.

Usage::

    from eatp.interop.jwt import export_chain_as_jwt, import_chain_from_jwt

    token = export_chain_as_jwt(chain, signing_key, algorithm="EdDSA")
    restored = import_chain_from_jwt(token, verify_key)
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Guarded import of PyJWT
# ---------------------------------------------------------------------------
try:
    import jwt as _jwt
except ImportError as _import_err:
    raise ImportError(
        "pyjwt[crypto] is required for EATP JWT interop but is not installed. "
        "Install it with: pip install 'pyjwt[crypto]'"
    ) from _import_err

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

EATP_VERSION: str = "0.1.0"
"""EATP protocol version embedded in every JWT payload."""

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

from eatp.chain import (
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    Constraint,
    ConstraintEnvelope,
    ConstraintType,
    DelegationRecord,
    GenesisRecord,
    TrustLineageChain,
)
from eatp.reasoning import ConfidentialityLevel


def _validate_signing_key(signing_key: str) -> None:
    """Raise ValueError if the signing key is empty or invalid."""
    if not signing_key:
        raise ValueError(
            "signing_key must be a non-empty string. Provide a valid secret or PEM-encoded key for signing JWTs."
        )


def _validate_verify_key(verify_key: str) -> None:
    """Raise ValueError if the verify key is empty or invalid."""
    if not verify_key:
        raise ValueError(
            "verify_key must be a non-empty string. Provide a valid secret or PEM-encoded key for verifying JWTs."
        )


def _datetime_to_epoch(dt: datetime) -> int:
    """Convert a timezone-aware datetime to a POSIX epoch integer."""
    return int(dt.timestamp())


def _serialize_genesis(genesis: GenesisRecord) -> Dict[str, Any]:
    """Serialize a GenesisRecord to a JSON-safe dict."""
    return {
        "id": genesis.id,
        "agent_id": genesis.agent_id,
        "authority_id": genesis.authority_id,
        "authority_type": genesis.authority_type.value,
        "created_at": genesis.created_at.isoformat(),
        "expires_at": genesis.expires_at.isoformat() if genesis.expires_at else None,
        "signature": genesis.signature,
        "signature_algorithm": genesis.signature_algorithm,
        "metadata": genesis.metadata,
    }


def _serialize_capability(cap: CapabilityAttestation) -> Dict[str, Any]:
    """Serialize a CapabilityAttestation to a JSON-safe dict."""
    return {
        "id": cap.id,
        "capability": cap.capability,
        "capability_type": cap.capability_type.value,
        "constraints": cap.constraints,
        "attester_id": cap.attester_id,
        "attested_at": cap.attested_at.isoformat(),
        "expires_at": cap.expires_at.isoformat() if cap.expires_at else None,
        "signature": cap.signature,
        "scope": cap.scope,
    }


def _serialize_delegation(delegation: DelegationRecord) -> Dict[str, Any]:
    """Serialize a DelegationRecord to a JSON-safe dict."""
    d: Dict[str, Any] = {
        "id": delegation.id,
        "delegator_id": delegation.delegator_id,
        "delegatee_id": delegation.delegatee_id,
        "task_id": delegation.task_id,
        "capabilities_delegated": delegation.capabilities_delegated,
        "constraint_subset": delegation.constraint_subset,
        "delegated_at": delegation.delegated_at.isoformat(),
        "expires_at": (delegation.expires_at.isoformat() if delegation.expires_at else None),
        "signature": delegation.signature,
        "parent_delegation_id": delegation.parent_delegation_id,
        "delegation_chain": delegation.delegation_chain,
        "delegation_depth": delegation.delegation_depth,
    }
    if delegation.human_origin is not None:
        d["human_origin"] = delegation.human_origin.to_dict()
    # Reasoning trace extension (confidentiality-based filtering)
    if delegation.reasoning_trace is not None:
        if delegation.reasoning_trace.confidentiality <= ConfidentialityLevel.RESTRICTED:
            d["reasoning_trace"] = delegation.reasoning_trace.to_dict()
        # Hash and signature are integrity proofs, not confidential — always include
    if delegation.reasoning_trace_hash is not None:
        d["reasoning_trace_hash"] = delegation.reasoning_trace_hash
    if delegation.reasoning_signature is not None:
        d["reasoning_signature"] = delegation.reasoning_signature
    return d


def _serialize_constraint_envelope(
    envelope: ConstraintEnvelope,
) -> Dict[str, Any]:
    """Serialize a ConstraintEnvelope to a JSON-safe dict."""
    return {
        "id": envelope.id,
        "agent_id": envelope.agent_id,
        "constraint_hash": envelope.constraint_hash,
        "active_constraints": [
            {
                "id": c.id,
                "constraint_type": c.constraint_type.value,
                "value": c.value,
                "source": c.source,
                "priority": c.priority,
            }
            for c in envelope.active_constraints
        ],
    }


def _serialize_audit_anchor(anchor: Any) -> Dict[str, Any]:
    """Serialize an AuditAnchor to a JSON-safe dict via its to_dict() method."""
    d = anchor.to_dict()
    # Apply confidentiality filtering to reasoning traces
    if (
        hasattr(anchor, "reasoning_trace")
        and anchor.reasoning_trace is not None
        and anchor.reasoning_trace.confidentiality > ConfidentialityLevel.RESTRICTED
    ):
        d.pop("reasoning_trace", None)
    return d


def _serialize_chain_payload(chain: TrustLineageChain) -> Dict[str, Any]:
    """Build the ``eatp_chain`` claim dict from a full TrustLineageChain."""
    chain_data: Dict[str, Any] = {
        "genesis": _serialize_genesis(chain.genesis),
        "capabilities": [_serialize_capability(c) for c in chain.capabilities],
        "delegations": [_serialize_delegation(d) for d in chain.delegations],
        "constraint_envelope": (
            _serialize_constraint_envelope(chain.constraint_envelope) if chain.constraint_envelope else None
        ),
        "audit_anchors": [_serialize_audit_anchor(a) for a in chain.audit_anchors],
        "chain_hash": chain.hash(),
    }
    return chain_data


def _compute_earliest_expiry(chain: TrustLineageChain) -> datetime | None:
    """Return the earliest expiry across the genesis, capabilities, and delegations.

    Returns None if nothing in the chain expires.
    """
    candidates: list[datetime] = []
    if chain.genesis.expires_at is not None:
        candidates.append(chain.genesis.expires_at)
    for cap in chain.capabilities:
        if cap.expires_at is not None:
            candidates.append(cap.expires_at)
    for deleg in chain.delegations:
        if deleg.expires_at is not None:
            candidates.append(deleg.expires_at)
    if not candidates:
        return None
    return min(candidates)


# ---------------------------------------------------------------------------
# Deserialization helpers
# ---------------------------------------------------------------------------


def _deserialize_genesis(data: Dict[str, Any]) -> GenesisRecord:
    """Reconstruct a GenesisRecord from a JWT claim dict."""
    return GenesisRecord(
        id=data["id"],
        agent_id=data["agent_id"],
        authority_id=data["authority_id"],
        authority_type=AuthorityType(data["authority_type"]),
        created_at=datetime.fromisoformat(data["created_at"]),
        expires_at=(datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None),
        signature=data.get("signature", ""),
        signature_algorithm=data.get("signature_algorithm", "Ed25519"),
        metadata=data.get("metadata", {}),
    )


def _deserialize_capability(data: Dict[str, Any]) -> CapabilityAttestation:
    """Reconstruct a CapabilityAttestation from a JWT claim dict."""
    return CapabilityAttestation(
        id=data["id"],
        capability=data["capability"],
        capability_type=CapabilityType(data["capability_type"]),
        constraints=data.get("constraints", []),
        attester_id=data["attester_id"],
        attested_at=datetime.fromisoformat(data["attested_at"]),
        signature=data.get("signature", ""),
        expires_at=(datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None),
        scope=data.get("scope"),
    )


def _deserialize_delegation(data: Dict[str, Any]) -> DelegationRecord:
    """Reconstruct a DelegationRecord from a JWT claim dict."""
    human_origin = None
    if data.get("human_origin"):
        from eatp.execution_context import HumanOrigin

        human_origin = HumanOrigin.from_dict(data["human_origin"])

    # Reasoning trace extension (backward compatible)
    reasoning_trace = None
    if data.get("reasoning_trace"):
        from eatp.reasoning import ReasoningTrace

        reasoning_trace = ReasoningTrace.from_dict(data["reasoning_trace"])

    return DelegationRecord(
        id=data["id"],
        delegator_id=data["delegator_id"],
        delegatee_id=data["delegatee_id"],
        task_id=data["task_id"],
        capabilities_delegated=data["capabilities_delegated"],
        constraint_subset=data.get("constraint_subset", []),
        delegated_at=datetime.fromisoformat(data["delegated_at"]),
        expires_at=(datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None),
        signature=data.get("signature", ""),
        parent_delegation_id=data.get("parent_delegation_id"),
        human_origin=human_origin,
        delegation_chain=data.get("delegation_chain", []),
        delegation_depth=data.get("delegation_depth", 0),
        reasoning_trace=reasoning_trace,
        reasoning_trace_hash=data.get("reasoning_trace_hash"),
        reasoning_signature=data.get("reasoning_signature"),
    )


def _deserialize_constraint_envelope(data: Dict[str, Any]) -> ConstraintEnvelope:
    """Reconstruct a ConstraintEnvelope from a JWT claim dict."""
    return ConstraintEnvelope(
        id=data["id"],
        agent_id=data["agent_id"],
        constraint_hash=data.get("constraint_hash", ""),
        active_constraints=[
            Constraint(
                id=c["id"],
                constraint_type=ConstraintType(c["constraint_type"]),
                value=c["value"],
                source=c["source"],
                priority=c.get("priority", 0),
            )
            for c in data.get("active_constraints", [])
        ],
    )


def _deserialize_chain(chain_data: Dict[str, Any]) -> TrustLineageChain:
    """Reconstruct a TrustLineageChain from the ``eatp_chain`` claim dict."""
    from eatp.chain import ActionResult, AuditAnchor

    genesis = _deserialize_genesis(chain_data["genesis"])

    capabilities = [_deserialize_capability(c) for c in chain_data.get("capabilities", [])]

    delegations = [_deserialize_delegation(d) for d in chain_data.get("delegations", [])]

    constraint_envelope = None
    env_data = chain_data.get("constraint_envelope")
    if env_data is not None:
        constraint_envelope = _deserialize_constraint_envelope(env_data)

    audit_anchors = []
    for a in chain_data.get("audit_anchors", []):
        human_origin = None
        if a.get("human_origin"):
            from eatp.execution_context import HumanOrigin

            human_origin = HumanOrigin.from_dict(a["human_origin"])

        # Reasoning trace extension (backward compatible)
        reasoning_trace = None
        if a.get("reasoning_trace"):
            from eatp.reasoning import ReasoningTrace

            reasoning_trace = ReasoningTrace.from_dict(a["reasoning_trace"])

        audit_anchors.append(
            AuditAnchor(
                id=a["id"],
                agent_id=a["agent_id"],
                action=a["action"],
                timestamp=datetime.fromisoformat(a["timestamp"]),
                trust_chain_hash=a["trust_chain_hash"],
                result=ActionResult(a["result"]),
                signature=a.get("signature", ""),
                resource=a.get("resource"),
                parent_anchor_id=a.get("parent_anchor_id"),
                context=a.get("context", {}),
                human_origin=human_origin,
                reasoning_trace=reasoning_trace,
                reasoning_trace_hash=a.get("reasoning_trace_hash"),
                reasoning_signature=a.get("reasoning_signature"),
            )
        )

    return TrustLineageChain(
        genesis=genesis,
        capabilities=capabilities,
        delegations=delegations,
        constraint_envelope=constraint_envelope,
        audit_anchors=audit_anchors,
    )


# ===================================================================
# Public API
# ===================================================================


def export_chain_as_jwt(
    chain: TrustLineageChain,
    signing_key: str,
    algorithm: str = "EdDSA",
) -> str:
    """Export a complete trust lineage chain as a signed JWT.

    The JWT embeds the full chain (genesis, capabilities, delegations,
    constraints, audit anchors) under the ``eatp_chain`` claim.  Standard
    IETF claims are populated from chain metadata:

    - ``iss``: authority_id from the genesis record
    - ``sub``: agent_id from the genesis record
    - ``iat``: current UTC timestamp
    - ``exp``: earliest expiry across all chain components (omitted if none)
    - ``jti``: unique token identifier (UUID4)

    Args:
        chain: The TrustLineageChain to export.
        signing_key: Secret or PEM key for signing.
        algorithm: JWT signing algorithm (default ``"EdDSA"``).

    Returns:
        Encoded JWT string.

    Raises:
        ValueError: If signing_key is empty.
    """
    _validate_signing_key(signing_key)

    now = datetime.now(timezone.utc)

    payload: Dict[str, Any] = {
        # Standard IETF claims
        "iss": chain.genesis.authority_id,
        "sub": chain.genesis.agent_id,
        "iat": _datetime_to_epoch(now),
        "jti": str(uuid.uuid4()),
        # EATP custom claims
        "eatp_version": EATP_VERSION,
        "eatp_type": "trust_chain",
        "eatp_chain": _serialize_chain_payload(chain),
    }

    earliest_expiry = _compute_earliest_expiry(chain)
    if earliest_expiry is not None:
        payload["exp"] = _datetime_to_epoch(earliest_expiry)

    logger.debug(
        "Exporting trust chain for agent=%s as JWT (algorithm=%s)",
        chain.genesis.agent_id,
        algorithm,
    )

    token: str = _jwt.encode(payload, signing_key, algorithm=algorithm)
    return token


def import_chain_from_jwt(
    token: str,
    verify_key: str,
    algorithm: str = "EdDSA",
) -> TrustLineageChain:
    """Import and verify a JWT, returning the embedded TrustLineageChain.

    Performs full signature verification and expiration checking.  The
    payload is validated for required EATP claims before deserialization.

    Args:
        token: The encoded JWT string.
        verify_key: Secret or PEM key for verification.
        algorithm: Expected JWT signing algorithm (default ``"EdDSA"``).

    Returns:
        Reconstructed TrustLineageChain.

    Raises:
        ValueError: If required EATP claims are missing or invalid.
        jwt.InvalidSignatureError: If the signature does not match.
        jwt.ExpiredSignatureError: If the token has expired.
        jwt.DecodeError: If the token is malformed.
    """
    _validate_verify_key(verify_key)

    # Restrict to asymmetric algorithms only to prevent both the "none"
    # algorithm attack and HMAC key-confusion attacks (where an attacker
    # signs with the public key as HMAC secret).  EATP uses Ed25519
    # exclusively; HMAC has no legitimate use case for trust chain JWTs.
    _SAFE_ALGORITHMS = {
        "EdDSA",
        "ES256",
        "ES384",
        "ES512",
        "RS256",
        "RS384",
        "RS512",
    }
    if algorithm not in _SAFE_ALGORITHMS:
        raise ValueError(f"Algorithm '{algorithm}' is not allowed. Use one of: {', '.join(sorted(_SAFE_ALGORITHMS))}")

    payload = _jwt.decode(token, verify_key, algorithms=[algorithm])

    # --- Validate EATP-specific claims ---

    if "eatp_version" not in payload:
        raise ValueError(
            "JWT payload is missing required claim 'eatp_version'. "
            "This token was not created by an EATP-compatible exporter."
        )

    eatp_type = payload.get("eatp_type")
    if eatp_type != "trust_chain":
        raise ValueError(
            f"JWT payload has unexpected eatp_type='{eatp_type}'. "
            f"Expected 'trust_chain' for chain import. "
            f"Use the appropriate import function for '{eatp_type}' tokens."
        )

    if "eatp_chain" not in payload:
        raise ValueError(
            "JWT payload is missing required claim 'eatp_chain'. "
            "The token does not contain serialized trust chain data."
        )

    chain_data = payload["eatp_chain"]

    logger.debug(
        "Importing trust chain from JWT for agent=%s (eatp_version=%s)",
        payload.get("sub", "unknown"),
        payload.get("eatp_version"),
    )

    return _deserialize_chain(chain_data)


def export_capability_as_jwt(
    attestation: CapabilityAttestation,
    signing_key: str,
    algorithm: str = "EdDSA",
) -> str:
    """Export a single capability attestation as a signed JWT.

    Claims mapping:

    - ``iss``: attester_id
    - ``sub``: capability attestation id
    - ``exp``: attestation expiry (omitted if none)

    Args:
        attestation: The CapabilityAttestation to export.
        signing_key: Secret or PEM key for signing.
        algorithm: JWT signing algorithm (default ``"EdDSA"``).

    Returns:
        Encoded JWT string.

    Raises:
        ValueError: If signing_key is empty.
    """
    _validate_signing_key(signing_key)

    now = datetime.now(timezone.utc)

    payload: Dict[str, Any] = {
        "iss": attestation.attester_id,
        "sub": attestation.id,
        "iat": _datetime_to_epoch(now),
        "jti": str(uuid.uuid4()),
        "eatp_version": EATP_VERSION,
        "eatp_type": "capability_attestation",
        "eatp_capability": _serialize_capability(attestation),
    }

    if attestation.expires_at is not None:
        payload["exp"] = _datetime_to_epoch(attestation.expires_at)

    logger.debug(
        "Exporting capability '%s' (id=%s) as JWT",
        attestation.capability,
        attestation.id,
    )

    token: str = _jwt.encode(payload, signing_key, algorithm=algorithm)
    return token


def export_delegation_as_jwt(
    delegation: DelegationRecord,
    signing_key: str,
    algorithm: str = "EdDSA",
) -> str:
    """Export a single delegation record as a signed JWT.

    Claims mapping:

    - ``iss``: delegator_id
    - ``sub``: delegatee_id
    - ``exp``: delegation expiry (omitted if none)

    Args:
        delegation: The DelegationRecord to export.
        signing_key: Secret or PEM key for signing.
        algorithm: JWT signing algorithm (default ``"EdDSA"``).

    Returns:
        Encoded JWT string.

    Raises:
        ValueError: If signing_key is empty.
    """
    _validate_signing_key(signing_key)

    now = datetime.now(timezone.utc)

    payload: Dict[str, Any] = {
        "iss": delegation.delegator_id,
        "sub": delegation.delegatee_id,
        "iat": _datetime_to_epoch(now),
        "jti": str(uuid.uuid4()),
        "eatp_version": EATP_VERSION,
        "eatp_type": "delegation",
        "eatp_delegation": _serialize_delegation(delegation),
    }

    if delegation.expires_at is not None:
        payload["exp"] = _datetime_to_epoch(delegation.expires_at)

    logger.debug(
        "Exporting delegation %s -> %s (id=%s) as JWT",
        delegation.delegator_id,
        delegation.delegatee_id,
        delegation.id,
    )

    token: str = _jwt.encode(payload, signing_key, algorithm=algorithm)
    return token
