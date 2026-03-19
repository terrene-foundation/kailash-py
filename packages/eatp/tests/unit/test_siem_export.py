# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for EATP SIEM Export module (Phase 5b - VA1).

Tests CEF and OCSF serializers for EATP operations, all four
SIEM event types, the factory function from_audit_anchor, and
round-trip correctness.

TDD: These tests are written FIRST, before the implementation.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone

import pytest

from eatp.chain import ActionResult, AuditAnchor
from eatp.export.siem import (
    AuditEvent,
    DelegateEvent,
    EstablishEvent,
    SIEMEvent,
    VerifyEvent,
    from_audit_anchor,
    serialize_cef,
    serialize_ocsf,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def now():
    """Current UTC timestamp."""
    return datetime.now(timezone.utc)


@pytest.fixture
def base_event(now):
    """A minimal SIEMEvent for testing."""
    return SIEMEvent(
        timestamp=now,
        agent_id="agent-001",
        operation="ESTABLISH",
        result="SUCCESS",
        severity=3,
    )


@pytest.fixture
def establish_event(now):
    """An EstablishEvent with all fields populated."""
    return EstablishEvent(
        timestamp=now,
        agent_id="agent-001",
        operation="ESTABLISH",
        result="SUCCESS",
        severity=3,
        authority_id="org-acme",
        source_ip="10.0.0.1",
        public_key_hash="sha256:abcdef1234567890",
        capabilities_count=5,
        metadata={"department": "engineering"},
    )


@pytest.fixture
def delegate_event(now):
    """A DelegateEvent with all fields populated."""
    return DelegateEvent(
        timestamp=now,
        agent_id="agent-002",
        operation="DELEGATE",
        result="SUCCESS",
        severity=5,
        authority_id="org-acme",
        delegator_id="agent-001",
        delegation_depth=2,
        constraints_count=3,
    )


@pytest.fixture
def verify_event(now):
    """A VerifyEvent with all fields populated."""
    return VerifyEvent(
        timestamp=now,
        agent_id="agent-001",
        operation="VERIFY",
        result="SUCCESS",
        severity=2,
        verification_level="FULL",
        trust_score=85,
        action_verified="analyze_data",
    )


@pytest.fixture
def audit_event(now):
    """An AuditEvent with all fields populated."""
    return AuditEvent(
        timestamp=now,
        agent_id="agent-001",
        operation="AUDIT",
        result="FAILURE",
        severity=7,
        action="generate_report",
        resource="financial_db",
        chain_hash="abc123def456",
    )


@pytest.fixture
def sample_audit_anchor(now):
    """An AuditAnchor for factory function testing."""
    return AuditAnchor(
        id="aud-001",
        agent_id="agent-001",
        action="analyze_data",
        timestamp=now,
        trust_chain_hash="abc123",
        result=ActionResult.SUCCESS,
        signature="sig-001",
        resource="financial_db",
        context={"source": "api"},
    )


# ===========================================================================
# 1. SIEMEvent dataclass tests
# ===========================================================================


class TestSIEMEvent:
    """Tests for the base SIEMEvent dataclass."""

    def test_event_has_auto_generated_uuid(self, now):
        """Event IDs should be auto-generated UUIDs."""
        event = SIEMEvent(
            timestamp=now,
            agent_id="agent-001",
            operation="ESTABLISH",
            result="SUCCESS",
            severity=3,
        )
        # Should be a valid UUID
        parsed = uuid.UUID(event.event_id)
        assert str(parsed) == event.event_id

    def test_event_ids_are_unique(self, now):
        """Each event should get a unique event_id."""
        event1 = SIEMEvent(
            timestamp=now,
            agent_id="agent-001",
            operation="ESTABLISH",
            result="SUCCESS",
            severity=3,
        )
        event2 = SIEMEvent(
            timestamp=now,
            agent_id="agent-001",
            operation="ESTABLISH",
            result="SUCCESS",
            severity=3,
        )
        assert event1.event_id != event2.event_id

    def test_event_required_fields(self, base_event):
        """Required fields should be accessible."""
        assert base_event.agent_id == "agent-001"
        assert base_event.operation == "ESTABLISH"
        assert base_event.result == "SUCCESS"
        assert base_event.severity == 3

    def test_event_optional_fields_default_none(self, base_event):
        """Optional fields default to None."""
        assert base_event.authority_id is None
        assert base_event.source_ip is None

    def test_event_metadata_defaults_to_empty_dict(self, base_event):
        """Metadata should default to empty dict."""
        assert base_event.metadata == {}

    def test_event_custom_event_id(self, now):
        """Should allow explicit event_id."""
        custom_id = "custom-event-001"
        event = SIEMEvent(
            timestamp=now,
            agent_id="agent-001",
            operation="VERIFY",
            result="DENIED",
            severity=8,
            event_id=custom_id,
        )
        assert event.event_id == custom_id


# ===========================================================================
# 2. Event type subclass tests
# ===========================================================================


class TestEstablishEvent:
    """Tests for EstablishEvent subclass."""

    def test_establish_has_public_key_hash(self, establish_event):
        """EstablishEvent should store public_key_hash."""
        assert establish_event.public_key_hash == "sha256:abcdef1234567890"

    def test_establish_has_capabilities_count(self, establish_event):
        """EstablishEvent should store capabilities_count."""
        assert establish_event.capabilities_count == 5

    def test_establish_defaults(self, now):
        """EstablishEvent fields should have correct defaults."""
        event = EstablishEvent(
            timestamp=now,
            agent_id="agent-001",
            operation="ESTABLISH",
            result="SUCCESS",
            severity=3,
        )
        assert event.public_key_hash is None
        assert event.capabilities_count == 0

    def test_establish_is_siem_event(self, establish_event):
        """EstablishEvent should be a SIEMEvent."""
        assert isinstance(establish_event, SIEMEvent)


class TestDelegateEvent:
    """Tests for DelegateEvent subclass."""

    def test_delegate_has_delegator_id(self, delegate_event):
        """DelegateEvent should store delegator_id."""
        assert delegate_event.delegator_id == "agent-001"

    def test_delegate_has_delegation_depth(self, delegate_event):
        """DelegateEvent should store delegation_depth."""
        assert delegate_event.delegation_depth == 2

    def test_delegate_has_constraints_count(self, delegate_event):
        """DelegateEvent should store constraints_count."""
        assert delegate_event.constraints_count == 3

    def test_delegate_defaults(self, now):
        """DelegateEvent fields should have correct defaults."""
        event = DelegateEvent(
            timestamp=now,
            agent_id="agent-002",
            operation="DELEGATE",
            result="SUCCESS",
            severity=5,
        )
        assert event.delegator_id is None
        assert event.delegation_depth == 0
        assert event.constraints_count == 0

    def test_delegate_is_siem_event(self, delegate_event):
        """DelegateEvent should be a SIEMEvent."""
        assert isinstance(delegate_event, SIEMEvent)


class TestVerifyEvent:
    """Tests for VerifyEvent subclass."""

    def test_verify_has_verification_level(self, verify_event):
        """VerifyEvent should store verification_level."""
        assert verify_event.verification_level == "FULL"

    def test_verify_has_trust_score(self, verify_event):
        """VerifyEvent should store trust_score."""
        assert verify_event.trust_score == 85

    def test_verify_has_action_verified(self, verify_event):
        """VerifyEvent should store action_verified."""
        assert verify_event.action_verified == "analyze_data"

    def test_verify_defaults(self, now):
        """VerifyEvent fields should have correct defaults."""
        event = VerifyEvent(
            timestamp=now,
            agent_id="agent-001",
            operation="VERIFY",
            result="SUCCESS",
            severity=2,
        )
        assert event.verification_level is None
        assert event.trust_score is None
        assert event.action_verified is None

    def test_verify_is_siem_event(self, verify_event):
        """VerifyEvent should be a SIEMEvent."""
        assert isinstance(verify_event, SIEMEvent)


class TestAuditEvent:
    """Tests for AuditEvent subclass."""

    def test_audit_has_action(self, audit_event):
        """AuditEvent should store action."""
        assert audit_event.action == "generate_report"

    def test_audit_has_resource(self, audit_event):
        """AuditEvent should store resource."""
        assert audit_event.resource == "financial_db"

    def test_audit_has_chain_hash(self, audit_event):
        """AuditEvent should store chain_hash."""
        assert audit_event.chain_hash == "abc123def456"

    def test_audit_defaults(self, now):
        """AuditEvent fields should have correct defaults."""
        event = AuditEvent(
            timestamp=now,
            agent_id="agent-001",
            operation="AUDIT",
            result="SUCCESS",
            severity=1,
        )
        assert event.action is None
        assert event.resource is None
        assert event.chain_hash is None

    def test_audit_is_siem_event(self, audit_event):
        """AuditEvent should be a SIEMEvent."""
        assert isinstance(audit_event, SIEMEvent)


# ===========================================================================
# 3. CEF serializer tests
# ===========================================================================


class TestSerializeCEF:
    """Tests for the CEF serialization function."""

    def test_cef_header_format(self, base_event):
        """CEF output should start with the standard CEF header."""
        cef = serialize_cef(base_event)
        assert cef.startswith("CEF:0|")

    def test_cef_vendor_product_version(self, base_event):
        """CEF should have correct vendor, product, and version."""
        cef = serialize_cef(base_event)
        parts = cef.split("|")
        assert parts[1] == "Terrene Foundation"
        assert parts[2] == "EATP"
        assert parts[3] == "1.0"

    def test_cef_signature_id_is_operation(self, base_event):
        """CEF Signature ID should be the EATP operation."""
        cef = serialize_cef(base_event)
        parts = cef.split("|")
        assert parts[4] == "ESTABLISH"

    def test_cef_name_is_human_readable(self, base_event):
        """CEF Name field should describe the event."""
        cef = serialize_cef(base_event)
        parts = cef.split("|")
        # Name should be a human-readable string containing the operation
        assert "ESTABLISH" in parts[5]

    def test_cef_severity_matches_event(self, base_event):
        """CEF severity should match the event severity."""
        cef = serialize_cef(base_event)
        parts = cef.split("|")
        assert parts[6].startswith("3")  # severity=3, may have extensions after

    def test_cef_has_seven_pipe_delimited_header_fields(self, base_event):
        """CEF header should have exactly 7 pipe-delimited fields before extensions."""
        cef = serialize_cef(base_event)
        # The header is: CEF:0|vendor|product|version|sig_id|name|severity|extensions
        # That's 8 parts when split by |, but the extension part is the 8th
        parts = cef.split("|")
        assert len(parts) >= 7

    def test_cef_extension_contains_agent_id(self, base_event):
        """CEF extensions should include agent_id as duser."""
        cef = serialize_cef(base_event)
        assert "duser=agent-001" in cef

    def test_cef_extension_contains_timestamp(self, base_event):
        """CEF extensions should include timestamp as rt."""
        cef = serialize_cef(base_event)
        assert "rt=" in cef

    def test_cef_extension_contains_result(self, base_event):
        """CEF extensions should include result as outcome."""
        cef = serialize_cef(base_event)
        assert "outcome=SUCCESS" in cef

    def test_cef_extension_contains_event_id(self, base_event):
        """CEF extensions should include event_id as externalId."""
        cef = serialize_cef(base_event)
        assert f"externalId={base_event.event_id}" in cef

    def test_cef_extension_contains_authority_id(self, establish_event):
        """CEF extensions should include authority_id as suser when present."""
        cef = serialize_cef(establish_event)
        assert "suser=org-acme" in cef

    def test_cef_extension_contains_source_ip(self, establish_event):
        """CEF extensions should include source_ip as src when present."""
        cef = serialize_cef(establish_event)
        assert "src=10.0.0.1" in cef

    def test_cef_pipe_characters_escaped_in_values(self, now):
        """Pipe characters in values must be escaped as \\|."""
        event = SIEMEvent(
            timestamp=now,
            agent_id="agent|with|pipes",
            operation="ESTABLISH",
            result="SUCCESS",
            severity=3,
        )
        cef = serialize_cef(event)
        # The agent_id with pipes should appear escaped in extensions
        assert "agent\\|with\\|pipes" in cef

    def test_cef_backslash_characters_escaped_in_values(self, now):
        """Backslash characters in values must be escaped as \\\\."""
        event = SIEMEvent(
            timestamp=now,
            agent_id="agent\\backslash",
            operation="ESTABLISH",
            result="SUCCESS",
            severity=3,
        )
        cef = serialize_cef(event)
        assert "agent\\\\backslash" in cef

    def test_cef_establish_event_extensions(self, establish_event):
        """EstablishEvent should include public_key_hash and capabilities_count."""
        cef = serialize_cef(establish_event)
        assert "cs1=sha256:abcdef1234567890" in cef
        assert "cn1=5" in cef

    def test_cef_delegate_event_extensions(self, delegate_event):
        """DelegateEvent should include delegator_id and delegation_depth."""
        cef = serialize_cef(delegate_event)
        assert "cs1=agent-001" in cef  # delegator_id
        assert "cn1=2" in cef  # delegation_depth

    def test_cef_verify_event_extensions(self, verify_event):
        """VerifyEvent should include verification_level and trust_score."""
        cef = serialize_cef(verify_event)
        assert "cs1=FULL" in cef  # verification_level
        assert "cn1=85" in cef  # trust_score

    def test_cef_audit_event_extensions(self, audit_event):
        """AuditEvent should include action, resource, and chain_hash."""
        cef = serialize_cef(audit_event)
        assert "act=generate_report" in cef
        assert "cs1=financial_db" in cef  # resource
        assert "cs2=abc123def456" in cef  # chain_hash

    def test_cef_returns_string(self, base_event):
        """CEF serializer should return a string."""
        result = serialize_cef(base_event)
        assert isinstance(result, str)

    def test_cef_severity_zero(self, now):
        """CEF should handle severity=0 correctly."""
        event = SIEMEvent(
            timestamp=now,
            agent_id="agent-001",
            operation="VERIFY",
            result="SUCCESS",
            severity=0,
        )
        cef = serialize_cef(event)
        parts = cef.split("|")
        assert parts[6].startswith("0")

    def test_cef_severity_ten(self, now):
        """CEF should handle severity=10 correctly."""
        event = SIEMEvent(
            timestamp=now,
            agent_id="agent-001",
            operation="VERIFY",
            result="FAILURE",
            severity=10,
        )
        cef = serialize_cef(event)
        parts = cef.split("|")
        assert parts[6].startswith("10")

    def test_cef_all_operations(self, now):
        """CEF should handle all four EATP operations."""
        for op in ["ESTABLISH", "DELEGATE", "VERIFY", "AUDIT"]:
            event = SIEMEvent(
                timestamp=now,
                agent_id="agent-001",
                operation=op,
                result="SUCCESS",
                severity=3,
            )
            cef = serialize_cef(event)
            parts = cef.split("|")
            assert parts[4] == op

    def test_cef_all_results(self, now):
        """CEF should handle all four result types."""
        for result_val in ["SUCCESS", "FAILURE", "DENIED", "PARTIAL"]:
            event = SIEMEvent(
                timestamp=now,
                agent_id="agent-001",
                operation="VERIFY",
                result=result_val,
                severity=3,
            )
            cef = serialize_cef(event)
            assert f"outcome={result_val}" in cef

    def test_cef_newline_characters_escaped_in_values(self, now):
        """Newline characters in values must be escaped."""
        event = SIEMEvent(
            timestamp=now,
            agent_id="agent\nwith\nnewlines",
            operation="ESTABLISH",
            result="SUCCESS",
            severity=3,
        )
        cef = serialize_cef(event)
        # Newlines in CEF extensions should be escaped as \\n
        assert "agent\\nwith\\nnewlines" in cef

    def test_cef_equals_sign_escaped_in_extension_values(self, now):
        """Equals signs in extension values must be escaped."""
        event = SIEMEvent(
            timestamp=now,
            agent_id="agent=equals",
            operation="ESTABLISH",
            result="SUCCESS",
            severity=3,
        )
        cef = serialize_cef(event)
        assert "agent\\=equals" in cef


# ===========================================================================
# 4. OCSF serializer tests
# ===========================================================================


class TestSerializeOCSF:
    """Tests for the OCSF serialization function."""

    def test_ocsf_returns_dict(self, base_event):
        """OCSF serializer should return a dict."""
        result = serialize_ocsf(base_event)
        assert isinstance(result, dict)

    def test_ocsf_is_json_serializable(self, base_event):
        """OCSF output must be JSON-serializable."""
        result = serialize_ocsf(base_event)
        serialized = json.dumps(result)
        assert isinstance(serialized, str)
        # Round-trip
        deserialized = json.loads(serialized)
        assert deserialized == result

    def test_ocsf_has_class_uid(self, base_event):
        """OCSF must include class_uid (Authentication = 3002)."""
        result = serialize_ocsf(base_event)
        assert "class_uid" in result
        assert isinstance(result["class_uid"], int)

    def test_ocsf_has_category_uid(self, base_event):
        """OCSF must include category_uid (Identity & Access = 3)."""
        result = serialize_ocsf(base_event)
        assert "category_uid" in result
        assert isinstance(result["category_uid"], int)

    def test_ocsf_has_activity_id(self, base_event):
        """OCSF must include activity_id."""
        result = serialize_ocsf(base_event)
        assert "activity_id" in result
        assert isinstance(result["activity_id"], int)

    def test_ocsf_has_severity_id(self, base_event):
        """OCSF must include severity_id."""
        result = serialize_ocsf(base_event)
        assert "severity_id" in result
        assert isinstance(result["severity_id"], int)

    def test_ocsf_has_time(self, base_event):
        """OCSF must include time as epoch milliseconds."""
        result = serialize_ocsf(base_event)
        assert "time" in result
        assert isinstance(result["time"], int)

    def test_ocsf_has_metadata(self, base_event):
        """OCSF must include metadata with product info."""
        result = serialize_ocsf(base_event)
        assert "metadata" in result
        meta = result["metadata"]
        assert "product" in meta
        assert meta["product"]["vendor_name"] == "Terrene Foundation"
        assert meta["product"]["name"] == "EATP"
        assert "version" in meta["product"]

    def test_ocsf_has_actor(self, base_event):
        """OCSF must include actor with agent information."""
        result = serialize_ocsf(base_event)
        assert "actor" in result
        assert "user" in result["actor"]
        assert result["actor"]["user"]["uid"] == "agent-001"

    def test_ocsf_has_status(self, base_event):
        """OCSF must include status field."""
        result = serialize_ocsf(base_event)
        assert "status" in result

    def test_ocsf_has_status_id(self, base_event):
        """OCSF must include status_id field."""
        result = serialize_ocsf(base_event)
        assert "status_id" in result
        assert isinstance(result["status_id"], int)

    def test_ocsf_success_status_id(self, now):
        """SUCCESS result should map to status_id=1."""
        event = SIEMEvent(
            timestamp=now,
            agent_id="agent-001",
            operation="ESTABLISH",
            result="SUCCESS",
            severity=3,
        )
        result = serialize_ocsf(event)
        assert result["status_id"] == 1

    def test_ocsf_failure_status_id(self, now):
        """FAILURE result should map to status_id=2."""
        event = SIEMEvent(
            timestamp=now,
            agent_id="agent-001",
            operation="ESTABLISH",
            result="FAILURE",
            severity=7,
        )
        result = serialize_ocsf(event)
        assert result["status_id"] == 2

    def test_ocsf_severity_mapping(self, now):
        """CEF severity 0-10 should map to OCSF severity_id 0-5."""
        # 0 -> 0 (Unknown), 1-2 -> 1 (Info), 3-4 -> 2 (Low)
        # 5-6 -> 3 (Medium), 7-8 -> 4 (High), 9-10 -> 5 (Critical)
        mapping = {
            0: 0,  # Unknown
            1: 1,  # Informational
            2: 1,
            3: 2,  # Low
            4: 2,
            5: 3,  # Medium
            6: 3,
            7: 4,  # High
            8: 4,
            9: 5,  # Critical
            10: 5,
        }
        for cef_severity, expected_ocsf in mapping.items():
            event = SIEMEvent(
                timestamp=now,
                agent_id="agent-001",
                operation="ESTABLISH",
                result="SUCCESS",
                severity=cef_severity,
            )
            result = serialize_ocsf(event)
            assert result["severity_id"] == expected_ocsf, (
                f"CEF severity {cef_severity} should map to OCSF "
                f"severity_id {expected_ocsf}, got {result['severity_id']}"
            )

    def test_ocsf_includes_event_uid(self, base_event):
        """OCSF should include the event_id as uid."""
        result = serialize_ocsf(base_event)
        assert result.get("uid") == base_event.event_id

    def test_ocsf_includes_activity_name(self, base_event):
        """OCSF should include activity_name matching the operation."""
        result = serialize_ocsf(base_event)
        assert "activity_name" in result
        assert "ESTABLISH" in result["activity_name"]

    def test_ocsf_includes_authority_when_present(self, establish_event):
        """OCSF should include authority info when authority_id is set."""
        result = serialize_ocsf(establish_event)
        # Authority should be in the actor or a dedicated field
        ocsf_str = json.dumps(result)
        assert "org-acme" in ocsf_str

    def test_ocsf_establish_event_unmapped_fields(self, establish_event):
        """EstablishEvent-specific fields should appear in OCSF unmapped dict."""
        result = serialize_ocsf(establish_event)
        assert "unmapped" in result
        unmapped = result["unmapped"]
        assert unmapped.get("public_key_hash") == "sha256:abcdef1234567890"
        assert unmapped.get("capabilities_count") == 5

    def test_ocsf_delegate_event_unmapped_fields(self, delegate_event):
        """DelegateEvent-specific fields should appear in OCSF unmapped dict."""
        result = serialize_ocsf(delegate_event)
        assert "unmapped" in result
        unmapped = result["unmapped"]
        assert unmapped.get("delegator_id") == "agent-001"
        assert unmapped.get("delegation_depth") == 2
        assert unmapped.get("constraints_count") == 3

    def test_ocsf_verify_event_unmapped_fields(self, verify_event):
        """VerifyEvent-specific fields should appear in OCSF unmapped dict."""
        result = serialize_ocsf(verify_event)
        assert "unmapped" in result
        unmapped = result["unmapped"]
        assert unmapped.get("verification_level") == "FULL"
        assert unmapped.get("trust_score") == 85
        assert unmapped.get("action_verified") == "analyze_data"

    def test_ocsf_audit_event_unmapped_fields(self, audit_event):
        """AuditEvent-specific fields should appear in OCSF unmapped dict."""
        result = serialize_ocsf(audit_event)
        assert "unmapped" in result
        unmapped = result["unmapped"]
        assert unmapped.get("action") == "generate_report"
        assert unmapped.get("resource") == "financial_db"
        assert unmapped.get("chain_hash") == "abc123def456"

    def test_ocsf_all_operations_produce_valid_dicts(self, now):
        """All four operations should produce valid OCSF dicts."""
        for op in ["ESTABLISH", "DELEGATE", "VERIFY", "AUDIT"]:
            event = SIEMEvent(
                timestamp=now,
                agent_id="agent-001",
                operation=op,
                result="SUCCESS",
                severity=3,
            )
            result = serialize_ocsf(event)
            assert isinstance(result, dict)
            assert result["activity_name"] is not None
            json.dumps(result)  # Must be JSON-serializable

    def test_ocsf_source_ip_included_when_present(self, establish_event):
        """OCSF should include src_endpoint when source_ip is set."""
        result = serialize_ocsf(establish_event)
        ocsf_str = json.dumps(result)
        assert "10.0.0.1" in ocsf_str


# ===========================================================================
# 5. Factory function: from_audit_anchor
# ===========================================================================


class TestFromAuditAnchor:
    """Tests for the from_audit_anchor factory function."""

    def test_creates_audit_event(self, sample_audit_anchor):
        """Should return an AuditEvent instance."""
        event = from_audit_anchor(sample_audit_anchor)
        assert isinstance(event, AuditEvent)

    def test_maps_agent_id(self, sample_audit_anchor):
        """Should copy agent_id from anchor."""
        event = from_audit_anchor(sample_audit_anchor)
        assert event.agent_id == "agent-001"

    def test_maps_timestamp(self, sample_audit_anchor):
        """Should copy timestamp from anchor."""
        event = from_audit_anchor(sample_audit_anchor)
        assert event.timestamp == sample_audit_anchor.timestamp

    def test_maps_action(self, sample_audit_anchor):
        """Should map anchor.action to event.action."""
        event = from_audit_anchor(sample_audit_anchor)
        assert event.action == "analyze_data"

    def test_maps_resource(self, sample_audit_anchor):
        """Should map anchor.resource to event.resource."""
        event = from_audit_anchor(sample_audit_anchor)
        assert event.resource == "financial_db"

    def test_maps_chain_hash(self, sample_audit_anchor):
        """Should map anchor.trust_chain_hash to event.chain_hash."""
        event = from_audit_anchor(sample_audit_anchor)
        assert event.chain_hash == "abc123"

    def test_operation_is_audit(self, sample_audit_anchor):
        """Operation should always be AUDIT."""
        event = from_audit_anchor(sample_audit_anchor)
        assert event.operation == "AUDIT"

    def test_maps_success_result(self, sample_audit_anchor):
        """ActionResult.SUCCESS should map to 'SUCCESS'."""
        event = from_audit_anchor(sample_audit_anchor)
        assert event.result == "SUCCESS"

    def test_maps_failure_result(self, now):
        """ActionResult.FAILURE should map to 'FAILURE'."""
        anchor = AuditAnchor(
            id="aud-002",
            agent_id="agent-002",
            action="generate_report",
            timestamp=now,
            trust_chain_hash="def456",
            result=ActionResult.FAILURE,
            signature="sig-002",
        )
        event = from_audit_anchor(anchor)
        assert event.result == "FAILURE"

    def test_maps_denied_result(self, now):
        """ActionResult.DENIED should map to 'DENIED'."""
        anchor = AuditAnchor(
            id="aud-003",
            agent_id="agent-003",
            action="access_secrets",
            timestamp=now,
            trust_chain_hash="ghi789",
            result=ActionResult.DENIED,
            signature="sig-003",
        )
        event = from_audit_anchor(anchor)
        assert event.result == "DENIED"

    def test_maps_partial_result(self, now):
        """ActionResult.PARTIAL should map to 'PARTIAL'."""
        anchor = AuditAnchor(
            id="aud-004",
            agent_id="agent-004",
            action="batch_process",
            timestamp=now,
            trust_chain_hash="jkl012",
            result=ActionResult.PARTIAL,
            signature="sig-004",
        )
        event = from_audit_anchor(anchor)
        assert event.result == "PARTIAL"

    def test_authority_id_passed_through(self, sample_audit_anchor):
        """authority_id argument should be set on the event."""
        event = from_audit_anchor(sample_audit_anchor, authority_id="org-acme")
        assert event.authority_id == "org-acme"

    def test_authority_id_defaults_to_none(self, sample_audit_anchor):
        """authority_id should default to None when not provided."""
        event = from_audit_anchor(sample_audit_anchor)
        assert event.authority_id is None

    def test_severity_for_success(self, sample_audit_anchor):
        """SUCCESS actions should have low severity."""
        event = from_audit_anchor(sample_audit_anchor)
        assert event.severity <= 3

    def test_severity_for_denied(self, now):
        """DENIED actions should have high severity."""
        anchor = AuditAnchor(
            id="aud-denied",
            agent_id="agent-001",
            action="access_secrets",
            timestamp=now,
            trust_chain_hash="hash",
            result=ActionResult.DENIED,
            signature="sig",
        )
        event = from_audit_anchor(anchor)
        assert event.severity >= 7

    def test_severity_for_failure(self, now):
        """FAILURE actions should have medium-high severity."""
        anchor = AuditAnchor(
            id="aud-fail",
            agent_id="agent-001",
            action="process_data",
            timestamp=now,
            trust_chain_hash="hash",
            result=ActionResult.FAILURE,
            signature="sig",
        )
        event = from_audit_anchor(anchor)
        assert event.severity >= 5

    def test_context_in_metadata(self, sample_audit_anchor):
        """Anchor context should be included in event metadata."""
        event = from_audit_anchor(sample_audit_anchor)
        assert event.metadata.get("context") == {"source": "api"}

    def test_has_valid_event_id(self, sample_audit_anchor):
        """Factory should create events with valid UUID event_ids."""
        event = from_audit_anchor(sample_audit_anchor)
        parsed = uuid.UUID(event.event_id)
        assert str(parsed) == event.event_id


# ===========================================================================
# 6. Round-trip and integration tests
# ===========================================================================


class TestRoundTrip:
    """Tests ensuring CEF and OCSF serializers handle all event types."""

    def test_cef_roundtrip_all_event_types(self, establish_event, delegate_event, verify_event, audit_event):
        """All event types should serialize to valid CEF strings."""
        for event in [establish_event, delegate_event, verify_event, audit_event]:
            cef = serialize_cef(event)
            assert isinstance(cef, str)
            assert cef.startswith("CEF:0|")
            # Should have valid structure
            parts = cef.split("|")
            assert len(parts) >= 7

    def test_ocsf_roundtrip_all_event_types(self, establish_event, delegate_event, verify_event, audit_event):
        """All event types should serialize to valid OCSF dicts."""
        for event in [establish_event, delegate_event, verify_event, audit_event]:
            ocsf = serialize_ocsf(event)
            assert isinstance(ocsf, dict)
            # Must be JSON round-trippable
            serialized = json.dumps(ocsf)
            deserialized = json.loads(serialized)
            assert deserialized == ocsf

    def test_cef_and_ocsf_same_event_id(self, base_event):
        """CEF and OCSF should reference the same event_id."""
        cef = serialize_cef(base_event)
        ocsf = serialize_ocsf(base_event)
        assert base_event.event_id in cef
        assert ocsf["uid"] == base_event.event_id

    def test_factory_to_cef(self, sample_audit_anchor):
        """Factory -> CEF should produce valid output."""
        event = from_audit_anchor(sample_audit_anchor, authority_id="org-acme")
        cef = serialize_cef(event)
        assert cef.startswith("CEF:0|")
        assert "agent-001" in cef
        assert "AUDIT" in cef

    def test_factory_to_ocsf(self, sample_audit_anchor):
        """Factory -> OCSF should produce valid output."""
        event = from_audit_anchor(sample_audit_anchor, authority_id="org-acme")
        ocsf = serialize_ocsf(event)
        assert isinstance(ocsf, dict)
        assert ocsf["actor"]["user"]["uid"] == "agent-001"
        json.dumps(ocsf)  # Must be JSON-serializable

    def test_cef_no_newlines_in_output(self, establish_event):
        """CEF output should be a single line (no embedded newlines)."""
        cef = serialize_cef(establish_event)
        assert "\n" not in cef
        assert "\r" not in cef
