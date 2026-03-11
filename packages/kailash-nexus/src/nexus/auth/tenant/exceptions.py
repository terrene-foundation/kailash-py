"""Tenant isolation exceptions.

Provides exception types for tenant-related errors including
not found, inactive, access denied, and context errors.
"""

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
