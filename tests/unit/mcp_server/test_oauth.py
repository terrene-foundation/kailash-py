"""Unit tests for OAuth 2.1 authentication system."""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.mcp_server.errors import AuthenticationError, AuthorizationError
from kailash.mcp_server.oauth import (
    AccessToken,
    AuthorizationCode,
    AuthorizationServer,
    ClientType,
    GrantType,
    InMemoryClientStore,
    InMemoryTokenStore,
    JWTManager,
    OAuth2Client,
    OAuthClient,
    RefreshToken,
    ResourceServer,
    TokenType,
)


class TestOAuthClient:
    """Test OAuth client representation."""

    def test_oauth_client_creation(self):
        """Test creating OAuth client."""
        client = OAuthClient(
            client_id="test_client_123",
            client_name="Test Application",
            client_type=ClientType.CONFIDENTIAL,
            redirect_uris=["https://app.example.com/callback"],
            grant_types=[GrantType.AUTHORIZATION_CODE],
            scopes=["read", "write"],
        )

        assert client.client_id == "test_client_123"
        assert client.client_name == "Test Application"
        assert client.client_type == ClientType.CONFIDENTIAL
        assert "https://app.example.com/callback" in client.redirect_uris
        assert GrantType.AUTHORIZATION_CODE in client.grant_types
        assert "read" in client.scopes

    def test_oauth_client_to_dict(self):
        """Test converting OAuth client to dictionary."""
        client = OAuthClient(
            client_id="test_client",
            client_name="Test App",
            client_type=ClientType.PUBLIC,
            redirect_uris=["http://localhost:3000/callback"],
            grant_types=[GrantType.AUTHORIZATION_CODE],
            scopes=["read"],
        )

        data = client.to_dict()

        assert data["client_id"] == "test_client"
        assert data["client_name"] == "Test App"
        assert data["client_type"] == "public"
        assert data["redirect_uris"] == ["http://localhost:3000/callback"]

    def test_oauth_client_supports_grant_type(self):
        """Test checking if client supports grant type."""
        client = OAuthClient(
            client_id="test",
            grant_types=[GrantType.AUTHORIZATION_CODE, GrantType.CLIENT_CREDENTIALS],
        )

        assert client.supports_grant_type(GrantType.AUTHORIZATION_CODE) is True
        assert client.supports_grant_type(GrantType.CLIENT_CREDENTIALS) is True
        assert client.supports_grant_type(GrantType.REFRESH_TOKEN) is False

    def test_oauth_client_has_scope(self):
        """Test checking if client has scope."""
        client = OAuthClient(client_id="test", scopes=["read", "write", "admin"])

        assert client.has_scope("read") is True
        assert client.has_scope("admin") is True
        assert client.has_scope("delete") is False

    def test_oauth_client_valid_redirect_uri(self):
        """Test validating redirect URI."""
        client = OAuthClient(
            client_id="test",
            redirect_uris=[
                "https://app.example.com/callback",
                "http://localhost:3000/callback",
            ],
        )

        assert client.is_valid_redirect_uri("https://app.example.com/callback") is True
        assert client.is_valid_redirect_uri("http://localhost:3000/callback") is True
        assert client.is_valid_redirect_uri("https://malicious.com/callback") is False


class TestAccessToken:
    """Test access token representation."""

    def test_access_token_creation(self):
        """Test creating access token."""
        token = AccessToken(
            token="access_token_123",
            client_id="client_123",
            user_id="user_456",
            scopes=["read", "write"],
            expires_at=time.time() + 3600,
        )

        assert token.token == "access_token_123"
        assert token.client_id == "client_123"
        assert token.user_id == "user_456"
        assert "read" in token.scopes
        assert not token.is_expired()

    def test_access_token_expiry(self):
        """Test access token expiry checking."""
        # Expired token
        expired_token = AccessToken(
            token="expired_token",
            client_id="client",
            expires_at=time.time() - 3600,  # 1 hour ago
        )

        assert expired_token.is_expired() is True

        # Valid token
        valid_token = AccessToken(
            token="valid_token",
            client_id="client",
            expires_at=time.time() + 3600,  # 1 hour from now
        )

        assert valid_token.is_expired() is False

    def test_access_token_has_scope(self):
        """Test checking if token has scope."""
        token = AccessToken(token="token", client_id="client", scopes=["read", "write"])

        assert token.has_scope("read") is True
        assert token.has_scope("write") is True
        assert token.has_scope("admin") is False

    def test_access_token_to_dict(self):
        """Test converting access token to dictionary."""
        token = AccessToken(
            token="token_123",
            client_id="client_123",
            scopes=["read"],
            expires_at=time.time() + 3600,
        )

        data = token.to_dict()

        assert data["access_token"] == "token_123"
        assert data["token_type"] == "Bearer"
        assert data["scope"] == "read"
        assert "expires_in" in data


class TestRefreshToken:
    """Test refresh token representation."""

    def test_refresh_token_creation(self):
        """Test creating refresh token."""
        token = RefreshToken(
            token="refresh_token_123",
            client_id="client_123",
            user_id="user_456",
            scopes=["read", "write"],
        )

        assert token.token == "refresh_token_123"
        assert token.client_id == "client_123"
        assert token.user_id == "user_456"
        assert "read" in token.scopes

    def test_refresh_token_is_revoked(self):
        """Test refresh token revocation status."""
        token = RefreshToken(token="token", client_id="client")

        assert token.is_revoked is False

        token.revoke()
        assert token.is_revoked is True


class TestAuthorizationCode:
    """Test authorization code representation."""

    def test_authorization_code_creation(self):
        """Test creating authorization code."""
        code = AuthorizationCode(
            code="auth_code_123",
            client_id="client_123",
            user_id="user_456",
            redirect_uri="https://app.example.com/callback",
            scopes=["read"],
            expires_at=time.time() + 600,
        )

        assert code.code == "auth_code_123"
        assert code.client_id == "client_123"
        assert code.redirect_uri == "https://app.example.com/callback"
        assert not code.is_expired()

    def test_authorization_code_expiry(self):
        """Test authorization code expiry."""
        # Short-lived code (10 minutes)
        code = AuthorizationCode(
            code="code",
            client_id="client",
            redirect_uri="https://example.com/callback",
            expires_at=time.time() - 60,  # 1 minute ago
        )

        assert code.is_expired() is True


class TestInMemoryClientStore:
    """Test in-memory client store."""

    def setup_method(self):
        """Set up test environment."""
        self.store = InMemoryClientStore()

    @pytest.mark.asyncio
    async def test_store_and_get_client(self):
        """Test storing and retrieving client."""
        client = OAuthClient(
            client_id="test_client",
            client_name="Test Client",
            client_secret="secret_123",
        )

        await self.store.store_client(client)

        retrieved = await self.store.get_client("test_client")
        assert retrieved is not None
        assert retrieved.client_id == "test_client"
        assert retrieved.client_name == "Test Client"

    @pytest.mark.asyncio
    async def test_get_nonexistent_client(self):
        """Test getting client that doesn't exist."""
        result = await self.store.get_client("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_client(self):
        """Test deleting client."""
        client = OAuthClient(client_id="delete_me")
        await self.store.store_client(client)

        assert await self.store.get_client("delete_me") is not None

        await self.store.delete_client("delete_me")

        assert await self.store.get_client("delete_me") is None

    @pytest.mark.asyncio
    async def test_authenticate_client_valid(self):
        """Test authenticating client with valid credentials."""
        client = OAuthClient(client_id="auth_client", client_secret="secret_123")
        await self.store.store_client(client)

        authenticated = await self.store.authenticate_client(
            "auth_client", "secret_123"
        )
        assert authenticated is not None
        assert authenticated.client_id == "auth_client"

    @pytest.mark.asyncio
    async def test_authenticate_client_invalid(self):
        """Test authenticating client with invalid credentials."""
        client = OAuthClient(client_id="auth_client", client_secret="secret_123")
        await self.store.store_client(client)

        # Wrong secret
        authenticated = await self.store.authenticate_client(
            "auth_client", "wrong_secret"
        )
        assert authenticated is None

        # Wrong client ID
        authenticated = await self.store.authenticate_client(
            "wrong_client", "secret_123"
        )
        assert authenticated is None


class TestInMemoryTokenStore:
    """Test in-memory token store."""

    def setup_method(self):
        """Set up test environment."""
        self.store = InMemoryTokenStore()

    @pytest.mark.asyncio
    async def test_store_and_get_access_token(self):
        """Test storing and retrieving access token."""
        token = AccessToken(token="access_123", client_id="client_123", scopes=["read"])

        await self.store.store_access_token(token)

        retrieved = await self.store.get_access_token("access_123")
        assert retrieved is not None
        assert retrieved.token == "access_123"
        assert retrieved.client_id == "client_123"

    @pytest.mark.asyncio
    async def test_store_and_get_refresh_token(self):
        """Test storing and retrieving refresh token."""
        token = RefreshToken(
            token="refresh_123", client_id="client_123", scopes=["read"]
        )

        await self.store.store_refresh_token(token)

        retrieved = await self.store.get_refresh_token("refresh_123")
        assert retrieved is not None
        assert retrieved.token == "refresh_123"

    @pytest.mark.asyncio
    async def test_store_and_get_authorization_code(self):
        """Test storing and retrieving authorization code."""
        code = AuthorizationCode(
            code="auth_code_123",
            client_id="client_123",
            redirect_uri="https://example.com/callback",
            expires_at=time.time() + 600,
        )

        await self.store.store_authorization_code(code)

        retrieved = await self.store.get_authorization_code("auth_code_123")
        assert retrieved is not None
        assert retrieved.code == "auth_code_123"

    @pytest.mark.asyncio
    async def test_revoke_access_token(self):
        """Test revoking access token."""
        token = AccessToken(token="revoke_me", client_id="client")
        await self.store.store_access_token(token)

        await self.store.revoke_access_token("revoke_me")

        # Token should no longer be retrievable
        retrieved = await self.store.get_access_token("revoke_me")
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_revoke_refresh_token(self):
        """Test revoking refresh token."""
        token = RefreshToken(token="revoke_me", client_id="client")
        await self.store.store_refresh_token(token)

        await self.store.revoke_refresh_token("revoke_me")

        retrieved = await self.store.get_refresh_token("revoke_me")
        assert retrieved is None


class TestJWTManager:
    """Test JWT token management."""

    def setup_method(self):
        """Set up test environment."""
        # Create a test RSA key pair
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        self.private_key_pem = private_pem.decode()
        self.public_key_pem = public_pem.decode()

        self.jwt_manager = JWTManager(
            private_key_pem=self.private_key_pem,
            public_key_pem=self.public_key_pem,
            issuer="https://auth.example.com",
        )

    def test_jwt_manager_initialization(self):
        """Test JWT manager initialization."""
        assert self.jwt_manager.issuer == "https://auth.example.com"
        assert self.jwt_manager.algorithm == "RS256"

    def test_create_access_token_jwt(self):
        """Test creating access token JWT."""
        token_data = {
            "client_id": "client_123",
            "user_id": "user_456",
            "scopes": ["read", "write"],
        }

        jwt_token = self.jwt_manager.create_access_token(token_data, expires_in=3600)

        assert isinstance(jwt_token, str)
        assert len(jwt_token.split(".")) == 3  # JWT has 3 parts

    def test_verify_access_token_jwt(self):
        """Test verifying access token JWT."""
        token_data = {
            "client_id": "client_123",
            "user_id": "user_456",
            "scopes": ["read", "write"],
        }

        jwt_token = self.jwt_manager.create_access_token(token_data, expires_in=3600)

        verified_data = self.jwt_manager.verify_access_token(jwt_token)

        assert verified_data["client_id"] == "client_123"
        assert verified_data["user_id"] == "user_456"
        assert "read" in verified_data["scopes"]

    def test_verify_invalid_jwt(self):
        """Test verifying invalid JWT."""
        with pytest.raises(AuthenticationError):
            self.jwt_manager.verify_access_token("invalid.jwt.token")

    def test_verify_expired_jwt(self):
        """Test verifying expired JWT."""
        token_data = {"client_id": "client"}

        # Create token that expires immediately
        jwt_token = self.jwt_manager.create_access_token(token_data, expires_in=-1)

        with pytest.raises(AuthenticationError):
            self.jwt_manager.verify_access_token(jwt_token)

    def test_create_refresh_token_jwt(self):
        """Test creating refresh token JWT."""
        token_data = {"client_id": "client_123", "user_id": "user_456"}

        jwt_token = self.jwt_manager.create_refresh_token(token_data)

        assert isinstance(jwt_token, str)

    def test_verify_refresh_token_jwt(self):
        """Test verifying refresh token JWT."""
        token_data = {"client_id": "client_123", "user_id": "user_456"}

        jwt_token = self.jwt_manager.create_refresh_token(token_data)
        verified_data = self.jwt_manager.verify_refresh_token(jwt_token)

        assert verified_data["client_id"] == "client_123"
        assert verified_data["user_id"] == "user_456"


class TestAuthorizationServer:
    """Test OAuth 2.1 authorization server."""

    def setup_method(self):
        """Set up test environment."""
        with patch("kailash.mcp_server.oauth.JWTManager") as mock_jwt:
            mock_jwt_instance = MagicMock()
            mock_jwt.return_value = mock_jwt_instance

            self.server = AuthorizationServer(
                issuer="https://auth.example.com",
                private_key_path="test_key.pem",
                client_store=InMemoryClientStore(),
                token_store=InMemoryTokenStore(),
            )

    @pytest.mark.asyncio
    async def test_register_client(self):
        """Test registering OAuth client."""
        client_data = {
            "client_name": "Test App",
            "redirect_uris": ["https://app.example.com/callback"],
            "grant_types": ["authorization_code"],
            "scopes": ["read", "write"],
        }

        client = await self.server.register_client(**client_data)

        assert client.client_name == "Test App"
        assert client.client_id is not None
        assert len(client.client_id) > 0
        assert client.client_secret is not None  # Should be confidential by default

    @pytest.mark.asyncio
    async def test_register_public_client(self):
        """Test registering public OAuth client."""
        client_data = {
            "client_name": "Mobile App",
            "client_type": "public",
            "redirect_uris": ["app://callback"],
        }

        client = await self.server.register_client(**client_data)

        assert client.client_type == ClientType.PUBLIC
        assert client.client_secret is None  # Public clients don't have secrets

    @pytest.mark.asyncio
    async def test_generate_authorization_code(self):
        """Test generating authorization code."""
        # First register a client
        client = await self.server.register_client(
            client_name="Test Client",
            redirect_uris=["https://app.example.com/callback"],
        )

        code = await self.server.generate_authorization_code(
            client_id=client.client_id,
            user_id="user_123",
            redirect_uri="https://app.example.com/callback",
            scopes=["read"],
        )

        assert code is not None
        assert len(code) > 0

    @pytest.mark.asyncio
    async def test_generate_authorization_code_invalid_redirect(self):
        """Test generating code with invalid redirect URI."""
        client = await self.server.register_client(
            client_name="Test Client",
            redirect_uris=["https://app.example.com/callback"],
        )

        with pytest.raises(AuthorizationError):
            await self.server.generate_authorization_code(
                client_id=client.client_id,
                user_id="user_123",
                redirect_uri="https://malicious.com/callback",  # Not in allowed URIs
                scopes=["read"],
            )

    @pytest.mark.asyncio
    async def test_exchange_authorization_code(self):
        """Test exchanging authorization code for tokens."""
        # Setup
        client = await self.server.register_client(
            client_name="Test Client",
            redirect_uris=["https://app.example.com/callback"],
        )

        code = await self.server.generate_authorization_code(
            client_id=client.client_id,
            user_id="user_123",
            redirect_uri="https://app.example.com/callback",
            scopes=["read", "write"],
        )

        # Mock JWT creation
        self.server.jwt_manager.create_access_token.return_value = "access_token_jwt"
        self.server.jwt_manager.create_refresh_token.return_value = "refresh_token_jwt"

        # Exchange code for tokens
        tokens = await self.server.exchange_authorization_code(
            client_id=client.client_id,
            client_secret=client.client_secret,
            code=code,
            redirect_uri="https://app.example.com/callback",
        )

        assert "access_token" in tokens
        assert "refresh_token" in tokens
        assert tokens["token_type"] == "Bearer"
        assert "expires_in" in tokens

    @pytest.mark.asyncio
    async def test_client_credentials_grant(self):
        """Test client credentials grant flow."""
        client = await self.server.register_client(
            client_name="Service Client",
            grant_types=["client_credentials"],
            scopes=["api.read", "api.write"],
        )

        self.server.jwt_manager.create_access_token.return_value = "access_token_jwt"

        tokens = await self.server.client_credentials_grant(
            client_id=client.client_id,
            client_secret=client.client_secret,
            scopes=["api.read"],
        )

        assert "access_token" in tokens
        assert tokens["token_type"] == "Bearer"
        # Client credentials flow typically doesn't include refresh tokens
        assert "refresh_token" not in tokens

    @pytest.mark.asyncio
    async def test_refresh_access_token(self):
        """Test refreshing access token."""
        # Setup client and initial tokens
        client = await self.server.register_client(client_name="Test Client")

        # Mock refresh token verification
        self.server.jwt_manager.verify_refresh_token.return_value = {
            "client_id": client.client_id,
            "user_id": "user_123",
            "scopes": ["read", "write"],
        }
        self.server.jwt_manager.create_access_token.return_value = (
            "new_access_token_jwt"
        )

        tokens = await self.server.refresh_access_token(
            client_id=client.client_id,
            client_secret=client.client_secret,
            refresh_token="valid_refresh_token",
        )

        assert "access_token" in tokens
        assert tokens["token_type"] == "Bearer"

    @pytest.mark.asyncio
    async def test_introspect_token(self):
        """Test token introspection."""
        # Mock token verification
        self.server.jwt_manager.verify_access_token.return_value = {
            "client_id": "client_123",
            "user_id": "user_456",
            "scopes": ["read", "write"],
            "exp": time.time() + 3600,
        }

        result = await self.server.introspect_token("valid_access_token")

        assert result["active"] is True
        assert result["client_id"] == "client_123"
        assert result["scope"] == "read write"

    @pytest.mark.asyncio
    async def test_introspect_invalid_token(self):
        """Test introspecting invalid token."""
        self.server.jwt_manager.verify_access_token.side_effect = AuthenticationError(
            "Invalid token"
        )

        result = await self.server.introspect_token("invalid_token")

        assert result["active"] is False

    @pytest.mark.asyncio
    async def test_revoke_token(self):
        """Test token revocation."""
        # Test should call the token store's revoke method
        with patch.object(
            self.server.token_store, "revoke_access_token"
        ) as mock_revoke:
            await self.server.revoke_token("token_to_revoke")
            mock_revoke.assert_called_once_with("token_to_revoke")


class TestResourceServer:
    """Test OAuth 2.1 resource server."""

    def setup_method(self):
        """Set up test environment."""
        with patch("kailash.mcp_server.oauth.JWTManager") as mock_jwt:
            mock_jwt_instance = MagicMock()
            mock_jwt.return_value = mock_jwt_instance

            self.server = ResourceServer(
                issuer="https://auth.example.com", audience="mcp-api"
            )

    @pytest.mark.asyncio
    async def test_authenticate_valid_token(self):
        """Test authenticating with valid token."""
        # Mock JWT verification
        self.server.jwt_manager.verify_access_token.return_value = {
            "client_id": "client_123",
            "user_id": "user_456",
            "scopes": ["read", "write"],
            "aud": "mcp-api",
        }

        auth_info = await self.server.authenticate("Bearer valid_token")

        assert auth_info is not None
        assert auth_info["client_id"] == "client_123"
        assert auth_info["user_id"] == "user_456"

    @pytest.mark.asyncio
    async def test_authenticate_invalid_token(self):
        """Test authenticating with invalid token."""
        self.server.jwt_manager.verify_access_token.side_effect = AuthenticationError(
            "Invalid token"
        )

        with pytest.raises(AuthenticationError):
            await self.server.authenticate("Bearer invalid_token")

    @pytest.mark.asyncio
    async def test_authenticate_wrong_audience(self):
        """Test authenticating with token for wrong audience."""
        self.server.jwt_manager.verify_access_token.return_value = {
            "client_id": "client_123",
            "aud": "different-api",  # Wrong audience
        }

        with pytest.raises(AuthorizationError):
            await self.server.authenticate("Bearer token_for_different_api")

    @pytest.mark.asyncio
    async def test_check_permission_valid(self):
        """Test checking permission with valid scope."""
        token_info = {"scopes": ["read", "write", "admin"]}

        # Should not raise
        await self.server.check_permission(token_info, "write")

    @pytest.mark.asyncio
    async def test_check_permission_invalid(self):
        """Test checking permission with insufficient scope."""
        token_info = {"scopes": ["read"]}

        with pytest.raises(AuthorizationError):
            await self.server.check_permission(token_info, "admin")

    def test_get_headers_for_auth(self):
        """Test getting headers for authentication."""
        headers = asyncio.run(self.server.get_headers())

        # ResourceServer as AuthProvider should return empty headers
        # (authentication is handled via Bearer tokens in requests)
        assert headers == {}


class TestOAuth2Client:
    """Test OAuth 2.1 client."""

    def setup_method(self):
        """Set up test environment."""
        self.client = OAuth2Client(
            client_id="test_client",
            client_secret="test_secret",
            token_endpoint="https://auth.example.com/token",
        )

    @pytest.mark.asyncio
    async def test_get_client_credentials_token(self):
        """Test getting token via client credentials flow."""
        mock_response = {
            "access_token": "access_token_123",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "api.read api.write",
        }

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value.json = AsyncMock(
                return_value=mock_response
            )
            mock_post.return_value.__aenter__.return_value.status = 200

            token = await self.client.get_client_credentials_token(
                scopes=["api.read", "api.write"]
            )

            assert token["access_token"] == "access_token_123"
            assert token["token_type"] == "Bearer"

    @pytest.mark.asyncio
    async def test_refresh_token(self):
        """Test refreshing access token."""
        mock_response = {
            "access_token": "new_access_token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value.json = AsyncMock(
                return_value=mock_response
            )
            mock_post.return_value.__aenter__.return_value.status = 200

            token = await self.client.refresh_token("refresh_token_123")

            assert token["access_token"] == "new_access_token"

    @pytest.mark.asyncio
    async def test_introspect_token(self):
        """Test token introspection."""
        mock_response = {
            "active": True,
            "client_id": "test_client",
            "scope": "read write",
        }

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value.json = AsyncMock(
                return_value=mock_response
            )
            mock_post.return_value.__aenter__.return_value.status = 200

            result = await self.client.introspect_token("access_token_123")

            assert result["active"] is True
            assert result["client_id"] == "test_client"

    @pytest.mark.asyncio
    async def test_client_credentials_token_error(self):
        """Test error handling in client credentials flow."""
        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 400
            mock_post.return_value.__aenter__.return_value.json = AsyncMock(
                return_value={
                    "error": "invalid_client",
                    "error_description": "Client authentication failed",
                }
            )

            with pytest.raises(AuthenticationError):
                await self.client.get_client_credentials_token()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
