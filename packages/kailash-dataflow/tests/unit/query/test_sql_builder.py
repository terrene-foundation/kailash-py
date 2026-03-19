"""
Unit tests for the DataFlow SQL Aggregation Query Module.

These tests are SELF-CONTAINED: they import ONLY from dataflow.query.models
and dataflow.query.sql_builder. They do NOT import from the DataFlow engine
or kailash core, avoiding the pre-existing import error in those packages.

Tests verify:
- SQL string generation correctness
- Parameterized query safety (values never interpolated)
- Identifier validation (SQL injection prevention)
- Model serialization/deserialization roundtrips
- Filter operator parsing (__gt, __lt, __gte, __lte, __ne)
- AggregateSpec alias generation
- AggregateOp enum completeness
"""

from __future__ import annotations

import pytest

from dataflow.query.models import (
    AggregateOp,
    AggregateSpec,
    AggregationResult,
    validate_identifier,
)
from dataflow.query.sql_builder import (
    _build_where_clause,
    build_aggregate,
    build_count_by,
    build_sum_by,
)


# ---------------------------------------------------------------------------
# build_count_by tests
# ---------------------------------------------------------------------------


class TestBuildCountBy:
    def test_build_count_by_basic(self) -> None:
        """COUNT(*) GROUP BY without filter generates correct SQL."""
        sql, params = build_count_by("orders", "status")
        assert sql == "SELECT status, COUNT(*) AS count FROM orders GROUP BY status"
        assert params == []

    def test_build_count_by_with_filter(self) -> None:
        """COUNT(*) with a filter adds WHERE clause and parameterizes values."""
        sql, params = build_count_by("orders", "status", {"region": "US"})
        assert sql == (
            "SELECT status, COUNT(*) AS count FROM orders "
            "WHERE region = ? GROUP BY status"
        )
        assert params == ["US"]

    def test_build_count_by_with_multiple_filters(self) -> None:
        """Multiple filter conditions are joined with AND."""
        sql, params = build_count_by("orders", "status", {"region": "US", "year": 2026})
        assert "WHERE" in sql
        assert "AND" in sql
        assert "GROUP BY status" in sql
        # Both params are present
        assert len(params) == 2
        assert "US" in params
        assert 2026 in params

    def test_build_count_by_rejects_invalid_table(self) -> None:
        """Table name with injection attempt is rejected."""
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            build_count_by("orders; DROP TABLE users", "status")

    def test_build_count_by_rejects_invalid_group_by(self) -> None:
        """Group-by column with injection attempt is rejected."""
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            build_count_by("orders", "status; --")


# ---------------------------------------------------------------------------
# build_sum_by tests
# ---------------------------------------------------------------------------


class TestBuildSumBy:
    def test_build_sum_by_basic(self) -> None:
        """SUM() GROUP BY without filter generates correct SQL."""
        sql, params = build_sum_by("orders", "amount", "category")
        assert sql == (
            "SELECT category, SUM(amount) AS sum_amount "
            "FROM orders GROUP BY category"
        )
        assert params == []

    def test_build_sum_by_with_filter(self) -> None:
        """SUM() with filter adds WHERE clause and parameterizes values."""
        sql, params = build_sum_by("orders", "amount", "category", {"status": "paid"})
        assert sql == (
            "SELECT category, SUM(amount) AS sum_amount "
            "FROM orders WHERE status = ? GROUP BY category"
        )
        assert params == ["paid"]

    def test_build_sum_by_rejects_invalid_sum_field(self) -> None:
        """Sum field with injection attempt is rejected."""
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            build_sum_by("orders", "amount FROM orders; --", "category")


# ---------------------------------------------------------------------------
# build_aggregate tests
# ---------------------------------------------------------------------------


class TestBuildAggregate:
    def test_build_aggregate_single_spec(self) -> None:
        """Single aggregate spec without GROUP BY."""
        specs = [AggregateSpec(op=AggregateOp.COUNT, field="*")]
        sql, params = build_aggregate("orders", specs)
        assert sql == "SELECT COUNT(*) AS count_all FROM orders"
        assert params == []

    def test_build_aggregate_multiple_specs(self) -> None:
        """Multiple aggregate specs in a single query."""
        specs = [
            AggregateSpec(op=AggregateOp.COUNT, field="*"),
            AggregateSpec(op=AggregateOp.SUM, field="amount"),
            AggregateSpec(op=AggregateOp.AVG, field="price", alias="avg_price"),
        ]
        sql, params = build_aggregate("orders", specs)
        assert sql == (
            "SELECT COUNT(*) AS count_all, SUM(amount) AS sum_amount, "
            "AVG(price) AS avg_price FROM orders"
        )
        assert params == []

    def test_build_aggregate_with_group_by(self) -> None:
        """Aggregate with GROUP BY includes the group column in SELECT."""
        specs = [
            AggregateSpec(op=AggregateOp.COUNT, field="*"),
            AggregateSpec(op=AggregateOp.SUM, field="amount"),
        ]
        sql, params = build_aggregate("orders", specs, group_by="category")
        assert sql == (
            "SELECT category, COUNT(*) AS count_all, SUM(amount) AS sum_amount "
            "FROM orders GROUP BY category"
        )
        assert params == []

    def test_build_aggregate_with_filter(self) -> None:
        """Aggregate with both WHERE and GROUP BY."""
        specs = [AggregateSpec(op=AggregateOp.SUM, field="amount")]
        sql, params = build_aggregate(
            "orders", specs, group_by="category", filter={"status": "paid"}
        )
        assert sql == (
            "SELECT category, SUM(amount) AS sum_amount "
            "FROM orders WHERE status = ? GROUP BY category"
        )
        assert params == ["paid"]

    def test_build_aggregate_min_max(self) -> None:
        """MIN and MAX operations generate correct SQL."""
        specs = [
            AggregateSpec(op=AggregateOp.MIN, field="price", alias="min_price"),
            AggregateSpec(op=AggregateOp.MAX, field="price", alias="max_price"),
        ]
        sql, params = build_aggregate("products", specs)
        assert sql == (
            "SELECT MIN(price) AS min_price, MAX(price) AS max_price FROM products"
        )
        assert params == []

    def test_build_aggregate_empty_specs_raises(self) -> None:
        """Empty specs list raises ValueError."""
        with pytest.raises(ValueError, match="at least one AggregateSpec"):
            build_aggregate("orders", [])

    def test_build_aggregate_non_list_specs_raises(self) -> None:
        """Non-list specs raises TypeError."""
        with pytest.raises(TypeError, match="specs must be a list"):
            build_aggregate("orders", "not_a_list")  # type: ignore[arg-type]

    def test_build_aggregate_invalid_spec_type_raises(self) -> None:
        """Non-AggregateSpec item in specs list raises TypeError."""
        with pytest.raises(TypeError, match="specs\\[0\\] must be an AggregateSpec"):
            build_aggregate("orders", [{"op": "count", "field": "*"}])  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# Filter operator tests
# ---------------------------------------------------------------------------


class TestFilterOperators:
    def test_filter_eq_default(self) -> None:
        """Plain column name uses = operator."""
        where, params = _build_where_clause({"status": "active"})
        assert where == "status = ?"
        assert params == ["active"]

    def test_filter_gt(self) -> None:
        """__gt suffix produces > operator."""
        where, params = _build_where_clause({"age__gt": 18})
        assert where == "age > ?"
        assert params == [18]

    def test_filter_lt(self) -> None:
        """__lt suffix produces < operator."""
        where, params = _build_where_clause({"price__lt": 100})
        assert where == "price < ?"
        assert params == [100]

    def test_filter_gte(self) -> None:
        """__gte suffix produces >= operator."""
        where, params = _build_where_clause({"score__gte": 90})
        assert where == "score >= ?"
        assert params == [90]

    def test_filter_lte(self) -> None:
        """__lte suffix produces <= operator."""
        where, params = _build_where_clause({"quantity__lte": 0})
        assert where == "quantity <= ?"
        assert params == [0]

    def test_filter_ne(self) -> None:
        """__ne suffix produces != operator."""
        where, params = _build_where_clause({"status__ne": "deleted"})
        assert where == "status != ?"
        assert params == ["deleted"]

    def test_filter_multiple_operators(self) -> None:
        """Multiple filter conditions with different operators."""
        where, params = _build_where_clause(
            {"age__gte": 18, "age__lt": 65, "status": "active"}
        )
        assert "age >= ?" in where
        assert "age < ?" in where
        assert "status = ?" in where
        assert "AND" in where
        assert len(params) == 3

    def test_filter_empty_dict(self) -> None:
        """Empty filter dict returns empty clause."""
        where, params = _build_where_clause({})
        assert where == ""
        assert params == []

    def test_filter_rejects_invalid_column(self) -> None:
        """Column name with injection is rejected even with operator suffix."""
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            _build_where_clause({"name; DROP TABLE users__gt": 1})

    def test_filter_rejects_non_string_key(self) -> None:
        """Non-string filter key raises TypeError."""
        with pytest.raises(TypeError, match="Filter key must be a string"):
            _build_where_clause({42: "value"})  # type: ignore[dict-item]

    def test_filter_rejects_non_dict(self) -> None:
        """Non-dict filter raises TypeError."""
        with pytest.raises(TypeError, match="filter must be a dict"):
            _build_where_clause("not_a_dict")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# validate_identifier tests
# ---------------------------------------------------------------------------


class TestValidateIdentifier:
    def test_valid_simple(self) -> None:
        """Simple alphanumeric identifier passes validation."""
        validate_identifier("users")
        validate_identifier("order_items")
        validate_identifier("Table1")
        validate_identifier("_private")

    def test_valid_underscore_start(self) -> None:
        """Identifiers starting with underscore are valid."""
        validate_identifier("_id")
        validate_identifier("__internal")

    def test_rejects_injection_semicolon(self) -> None:
        """Semicolon injection attempt is rejected."""
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            validate_identifier("; DROP TABLE users")

    def test_rejects_injection_quote(self) -> None:
        """Quote injection attempt is rejected."""
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            validate_identifier("users' OR '1'='1")

    def test_rejects_dash(self) -> None:
        """Identifier with dash is rejected (not valid SQL identifier)."""
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            validate_identifier("my-table")

    def test_rejects_space(self) -> None:
        """Identifier with space is rejected."""
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            validate_identifier("my table")

    def test_rejects_dot(self) -> None:
        """Identifier with dot is rejected (no schema.table qualification)."""
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            validate_identifier("schema.table")

    def test_rejects_empty_string(self) -> None:
        """Empty string is rejected."""
        with pytest.raises(ValueError, match="must not be empty"):
            validate_identifier("")

    def test_rejects_numeric_start(self) -> None:
        """Identifier starting with a digit is rejected."""
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            validate_identifier("1table")

    def test_rejects_non_string(self) -> None:
        """Non-string input raises TypeError."""
        with pytest.raises(TypeError, match="must be a string"):
            validate_identifier(42)  # type: ignore[arg-type]

    def test_rejects_none(self) -> None:
        """None input raises TypeError."""
        with pytest.raises(TypeError, match="must be a string"):
            validate_identifier(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# AggregateSpec tests
# ---------------------------------------------------------------------------


class TestAggregateSpec:
    def test_effective_alias_explicit(self) -> None:
        """Explicit alias is returned as-is."""
        spec = AggregateSpec(op=AggregateOp.SUM, field="amount", alias="total_amount")
        assert spec.effective_alias() == "total_amount"

    def test_effective_alias_auto_field(self) -> None:
        """Auto-generated alias is {op}_{field}."""
        spec = AggregateSpec(op=AggregateOp.AVG, field="price")
        assert spec.effective_alias() == "avg_price"

    def test_effective_alias_count_star(self) -> None:
        """COUNT(*) auto-generates alias 'count_all'."""
        spec = AggregateSpec(op=AggregateOp.COUNT, field="*")
        assert spec.effective_alias() == "count_all"

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """Serialization to dict and back preserves all fields."""
        original = AggregateSpec(op=AggregateOp.SUM, field="amount", alias="total")
        data = original.to_dict()
        restored = AggregateSpec.from_dict(data)
        assert restored.op == original.op
        assert restored.field == original.field
        assert restored.alias == original.alias

    def test_to_dict_from_dict_roundtrip_no_alias(self) -> None:
        """Roundtrip without alias preserves None."""
        original = AggregateSpec(op=AggregateOp.COUNT, field="*")
        data = original.to_dict()
        restored = AggregateSpec.from_dict(data)
        assert restored.op == AggregateOp.COUNT
        assert restored.field == "*"
        assert restored.alias is None

    def test_to_dict_structure(self) -> None:
        """to_dict returns expected keys and values."""
        spec = AggregateSpec(op=AggregateOp.MAX, field="price", alias="top_price")
        d = spec.to_dict()
        assert d == {"op": "max", "field": "price", "alias": "top_price"}

    def test_from_dict_missing_op_raises(self) -> None:
        """from_dict without 'op' key raises KeyError."""
        with pytest.raises(KeyError, match="op"):
            AggregateSpec.from_dict({"field": "amount"})

    def test_from_dict_missing_field_raises(self) -> None:
        """from_dict without 'field' key raises KeyError."""
        with pytest.raises(KeyError, match="field"):
            AggregateSpec.from_dict({"op": "sum"})

    def test_from_dict_invalid_op_raises(self) -> None:
        """from_dict with unknown op value raises ValueError."""
        with pytest.raises(ValueError):
            AggregateSpec.from_dict({"op": "INVALID", "field": "amount"})

    def test_rejects_wildcard_with_non_count(self) -> None:
        """Wildcard '*' is only valid with COUNT."""
        with pytest.raises(ValueError, match="only valid with COUNT"):
            AggregateSpec(op=AggregateOp.SUM, field="*")

    def test_rejects_invalid_field(self) -> None:
        """Field with invalid identifier is rejected."""
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            AggregateSpec(op=AggregateOp.SUM, field="amount; --")

    def test_rejects_invalid_alias(self) -> None:
        """Alias with invalid identifier is rejected."""
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            AggregateSpec(op=AggregateOp.SUM, field="amount", alias="total amount")

    def test_rejects_non_enum_op(self) -> None:
        """Non-AggregateOp value for op raises TypeError."""
        with pytest.raises(TypeError, match="must be an AggregateOp"):
            AggregateSpec(op="sum", field="amount")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# AggregateOp enum tests
# ---------------------------------------------------------------------------


class TestAggregateOp:
    def test_all_values_present(self) -> None:
        """All five standard SQL aggregate operations are present."""
        expected = {"count", "sum", "avg", "min", "max"}
        actual = {op.value for op in AggregateOp}
        assert actual == expected

    def test_is_string_enum(self) -> None:
        """AggregateOp values are strings (for JSON serialization)."""
        for op in AggregateOp:
            assert isinstance(op.value, str)
            assert isinstance(op, str)  # str enum

    def test_enum_access_by_value(self) -> None:
        """Can construct AggregateOp from string value."""
        assert AggregateOp("count") == AggregateOp.COUNT
        assert AggregateOp("sum") == AggregateOp.SUM
        assert AggregateOp("avg") == AggregateOp.AVG
        assert AggregateOp("min") == AggregateOp.MIN
        assert AggregateOp("max") == AggregateOp.MAX

    def test_invalid_value_raises(self) -> None:
        """Invalid string value raises ValueError."""
        with pytest.raises(ValueError):
            AggregateOp("GROUP_CONCAT")


# ---------------------------------------------------------------------------
# AggregationResult tests
# ---------------------------------------------------------------------------


class TestAggregationResult:
    def test_to_dict_from_dict_roundtrip(self) -> None:
        """Serialization to dict and back preserves fields."""
        original = AggregationResult(
            data=[{"status": "active", "count": 42}],
            query="SELECT status, COUNT(*) AS count FROM users GROUP BY status",
            params=[],
            row_count=1,
        )
        d = original.to_dict()
        restored = AggregationResult.from_dict(d)
        assert restored.data == original.data
        assert restored.query == original.query
        assert restored.row_count == original.row_count

    def test_to_dict_structure(self) -> None:
        """to_dict returns expected keys (params excluded for serialization)."""
        result = AggregationResult(data=[{"a": 1}], query="SELECT 1", row_count=1)
        d = result.to_dict()
        assert "data" in d
        assert "query" in d
        assert "row_count" in d

    def test_default_values(self) -> None:
        """Default AggregationResult has empty data and zero row_count."""
        result = AggregationResult()
        assert result.data == []
        assert result.query == ""
        assert result.params == []
        assert result.row_count == 0

    def test_from_dict_with_empty_dict(self) -> None:
        """from_dict with empty dict returns defaults."""
        result = AggregationResult.from_dict({})
        assert result.data == []
        assert result.query == ""
        assert result.row_count == 0

    def test_from_dict_rejects_non_dict(self) -> None:
        """from_dict with non-dict raises TypeError."""
        with pytest.raises(TypeError, match="expects a dict"):
            AggregationResult.from_dict("not_a_dict")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# SQL injection security tests
# ---------------------------------------------------------------------------


class TestSQLInjectionPrevention:
    """Verify that all injection vectors are blocked by identifier validation."""

    def test_table_injection_in_count_by(self) -> None:
        """SQL injection via table name in count_by is blocked."""
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            build_count_by("users; DROP TABLE users; --", "status")

    def test_group_by_injection_in_count_by(self) -> None:
        """SQL injection via group_by in count_by is blocked."""
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            build_count_by("users", "status UNION SELECT * FROM passwords")

    def test_filter_column_injection(self) -> None:
        """SQL injection via filter column name is blocked."""
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            build_count_by("users", "status", {"1=1 OR name": "admin"})

    def test_table_injection_in_sum_by(self) -> None:
        """SQL injection via table name in sum_by is blocked."""
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            build_sum_by("orders' OR '1'='1", "amount", "category")

    def test_sum_field_injection(self) -> None:
        """SQL injection via sum_field in sum_by is blocked."""
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            build_sum_by("orders", "amount); DELETE FROM orders; --", "category")

    def test_table_injection_in_aggregate(self) -> None:
        """SQL injection via table name in aggregate is blocked."""
        specs = [AggregateSpec(op=AggregateOp.COUNT, field="*")]
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            build_aggregate("orders; DROP TABLE orders", specs)

    def test_group_by_injection_in_aggregate(self) -> None:
        """SQL injection via group_by in aggregate is blocked."""
        specs = [AggregateSpec(op=AggregateOp.COUNT, field="*")]
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            build_aggregate("orders", specs, group_by="id; --")

    def test_values_are_never_interpolated(self) -> None:
        """Filter values appear in params list, never in the SQL string."""
        malicious_value = "'; DROP TABLE users; --"
        sql, params = build_count_by("orders", "status", {"region": malicious_value})
        # The malicious string must NOT appear in the SQL
        assert malicious_value not in sql
        # It must be in the params list for safe parameterized execution
        assert malicious_value in params
        # SQL uses ? placeholder
        assert "?" in sql
