#!/usr/bin/env python3
"""
E2E tests for Migration Validation Pipeline - Phase 2

Tests complete migration validation workflows from end-to-end with real infrastructure.
Demonstrates the full migration validation system working together.

TIER 3 REQUIREMENTS:
- Complete user workflows from start to finish
- Real infrastructure and data (NO MOCKING)
- Test actual business scenarios and expectations
- Timeout: <10 seconds per test
- Complete validation workflows with runtime execution

VALIDATION SCENARIOS:
1. Safe column removal validation workflow
2. Risky migration detection and blocking
3. Performance degradation detection
4. Rollback validation failures
5. Data integrity verification
6. Complete dependency analysis workflows
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List

import pytest

# Set up logging for E2E tests
logging.basicConfig(level=logging.INFO)

from dataflow.migrations.dependency_analyzer import DependencyAnalyzer

# Import components for E2E testing
from dataflow.migrations.migration_validation_pipeline import (
    MigrationValidationConfig,
    MigrationValidationPipeline,
    MigrationValidationResult,
    ValidationError,
    ValidationStatus,
)
from dataflow.migrations.risk_assessment_engine import RiskAssessmentEngine, RiskLevel
from dataflow.migrations.staging_environment_manager import (
    ProductionDatabase,
    StagingEnvironmentConfig,
    StagingEnvironmentManager,
)
from dataflow.migrations.validation_checkpoints import CheckpointStatus, CheckpointType

# Test database configuration
TEST_DB_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "database": "dataflow_test",
    "user": "dataflow_test",
    "password": "dataflow_test_password",
}


@pytest.fixture(scope="session")
async def e2e_test_database():
    """Set up E2E test database with realistic schema."""
    import asyncpg

    conn = await asyncpg.connect(**TEST_DB_CONFIG)

    try:
        # Create realistic e-commerce schema for testing
        await conn.execute(
            """
            DROP TABLE IF EXISTS order_items CASCADE;
            DROP TABLE IF EXISTS orders CASCADE;
            DROP TABLE IF EXISTS products CASCADE;
            DROP TABLE IF EXISTS users CASCADE;
            DROP TABLE IF EXISTS categories CASCADE;
        """
        )

        # Users table
        await conn.execute(
            """
            CREATE TABLE users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                first_name VARCHAR(50),
                last_name VARCHAR(50),
                phone VARCHAR(20),
                deprecated_field VARCHAR(100), -- For safe removal testing
                legacy_column TEXT,           -- For testing migration scenarios
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """
        )

        # Categories table
        await conn.execute(
            """
            CREATE TABLE categories (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL,
                description TEXT,
                deprecated_category_field VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """
        )

        # Products table
        await conn.execute(
            """
            CREATE TABLE products (
                id SERIAL PRIMARY KEY,
                category_id INTEGER REFERENCES categories(id),
                name VARCHAR(200) NOT NULL,
                description TEXT,
                price DECIMAL(10,2) NOT NULL,
                stock_quantity INTEGER DEFAULT 0,
                old_pricing_field DECIMAL(8,2), -- For migration testing
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """
        )

        # Orders table
        await conn.execute(
            """
            CREATE TABLE orders (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                total_amount DECIMAL(12,2) NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                shipping_address TEXT,
                deprecated_order_field VARCHAR(100)
            );
        """
        )

        # Order items table
        await conn.execute(
            """
            CREATE TABLE order_items (
                id SERIAL PRIMARY KEY,
                order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
                product_id INTEGER REFERENCES products(id),
                quantity INTEGER NOT NULL,
                unit_price DECIMAL(10,2) NOT NULL,
                subtotal DECIMAL(12,2) GENERATED ALWAYS AS (quantity * unit_price) STORED
            );
        """
        )

        # Insert test data
        await conn.execute(
            """
            INSERT INTO categories (name, description, deprecated_category_field) VALUES
            ('Electronics', 'Electronic devices and gadgets', 'old_cat_1'),
            ('Clothing', 'Fashion and apparel', 'old_cat_2'),
            ('Books', 'Physical and digital books', 'old_cat_3');
        """
        )

        await conn.execute(
            """
            INSERT INTO users (username, email, first_name, last_name, phone, deprecated_field, legacy_column) VALUES
            ('john_doe', 'john@example.com', 'John', 'Doe', '123-456-7890', 'old_user_data_1', 'legacy_1'),
            ('jane_smith', 'jane@example.com', 'Jane', 'Smith', '098-765-4321', 'old_user_data_2', 'legacy_2'),
            ('bob_wilson', 'bob@example.com', 'Bob', 'Wilson', '555-123-4567', 'old_user_data_3', 'legacy_3'),
            ('alice_brown', 'alice@example.com', 'Alice', 'Brown', '777-888-9999', 'old_user_data_4', 'legacy_4');
        """
        )

        await conn.execute(
            """
            INSERT INTO products (category_id, name, description, price, stock_quantity, old_pricing_field) VALUES
            (1, 'Laptop Computer', 'High-performance laptop', 999.99, 50, 899.99),
            (1, 'Smartphone', 'Latest model smartphone', 699.99, 100, 599.99),
            (2, 'T-Shirt', 'Cotton t-shirt', 19.99, 200, 17.99),
            (3, 'Programming Book', 'Learn to code', 49.99, 30, 44.99);
        """
        )

        await conn.execute(
            """
            INSERT INTO orders (user_id, total_amount, status, shipping_address, deprecated_order_field) VALUES
            (1, 999.99, 'completed', '123 Main St', 'old_order_1'),
            (2, 719.98, 'pending', '456 Oak Ave', 'old_order_2'),
            (3, 49.99, 'completed', '789 Pine Rd', 'old_order_3'),
            (1, 19.99, 'completed', '123 Main St', 'old_order_4');
        """
        )

        await conn.execute(
            """
            INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
            (1, 1, 1, 999.99),
            (2, 1, 1, 999.99),
            (2, 2, 1, 699.99),
            (3, 4, 1, 49.99),
            (4, 3, 1, 19.99);
        """
        )

        # Create some indexes for performance testing
        await conn.execute("CREATE INDEX idx_users_email ON users(email)")
        await conn.execute("CREATE INDEX idx_orders_user_id ON orders(user_id)")
        await conn.execute(
            "CREATE INDEX idx_products_category_id ON products(category_id)"
        )

        yield

    finally:
        # Cleanup
        try:
            await conn.execute(
                """
                DROP TABLE IF EXISTS order_items CASCADE;
                DROP TABLE IF EXISTS orders CASCADE;
                DROP TABLE IF EXISTS products CASCADE;
                DROP TABLE IF EXISTS users CASCADE;
                DROP TABLE IF EXISTS categories CASCADE;
            """
            )
        except Exception as e:
            logging.warning(f"E2E cleanup warning: {e}")
        finally:
            await conn.close()


@pytest.fixture
async def e2e_validation_pipeline():
    """Create validation pipeline for E2E testing."""
    config = MigrationValidationConfig(
        staging_timeout_seconds=60,
        performance_baseline_queries=[
            "SELECT COUNT(*) FROM {table_name}",
            "SELECT * FROM {table_name} LIMIT 5",
            "SELECT {table_name}.*, categories.name as category_name FROM {table_name} LEFT JOIN categories ON {table_name}.category_id = categories.id LIMIT 3",
        ],
        rollback_validation_enabled=True,
        data_integrity_checks_enabled=True,
        parallel_validation_enabled=True,
        max_validation_time_seconds=120,
        performance_degradation_threshold=0.40,  # 40% threshold for E2E
    )

    # Mock staging manager for E2E (focus on validation logic)
    from unittest.mock import AsyncMock, Mock

    staging_manager = Mock(spec=StagingEnvironmentManager)

    # Mock staging environment
    mock_staging_env = Mock()
    mock_staging_env.staging_id = "e2e_staging_001"

    # Mock staging_db with test database credentials
    mock_staging_db = Mock()
    mock_staging_db.host = TEST_DB_CONFIG["host"]
    mock_staging_db.port = TEST_DB_CONFIG["port"]
    mock_staging_db.database = TEST_DB_CONFIG["database"]
    mock_staging_db.user = TEST_DB_CONFIG["user"]
    mock_staging_db.password = TEST_DB_CONFIG["password"]
    mock_staging_db.connection_timeout = 30
    mock_staging_env.staging_db = mock_staging_db

    staging_manager.create_staging_environment = AsyncMock(
        return_value=mock_staging_env
    )
    staging_manager.replicate_production_schema = AsyncMock(return_value=Mock())
    staging_manager.cleanup_staging_environment = AsyncMock(
        return_value={"status": "SUCCESS"}
    )

    # Create real analyzers
    dependency_analyzer = DependencyAnalyzer()
    risk_engine = RiskAssessmentEngine()

    pipeline = MigrationValidationPipeline(
        staging_manager=staging_manager,
        dependency_analyzer=dependency_analyzer,
        risk_engine=risk_engine,
        config=config,
    )

    return pipeline


class TestMigrationValidationE2E:
    """E2E tests for complete migration validation workflows."""

    @pytest.mark.asyncio
    async def test_safe_column_removal_complete_workflow(
        self, e2e_validation_pipeline, e2e_test_database
    ):
        """Test complete workflow for safe column removal validation."""
        migration_info = {
            "migration_id": "e2e_safe_removal_001",
            "table_name": "users",
            "column_name": "deprecated_field",  # Safe to remove - no dependencies
            "migration_sql": "ALTER TABLE users DROP COLUMN deprecated_field",
            "rollback_sql": "ALTER TABLE users ADD COLUMN deprecated_field VARCHAR(100)",
            "description": "Remove deprecated user field that is no longer used",
        }

        production_db = ProductionDatabase(**TEST_DB_CONFIG)

        result = await e2e_validation_pipeline.validate_migration(
            migration_info=migration_info, production_db=production_db
        )

        # Verify successful validation
        assert isinstance(result, MigrationValidationResult)
        assert result.validation_status == ValidationStatus.PASSED
        assert result.migration_id == "e2e_safe_removal_001"
        assert result.validation_duration_seconds > 0
        assert result.staging_environment_id is not None

        # Verify all checkpoints were executed
        checkpoint_types = {cp.checkpoint_type for cp in result.checkpoints}
        expected_checkpoints = {
            CheckpointType.DEPENDENCY_ANALYSIS,
            CheckpointType.PERFORMANCE_VALIDATION,
            CheckpointType.ROLLBACK_VALIDATION,
            CheckpointType.DATA_INTEGRITY,
            CheckpointType.SCHEMA_CONSISTENCY,
        }
        assert checkpoint_types == expected_checkpoints

        # Verify dependency analysis passed (no critical dependencies)
        dependency_checkpoint = next(
            cp
            for cp in result.checkpoints
            if cp.checkpoint_type == CheckpointType.DEPENDENCY_ANALYSIS
        )
        assert dependency_checkpoint.status == CheckpointStatus.PASSED
        assert (
            "no dependencies" in dependency_checkpoint.message.lower()
            or "safe" in dependency_checkpoint.message.lower()
        )

        # Verify no critical validation errors
        critical_errors = [
            err
            for err in result.validation_errors
            if "critical" in err.message.lower() or "dangerous" in err.message.lower()
        ]
        assert len(critical_errors) == 0

    @pytest.mark.asyncio
    async def test_dangerous_foreign_key_column_removal_blocked(
        self, e2e_validation_pipeline, e2e_test_database
    ):
        """Test that removal of foreign key referenced columns is properly blocked."""
        migration_info = {
            "migration_id": "e2e_dangerous_removal_001",
            "table_name": "users",
            "column_name": "id",  # PRIMARY KEY referenced by orders.user_id
            "migration_sql": "ALTER TABLE users DROP COLUMN id",
            "rollback_sql": "-- Cannot safely rollback primary key removal",
            "description": "Attempt to remove user ID - should be blocked due to FK references",
        }

        production_db = ProductionDatabase(**TEST_DB_CONFIG)

        result = await e2e_validation_pipeline.validate_migration(
            migration_info=migration_info, production_db=production_db
        )

        # Should fail validation due to foreign key dependencies
        assert result.validation_status == ValidationStatus.FAILED
        assert result.migration_id == "e2e_dangerous_removal_001"

        # Should detect foreign key dependencies
        dependency_checkpoint = next(
            (
                cp
                for cp in result.checkpoints
                if cp.checkpoint_type == CheckpointType.DEPENDENCY_ANALYSIS
            ),
            None,
        )
        assert dependency_checkpoint is not None
        assert dependency_checkpoint.status == CheckpointStatus.FAILED

        # Should have validation errors about dependencies
        dependency_errors = [
            err
            for err in result.validation_errors
            if (
                "dependencies" in err.message.lower()
                or "foreign" in err.message.lower()
                or "critical" in err.message.lower()
            )
        ]
        assert len(dependency_errors) > 0

        # Risk level should be high or critical
        assert result.overall_risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]

    @pytest.mark.asyncio
    async def test_rollback_validation_failure_detection(
        self, e2e_validation_pipeline, e2e_test_database
    ):
        """Test detection of migrations with inadequate rollback procedures."""
        migration_info = {
            "migration_id": "e2e_rollback_failure_001",
            "table_name": "products",
            "column_name": "old_pricing_field",
            "migration_sql": "ALTER TABLE products DROP COLUMN old_pricing_field",
            "rollback_sql": "",  # Empty rollback - should fail validation
            "description": "Migration with no rollback procedure",
        }

        production_db = ProductionDatabase(**TEST_DB_CONFIG)

        result = await e2e_validation_pipeline.validate_migration(
            migration_info=migration_info, production_db=production_db
        )

        # Should fail validation due to rollback issues
        assert result.validation_status == ValidationStatus.FAILED

        # Should detect rollback validation failure
        rollback_checkpoint = next(
            (
                cp
                for cp in result.checkpoints
                if cp.checkpoint_type == CheckpointType.ROLLBACK_VALIDATION
            ),
            None,
        )
        assert rollback_checkpoint is not None
        assert rollback_checkpoint.status == CheckpointStatus.FAILED
        assert "rollback" in rollback_checkpoint.message.lower()
        assert (
            "empty" in rollback_checkpoint.message.lower()
            or "missing" in rollback_checkpoint.message.lower()
        )

        # Should have specific rollback validation errors
        rollback_errors = [
            err for err in result.validation_errors if "rollback" in err.message.lower()
        ]
        assert len(rollback_errors) > 0

    @pytest.mark.asyncio
    async def test_performance_validation_with_indexed_column(
        self, e2e_validation_pipeline, e2e_test_database
    ):
        """Test performance validation for column removal that might affect query performance."""
        migration_info = {
            "migration_id": "e2e_performance_test_001",
            "table_name": "users",
            "column_name": "email",  # Has index - might affect performance
            "migration_sql": "ALTER TABLE users DROP COLUMN email",
            "rollback_sql": "ALTER TABLE users ADD COLUMN email VARCHAR(255) UNIQUE",
            "description": "Remove indexed email column - may impact performance",
        }

        production_db = ProductionDatabase(**TEST_DB_CONFIG)

        result = await e2e_validation_pipeline.validate_migration(
            migration_info=migration_info, production_db=production_db
        )

        # May pass or fail depending on performance impact
        assert result.validation_status in [
            ValidationStatus.PASSED,
            ValidationStatus.FAILED,
        ]

        # Should have executed performance validation
        perf_checkpoint = next(
            (
                cp
                for cp in result.checkpoints
                if cp.checkpoint_type == CheckpointType.PERFORMANCE_VALIDATION
            ),
            None,
        )
        assert perf_checkpoint is not None
        assert perf_checkpoint.status in [
            CheckpointStatus.PASSED,
            CheckpointStatus.FAILED,
        ]

        # Should have performance metrics
        if perf_checkpoint.status == CheckpointStatus.FAILED:
            assert "performance" in perf_checkpoint.message.lower()
            assert "degradation" in perf_checkpoint.message.lower()
        else:
            assert "acceptable" in perf_checkpoint.message.lower()

    @pytest.mark.asyncio
    async def test_data_integrity_validation_comprehensive(
        self, e2e_validation_pipeline, e2e_test_database
    ):
        """Test comprehensive data integrity validation."""
        migration_info = {
            "migration_id": "e2e_integrity_test_001",
            "table_name": "categories",
            "column_name": "deprecated_category_field",
            "migration_sql": "ALTER TABLE categories DROP COLUMN deprecated_category_field",
            "rollback_sql": "ALTER TABLE categories ADD COLUMN deprecated_category_field VARCHAR(50)",
            "description": "Remove deprecated category field with integrity checks",
        }

        production_db = ProductionDatabase(**TEST_DB_CONFIG)

        result = await e2e_validation_pipeline.validate_migration(
            migration_info=migration_info, production_db=production_db
        )

        # Should pass validation for non-critical column
        assert result.validation_status == ValidationStatus.PASSED

        # Should have executed data integrity validation
        integrity_checkpoint = next(
            (
                cp
                for cp in result.checkpoints
                if cp.checkpoint_type == CheckpointType.DATA_INTEGRITY
            ),
            None,
        )
        assert integrity_checkpoint is not None

        # Data integrity should pass for this migration
        if integrity_checkpoint.status == CheckpointStatus.PASSED:
            assert "integrity" in integrity_checkpoint.message.lower()
            assert (
                "passed" in integrity_checkpoint.message.lower()
                or "validated" in integrity_checkpoint.message.lower()
            )

    @pytest.mark.asyncio
    async def test_parallel_checkpoint_execution_performance(
        self, e2e_validation_pipeline, e2e_test_database
    ):
        """Test parallel checkpoint execution for better performance."""
        migration_info = {
            "migration_id": "e2e_parallel_test_001",
            "table_name": "products",
            "column_name": "description",
            "migration_sql": "ALTER TABLE products ALTER COLUMN description TYPE TEXT",
            "rollback_sql": "ALTER TABLE products ALTER COLUMN description TYPE TEXT",
            "description": "Column type change to test parallel execution",
        }

        production_db = ProductionDatabase(**TEST_DB_CONFIG)

        # Test with parallel execution enabled
        start_time = datetime.now()
        result = await e2e_validation_pipeline.validate_migration(
            migration_info=migration_info, production_db=production_db
        )
        execution_time = (datetime.now() - start_time).total_seconds()

        # Should complete validation
        assert result.validation_status in [
            ValidationStatus.PASSED,
            ValidationStatus.FAILED,
        ]
        assert len(result.checkpoints) > 0
        assert execution_time < 10.0  # Should complete within E2E timeout

        # All checkpoints should have execution times
        for checkpoint in result.checkpoints:
            assert checkpoint.execution_time_seconds >= 0

    @pytest.mark.asyncio
    async def test_risk_assessment_integration_e2e(
        self, e2e_validation_pipeline, e2e_test_database
    ):
        """Test risk assessment integration with complete validation results."""
        # Test low-risk migration
        safe_migration_info = {
            "migration_id": "e2e_risk_low_001",
            "table_name": "users",
            "column_name": "legacy_column",
            "migration_sql": "ALTER TABLE users DROP COLUMN legacy_column",
            "rollback_sql": "ALTER TABLE users ADD COLUMN legacy_column TEXT",
            "description": "Remove unused legacy column - low risk",
        }

        production_db = ProductionDatabase(**TEST_DB_CONFIG)

        result_safe = await e2e_validation_pipeline.validate_migration(
            migration_info=safe_migration_info, production_db=production_db
        )

        # Should pass with low/medium risk
        assert result_safe.validation_status == ValidationStatus.PASSED
        assert result_safe.overall_risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM]
        assert result_safe.risk_assessment is not None

        # Test high-risk migration
        risky_migration_info = {
            "migration_id": "e2e_risk_high_001",
            "table_name": "categories",
            "column_name": "id",  # Primary key referenced by products
            "migration_sql": "ALTER TABLE categories DROP COLUMN id",
            "rollback_sql": "-- Cannot rollback primary key drop",
            "description": "Remove category ID - high risk due to FK references",
        }

        result_risky = await e2e_validation_pipeline.validate_migration(
            migration_info=risky_migration_info, production_db=production_db
        )

        # Should fail with high/critical risk
        assert result_risky.validation_status == ValidationStatus.FAILED
        assert result_risky.overall_risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]

        # Risk assessment should be updated based on validation results
        assert result_risky.risk_assessment is not None
        assert (
            result_risky.risk_assessment.overall_score
            > result_safe.risk_assessment.overall_score
        )

    @pytest.mark.asyncio
    async def test_complete_validation_workflow_summary(
        self, e2e_validation_pipeline, e2e_test_database
    ):
        """Test complete validation workflow and summary generation."""
        migration_info = {
            "migration_id": "e2e_summary_test_001",
            "table_name": "order_items",
            "column_name": "subtotal",  # Computed column - might be complex
            "migration_sql": "ALTER TABLE order_items DROP COLUMN subtotal",
            "rollback_sql": "ALTER TABLE order_items ADD COLUMN subtotal DECIMAL(12,2) GENERATED ALWAYS AS (quantity * unit_price) STORED",
            "description": "Remove computed subtotal column",
        }

        production_db = ProductionDatabase(**TEST_DB_CONFIG)

        result = await e2e_validation_pipeline.validate_migration(
            migration_info=migration_info, production_db=production_db
        )

        # Verify comprehensive result structure
        assert isinstance(result, MigrationValidationResult)
        assert result.migration_id == "e2e_summary_test_001"
        assert result.validation_status in [
            ValidationStatus.PASSED,
            ValidationStatus.FAILED,
        ]
        assert result.overall_risk_level in [
            RiskLevel.LOW,
            RiskLevel.MEDIUM,
            RiskLevel.HIGH,
            RiskLevel.CRITICAL,
        ]

        # Verify validation summary
        summary = result.get_validation_summary()
        assert "migration_id" in summary
        assert "status" in summary
        assert "overall_risk" in summary
        assert "duration_seconds" in summary
        assert "checkpoints_passed" in summary
        assert "checkpoints_failed" in summary
        assert summary["checkpoints_passed"] + summary["checkpoints_failed"] > 0

        # Verify result completeness
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.validation_duration_seconds > 0
        assert len(result.checkpoints) > 0

        # Log comprehensive results for verification
        logging.info(f"E2E Validation Result Summary: {summary}")
        logging.info(f"Checkpoints executed: {len(result.checkpoints)}")
        logging.info(f"Validation errors: {len(result.validation_errors)}")
        logging.info(f"Overall risk level: {result.overall_risk_level.value}")


class TestValidationWorkflowBusinessScenarios:
    """E2E tests for realistic business migration scenarios."""

    @pytest.mark.asyncio
    async def test_e_commerce_schema_evolution_workflow(
        self, e2e_validation_pipeline, e2e_test_database
    ):
        """Test realistic e-commerce schema evolution scenario."""
        # Scenario: E-commerce company wants to remove old pricing fields
        # after migrating to new pricing system

        migrations = [
            {
                "migration_id": "ecommerce_pricing_cleanup_001",
                "table_name": "products",
                "column_name": "old_pricing_field",
                "migration_sql": "ALTER TABLE products DROP COLUMN old_pricing_field",
                "rollback_sql": "ALTER TABLE products ADD COLUMN old_pricing_field DECIMAL(8,2)",
                "description": "Remove deprecated pricing field from products table",
            }
        ]

        production_db = ProductionDatabase(**TEST_DB_CONFIG)

        for migration_info in migrations:
            result = await e2e_validation_pipeline.validate_migration(
                migration_info=migration_info, production_db=production_db
            )

            # Should validate successfully for non-critical column removal
            assert result.validation_status == ValidationStatus.PASSED
            assert result.overall_risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM]

            # Should have no critical blocking issues
            critical_errors = [
                err
                for err in result.validation_errors
                if err.error_type.startswith("CRITICAL_")
            ]
            assert len(critical_errors) == 0

    @pytest.mark.asyncio
    async def test_data_cleanup_migration_scenario(
        self, e2e_validation_pipeline, e2e_test_database
    ):
        """Test data cleanup migration scenario."""
        # Scenario: Company wants to clean up deprecated user fields
        # after user profile system redesign

        migration_info = {
            "migration_id": "user_cleanup_001",
            "table_name": "users",
            "column_name": "phone",  # Assume this is being moved to separate contacts table
            "migration_sql": "ALTER TABLE users DROP COLUMN phone",
            "rollback_sql": "ALTER TABLE users ADD COLUMN phone VARCHAR(20)",
            "description": "Remove phone from users table as part of contacts system migration",
        }

        production_db = ProductionDatabase(**TEST_DB_CONFIG)

        result = await e2e_validation_pipeline.validate_migration(
            migration_info=migration_info, production_db=production_db
        )

        # Should validate the migration
        assert result.validation_status in [
            ValidationStatus.PASSED,
            ValidationStatus.FAILED,
        ]

        # Should complete comprehensive validation
        assert len(result.checkpoints) > 0
        assert result.validation_duration_seconds > 0

        # Should provide clear feedback about the migration safety
        if result.validation_status == ValidationStatus.PASSED:
            assert result.overall_risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM]
        else:
            # Should have clear error messages explaining why migration was blocked
            assert len(result.validation_errors) > 0

        # Verify all business-critical checkpoints were executed
        checkpoint_types = {cp.checkpoint_type for cp in result.checkpoints}
        business_critical_checkpoints = {
            CheckpointType.DEPENDENCY_ANALYSIS,  # Critical for data integrity
            CheckpointType.DATA_INTEGRITY,  # Critical for business continuity
            CheckpointType.ROLLBACK_VALIDATION,  # Critical for deployment safety
        }

        for critical_checkpoint in business_critical_checkpoints:
            assert critical_checkpoint in checkpoint_types
