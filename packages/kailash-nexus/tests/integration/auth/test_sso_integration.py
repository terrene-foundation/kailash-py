"""Integration tests for SSO providers (TODO-310C).

Tests SSO flows with real HTTP requests using pytest-httpserver.
Tier 2 tests - NO MOCKING. Uses real HTTP server as mock OAuth provider.
"""

import json
import time

import pytest
from nexus.auth.sso import (
    InMemorySSOStateStore,
    InvalidStateError,
    _get_state_store,
    configure_state_store,
)
from nexus.auth.sso.base import SSOAuthError, SSOTokenResponse, SSOUserInfo
from pytest_httpserver import HTTPServer

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_state_store():
    """Reset SSO state store before each test."""
    configure_state_store(InMemorySSOStateStore())
    yield
    configure_state_store(InMemorySSOStateStore())


# =============================================================================
# Tests: GitHub OAuth Flow with Real HTTP
# =============================================================================


class TestGitHubOAuthFlowIntegration:
    """Integration tests for GitHub OAuth flow with real HTTP."""

    @pytest.mark.asyncio
    async def test_github_token_exchange_success(self, httpserver: HTTPServer):
        """GitHub token exchange with real HTTP server."""
        from nexus.auth.sso.github import GitHubProvider

        # Configure mock GitHub token endpoint
        httpserver.expect_request(
            "/login/oauth/access_token",
            method="POST",
        ).respond_with_json(
            {
                "access_token": "gho_test_access_token_123",
                "token_type": "bearer",
                "scope": "user:email",
            }
        )

        github = GitHubProvider(
            client_id="test-client",
            client_secret="test-secret",
        )
        # Override token URL to point to local server
        github.TOKEN_URL = httpserver.url_for("/login/oauth/access_token")

        tokens = await github.exchange_code(
            code="test-auth-code",
            redirect_uri="https://myapp.com/callback",
        )

        assert tokens.access_token == "gho_test_access_token_123"
        assert tokens.token_type == "bearer"
        assert tokens.id_token is None  # GitHub has no ID tokens
        assert tokens.scope == "user:email"

        await github.close()

    @pytest.mark.asyncio
    async def test_github_token_exchange_error(self, httpserver: HTTPServer):
        """GitHub token exchange handles error responses."""
        from nexus.auth.sso.github import GitHubProvider

        httpserver.expect_request(
            "/login/oauth/access_token",
            method="POST",
        ).respond_with_json(
            {
                "error": "bad_verification_code",
                "error_description": "The code passed is incorrect or expired.",
            }
        )

        github = GitHubProvider(
            client_id="test-client",
            client_secret="test-secret",
        )
        github.TOKEN_URL = httpserver.url_for("/login/oauth/access_token")

        with pytest.raises(SSOAuthError, match="Token exchange failed"):
            await github.exchange_code(
                code="expired-code",
                redirect_uri="https://myapp.com/callback",
            )

        await github.close()

    @pytest.mark.asyncio
    async def test_github_user_info_success(self, httpserver: HTTPServer):
        """GitHub user info fetch with real HTTP."""
        from nexus.auth.sso.github import GitHubProvider

        httpserver.expect_request(
            "/user",
            method="GET",
        ).respond_with_json(
            {
                "id": 12345,
                "login": "testuser",
                "name": "Test User",
                "email": "testuser@example.com",
                "avatar_url": "https://avatars.githubusercontent.com/u/12345",
            }
        )

        github = GitHubProvider(
            client_id="test-client",
            client_secret="test-secret",
        )
        github.USERINFO_URL = httpserver.url_for("/user")

        info = await github.get_user_info("gho_test_token")

        assert info.provider_user_id == "12345"
        assert info.name == "Test User"
        assert info.email == "testuser@example.com"
        assert info.picture == "https://avatars.githubusercontent.com/u/12345"

        await github.close()

    @pytest.mark.asyncio
    async def test_github_user_info_with_email_fallback(self, httpserver: HTTPServer):
        """GitHub fetches email from /user/emails if not in /user."""
        from nexus.auth.sso.github import GitHubProvider

        httpserver.expect_request(
            "/user",
            method="GET",
        ).respond_with_json(
            {
                "id": 67890,
                "login": "privateemail",
                "name": "Private Email User",
                "email": None,  # Email is private
            }
        )

        httpserver.expect_request(
            "/user/emails",
            method="GET",
        ).respond_with_json(
            [
                {
                    "email": "primary@example.com",
                    "primary": True,
                    "verified": True,
                },
                {
                    "email": "secondary@example.com",
                    "primary": False,
                    "verified": True,
                },
            ]
        )

        github = GitHubProvider(
            client_id="test-client",
            client_secret="test-secret",
        )
        github.USERINFO_URL = httpserver.url_for("/user")
        github.EMAILS_URL = httpserver.url_for("/user/emails")

        info = await github.get_user_info("gho_test_token")

        assert info.email == "primary@example.com"
        assert info.email_verified is True

        await github.close()


# =============================================================================
# Tests: Google OAuth Flow with Real HTTP
# =============================================================================


class TestGoogleOAuthFlowIntegration:
    """Integration tests for Google OAuth flow with real HTTP."""

    @pytest.mark.asyncio
    async def test_google_token_exchange_success(self, httpserver: HTTPServer):
        """Google token exchange with real HTTP server."""
        from nexus.auth.sso.google import GoogleProvider

        httpserver.expect_request(
            "/token",
            method="POST",
        ).respond_with_json(
            {
                "access_token": "ya29.test_access_token",
                "id_token": "eyJ.fake.id_token",
                "refresh_token": "1//test_refresh",
                "token_type": "Bearer",
                "expires_in": 3599,
                "scope": "openid email profile",
            }
        )

        google = GoogleProvider(
            client_id="test.apps.googleusercontent.com",
            client_secret="test-secret",
        )
        google.TOKEN_URL = httpserver.url_for("/token")

        tokens = await google.exchange_code(
            code="google-auth-code",
            redirect_uri="https://myapp.com/callback",
        )

        assert tokens.access_token == "ya29.test_access_token"
        assert tokens.id_token == "eyJ.fake.id_token"
        assert tokens.refresh_token == "1//test_refresh"
        assert tokens.expires_in == 3599

        await google.close()

    @pytest.mark.asyncio
    async def test_google_user_info_success(self, httpserver: HTTPServer):
        """Google user info fetch with real HTTP."""
        from nexus.auth.sso.google import GoogleProvider

        httpserver.expect_request(
            "/userinfo",
            method="GET",
        ).respond_with_json(
            {
                "sub": "google-user-123",
                "email": "user@gmail.com",
                "email_verified": True,
                "name": "Google User",
                "given_name": "Google",
                "family_name": "User",
                "picture": "https://lh3.googleusercontent.com/photo",
                "locale": "en",
            }
        )

        google = GoogleProvider(
            client_id="test.apps.googleusercontent.com",
            client_secret="test-secret",
        )
        google.USERINFO_URL = httpserver.url_for("/userinfo")

        info = await google.get_user_info("ya29.test_token")

        assert info.provider_user_id == "google-user-123"
        assert info.email == "user@gmail.com"
        assert info.email_verified is True
        assert info.name == "Google User"
        assert info.given_name == "Google"
        assert info.family_name == "User"
        assert info.locale == "en"

        await google.close()

    @pytest.mark.asyncio
    async def test_google_token_exchange_error(self, httpserver: HTTPServer):
        """Google returns error on invalid code."""
        from nexus.auth.sso.google import GoogleProvider

        httpserver.expect_request(
            "/token",
            method="POST",
        ).respond_with_data(
            json.dumps({"error": "invalid_grant"}),
            status=400,
            content_type="application/json",
        )

        google = GoogleProvider(
            client_id="test.apps.googleusercontent.com",
            client_secret="test-secret",
        )
        google.TOKEN_URL = httpserver.url_for("/token")

        with pytest.raises(SSOAuthError, match="Token exchange failed"):
            await google.exchange_code(
                code="bad-code",
                redirect_uri="https://myapp.com/callback",
            )

        await google.close()


# =============================================================================
# Tests: Azure AD OAuth Flow with Real HTTP
# =============================================================================


class TestAzureOAuthFlowIntegration:
    """Integration tests for Azure AD OAuth flow with real HTTP."""

    @pytest.mark.asyncio
    async def test_azure_token_exchange_success(self, httpserver: HTTPServer):
        """Azure AD token exchange with real HTTP server."""
        from nexus.auth.sso.azure import AzureADProvider

        httpserver.expect_request(
            "/test-tenant/oauth2/v2.0/token",
            method="POST",
        ).respond_with_json(
            {
                "access_token": "eyJ.azure_access_token",
                "id_token": "eyJ.azure_id_token",
                "refresh_token": "0.azure_refresh",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "openid profile email",
            }
        )

        azure = AzureADProvider(
            tenant_id="test-tenant",
            client_id="azure-client-id",
            client_secret="azure-secret",
        )
        # Override authority base to local server
        azure.AUTHORITY_BASE = httpserver.url_for("")

        tokens = await azure.exchange_code(
            code="azure-auth-code",
            redirect_uri="https://myapp.com/callback",
        )

        assert tokens.access_token == "eyJ.azure_access_token"
        assert tokens.id_token == "eyJ.azure_id_token"
        assert tokens.refresh_token == "0.azure_refresh"

        await azure.close()

    @pytest.mark.asyncio
    async def test_azure_user_info_from_graph(self, httpserver: HTTPServer):
        """Azure user info from Microsoft Graph API."""
        from nexus.auth.sso.azure import AzureADProvider

        httpserver.expect_request(
            "/me",
            method="GET",
        ).respond_with_json(
            {
                "id": "azure-user-id-123",
                "displayName": "Azure User",
                "mail": "azure.user@company.com",
                "givenName": "Azure",
                "surname": "User",
                "preferredLanguage": "en-US",
            }
        )

        azure = AzureADProvider(
            tenant_id="test-tenant",
            client_id="azure-client-id",
            client_secret="azure-secret",
        )
        azure.GRAPH_API_BASE = httpserver.url_for("")

        info = await azure.get_user_info("eyJ.azure_access_token")

        assert info.provider_user_id == "azure-user-id-123"
        assert info.name == "Azure User"
        assert info.email == "azure.user@company.com"
        assert info.email_verified is True  # Azure verifies emails
        assert info.given_name == "Azure"
        assert info.family_name == "User"

        await azure.close()


# =============================================================================
# Tests: CSRF State Validation Flow
# =============================================================================


class TestCsrfStateValidationIntegration:
    """Integration tests for CSRF state management."""

    def test_state_flow_create_and_validate(self):
        """Full state lifecycle: create -> validate -> consumed."""
        import secrets

        store = _get_state_store()
        state = secrets.token_urlsafe(32)
        store.store(state)

        # Validate (consume)
        assert store.validate_and_consume(state) is True

        # State consumed - cannot be used again
        assert store.validate_and_consume(state) is False

    def test_state_prevents_replay(self):
        """Same state cannot be used twice (one-time use)."""
        store = _get_state_store()
        state = "replay-test-state"
        store.store(state)

        # First use
        store.validate_and_consume(state)

        # Second use fails
        assert store.validate_and_consume(state) is False

    def test_expired_state_rejected(self):
        """Expired state is detected and rejected."""
        # Use a store with very short TTL to test expiry
        short_ttl_store = InMemorySSOStateStore(ttl_seconds=1)
        configure_state_store(short_ttl_store)

        state = "expired-state"
        # Directly insert with past timestamp to simulate expiry
        short_ttl_store._store[state] = time.time() - 100

        # Expired state is rejected
        assert short_ttl_store.validate_and_consume(state) is False

    def test_unknown_state_rejected(self):
        """Unknown state (CSRF attack) is rejected."""
        store = _get_state_store()
        assert store.validate_and_consume("unknown-state") is False

    @pytest.mark.asyncio
    async def test_handle_callback_rejects_invalid_state(self):
        """handle_sso_callback raises on invalid state."""
        from nexus.auth.sso import handle_sso_callback
        from nexus.auth.sso.github import GitHubProvider

        github = GitHubProvider(
            client_id="test-client",
            client_secret="test-secret",
        )

        with pytest.raises(InvalidStateError, match="Invalid or expired"):
            await handle_sso_callback(
                provider=github,
                code="some-code",
                state="bogus-state",
                auth_plugin=None,
                callback_base_url="https://myapp.com",
            )

    @pytest.mark.asyncio
    async def test_handle_callback_rejects_expired_state(self):
        """handle_sso_callback raises on expired state."""
        from nexus.auth.sso import handle_sso_callback
        from nexus.auth.sso.github import GitHubProvider

        # Use a store with short TTL and insert expired state
        short_ttl_store = InMemorySSOStateStore(ttl_seconds=1)
        configure_state_store(short_ttl_store)

        state = "expired-callback-state"
        short_ttl_store._store[state] = time.time() - 100

        github = GitHubProvider(
            client_id="test-client",
            client_secret="test-secret",
        )

        with pytest.raises(InvalidStateError, match="Invalid or expired"):
            await handle_sso_callback(
                provider=github,
                code="some-code",
                state=state,
                auth_plugin=None,
                callback_base_url="https://myapp.com",
            )


# =============================================================================
# Tests: Authorization URL Verification
# =============================================================================


class TestAuthorizationUrlIntegration:
    """Integration tests for authorization URL generation across providers."""

    def test_all_providers_generate_valid_urls(self):
        """All providers generate URLs with required OAuth2 parameters."""
        from nexus.auth.sso.azure import AzureADProvider
        from nexus.auth.sso.github import GitHubProvider
        from nexus.auth.sso.google import GoogleProvider

        providers = [
            AzureADProvider(
                tenant_id="test-tenant",
                client_id="azure-client",
                client_secret="secret",
            ),
            GoogleProvider(
                client_id="google-client",
                client_secret="secret",
            ),
            GitHubProvider(
                client_id="github-client",
                client_secret="secret",
            ),
        ]

        for provider in providers:
            url = provider.get_authorization_url(
                state="test-state",
                redirect_uri="https://myapp.com/callback",
            )

            assert "state=test-state" in url, f"{provider.name} missing state param"
            assert (
                f"client_id={provider.client_id}" in url
            ), f"{provider.name} missing client_id param"
            assert "redirect_uri=" in url, f"{provider.name} missing redirect_uri"
