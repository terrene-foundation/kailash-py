"""
Docker Test Manager for Integration Tests

Provides real Docker infrastructure management for testing.
NO MOCKING - uses actual Docker services.
"""

import asyncio
import subprocess
import time
from typing import Any, Dict, Optional

import psycopg2
import redis

from .docker_config import DATABASE_CONFIG, REDIS_CONFIG


class DockerTestManager:
    """
    Manages Docker test infrastructure for integration tests.

    This is a real infrastructure manager - NO MOCKING.
    Uses actual Docker containers on dedicated test ports.
    """

    def __init__(self):
        self.postgres_config = DATABASE_CONFIG
        self.redis_config = REDIS_CONFIG
        self.services_started = False

    async def start_services(self) -> bool:
        """Start Docker test services."""
        try:
            # Services should already be running via test-env
            # Just verify they're accessible
            await self.wait_for_postgres()
            await self.wait_for_redis()
            self.services_started = True
            return True
        except Exception as e:
            print(f"Failed to connect to test services: {e}")
            return False

    async def stop_services(self) -> None:
        """Stop Docker test services (no-op, managed externally)."""
        # Services are managed by test-env script
        self.services_started = False

    async def wait_for_postgres(self, timeout: int = 30) -> bool:
        """Wait for PostgreSQL to be ready."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                conn = psycopg2.connect(
                    host=self.postgres_config["host"],
                    port=self.postgres_config["port"],
                    database=self.postgres_config["database"],
                    user=self.postgres_config["user"],
                    password=self.postgres_config["password"],
                )
                conn.close()
                return True
            except psycopg2.OperationalError:
                await asyncio.sleep(0.5)
        return False

    async def wait_for_redis(self, timeout: int = 30) -> bool:
        """Wait for Redis to be ready."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                r = redis.Redis(
                    host=self.redis_config["host"],
                    port=self.redis_config["port"],
                    decode_responses=True,
                )
                r.ping()
                r.close()
                return True
            except redis.ConnectionError:
                await asyncio.sleep(0.5)
        return False

    def get_postgres_url(self) -> str:
        """Get PostgreSQL connection URL."""
        return (
            f"postgresql://{self.postgres_config['user']}:"
            f"{self.postgres_config['password']}@"
            f"{self.postgres_config['host']}:"
            f"{self.postgres_config['port']}/"
            f"{self.postgres_config['database']}"
        )

    def get_redis_url(self) -> str:
        """Get Redis connection URL."""
        return f"redis://{self.redis_config['host']}:{self.redis_config['port']}"

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start_services()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop_services()
