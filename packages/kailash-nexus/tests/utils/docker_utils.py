"""
Docker Test Environment Utilities for Nexus Testing

This module provides Docker-based test environment setup for integration and E2E tests.
Uses the main SDK Docker configuration but with app-specific test configurations.
"""

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

# Add the main SDK tests utils to path for importing configurations
sdk_tests_path = Path(__file__).parent.parent.parent.parent / "tests" / "utils"
sys.path.insert(0, str(sdk_tests_path))

try:
    from docker_config import (
        DATABASE_CONFIG,
        OLLAMA_CONFIG,
        REDIS_CONFIG,
        ensure_docker_services,
        get_postgres_connection_string,
        get_redis_url,
        is_docker_available,
        is_ollama_available,
        is_postgres_available,
        is_redis_available,
    )
except ImportError:
    # Fallback configuration if main SDK docker_config is not available
    DATABASE_CONFIG = {
        "host": "localhost",
        "port": 5434,
        "database": "kailash_test",
        "user": "test_user",
        "password": "test_password",
    }

    REDIS_CONFIG = {
        "host": "localhost",
        "port": 6380,
    }

    OLLAMA_CONFIG = {
        "host": "localhost",
        "port": 11435,
        "base_url": "http://localhost:11435",
    }

    def get_postgres_connection_string():
        return "postgresql://test_user:test_password@localhost:5434/kailash_test"

    def get_redis_url():
        return "redis://localhost:6380"

    def is_docker_available():
        try:
            result = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
            return result.returncode == 0
        except:
            return False

    def is_postgres_available():
        try:
            import psycopg2

            conn = psycopg2.connect(
                host="localhost",
                port=5434,
                database="kailash_test",
                user="test_user",
                password="test_password",
                connect_timeout=3,
            )
            conn.close()
            return True
        except:
            return False

    def is_redis_available():
        try:
            import redis

            r = redis.Redis(host="localhost", port=6380, socket_connect_timeout=3)
            r.ping()
            return True
        except:
            return False

    def is_ollama_available():
        try:
            import requests

            response = requests.get("http://localhost:11435/api/tags", timeout=3)
            return response.status_code == 200
        except:
            return False

    async def ensure_docker_services():
        return is_postgres_available() and is_redis_available()


class DockerTestEnvironment:
    """Docker-based test environment for Nexus integration and E2E tests."""

    def __init__(self, services: Optional[list] = None):
        """
        Initialize Docker test environment.

        Args:
            services: List of services to manage ['postgres', 'redis', 'ollama']
                     If None, defaults to ['postgres', 'redis']
        """
        self.services = services or ["postgres", "redis"]
        self.docker_compose_file = self._get_docker_compose_file()
        self.container_prefix = "nexus_test"

    def _get_docker_compose_file(self) -> str:
        """Get the Docker Compose file path."""
        # Try to use the main SDK docker-compose file
        sdk_compose = (
            Path(__file__).parent.parent.parent.parent
            / "tests"
            / "utils"
            / "docker-compose.test.yml"
        )
        if sdk_compose.exists():
            return str(sdk_compose)

        # Fallback to a minimal compose file path
        local_compose = Path(__file__).parent / "docker-compose.nexus-test.yml"
        return str(local_compose)

    async def start(self) -> bool:
        """Start the test environment services."""
        if not is_docker_available():
            print("Docker is not available - skipping service startup")
            return False

        try:
            # Start requested services
            cmd = [
                "docker-compose",
                "-f",
                self.docker_compose_file,
                "up",
                "-d",
            ] + self.services
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode != 0:
                print(f"Failed to start services: {result.stderr}")
                return False

            # Wait for services to be ready
            await self._wait_for_services()
            return True

        except Exception as e:
            print(f"Error starting Docker services: {e}")
            return False

    async def stop(self) -> bool:
        """Stop the test environment services."""
        try:
            cmd = ["docker-compose", "-f", self.docker_compose_file, "down"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return result.returncode == 0
        except Exception as e:
            print(f"Error stopping Docker services: {e}")
            return False

    async def _wait_for_services(self, timeout: int = 30) -> bool:
        """Wait for services to become available."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            all_ready = True

            if "postgres" in self.services and not is_postgres_available():
                all_ready = False

            if "redis" in self.services and not is_redis_available():
                all_ready = False

            if "ollama" in self.services and not is_ollama_available():
                all_ready = False

            if all_ready:
                return True

            await asyncio.sleep(1)

        return False

    def get_postgres_config(self) -> Dict[str, Any]:
        """Get PostgreSQL connection configuration."""
        return DATABASE_CONFIG.copy()

    def get_redis_config(self) -> Dict[str, Any]:
        """Get Redis connection configuration."""
        return REDIS_CONFIG.copy()

    def get_ollama_config(self) -> Dict[str, Any]:
        """Get Ollama connection configuration."""
        return OLLAMA_CONFIG.copy()

    async def is_healthy(self) -> bool:
        """Check if all requested services are healthy."""
        try:
            if "postgres" in self.services and not is_postgres_available():
                return False

            if "redis" in self.services and not is_redis_available():
                return False

            if "ollama" in self.services and not is_ollama_available():
                return False

            return True
        except Exception:
            return False

    async def reset_data(self) -> bool:
        """Reset test data in all services."""
        try:
            # Reset PostgreSQL test data
            if "postgres" in self.services and is_postgres_available():
                await self._reset_postgres_data()

            # Reset Redis data
            if "redis" in self.services and is_redis_available():
                await self._reset_redis_data()

            return True
        except Exception as e:
            print(f"Error resetting test data: {e}")
            return False

    async def _reset_postgres_data(self):
        """Reset PostgreSQL test database."""
        try:
            import asyncpg

            conn = await asyncpg.connect(get_postgres_connection_string())

            # Get all tables and truncate them
            tables = await conn.fetch(
                """
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public' AND tablename NOT LIKE 'pg_%'
            """
            )

            for table in tables:
                await conn.execute(f'TRUNCATE TABLE "{table["tablename"]}" CASCADE')

            await conn.close()
        except Exception as e:
            print(f"Warning: Could not reset PostgreSQL data: {e}")

    async def _reset_redis_data(self):
        """Reset Redis test data."""
        try:
            import redis.asyncio as redis

            r = redis.Redis(host=REDIS_CONFIG["host"], port=REDIS_CONFIG["port"])
            await r.flushdb()
            await r.aclose()
        except Exception as e:
            print(f"Warning: Could not reset Redis data: {e}")


class NexusTestBase:
    """Base class for Nexus tests requiring Docker services."""

    def __init__(self):
        self.docker_env = None

    async def setup_test_environment(self, services: Optional[list] = None):
        """Set up the test environment before tests."""
        self.docker_env = DockerTestEnvironment(services)

        # Start services if they're not already running
        if not await self.docker_env.is_healthy():
            success = await self.docker_env.start()
            if not success:
                raise RuntimeError("Failed to start test environment")

        # Reset data for clean test state
        await self.docker_env.reset_data()

    async def teardown_test_environment(self):
        """Clean up the test environment after tests."""
        if self.docker_env:
            # Don't stop services - let them run for other tests
            # Just reset data
            await self.docker_env.reset_data()


# Pytest fixtures for easy use in tests
def pytest_docker_environment(services=None):
    """Pytest fixture factory for Docker test environment."""
    import pytest

    @pytest.fixture(scope="function")
    async def docker_environment():
        env = DockerTestEnvironment(services)

        # Start if not healthy
        if not await env.is_healthy():
            await env.start()

        # Reset data for clean state
        await env.reset_data()

        yield env

        # Reset data after test
        await env.reset_data()

    return docker_environment


# Skip decorators for integration/E2E tests
def skip_if_no_docker():
    """Skip test if Docker is not available."""
    import pytest

    return pytest.mark.skipif(not is_docker_available(), reason="Docker not available")


def skip_if_no_postgres():
    """Skip test if PostgreSQL is not available."""
    import pytest

    return pytest.mark.skipif(
        not is_postgres_available(), reason="PostgreSQL not available"
    )


def skip_if_no_redis():
    """Skip test if Redis is not available."""
    import pytest

    return pytest.mark.skipif(not is_redis_available(), reason="Redis not available")


def skip_if_no_ollama():
    """Skip test if Ollama is not available."""
    import pytest

    return pytest.mark.skipif(not is_ollama_available(), reason="Ollama not available")


# Main Docker environment instance for module-level use
_global_docker_env = None


def get_docker_environment(services=None):
    """Get or create a global Docker environment instance."""
    global _global_docker_env
    if _global_docker_env is None:
        _global_docker_env = DockerTestEnvironment(services)
    return _global_docker_env
