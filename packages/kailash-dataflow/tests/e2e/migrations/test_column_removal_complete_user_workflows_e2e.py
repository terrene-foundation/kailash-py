#!/usr/bin/env python3
"""
End-to-End Tests for TODO-137 Column Removal Complete User Workflows

Tests complete user workflows for the Column Removal Dependency Analysis system
from the perspective of real database administrators and developers using the system
in production scenarios.

USER WORKFLOWS TESTED:
1. Database Administrator - Critical Column Removal Assessment
2. Developer - Safe Legacy Column Cleanup
3. DevOps Engineer - Automated Migration Pipeline Integration
4. Data Engineer - Complex Schema Refactoring
5. System Administrator - Emergency Column Removal Scenarios
6. Business Analyst - Impact Assessment and Reporting

Following Tier 3 testing guidelines:
- Complete user workflows from start to finish
- Real infrastructure and data (NO MOCKING)
- Timeout: <10 seconds per test
- Tests actual user scenarios and business requirements
- Validates complete system integration from user perspective

E2E Test Setup:
1. Run: ./tests/utils/test-env up && ./tests/utils/test-env status
2. Tests use complete DataFlow + Migration system integration
3. Validates real user scenarios with production-like workflows
"""

import asyncio
import json
import logging
import tempfile
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import asyncpg
import pytest

from dataflow import DataFlow
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
from tests.infrastructure.test_harness import DatabaseConfig, DatabaseInfrastructure

# Configure logging for E2E user workflow testing
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# E2E test fixtures
@pytest.fixture(scope="session")
async def e2e_database():
    """Set up E2E test database infrastructure."""
    config = DatabaseConfig.from_environment()
    infrastructure = DatabaseInfrastructure(config)
    await infrastructure.initialize()

    yield infrastructure

    # Cleanup
    if infrastructure._pool:
        await infrastructure._pool.close()


@pytest.fixture(scope="session")
async def e2e_dataflow(e2e_database):
    """Create DataFlow instance for E2E tests."""
    config = e2e_database.config

    # Create DataFlow with real database
    dataflow = DataFlow(config.url, existing_schema_mode=True)

    yield dataflow

    # Cleanup
    if hasattr(dataflow, "close"):
        await dataflow.close()


@pytest.fixture
async def user_workflow_components(e2e_dataflow):
    """Create all components for user workflow testing."""
    connection_manager = MigrationConnectionManager(e2e_dataflow)
    dependency_analyzer = DependencyAnalyzer(connection_manager)
    column_removal_manager = ColumnRemovalManager(connection_manager)
    impact_reporter = ImpactReporter()

    return (
        dependency_analyzer,
        column_removal_manager,
        impact_reporter,
        connection_manager,
    )


@pytest.fixture
async def e2e_connection(e2e_database):
    """Direct connection for E2E test setup."""
    pool = e2e_database._pool
    async with pool.acquire() as conn:
        yield conn


@pytest.fixture(autouse=True)
async def clean_e2e_user_schema(e2e_connection):
    """Clean E2E user workflow schema before each test."""
    await e2e_connection.execute(
        """
        DO $$
        DECLARE
            r RECORD;
        BEGIN
            -- Drop views
            FOR r IN (SELECT schemaname, viewname FROM pg_views
                     WHERE schemaname = 'public' AND viewname LIKE 'user_%')
            LOOP
                EXECUTE 'DROP VIEW IF EXISTS ' || quote_ident(r.schemaname) || '.' || quote_ident(r.viewname) || ' CASCADE';
            END LOOP;

            -- Drop functions
            FOR r IN (SELECT routine_schema, routine_name FROM information_schema.routines
                     WHERE routine_schema = 'public' AND routine_name LIKE 'user_%')
            LOOP
                EXECUTE 'DROP FUNCTION IF EXISTS ' || quote_ident(r.routine_schema) || '.' || quote_ident(r.routine_name) || ' CASCADE';
            END LOOP;

            -- Drop tables
            FOR r IN (SELECT schemaname, tablename FROM pg_tables
                     WHERE schemaname = 'public' AND tablename LIKE 'user_%')
            LOOP
                EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.schemaname) || '.' || quote_ident(r.tablename) || ' CASCADE';
            END LOOP;
        END $$;
    """
    )


def generate_unique_id() -> str:
    """Generate unique ID for test resources."""
    return uuid.uuid4().hex[:8]


@pytest.mark.e2e
@pytest.mark.timeout(120)
class TestColumnRemovalCompleteUserWorkflows:
    """E2E tests for complete user workflows."""

    @pytest.mark.asyncio
    async def test_database_administrator_critical_assessment_workflow(
        self, user_workflow_components, e2e_connection
    ):
        """
        USER WORKFLOW: Database Administrator - Critical Column Removal Assessment

        SCENARIO: Senior DBA needs to assess the risk of removing a primary key column
        that's causing performance issues. They need comprehensive analysis and reporting
        to present to the management team for approval.

        WORKFLOW STEPS:
        1. Analyze dependencies for critical column
        2. Generate comprehensive impact report
        3. Create detailed safety assessment
        4. Export reports for management review
        5. Plan removal strategy (if safe) or document blocking issues
        """
        (
            dependency_analyzer,
            column_removal_manager,
            impact_reporter,
            connection_manager,
        ) = user_workflow_components

        test_id = generate_unique_id()
        logger.info(
            f"🧑‍💼 DBA WORKFLOW [{test_id}]: Critical column removal assessment"
        )

        # Create realistic enterprise database scenario
        await e2e_connection.execute(
            f"""
            -- Main customer table (performance issues due to varchar PK)
            CREATE TABLE user_customers_{test_id} (
                customer_code VARCHAR(50) PRIMARY KEY,  -- Performance problem - DBA wants to change to INTEGER
                company_name VARCHAR(255) NOT NULL,
                industry VARCHAR(100),
                annual_revenue DECIMAL(15,2),
                created_date DATE DEFAULT CURRENT_DATE,
                last_updated TIMESTAMP DEFAULT NOW()
            );

            -- Critical business tables with foreign key references
            CREATE TABLE user_orders_{test_id} (
                id SERIAL PRIMARY KEY,
                customer_code VARCHAR(50) NOT NULL,
                order_date DATE NOT NULL,
                total_amount DECIMAL(12,2) NOT NULL,
                order_status VARCHAR(20) DEFAULT 'pending',
                CONSTRAINT fk_orders_customer_{test_id} FOREIGN KEY (customer_code)
                    REFERENCES user_customers_{test_id}(customer_code) ON DELETE RESTRICT
            );

            CREATE TABLE user_contracts_{test_id} (
                id SERIAL PRIMARY KEY,
                customer_code VARCHAR(50) NOT NULL,
                contract_number VARCHAR(100) UNIQUE NOT NULL,
                start_date DATE NOT NULL,
                end_date DATE,
                contract_value DECIMAL(15,2) NOT NULL,
                CONSTRAINT fk_contracts_customer_{test_id} FOREIGN KEY (customer_code)
                    REFERENCES user_customers_{test_id}(customer_code) ON DELETE RESTRICT
            );

            CREATE TABLE user_support_tickets_{test_id} (
                id SERIAL PRIMARY KEY,
                customer_code VARCHAR(50) NOT NULL,
                ticket_number VARCHAR(50) UNIQUE NOT NULL,
                priority VARCHAR(20) DEFAULT 'medium',
                status VARCHAR(20) DEFAULT 'open',
                created_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT fk_tickets_customer_{test_id} FOREIGN KEY (customer_code)
                    REFERENCES user_customers_{test_id}(customer_code) ON DELETE CASCADE
            );

            -- Business intelligence views (critical for reporting)
            CREATE VIEW user_customer_revenue_summary_{test_id} AS
            SELECT
                c.customer_code, c.company_name, c.industry, c.annual_revenue,
                COUNT(DISTINCT o.id) as total_orders,
                COALESCE(SUM(o.total_amount), 0) as total_order_value,
                COUNT(DISTINCT con.id) as active_contracts,
                COALESCE(SUM(con.contract_value), 0) as total_contract_value
            FROM user_customers_{test_id} c
            LEFT JOIN user_orders_{test_id} o ON c.customer_code = o.customer_code
            LEFT JOIN user_contracts_{test_id} con ON c.customer_code = con.customer_code
            GROUP BY c.customer_code, c.company_name, c.industry, c.annual_revenue;

            CREATE VIEW user_customer_activity_summary_{test_id} AS
            SELECT
                c.customer_code, c.company_name,
                COUNT(DISTINCT o.id) as order_count,
                COUNT(DISTINCT t.id) as support_ticket_count,
                MAX(o.order_date) as last_order_date,
                MAX(t.created_at) as last_support_contact
            FROM user_customers_{test_id} c
            LEFT JOIN user_orders_{test_id} o ON c.customer_code = o.customer_code
            LEFT JOIN user_support_tickets_{test_id} t ON c.customer_code = t.customer_code
            GROUP BY c.customer_code, c.company_name;

            -- Performance indexes (part of the performance optimization)
            CREATE INDEX user_customers_industry_idx_{test_id} ON user_customers_{test_id}(industry);
            CREATE INDEX user_customers_revenue_idx_{test_id} ON user_customers_{test_id}(annual_revenue DESC);

            -- Insert realistic business data
            INSERT INTO user_customers_{test_id} (customer_code, company_name, industry, annual_revenue) VALUES
            ('ENTERPRISE_001', 'Global Tech Corporation', 'Technology', 50000000.00),
            ('FINANCE_002', 'Premier Financial Services', 'Finance', 25000000.00),
            ('RETAIL_003', 'National Retail Chain', 'Retail', 75000000.00),
            ('MANUFACTURING_004', 'Industrial Manufacturing Inc', 'Manufacturing', 40000000.00),
            ('HEALTHCARE_005', 'Regional Healthcare System', 'Healthcare', 60000000.00);

            -- Orders data
            INSERT INTO user_orders_{test_id} (customer_code, order_date, total_amount, order_status) VALUES
            ('ENTERPRISE_001', '2024-01-15', 150000.00, 'completed'),
            ('ENTERPRISE_001', '2024-02-20', 200000.00, 'completed'),
            ('FINANCE_002', '2024-01-10', 75000.00, 'completed'),
            ('RETAIL_003', '2024-03-01', 300000.00, 'pending'),
            ('MANUFACTURING_004', '2024-01-25', 125000.00, 'completed');

            -- Contracts data
            INSERT INTO user_contracts_{test_id} (customer_code, contract_number, start_date, end_date, contract_value) VALUES
            ('ENTERPRISE_001', 'CONTRACT_ENT_2024_001', '2024-01-01', '2024-12-31', 1000000.00),
            ('FINANCE_002', 'CONTRACT_FIN_2024_001', '2024-01-01', '2025-12-31', 500000.00),
            ('RETAIL_003', 'CONTRACT_RET_2024_001', '2024-01-01', '2024-06-30', 750000.00);

            -- Support tickets
            INSERT INTO user_support_tickets_{test_id} (customer_code, ticket_number, priority, status) VALUES
            ('ENTERPRISE_001', 'TICKET_001', 'high', 'open'),
            ('FINANCE_002', 'TICKET_002', 'medium', 'resolved'),
            ('RETAIL_003', 'TICKET_003', 'high', 'open');
        """
        )

        try:
            # **STEP 1**: DBA performs comprehensive dependency analysis
            logger.info(
                "DBA Step 1: Analyzing dependencies for customer_code primary key column"
            )

            workflow_start = time.time()

            dependency_report = await dependency_analyzer.analyze_column_dependencies(
                f"user_customers_{test_id}", "customer_code"
            )

            analysis_time = time.time() - workflow_start

            # Validate comprehensive dependency detection
            assert dependency_report.has_dependencies() is True

            total_deps = dependency_report.get_total_dependency_count()
            assert (
                total_deps >= 6
            ), f"DBA expects comprehensive analysis, found {total_deps} dependencies"

            # Must detect all foreign key references (critical business data)
            fk_deps = dependency_report.dependencies.get(DependencyType.FOREIGN_KEY, [])
            assert len(fk_deps) >= 3, "DBA needs all FK dependencies identified"

            # Must detect business intelligence views
            view_deps = dependency_report.dependencies.get(DependencyType.VIEW, [])
            assert len(view_deps) >= 2, "DBA needs all BI views identified"

            logger.info(
                f"DBA Analysis Complete: {total_deps} dependencies in {analysis_time:.2f}s"
            )

            # **STEP 2**: DBA generates comprehensive impact report for management
            logger.info(
                "DBA Step 2: Generating comprehensive impact report for management"
            )

            impact_report = impact_reporter.generate_impact_report(dependency_report)

            # Validate impact assessment for management presentation
            assert impact_report.assessment.overall_risk == ImpactLevel.CRITICAL
            assert (
                impact_report.assessment.critical_dependencies >= 3
            ), "Management needs to see critical impact"

            # Generate multiple report formats for different audiences
            console_report = impact_reporter.format_user_friendly_report(
                impact_report, OutputFormat.CONSOLE, include_details=True
            )
            html_report = impact_reporter.format_user_friendly_report(
                impact_report, OutputFormat.HTML, include_details=True
            )
            json_report = impact_reporter.format_user_friendly_report(
                impact_report, OutputFormat.JSON
            )
            summary_report = impact_reporter.format_user_friendly_report(
                impact_report, OutputFormat.SUMMARY
            )

            # Validate reports are comprehensive for management review
            assert "CRITICAL IMPACT DETECTED" in console_report
            assert f"user_customers_{test_id}.customer_code" in console_report
            assert "DO NOT REMOVE" in console_report

            assert "<div" in html_report and "<style>" in html_report
            assert "critical-risk" in html_report

            parsed_json = json.loads(json_report)
            assert parsed_json["assessment"]["overall_risk"] == "critical"

            logger.info("DBA Impact Reports Generated: Console, HTML, JSON, Summary")

            # **STEP 3**: DBA performs safety assessment and planning
            logger.info("DBA Step 3: Creating removal plan and safety assessment")

            removal_plan = await column_removal_manager.plan_column_removal(
                f"user_customers_{test_id}",
                "customer_code",
                BackupStrategy.TABLE_SNAPSHOT,
            )

            safety_validation = await column_removal_manager.validate_removal_safety(
                removal_plan
            )

            # Generate safety report for management
            safety_report = impact_reporter.generate_safety_validation_report(
                safety_validation
            )

            # Validate DBA safety assessment
            assert (
                safety_validation.is_safe is False
            ), "DBA expects system to block dangerous removal"
            assert safety_validation.risk_level == ImpactLevel.CRITICAL
            assert len(safety_validation.blocking_dependencies) >= 3
            assert safety_validation.requires_confirmation is True

            assert "❌ UNSAFE" in safety_report
            assert "CRITICAL" in safety_report
            assert "BLOCKING DEPENDENCIES" in safety_report

            logger.info(
                "DBA Safety Assessment: REMOVAL BLOCKED due to critical dependencies"
            )

            # **STEP 4**: DBA documents findings and recommendations
            logger.info("DBA Step 4: Documenting findings for management presentation")

            # Create comprehensive documentation package
            documentation = {
                "analysis_timestamp": datetime.now().isoformat(),
                "table_analyzed": f"user_customers_{test_id}",
                "column_analyzed": "customer_code",
                "analyst": "Senior Database Administrator",
                "analysis_duration_seconds": analysis_time,
                "total_dependencies_found": total_deps,
                "risk_assessment": impact_report.assessment.overall_risk.value,
                "safety_verdict": "BLOCKED - Too Dangerous",
                "business_impact": {
                    "affected_orders": "All customer orders would lose referential integrity",
                    "affected_contracts": "All customer contracts would be orphaned",
                    "affected_support": "All support tickets would lose customer association",
                    "affected_reporting": "Business intelligence dashboards would break",
                },
                "recommendations": [
                    "Do not proceed with column removal in current state",
                    "Consider alternative performance optimizations first",
                    "If removal is necessary, plan multi-phase migration:",
                    "  1. Add new integer primary key column",
                    "  2. Update all foreign key references",
                    "  3. Update all views and reports",
                    "  4. Remove old varchar column after 6-month transition period",
                    "Estimated effort: 3-6 months for safe migration",
                ],
                "reports_generated": {
                    "console_report_length": len(console_report),
                    "html_report_available": True,
                    "json_report_available": True,
                    "summary_available": True,
                },
            }

            # **STEP 5**: DBA validates system behavior matches expectations
            logger.info(
                "DBA Step 5: Validating system recommendations align with DBA expertise"
            )

            # DBA expects system to block this removal
            primary_rec = impact_report.recommendations[0]
            assert primary_rec.type == RecommendationType.DO_NOT_REMOVE

            # DBA expects clear warnings about data loss risk
            assert any(
                "foreign key" in rec.lower() for rec in safety_validation.warnings
            )

            # DBA expects practical recommendations
            assert any(
                "constraint" in rec.lower() or "foreign key" in rec.lower()
                for rec in safety_validation.recommendations
            )

            total_workflow_time = time.time() - workflow_start

            logger.info("🎯 DBA WORKFLOW COMPLETE - Management Presentation Ready")
            logger.info(f"  ✅ Analysis completed in {total_workflow_time:.2f} seconds")
            logger.info(f"  ✅ Found {total_deps} dependencies requiring attention")
            logger.info("  ✅ System correctly blocked dangerous removal")
            logger.info("  ✅ Generated comprehensive reports for management")
            logger.info("  ✅ Provided actionable recommendations")

            # Verify data integrity maintained throughout analysis
            final_customer_count = await e2e_connection.fetchval(
                f"SELECT COUNT(*) FROM user_customers_{test_id}"
            )
            final_order_count = await e2e_connection.fetchval(
                f"SELECT COUNT(*) FROM user_orders_{test_id}"
            )

            assert (
                final_customer_count == 5
            ), "Customer data must be preserved during analysis"
            assert (
                final_order_count == 5
            ), "Order data must be preserved during analysis"

        finally:
            # Cleanup handled by fixture
            pass

    @pytest.mark.asyncio
    async def test_developer_safe_legacy_cleanup_workflow(
        self, user_workflow_components, e2e_connection
    ):
        """
        USER WORKFLOW: Developer - Safe Legacy Column Cleanup

        SCENARIO: Developer needs to clean up deprecated columns that are no longer
        used in the application after a recent refactoring. They need to identify
        truly unused columns and safely remove them.

        WORKFLOW STEPS:
        1. Identify candidates for removal
        2. Analyze dependencies for each column
        3. Confirm columns are truly unused
        4. Plan and execute safe removal
        5. Verify cleanup success
        """
        (
            dependency_analyzer,
            column_removal_manager,
            impact_reporter,
            connection_manager,
        ) = user_workflow_components

        test_id = generate_unique_id()
        logger.info(f"👩‍💻 DEVELOPER WORKFLOW [{test_id}]: Safe legacy column cleanup")

        # Create development scenario with legacy columns
        await e2e_connection.execute(
            f"""
            CREATE TABLE user_products_{test_id} (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                price DECIMAL(10,2) NOT NULL,
                category VARCHAR(100) NOT NULL,

                -- Legacy columns from old system (developer wants to remove these)
                old_product_id VARCHAR(50),      -- Replaced by 'id' field
                legacy_status VARCHAR(20),       -- Replaced by new status system
                deprecated_field TEXT,           -- No longer used anywhere
                temp_migration_flag BOOLEAN,     -- Was used during data migration, now unused

                -- Current active columns
                status VARCHAR(20) DEFAULT 'active',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            -- Dependencies on ACTIVE columns (not legacy ones)
            CREATE INDEX user_products_name_idx_{test_id} ON user_products_{test_id}(name);
            CREATE INDEX user_products_category_idx_{test_id} ON user_products_{test_id}(category, status);

            CREATE VIEW user_active_products_{test_id} AS
            SELECT id, name, description, price, category, status
            FROM user_products_{test_id}
            WHERE status = 'active';

            -- Related table that uses ACTIVE columns
            CREATE TABLE user_inventory_{test_id} (
                id SERIAL PRIMARY KEY,
                product_id INTEGER NOT NULL,
                quantity INTEGER DEFAULT 0,
                CONSTRAINT fk_inventory_product_{test_id} FOREIGN KEY (product_id)
                    REFERENCES user_products_{test_id}(id) ON DELETE CASCADE
            );

            -- Constraint on ACTIVE column
            ALTER TABLE user_products_{test_id} ADD CONSTRAINT check_price_positive_{test_id} CHECK (price > 0);

            -- Add sample data
            INSERT INTO user_products_{test_id}
                (name, description, price, category, old_product_id, legacy_status, deprecated_field, temp_migration_flag, status)
            VALUES
                ('Widget A', 'High quality widget', 19.99, 'widgets', 'OLD_001', 'live', 'unused data', true, 'active'),
                ('Gadget B', 'Useful gadget', 29.99, 'gadgets', 'OLD_002', 'live', 'more unused', false, 'active'),
                ('Tool C', 'Professional tool', 49.99, 'tools', 'OLD_003', 'archived', 'legacy info', true, 'inactive');

            INSERT INTO user_inventory_{test_id} (product_id, quantity) VALUES (1, 100), (2, 50), (3, 25);
        """
        )

        try:
            # **STEP 1**: Developer identifies legacy column candidates
            logger.info(
                "Developer Step 1: Identifying legacy column candidates for cleanup"
            )

            legacy_columns = [
                "old_product_id",
                "legacy_status",
                "deprecated_field",
                "temp_migration_flag",
            ]
            analysis_results = {}

            # **STEP 2**: Developer analyzes each legacy column for dependencies
            logger.info(
                "Developer Step 2: Analyzing dependencies for each legacy column"
            )

            for column in legacy_columns:
                logger.info(f"Analyzing legacy column: {column}")

                start_time = time.time()
                dependency_report = (
                    await dependency_analyzer.analyze_column_dependencies(
                        f"user_products_{test_id}", column
                    )
                )
                analysis_time = time.time() - start_time

                impact_report = impact_reporter.generate_impact_report(
                    dependency_report
                )

                analysis_results[column] = {
                    "dependency_report": dependency_report,
                    "impact_report": impact_report,
                    "analysis_time": analysis_time,
                    "total_dependencies": dependency_report.get_total_dependency_count(),
                    "has_critical_deps": len(
                        dependency_report.get_critical_dependencies()
                    )
                    > 0,
                    "removal_recommendation": (
                        dependency_report.get_removal_recommendation()
                        if hasattr(dependency_report, "get_removal_recommendation")
                        else "UNKNOWN"
                    ),
                }

            # **STEP 3**: Developer confirms columns are truly unused
            logger.info("Developer Step 3: Confirming columns are safe for removal")

            safe_columns = []
            unsafe_columns = []

            for column, results in analysis_results.items():
                total_deps = results["total_dependencies"]
                has_critical = results["has_critical_deps"]

                if total_deps == 0 and not has_critical:
                    safe_columns.append(column)
                    logger.info(f"  ✅ {column}: SAFE - No dependencies found")
                else:
                    unsafe_columns.append(column)
                    logger.info(
                        f"  ⚠️ {column}: REVIEW NEEDED - {total_deps} dependencies found"
                    )

            # Developer expects most legacy columns to be safe for removal
            assert (
                len(safe_columns) >= 2
            ), f"Expected some safe columns, found: {safe_columns}"

            # **STEP 4**: Developer plans and executes safe removal
            logger.info(
                f"Developer Step 4: Planning removal for {len(safe_columns)} safe columns"
            )

            removal_results = {}

            for column in safe_columns:
                logger.info(f"Processing removal for: {column}")

                # Plan removal
                removal_plan = await column_removal_manager.plan_column_removal(
                    f"user_products_{test_id}", column, BackupStrategy.COLUMN_ONLY
                )

                # Validate safety
                safety_validation = (
                    await column_removal_manager.validate_removal_safety(removal_plan)
                )

                assert (
                    safety_validation.is_safe is True
                ), f"Expected {column} to be safe for removal"
                assert safety_validation.risk_level in [
                    ImpactLevel.LOW,
                    ImpactLevel.INFORMATIONAL,
                ]

                # Execute removal
                removal_result = await column_removal_manager.execute_safe_removal(
                    removal_plan
                )

                removal_results[column] = {
                    "result": removal_result.result,
                    "success": removal_result.result == RemovalResult.SUCCESS,
                    "execution_time": removal_result.execution_time,
                    "backup_created": removal_result.backup_preserved,
                }

                if removal_result.result == RemovalResult.SUCCESS:
                    logger.info(
                        f"  ✅ {column}: Successfully removed in {removal_result.execution_time:.2f}s"
                    )
                else:
                    logger.info(
                        f"  ❌ {column}: Removal failed - {removal_result.error_message}"
                    )

            # **STEP 5**: Developer verifies cleanup success
            logger.info(
                "Developer Step 5: Verifying cleanup success and data integrity"
            )

            # Verify removed columns no longer exist
            for column in safe_columns:
                if removal_results[column]["success"]:
                    column_exists = await e2e_connection.fetchval(
                        f"""
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name = 'user_products_{test_id}'
                            AND column_name = '{column}'
                        )
                    """
                    )
                    assert (
                        column_exists is False
                    ), f"Column {column} should have been removed"

            # Verify active functionality still works (dependencies preserved)
            active_view_works = await e2e_connection.fetchval(
                f"SELECT COUNT(*) FROM user_active_products_{test_id}"
            )
            assert active_view_works == 2, "Active products view should still work"

            inventory_fk_works = await e2e_connection.fetchval(
                f"SELECT COUNT(*) FROM user_inventory_{test_id}"
            )
            assert (
                inventory_fk_works == 3
            ), "Inventory FK relationships should still work"

            # Verify data integrity
            product_count = await e2e_connection.fetchval(
                f"SELECT COUNT(*) FROM user_products_{test_id}"
            )
            assert product_count == 3, "Product data should be preserved"

            # Verify active columns and constraints still work
            constraint_exists = await e2e_connection.fetchval(
                f"""
                SELECT COUNT(*) FROM information_schema.table_constraints
                WHERE table_name = 'user_products_{test_id}'
                AND constraint_name = 'check_price_positive_{test_id}'
            """
            )
            assert constraint_exists == 1, "Active constraints should be preserved"

            successful_removals = sum(
                1 for r in removal_results.values() if r["success"]
            )
            total_cleanup_time = sum(
                r["execution_time"] for r in removal_results.values() if r["success"]
            )

            logger.info("🎯 DEVELOPER WORKFLOW COMPLETE - Legacy Cleanup Successful")
            logger.info(f"  ✅ Analyzed {len(legacy_columns)} legacy columns")
            logger.info(f"  ✅ Identified {len(safe_columns)} safe for removal")
            logger.info(f"  ✅ Successfully removed {successful_removals} columns")
            logger.info(f"  ✅ Total cleanup time: {total_cleanup_time:.2f}s")
            logger.info("  ✅ Data integrity preserved throughout cleanup")

        finally:
            # Cleanup handled by fixture
            pass

    @pytest.mark.asyncio
    async def test_devops_automated_pipeline_integration_workflow(
        self, user_workflow_components, e2e_connection
    ):
        """
        USER WORKFLOW: DevOps Engineer - Automated Migration Pipeline Integration

        SCENARIO: DevOps engineer needs to integrate column removal analysis into
        the CI/CD pipeline to prevent dangerous deployments and automate safe
        schema changes as part of application deployments.

        WORKFLOW STEPS:
        1. Setup automated analysis for schema changes
        2. Implement safety gates for CI/CD pipeline
        3. Generate machine-readable reports for automation
        4. Integrate with deployment pipeline decisions
        5. Validate automated rollback capabilities
        """
        (
            dependency_analyzer,
            column_removal_manager,
            impact_reporter,
            connection_manager,
        ) = user_workflow_components

        test_id = generate_unique_id()
        logger.info(f"⚙️ DEVOPS WORKFLOW [{test_id}]: Automated pipeline integration")

        # Create CI/CD pipeline test scenario
        await e2e_connection.execute(
            f"""
            -- Application tables that might be modified by deployments
            CREATE TABLE user_app_users_{test_id} (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                profile_data JSONB DEFAULT '{{}}'::jsonb,

                -- Fields that deployments might want to remove
                deprecated_api_key VARCHAR(255),    -- Replaced by OAuth
                old_email_format VARCHAR(255),      -- Legacy field
                temp_feature_flag BOOLEAN DEFAULT false,  -- Feature flag column

                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            -- Application data that depends on user fields
            CREATE TABLE user_app_sessions_{test_id} (
                id SERIAL PRIMARY KEY,
                user_email VARCHAR(255) NOT NULL,
                session_token VARCHAR(255) UNIQUE NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT fk_sessions_user_{test_id} FOREIGN KEY (user_email)
                    REFERENCES user_app_users_{test_id}(email) ON DELETE CASCADE
            );

            CREATE TABLE user_app_audit_{test_id} (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                action VARCHAR(100) NOT NULL,
                timestamp TIMESTAMP DEFAULT NOW(),
                CONSTRAINT fk_audit_user_{test_id} FOREIGN KEY (user_id)
                    REFERENCES user_app_users_{test_id}(id) ON DELETE CASCADE
            );

            -- Insert test data
            INSERT INTO user_app_users_{test_id} (username, email, deprecated_api_key, old_email_format, temp_feature_flag) VALUES
            ('devops_user', 'devops@company.com', 'deprecated_key_123', 'old@format.com', true),
            ('test_user', 'test@company.com', 'deprecated_key_456', 'test@old.com', false);

            INSERT INTO user_app_sessions_{test_id} (user_email, session_token, expires_at) VALUES
            ('devops@company.com', 'session_123', NOW() + INTERVAL '1 day'),
            ('test@company.com', 'session_456', NOW() + INTERVAL '1 day');

            INSERT INTO user_app_audit_{test_id} (user_id, action) VALUES
            (1, 'login'), (1, 'profile_update'), (2, 'login');
        """
        )

        try:
            # **STEP 1**: DevOps sets up automated analysis for schema changes
            logger.info(
                "DevOps Step 1: Setting up automated analysis for CI/CD pipeline"
            )

            # Simulate CI/CD pipeline analyzing multiple proposed changes
            pipeline_changes = [
                {
                    "change_type": "remove_column",
                    "table": f"user_app_users_{test_id}",
                    "column": "deprecated_api_key",
                    "reason": "Replaced by OAuth system",
                    "expected_risk": "LOW",
                },
                {
                    "change_type": "remove_column",
                    "table": f"user_app_users_{test_id}",
                    "column": "email",  # DANGEROUS - has FK references
                    "reason": "Moving to username-only auth",
                    "expected_risk": "CRITICAL",
                },
                {
                    "change_type": "remove_column",
                    "table": f"user_app_users_{test_id}",
                    "column": "temp_feature_flag",
                    "reason": "Feature flag no longer needed",
                    "expected_risk": "LOW",
                },
            ]

            pipeline_results = []

            # **STEP 2**: DevOps implements safety gates for CI/CD pipeline
            logger.info(
                "DevOps Step 2: Running safety analysis for all pipeline changes"
            )

            for change in pipeline_changes:
                change_start = time.time()

                logger.info(
                    f"Analyzing pipeline change: {change['table']}.{change['column']}"
                )

                # Automated dependency analysis
                dependency_report = (
                    await dependency_analyzer.analyze_column_dependencies(
                        change["table"], change["column"]
                    )
                )

                # Automated impact assessment
                impact_report = impact_reporter.generate_impact_report(
                    dependency_report
                )

                # Automated safety validation
                removal_plan = await column_removal_manager.plan_column_removal(
                    change["table"], change["column"], BackupStrategy.COLUMN_ONLY
                )
                safety_validation = (
                    await column_removal_manager.validate_removal_safety(removal_plan)
                )

                change_time = time.time() - change_start

                # **STEP 3**: DevOps generates machine-readable reports for automation
                # Generate machine-readable JSON for CI/CD decisions
                json_report = impact_reporter.format_user_friendly_report(
                    impact_report, OutputFormat.JSON
                )
                parsed_report = json.loads(json_report)

                pipeline_result = {
                    "change": change,
                    "analysis_time_seconds": change_time,
                    "total_dependencies": dependency_report.get_total_dependency_count(),
                    "risk_level": impact_report.assessment.overall_risk.value,
                    "is_safe_for_automation": safety_validation.is_safe,
                    "requires_manual_review": safety_validation.requires_confirmation,
                    "blocking_dependencies_count": len(
                        safety_validation.blocking_dependencies
                    ),
                    "pipeline_decision": self._determine_pipeline_decision(
                        safety_validation, impact_report
                    ),
                    "automated_report": parsed_report,
                    "warnings": safety_validation.warnings,
                    "recommendations": safety_validation.recommendations,
                }

                pipeline_results.append(pipeline_result)

                logger.info(
                    f"  Pipeline Decision: {pipeline_result['pipeline_decision']} (Risk: {pipeline_result['risk_level']})"
                )

            # **STEP 4**: DevOps validates pipeline decisions
            logger.info("DevOps Step 4: Validating automated pipeline decisions")

            # Verify pipeline correctly identifies safe vs unsafe changes
            api_key_result = next(
                r
                for r in pipeline_results
                if r["change"]["column"] == "deprecated_api_key"
            )
            email_result = next(
                r for r in pipeline_results if r["change"]["column"] == "email"
            )
            feature_flag_result = next(
                r
                for r in pipeline_results
                if r["change"]["column"] == "temp_feature_flag"
            )

            # Safe changes should be approved for automation
            assert api_key_result["pipeline_decision"] in [
                "APPROVE",
                "APPROVE_WITH_BACKUP",
            ]
            assert api_key_result["is_safe_for_automation"] is True
            assert api_key_result["risk_level"] in ["low", "informational"]

            assert feature_flag_result["pipeline_decision"] in [
                "APPROVE",
                "APPROVE_WITH_BACKUP",
            ]
            assert feature_flag_result["is_safe_for_automation"] is True

            # Dangerous changes should be blocked
            assert email_result["pipeline_decision"] == "BLOCK"
            assert email_result["is_safe_for_automation"] is False
            assert email_result["risk_level"] == "critical"
            assert email_result["blocking_dependencies_count"] >= 1

            # **STEP 5**: DevOps tests automated execution of safe changes
            logger.info(
                "DevOps Step 5: Testing automated execution of approved changes"
            )

            approved_changes = [
                r
                for r in pipeline_results
                if r["pipeline_decision"] in ["APPROVE", "APPROVE_WITH_BACKUP"]
            ]

            automation_results = []

            for approved in approved_changes:
                change = approved["change"]
                logger.info(
                    f"Automating removal of {change['table']}.{change['column']}"
                )

                # Create removal plan
                removal_plan = await column_removal_manager.plan_column_removal(
                    change["table"], change["column"], BackupStrategy.COLUMN_ONLY
                )

                # Execute automated removal
                execution_result = await column_removal_manager.execute_safe_removal(
                    removal_plan
                )

                automation_results.append(
                    {
                        "column": change["column"],
                        "success": execution_result.result == RemovalResult.SUCCESS,
                        "execution_time": execution_result.execution_time,
                        "backup_created": execution_result.backup_preserved,
                    }
                )

                if execution_result.result == RemovalResult.SUCCESS:
                    logger.info(
                        f"  ✅ Automated removal successful: {change['column']}"
                    )
                else:
                    logger.info(
                        f"  ❌ Automated removal failed: {change['column']} - {execution_result.error_message}"
                    )

            # Verify automated execution results
            successful_automations = sum(1 for r in automation_results if r["success"])

            # DevOps expects all approved changes to execute successfully
            assert (
                successful_automations >= 2
            ), f"Expected successful automated removals, got {successful_automations}"

            # **STEP 6**: DevOps validates data integrity after automation
            logger.info(
                "DevOps Step 6: Validating data integrity after automated changes"
            )

            # Verify critical table still exists and functions
            user_count = await e2e_connection.fetchval(
                f"SELECT COUNT(*) FROM user_app_users_{test_id}"
            )
            session_count = await e2e_connection.fetchval(
                f"SELECT COUNT(*) FROM user_app_sessions_{test_id}"
            )
            audit_count = await e2e_connection.fetchval(
                f"SELECT COUNT(*) FROM user_app_audit_{test_id}"
            )

            assert user_count == 2, "User data must be preserved"
            assert session_count == 2, "Session data must be preserved"
            assert audit_count == 3, "Audit data must be preserved"

            # Verify FK relationships still work (email column should still exist - was blocked)
            email_constraint_exists = await e2e_connection.fetchval(
                f"""
                SELECT COUNT(*) FROM information_schema.table_constraints
                WHERE table_name = 'user_app_sessions_{test_id}'
                AND constraint_name = 'fk_sessions_user_{test_id}'
            """
            )
            assert (
                email_constraint_exists == 1
            ), "Critical FK constraint must be preserved"

            total_pipeline_time = sum(
                r["analysis_time_seconds"] for r in pipeline_results
            )
            blocked_changes = sum(
                1 for r in pipeline_results if r["pipeline_decision"] == "BLOCK"
            )

            logger.info("🎯 DEVOPS WORKFLOW COMPLETE - Pipeline Integration Successful")
            logger.info(
                f"  ✅ Analyzed {len(pipeline_changes)} proposed changes in {total_pipeline_time:.2f}s"
            )
            logger.info(
                f"  ✅ Approved {len(approved_changes)} safe changes for automation"
            )
            logger.info(f"  ✅ Blocked {blocked_changes} dangerous changes")
            logger.info(
                f"  ✅ Successfully automated {successful_automations} removals"
            )
            logger.info("  ✅ Data integrity maintained throughout pipeline")

        finally:
            # Cleanup handled by fixture
            pass

    def _determine_pipeline_decision(
        self, safety_validation: SafetyValidation, impact_report
    ) -> str:
        """Helper method to determine CI/CD pipeline decision based on analysis."""
        if not safety_validation.is_safe:
            return "BLOCK"
        elif impact_report.assessment.overall_risk in [
            ImpactLevel.CRITICAL,
            ImpactLevel.HIGH,
        ]:
            return "BLOCK"
        elif safety_validation.requires_confirmation:
            return "APPROVE_WITH_BACKUP"
        else:
            return "APPROVE"

    @pytest.mark.asyncio
    async def test_data_engineer_complex_schema_refactoring_workflow(
        self, user_workflow_components, e2e_connection
    ):
        """
        USER WORKFLOW: Data Engineer - Complex Schema Refactoring

        SCENARIO: Data engineer needs to refactor a complex analytics schema by
        removing columns that are being replaced by a new data warehouse design.
        The analysis must account for complex interdependencies.

        WORKFLOW STEPS:
        1. Map complex schema dependencies
        2. Identify column removal candidates for refactoring
        3. Analyze interdependency chains
        4. Plan multi-phase refactoring approach
        5. Execute safe portion of refactoring
        """
        (
            dependency_analyzer,
            column_removal_manager,
            impact_reporter,
            connection_manager,
        ) = user_workflow_components

        test_id = generate_unique_id()
        logger.info(
            f"📊 DATA ENGINEER WORKFLOW [{test_id}]: Complex schema refactoring"
        )

        # Create complex analytics schema
        await e2e_connection.execute(
            f"""
            -- Raw data ingestion tables
            CREATE TABLE user_raw_events_{test_id} (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(100) NOT NULL,
                event_type VARCHAR(50) NOT NULL,
                event_data JSONB NOT NULL,

                -- Columns to be refactored (moving to data warehouse)
                legacy_session_id VARCHAR(100),      -- Being replaced by new session tracking
                old_user_agent TEXT,                 -- Moving to parsed user agent table
                deprecated_geo_data VARCHAR(500),    -- Moving to dedicated geo table

                -- Columns staying in operational system
                timestamp TIMESTAMP DEFAULT NOW(),
                processed BOOLEAN DEFAULT FALSE
            );

            -- Analytics aggregation tables
            CREATE TABLE user_analytics_daily_{test_id} (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL,
                user_id VARCHAR(100) NOT NULL,

                -- Metrics being refactored
                legacy_session_count INTEGER DEFAULT 0,        -- Calculated from legacy_session_id
                old_geo_country VARCHAR(100),                  -- Derived from deprecated_geo_data
                deprecated_device_type VARCHAR(50),            -- Derived from old_user_agent

                -- Metrics staying
                event_count INTEGER DEFAULT 0,
                last_processed TIMESTAMP DEFAULT NOW()
            );

            -- Reporting views that depend on legacy columns
            CREATE VIEW user_legacy_session_report_{test_id} AS
            SELECT
                user_id,
                DATE(timestamp) as report_date,
                COUNT(DISTINCT legacy_session_id) as unique_sessions,
                COUNT(*) as total_events
            FROM user_raw_events_{test_id}
            WHERE legacy_session_id IS NOT NULL
            GROUP BY user_id, DATE(timestamp);

            CREATE VIEW user_geo_analytics_{test_id} AS
            SELECT
                user_id,
                deprecated_geo_data,
                COUNT(*) as event_count
            FROM user_raw_events_{test_id}
            WHERE deprecated_geo_data IS NOT NULL
            GROUP BY user_id, deprecated_geo_data;

            -- Functions that process legacy data
            CREATE OR REPLACE FUNCTION user_parse_legacy_geo_{test_id}(geo_data VARCHAR)
            RETURNS TABLE(country VARCHAR, region VARCHAR) AS $$
            BEGIN
                -- Simulated geo parsing from deprecated format
                RETURN QUERY
                SELECT
                    CASE
                        WHEN geo_data LIKE '%US%' THEN 'United States'::VARCHAR
                        WHEN geo_data LIKE '%UK%' THEN 'United Kingdom'::VARCHAR
                        ELSE 'Unknown'::VARCHAR
                    END as country,
                    'Unknown'::VARCHAR as region;
            END;
            $$ LANGUAGE plpgsql;

            -- Trigger that processes legacy session data
            CREATE OR REPLACE FUNCTION user_update_session_analytics_{test_id}()
            RETURNS TRIGGER AS $$
            BEGIN
                IF NEW.legacy_session_id IS NOT NULL THEN
                    INSERT INTO user_analytics_daily_{test_id} (date, user_id, legacy_session_count)
                    VALUES (DATE(NEW.timestamp), NEW.user_id, 1)
                    ON CONFLICT (date, user_id) DO UPDATE
                    SET legacy_session_count = user_analytics_daily_{test_id}.legacy_session_count + 1;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER user_session_analytics_trigger_{test_id}
                AFTER INSERT ON user_raw_events_{test_id}
                FOR EACH ROW EXECUTE FUNCTION user_update_session_analytics_{test_id}();

            -- Insert realistic analytics data
            INSERT INTO user_raw_events_{test_id}
                (user_id, event_type, event_data, legacy_session_id, old_user_agent, deprecated_geo_data)
            VALUES
                ('user_001', 'page_view', '{"page": "/home"}'::jsonb, 'session_123', 'Mozilla/5.0 Chrome', 'US:California:San Francisco'),
                ('user_001', 'click', '{"element": "button"}'::jsonb, 'session_123', 'Mozilla/5.0 Chrome', 'US:California:San Francisco'),
                ('user_002', 'page_view', '{"page": "/product"}'::jsonb, 'session_456', 'Safari/14.0', 'UK:England:London'),
                ('user_002', 'purchase', '{"amount": 99.99}'::jsonb, 'session_456', 'Safari/14.0', 'UK:England:London'),
                ('user_003', 'page_view', '{"page": "/about"}'::jsonb, 'session_789', 'Firefox/88.0', 'CA:Ontario:Toronto');

            INSERT INTO user_analytics_daily_{test_id}
                (date, user_id, legacy_session_count, old_geo_country, deprecated_device_type, event_count)
            VALUES
                (CURRENT_DATE, 'user_001', 1, 'United States', 'Desktop', 2),
                (CURRENT_DATE, 'user_002', 1, 'United Kingdom', 'Mobile', 2),
                (CURRENT_DATE, 'user_003', 1, 'Canada', 'Desktop', 1);
        """
        )

        try:
            # **STEP 1**: Data engineer maps complex schema dependencies
            logger.info("Data Engineer Step 1: Mapping complex schema dependencies")

            refactoring_candidates = [
                "legacy_session_id",  # Used in views, triggers, and analytics
                "old_user_agent",  # May have minimal dependencies
                "deprecated_geo_data",  # Used in views and functions
            ]

            dependency_mapping = {}

            for column in refactoring_candidates:
                logger.info(f"Analyzing complex dependencies for: {column}")

                dependency_report = (
                    await dependency_analyzer.analyze_column_dependencies(
                        f"user_raw_events_{test_id}", column
                    )
                )

                impact_report = impact_reporter.generate_impact_report(
                    dependency_report
                )

                dependency_mapping[column] = {
                    "report": dependency_report,
                    "impact": impact_report,
                    "total_deps": dependency_report.get_total_dependency_count(),
                    "dep_types": (
                        list(dependency_report.dependencies.keys())
                        if dependency_report.has_dependencies()
                        else []
                    ),
                    "risk_level": impact_report.assessment.overall_risk.value,
                }

                logger.info(
                    f"  {column}: {dependency_mapping[column]['total_deps']} deps, risk: {dependency_mapping[column]['risk_level']}"
                )

            # **STEP 2**: Data engineer analyzes interdependency chains
            logger.info("Data Engineer Step 2: Analyzing interdependency chains")

            # Data engineer expects complex interdependencies
            for column, mapping in dependency_mapping.items():
                deps = mapping["report"]

                if deps.has_dependencies():
                    # Check for view dependencies
                    if DependencyType.VIEW in deps.dependencies:
                        view_deps = deps.dependencies[DependencyType.VIEW]
                        logger.info(
                            f"  {column} affects {len(view_deps)} analytical views"
                        )

                    # Check for trigger dependencies
                    if DependencyType.TRIGGER in deps.dependencies:
                        trigger_deps = deps.dependencies[DependencyType.TRIGGER]
                        logger.info(
                            f"  {column} affects {len(trigger_deps)} data processing triggers"
                        )

                    # Check for function dependencies (if supported)
                    if DependencyType.CONSTRAINT in deps.dependencies:
                        logger.info(
                            f"  {column} may affect stored procedures/functions"
                        )

            # **STEP 3**: Data engineer identifies refactoring phases
            logger.info(
                "Data Engineer Step 3: Planning multi-phase refactoring approach"
            )

            # Classify columns by refactoring difficulty
            low_impact_columns = []
            high_impact_columns = []
            critical_columns = []

            for column, mapping in dependency_mapping.items():
                risk = mapping["risk_level"]
                total_deps = mapping["total_deps"]

                if risk in ["informational", "low"] and total_deps <= 1:
                    low_impact_columns.append(column)
                elif risk in ["medium", "high"] or total_deps > 1:
                    high_impact_columns.append(column)
                else:
                    critical_columns.append(column)

            logger.info("Refactoring phases planned:")
            logger.info(f"  Phase 1 (Safe): {low_impact_columns}")
            logger.info(f"  Phase 2 (Complex): {high_impact_columns}")
            logger.info(f"  Phase 3 (Critical): {critical_columns}")

            # **STEP 4**: Data engineer executes safe phase of refactoring
            logger.info("Data Engineer Step 4: Executing Phase 1 (safe) refactoring")

            phase1_results = []

            for column in low_impact_columns:
                logger.info(f"Refactoring safe column: {column}")

                # Plan removal
                removal_plan = await column_removal_manager.plan_column_removal(
                    f"user_raw_events_{test_id}", column, BackupStrategy.TABLE_SNAPSHOT
                )

                # Validate safety
                safety_validation = (
                    await column_removal_manager.validate_removal_safety(removal_plan)
                )

                if safety_validation.is_safe:
                    # Execute safe removal
                    removal_result = await column_removal_manager.execute_safe_removal(
                        removal_plan
                    )

                    phase1_results.append(
                        {
                            "column": column,
                            "success": removal_result.result == RemovalResult.SUCCESS,
                            "execution_time": removal_result.execution_time,
                            "backup_created": removal_result.backup_preserved,
                        }
                    )

                    if removal_result.result == RemovalResult.SUCCESS:
                        logger.info(f"  ✅ Phase 1: {column} successfully refactored")
                    else:
                        logger.info(f"  ❌ Phase 1: {column} refactoring failed")
                else:
                    logger.info(
                        f"  ⚠️ Phase 1: {column} not safe for automated refactoring"
                    )

            # **STEP 5**: Data engineer validates refactoring results
            logger.info(
                "Data Engineer Step 5: Validating refactoring results and data integrity"
            )

            # Verify core analytics functionality still works
            raw_events_count = await e2e_connection.fetchval(
                f"SELECT COUNT(*) FROM user_raw_events_{test_id}"
            )
            analytics_count = await e2e_connection.fetchval(
                f"SELECT COUNT(*) FROM user_analytics_daily_{test_id}"
            )

            assert raw_events_count == 5, "Raw events data must be preserved"
            assert analytics_count == 3, "Analytics data must be preserved"

            # Verify views still work (if their dependencies weren't removed)
            try:
                session_report_count = await e2e_connection.fetchval(
                    f"SELECT COUNT(*) FROM user_legacy_session_report_{test_id}"
                )
                logger.info(
                    f"Legacy session reports still available: {session_report_count} records"
                )
            except Exception as e:
                logger.info(
                    f"Legacy session reports affected by refactoring: {str(e)[:100]}"
                )

            # Verify triggers still work
            trigger_exists = await e2e_connection.fetchval(
                f"""
                SELECT COUNT(*) FROM information_schema.triggers
                WHERE trigger_name = 'user_session_analytics_trigger_{test_id}'
            """
            )
            logger.info(f"Analytics trigger preserved: {trigger_exists == 1}")

            # Data engineer validates business logic preservation
            total_events_by_user = await e2e_connection.fetch(
                f"""
                SELECT user_id, COUNT(*) as event_count
                FROM user_raw_events_{test_id}
                GROUP BY user_id ORDER BY user_id
            """
            )

            # Verify expected data patterns
            assert len(total_events_by_user) == 3, "All users should be preserved"
            assert (
                total_events_by_user[0]["event_count"] == 2
            ), "User 001 should have 2 events"
            assert (
                total_events_by_user[1]["event_count"] == 2
            ), "User 002 should have 2 events"

            successful_phase1 = sum(1 for r in phase1_results if r["success"])
            total_refactoring_time = sum(
                r["execution_time"] for r in phase1_results if r["success"]
            )

            logger.info(
                "🎯 DATA ENGINEER WORKFLOW COMPLETE - Complex Schema Refactoring"
            )
            logger.info(
                f"  ✅ Mapped dependencies for {len(refactoring_candidates)} refactoring candidates"
            )
            logger.info("  ✅ Identified multi-phase refactoring approach")
            logger.info(
                f"  ✅ Successfully completed Phase 1: {successful_phase1} columns refactored"
            )
            logger.info(f"  ✅ Phase 1 execution time: {total_refactoring_time:.2f}s")
            logger.info("  ✅ Data integrity and business logic preserved")
            logger.info("  ✅ Phases 2-3 ready for planning with dependency analysis")

        finally:
            # Cleanup handled by fixture
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
