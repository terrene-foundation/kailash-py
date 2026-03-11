"""
Docker infrastructure configuration for Kaizen framework integration testing.

Adapts Kailash Core SDK docker test infrastructure for Kaizen-specific requirements.
Provides real infrastructure services for Tier 2 (Integration) and Tier 3 (E2E) testing.

Based on Kailash test-env infrastructure with locked-in port configuration:
- PostgreSQL: 5434 (enterprise data persistence)
- Redis: 6380 (memory and caching)
- Ollama: 11435 (real AI model testing)
- MySQL: 3307 (alternative database testing)
- MongoDB: 27017 (document storage)
"""

import asyncio
import logging
import os
import subprocess
import time
from typing import Dict, List

import asyncpg
import pymongo
import redis
import requests

logger = logging.getLogger(__name__)

# Service configurations adapted from Kailash Core SDK
DATABASE_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5434")),
    "database": os.getenv("DB_NAME", "kailash_test"),
    "user": os.getenv("DB_USER", "test_user"),
    "password": os.getenv("DB_PASSWORD", "test_password"),
}

REDIS_CONFIG = {
    "host": os.getenv("REDIS_HOST", "localhost"),
    "port": int(os.getenv("REDIS_PORT", "6380")),
}

OLLAMA_CONFIG = {
    "host": os.getenv("OLLAMA_HOST", "localhost"),
    "port": int(os.getenv("OLLAMA_PORT", "11435")),
    "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11435"),
}

MONGODB_CONFIG = {
    "host": os.getenv("MONGO_HOST", "localhost"),
    "port": int(os.getenv("MONGO_PORT", "27017")),
    "username": os.getenv("MONGO_USER", "kailash"),
    "password": os.getenv("MONGO_PASSWORD", "kailash123"),
}

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", "3307")),
    "database": os.getenv("MYSQL_DATABASE", "kailash_test"),
    "user": os.getenv("MYSQL_USER", "kailash_test"),
    "password": os.getenv("MYSQL_PASSWORD", "test_password"),
}

JAEGER_CONFIG = {
    "host": os.getenv("JAEGER_HOST", "localhost"),
    "ui_port": int(os.getenv("JAEGER_UI_PORT", "16686")),
    "grpc_port": int(os.getenv("JAEGER_GRPC_PORT", "4317")),
    "http_port": int(os.getenv("JAEGER_HTTP_PORT", "4318")),
    "base_url": os.getenv("JAEGER_BASE_URL", "http://localhost:16686"),
}


class DockerServicesManager:
    """Manages Docker services for integration testing following Kailash patterns."""

    def __init__(self):
        self.required_services = [
            "postgresql",
            "redis",
        ]  # Minimum for integration tests
        self.enterprise_services = [
            "postgresql",
            "redis",
            "ollama",
            "mongodb",
        ]  # For E2E tests
        self.service_health_timeout = 30  # seconds

    async def check_service_health(self, service: str) -> bool:
        """Check if a specific service is healthy and accessible."""
        try:
            if service == "postgresql":
                return await self._check_postgresql()
            elif service == "redis":
                return await self._check_redis()
            elif service == "ollama":
                return await self._check_ollama()
            elif service == "mongodb":
                return await self._check_mongodb()
            elif service == "mysql":
                return await self._check_mysql()
            elif service == "jaeger":
                return await self._check_jaeger()
            else:
                logger.warning(f"Unknown service: {service}")
                return False
        except Exception as e:
            logger.debug(f"Health check failed for {service}: {e}")
            return False

    async def _check_postgresql(self) -> bool:
        """Check PostgreSQL health using asyncpg."""
        try:
            conn = await asyncpg.connect(
                host=DATABASE_CONFIG["host"],
                port=DATABASE_CONFIG["port"],
                database=DATABASE_CONFIG["database"],
                user=DATABASE_CONFIG["user"],
                password=DATABASE_CONFIG["password"],
                timeout=5.0,
            )
            result = await conn.fetchval("SELECT 1")
            await conn.close()
            return result == 1
        except Exception as e:
            logger.debug(f"PostgreSQL health check failed: {e}")
            return False

    async def _check_redis(self) -> bool:
        """Check Redis health."""
        try:
            r = redis.Redis(
                host=REDIS_CONFIG["host"],
                port=REDIS_CONFIG["port"],
                socket_timeout=5,
                socket_connect_timeout=5,
            )
            return r.ping()
        except Exception as e:
            logger.debug(f"Redis health check failed: {e}")
            return False

    async def _check_ollama(self) -> bool:
        """Check Ollama health via HTTP API."""
        try:
            response = requests.get(f"{OLLAMA_CONFIG['base_url']}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Ollama health check failed: {e}")
            return False

    async def _check_mongodb(self) -> bool:
        """Check MongoDB health."""
        try:
            client = pymongo.MongoClient(
                host=MONGODB_CONFIG["host"],
                port=MONGODB_CONFIG["port"],
                username=MONGODB_CONFIG["username"],
                password=MONGODB_CONFIG["password"],
                serverSelectionTimeoutMS=5000,
            )
            client.server_info()
            client.close()
            return True
        except Exception as e:
            logger.debug(f"MongoDB health check failed: {e}")
            return False

    async def _check_mysql(self) -> bool:
        """Check MySQL health."""
        try:
            # Using subprocess to avoid additional MySQL dependencies
            import mysql.connector

            conn = mysql.connector.connect(
                host=MYSQL_CONFIG["host"],
                port=MYSQL_CONFIG["port"],
                database=MYSQL_CONFIG["database"],
                user=MYSQL_CONFIG["user"],
                password=MYSQL_CONFIG["password"],
                connection_timeout=5,
            )
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            return result[0] == 1
        except ImportError:
            # If mysql-connector-python is not available, skip MySQL checks
            logger.debug("MySQL connector not available, skipping health check")
            return True
        except Exception as e:
            logger.debug(f"MySQL health check failed: {e}")
            return False

    async def _check_jaeger(self) -> bool:
        """Check Jaeger health via HTTP API."""
        try:
            response = requests.get(
                f"http://{JAEGER_CONFIG['host']}:{JAEGER_CONFIG['ui_port']}", timeout=5
            )
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Jaeger health check failed: {e}")
            return False

    def check_docker_availability(self) -> bool:
        """Check if Docker is available and running."""
        try:
            result = subprocess.run(["docker", "ps"], capture_output=True, timeout=10)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Docker availability check failed: {e}")
            return False

    def check_kailash_test_env(self) -> bool:
        """Check if Kailash test-env script is available."""
        kailash_root = os.path.join(os.path.dirname(__file__), "../../../..")
        test_env_path = os.path.join(kailash_root, "tests/utils/test-env")
        return os.path.isfile(test_env_path) and os.access(test_env_path, os.X_OK)

    async def start_services(self, services: List[str] = None) -> bool:
        """Start Docker services using Kailash test-env infrastructure."""
        services = services or self.required_services

        if not self.check_docker_availability():
            logger.error("Docker is not available")
            return False

        try:
            # Use Kailash test-env to start services
            kailash_root = os.path.join(os.path.dirname(__file__), "../../../..")
            test_env_path = os.path.join(kailash_root, "tests/utils/test-env")

            if self.check_kailash_test_env():
                result = subprocess.run([test_env_path, "up"], timeout=120)
                if result.returncode != 0:
                    logger.error("Failed to start services with test-env")
                    return False
            else:
                # Fallback to docker-compose
                docker_compose_path = os.path.join(
                    kailash_root, "tests/utils/docker-compose.test.yml"
                )
                if os.path.isfile(docker_compose_path):
                    result = subprocess.run(
                        ["docker-compose", "-f", docker_compose_path, "up", "-d"],
                        timeout=120,
                    )
                    if result.returncode != 0:
                        logger.error("Failed to start services with docker-compose")
                        return False
                else:
                    logger.error("Neither test-env nor docker-compose.test.yml found")
                    return False

            # Wait for services to be healthy
            await self.wait_for_services_healthy(services)
            return True

        except Exception as e:
            logger.error(f"Failed to start services: {e}")
            return False

    async def wait_for_services_healthy(self, services: List[str]) -> bool:
        """Wait for specified services to become healthy."""
        start_time = time.time()

        while time.time() - start_time < self.service_health_timeout:
            all_healthy = True
            for service in services:
                if not await self.check_service_health(service):
                    all_healthy = False
                    break

            if all_healthy:
                logger.info(f"All services healthy: {services}")
                return True

            await asyncio.sleep(2)

        logger.error(f"Timeout waiting for services to become healthy: {services}")
        return False


# Global instance for easy access
_docker_manager = DockerServicesManager()


async def ensure_docker_services(
    services: List[str] = None, enterprise_mode: bool = False
) -> bool:
    """
    Ensure Docker services are available for integration testing.

    Args:
        services: List of services to check/start. Defaults to required services.
        enterprise_mode: If True, checks enterprise services (includes Ollama, MongoDB)

    Returns:
        bool: True if all services are healthy and available

    Usage:
        # Basic integration testing
        services_ready = await ensure_docker_services()

        # Enterprise E2E testing
        services_ready = await ensure_docker_services(enterprise_mode=True)
    """
    if enterprise_mode:
        services = services or _docker_manager.enterprise_services
    else:
        services = services or _docker_manager.required_services

    logger.info(f"Checking Docker services: {services}")

    # First check if services are already healthy
    all_healthy = True
    for service in services:
        if not await _docker_manager.check_service_health(service):
            all_healthy = False
            break

    if all_healthy:
        logger.info("All Docker services already healthy")
        return True

    # Try to start services if they're not healthy
    logger.info("Starting Docker services...")
    return await _docker_manager.start_services(services)


def get_postgres_connection_string(database: str = None) -> str:
    """Get PostgreSQL connection string for tests."""
    db = database or DATABASE_CONFIG["database"]
    return (
        f"postgresql://{DATABASE_CONFIG['user']}:{DATABASE_CONFIG['password']}"
        f"@{DATABASE_CONFIG['host']}:{DATABASE_CONFIG['port']}/{db}"
    )


def get_redis_url() -> str:
    """Get Redis URL for tests."""
    return f"redis://{REDIS_CONFIG['host']}:{REDIS_CONFIG['port']}"


def get_ollama_base_url() -> str:
    """Get Ollama base URL for tests."""
    return OLLAMA_CONFIG["base_url"]


def get_mongodb_connection_string(database: str = "kaizen_test") -> str:
    """Get MongoDB connection string for tests."""
    return (
        f"mongodb://{MONGODB_CONFIG['username']}:{MONGODB_CONFIG['password']}"
        f"@{MONGODB_CONFIG['host']}:{MONGODB_CONFIG['port']}/{database}"
    )


# Connection configuration helpers for tests
def get_test_db_config() -> Dict:
    """Get database configuration for test fixtures."""
    return DATABASE_CONFIG.copy()


def get_test_redis_config() -> Dict:
    """Get Redis configuration for test fixtures."""
    return REDIS_CONFIG.copy()


def get_test_ollama_config() -> Dict:
    """Get Ollama configuration for test fixtures."""
    return OLLAMA_CONFIG.copy()


# Health check functions for individual use
async def check_postgresql_health() -> bool:
    """Check if PostgreSQL is healthy."""
    return await _docker_manager.check_service_health("postgresql")


async def check_redis_health() -> bool:
    """Check if Redis is healthy."""
    return await _docker_manager.check_service_health("redis")


async def check_ollama_health() -> bool:
    """Check if Ollama is healthy."""
    return await _docker_manager.check_service_health("ollama")


async def check_jaeger_health() -> bool:
    """Check if Jaeger is healthy."""
    return await _docker_manager.check_service_health("jaeger")


def is_jaeger_available() -> bool:
    """Check if Jaeger is available (synchronous wrapper)."""
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(check_jaeger_health())


def get_jaeger_config() -> Dict:
    """Get Jaeger configuration for test fixtures."""
    return JAEGER_CONFIG.copy()


# Convenience function for skipping tests when services are not available
def require_docker_services(services: List[str] = None):
    """
    Decorator to skip tests when Docker services are not available.

    Usage:
        @require_docker_services()
        def test_with_postgres():
            # Test code that requires PostgreSQL and Redis
            pass

        @require_docker_services(['postgresql', 'redis', 'ollama'])
        def test_with_ai():
            # Test code that requires AI services
            pass
    """
    import pytest

    def decorator(func):
        async def wrapper(*args, **kwargs):
            if not await ensure_docker_services(services):
                pytest.skip("Required Docker services not available")
            return (
                await func(*args, **kwargs)
                if asyncio.iscoroutinefunction(func)
                else func(*args, **kwargs)
            )

        return wrapper

    return decorator
