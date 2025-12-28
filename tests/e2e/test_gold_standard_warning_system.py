"""
End-to-End tests for the Gold Standard Enhanced Warning System.

Tests the complete warning system flow with real workflows and production scenarios.
"""

import os
import sys
import tempfile
import warnings
from pathlib import Path

import pytest
from kailash.nodes.base import Node, NodeParameter, NodeRegistry
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestGoldStandardWarningSystemE2E:
    """E2E tests for enhanced warning system with SDK vs custom node detection."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test environment."""
        self.workflow = WorkflowBuilder()
        self.runtime = LocalRuntime()

        # Capture warnings
        self.warnings = []

        def warning_handler(message, category, filename, lineno, file=None, line=None):
            self.warnings.append(str(message))

        self.original_showwarning = warnings.showwarning
        warnings.showwarning = warning_handler

        yield

        warnings.showwarning = self.original_showwarning

    def test_sdk_node_string_pattern_warning(self):
        """Test that SDK nodes used with class reference show helpful string pattern warning."""
        from kailash.nodes.data import CSVReaderNode

        # Use SDK node with class reference (incorrect pattern)
        self.workflow.add_node(CSVReaderNode, "reader", {"file_path": "data.csv"})

        # Should generate warning about string pattern
        assert len(self.warnings) == 1
        warning = self.warnings[0]
        assert "SDK node detected" in warning
        assert "PREFERRED: add_node('CSVReaderNode'" in warning
        assert (
            "String references work for all @register_node() decorated SDK nodes"
            in warning
        )

    def test_custom_node_class_reference_guidance(self):
        """Test that custom nodes with class reference get helpful guidance."""

        # Create custom node in test module
        class MyCustomProcessor(Node):
            def get_parameters(self):
                return {"data": NodeParameter(name="data", type=list, required=True)}

            def run(self, **kwargs):
                return {"result": kwargs.get("data", [])}

        # Use custom node with class reference (correct pattern)
        self.workflow.add_node(MyCustomProcessor, "processor", {"data": [1, 2, 3]})

        # Should generate guidance about custom nodes
        assert len(self.warnings) == 1
        warning = self.warnings[0]
        assert "Custom node detected" in warning
        assert "Class reference pattern confirmed for" in warning
        assert "MyCustomProcessor" in warning

    def test_production_workflow_mixed_nodes(self):
        """Test production workflow with both SDK and custom nodes."""

        # Create custom entry node
        class DataEntryNode(Node):
            def get_parameters(self):
                return {
                    "source": NodeParameter(name="source", type=str, required=True),
                    "config": NodeParameter(
                        name="config", type=dict, required=False, default={}
                    ),
                }

            def run(self, **kwargs):
                return {"result": {"data": [1, 2, 3, 4, 5]}}

        # Build mixed workflow
        self.workflow.add_node(DataEntryNode, "entry", {"source": "api"})

        # Try to use SDK node with class reference
        from kailash.nodes.ml import DataTransformerNode

        self.workflow.add_node(
            DataTransformerNode, "transformer", {"transformation_type": "normalize"}
        )

        # Connect nodes
        self.workflow.connect("entry", "transformer", mapping={"result.data": "data"})

        # Should get warnings for SDK node misuse
        sdk_warnings = [w for w in self.warnings if "SDK node detected" in w]
        assert len(sdk_warnings) == 1
        assert "DataTransformerNode" in sdk_warnings[0]

    def test_workflow_execution_with_warnings(self):
        """Test that workflows execute correctly despite warnings."""

        # Create custom node
        class ProcessorNode(Node):
            def get_parameters(self):
                return {"data": NodeParameter(name="data", type=list, required=True)}

            def run(self, **kwargs):
                data = kwargs.get("data", [])
                return {"result": [x * 2 for x in data]}

        # Build workflow with mixed patterns
        self.workflow.add_node(
            "PythonCodeNode",
            "generator",
            {"code": "result = {'numbers': list(range(5))}"},
        )
        self.workflow.add_node(ProcessorNode, "processor")
        self.workflow.connect(
            "generator", "processor", mapping={"result.numbers": "data"}
        )

        # Execute workflow
        results, run_id = self.runtime.execute(self.workflow.build())

        # Verify execution success
        assert results["processor"]["result"] == [0, 2, 4, 6, 8]

        # Verify only custom node warning was generated
        assert len(self.warnings) == 1
        assert "Custom node detected" in self.warnings[0]

    def test_dynamic_node_loading_scenario(self):
        """Test warning system with dynamically loaded nodes."""
        # Create temporary module with custom node
        with tempfile.TemporaryDirectory() as tmpdir:
            module_path = Path(tmpdir) / "dynamic_nodes.py"
            module_path.write_text(
                """
from kailash.nodes.base import Node, NodeParameter

class DynamicCustomNode(Node):
    def get_parameters(self):
        return {
            "input": NodeParameter(name="input", type=str, required=True)
        }

    def run(self, **kwargs):
        return {"result": f"Processed: {kwargs.get('input', '')}"}
"""
            )

            # Add to sys.path and import
            sys.path.insert(0, tmpdir)
            try:
                from dynamic_nodes import DynamicCustomNode

                # Use dynamic node
                self.workflow.add_node(DynamicCustomNode, "dynamic", {"input": "test"})

                # Should detect as custom node
                assert len(self.warnings) == 1
                assert "Custom node detected" in self.warnings[0]
                assert "DynamicCustomNode" in self.warnings[0]

            finally:
                sys.path.remove(tmpdir)

    def test_warning_suppression_for_string_patterns(self):
        """Test that correct string patterns don't generate warnings."""
        # Use SDK nodes with correct string pattern
        self.workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
        self.workflow.add_node(
            "DataTransformerNode", "transformer", {"transformation_type": "normalize"}
        )

        # Should not generate any warnings
        assert len(self.warnings) == 0

    def test_nested_workflow_warning_propagation(self):
        """Test warning system with nested workflows."""
        # Create inner workflow
        inner_workflow = WorkflowBuilder()

        # Use SDK node incorrectly in inner workflow
        from kailash.nodes.io import JSONReaderNode

        inner_workflow.add_node(JSONReaderNode, "reader", {"file_path": "data.json"})

        # Add inner workflow to outer
        self.workflow.add_node(
            "WorkflowNode", "nested", {"workflow": inner_workflow.build()}
        )

        # Warnings should propagate from inner workflow
        assert len(self.warnings) == 1
        assert "SDK node detected" in self.warnings[0]
        assert "JSONReaderNode" in self.warnings[0]

    def test_production_deployment_validation(self):
        """Test warning system catches common production deployment issues."""
        # Simulate production pattern mistakes

        # 1. Using internal SDK nodes incorrectly
        from kailash.nodes.security import AuthenticationNode

        self.workflow.add_node(AuthenticationNode, "auth", {"auth_type": "oauth2"})

        # 2. Custom node without proper parameters
        class BadCustomNode(Node):
            def get_parameters(self):
                return {}  # Empty parameters - will be caught by parameter validator

            def run(self, **kwargs):
                # This will fail in production due to no parameters
                return {"result": kwargs.get("data", "no data")}

        self.workflow.add_node(BadCustomNode, "bad_node")

        # Should have warnings for SDK node
        sdk_warnings = [w for w in self.warnings if "SDK node detected" in w]
        assert len(sdk_warnings) == 1
        assert "AuthenticationNode" in sdk_warnings[0]

    def test_warning_message_quality_and_helpfulness(self):
        """Test that warning messages provide actionable guidance."""
        from kailash.nodes.ml import ModelTrainerNode

        # Use SDK node incorrectly
        self.workflow.add_node(
            ModelTrainerNode, "trainer", {"model_type": "regression"}
        )

        # Verify warning quality
        assert len(self.warnings) == 1
        warning = self.warnings[0]

        # Check for helpful elements
        assert "SDK node detected" in warning
        assert "PREFERRED" in warning  # Suggestion
        assert "'ModelTrainerNode'" in warning  # Correct pattern
        assert "String references" in warning  # Explanation

    def test_batch_workflow_creation_warnings(self):
        """Test warning system performance with many nodes."""
        # Create workflow with many nodes
        for i in range(10):
            if i % 2 == 0:
                # Custom nodes (correct pattern)
                class BatchNode(Node):
                    def get_parameters(self):
                        return {"id": NodeParameter(name="id", type=int, required=True)}

                    def run(self, **kwargs):
                        return {"result": kwargs.get("id", 0)}

                self.workflow.add_node(BatchNode, f"custom_{i}", {"id": i})
            else:
                # SDK nodes (with warning)
                from kailash.nodes.utils import LoggerNode

                self.workflow.add_node(LoggerNode, f"logger_{i}", {"log_level": "INFO"})

        # Should have 5 SDK node warnings
        sdk_warnings = [w for w in self.warnings if "SDK node detected" in w]
        assert len(sdk_warnings) == 5

        # All warnings should be helpful
        for warning in sdk_warnings:
            assert "PREFERRED" in warning
            assert "LoggerNode" in warning


class TestWarningSystemIntegration:
    """Integration tests for warning system with other SDK features."""

    def test_warning_with_validation_framework(self):
        """Test warning system works alongside validation framework."""
        workflow = WorkflowBuilder()

        # Create node with validation issues
        class ProblematicNode(Node):
            def get_parameters(self):
                return {}  # Will trigger parameter validation warnings

            def run(self, **kwargs):
                return {"result": "no params"}

        # Capture all warnings and validation issues
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            workflow.add_node(ProblematicNode, "problem", {"data": "ignored"})

            # Build workflow to trigger validation
            built_workflow = workflow.build()

            # Should have both node detection and validation warnings
            warning_messages = [str(warning.message) for warning in w]

            # Check for custom node detection
            custom_warnings = [
                m for m in warning_messages if "Custom node detected" in m
            ]
            assert len(custom_warnings) >= 1

            # Validation will be checked separately by ParameterDeclarationValidator

    def test_warning_with_performance_monitoring(self):
        """Test warning system doesn't impact performance monitoring."""
        import time

        workflow = WorkflowBuilder()
        runtime = LocalRuntime()

        # Create a slow custom node
        class SlowNode(Node):
            def get_parameters(self):
                return {"delay": NodeParameter(name="delay", type=float, required=True)}

            def run(self, **kwargs):
                time.sleep(kwargs.get("delay", 0.1))
                return {"result": "done"}

        # Add nodes with warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            workflow.add_node(SlowNode, "slow1", {"delay": 0.1})
            workflow.add_node(SlowNode, "slow2", {"delay": 0.1})

            # Execute and measure
            start_time = time.time()
            results, run_id = runtime.execute(workflow.build())
            execution_time = time.time() - start_time

            # Warnings shouldn't significantly impact performance
            assert execution_time < 0.5  # Should be ~0.2s + overhead

            # Warnings should still be generated
            assert len(w) == 2
            assert all("Custom node detected" in str(warning.message) for warning in w)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
