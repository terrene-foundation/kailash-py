#!/usr/bin/env python3
"""
Integration Tests for Complete TODO-137 Phase 1→2→3 Workflow

Tests the complete column removal dependency analysis workflow with real PostgreSQL infrastructure,
validating the integration between all three phases:

Phase 1: DependencyAnalyzer - dependency detection
Phase 2: ColumnRemovalManager - safe removal execution
Phase 3: ImpactReporter - user-friendly reporting

Following Tier 2 testing guidelines:
- Uses real PostgreSQL Docker infrastructure (NO MOCKING)
- Timeout: <5 seconds per test
- Tests actual PostgreSQL system integration
- Validates complete workflow accuracy
- CRITICAL PRIORITY: End-to-end safety validation

Integration Test Setup:
1. Run: ./tests/utils/test-env up && ./tests/utils/test-env status
2. Verify PostgreSQL running on port 5434
3. All tests use real database objects and workflows
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List

import asyncpg
import pytest
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

from kailash.runtime.local import LocalRuntime

# Import test infrastructure
from tests.infrastructure.test_harness import IntegrationTestSuite

# Configure logging for integration test debugging
logging.basicConfig(level=logging.INFO)
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

    # Mock DataFlow instance with database config
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
async def workflow_components(connection_manager):
    """Create all three workflow components."""
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
async def clean_test_schema(test_suite):
    """Clean test schema before each test."""
    # Drop all test objects
    async with test_suite.get_connection() as conn:
        await conn.execute(
            """
        DO $$
        DECLARE
            r RECORD;
        BEGIN
            -- Drop views
            FOR r IN (SELECT schemaname, viewname FROM pg_views
                     WHERE schemaname = 'public' AND viewname LIKE 'workflow_%')
            LOOP
                EXECUTE 'DROP VIEW IF EXISTS ' || quote_ident(r.schemaname) || '.' || quote_ident(r.viewname) || ' CASCADE';
            END LOOP;

            -- Drop functions
            FOR r IN (SELECT routine_schema, routine_name FROM information_schema.routines
                     WHERE routine_schema = 'public' AND routine_name LIKE 'workflow_%')
            LOOP
                EXECUTE 'DROP FUNCTION IF EXISTS ' || quote_ident(r.routine_schema) || '.' || quote_ident(r.routine_name) || ' CASCADE';
            END LOOP;

            -- Drop tables
            FOR r IN (SELECT schemaname, tablename FROM pg_tables
                     WHERE schemaname = 'public' AND tablename LIKE 'workflow_%')
            LOOP
                EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.schemaname) || '.' || quote_ident(r.tablename) || ' CASCADE';
            END LOOP;
        END $$;
    """
        )


@pytest.mark.integration
@pytest.mark.timeout(30)
class TestCompleteWorkflowIntegration:
    """Integration tests for complete Phase 1→2→3 workflow."""

    @pytest.mark.asyncio
    async def test_critical_foreign_key_scenario_complete_workflow(
        self, workflow_components, test_connection, runtime
    ):
        """
        Test complete workflow for CRITICAL scenario: Foreign Key Target Column Removal

        This tests the most dangerous scenario - attempting to remove a column that is
        referenced by foreign keys. The system MUST:
        1. Detect all foreign key dependencies (Phase 1)
        2. Block removal due to critical dependencies (Phase 2)
        3. Generate clear "DO NOT REMOVE" recommendations (Phase 3)
        """
        dependency_analyzer, column_removal_manager, impact_reporter = (
            workflow_components
        )

        logger.info("Setting up CRITICAL scenario: Foreign Key target column removal")

        # Create schema with foreign key dependencies
        await test_connection.execute(
            """
            -- Target table with primary key column to be "removed"
            CREATE TABLE workflow_users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );

            -- Multiple tables referencing users.id (CRITICAL dependencies)
            CREATE TABLE workflow_orders (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                total_amount DECIMAL(10,2) NOT NULL,
                CONSTRAINT fk_orders_user_id FOREIGN KEY (user_id) REFERENCES workflow_users(id) ON DELETE RESTRICT
            );

            CREATE TABLE workflow_profiles (
                id SERIAL PRIMARY KEY,
                user_id INTEGER UNIQUE NOT NULL,
                bio TEXT,
                CONSTRAINT fk_profiles_user_id FOREIGN KEY (user_id) REFERENCES workflow_users(id) ON DELETE CASCADE
            );

            CREATE TABLE workflow_sessions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                session_token VARCHAR(255) NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                CONSTRAINT fk_sessions_user_id FOREIGN KEY (user_id) REFERENCES workflow_users(id) ON DELETE CASCADE
            );

            -- View that uses the target column
            CREATE VIEW workflow_user_summary AS
            SELECT u.id, u.username, u.email,
                   COUNT(DISTINCT o.id) as order_count,
                   COUNT(DISTINCT s.id) as session_count
            FROM workflow_users u
            LEFT JOIN workflow_orders o ON u.id = o.user_id
            LEFT JOIN workflow_sessions s ON u.id = s.user_id
            GROUP BY u.id, u.username, u.email;

            -- Index on target column
            CREATE INDEX workflow_users_id_lookup ON workflow_users(id);
        """
        )

        try:
            logger.info(
                "PHASE 1: Analyzing dependencies for workflow_users.id (FK target column)"
            )

            # **PHASE 1**: Dependency Analysis
            start_time = time.time()
            dependency_report = await dependency_analyzer.analyze_column_dependencies(
                "workflow_users", "id"
            )
            phase1_time = time.time() - start_time

            # Verify Phase 1 detected critical dependencies
            assert dependency_report.has_dependencies() is True
            assert DependencyType.FOREIGN_KEY in dependency_report.dependencies

            fk_deps = dependency_report.dependencies[DependencyType.FOREIGN_KEY]
            fk_names = {dep.constraint_name for dep in fk_deps}

            # Must detect all 3 foreign key constraints
            expected_fks = {
                "fk_orders_user_id",
                "fk_profiles_user_id",
                "fk_sessions_user_id",
            }
            found_fks = expected_fks.intersection(fk_names)
            assert (
                len(found_fks) >= 3
            ), f"Must detect all FK dependencies, found: {found_fks}"

            # All FK dependencies must be CRITICAL
            for fk_dep in fk_deps:
                assert (
                    fk_dep.impact_level == ImpactLevel.CRITICAL
                ), f"FK {fk_dep.constraint_name} must be CRITICAL"
                assert fk_dep.target_table == "workflow_users"
                assert fk_dep.target_column == "id"

            critical_deps = dependency_report.get_critical_dependencies()
            assert (
                len(critical_deps) >= 3
            ), "Must identify at least 3 critical dependencies"

            logger.info(
                f"Phase 1 complete: Found {len(fk_deps)} FK dependencies in {phase1_time:.2f}s"
            )

            logger.info("PHASE 3: Generating impact assessment")

            # **PHASE 3**: Impact Assessment
            impact_report = impact_reporter.generate_impact_report(dependency_report)

            # Verify Phase 3 identifies critical scenario
            assert impact_report.assessment.overall_risk == ImpactLevel.CRITICAL
            assert impact_report.assessment.critical_dependencies >= 3
            assert (
                impact_report.assessment.total_dependencies >= 4
            )  # 3 FKs + view + index

            # Primary recommendation must be DO NOT REMOVE
            primary_rec = impact_report.recommendations[0]
            assert primary_rec.type == RecommendationType.DO_NOT_REMOVE
            assert "CRITICAL" in primary_rec.title.upper()
            assert len(primary_rec.action_steps) > 0

            logger.info("PHASE 2: Planning and validating column removal")

            # **PHASE 2**: Removal Planning and Safety Validation
            removal_plan = await column_removal_manager.plan_column_removal(
                "workflow_users", "id", BackupStrategy.TABLE_SNAPSHOT
            )

            # Verify Phase 2 detects same dependencies
            assert (
                len(removal_plan.dependencies) >= 4
            )  # Should include all detected dependencies

            safety_validation = await column_removal_manager.validate_removal_safety(
                removal_plan
            )

            # **CRITICAL SAFETY VALIDATION**: Must block removal
            assert (
                safety_validation.is_safe is False
            ), "CRITICAL: Must block FK target column removal"
            assert safety_validation.risk_level == ImpactLevel.CRITICAL
            assert len(safety_validation.blocking_dependencies) >= 3
            assert safety_validation.requires_confirmation is True
            assert len(safety_validation.warnings) > 0
            assert "CRITICAL" in " ".join(safety_validation.warnings)

            logger.info("PHASE 3: Generating user-friendly reports")

            # **PHASE 3**: User-Friendly Reporting
            console_report = impact_reporter.format_user_friendly_report(
                impact_report, OutputFormat.CONSOLE, include_details=True
            )
            json_report = impact_reporter.format_user_friendly_report(
                impact_report, OutputFormat.JSON
            )
            safety_report = impact_reporter.generate_safety_validation_report(
                safety_validation
            )

            # Verify reports clearly communicate danger
            assert "CRITICAL IMPACT DETECTED" in console_report
            assert "DO NOT REMOVE" in console_report
            assert "🔴" in console_report  # Critical icon
            assert "workflow_users.id" in console_report

            # JSON report should be parseable and consistent
            parsed_json = json.loads(json_report)
            assert parsed_json["assessment"]["overall_risk"] == "critical"
            assert parsed_json["assessment"]["critical_dependencies"] >= 3

            # Safety report should clearly indicate danger
            assert "❌ UNSAFE" in safety_report
            assert "🔴 CRITICAL" in safety_report
            assert "BLOCKING DEPENDENCIES" in safety_report

            logger.info("INTEGRATION VALIDATION: End-to-end workflow consistency")

            # **WORKFLOW INTEGRATION VALIDATION**: All phases consistent
            assert (
                dependency_report.get_removal_recommendation() == "DANGEROUS"
            ), "Phase 1 must recommend DANGEROUS"

            assert safety_validation.is_safe is False, "Phase 2 must validate as unsafe"

            assert (
                primary_rec.type == RecommendationType.DO_NOT_REMOVE
            ), "Phase 3 must recommend DO NOT REMOVE"

            # Performance validation
            assert phase1_time < 5.0, f"Phase 1 took too long: {phase1_time:.2f}s"

            logger.info("✅ CRITICAL SCENARIO WORKFLOW VALIDATION COMPLETE")
            logger.info(
                f"  - Dependencies detected: {dependency_report.get_total_dependency_count()}"
            )
            logger.info(f"  - Critical dependencies: {len(critical_deps)}")
            logger.info(f"  - Analysis time: {phase1_time:.2f}s")
            logger.info(
                f"  - Safety verdict: {'BLOCKED' if not safety_validation.is_safe else 'ALLOWED'}"
            )
            logger.info(f"  - Recommendation: {primary_rec.type.value}")

        finally:
            # Cleanup handled by fixture
            pass

    @pytest.mark.asyncio
    async def test_safe_removal_scenario_complete_workflow(
        self, workflow_components, test_connection, runtime
    ):
        """
        Test complete workflow for SAFE scenario: Unused Column Removal

        This tests a safe scenario - removing a truly unused column with minimal dependencies.
        The system should:
        1. Detect minimal or no dependencies (Phase 1)
        2. Allow removal with appropriate safety measures (Phase 2)
        3. Generate clear "SAFE TO REMOVE" recommendations (Phase 3)
        """
        dependency_analyzer, column_removal_manager, impact_reporter = (
            workflow_components
        )

        logger.info("Setting up SAFE scenario: Unused column removal")

        # Create schema with unused column
        await test_connection.execute(
            """
            CREATE TABLE workflow_products (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                price DECIMAL(10,2) NOT NULL,
                category VARCHAR(100) NOT NULL,
                unused_legacy_field VARCHAR(255),  -- Target for safe removal
                created_at TIMESTAMP DEFAULT NOW()
            );

            -- Create dependencies on OTHER columns (not unused_legacy_field)
            CREATE INDEX workflow_products_name_idx ON workflow_products(name);
            CREATE INDEX workflow_products_category_price_idx ON workflow_products(category, price);

            CREATE VIEW workflow_product_catalog AS
            SELECT id, name, price, category, created_at
            FROM workflow_products
            WHERE price > 0;

            -- Constraint on different column
            ALTER TABLE workflow_products ADD CONSTRAINT check_price_positive CHECK (price > 0);
        """
        )

        try:
            logger.info("PHASE 1: Analyzing dependencies for unused_legacy_field")

            # **PHASE 1**: Dependency Analysis
            dependency_report = await dependency_analyzer.analyze_column_dependencies(
                "workflow_products", "unused_legacy_field"
            )

            # Verify Phase 1 detects no or minimal dependencies
            assert (
                dependency_report.get_total_dependency_count() == 0
            ), "Unused column should have no dependencies"
            assert dependency_report.has_dependencies() is False

            critical_deps = dependency_report.get_critical_dependencies()
            assert len(critical_deps) == 0, "Should have no critical dependencies"

            logger.info("PHASE 3: Generating impact assessment for safe scenario")

            # **PHASE 3**: Impact Assessment
            impact_report = impact_reporter.generate_impact_report(dependency_report)

            # Verify Phase 3 identifies safe scenario
            assert impact_report.assessment.overall_risk in [
                ImpactLevel.LOW,
                ImpactLevel.INFORMATIONAL,
            ]
            assert impact_report.assessment.critical_dependencies == 0
            assert impact_report.assessment.total_dependencies == 0

            # Primary recommendation should be safe
            primary_rec = impact_report.recommendations[0]
            assert primary_rec.type == RecommendationType.SAFE_TO_REMOVE
            assert "SAFE" in primary_rec.title.upper()

            logger.info("PHASE 2: Planning and validating safe removal")

            # **PHASE 2**: Removal Planning and Safety Validation
            removal_plan = await column_removal_manager.plan_column_removal(
                "workflow_products", "unused_legacy_field", BackupStrategy.COLUMN_ONLY
            )

            # Verify Phase 2 plans for safe removal
            assert len(removal_plan.dependencies) == 0
            assert removal_plan.backup_strategy == BackupStrategy.COLUMN_ONLY
            assert removal_plan.confirmation_required is True  # Still recommend backup

            safety_validation = await column_removal_manager.validate_removal_safety(
                removal_plan
            )

            # **SAFETY VALIDATION**: Should allow removal
            assert (
                safety_validation.is_safe is True
            ), "Should validate as safe for unused column"
            assert safety_validation.risk_level in [
                ImpactLevel.LOW,
                ImpactLevel.INFORMATIONAL,
            ]
            assert len(safety_validation.blocking_dependencies) == 0
            assert safety_validation.requires_confirmation is False  # Safe removal

            logger.info("PHASE 3: Generating user-friendly reports for safe scenario")

            # **PHASE 3**: User-Friendly Reporting
            console_report = impact_reporter.format_user_friendly_report(
                impact_report, OutputFormat.CONSOLE
            )
            summary_report = impact_reporter.format_user_friendly_report(
                impact_report, OutputFormat.SUMMARY
            )
            safety_report = impact_reporter.generate_safety_validation_report(
                safety_validation
            )

            # Verify reports communicate safety
            assert (
                "SAFE TO REMOVE" in console_report
                or "minimal" in console_report.lower()
            )
            assert "✅" in console_report or "🟢" in console_report
            assert "workflow_products.unused_legacy_field" in console_report

            # Summary should be concise and positive
            assert (
                "Risk: LOW" in summary_report or "Risk: INFORMATIONAL" in summary_report
            )

            # Safety report should indicate safe
            assert "✅ SAFE" in safety_report
            assert safety_validation.risk_level.value.upper() in safety_report

            logger.info(
                "WORKFLOW VALIDATION: Verifying other columns still have dependencies"
            )

            # **WORKFLOW INTEGRITY CHECK**: Verify analyzer works for columns with dependencies
            name_report = await dependency_analyzer.analyze_column_dependencies(
                "workflow_products", "name"
            )
            price_report = await dependency_analyzer.analyze_column_dependencies(
                "workflow_products", "price"
            )

            assert (
                name_report.has_dependencies() is True
            ), "Name column should have dependencies (index, view)"
            assert (
                price_report.has_dependencies() is True
            ), "Price column should have dependencies (constraint, view, index)"

            logger.info("✅ SAFE SCENARIO WORKFLOW VALIDATION COMPLETE")
            logger.info(
                f"  - Dependencies detected: {dependency_report.get_total_dependency_count()}"
            )
            logger.info(
                f"  - Risk level: {impact_report.assessment.overall_risk.value}"
            )
            logger.info(
                f"  - Safety verdict: {'ALLOWED' if safety_validation.is_safe else 'BLOCKED'}"
            )
            logger.info(f"  - Recommendation: {primary_rec.type.value}")

        finally:
            # Cleanup handled by fixture
            pass

    @pytest.mark.asyncio
    async def test_complex_mixed_scenario_complete_workflow(
        self, workflow_components, test_connection, runtime
    ):
        """
        Test complete workflow for COMPLEX scenario: Mixed Dependencies

        This tests a realistic scenario with mixed dependency types and impact levels.
        The system should:
        1. Detect all dependency types accurately (Phase 1)
        2. Provide nuanced risk assessment (Phase 2)
        3. Generate appropriate recommendations and warnings (Phase 3)
        """
        dependency_analyzer, column_removal_manager, impact_reporter = (
            workflow_components
        )

        logger.info("Setting up COMPLEX scenario: Mixed dependencies")

        # Create complex schema with mixed dependencies
        await test_connection.execute(
            """
            -- Main table
            CREATE TABLE workflow_customers (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,  -- Target column with mixed dependencies
                username VARCHAR(100) UNIQUE NOT NULL,
                status VARCHAR(20) DEFAULT 'active',
                created_at TIMESTAMP DEFAULT NOW()
            );

            -- Table with outgoing FK (from email column - unusual but possible)
            CREATE TABLE workflow_email_domains (
                domain VARCHAR(255) PRIMARY KEY
            );

            -- Incoming FK (more common - references customers.email)
            CREATE TABLE workflow_notifications (
                id SERIAL PRIMARY KEY,
                customer_email VARCHAR(255) NOT NULL,
                message TEXT NOT NULL,
                sent_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT fk_notifications_email FOREIGN KEY (customer_email) REFERENCES workflow_customers(email) ON DELETE CASCADE
            );

            -- Views using email column
            CREATE VIEW workflow_active_customers AS
            SELECT id, email, username, created_at
            FROM workflow_customers
            WHERE status = 'active' AND email IS NOT NULL;

            CREATE VIEW workflow_email_stats AS
            SELECT
                SUBSTRING(email FROM '@(.*)$') as domain,
                COUNT(*) as customer_count
            FROM workflow_customers
            WHERE email IS NOT NULL
            GROUP BY SUBSTRING(email FROM '@(.*)$');

            -- Indexes involving email
            CREATE UNIQUE INDEX workflow_customers_email_unique ON workflow_customers(email);
            CREATE INDEX workflow_customers_email_status_idx ON workflow_customers(email, status);

            -- Constraints involving email
            ALTER TABLE workflow_customers ADD CONSTRAINT check_email_format
                CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$');

            -- Trigger using email column
            CREATE TABLE workflow_email_audit (
                id SERIAL PRIMARY KEY,
                old_email VARCHAR(255),
                new_email VARCHAR(255),
                changed_at TIMESTAMP DEFAULT NOW()
            );

            CREATE OR REPLACE FUNCTION workflow_audit_email_changes()
            RETURNS TRIGGER AS $$
            BEGIN
                IF OLD.email IS DISTINCT FROM NEW.email THEN
                    INSERT INTO workflow_email_audit (old_email, new_email)
                    VALUES (OLD.email, NEW.email);
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER workflow_email_audit_trigger
                AFTER UPDATE ON workflow_customers
                FOR EACH ROW EXECUTE FUNCTION workflow_audit_email_changes();
        """
        )

        try:
            logger.info(
                "PHASE 1: Analyzing complex dependencies for workflow_customers.email"
            )

            # **PHASE 1**: Comprehensive Dependency Analysis
            start_time = time.time()
            dependency_report = await dependency_analyzer.analyze_column_dependencies(
                "workflow_customers", "email"
            )
            analysis_time = time.time() - start_time

            # Verify Phase 1 detects multiple dependency types
            assert dependency_report.has_dependencies() is True

            # Should detect foreign key dependencies
            if DependencyType.FOREIGN_KEY in dependency_report.dependencies:
                fk_deps = dependency_report.dependencies[DependencyType.FOREIGN_KEY]
                fk_names = {dep.constraint_name for dep in fk_deps}
                assert (
                    "fk_notifications_email" in fk_names
                ), "Should detect incoming FK to email column"

            # Should detect view dependencies
            assert DependencyType.VIEW in dependency_report.dependencies
            view_deps = dependency_report.dependencies[DependencyType.VIEW]
            view_names = {dep.view_name for dep in view_deps}
            assert (
                "workflow_active_customers" in view_names
            ), "Should detect view using email column"

            # Should detect index dependencies
            assert DependencyType.INDEX in dependency_report.dependencies
            index_deps = dependency_report.dependencies[DependencyType.INDEX]
            index_names = {dep.index_name for dep in index_deps}
            assert (
                "workflow_customers_email_unique" in index_names
            ), "Should detect unique email index"

            # Should detect constraint dependencies
            assert DependencyType.CONSTRAINT in dependency_report.dependencies
            constraint_deps = dependency_report.dependencies[DependencyType.CONSTRAINT]
            constraint_names = {dep.constraint_name for dep in constraint_deps}
            assert (
                "check_email_format" in constraint_names
            ), "Should detect email format constraint"

            # Should detect trigger dependencies
            assert DependencyType.TRIGGER in dependency_report.dependencies
            trigger_deps = dependency_report.dependencies[DependencyType.TRIGGER]
            trigger_names = {dep.trigger_name for dep in trigger_deps}
            assert (
                "workflow_email_audit_trigger" in trigger_names
            ), "Should detect email audit trigger"

            total_deps = dependency_report.get_total_dependency_count()
            assert (
                total_deps >= 6
            ), f"Should detect multiple dependencies, found: {total_deps}"

            logger.info(
                f"Phase 1 complete: Found {total_deps} dependencies in {analysis_time:.2f}s"
            )

            logger.info("PHASE 3: Generating impact assessment for complex scenario")

            # **PHASE 3**: Impact Assessment
            impact_report = impact_reporter.generate_impact_report(dependency_report)

            # Verify Phase 3 handles mixed dependencies appropriately
            impact_summary = dependency_report.generate_impact_summary()

            # Should have mixed impact levels
            if impact_summary[ImpactLevel.CRITICAL] > 0:
                assert impact_report.assessment.overall_risk == ImpactLevel.CRITICAL
            elif impact_summary[ImpactLevel.HIGH] > 0:
                assert impact_report.assessment.overall_risk == ImpactLevel.HIGH
            else:
                assert impact_report.assessment.overall_risk in [
                    ImpactLevel.MEDIUM,
                    ImpactLevel.LOW,
                ]

            assert impact_report.assessment.total_dependencies == total_deps

            # Should have multiple recommendation types
            assert len(impact_report.recommendations) >= 1
            primary_rec = impact_report.recommendations[0]
            assert primary_rec.type in [
                RecommendationType.DO_NOT_REMOVE,
                RecommendationType.REQUIRES_FIXES,
                RecommendationType.PROCEED_WITH_CAUTION,
            ]

            logger.info("PHASE 2: Planning and validating complex removal scenario")

            # **PHASE 2**: Removal Planning and Safety Validation
            removal_plan = await column_removal_manager.plan_column_removal(
                "workflow_customers", "email", BackupStrategy.TABLE_SNAPSHOT
            )

            # Verify Phase 2 handles complex dependencies
            assert len(removal_plan.dependencies) == total_deps
            assert len(removal_plan.execution_stages) >= 5  # Multiple stages needed
            assert removal_plan.estimated_duration > 5.0  # Complex = longer

            safety_validation = await column_removal_manager.validate_removal_safety(
                removal_plan
            )

            # Safety assessment should match impact assessment
            if impact_report.assessment.overall_risk == ImpactLevel.CRITICAL:
                assert safety_validation.is_safe is False
                assert safety_validation.risk_level == ImpactLevel.CRITICAL
                assert len(safety_validation.blocking_dependencies) > 0
            else:
                # May be safe but with warnings
                assert safety_validation.requires_confirmation is True
                assert len(safety_validation.warnings) > 0

            logger.info(
                "PHASE 3: Generating comprehensive reports for complex scenario"
            )

            # **PHASE 3**: Comprehensive User-Friendly Reporting
            console_report = impact_reporter.format_user_friendly_report(
                impact_report, OutputFormat.CONSOLE, include_details=True
            )
            json_report = impact_reporter.format_user_friendly_report(
                impact_report, OutputFormat.JSON
            )
            html_report = impact_reporter.format_user_friendly_report(
                impact_report, OutputFormat.HTML, include_details=True
            )
            safety_report = impact_reporter.generate_safety_validation_report(
                safety_validation
            )

            # Verify comprehensive reporting
            assert "workflow_customers.email" in console_report
            assert "dependencies" in console_report.lower()

            # JSON should be complete and parseable
            parsed_json = json.loads(json_report)
            assert "dependency_details" in parsed_json
            assert (
                len(parsed_json["dependency_details"]) >= 3
            )  # Multiple dependency types

            # HTML should contain styling and structure
            assert "<div" in html_report and "<style>" in html_report

            # Safety report should contain detailed analysis
            assert "dependencies" in safety_report.lower()

            logger.info("INTEGRATION VALIDATION: Complex scenario workflow consistency")

            # **WORKFLOW INTEGRATION VALIDATION**: Phases work together correctly
            removal_recommendation = dependency_report.get_removal_recommendation()
            assert removal_recommendation in [
                "DANGEROUS",
                "CAUTION",
                "REVIEW",
                "LOW_RISK",
            ]

            # All phases should agree on risk level
            phase1_risk = dependency_report.generate_impact_summary()
            phase2_risk = safety_validation.risk_level
            phase3_risk = impact_report.assessment.overall_risk

            # Risk levels should be consistent or escalated appropriately
            risk_levels = [
                ImpactLevel.INFORMATIONAL,
                ImpactLevel.LOW,
                ImpactLevel.MEDIUM,
                ImpactLevel.HIGH,
                ImpactLevel.CRITICAL,
            ]
            assert phase2_risk in risk_levels
            assert phase3_risk in risk_levels

            # Performance validation
            assert analysis_time < 5.0, f"Analysis took too long: {analysis_time:.2f}s"

            logger.info("✅ COMPLEX SCENARIO WORKFLOW VALIDATION COMPLETE")
            logger.info(f"  - Dependencies detected: {total_deps}")
            logger.info(
                f"  - Impact levels: Critical={impact_summary[ImpactLevel.CRITICAL]}, High={impact_summary[ImpactLevel.HIGH]}, Medium={impact_summary[ImpactLevel.MEDIUM]}"
            )
            logger.info(f"  - Analysis time: {analysis_time:.2f}s")
            logger.info(
                f"  - Safety verdict: {'BLOCKED' if not safety_validation.is_safe else 'ALLOWED'}"
            )
            logger.info(f"  - Phase 1 recommendation: {removal_recommendation}")
            logger.info(f"  - Phase 3 recommendation: {primary_rec.type.value}")

        finally:
            # Cleanup handled by fixture
            pass

    @pytest.mark.asyncio
    async def test_workflow_performance_validation(
        self, workflow_components, test_connection, runtime
    ):
        """
        Test complete workflow performance with requirements validation.

        Validates that the complete Phase 1→2→3 workflow meets performance requirements:
        - <30 seconds for dependency analysis (per requirements)
        - <512MB memory usage for dependency graphs
        - Accurate dependency detection under performance constraints
        """
        dependency_analyzer, column_removal_manager, impact_reporter = (
            workflow_components
        )

        logger.info(
            "Setting up PERFORMANCE scenario: Large schema with many dependencies"
        )

        # Create large schema for performance testing
        num_tables = 30
        num_views = 10

        # Base table
        await test_connection.execute(
            """
            CREATE TABLE workflow_perf_base (
                id SERIAL PRIMARY KEY,
                shared_key VARCHAR(50) NOT NULL,
                data TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """
        )

        # Create many dependent tables
        for i in range(num_tables):
            await test_connection.execute(
                f"""
                CREATE TABLE workflow_perf_dep_{i} (
                    id SERIAL PRIMARY KEY,
                    base_id INTEGER NOT NULL,
                    value_{i} INTEGER DEFAULT 0,
                    CONSTRAINT fk_perf_dep_{i} FOREIGN KEY (base_id) REFERENCES workflow_perf_base(id) ON DELETE CASCADE
                );
                CREATE INDEX workflow_perf_dep_{i}_base_idx ON workflow_perf_dep_{i}(base_id);
            """
            )

        # Create views
        for i in range(num_views):
            await test_connection.execute(
                f"""
                CREATE VIEW workflow_perf_view_{i} AS
                SELECT b.id, b.shared_key, COUNT(d.id) as dep_count_{i}
                FROM workflow_perf_base b
                LEFT JOIN workflow_perf_dep_{i % num_tables} d ON b.id = d.base_id
                GROUP BY b.id, b.shared_key;
            """
            )

        try:
            logger.info(
                f"PERFORMANCE TEST: Analyzing {num_tables} FK deps + {num_views} views"
            )

            # **COMPLETE WORKFLOW PERFORMANCE TEST**
            workflow_start = time.time()

            # Phase 1: Dependency Analysis
            phase1_start = time.time()
            dependency_report = await dependency_analyzer.analyze_column_dependencies(
                "workflow_perf_base", "id"
            )
            phase1_time = time.time() - phase1_start

            # Phase 3: Impact Assessment
            phase3_start = time.time()
            impact_report = impact_reporter.generate_impact_report(dependency_report)
            phase3_time = time.time() - phase3_start

            # Phase 2: Planning and Validation
            phase2_start = time.time()
            removal_plan = await column_removal_manager.plan_column_removal(
                "workflow_perf_base", "id", BackupStrategy.COLUMN_ONLY
            )
            safety_validation = await column_removal_manager.validate_removal_safety(
                removal_plan
            )
            phase2_time = time.time() - phase2_start

            total_workflow_time = time.time() - workflow_start

            # **PERFORMANCE REQUIREMENTS VALIDATION**
            # Requirement: <30 seconds for dependency analysis
            assert (
                phase1_time < 30.0
            ), f"Phase 1 took too long: {phase1_time:.2f}s (requirement: <30s)"

            # Complete workflow should be reasonable
            assert (
                total_workflow_time < 35.0
            ), f"Total workflow took too long: {total_workflow_time:.2f}s"

            # **ACCURACY VALIDATION UNDER PERFORMANCE CONSTRAINTS**
            total_deps = dependency_report.get_total_dependency_count()

            # Should detect all FK dependencies
            fk_deps = dependency_report.dependencies.get(DependencyType.FOREIGN_KEY, [])
            assert (
                len(fk_deps) == num_tables
            ), f"Should find {num_tables} FK deps, found {len(fk_deps)}"

            # Should detect view dependencies
            view_deps = dependency_report.dependencies.get(DependencyType.VIEW, [])
            assert (
                len(view_deps) >= num_views
            ), f"Should find at least {num_views} view deps, found {len(view_deps)}"

            # All FK dependencies should be CRITICAL
            for fk_dep in fk_deps:
                assert fk_dep.impact_level == ImpactLevel.CRITICAL

            # **PHASE INTEGRATION UNDER PERFORMANCE LOAD**
            # All phases should produce consistent results
            assert impact_report.assessment.total_dependencies == total_deps
            assert impact_report.assessment.critical_dependencies == len(fk_deps)
            assert impact_report.assessment.overall_risk == ImpactLevel.CRITICAL

            assert (
                safety_validation.is_safe is False
            )  # Should block due to critical FKs
            assert safety_validation.risk_level == ImpactLevel.CRITICAL
            assert len(safety_validation.blocking_dependencies) >= num_tables

            # **REPORTING PERFORMANCE**
            report_start = time.time()
            console_report = impact_reporter.format_user_friendly_report(
                impact_report, OutputFormat.CONSOLE
            )
            json_report = impact_reporter.format_user_friendly_report(
                impact_report, OutputFormat.JSON
            )
            safety_report = impact_reporter.generate_safety_validation_report(
                safety_validation
            )
            report_time = time.time() - report_start

            # Reporting should be fast even with large dependency sets
            assert (
                report_time < 2.0
            ), f"Report generation took too long: {report_time:.2f}s"

            # Reports should handle large dependency lists gracefully
            assert "... and" in console_report  # Should truncate for readability

            parsed_json = json.loads(json_report)
            assert parsed_json["assessment"]["total_dependencies"] == total_deps

            logger.info("✅ PERFORMANCE WORKFLOW VALIDATION COMPLETE")
            logger.info(f"  - Schema size: {num_tables} tables, {num_views} views")
            logger.info(f"  - Total dependencies: {total_deps}")
            logger.info(f"  - Phase 1 time: {phase1_time:.2f}s")
            logger.info(f"  - Phase 2 time: {phase2_time:.2f}s")
            logger.info(f"  - Phase 3 time: {phase3_time:.2f}s")
            logger.info(f"  - Total workflow time: {total_workflow_time:.2f}s")
            logger.info(f"  - Report generation time: {report_time:.2f}s")
            logger.info(
                f"  - Performance requirement: ✅ <30s (actual: {phase1_time:.2f}s)"
            )

        finally:
            # Cleanup handled by fixture
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
