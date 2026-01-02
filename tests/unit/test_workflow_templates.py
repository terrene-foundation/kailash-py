"""
Unit tests for workflow templates module.

Tests all CycleTemplates methods, configuration validation, and pattern correctness.
Following TDD principles - these tests drive the implementation improvements.
"""

import time
from unittest.mock import MagicMock, patch

import pytest
from kailash.nodes.code import PythonCodeNode
from kailash.workflow import Workflow
from kailash.workflow.templates import CycleTemplate, CycleTemplates


class TestCycleTemplate:
    """Test CycleTemplate dataclass functionality."""

    def test_cycle_template_creation(self):
        """Test creating a CycleTemplate with required fields."""
        template = CycleTemplate(
            name="test_template",
            description="A test template",
            nodes=["node1", "node2"],
        )

        assert template.name == "test_template"
        assert template.description == "A test template"
        assert template.nodes == ["node1", "node2"]
        assert template.convergence_condition is None
        assert template.max_iterations == 100
        assert template.timeout is None
        assert template.parameters is None

    def test_cycle_template_with_all_fields(self):
        """Test creating a CycleTemplate with all fields specified."""
        template = CycleTemplate(
            name="full_template",
            description="A complete template",
            nodes=["node1", "node2", "node3"],
            convergence_condition="quality > 0.95",
            max_iterations=50,
            timeout=300.0,
            parameters={"param1": "value1", "param2": 42},
        )

        assert template.name == "full_template"
        assert template.description == "A complete template"
        assert template.nodes == ["node1", "node2", "node3"]
        assert template.convergence_condition == "quality > 0.95"
        assert template.max_iterations == 50
        assert template.timeout == 300.0
        assert template.parameters == {"param1": "value1", "param2": 42}

    def test_cycle_template_nodes_validation(self):
        """Test that nodes list is properly handled."""
        # Empty nodes list should be allowed
        template = CycleTemplate(
            name="empty_nodes", description="Template with empty nodes", nodes=[]
        )
        assert template.nodes == []

        # Single node
        template = CycleTemplate(
            name="single_node", description="Template with single node", nodes=["node1"]
        )
        assert template.nodes == ["node1"]


class TestCycleTemplatesOptimization:
    """Test optimization cycle template functionality."""

    def test_optimization_cycle_basic(self):
        """Test basic optimization cycle creation."""
        workflow = Workflow("test_opt", "Test Optimization")

        # Add required nodes
        workflow.add_node(
            "processor",
            PythonCodeNode(name="processor", code="result = {'data': 'processed'}"),
        )
        workflow.add_node(
            "evaluator",
            PythonCodeNode(name="evaluator", code="result = {'quality': 0.8}"),
        )

        # Mock the workflow methods to verify calls
        workflow.connect = MagicMock()
        workflow.create_cycle = MagicMock()

        # Create mock cycle builder for chaining
        mock_cycle_builder = MagicMock()
        mock_cycle_builder.connect.return_value = mock_cycle_builder
        mock_cycle_builder.max_iterations.return_value = mock_cycle_builder
        mock_cycle_builder.converge_when.return_value = mock_cycle_builder
        mock_cycle_builder.build.return_value = "cycle_built"
        workflow.create_cycle.return_value = mock_cycle_builder

        cycle_id = CycleTemplates.optimization_cycle(
            workflow=workflow,
            processor_node="processor",
            evaluator_node="evaluator",
        )

        # Verify workflow connections were made
        workflow.connect.assert_called_once_with("processor", "evaluator")

        # Verify cycle creation was called
        workflow.create_cycle.assert_called_once()

        # Verify cycle builder chain was called correctly
        mock_cycle_builder.connect.assert_called_once_with("evaluator", "processor")
        mock_cycle_builder.max_iterations.assert_called_once_with(50)  # default
        mock_cycle_builder.converge_when.assert_called_once_with(
            "quality > 0.9"
        )  # default
        mock_cycle_builder.build.assert_called_once()

        # Verify cycle_id is returned
        assert cycle_id.startswith("optimization_cycle_")

    def test_optimization_cycle_custom_parameters(self):
        """Test optimization cycle with custom parameters."""
        workflow = Workflow("test_opt", "Test Optimization")

        # Add required nodes
        workflow.add_node(
            "custom_processor",
            PythonCodeNode(
                name="custom_processor", code="result = {'data': 'processed'}"
            ),
        )
        workflow.add_node(
            "custom_evaluator",
            PythonCodeNode(name="custom_evaluator", code="result = {'quality': 0.95}"),
        )

        # Mock the workflow methods
        workflow.connect = MagicMock()
        workflow.create_cycle = MagicMock()

        # Create mock cycle builder
        mock_cycle_builder = MagicMock()
        mock_cycle_builder.connect.return_value = mock_cycle_builder
        mock_cycle_builder.max_iterations.return_value = mock_cycle_builder
        mock_cycle_builder.converge_when.return_value = mock_cycle_builder
        mock_cycle_builder.build.return_value = "cycle_built"
        workflow.create_cycle.return_value = mock_cycle_builder

        cycle_id = CycleTemplates.optimization_cycle(
            workflow=workflow,
            processor_node="custom_processor",
            evaluator_node="custom_evaluator",
            convergence="quality > 0.98",
            max_iterations=75,
            cycle_id="custom_optimization_cycle",
        )

        # Verify custom parameters were used
        mock_cycle_builder.max_iterations.assert_called_once_with(75)
        mock_cycle_builder.converge_when.assert_called_once_with("quality > 0.98")

        # Verify custom cycle_id was used
        assert cycle_id == "custom_optimization_cycle"

    def test_optimization_cycle_id_generation(self):
        """Test that cycle IDs are generated correctly when not provided."""
        workflow = Workflow("test_opt", "Test Optimization")

        # Add required nodes
        workflow.add_node(
            "processor", PythonCodeNode(name="processor", code="result = {}")
        )
        workflow.add_node(
            "evaluator", PythonCodeNode(name="evaluator", code="result = {}")
        )

        # Mock workflow methods
        workflow.connect = MagicMock()
        workflow.create_cycle = MagicMock()
        mock_cycle_builder = MagicMock()
        mock_cycle_builder.connect.return_value = mock_cycle_builder
        mock_cycle_builder.max_iterations.return_value = mock_cycle_builder
        mock_cycle_builder.converge_when.return_value = mock_cycle_builder
        mock_cycle_builder.build.return_value = "cycle_built"
        workflow.create_cycle.return_value = mock_cycle_builder

        # Mock time to ensure consistent ID generation
        with patch("kailash.workflow.templates.time.time", return_value=1234567890):
            cycle_id = CycleTemplates.optimization_cycle(
                workflow=workflow,
                processor_node="processor",
                evaluator_node="evaluator",
            )

        assert cycle_id == "optimization_cycle_1234567890000"


class TestCycleTemplatesRetry:
    """Test retry cycle template functionality."""

    def test_retry_cycle_basic(self):
        """Test basic retry cycle creation."""
        workflow = Workflow("test_retry", "Test Retry")

        # Add target node
        workflow.add_node(
            "api_call",
            PythonCodeNode(name="api_call", code="result = {'success': True}"),
        )

        # Mock workflow methods
        workflow.add_node = MagicMock()
        workflow.connect = MagicMock()

        cycle_id = CycleTemplates.retry_cycle(
            workflow=workflow,
            target_node="api_call",
        )

        # Verify retry controller node was added
        workflow.add_node.assert_called_once()
        call_args = workflow.add_node.call_args
        assert call_args[0][0] == "api_call_retry_controller"  # node_id
        assert isinstance(call_args[0][1], PythonCodeNode)  # node instance

        # Verify connections were made
        assert workflow.connect.call_count == 2

        # Verify cycle_id is returned
        assert cycle_id.startswith("retry_cycle_")

    def test_retry_cycle_custom_parameters(self):
        """Test retry cycle with custom parameters."""
        workflow = Workflow("test_retry", "Test Retry")

        # Add target node
        workflow.add_node(
            "custom_api", PythonCodeNode(name="custom_api", code="result = {}")
        )

        # Mock workflow methods
        workflow.add_node = MagicMock()
        workflow.connect = MagicMock()

        cycle_id = CycleTemplates.retry_cycle(
            workflow=workflow,
            target_node="custom_api",
            max_retries=5,
            backoff_strategy="linear",
            success_condition="status == 'ok'",
            cycle_id="custom_retry_cycle",
        )

        # Verify retry controller node was added with correct configuration
        workflow.add_node.assert_called_once()
        call_args = workflow.add_node.call_args
        assert call_args[0][0] == "custom_api_retry_controller"

        # Check that the code contains the custom parameters
        retry_node = call_args[0][1]
        assert "5" in retry_node.code  # max_retries
        assert "linear" in retry_node.code  # backoff_strategy

        # Verify custom cycle_id was used
        assert cycle_id == "custom_retry_cycle"

    def test_retry_cycle_backoff_strategies(self):
        """Test retry cycle with different backoff strategies."""
        workflow = Workflow("test_retry", "Test Retry")
        workflow.add_node("target", PythonCodeNode(name="target", code="result = {}"))

        # Mock workflow methods
        workflow.add_node = MagicMock()
        workflow.connect = MagicMock()

        # Test exponential backoff
        CycleTemplates.retry_cycle(
            workflow=workflow,
            target_node="target",
            backoff_strategy="exponential",
        )

        call_args = workflow.add_node.call_args
        retry_node = call_args[0][1]
        assert "exponential" in retry_node.code
        assert "2 ** (attempt - 1)" in retry_node.code

        # Reset mock and test linear backoff
        workflow.add_node.reset_mock()

        CycleTemplates.retry_cycle(
            workflow=workflow,
            target_node="target",
            backoff_strategy="linear",
        )

        call_args = workflow.add_node.call_args
        retry_node = call_args[0][1]
        assert "linear" in retry_node.code
        assert "attempt * 1.0" in retry_node.code

        # Reset mock and test fixed backoff
        workflow.add_node.reset_mock()

        CycleTemplates.retry_cycle(
            workflow=workflow,
            target_node="target",
            backoff_strategy="fixed",
        )

        call_args = workflow.add_node.call_args
        retry_node = call_args[0][1]
        assert "fixed" in retry_node.code

    def test_retry_cycle_code_generation(self):
        """Test that retry cycle generates proper Python code."""
        workflow = Workflow("test_retry", "Test Retry")
        workflow.add_node("target", PythonCodeNode(name="target", code="result = {}"))

        # Mock workflow methods
        workflow.add_node = MagicMock()
        workflow.connect = MagicMock()

        CycleTemplates.retry_cycle(
            workflow=workflow,
            target_node="target",
            max_retries=3,
            backoff_strategy="exponential",
        )

        call_args = workflow.add_node.call_args
        retry_node = call_args[0][1]
        code = retry_node.code

        # Check that code contains essential retry logic
        assert "import time" in code
        assert "import random" in code
        assert "attempt = attempt" in code
        assert "should_retry = attempt <= 3" in code
        assert "backoff_time" in code
        assert "jitter" in code
        assert "result = {" in code


class TestCycleTemplatesDataQuality:
    """Test data quality cycle template functionality."""

    def test_data_quality_cycle_basic(self):
        """Test basic data quality cycle creation."""
        workflow = Workflow("test_quality", "Test Data Quality")

        # Add required nodes
        workflow.add_node(
            "cleaner", PythonCodeNode(name="cleaner", code="result = {'cleaned': True}")
        )
        workflow.add_node(
            "validator",
            PythonCodeNode(name="validator", code="result = {'quality': 0.96}"),
        )

        # Mock workflow methods to check for call without actual implementation
        workflow.connect = MagicMock()

        cycle_id = CycleTemplates.data_quality_cycle(
            workflow=workflow,
            cleaner_node="cleaner",
            validator_node="validator",
        )

        # Should start with correct prefix
        assert cycle_id.startswith("data_quality_cycle_")

    def test_data_quality_cycle_custom_parameters(self):
        """Test data quality cycle with custom parameters."""
        workflow = Workflow("test_quality", "Test Data Quality")

        # Add required nodes
        workflow.add_node(
            "advanced_cleaner",
            PythonCodeNode(name="advanced_cleaner", code="result = {}"),
        )
        workflow.add_node(
            "advanced_validator",
            PythonCodeNode(name="advanced_validator", code="result = {}"),
        )

        # Mock workflow methods
        workflow.connect = MagicMock()

        cycle_id = CycleTemplates.data_quality_cycle(
            workflow=workflow,
            cleaner_node="advanced_cleaner",
            validator_node="advanced_validator",
            quality_threshold=0.99,
            max_iterations=20,
            cycle_id="custom_quality_cycle",
        )

        # Verify custom cycle_id was used
        assert cycle_id == "custom_quality_cycle"


class TestCycleTemplatesParameterValidation:
    """Test parameter validation across all template methods."""

    def test_empty_workflow_handling(self):
        """Test that templates handle workflows appropriately."""
        workflow = Workflow("empty", "Empty Workflow")

        # Mock workflow methods to prevent actual execution
        workflow.add_node = MagicMock()
        workflow.connect = MagicMock()
        workflow.create_cycle = MagicMock()

        # Create mock cycle builder
        mock_cycle_builder = MagicMock()
        mock_cycle_builder.connect.return_value = mock_cycle_builder
        mock_cycle_builder.max_iterations.return_value = mock_cycle_builder
        mock_cycle_builder.converge_when.return_value = mock_cycle_builder
        mock_cycle_builder.build.return_value = "cycle_built"
        workflow.create_cycle.return_value = mock_cycle_builder

        # These should not raise exceptions even with non-existent nodes
        # (the actual workflow execution would fail, but template creation should succeed)

        optimization_id = CycleTemplates.optimization_cycle(
            workflow, "nonexistent_processor", "nonexistent_evaluator"
        )
        assert optimization_id is not None

        retry_id = CycleTemplates.retry_cycle(workflow, "nonexistent_target")
        assert retry_id is not None

    def test_parameter_boundary_values(self):
        """Test templates with boundary parameter values."""
        workflow = Workflow("boundary", "Boundary Test")

        # Mock workflow methods
        workflow.add_node = MagicMock()
        workflow.connect = MagicMock()
        workflow.create_cycle = MagicMock()

        # Create mock cycle builder
        mock_cycle_builder = MagicMock()
        mock_cycle_builder.connect.return_value = mock_cycle_builder
        mock_cycle_builder.max_iterations.return_value = mock_cycle_builder
        mock_cycle_builder.converge_when.return_value = mock_cycle_builder
        mock_cycle_builder.build.return_value = "cycle_built"
        workflow.create_cycle.return_value = mock_cycle_builder

        # Test with minimum values
        cycle_id = CycleTemplates.optimization_cycle(
            workflow, "processor", "evaluator", max_iterations=1
        )
        mock_cycle_builder.max_iterations.assert_called_with(1)

        # Test with very high values
        cycle_id = CycleTemplates.optimization_cycle(
            workflow, "processor", "evaluator", max_iterations=10000
        )
        mock_cycle_builder.max_iterations.assert_called_with(10000)

    def test_string_parameter_handling(self):
        """Test that string parameters are handled correctly."""
        workflow = Workflow("string_test", "String Parameter Test")

        # Mock workflow methods
        workflow.add_node = MagicMock()
        workflow.connect = MagicMock()

        # Test with various convergence condition formats
        conditions = [
            "quality > 0.95",
            "accuracy >= 0.9 and loss < 0.1",
            "iteration_count > 10",
            "status == 'complete'",
        ]

        for condition in conditions:
            cycle_id = CycleTemplates.retry_cycle(
                workflow, "target", success_condition=condition
            )
            assert cycle_id is not None

    def test_cycle_id_uniqueness(self):
        """Test that generated cycle IDs are unique when not specified."""
        workflow = Workflow("unique_test", "Unique ID Test")

        # Mock workflow methods
        workflow.add_node = MagicMock()
        workflow.connect = MagicMock()
        workflow.create_cycle = MagicMock()
        mock_cycle_builder = MagicMock()
        mock_cycle_builder.connect.return_value = mock_cycle_builder
        mock_cycle_builder.max_iterations.return_value = mock_cycle_builder
        mock_cycle_builder.converge_when.return_value = mock_cycle_builder
        mock_cycle_builder.build.return_value = "cycle_built"
        workflow.create_cycle.return_value = mock_cycle_builder

        # Generate multiple cycle IDs
        ids = []
        for i in range(5):
            cycle_id = CycleTemplates.optimization_cycle(
                workflow, f"processor_{i}", f"evaluator_{i}"
            )
            ids.append(cycle_id)
            # Small delay to ensure different timestamps
            time.sleep(0.001)

        # All IDs should be unique
        assert len(set(ids)) == len(ids)

        # All should have correct prefix
        for cycle_id in ids:
            assert cycle_id.startswith("optimization_cycle_")
