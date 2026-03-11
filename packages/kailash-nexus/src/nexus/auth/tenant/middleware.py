"""Tenant isolation middleware for FastAPI/Starlette.

Provides TenantMiddleware that resolves tenant from requests,
sets tenant context via contextvars, and handles tenant-related errors.
"""

import fnmatch
import logging
from typing import Callable, Optional

from fastapi import Request, Response
from nexus.auth.tenant.config import TenantConfig
from nexus.auth.tenant.context import TenantContext, _current_tenant
from nexus.auth.tenant.exceptions import (
    TenantAccessDeniedError,
    TenantInactiveError,
    TenantNotFoundError,
)
from nexus.auth.tenant.resolver import TenantResolver
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

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
        >>> from nexus.auth.tenant import TenantMiddleware, TenantConfig
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
        # SECURITY: Default to validate_registered=True (fail-closed)
        # to prevent unauthorized tenant access via ad-hoc tenant IDs
        self._tenant_context = tenant_context or TenantContext(validate_registered=True)
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
                return await call_next(request)

            # Set tenant context
            token = _current_tenant.set(tenant_info)

            # Add tenant info to request state for easy access
            request.state.tenant_id = tenant_info.tenant_id
            request.state.tenant = tenant_info

            logger.debug("Tenant context set: %s for %s", tenant_info.tenant_id, path)

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
            logger.warning("Tenant not found: %s", e.tenant_id)
            return JSONResponse(
                status_code=404,
                content={
                    "detail": f"Tenant not found: {e.tenant_id}",
                    "error_code": "TENANT_NOT_FOUND",
                },
            )

        except TenantInactiveError as e:
            logger.warning("Tenant inactive: %s", e.tenant_id)
            return JSONResponse(
                status_code=403,
                content={
                    "detail": f"Tenant is inactive: {e.tenant_id}",
                    "error_code": "TENANT_INACTIVE",
                },
            )

        except TenantAccessDeniedError as e:
            logger.warning("Tenant access denied: %s", e)
            return JSONResponse(
                status_code=403,
                content={
                    "detail": e.reason,
                    "error_code": "TENANT_ACCESS_DENIED",
                },
            )
