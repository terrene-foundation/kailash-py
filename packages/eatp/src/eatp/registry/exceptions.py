# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Exceptions for the Agent Registry module.

These exceptions represent specific error conditions that can occur
during agent registration, discovery, and management operations.
"""

from typing import Any, Dict, List, Optional


class RegistryError(Exception):
    """
    Base exception for all registry-related errors.

    Attributes:
        message: Human-readable error message
        details: Additional context about the error
    """

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} - Details: {self.details}"
        return self.message


class AgentNotFoundError(RegistryError):
    """
    Raised when an agent is not found in the registry.

    This error occurs when attempting to access, update, or delete
    an agent that doesn't exist in the registry.
    """

    def __init__(self, agent_id: str, message: Optional[str] = None):
        msg = message or f"Agent not found: {agent_id}"
        super().__init__(msg, details={"agent_id": agent_id})
        self.agent_id = agent_id


class AgentAlreadyRegisteredError(RegistryError):
    """
    Raised when attempting to register an agent that already exists.

    This error prevents duplicate registrations and ensures
    each agent_id is unique in the registry.
    """

    def __init__(self, agent_id: str, message: Optional[str] = None):
        msg = message or f"Agent already registered: {agent_id}"
        super().__init__(msg, details={"agent_id": agent_id})
        self.agent_id = agent_id


class ValidationError(RegistryError):
    """
    Raised when registration request validation fails.

    This error contains the list of validation errors that
    prevented the registration from proceeding.
    """

    def __init__(self, errors: List[str], message: Optional[str] = None):
        msg = message or f"Validation failed: {', '.join(errors)}"
        super().__init__(msg, details={"errors": errors})
        self.errors = errors


class TrustVerificationError(RegistryError):
    """
    Raised when trust verification fails during registration.

    This error indicates that the agent's trust chain could not
    be verified, or the chain doesn't match the registration request.
    """

    def __init__(
        self,
        agent_id: str,
        reason: str,
        message: Optional[str] = None,
    ):
        msg = message or f"Trust verification failed for {agent_id}: {reason}"
        super().__init__(msg, details={"agent_id": agent_id, "reason": reason})
        self.agent_id = agent_id
        self.reason = reason


class RegistryStoreError(RegistryError):
    """
    Raised when a database operation fails in the registry store.

    This error wraps underlying database errors and provides
    context about what operation was being performed.
    """

    def __init__(
        self,
        operation: str,
        message: str,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            details={
                "operation": operation,
                "original_error": str(original_error) if original_error else None,
            },
        )
        self.operation = operation
        self.original_error = original_error
