"""Generate wire format fixtures for cross-language compatibility testing.

Produces JSON fixture files from the Python EATP SDK that can be loaded
and verified by the Rust SDK (and vice versa) to ensure wire format
compatibility.

Usage:
    cd packages/eatp
    python -m tests.fixtures.wire_format.generate_fixtures
"""

import json
import os
from datetime import datetime, timezone

from eatp.chain import (
    ActionResult,
    AuditAnchor,
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    Constraint,
    ConstraintEnvelope,
    ConstraintType,
    DelegationRecord,
    GenesisRecord,
    TrustLineageChain,
    VerificationLevel,
    VerificationResult,
)
from eatp.crypto import generate_keypair, hash_chain, sign

FIXTURE_DIR = os.path.dirname(os.path.abspath(__file__))
TIMESTAMP = "2025-01-15T10:30:00+00:00"
TIMESTAMP_DT = datetime.fromisoformat(TIMESTAMP)


def generate_keypair_fixture():
    """Generate a deterministic-looking keypair fixture."""
    priv, pub = generate_keypair()
    return priv, pub


def generate_genesis_record(priv_key: str, pub_key: str) -> dict:
    """Generate a genesis record fixture."""
    genesis = GenesisRecord(
        id="gen-12345678-1234-1234-1234-123456789012",
        agent_id="agent-001",
        authority_id="org-acme",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=TIMESTAMP_DT,
        signature="",  # Will be signed below
        signature_algorithm="Ed25519",
        expires_at=datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        metadata={"department": "engineering", "owner": "admin@acme.com"},
    )
    # Sign the record
    payload = genesis.to_signing_payload()
    genesis.signature = sign(payload, priv_key)

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


def generate_capability_attestation(priv_key: str) -> dict:
    """Generate a capability attestation fixture."""
    cap = CapabilityAttestation(
        id="cap-12345678-1234-1234-1234-123456789012",
        capability="analyze_data",
        capability_type=CapabilityType.ACTION,
        constraints=["read_only", "no_pii"],
        attester_id="org-acme",
        attested_at=TIMESTAMP_DT,
        signature="",
        expires_at=datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        scope={"tables": ["transactions", "reports"]},
    )
    payload = cap.to_signing_payload()
    cap.signature = sign(payload, priv_key)

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


def generate_delegation_record(priv_key: str) -> dict:
    """Generate a delegation record fixture."""
    delegation = DelegationRecord(
        id="del-12345678-1234-1234-1234-123456789012",
        delegator_id="agent-001",
        delegatee_id="agent-002",
        task_id="task-analysis-001",
        capabilities_delegated=["analyze_data"],
        constraint_subset=["read_only", "no_pii", "max_100_records"],
        delegated_at=TIMESTAMP_DT,
        signature="",
        expires_at=datetime(2025, 7, 15, 10, 30, 0, tzinfo=timezone.utc),
        parent_delegation_id=None,
        delegation_chain=["org-acme", "agent-001", "agent-002"],
        delegation_depth=1,
    )
    payload = delegation.to_signing_payload()
    delegation.signature = sign(payload, priv_key)

    return delegation.to_dict()


def generate_audit_anchor(priv_key: str) -> dict:
    """Generate an audit anchor fixture."""
    chain_hash = hash_chain({"genesis_id": "gen-12345678-1234-1234-1234-123456789012"})
    anchor = AuditAnchor(
        id="aud-12345678-1234-1234-1234-123456789012",
        agent_id="agent-001",
        action="analyze_data",
        timestamp=TIMESTAMP_DT,
        trust_chain_hash=chain_hash,
        result=ActionResult.SUCCESS,
        signature="",
        resource="transactions_table",
        parent_anchor_id=None,
        context={"records_analyzed": 42, "duration_ms": 150},
    )
    payload = anchor.to_signing_payload()
    anchor.signature = sign(payload, priv_key)

    return anchor.to_dict()


def generate_constraint_envelope() -> dict:
    """Generate a constraint envelope fixture."""
    envelope = ConstraintEnvelope(
        id="env-agent-001",
        agent_id="agent-001",
        active_constraints=[
            Constraint(
                id="c-001",
                constraint_type=ConstraintType.FINANCIAL,
                value="max_api_calls:1000",
                source="cap-001",
                priority=1,
            ),
            Constraint(
                id="c-002",
                constraint_type=ConstraintType.TEMPORAL,
                value="business_hours_only",
                source="cap-001",
                priority=2,
            ),
            Constraint(
                id="c-003",
                constraint_type=ConstraintType.DATA_ACCESS,
                value="department_data_only",
                source="del-001",
                priority=1,
            ),
        ],
    )

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
        "computed_at": (envelope.computed_at.isoformat() if envelope.computed_at else None),
        "valid_until": envelope.valid_until,
    }


def generate_verification_verdict() -> dict:
    """Generate a verification verdict fixture."""
    result = VerificationResult(
        valid=True,
        level=VerificationLevel.STANDARD,
        reason=None,
        capability_used="analyze_data",
        effective_constraints=["read_only", "no_pii"],
        violations=[],
    )
    return {
        "valid": result.valid,
        "level": result.level.value,
        "reason": result.reason,
        "capability_used": result.capability_used,
        "effective_constraints": result.effective_constraints,
        "violations": result.violations,
    }


def generate_full_chain(priv_key: str, pub_key: str) -> dict:
    """Generate a full TrustLineageChain fixture."""
    genesis = GenesisRecord(
        id="gen-12345678-1234-1234-1234-123456789012",
        agent_id="agent-001",
        authority_id="org-acme",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=TIMESTAMP_DT,
        signature=sign(
            {
                "id": "gen-12345678-1234-1234-1234-123456789012",
                "agent_id": "agent-001",
                "authority_id": "org-acme",
                "authority_type": "organization",
                "created_at": TIMESTAMP,
                "expires_at": None,
                "metadata": {},
            },
            priv_key,
        ),
    )

    cap = CapabilityAttestation(
        id="cap-12345678-1234-1234-1234-123456789012",
        capability="analyze_data",
        capability_type=CapabilityType.ACTION,
        constraints=["read_only"],
        attester_id="org-acme",
        attested_at=TIMESTAMP_DT,
        signature=sign({"capability": "analyze_data"}, priv_key),
    )

    chain = TrustLineageChain(genesis=genesis, capabilities=[cap])
    return chain.to_dict()


def main():
    """Generate all fixtures."""
    priv_key, pub_key = generate_keypair_fixture()

    fixtures = {
        "genesis-record": generate_genesis_record(priv_key, pub_key),
        "capability-attestation": generate_capability_attestation(priv_key),
        "delegation-record": generate_delegation_record(priv_key),
        "audit-anchor": generate_audit_anchor(priv_key),
        "constraint-envelope": generate_constraint_envelope(),
        "verification-verdict": generate_verification_verdict(),
        "full-chain": generate_full_chain(priv_key, pub_key),
    }

    # Save keypair for verification
    keypair = {"private_key": priv_key, "public_key": pub_key}
    with open(os.path.join(FIXTURE_DIR, "keypair.json"), "w") as f:
        json.dump(keypair, f, indent=2)

    # Save each fixture
    for name, data in fixtures.items():
        filepath = os.path.join(FIXTURE_DIR, f"{name}.fixture.json")
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Generated: {filepath}")

    # Save manifest
    manifest = {
        "generated_by": "python-eatp-sdk",
        "version": "0.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fixtures": list(fixtures.keys()),
        "crypto": {"algorithm": "Ed25519", "library": "PyNaCl"},
    }
    with open(os.path.join(FIXTURE_DIR, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nGenerated {len(fixtures)} fixtures + keypair + manifest")


if __name__ == "__main__":
    main()
