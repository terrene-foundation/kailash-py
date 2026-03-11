"""
DataFlow Aggregate Operations Node

Provides intelligent aggregation with natural language expressions.
"""

import logging
import re
import statistics
from collections import defaultdict
from typing import Any, Dict, List, Optional, Union

from kailash.nodes.base import Node, NodeParameter, NodeRegistry

from .workflow_connection_manager import SmartNodeConnectionMixin

logger = logging.getLogger(__name__)


class AggregateNode(Node):
    """Aggregate node with visual operations and natural language support.

    This node supports:
    - Natural language aggregations: "sum of amount", "average of price", "count of users"
    - Multiple aggregation functions: sum, average, count, min, max, median, mode
    - Grouping operations: "sum of amount by category", "average price by region"
    - Smart field detection: automatically finds numeric fields for aggregation
    - Complex expressions: "sum of amount where status is active"
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define parameters for AggregateNode."""
        return {
            "data": NodeParameter(
                name="data", type=list, required=True, description="Data to aggregate"
            ),
            "aggregate_expression": NodeParameter(
                name="aggregate_expression",
                type=str,
                required=True,
                description="Natural language aggregation expression",
            ),
            "group_by": NodeParameter(
                name="group_by",
                type=list,
                required=False,
                default=[],
                description="Fields to group by (auto-detected from expression if not specified)",
            ),
            "filter_expression": NodeParameter(
                name="filter_expression",
                type=str,
                required=False,
                description="Optional filter to apply before aggregation",
            ),
            "numeric_fields": NodeParameter(
                name="numeric_fields",
                type=list,
                required=False,
                default=[],
                description="Override auto-detected numeric fields",
            ),
            "return_details": NodeParameter(
                name="return_details",
                type=bool,
                required=False,
                default=False,
                description="Return detailed breakdown of calculations",
            ),
            "connection_pool_id": NodeParameter(
                name="connection_pool_id",
                type=str,
                required=False,
                description="ID of DataFlowConnectionManager node for database operations",
            ),
        }

    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute aggregation operations."""
        data = kwargs.get("data", [])
        aggregate_expression = kwargs.get("aggregate_expression", "")
        group_by = kwargs.get("group_by", [])
        filter_expression = kwargs.get("filter_expression")
        numeric_fields = kwargs.get("numeric_fields", [])
        return_details = kwargs.get("return_details", False)

        logger.info(f"Executing AggregateNode with expression: {aggregate_expression}")

        if not data:
            return {
                "result": None,
                "aggregate_expression": aggregate_expression,
                "total_records": 0,
                "parsed_successfully": True,
            }

        try:
            # Auto-detect numeric fields if not specified
            if not numeric_fields:
                numeric_fields = self._auto_detect_numeric_fields(
                    data[0] if data else {}
                )

            # Apply filter if specified
            filtered_data = data
            if filter_expression:
                filtered_data = self._apply_filter(data, filter_expression)

            # Parse aggregation expression
            agg_config = self._parse_aggregate_expression(
                aggregate_expression, numeric_fields, group_by
            )

            # Perform aggregation
            result = self._perform_aggregation(filtered_data, agg_config)

            return {
                "result": result,
                "aggregate_expression": aggregate_expression,
                "aggregation_function": agg_config["function"],
                "field": agg_config["field"],
                "group_by": agg_config["group_by"],
                "total_records": len(data),
                "filtered_records": len(filtered_data),
                "parsed_successfully": True,
                "details": agg_config.get("details") if return_details else None,
            }

        except Exception as e:
            logger.error(f"Failed to execute aggregation '{aggregate_expression}': {e}")
            return {
                "result": None,
                "aggregate_expression": aggregate_expression,
                "total_records": len(data),
                "error": str(e),
                "parsed_successfully": False,
            }

    def _auto_detect_numeric_fields(self, sample_record: Dict) -> List[str]:
        """Auto-detect numeric fields from sample record."""
        numeric_fields = []

        for field_name, value in sample_record.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                numeric_fields.append(field_name)

        return numeric_fields

    def _apply_filter(self, data: List[Dict], filter_expression: str) -> List[Dict]:
        """Apply simple filter to data before aggregation."""
        # Simple filter implementation - could be enhanced to use NaturalLanguageFilterNode
        filter_expr = filter_expression.lower().strip()

        # Basic "where field is value" pattern
        where_pattern = r"where\s+(\w+)\s+is\s+(\w+)"
        match = re.search(where_pattern, filter_expr)

        if match:
            field, value = match.groups()
            return [
                record
                for record in data
                if str(record.get(field, "")).lower() == value.lower()
            ]

        # Basic "where field equals value" pattern
        equals_pattern = r'where\s+(\w+)\s+equals\s+(["\']?)([^"\']+)\2'
        match = re.search(equals_pattern, filter_expr)

        if match:
            field, _, value = match.groups()
            return [record for record in data if str(record.get(field, "")) == value]

        return data

    def _parse_aggregate_expression(
        self, expression: str, numeric_fields: List[str], group_by: List[str]
    ) -> Dict[str, Any]:
        """Parse natural language aggregation expression."""
        expression = expression.lower().strip()

        # Extract aggregation function and field
        agg_patterns = [
            (r"sum of (\w+)", "sum"),
            (r"total (\w+)", "sum"),
            (r"average (?:of )?(\w+)", "average"),
            (r"mean (?:of )?(\w+)", "average"),
            (r"avg (?:of )?(\w+)", "average"),
            (r"count (?:of )?(\w+)", "count"),
            (r"number of (\w+)", "count"),
            (r"minimum (?:of )?(\w+)", "min"),
            (r"min (?:of )?(\w+)", "min"),
            (r"maximum (?:of )?(\w+)", "max"),
            (r"max (?:of )?(\w+)", "max"),
            (r"median (?:of )?(\w+)", "median"),
            (r"mode (?:of )?(\w+)", "mode"),
            (r"standard deviation (?:of )?(\w+)", "std"),
            (r"std (?:of )?(\w+)", "std"),
            (r"variance (?:of )?(\w+)", "variance"),
        ]

        function = None
        field = None

        for pattern, func in agg_patterns:
            match = re.search(pattern, expression)
            if match:
                function = func
                field = match.group(1)
                break

        if not function:
            # Try to infer from context
            if any(word in expression for word in ["sum", "total"]):
                function = "sum"
            elif any(word in expression for word in ["average", "mean", "avg"]):
                function = "average"
            elif any(word in expression for word in ["count", "number"]):
                function = "count"
            else:
                function = "sum"  # Default fallback

        # Auto-detect field if not found
        if not field:
            field = self._detect_field_from_expression(expression, numeric_fields)

        # Extract group by information
        detected_group_by = group_by.copy()

        # Look for "by" keyword
        by_pattern = r"by (\w+(?:,\s*\w+)*)"
        match = re.search(by_pattern, expression)
        if match:
            by_fields = [f.strip() for f in match.group(1).split(",")]
            detected_group_by.extend(by_fields)

        # Remove duplicates
        detected_group_by = list(set(detected_group_by))

        return {
            "function": function,
            "field": field,
            "group_by": detected_group_by,
            "original_expression": expression,
            "details": {
                "detected_function": function,
                "detected_field": field,
                "detected_group_by": detected_group_by,
            },
        }

    def _detect_field_from_expression(
        self, expression: str, numeric_fields: List[str]
    ) -> Optional[str]:
        """Detect target field from expression context."""
        # Look for common field names in expression
        common_fields = [
            "amount",
            "price",
            "total",
            "value",
            "cost",
            "revenue",
            "quantity",
            "count",
        ]

        for field in common_fields:
            if field in expression:
                return field

        # Fall back to first numeric field
        return numeric_fields[0] if numeric_fields else None

    def _perform_aggregation(self, data: List[Dict], agg_config: Dict[str, Any]) -> Any:
        """Perform the actual aggregation operation."""
        function = agg_config["function"]
        field = agg_config["field"]
        group_by = agg_config["group_by"]

        if not data:
            return None

        if not group_by:
            # Simple aggregation without grouping
            return self._aggregate_values(data, function, field)
        else:
            # Grouped aggregation
            return self._aggregate_grouped(data, function, field, group_by)

    def _aggregate_values(
        self, data: List[Dict], function: str, field: Optional[str]
    ) -> Any:
        """Aggregate values without grouping."""
        if function == "count":
            if field:
                # Count non-null values in field
                return len([record for record in data if record.get(field) is not None])
            else:
                # Count all records
                return len(data)

        # For other functions, we need a field
        if not field:
            return None

        # Extract numeric values
        values = []
        for record in data:
            value = record.get(field)
            if value is not None:
                try:
                    values.append(float(value))
                except (ValueError, TypeError):
                    continue

        if not values:
            return None

        # Apply aggregation function
        if function == "sum":
            return sum(values)
        elif function == "average":
            return statistics.mean(values)
        elif function == "min":
            return min(values)
        elif function == "max":
            return max(values)
        elif function == "median":
            return statistics.median(values)
        elif function == "mode":
            try:
                return statistics.mode(values)
            except statistics.StatisticsError:
                return None  # No unique mode
        elif function == "std":
            return statistics.stdev(values) if len(values) > 1 else 0
        elif function == "variance":
            return statistics.variance(values) if len(values) > 1 else 0
        else:
            return sum(values)  # Default to sum

    def _aggregate_grouped(
        self, data: List[Dict], function: str, field: Optional[str], group_by: List[str]
    ) -> Dict[str, Any]:
        """Aggregate values with grouping."""
        # Group data by specified fields
        groups = defaultdict(list)

        for record in data:
            # Create group key
            group_key = tuple(str(record.get(gb_field, "")) for gb_field in group_by)
            groups[group_key].append(record)

        # Aggregate each group
        result = {}
        for group_key, group_data in groups.items():
            # Create readable group name
            if len(group_by) == 1:
                group_name = str(group_key[0])
            else:
                group_name = " | ".join(
                    f"{gb}={gk}" for gb, gk in zip(group_by, group_key)
                )

            # Calculate aggregation for this group
            agg_value = self._aggregate_values(group_data, function, field)
            result[group_name] = {
                "value": agg_value,
                "count": len(group_data),
                "group_fields": dict(zip(group_by, group_key)),
            }

        return result

    def _get_aggregation_summary(
        self, result: Any, agg_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate summary information about the aggregation."""
        summary = {
            "function": agg_config["function"],
            "field": agg_config["field"],
            "group_by": agg_config["group_by"],
        }

        if isinstance(result, dict):
            # Grouped results
            summary["groups"] = len(result)
            summary["values"] = [
                group["value"]
                for group in result.values()
                if group["value"] is not None
            ]
        else:
            # Single result
            summary["groups"] = 0
            summary["values"] = [result] if result is not None else []

        return summary


# Register the node with Kailash's NodeRegistry
NodeRegistry.register(AggregateNode, alias="AggregateNode")
