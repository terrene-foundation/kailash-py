"""
Fluent API for Cyclic Workflow Creation.

This module provides an intuitive, chainable API for creating cyclic workflows
with enhanced developer experience and IDE support. The CycleBuilder pattern
makes cycle configuration more discoverable and type-safe while maintaining
full backward compatibility with existing workflow construction methods.

Examples:
    Basic cycle creation:

    >>> workflow = Workflow("optimization", "Optimization Loop")
    >>> cycle = workflow.create_cycle("quality_improvement")
    >>> cycle.connect("processor", "evaluator") \
    ...      .max_iterations(50) \
    ...      .converge_when("quality > 0.9") \
    ...      .timeout(300) \
    ...      .build()

    Advanced configuration:

    >>> cycle = workflow.create_cycle("complex_optimization") \
    ...     .connect("optimizer", "evaluator", {"result": "input_data"}) \
    ...     .max_iterations(100) \
    ...     .converge_when("improvement < 0.001") \
    ...     .timeout(600) \
    ...     .memory_limit(2048) \
    ...     .when("needs_optimization == True") \
    ...     .nested_in("outer_cycle") \
    ...     .build()

    Template integration:

    >>> from kailash.workflow.cycle_config import CycleTemplates
    >>> config = CycleTemplates.optimization_loop(max_iterations=50)
    >>> cycle = CycleBuilder.from_config(workflow, config) \
    ...     .connect("processor", "evaluator") \
    ...     .timeout(120)  # Override template value
    ...     .build()
"""

import logging
from typing import TYPE_CHECKING

from kailash.sdk_exceptions import WorkflowValidationError
from kailash.workflow.cycle_exceptions import (
    CycleConfigurationError,
    CycleConnectionError,
)

if TYPE_CHECKING:
    from .cycle_config import CycleConfig
    from .graph import Workflow

logger = logging.getLogger(__name__)


class CycleBuilder:
    """
    Fluent builder for creating cyclic workflow connections.

    This class provides an intuitive, chainable API for configuring cyclic
    connections in workflows. It replaces the verbose parameter-heavy approach
    with a more discoverable and type-safe builder pattern.

    Examples:
        Creating a basic cycle:

        >>> workflow = Workflow("optimization", "Optimization Loop")
        >>> cycle = workflow.create_cycle("quality_improvement")
        >>> cycle.connect("processor", "evaluator") \
        ...      .max_iterations(50) \
        ...      .converge_when("quality > 0.9") \
        ...      .timeout(300) \
        ...      .build()
    """

    def __init__(self, workflow: "Workflow", cycle_id: str | None = None):
        """
        Initialize a new CycleBuilder.

        Args:
            workflow: The workflow to add the cycle to.
            cycle_id: Optional identifier for the cycle group.
        """
        self._workflow = workflow
        self._cycle_id = cycle_id

        # Connection parameters
        self._source_node: str | None = None
        self._target_node: str | None = None
        self._mapping: dict[str, str] | None = None

        # Cycle parameters
        self._max_iterations: int | None = None
        self._convergence_check: str | None = None
        self._timeout: float | None = None
        self._memory_limit: int | None = None
        self._condition: str | None = None
        self._parent_cycle: str | None = None

    def connect(
        self,
        source_node: str,
        target_node: str,
        mapping: dict[str, str] | None = None,
    ) -> "CycleBuilder":
        """
        Configure the source and target nodes for the cycle connection.

        Establishes which nodes will be connected in a cyclic pattern. The
        mapping parameter defines how outputs from the source node map to
        inputs of the target node.

        Args:
            source_node: Node ID that produces output for the cycle.
            target_node: Node ID that receives input from the cycle.
            mapping: Output-to-input mapping. Keys are source output fields,
                values are target input fields. If None, attempts automatic
                mapping based on parameter names.

        Returns:
            Self for method chaining.

        Raises:
            WorkflowValidationError: If source or target node doesn't exist.
            CycleConfigurationError: If nodes are invalid for cyclic connection.

        Examples:
            >>> cycle.connect("processor", "evaluator", {"result": "input_data"})
            >>> # Or with automatic mapping
            >>> cycle.connect("node_a", "node_b")
        """
        # Validate nodes exist in workflow
        available_nodes = list(self._workflow.nodes.keys())

        if source_node not in self._workflow.nodes:
            raise CycleConnectionError(
                f"Source node '{source_node}' not found in workflow",
                source_node=source_node,
                available_nodes=available_nodes,
                error_code="CYCLE_CONN_001",
            )

        if target_node not in self._workflow.nodes:
            raise CycleConnectionError(
                f"Target node '{target_node}' not found in workflow",
                target_node=target_node,
                available_nodes=available_nodes,
                error_code="CYCLE_CONN_002",
            )

        self._source_node = source_node
        self._target_node = target_node
        self._mapping = mapping

        return self

    def max_iterations(self, iterations: int) -> "CycleBuilder":
        """
        Set the maximum number of cycle iterations for safety.

        Provides a hard limit on cycle execution to prevent infinite loops.
        This is a critical safety mechanism for production workflows.

        Args:
            iterations: Maximum number of iterations allowed. Must be positive.
                Recommended range: 10-1000 depending on use case.

        Returns:
            Self for method chaining.

        Raises:
            CycleConfigurationError: If iterations is not positive.

        Examples:
            >>> cycle.max_iterations(100)  # Allow up to 100 iterations
            >>> cycle.max_iterations(10)   # Quick convergence expected
        """
        if iterations <= 0:
            raise CycleConfigurationError(
                "max_iterations must be positive",
                cycle_id=self._cycle_id,
                invalid_params={"max_iterations": iterations},
                error_code="CYCLE_CONFIG_002",
                suggestions=[
                    "Use 10-100 iterations for quick convergence",
                    "Use 100-1000 iterations for complex optimization",
                    "Consider adding convergence_check for early termination",
                ],
            )

        self._max_iterations = iterations
        return self

    def converge_when(self, condition: str) -> "CycleBuilder":
        """
        Set the convergence condition to terminate the cycle early.

        Defines an expression that, when true, will stop cycle execution
        before reaching max_iterations. This enables efficient early
        termination when the desired result is achieved.

        Args:
            condition: Python expression evaluated against node outputs.
                Can reference any output field from cycle nodes.
                Examples: "error < 0.01", "quality > 0.9", "improvement < 0.001"

        Returns:
            Self for method chaining.

        Raises:
            CycleConfigurationError: If condition syntax is invalid.

        Examples:
            >>> cycle.converge_when("error < 0.01")           # Numerical convergence
            >>> cycle.converge_when("quality > 0.95")        # Quality threshold
            >>> cycle.converge_when("improvement < 0.001")   # Minimal improvement
        """
        if not condition or not isinstance(condition, str):
            raise CycleConfigurationError(
                "Convergence condition must be a non-empty string expression. "
                "Examples: 'error < 0.01', 'quality > 0.9', 'count >= 10'"
            )

        # Basic validation - check for dangerous operations
        dangerous_patterns = ["import ", "exec(", "eval(", "__"]
        for pattern in dangerous_patterns:
            if pattern in condition:
                raise CycleConfigurationError(
                    f"Convergence condition contains potentially unsafe operation: '{pattern}'. "
                    "Use simple comparison expressions only."
                )

        self._convergence_check = condition
        return self

    def timeout(self, seconds: float) -> "CycleBuilder":
        """
        Set a timeout limit for cycle execution.

        Provides time-based safety limit to prevent cycles from running
        indefinitely. Useful for cycles that might have unpredictable
        convergence times.

        Args:
            seconds: Maximum execution time in seconds. Must be positive.
                Recommended: 30-3600 seconds.

        Returns:
            Self for method chaining.

        Raises:
            CycleConfigurationError: If timeout is not positive.

        Examples:
            >>> cycle.timeout(300)    # 5 minutes maximum
            >>> cycle.timeout(30.5)   # 30.5 seconds for quick cycles
        """
        if seconds <= 0:
            raise CycleConfigurationError(
                f"Timeout must be positive, got {seconds}. "
                "Recommendation: Use 30-300 seconds for most cycles, "
                "up to 3600 seconds for long-running optimization."
            )

        self._timeout = seconds
        return self

    def memory_limit(self, mb: int) -> "CycleBuilder":
        """
        Set a memory usage limit for cycle execution.

        Provides memory-based safety limit to prevent cycles from consuming
        excessive memory through data accumulation across iterations.

        Args:
            mb: Maximum memory usage in megabytes. Must be positive.
                Recommended: 100-10000 MB.

        Returns:
            Self for method chaining.

        Raises:
            CycleConfigurationError: If memory limit is not positive.

        Examples:
            >>> cycle.memory_limit(1024)  # 1GB limit
            >>> cycle.memory_limit(512)   # 512MB for smaller workflows
        """
        if mb <= 0:
            raise CycleConfigurationError(
                f"Memory limit must be positive, got {mb}. "
                "Recommendation: Use 100-1000 MB for most cycles, "
                "up to 10000 MB for data-intensive processing."
            )

        self._memory_limit = mb
        return self

    def when(self, condition: str) -> "CycleBuilder":
        """
        Set a conditional expression for cycle routing.

        Enables conditional cycle execution where the cycle only runs
        when the specified condition is met. Useful for adaptive workflows.

        Args:
            condition: Python expression for conditional execution.
                Evaluated before each cycle iteration.

        Returns:
            Self for method chaining.

        Raises:
            CycleConfigurationError: If condition syntax is invalid.

        Examples:
            >>> cycle.when("retry_count < 3")      # Retry logic
            >>> cycle.when("needs_optimization")   # Conditional optimization
        """
        if not condition or not isinstance(condition, str):
            raise CycleConfigurationError(
                "Condition must be a non-empty string expression. "
                "Examples: 'retry_count < 3', 'needs_improvement == True'"
            )

        self._condition = condition
        return self

    def nested_in(self, parent_cycle_id: str) -> "CycleBuilder":
        """
        Make this cycle nested within another cycle.

        Enables hierarchical cycle structures where one cycle operates
        within the iterations of a parent cycle. Useful for multi-level
        optimization scenarios.

        Args:
            parent_cycle_id: Identifier of the parent cycle.

        Returns:
            Self for method chaining.

        Raises:
            CycleConfigurationError: If parent cycle ID is invalid.

        Examples:
            >>> cycle.nested_in("outer_optimization")  # This cycle runs inside outer_optimization
        """
        if not parent_cycle_id or not isinstance(parent_cycle_id, str):
            raise CycleConfigurationError("Parent cycle ID must be a non-empty string")

        self._parent_cycle = parent_cycle_id
        return self

    def build(self) -> None:
        """
        Build and add the configured cycle to the workflow.

        Validates the cycle configuration and creates the actual cyclic
        connection in the workflow. This finalizes the cycle builder
        pattern and applies all configured settings.

        Raises:
            CycleConfigurationError: If cycle configuration is incomplete or invalid.
            WorkflowValidationError: If workflow connection fails.

        Examples:
            >>> cycle.connect("node_a", "node_b") \
            ...      .max_iterations(50) \
            ...      .converge_when("quality > 0.9") \
            ...      .build()  # Creates the cycle in the workflow
        """
        # Validate required parameters
        if not self._source_node or not self._target_node:
            raise CycleConfigurationError(
                "Cycle must have source and target nodes configured. "
                "Call connect(source_node, target_node) before build()."
            )

        # Validate at least one termination condition
        if (
            not self._max_iterations
            and not self._convergence_check
            and not self._timeout
        ):
            raise CycleConfigurationError(
                "Cycle must have at least one termination condition. "
                "Add max_iterations(), converge_when(), or timeout() before build(). "
                "Recommendation: Always include max_iterations() as a safety net."
            )

        # Create the connection using the workflow's connect method
        try:
            self._workflow.connect(
                source_node=self._source_node,
                target_node=self._target_node,
                mapping=self._mapping,
                cycle=True,
                max_iterations=self._max_iterations,
                convergence_check=self._convergence_check,
                cycle_id=self._cycle_id,
                timeout=self._timeout,
                memory_limit=self._memory_limit,
                condition=self._condition,
                parent_cycle=self._parent_cycle,
            )

            logger.info(
                f"Created cycle '{self._cycle_id or 'unnamed'}' from "
                f"{self._source_node} to {self._target_node} with "
                f"max_iterations={self._max_iterations}, "
                f"convergence='{self._convergence_check}'"
            )

        except Exception as e:
            raise WorkflowValidationError(
                f"Failed to create cycle connection: {e}"
            ) from e

    @classmethod
    def from_config(cls, workflow: "Workflow", config: "CycleConfig") -> "CycleBuilder":
        """
        Create a CycleBuilder from a CycleConfig instance.

        Provides an alternative constructor that initializes the builder
        with all configuration from a type-safe CycleConfig object. This
        enables configuration reuse, templating, and structured configuration
        management across multiple cycles.

        Args:
            workflow: Target workflow for the cycle.
            config: Pre-configured cycle parameters.

        Returns:
            Builder instance initialized with config values.

        Raises:
            CycleConfigurationError: If config is invalid.
            ImportError: If CycleConfig module is not available.

        Examples:
            Using a template:

            >>> config = CycleTemplates.optimization_loop(max_iterations=50)
            >>> builder = CycleBuilder.from_config(workflow, config)
            >>> builder.connect("optimizer", "evaluator").build()

            Using custom configuration:

            >>> config = CycleConfig(max_iterations=100, timeout=300)
            >>> builder = CycleBuilder.from_config(workflow, config)
            >>> builder.connect("processor", "evaluator").build()
        """
        try:
            from kailash.workflow.cycle_config import CycleConfig
        except ImportError as e:
            raise ImportError(
                "CycleConfig not available. Ensure kailash.workflow.cycle_config is installed."
            ) from e

        # Validate config is correct type
        if not isinstance(config, CycleConfig):
            raise CycleConfigurationError(
                f"Expected CycleConfig instance, got {type(config)}. "
                "Use CycleConfig() or CycleTemplates.* to create valid configuration."
            )

        # Create builder with config values
        builder = cls(workflow=workflow, cycle_id=config.cycle_id)

        # Apply configuration parameters
        if config.max_iterations is not None:
            builder._max_iterations = config.max_iterations

        if config.convergence_check is not None:
            if isinstance(config.convergence_check, str):
                builder._convergence_check = config.convergence_check
            else:
                # For callable convergence checks, convert to description
                builder._convergence_check = "<callable_convergence_check>"

        if config.timeout is not None:
            builder._timeout = config.timeout

        if config.memory_limit is not None:
            builder._memory_limit = config.memory_limit

        if config.condition is not None:
            builder._condition = config.condition

        if config.parent_cycle is not None:
            builder._parent_cycle = config.parent_cycle

        return builder

    def apply_config(self, config: "CycleConfig") -> "CycleBuilder":
        """
        Apply configuration from a CycleConfig instance to this builder.

        Merges configuration parameters from a CycleConfig object into
        the current builder state. This allows combining fluent builder
        calls with structured configuration objects for maximum flexibility.

        Args:
            config: Configuration to apply to this builder.

        Returns:
            Self for method chaining.

        Raises:
            CycleConfigurationError: If config is invalid.

        Examples:
            >>> builder = workflow.create_cycle("custom") \
            ...     .connect("a", "b") \
            ...     .apply_config(CycleTemplates.optimization_loop()) \
            ...     .timeout(120)  # Override the template timeout
            ...     .build()
        """
        try:
            from kailash.workflow.cycle_config import CycleConfig
        except ImportError as e:
            raise ImportError(
                "CycleConfig not available. Ensure kailash.workflow.cycle_config is installed."
            ) from e

        if not isinstance(config, CycleConfig):
            raise CycleConfigurationError(
                f"Expected CycleConfig instance, got {type(config)}"
            )

        # Apply non-None configuration values
        if config.max_iterations is not None:
            self._max_iterations = config.max_iterations

        if config.convergence_check is not None:
            if isinstance(config.convergence_check, str):
                self._convergence_check = config.convergence_check

        if config.timeout is not None:
            self._timeout = config.timeout

        if config.memory_limit is not None:
            self._memory_limit = config.memory_limit

        if config.condition is not None:
            self._condition = config.condition

        if config.parent_cycle is not None:
            self._parent_cycle = config.parent_cycle

        # Update cycle_id if specified in config
        if config.cycle_id is not None:
            self._cycle_id = config.cycle_id

        return self

    def __repr__(self) -> str:
        """
        Return string representation of the cycle builder configuration.

        Returns:
            Human-readable representation of current configuration.

        Examples:
            >>> str(cycle)
            'CycleBuilder(cycle_id=optimization, source=processor, target=evaluator, max_iterations=50)'
        """
        return (
            f"CycleBuilder("
            f"cycle_id={self._cycle_id}, "
            f"source={self._source_node}, "
            f"target={self._target_node}, "
            f"max_iterations={self._max_iterations}, "
            f"convergence='{self._convergence_check}'"
            f")"
        )
