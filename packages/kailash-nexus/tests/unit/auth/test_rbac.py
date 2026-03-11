"""Unit tests for RBAC system (TODO-310B).

Tests role-based access control: role hierarchy, permission wildcards,
inheritance cycles, caching, dynamic roles, and FastAPI dependencies.
Tier 1 - mocking allowed but minimal.
"""

import pytest
from nexus.auth.exceptions import InsufficientPermissionError, InsufficientRoleError
from nexus.auth.models import AuthenticatedUser
from nexus.auth.rbac import (
    RBACManager,
    RBACMiddleware,
    RoleDefinition,
    matches_permission,
    matches_permission_set,
    permissions_required,
    require_permission_dep,
    require_role_dep,
    roles_required,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def simple_roles():
    """Simple role definitions (list format)."""
    return {
        "super_admin": ["*"],
        "admin": ["read:*", "write:*", "delete:users", "manage:roles"],
        "editor": ["read:*", "write:articles", "write:comments"],
        "viewer": ["read:*"],
    }


@pytest.fixture
def hierarchical_roles():
    """Hierarchical role definitions (full format)."""
    return {
        "super_admin": {
            "permissions": ["*"],
            "description": "Full system access",
            "inherits": [],
        },
        "admin": {
            "permissions": ["manage:users", "manage:roles", "delete:*", "view:audit"],
            "description": "Administrative access",
            "inherits": ["editor", "moderator"],
        },
        "editor": {
            "permissions": ["write:articles", "write:comments", "publish:articles"],
            "description": "Content creation and editing",
            "inherits": ["viewer"],
        },
        "moderator": {
            "permissions": ["moderate:comments", "flag:content", "ban:users"],
            "description": "Content moderation",
            "inherits": ["viewer"],
        },
        "viewer": {
            "permissions": ["read:articles", "read:comments", "read:profiles"],
            "description": "Read-only access",
            "inherits": [],
        },
    }


@pytest.fixture
def simple_rbac(simple_roles):
    """RBACManager with simple roles."""
    return RBACManager(roles=simple_roles)


@pytest.fixture
def hierarchical_rbac(hierarchical_roles):
    """RBACManager with hierarchical roles."""
    return RBACManager(roles=hierarchical_roles)


def _make_user(
    user_id="user-1",
    roles=None,
    permissions=None,
    **kwargs,
):
    """Create an AuthenticatedUser for testing."""
    return AuthenticatedUser(
        user_id=user_id,
        roles=roles or [],
        permissions=permissions or [],
        **kwargs,
    )


# =============================================================================
# Tests: Permission Matching
# =============================================================================


class TestPermissionMatching:
    """Test permission pattern matching functions."""

    def test_exact_match(self):
        """Exact permission strings match."""
        assert matches_permission("read:users", "read:users") is True

    def test_exact_mismatch(self):
        """Non-matching exact permissions return False."""
        assert matches_permission("read:users", "read:articles") is False

    def test_action_wildcard(self):
        """Action wildcard 'read:*' matches any resource under that action."""
        assert matches_permission("read:*", "read:users") is True
        assert matches_permission("read:*", "read:articles") is True
        assert matches_permission("read:*", "write:users") is False

    def test_resource_wildcard(self):
        """Resource wildcard '*:users' matches any action on that resource."""
        assert matches_permission("*:users", "read:users") is True
        assert matches_permission("*:users", "write:users") is True
        assert matches_permission("*:users", "read:articles") is False

    def test_super_wildcard(self):
        """Super wildcard '*' matches everything."""
        assert matches_permission("*", "read:users") is True
        assert matches_permission("*", "write:articles") is True
        assert matches_permission("*", "anything:whatever") is True

    def test_no_colon_mismatch(self):
        """Permissions without colon only match exactly or via super wildcard."""
        assert matches_permission("admin", "admin") is True
        assert matches_permission("admin", "user") is False
        assert matches_permission("*", "admin") is True

    def test_double_wildcard(self):
        """'*:*' matches any action:resource."""
        assert matches_permission("*:*", "read:users") is True
        assert matches_permission("*:*", "write:anything") is True

    def test_matches_permission_set_any_match(self):
        """matches_permission_set returns True if any pattern matches."""
        perms = {"read:users", "write:articles"}
        assert matches_permission_set(perms, "read:users") is True
        assert matches_permission_set(perms, "write:articles") is True
        assert matches_permission_set(perms, "delete:users") is False

    def test_matches_permission_set_wildcard(self):
        """matches_permission_set works with wildcard patterns."""
        perms = {"read:*", "write:articles"}
        assert matches_permission_set(perms, "read:anything") is True
        assert matches_permission_set(perms, "write:users") is False

    def test_matches_permission_set_empty(self):
        """Empty permission set matches nothing."""
        assert matches_permission_set(set(), "read:users") is False


# =============================================================================
# Tests: RoleDefinition
# =============================================================================


class TestRoleDefinition:
    """Test RoleDefinition dataclass."""

    def test_basic_creation(self):
        """Create RoleDefinition with defaults."""
        role = RoleDefinition(name="viewer")
        assert role.name == "viewer"
        assert role.permissions == []
        assert role.description == ""
        assert role.inherits == []

    def test_full_creation(self):
        """Create RoleDefinition with all fields."""
        role = RoleDefinition(
            name="admin",
            permissions=["read:*", "write:*"],
            description="Admin role",
            inherits=["viewer"],
        )
        assert role.name == "admin"
        assert role.permissions == ["read:*", "write:*"]
        assert role.description == "Admin role"
        assert role.inherits == ["viewer"]


# =============================================================================
# Tests: RBACManager - Simple Roles
# =============================================================================


class TestRBACManagerSimpleRoles:
    """Test RBACManager with simple (list) role definitions."""

    def test_load_simple_roles(self, simple_rbac):
        """Simple roles are loaded correctly."""
        assert "super_admin" in simple_rbac.roles
        assert "admin" in simple_rbac.roles
        assert "editor" in simple_rbac.roles
        assert "viewer" in simple_rbac.roles

    def test_simple_role_permissions(self, simple_rbac):
        """Get permissions for a simple role."""
        perms = simple_rbac.get_role_permissions("viewer")
        assert "read:*" in perms

    def test_super_admin_has_all(self, simple_rbac):
        """Super admin with '*' matches everything."""
        assert simple_rbac.has_permission("super_admin", "read:users") is True
        assert simple_rbac.has_permission("super_admin", "delete:everything") is True

    def test_admin_permissions(self, simple_rbac):
        """Admin has specific + wildcard permissions."""
        assert simple_rbac.has_permission("admin", "read:anything") is True
        assert simple_rbac.has_permission("admin", "write:anything") is True
        assert simple_rbac.has_permission("admin", "delete:users") is True
        assert simple_rbac.has_permission("admin", "delete:articles") is False

    def test_viewer_read_only(self, simple_rbac):
        """Viewer can only read."""
        assert simple_rbac.has_permission("viewer", "read:users") is True
        assert simple_rbac.has_permission("viewer", "write:users") is False
        assert simple_rbac.has_permission("viewer", "delete:users") is False

    def test_unknown_role_empty_permissions(self, simple_rbac):
        """Unknown role has no permissions."""
        perms = simple_rbac.get_role_permissions("nonexistent")
        assert len(perms) == 0

    def test_empty_manager(self):
        """Manager with no roles works."""
        rbac = RBACManager()
        assert len(rbac.roles) == 0
        perms = rbac.get_role_permissions("any")
        assert len(perms) == 0


# =============================================================================
# Tests: RBACManager - Hierarchical Roles
# =============================================================================


class TestRBACManagerHierarchicalRoles:
    """Test RBACManager with hierarchical (inherited) role definitions."""

    def test_viewer_base_permissions(self, hierarchical_rbac):
        """Viewer has only its own permissions."""
        perms = hierarchical_rbac.get_role_permissions("viewer")
        assert "read:articles" in perms
        assert "read:comments" in perms
        assert "read:profiles" in perms
        assert len(perms) == 3

    def test_editor_inherits_viewer(self, hierarchical_rbac):
        """Editor has its own + inherited viewer permissions."""
        perms = hierarchical_rbac.get_role_permissions("editor")
        # Own
        assert "write:articles" in perms
        assert "write:comments" in perms
        assert "publish:articles" in perms
        # Inherited from viewer
        assert "read:articles" in perms
        assert "read:comments" in perms
        assert "read:profiles" in perms
        assert len(perms) == 6

    def test_moderator_inherits_viewer(self, hierarchical_rbac):
        """Moderator has its own + inherited viewer permissions."""
        perms = hierarchical_rbac.get_role_permissions("moderator")
        # Own
        assert "moderate:comments" in perms
        assert "flag:content" in perms
        assert "ban:users" in perms
        # Inherited from viewer
        assert "read:articles" in perms
        assert len(perms) == 6

    def test_admin_inherits_editor_and_moderator(self, hierarchical_rbac):
        """Admin has own + editor + moderator (both inherit viewer)."""
        perms = hierarchical_rbac.get_role_permissions("admin")
        # Own
        assert "manage:users" in perms
        assert "manage:roles" in perms
        assert "delete:*" in perms
        assert "view:audit" in perms
        # From editor
        assert "write:articles" in perms
        assert "publish:articles" in perms
        # From moderator
        assert "moderate:comments" in perms
        assert "ban:users" in perms
        # From viewer (transitive)
        assert "read:articles" in perms
        # Total: 4 own + 3 editor + 3 mod + 3 viewer = 13 (viewer deduped)
        assert len(perms) == 13

    def test_transitive_permission_check(self, hierarchical_rbac):
        """Admin can check inherited permissions transitively."""
        # Admin -> editor -> viewer -> read:articles
        assert hierarchical_rbac.has_permission("admin", "read:articles") is True
        # Admin has delete:* from own permissions
        assert hierarchical_rbac.has_permission("admin", "delete:anything") is True

    def test_super_admin_wildcard(self, hierarchical_rbac):
        """Super admin matches everything."""
        assert (
            hierarchical_rbac.has_permission("super_admin", "absolutely:anything")
            is True
        )


# =============================================================================
# Tests: Inheritance Validation
# =============================================================================


class TestInheritanceValidation:
    """Test role inheritance validation (cycles and invalid refs)."""

    def test_direct_cycle(self):
        """Direct cycle (A -> B -> A) is detected."""
        with pytest.raises(ValueError, match="cycle"):
            RBACManager(
                roles={
                    "a": {"permissions": [], "inherits": ["b"]},
                    "b": {"permissions": [], "inherits": ["a"]},
                }
            )

    def test_indirect_cycle(self):
        """Indirect cycle (A -> B -> C -> A) is detected."""
        with pytest.raises(ValueError, match="cycle"):
            RBACManager(
                roles={
                    "a": {"permissions": [], "inherits": ["b"]},
                    "b": {"permissions": [], "inherits": ["c"]},
                    "c": {"permissions": [], "inherits": ["a"]},
                }
            )

    def test_self_cycle(self):
        """Self-referencing role (A -> A) is detected."""
        with pytest.raises(ValueError, match="cycle"):
            RBACManager(
                roles={
                    "a": {"permissions": [], "inherits": ["a"]},
                }
            )

    def test_invalid_inheritance_reference(self):
        """Reference to non-existent role raises ValueError."""
        with pytest.raises(ValueError, match="undefined role"):
            RBACManager(
                roles={
                    "editor": {"permissions": [], "inherits": ["nonexistent"]},
                }
            )

    def test_valid_diamond_inheritance(self):
        """Diamond inheritance (A -> B, A -> C, B -> D, C -> D) is valid."""
        rbac = RBACManager(
            roles={
                "d": {"permissions": ["read:*"], "inherits": []},
                "b": {"permissions": ["write:x"], "inherits": ["d"]},
                "c": {"permissions": ["write:y"], "inherits": ["d"]},
                "a": {"permissions": ["admin:*"], "inherits": ["b", "c"]},
            }
        )
        perms = rbac.get_role_permissions("a")
        assert "admin:*" in perms
        assert "write:x" in perms
        assert "write:y" in perms
        assert "read:*" in perms

    def test_invalid_role_definition_type(self):
        """Non-list/dict role definition raises ValueError."""
        with pytest.raises(ValueError, match="Invalid role definition"):
            RBACManager(roles={"bad": 42})


# =============================================================================
# Tests: Permission Cache
# =============================================================================


class TestPermissionCache:
    """Test permission caching behavior."""

    def test_cache_populated_on_lookup(self, hierarchical_rbac):
        """Cache is populated after first lookup."""
        assert "editor" not in hierarchical_rbac._permission_cache
        hierarchical_rbac.get_role_permissions("editor")
        assert "editor" in hierarchical_rbac._permission_cache

    def test_cache_returns_same_result(self, hierarchical_rbac):
        """Cached result matches fresh computation."""
        perms1 = hierarchical_rbac.get_role_permissions("admin")
        perms2 = hierarchical_rbac.get_role_permissions("admin")
        assert perms1 == perms2

    def test_cache_invalidated_on_add_role(self, simple_rbac):
        """Adding a role clears the cache."""
        simple_rbac.get_role_permissions("viewer")
        assert len(simple_rbac._permission_cache) > 0
        simple_rbac.add_role("new_role", ["test:*"])
        assert len(simple_rbac._permission_cache) == 0

    def test_cache_invalidated_on_remove_role(self, simple_rbac):
        """Removing a role clears the cache."""
        simple_rbac.get_role_permissions("viewer")
        assert len(simple_rbac._permission_cache) > 0
        # viewer isn't inherited by anyone in simple_roles, safe to remove
        simple_rbac.remove_role("viewer")
        assert len(simple_rbac._permission_cache) == 0


# =============================================================================
# Tests: User Permission Resolution
# =============================================================================


class TestUserPermissions:
    """Test user permission resolution from roles + direct permissions."""

    def test_user_role_permissions(self, simple_rbac):
        """User gets permissions from their roles."""
        user = _make_user(roles=["editor"])
        perms = simple_rbac.get_user_permissions(user)
        assert "read:*" in perms
        assert "write:articles" in perms

    def test_user_direct_permissions_merged(self, simple_rbac):
        """User direct permissions are merged with role permissions."""
        user = _make_user(roles=["viewer"], permissions=["special:access"])
        perms = simple_rbac.get_user_permissions(user)
        assert "read:*" in perms
        assert "special:access" in perms

    def test_user_multiple_roles(self, simple_rbac):
        """User with multiple roles gets union of permissions."""
        user = _make_user(roles=["editor", "viewer"])
        perms = simple_rbac.get_user_permissions(user)
        assert "write:articles" in perms
        assert "read:*" in perms

    def test_default_role_for_roleless_user(self):
        """User without roles gets default role permissions."""
        rbac = RBACManager(
            roles={"guest": ["read:public"]},
            default_role="guest",
        )
        user = _make_user(roles=[])
        perms = rbac.get_user_permissions(user)
        assert "read:public" in perms

    def test_no_default_role(self):
        """User without roles and no default gets empty permissions."""
        rbac = RBACManager(roles={"admin": ["*"]})
        user = _make_user(roles=[])
        perms = rbac.get_user_permissions(user)
        assert len(perms) == 0

    def test_has_permission_with_user(self, simple_rbac):
        """has_permission works with AuthenticatedUser objects."""
        user = _make_user(roles=["editor"])
        assert simple_rbac.has_permission(user, "read:users") is True
        assert simple_rbac.has_permission(user, "write:articles") is True
        assert simple_rbac.has_permission(user, "delete:users") is False

    def test_has_role(self, simple_rbac):
        """has_role checks user's role list."""
        user = _make_user(roles=["editor", "viewer"])
        assert simple_rbac.has_role(user, "editor") is True
        assert simple_rbac.has_role(user, "viewer") is True
        assert simple_rbac.has_role(user, "admin") is False

    def test_has_role_any(self, simple_rbac):
        """has_role returns True if user has any of the specified roles."""
        user = _make_user(roles=["viewer"])
        assert simple_rbac.has_role(user, "admin", "viewer") is True
        assert simple_rbac.has_role(user, "admin", "editor") is False


# =============================================================================
# Tests: Role Enforcement (require_role / require_permission)
# =============================================================================


class TestRoleEnforcement:
    """Test require_role and require_permission enforcement."""

    def test_require_permission_success(self, simple_rbac):
        """require_permission passes when user has permission."""
        user = _make_user(roles=["admin"])
        simple_rbac.require_permission(user, "read:users")

    def test_require_permission_failure(self, simple_rbac):
        """require_permission raises InsufficientPermissionError."""
        user = _make_user(roles=["viewer"])
        with pytest.raises(InsufficientPermissionError):
            simple_rbac.require_permission(user, "delete:users")

    def test_require_role_success(self, simple_rbac):
        """require_role passes when user has the role."""
        user = _make_user(roles=["admin"])
        simple_rbac.require_role(user, "admin")

    def test_require_role_failure(self, simple_rbac):
        """require_role raises InsufficientRoleError."""
        user = _make_user(roles=["viewer"])
        with pytest.raises(InsufficientRoleError):
            simple_rbac.require_role(user, "admin")

    def test_require_role_any_match(self, simple_rbac):
        """require_role passes if user has any of the specified roles."""
        user = _make_user(roles=["editor"])
        simple_rbac.require_role(user, "admin", "editor")


# =============================================================================
# Tests: Dynamic Role Management
# =============================================================================


class TestDynamicRoles:
    """Test add_role and remove_role."""

    def test_add_role(self, simple_rbac):
        """Add a new role dynamically."""
        simple_rbac.add_role("moderator", ["moderate:*", "ban:users"])
        assert "moderator" in simple_rbac.roles
        perms = simple_rbac.get_role_permissions("moderator")
        assert "moderate:*" in perms
        assert "ban:users" in perms

    def test_add_role_with_inheritance(self, simple_rbac):
        """Add role that inherits from existing role."""
        simple_rbac.add_role(
            "senior_editor",
            ["publish:*"],
            inherits=["editor"],
        )
        perms = simple_rbac.get_role_permissions("senior_editor")
        assert "publish:*" in perms
        assert "write:articles" in perms  # Inherited from editor

    def test_add_duplicate_role(self, simple_rbac):
        """Adding duplicate role raises ValueError."""
        with pytest.raises(ValueError, match="already exists"):
            simple_rbac.add_role("admin", ["new:perm"])

    def test_add_role_invalid_inheritance(self, simple_rbac):
        """Adding role inheriting from non-existent role raises ValueError."""
        with pytest.raises(ValueError, match="undefined role"):
            simple_rbac.add_role("bad", ["test:*"], inherits=["nonexistent"])

    def test_remove_role(self, simple_rbac):
        """Remove a role."""
        simple_rbac.remove_role("viewer")
        assert "viewer" not in simple_rbac.roles

    def test_remove_nonexistent_role(self, simple_rbac):
        """Removing non-existent role raises ValueError."""
        with pytest.raises(ValueError, match="doesn't exist"):
            simple_rbac.remove_role("nonexistent")

    def test_remove_inherited_role_blocked(self, hierarchical_rbac):
        """Cannot remove a role that others inherit from."""
        with pytest.raises(ValueError, match="inherited by"):
            hierarchical_rbac.remove_role("viewer")


# =============================================================================
# Tests: Statistics
# =============================================================================


class TestRBACStats:
    """Test get_stats method."""

    def test_stats_structure(self, simple_rbac):
        """Stats has expected structure."""
        stats = simple_rbac.get_stats()
        assert "total_roles" in stats
        assert "total_unique_permissions" in stats
        assert "roles" in stats
        assert "default_role" in stats

    def test_stats_counts(self, simple_rbac):
        """Stats reflect actual role count."""
        stats = simple_rbac.get_stats()
        assert stats["total_roles"] == 4

    def test_stats_role_detail(self, hierarchical_rbac):
        """Stats include per-role detail."""
        stats = hierarchical_rbac.get_stats()
        admin_stats = stats["roles"]["admin"]
        assert admin_stats["direct_permissions"] == 4
        assert "editor" in admin_stats["inherited_from"]
        assert "moderator" in admin_stats["inherited_from"]
        assert admin_stats["total_permissions"] == 13


# =============================================================================
# Tests: FastAPI Dependency Factories
# =============================================================================


class TestDependencyFactories:
    """Test require_role_dep and require_permission_dep factory functions."""

    def test_require_role_dep_creates_callable(self):
        """require_role_dep returns a RequireRole instance."""
        from nexus.auth.dependencies import RequireRole

        dep = require_role_dep("admin")
        assert isinstance(dep, RequireRole)

    def test_require_permission_dep_creates_callable(self):
        """require_permission_dep returns a RequirePermission instance."""
        from nexus.auth.dependencies import RequirePermission

        dep = require_permission_dep("write:articles")
        assert isinstance(dep, RequirePermission)

    def test_require_role_dep_multi_roles(self):
        """require_role_dep passes multiple roles through."""
        dep = require_role_dep("admin", "super_admin")
        assert dep.roles == ("admin", "super_admin")

    def test_require_permission_dep_multi_perms(self):
        """require_permission_dep passes multiple permissions through."""
        dep = require_permission_dep("read:users", "write:users")
        assert dep.permissions == ("read:users", "write:users")


# =============================================================================
# Tests: InsufficientPermissionError and InsufficientRoleError
# =============================================================================


class TestExceptionDetails:
    """Test exception detail messages."""

    def test_insufficient_permission_detail(self):
        """InsufficientPermissionError uses generic message (no permission leaking)."""
        err = InsufficientPermissionError("delete:users")
        assert err.detail == "Forbidden"
        assert "delete:users" not in str(err)

    def test_insufficient_role_detail(self):
        """InsufficientRoleError uses generic message (no role leaking)."""
        err = InsufficientRoleError(["admin", "super_admin"])
        assert err.detail == "Forbidden"
        assert "admin" not in err.detail
