"""Configuration for user management integration tests."""

import asyncio

import pytest
import pytest_asyncio

from tests.utils.docker_config import ensure_docker_services


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def check_docker_services():
    """Ensure Docker services are available before running tests."""
    services_ok = await ensure_docker_services()
    if not services_ok:
        pytest.skip(
            "Docker services not available. Please ensure PostgreSQL, Redis, and Ollama are running."
        )
