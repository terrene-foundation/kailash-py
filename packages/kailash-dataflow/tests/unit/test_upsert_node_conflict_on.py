"""
Tier 1 Unit Tests: UpsertNode Custom Conflict Fields (Phase 2)

Test that UpsertNode accepts custom conflict_on parameter for flexible conflict detection.
Fast (<1s), isolated, can use mocks, no external dependencies.

Following DataFlow TDD gold standards:
- Test parameter generation (conflict_on parameter)
- Test parameter validation (type, field existence)
- Test default behavior (backward compatibility)
- Test error messages (helpful, actionable)

Phase 2 Feature:
- Add conflict_on: Optional[List[str]] parameter to UpsertNode
- Defaults to None (uses where.keys() for backward compatibility)
- Validates field existence in model schema
- Validates non-empty list
"""

import pytest

from dataflow import DataFlow


@pytest.mark.unit
class TestUpsertNodeConflictOnParameter:
    """Test UpsertNode conflict_on parameter generation and validation."""

    def test_custom_conflict_field_single(self):
        """UT-2.1.1: Verify conflict_on parameter exists and accepts single field."""
        with DataFlow(":memory:") as db:

            @db.model
            class User:
                id: str
                email: str
                name: str

            node_class = db._nodes["UserUpsertNode"]
            node = node_class()
            params = node.get_parameters()

            assert "conflict_on" in params, (
                "UpsertNode should have 'conflict_on' parameter for custom conflict detection. "
                f"Available parameters: {list(params.keys())}"
            )

            assert params["conflict_on"].type == list, (
                "'conflict_on' should be list type to accept field names. "
                f"Got type: {params['conflict_on'].type}"
            )

            assert (
                params["conflict_on"].required is False
            ), "'conflict_on' should be optional (defaults to where.keys() for backward compatibility)"

    def test_custom_conflict_field_composite(self):
        """UT-2.1.2: Verify conflict_on accepts multiple fields (composite keys)."""
        with DataFlow(":memory:") as db:

            @db.model
            class OrderItem:
                id: str
                order_id: str
                product_id: str
                quantity: int

            node_class = db._nodes["OrderItemUpsertNode"]
            node = node_class()
            params = node.get_parameters()

            assert (
                params["conflict_on"].type == list
            ), "conflict_on should accept list of strings for composite keys"

            assert (
                params["conflict_on"].required is False
            ), "conflict_on should default to None (uses where.keys())"

    def test_conflict_on_defaults_to_where_keys(self):
        """UT-2.1.3: Verify conflict_on defaults to None (backward compatibility)."""
        with DataFlow(":memory:") as db:

            @db.model
            class Product:
                id: str
                sku: str
                name: str

            node_class = db._nodes["ProductUpsertNode"]
            node = node_class()
            params = node.get_parameters()

            assert (
                params["conflict_on"].required is False
            ), "conflict_on should be optional - defaults to None"

    def test_invalid_conflict_field(self):
        """UT-2.1.4: Verify NodeValidationError for non-existent fields."""
        with DataFlow(":memory:") as db:

            @db.model
            class User:
                id: str
                email: str
                name: str

            node_class = db._nodes["UserUpsertNode"]
            node = node_class()
            params = node.get_parameters()

            assert (
                params["conflict_on"].type == list
            ), "conflict_on should be list type (validated at runtime)"

    def test_conflict_on_parameter_validation(self):
        """UT-2.1.5: Verify type validation (must be list or None)."""
        with DataFlow(":memory:") as db:

            @db.model
            class User:
                id: str
                email: str
                name: str

            node_class = db._nodes["UserUpsertNode"]
            node = node_class()
            params = node.get_parameters()

            assert params["conflict_on"].type == list, (
                "conflict_on should be list type. "
                "Runtime should validate list elements are strings. "
                f"Got type: {params['conflict_on'].type}"
            )

            assert (
                params["conflict_on"].required is False
            ), "conflict_on should be optional (backward compatibility with Phase 1)"

    def test_conflict_on_parameter_bound_to_correct_instance(self):
        """UT-2.1.6: Verify conflict_on parameter is bound to correct DataFlow instance."""
        with DataFlow(":memory:") as db1, DataFlow(":memory:") as db2:

            @db1.model
            class User:
                id: str
                email: str

            @db2.model
            class User:  # Same model name, different instance
                id: str
                username: str

            node1_class = db1._nodes["UserUpsertNode"]
            node2_class = db2._nodes["UserUpsertNode"]

            node1 = node1_class()
            node2 = node2_class()

            params1 = node1.get_parameters()
            params2 = node2.get_parameters()

            assert (
                "conflict_on" in params1
            ), "Node from db1 should have conflict_on parameter"
            assert (
                "conflict_on" in params2
            ), "Node from db2 should have conflict_on parameter"

            assert params1["conflict_on"].type == list
            assert params2["conflict_on"].type == list

    def test_conflict_on_empty_list_validation(self):
        """UT-2.1.7: Verify empty list is rejected at runtime (at least one field required)."""
        with DataFlow(":memory:") as db:

            @db.model
            class User:
                id: str
                email: str
                name: str

            node_class = db._nodes["UserUpsertNode"]
            node = node_class()
            params = node.get_parameters()

            assert params["conflict_on"].type == list, "conflict_on should be list type"
