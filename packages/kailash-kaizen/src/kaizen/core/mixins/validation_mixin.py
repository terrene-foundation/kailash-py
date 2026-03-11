"""
Validation Mixin for BaseAgent.

Provides input/output validation for agent operations including:
- Input validation against signature fields
- Output validation against signature fields
- Type checking with helpful error messages
- Required field enforcement
"""

import functools
import inspect
import logging
from typing import TYPE_CHECKING, Any, Dict, Optional, Set, get_args, get_origin

if TYPE_CHECKING:
    from kaizen.core.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when validation fails."""

    pass


class ValidationMixin:
    """
    Mixin that adds input/output validation to agents.

    Validates agent inputs and outputs against their signature:
    - Required input fields must be present
    - Input types must match signature field types
    - Output fields are validated for type correctness
    - Helpful error messages for validation failures

    Example:
        config = BaseAgentConfig(validation_enabled=True)
        agent = SimpleQAAgent(config)
        # If required 'question' field is missing, ValidationError is raised
        result = await agent.run()  # Raises ValidationError
    """

    @classmethod
    def apply(cls, agent: "BaseAgent") -> None:
        """
        Apply validation behavior to agent.

        Args:
            agent: The agent instance to apply validation to
        """
        agent._validation_enabled = True

        # Store original run method
        original_run = agent.run
        is_async = inspect.iscoroutinefunction(original_run)
        agent_name = agent.__class__.__name__

        def _validate_and_log_inputs(kwargs: Dict[str, Any]) -> None:
            """Validate inputs and log errors."""
            try:
                cls._validate_inputs(agent, kwargs)
            except ValidationError as e:
                logger.error(
                    f"{agent_name}: Input validation failed: {e}",
                    extra={
                        "agent": agent_name,
                        "validation_type": "input",
                        "error": str(e),
                    },
                )
                raise

        def _validate_and_log_outputs(result: Dict[str, Any]) -> None:
            """Validate outputs and log errors."""
            try:
                cls._validate_outputs(agent, result)
            except ValidationError as e:
                logger.error(
                    f"{agent_name}: Output validation failed: {e}",
                    extra={
                        "agent": agent_name,
                        "validation_type": "output",
                        "error": str(e),
                    },
                )
                raise

        if is_async:

            @functools.wraps(original_run)
            async def validated_run_async(*args: Any, **kwargs: Any) -> Dict[str, Any]:
                """Wrapped async run method with validation."""
                _validate_and_log_inputs(kwargs)
                result = await original_run(*args, **kwargs)
                _validate_and_log_outputs(result)
                return result

            agent.run = validated_run_async
        else:

            @functools.wraps(original_run)
            def validated_run_sync(*args: Any, **kwargs: Any) -> Dict[str, Any]:
                """Wrapped sync run method with validation."""
                _validate_and_log_inputs(kwargs)
                result = original_run(*args, **kwargs)
                _validate_and_log_outputs(result)
                return result

            agent.run = validated_run_sync

    @classmethod
    def _validate_inputs(cls, agent: "BaseAgent", inputs: Dict[str, Any]) -> None:
        """
        Validate inputs against agent signature.

        Args:
            agent: The agent instance
            inputs: Input dictionary to validate

        Raises:
            ValidationError: If validation fails
        """
        signature = getattr(agent, "signature", None)
        if signature is None:
            return

        # Get input fields from signature
        input_fields = getattr(signature, "_input_fields", {})
        if not input_fields:
            return

        # Check required fields
        for field_name, field_def in input_fields.items():
            required = getattr(field_def, "required", True)
            default = getattr(field_def, "default", None)

            if required and default is None:
                if field_name not in inputs:
                    raise ValidationError(
                        f"Required input field '{field_name}' is missing"
                    )

            # Type check if value provided
            if field_name in inputs:
                expected_type = getattr(field_def, "type_", None)
                if expected_type is not None:
                    value = inputs[field_name]
                    if not cls._check_type(value, expected_type):
                        raise ValidationError(
                            f"Input field '{field_name}' has wrong type: "
                            f"expected {expected_type}, got {type(value).__name__}"
                        )

    @classmethod
    def _validate_outputs(cls, agent: "BaseAgent", outputs: Dict[str, Any]) -> None:
        """
        Validate outputs against agent signature.

        Args:
            agent: The agent instance
            outputs: Output dictionary to validate

        Raises:
            ValidationError: If validation fails
        """
        signature = getattr(agent, "signature", None)
        if signature is None:
            return

        # Get output fields from signature
        output_fields = getattr(signature, "_output_fields", {})
        if not output_fields:
            return

        if not isinstance(outputs, dict):
            raise ValidationError(f"Expected dict output, got {type(outputs).__name__}")

        # Check required output fields
        for field_name, field_def in output_fields.items():
            required = getattr(field_def, "required", True)

            if required and field_name not in outputs:
                raise ValidationError(
                    f"Required output field '{field_name}' is missing from result"
                )

    @classmethod
    def _check_type(cls, value: Any, expected_type: Any) -> bool:
        """
        Check if value matches expected type.

        Handles:
        - Basic types (str, int, float, bool)
        - Optional types
        - List/Dict types
        - Union types

        Args:
            value: Value to check
            expected_type: Expected type annotation

        Returns:
            True if type matches, False otherwise
        """
        if value is None:
            # None is allowed for Optional types
            origin = get_origin(expected_type)
            if origin is type(None):
                return True
            # Check if Optional (Union[X, None])
            args = get_args(expected_type)
            if type(None) in args:
                return True
            return False

        # Get origin type for generic types
        origin = get_origin(expected_type)
        if origin is not None:
            # Handle List, Dict, Optional, Union
            if origin is list:
                return isinstance(value, list)
            if origin is dict:
                return isinstance(value, dict)
            # Union type
            args = get_args(expected_type)
            if args:
                return any(cls._check_type(value, arg) for arg in args)
            return isinstance(value, origin)

        # Basic type check
        try:
            return isinstance(value, expected_type)
        except TypeError:
            # Some types don't support isinstance
            return True

    @classmethod
    def is_validation_enabled(cls, agent: "BaseAgent") -> bool:
        """
        Check if validation is enabled for agent.

        Args:
            agent: The agent instance

        Returns:
            True if validation is enabled
        """
        return getattr(agent, "_validation_enabled", False)
