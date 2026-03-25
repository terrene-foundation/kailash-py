"""
DataFlow Test Configuration - Standalone Version

Provides fixtures and utilities for DataFlow testing without external dependencies.
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))  # kailash-dataflow/src
sys.path.insert(0, str(Path(__file__).parent.parent))  # packages/kailash-dataflow
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))  # project root
# Add kailash-nexus src for nexus imports
sys.path.insert(
    0, str(Path(__file__).parent.parent.parent / "kailash-nexus" / "src")
)  # kailash-nexus/src

# Set test environment to reduce connection pool usage
os.environ["DATAFLOW_TEST_MODE"] = "true"
os.environ["DATAFLOW_POOL_SIZE"] = "1"
os.environ["DATAFLOW_MAX_OVERFLOW"] = "1"

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow, DataFlowConfig


@pytest.fixture(scope="function")
def event_loop():
    """Create a fresh event loop for each async test to ensure isolation."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    # Ensure the loop is set as the current event loop
    asyncio.set_event_loop(loop)
    yield loop
    # Clean up
    try:
        # Cancel all remaining tasks
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        # Wait for tasks to complete cancellation
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    except Exception:
        pass
    finally:
        loop.close()
        # Reset to None to prevent reuse
        asyncio.set_event_loop(None)


@pytest.fixture(scope="session")
def shared_dataflow_config():
    """Shared DataFlow configuration for E2E tests to prevent connection pool exhaustion."""
    # Use TEST_DATABASE_URL if set, otherwise use the default test database
    database_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://test_user:test_password@localhost:5434/kailash_test",
    )
    return {
        "database_url": database_url,
        "pool_size": int(os.getenv("DATAFLOW_POOL_SIZE", 1)),
        "pool_max_overflow": int(os.getenv("DATAFLOW_MAX_OVERFLOW", 1)),
        "pool_timeout": 30,
        "pool_recycle": 60,  # Aggressive recycling for tests
        "pool_pre_ping": True,  # Verify connections before use
        "echo": False,  # Disable SQL logging
        "monitoring": False,  # Disable monitoring for tests
    }


@pytest.fixture(scope="function", autouse=True)
def cleanup_e2e_database(request):
    """Clean E2E test database after each test."""
    # Only run for E2E tests
    if "e2e/dataflow" in str(request.fspath):
        yield
        # Clean up database to ensure isolation
        try:
            subprocess.run(
                [
                    "psql",
                    os.getenv(
                        "TEST_DATABASE_URL",
                        "postgresql://test_user:test_password@localhost:5434/kailash_test",
                    ),
                    "-c",
                    "DROP SCHEMA public CASCADE; CREATE SCHEMA public;",
                ],
                capture_output=True,
                check=False,
            )
        except Exception:
            # Ignore cleanup errors
            pass
    else:
        yield


@pytest.fixture
def dataflow():
    """Create a DataFlow instance for testing."""
    # Use PostgreSQL for integration tests (shared test infrastructure on port 5434)
    # Allow table creation for tests that need it
    # Disable caching to avoid stale test data
    df = DataFlow(
        database_url=os.getenv(
            "TEST_DATABASE_URL",
            "postgresql://test_user:test_password@localhost:5434/kailash_test",
        ),
        existing_schema_mode=False,  # Allow table creation for tests
        auto_migrate=True,  # Enable auto-migration
        migration_enabled=True,  # Enable migration system
        cache_enabled=False,
    )
    return df


@pytest.fixture
async def clean_database(dataflow):
    """Clean database before and after test."""
    # Setup: Clean database before test
    try:
        # Try to clean up any existing test tables
        await dataflow.cleanup_test_tables()
    except Exception:
        # Ignore cleanup errors during setup
        pass

    yield dataflow

    # Teardown: Clean database after test
    try:
        await dataflow.cleanup_test_tables()
    except Exception:
        # Ignore cleanup errors during teardown
        pass


@pytest.fixture
def workflow_builder():
    """Create a WorkflowBuilder instance."""
    return WorkflowBuilder()


@pytest.fixture
def runtime():
    """Create a LocalRuntime instance with proper cleanup."""
    rt = LocalRuntime()
    yield rt
    rt.close()


@pytest.fixture
def sample_user_model():
    """Create a sample User model."""
    import tempfile

    db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = db_file.name
    db_file.close()

    db = DataFlow(database_url=f"sqlite:///{db_path}")

    @db.model
    class User:
        name: str
        email: str
        active: bool = True

    # Clean up after test
    import atexit
    import os

    atexit.register(lambda: os.unlink(db_path) if os.path.exists(db_path) else None)

    return User, db


@pytest.fixture
def sample_product_model():
    """Create a sample Product model."""
    import tempfile

    db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = db_file.name
    db_file.close()

    db = DataFlow(database_url=f"sqlite:///{db_path}")

    @db.model
    class Product:
        name: str
        price: float
        category: str = "general"

    # Clean up after test
    import atexit
    import os

    atexit.register(lambda: os.unlink(db_path) if os.path.exists(db_path) else None)

    return Product, db


# Test data fixtures
@pytest.fixture
def sample_users():
    """Sample user data for testing."""
    return [
        {"name": "Alice", "email": "alice@example.com", "active": True},
        {"name": "Bob", "email": "bob@example.com", "active": True},
        {"name": "Charlie", "email": "charlie@example.com", "active": False},
    ]


@pytest.fixture
def sample_products():
    """Sample product data for testing."""
    return [
        {"name": "Laptop", "price": 999.99, "category": "electronics"},
        {"name": "Mouse", "price": 29.99, "category": "electronics"},
        {"name": "Coffee", "price": 12.99, "category": "food"},
    ]


# Database configurations for testing
DATABASE_CONFIGS = [
    {
        "id": "postgresql",
        "url": os.getenv(
            "TEST_DATABASE_URL",
            "postgresql://test_user:test_password@localhost:5434/kailash_test",
        ),
        "type": "postgresql",
    },
    {"id": "sqlite_memory", "url": ":memory:", "type": "sqlite"},
    {
        "id": "sqlite_file",
        "url": f"sqlite:///tmp/dataflow_test_{int(__import__('time').time())}_{__import__('random').randint(1000, 9999)}.db",
        "type": "sqlite",
    },
]

# Legacy config for backward compatibility
TEST_DATABASE_CONFIG = {
    "postgresql": {
        "database_url": os.getenv(
            "TEST_DATABASE_URL",
            "postgresql://test_user:test_password@localhost:5434/kailash_test",
        ),
    },
    "mysql": {
        "database_url": os.getenv(
            "TEST_MYSQL_URL",
            "mysql+pymysql://test_user:test_password@localhost:3307/kailash_test",
        ),
    },
    "sqlite": {
        "database_url": "sqlite:///test_database.db",
    },
}


@pytest.fixture
def db_config():
    """Fixture to provide database configuration for parameterized tests."""
    return DATABASE_CONFIGS


@pytest.fixture
def test_database_url(request):
    """Get database URL based on test parameter."""
    # Always use the shared SDK Docker PostgreSQL for consistency
    # This prevents port conflicts and ensures all tests use the same infrastructure
    return "postgresql://test_user:test_password@localhost:5434/kailash_test"


@pytest.fixture
async def postgres_connection(test_database_url):
    """Create PostgreSQL connection using shared SDK Docker infrastructure."""
    import asyncpg

    # Use shared SDK Docker PostgreSQL
    connection = await asyncpg.connect(
        host="localhost",
        port=5434,
        user="test_user",
        password="test_password",
        database="kailash_test",
    )

    yield connection
    await connection.close()


@pytest.fixture(scope="function")
def standard_dataflow_config():
    """Standard DataFlow configuration for all integration tests.

    This fixture provides a consistent configuration that works with the
    shared SDK Docker infrastructure and ensures all tests use the same setup.
    """
    return {
        "database_url": "postgresql://test_user:test_password@localhost:5434/kailash_test",
        "existing_schema_mode": True,  # Don't drop/recreate tables
        "auto_migrate": False,  # No migrations in tests
        "cache_enabled": False,  # Disable caching for consistent tests
        "pool_size": 1,  # Minimal pool size for tests
        "pool_max_overflow": 0,  # No overflow connections
        "pool_timeout": 10,  # Quick timeout to prevent hangs
        "pool_recycle": 30,  # Very aggressive recycling for tests
        "pool_pre_ping": True,  # Verify connections before use
        "echo": False,  # Disable SQL logging
        "monitoring": False,  # Disable monitoring for tests
    }


@pytest.fixture(scope="function")
async def standard_dataflow(standard_dataflow_config):
    """Standard DataFlow instance for integration tests.

    This fixture provides a clean DataFlow instance with consistent
    configuration and schema setup. All integration tests should use this
    instead of creating their own DataFlow instances.

    Uses DataFlow's built-in connection management for proper cleanup.
    """
    # Create DataFlow with minimal connection pool to prevent exhaustion
    config = standard_dataflow_config.copy()
    config.update(
        {
            "pool_size": 1,  # Minimal pool size
            "pool_max_overflow": 0,  # No overflow connections
            "pool_timeout": 10,  # Quick timeout
            "pool_recycle": 30,  # Aggressive recycling
        }
    )

    # Use DataFlow as context manager for automatic connection cleanup
    with DataFlow(**config) as df:
        # Create a clean schema for the test
        import random
        import time

        test_id = f"{int(time.time())}_{random.randint(1000, 9999)}"

        # Define standard test models that all tests can use
        @df.model
        class TestUser:
            name: str
            email: str
            active: bool = True
            created_at: str = None

        TestUser.__name__ = f"TestUser_{test_id}"
        TestUser.__tablename__ = f"test_users_{test_id}"

        @df.model
        class TestProduct:
            name: str
            price: float
            category: str = "general"
            in_stock: bool = True

        TestProduct.__name__ = f"TestProduct_{test_id}"
        TestProduct.__tablename__ = f"test_products_{test_id}"

        @df.model
        class TestOrder:
            user_id: int
            product_id: int
            quantity: int = 1
            total_price: float = 0.0
            status: str = "pending"

        TestOrder.__name__ = f"TestOrder_{test_id}"
        TestOrder.__tablename__ = f"test_orders_{test_id}"

        # Initialize database connection and create tables
        try:
            await df.initialize()
            df.create_tables()
        except Exception as e:
            # Log but don't fail - tables might already exist
            import logging

            logging.getLogger(__name__).debug(f"Table creation warning: {e}")

        yield df

        # Cleanup: Drop test tables using DataFlow's connection management
        try:
            conn = await df._get_async_database_connection()
            await conn.execute(f"DROP TABLE IF EXISTS test_orders_{test_id} CASCADE")
            await conn.execute(f"DROP TABLE IF EXISTS test_products_{test_id} CASCADE")
            await conn.execute(f"DROP TABLE IF EXISTS test_users_{test_id} CASCADE")
            await conn.close()
        except Exception:
            pass  # Ignore cleanup errors
    # DataFlow context manager automatically calls df.close() here


@pytest.fixture(scope="function")
def standard_test_data():
    """Standard test data for all integration tests."""
    return {
        "users": [
            {"name": "Alice Smith", "email": "alice@example.com", "active": True},
            {"name": "Bob Jones", "email": "bob@example.com", "active": True},
            {"name": "Charlie Brown", "email": "charlie@example.com", "active": False},
        ],
        "products": [
            {
                "name": "Laptop",
                "price": 999.99,
                "category": "electronics",
                "in_stock": True,
            },
            {
                "name": "Mouse",
                "price": 29.99,
                "category": "electronics",
                "in_stock": True,
            },
            {"name": "Coffee", "price": 12.99, "category": "food", "in_stock": False},
        ],
        "orders": [
            {
                "user_id": 1,
                "product_id": 1,
                "quantity": 1,
                "total_price": 999.99,
                "status": "completed",
            },
            {
                "user_id": 2,
                "product_id": 2,
                "quantity": 2,
                "total_price": 59.98,
                "status": "pending",
            },
        ],
    }


@pytest.fixture(scope="function")
def no_mocking_policy():
    """Enforce no-mocking policy for integration tests.

    This fixture serves as a reminder and validator that integration tests
    should use real infrastructure, not mocks.
    """
    import sys
    from unittest.mock import MagicMock, Mock, patch

    # Store original classes
    original_mock = Mock
    original_magic_mock = MagicMock
    original_patch = patch

    def forbidden_mock(*args, **kwargs):
        raise RuntimeError(
            "Mocking is not allowed in integration tests! Use real infrastructure."
        )

    def forbidden_patch(*args, **kwargs):
        raise RuntimeError(
            "Patching/mocking is not allowed in integration tests! Use real infrastructure."
        )

    # Replace Mock classes with forbidden versions
    sys.modules["unittest.mock"].Mock = forbidden_mock
    sys.modules["unittest.mock"].MagicMock = forbidden_mock
    sys.modules["unittest.mock"].patch = forbidden_patch

    yield

    # Restore original classes
    sys.modules["unittest.mock"].Mock = original_mock
    sys.modules["unittest.mock"].MagicMock = original_magic_mock
    sys.modules["unittest.mock"].patch = original_patch


@pytest.fixture
def dataflow_config():
    """Create a DataFlowConfig for integration tests."""
    from dataflow.core.config import DatabaseConfig, DataFlowConfig, Environment

    # Use test database configuration from environment or default
    database_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://test_user:test_password@localhost:5434/kailash_test",
    )

    database_config = DatabaseConfig(
        url=database_url,
        pool_size=10,
        max_overflow=20,
        pool_recycle=3600,
        echo=False,
    )

    config = DataFlowConfig(environment=Environment.TESTING, database=database_config)

    return config


@pytest.fixture
def sample_models():
    """Create sample models for testing."""
    import random
    import time

    def _create_models(dataflow_instance):
        # Use unique names to avoid model registration conflicts
        suffix = f"_{int(time.time())}_{random.randint(1000, 9999)}"

        # Create unique model classes with proper table names
        def create_user_class():
            class User:
                name: str
                email: str
                active: bool = True

            User.__name__ = f"User{suffix}"
            User.__tablename__ = f"users{suffix}"
            return User

        def create_post_class():
            class Post:
                title: str
                content: str
                author_id: int
                published: bool = False

            Post.__name__ = f"Post{suffix}"
            Post.__tablename__ = f"posts{suffix}"
            return Post

        def create_comment_class():
            class Comment:
                content: str
                post_id: int
                author_id: int

            Comment.__name__ = f"Comment{suffix}"
            Comment.__tablename__ = f"comments{suffix}"
            return Comment

        # Register models with DataFlow
        User = dataflow_instance.model(create_user_class())
        Post = dataflow_instance.model(create_post_class())
        Comment = dataflow_instance.model(create_comment_class())

        # Create the database tables for these models
        try:
            dataflow_instance.create_tables()
        except Exception as e:
            # Log but don't fail - tables might already exist
            import logging

            logging.getLogger(__name__).debug(f"Table creation warning: {e}")

        return User, Post, Comment

    return _create_models


@pytest.fixture
def test_data():
    """Sample test data."""
    return {
        "users": [
            {"name": "Alice Smith", "email": "alice@example.com", "active": True},
            {"name": "Bob Jones", "email": "bob@example.com", "active": True},
            {"name": "Charlie Brown", "email": "charlie@example.com", "active": True},
        ],
        "posts": [
            {
                "title": "First Post",
                "content": "This is the first post",
                "published": True,
            },
            {
                "title": "Second Post",
                "content": "This is the second post",
                "published": False,
            },
        ],
    }


# Configure pytest markers
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers",
        "requires_full_infrastructure: Test requires full production infrastructure",
    )
    config.addinivalue_line(
        "markers",
        "requires_monitoring: Test requires monitoring stack (Prometheus/Grafana)",
    )
    config.addinivalue_line(
        "markers", "requires_multi_db: Test requires multiple database instances"
    )


def pytest_collection_modifyitems(config, items):
    """Skip tests that require unavailable infrastructure."""
    # Check if we're in minimal test mode
    minimal_mode = os.getenv("DATAFLOW_MINIMAL_TESTS", "false").lower() == "true"

    if minimal_mode:
        skip_infra = pytest.mark.skip(
            reason="Full infrastructure not available in minimal mode"
        )
        skip_monitoring = pytest.mark.skip(
            reason="Monitoring not available in minimal mode"
        )
        skip_multi_db = pytest.mark.skip(
            reason="Multiple databases not available in minimal mode"
        )

        for item in items:
            if "requires_full_infrastructure" in item.keywords:
                item.add_marker(skip_infra)
            if "requires_monitoring" in item.keywords:
                item.add_marker(skip_monitoring)
            if "requires_multi_db" in item.keywords:
                item.add_marker(skip_multi_db)


# TDD Infrastructure Fixtures
@pytest.fixture(scope="function", autouse=True)
def tdd_infrastructure():
    """Initialize TDD infrastructure for the test session if enabled.

    Note: This is a sync fixture. TDD infrastructure setup requires PostgreSQL
    on port 5434 and is only used when DATAFLOW_TDD_MODE=true AND the database
    is reachable. If either condition is not met, the fixture is a no-op.
    """
    from dataflow.testing.tdd_support import is_tdd_mode

    if not is_tdd_mode():
        yield
        return

    # TDD mode is on - try to set up infrastructure, but gracefully skip
    # if PostgreSQL is not available (some test files set TDD_MODE at module level)
    import asyncio
    import socket

    from dataflow.testing.tdd_support import (
        setup_tdd_infrastructure,
        teardown_tdd_infrastructure,
    )

    # Quick check if PostgreSQL is reachable before attempting async connection
    tdd_db_available = False
    try:
        sock = socket.create_connection(("localhost", 5434), timeout=1)
        sock.close()
        tdd_db_available = True
    except (ConnectionRefusedError, OSError, socket.timeout):
        pass

    if not tdd_db_available:
        yield
        return

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(setup_tdd_infrastructure())
    except Exception:
        # Infrastructure setup failed - continue without TDD
        yield
        return

    yield

    try:
        loop.run_until_complete(teardown_tdd_infrastructure())
    except Exception:
        pass
    finally:
        loop.close()


@pytest.fixture
async def tdd_test_context():
    """Create a TDD test context for fast, isolated testing."""
    from dataflow.testing.tdd_support import tdd_test_context

    async with tdd_test_context() as ctx:
        yield ctx


@pytest.fixture
async def fast_test_db():
    """
    Provide a fast database connection for TDD tests.

    Uses the TDD infrastructure for sub-100ms test execution through
    connection reuse and savepoint-based isolation.
    """
    from dataflow.testing.tdd_support import get_test_context, is_tdd_mode

    if not is_tdd_mode():
        pytest.skip("TDD mode not enabled (set DATAFLOW_TDD_MODE=true)")

    context = get_test_context()
    if not context:
        pytest.skip("No TDD test context available")

    return context.connection


@pytest.fixture
def tdd_dataflow():
    """
    Create a DataFlow instance optimized for TDD testing.

    Uses existing_schema_mode=True and TDD-aware connection management
    for maximum performance and test isolation.
    """
    from dataflow.testing.tdd_support import is_tdd_mode

    if not is_tdd_mode():
        pytest.skip("TDD mode not enabled (set DATAFLOW_TDD_MODE=true)")

    # Create DataFlow with TDD-optimized settings
    config = {
        "database_url": "postgresql://test_user:test_password@localhost:5434/kailash_test",
        "existing_schema_mode": True,  # Don't recreate tables
        "auto_migrate": False,  # No migrations
        "cache_enabled": False,  # No caching
        "pool_size": 1,  # Minimal pool
        "pool_max_overflow": 0,  # No overflow
        "pool_timeout": 5,  # Fast timeout
        "echo": False,  # No SQL logging
    }

    df = DataFlow(**config)
    yield df
    df.close()


@pytest.fixture
def enable_tdd_mode():
    """Enable TDD mode for a specific test."""
    import os

    original_value = os.environ.get("DATAFLOW_TDD_MODE")
    os.environ["DATAFLOW_TDD_MODE"] = "true"

    yield

    # Restore original value
    if original_value is None:
        os.environ.pop("DATAFLOW_TDD_MODE", None)
    else:
        os.environ["DATAFLOW_TDD_MODE"] = original_value


@pytest.fixture
def tdd_performance_tracker():
    """Track test performance for TDD optimization."""
    import time

    start_time = time.time()

    yield

    end_time = time.time()
    execution_time = (end_time - start_time) * 1000  # Convert to milliseconds

    # Log warning if test exceeds TDD performance target
    if execution_time > 100:  # 100ms target
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"TDD test exceeded 100ms target: {execution_time:.2f}ms")

    # Store performance data for analysis
    if not hasattr(tdd_performance_tracker, "performance_data"):
        tdd_performance_tracker.performance_data = []
    tdd_performance_tracker.performance_data.append(execution_time)


# Enhanced TDD Fixtures (Import from fixtures module)
# These are imported as functions to maintain pytest fixture discovery


def _import_tdd_fixtures():
    """Import advanced TDD fixtures from the fixtures module."""
    try:
        # Import the fixture module to ensure pytest can discover the fixtures
        import tests.fixtures.tdd_fixtures

        # The fixtures are already decorated with @pytest.fixture in the module
        # No need to re-register them here - pytest will auto-discover them

    except ImportError:
        # Advanced TDD fixtures not available - fall back to basic ones
        pass


# Import enhanced fixtures if available
_import_tdd_fixtures()


# ============================================================================
# CRITICAL FIX: Event Loop Lifecycle Management for Connection Pools
# ============================================================================
# This fixture addresses SDK-CORE-2025-001: AsyncLocalRuntime transaction bug
# Root Cause: pytest-asyncio creates NEW event loops per test, but DataFlow's
#             AsyncSQLDatabaseNode caches connection pools at CLASS-LEVEL.
#             asyncpg pools are bound to specific event loops, causing
#             "Event loop is closed" errors when tests reuse stale pools.
# Solution: Auto-cleanup all shared pools after EACH test to prevent
#           event loop mismatch.
# Reference: /packages/kailash-dataflow/ASYNC_RUNTIME_EVENT_LOOP_ANALYSIS.md
# ============================================================================


@pytest.fixture(scope="function", autouse=True)
async def cleanup_dataflow_connection_pools():
    """
    Cleanup DataFlow connection pools after each test to prevent event loop mismatch.

    This is a CRITICAL fix for SDK-CORE-2025-001. Without this cleanup:
    1. Test 1 creates connection pool bound to Event Loop A
    2. Test 1 completes, Event Loop A closes
    3. Test 2 starts with NEW Event Loop B
    4. Test 2 tries to reuse pool from Test 1 → "Event loop is closed" ❌

    With this cleanup:
    1. Test 1 creates connection pool bound to Event Loop A
    2. Test 1 completes
    3. THIS FIXTURE closes all pools and clears cache ✅
    4. Test 2 starts with fresh Event Loop B
    5. Test 2 creates NEW pool bound to Event Loop B → SUCCESS ✅
    """
    # Run the test first
    yield

    # CRITICAL: Cleanup after test completes
    try:
        # Import AsyncSQLDatabaseNode to access shared pools
        import asyncio

        from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

        # Close all shared connection pools
        for pool_key, (adapter, loop_id) in list(
            AsyncSQLDatabaseNode._shared_pools.items()
        ):
            try:
                # Get the current event loop to check if it's running
                try:
                    loop = asyncio.get_running_loop()
                    loop_is_closed = loop.is_closed()
                except RuntimeError:
                    # No running loop - event loop already closed
                    loop_is_closed = True

                # Close the adapter's connection pool
                # PostgreSQL/MySQL use close_connection_pool(), SQLite uses disconnect()
                if hasattr(adapter, "close_connection_pool"):
                    if loop_is_closed:
                        # Event loop is closed - force synchronous cleanup
                        # Get the pool and close it directly without awaiting
                        if hasattr(adapter, "_pool") and adapter._pool:
                            try:
                                # Close asyncpg pool synchronously
                                adapter._pool.terminate()
                            except Exception:
                                pass
                    else:
                        # Event loop still running - normal async cleanup
                        await adapter.close_connection_pool()
                elif hasattr(adapter, "disconnect"):
                    if loop_is_closed:
                        # SQLite - can disconnect synchronously
                        pass  # Will be cleared from cache below
                    else:
                        await adapter.disconnect()
                else:
                    import logging

                    logging.warning(
                        f"Adapter {type(adapter).__name__} has no cleanup method"
                    )
            except Exception as e:
                # Log but don't fail the test if cleanup has issues
                import logging

                logging.warning(
                    f"Error closing connection pool {pool_key}: {e}", exc_info=True
                )

        # Clear the shared pools dictionary (CRITICAL - always do this)
        AsyncSQLDatabaseNode._shared_pools.clear()

    except Exception as e:
        # Log but don't fail the test if cleanup module import fails
        import logging

        logging.warning(f"Error during pool cleanup: {e}", exc_info=True)
