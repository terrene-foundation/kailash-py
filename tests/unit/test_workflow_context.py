"""Unit tests for workflow context propagation functionality."""

import asyncio
import threading
import time
from typing import Any, Dict
from unittest.mock import MagicMock, Mock, patch

import pytest
from kailash.nodes.base import Node
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestWorkflowContext:
    """Test workflow context management in runtime."""

    def test_runtime_creates_workflow_context(self):
        """Test that LocalRuntime creates a workflow context for execution."""
        with LocalRuntime() as runtime:
            workflow = WorkflowBuilder().build()

            with patch.object(runtime, "_execute_workflow_async") as mock_execute:
                mock_execute.return_value = {"result": "success"}
                runtime.execute(workflow)

                # Verify workflow context was created
                assert hasattr(runtime, "_current_workflow_context")
                assert isinstance(runtime._current_workflow_context, dict)

    def test_workflow_context_passed_to_nodes(self):
        """Test that workflow context is passed to nodes during execution."""
        with LocalRuntime() as runtime:
            workflow = WorkflowBuilder()
            # Don't provide code parameter as PythonCodeNode doesn't declare workflow parameters
            # Create the node instance directly
            from kailash.nodes.code.python import PythonCodeNode

            python_node = PythonCodeNode(name="test", code="result = {'success': True}")
            workflow.add_node(python_node, "test", {})

            context_received = []

            def mock_execute(self, **kwargs):
                # Check if workflow context was set
                if hasattr(self, "_workflow_context"):
                    context_received.append(self._workflow_context)
                return {"result": "success"}

            with patch.object(PythonCodeNode, "execute", mock_execute):
                runtime.execute(
                    workflow.build(),
                    parameters={"workflow_context": {"test_key": "test_value"}},
                )

                # Verify node received workflow context
                assert len(context_received) == 1
                assert isinstance(context_received[0], dict)
                assert context_received[0].get("test_key") == "test_value"

    def test_workflow_context_isolated_between_executions(self):
        """Test that each workflow execution gets its own context."""
        with LocalRuntime() as runtime:
            workflow = WorkflowBuilder()
            # Create PythonCodeNode instance directly to avoid parameter validation issues
            from kailash.nodes.code.python import PythonCodeNode

            python_node = PythonCodeNode(name="test", code="result = {'success': True}")
            workflow.add_node(python_node, "test", {})

            contexts = []

            def mock_execute(self, **kwargs):
                if hasattr(self, "_workflow_context"):
                    contexts.append(id(self._workflow_context))
                return {"result": "success"}

            with patch.object(PythonCodeNode, "execute", mock_execute):
                # Execute workflow twice with different contexts
                runtime.execute(
                    workflow.build(), parameters={"workflow_context": {"run": 1}}
                )
                runtime.execute(
                    workflow.build(), parameters={"workflow_context": {"run": 2}}
                )

                # Verify different contexts
                assert len(contexts) == 2
            # Context objects should be different
            assert contexts[0] != contexts[1]

    def test_workflow_context_cleanup_after_execution(self):
        """Test that workflow context is cleaned up after execution."""
        with LocalRuntime() as runtime:
            workflow = WorkflowBuilder()
            # Create PythonCodeNode instance directly to avoid parameter validation issues
            from kailash.nodes.code.python import PythonCodeNode

            python_node = PythonCodeNode(name="test", code="result = {'success': True}")
            workflow.add_node(python_node, "test", {})

            runtime.execute(
                workflow.build(), parameters={"workflow_context": {"test": "cleanup"}}
            )

            # Verify context is cleaned up after execution
            assert hasattr(runtime, "_current_workflow_context")
            assert runtime._current_workflow_context is None


class TestNodeContextAccess:
    """Test node context access methods."""

    def test_node_get_workflow_context(self):
        """Test that nodes can retrieve values from workflow context."""
        from kailash.nodes.code.python import PythonCodeNode

        node = PythonCodeNode(name="test", code="result = {'success': True}")
        node._workflow_context = {"test_key": "test_value"}

        value = node.get_workflow_context("test_key")
        assert value == "test_value"

    def test_node_get_workflow_context_missing_key(self):
        """Test get_workflow_context returns None for missing keys."""
        from kailash.nodes.code.python import PythonCodeNode

        node = PythonCodeNode(name="test", code="result = {'success': True}")
        node._workflow_context = {}

        value = node.get_workflow_context("missing_key")
        assert value is None

    def test_node_set_workflow_context(self):
        """Test that nodes can set values in workflow context."""
        from kailash.nodes.code.python import PythonCodeNode

        node = PythonCodeNode(name="test", code="result = {'success': True}")
        node._workflow_context = {}

        node.set_workflow_context("new_key", "new_value")
        assert node._workflow_context["new_key"] == "new_value"

    def test_node_set_workflow_context_overwrites(self):
        """Test that set_workflow_context overwrites existing values."""
        from kailash.nodes.code.python import PythonCodeNode

        node = PythonCodeNode(name="test", code="result = {'success': True}")
        node._workflow_context = {}

        node.set_workflow_context("key", "old_value")
        node.set_workflow_context("key", "new_value")
        assert node._workflow_context["key"] == "new_value"

    def test_node_context_methods_without_workflow_context(self):
        """Test context methods handle missing _workflow_context gracefully."""
        from kailash.nodes.code.python import PythonCodeNode

        node = PythonCodeNode(name="test", code="result = {'success': True}")
        # Don't set _workflow_context

        # Try to use context methods without _workflow_context
        value = node.get_workflow_context("key")
        node.set_workflow_context("key", "value")

        assert value is None
        assert hasattr(node, "_workflow_context")
        assert node._workflow_context["key"] == "value"


class TestWorkflowContextThreadSafety:
    """Test thread safety of workflow context."""

    def test_concurrent_workflow_context_isolation(self):
        """Test that concurrent workflows have isolated contexts."""
        runtime1 = LocalRuntime()
        runtime2 = LocalRuntime()

        # Create workflows with different context values
        from kailash.nodes.code.python import PythonCodeNode

        workflow1 = WorkflowBuilder()
        python_node1 = PythonCodeNode(
            name="test",
            code="""
# Access workflow context
context_value = get_workflow_context('isolation_test', 'default')
result = {'context_value': context_value}
""",
        )
        workflow1.add_node(python_node1, "test", {})

        workflow2 = WorkflowBuilder()
        python_node2 = PythonCodeNode(
            name="test",
            code="""
# Access workflow context
context_value = get_workflow_context('isolation_test', 'default')
result = {'context_value': context_value}
""",
        )
        workflow2.add_node(python_node2, "test", {})

        # Execute workflows with different contexts
        with runtime1:
            results1, _ = runtime1.execute(
                workflow1.build(),
                parameters={"workflow_context": {"isolation_test": "runtime1_value"}},
            )

        with runtime2:
            results2, _ = runtime2.execute(
                workflow2.build(),
                parameters={"workflow_context": {"isolation_test": "runtime2_value"}},
            )

        # Verify contexts were isolated
        context1_value = results1.get("test", {}).get("result", {}).get("context_value")
        context2_value = results2.get("test", {}).get("result", {}).get("context_value")

        assert context1_value == "runtime1_value"
        assert context2_value == "runtime2_value"
        assert context1_value != context2_value


# DataFlow-specific transaction node tests moved to apps/kailash-dataflow/tests/
# This keeps the core SDK test suite free of app dependencies
