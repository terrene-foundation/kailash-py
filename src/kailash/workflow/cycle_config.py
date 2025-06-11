"""
Type-Safe Configuration System for Cyclic Workflows.

This module provides a comprehensive, type-safe configuration system for cyclic
workflows using Python dataclasses with runtime validation. It enables
structured cycle configuration with full IDE support, compile-time type
checking, and extensive validation to prevent common configuration errors.

Design Philosophy:
    Provides compile-time type safety and runtime validation for cycle
    configurations, replacing loose parameter passing with validated
    configuration objects. Enables configuration reuse, templating, and
    standardization across workflows while maintaining maximum flexibility.

Key Features:
    - Dataclass-based configuration with automatic validation
    - Pre-built templates for common cycle patterns
    - Configuration merging and composition
    - Export/import capabilities for configuration persistence
    - Comprehensive validation with actionable error messages

Configuration Categories:
    1. Termination Conditions: max_iterations, timeout, convergence_check
    2. Safety Limits: memory_limit, iteration_safety_factor
    3. Cycle Metadata: cycle_id, parent_cycle, description
    4. Execution Control: condition, priority, retry_policy

Validation Strategy:
    Performs comprehensive validation at initialization and modification,
    checking parameter types, ranges, safety constraints, and logical
    consistency. Provides specific, actionable error messages.

Upstream Dependencies:
    - Used by CycleBuilder.build() for configuration validation
    - Can be used directly with Workflow.connect() for type safety
    - Supports serialization for configuration persistence

Downstream Consumers:
    - CyclicWorkflowExecutor for execution of configured cycles
    - Cycle debugging and profiling tools for configuration analysis
    - Configuration templates and presets for common patterns
    - Workflow generation and automation tools

Template System:
    CycleTemplates class provides factory methods for creating optimized
    configurations for specific use cases, reducing boilerplate and ensuring
    best practices are followed automatically.

Example Usage:
    Basic configuration:

    >>> from kailash.workflow.cycle_config import CycleConfig
    >>> config = CycleConfig(
    ...     max_iterations=100,
    ...     convergence_check="error < 0.01",
    ...     timeout=300.0,
    ...     cycle_id="optimization_loop"
    ... )
    >>> # Use with workflow
    >>> workflow.connect(
    ...     "processor", "evaluator",
    ...     cycle=True, cycle_config=config
    ... )

    Template usage:

    >>> from kailash.workflow.cycle_config import CycleTemplates
    >>> # Pre-optimized configuration
    >>> config = CycleTemplates.optimization_loop(
    ...     max_iterations=200,
    ...     convergence_threshold=0.001
    ... )
    >>> # Customize template
    >>> custom_config = config.merge(CycleConfig(
    ...     timeout=600.0,
    ...     memory_limit=2048
    ... ))

    Configuration management:

    >>> # Export for reuse
    >>> template_data = config.create_template("ml_training")
    >>> # Import and modify
    >>> loaded_config = CycleConfig.from_dict(template_data["configuration"])
    >>> # Validation and safety
    >>> config.validate()  # Explicit validation
    >>> effective_max = config.get_effective_max_iterations()  # With safety factor

See Also:
    - :mod:`kailash.workflow.cycle_builder` for fluent configuration API
    - :mod:`kailash.workflow.templates` for pre-built cycle patterns
    - :doc:`/guides/configuration` for configuration best practices
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from kailash.workflow.cycle_exceptions import CycleConfigurationError

logger = logging.getLogger(__name__)


@dataclass
class CycleConfig:
    """
    Type-safe configuration for cyclic workflow connections.

    This dataclass provides a structured, type-safe way to configure cycle
    parameters with validation, default values, and comprehensive error
    checking. It replaces loose parameter passing with a validated configuration
    object that can be reused across multiple cycles.

    Design Philosophy:
        Provides compile-time type safety and runtime validation for cycle
        configurations. Enables configuration reuse, templating, and
        standardization across workflows while maintaining flexibility.

    Upstream Dependencies:
        - Used by CycleBuilder.build() for configuration validation
        - Can be used directly with Workflow.connect() for type safety
        - Supports serialization for configuration persistence

    Downstream Consumers:
        - CyclicWorkflowExecutor for execution of configured cycles
        - Cycle debugging and profiling tools for configuration analysis
        - Configuration templates and presets for common patterns

    Configuration Categories:
        1. Termination Conditions: max_iterations, timeout, convergence_check
        2. Safety Limits: memory_limit, iteration_safety_factor
        3. Cycle Metadata: cycle_id, parent_cycle, description
        4. Execution Control: condition, priority, retry_policy

    Example:
        >>> # Basic configuration
        >>> config = CycleConfig(max_iterations=100, convergence_check="error < 0.01")
        >>> workflow.connect("a", "b", cycle_config=config)

        >>> # Advanced configuration with all features
        >>> config = CycleConfig(
        ...     max_iterations=50,
        ...     convergence_check="quality > 0.95",
        ...     timeout=300.0,
        ...     memory_limit=1024,
        ...     cycle_id="optimization_loop",
        ...     description="Quality optimization cycle",
        ...     condition="needs_optimization == True"
        ... )
    """

    # Termination conditions (at least one required)
    max_iterations: int | None = None
    convergence_check: str | Callable | None = None
    timeout: float | None = None

    # Safety and resource limits
    memory_limit: int | None = None
    iteration_safety_factor: float = 1.5  # Multiplier for max_iterations safety

    # Cycle metadata and identification
    cycle_id: str | None = None
    parent_cycle: str | None = None
    description: str = ""

    # Execution control and conditions
    condition: str | None = None  # When to execute the cycle
    priority: int = 0  # Execution priority for multiple cycles

    # Advanced configuration
    retry_policy: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """
        Validate configuration after initialization.

        Performs comprehensive validation of all configuration parameters
        to ensure they are valid, compatible, and safe for cycle execution.

        Raises:
            CycleConfigurationError: If configuration is invalid or unsafe

        Side Effects:
            Logs validation warnings for suboptimal configurations
            Applies automatic fixes for minor configuration issues
        """
        self.validate()

    def validate(self) -> None:
        """
        Validate the cycle configuration for correctness and safety.

        Performs comprehensive validation of all configuration parameters,
        checking for required fields, valid ranges, unsafe expressions,
        and configuration conflicts. Provides actionable error messages
        for any validation failures.

        Raises:
            CycleConfigurationError: If configuration is invalid

        Side Effects:
            Logs warnings for suboptimal but valid configurations
            May modify configuration for automatic safety improvements

        Example:
            >>> config = CycleConfig(max_iterations=-5)  # Will raise error
            >>> config.validate()  # CycleConfigurationError
        """
        errors = []
        warnings = []

        # Validate termination conditions (at least one required)
        termination_conditions = [
            self.max_iterations is not None,
            self.convergence_check is not None,
            self.timeout is not None,
        ]

        if not any(termination_conditions):
            errors.append(
                "At least one termination condition is required: "
                "max_iterations, convergence_check, or timeout. "
                "Recommendation: Always include max_iterations as a safety net."
            )

        # Validate max_iterations
        if self.max_iterations is not None:
            if not isinstance(self.max_iterations, int):
                raise CycleConfigurationError(
                    f"max_iterations must be an integer, got {type(self.max_iterations)}",
                    error_code="CYCLE_CONFIG_002",
                    invalid_params={"max_iterations": self.max_iterations},
                    suggestions=[
                        "Use integer values for max_iterations",
                        "Convert float values to int if needed",
                    ],
                )
            elif self.max_iterations <= 0:
                raise CycleConfigurationError(
                    f"max_iterations must be positive, got {self.max_iterations}",
                    error_code="CYCLE_CONFIG_002",
                    invalid_params={"max_iterations": self.max_iterations},
                    suggestions=[
                        "Use 10-100 iterations for quick convergence",
                        "Use 100-1000 iterations for complex optimization",
                        "Consider adding convergence_check for early termination",
                    ],
                )
            elif self.max_iterations > 10000:
                warnings.append(
                    f"max_iterations={self.max_iterations} is very high. "
                    "Consider using convergence_check for efficiency."
                )

        # Validate convergence_check
        if self.convergence_check is not None:
            if isinstance(self.convergence_check, str):
                if not self.convergence_check.strip():
                    errors.append(
                        "Convergence condition cannot be empty. "
                        "Examples: 'error < 0.01', 'quality > 0.9', 'count >= 10'"
                    )
                else:
                    # Validate expression safety
                    unsafe_patterns = [
                        "import ",
                        "exec(",
                        "eval(",
                        "__",
                        "open(",
                        "file(",
                    ]
                    for pattern in unsafe_patterns:
                        if pattern in self.convergence_check:
                            errors.append(
                                f"Convergence condition contains unsafe operation: '{pattern}'. "
                                "Use simple comparison expressions only."
                            )
            elif not callable(self.convergence_check):
                errors.append(
                    f"convergence_check must be string or callable, got {type(self.convergence_check)}"
                )

        # Validate timeout
        if self.timeout is not None:
            if not isinstance(self.timeout, (int, float)):
                errors.append(f"timeout must be numeric, got {type(self.timeout)}")
            elif self.timeout <= 0:
                errors.append(
                    f"timeout must be positive, got {self.timeout}. "
                    "Recommendation: Use 30-300 seconds for most cycles."
                )
            elif self.timeout > 3600:
                warnings.append(
                    f"timeout={self.timeout} seconds is very long (>1 hour). "
                    "Consider breaking into smaller cycles."
                )

        # Validate memory_limit
        if self.memory_limit is not None:
            if not isinstance(self.memory_limit, int):
                errors.append(
                    f"memory_limit must be an integer, got {type(self.memory_limit)}"
                )
            elif self.memory_limit <= 0:
                errors.append(
                    f"memory_limit must be positive, got {self.memory_limit}. "
                    "Recommendation: Use 100-1000 MB for most cycles."
                )
            elif self.memory_limit > 100000:  # 100GB
                warnings.append(
                    f"memory_limit={self.memory_limit} MB is very high. "
                    "Verify this is intentional for your use case."
                )

        # Validate iteration_safety_factor
        if not isinstance(self.iteration_safety_factor, (int, float)):
            errors.append(
                f"iteration_safety_factor must be numeric, got {type(self.iteration_safety_factor)}"
            )
        elif self.iteration_safety_factor < 1.0:
            errors.append(
                f"iteration_safety_factor must be >= 1.0, got {self.iteration_safety_factor}. "
                "This factor provides safety buffer for max_iterations."
            )
        elif self.iteration_safety_factor > 10.0:
            warnings.append(
                f"iteration_safety_factor={self.iteration_safety_factor} is very high. "
                "This may cause excessive iteration limits."
            )

        # Validate cycle_id
        if self.cycle_id is not None:
            if not isinstance(self.cycle_id, str) or not self.cycle_id.strip():
                errors.append("cycle_id must be a non-empty string")
            elif len(self.cycle_id) > 100:
                warnings.append(f"cycle_id='{self.cycle_id}' is very long (>100 chars)")

        # Validate parent_cycle
        if self.parent_cycle is not None:
            if not isinstance(self.parent_cycle, str) or not self.parent_cycle.strip():
                errors.append("parent_cycle must be a non-empty string")
            elif self.parent_cycle == self.cycle_id:
                errors.append("parent_cycle cannot be the same as cycle_id")

        # Validate condition
        if self.condition is not None:
            if not isinstance(self.condition, str) or not self.condition.strip():
                errors.append(
                    "condition must be a non-empty string expression. "
                    "Examples: 'retry_count < 3', 'needs_improvement == True'"
                )

        # Validate priority
        if not isinstance(self.priority, int):
            errors.append(f"priority must be an integer, got {type(self.priority)}")
        elif abs(self.priority) > 1000:
            warnings.append(f"priority={self.priority} is very high/low")

        # Log warnings
        for warning in warnings:
            logger.warning(f"CycleConfig validation warning: {warning}")

        # Raise errors if any found
        if errors:
            error_message = "CycleConfig validation failed:\n" + "\n".join(
                f"• {error}" for error in errors
            )
            raise CycleConfigurationError(
                error_message,
                error_code="CYCLE_CONFIG_001",
                suggestions=[
                    "Ensure at least one termination condition (max_iterations, convergence_check, or timeout)",
                    "Use positive values for numeric parameters",
                    "Avoid unsafe operations in convergence expressions",
                    "Check the CycleConfig documentation for valid parameter ranges",
                ],
            )

    def get_effective_max_iterations(self) -> int | None:
        """
        Get the effective maximum iterations with safety factor applied.

        Calculates the actual maximum iterations that will be used during
        cycle execution, including the safety factor multiplier to prevent
        runaway cycles even when convergence conditions fail.

        Returns:
            Optional[int]: Effective maximum iterations, or None if not configured

        Side Effects:
            None - this is a pure calculation method

        Example:
            >>> config = CycleConfig(max_iterations=100, iteration_safety_factor=1.5)
            >>> config.get_effective_max_iterations()
            150
        """
        if self.max_iterations is None:
            return None
        return int(self.max_iterations * self.iteration_safety_factor)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert configuration to dictionary format.

        Serializes the configuration to a dictionary suitable for JSON/YAML
        export, API transmission, or storage. Excludes None values and
        callable convergence checks for clean serialization.

        Returns:
            Dict[str, Any]: Dictionary representation of configuration

        Side Effects:
            None - this method is pure

        Example:
            >>> config = CycleConfig(max_iterations=100)
            >>> config.to_dict()
            {'max_iterations': 100, 'iteration_safety_factor': 1.5, ...}
        """
        result = {}

        for key, value in self.__dict__.items():
            if value is not None:
                # Skip callable convergence_check for serialization
                if key == "convergence_check" and callable(value):
                    result[key] = "<callable>"
                else:
                    result[key] = value

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CycleConfig":
        """
        Create configuration from dictionary data.

        Deserializes a configuration from dictionary format, typically
        loaded from JSON/YAML files or API requests. Handles missing
        fields gracefully with default values.

        Args:
            data (Dict[str, Any]): Dictionary containing configuration data

        Returns:
            CycleConfig: New configuration instance

        Raises:
            CycleConfigurationError: If data contains invalid values

        Side Effects:
            Validates the resulting configuration automatically

        Example:
            >>> data = {'max_iterations': 100, 'timeout': 60.0}
            >>> config = CycleConfig.from_dict(data)
        """
        # Filter out unknown fields
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in known_fields}

        try:
            return cls(**filtered_data)
        except Exception as e:
            raise CycleConfigurationError(
                f"Failed to create CycleConfig from data: {e}"
            ) from e

    def merge(self, other: "CycleConfig") -> "CycleConfig":
        """
        Merge this configuration with another, with other taking precedence.

        Creates a new configuration by merging two configurations, where
        non-None values from the other configuration override values in
        this configuration. Useful for applying templates and overlays.

        Args:
            other (CycleConfig): Configuration to merge with (takes precedence)

        Returns:
            CycleConfig: New merged configuration instance

        Raises:
            CycleConfigurationError: If merged configuration is invalid

        Side Effects:
            Validates the resulting merged configuration

        Example:
            >>> base = CycleConfig(max_iterations=100)
            >>> override = CycleConfig(timeout=60.0, cycle_id="custom")
            >>> merged = base.merge(override)
            >>> # Result has max_iterations=100, timeout=60.0, cycle_id="custom"
        """
        merged_data = {}

        # Start with this configuration
        for key, value in self.__dict__.items():
            if value is not None:
                merged_data[key] = value

        # Override with other configuration
        for key, value in other.__dict__.items():
            if value is not None:
                merged_data[key] = value

        return CycleConfig(**merged_data)

    def create_template(self, template_name: str) -> dict[str, Any]:
        """
        Create a reusable template from this configuration.

        Exports the configuration as a named template that can be stored,
        shared, and reused across multiple workflows. Templates include
        metadata about their intended use case and recommended parameters.

        Args:
            template_name (str): Name for the template

        Returns:
            Dict[str, Any]: Template data including metadata

        Side Effects:
            None - this method is pure

        Example:
            >>> config = CycleConfig(max_iterations=50, convergence_check="quality > 0.9")
            >>> template = config.create_template("quality_optimization")
        """
        template_data = {
            "template_name": template_name,
            "description": self.description or f"Cycle template: {template_name}",
            "created_from": "CycleConfig.create_template()",
            "configuration": self.to_dict(),
            "usage_notes": {
                "max_iterations": "Adjust based on expected convergence time",
                "convergence_check": "Modify condition for your specific metrics",
                "timeout": "Set based on acceptable execution time",
            },
        }

        return template_data

    def __repr__(self) -> str:
        """
        Return string representation of the configuration.

        Returns:
            str: Human-readable representation showing key configuration values

        Example:
            >>> config = CycleConfig(max_iterations=100, timeout=60.0)
            >>> str(config)
            'CycleConfig(max_iterations=100, timeout=60.0, cycle_id=None)'
        """
        key_params = []

        if self.max_iterations is not None:
            key_params.append(f"max_iterations={self.max_iterations}")
        if self.convergence_check is not None:
            conv_str = (
                self.convergence_check
                if isinstance(self.convergence_check, str)
                else "<callable>"
            )
            key_params.append(f"convergence_check='{conv_str}'")
        if self.timeout is not None:
            key_params.append(f"timeout={self.timeout}")
        if self.cycle_id is not None:
            key_params.append(f"cycle_id='{self.cycle_id}'")

        return f"CycleConfig({', '.join(key_params)})"


# Pre-defined configuration templates for common use cases
class CycleTemplates:
    """
    Pre-defined cycle configuration templates for common patterns.

    This class provides factory methods for creating CycleConfig instances
    optimized for specific use cases, reducing boilerplate and ensuring
    best practices are followed for common cycle patterns.

    Design Philosophy:
        Provides curated, tested configurations for common cycle patterns
        to reduce setup time and ensure optimal performance. Templates
        can be customized after creation for specific requirements.

    Example:
        >>> # Quick optimization cycle
        >>> config = CycleTemplates.optimization_loop(max_iterations=50)

        >>> # Retry logic with exponential backoff
        >>> config = CycleTemplates.retry_cycle(max_retries=3)
    """

    @staticmethod
    def optimization_loop(
        max_iterations: int = 100,
        convergence_threshold: float = 0.01,
        timeout: float | None = None,
    ) -> CycleConfig:
        """
        Create configuration for optimization cycles.

        Optimized for iterative improvement algorithms like gradient descent,
        quality improvement, or parameter tuning. Focuses on convergence
        detection with reasonable iteration limits.

        Args:
            max_iterations (int): Maximum optimization iterations
            convergence_threshold (float): Convergence threshold for stopping
            timeout (Optional[float]): Optional timeout in seconds

        Returns:
            CycleConfig: Configured for optimization patterns

        Example:
            >>> config = CycleTemplates.optimization_loop(max_iterations=200)
            >>> workflow.connect("optimizer", "evaluator", cycle_config=config)
        """
        return CycleConfig(
            max_iterations=max_iterations,
            convergence_check=f"improvement < {convergence_threshold}",
            timeout=timeout,
            cycle_id="optimization_loop",
            description="Iterative optimization cycle with convergence detection",
            iteration_safety_factor=2.0,  # Higher safety for optimization
        )

    @staticmethod
    def retry_cycle(
        max_retries: int = 3, timeout_per_retry: float = 30.0
    ) -> CycleConfig:
        """
        Create configuration for retry logic patterns.

        Optimized for error recovery, API retry logic, and fault-tolerant
        operations. Includes reasonable timeout per attempt and limited
        retry counts to prevent indefinite hanging.

        Args:
            max_retries (int): Maximum number of retry attempts
            timeout_per_retry (float): Timeout per individual retry

        Returns:
            CycleConfig: Configured for retry patterns

        Example:
            >>> config = CycleTemplates.retry_cycle(max_retries=5)
            >>> workflow.connect("api_call", "error_handler", cycle_config=config)
        """
        return CycleConfig(
            max_iterations=max_retries,
            timeout=timeout_per_retry * max_retries,
            cycle_id="retry_cycle",
            description="Retry cycle with exponential backoff support",
            condition="error_occurred == True",
            iteration_safety_factor=1.2,  # Conservative safety for retries
        )

    @staticmethod
    def data_quality_cycle(
        quality_threshold: float = 0.95, max_iterations: int = 10
    ) -> CycleConfig:
        """
        Create configuration for data quality improvement cycles.

        Optimized for iterative data cleaning, validation, and quality
        enhancement workflows. Focuses on quality metrics and reasonable
        iteration limits for data processing.

        Args:
            quality_threshold (float): Quality threshold for stopping (0.0-1.0)
            max_iterations (int): Maximum cleaning iterations

        Returns:
            CycleConfig: Configured for data quality patterns

        Example:
            >>> config = CycleTemplates.data_quality_cycle(quality_threshold=0.98)
            >>> workflow.connect("cleaner", "validator", cycle_config=config)
        """
        return CycleConfig(
            max_iterations=max_iterations,
            convergence_check=f"quality >= {quality_threshold}",
            timeout=300.0,  # 5 minutes for data processing
            cycle_id="data_quality_cycle",
            description="Data quality improvement cycle with quality metrics",
            memory_limit=2048,  # 2GB for data processing
        )

    @staticmethod
    def training_loop(
        max_epochs: int = 100, early_stopping_patience: int = 10
    ) -> CycleConfig:
        """
        Create configuration for machine learning training cycles.

        Optimized for ML model training with early stopping, validation
        monitoring, and resource management. Includes higher memory limits
        and longer timeouts typical for training workflows.

        Args:
            max_epochs (int): Maximum training epochs
            early_stopping_patience (int): Epochs to wait for improvement

        Returns:
            CycleConfig: Configured for ML training patterns

        Example:
            >>> config = CycleTemplates.training_loop(max_epochs=200)
            >>> workflow.connect("trainer", "evaluator", cycle_config=config)
        """
        return CycleConfig(
            max_iterations=max_epochs,
            convergence_check=f"epochs_without_improvement >= {early_stopping_patience}",
            timeout=3600.0,  # 1 hour for training
            cycle_id="training_loop",
            description="ML training cycle with early stopping",
            memory_limit=8192,  # 8GB for ML training
            iteration_safety_factor=1.1,  # Conservative for long training
        )
