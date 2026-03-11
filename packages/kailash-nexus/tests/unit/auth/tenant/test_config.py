"""Unit tests for TenantConfig (TODO-310E).

Tier 1 tests - mocking allowed.
"""

import pytest
from nexus.auth.tenant.config import TenantConfig

# =============================================================================
# Tests: Default Values
# =============================================================================


class TestTenantConfigDefaults:
    """Test default configuration values."""

    def test_config_defaults(self):
        """Test all default values are correct."""
        config = TenantConfig()
        assert config.enabled is True
        assert config.tenant_id_header == "X-Tenant-ID"
        assert config.jwt_claim == "tenant_id"
        assert config.fallback_to_user_org is True
        assert config.org_field_name == "organization_id"
        assert config.validate_tenant_exists is True
        assert config.validate_tenant_active is True
        assert config.allow_admin_override is True
        assert config.admin_role == "super_admin"
        assert "/health" in config.exclude_paths
        assert "/metrics" in config.exclude_paths
        assert config.custom_resolver is None

    def test_config_custom_values(self):
        """Test setting custom values."""
        config = TenantConfig(
            enabled=False,
            tenant_id_header="X-Org-ID",
            jwt_claim="org_id",
            fallback_to_user_org=False,
            org_field_name="org_id",
            validate_tenant_exists=False,
            admin_role="admin",
            exclude_paths=["/health"],
        )
        assert config.enabled is False
        assert config.tenant_id_header == "X-Org-ID"
        assert config.jwt_claim == "org_id"
        assert config.fallback_to_user_org is False
        assert config.admin_role == "admin"

    def test_config_custom_resolver(self):
        """Test custom resolver configuration."""

        async def my_resolver(request):
            return None

        config = TenantConfig(custom_resolver=my_resolver)
        assert config.custom_resolver is my_resolver


# =============================================================================
# Tests: Package Exports
# =============================================================================


class TestTenantPackageExports:
    """Test package exports."""

    def test_config_exported(self):
        """TenantConfig accessible from tenant package."""
        from nexus.auth.tenant import TenantConfig as TC

        assert TC is TenantConfig

    def test_context_exported(self):
        """TenantContext accessible from tenant package."""
        from nexus.auth.tenant import TenantContext

        assert TenantContext is not None

    def test_info_exported(self):
        """TenantInfo accessible from tenant package."""
        from nexus.auth.tenant import TenantInfo

        assert TenantInfo is not None

    def test_middleware_exported(self):
        """TenantMiddleware accessible from tenant package."""
        from nexus.auth.tenant import TenantMiddleware

        assert TenantMiddleware is not None

    def test_resolver_exported(self):
        """TenantResolver accessible from tenant package."""
        from nexus.auth.tenant import TenantResolver

        assert TenantResolver is not None

    def test_helpers_exported(self):
        """Helper functions accessible from tenant package."""
        from nexus.auth.tenant import (
            get_current_tenant,
            get_current_tenant_id,
            require_tenant,
        )

        assert callable(get_current_tenant)
        assert callable(get_current_tenant_id)
        assert callable(require_tenant)

    def test_exceptions_exported(self):
        """Exception classes accessible from tenant package."""
        from nexus.auth.tenant import (
            TenantAccessDeniedError,
            TenantContextError,
            TenantError,
            TenantInactiveError,
            TenantNotFoundError,
        )

        assert issubclass(TenantContextError, TenantError)
        assert issubclass(TenantNotFoundError, TenantError)
        assert issubclass(TenantInactiveError, TenantError)
        assert issubclass(TenantAccessDeniedError, TenantError)

    def test_exports_from_auth_package(self):
        """Tenant components accessible from nexus.auth."""
        from nexus.auth import TenantConfig, TenantContext, TenantMiddleware

        assert TenantConfig is not None
        assert TenantContext is not None
        assert TenantMiddleware is not None
