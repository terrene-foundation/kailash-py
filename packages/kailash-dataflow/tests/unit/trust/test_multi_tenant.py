#!/usr/bin/env python3
"""
Unit Tests for Trust-Aware Multi-Tenancy (CARE-021).

Tests the cross-tenant delegation and trust management for DataFlow.
These tests verify that EATP delegation chains are properly enforced
for cross-tenant data access.

Test Coverage:
- CrossTenantDelegation creation and validation
- CrossTenantDelegation access checking
- CrossTenantDelegation serialization
- TenantTrustManager creation and verification
- TenantTrustManager delegation management
- TenantTrustManager advanced features
- Edge cases

Total: 35 tests
"""

from datetime import datetime, timedelta, timezone
from typing import Set

import pytest

from dataflow.trust.multi_tenant import CrossTenantDelegation, TenantTrustManager

# === Test Group 1: CrossTenantDelegation Creation (6 tests) ===


class TestCrossTenantDelegationCreation:
    """Tests for CrossTenantDelegation dataclass creation."""

    def test_create_delegation_all_fields(self):
        """Test delegation creation with all fields populated."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=24)

        delegation = CrossTenantDelegation(
            delegation_id="del-001",
            source_tenant_id="tenant-source",
            target_tenant_id="tenant-target",
            delegating_agent_id="agent-delegator",
            receiving_agent_id="agent-receiver",
            allowed_models=["User", "Transaction"],
            allowed_operations={"SELECT", "INSERT"},
            row_filter={"department": "finance"},
            expires_at=expires,
            created_at=now,
            revoked=False,
            revoked_at=None,
            revoked_reason=None,
        )

        assert delegation.delegation_id == "del-001"
        assert delegation.source_tenant_id == "tenant-source"
        assert delegation.target_tenant_id == "tenant-target"
        assert delegation.delegating_agent_id == "agent-delegator"
        assert delegation.receiving_agent_id == "agent-receiver"
        assert delegation.allowed_models == ["User", "Transaction"]
        assert delegation.allowed_operations == {"SELECT", "INSERT"}
        assert delegation.row_filter == {"department": "finance"}
        assert delegation.expires_at == expires
        assert delegation.created_at == now
        assert delegation.revoked is False
        assert delegation.revoked_at is None
        assert delegation.revoked_reason is None

    def test_create_delegation_defaults(self):
        """Test delegation creation with default values works correctly."""
        now = datetime.now(timezone.utc)

        delegation = CrossTenantDelegation(
            delegation_id="del-002",
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            delegating_agent_id="agent-a",
            receiving_agent_id="agent-b",
            allowed_models=["User"],
            allowed_operations={"SELECT"},
            row_filter=None,
            expires_at=None,
            created_at=now,
        )

        # Check defaults
        assert delegation.revoked is False
        assert delegation.revoked_at is None
        assert delegation.revoked_reason is None
        assert delegation.row_filter is None
        assert delegation.expires_at is None

    def test_delegation_is_expired_true(self):
        """Test is_expired returns True for expired delegation."""
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        now = datetime.now(timezone.utc)

        delegation = CrossTenantDelegation(
            delegation_id="del-003",
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            delegating_agent_id="agent-a",
            receiving_agent_id="agent-b",
            allowed_models=["User"],
            allowed_operations={"SELECT"},
            row_filter=None,
            expires_at=past,  # Already expired
            created_at=now - timedelta(hours=2),
        )

        assert delegation.is_expired() is True

    def test_delegation_is_expired_false(self):
        """Test is_expired returns False for active delegation."""
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        now = datetime.now(timezone.utc)

        delegation = CrossTenantDelegation(
            delegation_id="del-004",
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            delegating_agent_id="agent-a",
            receiving_agent_id="agent-b",
            allowed_models=["User"],
            allowed_operations={"SELECT"},
            row_filter=None,
            expires_at=future,  # Not expired yet
            created_at=now,
        )

        assert delegation.is_expired() is False

    def test_delegation_is_active_when_valid(self):
        """Test is_active returns True when delegation is valid and not revoked."""
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        now = datetime.now(timezone.utc)

        delegation = CrossTenantDelegation(
            delegation_id="del-005",
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            delegating_agent_id="agent-a",
            receiving_agent_id="agent-b",
            allowed_models=["User"],
            allowed_operations={"SELECT"},
            row_filter=None,
            expires_at=future,
            created_at=now,
            revoked=False,
        )

        assert delegation.is_active() is True

    def test_delegation_is_active_when_revoked(self):
        """Test is_active returns False when delegation is revoked."""
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        now = datetime.now(timezone.utc)

        delegation = CrossTenantDelegation(
            delegation_id="del-006",
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            delegating_agent_id="agent-a",
            receiving_agent_id="agent-b",
            allowed_models=["User"],
            allowed_operations={"SELECT"},
            row_filter=None,
            expires_at=future,
            created_at=now,
            revoked=True,
            revoked_at=now,
            revoked_reason="Security concern",
        )

        assert delegation.is_active() is False


# === Test Group 2: CrossTenantDelegation Access Check (6 tests) ===


class TestCrossTenantDelegationAccessCheck:
    """Tests for CrossTenantDelegation.allows_access method."""

    def test_allows_access_matching(self):
        """Test allows_access returns True when model, operation, and agent all match."""
        now = datetime.now(timezone.utc)
        future = now + timedelta(hours=1)

        delegation = CrossTenantDelegation(
            delegation_id="del-007",
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            delegating_agent_id="agent-delegator",
            receiving_agent_id="agent-receiver",
            allowed_models=["User", "Transaction"],
            allowed_operations={"SELECT", "INSERT"},
            row_filter=None,
            expires_at=future,
            created_at=now,
        )

        assert delegation.allows_access("User", "SELECT", "agent-receiver") is True
        assert (
            delegation.allows_access("Transaction", "INSERT", "agent-receiver") is True
        )

    def test_allows_access_wrong_model(self):
        """Test allows_access returns False for wrong model."""
        now = datetime.now(timezone.utc)
        future = now + timedelta(hours=1)

        delegation = CrossTenantDelegation(
            delegation_id="del-008",
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            delegating_agent_id="agent-delegator",
            receiving_agent_id="agent-receiver",
            allowed_models=["User"],  # Only User
            allowed_operations={"SELECT"},
            row_filter=None,
            expires_at=future,
            created_at=now,
        )

        assert (
            delegation.allows_access("Transaction", "SELECT", "agent-receiver") is False
        )

    def test_allows_access_wrong_operation(self):
        """Test allows_access returns False for wrong operation."""
        now = datetime.now(timezone.utc)
        future = now + timedelta(hours=1)

        delegation = CrossTenantDelegation(
            delegation_id="del-009",
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            delegating_agent_id="agent-delegator",
            receiving_agent_id="agent-receiver",
            allowed_models=["User"],
            allowed_operations={"SELECT"},  # Only SELECT
            row_filter=None,
            expires_at=future,
            created_at=now,
        )

        assert delegation.allows_access("User", "INSERT", "agent-receiver") is False
        assert delegation.allows_access("User", "DELETE", "agent-receiver") is False

    def test_allows_access_wrong_agent(self):
        """Test allows_access returns False for wrong receiving agent."""
        now = datetime.now(timezone.utc)
        future = now + timedelta(hours=1)

        delegation = CrossTenantDelegation(
            delegation_id="del-010",
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            delegating_agent_id="agent-delegator",
            receiving_agent_id="agent-receiver",  # Only this agent
            allowed_models=["User"],
            allowed_operations={"SELECT"},
            row_filter=None,
            expires_at=future,
            created_at=now,
        )

        assert delegation.allows_access("User", "SELECT", "agent-other") is False

    def test_allows_access_expired(self):
        """Test allows_access returns False for expired delegation."""
        now = datetime.now(timezone.utc)
        past = now - timedelta(hours=1)

        delegation = CrossTenantDelegation(
            delegation_id="del-011",
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            delegating_agent_id="agent-delegator",
            receiving_agent_id="agent-receiver",
            allowed_models=["User"],
            allowed_operations={"SELECT"},
            row_filter=None,
            expires_at=past,  # Expired
            created_at=now - timedelta(hours=2),
        )

        assert delegation.allows_access("User", "SELECT", "agent-receiver") is False

    def test_allows_access_revoked(self):
        """Test allows_access returns False for revoked delegation."""
        now = datetime.now(timezone.utc)
        future = now + timedelta(hours=1)

        delegation = CrossTenantDelegation(
            delegation_id="del-012",
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            delegating_agent_id="agent-delegator",
            receiving_agent_id="agent-receiver",
            allowed_models=["User"],
            allowed_operations={"SELECT"},
            row_filter=None,
            expires_at=future,
            created_at=now,
            revoked=True,  # Revoked
            revoked_at=now,
        )

        assert delegation.allows_access("User", "SELECT", "agent-receiver") is False


# === Test Group 3: CrossTenantDelegation Serialization (2 tests) ===


class TestCrossTenantDelegationSerialization:
    """Tests for CrossTenantDelegation serialization methods."""

    def test_delegation_to_dict_and_from_dict(self):
        """Test roundtrip serialization of delegation."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=24)

        original = CrossTenantDelegation(
            delegation_id="del-013",
            source_tenant_id="tenant-source",
            target_tenant_id="tenant-target",
            delegating_agent_id="agent-delegator",
            receiving_agent_id="agent-receiver",
            allowed_models=["User", "Transaction"],
            allowed_operations={"SELECT", "INSERT"},
            row_filter={"department": "finance"},
            expires_at=expires,
            created_at=now,
            revoked=False,
            revoked_at=None,
            revoked_reason=None,
        )

        # Serialize to dict
        data = original.to_dict()

        # Deserialize back
        restored = CrossTenantDelegation.from_dict(data)

        # Verify all fields match
        assert restored.delegation_id == original.delegation_id
        assert restored.source_tenant_id == original.source_tenant_id
        assert restored.target_tenant_id == original.target_tenant_id
        assert restored.delegating_agent_id == original.delegating_agent_id
        assert restored.receiving_agent_id == original.receiving_agent_id
        assert restored.allowed_models == original.allowed_models
        assert restored.allowed_operations == original.allowed_operations
        assert restored.row_filter == original.row_filter
        assert restored.revoked == original.revoked
        # Note: datetime comparison may need tolerance
        assert restored.created_at is not None

    def test_delegation_from_dict_with_set(self):
        """Test that operations set is preserved through serialization."""
        now = datetime.now(timezone.utc)

        delegation = CrossTenantDelegation(
            delegation_id="del-014",
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            delegating_agent_id="agent-a",
            receiving_agent_id="agent-b",
            allowed_models=["User"],
            allowed_operations={"SELECT", "INSERT", "UPDATE"},
            row_filter=None,
            expires_at=None,
            created_at=now,
        )

        data = delegation.to_dict()
        restored = CrossTenantDelegation.from_dict(data)

        # Verify set is preserved (order doesn't matter)
        assert isinstance(restored.allowed_operations, set)
        assert restored.allowed_operations == {"SELECT", "INSERT", "UPDATE"}


# === Test Group 4: TenantTrustManager Creation and Verification (8 tests) ===


class TestTenantTrustManagerVerification:
    """Tests for TenantTrustManager verification methods."""

    @pytest.mark.asyncio
    async def test_same_tenant_always_allowed(self):
        """Test that same-tenant access is always allowed."""
        manager = TenantTrustManager(strict_mode=True)

        allowed, reason = await manager.verify_cross_tenant_access(
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-a",  # Same tenant
            agent_id="agent-001",
            model="User",
            operation="SELECT",
        )

        assert allowed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_cross_tenant_without_delegation_denied(self):
        """Test that cross-tenant access without delegation is denied in strict mode."""
        manager = TenantTrustManager(strict_mode=True)

        allowed, reason = await manager.verify_cross_tenant_access(
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",  # Different tenant
            agent_id="agent-001",
            model="User",
            operation="SELECT",
        )

        assert allowed is False
        assert reason is not None
        assert "delegation" in reason.lower() or "cross-tenant" in reason.lower()

    @pytest.mark.asyncio
    async def test_cross_tenant_with_valid_delegation_allowed(self):
        """Test that cross-tenant access with valid delegation is allowed."""
        manager = TenantTrustManager(strict_mode=True)

        # Create delegation first
        delegation = await manager.create_cross_tenant_delegation(
            source_tenant_id="tenant-source",
            target_tenant_id="tenant-target",
            delegating_agent_id="agent-delegator",
            receiving_agent_id="agent-receiver",
            allowed_models=["User"],
            allowed_operations={"SELECT"},
        )

        # Verify access
        allowed, reason = await manager.verify_cross_tenant_access(
            source_tenant_id="tenant-source",
            target_tenant_id="tenant-target",
            agent_id="agent-receiver",
            model="User",
            operation="SELECT",
        )

        assert allowed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_cross_tenant_expired_delegation_denied(self):
        """Test that cross-tenant access with expired delegation is denied."""
        manager = TenantTrustManager(strict_mode=True)

        # Create delegation that expires immediately
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        delegation = await manager.create_cross_tenant_delegation(
            source_tenant_id="tenant-source",
            target_tenant_id="tenant-target",
            delegating_agent_id="agent-delegator",
            receiving_agent_id="agent-receiver",
            allowed_models=["User"],
            allowed_operations={"SELECT"},
            expires_at=past,
        )

        # Verify access
        allowed, reason = await manager.verify_cross_tenant_access(
            source_tenant_id="tenant-source",
            target_tenant_id="tenant-target",
            agent_id="agent-receiver",
            model="User",
            operation="SELECT",
        )

        assert allowed is False
        assert reason is not None

    @pytest.mark.asyncio
    async def test_cross_tenant_revoked_delegation_denied(self):
        """Test that cross-tenant access with revoked delegation is denied."""
        manager = TenantTrustManager(strict_mode=True)

        # Create and immediately revoke delegation
        delegation = await manager.create_cross_tenant_delegation(
            source_tenant_id="tenant-source",
            target_tenant_id="tenant-target",
            delegating_agent_id="agent-delegator",
            receiving_agent_id="agent-receiver",
            allowed_models=["User"],
            allowed_operations={"SELECT"},
        )

        await manager.revoke_delegation(delegation.delegation_id, "Testing revocation")

        # Verify access
        allowed, reason = await manager.verify_cross_tenant_access(
            source_tenant_id="tenant-source",
            target_tenant_id="tenant-target",
            agent_id="agent-receiver",
            model="User",
            operation="SELECT",
        )

        assert allowed is False
        assert reason is not None

    @pytest.mark.asyncio
    async def test_cross_tenant_wrong_model_denied(self):
        """Test that cross-tenant access for wrong model is denied."""
        manager = TenantTrustManager(strict_mode=True)

        # Create delegation for User model only
        await manager.create_cross_tenant_delegation(
            source_tenant_id="tenant-source",
            target_tenant_id="tenant-target",
            delegating_agent_id="agent-delegator",
            receiving_agent_id="agent-receiver",
            allowed_models=["User"],  # Only User
            allowed_operations={"SELECT"},
        )

        # Try to access Transaction model
        allowed, reason = await manager.verify_cross_tenant_access(
            source_tenant_id="tenant-source",
            target_tenant_id="tenant-target",
            agent_id="agent-receiver",
            model="Transaction",  # Wrong model
            operation="SELECT",
        )

        assert allowed is False
        assert reason is not None

    @pytest.mark.asyncio
    async def test_cross_tenant_wrong_operation_denied(self):
        """Test that cross-tenant access for wrong operation is denied."""
        manager = TenantTrustManager(strict_mode=True)

        # Create delegation for SELECT only
        await manager.create_cross_tenant_delegation(
            source_tenant_id="tenant-source",
            target_tenant_id="tenant-target",
            delegating_agent_id="agent-delegator",
            receiving_agent_id="agent-receiver",
            allowed_models=["User"],
            allowed_operations={"SELECT"},  # Only SELECT
        )

        # Try to DELETE
        allowed, reason = await manager.verify_cross_tenant_access(
            source_tenant_id="tenant-source",
            target_tenant_id="tenant-target",
            agent_id="agent-receiver",
            model="User",
            operation="DELETE",  # Wrong operation
        )

        assert allowed is False
        assert reason is not None

    @pytest.mark.asyncio
    async def test_non_strict_mode_allows_cross_tenant(self):
        """Test that non-strict mode allows cross-tenant access with warning."""
        manager = TenantTrustManager(strict_mode=False)  # Non-strict

        allowed, reason = await manager.verify_cross_tenant_access(
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            agent_id="agent-001",
            model="User",
            operation="SELECT",
        )

        # Non-strict mode should allow access
        assert allowed is True
        # But may include a warning message
        # (reason can be None or a warning string)


# === Test Group 5: TenantTrustManager Delegation Management (6 tests) ===


class TestTenantTrustManagerDelegationManagement:
    """Tests for TenantTrustManager delegation management methods."""

    @pytest.mark.asyncio
    async def test_create_delegation_generates_id(self):
        """Test that create_delegation generates a valid UUID delegation_id."""
        manager = TenantTrustManager()

        delegation = await manager.create_cross_tenant_delegation(
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            delegating_agent_id="agent-a",
            receiving_agent_id="agent-b",
            allowed_models=["User"],
        )

        assert delegation.delegation_id is not None
        assert len(delegation.delegation_id) > 0
        # UUID format check (should contain hyphens)
        assert "-" in delegation.delegation_id

    @pytest.mark.asyncio
    async def test_create_delegation_self_tenant_rejected(self):
        """Test that self-delegation (source == target) is rejected."""
        manager = TenantTrustManager()

        with pytest.raises(ValueError) as exc_info:
            await manager.create_cross_tenant_delegation(
                source_tenant_id="tenant-a",
                target_tenant_id="tenant-a",  # Same as source
                delegating_agent_id="agent-a",
                receiving_agent_id="agent-b",
                allowed_models=["User"],
            )

        assert (
            "same tenant" in str(exc_info.value).lower()
            or "self" in str(exc_info.value).lower()
        )

    @pytest.mark.asyncio
    async def test_revoke_delegation_succeeds(self):
        """Test that revocation marks delegation as revoked."""
        manager = TenantTrustManager()

        delegation = await manager.create_cross_tenant_delegation(
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            delegating_agent_id="agent-a",
            receiving_agent_id="agent-b",
            allowed_models=["User"],
        )

        result = await manager.revoke_delegation(
            delegation.delegation_id,
            reason="Security audit",
        )

        assert result is True

        # Verify delegation is now revoked
        revoked_delegation = await manager.get_delegation(delegation.delegation_id)
        assert revoked_delegation is not None
        assert revoked_delegation.revoked is True
        assert revoked_delegation.revoked_reason == "Security audit"
        assert revoked_delegation.revoked_at is not None

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_delegation(self):
        """Test that revoking non-existent delegation returns False."""
        manager = TenantTrustManager()

        result = await manager.revoke_delegation(
            "nonexistent-delegation-id",
            reason="Test",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_list_delegations_all(self):
        """Test that list_delegations returns all delegations."""
        manager = TenantTrustManager()

        # Create multiple delegations
        await manager.create_cross_tenant_delegation(
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            delegating_agent_id="agent-a",
            receiving_agent_id="agent-b",
            allowed_models=["User"],
        )

        await manager.create_cross_tenant_delegation(
            source_tenant_id="tenant-b",
            target_tenant_id="tenant-c",
            delegating_agent_id="agent-b",
            receiving_agent_id="agent-c",
            allowed_models=["Transaction"],
        )

        delegations = await manager.list_delegations(active_only=False)

        assert len(delegations) == 2

    @pytest.mark.asyncio
    async def test_list_delegations_by_tenant(self):
        """Test that list_delegations can filter by tenant."""
        manager = TenantTrustManager()

        # Create delegations involving different tenants
        await manager.create_cross_tenant_delegation(
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            delegating_agent_id="agent-a",
            receiving_agent_id="agent-b",
            allowed_models=["User"],
        )

        await manager.create_cross_tenant_delegation(
            source_tenant_id="tenant-c",
            target_tenant_id="tenant-d",
            delegating_agent_id="agent-c",
            receiving_agent_id="agent-d",
            allowed_models=["Transaction"],
        )

        # Filter by tenant-a (should find 1)
        delegations_a = await manager.list_delegations(
            tenant_id="tenant-a",
            active_only=False,
        )
        assert len(delegations_a) == 1
        assert delegations_a[0].source_tenant_id == "tenant-a"


# === Test Group 6: TenantTrustManager Advanced Features (5 tests) ===


class TestTenantTrustManagerAdvancedFeatures:
    """Tests for TenantTrustManager advanced features."""

    @pytest.mark.asyncio
    async def test_list_active_only(self):
        """Test that list_delegations with active_only=True only returns active delegations."""
        manager = TenantTrustManager()

        # Create two delegations
        del1 = await manager.create_cross_tenant_delegation(
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            delegating_agent_id="agent-a",
            receiving_agent_id="agent-b",
            allowed_models=["User"],
        )

        await manager.create_cross_tenant_delegation(
            source_tenant_id="tenant-c",
            target_tenant_id="tenant-d",
            delegating_agent_id="agent-c",
            receiving_agent_id="agent-d",
            allowed_models=["Transaction"],
        )

        # Revoke one
        await manager.revoke_delegation(del1.delegation_id)

        # List active only
        active_delegations = await manager.list_delegations(active_only=True)
        assert len(active_delegations) == 1
        assert active_delegations[0].source_tenant_id == "tenant-c"

    @pytest.mark.asyncio
    async def test_get_delegation_by_id(self):
        """Test that get_delegation retrieves a specific delegation by ID."""
        manager = TenantTrustManager()

        created = await manager.create_cross_tenant_delegation(
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            delegating_agent_id="agent-a",
            receiving_agent_id="agent-b",
            allowed_models=["User"],
        )

        retrieved = await manager.get_delegation(created.delegation_id)

        assert retrieved is not None
        assert retrieved.delegation_id == created.delegation_id
        assert retrieved.source_tenant_id == "tenant-a"
        assert retrieved.target_tenant_id == "tenant-b"

    @pytest.mark.asyncio
    async def test_get_active_delegations_for_agent(self):
        """Test that get_active_delegations_for_agent filters by receiving agent."""
        manager = TenantTrustManager()

        # Create delegations with different receivers
        await manager.create_cross_tenant_delegation(
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            delegating_agent_id="agent-delegator",
            receiving_agent_id="agent-receiver-1",
            allowed_models=["User"],
        )

        await manager.create_cross_tenant_delegation(
            source_tenant_id="tenant-c",
            target_tenant_id="tenant-d",
            delegating_agent_id="agent-delegator",
            receiving_agent_id="agent-receiver-2",
            allowed_models=["Transaction"],
        )

        await manager.create_cross_tenant_delegation(
            source_tenant_id="tenant-e",
            target_tenant_id="tenant-f",
            delegating_agent_id="agent-delegator",
            receiving_agent_id="agent-receiver-1",  # Same as first
            allowed_models=["Order"],
        )

        # Get delegations for agent-receiver-1
        delegations = await manager.get_active_delegations_for_agent("agent-receiver-1")

        assert len(delegations) == 2
        for d in delegations:
            assert d.receiving_agent_id == "agent-receiver-1"

    @pytest.mark.asyncio
    async def test_get_row_filter_for_access(self):
        """Test that get_row_filter_for_access extracts the row filter from delegation."""
        manager = TenantTrustManager()

        await manager.create_cross_tenant_delegation(
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            delegating_agent_id="agent-delegator",
            receiving_agent_id="agent-receiver",
            allowed_models=["User"],
            row_filter={"department": "finance", "status": "active"},
        )

        row_filter = manager.get_row_filter_for_access(
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            agent_id="agent-receiver",
            model="User",
        )

        assert row_filter is not None
        assert row_filter == {"department": "finance", "status": "active"}

    @pytest.mark.asyncio
    async def test_get_row_filter_no_delegation(self):
        """Test that get_row_filter_for_access returns None when no delegation exists."""
        manager = TenantTrustManager()

        row_filter = manager.get_row_filter_for_access(
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            agent_id="agent-receiver",
            model="User",
        )

        assert row_filter is None


# === Test Group 7: Edge Cases (2 tests) ===


class TestMultiTenantEdgeCases:
    """Tests for edge cases in multi-tenant functionality."""

    @pytest.mark.asyncio
    async def test_multiple_delegations_same_tenants(self):
        """Test that multiple delegations between same tenants are supported."""
        manager = TenantTrustManager(strict_mode=True)

        # Create multiple delegations between same tenant pair
        del1 = await manager.create_cross_tenant_delegation(
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            delegating_agent_id="agent-a",
            receiving_agent_id="agent-b1",  # Different receiver
            allowed_models=["User"],
        )

        del2 = await manager.create_cross_tenant_delegation(
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            delegating_agent_id="agent-a",
            receiving_agent_id="agent-b2",  # Different receiver
            allowed_models=["Transaction"],
        )

        assert del1.delegation_id != del2.delegation_id

        # Both should have access to their respective models
        allowed1, _ = await manager.verify_cross_tenant_access(
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            agent_id="agent-b1",
            model="User",
            operation="SELECT",
        )
        assert allowed1 is True

        allowed2, _ = await manager.verify_cross_tenant_access(
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            agent_id="agent-b2",
            model="Transaction",
            operation="SELECT",
        )
        assert allowed2 is True

    @pytest.mark.asyncio
    async def test_delegation_default_operations_select_only(self):
        """Test that default allowed_operations is SELECT only."""
        manager = TenantTrustManager(strict_mode=True)

        # Create delegation without specifying operations
        delegation = await manager.create_cross_tenant_delegation(
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            delegating_agent_id="agent-a",
            receiving_agent_id="agent-b",
            allowed_models=["User"],
            # No allowed_operations specified
        )

        # Default should be SELECT only
        assert delegation.allowed_operations == {"SELECT"}

        # SELECT should be allowed
        allowed_select, _ = await manager.verify_cross_tenant_access(
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            agent_id="agent-b",
            model="User",
            operation="SELECT",
        )
        assert allowed_select is True

        # INSERT should be denied
        allowed_insert, _ = await manager.verify_cross_tenant_access(
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            agent_id="agent-b",
            model="User",
            operation="INSERT",
        )
        assert allowed_insert is False


# === Test Group: CARE-058b Operation Validation (Security Fix) ===


class TestOperationValidation:
    """Tests for CARE-058b: allowed_operations validation.

    Security fix: CrossTenantDelegation now validates that all operations
    in allowed_operations are from a valid allowlist.
    """

    @pytest.mark.asyncio
    async def test_valid_operations_accepted(self):
        """Test that valid operations are accepted.

        CARE-058b: SELECT, INSERT, UPDATE, DELETE are all valid.
        """
        manager = TenantTrustManager(strict_mode=True)

        # All valid operations should be accepted
        delegation = await manager.create_cross_tenant_delegation(
            source_tenant_id="tenant-a",
            target_tenant_id="tenant-b",
            delegating_agent_id="agent-a",
            receiving_agent_id="agent-b",
            allowed_models=["User"],
            allowed_operations={"SELECT", "INSERT", "UPDATE", "DELETE"},
        )

        assert delegation.allowed_operations == {"SELECT", "INSERT", "UPDATE", "DELETE"}

    @pytest.mark.asyncio
    async def test_invalid_operation_rejected(self):
        """Test that invalid operations are rejected with ValueError.

        CARE-058b: Operations not in the allowlist should raise ValueError.
        """
        manager = TenantTrustManager(strict_mode=True)

        with pytest.raises(ValueError) as exc_info:
            await manager.create_cross_tenant_delegation(
                source_tenant_id="tenant-a",
                target_tenant_id="tenant-b",
                delegating_agent_id="agent-a",
                receiving_agent_id="agent-b",
                allowed_models=["User"],
                allowed_operations={"SELECT", "DROP"},  # DROP is invalid
            )

        error_msg = str(exc_info.value).lower()
        assert "invalid" in error_msg
        assert "drop" in error_msg.lower()

    @pytest.mark.asyncio
    async def test_multiple_invalid_operations_rejected(self):
        """Test that multiple invalid operations are all reported.

        CARE-058b: Error message should list all invalid operations.
        """
        manager = TenantTrustManager(strict_mode=True)

        with pytest.raises(ValueError) as exc_info:
            await manager.create_cross_tenant_delegation(
                source_tenant_id="tenant-a",
                target_tenant_id="tenant-b",
                delegating_agent_id="agent-a",
                receiving_agent_id="agent-b",
                allowed_models=["User"],
                allowed_operations={"TRUNCATE", "DROP", "ALTER"},  # All invalid
            )

        error_msg = str(exc_info.value)
        # All invalid operations should be mentioned
        assert "TRUNCATE" in error_msg or "truncate" in error_msg.lower()
        assert "DROP" in error_msg or "drop" in error_msg.lower()
        assert "ALTER" in error_msg or "alter" in error_msg.lower()
