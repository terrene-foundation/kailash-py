"""
DataFlow TDD Support Infrastructure

Provides core TDD infrastructure for fast, isolated testing using PostgreSQL savepoints
and transaction-based test isolation. Designed to achieve <100ms test execution time
vs the current >2000ms by reusing connections and leveraging database transactions
for test isolation.

Key Features:
- Transaction-based test isolation using PostgreSQL savepoints
- Connection reuse and pooling for performance
- Zero impact on existing users (feature flag controlled)
- Integration with DataFlow's progressive disclosure system
- Support for test context management and cleanup

Performance Goals:
- Target: <100ms per test (vs current >2000ms)
- Connection reuse eliminates setup/teardown overhead
- Savepoints provide instant test isolation
- Minimal memory footprint for test contexts
"""

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Optional

import asyncpg

logger = logging.getLogger(__name__)

# Global test context storage (thread-local would be better for production)
_current_test_context: Optional["TDDTestContext"] = None
_database_manager: Optional["TDDDatabaseManager"] = None
_transaction_manager: Optional["TDDTransactionManager"] = None


def is_tdd_mode() -> bool:
    """
    Check if DataFlow is running in TDD mode.

    TDD mode is enabled by setting the DATAFLOW_TDD_MODE environment variable
    to any truthy value (true, yes, 1, on, etc.)

    Returns:
        bool: True if TDD mode is enabled, False otherwise
    """
    tdd_mode = os.getenv("DATAFLOW_TDD_MODE", "false").lower()
    return tdd_mode in ("true", "yes", "1", "on", "enabled")


def get_test_context() -> Optional["TDDTestContext"]:
    """
    Get the current test context.

    Returns:
        Optional[TDDTestContext]: Current test context or None if not set
    """
    return _current_test_context


def set_test_context(context: "TDDTestContext") -> None:
    """
    Set the current test context.

    Args:
        context: The test context to set as current
    """
    global _current_test_context
    _current_test_context = context


def clear_test_context() -> None:
    """Clear the current test context."""
    global _current_test_context
    _current_test_context = None


@dataclass
class TDDTestContext:
    """
    Test context for TDD infrastructure.

    Manages test-specific state including database connections, savepoints,
    and test isolation settings. Each test gets its own context to ensure
    proper isolation and cleanup.

    Attributes:
        test_id: Unique identifier for this test
        isolation_level: PostgreSQL transaction isolation level
        timeout: Maximum test execution timeout in seconds
        savepoint_name: Name of the PostgreSQL savepoint for this test
        rollback_on_error: Whether to rollback on test failure
        connection: Active database connection for this test
        savepoint_created: Whether savepoint has been created
        metadata: Additional test metadata storage
    """

    test_id: str = field(default_factory=lambda: f"test_{uuid.uuid4().hex[:8]}")
    isolation_level: str = "READ COMMITTED"
    timeout: int = 30
    savepoint_name: str = field(default_factory=lambda: f"sp_{uuid.uuid4().hex[:8]}")
    rollback_on_error: bool = True
    connection: Optional[asyncpg.Connection] = None
    savepoint_created: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Post-initialization setup."""
        # Ensure savepoint name is valid for PostgreSQL
        if not self.savepoint_name.startswith("sp_"):
            self.savepoint_name = f"sp_{self.savepoint_name}"

        # Limit savepoint name length for performance
        if len(self.savepoint_name) > 20:
            self.savepoint_name = self.savepoint_name[:20]


class TDDDatabaseManager:
    """
    Database connection manager for TDD infrastructure.

    Manages database connections for tests with focus on reuse and performance.
    Maintains a pool of test connections and handles cleanup to prevent
    connection leaks.

    Key features:
    - Connection reuse across test runs
    - Automatic cleanup on test completion
    - PostgreSQL-specific optimizations
    - Test isolation through connection management
    """

    def __init__(self):
        self.connection_pool: Optional[asyncpg.Pool] = None
        self.active_connections: Dict[str, asyncpg.Connection] = {}
        self.test_isolation_enabled: bool = True
        self._connection_string: Optional[str] = None

    async def initialize(self, connection_string: str = None) -> None:
        """
        Initialize the database manager.

        Args:
            connection_string: PostgreSQL connection string
        """
        self._connection_string = (
            connection_string or self._get_default_connection_string()
        )

        # Create a small connection pool for tests
        if not self.connection_pool:
            self.connection_pool = await asyncpg.create_pool(
                self._connection_string,
                min_size=1,
                max_size=5,  # Small pool for tests
                command_timeout=30,
            )

    def _get_default_connection_string(self) -> str:
        """Get default test database connection string."""
        return os.getenv(
            "TEST_DATABASE_URL",
            "postgresql://test_user:test_password@localhost:5434/kailash_test",
        )

    async def get_test_connection(self, context: TDDTestContext) -> asyncpg.Connection:
        """
        Get a database connection for the test context.

        Reuses existing connections when possible to improve performance.

        Args:
            context: Test context requiring a database connection

        Returns:
            asyncpg.Connection: Database connection for the test
        """
        # Check if we already have a connection for this test
        if context.test_id in self.active_connections:
            return self.active_connections[context.test_id]

        # Create new connection
        if self.connection_pool:
            connection = await self.connection_pool.acquire()
        else:
            connection = await asyncpg.connect(self._connection_string)

        # Store connection for reuse
        self.active_connections[context.test_id] = connection
        context.connection = connection

        logger.debug(f"Created database connection for test {context.test_id}")
        return connection

    async def cleanup_test_connection(self, context: TDDTestContext) -> None:
        """
        Clean up database connection for a test context.

        Args:
            context: Test context to clean up
        """
        if context.test_id in self.active_connections:
            connection = self.active_connections[context.test_id]

            try:
                if self.connection_pool:
                    await self.connection_pool.release(connection)
                else:
                    await connection.close()
            except Exception as e:
                logger.warning(
                    f"Error closing connection for test {context.test_id}: {e}"
                )
            finally:
                del self.active_connections[context.test_id]
                context.connection = None

            logger.debug(f"Cleaned up database connection for test {context.test_id}")

    async def cleanup_all_test_connections(self) -> None:
        """Clean up all active test connections."""
        for test_id in list(self.active_connections.keys()):
            connection = self.active_connections[test_id]
            try:
                if self.connection_pool:
                    await self.connection_pool.release(connection)
                else:
                    await connection.close()
            except Exception as e:
                logger.warning(f"Error closing connection for test {test_id}: {e}")

        self.active_connections.clear()
        logger.debug("Cleaned up all test database connections")

    async def close(self) -> None:
        """Close the database manager and all connections."""
        await self.cleanup_all_test_connections()

        if self.connection_pool:
            await self.connection_pool.close()
            self.connection_pool = None


class TDDTransactionManager:
    """
    Transaction and savepoint manager for TDD infrastructure.

    Manages PostgreSQL transactions and savepoints to provide fast test isolation.
    Uses savepoints to create isolated test environments that can be quickly
    rolled back, eliminating the need for database cleanup between tests.

    Key features:
    - PostgreSQL savepoint management
    - Transaction isolation for tests
    - Fast rollback for test cleanup
    - Error handling and recovery
    """

    def __init__(self):
        self.active_savepoints: Dict[str, str] = {}  # test_id -> savepoint_name

    async def create_savepoint(
        self, connection: asyncpg.Connection, context: TDDTestContext
    ) -> None:
        """
        Create a savepoint for test isolation.

        Args:
            connection: Database connection
            context: Test context
        """
        try:
            await connection.execute(f"SAVEPOINT {context.savepoint_name}")
            context.savepoint_created = True
            self.active_savepoints[context.test_id] = context.savepoint_name

            logger.debug(
                f"Created savepoint {context.savepoint_name} for test {context.test_id}"
            )

        except Exception as e:
            logger.error(f"Failed to create savepoint for test {context.test_id}: {e}")
            context.savepoint_created = False
            raise

    async def rollback_to_savepoint(
        self, connection: asyncpg.Connection, context: TDDTestContext
    ) -> None:
        """
        Rollback to the test's savepoint.

        Args:
            connection: Database connection
            context: Test context
        """
        if not context.savepoint_created:
            logger.debug(f"No savepoint to rollback for test {context.test_id}")
            return

        try:
            await connection.execute(f"ROLLBACK TO SAVEPOINT {context.savepoint_name}")
            logger.debug(
                f"Rolled back to savepoint {context.savepoint_name} for test {context.test_id}"
            )

        except Exception as e:
            logger.error(
                f"Failed to rollback to savepoint for test {context.test_id}: {e}"
            )
            raise

    async def release_savepoint(
        self, connection: asyncpg.Connection, context: TDDTestContext
    ) -> None:
        """
        Release (commit) the test's savepoint.

        Args:
            connection: Database connection
            context: Test context
        """
        if not context.savepoint_created:
            logger.debug(f"No savepoint to release for test {context.test_id}")
            return

        try:
            await connection.execute(f"RELEASE SAVEPOINT {context.savepoint_name}")
            context.savepoint_created = False

            if context.test_id in self.active_savepoints:
                del self.active_savepoints[context.test_id]

            logger.debug(
                f"Released savepoint {context.savepoint_name} for test {context.test_id}"
            )

        except Exception as e:
            logger.error(f"Failed to release savepoint for test {context.test_id}: {e}")
            raise

    async def begin_test_transaction(
        self, connection: asyncpg.Connection, context: TDDTestContext
    ) -> None:
        """
        Begin a test transaction with proper isolation and savepoint.

        Args:
            connection: Database connection
            context: Test context
        """
        try:
            # Begin transaction with isolation level
            # PostgreSQL syntax: BEGIN or START TRANSACTION followed by SET TRANSACTION
            await connection.execute("BEGIN")
            await connection.execute(
                f"SET TRANSACTION ISOLATION LEVEL {context.isolation_level}"
            )

            # Create savepoint for test isolation
            await self.create_savepoint(connection, context)

            logger.debug(f"Started test transaction for test {context.test_id}")

        except Exception as e:
            logger.error(
                f"Failed to begin test transaction for test {context.test_id}: {e}"
            )
            raise

    async def end_test_transaction(
        self,
        connection: asyncpg.Connection,
        context: TDDTestContext,
        rollback: bool = None,
    ) -> None:
        """
        End a test transaction, either committing or rolling back.

        Args:
            connection: Database connection
            context: Test context
            rollback: Whether to rollback (None = use context.rollback_on_error)
        """
        if rollback is None:
            rollback = context.rollback_on_error

        try:
            if rollback:
                await self.rollback_to_savepoint(connection, context)
            else:
                await self.release_savepoint(connection, context)

            logger.debug(
                f"Ended test transaction for test {context.test_id} (rollback={rollback})"
            )

        except Exception as e:
            logger.error(
                f"Failed to end test transaction for test {context.test_id}: {e}"
            )
            raise


# Global manager instances
def get_database_manager() -> TDDDatabaseManager:
    """Get the global database manager instance."""
    global _database_manager
    if _database_manager is None:
        _database_manager = TDDDatabaseManager()
    return _database_manager


def get_transaction_manager() -> TDDTransactionManager:
    """Get the global transaction manager instance."""
    global _transaction_manager
    if _transaction_manager is None:
        _transaction_manager = TDDTransactionManager()
    return _transaction_manager


@asynccontextmanager
async def tdd_test_context(
    test_id: str = None,
    isolation_level: str = "READ COMMITTED",
    timeout: int = 30,
    rollback_on_error: bool = True,
    **kwargs,
) -> AsyncGenerator[TDDTestContext, None]:
    """
    Async context manager for TDD test execution.

    Provides a complete test environment with database connection,
    transaction isolation, and automatic cleanup.

    Args:
        test_id: Unique test identifier (auto-generated if None)
        isolation_level: PostgreSQL transaction isolation level
        timeout: Test timeout in seconds
        rollback_on_error: Whether to rollback on test failure
        **kwargs: Additional metadata for the test context

    Yields:
        TDDTestContext: Configured test context

    Example:
        async with tdd_test_context(test_id="user_registration") as ctx:
            # Test code here - automatic cleanup on exit
            connection = ctx.connection
            # Perform test operations...
    """
    # Create test context
    context = TDDTestContext(
        test_id=test_id,
        isolation_level=isolation_level,
        timeout=timeout,
        rollback_on_error=rollback_on_error,
        metadata=kwargs,
    )

    # Set as current context
    set_test_context(context)

    # Get managers
    db_manager = get_database_manager()
    tx_manager = get_transaction_manager()

    try:
        # Initialize database manager if needed
        if not db_manager.connection_pool:
            await db_manager.initialize()

        # Get database connection
        connection = await db_manager.get_test_connection(context)

        # Begin test transaction
        await tx_manager.begin_test_transaction(connection, context)

        # Yield context for test execution
        yield context

    except Exception as e:
        logger.error(f"Error in test context {context.test_id}: {e}")
        # Rollback on error
        if context.connection and context.savepoint_created:
            try:
                await tx_manager.end_test_transaction(
                    context.connection, context, rollback=True
                )
            except Exception as cleanup_error:
                logger.error(
                    f"Error during cleanup for test {context.test_id}: {cleanup_error}"
                )
        raise

    finally:
        try:
            # End transaction (rollback by default for test isolation)
            if context.connection and context.savepoint_created:
                await tx_manager.end_test_transaction(
                    context.connection, context, rollback=True
                )

            # Cleanup connection
            await db_manager.cleanup_test_connection(context)

        except Exception as cleanup_error:
            logger.error(
                f"Error during final cleanup for test {context.test_id}: {cleanup_error}"
            )

        finally:
            # Clear context
            clear_test_context()


# Convenience functions for test setup
async def setup_tdd_infrastructure() -> None:
    """Initialize TDD infrastructure for test session."""
    if not is_tdd_mode():
        return

    db_manager = get_database_manager()
    await db_manager.initialize()

    logger.info("TDD infrastructure initialized")


async def teardown_tdd_infrastructure() -> None:
    """Cleanup TDD infrastructure after test session."""
    if not is_tdd_mode():
        return

    db_manager = get_database_manager()
    await db_manager.close()

    # Clear global state
    global _database_manager, _transaction_manager, _current_test_context
    _database_manager = None
    _transaction_manager = None
    _current_test_context = None

    logger.info("TDD infrastructure cleaned up")
