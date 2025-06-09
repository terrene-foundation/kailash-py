"""
Template: Custom Node Creation
Purpose: Template for creating your own custom node
Use Case: When built-in nodes don't meet your specific requirements

Customization Points:
- Node class name and description
- get_parameters(): Define your node's configuration
- run(): Implement your node's logic
- get_output_schema(): Define output validation (optional)
"""

import logging
from typing import Any, Dict, List, Optional

from kailash.nodes.base import Node

# Set up logging for your node
logger = logging.getLogger(__name__)


class MyCustomNode(Node):
    """
    A custom node that performs specific business logic.

    This node demonstrates:
    - Parameter definition with types and defaults
    - Input validation
    - Error handling
    - Output schema validation
    - Logging best practices
    """

    def get_parameters(self) -> Dict[str, Any]:
        """
        Define the parameters your node accepts.

        Returns:
            Dictionary of parameter definitions with:
            - type: Python type (str, int, float, bool, list, dict)
            - required: Whether the parameter is mandatory
            - default: Default value if not provided
            - description: Human-readable description
            - enum: List of allowed values (optional)
            - min/max: Numeric bounds (optional)
        """
        return {
            # Required parameters
            "operation": {
                "type": str,
                "required": True,
                "description": "Operation to perform",
                "enum": ["transform", "filter", "aggregate"],
            },
            # Optional parameters with defaults
            "threshold": {
                "type": float,
                "required": False,
                "default": 0.5,
                "description": "Threshold value for filtering",
                "min": 0.0,
                "max": 1.0,
            },
            "case_sensitive": {
                "type": bool,
                "required": False,
                "default": True,
                "description": "Whether string operations are case-sensitive",
            },
            "fields": {
                "type": list,
                "required": False,
                "default": [],
                "description": "List of fields to process",
            },
            "options": {
                "type": dict,
                "required": False,
                "default": {},
                "description": "Additional options for processing",
            },
        }

    def validate_inputs(self, data: Any, **kwargs) -> None:
        """
        Validate inputs before processing.
        Raises ValueError if validation fails.
        """
        # Check data is not None
        if data is None:
            raise ValueError("Input data cannot be None")

        # Check data type
        if not isinstance(data, (list, dict)):
            raise ValueError(f"Expected list or dict, got {type(data).__name__}")

        # Validate based on operation
        operation = kwargs.get("operation")
        if operation == "filter" and "threshold" not in kwargs:
            raise ValueError("Filter operation requires threshold parameter")

        # Custom validation for your use case
        if isinstance(data, list) and len(data) == 0:
            logger.warning("Processing empty list")

    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        Execute the node's logic.

        Args:
            context: Workflow context containing data from connected nodes
            **kwargs: Parameters passed to the node

        Returns:
            Dictionary with output data
        """
        # Extract parameters
        operation = kwargs.get("operation")
        threshold = kwargs.get(
            "threshold", self.get_parameters()["threshold"]["default"]
        )
        case_sensitive = kwargs.get("case_sensitive", True)
        fields = kwargs.get("fields", [])
        options = kwargs.get("options", {})

        # Get input data from context
        data = context.get("data", context)

        # Validate inputs
        self.validate_inputs(data, **kwargs)

        # Log operation
        logger.info(f"Executing {operation} operation with threshold={threshold}")

        try:
            # Perform operation based on type
            if operation == "transform":
                result = self._transform_data(data, fields, case_sensitive, options)
            elif operation == "filter":
                result = self._filter_data(data, threshold, fields, options)
            elif operation == "aggregate":
                result = self._aggregate_data(data, fields, options)
            else:
                raise ValueError(f"Unknown operation: {operation}")

            # Return results
            return {
                "data": result,
                "metadata": {
                    "operation": operation,
                    "records_processed": len(data) if isinstance(data, list) else 1,
                    "parameters_used": {
                        "threshold": threshold,
                        "case_sensitive": case_sensitive,
                        "fields": fields,
                    },
                },
            }

        except Exception as e:
            logger.error(f"Error in {operation} operation: {str(e)}")
            # Decide whether to raise or return error
            # Option 1: Raise to stop workflow
            raise

            # Option 2: Return error for graceful handling
            # return {
            #     "error": str(e),
            #     "error_type": type(e).__name__,
            #     "data": None
            # }

    def _transform_data(
        self, data: Any, fields: List[str], case_sensitive: bool, options: Dict
    ) -> Any:
        """Transform data according to options"""
        if isinstance(data, list):
            transformed = []
            for item in data:
                if isinstance(item, dict):
                    new_item = item.copy()
                    # Example transformation: uppercase specified fields
                    for field in fields:
                        if field in new_item and isinstance(new_item[field], str):
                            new_item[field] = (
                                new_item[field].upper()
                                if not case_sensitive
                                else new_item[field]
                            )
                    transformed.append(new_item)
                else:
                    transformed.append(item)
            return transformed
        elif isinstance(data, dict):
            # Transform dictionary
            transformed = data.copy()
            for field in fields:
                if field in transformed and isinstance(transformed[field], str):
                    transformed[field] = (
                        transformed[field].upper()
                        if not case_sensitive
                        else transformed[field]
                    )
            return transformed
        else:
            return data

    def _filter_data(
        self, data: Any, threshold: float, fields: List[str], options: Dict
    ) -> Any:
        """Filter data based on threshold"""
        if isinstance(data, list):
            filtered = []
            for item in data:
                if isinstance(item, dict):
                    # Example: filter based on numeric field value
                    if fields:
                        # Check specified fields
                        for field in fields:
                            if field in item:
                                try:
                                    value = float(item[field])
                                    if value >= threshold:
                                        filtered.append(item)
                                        break
                                except (ValueError, TypeError):
                                    continue
                    else:
                        # Check any numeric field
                        for key, value in item.items():
                            try:
                                if float(value) >= threshold:
                                    filtered.append(item)
                                    break
                            except (ValueError, TypeError):
                                continue
                else:
                    # For non-dict items, include all
                    filtered.append(item)
            return filtered
        else:
            # For non-list data, return as-is
            return data

    def _aggregate_data(
        self, data: Any, fields: List[str], options: Dict
    ) -> Dict[str, Any]:
        """Aggregate data to produce summary statistics"""
        if isinstance(data, list):
            aggregated = {"count": len(data), "field_stats": {}}

            # Calculate stats for specified fields
            for field in fields:
                values = []
                for item in data:
                    if isinstance(item, dict) and field in item:
                        try:
                            values.append(float(item[field]))
                        except (ValueError, TypeError):
                            continue

                if values:
                    aggregated["field_stats"][field] = {
                        "count": len(values),
                        "sum": sum(values),
                        "avg": sum(values) / len(values),
                        "min": min(values),
                        "max": max(values),
                    }

            return aggregated
        else:
            # For non-list data, return basic info
            return {"count": 1, "data_type": type(data).__name__}

    def get_output_schema(self) -> Optional[Dict[str, Any]]:
        """
        Define the expected output schema for validation.

        Returns:
            JSON Schema dictionary or None if no validation needed
        """
        return {
            "type": "object",
            "properties": {
                "data": {
                    "description": "Processed data",
                    "oneOf": [{"type": "array"}, {"type": "object"}],
                },
                "metadata": {
                    "type": "object",
                    "properties": {
                        "operation": {"type": "string"},
                        "records_processed": {"type": "integer", "minimum": 0},
                        "parameters_used": {"type": "object"},
                    },
                    "required": ["operation", "records_processed"],
                },
            },
            "required": ["data", "metadata"],
        }


# Example usage in a workflow
if __name__ == "__main__":
    from kailash.runtime.local import LocalRuntime
    from kailash.workflow import Workflow

    # Create workflow
    workflow = Workflow()

    # Add custom node
    custom_node = MyCustomNode(
        config={"operation": "filter", "threshold": 0.7, "fields": ["score", "rating"]}
    )
    workflow.add_node("processor", custom_node)

    # Execute with sample data
    runtime = LocalRuntime()
    sample_data = [
        {"name": "Item1", "score": 0.8, "rating": 0.9},
        {"name": "Item2", "score": 0.6, "rating": 0.7},
        {"name": "Item3", "score": 0.9, "rating": 0.5},
    ]

    results = runtime.execute(workflow, parameters={"processor": {"data": sample_data}})

    print("Results:", results)
