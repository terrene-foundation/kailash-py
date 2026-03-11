"""Trust-Aware Multi-Tenancy for DataFlow (CARE-021).

This module provides cross-tenant delegation management for DataFlow,
enabling trust-aware data access across tenant boundaries with explicit
EATP delegation chains.

Design Principles:
    - No hard dependencies on Kaizen or Core SDK trust modules
    - Graceful degradation when trust modules not available
    - All TenantTrustManager methods are async for consistency
    - Thread-safe with no shared mutable state between instances
    - Explicit error handling (never use defaults for fallbacks)
    - Self-delegation (source == target) always rejected

Key Classes:
    - CrossTenantDelegation: Represents a delegation record between tenants
    - TenantTrustManager: Manages cross-tenant delegations and verification

Example:
    >>> manager = TenantTrustManager(strict_mode=True)
    >>> delegation = await manager.create_cross_tenant_delegation(
    ...     source_tenant_id="tenant-a",
    ...     target_tenant_id="tenant-b",
    ...     delegating_agent_id="agent-a",
    ...     receiving_agent_id="agent-b",
    ...     allowed_models=["User"],
    ... )
    >>> allowed, reason = await manager.verify_cross_tenant_access(
    ...     source_tenant_id="tenant-a",
    ...     target_tenant_id="tenant-b",
    ...     agent_id="agent-b",
    ...     model="User",
    ...     operation="SELECT",
    ... )
    >>> print(allowed)  # True

Version:
    Added in: v0.11.0
    Part of: CARE-021 trust implementation
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# CARE-058b: Valid operations allowlist for cross-tenant delegations
# Only these operations are permitted in allowed_operations sets
VALID_OPERATIONS: frozenset = frozenset({"SELECT", "INSERT", "UPDATE", "DELETE"})


# === Data Classes ===


@dataclass
class CrossTenantDelegation:
    """Represents a cross-tenant delegation record.

    A delegation allows an agent in one tenant to access data in another tenant,
    subject to specific constraints on models, operations, and optional row filters.

    Attributes:
        delegation_id: Unique identifier for this delegation (UUID format)
        source_tenant_id: Tenant providing data access
        target_tenant_id: Tenant receiving data access
        delegating_agent_id: Agent in source tenant granting access
        receiving_agent_id: Agent in target tenant receiving access
        allowed_models: List of model names that can be accessed
        allowed_operations: Set of allowed operations (SELECT, INSERT, UPDATE, DELETE)
        row_filter: Optional row-level filter to restrict data access
        expires_at: Optional delegation expiry time
        created_at: Creation timestamp (UTC)
        revoked: Whether this delegation has been revoked
        revoked_at: Timestamp when delegation was revoked
        revoked_reason: Reason for revocation

    Example:
        >>> delegation = CrossTenantDelegation(
        ...     delegation_id="del-001",
        ...     source_tenant_id="tenant-source",
        ...     target_tenant_id="tenant-target",
        ...     delegating_agent_id="agent-delegator",
        ...     receiving_agent_id="agent-receiver",
        ...     allowed_models=["User"],
        ...     allowed_operations={"SELECT"},
        ...     row_filter=None,
        ...     expires_at=None,
        ...     created_at=datetime.now(timezone.utc),
        ... )
    """

    delegation_id: str
    source_tenant_id: str
    target_tenant_id: str
    delegating_agent_id: str
    receiving_agent_id: str
    allowed_models: List[str]
    allowed_operations: Set[str]
    row_filter: Optional[Dict[str, Any]]
    expires_at: Optional[datetime]
    created_at: datetime
    revoked: bool = False
    revoked_at: Optional[datetime] = None
    revoked_reason: Optional[str] = None

    def is_expired(self) -> bool:
        """Check if this delegation has expired.

        Returns:
            True if expires_at is set and is in the past, False otherwise.

        Note:
            A delegation without expires_at never expires (returns False).
        """
        if self.expires_at is None:
            return False

        now = datetime.now(timezone.utc)
        return self.expires_at <= now

    def is_active(self) -> bool:
        """Check if this delegation is currently active.

        A delegation is active if it is not expired and not revoked.

        Returns:
            True if the delegation is active, False otherwise.
        """
        if self.revoked:
            return False

        if self.is_expired():
            return False

        return True

    def allows_access(self, model: str, operation: str, agent_id: str) -> bool:
        """Check if this delegation allows the requested access.

        Args:
            model: The model name being accessed
            operation: The operation being performed (SELECT, INSERT, etc.)
            agent_id: The agent requesting access

        Returns:
            True if access is allowed, False otherwise.

        Note:
            Access is denied if:
            - The delegation is not active (expired or revoked)
            - The agent is not the receiving agent
            - The model is not in allowed_models
            - The operation is not in allowed_operations
        """
        # Check if delegation is active
        if not self.is_active():
            return False

        # Check agent matches
        if agent_id != self.receiving_agent_id:
            return False

        # Check model is allowed
        if model not in self.allowed_models:
            return False

        # Check operation is allowed
        if operation not in self.allowed_operations:
            return False

        return True

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this delegation to a dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "delegation_id": self.delegation_id,
            "source_tenant_id": self.source_tenant_id,
            "target_tenant_id": self.target_tenant_id,
            "delegating_agent_id": self.delegating_agent_id,
            "receiving_agent_id": self.receiving_agent_id,
            "allowed_models": self.allowed_models,
            "allowed_operations": list(self.allowed_operations),
            "row_filter": self.row_filter,
            "expires_at": (self.expires_at.isoformat() if self.expires_at else None),
            "created_at": self.created_at.isoformat(),
            "revoked": self.revoked,
            "revoked_at": (self.revoked_at.isoformat() if self.revoked_at else None),
            "revoked_reason": self.revoked_reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CrossTenantDelegation":
        """Deserialize a delegation from a dictionary.

        Args:
            data: Dictionary containing delegation data

        Returns:
            CrossTenantDelegation instance

        Raises:
            KeyError: If required fields are missing
            ValueError: If data format is invalid
        """
        # Parse datetime fields
        expires_at = None
        if data.get("expires_at"):
            expires_at = datetime.fromisoformat(data["expires_at"])

        created_at_str = data.get("created_at")
        if created_at_str:
            created_at = datetime.fromisoformat(created_at_str)
        else:
            created_at = datetime.now(timezone.utc)

        revoked_at = None
        if data.get("revoked_at"):
            revoked_at = datetime.fromisoformat(data["revoked_at"])

        # Parse allowed_operations - could be list or set
        allowed_ops = data.get("allowed_operations", set())
        if isinstance(allowed_ops, list):
            allowed_ops = set(allowed_ops)

        return cls(
            delegation_id=data["delegation_id"],
            source_tenant_id=data["source_tenant_id"],
            target_tenant_id=data["target_tenant_id"],
            delegating_agent_id=data["delegating_agent_id"],
            receiving_agent_id=data["receiving_agent_id"],
            allowed_models=data["allowed_models"],
            allowed_operations=allowed_ops,
            row_filter=data.get("row_filter"),
            expires_at=expires_at,
            created_at=created_at,
            revoked=data.get("revoked", False),
            revoked_at=revoked_at,
            revoked_reason=data.get("revoked_reason"),
        )


# === Tenant Trust Manager ===


class TenantTrustManager:
    """Manages cross-tenant delegations and access verification.

    This class provides methods for creating, verifying, and managing
    cross-tenant delegation chains. It supports both strict and non-strict
    enforcement modes.

    Attributes:
        strict_mode: If True, cross-tenant access requires explicit delegation.
                    If False, access is logged but allowed.

    Example:
        >>> manager = TenantTrustManager(strict_mode=True)
        >>> delegation = await manager.create_cross_tenant_delegation(
        ...     source_tenant_id="tenant-a",
        ...     target_tenant_id="tenant-b",
        ...     delegating_agent_id="agent-a",
        ...     receiving_agent_id="agent-b",
        ...     allowed_models=["User"],
        ... )
        >>> allowed, reason = await manager.verify_cross_tenant_access(
        ...     source_tenant_id="tenant-a",
        ...     target_tenant_id="tenant-b",
        ...     agent_id="agent-b",
        ...     model="User",
        ...     operation="SELECT",
        ... )
    """

    def __init__(
        self,
        strict_mode: bool = True,
    ) -> None:
        """Initialize TenantTrustManager.

        Args:
            strict_mode: If True, cross-tenant access requires explicit
                        delegation. If False, access is logged but allowed.
        """
        self._delegations: Dict[str, CrossTenantDelegation] = {}
        self._strict_mode = strict_mode
        # ROUND7-001: Thread-safe access to _delegations dict
        self._lock = threading.Lock()

    async def create_cross_tenant_delegation(
        self,
        source_tenant_id: str,
        target_tenant_id: str,
        delegating_agent_id: str,
        receiving_agent_id: str,
        allowed_models: List[str],
        allowed_operations: Optional[Set[str]] = None,
        row_filter: Optional[Dict[str, Any]] = None,
        expires_at: Optional[datetime] = None,
    ) -> CrossTenantDelegation:
        """Create a cross-tenant delegation record.

        Args:
            source_tenant_id: Tenant providing data access
            target_tenant_id: Tenant receiving data access
            delegating_agent_id: Agent in source tenant granting access
            receiving_agent_id: Agent in target tenant receiving access
            allowed_models: List of model names that can be accessed
            allowed_operations: Set of allowed operations (default: {"SELECT"})
            row_filter: Optional row-level filter to restrict data access
            expires_at: Optional delegation expiry time

        Returns:
            The created CrossTenantDelegation

        Raises:
            ValueError: If source_tenant_id == target_tenant_id (self-delegation)
        """
        # Validate: source != target
        if source_tenant_id == target_tenant_id:
            raise ValueError(
                f"Cannot create self-delegation: source and target tenant "
                f"are the same ({source_tenant_id})"
            )

        # Default operations to SELECT only
        if allowed_operations is None:
            allowed_operations = {"SELECT"}

        # CARE-058b: Validate allowed_operations against valid operations allowlist
        invalid_operations = allowed_operations - VALID_OPERATIONS
        if invalid_operations:
            raise ValueError(
                f"Invalid operations: {sorted(invalid_operations)}. "
                f"Valid operations are: {sorted(VALID_OPERATIONS)}"
            )

        # Generate UUID for delegation
        delegation_id = str(uuid.uuid4())

        # Create delegation
        delegation = CrossTenantDelegation(
            delegation_id=delegation_id,
            source_tenant_id=source_tenant_id,
            target_tenant_id=target_tenant_id,
            delegating_agent_id=delegating_agent_id,
            receiving_agent_id=receiving_agent_id,
            allowed_models=allowed_models,
            allowed_operations=allowed_operations,
            row_filter=row_filter,
            expires_at=expires_at,
            created_at=datetime.now(timezone.utc),
        )

        # ROUND7-001: Thread-safe delegation storage
        with self._lock:
            self._delegations[delegation_id] = delegation

        logger.info(
            f"Created cross-tenant delegation: {delegation_id} "
            f"({source_tenant_id} -> {target_tenant_id})"
        )

        return delegation

    async def verify_cross_tenant_access(
        self,
        source_tenant_id: str,
        target_tenant_id: str,
        agent_id: str,
        model: str,
        operation: str,
    ) -> Tuple[bool, Optional[str]]:
        """Verify that cross-tenant access is authorized.

        Args:
            source_tenant_id: Tenant whose data is being accessed
            target_tenant_id: Tenant requesting access
            agent_id: Agent requesting access
            model: Model being accessed
            operation: Operation being performed

        Returns:
            Tuple of (allowed, reason_if_denied).
            If allowed is True, reason is None.
            If allowed is False, reason contains explanation.

        Note:
            Same-tenant access (source == target) is always allowed.
            Cross-tenant access requires an active delegation in strict mode.
        """
        # Same tenant access is always allowed
        if source_tenant_id == target_tenant_id:
            return (True, None)

        # ROUND7-001: Thread-safe delegation iteration
        with self._lock:
            for delegation in self._delegations.values():
                if (
                    delegation.source_tenant_id == source_tenant_id
                    and delegation.target_tenant_id == target_tenant_id
                    and delegation.allows_access(model, operation, agent_id)
                ):
                    logger.debug(
                        f"Cross-tenant access authorized via delegation "
                        f"{delegation.delegation_id}"
                    )
                    return (True, None)

        # No valid delegation found
        if self._strict_mode:
            reason = (
                f"Cross-tenant access denied: no valid delegation from "
                f"{source_tenant_id} to {target_tenant_id} for agent {agent_id} "
                f"on model {model} with operation {operation}"
            )
            logger.warning(reason)
            return (False, reason)
        else:
            # Non-strict mode: log warning but allow
            logger.warning(
                f"Cross-tenant access allowed (non-strict mode): "
                f"{source_tenant_id} -> {target_tenant_id}, "
                f"agent={agent_id}, model={model}, operation={operation}"
            )
            return (True, None)

    async def revoke_delegation(
        self,
        delegation_id: str,
        reason: Optional[str] = None,
    ) -> bool:
        """Revoke a cross-tenant delegation.

        Args:
            delegation_id: ID of the delegation to revoke
            reason: Optional reason for revocation

        Returns:
            True if delegation was found and revoked, False if not found.
        """
        # ROUND7-001: Thread-safe revocation
        with self._lock:
            if delegation_id not in self._delegations:
                logger.warning(f"Cannot revoke delegation: {delegation_id} not found")
                return False

            delegation = self._delegations[delegation_id]
            delegation.revoked = True
            delegation.revoked_at = datetime.now(timezone.utc)
            delegation.revoked_reason = reason

        logger.info(
            f"Revoked delegation {delegation_id}: {reason or 'no reason provided'}"
        )

        return True

    async def list_delegations(
        self,
        tenant_id: Optional[str] = None,
        active_only: bool = True,
    ) -> List[CrossTenantDelegation]:
        """List delegations, optionally filtered by tenant.

        Args:
            tenant_id: If provided, filter to delegations where this tenant
                      is either source or target
            active_only: If True, only return active (non-expired, non-revoked)
                        delegations

        Returns:
            List of matching CrossTenantDelegation objects.
        """
        result: List[CrossTenantDelegation] = []

        # ROUND7-001: Thread-safe delegation iteration
        with self._lock:
            for delegation in self._delegations.values():
                # Filter by active status
                if active_only and not delegation.is_active():
                    continue

                # Filter by tenant
                if tenant_id is not None:
                    if (
                        delegation.source_tenant_id != tenant_id
                        and delegation.target_tenant_id != tenant_id
                    ):
                        continue

                result.append(delegation)

        return result

    async def get_delegation(
        self,
        delegation_id: str,
    ) -> Optional[CrossTenantDelegation]:
        """Get a specific delegation by ID.

        Args:
            delegation_id: ID of the delegation to retrieve

        Returns:
            The CrossTenantDelegation if found, None otherwise.
        """
        # ROUND7-001: Thread-safe delegation access
        with self._lock:
            return self._delegations.get(delegation_id)

    async def get_active_delegations_for_agent(
        self,
        agent_id: str,
    ) -> List[CrossTenantDelegation]:
        """Get all active delegations where agent is the receiver.

        Args:
            agent_id: ID of the receiving agent

        Returns:
            List of active CrossTenantDelegation objects where this agent
            is the receiving_agent_id.
        """
        result: List[CrossTenantDelegation] = []

        # ROUND7-001: Thread-safe delegation iteration
        with self._lock:
            for delegation in self._delegations.values():
                if not delegation.is_active():
                    continue

                if delegation.receiving_agent_id == agent_id:
                    result.append(delegation)

        return result

    def get_row_filter_for_access(
        self,
        source_tenant_id: str,
        target_tenant_id: str,
        agent_id: str,
        model: str,
    ) -> Optional[Dict[str, Any]]:
        """Get the row filter that should be applied for cross-tenant access.

        This method finds the applicable delegation and extracts its row filter.
        If multiple delegations match, the first active one is used.

        Args:
            source_tenant_id: Tenant whose data is being accessed
            target_tenant_id: Tenant requesting access
            agent_id: Agent requesting access
            model: Model being accessed

        Returns:
            The row filter dict from the matching delegation, or None if
            no matching delegation exists or the delegation has no row filter.
        """
        # ROUND7-001: Thread-safe delegation iteration
        with self._lock:
            for delegation in self._delegations.values():
                if (
                    delegation.source_tenant_id == source_tenant_id
                    and delegation.target_tenant_id == target_tenant_id
                    and delegation.receiving_agent_id == agent_id
                    and model in delegation.allowed_models
                    and delegation.is_active()
                ):
                    return delegation.row_filter

        return None
