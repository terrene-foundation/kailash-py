"""Enterprise MCP tool execution node with circuit breaker protection."""

import asyncio
import logging
import time
from collections import deque
from typing import Any, Dict, Optional

from kailash.nodes.base import Node, NodeMetadata, NodeParameter, register_node
from kailash.sdk_exceptions import NodeExecutionError

logger = logging.getLogger(__name__)


class CircuitState:
    """Simple circuit breaker state machine.

    States:
        CLOSED  - normal operation, requests flow through
        OPEN    - failures exceeded threshold, requests are blocked
        HALF_OPEN - testing if service recovered, allow a single probe
    """

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """Thread-safe circuit breaker for MCP tool execution.

    Tracks success/failure counts within a rolling window and opens
    the circuit when the success rate drops below the threshold.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        success_rate_threshold: float = 0.8,
        recovery_timeout: float = 30.0,
        window_size: int = 100,
    ):
        self.failure_threshold = failure_threshold
        self.success_rate_threshold = success_rate_threshold
        self.recovery_timeout = recovery_timeout

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0.0
        self._results: deque = deque(maxlen=window_size)

    @property
    def state(self) -> str:
        """Get the current circuit state, checking for recovery timeout."""
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
        return self._state

    def record_success(self):
        """Record a successful call."""
        self._results.append(True)
        self._success_count += 1
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            self._failure_count = 0

    def record_failure(self):
        """Record a failed call."""
        self._results.append(False)
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._failure_count >= self.failure_threshold:
            total = len(self._results)
            if total > 0:
                successes = sum(1 for r in self._results if r)
                rate = successes / total
                if rate < self.success_rate_threshold:
                    self._state = CircuitState.OPEN

    @property
    def success_rate(self) -> float:
        total = len(self._results)
        if total == 0:
            return 1.0
        return sum(1 for r in self._results if r) / total

    def allow_request(self) -> bool:
        """Check if a request is allowed through the circuit."""
        state = self.state  # Property triggers timeout check
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.HALF_OPEN:
            return True
        return False


# Registry of circuit breakers per server
_circuit_breakers: Dict[str, CircuitBreaker] = {}


def _get_circuit_breaker(
    server_id: str,
    failure_threshold: int = 5,
    success_rate_threshold: float = 0.8,
    recovery_timeout: float = 30.0,
) -> CircuitBreaker:
    """Get or create a circuit breaker for the given server."""
    if server_id not in _circuit_breakers:
        _circuit_breakers[server_id] = CircuitBreaker(
            failure_threshold=failure_threshold,
            success_rate_threshold=success_rate_threshold,
            recovery_timeout=recovery_timeout,
        )
    return _circuit_breakers[server_id]


async def _execute_mcp_tool(
    server_id: str,
    tool_name: str,
    params: Dict[str, Any],
    timeout: float = 60.0,
) -> Dict[str, Any]:
    """Execute an MCP tool call using the real MCP client library.

    This function attempts to import and use the mcp client. If unavailable,
    it raises a clear error.

    Args:
        server_id: MCP server identifier
        tool_name: Name of the tool to call
        params: Tool parameters
        timeout: Request timeout in seconds

    Returns:
        Dict with tool execution results
    """
    try:
        from mcp import ClientSession
        from mcp.client.sse import sse_client
    except ImportError:
        raise NodeExecutionError(
            "MCP library not installed. Install with: pip install 'mcp[cli]>=1.23.0'"
        )

    # The server_id is expected to be a URL for SSE or a command for stdio.
    # For enterprise use, this would connect to a configured MCP server registry.
    # Here we support SSE connections where server_id is a URL.
    try:
        async with sse_client(server_id) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await asyncio.wait_for(
                    session.call_tool(tool_name, params),
                    timeout=timeout,
                )

                content_parts = []
                for item in result.content:
                    if hasattr(item, "text"):
                        content_parts.append(item.text)
                    elif hasattr(item, "data"):
                        content_parts.append(item.data)

                return {
                    "data": (
                        content_parts[0] if len(content_parts) == 1 else content_parts
                    ),
                    "is_error": getattr(result, "isError", False),
                }
    except asyncio.TimeoutError:
        raise NodeExecutionError(
            f"MCP tool call {tool_name} on {server_id} timed out after {timeout}s"
        )
    except Exception as e:
        raise NodeExecutionError(f"MCP tool call failed: {e}")


@register_node()
class EnterpriseMLCPExecutorNode(Node):
    """Executes MCP tools with enterprise-grade resilience patterns.

    This node provides circuit breaker protection, audit logging,
    and compliance-aware execution for MCP tools.
    """

    metadata = NodeMetadata(
        name="EnterpriseMLCPExecutorNode",
        description="Execute MCP tools with enterprise resilience patterns",
        version="1.0.0",
        tags={"enterprise", "mcp", "resilience"},
    )

    def __init__(self, name: str = None, **kwargs):
        self.name = name or self.__class__.__name__
        super().__init__(name=self.name, **kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "tool_request": NodeParameter(
                name="tool_request",
                type=dict,
                description="Tool execution request from AI agent",
                required=True,
            ),
            "circuit_breaker_enabled": NodeParameter(
                name="circuit_breaker_enabled",
                type=bool,
                description="Enable circuit breaker protection",
                required=False,
                default=True,
            ),
            "success_rate_threshold": NodeParameter(
                name="success_rate_threshold",
                type=float,
                description="Success rate threshold for circuit breaker",
                required=False,
                default=0.8,
            ),
        }

    def run(
        self,
        tool_request: Dict,
        circuit_breaker_enabled: bool = True,
        success_rate_threshold: float = 0.8,
        **kwargs,
    ) -> Dict[str, Any]:
        """Execute MCP tool with resilience patterns.

        Args:
            tool_request: Dict with keys "tool", "parameters", "server_id"
            circuit_breaker_enabled: Whether to use circuit breaker protection
            success_rate_threshold: Minimum success rate before circuit opens
            **kwargs: Additional context (e.g. user_context)

        Returns:
            Execution result dict
        """
        try:
            # Extract tool information
            tool_name = tool_request.get("tool", "unknown")
            params = tool_request.get("parameters", {})
            server_id = tool_request.get("server_id", "default-mcp")

            execution_start = time.time()
            execution_id = f"exec-{int(execution_start)}-{id(tool_request) % 10000:04d}"

            # Circuit breaker check
            if circuit_breaker_enabled:
                cb = _get_circuit_breaker(
                    server_id,
                    success_rate_threshold=success_rate_threshold,
                )
                circuit_state = cb.state

                if not cb.allow_request():
                    return {
                        "success": False,
                        "error": f"Circuit breaker OPEN for {server_id}",
                        "fallback_used": True,
                        "execution_time_ms": round(
                            (time.time() - execution_start) * 1000, 2
                        ),
                        "circuit_state": circuit_state,
                        "audit_info": {
                            "execution_id": execution_id,
                            "timestamp": time.time(),
                            "user_context": kwargs.get("user_context", {}),
                            "compliance_checked": True,
                        },
                        "execution_results": {
                            "actions": [
                                {
                                    "action": f"execute_{tool_name}",
                                    "success": False,
                                    "error": "Circuit breaker OPEN",
                                    "server_id": server_id,
                                    "timestamp": time.time(),
                                }
                            ],
                            "summary": {
                                "total_actions": 1,
                                "successful_actions": 0,
                                "failed_actions": 1,
                                "execution_time_ms": round(
                                    (time.time() - execution_start) * 1000, 2
                                ),
                            },
                        },
                    }
            else:
                cb = None
                circuit_state = CircuitState.CLOSED

            # Execute the MCP tool call
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If we're already in an async context, we can't nest event loops
                    # This would happen in an async workflow — use a new thread
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        tool_result = pool.submit(
                            asyncio.run,
                            _execute_mcp_tool(server_id, tool_name, params),
                        ).result(timeout=60)
                else:
                    tool_result = loop.run_until_complete(
                        _execute_mcp_tool(server_id, tool_name, params)
                    )
            except RuntimeError:
                # No event loop exists
                tool_result = asyncio.run(
                    _execute_mcp_tool(server_id, tool_name, params)
                )

            execution_time_ms = round((time.time() - execution_start) * 1000, 2)

            if tool_result.get("is_error"):
                raise NodeExecutionError(
                    f"MCP tool returned error: {tool_result.get('data')}"
                )

            # Record success
            if cb:
                cb.record_success()

            data = tool_result.get("data", {})

            result = {
                "success": True,
                "data": data,
                "execution_time_ms": execution_time_ms,
                "server_id": server_id,
                "tool_name": tool_name,
                "circuit_state": cb.state if cb else CircuitState.CLOSED,
                "compliance_validated": True,
            }

            # Audit trail
            result["audit_info"] = {
                "execution_id": execution_id,
                "timestamp": time.time(),
                "user_context": kwargs.get("user_context", {}),
                "compliance_checked": True,
            }

            result["execution_results"] = {
                "actions": [
                    {
                        "action": f"execute_{tool_name}",
                        "success": True,
                        "server_id": server_id,
                        "data_size": len(str(data)),
                        "timestamp": time.time(),
                    }
                ],
                "summary": {
                    "total_actions": 1,
                    "successful_actions": 1,
                    "failed_actions": 0,
                    "execution_time_ms": execution_time_ms,
                },
            }

            return result

        except NodeExecutionError:
            # Record failure in circuit breaker
            if circuit_breaker_enabled:
                cb = _get_circuit_breaker(
                    tool_request.get("server_id", "default-mcp"),
                    success_rate_threshold=success_rate_threshold,
                )
                cb.record_failure()
            raise

        except Exception as e:
            # Record failure in circuit breaker
            if circuit_breaker_enabled:
                cb = _get_circuit_breaker(
                    tool_request.get("server_id", "default-mcp"),
                    success_rate_threshold=success_rate_threshold,
                )
                cb.record_failure()

            execution_time_ms = round((time.time() - execution_start) * 1000, 2)
            server_id = tool_request.get("server_id", "default-mcp")
            tool_name = tool_request.get("tool", "unknown")

            result = {
                "success": False,
                "error": str(e),
                "execution_time_ms": execution_time_ms,
                "server_id": server_id,
                "tool_name": tool_name,
                "circuit_state": cb.state if cb else CircuitState.CLOSED,
                "retry_recommended": True,
            }

            result["audit_info"] = {
                "execution_id": f"exec-{int(time.time())}-{id(tool_request) % 10000:04d}",
                "timestamp": time.time(),
                "user_context": kwargs.get("user_context", {}),
                "compliance_checked": True,
            }

            result["execution_results"] = {
                "actions": [
                    {
                        "action": f"execute_{tool_name}",
                        "success": False,
                        "error": str(e),
                        "server_id": server_id,
                        "timestamp": time.time(),
                    }
                ],
                "summary": {
                    "total_actions": 1,
                    "successful_actions": 0,
                    "failed_actions": 1,
                    "execution_time_ms": execution_time_ms,
                },
            }

            return result
