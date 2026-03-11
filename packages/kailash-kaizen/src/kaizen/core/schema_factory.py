"""
Schema Factory for Provider-Compatible Schema Generation.

This module provides automatic schema adaptation based on provider constraints,
particularly for OpenAI Structured Outputs API strict mode compatibility.

The main challenge:
- OpenAI strict mode requires ALL properties to be in the 'required' array
- Python TypedDict with NotRequired fields are incompatible with this
- Solution: Factory pattern that adapts schemas based on provider

Author: Kailash Kaizen Team
Version: 0.6.4
"""

import logging
import re
from typing import Any, Dict, Type, TypedDict, get_args, get_origin, get_type_hints

from kaizen.core.config import BaseAgentConfig
from typing_extensions import NotRequired

logger = logging.getLogger(__name__)


class SchemaFactory:
    """
    Factory for generating provider-compatible schemas.

    Automatically adapts schemas based on provider constraints:
    - OpenAI strict mode: All fields required (converts NotRequired → Required)
    - Other providers: Preserve NotRequired fields

    Example:
        ```python
        from kaizen.core.schema_factory import SchemaFactory
        from kaizen.core.config import BaseAgentConfig

        # Define base schema with optional fields
        class PlanStep(TypedDict):
            step: int
            action: str
            description: str
            tools: NotRequired[list]  # Optional
            dependencies: NotRequired[list]  # Optional

        # Adapt for OpenAI strict mode
        config = BaseAgentConfig(
            llm_provider="openai",
            provider_config={
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"strict": True}
                }
            }
        )

        adapted_schema = SchemaFactory.adapt_for_provider(PlanStep, config)
        # Result: All fields become required for OpenAI strict mode
        ```
    """

    @staticmethod
    def adapt_for_provider(
        base_schema: Type[TypedDict], config: BaseAgentConfig
    ) -> Type[TypedDict]:
        """
        Adapt schema for provider constraints.

        Args:
            base_schema: Base TypedDict class (may have NotRequired fields)
            config: Provider configuration

        Returns:
            Adapted TypedDict class:
            - For OpenAI strict mode: All fields required
            - For other providers: Original schema preserved

        Example:
            ```python
            adapted = SchemaFactory.adapt_for_provider(PlanStep, config)
            ```
        """
        # Check if OpenAI strict mode is enabled
        is_openai_strict = SchemaFactory._is_openai_strict_mode(config)

        if is_openai_strict:
            logger.debug(
                f"Adapting schema {base_schema.__name__} for OpenAI strict mode"
            )
            return SchemaFactory._make_all_required(base_schema)
        else:
            logger.debug(
                f"Preserving original schema {base_schema.__name__} (not OpenAI strict mode)"
            )
            return base_schema

    @staticmethod
    def _is_openai_strict_mode(config: BaseAgentConfig) -> bool:
        """
        Check if configuration uses OpenAI Structured Outputs API strict mode.

        Args:
            config: Provider configuration

        Returns:
            True if OpenAI strict mode is enabled, False otherwise
        """
        # Check provider
        if config.llm_provider != "openai":
            return False

        # Check provider_config for strict mode
        provider_config = config.provider_config or {}
        response_format = provider_config.get("response_format", {})

        # OpenAI strict mode format:
        # {"type": "json_schema", "json_schema": {"strict": True, ...}}
        if response_format.get("type") == "json_schema":
            json_schema = response_format.get("json_schema", {})
            return json_schema.get("strict") == True

        return False

    @staticmethod
    def _make_all_required(schema: Type[TypedDict]) -> Type[TypedDict]:
        """
        Convert all NotRequired fields to required fields.

        For OpenAI strict mode, all properties must be in the 'required' array.
        This method creates a new TypedDict with all fields required.

        Args:
            schema: Original TypedDict with NotRequired fields

        Returns:
            New TypedDict with all fields required

        Implementation:
            - Analyzes __annotations__ to find NotRequired fields
            - Creates new TypedDict with unwrapped types
            - For NotRequired[list] → list
            - For NotRequired[dict] → dict
            - For NotRequired[str] → str
        """
        # Get type hints (includes NotRequired annotations)
        hints = get_type_hints(schema, include_extras=True)

        # Build new annotations dict with unwrapped types
        new_annotations = {}
        for field_name, field_type in hints.items():
            # Check if this is NotRequired
            origin = get_origin(field_type)

            if origin is NotRequired:
                # Unwrap NotRequired[T] → T
                args = get_args(field_type)
                unwrapped_type = args[0] if args else field_type
                new_annotations[field_name] = unwrapped_type
                logger.debug(
                    f"  Unwrapped {field_name}: NotRequired[{unwrapped_type}] → {unwrapped_type}"
                )
            else:
                # Keep as-is (already required)
                new_annotations[field_name] = field_type

        # Create new TypedDict class with all required fields using functional form
        # TypedDict('ClassName', {'field1': type1, 'field2': type2, ...})
        new_schema_name = f"{schema.__name__}Strict"
        new_schema = TypedDict(new_schema_name, new_annotations)

        logger.debug(
            f"Created strict schema: {new_schema_name} with {len(new_annotations)} required fields"
        )

        return new_schema

    @staticmethod
    def get_empty_default(field_type: Type) -> Any:
        """
        Get appropriate empty default value for a field type.

        Used when converting NotRequired fields to required fields
        to provide sensible defaults in prompts.

        Args:
            field_type: The field's type

        Returns:
            Appropriate empty default:
            - list → []
            - dict → {}
            - str → ""
            - int → 0
            - float → 0.0
            - bool → False

        Example:
            ```python
            default = SchemaFactory.get_empty_default(list)  # Returns []
            ```
        """
        origin = get_origin(field_type)

        # Handle generic types (List[T], Dict[K,V], etc.)
        if origin is list:
            return []
        elif origin is dict:
            return {}

        # Handle simple types
        if field_type == list:
            return []
        elif field_type == dict:
            return {}
        elif field_type == str:
            return ""
        elif field_type == int:
            return 0
        elif field_type == float:
            return 0.0
        elif field_type == bool:
            return False
        else:
            # Default to None for unknown types
            return None
