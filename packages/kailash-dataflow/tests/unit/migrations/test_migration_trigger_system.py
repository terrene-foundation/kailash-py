"""
Unit tests for Migration Trigger System Configuration.

Tests the configuration options for controlling migration behavior.
"""

from unittest.mock import Mock, patch

import pytest


class TestMigrationTriggerSystem:
    """Test migration system configuration options."""

    def test_auto_migrate_config_option_exists(self):
        """Test that auto_migrate configuration option exists."""
        from dataflow.core.config import DataFlowConfig

        # Test that config accepts auto_migrate parameter
        config = DataFlowConfig(auto_migrate=False)
        assert not config.auto_migrate

        # Test default value
        default_config = DataFlowConfig()
        assert hasattr(default_config, "auto_migrate")
        assert default_config.auto_migrate  # Default should be True

    def test_migration_directory_config_option(self):
        """Test that migration directory can be configured."""
        from pathlib import Path

        from dataflow.core.config import DataFlowConfig

        # Test custom migration directory
        config = DataFlowConfig(migration_directory="custom_migrations")
        assert config.migration_directory == Path("custom_migrations")

        # Test default value
        default_config = DataFlowConfig()
        assert default_config.migration_directory == Path("migrations")
