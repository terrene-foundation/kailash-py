"""Node execution protocol for saga and 2PC transaction coordinators.

Provides a protocol for executing nodes by type name, decoupling the
transaction coordinators from the node resolution and execution mechanics.
The default RegistryNodeExecutor resolves nodes via NodeRegistry and runs them.
A MockNodeExecutor is provided for testing without real node infrastructure.
"""

import asyncio
import logging
from collections import deque
from typing import Any, Dict, Optional, Protocol, Set, runtime_checkable

from kailash.nodes.base import NodeRegistry

logger = logging.getLogger(__name__)


@runtime_checkable
class NodeExecutor(Protocol):
    """Protocol for executing nodes by type name.

    Transaction coordinators (Saga, 2PC) use this protocol to run
    individual steps.  Implementations resolve the node type, instantiate
    it, call its run/async_run method, and return the result dict.
    """

    async def execute(
        self,
        node_type: str,
        params: Dict[str, Any],
        timeout: float = 300.0,
    ) -> Dict[str, Any]:
        """Execute a node identified by *node_type* with the given parameters.

        Args:
            node_type: Registered node class name (e.g. ``"PythonCodeNode"``).
            params: Keyword arguments forwarded to the node's run method.
            timeout: Maximum wall-clock seconds before the call is cancelled.

        Returns:
            Result dictionary produced by the node.

        Raises:
            asyncio.TimeoutError: If execution exceeds *timeout*.
            Exception: Any error raised by the underlying node.
        """
        ...


# Node types that can execute arbitrary user code and are blocked by default.
DANGEROUS_NODE_TYPES: Set[str] = {"PythonCodeNode", "AsyncPythonCodeNode"}


class RegistryNodeExecutor:
    """Default executor that resolves nodes via NodeRegistry and runs them.

    For each call the executor:
    1. Looks up the node class in ``NodeRegistry``.
    2. Instantiates it with a deterministic name (``saga_<node_type>``).
    3. Dispatches to ``async_run`` (if available) or ``run``.
    4. Normalises the return value to ``Dict[str, Any]``.

    Args:
        registry: Node registry to use. Defaults to ``NodeRegistry``.
        allowed_node_types: Optional set of node type names that may be
            executed.  When provided, any node type not in the set raises
            ``ValueError``.  When ``None`` (default), all node types except
            those in ``DANGEROUS_NODE_TYPES`` are allowed.
    """

    def __init__(
        self,
        registry: Optional[type] = None,
        allowed_node_types: Optional[Set[str]] = None,
    ):
        self._registry = registry or NodeRegistry
        self._allowed_node_types = allowed_node_types

    async def execute(
        self,
        node_type: str,
        params: Dict[str, Any],
        timeout: float = 300.0,
    ) -> Dict[str, Any]:
        """Execute a node by type name with the given parameters."""
        if self._allowed_node_types is not None:
            if node_type not in self._allowed_node_types:
                raise ValueError(
                    f"Node type '{node_type}' is not in the allowed_node_types allowlist"
                )
        else:
            if node_type in DANGEROUS_NODE_TYPES:
                raise ValueError(
                    f"Node type '{node_type}' is blocked by default for security reasons. "
                    f"Provide an explicit allowed_node_types set to permit it."
                )
        node_cls = self._registry.get(node_type)
        node = node_cls(name=f"saga_{node_type}")

        # Determine if node is async or sync
        if hasattr(node, "async_run") and asyncio.iscoroutinefunction(
            getattr(node, "async_run", None)
        ):
            try:
                result = await asyncio.wait_for(
                    node.async_run(**params),  # type: ignore[reportAttributeAccessIssue]
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.error("Node %s timed out after %.1f seconds", node_type, timeout)
                raise
        else:
            # Sync node -- run in a thread to avoid blocking the event loop
            loop = asyncio.get_running_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: node.run(**params)),
                timeout=timeout,
            )

        # Normalise result to dict
        if not isinstance(result, dict):
            result = {"result": result}

        return result


class MockNodeExecutor:
    """Mock executor for testing.  Configure responses per node type.

    Usage::

        executor = MockNodeExecutor()
        executor.set_response("ValidationNode", {"status": "success", "valid": True})
        executor.set_failure("PaymentNode", RuntimeError("declined"))

        # Pass to SagaCoordinatorNode:
        saga = SagaCoordinatorNode(executor=executor)
    """

    def __init__(self) -> None:
        self._responses: Dict[str, Dict[str, Any]] = {}
        self._call_history: deque = deque(maxlen=10000)
        self._failures: Dict[str, Exception] = {}

    def set_response(self, node_type: str, response: Dict[str, Any]) -> None:
        """Register a canned response for *node_type*."""
        self._responses[node_type] = response

    def set_failure(self, node_type: str, error: Exception) -> None:
        """Register *error* to be raised when *node_type* is executed."""
        self._failures[node_type] = error

    async def execute(
        self,
        node_type: str,
        params: Dict[str, Any],
        timeout: float = 300.0,
    ) -> Dict[str, Any]:
        """Return the pre-configured response or raise the pre-configured error."""
        self._call_history.append(
            {"node_type": node_type, "params": params, "timeout": timeout}
        )
        if node_type in self._failures:
            raise self._failures[node_type]
        return self._responses.get(
            node_type, {"status": "success", "node_type": node_type}
        )

    @property
    def calls(self) -> list[Dict[str, Any]]:
        """Return the full call history (node_type, params, timeout)."""
        return list(self._call_history)

    def reset(self) -> None:
        """Clear all responses, failures, and call history."""
        self._responses.clear()
        self._call_history.clear()
        self._failures.clear()
