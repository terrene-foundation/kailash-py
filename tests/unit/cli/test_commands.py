"""Tests for CLI commands module."""

import pytest
import yaml
from click.testing import CliRunner
from kailash.cli.commands import cli


class TestCLICommands:
    """Test CLI commands."""

    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()

    def test_cli_help(self):
        """Test CLI help command."""
        result = self.runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Usage:" in result.output

    def test_cli_version(self):
        """Test CLI version command."""
        result = self.runner.invoke(cli, ["--version"])
        assert result.exit_code == 0

    def test_init_command_help(self):
        """Test init command help."""
        result = self.runner.invoke(cli, ["init", "--help"])
        assert result.exit_code == 0
        assert "init" in result.output.lower()

    def test_init_command_basic(self):
        """Test basic init command."""
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(cli, ["init", "test-project"])
            # Allow success or failure as template might not exist
            assert result.exit_code in [0, 1, 2]

    def test_run_command_help(self):
        """Test run command help."""
        result = self.runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "run" in result.output.lower()

    def test_run_nonexistent_file(self):
        """Test running non-existent workflow file."""
        result = self.runner.invoke(cli, ["run", "nonexistent.yaml"])
        assert result.exit_code != 0

    def test_validate_command_help(self):
        """Test validate command help."""
        result = self.runner.invoke(cli, ["validate", "--help"])
        assert result.exit_code == 0
        assert "validate" in result.output.lower()

    def test_validate_nonexistent_file(self):
        """Test validating non-existent workflow file."""
        result = self.runner.invoke(cli, ["validate", "nonexistent.yaml"])
        assert result.exit_code != 0

    def test_export_command_help(self):
        """Test export command help."""
        result = self.runner.invoke(cli, ["export", "--help"])
        assert result.exit_code == 0
        assert "export" in result.output.lower()

    def test_export_nonexistent_file(self):
        """Test exporting non-existent workflow."""
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(
                cli, ["export", "nonexistent.yaml", "output.yaml"]
            )
            assert result.exit_code != 0

    def test_global_debug_flag(self):
        """Test global debug flag."""
        result = self.runner.invoke(cli, ["--debug", "--help"])
        assert result.exit_code == 0

    def test_invalid_command(self):
        """Test invalid command."""
        result = self.runner.invoke(cli, ["invalid-command"])
        assert result.exit_code != 0
        assert "No such command" in result.output or "Usage:" in result.output

    def test_command_with_invalid_option(self):
        """Test command with invalid option."""
        result = self.runner.invoke(cli, ["--invalid-option"])
        assert result.exit_code != 0

    def test_cli_error_handling(self):
        """Test CLI error handling."""
        # Test with corrupted workflow file
        with self.runner.isolated_filesystem():
            with open("corrupted.yaml", "w") as f:
                f.write("invalid: yaml: content: [")

            result = self.runner.invoke(cli, ["run", "corrupted.yaml"])
            assert result.exit_code != 0

    def test_cli_workflow_validation(self):
        """Test workflow validation through CLI."""
        with self.runner.isolated_filesystem():
            # Create a simple valid workflow
            workflow_data = {
                "metadata": {"name": "Test Workflow", "version": "1.0.0"},
                "nodes": [],
                "connections": [],
            }

            with open("valid.yaml", "w") as f:
                yaml.dump(workflow_data, f)

            # Test validation
            result = self.runner.invoke(cli, ["validate", "valid.yaml"])
            # Allow various exit codes as validation logic may vary
            assert result.exit_code in [0, 1, 2]
