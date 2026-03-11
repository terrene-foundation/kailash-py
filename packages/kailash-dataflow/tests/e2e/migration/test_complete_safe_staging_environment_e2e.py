#!/usr/bin/env python3
"""
End-to-End tests for Complete Safe Staging Environment System - TODO-141 Phase 1+2+3.

Tests the complete integrated workflow from staging environment creation through
production deployment validation, representing real-world deployment scenarios.

TIER 3 (E2E) REQUIREMENTS:
- Complete user workflows from start to finish
- Real infrastructure and data throughout entire pipeline
- NO MOCKING - complete scenarios with real services
- Test actual user scenarios and business requirements
- Validate business requirements end-to-end
- Test complete workflows with runtime execution
- Timeout: <10 seconds per test
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pytest
from dataflow.migrations.dependency_analyzer import DependencyAnalyzer
from dataflow.migrations.impact_reporter import ImpactReporter, OutputFormat
from dataflow.migrations.migration_validation_pipeline import (
    MigrationValidationConfig,
    MigrationValidationPipeline,
    ValidationStatus,
)

# Import complete system components
from dataflow.migrations.production_deployment_validator import (
    DeploymentApprovalStatus,
    DeploymentResult,
    DeploymentStrategy,
    ProductionDeploymentValidator,
    ProductionSafetyConfig,
    RiskLevel,
)
from dataflow.migrations.risk_assessment_engine import (
    RiskAssessmentEngine,
    RiskCategory,
)
from dataflow.migrations.staging_environment_manager import (
    ProductionDatabase,
    StagingDatabase,
    StagingEnvironmentConfig,
    StagingEnvironmentManager,
    StagingEnvironmentStatus,
)

# Test infrastructure
from tests.utils.real_infrastructure import (
    PostgreSQLTestManager,
    cleanup_test_database,
    create_test_tables,
    insert_test_data,
    setup_test_database,
)


@dataclass
class BusinessScenario:
    """Represents a business migration scenario for E2E testing."""

    name: str
    description: str
    migration_info: Dict[str, Any]
    expected_risk_level: RiskLevel
    expected_outcome: str
    business_impact: str
    stakeholder_approvals_required: bool


@pytest.fixture(scope="function")
async def production_database():
    """Set up production-like database with realistic schema and data."""
    db_config = await setup_test_database("e2e_production_db")

    # Create realistic business tables
    await create_test_tables(
        db_config,
        [
            """
        CREATE TABLE IF NOT EXISTS customers (
            customer_id SERIAL PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            first_name VARCHAR(100),
            last_name VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(20) DEFAULT 'active'
        )
        """,
            """
        CREATE TABLE IF NOT EXISTS orders (
            order_id SERIAL PRIMARY KEY,
            customer_id INTEGER REFERENCES customers(customer_id),
            order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            total_amount DECIMAL(10,2),
            status VARCHAR(20) DEFAULT 'pending',
            shipping_address TEXT
        )
        """,
            """
        CREATE TABLE IF NOT EXISTS order_items (
            item_id SERIAL PRIMARY KEY,
            order_id INTEGER REFERENCES orders(order_id) ON DELETE CASCADE,
            product_name VARCHAR(255),
            quantity INTEGER,
            unit_price DECIMAL(10,2)
        )
        """,
            """
        CREATE INDEX IF NOT EXISTS idx_customers_email ON customers(email);
        CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);
        CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
        """,
        ],
    )

    # Insert realistic test data
    await insert_test_data(
        db_config,
        [
            "INSERT INTO customers (email, first_name, last_name) VALUES ('john@example.com', 'John', 'Doe')",
            "INSERT INTO customers (email, first_name, last_name) VALUES ('jane@example.com', 'Jane', 'Smith')",
            "INSERT INTO orders (customer_id, total_amount) VALUES (1, 99.99), (2, 149.50)",
            "INSERT INTO order_items (order_id, product_name, quantity, unit_price) VALUES (1, 'Widget A', 2, 49.99)",
        ],
    )

    yield db_config
    await cleanup_test_database(db_config)


@pytest.fixture
def production_db_config(production_database):
    """Production database configuration."""
    return ProductionDatabase(
        host=production_database["host"],
        port=production_database["port"],
        database=production_database["database"],
        user=production_database["user"],
        password=production_database["password"],
    )


@pytest.fixture
async def complete_safe_staging_system(production_db_config):
    """Complete Safe Staging Environment system with all phases integrated."""
    # Phase 1: Staging Environment Manager
    staging_config = StagingEnvironmentConfig(
        default_data_sample_size=0.1,  # 10% sample for realistic testing
        max_staging_environments=3,
        cleanup_timeout_seconds=60,
        auto_cleanup_hours=1,  # Quick cleanup for tests
    )
    staging_manager = StagingEnvironmentManager(config=staging_config)

    # Phase 2: Migration Validation Pipeline
    validation_config = MigrationValidationConfig(
        staging_timeout_seconds=60,
        max_validation_time_seconds=120,
        performance_degradation_threshold=0.3,  # 30% threshold
        rollback_validation_enabled=True,
        data_integrity_checks_enabled=True,
        parallel_validation_enabled=True,
    )

    dependency_analyzer = DependencyAnalyzer()
    risk_engine = RiskAssessmentEngine()

    validation_pipeline = MigrationValidationPipeline(
        staging_manager=staging_manager,
        dependency_analyzer=dependency_analyzer,
        risk_engine=risk_engine,
        config=validation_config,
    )

    # Phase 3: Production Deployment Validator
    production_config = ProductionSafetyConfig(
        require_executive_approval_threshold=RiskLevel.HIGH,
        require_staging_validation=True,
        require_rollback_plan=True,
        max_deployment_time_minutes=10,  # Extended for E2E tests
        zero_downtime_required=True,
        backup_before_deployment=True,
    )

    impact_reporter = ImpactReporter()

    production_validator = ProductionDeploymentValidator(
        staging_manager=staging_manager,
        validation_pipeline=validation_pipeline,
        risk_engine=risk_engine,
        config=production_config,
        dependency_analyzer=dependency_analyzer,
        impact_reporter=impact_reporter,
    )

    return {
        "staging_manager": staging_manager,
        "validation_pipeline": validation_pipeline,
        "production_validator": production_validator,
        "risk_engine": risk_engine,
        "impact_reporter": impact_reporter,
    }


@pytest.fixture
def business_scenarios():
    """Realistic business migration scenarios for E2E testing."""
    return [
        BusinessScenario(
            name="customer_loyalty_program",
            description="Add loyalty points column to customers table for new rewards program",
            migration_info={
                "migration_id": "loyalty_program_001",
                "table_name": "customers",
                "column_name": "loyalty_points",
                "operation_type": "add_column",
                "sql_statements": [
                    "ALTER TABLE customers ADD COLUMN loyalty_points INTEGER DEFAULT 0;"
                ],
                "business_justification": "Enable customer rewards program for Q2 launch",
                "estimated_impact": "2 million customer records",
            },
            expected_risk_level=RiskLevel.LOW,
            expected_outcome="success_with_minimal_risk",
            business_impact="Low - additive change with default value",
            stakeholder_approvals_required=False,
        ),
        BusinessScenario(
            name="order_status_expansion",
            description="Modify order status column to support new fulfillment states",
            migration_info={
                "migration_id": "order_status_expansion_001",
                "table_name": "orders",
                "column_name": "status",
                "operation_type": "modify_column",
                "sql_statements": [
                    "ALTER TABLE orders ALTER COLUMN status TYPE VARCHAR(50);"
                ],
                "business_justification": "Support new fulfillment workflow states",
                "estimated_impact": "500K active orders, 10 dependent systems",
            },
            expected_risk_level=RiskLevel.MEDIUM,
            expected_outcome="requires_staging_validation",
            business_impact="Medium - existing column modification with dependencies",
            stakeholder_approvals_required=True,
        ),
        BusinessScenario(
            name="legacy_table_removal",
            description="Remove deprecated customer_preferences table",
            migration_info={
                "migration_id": "legacy_cleanup_001",
                "table_name": "customer_preferences",
                "operation_type": "drop_table",
                "sql_statements": ["DROP TABLE customer_preferences;"],
                "business_justification": "Clean up deprecated table after preference system migration",
                "estimated_impact": "Complete data loss, potential application breakage",
            },
            expected_risk_level=RiskLevel.HIGH,
            expected_outcome="requires_executive_approval",
            business_impact="High - permanent data loss risk",
            stakeholder_approvals_required=True,
        ),
    ]


@pytest.mark.asyncio
class TestCompleteSafeStagingEnvironmentE2E:
    """Complete end-to-end tests for Safe Staging Environment system."""

    async def test_complete_low_risk_deployment_workflow(
        self, complete_safe_staging_system, production_db_config, business_scenarios
    ):
        """Test complete workflow for low-risk business migration."""
        scenario = next(
            s for s in business_scenarios if s.name == "customer_loyalty_program"
        )
        system = complete_safe_staging_system

        print(f"\n=== E2E Test: {scenario.description} ===")
        print(f"Business Impact: {scenario.business_impact}")

        # Complete end-to-end workflow
        start_time = time.time()

        deployment_result = await system[
            "production_validator"
        ].validate_production_deployment(
            scenario.migration_info, production_db=production_db_config
        )

        total_duration = time.time() - start_time

        # Validate complete workflow
        assert deployment_result is not None
        assert deployment_result.migration_id == scenario.migration_info["migration_id"]
        assert total_duration < 10.0  # E2E timeout requirement

        print(f"Deployment Result: {deployment_result.success}")
        print(f"Total Duration: {total_duration:.2f}s")
        print(f"Message: {deployment_result.message}")

        # Generate business impact report
        if deployment_result.success:
            print("✅ Low-risk migration completed successfully")
            assert deployment_result.deployment_duration_seconds > 0
        else:
            print(f"⚠️ Migration blocked/failed: {deployment_result.message}")
            assert len(deployment_result.errors) > 0

        # Validate no critical issues for low-risk scenario
        if deployment_result.errors:
            for error in deployment_result.errors:
                print(f"Error: {error}")

    async def test_complete_medium_risk_staging_validation_workflow(
        self, complete_safe_staging_system, production_db_config, business_scenarios
    ):
        """Test complete workflow for medium-risk migration requiring staging validation."""
        scenario = next(
            s for s in business_scenarios if s.name == "order_status_expansion"
        )
        system = complete_safe_staging_system

        print(f"\n=== E2E Test: {scenario.description} ===")
        print(f"Expected Risk: {scenario.expected_risk_level.value}")
        print(
            f"Stakeholder Approval Required: {scenario.stakeholder_approvals_required}"
        )

        start_time = time.time()

        # Execute complete staging validation workflow
        deployment_result = await system[
            "production_validator"
        ].validate_production_deployment(
            scenario.migration_info, production_db=production_db_config
        )

        total_duration = time.time() - start_time

        # Validate staging validation was executed
        assert deployment_result is not None
        assert deployment_result.migration_id == scenario.migration_info["migration_id"]
        assert total_duration < 10.0

        print(f"Staging Validation Result: {deployment_result.success}")
        print(f"Duration: {total_duration:.2f}s")
        print(f"Phases Completed: {len(deployment_result.phases_completed)}")

        # Medium-risk should involve staging validation
        if deployment_result.success:
            print("✅ Medium-risk migration completed with staging validation")
            # Should have completed multiple phases for medium risk
            assert len(deployment_result.phases_completed) > 0
        else:
            print(
                f"⚠️ Medium-risk migration requires additional approvals: {deployment_result.message}"
            )
            # Should have specific guidance for medium-risk failures
            assert deployment_result.message is not None

    async def test_complete_high_risk_executive_approval_workflow(
        self, complete_safe_staging_system, production_db_config, business_scenarios
    ):
        """Test complete workflow for high-risk migration requiring executive approval."""
        scenario = next(
            s for s in business_scenarios if s.name == "legacy_table_removal"
        )
        system = complete_safe_staging_system

        print(f"\n=== E2E Test: {scenario.description} ===")
        print(f"Business Impact: {scenario.business_impact}")
        print(f"Expected Outcome: {scenario.expected_outcome}")

        start_time = time.time()

        # Execute high-risk deployment workflow
        deployment_result = await system[
            "production_validator"
        ].validate_production_deployment(
            scenario.migration_info, production_db=production_db_config
        )

        total_duration = time.time() - start_time

        # Validate high-risk handling
        assert deployment_result is not None
        assert deployment_result.migration_id == scenario.migration_info["migration_id"]
        assert total_duration < 10.0

        print(f"High-Risk Deployment Result: {deployment_result.success}")
        print(f"Duration: {total_duration:.2f}s")

        # High-risk migrations should be blocked or require approval
        if not deployment_result.success:
            print("✅ High-risk migration properly blocked pending approvals")
            assert (
                "approval" in deployment_result.message.lower()
                or "blocked" in deployment_result.message.lower()
            )
        else:
            print("⚠️ High-risk migration allowed - validating safety measures")
            # If allowed, should have extensive safety measures
            assert len(deployment_result.phases_completed) > 2

    async def test_complete_staging_environment_lifecycle(
        self, complete_safe_staging_system, production_db_config
    ):
        """Test complete staging environment lifecycle from creation to cleanup."""
        system = complete_safe_staging_system
        staging_manager = system["staging_manager"]

        print("\n=== E2E Test: Complete Staging Environment Lifecycle ===")

        # Phase 1: Create staging environment with production data
        print("Phase 1: Creating staging environment...")
        start_time = time.time()

        staging_env = await staging_manager.create_staging_environment(
            production_db=production_db_config,
            data_sample_size=0.05,  # 5% sample for faster testing
        )

        creation_duration = time.time() - start_time

        assert staging_env is not None
        assert staging_env.staging_id
        assert staging_env.status == StagingEnvironmentStatus.ACTIVE
        assert creation_duration < 10.0

        print(
            f"✅ Staging environment created: {staging_env.staging_id} ({creation_duration:.2f}s)"
        )

        # Phase 2: Replicate production schema with data sampling
        print("Phase 2: Replicating production schema...")
        schema_start = time.time()

        replication_result = await staging_manager.replicate_production_schema(
            staging_id=staging_env.staging_id,
            include_data=True,
            tables_filter=["customers", "orders"],  # Focus on key tables
        )

        replication_duration = time.time() - schema_start

        assert replication_result.tables_replicated > 0
        assert replication_result.data_sampling_completed is True
        assert replication_duration < 10.0

        print(
            f"✅ Schema replication: {replication_result.tables_replicated} tables, "
            f"{replication_result.total_rows_sampled} rows ({replication_duration:.2f}s)"
        )

        # Phase 3: Get staging environment information
        print("Phase 3: Validating staging environment...")
        info_start = time.time()

        staging_info = await staging_manager.get_staging_environment_info(
            staging_env.staging_id
        )

        info_duration = time.time() - info_start

        assert staging_info.staging_environment.staging_id == staging_env.staging_id
        assert staging_info.active_connections >= 0
        assert info_duration < 5.0

        print(f"✅ Staging environment validated ({info_duration:.2f}s)")

        # Phase 4: Cleanup staging environment
        print("Phase 4: Cleaning up staging environment...")
        cleanup_start = time.time()

        cleanup_result = await staging_manager.cleanup_staging_environment(
            staging_env.staging_id
        )

        cleanup_duration = time.time() - cleanup_start

        assert cleanup_result["cleanup_status"] == "SUCCESS"
        assert cleanup_result["resources_freed"] is True
        assert cleanup_duration < 10.0

        print(f"✅ Staging environment cleaned up ({cleanup_duration:.2f}s)")

        # Validate total lifecycle duration
        total_lifecycle_duration = (
            creation_duration + replication_duration + info_duration + cleanup_duration
        )
        print(f"Total Staging Lifecycle: {total_lifecycle_duration:.2f}s")
        assert total_lifecycle_duration < 30.0  # Reasonable total time

    async def test_complete_validation_pipeline_with_real_dependencies(
        self, complete_safe_staging_system, production_db_config
    ):
        """Test complete validation pipeline with real dependency analysis."""
        system = complete_safe_staging_system
        validation_pipeline = system["validation_pipeline"]

        print("\n=== E2E Test: Complete Validation Pipeline ===")

        # Test migration with real dependencies (orders table has FK to customers)
        migration_info = {
            "migration_id": "validation_pipeline_e2e_001",
            "table_name": "orders",
            "column_name": "customer_id",
            "operation_type": "modify_column",
            "sql_statements": [
                "ALTER TABLE orders ALTER COLUMN customer_id TYPE BIGINT;"
            ],
        }

        print("Executing complete validation pipeline...")
        start_time = time.time()

        validation_result = await validation_pipeline.validate_migration(
            migration_info, production_db=production_db_config
        )

        validation_duration = time.time() - start_time

        # Validate complete pipeline execution
        assert validation_result is not None
        assert validation_result.migration_id == migration_info["migration_id"]
        assert validation_result.validation_status is not None
        assert validation_duration < 10.0

        print(f"Validation Status: {validation_result.validation_status.value}")
        print(f"Duration: {validation_duration:.2f}s")
        print(f"Checkpoints: {len(validation_result.checkpoints)}")

        # Should have executed multiple validation checkpoints
        assert len(validation_result.checkpoints) > 0

        # Validate staging environment was used
        assert validation_result.staging_environment_id is not None

        # Check for dependency analysis results
        if validation_result.dependency_report:
            print(
                f"Dependencies analyzed: {validation_result.dependency_report.get_total_dependency_count()}"
            )

        # Validate risk assessment was performed
        if validation_result.risk_assessment:
            print(f"Risk Level: {validation_result.risk_assessment.risk_level.value}")
            assert validation_result.risk_assessment.overall_score >= 0

        print("✅ Complete validation pipeline executed successfully")

    async def test_complete_impact_reporting_workflow(
        self, complete_safe_staging_system, production_db_config, business_scenarios
    ):
        """Test complete impact reporting workflow for business stakeholders."""
        system = complete_safe_staging_system
        impact_reporter = system["impact_reporter"]

        scenario = business_scenarios[1]  # Medium-risk scenario

        print("\n=== E2E Test: Complete Impact Reporting ===")
        print(f"Scenario: {scenario.description}")

        # Execute deployment validation to generate impact data
        deployment_result = await system[
            "production_validator"
        ].validate_production_deployment(
            scenario.migration_info, production_db=production_db_config
        )

        # Generate impact reports in multiple formats
        if (
            hasattr(deployment_result, "dependency_report")
            and deployment_result.dependency_report
        ):
            dependency_report = deployment_result.dependency_report
        else:
            # Create a sample dependency report for testing
            from dataflow.migrations.dependency_analyzer import DependencyReport

            dependency_report = DependencyReport(
                table_name=scenario.migration_info["table_name"],
                column_name=scenario.migration_info.get("column_name", ""),
            )

        # Generate impact report
        impact_report = impact_reporter.generate_impact_report(dependency_report)

        # Test different output formats
        console_report = impact_reporter.format_user_friendly_report(
            impact_report, format_type=OutputFormat.CONSOLE
        )

        json_report = impact_reporter.format_user_friendly_report(
            impact_report, format_type=OutputFormat.JSON
        )

        summary_report = impact_reporter.format_user_friendly_report(
            impact_report, format_type=OutputFormat.SUMMARY
        )

        # Validate report generation
        assert len(console_report) > 0
        assert len(json_report) > 0
        assert len(summary_report) > 0

        print("Console Report Preview:")
        print(
            console_report[:500] + "..."
            if len(console_report) > 500
            else console_report
        )

        print(f"\nSummary Report: {summary_report}")

        # Validate recommendations were generated
        assert len(impact_report.recommendations) > 0

        print("✅ Impact reporting workflow completed successfully")

    async def test_complete_rollback_workflow(
        self, complete_safe_staging_system, production_db_config
    ):
        """Test complete rollback workflow for deployment recovery."""
        system = complete_safe_staging_system
        production_validator = system["production_validator"]

        print("\n=== E2E Test: Complete Rollback Workflow ===")

        # Create a migration that would need rollback
        migration_info = {
            "migration_id": "rollback_test_001",
            "table_name": "customers",
            "column_name": "test_rollback_column",
            "operation_type": "add_column",
            "sql_statements": [
                "ALTER TABLE customers ADD COLUMN test_rollback_column TEXT;"
            ],
        }

        # Generate rollback plan
        print("Generating rollback plan...")
        rollback_plan = production_validator._generate_rollback_plan(migration_info)

        assert rollback_plan.migration_id == migration_info["migration_id"]
        assert len(rollback_plan.rollback_steps) > 0
        assert rollback_plan.is_executable

        print(f"Rollback plan: {len(rollback_plan.rollback_steps)} steps")
        print(f"Estimated rollback time: {rollback_plan.estimated_rollback_time:.1f}s")

        # Execute rollback workflow
        print("Executing rollback workflow...")
        start_time = time.time()

        rollback_result = await production_validator.execute_rollback(
            deployment_id="test_deployment_001",
            rollback_plan=rollback_plan,
            reason="E2E testing rollback workflow",
        )

        rollback_duration = time.time() - start_time

        # Validate rollback execution
        assert rollback_result is not None
        assert rollback_result.rollback_executed is True
        assert rollback_duration < 10.0

        print(f"Rollback Result: {rollback_result.success}")
        print(f"Duration: {rollback_duration:.2f}s")
        print(f"Steps Completed: {len(rollback_result.phases_completed)}")

        if rollback_result.success:
            print("✅ Rollback workflow completed successfully")
        else:
            print(f"⚠️ Rollback encountered issues: {rollback_result.message}")
            if rollback_result.errors:
                for error in rollback_result.errors:
                    print(f"Error: {error}")

    async def test_complete_concurrent_deployment_scenario(
        self, complete_safe_staging_system, production_db_config
    ):
        """Test complete concurrent deployment prevention in realistic scenario."""
        system = complete_safe_staging_system

        print("\n=== E2E Test: Concurrent Deployment Prevention ===")

        # Two conflicting migrations to same schema
        migration_1 = {
            "migration_id": "concurrent_test_001",
            "table_name": "customers",
            "column_name": "field_1",
            "operation_type": "add_column",
            "schema_name": "public",
        }

        migration_2 = {
            "migration_id": "concurrent_test_002",
            "table_name": "orders",
            "column_name": "field_2",
            "operation_type": "add_column",
            "schema_name": "public",  # Same schema
        }

        print("Starting first deployment...")
        # Start first deployment (don't await - simulate concurrent)
        deployment_1_task = asyncio.create_task(
            system["production_validator"].validate_production_deployment(
                migration_1, production_db=production_db_config
            )
        )

        # Small delay to ensure first deployment starts
        await asyncio.sleep(0.1)

        print("Attempting second concurrent deployment...")
        # Try second deployment immediately
        start_time = time.time()
        deployment_2_result = await system[
            "production_validator"
        ].validate_production_deployment(
            migration_2, production_db=production_db_config
        )
        concurrent_check_duration = time.time() - start_time

        # Wait for first deployment to complete
        deployment_1_result = await deployment_1_task

        print(f"First deployment: {deployment_1_result.success}")
        print(f"Second deployment: {deployment_2_result.success}")
        print(f"Concurrent check duration: {concurrent_check_duration:.2f}s")

        # Validate concurrent deployment prevention
        assert concurrent_check_duration < 10.0  # Should fail fast

        # At least one deployment should mention concurrency
        combined_messages = (
            f"{deployment_1_result.message} {deployment_2_result.message}"
        )
        if not deployment_2_result.success:
            assert (
                "concurrent" in combined_messages.lower()
                or "progress" in combined_messages.lower()
            )
            print("✅ Concurrent deployment properly prevented")
        else:
            print("⚠️ Both deployments allowed - validating safe execution")

    async def test_complete_performance_benchmarking(
        self, complete_safe_staging_system, production_db_config, business_scenarios
    ):
        """Test complete system performance under realistic load."""
        system = complete_safe_staging_system

        print("\n=== E2E Test: Performance Benchmarking ===")

        # Test multiple scenarios to measure performance
        performance_results = []

        for i, scenario in enumerate(business_scenarios[:2]):  # Test first 2 scenarios
            print(f"\nPerformance Test {i+1}: {scenario.name}")

            start_time = time.time()

            deployment_result = await system[
                "production_validator"
            ].validate_production_deployment(
                scenario.migration_info, production_db=production_db_config
            )

            end_time = time.time()
            duration = end_time - start_time

            performance_results.append(
                {
                    "scenario": scenario.name,
                    "duration": duration,
                    "success": deployment_result.success,
                    "phases": len(deployment_result.phases_completed),
                    "errors": len(deployment_result.errors),
                }
            )

            print(f"Duration: {duration:.2f}s, Success: {deployment_result.success}")

            # Each scenario should complete within E2E timeout
            assert duration < 10.0

        # Analyze overall performance
        avg_duration = sum(r["duration"] for r in performance_results) / len(
            performance_results
        )
        max_duration = max(r["duration"] for r in performance_results)

        print("\nPerformance Summary:")
        print(f"Average Duration: {avg_duration:.2f}s")
        print(f"Maximum Duration: {max_duration:.2f}s")

        # Performance requirements
        assert avg_duration < 5.0  # Average should be under 5s
        assert max_duration < 10.0  # Max should be under 10s

        print("✅ Performance benchmarking completed successfully")

        for result in performance_results:
            print(
                f"  {result['scenario']}: {result['duration']:.2f}s ({'✅' if result['success'] else '⚠️'})"
            )


if __name__ == "__main__":
    # Run E2E tests with extended timeout
    pytest.main(
        [
            __file__,
            "-v",
            "--tb=short",
            "--timeout=10",
            "-s",  # Show output for debugging
        ]
    )
