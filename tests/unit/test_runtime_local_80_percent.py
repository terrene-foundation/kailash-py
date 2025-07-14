"""Comprehensive tests to boost runtime.local coverage from 12% to >80%."""

import asyncio
import logging
import threading
from datetime import UTC, datetime
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import networkx as nx
import pytest
from pydantic import BaseModel


class TestUserContext(BaseModel):
    """Test user context model."""

    user_id: str = "test_user"
    roles: list = ["analyst"]


class TestLocalRuntimeCore:
    """Test core LocalRuntime functionality."""

    def test_local_runtime_initialization(self):
        """Test LocalRuntime initialization with various configurations."""
        try:
            from kailash.runtime.local import LocalRuntime

            # Test default initialization
            runtime = LocalRuntime()
            assert runtime.debug is False
            assert runtime.enable_cycles is True
            assert runtime.enable_async is True
            assert runtime.max_concurrency == 10
            assert runtime.user_context is None
            assert runtime.enable_monitoring is True
            assert runtime.enable_security is False
            assert runtime.enable_audit is False
            assert runtime.resource_limits == {}

            # Test custom initialization
            user_context = TestUserContext()
            resource_limits = {"memory_mb": 1024, "cpu_cores": 4}

            runtime = LocalRuntime(
                debug=True,
                enable_cycles=False,
                enable_async=False,
                max_concurrency=5,
                user_context=user_context,
                enable_monitoring=False,
                enable_security=True,
                enable_audit=True,
                resource_limits=resource_limits,
            )

            assert runtime.debug is True
            assert runtime.enable_cycles is False
            assert runtime.enable_async is False
            assert runtime.max_concurrency == 5
            assert runtime.user_context == user_context
            assert runtime.enable_monitoring is False
            assert runtime.enable_security is True
            assert runtime.enable_audit is True
            assert runtime.resource_limits == resource_limits

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_execution_context_setup(self):
        """Test execution context configuration."""
        try:
            from kailash.runtime.local import LocalRuntime

            user_context = TestUserContext()
            runtime = LocalRuntime(
                enable_security=True,
                enable_monitoring=True,
                enable_audit=True,
                user_context=user_context,
            )

            context = runtime._execution_context
            assert context["security_enabled"] is True
            assert context["monitoring_enabled"] is True
            assert context["audit_enabled"] is True
            assert context["async_enabled"] is True
            assert context["user_context"] == user_context

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_cyclic_executor_initialization(self):
        """Test cyclic executor initialization."""
        try:
            from kailash.runtime.local import LocalRuntime

            # With cycles enabled
            runtime = LocalRuntime(enable_cycles=True)
            assert hasattr(runtime, "cyclic_executor")

            # With cycles disabled
            runtime = LocalRuntime(enable_cycles=False)
            assert not hasattr(runtime, "cyclic_executor")

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_logging_configuration(self):
        """Test logging configuration based on debug setting."""
        try:
            from kailash.runtime.local import LocalRuntime

            # Test debug mode
            with patch("kailash.runtime.local.logger") as mock_logger:
                runtime = LocalRuntime(debug=True)
                mock_logger.setLevel.assert_called_with(logging.DEBUG)

            # Test non-debug mode
            with patch("kailash.runtime.local.logger") as mock_logger:
                runtime = LocalRuntime(debug=False)
                mock_logger.setLevel.assert_called_with(logging.INFO)

        except ImportError:
            pytest.skip("LocalRuntime not available")


class TestLocalRuntimeExecution:
    """Test LocalRuntime execution methods."""

    def test_execute_with_existing_event_loop(self):
        """Test execute method when called from within an existing event loop."""
        try:
            from kailash.runtime.local import LocalRuntime

            runtime = LocalRuntime()
            mock_workflow = Mock()

            # Mock the sync execution method
            with patch.object(runtime, "_execute_sync") as mock_sync:
                mock_sync.return_value = ({"result": "success"}, "run_123")

                # Mock get_running_loop to simulate existing event loop
                with patch("asyncio.get_running_loop") as mock_get_loop:
                    mock_get_loop.return_value = Mock()  # Simulate active loop

                    results, run_id = runtime.execute(mock_workflow)

                    assert results == {"result": "success"}
                    assert run_id == "run_123"
                    mock_sync.assert_called_once()

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_execute_without_event_loop(self):
        """Test execute method when no event loop is running."""
        try:
            from kailash.runtime.local import LocalRuntime

            runtime = LocalRuntime()
            mock_workflow = Mock()

            # Mock the async execution method
            with patch.object(runtime, "_execute_async") as mock_async:
                mock_async.return_value = ({"result": "success"}, "run_123")

                # Mock get_running_loop to raise RuntimeError (no loop)
                with patch("asyncio.get_running_loop") as mock_get_loop:
                    mock_get_loop.side_effect = RuntimeError("No event loop")

                    with patch("asyncio.run") as mock_run:
                        mock_run.return_value = ({"result": "success"}, "run_123")

                        results, run_id = runtime.execute(mock_workflow)

                        assert results == {"result": "success"}
                        assert run_id == "run_123"
                        mock_run.assert_called_once()

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_execute_async_method(self):
        """Test execute_async method."""
        try:
            from kailash.runtime.local import LocalRuntime

            runtime = LocalRuntime()
            mock_workflow = Mock()

            # Mock the internal async execution method
            with patch.object(runtime, "_execute_async") as mock_async:
                mock_async.return_value = ({"result": "success"}, "run_123")

                # Run the async method
                async def test_async():
                    results, run_id = await runtime.execute_async(mock_workflow)
                    assert results == {"result": "success"}
                    assert run_id == "run_123"
                    mock_async.assert_called_once_with(
                        workflow=mock_workflow, task_manager=None, parameters=None
                    )

                asyncio.run(test_async())

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_execute_sync_threading(self):
        """Test _execute_sync method with threading."""
        try:
            from kailash.runtime.local import LocalRuntime

            runtime = LocalRuntime()
            mock_workflow = Mock()

            # Mock the async execution method
            with patch.object(runtime, "_execute_async") as mock_async:
                mock_async.return_value = ({"result": "success"}, "run_123")

                results, run_id = runtime._execute_sync(mock_workflow)

                assert results == {"result": "success"}
                assert run_id == "run_123"
                mock_async.assert_called_once()

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_execute_sync_exception_handling(self):
        """Test _execute_sync exception handling."""
        try:
            from kailash.runtime.local import LocalRuntime

            runtime = LocalRuntime()
            mock_workflow = Mock()

            # Mock the async execution method to raise an exception
            with patch.object(runtime, "_execute_async") as mock_async:
                mock_async.side_effect = Exception("Test error")

                with pytest.raises(Exception, match="Test error"):
                    runtime._execute_sync(mock_workflow)

        except ImportError:
            pytest.skip("LocalRuntime not available")


class TestLocalRuntimeAsyncExecution:
    """Test LocalRuntime async execution implementation."""

    def test_execute_async_no_workflow(self):
        """Test async execution with no workflow."""
        try:
            from kailash.runtime.local import LocalRuntime
            from kailash.sdk_exceptions import RuntimeExecutionError

            runtime = LocalRuntime()

            async def test_async():
                with pytest.raises(RuntimeExecutionError, match="No workflow provided"):
                    await runtime._execute_async(None)

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_execute_async_with_security_check(self):
        """Test async execution with security checks enabled."""
        try:
            from kailash.runtime.local import LocalRuntime

            user_context = TestUserContext()
            runtime = LocalRuntime(enable_security=True, user_context=user_context)

            mock_workflow = Mock()
            mock_workflow.workflow_id = "test_workflow"
            mock_workflow.name = "Test Workflow"
            mock_workflow.has_cycles.return_value = False
            mock_workflow.validate.return_value = None

            with patch.object(runtime, "_check_workflow_access") as mock_check:
                with patch.object(
                    runtime, "_process_workflow_parameters"
                ) as mock_process:
                    mock_process.return_value = {}
                    with patch.object(
                        runtime, "_execute_workflow_async"
                    ) as mock_execute:
                        mock_execute.return_value = {"result": "success"}

                        async def test_async():
                            results, run_id = await runtime._execute_async(
                                mock_workflow
                            )
                            mock_check.assert_called_once_with(mock_workflow)
                            assert results == {"result": "success"}

                        asyncio.run(test_async())

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_execute_async_with_audit_logging(self):
        """Test async execution with audit logging enabled."""
        try:
            from kailash.runtime.local import LocalRuntime

            runtime = LocalRuntime(enable_audit=True)

            mock_workflow = Mock()
            mock_workflow.workflow_id = "test_workflow"
            mock_workflow.name = "Test Workflow"
            mock_workflow.has_cycles.return_value = False
            mock_workflow.validate.return_value = None

            with patch.object(runtime, "_log_audit_event_async") as mock_audit:
                with patch.object(
                    runtime, "_process_workflow_parameters"
                ) as mock_process:
                    mock_process.return_value = {}
                    with patch.object(
                        runtime, "_execute_workflow_async"
                    ) as mock_execute:
                        mock_execute.return_value = {"result": "success"}

                        async def test_async():
                            results, run_id = await runtime._execute_async(
                                mock_workflow
                            )

                            # Should log start and completion events
                            assert mock_audit.call_count >= 2

                            # Check start event
                            start_call = mock_audit.call_args_list[0]
                            assert start_call[0][0] == "workflow_execution_start"

                            # Check completion event
                            completion_call = mock_audit.call_args_list[1]
                            assert (
                                completion_call[0][0] == "workflow_execution_completed"
                            )

                        asyncio.run(test_async())

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_execute_async_with_task_manager(self):
        """Test async execution with task manager."""
        try:
            from kailash.runtime.local import LocalRuntime

            runtime = LocalRuntime(enable_monitoring=True)

            mock_workflow = Mock()
            mock_workflow.workflow_id = "test_workflow"
            mock_workflow.name = "Test Workflow"
            mock_workflow.has_cycles.return_value = False
            mock_workflow.validate.return_value = None

            mock_task_manager = Mock()
            mock_task_manager.create_run.return_value = "run_123"

            with patch.object(runtime, "_process_workflow_parameters") as mock_process:
                mock_process.return_value = {}
                with patch.object(runtime, "_execute_workflow_async") as mock_execute:
                    mock_execute.return_value = {"result": "success"}

                    async def test_async():
                        results, run_id = await runtime._execute_async(
                            mock_workflow, task_manager=mock_task_manager
                        )

                        mock_task_manager.create_run.assert_called_once()
                        mock_task_manager.update_run_status.assert_called_with(
                            "run_123", "completed"
                        )
                        assert run_id == "run_123"

                    asyncio.run(test_async())

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_execute_async_cyclic_workflow(self):
        """Test async execution with cyclic workflow."""
        try:
            from kailash.runtime.local import LocalRuntime

            runtime = LocalRuntime(enable_cycles=True)

            mock_workflow = Mock()
            mock_workflow.workflow_id = "test_workflow"
            mock_workflow.name = "Test Workflow"
            mock_workflow.has_cycles.return_value = True
            mock_workflow.validate.return_value = None

            # Mock cyclic executor with proper async handling
            mock_cyclic_executor = Mock()
            mock_cyclic_executor.execute.return_value = (
                {"result": "cyclic"},
                "run_456",
            )
            runtime.cyclic_executor = mock_cyclic_executor

            with patch.object(runtime, "_process_workflow_parameters") as mock_process:
                mock_process.return_value = {}

                async def test_async():
                    results, run_id = await runtime._execute_async(mock_workflow)

                    mock_cyclic_executor.execute.assert_called_once()
                    assert results == {"result": "cyclic"}
                    assert run_id == "run_456"

                asyncio.run(test_async())

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_execute_async_error_handling(self):
        """Test async execution error handling and audit logging."""
        try:
            from kailash.runtime.local import LocalRuntime
            from kailash.sdk_exceptions import (
                RuntimeExecutionError,
                WorkflowValidationError,
            )

            runtime = LocalRuntime(enable_audit=True)

            mock_workflow = Mock()
            mock_workflow.workflow_id = "test_workflow"
            mock_workflow.validate.side_effect = WorkflowValidationError(
                "Validation failed"
            )

            with patch.object(runtime, "_log_audit_event_async") as mock_audit:

                async def test_async():
                    with pytest.raises(WorkflowValidationError):
                        await runtime._execute_async(mock_workflow)

                    # Should log validation failure
                    mock_audit.assert_called_with(
                        "workflow_validation_failed",
                        {"workflow_id": "test_workflow", "error": "Validation failed"},
                    )

                asyncio.run(test_async())

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_execute_async_permission_error(self):
        """Test async execution with permission error."""
        try:
            from kailash.runtime.local import LocalRuntime

            user_context = TestUserContext()
            runtime = LocalRuntime(
                enable_security=True, enable_audit=True, user_context=user_context
            )

            mock_workflow = Mock()
            mock_workflow.workflow_id = "test_workflow"

            with patch.object(runtime, "_check_workflow_access") as mock_check:
                mock_check.side_effect = PermissionError("Access denied")

                with patch.object(runtime, "_log_audit_event_async") as mock_audit:

                    async def test_async():
                        with pytest.raises(PermissionError):
                            await runtime._execute_async(mock_workflow)

                        # Should log access denial
                        mock_audit.assert_called_with(
                            "workflow_access_denied",
                            {
                                "workflow_id": "test_workflow",
                                "user_context": runtime._serialize_user_context(),
                                "error": "Access denied",
                            },
                        )

                    asyncio.run(test_async())

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_execute_async_general_exception(self):
        """Test async execution with general exception."""
        try:
            from kailash.runtime.local import LocalRuntime
            from kailash.sdk_exceptions import RuntimeExecutionError

            runtime = LocalRuntime(enable_audit=True)

            mock_workflow = Mock()
            mock_workflow.workflow_id = "test_workflow"
            mock_workflow.validate.side_effect = Exception("General error")

            with patch.object(runtime, "_log_audit_event_async") as mock_audit:

                async def test_async():
                    with pytest.raises(
                        RuntimeExecutionError,
                        match="Unified enterprise workflow execution failed",
                    ):
                        await runtime._execute_async(mock_workflow)

                    # Should log execution failure
                    mock_audit.assert_called_with(
                        "workflow_execution_failed",
                        {"workflow_id": "test_workflow", "error": "General error"},
                    )

                asyncio.run(test_async())

        except ImportError:
            pytest.skip("LocalRuntime not available")


class TestWorkflowExecution:
    """Test workflow execution methods."""

    def test_execute_workflow_async_basic(self):
        """Test basic workflow execution."""
        try:
            from kailash.runtime.local import LocalRuntime

            runtime = LocalRuntime()

            # Create mock workflow with graph
            mock_workflow = Mock()
            mock_workflow.graph = nx.DiGraph()
            mock_workflow.graph.add_node("node1")
            mock_workflow._node_instances = {"node1": Mock()}
            mock_workflow._node_instances["node1"].execute.return_value = {
                "output": "test"
            }
            mock_workflow._node_instances["node1"].config = {}

            # Mock topological sort
            with patch("networkx.topological_sort") as mock_topo:
                mock_topo.return_value = ["node1"]

                with patch.object(runtime, "_prepare_node_inputs") as mock_inputs:
                    mock_inputs.return_value = {"input": "data"}

                    with patch(
                        "kailash.utils.data_validation.DataTypeValidator"
                    ) as mock_validator:
                        mock_validator.validate_node_input.return_value = {
                            "input": "data"
                        }

                        with patch(
                            "kailash.tracking.metrics_collector.MetricsCollector"
                        ) as mock_collector:
                            mock_context = Mock()
                            mock_metrics = Mock()
                            mock_metrics.duration = 0.1
                            mock_metrics.to_task_metrics.return_value = {}
                            mock_context.result.return_value = mock_metrics
                            mock_collector.return_value.collect.return_value.__enter__.return_value = (
                                mock_context
                            )
                            mock_collector.return_value.collect.return_value.__exit__.return_value = (
                                None
                            )

                            async def test_async():
                                results = await runtime._execute_workflow_async(
                                    workflow=mock_workflow,
                                    task_manager=None,
                                    run_id=None,
                                    parameters={},
                                )

                                assert results == {"node1": {"output": "test"}}
                                mock_workflow._node_instances[
                                    "node1"
                                ].execute.assert_called_once()

                            asyncio.run(test_async())

        except ImportError:
            pytest.skip("LocalRuntime or dependencies not available")

    def test_execute_workflow_async_with_task_manager(self):
        """Test workflow execution with task manager."""
        try:
            from kailash.runtime.local import LocalRuntime

            runtime = LocalRuntime()

            # Create mock workflow
            mock_workflow = Mock()
            mock_workflow.graph = nx.DiGraph()
            mock_workflow.graph.add_node("node1")
            mock_workflow._node_instances = {"node1": Mock()}
            mock_workflow._node_instances["node1"].execute.return_value = {
                "output": "test"
            }
            mock_workflow._node_instances["node1"].__class__.__name__ = "TestNode"

            # Create mock task manager
            mock_task_manager = Mock()
            mock_task = Mock()
            mock_task.task_id = "task_123"
            mock_task_manager.create_task.return_value = mock_task

            with patch("networkx.topological_sort") as mock_topo:
                mock_topo.return_value = ["node1"]

                with patch.object(runtime, "_prepare_node_inputs") as mock_inputs:
                    mock_inputs.return_value = {"input": "data"}

                    with patch(
                        "kailash.utils.data_validation.DataTypeValidator"
                    ) as mock_validator:
                        mock_validator.validate_node_input.return_value = {
                            "input": "data"
                        }

                        with patch(
                            "kailash.tracking.metrics_collector.MetricsCollector"
                        ) as mock_collector:
                            mock_context = Mock()
                            mock_metrics = Mock()
                            mock_metrics.duration = 0.1
                            mock_metrics.to_task_metrics.return_value = {
                                "duration": 0.1
                            }
                            mock_context.result.return_value = mock_metrics
                            mock_collector.return_value.collect.return_value.__enter__.return_value = (
                                mock_context
                            )
                            mock_collector.return_value.collect.return_value.__exit__.return_value = (
                                None
                            )

                            async def test_async():
                                results = await runtime._execute_workflow_async(
                                    workflow=mock_workflow,
                                    task_manager=mock_task_manager,
                                    run_id="run_123",
                                    parameters={},
                                )

                                # Task should be created and updated
                                mock_task_manager.create_task.assert_called_once()
                                assert (
                                    mock_task_manager.update_task_status.call_count >= 2
                                )  # Running + Completed

                            asyncio.run(test_async())

        except ImportError:
            pytest.skip("LocalRuntime or dependencies not available")

    def test_execute_workflow_async_node_failure(self):
        """Test workflow execution with node failure."""
        try:
            from kailash.runtime.local import LocalRuntime
            from kailash.sdk_exceptions import WorkflowExecutionError

            runtime = LocalRuntime()

            # Create mock workflow
            mock_workflow = Mock()
            mock_workflow.graph = nx.DiGraph()
            mock_workflow.graph.add_node("node1")
            mock_workflow.graph.add_node("node2")
            mock_workflow.graph.add_edge("node1", "node2")
            mock_workflow._node_instances = {"node1": Mock(), "node2": Mock()}
            # Make node1 fail
            mock_workflow._node_instances["node1"].execute.side_effect = Exception(
                "Node failed"
            )

            with patch("networkx.topological_sort") as mock_topo:
                mock_topo.return_value = ["node1", "node2"]

                with patch.object(runtime, "_prepare_node_inputs") as mock_inputs:
                    mock_inputs.return_value = {"input": "data"}

                    with patch(
                        "kailash.utils.data_validation.DataTypeValidator"
                    ) as mock_validator:
                        mock_validator.validate_node_input.return_value = {
                            "input": "data"
                        }

                        with patch.object(
                            runtime, "_should_stop_on_error"
                        ) as mock_stop:
                            mock_stop.return_value = True

                            with patch(
                                "kailash.tracking.metrics_collector.MetricsCollector"
                            ) as mock_collector:
                                mock_context = Mock()
                                mock_collector.return_value.collect.return_value.__enter__.return_value = (
                                    mock_context
                                )
                                mock_collector.return_value.collect.return_value.__exit__.return_value = (
                                    None
                                )

                                async def test_async():
                                    with pytest.raises(
                                        WorkflowExecutionError,
                                        match="Node 'node1' failed",
                                    ):
                                        await runtime._execute_workflow_async(
                                            workflow=mock_workflow,
                                            task_manager=None,
                                            run_id=None,
                                            parameters={},
                                        )

                                asyncio.run(test_async())

        except ImportError:
            pytest.skip("LocalRuntime or dependencies not available")

    def test_execute_workflow_async_continue_on_error(self):
        """Test workflow execution continuing on non-critical errors."""
        try:
            from kailash.runtime.local import LocalRuntime

            runtime = LocalRuntime()

            # Create mock workflow
            mock_workflow = Mock()
            mock_workflow.graph = nx.DiGraph()
            mock_workflow.graph.add_node("node1")
            mock_workflow.graph.add_node("node2")
            mock_workflow._node_instances = {"node1": Mock(), "node2": Mock()}
            # Set up configs
            mock_workflow._node_instances["node1"].config = {}
            mock_workflow._node_instances["node2"].config = {}
            # Make node1 fail but continue execution
            mock_workflow._node_instances["node1"].execute.side_effect = Exception(
                "Node failed"
            )
            mock_workflow._node_instances["node2"].execute.return_value = {
                "output": "success"
            }

            with patch("networkx.topological_sort") as mock_topo:
                mock_topo.return_value = ["node1", "node2"]

                with patch.object(runtime, "_prepare_node_inputs") as mock_inputs:
                    mock_inputs.return_value = {"input": "data"}

                    with patch(
                        "kailash.utils.data_validation.DataTypeValidator"
                    ) as mock_validator:
                        mock_validator.validate_node_input.return_value = {
                            "input": "data"
                        }

                        with patch.object(
                            runtime, "_should_stop_on_error"
                        ) as mock_stop:
                            mock_stop.return_value = False  # Continue on error

                            with patch(
                                "kailash.tracking.metrics_collector.MetricsCollector"
                            ) as mock_collector:
                                mock_context = Mock()
                                mock_metrics = Mock()
                                mock_metrics.duration = 0.1
                                mock_metrics.to_task_metrics.return_value = {}
                                mock_context.result.return_value = mock_metrics
                                mock_collector.return_value.collect.return_value.__enter__.return_value = (
                                    mock_context
                                )
                                mock_collector.return_value.collect.return_value.__exit__.return_value = (
                                    None
                                )

                                async def test_async():
                                    results = await runtime._execute_workflow_async(
                                        workflow=mock_workflow,
                                        task_manager=None,
                                        run_id=None,
                                        parameters={},
                                    )

                                    # Should have both results - one error, one success
                                    assert "node1" in results
                                    assert results["node1"]["failed"] is True
                                    assert "node2" in results
                                    assert results["node2"] == {"output": "success"}

                                asyncio.run(test_async())

        except ImportError:
            pytest.skip("LocalRuntime or dependencies not available")

    def test_execute_workflow_async_network_error(self):
        """Test workflow execution with network topology error."""
        try:
            from kailash.runtime.local import LocalRuntime
            from kailash.sdk_exceptions import WorkflowExecutionError

            runtime = LocalRuntime()

            mock_workflow = Mock()
            mock_workflow.graph = nx.DiGraph()

            with patch("networkx.topological_sort") as mock_topo:
                mock_topo.side_effect = nx.NetworkXError("Cycle detected")

                async def test_async():
                    with pytest.raises(
                        WorkflowExecutionError,
                        match="Failed to determine execution order",
                    ):
                        await runtime._execute_workflow_async(
                            workflow=mock_workflow,
                            task_manager=None,
                            run_id=None,
                            parameters={},
                        )

                asyncio.run(test_async())

        except ImportError:
            pytest.skip("LocalRuntime or dependencies not available")

    def test_execute_workflow_async_missing_node_instance(self):
        """Test workflow execution with missing node instance."""
        try:
            from kailash.runtime.local import LocalRuntime
            from kailash.sdk_exceptions import WorkflowExecutionError

            runtime = LocalRuntime()

            mock_workflow = Mock()
            mock_workflow.graph = nx.DiGraph()
            mock_workflow.graph.add_node("node1")
            mock_workflow._node_instances = {}  # Missing node instance

            with patch("networkx.topological_sort") as mock_topo:
                mock_topo.return_value = ["node1"]

                async def test_async():
                    with pytest.raises(
                        WorkflowExecutionError, match="Node instance 'node1' not found"
                    ):
                        await runtime._execute_workflow_async(
                            workflow=mock_workflow,
                            task_manager=None,
                            run_id=None,
                            parameters={},
                        )

                asyncio.run(test_async())

        except ImportError:
            pytest.skip("LocalRuntime or dependencies not available")


class TestNodeInputPreparation:
    """Test node input preparation methods."""

    def test_prepare_node_inputs_basic(self):
        """Test basic node input preparation."""
        try:
            from kailash.runtime.local import LocalRuntime

            runtime = LocalRuntime()

            # Create mock workflow and node
            mock_workflow = Mock()
            mock_workflow.graph = nx.DiGraph()
            mock_workflow.graph.add_node("node1")

            mock_node = Mock()
            node_outputs = {}
            parameters = {"param1": "value1"}

            inputs = runtime._prepare_node_inputs(
                workflow=mock_workflow,
                node_id="node1",
                node_instance=mock_node,
                node_outputs=node_outputs,
                parameters=parameters,
            )

            assert inputs == parameters

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_prepare_node_inputs_with_connections(self):
        """Test node input preparation with connections."""
        try:
            from kailash.runtime.local import LocalRuntime

            runtime = LocalRuntime()

            # Create mock workflow with connections
            mock_workflow = Mock()
            mock_workflow.graph = nx.DiGraph()
            mock_workflow.graph.add_node("node1")
            mock_workflow.graph.add_node("node2")
            mock_workflow.graph.add_edge(
                "node1", "node2", mapping={"output1": "input1"}
            )

            # Mock in_edges method
            mock_workflow.graph.in_edges.return_value = [
                ("node1", "node2", {"mapping": {"output1": "input1"}})
            ]

            mock_node = Mock()
            node_outputs = {"node1": {"output1": "test_data"}}
            parameters = {"param1": "value1"}

            with patch(
                "kailash.utils.data_validation.DataTypeValidator"
            ) as mock_validator:
                mock_validator.validate_node_output.return_value = {
                    "output1": "test_data"
                }

                inputs = runtime._prepare_node_inputs(
                    workflow=mock_workflow,
                    node_id="node2",
                    node_instance=mock_node,
                    node_outputs=node_outputs,
                    parameters=parameters,
                )

                assert inputs["input1"] == "test_data"
                assert inputs["param1"] == "value1"

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_prepare_node_inputs_nested_mapping(self):
        """Test node input preparation with nested key mapping."""
        try:
            from kailash.runtime.local import LocalRuntime

            runtime = LocalRuntime(debug=True)

            # Create mock workflow
            mock_workflow = Mock()
            mock_workflow.graph = nx.DiGraph()
            mock_workflow.graph.in_edges.return_value = [
                ("node1", "node2", {"mapping": {"result.files": "input_files"}})
            ]

            mock_node = Mock()
            node_outputs = {"node1": {"result": {"files": ["file1.txt", "file2.txt"]}}}

            with patch(
                "kailash.utils.data_validation.DataTypeValidator"
            ) as mock_validator:
                mock_validator.validate_node_output.return_value = node_outputs["node1"]

                inputs = runtime._prepare_node_inputs(
                    workflow=mock_workflow,
                    node_id="node2",
                    node_instance=mock_node,
                    node_outputs=node_outputs,
                    parameters={},
                )

                assert inputs["input_files"] == ["file1.txt", "file2.txt"]

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_prepare_node_inputs_failed_source_node(self):
        """Test node input preparation with failed source node."""
        try:
            from kailash.runtime.local import LocalRuntime
            from kailash.sdk_exceptions import WorkflowExecutionError

            runtime = LocalRuntime()

            mock_workflow = Mock()
            mock_workflow.graph = nx.DiGraph()
            mock_workflow.graph.in_edges.return_value = [
                ("node1", "node2", {"mapping": {"output1": "input1"}})
            ]

            mock_node = Mock()
            node_outputs = {"node1": {"failed": True, "error": "Node failed"}}

            with pytest.raises(
                WorkflowExecutionError, match="Cannot use outputs from failed node"
            ):
                runtime._prepare_node_inputs(
                    workflow=mock_workflow,
                    node_id="node2",
                    node_instance=mock_node,
                    node_outputs=node_outputs,
                    parameters={},
                )

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_prepare_node_inputs_runtime_parameters(self):
        """Test node input preparation with runtime parameters."""
        try:
            from kailash.runtime.local import LocalRuntime

            runtime = LocalRuntime()

            mock_workflow = Mock()
            mock_workflow.graph = nx.DiGraph()
            mock_workflow.graph.in_edges.return_value = []

            mock_node = Mock()
            parameters = {
                "consumer_timeout_ms": 5000,
                "max_messages": 100,
                "limit": 50,
                "config_param": "not_runtime",
            }

            inputs = runtime._prepare_node_inputs(
                workflow=mock_workflow,
                node_id="node1",
                node_instance=mock_node,
                node_outputs={},
                parameters=parameters,
            )

            assert inputs["timeout_ms"] == 5000
            assert inputs["max_messages"] == 100
            assert inputs["limit"] == 50
            assert inputs["config_param"] == "not_runtime"

        except ImportError:
            pytest.skip("LocalRuntime not available")


class TestUtilityMethods:
    """Test utility and helper methods."""

    def test_should_stop_on_error_with_dependents(self):
        """Test should_stop_on_error with dependent nodes."""
        try:
            from kailash.runtime.local import LocalRuntime

            runtime = LocalRuntime()

            mock_workflow = Mock()
            mock_workflow.graph = nx.DiGraph()
            mock_workflow.graph.add_node("node1")
            mock_workflow.graph.add_node("node2")
            mock_workflow.graph.add_edge("node1", "node2")
            mock_workflow.graph.out_degree.return_value = 1

            result = runtime._should_stop_on_error(mock_workflow, "node1")
            assert result is True

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_should_stop_on_error_no_dependents(self):
        """Test should_stop_on_error with no dependent nodes."""
        try:
            from kailash.runtime.local import LocalRuntime

            runtime = LocalRuntime()

            mock_workflow = Mock()
            mock_workflow.graph = nx.DiGraph()
            mock_workflow.graph.add_node("node1")
            mock_workflow.graph.out_degree.return_value = 0

            result = runtime._should_stop_on_error(mock_workflow, "node1")
            assert result is False

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_serialize_user_context_pydantic(self):
        """Test user context serialization with Pydantic model."""
        try:
            from kailash.runtime.local import LocalRuntime

            user_context = TestUserContext()
            runtime = LocalRuntime(user_context=user_context)

            result = runtime._serialize_user_context()
            expected = {"user_id": "test_user", "roles": ["analyst"]}
            assert result == expected

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_serialize_user_context_dict_object(self):
        """Test user context serialization with dict-like object."""
        try:
            from kailash.runtime.local import LocalRuntime

            class DictLikeContext:
                def __init__(self):
                    self.user_id = "test_user"
                    self.roles = ["admin"]

            user_context = DictLikeContext()
            runtime = LocalRuntime(user_context=user_context)

            result = runtime._serialize_user_context()
            assert result["user_id"] == "test_user"
            assert result["roles"] == ["admin"]

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_serialize_user_context_string_fallback(self):
        """Test user context serialization with string fallback."""
        try:
            from kailash.runtime.local import LocalRuntime

            user_context = "simple_string_context"
            runtime = LocalRuntime(user_context=user_context)

            result = runtime._serialize_user_context()
            assert result == {"user_context": "simple_string_context"}

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_serialize_user_context_none(self):
        """Test user context serialization with None."""
        try:
            from kailash.runtime.local import LocalRuntime

            runtime = LocalRuntime(user_context=None)

            result = runtime._serialize_user_context()
            assert result is None

        except ImportError:
            pytest.skip("LocalRuntime not available")


class TestParameterProcessing:
    """Test parameter processing methods."""

    def test_process_workflow_parameters_none(self):
        """Test parameter processing with None parameters."""
        try:
            from kailash.runtime.local import LocalRuntime

            runtime = LocalRuntime()
            mock_workflow = Mock()

            result = runtime._process_workflow_parameters(mock_workflow, None)
            assert result is None

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_separate_parameter_formats(self):
        """Test parameter format separation."""
        try:
            from kailash.runtime.local import LocalRuntime

            runtime = LocalRuntime(debug=True)

            mock_workflow = Mock()
            mock_workflow.graph = nx.DiGraph()
            mock_workflow.graph.add_node("node1")
            mock_workflow.graph.add_node("node2")

            # Mixed format parameters
            parameters = {
                "node1": {"param1": "value1"},  # Node-specific
                "global_param": "global_value",  # Workflow-level
                "node2": {"param2": "value2"},  # Node-specific
                "another_global": "global2",  # Workflow-level
            }

            node_specific, workflow_level = runtime._separate_parameter_formats(
                parameters, mock_workflow
            )

            assert node_specific == {
                "node1": {"param1": "value1"},
                "node2": {"param2": "value2"},
            }
            assert workflow_level == {
                "global_param": "global_value",
                "another_global": "global2",
            }

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_is_node_specific_format_true(self):
        """Test node-specific format detection (positive case)."""
        try:
            from kailash.runtime.local import LocalRuntime

            runtime = LocalRuntime()

            mock_workflow = Mock()
            mock_workflow.graph = nx.DiGraph()
            mock_workflow.graph.add_node("node1")

            parameters = {"node1": {"param": "value"}}

            result = runtime._is_node_specific_format(parameters, mock_workflow)
            assert result is True

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_is_node_specific_format_false(self):
        """Test node-specific format detection (negative case)."""
        try:
            from kailash.runtime.local import LocalRuntime

            runtime = LocalRuntime()

            mock_workflow = Mock()
            mock_workflow.graph = nx.DiGraph()
            mock_workflow.graph.add_node("node1")

            parameters = {"global_param": "value"}

            result = runtime._is_node_specific_format(parameters, mock_workflow)
            assert result is False

        except ImportError:
            pytest.skip("LocalRuntime not available")

    def test_is_node_specific_format_heuristic(self):
        """Test node-specific format detection with heuristics."""
        try:
            from kailash.runtime.local import LocalRuntime

            runtime = LocalRuntime()

            mock_workflow = Mock()
            mock_workflow.graph = nx.DiGraph()

            # All dict values with ID-like keys
            parameters = {
                "node_task": {"param": "value"},
                "data_processor": {"setting": "config"},
            }

            result = runtime._is_node_specific_format(parameters, mock_workflow)
            assert result is True

        except ImportError:
            pytest.skip("LocalRuntime not available")
