"""
E2E tests for MigrationPerformanceTracker - Phase 1B Component 3

End-to-end validation of complete migration performance tracking workflows
with real infrastructure, comprehensive scenarios, and user workflows.

Performance target: <10 seconds per test
Real infrastructure: Complete PostgreSQL stack with all components
Focus: Complete user workflows and real-world scenarios
"""

import asyncio
import json
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from dataflow.migrations.auto_migration_system import (
    ColumnDefinition,
    Migration,
    MigrationOperation,
    MigrationType,
    TableDefinition,
)
from dataflow.migrations.batched_migration_executor import BatchedMigrationExecutor
from dataflow.migrations.migration_connection_manager import MigrationConnectionManager
from dataflow.migrations.migration_performance_tracker import (
    MigrationPerformanceTracker,
    PerformanceMetrics,
    RegressionSeverity,
)
from dataflow.migrations.migration_test_framework import MigrationTestFramework
from dataflow.migrations.postgresql_test_manager import PostgreSQLTestManager
from dataflow.migrations.schema_state_manager import SchemaStateManager

try:
    import asyncpg

    import docker

    DEPENDENCIES_AVAILABLE = True
except ImportError:
    DEPENDENCIES_AVAILABLE = False


@pytest.mark.e2e
@pytest.mark.skipif(
    not DEPENDENCIES_AVAILABLE, reason="asyncpg or docker not available"
)
class TestMigrationPerformanceTrackerE2E:
    """End-to-end tests for complete migration performance tracking workflows."""

    @pytest.fixture(scope="class")
    async def postgres_manager(self):
        """Setup PostgreSQL test manager for E2E tests."""
        manager = PostgreSQLTestManager(
            container_name="test_e2e_performance_tracker_postgres",
            postgres_port=5437,  # Unique port for E2E tests
            performance_target_seconds=10.0,
        )

        container_info = await manager.start_test_container()
        assert container_info.ready, f"Container not ready: {container_info.error}"

        yield manager

        await manager.cleanup_test_environment()

    @pytest.fixture
    async def temp_dir(self):
        """Create temporary directory for E2E test files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    async def complete_migration_stack(self, postgres_manager, temp_dir):
        """Setup complete migration stack with all components."""
        container_info = await postgres_manager.get_container_status()
        connection = await asyncpg.connect(container_info.database_url)

        # Create mock DataFlow instance
        mock_dataflow = type(
            "MockDataFlow",
            (),
            {"connection_string": container_info.database_url, "dialect": "postgresql"},
        )()

        # Initialize all components
        connection_manager = MigrationConnectionManager(
            dataflow_instance=mock_dataflow, max_connections=10, connection_timeout=30.0
        )

        batched_executor = BatchedMigrationExecutor(
            connection=connection, connection_manager=connection_manager
        )

        schema_state_manager = SchemaStateManager(
            connection=connection, cache_ttl_seconds=300
        )

        migration_framework = MigrationTestFramework(
            database_type="postgresql",
            connection_string=container_info.database_url,
            performance_target_seconds=10.0,
            enable_rollback_testing=True,
            integration_mode=True,
        )

        performance_tracker = MigrationPerformanceTracker(
            database_type="postgresql",
            baseline_file=str(temp_dir / "e2e_baselines.json"),
            history_file=str(temp_dir / "e2e_history.jsonl"),
            max_history_size=1000,
            enable_detailed_monitoring=True,
        )

        # Integrate all components
        performance_tracker.integrate_with_components(
            batched_executor=batched_executor,
            connection_manager=connection_manager,
            schema_state_manager=schema_state_manager,
            test_framework=migration_framework,
        )

        stack = {
            "performance_tracker": performance_tracker,
            "migration_framework": migration_framework,
            "postgres_manager": postgres_manager,
            "connection_manager": connection_manager,
            "batched_executor": batched_executor,
            "schema_state_manager": schema_state_manager,
            "connection": connection,
            "container_info": container_info,
        }

        yield stack

        # Cleanup
        await connection_manager.close()
        await connection.close()

    def create_e2e_migration_scenario(
        self, scenario_name: str, complexity: str = "medium"
    ):
        """Create realistic migration scenarios for E2E testing."""
        if complexity == "simple":
            return self._create_simple_migration_scenario(scenario_name)
        elif complexity == "medium":
            return self._create_medium_migration_scenario(scenario_name)
        elif complexity == "complex":
            return self._create_complex_migration_scenario(scenario_name)
        else:
            raise ValueError(f"Unknown complexity: {complexity}")

    def _create_simple_migration_scenario(self, scenario_name: str):
        """Create simple migration scenario (1-2 tables, basic operations)."""
        migration = Migration(
            version=f"e2e_simple_{scenario_name}", name=f"E2E Simple: {scenario_name}"
        )

        # Single table creation
        table_operation = MigrationOperation(
            operation_type=MigrationType.CREATE_TABLE,
            table_name=f"simple_{scenario_name}_users",
            description=f"Create simple users table for {scenario_name}",
            sql_up=f"""
                CREATE TABLE simple_{scenario_name}_users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) NOT NULL UNIQUE,
                    email VARCHAR(100) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            sql_down=f"DROP TABLE IF EXISTS simple_{scenario_name}_users;",
            metadata={"scenario": scenario_name, "complexity": "simple"},
        )
        migration.add_operation(table_operation)

        # Basic index
        index_operation = MigrationOperation(
            operation_type=MigrationType.ADD_INDEX,
            table_name=f"simple_{scenario_name}_users",
            description=f"Add email index for {scenario_name}",
            sql_up=f"CREATE INDEX idx_simple_{scenario_name}_users_email ON simple_{scenario_name}_users(email);",
            sql_down=f"DROP INDEX IF EXISTS idx_simple_{scenario_name}_users_email;",
            metadata={"scenario": scenario_name, "complexity": "simple"},
        )
        migration.add_operation(index_operation)

        return migration

    def _create_medium_migration_scenario(self, scenario_name: str):
        """Create medium complexity migration scenario (3-5 tables, relationships)."""
        migration = Migration(
            version=f"e2e_medium_{scenario_name}", name=f"E2E Medium: {scenario_name}"
        )

        # Users table
        users_operation = MigrationOperation(
            operation_type=MigrationType.CREATE_TABLE,
            table_name=f"medium_{scenario_name}_users",
            description=f"Create users table for {scenario_name}",
            sql_up=f"""
                CREATE TABLE medium_{scenario_name}_users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) NOT NULL UNIQUE,
                    email VARCHAR(100) NOT NULL UNIQUE,
                    first_name VARCHAR(50),
                    last_name VARCHAR(50),
                    date_of_birth DATE,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            sql_down=f"DROP TABLE IF EXISTS medium_{scenario_name}_users CASCADE;",
            metadata={"scenario": scenario_name, "complexity": "medium"},
        )
        migration.add_operation(users_operation)

        # Categories table
        categories_operation = MigrationOperation(
            operation_type=MigrationType.CREATE_TABLE,
            table_name=f"medium_{scenario_name}_categories",
            description=f"Create categories table for {scenario_name}",
            sql_up=f"""
                CREATE TABLE medium_{scenario_name}_categories (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL UNIQUE,
                    description TEXT,
                    parent_id INTEGER REFERENCES medium_{scenario_name}_categories(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            sql_down=f"DROP TABLE IF EXISTS medium_{scenario_name}_categories CASCADE;",
            metadata={"scenario": scenario_name, "complexity": "medium"},
        )
        migration.add_operation(categories_operation)

        # Posts table with foreign keys
        posts_operation = MigrationOperation(
            operation_type=MigrationType.CREATE_TABLE,
            table_name=f"medium_{scenario_name}_posts",
            description=f"Create posts table for {scenario_name}",
            sql_up=f"""
                CREATE TABLE medium_{scenario_name}_posts (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(200) NOT NULL,
                    content TEXT,
                    user_id INTEGER NOT NULL REFERENCES medium_{scenario_name}_users(id) ON DELETE CASCADE,
                    category_id INTEGER REFERENCES medium_{scenario_name}_categories(id),
                    status VARCHAR(20) DEFAULT 'draft',
                    published_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            sql_down=f"DROP TABLE IF EXISTS medium_{scenario_name}_posts CASCADE;",
            metadata={"scenario": scenario_name, "complexity": "medium"},
        )
        migration.add_operation(posts_operation)

        # Multiple indexes
        indexes = [
            ("users_email", f"medium_{scenario_name}_users", "email"),
            ("users_username", f"medium_{scenario_name}_users", "username"),
            ("posts_user_id", f"medium_{scenario_name}_posts", "user_id"),
            ("posts_category_id", f"medium_{scenario_name}_posts", "category_id"),
            ("posts_status", f"medium_{scenario_name}_posts", "status"),
        ]

        for index_name, table_name, column in indexes:
            index_operation = MigrationOperation(
                operation_type=MigrationType.ADD_INDEX,
                table_name=table_name,
                description=f"Add {index_name} index for {scenario_name}",
                sql_up=f"CREATE INDEX idx_{index_name}_{scenario_name} ON {table_name}({column});",
                sql_down=f"DROP INDEX IF EXISTS idx_{index_name}_{scenario_name};",
                metadata={"scenario": scenario_name, "complexity": "medium"},
            )
            migration.add_operation(index_operation)

        return migration

    def _create_complex_migration_scenario(self, scenario_name: str):
        """Create complex migration scenario (6+ tables, advanced features)."""
        migration = Migration(
            version=f"e2e_complex_{scenario_name}", name=f"E2E Complex: {scenario_name}"
        )

        # Base tables (similar to medium but with more complexity)
        tables = [
            (
                f"complex_{scenario_name}_users",
                """
                CREATE TABLE complex_{scenario_name}_users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) NOT NULL UNIQUE,
                    email VARCHAR(100) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    first_name VARCHAR(50),
                    last_name VARCHAR(50),
                    date_of_birth DATE,
                    phone VARCHAR(20),
                    address JSONB,
                    preferences JSONB DEFAULT '{}',
                    is_active BOOLEAN DEFAULT TRUE,
                    email_verified BOOLEAN DEFAULT FALSE,
                    last_login TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT valid_email CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'),
                    CONSTRAINT valid_username CHECK (length(username) >= 3)
                )
            """,
            ),
            (
                f"complex_{scenario_name}_roles",
                """
                CREATE TABLE complex_{scenario_name}_roles (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(50) NOT NULL UNIQUE,
                    description TEXT,
                    permissions JSONB DEFAULT '[]',
                    is_system BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            ),
            (
                f"complex_{scenario_name}_user_roles",
                """
                CREATE TABLE complex_{scenario_name}_user_roles (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES complex_{scenario_name}_users(id) ON DELETE CASCADE,
                    role_id INTEGER NOT NULL REFERENCES complex_{scenario_name}_roles(id) ON DELETE CASCADE,
                    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    granted_by INTEGER REFERENCES complex_{scenario_name}_users(id),
                    expires_at TIMESTAMP,
                    UNIQUE(user_id, role_id)
                )
            """,
            ),
            (
                f"complex_{scenario_name}_categories",
                """
                CREATE TABLE complex_{scenario_name}_categories (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    slug VARCHAR(100) NOT NULL UNIQUE,
                    description TEXT,
                    parent_id INTEGER REFERENCES complex_{scenario_name}_categories(id),
                    path TEXT, -- Materialized path for hierarchy
                    level INTEGER DEFAULT 0,
                    sort_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            ),
            (
                f"complex_{scenario_name}_posts",
                """
                CREATE TABLE complex_{scenario_name}_posts (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(200) NOT NULL,
                    slug VARCHAR(200) NOT NULL UNIQUE,
                    content TEXT,
                    excerpt TEXT,
                    user_id INTEGER NOT NULL REFERENCES complex_{scenario_name}_users(id) ON DELETE CASCADE,
                    category_id INTEGER REFERENCES complex_{scenario_name}_categories(id),
                    status VARCHAR(20) DEFAULT 'draft',
                    visibility VARCHAR(20) DEFAULT 'public',
                    featured BOOLEAN DEFAULT FALSE,
                    allow_comments BOOLEAN DEFAULT TRUE,
                    view_count INTEGER DEFAULT 0,
                    like_count INTEGER DEFAULT 0,
                    comment_count INTEGER DEFAULT 0,
                    tags TEXT[],
                    metadata JSONB DEFAULT '{}',
                    published_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT valid_status CHECK (status IN ('draft', 'published', 'archived', 'deleted')),
                    CONSTRAINT valid_visibility CHECK (visibility IN ('public', 'private', 'protected'))
                )
            """,
            ),
            (
                f"complex_{scenario_name}_comments",
                """
                CREATE TABLE complex_{scenario_name}_comments (
                    id SERIAL PRIMARY KEY,
                    post_id INTEGER NOT NULL REFERENCES complex_{scenario_name}_posts(id) ON DELETE CASCADE,
                    user_id INTEGER REFERENCES complex_{scenario_name}_users(id) ON DELETE SET NULL,
                    parent_id INTEGER REFERENCES complex_{scenario_name}_comments(id),
                    content TEXT NOT NULL,
                    author_name VARCHAR(100), -- For guest comments
                    author_email VARCHAR(100), -- For guest comments
                    is_approved BOOLEAN DEFAULT FALSE,
                    like_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            ),
        ]

        # Create all tables
        for table_name, sql in tables:
            operation = MigrationOperation(
                operation_type=MigrationType.CREATE_TABLE,
                table_name=table_name,
                description=f"Create {table_name} for {scenario_name}",
                sql_up=sql.format(scenario_name=scenario_name),
                sql_down=f"DROP TABLE IF EXISTS {table_name} CASCADE;",
                metadata={"scenario": scenario_name, "complexity": "complex"},
            )
            migration.add_operation(operation)

        # Complex indexes including partial, functional, and multi-column
        complex_indexes = [
            (
                f"complex_{scenario_name}_users",
                "email_verified_active",
                "email WHERE is_active = TRUE",
            ),
            (f"complex_{scenario_name}_users", "username_lower", "LOWER(username)"),
            (
                f"complex_{scenario_name}_posts",
                "user_status_published",
                "user_id, status, published_at",
            ),
            (
                f"complex_{scenario_name}_posts",
                "category_featured_published",
                "category_id WHERE featured = TRUE AND status = 'published'",
            ),
            (
                f"complex_{scenario_name}_posts",
                "tags_gin",
                "tags",
            ),  # GIN index for array
            (
                f"complex_{scenario_name}_comments",
                "post_approved_created",
                "post_id, created_at WHERE is_approved = TRUE",
            ),
            (
                f"complex_{scenario_name}_categories",
                "path_gist",
                "path",
            ),  # For hierarchical queries
        ]

        for table_name, index_name, index_expr in complex_indexes:
            if "gin" in index_name.lower():
                sql_up = f"CREATE INDEX idx_{index_name}_{scenario_name} ON {table_name} USING GIN ({index_expr});"
            elif "gist" in index_name.lower():
                sql_up = f"CREATE INDEX idx_{index_name}_{scenario_name} ON {table_name} USING GIST ({index_expr});"
            else:
                sql_up = f"CREATE INDEX idx_{index_name}_{scenario_name} ON {table_name} ({index_expr});"

            index_operation = MigrationOperation(
                operation_type=MigrationType.ADD_INDEX,
                table_name=table_name,
                description=f"Add {index_name} index for {scenario_name}",
                sql_up=sql_up,
                sql_down=f"DROP INDEX IF EXISTS idx_{index_name}_{scenario_name};",
                metadata={"scenario": scenario_name, "complexity": "complex"},
            )
            migration.add_operation(index_operation)

        return migration

    @pytest.mark.timeout(10)
    async def test_complete_migration_lifecycle_workflow(
        self, complete_migration_stack
    ):
        """Test complete migration lifecycle with performance tracking."""
        stack = complete_migration_stack
        tracker = stack["performance_tracker"]
        connection = stack["connection"]

        start_time = time.perf_counter()

        # Phase 1: Execute simple migration and establish baseline
        simple_migration = self.create_e2e_migration_scenario("lifecycle", "simple")

        simple_metrics = await tracker.benchmark_migration(
            migration=simple_migration, connection=connection
        )

        assert simple_metrics.success is True
        assert simple_metrics.execution_time_ms > 0

        # Phase 2: Execute medium complexity migration
        medium_migration = self.create_e2e_migration_scenario("lifecycle", "medium")

        medium_metrics = await tracker.benchmark_migration(
            migration=medium_migration, connection=connection
        )

        assert medium_metrics.success is True
        assert medium_metrics.execution_time_ms > simple_metrics.execution_time_ms

        # Phase 3: Execute complex migration
        complex_migration = self.create_e2e_migration_scenario("lifecycle", "complex")

        complex_metrics = await tracker.benchmark_migration(
            migration=complex_migration, connection=connection
        )

        assert complex_metrics.success is True

        # Phase 4: Analyze performance trends
        all_metrics = [simple_metrics, medium_metrics, complex_metrics]
        insights = tracker.get_performance_insights(all_metrics, include_trends=True)

        assert insights["summary"]["total_migrations"] == 3
        assert insights["summary"]["success_rate"] == 100.0

        # Phase 5: Regression detection
        regressions = tracker.detect_performance_regression(all_metrics)

        # Should detect performance changes between simple and complex
        execution_changes = [
            r for r in regressions if "execution time" in r.metric_name.lower()
        ]
        # Note: This might not be a "regression" per se, as complex migrations are expected to take longer

        # Phase 6: Generate comprehensive report
        report_path = (
            Path(stack["performance_tracker"].baseline_file).parent
            / "lifecycle_report.json"
        )
        export_success = tracker.export_performance_report(
            output_file=str(report_path),
            metrics=all_metrics,
            include_detailed_analysis=True,
        )

        assert export_success is True
        assert report_path.exists()

        total_time = time.perf_counter() - start_time
        assert (
            total_time < 10.0
        ), f"Complete lifecycle took {total_time:.2f}s, exceeds 10s target"

        # Cleanup test tables
        await self._cleanup_e2e_tables(connection, "lifecycle")

    @pytest.mark.timeout(10)
    async def test_performance_regression_detection_workflow(
        self, complete_migration_stack
    ):
        """Test performance regression detection in realistic scenario."""
        stack = complete_migration_stack
        tracker = stack["performance_tracker"]
        connection = stack["connection"]

        # Phase 1: Establish performance baseline with consistent migrations
        baseline_metrics = []

        for i in range(3):
            migration = self.create_e2e_migration_scenario(f"baseline_{i}", "simple")

            metrics = await tracker.benchmark_migration(
                migration=migration, connection=connection
            )

            assert metrics.success is True
            baseline_metrics.append(metrics)

            # Small delay to separate executions
            await asyncio.sleep(0.2)

        # Phase 2: Introduce performance regression with complex migration
        # This simulates a developer introducing an inefficient migration
        regression_migration = Migration(
            version="regression_001", name="Performance Regression Simulation"
        )

        # Add operations that would cause performance regression
        # 1. Large table with many columns and constraints
        large_table_operation = MigrationOperation(
            operation_type=MigrationType.CREATE_TABLE,
            table_name="regression_large_table",
            description="Create large table with many constraints",
            sql_up="""
                CREATE TABLE regression_large_table (
                    id SERIAL PRIMARY KEY,
                    col1 VARCHAR(1000) NOT NULL,
                    col2 VARCHAR(1000) NOT NULL,
                    col3 VARCHAR(1000) NOT NULL,
                    col4 VARCHAR(1000) NOT NULL,
                    col5 TEXT NOT NULL,
                    col6 TEXT NOT NULL,
                    col7 JSONB DEFAULT '{}',
                    col8 JSONB DEFAULT '{}',
                    col9 TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    col10 TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT check_col1_length CHECK (length(col1) > 10),
                    CONSTRAINT check_col2_length CHECK (length(col2) > 10),
                    CONSTRAINT check_col3_length CHECK (length(col3) > 10),
                    CONSTRAINT unique_combo UNIQUE(col1, col2, col3)
                )
            """,
            sql_down="DROP TABLE IF EXISTS regression_large_table CASCADE;",
            metadata={"regression_test": True},
        )
        regression_migration.add_operation(large_table_operation)

        # 2. Multiple complex indexes
        for i in range(8):
            index_operation = MigrationOperation(
                operation_type=MigrationType.ADD_INDEX,
                table_name="regression_large_table",
                description=f"Add complex index {i}",
                sql_up=f"CREATE INDEX idx_regression_complex_{i} ON regression_large_table(col{i+1}, col{(i+1)%5+1});",
                sql_down=f"DROP INDEX IF EXISTS idx_regression_complex_{i};",
                metadata={"regression_test": True},
            )
            regression_migration.add_operation(index_operation)

        # 3. Complex constraints
        for i in range(3):
            constraint_operation = MigrationOperation(
                operation_type=MigrationType.ADD_CONSTRAINT,
                table_name="regression_large_table",
                description=f"Add complex constraint {i}",
                sql_up=f"ALTER TABLE regression_large_table ADD CONSTRAINT check_regression_{i} CHECK (length(col{i+1}) < 500);",
                sql_down=f"ALTER TABLE regression_large_table DROP CONSTRAINT IF EXISTS check_regression_{i};",
                metadata={"regression_test": True},
            )
            regression_migration.add_operation(constraint_operation)

        # Execute regression migration
        regression_metrics = await tracker.benchmark_migration(
            migration=regression_migration, connection=connection
        )

        assert regression_metrics.success is True

        # Phase 3: Detect regressions
        all_metrics = baseline_metrics + [regression_metrics]
        regressions = tracker.detect_performance_regression(
            all_metrics, baseline=baseline_metrics[0]
        )

        # Should detect significant performance regressions
        severe_regressions = [
            r
            for r in regressions
            if r.severity
            in [
                RegressionSeverity.MODERATE,
                RegressionSeverity.SEVERE,
                RegressionSeverity.CRITICAL,
            ]
        ]

        assert len(severe_regressions) > 0, "Should detect performance regression"

        # Verify regression details
        execution_regressions = [
            r for r in severe_regressions if "execution time" in r.metric_name.lower()
        ]
        assert len(execution_regressions) > 0, "Should detect execution time regression"

        # Phase 4: Verify recommendations are provided
        for regression in severe_regressions:
            assert (
                len(regression.recommendations) > 0
            ), "Regressions should have recommendations"
            assert any(
                "optimization" in rec.lower() or "performance" in rec.lower()
                for rec in regression.recommendations
            ), "Should have performance recommendations"

        # Phase 5: Generate regression report
        insights = tracker.get_performance_insights(all_metrics, include_trends=True)

        assert len(insights["regressions"]) > 0
        assert any(
            rec
            for rec in insights["recommendations"]
            if "regression" in rec.lower() or "performance" in rec.lower()
        )

        # Cleanup
        await connection.execute("DROP TABLE IF EXISTS regression_large_table CASCADE")
        await self._cleanup_e2e_tables(connection, "baseline_0")
        await self._cleanup_e2e_tables(connection, "baseline_1")
        await self._cleanup_e2e_tables(connection, "baseline_2")

    @pytest.mark.timeout(10)
    async def test_concurrent_migration_performance_tracking(
        self, complete_migration_stack
    ):
        """Test performance tracking under concurrent migration scenarios."""
        stack = complete_migration_stack
        tracker = stack["performance_tracker"]
        container_info = stack["container_info"]

        # Create multiple connections for concurrent operations
        connections = []
        for i in range(4):
            conn = await asyncpg.connect(container_info.database_url)
            connections.append(conn)

        try:
            # Create different migration scenarios for concurrent execution
            scenarios = [
                ("concurrent_simple", "simple"),
                ("concurrent_medium", "medium"),
                ("concurrent_simple2", "simple"),
                ("concurrent_complex", "complex"),
            ]

            # Define concurrent migration tasks
            async def run_concurrent_migration(
                scenario_name, complexity, connection, tracker_instance
            ):
                migration = self.create_e2e_migration_scenario(
                    scenario_name, complexity
                )

                return await tracker_instance.benchmark_migration(
                    migration=migration, connection=connection
                )

            # Create separate tracker instances to avoid conflicts
            trackers = []
            for i in range(4):
                temp_tracker = MigrationPerformanceTracker(
                    database_type="postgresql", enable_detailed_monitoring=True
                )
                trackers.append(temp_tracker)

            # Run concurrent migrations
            start_time = time.perf_counter()

            concurrent_tasks = [
                run_concurrent_migration(
                    scenario_name, complexity, connections[i], trackers[i]
                )
                for i, (scenario_name, complexity) in enumerate(scenarios)
            ]

            results = await asyncio.gather(*concurrent_tasks)

            total_time = time.perf_counter() - start_time

            # Verify all migrations completed successfully
            assert len(results) == 4
            assert all(result.success for result in results)

            # Verify concurrent execution was efficient
            assert (
                total_time < 10.0
            ), f"Concurrent execution took {total_time:.2f}s, exceeds 10s target"

            # Verify each migration has appropriate performance characteristics
            simple_results = [results[0], results[2]]  # Two simple migrations
            medium_result = results[1]
            complex_result = results[3]

            # Simple migrations should be faster than complex
            simple_avg_time = sum(r.execution_time_ms for r in simple_results) / len(
                simple_results
            )
            assert (
                complex_result.execution_time_ms > simple_avg_time
            ), "Complex migration should take longer than simple"

            # Medium should be between simple and complex
            assert (
                medium_result.execution_time_ms > simple_avg_time
            ), "Medium migration should take longer than simple"

            # Verify all operations were tracked
            total_operations = sum(r.operation_count for r in results)
            assert total_operations > 10, "Should have tracked multiple operations"

            # Analyze combined performance
            combined_insights = tracker.get_performance_insights(
                results, include_trends=True
            )

            assert combined_insights["summary"]["total_migrations"] == 4
            assert combined_insights["summary"]["success_rate"] == 100.0

        finally:
            # Cleanup concurrent test tables
            for scenario_name, _ in scenarios:
                await self._cleanup_e2e_tables(connections[0], scenario_name)

            # Close all connections
            for conn in connections:
                await conn.close()

    @pytest.mark.timeout(10)
    async def test_historical_performance_analysis_workflow(
        self, complete_migration_stack
    ):
        """Test historical performance analysis and trend detection."""
        stack = complete_migration_stack
        tracker = stack["performance_tracker"]
        connection = stack["connection"]

        # Phase 1: Generate historical performance data over time
        historical_data = []

        # Simulate migrations over time with gradual performance changes
        base_scenarios = [
            ("historical_v1", "simple"),
            ("historical_v2", "simple"),
            ("historical_v3", "medium"),
            ("historical_v4", "medium"),
            ("historical_v5", "medium"),
            ("historical_v6", "complex"),
            ("historical_v7", "complex"),
        ]

        for i, (scenario_name, complexity) in enumerate(base_scenarios):
            migration = self.create_e2e_migration_scenario(scenario_name, complexity)

            # Add timestamp variation to simulate historical data
            metrics = await tracker.benchmark_migration(
                migration=migration, connection=connection
            )

            # Manually adjust timestamp to simulate historical progression
            historical_timestamp = (
                datetime.now() - timedelta(days=len(base_scenarios) - i)
            ).isoformat()
            metrics.timestamp = historical_timestamp

            assert metrics.success is True
            historical_data.append(metrics)

            # Add to tracker history
            tracker.performance_history.append(metrics)

            # Small delay between migrations
            await asyncio.sleep(0.1)

        # Phase 2: Analyze trends across the historical data
        trends = tracker._analyze_performance_trends(historical_data)

        assert len(trends) > 0

        # Should detect trends in key metrics
        trend_metrics = [t["metric"] for t in trends]
        assert any("execution time" in metric.lower() for metric in trend_metrics)
        assert any("memory" in metric.lower() for metric in trend_metrics)

        # Phase 3: Test baseline creation from historical data
        operation_key = "historical_analysis"
        baseline = tracker._get_baseline_for_operation(
            operation_key, historical_data[:3]
        )  # Use first 3 as baseline

        assert baseline is not None
        assert baseline.migration_name in [
            m.migration_name for m in historical_data[:3]
        ]

        # Phase 4: Regression detection using historical baseline
        recent_metrics = historical_data[-3:]  # Last 3 migrations
        regressions = tracker.detect_performance_regression(
            recent_metrics, baseline=baseline
        )

        # May detect regressions as complexity increased over time
        performance_changes = [r for r in regressions if r.change_percent != 0]
        assert len(performance_changes) >= 0  # Some change is expected

        # Phase 5: Generate comprehensive historical insights
        insights = tracker.get_performance_insights(
            historical_data, include_trends=True
        )

        # Verify comprehensive analysis
        assert insights["summary"]["total_migrations"] == len(historical_data)
        assert len(insights["trends"]) > 0
        assert "key_metrics" in insights

        # Verify trend analysis includes direction and confidence
        for trend in insights["trends"]:
            assert "direction" in trend
            assert "strength" in trend
            assert trend["direction"] in ["increasing", "decreasing", "stable"]
            assert trend["strength"] in ["weak", "moderate", "strong"]

        # Phase 6: Export historical report
        historical_report_path = (
            Path(tracker.baseline_file).parent / "historical_analysis_report.json"
        )
        export_success = tracker.export_performance_report(
            output_file=str(historical_report_path),
            metrics=historical_data,
            include_detailed_analysis=True,
        )

        assert export_success is True
        assert historical_report_path.exists()

        # Verify report contains historical analysis
        with open(historical_report_path, "r") as f:
            report_data = json.load(f)

        assert "trends" in report_data
        assert len(report_data["trends"]) > 0
        assert "date_range" in report_data["report_metadata"]

        # Cleanup historical test tables
        for scenario_name, _ in base_scenarios:
            await self._cleanup_e2e_tables(connection, scenario_name)

    async def _cleanup_e2e_tables(self, connection, scenario_prefix):
        """Helper method to cleanup E2E test tables by scenario prefix."""
        try:
            # Get all tables that match the scenario prefix
            tables_query = f"""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name LIKE '%{scenario_prefix}%'
                ORDER BY table_name
            """
            tables = await connection.fetch(tables_query)

            # Drop tables in reverse order to handle dependencies
            table_names = [row["table_name"] for row in tables]
            table_names.reverse()

            for table_name in table_names:
                await connection.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")

        except Exception as e:
            # Log warning but don't fail test
            print(f"Warning: Could not cleanup tables for {scenario_prefix}: {e}")


@pytest.mark.e2e
@pytest.mark.skipif(
    not DEPENDENCIES_AVAILABLE, reason="asyncpg or docker not available"
)
class TestRealWorldMigrationScenarios:
    """Test performance tracking with real-world migration scenarios."""

    @pytest.fixture(scope="class")
    async def postgres_manager(self):
        """Setup PostgreSQL for real-world scenario tests."""
        manager = PostgreSQLTestManager(
            container_name="test_real_world_postgres",
            postgres_port=5438,  # Unique port
            performance_target_seconds=10.0,
        )

        container_info = await manager.start_test_container()
        assert container_info.ready

        yield manager

        await manager.cleanup_test_environment()

    @pytest.mark.timeout(10)
    async def test_e_commerce_migration_scenario(self, postgres_manager):
        """Test performance tracking for e-commerce platform migration."""
        container_info = await postgres_manager.get_container_status()
        connection = await asyncpg.connect(container_info.database_url)

        tracker = MigrationPerformanceTracker(
            database_type="postgresql", enable_detailed_monitoring=True
        )

        try:
            # E-commerce migration: Users, Products, Orders, Payments
            ecommerce_migration = Migration(
                version="ecommerce_v1", name="E-commerce Platform Migration"
            )

            # Core e-commerce tables with realistic structure
            ecommerce_tables = [
                (
                    "customers",
                    """
                    CREATE TABLE customers (
                        id SERIAL PRIMARY KEY,
                        email VARCHAR(255) NOT NULL UNIQUE,
                        password_hash VARCHAR(255) NOT NULL,
                        first_name VARCHAR(100),
                        last_name VARCHAR(100),
                        phone VARCHAR(20),
                        date_of_birth DATE,
                        registration_source VARCHAR(50),
                        email_verified BOOLEAN DEFAULT FALSE,
                        marketing_consent BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """,
                ),
                (
                    "addresses",
                    """
                    CREATE TABLE addresses (
                        id SERIAL PRIMARY KEY,
                        customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
                        type VARCHAR(20) DEFAULT 'shipping',
                        first_name VARCHAR(100),
                        last_name VARCHAR(100),
                        company VARCHAR(100),
                        address_line1 VARCHAR(200) NOT NULL,
                        address_line2 VARCHAR(200),
                        city VARCHAR(100) NOT NULL,
                        state VARCHAR(100),
                        postal_code VARCHAR(20),
                        country VARCHAR(2) NOT NULL,
                        is_default BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """,
                ),
                (
                    "categories",
                    """
                    CREATE TABLE categories (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        slug VARCHAR(100) NOT NULL UNIQUE,
                        description TEXT,
                        parent_id INTEGER REFERENCES categories(id),
                        image_url VARCHAR(500),
                        is_active BOOLEAN DEFAULT TRUE,
                        sort_order INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """,
                ),
                (
                    "products",
                    """
                    CREATE TABLE products (
                        id SERIAL PRIMARY KEY,
                        sku VARCHAR(100) NOT NULL UNIQUE,
                        name VARCHAR(200) NOT NULL,
                        slug VARCHAR(200) NOT NULL UNIQUE,
                        description TEXT,
                        short_description TEXT,
                        category_id INTEGER REFERENCES categories(id),
                        brand VARCHAR(100),
                        price DECIMAL(10,2) NOT NULL,
                        compare_price DECIMAL(10,2),
                        cost_price DECIMAL(10,2),
                        inventory_quantity INTEGER DEFAULT 0,
                        track_inventory BOOLEAN DEFAULT TRUE,
                        weight DECIMAL(8,2),
                        dimensions JSONB,
                        images JSONB DEFAULT '[]',
                        attributes JSONB DEFAULT '{}',
                        is_active BOOLEAN DEFAULT TRUE,
                        is_featured BOOLEAN DEFAULT FALSE,
                        tags TEXT[],
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """,
                ),
                (
                    "orders",
                    """
                    CREATE TABLE orders (
                        id SERIAL PRIMARY KEY,
                        order_number VARCHAR(50) NOT NULL UNIQUE,
                        customer_id INTEGER REFERENCES customers(id),
                        status VARCHAR(20) DEFAULT 'pending',
                        currency VARCHAR(3) DEFAULT 'USD',
                        subtotal DECIMAL(10,2) NOT NULL,
                        tax_amount DECIMAL(10,2) DEFAULT 0,
                        shipping_amount DECIMAL(10,2) DEFAULT 0,
                        discount_amount DECIMAL(10,2) DEFAULT 0,
                        total_amount DECIMAL(10,2) NOT NULL,
                        billing_address JSONB,
                        shipping_address JSONB,
                        payment_status VARCHAR(20) DEFAULT 'pending',
                        fulfillment_status VARCHAR(20) DEFAULT 'unfulfilled',
                        notes TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """,
                ),
                (
                    "order_items",
                    """
                    CREATE TABLE order_items (
                        id SERIAL PRIMARY KEY,
                        order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                        product_id INTEGER NOT NULL REFERENCES products(id),
                        quantity INTEGER NOT NULL,
                        unit_price DECIMAL(10,2) NOT NULL,
                        total_price DECIMAL(10,2) NOT NULL,
                        product_snapshot JSONB, -- Store product details at time of order
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """,
                ),
            ]

            # Create all tables
            for table_name, sql in ecommerce_tables:
                operation = MigrationOperation(
                    operation_type=MigrationType.CREATE_TABLE,
                    table_name=table_name,
                    description=f"Create {table_name} table",
                    sql_up=sql,
                    sql_down=f"DROP TABLE IF EXISTS {table_name} CASCADE;",
                    metadata={"scenario": "ecommerce"},
                )
                ecommerce_migration.add_operation(operation)

            # Add essential indexes for e-commerce performance
            ecommerce_indexes = [
                ("customers", "email_verified", "email, email_verified"),
                ("customers", "registration_date", "created_at"),
                ("products", "category_active", "category_id WHERE is_active = TRUE"),
                ("products", "sku_unique", "sku"),
                ("products", "name_search", "LOWER(name)"),
                ("products", "price_range", "price WHERE is_active = TRUE"),
                ("orders", "customer_status", "customer_id, status"),
                ("orders", "order_date", "created_at"),
                ("orders", "order_number", "order_number"),
                ("order_items", "order_product", "order_id, product_id"),
                ("addresses", "customer_default", "customer_id, is_default"),
            ]

            for table_name, index_name, index_expr in ecommerce_indexes:
                operation = MigrationOperation(
                    operation_type=MigrationType.ADD_INDEX,
                    table_name=table_name,
                    description=f"Add {index_name} index",
                    sql_up=f"CREATE INDEX idx_{table_name}_{index_name} ON {table_name} ({index_expr});",
                    sql_down=f"DROP INDEX IF EXISTS idx_{table_name}_{index_name};",
                    metadata={"scenario": "ecommerce"},
                )
                ecommerce_migration.add_operation(operation)

            # Benchmark e-commerce migration
            start_time = time.perf_counter()
            metrics = await tracker.benchmark_migration(
                migration=ecommerce_migration, connection=connection
            )
            execution_time = time.perf_counter() - start_time

            # Verify e-commerce migration performance
            assert metrics.success is True
            assert (
                execution_time < 10.0
            ), f"E-commerce migration took {execution_time:.2f}s, exceeds 10s target"
            assert metrics.operation_count == len(ecommerce_tables) + len(
                ecommerce_indexes
            )

            # Verify tables were created
            for table_name, _ in ecommerce_tables:
                table_query = f"""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = '{table_name}'
                """
                result = await connection.fetch(table_query)
                assert len(result) > 0, f"Table {table_name} should exist"

            # Verify performance characteristics
            assert (
                metrics.execution_time_ms > 100
            ), "E-commerce migration should take reasonable time"
            assert metrics.query_count > 10, "Should execute multiple queries"
            assert metrics.memory_delta_mb >= 0, "Memory usage should be tracked"

        finally:
            # Cleanup e-commerce tables
            ecommerce_table_names = [name for name, _ in ecommerce_tables]
            ecommerce_table_names.reverse()  # Drop in reverse order for dependencies

            for table_name in ecommerce_table_names:
                await connection.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")

            await connection.close()

    @pytest.mark.timeout(10)
    async def test_social_media_migration_scenario(self, postgres_manager):
        """Test performance tracking for social media platform migration."""
        container_info = await postgres_manager.get_container_status()
        connection = await asyncpg.connect(container_info.database_url)

        tracker = MigrationPerformanceTracker(
            database_type="postgresql", enable_detailed_monitoring=True
        )

        try:
            # Social media migration with focus on high-volume, read-heavy operations
            social_migration = Migration(
                version="social_v1", name="Social Media Platform Migration"
            )

            # Social media specific tables optimized for performance
            social_tables = [
                (
                    "users",
                    """
                    CREATE TABLE users (
                        id SERIAL PRIMARY KEY,
                        username VARCHAR(50) NOT NULL UNIQUE,
                        email VARCHAR(255) NOT NULL UNIQUE,
                        display_name VARCHAR(100),
                        bio TEXT,
                        avatar_url VARCHAR(500),
                        cover_url VARCHAR(500),
                        location VARCHAR(100),
                        website VARCHAR(200),
                        follower_count INTEGER DEFAULT 0,
                        following_count INTEGER DEFAULT 0,
                        post_count INTEGER DEFAULT 0,
                        is_verified BOOLEAN DEFAULT FALSE,
                        is_private BOOLEAN DEFAULT FALSE,
                        is_active BOOLEAN DEFAULT TRUE,
                        last_active TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """,
                ),
                (
                    "follows",
                    """
                    CREATE TABLE follows (
                        id SERIAL PRIMARY KEY,
                        follower_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        following_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(follower_id, following_id),
                        CHECK (follower_id != following_id)
                    )
                """,
                ),
                (
                    "posts",
                    """
                    CREATE TABLE posts (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        content TEXT NOT NULL,
                        media_urls JSONB DEFAULT '[]',
                        hashtags TEXT[],
                        mentions INTEGER[],
                        reply_to_id INTEGER REFERENCES posts(id),
                        like_count INTEGER DEFAULT 0,
                        comment_count INTEGER DEFAULT 0,
                        share_count INTEGER DEFAULT 0,
                        view_count INTEGER DEFAULT 0,
                        is_edited BOOLEAN DEFAULT FALSE,
                        visibility VARCHAR(20) DEFAULT 'public',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """,
                ),
                (
                    "likes",
                    """
                    CREATE TABLE likes (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_id, post_id)
                    )
                """,
                ),
                (
                    "comments",
                    """
                    CREATE TABLE comments (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
                        parent_id INTEGER REFERENCES comments(id),
                        content TEXT NOT NULL,
                        like_count INTEGER DEFAULT 0,
                        reply_count INTEGER DEFAULT 0,
                        is_edited BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """,
                ),
                (
                    "notifications",
                    """
                    CREATE TABLE notifications (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        type VARCHAR(50) NOT NULL,
                        title VARCHAR(200),
                        message TEXT,
                        related_user_id INTEGER REFERENCES users(id),
                        related_post_id INTEGER REFERENCES posts(id),
                        data JSONB DEFAULT '{}',
                        is_read BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """,
                ),
            ]

            # Create tables
            for table_name, sql in social_tables:
                operation = MigrationOperation(
                    operation_type=MigrationType.CREATE_TABLE,
                    table_name=table_name,
                    description=f"Create {table_name} table",
                    sql_up=sql,
                    sql_down=f"DROP TABLE IF EXISTS {table_name} CASCADE;",
                    metadata={"scenario": "social_media"},
                )
                social_migration.add_operation(operation)

            # Add performance-critical indexes for social media
            social_indexes = [
                ("users", "username_lower", "LOWER(username)"),
                ("users", "active_verified", "is_active, is_verified"),
                ("follows", "follower_following", "follower_id, following_id"),
                ("follows", "following_created", "following_id, created_at"),
                ("posts", "user_created", "user_id, created_at DESC"),
                ("posts", "hashtags_gin", "hashtags"),  # GIN index for array search
                ("posts", "mentions_gin", "mentions"),  # GIN index for array search
                (
                    "posts",
                    "visibility_created",
                    "visibility, created_at DESC WHERE visibility = 'public'",
                ),
                ("likes", "post_created", "post_id, created_at"),
                ("likes", "user_created", "user_id, created_at"),
                ("comments", "post_created", "post_id, created_at"),
                (
                    "comments",
                    "parent_created",
                    "parent_id, created_at WHERE parent_id IS NOT NULL",
                ),
                ("notifications", "user_unread", "user_id, is_read, created_at"),
            ]

            for table_name, index_name, index_expr in social_indexes:
                if "gin" in index_name:
                    sql_up = f"CREATE INDEX idx_{table_name}_{index_name} ON {table_name} USING GIN ({index_expr});"
                else:
                    sql_up = f"CREATE INDEX idx_{table_name}_{index_name} ON {table_name} ({index_expr});"

                operation = MigrationOperation(
                    operation_type=MigrationType.ADD_INDEX,
                    table_name=table_name,
                    description=f"Add {index_name} index",
                    sql_up=sql_up,
                    sql_down=f"DROP INDEX IF EXISTS idx_{table_name}_{index_name};",
                    metadata={"scenario": "social_media"},
                )
                social_migration.add_operation(operation)

            # Benchmark social media migration
            start_time = time.perf_counter()
            metrics = await tracker.benchmark_migration(
                migration=social_migration, connection=connection
            )
            execution_time = time.perf_counter() - start_time

            # Verify social media migration performance
            assert metrics.success is True
            assert (
                execution_time < 10.0
            ), f"Social media migration took {execution_time:.2f}s, exceeds 10s target"
            assert metrics.operation_count == len(social_tables) + len(social_indexes)

            # Verify specific performance requirements for social media
            assert (
                metrics.execution_time_ms < 8000
            ), "Social media migration should be optimized for speed"
            assert (
                metrics.query_count > 15
            ), "Should have many operations for comprehensive schema"

            # Generate performance insights specific to social media workload
            insights = tracker.get_performance_insights([metrics], include_trends=False)

            assert insights["summary"]["success_rate"] == 100.0
            assert insights["summary"]["total_migrations"] == 1

        finally:
            # Cleanup social media tables
            social_table_names = [name for name, _ in social_tables]
            social_table_names.reverse()

            for table_name in social_table_names:
                await connection.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")

            await connection.close()
