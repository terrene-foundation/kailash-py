"""Unit tests for JWT middleware (TODO-310A).

Tests for JWTConfig validation, token extraction, token verification,
middleware dispatch, AuthenticatedUser creation, and error handling.
Tier 1 tests - mocking allowed for isolated unit testing.
"""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import jwt as pyjwt
import pytest
from nexus.auth.exceptions import ExpiredTokenError, InvalidTokenError
from nexus.auth.jwt import JWTConfig, JWTMiddleware
from nexus.auth.models import AuthenticatedUser

# =============================================================================
# Tests: JWTConfig Validation
# =============================================================================


class TestJWTConfigValidation:
    """Tests for JWTConfig dataclass and validation."""

    def test_config_requires_secret_for_hs256(self):
        """HS256 algorithm requires secret key."""
        with pytest.raises(ValueError, match="requires secret"):
            JWTConfig(algorithm="HS256")

    def test_config_requires_secret_for_hs384(self):
        """HS384 algorithm requires secret key."""
        with pytest.raises(ValueError, match="requires secret"):
            JWTConfig(algorithm="HS384")

    def test_config_requires_secret_for_hs512(self):
        """HS512 algorithm requires secret key."""
        with pytest.raises(ValueError, match="requires secret"):
            JWTConfig(algorithm="HS512")

    def test_config_requires_public_key_for_rs256(self):
        """RS256 algorithm requires public_key or jwks_url."""
        with pytest.raises(ValueError, match="requires public_key"):
            JWTConfig(algorithm="RS256")

    def test_config_requires_public_key_for_es256(self):
        """ES256 algorithm requires public_key or jwks_url."""
        with pytest.raises(ValueError, match="requires public_key"):
            JWTConfig(algorithm="ES256")

    def test_config_accepts_hs256_with_secret(self):
        """HS256 with secret key is valid."""
        config = JWTConfig(secret="test-secret-key-at-least-32-chars")
        assert config.algorithm == "HS256"
        assert config.secret == "test-secret-key-at-least-32-chars"

    def test_config_defaults(self):
        """JWTConfig has sensible defaults."""
        config = JWTConfig(secret="test-secret-key-for-jwt-unit-testing")
        assert config.algorithm == "HS256"
        assert config.token_header == "Authorization"
        assert config.token_cookie is None
        assert config.token_query_param is None
        assert config.verify_exp is True
        assert config.leeway == 0
        assert "/health" in config.exempt_paths

    def test_config_custom_exempt_paths(self):
        """JWTConfig accepts custom exempt paths."""
        config = JWTConfig(
            secret="test-secret-key-for-jwt-unit-testing",
            exempt_paths=["/health", "/api/public/*"],
        )
        assert config.exempt_paths == ["/health", "/api/public/*"]

    def test_config_accepts_jwks_url_for_rs256(self):
        """RS256 with jwks_url is valid (no public_key needed)."""
        config = JWTConfig(
            algorithm="RS256",
            jwks_url="https://example.com/.well-known/jwks.json",
        )
        assert config.algorithm == "RS256"
        assert config.jwks_url == "https://example.com/.well-known/jwks.json"

    def test_config_rejects_short_secret(self):
        """SECURITY: Secrets shorter than 32 chars are rejected."""
        with pytest.raises(ValueError, match="at least 32 characters"):
            JWTConfig(secret="too-short")

    def test_config_rejects_31_char_secret(self):
        """SECURITY: Exactly 31 chars rejected (boundary test)."""
        with pytest.raises(ValueError, match="at least 32 characters"):
            JWTConfig(secret="a" * 31)

    def test_config_accepts_32_char_secret(self):
        """SECURITY: Exactly 32 chars accepted (boundary test)."""
        config = JWTConfig(secret="a" * 32)
        assert len(config.secret) == 32


# =============================================================================
# Tests: Security - Token Type Validation
# =============================================================================


class TestTokenTypeValidation:
    """SECURITY: Tests for token_type claim validation."""

    SECRET = "test-secret-key-at-least-32-characters-long"

    def _make_middleware(self, **config_overrides):
        """Create a JWTMiddleware with test config."""
        defaults = {"secret": self.SECRET, "algorithm": "HS256"}
        defaults.update(config_overrides)
        config = JWTConfig(**defaults)
        mw = JWTMiddleware.__new__(JWTMiddleware)
        mw.config = config
        mw._jwks_client = None
        return mw

    def test_access_token_accepted(self):
        """Access tokens (token_type=access) pass verification."""
        mw = self._make_middleware()
        token = mw.create_access_token(user_id="user-1")
        payload = mw._verify_token(token)
        assert payload["sub"] == "user-1"
        assert payload["token_type"] == "access"

    def test_refresh_token_rejected(self):
        """SECURITY: Refresh tokens cannot be used for API auth."""
        mw = self._make_middleware()
        token = mw.create_refresh_token(user_id="user-1")
        with pytest.raises(InvalidTokenError, match="Refresh tokens"):
            mw._verify_token(token)

    def test_token_without_type_accepted(self):
        """Tokens without token_type claim are accepted (backwards compatibility)."""
        mw = self._make_middleware()
        payload = {
            "sub": "user-1",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }
        token = pyjwt.encode(payload, self.SECRET, algorithm="HS256")
        result = mw._verify_token(token)
        assert result["sub"] == "user-1"


# =============================================================================
# Tests: Security - Error Message Sanitization
# =============================================================================


class TestErrorMessageSanitization:
    """SECURITY: Tests that error messages don't leak internal details."""

    SECRET = "test-secret-key-at-least-32-characters-long"

    def _make_middleware(self, **config_overrides):
        """Create a JWTMiddleware with test config."""
        defaults = {"secret": self.SECRET, "algorithm": "HS256"}
        defaults.update(config_overrides)
        config = JWTConfig(**defaults)
        mw = JWTMiddleware.__new__(JWTMiddleware)
        mw.config = config
        mw._jwks_client = None
        return mw

    def test_algorithm_mismatch_doesnt_reveal_config(self):
        """SECURITY: Error on algorithm mismatch doesn't reveal configured algorithm."""
        import base64
        import json

        mw = self._make_middleware()
        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "HS384", "typ": "JWT"}).encode()
        ).rstrip(b"=")
        payload = base64.urlsafe_b64encode(
            json.dumps({"sub": "attacker"}).encode()
        ).rstrip(b"=")
        fake_token = f"{header.decode()}.{payload.decode()}.fake"

        with pytest.raises(InvalidTokenError) as exc_info:
            mw._verify_token(fake_token)

        error_msg = str(exc_info.value)
        assert "HS256" not in error_msg  # Don't reveal configured algo
        assert "algorithm mismatch" in error_msg.lower()

    def test_malformed_token_doesnt_reveal_internals(self):
        """SECURITY: Malformed token error doesn't leak library details."""
        mw = self._make_middleware()

        with pytest.raises(InvalidTokenError) as exc_info:
            mw._verify_token("not.a.valid.token")

        error_msg = str(exc_info.value)
        assert "Malformed token" in error_msg or "Invalid token" in error_msg


# =============================================================================
# Tests: Token Extraction
# =============================================================================


class TestTokenExtraction:
    """Tests for token extraction from various sources."""

    def _make_middleware(self, **config_overrides):
        """Create a JWTMiddleware with test config, bypassing ASGI init."""
        defaults = {"secret": "test-secret-key-for-jwt-unit-testing"}
        defaults.update(config_overrides)
        config = JWTConfig(**defaults)
        mw = JWTMiddleware.__new__(JWTMiddleware)
        mw.config = config
        mw._jwks_client = None
        return mw

    def test_extract_from_bearer_header(self):
        """Extract token from Authorization: Bearer header."""
        mw = self._make_middleware()
        request = MagicMock()
        request.headers = {"Authorization": "Bearer test-token-123"}
        request.cookies = {}
        request.query_params = {}

        token = mw._extract_token(request)
        assert token == "test-token-123"

    def test_extract_from_bearer_header_case_insensitive(self):
        """Extract token from lowercase 'bearer' prefix."""
        mw = self._make_middleware()
        request = MagicMock()
        request.headers = {"Authorization": "bearer test-token-456"}
        request.cookies = {}
        request.query_params = {}

        token = mw._extract_token(request)
        assert token == "test-token-456"

    def test_extract_from_cookie(self):
        """Extract token from cookie when configured."""
        mw = self._make_middleware(token_cookie="auth_token")
        request = MagicMock()
        request.headers = {}
        request.cookies = {"auth_token": "cookie-token-789"}
        request.query_params = {}

        token = mw._extract_token(request)
        assert token == "cookie-token-789"

    def test_extract_from_query_param(self):
        """Extract token from query parameter when configured."""
        mw = self._make_middleware(token_query_param="access_token")
        request = MagicMock()
        request.headers = {}
        request.cookies = {}
        request.query_params = {"access_token": "query-token-abc"}

        token = mw._extract_token(request)
        assert token == "query-token-abc"

    def test_extraction_priority_bearer_over_cookie(self):
        """Bearer header takes priority over cookie."""
        mw = self._make_middleware(token_cookie="auth_token")
        request = MagicMock()
        request.headers = {"Authorization": "Bearer header-token"}
        request.cookies = {"auth_token": "cookie-token"}
        request.query_params = {}

        token = mw._extract_token(request)
        assert token == "header-token"

    def test_extraction_priority_cookie_over_query(self):
        """Cookie takes priority over query parameter."""
        mw = self._make_middleware(
            token_cookie="auth_token",
            token_query_param="access_token",
        )
        request = MagicMock()
        request.headers = {}
        request.cookies = {"auth_token": "cookie-token"}
        request.query_params = {"access_token": "query-token"}

        token = mw._extract_token(request)
        assert token == "cookie-token"

    def test_no_token_returns_none(self):
        """No token found returns None."""
        mw = self._make_middleware()
        request = MagicMock()
        request.headers = {}
        request.cookies = {}
        request.query_params = {}

        token = mw._extract_token(request)
        assert token is None

    def test_cookie_not_checked_when_not_configured(self):
        """Cookie is not checked when token_cookie is None."""
        mw = self._make_middleware()  # No token_cookie
        request = MagicMock()
        request.headers = {}
        request.cookies = {"access_token": "sneaky-token"}
        request.query_params = {}

        token = mw._extract_token(request)
        assert token is None

    def test_query_param_not_checked_when_not_configured(self):
        """Query param is not checked when token_query_param is None."""
        mw = self._make_middleware()  # No token_query_param
        request = MagicMock()
        request.headers = {}
        request.cookies = {}
        request.query_params = {"access_token": "sneaky-token"}

        token = mw._extract_token(request)
        assert token is None


# =============================================================================
# Tests: Token Verification
# =============================================================================


class TestTokenVerification:
    """Tests for JWT token verification."""

    SECRET = "test-secret-key-at-least-32-characters-long"

    def _make_middleware(self, **config_overrides):
        """Create a JWTMiddleware with test config, bypassing ASGI init."""
        defaults = {"secret": self.SECRET, "algorithm": "HS256"}
        defaults.update(config_overrides)
        config = JWTConfig(**defaults)
        mw = JWTMiddleware.__new__(JWTMiddleware)
        mw.config = config
        mw._jwks_client = None
        return mw

    def _make_token(self, payload, secret=None, algorithm="HS256"):
        """Create a JWT token for testing."""
        return pyjwt.encode(
            payload,
            secret or self.SECRET,
            algorithm=algorithm,
        )

    def test_verify_valid_token_hs256(self):
        """Valid HS256 token is decoded correctly."""
        mw = self._make_middleware()
        payload = {
            "sub": "user-123",
            "email": "user@example.com",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }
        token = self._make_token(payload)

        result = mw._verify_token(token)
        assert result["sub"] == "user-123"
        assert result["email"] == "user@example.com"

    def test_verify_rejects_invalid_signature(self):
        """Token signed with wrong key is rejected."""
        mw = self._make_middleware()
        payload = {
            "sub": "user-123",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }
        token = self._make_token(payload, secret="wrong-secret-key-thats-different")

        with pytest.raises(InvalidTokenError):
            mw._verify_token(token)

    def test_verify_rejects_expired_token(self):
        """Expired token raises ExpiredTokenError."""
        mw = self._make_middleware()
        payload = {
            "sub": "user-123",
            "exp": int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()),
        }
        token = self._make_token(payload)

        with pytest.raises(ExpiredTokenError):
            mw._verify_token(token)

    def test_verify_rejects_algorithm_none(self):
        """Token with 'none' algorithm is rejected."""
        mw = self._make_middleware()
        # Manually craft a token with alg=none
        import base64
        import json

        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "none", "typ": "JWT"}).encode()
        ).rstrip(b"=")
        payload_data = base64.urlsafe_b64encode(
            json.dumps({"sub": "attacker"}).encode()
        ).rstrip(b"=")
        fake_token = f"{header.decode()}.{payload_data.decode()}."

        with pytest.raises(InvalidTokenError, match="none"):
            mw._verify_token(fake_token)

    def test_verify_rejects_algorithm_mismatch(self):
        """Token with mismatched algorithm is rejected."""
        mw = self._make_middleware(algorithm="HS256")
        # Create token claiming HS384 but server expects HS256
        import base64
        import json

        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "HS384", "typ": "JWT"}).encode()
        ).rstrip(b"=")
        payload_data = base64.urlsafe_b64encode(
            json.dumps({"sub": "attacker"}).encode()
        ).rstrip(b"=")
        import hashlib
        import hmac

        signing_input = f"{header.decode()}.{payload_data.decode()}"
        sig = base64.urlsafe_b64encode(
            hmac.new(
                self.SECRET.encode(), signing_input.encode(), hashlib.sha384
            ).digest()
        ).rstrip(b"=")
        fake_token = f"{signing_input}.{sig.decode()}"

        with pytest.raises(InvalidTokenError, match="algorithm mismatch"):
            mw._verify_token(fake_token)

    def test_verify_checks_audience(self):
        """Token with wrong audience is rejected."""
        mw = self._make_middleware(audience="my-app")
        payload = {
            "sub": "user-123",
            "aud": "wrong-app",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }
        token = self._make_token(payload)

        with pytest.raises(InvalidTokenError, match="audience"):
            mw._verify_token(token)

    def test_verify_checks_issuer(self):
        """Token with wrong issuer is rejected."""
        mw = self._make_middleware(issuer="https://auth.example.com")
        payload = {
            "sub": "user-123",
            "iss": "https://evil.example.com",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }
        token = self._make_token(payload)

        with pytest.raises(InvalidTokenError, match="issuer"):
            mw._verify_token(token)

    def test_verify_accepts_correct_audience(self):
        """Token with correct audience is accepted."""
        mw = self._make_middleware(audience="my-app")
        payload = {
            "sub": "user-123",
            "aud": "my-app",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }
        token = self._make_token(payload)

        result = mw._verify_token(token)
        assert result["sub"] == "user-123"

    def test_verify_accepts_correct_issuer(self):
        """Token with correct issuer is accepted."""
        mw = self._make_middleware(issuer="https://auth.example.com")
        payload = {
            "sub": "user-123",
            "iss": "https://auth.example.com",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }
        token = self._make_token(payload)

        result = mw._verify_token(token)
        assert result["sub"] == "user-123"

    def test_verify_respects_leeway(self):
        """Leeway allows slightly expired tokens."""
        mw = self._make_middleware(leeway=60)
        payload = {
            "sub": "user-123",
            "exp": int(
                (datetime.now(timezone.utc) - timedelta(seconds=30)).timestamp()
            ),
        }
        token = self._make_token(payload)

        result = mw._verify_token(token)
        assert result["sub"] == "user-123"

    def test_verify_rejects_malformed_token(self):
        """Malformed token raises InvalidTokenError."""
        mw = self._make_middleware()

        with pytest.raises(InvalidTokenError):
            mw._verify_token("not-a-valid-jwt")


# =============================================================================
# Tests: Path Exemptions
# =============================================================================


class TestPathExemptions:
    """Tests for path exemption checking."""

    def _make_middleware(self, exempt_paths):
        """Create a JWTMiddleware with test config."""
        config = JWTConfig(
            secret="test-secret-key-for-jwt-unit-testing", exempt_paths=exempt_paths
        )
        mw = JWTMiddleware.__new__(JWTMiddleware)
        mw.config = config
        mw._jwks_client = None
        return mw

    def test_exact_path_match(self):
        """Exact path match is exempt."""
        mw = self._make_middleware(["/health"])
        assert mw._is_path_exempt("/health") is True

    def test_exact_path_no_match(self):
        """Non-matching exact path is not exempt."""
        mw = self._make_middleware(["/health"])
        assert mw._is_path_exempt("/healthy") is False

    def test_wildcard_pattern(self):
        """Wildcard pattern matches sub-paths."""
        mw = self._make_middleware(["/auth/*"])
        assert mw._is_path_exempt("/auth/login") is True
        assert mw._is_path_exempt("/auth/sso/google") is True

    def test_wildcard_matches_base(self):
        """Wildcard pattern also matches the base path."""
        mw = self._make_middleware(["/auth/*"])
        assert mw._is_path_exempt("/auth") is True

    def test_wildcard_does_not_match_similar(self):
        """Wildcard pattern does not match similar paths."""
        mw = self._make_middleware(["/auth/*"])
        assert mw._is_path_exempt("/authentication") is False

    def test_multiple_exempt_paths(self):
        """Multiple exempt paths all work."""
        mw = self._make_middleware(["/health", "/docs", "/api/public/*"])
        assert mw._is_path_exempt("/health") is True
        assert mw._is_path_exempt("/docs") is True
        assert mw._is_path_exempt("/api/public/data") is True
        assert mw._is_path_exempt("/api/private/data") is False

    def test_default_exempt_paths(self):
        """Default exempt paths include standard endpoints."""
        config = JWTConfig(secret="test-secret-key-for-jwt-unit-testing")
        mw = JWTMiddleware.__new__(JWTMiddleware)
        mw.config = config
        mw._jwks_client = None

        assert mw._is_path_exempt("/health") is True
        assert mw._is_path_exempt("/metrics") is True
        assert mw._is_path_exempt("/docs") is True


# =============================================================================
# Tests: User Creation from Payload
# =============================================================================


class TestUserCreation:
    """Tests for AuthenticatedUser creation from JWT payload."""

    def _make_middleware(self):
        """Create a JWTMiddleware with test config."""
        config = JWTConfig(secret="test-secret-key-for-jwt-unit-testing")
        mw = JWTMiddleware.__new__(JWTMiddleware)
        mw.config = config
        mw._jwks_client = None
        return mw

    def test_standard_claims(self):
        """Standard JWT claims are mapped correctly."""
        mw = self._make_middleware()
        payload = {
            "sub": "user-123",
            "email": "user@example.com",
            "roles": ["admin", "editor"],
            "permissions": ["read:*", "write:articles"],
        }

        user = mw._create_user_from_payload(payload)

        assert user.user_id == "user-123"
        assert user.email == "user@example.com"
        assert user.roles == ["admin", "editor"]
        assert "read:*" in user.permissions
        assert "write:articles" in user.permissions

    def test_missing_sub_claim_raises(self):
        """Missing 'sub' claim raises InvalidTokenError."""
        mw = self._make_middleware()
        payload = {"email": "user@example.com"}

        with pytest.raises(InvalidTokenError, match="user identifier"):
            mw._create_user_from_payload(payload)

    def test_alternative_user_id_claims(self):
        """Alternative user_id claims (user_id, uid) are supported."""
        mw = self._make_middleware()

        # user_id claim
        user = mw._create_user_from_payload({"user_id": "alt-123"})
        assert user.user_id == "alt-123"

        # uid claim
        user = mw._create_user_from_payload({"uid": "uid-456"})
        assert user.user_id == "uid-456"

    def test_roles_as_string(self):
        """Single role string is converted to list."""
        mw = self._make_middleware()
        payload = {"sub": "user-123", "roles": "admin"}

        user = mw._create_user_from_payload(payload)
        assert user.roles == ["admin"]

    def test_role_singular_claim(self):
        """'role' (singular) claim is added to roles."""
        mw = self._make_middleware()
        payload = {"sub": "user-123", "role": "editor"}

        user = mw._create_user_from_payload(payload)
        assert "editor" in user.roles

    def test_permissions_from_scope(self):
        """OAuth2 'scope' claim is parsed into permissions."""
        mw = self._make_middleware()
        payload = {"sub": "user-123", "scope": "read write admin"}

        user = mw._create_user_from_payload(payload)
        assert "read" in user.permissions
        assert "write" in user.permissions
        assert "admin" in user.permissions

    def test_tenant_id_extraction(self):
        """Tenant ID is extracted from multiple possible claims."""
        mw = self._make_middleware()

        # tenant_id
        user = mw._create_user_from_payload({"sub": "u", "tenant_id": "t-123"})
        assert user.tenant_id == "t-123"

        # tid (Azure AD)
        user = mw._create_user_from_payload({"sub": "u", "tid": "azure-tenant"})
        assert user.tenant_id == "azure-tenant"

        # organization_id
        user = mw._create_user_from_payload({"sub": "u", "organization_id": "org-1"})
        assert user.tenant_id == "org-1"

    def test_provider_detection_azure(self):
        """Azure AD issuer is detected."""
        mw = self._make_middleware()
        payload = {
            "sub": "user-123",
            "iss": "https://login.microsoftonline.com/tenant-id/v2.0",
        }

        user = mw._create_user_from_payload(payload)
        assert user.provider == "azure"

    def test_provider_detection_google(self):
        """Google issuer is detected."""
        mw = self._make_middleware()
        payload = {"sub": "user-123", "iss": "https://accounts.google.com"}

        user = mw._create_user_from_payload(payload)
        assert user.provider == "google"

    def test_provider_detection_apple(self):
        """Apple issuer is detected."""
        mw = self._make_middleware()
        payload = {"sub": "user-123", "iss": "https://appleid.apple.com"}

        user = mw._create_user_from_payload(payload)
        assert user.provider == "apple"

    def test_provider_detection_local(self):
        """Unknown issuer defaults to 'local'."""
        mw = self._make_middleware()
        payload = {"sub": "user-123"}

        user = mw._create_user_from_payload(payload)
        assert user.provider == "local"

    def test_raw_claims_preserved(self):
        """Original JWT payload is stored as raw_claims."""
        mw = self._make_middleware()
        payload = {"sub": "user-123", "custom_field": "custom_value"}

        user = mw._create_user_from_payload(payload)
        assert user.raw_claims == payload
        assert user.get_claim("custom_field") == "custom_value"


# =============================================================================
# Tests: Token Creation
# =============================================================================


class TestTokenCreation:
    """Tests for access token and refresh token creation."""

    SECRET = "test-secret-key-at-least-32-characters-long"

    def _make_middleware(self, **config_overrides):
        """Create a JWTMiddleware with test config."""
        defaults = {"secret": self.SECRET, "algorithm": "HS256"}
        defaults.update(config_overrides)
        config = JWTConfig(**defaults)
        mw = JWTMiddleware.__new__(JWTMiddleware)
        mw.config = config
        mw._jwks_client = None
        return mw

    def test_create_access_token(self):
        """Create a valid access token."""
        mw = self._make_middleware()

        token = mw.create_access_token(
            user_id="user-123",
            email="user@example.com",
            roles=["admin"],
        )

        # Verify the token is valid
        payload = pyjwt.decode(token, self.SECRET, algorithms=["HS256"])
        assert payload["sub"] == "user-123"
        assert payload["email"] == "user@example.com"
        assert payload["roles"] == ["admin"]
        assert payload["token_type"] == "access"

    def test_create_access_token_with_expiry(self):
        """Access token has correct expiration."""
        mw = self._make_middleware()

        token = mw.create_access_token(
            user_id="user-123",
            expires_minutes=60,
        )

        payload = pyjwt.decode(token, self.SECRET, algorithms=["HS256"])
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)
        # Should expire ~60 minutes from now
        assert 59 <= (exp - now).total_seconds() / 60 <= 61

    def test_create_access_token_with_tenant(self):
        """Access token includes tenant_id."""
        mw = self._make_middleware()

        token = mw.create_access_token(
            user_id="user-123",
            tenant_id="tenant-456",
        )

        payload = pyjwt.decode(token, self.SECRET, algorithms=["HS256"])
        assert payload["tenant_id"] == "tenant-456"

    def test_create_access_token_with_issuer(self):
        """Access token includes issuer when configured."""
        mw = self._make_middleware(issuer="https://auth.example.com")

        token = mw.create_access_token(user_id="user-123")

        payload = pyjwt.decode(
            token,
            self.SECRET,
            algorithms=["HS256"],
            options={"verify_iss": False},
        )
        assert payload["iss"] == "https://auth.example.com"

    def test_create_refresh_token(self):
        """Create a valid refresh token."""
        mw = self._make_middleware()

        token = mw.create_refresh_token(user_id="user-123")

        payload = pyjwt.decode(token, self.SECRET, algorithms=["HS256"])
        assert payload["sub"] == "user-123"
        assert payload["token_type"] == "refresh"
        assert "jti" in payload  # Unique token ID

    def test_create_refresh_token_expiry(self):
        """Refresh token has correct expiration (days)."""
        mw = self._make_middleware()

        token = mw.create_refresh_token(user_id="user-123", expires_days=30)

        payload = pyjwt.decode(token, self.SECRET, algorithms=["HS256"])
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)
        days = (exp - now).total_seconds() / 86400
        assert 29 <= days <= 31

    def test_create_access_token_extra_claims(self):
        """Access token accepts extra claims."""
        mw = self._make_middleware()

        token = mw.create_access_token(
            user_id="user-123",
            custom_field="custom_value",
        )

        payload = pyjwt.decode(token, self.SECRET, algorithms=["HS256"])
        assert payload["custom_field"] == "custom_value"


# =============================================================================
# Tests: AuthenticatedUser Model
# =============================================================================


class TestAuthenticatedUserModel:
    """Tests for AuthenticatedUser dataclass."""

    def test_has_role(self):
        """has_role returns True for present role."""
        user = AuthenticatedUser(user_id="u", roles=["admin", "editor"])
        assert user.has_role("admin") is True
        assert user.has_role("viewer") is False

    def test_has_any_role(self):
        """has_any_role returns True if any role matches."""
        user = AuthenticatedUser(user_id="u", roles=["editor"])
        assert user.has_any_role("admin", "editor") is True
        assert user.has_any_role("admin", "superuser") is False

    def test_has_permission_exact(self):
        """has_permission checks exact permission match."""
        user = AuthenticatedUser(user_id="u", permissions=["read:users"])
        assert user.has_permission("read:users") is True
        assert user.has_permission("write:users") is False

    def test_has_permission_wildcard(self):
        """has_permission supports action wildcard."""
        user = AuthenticatedUser(user_id="u", permissions=["read:*"])
        assert user.has_permission("read:users") is True
        assert user.has_permission("read:articles") is True
        assert user.has_permission("write:users") is False

    def test_has_permission_super_wildcard(self):
        """'*' permission matches everything."""
        user = AuthenticatedUser(user_id="u", permissions=["*"])
        assert user.has_permission("read:users") is True
        assert user.has_permission("write:articles") is True
        assert user.has_permission("delete:anything") is True

    def test_is_admin(self):
        """is_admin detects admin roles."""
        admin = AuthenticatedUser(user_id="u", roles=["admin"])
        assert admin.is_admin is True

        super_admin = AuthenticatedUser(user_id="u", roles=["super_admin"])
        assert super_admin.is_admin is True

        viewer = AuthenticatedUser(user_id="u", roles=["viewer"])
        assert viewer.is_admin is False

    def test_display_name(self):
        """display_name prefers name > email > user_id."""
        user = AuthenticatedUser(
            user_id="u-123",
            email="user@example.com",
            raw_claims={"name": "John Doe"},
        )
        assert user.display_name == "John Doe"

        user2 = AuthenticatedUser(user_id="u-123", email="user@example.com")
        assert user2.display_name == "user@example.com"

        user3 = AuthenticatedUser(user_id="u-123")
        assert user3.display_name == "u-123"

    def test_get_claim(self):
        """get_claim retrieves from raw_claims."""
        user = AuthenticatedUser(
            user_id="u",
            raw_claims={"custom_field": "value", "nested": {"deep": True}},
        )
        assert user.get_claim("custom_field") == "value"
        assert user.get_claim("missing") is None
        assert user.get_claim("missing", "default") == "default"


# =============================================================================
# Tests: Exception Hierarchy
# =============================================================================


class TestExceptions:
    """Tests for auth exception hierarchy."""

    def test_auth_error_base(self):
        """AuthError is base class."""
        from nexus.auth.exceptions import AuthError

        err = AuthError("test error")
        assert str(err) == "test error"
        assert err.status_code == 500

    def test_authentication_error(self):
        """AuthenticationError has 401 status."""
        from nexus.auth.exceptions import AuthenticationError

        err = AuthenticationError()
        assert err.status_code == 401
        assert "authenticated" in err.detail.lower()

    def test_invalid_token_error(self):
        """InvalidTokenError has custom detail."""
        err = InvalidTokenError("bad token")
        assert err.detail == "bad token"
        assert err.status_code == 401

    def test_expired_token_error(self):
        """ExpiredTokenError has custom detail."""
        err = ExpiredTokenError()
        assert "expired" in err.detail.lower()
        assert err.status_code == 401

    def test_authorization_error(self):
        """AuthorizationError has 403 status."""
        from nexus.auth.exceptions import AuthorizationError

        err = AuthorizationError()
        assert err.status_code == 403

    def test_insufficient_role_error(self):
        """InsufficientRoleError uses generic detail (no role leaking)."""
        from nexus.auth.exceptions import InsufficientRoleError

        err = InsufficientRoleError(["admin", "manager"])
        assert err.detail == "Forbidden"
        assert "admin" not in err.detail
        assert err.status_code == 403

    def test_insufficient_permission_error(self):
        """InsufficientPermissionError uses generic detail (no permission leaking)."""
        from nexus.auth.exceptions import InsufficientPermissionError

        err = InsufficientPermissionError("write:users")
        assert err.detail == "Forbidden"
        assert "write:users" not in err.detail
        assert err.status_code == 403

    def test_rate_limit_exceeded_error(self):
        """RateLimitExceededError has 429 status."""
        from nexus.auth.exceptions import RateLimitExceededError

        err = RateLimitExceededError()
        assert err.status_code == 429
