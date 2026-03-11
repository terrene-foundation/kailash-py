"""
PostgreSQL Test Manager - Phase 1B Component 2

Real database integration testing manager for comprehensive PostgreSQL testing
with Docker container lifecycle management and test data management.

Key Features:
- Docker PostgreSQL container lifecycle management
- Real database integration testing (NO MOCKING in Tiers 2-3)
- Integration with Migration Testing Framework (Component 1)
- Comprehensive test data lifecycle management
- Concurrent access scenario testing
- Performance validation (<5s for integration tests)
- Compatibility with existing test infrastructure

This manager integrates with:
- Migration Testing Framework (Component 1) for migration testing
- Docker test infrastructure (tests/utils/test_env) for container management
- Existing test utilities for E2E testing scenarios
- Phase 1A components for comprehensive migration testing
"""

import asyncio
import logging
import os
import socket
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import asyncpg

    import docker

    DEPENDENCIES_AVAILABLE = True
except ImportError:
    DEPENDENCIES_AVAILABLE = False

from .migration_test_framework import (
    MigrationTestEnvironment,
    MigrationTestError,
    MigrationTestFramework,
    MigrationTestResult,
)

logger = logging.getLogger(__name__)


class ContainerStatus(Enum):
    """PostgreSQL container status."""

    NOT_FOUND = "not_found"
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


@dataclass
class ContainerInfo:
    """PostgreSQL container information."""

    container_id: Optional[str]
    status: ContainerStatus
    database_url: str
    host: str
    port: int
    database: str
    user: str
    password: str
    ready: bool = False
    error: Optional[str] = None
    performance_metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PostgreSQLTestExecutionResult:
    """Result of test execution against PostgreSQL."""

    success: bool
    test_case_name: str
    execution_time: float
    container_info: ContainerInfo
    migration_results: List[MigrationTestResult] = field(default_factory=list)
    performance_metrics: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    concurrent_test_results: Dict[str, Any] = field(default_factory=dict)


class PostgreSQLTestManager:
    """
    PostgreSQL Test Manager for real database integration testing.

    Manages Docker PostgreSQL containers for integration and E2E testing
    with NO MOCKING policy enforcement and performance validation.
    """

    def __init__(
        self,
        container_name: str = "dataflow_test_postgres_manager",
        postgres_port: int = 5434,  # Different from test_env to avoid conflicts
        performance_target_seconds: float = 5.0,
        enable_concurrent_testing: bool = True,
        integration_with_test_env: bool = True,
    ):
        """
        Initialize PostgreSQL Test Manager.

        Args:
            container_name: Docker container name
            postgres_port: PostgreSQL port (avoid conflicts with test_env)
            performance_target_seconds: Max execution time for integration tests
            enable_concurrent_testing: Whether to run concurrent access tests
            integration_with_test_env: Whether to integrate with existing test_env
        """
        if not DEPENDENCIES_AVAILABLE:
            raise MigrationTestError(
                "Required dependencies (asyncpg, docker) not available"
            )

        self.container_name = container_name
        self.postgres_port = postgres_port
        self.performance_target = performance_target_seconds
        self.enable_concurrent_testing = enable_concurrent_testing
        self.integration_with_test_env = integration_with_test_env

        # Database configuration
        self.database_config = {
            "host": "localhost",
            "port": postgres_port,
            "database": "dataflow_test_manager",
            "user": "dataflow_test_manager",
            "password": "dataflow_test_manager_password",
        }

        # Docker client
        self._docker_client: Optional[docker.DockerClient] = None
        self._container: Optional[docker.models.containers.Container] = None

        # Migration testing integration
        self._migration_framework: Optional[MigrationTestFramework] = None

        # Test data management
        self._test_databases: List[str] = []
        self._active_connections: List[Any] = []

        logger.info(
            f"PostgreSQLTestManager initialized: port {postgres_port}, "
            f"target {performance_target_seconds}s"
        )

    def _check_docker_available(self) -> bool:
        """Check if Docker is available and running."""
        try:
            self._docker_client = docker.from_env()
            self._docker_client.ping()
            return True
        except Exception as e:
            logger.error(f"Docker not available: {e}")
            return False

    def _check_port_available(self, port: int) -> bool:
        """Check if port is available for use."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            result = sock.connect_ex(("localhost", port))
            return result != 0

    async def start_test_container(self) -> ContainerInfo:
        """
        Start PostgreSQL test container with performance monitoring.

        Returns:
            ContainerInfo with connection details and status
        """
        logger.info("Starting PostgreSQL test container...")
        start_time = time.perf_counter()

        try:
            # Check Docker availability
            if not self._check_docker_available():
                raise MigrationTestError("Docker is not available")

            # Check for port conflicts
            if not self._check_port_available(self.postgres_port):
                logger.warning(f"Port {self.postgres_port} already in use")
                # Try to find existing container
                existing_container = await self._find_existing_container()
                if existing_container and existing_container.ready:
                    logger.info("Using existing container")
                    return existing_container

            # Remove existing container if it exists
            await self._cleanup_existing_container()

            # Start new container
            container_info = await self._start_new_container()

            # Wait for PostgreSQL to be ready
            await self._wait_for_postgresql_ready(container_info)

            setup_time = time.perf_counter() - start_time
            container_info.performance_metrics["setup_time"] = setup_time

            logger.info(f"PostgreSQL container ready in {setup_time:.3f}s")

            # Verify performance target
            if setup_time > self.performance_target:
                logger.warning(
                    f"Container setup time {setup_time:.3f}s exceeds "
                    f"target {self.performance_target}s"
                )

            return container_info

        except Exception as e:
            logger.error(f"Failed to start PostgreSQL container: {e}")
            return ContainerInfo(
                container_id=None,
                status=ContainerStatus.ERROR,
                database_url="",
                host="",
                port=0,
                database="",
                user="",
                password="",
                error=str(e),
            )

    async def _find_existing_container(self) -> Optional[ContainerInfo]:
        """Find and verify existing container."""
        try:
            container = self._docker_client.containers.get(self.container_name)

            if container.status == "running":
                container_info = ContainerInfo(
                    container_id=container.id,
                    status=ContainerStatus.RUNNING,
                    database_url=self._build_database_url(),
                    **self.database_config,
                )

                # Test connection
                if await self._test_connection(container_info):
                    container_info.ready = True
                    self._container = container
                    return container_info

        except docker.errors.NotFound:
            pass
        except Exception as e:
            logger.warning(f"Error checking existing container: {e}")

        return None

    async def _cleanup_existing_container(self):
        """Remove existing container if it exists."""
        try:
            container = self._docker_client.containers.get(self.container_name)
            logger.info("Removing existing container")
            container.stop()
            container.remove()
        except docker.errors.NotFound:
            pass
        except Exception as e:
            logger.warning(f"Error cleaning up existing container: {e}")

    async def _start_new_container(self) -> ContainerInfo:
        """Start new PostgreSQL container."""
        logger.info("Creating new PostgreSQL container...")

        try:
            self._container = self._docker_client.containers.run(
                "postgres:15-alpine",
                name=self.container_name,
                environment={
                    "POSTGRES_DB": self.database_config["database"],
                    "POSTGRES_USER": self.database_config["user"],
                    "POSTGRES_PASSWORD": self.database_config["password"],
                    "POSTGRES_HOST_AUTH_METHOD": "trust",
                },
                ports={5432: self.postgres_port},
                detach=True,
                remove=False,
                # Add health check
                healthcheck={
                    "test": [
                        "CMD-SHELL",
                        f"pg_isready -U {self.database_config['user']} -d {self.database_config['database']}",
                    ],
                    "interval": 30000000000,  # 30s in nanoseconds
                    "timeout": 10000000000,  # 10s in nanoseconds
                    "retries": 3,
                    "start_period": 60000000000,  # 60s in nanoseconds
                },
            )

            container_info = ContainerInfo(
                container_id=self._container.id,
                status=ContainerStatus.STARTING,
                database_url=self._build_database_url(),
                **self.database_config,
            )

            logger.info(f"Container started: {container_info.container_id[:12]}")
            return container_info

        except Exception as e:
            logger.error(f"Failed to start container: {e}")
            raise MigrationTestError(f"Container creation failed: {e}")

    def _build_database_url(self) -> str:
        """Build PostgreSQL database URL."""
        return (
            f"postgresql://{self.database_config['user']}:"
            f"{self.database_config['password']}@"
            f"{self.database_config['host']}:"
            f"{self.database_config['port']}/"
            f"{self.database_config['database']}"
        )

    async def _wait_for_postgresql_ready(
        self, container_info: ContainerInfo, max_attempts: int = 30
    ):
        """Wait for PostgreSQL to be ready to accept connections."""
        logger.info("Waiting for PostgreSQL to be ready...")

        for attempt in range(max_attempts):
            try:
                if await self._test_connection(container_info):
                    container_info.status = ContainerStatus.RUNNING
                    container_info.ready = True
                    logger.info("PostgreSQL is ready!")
                    return

            except Exception as e:
                if attempt == max_attempts - 1:
                    logger.error(
                        f"PostgreSQL not ready after {max_attempts} attempts: {e}"
                    )
                    container_info.status = ContainerStatus.ERROR
                    container_info.error = f"Startup timeout: {e}"
                    raise MigrationTestError(f"PostgreSQL startup failed: {e}")

            await asyncio.sleep(1)

    async def _test_connection(self, container_info: ContainerInfo) -> bool:
        """Test PostgreSQL connection."""
        try:
            conn = await asyncpg.connect(container_info.database_url)
            await conn.execute("SELECT 1")
            await conn.close()
            return True
        except Exception:
            return False

    async def run_migration_integration_test(
        self, test_case: Dict[str, Any]
    ) -> PostgreSQLTestExecutionResult:
        """
        Run migration integration test against real PostgreSQL.

        Args:
            test_case: Test case configuration containing:
                - name: Test case name
                - migrations: List of migrations to test
                - expected_schema: Expected schema after migrations
                - performance_target: Optional custom performance target

        Returns:
            TestExecutionResult with comprehensive results
        """
        test_name = test_case.get("name", "unknown_test")
        logger.info(f"Running migration integration test: {test_name}")
        start_time = time.perf_counter()

        try:
            # Ensure container is running
            container_info = await self.start_test_container()
            if not container_info.ready:
                raise MigrationTestError(f"Container not ready: {container_info.error}")

            # Initialize migration testing framework
            migration_framework = MigrationTestFramework(
                database_type="postgresql",
                connection_string=container_info.database_url,
                performance_target_seconds=test_case.get(
                    "performance_target", self.performance_target
                ),
                enable_rollback_testing=test_case.get("enable_rollback", True),
                integration_mode=True,  # NO MOCKING
            )

            # Execute migrations
            migration_results = []
            for migration_config in test_case.get("migrations", []):
                # Create test migration
                migration = migration_framework.create_test_migration(
                    name=migration_config["name"],
                    tables=migration_config["tables"],
                    operations=migration_config.get("operations"),
                )

                # Run comprehensive test
                result = await migration_framework.run_comprehensive_test(
                    migration=migration,
                    expected_schema=migration_config.get("expected_schema", {}),
                    test_rollback=test_case.get("enable_rollback", True),
                )

                migration_results.append(result)

                # Check if migration failed
                if not result.success:
                    logger.error(f"Migration {migration.name} failed: {result.error}")

            # Run concurrent access tests if enabled
            concurrent_results = {}
            if self.enable_concurrent_testing and test_case.get(
                "test_concurrent", True
            ):
                concurrent_results = await self._run_concurrent_access_tests(
                    container_info
                )

            execution_time = time.perf_counter() - start_time

            # Calculate overall success
            overall_success = all(result.success for result in migration_results)
            if concurrent_results:
                overall_success = overall_success and concurrent_results.get(
                    "success", True
                )

            return PostgreSQLTestExecutionResult(
                success=overall_success,
                test_case_name=test_name,
                execution_time=execution_time,
                container_info=container_info,
                migration_results=migration_results,
                performance_metrics={
                    "execution_time": execution_time,
                    "target_time": self.performance_target,
                    "performance_pass": execution_time <= self.performance_target,
                    "migrations_count": len(migration_results),
                    "migrations_passed": sum(1 for r in migration_results if r.success),
                },
                concurrent_test_results=concurrent_results,
            )

        except Exception as e:
            execution_time = time.perf_counter() - start_time
            logger.error(f"Migration integration test failed: {e}")

            return PostgreSQLTestExecutionResult(
                success=False,
                test_case_name=test_name,
                execution_time=execution_time,
                container_info=ContainerInfo(
                    container_id=None,
                    status=ContainerStatus.ERROR,
                    database_url="",
                    host="",
                    port=0,
                    database="",
                    user="",
                    password="",
                    error=str(e),
                ),
                error=str(e),
            )

    async def _run_concurrent_access_tests(
        self, container_info: ContainerInfo
    ) -> Dict[str, Any]:
        """
        Run concurrent access tests against PostgreSQL.

        Tests multiple simultaneous connections and operations
        to verify database handles concurrent access properly.
        """
        logger.info("Running concurrent access tests...")
        start_time = time.perf_counter()

        try:
            # Test 1: Multiple simultaneous connections
            connection_test = await self._test_multiple_connections(container_info)

            # Test 2: Concurrent read/write operations
            read_write_test = await self._test_concurrent_read_write(container_info)

            # Test 3: Schema operations under concurrent load
            schema_test = await self._test_concurrent_schema_operations(container_info)

            execution_time = time.perf_counter() - start_time

            overall_success = (
                connection_test["success"]
                and read_write_test["success"]
                and schema_test["success"]
            )

            return {
                "success": overall_success,
                "execution_time": execution_time,
                "connection_test": connection_test,
                "read_write_test": read_write_test,
                "schema_test": schema_test,
            }

        except Exception as e:
            logger.error(f"Concurrent access tests failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "execution_time": time.perf_counter() - start_time,
            }

    async def _test_multiple_connections(
        self, container_info: ContainerInfo, connection_count: int = 10
    ) -> Dict[str, Any]:
        """Test multiple simultaneous database connections."""
        logger.info(f"Testing {connection_count} simultaneous connections...")

        try:
            # Create multiple connections simultaneously
            connection_tasks = [
                asyncpg.connect(container_info.database_url)
                for _ in range(connection_count)
            ]

            start_time = time.perf_counter()
            connections = await asyncio.gather(*connection_tasks)
            connection_time = time.perf_counter() - start_time

            # Test each connection
            test_tasks = [
                conn.execute("SELECT 1 as test_value") for conn in connections
            ]

            query_start = time.perf_counter()
            await asyncio.gather(*test_tasks)
            query_time = time.perf_counter() - query_start

            # Close all connections
            close_tasks = [conn.close() for conn in connections]
            await asyncio.gather(*close_tasks)

            logger.info(
                f"Multiple connections test passed: {connection_count} connections "
                f"in {connection_time:.3f}s, queries in {query_time:.3f}s"
            )

            return {
                "success": True,
                "connection_count": connection_count,
                "connection_time": connection_time,
                "query_time": query_time,
                "total_time": connection_time + query_time,
            }

        except Exception as e:
            logger.error(f"Multiple connections test failed: {e}")
            return {"success": False, "error": str(e)}

    async def _test_concurrent_read_write(
        self, container_info: ContainerInfo
    ) -> Dict[str, Any]:
        """Test concurrent read and write operations."""
        logger.info("Testing concurrent read/write operations...")

        try:
            # Create test table
            conn = await asyncpg.connect(container_info.database_url)
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS concurrent_test (
                    id SERIAL PRIMARY KEY,
                    value INTEGER,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            await conn.close()

            # Concurrent write operations
            async def write_operation(writer_id: int):
                conn = await asyncpg.connect(container_info.database_url)
                try:
                    for i in range(10):
                        await conn.execute(
                            "INSERT INTO concurrent_test (value) VALUES ($1)",
                            writer_id * 100 + i,
                        )
                    return {"writer_id": writer_id, "success": True}
                except Exception as e:
                    return {"writer_id": writer_id, "success": False, "error": str(e)}
                finally:
                    await conn.close()

            # Concurrent read operations
            async def read_operation(reader_id: int):
                conn = await asyncpg.connect(container_info.database_url)
                try:
                    rows = await conn.fetch(
                        "SELECT COUNT(*) as count FROM concurrent_test"
                    )
                    count = rows[0]["count"] if rows else 0
                    return {"reader_id": reader_id, "success": True, "count": count}
                except Exception as e:
                    return {"reader_id": reader_id, "success": False, "error": str(e)}
                finally:
                    await conn.close()

            start_time = time.perf_counter()

            # Run concurrent operations
            write_tasks = [write_operation(i) for i in range(5)]
            read_tasks = [read_operation(i) for i in range(5)]

            results = await asyncio.gather(*(write_tasks + read_tasks))
            execution_time = time.perf_counter() - start_time

            # Analyze results
            write_results = results[:5]
            read_results = results[5:]

            writes_successful = all(r["success"] for r in write_results)
            reads_successful = all(r["success"] for r in read_results)

            # Cleanup
            conn = await asyncpg.connect(container_info.database_url)
            await conn.execute("DROP TABLE IF EXISTS concurrent_test")
            await conn.close()

            logger.info(
                f"Concurrent read/write test completed in {execution_time:.3f}s: "
                f"writes={writes_successful}, reads={reads_successful}"
            )

            return {
                "success": writes_successful and reads_successful,
                "execution_time": execution_time,
                "write_results": write_results,
                "read_results": read_results,
            }

        except Exception as e:
            logger.error(f"Concurrent read/write test failed: {e}")
            return {"success": False, "error": str(e)}

    async def _test_concurrent_schema_operations(
        self, container_info: ContainerInfo
    ) -> Dict[str, Any]:
        """Test schema operations under concurrent load."""
        logger.info("Testing concurrent schema operations...")

        try:
            # Schema operation while concurrent queries are running
            async def background_queries():
                conn = await asyncpg.connect(container_info.database_url)
                try:
                    # Create test table for background queries
                    await conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS background_test (
                            id SERIAL PRIMARY KEY,
                            data TEXT
                        )
                    """
                    )

                    # Run queries
                    for i in range(50):
                        await conn.execute(
                            "INSERT INTO background_test (data) VALUES ($1)",
                            f"data_{i}",
                        )
                        await conn.fetch("SELECT COUNT(*) FROM background_test")
                        await asyncio.sleep(0.01)  # Small delay

                    return {"success": True}
                except Exception as e:
                    return {"success": False, "error": str(e)}
                finally:
                    await conn.close()

            async def schema_operations():
                conn = await asyncpg.connect(container_info.database_url)
                try:
                    # Create and modify table schema
                    await conn.execute(
                        """
                        CREATE TABLE schema_test (
                            id SERIAL PRIMARY KEY,
                            name VARCHAR(100)
                        )
                    """
                    )

                    await conn.execute(
                        """
                        ALTER TABLE schema_test ADD COLUMN email VARCHAR(255)
                    """
                    )

                    await conn.execute(
                        """
                        CREATE INDEX idx_schema_test_name ON schema_test(name)
                    """
                    )

                    await conn.execute("DROP TABLE schema_test")

                    return {"success": True}
                except Exception as e:
                    return {"success": False, "error": str(e)}
                finally:
                    await conn.close()

            start_time = time.perf_counter()

            # Run schema operations concurrently with background queries
            results = await asyncio.gather(background_queries(), schema_operations())

            execution_time = time.perf_counter() - start_time

            background_success = results[0]["success"]
            schema_success = results[1]["success"]

            # Cleanup
            conn = await asyncpg.connect(container_info.database_url)
            await conn.execute("DROP TABLE IF EXISTS background_test")
            await conn.close()

            logger.info(
                f"Concurrent schema operations test completed in {execution_time:.3f}s: "
                f"background={background_success}, schema={schema_success}"
            )

            return {
                "success": background_success and schema_success,
                "execution_time": execution_time,
                "background_result": results[0],
                "schema_result": results[1],
            }

        except Exception as e:
            logger.error(f"Concurrent schema operations test failed: {e}")
            return {"success": False, "error": str(e)}

    async def cleanup_test_environment(self) -> None:
        """
        Clean up test environment including containers and connections.

        Performs comprehensive cleanup of all test resources.
        """
        logger.info("Cleaning up PostgreSQL test environment...")

        try:
            # Close active connections
            if self._active_connections:
                for conn in self._active_connections:
                    try:
                        if hasattr(conn, "close"):
                            if asyncio.iscoroutinefunction(conn.close):
                                await conn.close()
                            else:
                                conn.close()
                    except Exception as e:
                        logger.warning(f"Error closing connection: {e}")

                self._active_connections.clear()

            # Stop and remove container
            if self._container:
                try:
                    logger.info("Stopping PostgreSQL container...")
                    self._container.stop(timeout=10)
                    self._container.remove()
                    logger.info("Container removed successfully")
                except Exception as e:
                    logger.warning(f"Error removing container: {e}")

                self._container = None

            # Reset state
            self._test_databases.clear()
            self._migration_framework = None

            logger.info("Test environment cleanup completed")

        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            raise MigrationTestError(f"Cleanup failed: {e}")

    async def get_container_status(self) -> ContainerInfo:
        """
        Get current container status and health information.

        Returns:
            ContainerInfo with current status
        """
        try:
            if not self._container:
                return ContainerInfo(
                    container_id=None,
                    status=ContainerStatus.NOT_FOUND,
                    database_url="",
                    host="",
                    port=0,
                    database="",
                    user="",
                    password="",
                )

            # Refresh container status
            self._container.reload()

            container_info = ContainerInfo(
                container_id=self._container.id,
                status=(
                    ContainerStatus.RUNNING
                    if self._container.status == "running"
                    else ContainerStatus.STOPPED
                ),
                database_url=self._build_database_url(),
                **self.database_config,
            )

            # Test connection if container is running
            if container_info.status == ContainerStatus.RUNNING:
                container_info.ready = await self._test_connection(container_info)

            return container_info

        except Exception as e:
            logger.error(f"Error getting container status: {e}")
            return ContainerInfo(
                container_id=None,
                status=ContainerStatus.ERROR,
                database_url="",
                host="",
                port=0,
                database="",
                user="",
                password="",
                error=str(e),
            )

    def get_test_database_url(self) -> str:
        """Get the test database URL for integration with other components."""
        return self._build_database_url()

    async def create_test_database(self, database_name: str) -> str:
        """
        Create a new test database for isolated testing.

        Args:
            database_name: Name of the test database to create

        Returns:
            Database URL for the new test database
        """
        logger.info(f"Creating test database: {database_name}")

        try:
            # Connect to main database
            conn = await asyncpg.connect(self._build_database_url())

            # Create new database
            await conn.execute(f'CREATE DATABASE "{database_name}"')
            await conn.close()

            # Build URL for new database
            new_db_url = (
                f"postgresql://{self.database_config['user']}:"
                f"{self.database_config['password']}@"
                f"{self.database_config['host']}:"
                f"{self.database_config['port']}/"
                f"{database_name}"
            )

            self._test_databases.append(database_name)
            logger.info(f"Test database '{database_name}' created successfully")

            return new_db_url

        except Exception as e:
            logger.error(f"Failed to create test database '{database_name}': {e}")
            raise MigrationTestError(f"Database creation failed: {e}")

    async def drop_test_database(self, database_name: str) -> bool:
        """
        Drop a test database.

        Args:
            database_name: Name of the test database to drop

        Returns:
            True if successful
        """
        logger.info(f"Dropping test database: {database_name}")

        try:
            # Connect to main database
            conn = await asyncpg.connect(self._build_database_url())

            # Drop database
            await conn.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
            await conn.close()

            if database_name in self._test_databases:
                self._test_databases.remove(database_name)

            logger.info(f"Test database '{database_name}' dropped successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to drop test database '{database_name}': {e}")
            return False
