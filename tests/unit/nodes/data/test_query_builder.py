"""Tests for Query Builder Integration."""

import pytest
from kailash.nodes.data.query_builder import (
    DatabaseDialect,
    QueryBuilder,
    QueryOperator,
    create_query_builder,
)
from kailash.sdk_exceptions import NodeValidationError


class TestQueryBuilder:
    """Test QueryBuilder functionality."""

    def test_initialization(self):
        """Test query builder initialization."""
        builder = QueryBuilder()
        assert builder.dialect == DatabaseDialect.POSTGRESQL
        assert builder.table_name is None
        assert builder.tenant_id is None
        assert builder.conditions == []
        assert builder.parameters == []
        assert builder.parameter_counter == 0

    def test_table_method(self):
        """Test table method."""
        builder = QueryBuilder().table("users")
        assert builder.table_name == "users"

    def test_tenant_method(self):
        """Test tenant method."""
        builder = QueryBuilder().tenant("tenant123")
        assert builder.tenant_id == "tenant123"

    def test_where_equality(self):
        """Test WHERE with equality operator."""
        builder = QueryBuilder().table("users").where("name", QueryOperator.EQ, "John")

        query, params = builder.build_select()
        assert "SELECT * FROM users WHERE name = $1" in query
        assert params == ["John"]

    def test_where_comparison_operators(self):
        """Test WHERE with comparison operators."""
        builder = QueryBuilder().table("users")

        # Test less than
        builder.where("age", QueryOperator.LT, 30)
        query, params = builder.build_select()
        assert "age < $1" in query
        assert params == [30]

        # Reset and test greater than or equal
        builder.reset().table("users").where("age", QueryOperator.GTE, 18)
        query, params = builder.build_select()
        assert "age >= $1" in query
        assert params == [18]

    def test_where_in_operator(self):
        """Test WHERE with IN operator."""
        builder = (
            QueryBuilder()
            .table("users")
            .where("status", QueryOperator.IN, ["active", "pending"])
        )

        query, params = builder.build_select()
        assert "status IN ($1, $2)" in query
        assert params == ["active", "pending"]

    def test_where_not_in_operator(self):
        """Test WHERE with NOT IN operator."""
        builder = (
            QueryBuilder()
            .table("users")
            .where("status", QueryOperator.NIN, ["banned", "deleted"])
        )

        query, params = builder.build_select()
        assert "status NOT IN ($1, $2)" in query
        assert params == ["banned", "deleted"]

    def test_where_like_operator(self):
        """Test WHERE with LIKE operator."""
        builder = (
            QueryBuilder().table("users").where("name", QueryOperator.LIKE, "John%")
        )

        query, params = builder.build_select()
        assert "name LIKE $1" in query
        assert params == ["John%"]

    def test_where_ilike_operator_postgresql(self):
        """Test WHERE with ILIKE operator on PostgreSQL."""
        builder = (
            QueryBuilder(DatabaseDialect.POSTGRESQL)
            .table("users")
            .where("name", QueryOperator.ILIKE, "john%")
        )

        query, params = builder.build_select()
        assert "name ILIKE $1" in query
        assert params == ["john%"]

    def test_where_ilike_operator_mysql(self):
        """Test WHERE with ILIKE operator on MySQL."""
        builder = (
            QueryBuilder(DatabaseDialect.MYSQL)
            .table("users")
            .where("name", QueryOperator.ILIKE, "john%")
        )

        query, params = builder.build_select()
        assert "LOWER(name) LIKE LOWER($1)" in query
        assert params == ["john%"]

    def test_where_regex_operator_postgresql(self):
        """Test WHERE with REGEX operator on PostgreSQL."""
        builder = (
            QueryBuilder(DatabaseDialect.POSTGRESQL)
            .table("users")
            .where("name", QueryOperator.REGEX, "^J.*")
        )

        query, params = builder.build_select()
        assert "name ~ $1" in query
        assert params == ["^J.*"]

    def test_where_regex_operator_mysql(self):
        """Test WHERE with REGEX operator on MySQL."""
        builder = (
            QueryBuilder(DatabaseDialect.MYSQL)
            .table("users")
            .where("name", QueryOperator.REGEX, "^J.*")
        )

        query, params = builder.build_select()
        assert "name REGEXP $1" in query
        assert params == ["^J.*"]

    def test_multiple_where_conditions(self):
        """Test multiple WHERE conditions."""
        builder = (
            QueryBuilder()
            .table("users")
            .where("age", QueryOperator.GTE, 18)
            .where("status", QueryOperator.EQ, "active")
            .where("city", QueryOperator.IN, ["New York", "Boston"])
        )

        query, params = builder.build_select()
        assert "age >= $1 AND status = $2 AND city IN ($3, $4)" in query
        assert params == [18, "active", "New York", "Boston"]

    def test_find_method_simple(self):
        """Test find method with simple conditions."""
        query_obj = {
            "name": "John",
            "age": {"$gte": 18},
            "status": {"$in": ["active", "pending"]},
        }

        builder = QueryBuilder().table("users").find(query_obj)

        query, params = builder.build_select()
        assert "name = $1" in query
        assert "age >= $2" in query
        assert "status IN ($3, $4)" in query
        assert params == ["John", 18, "active", "pending"]

    def test_find_method_logical_and(self):
        """Test find method with $and operator."""
        query_obj = {"$and": [{"age": {"$gte": 18}}, {"status": "active"}]}

        builder = QueryBuilder().table("users").find(query_obj)

        query, params = builder.build_select()
        assert "age >= $1" in query
        assert "status = $2" in query
        assert params == [18, "active"]

    def test_tenant_filtering(self):
        """Test automatic tenant filtering."""
        builder = (
            QueryBuilder()
            .table("users")
            .tenant("tenant123")
            .where("name", QueryOperator.EQ, "John")
        )

        query, params = builder.build_select()
        assert "tenant_id = $1 AND (name = $2)" in query
        assert params == ["tenant123", "John"]

    def test_tenant_filtering_no_conditions(self):
        """Test tenant filtering with no other conditions."""
        builder = QueryBuilder().table("users").tenant("tenant123")

        query, params = builder.build_select()
        assert "tenant_id = $1" in query
        assert params == ["tenant123"]

    def test_build_update(self):
        """Test building UPDATE queries."""
        builder = QueryBuilder().table("users").where("id", QueryOperator.EQ, 1)

        updates = {"name": "Jane", "age": 25}
        query, params = builder.build_update(updates)

        assert "UPDATE users SET name = $1, age = $2 WHERE id = $3" in query
        assert params == ["Jane", 25, 1]

    def test_build_delete(self):
        """Test building DELETE queries."""
        builder = (
            QueryBuilder().table("users").where("status", QueryOperator.EQ, "deleted")
        )

        query, params = builder.build_delete()

        assert "DELETE FROM users WHERE status = $1" in query
        assert params == ["deleted"]

    def test_build_select_with_fields(self):
        """Test building SELECT queries with specific fields."""
        builder = (
            QueryBuilder().table("users").where("status", QueryOperator.EQ, "active")
        )

        query, params = builder.build_select(["name", "email"])

        assert "SELECT name, email FROM users WHERE status = $1" in query
        assert params == ["active"]

    def test_json_operators_postgresql(self):
        """Test JSON operators on PostgreSQL."""
        builder = QueryBuilder(DatabaseDialect.POSTGRESQL).table("users")

        # Test contains
        builder.where("metadata", QueryOperator.CONTAINS, {"key": "value"})
        query, params = builder.build_select()
        assert "metadata @> $1" in query
        assert params == [{"key": "value"}]

        # Test contained by
        builder.reset().table("users").where(
            "tags", QueryOperator.CONTAINED_BY, ["tag1", "tag2"]
        )
        query, params = builder.build_select()
        assert "tags <@ $1" in query
        assert params == [["tag1", "tag2"]]

        # Test has key
        builder.reset().table("users").where("metadata", QueryOperator.HAS_KEY, "email")
        query, params = builder.build_select()
        assert "metadata ? $1" in query
        assert params == ["email"]

    def test_json_operators_mysql(self):
        """Test JSON operators on MySQL."""
        builder = QueryBuilder(DatabaseDialect.MYSQL).table("users")

        # Test contains
        builder.where("metadata", QueryOperator.CONTAINS, {"key": "value"})
        query, params = builder.build_select()
        assert "JSON_CONTAINS(metadata, $1)" in query
        assert params == [{"key": "value"}]

        # Test has key
        builder.reset().table("users").where("metadata", QueryOperator.HAS_KEY, "email")
        query, params = builder.build_select()
        assert "JSON_EXTRACT(metadata, '$.email') IS NOT NULL" in query
        assert params == []

    def test_validation_errors(self):
        """Test validation errors."""
        builder = QueryBuilder()

        # Test missing table name
        with pytest.raises(NodeValidationError, match="Table name is required"):
            builder.build_select()

        # Test IN with non-list value
        with pytest.raises(NodeValidationError, match="\\$in requires a list or tuple"):
            builder.where("status", QueryOperator.IN, "active")

        # Test LIKE with non-string value
        with pytest.raises(
            NodeValidationError, match="\\$like requires a string value"
        ):
            builder.where("name", QueryOperator.LIKE, 123)

        # Test HAS_KEY with non-string value
        with pytest.raises(
            NodeValidationError, match="\\$has_key requires a string key"
        ):
            builder.where("metadata", QueryOperator.HAS_KEY, 123)

    def test_reset_method(self):
        """Test reset method."""
        builder = (
            QueryBuilder()
            .table("users")
            .tenant("tenant123")
            .where("name", QueryOperator.EQ, "John")
        )

        # Verify state is set
        assert builder.table_name == "users"
        assert builder.tenant_id == "tenant123"
        assert len(builder.conditions) == 1

        # Reset and verify state is cleared
        builder.reset()
        assert builder.table_name is None
        assert builder.tenant_id is None
        assert builder.conditions == []
        assert builder.parameters == []
        assert builder.parameter_counter == 0

    def test_unknown_operator_error(self):
        """Test error for unknown operator."""
        builder = QueryBuilder().table("users")

        with pytest.raises(NodeValidationError, match="Unknown operator: \\$unknown"):
            builder.find({"name": {"$unknown": "value"}})

    def test_and_operator_validation(self):
        """Test $and operator validation."""
        builder = QueryBuilder().table("users")

        # Test with non-list value
        with pytest.raises(
            NodeValidationError, match="\\$and requires a list of conditions"
        ):
            builder.find({"$and": "not a list"})

    def test_or_operator_validation(self):
        """Test $or operator validation."""
        builder = QueryBuilder().table("users")

        # Test with non-list value
        with pytest.raises(
            NodeValidationError, match="\\$or requires a list of conditions"
        ):
            builder.find({"$or": "not a list"})


class TestQueryBuilderFactory:
    """Test query builder factory function."""

    def test_create_query_builder_postgresql(self):
        """Test creating PostgreSQL query builder."""
        builder = create_query_builder("postgresql")
        assert builder.dialect == DatabaseDialect.POSTGRESQL

    def test_create_query_builder_mysql(self):
        """Test creating MySQL query builder."""
        builder = create_query_builder("mysql")
        assert builder.dialect == DatabaseDialect.MYSQL

    def test_create_query_builder_sqlite(self):
        """Test creating SQLite query builder."""
        builder = create_query_builder("sqlite")
        assert builder.dialect == DatabaseDialect.SQLITE

    def test_create_query_builder_case_insensitive(self):
        """Test creating query builder with case insensitive dialect."""
        builder = create_query_builder("PostgreSQL")
        assert builder.dialect == DatabaseDialect.POSTGRESQL

    def test_create_query_builder_invalid_dialect(self):
        """Test creating query builder with invalid dialect."""
        with pytest.raises(
            NodeValidationError, match="Unsupported database dialect: invalid"
        ):
            create_query_builder("invalid")

    def test_create_query_builder_default(self):
        """Test creating query builder with default dialect."""
        builder = create_query_builder()
        assert builder.dialect == DatabaseDialect.POSTGRESQL
