"""
SDK-based Authentication Manager for Kailash Middleware

This module provides authentication management using SDK security nodes
instead of manual JWT handling and custom implementations.

Moved from middleware/auth.py to resolve directory/file confusion.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ...nodes.admin import PermissionCheckNode
from ...nodes.data import AsyncSQLDatabaseNode
from ...nodes.security import (
    AuditLogNode,
    CredentialManagerNode,
    RotatingCredentialNode,
    SecurityEventNode,
)
from ...nodes.transform import DataTransformer

logger = logging.getLogger(__name__)


class AuthLevel(Enum):
    """Authentication levels for different security requirements."""

    PUBLIC = "public"
    BASIC = "basic"
    STANDARD = "standard"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


class MiddlewareAuthManager:
    """
    Authentication manager using SDK security nodes.

    Provides:
    - JWT token management with CredentialManagerNode
    - API key rotation with RotatingCredentialNode
    - Permission checking with PermissionCheckNode
    - Security event logging with SecurityEventNode
    - Audit trail with AuditLogNode

    This replaces manual JWT handling with SDK components for better
    security, performance, and consistency.
    """

    def __init__(
        self,
        secret_key: str = None,
        token_expiry_hours: int = 24,
        enable_api_keys: bool = True,
        enable_audit: bool = True,
        database_url: str = None,
    ):
        """
        Initialize SDK Auth Manager.

        Args:
            secret_key: Secret key for JWT signing (will use CredentialManager)
            token_expiry_hours: Token expiration time in hours
            enable_api_keys: Enable API key authentication
            enable_audit: Enable audit logging
            database_url: Database URL for persistence
        """
        self.token_expiry_hours = token_expiry_hours
        self.enable_api_keys = enable_api_keys
        self.enable_audit = enable_audit

        # Initialize SDK security nodes
        self._initialize_security_nodes(secret_key, database_url)

        # FastAPI security scheme
        self.bearer_scheme = HTTPBearer(auto_error=False)

    def _initialize_security_nodes(self, secret_key: str, database_url: str):
        """Initialize all SDK security nodes."""

        # Store the secret key in memory for JWT operations
        self.secret_key = secret_key

        # Credential manager for fetching other credentials (not for JWT secret)
        # In production, JWT secret would come from environment or vault
        self.credential_manager = CredentialManagerNode(
            credential_name="api_credentials",
            credential_type="api_key",
            name="jwt_credential_manager",
        )

        # Rotating credentials for API keys
        if self.enable_api_keys:
            self.api_key_manager = RotatingCredentialNode(
                name="api_key_rotator"
                # Note: RotatingCredentialNode doesn't require credential_name or rotation_interval_days in __init__
                # These are passed during execution
            )

        # Permission checker
        self.permission_checker = PermissionCheckNode(
            name="middleware_permission_checker"
        )

        # Security event logger
        self.security_logger = SecurityEventNode(name="middleware_security_events")

        # Audit logger
        if self.enable_audit:
            self.audit_logger = AuditLogNode(name="middleware_audit")

        # Data transformer for token operations
        self.token_transformer = DataTransformer(name="token_transformer")

        # Database node for user storage
        if database_url:
            self.db_node = AsyncSQLDatabaseNode(
                name="auth_database", connection_string=database_url
            )

    async def create_access_token(
        self,
        user_id: str,
        permissions: List[str] = None,
        metadata: Dict[str, Any] = None,
    ) -> str:
        """
        Create JWT access token using SDK nodes.

        Args:
            user_id: User identifier
            permissions: List of permissions
            metadata: Additional metadata

        Returns:
            JWT token string
        """
        # Create token payload
        payload = {
            "user_id": user_id,
            "permissions": permissions or [],
            "metadata": metadata or {},
            "exp": datetime.now(timezone.utc)
            + timedelta(hours=self.token_expiry_hours),
            "iat": datetime.now(timezone.utc),
        }

        # Create JWT token
        # In production, this would use a more sophisticated approach
        # For now, we'll use the JWT library directly
        try:
            token = jwt.encode(payload, self.secret_key, algorithm="HS256")
            token_result = {"token": token}
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to create token: {str(e)}"
            )

        # Log token creation
        if self.enable_audit:
            self.audit_logger.execute(
                user_id=user_id,
                action="create_token",
                resource_type="jwt_token",
                resource_id=user_id,
                details={"permissions": permissions},
            )

        return token_result.get("token")

    async def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify and decode JWT token using SDK nodes.

        Args:
            token: JWT token string

        Returns:
            Decoded token payload

        Raises:
            HTTPException: If token is invalid
        """
        try:
            # Verify JWT token
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])

            # Check expiration
            if payload.get("exp", 0) < datetime.now(timezone.utc).timestamp():
                raise HTTPException(status_code=401, detail="Token has expired")

            return payload

        except Exception as e:
            # Log security event
            self.security_logger.execute(
                event_type="token_verification_failed",
                severity="warning",
                details={"error": str(e)},
            )
            raise HTTPException(status_code=401, detail="Invalid authentication token")

    async def create_api_key(
        self, user_id: str, key_name: str, permissions: List[str] = None
    ) -> str:
        """
        Create API key using RotatingCredentialNode.

        Args:
            user_id: User identifier
            key_name: Name for the API key
            permissions: List of permissions

        Returns:
            API key string
        """
        if not self.enable_api_keys:
            raise HTTPException(status_code=400, detail="API keys are disabled")

        # Generate a secure API key
        api_key = f"sk_{secrets.token_urlsafe(32)}"

        # Store API key metadata using credential manager
        result = self.credential_manager.execute(
            operation="store_credential",
            credential_name=api_key,
            credential_data={
                "user_id": user_id,
                "key_name": key_name,
                "permissions": permissions or [],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "api_key": api_key,
            },
        )

        if not result.get("success", False):
            raise HTTPException(status_code=500, detail="Failed to create API key")

        # Audit log
        if self.enable_audit:
            self.audit_logger.execute(
                user_id=user_id,
                action="create_api_key",
                resource_type="api_key",
                resource_id=key_name,
                details={"permissions": permissions},
            )

        return api_key

    async def verify_api_key(self, api_key: str) -> Dict[str, Any]:
        """
        Verify API key using SDK nodes.

        Args:
            api_key: API key string

        Returns:
            API key metadata including user_id and permissions

        Raises:
            HTTPException: If API key is invalid
        """
        if not self.enable_api_keys:
            raise HTTPException(status_code=400, detail="API keys are disabled")

        try:
            # Verify using credential manager since rotating credential node doesn't have verify
            result = self.credential_manager.execute(
                operation="get_credential", credential_name=api_key
            )

            if not result.get("success", False):
                raise HTTPException(status_code=401, detail="Invalid API key")

            credential_data = result.get("credential", {})
            return credential_data.get("metadata", {})

        except HTTPException:
            raise
        except Exception as e:
            # Log security event
            self.security_logger.execute(
                event_type="api_key_verification_failed",
                severity="warning",
                details={"error": str(e)},
            )
            raise HTTPException(status_code=401, detail="Invalid API key")

    async def check_permission(
        self, user_id: str, permission: str, resource: Dict[str, Any] = None
    ) -> bool:
        """
        Check user permission using PermissionCheckNode.

        Args:
            user_id: User identifier
            permission: Permission to check
            resource: Optional resource context

        Returns:
            True if permission is granted
        """
        result = self.permission_checker.execute(
            user_context={"user_id": user_id},
            permission=permission,
            resource=resource or {},
        )

        granted = result.get("authorized", False)

        # Audit permission check
        if self.enable_audit:
            self.audit_logger.execute(
                user_id=user_id,
                action="check_permission",
                resource_type="permission",
                resource_id=permission,
                details={"granted": granted, "resource": resource},
            )

        return granted

    def get_current_user_dependency(self, required_permissions: List[str] = None):
        """
        Create FastAPI dependency for user authentication.

        Args:
            required_permissions: List of required permissions

        Returns:
            FastAPI dependency function
        """

        async def verify_user(
            request: Request,
            credentials: HTTPAuthorizationCredentials = Depends(self.bearer_scheme),
        ) -> Dict[str, Any]:
            """Verify user from request."""

            # Try bearer token first
            if credentials and credentials.credentials:
                try:
                    payload = await self.verify_token(credentials.credentials)
                    user_id = payload.get("user_id")

                    # Check permissions if required
                    if required_permissions:
                        user_permissions = payload.get("permissions", [])
                        for perm in required_permissions:
                            if perm not in user_permissions:
                                # Check using permission node
                                if not await self.check_permission(user_id, perm):
                                    raise HTTPException(
                                        status_code=403,
                                        detail=f"Missing required permission: {perm}",
                                    )

                    return {
                        "user_id": user_id,
                        "permissions": payload.get("permissions", []),
                        "metadata": payload.get("metadata", {}),
                    }
                except HTTPException:
                    pass

            # Try API key from header
            api_key = request.headers.get("X-API-Key")
            if api_key:
                try:
                    metadata = await self.verify_api_key(api_key)
                    user_id = metadata.get("user_id")

                    # Check permissions
                    if required_permissions:
                        key_permissions = metadata.get("permissions", [])
                        for perm in required_permissions:
                            if perm not in key_permissions:
                                if not await self.check_permission(user_id, perm):
                                    raise HTTPException(
                                        status_code=403,
                                        detail=f"Missing required permission: {perm}",
                                    )

                    return {
                        "user_id": user_id,
                        "permissions": metadata.get("permissions", []),
                        "metadata": metadata,
                    }
                except HTTPException:
                    pass

            # No valid authentication
            raise HTTPException(status_code=401, detail="Not authenticated")

        return verify_user


# Convenience function for creating auth dependencies
def require_auth(permissions: List[str] = None):
    """
    Create authentication dependency with required permissions.

    Args:
        permissions: List of required permissions

    Returns:
        FastAPI dependency
    """
    # This would use a global auth manager instance
    # In practice, this would be configured at app startup
    raise NotImplementedError(
        "Use auth_manager.get_current_user_dependency(permissions) instead"
    )
