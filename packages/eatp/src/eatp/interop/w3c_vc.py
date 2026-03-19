# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
W3C Verifiable Credentials export/import for EATP trust chains.

Implements W3C VC Data Model 2.0 serialization for TrustLineageChain
and CapabilityAttestation objects, enabling interoperability with
standards-compliant verifiable credential systems.

Proof type: Ed25519Signature2020
Signing: Ed25519 via PyNaCl (same primitives as eatp.crypto)

References:
    - W3C VC Data Model 2.0: https://www.w3.org/TR/vc-data-model-2.0/
    - Ed25519Signature2020: https://w3c-ccg.github.io/lds-ed25519-2020/
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

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
from eatp.crypto import serialize_for_signing, sign, verify_signature
from eatp.reasoning import ConfidentialityLevel, ReasoningTrace

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# W3C VC Data Model 2.0 Constants
# ---------------------------------------------------------------------------

W3C_CREDENTIALS_V2_CONTEXT = "https://www.w3.org/ns/credentials/v2"
EATP_CONTEXT_URL = "https://eatp.dev/ns/credentials/v1"

_CHAIN_VC_TYPE = ["VerifiableCredential", "EATPTrustChain"]
_CAPABILITY_VC_TYPE = ["VerifiableCredential", "EATPCapabilityAttestation"]

_PROOF_TYPE = "Ed25519Signature2020"
_PROOF_PURPOSE = "assertionMethod"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_contexts() -> list:
    """Return the @context array for an EATP Verifiable Credential."""
    return [W3C_CREDENTIALS_V2_CONTEXT, EATP_CONTEXT_URL]


def _iso(dt: datetime) -> str:
    """Format a datetime as ISO 8601 with timezone info.

    Raises:
        ValueError: If the datetime is naive (no timezone).
    """
    if dt.tzinfo is None:
        raise ValueError(f"datetime must be timezone-aware, got naive datetime: {dt!r}")
    return dt.isoformat()


def _iso_optional(dt: Optional[datetime]) -> Optional[str]:
    """Format an optional datetime; returns None when input is None."""
    if dt is None:
        return None
    return _iso(dt)


def _make_vc_id(record_id: str) -> str:
    """Generate a URN-format VC identifier from an EATP record ID."""
    return f"urn:eatp:vc:{record_id}"


def _serialize_genesis(genesis: GenesisRecord) -> Dict[str, Any]:
    """Serialize a GenesisRecord into W3C VC camelCase credentialSubject form."""
    result: Dict[str, Any] = {
        "id": genesis.id,
        "agentId": genesis.agent_id,
        "authorityId": genesis.authority_id,
        "authorityType": genesis.authority_type.value,
        "createdAt": _iso(genesis.created_at),
        "signatureAlgorithm": genesis.signature_algorithm,
        "signature": genesis.signature,
        "metadata": genesis.metadata,
    }
    if genesis.expires_at is not None:
        result["expiresAt"] = _iso(genesis.expires_at)
    return result


def _serialize_capability(cap: CapabilityAttestation) -> Dict[str, Any]:
    """Serialize a CapabilityAttestation into W3C VC camelCase form."""
    result: Dict[str, Any] = {
        "id": cap.id,
        "capability": cap.capability,
        "capabilityType": cap.capability_type.value,
        "constraints": list(cap.constraints),
        "attesterId": cap.attester_id,
        "attestedAt": _iso(cap.attested_at),
        "signature": cap.signature,
    }
    if cap.expires_at is not None:
        result["expiresAt"] = _iso(cap.expires_at)
    if cap.scope is not None:
        result["scope"] = cap.scope
    return result


def _serialize_reasoning_trace(trace: ReasoningTrace) -> Dict[str, Any]:
    """Serialize a ReasoningTrace into W3C VC camelCase form.

    Converts snake_case field names to camelCase for W3C VC compatibility.

    Args:
        trace: The reasoning trace to serialize.

    Returns:
        Dict with camelCase keys suitable for inclusion in credentialSubject.
    """
    return {
        "decision": trace.decision,
        "rationale": trace.rationale,
        "confidentiality": trace.confidentiality.value,
        "timestamp": trace.timestamp.isoformat(),
        "alternativesConsidered": trace.alternatives_considered,
        "evidence": trace.evidence,
        "methodology": trace.methodology,
        "confidence": trace.confidence,
    }


def _serialize_delegation(d: DelegationRecord) -> Dict[str, Any]:
    """Serialize a DelegationRecord into W3C VC camelCase form.

    Reasoning trace handling follows confidentiality-based selective disclosure:
    - PUBLIC / RESTRICTED: full reasoning trace included in ``reasoning`` key
    - CONFIDENTIAL / SECRET / TOP_SECRET: trace content withheld, only hash included
    - ``reasoningTraceHash`` and ``reasoningSignature`` are always included when present
      (they are not confidential — they are integrity proofs)
    """
    result: Dict[str, Any] = {
        "id": d.id,
        "delegatorId": d.delegator_id,
        "delegateeId": d.delegatee_id,
        "taskId": d.task_id,
        "capabilitiesDelegated": list(d.capabilities_delegated),
        "constraintSubset": list(d.constraint_subset),
        "delegatedAt": _iso(d.delegated_at),
        "signature": d.signature,
    }
    if d.expires_at is not None:
        result["expiresAt"] = _iso(d.expires_at)
    if d.parent_delegation_id is not None:
        result["parentDelegationId"] = d.parent_delegation_id

    # --- Reasoning trace extension (selective disclosure by confidentiality) ---
    if d.reasoning_trace is not None:
        if d.reasoning_trace.confidentiality <= ConfidentialityLevel.RESTRICTED:
            # PUBLIC or RESTRICTED: include full trace content
            result["reasoning"] = _serialize_reasoning_trace(d.reasoning_trace)
        else:
            # CONFIDENTIAL, SECRET, TOP_SECRET: withhold trace content
            logger.debug(
                "Reasoning trace withheld from VC export for delegation %s (confidentiality=%s > RESTRICTED)",
                d.id,
                d.reasoning_trace.confidentiality.value,
            )

    # Hash and signature are always included when present (not confidential)
    if d.reasoning_trace_hash is not None:
        result["reasoningTraceHash"] = d.reasoning_trace_hash
    if d.reasoning_signature is not None:
        result["reasoningSignature"] = d.reasoning_signature

    return result


def _serialize_constraint_envelope(
    env: Optional[ConstraintEnvelope],
) -> Optional[Dict[str, Any]]:
    """Serialize a ConstraintEnvelope into W3C VC camelCase form."""
    if env is None:
        return None
    return {
        "id": env.id,
        "agentId": env.agent_id,
        "constraintHash": env.constraint_hash,
        "activeConstraints": [
            {
                "id": c.id,
                "constraintType": c.constraint_type.value,
                "value": c.value,
                "source": c.source,
                "priority": c.priority,
            }
            for c in env.active_constraints
        ],
    }


def _compute_earliest_expiry(chain: TrustLineageChain) -> Optional[datetime]:
    """Find the earliest expiration across genesis, capabilities, delegations.

    Returns None when nothing in the chain expires.
    """
    candidates: list[datetime] = []
    if chain.genesis.expires_at is not None:
        candidates.append(chain.genesis.expires_at)
    for cap in chain.capabilities:
        if cap.expires_at is not None:
            candidates.append(cap.expires_at)
    for d in chain.delegations:
        if d.expires_at is not None:
            candidates.append(d.expires_at)
    if not candidates:
        return None
    return min(candidates)


def _build_signing_payload(vc_without_proof: Dict[str, Any]) -> str:
    """Build the canonical signing payload from a VC (without proof).

    Uses the same deterministic serialization as eatp.crypto.serialize_for_signing
    to ensure consistent signing/verification.
    """
    return serialize_for_signing(vc_without_proof)


def _create_proof(
    vc_without_proof: Dict[str, Any],
    issuer_did: str,
    signing_key: str,
) -> Dict[str, Any]:
    """Create an Ed25519Signature2020 proof for a VC document.

    Args:
        vc_without_proof: The complete VC dict minus the proof field.
        issuer_did: DID of the issuer (used in verificationMethod).
        signing_key: Base64-encoded Ed25519 private key.

    Returns:
        Proof dict suitable for inclusion in the VC.

    Raises:
        ValueError: If signing fails due to invalid key.
    """
    payload = _build_signing_payload(vc_without_proof)
    try:
        signature_b64 = sign(payload, signing_key)
    except ValueError as exc:
        raise ValueError(f"Failed to sign credential: invalid signing_key — {exc}") from exc

    return {
        "type": _PROOF_TYPE,
        "created": _iso(datetime.now(timezone.utc)),
        "verificationMethod": f"{issuer_did}#key-1",
        "proofPurpose": _PROOF_PURPOSE,
        "proofValue": signature_b64,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def export_as_verifiable_credential(
    chain: TrustLineageChain,
    issuer_did: str,
    signing_key: str,
) -> Dict[str, Any]:
    """Export a TrustLineageChain as a W3C Verifiable Credential.

    Produces a VC Data Model 2.0 compliant JSON-LD document with
    Ed25519Signature2020 proof.

    Args:
        chain: The EATP trust lineage chain to export.
        issuer_did: DID of the credential issuer (e.g. "did:eatp:org:acme").
        signing_key: Base64-encoded Ed25519 private key for signing.

    Returns:
        W3C VC dict with @context, type, issuer, validFrom, credentialSubject, proof.

    Raises:
        ValueError: If issuer_did is empty.
        ValueError: If signing_key is invalid or empty.
    """
    if not issuer_did or not issuer_did.strip():
        raise ValueError("issuer_did must be a non-empty DID string, got empty value")
    if not signing_key or not signing_key.strip():
        raise ValueError("signing_key must be a non-empty base64-encoded Ed25519 private key")

    credential_subject: Dict[str, Any] = {
        "genesis": _serialize_genesis(chain.genesis),
        "capabilities": [_serialize_capability(c) for c in chain.capabilities],
        "delegations": [_serialize_delegation(d) for d in chain.delegations],
        "constraintEnvelope": _serialize_constraint_envelope(chain.constraint_envelope),
        "chainHash": chain.hash(),
    }

    vc: Dict[str, Any] = {
        "@context": _build_contexts(),
        "id": _make_vc_id(chain.genesis.id),
        "type": list(_CHAIN_VC_TYPE),
        "issuer": issuer_did,
        "validFrom": _iso(chain.genesis.created_at),
        "credentialSubject": credential_subject,
    }

    earliest_expiry = _compute_earliest_expiry(chain)
    if earliest_expiry is not None:
        vc["validUntil"] = _iso(earliest_expiry)

    proof = _create_proof(vc, issuer_did, signing_key)
    vc["proof"] = proof

    logger.debug(
        "Exported TrustLineageChain as VC: agent_id=%s, vc_id=%s",
        chain.genesis.agent_id,
        vc["id"],
    )
    return vc


def export_capability_as_vc(
    attestation: CapabilityAttestation,
    issuer_did: str,
    signing_key: str,
) -> Dict[str, Any]:
    """Export a single CapabilityAttestation as a W3C Verifiable Credential.

    Args:
        attestation: The capability attestation to export.
        issuer_did: DID of the credential issuer.
        signing_key: Base64-encoded Ed25519 private key for signing.

    Returns:
        W3C VC dict for the single capability.

    Raises:
        ValueError: If issuer_did is empty.
        ValueError: If signing_key is invalid or empty.
    """
    if not issuer_did or not issuer_did.strip():
        raise ValueError("issuer_did must be a non-empty DID string, got empty value")
    if not signing_key or not signing_key.strip():
        raise ValueError("signing_key must be a non-empty base64-encoded Ed25519 private key")

    credential_subject = _serialize_capability(attestation)

    vc: Dict[str, Any] = {
        "@context": _build_contexts(),
        "id": _make_vc_id(attestation.id),
        "type": list(_CAPABILITY_VC_TYPE),
        "issuer": issuer_did,
        "validFrom": _iso(attestation.attested_at),
        "credentialSubject": credential_subject,
    }

    if attestation.expires_at is not None:
        vc["validUntil"] = _iso(attestation.expires_at)

    proof = _create_proof(vc, issuer_did, signing_key)
    vc["proof"] = proof

    logger.debug(
        "Exported CapabilityAttestation as VC: capability=%s, vc_id=%s",
        attestation.capability,
        vc["id"],
    )
    return vc


def verify_credential(credential: Dict[str, Any], public_key: str) -> bool:
    """Verify a W3C Verifiable Credential's Ed25519 proof.

    Reconstructs the signing payload from all fields except the proof,
    then verifies the Ed25519 signature against the provided public key.

    Args:
        credential: The W3C VC dict to verify.
        public_key: Base64-encoded Ed25519 public key.

    Returns:
        True if the signature is valid, False otherwise.

    Raises:
        ValueError: If proof is missing from the credential.
        ValueError: If proofValue is missing from the proof.
        ValueError: If public_key is empty or invalid.
    """
    if not public_key or not public_key.strip():
        raise ValueError("public_key must be a non-empty base64-encoded Ed25519 public key")

    if "proof" not in credential:
        raise ValueError("Credential is missing 'proof' field — cannot verify an unsigned credential")

    proof = credential["proof"]
    if "proofValue" not in proof:
        raise ValueError("Credential proof is missing 'proofValue' — the signature is required for verification")

    signature_b64 = proof["proofValue"]

    # Reconstruct the VC-without-proof for verification
    vc_without_proof = {k: v for k, v in credential.items() if k != "proof"}
    payload = _build_signing_payload(vc_without_proof)

    try:
        return verify_signature(payload, signature_b64, public_key)
    except Exception as exc:
        # InvalidSignatureError or other crypto errors from verify_signature
        # are raised for structural problems (bad key format, etc.)
        raise ValueError(f"public_key is invalid or signature verification encountered an error: {exc}") from exc


def import_from_verifiable_credential(
    credential: Dict[str, Any],
    public_key: str | None = None,
) -> TrustLineageChain:
    """Reconstruct a TrustLineageChain from a W3C Verifiable Credential.

    Validates the VC structure (context, type, credentialSubject) and
    deserializes the EATP chain data back into SDK objects.

    When ``public_key`` is provided, the proof is verified before import.
    Without a key, a warning is logged since importing unverified
    credentials is a security risk.

    Args:
        credential: The W3C VC dict to import.
        public_key: Optional Ed25519 public key for proof verification.

    Returns:
        TrustLineageChain reconstructed from the credential.

    Raises:
        ValueError: If the credential is missing required W3C VC fields.
        ValueError: If the credentialSubject is missing EATP chain data.
        ValueError: If public_key is provided and verification fails.
    """
    if public_key is not None:
        if not verify_credential(credential, public_key):
            raise ValueError("W3C VC proof verification failed — credential may be forged")
    else:
        logger.warning(
            "[W3C-VC] Importing credential WITHOUT proof verification. "
            "Pass public_key to import_from_verifiable_credential() "
            "to verify the cryptographic proof."
        )

    # --- Validate @context ---
    context = credential.get("@context", [])
    if W3C_CREDENTIALS_V2_CONTEXT not in context:
        raise ValueError(f"Invalid credential @context: must include '{W3C_CREDENTIALS_V2_CONTEXT}', got {context!r}")
    if EATP_CONTEXT_URL not in context:
        raise ValueError(
            f"Invalid credential @context: must include EATP context '{EATP_CONTEXT_URL}', got {context!r}"
        )

    # --- Validate type ---
    vc_type = credential.get("type", [])
    if "EATPTrustChain" not in vc_type:
        raise ValueError(f"Invalid credential type: must include 'EATPTrustChain', got {vc_type!r}")

    # --- Validate credentialSubject ---
    if "credentialSubject" not in credential:
        raise ValueError(
            "Credential is missing 'credentialSubject' field — cannot reconstruct trust chain without chain data"
        )

    subject = credential["credentialSubject"]

    if "genesis" not in subject:
        raise ValueError(
            "Credential credentialSubject is missing 'genesis' field — every EATP trust chain requires a genesis record"
        )

    # --- Deserialize genesis ---
    g = subject["genesis"]
    genesis = GenesisRecord(
        id=g["id"],
        agent_id=g["agentId"],
        authority_id=g["authorityId"],
        authority_type=AuthorityType(g["authorityType"]),
        created_at=datetime.fromisoformat(g["createdAt"]),
        expires_at=(datetime.fromisoformat(g["expiresAt"]) if g.get("expiresAt") else None),
        signature=g.get("signature", ""),
        signature_algorithm=g.get("signatureAlgorithm", "Ed25519"),
        metadata=g.get("metadata", {}),
    )

    # --- Deserialize capabilities ---
    capabilities: list[CapabilityAttestation] = []
    for c in subject.get("capabilities", []):
        capabilities.append(
            CapabilityAttestation(
                id=c["id"],
                capability=c["capability"],
                capability_type=CapabilityType(c["capabilityType"]),
                constraints=c.get("constraints", []),
                attester_id=c["attesterId"],
                attested_at=datetime.fromisoformat(c["attestedAt"]),
                expires_at=(datetime.fromisoformat(c["expiresAt"]) if c.get("expiresAt") else None),
                signature=c.get("signature", ""),
                scope=c.get("scope"),
            )
        )

    # --- Deserialize delegations ---
    delegations: list[DelegationRecord] = []
    for d in subject.get("delegations", []):
        # Reasoning trace extension (backward compatible — None if absent)
        reasoning_trace = None
        reasoning_data = d.get("reasoning")
        if reasoning_data is not None:
            # Convert camelCase VC keys back to snake_case for ReasoningTrace.from_dict()
            reasoning_trace = ReasoningTrace.from_dict(
                {
                    "decision": reasoning_data["decision"],
                    "rationale": reasoning_data["rationale"],
                    "confidentiality": reasoning_data["confidentiality"],
                    "timestamp": reasoning_data["timestamp"],
                    "alternatives_considered": reasoning_data.get("alternativesConsidered", []),
                    "evidence": reasoning_data.get("evidence", []),
                    "methodology": reasoning_data.get("methodology"),
                    "confidence": reasoning_data.get("confidence"),
                }
            )

        delegations.append(
            DelegationRecord(
                id=d["id"],
                delegator_id=d["delegatorId"],
                delegatee_id=d["delegateeId"],
                task_id=d["taskId"],
                capabilities_delegated=d.get("capabilitiesDelegated", []),
                constraint_subset=d.get("constraintSubset", []),
                delegated_at=datetime.fromisoformat(d["delegatedAt"]),
                expires_at=(datetime.fromisoformat(d["expiresAt"]) if d.get("expiresAt") else None),
                signature=d.get("signature", ""),
                parent_delegation_id=d.get("parentDelegationId"),
                reasoning_trace=reasoning_trace,
                reasoning_trace_hash=d.get("reasoningTraceHash"),
                reasoning_signature=d.get("reasoningSignature"),
            )
        )

    # --- Deserialize constraint envelope ---
    constraint_envelope = None
    env_data = subject.get("constraintEnvelope")
    if env_data is not None:
        constraint_envelope = ConstraintEnvelope(
            id=env_data["id"],
            agent_id=env_data["agentId"],
            constraint_hash=env_data.get("constraintHash", ""),
            active_constraints=[
                Constraint(
                    id=ac["id"],
                    constraint_type=ConstraintType(ac["constraintType"]),
                    value=ac["value"],
                    source=ac["source"],
                    priority=ac.get("priority", 0),
                )
                for ac in env_data.get("activeConstraints", [])
            ],
        )

    chain = TrustLineageChain(
        genesis=genesis,
        capabilities=capabilities,
        delegations=delegations,
        constraint_envelope=constraint_envelope,
    )

    logger.debug(
        "Imported TrustLineageChain from VC: agent_id=%s, caps=%d, delegations=%d",
        genesis.agent_id,
        len(capabilities),
        len(delegations),
    )
    return chain
