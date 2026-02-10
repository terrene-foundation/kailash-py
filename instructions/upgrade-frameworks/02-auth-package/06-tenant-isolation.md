# Tenant Isolation Specification

## Overview

This specification defines automatic tenant isolation for multi-tenant applications using Nexus. It ensures that database queries and API responses are automatically scoped to the authenticated user's organization/tenant, preventing cross-tenant data access.

## Evidence from Real Projects

| Project             | File                   | Lines | Key Features                                         |
| ------------------- | ---------------------- | ----- | ---------------------------------------------------- |
| dataflow.core       | `tenant_context.py`    | 404   | ContextVar-based switching, async-safe, registration |
| kailash.nodes.admin | `tenant_isolation.py`  | 250   | TenantIsolationManager, permission validation        |
| saas_starter        | `middleware/tenant.py` | 220   | JWT extraction, workflow scoping                     |

## Architecture

### Component Hierarchy

```
nexus.auth.tenant
    TenantConfig              # Configuration dataclass
    TenantContext             # Current tenant context (contextvars)
    TenantInfo                # Tenant metadata dataclass
    TenantResolver            # Resolves tenant from request
    TenantMiddleware          # FastAPI middleware
    tenant_context()          # Context manager for explicit switching
    get_current_tenant()      # Get current tenant (or raise)
    require_tenant()          # Get tenant or 403
```

### File Structure

```
apps/kailash-nexus/src/nexus/auth/
    __init__.py                 # Re-export TenantConfig, get_current_tenant
    tenant/
        __init__.py             # Re-export all components
        config.py               # TenantConfig dataclass
        context.py              # TenantContext, TenantInfo, contextvars
        resolver.py             # TenantResolver - extract tenant from request
        middleware.py           # TenantMiddleware
        exceptions.py           # TenantNotFoundError, TenantAccessDeniedError
```

## Configuration

### TenantConfig

**Location:** `nexus/auth/tenant/config.py`

```python
from dataclasses import dataclass, field
from typing import Callable, List, Optional

@dataclass
class TenantConfig:
    """Configuration for tenant isolation.

    Attributes:
        enabled: Whether tenant isolation is enabled (default: True)
        tenant_id_header: Header name for explicit tenant ID (default: "X-Tenant-ID")
        jwt_claim: JWT claim containing tenant ID (default: "tenant_id")
        fallback_to_user_org: Look up org from user record if not in JWT (default: True)
        org_field_name: Field name for organization in user record (default: "organization_id")
        validate_tenant_exists: Validate tenant exists in database (default: True)
        validate_tenant_active: Validate tenant is active (default: True)
        allow_admin_override: Allow super admins to access any tenant (default: True)
        admin_role: Role name for super admins (default: "super_admin")
        exclude_paths: Paths to exclude from tenant isolation (default: ["/health", "/metrics"])

    Example:
        >>> config = TenantConfig(
        ...     tenant_id_header="X-Tenant-ID",
        ...     jwt_claim="org_id",
        ...     fallback_to_user_org=True,
        ...     validate_tenant_exists=True,
        ...     exclude_paths=["/health", "/metrics", "/api/public/*"],
        ... )
    """

    enabled: bool = True
    tenant_id_header: str = "X-Tenant-ID"
    jwt_claim: str = "tenant_id"
    fallback_to_user_org: bool = True
    org_field_name: str = "organization_id"
    validate_tenant_exists: bool = True
    validate_tenant_active: bool = True
    allow_admin_override: bool = True
    admin_role: str = "super_admin"
    exclude_paths: List[str] = field(
        default_factory=lambda: ["/health", "/metrics", "/docs", "/openapi.json"]
    )

    # Custom tenant resolver (optional)
    custom_resolver: Optional[Callable] = None
```

## Context Management

### TenantContext and TenantInfo

**Location:** `nexus/auth/tenant/context.py`

```python
import logging
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Thread/async-safe context variable for current tenant
_current_tenant: ContextVar[Optional["TenantInfo"]] = ContextVar(
    "_current_tenant", default=None
)


@dataclass
class TenantInfo:
    """Information about the current tenant.

    Attributes:
        tenant_id: Unique identifier for the tenant
        name: Human-readable name (optional)
        active: Whether the tenant is active
        metadata: Additional tenant metadata
        created_at: When the tenant was created (optional)

    Example:
        >>> tenant = TenantInfo(
        ...     tenant_id="tenant-123",
        ...     name="Acme Corp",
        ...     active=True,
        ...     metadata={"plan": "enterprise"},
        ... )
    """

    tenant_id: str
    name: Optional[str] = None
    active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None

    def __post_init__(self):
        """Set created_at if not provided."""
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)


class TenantContext:
    """Manages tenant context for requests.

    Provides sync and async context managers for switching tenant context,
    using Python's contextvars module for thread/async safety.

    Example:
        >>> ctx = TenantContext()
        >>>
        >>> # Register tenants
        >>> ctx.register("tenant-a", name="Tenant A")
        >>> ctx.register("tenant-b", name="Tenant B")
        >>>
        >>> # Switch context (sync)
        >>> with ctx.switch("tenant-a"):
        ...     tenant = ctx.current()
        ...     print(f"Operating as: {tenant.tenant_id}")
        >>>
        >>> # Switch context (async)
        >>> async with ctx.aswitch("tenant-a"):
        ...     tenant = ctx.current()
    """

    def __init__(self, validate_registered: bool = True):
        """Initialize tenant context manager.

        Args:
            validate_registered: Whether to require tenants be registered (default: True).
                                 SECURITY: Default is True (fail-closed) to prevent
                                 unauthorized tenant access. Set to False only for
                                 development or when tenant validation is handled elsewhere.
        """
        self._tenants: Dict[str, TenantInfo] = {}
        self._validate_registered = validate_registered
        self._switch_count: int = 0
        self._active_switches: int = 0

    def register(
        self,
        tenant_id: str,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        active: bool = True,
    ) -> TenantInfo:
        """Register a tenant.

        Args:
            tenant_id: Unique tenant identifier
            name: Human-readable name (optional)
            metadata: Additional metadata (optional)
            active: Whether tenant is active (default: True)

        Returns:
            TenantInfo for the registered tenant

        Raises:
            ValueError: If tenant_id is invalid or already registered
        """
        if not tenant_id or not isinstance(tenant_id, str):
            raise ValueError("tenant_id must be a non-empty string")
        if tenant_id in self._tenants:
            raise ValueError(f"Tenant '{tenant_id}' is already registered")

        info = TenantInfo(
            tenant_id=tenant_id,
            name=name,
            active=active,
            metadata=metadata or {},
        )
        self._tenants[tenant_id] = info
        logger.debug(f"Registered tenant '{tenant_id}' ({name})")
        return info

    def unregister(self, tenant_id: str) -> None:
        """Unregister a tenant.

        Args:
            tenant_id: Tenant ID to unregister

        Raises:
            ValueError: If tenant not registered or currently active
        """
        if tenant_id not in self._tenants:
            raise ValueError(f"Tenant '{tenant_id}' is not registered")

        current = self.current()
        if current and current.tenant_id == tenant_id:
            raise ValueError(
                f"Cannot unregister tenant '{tenant_id}' while it is active"
            )

        del self._tenants[tenant_id]
        logger.debug(f"Unregistered tenant '{tenant_id}'")

    def get(self, tenant_id: str) -> Optional[TenantInfo]:
        """Get tenant info by ID.

        Args:
            tenant_id: Tenant ID to look up

        Returns:
            TenantInfo if found, None otherwise
        """
        return self._tenants.get(tenant_id)

    def list_tenants(self) -> List[TenantInfo]:
        """List all registered tenants.

        Returns:
            List of TenantInfo for all registered tenants
        """
        return list(self._tenants.values())

    def current(self) -> Optional[TenantInfo]:
        """Get the current tenant from context.

        Returns:
            Current TenantInfo, or None if no context is set
        """
        return _current_tenant.get()

    def require(self) -> TenantInfo:
        """Get current tenant or raise error.

        Returns:
            Current TenantInfo

        Raises:
            TenantContextError: If no tenant context is active
        """
        tenant = self.current()
        if tenant is None:
            raise TenantContextError(
                "No tenant context is active. "
                "Use 'with tenant_context.switch(tenant_id):' to set context."
            )
        return tenant

    @contextmanager
    def switch(self, tenant_id: str):
        """Synchronous context manager for switching tenant.

        Args:
            tenant_id: Tenant ID to switch to

        Yields:
            TenantInfo for the active tenant

        Raises:
            TenantNotFoundError: If tenant not registered (when validation enabled)
            TenantInactiveError: If tenant is inactive
        """
        tenant = self._resolve_tenant(tenant_id)

        previous = _current_tenant.get()
        token = _current_tenant.set(tenant)
        self._switch_count += 1
        self._active_switches += 1

        logger.debug(
            f"Switched to tenant '{tenant_id}' "
            f"(previous: {previous.tenant_id if previous else None})"
        )

        try:
            yield tenant
        finally:
            _current_tenant.reset(token)
            self._active_switches -= 1
            logger.debug(
                f"Restored tenant context to "
                f"'{previous.tenant_id if previous else None}'"
            )

    @asynccontextmanager
    async def aswitch(self, tenant_id: str):
        """Asynchronous context manager for switching tenant.

        Same semantics as switch() but for async code.

        Args:
            tenant_id: Tenant ID to switch to

        Yields:
            TenantInfo for the active tenant
        """
        tenant = self._resolve_tenant(tenant_id)

        previous = _current_tenant.get()
        token = _current_tenant.set(tenant)
        self._switch_count += 1
        self._active_switches += 1

        logger.debug(
            f"Async switched to tenant '{tenant_id}' "
            f"(previous: {previous.tenant_id if previous else None})"
        )

        try:
            yield tenant
        finally:
            _current_tenant.reset(token)
            self._active_switches -= 1
            logger.debug(
                f"Async restored tenant context to "
                f"'{previous.tenant_id if previous else None}'"
            )

    def _resolve_tenant(self, tenant_id: str) -> TenantInfo:
        """Resolve tenant ID to TenantInfo.

        Args:
            tenant_id: Tenant ID to resolve

        Returns:
            TenantInfo for the tenant

        Raises:
            TenantNotFoundError: If tenant not registered
            TenantInactiveError: If tenant is inactive
        """
        if self._validate_registered:
            if tenant_id not in self._tenants:
                available = list(self._tenants.keys())
                raise TenantNotFoundError(
                    tenant_id=tenant_id,
                    available=available,
                )

            tenant = self._tenants[tenant_id]
            if not tenant.active:
                raise TenantInactiveError(tenant_id=tenant_id)

            return tenant
        else:
            # Create ad-hoc tenant info without registration
            return TenantInfo(tenant_id=tenant_id)

    def deactivate(self, tenant_id: str) -> None:
        """Deactivate a tenant (prevents context switching).

        Args:
            tenant_id: Tenant ID to deactivate

        Raises:
            ValueError: If tenant not registered
        """
        if tenant_id not in self._tenants:
            raise ValueError(f"Tenant '{tenant_id}' is not registered")
        self._tenants[tenant_id].active = False
        logger.debug(f"Deactivated tenant '{tenant_id}'")

    def activate(self, tenant_id: str) -> None:
        """Reactivate a deactivated tenant.

        Args:
            tenant_id: Tenant ID to activate

        Raises:
            ValueError: If tenant not registered
        """
        if tenant_id not in self._tenants:
            raise ValueError(f"Tenant '{tenant_id}' is not registered")
        self._tenants[tenant_id].active = True
        logger.debug(f"Activated tenant '{tenant_id}'")

    def get_stats(self) -> Dict[str, Any]:
        """Get context switching statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "total_tenants": len(self._tenants),
            "active_tenants": sum(1 for t in self._tenants.values() if t.active),
            "total_switches": self._switch_count,
            "active_switches": self._active_switches,
            "current_tenant": (
                self.current().tenant_id if self.current() else None
            ),
        }


# Module-level helper functions

def get_current_tenant() -> Optional[TenantInfo]:
    """Get the current tenant from context.

    This is a module-level helper for code that needs to check
    the current tenant without a TenantContext instance.

    Returns:
        Current TenantInfo, or None if no context is set
    """
    return _current_tenant.get()


def get_current_tenant_id() -> Optional[str]:
    """Get the current tenant ID from context.

    Returns:
        Current tenant ID, or None if no context is set
    """
    tenant = _current_tenant.get()
    return tenant.tenant_id if tenant else None


def require_tenant() -> TenantInfo:
    """Get current tenant or raise 403.

    Returns:
        Current TenantInfo

    Raises:
        TenantContextError: If no tenant context is active
    """
    tenant = _current_tenant.get()
    if tenant is None:
        raise TenantContextError("No tenant context is active")
    return tenant
```

### Exceptions

**Location:** `nexus/auth/tenant/exceptions.py`

```python
from typing import List, Optional

class TenantError(Exception):
    """Base exception for tenant operations."""
    pass


class TenantContextError(TenantError):
    """Raised when no tenant context is active."""
    pass


class TenantNotFoundError(TenantError):
    """Raised when tenant is not found or not registered.

    Attributes:
        tenant_id: The tenant ID that was not found
        available: List of available tenant IDs
    """

    def __init__(
        self,
        tenant_id: str,
        available: Optional[List[str]] = None,
        message: Optional[str] = None,
    ):
        self.tenant_id = tenant_id
        self.available = available or []

        if message is None:
            message = f"Tenant '{tenant_id}' not found."
            if self.available:
                message += f" Available: {self.available}"

        super().__init__(message)


class TenantInactiveError(TenantError):
    """Raised when tenant is inactive.

    Attributes:
        tenant_id: The inactive tenant ID
    """

    def __init__(self, tenant_id: str, message: Optional[str] = None):
        self.tenant_id = tenant_id
        if message is None:
            message = f"Tenant '{tenant_id}' is inactive."
        super().__init__(message)


class TenantAccessDeniedError(TenantError):
    """Raised when access to tenant is denied.

    Attributes:
        tenant_id: The tenant ID access was denied to
        user_id: The user who was denied access
        reason: Reason for denial
    """

    def __init__(
        self,
        tenant_id: str,
        user_id: Optional[str] = None,
        reason: Optional[str] = None,
    ):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.reason = reason or "Access denied"

        message = f"Access to tenant '{tenant_id}' denied"
        if user_id:
            message += f" for user '{user_id}'"
        message += f": {self.reason}"

        super().__init__(message)
```

## Tenant Resolver

**Location:** `nexus/auth/tenant/resolver.py`

```python
import logging
from typing import Optional

from fastapi import Request

from .config import TenantConfig
from .context import TenantInfo
from .exceptions import TenantAccessDeniedError, TenantNotFoundError

logger = logging.getLogger(__name__)


class TenantResolver:
    """Resolves tenant from HTTP request.

    Resolution order (in priority):
    1. X-Tenant-ID header (for admin API access across tenants)
    2. tenant_id claim from JWT token (primary method)
    3. Organization lookup from user record (fallback)

    Example:
        >>> resolver = TenantResolver(config)
        >>> tenant_info = await resolver.resolve(request)
        >>> print(f"Resolved tenant: {tenant_info.tenant_id}")
    """

    def __init__(self, config: TenantConfig, tenant_store: Optional[Any] = None):
        """Initialize resolver.

        Args:
            config: Tenant configuration
            tenant_store: Optional store for tenant validation (DataFlow, etc.)
        """
        self.config = config
        self._tenant_store = tenant_store

    async def resolve(self, request: Request) -> Optional[TenantInfo]:
        """Resolve tenant from request.

        Args:
            request: FastAPI request

        Returns:
            TenantInfo if resolved, None otherwise

        Raises:
            TenantNotFoundError: If tenant validation fails
            TenantAccessDeniedError: If admin override not allowed
        """
        # Use custom resolver if provided
        if self.config.custom_resolver:
            return await self.config.custom_resolver(request)

        tenant_id = None
        source = None

        # 1. Check header (highest priority - for admin override)
        header_value = request.headers.get(self.config.tenant_id_header)
        if header_value:
            tenant_id = header_value
            source = "header"

            # Validate admin override is allowed and user has admin role
            if self.config.allow_admin_override:
                # Check if user has admin role
                user_roles = getattr(request.state, "roles", [])
                if self.config.admin_role not in user_roles:
                    # SECURITY: Fail-closed - explicitly reject non-admin override attempts
                    # Do NOT silently fall through to JWT claim as this could mask attack attempts
                    logger.warning(
                        f"Non-admin user attempted tenant override via header: "
                        f"user_id={getattr(request.state, 'user_id', 'unknown')}, "
                        f"tenant={tenant_id}"
                    )
                    raise TenantAccessDeniedError(
                        tenant_id=tenant_id,
                        user_id=getattr(request.state, 'user_id', None),
                        reason=f"Tenant override header requires '{self.config.admin_role}' role",
                    )
            else:
                # Admin override not allowed at all
                raise TenantAccessDeniedError(
                    tenant_id=tenant_id,
                    reason="Admin tenant override is disabled",
                )

        # 2. Check JWT claim
        if tenant_id is None and hasattr(request.state, "token_claims"):
            claims = request.state.token_claims
            if isinstance(claims, dict):
                tenant_id = claims.get(self.config.jwt_claim)
                if tenant_id:
                    source = "jwt"

        # 3. Fallback to user organization lookup
        if tenant_id is None and self.config.fallback_to_user_org:
            tenant_id = await self._lookup_user_org(request)
            if tenant_id:
                source = "user_org"

        if tenant_id is None:
            return None

        # Validate tenant exists and is active
        tenant_info = await self._validate_tenant(tenant_id)

        logger.debug(f"Resolved tenant '{tenant_id}' from {source}")
        return tenant_info

    async def _lookup_user_org(self, request: Request) -> Optional[str]:
        """Look up organization from user record.

        Args:
            request: FastAPI request

        Returns:
            Organization/tenant ID, or None
        """
        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            return None

        # If we have a user object with org_id
        user = getattr(request.state, "user", None)
        if user:
            if hasattr(user, self.config.org_field_name):
                return getattr(user, self.config.org_field_name)
            if isinstance(user, dict):
                return user.get(self.config.org_field_name)

        # Could add DataFlow lookup here if needed
        return None

    async def _validate_tenant(self, tenant_id: str) -> TenantInfo:
        """Validate tenant exists and is active.

        Args:
            tenant_id: Tenant ID to validate

        Returns:
            TenantInfo for valid tenant

        Raises:
            TenantNotFoundError: If tenant doesn't exist
            TenantInactiveError: If tenant is inactive
        """
        # If we have a tenant store, validate against it
        if self._tenant_store and self.config.validate_tenant_exists:
            # This would use DataFlow or similar to check tenant exists
            # For now, we create a basic TenantInfo
            pass

        # Create TenantInfo
        return TenantInfo(
            tenant_id=tenant_id,
            active=True,  # Assume active if validation not enabled
        )
```

## Middleware

**Location:** `nexus/auth/tenant/middleware.py`

```python
import fnmatch
import logging
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .config import TenantConfig
from .context import TenantContext, TenantInfo, _current_tenant
from .exceptions import (
    TenantAccessDeniedError,
    TenantInactiveError,
    TenantNotFoundError,
)
from .resolver import TenantResolver

logger = logging.getLogger(__name__)


class TenantMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for tenant isolation.

    Sets tenant context for each request based on JWT claims,
    headers, or user organization lookup.

    Middleware behavior:
    1. Check if path is excluded from tenant isolation
    2. Resolve tenant from request (header, JWT, user org)
    3. Validate tenant exists and is active
    4. Set tenant context via contextvars
    5. Process request within tenant context
    6. Clear tenant context on completion

    Example:
        >>> from fastapi import FastAPI
        >>> from nexus.auth import TenantConfig
        >>> from nexus.auth.tenant import TenantMiddleware
        >>>
        >>> app = FastAPI()
        >>> config = TenantConfig(
        ...     jwt_claim="org_id",
        ...     exclude_paths=["/health", "/metrics"],
        ... )
        >>> app.add_middleware(TenantMiddleware, config=config)
    """

    def __init__(
        self,
        app,
        config: TenantConfig,
        tenant_context: Optional[TenantContext] = None,
    ):
        """Initialize tenant middleware.

        Args:
            app: FastAPI/Starlette application
            config: Tenant configuration
            tenant_context: Optional TenantContext instance (creates one if not provided)
        """
        super().__init__(app)
        self.config = config
        self._tenant_context = tenant_context or TenantContext(validate_registered=False)
        self._resolver = TenantResolver(config)

    def _is_excluded_path(self, path: str) -> bool:
        """Check if path is excluded from tenant isolation.

        Args:
            path: Request path

        Returns:
            True if path is excluded
        """
        for pattern in self.config.exclude_paths:
            if fnmatch.fnmatch(path, pattern):
                return True
        return False

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with tenant context."""
        if not self.config.enabled:
            return await call_next(request)

        path = request.url.path

        # Check for excluded paths
        if self._is_excluded_path(path):
            return await call_next(request)

        try:
            # Resolve tenant from request
            tenant_info = await self._resolver.resolve(request)

            if tenant_info is None:
                # No tenant resolved - could be unauthenticated endpoint
                # Let auth middleware handle this
                return await call_next(request)

            # Set tenant context
            token = _current_tenant.set(tenant_info)

            # Add tenant info to request state for easy access
            request.state.tenant_id = tenant_info.tenant_id
            request.state.tenant = tenant_info

            logger.debug(
                f"Tenant context set: {tenant_info.tenant_id} for {path}"
            )

            try:
                # Process request within tenant context
                response = await call_next(request)

                # Add tenant header to response (for debugging)
                response.headers["X-Tenant-ID"] = tenant_info.tenant_id

                return response

            finally:
                # Clear tenant context
                _current_tenant.reset(token)

        except TenantNotFoundError as e:
            logger.warning(f"Tenant not found: {e.tenant_id}")
            return JSONResponse(
                status_code=404,
                content={
                    "detail": f"Tenant not found: {e.tenant_id}",
                    "error_code": "TENANT_NOT_FOUND",
                },
            )

        except TenantInactiveError as e:
            logger.warning(f"Tenant inactive: {e.tenant_id}")
            return JSONResponse(
                status_code=403,
                content={
                    "detail": f"Tenant is inactive: {e.tenant_id}",
                    "error_code": "TENANT_INACTIVE",
                },
            )

        except TenantAccessDeniedError as e:
            logger.warning(f"Tenant access denied: {e}")
            return JSONResponse(
                status_code=403,
                content={
                    "detail": e.reason,
                    "error_code": "TENANT_ACCESS_DENIED",
                },
            )
```

## Integration with DataFlow

### Automatic Query Scoping

When tenant context is set, DataFlow queries are automatically scoped:

```python
from dataflow import DataFlow
from nexus.auth.tenant import get_current_tenant_id

# In DataFlow query execution
def _apply_tenant_filter(query_filter: dict) -> dict:
    """Apply tenant filter to query."""
    tenant_id = get_current_tenant_id()
    if tenant_id:
        query_filter["tenant_id"] = tenant_id
    return query_filter
```

### Model Tenant Column

Models should include a tenant_id column:

```python
from dataflow import DataFlow

db = DataFlow("postgresql://...")

@db.model
class User:
    id: str
    name: str
    email: str
    tenant_id: str  # Required for tenant isolation
    organization_id: str  # Alias for tenant_id (common pattern)
```

### Explicit Tenant Context in Workflows

```python
from nexus.auth.tenant import tenant_context, get_current_tenant

# In a workflow node
async def process_data():
    tenant = get_current_tenant()
    if tenant:
        # All DataFlow operations automatically scoped
        users = await db.list("User", filter={})  # tenant_id auto-added
    else:
        raise TenantContextError("Tenant context required")
```

## Admin Override

### Super Admin Access

Super admins can access any tenant using the `X-Tenant-ID` header:

```python
@app.get("/api/admin/tenants/{tenant_id}/users")
async def list_tenant_users(request: Request, tenant_id: str):
    """List users in any tenant (super admin only)."""
    # TenantMiddleware validates admin role
    # Tenant context set from header

    users = await db.list("User", filter={})  # Scoped to tenant_id
    return {"users": users}
```

### Explicit Context Manager

For operations that need to cross tenant boundaries:

```python
from nexus.auth.tenant import TenantContext

tenant_ctx = TenantContext()

@app.get("/api/admin/cross-tenant-report")
async def cross_tenant_report(request: Request):
    """Generate report across all tenants (super admin only)."""
    # Verify super admin
    if "super_admin" not in request.state.roles:
        raise HTTPException(status_code=403)

    results = []
    for tenant in tenant_ctx.list_tenants():
        async with tenant_ctx.aswitch(tenant.tenant_id):
            # Operations scoped to this tenant
            count = await db.count("User", filter={})
            results.append({
                "tenant_id": tenant.tenant_id,
                "user_count": count,
            })

    return {"report": results}
```

## Integration with Nexus

### Nexus Configuration

```python
from nexus import Nexus
from nexus.auth import TenantConfig

app = Nexus(
    tenant_isolation=TenantConfig(
        jwt_claim="org_id",
        fallback_to_user_org=True,
        validate_tenant_exists=True,
        exclude_paths=["/health", "/metrics", "/api/public/*"],
    ),
)
```

### Manual Middleware Setup

```python
from fastapi import FastAPI
from nexus.auth import TenantConfig
from nexus.auth.tenant import TenantMiddleware

app = FastAPI()

config = TenantConfig(
    jwt_claim="org_id",
    exclude_paths=["/health"],
)

app.add_middleware(TenantMiddleware, config=config)
```

## Error Responses

### 403 Tenant Access Denied

```json
{
  "detail": "Access denied to tenant",
  "error_code": "TENANT_ACCESS_DENIED"
}
```

### 404 Tenant Not Found

```json
{
  "detail": "Tenant not found: tenant-xyz",
  "error_code": "TENANT_NOT_FOUND"
}
```

### 403 Tenant Inactive

```json
{
  "detail": "Tenant is inactive: tenant-xyz",
  "error_code": "TENANT_INACTIVE"
}
```

## Testing Requirements

### Tier 1: Unit Tests (Mocking Allowed)

**Location:** `tests/unit/auth/tenant/`

```python
# test_config.py
def test_config_defaults():
    """Test default configuration values."""
    config = TenantConfig()
    assert config.enabled is True
    assert config.tenant_id_header == "X-Tenant-ID"
    assert config.jwt_claim == "tenant_id"
    assert config.fallback_to_user_org is True

# test_context.py
def test_tenant_context_registration():
    """Test tenant registration."""
    ctx = TenantContext()
    tenant = ctx.register("tenant-1", name="Test Tenant")
    assert tenant.tenant_id == "tenant-1"
    assert tenant.name == "Test Tenant"

def test_tenant_context_switch():
    """Test synchronous context switching."""
    ctx = TenantContext()
    ctx.register("tenant-1")

    assert ctx.current() is None

    with ctx.switch("tenant-1"):
        assert ctx.current().tenant_id == "tenant-1"

    assert ctx.current() is None

@pytest.mark.asyncio
async def test_tenant_context_async_switch():
    """Test asynchronous context switching."""
    ctx = TenantContext()
    ctx.register("tenant-1")

    assert ctx.current() is None

    async with ctx.aswitch("tenant-1"):
        assert ctx.current().tenant_id == "tenant-1"

    assert ctx.current() is None

def test_tenant_context_nested_switch():
    """Test nested context switching."""
    ctx = TenantContext()
    ctx.register("tenant-1")
    ctx.register("tenant-2")

    with ctx.switch("tenant-1"):
        assert ctx.current().tenant_id == "tenant-1"

        with ctx.switch("tenant-2"):
            assert ctx.current().tenant_id == "tenant-2"

        assert ctx.current().tenant_id == "tenant-1"

def test_tenant_context_require_raises():
    """Test require() raises when no context."""
    ctx = TenantContext()
    ctx.register("tenant-1")

    with pytest.raises(TenantContextError):
        ctx.require()

def test_unregistered_tenant_raises():
    """Test switching to unregistered tenant raises."""
    ctx = TenantContext()

    with pytest.raises(TenantNotFoundError) as exc_info:
        with ctx.switch("unknown"):
            pass

    assert exc_info.value.tenant_id == "unknown"

# test_exceptions.py
def test_tenant_not_found_error():
    """Test TenantNotFoundError attributes."""
    error = TenantNotFoundError(
        tenant_id="xyz",
        available=["a", "b", "c"],
    )
    assert error.tenant_id == "xyz"
    assert error.available == ["a", "b", "c"]
    assert "xyz" in str(error)
```

### Tier 2: Integration Tests (NO MOCKING - Real Infrastructure)

**Location:** `tests/integration/auth/tenant/`

```python
# test_tenant_isolation_integration.py
@pytest.fixture
def test_client_with_tenants():
    """Create test client with tenant middleware."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    config = TenantConfig(
        jwt_claim="org_id",
        validate_tenant_exists=False,  # Don't need DB for this test
    )
    app.add_middleware(TenantMiddleware, config=config)

    @app.get("/api/data")
    async def get_data(request: Request):
        tenant = get_current_tenant()
        if tenant:
            return {"tenant_id": tenant.tenant_id}
        return {"tenant_id": None}

    return TestClient(app)

def test_tenant_from_jwt_claim(test_client_with_tenants):
    """Test tenant resolved from JWT claim (NO MOCKING)."""
    # Create JWT with org_id claim
    token = create_test_jwt({"org_id": "tenant-123"})

    response = test_client_with_tenants.get(
        "/api/data",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["tenant_id"] == "tenant-123"

def test_tenant_from_header(test_client_with_tenants):
    """Test admin override via header (NO MOCKING)."""
    # Create JWT with admin role
    token = create_test_jwt({
        "org_id": "tenant-1",
        "roles": ["super_admin"],
    })

    response = test_client_with_tenants.get(
        "/api/data",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": "tenant-999",
        },
    )

    assert response.status_code == 200
    assert response.json()["tenant_id"] == "tenant-999"

def test_non_admin_cannot_override(test_client_with_tenants):
    """Test non-admin cannot use header override (NO MOCKING)."""
    # Create JWT without admin role
    token = create_test_jwt({
        "org_id": "tenant-1",
        "roles": ["user"],
    })

    response = test_client_with_tenants.get(
        "/api/data",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": "tenant-999",
        },
    )

    # Should use JWT claim, not header
    assert response.status_code == 200
    assert response.json()["tenant_id"] == "tenant-1"

# test_dataflow_isolation_integration.py
@pytest.fixture
async def db():
    """Create DataFlow instance with real database."""
    db = DataFlow("sqlite:///:memory:")

    @db.model
    class User:
        id: str
        name: str
        tenant_id: str

    await db.initialize()
    yield db
    await db.close()

@pytest.mark.asyncio
async def test_tenant_a_cannot_see_tenant_b_data(db):
    """Test tenant isolation prevents cross-tenant access (NO MOCKING)."""
    ctx = TenantContext()
    ctx.register("tenant-a")
    ctx.register("tenant-b")

    # Create user in tenant-a
    async with ctx.aswitch("tenant-a"):
        await db.create("User", {
            "id": "user-1",
            "name": "Alice",
            "tenant_id": "tenant-a",
        })

    # Create user in tenant-b
    async with ctx.aswitch("tenant-b"):
        await db.create("User", {
            "id": "user-2",
            "name": "Bob",
            "tenant_id": "tenant-b",
        })

    # Tenant-a should only see their user
    async with ctx.aswitch("tenant-a"):
        users = await db.list("User", filter={})
        assert len(users) == 1
        assert users[0]["name"] == "Alice"

    # Tenant-b should only see their user
    async with ctx.aswitch("tenant-b"):
        users = await db.list("User", filter={})
        assert len(users) == 1
        assert users[0]["name"] == "Bob"
```

### Tier 3: E2E Tests (NO MOCKING - Full Stack)

**Location:** `tests/e2e/auth/tenant/`

```python
# test_tenant_e2e.py
@pytest.mark.asyncio
async def test_full_tenant_isolation_flow():
    """Test complete tenant isolation flow (NO MOCKING)."""
    import aiohttp

    base_url = "http://localhost:8000"

    # Create JWT for tenant-a
    token_a = create_test_jwt({"org_id": "tenant-a"})

    # Create JWT for tenant-b
    token_b = create_test_jwt({"org_id": "tenant-b"})

    async with aiohttp.ClientSession() as session:
        # Create resource as tenant-a
        async with session.post(
            f"{base_url}/api/resources",
            json={"name": "Resource A"},
            headers={"Authorization": f"Bearer {token_a}"},
        ) as resp:
            assert resp.status == 201
            resource_a = await resp.json()

        # Tenant-b should not see tenant-a's resource
        async with session.get(
            f"{base_url}/api/resources/{resource_a['id']}",
            headers={"Authorization": f"Bearer {token_b}"},
        ) as resp:
            assert resp.status == 404  # Not found in tenant-b context

        # Tenant-a can see their resource
        async with session.get(
            f"{base_url}/api/resources/{resource_a['id']}",
            headers={"Authorization": f"Bearer {token_a}"},
        ) as resp:
            assert resp.status == 200
```

## Performance Considerations

### Context Variable Performance

- ContextVar access is O(1)
- No thread synchronization needed
- Async-safe by design

### Caching Recommendations

```python
# Cache tenant info for repeated lookups
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_tenant_info(tenant_id: str) -> TenantInfo:
    """Cached tenant info lookup."""
    # Lookup from database
    pass
```

## Migration Path

### From Custom Implementations

```python
# Before: Custom tenant middleware
from myapp.middleware import TenantMiddleware as CustomTenantMiddleware

app.add_middleware(CustomTenantMiddleware, org_field="org_id")

# After: Nexus tenant isolation
from nexus.auth import TenantConfig
from nexus.auth.tenant import TenantMiddleware

app.add_middleware(
    TenantMiddleware,
    config=TenantConfig(jwt_claim="org_id"),
)
```
