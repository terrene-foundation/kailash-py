# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PACT N6 Cross-Implementation Conformance test suite.

Validates that PACT type serialization produces deterministic, byte-identical
JSON output matching committed test vectors. The same vectors are validated
by the Rust SDK to ensure cross-implementation conformance.

Serialization convention:
    .to_dict() -> json.dumps(sort_keys=True)

This produces a canonical JSON string that is identical regardless of
dict insertion order, platform, or Python version.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from kailash.trust import ConfidentialityLevel, TrustPosture
from kailash.trust.pact.access import AccessDecision
from kailash.trust.pact.audit import AuditAnchor
from kailash.trust.pact.clearance import RoleClearance, VettingStatus
from kailash.trust.pact.config import (
    CommunicationConstraintConfig,
    ConstraintEnvelopeConfig,
    DataAccessConstraintConfig,
    FinancialConstraintConfig,
    OperationalConstraintConfig,
    TemporalConstraintConfig,
    VerificationLevel,
)
from kailash.trust.pact.knowledge import FilterDecision, KnowledgeQuery
from kailash.trust.pact.observation import Observation
from kailash.trust.pact.suspension import (
    PlanSuspension,
    ResumeCondition,
    SuspensionTrigger,
)
from kailash.trust.pact.verdict import GovernanceVerdict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VECTORS_DIR = Path(__file__).parent / "vectors"


def _load_vector(filename: str) -> dict[str, Any]:
    """Load a test vector JSON file from the vectors directory."""
    path = VECTORS_DIR / filename
    with open(path) as f:
        return json.load(f)


def _canonical_json(d: dict[str, Any]) -> str:
    """Produce canonical JSON: sorted keys, no extra whitespace."""
    return json.dumps(d, sort_keys=True)


def _envelope_to_canonical_dict(envelope: ConstraintEnvelopeConfig) -> dict[str, Any]:
    """Convert a Pydantic ConstraintEnvelopeConfig to a canonical dict.

    Pydantic's model_dump(mode='python') returns enum instances; we
    convert them to their string values for JSON-safe canonical output.
    """
    d = envelope.model_dump(mode="python")

    def _enum_to_value(obj: Any) -> Any:
        if isinstance(obj, ConfidentialityLevel):
            return obj.value
        if isinstance(obj, dict):
            return {k: _enum_to_value(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_enum_to_value(item) for item in obj]
        return obj

    return _enum_to_value(d)


# ---------------------------------------------------------------------------
# Envelope serialization (ConstraintEnvelopeConfig)
# ---------------------------------------------------------------------------


class TestEnvelopeSerialization:
    """Verify ConstraintEnvelopeConfig serialization matches the committed vector."""

    def test_envelope_serialization_matches_vector(self) -> None:
        vector = _load_vector("constraint_envelope.json")
        inp = vector["input"]

        envelope = ConstraintEnvelopeConfig(
            id=inp["id"],
            description=inp["description"],
            confidentiality_clearance=ConfidentialityLevel(
                inp["confidentiality_clearance"]
            ),
            financial=FinancialConstraintConfig(**inp["financial"]),
            operational=OperationalConstraintConfig(**inp["operational"]),
            temporal=TemporalConstraintConfig(**inp["temporal"]),
            data_access=DataAccessConstraintConfig(**inp["data_access"]),
            communication=CommunicationConstraintConfig(**inp["communication"]),
            max_delegation_depth=inp["max_delegation_depth"],
        )

        canonical = _canonical_json(_envelope_to_canonical_dict(envelope))
        assert canonical == vector["expected_canonical_json"], (
            f"Envelope serialization mismatch.\n"
            f"Got:      {canonical}\n"
            f"Expected: {vector['expected_canonical_json']}"
        )


# ---------------------------------------------------------------------------
# Verdict serialization (GovernanceVerdict)
# ---------------------------------------------------------------------------


class TestVerdictSerialization:
    """Verify GovernanceVerdict serialization matches the committed vector."""

    def test_verdict_serialization_matches_vector(self) -> None:
        vector = _load_vector("governance_verdict.json")
        inp = vector["input"]

        verdict = GovernanceVerdict(
            level=inp["level"],
            reason=inp["reason"],
            role_address=inp["role_address"],
            action=inp["action"],
            effective_envelope_snapshot=inp["effective_envelope_snapshot"],
            audit_details=inp["audit_details"],
            access_decision=None,
            timestamp=datetime.fromisoformat(inp["timestamp"]),
            envelope_version=inp["envelope_version"],
        )

        canonical = _canonical_json(verdict.to_dict())
        assert canonical == vector["expected_canonical_json"], (
            f"Verdict serialization mismatch.\n"
            f"Got:      {canonical}\n"
            f"Expected: {vector['expected_canonical_json']}"
        )


# ---------------------------------------------------------------------------
# Clearance serialization (RoleClearance)
# ---------------------------------------------------------------------------


class TestClearanceSerialization:
    """Verify RoleClearance serialization matches the committed vector."""

    def test_clearance_serialization_matches_vector(self) -> None:
        vector = _load_vector("role_clearance.json")
        inp = vector["input"]

        clearance = RoleClearance(
            role_address=inp["role_address"],
            max_clearance=ConfidentialityLevel(inp["max_clearance"]),
            compartments=frozenset(inp["compartments"]),
            granted_by_role_address=inp["granted_by_role_address"],
            vetting_status=VettingStatus(inp["vetting_status"]),
            review_at=datetime.fromisoformat(inp["review_at"]),
            nda_signed=inp["nda_signed"],
        )

        canonical = _canonical_json(clearance.to_dict())
        assert canonical == vector["expected_canonical_json"], (
            f"Clearance serialization mismatch.\n"
            f"Got:      {canonical}\n"
            f"Expected: {vector['expected_canonical_json']}"
        )

    def test_clearance_roundtrip(self) -> None:
        """Verify to_dict -> from_dict roundtrip preserves all fields."""
        original = RoleClearance(
            role_address="D1-R1-D2-R2",
            max_clearance=ConfidentialityLevel.SECRET,
            compartments=frozenset(["alpha", "omega"]),
            granted_by_role_address="D1-R1",
            vetting_status=VettingStatus.ACTIVE,
            review_at=datetime(2026, 6, 15, 0, 0, 0, tzinfo=UTC),
            nda_signed=True,
        )
        roundtripped = RoleClearance.from_dict(original.to_dict())
        assert roundtripped.role_address == original.role_address
        assert roundtripped.max_clearance == original.max_clearance
        assert roundtripped.compartments == original.compartments
        assert roundtripped.granted_by_role_address == original.granted_by_role_address
        assert roundtripped.vetting_status == original.vetting_status
        assert roundtripped.review_at == original.review_at
        assert roundtripped.nda_signed == original.nda_signed


# ---------------------------------------------------------------------------
# Access decision serialization (AccessDecision)
# ---------------------------------------------------------------------------


class TestAccessDecisionSerialization:
    """Verify AccessDecision serialization matches the committed vectors."""

    def test_access_decision_serialization_matches_vector(self) -> None:
        vector = _load_vector("access_decision.json")

        for case in vector["vectors"]:
            inp = case["input"]
            decision = AccessDecision(
                allowed=inp["allowed"],
                reason=inp["reason"],
                step_failed=inp["step_failed"],
                audit_details=inp["audit_details"],
                valid_until=(
                    datetime.fromisoformat(inp["valid_until"])
                    if inp["valid_until"] is not None
                    else None
                ),
            )

            canonical = _canonical_json(decision.to_dict())
            assert canonical == case["expected_canonical_json"], (
                f"AccessDecision '{case['name']}' serialization mismatch.\n"
                f"Got:      {canonical}\n"
                f"Expected: {case['expected_canonical_json']}"
            )

    def test_access_decision_roundtrip(self) -> None:
        """Verify to_dict -> from_dict roundtrip preserves all fields."""
        original = AccessDecision(
            allowed=False,
            reason="No clearance found",
            step_failed=1,
            audit_details={"step": 1, "detail": "missing_clearance"},
            valid_until=None,
        )
        roundtripped = AccessDecision.from_dict(original.to_dict())
        assert roundtripped.allowed == original.allowed
        assert roundtripped.reason == original.reason
        assert roundtripped.step_failed == original.step_failed
        assert roundtripped.audit_details == original.audit_details
        assert roundtripped.valid_until == original.valid_until


# ---------------------------------------------------------------------------
# N1: FilterDecision roundtrip and vector match
# ---------------------------------------------------------------------------


class TestN1FilterDecision:
    """Verify FilterDecision (N1 pre-retrieval filtering) conformance."""

    def test_n1_filter_decision_serialization_matches_vector(self) -> None:
        vector = _load_vector("filter_decision.json")

        for case in vector["vectors"]:
            inp = case["input"]
            filtered_scope = None
            if inp["filtered_scope"] is not None:
                fs = inp["filtered_scope"]
                filtered_scope = KnowledgeQuery(
                    item_ids=(
                        frozenset(fs["item_ids"])
                        if fs["item_ids"] is not None
                        else None
                    ),
                    classifications=(
                        frozenset(fs["classifications"])
                        if fs["classifications"] is not None
                        else None
                    ),
                    owning_units=(
                        frozenset(fs["owning_units"])
                        if fs["owning_units"] is not None
                        else None
                    ),
                    description=fs.get("description", ""),
                )

            decision = FilterDecision(
                allowed=inp["allowed"],
                filtered_scope=filtered_scope,
                reason=inp["reason"],
                audit_anchor_id=inp["audit_anchor_id"],
            )

            canonical = _canonical_json(decision.to_dict())
            assert canonical == case["expected_canonical_json"], (
                f"FilterDecision '{case['name']}' serialization mismatch.\n"
                f"Got:      {canonical}\n"
                f"Expected: {case['expected_canonical_json']}"
            )

    def test_n1_filter_decision_roundtrip(self) -> None:
        """Verify FilterDecision to_dict -> from_dict roundtrip."""
        original = FilterDecision(
            allowed=True,
            filtered_scope=KnowledgeQuery(
                item_ids=frozenset(["doc-1", "doc-2"]),
                classifications=frozenset(["public"]),
                owning_units=frozenset(["D1-R1-D2"]),
                description="test query",
            ),
            reason="Narrowed scope",
            audit_anchor_id="anchor-rt-001",
        )
        roundtripped = FilterDecision.from_dict(original.to_dict())
        assert roundtripped.allowed == original.allowed
        assert roundtripped.reason == original.reason
        assert roundtripped.audit_anchor_id == original.audit_anchor_id
        assert roundtripped.filtered_scope is not None
        assert roundtripped.filtered_scope.item_ids == original.filtered_scope.item_ids
        assert (
            roundtripped.filtered_scope.classifications
            == original.filtered_scope.classifications
        )


# ---------------------------------------------------------------------------
# N3: PlanSuspension roundtrip and vector match
# ---------------------------------------------------------------------------


class TestN3PlanSuspension:
    """Verify PlanSuspension (N3 plan re-entry guarantee) conformance."""

    def test_n3_suspension_serialization_matches_vector(self) -> None:
        vector = _load_vector("plan_suspension.json")
        inp = vector["input"]

        suspension = PlanSuspension(
            plan_id=inp["plan_id"],
            trigger=SuspensionTrigger(inp["trigger"]),
            suspended_at=inp["suspended_at"],
            resume_conditions=tuple(
                ResumeCondition(
                    condition_type=c["condition_type"],
                    satisfied=c["satisfied"],
                    details=c["details"],
                )
                for c in inp["resume_conditions"]
            ),
            snapshot=inp["snapshot"],
            role_address=inp["role_address"],
            suspension_id=inp["suspension_id"],
        )

        canonical = _canonical_json(suspension.to_dict())
        assert canonical == vector["expected_canonical_json"], (
            f"PlanSuspension serialization mismatch.\n"
            f"Got:      {canonical}\n"
            f"Expected: {vector['expected_canonical_json']}"
        )

    def test_n3_suspension_roundtrip(self) -> None:
        """Verify PlanSuspension to_dict -> from_dict roundtrip."""
        original = PlanSuspension(
            plan_id="plan-rt-001",
            trigger=SuspensionTrigger.TEMPORAL,
            suspended_at="2026-03-01T12:00:00+00:00",
            resume_conditions=(
                ResumeCondition(
                    condition_type="deadline_extended",
                    satisfied=False,
                    details="Waiting for deadline extension",
                ),
            ),
            snapshot={"progress": 0.75},
            role_address="D1-R1",
            suspension_id="susp-rt-001",
        )
        roundtripped = PlanSuspension.from_dict(original.to_dict())
        assert roundtripped.plan_id == original.plan_id
        assert roundtripped.trigger == original.trigger
        assert roundtripped.suspended_at == original.suspended_at
        assert len(roundtripped.resume_conditions) == len(original.resume_conditions)
        assert (
            roundtripped.resume_conditions[0].condition_type
            == original.resume_conditions[0].condition_type
        )
        assert roundtripped.snapshot == original.snapshot
        assert roundtripped.role_address == original.role_address
        assert roundtripped.suspension_id == original.suspension_id


# ---------------------------------------------------------------------------
# N4: AuditAnchor vector match and hash determinism
# ---------------------------------------------------------------------------


class TestN4AuditAnchor:
    """Verify AuditAnchor (N4 tamper-evident audit) conformance."""

    def test_n4_audit_anchor_serialization_matches_vector(self) -> None:
        vector = _load_vector("audit_anchor.json")
        inp = vector["input"]

        anchor = AuditAnchor(
            anchor_id=inp["anchor_id"],
            sequence=inp["sequence"],
            previous_hash=inp["previous_hash"],
            agent_id=inp["agent_id"],
            action=inp["action"],
            verification_level=VerificationLevel(inp["verification_level"]),
            envelope_id=inp["envelope_id"],
            result=inp["result"],
            metadata=inp["metadata"],
            timestamp=datetime.fromisoformat(inp["timestamp"]),
        )
        anchor.seal()

        # Verify content hash matches expected
        assert anchor.content_hash == vector["expected_content_hash"], (
            f"AuditAnchor content hash mismatch.\n"
            f"Got:      {anchor.content_hash}\n"
            f"Expected: {vector['expected_content_hash']}"
        )

        # Verify full serialization matches expected
        canonical = _canonical_json(anchor.to_dict())
        assert canonical == vector["expected_canonical_json"], (
            f"AuditAnchor serialization mismatch.\n"
            f"Got:      {canonical}\n"
            f"Expected: {vector['expected_canonical_json']}"
        )

    def test_n4_audit_anchor_roundtrip(self) -> None:
        """Verify AuditAnchor to_dict -> from_dict roundtrip."""
        original = AuditAnchor(
            anchor_id="anc-rt-001",
            sequence=5,
            previous_hash="abc123",
            agent_id="agent-rt",
            action="clearance_granted",
            verification_level=VerificationLevel.FLAGGED,
            envelope_id="env-rt-001",
            result="success",
            metadata={"role_address": "D1-R1"},
            timestamp=datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC),
        )
        original.seal()

        roundtripped = AuditAnchor.from_dict(original.to_dict())
        assert roundtripped.anchor_id == original.anchor_id
        assert roundtripped.sequence == original.sequence
        assert roundtripped.previous_hash == original.previous_hash
        assert roundtripped.agent_id == original.agent_id
        assert roundtripped.action == original.action
        assert roundtripped.verification_level == original.verification_level
        assert roundtripped.content_hash == original.content_hash
        assert roundtripped.verify_integrity()


# ---------------------------------------------------------------------------
# N5: Observation roundtrip and vector match
# ---------------------------------------------------------------------------


class TestN5Observation:
    """Verify Observation (N5 structured monitoring) conformance."""

    def test_n5_observation_serialization_matches_vector(self) -> None:
        vector = _load_vector("observation.json")
        inp = vector["input"]

        obs = Observation(
            event_type=inp["event_type"],
            role_address=inp["role_address"],
            timestamp=inp["timestamp"],
            level=inp["level"],
            payload=inp["payload"],
            correlation_id=inp["correlation_id"],
            observation_id=inp["observation_id"],
        )

        canonical = _canonical_json(obs.to_dict())
        assert canonical == vector["expected_canonical_json"], (
            f"Observation serialization mismatch.\n"
            f"Got:      {canonical}\n"
            f"Expected: {vector['expected_canonical_json']}"
        )

    def test_n5_observation_roundtrip(self) -> None:
        """Verify Observation to_dict -> from_dict roundtrip."""
        original = Observation(
            event_type="envelope_change",
            role_address="D1-R1-D2-R2",
            timestamp="2026-03-01T12:00:00+00:00",
            level="warn",
            payload={"old_max_spend": 500.0, "new_max_spend": 1000.0},
            correlation_id="corr-rt-001",
            observation_id="obs-rt-001",
        )
        roundtripped = Observation.from_dict(original.to_dict())
        assert roundtripped.event_type == original.event_type
        assert roundtripped.role_address == original.role_address
        assert roundtripped.timestamp == original.timestamp
        assert roundtripped.level == original.level
        assert roundtripped.payload == original.payload
        assert roundtripped.correlation_id == original.correlation_id
        assert roundtripped.observation_id == original.observation_id


# ---------------------------------------------------------------------------
# Wire format: TrustPosture (AgentPosture) canonical values
# ---------------------------------------------------------------------------


class TestPostureWireFormat:
    """Verify TrustPosture enum values match canonical wire names."""

    CANONICAL_WIRE_NAMES = [
        ("PSEUDO", "pseudo"),
        ("TOOL", "tool"),
        ("SUPERVISED", "supervised"),
        ("DELEGATING", "delegating"),
        ("AUTONOMOUS", "autonomous"),
    ]

    def test_posture_wire_format(self) -> None:
        """Each TrustPosture member must serialize to its canonical wire name."""
        for member_name, expected_wire in self.CANONICAL_WIRE_NAMES:
            posture = TrustPosture[member_name]
            assert posture.value == expected_wire, (
                f"TrustPosture.{member_name}.value = {posture.value!r}, "
                f"expected {expected_wire!r}"
            )

    def test_posture_exhaustive(self) -> None:
        """Ensure all TrustPosture members are covered by the wire format check."""
        expected_members = {name for name, _ in self.CANONICAL_WIRE_NAMES}
        actual_members = {m.name for m in TrustPosture}
        assert actual_members == expected_members, (
            f"TrustPosture members changed. "
            f"Missing from test: {actual_members - expected_members}. "
            f"Extra in test: {expected_members - actual_members}"
        )

    def test_posture_count(self) -> None:
        """Exactly 5 posture levels must exist (EATP Decision 007)."""
        assert len(TrustPosture) == 5


# ---------------------------------------------------------------------------
# Wire format: VerificationLevel canonical values
# ---------------------------------------------------------------------------


class TestVerificationLevelWireFormat:
    """Verify VerificationLevel enum values match canonical wire names."""

    CANONICAL_WIRE_NAMES = [
        ("AUTO_APPROVED", "AUTO_APPROVED"),
        ("FLAGGED", "FLAGGED"),
        ("HELD", "HELD"),
        ("BLOCKED", "BLOCKED"),
    ]

    def test_verification_level_wire_format(self) -> None:
        """Each VerificationLevel member must serialize to its canonical wire name."""
        for member_name, expected_wire in self.CANONICAL_WIRE_NAMES:
            level = VerificationLevel[member_name]
            assert level.value == expected_wire, (
                f"VerificationLevel.{member_name}.value = {level.value!r}, "
                f"expected {expected_wire!r}"
            )

    def test_verification_level_exhaustive(self) -> None:
        """Ensure all VerificationLevel members are covered."""
        expected_members = {name for name, _ in self.CANONICAL_WIRE_NAMES}
        actual_members = {m.name for m in VerificationLevel}
        assert actual_members == expected_members, (
            f"VerificationLevel members changed. "
            f"Missing from test: {actual_members - expected_members}. "
            f"Extra in test: {expected_members - actual_members}"
        )

    def test_verification_level_count(self) -> None:
        """Exactly 4 verification levels must exist (PACT gradient)."""
        assert len(VerificationLevel) == 4


# ---------------------------------------------------------------------------
# Wire format: ConfidentialityLevel canonical values
# ---------------------------------------------------------------------------


class TestConfidentialityLevelWireFormat:
    """Verify ConfidentialityLevel enum values match canonical wire names."""

    CANONICAL_WIRE_NAMES = [
        ("PUBLIC", "public"),
        ("RESTRICTED", "restricted"),
        ("CONFIDENTIAL", "confidential"),
        ("SECRET", "secret"),
        ("TOP_SECRET", "top_secret"),
    ]

    def test_confidentiality_level_wire_format(self) -> None:
        """Each ConfidentialityLevel member must serialize to its canonical wire name."""
        for member_name, expected_wire in self.CANONICAL_WIRE_NAMES:
            level = ConfidentialityLevel[member_name]
            assert level.value == expected_wire, (
                f"ConfidentialityLevel.{member_name}.value = {level.value!r}, "
                f"expected {expected_wire!r}"
            )

    def test_confidentiality_level_exhaustive(self) -> None:
        """Ensure all ConfidentialityLevel members are covered."""
        expected_members = {name for name, _ in self.CANONICAL_WIRE_NAMES}
        actual_members = {m.name for m in ConfidentialityLevel}
        assert actual_members == expected_members, (
            f"ConfidentialityLevel members changed. "
            f"Missing from test: {actual_members - expected_members}. "
            f"Extra in test: {expected_members - actual_members}"
        )

    def test_confidentiality_level_count(self) -> None:
        """Exactly 5 confidentiality levels must exist."""
        assert len(ConfidentialityLevel) == 5


# ---------------------------------------------------------------------------
# Vector file integrity
# ---------------------------------------------------------------------------


class TestVectorIntegrity:
    """Verify all vector files exist and have required structure."""

    EXPECTED_VECTORS = [
        "access_decision.json",
        "audit_anchor.json",
        "constraint_envelope.json",
        "filter_decision.json",
        "governance_verdict.json",
        "observation.json",
        "plan_suspension.json",
        "role_clearance.json",
    ]

    @pytest.mark.parametrize("vector_file", EXPECTED_VECTORS)
    def test_vector_file_exists_and_valid_json(self, vector_file: str) -> None:
        """Each vector file must exist and contain valid JSON with required keys."""
        vector = _load_vector(vector_file)
        assert "description" in vector, f"{vector_file} missing 'description'"
        assert "pact_type" in vector, f"{vector_file} missing 'pact_type'"

    def test_all_expected_vectors_present(self) -> None:
        """Verify the vectors directory contains exactly the expected files."""
        actual_files = sorted(p.name for p in VECTORS_DIR.glob("*.json"))
        assert actual_files == sorted(self.EXPECTED_VECTORS), (
            f"Vector files mismatch.\n"
            f"Expected: {sorted(self.EXPECTED_VECTORS)}\n"
            f"Actual:   {actual_files}"
        )
