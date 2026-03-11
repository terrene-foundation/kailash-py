"""Integration tests for RBAC system (TODO-310B).

Tests RBAC with real JWT middleware, real HTTP requests via TestClient.
Tier 2 tests - NO MOCKING.
"""

from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from fastapi import APIRouter, Depends, Request
from nexus import Nexus
from nexus.auth.dependencies import RequirePermission, RequireRole
from nexus.auth.jwt import JWTConfig, JWTMiddleware
from nexus.auth.rbac import RBACManager, RBACMiddleware
from starlette.testclient import TestClient

SECRET = "integration-test-secret-key-at-least-32-chars"

ROLE_CONFIG = {
    "super_admin": {
        "permissions": ["*"],
        "description": "Full system access",
        "inherits": [],
    },
    "admin": {
        "permissions": ["manage:users", "manage:roles", "delete:*"],
        "description": "Administrative access",
        "inherits": ["editor"],
    },
    "editor": {
        "permissions": ["write:articles", "write:comments"],
        "description": "Content editing",
        "inherits": ["viewer"],
    },
    "viewer": {
        "permissions": ["read:*"],
        "description": "Read-only access",
        "inherits": [],
    },
}


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
# Fixtures
# =============================================================================


@pytest.fixture
def role_app():
    """Create Nexus app with JWT middleware for role-based tests."""
    app = Nexus(enable_durability=False)
    app.add_middleware(JWTMiddleware, config=JWTConfig(secret=SECRET))

    router = APIRouter()

    @router.get("/admin")
    def admin_endpoint(user=Depends(RequireRole("admin", "super_admin"))):
        return {"admin": True, "user_id": user.user_id}

    @router.get("/editor")
    def editor_endpoint(user=Depends(RequireRole("editor", "admin", "super_admin"))):
        return {"editor": True, "user_id": user.user_id}

    app.include_router(router, prefix="/api")
    return app


@pytest.fixture
def role_client(role_app):
    return TestClient(role_app._gateway.app)


@pytest.fixture
def permission_app():
    """Create Nexus app with JWT middleware for permission-based tests.

    RequirePermission checks user.permissions (from JWT claims).
    """
    app = Nexus(enable_durability=False)
    app.add_middleware(JWTMiddleware, config=JWTConfig(secret=SECRET))

    router = APIRouter()

    @router.post("/articles")
    def create_article(user=Depends(RequirePermission("write:articles"))):
        return {"created": True, "author": user.user_id}

    @router.delete("/users/{user_id}")
    def delete_user(user_id: str, user=Depends(RequirePermission("delete:users"))):
        return {"deleted": user_id}

    @router.get("/read-any")
    def read_any(user=Depends(RequirePermission("read:anything"))):
        return {"read": True}

    app.include_router(router, prefix="/api")
    return app


@pytest.fixture
def permission_client(permission_app):
    return TestClient(permission_app._gateway.app)


# =============================================================================
# Tests: Role-Based Access via RequireRole
# =============================================================================


class TestRoleBasedAccess:
    """Integration tests for role-based endpoint access using RequireRole."""

    def test_admin_can_access_admin_endpoint(self, role_client):
        """Admin role can access admin-only endpoint."""
        token = _make_token(roles=["admin"])
        response = role_client.get(
            "/api/admin",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["admin"] is True

    def test_super_admin_can_access_admin_endpoint(self, role_client):
        """Super admin can also access admin endpoint."""
        token = _make_token(roles=["super_admin"])
        response = role_client.get(
            "/api/admin",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

    def test_viewer_cannot_access_admin_endpoint(self, role_client):
        """Viewer role is denied access to admin endpoint."""
        token = _make_token(roles=["viewer"])
        response = role_client.get(
            "/api/admin",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    def test_editor_can_access_editor_endpoint(self, role_client):
        """Editor role can access editor endpoint."""
        token = _make_token(roles=["editor"])
        response = role_client.get(
            "/api/editor",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["editor"] is True

    def test_viewer_cannot_access_editor_endpoint(self, role_client):
        """Viewer cannot access editor endpoint."""
        token = _make_token(roles=["viewer"])
        response = role_client.get(
            "/api/editor",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    def test_unauthenticated_gets_401(self, role_client):
        """No token returns 401."""
        response = role_client.get("/api/admin")
        assert response.status_code == 401

    def test_multi_role_user(self, role_client):
        """User with multiple roles gets access if any matches."""
        token = _make_token(roles=["viewer", "admin"])
        response = role_client.get(
            "/api/admin",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200


# =============================================================================
# Tests: Permission-Based Access via RequirePermission (JWT Claims)
# =============================================================================


class TestPermissionBasedAccess:
    """Integration tests for permission-based access using JWT claim permissions."""

    def test_user_with_write_articles_permission(self, permission_client):
        """User with write:articles in JWT can create articles."""
        token = _make_token(permissions=["write:articles"])
        response = permission_client.post(
            "/api/articles",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["created"] is True

    def test_user_without_write_articles_permission(self, permission_client):
        """User without write:articles is denied."""
        token = _make_token(permissions=["read:articles"])
        response = permission_client.post(
            "/api/articles",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    def test_wildcard_permission_in_jwt(self, permission_client):
        """User with wildcard read:* in JWT can read anything."""
        token = _make_token(permissions=["read:*"])
        response = permission_client.get(
            "/api/read-any",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

    def test_delete_permission(self, permission_client):
        """User with delete:users can delete."""
        token = _make_token(permissions=["delete:users"])
        response = permission_client.delete(
            "/api/users/user-456",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["deleted"] == "user-456"

    def test_super_wildcard_permission(self, permission_client):
        """User with * permission can do everything."""
        token = _make_token(permissions=["*"])

        resp1 = permission_client.post(
            "/api/articles",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp1.status_code == 200

        resp2 = permission_client.delete(
            "/api/users/user-789",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp2.status_code == 200


# =============================================================================
# Tests: RBACManager with Real Hierarchy
# =============================================================================


class TestRBACManagerIntegration:
    """Integration tests for RBACManager with real role hierarchies."""

    def test_full_hierarchy_resolution(self):
        """Full hierarchy with transitive inheritance resolves correctly."""
        rbac = RBACManager(roles=ROLE_CONFIG)

        admin_perms = rbac.get_role_permissions("admin")
        assert "manage:users" in admin_perms
        assert "write:articles" in admin_perms  # From editor
        assert "read:*" in admin_perms  # From viewer via editor

    def test_permission_check_through_hierarchy(self):
        """Permission checks work through full hierarchy."""
        rbac = RBACManager(roles=ROLE_CONFIG)

        from nexus.auth.models import AuthenticatedUser

        admin = AuthenticatedUser(user_id="admin-1", roles=["admin"])
        editor = AuthenticatedUser(user_id="editor-1", roles=["editor"])
        viewer = AuthenticatedUser(user_id="viewer-1", roles=["viewer"])

        assert rbac.has_permission(admin, "delete:users") is True
        assert rbac.has_permission(editor, "write:articles") is True
        assert rbac.has_permission(editor, "read:anything") is True  # read:* inherited
        assert rbac.has_permission(viewer, "write:articles") is False

    def test_dynamic_role_with_real_checking(self):
        """Dynamically added role works with permission checks."""
        rbac = RBACManager(roles=ROLE_CONFIG)
        rbac.add_role(
            "content_manager",
            ["manage:content"],
            inherits=["editor"],
        )

        from nexus.auth.models import AuthenticatedUser

        cm = AuthenticatedUser(user_id="cm-1", roles=["content_manager"])
        assert rbac.has_permission(cm, "manage:content") is True
        assert rbac.has_permission(cm, "write:articles") is True  # From editor
        assert rbac.has_permission(cm, "read:anything") is True  # From viewer

    def test_diamond_inheritance_no_duplication(self):
        """Diamond inheritance resolves without duplication issues."""
        roles = {
            "base": ["read:*"],
            "left": {"permissions": ["write:x"], "inherits": ["base"]},
            "right": {"permissions": ["write:y"], "inherits": ["base"]},
            "top": {"permissions": ["admin:*"], "inherits": ["left", "right"]},
        }
        rbac = RBACManager(roles=roles)
        top_perms = rbac.get_role_permissions("top")
        assert "admin:*" in top_perms
        assert "write:x" in top_perms
        assert "write:y" in top_perms
        assert "read:*" in top_perms
        assert len(top_perms) == 4  # No duplicates

    def test_stats_reflect_hierarchy(self):
        """Stats accurately reflect role hierarchy."""
        rbac = RBACManager(roles=ROLE_CONFIG)
        stats = rbac.get_stats()
        assert stats["total_roles"] == 4
        editor_stats = stats["roles"]["editor"]
        assert editor_stats["total_permissions"] == 3  # 2 own + 1 viewer (read:*)


# =============================================================================
# Tests: RBAC Middleware Attaches Context
# =============================================================================


class TestRBACMiddlewareContext:
    """Integration tests for RBAC middleware attaching context to requests."""

    def test_rbac_context_attached_to_authenticated_request(self):
        """RBAC middleware attaches user_permissions and rbac_manager."""
        app = Nexus(enable_durability=False)
        # JWT must run first (added last due to Starlette ordering)
        app.add_middleware(RBACMiddleware, roles=ROLE_CONFIG)
        app.add_middleware(JWTMiddleware, config=JWTConfig(secret=SECRET))

        captured = {}

        router = APIRouter()

        @router.get("/check-context")
        def check_context_proper(request: Request):
            captured["has_permissions"] = hasattr(request.state, "user_permissions")
            captured["has_rbac_manager"] = hasattr(request.state, "rbac_manager")
            if captured["has_permissions"]:
                captured["permissions_count"] = len(request.state.user_permissions)
            return {"ok": True}

        app.include_router(router, prefix="/api")
        client = TestClient(app._gateway.app)

        token = _make_token(roles=["editor"])
        response = client.get(
            "/api/check-context",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert captured.get("has_permissions") is True
        assert captured.get("has_rbac_manager") is True
        # Editor has 5 perms: write:articles, write:comments + read:*,read:articles...(viewer)
        assert captured.get("permissions_count", 0) > 0
