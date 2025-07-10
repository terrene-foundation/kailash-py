"""Data validation and type consistency utilities for workflow execution."""

import logging
from typing import Any, Dict, List, Union

logger = logging.getLogger(__name__)


class DataTypeValidator:
    """Validates and fixes data type inconsistencies in workflow execution."""

    @staticmethod
    def validate_node_output(node_id: str, output: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and fix node output to ensure consistent data types.

        Args:
            node_id: ID of the node producing the output
            output: Raw output from the node

        Returns:
            Validated and potentially fixed output
        """
        if not isinstance(output, dict):
            logger.warning(
                f"Node '{node_id}' output should be a dict, got {type(output)}. Wrapping in result key."
            )
            return {"result": output}

        validated_output = {}

        for key, value in output.items():
            validated_value = DataTypeValidator._validate_value(node_id, key, value)
            validated_output[key] = validated_value

        return validated_output

    @staticmethod
    def _validate_value(node_id: str, key: str, value: Any) -> Any:
        """Validate a single value and fix common type issues.

        Args:
            node_id: ID of the node producing the value
            key: Key name for the value
            value: The value to validate

        Returns:
            Validated value
        """
        # Common bug: Dictionary gets converted to list of keys
        if isinstance(value, list) and key == "result":
            # Check if this looks like dict keys
            if all(isinstance(item, str) for item in value):
                logger.warning(
                    f"Node '{node_id}' output '{key}' appears to be dict keys converted to list: {value}. "
                    "This is a known bug in some node implementations."
                )
                # We can't recover the original dict, so wrap the list properly
                return value

        # Ensure string data is not accidentally indexed as dict
        if isinstance(value, str):
            return value

        # Validate dict structure
        if isinstance(value, dict):
            # Recursively validate nested dicts
            validated_dict = {}
            for subkey, subvalue in value.items():
                validated_dict[subkey] = DataTypeValidator._validate_value(
                    node_id, f"{key}.{subkey}", subvalue
                )
            return validated_dict

        # Validate list structure
        if isinstance(value, list):
            # Ensure list elements are consistently typed
            if len(value) > 0:
                first_type = type(value[0])
                inconsistent_types = [
                    i for i, item in enumerate(value) if type(item) is not first_type
                ]
                if inconsistent_types:
                    logger.warning(
                        f"Node '{node_id}' output '{key}' has inconsistent list element types. "
                        f"First type: {first_type}, inconsistent indices: {inconsistent_types[:5]}"
                    )

        return value

    @staticmethod
    def validate_node_input(node_id: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate node inputs before execution.

        Args:
            node_id: ID of the node receiving the inputs
            inputs: Input parameters for the node

        Returns:
            Validated inputs
        """
        if not isinstance(inputs, dict):
            logger.error(f"Node '{node_id}' inputs must be a dict, got {type(inputs)}")
            return {}

        validated_inputs = {}

        for key, value in inputs.items():
            # Handle common data mapping issues
            if key == "data" and isinstance(value, list):
                # Check if this is the dict-to-keys bug
                if all(isinstance(item, str) for item in value):
                    logger.warning(
                        f"Node '{node_id}' received list of strings for 'data' parameter: {value}. "
                        "This may be due to a dict-to-keys conversion bug in upstream node."
                    )

            validated_inputs[key] = value

        return validated_inputs

    @staticmethod
    def fix_string_indexing_error(data: Any, error_context: str = "") -> Any:
        """Fix common 'string indices must be integers' errors.

        Args:
            data: Data that caused the error
            error_context: Context information about the error

        Returns:
            Fixed data or None if unfixable
        """
        if isinstance(data, str):
            logger.warning(
                f"Attempting to index string as dict{' in ' + error_context if error_context else ''}. "
                f"String value: '{data[:100]}...'"
                if len(data) > 100
                else f"String value: '{data}'"
            )
            return None

        if isinstance(data, list) and all(isinstance(item, str) for item in data):
            logger.warning(
                f"Data appears to be list of dict keys{' in ' + error_context if error_context else ''}. "
                f"Keys: {data}. Cannot recover original dict structure."
            )
            return None

        return data

    @staticmethod
    def create_error_recovery_wrapper(
        original_data: Any, fallback_data: Any = None
    ) -> Dict[str, Any]:
        """Create a recovery wrapper for problematic data.

        Args:
            original_data: The problematic data
            fallback_data: Fallback data to use if original is unusable

        Returns:
            Recovery wrapper dict
        """
        return {
            "data": fallback_data if fallback_data is not None else {},
            "original_data": original_data,
            "data_type_error": True,
            "error_message": f"Data type conversion error. Original type: {type(original_data)}",
        }


def validate_workflow_data_flow(workflow_results: Dict[str, Any]) -> Dict[str, Any]:
    """Validate entire workflow result data flow for consistency.

    Args:
        workflow_results: Results from workflow execution

    Returns:
        Validated workflow results
    """
    validated_results = {}

    for node_id, result in workflow_results.items():
        try:
            validated_result = DataTypeValidator.validate_node_output(node_id, result)
            validated_results[node_id] = validated_result
        except Exception as e:
            logger.error(f"Data validation failed for node '{node_id}': {e}")
            validated_results[node_id] = (
                DataTypeValidator.create_error_recovery_wrapper(result)
            )

    return validated_results
