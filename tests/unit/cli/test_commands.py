"""Tests for CLI commands module."""

import pytest
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

    def test_init_command_basic(self, tmp_path, monkeypatch):
        """Test basic init command."""
        monkeypatch.chdir(tmp_path)
        result = self.runner.invoke(cli, ["init", "test-project"])
        assert result.exit_code == 0, result.output
        assert "Created new Kailash project: test-project" in result.output
        assert (tmp_path / "test-project" / "README.md").is_file()
        assert (
            tmp_path / "test-project" / "workflows" / "example_workflow.py"
        ).is_file()

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

    def test_export_nonexistent_file(self, tmp_path, monkeypatch):
        """Test exporting non-existent workflow."""
        monkeypatch.chdir(tmp_path)
        result = self.runner.invoke(cli, ["export", "nonexistent.yaml", "output.yaml"])
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

    def test_cli_error_handling(self, tmp_path, monkeypatch):
        """Test CLI error handling."""
        # Test with corrupted workflow file
        monkeypatch.chdir(tmp_path)
        with open("corrupted.yaml", "w") as f:
            f.write("invalid: yaml: content: [")

        result = self.runner.invoke(cli, ["run", "corrupted.yaml"])
        assert result.exit_code != 0

    def test_cli_workflow_validation(self, tmp_path, monkeypatch):
        """Validate an actual supported Python workflow through the CLI."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "valid.py").write_text(
            "from kailash.workflow.builder import WorkflowBuilder\n"
            "workflow = WorkflowBuilder()\n"
            "workflow.add_node('PythonCodeNode', 'value', {'code': 'result = 1'})\n"
            "workflow = workflow.build()\n"
        )
        result = self.runner.invoke(cli, ["validate", "valid.py"])
        assert result.exit_code == 0, result.output
        assert "is valid" in result.output

    def test_cli_workflow_validation_rejects_unsupported_format(
        self, tmp_path, monkeypatch
    ):
        """A real YAML file must fail, rather than accidentally count as valid."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "workflow.yaml").write_text("nodes: []\n")
        result = self.runner.invoke(cli, ["validate", "workflow.yaml"])
        assert result.exit_code == 1
        assert "Only Python workflow files are supported" in result.output
