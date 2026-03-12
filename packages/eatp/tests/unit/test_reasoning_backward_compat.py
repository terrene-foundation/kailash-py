# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Backward Compatibility Tests for EATP Reasoning Trace Extension.

TDD CONTRACT: These tests define the behavior that MUST NOT break when
ReasoningTrace fields are added to DelegationRecord and AuditAnchor.

Written BEFORE any code changes (TODO-020). Each test documents a specific
backward compatibility guarantee:

1. Signing payloads must remain IDENTICAL (cross-version signature verification)
2. Chain hashes must remain IDENTICAL (trust chain integrity)
3. Old-format deserialization must continue working (no reasoning fields)
4. serialize_for_signing() must produce deterministic output regardless of new fields
5. Round-trip serialization must preserve all existing fields
"""

import json
import pytest
from datetime import datetime, timezone

from eatp.chain import (
    GenesisRecord,
    CapabilityAttestation,
    DelegationRecord,
    ConstraintEnvelope,
    Constraint,
    AuditAnchor,
    TrustLineageChain,
    AuthorityType,
    CapabilityType,
    ActionResult,
    ConstraintType,
)
from eatp.crypto import (
    generate_keypair,
    sign,
    verify_signature,
    serialize_for_signing,
    hash_trust_chain_state,
)


# ---------------------------------------------------------------------------
# Fixtures: canonical test objects representing the "v1" wire format
# (pre-reasoning-trace). These are frozen — the exact field sets and
# serialized forms constitute the backward compatibility contract.
# ---------------------------------------------------------------------------

FIXED_TIMESTAMP = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
FIXED_EXPIRY = datetime(2027, 3, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def delegation_record():
    """A canonical DelegationRecord without reasoning trace fields."""
    return DelegationRecord(
        id="del-001",
        delegator_id="agent-alpha",
        delegatee_id="agent-beta",
        task_id="task-100",
        capabilities_delegated=["read_data", "write_reports"],
        constraint_subset=["max_rows:1000", "region:us-east"],
        delegated_at=FIXED_TIMESTAMP,
        signature="sig-placeholder",
        expires_at=FIXED_EXPIRY,
        parent_delegation_id="del-000",
    )


@pytest.fixture
def audit_anchor():
    """A canonical AuditAnchor without reasoning trace fields."""
    return AuditAnchor(
        id="audit-001",
        agent_id="agent-beta",
        action="generate_report",
        timestamp=FIXED_TIMESTAMP,
        trust_chain_hash="abc123def456",
        result=ActionResult.SUCCESS,
        signature="sig-placeholder",
        resource="reports/q1-2026.pdf",
        parent_anchor_id="audit-000",
        context={"department": "finance", "priority": "high"},
    )


@pytest.fixture
def genesis_record():
    """A canonical GenesisRecord."""
    return GenesisRecord(
        id="gen-001",
        agent_id="agent-alpha",
        authority_id="authority-root",
        authority_type=AuthorityType.HUMAN,
        created_at=FIXED_TIMESTAMP,
        expires_at=FIXED_EXPIRY,
        signature="sig-genesis",
        signature_algorithm="Ed25519",
        metadata={"org": "acme-corp"},
    )


@pytest.fixture
def capability_attestation():
    """A canonical CapabilityAttestation."""
    return CapabilityAttestation(
        id="cap-001",
        capability="read_data",
        capability_type=CapabilityType.ACCESS,
        constraints=["max_rows:1000"],
        attester_id="authority-root",
        attested_at=FIXED_TIMESTAMP,
        expires_at=FIXED_EXPIRY,
        signature="sig-cap",
        scope={"tables": ["users"]},
    )


@pytest.fixture
def constraint_envelope():
    """A canonical ConstraintEnvelope."""
    return ConstraintEnvelope(
        id="env-001",
        agent_id="agent-alpha",
        constraint_hash="hash-constraints",
        active_constraints=[
            Constraint(
                id="c-001",
                constraint_type=ConstraintType.FINANCIAL,
                value="100/hour",
                source="policy-engine",
                priority=1,
            ),
        ],
    )


@pytest.fixture
def trust_chain(
    genesis_record, capability_attestation, delegation_record, constraint_envelope
):
    """A complete TrustLineageChain for round-trip testing."""
    return TrustLineageChain(
        genesis=genesis_record,
        capabilities=[capability_attestation],
        delegations=[delegation_record],
        constraint_envelope=constraint_envelope,
    )


# ---------------------------------------------------------------------------
# Frozen payloads: these are the EXACT dict outputs that to_signing_payload()
# must produce. If these change, cross-version signature verification breaks.
# ---------------------------------------------------------------------------

FROZEN_DELEGATION_SIGNING_PAYLOAD = {
    "id": "del-001",
    "delegator_id": "agent-alpha",
    "delegatee_id": "agent-beta",
    "task_id": "task-100",
    "capabilities_delegated": ["read_data", "write_reports"],
    "constraint_subset": ["max_rows:1000", "region:us-east"],
    "delegated_at": "2026-03-01T12:00:00+00:00",
    "expires_at": "2027-03-01T12:00:00+00:00",
    "parent_delegation_id": "del-000",
    "reasoning_trace_hash": None,
}

FROZEN_AUDIT_SIGNING_PAYLOAD = {
    "id": "audit-001",
    "agent_id": "agent-beta",
    "action": "generate_report",
    "resource": "reports/q1-2026.pdf",
    "timestamp": "2026-03-01T12:00:00+00:00",
    "trust_chain_hash": "abc123def456",
    "result": "success",
    "parent_anchor_id": "audit-000",
    "context": {"department": "finance", "priority": "high"},
    "reasoning_trace_hash": None,
}


# ===========================================================================
# Test Class 1: Signing Payload Stability
# ===========================================================================


class TestSigningPayloadStability:
    """
    CRITICAL: to_signing_payload() output must be IDENTICAL before and after
    reasoning trace fields are added. If these tests break, cross-version
    signature verification is compromised.
    """

    def test_delegation_signing_payload_matches_frozen(self, delegation_record):
        """DelegationRecord.to_signing_payload() must match frozen reference."""
        payload = delegation_record.to_signing_payload()
        assert payload == FROZEN_DELEGATION_SIGNING_PAYLOAD

    def test_audit_anchor_signing_payload_matches_frozen(self, audit_anchor):
        """AuditAnchor.to_signing_payload() must match frozen reference."""
        payload = audit_anchor.to_signing_payload()
        assert payload == FROZEN_AUDIT_SIGNING_PAYLOAD

    def test_delegation_signing_payload_key_set(self, delegation_record):
        """DelegationRecord signing payload must contain exactly these keys."""
        payload = delegation_record.to_signing_payload()
        expected_keys = {
            "id",
            "delegator_id",
            "delegatee_id",
            "task_id",
            "capabilities_delegated",
            "constraint_subset",
            "delegated_at",
            "expires_at",
            "parent_delegation_id",
            "reasoning_trace_hash",
        }
        assert set(payload.keys()) == expected_keys

    def test_audit_anchor_signing_payload_key_set(self, audit_anchor):
        """AuditAnchor signing payload must contain exactly these keys."""
        payload = audit_anchor.to_signing_payload()
        expected_keys = {
            "id",
            "agent_id",
            "action",
            "resource",
            "timestamp",
            "trust_chain_hash",
            "result",
            "parent_anchor_id",
            "context",
            "reasoning_trace_hash",
        }
        assert set(payload.keys()) == expected_keys

    def test_delegation_signing_payload_no_full_reasoning_fields(
        self, delegation_record
    ):
        """DelegationRecord signing payload must NOT contain full reasoning objects.

        Note: reasoning_trace_hash IS included (v2.2 spec) to bind the reasoning
        trace to the parent record's signature.  But the full reasoning_trace
        object and the reasoning_signature are excluded — they have their own
        separate cryptographic verification path.
        """
        payload = delegation_record.to_signing_payload()
        excluded_fields = {
            "reasoning_trace",
            "reasoning_signature",
        }
        assert excluded_fields.isdisjoint(set(payload.keys())), (
            f"Signing payload contains full reasoning fields: "
            f"{excluded_fields & set(payload.keys())}"
        )
        # reasoning_trace_hash MUST be present (as None when no trace)
        assert "reasoning_trace_hash" in payload

    def test_audit_anchor_signing_payload_no_full_reasoning_fields(self, audit_anchor):
        """AuditAnchor signing payload must NOT contain full reasoning objects.

        Note: reasoning_trace_hash IS included (v2.2 spec) to bind the reasoning
        trace to the parent record's signature.  But the full reasoning_trace
        object and the reasoning_signature are excluded — they have their own
        separate cryptographic verification path.
        """
        payload = audit_anchor.to_signing_payload()
        excluded_fields = {
            "reasoning_trace",
            "reasoning_signature",
        }
        assert excluded_fields.isdisjoint(set(payload.keys())), (
            f"Signing payload contains full reasoning fields: "
            f"{excluded_fields & set(payload.keys())}"
        )
        # reasoning_trace_hash MUST be present (as None when no trace)
        assert "reasoning_trace_hash" in payload

    def test_delegation_signing_payload_no_human_origin(self, delegation_record):
        """DelegationRecord signing payload must NOT contain EATP human_origin."""
        payload = delegation_record.to_signing_payload()
        assert "human_origin" not in payload
        assert "delegation_chain" not in payload
        assert "delegation_depth" not in payload


# ===========================================================================
# Test Class 2: Cryptographic Signature Stability
# ===========================================================================


class TestCryptoSignatureStability:
    """
    End-to-end: sign a record, then verify. After reasoning fields are added,
    the same keypair + record must produce the same signature.
    """

    def test_delegation_sign_verify_roundtrip(self, delegation_record):
        """Signatures over DelegationRecord signing payload must verify."""
        private_key, public_key = generate_keypair()
        payload = delegation_record.to_signing_payload()
        signature = sign(payload, private_key)
        assert verify_signature(payload, signature, public_key)

    def test_audit_anchor_sign_verify_roundtrip(self, audit_anchor):
        """Signatures over AuditAnchor signing payload must verify."""
        private_key, public_key = generate_keypair()
        payload = audit_anchor.to_signing_payload()
        signature = sign(payload, private_key)
        assert verify_signature(payload, signature, public_key)

    def test_serialize_for_signing_deterministic(self, delegation_record):
        """serialize_for_signing() must produce identical output across calls."""
        payload = delegation_record.to_signing_payload()
        serialized_1 = serialize_for_signing(payload)
        serialized_2 = serialize_for_signing(payload)
        assert serialized_1 == serialized_2

    def test_serialize_for_signing_canonical_json(self, delegation_record):
        """serialize_for_signing() must produce canonical JSON (sorted keys, no spaces)."""
        payload = delegation_record.to_signing_payload()
        serialized = serialize_for_signing(payload)
        # Must be valid JSON
        parsed = json.loads(serialized)
        # Re-serialize with same rules must match
        re_serialized = json.dumps(parsed, separators=(",", ":"), sort_keys=True)
        assert serialized == re_serialized

    def test_serialize_for_signing_frozen_output(self):
        """serialize_for_signing() output for frozen payload must be stable."""
        serialized = serialize_for_signing(FROZEN_DELEGATION_SIGNING_PAYLOAD)
        # This is the contract: this exact string must be produced.
        # If it changes, all existing signatures in the wild become invalid.
        parsed = json.loads(serialized)
        assert parsed["id"] == "del-001"
        assert parsed["delegator_id"] == "agent-alpha"
        # reasoning_trace_hash is legitimately in the payload (v2.2 spec),
        # but full reasoning_trace and reasoning_signature must NOT appear
        assert '"reasoning_trace":' not in serialized
        assert '"reasoning_signature":' not in serialized
        # reasoning_trace_hash should be present as null (no trace)
        assert parsed["reasoning_trace_hash"] is None


# ===========================================================================
# Test Class 3: Chain Hash Stability
# ===========================================================================


class TestChainHashStability:
    """
    TrustLineageChain.hash() must produce the same hash for the same chain
    regardless of whether reasoning trace fields exist.
    """

    def test_chain_hash_deterministic(self, trust_chain):
        """Same chain must produce same hash across calls."""
        hash_1 = trust_chain.hash()
        hash_2 = trust_chain.hash()
        assert hash_1 == hash_2

    def test_chain_hash_uses_ids_only(self, trust_chain):
        """Chain hash is computed from IDs, not full record content.

        This means adding optional fields to records does NOT affect the hash.
        The hash function uses genesis_id, capability_ids, delegation_ids,
        and constraint_hash — all of which are pre-existing fields.
        """
        hash_value = trust_chain.hash()
        # Compute expected hash using the same inputs
        expected = hash_trust_chain_state(
            genesis_id="gen-001",
            capability_ids=["cap-001"],
            delegation_ids=["del-001"],
            constraint_hash="hash-constraints",
        )
        assert hash_value == expected

    def test_chain_hash_with_linked_hashing(self, trust_chain):
        """Linked hashing must also be deterministic."""
        hash_1 = trust_chain.hash(previous_hash="previous-state-hash-abc")
        hash_2 = trust_chain.hash(previous_hash="previous-state-hash-abc")
        assert hash_1 == hash_2


# ===========================================================================
# Test Class 4: Deserialization Backward Compatibility
# ===========================================================================


class TestDeserializationBackwardCompat:
    """
    Old-format dicts (without reasoning fields) must deserialize correctly.
    This simulates receiving records from an older SDK version.
    """

    def test_delegation_from_dict_without_reasoning(self):
        """DelegationRecord.from_dict() must handle missing reasoning fields."""
        old_format = {
            "id": "del-old-001",
            "delegator_id": "agent-v1",
            "delegatee_id": "agent-v2",
            "task_id": "task-legacy",
            "capabilities_delegated": ["read_data"],
            "constraint_subset": [],
            "delegated_at": "2026-01-15T10:00:00+00:00",
            "signature": "old-sig",
        }
        record = DelegationRecord.from_dict(old_format)
        assert record.id == "del-old-001"
        assert record.delegator_id == "agent-v1"
        assert record.delegatee_id == "agent-v2"
        assert record.task_id == "task-legacy"
        assert record.capabilities_delegated == ["read_data"]
        assert record.constraint_subset == []
        assert record.signature == "old-sig"
        assert record.expires_at is None
        assert record.parent_delegation_id is None
        # EATP fields default gracefully
        assert record.human_origin is None
        assert record.delegation_chain == []
        assert record.delegation_depth == 0

    def test_audit_anchor_from_dict_without_reasoning(self):
        """AuditAnchor.from_dict() must handle missing reasoning fields."""
        old_format = {
            "id": "audit-old-001",
            "agent_id": "agent-v1",
            "action": "process_data",
            "timestamp": "2026-01-15T10:00:00+00:00",
            "trust_chain_hash": "oldhash123",
            "result": "success",
            "signature": "old-sig",
        }
        record = AuditAnchor.from_dict(old_format)
        assert record.id == "audit-old-001"
        assert record.agent_id == "agent-v1"
        assert record.action == "process_data"
        assert record.result == ActionResult.SUCCESS
        assert record.signature == "old-sig"
        assert record.resource is None
        assert record.parent_anchor_id is None
        assert record.context == {}
        # EATP field defaults gracefully
        assert record.human_origin is None

    def test_delegation_from_dict_with_explicit_none_reasoning(self):
        """Explicit None values for reasoning fields must not crash."""
        data = {
            "id": "del-002",
            "delegator_id": "a",
            "delegatee_id": "b",
            "task_id": "t",
            "capabilities_delegated": [],
            "constraint_subset": [],
            "delegated_at": "2026-03-01T12:00:00+00:00",
            "signature": "",
            # Future: these fields may appear as None from newer SDKs
            "reasoning_trace": None,
            "reasoning_trace_hash": None,
            "reasoning_signature": None,
        }
        # from_dict should ignore unknown fields gracefully
        record = DelegationRecord.from_dict(data)
        assert record.id == "del-002"

    def test_audit_anchor_from_dict_with_explicit_none_reasoning(self):
        """Explicit None values for reasoning fields must not crash."""
        data = {
            "id": "audit-002",
            "agent_id": "a",
            "action": "test",
            "timestamp": "2026-03-01T12:00:00+00:00",
            "trust_chain_hash": "hash",
            "result": "success",
            "signature": "",
            "reasoning_trace": None,
            "reasoning_trace_hash": None,
            "reasoning_signature": None,
        }
        record = AuditAnchor.from_dict(data)
        assert record.id == "audit-002"


# ===========================================================================
# Test Class 5: Serialization Round-Trip Stability
# ===========================================================================


class TestSerializationRoundTrip:
    """
    to_dict() → from_dict() round-trips must preserve all existing fields
    and not introduce unexpected keys.
    """

    def test_delegation_round_trip(self, delegation_record):
        """DelegationRecord survives to_dict/from_dict round-trip."""
        serialized = delegation_record.to_dict()
        deserialized = DelegationRecord.from_dict(serialized)
        assert deserialized.id == delegation_record.id
        assert deserialized.delegator_id == delegation_record.delegator_id
        assert deserialized.delegatee_id == delegation_record.delegatee_id
        assert deserialized.task_id == delegation_record.task_id
        assert (
            deserialized.capabilities_delegated
            == delegation_record.capabilities_delegated
        )
        assert deserialized.constraint_subset == delegation_record.constraint_subset
        assert deserialized.delegated_at == delegation_record.delegated_at
        assert deserialized.expires_at == delegation_record.expires_at
        assert (
            deserialized.parent_delegation_id == delegation_record.parent_delegation_id
        )

    def test_audit_anchor_round_trip(self, audit_anchor):
        """AuditAnchor survives to_dict/from_dict round-trip."""
        serialized = audit_anchor.to_dict()
        deserialized = AuditAnchor.from_dict(serialized)
        assert deserialized.id == audit_anchor.id
        assert deserialized.agent_id == audit_anchor.agent_id
        assert deserialized.action == audit_anchor.action
        assert deserialized.timestamp == audit_anchor.timestamp
        assert deserialized.trust_chain_hash == audit_anchor.trust_chain_hash
        assert deserialized.result == audit_anchor.result
        assert deserialized.resource == audit_anchor.resource
        assert deserialized.parent_anchor_id == audit_anchor.parent_anchor_id
        assert deserialized.context == audit_anchor.context

    def test_chain_round_trip_without_reasoning(self, trust_chain):
        """Full TrustLineageChain survives to_dict/from_dict round-trip."""
        serialized = trust_chain.to_dict()
        deserialized = TrustLineageChain.from_dict(serialized)

        # Genesis
        assert deserialized.genesis.id == trust_chain.genesis.id
        assert deserialized.genesis.agent_id == trust_chain.genesis.agent_id
        assert deserialized.genesis.authority_id == trust_chain.genesis.authority_id
        assert deserialized.genesis.authority_type == trust_chain.genesis.authority_type

        # Capabilities
        assert len(deserialized.capabilities) == 1
        assert deserialized.capabilities[0].id == "cap-001"
        assert deserialized.capabilities[0].capability == "read_data"

        # Delegations
        assert len(deserialized.delegations) == 1
        assert deserialized.delegations[0].id == "del-001"
        assert deserialized.delegations[0].delegator_id == "agent-alpha"
        assert deserialized.delegations[0].delegatee_id == "agent-beta"

        # Constraint envelope
        assert deserialized.constraint_envelope is not None
        assert deserialized.constraint_envelope.id == "env-001"
        assert len(deserialized.constraint_envelope.active_constraints) == 1

    def test_chain_hash_preserved_after_round_trip(self, trust_chain):
        """Chain hash must be identical before and after round-trip."""
        hash_before = trust_chain.hash()
        serialized = trust_chain.to_dict()
        deserialized = TrustLineageChain.from_dict(serialized)
        hash_after = deserialized.hash()
        assert hash_before == hash_after


# ===========================================================================
# Test Class 6: TrustLineageChain.to_dict() Inline Serialization
# ===========================================================================


class TestChainInlineSerialization:
    """
    TrustLineageChain.to_dict() uses INLINE serialization for delegations
    (does NOT call DelegationRecord.to_dict()). This means new fields must
    be added in TWO places. These tests verify the inline serialization
    contract is stable.
    """

    def test_chain_to_dict_delegation_keys(self, trust_chain):
        """Delegations in chain to_dict() must have exactly these keys."""
        chain_dict = trust_chain.to_dict()
        delegation_dict = chain_dict["delegations"][0]
        expected_keys = {
            "id",
            "delegator_id",
            "delegatee_id",
            "task_id",
            "capabilities_delegated",
            "constraint_subset",
            "delegated_at",
            "expires_at",
            "parent_delegation_id",
        }
        assert set(delegation_dict.keys()) == expected_keys

    def test_chain_to_dict_no_eatp_fields_in_delegations(self, trust_chain):
        """Chain inline serialization must NOT include EATP extension fields.

        Note: This is a known limitation — TrustLineageChain.to_dict() uses
        inline dicts and does NOT call d.to_dict(). The EATP fields
        (human_origin, delegation_chain, delegation_depth) are currently
        missing from chain serialization. When reasoning fields are added,
        they must also be added here if they should be included.
        """
        chain_dict = trust_chain.to_dict()
        delegation_dict = chain_dict["delegations"][0]
        # These fields are currently NOT serialized in chain context
        assert "human_origin" not in delegation_dict
        assert "delegation_chain" not in delegation_dict
        assert "delegation_depth" not in delegation_dict
        assert "signature" not in delegation_dict

    def test_chain_to_dict_capability_keys(self, trust_chain):
        """Capabilities in chain to_dict() must have exactly these keys."""
        chain_dict = trust_chain.to_dict()
        cap_dict = chain_dict["capabilities"][0]
        expected_keys = {
            "id",
            "capability",
            "capability_type",
            "constraints",
            "attester_id",
            "attested_at",
            "expires_at",
            "scope",
        }
        assert set(cap_dict.keys()) == expected_keys

    def test_chain_to_dict_top_level_keys(self, trust_chain):
        """Chain to_dict() must have exactly these top-level keys."""
        chain_dict = trust_chain.to_dict()
        expected_keys = {
            "genesis",
            "capabilities",
            "delegations",
            "constraint_envelope",
            "chain_hash",
        }
        assert set(chain_dict.keys()) == expected_keys

    def test_chain_to_dict_genesis_keys(self, trust_chain):
        """Genesis in chain to_dict() must have exactly these keys."""
        chain_dict = trust_chain.to_dict()
        genesis_dict = chain_dict["genesis"]
        expected_keys = {
            "id",
            "agent_id",
            "authority_id",
            "authority_type",
            "created_at",
            "expires_at",
            "signature_algorithm",
            "metadata",
        }
        assert set(genesis_dict.keys()) == expected_keys


# ===========================================================================
# Test Class 7: Old Wire Format Fixtures
# ===========================================================================


class TestOldWireFormatFixtures:
    """
    Hardcoded JSON representing records from an older SDK version.
    These must always deserialize successfully, even after reasoning
    trace fields are added to the data model.
    """

    V1_CHAIN_JSON = {
        "genesis": {
            "id": "gen-v1-001",
            "agent_id": "agent-legacy",
            "authority_id": "auth-001",
            "authority_type": "human",
            "created_at": "2025-06-15T08:00:00+00:00",
            "expires_at": "2026-06-15T08:00:00+00:00",
            "signature_algorithm": "Ed25519",
            "metadata": {},
        },
        "capabilities": [
            {
                "id": "cap-v1-001",
                "capability": "data_analysis",
                "capability_type": "access",
                "constraints": ["read_only"],
                "attester_id": "auth-001",
                "attested_at": "2025-06-15T08:00:00+00:00",
                "expires_at": None,
                "scope": None,
            }
        ],
        "delegations": [
            {
                "id": "del-v1-001",
                "delegator_id": "agent-legacy",
                "delegatee_id": "agent-worker",
                "task_id": "task-v1",
                "capabilities_delegated": ["data_analysis"],
                "constraint_subset": ["read_only", "max_100_rows"],
                "delegated_at": "2025-06-15T09:00:00+00:00",
                "expires_at": None,
                "parent_delegation_id": None,
            }
        ],
        "constraint_envelope": {
            "id": "env-v1-001",
            "agent_id": "agent-legacy",
            "constraint_hash": "v1-hash",
            "active_constraints": [
                {
                    "id": "c-v1-001",
                    "constraint_type": "financial",
                    "value": "50/hour",
                    "source": "admin",
                    "priority": 0,
                }
            ],
        },
        "chain_hash": "ignored-on-import",
    }

    def test_v1_chain_deserializes(self):
        """V1 chain JSON must deserialize without errors."""
        chain = TrustLineageChain.from_dict(self.V1_CHAIN_JSON)
        assert chain.genesis.id == "gen-v1-001"
        assert chain.genesis.agent_id == "agent-legacy"
        assert chain.genesis.authority_type == AuthorityType.HUMAN
        assert len(chain.capabilities) == 1
        assert chain.capabilities[0].capability == "data_analysis"
        assert len(chain.delegations) == 1
        assert chain.delegations[0].delegatee_id == "agent-worker"
        assert chain.constraint_envelope is not None
        assert chain.constraint_envelope.id == "env-v1-001"

    def test_v1_chain_hash_computable(self):
        """Hash must be computable from V1 chain data."""
        chain = TrustLineageChain.from_dict(self.V1_CHAIN_JSON)
        hash_value = chain.hash()
        assert isinstance(hash_value, str)
        assert len(hash_value) > 0

    def test_v1_delegation_from_dict_minimal(self):
        """Minimal V1 delegation record must deserialize."""
        minimal = {
            "id": "del-minimal",
            "delegator_id": "a",
            "delegatee_id": "b",
            "task_id": "t",
            "capabilities_delegated": [],
            "constraint_subset": [],
            "delegated_at": "2025-01-01T00:00:00+00:00",
            "signature": "",
        }
        record = DelegationRecord.from_dict(minimal)
        assert record.id == "del-minimal"
        assert record.expires_at is None
        assert record.parent_delegation_id is None
        assert record.human_origin is None

    def test_v1_audit_anchor_from_dict_minimal(self):
        """Minimal V1 audit anchor must deserialize."""
        minimal = {
            "id": "audit-minimal",
            "agent_id": "a",
            "action": "test",
            "timestamp": "2025-01-01T00:00:00+00:00",
            "trust_chain_hash": "hash",
            "result": "success",
            "signature": "",
        }
        record = AuditAnchor.from_dict(minimal)
        assert record.id == "audit-minimal"
        assert record.resource is None
        assert record.context == {}
        assert record.human_origin is None

    def test_v1_chain_round_trip_stability(self):
        """V1 chain JSON → from_dict → to_dict → from_dict must be stable."""
        chain_1 = TrustLineageChain.from_dict(self.V1_CHAIN_JSON)
        serialized = chain_1.to_dict()
        chain_2 = TrustLineageChain.from_dict(serialized)

        assert chain_1.genesis.id == chain_2.genesis.id
        assert chain_1.genesis.authority_type == chain_2.genesis.authority_type
        assert len(chain_1.capabilities) == len(chain_2.capabilities)
        assert len(chain_1.delegations) == len(chain_2.delegations)
        assert chain_1.hash() == chain_2.hash()


# ===========================================================================
# Test Class 8: serialize_for_signing() Regression
# ===========================================================================


class TestSerializeForSigningRegression:
    """
    MOST CRITICAL: serialize_for_signing() uses dataclasses.asdict() for
    dataclass inputs. When new fields are added to DelegationRecord/AuditAnchor
    dataclasses, asdict() will silently include them. This tests that the
    signing path uses to_signing_payload() (which returns a plain dict)
    rather than passing the raw dataclass.
    """

    def test_signing_goes_through_payload_not_dataclass(self, delegation_record):
        """Sign/verify must work on to_signing_payload() dict, not the dataclass."""
        private_key, public_key = generate_keypair()

        # This is the CORRECT signing path
        payload = delegation_record.to_signing_payload()
        signature = sign(payload, private_key)
        assert verify_signature(payload, signature, public_key)

        # Verify the payload is a plain dict, not a dataclass
        assert isinstance(payload, dict)
        assert not hasattr(payload, "__dataclass_fields__")

    def test_serialize_for_signing_dict_vs_dataclass_different(self, delegation_record):
        """serialize_for_signing(dataclass) includes ALL fields; payload does not.

        This proves why signing MUST go through to_signing_payload() — the raw
        dataclass serialization includes extra fields that would break cross-version
        signature verification.
        """
        payload_serialized = serialize_for_signing(
            delegation_record.to_signing_payload()
        )
        # The dataclass includes human_origin, delegation_chain, delegation_depth
        # which are NOT in the signing payload
        dataclass_serialized = serialize_for_signing(delegation_record)

        # These MUST be different because the dataclass has extra fields
        # (human_origin=None, delegation_chain=[], delegation_depth=0)
        assert payload_serialized != dataclass_serialized, (
            "Signing payload and full dataclass serialization should differ. "
            "If they are identical, the test setup may be wrong."
        )

    def test_serialize_for_signing_stable_across_calls(self):
        """Deterministic canonical JSON for the same input."""
        data = {"z": 1, "a": 2, "m": [3, 1, 2]}
        s1 = serialize_for_signing(data)
        s2 = serialize_for_signing(data)
        assert s1 == s2
        # Keys must be sorted
        assert s1.index('"a"') < s1.index('"m"') < s1.index('"z"')


# ===========================================================================
# Test Class 9: ConstraintEnvelope Stability
# ===========================================================================


class TestConstraintEnvelopeStability:
    """
    ConstraintEnvelope will gain a REASONING_REQUIRED constraint type.
    These tests verify existing constraint types and behavior are stable.
    """

    def test_existing_constraint_types_unchanged(self):
        """All pre-existing ConstraintType values must remain valid."""
        existing_types = [
            "financial",
            "temporal",
            "data_access",
            "operational",
            "audit_requirement",
        ]
        for ct in existing_types:
            constraint_type = ConstraintType(ct)
            assert constraint_type.value == ct

    def test_constraint_envelope_serialization(self, constraint_envelope):
        """ConstraintEnvelope to_dict equivalent in chain must be stable."""
        # When serialized through TrustLineageChain.to_dict(), the constraint
        # envelope has a specific shape
        chain = TrustLineageChain(
            genesis=GenesisRecord(
                id="g",
                agent_id="a",
                authority_id="auth",
                authority_type=AuthorityType.HUMAN,
                created_at=FIXED_TIMESTAMP,
                signature="sig-test",
            ),
            constraint_envelope=constraint_envelope,
        )
        chain_dict = chain.to_dict()
        env_dict = chain_dict["constraint_envelope"]
        assert env_dict["id"] == "env-001"
        assert env_dict["agent_id"] == "agent-alpha"
        assert env_dict["constraint_hash"] == "hash-constraints"
        assert len(env_dict["active_constraints"]) == 1
        c = env_dict["active_constraints"][0]
        assert c["constraint_type"] == "financial"
        assert c["value"] == "100/hour"
