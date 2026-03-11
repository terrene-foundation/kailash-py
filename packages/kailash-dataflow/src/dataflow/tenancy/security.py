"""
Tenant Security Manager for Multi-Tenant Database Operations.

This module provides security controls and validation for multi-tenant
database operations, including access control, audit logging, and
security policy enforcement.
"""

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from .exceptions import CrossTenantAccessError, TenantSecurityError

logger = logging.getLogger(__name__)


class SecurityLevel(Enum):
    """Security levels for tenant operations."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SecurityPolicy:
    """Security policy configuration for a tenant."""

    tenant_id: str
    security_level: SecurityLevel
    allowed_operations: Set[str]
    forbidden_operations: Set[str]
    max_query_size: int
    max_queries_per_minute: int
    require_audit_logging: bool
    allow_cross_tenant_access: bool
    allowed_tables: Set[str]
    forbidden_tables: Set[str]

    def __post_init__(self):
        if self.allowed_operations is None:
            self.allowed_operations = set()
        if self.forbidden_operations is None:
            self.forbidden_operations = set()
        if self.allowed_tables is None:
            self.allowed_tables = set()
        if self.forbidden_tables is None:
            self.forbidden_tables = set()


@dataclass
class SecurityAuditLog:
    """Security audit log entry."""

    timestamp: datetime
    tenant_id: str
    operation: str
    query: str
    result: str
    security_level: SecurityLevel
    ip_address: Optional[str] = None
    user_id: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None


class TenantSecurityManager:
    """
    Manages security policies and controls for multi-tenant database operations.
    """

    def __init__(self):
        """Initialize the TenantSecurityManager."""
        self._policies: Dict[str, SecurityPolicy] = {}
        self._audit_logs: List[SecurityAuditLog] = []
        self._rate_limits: Dict[str, List[datetime]] = {}
        self._blocked_tenants: Set[str] = set()

        # Security configuration
        self._default_security_level = SecurityLevel.MEDIUM
        self._max_audit_logs = 10000
        self._rate_limit_window = timedelta(minutes=1)

    def register_tenant(
        self,
        tenant_id: str,
        security_level: SecurityLevel = SecurityLevel.MEDIUM,
        allowed_operations: Optional[Set[str]] = None,
        forbidden_operations: Optional[Set[str]] = None,
        max_query_size: int = 1024 * 1024,  # 1MB
        max_queries_per_minute: int = 100,
        require_audit_logging: bool = True,
        allow_cross_tenant_access: bool = False,
        allowed_tables: Optional[Set[str]] = None,
        forbidden_tables: Optional[Set[str]] = None,
    ) -> None:
        """
        Register a tenant with security policies.

        Args:
            tenant_id: The tenant identifier
            security_level: Security level for the tenant
            allowed_operations: Set of allowed SQL operations
            forbidden_operations: Set of forbidden SQL operations
            max_query_size: Maximum query size in bytes
            max_queries_per_minute: Rate limit for queries
            require_audit_logging: Whether to require audit logging
            allow_cross_tenant_access: Whether to allow cross-tenant access
            allowed_tables: Set of allowed table names
            forbidden_tables: Set of forbidden table names
        """
        if allowed_operations is None:
            allowed_operations = {"SELECT", "INSERT", "UPDATE", "DELETE"}
        if forbidden_operations is None:
            forbidden_operations = set()
        if allowed_tables is None:
            allowed_tables = set()
        if forbidden_tables is None:
            forbidden_tables = set()

        policy = SecurityPolicy(
            tenant_id=tenant_id,
            security_level=security_level,
            allowed_operations=allowed_operations,
            forbidden_operations=forbidden_operations,
            max_query_size=max_query_size,
            max_queries_per_minute=max_queries_per_minute,
            require_audit_logging=require_audit_logging,
            allow_cross_tenant_access=allow_cross_tenant_access,
            allowed_tables=allowed_tables,
            forbidden_tables=forbidden_tables,
        )

        self._policies[tenant_id] = policy
        logger.info(
            f"Registered tenant {tenant_id} with security level {security_level.value}"
        )

    def validate_operation(
        self,
        tenant_id: str,
        operation: str,
        query: str,
        tables: List[str],
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Validate a database operation against security policies.

        Args:
            tenant_id: The tenant identifier
            operation: The SQL operation type
            query: The SQL query
            tables: List of tables involved in the operation
            user_id: Optional user identifier
            ip_address: Optional IP address

        Returns:
            Validation result dictionary

        Raises:
            TenantSecurityError: If validation fails
        """
        try:
            # Check if tenant is blocked
            if tenant_id in self._blocked_tenants:
                raise TenantSecurityError(f"Tenant {tenant_id} is blocked")

            # Get security policy
            policy = self._policies.get(tenant_id)
            if not policy:
                # Create default policy
                self.register_tenant(tenant_id)
                policy = self._policies[tenant_id]

            # Check rate limits
            if not self._check_rate_limit(tenant_id, policy.max_queries_per_minute):
                raise TenantSecurityError(f"Rate limit exceeded for tenant {tenant_id}")

            # Check operation permissions
            if operation.upper() in policy.forbidden_operations:
                raise TenantSecurityError(
                    f"Operation {operation} is forbidden for tenant {tenant_id}"
                )

            if (
                policy.allowed_operations
                and operation.upper() not in policy.allowed_operations
            ):
                raise TenantSecurityError(
                    f"Operation {operation} is not allowed for tenant {tenant_id}"
                )

            # Check query size
            if len(query) > policy.max_query_size:
                raise TenantSecurityError(
                    f"Query size exceeds limit for tenant {tenant_id}"
                )

            # Check table permissions
            for table in tables:
                if table in policy.forbidden_tables:
                    raise TenantSecurityError(
                        f"Access to table {table} is forbidden for tenant {tenant_id}"
                    )

                if policy.allowed_tables and table not in policy.allowed_tables:
                    raise TenantSecurityError(
                        f"Access to table {table} is not allowed for tenant {tenant_id}"
                    )

            # Log audit trail
            if policy.require_audit_logging:
                self._log_audit_event(
                    tenant_id=tenant_id,
                    operation=operation,
                    query=query,
                    result="VALIDATED",
                    security_level=policy.security_level,
                    user_id=user_id,
                    ip_address=ip_address,
                    success=True,
                )

            return {
                "valid": True,
                "tenant_id": tenant_id,
                "security_level": policy.security_level.value,
                "audit_logged": policy.require_audit_logging,
                "rate_limit_remaining": policy.max_queries_per_minute
                - len(self._get_recent_queries(tenant_id)),
            }

        except TenantSecurityError as e:
            # Log security violation
            self._log_audit_event(
                tenant_id=tenant_id,
                operation=operation,
                query=query,
                result="SECURITY_VIOLATION",
                security_level=self._default_security_level,
                user_id=user_id,
                ip_address=ip_address,
                success=False,
                error_message=str(e),
            )

            logger.warning(f"Security validation failed for tenant {tenant_id}: {e}")

            return {
                "valid": False,
                "tenant_id": tenant_id,
                "error": str(e),
                "security_level": (
                    policy.security_level.value
                    if policy
                    else self._default_security_level.value
                ),
            }

    def validate_cross_tenant_access(
        self,
        requesting_tenant_id: str,
        target_tenant_id: str,
        operation: str,
        justification: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Validate cross-tenant access request.

        Args:
            requesting_tenant_id: The tenant making the request
            target_tenant_id: The tenant being accessed
            operation: The operation being performed
            justification: Optional justification for the access

        Returns:
            Validation result dictionary

        Raises:
            CrossTenantAccessError: If access is denied
        """
        requesting_policy = self._policies.get(requesting_tenant_id)
        if not requesting_policy:
            raise CrossTenantAccessError(
                f"No policy found for requesting tenant {requesting_tenant_id}"
            )

        if not requesting_policy.allow_cross_tenant_access:
            raise CrossTenantAccessError(
                f"Cross-tenant access is not allowed for tenant {requesting_tenant_id}"
            )

        # Log cross-tenant access attempt
        self._log_audit_event(
            tenant_id=requesting_tenant_id,
            operation=f"CROSS_TENANT_{operation}",
            query=f"Target tenant: {target_tenant_id}",
            result="CROSS_TENANT_ACCESS_GRANTED",
            security_level=requesting_policy.security_level,
            success=True,
        )

        return {
            "access_granted": True,
            "requesting_tenant": requesting_tenant_id,
            "target_tenant": target_tenant_id,
            "justification": justification,
            "security_level": requesting_policy.security_level.value,
        }

    def block_tenant(self, tenant_id: str, reason: str) -> None:
        """
        Block a tenant from performing database operations.

        Args:
            tenant_id: The tenant to block
            reason: Reason for blocking
        """
        self._blocked_tenants.add(tenant_id)

        self._log_audit_event(
            tenant_id=tenant_id,
            operation="TENANT_BLOCKED",
            query=f"Reason: {reason}",
            result="TENANT_BLOCKED",
            security_level=SecurityLevel.CRITICAL,
            success=True,
        )

        logger.warning(f"Tenant {tenant_id} blocked: {reason}")

    def unblock_tenant(self, tenant_id: str, reason: str) -> None:
        """
        Unblock a tenant.

        Args:
            tenant_id: The tenant to unblock
            reason: Reason for unblocking
        """
        self._blocked_tenants.discard(tenant_id)

        self._log_audit_event(
            tenant_id=tenant_id,
            operation="TENANT_UNBLOCKED",
            query=f"Reason: {reason}",
            result="TENANT_UNBLOCKED",
            security_level=SecurityLevel.HIGH,
            success=True,
        )

        logger.info(f"Tenant {tenant_id} unblocked: {reason}")

    def get_security_policy(self, tenant_id: str) -> Optional[SecurityPolicy]:
        """Get security policy for a tenant."""
        return self._policies.get(tenant_id)

    def update_security_policy(self, tenant_id: str, **updates) -> None:
        """
        Update security policy for a tenant.

        Args:
            tenant_id: The tenant identifier
            **updates: Policy updates
        """
        policy = self._policies.get(tenant_id)
        if not policy:
            raise TenantSecurityError(f"No policy found for tenant {tenant_id}")

        # Update policy fields
        for key, value in updates.items():
            if hasattr(policy, key):
                setattr(policy, key, value)

        logger.info(f"Updated security policy for tenant {tenant_id}")

    def get_audit_logs(
        self,
        tenant_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[SecurityAuditLog]:
        """
        Get audit logs with optional filtering.

        Args:
            tenant_id: Optional tenant filter
            start_time: Optional start time filter
            end_time: Optional end time filter
            limit: Maximum number of logs to return

        Returns:
            List of audit logs
        """
        logs = self._audit_logs

        # Apply filters
        if tenant_id:
            logs = [log for log in logs if log.tenant_id == tenant_id]

        if start_time:
            logs = [log for log in logs if log.timestamp >= start_time]

        if end_time:
            logs = [log for log in logs if log.timestamp <= end_time]

        # Sort by timestamp (most recent first) and limit
        logs.sort(key=lambda x: x.timestamp, reverse=True)
        return logs[:limit]

    def get_security_metrics(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get security metrics for monitoring.

        Args:
            tenant_id: Optional tenant filter

        Returns:
            Security metrics dictionary
        """
        logs = self._audit_logs
        if tenant_id:
            logs = [log for log in logs if log.tenant_id == tenant_id]

        # Calculate metrics
        total_operations = len(logs)
        successful_operations = len([log for log in logs if log.success])
        failed_operations = total_operations - successful_operations

        # Security violations
        security_violations = len(
            [
                log
                for log in logs
                if not log.success and "SECURITY_VIOLATION" in log.result
            ]
        )

        # Rate limit violations
        rate_limit_violations = len(
            [
                log
                for log in logs
                if not log.success and "rate limit" in (log.error_message or "").lower()
            ]
        )

        # Cross-tenant access attempts
        cross_tenant_attempts = len(
            [log for log in logs if "CROSS_TENANT" in log.operation]
        )

        return {
            "total_operations": total_operations,
            "successful_operations": successful_operations,
            "failed_operations": failed_operations,
            "security_violations": security_violations,
            "rate_limit_violations": rate_limit_violations,
            "cross_tenant_attempts": cross_tenant_attempts,
            "blocked_tenants": len(self._blocked_tenants),
            "registered_tenants": len(self._policies),
            "audit_logs_count": len(self._audit_logs),
        }

    # Private helper methods

    def _check_rate_limit(self, tenant_id: str, max_queries_per_minute: int) -> bool:
        """Check if tenant is within rate limits."""
        now = datetime.now()
        cutoff_time = now - self._rate_limit_window

        # Get recent queries for this tenant
        recent_queries = self._get_recent_queries(tenant_id)

        # Remove old queries
        recent_queries = [q for q in recent_queries if q > cutoff_time]
        self._rate_limits[tenant_id] = recent_queries

        # Check if under limit
        if len(recent_queries) >= max_queries_per_minute:
            return False

        # Record this query
        recent_queries.append(now)
        return True

    def _get_recent_queries(self, tenant_id: str) -> List[datetime]:
        """Get recent queries for a tenant."""
        return self._rate_limits.get(tenant_id, [])

    def _log_audit_event(
        self,
        tenant_id: str,
        operation: str,
        query: str,
        result: str,
        security_level: SecurityLevel,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        """Log an audit event."""
        audit_log = SecurityAuditLog(
            timestamp=datetime.now(),
            tenant_id=tenant_id,
            operation=operation,
            query=query,
            result=result,
            security_level=security_level,
            user_id=user_id,
            ip_address=ip_address,
            success=success,
            error_message=error_message,
        )

        self._audit_logs.append(audit_log)

        # Cleanup old logs if needed
        if len(self._audit_logs) > self._max_audit_logs:
            self._audit_logs = self._audit_logs[-self._max_audit_logs :]
