"""Asynchronous base node class extension for the Kailash SDK.

This module extends the base Node class with asynchronous execution capabilities,
allowing for more efficient handling of I/O-bound operations in workflows.
"""

from datetime import UTC, datetime
from typing import Any

from kailash.nodes.base import Node
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


class AsyncNode(Node):
    """Base class for asynchronous nodes in the Kailash system.

    This class extends the standard Node class with async execution capabilities,
    providing a clean interface for implementing asynchronous operations in
    workflow nodes. It's particularly useful for:

    1. API calls and network operations
    2. Database queries
    3. File operations
    4. External service integrations
    5. LLM/AI model inference

    Design Philosophy:
    - Maintain backward compatibility with synchronous nodes
    - Support both sync and async execution methods
    - Provide clear error handling and logging for async operations
    - Enable efficient parallel execution in workflows

    Usage Pattern:
    - Override async_run() instead of run() for async functionality
    - Default async_run() implementation calls run() for backward compatibility
    - Node configurtion and validation remain the same as standard nodes

    Upstream components:
    - Workflow: Creates and manages node instances
    - AsyncWorkflowExecutor: Executes nodes in parallel where possible
    - AsyncLocalRuntime: Runs workflows with async support

    Downstream usage:
    - Custom AsyncNodes: Implement async_run() for I/O-bound operations
    - TaskManager: Tracks node execution status
    """

    def execute(self, **runtime_inputs) -> dict[str, Any]:
        """Execute the node synchronously by running async code with proper event loop handling.

        This enhanced implementation handles all event loop scenarios:
        1. No event loop: Create new one with asyncio.run()
        2. Event loop running: Use ThreadPoolExecutor with isolated loop
        3. Threaded contexts: Proper thread-safe execution
        4. Windows compatibility: ProactorEventLoopPolicy support

        Args:
            **runtime_inputs: Runtime inputs for node execution

        Returns:
            Dictionary of validated outputs

        Raises:
            NodeValidationError: If inputs or outputs are invalid
            NodeExecutionError: If execution fails
        """
        import asyncio
        import concurrent.futures
        import sys
        import threading

        # For sync execution, we always create a new event loop
        # This avoids complexity with nested loops and ensures clean execution
        if sys.platform == "win32":
            # Windows requires special handling
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

        # Check if we're in a thread without an event loop
        current_thread = threading.current_thread()
        is_main_thread = isinstance(current_thread, threading._MainThread)

        # Run the async method - handle existing event loop
        try:
            # Try to get current event loop
            loop = asyncio.get_running_loop()
            # Event loop is running - need to run in separate thread
            return self._execute_in_thread(**runtime_inputs)
        except RuntimeError:
            # No event loop running
            if is_main_thread:
                # Main thread without loop - safe to use asyncio.run()
                return asyncio.run(self.execute_async(**runtime_inputs))
            else:
                # Non-main thread without loop - create new loop
                return self._execute_in_new_loop(**runtime_inputs)

    def _execute_in_thread(self, **runtime_inputs) -> dict[str, Any]:
        """Execute async code in a separate thread with its own event loop."""
        import asyncio
        import concurrent.futures

        def run_in_new_loop():
            """Run async code in a completely new event loop."""
            # Create fresh event loop for this thread
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(self.execute_async(**runtime_inputs))
            finally:
                new_loop.close()
                asyncio.set_event_loop(None)

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_in_new_loop)
            return future.result()

    def _execute_in_new_loop(self, **runtime_inputs) -> dict[str, Any]:
        """Execute async code by creating a new event loop in current thread."""
        import asyncio

        # Create and set new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.execute_async(**runtime_inputs))
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    def run(self, **kwargs) -> dict[str, Any]:
        """Synchronous run is not supported for AsyncNode.

        AsyncNode subclasses should implement async_run() instead of run().
        This method exists to provide a clear error message if someone
        accidentally tries to implement run() on an async node.

        Raises:
            NotImplementedError: Always, as async nodes must use async_run()
        """
        raise NotImplementedError(
            f"AsyncNode '{self.__class__.__name__}' should implement async_run() method, not run()"
        )

    async def async_run(self, **kwargs) -> dict[str, Any]:
        """Asynchronous execution method for the node.

        This method should be overridden by subclasses to implement asynchronous
        execution logic. The default implementation raises NotImplementedError
        to ensure async nodes properly implement their async behavior.

        Args:
            **kwargs: Input parameters for node execution

        Returns:
            Dictionary of outputs matching the node's output schema

        Raises:
            NodeExecutionError: If execution fails
        """
        raise NotImplementedError(
            f"AsyncNode '{self.__class__.__name__}' must implement async_run() method"
        )

    async def execute_async(self, **runtime_inputs) -> dict[str, Any]:
        """Execute the node asynchronously with validation and error handling.

        This method follows the same pattern as execute() but supports asynchronous
        execution. It performs:

        1. Input validation
        2. Execution via async_run()
        3. Output validation
        4. Error handling and logging

        Args:
            **runtime_inputs: Runtime inputs for node execution

        Returns:
            Dictionary of validated outputs

        Raises:
            NodeValidationError: If inputs or outputs are invalid
            NodeExecutionError: If execution fails
        """
        start_time = datetime.now(UTC)
        try:
            self.logger.info(f"Executing node {self.id} asynchronously")

            # Merge runtime inputs with config (runtime inputs take precedence)
            merged_inputs = {**self.config, **runtime_inputs}

            # Handle nested config case (for nodes that store parameters in config['config'])
            if "config" in merged_inputs and isinstance(merged_inputs["config"], dict):
                # Extract nested config
                nested_config = merged_inputs["config"]
                merged_inputs.update(nested_config)
                # Don't remove the config key as some nodes might need it

            # Validate inputs
            validated_inputs = self.validate_inputs(**merged_inputs)
            self.logger.debug(f"Validated inputs for {self.id}: {validated_inputs}")

            # Execute node logic asynchronously
            outputs = await self.async_run(**validated_inputs)

            # Validate outputs
            validated_outputs = self.validate_outputs(outputs)

            execution_time = (datetime.now(UTC) - start_time).total_seconds()
            self.logger.info(
                f"Node {self.id} executed successfully in {execution_time:.3f}s"
            )
            return validated_outputs

        except NodeValidationError:
            # Re-raise validation errors as-is
            raise
        except NodeExecutionError:
            # Re-raise execution errors as-is
            raise
        except Exception as e:
            # Wrap any other exception in NodeExecutionError
            self.logger.error(f"Node {self.id} execution failed: {e}", exc_info=True)
            raise NodeExecutionError(
                f"Node '{self.id}' execution failed: {type(e).__name__}: {e}"
            ) from e
