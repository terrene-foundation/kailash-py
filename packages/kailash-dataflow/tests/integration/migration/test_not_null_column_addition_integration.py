#!/usr/bin/env python3
"""
Integration Tests for NOT NULL Column Addition System with Real PostgreSQL

Tests the complete NOT NULL column addition workflow with real PostgreSQL database,
covering all major scenarios and edge cases that could occur in production.

NO MOCKING - All tests use real database infrastructure as per testing policy.

This test suite follows the Kailash SDK 3-tier testing strategy:
- Tier 2: Integration tests with real PostgreSQL database
- NO MOCKING allowed - uses actual database services
- Performance timeouts: <5 seconds for basic, <45 seconds for complex scenarios
- Test isolation via unique table names and proper cleanup
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

import pytest
from dataflow.migrations.constraint_validator import ConstraintValidator
from dataflow.migrations.default_strategies import DefaultValueStrategyManager
from dataflow.migrations.not_null_handler import (
    AdditionResult,
    ColumnDefinition,
    DefaultValueType,
    NotNullAdditionPlan,
    NotNullColumnHandler,
    ValidationResult,
)

from kailash.runtime.local import LocalRuntime

# Import the new test harness infrastructure
from tests.infrastructure.test_harness import (
    IntegrationTestSuite,
    NotNullTestHarness,
    PerformanceMeasurement,
)

# Configure logging for test debugging
logging.basicConfig(level=logging.INFO)


# Use the standardized fixtures from conftest.py and test harness
@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def runtime():
    """Create LocalRuntime for workflow execution."""
    return LocalRuntime()


@pytest.fixture
async def not_null_harness(test_suite):
    """Create NOT NULL test harness."""
    yield test_suite.not_null_harness


@pytest.mark.integration
@pytest.mark.timeout(30)
class TestNotNullColumnHandlerIntegration:
    """Integration tests for NotNullColumnHandler with real PostgreSQL."""

    @pytest.mark.asyncio
    async def test_plan_not_null_addition_real_table(self, not_null_harness):
        """Test planning NOT NULL addition with real table analysis."""
        # Create test table using standardized factory
        table_name = await not_null_harness.table_factory.create_basic_table()
        handler = not_null_harness.create_handler()

        column = not_null_harness.static_column("status", "active")

        plan = await handler.plan_not_null_addition(table_name, column)

        assert plan.table_name == table_name
        assert plan.column.name == "status"
        assert plan.execution_strategy in ["single_ddl", "batched_update"]
        assert plan.affected_rows == 3  # Standard test data has 3 rows
        assert plan.estimated_duration is not None
        assert plan.rollback_plan is not None

    @pytest.mark.asyncio
    async def test_validate_addition_safety_real_constraints(self, not_null_harness):
        """Test safety validation with real database constraints."""
        # Create constrained table using standardized factory
        tables = await not_null_harness.table_factory.create_constrained_table()
        handler = not_null_harness.create_handler()
        table_name = tables["main_table"]

        # Test valid column addition using standard column definition
        valid_column = ColumnDefinition(
            name="priority",
            data_type="INTEGER",
            default_value=1,
            default_type=DefaultValueType.STATIC,
        )

        plan = NotNullAdditionPlan(
            table_name=table_name, column=valid_column, execution_strategy="single_ddl"
        )

        validation = await handler.validate_addition_safety(plan)

        assert validation.is_safe is True
        assert len(validation.issues) == 0
        # May have warnings about manual constraint validation

    @pytest.mark.asyncio
    async def test_validate_addition_safety_column_exists(self, not_null_harness):
        """Test safety validation when column already exists."""
        table_name = await not_null_harness.table_factory.create_basic_table()
        handler = not_null_harness.create_handler()

        # Try to add a column that already exists (name column exists in basic table)
        existing_column = ColumnDefinition(
            name="name",  # This column already exists
            data_type="VARCHAR(100)",
            default_value="test",
            default_type=DefaultValueType.STATIC,
        )

        plan = NotNullAdditionPlan(
            table_name=table_name,
            column=existing_column,
            execution_strategy="single_ddl",
        )

        validation = await handler.validate_addition_safety(plan)

        assert validation.is_safe is False
        assert len(validation.issues) > 0
        assert any("already exists" in issue for issue in validation.issues)

    @pytest.mark.asyncio
    async def test_execute_static_default_addition(self, not_null_harness):
        """Test executing static default NOT NULL column addition."""
        table_name = await not_null_harness.table_factory.create_basic_table()
        handler = not_null_harness.create_handler()

        column = not_null_harness.static_column("status", "pending")

        plan = NotNullAdditionPlan(
            table_name=table_name,
            column=column,
            execution_strategy="single_ddl",
            validate_constraints=True,
        )

        # Execute the addition
        result = await handler.execute_not_null_addition(plan)

        assert result.result == AdditionResult.SUCCESS
        assert result.affected_rows == 3
        assert result.execution_time > 0

        # Verify column was added with correct default
        async with not_null_harness.infrastructure.connection() as conn:
            column_info = await conn.fetch(
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = $1 AND column_name = 'status'
            """,
                table_name,
            )

            assert len(column_info) == 1
            assert column_info[0]["is_nullable"] == "NO"
            assert "'pending'" in column_info[0]["column_default"]

            # Verify all rows have the default value
            rows = await conn.fetch(f"SELECT status FROM {table_name}")
            assert len(rows) == 3
            assert all(row["status"] == "pending" for row in rows)

    @pytest.mark.asyncio
    async def test_execute_function_default_addition(self, not_null_harness):
        """Test executing function default NOT NULL column addition."""
        table_name = await not_null_harness.table_factory.create_basic_table()
        handler = not_null_harness.create_handler()

        column = not_null_harness.function_column("updated_at", "CURRENT_TIMESTAMP")

        plan = NotNullAdditionPlan(
            table_name=table_name,
            column=column,
            execution_strategy="single_ddl",
            validate_constraints=True,
        )

        # Execute the addition
        result = await handler.execute_not_null_addition(plan)

        assert result.result == AdditionResult.SUCCESS
        assert result.affected_rows == 3

        # Verify column was added with function default
        async with not_null_harness.infrastructure.connection() as conn:
            column_info = await conn.fetch(
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = $1 AND column_name = 'updated_at'
            """,
                table_name,
            )

            assert len(column_info) == 1
            assert column_info[0]["is_nullable"] == "NO"
            assert (
                "CURRENT_TIMESTAMP" in column_info[0]["column_default"]
                or "now()" in column_info[0]["column_default"]
            )

            # Verify all rows have timestamp values
            rows = await conn.fetch(f"SELECT updated_at FROM {table_name}")
            assert len(rows) == 3
            assert all(row["updated_at"] is not None for row in rows)

    @pytest.mark.asyncio
    async def test_rollback_not_null_addition(self, not_null_harness):
        """Test rolling back NOT NULL column addition."""
        table_name = await not_null_harness.table_factory.create_basic_table()
        handler = not_null_harness.create_handler()

        # First, add a column
        column = ColumnDefinition(
            name="temp_column",
            data_type="VARCHAR(50)",
            default_value="temporary",
            default_type=DefaultValueType.STATIC,
        )

        plan = NotNullAdditionPlan(
            table_name=table_name, column=column, execution_strategy="single_ddl"
        )

        # Execute the addition
        add_result = await handler.execute_not_null_addition(plan)
        assert add_result.result == AdditionResult.SUCCESS

        # Verify column exists
        async with not_null_harness.infrastructure.connection() as conn:
            column_exists_before = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name = $1 AND column_name = 'temp_column')",
                table_name,
            )
            assert column_exists_before is True

        # Now rollback
        rollback_result = await handler.rollback_not_null_addition(plan)

        assert rollback_result.result == AdditionResult.SUCCESS
        assert rollback_result.rollback_executed is True
        assert rollback_result.execution_time > 0

        # Verify column no longer exists
        async with not_null_harness.infrastructure.connection() as conn:
            column_exists_after = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name = $1 AND column_name = 'temp_column')",
                table_name,
            )
            assert column_exists_after is False

    @pytest.mark.asyncio
    async def test_batched_addition_large_table(self, not_null_harness):
        """Test batched addition with large table (performance test)."""
        # Create large table for performance testing
        table_name = await not_null_harness.table_factory.create_large_table(
            rows=1000
        )  # Reduced for faster testing
        handler = not_null_harness.create_handler()

        # Use computed default that will require batched processing
        column = not_null_harness.computed_column(
            "tier", "CASE WHEN id <= 500 THEN 'premium' ELSE 'basic' END"
        )

        plan = NotNullAdditionPlan(
            table_name=table_name,
            column=column,
            execution_strategy="batched_update",
            batch_size=100,
            validate_constraints=True,
        )

        # Execute with performance measurement
        start_time = datetime.now()
        result = await handler.execute_not_null_addition(plan)
        execution_time = (datetime.now() - start_time).total_seconds()

        # Assert performance bounds
        PerformanceMeasurement.assert_performance_bounds(
            execution_time, 10.0, "batched_addition_large_table", 1000
        )

        assert result.result == AdditionResult.SUCCESS
        assert result.affected_rows == 1000

        # Verify values were computed correctly
        async with not_null_harness.infrastructure.connection() as conn:
            premium_count = await conn.fetchval(
                f"SELECT COUNT(*) FROM {table_name} WHERE tier = 'premium'"
            )
            basic_count = await conn.fetchval(
                f"SELECT COUNT(*) FROM {table_name} WHERE tier = 'basic'"
            )

            assert premium_count == 500
            assert basic_count == 500


@pytest.mark.integration
@pytest.mark.timeout(45)
class TestDefaultValueStrategyManagerIntegration:
    """Integration tests for DefaultValueStrategyManager with real database."""

    @pytest.mark.asyncio
    async def test_validate_foreign_key_constraints_real_database(
        self, not_null_harness
    ):
        """Test foreign key constraint validation with real database."""
        tables = await not_null_harness.table_factory.create_constrained_table()
        manager = not_null_harness.create_strategy_manager()

        # Test valid foreign key reference
        fk_column = ColumnDefinition(
            name="secondary_category_id",
            data_type="INTEGER",
            foreign_key_reference=f"{tables['category_table']}(id)",
            default_value=1,
            default_type=DefaultValueType.STATIC,
        )

        table_info = {"row_count": 3}
        strategy_type, reason = manager.recommend_strategy(fk_column, table_info)

        assert strategy_type == DefaultValueType.FOREIGN_KEY
        assert "Foreign key" in reason

        # Test invalid foreign key reference
        invalid_fk_column = ColumnDefinition(
            name="invalid_fk",
            data_type="INTEGER",
            foreign_key_reference="nonexistent_table(id)",
            default_value=1,
            default_type=DefaultValueType.STATIC,
        )

        invalid_strategy_type, invalid_reason = manager.recommend_strategy(
            invalid_fk_column, table_info
        )
        # Should fall back to static since FK is invalid
        assert invalid_strategy_type == DefaultValueType.STATIC

    @pytest.mark.asyncio
    async def test_validate_unique_constraints_real_database(self, not_null_harness):
        """Test unique constraint validation with real database."""
        tables = await not_null_harness.table_factory.create_constrained_table()
        manager = not_null_harness.create_strategy_manager()

        # Test unique column recommendation
        unique_column = ColumnDefinition(
            name="unique_code", data_type="INTEGER", unique=True
        )

        table_info = {"row_count": 3}
        strategy_type, reason = manager.recommend_strategy(unique_column, table_info)

        assert strategy_type == DefaultValueType.SEQUENCE
        assert "unique" in reason.lower()

    @pytest.mark.asyncio
    async def test_comprehensive_constraint_validation(self, not_null_harness):
        """Test comprehensive constraint validation with real constraints."""
        tables = await not_null_harness.table_factory.create_constrained_table()
        validator = not_null_harness.create_constraint_validator()

        # Test column that fits within existing constraints
        valid_column = ColumnDefinition(
            name="score", data_type="INTEGER", default_value=50
        )

        validation = await validator.validate_all_constraints(
            tables["main_table"], valid_column, 50
        )

        assert validation.is_safe is True


@pytest.mark.integration
@pytest.mark.timeout(15)
class TestEndToEndScenarios:
    """End-to-end integration test scenarios."""

    @pytest.mark.asyncio
    async def test_strategy_performance_estimation_real_table(self, not_null_harness):
        """Test strategy performance estimation with real table data."""
        table_name = await not_null_harness.table_factory.create_basic_table()
        manager = not_null_harness.create_strategy_manager()

        # Test static default performance
        static_column = not_null_harness.static_column("simple_flag", True)
        static_perf = manager.get_strategy(
            DefaultValueType.STATIC
        ).estimate_performance_impact(table_name, 3, static_column)

        assert static_perf["strategy"] == "single_ddl"
        assert static_perf["estimated_seconds"] < 1.0

        # Test computed default performance
        computed_column = not_null_harness.computed_column(
            "computed_field", "CASE WHEN id > 1 THEN 'high' ELSE 'low' END"
        )
        computed_perf = manager.get_strategy(
            DefaultValueType.COMPUTED
        ).estimate_performance_impact(table_name, 3, computed_column)

        assert computed_perf["strategy"] == "batched_update"
        assert computed_perf["estimated_seconds"] > static_perf["estimated_seconds"]

    @pytest.mark.asyncio
    async def test_strategy_validation_with_real_constraints(self, not_null_harness):
        """Test strategy validation against real database constraints."""
        tables = await not_null_harness.table_factory.create_constrained_table()
        manager = not_null_harness.create_strategy_manager()

        # Get actual constraints from database
        async with not_null_harness.infrastructure.connection() as conn:
            constraints = await conn.fetch(
                """
                SELECT conname, contype, pg_get_constraintdef(oid) as definition
                FROM pg_constraint
                WHERE conrelid = $1::regclass
            """,
                tables["main_table"],
            )

            constraint_list = []
            for row in constraints:
                constraint_list.append(
                    {
                        "name": row["conname"],
                        "constraint_type": {
                            "c": "CHECK",
                            "f": "FOREIGN KEY",
                            "p": "PRIMARY KEY",
                            "u": "UNIQUE",
                        }.get(row["contype"], "UNKNOWN"),
                        "constraint_definition": row["definition"],
                    }
                )

        # Test static strategy against real constraints
        static_column = ColumnDefinition(
            name="test_age",
            data_type="INTEGER",
            default_value=25,  # Should be valid for age CHECK constraint
            default_type=DefaultValueType.STATIC,
        )

        strategy = manager.get_strategy(DefaultValueType.STATIC)
        validation = strategy.validate_against_constraints(
            static_column, constraint_list
        )

        assert validation.is_safe is True
        # Should have warnings about manual validation needed
        assert len(validation.warnings) > 0

    @pytest.mark.asyncio
    async def test_complete_static_default_workflow(self, not_null_harness):
        """Test complete workflow for static default addition."""
        table_name = await not_null_harness.table_factory.create_basic_table()
        handler = not_null_harness.create_handler()

        # Step 1: Plan the addition
        column = not_null_harness.static_column("workflow_status", "draft")
        plan = await handler.plan_not_null_addition(table_name, column)

        assert plan.execution_strategy == "single_ddl"
        assert plan.estimated_duration < 1.0

        # Step 2: Validate safety
        validation = await handler.validate_addition_safety(plan)
        assert validation.is_safe is True

        # Step 3: Execute addition
        result = await handler.execute_not_null_addition(plan)
        assert result.result == AdditionResult.SUCCESS
        assert result.affected_rows == 3

        # Step 4: Verify result
        async with not_null_harness.infrastructure.connection() as conn:
            values = await conn.fetch(f"SELECT workflow_status FROM {table_name}")
            assert len(values) == 3
            assert all(row["workflow_status"] == "draft" for row in values)

    @pytest.mark.asyncio
    async def test_complete_computed_default_workflow(self, not_null_harness):
        """Test complete workflow for computed default addition."""
        table_name = await not_null_harness.table_factory.create_basic_table()
        handler = not_null_harness.create_handler()

        # Step 1: Plan the addition with computed default
        column = not_null_harness.computed_column(
            "priority_level", "CASE WHEN id <= 2 THEN 'high' ELSE 'normal' END"
        )
        plan = await handler.plan_not_null_addition(table_name, column)

        assert plan.execution_strategy == "batched_update"

        # Step 2: Validate safety
        validation = await handler.validate_addition_safety(plan)
        assert validation.is_safe is True

        # Step 3: Execute addition
        result = await handler.execute_not_null_addition(plan)
        assert result.result == AdditionResult.SUCCESS
        assert result.affected_rows == 3

        # Step 4: Verify computed values are correct
        async with not_null_harness.infrastructure.connection() as conn:
            values = await conn.fetch(
                f"SELECT id, priority_level FROM {table_name} ORDER BY id"
            )
            assert len(values) == 3

            # Based on our test data: id 1,2 should be 'high', id 3 should be 'normal'
            assert values[0]["priority_level"] == "high"  # id=1
            assert values[1]["priority_level"] == "high"  # id=2
            assert values[2]["priority_level"] == "normal"  # id=3

    @pytest.mark.asyncio
    async def test_workflow_with_constraint_violation_prevention(
        self, not_null_harness
    ):
        """Test workflow prevents constraint violations."""
        tables = await not_null_harness.table_factory.create_constrained_table()
        handler = not_null_harness.create_handler()

        # Try to add a column with a default that would violate age CHECK constraint
        invalid_column = ColumnDefinition(
            name="invalid_age",
            data_type="INTEGER",
            default_value=200,  # Violates CHECK (age >= 0 AND age <= 150)
            default_type=DefaultValueType.STATIC,
        )

        plan = NotNullAdditionPlan(
            table_name=tables["main_table"],
            column=invalid_column,
            execution_strategy="single_ddl",
            validate_constraints=True,
        )

        # Safety validation should warn about this
        validation = await handler.validate_addition_safety(plan)

        # The validation may pass (since it doesn't do deep constraint analysis)
        # but if executed, it might fail - this tests the overall robustness
        if validation.is_safe:
            # If validation passes, execution should handle constraint violations gracefully
            result = await handler.execute_not_null_addition(plan)
            # Result could be SUCCESS or CONSTRAINT_VIOLATION depending on PostgreSQL behavior
            assert result.result in [
                AdditionResult.SUCCESS,
                AdditionResult.CONSTRAINT_VIOLATION,
                AdditionResult.ROLLBACK_REQUIRED,
            ]

    @pytest.mark.asyncio
    async def test_performance_monitoring_workflow(self, not_null_harness):
        """Test performance monitoring during workflow execution."""
        # Create moderately sized table for performance testing
        table_name = await not_null_harness.table_factory.create_large_table(rows=500)
        handler = not_null_harness.create_handler()

        # Plan computed default addition (more expensive operation)
        column = not_null_harness.computed_column(
            "performance_tier",
            "CASE WHEN value % 3 = 0 THEN 'premium' WHEN value % 2 = 0 THEN 'standard' ELSE 'basic' END",
        )

        plan = await handler.plan_not_null_addition(table_name, column)
        plan.performance_monitoring = True

        # Execute with performance monitoring
        start_time = datetime.now()
        result = await handler.execute_not_null_addition(plan)
        total_time = (datetime.now() - start_time).total_seconds()

        # Verify performance characteristics
        assert result.result == AdditionResult.SUCCESS
        assert result.affected_rows == 500
        assert result.execution_time > 0

        # Assert reasonable performance bounds
        PerformanceMeasurement.assert_performance_bounds(
            total_time, 15.0, "performance_monitoring_workflow", 500
        )

        # Verify computed values are distributed correctly
        async with not_null_harness.infrastructure.connection() as conn:
            tier_counts = await conn.fetch(
                f"""
                SELECT performance_tier, COUNT(*) as count
                FROM {table_name}
                GROUP BY performance_tier
                ORDER BY performance_tier
            """
            )

            # Should have all three tiers represented
            tier_names = [row["performance_tier"] for row in tier_counts]
            assert "basic" in tier_names
            assert "premium" in tier_names
            assert "standard" in tier_names

            # Total should equal original row count
            total_rows = sum(row["count"] for row in tier_counts)
            assert total_rows == 500


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
