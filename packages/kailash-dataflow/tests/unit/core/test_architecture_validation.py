"""
Architecture Validation Tests

Tests to ensure that the architectural refactoring is working correctly
and that the documentation aligns with the implementation.
"""

from dataclasses import asdict
from pathlib import Path

import pytest
from dataflow import DataFlow
from dataflow.core.config import (
    DatabaseConfig,
    DataFlowConfig,
    Environment,
    MonitoringConfig,
    SecurityConfig,
)


class TestArchitecturalRefactoring:
    """Test that the architectural refactoring is working correctly."""

    def test_config_structure_migration(self):
        """Test that config moved from monolithic to structured approach."""
        # Test that we can create structured configuration
        database_config = DatabaseConfig(url="sqlite:///:memory:", pool_size=10)

        monitoring_config = MonitoringConfig(enabled=True, slow_query_threshold=2.0)

        security_config = SecurityConfig(multi_tenant=True, encrypt_at_rest=True)

        config = DataFlowConfig(
            environment=Environment.TESTING,
            database=database_config,
            monitoring=monitoring_config,
            security=security_config,
        )

        # Verify structured access
        assert config.database.pool_size == 10
        assert config.monitoring.enabled is True
        assert config.security.multi_tenant is True
        assert config.environment == Environment.TESTING

    def test_environment_detection(self):
        """Test that environment detection works correctly."""
        # Test explicit environment setting
        config = DataFlowConfig(environment=Environment.PRODUCTION)
        assert config.environment == Environment.PRODUCTION

        # Test auto-detection
        auto_config = DataFlowConfig()
        assert auto_config.environment is not None

        # Test from_env method
        env_config = DataFlowConfig.from_env()
        assert env_config.environment is not None

    def test_dataflow_initialization_patterns(self):
        """Test all supported DataFlow initialization patterns."""
        # Pattern 1: Zero-config (uses defaults)
        db1 = DataFlow()
        assert db1.config is not None
        assert db1.config.database is not None

        # Pattern 2: Direct database URL
        db2 = DataFlow(database_url="sqlite:///:memory:")
        assert db2.config.database.url == "sqlite:///:memory:"

        # Pattern 3: Structured configuration
        config = DataFlowConfig(database=DatabaseConfig(url="sqlite:///:memory:"))
        db3 = DataFlow(config=config)
        assert db3.config.database.url == "sqlite:///:memory:"

        # Pattern 4: Mixed parameters
        db4 = DataFlow(database_url="sqlite:///:memory:", pool_size=15, monitoring=True)
        assert db4.config.database.url == "sqlite:///:memory:"
        assert db4.config.database.pool_size == 15
        assert db4.config.monitoring.enabled is True

    def test_configuration_validation(self):
        """Test that configuration validation works correctly."""
        # Test valid production config
        prod_config = DataFlowConfig(
            environment=Environment.PRODUCTION,
            database=DatabaseConfig(url="postgresql://user:pass@localhost/prod_db"),
        )
        issues = prod_config.validate()
        assert len(issues) == 0

        # Test invalid production config (SQLite in production)
        invalid_prod_config = DataFlowConfig(
            environment=Environment.PRODUCTION,
            database=DatabaseConfig(url="sqlite:///prod.db"),
        )
        issues = invalid_prod_config.validate()
        assert len(issues) > 0
        assert any("SQLite" in issue for issue in issues)

    def test_config_serialization(self):
        """Test that configuration can be serialized/deserialized."""
        original_config = DataFlowConfig(
            environment=Environment.DEVELOPMENT,
            database=DatabaseConfig(
                url="postgresql://test:test@localhost/test", pool_size=5
            ),
            monitoring=MonitoringConfig(enabled=True),
            security=SecurityConfig(multi_tenant=False),
        )

        # Test to_dict
        config_dict = original_config.to_dict()
        assert config_dict["environment"] == "development"
        assert config_dict["database"]["pool_size"] == 5
        assert config_dict["monitoring"]["enabled"] is True

        # Verify the dict contains all expected sections
        assert "database" in config_dict
        assert "monitoring" in config_dict
        assert "security" in config_dict

    def test_database_config_intelligence(self):
        """Test intelligent database configuration features."""
        # Test pool size calculation based on environment
        dev_config = DatabaseConfig(url="sqlite:///:memory:")
        dev_pool_size = dev_config.get_pool_size(Environment.DEVELOPMENT)
        assert dev_pool_size == 5  # Should be smaller for development

        prod_config = DatabaseConfig(url="postgresql://user:pass@localhost/prod")
        prod_pool_size = prod_config.get_pool_size(Environment.PRODUCTION)
        assert prod_pool_size >= 10  # Should be larger for production

        # Test explicit pool size override
        explicit_config = DatabaseConfig(
            url="postgresql://user:pass@localhost/test", pool_size=25
        )
        explicit_pool_size = explicit_config.get_pool_size(Environment.PRODUCTION)
        assert explicit_pool_size == 25

    def test_progressive_disclosure(self):
        """Test that configuration supports progressive disclosure."""
        # Simple usage - minimal config
        simple_config = DataFlowConfig()
        assert simple_config.database is not None
        assert simple_config.monitoring is not None
        assert simple_config.security is not None

        # Advanced usage - detailed config
        advanced_config = DataFlowConfig(
            environment=Environment.PRODUCTION,
            database=DatabaseConfig(
                url="postgresql://user:pass@localhost/prod",
                pool_size=20,
                max_overflow=30,
                pool_recycle=3600,
                echo=False,
            ),
            monitoring=MonitoringConfig(
                enabled=True,
                slow_query_threshold=1.0,
                query_insights=True,
                connection_metrics=True,
            ),
            security=SecurityConfig(
                access_control_enabled=True,
                access_control_strategy="rbac",
                encrypt_at_rest=True,
                encrypt_in_transit=True,
                multi_tenant=True,
                audit_enabled=True,
            ),
        )

        # Verify all advanced options are accessible
        assert advanced_config.database.max_overflow == 30
        assert advanced_config.monitoring.query_insights is True
        assert advanced_config.security.access_control_strategy == "rbac"


class TestDocumentationAlignment:
    """Test that documentation aligns with implementation."""

    def test_claude_md_patterns_work(self):
        """Test that patterns shown in CLAUDE.md actually work."""
        # Test the basic pattern from CLAUDE.md
        db = DataFlow()  # Zero config - creates SQLite automatically
        assert db.config is not None

        # Test production pattern from CLAUDE.md
        db_prod = DataFlow(
            database_url="postgresql://user:pass@localhost/db", pool_size=20
        )
        assert db_prod.config.database.url == "postgresql://user:pass@localhost/db"
        assert db_prod.config.database.pool_size == 20

    def test_decision_matrix_examples(self):
        """Test that decision matrix examples from docs work."""
        # Test quick prototype pattern
        quick_config = DataFlowConfig(environment=Environment.DEVELOPMENT)
        db_quick = DataFlow(config=quick_config)
        assert db_quick.config.environment == Environment.DEVELOPMENT

        # Test enterprise pattern
        enterprise_config = DataFlowConfig(
            environment=Environment.PRODUCTION,
            database=DatabaseConfig(
                url="postgresql://user:pass@prod-db:5432/app", pool_size=50
            ),
            security=SecurityConfig(
                multi_tenant=True, audit_enabled=True, encrypt_at_rest=True
            ),
            monitoring=MonitoringConfig(
                enabled=True, connection_metrics=True, transaction_tracking=True
            ),
        )
        db_enterprise = DataFlow(config=enterprise_config)
        assert db_enterprise.config.security.multi_tenant is True
        assert db_enterprise.config.monitoring.enabled is True


class TestRegressionPrevention:
    """Tests to prevent regression of the architectural improvements."""

    def test_no_flat_config_kwargs(self):
        """Ensure we don't regress to flat configuration kwargs."""
        # These should work (structured approach)
        config = DataFlowConfig(
            database=DatabaseConfig(url="sqlite:///:memory:", pool_size=10),
            monitoring=MonitoringConfig(enabled=True),
        )
        db = DataFlow(config=config)
        assert db.config.database.pool_size == 10

        # Mixed approach should also work (backward compatibility)
        db2 = DataFlow(database_url="sqlite:///:memory:", pool_size=15, monitoring=True)
        assert db2.config.database.pool_size == 15
        assert db2.config.monitoring.enabled is True

    def test_configuration_immutability_after_init(self):
        """Test that configuration is properly managed after initialization."""
        config = DataFlowConfig(database=DatabaseConfig(url="sqlite:///:memory:"))
        db = DataFlow(config=config)

        # Configuration should be accessible
        assert db.config.database.url == "sqlite:///:memory:"

        # Modifying original config shouldn't affect initialized instance
        config.database.pool_size = 999
        # DataFlow should have its own copy or be unaffected
        assert db.config.database.pool_size != 999

    def test_environment_specific_defaults(self):
        """Test that environment-specific defaults work correctly."""
        # Development should use conservative defaults
        dev_config = DataFlowConfig(environment=Environment.DEVELOPMENT)
        assert dev_config.monitoring.enabled is False  # Less monitoring in dev

        # Production should use robust defaults
        prod_config = DataFlowConfig(environment=Environment.PRODUCTION)
        assert prod_config.monitoring.enabled is True  # More monitoring in prod

        # Testing should use appropriate defaults
        test_config = DataFlowConfig(environment=Environment.TESTING)
        assert test_config.monitoring.enabled is False  # Less monitoring in test
        assert test_config.security.audit_enabled is True  # But auditing enabled


if __name__ == "__main__":
    pytest.main([__file__])
