"""
Unit tests for LegacyAPICompatibility backward compatibility system.

This module tests the backward compatibility system that ensures:
- Existing create_tables() calls still work
- Configuration migration and upgrade paths
- Zero breaking changes for existing applications
- Seamless transition from manual to auto-migration mode
"""

import unittest
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, Mock, call, patch

import pytest


@dataclass
class DataFlowApp:
    """Mock DataFlow application for testing."""

    config: Dict[str, Any]
    models: List[str]
    database_url: str
    migration_enabled: bool = False


@dataclass
class ProductionConfig:
    """Mock production configuration."""

    database_url: str
    pool_size: int
    migration_settings: Dict[str, Any]
    monitoring_enabled: bool = True


class TestLegacyAPICompatibility(unittest.TestCase):
    """Test suite for LegacyAPICompatibility class."""

    def setUp(self):
        """Set up test fixtures."""
        # Import the real class when implemented
        from dataflow.compatibility.legacy_support import LegacyAPICompatibility

        self.compatibility_checker = LegacyAPICompatibility()

    def test_legacy_compatibility_initialization(self):
        """Test LegacyAPICompatibility initializes correctly."""
        self.assertIsNotNone(self.compatibility_checker)

    def test_validate_create_tables_compatibility_success(self):
        """Test that create_tables() method still works as before."""
        # Setup mock DataFlow engine with create_tables method
        mock_engine = Mock()
        mock_engine.create_tables = Mock()
        mock_engine.create_tables.return_value = None

        # Add some mock models
        mock_engine._models = {
            "User": {"fields": {"name": {"type": str, "required": True}}},
            "Order": {"fields": {"total": {"type": float, "required": True}}},
        }

        # Execute compatibility validation
        result = self.compatibility_checker.validate_create_tables_compatibility()

        # Import the correct CompatibilityReport type
        from dataflow.compatibility.legacy_support import CompatibilityReport

        # Verify compatibility report
        self.assertIsInstance(result, CompatibilityReport)
        self.assertTrue(result.is_compatible)
        self.assertEqual(len(result.issues), 0)
        self.assertIn("create_tables", result.tested_methods)

    def test_validate_create_tables_compatibility_with_issues(self):
        """Test create_tables compatibility when issues are detected."""
        # Setup mock engine with problematic create_tables implementation
        mock_engine = Mock()
        mock_engine.create_tables = Mock(
            side_effect=Exception("Method signature changed")
        )

        # Execute compatibility validation with mock engine
        result = self.compatibility_checker.validate_create_tables_compatibility(
            test_engine=mock_engine
        )

        # Verify issues are detected
        self.assertFalse(result.is_compatible)
        self.assertGreater(len(result.issues), 0)
        # The error is detected during functionality testing, not signature testing
        self.assertIn("functionality", result.issues[0]["description"].lower())

    def test_test_manual_migration_workflow_success(self):
        """Test existing manual migration patterns work correctly."""
        # Setup mock manual migration workflow
        with patch("dataflow.core.engine.DataFlow") as MockDataFlow:
            mock_engine = MockDataFlow.return_value
            mock_engine.create_tables = Mock()
            mock_engine._models = {"User": {"fields": {"name": {"type": str}}}}

            # Execute manual migration workflow test
            result = self.compatibility_checker.test_manual_migration_workflow()

            # Import the correct WorkflowResult type
            from dataflow.compatibility.legacy_support import WorkflowResult

            # Verify manual workflow still works
            self.assertIsInstance(result, WorkflowResult)
            self.assertTrue(result.success)
            self.assertIn("manual_migration", result.workflow_type)
            self.assertEqual(len(result.errors), 0)

    def test_test_manual_migration_workflow_with_errors(self):
        """Test manual migration workflow when errors occur."""
        # Setup mock that raises errors
        with patch("dataflow.core.engine.DataFlow") as MockDataFlow:
            mock_engine = MockDataFlow.return_value
            mock_engine.create_tables = Mock(side_effect=Exception("Migration failed"))

            # Execute manual migration workflow test
            result = self.compatibility_checker.test_manual_migration_workflow()

            # Verify errors are captured
            self.assertFalse(result.success)
            self.assertGreater(len(result.errors), 0)
            self.assertIn("Migration failed", str(result.errors[0]))

    def test_validate_configuration_compatibility_success(self):
        """Test configuration backwards compatibility."""
        # Setup old-style configuration
        old_config = {
            "database_url": "postgresql://user:pass@localhost/db",
            "pool_size": 10,
            "echo": False,
            "migration_enabled": False,  # Old style - manually managed
        }

        # Setup new-style DataFlowConfig mock
        from dataflow.compatibility.legacy_support import DataFlowConfig

        new_config = DataFlowConfig(
            database_url=old_config["database_url"],
            pool_size=old_config["pool_size"],
            echo=old_config["echo"],
        )

        # Execute compatibility validation
        result = self.compatibility_checker.validate_configuration_compatibility(
            old_config, new_config
        )

        # Verify compatibility
        self.assertTrue(result)

    def test_validate_configuration_compatibility_with_breaking_changes(self):
        """Test configuration compatibility when breaking changes exist."""
        # Setup configuration with removed/changed properties
        old_config = {
            "database_url": "postgresql://user:pass@localhost/db",
            "deprecated_setting": "value",  # This setting was removed
            "pool_size": 10,
        }

        # Setup new config that doesn't support deprecated setting
        from dataflow.compatibility.legacy_support import DataFlowConfig

        new_config = DataFlowConfig(
            database_url=old_config["database_url"],
            pool_size=old_config["pool_size"],
            # No deprecated_setting support - this should cause incompatibility
        )

        # Execute compatibility validation
        result = self.compatibility_checker.validate_configuration_compatibility(
            old_config, new_config
        )

        # Verify incompatibility is detected
        self.assertFalse(result)

    def test_configuration_upgrade_path_validation(self):
        """Test that configuration can be upgraded from old to new format."""
        # Setup old configuration format
        old_config = {
            "database_url": "postgresql://user:pass@localhost/db",
            "pool_size": 20,
            "pool_max_overflow": 30,
            "echo": True,
            "multi_tenant": False,
            "cache_enabled": True,
        }

        # Test upgrade path
        upgraded_config = self.compatibility_checker._upgrade_configuration(old_config)

        # Verify upgrade maintains all settings
        self.assertIsNotNone(upgraded_config)
        self.assertEqual(upgraded_config["database"]["url"], old_config["database_url"])
        self.assertEqual(
            upgraded_config["database"]["pool_size"], old_config["pool_size"]
        )
        self.assertEqual(upgraded_config["database"]["echo"], old_config["echo"])

    def test_legacy_api_method_signatures(self):
        """Test that legacy API method signatures are preserved."""
        # Test create_tables signature compatibility
        signature_tests = [
            {
                "method": "create_tables",
                "old_signature": ["database_type"],
                "current_params": ["database_type"],
            },
            {
                "method": "__init__",
                "old_signature": ["database_url", "config", "pool_size"],
                "current_params": [
                    "database_url",
                    "config",
                    "pool_size",
                    "migration_enabled",
                ],
            },
        ]

        for test_case in signature_tests:
            compatibility = (
                self.compatibility_checker._check_method_signature_compatibility(
                    test_case["method"],
                    test_case["old_signature"],
                    test_case["current_params"],
                )
            )

            # All old parameters should be supported
            self.assertTrue(compatibility["is_compatible"])
            self.assertEqual(len(compatibility["missing_params"]), 0)

    def test_backward_compatible_model_registration(self):
        """Test that model registration works with both old and new styles."""
        # Test old-style model registration (without auto-migration)
        with patch("dataflow.core.engine.DataFlow") as MockDataFlow:
            mock_engine = MockDataFlow.return_value
            mock_engine._migration_system = None  # Simulate old system
            mock_engine.model = Mock()

            # Should work without migration system
            result = self.compatibility_checker._test_model_registration_compatibility(
                mock_engine
            )

            self.assertTrue(result["old_style_compatible"])
            self.assertTrue(result["new_style_compatible"])

    def test_auto_migration_opt_in_behavior(self):
        """Test that auto-migration is opt-in and doesn't break existing apps."""
        # Setup DataFlow with migration disabled (default for backward compatibility)
        with patch("dataflow.core.engine.DataFlow") as MockDataFlow:
            mock_engine = MockDataFlow.return_value
            mock_engine._migration_system = None  # Migration disabled by default

            # Test that existing workflows continue to work
            result = self.compatibility_checker._test_opt_in_migration_behavior(
                mock_engine
            )

            self.assertTrue(result["migration_disabled_by_default"])
            self.assertTrue(result["existing_workflows_work"])
            self.assertFalse(result["unexpected_migrations_triggered"])

    def test_database_url_parsing_compatibility(self):
        """Test that database URL parsing remains backward compatible."""
        test_urls = [
            "postgresql://user:pass@localhost/db",
            "postgresql://user@localhost:5434/db",
            "postgres://user:pass@localhost/db",  # Alternative scheme
            ":memory:",  # SQLite memory database
            "sqlite:///path/to/db.sqlite",
        ]

        for url in test_urls:
            # Test that URL parsing still works
            is_compatible = self.compatibility_checker._test_database_url_compatibility(
                url
            )

            self.assertTrue(is_compatible, f"URL parsing failed for: {url}")

    def test_environment_variable_compatibility(self):
        """Test that environment variable usage remains compatible."""
        # Test common environment variables still work
        env_vars = [
            "DATABASE_URL",
            "DATAFLOW_POOL_SIZE",
            "DATAFLOW_ECHO",
            "DATAFLOW_DISABLE_MIGRATIONS",  # New variable should not break old apps
        ]

        compatibility_results = {}
        for var in env_vars:
            compatibility_results[var] = (
                self.compatibility_checker._test_env_var_compatibility(var)
            )

        # All environment variables should be handled gracefully
        for var, is_compatible in compatibility_results.items():
            self.assertTrue(
                is_compatible, f"Environment variable compatibility failed for: {var}"
            )

    def test_connection_pool_backward_compatibility(self):
        """Test that connection pool configuration remains backward compatible."""
        # Test old connection pool parameters
        old_pool_config = {
            "pool_size": 20,
            "pool_max_overflow": 30,
            "pool_recycle": 3600,
            "pool_timeout": 30,
        }

        # Test compatibility
        result = self.compatibility_checker._test_connection_pool_compatibility(
            old_pool_config
        )

        self.assertTrue(result["is_compatible"])
        self.assertEqual(len(result["unsupported_params"]), 0)
        self.assertGreaterEqual(len(result["supported_params"]), 4)

    def test_error_message_compatibility(self):
        """Test that error messages remain consistent for backward compatibility."""
        # Test that error messages haven't changed in breaking ways
        error_scenarios = [
            "invalid_database_url",
            "model_registration_error",
            "connection_pool_exhausted",
            "migration_failure",
        ]

        for scenario in error_scenarios:
            error_format = self.compatibility_checker._get_error_message_format(
                scenario
            )

            # Verify error messages are still informative and consistent
            self.assertIsInstance(error_format, str)
            self.assertGreater(len(error_format), 0)
            self.assertNotIn("breaking_change", error_format.lower())

    def test_import_path_compatibility(self):
        """Test that import paths remain stable."""
        # Test that common import paths still work
        import_tests = [
            "from dataflow import DataFlow",
            "from dataflow.core.engine import DataFlow",
            "from dataflow.core.config import DataFlowConfig",
        ]

        for import_statement in import_tests:
            is_compatible = self.compatibility_checker._test_import_compatibility(
                import_statement
            )
            self.assertTrue(
                is_compatible, f"Import compatibility failed for: {import_statement}"
            )

    def test_legacy_decorators_compatibility(self):
        """Test that legacy decorators still work."""
        # Test @db.model decorator compatibility
        with patch("dataflow.core.engine.DataFlow") as MockDataFlow:
            mock_engine = MockDataFlow.return_value
            mock_engine.model = Mock()

            # Test that decorator works both ways
            @mock_engine.model
            class TestModel:
                name: str
                active: bool = True

            # Verify decorator was called
            mock_engine.model.assert_called_once()

            # Test compatibility
            result = self.compatibility_checker._test_decorator_compatibility(
                mock_engine
            )
            self.assertTrue(result["model_decorator_compatible"])

    def test_query_builder_backward_compatibility(self):
        """Test that query builder API remains backward compatible."""
        # Test that existing query builder patterns still work
        with patch(
            "dataflow.database.query_builder.create_query_builder"
        ) as mock_builder:
            mock_query_builder = Mock()
            mock_builder.return_value = mock_query_builder

            # Test compatibility
            result = self.compatibility_checker._test_query_builder_compatibility()

            self.assertTrue(result["api_compatible"])
            self.assertTrue(result["method_signatures_stable"])

    def test_transaction_api_compatibility(self):
        """Test that transaction API remains backward compatible."""
        # Setup mock transaction manager
        with patch("dataflow.core.engine.DataFlow") as MockDataFlow:
            mock_engine = MockDataFlow.return_value
            mock_engine.transactions = Mock()
            mock_engine.transactions.begin = Mock()
            mock_engine.transactions.commit = Mock()
            mock_engine.transactions.rollback = Mock()

            # Test transaction API compatibility
            result = self.compatibility_checker._test_transaction_api_compatibility(
                mock_engine
            )

            self.assertTrue(result["transaction_methods_available"])
            self.assertTrue(result["api_signatures_compatible"])

    def test_configuration_validation_compatibility(self):
        """Test that configuration validation remains backward compatible."""
        # Test various configuration formats that should still work
        config_formats = [
            # Old style - direct parameters
            {
                "database_url": "postgresql://localhost/test",
                "pool_size": 10,
                "echo": False,
            },
            # New style - structured config
            {
                "database": {
                    "url": "postgresql://localhost/test",
                    "pool_size": 10,
                    "echo": False,
                }
            },
        ]

        for config_format in config_formats:
            is_valid = self.compatibility_checker._validate_config_format(config_format)
            self.assertTrue(
                is_valid, f"Configuration format validation failed for: {config_format}"
            )


if __name__ == "__main__":
    unittest.main()
