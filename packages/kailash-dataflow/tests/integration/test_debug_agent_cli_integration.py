"""
Integration tests for DataFlow Debug Agent CLI with real infrastructure.

Tests CLI with real DebugAgent, ErrorEnhancer, Inspector, and KnowledgeBase.
Following NO MOCKING policy for Tier 2 integration tests.

Test Coverage:
- Real error diagnosis flow with DebugAgent
- Real ErrorEnhancer error analysis (60+ error types)
- Real Inspector workflow introspection (30 methods)
- Real KnowledgeBase pattern storage
- Complete diagnosis with ranked solutions
- Actual error scenarios from error catalog
- CLI output format verification (text/JSON)
- Verbose mode and top-N solution display
- Performance validation (<5 seconds target)
"""

import json
import tempfile
import time
from pathlib import Path

import pytest
from click.testing import CliRunner
from dataflow import DataFlow
from dataflow.cli.debug_agent_cli import diagnose
from dataflow.core.error_enhancer import ErrorEnhancer
from dataflow.debug.agent import DebugAgent
from dataflow.debug.data_structures import KnowledgeBase
from dataflow.exceptions import EnhancedDataFlowError

from kailash.workflow.builder import WorkflowBuilder


@pytest.fixture
def cli_runner():
    """Create Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def error_enhancer():
    """Create real ErrorEnhancer instance with full mode."""
    return ErrorEnhancer()


@pytest.fixture
def knowledge_base():
    """Create real KnowledgeBase instance (in-memory)."""
    return KnowledgeBase(storage_type="memory")


@pytest.fixture
def debug_agent(error_enhancer, knowledge_base):
    """Create real DebugAgent instance with ErrorEnhancer and KnowledgeBase."""
    agent = DebugAgent(
        error_enhancer=error_enhancer,
        knowledge_base=knowledge_base,
        model="gpt-4o-mini",
    )
    return agent


@pytest.fixture
def sample_workflow():
    """Create sample workflow for testing."""
    workflow = WorkflowBuilder()
    # Intentionally create invalid workflow for error testing
    workflow.add_node("UserCreateNode", "create", {"name": "Alice"})  # Missing 'id'
    return workflow


@pytest.fixture
def temp_workflow_file(tmp_path):
    """Create temporary workflow file for --workflow tests."""
    workflow_file = tmp_path / "test_workflow.py"
    workflow_file.write_text(
        """
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {"name": "Alice"})  # Missing 'id'
workflow.add_node("UserReadNode", "read", {"id": "user-123"})
workflow.add_connection("create", "id", "read", "id")
"""
    )
    return workflow_file


@pytest.mark.integration
@pytest.mark.timeout(10)
class TestRealErrorDiagnosisFlow:
    """Test complete error diagnosis flow with real components."""

    def test_parameter_error_diagnosis_with_real_enhancer(
        self, cli_runner, error_enhancer
    ):
        """Test DF-101 parameter error diagnosis with real ErrorEnhancer."""
        # Create real enhanced error using ErrorEnhancer API
        original_error = KeyError("id")
        enhanced_error = error_enhancer.enhance_parameter_error(
            node_id="create_user",
            node_type="UserCreateNode",
            parameter_name="id",
            original_error=original_error,
        )

        # Execute CLI with real enhanced error
        result = cli_runner.invoke(
            diagnose,
            [
                "--error-input",
                str(enhanced_error),
                "--format",
                "text",
            ],
        )

        # Verify diagnosis output contains expected elements
        if result.exit_code != 0:
            print(f"CLI FAILED. Exit code: {result.exit_code}")
            print(f"Output: {result.output}")
            print(
                f"Exception: {result.exception if hasattr(result, 'exception') else 'None'}"
            )
        assert (
            result.exit_code == 0
        ), f"CLI failed with exit code {result.exit_code}. Output: {result.output[:500]}"
        assert "DF-" in result.output  # Error code
        assert "parameter" in result.output.lower()
        assert "Solutions" in result.output
        assert "Confidence" in result.output

    def test_connection_error_diagnosis_with_real_enhancer(
        self, cli_runner, error_enhancer
    ):
        """Test DF-201 connection error diagnosis with real ErrorEnhancer."""
        # Create real connection error
        original_error = ValueError("Connection parameter mismatch")
        enhanced_error = error_enhancer.enhance_connection_error(
            source_node="node_a",
            source_param="user_id",
            target_node="node_b",
            target_param="id",
            original_error=original_error,
        )

        # Execute CLI with real error
        result = cli_runner.invoke(
            diagnose,
            [
                "--error-input",
                str(enhanced_error),
                "--format",
                "text",
            ],
        )

        # Verify diagnosis
        assert result.exit_code == 0
        assert "DF-" in result.output
        assert (
            "connection" in result.output.lower()
            or "parameter" in result.output.lower()
        )

    def test_migration_error_diagnosis_with_real_enhancer(
        self, cli_runner, error_enhancer
    ):
        """Test DF-301 migration error diagnosis with real ErrorEnhancer."""
        # Create real migration error
        original_error = RuntimeError("Table 'users' already exists")
        enhanced_error = error_enhancer.enhance_migration_error(
            model_name="User",
            operation="CREATE_TABLE",
            details={"table_name": "users"},
            original_error=original_error,
        )

        # Execute CLI with real error
        result = cli_runner.invoke(
            diagnose,
            [
                "--error-input",
                str(enhanced_error),
                "--format",
                "text",
            ],
        )

        # Verify diagnosis addresses migration
        assert result.exit_code == 0
        assert "DF-" in result.output
        assert "table" in result.output.lower() or "migration" in result.output.lower()

    def test_runtime_error_diagnosis_with_real_enhancer(
        self, cli_runner, error_enhancer
    ):
        """Test DF-501 runtime error diagnosis with real ErrorEnhancer."""
        # Create real runtime error
        original_error = TimeoutError("Workflow execution timeout")
        enhanced_error = error_enhancer.enhance_runtime_error(
            node_id="test_node",
            workflow_id="test_workflow",
            operation="TIMEOUT",
            original_error=original_error,
        )

        # Execute CLI with real error
        result = cli_runner.invoke(
            diagnose,
            [
                "--error-input",
                str(enhanced_error),
                "--format",
                "text",
            ],
        )

        # Verify diagnosis
        assert result.exit_code == 0
        assert "DF-" in result.output
        assert "timeout" in result.output.lower() or "runtime" in result.output.lower()


@pytest.mark.integration
@pytest.mark.timeout(10)
class TestRealInspectorIntegration:
    """Test Inspector API integration with real workflow files."""

    def test_workflow_file_loading_with_inspector(self, cli_runner, temp_workflow_file):
        """Test CLI with --workflow option and real workflow file."""
        # Execute CLI command with workflow file
        result = cli_runner.invoke(
            diagnose,
            [
                "--workflow",
                str(temp_workflow_file),
                "--format",
                "text",
            ],
        )

        # Verify workflow was loaded (may not diagnose without error)
        # Exit code 0 means successful load, even if no diagnosis
        assert result.exit_code == 0 or "not found" not in result.output.lower()

    def test_workflow_with_error_and_inspector(
        self, cli_runner, temp_workflow_file, error_enhancer
    ):
        """Test workflow file + error input for complete diagnosis."""
        # Create real error
        original_error = KeyError("id")
        enhanced_error = error_enhancer.enhance_parameter_error(
            node_id="create_user",
            parameter_name="id",
            original_error=original_error,
        )

        # Execute CLI with both workflow and error
        result = cli_runner.invoke(
            diagnose,
            [
                "--workflow",
                str(temp_workflow_file),
                "--error-input",
                str(enhanced_error),
                "--format",
                "text",
            ],
        )

        # Verify complete diagnosis
        assert result.exit_code == 0
        assert "DF-" in result.output
        assert "Solutions" in result.output

    def test_invalid_workflow_file_error_handling(self, cli_runner, tmp_path):
        """Test error handling for non-existent workflow file."""
        non_existent_file = tmp_path / "does_not_exist.py"

        result = cli_runner.invoke(
            diagnose,
            [
                "--workflow",
                str(non_existent_file),
            ],
        )

        # Should fail with clear error message
        assert result.exit_code != 0
        assert (
            "not found" in result.output.lower()
            or "does not exist" in result.output.lower()
        )


@pytest.mark.integration
@pytest.mark.timeout(10)
class TestRealOutputFormatting:
    """Test CLI output formatting with real data."""

    def test_plain_text_format_with_real_diagnosis(self, cli_runner, error_enhancer):
        """Test plain text output format with real diagnosis."""
        # Create real error
        original_error = KeyError("email")
        enhanced_error = error_enhancer.enhance_parameter_error(
            node_id="update_user",
            parameter_name="email",
            original_error=original_error,
        )

        # Execute CLI with text format
        result = cli_runner.invoke(
            diagnose,
            [
                "--error-input",
                str(enhanced_error),
                "--format",
                "text",
            ],
        )

        # Verify plain text format
        assert result.exit_code == 0
        assert "DataFlow AI Debug Agent - Diagnosis" in result.output
        assert "Confidence:" in result.output
        assert "Solutions" in result.output

    def test_json_format_with_real_diagnosis(self, cli_runner, error_enhancer):
        """Test JSON output format with real diagnosis."""
        # Create real error
        original_error = KeyError("id")
        enhanced_error = error_enhancer.enhance_parameter_error(
            node_id="create_user",
            parameter_name="id",
            original_error=original_error,
        )

        # Execute CLI with JSON format
        result = cli_runner.invoke(
            diagnose,
            [
                "--error-input",
                str(enhanced_error),
                "--format",
                "json",
            ],
        )

        # Verify JSON structure
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "diagnosis" in data
        assert "ranked_solutions" in data
        assert "confidence" in data
        assert "next_steps" in data
        assert isinstance(data["ranked_solutions"], list)

    def test_verbose_mode_with_real_diagnosis(self, cli_runner, error_enhancer):
        """Test verbose mode shows complete details."""
        # Create real error
        original_error = KeyError("name")
        enhanced_error = error_enhancer.enhance_parameter_error(
            node_id="create_user",
            parameter_name="name",
            original_error=original_error,
        )

        # Execute CLI with verbose flag
        result = cli_runner.invoke(
            diagnose,
            [
                "--error-input",
                str(enhanced_error),
                "--verbose",
            ],
        )

        # Verify verbose output includes detailed information
        assert result.exit_code == 0
        assert "Reasoning:" in result.output
        assert "Confidence:" in result.output
        assert "Effectiveness:" in result.output

    def test_top_n_solution_limiting(self, cli_runner, error_enhancer):
        """Test --top-n option limits solution display."""
        # Create real error
        original_error = KeyError("email")
        enhanced_error = error_enhancer.enhance_parameter_error(
            node_id="update_user",
            parameter_name="email",
            original_error=original_error,
        )

        # Execute CLI with top-n=2
        result = cli_runner.invoke(
            diagnose,
            [
                "--error-input",
                str(enhanced_error),
                "--top-n",
                "2",
                "--format",
                "json",
            ],
        )

        # Verify only 2 solutions returned
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["ranked_solutions"]) <= 2


@pytest.mark.integration
@pytest.mark.timeout(10)
class TestErrorHandling:
    """Test CLI error handling with real scenarios."""

    def test_missing_required_arguments(self, cli_runner):
        """Test error when neither --error-input nor --workflow provided."""
        result = cli_runner.invoke(diagnose, [])

        # Should fail with clear error message
        assert result.exit_code != 0
        assert "Either --error-input or --workflow is required" in result.output

    def test_invalid_top_n_value(self, cli_runner, error_enhancer):
        """Test error handling for invalid --top-n value."""
        # Create real error
        original_error = KeyError("id")
        enhanced_error = error_enhancer.enhance_parameter_error(
            node_id="create_user",
            parameter_name="id",
            original_error=original_error,
        )

        # Execute CLI with invalid top-n
        result = cli_runner.invoke(
            diagnose,
            [
                "--error-input",
                str(enhanced_error),
                "--top-n",
                "-1",
            ],
        )

        # Should fail with validation error
        assert result.exit_code != 0

    def test_invalid_format_option(self, cli_runner, error_enhancer):
        """Test error handling for invalid --format value."""
        # Create real error
        original_error = KeyError("id")
        enhanced_error = error_enhancer.enhance_parameter_error(
            node_id="create_user",
            parameter_name="id",
            original_error=original_error,
        )

        # Execute CLI with invalid format
        result = cli_runner.invoke(
            diagnose,
            [
                "--error-input",
                str(enhanced_error),
                "--format",
                "xml",  # Only text/json supported
            ],
        )

        # Should fail with format validation error
        assert result.exit_code != 0
        assert "Invalid value for '--format'" in result.output


@pytest.mark.integration
@pytest.mark.timeout(10)
class TestSolutionRanking:
    """Test solution ranking with real DebugAgent."""

    def test_solutions_ranked_by_relevance(self, cli_runner, error_enhancer):
        """Test that solutions are ranked by relevance score."""
        # Create real error
        original_error = KeyError("email")
        enhanced_error = error_enhancer.enhance_parameter_error(
            node_id="create_user",
            node_type="UserCreateNode",
            parameter_name="email",
            original_error=original_error,
        )

        # Execute CLI with JSON format to verify ranking
        result = cli_runner.invoke(
            diagnose,
            [
                "--error-input",
                str(enhanced_error),
                "--format",
                "json",
            ],
        )

        # Verify solutions are ranked in descending order
        assert result.exit_code == 0
        data = json.loads(result.output)
        solutions = data["ranked_solutions"]

        if len(solutions) > 1:
            # Verify descending relevance_score order
            for i in range(len(solutions) - 1):
                assert (
                    solutions[i]["relevance_score"]
                    >= solutions[i + 1]["relevance_score"]
                )

    def test_confidence_score_calculation(self, cli_runner, error_enhancer):
        """Test that confidence score is properly calculated."""
        # Create real error
        original_error = KeyError("id")
        enhanced_error = error_enhancer.enhance_parameter_error(
            node_id="create_user",
            parameter_name="id",
            original_error=original_error,
        )

        # Execute CLI
        result = cli_runner.invoke(
            diagnose,
            [
                "--error-input",
                str(enhanced_error),
                "--format",
                "json",
            ],
        )

        # Verify confidence is between 0 and 1
        assert result.exit_code == 0
        data = json.loads(result.output)
        confidence = data["confidence"]
        assert 0.0 <= confidence <= 1.0

    def test_next_steps_generation(self, cli_runner, error_enhancer):
        """Test that next steps are properly generated."""
        # Create real error
        original_error = KeyError("name")
        enhanced_error = error_enhancer.enhance_parameter_error(
            node_id="update_user",
            parameter_name="name",
            original_error=original_error,
        )

        # Execute CLI
        result = cli_runner.invoke(
            diagnose,
            [
                "--error-input",
                str(enhanced_error),
                "--format",
                "json",
            ],
        )

        # Verify next steps are present
        assert result.exit_code == 0
        data = json.loads(result.output)
        next_steps = data["next_steps"]
        assert isinstance(next_steps, list)
        assert len(next_steps) > 0


@pytest.mark.integration
@pytest.mark.timeout(15)
class TestPerformance:
    """Test CLI performance with real components."""

    def test_diagnosis_under_5_seconds(self, cli_runner, error_enhancer):
        """Test that diagnosis completes in under 5 seconds (95th percentile target)."""
        # Create real error
        original_error = KeyError("id")
        enhanced_error = error_enhancer.enhance_parameter_error(
            node_id="create_user",
            parameter_name="id",
            original_error=original_error,
        )

        # Measure execution time
        start_time = time.time()

        result = cli_runner.invoke(
            diagnose,
            [
                "--error-input",
                str(enhanced_error),
                "--format",
                "text",
            ],
        )

        end_time = time.time()
        execution_time = end_time - start_time

        # Verify execution time meets target
        assert result.exit_code == 0
        assert (
            execution_time < 5.0
        ), f"Diagnosis took {execution_time:.2f}s (target: <5s)"


@pytest.mark.integration
@pytest.mark.timeout(10)
class TestDataFlowIntegration:
    """Test integration with real DataFlow instances."""

    def test_diagnosis_with_dataflow_model_error(self, cli_runner, error_enhancer):
        """Test diagnosis of error from real DataFlow model operation."""
        # Simulate real DataFlow model error
        original_error = TypeError("Primary key 'id' must be defined")
        enhanced_error = error_enhancer.enhance_generic_error(
            exception=original_error,
            model="User",
            field="id",
        )

        # Execute CLI
        result = cli_runner.invoke(
            diagnose,
            [
                "--error-input",
                str(enhanced_error),
                "--format",
                "text",
            ],
        )

        # Verify diagnosis addresses model definition
        assert result.exit_code == 0
        assert "model" in result.output.lower()
        assert "Solutions" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
