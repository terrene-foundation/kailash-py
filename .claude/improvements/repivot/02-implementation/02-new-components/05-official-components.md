# Official Components Detailed Specification

**Purpose:** Detailed specs for the 5 initial official marketplace components

**Priority:** 1 (Critical - Sets marketplace quality standard)
**Estimated Effort:** 200 hours total (40 hours each)
**Timeline:** Weeks 17-22

---

## Component Standards (All Official Components)

### Required Structure

```
kailash-{component}/
├── src/kailash_{component}/
│   ├── __init__.py              # Public API exports
│   ├── manager.py               # Main class (if applicable)
│   ├── workflows/               # Pre-built workflows
│   ├── models/                  # DataFlow models (if applicable)
│   └── nodes/                   # Custom nodes (if applicable)
│
├── examples/
│   ├── basic_usage.py           # Simple example (5 min)
│   ├── advanced_usage.py        # Complex example (30 min)
│   └── integration_example.py  # With other components
│
├── tests/
│   ├── unit/                    # Tier 1 - mocked
│   ├── integration/             # Tier 2 - real infrastructure
│   └── e2e/                     # Tier 3 - complete flows
│
├── docs/
│   ├── quickstart.md           # 5-minute quick start
│   ├── api-reference.md        # Complete API docs
│   ├── integration-guide.md    # How to integrate
│   └── troubleshooting.md      # Common issues
│
├── README.md                    # Overview, installation, quick start
├── CLAUDE.md                   # AI assistant instructions
├── CHANGELOG.md                # Version history
├── LICENSE                      # MIT license
├── pyproject.toml              # Package metadata
└── .github/workflows/          # CI/CD
    ├── tests.yml               # Run tests on PR
    └── publish.yml             # Publish to PyPI on release
```

### Required Features

**All official components MUST:**
1. ✅ Work with Quick Mode (simple API)
2. ✅ Work with Full SDK (advanced usage)
3. ✅ Work with all databases (PostgreSQL, MySQL, SQLite)
4. ✅ Include AI-friendly documentation (CLAUDE.md)
5. ✅ Have 80%+ test coverage
6. ✅ Follow Kailash coding standards
7. ✅ Provide pre-built workflows (not just utilities)
8. ✅ Include working examples

---

## Component 1: kailash-dataflow-utils

**Priority:** Highest (Prevents common errors like 48-hour datetime bug)

### Purpose

Prevent common DataFlow errors through field helpers and validators.

### Public API

```python
# src/kailash_dataflow_utils/__init__.py

from .fields import (
    TimestampField,
    DateField,
    JSONField,
    UUIDField,
    EmailField,
    PhoneField,
    URLField
)

from .validators import (
    EmailValidator,
    PhoneValidator,
    URLValidator,
    PasswordValidator
)

from .mixins import (
    TimestampMixin,
    SoftDeleteMixin,
    AuditMixin
)

__all__ = [
    # Fields
    "TimestampField",
    "DateField",
    "JSONField",
    "UUIDField",
    "EmailField",
    "PhoneField",
    "URLField",
    # Validators
    "EmailValidator",
    "PhoneValidator",
    "URLValidator",
    "PasswordValidator",
    # Mixins
    "TimestampMixin",
    "SoftDeleteMixin",
    "AuditMixin",
]
```

### Implementation: TimestampField

```python
# src/kailash_dataflow_utils/fields.py

from datetime import datetime, timezone
from typing import Any, Optional

class TimestampField:
    """Helper for datetime fields - prevents isoformat() errors.

    Common mistake:
        created_at: datetime.now().isoformat()  # ❌ Returns string

    Correct:
        created_at: TimestampField.now()  # ✅ Returns datetime
    """

    @staticmethod
    def now() -> datetime:
        """Return current UTC datetime (not string).

        Returns:
            datetime: Current datetime with UTC timezone
        """
        return datetime.now(timezone.utc)

    @staticmethod
    def from_timestamp(timestamp: float) -> datetime:
        """Convert Unix timestamp to datetime.

        Args:
            timestamp: Unix timestamp (seconds since epoch)

        Returns:
            datetime: Datetime object

        Example:
            dt = TimestampField.from_timestamp(1705456789)
        """
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)

    @staticmethod
    def from_iso(iso_string: str) -> datetime:
        """Parse ISO format string to datetime.

        Args:
            iso_string: ISO 8601 format string

        Returns:
            datetime: Parsed datetime

        Example:
            dt = TimestampField.from_iso("2025-01-15T10:30:00Z")
        """
        return datetime.fromisoformat(iso_string.replace('Z', '+00:00'))

    @staticmethod
    def validate(value: Any) -> datetime:
        """Validate and convert to datetime.

        Args:
            value: Value to validate (datetime, str, int, float)

        Returns:
            datetime: Validated datetime object

        Raises:
            ValueError: If value cannot be converted

        Example:
            dt = TimestampField.validate("2025-01-15T10:30:00")
            dt = TimestampField.validate(1705456789)
            dt = TimestampField.validate(datetime.now())
        """
        if isinstance(value, datetime):
            return value
        elif isinstance(value, str):
            return TimestampField.from_iso(value)
        elif isinstance(value, (int, float)):
            return TimestampField.from_timestamp(value)
        else:
            raise ValueError(
                f"Expected datetime, string, or number. Got {type(value).__name__}. "
                f"Did you use .isoformat()? Use TimestampField.now() instead."
            )
```

### Implementation: JSONField

```python
class JSONField:
    """Helper for JSON fields - handles serialization.

    Common mistake:
        metadata: json.dumps(data)  # ❌ DataFlow handles serialization

    Correct:
        metadata: data  # ✅ Pass dict directly
        # OR:
        metadata: JSONField.validate(data)  # Explicit validation
    """

    @staticmethod
    def dumps(data: dict) -> str:
        """Serialize to JSON string (rarely needed).

        Note: DataFlow handles JSON serialization automatically.
        Only use if you need explicit JSON string.
        """
        import json
        return json.dumps(data)

    @staticmethod
    def loads(json_string: str) -> dict:
        """Deserialize from JSON string."""
        import json
        return json.loads(json_string)

    @staticmethod
    def validate(value: Any) -> dict:
        """Validate and convert to dict.

        Args:
            value: Value to validate (dict or JSON string)

        Returns:
            dict: Validated dictionary

        Raises:
            ValueError: If value is not valid JSON

        Example:
            data = JSONField.validate({"key": "value"})
            data = JSONField.validate('{"key": "value"}')
        """
        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            import json
            try:
                return json.loads(value)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON: {e}")
        else:
            raise ValueError(
                f"Expected dict or JSON string. Got {type(value).__name__}. "
                f"Did you use json.dumps()? Pass dict directly to DataFlow."
            )
```

### Implementation: UUIDField

```python
class UUIDField:
    """Helper for UUID fields - ensures correct format."""

    @staticmethod
    def generate() -> str:
        """Generate new UUID string.

        Returns:
            str: UUID in standard format (lowercase with hyphens)

        Example:
            id = UUIDField.generate()  # "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d"
        """
        import uuid
        return str(uuid.uuid4())

    @staticmethod
    def validate(value: Any) -> str:
        """Validate UUID format.

        Args:
            value: Value to validate (string or UUID object)

        Returns:
            str: Validated UUID string

        Raises:
            ValueError: If value is not valid UUID

        Example:
            id = UUIDField.validate("a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d")
        """
        import uuid

        if isinstance(value, uuid.UUID):
            return str(value)
        elif isinstance(value, str):
            try:
                # Validate format
                uuid.UUID(value)
                return value.lower()  # Normalize to lowercase
            except ValueError:
                raise ValueError(
                    f"Invalid UUID format: {value}. "
                    f"Use UUIDField.generate() to create valid UUID."
                )
        else:
            raise ValueError(f"Expected UUID or string. Got {type(value).__name__}")
```

### Implementation: Mixins

```python
# src/kailash_dataflow_utils/mixins.py

from datetime import datetime
from typing import Optional

class TimestampMixin:
    """Add timestamp fields to models.

    Usage:
        @db.model
        class User(TimestampMixin):
            name: str
            # created_at, updated_at added automatically
    """
    created_at: datetime
    updated_at: datetime

class SoftDeleteMixin:
    """Add soft delete capability.

    Usage:
        @db.model
        class User(SoftDeleteMixin):
            name: str
            # deleted_at added automatically
            # Queries automatically filter out deleted records
    """
    deleted_at: Optional[datetime] = None
    is_deleted: bool = False

class AuditMixin:
    """Add audit fields for tracking changes.

    Usage:
        @db.model
        class User(AuditMixin):
            name: str
            # created_by, updated_by, deleted_by added automatically
    """
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    deleted_by: Optional[str] = None
```

### Usage Example

```python
from kailash_dataflow_utils import (
    TimestampField,
    UUIDField,
    JSONField,
    TimestampMixin,
    SoftDeleteMixin
)
from dataflow import DataFlow

db = DataFlow("postgresql://...")

@db.model
class User(TimestampMixin, SoftDeleteMixin):
    """User model with timestamp and soft delete."""
    id: str
    name: str
    email: str
    preferences: dict  # JSON field

# In workflow
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": UUIDField.generate(),  # ✅ Valid UUID
    "name": "Alice",
    "email": "alice@example.com",
    "preferences": {"theme": "dark", "lang": "en"},  # ✅ Dict, not json.dumps()
    # created_at added automatically by TimestampMixin
    # is_deleted defaults to False from SoftDeleteMixin
})
```

**Testing:**
```python
# tests/integration/test_dataflow_utils.py

def test_timestamp_field_prevents_isoformat_error():
    """Validate that TimestampField prevents common datetime error."""

    # This should work (datetime object)
    dt = TimestampField.now()
    assert isinstance(dt, datetime)

    # This should raise helpful error (string)
    with pytest.raises(ValueError, match="Did you use .isoformat()"):
        TimestampField.validate(datetime.now().isoformat())

def test_uuid_field_generates_valid_uuid():
    """Validate that UUIDField generates valid UUIDs."""
    import uuid

    uid = UUIDField.generate()
    assert isinstance(uid, str)

    # Should be valid UUID
    parsed = uuid.UUID(uid)
    assert str(parsed) == uid
```

**Estimated effort:** 40 hours
- Fields implementation: 10 hours
- Validators: 8 hours
- Mixins: 6 hours
- Tests: 10 hours
- Documentation: 6 hours

---

## Component 2: kailash-sso

**Priority:** High (Most requested feature)

### Purpose

Complete authentication solution - OAuth2, SAML, JWT.

### Public API

```python
# src/kailash_sso/__init__.py

from .manager import SSOManager
from .providers import OAuth2Provider, SAMLProvider, JWTProvider
from .workflows import login_workflow, register_workflow, logout_workflow
from .middleware import AuthMiddleware

__all__ = [
    "SSOManager",
    "OAuth2Provider",
    "SAMLProvider",
    "JWTProvider",
    "login_workflow",
    "register_workflow",
    "logout_workflow",
    "AuthMiddleware",
]
```

### Core Implementation

```python
# src/kailash_sso/manager.py

from typing import Dict, List, Optional
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow import Workflow

class SSOManager:
    """Manage authentication and SSO."""

    def __init__(
        self,
        providers: Dict[str, Dict],
        jwt_secret: str,
        token_expiry: int = 86400,  # 24 hours
        refresh_enabled: bool = True,
        mfa_enabled: bool = False
    ):
        """Initialize SSO manager.

        Args:
            providers: OAuth2/SAML provider configurations
                {
                    "google": {"client_id": "...", "client_secret": "..."},
                    "github": {"client_id": "...", "client_secret": "..."},
                    "saml": {"metadata_url": "..."}
                }
            jwt_secret: Secret for signing JWT tokens
            token_expiry: Token expiration in seconds
            refresh_enabled: Enable refresh tokens
            mfa_enabled: Enable multi-factor authentication
        """
        self.providers = providers
        self.jwt_secret = jwt_secret
        self.token_expiry = token_expiry
        self.refresh_enabled = refresh_enabled
        self.mfa_enabled = mfa_enabled

        # Initialize providers
        self._oauth2_providers = self._init_oauth2_providers()
        self._saml_provider = self._init_saml_provider() if "saml" in providers else None

    def login_workflow(self) -> Workflow:
        """Pre-built login workflow.

        Supports:
        - Email/password authentication
        - OAuth2 providers (Google, GitHub, etc.)
        - SAML authentication

        Inputs:
            - email: str
            - password: str (for email/password)
            - provider: str (for OAuth2/SAML, e.g., "google", "saml")
            - oauth_code: str (for OAuth2 callback)

        Returns workflow that produces:
            - access_token: str (JWT)
            - refresh_token: str (if refresh_enabled)
            - user: dict (user information)
            - expires_at: datetime
        """
        workflow = WorkflowBuilder()

        # Step 1: Determine auth method
        workflow.add_node("SwitchNode", "auth_method", {
            "condition": "inputs.get('provider') is not None",
            "true_branch": "oauth_login",
            "false_branch": "password_login"
        })

        # Path A: Password authentication
        workflow.add_node("UserListNode", "find_user", {
            "filters": {"email": "{{ email }}"},
            "limit": 1
        })

        workflow.add_node("PythonCodeNode", "verify_password", {
            "code": self._get_password_verification_code(),
            "inputs": {
                "user": "{{ find_user }}",
                "password": "{{ password }}"
            }
        })

        # Path B: OAuth2 authentication
        workflow.add_node("HTTPRequestNode", "oauth_exchange", {
            "url": "{{ oauth_token_url }}",
            "method": "POST",
            "body": {
                "code": "{{ oauth_code }}",
                "client_id": "{{ client_id }}",
                "client_secret": "{{ client_secret }}",
                "redirect_uri": "{{ redirect_uri }}",
                "grant_type": "authorization_code"
            }
        })

        workflow.add_node("HTTPRequestNode", "oauth_userinfo", {
            "url": "{{ userinfo_url }}",
            "method": "GET",
            "headers": {
                "Authorization": "Bearer {{ oauth_exchange.access_token }}"
            }
        })

        workflow.add_node("PythonCodeNode", "get_or_create_user", {
            "code": self._get_oauth_user_code(),
            "inputs": {"userinfo": "{{ oauth_userinfo }}"}
        })

        # Common: Generate JWT
        workflow.add_node("JWTGenerateNode", "generate_token", {
            "payload": {
                "user_id": "{{ user.id }}",
                "email": "{{ user.email }}",
                "name": "{{ user.name }}"
            },
            "secret": self.jwt_secret,
            "expires_in": self.token_expiry
        })

        # Connections
        workflow.add_connection("auth_method", "password_login", "output", "input")
        workflow.add_connection("auth_method", "oauth_login", "output", "input")
        # ... (more connections)

        return workflow.build()

    def register_workflow(self) -> Workflow:
        """Pre-built registration workflow."""
        # Implementation for user registration
        pass

    def logout_workflow(self) -> Workflow:
        """Pre-built logout workflow."""
        # Implementation for logout (invalidate session)
        pass

    def refresh_token_workflow(self) -> Workflow:
        """Refresh access token using refresh token."""
        # Implementation for token refresh
        pass

    # Helper methods
    def _init_oauth2_providers(self):
        """Initialize OAuth2 providers from config."""
        pass

    def _get_password_verification_code(self) -> str:
        """Generate code for password verification."""
        return """
import hashlib

users = inputs['user']
if not users:
    return {'valid': False, 'error': 'User not found'}

user = users[0]
provided_hash = hashlib.sha256(inputs['password'].encode()).hexdigest()

if provided_hash == user['hashed_password']:
    return {'valid': True, 'user': user}
else:
    return {'valid': False, 'error': 'Invalid password'}
        """
```

### Usage Examples

**Quick Mode:**
```python
from kailash.quick import app, db
from kailash_sso import SSOManager

sso = SSOManager(
    providers={
        "google": {
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET")
        }
    },
    jwt_secret=os.getenv("JWT_SECRET")
)

# Register workflows
app.register_workflow("login", sso.login_workflow())
app.register_workflow("register", sso.register_workflow())

app.run()
```

**Full SDK:**
```python
from kailash_sso import SSOManager
from nexus import Nexus

sso = SSOManager(
    providers={
        "google": {...},
        "github": {...},
        "saml": {"metadata_url": "..."}
    },
    jwt_secret="secret",
    mfa_enabled=True  # Enable MFA
)

nexus = Nexus(enable_auth=True)
nexus.register("login", sso.login_workflow())
nexus.register("register", sso.register_workflow())
nexus.register("logout", sso.logout_workflow())
nexus.register("refresh", sso.refresh_token_workflow())
```

**Testing:**
```python
# tests/integration/test_oauth2_flow.py

def test_google_oauth2_login():
    """Test Google OAuth2 login flow."""
    from kailash_sso import SSOManager
    from kailash.runtime.local import LocalRuntime

    sso = SSOManager(
        providers={
            "google": {
                "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                "redirect_uri": "http://localhost:8000/callback"
            }
        },
        jwt_secret="test-secret"
    )

    workflow = sso.login_workflow()

    # Note: Requires OAuth2 mock server or manual testing
    # See tests/integration/oauth2_mock_server.py
    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow, inputs={
        "provider": "google",
        "oauth_code": "test-auth-code"  # From OAuth2 flow
    })

    assert "access_token" in results
    assert "user" in results
```

**Estimated effort:** 40 hours

---

## Component 3: kailash-rbac

### Purpose

Role-Based Access Control for multi-user applications.

### Public API

```python
# src/kailash_rbac/__init__.py

from .manager import RBACManager
from .models import Role, Permission, UserRole
from .middleware import RBACMiddleware
from .nodes import RBACCheckNode

__all__ = [
    "RBACManager",
    "Role",
    "Permission",
    "UserRole",
    "RBACMiddleware",
    "RBACCheckNode",
]
```

### Core Implementation

```python
# src/kailash_rbac/manager.py

from dataflow import DataFlow
from typing import List, Dict, Optional

class RBACManager:
    """Manage roles and permissions."""

    def __init__(
        self,
        db: DataFlow,
        roles: Optional[Dict[str, List[str]]] = None,
        resource_types: Optional[List[str]] = None
    ):
        """Initialize RBAC manager.

        Args:
            db: DataFlow instance (for storing roles/permissions)
            roles: Predefined roles
                {
                    "admin": ["*"],  # All permissions
                    "user": ["read:own", "update:own"],
                    "viewer": ["read:*"]
                }
            resource_types: Resource types to manage
                ["users", "products", "orders"]
        """
        self.db = db
        self.roles = roles or {}
        self.resource_types = resource_types or []

        # Register RBAC models with DataFlow
        self._register_models()

        # Initialize default roles if provided
        if roles:
            self._initialize_default_roles()

    def _register_models(self):
        """Register Role and Permission models."""

        @self.db.model
        class Role:
            id: str
            name: str
            description: str
            permissions: list  # JSON field: ["read:users", "write:products"]

        @self.db.model
        class UserRole:
            id: str
            user_id: str
            role_id: str

    def check_permission_workflow(self) -> 'Workflow':
        """Workflow to check if user has permission.

        Inputs:
            - user_id: str
            - permission: str (e.g., "read:users")
            - resource_id: str (optional, for resource-level checks)

        Returns:
            - authorized: bool
            - roles: list (user's roles)
        """
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()

        # Get user roles
        workflow.add_node("UserRoleListNode", "get_user_roles", {
            "filters": {"user_id": "{{ user_id }}"}
        })

        # Get role permissions
        workflow.add_node("PythonCodeNode", "check_permissions", {
            "code": """
user_roles = inputs['get_user_roles']
required_permission = inputs['permission']

# Get all role IDs
role_ids = [ur['role_id'] for ur in user_roles]

# Query roles to get permissions
# ... (check if any role has required permission)

return {'authorized': has_permission, 'roles': user_roles}
            """,
            "inputs": {
                "get_user_roles": "{{ get_user_roles }}",
                "permission": "{{ permission }}"
            }
        })

        workflow.add_connection("get_user_roles", "check_permissions", "output", "input")

        return workflow.build()

    def assign_role_workflow(self) -> 'Workflow':
        """Workflow to assign role to user."""
        # Implementation
        pass

    def revoke_role_workflow(self) -> 'Workflow':
        """Workflow to revoke role from user."""
        # Implementation
        pass

    # Convenience methods (execute workflows internally)
    def has_permission(self, user_id: str, permission: str, resource_id: str = None) -> bool:
        """Check if user has permission.

        This is a convenience method that executes the workflow internally.
        For use in custom workflows, use check_permission_workflow() instead.
        """
        from kailash.runtime.local import LocalRuntime

        workflow = self.check_permission_workflow()
        runtime = LocalRuntime()

        results, _ = runtime.execute(workflow, inputs={
            "user_id": user_id,
            "permission": permission,
            "resource_id": resource_id
        })

        return results.get("check_permissions", {}).get("authorized", False)

    def assign_role(self, user_id: str, role: str):
        """Assign role to user (convenience method)."""
        # Execute assign_role_workflow internally
        pass
```

### Custom Node: RBACCheckNode

```python
# src/kailash_rbac/nodes.py

from kailash.nodes.base import BaseNode

class RBACCheckNode(BaseNode):
    """Node for checking permissions in workflows.

    Usage:
        workflow.add_node("RBACCheckNode", "authorize", {
            "user_id": "{{ current_user_id }}",
            "permission": "delete:users",
            "resource_id": "{{ target_user_id }}"
        })

    Raises:
        PermissionError if user doesn't have permission
    """

    def __init__(self, rbac_manager: 'RBACManager'):
        super().__init__()
        self.rbac = rbac_manager

    def execute(self, params: dict) -> dict:
        user_id = params["user_id"]
        permission = params["permission"]
        resource_id = params.get("resource_id")

        authorized = self.rbac.has_permission(user_id, permission, resource_id)

        if not authorized:
            raise PermissionError(
                f"User {user_id} does not have permission: {permission}"
            )

        return {"authorized": True, "user_id": user_id}
```

### Usage Example

```python
from kailash_rbac import RBACManager
from kailash_sso import SSOManager
from dataflow import DataFlow
from nexus import Nexus

# Initialize
db = DataFlow("postgresql://...")

# Setup RBAC
rbac = RBACManager(
    db=db,
    roles={
        "admin": ["*"],
        "editor": ["read:*", "write:own"],
        "viewer": ["read:*"]
    }
)

# Setup SSO
sso = SSOManager(
    providers={"google": {...}},
    jwt_secret="secret"
)

# Protected workflow example
def delete_user_workflow():
    workflow = WorkflowBuilder()

    # Step 1: Check permission
    workflow.add_node("RBACCheckNode", "authorize", {
        "user_id": "{{ current_user_id }}",
        "permission": "delete:users"
    })

    # Step 2: Delete user (only if authorized)
    workflow.add_node("UserDeleteNode", "delete", {
        "id": "{{ target_user_id }}"
    })

    workflow.add_connection("authorize", "delete", "output", "input")

    return workflow.build()

# Register
nexus = Nexus(enable_auth=True)
nexus.register("login", sso.login_workflow())
nexus.register("delete_user", delete_user_workflow())
```

**Estimated effort:** 40 hours

---

## Component 4: kailash-admin

### Purpose

Auto-generated admin dashboard for DataFlow models.

### Public API

```python
# src/kailash_admin/__init__.py

from .dashboard import AdminDashboard
from .ui import AdminUI
from .widgets import TableWidget, FormWidget, ChartWidget

__all__ = [
    "AdminDashboard",
    "AdminUI",
    "TableWidget",
    "FormWidget",
    "ChartWidget",
]
```

### Implementation

```python
# src/kailash_admin/dashboard.py

from dataflow import DataFlow
from typing import List, Optional

class AdminDashboard:
    """Auto-generated admin dashboard for DataFlow models."""

    def __init__(
        self,
        db: DataFlow,
        models: List[str],
        auth_required: bool = True,
        title: str = "Admin Dashboard"
    ):
        """Initialize admin dashboard.

        Args:
            db: DataFlow instance
            models: List of model names to include
            auth_required: Require authentication
            title: Dashboard title
        """
        self.db = db
        self.models = models
        self.auth_required = auth_required
        self.title = title

        # Generate UI for each model
        self._ui_components = self._generate_ui()

    def register_with_nexus(self, nexus: 'Nexus'):
        """Register admin endpoints with Nexus.

        Creates:
            - GET /admin - Dashboard home
            - GET /admin/{model} - Model list view
            - GET /admin/{model}/create - Create form
            - GET /admin/{model}/{id} - Detail view
            - POST /admin/{model}/{id}/edit - Edit form
            - POST /admin/{model}/{id}/delete - Delete action
        """
        # Register workflows for each model
        for model_name in self.models:
            # List view workflow
            list_workflow = self._create_list_workflow(model_name)
            nexus.register(f"admin_list_{model_name.lower()}", list_workflow)

            # Create workflow
            create_workflow = self._create_create_workflow(model_name)
            nexus.register(f"admin_create_{model_name.lower()}", create_workflow)

            # Update workflow
            update_workflow = self._create_update_workflow(model_name)
            nexus.register(f"admin_update_{model_name.lower()}", update_workflow)

            # Delete workflow
            delete_workflow = self._create_delete_workflow(model_name)
            nexus.register(f"admin_delete_{model_name.lower()}", delete_workflow)

        # Register UI routes (serve React/Vue app)
        nexus.endpoint("/admin")(self._serve_admin_ui)
        nexus.endpoint("/admin/{model}")(self._serve_model_ui)

    def _create_list_workflow(self, model_name: str):
        """Create workflow for model list view."""
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()

        # List all records
        workflow.add_node(f"{model_name}ListNode", "list", {
            "filters": {},
            "limit": 100,
            "offset": "{{ offset }}",
            "order_by": "created_at DESC"
        })

        # Get total count
        workflow.add_node("PythonCodeNode", "count", {
            "code": f"""
from dataflow import DataFlow
db = DataFlow()
# Count total records
return {{'total': len(inputs['list'])}}
            """,
            "inputs": {"list": "{{ list }}"}
        })

        workflow.add_connection("list", "count", "output", "input")

        return workflow.build()

    # Similar for create, update, delete workflows
```

### UI Components

**Frontend (React):**
```
src/kailash_admin/ui/
├── components/
│   ├── Dashboard.tsx        # Main dashboard
│   ├── ModelTable.tsx       # Table view
│   ├── ModelForm.tsx        # Create/edit form
│   └── ModelDetail.tsx      # Detail view
│
├── App.tsx                  # React app entry
└── api.ts                   # API client
```

**API client:**
```typescript
// src/kailash_admin/ui/api.ts

export class AdminAPI {
  constructor(private baseURL: string = 'http://localhost:8000') {}

  async listModel(modelName: string, page: number = 1) {
    const response = await fetch(
      `${this.baseURL}/workflows/admin_list_${modelName.toLowerCase()}/execute`,
      {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({offset: (page - 1) * 100})
      }
    );
    return response.json();
  }

  async createRecord(modelName: string, data: any) {
    const response = await fetch(
      `${this.baseURL}/workflows/admin_create_${modelName.toLowerCase()}/execute`,
      {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
      }
    );
    return response.json();
  }
}
```

**Value:**
- 20+ hours of React development → 5 minutes of configuration
- Responsive UI (mobile-friendly)
- Customizable (override components)
- Integrates with RBAC (permission-based UI)

**Estimated effort:** 40 hours
- Backend workflows: 10 hours
- React UI: 20 hours
- Integration: 5 hours
- Testing: 5 hours

---

## Component 5: kailash-payments

### Purpose

Payment processing with Stripe and PayPal.

### Public API

```python
# src/kailash_payments/__init__.py

from .manager import PaymentManager
from .providers import StripeProvider, PayPalProvider
from .models import Payment, Subscription, Refund

__all__ = [
    "PaymentManager",
    "StripeProvider",
    "PayPalProvider",
    "Payment",
    "Subscription",
    "Refund",
]
```

### Core Implementation

```python
# src/kailash_payments/manager.py

from kailash.workflow.builder import WorkflowBuilder
from dataflow import DataFlow

class PaymentManager:
    """Manage payment processing."""

    def __init__(
        self,
        db: DataFlow,
        providers: Dict[str, Dict],
        default_currency: str = "usd"
    ):
        """Initialize payment manager.

        Args:
            db: DataFlow instance for storing payment records
            providers: Payment provider configurations
                {
                    "stripe": {
                        "api_key": "sk_...",
                        "webhook_secret": "whsec_..."
                    },
                    "paypal": {
                        "client_id": "...",
                        "client_secret": "..."
                    }
                }
            default_currency: Default currency (ISO 4217 code)
        """
        self.db = db
        self.providers = providers
        self.default_currency = default_currency

        # Register payment models
        self._register_models()

    def _register_models(self):
        """Register payment-related models."""

        @self.db.model
        class Payment:
            id: str
            user_id: str
            amount: float
            currency: str
            status: str  # pending, completed, failed, refunded
            provider: str  # stripe, paypal
            provider_payment_id: str
            metadata: dict

        @self.db.model
        class Subscription:
            id: str
            user_id: str
            plan: str
            status: str  # active, cancelled, past_due
            current_period_end: datetime
            provider_subscription_id: str

        @self.db.model
        class Refund:
            id: str
            payment_id: str
            amount: float
            reason: str
            status: str

    def charge_workflow(self) -> 'Workflow':
        """Create workflow for charging a payment.

        Inputs:
            - user_id: str
            - amount: float
            - currency: str (default: usd)
            - payment_method: str (Stripe payment method ID)
            - description: str

        Returns:
            - payment: dict (Payment record)
            - stripe_response: dict (Stripe API response)
        """
        workflow = WorkflowBuilder()

        # Step 1: Create payment record (pending)
        workflow.add_node("PaymentCreateNode", "create_payment", {
            "id": UUIDField.generate(),
            "user_id": "{{ user_id }}",
            "amount": "{{ amount }}",
            "currency": "{{ currency }}",
            "status": "pending",
            "provider": "stripe"
        })

        # Step 2: Charge via Stripe
        workflow.add_node("HTTPRequestNode", "stripe_charge", {
            "url": "https://api.stripe.com/v1/payment_intents",
            "method": "POST",
            "headers": {
                "Authorization": f"Bearer {self.providers['stripe']['api_key']}",
                "Content-Type": "application/x-www-form-urlencoded"
            },
            "body": {
                "amount": "{{ amount * 100 }}",  # Cents
                "currency": "{{ currency }}",
                "payment_method": "{{ payment_method }}",
                "confirm": "true",
                "description": "{{ description }}"
            }
        })

        # Step 3: Update payment status
        workflow.add_node("SwitchNode", "check_status", {
            "condition": "inputs['stripe_charge']['status'] == 'succeeded'",
            "true_branch": "mark_completed",
            "false_branch": "mark_failed"
        })

        workflow.add_node("PaymentUpdateNode", "mark_completed", {
            "filter": {"id": "{{ create_payment.id }}"},
            "fields": {
                "status": "completed",
                "provider_payment_id": "{{ stripe_charge.id }}"
            }
        })

        workflow.add_node("PaymentUpdateNode", "mark_failed", {
            "filter": {"id": "{{ create_payment.id }}"},
            "fields": {
                "status": "failed",
                "metadata": {"error": "{{ stripe_charge.error }}"}
            }
        })

        # Error handler: Mark as failed on exception
        workflow.add_error_handler("stripe_charge", "handle_error")

        workflow.add_node("PaymentUpdateNode", "handle_error", {
            "filter": {"id": "{{ create_payment.id }}"},
            "fields": {
                "status": "failed",
                "metadata": {"error": "{{ error }}"}
            }
        })

        # Connections
        workflow.add_connection("create_payment", "stripe_charge", "output", "input")
        workflow.add_connection("stripe_charge", "check_status", "output", "input")

        return workflow.build()

    def refund_workflow(self) -> 'Workflow':
        """Create refund workflow."""
        # Implementation
        pass

    def create_subscription_workflow(self) -> 'Workflow':
        """Create subscription workflow."""
        # Implementation
        pass

    def webhook_handler_workflow(self) -> 'Workflow':
        """Handle Stripe/PayPal webhooks."""
        # Implementation for processing webhook events
        pass
```

### Usage Example

```python
from kailash_payments import PaymentManager
from kailash_sso import SSOManager
from dataflow import DataFlow
from nexus import Nexus

db = DataFlow("postgresql://...")

# Setup payments
payments = PaymentManager(
    db=db,
    providers={
        "stripe": {
            "api_key": os.getenv("STRIPE_API_KEY"),
            "webhook_secret": os.getenv("STRIPE_WEBHOOK_SECRET")
        }
    }
)

# Setup auth
sso = SSOManager(...)

# Register workflows
nexus = Nexus()
nexus.register("login", sso.login_workflow())
nexus.register("charge_payment", payments.charge_workflow())
nexus.register("process_refund", payments.refund_workflow())
nexus.register("stripe_webhook", payments.webhook_handler_workflow())

# Protected payment endpoint
from kailash_rbac import RBACManager

rbac = RBACManager(db=db)

def protected_charge_workflow():
    workflow = WorkflowBuilder()

    # Authorize
    workflow.add_node("RBACCheckNode", "authorize", {
        "user_id": "{{ user_id }}",
        "permission": "charge:payments"
    })

    # Charge (only if authorized)
    workflow.add_node("SubWorkflowNode", "charge", {
        "workflow": payments.charge_workflow(),
        "inputs": {
            "user_id": "{{ user_id }}",
            "amount": "{{ amount }}"
        }
    })

    workflow.add_connection("authorize", "charge", "output", "input")

    return workflow.build()

nexus.register("protected_charge", protected_charge_workflow())
```

**Estimated effort:** 40 hours

---

## Component Integration Matrix

**How components work together:**

| Component | Uses | Used By | Integration Points |
|-----------|------|---------|-------------------|
| **kailash-dataflow-utils** | DataFlow | All components | Field helpers, validators |
| **kailash-sso** | DataFlow (user models), JWT | RBAC, Admin | User authentication |
| **kailash-rbac** | DataFlow (role models), SSO | Admin, Payments | Authorization |
| **kailash-admin** | DataFlow (all models), RBAC | - | UI for data management |
| **kailash-payments** | DataFlow (payment models), SSO | Admin | Payment processing |

**Example: Complete SaaS Stack**
```python
# Install all components
pip install kailash-dataflow-utils kailash-sso kailash-rbac kailash-admin kailash-payments

from dataflow import DataFlow
from nexus import Nexus
from kailash_dataflow_utils import UUIDField, TimestampField
from kailash_sso import SSOManager
from kailash_rbac import RBACManager
from kailash_admin import AdminDashboard
from kailash_payments import PaymentManager

# Initialize
db = DataFlow("postgresql://...", multi_tenant=True)

# Component stack
sso = SSOManager(providers={"google": {...}}, jwt_secret="...")
rbac = RBACManager(db=db, roles={"admin": ["*"], "user": ["read:own"]})
admin = AdminDashboard(db=db, models=["User", "Organization", "Payment"])
payments = PaymentManager(db=db, providers={"stripe": {...}})

# Deploy
nexus = Nexus(enable_auth=True)

# Auth workflows
nexus.register("login", sso.login_workflow())
nexus.register("register", sso.register_workflow())

# Payment workflows
nexus.register("charge", payments.charge_workflow())
nexus.register("refund", payments.refund_workflow())

# Admin UI
admin.register_with_nexus(nexus)

# Start
nexus.start()

# ✅ Complete SaaS backend in 50 lines
# ✅ Auth, RBAC, payments, admin all working
# ✅ Multi-tenant, production-ready
# ✅ Would have taken 2+ weeks to build from scratch
```

---

## Component Testing

### Tier 1: Unit Tests (Mocked)

```python
# packages/kailash-sso/tests/unit/test_sso_manager.py

def test_sso_manager_initialization():
    """Test SSOManager initializes correctly."""
    from kailash_sso import SSOManager

    sso = SSOManager(
        providers={"google": {"client_id": "test", "client_secret": "test"}},
        jwt_secret="test-secret"
    )

    assert sso.jwt_secret == "test-secret"
    assert "google" in sso.providers

def test_login_workflow_structure():
    """Test that login workflow has correct structure."""
    from kailash_sso import SSOManager

    sso = SSOManager(providers={}, jwt_secret="test")
    workflow = sso.login_workflow()

    # Validate workflow structure
    assert len(workflow.nodes) > 0
    assert any(node.node_class == "SwitchNode" for node in workflow.nodes)
```

### Tier 2: Integration Tests (Real Infrastructure)

```python
# packages/kailash-sso/tests/integration/test_jwt_integration.py

def test_jwt_token_generation_and_validation():
    """Test JWT token generation with real JWT library."""
    from kailash_sso import SSOManager
    from kailash.runtime.local import LocalRuntime
    import jwt

    sso = SSOManager(providers={}, jwt_secret="test-secret-123")

    # Execute token generation workflow
    workflow = sso.login_workflow()
    runtime = LocalRuntime()

    results, _ = runtime.execute(workflow, inputs={
        "email": "test@example.com",
        "password": "testpass123"
    })

    # Validate token
    token = results.get("generate_token", {}).get("token")
    assert token is not None

    # Decode and verify
    decoded = jwt.decode(token, "test-secret-123", algorithms=["HS256"])
    assert decoded["email"] == "test@example.com"
```

### Tier 3: E2E Tests (Complete Flows)

```python
# packages/kailash-sso/tests/e2e/test_oauth2_e2e.py

def test_complete_oauth2_flow():
    """Test complete OAuth2 flow with real Google OAuth."""

    # This requires:
    # 1. OAuth2 mock server OR real credentials
    # 2. Complete flow: initiate → redirect → callback → token
    # 3. User creation in database
    # 4. Session management

    # Skip in CI (requires manual setup)
    pytest.skip("E2E test requires OAuth2 credentials")
```

---

## Component Documentation

### README.md Template

```markdown
# kailash-sso

OAuth2, SAML, and JWT authentication for Kailash applications.

## Features

- OAuth2 providers (Google, GitHub, Microsoft, etc.)
- SAML enterprise SSO
- JWT token management
- Session management
- Multi-factor authentication (MFA)
- Refresh tokens

## Installation

```bash
pip install kailash-sso
```

## Quick Start (5 minutes)

```python
from kailash_sso import SSOManager
from nexus import Nexus

# Configure SSO
sso = SSOManager(
    providers={
        "google": {
            "client_id": "YOUR_GOOGLE_CLIENT_ID",
            "client_secret": "YOUR_GOOGLE_CLIENT_SECRET"
        }
    },
    jwt_secret="your-secret-key"
)

# Get workflows
login = sso.login_workflow()
register = sso.register_workflow()

# Deploy
nexus = Nexus()
nexus.register("login", login)
nexus.register("register", register)
nexus.start()
```

Now available:
- `POST /workflows/login` - Email/password or OAuth2
- `POST /workflows/register` - User registration
- `GET /auth/google` - Google OAuth2 initiate (auto-generated)

## Documentation

- [Quick Start Guide](docs/quickstart.md)
- [OAuth2 Guide](docs/oauth2-guide.md)
- [SAML Guide](docs/saml-guide.md)
- [API Reference](docs/api-reference.md)
- [Migration Guide](docs/migration.md)

## Examples

See `examples/` directory:
- `oauth2_basic.py` - Simple OAuth2 setup
- `saml_enterprise.py` - Enterprise SAML configuration
- `mfa_enabled.py` - Multi-factor authentication
- `complete_saas.py` - Complete SaaS auth system

## Compatibility

- Python: 3.10+
- Kailash SDK: 0.9.27+
- Databases: PostgreSQL, MySQL, SQLite

## License

MIT - See LICENSE file

## Support

- Issues: https://github.com/kailash-sdk/kailash-sso/issues
- Discord: https://discord.gg/kailash
- Email: support@kailash.dev
```

### CLAUDE.md Template

```markdown
# Claude Code Instructions for kailash-sso

This component provides authentication and SSO for Kailash applications.

## Quick Usage

```python
pip install kailash-sso

from kailash_sso import SSOManager

sso = SSOManager(
    providers={"google": {"client_id": "...", "client_secret": "..."}},
    jwt_secret="secret"
)

# Pre-built workflows
login = sso.login_workflow()
register = sso.register_workflow()
```

## AI Instructions

When user asks for authentication:
1. Install kailash-sso
2. Configure providers (Google, GitHub, or SAML)
3. Get pre-built workflows
4. Register with Nexus

DO NOT build authentication from scratch.
DO NOT use raw JWT libraries (kailash-sso handles it).

## Common Customizations

**Add OAuth2 provider:**
```python
sso = SSOManager(
    providers={
        "google": {...},
        "github": {...},  # ← Add GitHub
        "microsoft": {...}  # ← Add Microsoft
    }
)
```

**Enable MFA:**
```python
sso = SSOManager(
    providers={...},
    jwt_secret="...",
    mfa_enabled=True  # ← Enable MFA
)
```

**Custom token expiry:**
```python
sso = SSOManager(
    providers={...},
    jwt_secret="...",
    token_expiry=3600  # ← 1 hour (default: 24 hours)
)
```

## Common Mistakes

❌ Building auth from scratch when kailash-sso exists
❌ Using raw JWT library (use SSOManager)
❌ Forgetting to set JWT_SECRET in environment
❌ Not handling OAuth2 callback endpoint

✅ Use kailash-sso for all authentication
✅ Configure providers in .env file
✅ Use pre-built workflows
✅ Register callback endpoint with Nexus
```

---

## Publishing Process

### 1. Build Package

```bash
cd packages/kailash-sso
python -m build
```

### 2. Test Package Locally

```bash
# Install from local build
pip install dist/kailash_sso-2.1.3-py3-none-any.whl

# Test import
python -c "from kailash_sso import SSOManager; print('✅ Import works')"

# Run example
python examples/basic_usage.py
```

### 3. Publish to PyPI

```bash
# Test PyPI first (optional)
python -m twine upload --repository testpypi dist/*

# Production PyPI
python -m twine upload dist/*
```

### 4. Tag Release

```bash
git tag -a v2.1.3 -m "Release v2.1.3 - Added SAML support"
git push origin v2.1.3
```

### 5. Update Marketplace Catalog

```bash
# Submit to kailash.dev marketplace (optional)
kailash marketplace submit kailash-sso

# Or just publish to PyPI (automatically discoverable)
```

---

## Component Versioning Example

**kailash-sso version history:**
```
v1.0.0 (2025-01) - Initial release
  - OAuth2 (Google, GitHub)
  - JWT tokens
  - Basic workflows

v1.1.0 (2025-02) - SAML support
  - Added SAMLProvider
  - Enterprise SSO
  - Backward compatible

v1.2.0 (2025-03) - MFA support
  - Multi-factor authentication
  - TOTP support
  - Backward compatible

v1.2.1 (2025-04) - Security patch
  - Fixed JWT vulnerability
  - Urgent update recommended

v2.0.0 (2025-06) - API redesign
  - Breaking: Changed SSOManager constructor
  - Migration guide provided
  - Improved performance
```

---

## Success Metrics

### Per-Component Metrics

**1. Install Rate**
- kailash-sso: 200+ installs/month (highest demand)
- kailash-dataflow-utils: 300+ installs/month (used by all)
- kailash-rbac: 150+ installs/month
- kailash-admin: 100+ installs/month
- kailash-payments: 80+ installs/month (niche)

**2. Component Satisfaction (NPS)**
- Target: NPS 50+ for all official components
- Measure: In-package survey (optional)
- Quarterly email survey

**3. GitHub Stars**
- Target: 100+ stars per component
- Indicates: Community validation

**4. Production Usage**
- Target: 50+ apps using each component in production
- Measure: Opt-in telemetry + case studies

### Ecosystem Metrics

**5. Component Combinations**
- Most common: sso + rbac + admin (complete auth stack)
- Second: dataflow-utils + sso (minimal stack)
- Track: Which components are installed together

**6. Template Integration**
- Target: 100% of templates use ≥2 official components
- Validates: Components are actually useful

---

## Key Takeaways

**Official components set the quality bar for the entire marketplace.**

**Critical success factors:**
1. **Excellent quality** - 80%+ test coverage, comprehensive docs
2. **Easy to use** - 5 minutes from install to working
3. **Well integrated** - Components work together seamlessly
4. **Maintained** - Monthly updates, security patches
5. **AI-friendly** - CLAUDE.md with clear instructions

**If official components succeed:**
- Community will submit components (proven marketplace)
- IT teams will trust ecosystem (quality standards)
- Developers will contribute (vibrant community)

**If official components fail:**
- Users won't trust marketplace
- No community contributions
- Ecosystem doesn't grow

**These 5 components are the foundation. Must be perfect.**

---

**Next:** See `03-modifications/` for changes to existing SDK code (runtime, CLI, error messages)
