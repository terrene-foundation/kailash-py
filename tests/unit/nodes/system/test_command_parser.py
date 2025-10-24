"""Unit tests for command parsing nodes."""

from unittest.mock import Mock, patch

import pytest
from src.kailash.nodes.system.command_parser import (
    CommandParserNode,
    CommandRouterNode,
    CommandType,
    InteractiveShellNode,
    ParsedCommand,
)


class TestCommandParserNode:
    """Unit tests for CommandParserNode."""

    def test_parse_simple_command(self):
        """Test parsing a simple command without arguments."""
        node = CommandParserNode()

        result = node.execute(command_input="help")

        assert result["success"] is True
        assert result["command_name"] == "help"
        assert result["command_type"] == "system"
        assert result["arguments"] == {}
        assert result["error"] is None

    def test_parse_command_with_arguments(self):
        """Test parsing a command with arguments."""
        node = CommandParserNode()
        command_defs = {
            "run": {
                "type": "workflow",
                "arguments": {
                    "workflow": {
                        "flags": ["workflow", "--workflow"],
                        "type": str,
                        "required": True,
                    },
                    "verbose": {"flags": ["--verbose", "-v"], "action": "store_true"},
                },
            }
        }

        result = node.execute(
            command_input="run --workflow test_workflow --verbose",
            command_definitions=command_defs,
        )

        assert result["success"] is True
        assert result["command_name"] == "run"
        assert result["command_type"] == "workflow"
        assert "workflow" in result["arguments"]
        assert "verbose" in result["flags"]

    def test_parse_command_with_subcommand(self):
        """Test parsing a command with subcommands."""
        node = CommandParserNode()
        command_defs = {
            "list": {
                "type": "system",
                "subcommands": {
                    "workflows": {
                        "help": "List workflows",
                        "arguments": {
                            "verbose": {
                                "flags": ["--verbose", "-v"],
                                "action": "store_true",
                            }
                        },
                    }
                },
            }
        }

        result = node.execute(
            command_input="list workflows --verbose", command_definitions=command_defs
        )

        assert result["success"] is True
        assert result["command_name"] == "list"
        assert result["subcommand"] == "workflows"
        assert "verbose" in result["flags"]

    def test_parse_unknown_command_allowed(self):
        """Test parsing unknown command when allowed."""
        node = CommandParserNode()

        result = node.execute(
            command_input="unknown_cmd --flag value",
            allow_unknown_commands=True,
            default_command_type="custom",
        )

        assert result["success"] is True
        assert result["command_name"] == "unknown_cmd"
        assert result["command_type"] == "custom"
        assert "flag" in result["arguments"]

    def test_parse_unknown_command_disallowed(self):
        """Test parsing unknown command when not allowed."""
        node = CommandParserNode()

        result = node.execute(command_input="unknown_cmd", allow_unknown_commands=False)

        assert result["success"] is False
        assert result["command_name"] == "unknown_command"
        assert "Unknown command" in result["error"]

    def test_parse_system_commands(self):
        """Test parsing system commands."""
        node = CommandParserNode()

        # Test help command
        result = node.execute(command_input="help topic")
        assert result["command_name"] == "help"
        assert result["arguments"]["topic"] == "topic"

        # Test exit command
        result = node.execute(command_input="exit --force")
        assert result["command_name"] == "exit"
        assert result["arguments"]["force"] is True

    def test_parse_empty_command(self):
        """Test parsing empty command."""
        node = CommandParserNode()

        result = node.execute(command_input="")

        assert result["success"] is True
        assert result["command_name"] == "help"
        assert result["command_type"] == "help"

    def test_parse_invalid_quotes(self):
        """Test parsing command with invalid quotes."""
        node = CommandParserNode()

        result = node.execute(command_input='test "unclosed quote')

        assert result["success"] is False
        assert result["command_name"] == "parse_error"
        assert "Failed to tokenize" in result["error"]


class TestInteractiveShellNode:
    """Unit tests for InteractiveShellNode."""

    def test_shell_initialization(self):
        """Test shell session initialization."""
        node = InteractiveShellNode()

        result = node.execute(
            session_id="test_session", command_input="echo hello", session_state={}
        )

        assert result["success"] is True
        assert result["session_id"] == "test_session"
        assert "history" in result["session_state"]
        assert "environment" in result["session_state"]
        assert "working_directory" in result["session_state"]

    def test_command_history(self):
        """Test command history management."""
        node = InteractiveShellNode()
        session_state = {"history": []}

        # First command
        result = node.execute(
            session_id="test_session",
            command_input="first command",
            session_state=session_state,
        )

        assert len(result["session_state"]["history"]) == 1
        assert result["session_state"]["history"][0]["command"] == "first command"

        # Second command
        result = node.execute(
            session_id="test_session",
            command_input="second command",
            session_state=result["session_state"],
        )

        assert len(result["session_state"]["history"]) == 2

    def test_history_size_limit(self):
        """Test history size limiting."""
        node = InteractiveShellNode()
        session_state = {"history": []}

        # Add more commands than max_history
        for i in range(15):
            result = node.execute(
                session_id="test_session",
                command_input=f"command {i}",
                session_state=session_state,
                max_history=10,
            )
            session_state = result["session_state"]

        assert len(session_state["history"]) == 10
        assert session_state["history"][-1]["command"] == "command 14"

    def test_shell_commands(self):
        """Test shell-specific command processing."""
        node = InteractiveShellNode()
        session_state = {}

        # Test cd command
        result = node.execute(
            session_id="test_session",
            command_input="cd /home/user",
            session_state=session_state,
        )

        assert result["shell_result"]["type"] == "directory_change"
        assert result["session_state"]["working_directory"] == "/home/user"

        # Test set command
        result = node.execute(
            session_id="test_session",
            command_input="set VAR=value",
            session_state=result["session_state"],
        )

        assert result["shell_result"]["type"] == "environment_set"
        assert result["session_state"]["environment"]["VAR"] == "value"

    def test_prompt_generation(self):
        """Test prompt generation with templates."""
        node = InteractiveShellNode()
        session_state = {
            "working_directory": "/home/user",
            "history": ["cmd1", "cmd2"],
            "environment": {"USER": "testuser"},
        }

        result = node.execute(
            session_id="test_session",
            command_input="",
            session_state=session_state,
            prompt_template="{USER}@{cwd}[{history_count}]$ ",
        )

        prompt = result["prompt"]
        assert "testuser" in prompt
        assert "/home/user" in prompt
        assert "2" in prompt

    def test_history_command(self):
        """Test history shell command."""
        node = InteractiveShellNode()
        session_state = {
            "history": [
                {"command": "cmd1", "timestamp": 1234567890},
                {"command": "cmd2", "timestamp": 1234567891},
            ]
        }

        result = node.execute(
            session_id="test_session",
            command_input="history",
            session_state=session_state,
        )

        assert result["shell_result"]["type"] == "history"
        assert len(result["shell_result"]["data"]) == 2


class TestCommandRouterNode:
    """Unit tests for CommandRouterNode."""

    def test_exact_command_routing(self):
        """Test routing with exact command match."""
        node = CommandRouterNode()
        parsed_command = {
            "command_type": "workflow",
            "command_name": "run",
            "arguments": {"workflow": "test"},
            "subcommand": None,
        }
        routing_config = {
            "run": {"type": "workflow_executor", "handler": "execute_workflow"}
        }

        result = node.execute(
            parsed_command=parsed_command, routing_config=routing_config
        )

        assert result["success"] is True
        assert result["routing_target"]["type"] == "workflow_executor"
        assert result["routing_target"]["handler"] == "execute_workflow"

    def test_subcommand_routing(self):
        """Test routing with subcommands."""
        node = CommandRouterNode()
        parsed_command = {
            "command_type": "system",
            "command_name": "list",
            "arguments": {},
            "subcommand": "workflows",
        }
        routing_config = {
            "list:workflows": {"type": "handler", "handler": "list_workflows"}
        }

        result = node.execute(
            parsed_command=parsed_command, routing_config=routing_config
        )

        assert result["success"] is True
        assert result["routing_target"]["handler"] == "list_workflows"

    def test_type_based_routing(self):
        """Test routing based on command type."""
        node = CommandRouterNode()
        parsed_command = {
            "command_type": "workflow",
            "command_name": "unknown_workflow",
            "arguments": {},
            "subcommand": None,
        }
        routing_config = {
            "type:workflow": {"type": "handler", "handler": "handle_workflow"}
        }

        result = node.execute(
            parsed_command=parsed_command, routing_config=routing_config
        )

        assert result["success"] is True
        assert result["routing_target"]["handler"] == "handle_workflow"

    def test_default_routing(self):
        """Test default routing when no match found."""
        node = CommandRouterNode()
        parsed_command = {
            "command_type": "custom",
            "command_name": "unknown",
            "arguments": {},
            "subcommand": None,
        }
        routing_config = {}

        result = node.execute(
            parsed_command=parsed_command,
            routing_config=routing_config,
            default_handler="help",
        )

        assert result["success"] is True
        assert result["routing_target"]["handler"] == "help"

    def test_execution_params_preparation(self):
        """Test execution parameters preparation."""
        node = CommandRouterNode()
        parsed_command = ParsedCommand(
            command_type=CommandType.WORKFLOW,
            command_name="run",
            arguments={"workflow": "test", "input": "data"},
            subcommand=None,
            flags=["verbose"],
            raw_command="run test --input data --verbose",
        )
        routing_config = {
            "run": {
                "type": "workflow_executor",
                "handler": "execute_workflow",
                "parameters": {"timeout": 300},
            }
        }

        result = node.execute(
            parsed_command=parsed_command, routing_config=routing_config
        )

        params = result["execution_params"]
        assert params["command_arguments"]["workflow"] == "test"
        assert params["timeout"] == 300
        assert params["parsed_command"]["command_type"] == "workflow"

    def test_pattern_matching(self):
        """Test pattern-based routing."""
        node = CommandRouterNode()
        parsed_command = {
            "command_type": "custom",
            "command_name": "test_workflow",
            "arguments": {},
            "subcommand": None,
        }
        routing_config = {
            "pattern:*_workflow": {
                "type": "handler",
                "handler": "workflow_pattern_handler",
            }
        }

        result = node.execute(
            parsed_command=parsed_command, routing_config=routing_config
        )

        assert result["success"] is True
        assert result["routing_target"]["handler"] == "workflow_pattern_handler"

    def test_routing_error_handling(self):
        """Test error handling in routing."""
        node = CommandRouterNode()

        # Test with invalid parsed command
        result = node.execute(parsed_command=None, routing_config={})  # Invalid input

        assert result["success"] is False
        assert result["routing_target"]["type"] == "error"
        assert "error" in result


class TestParsedCommand:
    """Unit tests for ParsedCommand dataclass."""

    def test_parsed_command_creation(self):
        """Test ParsedCommand creation and properties."""
        cmd = ParsedCommand(
            command_type=CommandType.WORKFLOW,
            command_name="test",
            arguments={"arg1": "value1"},
            subcommand="sub",
            flags=["flag1"],
            raw_command="test sub --arg1 value1 --flag1",
        )

        assert cmd.command_type == CommandType.WORKFLOW
        assert cmd.command_name == "test"
        assert cmd.arguments["arg1"] == "value1"
        assert cmd.subcommand == "sub"
        assert "flag1" in cmd.flags
        assert cmd.raw_command == "test sub --arg1 value1 --flag1"
        assert cmd.error is None

    def test_parsed_command_defaults(self):
        """Test ParsedCommand with default values."""
        cmd = ParsedCommand(
            command_type=CommandType.SYSTEM, command_name="help", arguments={}
        )

        assert cmd.subcommand is None
        assert cmd.flags == []
        assert cmd.raw_command == ""
        assert cmd.error is None

    def test_parsed_command_with_error(self):
        """Test ParsedCommand with error."""
        cmd = ParsedCommand(
            command_type=CommandType.SYSTEM,
            command_name="error",
            arguments={},
            error="Parse error occurred",
        )

        assert cmd.error == "Parse error occurred"
