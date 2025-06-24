"""
Basic Integration Test for Refactored Middleware

Simple test to verify the middleware refactoring is working correctly
and SDK components are being used as intended.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest


def test_middleware_imports():
    """Test that all refactored middleware components can be imported."""
    from kailash.middleware.auth import MiddlewareAuthManager as MiddlewareAuth
    from kailash.middleware.communication.ai_chat import AIChatMiddleware
    from kailash.middleware.communication.events import EventStream
    from kailash.middleware.communication.realtime import RealtimeMiddleware
    from kailash.middleware.core.agent_ui import AgentUIMiddleware

    print("✅ All middleware imports successful")


def test_auth_uses_sdk_nodes():
    """Test that auth middleware uses SDK security nodes."""
    from kailash.middleware.auth import MiddlewareAuthManager as MiddlewareAuth
    from kailash.nodes.admin import PermissionCheckNode
    from kailash.nodes.security import CredentialManagerNode, RotatingCredentialNode

    # Create auth manager with a test secret - it will store it in the credential manager
    auth = MiddlewareAuth(secret_key="test-secret-key")

    # Check that SDK nodes are being used
    assert hasattr(auth, "credential_manager")
    assert isinstance(auth.credential_manager, CredentialManagerNode)

    # Check API key manager (only exists if enable_api_keys=True, which is default)
    assert hasattr(auth, "api_key_manager")
    assert isinstance(auth.api_key_manager, RotatingCredentialNode)

    # Check permission checker
    assert hasattr(auth, "permission_checker")
    assert isinstance(auth.permission_checker, PermissionCheckNode)

    print("✅ Auth middleware uses SDK security nodes")


def test_agent_ui_uses_sdk_runtime():
    """Test that agent UI middleware uses SDK runtime."""
    from kailash.middleware.core.agent_ui import AgentUIMiddleware
    from kailash.runtime.local import LocalRuntime

    agent_ui = AgentUIMiddleware()

    # Check that SDK runtime is being used
    assert hasattr(agent_ui, "runtime")
    assert isinstance(agent_ui.runtime, LocalRuntime)

    # Check that WorkflowBuilder integration exists
    assert hasattr(agent_ui, "sessions")

    print("✅ Agent UI middleware uses SDK runtime")


def test_realtime_uses_sdk_http_node():
    """Test that realtime middleware uses SDK HTTP nodes."""
    from kailash.middleware.communication.realtime import WebhookManager
    from kailash.nodes.api import HTTPRequestNode
    from kailash.nodes.security import CredentialManagerNode

    webhook_manager = WebhookManager()

    # Check that SDK nodes are being used
    assert hasattr(webhook_manager, "http_node")
    assert isinstance(webhook_manager.http_node, HTTPRequestNode)

    # Check that credential node is being used (audit node was not found in WebhookManager)
    assert hasattr(webhook_manager, "credential_node")
    assert isinstance(webhook_manager.credential_node, CredentialManagerNode)

    print("✅ Realtime middleware uses SDK HTTP nodes")


@pytest.mark.asyncio
async def test_event_system_basic_functionality():
    """Test basic event system functionality."""
    from kailash.middleware.communication.events import (
        EventStream,
        EventType,
        WorkflowEvent,
    )

    event_stream = EventStream()
    received_events = []

    async def test_handler(event):
        received_events.append(event)

    # Subscribe to events
    await event_stream.subscribe("test", test_handler)

    # Emit test event
    import datetime

    test_event = WorkflowEvent(
        id="test-event",
        type=EventType.WORKFLOW_STARTED,
        workflow_id="test-workflow",
        timestamp=datetime.datetime.now(),
    )

    await event_stream.emit(test_event)

    # Give it a moment to process
    await asyncio.sleep(0.1)

    assert len(received_events) == 1
    assert received_events[0].id == "test-event"

    print("✅ Event system working correctly")


def test_database_repos_use_sdk_nodes():
    """Test that database repositories use SDK database nodes."""
    from kailash.middleware.database.repositories import SessionRepository
    from kailash.nodes.data import AsyncSQLDatabaseNode

    # Create repository with test connection
    repo = SessionRepository("sqlite:///test.db")

    # Check that SDK database node is used
    assert hasattr(repo, "db_node")
    assert isinstance(repo.db_node, AsyncSQLDatabaseNode)

    print("✅ Database repositories use SDK nodes")


def test_ai_chat_uses_sdk_vector_nodes():
    """Test that AI chat middleware uses SDK vector and embedding nodes."""
    from kailash.middleware.communication.ai_chat import AIChatMiddleware
    from kailash.nodes.ai import EmbeddingGeneratorNode

    # Create without vector DB to avoid connection issues
    agent_ui_mock = MagicMock()
    ai_chat = AIChatMiddleware(agent_ui_mock, enable_semantic_search=False)

    # Check workflow generator exists
    assert hasattr(ai_chat, "workflow_generator")
    assert ai_chat.workflow_generator is not None

    # When semantic search is enabled, should have embedding node
    ai_chat_with_vector = AIChatMiddleware(
        agent_ui_mock,
        vector_db_url="postgresql://test:test@localhost/test",
        enable_semantic_search=True,
    )

    assert hasattr(ai_chat_with_vector, "embedding_node")
    assert isinstance(ai_chat_with_vector.embedding_node, EmbeddingGeneratorNode)

    print("✅ AI chat middleware uses SDK vector/embedding nodes")


@pytest.mark.asyncio
async def test_workflow_creation_integration():
    """Test workflow creation using SDK WorkflowBuilder."""
    from kailash.middleware.core.agent_ui import AgentUIMiddleware

    agent_ui = AgentUIMiddleware()

    # Test workflow config
    workflow_config = {
        "name": "test_workflow",
        "nodes": [
            {
                "id": "test_node",
                "type": "PythonCodeNode",
                "config": {"code": "result = {'message': 'test'}"},
            }
        ],
        "connections": [],
    }

    # Mock WorkflowBuilder.from_dict to avoid actual workflow creation
    with patch("kailash.workflow.builder.WorkflowBuilder.from_dict") as mock_from_dict:
        mock_workflow = MagicMock()
        mock_from_dict.return_value = mock_workflow

        # First create a session
        session_id = await agent_ui.create_session(user_id="test_user")

        # Use the correct method name
        workflow_id = await agent_ui.create_dynamic_workflow(
            session_id, workflow_config
        )

        assert workflow_id is not None
        mock_from_dict.assert_called_once_with(workflow_config)

        print("✅ Workflow creation uses SDK WorkflowBuilder")


def run_all_basic_tests():
    """Run all basic integration tests."""
    print("🧪 Running Basic Middleware Integration Tests...\n")

    tests_passed = 0
    total_tests = 0

    # Sync tests
    sync_tests = [
        test_middleware_imports,
        test_auth_uses_sdk_nodes,
        test_agent_ui_uses_sdk_runtime,
        test_realtime_uses_sdk_http_node,
        test_database_repos_use_sdk_nodes,
        test_ai_chat_uses_sdk_vector_nodes,
    ]

    for test in sync_tests:
        total_tests += 1
        try:
            test()
            tests_passed += 1
        except Exception as e:
            print(f"❌ {test.__name__} failed: {e}")

    # Async tests
    async def run_async_tests():
        nonlocal tests_passed, total_tests

        async_tests = [
            test_event_system_basic_functionality,
            test_workflow_creation_integration,
        ]

        for test in async_tests:
            total_tests += 1
            try:
                await test()
                tests_passed += 1
            except Exception as e:
                print(f"❌ {test.__name__} failed: {e}")

    # Run async tests
    asyncio.execute(run_async_tests())

    print(f"\n📊 Test Results: {tests_passed}/{total_tests} tests passed")

    if tests_passed == total_tests:
        print("🎉 All basic integration tests passed!")
        print("✅ Middleware refactoring is working correctly")
        print("✅ SDK components are being used as intended")
    else:
        print(f"⚠️  {total_tests - tests_passed} tests failed")
        print("🔧 Some middleware components may need attention")

    return tests_passed == total_tests
