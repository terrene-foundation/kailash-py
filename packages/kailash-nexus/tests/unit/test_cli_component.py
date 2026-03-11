"""Unit tests for CLI channel integration component."""

import json
import os
import subprocess
import sys
from unittest.mock import Mock, patch

import pytest
import requests


class TestNexusCLI:
    """Test the Nexus CLI implementation."""

    def test_cli_module_importable(self):
        """Test that the CLI module can be imported."""
        from nexus.cli.main import NexusCLI

        cli = NexusCLI()
        assert cli.base_url == "http://localhost:8000"

        cli_custom = NexusCLI("http://localhost:9000")
        assert cli_custom.base_url == "http://localhost:9000"

    def test_parse_parameters(self):
        """Test parameter parsing functionality."""
        from nexus.cli.main import NexusCLI

        cli = NexusCLI()

        # Test simple key=value pairs
        params = cli.parse_parameters(["name=test", "count=5", "enabled=true"])
        assert params == {"name": "test", "count": 5, "enabled": True}

        # Test JSON values
        params = cli.parse_parameters(['data={"items": [1, 2, 3]}'])
        assert params == {"data": {"items": [1, 2, 3]}}

        # Test mixed types
        params = cli.parse_parameters(["str=hello", "num=42", 'obj={"key": "value"}'])
        assert params == {"str": "hello", "num": 42, "obj": {"key": "value"}}

    def test_parse_parameters_invalid_format(self):
        """Test parameter parsing with invalid format."""
        from nexus.cli.main import NexusCLI

        cli = NexusCLI()

        with pytest.raises(SystemExit):
            cli.parse_parameters(["invalid_format"])

    @patch("requests.get")
    def test_list_workflows_success(self, mock_get):
        """Test successful workflow listing."""
        from nexus.cli.main import NexusCLI

        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "workflow1": {"description": "Test workflow 1"},
            "workflow2": {"description": "Test workflow 2"},
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        cli = NexusCLI()

        # Capture stdout
        with patch("builtins.print") as mock_print:
            cli.list_workflows()

        # Verify correct API call
        mock_get.assert_called_once_with("http://localhost:8000/workflows", timeout=5)

        # Verify output
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert "Available workflows:" in print_calls
        assert "  - workflow1" in print_calls
        assert "  - workflow2" in print_calls

    @patch("requests.get")
    def test_list_workflows_empty(self, mock_get):
        """Test workflow listing with no workflows."""
        from nexus.cli.main import NexusCLI

        # Mock empty response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        cli = NexusCLI()

        with patch("builtins.print") as mock_print:
            cli.list_workflows()

        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert "No workflows available." in print_calls

    @patch("requests.get")
    def test_list_workflows_connection_error(self, mock_get):
        """Test workflow listing with connection error."""
        from nexus.cli.main import NexusCLI

        mock_get.side_effect = requests.ConnectionError("Connection failed")

        cli = NexusCLI()

        with pytest.raises(SystemExit):
            with patch("builtins.print") as mock_print:
                cli.list_workflows()

    @patch("requests.post")
    def test_run_workflow_success_enterprise_format(self, mock_post):
        """Test successful workflow execution with enterprise format."""
        from nexus.cli.main import NexusCLI

        # Mock enterprise format response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "outputs": {
                "process": {"result": {"status": "success", "message": "Hello, World!"}}
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        cli = NexusCLI()

        with patch("builtins.print") as mock_print:
            cli.run_workflow("test-workflow", {"name": "test"})

        # Verify correct API call
        mock_post.assert_called_once_with(
            "http://localhost:8000/workflows/test-workflow",
            json={"parameters": {"name": "test"}},
            timeout=30,
        )

        # Verify output
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert "status: success" in print_calls
        assert "message: Hello, World!" in print_calls

    @patch("requests.post")
    def test_run_workflow_success_direct_format(self, mock_post):
        """Test successful workflow execution with direct format."""
        from nexus.cli.main import NexusCLI

        # Mock direct format response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": "success",
            "data": {"processed": True},
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        cli = NexusCLI()

        with patch("builtins.print") as mock_print:
            cli.run_workflow("test-workflow")

        # Should print JSON for direct format
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        # The output should be JSON formatted
        assert any("result" in call for call in print_calls)

    @patch("requests.post")
    def test_run_workflow_execution_error(self, mock_post):
        """Test workflow execution with connection error."""
        from nexus.cli.main import NexusCLI

        mock_post.side_effect = requests.RequestException("Execution failed")

        cli = NexusCLI()

        with pytest.raises(SystemExit):
            with patch("builtins.print") as mock_print:
                cli.run_workflow("test-workflow")

    def test_cli_module_entry_point(self):
        """Test that CLI module can be invoked."""
        # Test that the module is discoverable
        import os

        # Get the Nexus src directory and kailash core SDK src directory
        nexus_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        kailash_root = os.path.dirname(os.path.dirname(nexus_root))
        env = os.environ.copy()
        nexus_src = os.path.join(nexus_root, "src")
        kailash_src = os.path.join(kailash_root, "src")
        env["PYTHONPATH"] = f"{nexus_src}:{kailash_src}:{env.get('PYTHONPATH', '')}"

        result = subprocess.run(
            ["python", "-c", "import nexus.cli; print('success')"],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0
        assert "success" in result.stdout

    @patch("argparse.ArgumentParser.parse_args")
    @patch("nexus.cli.main.NexusCLI")
    def test_main_function_list_command(self, mock_cli_class, mock_parse_args):
        """Test main function with list command."""
        from nexus.cli.main import main

        # Mock arguments for list command
        mock_args = Mock()
        mock_args.command = "list"
        mock_args.url = "http://localhost:8000"
        mock_parse_args.return_value = mock_args

        # Mock CLI instance
        mock_cli = Mock()
        mock_cli_class.return_value = mock_cli

        main()

        # Verify CLI was initialized with correct URL
        mock_cli_class.assert_called_once_with(base_url="http://localhost:8000")

        # Verify list_workflows was called
        mock_cli.list_workflows.assert_called_once()

    @patch("argparse.ArgumentParser.parse_args")
    @patch("nexus.cli.main.NexusCLI")
    def test_main_function_run_command(self, mock_cli_class, mock_parse_args):
        """Test main function with run command."""
        from nexus.cli.main import main

        # Mock arguments for run command
        mock_args = Mock()
        mock_args.command = "run"
        mock_args.workflow = "test-workflow"
        mock_args.param = ["name=test", "count=5"]
        mock_args.url = "http://localhost:8001"
        mock_parse_args.return_value = mock_args

        # Mock CLI instance
        mock_cli = Mock()
        mock_cli.parse_parameters.return_value = {"name": "test", "count": 5}
        mock_cli_class.return_value = mock_cli

        main()

        # Verify CLI was initialized with correct URL
        mock_cli_class.assert_called_once_with(base_url="http://localhost:8001")

        # Verify parameters were parsed
        mock_cli.parse_parameters.assert_called_once_with(["name=test", "count=5"])

        # Verify run_workflow was called
        mock_cli.run_workflow.assert_called_once_with(
            "test-workflow", {"name": "test", "count": 5}
        )

    @patch("argparse.ArgumentParser.parse_args")
    def test_main_function_no_command(self, mock_parse_args):
        """Test main function with no command."""
        from nexus.cli.main import main

        # Mock arguments with no command
        mock_args = Mock()
        mock_args.command = None
        mock_parse_args.return_value = mock_args

        with pytest.raises(SystemExit):
            main()


class TestCLIIntegration:
    """Test CLI integration points."""

    def test_cli_help_output(self):
        """Test CLI help output."""
        import os

        # Get the Nexus src directory and kailash core SDK src directory
        nexus_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        kailash_root = os.path.dirname(os.path.dirname(nexus_root))
        env = os.environ.copy()
        nexus_src = os.path.join(nexus_root, "src")
        kailash_src = os.path.join(kailash_root, "src")
        env["PYTHONPATH"] = f"{nexus_src}:{kailash_src}:{env.get('PYTHONPATH', '')}"

        result = subprocess.run(
            ["python", "-m", "nexus.cli", "--help"],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0
        assert "Nexus CLI" in result.stdout
        assert "list" in result.stdout
        assert "run" in result.stdout

    def test_cli_list_help(self):
        """Test CLI list command help."""
        import os

        # Get the Nexus src directory and kailash core SDK src directory
        nexus_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        kailash_root = os.path.dirname(os.path.dirname(nexus_root))
        env = os.environ.copy()
        nexus_src = os.path.join(nexus_root, "src")
        kailash_src = os.path.join(kailash_root, "src")
        env["PYTHONPATH"] = f"{nexus_src}:{kailash_src}:{env.get('PYTHONPATH', '')}"

        result = subprocess.run(
            ["python", "-m", "nexus.cli", "list", "--help"],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0
        assert "usage:" in result.stdout
        assert "list" in result.stdout

    def test_cli_run_help(self):
        """Test CLI run command help."""
        import os

        # Get the Nexus src directory and kailash core SDK src directory
        nexus_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        kailash_root = os.path.dirname(os.path.dirname(nexus_root))
        env = os.environ.copy()
        nexus_src = os.path.join(nexus_root, "src")
        kailash_src = os.path.join(kailash_root, "src")
        env["PYTHONPATH"] = f"{nexus_src}:{kailash_src}:{env.get('PYTHONPATH', '')}"

        result = subprocess.run(
            ["python", "-m", "nexus.cli", "run", "--help"],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0
        assert "workflow" in result.stdout
        assert "--param" in result.stdout
