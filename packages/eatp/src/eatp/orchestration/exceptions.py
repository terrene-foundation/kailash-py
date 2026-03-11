# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Trust Orchestration Exceptions.

Custom exceptions for trust-aware orchestration operations.
"""

from typing import Optional


class OrchestrationTrustError(Exception):
    """Base exception for trust orchestration errors."""

    def __init__(self, message: str, cause: Optional[Exception] = None):
        super().__init__(message)
        self.cause = cause


class TrustVerificationFailedError(OrchestrationTrustError):
    """Trust verification failed before agent execution."""

    def __init__(
        self,
        agent_id: str,
        action: str,
        reason: str,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            f"Trust verification failed for agent '{agent_id}' "
            f"attempting action '{action}': {reason}",
            cause=cause,
        )
        self.agent_id = agent_id
        self.action = action
        self.reason = reason


class PolicyViolationError(OrchestrationTrustError):
    """Trust policy was violated."""

    def __init__(
        self,
        policy_name: str,
        agent_id: str,
        violation_details: str,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            f"Policy '{policy_name}' violated by agent '{agent_id}': {violation_details}",
            cause=cause,
        )
        self.policy_name = policy_name
        self.agent_id = agent_id
        self.violation_details = violation_details


class ConstraintLooseningError(OrchestrationTrustError):
    """Attempted to loosen constraints during delegation."""

    def __init__(
        self,
        constraint_type: str,
        parent_value: str,
        attempted_value: str,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            f"Cannot loosen {constraint_type} constraint from '{parent_value}' "
            f"to '{attempted_value}' - constraints can only be tightened",
            cause=cause,
        )
        self.constraint_type = constraint_type
        self.parent_value = parent_value
        self.attempted_value = attempted_value


class DelegationChainError(OrchestrationTrustError):
    """Error in delegation chain construction or traversal."""

    def __init__(
        self,
        message: str,
        chain_length: int = 0,
        cause: Optional[Exception] = None,
    ):
        super().__init__(f"Delegation chain error: {message}", cause=cause)
        self.chain_length = chain_length


class ContextPropagationError(OrchestrationTrustError):
    """Error propagating trust context to child agent."""

    def __init__(
        self,
        parent_agent_id: str,
        child_agent_id: str,
        reason: str,
        cause: Optional[Exception] = None,
    ):
        super().__init__(
            f"Failed to propagate context from '{parent_agent_id}' "
            f"to '{child_agent_id}': {reason}",
            cause=cause,
        )
        self.parent_agent_id = parent_agent_id
        self.child_agent_id = child_agent_id
        self.reason = reason
