"""
Unit tests for CLI validate command.

Tests the dataflow-validate command for workflow validation,
error detection, auto-fixing, and output formatting.
"""

import json
from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner


class TestValidateCommand:
    """Test suite for validate command."""

    @pytest.fixture
    def runner(self):
        """Create Click test runner."""
        return CliRunner()

    @pytest.fixture
    def valid_workflow(self):
        """Create a valid workflow mock."""
        workflow = Mock()
        workflow.nodes = {"node1": Mock(), "node2": Mock()}
        workflow.connections = [{"source": "node1", "target": "node2"}]
        workflow.name = "test_workflow"
        return workflow

    @pytest.fixture
    def invalid_workflow(self):
        """Create an invalid workflow mock with errors."""
        workflow = Mock()
        workflow.nodes = {"node1": Mock()}
        workflow.connections = [{"source": "node1", "target": "missing_node"}]
        workflow.name = "invalid_workflow"
        return workflow

    def test_validate_command_with_valid_workflow(self, runner):
        """
        Test validate command succeeds with valid workflow.

        Expected behavior:
        - Exit code 0 (success)
        - Success message displayed
        - No errors reported
        """
        from dataflow.cli.commands import validate

        with patch("dataflow.cli.validate.load_workflow") as mock_load:
            mock_load.return_value = Mock(
                nodes={"node1": Mock()}, connections=[], name="valid_workflow"
            )

            with patch("dataflow.platform.inspector.Inspector") as mock_inspector:
                mock_inspector.return_value.validate.return_value = {
                    "valid": True,
                    "errors": [],
                    "warnings": [],
                }

                result = runner.invoke(validate, ["workflow.py"])

                # Debug: print output if test fails
                if result.exit_code != 0:
                    print(f"\n=== CLI Output ===\n{result.output}\n==================")

                assert (
                    result.exit_code == 0
                ), f"Expected 0, got {result.exit_code}. Output: {result.output}"
                assert "✓" in result.output or "valid" in result.output.lower()
                assert "error" not in result.output.lower()

    def test_validate_command_with_invalid_workflow(self, runner):
        """
        Test validate command detects invalid workflow.

        Expected behavior:
        - Exit code 1 (validation errors)
        - Error messages displayed
        - Detailed error information
        """
        from dataflow.cli.commands import validate

        with patch("dataflow.cli.validate.load_workflow") as mock_load:
            mock_load.return_value = Mock(
                nodes={"node1": Mock()},
                connections=[{"source": "node1", "target": "missing"}],
                name="invalid_workflow",
            )

            with patch("dataflow.platform.inspector.Inspector") as mock_inspector:
                mock_inspector.return_value.validate.return_value = {
                    "valid": False,
                    "errors": [
                        {
                            "type": "ConnectionError",
                            "message": "Target node 'missing' not found",
                            "node": "node1",
                        }
                    ],
                    "warnings": [],
                }

                result = runner.invoke(validate, ["workflow.py"])

                assert result.exit_code == 1
                assert "error" in result.output.lower()
                assert "missing" in result.output.lower()

    def test_validate_command_json_output(self, runner):
        """
        Test validate command with JSON output format.

        Expected behavior:
        - Valid JSON output
        - Contains validation results
        - Machine-readable format
        """
        from dataflow.cli.commands import validate

        with patch("dataflow.cli.validate.load_workflow") as mock_load:
            mock_load.return_value = Mock(
                nodes={"node1": Mock()}, connections=[], name="test_workflow"
            )

            with patch("dataflow.platform.inspector.Inspector") as mock_inspector:
                validation_result = {
                    "valid": True,
                    "errors": [],
                    "warnings": [],
                    "metrics": {"node_count": 1, "connection_count": 0},
                }
                mock_inspector.return_value.validate.return_value = validation_result

                result = runner.invoke(validate, ["workflow.py", "--output", "json"])

                assert result.exit_code == 0

                # Parse JSON output
                output_data = json.loads(result.output)
                assert output_data["valid"] is True
                assert "errors" in output_data
                assert "warnings" in output_data

    def test_validate_command_with_fix_flag(self, runner):
        """
        Test validate command with --fix flag for auto-correction.

        Expected behavior:
        - Attempts to fix errors
        - Reports fixed issues
        - Exit code 0 if all fixed
        """
        from dataflow.cli.commands import validate

        with patch("dataflow.cli.validate.load_workflow") as mock_load:
            workflow_mock = Mock(
                nodes={"node1": Mock()},
                connections=[{"source": "node1", "target": "node2"}],
                name="fixable_workflow",
            )
            mock_load.return_value = workflow_mock

            with patch("dataflow.platform.inspector.Inspector") as mock_inspector:
                # First validation: has fixable errors, second validation: fixed
                mock_inspector.return_value.validate.side_effect = [
                    {
                        "valid": False,
                        "errors": [
                            {
                                "type": "ParameterNaming",
                                "message": "Parameter 'userName' should be 'user_name'",
                                "fixable": True,
                            }
                        ],
                        "warnings": [],
                    },
                    {"valid": True, "errors": [], "warnings": []},
                ]

                with patch("dataflow.cli.validate.apply_fixes") as mock_fix:
                    mock_fix.return_value = {
                        "fixed": 1,
                        "failed": 0,
                        "changes": ["Renamed userName to user_name"],
                    }

                    result = runner.invoke(validate, ["workflow.py", "--fix"])

                    assert result.exit_code == 0
                    assert "fixed" in result.output.lower()
                    mock_fix.assert_called_once()

    def test_validate_command_exit_codes(self, runner):
        """
        Test validate command follows pytest exit code conventions.

        Expected behavior:
        - Exit code 0: Success (valid workflow)
        - Exit code 1: Validation errors found
        - Exit code 2: Internal error (exception)
        """
        from dataflow.cli.commands import validate

        # Test exit code 0 (success)
        with patch("dataflow.cli.validate.load_workflow") as mock_load:
            mock_load.return_value = Mock(nodes={}, connections=[], name="valid")

            with patch("dataflow.platform.inspector.Inspector") as mock_inspector:
                mock_inspector.return_value.validate.return_value = {
                    "valid": True,
                    "errors": [],
                    "warnings": [],
                }

                result = runner.invoke(validate, ["workflow.py"])
                assert result.exit_code == 0

        # Test exit code 1 (validation errors)
        with patch("dataflow.cli.validate.load_workflow") as mock_load:
            mock_load.return_value = Mock(nodes={}, connections=[], name="invalid")

            with patch("dataflow.platform.inspector.Inspector") as mock_inspector:
                mock_inspector.return_value.validate.return_value = {
                    "valid": False,
                    "errors": [{"type": "Error", "message": "Test error"}],
                    "warnings": [],
                }

                result = runner.invoke(validate, ["workflow.py"])
                assert result.exit_code == 1

        # Test exit code 2 (internal error)
        with patch("dataflow.cli.validate.load_workflow") as mock_load:
            mock_load.side_effect = Exception("Internal error")

            result = runner.invoke(validate, ["workflow.py"])
            assert result.exit_code == 2
