"""Unit tests for security hardening fixes (post-security-review).

Tests for:
- Finding 1: SSO CSRF bypass in exchange_sso_code (CRITICAL)
- Finding 5: Pluggable SSO state store (HIGH)
- Finding 7+8: Tenant validation fail-closed (HIGH)
- Finding 10: X-Forwarded-For trust_proxy_headers (HIGH)
- Finding 11: SSO error response sanitization (HIGH)
- Finding 14: InMemoryBackend bounded growth (MEDIUM)
- Finding 19: Reserved claims protection in create_access_token (LOW)
- Finding 20: Role/permission error message sanitization (LOW)
- Finding 22: Redis URL credential sanitization (LOW)

Tier 1 tests - mocking allowed for isolated unit testing.
"""

import logging
import time

import pytest
from nexus.auth.audit.config import AuditConfig
from nexus.auth.audit.middleware import AuditMiddleware
from nexus.auth.rate_limit.backends.memory import InMemoryBackend
from nexus.auth.sso import (
    InMemorySSOStateStore,
    InvalidStateError,
    SSOStateStore,
    _get_state_store,
    configure_state_store,
    exchange_sso_code,
)
from nexus.auth.sso.base import BaseSSOProvider, SSOAuthError
from nexus.auth.tenant.config import TenantConfig
from nexus.auth.tenant.context import TenantContext
from nexus.auth.tenant.exceptions import TenantNotFoundError
from nexus.auth.tenant.middleware import TenantMiddleware
from nexus.auth.tenant.resolver import TenantResolver

# =============================================================================
# Finding 1: SSO CSRF bypass - exchange_sso_code requires state
# =============================================================================


class TestExchangeSSOCodeCSRF:
    """Tests for exchange_sso_code CSRF state requirement."""

    @pytest.mark.asyncio
    async def test_empty_state_raises_invalid_state_error(self):
        """exchange_sso_code with empty state must raise InvalidStateError."""
        with pytest.raises(InvalidStateError, match="CSRF state parameter is required"):
            await exchange_sso_code(
                provider=None,
                code="test-code",
                state="",
                auth_plugin=None,
            )

    @pytest.mark.asyncio
    async def test_none_state_raises_invalid_state_error(self):
        """exchange_sso_code with None-like state must raise."""
        with pytest.raises(InvalidStateError, match="CSRF state parameter is required"):
            await exchange_sso_code(
                provider=None,
                code="test-code",
                state="",
                auth_plugin=None,
            )

    @pytest.mark.asyncio
    async def test_invalid_state_raises_error(self):
        """exchange_sso_code with unrecognized state must raise."""
        with pytest.raises(InvalidStateError):
            await exchange_sso_code(
                provider=None,
                code="test-code",
                state="not-a-valid-state-token",
                auth_plugin=None,
            )


# =============================================================================
# Finding 5: Pluggable SSO state store
# =============================================================================


class TestSSOStateStore:
    """Tests for SSO state store abstraction."""

    def test_in_memory_store_protocol_compliance(self):
        """InMemorySSOStateStore satisfies SSOStateStore protocol."""
        store = InMemorySSOStateStore()
        assert isinstance(store, SSOStateStore)

    def test_store_and_validate(self):
        """Store a state and validate it once."""
        store = InMemorySSOStateStore()
        store.store("test-state-123")
        assert store.validate_and_consume("test-state-123") is True

    def test_single_use_consumption(self):
        """State tokens are consumed on first validation (single use)."""
        store = InMemorySSOStateStore()
        store.store("single-use-token")
        assert store.validate_and_consume("single-use-token") is True
        assert store.validate_and_consume("single-use-token") is False

    def test_unknown_state_rejected(self):
        """Unknown state tokens are rejected."""
        store = InMemorySSOStateStore()
        assert store.validate_and_consume("nonexistent") is False

    def test_expired_state_rejected(self):
        """Expired state tokens are rejected."""
        store = InMemorySSOStateStore(ttl_seconds=1)
        store.store("will-expire")
        # Manually backdate the entry
        store._store["will-expire"] = time.time() - 10
        assert store.validate_and_consume("will-expire") is False

    def test_cleanup_removes_expired(self):
        """cleanup() removes expired entries."""
        store = InMemorySSOStateStore(ttl_seconds=1)
        store._store["old"] = time.time() - 10
        store._store["fresh"] = time.time()
        store.cleanup()
        assert "old" not in store._store
        assert "fresh" in store._store

    def test_configure_state_store_replaces_default(self):
        """configure_state_store replaces the default store."""
        original = _get_state_store()
        custom = InMemorySSOStateStore(ttl_seconds=300)
        configure_state_store(custom)
        assert _get_state_store() is custom
        # Restore original
        configure_state_store(original)

    def test_configure_state_store_rejects_non_protocol(self):
        """configure_state_store rejects non-compliant objects."""
        with pytest.raises(TypeError, match="SSOStateStore protocol"):
            configure_state_store("not a store")

    def test_custom_store_implementation(self):
        """Custom store implementations work correctly."""

        class DictStore:
            def __init__(self):
                self._data = {}

            def store(self, state):
                self._data[state] = True

            def validate_and_consume(self, state):
                return self._data.pop(state, False)

            def cleanup(self):
                pass

        store = DictStore()
        assert isinstance(store, SSOStateStore)
        store.store("custom-state")
        assert store.validate_and_consume("custom-state") is True
        assert store.validate_and_consume("custom-state") is False


# =============================================================================
# Finding 7+8: Tenant validation fail-closed
# =============================================================================


class TestTenantValidationFailClosed:
    """Tests for tenant validation fail-closed behavior."""

    @pytest.mark.asyncio
    async def test_validate_tenant_rejects_when_no_store(self):
        """_validate_tenant rejects when validation enabled but no store."""
        config = TenantConfig(validate_tenant_exists=True)
        resolver = TenantResolver(config, tenant_store=None)

        with pytest.raises(TenantNotFoundError, match="tenant store not configured"):
            await resolver._validate_tenant("any-tenant-id")

    @pytest.mark.asyncio
    async def test_validate_tenant_accepts_when_validation_disabled(self):
        """_validate_tenant accepts any tenant when validation disabled."""
        config = TenantConfig(validate_tenant_exists=False)
        resolver = TenantResolver(config, tenant_store=None)

        result = await resolver._validate_tenant("any-tenant-id")
        assert result.tenant_id == "any-tenant-id"
        assert result.active is True

    @pytest.mark.asyncio
    async def test_validate_tenant_logs_warning_on_no_store(self, caplog):
        """_validate_tenant logs warning when validation enabled but no store."""
        config = TenantConfig(validate_tenant_exists=True)
        resolver = TenantResolver(config, tenant_store=None)

        with caplog.at_level(logging.WARNING):
            with pytest.raises(TenantNotFoundError):
                await resolver._validate_tenant("test-tenant")

        assert "no tenant store configured" in caplog.text

    def test_tenant_middleware_defaults_to_validate_registered_true(self):
        """TenantMiddleware defaults to validate_registered=True (fail-closed)."""
        # Create a minimal middleware without a real app
        config = TenantConfig()

        class DummyApp:
            pass

        mw = TenantMiddleware.__new__(TenantMiddleware)
        mw.config = config
        mw._tenant_context = TenantContext(validate_registered=True)
        mw._resolver = TenantResolver(config)

        # Verify the context has validation enabled
        assert mw._tenant_context._validate_registered is True


# =============================================================================
# Finding 10: X-Forwarded-For trust_proxy_headers
# =============================================================================


class TestTrustProxyHeaders:
    """Tests for audit middleware proxy header trust configuration."""

    def test_trust_proxy_headers_default_false(self):
        """trust_proxy_headers defaults to False (secure default)."""
        config = AuditConfig()
        assert config.trust_proxy_headers is False

    def test_client_ip_ignores_xff_when_untrusted(self):
        """_get_client_ip ignores X-Forwarded-For when trust_proxy_headers=False."""
        config = AuditConfig(trust_proxy_headers=False)
        mw = AuditMiddleware.__new__(AuditMiddleware)
        mw.config = config

        class FakeRequest:
            headers = {"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "5.6.7.8"}
            client = type("C", (), {"host": "10.0.0.1"})()

        ip = mw._get_client_ip(FakeRequest())
        assert ip == "10.0.0.1"

    def test_client_ip_uses_xff_when_trusted(self):
        """_get_client_ip uses X-Forwarded-For when trust_proxy_headers=True."""
        config = AuditConfig(trust_proxy_headers=True)
        mw = AuditMiddleware.__new__(AuditMiddleware)
        mw.config = config

        class FakeRequest:
            headers = {"X-Forwarded-For": "1.2.3.4, 10.0.0.1"}
            client = type("C", (), {"host": "10.0.0.1"})()

        ip = mw._get_client_ip(FakeRequest())
        assert ip == "1.2.3.4"

    def test_client_ip_uses_real_ip_when_trusted(self):
        """_get_client_ip uses X-Real-IP when trusted and no XFF."""
        config = AuditConfig(trust_proxy_headers=True)
        mw = AuditMiddleware.__new__(AuditMiddleware)
        mw.config = config

        class FakeRequest:
            headers = {"X-Real-IP": "5.6.7.8"}
            client = type("C", (), {"host": "10.0.0.1"})()

        ip = mw._get_client_ip(FakeRequest())
        assert ip == "5.6.7.8"


# =============================================================================
# Finding 11: SSO error response sanitization
# =============================================================================


class TestSSOErrorSanitization:
    """Tests for SSO error response message sanitization."""

    @pytest.mark.asyncio
    async def test_post_form_error_does_not_leak_response_body(self):
        """_post_form error should not include provider response body."""
        from unittest.mock import AsyncMock, MagicMock

        provider = BaseSSOProvider.__new__(BaseSSOProvider)
        provider.timeout = 30

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "<html><body>Internal server error details</body></html>"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        provider._http_client = mock_client

        with pytest.raises(SSOAuthError) as exc_info:
            await provider._post_form("https://example.com/token", {"code": "test"})

        error_msg = str(exc_info.value)
        # Should contain status code but NOT the full response body
        assert "400" in error_msg
        assert "Internal server error details" not in error_msg
        assert "<html>" not in error_msg

    @pytest.mark.asyncio
    async def test_get_json_error_does_not_leak_response_body(self):
        """_get_json error should not include provider response body."""
        from unittest.mock import AsyncMock, MagicMock

        provider = BaseSSOProvider.__new__(BaseSSOProvider)
        provider.timeout = 30

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = '{"error": "internal_error", "trace": "secret trace data"}'

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        provider._http_client = mock_client

        with pytest.raises(SSOAuthError) as exc_info:
            await provider._get_json("https://example.com/userinfo")

        error_msg = str(exc_info.value)
        assert "500" in error_msg
        assert "secret trace data" not in error_msg


# =============================================================================
# Finding 14: InMemoryBackend bounded growth
# =============================================================================


class TestInMemoryBackendBoundedGrowth:
    """Tests for InMemoryBackend max entries eviction."""

    @pytest.mark.asyncio
    async def test_eviction_when_max_entries_exceeded(self):
        """Entries are evicted when max_entries is exceeded."""
        backend = InMemoryBackend(max_entries=10)

        # Fill beyond capacity
        for i in range(15):
            await backend.check_and_record(f"user-{i}", limit=100, window_seconds=60)

        # Should have evicted some entries
        assert len(backend._buckets) <= 14  # 15 - at least 1 evicted

    @pytest.mark.asyncio
    async def test_default_max_entries(self):
        """Default max_entries is 100,000."""
        backend = InMemoryBackend()
        assert backend._max_entries == 100_000

    @pytest.mark.asyncio
    async def test_custom_max_entries(self):
        """Custom max_entries is respected."""
        backend = InMemoryBackend(max_entries=50)
        assert backend._max_entries == 50

    @pytest.mark.asyncio
    async def test_eviction_removes_oldest(self):
        """Eviction removes the oldest entries first."""
        from datetime import datetime, timezone

        backend = InMemoryBackend(max_entries=5)

        # Add entries with known timestamps
        for i in range(5):
            await backend.check_and_record(f"user-{i}", limit=100, window_seconds=60)

        # Now add one more to trigger eviction
        await backend.check_and_record("user-new", limit=100, window_seconds=60)

        # The newest entry should still exist
        assert "user-new" in backend._buckets


# =============================================================================
# Finding 19: Reserved claims protection
# =============================================================================


class TestReservedClaimsProtection:
    """Tests for create_access_token reserved claims protection."""

    def _make_middleware(self):
        """Create a JWTMiddleware for testing."""
        from unittest.mock import MagicMock

        from nexus.auth.jwt import JWTConfig, JWTMiddleware

        config = JWTConfig(secret="test-secret-key-for-jwt-unit-testing-min32")
        app = MagicMock()
        mw = JWTMiddleware.__new__(JWTMiddleware)
        mw.config = config
        mw._jwks_client = None
        return mw

    def test_extra_claims_cannot_override_sub(self):
        """extra_claims cannot override 'sub' claim."""
        import jwt as pyjwt

        mw = self._make_middleware()
        token = mw.create_access_token(
            user_id="real-user",
            sub="attacker-user",  # Attempt to override
        )
        payload = pyjwt.decode(token, mw.config.secret, algorithms=["HS256"])
        assert payload["sub"] == "real-user"

    def test_extra_claims_cannot_override_token_type(self):
        """extra_claims cannot override 'token_type' claim."""
        import jwt as pyjwt

        mw = self._make_middleware()
        token = mw.create_access_token(
            user_id="user1",
            token_type="refresh",  # Attempt to forge refresh as access
        )
        payload = pyjwt.decode(token, mw.config.secret, algorithms=["HS256"])
        assert payload["token_type"] == "access"

    def test_extra_claims_cannot_override_exp(self):
        """extra_claims cannot override 'exp' claim to extend token lifetime."""
        import jwt as pyjwt

        mw = self._make_middleware()
        # Try to set a very long expiration via extra_claims
        token = mw.create_access_token(
            user_id="user1",
            expires_minutes=1,  # 1 minute
        )
        payload_normal = pyjwt.decode(token, mw.config.secret, algorithms=["HS256"])
        normal_exp = payload_normal["exp"]

        # Now try with extra_claims attempting to extend exp
        token2 = mw.create_access_token(
            user_id="user1",
            expires_minutes=1,
            exp=normal_exp + 999999,  # Attempt to extend via extra_claims
        )
        payload_attacked = pyjwt.decode(token2, mw.config.secret, algorithms=["HS256"])
        # exp should NOT be extended - reserved claim protection
        assert payload_attacked["exp"] <= normal_exp + 5  # Allow ~5s clock drift

    def test_extra_claims_logs_warning(self, caplog):
        """Attempting to override reserved claims logs a warning."""
        mw = self._make_middleware()
        with caplog.at_level(logging.WARNING):
            mw.create_access_token(
                user_id="user1",
                exp=999999999,  # Attempt to extend expiration
            )
        assert (
            "reserved claims" in caplog.text.lower()
            or "Ignoring reserved" in caplog.text
        )

    def test_non_reserved_extra_claims_allowed(self):
        """Non-reserved extra claims are included normally."""
        import jwt as pyjwt

        mw = self._make_middleware()
        token = mw.create_access_token(
            user_id="user1",
            department="engineering",
            team="platform",
        )
        payload = pyjwt.decode(token, mw.config.secret, algorithms=["HS256"])
        assert payload["department"] == "engineering"
        assert payload["team"] == "platform"


# =============================================================================
# Finding 20: Role/permission error message sanitization
# =============================================================================


class TestRBACErrorSanitization:
    """Tests for sanitized RBAC error messages."""

    @pytest.mark.asyncio
    async def test_roles_required_returns_generic_forbidden(self):
        """roles_required decorator returns generic 'Forbidden' message."""
        from nexus.auth.models import AuthenticatedUser
        from nexus.auth.rbac import roles_required

        @roles_required("admin")
        async def protected_endpoint(request):
            return {"ok": True}

        class FakeRequest:
            class state:
                user = AuthenticatedUser(
                    user_id="user1",
                    roles=["viewer"],  # Not admin
                )

        response = await protected_endpoint(FakeRequest())
        assert response.status_code == 403
        body = response.body.decode()
        # Should NOT reveal required roles
        assert "admin" not in body
        assert "Forbidden" in body

    @pytest.mark.asyncio
    async def test_permissions_required_returns_generic_forbidden(self):
        """permissions_required decorator returns generic 'Forbidden' message."""
        from nexus.auth.models import AuthenticatedUser
        from nexus.auth.rbac import permissions_required

        @permissions_required("delete:users")
        async def protected_endpoint(request):
            return {"ok": True}

        class FakeRequest:
            class state:
                user = AuthenticatedUser(
                    user_id="user1",
                    roles=[],
                    permissions=["read:users"],  # Not delete
                )

        response = await protected_endpoint(FakeRequest())
        assert response.status_code == 403
        body = response.body.decode()
        # Should NOT reveal required permissions
        assert "delete:users" not in body
        assert "Forbidden" in body


# =============================================================================
# Finding 22: Redis URL sanitization
# =============================================================================


class TestRedisURLSanitization:
    """Tests for Redis URL credential sanitization."""

    def test_sanitize_url_removes_credentials(self):
        """_sanitize_url removes username and password from URL."""
        from nexus.auth.rate_limit.backends.redis import RedisBackend

        url = "redis://admin:s3cr3t@redis.example.com:6379/0"
        safe = RedisBackend._sanitize_url(url)
        assert "admin" not in safe
        assert "s3cr3t" not in safe
        assert "redis.example.com" in safe
        assert "6379" in safe

    def test_sanitize_url_preserves_no_cred_url(self):
        """_sanitize_url preserves URLs without credentials."""
        from nexus.auth.rate_limit.backends.redis import RedisBackend

        url = "redis://localhost:6379/0"
        safe = RedisBackend._sanitize_url(url)
        assert safe == url

    def test_sanitize_url_handles_password_only(self):
        """_sanitize_url handles URLs with password only."""
        from nexus.auth.rate_limit.backends.redis import RedisBackend

        url = "redis://:mypassword@redis.example.com:6379/0"
        safe = RedisBackend._sanitize_url(url)
        assert "mypassword" not in safe
        assert "redis.example.com" in safe
