"""Tests for AsyncSQLDatabaseNode retry logic."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode, RetryConfig
from kailash.sdk_exceptions import NodeExecutionError


class TestRetryConfig:
    """Test RetryConfig functionality."""

    def test_default_retry_config(self):
        """Test default retry configuration."""
        config = RetryConfig()

        assert config.max_retries == 3
        assert config.initial_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
        assert config.jitter is True
        assert len(config.retryable_errors) > 0

    def test_custom_retry_config(self):
        """Test custom retry configuration."""
        config = RetryConfig(
            max_retries=5,
            initial_delay=0.5,
            max_delay=30.0,
            exponential_base=3.0,
            jitter=False,
        )

        assert config.max_retries == 5
        assert config.initial_delay == 0.5
        assert config.max_delay == 30.0
        assert config.exponential_base == 3.0
        assert config.jitter is False

    def test_should_retry_detection(self):
        """Test error detection for retry."""
        config = RetryConfig()

        # Retryable errors
        retryable_errors = [
            Exception("connection_refused"),
            Exception("Connection reset by peer"),
            Exception("pool is closed"),
            Exception("Lost connection to MySQL server"),
            Exception("database is locked"),
            Exception("Request timed out"),
        ]

        for error in retryable_errors:
            assert config.should_retry(error) is True

        # Non-retryable errors
        non_retryable_errors = [
            Exception("Syntax error in SQL"),
            Exception("Table not found"),
            Exception("Permission denied"),
        ]

        for error in non_retryable_errors:
            assert config.should_retry(error) is False

    def test_delay_calculation_without_jitter(self):
        """Test delay calculation without jitter."""
        config = RetryConfig(
            initial_delay=1.0,
            exponential_base=2.0,
            max_delay=10.0,
            jitter=False,
        )

        # Test exponential backoff
        assert config.get_delay(0) == 1.0  # 1 * 2^0
        assert config.get_delay(1) == 2.0  # 1 * 2^1
        assert config.get_delay(2) == 4.0  # 1 * 2^2
        assert config.get_delay(3) == 8.0  # 1 * 2^3
        assert config.get_delay(4) == 10.0  # capped at max_delay

    def test_delay_calculation_with_jitter(self):
        """Test delay calculation with jitter."""
        config = RetryConfig(
            initial_delay=1.0,
            exponential_base=2.0,
            jitter=True,
        )

        # With jitter, delay should be within ±25% of base delay
        for attempt in range(5):
            delay = config.get_delay(attempt)
            base_delay = 1.0 * (2.0**attempt)
            min_delay = base_delay * 0.75
            max_delay = base_delay * 1.25
            assert min_delay <= delay <= max_delay


class TestAsyncSQLRetry:
    """Test AsyncSQLDatabaseNode retry functionality."""

    def test_retry_config_from_dict(self):
        """Test creating node with retry config as dict."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            retry_config={
                "max_retries": 5,
                "initial_delay": 0.5,
            },
        )

        assert node._retry_config.max_retries == 5
        assert node._retry_config.initial_delay == 0.5

    def test_retry_config_from_params(self):
        """Test creating node with individual retry parameters."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            max_retries=4,
            retry_delay=2.0,
        )

        assert node._retry_config.max_retries == 4
        assert node._retry_config.initial_delay == 2.0

    @pytest.mark.asyncio
    async def test_connection_retry_success(self):
        """Test successful connection after retries."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            max_retries=3,
            retry_delay=0.1,  # Short delay for tests
        )

        # Mock the adapter's connect method instead
        mock_adapter = MagicMock()
        connect_calls = 0

        async def mock_connect():
            nonlocal connect_calls
            connect_calls += 1
            if connect_calls < 3:
                raise Exception("connection_refused")
            # Success on third attempt

        mock_adapter.connect = AsyncMock(side_effect=mock_connect)

        # Mock adapter type selection
        with patch(
            "kailash.nodes.data.async_sql.PostgreSQLAdapter", return_value=mock_adapter
        ):
            adapter = await node._create_adapter()
            assert adapter is mock_adapter
            assert connect_calls == 3

    @pytest.mark.asyncio
    async def test_connection_retry_failure(self):
        """Test connection failure after all retries."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            max_retries=2,
            retry_delay=0.1,
        )

        # Mock the adapter's connect method
        mock_adapter = MagicMock()
        mock_adapter.connect = AsyncMock(side_effect=Exception("connection_refused"))

        # Mock adapter type selection
        with patch(
            "kailash.nodes.data.async_sql.PostgreSQLAdapter", return_value=mock_adapter
        ):
            # Should fail after max retries
            with pytest.raises(
                NodeExecutionError, match="Failed to connect after 2 attempts"
            ):
                await node._create_adapter()

            assert mock_adapter.connect.call_count == 2

    @pytest.mark.asyncio
    async def test_query_retry_transient_error(self):
        """Test query retry on transient errors."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            max_retries=3,
            retry_delay=0.1,
        )

        # Mock adapter
        mock_adapter = AsyncMock()

        # Mock _get_adapter to return our mock
        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            # Mock _execute_with_transaction to fail twice then succeed
            with patch.object(node, "_execute_with_transaction") as mock_execute:
                mock_execute.side_effect = [
                    Exception("connection reset"),
                    Exception("pool is closed"),
                    [{"id": 1, "name": "test"}],  # Success on third attempt
                ]

                result = await node.execute_async(query="SELECT * FROM users")

                assert mock_execute.call_count == 3
                assert result["result"]["data"] == [{"id": 1, "name": "test"}]

    @pytest.mark.asyncio
    async def test_query_retry_non_retryable_error(self):
        """Test that non-retryable errors fail immediately."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            max_retries=3,
        )

        # Mock adapter
        mock_adapter = AsyncMock()

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            with patch.object(node, "_execute_with_transaction") as mock_execute:
                # Non-retryable error
                mock_execute.side_effect = Exception("Syntax error in SQL")

                with pytest.raises(NodeExecutionError, match="Syntax error"):
                    await node.execute_async(query="INVALID SQL")

                # Should fail immediately without retries
                assert mock_execute.call_count == 1

    @pytest.mark.asyncio
    async def test_query_retry_exhaustion(self):
        """Test error after all retries are exhausted."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            max_retries=2,
            retry_delay=0.1,
        )

        # Mock adapter
        mock_adapter = AsyncMock()

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            with patch.object(node, "_execute_with_transaction") as mock_execute:
                # Always fail with retryable error
                mock_execute.side_effect = Exception("connection reset")

                with pytest.raises(NodeExecutionError, match="Database query failed"):
                    await node.execute_async(query="SELECT * FROM users")

                assert mock_execute.call_count == 2

    @pytest.mark.asyncio
    async def test_reconnection_on_pool_closed(self):
        """Test automatic reconnection when pool is closed."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            max_retries=3,
            retry_delay=0.1,
        )

        # Set up initial adapter
        mock_adapter1 = AsyncMock()
        mock_adapter2 = AsyncMock()
        node._adapter = mock_adapter1
        node._connected = True

        # Mock _get_adapter to return new adapter after reconnection
        get_adapter_calls = 0

        async def mock_get_adapter():
            nonlocal get_adapter_calls
            get_adapter_calls += 1
            if get_adapter_calls == 1:
                return mock_adapter1
            return mock_adapter2

        with patch.object(node, "_get_adapter", side_effect=mock_get_adapter):
            with patch.object(node, "_execute_with_transaction") as mock_execute:
                # First call fails with pool closed, second succeeds
                mock_execute.side_effect = [
                    Exception("pool is closed"),
                    [{"id": 1}],
                ]

                result = await node.execute_async(query="SELECT * FROM users")

                # Should have cleared adapter to force reconnection
                assert get_adapter_calls == 2
                assert result["result"]["data"] == [{"id": 1}]

    @pytest.mark.asyncio
    async def test_retry_delay_timing(self):
        """Test that retry delays are applied correctly."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            retry_config={
                "max_retries": 3,
                "initial_delay": 0.1,
                "exponential_base": 2.0,
                "jitter": False,  # No jitter for predictable timing
            },
        )

        # Mock adapter
        mock_adapter = AsyncMock()

        # Track sleep calls
        sleep_calls = []

        async def mock_sleep(delay):
            sleep_calls.append(delay)

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            with patch.object(node, "_execute_with_transaction") as mock_execute:
                with patch("asyncio.sleep", side_effect=mock_sleep):
                    # Fail all attempts
                    mock_execute.side_effect = Exception("connection reset")

                    with pytest.raises(NodeExecutionError):
                        await node.execute_async(query="SELECT 1")

                    # Check delays: 0.1, 0.2 (0.1 * 2^1)
                    assert len(sleep_calls) == 2
                    assert sleep_calls[0] == 0.1
                    assert sleep_calls[1] == 0.2
