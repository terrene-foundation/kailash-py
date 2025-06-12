"""Pytest configuration for test_nodes directory."""

import os
import pytest
import asyncio
import asyncpg


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


async def check_postgres_connection():
    """Check if PostgreSQL is available."""
    try:
        conn = await asyncpg.connect(
            host="localhost",
            port=5432,
            user="kailash",
            password="kailash123",
            database="test_db",
            timeout=5,
        )
        await conn.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
async def postgres_available():
    """Check if PostgreSQL test database is available."""
    return await check_postgres_connection()


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "requires_postgres: mark test as requiring PostgreSQL"
    )
    config.addinivalue_line(
        "markers", "requires_ollama: mark test as requiring Ollama"
    )


def pytest_collection_modifyitems(config, items):
    """Skip tests that require services not available."""
    # Check service availability
    import asyncio
    
    postgres_available = asyncio.run(check_postgres_connection())
    
    skip_postgres = pytest.mark.skip(reason="PostgreSQL not available")
    
    for item in items:
        if "requires_postgres" in item.keywords and not postgres_available:
            item.add_marker(skip_postgres)