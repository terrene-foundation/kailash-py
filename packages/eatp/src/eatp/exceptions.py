# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP Exception Hierarchy.

Provides specific exception types for trust-related errors,
enabling precise error handling and informative error messages.
"""

from typing import Any, List, Optional


class TrustError(Exception):
    """Base exception for all trust-related errors."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} - Details: {self.details}"
        return self.message


class AuthorityNotFoundError(TrustError):
    """Raised when a specified authority does not exist."""

    def __init__(self, authority_id: str):
        super().__init__(
            f"Authority not found: {authority_id}",
            details={"authority_id": authority_id},
        )
        self.authority_id = authority_id


class AuthorityInactiveError(TrustError):
    """Raised when attempting to use an inactive authority."""

    def __init__(self, authority_id: str, reason: Optional[str] = None):
        message = f"Authority is inactive: {authority_id}"
        if reason:
            message += f" ({reason})"
        super().__init__(
            message, details={"authority_id": authority_id, "reason": reason}
        )
        self.authority_id = authority_id
        self.reason = reason


class TrustChainNotFoundError(TrustError):
    """Raised when an agent has no trust chain."""

    def __init__(self, agent_id: str):
        super().__init__(
            f"No trust chain found for agent: {agent_id}",
            details={"agent_id": agent_id},
        )
        self.agent_id = agent_id


class InvalidTrustChainError(TrustError):
    """Raised when a trust chain fails verification."""

    def __init__(
        self, agent_id: str, reason: str, violations: Optional[List[str]] = None
    ):
        super().__init__(
            f"Invalid trust chain for agent {agent_id}: {reason}",
            details={
                "agent_id": agent_id,
                "reason": reason,
                "violations": violations or [],
            },
        )
        self.agent_id = agent_id
        self.reason = reason
        self.violations = violations or []


class CapabilityNotFoundError(TrustError):
    """Raised when an agent lacks a required capability."""

    def __init__(self, agent_id: str, capability: str):
        super().__init__(
            f"Agent {agent_id} does not have capability: {capability}",
            details={"agent_id": agent_id, "capability": capability},
        )
        self.agent_id = agent_id
        self.capability = capability


class ConstraintViolationError(TrustError):
    """Raised when an action violates trust constraints."""

    def __init__(
        self,
        message: str,
        violations: Optional[List[dict]] = None,
        agent_id: Optional[str] = None,
        action: Optional[str] = None,
    ):
        super().__init__(
            message,
            details={
                "violations": violations or [],
                "agent_id": agent_id,
                "action": action,
            },
        )
        self.violations = violations or []
        self.agent_id = agent_id
        self.action = action


class DelegationError(TrustError):
    """Raised when a delegation operation fails."""

    def __init__(
        self,
        message: str,
        delegator_id: Optional[str] = None,
        delegatee_id: Optional[str] = None,
        reason: Optional[str] = None,
    ):
        super().__init__(
            message,
            details={
                "delegator_id": delegator_id,
                "delegatee_id": delegatee_id,
                "reason": reason,
            },
        )
        self.delegator_id = delegator_id
        self.delegatee_id = delegatee_id
        self.reason = reason


class DelegationCycleError(DelegationError):
    """
    Raised when a cycle is detected in the delegation chain.

    CARE-003: Cycle detection prevents infinite loops and DoS vulnerabilities
    in delegation chains by detecting when a delegation would create a
    circular reference.
    """

    def __init__(self, cycle_path: List[Any]):
        self.cycle_path = cycle_path
        cycle_str = " -> ".join(str(p) for p in cycle_path)
        super().__init__(
            f"Delegation cycle detected: {cycle_str}",
            reason="cycle_detected",
        )


class InvalidSignatureError(TrustError):
    """Raised when a cryptographic signature is invalid."""

    def __init__(
        self,
        message: str = "Invalid signature",
        record_type: Optional[str] = None,
        record_id: Optional[str] = None,
    ):
        super().__init__(
            message, details={"record_type": record_type, "record_id": record_id}
        )
        self.record_type = record_type
        self.record_id = record_id


class VerificationFailedError(TrustError):
    """Raised when trust verification fails for an action."""

    def __init__(
        self,
        agent_id: str,
        action: str,
        reason: str,
        violations: Optional[List[dict]] = None,
    ):
        super().__init__(
            f"Trust verification failed for {agent_id} attempting {action}: {reason}",
            details={
                "agent_id": agent_id,
                "action": action,
                "reason": reason,
                "violations": violations or [],
            },
        )
        self.agent_id = agent_id
        self.action = action
        self.reason = reason
        self.violations = violations or []


class DelegationExpiredError(DelegationError):
    """Raised when attempting to use an expired delegation."""

    def __init__(self, delegation_id: str, expired_at: str):
        super().__init__(
            f"Delegation {delegation_id} expired at {expired_at}", reason="expired"
        )
        self.delegation_id = delegation_id
        self.expired_at = expired_at


class AgentAlreadyEstablishedError(TrustError):
    """Raised when trying to establish trust for an agent that already has it."""

    def __init__(self, agent_id: str):
        super().__init__(
            f"Agent {agent_id} already has an established trust chain",
            details={"agent_id": agent_id},
        )
        self.agent_id = agent_id


# PostgresTrustStore specific exceptions


class TrustStoreError(TrustError):
    """Base exception for trust store operations."""

    pass


class TrustChainInvalidError(TrustStoreError):
    """Raised when a trust chain fails validation before storage."""

    def __init__(self, message: str, agent_id: Optional[str] = None):
        super().__init__(message, details={"agent_id": agent_id})
        self.agent_id = agent_id


class TrustStoreDatabaseError(TrustStoreError):
    """Raised when a database operation fails."""

    def __init__(self, message: str, operation: Optional[str] = None):
        super().__init__(message, details={"operation": operation})
        self.operation = operation
