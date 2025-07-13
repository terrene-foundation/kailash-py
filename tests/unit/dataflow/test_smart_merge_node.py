"""Unit tests for DataFlow SmartMergeNode functionality.

These tests ensure that SmartMergeNode correctly performs intelligent merges
with auto-relationship detection and natural language support.
"""

import os
import sys

import pytest

# Add the DataFlow app to the path
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../../apps/kailash-dataflow/src")
)

from dataflow.nodes.smart_operations import SmartMergeNode


class TestSmartMergeNode:
    """Test SmartMergeNode intelligent merge operations."""

    def setup_method(self):
        """Set up test data for each test."""
        self.node = SmartMergeNode()

        # Sample user data
        self.users_data = [
            {"id": 1, "name": "Alice", "email": "alice@example.com"},
            {"id": 2, "name": "Bob", "email": "bob@example.com"},
            {"id": 3, "name": "Charlie", "email": "charlie@example.com"},
        ]

        # Sample order data
        self.orders_data = [
            {"id": 101, "user_id": 1, "total": 250.00, "status": "completed"},
            {"id": 102, "user_id": 2, "total": 150.00, "status": "pending"},
            {"id": 103, "user_id": 1, "total": 300.00, "status": "completed"},
            {
                "id": 104,
                "user_id": 4,
                "total": 100.00,
                "status": "pending",
            },  # No matching user
        ]

        # Sample profile data
        self.profiles_data = [
            {"user_id": 1, "bio": "Software engineer", "location": "NYC"},
            {"user_id": 2, "bio": "Designer", "location": "SF"},
            {"user_id": 3, "bio": "Manager", "location": "LA"},
        ]

    def test_auto_merge_with_foreign_key_detection(self):
        """Test auto merge with automatic foreign key detection."""
        result = self.node.execute(
            left_data=self.users_data,
            right_data=self.orders_data,
            merge_type="auto",
            left_model="User",
            right_model="Order",
        )

        # Should detect id -> user_id relationship
        assert result["auto_detected"] is True
        assert result["join_conditions"]["left_key"] == "id"
        assert result["join_conditions"]["right_key"] == "user_id"

        # Should have inner join results
        merged_data = result["merged_data"]
        assert len(merged_data) == 3  # 3 orders with matching users

        # Verify merge correctness
        for record in merged_data:
            assert "name" in record  # From users
            assert "total" in record  # From orders
            assert "user_id" in record  # Join key from orders
            assert "id" in record  # User's id (left table wins conflicts)
            assert "right_id" in record  # Order's id (right table field prefixed)

    def test_inner_join_explicit_conditions(self):
        """Test inner join with explicit join conditions."""
        result = self.node.execute(
            left_data=self.users_data,
            right_data=self.profiles_data,
            merge_type="inner",
            join_conditions={"left_key": "id", "right_key": "user_id"},
        )

        merged_data = result["merged_data"]
        assert len(merged_data) == 3  # All users have profiles

        # Verify merge correctness
        for record in merged_data:
            assert "name" in record  # From users
            assert "bio" in record  # From profiles
            assert record["id"] == record["user_id"]

    def test_left_join_preserves_left_records(self):
        """Test left join preserves all left records."""
        result = self.node.execute(
            left_data=self.users_data,
            right_data=self.orders_data,
            merge_type="left",
            join_conditions={"left_key": "id", "right_key": "user_id"},
        )

        merged_data = result["merged_data"]
        # Should include Charlie (user 3) even though no orders
        user_ids = {record["id"] for record in merged_data}
        assert 1 in user_ids
        assert 2 in user_ids
        assert 3 in user_ids

        # Charlie should be in result without order data
        charlie_records = [r for r in merged_data if r["id"] == 3]
        assert len(charlie_records) == 1
        assert "total" not in charlie_records[0]

    def test_right_join_preserves_right_records(self):
        """Test right join preserves all right records."""
        result = self.node.execute(
            left_data=self.users_data,
            right_data=self.orders_data,
            merge_type="right",
            join_conditions={"left_key": "id", "right_key": "user_id"},
        )

        merged_data = result["merged_data"]
        # Should include order 104 even though no matching user
        order_ids = {record.get("id") for record in merged_data if "total" in record}
        assert 101 in order_ids
        assert 102 in order_ids
        assert 103 in order_ids
        assert 104 in order_ids

    def test_outer_join_includes_all_records(self):
        """Test outer join includes all records from both datasets."""
        result = self.node.execute(
            left_data=self.users_data,
            right_data=self.orders_data,
            merge_type="outer",
            join_conditions={"left_key": "id", "right_key": "user_id"},
        )

        merged_data = result["merged_data"]

        # Should include Charlie (user without orders) and order 104 (order without user)
        has_charlie = any(r.get("id") == 3 and "name" in r for r in merged_data)
        has_orphan_order = any(r.get("id") == 104 and "total" in r for r in merged_data)

        assert has_charlie
        assert has_orphan_order

    def test_enrich_mode_adds_specific_fields(self):
        """Test enrich mode adds only specified fields."""
        result = self.node.execute(
            left_data=self.users_data,
            right_data=self.profiles_data,
            merge_type="enrich",
            join_conditions={"left_key": "id", "right_key": "user_id"},
            enrich_fields=["bio"],
        )

        merged_data = result["merged_data"]
        assert len(merged_data) == 3

        # Should add bio but not location
        for record in merged_data:
            assert "name" in record  # Original field
            assert "bio" in record  # Enriched field
            assert "location" not in record  # Not in enrich_fields

    def test_enrich_mode_all_fields_when_no_specification(self):
        """Test enrich mode adds all fields when no specific fields specified."""
        result = self.node.execute(
            left_data=self.users_data,
            right_data=self.profiles_data,
            merge_type="enrich",
            join_conditions={"left_key": "id", "right_key": "user_id"},
        )

        merged_data = result["merged_data"]

        # Should add all fields with "right_" prefix (except join key)
        for record in merged_data:
            assert "name" in record
            assert "right_bio" in record
            assert "right_location" in record

    def test_natural_language_specification(self):
        """Test natural language merge specification parsing."""
        result = self.node.execute(
            left_data=self.users_data,
            right_data=self.orders_data,
            merge_type="auto",
            natural_language_spec="users with their orders",
        )

        # Should parse natural language and detect correct relationship
        assert result["join_conditions"]["left_key"] == "id"
        assert result["join_conditions"]["right_key"] == "user_id"

        merged_data = result["merged_data"]
        assert len(merged_data) == 3  # 3 orders with matching users

    def test_auto_detection_fallback_with_common_fields(self):
        """Test auto-detection falls back to common field names."""
        # Data with common 'id' field
        left_data = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        right_data = [{"id": 1, "value": "X"}, {"id": 2, "value": "Y"}]

        result = self.node.execute(
            left_data=left_data, right_data=right_data, merge_type="auto"
        )

        # Should detect common 'id' field
        assert result["join_conditions"]["left_key"] == "id"
        assert result["join_conditions"]["right_key"] == "id"

        merged_data = result["merged_data"]
        assert len(merged_data) == 2

    def test_single_record_input_normalization(self):
        """Test that single records are normalized to lists."""
        single_user = {"id": 1, "name": "Alice"}
        single_profile = {"user_id": 1, "bio": "Engineer"}

        result = self.node.execute(
            left_data=single_user,
            right_data=single_profile,
            merge_type="inner",
            join_conditions={"left_key": "id", "right_key": "user_id"},
        )

        merged_data = result["merged_data"]
        assert len(merged_data) == 1
        assert merged_data[0]["name"] == "Alice"
        assert merged_data[0]["bio"] == "Engineer"

    def test_no_join_conditions_handling(self):
        """Test handling when no join conditions can be detected."""
        # Data with no common fields or detectable patterns
        left_data = [{"field_a": 1}, {"field_a": 2}]
        right_data = [{"field_b": "x"}, {"field_b": "y"}]

        result = self.node.execute(
            left_data=left_data, right_data=right_data, merge_type="auto"
        )

        # Should fall back to default id-based join
        assert result["join_conditions"]["left_key"] == "id"
        assert result["join_conditions"]["right_key"] == "id"

        # Since no 'id' fields exist, result should be empty
        assert len(result["merged_data"]) == 0

    def test_model_based_relationship_detection(self):
        """Test relationship detection based on model names."""
        result = self.node.execute(
            left_data=self.users_data,
            right_data=self.orders_data,
            merge_type="auto",
            left_model="User",
            right_model="Order",
        )

        # Should detect User -> Order relationship (id -> user_id)
        assert result["join_conditions"]["left_key"] == "id"
        assert result["join_conditions"]["right_key"] == "user_id"

    def test_reverse_model_relationship_detection(self):
        """Test relationship detection with reversed model order."""
        result = self.node.execute(
            left_data=self.orders_data,
            right_data=self.users_data,
            merge_type="auto",
            left_model="Order",
            right_model="User",
        )

        # Should detect Order -> User relationship (user_id -> id)
        assert result["join_conditions"]["left_key"] == "user_id"
        assert result["join_conditions"]["right_key"] == "id"

    def test_merge_result_metadata(self):
        """Test that merge results include proper metadata."""
        result = self.node.execute(
            left_data=self.users_data,
            right_data=self.orders_data,
            merge_type="inner",
            join_conditions={"left_key": "id", "right_key": "user_id"},
        )

        # Verify metadata
        assert "merged_data" in result
        assert "merge_type" in result
        assert "join_conditions" in result
        assert "left_count" in result
        assert "right_count" in result
        assert "result_count" in result
        assert "auto_detected" in result

        assert result["merge_type"] == "inner"
        assert result["left_count"] == 3
        assert result["right_count"] == 4
        assert result["result_count"] == len(result["merged_data"])

    def test_empty_data_handling(self):
        """Test handling of empty datasets."""
        result = self.node.execute(
            left_data=[], right_data=self.orders_data, merge_type="inner"
        )

        assert result["merged_data"] == []
        assert result["left_count"] == 0
        assert result["right_count"] == 4

    def test_unsupported_merge_type_error(self):
        """Test that unsupported merge types raise appropriate errors."""
        with pytest.raises(ValueError, match="Unsupported merge_type"):
            self.node.execute(
                left_data=self.users_data,
                right_data=self.orders_data,
                merge_type="invalid_type",
            )

    def test_node_parameters_definition(self):
        """Test that node parameters are properly defined."""
        params = self.node.get_parameters()

        # Verify required parameters
        assert "left_data" in params
        assert "right_data" in params
        assert params["left_data"].required is True
        assert params["right_data"].required is True

        # Verify optional parameters
        assert "merge_type" in params
        assert params["merge_type"].default == "auto"
        assert "join_conditions" in params
        assert "enrich_fields" in params
        assert "natural_language_spec" in params

    def test_complex_data_merge(self):
        """Test merge with more complex nested data structures."""
        complex_left = [
            {
                "id": 1,
                "user": {"name": "Alice", "dept": "Engineering"},
                "metadata": {"role": "Senior"},
            }
        ]
        complex_right = [
            {
                "user_id": 1,
                "project": {"name": "DataFlow", "status": "Active"},
                "hours": 40,
            }
        ]

        result = self.node.execute(
            left_data=complex_left,
            right_data=complex_right,
            merge_type="inner",
            join_conditions={"left_key": "id", "right_key": "user_id"},
        )

        merged_data = result["merged_data"]
        assert len(merged_data) == 1

        record = merged_data[0]
        assert record["user"]["name"] == "Alice"
        assert record["project"]["name"] == "DataFlow"
        assert record["hours"] == 40
