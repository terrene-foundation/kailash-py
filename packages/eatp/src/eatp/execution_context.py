# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Execution context for EATP trust propagation.

This module provides the HumanOrigin and ExecutionContext classes that
enable tracing every agent action back to the human who authorized it.

EATP (Enterprise Agent Trust Protocol) requires that every action in an
agentic system must be traceable to a human who authorized it. This module
provides the core data structures and context propagation mechanisms.

Key Components:
- HumanOrigin: Immutable record of the human who authorized an execution chain
- ExecutionContext: Ambient context that flows through all EATP operations
- Context variable functions for async-safe propagation

Reference: docs/plans/eatp-integration/05-architecture-design.md

Author: Kaizen Framework Team
Created: 2026-01-02
"""

import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class HumanOrigin:
    """
    Immutable record of the human who authorized an execution chain.

    This is the MOST CRITICAL data structure in EATP.
    It MUST be present in every operation and CANNOT be modified.

    The HumanOrigin is created when a human authenticates and initiates
    a task. It then flows through every delegation and audit record,
    ensuring complete traceability.

    Attributes:
        human_id: Unique identifier (email or user_id from auth system)
        display_name: Human-readable name for UI display
        auth_provider: Authentication provider (okta, azure_ad, etc.)
        session_id: Session ID for correlation and revocation
        authenticated_at: When the human authenticated

    Example:
        >>> origin = HumanOrigin(
        ...     human_id="alice@corp.com",
        ...     display_name="Alice Chen",
        ...     auth_provider="okta",
        ...     session_id="sess-123",
        ...     authenticated_at=datetime.now(timezone.utc)
        ... )
        >>> # Immutable - cannot be modified
        >>> origin.human_id = "bob@corp.com"  # Raises FrozenInstanceError
    """

    human_id: str
    display_name: str
    auth_provider: str
    session_id: str
    authenticated_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize to dictionary for storage and transport.

        Returns:
            Dictionary representation with ISO-formatted datetime
        """
        return {
            "human_id": self.human_id,
            "display_name": self.display_name,
            "auth_provider": self.auth_provider,
            "session_id": self.session_id,
            "authenticated_at": self.authenticated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HumanOrigin":
        """
        Deserialize from dictionary.

        Args:
            data: Dictionary with HumanOrigin fields

        Returns:
            HumanOrigin instance
        """
        authenticated_at = data["authenticated_at"]
        if isinstance(authenticated_at, str):
            authenticated_at = datetime.fromisoformat(authenticated_at)

        return cls(
            human_id=data["human_id"],
            display_name=data["display_name"],
            auth_provider=data["auth_provider"],
            session_id=data["session_id"],
            authenticated_at=authenticated_at,
        )

    def __str__(self) -> str:
        """Return human-readable representation."""
        return f"HumanOrigin({self.human_id}, provider={self.auth_provider})"


@dataclass
class ExecutionContext:
    """
    Context that flows through all EATP operations.

    This is the "ambient" context that every operation has access to.
    It provides the HumanOrigin and accumulated constraints.

    The ExecutionContext carries:
    - The human who ultimately authorized this chain (immutable)
    - The delegation chain showing the path from human to current agent
    - Accumulated constraints that can only be tightened
    - A trace ID for correlating all operations in this chain

    Attributes:
        human_origin: The human who ultimately authorized this chain
        delegation_chain: List of agent IDs from human to current agent
        delegation_depth: How deep in the delegation chain (0 = direct from human)
        constraints: Accumulated constraints (tightened through delegation)
        trace_id: Unique ID for correlating all operations in this chain

    Example:
        >>> origin = HumanOrigin(human_id="alice@corp.com", ...)
        >>> ctx = ExecutionContext(
        ...     human_origin=origin,
        ...     delegation_chain=["pseudo:alice@corp.com"],
        ...     delegation_depth=0,
        ...     constraints={"cost_limit": 10000}
        ... )
        >>>
        >>> # Delegate to an agent - creates new context with preserved human_origin
        >>> delegated_ctx = ctx.with_delegation("agent-a", {"cost_limit": 1000})
        >>> assert delegated_ctx.human_origin is origin  # Same reference!
    """

    human_origin: HumanOrigin
    delegation_chain: List[str] = field(default_factory=list)
    delegation_depth: int = 0
    constraints: Dict[str, Any] = field(default_factory=dict)
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def with_delegation(
        self,
        delegatee_id: str,
        additional_constraints: Optional[Dict[str, Any]] = None,
    ) -> "ExecutionContext":
        """
        Create new context for a delegated agent.

        IMPORTANT: human_origin is PRESERVED (never changes).
        Constraints are MERGED (can only tighten).

        This method creates a new ExecutionContext suitable for passing
        to a delegated agent. The human_origin reference is preserved
        exactly (same object), ensuring traceability.

        Args:
            delegatee_id: ID of the agent receiving delegation
            additional_constraints: New constraints to add (must be tighter)

        Returns:
            New ExecutionContext for the delegated agent

        Example:
            >>> parent_ctx = ExecutionContext(human_origin=origin, ...)
            >>> child_ctx = parent_ctx.with_delegation(
            ...     "worker-agent",
            ...     {"cost_limit": 500}  # Tighter than parent's 1000
            ... )
            >>> assert child_ctx.human_origin is parent_ctx.human_origin
            >>> assert "worker-agent" in child_ctx.delegation_chain
        """
        new_chain = self.delegation_chain + [delegatee_id]
        merged_constraints = {**self.constraints}
        if additional_constraints:
            merged_constraints.update(additional_constraints)

        return ExecutionContext(
            human_origin=self.human_origin,  # PRESERVED - never changes!
            delegation_chain=new_chain,
            delegation_depth=self.delegation_depth + 1,
            constraints=merged_constraints,
            trace_id=self.trace_id,  # Same trace for correlation
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize to dictionary for storage and transport.

        Returns:
            Dictionary representation
        """
        return {
            "human_origin": self.human_origin.to_dict(),
            "delegation_chain": self.delegation_chain,
            "delegation_depth": self.delegation_depth,
            "constraints": self.constraints,
            "trace_id": self.trace_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionContext":
        """
        Deserialize from dictionary.

        Args:
            data: Dictionary with ExecutionContext fields

        Returns:
            ExecutionContext instance
        """
        return cls(
            human_origin=HumanOrigin.from_dict(data["human_origin"]),
            delegation_chain=data.get("delegation_chain", []),
            delegation_depth=data.get("delegation_depth", 0),
            constraints=data.get("constraints", {}),
            trace_id=data.get("trace_id", str(uuid.uuid4())),
        )

    def __str__(self) -> str:
        """Return human-readable representation."""
        chain_str = (
            " -> ".join(self.delegation_chain) if self.delegation_chain else "[]"
        )
        return f"ExecutionContext(human={self.human_origin.human_id}, chain={chain_str}, depth={self.delegation_depth})"


# =============================================================================
# Context Variable for Async-Safe Propagation
# =============================================================================

# Context variable for async-safe propagation
# Using ContextVar ensures each async task has its own isolated context
_execution_context: ContextVar[Optional[ExecutionContext]] = ContextVar(
    "execution_context", default=None
)


def get_current_context() -> Optional[ExecutionContext]:
    """
    Get the current execution context.

    Returns None if no context is set. In a properly configured EATP
    system, this indicates a bug - all operations should have a context.

    Returns:
        Current ExecutionContext or None if not set

    Example:
        >>> with execution_context(ctx):
        ...     current = get_current_context()
        ...     assert current is ctx
    """
    return _execution_context.get()


def set_current_context(ctx: ExecutionContext) -> None:
    """
    Set the current execution context.

    Note: Prefer using the execution_context() context manager for
    automatic cleanup. Direct use of set_current_context() requires
    manual cleanup via reset.

    Args:
        ctx: ExecutionContext to set as current
    """
    _execution_context.set(ctx)


def require_current_context() -> ExecutionContext:
    """
    Get the current execution context, raising if not set.

    Use this in operations that require a context to be present.

    Returns:
        Current ExecutionContext

    Raises:
        RuntimeError: If no context is set

    Example:
        >>> # Inside a trusted operation
        >>> ctx = require_current_context()
        >>> human_id = ctx.human_origin.human_id
    """
    ctx = _execution_context.get()
    if ctx is None:
        raise RuntimeError(
            "No ExecutionContext available. All EATP operations must have a "
            "human_origin. Use PseudoAgent to initiate trust chains or wrap "
            "operations with execution_context()."
        )
    return ctx


@contextmanager
def execution_context(ctx: ExecutionContext):
    """
    Context manager for setting execution context.

    This is the preferred way to set the execution context as it
    ensures proper cleanup after the block exits.

    The context is automatically propagated through async/await calls
    and nested function calls within the block.

    Args:
        ctx: ExecutionContext to set for this block

    Yields:
        The ExecutionContext for convenience

    Example:
        >>> ctx = ExecutionContext(human_origin=origin, ...)
        >>> with execution_context(ctx):
        ...     # All operations in this block will have access to ctx
        ...     await agent.execute_async(...)
        ...     # Even nested async calls have access
        ...     await nested_operation()
    """
    token = _execution_context.set(ctx)
    try:
        yield ctx
    finally:
        _execution_context.reset(token)


# =============================================================================
# Utility Functions
# =============================================================================


def get_human_origin() -> Optional[HumanOrigin]:
    """
    Get the HumanOrigin from the current context.

    Convenience function for quickly accessing the human origin.

    Returns:
        HumanOrigin if context is set, None otherwise
    """
    ctx = get_current_context()
    return ctx.human_origin if ctx else None


def get_delegation_chain() -> List[str]:
    """
    Get the delegation chain from the current context.

    Returns:
        List of agent IDs in the delegation chain, or empty list if no context
    """
    ctx = get_current_context()
    return ctx.delegation_chain if ctx else []


def get_trace_id() -> Optional[str]:
    """
    Get the trace ID from the current context.

    Returns:
        Trace ID for correlating operations, or None if no context
    """
    ctx = get_current_context()
    return ctx.trace_id if ctx else None
