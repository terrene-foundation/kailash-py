"""Integration tests for the Nexus multi-channel framework."""

import asyncio
import logging
from typing import Any, Dict

import pytest

# Configure logging
logging.basicConfig(level=logging.WARNING)  # Reduce noise in tests


@pytest.mark.asyncio
class TestNexusFramework:
    """Integration tests for the complete Nexus framework."""

    async def test_nexus_creation_and_configuration(self):
        """Test Nexus Gateway creation and configuration."""
        from src.kailash.nexus import (
            create_api_nexus,
            create_development_nexus,
            create_nexus,
        )

        # Test basic nexus creation with MCP enabled
        nexus1 = create_nexus(
            name="test-nexus-1",
            enable_cli=False,  # Disable to avoid interactive mode
            enable_mcp=True,  # Test MCP integration
            api_port=8901,
            mcp_port=3001,
        )

        # Test specialized nexus creation
        api_nexus = create_api_nexus(name="api-test-nexus", port=8902)

        dev_nexus = create_development_nexus(
            name="dev-test-nexus", api_port=8903, mcp_port=3002
        )

        # Test configuration
        assert nexus1.config.name == "test-nexus-1"
        assert nexus1.config.api_port == 8901
        assert not nexus1.config.enable_cli
        assert nexus1.config.enable_mcp
        assert nexus1.config.enable_api

        assert api_nexus.config.enable_api
        assert not api_nexus.config.enable_cli
        assert not api_nexus.config.enable_mcp

        # Test health checks without starting
        health1 = await nexus1.health_check()
        health2 = await api_nexus.health_check()
        health3 = await dev_nexus.health_check()

        assert not health1["nexus_running"]  # Should not be running yet
        assert not health2["nexus_running"]
        assert not health3["nexus_running"]

        # Test stats
        stats1 = await nexus1.get_stats()
        assert stats1["nexus"]["name"] == "test-nexus-1"
        assert stats1["nexus"]["channels_enabled"] == 2  # API and MCP enabled

    async def test_workflow_registration_across_channels(self):
        """Test workflow registration across different channels."""
        from src.kailash.nexus import create_nexus
        from src.kailash.workflow.builder import WorkflowBuilder

        # Create a simple test workflow
        workflow_builder = WorkflowBuilder()
        workflow_builder.add_node(
            "PythonCodeNode", "test_node", {"code": "return {'result': 'test_success'}"}
        )
        test_workflow = workflow_builder.build()

        # Create nexus with API and MCP enabled
        nexus = create_nexus(
            name="workflow-test-nexus",
            enable_cli=False,
            enable_mcp=True,
            api_port=8904,
            mcp_port=3003,
        )

        # Register workflow
        nexus.register_workflow("test_workflow", test_workflow)

        # Check workflow registration
        workflows = nexus.list_workflows()
        assert "test_workflow" in workflows, f"Workflow not registered: {workflows}"

        # Check that workflow is available on API channel
        api_channel = nexus.get_channel("api")
        assert api_channel is not None, "API channel not found"

        # Check that workflow is available on MCP channel
        mcp_channel = nexus.get_channel("mcp")
        assert mcp_channel is not None, "MCP channel not found"

    async def test_session_management(self):
        """Test session management across channels."""
        from src.kailash.channels.session import CrossChannelSession, SessionManager

        manager = SessionManager(default_timeout=60)
        await manager.start()

        try:
            # Create sessions
            session1 = manager.create_session(user_id="user1")
            session2 = manager.create_session(user_id="user2")

            # Test session channels
            session1.add_channel("api", {"context": "api_session"})
            session1.add_channel("cli", {"context": "cli_session"})
            session2.add_channel("api", {"context": "api_session2"})

            # Test session data
            session1.set_shared_data("preference", "dark_mode")
            session1.add_event({"type": "login", "timestamp": 1234567890})

            # Test manager operations
            api_sessions = manager.get_channel_sessions("api")
            assert (
                len(api_sessions) == 2
            ), f"Expected 2 API sessions, got {len(api_sessions)}"

            cli_sessions = manager.get_channel_sessions("cli")
            assert (
                len(cli_sessions) == 1
            ), f"Expected 1 CLI session, got {len(cli_sessions)}"

            # Test broadcast
            broadcast_count = await manager.broadcast_to_channel(
                "api", {"message": "test"}
            )
            assert (
                broadcast_count == 2
            ), f"Expected to broadcast to 2 sessions, got {broadcast_count}"

        finally:
            await manager.stop()

    async def test_event_routing(self):
        """Test event routing functionality."""
        from src.kailash.channels.base import ChannelEvent, ChannelType
        from src.kailash.channels.event_router import EventRouter
        from src.kailash.channels.session import SessionManager

        # Create session manager and event router
        session_manager = SessionManager()
        await session_manager.start()

        router = EventRouter(session_manager)
        await router.start()

        try:
            # Create a test event
            event = ChannelEvent(
                event_id="test_event_1",
                channel_name="api",
                channel_type=ChannelType.API,
                event_type="workflow_executed",
                payload={"workflow": "test", "success": True},
            )

            # Route the event
            await router.route_event(event)

            # Check stats
            stats = router.get_stats()
            assert (
                stats["total_events"] >= 1
            ), f"Expected at least 1 event, got {stats['total_events']}"

            # Health check
            health = await router.health_check()
            assert health["healthy"], f"Router health check failed: {health}"

        finally:
            await router.stop()
            await session_manager.stop()

    async def test_individual_channel_implementations(self):
        """Test individual channel implementations including MCP."""
        from src.kailash.channels.api_channel import APIChannel
        from src.kailash.channels.base import ChannelConfig, ChannelType
        from src.kailash.channels.cli_channel import CLIChannel
        from src.kailash.channels.mcp_channel import MCPChannel

        # Test API Channel
        api_config = ChannelConfig(
            name="test-api", channel_type=ChannelType.API, host="localhost", port=8905
        )
        api_channel = APIChannel(api_config)

        assert api_channel.name == "test-api"
        assert api_channel.channel_type == ChannelType.API
        assert not api_channel.is_running

        api_health = await api_channel.health_check()
        assert "healthy" in api_health

        # Test CLI Channel
        cli_config = ChannelConfig(name="test-cli", channel_type=ChannelType.CLI)
        cli_channel = CLIChannel(cli_config)

        assert cli_channel.name == "test-cli"
        assert cli_channel.channel_type == ChannelType.CLI

        cli_health = await cli_channel.health_check()
        assert "healthy" in cli_health

        # Test MCP Channel (critical test for initialization fix)
        mcp_config = ChannelConfig(
            name="test-mcp", channel_type=ChannelType.MCP, host="localhost", port=3004
        )
        mcp_channel = MCPChannel(mcp_config)

        assert mcp_channel.name == "test-mcp"
        assert mcp_channel.channel_type == ChannelType.MCP
        assert not mcp_channel.is_running

        # Test MCP health check
        mcp_health = await mcp_channel.health_check()
        assert "healthy" in mcp_health
        assert "mcp_server_running" in mcp_health["checks"]

        # Test MCP workflow registration
        from src.kailash.workflow.builder import WorkflowBuilder

        test_workflow_builder = WorkflowBuilder()
        test_workflow_builder.add_node(
            "PythonCodeNode",
            "test_mcp_node",
            {"code": "return {'mcp_result': 'success'}"},
        )
        test_mcp_workflow = test_workflow_builder.build()

        mcp_channel.register_workflow("test_mcp_workflow", test_mcp_workflow)

        # Test MCP tools list
        tools_response = await mcp_channel._handle_tools_list()
        assert "tools" in tools_response
        assert (
            len(tools_response["tools"]) > 0
        )  # Should have default tools + workflow tool

    async def test_command_parsing(self):
        """Test command parsing functionality."""
        from src.kailash.nodes.system.command_parser import (
            CommandParserNode,
            CommandRouterNode,
        )

        # Test CommandParserNode
        parser = CommandParserNode()

        # Test simple command
        result = parser.execute(command_input="help")
        assert result["success"], f"Simple command failed: {result}"
        assert result["command_name"] == "help"

        # Test command with arguments
        result = parser.execute(
            command_input="status --verbose",
            command_definitions={
                "status": {
                    "type": "system",
                    "arguments": {
                        "verbose": {
                            "flags": ["--verbose", "-v"],
                            "action": "store_true",
                        }
                    },
                }
            },
        )
        assert result["success"], f"Command with args failed: {result}"
        assert result["command_name"] == "status"

        # Test RouterNode
        router = CommandRouterNode()

        routing_result = router.execute(
            parsed_command={
                "command_type": "system",
                "command_name": "help",
                "arguments": {},
                "subcommand": None,
            },
            routing_config={"help": {"type": "handler", "handler": "show_help"}},
        )

        assert routing_result["success"], f"Routing failed: {routing_result}"
        assert routing_result["routing_target"]["handler"] == "show_help"


@pytest.mark.asyncio
async def test_complete_nexus_integration():
    """Test complete Nexus integration scenario."""
    # This test combines multiple components to verify end-to-end functionality
    from src.kailash.nexus import create_development_nexus
    from src.kailash.workflow.builder import WorkflowBuilder

    # Create a development nexus with all channels
    nexus = create_development_nexus(
        name="integration-test-nexus", api_port=8910, mcp_port=3010
    )

    # Create and register a test workflow
    workflow_builder = WorkflowBuilder()
    workflow_builder.add_node(
        "PythonCodeNode",
        "integration_test",
        {"code": "return {'integration_test': 'passed', 'timestamp': '2025-07-09'}"},
    )
    test_workflow = workflow_builder.build()

    nexus.register_workflow("integration_test_workflow", test_workflow)

    # Verify workflow is available
    workflows = nexus.list_workflows()
    assert "integration_test_workflow" in workflows

    # Verify all channels are accessible
    api_channel = nexus.get_channel("api")
    cli_channel = nexus.get_channel("cli")
    mcp_channel = nexus.get_channel("mcp")

    assert api_channel is not None
    assert cli_channel is not None
    assert mcp_channel is not None

    # Test health checks (be flexible with channel health during testing)
    health = await nexus.health_check()
    assert not health["nexus_running"]  # Not started yet
    assert "checks" in health
    assert "channels" in health["checks"]

    # Verify all expected channels are present in health check
    expected_channels = ["api", "cli", "mcp"]
    for channel_name in expected_channels:
        assert (
            channel_name in health["checks"]["channels"]
        ), f"Channel {channel_name} missing from health check"
        assert (
            "healthy" in health["checks"]["channels"][channel_name]
        ), f"Channel {channel_name} missing healthy status"

    # Test stats
    stats = await nexus.get_stats()
    assert stats["nexus"]["name"] == "integration-test-nexus"
    assert stats["nexus"]["channels_enabled"] == 3  # All channels enabled
    assert stats["nexus"]["workflows_registered"] == 1  # Correct key name
