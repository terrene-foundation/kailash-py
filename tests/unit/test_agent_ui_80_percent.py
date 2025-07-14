"""Comprehensive tests to boost middleware.core.agent_ui coverage from 22% to >80%."""

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest


class TestWorkflowSession:
    """Test WorkflowSession class functionality."""

    def test_workflow_session_initialization(self):
        """Test WorkflowSession initialization."""
        try:
            from kailash.middleware.core.agent_ui import WorkflowSession

            session = WorkflowSession(
                session_id="session_123",
                user_id="user_456",
                metadata={"client": "web", "version": "1.0"},
            )

            assert session.session_id == "session_123"
            assert session.user_id == "user_456"
            assert session.metadata == {"client": "web", "version": "1.0"}
            assert session.active is True
            assert isinstance(session.workflows, dict)
            assert isinstance(session.executions, dict)
            assert isinstance(session.created_at, datetime)

        except ImportError:
            pytest.skip("WorkflowSession not available")

    def test_workflow_session_add_workflow(self):
        """Test adding workflows to session."""
        try:
            from kailash.middleware.core.agent_ui import WorkflowSession

            session = WorkflowSession("session_123")
            mock_workflow = Mock()
            mock_workflow.name = "Test Workflow"

            session.add_workflow("workflow_1", mock_workflow)

            assert "workflow_1" in session.workflows
            assert session.workflows["workflow_1"] == mock_workflow

        except ImportError:
            pytest.skip("WorkflowSession not available")

    def test_workflow_session_start_execution(self):
        """Test starting workflow execution."""
        try:
            from kailash.middleware.core.agent_ui import WorkflowSession

            session = WorkflowSession("session_123")
            mock_workflow = Mock()
            mock_workflow.name = "Test Workflow"
            session.add_workflow("workflow_1", mock_workflow)

            execution_id = session.start_execution("workflow_1", {"input": "data"})

            assert execution_id in session.executions
            execution = session.executions[execution_id]
            assert execution["workflow_id"] == "workflow_1"
            assert execution["inputs"] == {"input": "data"}
            assert execution["status"] == "started"
            assert execution["progress"] == 0.0

        except ImportError:
            pytest.skip("WorkflowSession not available")

    def test_workflow_session_start_execution_nonexistent_workflow(self):
        """Test starting execution with non-existent workflow."""
        try:
            from kailash.middleware.core.agent_ui import WorkflowSession

            session = WorkflowSession("session_123")

            with pytest.raises(ValueError, match="Workflow nonexistent not found"):
                session.start_execution("nonexistent")

        except ImportError:
            pytest.skip("WorkflowSession not available")

    def test_workflow_session_update_execution(self):
        """Test updating execution status."""
        try:
            from kailash.middleware.core.agent_ui import WorkflowSession

            session = WorkflowSession("session_123")
            mock_workflow = Mock()
            session.add_workflow("workflow_1", mock_workflow)
            execution_id = session.start_execution("workflow_1")

            # Update execution
            session.update_execution(
                execution_id, status="running", progress=50.0, current_node="node1"
            )

            execution = session.executions[execution_id]
            assert execution["status"] == "running"
            assert execution["progress"] == 50.0
            assert execution["current_node"] == "node1"
            assert "updated_at" in execution

        except ImportError:
            pytest.skip("WorkflowSession not available")

    def test_workflow_session_update_nonexistent_execution(self):
        """Test updating non-existent execution (should not crash)."""
        try:
            from kailash.middleware.core.agent_ui import WorkflowSession

            session = WorkflowSession("session_123")

            # This should not raise an error, just do nothing
            session.update_execution("nonexistent", status="completed")

            # Verify no executions were created
            assert len(session.executions) == 0

        except ImportError:
            pytest.skip("WorkflowSession not available")


class TestAgentUIMiddlewareInit:
    """Test AgentUIMiddleware initialization."""

    def test_agent_ui_middleware_default_init(self):
        """Test AgentUIMiddleware with default settings."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            with patch("kailash.middleware.core.agent_ui.MiddlewareWorkflowRepository"):
                with patch(
                    "kailash.middleware.core.agent_ui.MiddlewareExecutionRepository"
                ):
                    middleware = AgentUIMiddleware()

                    assert middleware.enable_dynamic_workflows is True
                    assert middleware.max_sessions == 1000
                    assert middleware.session_timeout_minutes == 60
                    assert middleware.enable_workflow_sharing is True
                    assert middleware.enable_persistence is False  # No database_url
                    assert isinstance(middleware.sessions, dict)
                    assert isinstance(middleware.shared_workflows, dict)
                    assert isinstance(middleware.active_executions, dict)

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")

    def test_agent_ui_middleware_custom_init(self):
        """Test AgentUIMiddleware with custom settings."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            with patch("kailash.middleware.core.agent_ui.MiddlewareWorkflowRepository"):
                with patch(
                    "kailash.middleware.core.agent_ui.MiddlewareExecutionRepository"
                ):
                    middleware = AgentUIMiddleware(
                        enable_dynamic_workflows=False,
                        max_sessions=500,
                        session_timeout_minutes=30,
                        enable_workflow_sharing=False,
                        enable_persistence=True,
                        database_url="postgresql://localhost/test",
                    )

                    assert middleware.enable_dynamic_workflows is False
                    assert middleware.max_sessions == 500
                    assert middleware.session_timeout_minutes == 30
                    assert middleware.enable_workflow_sharing is False
                    assert middleware.enable_persistence is True

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")

    def test_init_sdk_nodes(self):
        """Test SDK nodes initialization."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            with patch(
                "kailash.middleware.core.agent_ui.CredentialManagerNode"
            ) as mock_cred:
                with patch(
                    "kailash.middleware.core.agent_ui.DataTransformer"
                ) as mock_trans:
                    with patch(
                        "kailash.middleware.core.agent_ui.MiddlewareWorkflowRepository"
                    ) as mock_repo:
                        with patch(
                            "kailash.middleware.core.agent_ui.MiddlewareExecutionRepository"
                        ) as mock_exec_repo:
                            middleware = AgentUIMiddleware(
                                enable_persistence=True,
                                database_url="postgresql://localhost/test",
                            )

                            # Verify SDK nodes were initialized
                            mock_cred.assert_called_once()
                            mock_trans.assert_called_once()
                            mock_repo.assert_called_once()
                            mock_exec_repo.assert_called_once()

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")


class TestSessionManagement:
    """Test session management methods."""

    def test_create_session_basic(self):
        """Test basic session creation."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware()

            async def test_async():
                session_id = await middleware.create_session(
                    user_id="user123", metadata={"client": "web"}
                )

                assert session_id in middleware.sessions
                session = middleware.sessions[session_id]
                assert session.user_id == "user123"
                assert session.metadata == {"client": "web"}
                assert session.active is True
                assert middleware.sessions_created == 1

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")

    def test_create_session_no_user_id(self):
        """Test session creation without user ID."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware()

            async def test_async():
                session_id = await middleware.create_session()

                assert session_id in middleware.sessions
                session = middleware.sessions[session_id]
                assert session.user_id is None
                assert session.metadata == {}

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")

    def test_create_session_max_sessions_reached(self):
        """Test session creation when max sessions reached."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware(max_sessions=2)

            async def test_async():
                # Create max sessions
                session1 = await middleware.create_session()
                session2 = await middleware.create_session()

                # Try to create one more
                with pytest.raises(
                    RuntimeError, match="Maximum sessions limit reached"
                ):
                    await middleware.create_session()

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")

    def test_get_session_existing(self):
        """Test getting existing session."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware()

            async def test_async():
                session_id = await middleware.create_session(user_id="user123")

                retrieved_session = await middleware.get_session(session_id)

                assert retrieved_session is not None
                assert retrieved_session.session_id == session_id
                assert retrieved_session.user_id == "user123"

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")

    def test_get_session_nonexistent(self):
        """Test getting non-existent session."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware()

            async def test_async():
                session = await middleware.get_session("nonexistent")
                assert session is None

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")

    def test_close_session_existing(self):
        """Test closing existing session."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware()

            async def test_async():
                session_id = await middleware.create_session()

                await middleware.close_session(session_id)

                # Session should be marked inactive
                session = middleware.sessions[session_id]
                assert session.active is False

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")

    def test_close_session_nonexistent(self):
        """Test closing non-existent session."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware()

            async def test_async():
                # Should not raise error
                await middleware.close_session("nonexistent")

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")

    def test_cleanup_old_sessions(self):
        """Test cleanup of old sessions."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware(
                session_timeout_minutes=0
            )  # Immediate timeout

            async def test_async():
                session_id = await middleware.create_session()

                # Make session look old
                session = middleware.sessions[session_id]
                session.created_at = datetime.now(timezone.utc).replace(year=2020)

                await middleware._cleanup_old_sessions()

                # Session should be inactive
                assert session.active is False

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")


class TestWorkflowManagement:
    """Test workflow management methods."""

    def test_register_workflow(self):
        """Test workflow registration."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware()
            mock_workflow = Mock()
            mock_workflow.name = "Test Workflow"

            async def test_async():
                session_id = await middleware.create_session()

                await middleware.register_workflow(
                    workflow_id="workflow_1",
                    workflow=mock_workflow,
                    session_id=session_id,
                    make_shared=False,
                )

                session = middleware.sessions[session_id]
                assert "workflow_1" in session.workflows
                assert session.workflows["workflow_1"] == mock_workflow

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")

    def test_register_shared_workflow(self):
        """Test shared workflow registration."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware()
            mock_workflow = Mock()
            mock_workflow.name = "Shared Workflow"

            async def test_async():
                await middleware.register_workflow(
                    workflow_id="shared_workflow",
                    workflow=mock_workflow,
                    make_shared=True,
                )

                assert "shared_workflow" in middleware.shared_workflows
                assert middleware.shared_workflows["shared_workflow"] == mock_workflow

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")

    def test_create_dynamic_workflow(self):
        """Test dynamic workflow creation."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware(enable_dynamic_workflows=True)

            workflow_config = {
                "name": "Test Workflow",
                "description": "A test workflow",
                "nodes": [
                    {
                        "id": "node1",
                        "type": "PythonCodeNode",
                        "config": {"code": "result = 42"},
                    }
                ],
                "connections": [],
            }

            with patch.object(middleware, "_build_workflow_from_config") as mock_build:
                mock_workflow = Mock()
                mock_build.return_value = mock_workflow

                async def test_async():
                    session_id = await middleware.create_session()

                    workflow_id = await middleware.create_dynamic_workflow(
                        session_id, workflow_config
                    )

                    assert workflow_id is not None
                    mock_build.assert_called_once_with(workflow_config)

                asyncio.run(test_async())

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")

    def test_create_dynamic_workflow_disabled(self):
        """Test dynamic workflow creation when disabled."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware(enable_dynamic_workflows=False)

            async def test_async():
                session_id = await middleware.create_session()

                with pytest.raises(
                    RuntimeError, match="Dynamic workflow creation is disabled"
                ):
                    await middleware.create_dynamic_workflow(session_id, {})

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")

    def test_build_workflow_from_config(self):
        """Test building workflow from configuration."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware()

            config = {
                "name": "Test Workflow",
                "nodes": [
                    {
                        "id": "node1",
                        "type": "PythonCodeNode",
                        "config": {"code": "result = 42"},
                    }
                ],
                "connections": [],
            }

            with patch(
                "kailash.middleware.core.agent_ui.WorkflowBuilder"
            ) as mock_builder:
                mock_workflow = Mock()
                mock_builder.from_dict.return_value.build.return_value = mock_workflow

                async def test_async():
                    result = await middleware._build_workflow_from_config(config)

                    assert result == mock_workflow
                    mock_builder.from_dict.assert_called_once_with(config)

                asyncio.run(test_async())

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")


class TestWorkflowExecution:
    """Test workflow execution methods."""

    def test_execute_workflow_basic(self):
        """Test basic workflow execution."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware()
            mock_workflow = Mock()
            mock_workflow.name = "Test Workflow"

            async def test_async():
                session_id = await middleware.create_session()
                await middleware.register_workflow(
                    "workflow_1", mock_workflow, session_id
                )

                with patch.object(
                    middleware, "_execute_workflow_async"
                ) as mock_execute:
                    execution_id = await middleware.execute_workflow(
                        session_id, "workflow_1", {"input": "data"}
                    )

                    assert execution_id in middleware.active_executions
                    execution = middleware.active_executions[execution_id]
                    assert execution["workflow_id"] == "workflow_1"
                    assert execution["session_id"] == session_id
                    assert execution["inputs"] == {"input": "data"}

                    mock_execute.assert_called_once_with(execution_id)

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")

    def test_execute_workflow_nonexistent_session(self):
        """Test executing workflow with non-existent session."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware()

            async def test_async():
                with pytest.raises(ValueError, match="Session 'nonexistent' not found"):
                    await middleware.execute_workflow("nonexistent", "workflow_1")

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")

    def test_execute_workflow_nonexistent_workflow(self):
        """Test executing non-existent workflow."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware()

            async def test_async():
                session_id = await middleware.create_session()

                with pytest.raises(
                    ValueError, match="Workflow 'nonexistent' not found"
                ):
                    await middleware.execute_workflow(session_id, "nonexistent")

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")

    def test_execute_method(self):
        """Test execute method (deprecated interface)."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware()
            mock_workflow = Mock()

            with patch.object(middleware, "execute_workflow") as mock_execute:
                mock_execute.return_value = "execution_123"

                async def test_async():
                    session_id = await middleware.create_session()

                    result = await middleware.execute(
                        workflow=mock_workflow,
                        session_id=session_id,
                        inputs={"data": "test"},
                    )

                    assert result == "execution_123"

                asyncio.run(test_async())

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")

    def test_get_execution_status_existing(self):
        """Test getting execution status for existing execution."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware()

            async def test_async():
                session_id = await middleware.create_session()

                # Manually create execution data
                execution_id = str(uuid.uuid4())
                middleware.active_executions[execution_id] = {
                    "status": "running",
                    "progress": 50.0,
                    "session_id": session_id,
                }

                status = await middleware.get_execution_status(execution_id, session_id)

                assert status is not None
                assert status["status"] == "running"
                assert status["progress"] == 50.0

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")

    def test_get_execution_status_nonexistent(self):
        """Test getting status for non-existent execution."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware()

            async def test_async():
                session_id = await middleware.create_session()

                status = await middleware.get_execution_status(
                    "nonexistent", session_id
                )
                assert status is None

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")

    def test_cancel_execution(self):
        """Test canceling execution."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware()

            async def test_async():
                session_id = await middleware.create_session()

                # Create execution
                execution_id = str(uuid.uuid4())
                middleware.active_executions[execution_id] = {
                    "status": "running",
                    "session_id": session_id,
                    "task": Mock(),  # Mock asyncio task
                }

                await middleware.cancel_execution(execution_id, session_id)

                # Execution should be marked as cancelled
                execution = middleware.active_executions[execution_id]
                assert execution["status"] == "cancelled"

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")


class TestNodeDiscovery:
    """Test node discovery methods."""

    def test_get_available_nodes(self):
        """Test getting available nodes."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware()

            # Mock node registry
            mock_node_class = Mock()
            mock_node_class.__name__ = "TestNode"
            mock_node_class.__doc__ = "A test node"

            with patch.object(
                middleware.node_registry, "_nodes", {"TestNode": mock_node_class}
            ):
                with patch.object(middleware, "_get_node_schema") as mock_schema:
                    mock_schema.return_value = {"type": "object"}

                    async def test_async():
                        nodes = await middleware.get_available_nodes()

                        assert len(nodes) == 1
                        assert nodes[0]["name"] == "TestNode"
                        assert nodes[0]["description"] == "A test node"
                        assert nodes[0]["schema"] == {"type": "object"}

                    asyncio.run(test_async())

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")

    def test_get_node_schema(self):
        """Test getting node schema."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware()

            mock_node_class = Mock()
            mock_instance = Mock()
            mock_node_class.return_value = mock_instance
            mock_instance.get_parameters.return_value = {
                "param1": Mock(name="param1", type_hint=str, required=True)
            }

            schema = middleware._get_node_schema(mock_node_class)

            assert "properties" in schema
            assert "param1" in schema["properties"]

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")


class TestStatisticsAndEvents:
    """Test statistics and event methods."""

    def test_get_stats(self):
        """Test getting middleware statistics."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware()

            # Create some test data
            middleware.sessions_created = 5
            middleware.workflows_executed = 10
            middleware.events_emitted = 20

            stats = middleware.get_stats()

            assert stats["uptime_seconds"] > 0
            assert stats["active_sessions"] == 0  # No active sessions yet
            assert stats["total_sessions_created"] == 5
            assert stats["workflows_executed"] == 10
            assert stats["events_emitted"] == 20

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")

    def test_subscribe_to_events(self):
        """Test event subscription."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware()
            mock_callback = Mock()

            async def test_async():
                subscriber_id = await middleware.subscribe_to_events(
                    callback=mock_callback,
                    event_types=["workflow.started", "workflow.completed"],
                )

                assert subscriber_id is not None
                # Verify subscription was registered with event stream
                # This would need to be mocked based on actual EventStream implementation

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")

    def test_unsubscribe_from_events(self):
        """Test event unsubscription."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware()

            async def test_async():
                # Should not raise error even with non-existent subscriber
                await middleware.unsubscribe_from_events("nonexistent")

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")


class TestEventEmission:
    """Test event emission methods."""

    def test_emit_execution_event(self):
        """Test emitting execution events."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware()

            # Mock event stream
            with patch.object(middleware.event_stream, "emit") as mock_emit:

                async def test_async():
                    await middleware._emit_execution_event(
                        execution_id="exec_123",
                        event_type="workflow.started",
                        data={"workflow_id": "workflow_1"},
                    )

                    mock_emit.assert_called_once()

                asyncio.run(test_async())

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")


class TestErrorHandling:
    """Test error handling scenarios."""

    def test_execution_with_invalid_workflow_config(self):
        """Test handling invalid workflow configuration."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware()

            invalid_config = {
                "name": "Invalid Workflow",
                "nodes": [{"id": "invalid", "type": "NonExistentNode"}],
            }

            with patch(
                "kailash.middleware.core.agent_ui.WorkflowBuilder"
            ) as mock_builder:
                mock_builder.from_dict.side_effect = Exception("Invalid node type")

                async def test_async():
                    with pytest.raises(Exception, match="Invalid node type"):
                        await middleware._build_workflow_from_config(invalid_config)

                asyncio.run(test_async())

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")

    def test_session_operations_with_inactive_session(self):
        """Test operations on inactive sessions."""
        try:
            from kailash.middleware.core.agent_ui import AgentUIMiddleware

            middleware = AgentUIMiddleware()

            async def test_async():
                session_id = await middleware.create_session()
                await middleware.close_session(session_id)  # Make inactive

                # Try to execute workflow on inactive session
                # Implementation should handle this gracefully
                session = await middleware.get_session(session_id)
                assert session is not None
                assert session.active is False

            asyncio.run(test_async())

        except ImportError:
            pytest.skip("AgentUIMiddleware not available")
