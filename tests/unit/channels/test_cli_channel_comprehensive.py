"""Comprehensive unit tests for cli_channel module."""

import asyncio
from io import StringIO
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock, patch

import pytest
from kailash.channels.base import ChannelConfig, ChannelStatus, ChannelType
from kailash.channels.cli_channel import CLIChannel, CLISession


class TestCLISession:
    """Test CLISession dataclass."""

    def test_cli_session_creation_minimal(self):
        """Test creating CLISession with minimal fields."""
        session = CLISession(session_id="test_session")

        assert session.session_id == "test_session"
        assert session.user_id is None
        assert session.shell_state == {}
        assert session.command_history == []
        assert session.active is True
        assert session.last_command_time is None

    def test_cli_session_creation_full(self):
        """Test creating CLISession with all fields."""
        shell_state = {"var1": "value1"}
        command_history = ["help", "status"]

        session = CLISession(
            session_id="test_session",
            user_id="user123",
            shell_state=shell_state,
            command_history=command_history,
            active=False,
            last_command_time=123456.789,
        )

        assert session.session_id == "test_session"
        assert session.user_id == "user123"
        assert session.shell_state == shell_state
        assert session.command_history == command_history
        assert session.active is False
        assert session.last_command_time == 123456.789


class TestCLIChannel:
    """Test CLIChannel class."""

    @pytest.fixture
    def channel_config(self):
        """Create channel configuration."""
        return ChannelConfig(
            name="test_cli",
            channel_type=ChannelType.CLI,
            host="localhost",
            port=None,
            enable_sessions=True,
            enable_auth=False,
            enable_event_routing=True,
            extra_config={"interactive_mode": False, "prompt_template": "test> "},
        )

    @pytest.fixture
    def mock_input_stream(self):
        """Create mock input stream."""
        return StringIO("help\nstatus\nexit\n")

    @pytest.fixture
    def mock_output_stream(self):
        """Create mock output stream."""
        return StringIO()

    @pytest.fixture
    def cli_channel(self, channel_config, mock_input_stream, mock_output_stream):
        """Create CLIChannel instance."""
        with (
            patch("kailash.channels.cli_channel.CommandParserNode"),
            patch("kailash.channels.cli_channel.InteractiveShellNode"),
            patch("kailash.channels.cli_channel.CommandRouterNode"),
            patch("kailash.channels.cli_channel.LocalRuntime"),
        ):

            return CLIChannel(
                config=channel_config,
                input_stream=mock_input_stream,
                output_stream=mock_output_stream,
            )

    def test_init_with_streams(
        self, channel_config, mock_input_stream, mock_output_stream
    ):
        """Test initialization with provided streams."""
        with (
            patch("kailash.channels.cli_channel.CommandParserNode"),
            patch("kailash.channels.cli_channel.InteractiveShellNode"),
            patch("kailash.channels.cli_channel.CommandRouterNode"),
            patch("kailash.channels.cli_channel.LocalRuntime"),
        ):

            channel = CLIChannel(
                config=channel_config,
                input_stream=mock_input_stream,
                output_stream=mock_output_stream,
            )

            assert channel.input_stream is mock_input_stream
            assert channel.output_stream is mock_output_stream
            assert channel.name == "test_cli"

    def test_init_without_streams(self, channel_config):
        """Test initialization without provided streams."""
        import sys

        with (
            patch("kailash.channels.cli_channel.CommandParserNode"),
            patch("kailash.channels.cli_channel.InteractiveShellNode"),
            patch("kailash.channels.cli_channel.CommandRouterNode"),
            patch("kailash.channels.cli_channel.LocalRuntime"),
        ):

            channel = CLIChannel(config=channel_config)

            assert channel.input_stream is sys.stdin
            assert channel.output_stream is sys.stdout

    def test_setup_default_commands(self, cli_channel):
        """Test default command setup."""
        commands = cli_channel._command_definitions

        assert "run" in commands
        assert "list" in commands
        assert "status" in commands
        assert "config" in commands

        # Check run command structure
        run_cmd = commands["run"]
        assert run_cmd["type"] == "workflow"
        assert "arguments" in run_cmd
        assert "workflow" in run_cmd["arguments"]

    def test_setup_default_routing(self, cli_channel):
        """Test default routing setup."""
        routing = cli_channel._routing_config

        assert "run" in routing
        assert "list:workflows" in routing
        assert "status" in routing
        assert "help" in routing
        assert "exit" in routing

    @pytest.mark.asyncio
    async def test_start_channel(self, cli_channel):
        """Test starting the CLI channel."""
        cli_channel.status = ChannelStatus.STOPPED

        with (
            patch.object(cli_channel, "_setup_event_queue"),
            patch.object(cli_channel, "emit_event") as mock_emit,
            patch.object(cli_channel, "_cli_loop") as mock_loop,
        ):

            await cli_channel.start()

            assert cli_channel.status == ChannelStatus.RUNNING
            assert "default" in cli_channel._sessions
            assert cli_channel._current_session is not None
            assert cli_channel._running is True
            mock_emit.assert_called()

    @pytest.mark.asyncio
    async def test_start_already_running(self, cli_channel):
        """Test starting channel when already running."""
        cli_channel.status = ChannelStatus.RUNNING

        await cli_channel.start()

        assert cli_channel.status == ChannelStatus.RUNNING

    @pytest.mark.asyncio
    async def test_start_with_error(self, cli_channel):
        """Test starting channel with error."""
        cli_channel.status = ChannelStatus.STOPPED

        with patch.object(
            cli_channel, "_setup_event_queue", side_effect=Exception("Test error")
        ):
            with pytest.raises(Exception, match="Test error"):
                await cli_channel.start()

            assert cli_channel.status == ChannelStatus.ERROR

    @pytest.mark.asyncio
    async def test_stop_channel(self, cli_channel):
        """Test stopping the CLI channel."""
        cli_channel.status = ChannelStatus.RUNNING
        cli_channel._running = True

        # Create a task that will be cancelled
        async def dummy_task():
            await asyncio.sleep(1)

        task = asyncio.create_task(dummy_task())
        cli_channel._main_task = task

        with (
            patch.object(cli_channel, "emit_event") as mock_emit,
            patch.object(cli_channel, "_cleanup") as mock_cleanup,
        ):

            await cli_channel.stop()

            assert cli_channel.status == ChannelStatus.STOPPED
            assert cli_channel._running is False
            # Note: cancel is called within the stop method
            mock_emit.assert_called()
            mock_cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_already_stopped(self, cli_channel):
        """Test stopping channel when already stopped."""
        cli_channel.status = ChannelStatus.STOPPED

        await cli_channel.stop()

        assert cli_channel.status == ChannelStatus.STOPPED

    @pytest.mark.asyncio
    async def test_handle_request_success(self, cli_channel):
        """Test handling successful request."""
        request = {"command": "help", "session_id": "test_session"}

        mock_result = {"type": "success", "message": "Help displayed"}

        with patch.object(cli_channel, "_process_command", return_value=mock_result):
            response = await cli_channel.handle_request(request)

            assert response.success is True
            assert response.data == mock_result
            assert response.metadata["session_id"] == "test_session"

    @pytest.mark.asyncio
    async def test_handle_request_with_exception(self, cli_channel):
        """Test handling request with exception."""
        request = {"command": "invalid"}

        with patch.object(
            cli_channel, "_process_command", side_effect=Exception("Process error")
        ):
            response = await cli_channel.handle_request(request)

            assert response.success is False
            assert "Process error" in response.error

    @pytest.mark.asyncio
    async def test_cli_loop_non_interactive(self, cli_channel):
        """Test CLI loop in non-interactive mode."""
        cli_channel._running = True
        cli_channel.config.extra_config["interactive_mode"] = False

        with (
            patch.object(cli_channel, "_generate_prompt", return_value="test> "),
            patch.object(cli_channel, "_write_output") as mock_write,
        ):

            await cli_channel._cli_loop()

            mock_write.assert_called()

    @pytest.mark.asyncio
    async def test_cli_loop_with_error(self, cli_channel):
        """Test CLI loop with error handling."""
        cli_channel._running = True
        cli_channel.config.extra_config["interactive_mode"] = True

        with (
            patch.object(
                cli_channel, "_generate_prompt", side_effect=Exception("Prompt error")
            ),
            patch.object(cli_channel, "_write_output") as mock_write,
        ):

            # Set _running to False after first iteration to exit loop
            def stop_after_error(*args):
                cli_channel._running = False

            mock_write.side_effect = stop_after_error

            await cli_channel._cli_loop()

            mock_write.assert_called()

    @pytest.mark.asyncio
    async def test_generate_prompt_with_session(self, cli_channel):
        """Test prompt generation with session."""
        session = CLISession(session_id="test_session")
        cli_channel._current_session = session
        cli_channel.shell_node.execute.return_value = {"prompt": "custom> "}

        prompt = await cli_channel._generate_prompt()

        assert prompt == "custom> "
        cli_channel.shell_node.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_prompt_without_session(self, cli_channel):
        """Test prompt generation without session."""
        cli_channel._current_session = None

        prompt = await cli_channel._generate_prompt()

        assert prompt == "kailash> "

    @pytest.mark.asyncio
    async def test_process_command_parse_failure(self, cli_channel):
        """Test processing command with parse failure."""
        session = CLISession(session_id="test_session")
        cli_channel.command_parser.execute.return_value = {
            "success": False,
            "error": "Parse error",
        }

        result = await cli_channel._process_command("invalid command", session)

        assert result["type"] == "error"
        assert "Parse error" in result["message"]

    @pytest.mark.asyncio
    async def test_process_command_shell_handling(self, cli_channel):
        """Test processing command handled by shell."""
        session = CLISession(session_id="test_session")
        cli_channel.command_parser.execute.return_value = {
            "success": True,
            "parsed_command": {},
        }
        cli_channel.shell_node.execute.return_value = {
            "shell_result": {"type": "handled", "output": "Shell output"},
            "session_state": {"var": "value"},
        }

        result = await cli_channel._process_command("shell command", session)

        assert result["type"] == "shell_command"
        assert result["result"]["type"] == "handled"

    @pytest.mark.asyncio
    async def test_process_command_routing_failure(self, cli_channel):
        """Test processing command with routing failure."""
        session = CLISession(session_id="test_session")
        cli_channel.command_parser.execute.return_value = {
            "success": True,
            "parsed_command": {},
        }
        cli_channel.shell_node.execute.return_value = {
            "shell_result": {"type": "passthrough"},
            "session_state": {},
        }
        cli_channel.router_node.execute.return_value = {
            "success": False,
            "error": "Routing error",
        }

        result = await cli_channel._process_command("unknown command", session)

        assert result["type"] == "error"
        assert "Routing error" in result["message"]

    @pytest.mark.asyncio
    async def test_process_command_successful_routing(self, cli_channel):
        """Test processing command with successful routing."""
        session = CLISession(session_id="test_session")
        cli_channel.command_parser.execute.return_value = {
            "success": True,
            "parsed_command": {},
        }
        cli_channel.shell_node.execute.return_value = {
            "shell_result": {"type": "passthrough"},
            "session_state": {},
        }
        cli_channel.router_node.execute.return_value = {
            "success": True,
            "routing_target": {"type": "handler", "handler": "show_help"},
            "execution_params": {},
        }

        execution_result = {"success": True, "message": "Help displayed"}

        with patch.object(
            cli_channel, "_execute_routed_command", return_value=execution_result
        ):
            result = await cli_channel._process_command("help", session)

            assert result["type"] == "command_execution"
            assert result["execution_result"] == execution_result

    @pytest.mark.asyncio
    async def test_execute_routed_command_workflow_executor(self, cli_channel):
        """Test executing workflow executor command."""
        routing_target = {"type": "workflow_executor", "handler": "execute_workflow"}
        execution_params = {"workflow": "test_workflow"}
        session = CLISession(session_id="test_session")

        with patch.object(
            cli_channel, "_execute_workflow_command", return_value={"success": True}
        ):
            result = await cli_channel._execute_routed_command(
                routing_target, execution_params, session
            )

            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_routed_command_handler(self, cli_channel):
        """Test executing handler command."""
        routing_target = {"type": "handler", "handler": "show_help"}
        execution_params = {}
        session = CLISession(session_id="test_session")

        with patch.object(
            cli_channel, "_execute_handler_command", return_value={"success": True}
        ):
            result = await cli_channel._execute_routed_command(
                routing_target, execution_params, session
            )

            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_routed_command_unknown_type(self, cli_channel):
        """Test executing command with unknown type."""
        routing_target = {"type": "unknown", "handler": "unknown"}
        execution_params = {}
        session = CLISession(session_id="test_session")

        result = await cli_channel._execute_routed_command(
            routing_target, execution_params, session
        )

        assert result["success"] is False
        assert "Unknown target type" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_workflow_command(self, cli_channel):
        """Test executing workflow command."""
        execution_params = {"workflow": "test_workflow", "inputs": {}}

        result = await cli_channel._execute_workflow_command(execution_params)

        assert result["success"] is True
        assert "not yet implemented" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_handler_command_help(self, cli_channel):
        """Test executing help handler command."""
        execution_params = {}
        session = CLISession(session_id="test_session")

        with patch.object(
            cli_channel,
            "_handle_help",
            return_value={"success": True, "message": "Help text"},
        ):
            result = await cli_channel._execute_handler_command(
                "show_help", execution_params, session
            )

            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_handler_command_unknown(self, cli_channel):
        """Test executing unknown handler command."""
        execution_params = {}
        session = CLISession(session_id="test_session")

        result = await cli_channel._execute_handler_command(
            "unknown_handler", execution_params, session
        )

        assert result["success"] is False
        assert "Unknown handler" in result["error"]

    @pytest.mark.asyncio
    async def test_handle_help_general(self, cli_channel):
        """Test general help command."""
        params = {"command_arguments": {}}

        result = await cli_channel._handle_help(params)

        assert result["success"] is True
        assert "Available commands" in result["message"]
        assert "run:" in result["message"]

    @pytest.mark.asyncio
    async def test_handle_help_specific_command(self, cli_channel):
        """Test help for specific command."""
        params = {"command_arguments": {"topic": "run"}}

        result = await cli_channel._handle_help(params)

        assert result["success"] is True
        assert "run:" in result["message"]
        assert "Execute a workflow" in result["message"]

    @pytest.mark.asyncio
    async def test_handle_status(self, cli_channel):
        """Test status command."""
        params = {"command_arguments": {"verbose": False}}
        cli_channel._sessions = {"session1": CLISession("session1", active=True)}

        result = await cli_channel._handle_status(params)

        assert result["success"] is True
        assert result["data"]["channel"] == "test_cli"
        assert result["data"]["sessions"] == 1

    @pytest.mark.asyncio
    async def test_handle_status_verbose(self, cli_channel):
        """Test verbose status command."""
        params = {"command_arguments": {"verbose": True}}

        with patch.object(
            cli_channel, "get_status", return_value={"detailed": "status"}
        ):
            result = await cli_channel._handle_status(params)

            assert result["success"] is True
            assert "detailed" in result["data"]

    @pytest.mark.asyncio
    async def test_handle_list_workflows(self, cli_channel):
        """Test list workflows command."""
        params = {}

        result = await cli_channel._handle_list_workflows(params)

        assert result["success"] is True
        assert "not yet implemented" in result["message"]
        assert result["workflows"] == []

    @pytest.mark.asyncio
    async def test_handle_list_sessions(self, cli_channel):
        """Test list sessions command."""
        session1 = CLISession("session1", user_id="user1", active=True)
        session1.command_history = ["help", "status"]
        session1.last_command_time = 123456.789

        cli_channel._sessions = {"session1": session1}
        params = {}

        result = await cli_channel._handle_list_sessions(params)

        assert result["success"] is True
        sessions = result["data"]["sessions"]
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "session1"
        assert sessions[0]["user_id"] == "user1"
        assert sessions[0]["command_count"] == 2

    @pytest.mark.asyncio
    async def test_handle_exit_force(self, cli_channel):
        """Test exit command with force."""
        params = {"command_arguments": {"force": True}}
        session = CLISession("session1")

        with patch.object(cli_channel, "stop") as mock_stop:
            result = await cli_channel._handle_exit(params, session)

            assert result["success"] is True
            assert "Exiting CLI" in result["message"]

    @pytest.mark.asyncio
    async def test_handle_exit_single_session(self, cli_channel):
        """Test exit command with single session."""
        params = {"command_arguments": {"force": False}}
        session = CLISession("session1")
        cli_channel._sessions = {"session1": session}

        with patch.object(cli_channel, "stop") as mock_stop:
            result = await cli_channel._handle_exit(params, session)

            assert result["success"] is True
            assert "Exiting CLI" in result["message"]

    @pytest.mark.asyncio
    async def test_handle_exit_multiple_sessions(self, cli_channel):
        """Test exit command with multiple sessions."""
        params = {"command_arguments": {"force": False}}
        session1 = CLISession("session1")
        session2 = CLISession("session2")
        cli_channel._sessions = {"session1": session1, "session2": session2}

        result = await cli_channel._handle_exit(params, session1)

        assert result["success"] is True
        assert "deactivated" in result["message"]
        assert session1.active is False

    def test_write_output(self, cli_channel, mock_output_stream):
        """Test writing output to stream."""
        cli_channel._write_output("Test output")

        mock_output_stream.seek(0)
        output = mock_output_stream.read()
        assert "Test output" in output

    def test_write_output_no_stream(self, channel_config):
        """Test writing output with no stream."""
        with (
            patch("kailash.channels.cli_channel.CommandParserNode"),
            patch("kailash.channels.cli_channel.InteractiveShellNode"),
            patch("kailash.channels.cli_channel.CommandRouterNode"),
            patch("kailash.channels.cli_channel.LocalRuntime"),
        ):

            channel = CLIChannel(config=channel_config, output_stream=None)

            # Should not raise an exception
            channel._write_output("Test output")

    @pytest.mark.asyncio
    async def test_health_check(self, cli_channel):
        """Test health check."""
        active_session = CLISession("session1", active=True)
        inactive_session = CLISession("session2", active=False)
        cli_channel._sessions = {
            "session1": active_session,
            "session2": inactive_session,
        }

        with patch("kailash.channels.cli_channel.super") as mock_super:
            mock_super_health = Mock()
            mock_super_health.health_check = AsyncMock(
                return_value={"healthy": True, "checks": {"base": True}}
            )
            mock_super.return_value = mock_super_health

            health = await cli_channel.health_check()

        assert health["healthy"] is True
        assert "sessions_active" in health["checks"]
        assert "command_parser_ready" in health["checks"]
        assert health["sessions"] == 2
        assert health["active_sessions"] == 1
