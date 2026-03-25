"""Signal wait node for pausing workflow execution until an external signal is received.

This module provides the SignalWaitNode, which blocks workflow execution at a
specific point until an external signal is delivered via the workflow's
SignalChannel. This enables human-in-the-loop workflows, external approval
gates, and inter-workflow coordination.

Architecture:
    The SignalWaitNode retrieves the SignalChannel from the workflow context
    (set by the runtime during execution) and awaits a named signal. When the
    signal arrives, the node passes the signal data to its output.

    The node implements both sync (run) and async (execute_async) paths:
    - In async runtimes (the default): execute_async is called, which directly
      awaits the signal channel. This is the preferred path.
    - In sync-only contexts: run() uses a thread-safe bridge to wait for the
      signal without blocking the event loop.

Usage:
    In a workflow builder::

        >>> workflow = WorkflowBuilder()
        >>> workflow.add_node("PythonCodeNode", "prepare", {"code": "result = 'ready'"})
        >>> workflow.add_node("SignalWaitNode", "wait_approval", {
        ...     "signal_name": "approval",
        ...     "timeout": 300.0  # 5 minutes
        ... })
        >>> workflow.add_node("PythonCodeNode", "process", {"code": "result = data"})
        >>> workflow.add_connection("prepare", "result", "wait_approval", "input_data")
        >>> workflow.add_connection("wait_approval", "signal_data", "process", "data")

    Sending the signal externally::

        >>> runtime.signal(workflow_id, "approval", {"approved": True})

See Also:
    - SignalChannel: The underlying signal delivery mechanism
    - LocalRuntime.signal: Runtime method for sending signals to workflows
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from kailash.nodes.base import Node, NodeParameter, register_node

logger = logging.getLogger(__name__)


@register_node()
class SignalWaitNode(Node):
    """Node that blocks execution until a named signal is received.

    The SignalWaitNode pauses the workflow at a specific point, waiting for
    an external signal to be delivered via the runtime's signal API. When the
    signal arrives, the data payload is passed through as the node's output.

    This enables patterns such as:
    - Human-in-the-loop approval gates
    - External system event waiting
    - Inter-workflow coordination
    - Timed waits with fallback behavior

    The runtime automatically calls execute_async() for this node (since it
    defines the method), allowing proper async signal waiting without blocking
    the event loop.

    Parameters:
        signal_name (str): Required. Name of the signal to wait for.
        timeout (float): Optional. Maximum seconds to wait before timing out.
            None means wait indefinitely (default: None).
        input_data (Any): Optional. Pass-through data from upstream nodes,
            included in output alongside signal data.

    Outputs:
        signal_data: The data payload received with the signal.
        signal_name: The name of the signal that was received.
        input_data: The input data passed through from upstream.
        timed_out: Boolean indicating whether the wait timed out.

    Example:
        >>> node = SignalWaitNode(id="wait_approval", config={
        ...     "signal_name": "approval",
        ...     "timeout": 60.0
        ... })
    """

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define signal wait parameters."""
        return {
            "signal_name": NodeParameter(
                name="signal_name",
                type=str,
                required=True,
                description="Name of the signal to wait for",
            ),
            "timeout": NodeParameter(
                name="timeout",
                type=float,
                required=False,
                default=None,
                description=(
                    "Maximum seconds to wait for the signal. None waits indefinitely."
                ),
            ),
            "input_data": NodeParameter(
                name="input_data",
                type=Any,
                required=False,
                default=None,
                description="Pass-through data from upstream nodes",
            ),
        }

    def _get_signal_channel(self) -> Any:
        """Retrieve the SignalChannel from workflow context.

        Returns:
            The SignalChannel instance.

        Raises:
            RuntimeError: If no SignalChannel is available.
        """
        signal_channel = self.get_workflow_context("signal_channel")
        if signal_channel is None:
            raise RuntimeError(
                f"No SignalChannel available in workflow context for node '{self.id}'. "
                "The runtime must set 'signal_channel' in the workflow context. "
                "Use LocalRuntime which automatically provides signal channels."
            )
        return signal_channel

    def _build_result(
        self,
        signal_name: str,
        signal_data: Any,
        input_data: Any,
        timed_out: bool,
    ) -> dict[str, Any]:
        """Build the standard result dict.

        Args:
            signal_name: Name of the signal.
            signal_data: Data received (or None if timed out).
            input_data: Pass-through data from upstream.
            timed_out: Whether the wait timed out.

        Returns:
            Standardized output dictionary.
        """
        return {
            "signal_data": signal_data,
            "signal_name": signal_name,
            "input_data": input_data,
            "timed_out": timed_out,
        }

    async def execute_async(self, **runtime_inputs: Any) -> dict[str, Any]:
        """Execute the signal wait asynchronously.

        This method is detected by the runtime (via hasattr check) and called
        instead of the synchronous execute() -> run() path. This allows the
        node to properly await the signal channel without blocking the event
        loop.

        Args:
            **runtime_inputs: Node parameters including signal_name, timeout,
                and input_data.

        Returns:
            Dictionary containing signal_data, signal_name, input_data, and timed_out.
        """
        start_time = datetime.now(UTC)
        self.logger.info(f"Executing node {self.id} (async signal wait)")

        # Merge config with runtime inputs (runtime takes precedence)
        merged = {**self.config, **runtime_inputs}
        signal_name = merged.get("signal_name")
        timeout = merged.get("timeout")
        input_data = merged.get("input_data")

        if not signal_name:
            raise ValueError("signal_name is required for SignalWaitNode")

        signal_channel = self._get_signal_channel()

        self.logger.info(
            f"Node {self.id}: waiting for signal '{signal_name}' (timeout={timeout})"
        )

        try:
            signal_data = await signal_channel.wait_for(signal_name, timeout=timeout)
            self.logger.info(f"Node {self.id}: signal '{signal_name}' received")
            return self._build_result(signal_name, signal_data, input_data, False)
        except TimeoutError:
            self.logger.warning(
                f"Node {self.id}: timed out waiting for signal '{signal_name}'"
            )
            return self._build_result(signal_name, None, input_data, True)

    def run(self, **kwargs: Any) -> dict[str, Any]:
        """Synchronous fallback for non-async runtimes.

        In normal LocalRuntime execution, execute_async() is called instead.
        This method provides a fallback for sync-only contexts by creating
        a new event loop to run the async wait.

        Args:
            **kwargs: Node parameters.

        Returns:
            Dictionary containing signal_data, signal_name, input_data, and timed_out.
        """
        signal_name = kwargs.get("signal_name")
        timeout = kwargs.get("timeout")
        input_data = kwargs.get("input_data")

        if not signal_name:
            raise ValueError("signal_name is required for SignalWaitNode")

        signal_channel = self._get_signal_channel()

        # If no event loop is running, we can use run_until_complete directly
        try:
            asyncio.get_running_loop()
            # We're in a running loop but called synchronously.
            # This happens if enable_async=False. Use a thread to avoid deadlock.
            import queue as thread_queue
            import threading

            bridge: thread_queue.Queue = thread_queue.Queue()

            def _wait_in_thread():
                loop = asyncio.new_event_loop()
                try:
                    data = loop.run_until_complete(
                        signal_channel.wait_for(signal_name, timeout=timeout)
                    )
                    bridge.put(("data", data))
                except TimeoutError:
                    bridge.put(("timeout", None))
                except Exception as e:
                    bridge.put(("error", e))
                finally:
                    loop.close()

            thread = threading.Thread(target=_wait_in_thread, daemon=True)
            thread.start()

            # Wait for result with same timeout plus buffer
            effective_timeout = (timeout + 5.0) if timeout is not None else None
            try:
                tag, value = bridge.get(timeout=effective_timeout)
            except thread_queue.Empty:
                return self._build_result(signal_name, None, input_data, True)

            if tag == "timeout":
                return self._build_result(signal_name, None, input_data, True)
            elif tag == "error":
                raise value
            else:
                return self._build_result(signal_name, value, input_data, False)

        except RuntimeError:
            # No running event loop -- safe to create one
            loop = asyncio.new_event_loop()
            try:
                signal_data = loop.run_until_complete(
                    signal_channel.wait_for(signal_name, timeout=timeout)
                )
                return self._build_result(signal_name, signal_data, input_data, False)
            except TimeoutError:
                return self._build_result(signal_name, None, input_data, True)
            finally:
                loop.close()

    def get_output_schema(self) -> dict[str, Any] | None:  # type: ignore[reportIncompatibleMethodOverride]
        """Define output schema for signal wait node."""
        return {
            "type": "object",
            "properties": {
                "signal_data": {
                    "description": "Data payload received with the signal",
                },
                "signal_name": {
                    "type": "string",
                    "description": "Name of the signal that was received",
                },
                "input_data": {
                    "description": "Pass-through data from upstream nodes",
                },
                "timed_out": {
                    "type": "boolean",
                    "description": "Whether the wait timed out",
                },
            },
            "required": [
                "signal_data",
                "signal_name",
                "input_data",
                "timed_out",
            ],
        }
