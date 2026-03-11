"""
Docker Test Base Infrastructure for Kaizen Framework Testing

Provides real Docker infrastructure for Tier 2 (Integration) and Tier 3 (E2E) tests.
NO MOCKING ALLOWED in these test tiers - uses actual Docker services.

Requirements:
- Docker services must be running: ./tests/utils/test-env up
- Real PostgreSQL, Redis, MinIO, Elasticsearch services
- Actual network and persistence operations

Based on Kailash Core SDK testing infrastructure with Kaizen-specific extensions.
"""

import logging
import os
import subprocess
import time
from abc import ABC
from typing import Any, Dict

import pytest


class DockerServiceError(Exception):
    """Exception raised when Docker services are not available."""

    pass


class DockerTestBase(ABC):
    """
    Base class for Docker-based testing infrastructure.

    Provides common functionality for integration and E2E tests that require
    real Docker services and infrastructure.
    """

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.required_services = ["postgresql", "redis", "minio"]
        self.service_health_timeout = 60  # seconds

    def setup_method(self):
        """Setup method called before each test."""
        self.logger.info(
            f"Setting up Docker test environment for {self.__class__.__name__}"
        )

    def teardown_method(self):
        """Teardown method called after each test."""
        self.logger.info(
            f"Tearing down Docker test environment for {self.__class__.__name__}"
        )

    def ensure_docker_services(self):
        """
        Ensure all required Docker services are running and healthy.

        Raises:
            DockerServiceError: If services are not available or healthy
        """
        self.logger.info("Checking Docker services availability...")

        # Check if Docker is running
        try:
            result = subprocess.run(
                ["docker", "info"], capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                raise DockerServiceError("Docker is not running or not accessible")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            raise DockerServiceError("Docker command not found or timed out")

        # Check specific services
        for service in self.required_services:
            if not self._check_service_health(service):
                self.logger.warning(
                    f"Service {service} not healthy, attempting to start..."
                )
                self._start_test_services()
                break

        # Final health check
        unhealthy_services = []
        for service in self.required_services:
            if not self._check_service_health(service):
                unhealthy_services.append(service)

        if unhealthy_services:
            raise DockerServiceError(
                f"Services not healthy: {unhealthy_services}. "
                f"Please run: ./tests/utils/test-env up"
            )

        self.logger.info("All Docker services are healthy and ready")

    def _check_service_health(self, service_name: str) -> bool:
        """
        Check if a specific service is healthy.

        Args:
            service_name: Name of the service to check

        Returns:
            True if service is healthy, False otherwise
        """
        health_checks = {
            "postgresql": self._check_postgresql_health,
            "redis": self._check_redis_health,
            "minio": self._check_minio_health,
            "elasticsearch": self._check_elasticsearch_health,
        }

        check_func = health_checks.get(service_name)
        if not check_func:
            self.logger.warning(f"No health check defined for service: {service_name}")
            return False

        try:
            return check_func()
        except Exception as e:
            self.logger.debug(f"Health check failed for {service_name}: {e}")
            return False

    def _check_postgresql_health(self) -> bool:
        """Check PostgreSQL health."""
        try:
            import psycopg2

            conn = psycopg2.connect(
                host="localhost",
                port=5434,  # Test port
                database="kailash_test",
                user="test_user",
                password="test_password",
                connect_timeout=5,
            )
            conn.close()
            return True
        except Exception:
            return False

    def _check_redis_health(self) -> bool:
        """Check Redis health."""
        try:
            import redis

            r = redis.Redis(host="localhost", port=6380, db=0, socket_timeout=5)
            r.ping()
            return True
        except Exception:
            return False

    def _check_minio_health(self) -> bool:
        """Check MinIO health."""
        try:
            import requests

            response = requests.get(
                "http://localhost:9001/minio/health/live", timeout=5
            )
            return response.status_code == 200
        except Exception:
            return False

    def _check_elasticsearch_health(self) -> bool:
        """Check Elasticsearch health."""
        try:
            import requests

            response = requests.get("http://localhost:9201/_cluster/health", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def _start_test_services(self):
        """
        Attempt to start test services using test-env script.

        Note: This assumes the test-env script exists and is executable.
        """
        test_env_script = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "..",
            "..",
            "tests",
            "utils",
            "test-env",
        )

        if not os.path.exists(test_env_script):
            self.logger.warning(f"test-env script not found at {test_env_script}")
            return

        try:
            self.logger.info("Starting test services...")
            result = subprocess.run(
                [test_env_script, "up"],
                capture_output=True,
                text=True,
                timeout=120,  # 2 minutes timeout
            )

            if result.returncode == 0:
                self.logger.info("Test services started successfully")
                # Wait for services to be ready
                time.sleep(10)
            else:
                self.logger.warning(f"Failed to start test services: {result.stderr}")

        except subprocess.TimeoutExpired:
            self.logger.warning("Timeout while starting test services")
        except Exception as e:
            self.logger.warning(f"Error starting test services: {e}")

    def get_service_config(self, service_name: str) -> Dict[str, Any]:
        """
        Get configuration for a specific service.

        Args:
            service_name: Name of the service

        Returns:
            Service configuration dictionary
        """
        configs = {
            "postgresql": {
                "host": "localhost",
                "port": 5434,
                "database": "kailash_test",
                "user": "test_user",
                "password": "test_password",
                "url": "postgresql://test_user:test_password@localhost:5434/kailash_test",
            },
            "redis": {
                "host": "localhost",
                "port": 6380,
                "db": 0,
                "url": "redis://localhost:6380/0",
            },
            "minio": {
                "endpoint": "localhost:9001",
                "access_key": "testuser",
                "secret_key": "testpass",
                "secure": False,
                "url": "http://localhost:9001",
            },
            "elasticsearch": {
                "host": "localhost",
                "port": 9201,
                "url": "http://localhost:9201",
            },
        }

        return configs.get(service_name, {})


class DockerIntegrationTestBase(DockerTestBase):
    """
    Base class specifically for Tier 2 Integration tests.

    Provides integration-specific functionality and ensures proper
    test environment setup for component integration testing.
    """

    def __init__(self):
        super().__init__()
        self.required_services = [
            "postgresql",
            "redis",
        ]  # Core services for integration

    def setup_method(self):
        """Setup for integration tests."""
        super().setup_method()
        self.logger.info("Setting up integration test environment")

        # Integration tests may need some basic cleanup
        self._cleanup_test_data()

    def teardown_method(self):
        """Teardown for integration tests."""
        super().teardown_method()
        self._cleanup_test_data()

    def _cleanup_test_data(self):
        """Clean up test data between integration tests."""
        try:
            # Clean Redis test data
            if self._check_redis_health():
                import redis

                r = redis.Redis(host="localhost", port=6380, db=0)
                # Only clean test keys
                test_keys = r.keys("test:*")
                if test_keys:
                    r.delete(*test_keys)

            # Clean PostgreSQL test data
            if self._check_postgresql_health():
                import psycopg2

                conn = psycopg2.connect(
                    host="localhost",
                    port=5434,
                    database="kailash_test",
                    user="test_user",
                    password="test_password",
                )
                cursor = conn.cursor()

                # Clean test tables (if they exist)
                test_tables = ["test_users", "test_workflows", "test_audit_logs"]
                for table in test_tables:
                    try:
                        cursor.execute(f"TRUNCATE TABLE {table} CASCADE")
                    except Exception:
                        pass  # Table might not exist

                conn.commit()
                conn.close()

        except Exception as e:
            self.logger.debug(f"Cleanup warning: {e}")


class DockerE2ETestBase(DockerTestBase):
    """
    Base class specifically for Tier 3 E2E tests.

    Provides E2E-specific functionality and ensures complete
    infrastructure stack is available for end-to-end testing.
    """

    def __init__(self):
        super().__init__()
        self.required_services = [
            "postgresql",
            "redis",
            "minio",
            "elasticsearch",
        ]  # Full stack

    def setup_method(self):
        """Setup for E2E tests."""
        super().setup_method()
        self.logger.info("Setting up E2E test environment")

        # E2E tests need complete environment reset
        self._reset_test_environment()

    def teardown_method(self):
        """Teardown for E2E tests."""
        super().teardown_method()
        # Optionally clean up after E2E tests
        # (might want to preserve state for debugging)

    def _reset_test_environment(self):
        """Reset the complete test environment for E2E tests."""
        try:
            # More comprehensive cleanup for E2E tests
            self._cleanup_test_data()

            # Reset MinIO test buckets
            if self._check_minio_health():
                try:
                    from minio import Minio

                    client = Minio(
                        "localhost:9001",
                        access_key="testuser",
                        secret_key="testpass",
                        secure=False,
                    )

                    # List and clean test buckets
                    buckets = client.list_buckets()
                    for bucket in buckets:
                        if bucket.name.startswith("test-"):
                            # Remove all objects in test bucket
                            objects = client.list_objects(bucket.name, recursive=True)
                            object_names = [obj.object_name for obj in objects]
                            if object_names:
                                errors = client.remove_objects(
                                    bucket.name, object_names
                                )
                                for error in errors:
                                    self.logger.warning(f"MinIO cleanup error: {error}")

                except Exception as e:
                    self.logger.debug(f"MinIO cleanup warning: {e}")

        except Exception as e:
            self.logger.debug(f"Environment reset warning: {e}")


# Utility functions for test infrastructure
def skip_if_docker_unavailable():
    """
    Decorator to skip tests if Docker infrastructure is not available.

    Usage:
        @skip_if_docker_unavailable()
        def test_with_docker(self):
            # Test that requires Docker
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                # Quick Docker check
                result = subprocess.run(
                    ["docker", "info"], capture_output=True, timeout=5
                )
                if result.returncode != 0:
                    pytest.skip("Docker not available")
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pytest.skip("Docker not available")

            return func(*args, **kwargs)

        return wrapper

    return decorator


def require_service(service_name: str):
    """
    Decorator to require a specific service for a test.

    Args:
        service_name: Name of the required service

    Usage:
        @require_service("postgresql")
        def test_with_postgres(self):
            # Test that requires PostgreSQL
    """

    def decorator(func):
        def wrapper(self, *args, **kwargs):
            if hasattr(self, "_check_service_health"):
                if not self._check_service_health(service_name):
                    pytest.skip(f"Service {service_name} not available")
            return func(self, *args, **kwargs)

        return wrapper

    return decorator


# Export main classes
__all__ = [
    "DockerTestBase",
    "DockerIntegrationTestBase",
    "DockerE2ETestBase",
    "DockerServiceError",
    "skip_if_docker_unavailable",
    "require_service",
]
