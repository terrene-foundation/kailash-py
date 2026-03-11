"""
Structured Output Support - JSON Schema Generation from Signatures

Generates JSON schemas for reliable LLM outputs with OpenAI Structured Outputs API support.

Features:
- Automatic schema generation from Kaizen signatures
- OpenAI Structured Outputs API integration (strict mode)
- Legacy json_object format support
- 100% format compliance with strict mode (gpt-4o-2024-08-06+)
- Output validation against schema
- No regex parsing needed

Usage with BaseAgent:
    >>> from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
    >>> from kaizen.signatures import Signature, InputField, OutputField
    >>> from kaizen.core.structured_output import create_structured_output_config
    >>>
    >>> class QASignature(Signature):
    ...     question: str = InputField(desc="User question")
    ...     answer: str = OutputField(desc="Answer")
    ...     confidence: float = OutputField(desc="Confidence 0-1")
    >>>
    >>> # Create structured output config
    >>> response_format = create_structured_output_config(QASignature(), strict=True)
    >>>
    >>> # Pass to BaseAgent via generation_config
    >>> config = BaseAgentConfig(
    ...     llm_provider="openai",
    ...     model="gpt-4o-2024-08-06",  # Required for strict mode
    ...     generation_config={"response_format": response_format}
    ... )
    >>> agent = BaseAgent(config=config, signature=QASignature())
    >>> result = agent.run(question="What is AI?")  # 100% schema compliance!

Supported Models (strict=True):
- gpt-4o-2024-08-06 and later
- gpt-4o-mini-2024-07-18 and later

Legacy Models (strict=False):
- All OpenAI models (best-effort compliance ~70-85%)
"""

import json
import logging
from typing import Any, Dict, List, Literal, Type, get_args, get_origin

from kaizen.core.type_introspector import TypeIntrospector

logger = logging.getLogger(__name__)


class StructuredOutputGenerator:
    """
    Generates JSON schemas from Kaizen signatures.

    Supports OpenAI's structured output format for reliable JSON responses.
    """

    @staticmethod
    def signature_to_json_schema(signature: Any) -> Dict[str, Any]:
        """
        Convert signature to JSON schema.

        Args:
            signature: Kaizen Signature instance

        Returns:
            Dict: JSON schema for structured output

        Example:
            >>> schema = StructuredOutputGenerator.signature_to_json_schema(qa_signature)
            >>> # Use with OpenAI: model='gpt-4-turbo-preview', response_format={"type": "json_object", "schema": schema}
        """
        schema = {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        }

        # Extract output fields from signature
        if hasattr(signature, "output_fields"):
            for field_name, field_info in signature.output_fields.items():
                field_type = field_info.get("type", str)
                # Support both 'desc' parameter and 'description' in metadata
                field_desc = field_info.get("desc", "") or field_info.get(
                    "metadata", {}
                ).get("description", "")

                # Use TypeIntrospector for comprehensive type-to-schema conversion
                # This supports: Literal, Union, Optional, List[T], Dict[K,V], TypedDict, and basic types
                field_schema = TypeIntrospector.type_to_json_schema(
                    field_type, field_desc
                )

                # Extract validation constraints from metadata (if present)
                # Note: metadata is double-nested as metadata.metadata.validation
                metadata = field_info.get("metadata", {}).get("metadata", {})
                validation = metadata.get("validation", {})

                # Add validation constraints if present
                if "enum" in validation and "enum" not in field_schema:
                    # Don't override Literal-based enums
                    field_schema["enum"] = validation["enum"]

                # Add numeric constraints if present
                if "min" in validation:
                    field_schema["minimum"] = validation["min"]
                if "max" in validation:
                    field_schema["maximum"] = validation["max"]

                # Add pattern constraint if present
                if "pattern" in validation:
                    field_schema["pattern"] = validation["pattern"]

                schema["properties"][field_name] = field_schema

                # All output fields are required
                schema["required"].append(field_name)

        return schema

    @staticmethod
    def _python_type_to_json_type(python_type: Type) -> str:
        """Map Python type to JSON schema type."""
        type_mapping = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
        }

        return type_mapping.get(python_type, "string")

    @staticmethod
    def generate_system_prompt_with_schema(signature: Any) -> str:
        """
        Generate system prompt with embedded JSON schema.

        Args:
            signature: Kaizen Signature instance

        Returns:
            str: System prompt with schema instructions

        Example:
            >>> prompt = StructuredOutputGenerator.generate_system_prompt_with_schema(signature)
        """
        prompt_parts = []

        # Add signature description
        if hasattr(signature, "description") and signature.description:
            prompt_parts.append(signature.description)
        elif hasattr(signature, "name") and signature.name:
            prompt_parts.append(f"Task: {signature.name}")

        # Add input field descriptions
        if hasattr(signature, "input_fields") and signature.input_fields:
            prompt_parts.append("\nExpected Inputs:")
            for field_name, field_info in signature.input_fields.items():
                if isinstance(field_info, dict):
                    # Support both 'desc' parameter and 'description' in metadata
                    field_desc = field_info.get("desc", "") or field_info.get(
                        "metadata", {}
                    ).get("description", "")
                    if field_desc:
                        prompt_parts.append(f"  - {field_name}: {field_desc}")

        # Add output field descriptions with types
        if hasattr(signature, "output_fields") and signature.output_fields:
            prompt_parts.append("\nRequired Outputs:")
            for field_name, field_info in signature.output_fields.items():
                if isinstance(field_info, dict):
                    field_type = field_info.get("type", str).__name__
                    # Support both 'desc' parameter and 'description' in metadata
                    field_desc = field_info.get("desc", "") or field_info.get(
                        "metadata", {}
                    ).get("description", "")
                    prompt_parts.append(
                        f"  - {field_name} ({field_type}): {field_desc}"
                    )

        # Add JSON schema
        schema = StructuredOutputGenerator.signature_to_json_schema(signature)
        prompt_parts.append("\n---")
        prompt_parts.append(
            "\nYou MUST respond with a valid JSON object matching this exact schema:"
        )
        prompt_parts.append(f"```json\n{json.dumps(schema, indent=2)}\n```")
        prompt_parts.append("\nDo NOT include any text outside the JSON object.")
        prompt_parts.append(
            "Ensure all required fields are present with correct types."
        )

        return "\n".join(prompt_parts)

    @staticmethod
    def validate_output(
        output: Dict[str, Any], signature: Any
    ) -> tuple[bool, List[str]]:
        """
        Validate output against signature schema.

        Supports all Python type annotations including Literal, Union, Optional,
        List[T], Dict[K,V], TypedDict, and basic types.

        Args:
            output: LLM output to validate
            signature: Kaizen Signature instance

        Returns:
            tuple: (is_valid, list of errors)

        Example:
            >>> is_valid, errors = StructuredOutputGenerator.validate_output(result, signature)
            >>> if not is_valid:
            ...     print(f"Validation errors: {errors}")
        """
        errors = []

        if not hasattr(signature, "output_fields"):
            return True, []

        # Check all required fields present and validate types
        for field_name, field_info in signature.output_fields.items():
            if field_name not in output:
                errors.append(f"Missing required field: {field_name}")
                continue

            # Get expected type and actual value
            expected_type = field_info.get("type", str)
            actual_value = output[field_name]

            # Use TypeIntrospector for comprehensive type validation
            # This handles Literal, Union, Optional, List[T], Dict[K,V], TypedDict, etc.
            is_valid, error_msg = TypeIntrospector.validate_value_against_type(
                actual_value, expected_type
            )

            if not is_valid:
                errors.append(f"{field_name}: {error_msg}")

        return len(errors) == 0, errors


def _make_all_properties_required(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Post-process JSON schema to make all properties required.

    OpenAI strict mode requires ALL properties to be in the 'required' array.
    This function recursively processes the schema to ensure compliance.

    Args:
        schema: JSON schema dictionary

    Returns:
        Modified schema with all properties required
    """
    if not isinstance(schema, dict):
        return schema

    # Create a copy to avoid modifying the original
    schema = schema.copy()

    # If this object has properties, make them all required
    if "properties" in schema and isinstance(schema["properties"], dict):
        property_names = list(schema["properties"].keys())
        if property_names:
            schema["required"] = property_names

        # Recursively process nested objects
        for prop_name, prop_schema in schema["properties"].items():
            schema["properties"][prop_name] = _make_all_properties_required(prop_schema)

    # Handle array items
    if "items" in schema:
        schema["items"] = _make_all_properties_required(schema["items"])

    # Handle allOf, anyOf, oneOf
    for key in ["allOf", "anyOf", "oneOf"]:
        if key in schema and isinstance(schema[key], list):
            schema[key] = [_make_all_properties_required(s) for s in schema[key]]

    return schema


# Convenience function
def create_structured_output_config(
    signature: Any,
    strict: bool = True,
    name: str = "response",
    auto_fallback: bool = True,
) -> Dict[str, Any]:
    """
    Create OpenAI-compatible structured output configuration.

    Supports both OpenAI Structured Outputs formats:
    - New format (strict=True): 100% reliability with gpt-4o-2024-08-06+
    - Legacy format (strict=False): Best-effort with older models

    Intelligent strict mode validation:
    - Checks if signature types are compatible with OpenAI strict mode
    - Auto-falls back to strict=False if incompatible types detected (when auto_fallback=True)
    - Provides clear error messages explaining incompatibilities

    Args:
        signature: Kaizen Signature instance
        strict: Use strict mode (new format) for 100% reliability.
                Requires gpt-4o-2024-08-06 or gpt-4o-mini-2024-07-18+.
                Default: True
        name: Schema name for strict mode. Default: "response"
        auto_fallback: Automatically fall back to strict=False if types are incompatible.
                       If False, raises ValueError on incompatibility.
                       Default: True

    Returns:
        Dict: Config for OpenAI API response_format parameter

    Raises:
        ValueError: If strict=True but signature has incompatible types and auto_fallback=False

    Example (Strict Mode - Recommended):
        >>> config = create_structured_output_config(qa_signature, strict=True)
        >>> # Use with: model="gpt-4o-2024-08-06", response_format=config
        >>> # Guaranteed 100% schema compliance

    Example (Legacy Mode):
        >>> config = create_structured_output_config(qa_signature, strict=False)
        >>> # Use with any model, best-effort schema compliance (~70-85%)

    Example (Auto-Fallback):
        >>> # Signature with Dict[str, Any] (incompatible with strict mode)
        >>> config = create_structured_output_config(flex_signature, strict=True, auto_fallback=True)
        >>> # Automatically uses strict=False, logs warning
    """
    # Validate strict mode compatibility
    if strict and hasattr(signature, "output_fields"):
        incompatible_fields = []

        for field_name, field_info in signature.output_fields.items():
            field_type = field_info.get("type", str)
            compatible, reason = TypeIntrospector.is_strict_mode_compatible(field_type)

            if not compatible:
                incompatible_fields.append((field_name, field_type, reason))

        # Handle incompatibilities
        if incompatible_fields:
            error_messages = []
            for field_name, field_type, reason in incompatible_fields:
                type_name = (
                    field_type.__name__
                    if hasattr(field_type, "__name__")
                    else str(field_type)
                )
                error_messages.append(
                    f"  - Field '{field_name}' ({type_name}): {reason}"
                )

            full_error = (
                "OpenAI strict mode incompatibility detected:\n"
                + "\n".join(error_messages)
                + "\n\nRecommendations:"
                + "\n  1. Use strict=False for flexible schemas (70-85% compliance)"
                + "\n  2. Replace Dict[str, Any] with List[str] or TypedDict"
                + "\n  3. Replace Union types with separate Optional fields"
            )

            if auto_fallback:
                # Auto-fallback to strict=False
                logger.warning(
                    f"{full_error}\n\nAuto-falling back to strict=False mode."
                )
                strict = False
            else:
                # Raise error
                raise ValueError(full_error)

    schema = StructuredOutputGenerator.signature_to_json_schema(signature)

    if strict:
        # Post-process schema to make all properties required (handles NotRequired fields)
        schema = _make_all_properties_required(schema)

        # New OpenAI Structured Outputs format (gpt-4o-2024-08-06+)
        # Provides 100% reliability via constrained sampling
        return {
            "type": "json_schema",
            "json_schema": {"name": name, "strict": True, "schema": schema},
        }
    else:
        # Legacy format (prompt-based, best-effort)
        # OpenAI expects only {"type": "json_object"} without schema key
        return {"type": "json_object"}
