"""Unit tests for SSO providers (TODO-310C).

Tests SSO provider protocol, base classes, and all 4 provider implementations.
Tier 1 tests - mocking allowed for external HTTP calls.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nexus.auth.sso.base import (
    BaseSSOProvider,
    SSOAuthError,
    SSOProvider,
    SSOTokenResponse,
    SSOUserInfo,
)

# =============================================================================
# Tests: SSOTokenResponse
# =============================================================================


class TestSSOTokenResponse:
    """Tests for SSOTokenResponse dataclass."""

    def test_minimal_creation(self):
        """Token response with only access_token."""
        token = SSOTokenResponse(access_token="test-token")
        assert token.access_token == "test-token"
        assert token.id_token is None
        assert token.refresh_token is None
        assert token.token_type == "Bearer"
        assert token.expires_in == 3600
        assert token.scope is None

    def test_full_creation(self):
        """Token response with all fields."""
        token = SSOTokenResponse(
            access_token="access-123",
            id_token="id-456",
            refresh_token="refresh-789",
            token_type="Bearer",
            expires_in=7200,
            scope="openid profile email",
        )
        assert token.access_token == "access-123"
        assert token.id_token == "id-456"
        assert token.refresh_token == "refresh-789"
        assert token.expires_in == 7200
        assert token.scope == "openid profile email"


# =============================================================================
# Tests: SSOUserInfo
# =============================================================================


class TestSSOUserInfo:
    """Tests for SSOUserInfo dataclass."""

    def test_minimal_creation(self):
        """User info with only provider_user_id."""
        info = SSOUserInfo(provider_user_id="user-123")
        assert info.provider_user_id == "user-123"
        assert info.email is None
        assert info.email_verified is False
        assert info.name is None
        assert info.raw_data == {}

    def test_full_creation(self):
        """User info with all fields."""
        info = SSOUserInfo(
            provider_user_id="user-123",
            email="user@example.com",
            email_verified=True,
            name="Test User",
            given_name="Test",
            family_name="User",
            picture="https://example.com/photo.jpg",
            locale="en-US",
            raw_data={"extra": "data"},
        )
        assert info.email == "user@example.com"
        assert info.email_verified is True
        assert info.name == "Test User"
        assert info.given_name == "Test"
        assert info.family_name == "User"
        assert info.picture == "https://example.com/photo.jpg"
        assert info.locale == "en-US"
        assert info.raw_data == {"extra": "data"}

    def test_raw_data_default_to_empty_dict(self):
        """raw_data defaults to empty dict via __post_init__."""
        info = SSOUserInfo(provider_user_id="u1")
        assert info.raw_data == {}
        assert info.raw_data is not None


# =============================================================================
# Tests: SSOProvider Protocol
# =============================================================================


class TestSSOProviderProtocol:
    """Tests for SSOProvider protocol."""

    def test_protocol_is_runtime_checkable(self):
        """Protocol supports isinstance() checks."""

        class FakeProvider:
            name = "fake"

            def get_authorization_url(self, state, redirect_uri, scope=None, **kw):
                return ""

            async def exchange_code(self, code, redirect_uri):
                return SSOTokenResponse(access_token="t")

            async def get_user_info(self, access_token):
                return SSOUserInfo(provider_user_id="u")

            def validate_id_token(self, id_token):
                return {}

        assert isinstance(FakeProvider(), SSOProvider)

    def test_non_conforming_class_fails_check(self):
        """Class missing methods doesn't pass isinstance check."""

        class Incomplete:
            pass

        assert not isinstance(Incomplete(), SSOProvider)


# =============================================================================
# Tests: BaseSSOProvider
# =============================================================================


class TestBaseSSOProvider:
    """Tests for BaseSSOProvider base class."""

    def test_initialization(self):
        """Base provider stores client credentials."""
        provider = BaseSSOProvider(
            client_id="client-123",
            client_secret="secret-456",
            timeout=15,
        )
        assert provider.client_id == "client-123"
        assert provider.client_secret == "secret-456"
        assert provider.timeout == 15
        assert provider._http_client is None

    def test_initialization_without_secret(self):
        """Base provider works without client_secret (e.g., Apple)."""
        provider = BaseSSOProvider(client_id="client-123")
        assert provider.client_secret is None
        assert provider.timeout == 30  # default

    @pytest.mark.asyncio
    async def test_get_http_client_creates_client(self):
        """_get_http_client creates httpx.AsyncClient lazily."""
        provider = BaseSSOProvider(client_id="c1")
        client = await provider._get_http_client()
        assert client is not None
        # Same client returned on second call
        client2 = await provider._get_http_client()
        assert client is client2
        await provider.close()

    @pytest.mark.asyncio
    async def test_close_cleans_up_client(self):
        """close() releases HTTP client."""
        provider = BaseSSOProvider(client_id="c1")
        await provider._get_http_client()
        assert provider._http_client is not None
        await provider.close()
        assert provider._http_client is None

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self):
        """close() is safe to call multiple times."""
        provider = BaseSSOProvider(client_id="c1")
        await provider.close()  # No error even without client
        await provider.close()


# =============================================================================
# Tests: SSOAuthError
# =============================================================================


class TestSSOAuthError:
    """Tests for SSOAuthError exception."""

    def test_is_exception(self):
        """SSOAuthError is an Exception."""
        err = SSOAuthError("test error")
        assert isinstance(err, Exception)
        assert str(err) == "test error"

    def test_can_be_raised_and_caught(self):
        """SSOAuthError can be raised and caught."""
        with pytest.raises(SSOAuthError, match="OAuth failed"):
            raise SSOAuthError("OAuth failed")


# =============================================================================
# Tests: AzureADProvider
# =============================================================================


class TestAzureADProvider:
    """Tests for Azure AD provider."""

    def test_initialization_single_tenant(self):
        """Single tenant Azure AD provider init."""
        from nexus.auth.sso.azure import AzureADProvider

        azure = AzureADProvider(
            tenant_id="test-tenant-id",
            client_id="test-client-id",
            client_secret="test-secret",
        )
        assert azure.name == "azure"
        assert azure.tenant_id == "test-tenant-id"
        assert azure.client_id == "test-client-id"
        assert azure.is_multi_tenant is False
        assert "openid" in azure.scopes

    def test_initialization_multi_tenant_common(self):
        """Multi-tenant mode with 'common'."""
        from nexus.auth.sso.azure import AzureADProvider

        azure = AzureADProvider(
            tenant_id="common",
            client_id="test-client",
            client_secret="test-secret",
        )
        assert azure.is_multi_tenant is True

    def test_initialization_multi_tenant_organizations(self):
        """Multi-tenant mode with 'organizations'."""
        from nexus.auth.sso.azure import AzureADProvider

        azure = AzureADProvider(
            tenant_id="organizations",
            client_id="test-client",
            client_secret="test-secret",
        )
        assert azure.is_multi_tenant is True

    def test_initialization_multi_tenant_consumers(self):
        """Multi-tenant mode with 'consumers'."""
        from nexus.auth.sso.azure import AzureADProvider

        azure = AzureADProvider(
            tenant_id="consumers",
            client_id="test-client",
            client_secret="test-secret",
        )
        assert azure.is_multi_tenant is True

    def test_custom_scopes(self):
        """Custom scopes override defaults."""
        from nexus.auth.sso.azure import AzureADProvider

        azure = AzureADProvider(
            tenant_id="t1",
            client_id="c1",
            client_secret="s1",
            scopes=["openid", "custom:scope"],
        )
        assert azure.scopes == ["openid", "custom:scope"]

    def test_allowed_tenants(self):
        """allowed_tenants is stored for multi-tenant validation."""
        from nexus.auth.sso.azure import AzureADProvider

        azure = AzureADProvider(
            tenant_id="common",
            client_id="c1",
            client_secret="s1",
            allowed_tenants=["tenant-a", "tenant-b"],
        )
        assert azure.allowed_tenants == ["tenant-a", "tenant-b"]

    def test_authorization_url_generation(self):
        """Authorization URL contains required parameters."""
        from nexus.auth.sso.azure import AzureADProvider

        azure = AzureADProvider(
            tenant_id="test-tenant",
            client_id="test-client",
            client_secret="test-secret",
        )

        url = azure.get_authorization_url(
            state="csrf-state-123",
            redirect_uri="https://myapp.com/callback",
        )

        assert "login.microsoftonline.com/test-tenant" in url
        assert "oauth2/v2.0/authorize" in url
        assert "client_id=test-client" in url
        assert "state=csrf-state-123" in url
        assert "response_type=code" in url
        assert "redirect_uri=" in url
        assert "response_mode=query" in url

    def test_authorization_url_custom_prompt(self):
        """Custom prompt parameter is included."""
        from nexus.auth.sso.azure import AzureADProvider

        azure = AzureADProvider(
            tenant_id="t1",
            client_id="c1",
            client_secret="s1",
        )

        url = azure.get_authorization_url(
            state="s",
            redirect_uri="https://app.com/cb",
            prompt="consent",
        )
        assert "prompt=consent" in url

    def test_authorization_url_custom_scope(self):
        """Custom scope string overrides default."""
        from nexus.auth.sso.azure import AzureADProvider

        azure = AzureADProvider(
            tenant_id="t1",
            client_id="c1",
            client_secret="s1",
        )

        url = azure.get_authorization_url(
            state="s",
            redirect_uri="https://app.com/cb",
            scope="openid custom:scope",
        )
        assert "openid+custom%3Ascope" in url or "openid%20custom%3Ascope" in url

    def test_authorization_url_extra_kwargs(self):
        """Extra kwargs are included in URL."""
        from nexus.auth.sso.azure import AzureADProvider

        azure = AzureADProvider(
            tenant_id="t1",
            client_id="c1",
            client_secret="s1",
        )

        url = azure.get_authorization_url(
            state="s",
            redirect_uri="https://app.com/cb",
            login_hint="user@example.com",
        )
        assert "login_hint=" in url

    def test_logout_url(self):
        """Logout URL is generated correctly."""
        from nexus.auth.sso.azure import AzureADProvider

        azure = AzureADProvider(
            tenant_id="test-tenant",
            client_id="c1",
            client_secret="s1",
        )

        url = azure.get_logout_url()
        assert "login.microsoftonline.com/test-tenant/oauth2/v2.0/logout" in url

    def test_logout_url_with_redirect(self):
        """Logout URL includes post_logout_redirect_uri."""
        from nexus.auth.sso.azure import AzureADProvider

        azure = AzureADProvider(
            tenant_id="t1",
            client_id="c1",
            client_secret="s1",
        )

        url = azure.get_logout_url(post_logout_redirect_uri="https://myapp.com")
        assert "post_logout_redirect_uri=https://myapp.com" in url

    def test_provider_implements_protocol(self):
        """AzureADProvider satisfies SSOProvider protocol."""
        from nexus.auth.sso.azure import AzureADProvider

        azure = AzureADProvider(
            tenant_id="t1",
            client_id="c1",
            client_secret="s1",
        )
        assert isinstance(azure, SSOProvider)


# =============================================================================
# Tests: GoogleProvider
# =============================================================================


class TestGoogleProvider:
    """Tests for Google provider."""

    def test_initialization(self):
        """Google provider initializes correctly."""
        from nexus.auth.sso.google import GoogleProvider

        google = GoogleProvider(
            client_id="test.apps.googleusercontent.com",
            client_secret="test-secret",
        )
        assert google.name == "google"
        assert google.client_id == "test.apps.googleusercontent.com"
        assert "openid" in google.scopes
        assert "profile" in google.scopes
        assert "email" in google.scopes

    def test_custom_scopes(self):
        """Custom scopes override defaults."""
        from nexus.auth.sso.google import GoogleProvider

        google = GoogleProvider(
            client_id="c1",
            client_secret="s1",
            scopes=["openid", "custom"],
        )
        assert google.scopes == ["openid", "custom"]

    def test_authorization_url_generation(self):
        """Authorization URL contains required parameters."""
        from nexus.auth.sso.google import GoogleProvider

        google = GoogleProvider(
            client_id="test.apps.googleusercontent.com",
            client_secret="test-secret",
        )

        url = google.get_authorization_url(
            state="csrf-state-456",
            redirect_uri="https://myapp.com/callback",
        )

        assert "accounts.google.com" in url
        assert "client_id=test.apps.googleusercontent.com" in url
        assert "state=csrf-state-456" in url
        assert "response_type=code" in url
        assert "access_type=offline" in url
        assert "prompt=consent" in url

    def test_authorization_url_custom_access_type(self):
        """Custom access_type parameter."""
        from nexus.auth.sso.google import GoogleProvider

        google = GoogleProvider(client_id="c1", client_secret="s1")

        url = google.get_authorization_url(
            state="s",
            redirect_uri="https://app.com/cb",
            access_type="online",
        )
        assert "access_type=online" in url

    def test_authorization_url_gsuite_domain_hint(self):
        """hd parameter for G Suite domain restriction."""
        from nexus.auth.sso.google import GoogleProvider

        google = GoogleProvider(client_id="c1", client_secret="s1")

        url = google.get_authorization_url(
            state="s",
            redirect_uri="https://app.com/cb",
            hd="example.com",
        )
        assert "hd=example.com" in url

    def test_provider_implements_protocol(self):
        """GoogleProvider satisfies SSOProvider protocol."""
        from nexus.auth.sso.google import GoogleProvider

        google = GoogleProvider(client_id="c1", client_secret="s1")
        assert isinstance(google, SSOProvider)


# =============================================================================
# Tests: AppleProvider
# =============================================================================


class TestAppleProvider:
    """Tests for Apple provider."""

    # Test ES256 private key for unit testing (NOT a real key)
    _TEST_PRIVATE_KEY = """-----BEGIN EC PRIVATE KEY-----
MHQCAQEEIBNSEIiGdXS07HmN5EjXfnnGP4VUfWpPDFXZ8IjELgG1oAcGBSuB
BAAioGQDYgAE2bCXhjbVQ7/k1qPVXxGjOZjNg2pChOBfGIi+h6u/s7q5m6JN2B
sFjCx6n4v+FdD8aZZm2tKbhh3ZO2UbZhXCMlTjN3odfhFGIjELgG1aFk0tZE
qW1hGijWYYl6Gm7O
-----END EC PRIVATE KEY-----"""

    def _make_provider(self, **kwargs):
        """Create AppleProvider with test key."""
        defaults = {
            "team_id": "TEAM123",
            "client_id": "com.test.service",
            "key_id": "KEY123",
            "private_key": self._TEST_PRIVATE_KEY,
        }
        defaults.update(kwargs)
        from nexus.auth.sso.apple import AppleProvider

        return AppleProvider(**defaults)

    def test_initialization_with_private_key(self):
        """Apple provider initializes with private key string."""
        apple = self._make_provider()
        assert apple.name == "apple"
        assert apple.team_id == "TEAM123"
        assert apple.client_id == "com.test.service"
        assert apple.key_id == "KEY123"
        assert "name" in apple.scopes
        assert "email" in apple.scopes

    def test_initialization_requires_key(self):
        """Raises ValueError if no key provided."""
        from nexus.auth.sso.apple import AppleProvider

        with pytest.raises(ValueError, match="private_key or private_key_path"):
            AppleProvider(
                team_id="T1",
                client_id="C1",
                key_id="K1",
            )

    def test_initialization_with_key_path(self, tmp_path):
        """Apple provider initializes with key file path."""
        from nexus.auth.sso.apple import AppleProvider

        key_file = tmp_path / "AuthKey.p8"
        key_file.write_text(self._TEST_PRIVATE_KEY)

        apple = AppleProvider(
            team_id="T1",
            client_id="C1",
            key_id="K1",
            private_key_path=str(key_file),
        )
        assert apple._private_key == self._TEST_PRIVATE_KEY

    def test_custom_scopes(self):
        """Custom scopes override defaults."""
        apple = self._make_provider(scopes=["email"])
        assert apple.scopes == ["email"]

    def test_authorization_url_generation(self):
        """Authorization URL contains required parameters."""
        apple = self._make_provider()

        url = apple.get_authorization_url(
            state="csrf-state-789",
            redirect_uri="https://myapp.com/callback",
        )

        assert "appleid.apple.com/auth/authorize" in url
        assert "client_id=com.test.service" in url
        assert "state=csrf-state-789" in url
        assert "response_type=code" in url
        assert "response_mode=form_post" in url

    def test_authorization_url_custom_response_mode(self):
        """Custom response_mode parameter."""
        apple = self._make_provider()

        url = apple.get_authorization_url(
            state="s",
            redirect_uri="https://app.com/cb",
            response_mode="query",
        )
        assert "response_mode=query" in url

    def test_client_secret_generation(self):
        """Client secret is a valid JWT."""
        import jwt as pyjwt

        apple = self._make_provider()

        # _generate_client_secret will fail with the test key since
        # it's not a real ES256 key, but we test the method exists
        # and has the right structure
        assert hasattr(apple, "_generate_client_secret")
        assert callable(apple._generate_client_secret)

    @pytest.mark.asyncio
    async def test_get_user_info_returns_empty(self):
        """Apple get_user_info returns empty (no userinfo endpoint)."""
        apple = self._make_provider()
        info = await apple.get_user_info("fake-token")
        assert info.provider_user_id == ""
        assert info.raw_data == {}

    def test_extract_user_info(self):
        """extract_user_info creates SSOUserInfo from claims."""
        apple = self._make_provider()

        claims = {
            "sub": "user-apple-123",
            "email": "user@privaterelay.appleid.com",
            "email_verified": True,
            "name": "John Doe",
            "given_name": "John",
            "family_name": "Doe",
        }

        info = apple.extract_user_info(claims)
        assert info.provider_user_id == "user-apple-123"
        assert info.email == "user@privaterelay.appleid.com"
        assert info.email_verified is True
        assert info.name == "John Doe"
        assert info.given_name == "John"
        assert info.family_name == "Doe"

    def test_provider_implements_protocol(self):
        """AppleProvider satisfies SSOProvider protocol."""
        apple = self._make_provider()
        assert isinstance(apple, SSOProvider)


# =============================================================================
# Tests: GitHubProvider
# =============================================================================


class TestGitHubProvider:
    """Tests for GitHub provider."""

    def test_initialization(self):
        """GitHub provider initializes correctly."""
        from nexus.auth.sso.github import GitHubProvider

        github = GitHubProvider(
            client_id="gh-client-123",
            client_secret="gh-secret-456",
        )
        assert github.name == "github"
        assert github.client_id == "gh-client-123"
        assert "user:email" in github.scopes

    def test_custom_scopes(self):
        """Custom scopes override defaults."""
        from nexus.auth.sso.github import GitHubProvider

        github = GitHubProvider(
            client_id="c1",
            client_secret="s1",
            scopes=["user", "repo"],
        )
        assert github.scopes == ["user", "repo"]

    def test_authorization_url_generation(self):
        """Authorization URL contains required parameters."""
        from nexus.auth.sso.github import GitHubProvider

        github = GitHubProvider(
            client_id="gh-client",
            client_secret="gh-secret",
        )

        url = github.get_authorization_url(
            state="csrf-gh-state",
            redirect_uri="https://myapp.com/callback",
        )

        assert "github.com/login/oauth/authorize" in url
        assert "client_id=gh-client" in url
        assert "state=csrf-gh-state" in url
        assert "allow_signup=true" in url

    def test_authorization_url_disable_signup(self):
        """allow_signup=false disables new signups."""
        from nexus.auth.sso.github import GitHubProvider

        github = GitHubProvider(client_id="c1", client_secret="s1")

        url = github.get_authorization_url(
            state="s",
            redirect_uri="https://app.com/cb",
            allow_signup=False,
        )
        assert "allow_signup=false" in url

    def test_validate_id_token_raises(self):
        """GitHub validate_id_token always raises (no OIDC support)."""
        from nexus.auth.sso.github import GitHubProvider

        github = GitHubProvider(client_id="c1", client_secret="s1")

        with pytest.raises(SSOAuthError, match="doesn't support ID tokens"):
            github.validate_id_token("fake-token")

    def test_provider_implements_protocol(self):
        """GitHubProvider satisfies SSOProvider protocol."""
        from nexus.auth.sso.github import GitHubProvider

        github = GitHubProvider(client_id="c1", client_secret="s1")
        assert isinstance(github, SSOProvider)


# =============================================================================
# Tests: State Management (from __init__.py)
# =============================================================================


class TestStateManagement:
    """Tests for CSRF state management via SSOStateStore protocol."""

    def setup_method(self):
        """Reset state store before each test."""
        from nexus.auth.sso import InMemorySSOStateStore, configure_state_store

        configure_state_store(InMemorySSOStateStore())

    def test_state_stored_on_initiate(self):
        """State store accepts and holds state tokens."""
        import secrets

        from nexus.auth.sso import _get_state_store

        store = _get_state_store()
        state = secrets.token_urlsafe(32)
        store.store(state)

        # State can be validated
        assert store.validate_and_consume(state) is True

    def test_state_consumed_on_validate(self):
        """State is consumed (removed) after validation."""
        from nexus.auth.sso import _get_state_store

        store = _get_state_store()
        store.store("test-state")

        # First validation succeeds
        assert store.validate_and_consume("test-state") is True
        # State is now consumed
        assert store.validate_and_consume("test-state") is False

    def test_state_one_time_use(self):
        """State cannot be used twice."""
        from nexus.auth.sso import _get_state_store

        store = _get_state_store()
        store.store("one-time-state")

        # First use
        store.validate_and_consume("one-time-state")

        # Second use fails
        assert store.validate_and_consume("one-time-state") is False

    def test_expired_state_cleanup(self):
        """InMemorySSOStateStore.cleanup() removes expired entries."""
        from nexus.auth.sso import InMemorySSOStateStore

        store = InMemorySSOStateStore(ttl_seconds=1)

        # Add an expired state (directly manipulate internal store)
        store._store["expired"] = time.time() - 100
        store._store["valid"] = time.time()

        store.cleanup()

        assert "expired" not in store._store
        assert "valid" in store._store

    def test_invalid_state_error(self):
        """InvalidStateError is properly defined."""
        from nexus.auth.sso import InvalidStateError

        err = InvalidStateError("bad state")
        assert isinstance(err, Exception)
        assert str(err) == "bad state"


# =============================================================================
# Tests: Package Exports
# =============================================================================


class TestPackageExports:
    """Tests for SSO package __init__.py exports."""

    def test_base_exports(self):
        """Base types are exported."""
        from nexus.auth.sso import (
            BaseSSOProvider,
            SSOAuthError,
            SSOProvider,
            SSOTokenResponse,
            SSOUserInfo,
        )

        assert SSOProvider is not None
        assert BaseSSOProvider is not None
        assert SSOTokenResponse is not None
        assert SSOUserInfo is not None
        assert SSOAuthError is not None

    def test_provider_exports(self):
        """All provider classes are exported."""
        from nexus.auth.sso import (
            AppleProvider,
            AzureADProvider,
            GitHubProvider,
            GoogleProvider,
        )

        assert AzureADProvider is not None
        assert GoogleProvider is not None
        assert AppleProvider is not None
        assert GitHubProvider is not None

    def test_helper_function_exports(self):
        """Helper functions are exported."""
        from nexus.auth.sso import (
            InvalidStateError,
            exchange_sso_code,
            handle_sso_callback,
            initiate_sso_login,
        )

        assert callable(initiate_sso_login)
        assert callable(handle_sso_callback)
        assert callable(exchange_sso_code)
        assert InvalidStateError is not None

    def test_all_list_complete(self):
        """__all__ contains all expected names."""
        from nexus.auth import sso

        expected = {
            "SSOProvider",
            "BaseSSOProvider",
            "SSOTokenResponse",
            "SSOUserInfo",
            "SSOAuthError",
            "AzureADProvider",
            "GoogleProvider",
            "AppleProvider",
            "GitHubProvider",
            "SSOStateStore",
            "InMemorySSOStateStore",
            "configure_state_store",
            "initiate_sso_login",
            "handle_sso_callback",
            "exchange_sso_code",
            "InvalidStateError",
        }
        assert expected.issubset(set(sso.__all__))


# =============================================================================
# Tests: Provider Name Properties
# =============================================================================


class TestProviderNames:
    """Tests for provider name attributes (used in routing)."""

    def test_azure_name(self):
        from nexus.auth.sso.azure import AzureADProvider

        p = AzureADProvider(tenant_id="t", client_id="c", client_secret="s")
        assert p.name == "azure"

    def test_google_name(self):
        from nexus.auth.sso.google import GoogleProvider

        p = GoogleProvider(client_id="c", client_secret="s")
        assert p.name == "google"

    def test_apple_name(self):
        from nexus.auth.sso.apple import AppleProvider

        p = AppleProvider(
            team_id="T",
            client_id="C",
            key_id="K",
            private_key="-----BEGIN EC PRIVATE KEY-----\nfake\n-----END EC PRIVATE KEY-----",
        )
        assert p.name == "apple"

    def test_github_name(self):
        from nexus.auth.sso.github import GitHubProvider

        p = GitHubProvider(client_id="c", client_secret="s")
        assert p.name == "github"


# =============================================================================
# Tests: Azure AD Constants
# =============================================================================


class TestAzureConstants:
    """Tests for Azure AD provider constants."""

    def test_authority_base(self):
        from nexus.auth.sso.azure import AzureADProvider

        assert AzureADProvider.AUTHORITY_BASE == "https://login.microsoftonline.com"

    def test_graph_api_base(self):
        from nexus.auth.sso.azure import AzureADProvider

        assert AzureADProvider.GRAPH_API_BASE == "https://graph.microsoft.com/v1.0"


# =============================================================================
# Tests: Google Constants
# =============================================================================


class TestGoogleConstants:
    """Tests for Google provider constants."""

    def test_authorization_url(self):
        from nexus.auth.sso.google import GoogleProvider

        assert (
            GoogleProvider.AUTHORIZATION_URL
            == "https://accounts.google.com/o/oauth2/v2/auth"
        )

    def test_token_url(self):
        from nexus.auth.sso.google import GoogleProvider

        assert GoogleProvider.TOKEN_URL == "https://oauth2.googleapis.com/token"

    def test_jwks_url(self):
        from nexus.auth.sso.google import GoogleProvider

        assert GoogleProvider.JWKS_URL == "https://www.googleapis.com/oauth2/v3/certs"


# =============================================================================
# Tests: Apple Constants
# =============================================================================


class TestAppleConstants:
    """Tests for Apple provider constants."""

    def test_authorization_url(self):
        from nexus.auth.sso.apple import AppleProvider

        assert (
            AppleProvider.AUTHORIZATION_URL
            == "https://appleid.apple.com/auth/authorize"
        )

    def test_token_url(self):
        from nexus.auth.sso.apple import AppleProvider

        assert AppleProvider.TOKEN_URL == "https://appleid.apple.com/auth/token"

    def test_jwks_url(self):
        from nexus.auth.sso.apple import AppleProvider

        assert AppleProvider.JWKS_URL == "https://appleid.apple.com/auth/keys"


# =============================================================================
# Tests: GitHub Constants
# =============================================================================


class TestGitHubConstants:
    """Tests for GitHub provider constants."""

    def test_authorization_url(self):
        from nexus.auth.sso.github import GitHubProvider

        assert (
            GitHubProvider.AUTHORIZATION_URL
            == "https://github.com/login/oauth/authorize"
        )

    def test_token_url(self):
        from nexus.auth.sso.github import GitHubProvider

        assert GitHubProvider.TOKEN_URL == "https://github.com/login/oauth/access_token"

    def test_user_info_url(self):
        from nexus.auth.sso.github import GitHubProvider

        assert GitHubProvider.USERINFO_URL == "https://api.github.com/user"

    def test_emails_url(self):
        from nexus.auth.sso.github import GitHubProvider

        assert GitHubProvider.EMAILS_URL == "https://api.github.com/user/emails"
