#!/usr/bin/env python3
"""
Integration Tests for Mitigation Strategy Engine - TODO-140 Phase 2

Comprehensive integration tests validating the interaction between the Mitigation
Strategy Engine and Phase 1 Risk Assessment Engine with real database scenarios.
Tests end-to-end mitigation strategy generation, effectiveness assessment, and
roadmap creation with actual risk assessments.

TIER 2 TESTING APPROACH:
- Real database infrastructure (PostgreSQL)
- Integration with Phase 1 RiskAssessmentEngine
- Integration with DependencyAnalyzer and ForeignKeyAnalyzer
- Performance validation (<5 seconds per test)
- Real scenario-based testing
- No mocking of core components
"""

import asyncio
import logging
import time
from typing import Any, Dict

import asyncpg
import pytest
from dataflow.migrations.dependency_analyzer import (
    DependencyAnalyzer,
    DependencyReport,
    DependencyType,
    ImpactLevel,
)
from dataflow.migrations.mitigation_strategy_engine import (
    EffectivenessAssessment,
    MitigationCategory,
    MitigationComplexity,
    MitigationPriority,
    MitigationStrategy,
    MitigationStrategyEngine,
    PrioritizedMitigationPlan,
    RiskReductionRoadmap,
)
from dataflow.migrations.risk_assessment_engine import (
    ComprehensiveRiskAssessment,
    RiskAssessmentEngine,
    RiskCategory,
    RiskLevel,
    RiskScore,
)

from kailash.runtime.local import LocalRuntime
from tests.infrastructure.test_harness import IntegrationTestSuite


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


from dataflow.migrations.foreign_key_analyzer import (
    FKImpactLevel,
    FKImpactReport,
    ForeignKeyAnalyzer,
)

# Import integration test infrastructure
from tests.infrastructure.test_harness import IntegrationTestSuite

# Configure logging for test debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Connection management using the new test harness


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
async def test_connection(test_suite):
    """Get test database connection from suite."""
    async with test_suite.get_connection() as conn:
        yield conn


@pytest.fixture
async def connection_manager(test_suite):
    """Create async connection manager for each test - FIXED for concurrent operations."""

    class AsyncConnectionManager:
        def __init__(self, db_url):
            self.database_url = db_url
            self._connections = {}
            self._lock = asyncio.Lock()

        async def get_connection(self):
            """Get async database connection - creates NEW connection for each call."""
            # Always create a new connection for concurrent operations
            # This fixes the "operation is in progress" error
            connection = await asyncpg.connect(self.database_url)

            # Store for cleanup tracking
            connection_id = id(connection)
            self._connections[connection_id] = connection

            return connection

        def close_all_connections(self):
            """Close all connections."""
            for connection in self._connections.values():
                if not connection.is_closed():
                    asyncio.create_task(connection.close())
            self._connections.clear()

    manager = AsyncConnectionManager(test_suite.config.url)

    yield manager

    # Cleanup
    manager.close_all_connections()


@pytest.fixture
async def dependency_analyzer(connection_manager):
    """Create DependencyAnalyzer for each test."""
    analyzer = DependencyAnalyzer(connection_manager)
    yield analyzer


@pytest.fixture
async def fk_analyzer(connection_manager):
    """Create ForeignKeyAnalyzer for each test."""
    analyzer = ForeignKeyAnalyzer(connection_manager)
    yield analyzer


@pytest.fixture
async def risk_assessment_engine(dependency_analyzer, fk_analyzer):
    """Create RiskAssessmentEngine for each test."""
    engine = RiskAssessmentEngine(
        dependency_analyzer=dependency_analyzer, fk_analyzer=fk_analyzer
    )
    yield engine


@pytest.fixture
async def mitigation_engine():
    """Create MitigationStrategyEngine for each test."""
    engine = MitigationStrategyEngine(enable_enterprise_strategies=True)
    yield engine


@pytest.fixture(autouse=True)
async def clean_test_schema(test_connection):
    """Clean test schema before each test."""
    # Drop all test tables, views, functions, triggers
    await test_connection.execute(
        """
        DO $$
        DECLARE
            r RECORD;
        BEGIN
            -- Drop all views
            FOR r IN (SELECT schemaname, viewname FROM pg_views WHERE schemaname = 'public' AND viewname LIKE 'test_%') LOOP
                EXECUTE 'DROP VIEW IF EXISTS ' || quote_ident(r.schemaname) || '.' || quote_ident(r.viewname) || ' CASCADE';
            END LOOP;

            -- Drop all tables
            FOR r IN (SELECT schemaname, tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'test_%') LOOP
                EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.schemaname) || '.' || quote_ident(r.tablename) || ' CASCADE';
            END LOOP;

            -- Drop all functions
            FOR r IN (SELECT n.nspname, p.proname, pg_get_function_identity_arguments(p.oid) as args
                     FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid
                     WHERE n.nspname = 'public' AND p.proname LIKE 'test_%') LOOP
                EXECUTE 'DROP FUNCTION IF EXISTS ' || quote_ident(r.nspname) || '.' || quote_ident(r.proname) || '(' || r.args || ') CASCADE';
            END LOOP;
        END $$;
    """
    )


class TestMitigationStrategyEngineIntegration:
    """Integration tests for MitigationStrategyEngine with real infrastructure."""

    @pytest.mark.asyncio
    async def test_integration_with_risk_assessment_simple_scenario(
        self,
        mitigation_engine,
        risk_assessment_engine,
        dependency_analyzer,
        test_connection,
    ):
        """Test full integration with risk assessment for simple scenario."""
        # Create a simple table for testing
        await test_connection.execute(
            """
            CREATE TABLE test_simple_users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                email VARCHAR(255) UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX test_simple_users_email_idx ON test_simple_users(email);
        """
        )

        # Mock operation for risk assessment
        class MockOperation:
            def __init__(self):
                self.table = "test_simple_users"
                self.column = "email"
                self.operation_type = "drop_column"
                self.has_backup = True
                self.is_production = False
                self.estimated_rows = 1000
                self.table_size_mb = 10.0

        operation = MockOperation()

        # Get real dependency analysis
        dependency_report = await dependency_analyzer.analyze_column_dependencies(
            operation.table, operation.column
        )

        # Get real risk assessment
        risk_assessment = risk_assessment_engine.calculate_migration_risk_score(
            operation, dependency_report
        )

        # Generate mitigation strategies
        strategies = mitigation_engine.generate_mitigation_strategies(
            risk_assessment,
            dependency_report,
            {"is_production": False, "table_size_mb": 10.0, "estimated_rows": 1000},
        )

        # Validate integration results
        assert len(strategies) >= 0  # May be empty for low-risk scenario
        assert isinstance(risk_assessment, ComprehensiveRiskAssessment)
        assert risk_assessment.overall_score >= 0

        # If strategies are generated, validate they target appropriate risks
        if strategies:
            for strategy in strategies:
                assert len(strategy.target_risk_categories) > 0
                assert strategy.risk_reduction_potential > 0
                assert strategy.estimated_effort_hours >= 0

    @pytest.mark.asyncio
    async def test_integration_high_risk_cascade_scenario(
        self,
        mitigation_engine,
        risk_assessment_engine,
        dependency_analyzer,
        test_connection,
    ):
        """Test integration with high-risk CASCADE FK scenario."""
        # Create tables with CASCADE FK relationship
        await test_connection.execute(
            """
            CREATE TABLE test_companies (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                code VARCHAR(50) UNIQUE
            );

            CREATE TABLE test_employees (
                id SERIAL PRIMARY KEY,
                company_id INTEGER NOT NULL,
                name VARCHAR(255) NOT NULL,
                email VARCHAR(255),
                CONSTRAINT fk_employees_company
                    FOREIGN KEY (company_id) REFERENCES test_companies(id) ON DELETE CASCADE
            );
        """
        )

        # Mock high-risk operation
        class MockHighRiskOperation:
            def __init__(self):
                self.table = "test_companies"
                self.column = "id"
                self.operation_type = "drop_column"
                self.has_backup = False  # No backup = higher risk
                self.is_production = True  # Production = higher risk
                self.estimated_rows = 50000  # Large table = higher risk
                self.table_size_mb = 500.0

        operation = MockHighRiskOperation()

        # Get real dependency analysis
        dependency_report = await dependency_analyzer.analyze_column_dependencies(
            operation.table, operation.column
        )

        # Get real risk assessment
        risk_assessment = risk_assessment_engine.calculate_migration_risk_score(
            operation, dependency_report
        )

        # Should be high or critical risk due to CASCADE FK
        assert risk_assessment.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
        assert risk_assessment.overall_score > 50

        # Generate mitigation strategies
        strategies = mitigation_engine.generate_mitigation_strategies(
            risk_assessment,
            dependency_report,
            {"is_production": True, "table_size_mb": 500.0, "estimated_rows": 50000},
        )

        # High-risk scenario should generate multiple strategies
        assert len(strategies) > 0

        # Should include critical and high priority strategies
        priorities = [s.priority for s in strategies]
        assert (
            MitigationPriority.CRITICAL in priorities
            or MitigationPriority.HIGH in priorities
        )

        # Should include data loss mitigation strategies
        data_loss_strategies = [
            s for s in strategies if RiskCategory.DATA_LOSS in s.target_risk_categories
        ]
        assert len(data_loss_strategies) > 0

        # Should include backup-related strategies for no-backup scenario
        backup_strategies = [
            s
            for s in strategies
            if "backup" in s.name.lower() or "backup" in s.description.lower()
        ]
        assert len(backup_strategies) > 0

    @pytest.mark.asyncio
    async def test_integration_prioritization_and_roadmap_creation(
        self,
        mitigation_engine,
        risk_assessment_engine,
        dependency_analyzer,
        test_connection,
    ):
        """Test full integration from risk assessment to roadmap creation."""
        # Create complex scenario with multiple risk factors
        await test_connection.execute(
            """
            CREATE TABLE test_main_table (
                id SERIAL PRIMARY KEY,
                data VARCHAR(255),
                status VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE test_dependent_table (
                id SERIAL PRIMARY KEY,
                main_id INTEGER NOT NULL,
                value TEXT,
                CONSTRAINT fk_dependent_main
                    FOREIGN KEY (main_id) REFERENCES test_main_table(id) ON DELETE CASCADE
            );

            CREATE VIEW test_summary_view AS
            SELECT t.id, t.data, t.status, COUNT(d.id) as dependent_count
            FROM test_main_table t
            LEFT JOIN test_dependent_table d ON t.id = d.main_id
            GROUP BY t.id, t.data, t.status;

            CREATE INDEX test_main_table_status_idx ON test_main_table(status);
            CREATE INDEX test_main_table_data_idx ON test_main_table(data);
        """
        )

        # Mock complex operation
        class MockComplexOperation:
            def __init__(self):
                self.table = "test_main_table"
                self.column = "status"
                self.operation_type = "drop_column"
                self.has_backup = True
                self.is_production = True
                self.estimated_rows = 25000
                self.table_size_mb = 150.0

        operation = MockComplexOperation()

        # Full integration workflow
        start_time = time.time()

        # 1. Analyze dependencies
        dependency_report = await dependency_analyzer.analyze_column_dependencies(
            operation.table, operation.column
        )

        # 2. Assess risks
        risk_assessment = risk_assessment_engine.calculate_migration_risk_score(
            operation, dependency_report
        )

        # 3. Generate strategies
        strategies = mitigation_engine.generate_mitigation_strategies(
            risk_assessment,
            dependency_report,
            {"is_production": True, "table_size_mb": 150.0, "estimated_rows": 25000},
        )

        # 4. Prioritize strategies
        mitigation_plan = mitigation_engine.prioritize_mitigation_actions(
            strategies, risk_assessment, {"budget_hours": 40.0, "team_size": 3}
        )

        # 5. Create roadmap
        roadmap = mitigation_engine.create_risk_reduction_roadmap(
            risk_assessment, RiskLevel.MEDIUM, mitigation_plan
        )

        integration_time = time.time() - start_time

        # Performance validation - should complete within 5 seconds
        assert integration_time < 5.0

        # Validate end-to-end results
        assert isinstance(mitigation_plan, PrioritizedMitigationPlan)
        assert isinstance(roadmap, RiskReductionRoadmap)

        # Plan should have strategies and assessments
        assert len(mitigation_plan.mitigation_strategies) > 0
        assert len(mitigation_plan.effectiveness_assessments) > 0
        assert mitigation_plan.total_estimated_effort > 0

        # Roadmap should have phases and success criteria
        assert len(roadmap.phases) > 0
        assert len(roadmap.success_criteria) > 0
        assert roadmap.estimated_total_duration > 0
        assert len(roadmap.stakeholder_approvals) > 0

        # Should have risk reduction projections
        assert len(mitigation_plan.projected_risk_reduction) > 0
        assert mitigation_plan.projected_overall_risk < risk_assessment.overall_score

    @pytest.mark.asyncio
    async def test_integration_enterprise_strategies_critical_risk(
        self, risk_assessment_engine, dependency_analyzer, test_connection
    ):
        """Test enterprise strategy generation for critical risk scenarios."""
        # Create enterprise-level critical scenario
        await test_connection.execute(
            """
            CREATE TABLE test_critical_master (
                id SERIAL PRIMARY KEY,
                business_key VARCHAR(100) UNIQUE NOT NULL,
                status VARCHAR(50) NOT NULL
            );

            -- Create multiple CASCADE dependencies
            CREATE TABLE test_critical_orders (
                id SERIAL PRIMARY KEY,
                master_id INTEGER NOT NULL,
                amount DECIMAL(10,2),
                CONSTRAINT fk_orders_master
                    FOREIGN KEY (master_id) REFERENCES test_critical_master(id) ON DELETE CASCADE
            );

            CREATE TABLE test_critical_payments (
                id SERIAL PRIMARY KEY,
                master_id INTEGER NOT NULL,
                payment_amount DECIMAL(10,2),
                CONSTRAINT fk_payments_master
                    FOREIGN KEY (master_id) REFERENCES test_critical_master(id) ON DELETE CASCADE
            );

            CREATE TABLE test_critical_audit (
                id SERIAL PRIMARY KEY,
                master_id INTEGER NOT NULL,
                audit_data TEXT,
                CONSTRAINT fk_audit_master
                    FOREIGN KEY (master_id) REFERENCES test_critical_master(id) ON DELETE CASCADE
            );
        """
        )

        # Mock critical enterprise operation
        class MockCriticalOperation:
            def __init__(self):
                self.table = "test_critical_master"
                self.column = "business_key"
                self.operation_type = "drop_column"
                self.has_backup = False  # Critical: no backup
                self.is_production = True  # Critical: production
                self.estimated_rows = 100000  # Critical: large table
                self.table_size_mb = 1000.0  # Critical: very large

        operation = MockCriticalOperation()

        # Full assessment and mitigation
        dependency_report = await dependency_analyzer.analyze_column_dependencies(
            operation.table, operation.column
        )

        risk_assessment = risk_assessment_engine.calculate_migration_risk_score(
            operation, dependency_report
        )

        # Should be critical risk
        assert risk_assessment.risk_level == RiskLevel.CRITICAL
        assert risk_assessment.overall_score > 75

        # Test with enterprise strategies enabled
        enterprise_engine = MitigationStrategyEngine(enable_enterprise_strategies=True)

        strategies = enterprise_engine.generate_mitigation_strategies(
            risk_assessment,
            dependency_report,
            {"is_production": True, "table_size_mb": 1000.0, "estimated_rows": 100000},
        )

        # Should generate enterprise-level strategies
        assert len(strategies) > 0

        enterprise_strategies = [
            s for s in strategies if s.complexity == MitigationComplexity.ENTERPRISE
        ]
        assert len(enterprise_strategies) > 0

        critical_strategies = [
            s for s in strategies if s.priority == MitigationPriority.CRITICAL
        ]
        assert len(critical_strategies) > 0

        # Should include approval workflow strategies
        approval_strategies = [
            s
            for s in strategies
            if "approval" in s.name.lower() or "approval" in s.description.lower()
        ]
        assert len(approval_strategies) > 0

    @pytest.mark.asyncio
    async def test_integration_performance_large_strategy_set(
        self,
        mitigation_engine,
        risk_assessment_engine,
        dependency_analyzer,
        test_connection,
    ):
        """Test performance with large complex scenarios generating many strategies."""
        # Create large complex schema
        await test_connection.execute(
            """
            CREATE TABLE test_perf_master (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255),
                status VARCHAR(50),
                category VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """
        )

        # Create multiple dependent tables and indexes
        for i in range(5):
            await test_connection.execute(
                f"""
                CREATE TABLE test_perf_detail_{i} (
                    id SERIAL PRIMARY KEY,
                    master_id INTEGER NOT NULL,
                    data_{i} TEXT,
                    CONSTRAINT fk_detail_{i}_master
                        FOREIGN KEY (master_id) REFERENCES test_perf_master(id) ON DELETE CASCADE
                );

                CREATE INDEX test_perf_detail_{i}_master_idx ON test_perf_detail_{i}(master_id);
                CREATE INDEX test_perf_detail_{i}_data_idx ON test_perf_detail_{i}(data_{i});

                CREATE VIEW test_perf_view_{i} AS
                SELECT m.id, m.name, d.data_{i}
                FROM test_perf_master m
                LEFT JOIN test_perf_detail_{i} d ON m.id = d.master_id;
            """
            )

        # Mock operation affecting many dependencies
        class MockLargeOperation:
            def __init__(self):
                self.table = "test_perf_master"
                self.column = "id"  # Primary key - affects all FKs
                self.operation_type = "drop_column"
                self.has_backup = False
                self.is_production = True
                self.estimated_rows = 75000
                self.table_size_mb = 800.0

        operation = MockLargeOperation()

        # Performance test
        start_time = time.time()

        # Full integration workflow
        dependency_report = await dependency_analyzer.analyze_column_dependencies(
            operation.table, operation.column
        )

        risk_assessment = risk_assessment_engine.calculate_migration_risk_score(
            operation, dependency_report
        )

        strategies = mitigation_engine.generate_mitigation_strategies(
            risk_assessment,
            dependency_report,
            {"is_production": True, "table_size_mb": 800.0, "estimated_rows": 75000},
        )

        mitigation_plan = mitigation_engine.prioritize_mitigation_actions(
            strategies, risk_assessment
        )

        roadmap = mitigation_engine.create_risk_reduction_roadmap(
            risk_assessment, RiskLevel.LOW, mitigation_plan
        )

        total_time = time.time() - start_time

        # Performance validation - should handle complex scenarios efficiently
        assert total_time < 5.0  # 5 second limit for integration tests

        # Should handle large dependency sets effectively
        assert len(strategies) > 0
        assert len(mitigation_plan.mitigation_strategies) > 0
        assert len(roadmap.phases) > 0

        logger.info(
            f"Large scenario integration test completed in {total_time:.2f}s with {len(strategies)} strategies"
        )

    @pytest.mark.asyncio
    async def test_integration_effectiveness_assessment_accuracy(
        self,
        mitigation_engine,
        risk_assessment_engine,
        dependency_analyzer,
        test_connection,
    ):
        """Test accuracy of effectiveness assessments with real risk scenarios."""
        # Create scenario with known risk characteristics
        await test_connection.execute(
            """
            CREATE TABLE test_effectiveness_table (
                id SERIAL PRIMARY KEY,
                critical_data VARCHAR(255) UNIQUE NOT NULL,
                status VARCHAR(50)
            );

            CREATE UNIQUE INDEX test_effectiveness_critical_idx ON test_effectiveness_table(critical_data);
        """
        )

        # Mock operation with specific characteristics
        class MockEffectivenessOperation:
            def __init__(self):
                self.table = "test_effectiveness_table"
                self.column = "critical_data"
                self.operation_type = "drop_column"
                self.has_backup = True
                self.is_production = False
                self.estimated_rows = 5000
                self.table_size_mb = 25.0

        operation = MockEffectivenessOperation()

        # Get assessment and strategies
        dependency_report = await dependency_analyzer.analyze_column_dependencies(
            operation.table, operation.column
        )

        risk_assessment = risk_assessment_engine.calculate_migration_risk_score(
            operation, dependency_report
        )

        strategies = mitigation_engine.generate_mitigation_strategies(
            risk_assessment, dependency_report
        )

        # Test effectiveness assessment accuracy
        for strategy in strategies:
            assessment = mitigation_engine.validate_mitigation_effectiveness(
                strategy, risk_assessment
            )

            # Validate assessment components
            assert 0 <= assessment.overall_effectiveness_score <= 100
            assert 0 <= assessment.implementation_feasibility <= 100
            assert 0 <= assessment.assessment_confidence <= 1.0

            # Risk reduction should be meaningful for target categories
            for risk_category in strategy.target_risk_categories:
                if risk_category in assessment.risk_reduction_by_category:
                    reduction = assessment.risk_reduction_by_category[risk_category]
                    assert reduction >= 0
                    # Reduction should not exceed current risk score
                    if risk_category in risk_assessment.category_scores:
                        current_score = risk_assessment.category_scores[
                            risk_category
                        ].score
                        assert reduction <= current_score

            # Effectiveness should correlate with strategy properties
            if strategy.risk_reduction_potential > 80:
                assert assessment.overall_effectiveness_score > 50

            if strategy.implementation_complexity > 70:
                assert assessment.implementation_feasibility < 90

    @pytest.mark.asyncio
    async def test_integration_roadmap_phase_logic(
        self,
        mitigation_engine,
        risk_assessment_engine,
        dependency_analyzer,
        test_connection,
    ):
        """Test roadmap phase creation logic with real scenarios."""
        # Create scenario requiring phased approach
        await test_connection.execute(
            """
            CREATE TABLE test_phase_master (
                id SERIAL PRIMARY KEY,
                key_field VARCHAR(100) NOT NULL
            );

            CREATE TABLE test_phase_child (
                id SERIAL PRIMARY KEY,
                master_id INTEGER NOT NULL,
                CONSTRAINT fk_phase_child
                    FOREIGN KEY (master_id) REFERENCES test_phase_master(id) ON DELETE CASCADE
            );
        """
        )

        # Mock operation requiring multiple mitigation phases
        class MockPhasedOperation:
            def __init__(self):
                self.table = "test_phase_master"
                self.column = "key_field"
                self.operation_type = "drop_column"
                self.has_backup = False
                self.is_production = True
                self.estimated_rows = 30000
                self.table_size_mb = 200.0

        operation = MockPhasedOperation()

        # Get full assessment and mitigation plan
        dependency_report = await dependency_analyzer.analyze_column_dependencies(
            operation.table, operation.column
        )

        risk_assessment = risk_assessment_engine.calculate_migration_risk_score(
            operation, dependency_report
        )

        strategies = mitigation_engine.generate_mitigation_strategies(
            risk_assessment,
            dependency_report,
            {"is_production": True, "table_size_mb": 200.0},
        )

        mitigation_plan = mitigation_engine.prioritize_mitigation_actions(
            strategies, risk_assessment
        )

        roadmap = mitigation_engine.create_risk_reduction_roadmap(
            risk_assessment, RiskLevel.LOW, mitigation_plan
        )

        # Validate phase logic
        phases = roadmap.phases
        assert len(phases) > 0

        # Phases should be ordered by priority
        if len(phases) > 1:
            # First phase should be critical strategies if they exist
            critical_strategies = [
                s
                for s in mitigation_plan.mitigation_strategies
                if s.priority == MitigationPriority.CRITICAL
            ]
            if critical_strategies:
                first_phase = phases[0]
                assert first_phase["phase_name"] == "Critical Risk Mitigation"
                for strategy_id in critical_strategies:
                    assert strategy_id.id in first_phase["strategies"]

        # Each phase should have reasonable duration estimates
        for phase in phases:
            assert phase["estimated_duration"] >= 0
            assert len(phase["strategies"]) > 0
            assert len(phase.get("success_criteria", [])) > 0

        # Total duration should match sum of phase durations
        total_phase_duration = sum(phase["estimated_duration"] for phase in phases)
        assert abs(total_phase_duration - roadmap.estimated_total_duration) < 0.1

        # Should have milestone checkpoints for each phase
        assert len(roadmap.milestone_checkpoints) == len(phases)

    @pytest.mark.asyncio
    async def test_integration_real_world_migration_scenario(
        self,
        mitigation_engine,
        risk_assessment_engine,
        dependency_analyzer,
        test_connection,
    ):
        """Test with realistic migration scenario simulating production environment."""
        # Create realistic e-commerce-like schema
        await test_connection.execute(
            """
            -- Core business tables
            CREATE TABLE test_customers (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE test_orders (
                id SERIAL PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                order_status VARCHAR(50) NOT NULL,
                total_amount DECIMAL(10,2),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_orders_customer
                    FOREIGN KEY (customer_id) REFERENCES test_customers(id) ON DELETE CASCADE
            );

            CREATE TABLE test_payments (
                id SERIAL PRIMARY KEY,
                order_id INTEGER NOT NULL,
                payment_status VARCHAR(50),
                amount DECIMAL(10,2),
                CONSTRAINT fk_payments_order
                    FOREIGN KEY (order_id) REFERENCES test_orders(id) ON DELETE CASCADE
            );

            -- Business intelligence views
            CREATE VIEW test_customer_summary AS
            SELECT
                c.id,
                c.email,
                c.status,
                COUNT(o.id) as total_orders,
                COALESCE(SUM(o.total_amount), 0) as total_spent
            FROM test_customers c
            LEFT JOIN test_orders o ON c.id = o.customer_id
            GROUP BY c.id, c.email, c.status;

            -- Performance indexes
            CREATE INDEX test_customers_status_idx ON test_customers(status);
            CREATE INDEX test_orders_customer_idx ON test_orders(customer_id);
            CREATE INDEX test_orders_status_idx ON test_orders(order_status);
            CREATE INDEX test_payments_order_idx ON test_payments(order_id);
        """
        )

        # Mock realistic production migration
        class MockProductionMigration:
            def __init__(self):
                self.table = "test_customers"
                self.column = "status"  # Critical business field
                self.operation_type = "drop_column"
                self.has_backup = True  # Production has backups
                self.is_production = True
                self.estimated_rows = 250000  # Large customer base
                self.table_size_mb = 450.0  # Substantial size

        operation = MockProductionMigration()

        # Full end-to-end workflow
        start_time = time.time()

        dependency_report = await dependency_analyzer.analyze_column_dependencies(
            operation.table, operation.column
        )

        risk_assessment = risk_assessment_engine.calculate_migration_risk_score(
            operation, dependency_report
        )

        strategies = mitigation_engine.generate_mitigation_strategies(
            risk_assessment,
            dependency_report,
            {"is_production": True, "table_size_mb": 450.0, "estimated_rows": 250000},
        )

        mitigation_plan = mitigation_engine.prioritize_mitigation_actions(
            strategies,
            risk_assessment,
            {
                "budget_hours": 80.0,  # Realistic enterprise budget
                "team_size": 5,  # Full team
            },
        )

        roadmap = mitigation_engine.create_risk_reduction_roadmap(
            risk_assessment, RiskLevel.MEDIUM, mitigation_plan
        )

        workflow_time = time.time() - start_time

        # Performance validation for production scenario
        assert workflow_time < 5.0

        # Validate realistic production results
        assert isinstance(risk_assessment, ComprehensiveRiskAssessment)
        assert risk_assessment.risk_level in [
            RiskLevel.MEDIUM,
            RiskLevel.HIGH,
            RiskLevel.CRITICAL,
        ]

        # Production scenarios should generate meaningful strategies
        assert len(strategies) > 0

        # Should include production-appropriate strategies
        production_strategies = [
            s
            for s in strategies
            if "production" in s.description.lower()
            or "maintenance" in s.description.lower()
        ]
        staging_strategies = [
            s
            for s in strategies
            if "staging" in s.description.lower()
            or "rehearsal" in s.description.lower()
        ]

        assert len(production_strategies) > 0 or len(staging_strategies) > 0

        # Should have appropriate approval requirements
        approvals = roadmap.stakeholder_approvals
        assert len(approvals) > 0
        assert any(
            "Manager" in approval or "Lead" in approval for approval in approvals
        )

        # Resource estimates should be realistic
        resources = roadmap.required_resources
        assert resources["total_person_hours"] > 0
        assert resources["estimated_team_size"] >= 1
        assert "budget_estimate" in resources

        logger.info(
            f"Production scenario completed in {workflow_time:.2f}s - Risk: {risk_assessment.risk_level.value.upper()} ({risk_assessment.overall_score:.1f})"
        )
        logger.info(
            f"Generated {len(strategies)} strategies, {len(roadmap.phases)} phases, effort: {mitigation_plan.total_estimated_effort:.1f}h"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
