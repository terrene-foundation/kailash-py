"""Transform nodes for data processing."""

import traceback
from typing import Any, Dict

from kailash.nodes.base import Node, NodeParameter, register_node


@register_node()
class Filter(Node):
    """Filters data based on a condition."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=False,  # Data comes from workflow connections
                description="Input data to filter",
            ),
            "field": NodeParameter(
                name="field",
                type=str,
                required=False,
                description="Field name for dict-based filtering",
            ),
            "operator": NodeParameter(
                name="operator",
                type=str,
                required=False,
                default="==",
                description="Comparison operator (==, !=, >, <, >=, <=, contains)",
            ),
            "value": NodeParameter(
                name="value",
                type=Any,
                required=False,
                description="Value to compare against",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        data = kwargs["data"]
        field = kwargs.get("field")
        operator = kwargs.get("operator", "==")
        value = kwargs.get("value")

        if not data:
            return {"filtered_data": []}

        filtered_data = []
        for item in data:
            if field and isinstance(item, dict):
                item_value = item.get(field)
            else:
                item_value = item

            if self._apply_operator(item_value, operator, value):
                filtered_data.append(item)

        return {"filtered_data": filtered_data}

    def _apply_operator(
        self, item_value: Any, operator: str, compare_value: Any
    ) -> bool:
        """Apply comparison operator."""
        try:
            # Handle None values - they fail most comparisons
            if item_value is None:
                if operator in ["==", "!="]:
                    return (operator == "==") == (compare_value is None)
                else:
                    return False  # None fails all other comparisons

            # For numeric operators, try to convert strings to numbers
            if operator in [">", "<", ">=", "<="]:
                try:
                    # Try to convert both values to float for comparison
                    if isinstance(item_value, str):
                        item_value = float(item_value)
                    if isinstance(compare_value, str):
                        compare_value = float(compare_value)
                except (ValueError, TypeError):
                    # If conversion fails, fall back to string comparison
                    pass

            if operator == "==":
                return item_value == compare_value
            elif operator == "!=":
                return item_value != compare_value
            elif operator == ">":
                return item_value > compare_value
            elif operator == "<":
                return item_value < compare_value
            elif operator == ">=":
                return item_value >= compare_value
            elif operator == "<=":
                return item_value <= compare_value
            elif operator == "contains":
                return compare_value in str(item_value)
            else:
                raise ValueError(f"Unknown operator: {operator}")
        except Exception:
            # If any comparison fails, return False (filter out the item)
            return False


@register_node()
class Map(Node):
    """Maps data using a transformation."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=False,  # Data comes from workflow connections
                description="Input data to transform",
            ),
            "field": NodeParameter(
                name="field",
                type=str,
                required=False,
                description="Field to extract from dict items",
            ),
            "new_field": NodeParameter(
                name="new_field",
                type=str,
                required=False,
                description="New field name for dict items",
            ),
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=False,
                default="identity",
                description="Operation to apply (identity, upper, lower, multiply, add)",
            ),
            "value": NodeParameter(
                name="value",
                type=Any,
                required=False,
                description="Value for operations that need it",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        data = kwargs["data"]
        field = kwargs.get("field")
        new_field = kwargs.get("new_field")
        operation = kwargs.get("operation", "identity")
        value = kwargs.get("value")

        mapped_data = []
        for item in data:
            if isinstance(item, dict):
                new_item = item.copy()
                if field:
                    item_value = item.get(field)
                    transformed = self._apply_operation(item_value, operation, value)
                    if new_field:
                        new_item[new_field] = transformed
                    else:
                        new_item[field] = transformed
                mapped_data.append(new_item)
            else:
                transformed = self._apply_operation(item, operation, value)
                mapped_data.append(transformed)

        return {"mapped_data": mapped_data}

    def _apply_operation(self, item_value: Any, operation: str, op_value: Any) -> Any:
        """Apply transformation operation."""
        if operation == "identity":
            return item_value
        elif operation == "upper":
            return str(item_value).upper()
        elif operation == "lower":
            return str(item_value).lower()
        elif operation == "multiply":
            return float(item_value) * float(op_value)
        elif operation == "add":
            if isinstance(item_value, str):
                return str(item_value) + str(op_value)
            return float(item_value) + float(op_value)
        else:
            raise ValueError(f"Unknown operation: {operation}")


@register_node()
class DataTransformer(Node):
    """
    Transforms data using custom transformation functions provided as strings.

    This node allows arbitrary data transformations by providing lambda functions
    or other Python code as strings. These are compiled and executed against the input data.
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=False,
                description="Primary input data to transform",
            ),
            "transformations": NodeParameter(
                name="transformations",
                type=list,
                required=True,
                description="List of transformation functions as strings",
            ),
            **{
                f"arg{i}": NodeParameter(
                    name=f"arg{i}",
                    type=Any,
                    required=False,
                    description=f"Additional argument {i}",
                )
                for i in range(1, 6)
            },  # Support for up to 5 additional arguments
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        # Extract the transformation functions
        transformations = kwargs.get("transformations", [])
        if not transformations:
            return {"result": kwargs.get("data", [])}

        # Get all input data
        input_data = {}
        for key, value in kwargs.items():
            if key != "transformations":
                input_data[key] = value

        # Execute the transformations
        result = input_data.get("data", [])

        for transform_str in transformations:
            try:
                # Create a safe globals dictionary with basic functions
                safe_globals = {
                    "len": len,
                    "sum": sum,
                    "min": min,
                    "max": max,
                    "dict": dict,
                    "list": list,
                    "set": set,
                    "str": str,
                    "int": int,
                    "float": float,
                    "bool": bool,
                    "sorted": sorted,
                }

                # For multi-line code blocks
                if "\n" in transform_str.strip():
                    # Prepare local context for execution
                    local_vars = input_data.copy()
                    local_vars["result"] = result

                    # Execute the code block
                    exec(transform_str, safe_globals, local_vars)  # noqa: S102

                    # Extract the result from local context
                    result = local_vars.get("result", result)

                # For single expressions or lambdas
                else:
                    # For lambda functions like: "lambda x: x * 2"
                    if transform_str.strip().startswith("lambda"):
                        # First, compile the lambda function
                        lambda_func = eval(transform_str, safe_globals)  # noqa: S307

                        # Apply the lambda function based on input data
                        if isinstance(result, list):
                            # If there are multiple arguments expected by the lambda
                            if (
                                "data" in input_data
                                and lambda_func.__code__.co_argcount > 1
                            ):
                                # For cases like "lambda tx, customers_dict: ..."
                                arg_names = lambda_func.__code__.co_varnames[
                                    : lambda_func.__code__.co_argcount
                                ]

                                # Apply the lambda to each item
                                new_result = []
                                for item in result:
                                    args = {}
                                    # First arg is the item itself
                                    args[arg_names[0]] = item
                                    # Other args come from input_data
                                    self.logger.debug(
                                        f"Lambda expected args: {arg_names}"
                                    )
                                    self.logger.debug(
                                        f"Available input data keys: {input_data.keys()}"
                                    )
                                    for i, arg_name in enumerate(arg_names[1:], 1):
                                        if arg_name in input_data:
                                            args[arg_name] = input_data[arg_name]
                                            self.logger.debug(
                                                f"Found {arg_name} in input_data"
                                            )
                                        else:
                                            self.logger.error(
                                                f"Missing required argument {arg_name} for lambda function"
                                            )

                                    # Apply function with the args
                                    transformed = lambda_func(**args)
                                    new_result.append(transformed)
                                result = new_result
                            else:
                                # Simple map operation: lambda x: x * 2
                                result = [lambda_func(item) for item in result]
                        else:
                            # Apply directly to a single value
                            result = lambda_func(result)

                    # For regular expressions like: "x * 2"
                    else:
                        local_vars = input_data.copy()
                        local_vars["result"] = result
                        result = eval(
                            transform_str, safe_globals, local_vars
                        )  # noqa: S307

            except Exception as e:
                tb = traceback.format_exc()
                self.logger.error(f"Error executing transformation: {e}")
                raise RuntimeError(
                    f"Error executing transformation '{transform_str}': {str(e)}\n{tb}"
                )

        return {"result": result}


@register_node()
class Sort(Node):
    """Sorts data."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=False,  # Data comes from workflow connections
                description="Input data to sort",
            ),
            "field": NodeParameter(
                name="field",
                type=str,
                required=False,
                description="Field to sort by for dict items",
            ),
            "reverse": NodeParameter(
                name="reverse",
                type=bool,
                required=False,
                default=False,
                description="Sort in descending order",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        data = kwargs["data"]
        field = kwargs.get("field")
        reverse = kwargs.get("reverse", False)

        if not data:
            return {"sorted_data": []}

        if field and isinstance(data[0], dict):
            sorted_data = sorted(data, key=lambda x: x.get(field), reverse=reverse)
        else:
            sorted_data = sorted(data, reverse=reverse)

        return {"sorted_data": sorted_data}
