#!/usr/bin/env python3
"""
Critical Safety Scenario Tests for TODO-137 Column Removal Dependency Analysis

Tests the most dangerous column removal scenarios to validate that the system
PREVENTS DATA LOSS by blocking critical operations. These tests validate the
core safety requirements identified in the deep-analyst risk assessment.

CRITICAL SAFETY REQUIREMENTS TESTED:
1. Foreign Key Target Column Removal (MUST be blocked)
2. Primary Key Column Removal (MUST be blocked)
3. Unique Constraint Target Removal (MUST be blocked)
4. Cascade Deletion Chain Prevention (MUST analyze impact)
5. Data Integrity Preservation (0% data loss requirement)

Following Tier 2 testing guidelines:
- Uses real PostgreSQL Docker infrastructure (NO MOCKING)
- Timeout: <5 seconds per test
- Tests actual database constraint enforcement
- Validates complete safety mechanisms
- CRITICAL PRIORITY: Zero tolerance for data loss incidents

Integration Test Setup:
1. Run: ./tests/utils/test-env up && ./tests/utils/test-env status
2. Verify PostgreSQL running on port 5434
3. All tests use real constraint violations and safety checks
"""

import asyncio
import logging
import time
from typing import Any, Dict, List

import asyncpg
import pytest
from kailash.runtime.local import LocalRuntime

from dataflow.migrations.column_removal_manager import (
    BackupStrategy,
    ColumnRemovalManager,
    RemovalPlan,
    RemovalResult,
    SafetyValidation,
)
from dataflow.migrations.dependency_analyzer import (
    DependencyAnalyzer,
    DependencyReport,
    DependencyType,
    ImpactLevel,
)
from dataflow.migrations.impact_reporter import (
    ImpactReporter,
    OutputFormat,
    RecommendationType,
)
from dataflow.migrations.migration_connection_manager import MigrationConnectionManager

# Import test infrastructure
from tests.infrastructure.test_harness import IntegrationTestSuite

# Configure logging for critical safety test debugging
logging.basicConfig(level=logging.WARNING)  # Less verbose for critical tests
logger = logging.getLogger(__name__)


# Integration test fixtures
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
async def connection_manager(test_suite):
    """Create connection manager for tests."""

    class MockDataFlow:
        def __init__(self, url):
            self.config = type("Config", (), {})()
            self.config.database = type("Database", (), {})()
            self.config.database.url = url

    config = test_suite.config
    mock_dataflow = MockDataFlow(config.url)
    manager = MigrationConnectionManager(mock_dataflow)

    yield manager

    # Cleanup
    manager.close_all_connections()


@pytest.fixture
async def safety_components(connection_manager):
    """Create all safety validation components."""
    dependency_analyzer = DependencyAnalyzer(connection_manager)
    column_removal_manager = ColumnRemovalManager(connection_manager)
    impact_reporter = ImpactReporter()

    return dependency_analyzer, column_removal_manager, impact_reporter


@pytest.fixture
async def test_connection(test_suite):
    """Direct connection for test setup."""
    async with test_suite.get_connection() as conn:
        yield conn


@pytest.fixture(autouse=True)
async def clean_critical_schema(test_suite):
    """Clean test schema before each critical safety test."""
    async with test_suite.get_connection() as conn:
        await conn.execute(
            """
        DO $$
        DECLARE
            r RECORD;
        BEGIN
            -- Drop views
            FOR r IN (SELECT schemaname, viewname FROM pg_views
                     WHERE schemaname = 'public' AND viewname LIKE 'critical_%')
            LOOP
                EXECUTE 'DROP VIEW IF EXISTS ' || quote_ident(r.schemaname) || '.' || quote_ident(r.viewname) || ' CASCADE';
            END LOOP;

            -- Drop functions
            FOR r IN (SELECT routine_schema, routine_name FROM information_schema.routines
                     WHERE routine_schema = 'public' AND routine_name LIKE 'critical_%')
            LOOP
                EXECUTE 'DROP FUNCTION IF EXISTS ' || quote_ident(r.routine_schema) || '.' || quote_ident(r.routine_name) || ' CASCADE';
            END LOOP;

            -- Drop tables (with CASCADE to handle FKs)
            FOR r IN (SELECT schemaname, tablename FROM pg_tables
                     WHERE schemaname = 'public' AND tablename LIKE 'critical_%')
            LOOP
                EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.schemaname) || '.' || quote_ident(r.tablename) || ' CASCADE';
            END LOOP;
        END $$;
    """
        )


@pytest.mark.integration
@pytest.mark.timeout(30)
class TestCriticalSafetyScenarios:
    """Critical safety tests - Zero tolerance for data loss."""

    @pytest.mark.asyncio
    async def test_critical_primary_key_target_prevention(
        self, safety_components, test_connection
    ):
        """
        CRITICAL SAFETY TEST: Primary Key Target Column Removal Prevention

        This is the MOST DANGEROUS scenario - removing a primary key column that is
        referenced by foreign keys. The system MUST:
        1. Detect all foreign key references
        2. Block removal with CRITICAL risk level
        3. Provide clear danger warnings
        4. NEVER allow execution under any circumstances
        """
        dependency_analyzer, column_removal_manager, impact_reporter = safety_components

        logger.warning("🚨 CRITICAL SAFETY TEST: Primary key target removal prevention")

        # Create schema with primary key referenced by multiple foreign keys
        await test_connection.execute(
            """
            -- Primary table with primary key (CRITICAL removal target)
            CREATE TABLE critical_users (
                id SERIAL PRIMARY KEY,  -- THIS IS THE DANGEROUS REMOVAL TARGET
                username VARCHAR(100) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );

            -- Multiple child tables with CASCADE deletes (data loss risk)
            CREATE TABLE critical_orders (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                total_amount DECIMAL(15,2) NOT NULL,
                order_date DATE NOT NULL DEFAULT CURRENT_DATE,
                CONSTRAINT fk_orders_user_id FOREIGN KEY (user_id)
                    REFERENCES critical_users(id) ON DELETE CASCADE  -- CASCADE = DATA LOSS RISK
            );

            CREATE TABLE critical_profiles (
                id SERIAL PRIMARY KEY,
                user_id INTEGER UNIQUE NOT NULL,
                bio TEXT,
                avatar_url VARCHAR(500),
                CONSTRAINT fk_profiles_user_id FOREIGN KEY (user_id)
                    REFERENCES critical_users(id) ON DELETE CASCADE  -- CASCADE = DATA LOSS RISK
            );

            CREATE TABLE critical_sessions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                session_token VARCHAR(255) UNIQUE NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                ip_address INET,
                CONSTRAINT fk_sessions_user_id FOREIGN KEY (user_id)
                    REFERENCES critical_users(id) ON DELETE CASCADE  -- CASCADE = DATA LOSS RISK
            );

            -- Child table with RESTRICT delete (prevents deletion but still dangerous)
            CREATE TABLE critical_audit_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                action VARCHAR(100) NOT NULL,
                timestamp TIMESTAMP DEFAULT NOW(),
                CONSTRAINT fk_audit_user_id FOREIGN KEY (user_id)
                    REFERENCES critical_users(id) ON DELETE RESTRICT  -- RESTRICT = PREVENTS DELETE
            );

            -- Add critical data that would be lost
            INSERT INTO critical_users (username, email) VALUES
            ('admin', 'admin@company.com'),
            ('user1', 'user1@company.com'),
            ('user2', 'user2@company.com');

            INSERT INTO critical_orders (user_id, total_amount) VALUES
            (1, 1000.00), (1, 500.00),  -- Admin's orders
            (2, 200.00), (3, 150.00);   -- User orders

            INSERT INTO critical_profiles (user_id, bio) VALUES
            (1, 'System Administrator'),
            (2, 'Regular User'),
            (3, 'Another User');

            INSERT INTO critical_sessions (user_id, session_token, expires_at) VALUES
            (1, 'admin_session_123', NOW() + INTERVAL '1 day'),
            (2, 'user1_session_456', NOW() + INTERVAL '1 day');

            INSERT INTO critical_audit_logs (user_id, action) VALUES
            (1, 'LOGIN'), (1, 'CREATE_ORDER'),
            (2, 'LOGIN'), (3, 'LOGIN');
        """
        )

        try:
            # **PHASE 1**: Dependency Analysis - MUST detect all foreign key references
            logger.warning(
                "Phase 1: Analyzing critical_users.id (primary key with FK references)"
            )

            dependency_report = await dependency_analyzer.analyze_column_dependencies(
                "critical_users", "id"
            )

            # **CRITICAL VALIDATION 1**: Must detect ALL foreign key dependencies
            assert (
                dependency_report.has_dependencies() is True
            ), "CRITICAL: Must detect FK dependencies"
            assert (
                DependencyType.FOREIGN_KEY in dependency_report.dependencies
            ), "CRITICAL: Must detect FK type"

            fk_deps = dependency_report.dependencies[DependencyType.FOREIGN_KEY]
            fk_names = {dep.constraint_name for dep in fk_deps}

            # Must detect all 4 foreign key constraints
            expected_fks = {
                "fk_orders_user_id",
                "fk_profiles_user_id",
                "fk_sessions_user_id",
                "fk_audit_user_id",
            }
            found_fks = expected_fks.intersection(fk_names)
            assert (
                len(found_fks) == 4
            ), f"CRITICAL: Must find all 4 FK constraints, found: {found_fks}"

            # **CRITICAL VALIDATION 2**: ALL foreign keys must be marked CRITICAL
            for fk_dep in fk_deps:
                assert (
                    fk_dep.impact_level == ImpactLevel.CRITICAL
                ), f"CRITICAL: FK {fk_dep.constraint_name} must be CRITICAL impact"
                assert (
                    fk_dep.target_table == "critical_users"
                ), "CRITICAL: FK must target critical_users"
                assert (
                    fk_dep.target_column == "id"
                ), "CRITICAL: FK must target id column"

            # Verify CASCADE vs RESTRICT detection
            cascade_fks = [fk for fk in fk_deps if fk.on_delete == "CASCADE"]
            restrict_fks = [fk for fk in fk_deps if fk.on_delete == "RESTRICT"]

            assert (
                len(cascade_fks) == 3
            ), f"CRITICAL: Must detect 3 CASCADE FKs (data loss risk), found: {len(cascade_fks)}"
            assert (
                len(restrict_fks) == 1
            ), f"CRITICAL: Must detect 1 RESTRICT FK, found: {len(restrict_fks)}"

            # **CRITICAL VALIDATION 3**: Overall recommendation must be DANGEROUS
            recommendation = dependency_report.get_removal_recommendation()
            assert (
                recommendation == "DANGEROUS"
            ), f"CRITICAL: Must recommend DANGEROUS, got: {recommendation}"

            critical_deps = dependency_report.get_critical_dependencies()
            assert (
                len(critical_deps) >= 4
            ), f"CRITICAL: Must identify at least 4 critical deps, found: {len(critical_deps)}"

            logger.warning(
                f"✅ Phase 1 CRITICAL validation passed: {len(fk_deps)} FK dependencies detected"
            )

            # **PHASE 3**: Impact Assessment - MUST generate critical warnings
            logger.warning(
                "Phase 3: Generating impact assessment for primary key removal"
            )

            impact_report = impact_reporter.generate_impact_report(dependency_report)

            # **CRITICAL VALIDATION 4**: Impact assessment must be CRITICAL
            assert (
                impact_report.assessment.overall_risk == ImpactLevel.CRITICAL
            ), "CRITICAL: Impact must be CRITICAL"
            assert (
                impact_report.assessment.critical_dependencies >= 4
            ), "CRITICAL: Must count all critical deps"

            # Primary recommendation MUST be DO NOT REMOVE
            primary_rec = impact_report.recommendations[0]
            assert (
                primary_rec.type == RecommendationType.DO_NOT_REMOVE
            ), "CRITICAL: Must recommend DO NOT REMOVE"
            assert (
                "CRITICAL" in primary_rec.title.upper()
            ), "CRITICAL: Title must emphasize CRITICAL"

            # Generate user-facing reports
            console_report = impact_reporter.format_user_friendly_report(
                impact_report, OutputFormat.CONSOLE
            )

            # **CRITICAL VALIDATION 5**: Console report must clearly warn of danger
            assert (
                "CRITICAL IMPACT DETECTED" in console_report
            ), "CRITICAL: Must show critical impact"
            assert (
                "DO NOT REMOVE" in console_report
            ), "CRITICAL: Must show DO NOT REMOVE"
            assert "🔴" in console_report, "CRITICAL: Must show critical icon"
            assert (
                "critical_users.id" in console_report
            ), "CRITICAL: Must identify specific column"

            logger.warning(
                "✅ Phase 3 CRITICAL validation passed: Impact assessment shows CRITICAL danger"
            )

            # **PHASE 2**: Safety Validation - MUST block execution
            logger.warning(
                "Phase 2: Safety validation for primary key removal (MUST BLOCK)"
            )

            removal_plan = await column_removal_manager.plan_column_removal(
                "critical_users", "id", BackupStrategy.TABLE_SNAPSHOT
            )

            safety_validation = await column_removal_manager.validate_removal_safety(
                removal_plan
            )

            # **CRITICAL VALIDATION 6**: Safety validation MUST block removal
            assert (
                safety_validation.is_safe is False
            ), "CRITICAL SAFETY VIOLATION: Must block primary key removal"
            assert (
                safety_validation.risk_level == ImpactLevel.CRITICAL
            ), "CRITICAL: Risk must be CRITICAL"
            assert (
                len(safety_validation.blocking_dependencies) >= 4
            ), "CRITICAL: Must list all blocking deps"
            assert (
                safety_validation.requires_confirmation is True
            ), "CRITICAL: Must require confirmation"

            # Must have critical warnings
            assert len(safety_validation.warnings) > 0, "CRITICAL: Must have warnings"
            warning_text = " ".join(safety_validation.warnings).lower()
            assert any(
                word in warning_text
                for word in ["critical", "foreign key", "data loss", "cascade"]
            ), "CRITICAL: Warnings must mention data loss risk"

            # Must have specific recommendations
            assert (
                len(safety_validation.recommendations) > 0
            ), "CRITICAL: Must have safety recommendations"
            rec_text = " ".join(safety_validation.recommendations).lower()
            assert any(
                word in rec_text
                for word in ["foreign key", "constraint", "remove", "first"]
            ), "CRITICAL: Must recommend removing FKs first"

            logger.warning(
                "✅ Phase 2 CRITICAL validation passed: Safety validation blocks removal"
            )

            # **PHASE 2**: Execution Prevention Test - MUST NOT execute
            logger.warning("Testing execution prevention (CRITICAL safety requirement)")

            # Even if we try to execute, it MUST fail at safety validation stage
            removal_plan.force_execution = False  # Ensure safety checks are enabled

            result = await column_removal_manager.execute_safe_removal(removal_plan)

            # **CRITICAL VALIDATION 7**: Execution MUST fail at safety validation
            assert (
                result.result != RemovalResult.SUCCESS
            ), "CRITICAL SAFETY VIOLATION: Execution must not succeed"
            assert result.result in [
                RemovalResult.SAFETY_VALIDATION_FAILED,
                RemovalResult.TRANSACTION_FAILED,
            ], f"CRITICAL: Must fail due to safety validation, got: {result.result}"

            # Database state must be unchanged
            column_exists = await test_connection.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'critical_users' AND column_name = 'id'
                )
            """
            )
            assert (
                column_exists is True
            ), "CRITICAL SAFETY VIOLATION: Column must still exist after blocked removal"

            # Data must be intact
            user_count = await test_connection.fetchval(
                "SELECT COUNT(*) FROM critical_users"
            )
            order_count = await test_connection.fetchval(
                "SELECT COUNT(*) FROM critical_orders"
            )

            assert user_count == 3, "CRITICAL DATA LOSS: User data must be preserved"
            assert order_count == 4, "CRITICAL DATA LOSS: Order data must be preserved"

            logger.warning(
                "✅ EXECUTION PREVENTION validated: System blocked dangerous removal"
            )

            # **FINAL CRITICAL VALIDATION**: Cross-phase consistency
            # All phases must agree on CRITICAL risk and blocking
            assert (
                dependency_report.get_removal_recommendation() == "DANGEROUS"
                and impact_report.assessment.overall_risk == ImpactLevel.CRITICAL
                and safety_validation.is_safe is False
                and result.result != RemovalResult.SUCCESS
            ), "CRITICAL: All phases must consistently block dangerous removal"

            logger.warning(
                "🎯 CRITICAL SAFETY TEST PASSED: Primary key removal prevention validated"
            )
            logger.warning(f"   - FK dependencies detected: {len(fk_deps)}")
            logger.warning(f"   - CASCADE FKs (data loss risk): {len(cascade_fks)}")
            logger.warning(f"   - RESTRICT FKs (deletion blocked): {len(restrict_fks)}")
            logger.warning("   - Safety verdict: BLOCKED ✅")

        finally:
            # Ensure cleanup occurs even if test fails
            pass

    @pytest.mark.asyncio
    async def test_critical_unique_constraint_target_prevention(
        self, safety_components, test_connection
    ):
        """
        CRITICAL SAFETY TEST: Unique Constraint Target Column Removal Prevention

        Tests removal of columns that are targets of unique constraints with foreign
        key references. This can cause referential integrity violations.
        """
        dependency_analyzer, column_removal_manager, impact_reporter = safety_components

        logger.warning(
            "🚨 CRITICAL SAFETY TEST: Unique constraint target removal prevention"
        )

        # Create schema with unique constraint referenced by foreign keys
        await test_connection.execute(
            """
            CREATE TABLE critical_products (
                id SERIAL PRIMARY KEY,
                sku VARCHAR(50) UNIQUE NOT NULL,  -- UNIQUE constraint target (dangerous to remove)
                name VARCHAR(255) NOT NULL,
                price DECIMAL(10,2) NOT NULL
            );

            -- Foreign key referencing the unique constraint column
            CREATE TABLE critical_order_items (
                id SERIAL PRIMARY KEY,
                product_sku VARCHAR(50) NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price DECIMAL(10,2) NOT NULL,
                CONSTRAINT fk_order_items_sku FOREIGN KEY (product_sku)
                    REFERENCES critical_products(sku) ON DELETE RESTRICT
            );

            CREATE TABLE critical_inventory (
                id SERIAL PRIMARY KEY,
                product_sku VARCHAR(50) NOT NULL,
                stock_level INTEGER NOT NULL,
                warehouse_location VARCHAR(100),
                CONSTRAINT fk_inventory_sku FOREIGN KEY (product_sku)
                    REFERENCES critical_products(sku) ON DELETE CASCADE
            );

            -- Add critical data
            INSERT INTO critical_products (sku, name, price) VALUES
            ('PROD001', 'Critical Product 1', 99.99),
            ('PROD002', 'Critical Product 2', 149.99);

            INSERT INTO critical_order_items (product_sku, quantity, unit_price) VALUES
            ('PROD001', 5, 99.99),
            ('PROD002', 3, 149.99);

            INSERT INTO critical_inventory (product_sku, stock_level, warehouse_location) VALUES
            ('PROD001', 100, 'Warehouse A'),
            ('PROD002', 50, 'Warehouse B');
        """
        )

        try:
            # Analyze dependencies for unique constraint target column
            dependency_report = await dependency_analyzer.analyze_column_dependencies(
                "critical_products", "sku"
            )

            # **CRITICAL VALIDATION**: Must detect foreign key dependencies on unique column
            assert dependency_report.has_dependencies() is True
            assert DependencyType.FOREIGN_KEY in dependency_report.dependencies

            fk_deps = dependency_report.dependencies[DependencyType.FOREIGN_KEY]
            assert (
                len(fk_deps) >= 2
            ), "CRITICAL: Must detect both FK dependencies on unique constraint"

            # All FKs referencing unique constraint must be CRITICAL
            for fk_dep in fk_deps:
                assert fk_dep.impact_level == ImpactLevel.CRITICAL
                assert fk_dep.target_column == "sku"

            # Should also detect the unique constraint itself
            assert (
                DependencyType.INDEX in dependency_report.dependencies
                or DependencyType.CONSTRAINT in dependency_report.dependencies
            )

            # Safety validation must block removal
            removal_plan = await column_removal_manager.plan_column_removal(
                "critical_products", "sku", BackupStrategy.TABLE_SNAPSHOT
            )
            safety_validation = await column_removal_manager.validate_removal_safety(
                removal_plan
            )

            assert (
                safety_validation.is_safe is False
            ), "CRITICAL: Must block unique constraint target removal"
            assert safety_validation.risk_level == ImpactLevel.CRITICAL

            logger.warning(
                "✅ CRITICAL SAFETY: Unique constraint target removal blocked"
            )

        finally:
            pass

    @pytest.mark.asyncio
    async def test_critical_cascade_deletion_chain_analysis(
        self, safety_components, test_connection
    ):
        """
        CRITICAL SAFETY TEST: Cascade Deletion Chain Impact Analysis

        Tests scenarios where removing a column could trigger cascade deletions
        affecting multiple tables and thousands of rows of data.
        """
        dependency_analyzer, column_removal_manager, impact_reporter = safety_components

        logger.warning("🚨 CRITICAL SAFETY TEST: Cascade deletion chain analysis")

        # Create complex cascade chain schema
        await test_connection.execute(
            """
            -- Root table
            CREATE TABLE critical_companies (
                id SERIAL PRIMARY KEY,
                company_code VARCHAR(20) UNIQUE NOT NULL  -- Removal target
            );

            -- Level 1: Direct dependents
            CREATE TABLE critical_departments (
                id SERIAL PRIMARY KEY,
                company_code VARCHAR(20) NOT NULL,
                dept_name VARCHAR(100) NOT NULL,
                CONSTRAINT fk_dept_company FOREIGN KEY (company_code)
                    REFERENCES critical_companies(company_code) ON DELETE CASCADE
            );

            CREATE TABLE critical_locations (
                id SERIAL PRIMARY KEY,
                company_code VARCHAR(20) NOT NULL,
                address TEXT NOT NULL,
                CONSTRAINT fk_location_company FOREIGN KEY (company_code)
                    REFERENCES critical_companies(company_code) ON DELETE CASCADE
            );

            -- Level 2: Cascade chain continues
            CREATE TABLE critical_employees (
                id SERIAL PRIMARY KEY,
                department_id INTEGER NOT NULL,
                employee_code VARCHAR(20) UNIQUE NOT NULL,
                CONSTRAINT fk_emp_dept FOREIGN KEY (department_id)
                    REFERENCES critical_departments(id) ON DELETE CASCADE
            );

            -- Level 3: Deep cascade chain
            CREATE TABLE critical_timesheets (
                id SERIAL PRIMARY KEY,
                employee_code VARCHAR(20) NOT NULL,
                work_date DATE NOT NULL,
                hours DECIMAL(4,2) NOT NULL,
                CONSTRAINT fk_timesheet_emp FOREIGN KEY (employee_code)
                    REFERENCES critical_employees(employee_code) ON DELETE CASCADE
            );

            -- Create substantial amount of data that would be lost
            INSERT INTO critical_companies (company_code) VALUES ('COMP001'), ('COMP002');

            INSERT INTO critical_departments (company_code, dept_name) VALUES
            ('COMP001', 'Engineering'), ('COMP001', 'Sales'),
            ('COMP002', 'Marketing'), ('COMP002', 'Support');

            INSERT INTO critical_locations (company_code, address) VALUES
            ('COMP001', '123 Tech St'), ('COMP001', '456 Office Blvd'),
            ('COMP002', '789 Business Ave');

            INSERT INTO critical_employees (department_id, employee_code) VALUES
            (1, 'EMP001'), (1, 'EMP002'), (2, 'EMP003'), (2, 'EMP004'),
            (3, 'EMP005'), (4, 'EMP006'), (4, 'EMP007');

            -- Lots of timesheet data (would all be lost in cascade)
            INSERT INTO critical_timesheets (employee_code, work_date, hours)
            SELECT
                'EMP00' || (i % 7 + 1)::text,
                CURRENT_DATE - (i % 30)::integer,
                8.0
            FROM generate_series(1, 200) i;  -- 200 timesheet records
        """
        )

        try:
            # Analyze the company_code column (root of cascade chain)
            dependency_report = await dependency_analyzer.analyze_column_dependencies(
                "critical_companies", "company_code"
            )

            # **CRITICAL VALIDATION**: Must detect cascade chain impact
            assert dependency_report.has_dependencies() is True

            fk_deps = dependency_report.dependencies.get(DependencyType.FOREIGN_KEY, [])
            assert len(fk_deps) >= 2, "CRITICAL: Must detect direct FK dependencies"

            # All direct FKs should be CRITICAL due to CASCADE behavior
            cascade_fks = [fk for fk in fk_deps if fk.on_delete == "CASCADE"]
            assert len(cascade_fks) >= 2, "CRITICAL: Must detect CASCADE foreign keys"

            for fk_dep in cascade_fks:
                assert (
                    fk_dep.impact_level == ImpactLevel.CRITICAL
                ), "CRITICAL: CASCADE FKs must be CRITICAL impact"

            # Impact assessment should recognize cascade danger
            impact_report = impact_reporter.generate_impact_report(dependency_report)

            assert impact_report.assessment.overall_risk == ImpactLevel.CRITICAL

            # Recommendations should warn about cascade deletion
            console_report = impact_reporter.format_user_friendly_report(
                impact_report, OutputFormat.CONSOLE
            )
            assert any(
                word in console_report.lower()
                for word in ["cascade", "deletion", "multiple tables"]
            )

            # Safety validation must block with cascade warnings
            removal_plan = await column_removal_manager.plan_column_removal(
                "critical_companies", "company_code", BackupStrategy.TABLE_SNAPSHOT
            )
            safety_validation = await column_removal_manager.validate_removal_safety(
                removal_plan
            )

            assert (
                safety_validation.is_safe is False
            ), "CRITICAL: Must block cascade deletion root"

            # Verify data exists that would be lost
            timesheet_count = await test_connection.fetchval(
                "SELECT COUNT(*) FROM critical_timesheets"
            )
            employee_count = await test_connection.fetchval(
                "SELECT COUNT(*) FROM critical_employees"
            )

            assert (
                timesheet_count >= 200
            ), "Should have substantial data that would be lost"
            assert employee_count >= 7, "Should have employee data that would be lost"

            logger.warning(
                f"✅ CRITICAL SAFETY: Cascade chain blocked - would affect {timesheet_count} timesheets, {employee_count} employees"
            )

        finally:
            pass

    @pytest.mark.asyncio
    async def test_critical_data_integrity_preservation(
        self, safety_components, test_connection
    ):
        """
        CRITICAL SAFETY TEST: Data Integrity Preservation (0% Data Loss Requirement)

        Validates that the system maintains 100% data integrity under all
        circumstances, including edge cases and error conditions.
        """
        dependency_analyzer, column_removal_manager, impact_reporter = safety_components

        logger.warning(
            "🚨 CRITICAL SAFETY TEST: Data integrity preservation (0% data loss)"
        )

        # Create schema with valuable business data
        await test_connection.execute(
            """
            CREATE TABLE critical_customers (
                id SERIAL PRIMARY KEY,
                customer_id VARCHAR(50) UNIQUE NOT NULL,  -- Business critical identifier
                company_name VARCHAR(255) NOT NULL,
                total_value DECIMAL(15,2) NOT NULL DEFAULT 0
            );

            CREATE TABLE critical_transactions (
                id SERIAL PRIMARY KEY,
                customer_id VARCHAR(50) NOT NULL,
                transaction_amount DECIMAL(15,2) NOT NULL,
                transaction_date DATE NOT NULL DEFAULT CURRENT_DATE,
                CONSTRAINT fk_trans_customer FOREIGN KEY (customer_id)
                    REFERENCES critical_customers(customer_id) ON DELETE RESTRICT
            );

            -- Insert valuable business data
            INSERT INTO critical_customers (customer_id, company_name, total_value) VALUES
            ('CUST-001', 'Major Corporation', 500000.00),
            ('CUST-002', 'Important Client', 750000.00),
            ('CUST-003', 'Key Partner', 300000.00);

            INSERT INTO critical_transactions (customer_id, transaction_amount) VALUES
            ('CUST-001', 100000.00), ('CUST-001', 75000.00),
            ('CUST-002', 250000.00), ('CUST-002', 125000.00),
            ('CUST-003', 50000.00);
        """
        )

        try:
            # Calculate initial data state
            initial_customer_count = await test_connection.fetchval(
                "SELECT COUNT(*) FROM critical_customers"
            )
            initial_transaction_count = await test_connection.fetchval(
                "SELECT COUNT(*) FROM critical_transactions"
            )
            initial_total_value = await test_connection.fetchval(
                "SELECT SUM(total_value) FROM critical_customers"
            )

            assert initial_customer_count == 3, "Initial data setup validation"
            assert initial_transaction_count == 5, "Initial transaction data validation"
            assert (
                initial_total_value == 1550000.00
            ), "Initial business value validation"

            # Attempt to remove business critical column
            dependency_report = await dependency_analyzer.analyze_column_dependencies(
                "critical_customers", "customer_id"
            )

            # System must detect this as critical
            assert dependency_report.has_dependencies() is True

            # Plan removal (should be blocked)
            removal_plan = await column_removal_manager.plan_column_removal(
                "critical_customers", "customer_id", BackupStrategy.TABLE_SNAPSHOT
            )

            # Safety validation MUST block
            safety_validation = await column_removal_manager.validate_removal_safety(
                removal_plan
            )
            assert (
                safety_validation.is_safe is False
            ), "CRITICAL: Must protect business data"

            # Even if we force attempt execution (simulate system malfunction), data must be preserved
            try:
                result = await column_removal_manager.execute_safe_removal(removal_plan)

                # If execution somehow proceeded, it must have failed safely
                assert (
                    result.result != RemovalResult.SUCCESS
                ), "CRITICAL: Execution must not succeed with critical data"

            except Exception as e:
                # Exception during execution is acceptable - prevents data loss
                logger.warning(
                    f"Expected exception during critical data protection: {str(e)[:100]}"
                )

            # **CRITICAL VALIDATION**: Verify 0% data loss
            final_customer_count = await test_connection.fetchval(
                "SELECT COUNT(*) FROM critical_customers"
            )
            final_transaction_count = await test_connection.fetchval(
                "SELECT COUNT(*) FROM critical_transactions"
            )
            final_total_value = await test_connection.fetchval(
                "SELECT SUM(total_value) FROM critical_customers"
            )

            assert (
                final_customer_count == initial_customer_count
            ), "CRITICAL DATA LOSS: Customer count changed"
            assert (
                final_transaction_count == initial_transaction_count
            ), "CRITICAL DATA LOSS: Transaction count changed"
            assert (
                final_total_value == initial_total_value
            ), "CRITICAL DATA LOSS: Business value changed"

            # Verify column still exists
            column_exists = await test_connection.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'critical_customers' AND column_name = 'customer_id'
                )
            """
            )
            assert (
                column_exists is True
            ), "CRITICAL: Business critical column must be preserved"

            # Verify referential integrity is intact
            orphaned_transactions = await test_connection.fetchval(
                """
                SELECT COUNT(*) FROM critical_transactions t
                LEFT JOIN critical_customers c ON t.customer_id = c.customer_id
                WHERE c.customer_id IS NULL
            """
            )
            assert (
                orphaned_transactions == 0
            ), "CRITICAL: No orphaned transactions (referential integrity preserved)"

            logger.warning(
                "✅ CRITICAL SAFETY: Data integrity preserved - 0% data loss validated"
            )
            logger.warning(f"   - Customers preserved: {final_customer_count}")
            logger.warning(f"   - Transactions preserved: {final_transaction_count}")
            logger.warning(f"   - Business value preserved: ${final_total_value:,.2f}")

        finally:
            pass

    @pytest.mark.asyncio
    async def test_critical_system_recovery_validation(
        self, safety_components, test_connection
    ):
        """
        CRITICAL SAFETY TEST: System Recovery Validation

        Tests that the system can recover from failures without data loss
        and maintains consistent state even during error conditions.
        """
        dependency_analyzer, column_removal_manager, impact_reporter = safety_components

        logger.warning("🚨 CRITICAL SAFETY TEST: System recovery validation")

        # Create schema for recovery testing
        await test_connection.execute(
            """
            CREATE TABLE critical_recovery_test (
                id SERIAL PRIMARY KEY,
                recovery_column VARCHAR(100),  -- Target for recovery test
                important_data TEXT NOT NULL
            );

            INSERT INTO critical_recovery_test (recovery_column, important_data) VALUES
            ('data1', 'Important business data 1'),
            ('data2', 'Important business data 2'),
            ('data3', 'Important business data 3');
        """
        )

        try:
            # Record initial state
            initial_count = await test_connection.fetchval(
                "SELECT COUNT(*) FROM critical_recovery_test"
            )
            initial_data = await test_connection.fetch(
                "SELECT * FROM critical_recovery_test ORDER BY id"
            )

            # Create removal plan
            removal_plan = await column_removal_manager.plan_column_removal(
                "critical_recovery_test",
                "recovery_column",
                BackupStrategy.TABLE_SNAPSHOT,
            )

            # Simulate system failure during execution by injecting failure
            original_method = column_removal_manager._execute_removal_stage

            failure_injected = False

            async def failing_stage_executor(
                stage, table_name, column_name, connection, plan, stage_details=None
            ):
                nonlocal failure_injected
                if stage.name == "COLUMN_REMOVAL" and not failure_injected:
                    failure_injected = True
                    raise Exception(
                        "Simulated system failure during critical operation"
                    )
                return await original_method(
                    stage, table_name, column_name, connection, plan, stage_details
                )

            column_removal_manager._execute_removal_stage = failing_stage_executor

            try:
                # Execute with injected failure
                result = await column_removal_manager.execute_safe_removal(removal_plan)

                # System should recover from failure
                assert result.result in [
                    RemovalResult.TRANSACTION_FAILED,
                    RemovalResult.SYSTEM_ERROR,
                ]
                assert (
                    result.rollback_executed is True
                ), "CRITICAL: System must rollback on failure"

            finally:
                # Restore original method
                column_removal_manager._execute_removal_stage = original_method

            # **CRITICAL RECOVERY VALIDATION**: Verify complete recovery
            post_failure_count = await test_connection.fetchval(
                "SELECT COUNT(*) FROM critical_recovery_test"
            )
            post_failure_data = await test_connection.fetch(
                "SELECT * FROM critical_recovery_test ORDER BY id"
            )

            assert (
                post_failure_count == initial_count
            ), "CRITICAL RECOVERY FAILURE: Row count changed after recovery"

            # Verify data is identical
            for initial_row, recovered_row in zip(initial_data, post_failure_data):
                assert dict(initial_row) == dict(
                    recovered_row
                ), "CRITICAL RECOVERY FAILURE: Data corrupted during recovery"

            # Verify schema integrity
            column_exists = await test_connection.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'critical_recovery_test' AND column_name = 'recovery_column'
                )
            """
            )
            assert (
                column_exists is True
            ), "CRITICAL RECOVERY FAILURE: Column lost during recovery"

            logger.warning(
                "✅ CRITICAL SAFETY: System recovery validated - no data loss during failure"
            )

        finally:
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
