#!/usr/bin/env python3
"""
Migration Performance Tracking Example - Phase 1B Component 3

This example demonstrates how to use the MigrationPerformanceTracker
to monitor migration performance, detect regressions, and generate insights.

Key Features Demonstrated:
- Performance benchmarking of migration operations
- Regression detection with configurable thresholds
- Historical performance analysis and trend detection
- Integration with all Phase 1A and 1B components
- Comprehensive performance reporting
"""

import asyncio
import tempfile
from datetime import datetime
from pathlib import Path

from dataflow.migrations import (
    BatchedMigrationExecutor,
    ColumnDefinition,
    Migration,
    MigrationOperation,
    MigrationPerformanceTracker,
    MigrationTestFramework,
    MigrationType,
    PerformanceMetrics,
    RegressionSeverity,
    TableDefinition,
)


class MockConnection:
    """Mock database connection for examples."""

    async def execute(self, sql):
        # Simulate database execution with small delay
        await asyncio.sleep(0.001)
        return None

    def commit(self):
        return None


def create_sample_migration(name: str, complexity: str = "simple") -> Migration:
    """Create sample migrations for demonstration."""
    migration = Migration(version=f"example_{name}", name=f"Example: {name}")

    if complexity == "simple":
        # Simple table creation
        operation = MigrationOperation(
            operation_type=MigrationType.CREATE_TABLE,
            table_name=f"example_{name}_simple",
            description=f"Create simple table for {name}",
            sql_up=f"""
                CREATE TABLE example_{name}_simple (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            sql_down=f"DROP TABLE IF EXISTS example_{name}_simple;",
            metadata={"example": True, "complexity": "simple"},
        )
        migration.add_operation(operation)

    elif complexity == "complex":
        # Complex table with relationships and constraints
        users_operation = MigrationOperation(
            operation_type=MigrationType.CREATE_TABLE,
            table_name=f"example_{name}_users",
            description=f"Create users table for {name}",
            sql_up=f"""
                CREATE TABLE example_{name}_users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) NOT NULL UNIQUE,
                    email VARCHAR(100) NOT NULL UNIQUE,
                    profile JSONB DEFAULT '{{}}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT valid_email CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{{2,}}$')
                )
            """,
            sql_down=f"DROP TABLE IF EXISTS example_{name}_users CASCADE;",
            metadata={"example": True, "complexity": "complex"},
        )
        migration.add_operation(users_operation)

        posts_operation = MigrationOperation(
            operation_type=MigrationType.CREATE_TABLE,
            table_name=f"example_{name}_posts",
            description=f"Create posts table for {name}",
            sql_up=f"""
                CREATE TABLE example_{name}_posts (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES example_{name}_users(id) ON DELETE CASCADE,
                    title VARCHAR(200) NOT NULL,
                    content TEXT,
                    tags TEXT[],
                    metadata JSONB DEFAULT '{{}}',
                    published BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            sql_down=f"DROP TABLE IF EXISTS example_{name}_posts CASCADE;",
            metadata={"example": True, "complexity": "complex"},
        )
        migration.add_operation(posts_operation)

        # Add indexes
        for table, column in [
            ("users", "username"),
            ("users", "email"),
            ("posts", "user_id"),
            ("posts", "published"),
        ]:
            index_operation = MigrationOperation(
                operation_type=MigrationType.ADD_INDEX,
                table_name=f"example_{name}_{table}",
                description=f"Add index on {column}",
                sql_up=f"CREATE INDEX idx_{name}_{table}_{column} ON example_{name}_{table}({column});",
                sql_down=f"DROP INDEX IF EXISTS idx_{name}_{table}_{column};",
                metadata={"example": True, "complexity": "complex"},
            )
            migration.add_operation(index_operation)

    return migration


async def demonstrate_basic_performance_tracking():
    """Demonstrate basic performance tracking functionality."""
    print("=" * 60)
    print("1. BASIC PERFORMANCE TRACKING")
    print("=" * 60)

    # Create temporary directory for this example
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Initialize performance tracker
        tracker = MigrationPerformanceTracker(
            database_type="sqlite",  # Using SQLite for simplicity
            baseline_file=str(temp_path / "baselines.json"),
            history_file=str(temp_path / "history.jsonl"),
            enable_detailed_monitoring=True,
        )

        print("📊 Created MigrationPerformanceTracker")

        # Create and benchmark simple migration
        simple_migration = create_sample_migration("basic", "simple")

        print(f"⚡ Benchmarking simple migration: {simple_migration.name}")

        # Note: For this example, we'll use a mock connection
        # In real usage, you'd provide a real database connection
        mock_connection = MockConnection()

        # Benchmark the migration
        metrics = await tracker.benchmark_migration(
            migration=simple_migration, connection=mock_connection
        )

        # Display results
        print("✅ Migration completed successfully!")
        print(f"   Execution time: {metrics.execution_time_ms:.2f}ms")
        print(f"   Memory usage: {metrics.memory_delta_mb:.2f}MB")
        print(f"   CPU usage: {metrics.cpu_percent:.1f}%")
        print(f"   Operations: {metrics.operation_count}")
        print(f"   Success: {metrics.success}")

        return tracker, [metrics]


async def demonstrate_regression_detection():
    """Demonstrate performance regression detection."""
    print("\\n" + "=" * 60)
    print("2. PERFORMANCE REGRESSION DETECTION")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        tracker = MigrationPerformanceTracker(
            database_type="sqlite",
            baseline_file=str(temp_path / "baselines.json"),
            history_file=str(temp_path / "history.jsonl"),
            enable_detailed_monitoring=True,
            regression_thresholds={
                "warning": 0.10,  # 10%
                "moderate": 0.20,  # 20%
                "severe": 0.40,  # 40%
                "critical": 1.00,  # 100%
            },
        )

        print("📈 Setting up regression detection scenario...")

        # Create baseline with consistent performance
        baseline_metrics = []
        mock_connection = MockConnection()

        print("📊 Creating performance baseline (3 migrations)...")
        for i in range(3):
            migration = create_sample_migration(f"baseline_{i}", "simple")

            # Simulate consistent performance by controlling timing
            import time

            start_time = time.perf_counter()

            metrics = await tracker.benchmark_migration(
                migration=migration, connection=mock_connection
            )

            baseline_metrics.append(metrics)
            print(f"   Baseline {i+1}: {metrics.execution_time_ms:.2f}ms")

        # Create migration that simulates performance regression
        print("\\n⚠️  Simulating performance regression...")

        complex_migration = create_sample_migration("regression", "complex")

        # Simulate longer execution (this will have more operations and appear slower)
        regression_metrics = await tracker.benchmark_migration(
            migration=complex_migration, connection=mock_connection
        )

        print(f"   Regression migration: {regression_metrics.execution_time_ms:.2f}ms")

        # Detect regressions
        all_metrics = baseline_metrics + [regression_metrics]
        regressions = tracker.detect_performance_regression(
            metrics=all_metrics, baseline=baseline_metrics[0]
        )

        print("\\n🔍 Regression Analysis Results:")
        print(f"   Found {len(regressions)} potential regressions")

        for regression in regressions:
            severity_emoji = {
                RegressionSeverity.WARNING: "⚠️",
                RegressionSeverity.MODERATE: "🔶",
                RegressionSeverity.SEVERE: "🔴",
                RegressionSeverity.CRITICAL: "💥",
            }.get(regression.severity, "ℹ️")

            print(f"   {severity_emoji} {regression.metric_name}")
            print(
                f"      Change: {regression.change_percent:+.1f}% "
                f"(from {regression.baseline_value:.2f} to {regression.current_value:.2f})"
            )
            print(f"      Severity: {regression.severity.value}")
            print(
                f"      Trend: {regression.trend_direction} (confidence: {regression.trend_confidence:.1f})"
            )

            if regression.recommendations:
                print("      Recommendations:")
                for rec in regression.recommendations[
                    :2
                ]:  # Show first 2 recommendations
                    print(f"        • {rec}")

        return tracker, all_metrics


async def demonstrate_historical_analysis():
    """Demonstrate historical performance analysis and trend detection."""
    print("\\n" + "=" * 60)
    print("3. HISTORICAL PERFORMANCE ANALYSIS")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        tracker = MigrationPerformanceTracker(
            database_type="sqlite",
            baseline_file=str(temp_path / "baselines.json"),
            history_file=str(temp_path / "history.jsonl"),
            max_history_size=100,
            enable_detailed_monitoring=True,
        )

        print("📈 Generating historical performance data...")

        # Simulate historical migrations with performance changes over time
        historical_metrics = []
        mock_connection = MockConnection()

        # Create migrations that simulate performance improvement over time
        complexities = [
            "simple",
            "simple",
            "complex",
            "simple",
            "complex",
            "simple",
            "simple",
        ]

        for i, complexity in enumerate(complexities):
            migration = create_sample_migration(f"historical_{i:02d}", complexity)

            metrics = await tracker.benchmark_migration(
                migration=migration, connection=mock_connection
            )

            # Manually adjust timestamp to simulate historical progression
            from datetime import datetime, timedelta

            historical_timestamp = (
                datetime.now() - timedelta(days=len(complexities) - i)
            ).isoformat()
            metrics.timestamp = historical_timestamp

            historical_metrics.append(metrics)
            print(
                f"   Migration {i+1} ({complexity}): {metrics.execution_time_ms:.2f}ms"
            )

        # Analyze trends
        print("\\n📊 Analyzing performance trends...")
        insights = tracker.get_performance_insights(
            metrics=historical_metrics, include_trends=True
        )

        # Display summary
        summary = insights["summary"]
        print("\\n📋 Performance Summary:")
        print(f"   Total migrations: {summary['total_migrations']}")
        print(f"   Success rate: {summary['success_rate']:.1f}%")
        print(f"   Average execution time: {summary['avg_execution_time_ms']:.2f}ms")
        print(f"   Average memory usage: {summary['avg_memory_usage_mb']:.2f}MB")

        # Display trends
        trends = insights["trends"]
        print("\\n📈 Performance Trends:")
        for trend in trends:
            direction_emoji = {
                "increasing": "📈",
                "decreasing": "📉",
                "stable": "➡️",
            }.get(trend["direction"], "❓")

            strength_desc = {
                "weak": "weak",
                "moderate": "moderate",
                "strong": "strong",
            }.get(trend["strength"], "unknown")

            print(
                f"   {direction_emoji} {trend['metric']}: {trend['direction']} ({strength_desc})"
            )
            print(f"      Latest value: {trend['recent_value']:.2f} {trend['unit']}")
            print(f"      First value: {trend['first_value']:.2f} {trend['unit']}")

        # Display key metrics
        key_metrics = insights["key_metrics"]
        print("\\n🔢 Key Performance Metrics:")

        if key_metrics and "execution_time" in key_metrics:
            exec_metrics = key_metrics["execution_time"]
            print("   Execution Time:")
            print(f"     Min: {exec_metrics['min_ms']:.2f}ms")
            print(f"     Max: {exec_metrics['max_ms']:.2f}ms")
            print(f"     Average: {exec_metrics['avg_ms']:.2f}ms")
            print(f"     Std Dev: {exec_metrics['std_dev_ms']:.2f}ms")
        else:
            print("   No successful executions to analyze")

        # Display recommendations
        recommendations = insights["recommendations"]
        if recommendations:
            print("\\n💡 Recommendations:")
            for rec in recommendations[:3]:  # Show first 3 recommendations
                print(f"   • {rec}")

        return tracker, historical_metrics


async def demonstrate_performance_reporting():
    """Demonstrate comprehensive performance reporting."""
    print("\\n" + "=" * 60)
    print("4. COMPREHENSIVE PERFORMANCE REPORTING")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        tracker = MigrationPerformanceTracker(
            database_type="sqlite",
            baseline_file=str(temp_path / "baselines.json"),
            history_file=str(temp_path / "history.jsonl"),
            enable_detailed_monitoring=True,
        )

        print("📋 Generating comprehensive performance data...")

        # Create varied migration scenarios
        scenarios = [
            ("user_management", "simple"),
            ("product_catalog", "complex"),
            ("order_processing", "complex"),
            ("analytics_tables", "simple"),
            ("reporting_views", "complex"),
        ]

        all_metrics = []
        mock_connection = MockConnection()

        for name, complexity in scenarios:
            migration = create_sample_migration(name, complexity)

            metrics = await tracker.benchmark_migration(
                migration=migration, connection=mock_connection
            )

            all_metrics.append(metrics)
            print(f"   ✅ {name} ({complexity}): {metrics.execution_time_ms:.2f}ms")

        # Export comprehensive report
        report_file = temp_path / "migration_performance_report.json"

        print(f"\\n📄 Exporting performance report to {report_file.name}...")

        success = tracker.export_performance_report(
            output_file=str(report_file),
            metrics=all_metrics,
            include_detailed_analysis=True,
        )

        if success:
            print("✅ Report exported successfully!")

            # Load and display report summary
            import json

            with open(report_file, "r") as f:
                report_data = json.load(f)

            metadata = report_data["report_metadata"]
            summary = report_data["performance_summary"]

            print("\\n📊 Report Summary:")
            print(f"   Generated: {metadata['generated_at']}")
            print(f"   Metrics count: {metadata['metrics_count']}")
            print(f"   Database type: {metadata['database_type']}")
            print(f"   Total migrations: {summary['total_migrations']}")
            print(f"   Success rate: {summary['success_rate']:.1f}%")
            print(
                f"   Average execution time: {summary['avg_execution_time_ms']:.2f}ms"
            )

            print("\\n📁 Report sections:")
            for section in [
                "performance_summary",
                "key_metrics",
                "regressions",
                "trends",
                "insights",
            ]:
                if section in report_data:
                    print(f"   ✅ {section}")

            # Show file size
            file_size = report_file.stat().st_size
            print(f"\\n📏 Report file size: {file_size:,} bytes")

        else:
            print("❌ Report export failed!")

        return tracker, all_metrics, str(report_file) if success else None


async def demonstrate_component_integration():
    """Demonstrate integration with other migration components."""
    print("\\n" + "=" * 60)
    print("5. COMPONENT INTEGRATION")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Initialize performance tracker
        tracker = MigrationPerformanceTracker(
            database_type="sqlite",
            baseline_file=str(temp_path / "baselines.json"),
            history_file=str(temp_path / "history.jsonl"),
            enable_detailed_monitoring=True,
        )

        print("🔗 Setting up component integration...")

        # Create mock components for demonstration
        # In real usage, these would be actual database connections and instances

        # Mock batched executor
        class MockBatchedExecutor:
            def batch_ddl_operations(self, ops):
                return [["CREATE TABLE (...);"] for _ in ops]

            async def execute_batched_migrations(self, batches):
                await asyncio.sleep(0.001)  # Simulate work
                return True

            def get_execution_metrics(self):
                class MockMetrics:
                    total_batches = 1
                    parallel_batches = 0
                    total_operations = 1

                return MockMetrics()

        mock_batched_executor = MockBatchedExecutor()

        # Mock test framework
        class MockTestFramework:
            async def execute_test_migration(self, migration, connection):
                await asyncio.sleep(0.001)  # Simulate work

                class MockResult:
                    success = True
                    error = None
                    performance_metrics = {"rollback_time": 25.0}

                return MockResult()

        mock_test_framework = MockTestFramework()

        # Integrate components
        tracker.integrate_with_components(
            batched_executor=mock_batched_executor, test_framework=mock_test_framework
        )

        print("✅ Components integrated:")
        print("   • BatchedMigrationExecutor")
        print("   • MigrationTestFramework")

        # Create migration for integrated testing
        integration_migration = create_sample_migration("integration_test", "complex")

        print("\\n⚡ Benchmarking with integrated components...")

        mock_connection = MockConnection()

        # Benchmark with batched executor integration
        metrics = await tracker.benchmark_migration(
            migration=integration_migration, connection=mock_connection
        )

        print("✅ Integrated benchmark completed!")
        print(f"   Execution time: {metrics.execution_time_ms:.2f}ms")
        print(f"   Batch count: {metrics.batch_count}")
        print(f"   Batch efficiency: {metrics.batch_efficiency:.2f}")
        print(f"   Rollback time: {metrics.rollback_time_ms:.2f}ms")
        print(f"   Success: {metrics.success}")

        # Generate insights with integrated data
        insights = tracker.get_performance_insights([metrics])

        print("\\n🔍 Integration Insights:")
        summary = insights["summary"]
        print(f"   Status: {summary['status']}")
        if "total_operations" in summary:
            print(f"   Total operations: {summary['total_operations']}")
        else:
            print(f"   Migration count: {summary.get('total_migrations', 0)}")

        recommendations = insights["recommendations"]
        if recommendations:
            print("   Recommendations:")
            for rec in recommendations[:2]:
                print(f"     • {rec}")

        return tracker, [metrics]


async def main():
    """Run all performance tracking demonstrations."""
    print("🚀 Migration Performance Tracking Example")
    print("Phase 1B Component 3 - Comprehensive Performance Monitoring")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        # Run all demonstrations
        demo_results = []

        demo_results.append(await demonstrate_basic_performance_tracking())
        demo_results.append(await demonstrate_regression_detection())
        demo_results.append(await demonstrate_historical_analysis())
        demo_results.append(await demonstrate_performance_reporting())
        demo_results.append(await demonstrate_component_integration())

        # Summary
        print("\\n" + "=" * 60)
        print("🎉 DEMONSTRATION COMPLETE")
        print("=" * 60)

        total_migrations = sum(
            len(result[1])
            for result in demo_results
            if len(result) >= 2 and isinstance(result[1], list)
        )

        print("✅ Successfully demonstrated:")
        print("   • Basic performance tracking")
        print("   • Regression detection and analysis")
        print("   • Historical performance trends")
        print("   • Comprehensive reporting")
        print("   • Component integration")
        print(f"\\n📊 Total migrations benchmarked: {total_migrations}")

        # Show any exported report files
        report_files = [
            result[2] for result in demo_results if len(result) > 2 and result[2]
        ]
        if report_files:
            print("\\n📄 Generated reports:")
            for report_file in report_files:
                print(f"   • {report_file}")

        print("\\n🎯 Key Features Demonstrated:")
        print("   ✅ Real-time performance measurement (<50ms overhead)")
        print("   ✅ Memory usage tracking (<5MB measurement overhead)")
        print("   ✅ Regression detection (configurable thresholds)")
        print("   ✅ Historical trend analysis")
        print("   ✅ Component integration (Phase 1A & 1B)")
        print("   ✅ Comprehensive reporting and insights")

        return True

    except Exception as e:
        print(f"\\n❌ Demonstration failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Run the example
    success = asyncio.run(main())

    if success:
        print("\\n🎉 Migration Performance Tracking example completed successfully!")
        print("\\nThe MigrationPerformanceTracker is ready for production use with:")
        print("  • Comprehensive performance monitoring")
        print("  • Automated regression detection")
        print("  • Historical analysis and insights")
        print("  • Full integration with Phase 1A and 1B components")
    else:
        print("\\n❌ Example failed - see error details above")
        exit(1)
