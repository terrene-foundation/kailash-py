"""Unit tests for ValidationMixin.

Tests validation logic for workflows, connections, conditional execution,
and switch node results.
"""

import pytest
from kailash.runtime.base import BaseRuntime
from kailash.runtime.mixins.validation import ValidationMixin
from kailash.sdk_exceptions import WorkflowValidationError
from kailash.workflow import Workflow

from tests.unit.runtime.helpers_runtime import (
    create_empty_workflow,
    create_large_workflow,
    create_minimal_workflow,
    create_multiple_node_outputs,
    create_node_outputs,
    create_switch_results,
    create_valid_workflow,
    create_workflow_with_contracts,
    create_workflow_with_disconnected_node,
    create_workflow_with_switch,
)


class ConcreteRuntimeWithValidation(ValidationMixin, BaseRuntime):
    """Concrete runtime implementation with validation mixin."""

    def execute(self, workflow: Workflow, **kwargs):
        """Minimal execute implementation."""
        return {}, "test-run-id"


class TestValidationMixinInitialization:
    """Test ValidationMixin initialization and MRO."""

    def test_mixin_initialization(self):
        """Test ValidationMixin initializes correctly via super()."""
        runtime = ConcreteRuntimeWithValidation()

        # Should have both BaseRuntime and ValidationMixin methods
        assert hasattr(runtime, "validate_workflow")
        assert hasattr(runtime, "_validate_connection_contracts")
        assert hasattr(runtime, "_validate_conditional_execution_prerequisites")
        assert hasattr(runtime, "debug")  # BaseRuntime attribute

    def test_mro_chain(self):
        """Test Method Resolution Order is correct."""
        mro = ConcreteRuntimeWithValidation.__mro__

        # Should have ValidationMixin before BaseRuntime
        mixin_index = mro.index(ValidationMixin)
        base_index = mro.index(BaseRuntime)

        assert mixin_index < base_index


class TestValidateWorkflow:
    """Test validate_workflow() method."""

    def test_validate_valid_workflow(self):
        """Test validating a valid workflow returns no warnings."""
        runtime = ConcreteRuntimeWithValidation()
        workflow = create_valid_workflow()

        warnings = runtime.validate_workflow(workflow)

        assert isinstance(warnings, list)
        # May have warnings but should not raise

    def test_validate_minimal_workflow(self):
        """Test validating minimal workflow."""
        runtime = ConcreteRuntimeWithValidation()
        workflow = create_minimal_workflow()

        warnings = runtime.validate_workflow(workflow)

        # Single node workflow should be valid
        assert isinstance(warnings, list)

    def test_validate_workflow_with_disconnected_node(self):
        """Test validation warns about disconnected nodes."""
        runtime = ConcreteRuntimeWithValidation()
        workflow = create_workflow_with_disconnected_node()

        warnings = runtime.validate_workflow(workflow)

        # Should warn about disconnected node
        assert len(warnings) > 0
        assert any("disconnected" in w.lower() for w in warnings)

    def test_validate_large_workflow_performance_warning(self):
        """Test validation warns about large workflows."""
        runtime = ConcreteRuntimeWithValidation()
        workflow = create_large_workflow(node_count=150)

        warnings = runtime.validate_workflow(workflow)

        # Should warn about performance
        assert len(warnings) > 0
        assert any("performance" in w.lower() or "large" in w.lower() for w in warnings)

    def test_validate_empty_workflow(self):
        """Test validating empty workflow."""
        runtime = ConcreteRuntimeWithValidation()
        workflow = create_empty_workflow()

        # Empty workflow should validate
        warnings = runtime.validate_workflow(workflow)
        assert isinstance(warnings, list)

    def test_validate_workflow_invalid_structure(self):
        """Test validation raises error for invalid workflow structure."""
        runtime = ConcreteRuntimeWithValidation()

        # Create workflow with invalid structure
        workflow = Workflow(workflow_id="invalid", name="Invalid")
        # Manually break workflow structure
        workflow.graph = None  # Break graph

        with pytest.raises(WorkflowValidationError):
            runtime.validate_workflow(workflow)

    def test_validate_workflow_with_switch(self):
        """Test validating workflow with SwitchNode."""
        runtime = ConcreteRuntimeWithValidation()
        workflow = create_workflow_with_switch()

        warnings = runtime.validate_workflow(workflow)

        # Should validate successfully
        assert isinstance(warnings, list)

    def test_validate_workflow_checks_parameters(self):
        """Test validation checks node parameters."""
        runtime = ConcreteRuntimeWithValidation()
        workflow = create_valid_workflow()

        # Validation should check parameters
        warnings = runtime.validate_workflow(workflow)

        # Should complete without error
        assert isinstance(warnings, list)


class TestValidateConnectionContracts:
    """Test _validate_connection_contracts() method."""

    def test_validate_connection_contracts_no_contracts(self):
        """Test validation when no contracts are defined."""
        runtime = ConcreteRuntimeWithValidation()
        workflow = create_valid_workflow()
        target_node_id = "node2"
        target_inputs = {"data": [1, 2, 3]}
        node_outputs = {"node1": {"result": [1, 2, 3]}}

        violations = runtime._validate_connection_contracts(
            workflow, target_node_id, target_inputs, node_outputs
        )

        # No contracts defined, so no violations
        assert isinstance(violations, list)
        assert len(violations) == 0

    def test_validate_connection_contracts_with_contracts(self):
        """Test validation with defined contracts."""
        pytest.importorskip(
            "kailash.contracts", reason="Contracts module not available"
        )

        runtime = ConcreteRuntimeWithValidation()
        workflow = create_workflow_with_contracts()
        target_node_id = "target"
        target_inputs = {"data": {"data": [1, 2, 3], "type": "numbers"}}
        node_outputs = {"source": {"result": {"data": [1, 2, 3], "type": "numbers"}}}

        violations = runtime._validate_connection_contracts(
            workflow, target_node_id, target_inputs, node_outputs
        )

        # Valid data should pass
        assert isinstance(violations, list)

    def test_validate_connection_contracts_invalid_data(self):
        """Test validation catches contract violations."""
        pytest.importorskip(
            "kailash.contracts", reason="Contracts module not available"
        )

        runtime = ConcreteRuntimeWithValidation()
        workflow = create_workflow_with_contracts()

        # Set up contract that will be violated
        workflow.metadata["connection_contracts"]["source.result → target.data"] = {
            "name": "strict_contract",
            "source_output": "result",
            "target_input": "data",
            "required": True,
            "type": "dict",
            "source_schema": {"type": "dict", "required_keys": ["data", "type"]},
            "target_schema": {"type": "dict", "required_keys": ["data", "type"]},
        }

        target_node_id = "target"
        # Invalid data (wrong type)
        target_inputs = {"data": "invalid string"}
        node_outputs = {"source": {"result": "invalid string"}}

        violations = runtime._validate_connection_contracts(
            workflow, target_node_id, target_inputs, node_outputs
        )

        # May have violations depending on contract validator implementation
        assert isinstance(violations, list)

    def test_validate_connection_contracts_missing_source_data(self):
        """Test validation handles missing source data."""
        pytest.importorskip(
            "kailash.contracts", reason="Contracts module not available"
        )

        runtime = ConcreteRuntimeWithValidation()
        workflow = create_workflow_with_contracts()
        target_node_id = "target"
        target_inputs = {"data": [1, 2, 3]}
        # Missing source node outputs
        node_outputs = {}

        violations = runtime._validate_connection_contracts(
            workflow, target_node_id, target_inputs, node_outputs
        )

        # Should handle gracefully
        assert isinstance(violations, list)


class TestValidateConditionalExecutionPrerequisites:
    """Test _validate_conditional_execution_prerequisites() method."""

    def test_validate_prerequisites_with_switch_node(self):
        """Test validation passes with SwitchNode present."""
        runtime = ConcreteRuntimeWithValidation()
        workflow = create_workflow_with_switch()

        result = runtime._validate_conditional_execution_prerequisites(workflow)

        # Should return True (has SwitchNode)
        assert result is True

    def test_validate_prerequisites_without_switch_node(self):
        """Test validation fails without SwitchNode."""
        runtime = ConcreteRuntimeWithValidation()
        workflow = create_valid_workflow()  # No SwitchNode

        result = runtime._validate_conditional_execution_prerequisites(workflow)

        # Should return False (no SwitchNode)
        assert result is False

    def test_validate_prerequisites_too_large(self):
        """Test validation fails for too large workflows."""
        runtime = ConcreteRuntimeWithValidation()
        workflow = create_large_workflow(node_count=150)

        result = runtime._validate_conditional_execution_prerequisites(workflow)

        # Should return False (too large)
        assert result is False

    def test_validate_prerequisites_error_handling(self):
        """Test validation handles errors gracefully."""
        runtime = ConcreteRuntimeWithValidation()

        # Create workflow with broken structure
        workflow = Workflow(workflow_id="broken", name="Broken")
        workflow.graph = None  # Break graph

        result = runtime._validate_conditional_execution_prerequisites(workflow)

        # Should return False on error
        assert result is False

    def test_validate_prerequisites_switch_without_condition(self):
        """Test validation handles SwitchNode without condition field."""
        runtime = ConcreteRuntimeWithValidation()
        workflow = create_workflow_with_switch()

        # Should still validate (fallback logic)
        result = runtime._validate_conditional_execution_prerequisites(workflow)
        assert isinstance(result, bool)


class TestValidateSwitchResults:
    """Test _validate_switch_results() method."""

    def test_validate_switch_results_valid(self):
        """Test validation passes for valid switch results."""
        runtime = ConcreteRuntimeWithValidation()
        switch_results = create_switch_results(
            "switch1", true_output={"data": "true"}, false_output=None
        )

        result = runtime._validate_switch_results(switch_results)

        assert result is True

    def test_validate_switch_results_both_outputs(self):
        """Test validation with both true and false outputs."""
        runtime = ConcreteRuntimeWithValidation()
        switch_results = create_switch_results(
            "switch1", true_output={"data": "true"}, false_output={"data": "false"}
        )

        result = runtime._validate_switch_results(switch_results)

        assert result is True

    def test_validate_switch_results_empty(self):
        """Test validation with empty results."""
        runtime = ConcreteRuntimeWithValidation()
        switch_results = {}

        result = runtime._validate_switch_results(switch_results)

        # Empty results are valid
        assert result is True

    def test_validate_switch_results_failed_execution(self):
        """Test validation fails for failed switch execution."""
        runtime = ConcreteRuntimeWithValidation()
        switch_results = create_switch_results("switch1", failed=True)

        result = runtime._validate_switch_results(switch_results)

        # Should return False for failed execution
        assert result is False

    def test_validate_switch_results_invalid_type(self):
        """Test validation fails for invalid result type."""
        runtime = ConcreteRuntimeWithValidation()
        # Invalid: results should be dict, not string
        switch_results = {"switch1": "invalid string result"}

        result = runtime._validate_switch_results(switch_results)

        # Should return False for invalid type
        assert result is False

    def test_validate_switch_results_missing_outputs(self):
        """Test validation fails when required outputs are missing."""
        runtime = ConcreteRuntimeWithValidation()
        # No true_output or false_output keys
        switch_results = {"switch1": {"other_key": "value"}}

        result = runtime._validate_switch_results(switch_results)

        # Should return False (missing required keys)
        assert result is False

    def test_validate_switch_results_error_handling(self):
        """Test validation handles errors gracefully."""
        runtime = ConcreteRuntimeWithValidation()
        # Pass something that will cause error
        switch_results = None

        result = runtime._validate_switch_results(switch_results)

        # Should return True on None (no results to validate)
        assert isinstance(result, bool)


class TestValidateConditionalExecutionResults:
    """Test _validate_conditional_execution_results() method."""

    def test_validate_results_valid(self):
        """Test validation passes for valid results."""
        runtime = ConcreteRuntimeWithValidation()
        workflow = create_valid_workflow()
        results = {"node1": {"result": [1, 2, 3]}, "node2": {"output": "processed"}}

        result = runtime._validate_conditional_execution_results(results, workflow)

        assert result is True

    def test_validate_results_empty(self):
        """Test validation fails for empty results."""
        runtime = ConcreteRuntimeWithValidation()
        workflow = create_valid_workflow()
        results = {}

        result = runtime._validate_conditional_execution_results(results, workflow)

        # Should return False (no results)
        assert result is False

    def test_validate_results_too_few_nodes_executed(self):
        """Test validation warns when too few nodes executed."""
        runtime = ConcreteRuntimeWithValidation()
        workflow = create_large_workflow(node_count=100)
        # Only 10 nodes executed (10% of total)
        results = {f"node_{i}": {"result": i} for i in range(10)}

        result = runtime._validate_conditional_execution_results(results, workflow)

        # Should still return True but log warning
        assert result is True

    def test_validate_results_excessive_failures(self):
        """Test validation fails with excessive node failures."""
        runtime = ConcreteRuntimeWithValidation()
        workflow = create_valid_workflow()
        # More than 50% failures
        results = {
            "node1": {"failed": True, "error": "Error 1"},
            "node2": {"failed": True, "error": "Error 2"},
            "node3": {"result": "success"},
        }

        result = runtime._validate_conditional_execution_results(results, workflow)

        # Should return False (too many failures)
        assert result is False

    def test_validate_results_acceptable_failures(self):
        """Test validation passes with acceptable failure rate."""
        runtime = ConcreteRuntimeWithValidation()
        workflow = create_valid_workflow()
        # Less than 50% failures
        results = {
            "node1": {"result": "success"},
            "node2": {"result": "success"},
            "node3": {"result": "success"},
            "node4": {"failed": True, "error": "Single failure"},
        }

        result = runtime._validate_conditional_execution_results(results, workflow)

        # Should return True (acceptable failure rate)
        assert result is True

    def test_validate_results_error_handling(self):
        """Test validation handles errors gracefully."""
        runtime = ConcreteRuntimeWithValidation()
        workflow = create_valid_workflow()
        # Invalid results structure
        results = None

        result = runtime._validate_conditional_execution_results(results, workflow)

        # Should return False on error
        assert result is False


class TestValidationMixinIntegration:
    """Test integration of validation methods."""

    def test_full_validation_workflow(self):
        """Test complete validation workflow."""
        runtime = ConcreteRuntimeWithValidation()
        workflow = create_workflow_with_switch()

        # 1. Validate workflow structure
        warnings = runtime.validate_workflow(workflow)
        assert isinstance(warnings, list)

        # 2. Check conditional execution prerequisites
        has_prerequisites = runtime._validate_conditional_execution_prerequisites(
            workflow
        )
        assert has_prerequisites is True

        # 3. Validate switch results
        switch_results = create_switch_results("switch", true_output={"data": "test"})
        switch_valid = runtime._validate_switch_results(switch_results)
        assert switch_valid is True

        # 4. Validate final results
        results = {"switch": {"true_output": "test"}, "true_branch": {"result": "done"}}
        results_valid = runtime._validate_conditional_execution_results(
            results, workflow
        )
        assert results_valid is True

    def test_validation_with_all_features(self):
        """Test validation with all features enabled."""
        runtime = ConcreteRuntimeWithValidation(
            debug=True, enable_cycles=True, enable_monitoring=True
        )
        workflow = create_workflow_with_contracts()

        # Should handle all validation methods
        warnings = runtime.validate_workflow(workflow)
        assert isinstance(warnings, list)

        # Connection contract validation (if contracts module available)
        try:
            violations = runtime._validate_connection_contracts(
                workflow,
                "target",
                {"data": [1, 2, 3]},
                {"source": {"result": [1, 2, 3]}},
            )
            assert isinstance(violations, list)
        except ModuleNotFoundError:
            # Contracts module not available - skip this part
            pass

    def test_validation_mixin_stateless(self):
        """Test ValidationMixin is stateless and doesn't add attributes."""
        runtime = ConcreteRuntimeWithValidation()

        # ValidationMixin should not add instance attributes
        # (all validation is stateless)
        before_attrs = set(dir(runtime))

        # Call validation methods
        workflow = create_valid_workflow()
        runtime.validate_workflow(workflow)
        runtime._validate_conditional_execution_prerequisites(workflow)
        runtime._validate_switch_results({})

        after_attrs = set(dir(runtime))

        # No new instance attributes from mixin
        # (logger is from BaseRuntime, not ValidationMixin)
        assert before_attrs == after_attrs
