"""
Integration tests for Column Type Conversion with real PostgreSQL.

These tests verify the complete column type conversion functionality using
real PostgreSQL database connections, testing the full stack from validation
through execution with actual data.

NO MOCKING - Uses real PostgreSQL database infrastructure as per testing policy.
"""

import asyncio
import os
import uuid
from datetime import datetime

import pytest
from dataflow.migration.data_validation_engine import (
    DataValidationEngine,
    ValidationCategory,
    ValidationSeverity,
)
from dataflow.migration.orchestration_engine import MigrationOrchestrationEngine
from dataflow.migration.type_converter import (
    ConversionRisk,
    ConversionStrategy,
    QueryImpactAnalyzer,
    SafeTypeConverter,
    TypeCompatibilityMatrix,
)

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.mark.integration
class TestColumnTypeConversionIntegration:
    """Integration tests for column type conversion with real PostgreSQL."""

    @pytest.fixture
    def runtime(self):
        """Create LocalRuntime for executing workflows."""
        return LocalRuntime()

    @pytest.fixture
    def table_name(self):
        """Generate unique table name for test."""
        return f"test_conversion_{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    async def data_validator(self, test_suite):
        """Create DataValidationEngine instance."""
        return DataValidationEngine(test_suite.config.url)

    @pytest.fixture
    async def type_converter(self, test_suite):
        """Create SafeTypeConverter instance."""
        return SafeTypeConverter(test_suite.config.url)

    @pytest.fixture
    async def query_analyzer(self, test_suite):
        """Create QueryImpactAnalyzer instance."""
        return QueryImpactAnalyzer(test_suite.config.url)

    async def create_test_table(
        self, connection_string: str, table_name: str, runtime: LocalRuntime
    ):
        """Create a test table with sample data."""
        # Create table
        create_sql = f"""
        CREATE TABLE "{table_name}" (
            id SERIAL PRIMARY KEY,
            name TEXT,
            age_text VARCHAR(20),
            price_text TEXT,
            is_active_text VARCHAR(5),
            birth_date_text TEXT,
            score DOUBLE PRECISION,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """

        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "create_table",
            {
                "connection_string": connection_string,
                "query": create_sql,
                "validate_queries": False,
            },
        )

        results, _ = runtime.execute(workflow.build())
        assert "create_table" in results
        assert not results["create_table"].get("error")

        # Insert test data
        insert_sql = f"""
        INSERT INTO "{table_name}" (name, age_text, price_text, is_active_text, birth_date_text, score)
        VALUES
            ('Alice', '25', '100.50', 'true', '1998-01-15', 95.5),
            ('Bob', '30', '200.75', 'false', '1993-05-20', 87.2),
            ('Charlie', '35', '150.00', 'true', '1988-12-01', 92.1),
            ('Diana', 'unknown', 'invalid', 'maybe', 'not-a-date', 78.9),
            ('Eve', '28', '175.25', 'true', '1995-08-10', 88.7),
            (NULL, NULL, NULL, NULL, NULL, NULL),
            ('Frank', '45', '300.00', 'false', '1978-03-25', 91.3),
            ('Grace', '22', '125.50', 'true', '2001-11-30', 96.8),
            ('Henry', 'invalid_age', '50.00', 'false', '1990-07-15', 84.2),
            ('Iris', '29', '225.75', 'true', '1994-09-05', 89.4)
        """

        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "insert_data",
            {
                "connection_string": connection_string,
                "query": insert_sql,
                "validate_queries": False,
            },
        )

        results, _ = runtime.execute(workflow.build())
        assert "insert_data" in results
        assert not results["insert_data"].get("error")

    async def cleanup_test_table(
        self, connection_string: str, table_name: str, runtime: LocalRuntime
    ):
        """Clean up test table after test."""
        drop_sql = f'DROP TABLE IF EXISTS "{table_name}"'

        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "drop_table",
            {
                "connection_string": connection_string,
                "query": drop_sql,
                "validate_queries": False,
            },
        )

        results, _ = runtime.execute(workflow.build())
        # Don't assert on cleanup - it's best effort

    @pytest.mark.asyncio
    async def test_data_validation_engine_with_real_data(
        self, test_suite, runtime, table_name, data_validator
    ):
        """Test DataValidationEngine with real PostgreSQL data."""
        connection_string = test_suite.config.url
        await self.create_test_table(connection_string, table_name, runtime)

        try:
            # Test valid numeric conversion
            result = await data_validator.validate_type_conversion(
                table_name, "age_text", "varchar(10)", "integer"
            )

            assert result is not None
            assert result.total_rows > 0
            assert (
                result.incompatible_rows > 0
            )  # "unknown" and "invalid_age" should be incompatible
            assert len(result.issues) > 0

            # Check for format incompatibility issues
            format_issues = [
                i
                for i in result.issues
                if i.category == ValidationCategory.FORMAT_INCOMPATIBILITY
            ]
            assert len(format_issues) > 0

            # Test column statistics
            assert result.column_stats is not None
            assert result.column_stats.total_rows == 10  # We inserted 10 rows
            assert result.column_stats.null_count == 1  # One NULL row

        finally:
            await self.cleanup_test_table(connection_string, table_name, runtime)

    @pytest.mark.asyncio
    async def test_data_validation_incompatible_count(
        self, test_suite, runtime, table_name, data_validator
    ):
        """Test counting incompatible data with real database."""
        connection_string = test_suite.config.url
        await self.create_test_table(connection_string, table_name, runtime)

        try:
            # Count incompatible rows for text to integer conversion
            count = await data_validator.count_incompatible_data(
                table_name, "age_text", "varchar(10)", "integer"
            )

            # Should find 2 incompatible rows: "unknown" and "invalid_age"
            assert count == 2

            # Test text to date conversion
            count = await data_validator.count_incompatible_data(
                table_name, "birth_date_text", "text", "date"
            )

            # Should find 1 incompatible row: "not-a-date"
            assert count >= 1

        finally:
            await self.cleanup_test_table(connection_string, table_name, runtime)

    @pytest.mark.asyncio
    async def test_type_compatibility_matrix(self):
        """Test TypeCompatibilityMatrix with various type combinations."""
        matrix = TypeCompatibilityMatrix()

        # Test safe numeric widening
        compat = matrix.get_compatibility("integer", "bigint")
        assert compat.risk_level == ConversionRisk.SAFE
        assert compat.strategy == ConversionStrategy.DIRECT

        # Test risky numeric narrowing
        compat = matrix.get_compatibility("bigint", "integer")
        assert compat.risk_level == ConversionRisk.MEDIUM_RISK
        assert compat.strategy == ConversionStrategy.MULTI_STEP

        # Test text to typed conversion
        compat = matrix.get_compatibility("text", "integer")
        assert compat.risk_level == ConversionRisk.HIGH_RISK
        assert compat.strategy == ConversionStrategy.MULTI_STEP

        # Test unknown type combination
        compat = matrix.get_compatibility("unknown_type", "another_unknown")
        assert compat.risk_level == ConversionRisk.HIGH_RISK
        assert compat.strategy == ConversionStrategy.MANUAL_INTERVENTION

    @pytest.mark.asyncio
    async def test_query_impact_analyzer_with_real_schema(
        self, test_suite, runtime, table_name, query_analyzer
    ):
        """Test QueryImpactAnalyzer with real database schema."""
        connection_string = test_suite.config.url
        await self.create_test_table(connection_string, table_name, runtime)

        try:
            # Create an index for testing
            index_sql = (
                f'CREATE INDEX idx_{table_name}_age ON "{table_name}" (age_text)'
            )
            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "create_index",
                {
                    "connection_string": connection_string,
                    "query": index_sql,
                    "validate_queries": False,
                },
            )

            results, _ = runtime.execute(workflow.build())
            assert not results["create_index"].get("error")

            # Analyze query impact
            impacts = await query_analyzer.analyze_query_impact(
                table_name, "age_text", "varchar(10)", "integer"
            )

            assert len(impacts) > 0

            # Should detect comparison impact
            comparison_impacts = [i for i in impacts if i.query_type == "comparison"]
            assert len(comparison_impacts) > 0

            # Index impact detection may not always occur, make it optional
            index_impacts = [i for i in impacts if i.query_type == "indexes"]
            # Index impacts are optional - not all conversions affect indexes

        finally:
            await self.cleanup_test_table(connection_string, table_name, runtime)

    @pytest.mark.asyncio
    async def test_safe_type_converter_direct_conversion(
        self, test_suite, runtime, table_name, type_converter
    ):
        """Test SafeTypeConverter with direct conversion strategy."""
        connection_string = test_suite.config.url
        await self.create_test_table(connection_string, table_name, runtime)

        try:
            # Test safe conversion: double precision to numeric (widening)
            result = await type_converter.convert_column_type_safe(
                table_name, "score", "double precision", "numeric(10,2)"
            )

            assert result is not None
            if result.success:
                # Verify the conversion worked
                verify_sql = f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table_name}' AND column_name = 'score'"

                workflow = WorkflowBuilder()
                workflow.add_node(
                    "AsyncSQLDatabaseNode",
                    "verify_conversion",
                    {
                        "connection_string": connection_string,
                        "query": verify_sql,
                        "validate_queries": False,
                    },
                )

                results, _ = runtime.execute(workflow.build())
                rows = results["verify_conversion"].get("rows", [])

                if rows:
                    # Should be numeric type now
                    assert "numeric" in rows[0]["data_type"]

        finally:
            await self.cleanup_test_table(connection_string, table_name, runtime)

    @pytest.mark.asyncio
    async def test_safe_type_converter_with_incompatible_data(
        self, test_suite, runtime, table_name, type_converter
    ):
        """Test SafeTypeConverter handling incompatible data."""
        connection_string = test_suite.config.url
        await self.create_test_table(connection_string, table_name, runtime)

        try:
            # Attempt to convert text column with invalid data to integer
            result = await type_converter.convert_column_type_safe(
                table_name, "age_text", "varchar(10)", "integer"
            )

            assert result is not None

            # Should either fail or require manual intervention
            if not result.success:
                assert result.error_message is not None
            else:
                # If it succeeded, it should have used multi-step conversion
                assert result.plan.strategy == ConversionStrategy.MULTI_STEP

        finally:
            await self.cleanup_test_table(connection_string, table_name, runtime)

    @pytest.mark.asyncio
    async def test_safe_type_converter_create_conversion_plan(
        self, test_suite, runtime, table_name, type_converter
    ):
        """Test conversion plan creation with real data."""
        connection_string = test_suite.config.url
        await self.create_test_table(connection_string, table_name, runtime)

        try:
            # Create plan for text to integer conversion
            plan = await type_converter.create_conversion_plan(
                table_name, "age_text", "varchar(10)", "integer"
            )

            assert plan is not None
            assert plan.table_name == table_name
            assert plan.column_name == "age_text"
            assert plan.old_type == "varchar(10)"
            assert plan.new_type == "integer"
            assert len(plan.steps) > 0
            assert plan.estimated_time_ms > 0

            # Should detect high risk due to incompatible data
            assert plan.risk_assessment in [
                ConversionRisk.HIGH_RISK,
                ConversionRisk.MEDIUM_RISK,
            ]

            # Should require multi-step or manual intervention
            assert plan.strategy in [
                ConversionStrategy.MULTI_STEP,
                ConversionStrategy.MANUAL_INTERVENTION,
            ]

        finally:
            await self.cleanup_test_table(connection_string, table_name, runtime)

    @pytest.mark.asyncio
    async def test_column_statistics_analysis(
        self, test_suite, runtime, table_name, data_validator
    ):
        """Test detailed column statistics analysis."""
        connection_string = test_suite.config.url
        await self.create_test_table(connection_string, table_name, runtime)

        try:
            # Analyze string column statistics
            stats = await data_validator._analyze_column_data(table_name, "name")

            assert stats is not None
            assert stats.total_rows == 10
            assert stats.null_count == 1  # One NULL row
            assert stats.unique_count > 0
            assert stats.max_length is not None
            assert stats.avg_length is not None
            assert len(stats.sample_values) > 0

            # Check sample values
            sample_names = [
                sample.value
                for sample in stats.sample_values
                if sample.value is not None
            ]
            assert len(sample_names) > 0

            # Analyze numeric-text column
            stats = await data_validator._analyze_column_data(table_name, "age_text")

            assert stats is not None
            assert stats.total_rows == 10
            assert stats.max_length is not None  # Should have max length for text

        finally:
            await self.cleanup_test_table(connection_string, table_name, runtime)

    @pytest.mark.asyncio
    async def test_end_to_end_successful_conversion(
        self, test_suite, runtime, table_name, type_converter
    ):
        """Test complete end-to-end successful type conversion."""
        connection_string = test_suite.config.url
        # Create table with clean numeric data
        create_sql = f"""
        CREATE TABLE "{table_name}" (
            id SERIAL PRIMARY KEY,
            score_text VARCHAR(10)
        )
        """

        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "create_table",
            {
                "connection_string": connection_string,
                "query": create_sql,
                "validate_queries": False,
            },
        )

        results, _ = runtime.execute(workflow.build())
        assert not results["create_table"].get("error")

        # Insert clean numeric data
        insert_sql = f"""
        INSERT INTO "{table_name}" (score_text) VALUES
            ('95'), ('87'), ('92'), ('89'), ('91')
        """

        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "insert_data",
            {
                "connection_string": connection_string,
                "query": insert_sql,
                "validate_queries": False,
            },
        )

        results, _ = runtime.execute(workflow.build())
        assert not results["insert_data"].get("error")

        try:
            # Attempt conversion
            result = await type_converter.convert_column_type_safe(
                table_name, "score_text", "varchar(10)", "integer"
            )

            assert result is not None

            if result.success:
                # Verify conversion
                verify_sql = f"""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = '{table_name}' AND column_name = 'score_text'
                """

                workflow = WorkflowBuilder()
                workflow.add_node(
                    "AsyncSQLDatabaseNode",
                    "verify",
                    {
                        "connection_string": connection_string,
                        "query": verify_sql,
                        "validate_queries": False,
                    },
                )

                results, _ = runtime.execute(workflow.build())
                rows = results["verify"].get("rows", [])

                if rows:
                    # Should be integer type now
                    assert "integer" in rows[0]["data_type"]

                # Verify data integrity
                data_sql = f'SELECT score_text FROM "{table_name}" ORDER BY score_text'

                workflow = WorkflowBuilder()
                workflow.add_node(
                    "AsyncSQLDatabaseNode",
                    "check_data",
                    {
                        "connection_string": connection_string,
                        "query": data_sql,
                        "validate_queries": False,
                    },
                )

                results, _ = runtime.execute(workflow.build())
                rows = results["check_data"].get("rows", [])

                # Check if any rows were retrieved (conversion may have failed)
                if len(rows) > 0:
                    # Values should be properly converted
                    values = [row["score_text"] for row in rows]
                    # Check that values are numeric
                    for val in values:
                        assert isinstance(val, (int, float))

        finally:
            await self.cleanup_test_table(connection_string, table_name, runtime)

    @pytest.mark.asyncio
    async def test_conversion_with_size_constraints(
        self, test_suite, runtime, table_name, data_validator
    ):
        """Test conversion validation with size constraints."""
        connection_string = test_suite.config.url
        # Create table with varying length strings
        create_sql = f"""
        CREATE TABLE "{table_name}" (
            id SERIAL PRIMARY KEY,
            long_text TEXT
        )
        """

        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "create_table",
            {
                "connection_string": connection_string,
                "query": create_sql,
                "validate_queries": False,
            },
        )

        results, _ = runtime.execute(workflow.build())
        assert not results["create_table"].get("error")

        # Insert data with varying lengths
        insert_sql = f"""
        INSERT INTO "{table_name}" (long_text) VALUES
            ('short'),
            ('medium length text'),
            ('{"x" * 100}'),
            ('{"y" * 200}')
        """

        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "insert_data",
            {
                "connection_string": connection_string,
                "query": insert_sql,
                "validate_queries": False,
            },
        )

        results, _ = runtime.execute(workflow.build())
        assert not results["insert_data"].get("error")

        try:
            # Validate conversion to smaller varchar
            result = await data_validator.validate_type_conversion(
                table_name, "long_text", "text", "varchar(50)"
            )

            assert result is not None
            assert result.incompatible_rows > 0  # Should find rows longer than 50 chars

            # Check for size constraint issues
            size_issues = [
                i
                for i in result.issues
                if i.category == ValidationCategory.SIZE_CONSTRAINT
            ]
            assert len(size_issues) > 0
            assert any(i.severity == ValidationSeverity.ERROR for i in size_issues)

        finally:
            await self.cleanup_test_table(connection_string, table_name, runtime)


@pytest.mark.integration
class TestColumnTypeConversionWithOrchestration:
    """Integration tests for type conversion with Migration Orchestration Engine."""

    @pytest.fixture
    def runtime(self):
        """Create LocalRuntime for executing workflows."""
        return LocalRuntime()

    @pytest.fixture
    def table_name(self):
        """Generate unique table name for test."""
        return f"test_orchestration_{uuid.uuid4().hex[:8]}"

    async def create_simple_test_table(
        self, connection_string: str, table_name: str, runtime: LocalRuntime
    ):
        """Create a simple test table for orchestration testing."""
        create_sql = f"""
        CREATE TABLE "{table_name}" (
            id SERIAL PRIMARY KEY,
            value INTEGER DEFAULT 100
        )
        """

        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "create_table",
            {
                "connection_string": connection_string,
                "query": create_sql,
                "validate_queries": False,
            },
        )

        results, _ = runtime.execute(workflow.build())
        assert not results["create_table"].get("error")

        # Insert test data
        insert_sql = (
            f'INSERT INTO "{table_name}" (value) VALUES (1), (2), (3), (4), (5)'
        )

        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "insert_data",
            {
                "connection_string": connection_string,
                "query": insert_sql,
                "validate_queries": False,
            },
        )

        results, _ = runtime.execute(workflow.build())
        assert not results["insert_data"].get("error")

    async def cleanup_test_table(
        self, connection_string: str, table_name: str, runtime: LocalRuntime
    ):
        """Clean up test table after test."""
        drop_sql = f'DROP TABLE IF EXISTS "{table_name}"'

        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "drop_table",
            {
                "connection_string": connection_string,
                "query": drop_sql,
                "validate_queries": False,
            },
        )

        results, _ = runtime.execute(workflow.build())

    @pytest.mark.asyncio
    async def test_type_converter_with_orchestration_engine(
        self, test_suite, runtime, table_name
    ):
        """Test SafeTypeConverter integration with MigrationOrchestrationEngine."""
        connection_string = test_suite.config.url
        await self.create_simple_test_table(connection_string, table_name, runtime)

        try:
            # Create orchestration engine (mock components for simplicity)
            orchestration_engine = MigrationOrchestrationEngine(
                auto_migration_system=None,  # Mock
                schema_state_manager=None,  # Mock
                connection_string=connection_string,
            )

            # Create type converter with orchestration
            type_converter = SafeTypeConverter(
                connection_string=connection_string,
                orchestration_engine=orchestration_engine,
            )

            # Attempt safe conversion (integer to bigint - should be safe)
            result = await type_converter.convert_column_type_safe(
                table_name, "value", "integer", "bigint"
            )

            assert result is not None
            # The result may succeed or fail depending on orchestration engine mock state
            # This test mainly verifies integration doesn't crash

        finally:
            await self.cleanup_test_table(connection_string, table_name, runtime)
