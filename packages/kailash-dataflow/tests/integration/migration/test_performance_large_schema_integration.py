#!/usr/bin/env python3
"""
Performance Testing with Large Schema Validation for TODO-137

Tests the performance requirements for the TODO-137 Column Removal Dependency Analysis system
under enterprise-scale conditions with large, complex database schemas.

PERFORMANCE REQUIREMENTS TESTED:
1. <30 seconds for dependency analysis of 1000+ database objects
2. <512MB memory usage for dependency graph storage
3. 100% dependency detection accuracy under performance constraints
4. Linear performance scaling (not exponential degradation)
5. Memory cleanup and garbage collection efficiency

Following Tier 2 testing guidelines:
- Uses real PostgreSQL Docker infrastructure (NO MOCKING)
- Timeout: <35 seconds per test (to allow for 30s requirement + overhead)
- Tests actual large-scale database operations
- Validates memory usage with real dependency graphs
- CRITICAL PRIORITY: Enterprise deployment readiness

Performance Test Setup:
1. Run: ./tests/utils/test-env up && ./tests/utils/test-env status
2. Verify PostgreSQL running on port 5434
3. Tests use large-scale real database schemas (1000+ objects)
4. Memory profiling enabled for resource usage validation
"""

import asyncio
import gc
import logging
import time
import tracemalloc
from typing import Any, Dict, List, Tuple

import asyncpg
import psutil
import pytest
from dataflow.migrations.column_removal_manager import (
    BackupStrategy,
    ColumnRemovalManager,
    RemovalPlan,
    SafetyValidation,
)
from dataflow.migrations.dependency_analyzer import (
    DependencyAnalyzer,
    DependencyReport,
    DependencyType,
    ImpactLevel,
)
from dataflow.migrations.impact_reporter import ImpactReporter, OutputFormat
from dataflow.migrations.migration_connection_manager import MigrationConnectionManager

from kailash.runtime.local import LocalRuntime

# Import test infrastructure
from tests.infrastructure.test_harness import (
    DatabaseConfig,
    DatabaseInfrastructure,
    IntegrationTestSuite,
)

# Configure logging for performance test debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_memory_usage() -> float:
    """Get current memory usage in MB."""
    process = psutil.Process()
    memory_info = process.memory_info()
    return memory_info.rss / 1024 / 1024  # Convert bytes to MB


def start_memory_profiling() -> None:
    """Start memory profiling."""
    tracemalloc.start()
    gc.collect()  # Clean up before measuring


def get_memory_profile() -> Tuple[float, float]:
    """Get memory profile results in MB."""
    if not tracemalloc.is_tracing():
        return 0.0, 0.0

    current, peak = tracemalloc.get_traced_memory()
    return current / 1024 / 1024, peak / 1024 / 1024  # Convert to MB


def stop_memory_profiling() -> None:
    """Stop memory profiling."""
    if tracemalloc.is_tracing():
        tracemalloc.stop()


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


# Integration test fixtures
@pytest.fixture(scope="session")
async def test_database():
    """Set up test database infrastructure."""
    config = DatabaseConfig.from_environment()
    infrastructure = DatabaseInfrastructure(config)
    await infrastructure.initialize()

    yield infrastructure

    # Cleanup
    if infrastructure._pool:
        await infrastructure._pool.close()


@pytest.fixture
async def connection_manager(test_database):
    """Create connection manager for tests."""

    class MockDataFlow:
        def __init__(self, url):
            self.config = type("Config", (), {})()
            self.config.database = type("Database", (), {})()
            self.config.database.url = url

    config = test_database.config
    mock_dataflow = MockDataFlow(config.url)
    manager = MigrationConnectionManager(mock_dataflow)

    yield manager

    # Cleanup
    manager.close_all_connections()


@pytest.fixture
async def performance_components(connection_manager):
    """Create all components for performance testing."""
    dependency_analyzer = DependencyAnalyzer(connection_manager)
    column_removal_manager = ColumnRemovalManager(connection_manager)
    impact_reporter = ImpactReporter()

    return dependency_analyzer, column_removal_manager, impact_reporter


@pytest.fixture
async def test_connection(test_database):
    """Direct connection for test setup."""
    pool = test_database._pool
    async with pool.acquire() as conn:
        yield conn


@pytest.fixture(autouse=True)
async def clean_performance_schema(test_connection):
    """Clean performance test schema before each test."""
    await test_connection.execute(
        """
        DO $$
        DECLARE
            r RECORD;
        BEGIN
            -- Drop views
            FOR r IN (SELECT schemaname, viewname FROM pg_views
                     WHERE schemaname = 'public' AND viewname LIKE 'perf_%')
            LOOP
                EXECUTE 'DROP VIEW IF EXISTS ' || quote_ident(r.schemaname) || '.' || quote_ident(r.viewname) || ' CASCADE';
            END LOOP;

            -- Drop functions
            FOR r IN (SELECT routine_schema, routine_name FROM information_schema.routines
                     WHERE routine_schema = 'public' AND routine_name LIKE 'perf_%')
            LOOP
                EXECUTE 'DROP FUNCTION IF EXISTS ' || quote_ident(r.routine_schema) || '.' || quote_ident(r.routine_name) || ' CASCADE';
            END LOOP;

            -- Drop tables (with CASCADE to handle FKs)
            FOR r IN (SELECT schemaname, tablename FROM pg_tables
                     WHERE schemaname = 'public' AND tablename LIKE 'perf_%')
            LOOP
                EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.schemaname) || '.' || quote_ident(r.tablename) || ' CASCADE';
            END LOOP;
        END $$;
    """
    )


@pytest.mark.integration
@pytest.mark.timeout(120)  # Allow extra time for large schema setup
class TestPerformanceLargeSchema:
    """Performance tests for large enterprise schema scenarios."""

    @pytest.mark.asyncio
    async def test_large_schema_dependency_analysis_performance(
        self, performance_components, test_connection
    ):
        """
        PERFORMANCE TEST: Large Schema Dependency Analysis (<30 seconds requirement)

        Creates a large enterprise-scale schema with 1000+ objects and validates
        that dependency analysis completes within 30 seconds with accurate results.
        """
        dependency_analyzer, column_removal_manager, impact_reporter = (
            performance_components
        )

        logger.info(
            "🚀 PERFORMANCE TEST: Large schema dependency analysis (<30s requirement)"
        )

        # Configuration for large schema
        NUM_MAIN_TABLES = 50
        NUM_DEPENDENT_TABLES_PER_MAIN = 20  # 50 * 20 = 1000 dependent tables
        NUM_VIEWS_PER_MAIN = 5  # 50 * 5 = 250 views
        NUM_INDEXES_PER_TABLE = 3  # Additional indexes

        total_expected_objects = (
            NUM_MAIN_TABLES
            + (NUM_MAIN_TABLES * NUM_DEPENDENT_TABLES_PER_MAIN)
            + (NUM_MAIN_TABLES * NUM_VIEWS_PER_MAIN)
        )

        logger.info(
            f"Creating large schema: {NUM_MAIN_TABLES} main tables, ~{total_expected_objects} total objects"
        )

        # Start memory profiling
        start_memory_profiling()
        initial_memory = get_memory_usage()

        schema_creation_start = time.time()

        try:
            # Create main tables with target columns
            main_tables = []
            for i in range(NUM_MAIN_TABLES):
                table_name = f"perf_main_{i:03d}"
                main_tables.append(table_name)

                await test_connection.execute(
                    f"""
                    CREATE TABLE {table_name} (
                        id SERIAL PRIMARY KEY,
                        shared_key VARCHAR(50) NOT NULL,  -- Common FK target
                        business_id VARCHAR(50) UNIQUE NOT NULL,  -- Another FK target
                        name VARCHAR(255) NOT NULL,
                        data JSONB DEFAULT '{{}}'::jsonb,
                        created_at TIMESTAMP DEFAULT NOW()
                    );
                """
                )

                # Create indexes for realistic performance
                await test_connection.execute(
                    f"""
                    CREATE INDEX {table_name}_shared_key_idx ON {table_name}(shared_key);
                    CREATE INDEX {table_name}_business_id_idx ON {table_name}(business_id);
                    CREATE INDEX {table_name}_created_at_idx ON {table_name}(created_at DESC);
                """
                )

            # Create dependent tables with foreign keys
            for i, main_table in enumerate(main_tables):
                for j in range(NUM_DEPENDENT_TABLES_PER_MAIN):
                    dep_table = f"perf_dep_{i:03d}_{j:02d}"

                    await test_connection.execute(
                        f"""
                        CREATE TABLE {dep_table} (
                            id SERIAL PRIMARY KEY,
                            main_shared_key VARCHAR(50) NOT NULL,
                            main_business_id VARCHAR(50) NOT NULL,
                            dep_data TEXT,
                            amount DECIMAL(12,2) DEFAULT 0.00,
                            CONSTRAINT fk_{dep_table}_shared FOREIGN KEY (main_shared_key)
                                REFERENCES {main_table}(shared_key) ON DELETE CASCADE,
                            CONSTRAINT fk_{dep_table}_business FOREIGN KEY (main_business_id)
                                REFERENCES {main_table}(business_id) ON DELETE RESTRICT
                        );
                    """
                    )

                    # Create index on FK columns
                    await test_connection.execute(
                        f"""
                        CREATE INDEX {dep_table}_main_keys_idx ON {dep_table}(main_shared_key, main_business_id);
                    """
                    )

            # Create views that use the target columns
            for i, main_table in enumerate(main_tables):
                for j in range(NUM_VIEWS_PER_MAIN):
                    view_name = f"perf_view_{i:03d}_{j:02d}"

                    # Create views that reference the target columns
                    sample_deps = [
                        f"perf_dep_{i:03d}_{k:02d}"
                        for k in range(min(3, NUM_DEPENDENT_TABLES_PER_MAIN))
                    ]

                    view_definition = f"""
                        CREATE VIEW {view_name} AS
                        SELECT
                            m.id, m.shared_key, m.business_id, m.name,
                            COUNT(d1.id) as dep_count_1,
                            COALESCE(SUM(d1.amount), 0) as total_amount
                        FROM {main_table} m
                        LEFT JOIN {sample_deps[0]} d1 ON m.shared_key = d1.main_shared_key
                        GROUP BY m.id, m.shared_key, m.business_id, m.name
                    """

                    await test_connection.execute(view_definition)

            schema_creation_time = time.time() - schema_creation_start
            schema_memory = get_memory_usage() - initial_memory

            # Verify schema size
            object_counts = await test_connection.fetchrow(
                """
                SELECT
                    (SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'perf_%') as table_count,
                    (SELECT COUNT(*) FROM pg_views WHERE schemaname = 'public' AND viewname LIKE 'perf_%') as view_count,
                    (SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'public' AND indexname LIKE 'perf_%') as index_count
            """
            )

            total_objects = (
                object_counts["table_count"]
                + object_counts["view_count"]
                + object_counts["index_count"]
            )

            logger.info(
                f"Schema created: {schema_creation_time:.2f}s, {total_objects} objects, {schema_memory:.1f}MB"
            )
            logger.info(f"  - Tables: {object_counts['table_count']}")
            logger.info(f"  - Views: {object_counts['view_count']}")
            logger.info(f"  - Indexes: {object_counts['index_count']}")

            # Verify we have a large enough schema for the test
            assert (
                total_objects >= 1000
            ), f"Schema too small for performance test: {total_objects} objects"

            # **MAIN PERFORMANCE TEST**: Analyze dependencies for high-impact column
            logger.info("Starting dependency analysis performance test...")

            # Target the most connected table's shared_key (should have many dependencies)
            target_table = main_tables[0]  # First main table
            target_column = "shared_key"  # Column with many FK references

            analysis_start_time = time.time()
            analysis_start_memory = get_memory_usage()

            # **CRITICAL PERFORMANCE REQUIREMENT**: Must complete in <30 seconds
            dependency_report = await dependency_analyzer.analyze_column_dependencies(
                target_table, target_column
            )

            analysis_time = time.time() - analysis_start_time
            analysis_memory = get_memory_usage() - analysis_start_memory
            current_memory, peak_memory = get_memory_profile()

            # **PERFORMANCE VALIDATION 1**: <30 second requirement
            assert (
                analysis_time < 30.0
            ), f"PERFORMANCE FAILURE: Analysis took {analysis_time:.2f}s (requirement: <30s)"

            # **PERFORMANCE VALIDATION 2**: <512MB memory requirement
            assert (
                peak_memory < 512.0
            ), f"PERFORMANCE FAILURE: Peak memory {peak_memory:.1f}MB (requirement: <512MB)"

            # **ACCURACY VALIDATION**: Verify all dependencies were detected
            assert (
                dependency_report.has_dependencies() is True
            ), "Should detect dependencies in large schema"

            total_deps = dependency_report.get_total_dependency_count()
            assert (
                total_deps >= NUM_DEPENDENT_TABLES_PER_MAIN
            ), f"Should detect at least {NUM_DEPENDENT_TABLES_PER_MAIN} dependencies"

            # Verify foreign key detection accuracy
            fk_deps = dependency_report.dependencies.get(DependencyType.FOREIGN_KEY, [])
            assert (
                len(fk_deps) >= NUM_DEPENDENT_TABLES_PER_MAIN
            ), f"Should detect {NUM_DEPENDENT_TABLES_PER_MAIN} FK deps, found {len(fk_deps)}"

            # Verify view detection
            view_deps = dependency_report.dependencies.get(DependencyType.VIEW, [])
            assert (
                len(view_deps) >= NUM_VIEWS_PER_MAIN
            ), f"Should detect {NUM_VIEWS_PER_MAIN} view deps, found {len(view_deps)}"

            # All foreign keys should be CRITICAL (referencing target column)
            critical_deps = dependency_report.get_critical_dependencies()
            assert (
                len(critical_deps) >= NUM_DEPENDENT_TABLES_PER_MAIN
            ), "All FKs should be critical"

            # **PERFORMANCE METRICS LOGGING**
            deps_per_second = total_deps / analysis_time if analysis_time > 0 else 0
            memory_per_dep = peak_memory / total_deps if total_deps > 0 else 0

            logger.info("🎯 PERFORMANCE TEST RESULTS:")
            logger.info(f"  ✅ Analysis time: {analysis_time:.2f}s (requirement: <30s)")
            logger.info(f"  ✅ Peak memory: {peak_memory:.1f}MB (requirement: <512MB)")
            logger.info(f"  ✅ Dependencies found: {total_deps}")
            logger.info(f"  ✅ Analysis rate: {deps_per_second:.1f} deps/second")
            logger.info(f"  ✅ Memory efficiency: {memory_per_dep:.2f} MB/dependency")
            logger.info(f"  ✅ Schema scale: {total_objects} database objects")

            # Test impact reporting performance
            logger.info("Testing impact reporting performance...")

            report_start = time.time()
            impact_report = impact_reporter.generate_impact_report(dependency_report)
            console_report = impact_reporter.format_user_friendly_report(
                impact_report, OutputFormat.CONSOLE
            )
            report_time = time.time() - report_start

            assert report_time < 5.0, f"Report generation too slow: {report_time:.2f}s"
            assert len(console_report) > 0, "Report should not be empty"

            logger.info(f"  ✅ Report generation: {report_time:.2f}s")

            # Test removal planning performance
            logger.info("Testing removal planning performance...")

            plan_start = time.time()
            removal_plan = await column_removal_manager.plan_column_removal(
                target_table, target_column, BackupStrategy.TABLE_SNAPSHOT
            )
            plan_time = time.time() - plan_start

            assert plan_time < 10.0, f"Removal planning too slow: {plan_time:.2f}s"
            assert (
                len(removal_plan.dependencies) == total_deps
            ), "Planning should include all dependencies"

            logger.info(f"  ✅ Removal planning: {plan_time:.2f}s")

        finally:
            stop_memory_profiling()

            # Memory cleanup verification
            gc.collect()
            final_memory = get_memory_usage()
            memory_freed = max(0, peak_memory + analysis_start_memory - final_memory)

            logger.info(f"Memory cleanup: {memory_freed:.1f}MB freed")

    @pytest.mark.asyncio
    async def test_concurrent_analysis_performance(
        self, performance_components, test_connection
    ):
        """
        PERFORMANCE TEST: Concurrent Analysis Performance

        Tests performance when multiple dependency analyses run concurrently,
        simulating multiple users or parallel migration operations.
        """
        dependency_analyzer, column_removal_manager, impact_reporter = (
            performance_components
        )

        logger.info("🚀 PERFORMANCE TEST: Concurrent analysis performance")

        # Create schema for concurrent testing
        await test_connection.execute(
            """
            CREATE TABLE perf_concurrent_base (
                id SERIAL PRIMARY KEY,
                shared_column VARCHAR(50) NOT NULL
            );
        """
        )

        # Create multiple dependent tables
        num_tables = 20
        for i in range(num_tables):
            await test_connection.execute(
                f"""
                CREATE TABLE perf_concurrent_dep_{i} (
                    id SERIAL PRIMARY KEY,
                    base_shared VARCHAR(50) NOT NULL,
                    data_col_{i} VARCHAR(255),
                    CONSTRAINT fk_concurrent_{i} FOREIGN KEY (base_shared)
                        REFERENCES perf_concurrent_base(shared_column) ON DELETE CASCADE
                );
                CREATE INDEX perf_concurrent_dep_{i}_shared_idx ON perf_concurrent_dep_{i}(base_shared);
            """
            )

        # Create views
        for i in range(5):
            await test_connection.execute(
                f"""
                CREATE VIEW perf_concurrent_view_{i} AS
                SELECT b.id, b.shared_column, COUNT(d.id) as dep_count
                FROM perf_concurrent_base b
                LEFT JOIN perf_concurrent_dep_{i} d ON b.shared_column = d.base_shared
                GROUP BY b.id, b.shared_column;
            """
            )

        # Test concurrent dependency analysis
        start_memory = get_memory_usage()

        async def analyze_dependencies(table_suffix="base"):
            """Analyze dependencies for concurrent testing."""
            start_time = time.time()

            # Each concurrent analysis targets the same column
            report = await dependency_analyzer.analyze_column_dependencies(
                "perf_concurrent_base", "shared_column"
            )

            analysis_time = time.time() - start_time
            return {
                "analysis_time": analysis_time,
                "dependency_count": report.get_total_dependency_count(),
                "has_dependencies": report.has_dependencies(),
            }

        # Run multiple concurrent analyses
        concurrent_start = time.time()

        concurrent_tasks = [analyze_dependencies(f"task_{i}") for i in range(5)]
        results = await asyncio.gather(*concurrent_tasks)

        concurrent_time = time.time() - concurrent_start
        peak_memory = get_memory_usage() - start_memory

        # Validate concurrent performance
        max_individual_time = max(r["analysis_time"] for r in results)
        min_individual_time = min(r["analysis_time"] for r in results)
        avg_individual_time = sum(r["analysis_time"] for r in results) / len(results)

        # All analyses should complete reasonably quickly
        assert (
            max_individual_time < 10.0
        ), f"Concurrent analysis too slow: {max_individual_time:.2f}s"

        # Memory usage should be reasonable for concurrent operations
        assert (
            peak_memory < 256.0
        ), f"Concurrent memory usage too high: {peak_memory:.1f}MB"

        # All analyses should detect the same dependencies
        dependency_counts = [r["dependency_count"] for r in results]
        assert all(
            count == dependency_counts[0] for count in dependency_counts
        ), "Concurrent analyses should detect same dependencies"

        logger.info("Concurrent analysis results:")
        logger.info(f"  - Total time: {concurrent_time:.2f}s")
        logger.info(
            f"  - Individual times: min={min_individual_time:.2f}s, max={max_individual_time:.2f}s, avg={avg_individual_time:.2f}s"
        )
        logger.info(f"  - Peak memory: {peak_memory:.1f}MB")
        logger.info(f"  - Dependencies per analysis: {dependency_counts[0]}")

    @pytest.mark.asyncio
    async def test_memory_efficiency_large_dependency_graphs(
        self, performance_components, test_connection
    ):
        """
        PERFORMANCE TEST: Memory Efficiency for Large Dependency Graphs

        Tests memory usage efficiency when storing and processing large
        dependency graphs with complex interconnections.
        """
        dependency_analyzer, column_removal_manager, impact_reporter = (
            performance_components
        )

        logger.info(
            "🚀 PERFORMANCE TEST: Memory efficiency for large dependency graphs"
        )

        start_memory_profiling()
        initial_memory = get_memory_usage()

        # Create deeply interconnected schema
        num_levels = 10
        nodes_per_level = 15

        # Create hierarchical foreign key structure
        prev_table = None
        all_tables = []

        for level in range(num_levels):
            for node in range(nodes_per_level):
                table_name = f"perf_mem_L{level}_N{node}"
                all_tables.append(table_name)

                create_sql = f"""
                    CREATE TABLE {table_name} (
                        id SERIAL PRIMARY KEY,
                        level_{level}_key VARCHAR(50) NOT NULL,
                        node_data TEXT DEFAULT 'sample data for memory testing'
                """

                # Add foreign key to previous level
                if level > 0:
                    prev_level_table = f"perf_mem_L{level-1}_N{node % nodes_per_level}"
                    create_sql += f""",
                        prev_level_key VARCHAR(50),
                        CONSTRAINT fk_{table_name}_prev FOREIGN KEY (prev_level_key)
                            REFERENCES {prev_level_table}(level_{level-1}_key) ON DELETE CASCADE
                    """

                create_sql += ");"

                await test_connection.execute(create_sql)

                # Create index for performance
                await test_connection.execute(
                    f"""
                    CREATE INDEX {table_name}_level_key_idx ON {table_name}(level_{level}_key);
                """
                )

        # Create cross-level views for complex dependencies
        for level in range(1, min(5, num_levels)):  # Avoid too many views
            for node in range(min(5, nodes_per_level)):
                view_name = f"perf_mem_view_L{level}_N{node}"

                await test_connection.execute(
                    f"""
                    CREATE VIEW {view_name} AS
                    SELECT
                        l0.id as root_id,
                        l0.level_0_key,
                        l{level}.level_{level}_key,
                        COUNT(*) as hierarchy_count
                    FROM perf_mem_L0_N{node % nodes_per_level} l0
                    JOIN perf_mem_L{level}_N{node} l{level} ON l0.level_0_key = l{level}.prev_level_key
                    GROUP BY l0.id, l0.level_0_key, l{level}.level_{level}_key;
                """
                )

        schema_memory = get_memory_usage() - initial_memory

        # Test memory efficiency during analysis
        logger.info(
            f"Testing memory efficiency with {len(all_tables)} interconnected tables..."
        )

        analysis_start_memory = get_memory_usage()

        # Analyze the root table (should trigger analysis of entire hierarchy)
        root_table = "perf_mem_L0_N0"
        dependency_report = await dependency_analyzer.analyze_column_dependencies(
            root_table, "level_0_key"
        )

        analysis_peak_memory = get_memory_usage() - analysis_start_memory
        current_traced, peak_traced = get_memory_profile()

        # Verify dependency detection
        total_deps = dependency_report.get_total_dependency_count()
        assert total_deps > 0, "Should detect dependencies in hierarchical schema"

        # **MEMORY EFFICIENCY VALIDATION**
        # Memory per dependency should be reasonable
        memory_per_dependency = peak_traced / total_deps if total_deps > 0 else 0

        assert (
            memory_per_dependency < 1.0
        ), f"Memory per dependency too high: {memory_per_dependency:.2f}MB"
        assert peak_traced < 512.0, f"Peak memory too high: {peak_traced:.1f}MB"

        logger.info("Memory efficiency results:")
        logger.info(f"  - Schema creation: {schema_memory:.1f}MB")
        logger.info(f"  - Analysis peak: {peak_traced:.1f}MB")
        logger.info(f"  - Dependencies found: {total_deps}")
        logger.info(f"  - Memory per dependency: {memory_per_dependency:.3f}MB")
        logger.info(f"  - Total objects analyzed: {len(all_tables)} tables + views")

        # Test memory cleanup
        dependency_report = None  # Release reference
        gc.collect()

        cleanup_memory = get_memory_usage()
        memory_freed = analysis_peak_memory - (cleanup_memory - analysis_start_memory)

        logger.info(f"  - Memory freed after cleanup: {memory_freed:.1f}MB")

        stop_memory_profiling()

    @pytest.mark.asyncio
    async def test_performance_scaling_characteristics(
        self, performance_components, test_connection
    ):
        """
        PERFORMANCE TEST: Performance Scaling Characteristics

        Tests how performance scales with increasing schema complexity to ensure
        linear (not exponential) scaling behavior.
        """
        dependency_analyzer, column_removal_manager, impact_reporter = (
            performance_components
        )

        logger.info("🚀 PERFORMANCE TEST: Performance scaling characteristics")

        scaling_results = []

        # Test different schema sizes
        test_sizes = [10, 25, 50, 100]

        for size in test_sizes:
            logger.info(f"Testing performance with {size} dependent objects...")

            # Clean up previous test
            await test_connection.execute(
                """
                DO $$
                DECLARE
                    r RECORD;
                BEGIN
                    FOR r IN (SELECT schemaname, tablename FROM pg_tables
                             WHERE schemaname = 'public' AND tablename LIKE 'perf_scale_%')
                    LOOP
                        EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.schemaname) || '.' || quote_ident(r.tablename) || ' CASCADE';
                    END LOOP;
                END $$;
            """
            )

            # Create base table
            await test_connection.execute(
                """
                CREATE TABLE perf_scale_base (
                    id SERIAL PRIMARY KEY,
                    scale_key VARCHAR(50) NOT NULL
                );
            """
            )

            schema_start = time.time()

            # Create dependent tables
            for i in range(size):
                await test_connection.execute(
                    f"""
                    CREATE TABLE perf_scale_dep_{i} (
                        id SERIAL PRIMARY KEY,
                        base_key VARCHAR(50) NOT NULL,
                        data_{i} TEXT,
                        CONSTRAINT fk_scale_{i} FOREIGN KEY (base_key)
                            REFERENCES perf_scale_base(scale_key) ON DELETE CASCADE
                    );
                """
                )

            schema_time = time.time() - schema_start

            # Measure analysis performance
            start_memory = get_memory_usage()
            analysis_start = time.time()

            dependency_report = await dependency_analyzer.analyze_column_dependencies(
                "perf_scale_base", "scale_key"
            )

            analysis_time = time.time() - analysis_start
            memory_used = get_memory_usage() - start_memory

            total_deps = dependency_report.get_total_dependency_count()

            scaling_results.append(
                {
                    "size": size,
                    "schema_time": schema_time,
                    "analysis_time": analysis_time,
                    "memory_used": memory_used,
                    "dependencies_found": total_deps,
                    "time_per_dependency": (
                        analysis_time / total_deps if total_deps > 0 else 0
                    ),
                }
            )

            logger.info(
                f"  Size {size}: {analysis_time:.2f}s, {memory_used:.1f}MB, {total_deps} deps"
            )

        # Analyze scaling characteristics
        logger.info("Performance scaling analysis:")
        logger.info("Size | Analysis Time | Memory | Deps | Time/Dep")
        logger.info("-" * 50)

        for result in scaling_results:
            logger.info(
                f"{result['size']:4d} | {result['analysis_time']:11.2f}s | {result['memory_used']:6.1f}MB | {result['dependencies_found']:4d} | {result['time_per_dependency']:8.4f}s"
            )

        # Validate scaling characteristics
        times = [r["analysis_time"] for r in scaling_results]
        sizes = [r["size"] for r in scaling_results]

        # Check that performance doesn't degrade exponentially
        # Time per dependency should remain relatively constant
        time_per_deps = [r["time_per_dependency"] for r in scaling_results]

        # Variation in time per dependency should be reasonable (not exponential growth)
        max_time_per_dep = max(time_per_deps)
        min_time_per_dep = min(time_per_deps)
        variation_ratio = (
            max_time_per_dep / min_time_per_dep
            if min_time_per_dep > 0
            else float("inf")
        )

        assert (
            variation_ratio < 3.0
        ), f"Performance scaling too poor: {variation_ratio:.2f}x variation"

        # Largest test should still meet performance requirements
        largest_test = scaling_results[-1]
        assert (
            largest_test["analysis_time"] < 15.0
        ), f"Largest test too slow: {largest_test['analysis_time']:.2f}s"

        logger.info(
            f"Scaling validation: {variation_ratio:.2f}x performance variation (requirement: <3.0x)"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
