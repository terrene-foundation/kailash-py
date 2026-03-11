#!/usr/bin/env python3
"""
Comprehensive Unit Tests for NOT NULL Column Addition System

Tests the NotNullColumnHandler, DefaultValueStrategyManager, and ConstraintValidator
with various scenarios including edge cases and error conditions.

All tests use SQLite in-memory databases and mocks for isolation.
"""

import asyncio
import unittest.mock as mock
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import pytest
from dataflow.migrations.constraint_validator import (
    CheckConstraint,
    ConstraintValidationResult,
    ConstraintValidator,
    ForeignKeyConstraint,
    TriggerInfo,
    UniqueConstraint,
)
from dataflow.migrations.default_strategies import (
    ConditionalDefaultStrategy,
    DefaultStrategy,
    DefaultValueStrategyManager,
    ForeignKeyDefaultStrategy,
    SequenceDefaultStrategy,
)
from dataflow.migrations.not_null_handler import (
    AdditionExecutionResult,
    AdditionResult,
    ColumnDefinition,
    ComputedDefaultStrategy,
    DefaultValueType,
    FunctionDefaultStrategy,
    NotNullAdditionPlan,
    NotNullColumnHandler,
    StaticDefaultStrategy,
    ValidationResult,
)


def create_mock_connection():
    """Create a mock connection with transaction support."""
    mock_connection = AsyncMock()

    # Create a proper async context manager class
    class MockTransaction:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    # Make transaction() return the context manager directly, not a coroutine
    mock_connection.transaction = Mock(return_value=MockTransaction())

    return mock_connection


class TestColumnDefinition:
    """Test ColumnDefinition data class."""

    def test_column_definition_creation(self):
        """Test basic column definition creation."""
        column = ColumnDefinition(
            name="test_column",
            data_type="VARCHAR(255)",
            nullable=False,
            default_value="test_default",
            default_type=DefaultValueType.STATIC,
        )

        assert column.name == "test_column"
        assert column.data_type == "VARCHAR(255)"
        assert not column.nullable
        assert column.default_value == "test_default"
        assert column.default_type == DefaultValueType.STATIC
        assert column.check_constraints == []

    def test_column_definition_with_constraints(self):
        """Test column definition with check constraints."""
        column = ColumnDefinition(
            name="age",
            data_type="INTEGER",
            nullable=False,
            default_value=0,
            check_constraints=["age >= 0", "age <= 150"],
        )

        assert len(column.check_constraints) == 2
        assert "age >= 0" in column.check_constraints
        assert "age <= 150" in column.check_constraints

    def test_column_definition_defaults(self):
        """Test column definition default values."""
        column = ColumnDefinition(name="simple", data_type="TEXT")

        assert column.nullable is False
        assert column.default_value is None
        assert column.default_type == DefaultValueType.STATIC
        assert column.default_expression is None
        assert column.foreign_key_reference is None
        assert column.check_constraints == []
        assert not column.unique
        assert not column.indexed


class TestStaticDefaultStrategy:
    """Test StaticDefaultStrategy implementation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.strategy = StaticDefaultStrategy()

    def test_static_string_default(self):
        """Test static string default value generation."""
        column = ColumnDefinition(
            name="status", data_type="VARCHAR(50)", default_value="active"
        )

        result = self.strategy.generate_default_expression(column)
        assert result == "'active'"

    def test_static_integer_default(self):
        """Test static integer default value generation."""
        column = ColumnDefinition(name="count", data_type="INTEGER", default_value=0)

        result = self.strategy.generate_default_expression(column)
        assert result == "0"

    def test_static_boolean_default(self):
        """Test static boolean default value generation."""
        column = ColumnDefinition(
            name="active", data_type="BOOLEAN", default_value=True
        )

        result = self.strategy.generate_default_expression(column)
        assert result == "TRUE"

    def test_static_float_default(self):
        """Test static float default value generation."""
        column = ColumnDefinition(
            name="price", data_type="DECIMAL(10,2)", default_value=99.99
        )

        result = self.strategy.generate_default_expression(column)
        assert result == "99.99"

    def test_static_datetime_default(self):
        """Test static datetime default value generation."""
        test_datetime = datetime(2025, 1, 1, 12, 0, 0)
        column = ColumnDefinition(
            name="created_at", data_type="TIMESTAMP", default_value=test_datetime
        )

        result = self.strategy.generate_default_expression(column)
        assert result == "'2025-01-01T12:00:00'"

    def test_static_default_missing_value(self):
        """Test static default with missing value."""
        column = ColumnDefinition(
            name="test", data_type="VARCHAR(50)", default_value=None
        )

        with pytest.raises(
            ValueError, match="Static default strategy requires a default_value"
        ):
            self.strategy.generate_default_expression(column)

    def test_validate_against_constraints_success(self):
        """Test constraint validation success."""
        column = ColumnDefinition(
            name="status", data_type="VARCHAR(50)", default_value="active"
        )

        constraints = [
            {
                "constraint_type": "CHECK",
                "constraint_definition": "status IN ('active', 'inactive')",
            }
        ]

        result = self.strategy.validate_against_constraints(column, constraints)
        assert result.is_safe is True
        assert len(result.issues) == 0
        assert len(result.warnings) == 1  # Manual validation warning

    def test_validate_type_compatibility_integer(self):
        """Test type compatibility validation for integers."""
        column = ColumnDefinition(
            name="count", data_type="INTEGER", default_value="not_a_number"
        )

        constraints = []
        result = self.strategy.validate_against_constraints(column, constraints)
        assert result.is_safe is False
        assert len(result.issues) == 1
        assert "not compatible with integer type" in result.issues[0]

    def test_estimate_performance_small_table(self):
        """Test performance estimation for small table."""
        result = self.strategy.estimate_performance_impact(
            "test_table", 1000, ColumnDefinition("test", "TEXT")
        )

        assert result["estimated_seconds"] < 1.0
        assert result["strategy"] == "single_ddl"
        assert result["batch_required"] is False

    def test_estimate_performance_large_table(self):
        """Test performance estimation for large table."""
        result = self.strategy.estimate_performance_impact(
            "test_table", 2000000, ColumnDefinition("test", "TEXT")
        )

        assert result["estimated_seconds"] > 1.0
        assert result["strategy"] == "single_ddl"
        assert result["batch_required"] is True


class TestComputedDefaultStrategy:
    """Test ComputedDefaultStrategy implementation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.strategy = ComputedDefaultStrategy()

    def test_computed_default_generation(self):
        """Test computed default expression generation."""
        column = ColumnDefinition(
            name="priority",
            data_type="INTEGER",
            default_expression="CASE WHEN amount > 1000 THEN 1 ELSE 2 END",
        )

        result = self.strategy.generate_default_expression(column)
        assert result == "CASE WHEN amount > 1000 THEN 1 ELSE 2 END"

    def test_computed_default_missing_expression(self):
        """Test computed default with missing expression."""
        column = ColumnDefinition(
            name="test", data_type="INTEGER", default_expression=None
        )

        with pytest.raises(
            ValueError, match="Computed default strategy requires default_expression"
        ):
            self.strategy.generate_default_expression(column)

    def test_validate_against_constraints_invalid_expression(self):
        """Test validation with invalid SQL expression."""
        column = ColumnDefinition(
            name="test",
            data_type="INTEGER",
            default_expression="DROP TABLE users",  # Dangerous expression
        )

        result = self.strategy.validate_against_constraints(column, [])
        assert result.is_safe is False
        assert len(result.issues) == 1
        assert "Invalid SQL expression" in result.issues[0]

    def test_validate_against_constraints_valid_expression(self):
        """Test validation with valid SQL expression."""
        column = ColumnDefinition(
            name="status_code",
            data_type="INTEGER",
            default_expression="CASE WHEN active THEN 1 ELSE 0 END",
        )

        result = self.strategy.validate_against_constraints(column, [])
        assert result.is_safe is True
        assert len(result.warnings) == 1
        assert "careful testing" in result.warnings[0]

    def test_estimate_performance_impact(self):
        """Test performance impact estimation."""
        column = ColumnDefinition("test", "INTEGER")
        result = self.strategy.estimate_performance_impact("test_table", 100000, column)

        # Updated to match realistic performance estimates after optimization
        assert result["estimated_seconds"] > 0.5  # More realistic expectation
        assert result["strategy"] == "batched_update"
        assert result["batch_required"] is True
        assert result["requires_table_scan"] is True


class TestFunctionDefaultStrategy:
    """Test FunctionDefaultStrategy implementation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.strategy = FunctionDefaultStrategy()

    def test_function_current_timestamp(self):
        """Test CURRENT_TIMESTAMP function default."""
        column = ColumnDefinition(
            name="created_at",
            data_type="TIMESTAMP",
            default_expression="CURRENT_TIMESTAMP",
        )

        result = self.strategy.generate_default_expression(column)
        assert result == "CURRENT_TIMESTAMP"

    def test_function_now(self):
        """Test NOW() function default."""
        column = ColumnDefinition(
            name="created_at", data_type="TIMESTAMP", default_expression="NOW()"
        )

        result = self.strategy.generate_default_expression(column)
        assert result == "CURRENT_TIMESTAMP"

    def test_function_uuid_generation(self):
        """Test UUID generation function."""
        column = ColumnDefinition(
            name="id", data_type="UUID", default_expression="GENERATE_UUID"
        )

        result = self.strategy.generate_default_expression(column)
        assert result == "gen_random_uuid()"

    def test_function_missing_expression(self):
        """Test function strategy with missing expression."""
        column = ColumnDefinition(
            name="test", data_type="TIMESTAMP", default_expression=None
        )

        with pytest.raises(
            ValueError, match="Function default strategy requires default_expression"
        ):
            self.strategy.generate_default_expression(column)

    def test_validate_timestamp_compatibility(self):
        """Test validation of timestamp function compatibility."""
        column = ColumnDefinition(
            name="created_at",
            data_type="TIMESTAMP",
            default_expression="CURRENT_TIMESTAMP",
        )

        result = self.strategy.validate_against_constraints(column, [])
        assert result.is_safe is True
        assert len(result.issues) == 0

    def test_validate_incompatible_function_type(self):
        """Test validation of incompatible function and data type."""
        column = ColumnDefinition(
            name="count", data_type="INTEGER", default_expression="CURRENT_TIMESTAMP"
        )

        result = self.strategy.validate_against_constraints(column, [])
        assert result.is_safe is False
        assert len(result.issues) == 1
        assert "incompatible with type" in result.issues[0]

    def test_estimate_performance_fast_function(self):
        """Test performance estimation for fast functions."""
        column = ColumnDefinition("test", "TIMESTAMP")
        result = self.strategy.estimate_performance_impact("test_table", 100000, column)

        assert result["estimated_seconds"] < 1.0
        assert result["strategy"] == "single_ddl"
        assert result["batch_required"] is False


class TestDefaultValueStrategyManager:
    """Test DefaultValueStrategyManager."""

    def setup_method(self):
        """Set up test fixtures."""
        self.manager = DefaultValueStrategyManager()

    def test_manager_initialization(self):
        """Test strategy manager initialization."""
        strategies = self.manager.list_available_strategies()

        assert DefaultValueType.STATIC in strategies
        assert DefaultValueType.COMPUTED in strategies
        assert DefaultValueType.FUNCTION in strategies
        assert DefaultValueType.CONDITIONAL in strategies
        assert DefaultValueType.SEQUENCE in strategies
        assert DefaultValueType.FOREIGN_KEY in strategies

    def test_get_strategy_static(self):
        """Test getting static strategy."""
        strategy = self.manager.get_strategy(DefaultValueType.STATIC)
        assert isinstance(strategy, StaticDefaultStrategy)

    def test_get_strategy_invalid(self):
        """Test getting invalid strategy type."""
        with pytest.raises(ValueError, match="Unknown strategy type"):
            # Create a fake enum value
            fake_type = "INVALID_TYPE"
            self.manager.get_strategy(fake_type)

    def test_static_default_creation_string(self):
        """Test static default strategy creation for string."""
        strategy = self.manager.static_default("active")

        assert strategy.strategy_type == DefaultValueType.STATIC
        assert strategy.sql_expression == "'active'"
        assert not strategy.requires_batching

    def test_static_default_creation_integer(self):
        """Test static default strategy creation for integer."""
        strategy = self.manager.static_default(42)

        assert strategy.strategy_type == DefaultValueType.STATIC
        assert strategy.sql_expression == "42"

    def test_static_default_creation_boolean(self):
        """Test static default strategy creation for boolean."""
        strategy = self.manager.static_default(True)

        assert strategy.strategy_type == DefaultValueType.STATIC
        assert strategy.sql_expression == "TRUE"

    def test_static_default_creation_datetime(self):
        """Test static default strategy creation for datetime."""
        test_dt = datetime(2025, 1, 1, 12, 0, 0)
        strategy = self.manager.static_default(test_dt)

        assert strategy.strategy_type == DefaultValueType.STATIC
        assert strategy.sql_expression == "'2025-01-01T12:00:00'"

    def test_computed_default_creation(self):
        """Test computed default strategy creation."""
        expression = "CASE WHEN amount > 100 THEN 'high' ELSE 'low' END"
        strategy = self.manager.computed_default(expression)

        assert strategy.strategy_type == DefaultValueType.COMPUTED
        assert strategy.sql_expression == expression
        assert strategy.requires_batching is True

    def test_computed_default_invalid_expression(self):
        """Test computed default with invalid expression."""
        with pytest.raises(ValueError, match="Invalid or unsafe SQL expression"):
            self.manager.computed_default("DROP TABLE users")

    def test_function_default_creation_no_args(self):
        """Test function default creation without arguments."""
        strategy = self.manager.function_default("CURRENT_TIMESTAMP")

        assert strategy.strategy_type == DefaultValueType.FUNCTION
        assert strategy.sql_expression == "CURRENT_TIMESTAMP"

    def test_function_default_creation_with_args(self):
        """Test function default creation with arguments."""
        strategy = self.manager.function_default(
            "SUBSTRING", ["column_name", "1", "10"]
        )

        assert strategy.strategy_type == DefaultValueType.FUNCTION
        assert strategy.sql_expression == "SUBSTRING(column_name, 1, 10)"

    def test_function_default_invalid_name(self):
        """Test function default with invalid name."""
        with pytest.raises(ValueError, match="Invalid or unsafe function name"):
            self.manager.function_default("DROP_TABLE")

    def test_conditional_default_creation(self):
        """Test conditional default strategy creation."""
        conditions = [("amount > 1000", "premium"), ("amount > 100", "standard")]
        strategy = self.manager.conditional_default(conditions)

        assert strategy.strategy_type == DefaultValueType.CONDITIONAL
        assert "CASE" in strategy.sql_expression
        assert "WHEN amount > 1000 THEN 'premium'" in strategy.sql_expression
        assert strategy.requires_batching is True

    def test_conditional_default_empty_conditions(self):
        """Test conditional default with empty conditions."""
        with pytest.raises(ValueError, match="requires at least one condition"):
            self.manager.conditional_default([])

    def test_conditional_default_unsafe_condition(self):
        """Test conditional default with unsafe condition."""
        conditions = [("amount > 100 AND (SELECT COUNT(*) FROM users) > 0", "value")]
        with pytest.raises(ValueError, match="Unsafe condition"):
            self.manager.conditional_default(conditions)

    def test_sequence_default_creation(self):
        """Test sequence default strategy creation."""
        strategy = self.manager.sequence_default("user_id_seq")

        assert strategy.strategy_type == DefaultValueType.SEQUENCE
        assert strategy.sql_expression == "nextval('user_id_seq')"

    def test_sequence_default_empty_name(self):
        """Test sequence default with empty name."""
        with pytest.raises(ValueError, match="Sequence name is required"):
            self.manager.sequence_default("")

    def test_foreign_key_default_static(self):
        """Test foreign key default with static value."""
        strategy = self.manager.foreign_key_default("categories", "id", static_value=1)

        assert strategy.strategy_type == DefaultValueType.FOREIGN_KEY
        assert strategy.sql_expression == "1"
        assert not strategy.requires_batching

    def test_foreign_key_default_lookup(self):
        """Test foreign key default with lookup condition."""
        strategy = self.manager.foreign_key_default(
            "categories", "id", lookup_condition="name = 'default'"
        )

        assert strategy.strategy_type == DefaultValueType.FOREIGN_KEY
        assert (
            "SELECT id FROM categories WHERE name = 'default'"
            in strategy.sql_expression
        )
        assert strategy.requires_batching is True

    def test_foreign_key_default_both_params(self):
        """Test foreign key default with both static and lookup."""
        with pytest.raises(ValueError, match="Cannot specify both"):
            self.manager.foreign_key_default(
                "categories", "id", lookup_condition="name = 'default'", static_value=1
            )

    def test_foreign_key_default_neither_param(self):
        """Test foreign key default with neither static nor lookup."""
        with pytest.raises(ValueError, match="Must specify either"):
            self.manager.foreign_key_default("categories", "id")

    def test_recommend_strategy_small_table_integer(self):
        """Test strategy recommendation for small table with integer column."""
        column = ColumnDefinition("count", "INTEGER", unique=False)
        table_info = {"row_count": 1000}

        strategy_type, reason = self.manager.recommend_strategy(column, table_info)

        assert strategy_type == DefaultValueType.STATIC
        assert "static default" in reason.lower()

    def test_recommend_strategy_unique_integer(self):
        """Test strategy recommendation for unique integer column."""
        column = ColumnDefinition("id", "INTEGER", unique=True)
        table_info = {"row_count": 10000}

        strategy_type, reason = self.manager.recommend_strategy(column, table_info)

        assert strategy_type == DefaultValueType.SEQUENCE
        assert "sequence" in reason.lower()

    def test_recommend_strategy_timestamp(self):
        """Test strategy recommendation for timestamp column."""
        column = ColumnDefinition("created_at", "TIMESTAMP")
        table_info = {"row_count": 5000}

        strategy_type, reason = self.manager.recommend_strategy(column, table_info)

        assert strategy_type == DefaultValueType.FUNCTION
        assert "CURRENT_TIMESTAMP" in reason

    def test_recommend_strategy_foreign_key(self):
        """Test strategy recommendation for foreign key column."""
        column = ColumnDefinition(
            "category_id", "INTEGER", foreign_key_reference="categories.id"
        )
        table_info = {"row_count": 2000}

        strategy_type, reason = self.manager.recommend_strategy(column, table_info)

        assert strategy_type == DefaultValueType.FOREIGN_KEY
        assert "referential integrity" in reason.lower()


class TestConstraintValidator:
    """Test ConstraintValidator functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = ConstraintValidator()
        self.mock_connection = create_mock_connection()

    @pytest.mark.asyncio
    async def test_validate_foreign_key_references_valid(self):
        """Test foreign key validation with valid reference."""
        # Mock connection to return True for existence check
        self.mock_connection.fetchval.return_value = True

        fk_constraint = ForeignKeyConstraint(
            name="fk_test",
            source_columns=["category_id"],
            target_table="categories",
            target_columns=["id"],
        )

        result = await self.validator.validate_foreign_key_references(
            1, fk_constraint, self.mock_connection
        )

        assert result is True
        self.mock_connection.fetchval.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_foreign_key_references_invalid(self):
        """Test foreign key validation with invalid reference."""
        # Mock connection to return False for existence check
        self.mock_connection.fetchval.return_value = False

        fk_constraint = ForeignKeyConstraint(
            name="fk_test",
            source_columns=["category_id"],
            target_table="categories",
            target_columns=["id"],
        )

        result = await self.validator.validate_foreign_key_references(
            999, fk_constraint, self.mock_connection
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_validate_foreign_key_references_null(self):
        """Test foreign key validation with NULL value."""
        fk_constraint = ForeignKeyConstraint(
            name="fk_test",
            source_columns=["category_id"],
            target_table="categories",
            target_columns=["id"],
        )

        result = await self.validator.validate_foreign_key_references(
            None, fk_constraint, self.mock_connection
        )

        # NULL should always be valid for foreign keys
        assert result is True
        # Should not make database call for NULL
        self.mock_connection.fetchval.assert_not_called()

    def test_extract_columns_from_check_clause(self):
        """Test column extraction from check constraint clause."""
        check_clause = "(age >= 0 AND age <= 150 AND status IN ('active', 'inactive'))"

        columns = self.validator._extract_columns_from_check_clause(check_clause)

        assert "age" in columns
        assert "status" in columns
        assert len(columns) >= 2

    def test_extract_function_name_from_action(self):
        """Test function name extraction from trigger action."""
        action_statement = "EXECUTE FUNCTION update_modified_time()"

        function_name = self.validator._extract_function_name(action_statement)

        assert function_name == "update_modified_time"

    def test_extract_function_name_fallback(self):
        """Test function name extraction fallback."""
        action_statement = "SOME_UNKNOWN_FORMAT"

        function_name = self.validator._extract_function_name(action_statement)

        assert function_name == "SOME_UNKNOWN_FORMAT"

    def test_trigger_might_be_affected_insert(self):
        """Test trigger affect detection for INSERT trigger."""
        trigger = TriggerInfo(
            name="test_trigger",
            event="INSERT",
            timing="BEFORE",
            function_name="log_changes",
        )

        result = self.validator._trigger_might_be_affected(trigger, "new_column")
        assert result is True

    def test_trigger_might_be_affected_update(self):
        """Test trigger affect detection for UPDATE trigger."""
        trigger = TriggerInfo(
            name="test_trigger",
            event="UPDATE",
            timing="AFTER",
            function_name="audit_changes",
        )

        result = self.validator._trigger_might_be_affected(trigger, "new_column")
        assert result is True

    def test_trigger_might_be_affected_delete_only(self):
        """Test trigger affect detection for DELETE-only trigger."""
        trigger = TriggerInfo(
            name="test_trigger",
            event="DELETE",
            timing="BEFORE",
            function_name="cleanup_data",
        )

        result = self.validator._trigger_might_be_affected(trigger, "new_column")
        # DELETE triggers typically not affected by new columns
        assert result is False


class TestNotNullColumnHandler:
    """Test NotNullColumnHandler main functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = NotNullColumnHandler()
        self.mock_connection = create_mock_connection()

        # Mock the _get_connection method to return our mock
        self.handler._get_connection = AsyncMock(return_value=self.mock_connection)

    @pytest.mark.asyncio
    async def test_plan_not_null_addition_basic(self):
        """Test basic NOT NULL addition planning."""
        # Mock table analysis
        self.mock_connection.fetchval.return_value = 1000  # row count
        self.mock_connection.fetch.return_value = []  # no constraints

        column = ColumnDefinition(
            name="status",
            data_type="VARCHAR(50)",
            default_value="active",
            default_type=DefaultValueType.STATIC,
        )

        with patch.object(self.handler, "_analyze_table_structure") as mock_analyze:
            mock_analyze.return_value = {"row_count": 1000, "constraints": []}

            with patch.object(self.handler, "_generate_rollback_plan") as mock_rollback:
                mock_rollback.return_value = {"strategy": "drop_column"}

                plan = await self.handler.plan_not_null_addition("test_table", column)

                assert plan.table_name == "test_table"
                assert plan.column.name == "status"
                assert plan.execution_strategy == "single_ddl"
                assert plan.affected_rows == 1000
                assert plan.rollback_plan is not None

    @pytest.mark.asyncio
    async def test_validate_addition_safety_success(self):
        """Test addition safety validation success."""
        column = ColumnDefinition(
            name="priority",
            data_type="INTEGER",
            default_value=1,
            default_type=DefaultValueType.STATIC,
        )

        plan = NotNullAdditionPlan(
            table_name="test_table",
            column=column,
            execution_strategy="single_ddl",
            estimated_duration=2.0,
        )

        # Mock all validation methods to return success
        with (
            patch.object(self.handler, "_validate_table_access", return_value=True),
            patch.object(self.handler, "_check_column_exists", return_value=False),
            patch.object(self.handler, "_get_table_constraints", return_value=[]),
            patch.object(
                self.handler, "_check_concurrent_operations", return_value=False
            ),
        ):

            result = await self.handler.validate_addition_safety(plan)

            assert result.is_safe is True
            assert len(result.issues) == 0

    @pytest.mark.asyncio
    async def test_validate_addition_safety_column_exists(self):
        """Test addition safety validation when column already exists."""
        column = ColumnDefinition(
            name="existing_column",
            data_type="VARCHAR(100)",
            default_value="test",
            default_type=DefaultValueType.STATIC,
        )

        plan = NotNullAdditionPlan(
            table_name="test_table", column=column, execution_strategy="single_ddl"
        )

        # Mock column exists
        with (
            patch.object(self.handler, "_validate_table_access", return_value=True),
            patch.object(self.handler, "_check_column_exists", return_value=True),
            patch.object(self.handler, "_get_table_constraints", return_value=[]),
        ):

            result = await self.handler.validate_addition_safety(plan)

            assert result.is_safe is False
            assert len(result.issues) == 1
            assert "already exists" in result.issues[0]

    @pytest.mark.asyncio
    async def test_execute_single_ddl_addition(self):
        """Test single DDL execution strategy."""
        column = ColumnDefinition(
            name="status",
            data_type="VARCHAR(50)",
            default_value="active",
            default_type=DefaultValueType.STATIC,
        )

        plan = NotNullAdditionPlan(
            table_name="test_table", column=column, execution_strategy="single_ddl"
        )

        # Mock successful execution
        self.mock_connection.fetchval.return_value = 1000  # affected rows

        result = await self.handler._execute_single_ddl_addition(
            plan, self.mock_connection
        )

        assert result.result == AdditionResult.SUCCESS
        assert result.affected_rows == 1000

        # Verify SQL was executed
        self.mock_connection.execute.assert_called_once()
        call_args = self.mock_connection.execute.call_args[0][0]
        assert "ALTER TABLE test_table" in call_args
        assert "ADD COLUMN status VARCHAR(50)" in call_args
        assert "NOT NULL DEFAULT 'active'" in call_args


class TestIntegrationScenarios:
    """Test integration scenarios combining multiple components."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = NotNullColumnHandler()
        self.strategy_manager = DefaultValueStrategyManager()
        self.validator = ConstraintValidator()

    @pytest.mark.asyncio
    async def test_end_to_end_static_default_scenario(self):
        """Test complete end-to-end scenario with static default."""
        # Create a realistic scenario
        column = ColumnDefinition(
            name="status",
            data_type="VARCHAR(20)",
            default_value="pending",
            default_type=DefaultValueType.STATIC,
        )

        # Test strategy creation
        strategy = self.strategy_manager.static_default("pending")
        assert strategy.strategy_type == DefaultValueType.STATIC
        assert strategy.sql_expression == "'pending'"

        # Test constraint validation (mocked)
        with (
            patch.object(self.validator, "_get_connection"),
            patch.object(
                self.validator, "_get_all_constraints_info"
            ) as mock_constraints,
        ):

            mock_constraints.return_value = {
                "foreign_keys": [],
                "check_constraints": [],
                "unique_constraints": [],
                "triggers": [],
            }

            validation = await self.validator.validate_all_constraints(
                "orders", column, "pending"
            )

            assert validation.is_safe is True

    def test_strategy_recommendation_integration(self):
        """Test strategy recommendation with different scenarios."""
        # Test cases with different column types and requirements
        test_cases = [
            {
                "column": ColumnDefinition("id", "INTEGER", unique=True),
                "table_info": {"row_count": 50000},
                "expected": DefaultValueType.SEQUENCE,
            },
            {
                "column": ColumnDefinition("created_at", "TIMESTAMP"),
                "table_info": {"row_count": 10000},
                "expected": DefaultValueType.FUNCTION,
            },
            {
                "column": ColumnDefinition(
                    "category_id", "INTEGER", foreign_key_reference="categories.id"
                ),
                "table_info": {"row_count": 5000},
                "expected": DefaultValueType.FOREIGN_KEY,
            },
            {
                "column": ColumnDefinition("name", "VARCHAR(100)"),
                "table_info": {"row_count": 1000},
                "expected": DefaultValueType.STATIC,
            },
        ]

        for case in test_cases:
            strategy_type, reason = self.strategy_manager.recommend_strategy(
                case["column"], case["table_info"]
            )
            assert (
                strategy_type == case["expected"]
            ), f"Failed for {case['column'].name}: got {strategy_type}, expected {case['expected']}"

    def test_validation_result_aggregation(self):
        """Test aggregation of validation results from multiple components."""
        issues = []
        warnings = []

        # Simulate results from different validators
        static_validation = ValidationResult(
            is_safe=True, issues=[], warnings=["Static default performance OK"]
        )
        constraint_validation = ValidationResult(
            is_safe=True, issues=[], warnings=["Check constraints need manual review"]
        )
        fk_validation = ValidationResult(
            is_safe=False, issues=["Foreign key reference invalid"], warnings=[]
        )

        # Aggregate results
        all_validations = [static_validation, constraint_validation, fk_validation]
        for validation in all_validations:
            issues.extend(validation.issues)
            warnings.extend(validation.warnings)

        overall_safe = all(v.is_safe for v in all_validations)

        assert not overall_safe  # Should be unsafe due to FK issue
        assert len(issues) == 1
        assert len(warnings) == 2
        assert "Foreign key reference invalid" in issues
        assert any("performance" in w for w in warnings)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
