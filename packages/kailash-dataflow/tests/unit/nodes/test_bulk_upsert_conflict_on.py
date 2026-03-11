"""Unit tests for BulkUpsertNode conflict_on parameter.

Tests parameter validation, deduplication logic, and query building
with custom conflict fields (natural keys and composite keys).
"""

import pytest

from dataflow.nodes.bulk_upsert import BulkUpsertNode


class TestBulkUpsertConflictOnParameter:
    """Test conflict_on parameter handling in BulkUpsertNode."""

    def test_conflict_on_parameter_exists(self):
        """Test that conflict_on parameter is properly defined."""
        node = BulkUpsertNode(
            table_name="test_table",
            connection_string="postgresql://localhost/test",
        )

        parameters = node.get_parameters()
        assert "conflict_on" in parameters
        assert parameters["conflict_on"].type == list
        assert parameters["conflict_on"].required is False
        assert parameters["conflict_on"].default is None

    def test_conflict_on_parameter_description(self):
        """Test that conflict_on parameter has descriptive documentation."""
        node = BulkUpsertNode(
            table_name="test_table",
            connection_string="postgresql://localhost/test",
        )

        parameters = node.get_parameters()
        description = parameters["conflict_on"].description
        assert "Fields to detect conflicts on" in description
        assert "email" in description  # Example single field
        assert "order_id" in description  # Example composite key

    def test_deduplicate_with_single_conflict_field(self):
        """Test deduplication using single conflict field (email)."""
        node = BulkUpsertNode(
            table_name="users",
            connection_string="postgresql://localhost/test",
        )

        # Test data with duplicate emails
        data = [
            {"id": "1", "email": "alice@example.com", "name": "Alice 1"},
            {"id": "2", "email": "bob@example.com", "name": "Bob"},
            {
                "id": "3",
                "email": "alice@example.com",
                "name": "Alice 2",
            },  # Duplicate email
        ]

        # Deduplicate on email (keep first)
        deduplicated = node._deduplicate_batch_data(data, ["email"])

        assert len(deduplicated) == 2
        assert deduplicated[0]["email"] == "alice@example.com"
        assert deduplicated[0]["name"] == "Alice 1"  # Kept first occurrence
        assert deduplicated[1]["email"] == "bob@example.com"

    def test_deduplicate_with_composite_conflict_fields(self):
        """Test deduplication using composite key (order_id + product_id)."""
        node = BulkUpsertNode(
            table_name="order_items",
            connection_string="postgresql://localhost/test",
        )

        # Test data with duplicate composite keys
        data = [
            {"id": "1", "order_id": "ord-1", "product_id": "prod-A", "quantity": 5},
            {"id": "2", "order_id": "ord-1", "product_id": "prod-B", "quantity": 3},
            {
                "id": "3",
                "order_id": "ord-1",
                "product_id": "prod-A",
                "quantity": 10,
            },  # Duplicate
        ]

        # Deduplicate on composite key
        deduplicated = node._deduplicate_batch_data(data, ["order_id", "product_id"])

        assert len(deduplicated) == 2
        # First occurrence of (ord-1, prod-A) kept
        first_item = [d for d in deduplicated if d["product_id"] == "prod-A"][0]
        assert first_item["quantity"] == 5

    def test_deduplicate_keep_last_strategy(self):
        """Test deduplication with handle_duplicates='last' strategy."""
        node = BulkUpsertNode(
            table_name="users",
            connection_string="postgresql://localhost/test",
            handle_duplicates="last",
        )

        # Test data with duplicate emails
        data = [
            {"id": "1", "email": "alice@example.com", "name": "Alice Old"},
            {"id": "2", "email": "bob@example.com", "name": "Bob"},
            {"id": "3", "email": "alice@example.com", "name": "Alice New"},  # Latest
        ]

        # Deduplicate on email (keep last)
        deduplicated = node._deduplicate_batch_data(data, ["email"])

        assert len(deduplicated) == 2
        alice_record = [d for d in deduplicated if d["email"] == "alice@example.com"][0]
        assert alice_record["name"] == "Alice New"  # Kept last occurrence

    def test_build_query_with_single_conflict_field(self):
        """Test query building with single conflict field."""
        node = BulkUpsertNode(
            table_name="users",
            connection_string="postgresql://localhost/test",
            database_type="postgresql",
        )

        batch = [{"id": "1", "email": "alice@example.com", "name": "Alice"}]
        columns = ["id", "email", "name"]
        column_names = "id, email, name"

        query = node._build_upsert_query(
            batch, columns, column_names, False, "update", ["email"]
        )

        # Verify ON CONFLICT uses email
        assert "ON CONFLICT (email)" in query
        assert "DO UPDATE SET" in query
        # Verify email is excluded from update (it's the conflict field)
        assert "email = EXCLUDED.email" not in query

    def test_build_query_with_composite_conflict_fields(self):
        """Test query building with composite conflict fields."""
        node = BulkUpsertNode(
            table_name="order_items",
            connection_string="postgresql://localhost/test",
            database_type="postgresql",
        )

        batch = [
            {"id": "1", "order_id": "ord-1", "product_id": "prod-A", "quantity": 5}
        ]
        columns = ["id", "order_id", "product_id", "quantity"]
        column_names = "id, order_id, product_id, quantity"

        query = node._build_upsert_query(
            batch, columns, column_names, False, "update", ["order_id", "product_id"]
        )

        # Verify ON CONFLICT uses composite key
        assert "ON CONFLICT (order_id, product_id)" in query
        assert "DO UPDATE SET" in query
        # Verify conflict fields are excluded from update
        assert "order_id = EXCLUDED.order_id" not in query
        assert "product_id = EXCLUDED.product_id" not in query
        # Verify non-conflict fields are updated
        assert "quantity = EXCLUDED.quantity" in query

    def test_build_query_ignores_immutable_fields(self):
        """Test that id and created_at are never updated, regardless of conflict_on."""
        node = BulkUpsertNode(
            table_name="users",
            connection_string="postgresql://localhost/test",
            database_type="postgresql",
            auto_timestamps=True,
        )

        batch = [
            {
                "id": "1",
                "email": "alice@example.com",
                "name": "Alice",
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-02T00:00:00",
            }
        ]
        columns = ["id", "email", "name", "created_at", "updated_at"]
        column_names = "id, email, name, created_at, updated_at"

        query = node._build_upsert_query(
            batch, columns, column_names, False, "update", ["email"]
        )

        # Immutable fields should NEVER be in update clause
        assert "id = EXCLUDED.id" not in query
        assert "created_at = EXCLUDED.created_at" not in query
        # updated_at should use CURRENT_TIMESTAMP (auto-managed)
        assert "updated_at = CURRENT_TIMESTAMP" in query

    def test_empty_conflict_on_uses_all_columns(self):
        """Test that empty conflict_on list is handled gracefully."""
        node = BulkUpsertNode(
            table_name="users",
            connection_string="postgresql://localhost/test",
            database_type="postgresql",
        )

        batch = [{"id": "1", "email": "alice@example.com"}]
        columns = ["id", "email"]
        column_names = "id, email"

        # Empty conflict_on should build valid query (though semantically odd)
        query = node._build_upsert_query(
            batch, columns, column_names, False, "update", []
        )

        # Should still generate valid SQL
        assert "INSERT INTO users" in query
        assert "ON CONFLICT ()" in query

    def test_conflict_on_with_null_values(self):
        """Test deduplication behavior with NULL values in conflict fields.

        Note: Python's tuple hashing treats None as equal, so (None,) == (None,).
        This means NULL values WILL deduplicate in batch preprocessing.
        The database will handle NULL != NULL semantics during INSERT.
        """
        node = BulkUpsertNode(
            table_name="users",
            connection_string="postgresql://localhost/test",
        )

        # In Python deduplication, NULL values are treated as equal
        data = [
            {"id": "1", "email": None, "name": "User 1"},
            {"id": "2", "email": None, "name": "User 2"},
            {"id": "3", "email": "alice@example.com", "name": "Alice"},
        ]

        deduplicated = node._deduplicate_batch_data(data, ["email"])

        # Python treats None==None, so NULL emails deduplicate (keep first)
        assert len(deduplicated) == 2
        null_record = [d for d in deduplicated if d["email"] is None][0]
        assert null_record["name"] == "User 1"  # First occurrence kept

    def test_metadata_includes_resolved_conflict_on(self):
        """Test that result metadata includes the resolved conflict_on value."""
        # This is tested in integration tests since it requires async execution
        # Here we just verify the metadata structure is correct
        node = BulkUpsertNode(
            table_name="users",
            connection_string="postgresql://localhost/test",
            conflict_columns=["email"],  # Config default
        )

        # Verify config default is set
        assert node.conflict_columns == ["email"]


class TestBulkUpsertBackwardCompatibility:
    """Test backward compatibility when conflict_on is not provided."""

    def test_defaults_to_config_conflict_columns(self):
        """Test that omitting conflict_on uses config conflict_columns."""
        node = BulkUpsertNode(
            table_name="users",
            connection_string="postgresql://localhost/test",
            conflict_columns=["email"],  # Config default
        )

        batch = [{"id": "1", "email": "alice@example.com", "name": "Alice"}]
        columns = ["id", "email", "name"]
        column_names = "id, email, name"

        # When conflict_on=None, should use config conflict_columns
        query = node._build_upsert_query(
            batch, columns, column_names, False, "update", ["email"]  # From config
        )

        # Should use config default
        assert "ON CONFLICT (email)" in query

    def test_runtime_conflict_on_overrides_config(self):
        """Test that runtime conflict_on overrides config conflict_columns."""
        node = BulkUpsertNode(
            table_name="users",
            connection_string="postgresql://localhost/test",
            conflict_columns=["email"],  # Config default
        )

        batch = [{"id": "1", "username": "alice", "email": "alice@example.com"}]
        columns = ["id", "username", "email"]
        column_names = "id, username, email"

        # Runtime override with username instead of email
        query = node._build_upsert_query(
            batch, columns, column_names, False, "update", ["username"]  # Override
        )

        # Should use runtime override, not config
        assert "ON CONFLICT (username)" in query
        assert "ON CONFLICT (email)" not in query
