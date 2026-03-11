"""
DataFlow Smart Operations

Smart nodes that provide intelligent database operations with auto-detection.
"""

import logging
from typing import Any, Dict, List, Optional

from kailash.nodes.base import Node, NodeParameter, NodeRegistry

from .workflow_connection_manager import SmartNodeConnectionMixin

logger = logging.getLogger(__name__)


class SmartMergeNode(SmartNodeConnectionMixin, Node):
    """Smart merge node with auto-relationship detection.

    This node can automatically detect foreign key relationships and perform
    intelligent merges without requiring explicit join conditions.

    Features:
    - Auto-detection of foreign key relationships
    - Support for "auto" merge type
    - "enrich" mode to add related data
    - Natural language merge specifications
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._relationships_cache = {}

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define parameters for SmartMergeNode."""
        return {
            "left_data": NodeParameter(
                name="left_data",
                type=list,
                required=True,
                description="Left dataset for merge operation",
            ),
            "right_data": NodeParameter(
                name="right_data",
                type=list,
                required=True,
                description="Right dataset for merge operation",
            ),
            "merge_type": NodeParameter(
                name="merge_type",
                type=str,
                required=False,
                default="auto",
                description="Type of merge: 'auto', 'inner', 'left', 'right', 'outer', 'enrich'",
            ),
            "left_model": NodeParameter(
                name="left_model",
                type=str,
                required=False,
                description="Name of left model for auto-detection",
            ),
            "right_model": NodeParameter(
                name="right_model",
                type=str,
                required=False,
                description="Name of right model for auto-detection",
            ),
            "join_conditions": NodeParameter(
                name="join_conditions",
                type=dict,
                required=False,
                default={},
                description="Manual join conditions (overrides auto-detection)",
            ),
            "enrich_fields": NodeParameter(
                name="enrich_fields",
                type=list,
                required=False,
                default=[],
                description="Specific fields to enrich when using enrich mode",
            ),
            "natural_language_spec": NodeParameter(
                name="natural_language_spec",
                type=str,
                required=False,
                description="Natural language merge specification (e.g., 'merge users with their orders')",
            ),
            "connection_pool_id": NodeParameter(
                name="connection_pool_id",
                type=str,
                required=False,
                description="ID of DataFlowConnectionManager node for database operations",
            ),
        }

    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute smart merge operation with connection pool integration."""
        return self._execute_with_connection(self._perform_merge, **kwargs)

    def _perform_merge(self, **kwargs) -> Dict[str, Any]:
        """Perform the actual smart merge operation."""
        left_data = kwargs.get("left_data", [])
        right_data = kwargs.get("right_data", [])
        merge_type = kwargs.get("merge_type", "auto")
        left_model = kwargs.get("left_model")
        right_model = kwargs.get("right_model")
        join_conditions = kwargs.get("join_conditions", {})
        enrich_fields = kwargs.get("enrich_fields", [])
        natural_language_spec = kwargs.get("natural_language_spec")

        logger.info(f"Executing SmartMergeNode with merge_type: {merge_type}")

        # Normalize data to lists
        if isinstance(left_data, dict):
            left_data = [left_data]
        if isinstance(right_data, dict):
            right_data = [right_data]

        # Auto-detect relationships if merge_type is "auto"
        if merge_type == "auto":
            detected_conditions = self._auto_detect_join_conditions(
                left_data, right_data, left_model, right_model
            )
            if detected_conditions:
                join_conditions = detected_conditions
                logger.info(f"Auto-detected join conditions: {join_conditions}")
            else:
                logger.warning(
                    "Could not auto-detect join conditions, falling back to inner join on 'id'"
                )
                join_conditions = {"left_key": "id", "right_key": "id"}

        # Process natural language specification if provided
        if natural_language_spec:
            nl_conditions = self._parse_natural_language_spec(natural_language_spec)
            if nl_conditions:
                join_conditions.update(nl_conditions)
                logger.info(f"Applied natural language conditions: {nl_conditions}")

        # Perform the merge based on type
        if merge_type in ["auto", "inner"]:
            result = self._inner_join(left_data, right_data, join_conditions)
        elif merge_type == "left":
            result = self._left_join(left_data, right_data, join_conditions)
        elif merge_type == "right":
            result = self._right_join(left_data, right_data, join_conditions)
        elif merge_type == "outer":
            result = self._outer_join(left_data, right_data, join_conditions)
        elif merge_type == "enrich":
            result = self._enrich_merge(
                left_data, right_data, join_conditions, enrich_fields
            )
        else:
            raise ValueError(f"Unsupported merge_type: {merge_type}")

        return {
            "merged_data": result,
            "merge_type": merge_type,
            "join_conditions": join_conditions,
            "left_count": len(left_data),
            "right_count": len(right_data),
            "result_count": len(result),
            "auto_detected": merge_type == "auto" and not kwargs.get("join_conditions"),
        }

    def _auto_detect_join_conditions(
        self,
        left_data: List[Dict],
        right_data: List[Dict],
        left_model: Optional[str] = None,
        right_model: Optional[str] = None,
    ) -> Dict[str, str]:
        """Auto-detect join conditions based on data structure and model relationships."""

        if not left_data or not right_data:
            return {}

        # Get sample records
        left_sample = left_data[0]
        right_sample = right_data[0]

        # Strategy 1: Use model relationship information if available
        if left_model and right_model:
            model_conditions = self._detect_from_models(left_model, right_model)
            if model_conditions:
                return model_conditions

        # Strategy 2: Common foreign key patterns
        left_keys = set(left_sample.keys())
        right_keys = set(right_sample.keys())

        # Look for foreign key patterns
        # Check for foreign key in right table pointing to left table's id
        if (
            left_model
            and f"{left_model.lower()}_id" in right_keys
            and "id" in left_keys
        ):
            return {"left_key": "id", "right_key": f"{left_model.lower()}_id"}

        # Check for foreign key in left table pointing to right table's id
        if (
            right_model
            and f"{right_model.lower()}_id" in left_keys
            and "id" in right_keys
        ):
            return {"left_key": f"{right_model.lower()}_id", "right_key": "id"}

        # Common foreign key patterns (left_key, right_key)
        foreign_key_patterns = [
            ("id", "user_id"),  # users.id -> orders.user_id
            ("id", "customer_id"),  # customers.id -> orders.customer_id
            ("id", "product_id"),  # products.id -> order_items.product_id
            ("id", "order_id"),  # orders.id -> order_items.order_id
        ]

        for left_key, right_key in foreign_key_patterns:
            if left_key in left_keys and right_key in right_keys:
                return {"left_key": left_key, "right_key": right_key}

        # Strategy 3: Look for common field names
        common_fields = left_keys.intersection(right_keys)
        priority_fields = ["id", "user_id", "customer_id", "product_id", "order_id"]

        for field in priority_fields:
            if field in common_fields:
                return {"left_key": field, "right_key": field}

        # Strategy 4: First common field
        if common_fields:
            common_field = next(iter(common_fields))
            return {"left_key": common_field, "right_key": common_field}

        return {}

    def _detect_from_models(self, left_model: str, right_model: str) -> Dict[str, str]:
        """Detect join conditions from model relationship metadata."""
        # This would integrate with the DataFlow relationship detection
        # For now, return common patterns based on model names

        # Common relationship patterns
        relationships = {
            ("User", "Order"): {"left_key": "id", "right_key": "user_id"},
            ("Order", "User"): {"left_key": "user_id", "right_key": "id"},
            ("User", "Profile"): {"left_key": "id", "right_key": "user_id"},
            ("Profile", "User"): {"left_key": "user_id", "right_key": "id"},
            ("Order", "OrderItem"): {"left_key": "id", "right_key": "order_id"},
            ("OrderItem", "Order"): {"left_key": "order_id", "right_key": "id"},
            ("Product", "OrderItem"): {"left_key": "id", "right_key": "product_id"},
            ("OrderItem", "Product"): {"left_key": "product_id", "right_key": "id"},
        }

        return relationships.get((left_model, right_model), {})

    def _parse_natural_language_spec(self, spec: str) -> Dict[str, str]:
        """Parse natural language merge specifications."""
        spec_lower = spec.lower()

        # Simple pattern matching for common phrases
        patterns = {
            "users with their orders": {"left_key": "id", "right_key": "user_id"},
            "orders with users": {"left_key": "user_id", "right_key": "id"},
            "customers with orders": {"left_key": "id", "right_key": "customer_id"},
            "orders with customers": {"left_key": "customer_id", "right_key": "id"},
            "products with order items": {"left_key": "id", "right_key": "product_id"},
            "order items with products": {"left_key": "product_id", "right_key": "id"},
        }

        for pattern, conditions in patterns.items():
            if pattern in spec_lower:
                return conditions

        return {}

    def _inner_join(
        self,
        left_data: List[Dict],
        right_data: List[Dict],
        join_conditions: Dict[str, str],
    ) -> List[Dict]:
        """Perform inner join merge."""
        left_key = join_conditions.get("left_key")
        right_key = join_conditions.get("right_key")

        if not left_key or not right_key:
            return []

        # Create index for right data
        right_index = {}
        for right_record in right_data:
            key_value = right_record.get(right_key)
            if key_value is not None:
                if key_value not in right_index:
                    right_index[key_value] = []
                right_index[key_value].append(right_record)

        # Perform join
        result = []
        for left_record in left_data:
            left_value = left_record.get(left_key)
            if left_value is not None and left_value in right_index:
                for right_record in right_index[left_value]:
                    merged_record = self._merge_records(
                        left_record, right_record, left_key, right_key
                    )
                    result.append(merged_record)

        return result

    def _merge_records(
        self, left_record: Dict, right_record: Dict, left_key: str, right_key: str
    ) -> Dict:
        """Merge two records handling field name conflicts."""
        merged_record = left_record.copy()

        for key, value in right_record.items():
            if key in merged_record:
                if key == left_key and key == right_key:
                    # Same join key, no conflict - keep the same value
                    pass  # Already in merged_record
                elif key == right_key:
                    # This is the right join key, add it
                    merged_record[key] = value
                else:
                    # Field name conflict (not a join key), prefix right table field
                    merged_record[f"right_{key}"] = value
            else:
                # No conflict, add directly
                merged_record[key] = value

        return merged_record

    def _merge_records_right_primary(
        self, right_record: Dict, left_record: Dict, right_key: str, left_key: str
    ) -> Dict:
        """Merge two records with right table as primary (for right joins)."""
        merged_record = right_record.copy()

        for key, value in left_record.items():
            if key in merged_record:
                if key == left_key and key == right_key:
                    # Same join key, no conflict - keep the right value
                    pass  # Already in merged_record
                elif key == left_key and key != right_key:
                    # This is the left join key but conflicts with a right field
                    # In right join, prefix the left join key to avoid overwriting right field
                    merged_record[f"left_{key}"] = value
                else:
                    # Field name conflict (not a join key), prefix left table field
                    # In right join, right table fields have priority
                    merged_record[f"left_{key}"] = value
            else:
                # No conflict, add directly
                merged_record[key] = value

        return merged_record

    def _left_join(
        self,
        left_data: List[Dict],
        right_data: List[Dict],
        join_conditions: Dict[str, str],
    ) -> List[Dict]:
        """Perform left join merge."""
        left_key = join_conditions.get("left_key")
        right_key = join_conditions.get("right_key")

        if not left_key or not right_key:
            return left_data.copy()

        # Create index for right data
        right_index = {}
        for right_record in right_data:
            key_value = right_record.get(right_key)
            if key_value is not None:
                if key_value not in right_index:
                    right_index[key_value] = []
                right_index[key_value].append(right_record)

        # Perform left join
        result = []
        for left_record in left_data:
            left_value = left_record.get(left_key)
            if left_value is not None and left_value in right_index:
                for right_record in right_index[left_value]:
                    merged_record = self._merge_records(
                        left_record, right_record, left_key, right_key
                    )
                    result.append(merged_record)
            else:
                # Include left record even without match
                result.append(left_record.copy())

        return result

    def _right_join(
        self,
        left_data: List[Dict],
        right_data: List[Dict],
        join_conditions: Dict[str, str],
    ) -> List[Dict]:
        """Perform right join merge."""
        left_key = join_conditions.get("left_key")
        right_key = join_conditions.get("right_key")

        if not left_key or not right_key:
            return right_data.copy()

        # Create index for left data
        left_index = {}
        for left_record in left_data:
            key_value = left_record.get(left_key)
            if key_value is not None:
                if key_value not in left_index:
                    left_index[key_value] = []
                left_index[key_value].append(left_record)

        # Perform right join (preserve all right records)
        result = []
        for right_record in right_data:
            right_value = right_record.get(right_key)
            if right_value is not None and right_value in left_index:
                for left_record in left_index[right_value]:
                    # For right join, right table is "primary", so swap merge order
                    merged_record = self._merge_records_right_primary(
                        right_record, left_record, right_key, left_key
                    )
                    result.append(merged_record)
            else:
                # Include right record even without match
                result.append(right_record.copy())

        return result

    def _outer_join(
        self,
        left_data: List[Dict],
        right_data: List[Dict],
        join_conditions: Dict[str, str],
    ) -> List[Dict]:
        """Perform outer join merge."""
        left_key = join_conditions.get("left_key")
        right_key = join_conditions.get("right_key")

        if not left_key or not right_key:
            return left_data + right_data

        # Get left join results
        left_results = self._left_join(left_data, right_data, join_conditions)

        # Find unmatched right records
        left_values = {
            record.get(left_key)
            for record in left_data
            if record.get(left_key) is not None
        }
        unmatched_right = []
        for right_record in right_data:
            right_value = right_record.get(right_key)
            if right_value is not None and right_value not in left_values:
                unmatched_right.append(right_record.copy())

        return left_results + unmatched_right

    def _enrich_merge(
        self,
        left_data: List[Dict],
        right_data: List[Dict],
        join_conditions: Dict[str, str],
        enrich_fields: List[str],
    ) -> List[Dict]:
        """Perform enrich merge - add specific fields from right to left."""
        left_key = join_conditions.get("left_key")
        right_key = join_conditions.get("right_key")

        if not left_key or not right_key:
            return left_data.copy()

        # Create index for right data
        right_index = {}
        for right_record in right_data:
            key_value = right_record.get(right_key)
            if key_value is not None:
                right_index[key_value] = right_record

        # Perform enrichment
        result = []
        for left_record in left_data:
            enriched_record = left_record.copy()
            left_value = left_record.get(left_key)

            if left_value is not None and left_value in right_index:
                right_record = right_index[left_value]

                # Add all fields if no specific fields specified
                if not enrich_fields:
                    for key, value in right_record.items():
                        if key != right_key:  # Don't duplicate the join key
                            enriched_record[f"right_{key}"] = value
                else:
                    # Add only specified fields
                    for field in enrich_fields:
                        if field in right_record:
                            enriched_record[field] = right_record[field]

            result.append(enriched_record)

        return result


# Register only the SmartMergeNode with Kailash's NodeRegistry
# AggregateNode and NaturalLanguageFilterNode are registered in their respective standalone files
NodeRegistry.register(SmartMergeNode, alias="SmartMergeNode")
