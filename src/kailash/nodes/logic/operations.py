"""Logic operation nodes for the Kailash SDK."""
from typing import Any, Dict, List
from collections import defaultdict

from kailash.nodes.base import Node, NodeParameter, register_node


@register_node()
class Aggregator(Node):
    """Aggregates data based on grouping and operations."""
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=True,
                description="Input data to aggregate"
            ),
            "group_by": NodeParameter(
                name="group_by",
                type=str,
                required=False,
                description="Field to group by"
            ),
            "aggregate_field": NodeParameter(
                name="aggregate_field",
                type=str,
                required=False,
                description="Field to aggregate"
            ),
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=False,
                default="count",
                description="Aggregation operation (count, sum, avg, min, max)"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        data = kwargs["data"]
        group_by = kwargs.get("group_by")
        aggregate_field = kwargs.get("aggregate_field")
        operation = kwargs.get("operation", "count")
        
        if not data:
            return {"aggregated_data": []}
        
        if group_by:
            # Group the data
            groups = defaultdict(list)
            for item in data:
                if isinstance(item, dict):
                    key = item.get(group_by)
                    groups[key].append(item)
            
            # Aggregate each group
            aggregated = []
            for key, items in groups.items():
                result = {group_by: key}
                result["value"] = self._aggregate_items(items, aggregate_field, operation)
                aggregated.append(result)
            
            return {"aggregated_data": aggregated}
        else:
            # Aggregate all data
            result = self._aggregate_items(data, aggregate_field, operation)
            return {"aggregated_data": [{"value": result}]}
    
    def _aggregate_items(self, items: List[Any], field: str, operation: str) -> Any:
        """Perform aggregation operation on items."""
        if operation == "count":
            return len(items)
        
        if field:
            values = [item.get(field) for item in items if isinstance(item, dict)]
        else:
            values = items
        
        try:
            if operation == "sum":
                return sum(float(v) for v in values if v is not None)
            elif operation == "avg":
                numeric_values = [float(v) for v in values if v is not None]
                return sum(numeric_values) / len(numeric_values) if numeric_values else 0
            elif operation == "min":
                return min(v for v in values if v is not None)
            elif operation == "max":
                return max(v for v in values if v is not None)
            else:
                raise ValueError(f"Unknown operation: {operation}")
        except (ValueError, TypeError) as e:
            raise ValueError(f"Cannot perform {operation} on non-numeric values") from e


@register_node()
class Conditional(Node):
    """Conditional logic node that routes data based on conditions."""
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data": NodeParameter(
                name="data",
                type=Any,
                required=True,
                description="Input data to evaluate"
            ),
            "condition_field": NodeParameter(
                name="condition_field",
                type=str,
                required=False,
                description="Field to check for condition"
            ),
            "operator": NodeParameter(
                name="operator",
                type=str,
                required=False,
                default="==",
                description="Comparison operator"
            ),
            "value": NodeParameter(
                name="value",
                type=Any,
                required=False,
                description="Value to compare against"
            ),
            "true_value": NodeParameter(
                name="true_value",
                type=Any,
                required=False,
                default=None,
                description="Value to return if condition is true"
            ),
            "false_value": NodeParameter(
                name="false_value",
                type=Any,
                required=False,
                default=None,
                description="Value to return if condition is false"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        data = kwargs["data"]
        condition_field = kwargs.get("condition_field")
        operator = kwargs.get("operator", "==")
        value = kwargs.get("value")
        true_value = kwargs.get("true_value", data)
        false_value = kwargs.get("false_value", None)
        
        # Extract value to check
        if condition_field and isinstance(data, dict):
            check_value = data.get(condition_field)
        else:
            check_value = data
        
        # Evaluate condition
        condition_met = self._evaluate_condition(check_value, operator, value)
        
        # Return appropriate value
        result = true_value if condition_met else false_value
        
        return {
            "result": result,
            "condition_met": condition_met
        }
    
    def _evaluate_condition(self, check_value: Any, operator: str, compare_value: Any) -> bool:
        """Evaluate a condition."""
        if operator == "==":
            return check_value == compare_value
        elif operator == "!=":
            return check_value != compare_value
        elif operator == ">":
            return check_value > compare_value
        elif operator == "<":
            return check_value < compare_value
        elif operator == ">=":
            return check_value >= compare_value
        elif operator == "<=":
            return check_value <= compare_value
        elif operator == "contains":
            return compare_value in str(check_value)
        elif operator == "is_null":
            return check_value is None
        elif operator == "is_not_null":
            return check_value is not None
        else:
            raise ValueError(f"Unknown operator: {operator}")


@register_node()
class Merge(Node):
    """Merges multiple data sources."""
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data1": NodeParameter(
                name="data1",
                type=Any,
                required=True,
                description="First data source"
            ),
            "data2": NodeParameter(
                name="data2",
                type=Any,
                required=True,
                description="Second data source"
            ),
            "merge_type": NodeParameter(
                name="merge_type",
                type=str,
                required=False,
                default="concat",
                description="Type of merge (concat, zip, merge_dict)"
            ),
            "key": NodeParameter(
                name="key",
                type=str,
                required=False,
                description="Key field for dict merging"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        data1 = kwargs["data1"]
        data2 = kwargs["data2"]
        merge_type = kwargs.get("merge_type", "concat")
        key = kwargs.get("key")
        
        if merge_type == "concat":
            if isinstance(data1, list) and isinstance(data2, list):
                result = data1 + data2
            else:
                result = [data1, data2]
        
        elif merge_type == "zip":
            if isinstance(data1, list) and isinstance(data2, list):
                result = list(zip(data1, data2))
            else:
                result = [(data1, data2)]
        
        elif merge_type == "merge_dict":
            if isinstance(data1, dict) and isinstance(data2, dict):
                result = {**data1, **data2}
            elif isinstance(data1, list) and isinstance(data2, list) and key:
                # Merge lists of dicts by key
                result = []
                data2_indexed = {item.get(key): item for item in data2 if isinstance(item, dict)}
                
                for item in data1:
                    if isinstance(item, dict):
                        key_value = item.get(key)
                        if key_value in data2_indexed:
                            merged_item = {**item, **data2_indexed[key_value]}
                            result.append(merged_item)
                        else:
                            result.append(item)
            else:
                raise ValueError("merge_dict requires dict inputs or lists of dicts with a key")
        
        else:
            raise ValueError(f"Unknown merge type: {merge_type}")
        
        return {"merged_data": result}