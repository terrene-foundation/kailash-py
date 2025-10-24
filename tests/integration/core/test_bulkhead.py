"""Unit tests for bulkhead isolation pattern.

Tier 1 tests - Fast isolated testing with mocks, no external dependencies.
All tests must complete in <1 second with no sleep/delays.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, Mock, patch

import pytest
from src.kailash.core.resilience.bulkhead import (
    BulkheadManager,
    BulkheadPartition,
    BulkheadRejectionError,
    PartitionConfig,
    PartitionMetrics,
    PartitionType,
    ResourceType,
    execute_with_bulkhead,
    get_bulkhead_manager,
)


class TestPartitionConfig:
    """Test partition configuration."""

    def test_default_config(self):
        """Test default partition configuration."""
        config = PartitionConfig(name="test", partition_type=PartitionType.IO_BOUND)

        assert config.name == "test"
        assert config.partition_type == PartitionType.IO_BOUND
        assert config.max_concurrent_operations == 10
        assert config.timeout == 30
        assert config.priority == 1
        assert config.queue_size == 100
        assert config.circuit_breaker_enabled
        assert config.metrics_enabled

    def test_custom_config(self):
        """Test custom partition configuration."""
        config = PartitionConfig(
            name="custom",
            partition_type=PartitionType.CPU_BOUND,
            max_concurrent_operations=5,
            max_threads=2,
            timeout=60,
            priority=10,
            queue_size=50,
            circuit_breaker_enabled=False,
        )

        assert config.max_concurrent_operations == 5
        assert config.max_threads == 2
        assert config.timeout == 60
        assert config.priority == 10
        assert config.queue_size == 50
        assert not config.circuit_breaker_enabled


class TestPartitionMetrics:
    """Test partition metrics."""

    def test_default_metrics(self):
        """Test default metrics initialization."""
        metrics = PartitionMetrics()

        assert metrics.total_operations == 0
        assert metrics.successful_operations == 0
        assert metrics.failed_operations == 0
        assert metrics.rejected_operations == 0
        assert metrics.avg_execution_time == 0.0
        assert metrics.max_execution_time == 0.0
        assert metrics.created_at is not None


class TestBulkheadPartition:
    """Test bulkhead partition functionality."""

    @pytest.fixture
    def io_partition_config(self):
        """Create I/O bound partition config."""
        return PartitionConfig(
            name="test_io",
            partition_type=PartitionType.IO_BOUND,
            max_concurrent_operations=2,
            timeout=5,
            circuit_breaker_enabled=False,  # Disable for unit tests
        )

    @pytest.fixture
    def cpu_partition_config(self):
        """Create CPU bound partition config."""
        return PartitionConfig(
            name="test_cpu",
            partition_type=PartitionType.CPU_BOUND,
            max_concurrent_operations=1,
            max_threads=2,
            timeout=5,
            circuit_breaker_enabled=False,
        )

    @pytest.fixture
    def io_partition(self, io_partition_config):
        """Create I/O partition for testing."""
        partition = BulkheadPartition(io_partition_config)
        yield partition
        # Clean up any remaining operations
        partition._active_operations.clear()
        partition.metrics = PartitionMetrics()

    @pytest.fixture
    def cpu_partition(self, cpu_partition_config):
        """Create CPU partition for testing."""
        partition = BulkheadPartition(cpu_partition_config)
        yield partition
        # Clean up any remaining operations
        partition._active_operations.clear()
        partition.metrics = PartitionMetrics()
        if hasattr(partition, "_thread_pool") and partition._thread_pool:
            partition._thread_pool.shutdown(wait=False)

    def test_partition_initialization_io(self, io_partition_config):
        """Test I/O partition initialization."""
        partition = BulkheadPartition(io_partition_config)

        assert partition.config == io_partition_config
        assert isinstance(partition.metrics, PartitionMetrics)
        assert partition._semaphore._value == 2
        assert partition._thread_pool is None  # No thread pool for I/O
        assert len(partition._active_operations) == 0

    def test_partition_initialization_cpu(self, cpu_partition_config):
        """Test CPU partition initialization."""
        partition = BulkheadPartition(cpu_partition_config)

        assert partition.config == cpu_partition_config
        assert isinstance(partition._thread_pool, ThreadPoolExecutor)
        assert partition._thread_pool._max_workers == 2

    @pytest.mark.asyncio
    async def test_simple_sync_execution(self, io_partition):
        """Test simple synchronous function execution."""

        def simple_task(x, y):
            return x + y

        result = await io_partition.execute(simple_task, 5, 3)
        assert result == 8

        # Check metrics
        status = io_partition.get_status()
        assert status["metrics"]["total_operations"] == 1
        assert status["metrics"]["successful_operations"] == 1
        assert status["metrics"]["failed_operations"] == 0

    @pytest.mark.asyncio
    async def test_simple_async_execution(self, io_partition):
        """Test simple asynchronous function execution."""

        async def async_task(value):
            return value * 2

        result = await io_partition.execute(async_task, 10)
        assert result == 20

        # Check metrics
        status = io_partition.get_status()
        assert status["metrics"]["successful_operations"] == 1

    @pytest.mark.asyncio
    async def test_function_with_kwargs(self, io_partition):
        """Test function execution with keyword arguments."""

        def task_with_kwargs(a, b, multiplier=1):
            return (a + b) * multiplier

        result = await io_partition.execute(task_with_kwargs, 3, 4, multiplier=2)
        assert result == 14

    @pytest.mark.asyncio
    async def test_execution_error_handling(self, io_partition):
        """Test error handling in execution."""

        def failing_task():
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            await io_partition.execute(failing_task)

        # Check metrics recorded failure
        status = io_partition.get_status()
        assert status["metrics"]["failed_operations"] == 1
        assert status["metrics"]["successful_operations"] == 0

    @pytest.mark.asyncio
    async def test_timeout_handling(self, io_partition):
        """Test timeout handling with mocked delay."""

        async def slow_task():
            # Mock a slow operation without actual delay
            await asyncio.sleep(0)  # Immediate return
            return "completed"

        # Test with very short timeout to trigger timeout in test
        async def mock_wait_for(coro, timeout):
            # Properly await the coroutine and then raise timeout
            await coro
            raise asyncio.TimeoutError()

        with patch("asyncio.wait_for", side_effect=mock_wait_for):
            with pytest.raises(asyncio.TimeoutError):
                await io_partition.execute(slow_task, timeout=0.001)

        # Check metrics recorded failure
        status = io_partition.get_status()
        assert status["metrics"]["failed_operations"] == 1

    def test_rejection_error_creation(self):
        """Test BulkheadRejectionError can be created and raised."""
        error = BulkheadRejectionError("Test rejection message")
        assert str(error) == "Test rejection message"

        # Test it can be raised and caught
        with pytest.raises(BulkheadRejectionError, match="Test rejection message"):
            raise error

    @pytest.mark.asyncio
    async def test_metrics_calculation(self, io_partition):
        """Test metrics calculation without timing dependencies."""

        def task(value):
            return value

        # Execute multiple operations
        await io_partition.execute(task, 1)
        await io_partition.execute(task, 2)
        await io_partition.execute(task, 3)

        status = io_partition.get_status()
        metrics = status["metrics"]

        assert metrics["total_operations"] == 3
        assert metrics["successful_operations"] == 3
        assert metrics["failed_operations"] == 0
        assert metrics["success_rate"] == 1.0
        assert metrics["avg_execution_time"] >= 0

    @pytest.mark.asyncio
    async def test_success_rate_calculation(self, io_partition):
        """Test success rate calculation."""

        def success_task():
            return "success"

        def fail_task():
            raise ValueError("fail")

        # Execute mix of successful and failing operations
        await io_partition.execute(success_task)
        await io_partition.execute(success_task)

        try:
            await io_partition.execute(fail_task)
        except ValueError:
            pass

        status = io_partition.get_status()
        metrics = status["metrics"]

        assert metrics["total_operations"] == 3
        assert metrics["successful_operations"] == 2
        assert metrics["failed_operations"] == 1
        assert abs(metrics["success_rate"] - 0.6666666666666666) < 0.0001

    def test_get_status_structure(self, io_partition):
        """Test status structure without execution."""
        status = io_partition.get_status()

        assert "name" in status
        assert "type" in status
        assert "metrics" in status
        assert "config" in status
        assert "resources" in status
        assert "circuit_breaker" in status

        # Check metrics structure
        metrics = status["metrics"]
        required_metrics = [
            "total_operations",
            "successful_operations",
            "failed_operations",
            "rejected_operations",
            "active_operations",
            "queued_operations",
            "avg_execution_time",
            "max_execution_time",
            "success_rate",
        ]
        for metric in required_metrics:
            assert metric in metrics

    @pytest.mark.asyncio
    async def test_operation_cleanup(self, io_partition):
        """Test that operations are properly cleaned up."""

        def simple_task():
            return "done"

        # Check initial state
        assert len(io_partition._active_operations) == 0

        # Execute operation
        await io_partition.execute(simple_task)

        # Check operations are cleaned up
        assert len(io_partition._active_operations) == 0

    @pytest.mark.asyncio
    async def test_cpu_bound_execution_path(self, cpu_partition):
        """Test CPU-bound execution uses thread pool."""

        def cpu_task(n):
            return sum(range(n))

        # Test actual execution without complex mocking
        result = await cpu_partition.execute(cpu_task, 10)
        assert result == 45  # sum(range(10)) = 0+1+2+...+9 = 45

        # Verify metrics recorded the operation
        status = cpu_partition.get_status()
        assert status["metrics"]["successful_operations"] >= 1


class TestBulkheadManager:
    """Test bulkhead manager functionality."""

    def test_manager_initialization(self):
        """Test manager initialization with default partitions."""
        manager = BulkheadManager()

        # Check default partitions exist
        assert "critical" in manager.partitions
        assert "database" in manager.partitions
        assert "compute" in manager.partitions
        assert "background" in manager.partitions

        # Check partition types
        assert (
            manager.partitions["critical"].config.partition_type
            == PartitionType.CRITICAL
        )
        assert (
            manager.partitions["database"].config.partition_type
            == PartitionType.IO_BOUND
        )
        assert (
            manager.partitions["compute"].config.partition_type
            == PartitionType.CPU_BOUND
        )
        assert (
            manager.partitions["background"].config.partition_type
            == PartitionType.BACKGROUND
        )

    def test_create_custom_partition(self):
        """Test creating custom partition."""
        manager = BulkheadManager()

        config = PartitionConfig(
            name="custom",
            partition_type=PartitionType.CUSTOM,
            max_concurrent_operations=5,
        )

        partition = manager.create_partition(config)
        assert partition.config.name == "custom"
        assert "custom" in manager.partitions
        assert manager.get_partition("custom") == partition

    def test_duplicate_partition_error(self):
        """Test error when creating duplicate partition."""
        manager = BulkheadManager()

        config = PartitionConfig(
            name="database", partition_type=PartitionType.IO_BOUND  # Already exists
        )

        with pytest.raises(ValueError, match="already exists"):
            manager.create_partition(config)

    def test_get_nonexistent_partition_error(self):
        """Test error when getting nonexistent partition."""
        manager = BulkheadManager()

        with pytest.raises(ValueError, match="not found"):
            manager.get_partition("nonexistent")

    def test_get_all_status(self):
        """Test getting status of all partitions."""
        manager = BulkheadManager()

        all_status = manager.get_all_status()

        assert isinstance(all_status, dict)
        assert "critical" in all_status
        assert "database" in all_status
        assert "compute" in all_status
        assert "background" in all_status

        # Check each status has required structure
        for partition_status in all_status.values():
            assert "name" in partition_status
            assert "metrics" in partition_status
            assert "config" in partition_status

    @pytest.mark.asyncio
    async def test_isolated_execution_context_manager(self):
        """Test isolated execution context manager."""
        manager = BulkheadManager()

        def simple_task():
            return "executed"

        async with manager.isolated_execution("database") as partition:
            result = await partition.execute(simple_task)
            assert result == "executed"


class TestGlobalBulkheadManager:
    """Test global bulkhead manager functions."""

    def test_get_global_manager_singleton(self):
        """Test global manager is singleton."""
        # Clear any existing global manager
        import src.kailash.core.resilience.bulkhead as bulkhead_module

        bulkhead_module._bulkhead_manager = None

        manager1 = get_bulkhead_manager()
        manager2 = get_bulkhead_manager()

        assert manager1 is manager2
        assert isinstance(manager1, BulkheadManager)

    @pytest.mark.asyncio
    async def test_execute_with_bulkhead_convenience(self):
        """Test convenience function for bulkhead execution."""
        # Clear any existing global manager
        import src.kailash.core.resilience.bulkhead as bulkhead_module

        bulkhead_module._bulkhead_manager = None

        def test_function(x, y):
            return x * y

        result = await execute_with_bulkhead("database", test_function, 6, 7)
        assert result == 42


class TestEnumTypes:
    """Test enum type definitions."""

    def test_partition_types(self):
        """Test partition type enum values."""
        assert PartitionType.CPU_BOUND.value == "cpu_bound"
        assert PartitionType.IO_BOUND.value == "io_bound"
        assert PartitionType.CRITICAL.value == "critical"
        assert PartitionType.BACKGROUND.value == "background"
        assert PartitionType.CUSTOM.value == "custom"

    def test_resource_types(self):
        """Test resource type enum values."""
        assert ResourceType.THREADS.value == "threads"
        assert ResourceType.CONNECTIONS.value == "connections"
        assert ResourceType.MEMORY.value == "memory"
        assert ResourceType.SEMAPHORE.value == "semaphore"


class TestBulkheadExceptions:
    """Test bulkhead exception types."""

    def test_rejection_error(self):
        """Test BulkheadRejectionError exception."""
        error = BulkheadRejectionError("Test rejection")
        assert str(error) == "Test rejection"
        assert isinstance(error, Exception)
