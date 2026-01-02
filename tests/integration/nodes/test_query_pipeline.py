"""Unit tests for query pipeline node."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from kailash.nodes.data.query_pipeline import (
    PipelineBatch,
    PipelinedQuery,
    PipelineResult,
    PipelineStrategy,
    QueryPipelineNode,
    QueryPipelineOptimizer,
)


class TestQueryPipelineNode:
    """Test query pipeline functionality."""

    @pytest.fixture
    def mock_runtime(self):
        """Create mock runtime with resource registry."""
        runtime = Mock()
        runtime.resource_registry = Mock()
        return runtime

    @pytest.fixture
    def mock_pool(self):
        """Create mock connection pool."""
        pool = AsyncMock()

        # Mock connection
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value={"data": [], "success": True})

        # Mock acquire to return context manager
        class MockAcquireContext:
            async def __aenter__(self):
                return mock_conn

            async def __aexit__(self, *args):
                return None

        # Make acquire a regular function that returns the context manager
        pool.acquire = Mock(return_value=MockAcquireContext())

        return pool

    @pytest.fixture
    def pipeline_node(self, mock_runtime, mock_pool):
        """Create test pipeline node."""
        node = QueryPipelineNode(
            name="test_pipeline",
            connection_pool="test_pool",
            batch_size=10,
            flush_interval=0,  # Disable auto-flush for tests
            strategy="best_effort",
        )

        # Set runtime and mock pool
        node.runtime = mock_runtime
        mock_runtime.resource_registry.get.return_value = mock_pool

        return node

    def test_get_parameters(self):
        """Test parameter definitions."""
        node = QueryPipelineNode(name="test")
        params = node.get_parameters()

        assert "connection_pool" in params
        assert "batch_size" in params
        assert "flush_interval" in params
        assert "strategy" in params
        assert "enable_optimization" in params
        assert "queries" in params

    @pytest.mark.asyncio
    async def test_add_single_query(self, pipeline_node):
        """Test adding single query to pipeline."""
        query_id = await pipeline_node.add_query(
            "SELECT * FROM users", [1, 2, 3], "callback_123"
        )

        assert query_id.startswith("pq_")
        assert len(pipeline_node._queue) == 1

        query = pipeline_node._queue[0]
        assert query.query == "SELECT * FROM users"
        assert query.parameters == [1, 2, 3]
        assert query.callback_id == "callback_123"

    @pytest.mark.asyncio
    async def test_auto_flush_on_batch_size(self, pipeline_node, mock_pool):
        """Test automatic flush when batch size reached."""
        pipeline_node.batch_size = 3

        # Add queries up to batch size
        for i in range(3):
            await pipeline_node.add_query(f"SELECT {i}", [i])

        # Wait for flush
        await asyncio.sleep(0.1)

        # Queue should be empty after flush
        assert len(pipeline_node._queue) == 0
        assert pipeline_node._total_queries == 3

    @pytest.mark.asyncio
    async def test_manual_flush(self, pipeline_node, mock_pool):
        """Test manual flush operation."""
        # Add queries
        await pipeline_node.add_query("SELECT 1")
        await pipeline_node.add_query("SELECT 2")

        # Manual flush
        results = await pipeline_node.flush()

        assert len(results) == 2
        assert all(isinstance(r, PipelineResult) for r in results)
        assert all(r.success for r in results)
        assert len(pipeline_node._queue) == 0

    @pytest.mark.asyncio
    async def test_execute_action(self, pipeline_node, mock_pool):
        """Test execute action with multiple queries."""
        input_data = {
            "queries": [
                {"query": "SELECT * FROM users", "parameters": []},
                {"query": "INSERT INTO logs VALUES (?)", "parameters": ["test"]},
            ]
        }

        result = await pipeline_node.execute(input_data)

        assert result["success"]
        assert result["count"] == 2
        assert len(result["results"]) == 2

    @pytest.mark.asyncio
    async def test_sequential_strategy(self, pipeline_node, mock_pool):
        """Test sequential execution strategy."""
        pipeline_node.strategy = PipelineStrategy.SEQUENTIAL

        # Make second query fail
        # Get the mock connection from the context manager
        mock_conn = await mock_pool.acquire().__aenter__()
        mock_conn.execute.side_effect = [
            {"data": [], "success": True},
            Exception("Query failed"),
            {"data": [], "success": True},  # This shouldn't execute
        ]

        # Add queries
        await pipeline_node.add_query("SELECT 1")
        await pipeline_node.add_query("SELECT 2")  # Will fail
        await pipeline_node.add_query("SELECT 3")  # Won't execute

        results = await pipeline_node.flush()

        assert len(results) == 3
        assert results[0].success
        assert not results[1].success
        assert not results[2].success  # Not executed due to sequential strategy
        assert "Not executed due to previous failure" in str(results[2].error)

    @pytest.mark.asyncio
    async def test_parallel_strategy(self, pipeline_node, mock_pool):
        """Test parallel execution strategy."""
        pipeline_node.strategy = PipelineStrategy.PARALLEL

        # Add SELECT queries (can be parallelized)
        for i in range(5):
            await pipeline_node.add_query(f"SELECT {i}")

        results = await pipeline_node.flush()

        assert len(results) == 5
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_transactional_strategy(self, pipeline_node, mock_pool):
        """Test transactional execution strategy."""
        pipeline_node.strategy = PipelineStrategy.TRANSACTIONAL

        # Get the mock connection from the context manager
        mock_conn = await mock_pool.acquire().__aenter__()

        # Make third query fail
        mock_conn.execute.side_effect = [
            None,  # BEGIN
            {"data": [], "success": True},  # Query 1
            {"data": [], "success": True},  # Query 2
            Exception("Transaction failed"),  # Query 3 fails
        ]

        # Add queries
        await pipeline_node.add_query("INSERT 1")
        await pipeline_node.add_query("INSERT 2")
        await pipeline_node.add_query("INSERT 3")

        results = await pipeline_node.flush()

        # All should fail in transaction
        assert len(results) == 3
        assert all(not r.success for r in results)
        assert all(str(r.error) == "Transaction failed" for r in results)

    @pytest.mark.asyncio
    async def test_best_effort_strategy(self, pipeline_node, mock_pool):
        """Test best effort execution strategy."""
        pipeline_node.strategy = PipelineStrategy.BEST_EFFORT

        # Get the mock connection from the context manager
        mock_conn = await mock_pool.acquire().__aenter__()

        # Make some queries fail
        mock_conn.execute.side_effect = [
            {"data": [], "success": True},
            Exception("Query 2 failed"),
            {"data": [], "success": True},
            Exception("Query 4 failed"),
            {"data": [], "success": True},
        ]

        # Add queries
        for i in range(5):
            await pipeline_node.add_query(f"SELECT {i}")

        results = await pipeline_node.flush()

        assert len(results) == 5
        assert results[0].success
        assert not results[1].success
        assert results[2].success
        assert not results[3].success
        assert results[4].success

    @pytest.mark.asyncio
    async def test_get_status(self, pipeline_node):
        """Test pipeline status reporting."""
        # Add some queries
        await pipeline_node.add_query("SELECT 1")
        await pipeline_node.add_query("SELECT 2")

        status = pipeline_node.get_status()

        assert status["queued_queries"] == 2
        assert status["total_queries"] == 2
        assert status["batch_size"] == 10
        assert status["flush_interval"] == 0  # Disabled for tests
        assert status["strategy"] == "best_effort"

    @pytest.mark.asyncio
    async def test_query_result_tracking(self, pipeline_node, mock_pool):
        """Test query result retrieval."""
        # Add and flush query
        query_id = await pipeline_node.add_query("SELECT * FROM test")
        results = await pipeline_node.flush()

        # Get result by ID
        result = pipeline_node.get_result(query_id)
        assert result is not None
        assert result.query_id == query_id
        assert result.success


class TestQueryPipelineOptimizer:
    """Test query optimization logic."""

    def test_optimize_batch_read_write_separation(self):
        """Test read/write query separation."""
        queries = [
            PipelinedQuery("q1", "INSERT INTO users VALUES (1)", None),
            PipelinedQuery("q2", "SELECT * FROM users", None),
            PipelinedQuery("q3", "UPDATE users SET active = 1", None),
            PipelinedQuery("q4", "SELECT COUNT(*) FROM orders", None),
            PipelinedQuery("q5", "DELETE FROM logs WHERE old = 1", None),
        ]

        optimized = QueryPipelineOptimizer.optimize_batch(queries)

        # SELECTs should come first
        assert optimized[0].query.startswith("SELECT")
        assert optimized[1].query.startswith("SELECT")
        # Then writes
        assert optimized[2].query.startswith("INSERT")
        assert optimized[3].query.startswith("UPDATE")
        assert optimized[4].query.startswith("DELETE")

    def test_can_merge_queries(self):
        """Test query merge detection."""
        q1 = PipelinedQuery("q1", "INSERT INTO users (name) VALUES (?)", ["Alice"])
        q2 = PipelinedQuery("q2", "INSERT INTO users (name) VALUES (?)", ["Bob"])
        q3 = PipelinedQuery("q3", "INSERT INTO orders (id) VALUES (?)", [1])
        q4 = PipelinedQuery("q4", "SELECT * FROM users", None)

        # Same table INSERTs can merge
        assert QueryPipelineOptimizer.can_merge_queries(q1, q2)

        # Different table INSERTs cannot merge
        assert not QueryPipelineOptimizer.can_merge_queries(q1, q3)

        # Non-INSERTs cannot merge
        assert not QueryPipelineOptimizer.can_merge_queries(q1, q4)


class TestPipelineBatch:
    """Test pipeline batch functionality."""

    def test_batch_creation(self):
        """Test batch creation and properties."""
        queries = [
            PipelinedQuery("q1", "SELECT 1", None),
            PipelinedQuery("q2", "SELECT 2", None),
        ]

        batch = PipelineBatch(
            id="batch_1", queries=queries, strategy=PipelineStrategy.PARALLEL
        )

        assert batch.id == "batch_1"
        assert batch.size() == 2
        assert batch.strategy == PipelineStrategy.PARALLEL

    def test_can_parallelize(self):
        """Test parallelization detection."""
        # All SELECTs can parallelize
        select_queries = [
            PipelinedQuery("q1", "SELECT * FROM users", None),
            PipelinedQuery("q2", "SELECT * FROM orders", None),
        ]
        batch1 = PipelineBatch("b1", select_queries, PipelineStrategy.PARALLEL)
        assert batch1.can_parallelize()

        # Mixed queries cannot parallelize
        mixed_queries = [
            PipelinedQuery("q1", "SELECT * FROM users", None),
            PipelinedQuery("q2", "INSERT INTO logs VALUES (1)", None),
        ]
        batch2 = PipelineBatch("b2", mixed_queries, PipelineStrategy.PARALLEL)
        assert not batch2.can_parallelize()

        # Non-parallel strategy cannot parallelize
        batch3 = PipelineBatch("b3", select_queries, PipelineStrategy.SEQUENTIAL)
        assert not batch3.can_parallelize()
