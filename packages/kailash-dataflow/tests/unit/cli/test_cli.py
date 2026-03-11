"""
Unit tests for DataFlow CLI interface.

Tests CLI commands and options without external dependencies.
"""

import os
import sys
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner
from dataflow.cli import init, main, schema, version


class TestDataFlowCLI:
    """Test DataFlow CLI interface functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()

    def test_main_command_help(self):
        """Test main command shows help."""
        result = self.runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "DataFlow - Workflow-native database framework" in result.output
        assert "schema" in result.output
        assert "init" in result.output
        assert "version" in result.output

    def test_main_command_version(self):
        """Test main command version option."""
        result = self.runner.invoke(main, ["--version"])

        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_version_command(self):
        """Test version command displays version."""
        result = self.runner.invoke(main, ["version"])

        assert result.exit_code == 0
        assert "DataFlow version 0.1.0" in result.output

    @patch("dataflow.cli.DataFlow")
    def test_schema_command_default(self, mock_dataflow):
        """Test schema command with default options."""
        mock_db = Mock()
        mock_dataflow.return_value = mock_db

        result = self.runner.invoke(main, ["schema"])

        assert result.exit_code == 0
        assert "DataFlow schema generation" in result.output
        assert "Using default/environment" in result.output
        assert "All models" in result.output
        assert "Schema generation functionality coming soon..." in result.output

        # Verify DataFlow was instantiated with None (default)
        mock_dataflow.assert_called_once_with(database_url=None)

    @patch("dataflow.cli.DataFlow")
    def test_schema_command_with_database_url(self, mock_dataflow):
        """Test schema command with database URL."""
        mock_db = Mock()
        mock_dataflow.return_value = mock_db
        database_url = "postgresql://test:test@localhost/testdb"

        result = self.runner.invoke(main, ["schema", "--database-url", database_url])

        assert result.exit_code == 0
        assert "DataFlow schema generation" in result.output
        assert f"Database URL: {database_url}" in result.output
        assert "All models" in result.output

        # Verify DataFlow was instantiated with provided URL
        mock_dataflow.assert_called_once_with(database_url=database_url)

    @patch("dataflow.cli.DataFlow")
    def test_schema_command_with_model(self, mock_dataflow):
        """Test schema command with specific model."""
        mock_db = Mock()
        mock_dataflow.return_value = mock_db
        model_name = "User"

        result = self.runner.invoke(main, ["schema", "--model", model_name])

        assert result.exit_code == 0
        assert "DataFlow schema generation" in result.output
        assert f"Model: {model_name}" in result.output

        mock_dataflow.assert_called_once_with(database_url=None)

    @patch("dataflow.cli.DataFlow")
    def test_schema_command_with_all_options(self, mock_dataflow):
        """Test schema command with all options."""
        mock_db = Mock()
        mock_dataflow.return_value = mock_db
        database_url = "postgresql://test:test@localhost/testdb"
        model_name = "Product"

        result = self.runner.invoke(
            main, ["schema", "--database-url", database_url, "--model", model_name]
        )

        assert result.exit_code == 0
        assert "DataFlow schema generation" in result.output
        assert f"Database URL: {database_url}" in result.output
        assert f"Model: {model_name}" in result.output

        mock_dataflow.assert_called_once_with(database_url=database_url)

    @patch("dataflow.cli.DataFlow")
    def test_schema_command_error_handling(self, mock_dataflow):
        """Test schema command handles errors gracefully."""
        mock_dataflow.side_effect = Exception("Database connection failed")

        result = self.runner.invoke(main, ["schema"])

        assert result.exit_code == 1
        assert "Error: Database connection failed" in result.output

    @patch("dataflow.cli.DataFlow")
    def test_init_command_default(self, mock_dataflow):
        """Test init command with default options."""
        mock_db = Mock()
        mock_dataflow.return_value = mock_db

        result = self.runner.invoke(main, ["init"])

        assert result.exit_code == 0
        assert "Initializing DataFlow database..." in result.output
        assert "Using default/environment" in result.output
        assert "Database initialization functionality coming soon..." in result.output

        mock_dataflow.assert_called_once_with(database_url=None)

    @patch("dataflow.cli.DataFlow")
    def test_init_command_with_database_url(self, mock_dataflow):
        """Test init command with database URL."""
        mock_db = Mock()
        mock_dataflow.return_value = mock_db
        database_url = "postgresql://test:test@localhost/testdb"

        result = self.runner.invoke(main, ["init", "--database-url", database_url])

        assert result.exit_code == 0
        assert "Initializing DataFlow database..." in result.output
        assert f"Database URL: {database_url}" in result.output

        mock_dataflow.assert_called_once_with(database_url=database_url)

    @patch("dataflow.cli.DataFlow")
    def test_init_command_error_handling(self, mock_dataflow):
        """Test init command handles errors gracefully."""
        mock_dataflow.side_effect = Exception("Database initialization failed")

        result = self.runner.invoke(main, ["init"])

        assert result.exit_code == 1
        assert "Error: Database initialization failed" in result.output

    def test_invalid_command(self):
        """Test invalid command shows error."""
        result = self.runner.invoke(main, ["nonexistent"])

        assert result.exit_code != 0
        assert "No such command" in result.output

    @patch("dataflow.cli.DataFlow")
    def test_schema_help_option(self, mock_dataflow):
        """Test schema command help option."""
        result = self.runner.invoke(main, ["schema", "--help"])

        assert result.exit_code == 0
        assert "Generate and display database schema" in result.output
        assert "--database-url" in result.output
        assert "--model" in result.output

    @patch("dataflow.cli.DataFlow")
    def test_init_help_option(self, mock_dataflow):
        """Test init command help option."""
        result = self.runner.invoke(main, ["init", "--help"])

        assert result.exit_code == 0
        assert "Initialize DataFlow database" in result.output
        assert "--database-url" in result.output

    def test_cli_module_imports(self):
        """Test that CLI module imports work correctly."""
        # Test that we can import the necessary modules
        import dataflow.cli

        assert hasattr(dataflow.cli, "main")
        assert hasattr(dataflow.cli, "schema")
        assert hasattr(dataflow.cli, "init")
        assert hasattr(dataflow.cli, "version")

    @patch.dict(os.environ, {"DATABASE_URL": "sqlite:///test.db"})
    @patch("dataflow.cli.DataFlow")
    def test_environment_variable_database_url(self, mock_dataflow):
        """Test that environment variables work with CLI."""
        mock_db = Mock()
        mock_dataflow.return_value = mock_db

        result = self.runner.invoke(main, ["schema"])

        assert result.exit_code == 0
        assert "Using default/environment" in result.output

        # DataFlow should still be called with None since we don't pass the env var explicitly
        mock_dataflow.assert_called_once_with(database_url=None)

    def test_path_setup(self):
        """Test that sys.path is modified correctly."""
        # The CLI module should have modified sys.path on import
        # We can't test this directly since it happens at import time,
        # but we can verify the path logic would work
        import dataflow.cli

        expected_path = os.path.dirname(
            os.path.dirname(os.path.abspath(dataflow.cli.__file__))
        )

        # The path should have been added to sys.path
        # This is mainly testing the import works correctly
        assert dataflow.cli.DataFlow is not None


class TestCLIIntegration:
    """Test CLI integration with DataFlow components."""

    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()

    @patch("dataflow.cli.DataFlow")
    def test_cli_dataflow_integration(self, mock_dataflow):
        """Test CLI properly integrates with DataFlow."""
        mock_db = Mock()
        mock_dataflow.return_value = mock_db

        # Test that CLI commands properly instantiate DataFlow
        commands_to_test = [
            (["schema"], "schema generation"),
            (["init"], "database initialization"),
        ]

        for command, expected_output in commands_to_test:
            result = self.runner.invoke(main, command)

            assert result.exit_code == 0
            assert expected_output.split()[0] in result.output.lower()

        # Verify DataFlow was called twice (once for each command)
        assert mock_dataflow.call_count == 2

    def test_cli_error_propagation(self):
        """Test that CLI properly propagates errors."""
        # Test with invalid database URL format that would cause DataFlow to fail
        with patch("dataflow.cli.DataFlow") as mock_dataflow:
            mock_dataflow.side_effect = ValueError("Invalid database URL format")

            result = self.runner.invoke(
                main, ["schema", "--database-url", "invalid-url"]
            )

            assert result.exit_code == 1
            assert "Error: Invalid database URL format" in result.output

    @patch("dataflow.cli.DataFlow")
    def test_cli_exit_codes(self, mock_dataflow):
        """Test that CLI uses proper exit codes."""
        mock_dataflow.side_effect = Exception("Test error")

        # Don't catch exceptions to test actual exit behavior
        result = self.runner.invoke(main, ["schema"])

        # The command should exit with code 1 on error
        assert result.exit_code == 1
        assert "Error: Test error" in result.output


class TestCLICommandLineIntegration:
    """Test CLI as it would be used from command line."""

    def test_main_function_callable(self):
        """Test that main function can be called."""
        from dataflow.cli import main

        # Test that main is a click.Group and callable
        assert hasattr(main, "__call__")
        assert hasattr(main, "commands")

        # Test that expected commands are registered
        assert "schema" in main.commands
        assert "init" in main.commands
        assert "version" in main.commands
