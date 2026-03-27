"""
Unit tests for connection mapping functionality in LocalRuntime.

Tests the connection mapping logic that handles data flow between nodes:
- Direct result mapping ("result" → entire node output)
- Dotted path navigation ("result.data" → nested dict value)
- AsyncPythonCodeNode special case (result prefix stripping)
- Multiple connections to same target
- None value handling
- Missing key handling

NO MOCKING - Tests verify actual connection mapping behavior with real runtime instances.

Note: AsyncLocalRuntime tests are in tests/tier2_integration/runtime/test_connection_mapping_async.py
because they spawn real threads that exhaust CI runner limits.
"""

import pytest

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestConnectionMappingLocalRuntime:
    """Test connection mapping in LocalRuntime."""

    def test_direct_result_mapping(self):
        """Test mapping 'result' to entire node output."""
        # Create workflow with simple connection using PythonCodeNode
        builder = WorkflowBuilder()

        # Source node returns a dict
        builder.add_node(
            "PythonCodeNode",
            "source",
            {"code": "result = {'data': 42, 'status': 'ok'}"},
        )

        # Target node receives the entire result dict as input_data
        builder.add_node(
            "PythonCodeNode",
            "target",
            {"code": "result = input_data"},
        )

        builder.connect("source", "target", mapping={"result": "input_data"})

        workflow = builder.build()

        # Execute workflow
        with LocalRuntime(connection_validation="off") as runtime:
            result, run_id = runtime.execute(workflow)

            # Verify result mapping
            assert "target" in result
            # Target should receive entire source output dict
            assert result["target"]["result"] == {"data": 42, "status": "ok"}

    def test_dotted_path_navigation(self):
        """Test mapping nested paths like 'result.data.value'."""
        # Create workflow with nested output
        builder = WorkflowBuilder()

        # Source node returns nested dict structure
        builder.add_node(
            "PythonCodeNode",
            "source",
            {
                "code": "result = {'data': {'value': 42, 'text': 'hello'}, 'metadata': {'count': 10}}"
            },
        )

        # Target node receives the nested value
        builder.add_node(
            "PythonCodeNode",
            "target",
            {"code": "result = input_data"},
        )

        builder.connect("source", "target", mapping={"result.data.value": "input_data"})

        workflow = builder.build()

        # Execute workflow
        with LocalRuntime(connection_validation="off") as runtime:
            result, run_id = runtime.execute(workflow)

            # Verify nested path navigation
            assert "target" in result
            # Target should receive 42 (from source.result.data.value)
            assert result["target"]["result"] == 42

    def test_async_python_code_node_special_case(self):
        """Test handling AsyncPythonCodeNode's result prefix stripping."""
        # Use actual AsyncPythonCodeNode which returns direct dict
        builder = WorkflowBuilder()

        # AsyncPythonCodeNode returns dict without 'result' wrapper
        builder.add_node(
            "AsyncPythonCodeNode",
            "source",
            {"code": "data = {'value': 99}\nstatus = 'ok'"},
        )

        # Target node receives the data
        builder.add_node(
            "PythonCodeNode",
            "target",
            {"code": "result = input_data"},
        )

        # Map "data" directly (AsyncPythonCodeNode doesn't wrap in "result")
        # This tests that we can access variables from AsyncPythonCodeNode
        builder.connect("source", "target", mapping={"data": "input_data"})

        workflow = builder.build()

        # Execute workflow
        with LocalRuntime(connection_validation="off") as runtime:
            result, run_id = runtime.execute(workflow)

            # Verify data was accessed correctly
            assert "target" in result
            # Should access "data" key from AsyncPythonCodeNode output
            assert result["target"]["result"] == {"value": 99}

    def test_multiple_connections(self):
        """Test multiple source nodes mapping to same target."""
        # Create workflow with multiple sources
        builder = WorkflowBuilder()

        # Source 1 returns simple dict
        builder.add_node(
            "PythonCodeNode",
            "source1",
            {"code": "result = {'data': 100}"},
        )

        # Source 2 returns nested dict
        builder.add_node(
            "PythonCodeNode",
            "source2",
            {"code": "result = {'data': {'text': 'hello'}}"},
        )

        # Target receives from both sources
        builder.add_node(
            "PythonCodeNode",
            "target",
            {"code": "result = {'value': value, 'text': text}"},
        )

        builder.connect("source1", "target", mapping={"result": "value"})
        builder.connect("source2", "target", mapping={"result.data.text": "text"})

        workflow = builder.build()

        # Execute workflow
        with LocalRuntime(connection_validation="off") as runtime:
            result, run_id = runtime.execute(workflow)

            # Verify both connections worked
            assert "target" in result
            # Target should have received data from both sources
            assert result["target"]["result"]["value"] == {"data": 100}
            assert result["target"]["result"]["text"] == "hello"

    def test_connection_mapping_with_none_values(self):
        """Test that None values are handled correctly in mapping."""
        # Create workflow where navigation returns None
        builder = WorkflowBuilder()

        # Source returns dict without the nested path
        builder.add_node(
            "PythonCodeNode",
            "source",
            {"code": "result = {'data': 42}"},
        )

        # Target just returns a value (doesn't need the missing input)
        builder.add_node(
            "PythonCodeNode",
            "target",
            {"code": "result = 'completed'"},
        )

        # Map a path that doesn't exist (runtime should handle gracefully)
        builder.connect(
            "source", "target", mapping={"result.nonexistent.path": "input_data"}
        )

        workflow = builder.build()

        # Execute workflow (should log warning but continue)
        with LocalRuntime(connection_validation="off") as runtime:
            result, run_id = runtime.execute(workflow)

            # Verify execution completes without error
            assert "target" in result
            # Target should complete successfully even without the mapped input
            assert result["target"]["result"] == "completed"

    def test_connection_mapping_with_missing_keys(self):
        """Test that missing keys are handled gracefully."""
        # Create workflow with missing key mapping
        builder = WorkflowBuilder()

        # Source returns dict
        builder.add_node(
            "PythonCodeNode",
            "source",
            {"code": "result = {'data': 42}"},
        )

        # Target just returns a value (doesn't need the missing input)
        builder.add_node(
            "PythonCodeNode",
            "target",
            {"code": "result = 'completed'"},
        )

        # Map a key that doesn't exist in source output
        builder.connect("source", "target", mapping={"missing_key": "input_data"})

        workflow = builder.build()

        # Execute workflow (should log warning but continue)
        with LocalRuntime(connection_validation="off") as runtime:
            result, run_id = runtime.execute(workflow)

            # Verify execution completes without error
            assert "target" in result


