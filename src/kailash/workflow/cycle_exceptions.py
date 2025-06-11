"""
Enhanced exception classes for cyclic workflow operations.

This module provides specialized exception classes with actionable error messages,
debugging context, and suggested solutions for cycle-related errors. These exceptions
replace generic errors with detailed diagnostics to improve developer experience.
"""

import logging
from typing import Any

from kailash.sdk_exceptions import WorkflowException

logger = logging.getLogger(__name__)


class CycleException(WorkflowException):
    """
    Base exception for all cycle-related errors.

    This base class provides common functionality for cycle exceptions
    including error codes, context information, and suggested solutions.
    All cycle-specific exceptions inherit from this class.

    Design Philosophy:
        Provides actionable error messages with specific suggestions for
        resolution. Each exception includes context about what went wrong,
        why it happened, and how to fix it.

    Upstream Dependencies:
        - Inherits from WorkflowException for consistency
        - Used throughout cycle builder and execution systems

    Downstream Consumers:
        - Developer error handling and debugging
        - IDE error highlighting and suggestions
        - Automated error reporting and analysis

    Attributes:
        error_code (str): Unique code for programmatic error handling
        context (Dict[str, Any]): Additional context about the error
        suggestions (List[str]): Actionable suggestions for resolution

    Example:
        >>> try:
        ...     # Some cycle operation
        ...     pass
        ... except CycleException as e:
        ...     print(f"Error: {e}")
        ...     print(f"Code: {e.error_code}")
        ...     print(f"Suggestions: {e.suggestions}")
    """

    def __init__(
        self,
        message: str,
        error_code: str = "CYCLE_ERROR",
        context: dict[str, Any] | None = None,
        suggestions: list[str] | None = None,
        documentation_url: str | None = None,
    ):
        """
        Initialize cycle exception with enhanced error information.

        Args:
            message (str): Human-readable error description
            error_code (str): Unique error code for programmatic handling
            context (Dict[str, Any], optional): Additional error context
            suggestions (List[str], optional): Actionable resolution suggestions
            documentation_url (str, optional): URL to relevant documentation

        Side Effects:
            Logs error details for debugging and analysis
        """
        super().__init__(message)
        self.error_code = error_code
        self.context = context or {}
        self.suggestions = suggestions or []
        self.documentation_url = documentation_url

        # Log error for debugging
        logger.debug(f"CycleException raised: {error_code} - {message}")

    def get_detailed_message(self) -> str:
        """
        Get detailed error message with context and suggestions.

        Returns:
            str: Comprehensive error message with all available information

        Example:
            >>> exception.get_detailed_message()
            'Error: Invalid cycle configuration
            Code: CYCLE_CONFIG_001
            Context: {"cycle_id": "test", "max_iterations": -5}
            Suggestions:
            • Set max_iterations to a positive value (recommended: 10-100)
            • Add convergence_check for early termination
            Documentation: https://docs.kailash.ai/cycles/configuration'
        """
        message_parts = [f"Error: {self.args[0]}"]

        if self.error_code != "CYCLE_ERROR":
            message_parts.append(f"Code: {self.error_code}")

        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            message_parts.append(f"Context: {context_str}")

        if self.suggestions:
            message_parts.append("Suggestions:")
            for suggestion in self.suggestions:
                message_parts.append(f"• {suggestion}")

        if self.documentation_url:
            message_parts.append(f"Documentation: {self.documentation_url}")

        return "\n".join(message_parts)

    def __str__(self) -> str:
        """Return string representation with enhanced details."""
        return self.get_detailed_message()


class CycleConfigurationError(CycleException):
    """
    Raised when cycle configuration is invalid or incomplete.

    This exception provides specific guidance for cycle configuration issues,
    including missing parameters, invalid values, and conflicting settings.
    It helps developers quickly identify and fix configuration problems.

    Common scenarios:
    - Missing required parameters (max_iterations or convergence_check)
    - Invalid parameter values (negative iterations, empty conditions)
    - Unsafe expressions in convergence conditions
    - Conflicting cycle settings

    Example:
        >>> raise CycleConfigurationError(
        ...     "Missing termination condition",
        ...     error_code="CYCLE_CONFIG_001",
        ...     context={"cycle_id": "test"},
        ...     suggestions=["Add max_iterations parameter", "Add convergence_check condition"]
        ... )
    """

    def __init__(
        self,
        message: str,
        cycle_id: str | None = None,
        invalid_params: dict[str, Any] | None = None,
        **kwargs,
    ):
        """
        Initialize cycle configuration error.

        Args:
            message (str): Error description
            cycle_id (str, optional): ID of the problematic cycle
            invalid_params (Dict[str, Any], optional): Invalid parameter values
            **kwargs: Additional arguments for base exception

        Side Effects:
            Automatically generates context and suggestions based on parameters
        """
        context = kwargs.get("context", {})
        suggestions = kwargs.get("suggestions", [])

        # Add cycle-specific context
        if cycle_id:
            context["cycle_id"] = cycle_id
        if invalid_params:
            context.update(invalid_params)

        # Add common suggestions if none provided
        if not suggestions:
            suggestions = [
                "Ensure at least one termination condition (max_iterations, convergence_check, or timeout)",
                "Use positive values for numeric parameters",
                "Avoid unsafe operations in convergence expressions",
                "Check the CycleConfig documentation for valid parameter ranges",
            ]

        super().__init__(
            message,
            error_code=kwargs.get("error_code", "CYCLE_CONFIG_001"),
            context=context,
            suggestions=suggestions,
            documentation_url="https://docs.kailash.ai/cycles/configuration",
        )


class CycleConnectionError(CycleException):
    """
    Raised when cycle connection creation fails.

    This exception handles errors during cycle connection establishment,
    including missing nodes, invalid mappings, and connection conflicts.
    It provides specific guidance for fixing connection issues.

    Common scenarios:
    - Source or target nodes don't exist in workflow
    - Invalid parameter mappings
    - Conflicting cycle connections
    - Missing required connection parameters

    Example:
        >>> raise CycleConnectionError(
        ...     "Source node 'processor' not found",
        ...     source_node="processor",
        ...     available_nodes=["reader", "writer"]
        ... )
    """

    def __init__(
        self,
        message: str,
        source_node: str | None = None,
        target_node: str | None = None,
        available_nodes: list[str] | None = None,
        mapping_errors: dict[str, str] | None = None,
        **kwargs,
    ):
        """
        Initialize cycle connection error.

        Args:
            message (str): Error description
            source_node (str, optional): Source node ID
            target_node (str, optional): Target node ID
            available_nodes (List[str], optional): Available node IDs
            mapping_errors (Dict[str, str], optional): Parameter mapping errors
            **kwargs: Additional arguments for base exception
        """
        context = kwargs.get("context", {})
        suggestions = kwargs.get("suggestions", [])

        # Add connection-specific context
        if source_node:
            context["source_node"] = source_node
        if target_node:
            context["target_node"] = target_node
        if available_nodes:
            context["available_nodes"] = available_nodes
        if mapping_errors:
            context["mapping_errors"] = mapping_errors

        # Generate specific suggestions
        if not suggestions:
            suggestions = []
            if available_nodes:
                suggestions.append(f"Available nodes: {', '.join(available_nodes)}")
            if source_node and available_nodes and source_node not in available_nodes:
                suggestions.append(
                    f"Add node '{source_node}' to workflow before connecting"
                )
            if mapping_errors:
                suggestions.append(
                    "Check parameter mappings for typos and type compatibility"
                )
            suggestions.append("Verify node IDs match exactly (case-sensitive)")

        super().__init__(
            message,
            error_code=kwargs.get("error_code", "CYCLE_CONN_001"),
            context=context,
            suggestions=suggestions,
            documentation_url="https://docs.kailash.ai/cycles/connections",
        )


class CycleValidationError(CycleException):
    """
    Raised when cycle validation fails during workflow validation.

    This exception handles validation errors for complete cycle configurations,
    including cycle graph analysis, parameter compatibility, and safety checks.

    Common scenarios:
    - Circular dependencies without proper cycle marking
    - Conflicting cycle parameters within groups
    - Invalid nested cycle relationships
    - Unsafe cycle configurations

    Example:
        >>> raise CycleValidationError(
        ...     "Conflicting max_iterations in cycle group",
        ...     cycle_group="optimization",
        ...     conflicting_values=[50, 100, 75]
        ... )
    """

    def __init__(
        self,
        message: str,
        cycle_group: str | None = None,
        validation_failures: list[str] | None = None,
        conflicting_values: list[Any] | None = None,
        **kwargs,
    ):
        """
        Initialize cycle validation error.

        Args:
            message (str): Error description
            cycle_group (str, optional): Affected cycle group ID
            validation_failures (List[str], optional): List of validation failures
            conflicting_values (List[Any], optional): Conflicting parameter values
            **kwargs: Additional arguments for base exception
        """
        context = kwargs.get("context", {})
        suggestions = kwargs.get("suggestions", [])

        # Add validation-specific context
        if cycle_group:
            context["cycle_group"] = cycle_group
        if validation_failures:
            context["validation_failures"] = validation_failures
        if conflicting_values:
            context["conflicting_values"] = conflicting_values

        # Generate validation-specific suggestions
        if not suggestions:
            suggestions = [
                "Review cycle configuration for consistency",
                "Ensure all cycle edges use the same parameters",
                "Check for proper cycle marking (cycle=True)",
                "Validate nested cycle relationships",
            ]
            if conflicting_values:
                suggestions.append("Use consistent parameter values across cycle group")

        super().__init__(
            message,
            error_code=kwargs.get("error_code", "CYCLE_VALID_001"),
            context=context,
            suggestions=suggestions,
            documentation_url="https://docs.kailash.ai/cycles/validation",
        )


class CycleExecutionError(CycleException):
    """
    Raised when cycle execution fails during runtime.

    This exception handles runtime errors during cycle execution,
    including convergence failures, timeout issues, and iteration problems.

    Common scenarios:
    - Cycle fails to converge within max_iterations
    - Timeout exceeded during cycle execution
    - Memory limit exceeded
    - Node execution failures within cycles

    Example:
        >>> raise CycleExecutionError(
        ...     "Cycle timeout exceeded",
        ...     cycle_id="optimization",
        ...     current_iteration=50,
        ...     timeout_seconds=300
        ... )
    """

    def __init__(
        self,
        message: str,
        cycle_id: str | None = None,
        current_iteration: int | None = None,
        max_iterations: int | None = None,
        timeout_seconds: float | None = None,
        memory_usage_mb: int | None = None,
        **kwargs,
    ):
        """
        Initialize cycle execution error.

        Args:
            message (str): Error description
            cycle_id (str, optional): ID of the failing cycle
            current_iteration (int, optional): Current iteration count
            max_iterations (int, optional): Maximum allowed iterations
            timeout_seconds (float, optional): Timeout limit in seconds
            memory_usage_mb (int, optional): Current memory usage
            **kwargs: Additional arguments for base exception
        """
        context = kwargs.get("context", {})
        suggestions = kwargs.get("suggestions", [])

        # Add execution-specific context
        if cycle_id:
            context["cycle_id"] = cycle_id
        if current_iteration is not None:
            context["current_iteration"] = current_iteration
        if max_iterations is not None:
            context["max_iterations"] = max_iterations
        if timeout_seconds is not None:
            context["timeout_seconds"] = timeout_seconds
        if memory_usage_mb is not None:
            context["memory_usage_mb"] = memory_usage_mb

        # Generate execution-specific suggestions
        if not suggestions:
            suggestions = []
            if (
                current_iteration
                and max_iterations
                and current_iteration >= max_iterations
            ):
                suggestions.extend(
                    [
                        "Increase max_iterations if more iterations are needed",
                        "Add or improve convergence_check for early termination",
                        "Review cycle logic for efficiency improvements",
                    ]
                )
            if timeout_seconds:
                suggestions.extend(
                    [
                        "Increase timeout limit if legitimate long execution is expected",
                        "Optimize node processing for faster execution",
                        "Consider breaking into smaller cycles",
                    ]
                )
            if memory_usage_mb:
                suggestions.extend(
                    [
                        "Increase memory_limit if more memory is needed",
                        "Optimize data handling to reduce memory usage",
                        "Consider streaming or chunked processing",
                    ]
                )

        super().__init__(
            message,
            error_code=kwargs.get("error_code", "CYCLE_EXEC_001"),
            context=context,
            suggestions=suggestions,
            documentation_url="https://docs.kailash.ai/cycles/execution",
        )


class CycleConvergenceError(CycleException):
    """
    Raised when cycle convergence detection fails or behaves unexpectedly.

    This exception handles convergence-related issues, including expression
    evaluation errors, impossible convergence conditions, and convergence
    detection failures.

    Common scenarios:
    - Convergence expression evaluation fails
    - Convergence condition references undefined variables
    - Convergence logic contradicts cycle behavior
    - Premature or delayed convergence detection

    Example:
        >>> raise CycleConvergenceError(
        ...     "Convergence expression evaluation failed",
        ...     convergence_expression="undefined_var > 0.5",
        ...     available_variables=["value", "quality", "iteration"]
        ... )
    """

    def __init__(
        self,
        message: str,
        convergence_expression: str | None = None,
        evaluation_error: str | None = None,
        available_variables: list[str] | None = None,
        cycle_data: dict[str, Any] | None = None,
        **kwargs,
    ):
        """
        Initialize cycle convergence error.

        Args:
            message (str): Error description
            convergence_expression (str, optional): The problematic expression
            evaluation_error (str, optional): Expression evaluation error details
            available_variables (List[str], optional): Available variable names
            cycle_data (Dict[str, Any], optional): Current cycle data
            **kwargs: Additional arguments for base exception
        """
        context = kwargs.get("context", {})
        suggestions = kwargs.get("suggestions", [])

        # Add convergence-specific context
        if convergence_expression:
            context["convergence_expression"] = convergence_expression
        if evaluation_error:
            context["evaluation_error"] = evaluation_error
        if available_variables:
            context["available_variables"] = available_variables
        if cycle_data:
            context["cycle_data"] = {
                k: str(v)[:100] for k, v in cycle_data.items()
            }  # Truncate for readability

        # Generate convergence-specific suggestions
        if not suggestions:
            suggestions = [
                "Check convergence expression syntax for typos",
                "Ensure all referenced variables exist in cycle output",
                "Use simple comparison operators (>, <, ==, >=, <=)",
                "Avoid complex logic or function calls in expressions",
            ]
            if available_variables:
                suggestions.append(
                    f"Available variables: {', '.join(available_variables)}"
                )
            if convergence_expression and evaluation_error:
                suggestions.append("Test convergence expression with sample data")

        super().__init__(
            message,
            error_code=kwargs.get("error_code", "CYCLE_CONV_001"),
            context=context,
            suggestions=suggestions,
            documentation_url="https://docs.kailash.ai/cycles/convergence",
        )


# Utility functions for enhanced error reporting
def create_configuration_error(
    issue: str, cycle_id: str | None = None, **invalid_params
) -> CycleConfigurationError:
    """
    Create a standardized configuration error with common suggestions.

    Args:
        issue (str): Description of the configuration issue
        cycle_id (str, optional): Cycle identifier
        **invalid_params: Invalid parameter values

    Returns:
        CycleConfigurationError: Configured exception with context

    Example:
        >>> error = create_configuration_error(
        ...     "Invalid max_iterations value",
        ...     cycle_id="test",
        ...     max_iterations=-5
        ... )
    """
    return CycleConfigurationError(
        message=issue, cycle_id=cycle_id, invalid_params=invalid_params
    )


def create_connection_error(
    issue: str,
    source_node: str | None = None,
    target_node: str | None = None,
    available_nodes: list[str] | None = None,
) -> CycleConnectionError:
    """
    Create a standardized connection error with node context.

    Args:
        issue (str): Description of the connection issue
        source_node (str, optional): Source node ID
        target_node (str, optional): Target node ID
        available_nodes (List[str], optional): Available node IDs

    Returns:
        CycleConnectionError: Configured exception with context

    Example:
        >>> error = create_connection_error(
        ...     "Node not found",
        ...     source_node="missing",
        ...     available_nodes=["node1", "node2"]
        ... )
    """
    return CycleConnectionError(
        message=issue,
        source_node=source_node,
        target_node=target_node,
        available_nodes=available_nodes,
    )


def create_execution_error(
    issue: str,
    cycle_id: str | None = None,
    current_iteration: int | None = None,
    max_iterations: int | None = None,
) -> CycleExecutionError:
    """
    Create a standardized execution error with runtime context.

    Args:
        issue (str): Description of the execution issue
        cycle_id (str, optional): Cycle identifier
        current_iteration (int, optional): Current iteration
        max_iterations (int, optional): Maximum iterations

    Returns:
        CycleExecutionError: Configured exception with context

    Example:
        >>> error = create_execution_error(
        ...     "Max iterations exceeded",
        ...     cycle_id="optimization",
        ...     current_iteration=100,
        ...     max_iterations=100
        ... )
    """
    return CycleExecutionError(
        message=issue,
        cycle_id=cycle_id,
        current_iteration=current_iteration,
        max_iterations=max_iterations,
    )
