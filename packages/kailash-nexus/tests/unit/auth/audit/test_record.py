"""Unit tests for AuditRecord (TODO-310F).

Tier 1 tests - mocking allowed.
"""

import json
from datetime import datetime, timezone

import pytest
from nexus.auth.audit.record import AuditRecord

# =============================================================================
# Tests: AuditRecord Creation
# =============================================================================


class TestAuditRecordCreation:
    """Test AuditRecord creation."""

    def test_create_factory_method(self):
        """Factory method creates record with auto-generated fields."""
        record = AuditRecord.create(
            method="POST",
            path="/api/users",
            status_code=201,
            duration_ms=45.2,
            ip_address="192.168.1.1",
        )

        assert record.method == "POST"
        assert record.path == "/api/users"
        assert record.status_code == 201
        assert record.duration_ms == 45.2
        assert record.ip_address == "192.168.1.1"
        assert record.request_id  # UUID auto-generated
        assert record.timestamp  # Timestamp auto-generated

    def test_create_with_all_fields(self):
        """Factory method with all optional fields."""
        record = AuditRecord.create(
            method="GET",
            path="/api/data",
            status_code=200,
            duration_ms=10.5,
            ip_address="10.0.0.1",
            user_agent="Mozilla/5.0",
            user_id="user-123",
            tenant_id="tenant-456",
            request_body_size=256,
            response_body_size=512,
            error=None,
            metadata={"action": "list_data"},
        )

        assert record.user_id == "user-123"
        assert record.tenant_id == "tenant-456"
        assert record.user_agent == "Mozilla/5.0"
        assert record.request_body_size == 256
        assert record.response_body_size == 512
        assert record.metadata["action"] == "list_data"

    def test_defaults(self):
        """Default values for optional fields."""
        record = AuditRecord.create(
            method="GET",
            path="/test",
            status_code=200,
            duration_ms=1.0,
            ip_address="127.0.0.1",
        )

        assert record.user_id is None
        assert record.tenant_id is None
        assert record.user_agent == ""
        assert record.request_body_size == 0
        assert record.response_body_size == 0
        assert record.error is None
        assert record.metadata == {}

    def test_timestamp_is_utc(self):
        """Timestamp is UTC."""
        record = AuditRecord.create(
            method="GET",
            path="/test",
            status_code=200,
            duration_ms=1.0,
            ip_address="127.0.0.1",
        )

        assert record.timestamp.tzinfo == timezone.utc

    def test_request_id_is_unique(self):
        """Each record gets a unique request ID."""
        r1 = AuditRecord.create(
            method="GET",
            path="/test",
            status_code=200,
            duration_ms=1.0,
            ip_address="127.0.0.1",
        )
        r2 = AuditRecord.create(
            method="GET",
            path="/test",
            status_code=200,
            duration_ms=1.0,
            ip_address="127.0.0.1",
        )

        assert r1.request_id != r2.request_id

    def test_create_with_error(self):
        """Record with error message."""
        record = AuditRecord.create(
            method="POST",
            path="/api/users",
            status_code=500,
            duration_ms=100.0,
            ip_address="127.0.0.1",
            error="Internal Server Error",
        )

        assert record.error == "Internal Server Error"
        assert record.status_code == 500


# =============================================================================
# Tests: Serialization
# =============================================================================


class TestAuditRecordSerialization:
    """Test serialization and deserialization."""

    def test_to_dict(self):
        """Serialize to dictionary."""
        record = AuditRecord.create(
            method="GET",
            path="/api/data",
            status_code=200,
            duration_ms=10.5,
            ip_address="10.0.0.1",
        )

        data = record.to_dict()
        assert data["method"] == "GET"
        assert data["path"] == "/api/data"
        assert data["status_code"] == 200
        assert data["duration_ms"] == 10.5
        assert data["ip_address"] == "10.0.0.1"
        assert "timestamp" in data
        assert "request_id" in data

    def test_to_dict_timestamp_is_iso_string(self):
        """Timestamp in to_dict is ISO format string."""
        record = AuditRecord.create(
            method="GET",
            path="/test",
            status_code=200,
            duration_ms=1.0,
            ip_address="127.0.0.1",
        )

        data = record.to_dict()
        assert isinstance(data["timestamp"], str)
        # Should be parseable
        datetime.fromisoformat(data["timestamp"])

    def test_to_json(self):
        """Serialize to JSON string."""
        record = AuditRecord.create(
            method="POST",
            path="/api/users",
            status_code=201,
            duration_ms=45.0,
            ip_address="192.168.1.1",
        )

        json_str = record.to_json()
        parsed = json.loads(json_str)
        assert parsed["method"] == "POST"
        assert parsed["path"] == "/api/users"

    def test_from_dict(self):
        """Deserialize from dictionary."""
        data = {
            "timestamp": "2024-01-15T10:30:00+00:00",
            "request_id": "abc-123",
            "method": "POST",
            "path": "/api/test",
            "status_code": 200,
            "ip_address": "127.0.0.1",
            "user_agent": "test",
            "duration_ms": 50.0,
        }

        record = AuditRecord.from_dict(data)
        assert record.method == "POST"
        assert record.request_id == "abc-123"
        assert record.path == "/api/test"
        assert record.status_code == 200
        assert record.duration_ms == 50.0

    def test_from_dict_with_z_timestamp(self):
        """Deserialize Z-suffix timestamp."""
        data = {
            "timestamp": "2024-01-15T10:30:00Z",
            "request_id": "abc-123",
            "method": "GET",
            "path": "/test",
            "status_code": 200,
            "ip_address": "127.0.0.1",
            "duration_ms": 1.0,
        }

        record = AuditRecord.from_dict(data)
        assert record.timestamp.year == 2024

    def test_from_dict_optional_fields(self):
        """Deserialize with missing optional fields."""
        data = {
            "timestamp": "2024-01-15T10:30:00+00:00",
            "request_id": "abc-123",
            "method": "GET",
            "path": "/test",
            "status_code": 200,
            "ip_address": "127.0.0.1",
            "duration_ms": 1.0,
        }

        record = AuditRecord.from_dict(data)
        assert record.user_id is None
        assert record.tenant_id is None
        assert record.user_agent == ""
        assert record.error is None
        assert record.metadata == {}

    def test_roundtrip(self):
        """to_dict -> from_dict roundtrip preserves data."""
        original = AuditRecord.create(
            method="PUT",
            path="/api/users/1",
            status_code=200,
            duration_ms=30.0,
            ip_address="10.0.0.1",
            user_agent="TestClient",
            user_id="user-123",
            tenant_id="tenant-456",
            request_body_size=100,
            response_body_size=200,
            error=None,
            metadata={"action": "update"},
        )

        data = original.to_dict()
        restored = AuditRecord.from_dict(data)

        assert restored.method == original.method
        assert restored.path == original.path
        assert restored.status_code == original.status_code
        assert restored.user_id == original.user_id
        assert restored.tenant_id == original.tenant_id
        assert restored.duration_ms == original.duration_ms
        assert restored.metadata == original.metadata
