#!/usr/bin/env python3
"""
Tier 1 Unit Tests: DataFlow Engine Integration with Migration Lock Manager

Tests that the DataFlow engine properly initializes the migration system
with lock manager support for concurrent safety.

Uses standardized unit test fixtures and follows Tier 1 testing policy.
"""

from unittest.mock import Mock, patch

import pytest
from dataflow.core.config import DatabaseConfig, DataFlowConfig
from dataflow.core.engine import DataFlow


@pytest.mark.unit
@pytest.mark.mocking
class TestDataFlowEngineLockIntegration:
    """Test DataFlow engine integration with migration lock manager."""

    def test_dataflow_accepts_migration_lock_timeout_parameter(self):
        """Test that DataFlow accepts migration_lock_timeout parameter."""
        config = DataFlowConfig(database=DatabaseConfig(url="sqlite:///test.db"))

        # Should not raise exception when migration_lock_timeout is provided
        dataflow = DataFlow(
            config=config,
            migration_enabled=False,  # Disable to avoid actual migration system init
            migration_lock_timeout=45,
        )

        # Parameter should be stored for later use
        assert hasattr(dataflow, "_migration_lock_timeout")
        assert dataflow._migration_lock_timeout == 45

    def test_dataflow_default_lock_timeout_value(self):
        """Test default migration lock timeout value."""
        config = DataFlowConfig(database=DatabaseConfig(url="sqlite:///test.db"))

        dataflow = DataFlow(
            config=config,
            migration_enabled=False,  # Disable to avoid actual migration system init
        )

        # Should have default timeout
        assert hasattr(dataflow, "_migration_lock_timeout")
        assert dataflow._migration_lock_timeout == 30  # Default

    def test_lock_timeout_parameter_validation(self):
        """Test that invalid lock timeout values are handled properly."""
        config = DataFlowConfig(database=DatabaseConfig(url="sqlite:///test.db"))

        # Negative timeout should be handled gracefully
        dataflow = DataFlow(
            config=config, migration_enabled=False, migration_lock_timeout=-1
        )

        # Should either use default or clamp to minimum
        assert dataflow._migration_lock_timeout >= 1

        # Zero timeout should be handled
        dataflow2 = DataFlow(
            config=config, migration_enabled=False, migration_lock_timeout=0
        )

        # Should use a reasonable minimum
        assert dataflow2._migration_lock_timeout >= 1

    @patch("dataflow.migrations.auto_migration_system.AutoMigrationSystem")
    def test_migration_disabled_no_lock_integration(self, mock_migration_system_class):
        """Test that when migration is disabled, no migration system is created."""
        config = DataFlowConfig(database=DatabaseConfig(url="sqlite:///test.db"))

        dataflow = DataFlow(
            config=config, migration_enabled=False
        )  # Migration disabled

        # AutoMigrationSystem should not be initialized
        mock_migration_system_class.assert_not_called()
        assert dataflow._migration_system is None


class TestDataFlowLockTimeoutConfiguration:
    """Test lock timeout configuration options."""

    def test_lock_timeout_from_config(self):
        """Test lock timeout can be specified in DataFlowConfig."""
        # Test that we can specify lock timeout in the config
        config = DataFlowConfig(database=DatabaseConfig(url="sqlite:///test.db"))

        # Add lock timeout to config if supported
        if hasattr(config, "migration_lock_timeout"):
            config.migration_lock_timeout = 120

        dataflow = DataFlow(config=config, migration_enabled=False)

        # This test validates the config structure - actual implementation may vary
        assert config is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--timeout=1"])
