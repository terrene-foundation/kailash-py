"""
Unit tests for retry configuration, metrics, and exception handling.

Tests cover:
1. Database-specific retry configuration factory methods
2. RetryMetrics thread safety and accuracy
3. RetryExhaustedException proper context capture
4. RetryConfig behavior (get_delay, should_retry, etc.)
"""

import threading
import time
from unittest.mock import Mock

import pytest

from kailash.nodes.data.async_sql import RetryConfig, RetryMetrics
from kailash.sdk_exceptions import RetryExhaustedException


class TestRetryConfig:
    """Test RetryConfig class behavior and database-specific configurations."""

    def test_default_retry_config(self):
        """Test default RetryConfig initialization."""
        config = RetryConfig()

        assert config.max_retries == 3
        assert config.initial_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
        assert config.jitter is True
        assert config.database_type is None
        assert config.metrics is None

    def test_sqlite_retry_config(self):
        """Test SQLite-optimized retry configuration."""
        config = RetryConfig.for_database("sqlite")

        # SQLite needs more aggressive retries due to file-level locking
        assert (
            config.max_retries == 10
        ), "SQLite should have 10 retries (increased from 3)"
        assert config.initial_delay == 0.5, "SQLite should start with 0.5s delay"
        assert config.max_delay == 30.0, "SQLite should have 30s max delay"
        assert (
            config.exponential_base == 1.5
        ), "SQLite should have gentler backoff (1.5x)"
        assert config.database_type == "sqlite"

    def test_postgresql_retry_config(self):
        """Test PostgreSQL-optimized retry configuration."""
        config = RetryConfig.for_database("postgresql")

        # PostgreSQL has better MVCC, needs fewer retries
        assert config.max_retries == 5
        assert config.initial_delay == 0.1
        assert config.max_delay == 10.0
        assert config.exponential_base == 2.0
        assert config.database_type == "postgresql"

    def test_postgres_alias(self):
        """Test that 'postgres' alias works."""
        config = RetryConfig.for_database("postgres")

        assert config.database_type == "postgresql"
        assert config.max_retries == 5

    def test_mysql_retry_config(self):
        """Test MySQL-optimized retry configuration."""
        config = RetryConfig.for_database("mysql")

        assert config.max_retries == 5
        assert config.initial_delay == 0.2
        assert config.max_delay == 15.0
        assert config.exponential_base == 2.0
        assert config.database_type == "mysql"

    def test_unknown_database_defaults(self):
        """Test that unknown database types get default RetryConfig."""
        config = RetryConfig.for_database("unknown_db")

        # Unknown databases get default RetryConfig() values
        assert config.max_retries == 3
        assert config.initial_delay == 1.0
        assert config.max_delay == 60.0
        assert config.database_type == "unknown_db"  # Preserves the input database_type

    def test_case_insensitive_database_type(self):
        """Test that database type matching is case-insensitive."""
        config1 = RetryConfig.for_database("SQLite")
        config2 = RetryConfig.for_database("POSTGRESQL")
        config3 = RetryConfig.for_database("MySQL")

        assert config1.database_type == "sqlite"
        assert config2.database_type == "postgresql"
        assert config3.database_type == "mysql"

    def test_get_delay_exponential_backoff(self):
        """Test exponential backoff delay calculation."""
        config = RetryConfig(
            initial_delay=1.0,
            max_delay=10.0,
            exponential_base=2.0,
            jitter=False,  # Disable jitter for deterministic testing
        )

        # Test exponential growth
        delay0 = config.get_delay(0)
        delay1 = config.get_delay(1)
        delay2 = config.get_delay(2)

        assert delay0 == 1.0, "First retry should be initial_delay"
        assert delay1 == 2.0, "Second retry should be 2x initial_delay"
        assert delay2 == 4.0, "Third retry should be 4x initial_delay"

    def test_get_delay_max_delay_cap(self):
        """Test that delays are capped at max_delay."""
        config = RetryConfig(
            initial_delay=1.0, max_delay=5.0, exponential_base=2.0, jitter=False
        )

        # After enough attempts, should hit max_delay
        delay10 = config.get_delay(10)  # Would be 1024.0 without cap

        assert delay10 == 5.0, "Delay should be capped at max_delay"

    def test_get_delay_with_jitter(self):
        """Test that jitter adds randomness to delays."""
        config = RetryConfig(
            initial_delay=1.0, max_delay=10.0, exponential_base=2.0, jitter=True
        )

        # Run multiple times to see variation
        delays = [config.get_delay(1) for _ in range(100)]

        # Base delay for attempt 1: 1.0 * (2.0 ** 1) = 2.0
        # Jitter is ±25%, so range is 2.0 ± 0.5 = [1.5, 2.5]
        assert all(
            1.5 <= d <= 2.5 for d in delays
        ), "Jittered delays should be in range [1.5, 2.5]"

        # With 100 samples, should have variation (not all identical)
        assert len(set(delays)) > 1, "Jitter should create variation"

    def test_should_retry_database_locked(self):
        """Test that database locked errors are retryable."""
        config = RetryConfig()

        error = Exception("database is locked")
        assert config.should_retry(error) is True

    def test_should_retry_timeout_errors(self):
        """Test that timeout errors are retryable."""
        config = RetryConfig()

        errors = [
            Exception("Operation timed out"),
            Exception("Connection timeout occurred"),
        ]

        for error in errors:
            assert config.should_retry(error) is True, f"Should retry: {error}"

    def test_should_retry_connection_error(self):
        """Test that connection errors are retryable."""
        config = RetryConfig()

        errors = [
            Exception("connection_refused by server"),
            Exception("connection reset by peer"),
            Exception("could not connect to database"),
        ]

        for error in errors:
            assert config.should_retry(error) is True, f"Should retry: {error}"

    def test_should_not_retry_non_retryable_errors(self):
        """Test that non-retryable errors return False."""
        config = RetryConfig()

        errors = [
            Exception("syntax error"),
            Exception("table does not exist"),
            Exception("column does not exist"),
        ]

        for error in errors:
            assert config.should_retry(error) is False, f"Should not retry: {error}"

    def test_metrics_integration(self):
        """Test that RetryConfig can integrate with RetryMetrics."""
        metrics = RetryMetrics()
        config = RetryConfig.for_database("sqlite", metrics=metrics)

        assert config.metrics is metrics
        assert config.database_type == "sqlite"


class TestRetryMetrics:
    """Test RetryMetrics class for thread-safe metrics tracking."""

    def test_initialization(self):
        """Test RetryMetrics initialization."""
        metrics = RetryMetrics()

        assert metrics.total_operations == 0
        assert metrics.total_retries == 0
        assert metrics.failed_operations == 0
        assert len(metrics.retry_histogram) == 0

    def test_record_successful_operation_no_retries(self):
        """Test recording a successful operation with no retries."""
        metrics = RetryMetrics()

        metrics.record_operation(num_retries=0, success=True)

        assert metrics.total_operations == 1
        assert metrics.total_retries == 0
        assert metrics.failed_operations == 0
        assert metrics.retry_histogram[0] == 1

    def test_record_successful_operation_with_retries(self):
        """Test recording a successful operation after retries."""
        metrics = RetryMetrics()

        metrics.record_operation(num_retries=3, success=True)

        assert metrics.total_operations == 1
        assert metrics.total_retries == 3
        assert metrics.failed_operations == 0
        assert metrics.retry_histogram[3] == 1

    def test_record_failed_operation(self):
        """Test recording a failed operation."""
        metrics = RetryMetrics()

        metrics.record_operation(num_retries=5, success=False)

        assert metrics.total_operations == 1
        assert metrics.total_retries == 5
        assert metrics.failed_operations == 1
        assert metrics.retry_histogram[5] == 1

    def test_multiple_operations(self):
        """Test tracking multiple operations."""
        metrics = RetryMetrics()

        # Record various operations
        metrics.record_operation(0, True)  # Success, no retries
        metrics.record_operation(2, True)  # Success, 2 retries
        metrics.record_operation(2, True)  # Success, 2 retries
        metrics.record_operation(5, False)  # Failed after 5 retries
        metrics.record_operation(1, True)  # Success, 1 retry

        assert metrics.total_operations == 5
        assert metrics.total_retries == 10  # 0 + 2 + 2 + 5 + 1
        assert metrics.failed_operations == 1
        assert metrics.retry_histogram[0] == 1
        assert metrics.retry_histogram[1] == 1
        assert metrics.retry_histogram[2] == 2
        assert metrics.retry_histogram[5] == 1

    def test_get_metrics_snapshot(self):
        """Test getting a metrics snapshot."""
        metrics = RetryMetrics()

        metrics.record_operation(0, True)
        metrics.record_operation(2, True)
        metrics.record_operation(5, False)

        snapshot = metrics.get_metrics()

        assert snapshot["total_operations"] == 3
        assert snapshot["total_retries"] == 7
        assert snapshot["failed_operations"] == 1
        assert snapshot["avg_retries_per_operation"] == pytest.approx(7 / 3)
        assert snapshot["failure_rate"] == pytest.approx(1 / 3)
        assert snapshot["retry_histogram"] == {0: 1, 2: 1, 5: 1}

    def test_thread_safety(self):
        """Test that RetryMetrics is thread-safe."""
        metrics = RetryMetrics()
        num_threads = 10
        operations_per_thread = 100

        def worker():
            for _ in range(operations_per_thread):
                metrics.record_operation(num_retries=1, success=True)

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # All operations should be recorded
        expected_total = num_threads * operations_per_thread
        assert metrics.total_operations == expected_total
        assert metrics.total_retries == expected_total  # Each had 1 retry
        assert metrics.failed_operations == 0

    def test_concurrent_histogram_updates(self):
        """Test that histogram updates are thread-safe."""
        metrics = RetryMetrics()
        num_threads = 5

        def worker(retry_count):
            for _ in range(50):
                metrics.record_operation(retry_count, True)

        threads = [
            threading.Thread(target=worker, args=(i,)) for i in range(num_threads)
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # Check histogram
        for i in range(num_threads):
            assert metrics.retry_histogram[i] == 50


class TestRetryExhaustedException:
    """Test RetryExhaustedException context capture."""

    def test_initialization(self):
        """Test RetryExhaustedException initialization."""
        original_error = Exception("Database locked")

        exc = RetryExhaustedException(
            operation="Database query execution",
            attempts=10,
            last_error=original_error,
            total_wait_time=15.5,
        )

        assert exc.operation == "Database query execution"
        assert exc.attempts == 10
        assert exc.last_error is original_error
        assert exc.total_wait_time == 15.5

    def test_message_format(self):
        """Test exception message formatting."""
        original_error = Exception("Connection refused")

        exc = RetryExhaustedException(
            operation="Database connection",
            attempts=5,
            last_error=original_error,
            total_wait_time=8.2,
        )

        message = str(exc)

        assert "Database connection" in message
        assert "5 retry attempts" in message
        assert "Connection refused" in message
        assert "8.20s" in message

    def test_message_without_wait_time(self):
        """Test exception message when total_wait_time is None."""
        exc = RetryExhaustedException(
            operation="Database query", attempts=3, last_error=Exception("Timeout")
        )

        message = str(exc)

        assert "3 retry attempts" in message
        assert "Timeout" in message
        # Should not contain wait time info
        assert "wait time" not in message.lower()

    def test_exception_inheritance(self):
        """Test that RetryExhaustedException inherits from RuntimeException."""
        from kailash.sdk_exceptions import RuntimeException

        exc = RetryExhaustedException(
            operation="Test", attempts=1, last_error=Exception("Test")
        )

        assert isinstance(exc, RuntimeException)

    def test_can_catch_as_runtime_exception(self):
        """Test that RetryExhaustedException can be caught as RuntimeException."""
        from kailash.sdk_exceptions import RuntimeException

        try:
            raise RetryExhaustedException(
                operation="Test", attempts=3, last_error=Exception("Original error")
            )
        except RuntimeException as e:
            assert isinstance(e, RetryExhaustedException)
            assert e.operation == "Test"
            assert e.attempts == 3

    def test_can_catch_as_kailash_exception(self):
        """Test that RetryExhaustedException can be caught as KailashException."""
        from kailash.sdk_exceptions import KailashException

        try:
            raise RetryExhaustedException(
                operation="Test", attempts=3, last_error=Exception("Original error")
            )
        except KailashException as e:
            assert isinstance(e, RetryExhaustedException)

    def test_exception_attributes_accessible(self):
        """Test that all exception attributes are accessible."""
        original_error = Exception("Database locked")

        exc = RetryExhaustedException(
            operation="Bulk insert",
            attempts=10,
            last_error=original_error,
            total_wait_time=25.3,
        )

        # All attributes should be accessible
        assert hasattr(exc, "operation")
        assert hasattr(exc, "attempts")
        assert hasattr(exc, "last_error")
        assert hasattr(exc, "total_wait_time")

        # Verify values
        assert exc.operation == "Bulk insert"
        assert exc.attempts == 10
        assert exc.last_error.args[0] == "Database locked"
        assert exc.total_wait_time == 25.3


class TestRetryConfigIntegration:
    """Integration tests for RetryConfig with RetryMetrics."""

    def test_config_with_metrics_lifecycle(self):
        """Test full lifecycle of config with metrics."""
        metrics = RetryMetrics()
        config = RetryConfig.for_database("sqlite", metrics=metrics)

        # Simulate retry loop
        for attempt in range(config.max_retries):
            try:
                # Simulate operation
                if attempt < 3:
                    # First 3 attempts fail
                    raise Exception("database is locked")
                else:
                    # 4th attempt succeeds
                    break
            except Exception as e:
                if not config.should_retry(e):
                    metrics.record_operation(attempt + 1, success=False)
                    raise

                if attempt >= config.max_retries - 1:
                    metrics.record_operation(attempt + 1, success=False)
                    raise

                time.sleep(0.001)  # Small delay for test speed

        # Record success
        metrics.record_operation(attempt, success=True)

        # Verify metrics
        snapshot = metrics.get_metrics()
        assert snapshot["total_operations"] == 1
        assert snapshot["total_retries"] == 3
        assert snapshot["failed_operations"] == 0

    def test_different_databases_different_configs(self):
        """Test that different databases get different configs."""
        sqlite_config = RetryConfig.for_database("sqlite")
        postgres_config = RetryConfig.for_database("postgresql")
        mysql_config = RetryConfig.for_database("mysql")

        # SQLite should have most retries (file-level locking)
        assert sqlite_config.max_retries > postgres_config.max_retries
        assert sqlite_config.max_retries > mysql_config.max_retries

        # SQLite should have gentler backoff
        assert sqlite_config.exponential_base < postgres_config.exponential_base

        # SQLite should have longer timeout
        assert sqlite_config.max_delay > postgres_config.max_delay
