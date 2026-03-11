"""
Performance Benchmarking for DataFlow Bulk Operations.

Benchmarks bulk_create, bulk_update, and bulk_delete operations with:
- Various data sizes (100, 1k, 10k, 100k records)
- Different batch sizes (100, 1000, 5000)
- PostgreSQL database
"""

import asyncio
import time
from typing import Dict, List

import pytest
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
async def setup_benchmark_table(test_suite):
    """Create benchmark table for testing."""
    connection_string = test_suite.config.url

    # Drop and create table
    drop_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query="DROP TABLE IF EXISTS benchmark_records CASCADE",
        validate_queries=False,
    )
    await drop_node.async_run()
    await drop_node.cleanup()

    setup_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query="""
        CREATE TABLE benchmark_records (
            id SERIAL PRIMARY KEY,
            category VARCHAR(50) NOT NULL,
            value INTEGER NOT NULL,
            data JSONB,
            active BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        validate_queries=False,
    )
    await setup_node.async_run()
    await setup_node.cleanup()

    yield connection_string

    # Cleanup
    cleanup_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query="DROP TABLE IF EXISTS benchmark_records CASCADE",
        validate_queries=False,
    )
    await cleanup_node.async_run()
    await cleanup_node.cleanup()


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format."""
    if seconds < 1:
        return f"{seconds * 1000:.2f}ms"
    return f"{seconds:.2f}s"


def calculate_throughput(records: int, duration: float) -> str:
    """Calculate throughput in records/second."""
    if duration == 0:
        return "N/A"
    throughput = records / duration
    if throughput >= 1000:
        return f"{throughput / 1000:.2f}k records/s"
    return f"{throughput:.2f} records/s"


class TestBulkCreatePerformance:
    """Benchmark bulk_create performance."""

    @pytest.mark.asyncio
    @pytest.mark.benchmark
    async def test_bulk_create_100_records(self, setup_benchmark_table):
        """Benchmark bulk_create with 100 records."""
        await self._benchmark_bulk_create(setup_benchmark_table, 100, 1000)

    @pytest.mark.asyncio
    @pytest.mark.benchmark
    async def test_bulk_create_1k_records(self, setup_benchmark_table):
        """Benchmark bulk_create with 1,000 records."""
        await self._benchmark_bulk_create(setup_benchmark_table, 1000, 1000)

    @pytest.mark.asyncio
    @pytest.mark.benchmark
    async def test_bulk_create_10k_records(self, setup_benchmark_table):
        """Benchmark bulk_create with 10,000 records."""
        await self._benchmark_bulk_create(setup_benchmark_table, 10000, 1000)

    @pytest.mark.asyncio
    @pytest.mark.benchmark
    async def test_bulk_create_batch_sizes(self, setup_benchmark_table):
        """Compare different batch sizes for bulk_create."""
        record_count = 5000
        batch_sizes = [100, 500, 1000, 2000, 5000]

        print(f"\n\nBatch Size Comparison for {record_count:,} records:")
        print("=" * 80)

        results = []
        for batch_size in batch_sizes:
            duration = await self._benchmark_bulk_create(
                setup_benchmark_table, record_count, batch_size, cleanup=True
            )
            results.append((batch_size, duration))

        # Print comparison
        print(f"\n{'Batch Size':<15} {'Duration':<15} {'Throughput':<20} {'Batches'}")
        print("-" * 80)
        for batch_size, duration in results:
            batches = (record_count + batch_size - 1) // batch_size
            print(
                f"{batch_size:<15,} {format_duration(duration):<15} "
                f"{calculate_throughput(record_count, duration):<20} {batches}"
            )

    async def _benchmark_bulk_create(
        self, connection_string, record_count, batch_size, cleanup=False
    ):
        """Helper to benchmark bulk_create operation."""
        df = DataFlow(connection_string, auto_migrate=False)

        @df.model
        class BenchmarkRecord:
            category: str
            value: int
            data: dict
            active: bool

        # Generate test data
        data = [
            {
                "category": f"cat_{i % 10}",
                "value": i,
                "data": {"index": i, "extra": f"data_{i}"},
                "active": i % 2 == 0,
            }
            for i in range(record_count)
        ]

        workflow = WorkflowBuilder()
        workflow.add_node(
            "BenchmarkRecordBulkCreateNode",
            "bulk_create",
            {
                "data": data,
                "batch_size": batch_size,
            },
        )

        runtime = LocalRuntime()

        # Benchmark execution
        start_time = time.time()
        results, run_id = runtime.execute(workflow.build())
        duration = time.time() - start_time

        create_result = results.get("bulk_create")
        assert create_result.get(
            "success"
        ), f"Bulk create failed: {create_result.get('error')}"
        assert create_result.get("inserted") == record_count

        print(f"\n\nbulk_create({record_count:,} records, batch_size={batch_size:,}):")
        print(f"  Duration: {format_duration(duration)}")
        print(f"  Throughput: {calculate_throughput(record_count, duration)}")
        print(f"  Batches: {create_result.get('batches', 0)}")

        # Cleanup if requested
        if cleanup:
            cleanup_node = AsyncSQLDatabaseNode(
                connection_string=connection_string,
                database_type="postgresql",
                query="DELETE FROM benchmark_records",
                validate_queries=False,
            )
            await cleanup_node.async_run()
            await cleanup_node.cleanup()

        return duration


class TestBulkUpdatePerformance:
    """Benchmark bulk_update performance."""

    @pytest.mark.asyncio
    @pytest.mark.benchmark
    async def test_bulk_update_filter_based_1k_records(self, setup_benchmark_table):
        """Benchmark filter-based bulk_update with 1,000 records."""
        await self._benchmark_bulk_update_filter(setup_benchmark_table, 1000)

    @pytest.mark.asyncio
    @pytest.mark.benchmark
    async def test_bulk_update_filter_based_10k_records(self, setup_benchmark_table):
        """Benchmark filter-based bulk_update with 10,000 records."""
        await self._benchmark_bulk_update_filter(setup_benchmark_table, 10000)

    @pytest.mark.asyncio
    @pytest.mark.benchmark
    async def test_bulk_update_data_based_1k_records(self, setup_benchmark_table):
        """Benchmark data-based bulk_update with 1,000 records."""
        await self._benchmark_bulk_update_data(setup_benchmark_table, 1000)

    async def _benchmark_bulk_update_filter(self, connection_string, record_count):
        """Helper to benchmark filter-based bulk_update."""
        # First create records
        insert_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query=f"""
            INSERT INTO benchmark_records (category, value, data, active)
            SELECT
                'cat_' || (i % 10),
                i,
                '{{"index": ' || i || '}}',
                (i % 2 = 0)
            FROM generate_series(1, {record_count}) i
            """,
            validate_queries=False,
        )
        await insert_node.async_run()
        await insert_node.cleanup()

        df = DataFlow(connection_string, auto_migrate=False)

        @df.model
        class BenchmarkRecord:
            category: str
            value: int
            data: dict
            active: bool

        # Update all cat_0 records
        workflow = WorkflowBuilder()
        workflow.add_node(
            "BenchmarkRecordBulkUpdateNode",
            "bulk_update",
            {
                "filter": {"category": "cat_0"},
                "update": {"active": False, "value": 999},
            },
        )

        runtime = LocalRuntime()

        start_time = time.time()
        results, run_id = runtime.execute(workflow.build())
        duration = time.time() - start_time

        update_result = results.get("bulk_update")
        assert update_result.get("success")
        updated_count = update_result.get("processed", 0)

        print(
            f"\n\nbulk_update filter-based ({record_count:,} records total, {updated_count:,} updated):"
        )
        print(f"  Duration: {format_duration(duration)}")
        print(f"  Throughput: {calculate_throughput(updated_count, duration)}")

        return duration

    async def _benchmark_bulk_update_data(self, connection_string, record_count):
        """Helper to benchmark data-based bulk_update."""
        # First create records
        insert_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query=f"""
            INSERT INTO benchmark_records (category, value, data, active)
            SELECT
                'cat_' || (i % 10),
                i,
                '{{"index": ' || i || '}}',
                (i % 2 = 0)
            FROM generate_series(1, {record_count}) i
            """,
            validate_queries=False,
        )
        await insert_node.async_run()
        await insert_node.cleanup()

        df = DataFlow(connection_string, auto_migrate=False)

        @df.model
        class BenchmarkRecord:
            category: str
            value: int
            data: dict
            active: bool

        # Prepare update data for first 100 records
        update_data = [
            {"id": i, "value": i * 10, "active": False}
            for i in range(1, min(101, record_count + 1))
        ]

        workflow = WorkflowBuilder()
        workflow.add_node(
            "BenchmarkRecordBulkUpdateNode",
            "bulk_update",
            {
                "data": update_data,
            },
        )

        runtime = LocalRuntime()

        start_time = time.time()
        results, run_id = runtime.execute(workflow.build())
        duration = time.time() - start_time

        update_result = results.get("bulk_update")
        assert update_result.get("success")
        updated_count = update_result.get("processed", 0)

        print(
            f"\n\nbulk_update data-based ({len(update_data):,} records updated by ID):"
        )
        print(f"  Duration: {format_duration(duration)}")
        print(f"  Throughput: {calculate_throughput(updated_count, duration)}")

        return duration


class TestBulkDeletePerformance:
    """Benchmark bulk_delete performance."""

    @pytest.mark.asyncio
    @pytest.mark.benchmark
    async def test_bulk_delete_filter_based_1k_records(self, setup_benchmark_table):
        """Benchmark filter-based bulk_delete with 1,000 records."""
        await self._benchmark_bulk_delete_filter(setup_benchmark_table, 1000)

    @pytest.mark.asyncio
    @pytest.mark.benchmark
    async def test_bulk_delete_filter_based_10k_records(self, setup_benchmark_table):
        """Benchmark filter-based bulk_delete with 10,000 records."""
        await self._benchmark_bulk_delete_filter(setup_benchmark_table, 10000)

    async def _benchmark_bulk_delete_filter(self, connection_string, record_count):
        """Helper to benchmark filter-based bulk_delete."""
        # First create records
        insert_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query=f"""
            INSERT INTO benchmark_records (category, value, data, active)
            SELECT
                'cat_' || (i % 10),
                i,
                '{{"index": ' || i || '}}',
                (i % 2 = 0)
            FROM generate_series(1, {record_count}) i
            """,
            validate_queries=False,
        )
        await insert_node.async_run()
        await insert_node.cleanup()

        df = DataFlow(connection_string, auto_migrate=False)

        @df.model
        class BenchmarkRecord:
            category: str
            value: int
            data: dict
            active: bool

        # Delete all cat_0 records
        workflow = WorkflowBuilder()
        workflow.add_node(
            "BenchmarkRecordBulkDeleteNode",
            "bulk_delete",
            {
                "filter": {"category": "cat_0"},
                "confirmed": True,
                "safe_mode": False,
            },
        )

        runtime = LocalRuntime()

        start_time = time.time()
        results, run_id = runtime.execute(workflow.build())
        duration = time.time() - start_time

        delete_result = results.get("bulk_delete")
        assert delete_result.get("success")
        deleted_count = delete_result.get("processed", 0)

        print(
            f"\n\nbulk_delete filter-based ({record_count:,} records total, {deleted_count:,} deleted):"
        )
        print(f"  Duration: {format_duration(duration)}")
        print(f"  Throughput: {calculate_throughput(deleted_count, duration)}")

        return duration
