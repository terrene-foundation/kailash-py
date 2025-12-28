"""
Unit tests for Resource Factories.

Tests factory implementations for:
- Database pools (PostgreSQL, MySQL, SQLite)
- HTTP clients (aiohttp, httpx)
- Caches (Redis, Memcached, in-memory)
- Message queues (RabbitMQ, Kafka, Redis)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.resources.factory import (
    CacheFactory,
    DatabasePoolFactory,
    HttpClientFactory,
    MessageQueueFactory,
)


class TestDatabasePoolFactory:
    """Test DatabasePoolFactory functionality."""

    def test_postgres_config(self):
        """Test PostgreSQL configuration."""
        factory = DatabasePoolFactory(
            backend="postgresql",
            host="db.example.com",
            port=5433,
            database="myapp",
            user="testuser",
            password="secret",
            min_size=2,
            max_size=10,
        )

        config = factory.get_config()
        assert config["backend"] == "postgresql"
        assert config["host"] == "db.example.com"
        assert config["port"] == 5433
        assert config["database"] == "myapp"
        assert config["user"] == "testuser"
        assert config["min_size"] == 2
        assert config["max_size"] == 10
        assert "password" not in config  # Should be excluded

    def test_default_ports(self):
        """Test default port assignment."""
        postgres_factory = DatabasePoolFactory(backend="postgresql")
        assert postgres_factory.port == 5432

        mysql_factory = DatabasePoolFactory(backend="mysql")
        assert mysql_factory.port == 3306

        sqlite_factory = DatabasePoolFactory(backend="sqlite")
        assert sqlite_factory.port is None

    @pytest.mark.asyncio
    async def test_postgres_pool_creation(self):
        """Test PostgreSQL pool creation."""
        factory = DatabasePoolFactory(
            backend="postgresql",
            host="localhost",
            database="test",
            user="test",
            password="test",
        )

        with patch("asyncpg.create_pool") as mock_create_pool:
            mock_pool = MagicMock()
            mock_create_pool.return_value = asyncio.Future()
            mock_create_pool.return_value.set_result(mock_pool)

            result = await factory.create()

            assert result == mock_pool
            mock_create_pool.assert_called_once()

            # Check DSN format
            call_args = mock_create_pool.call_args
            dsn = call_args[0][0]
            assert "postgresql://test:test@localhost:5432/test" == dsn

    @pytest.mark.asyncio
    async def test_mysql_pool_creation(self):
        """Test MySQL pool creation."""
        factory = DatabasePoolFactory(
            backend="mysql",
            host="localhost",
            database="test",
            user="test",
            password="test",
        )

        with patch("aiomysql.create_pool") as mock_create_pool:
            mock_pool = MagicMock()
            mock_create_pool.return_value = asyncio.Future()
            mock_create_pool.return_value.set_result(mock_pool)

            result = await factory.create()

            assert result == mock_pool
            mock_create_pool.assert_called_once_with(
                host="localhost",
                port=3306,
                user="test",
                password="test",
                db="test",
                minsize=5,
                maxsize=20,
            )

    @pytest.mark.asyncio
    async def test_sqlite_connection_creation(self):
        """Test SQLite connection creation."""
        factory = DatabasePoolFactory(backend="sqlite", database="/path/to/db.sqlite")

        with patch("aiosqlite.connect", new_callable=AsyncMock) as mock_connect:
            mock_conn = MagicMock()
            # aiosqlite.connect is an async function that returns a connection
            mock_connect.return_value = mock_conn

            result = await factory.create()

            assert result == mock_conn
            mock_connect.assert_called_once_with("/path/to/db.sqlite")

    @pytest.mark.asyncio
    async def test_unsupported_backend(self):
        """Test error for unsupported database backend."""
        factory = DatabasePoolFactory(backend="oracle")

        with pytest.raises(ValueError, match="Unsupported database backend: oracle"):
            await factory.create()

    @pytest.mark.asyncio
    async def test_missing_dependency(self):
        """Test error when database dependency is missing."""
        factory = DatabasePoolFactory(backend="postgresql")

        # Mock the import to raise ImportError
        with patch.dict("sys.modules", {"asyncpg": None}):
            with pytest.raises(ImportError, match="asyncpg is required"):
                await factory.create()


class TestHttpClientFactory:
    """Test HttpClientFactory functionality."""

    def test_aiohttp_config(self):
        """Test aiohttp configuration."""
        factory = HttpClientFactory(
            backend="aiohttp",
            base_url="https://api.example.com",
            timeout=60,
            headers={"Authorization": "Bearer token123"},
        )

        config = factory.get_config()
        assert config["backend"] == "aiohttp"
        assert config["base_url"] == "https://api.example.com"
        assert config["timeout"] == 60
        # Headers should mask auth values
        assert config["headers"]["Authorization"] == "***"

    @pytest.mark.asyncio
    async def test_aiohttp_client_creation(self):
        """Test aiohttp client creation."""
        factory = HttpClientFactory(
            backend="aiohttp", base_url="https://api.example.com", timeout=30
        )

        with patch("aiohttp.ClientSession") as MockSession:
            with patch("aiohttp.ClientTimeout") as MockTimeout:
                with patch("aiohttp.TCPConnector") as MockConnector:
                    mock_session = MagicMock()
                    MockSession.return_value = mock_session

                    result = await factory.create()

                    assert result == mock_session
                    MockTimeout.assert_called_once_with(total=30)
                    MockConnector.assert_called_once_with(limit=100)

    def test_httpx_client_creation(self):
        """Test httpx client creation."""
        factory = HttpClientFactory(
            backend="httpx", base_url="https://api.example.com", timeout=30
        )

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value = mock_client

            result = factory._create_httpx_client()

            assert result == mock_client
            MockClient.assert_called_once_with(
                base_url="https://api.example.com", timeout=30, headers={}
            )

    @pytest.mark.asyncio
    async def test_unsupported_backend(self):
        """Test error for unsupported HTTP backend."""
        factory = HttpClientFactory(backend="requests")

        with pytest.raises(ValueError, match="Unsupported HTTP backend: requests"):
            await factory.create()


class TestCacheFactory:
    """Test CacheFactory functionality."""

    def test_redis_config(self):
        """Test Redis configuration."""
        factory = CacheFactory(
            backend="redis", host="cache.example.com", port=6380, db=1
        )

        config = factory.get_config()
        assert config["backend"] == "redis"
        assert config["host"] == "cache.example.com"
        assert config["port"] == 6380
        assert config["db"] == 1

    def test_default_ports(self):
        """Test default port assignment."""
        redis_factory = CacheFactory(backend="redis")
        assert redis_factory.port == 6379

        memcached_factory = CacheFactory(backend="memcached")
        assert memcached_factory.port == 11211

        memory_factory = CacheFactory(backend="memory")
        assert memory_factory.port is None

    @pytest.mark.asyncio
    async def test_redis_client_creation(self):
        """Test Redis client creation."""
        factory = CacheFactory(backend="redis", host="localhost", port=6379)

        # Patch the actual method that creates Redis client
        with patch.object(factory, "_create_redis_client") as mock_create:
            mock_client = MagicMock()
            mock_create.return_value = mock_client

            result = await factory.create()

            assert result == mock_client
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_memcached_client_creation(self):
        """Test Memcached client creation."""
        factory = CacheFactory(backend="memcached", host="localhost", port=11211)

        with patch.object(factory, "_create_memcached_client") as mock_create:
            mock_client = MagicMock()
            mock_create.return_value = mock_client

            result = await factory.create()

            assert result == mock_client
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_memory_cache_creation(self):
        """Test in-memory cache creation."""
        factory = CacheFactory(backend="memory")

        result = factory._create_memory_cache()

        # Test the cache interface
        await result.set("key1", "value1")
        value = await result.get("key1")
        assert value == "value1"

        await result.delete("key1")
        value = await result.get("key1")
        assert value is None

        await result.set("key2", "value2")
        await result.clear()
        value = await result.get("key2")
        assert value is None


class TestMessageQueueFactory:
    """Test MessageQueueFactory functionality."""

    def test_rabbitmq_config(self):
        """Test RabbitMQ configuration."""
        factory = MessageQueueFactory(
            backend="rabbitmq",
            host="mq.example.com",
            port=5673,
            username="user",
            password="secret",
        )

        config = factory.get_config()
        assert config["backend"] == "rabbitmq"
        assert config["host"] == "mq.example.com"
        assert config["port"] == 5673
        assert config["username"] == "user"
        assert "password" not in config  # Should be excluded

    def test_default_ports(self):
        """Test default port assignment."""
        rabbitmq_factory = MessageQueueFactory(backend="rabbitmq")
        assert rabbitmq_factory.port == 5672

        kafka_factory = MessageQueueFactory(backend="kafka")
        assert kafka_factory.port == 9092

        redis_factory = MessageQueueFactory(backend="redis")
        assert redis_factory.port == 6379

    @pytest.mark.asyncio
    async def test_rabbitmq_client_creation(self):
        """Test RabbitMQ client creation."""
        factory = MessageQueueFactory(
            backend="rabbitmq", host="localhost", username="guest", password="guest"
        )

        with patch.object(factory, "_create_rabbitmq_client") as mock_create:
            mock_connection = MagicMock()
            mock_create.return_value = mock_connection

            result = await factory.create()

            assert result == mock_connection
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_kafka_client_creation(self):
        """Test Kafka client creation."""
        factory = MessageQueueFactory(backend="kafka", host="localhost", port=9092)

        with patch.object(factory, "_create_kafka_client") as mock_create:
            mock_client = MagicMock()
            mock_client.producer = MagicMock()
            mock_client.consumer = MagicMock()
            mock_create.return_value = mock_client

            result = await factory.create()

            assert result == mock_client
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_pubsub_creation(self):
        """Test Redis Pub/Sub creation."""
        factory = MessageQueueFactory(backend="redis", host="localhost")

        with patch.object(factory, "_create_redis_pubsub") as mock_redis:
            mock_client = MagicMock()
            mock_redis.return_value = mock_client

            result = await factory.create()

            assert result == mock_client

    @pytest.mark.asyncio
    async def test_unsupported_backend(self):
        """Test error for unsupported message queue backend."""
        factory = MessageQueueFactory(backend="activemq")

        with pytest.raises(
            ValueError, match="Unsupported message queue backend: activemq"
        ):
            await factory.create()
