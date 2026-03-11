"""Integration tests for NexusAuthPlugin (TODO-310G).

Tier 2 tests - NO MOCKING. Uses real FastAPI TestClient with real
middleware for full auth stack testing.
"""

import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nexus.auth.audit.config import AuditConfig
from nexus.auth.jwt import JWTConfig
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth.rate_limit.config import RateLimitConfig
from nexus.auth.tenant.config import TenantConfig

# =============================================================================
# Tests: Plugin Construction
# =============================================================================


class TestNexusAuthPluginConstruction:
    """Test plugin construction and validation."""

    def test_minimal_construction(self):
        """Plugin can be created with no components."""
        plugin = NexusAuthPlugin()
        assert plugin.name == "nexus_auth"
        assert plugin.enabled_components == []

    def test_jwt_only(self):
        """Plugin with JWT only."""
        plugin = NexusAuthPlugin(
            jwt=JWTConfig(secret="test-secret-key-for-plugin-integration"),
        )
        assert "jwt" in plugin.enabled_components

    def test_jwt_with_audit(self):
        """Plugin with JWT and audit."""
        plugin = NexusAuthPlugin(
            jwt=JWTConfig(secret="test-secret-key-for-plugin-integration"),
            audit=AuditConfig(backend="logging"),
        )
        assert "jwt" in plugin.enabled_components
        assert "audit" in plugin.enabled_components

    def test_rbac_without_jwt_raises(self):
        """RBAC without JWT raises ValueError."""
        with pytest.raises(ValueError, match="RBAC requires JWT"):
            NexusAuthPlugin(
                rbac={"admin": ["*"]},
            )

    def test_tenant_without_jwt_raises(self):
        """Tenant without JWT raises ValueError."""
        with pytest.raises(ValueError, match="Tenant isolation requires JWT"):
            NexusAuthPlugin(
                tenant_isolation=TenantConfig(),
            )

    def test_rbac_with_jwt_ok(self):
        """RBAC with JWT succeeds."""
        plugin = NexusAuthPlugin(
            jwt=JWTConfig(secret="test-secret-key-for-plugin-integration"),
            rbac={"admin": ["*"], "user": ["read:*"]},
        )
        assert "jwt" in plugin.enabled_components
        assert "rbac" in plugin.enabled_components

    def test_all_components(self):
        """Plugin with all components."""
        plugin = NexusAuthPlugin(
            jwt=JWTConfig(secret="test-secret-key-for-plugin-integration"),
            rbac={"admin": ["*"]},
            rate_limit=RateLimitConfig(),
            tenant_isolation=TenantConfig(
                validate_tenant_exists=False,
            ),
            audit=AuditConfig(),
        )
        assert len(plugin.enabled_components) == 5

    def test_description(self):
        """Description includes enabled components."""
        plugin = NexusAuthPlugin(
            jwt=JWTConfig(secret="test-secret-key-for-plugin-integration"),
            audit=AuditConfig(),
        )
        assert "JWT" in plugin.description
        assert "Audit" in plugin.description


# =============================================================================
# Tests: Factory Methods
# =============================================================================


class TestNexusAuthPluginFactories:
    """Test factory methods."""

    def test_basic_auth_factory(self):
        """basic_auth factory creates JWT + audit."""
        plugin = NexusAuthPlugin.basic_auth(
            jwt=JWTConfig(secret="test-secret-key-for-plugin-integration"),
        )
        assert "jwt" in plugin.enabled_components
        assert "audit" in plugin.enabled_components
        assert len(plugin.enabled_components) == 2

    def test_basic_auth_custom_audit(self):
        """basic_auth with custom audit config."""
        plugin = NexusAuthPlugin.basic_auth(
            jwt=JWTConfig(secret="test-secret-key-for-plugin-integration"),
            audit=AuditConfig(backend="logging", log_level="DEBUG"),
        )
        assert plugin.audit_config.log_level == "DEBUG"

    def test_saas_app_factory(self):
        """saas_app factory creates JWT + RBAC + tenant + audit."""
        plugin = NexusAuthPlugin.saas_app(
            jwt=JWTConfig(secret="test-secret-key-for-plugin-integration"),
            rbac={"admin": ["*"], "user": ["read:*"]},
            tenant_isolation=TenantConfig(
                validate_tenant_exists=False,
            ),
        )
        assert "jwt" in plugin.enabled_components
        assert "rbac" in plugin.enabled_components
        assert "tenant" in plugin.enabled_components
        assert "audit" in plugin.enabled_components

    def test_enterprise_factory(self):
        """enterprise factory creates all components."""
        plugin = NexusAuthPlugin.enterprise(
            jwt=JWTConfig(secret="test-secret-key-for-plugin-integration"),
            rbac={"admin": ["*"]},
            rate_limit=RateLimitConfig(),
            tenant_isolation=TenantConfig(
                validate_tenant_exists=False,
            ),
            audit=AuditConfig(),
        )
        assert len(plugin.enabled_components) == 5


# =============================================================================
# Tests: Plugin Protocol
# =============================================================================


class TestNexusAuthPluginProtocol:
    """Test NexusPlugin protocol compliance."""

    def test_has_name_property(self):
        """Plugin has name property."""
        plugin = NexusAuthPlugin()
        assert isinstance(plugin.name, str)
        assert len(plugin.name) > 0

    def test_has_description_property(self):
        """Plugin has description property."""
        plugin = NexusAuthPlugin()
        assert isinstance(plugin.description, str)

    def test_has_apply_method(self):
        """Plugin has apply method."""
        plugin = NexusAuthPlugin()
        assert callable(plugin.apply)

    def test_has_install_method(self):
        """Plugin has install method (NexusPluginProtocol)."""
        plugin = NexusAuthPlugin()
        assert callable(plugin.install)

    def test_validates_successfully(self):
        """Plugin passes validation."""
        plugin = NexusAuthPlugin()
        assert plugin.validate() is True

    def test_is_nexus_plugin(self):
        """Plugin is instance of NexusPlugin."""
        from nexus.plugins import NexusPlugin

        plugin = NexusAuthPlugin()
        assert isinstance(plugin, NexusPlugin)


# =============================================================================
# Tests: Middleware Installation
# =============================================================================


class TestNexusAuthPluginInstallation:
    """Integration tests for middleware installation (NO MOCKING)."""

    def test_install_audit_only(self, caplog):
        """Install with audit only logs to nexus.audit."""
        app = FastAPI()

        plugin = NexusAuthPlugin(
            audit=AuditConfig(
                backend="logging",
                exclude_paths=["/health"],
            ),
        )
        plugin.install(app)

        @app.get("/api/test")
        async def test_endpoint():
            return {"ok": True}

        @app.get("/health")
        async def health():
            return {"status": "healthy"}

        client = TestClient(app)

        with caplog.at_level(logging.INFO, logger="nexus.audit"):
            response = client.get("/api/test")

        assert response.status_code == 200

        audit_logs = [r for r in caplog.records if r.name == "nexus.audit"]
        assert len(audit_logs) == 1

    def test_install_rate_limit_only(self):
        """Install with rate limit only enforces limits."""
        app = FastAPI()

        plugin = NexusAuthPlugin(
            rate_limit=RateLimitConfig(
                requests_per_minute=2,
                burst_size=0,
            ),
        )
        plugin.install(app)

        @app.get("/api/test")
        async def test_endpoint():
            return {"ok": True}

        client = TestClient(app)

        # First 2 requests should succeed
        r1 = client.get("/api/test")
        r2 = client.get("/api/test")
        assert r1.status_code == 200
        assert r2.status_code == 200

        # Third request should be rate limited
        r3 = client.get("/api/test")
        assert r3.status_code == 429

    def test_install_jwt_with_audit(self, caplog):
        """Install with JWT + audit. Unauthenticated request is audited."""
        app = FastAPI()

        plugin = NexusAuthPlugin(
            jwt=JWTConfig(
                secret="test-secret-key-for-plugin-integration",
                exempt_paths=["/health"],
            ),
            audit=AuditConfig(
                backend="logging",
                exclude_paths=["/health"],
            ),
        )
        plugin.install(app)

        @app.get("/api/protected")
        async def protected():
            return {"ok": True}

        @app.get("/health")
        async def health():
            return {"status": "healthy"}

        client = TestClient(app)

        with caplog.at_level(logging.WARNING, logger="nexus.audit"):
            # No JWT token - should get 401
            response = client.get("/api/protected")

        assert response.status_code == 401

        # Audit should have logged the 401
        audit_logs = [r for r in caplog.records if r.name == "nexus.audit"]
        assert len(audit_logs) >= 1

    def test_apply_delegates_to_install(self, caplog):
        """apply() delegates to install()."""
        app = FastAPI()

        plugin = NexusAuthPlugin(
            audit=AuditConfig(
                backend="logging",
                exclude_paths=["/health"],
            ),
        )
        plugin.apply(app)

        @app.get("/api/test")
        async def test_endpoint():
            return {"ok": True}

        client = TestClient(app)

        with caplog.at_level(logging.INFO, logger="nexus.audit"):
            response = client.get("/api/test")

        assert response.status_code == 200
        audit_logs = [r for r in caplog.records if r.name == "nexus.audit"]
        assert len(audit_logs) == 1


# =============================================================================
# Tests: Export from auth package
# =============================================================================


class TestNexusAuthPluginExport:
    """Test exports."""

    def test_from_auth_package(self):
        """NexusAuthPlugin accessible from nexus.auth."""
        from nexus.auth import NexusAuthPlugin as NAP

        assert NAP is NexusAuthPlugin

    def test_from_plugin_module(self):
        """NexusAuthPlugin accessible from plugin module."""
        from nexus.auth.plugin import NexusAuthPlugin as NAP

        assert NAP is NexusAuthPlugin
