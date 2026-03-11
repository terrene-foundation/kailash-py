"""
Docker test environment configuration for DataFlow integration tests.

This module provides database configuration for testing against Docker services.
"""

# PostgreSQL test database configuration
DATABASE_CONFIG = {
    "database_url": "postgresql://test_user:test_password@localhost:5434/kailash_test",
    "host": "localhost",
    "port": 5434,
    "database": "kailash_test",
    "user": "test_user",
    "password": "test_password",
    "pool_size": 5,
    "pool_max_overflow": 10,
    "pool_recycle": 3600,
    "echo": False,  # Set to True for SQL logging during debug
}

# Alternative configuration with individual parameters
DATABASE_CONFIG_SPLIT = {
    "driver": "postgresql",
    "host": "localhost",
    "port": 5434,
    "database": "dataflow_test",
    "username": "dataflow_test",
    "password": "dataflow_test",
    "pool_size": 5,
    "pool_max_overflow": 10,
}

# Redis test configuration (for caching tests)
REDIS_CONFIG = {"host": "localhost", "port": 6380, "db": 0, "password": None}

# Test environment settings
TEST_ENVIRONMENT = {
    "environment": "testing",
    "debug": True,
    "monitoring": False,
    "multi_tenant": False,
}
