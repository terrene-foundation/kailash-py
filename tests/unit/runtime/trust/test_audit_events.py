"""Unit tests for runtime.trust.audit AuditEvent integration (CARE-018, SPEC-08).

Tests that the re-exported AuditEvent and AuditEventType from
kailash.runtime.trust.audit point to the canonical types in
kailash.trust.audit_store, and that the runtime audit generator
produces correctly-shaped canonical AuditEvent instances.

These are Tier 1 unit tests - fast, isolated, no external dependencies.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest


class TestAuditEventTypeEnum:
    """Test AuditEventType enum values (canonical + runtime).

    The canonical enum in kailash.trust.audit_store unions all domain
    values.  The workflow-lifecycle subset originating in runtime.trust.audit
    is still accessible via the same enum.
    """

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

    def test_workflow_lifecycle_event_types_present(self):
        """Test all 10 workflow-lifecycle event types are accessible."""
        from kailash.runtime.trust.audit import AuditEventType

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
        actual_names = [t.name for t in AuditEventType]
        for expected_name in expected:
            assert expected_name in actual_names, f"Missing event type: {expected_name}"

    def test_audit_event_type_is_canonical(self):
        """SPEC-08: runtime.trust.audit re-exports the canonical enum."""
        from kailash.runtime.trust.audit import AuditEventType as RuntimeAET
        from kailash.trust.audit_store import AuditEventType as CanonicalAET

        assert RuntimeAET is CanonicalAET


class TestAuditEventCanonicalShape:
    """Test AuditEvent dataclass has the canonical SPEC-08 shape."""

    def test_audit_event_is_canonical(self):
        """SPEC-08: runtime.trust.audit re-exports the canonical dataclass."""
        from kailash.runtime.trust.audit import AuditEvent as RuntimeAE
        from kailash.trust.audit_store import AuditEvent as CanonicalAE

        assert RuntimeAE is CanonicalAE

    def test_audit_event_creation_core_fields(self):
        """Test core hash-chained fields are required."""
        from kailash.runtime.trust.audit import AuditEvent

        event = AuditEvent(
            event_id="evt-abc123def456",
            timestamp="2026-04-09T12:00:00+00:00",
            actor="agent-789",
            action="execute_workflow",
            resource="/data/file.txt",
            outcome="success",
            prev_hash="0" * 64,
            hash="deadbeef" * 8,
        )

        assert event.event_id == "evt-abc123def456"
        assert event.timestamp == "2026-04-09T12:00:00+00:00"
        assert event.actor == "agent-789"
        assert event.action == "execute_workflow"
        assert event.resource == "/data/file.txt"
        assert event.outcome == "success"
        assert event.prev_hash == "0" * 64
        assert event.hash == "deadbeef" * 8

    def test_audit_event_extended_fields_optional(self):
        """Test extended domain fields default to None."""
        from kailash.runtime.trust.audit import AuditEvent

        event = AuditEvent(
            event_id="evt-test123456",
            timestamp="2026-04-09T12:00:00+00:00",
            actor="runtime",
            action="node_end",
            resource="",
            outcome="success",
            prev_hash="0" * 64,
            hash="abc",
        )

        # Extended fields default to None / empty
        assert event.event_type is None
        assert event.trace_id is None
        assert event.workflow_id is None
        assert event.node_id is None
        assert event.agent_id is None
        assert event.human_origin_id is None
        assert event.severity is None
        assert event.metadata == {}


class TestRuntimeEventBuilder:
    """Test the runtime _build_runtime_event helper produces canonical events."""

    def test_build_runtime_event_sets_event_type_string(self):
        """Runtime builder stores event_type as enum .value string."""
        from kailash.runtime.trust.audit import (
            AuditEventType,
            _build_runtime_event,
            _generate_event_id,
            _get_utc_now_iso,
        )

        event = _build_runtime_event(
            event_id=_generate_event_id(),
            event_type=AuditEventType.WORKFLOW_START,
            timestamp=_get_utc_now_iso(),
            trace_id="trace-123",
            workflow_id="wf-1",
            agent_id="agent-1",
            action="workflow_started",
            result="success",
            context={"workflow_name": "test"},
        )

        # event_type is a string on the canonical AuditEvent
        assert event.event_type == "workflow_start"
        # outcome is the canonical name (maps from runtime "result")
        assert event.outcome == "success"
        # workflow-runtime fields flow through
        assert event.trace_id == "trace-123"
        assert event.workflow_id == "wf-1"
        assert event.agent_id == "agent-1"
        # metadata carries the runtime "context" dict
        assert event.metadata == {"workflow_name": "test"}

    def test_build_runtime_event_id_format(self):
        """Event ID format: evt-{12 hex chars}."""
        from kailash.runtime.trust.audit import _generate_event_id

        event_id = _generate_event_id()
        assert event_id.startswith("evt-")
        hex_portion = event_id[4:]
        assert len(hex_portion) == 12
        assert re.match(r"^[0-9a-f]{12}$", hex_portion)

    def test_build_runtime_event_timestamp_is_iso_string(self):
        """Canonical timestamp is an ISO-8601 string, not datetime."""
        from kailash.runtime.trust.audit import _get_utc_now_iso

        ts = _get_utc_now_iso()
        assert isinstance(ts, str)
        # Must be parseable back to a UTC datetime
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None

    def test_build_runtime_event_to_dict_includes_extended_fields(self):
        """Canonical to_dict includes the runtime extended fields."""
        from kailash.runtime.trust.audit import AuditEventType, _build_runtime_event

        event = _build_runtime_event(
            event_id="evt-abc123def456",
            event_type=AuditEventType.WORKFLOW_END,
            timestamp="2024-01-15T12:30:45+00:00",
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
        assert data["outcome"] == "success"
        assert data["metadata"] == {"duration_ms": 1500}

    def test_build_runtime_event_outcomes(self):
        """Test different outcome values propagate correctly."""
        from kailash.runtime.trust.audit import AuditEventType, _build_runtime_event

        for outcome_str, event_type in [
            ("success", AuditEventType.NODE_END),
            ("failure", AuditEventType.NODE_ERROR),
            ("denied", AuditEventType.TRUST_DENIED),
        ]:
            event = _build_runtime_event(
                event_id=f"evt-{outcome_str:12}"[:16],
                event_type=event_type,
                timestamp="2026-04-09T12:00:00+00:00",
                trace_id="trace-1",
                result=outcome_str,
            )
            assert event.outcome == outcome_str
            assert event.to_dict()["outcome"] == outcome_str
