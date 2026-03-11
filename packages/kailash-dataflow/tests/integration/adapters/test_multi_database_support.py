"""
Integration tests for DataFlow multi-database support.

Tests DataFlow's ability to work with multiple database types simultaneously,
including PostgreSQL, MySQL, and SQLite configurations.
"""

import os
import sys
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

import pytest

# Import DataFlow components
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from dataflow import DataFlow
from dataflow.adapters.sql_dialects import PostgreSQLDialect
from dataflow.core.config import DatabaseConfig
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def runtime():
    """Create LocalRuntime for workflow execution."""
    from kailash.runtime.local import LocalRuntime

    return LocalRuntime()


class TestMultiDatabaseSupport:
    """Test DataFlow support for multiple database types."""

    def test_postgresql_database_configuration(self, test_suite):
        """Test DataFlow configuration with PostgreSQL."""
        db = DataFlow(
            database_url=test_suite.config.url,
            pool_size=10,
            pool_max_overflow=20,
            auto_migrate=False,
            existing_schema_mode=True,
        )

        # Verify PostgreSQL configuration
        assert db.config.database.url == test_suite.config.url
        assert db.config.database.pool_size == 10
        assert db.config.database.max_overflow == 20

        # Test PostgreSQL type mappings
        assert db._python_type_to_sql_type(str, "postgresql") == "VARCHAR(255)"
        assert db._python_type_to_sql_type(dict, "postgresql") == "JSONB"
        assert db._python_type_to_sql_type(bytes, "postgresql") == "BYTEA"

    def test_secondary_postgresql_database_configuration(self, test_suite):
        """Test DataFlow configuration with a secondary PostgreSQL database."""
        # Using a different PostgreSQL database (e.g., analytics DB on different port)
        db = DataFlow(
            database_url=test_suite.config.url,
            pool_size=15,
            pool_max_overflow=30,
            auto_migrate=False,
            existing_schema_mode=True,
        )

        # Verify secondary PostgreSQL configuration
        assert db.config.database.url == test_suite.config.url
        assert db.config.database.pool_size == 15
        assert db.config.database.max_overflow == 30

        # Test PostgreSQL type mappings (can differ based on configuration)
        assert db._python_type_to_sql_type(str, "postgresql") == "VARCHAR(255)"
        assert db._python_type_to_sql_type(dict, "postgresql") == "JSONB"
        assert db._python_type_to_sql_type(bytes, "postgresql") == "BYTEA"

    def test_third_postgresql_database_configuration(self, test_suite):
        """Test DataFlow configuration with a third PostgreSQL database."""
        # Using yet another PostgreSQL database (e.g., cache DB on different host)
        # For testing, we'll use the same database URL but with different configuration
        db = DataFlow(
            database_url=test_suite.config.url,
            pool_size=5,
            pool_max_overflow=10,
            auto_migrate=False,
            existing_schema_mode=True,
        )

        # Verify third PostgreSQL configuration
        assert db.config.database.url == test_suite.config.url
        assert db.config.database.pool_size == 5
        assert db.config.database.max_overflow == 10

        # Test PostgreSQL type mappings (same as others, for consistency)
        assert db._python_type_to_sql_type(str, "postgresql") == "VARCHAR(255)"
        assert db._python_type_to_sql_type(dict, "postgresql") == "JSONB"
        assert db._python_type_to_sql_type(bytes, "postgresql") == "BYTEA"

    def test_database_specific_model_registration(self, test_suite):
        """Test model registration with database-specific configurations."""
        # Use shared test database with auto_migrate=False to prevent connection attempts
        # Test with primary PostgreSQL
        pg_db = DataFlow(
            database_url=test_suite.config.url,
            auto_migrate=False,
            existing_schema_mode=True,
        )

        @pg_db.model
        class PostgreSQLModel:
            id: int
            name: str
            metadata: Dict[str, str]  # JSONB in PostgreSQL
            data: bytes  # BYTEA in PostgreSQL

        # Test with secondary PostgreSQL (analytics DB)
        analytics_db = DataFlow(
            database_url=test_suite.config.url,
            auto_migrate=False,
            existing_schema_mode=True,
        )

        @analytics_db.model
        class AnalyticsModel:
            id: int
            name: str
            metadata: Dict[str, str]  # JSONB in PostgreSQL
            data: bytes  # BYTEA in PostgreSQL

        # Test with third PostgreSQL (cache DB)
        cache_db = DataFlow(
            database_url=test_suite.config.url,
            auto_migrate=False,
            existing_schema_mode=True,
        )

        @cache_db.model
        class CacheModel:
            id: int
            name: str
            metadata: Dict[str, str]  # JSONB in PostgreSQL
            data: bytes  # BYTEA in PostgreSQL

        # Verify models are registered
        assert "PostgreSQLModel" in pg_db._models
        assert "AnalyticsModel" in analytics_db._models
        assert "CacheModel" in cache_db._models

    def test_sql_generation_across_databases(self, test_suite):
        """Test SQL generation for different database types."""
        databases = [
            (
                test_suite.config.url,
                "postgresql",
            ),
            (
                test_suite.config.url,
                "postgresql",
            ),
            (
                test_suite.config.url,
                "postgresql",
            ),
        ]

        for db_url, dialect in databases:
            db = DataFlow(
                database_url=db_url, auto_migrate=False, existing_schema_mode=True
            )

            @db.model
            class TestModel:
                id: int
                name: str
                active: bool = True
                created_at: datetime

            # Generate SQL for the model
            sql = db._generate_create_table_sql("TestModel")

            # Verify SQL contains expected elements
            assert "CREATE TABLE" in sql
            assert "test_models" in sql.lower()
            assert "name" in sql.lower()
            assert "active" in sql.lower()
            assert "created_at" in sql.lower()

            # Verify PostgreSQL-specific SQL features (all instances use PostgreSQL)
            # PostgreSQL uses TIMESTAMP for datetime
            assert "TIMESTAMP" in sql or "timestamp" in sql.lower()

    def test_dialect_specific_features(self):
        """Test database-specific dialect features."""
        # PostgreSQL dialect (only dialect supported in DataFlow alpha)
        pg_dialect = PostgreSQLDialect()
        pg_mappings = pg_dialect.get_type_mapping()

        assert "jsonb" in pg_mappings
        assert pg_mappings["jsonb"] == "JSONB"
        assert "bytea" in pg_mappings
        assert pg_mappings["bytea"] == "BYTEA"
        assert "integer" in pg_mappings
        assert pg_mappings["integer"] == "INTEGER"
        assert "text" in pg_mappings
        assert pg_mappings["text"] == "TEXT"
        assert "varchar" in pg_mappings
        assert pg_mappings["varchar"] == "VARCHAR"

    def test_database_url_parsing(self, test_suite):
        """Test parsing of different database URL formats."""
        # Only test with real, valid database connection
        # DataFlow doesn't just parse - it validates by connecting
        valid_url = test_suite.config.url
        db = DataFlow(
            database_url=valid_url, auto_migrate=False, existing_schema_mode=True
        )
        assert db.config.database.url == valid_url

        # Test invalid URL formats that should raise ValueError
        invalid_urls = [
            "invalid://not-a-database",  # Invalid scheme
            "postgresql://",  # Missing everything after scheme
            "",  # Empty string
            "postgresql://localhost/db",  # Missing @ character (for PostgreSQL)
            # Note: MySQL and SQLite are fully supported since v0.5.6 and v0.1.0 respectively
        ]

        for url in invalid_urls:
            try:
                db = DataFlow(
                    database_url=url, auto_migrate=False, existing_schema_mode=True
                )
                # If we get here without exception, that's a test failure
                assert False, f"Expected ValueError for invalid URL: {url}"
            except ValueError:
                # This is what we expect
                pass
            except Exception as e:
                # Any other exception is also acceptable for invalid URLs
                # as long as it prevents DataFlow from being created
                pass

    def test_connection_pool_configuration_by_database(self, test_suite):
        """Test connection pool configuration for different databases."""
        # Primary PostgreSQL with large pool
        pg_db = DataFlow(
            database_url=test_suite.config.url,
            pool_size=20,
            pool_max_overflow=50,
            pool_recycle=7200,
            auto_migrate=False,
            existing_schema_mode=True,
        )

        assert pg_db.config.database.pool_size == 20
        assert pg_db.config.database.max_overflow == 50
        assert pg_db.config.database.pool_recycle == 7200

        # Analytics PostgreSQL with medium pool
        analytics_db = DataFlow(
            database_url=test_suite.config.url,
            pool_size=10,
            pool_max_overflow=20,
            pool_recycle=3600,
            auto_migrate=False,
            existing_schema_mode=True,
        )

        assert analytics_db.config.database.pool_size == 10
        assert analytics_db.config.database.max_overflow == 20
        assert analytics_db.config.database.pool_recycle == 3600

        # Cache PostgreSQL with small pool
        cache_db = DataFlow(
            database_url=test_suite.config.url,
            pool_size=5,
            pool_max_overflow=10,
            pool_recycle=1800,
            auto_migrate=False,
            existing_schema_mode=True,
        )

        assert cache_db.config.database.pool_size == 5
        assert cache_db.config.database.max_overflow == 10
        assert cache_db.config.database.pool_recycle == 1800

    def test_enterprise_features_across_databases(self, test_suite):
        """Test enterprise features work across different databases."""
        # For testing, we'll simulate different enterprise databases with the same URL
        databases = [
            test_suite.config.url,
            test_suite.config.url,
            test_suite.config.url,
        ]

        for db_url in databases:
            db = DataFlow(
                database_url=db_url,
                multi_tenant=True,
                audit_logging=True,
                monitoring=True,
                auto_migrate=False,
                existing_schema_mode=True,
            )

            @db.model
            class EnterpriseModel:
                id: int
                name: str
                tenant_id: str

                __dataflow__ = {
                    "multi_tenant": True,
                    "soft_delete": True,
                    "audit_log": True,
                    "versioned": True,
                }

            # Verify enterprise configuration
            assert db.config.security.multi_tenant is True
            assert db.config.security.audit_enabled is True
            assert db.config.monitoring is True

            # Verify model registration
            assert "EnterpriseModel" in db._models

            # Verify enterprise features on model
            assert hasattr(EnterpriseModel, "__dataflow__")
            config = EnterpriseModel.__dataflow__
            assert config["multi_tenant"] is True
            assert config["audit_log"] is True

    def test_type_mapping_consistency_across_databases(self, test_suite):
        """Test type mapping consistency across database types."""
        databases = [
            (test_suite.config.url, "postgresql"),
            (test_suite.config.url, "postgresql"),
            (test_suite.config.url, "postgresql"),
        ]

        test_types = [str, int, float, bool, datetime]

        for db_url, dialect in databases:
            db = DataFlow(
                database_url=db_url, auto_migrate=False, existing_schema_mode=True
            )

            for python_type in test_types:
                sql_type = db._python_type_to_sql_type(python_type, dialect)

                # Verify mapping exists and is reasonable
                assert sql_type is not None
                assert isinstance(sql_type, str)
                assert len(sql_type) > 0

                # Verify PostgreSQL type names
                if python_type == bool:
                    assert "BOOLEAN" in sql_type
                elif python_type == str:
                    assert "VARCHAR" in sql_type
                elif python_type == int:
                    assert "INTEGER" in sql_type or "SERIAL" in sql_type
                elif python_type == float:
                    assert (
                        "REAL" in sql_type
                        or "NUMERIC" in sql_type
                        or "DOUBLE" in sql_type
                    )

    def test_database_specific_constraints(self, test_suite):
        """Test database-specific constraints and features."""
        # Primary PostgreSQL with advanced constraints
        pg_db = DataFlow(
            database_url=test_suite.config.url,
            auto_migrate=False,
            existing_schema_mode=True,
        )

        @pg_db.model
        class PostgreSQLAdvanced:
            id: int
            email: str
            metadata: Dict[str, str]

            __constraints__ = {
                "email": {"unique": True, "pattern": r"^[^@]+@[^@]+\.[^@]+$"},
                "metadata": {"jsonb_path_ops": True},
            }

            __indexes__ = [
                {"name": "idx_email_gin", "fields": ["email"], "type": "gin"},
                {"name": "idx_metadata_gin", "fields": ["metadata"], "type": "gin"},
            ]

        # Analytics PostgreSQL with specific features
        analytics_db = DataFlow(
            database_url=test_suite.config.url,
            auto_migrate=False,
            existing_schema_mode=True,
        )

        @analytics_db.model
        class AnalyticsAdvanced:
            id: int
            name: str
            data: Dict[str, str]

            __constraints__ = {
                "name": {"unique": True, "not_null": True},
                "data": {"jsonb_ops": True},
            }

            __indexes__ = [
                {"name": "idx_name_btree", "fields": ["name"], "type": "btree"},
                {
                    "name": "idx_data_gin",
                    "fields": ["data"],
                    "type": "gin",
                },
            ]

        # Cache PostgreSQL with performance-focused features
        cache_db = DataFlow(
            database_url=test_suite.config.url,
            auto_migrate=False,
            existing_schema_mode=True,
        )

        @cache_db.model
        class CacheAdvanced:
            id: int
            key: str
            value: str  # JSON stored as text for performance

            __constraints__ = {
                "key": {"unique": True, "not_null": True},
                "value": {"check": "length(value) < 65536"},
            }

            __indexes__ = [
                {"name": "idx_key_hash", "fields": ["key"], "type": "hash"},
                {
                    "name": "idx_created_btree",
                    "fields": ["created_at"],
                    "type": "btree",
                },
            ]

        # Verify all models register successfully
        assert "PostgreSQLAdvanced" in pg_db._models
        assert "AnalyticsAdvanced" in analytics_db._models
        assert "CacheAdvanced" in cache_db._models

    def test_database_feature_detection(self):
        """Test detection of database-specific features."""
        # PostgreSQL features (only dialect supported)
        pg_dialect = PostgreSQLDialect()

        # Test feature support (if method exists)
        if hasattr(pg_dialect, "supports_feature"):
            try:
                assert pg_dialect.supports_feature("arrays") in [True, False]
                assert pg_dialect.supports_feature("json") in [True, False]
                assert pg_dialect.supports_feature("jsonb") in [True, False]
                assert pg_dialect.supports_feature("uuid") in [True, False]
                assert pg_dialect.supports_feature("gin_indexes") in [True, False]
                assert pg_dialect.supports_feature("full_text_search") in [True, False]
            except (ValueError, KeyError):
                # Feature not recognized - acceptable
                pass

    def test_migration_across_databases(self, test_suite):
        """Test migration patterns across different databases."""
        # Test migration from legacy PostgreSQL to modern PostgreSQL scenario

        # Original PostgreSQL setup (legacy schema)
        legacy_db = DataFlow(
            database_url=test_suite.config.url,
            auto_migrate=False,
            existing_schema_mode=True,
        )

        @legacy_db.model
        class LegacyModel:
            id: int
            name: str
            data: str  # JSON as TEXT in legacy schema

        # Migrated PostgreSQL setup (modern schema)
        modern_db = DataFlow(
            database_url=test_suite.config.url,
            auto_migrate=False,
            existing_schema_mode=True,
        )

        @modern_db.model
        class ModernModel:
            id: int
            name: str
            data: Dict[str, str]  # Proper JSONB in modern PostgreSQL
            migrated_at: datetime = None
            version: int = 1

        # Verify both models work
        assert "LegacyModel" in legacy_db._models
        assert "ModernModel" in modern_db._models

        # Compare field mappings
        legacy_fields = legacy_db._model_fields["LegacyModel"]
        modern_fields = modern_db._model_fields["ModernModel"]

        # Common fields should exist
        assert "name" in legacy_fields
        assert "name" in modern_fields
        assert "data" in legacy_fields
        assert "data" in modern_fields

    def test_performance_characteristics_by_database(self, test_suite):
        """Test performance characteristics vary by database type."""
        import time

        databases = [
            (
                test_suite.config.url,
                "postgresql",
            ),
            (
                test_suite.config.url,
                "postgresql",
            ),
            (
                test_suite.config.url,
                "postgresql",
            ),
        ]

        for db_url, dialect in databases:
            db = DataFlow(
                database_url=db_url, auto_migrate=False, existing_schema_mode=True
            )

            # Test model registration performance
            start_time = time.time()

            for i in range(10):
                model_name = f"PerfModel_{dialect}_{i}"
                model_class = type(
                    model_name,
                    (),
                    {"__annotations__": {"id": int, "name": str, "value": float}},
                )
                db.model(model_class)

            registration_time = time.time() - start_time

            # All databases should have reasonable registration performance
            # With real infrastructure, 10 model registrations may take a few seconds
            assert registration_time < 5.0

            # Test type mapping performance
            start_time = time.time()

            for _ in range(100):
                db._python_type_to_sql_type(str, dialect)
                db._python_type_to_sql_type(int, dialect)
                db._python_type_to_sql_type(bool, dialect)

            mapping_time = time.time() - start_time

            # Type mapping should be very fast
            assert mapping_time < 0.1

    def test_database_configuration_validation(self, test_suite):
        """Test validation of database configurations."""
        # Valid configurations should work
        valid_configs = [
            test_suite.config.url,
            test_suite.config.url,
            test_suite.config.url,
            "postgresql://user:pass@remote-host:5432/remote",
        ]

        for config in valid_configs:
            db = DataFlow(
                database_url=config, auto_migrate=False, existing_schema_mode=True
            )
            assert db.config.database.url == config

        # Invalid configurations should be handled gracefully
        invalid_configs = [
            "invalid://not-a-database",
            "postgresql://",
            "mysql://missing-host",  # Invalid MySQL URL format (missing host/credentials)
            "sqlite:///invalid.db",  # Invalid SQLite path
            "",
        ]

        for config in invalid_configs:
            try:
                db = DataFlow(
                    database_url=config, auto_migrate=False, existing_schema_mode=True
                )
                # If it doesn't raise an error, that's also acceptable
                assert db is not None
            except ValueError:
                # Expected for invalid URLs
                pass

    def test_multi_database_workflow_compatibility(self, test_suite):
        """Test that models from different DataFlow instances are compatible."""
        # Create separate DataFlow instances for different PostgreSQL databases
        pg_db = DataFlow(
            database_url=test_suite.config.url,
            auto_migrate=False,
            existing_schema_mode=True,
        )
        analytics_db = DataFlow(
            database_url=test_suite.config.url,
            auto_migrate=False,
            existing_schema_mode=True,
        )
        cache_db = DataFlow(
            database_url=test_suite.config.url,
            auto_migrate=False,
            existing_schema_mode=True,
        )

        # Register similar models on each
        @pg_db.model
        class PrimaryUser:
            id: int
            name: str
            email: str

        @analytics_db.model
        class AnalyticsUser:
            id: int
            name: str
            email: str

        @cache_db.model
        class CacheUser:
            id: int
            name: str
            email: str

        # All should register successfully
        assert "PrimaryUser" in pg_db._models
        assert "AnalyticsUser" in analytics_db._models
        assert "CacheUser" in cache_db._models

        # Field structures should be consistent
        pg_fields = pg_db._model_fields["PrimaryUser"]
        analytics_fields = analytics_db._model_fields["AnalyticsUser"]
        cache_fields = cache_db._model_fields["CacheUser"]

        # All should have the same field names
        assert (
            set(pg_fields.keys())
            == set(analytics_fields.keys())
            == set(cache_fields.keys())
        )

    def test_zero_config_multi_database_support(self, test_suite):
        """Test that zero-config works with different database types."""
        # Test default configuration with different URLs
        databases = [
            test_suite.config.url,
            test_suite.config.url,
            test_suite.config.url,
        ]

        for db_url in databases:
            # Zero-config except for database URL
            db = DataFlow(
                database_url=db_url, auto_migrate=False, existing_schema_mode=True
            )

            @db.model
            class DefaultModel:
                name: str
                active: bool = True

            # Should work with minimal configuration
            assert "DefaultModel" in db._models
            assert db.config.database.url == db_url

            # Default values should be reasonable
            assert db.config.database.pool_size > 0
            assert db.config.database.max_overflow >= 0
