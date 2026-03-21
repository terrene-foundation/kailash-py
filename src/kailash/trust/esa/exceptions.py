# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
ESA Exception Hierarchy.

Provides specific exception types for Enterprise System Agent errors,
enabling precise error handling and informative error messages.
"""

from typing import Any, Dict, List, Optional


class ESAError(Exception):
    """Base exception for all ESA-related errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        """
        Initialize ESA error.

        Args:
            message: Human-readable error message
            details: Additional context as key-value pairs
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        """Format error message with details."""
        if self.details:
            return f"{self.message} - Details: {self.details}"
        return self.message


class ESANotEstablishedError(ESAError):
    """Raised when ESA operations are attempted before trust is established."""

    def __init__(self, system_id: str):
        """
        Initialize not established error.

        Args:
            system_id: The system ID that lacks established trust
        """
        super().__init__(
            f"ESA not established for system: {system_id}. Call establish_trust() before executing operations.",
            details={"system_id": system_id},
        )
        self.system_id = system_id


class ESACapabilityNotFoundError(ESAError):
    """Raised when a requested capability is not available on the ESA."""

    def __init__(
        self,
        capability: str,
        system_id: str,
        available_capabilities: Optional[List[str]] = None,
    ):
        """
        Initialize capability not found error.

        Args:
            capability: The requested capability that was not found
            system_id: The system ID being accessed
            available_capabilities: List of available capabilities (optional)
        """
        message = f"Capability '{capability}' not found on system '{system_id}'"
        if available_capabilities:
            message += f". Available: {', '.join(available_capabilities[:5])}"
            if len(available_capabilities) > 5:
                message += f" (and {len(available_capabilities) - 5} more)"

        super().__init__(
            message,
            details={
                "capability": capability,
                "system_id": system_id,
                "available_capabilities": available_capabilities or [],
            },
        )
        self.capability = capability
        self.system_id = system_id
        self.available_capabilities = available_capabilities or []


class ESAOperationError(ESAError):
    """Raised when an ESA operation fails during execution."""

    def __init__(
        self,
        operation: str,
        system_id: str,
        reason: str,
        original_error: Optional[Exception] = None,
    ):
        """
        Initialize operation error.

        Args:
            operation: The operation that failed
            system_id: The system ID being accessed
            reason: Human-readable reason for failure
            original_error: Original exception that caused the failure (optional)
        """
        message = f"Operation '{operation}' failed on system '{system_id}': {reason}"

        super().__init__(
            message,
            details={
                "operation": operation,
                "system_id": system_id,
                "reason": reason,
                "original_error": str(original_error) if original_error else None,
            },
        )
        self.operation = operation
        self.system_id = system_id
        self.reason = reason
        self.original_error = original_error


class ESAConnectionError(ESAError):
    """Raised when ESA cannot connect to the underlying system."""

    def __init__(
        self,
        system_id: str,
        endpoint: str,
        reason: str,
        original_error: Optional[Exception] = None,
    ):
        """
        Initialize connection error.

        Args:
            system_id: The system ID
            endpoint: The connection endpoint
            reason: Human-readable reason for connection failure
            original_error: Original exception (optional)
        """
        message = f"Connection failed to system '{system_id}' at '{endpoint}': {reason}"

        super().__init__(
            message,
            details={
                "system_id": system_id,
                "endpoint": endpoint,
                "reason": reason,
                "original_error": str(original_error) if original_error else None,
            },
        )
        self.system_id = system_id
        self.endpoint = endpoint
        self.reason = reason
        self.original_error = original_error


class ESAAuthorizationError(ESAError):
    """Raised when an agent is not authorized for the requested operation."""

    def __init__(
        self,
        requesting_agent_id: str,
        operation: str,
        system_id: str,
        reason: str,
        required_capability: Optional[str] = None,
    ):
        """
        Initialize authorization error.

        Args:
            requesting_agent_id: Agent that attempted the operation
            operation: The operation that was denied
            system_id: The system ID
            reason: Human-readable reason for denial
            required_capability: The capability required for authorization (optional)
        """
        message = (
            f"Agent '{requesting_agent_id}' not authorized for operation "
            f"'{operation}' on system '{system_id}': {reason}"
        )
        if required_capability:
            message += f" (requires capability: {required_capability})"

        super().__init__(
            message,
            details={
                "requesting_agent_id": requesting_agent_id,
                "operation": operation,
                "system_id": system_id,
                "reason": reason,
                "required_capability": required_capability,
            },
        )
        self.requesting_agent_id = requesting_agent_id
        self.operation = operation
        self.system_id = system_id
        self.reason = reason
        self.required_capability = required_capability


class ESADelegationError(ESAError):
    """Raised when capability delegation fails."""

    def __init__(self, capability: str, delegatee_id: str, system_id: str, reason: str):
        """
        Initialize delegation error.

        Args:
            capability: The capability that failed to delegate
            delegatee_id: Agent that was to receive the capability
            system_id: The system ID
            reason: Human-readable reason for failure
        """
        message = (
            f"Failed to delegate capability '{capability}' to agent '{delegatee_id}' for system '{system_id}': {reason}"
        )

        super().__init__(
            message,
            details={
                "capability": capability,
                "delegatee_id": delegatee_id,
                "system_id": system_id,
                "reason": reason,
            },
        )
        self.capability = capability
        self.delegatee_id = delegatee_id
        self.system_id = system_id
        self.reason = reason
