"""
Unit tests for Agent Registry models.

Tests cover the intent of the data models:
- AgentStatus enum for availability tracking
- AgentMetadata for complete agent information
- RegistrationRequest for registration validation

Note: These are unit tests (Tier 1), mocking is allowed.
"""

from datetime import datetime
from typing import Any, Dict

import pytest
from kaizen.trust.registry.models import AgentMetadata, AgentStatus, RegistrationRequest


class TestAgentStatus:
    """Tests for AgentStatus enum."""

    def test_status_values_exist(self):
        """All expected status values are defined."""
        assert AgentStatus.ACTIVE.value == "ACTIVE"
        assert AgentStatus.INACTIVE.value == "INACTIVE"
        assert AgentStatus.REVOKED.value == "REVOKED"
        assert AgentStatus.SUSPENDED.value == "SUSPENDED"
        assert AgentStatus.UNKNOWN.value == "UNKNOWN"

    def test_active_is_available(self):
        """ACTIVE status indicates agent is available."""
        assert AgentStatus.ACTIVE.is_available() is True

    def test_inactive_is_not_available(self):
        """INACTIVE status indicates agent is not available."""
        assert AgentStatus.INACTIVE.is_available() is False

    def test_revoked_is_not_available(self):
        """REVOKED status indicates agent is not available."""
        assert AgentStatus.REVOKED.is_available() is False

    def test_suspended_is_not_available(self):
        """SUSPENDED status indicates agent is not available."""
        assert AgentStatus.SUSPENDED.is_available() is False

    def test_unknown_is_not_available(self):
        """UNKNOWN status indicates agent is not available."""
        assert AgentStatus.UNKNOWN.is_available() is False

    def test_status_from_string(self):
        """Status can be constructed from string value."""
        assert AgentStatus("ACTIVE") == AgentStatus.ACTIVE
        assert AgentStatus("SUSPENDED") == AgentStatus.SUSPENDED


class TestAgentMetadata:
    """Tests for AgentMetadata dataclass."""

    def create_metadata(self, **overrides) -> AgentMetadata:
        """Helper to create metadata with defaults."""
        defaults = {
            "agent_id": "agent-001",
            "agent_type": "worker",
            "capabilities": ["analyze_data"],
            "constraints": ["read_only"],
            "status": AgentStatus.ACTIVE,
            "trust_chain_hash": "hash123",
            "registered_at": datetime(2024, 1, 1, 12, 0, 0),
            "last_seen": datetime(2024, 1, 1, 12, 30, 0),
            "metadata": {"version": "1.0"},
            "endpoint": None,
            "public_key": None,
        }
        defaults.update(overrides)
        return AgentMetadata(**defaults)

    def test_metadata_creation(self):
        """Metadata can be created with all fields."""
        metadata = self.create_metadata()

        assert metadata.agent_id == "agent-001"
        assert metadata.agent_type == "worker"
        assert metadata.capabilities == ["analyze_data"]
        assert metadata.constraints == ["read_only"]
        assert metadata.status == AgentStatus.ACTIVE
        assert metadata.trust_chain_hash == "hash123"
        assert metadata.metadata == {"version": "1.0"}

    def test_metadata_with_optional_fields(self):
        """Metadata supports optional endpoint and public_key."""
        metadata = self.create_metadata(
            endpoint="localhost:8080",
            public_key="ssh-rsa AAAA...",
        )

        assert metadata.endpoint == "localhost:8080"
        assert metadata.public_key == "ssh-rsa AAAA..."

    def test_to_dict_serialization(self):
        """Metadata can be serialized to dictionary."""
        metadata = self.create_metadata()
        data = metadata.to_dict()

        assert data["agent_id"] == "agent-001"
        assert data["agent_type"] == "worker"
        assert data["capabilities"] == ["analyze_data"]
        assert data["status"] == "ACTIVE"  # Enum value as string
        assert "registered_at" in data
        assert "last_seen" in data

    def test_to_dict_datetime_format(self):
        """Datetime fields are serialized as ISO format strings."""
        metadata = self.create_metadata(
            registered_at=datetime(2024, 6, 15, 10, 30, 45),
        )
        data = metadata.to_dict()

        assert data["registered_at"] == "2024-06-15T10:30:45"

    def test_from_dict_deserialization(self):
        """Metadata can be deserialized from dictionary."""
        data = {
            "agent_id": "agent-002",
            "agent_type": "supervisor",
            "capabilities": ["manage", "delegate"],
            "constraints": [],
            "status": "ACTIVE",
            "trust_chain_hash": "hash456",
            "registered_at": "2024-01-01T12:00:00",
            "last_seen": "2024-01-01T12:30:00",
            "metadata": {},
        }

        metadata = AgentMetadata.from_dict(data)

        assert metadata.agent_id == "agent-002"
        assert metadata.agent_type == "supervisor"
        assert metadata.capabilities == ["manage", "delegate"]
        assert metadata.status == AgentStatus.ACTIVE
        assert isinstance(metadata.registered_at, datetime)

    def test_from_dict_with_datetime_objects(self):
        """from_dict handles datetime objects directly."""
        data = {
            "agent_id": "agent-003",
            "agent_type": "worker",
            "capabilities": ["task"],
            "constraints": [],
            "status": AgentStatus.INACTIVE,
            "trust_chain_hash": "hash789",
            "registered_at": datetime(2024, 1, 1),
            "last_seen": datetime(2024, 1, 1),
        }

        metadata = AgentMetadata.from_dict(data)

        assert metadata.status == AgentStatus.INACTIVE
        assert metadata.registered_at == datetime(2024, 1, 1)

    def test_roundtrip_serialization(self):
        """Metadata survives to_dict -> from_dict roundtrip."""
        original = self.create_metadata(
            agent_id="roundtrip-agent",
            capabilities=["cap1", "cap2", "cap3"],
            metadata={"key": "value", "nested": {"a": 1}},
        )

        data = original.to_dict()
        restored = AgentMetadata.from_dict(data)

        assert restored.agent_id == original.agent_id
        assert restored.capabilities == original.capabilities
        assert restored.metadata == original.metadata


class TestRegistrationRequest:
    """Tests for RegistrationRequest dataclass."""

    def create_request(self, **overrides) -> RegistrationRequest:
        """Helper to create request with defaults."""
        defaults = {
            "agent_id": "agent-001",
            "agent_type": "worker",
            "capabilities": ["analyze_data"],
            "constraints": [],
            "metadata": {},
            "trust_chain_hash": "hash123",
            "verify_trust": True,
        }
        defaults.update(overrides)
        return RegistrationRequest(**defaults)

    def test_valid_request_passes_validation(self):
        """Valid request has no validation errors."""
        request = self.create_request()
        errors = request.validate()

        assert len(errors) == 0

    def test_empty_agent_id_fails_validation(self):
        """Empty agent_id causes validation error."""
        request = self.create_request(agent_id="")
        errors = request.validate()

        assert "agent_id cannot be empty" in errors

    def test_whitespace_agent_id_fails_validation(self):
        """Whitespace-only agent_id causes validation error."""
        request = self.create_request(agent_id="   ")
        errors = request.validate()

        assert "agent_id cannot be empty" in errors

    def test_empty_agent_type_fails_validation(self):
        """Empty agent_type causes validation error."""
        request = self.create_request(agent_type="")
        errors = request.validate()

        assert "agent_type cannot be empty" in errors

    def test_empty_capabilities_fails_validation(self):
        """Empty capabilities list causes validation error."""
        request = self.create_request(capabilities=[])
        errors = request.validate()

        assert "capabilities cannot be empty" in errors

    def test_missing_trust_chain_hash_with_verify_true(self):
        """Missing trust_chain_hash fails when verify_trust is True."""
        request = self.create_request(
            trust_chain_hash="",
            verify_trust=True,
        )
        errors = request.validate()

        assert "trust_chain_hash cannot be empty when verify_trust is True" in errors

    def test_missing_trust_chain_hash_with_verify_false(self):
        """Missing trust_chain_hash is OK when verify_trust is False."""
        request = self.create_request(
            trust_chain_hash="",
            verify_trust=False,
        )
        errors = request.validate()

        assert len(errors) == 0

    def test_multiple_validation_errors(self):
        """Multiple validation errors are all reported."""
        request = RegistrationRequest(
            agent_id="",
            agent_type="",
            capabilities=[],
            trust_chain_hash="",
            verify_trust=True,
        )
        errors = request.validate()

        assert len(errors) >= 3  # At least agent_id, agent_type, capabilities

    def test_request_with_all_optional_fields(self):
        """Request can include all optional fields."""
        request = RegistrationRequest(
            agent_id="agent-001",
            agent_type="worker",
            capabilities=["cap1"],
            constraints=["read_only"],
            metadata={"version": "1.0"},
            trust_chain_hash="hash123",
            endpoint="localhost:8080",
            public_key="ssh-rsa AAAA...",
            verify_trust=True,
        )
        errors = request.validate()

        assert len(errors) == 0
        assert request.endpoint == "localhost:8080"
        assert request.public_key == "ssh-rsa AAAA..."

    def test_verify_trust_default_is_true(self):
        """verify_trust defaults to True for security."""
        request = RegistrationRequest(
            agent_id="agent-001",
            agent_type="worker",
            capabilities=["cap1"],
            trust_chain_hash="hash123",
        )

        assert request.verify_trust is True
