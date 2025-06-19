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
        """Execute the node synchronously by running async code in a new event loop.

        This override allows AsyncNode to work with synchronous runtimes like LocalRuntime
        by wrapping the async execution in a synchronous interface.

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

        # For sync execution, we always create a new event loop
        # This avoids complexity with nested loops and ensures clean execution
        if sys.platform == "win32":
            # Windows requires special handling
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

        # Run the async method in a new event loop
        return asyncio.run(self.execute_async(**runtime_inputs))

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
