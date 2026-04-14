"""Unit tests for CLI channel workflow execution (gap C4)."""

import asyncio
from io import StringIO
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kailash.channels.base import ChannelConfig, ChannelType
from kailash.channels.cli_channel import CLIChannel


def _make_config(name: str = "test-cli") -> ChannelConfig:
    """Create a minimal ChannelConfig for testing."""
    return ChannelConfig(name=name, channel_type=ChannelType.CLI)


class TestWorkflowRegistration:
    """Tests for CLIChannel.register_workflow."""

    @pytest.fixture
    def channel(self):
        ch = CLIChannel(config=_make_config(), output_stream=StringIO())
        yield ch
        ch.close()

    def test_register_workflow_stores_definition(self, channel):
        mock_workflow = MagicMock()
        channel.register_workflow("my_wf", mock_workflow)

        assert "my_wf" in channel._registered_workflows
        assert channel._registered_workflows["my_wf"] is mock_workflow

    def test_register_multiple_workflows(self, channel):
        wf1 = MagicMock()
        wf2 = MagicMock()
        channel.register_workflow("wf1", wf1)
        channel.register_workflow("wf2", wf2)

        assert len(channel._registered_workflows) == 2
        assert channel._registered_workflows["wf1"] is wf1
        assert channel._registered_workflows["wf2"] is wf2

    def test_register_workflow_overwrites_existing(self, channel):
        old_wf = MagicMock()
        new_wf = MagicMock()
        channel.register_workflow("wf", old_wf)
        channel.register_workflow("wf", new_wf)

        assert channel._registered_workflows["wf"] is new_wf


class TestExecuteWorkflowCommand:
    """Tests for CLIChannel._execute_workflow_command."""

    @pytest.fixture
    def channel(self):
        ch = CLIChannel(config=_make_config(), output_stream=StringIO())
        yield ch
        ch.close()

    @pytest.mark.asyncio
    async def test_execute_registered_workflow(self, channel):
        # Create a mock workflow with .build()
        mock_built = MagicMock()
        mock_builder = MagicMock()
        mock_builder.build.return_value = mock_built

        channel.register_workflow("greet", mock_builder)

        # Mock the async runtime
        channel.runtime.execute_workflow_async = AsyncMock(
            return_value=({"output": "hello"}, "run-123")
        )

        result = await channel._execute_workflow_command(
            {"command_arguments": {"workflow": "greet"}}
        )

        assert result["success"] is True
        assert result["workflow_name"] == "greet"
        assert result["run_id"] == "run-123"
        assert result["results"] == {"output": "hello"}
        assert "execution_time_ms" in result
        assert result["execution_time_ms"] >= 0

        mock_builder.build.assert_called_once()
        channel.runtime.execute_workflow_async.assert_awaited_once_with(
            mock_built, inputs={}
        )

    @pytest.mark.asyncio
    async def test_execute_workflow_with_json_input(self, channel):
        mock_workflow = MagicMock()
        mock_workflow.build.return_value = MagicMock()
        channel.register_workflow("process", mock_workflow)

        channel.runtime.execute_workflow_async = AsyncMock(
            return_value=({"status": "done"}, "run-456")
        )

        result = await channel._execute_workflow_command(
            {
                "command_arguments": {
                    "workflow": "process",
                    "input": '{"key": "value"}',
                }
            }
        )

        assert result["success"] is True
        channel.runtime.execute_workflow_async.assert_awaited_once()
        call_kwargs = channel.runtime.execute_workflow_async.call_args
        assert call_kwargs.kwargs["inputs"] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_execute_workflow_invalid_json_input(self, channel):
        mock_workflow = MagicMock()
        channel.register_workflow("wf", mock_workflow)

        result = await channel._execute_workflow_command(
            {"command_arguments": {"workflow": "wf", "input": "not-json"}}
        )

        assert result["success"] is False
        assert "Invalid JSON input" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_workflow_not_found(self, channel):
        result = await channel._execute_workflow_command(
            {"command_arguments": {"workflow": "nonexistent"}}
        )

        assert result["success"] is False
        assert "not found" in result["error"]
        assert "nonexistent" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_workflow_no_name_provided(self, channel):
        result = await channel._execute_workflow_command({"command_arguments": {}})

        assert result["success"] is False
        assert "No workflow name provided" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_workflow_runtime_error(self, channel):
        mock_workflow = MagicMock()
        mock_workflow.build.return_value = MagicMock()
        channel.register_workflow("failing", mock_workflow)

        channel.runtime.execute_workflow_async = AsyncMock(
            side_effect=RuntimeError("Node execution failed")
        )

        result = await channel._execute_workflow_command(
            {"command_arguments": {"workflow": "failing"}}
        )

        assert result["success"] is False
        assert "Workflow execution failed" in result["error"]
        assert result["workflow_name"] == "failing"

    @pytest.mark.asyncio
    async def test_execute_workflow_without_build_method(self, channel):
        """Workflow objects that are already built (no .build() method)."""
        # A pre-built workflow object with no .build() method
        pre_built = {"nodes": [], "connections": []}
        channel.register_workflow("prebuilt", pre_built)

        channel.runtime.execute_workflow_async = AsyncMock(
            return_value=({"result": "ok"}, "run-789")
        )

        result = await channel._execute_workflow_command(
            {"command_arguments": {"workflow": "prebuilt"}}
        )

        assert result["success"] is True
        channel.runtime.execute_workflow_async.assert_awaited_once_with(
            pre_built, inputs={}
        )

    @pytest.mark.asyncio
    async def test_execute_workflow_from_workflow_server(self):
        """Workflow resolved from workflow_server when not directly registered."""
        mock_server = MagicMock()
        mock_registration = MagicMock()
        mock_registration.workflow = MagicMock()
        mock_server.workflows = {"server_wf": mock_registration}

        channel = CLIChannel(
            config=_make_config(),
            output_stream=StringIO(),
            workflow_server=mock_server,
        )

        channel.runtime.execute_workflow_async = AsyncMock(
            return_value=({"from": "server"}, "run-svr")
        )

        result = await channel._execute_workflow_command(
            {"command_arguments": {"workflow": "server_wf"}}
        )

        assert result["success"] is True
        assert result["workflow_name"] == "server_wf"
        assert result["results"] == {"from": "server"}

        channel.close()

    @pytest.mark.asyncio
    async def test_execute_workflow_not_found_shows_available(self):
        """Error message for missing workflow includes available workflow names."""
        mock_server = MagicMock()
        mock_server.workflows = {"server_wf": MagicMock()}

        channel = CLIChannel(
            config=_make_config(),
            output_stream=StringIO(),
            workflow_server=mock_server,
        )
        channel.register_workflow("local_wf", MagicMock())

        result = await channel._execute_workflow_command(
            {"command_arguments": {"workflow": "missing"}}
        )

        assert result["success"] is False
        assert "local_wf" in result["error"]
        assert "server_wf" in result["error"]

        channel.close()


class TestHandleListWorkflows:
    """Tests for CLIChannel._handle_list_workflows."""

    @pytest.fixture
    def channel(self):
        ch = CLIChannel(config=_make_config(), output_stream=StringIO())
        yield ch
        ch.close()

    @pytest.mark.asyncio
    async def test_list_no_workflows(self, channel):
        result = await channel._handle_list_workflows({})

        assert result["success"] is True
        assert result["workflows"] == []
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_list_registered_workflows(self, channel):
        wf = MagicMock()
        wf.description = "Test workflow"
        channel.register_workflow("test_wf", wf)

        result = await channel._handle_list_workflows({})

        assert result["success"] is True
        assert result["count"] == 1
        assert result["workflows"][0]["name"] == "test_wf"
        assert result["workflows"][0]["description"] == "Test workflow"
        assert result["workflows"][0]["source"] == "registered"

    @pytest.mark.asyncio
    async def test_list_server_workflows(self):
        mock_server = MagicMock()
        mock_reg = MagicMock()
        mock_reg.description = "Server workflow desc"
        mock_server.workflows = {"srv_wf": mock_reg}

        channel = CLIChannel(
            config=_make_config(),
            output_stream=StringIO(),
            workflow_server=mock_server,
        )

        result = await channel._handle_list_workflows({})

        assert result["success"] is True
        assert result["count"] == 1
        assert result["workflows"][0]["name"] == "srv_wf"
        assert result["workflows"][0]["source"] == "server"

        channel.close()

    @pytest.mark.asyncio
    async def test_list_combined_workflows_no_duplicates(self):
        """When same name exists in both sources, registered takes precedence."""
        mock_server = MagicMock()
        mock_reg = MagicMock()
        mock_reg.description = "Server version"
        mock_server.workflows = {"shared": mock_reg, "server_only": mock_reg}

        channel = CLIChannel(
            config=_make_config(),
            output_stream=StringIO(),
            workflow_server=mock_server,
        )
        local_wf = MagicMock()
        local_wf.description = "Local version"
        channel.register_workflow("shared", local_wf)

        result = await channel._handle_list_workflows({})

        assert result["success"] is True
        assert result["count"] == 2
        names = [w["name"] for w in result["workflows"]]
        assert "shared" in names
        assert "server_only" in names
        # "shared" should come from registered, not server
        shared = next(w for w in result["workflows"] if w["name"] == "shared")
        assert shared["source"] == "registered"
        assert shared["description"] == "Local version"

        channel.close()


class TestCLIChannelInit:
    """Tests for CLIChannel initialization with new parameters."""

    def test_default_init_no_workflow_server(self):
        channel = CLIChannel(
            config=_make_config(),
            output_stream=StringIO(),
        )
        assert channel.workflow_server is None
        assert channel._registered_workflows == {}
        channel.close()

    def test_init_with_workflow_server(self):
        mock_server = MagicMock()
        channel = CLIChannel(
            config=_make_config(),
            output_stream=StringIO(),
            workflow_server=mock_server,
        )
        assert channel.workflow_server is mock_server
        channel.close()

    def test_runtime_is_async(self):
        from kailash.runtime.async_local import AsyncLocalRuntime

        channel = CLIChannel(
            config=_make_config(),
            output_stream=StringIO(),
        )
        assert isinstance(channel.runtime, AsyncLocalRuntime)
        channel.close()
