"""
Pytest configuration for orchestration integration tests.

PATTERN: Async session-scope fixture for StateManager initialization.
This ensures StateManager is created in async context, matching test execution context.

DataFlow Async Fix History:
- v0.9.4: Partial fix - ConnectionManagerAdapter async context detection added
- v0.9.5: Complete fix - MigrationHistoryManager async context detection added
- Status: ✅ RESOLVED - Both components now detect async context correctly

Critical Pattern:
- StateManager MUST be created in async context (with event loop)
- DataFlow detects event loop at initialization time
- If created in sync context (pytest_configure), uses LocalRuntime
- If used in async tests, LocalRuntime blocks on thread.join() → deadlock

Solution:
- Use @pytest_asyncio.fixture(scope="session") instead of pytest_configure()
- Lazy initialization with asyncio.Lock() for thread safety
- DataFlow v0.9.5+ correctly detects async context → AsyncLocalRuntime
"""

import asyncio
import os
import tempfile

import pytest
import pytest_asyncio
from dotenv import load_dotenv

# Load .env BEFORE defining fixtures (module import time)
load_dotenv()


def _get_database_url() -> str:
    """
    Helper to get database URL for both sync and async contexts.

    Returns:
        PostgreSQL URL from POSTGRES_URL env var, or SQLite temp file
    """
    postgres_url = os.getenv("POSTGRES_URL")
    return (
        postgres_url
        if postgres_url
        else f"sqlite:///{tempfile.gettempdir()}/test_orchestration_state.db"
    )


@pytest_asyncio.fixture(scope="function")
async def state_manager():
    """
    Function-scope StateManager fixture initialized in async context.

    Pattern:
    1. Fresh StateManager instance per test (with fresh AsyncLocalRuntime)
    2. Async fixture ensures event loop exists during initialization
    3. ConnectionManagerAdapter correctly detects async context
    4. AsyncLocalRuntime gets fresh event loop for each test

    This prevents the "Event loop is closed" error when reusing StateManager
    across tests. Each test gets a fresh runtime tied to its own event loop.

    Yields:
        OrchestrationStateManager instance (function-scoped, async-initialized)

    Reference:
        AsyncLocalRuntime event loop binding pattern
        Issue: Session-scoped runtime captures first test's event loop
    """
    from kaizen.orchestration.state_manager import OrchestrationStateManager

    from tests.integration.orchestration.manual_table_creation import (
        initialize_orchestration_tables,
    )

    db_url = _get_database_url()

    # ✅ Manual table creation (only needed once per session, idempotent)
    # Tables already exist after first test, this is a no-op
    initialize_orchestration_tables(db_url)

    # ✅ Create fresh StateManager with fresh AsyncLocalRuntime for each test
    # This ensures each test gets a runtime bound to its own event loop
    state_mgr = OrchestrationStateManager(
        connection_string=db_url,
        db_instance_name="test_orchestration_db",
        auto_migrate=False,  # ✅ WORKAROUND: Bypass MigrationHistoryManager bug
        migration_enabled=False,  # ✅ WORKAROUND: Disable migration system entirely
    )

    yield state_mgr

    # ✅ Cleanup connection pools to prevent "Event loop is closed" errors
    # DataFlow connection pools retain references to event loops
    # Without cleanup, next test reuses pools bound to closed loop
    try:
        await state_mgr.db.cleanup_all_pools()
    except Exception as e:
        print(f"⚠️ Connection pool cleanup warning: {e}")


@pytest_asyncio.fixture(scope="session")
async def test_database_url():
    """
    Database URL for integration tests.

    Returns PostgreSQL URL from POSTGRES_URL environment variable if set,
    otherwise defaults to SQLite in temp directory.
    """
    return _get_database_url()


@pytest.fixture(scope="session", autouse=True)
def cleanup_database():
    """
    Cleanup database after all tests complete.

    Auto-use fixture that runs after all tests in the session.
    Removes SQLite test database if present.
    """
    yield

    # Cleanup logic (runs after all tests)
    db_url = _get_database_url()
    if "sqlite" in db_url:
        import os

        db_path = db_url.replace("sqlite:///", "")
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
                print(f"\n✅ Test database cleaned up: {db_path}")
            except Exception as e:
                print(f"\n⚠️ Failed to cleanup test database: {e}")
