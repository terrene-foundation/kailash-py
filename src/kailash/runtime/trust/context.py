"""RuntimeTrustContext for trust propagation in workflow execution (CARE-015).

This module provides the RuntimeTrustContext dataclass and supporting utilities
for propagating trust information through Kailash workflow execution.

Design Principles:
    - Immutable context updates (with_node, with_constraints create new instances)
    - Constraint tightening only (can add/tighten, never loosen)
    - Thread-safe context propagation via ContextVar
    - Optional Kaizen integration (graceful handling if Kaizen not installed)

Usage:
    # Create trust context
    ctx = RuntimeTrustContext(
        trace_id="trace-123",
        verification_mode=TrustVerificationMode.ENFORCING,
        constraints={"max_tokens": 1000},
    )

    # Extend for node execution (immutable)
    node_ctx = ctx.with_node("my_node")

    # Tighten constraints (immutable)
    tighter_ctx = ctx.with_constraints({"allowed_tools": ["read"]})

    # Use context manager for scoped propagation
    with runtime_trust_context(ctx):
        result = get_runtime_trust_context()  # Returns ctx

Version:
    Added in: v0.11.0
    Part of: CARE trust implementation (Phase 2)
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional
from uuid import uuid4

if TYPE_CHECKING:
    # Avoid hard Kaizen dependency
    pass

logger = logging.getLogger(__name__)


class TrustVerificationMode(Enum):
    """Trust verification modes for runtime execution.

    Modes:
        DISABLED: No trust verification (default for backward compatibility)
        PERMISSIVE: Log trust violations but allow execution
        ENFORCING: Block execution on trust violations
    """

    DISABLED = "disabled"
    PERMISSIVE = "permissive"
    ENFORCING = "enforcing"


def _generate_default_trace_id() -> str:
    """Generate a default trace ID using UUID4."""
    return str(uuid4())


def _get_utc_now() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(UTC)


@dataclass
class RuntimeTrustContext:
    """Trust context for workflow execution.

    This dataclass captures trust information that propagates through
    workflow execution, enabling:
    - Human origin tracking across agent delegation chains
    - Constraint propagation with tightening semantics
    - Audit trail for compliance
    - Verification mode control

    Immutability:
        with_node() and with_constraints() create new instances,
        preserving the original context unchanged.

    Attributes:
        trace_id: Unique identifier for tracing execution (default: UUID)
        human_origin: Origin information (compatible with Kaizen HumanOrigin)
        delegation_chain: List of agent IDs in delegation chain
        delegation_depth: Current depth in delegation chain
        constraints: Dictionary of constraints (can only be tightened)
        verification_mode: How to handle trust verification
        workflow_id: ID of the workflow being executed
        node_path: Execution path through nodes (for audit)
        metadata: Additional metadata for extensibility
        created_at: When this context was created

    Example:
        >>> ctx = RuntimeTrustContext(
        ...     trace_id="trace-123",
        ...     verification_mode=TrustVerificationMode.ENFORCING,
        ...     constraints={"max_tokens": 1000},
        ... )
        >>> node_ctx = ctx.with_node("process_data")
        >>> node_ctx.node_path
        ['process_data']
    """

    trace_id: str = field(default_factory=_generate_default_trace_id)
    human_origin: Optional[Any] = None
    delegation_chain: List[str] = field(default_factory=list)
    delegation_depth: int = 0
    constraints: Dict[str, Any] = field(default_factory=dict)
    verification_mode: TrustVerificationMode = TrustVerificationMode.DISABLED
    workflow_id: Optional[str] = None
    node_path: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_get_utc_now)

    def with_node(self, node_id: str) -> RuntimeTrustContext:
        """Create new context with node_id appended to node_path.

        This method creates a new RuntimeTrustContext instance with the
        given node_id added to the execution path. The original context
        remains unchanged (immutable pattern).

        Args:
            node_id: The node ID to append to the path

        Returns:
            New RuntimeTrustContext with extended node_path

        Example:
            >>> ctx = RuntimeTrustContext(node_path=["node1"])
            >>> new_ctx = ctx.with_node("node2")
            >>> ctx.node_path
            ['node1']
            >>> new_ctx.node_path
            ['node1', 'node2']
        """
        return RuntimeTrustContext(
            trace_id=self.trace_id,
            human_origin=self.human_origin,
            delegation_chain=list(self.delegation_chain),
            delegation_depth=self.delegation_depth,
            constraints=dict(self.constraints),
            verification_mode=self.verification_mode,
            workflow_id=self.workflow_id,
            node_path=list(self.node_path) + [node_id],
            metadata=dict(self.metadata),
            created_at=self.created_at,
        )

    def with_constraints(
        self, additional_constraints: Dict[str, Any]
    ) -> RuntimeTrustContext:
        """Create new context with merged constraints.

        This method creates a new RuntimeTrustContext instance with the
        additional constraints merged into the existing ones. The original
        context remains unchanged (immutable pattern).

        Note: This performs a simple merge where new values override existing
        ones. Semantic tightening (e.g., taking the minimum of numeric limits)
        is the responsibility of the caller.

        Args:
            additional_constraints: Constraints to merge/add

        Returns:
            New RuntimeTrustContext with merged constraints

        Example:
            >>> ctx = RuntimeTrustContext(constraints={"max_tokens": 1000})
            >>> new_ctx = ctx.with_constraints({"allowed_tools": ["read"]})
            >>> new_ctx.constraints
            {'max_tokens': 1000, 'allowed_tools': ['read']}
        """
        merged = dict(self.constraints)
        merged.update(additional_constraints)

        return RuntimeTrustContext(
            trace_id=self.trace_id,
            human_origin=self.human_origin,
            delegation_chain=list(self.delegation_chain),
            delegation_depth=self.delegation_depth,
            constraints=merged,
            verification_mode=self.verification_mode,
            workflow_id=self.workflow_id,
            node_path=list(self.node_path),
            metadata=dict(self.metadata),
            created_at=self.created_at,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize context to dictionary.

        Handles:
        - datetime fields as ISO format strings
        - human_origin via its to_dict() method if available
        - TrustVerificationMode as string value

        Returns:
            Dictionary representation of the context

        Example:
            >>> ctx = RuntimeTrustContext(trace_id="trace-123")
            >>> data = ctx.to_dict()
            >>> data["trace_id"]
            'trace-123'
        """
        # Handle human_origin serialization
        human_origin_dict = None
        if self.human_origin is not None:
            if hasattr(self.human_origin, "to_dict"):
                human_origin_dict = self.human_origin.to_dict()
            else:
                human_origin_dict = self.human_origin

        return {
            "trace_id": self.trace_id,
            "human_origin": human_origin_dict,
            "delegation_chain": list(self.delegation_chain),
            "delegation_depth": self.delegation_depth,
            "constraints": dict(self.constraints),
            "verification_mode": self.verification_mode.value,
            "workflow_id": self.workflow_id,
            "node_path": list(self.node_path),
            "metadata": dict(self.metadata),
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RuntimeTrustContext:
        """Deserialize context from dictionary.

        Handles:
        - ISO format strings as datetime
        - String verification mode values

        Args:
            data: Dictionary representation of the context

        Returns:
            RuntimeTrustContext instance

        Example:
            >>> data = {"trace_id": "trace-123", ...}
            >>> ctx = RuntimeTrustContext.from_dict(data)
            >>> ctx.trace_id
            'trace-123'
        """
        # Parse created_at from ISO string
        created_at_str = data.get("created_at")
        if isinstance(created_at_str, str):
            created_at = datetime.fromisoformat(created_at_str)
        elif isinstance(created_at_str, datetime):
            created_at = created_at_str
        else:
            created_at = _get_utc_now()

        # Parse verification mode
        mode_str = data.get("verification_mode", "disabled")
        if isinstance(mode_str, TrustVerificationMode):
            verification_mode = mode_str
        else:
            verification_mode = TrustVerificationMode(mode_str)

        return cls(
            trace_id=data.get("trace_id", _generate_default_trace_id()),
            human_origin=data.get("human_origin"),
            delegation_chain=list(data.get("delegation_chain", [])),
            delegation_depth=data.get("delegation_depth", 0),
            constraints=dict(data.get("constraints", {})),
            verification_mode=verification_mode,
            workflow_id=data.get("workflow_id"),
            node_path=list(data.get("node_path", [])),
            metadata=dict(data.get("metadata", {})),
            created_at=created_at,
        )

    @classmethod
    def from_kaizen_context(cls, ctx: Any) -> RuntimeTrustContext:
        """Bridge from Kaizen ExecutionContext.

        Creates a RuntimeTrustContext from a Kaizen ExecutionContext,
        mapping relevant fields and setting verification_mode to ENFORCING
        since Kaizen contexts imply trust enforcement.

        This method handles the case where Kaizen is not installed gracefully,
        using duck typing to access expected attributes.

        Args:
            ctx: Kaizen ExecutionContext (or any object with expected attributes)

        Returns:
            RuntimeTrustContext bridged from Kaizen context

        Example:
            >>> from kaizen.core.context import ExecutionContext
            >>> kaizen_ctx = ExecutionContext(...)
            >>> runtime_ctx = RuntimeTrustContext.from_kaizen_context(kaizen_ctx)
            >>> runtime_ctx.verification_mode
            TrustVerificationMode.ENFORCING
        """
        # Extract human_origin (may have to_dict method)
        human_origin = getattr(ctx, "human_origin", None)

        return cls(
            trace_id=getattr(ctx, "trace_id", _generate_default_trace_id()),
            human_origin=human_origin,
            delegation_chain=list(getattr(ctx, "delegation_chain", [])),
            delegation_depth=getattr(ctx, "delegation_depth", 0),
            constraints=dict(getattr(ctx, "constraints", {})),
            verification_mode=TrustVerificationMode.ENFORCING,
            workflow_id=None,
            node_path=[],
            metadata={},
            created_at=_get_utc_now(),
        )


# === Context Propagation ===

_runtime_trust_context: ContextVar[Optional[RuntimeTrustContext]] = ContextVar(
    "runtime_trust_context", default=None
)


def get_runtime_trust_context() -> Optional[RuntimeTrustContext]:
    """Get the current runtime trust context.

    Returns the RuntimeTrustContext from the current context variable,
    or None if no context is set.

    Returns:
        Current RuntimeTrustContext or None

    Example:
        >>> ctx = get_runtime_trust_context()
        >>> if ctx:
        ...     print(f"Trace: {ctx.trace_id}")
    """
    return _runtime_trust_context.get()


def set_runtime_trust_context(ctx: Optional[RuntimeTrustContext]) -> None:
    """Set the runtime trust context.

    Sets the RuntimeTrustContext in the current context variable.
    Pass None to clear the context.

    Args:
        ctx: RuntimeTrustContext to set, or None to clear

    Example:
        >>> ctx = RuntimeTrustContext(trace_id="trace-123")
        >>> set_runtime_trust_context(ctx)
        >>> get_runtime_trust_context().trace_id
        'trace-123'
    """
    _runtime_trust_context.set(ctx)


@contextmanager
def runtime_trust_context(ctx: RuntimeTrustContext) -> Iterator[RuntimeTrustContext]:
    """Context manager for scoped trust context propagation.

    Sets the trust context for the duration of the block, then
    resets to the previous value on exit (even on exception).

    Args:
        ctx: RuntimeTrustContext to use within the block

    Yields:
        The same RuntimeTrustContext that was passed in

    Example:
        >>> ctx = RuntimeTrustContext(trace_id="trace-123")
        >>> with runtime_trust_context(ctx) as active_ctx:
        ...     assert get_runtime_trust_context() is ctx
        ...     print(active_ctx.trace_id)
        trace-123
    """
    token = _runtime_trust_context.set(ctx)
    try:
        yield ctx
    finally:
        _runtime_trust_context.reset(token)
