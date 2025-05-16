"""Transform nodes for data processing."""
from typing import Any, Dict, List, Callable, Union

from kailash.nodes.base import Node, NodeParameter, register_node


@register_node()
class Filter(Node):
    """Filters data based on a condition."""
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=True,
                description="Input data to filter"
            ),
            "field": NodeParameter(
                name="field",
                type=str,
                required=False,
                description="Field name for dict-based filtering"
            ),
            "operator": NodeParameter(
                name="operator",
                type=str,
                required=False,
                default="==",
                description="Comparison operator (==, !=, >, <, >=, <=, contains)"
            ),
            "value": NodeParameter(
                name="value",
                type=Any,
                required=False,
                description="Value to compare against"
            )
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
    
    def _apply_operator(self, item_value: Any, operator: str, compare_value: Any) -> bool:
        """Apply comparison operator."""
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


@register_node()
class Map(Node):
    """Maps data using a transformation."""
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=True,
                description="Input data to transform"
            ),
            "field": NodeParameter(
                name="field",
                type=str,
                required=False,
                description="Field to extract from dict items"
            ),
            "new_field": NodeParameter(
                name="new_field",
                type=str,
                required=False,
                description="New field name for dict items"
            ),
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=False,
                default="identity",
                description="Operation to apply (identity, upper, lower, multiply, add)"
            ),
            "value": NodeParameter(
                name="value",
                type=Union[int, float, str],
                required=False,
                description="Value for operations that need it"
            )
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
class Sort(Node):
    """Sorts data."""
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=True,
                description="Input data to sort"
            ),
            "field": NodeParameter(
                name="field",
                type=str,
                required=False,
                description="Field to sort by for dict items"
            ),
            "reverse": NodeParameter(
                name="reverse",
                type=bool,
                required=False,
                default=False,
                description="Sort in descending order"
            )
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