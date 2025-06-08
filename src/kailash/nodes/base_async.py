"""Asynchronous base node class extension for the Kailash SDK.

This module extends the base Node class with asynchronous execution capabilities,
allowing for more efficient handling of I/O-bound operations in workflows.
"""

from datetime import datetime, timezone
from typing import Any, Dict

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

    def execute(self, **runtime_inputs) -> Dict[str, Any]:
        """Execute the node synchronously by running async code in a new event loop.

        This override allows AsyncNode to work with synchronous runtimes like LocalRuntime.
        It creates a new event loop to run the async code if needed.

        Args:
            **runtime_inputs: Runtime inputs for node execution

        Returns:
            Dictionary of validated outputs

        Raises:
            NodeValidationError: If inputs or outputs are invalid
            NodeExecutionError: If execution fails
        """
        import asyncio
        import sys

        # Check if we're already in an event loop
        try:
            asyncio.get_running_loop()
            # We're in an event loop - this is problematic for sync execution
            # Try to use nest_asyncio if available
            try:
                import nest_asyncio

                nest_asyncio.apply()
                return asyncio.run(self.execute_async(**runtime_inputs))
            except ImportError:
                # Fall back to running in a thread pool
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run, self.execute_async(**runtime_inputs)
                    )
                    return future.result()
        except RuntimeError:
            # No event loop running, we can create one
            if sys.platform == "win32":
                # Windows requires special handling
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            return asyncio.run(self.execute_async(**runtime_inputs))

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Asynchronous execution method for the node.

        This method should be overridden by subclasses that require asynchronous
        execution. The default implementation calls the synchronous run() method.

        Args:
            **kwargs: Input parameters for node execution

        Returns:
            Dictionary of outputs matching the node's output schema

        Raises:
            NodeExecutionError: If execution fails
        """
        # Default implementation calls the synchronous run() method
        return self.run(**kwargs)

    async def execute_async(self, **runtime_inputs) -> Dict[str, Any]:
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
        start_time = datetime.now(timezone.utc)
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

            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
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
