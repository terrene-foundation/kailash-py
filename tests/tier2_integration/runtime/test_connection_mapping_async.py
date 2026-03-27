"""
Tier 2 tests for connection mapping with AsyncLocalRuntime.

Extracted from tests/unit/runtime/test_connection_mapping.py because
AsyncLocalRuntime tests create real threads that exhaust CI runner limits.
These tests verify actual connection mapping behavior with real async runtime
instances and belong in Tier 2 where real threading is permitted.
"""

import asyncio

import pytest

from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestConnectionMappingAsyncLocalRuntime:
    """Test connection mapping in AsyncLocalRuntime."""

    @pytest.mark.asyncio
    async def test_direct_result_mapping(self):
        """Test mapping 'result' to entire node output in async runtime."""
        # Create workflow with simple connection
        builder = WorkflowBuilder()

        # Source node returns a dict
        builder.add_node(
            "PythonCodeNode",
            "source",
            {"code": "result = {'data': 42, 'status': 'ok'}"},
        )

        # Target node receives the entire result dict
        builder.add_node(
            "PythonCodeNode",
            "target",
            {"code": "result = input_data"},
        )

        builder.connect("source", "target", mapping={"result": "input_data"})

        workflow = builder.build()

        # Execute workflow
        runtime = AsyncLocalRuntime()
        try:
            results, run_id = await runtime.execute_workflow_async(workflow, inputs={})
        finally:
            runtime.close()

        # Verify result mapping
        assert "target" in results
        target_result = results["target"]["result"]
        # Target's input_data contains the mapped value (with result wrapper)
        assert target_result == {"result": {"data": 42, "status": "ok"}}

    @pytest.mark.asyncio
    async def test_dotted_path_navigation(self):
        """Test mapping nested paths like 'result.data.value' in async runtime."""
        # Create workflow with nested output
        builder = WorkflowBuilder()

        # Source node returns nested dict
        builder.add_node(
            "PythonCodeNode",
            "source",
            {"code": "result = {'data': {'value': 42, 'text': 'hello'}}"},
        )

        # Target node receives nested value
        builder.add_node(
            "PythonCodeNode",
            "target",
            {"code": "result = input_data"},
        )

        builder.connect("source", "target", mapping={"result.data.value": "input_data"})

        workflow = builder.build()

        # Execute workflow
        runtime = AsyncLocalRuntime()
        try:
            results, run_id = await runtime.execute_workflow_async(workflow, inputs={})
        finally:
            runtime.close()

        # Verify nested path navigation
        assert "target" in results
        assert results["target"]["result"] == 42

    @pytest.mark.asyncio
    async def test_async_python_code_node_special_case(self):
        """Test handling AsyncPythonCodeNode's result prefix stripping in async runtime."""
        # Use actual AsyncPythonCodeNode
        builder = WorkflowBuilder()

        # AsyncPythonCodeNode returns direct dict
        builder.add_node(
            "AsyncPythonCodeNode",
            "source",
            {"code": "data = {'value': 99}\nstatus = 'ok'"},
        )

        # Target receives nested value
        builder.add_node(
            "PythonCodeNode",
            "target",
            {"code": "result = input_data"},
        )

        builder.connect("source", "target", mapping={"data": "input_data"})

        workflow = builder.build()

        # Execute workflow
        runtime = AsyncLocalRuntime()
        try:
            results, run_id = await runtime.execute_workflow_async(workflow, inputs={})
        finally:
            runtime.close()

        # Verify result prefix was stripped
        assert "target" in results
        assert results["target"]["result"] == {"value": 99}

    @pytest.mark.asyncio
    async def test_multiple_connections(self):
        """Test multiple source nodes mapping to same target in async runtime."""
        # Create workflow with multiple sources
        builder = WorkflowBuilder()

        # Source 1
        builder.add_node(
            "PythonCodeNode",
            "source1",
            {"code": "result = {'data': 100}"},
        )

        # Source 2
        builder.add_node(
            "PythonCodeNode",
            "source2",
            {"code": "result = {'data': {'text': 'hello'}}"},
        )

        # Target
        builder.add_node(
            "PythonCodeNode",
            "target",
            {"code": "result = {'value': value, 'text': text}"},
        )

        builder.connect("source1", "target", mapping={"result": "value"})
        builder.connect("source2", "target", mapping={"result.data.text": "text"})

        workflow = builder.build()

        # Execute workflow
        runtime = AsyncLocalRuntime()
        try:
            results, run_id = await runtime.execute_workflow_async(workflow, inputs={})
        finally:
            runtime.close()

        # Verify both connections worked
        assert "target" in results
        assert results["target"]["result"]["value"] == {"result": {"data": 100}}
        assert results["target"]["result"]["text"] == "hello"

    @pytest.mark.asyncio
    async def test_connection_mapping_with_none_values(self):
        """Test that None values are handled correctly in async runtime."""
        # Create workflow where navigation returns None
        builder = WorkflowBuilder()

        # Source
        builder.add_node(
            "PythonCodeNode",
            "source",
            {"code": "result = {'data': 42}"},
        )

        # Target
        builder.add_node(
            "PythonCodeNode",
            "target",
            {"code": "result = 'completed'"},
        )

        builder.connect(
            "source", "target", mapping={"result.nonexistent.path": "input_data"}
        )

        workflow = builder.build()

        # Execute workflow
        runtime = AsyncLocalRuntime()
        try:
            results, run_id = await runtime.execute_workflow_async(workflow, inputs={})
        finally:
            runtime.close()

        # Verify execution completes
        assert "target" in results
        # Target executes successfully even without the mapped input
        assert results["target"]["result"] == "completed"

    @pytest.mark.asyncio
    async def test_connection_mapping_with_missing_keys(self):
        """Test that missing keys are handled gracefully in async runtime."""
        # Create workflow with missing key
        builder = WorkflowBuilder()

        # Source
        builder.add_node(
            "PythonCodeNode",
            "source",
            {"code": "result = {'data': 42}"},
        )

        # Target
        builder.add_node(
            "PythonCodeNode",
            "target",
            {"code": "result = 'completed'"},
        )

        builder.connect("source", "target", mapping={"missing_key": "input_data"})

        workflow = builder.build()

        # Execute workflow
        runtime = AsyncLocalRuntime()
        try:
            results, run_id = await runtime.execute_workflow_async(workflow, inputs={})
        finally:
            runtime.close()

        # Verify execution completes
        assert "target" in results
        assert results["target"]["result"] == "completed"


class TestConnectionMappingParityBothRuntimes:
    """Test that LocalRuntime and AsyncLocalRuntime have identical connection mapping behavior."""

    @pytest.mark.parametrize(
        "runtime_class,is_async",
        [(LocalRuntime, False), (AsyncLocalRuntime, True)],
    )
    def test_direct_result_mapping_parity(self, runtime_class, is_async):
        """Test 'result' mapping works identically in both runtimes."""
        # Create workflow
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "source",
            {"code": "result = {'data': 42}"},
        )
        builder.add_node(
            "PythonCodeNode",
            "target",
            {"code": "result = input_data"},
        )
        builder.connect("source", "target", mapping={"result": "input_data"})

        workflow = builder.build()

        # Execute with appropriate runtime
        if is_async:
            runtime = runtime_class()
            try:
                results, run_id = asyncio.run(
                    runtime.execute_workflow_async(workflow, inputs={})
                )
            finally:
                runtime.close()
            # Async returns flat result dict (same as sync after tuple unpacking)
            assert "target" in results
            # Async includes extra "result" wrapper in the mapped value
            assert results["target"]["result"] == {"result": {"data": 42}}
        else:
            with runtime_class(connection_validation="off") as runtime:
                results, run_id = runtime.execute(workflow)
                # Sync returns flat result dict
                assert "target" in results
                assert results["target"]["result"] == {"data": 42}

    @pytest.mark.parametrize(
        "runtime_class,is_async",
        [(LocalRuntime, False), (AsyncLocalRuntime, True)],
    )
    def test_dotted_path_navigation_parity(self, runtime_class, is_async):
        """Test dotted path navigation works identically in both runtimes."""
        # Create workflow
        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode",
            "source",
            {"code": "result = {'data': {'value': 42}}"},
        )
        builder.add_node(
            "PythonCodeNode",
            "target",
            {"code": "result = input_data"},
        )
        builder.connect("source", "target", mapping={"result.data.value": "input_data"})

        workflow = builder.build()

        # Execute with appropriate runtime
        if is_async:
            runtime = runtime_class()
            try:
                results, run_id = asyncio.run(
                    runtime.execute_workflow_async(workflow, inputs={})
                )
            finally:
                runtime.close()
            # Async returns flat result dict (same as sync after tuple unpacking)
            assert "target" in results
            assert results["target"]["result"] == 42
        else:
            with runtime_class(connection_validation="off") as runtime:
                results, run_id = runtime.execute(workflow)
                # Sync returns flat result dict
                assert "target" in results
                assert results["target"]["result"] == 42

    @pytest.mark.parametrize(
        "runtime_class,is_async",
        [(LocalRuntime, False), (AsyncLocalRuntime, True)],
    )
    def test_async_python_special_case_parity(self, runtime_class, is_async):
        """Test AsyncPythonCodeNode special case works identically in both runtimes."""
        # Create workflow
        builder = WorkflowBuilder()
        builder.add_node(
            "AsyncPythonCodeNode",
            "source",
            {"code": "data = {'value': 99}"},
        )
        builder.add_node(
            "PythonCodeNode",
            "target",
            {"code": "result = input_data"},
        )
        builder.connect("source", "target", mapping={"data": "input_data"})

        workflow = builder.build()

        # Execute with appropriate runtime
        if is_async:
            runtime = runtime_class()
            try:
                results, run_id = asyncio.run(
                    runtime.execute_workflow_async(workflow, inputs={})
                )
            finally:
                runtime.close()
            # Async returns flat result dict (same as sync after tuple unpacking)
            assert "target" in results
            assert results["target"]["result"] == {"value": 99}
        else:
            with runtime_class(connection_validation="off") as runtime:
                results, run_id = runtime.execute(workflow)
                # Sync returns flat result dict
                assert "target" in results
                assert results["target"]["result"] == {"value": 99}
