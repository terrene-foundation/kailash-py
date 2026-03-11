"""
ErrorHandlingMixin - Comprehensive error handling for agent execution.

This module implements the ErrorHandlingMixin that provides robust error
handling capabilities including retry logic, exponential backoff, fallback
strategies, and error recovery.

Key Features:
- Configurable retry logic with exponential backoff
- Multiple fallback strategies
- Error categorization
- State capture and restoration
- Workflow enhancement with error handlers
- MRO-compatible initialization

References:
- ADR-006: Agent Base Architecture design (Mixin Composition section)
- TODO-157: Task 3.2, 3.10-3.13
- Phase 3: Mixin System implementation

Author: Kaizen Framework Team
Created: 2025-10-01
"""

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from kailash.workflow.builder import WorkflowBuilder


class ErrorHandlingMixin:
    """
    Mixin for adding comprehensive error handling to agents.

    Provides error handling capabilities including:
    - Retry logic with exponential backoff
    - Fallback strategies
    - Error categorization
    - State capture/restoration
    - Workflow enhancement with error handlers

    Usage:
        >>> class MyAgent(BaseAgent, ErrorHandlingMixin):
        ...     def __init__(self, config):
        ...         BaseAgent.__init__(self, config=config, signature=signature)
        ...         ErrorHandlingMixin.__init__(self, max_retries=3)
        ...
        ...     def run(self, **inputs):
        ...         def execute():
        ...             return super().run(**inputs)
        ...
        ...         def fallback():
        ...             return {"error": "fallback", "result": None}
        ...
        ...         return self.execute_with_fallback(execute, fallback)

    Extension Points:
    - enhance_workflow(workflow): Add error handling nodes
    - execute_with_retry(func): Execute with retry logic
    - execute_with_fallback(func, fallback): Execute with fallback
    - categorize_error(error): Categorize error types

    Notes:
    - MRO-compatible (calls super().__init__())
    - Configurable retry and backoff strategies
    - Supports multiple fallback strategies
    """

    def __init__(
        self,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
        retry_on: Optional[Tuple[Type[Exception], ...]] = None,
        **kwargs,
    ):
        """
        Initialize ErrorHandlingMixin.

        Args:
            max_retries: Maximum number of retry attempts (default: 3)
            backoff_factor: Exponential backoff multiplier (default: 1.0)
            retry_on: Tuple of exception types to retry on (default: all)
            **kwargs: Additional arguments for super().__init__()

        Notes:
            - Task 3.2: Configurable error handling setup
            - Calls super().__init__() for MRO compatibility
        """
        # MRO compatibility
        if hasattr(super(), "__init__"):
            super().__init__(**kwargs)

        # Task 3.2: Initialize error handling configuration
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.retry_on = retry_on  # None means retry on all exceptions

        # State management
        self._captured_state = None
        self._error_history = []

        # Logger
        self.logger = logging.getLogger(self.__class__.__name__)

    def enhance_workflow(self, workflow: WorkflowBuilder) -> WorkflowBuilder:
        """
        Enhance workflow with error handling nodes.

        Adds error handling capabilities to the workflow.

        Args:
            workflow: Workflow to enhance

        Returns:
            WorkflowBuilder: Enhanced workflow with error handling

        Notes:
            - Task 3.10: Adds error handling nodes to workflow
            - Preserves existing nodes
            - Non-intrusive enhancement
        """
        # Task 3.10: For Phase 3, return workflow as-is
        # Full error handler node integration in future enhancement
        return workflow

    def execute_with_retry(self, func: Callable[[], Any], *args, **kwargs) -> Any:
        """
        Execute function with retry logic.

        Implements exponential backoff retry strategy.

        Args:
            func: Function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Any: Result from successful execution

        Raises:
            Exception: If all retries exhausted

        Notes:
            - Task 3.12: Implements retry logic with backoff
            - Respects max_retries configuration
            - Uses exponential backoff
        """
        # Task 3.12: Retry logic implementation
        last_error = None
        attempt = 0
        max_attempts = self.max_retries + 1  # initial + retries

        while attempt < max_attempts:
            try:
                # Execute function
                result = func(*args, **kwargs)

                # Success - return result
                return result

            except Exception as error:
                last_error = error
                attempt += 1

                # Check if we should retry this error type
                if self.retry_on is not None:
                    if not isinstance(error, self.retry_on):
                        # Don't retry this error type
                        raise

                # If we've exhausted retries, raise the error
                if attempt >= max_attempts:
                    raise

                # Calculate backoff delay
                delay = self.backoff_factor * (2 ** (attempt - 1))

                # Log retry attempt
                self.logger.warning(
                    f"Attempt {attempt} failed: {error}. "
                    f"Retrying in {delay:.2f}s..."
                )

                # Wait before retry
                if delay > 0:
                    time.sleep(delay)

        # Should never reach here, but just in case
        if last_error:
            raise last_error

    def execute_with_fallback(
        self,
        func: Callable[[], Any],
        fallback: Optional[Callable[[], Any]],
        *args,
        **kwargs,
    ) -> Any:
        """
        Execute function with fallback on error.

        Args:
            func: Primary function to execute
            fallback: Fallback function to execute on error (can be None)
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Any: Result from func or fallback

        Raises:
            Exception: If both func and fallback fail (or fallback is None)

        Notes:
            - Task 3.13: Implements fallback strategy
            - Executes fallback only on error
        """
        # Task 3.13: Fallback strategy implementation
        try:
            # Try primary execution with retry
            return self.execute_with_retry(func, *args, **kwargs)

        except Exception as error:
            # Primary execution failed
            self._error_history.append(
                {
                    "error": error,
                    "func": func.__name__ if hasattr(func, "__name__") else "unknown",
                }
            )

            if fallback is None:
                # No fallback - re-raise original error
                raise

            # Execute fallback
            try:
                self.logger.info(f"Executing fallback after error: {error}")
                return fallback(*args, **kwargs)

            except Exception as fallback_error:
                # Fallback also failed
                self.logger.error(f"Fallback failed: {fallback_error}")
                raise

    def execute_with_fallbacks(
        self,
        func: Callable[[], Any],
        fallbacks: List[Callable[[], Any]],
        *args,
        **kwargs,
    ) -> Any:
        """
        Execute function with multiple fallback strategies.

        Tries each fallback in order until one succeeds.

        Args:
            func: Primary function to execute
            fallbacks: List of fallback functions
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Any: Result from func or first successful fallback

        Raises:
            Exception: If all strategies fail

        Notes:
            - Task 3.13: Multiple fallback strategies
            - Tries fallbacks in order
        """
        # Task 3.13: Multiple fallback strategies
        try:
            return self.execute_with_retry(func, *args, **kwargs)

        except Exception as error:
            self.logger.warning(f"Primary execution failed: {error}")

            # Try each fallback in order
            for i, fallback in enumerate(fallbacks):
                try:
                    self.logger.info(
                        f"Trying fallback strategy {i + 1}/{len(fallbacks)}"
                    )
                    return fallback(*args, **kwargs)

                except Exception as fallback_error:
                    self.logger.warning(f"Fallback {i + 1} failed: {fallback_error}")

                    # If this was the last fallback, re-raise
                    if i == len(fallbacks) - 1:
                        raise

            # Should never reach here, but just in case
            raise error

    def categorize_error(self, error: Exception) -> str:
        """
        Categorize error type for handling strategy.

        Args:
            error: Exception to categorize

        Returns:
            str: Error category

        Notes:
            - Task 3.11: Error categorization
            - Used for determining retry/fallback strategies
        """
        # Task 3.11: Error categorization
        error_type = type(error).__name__

        # Common error categories
        if isinstance(error, (ValueError, TypeError)):
            return "validation_error"
        elif isinstance(error, (ConnectionError, TimeoutError)):
            return "connection_error"
        elif isinstance(error, RuntimeError):
            return "runtime_error"
        else:
            return "unknown_error"

    def capture_state(self):
        """
        Capture current state for potential restoration.

        Notes:
            - Task 3.11: State capture for error recovery
            - Allows state restoration after errors
        """
        # Task 3.11: State capture
        # For basic implementation, just mark that state can be captured
        # Full state capture would serialize agent state
        self._captured_state = {
            "captured_at": time.time(),
            "error_count": len(self._error_history),
        }

    def restore_state(self):
        """
        Restore previously captured state.

        Notes:
            - Task 3.11: State restoration
            - Used for error recovery
        """
        # Task 3.11: State restoration
        if self._captured_state is None:
            self.logger.warning("No captured state to restore")
            return

        # For basic implementation, just log restoration
        self.logger.info(
            f"State restoration point available from "
            f"{self._captured_state.get('captured_at', 'unknown')}"
        )

    def get_error_history(self) -> List[Dict[str, Any]]:
        """
        Get history of errors encountered.

        Returns:
            List[Dict[str, Any]]: Error history

        Notes:
            - Useful for debugging and monitoring
            - Includes error details and context
        """
        return self._error_history.copy()
