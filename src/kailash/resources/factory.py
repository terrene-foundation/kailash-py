"""
Resource Factories - Create and configure resources for the registry.

This module provides abstract factory interface and concrete implementations
for common resource types used in Kailash workflows.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ResourceFactory(ABC):
    """
    Abstract factory for creating resources.

    All resource factories must implement this interface to be used
    with the ResourceRegistry.
    """

    @abstractmethod
    async def create(self) -> Any:
        """
        Create and return a resource.

        This method should:
        - Create the resource (e.g., database connection pool)
        - Perform any initialization
        - Return the ready-to-use resource

        Returns:
            The created resource
        """
        pass

    @abstractmethod
    def get_config(self) -> Dict[str, Any]:
        """
        Get factory configuration for serialization.

        This is used for debugging and documentation purposes.

        Returns:
            Dictionary of configuration parameters
        """
        pass


class DatabasePoolFactory(ResourceFactory):
    """
    Factory for creating database connection pools.

    Supports multiple database backends:
    - PostgreSQL (asyncpg)
    - MySQL (aiomysql)
    - SQLite (aiosqlite)

    Example:
        ```python
        factory = DatabasePoolFactory(
            backend='postgresql',
            host='localhost',
            port=5432,
            database='myapp',
            user='dbuser',
            password='secret',
            min_size=5,
            max_size=20
        )
        ```
    """

    def __init__(
        self,
        backend: str = "postgresql",
        host: str = "localhost",
        port: Optional[int] = None,
        database: str = "test",
        user: Optional[str] = None,
        password: Optional[str] = None,
        min_size: int = 5,
        max_size: int = 20,
        **kwargs,
    ):
        """Initialize database pool factory."""
        self.backend = backend.lower()
        self.host = host
        self.port = port or self._default_port()
        self.database = database
        self.user = user
        self.password = password
        self.min_size = min_size
        self.max_size = max_size
        self.extra_config = kwargs

    def _default_port(self) -> int:
        """Get default port for backend."""
        return {
            "postgresql": 5432,
            "postgres": 5432,
            "mysql": 3306,
            "sqlite": None,
        }.get(self.backend, 5432)

    async def create(self) -> Any:
        """Create database connection pool."""
        if self.backend in ("postgresql", "postgres"):
            return await self._create_postgres_pool()
        elif self.backend == "mysql":
            return await self._create_mysql_pool()
        elif self.backend == "sqlite":
            return await self._create_sqlite_pool()
        else:
            raise ValueError(f"Unsupported database backend: {self.backend}")

    async def _create_postgres_pool(self):
        """Create PostgreSQL connection pool."""
        try:
            import asyncpg
        except ImportError:
            raise ImportError(
                "asyncpg is required for PostgreSQL. "
                "Install with: pip install asyncpg"
            )

        # Use default user if not provided
        user = self.user or "postgres"
        password = self.password or ""

        # Extract options if present
        options = self.extra_config.pop("options", None)

        # Build DSN
        dsn = f"postgresql://{user}:{password}@{self.host}:{self.port}/{self.database}"
        if options:
            # Add options to DSN as query parameters
            dsn += f"?options={options}"

        logger.info(
            f"Creating PostgreSQL pool: {self.host}:{self.port}/{self.database}"
        )

        return await asyncpg.create_pool(
            dsn, min_size=self.min_size, max_size=self.max_size, **self.extra_config
        )

    async def _create_mysql_pool(self):
        """Create MySQL connection pool."""
        try:
            import aiomysql
        except ImportError:
            raise ImportError(
                "aiomysql is required for MySQL. " "Install with: pip install aiomysql"
            )

        logger.info(f"Creating MySQL pool: {self.host}:{self.port}/{self.database}")

        return await aiomysql.create_pool(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            db=self.database,
            minsize=self.min_size,
            maxsize=self.max_size,
            **self.extra_config,
        )

    async def _create_sqlite_pool(self):
        """Create SQLite connection."""
        try:
            import aiosqlite
        except ImportError:
            raise ImportError(
                "aiosqlite is required for SQLite. "
                "Install with: pip install aiosqlite"
            )

        logger.info(f"Creating SQLite connection: {self.database}")

        # SQLite doesn't have pools, return a connection
        return await aiosqlite.connect(self.database, **self.extra_config)

    def get_config(self) -> Dict[str, Any]:
        """Get factory configuration."""
        config = {
            "backend": self.backend,
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.user,
            "min_size": self.min_size,
            "max_size": self.max_size,
        }
        config.update(self.extra_config)
        # Don't include password in config
        return {k: v for k, v in config.items() if k != "password"}


class HttpClientFactory(ResourceFactory):
    """
    Factory for creating HTTP clients.

    Supports:
    - aiohttp
    - httpx

    Example:
        ```python
        factory = HttpClientFactory(
            backend='aiohttp',
            base_url='https://api.example.com',
            timeout=30,
            headers={'Authorization': 'Bearer token'}
        )
        ```
    """

    def __init__(
        self,
        backend: str = "aiohttp",
        base_url: Optional[str] = None,
        timeout: int = 30,
        headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        """Initialize HTTP client factory."""
        self.backend = backend.lower()
        self.base_url = base_url
        self.timeout = timeout
        self.headers = headers or {}
        self.extra_config = kwargs

    async def create(self) -> Any:
        """Create HTTP client."""
        if self.backend == "aiohttp":
            return await self._create_aiohttp_client()
        elif self.backend == "httpx":
            return self._create_httpx_client()
        else:
            raise ValueError(f"Unsupported HTTP backend: {self.backend}")

    async def _create_aiohttp_client(self):
        """Create aiohttp client session."""
        try:
            import aiohttp
        except ImportError:
            raise ImportError("aiohttp is required. Install with: pip install aiohttp")

        logger.info(f"Creating aiohttp client: {self.base_url}")

        timeout = aiohttp.ClientTimeout(total=self.timeout)
        connector = aiohttp.TCPConnector(limit=100)

        return aiohttp.ClientSession(
            base_url=self.base_url,
            timeout=timeout,
            headers=self.headers,
            connector=connector,
            **self.extra_config,
        )

    def _create_httpx_client(self):
        """Create httpx async client."""
        try:
            import httpx
        except ImportError:
            raise ImportError("httpx is required. Install with: pip install httpx")

        logger.info(f"Creating httpx client: {self.base_url}")

        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=self.headers,
            **self.extra_config,
        )

    def get_config(self) -> Dict[str, Any]:
        """Get factory configuration."""
        config = {
            "backend": self.backend,
            "base_url": self.base_url,
            "timeout": self.timeout,
            "headers": {
                k: "***" if "auth" in k.lower() else v for k, v in self.headers.items()
            },
        }
        config.update(self.extra_config)
        return config


class CacheFactory(ResourceFactory):
    """
    Factory for creating cache clients.

    Supports:
    - Redis (aioredis)
    - Memcached (aiomemcache)
    - In-memory cache

    Example:
        ```python
        factory = CacheFactory(
            backend='redis',
            host='localhost',
            port=6379,
            db=0
        )
        ```
    """

    def __init__(
        self,
        backend: str = "redis",
        host: str = "localhost",
        port: Optional[int] = None,
        **kwargs,
    ):
        """Initialize cache factory."""
        self.backend = backend.lower()
        self.host = host
        self.port = port or self._default_port()
        self.extra_config = kwargs

    def _default_port(self) -> int:
        """Get default port for backend."""
        return {"redis": 6379, "memcached": 11211, "memory": None}.get(
            self.backend, 6379
        )

    async def create(self) -> Any:
        """Create cache client."""
        if self.backend == "redis":
            return await self._create_redis_client()
        elif self.backend == "memcached":
            return await self._create_memcached_client()
        elif self.backend == "memory":
            return self._create_memory_cache()
        else:
            raise ValueError(f"Unsupported cache backend: {self.backend}")

    async def _create_redis_client(self):
        """Create Redis client."""
        try:
            import redis.asyncio as aioredis
        except ImportError:
            try:
                import aioredis
            except ImportError:
                raise ImportError(
                    "redis or aioredis is required. "
                    "Install with: pip install redis[async] or pip install aioredis"
                )

        logger.info(f"Creating Redis client: {self.host}:{self.port}")

        return await aioredis.from_url(
            f"redis://{self.host}:{self.port}", **self.extra_config
        )

    async def _create_memcached_client(self):
        """Create Memcached client."""
        try:
            import aiomemcache
        except ImportError:
            raise ImportError(
                "aiomemcache is required. " "Install with: pip install aiomemcache"
            )

        logger.info(f"Creating Memcached client: {self.host}:{self.port}")

        client = aiomemcache.Client(self.host, self.port)
        await client.connect()
        return client

    def _create_memory_cache(self):
        """Create in-memory cache."""
        logger.info("Creating in-memory cache")

        class MemoryCache:
            """Simple in-memory cache implementation."""

            def __init__(self):
                self._cache = {}

            async def get(self, key: str) -> Any:
                return self._cache.get(key)

            async def set(self, key: str, value: Any, ttl: int = None) -> None:
                self._cache[key] = value
                # TODO: Implement expiration

            async def delete(self, key: str) -> None:
                self._cache.pop(key, None)

            async def clear(self) -> None:
                self._cache.clear()

        return MemoryCache()

    def get_config(self) -> Dict[str, Any]:
        """Get factory configuration."""
        config = {"backend": self.backend, "host": self.host, "port": self.port}
        config.update(self.extra_config)
        return config


class MessageQueueFactory(ResourceFactory):
    """
    Factory for creating message queue clients.

    Supports:
    - RabbitMQ (aio-pika)
    - Kafka (aiokafka)
    - Redis Pub/Sub

    Example:
        ```python
        factory = MessageQueueFactory(
            backend='rabbitmq',
            host='localhost',
            port=5672,
            username='guest',
            password='guest'
        )
        ```
    """

    def __init__(
        self,
        backend: str = "rabbitmq",
        host: str = "localhost",
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        **kwargs,
    ):
        """Initialize message queue factory."""
        self.backend = backend.lower()
        self.host = host
        self.port = port or self._default_port()
        self.username = username
        self.password = password
        self.extra_config = kwargs

    def _default_port(self) -> int:
        """Get default port for backend."""
        return {"rabbitmq": 5672, "kafka": 9092, "redis": 6379}.get(self.backend, 5672)

    async def create(self) -> Any:
        """Create message queue client."""
        if self.backend == "rabbitmq":
            return await self._create_rabbitmq_client()
        elif self.backend == "kafka":
            return await self._create_kafka_client()
        elif self.backend == "redis":
            return await self._create_redis_pubsub()
        else:
            raise ValueError(f"Unsupported message queue backend: {self.backend}")

    async def _create_rabbitmq_client(self):
        """Create RabbitMQ client."""
        try:
            import aio_pika
        except ImportError:
            raise ImportError(
                "aio-pika is required for RabbitMQ. "
                "Install with: pip install aio-pika"
            )

        logger.info(f"Creating RabbitMQ connection: {self.host}:{self.port}")

        url = f"amqp://{self.username}:{self.password}@{self.host}:{self.port}/"

        return await aio_pika.connect_robust(url, **self.extra_config)

    async def _create_kafka_client(self):
        """Create Kafka producer/consumer."""
        try:
            from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
        except ImportError:
            raise ImportError(
                "aiokafka is required for Kafka. " "Install with: pip install aiokafka"
            )

        logger.info(f"Creating Kafka client: {self.host}:{self.port}")

        # Return both producer and consumer
        producer = AIOKafkaProducer(
            bootstrap_servers=f"{self.host}:{self.port}", **self.extra_config
        )

        consumer = AIOKafkaConsumer(
            bootstrap_servers=f"{self.host}:{self.port}", **self.extra_config
        )

        await producer.start()
        await consumer.start()

        class KafkaClient:
            def __init__(self, producer, consumer):
                self.producer = producer
                self.consumer = consumer

            async def close(self):
                await self.producer.stop()
                await self.consumer.stop()

        return KafkaClient(producer, consumer)

    async def _create_redis_pubsub(self):
        """Create Redis Pub/Sub client."""
        # Reuse cache factory for Redis
        cache_factory = CacheFactory(
            backend="redis", host=self.host, port=self.port, **self.extra_config
        )
        return await cache_factory.create()

    def get_config(self) -> Dict[str, Any]:
        """Get factory configuration."""
        config = {
            "backend": self.backend,
            "host": self.host,
            "port": self.port,
            "username": self.username,
        }
        config.update(self.extra_config)
        # Don't include password
        return {k: v for k, v in config.items() if k != "password"}
