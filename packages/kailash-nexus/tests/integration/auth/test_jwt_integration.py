"""Integration tests for JWT middleware (TODO-310A).

Tests JWT middleware with real HTTP requests via TestClient.
Tier 2 tests - NO MOCKING. Real tokens, real middleware, real HTTP.
"""

from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from nexus import Nexus
from nexus.auth.exceptions import ExpiredTokenError, InvalidTokenError
from nexus.auth.jwt import JWTConfig, JWTMiddleware
from starlette.testclient import TestClient

SECRET = "integration-test-secret-key-at-least-32-chars"


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def jwt_app():
    """Create a Nexus app with JWT middleware."""
    app = Nexus(enable_durability=False)
    app.add_middleware(JWTMiddleware, config=JWTConfig(secret=SECRET))
    return app


@pytest.fixture
def jwt_client(jwt_app):
    """Create a TestClient from a JWT-protected Nexus app."""
    return TestClient(jwt_app._gateway.app)


def _make_token(
    sub="user-123",
    email="user@example.com",
    roles=None,
    exp_minutes=60,
    secret=SECRET,
    algorithm="HS256",
    **extra,
):
    """Create a real JWT token for testing."""
    payload = {
        "sub": sub,
        "email": email,
        "exp": int(
            (datetime.now(timezone.utc) + timedelta(minutes=exp_minutes)).timestamp()
        ),
        "iat": int(datetime.now(timezone.utc).timestamp()),
    }
    if roles:
        payload["roles"] = roles
    payload.update(extra)
    return pyjwt.encode(payload, secret, algorithm=algorithm)


# =============================================================================
# Tests: JWT with Real HTTP
# =============================================================================


class TestJWTWithRealHTTP:
    """Integration tests for JWT middleware with real HTTP requests."""

    def test_health_exempt_no_token(self, jwt_client):
        """Health endpoint is exempt from JWT authentication."""
        response = jwt_client.get("/health")
        assert response.status_code == 200

    def test_protected_endpoint_requires_token(self, jwt_client):
        """Non-exempt endpoint returns 401 without token."""
        response = jwt_client.get("/workflows/test/execute")
        assert response.status_code == 401
        assert response.json()["error"] == "missing_token"

    def test_valid_token_passes_through(self, jwt_client):
        """Valid token allows access to protected endpoints."""
        token = _make_token()
        response = jwt_client.get(
            "/workflows/test/execute",
            headers={"Authorization": f"Bearer {token}"},
        )
        # Not 401 - token is valid (might be 404/405 since workflow doesn't exist)
        assert response.status_code != 401

    def test_expired_token_returns_401(self, jwt_client):
        """Expired token returns 401 with token_expired error."""
        token = _make_token(exp_minutes=-60)  # Already expired
        response = jwt_client.get(
            "/workflows/test/execute",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        assert response.json()["error"] == "token_expired"

    def test_invalid_signature_returns_401(self, jwt_client):
        """Token with wrong secret returns 401."""
        token = _make_token(secret="wrong-secret-key-thats-different-too")
        response = jwt_client.get(
            "/workflows/test/execute",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        assert response.json()["error"] == "invalid_token"

    def test_www_authenticate_header_on_401(self, jwt_client):
        """401 responses include WWW-Authenticate header."""
        response = jwt_client.get("/workflows/test/execute")
        assert "WWW-Authenticate" in response.headers

    def test_malformed_token_returns_401(self, jwt_client):
        """Malformed token returns 401."""
        response = jwt_client.get(
            "/workflows/test/execute",
            headers={"Authorization": "Bearer not-a-valid-jwt-at-all"},
        )
        assert response.status_code == 401


# =============================================================================
# Tests: Algorithm Confusion Attack
# =============================================================================


class TestAlgorithmConfusionAttack:
    """Security tests for algorithm confusion attacks."""

    def test_none_algorithm_rejected(self, jwt_client):
        """Token with 'none' algorithm is rejected."""
        import base64
        import json

        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "none", "typ": "JWT"}).encode()
        ).rstrip(b"=")
        payload = base64.urlsafe_b64encode(
            json.dumps(
                {
                    "sub": "attacker",
                    "exp": int(
                        (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()
                    ),
                }
            ).encode()
        ).rstrip(b"=")
        fake_token = f"{header.decode()}.{payload.decode()}."

        response = jwt_client.get(
            "/workflows/test/execute",
            headers={"Authorization": f"Bearer {fake_token}"},
        )
        assert response.status_code == 401

    def test_algorithm_mismatch_rejected(self, jwt_client):
        """Token with different algorithm than configured is rejected."""
        import base64
        import hashlib
        import hmac
        import json

        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "HS384", "typ": "JWT"}).encode()
        ).rstrip(b"=")
        payload = base64.urlsafe_b64encode(
            json.dumps(
                {
                    "sub": "attacker",
                    "exp": int(
                        (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()
                    ),
                }
            ).encode()
        ).rstrip(b"=")
        signing_input = f"{header.decode()}.{payload.decode()}"
        sig = base64.urlsafe_b64encode(
            hmac.new(SECRET.encode(), signing_input.encode(), hashlib.sha384).digest()
        ).rstrip(b"=")
        fake_token = f"{signing_input}.{sig.decode()}"

        response = jwt_client.get(
            "/workflows/test/execute",
            headers={"Authorization": f"Bearer {fake_token}"},
        )
        assert response.status_code == 401


# =============================================================================
# Tests: Token Creation and Verification Roundtrip
# =============================================================================


class TestTokenRoundtrip:
    """Integration tests for token creation and verification roundtrip."""

    def test_create_and_verify_access_token(self):
        """Create access token, then verify it through middleware."""
        config = JWTConfig(secret=SECRET)
        mw = JWTMiddleware.__new__(JWTMiddleware)
        mw.config = config
        mw._jwks_client = None

        # Create token
        token = mw.create_access_token(
            user_id="user-123",
            email="user@example.com",
            roles=["admin"],
            permissions=["read:*", "write:articles"],
            tenant_id="tenant-456",
        )

        # Verify token
        payload = mw._verify_token(token)
        assert payload["sub"] == "user-123"
        assert payload["email"] == "user@example.com"
        assert payload["roles"] == ["admin"]
        assert payload["permissions"] == ["read:*", "write:articles"]
        assert payload["tenant_id"] == "tenant-456"
        assert payload["token_type"] == "access"

    def test_refresh_token_rejected_by_verify(self):
        """Refresh tokens cannot be used as access tokens (security: token_type validation)."""
        config = JWTConfig(secret=SECRET)
        mw = JWTMiddleware.__new__(JWTMiddleware)
        mw.config = config
        mw._jwks_client = None

        # Create refresh token
        token = mw.create_refresh_token(user_id="user-123", tenant_id="tenant-456")

        # SECURITY: _verify_token must reject refresh tokens
        from nexus.auth.exceptions import InvalidTokenError

        with pytest.raises(InvalidTokenError, match="Refresh tokens cannot be used"):
            mw._verify_token(token)

    def test_create_refresh_token_structure(self):
        """Refresh token has correct structure (jti, token_type, etc.)."""
        import jwt as pyjwt

        config = JWTConfig(secret=SECRET)
        mw = JWTMiddleware.__new__(JWTMiddleware)
        mw.config = config
        mw._jwks_client = None

        # Create token
        token = mw.create_refresh_token(user_id="user-123", tenant_id="tenant-456")

        # Decode without verification to check structure
        payload = pyjwt.decode(token, SECRET, algorithms=["HS256"])
        assert payload["sub"] == "user-123"
        assert payload["tenant_id"] == "tenant-456"
        assert payload["token_type"] == "refresh"
        assert "jti" in payload

    def test_access_token_populates_user(self):
        """Access token creates correct AuthenticatedUser."""
        config = JWTConfig(secret=SECRET)
        mw = JWTMiddleware.__new__(JWTMiddleware)
        mw.config = config
        mw._jwks_client = None

        token = mw.create_access_token(
            user_id="user-123",
            email="user@example.com",
            roles=["admin", "editor"],
        )

        payload = mw._verify_token(token)
        user = mw._create_user_from_payload(payload)

        assert user.user_id == "user-123"
        assert user.email == "user@example.com"
        assert "admin" in user.roles
        assert "editor" in user.roles
        assert user.is_admin is True


# =============================================================================
# Tests: Cookie-Based Authentication
# =============================================================================


class TestCookieAuthentication:
    """Integration tests for cookie-based JWT authentication."""

    def test_cookie_token_authentication(self):
        """Token from cookie authenticates request."""
        app = Nexus(enable_durability=False)
        app.add_middleware(
            JWTMiddleware,
            config=JWTConfig(secret=SECRET, token_cookie="access_token"),
        )
        client = TestClient(app._gateway.app)

        token = _make_token()
        # Set cookie on the client
        client.cookies.set("access_token", token)

        response = client.get("/workflows/test/execute")
        # Not 401 - authenticated via cookie
        assert response.status_code != 401


# =============================================================================
# Tests: FastAPI Dependencies
# =============================================================================


class TestFastAPIDependencies:
    """Integration tests for FastAPI auth dependencies."""

    def test_get_current_user_with_valid_token(self):
        """get_current_user returns user from request state."""
        from fastapi import APIRouter, Depends, Request
        from nexus.auth.dependencies import get_current_user

        app = Nexus(enable_durability=False)
        app.add_middleware(JWTMiddleware, config=JWTConfig(secret=SECRET))

        router = APIRouter()

        @router.get("/profile")
        def get_profile(user=Depends(get_current_user)):
            return {"user_id": user.user_id, "email": user.email}

        app.include_router(router, prefix="/api")
        client = TestClient(app._gateway.app)

        token = _make_token(sub="user-456", email="test@example.com")
        response = client.get(
            "/api/profile",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json()["user_id"] == "user-456"
        assert response.json()["email"] == "test@example.com"

    def test_get_current_user_without_token(self):
        """get_current_user raises 401 without authentication."""
        from fastapi import APIRouter, Depends
        from nexus.auth.dependencies import get_current_user

        app = Nexus(enable_durability=False)
        # No JWT middleware - test dependency standalone
        router = APIRouter()

        @router.get("/profile")
        def get_profile(user=Depends(get_current_user)):
            return {"user_id": user.user_id}

        app.include_router(router, prefix="/api")
        client = TestClient(app._gateway.app)

        response = client.get("/api/profile")
        assert response.status_code == 401

    def test_require_role_dependency(self):
        """RequireRole dependency checks roles."""
        from fastapi import APIRouter, Depends
        from nexus.auth.dependencies import RequireRole

        app = Nexus(enable_durability=False)
        app.add_middleware(JWTMiddleware, config=JWTConfig(secret=SECRET))

        router = APIRouter()

        @router.get("/admin")
        def admin_endpoint(user=Depends(RequireRole("admin"))):
            return {"admin": True}

        app.include_router(router, prefix="/api")
        client = TestClient(app._gateway.app)

        # Admin user - should succeed
        admin_token = _make_token(roles=["admin"])
        response = client.get(
            "/api/admin",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["admin"] is True

        # Viewer user - should get 403
        viewer_token = _make_token(roles=["viewer"])
        response = client.get(
            "/api/admin",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == 403

    def test_require_permission_dependency(self):
        """RequirePermission dependency checks permissions."""
        from fastapi import APIRouter, Depends
        from nexus.auth.dependencies import RequirePermission

        app = Nexus(enable_durability=False)
        app.add_middleware(JWTMiddleware, config=JWTConfig(secret=SECRET))

        router = APIRouter()

        @router.post("/articles")
        def create_article(user=Depends(RequirePermission("write:articles"))):
            return {"created": True}

        app.include_router(router, prefix="/api")
        client = TestClient(app._gateway.app)

        # User with correct permission
        writer_token = _make_token(permissions=["write:articles"])
        response = client.post(
            "/api/articles",
            headers={"Authorization": f"Bearer {writer_token}"},
        )
        assert response.status_code == 200

        # User without permission
        reader_token = _make_token(permissions=["read:articles"])
        response = client.post(
            "/api/articles",
            headers={"Authorization": f"Bearer {reader_token}"},
        )
        assert response.status_code == 403
