"""Command parsing nodes for CLI channel integration."""

import argparse
import asyncio
import logging
import shlex
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from ..base import Node, NodeParameter

logger = logging.getLogger(__name__)


class CommandType(Enum):
    """Types of commands that can be parsed."""

    WORKFLOW = "workflow"
    SYSTEM = "system"
    HELP = "help"
    ADMIN = "admin"
    CUSTOM = "custom"


@dataclass
class ParsedCommand:
    """Represents a parsed command."""

    command_type: CommandType
    command_name: str
    arguments: Dict[str, Any]
    subcommand: Optional[str] = None
    flags: List[str] = None
    raw_command: str = ""
    error: Optional[str] = None

    def __post_init__(self):
        if self.flags is None:
            self.flags = []


class CommandParserNode(Node):
    """Node for parsing CLI commands into structured data.

    This node takes raw command-line input and parses it into a structured
    format that can be used by other nodes in the workflow.
    """

    def __init__(self):
        """Initialize command parser node."""
        super().__init__()

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts.

        Returns:
            Dictionary of parameter definitions
        """
        return {
            "command_input": NodeParameter(
                name="command_input",
                type=str,
                required=True,
                description="Raw command line input to parse",
            ),
            "command_definitions": NodeParameter(
                name="command_definitions",
                type=dict,
                required=False,
                default={},
                description="Dictionary defining available commands and their arguments",
            ),
            "allow_unknown_commands": NodeParameter(
                name="allow_unknown_commands",
                type=bool,
                required=False,
                default=True,
                description="Whether to allow parsing of unknown commands",
            ),
            "default_command_type": NodeParameter(
                name="default_command_type",
                type=str,
                required=False,
                default="workflow",
                description="Default command type for unknown commands",
            ),
        }

    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute command parsing.

        Returns:
            Dictionary containing parsed command data
        """
        # Get parameters
        command_input = kwargs.get("command_input", "")
        command_definitions = kwargs.get("command_definitions", {})
        allow_unknown = kwargs.get("allow_unknown_commands", True)
        default_type = kwargs.get("default_command_type", "workflow")

        try:
            # Parse the command
            parsed_command = self._parse_command(
                command_input, command_definitions, allow_unknown, default_type
            )

            return {
                "parsed_command": parsed_command,
                "success": parsed_command.error is None,
                "command_type": parsed_command.command_type.value,
                "command_name": parsed_command.command_name,
                "arguments": parsed_command.arguments,
                "subcommand": parsed_command.subcommand,
                "flags": parsed_command.flags,
                "error": parsed_command.error,
            }

        except Exception as e:
            logger.error(f"Error parsing command: {e}")

            error_command = ParsedCommand(
                command_type=CommandType.SYSTEM,
                command_name="error",
                arguments={},
                raw_command=command_input,
                error=str(e),
            )

            return {
                "parsed_command": error_command,
                "success": False,
                "command_type": "system",
                "command_name": "error",
                "arguments": {},
                "subcommand": None,
                "flags": [],
                "error": str(e),
            }

    def _parse_command(
        self,
        command_input: str,
        command_definitions: Dict[str, Any],
        allow_unknown: bool,
        default_type: str,
    ) -> ParsedCommand:
        """Parse a command string into structured data.

        Args:
            command_input: Raw command string
            command_definitions: Dictionary of known command definitions
            allow_unknown: Whether to allow unknown commands
            default_type: Default command type for unknown commands

        Returns:
            ParsedCommand instance
        """
        # Tokenize the command
        try:
            tokens = shlex.split(command_input.strip())
        except ValueError as e:
            return ParsedCommand(
                command_type=CommandType.SYSTEM,
                command_name="parse_error",
                arguments={},
                raw_command=command_input,
                error=f"Failed to tokenize command: {e}",
            )

        if not tokens:
            return ParsedCommand(
                command_type=CommandType.HELP,
                command_name="help",
                arguments={},
                raw_command=command_input,
            )

        # Extract command name
        command_name = tokens[0]
        remaining_tokens = tokens[1:] if len(tokens) > 1 else []

        # Check if it's a known command
        if command_name in command_definitions:
            return self._parse_known_command(
                command_name,
                remaining_tokens,
                command_definitions[command_name],
                command_input,
            )

        # Handle special system commands
        if command_name in ["help", "exit", "quit", "status", "version"]:
            return self._parse_system_command(
                command_name, remaining_tokens, command_input
            )

        # Handle unknown commands
        if allow_unknown:
            return self._parse_unknown_command(
                command_name, remaining_tokens, default_type, command_input
            )
        else:
            return ParsedCommand(
                command_type=CommandType.SYSTEM,
                command_name="unknown_command",
                arguments={"requested_command": command_name},
                raw_command=command_input,
                error=f"Unknown command: {command_name}",
            )

    def _parse_known_command(
        self,
        command_name: str,
        tokens: List[str],
        definition: Dict[str, Any],
        raw_command: str,
    ) -> ParsedCommand:
        """Parse a known command using its definition.

        Args:
            command_name: Name of the command
            tokens: Remaining tokens after command name
            definition: Command definition dictionary
            raw_command: Original command string

        Returns:
            ParsedCommand instance
        """
        command_type = CommandType(definition.get("type", "custom"))

        # Create argument parser based on definition
        parser = argparse.ArgumentParser(
            prog=command_name,
            description=definition.get("description", ""),
            add_help=False,  # We'll handle help ourselves
        )

        # Add arguments from definition
        arguments_def = definition.get("arguments", {})
        for arg_name, arg_config in arguments_def.items():
            arg_flags = arg_config.get("flags", [f"--{arg_name}"])
            arg_type = arg_config.get("type", str)
            arg_required = arg_config.get("required", False)
            arg_help = arg_config.get("help", "")
            arg_default = arg_config.get("default")
            arg_action = arg_config.get("action")

            # Filter flags to only include those starting with '-'
            valid_flags = [flag for flag in arg_flags if flag.startswith("-")]
            if not valid_flags:
                valid_flags = [f"--{arg_name}"]  # Fallback

            kwargs = {"help": arg_help}

            if arg_action:
                kwargs["action"] = arg_action
            else:
                kwargs["type"] = arg_type
                kwargs["required"] = arg_required
                if arg_default is not None:
                    kwargs["default"] = arg_default

            parser.add_argument(*valid_flags, **kwargs)

        # Add subcommands if defined
        subcommands_def = definition.get("subcommands", {})
        subparser = None
        if subcommands_def:
            subparser = parser.add_subparsers(dest="subcommand")
            for sub_name, sub_config in subcommands_def.items():
                sub_p = subparser.add_parser(sub_name, help=sub_config.get("help", ""))
                # Add subcommand arguments
                for arg_name, arg_config in sub_config.get("arguments", {}).items():
                    arg_flags = arg_config.get("flags", [f"--{arg_name}"])
                    sub_p.add_argument(
                        *arg_flags,
                        **{k: v for k, v in arg_config.items() if k != "flags"},
                    )

        try:
            # Parse the arguments
            parsed_args = parser.parse_args(tokens)

            # Convert to dictionary
            args_dict = vars(parsed_args)
            subcommand = args_dict.pop("subcommand", None)

            # Extract flags (boolean arguments that were set)
            flags = [
                arg
                for arg, value in args_dict.items()
                if isinstance(value, bool) and value
            ]

            return ParsedCommand(
                command_type=command_type,
                command_name=command_name,
                arguments=args_dict,
                subcommand=subcommand,
                flags=flags,
                raw_command=raw_command,
            )

        except SystemExit:
            # argparse calls sys.exit on error, we catch this
            return ParsedCommand(
                command_type=command_type,
                command_name=command_name,
                arguments={},
                raw_command=raw_command,
                error="Invalid command arguments",
            )

    def _parse_system_command(
        self, command_name: str, tokens: List[str], raw_command: str
    ) -> ParsedCommand:
        """Parse a system command.

        Args:
            command_name: System command name
            tokens: Remaining tokens
            raw_command: Original command string

        Returns:
            ParsedCommand instance
        """
        arguments = {}

        if command_name == "help":
            if tokens:
                arguments["topic"] = tokens[0]
        elif command_name in ["exit", "quit"]:
            arguments["force"] = "--force" in tokens
        elif command_name == "status":
            arguments["verbose"] = "--verbose" in tokens or "-v" in tokens

        flags = [token for token in tokens if token.startswith("-")]

        return ParsedCommand(
            command_type=CommandType.SYSTEM,
            command_name=command_name,
            arguments=arguments,
            flags=flags,
            raw_command=raw_command,
        )

    def _parse_unknown_command(
        self, command_name: str, tokens: List[str], default_type: str, raw_command: str
    ) -> ParsedCommand:
        """Parse an unknown command with basic argument extraction.

        Args:
            command_name: Unknown command name
            tokens: Remaining tokens
            default_type: Default command type to assign
            raw_command: Original command string

        Returns:
            ParsedCommand instance
        """
        arguments = {}
        flags = []
        positional_args = []

        i = 0
        while i < len(tokens):
            token = tokens[i]

            if token.startswith("--"):
                # Long flag
                if "=" in token:
                    key, value = token[2:].split("=", 1)
                    arguments[key] = value
                else:
                    key = token[2:]
                    if i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                        arguments[key] = tokens[i + 1]
                        i += 1
                    else:
                        flags.append(key)
            elif token.startswith("-") and len(token) > 1:
                # Short flag(s)
                flag_chars = token[1:]
                for char in flag_chars:
                    flags.append(char)
            else:
                # Positional argument
                positional_args.append(token)

            i += 1

        # Add positional arguments
        if positional_args:
            arguments["args"] = positional_args

        try:
            command_type = CommandType(default_type)
        except ValueError:
            command_type = CommandType.CUSTOM

        return ParsedCommand(
            command_type=command_type,
            command_name=command_name,
            arguments=arguments,
            flags=flags,
            raw_command=raw_command,
        )


class InteractiveShellNode(Node):
    """Node for handling interactive shell sessions.

    This node manages persistent shell sessions with command history,
    tab completion, and session state.
    """

    def __init__(self):
        """Initialize interactive shell node."""
        super().__init__()

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts.

        Returns:
            Dictionary of parameter definitions
        """
        return {
            "session_id": NodeParameter(
                name="session_id",
                type=str,
                required=True,
                description="Unique session identifier",
            ),
            "command_input": NodeParameter(
                name="command_input",
                type=str,
                required=True,
                description="Command input from user",
            ),
            "session_state": NodeParameter(
                name="session_state",
                type=dict,
                required=False,
                default={},
                description="Current session state",
            ),
            "prompt_template": NodeParameter(
                name="prompt_template",
                type=str,
                required=False,
                default="kailash> ",
                description="Shell prompt template",
            ),
            "max_history": NodeParameter(
                name="max_history",
                type=int,
                required=False,
                default=1000,
                description="Maximum number of commands to keep in history",
            ),
        }

    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute interactive shell processing.

        Returns:
            Dictionary containing shell session data
        """
        # Get parameters
        session_id = kwargs.get("session_id", "")
        command_input = kwargs.get("command_input", "")
        session_state = kwargs.get("session_state", {})
        prompt_template = kwargs.get("prompt_template", "kailash> ")
        max_history = kwargs.get("max_history", 1000)

        try:
            # Initialize session state if needed
            if "history" not in session_state:
                session_state["history"] = []
            if "environment" not in session_state:
                session_state["environment"] = {}
            if "working_directory" not in session_state:
                session_state["working_directory"] = "/"
            if "last_command_time" not in session_state:
                session_state["last_command_time"] = None

            # Process special shell commands BEFORE adding to history
            shell_result = self._process_shell_commands(command_input, session_state)

            # Add command to history (but not if it's a history command to avoid including itself)
            if command_input.strip() and command_input.strip() != "history":
                import time

                current_time = time.time()
                session_state["history"].append(
                    {"command": command_input, "timestamp": current_time}
                )

                # Maintain history size
                if len(session_state["history"]) > max_history:
                    session_state["history"] = session_state["history"][-max_history:]

                session_state["last_command_time"] = current_time

            # Generate prompt
            prompt = self._generate_prompt(prompt_template, session_state)

            return {
                "session_id": session_id,
                "session_state": session_state,
                "prompt": prompt,
                "command_input": command_input,
                "shell_result": shell_result,
                "history_count": len(session_state["history"]),
                "success": True,
            }

        except Exception as e:
            logger.error(f"Error in interactive shell: {e}")
            return {
                "session_id": session_id,
                "session_state": session_state,
                "prompt": prompt_template,
                "command_input": command_input,
                "shell_result": {"error": str(e)},
                "history_count": len(session_state.get("history", [])),
                "success": False,
                "error": str(e),
            }

    def _generate_prompt(self, template: str, session_state: Dict[str, Any]) -> str:
        """Generate shell prompt based on template and session state.

        Args:
            template: Prompt template string
            session_state: Current session state

        Returns:
            Generated prompt string
        """
        # Simple template substitution
        prompt = template

        # Replace common placeholders
        prompt = prompt.replace("{cwd}", session_state.get("working_directory", "/"))
        prompt = prompt.replace(
            "{history_count}", str(len(session_state.get("history", [])))
        )

        # Add environment variables if needed
        for env_key, env_value in session_state.get("environment", {}).items():
            prompt = prompt.replace(f"{{{env_key}}}", str(env_value))

        return prompt

    def _process_shell_commands(
        self, command_input: str, session_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process shell-specific commands.

        Args:
            command_input: Command input string
            session_state: Current session state

        Returns:
            Shell command result
        """
        command = command_input.strip()

        if command == "history":
            return {
                "type": "history",
                "data": session_state.get("history", [])[-20:],  # Last 20 commands
            }
        elif command.startswith("cd "):
            # Change directory
            new_dir = command[3:].strip()
            if new_dir:
                session_state["working_directory"] = new_dir
                return {"type": "directory_change", "data": {"new_directory": new_dir}}
        elif command.startswith("set "):
            # Set environment variable
            try:
                var_assignment = command[4:].strip()
                if "=" in var_assignment:
                    key, value = var_assignment.split("=", 1)
                    session_state["environment"][key.strip()] = value.strip()
                    return {
                        "type": "environment_set",
                        "data": {"key": key.strip(), "value": value.strip()},
                    }
            except Exception as e:
                return {
                    "type": "error",
                    "data": {"message": f"Invalid set command: {e}"},
                }
        elif command == "env":
            return {"type": "environment", "data": session_state.get("environment", {})}
        elif command == "pwd":
            return {
                "type": "directory",
                "data": {
                    "current_directory": session_state.get("working_directory", "/")
                },
            }

        # Not a shell command, pass through
        return {"type": "passthrough", "data": {"command": command}}


class CommandRouterNode(Node):
    """Node for routing parsed commands to appropriate handlers.

    This node takes parsed commands and routes them to the correct
    workflow or handler based on command type and configuration.
    """

    def __init__(self):
        """Initialize command router node."""
        super().__init__()

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts.

        Returns:
            Dictionary of parameter definitions
        """
        return {
            "parsed_command": NodeParameter(
                name="parsed_command",
                type=dict,
                required=True,
                description="Parsed command data from CommandParserNode",
            ),
            "routing_config": NodeParameter(
                name="routing_config",
                type=dict,
                required=True,
                description="Configuration for command routing",
            ),
            "default_handler": NodeParameter(
                name="default_handler",
                type=str,
                required=False,
                default="help",
                description="Default handler for unmatched commands",
            ),
        }

    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute command routing.

        Returns:
            Dictionary containing routing decision and target information
        """
        # Get parameters
        parsed_command = kwargs.get("parsed_command", {})
        routing_config = kwargs.get("routing_config", {})
        default_handler = kwargs.get("default_handler", "help")

        try:
            # Extract command info
            if isinstance(parsed_command, ParsedCommand):
                command_type = parsed_command.command_type.value
                command_name = parsed_command.command_name
                arguments = parsed_command.arguments
                subcommand = parsed_command.subcommand
            else:
                # Handle dictionary input
                command_type = parsed_command.get("command_type", "custom")
                command_name = parsed_command.get("command_name", "unknown")
                arguments = parsed_command.get("arguments", {})
                subcommand = parsed_command.get("subcommand")

            # Find routing target
            routing_target = self._find_routing_target(
                command_type, command_name, subcommand, routing_config, default_handler
            )

            # Prepare execution parameters
            execution_params = self._prepare_execution_params(
                parsed_command, arguments, routing_target
            )

            return {
                "routing_target": routing_target,
                "execution_params": execution_params,
                "command_type": command_type,
                "command_name": command_name,
                "subcommand": subcommand,
                "success": True,
            }

        except Exception as e:
            logger.error(f"Error routing command: {e}")
            return {
                "routing_target": {"type": "error", "handler": "error"},
                "execution_params": {"error": str(e)},
                "command_type": "system",
                "command_name": "error",
                "subcommand": None,
                "success": False,
                "error": str(e),
            }

    def _find_routing_target(
        self,
        command_type: str,
        command_name: str,
        subcommand: Optional[str],
        routing_config: Dict[str, Any],
        default_handler: str,
    ) -> Dict[str, Any]:
        """Find the appropriate routing target for a command.

        Args:
            command_type: Type of command
            command_name: Name of command
            subcommand: Optional subcommand
            routing_config: Routing configuration
            default_handler: Default handler name

        Returns:
            Routing target information
        """
        # Check for exact command match first
        command_key = f"{command_name}"
        if subcommand:
            command_key += f":{subcommand}"

        if command_key in routing_config:
            return routing_config[command_key]

        # Check for command name match without subcommand
        if command_name in routing_config:
            return routing_config[command_name]

        # Check for command type routing
        type_key = f"type:{command_type}"
        if type_key in routing_config:
            return routing_config[type_key]

        # Check for pattern matching
        for pattern, target in routing_config.items():
            if pattern.startswith("pattern:"):
                pattern_str = pattern[8:]  # Remove "pattern:" prefix
                if self._match_pattern(command_name, pattern_str):
                    return target

        # Return default handler
        return {
            "type": "handler",
            "handler": default_handler,
            "description": f"Default handler for {command_name}",
        }

    def _match_pattern(self, command_name: str, pattern: str) -> bool:
        """Check if command name matches a pattern.

        Args:
            command_name: Command name to test
            pattern: Pattern to match against

        Returns:
            True if pattern matches
        """
        # Simple wildcard matching for now
        if "*" in pattern:
            import fnmatch

            return fnmatch.fnmatch(command_name, pattern)

        return command_name == pattern

    def _prepare_execution_params(
        self,
        parsed_command: Union[ParsedCommand, Dict[str, Any]],
        arguments: Dict[str, Any],
        routing_target: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Prepare parameters for execution.

        Args:
            parsed_command: Original parsed command
            arguments: Command arguments
            routing_target: Routing target information

        Returns:
            Execution parameters dictionary
        """
        # Base execution parameters
        exec_params = {"command_arguments": arguments, "routing_info": routing_target}

        # Add command data
        if isinstance(parsed_command, ParsedCommand):
            exec_params["parsed_command"] = {
                "command_type": parsed_command.command_type.value,
                "command_name": parsed_command.command_name,
                "arguments": parsed_command.arguments,
                "subcommand": parsed_command.subcommand,
                "flags": parsed_command.flags,
                "raw_command": parsed_command.raw_command,
                "error": parsed_command.error,
            }
        else:
            exec_params["parsed_command"] = parsed_command

        # Add target-specific parameters
        if routing_target.get("type") == "workflow":
            exec_params["workflow_name"] = routing_target.get("workflow")
            exec_params["workflow_inputs"] = arguments
        elif routing_target.get("type") == "handler":
            exec_params["handler_name"] = routing_target.get("handler")

        # Add any additional parameters from routing target
        additional_params = routing_target.get("parameters", {})
        exec_params.update(additional_params)

        return exec_params
