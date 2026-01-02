"""
Unit tests for Phase 5.3 workflow features.

Tests the following SDK components:
1. Cycle Templates (CycleTemplates)
2. Migration Helpers (DAGToCycleConverter)
3. Validation & Linting Tools (CycleLinter)
"""

import pytest
from kailash import Workflow
from kailash.nodes.code import PythonCodeNode
from kailash.workflow.migration import DAGToCycleConverter
from kailash.workflow.templates import CycleTemplates
from kailash.workflow.validation import CycleLinter, IssueSeverity


@pytest.mark.requires_isolation
class TestPhase53Features:
    """Test Phase 5.3 workflow enhancement features."""

    def test_cycle_templates_optimization(self):
        """Test CycleTemplates.optimization_cycle functionality."""
        # Create workflow
        workflow = Workflow("templates_test", "Templates Test")

        # Add simple nodes for testing
        processor = PythonCodeNode(
            name="processor", code="result = {'quality': 0.8, 'iteration': 1}"
        )
        workflow.add_node("processor", processor)

        evaluator = PythonCodeNode(
            name="evaluator",
            code="result = {'quality': 0.9, 'evaluation_complete': True}",
        )
        workflow.add_node("evaluator", evaluator)

        # Test optimization cycle template
        cycle_id = CycleTemplates.optimization_cycle(
            workflow=workflow,
            processor_node="processor",
            evaluator_node="evaluator",
            convergence="quality > 0.85",
            max_iterations=5,
        )

        # Verify cycle was created (cycle_id returned)
        assert cycle_id is not None
        assert isinstance(cycle_id, str)

        # Verify workflow has cycles
        assert workflow.has_cycles()

    def test_dag_to_cycle_converter(self):
        """Test DAGToCycleConverter analysis functionality."""
        # Create DAG workflow
        workflow = Workflow("dag_test", "DAG Test")

        # Add nodes that might form cycles
        optimizer = PythonCodeNode(
            name="optimizer", code="result = {'data': 'optimized', 'iteration': 1}"
        )
        workflow.add_node("optimizer", optimizer)

        evaluator = PythonCodeNode(
            name="evaluator", code="result = {'quality': 0.8, 'should_retry': False}"
        )
        workflow.add_node("evaluator", evaluator)

        # Connect nodes in DAG pattern
        workflow.connect("optimizer", "evaluator")

        # Test converter
        converter = DAGToCycleConverter(workflow)
        opportunities = converter.analyze_cyclification_opportunities()

        # Verify analysis results
        assert isinstance(opportunities, list)
        # The specific opportunities depend on implementation
        # Just verify the method returns a list structure

    def test_cycle_linter_basic(self):
        """Test CycleLinter basic validation functionality."""
        # Create workflow with potential issues
        workflow = Workflow("lint_test", "Lint Test")

        # Add simple cyclic pattern
        counter = PythonCodeNode(name="counter", code="result = {'count': 1}")
        workflow.add_node("counter", counter)

        # Create self-loop with new API
        workflow.create_cycle("test_cycle").connect(
            "counter", "counter"
        ).max_iterations(10).build()

        # Test linter
        linter = CycleLinter(workflow)

        # Verify linter exists and can be created
        assert linter is not None
        assert linter.workflow == workflow

        # If lint method exists, test it
        if hasattr(linter, "lint"):
            issues = linter.lint()
            assert isinstance(issues, list)

    def test_cycle_templates_retry_pattern(self):
        """Test retry pattern template."""
        workflow = Workflow("retry_test", "Retry Test")

        # Add operation node
        operation = PythonCodeNode(
            name="operation", code="result = {'success': False, 'attempt': 1}"
        )
        workflow.add_node("operation", operation)

        # Test retry template if it exists
        if hasattr(CycleTemplates, "retry_pattern"):
            cycle_id = CycleTemplates.retry_pattern(
                workflow=workflow,
                operation_node="operation",
                max_retries=3,
                retry_delay=1.0,
            )

            assert cycle_id is not None
            assert workflow.has_cycles()

    def test_converter_with_complex_dag(self):
        """Test converter with more complex DAG structure."""
        workflow = Workflow("complex_dag", "Complex DAG")

        # Create a more complex DAG
        nodes = {}
        for i in range(5):
            node = PythonCodeNode(
                name=f"node_{i}", code=f"result = {{'data': 'processed_{i}'}}"
            )
            nodes[f"node_{i}"] = node
            workflow.add_node(f"node_{i}", node)

        # Create connections
        workflow.connect("node_0", "node_1")
        workflow.connect("node_1", "node_2")
        workflow.connect("node_2", "node_3")
        workflow.connect("node_3", "node_4")
        workflow.connect("node_1", "node_3")  # Skip connection

        # Test converter
        converter = DAGToCycleConverter(workflow)
        opportunities = converter.analyze_cyclification_opportunities()

        # Verify it handles complex structures
        assert isinstance(opportunities, list)

    def test_linter_with_valid_cycle(self):
        """Test linter with properly configured cycle."""
        workflow = Workflow("valid_cycle", "Valid Cycle")

        # Add accumulator node
        accumulator = PythonCodeNode(
            name="accumulator", code="result = {'total': 10, 'done': False}"
        )
        workflow.add_node("accumulator", accumulator)

        # Create well-configured cycle
        workflow.create_cycle("valid_cycle").connect(
            "accumulator", "accumulator"
        ).max_iterations(10).converge_when("done == True").build()

        # Test linter creation
        linter = CycleLinter(workflow)
        assert linter is not None
        assert linter.workflow == workflow

    def test_cycle_templates_error_handling(self):
        """Test cycle templates handle errors gracefully."""
        workflow = Workflow("error_test", "Error Test")

        # Try to create cycle with non-existent nodes
        # This should raise an error during the connect phase
        with pytest.raises(
            Exception
        ):  # Can be ValueError, KeyError, or WorkflowValidationError
            CycleTemplates.optimization_cycle(
                workflow=workflow,
                processor_node="missing_node",
                evaluator_node="another_missing",
                convergence="quality > 0.85",
                max_iterations=5,
            )

    def test_converter_empty_workflow(self):
        """Test converter handles empty workflows."""
        workflow = Workflow("empty", "Empty Workflow")

        converter = DAGToCycleConverter(workflow)
        opportunities = converter.analyze_cyclification_opportunities()

        # Should handle empty workflow gracefully
        assert isinstance(opportunities, list)
        assert len(opportunities) == 0

    def test_workflow_has_cycles_method(self):
        """Test workflow.has_cycles() method."""
        # Workflow without cycles
        workflow1 = Workflow("no_cycles", "No Cycles")
        node1 = PythonCodeNode(name="node1", code="result = {'data': 1}")
        node2 = PythonCodeNode(name="node2", code="result = {'data': 2}")
        workflow1.add_node("node1", node1)
        workflow1.add_node("node2", node2)
        workflow1.connect("node1", "node2")

        assert not workflow1.has_cycles()

        # Workflow with cycles
        workflow2 = Workflow("with_cycles", "With Cycles")
        counter = PythonCodeNode(name="counter", code="result = {'count': 1}")
        workflow2.add_node("counter", counter)
        workflow2.create_cycle("test_cycle").connect(
            "counter", "counter"
        ).max_iterations(5).build()

        assert workflow2.has_cycles()
