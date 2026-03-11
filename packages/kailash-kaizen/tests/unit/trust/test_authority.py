"""
Unit tests for OrganizationalAuthorityRegistry and OrganizationalAuthority.

Tests cover:
- OrganizationalAuthority data class
- AuthorityPermission enum
- Serialization/deserialization
"""

from datetime import datetime

import pytest
from kaizen.trust.authority import AuthorityPermission, OrganizationalAuthority
from kaizen.trust.chain import AuthorityType


class TestAuthorityPermission:
    """Tests for AuthorityPermission enum."""

    def test_permission_values(self):
        """AuthorityPermission has expected values."""
        assert AuthorityPermission.CREATE_AGENTS.value == "create_agents"
        assert AuthorityPermission.DEACTIVATE_AGENTS.value == "deactivate_agents"
        assert AuthorityPermission.DELEGATE_TRUST.value == "delegate_trust"
        assert AuthorityPermission.GRANT_CAPABILITIES.value == "grant_capabilities"
        assert AuthorityPermission.REVOKE_CAPABILITIES.value == "revoke_capabilities"
        assert (
            AuthorityPermission.CREATE_SUBORDINATE_AUTHORITIES.value
            == "create_subordinate_authorities"
        )


class TestOrganizationalAuthority:
    """Tests for OrganizationalAuthority dataclass."""

    @pytest.fixture
    def sample_authority(self):
        """Create a sample authority for testing."""
        return OrganizationalAuthority(
            id="org-acme",
            name="Acme Corporation",
            authority_type=AuthorityType.ORGANIZATION,
            public_key="base64-public-key",
            signing_key_id="acme-signing-key-001",
            permissions=[
                AuthorityPermission.CREATE_AGENTS,
                AuthorityPermission.DELEGATE_TRUST,
            ],
            parent_authority_id=None,
            created_at=datetime(2025, 1, 1, 10, 0, 0),
            updated_at=datetime(2025, 1, 1, 10, 0, 0),
            is_active=True,
            metadata={"department": "Engineering"},
        )

    def test_authority_creation(self, sample_authority):
        """OrganizationalAuthority stores all attributes."""
        assert sample_authority.id == "org-acme"
        assert sample_authority.name == "Acme Corporation"
        assert sample_authority.authority_type == AuthorityType.ORGANIZATION
        assert sample_authority.public_key == "base64-public-key"
        assert sample_authority.signing_key_id == "acme-signing-key-001"
        assert len(sample_authority.permissions) == 2
        assert sample_authority.parent_authority_id is None
        assert sample_authority.is_active is True
        assert sample_authority.metadata == {"department": "Engineering"}

    def test_authority_has_permission(self, sample_authority):
        """has_permission correctly checks permissions."""
        assert (
            sample_authority.has_permission(AuthorityPermission.CREATE_AGENTS) is True
        )
        assert (
            sample_authority.has_permission(AuthorityPermission.DELEGATE_TRUST) is True
        )
        assert (
            sample_authority.has_permission(AuthorityPermission.REVOKE_CAPABILITIES)
            is False
        )

    def test_authority_to_dict(self, sample_authority):
        """to_dict serializes authority correctly."""
        data = sample_authority.to_dict()

        assert data["id"] == "org-acme"
        assert data["name"] == "Acme Corporation"
        assert data["authority_type"] == "organization"
        assert data["public_key"] == "base64-public-key"
        assert data["signing_key_id"] == "acme-signing-key-001"
        assert data["permissions"] == ["create_agents", "delegate_trust"]
        assert data["parent_authority_id"] is None
        assert data["is_active"] is True
        assert data["metadata"] == {"department": "Engineering"}
        assert "created_at" in data
        assert "updated_at" in data

    def test_authority_from_dict(self):
        """from_dict deserializes authority correctly."""
        data = {
            "id": "org-test",
            "name": "Test Organization",
            "authority_type": "organization",
            "public_key": "test-key",
            "signing_key_id": "test-signing-key",
            "permissions": ["create_agents"],
            "parent_authority_id": "org-parent",
            "created_at": "2025-01-01T10:00:00",
            "updated_at": "2025-01-01T10:00:00",
            "is_active": True,
            "metadata": {},
        }

        authority = OrganizationalAuthority.from_dict(data)

        assert authority.id == "org-test"
        assert authority.name == "Test Organization"
        assert authority.authority_type == AuthorityType.ORGANIZATION
        assert authority.public_key == "test-key"
        assert authority.signing_key_id == "test-signing-key"
        assert authority.permissions == [AuthorityPermission.CREATE_AGENTS]
        assert authority.parent_authority_id == "org-parent"
        assert authority.is_active is True

    def test_authority_roundtrip(self, sample_authority):
        """Authority survives to_dict/from_dict roundtrip."""
        data = sample_authority.to_dict()
        restored = OrganizationalAuthority.from_dict(data)

        assert restored.id == sample_authority.id
        assert restored.name == sample_authority.name
        assert restored.authority_type == sample_authority.authority_type
        assert restored.public_key == sample_authority.public_key
        assert restored.signing_key_id == sample_authority.signing_key_id
        assert restored.permissions == sample_authority.permissions
        assert restored.parent_authority_id == sample_authority.parent_authority_id
        assert restored.is_active == sample_authority.is_active
        assert restored.metadata == sample_authority.metadata

    def test_authority_default_values(self):
        """OrganizationalAuthority has correct default values."""
        authority = OrganizationalAuthority(
            id="org-minimal",
            name="Minimal Org",
            authority_type=AuthorityType.ORGANIZATION,
            public_key="key",
            signing_key_id="signing-key",
        )

        assert authority.permissions == []
        assert authority.parent_authority_id is None
        assert authority.is_active is True
        assert authority.metadata == {}

    def test_authority_with_hierarchical_parent(self):
        """Authority can have parent authority."""
        child = OrganizationalAuthority(
            id="dept-engineering",
            name="Engineering Department",
            authority_type=AuthorityType.ORGANIZATION,  # Using ORGANIZATION since DEPARTMENT doesn't exist
            public_key="key",
            signing_key_id="signing-key",
            parent_authority_id="org-acme",
        )

        assert child.parent_authority_id == "org-acme"

    def test_authority_inactive_state(self):
        """Authority can be created as inactive."""
        authority = OrganizationalAuthority(
            id="org-inactive",
            name="Inactive Org",
            authority_type=AuthorityType.ORGANIZATION,
            public_key="key",
            signing_key_id="signing-key",
            is_active=False,
            metadata={"deactivation_reason": "test"},
        )

        assert authority.is_active is False
        assert authority.metadata["deactivation_reason"] == "test"


class TestAuthorityPermissionCombinations:
    """Tests for various permission combinations."""

    def test_full_permissions_authority(self):
        """Authority can have all permissions."""
        authority = OrganizationalAuthority(
            id="org-admin",
            name="Admin Organization",
            authority_type=AuthorityType.ORGANIZATION,
            public_key="key",
            signing_key_id="signing-key",
            permissions=[
                AuthorityPermission.CREATE_AGENTS,
                AuthorityPermission.DEACTIVATE_AGENTS,
                AuthorityPermission.DELEGATE_TRUST,
                AuthorityPermission.GRANT_CAPABILITIES,
                AuthorityPermission.REVOKE_CAPABILITIES,
                AuthorityPermission.CREATE_SUBORDINATE_AUTHORITIES,
            ],
        )

        assert len(authority.permissions) == 6
        for perm in AuthorityPermission:
            assert authority.has_permission(perm) is True

    def test_no_permissions_authority(self):
        """Authority can have no permissions."""
        authority = OrganizationalAuthority(
            id="org-readonly",
            name="Read-Only Organization",
            authority_type=AuthorityType.ORGANIZATION,
            public_key="key",
            signing_key_id="signing-key",
            permissions=[],
        )

        assert len(authority.permissions) == 0
        for perm in AuthorityPermission:
            assert authority.has_permission(perm) is False

    def test_limited_permissions_authority(self):
        """Authority with limited permissions works correctly."""
        authority = OrganizationalAuthority(
            id="org-limited",
            name="Limited Organization",
            authority_type=AuthorityType.ORGANIZATION,
            public_key="key",
            signing_key_id="signing-key",
            permissions=[AuthorityPermission.CREATE_AGENTS],
        )

        assert authority.has_permission(AuthorityPermission.CREATE_AGENTS) is True
        assert authority.has_permission(AuthorityPermission.DEACTIVATE_AGENTS) is False
