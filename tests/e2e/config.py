"""
E2E Test Configuration

Centralized configuration for all E2E tests to ensure consistency.
"""

import os
from typing import Any, Dict


class E2ETestConfig:
    """Configuration for E2E tests."""

    # Database configuration
    DATABASE = {
        "host": os.getenv("TEST_DB_HOST", "localhost"),
        "port": int(os.getenv("TEST_DB_PORT", "5434")),
        "database": os.getenv("TEST_DB_NAME", "kailash_test"),
        "user": os.getenv("TEST_DB_USER", "test_user"),
        "password": os.getenv("TEST_DB_PASSWORD", "test_password"),
    }

    # Ollama configuration
    OLLAMA = {
        "host": os.getenv("OLLAMA_HOST", "http://localhost:11435"),
        "model": os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
        "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11435"),
    }

    # Redis configuration
    REDIS = {
        "host": os.getenv("REDIS_HOST", "localhost"),
        "port": int(os.getenv("REDIS_PORT", "6379")),
        "db": int(os.getenv("REDIS_DB", "0")),
    }

    # Test data prefixes to ensure isolation
    TEST_DATA_PREFIX = "test_"

    # Timeouts
    DEFAULT_TIMEOUT = 30.0
    GATEWAY_STARTUP_TIMEOUT = 10.0

    @classmethod
    def get_db_connection_string(cls) -> str:
        """Get PostgreSQL connection string."""
        db = cls.DATABASE
        return f"postgresql://{db['user']}:{db['password']}@{db['host']}:{db['port']}/{db['database']}"

    @classmethod
    def get_async_db_code(
        cls, operation: str = "# Your database operations here"
    ) -> str:
        """Generate AsyncPythonCodeNode code for database operations."""
        return f"""
import asyncpg
import json
from datetime import datetime, timezone

# Connect to database
conn = await asyncpg.connect(
    host="{cls.DATABASE['host']}",
    port={cls.DATABASE['port']},
    database="{cls.DATABASE['database']}",
    user="{cls.DATABASE['user']}",
    password="{cls.DATABASE['password']}"
)

try:
    {operation}
finally:
    await conn.close()
"""

    @classmethod
    def get_test_customer_id(cls, index: int = 0) -> str:
        """Get a consistent test customer ID."""
        return f"{cls.TEST_DATA_PREFIX}cust_{index:04d}"

    @classmethod
    def get_test_product_id(cls, index: int = 0) -> str:
        """Get a consistent test product ID."""
        return f"{cls.TEST_DATA_PREFIX}prod_{index:04d}"

    @classmethod
    def get_test_order_id(cls) -> str:
        """Generate a test order ID."""
        import uuid

        return f"{cls.TEST_DATA_PREFIX}ord_{uuid.uuid4().hex[:8]}"
