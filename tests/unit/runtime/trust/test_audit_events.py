"""Unit tests for AuditEvent and AuditEventType (CARE-018).

Tests for AuditEventType enum and AuditEvent dataclass.
These are Tier 1 unit tests - fast, isolated, no external dependencies.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest


class TestAuditEventTypeEnum:
    """Test AuditEventType enum values."""

    def test_workflow_start_event_type(self):
        """Test WORKFLOW_START type has correct string value."""
        from kailash.runtime.trust.audit import AuditEventType

        assert AuditEventType.WORKFLOW_START.value == "workflow_start"

    def test_workflow_end_event_type(self):
        """Test WORKFLOW_END type has correct string value."""
        from kailash.runtime.trust.audit import AuditEventType

        assert AuditEventType.WORKFLOW_END.value == "workflow_end"

    def test_workflow_error_event_type(self):
        """Test WORKFLOW_ERROR type has correct string value."""
        from kailash.runtime.trust.audit import AuditEventType

        assert AuditEventType.WORKFLOW_ERROR.value == "workflow_error"

    def test_node_start_event_type(self):
        """Test NODE_START type has correct string value."""
        from kailash.runtime.trust.audit import AuditEventType

        assert AuditEventType.NODE_START.value == "node_start"

    def test_node_end_event_type(self):
        """Test NODE_END type has correct string value."""
        from kailash.runtime.trust.audit import AuditEventType

        assert AuditEventType.NODE_END.value == "node_end"

    def test_node_error_event_type(self):
        """Test NODE_ERROR type has correct string value."""
        from kailash.runtime.trust.audit import AuditEventType

        assert AuditEventType.NODE_ERROR.value == "node_error"

    def test_trust_verification_event_type(self):
        """Test TRUST_VERIFICATION type has correct string value."""
        from kailash.runtime.trust.audit import AuditEventType

        assert AuditEventType.TRUST_VERIFICATION.value == "trust_verification"

    def test_trust_denied_event_type(self):
        """Test TRUST_DENIED type has correct string value."""
        from kailash.runtime.trust.audit import AuditEventType

        assert AuditEventType.TRUST_DENIED.value == "trust_denied"

    def test_resource_access_event_type(self):
        """Test RESOURCE_ACCESS type has correct string value."""
        from kailash.runtime.trust.audit import AuditEventType

        assert AuditEventType.RESOURCE_ACCESS.value == "resource_access"

    def test_delegation_used_event_type(self):
        """Test DELEGATION_USED type has correct string value."""
        from kailash.runtime.trust.audit import AuditEventType

        assert AuditEventType.DELEGATION_USED.value == "delegation_used"

    def test_all_ten_event_types_defined(self):
        """Test all 10 event types are defined."""
        from kailash.runtime.trust.audit import AuditEventType

        types = list(AuditEventType)
        assert len(types) == 10

        expected = [
            "WORKFLOW_START",
            "WORKFLOW_END",
            "WORKFLOW_ERROR",
            "NODE_START",
            "NODE_END",
            "NODE_ERROR",
            "TRUST_VERIFICATION",
            "TRUST_DENIED",
            "RESOURCE_ACCESS",
            "DELEGATION_USED",
        ]
        actual_names = [t.name for t in types]
        for expected_name in expected:
            assert expected_name in actual_names, f"Missing event type: {expected_name}"


class TestAuditEventCreation:
    """Test AuditEvent dataclass creation and fields."""

    def test_audit_event_creation_all_fields(self):
        """Test all fields set correctly on creation."""
        from kailash.runtime.trust.audit import AuditEvent, AuditEventType

        timestamp = datetime.now(UTC)
        event = AuditEvent(
            event_id="evt-abc123def456",
            event_type=AuditEventType.WORKFLOW_START,
            timestamp=timestamp,
            trace_id="trace-123",
            workflow_id="wf-456",
            node_id="node-1",
            agent_id="agent-789",
            human_origin_id="human-001",
            action="execute_workflow",
            resource="/data/file.txt",
            result="success",
            context={"key": "value"},
        )

        assert event.event_id == "evt-abc123def456"
        assert event.event_type == AuditEventType.WORKFLOW_START
        assert event.timestamp == timestamp
        assert event.trace_id == "trace-123"
        assert event.workflow_id == "wf-456"
        assert event.node_id == "node-1"
        assert event.agent_id == "agent-789"
        assert event.human_origin_id == "human-001"
        assert event.action == "execute_workflow"
        assert event.resource == "/data/file.txt"
        assert event.result == "success"
        assert event.context == {"key": "value"}

    def test_audit_event_defaults(self):
        """Test default values for optional fields."""
        from kailash.runtime.trust.audit import AuditEvent, AuditEventType

        timestamp = datetime.now(UTC)
        event = AuditEvent(
            event_id="evt-test123456",
            event_type=AuditEventType.NODE_END,
            timestamp=timestamp,
            trace_id="trace-default",
            result="success",
        )

        assert event.event_id == "evt-test123456"
        assert event.event_type == AuditEventType.NODE_END
        assert event.timestamp == timestamp
        assert event.trace_id == "trace-default"
        assert event.result == "success"

        # Optional fields should have None or empty defaults
        assert event.workflow_id is None
        assert event.node_id is None
        assert event.agent_id is None
        assert event.human_origin_id is None
        assert event.action is None
        assert event.resource is None
        assert event.context == {}


class TestAuditEventIdFormat:
    """Test AuditEvent ID format requirements."""

    def test_audit_event_id_format_starts_with_evt(self):
        """Test event ID starts with 'evt-'."""
        from kailash.runtime.trust.audit import AuditEvent, AuditEventType

        event = AuditEvent(
            event_id="evt-abc123def456",
            event_type=AuditEventType.WORKFLOW_START,
            timestamp=datetime.now(UTC),
            trace_id="trace-1",
            result="success",
        )

        assert event.event_id.startswith("evt-")

    def test_audit_event_id_format_has_12_hex_chars(self):
        """Test event ID has 12 hex characters after 'evt-'."""
        from kailash.runtime.trust.audit import AuditEvent, AuditEventType

        # Valid format: evt-{12 hex chars}
        event = AuditEvent(
            event_id="evt-a1b2c3d4e5f6",
            event_type=AuditEventType.WORKFLOW_START,
            timestamp=datetime.now(UTC),
            trace_id="trace-1",
            result="success",
        )

        # Extract the hex portion
        hex_portion = event.event_id[4:]  # After "evt-"
        assert len(hex_portion) == 12

        # Verify it's valid hex
        pattern = re.compile(r"^[0-9a-f]{12}$")
        assert pattern.match(hex_portion), f"Expected 12 hex chars, got: {hex_portion}"


class TestAuditEventTimestamp:
    """Test AuditEvent timestamp requirements."""

    def test_audit_event_timestamp_utc(self):
        """Test timestamp is UTC."""
        from kailash.runtime.trust.audit import AuditEvent, AuditEventType

        utc_timestamp = datetime.now(UTC)
        event = AuditEvent(
            event_id="evt-123456789abc",
            event_type=AuditEventType.WORKFLOW_START,
            timestamp=utc_timestamp,
            trace_id="trace-1",
            result="success",
        )

        assert event.timestamp.tzinfo is not None
        assert event.timestamp.tzinfo == UTC


class TestAuditEventSerialization:
    """Test AuditEvent to_dict serialization."""

    def test_audit_event_to_dict(self):
        """Test serialization works including datetime iso."""
        from kailash.runtime.trust.audit import AuditEvent, AuditEventType

        timestamp = datetime(2024, 1, 15, 12, 30, 45, tzinfo=UTC)
        event = AuditEvent(
            event_id="evt-abc123def456",
            event_type=AuditEventType.WORKFLOW_END,
            timestamp=timestamp,
            trace_id="trace-serialize",
            workflow_id="wf-1",
            node_id="node-1",
            agent_id="agent-1",
            human_origin_id="human-1",
            action="execute",
            resource="/path/resource",
            result="success",
            context={"duration_ms": 1500},
        )

        data = event.to_dict()

        assert data["event_id"] == "evt-abc123def456"
        assert data["event_type"] == "workflow_end"
        assert data["timestamp"] == "2024-01-15T12:30:45+00:00"
        assert data["trace_id"] == "trace-serialize"
        assert data["workflow_id"] == "wf-1"
        assert data["node_id"] == "node-1"
        assert data["agent_id"] == "agent-1"
        assert data["human_origin_id"] == "human-1"
        assert data["action"] == "execute"
        assert data["resource"] == "/path/resource"
        assert data["result"] == "success"
        assert data["context"] == {"duration_ms": 1500}

    def test_audit_event_to_dict_with_none_values(self):
        """Test serialization handles None values correctly."""
        from kailash.runtime.trust.audit import AuditEvent, AuditEventType

        timestamp = datetime.now(UTC)
        event = AuditEvent(
            event_id="evt-minimal12345",
            event_type=AuditEventType.NODE_START,
            timestamp=timestamp,
            trace_id="trace-minimal",
            result="success",
        )

        data = event.to_dict()

        assert data["event_id"] == "evt-minimal12345"
        assert data["event_type"] == "node_start"
        assert data["trace_id"] == "trace-minimal"
        assert data["result"] == "success"

        # Optional fields should be None
        assert data["workflow_id"] is None
        assert data["node_id"] is None
        assert data["agent_id"] is None
        assert data["human_origin_id"] is None
        assert data["action"] is None
        assert data["resource"] is None
        assert data["context"] == {}

    def test_audit_event_to_dict_result_values(self):
        """Test serialization with different result values."""
        from kailash.runtime.trust.audit import AuditEvent, AuditEventType

        timestamp = datetime.now(UTC)

        # Test success result
        success_event = AuditEvent(
            event_id="evt-success12345",
            event_type=AuditEventType.NODE_END,
            timestamp=timestamp,
            trace_id="trace-1",
            result="success",
        )
        assert success_event.to_dict()["result"] == "success"

        # Test failure result
        failure_event = AuditEvent(
            event_id="evt-failure12345",
            event_type=AuditEventType.NODE_ERROR,
            timestamp=timestamp,
            trace_id="trace-1",
            result="failure",
        )
        assert failure_event.to_dict()["result"] == "failure"

        # Test denied result
        denied_event = AuditEvent(
            event_id="evt-denied123456",
            event_type=AuditEventType.TRUST_DENIED,
            timestamp=timestamp,
            trace_id="trace-1",
            result="denied",
        )
        assert denied_event.to_dict()["result"] == "denied"
