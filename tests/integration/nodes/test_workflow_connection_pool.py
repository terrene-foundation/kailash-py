"""Unit tests for WorkflowConnectionPool."""

import asyncio
import time
from unittest.mock import AsyncMock, Mock, patch

import pytest
from kailash.core.actors import ConnectionState
from kailash.nodes.data.workflow_connection_pool import (
    ConnectionPoolMetrics,
    WorkflowConnectionPool,
    WorkflowPatternAnalyzer,
)
from kailash.sdk_exceptions import NodeExecutionError


@pytest.mark.critical
class TestConnectionPoolMetrics:
    """Test connection pool metrics collection."""

    def test_metrics_initialization(self):
        """Test metrics are initialized correctly."""
        metrics = ConnectionPoolMetrics("test_pool")

        assert metrics.pool_name == "test_pool"
        assert metrics.connections_created == 0
        assert metrics.connections_recycled == 0
        assert metrics.queries_executed == 0
        assert metrics.acquisition_wait_times == []

    def test_record_acquisition_time(self):
        """Test acquisition time recording."""
        metrics = ConnectionPoolMetrics("test_pool")

        # Record some times
        metrics.record_acquisition_time(0.1)
        metrics.record_acquisition_time(0.2)
        metrics.record_acquisition_time(0.15)

        assert len(metrics.acquisition_wait_times) == 3
        assert metrics.acquisition_wait_times == [0.1, 0.2, 0.15]

    def test_acquisition_time_limit(self):
        """Test that acquisition times are limited to 1000 entries."""
        metrics = ConnectionPoolMetrics("test_pool")

        # Record more than 1000 times
        for i in range(1100):
            metrics.record_acquisition_time(i / 1000.0)

        assert len(metrics.acquisition_wait_times) == 1000
        # Should keep the last 1000
        assert metrics.acquisition_wait_times[0] == 0.1
        assert metrics.acquisition_wait_times[-1] == 1.099

    def test_get_stats(self):
        """Test comprehensive stats calculation."""
        metrics = ConnectionPoolMetrics("test_pool")

        # Set up some data
        metrics.connections_created = 10
        metrics.connections_recycled = 2
        metrics.connections_failed = 1
        metrics.queries_executed = 100
        metrics.query_errors = 5

        metrics.record_acquisition_time(0.01)
        metrics.record_acquisition_time(0.02)
        metrics.record_acquisition_time(0.03)

        metrics.health_check_results = [True, True, False, True]

        stats = metrics.get_stats()

        assert stats["pool_name"] == "test_pool"
        assert stats["connections"]["created"] == 10
        assert stats["connections"]["recycled"] == 2
        assert stats["queries"]["executed"] == 100
        assert stats["queries"]["error_rate"] == 0.05
        assert stats["performance"]["avg_acquisition_time_ms"] == 20.0
        assert stats["health"]["success_rate"] == 0.75


@pytest.mark.critical
class TestWorkflowPatternAnalyzer:
    """Test workflow pattern analysis."""

    def test_record_workflow_start(self):
        """Test recording workflow start."""
        analyzer = WorkflowPatternAnalyzer()

        analyzer.record_workflow_start("wf_123", "data_processing")

        assert "wf_123" in analyzer.workflow_patterns
        pattern = analyzer.workflow_patterns["wf_123"]
        assert pattern["type"] == "data_processing"
        assert pattern["connections_used"] == 0

    def test_record_connection_usage(self):
        """Test recording connection usage."""
        analyzer = WorkflowPatternAnalyzer()

        analyzer.record_workflow_start("wf_123", "data_processing")
        analyzer.record_connection_usage("wf_123", 3)
        analyzer.record_connection_usage("wf_123", 5)
        analyzer.record_connection_usage("wf_123", 2)

        pattern = analyzer.workflow_patterns["wf_123"]
        assert pattern["connections_used"] == 5  # Maximum recorded
        assert analyzer.connection_usage["wf_123"] == [3, 5, 2]

    def test_get_expected_connections_no_history(self):
        """Test getting expected connections with no history."""
        analyzer = WorkflowPatternAnalyzer()

        expected = analyzer.get_expected_connections("new_workflow_type")
        assert expected == 2  # Default

    def test_get_expected_connections_with_history(self):
        """Test getting expected connections based on history."""
        analyzer = WorkflowPatternAnalyzer()

        # Create history
        for i in range(10):
            wf_id = f"wf_{i}"
            analyzer.record_workflow_start(wf_id, "data_processing")
            # Simulate usage pattern
            analyzer.workflow_patterns[wf_id]["connections_used"] = i + 1

        # Should return 90th percentile
        expected = analyzer.get_expected_connections("data_processing")
        # 90th percentile of [1,2,3,4,5,6,7,8,9,10] at index 9 (0-based) is 10
        assert expected == 10


@pytest.mark.critical
@pytest.mark.asyncio
class TestWorkflowConnectionPool:
    """Test WorkflowConnectionPool node."""

    @pytest.fixture
    def pool_config(self):
        """Basic pool configuration."""
        return {
            "name": "test_pool",
            "database_type": "postgresql",
            "host": "localhost",
            "database": "test_db",
            "user": "test_user",
            "password": "test_pass",
            "min_connections": 2,
            "max_connections": 5,
        }

    async def test_pool_initialization(self, pool_config):
        """Test pool initialization."""
        pool = WorkflowConnectionPool(**pool_config)

        assert pool.min_connections == 2
        assert pool.max_connections == 5
        assert pool.db_config["type"] == "postgresql"
        assert not pool._initialized

    async def test_initialize_operation(self, pool_config):
        """Test initialize operation."""
        pool = WorkflowConnectionPool(**pool_config)

        # Mock supervisor
        pool.supervisor.start = AsyncMock()
        pool._ensure_min_connections = AsyncMock()

        result = await pool.process({"operation": "initialize"})

        assert result["status"] == "initialized"
        assert result["min_connections"] == 2
        assert result["max_connections"] == 5
        assert pool._initialized

        # Should not re-initialize
        result2 = await pool.process({"operation": "initialize"})
        assert result2["status"] == "already_initialized"

    async def test_acquire_connection(self, pool_config):
        """Test acquiring a connection."""
        pool = WorkflowConnectionPool(**pool_config)

        # Mock connection
        mock_conn = Mock()
        mock_conn.id = "conn_123"
        mock_conn.health_score = 85.0

        # Pre-populate available connections
        await pool.available_connections.put(mock_conn)
        pool.all_connections["conn_123"] = mock_conn
        pool._initialized = True

        result = await pool.process({"operation": "acquire"})

        assert result["connection_id"] == "conn_123"
        assert result["health_score"] == 85.0
        assert "acquisition_time_ms" in result
        assert "conn_123" in pool.active_connections
        assert pool.available_connections.qsize() == 0

    async def test_acquire_creates_new_connection(self, pool_config):
        """Test acquiring creates new connection when needed."""
        pool = WorkflowConnectionPool(**pool_config)
        pool._initialized = True

        # Mock connection creation
        mock_conn = Mock()
        mock_conn.id = "conn_new"
        mock_conn.health_score = 100.0
        pool._create_connection = AsyncMock(return_value=mock_conn)

        result = await pool.process({"operation": "acquire"})

        assert result["connection_id"] == "conn_new"
        pool._create_connection.assert_called_once()

    async def test_acquire_waits_at_max_connections(self, pool_config):
        """Test acquire waits when at max connections."""
        pool = WorkflowConnectionPool(**pool_config)
        pool._initialized = True
        pool.max_connections = 1

        # Fill pool to max
        mock_conn = Mock()
        mock_conn.id = "conn_1"
        pool.all_connections["conn_1"] = mock_conn
        pool.active_connections["conn_1"] = mock_conn

        # Start acquire that should wait
        acquire_task = asyncio.create_task(pool.process({"operation": "acquire"}))

        # Give it time to start waiting
        await asyncio.sleep(0.1)

        # Release connection
        await pool.available_connections.put(mock_conn)

        # Now acquire should complete
        result = await acquire_task
        assert result["connection_id"] == "conn_1"

    async def test_release_connection(self, pool_config):
        """Test releasing a connection."""
        pool = WorkflowConnectionPool(**pool_config)
        pool._initialized = True

        # Set up active connection
        mock_conn = Mock()
        mock_conn.id = "conn_123"
        mock_conn.health_score = 80.0
        pool.active_connections["conn_123"] = mock_conn

        result = await pool.process(
            {"operation": "release", "connection_id": "conn_123"}
        )

        assert result["status"] == "released"
        assert "conn_123" not in pool.active_connections
        assert pool.available_connections.qsize() == 1

    async def test_release_recycles_unhealthy(self, pool_config):
        """Test releasing recycles unhealthy connections."""
        pool = WorkflowConnectionPool(**pool_config)
        pool._initialized = True
        pool.health_threshold = 50

        # Set up unhealthy connection
        mock_conn = Mock()
        mock_conn.id = "conn_123"
        mock_conn.health_score = 30.0
        pool.active_connections["conn_123"] = mock_conn
        pool._recycle_connection = AsyncMock()

        result = await pool.process(
            {"operation": "release", "connection_id": "conn_123"}
        )

        assert result["status"] == "recycled"
        pool._recycle_connection.assert_called_once_with(mock_conn)

    async def test_execute_query(self, pool_config):
        """Test executing a query."""
        pool = WorkflowConnectionPool(**pool_config)
        pool._initialized = True

        # Mock connection and result
        mock_result = Mock()
        mock_result.success = True
        mock_result.data = [{"id": 1, "name": "test"}]
        mock_result.error = None
        mock_result.execution_time = 0.05

        mock_conn = Mock()
        mock_conn.id = "conn_123"
        mock_conn.execute = AsyncMock(return_value=mock_result)
        pool.active_connections["conn_123"] = mock_conn

        result = await pool.process(
            {
                "operation": "execute",
                "connection_id": "conn_123",
                "query": "SELECT * FROM users",
                "params": None,
                "fetch_mode": "all",
            }
        )

        assert result["success"] is True
        assert result["data"] == [{"id": 1, "name": "test"}]
        assert result["execution_time_ms"] == 50.0
        assert pool.metrics.queries_executed == 1
        assert pool.metrics.query_errors == 0

    async def test_execute_query_error(self, pool_config):
        """Test executing a query that fails."""
        pool = WorkflowConnectionPool(**pool_config)
        pool._initialized = True

        # Mock connection and error result
        mock_result = Mock()
        mock_result.success = False
        mock_result.data = None
        mock_result.error = "Table not found"
        mock_result.execution_time = 0.01

        mock_conn = Mock()
        mock_conn.id = "conn_123"
        mock_conn.execute = AsyncMock(return_value=mock_result)
        pool.active_connections["conn_123"] = mock_conn

        result = await pool.process(
            {
                "operation": "execute",
                "connection_id": "conn_123",
                "query": "SELECT * FROM nonexistent",
            }
        )

        assert result["success"] is False
        assert result["error"] == "Table not found"
        assert pool.metrics.queries_executed == 1
        assert pool.metrics.query_errors == 1

    async def test_get_stats(self, pool_config):
        """Test getting pool statistics."""
        pool = WorkflowConnectionPool(**pool_config)
        pool._initialized = True

        # Set up some connections
        for i in range(3):
            mock_conn = Mock()
            mock_conn.id = f"conn_{i}"
            mock_conn.health_score = 90.0 - (i * 10)
            pool.all_connections[f"conn_{i}"] = mock_conn
            if i == 0:
                pool.active_connections[f"conn_{i}"] = mock_conn

        # Set up some metrics
        pool.metrics.connections_created = 3
        pool.metrics.queries_executed = 50

        result = await pool.process({"operation": "stats"})

        assert result["current_state"]["total_connections"] == 3
        assert result["current_state"]["active_connections"] == 1
        assert "health_scores" in result["current_state"]
        assert result["connections"]["created"] == 3
        assert result["queries"]["executed"] == 50

    async def test_workflow_integration(self, pool_config):
        """Test workflow lifecycle integration."""
        pool = WorkflowConnectionPool(**pool_config)
        pool._pre_warm_connections = AsyncMock()
        pool._cleanup = AsyncMock()

        # Workflow start
        await pool.on_workflow_start("wf_123", "data_processing")
        assert pool.workflow_id == "wf_123"
        pool._pre_warm_connections.assert_called()

        # Workflow complete
        await pool.on_workflow_complete("wf_123")
        pool._cleanup.assert_called_once()

    async def test_pre_warming(self, pool_config):
        """Test connection pre-warming."""
        pool = WorkflowConnectionPool(**pool_config)
        pool._initialized = True

        # Mock connection creation
        created_conns = []

        async def mock_create():
            conn = Mock()
            conn.id = f"conn_{len(created_conns)}"
            created_conns.append(conn)
            return conn

        pool._create_connection = mock_create

        await pool._pre_warm_connections(3)

        assert len(created_conns) == 3
        assert pool.available_connections.qsize() == 3

    async def test_context_manager(self, pool_config):
        """Test using pool as context manager."""
        pool = WorkflowConnectionPool(**pool_config)
        pool._initialize = AsyncMock()
        pool._cleanup = AsyncMock()

        async with pool as p:
            assert p is pool
            pool._initialize.assert_called_once()

        pool._cleanup.assert_called_once()

    async def test_supervisor_callbacks(self, pool_config):
        """Test supervisor callback handling."""
        pool = WorkflowConnectionPool(**pool_config)

        # Test failure callback
        pool.all_connections["conn_123"] = Mock()
        pool.active_connections["conn_123"] = Mock()

        pool._on_connection_failure("conn_123", Exception("Connection lost"))

        assert "conn_123" not in pool.all_connections
        assert "conn_123" not in pool.active_connections
        assert pool.metrics.connections_failed == 1

        # Test restart callback
        pool._on_connection_restart("conn_456", 2)
        # Should just log, no assertions needed

    async def test_recycle_connection(self, pool_config):
        """Test connection recycling."""
        pool = WorkflowConnectionPool(**pool_config)
        pool._initialized = True

        # Mock connection
        mock_conn = Mock()
        mock_conn.id = "conn_123"
        mock_conn.health_score = 20.0
        mock_conn.recycle = AsyncMock()

        pool.all_connections["conn_123"] = mock_conn
        pool._ensure_min_connections = AsyncMock()

        await pool._recycle_connection(mock_conn)

        assert "conn_123" not in pool.all_connections
        mock_conn.recycle.assert_called_once()
        pool._ensure_min_connections.assert_called_once()
        assert pool.metrics.connections_recycled == 1
