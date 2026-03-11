"""Unit tests for tenant exceptions (TODO-310E).

Tier 1 tests - mocking allowed.
"""

import pytest
from nexus.auth.tenant.exceptions import (
    TenantAccessDeniedError,
    TenantContextError,
    TenantError,
    TenantInactiveError,
    TenantNotFoundError,
)

# =============================================================================
# Tests: Exception Hierarchy
# =============================================================================


class TestTenantExceptionHierarchy:
    """Test exception hierarchy."""

    def test_tenant_error_is_exception(self):
        """TenantError is an Exception."""
        assert issubclass(TenantError, Exception)

    def test_context_error_inherits(self):
        """TenantContextError inherits from TenantError."""
        assert issubclass(TenantContextError, TenantError)

    def test_not_found_inherits(self):
        """TenantNotFoundError inherits from TenantError."""
        assert issubclass(TenantNotFoundError, TenantError)

    def test_inactive_inherits(self):
        """TenantInactiveError inherits from TenantError."""
        assert issubclass(TenantInactiveError, TenantError)

    def test_access_denied_inherits(self):
        """TenantAccessDeniedError inherits from TenantError."""
        assert issubclass(TenantAccessDeniedError, TenantError)


# =============================================================================
# Tests: TenantNotFoundError
# =============================================================================


class TestTenantNotFoundError:
    """Test TenantNotFoundError."""

    def test_basic_creation(self):
        """Create with just tenant_id."""
        error = TenantNotFoundError(tenant_id="xyz")
        assert error.tenant_id == "xyz"
        assert error.available == []
        assert "xyz" in str(error)

    def test_with_available_list(self):
        """Create with available tenants."""
        error = TenantNotFoundError(
            tenant_id="xyz",
            available=["a", "b", "c"],
        )
        assert error.available == ["a", "b", "c"]
        assert "Available" in str(error)

    def test_custom_message(self):
        """Create with custom message."""
        error = TenantNotFoundError(
            tenant_id="xyz",
            message="Custom not found message",
        )
        assert str(error) == "Custom not found message"

    def test_catch_as_tenant_error(self):
        """Can be caught as TenantError."""
        with pytest.raises(TenantError):
            raise TenantNotFoundError(tenant_id="xyz")


# =============================================================================
# Tests: TenantInactiveError
# =============================================================================


class TestTenantInactiveError:
    """Test TenantInactiveError."""

    def test_basic_creation(self):
        """Create with tenant_id."""
        error = TenantInactiveError(tenant_id="xyz")
        assert error.tenant_id == "xyz"
        assert "inactive" in str(error)

    def test_custom_message(self):
        """Create with custom message."""
        error = TenantInactiveError(
            tenant_id="xyz",
            message="Suspended for billing",
        )
        assert str(error) == "Suspended for billing"


# =============================================================================
# Tests: TenantAccessDeniedError
# =============================================================================


class TestTenantAccessDeniedError:
    """Test TenantAccessDeniedError."""

    def test_basic_creation(self):
        """Create with just tenant_id."""
        error = TenantAccessDeniedError(tenant_id="xyz")
        assert error.tenant_id == "xyz"
        assert error.user_id is None
        assert error.reason == "Access denied"
        assert "xyz" in str(error)

    def test_with_user_id(self):
        """Create with user_id."""
        error = TenantAccessDeniedError(
            tenant_id="xyz",
            user_id="user-123",
        )
        assert error.user_id == "user-123"
        assert "user-123" in str(error)

    def test_with_reason(self):
        """Create with custom reason."""
        error = TenantAccessDeniedError(
            tenant_id="xyz",
            reason="Requires admin role",
        )
        assert error.reason == "Requires admin role"
        assert "Requires admin role" in str(error)

    def test_full_creation(self):
        """Create with all fields."""
        error = TenantAccessDeniedError(
            tenant_id="xyz",
            user_id="user-123",
            reason="Not authorized",
        )
        assert error.tenant_id == "xyz"
        assert error.user_id == "user-123"
        assert error.reason == "Not authorized"


# =============================================================================
# Tests: TenantContextError
# =============================================================================


class TestTenantContextError:
    """Test TenantContextError."""

    def test_basic_creation(self):
        """Create with message."""
        error = TenantContextError("No context active")
        assert str(error) == "No context active"

    def test_catch_as_tenant_error(self):
        """Can be caught as TenantError."""
        with pytest.raises(TenantError):
            raise TenantContextError("test")
