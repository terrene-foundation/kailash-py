#!/usr/bin/env python3
"""
E2E Tests for Table Schema Rename Engine - TODO-139 Phase 1

Tests complete table rename workflows with complex dependencies and
real-world scenarios using full infrastructure stack.

Following Tier 3 testing guidelines:
- Complete user workflows from start to finish
- Real infrastructure and data - NO MOCKING
- Test actual user scenarios and expectations
- Timeout: <10 seconds per test
- CRITICAL PRIORITY: Real business requirements validation
"""

import asyncio
import time
import uuid

import asyncpg
import pytest
from dataflow.migrations.dependency_analyzer import DependencyAnalyzer
from dataflow.migrations.foreign_key_analyzer import ForeignKeyAnalyzer
from dataflow.migrations.table_rename_analyzer import (
    DependencyGraph,
    RenameImpactLevel,
    RenameValidation,
    SchemaObject,
    SchemaObjectType,
    TableRenameAnalyzer,
    TableRenameError,
    TableRenameReport,
)


class TestTableRenameEngineE2E:
    """E2E tests for complete table rename workflows."""

    @pytest.fixture
    async def database_connection(self):
        """Create direct connection to test database."""
        import os

        host = os.getenv("DB_HOST", "localhost")
        port = int(os.getenv("DB_PORT", "5433"))  # DataFlow test port
        user = os.getenv("DB_USER", "dataflow_test")
        password = os.getenv("DB_PASSWORD", "dataflow_test_password")
        database = os.getenv("DB_NAME", "dataflow_test")

        db_url = f"postgresql://{user}:{password}@{host}:{port}/{database}"
        conn = await asyncpg.connect(db_url)
        yield conn
        await conn.close()

    @pytest.fixture
    async def connection_manager(self, database_connection):
        """Create connection manager for analyzers."""

        class E2EConnectionManager:
            def __init__(self, conn):
                self.conn = conn

            async def get_connection(self):
                return self.conn

        return E2EConnectionManager(database_connection)

    @pytest.fixture
    async def rename_analyzer(self, connection_manager):
        """Create fully configured table rename analyzer."""
        dependency_analyzer = DependencyAnalyzer(connection_manager)
        fk_analyzer = ForeignKeyAnalyzer(connection_manager)

        analyzer = TableRenameAnalyzer(
            connection_manager=connection_manager,
            dependency_analyzer=dependency_analyzer,
            fk_analyzer=fk_analyzer,
        )
        return analyzer

    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_complete_table_rename_workflow_e2e(
        self, rename_analyzer, database_connection
    ):
        """Test complete table rename workflow from analysis to recommendations."""
        # Create a realistic business scenario: user management system
        test_id = str(uuid.uuid4())[:8]
        users_table = f"business_users_{test_id}"
        orders_table = f"business_orders_{test_id}"
        profiles_table = f"business_profiles_{test_id}"
        user_stats_view = f"business_user_stats_{test_id}"

        try:
            # Create business scenario with realistic dependencies
            await database_connection.execute(
                f"""
                -- Core users table
                CREATE TABLE {users_table} (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    username VARCHAR(100) UNIQUE NOT NULL,
                    first_name VARCHAR(100) NOT NULL,
                    last_name VARCHAR(100) NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    status VARCHAR(20) DEFAULT 'active'
                );

                -- Orders with CASCADE delete (high risk)
                CREATE TABLE {orders_table} (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    total_amount DECIMAL(12,2) NOT NULL,
                    order_status VARCHAR(50) DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT NOW(),
                    CONSTRAINT fk_{orders_table}_user_id FOREIGN KEY (user_id)
                        REFERENCES {users_table}(id) ON DELETE CASCADE ON UPDATE CASCADE
                );

                -- Profiles with SET NULL (medium risk)
                CREATE TABLE {profiles_table} (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER,
                    bio TEXT,
                    avatar_url VARCHAR(500),
                    preferences JSONB,
                    created_at TIMESTAMP DEFAULT NOW(),
                    CONSTRAINT fk_{profiles_table}_user_id FOREIGN KEY (user_id)
                        REFERENCES {users_table}(id) ON DELETE SET NULL ON UPDATE CASCADE
                );

                -- Realistic indexes for performance
                CREATE INDEX idx_{users_table}_email ON {users_table}(email);
                CREATE INDEX idx_{users_table}_username ON {users_table}(username);
                CREATE INDEX idx_{users_table}_status ON {users_table}(status);
                CREATE INDEX idx_{users_table}_created_at ON {users_table}(created_at);

                CREATE INDEX idx_{orders_table}_user_id ON {orders_table}(user_id);
                CREATE INDEX idx_{orders_table}_status ON {orders_table}(order_status);
                CREATE INDEX idx_{orders_table}_created_at ON {orders_table}(created_at);

                -- Business intelligence view
                CREATE VIEW {user_stats_view} AS
                SELECT
                    u.id,
                    u.email,
                    u.username,
                    u.first_name || ' ' || u.last_name as full_name,
                    u.status,
                    COUNT(DISTINCT o.id) as total_orders,
                    COALESCE(SUM(o.total_amount), 0) as lifetime_value,
                    MAX(o.created_at) as last_order_date,
                    u.created_at as user_since
                FROM {users_table} u
                LEFT JOIN {orders_table} o ON u.id = o.user_id
                WHERE u.status = 'active'
                GROUP BY u.id, u.email, u.username, u.first_name, u.last_name, u.status, u.created_at
                ORDER BY lifetime_value DESC;

                -- Add some realistic test data
                INSERT INTO {users_table} (email, username, first_name, last_name) VALUES
                    ('admin@company.com', 'admin', 'System', 'Administrator'),
                    ('john.doe@company.com', 'johndoe', 'John', 'Doe'),
                    ('jane.smith@company.com', 'janesmith', 'Jane', 'Smith');

                INSERT INTO {orders_table} (user_id, total_amount, order_status) VALUES
                    (1, 1500.00, 'completed'),
                    (2, 250.50, 'completed'),
                    (2, 89.99, 'shipped'),
                    (3, 1200.00, 'pending');

                INSERT INTO {profiles_table} (user_id, bio) VALUES
                    (1, 'System administrator account'),
                    (2, 'Regular customer since 2023'),
                    (3, 'VIP customer');
            """
            )

            # Phase 1: Complete Rename Analysis
            print(f"\\n=== PHASE 1: ANALYZING RENAME {users_table} -> customers ===")

            start_time = time.time()
            rename_report = await rename_analyzer.analyze_table_rename(
                users_table, "customers"
            )
            analysis_time = time.time() - start_time

            # Validate comprehensive analysis
            assert isinstance(rename_report, TableRenameReport)
            assert rename_report.old_table_name == users_table
            assert rename_report.new_table_name == "customers"
            assert (
                analysis_time < 10.0
            ), f"Analysis took {analysis_time:.2f}s, should be <10s"

            print(f"Analysis completed in {analysis_time:.3f}s")
            print(f"Found {len(rename_report.schema_objects)} dependent objects")

            # Phase 2: Dependency Analysis Validation
            print("\\n=== PHASE 2: DEPENDENCY ANALYSIS VALIDATION ===")

            # Must find all critical dependencies
            object_types = {obj.object_type for obj in rename_report.schema_objects}
            print(f"Object types found: {[ot.value for ot in object_types]}")

            # Must find FK constraints (most critical)
            fk_objects = [
                obj
                for obj in rename_report.schema_objects
                if obj.object_type == SchemaObjectType.FOREIGN_KEY
            ]
            assert (
                len(fk_objects) >= 2
            ), f"Expected ≥2 FK constraints, found {len(fk_objects)}"

            # Must find indexes (performance critical)
            index_objects = [
                obj
                for obj in rename_report.schema_objects
                if obj.object_type == SchemaObjectType.INDEX
            ]
            assert (
                len(index_objects) >= 4
            ), f"Expected ≥4 indexes, found {len(index_objects)}"

            # Validate CASCADE constraint detection (data loss risk)
            cascade_constraints = [
                fk
                for fk in fk_objects
                if "CASCADE" in fk.definition
                and fk.impact_level == RenameImpactLevel.CRITICAL
            ]
            assert (
                len(cascade_constraints) >= 1
            ), "Must detect CASCADE constraints as CRITICAL"

            print(
                f"✓ Found {len(fk_objects)} FK constraints ({len(cascade_constraints)} CASCADE)"
            )
            print(f"✓ Found {len(index_objects)} indexes")

            # Phase 3: Risk Assessment Validation
            print("\\n=== PHASE 3: RISK ASSESSMENT VALIDATION ===")

            impact_summary = rename_report.impact_summary
            print(f"Overall Risk: {impact_summary.overall_risk.value}")
            print(
                f"Critical: {impact_summary.critical_count}, High: {impact_summary.high_count}"
            )
            print(
                f"Medium: {impact_summary.medium_count}, Total: {impact_summary.total_objects}"
            )

            # Must be CRITICAL due to CASCADE constraints
            assert (
                impact_summary.overall_risk == RenameImpactLevel.CRITICAL
            ), f"Expected CRITICAL risk due to CASCADE constraints, got {impact_summary.overall_risk.value}"

            # Must have coordination requirements
            assert (
                impact_summary.requires_coordination
            ), "Complex rename must require coordination"
            assert (
                impact_summary.total_objects > 5
            ), "Should find multiple dependent objects"

            # Phase 4: Dependency Graph Analysis
            print("\\n=== PHASE 4: DEPENDENCY GRAPH ANALYSIS ===")

            dependency_graph = rename_report.dependency_graph
            assert isinstance(dependency_graph, DependencyGraph)
            assert dependency_graph.root_table == users_table
            assert len(dependency_graph.nodes) == len(rename_report.schema_objects)

            critical_deps = dependency_graph.get_critical_dependencies()
            print(f"Critical dependencies: {len(critical_deps)}")
            assert len(critical_deps) >= 1, "Must identify critical dependencies"

            # Phase 5: Business Impact Assessment
            print("\\n=== PHASE 5: BUSINESS IMPACT ASSESSMENT ===")

            # Simulate business decision making
            business_risk_factors = {
                "data_loss_risk": len(cascade_constraints) > 0,
                "downtime_required": impact_summary.requires_coordination,
                "application_impact": len(
                    [
                        obj
                        for obj in rename_report.schema_objects
                        if obj.requires_sql_rewrite
                    ]
                )
                > 0,
                "performance_impact": len(index_objects) > 0,
                "complexity_score": impact_summary.total_objects,
            }

            print("Business Risk Assessment:")
            for factor, value in business_risk_factors.items():
                print(f"  {factor}: {value}")

            # Must identify high business impact
            assert business_risk_factors[
                "data_loss_risk"
            ], "Must identify data loss risk"
            assert business_risk_factors[
                "downtime_required"
            ], "Must identify downtime requirements"
            assert (
                business_risk_factors["complexity_score"] > 5
            ), "Must identify complexity"

            # Phase 6: Validation and Safety Checks
            print("\\n=== PHASE 6: VALIDATION AND SAFETY CHECKS ===")

            validation = rename_report.validation
            assert (
                validation.is_valid
            ), f"Valid rename should pass validation: {validation.violations}"

            # Test invalid scenarios
            invalid_validation = await rename_analyzer.validate_rename_operation(
                users_table, "users; DROP TABLE orders;"
            )
            assert not invalid_validation.is_valid, "SQL injection should be detected"

            print("✓ Safety validation passed")
            print("✓ SQL injection detection working")

            # Phase 7: Performance and Scalability
            print("\\n=== PHASE 7: PERFORMANCE VALIDATION ===")

            # Verify analysis completes within reasonable time for production use
            assert (
                analysis_time < 5.0
            ), f"Analysis too slow for production: {analysis_time:.2f}s"

            # Verify memory efficiency (schema objects should be reasonable)
            assert (
                len(rename_report.schema_objects) < 100
            ), "Too many objects found - may indicate inefficient queries"

            print(f"✓ Analysis performance: {analysis_time:.3f}s")
            print(f"✓ Memory efficiency: {len(rename_report.schema_objects)} objects")

            print("\\n=== E2E TEST COMPLETED SUCCESSFULLY ===")
            print(f"✓ Complete workflow validated for {users_table} rename")
            print(f"✓ Risk level: {impact_summary.overall_risk.value}")
            print(f"✓ Dependencies: {impact_summary.total_objects} objects")
            print(f"✓ Performance: {analysis_time:.3f}s analysis time")

        finally:
            # Comprehensive cleanup
            cleanup_objects = [
                f"DROP VIEW IF EXISTS {user_stats_view} CASCADE",
                f"DROP TABLE IF EXISTS {profiles_table} CASCADE",
                f"DROP TABLE IF EXISTS {orders_table} CASCADE",
                f"DROP TABLE IF EXISTS {users_table} CASCADE",
            ]

            for cleanup_sql in cleanup_objects:
                try:
                    await database_connection.execute(cleanup_sql)
                except Exception as e:
                    print(f"Cleanup warning: {e}")

    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_edge_case_scenarios_e2e(self, rename_analyzer, database_connection):
        """Test edge cases and error scenarios in E2E fashion."""
        test_id = str(uuid.uuid4())[:8]

        # Test 1: Empty table (no dependencies)
        empty_table = f"empty_table_{test_id}"
        try:
            await database_connection.execute(
                f"""
                CREATE TABLE {empty_table} (id SERIAL PRIMARY KEY);
            """
            )

            report = await rename_analyzer.analyze_table_rename(
                empty_table, "renamed_empty"
            )
            assert report.impact_summary.overall_risk in [
                RenameImpactLevel.SAFE,
                RenameImpactLevel.MEDIUM,
                RenameImpactLevel.HIGH,
            ]

        finally:
            await database_connection.execute(
                f"DROP TABLE IF EXISTS {empty_table} CASCADE"
            )

        # Test 2: Non-existent table
        report = await rename_analyzer.analyze_table_rename(
            f"nonexistent_{test_id}", "new_name"
        )
        assert report.impact_summary.overall_risk == RenameImpactLevel.SAFE
        assert len(report.schema_objects) == 0

        # Test 3: Invalid rename validation
        validation = await rename_analyzer.validate_rename_operation("", "")
        assert not validation.is_valid

        validation = await rename_analyzer.validate_rename_operation("table", "table")
        assert not validation.is_valid

        print("✓ Edge case scenarios validated")

    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_production_readiness_e2e(self, rename_analyzer):
        """Test production readiness characteristics."""
        print("\\n=== PRODUCTION READINESS VALIDATION ===")

        # Test concurrent analysis (simplified - same analyzer, different tables)
        tasks = []
        for i in range(3):
            task = rename_analyzer.analyze_table_rename(
                f"nonexistent_table_{i}", f"renamed_{i}"
            )
            tasks.append(task)

        start_time = time.time()
        reports = await asyncio.gather(*tasks)
        concurrent_time = time.time() - start_time

        # Verify all completed successfully
        assert len(reports) == 3
        assert all(isinstance(r, TableRenameReport) for r in reports)

        # Performance should not degrade significantly
        assert (
            concurrent_time < 2.0
        ), f"Concurrent analysis too slow: {concurrent_time:.2f}s"

        print(f"✓ Concurrent analysis: {concurrent_time:.3f}s for 3 tables")
        print("✓ Production readiness validated")
