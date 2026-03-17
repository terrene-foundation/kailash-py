"""Continue-as-new pattern for the Kailash SDK.

This module implements the continue-as-new pattern, which allows a running
workflow to complete its current execution and immediately restart with
new parameters. This is useful for long-running workflows that need to
periodically checkpoint and restart to avoid unbounded history growth.

The pattern works through a special exception: when a node raises
ContinueAsNew, the runtime catches it, records the continuation chain,
and re-executes the workflow with the provided parameters.

Usage:
    >>> from kailash.workflow.continuation import ContinueAsNew, ContinuationContext
    >>>
    >>> # Inside a node's execute method:
    >>> if should_continue:
    ...     raise ContinueAsNew(
    ...         new_params={"page": current_page + 1},
    ...         version="2.0.0",  # optional: switch to a new workflow version
    ...     )
    >>>
    >>> # Tracking continuation history:
    >>> ctx = ContinuationContext()
    >>> ctx.record_continuation("run-1", {"page": 2})
    >>> print(ctx.depth)  # 1
    >>> print(ctx.continued_from)  # "run-1"

See Also:
    - WorkflowBuilder: Creates workflows that use continue-as-new
    - WorkflowVersionRegistry: For version-based continuation routing

Version:
    Added in: v0.13.0
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

__all__ = [
    "ContinueAsNew",
    "ContinuationContext",
    "ContinuationDepthExceededError",
    "DEFAULT_MAX_CONTINUATION_DEPTH",
]

DEFAULT_MAX_CONTINUATION_DEPTH = 1000
_MAX_PARAM_BYTES = 1024 * 1024  # 1 MB


class ContinueAsNew(Exception):
    """Signal to re-execute the workflow with new parameters.

    When raised inside a node's execute method, the runtime catches this
    exception, completes the current execution cleanly, and starts a new
    execution of the same (or a different version of the) workflow with
    the provided parameters.

    Attributes:
        new_params: Parameters for the new execution.
        version: Optional version string to route to a specific workflow
            version. If None, the same version is used.

    Example:
        >>> raise ContinueAsNew(
        ...     new_params={"cursor": "abc123", "batch_size": 100},
        ...     version="2.0.0",
        ... )
    """

    def __init__(
        self,
        new_params: Optional[Dict[str, Any]] = None,
        version: Optional[str] = None,
    ) -> None:
        self.new_params: Dict[str, Any] = new_params or {}
        self.version: Optional[str] = version
        super().__init__(
            f"ContinueAsNew requested (version={version}, "
            f"params_keys={sorted(self.new_params.keys())})"
        )


class ContinuationDepthExceededError(Exception):
    """Raised when continuation depth exceeds the configured maximum.

    This prevents infinite continuation loops where a workflow keeps
    raising ContinueAsNew indefinitely.

    Attributes:
        depth: The current continuation depth when the error was raised.
        max_depth: The configured maximum depth.
        chain: The continuation chain that led to this error.
    """

    def __init__(self, depth: int, max_depth: int, chain: List[str]) -> None:
        self.depth = depth
        self.max_depth = max_depth
        self.chain = chain
        super().__init__(
            f"Continuation depth {depth} exceeds maximum {max_depth}. "
            f"Chain length: {len(chain)} runs. "
            f"This may indicate an infinite continuation loop."
        )


@dataclass
class ContinuationContext:
    """Tracks the continuation chain for a workflow execution.

    Each time a workflow continues-as-new, the context records the
    previous run ID, parameters, and increments the depth counter.
    The runtime uses this to enforce maximum continuation depth and
    provide observability into long-running continuation chains.

    Attributes:
        max_depth: Maximum allowed continuation depth. Defaults to 1000.
        continued_from: The run_id of the immediately previous execution,
            or None if this is the first execution.
        depth: How many times the workflow has continued. Starts at 0.
        chain: Ordered list of (run_id, params) for each continuation.
    """

    max_depth: int = DEFAULT_MAX_CONTINUATION_DEPTH
    continued_from: Optional[str] = None
    depth: int = 0
    chain: List[Tuple[str, Dict[str, Any]]] = field(default_factory=list)

    def record_continuation(
        self,
        run_id: str,
        params: Dict[str, Any],
    ) -> None:
        """Record a continuation event.

        Args:
            run_id: The run_id of the execution that raised ContinueAsNew.
            params: The new parameters for the next execution.

        Raises:
            ContinuationDepthExceededError: If recording this continuation
                would exceed max_depth.
        """
        new_depth = self.depth + 1

        if new_depth > self.max_depth:
            chain_ids = [rid for rid, _ in self.chain] + [run_id]
            raise ContinuationDepthExceededError(
                depth=new_depth,
                max_depth=self.max_depth,
                chain=chain_ids,
            )

        # Guard against oversized params: if >1MB, store keys only
        try:
            param_size = len(json.dumps(params).encode())
        except (TypeError, ValueError):
            param_size = _MAX_PARAM_BYTES + 1
        if param_size > _MAX_PARAM_BYTES:
            logger.warning(
                "Continuation params exceed 1MB (size=%d); storing keys only",
                param_size,
            )
            params = {k: None for k in params}

        self.chain.append((run_id, params))
        self.continued_from = run_id
        self.depth = new_depth

        logger.info(
            "Continuation recorded: depth=%d, from_run=%s, params_keys=%s",
            self.depth,
            run_id,
            sorted(params.keys()),
        )

    def get_chain_run_ids(self) -> List[str]:
        """Get the ordered list of run IDs in the continuation chain.

        Returns:
            List of run_id strings from oldest to newest.
        """
        return [run_id for run_id, _ in self.chain]

    def get_params_at_depth(self, depth: int) -> Dict[str, Any]:
        """Get the parameters used at a specific continuation depth.

        Args:
            depth: The 1-based depth index.

        Returns:
            The parameters dict used at that continuation step.

        Raises:
            IndexError: If depth is out of range.
        """
        if depth < 1 or depth > len(self.chain):
            raise IndexError(
                f"Depth {depth} out of range. "
                f"Chain has {len(self.chain)} continuation(s) (1-based index)."
            )
        return self.chain[depth - 1][1]

    def reset(self) -> None:
        """Reset the continuation context to initial state.

        Clears the chain, depth, and continued_from. Preserves max_depth.
        """
        self.continued_from = None
        self.depth = 0
        self.chain = []
        logger.debug("Continuation context reset")
