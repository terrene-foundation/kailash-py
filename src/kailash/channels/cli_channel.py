"""CLI Channel implementation for interactive command-line interface."""

import asyncio
import logging
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TextIO

from ..nodes.system.command_parser import (
    CommandParserNode,
    CommandRouterNode,
    InteractiveShellNode,
    ParsedCommand,
)
from ..runtime.local import LocalRuntime
from ..workflow.builder import WorkflowBuilder
from .base import (
    Channel,
    ChannelConfig,
    ChannelEvent,
    ChannelResponse,
    ChannelStatus,
    ChannelType,
)

logger = logging.getLogger(__name__)


@dataclass
class CLISession:
    """Represents a CLI session."""

    session_id: str
    user_id: Optional[str] = None
    shell_state: Dict[str, Any] = field(default_factory=dict)
    command_history: List[str] = field(default_factory=list)
    active: bool = True
    last_command_time: Optional[float] = None


class CLIChannel(Channel):
    """Command-line interface channel implementation.

    This channel provides an interactive CLI interface for executing workflows
    and managing the Kailash system through command-line commands.
    """

    def __init__(
        self,
        config: ChannelConfig,
        input_stream: Optional[TextIO] = None,
        output_stream: Optional[TextIO] = None,
    ):
        """Initialize CLI channel.

        Args:
            config: Channel configuration
            input_stream: Input stream (defaults to sys.stdin)
            output_stream: Output stream (defaults to sys.stdout)
        """
        super().__init__(config)

        self.input_stream = input_stream or sys.stdin
        self.output_stream = output_stream or sys.stdout

        # CLI-specific components
        self.command_parser = CommandParserNode()
        self.shell_node = InteractiveShellNode()
        self.router_node = CommandRouterNode()

        # Session management
        self._sessions: Dict[str, CLISession] = {}
        self._current_session: Optional[CLISession] = None

        # Command definitions and routing
        self._command_definitions = self._setup_default_commands()
        self._routing_config = self._setup_default_routing()

        # Runtime for executing workflows
        self.runtime = LocalRuntime()

        # CLI state
        self._running = False
        self._main_task: Optional[asyncio.Task] = None

        logger.info(f"Initialized CLI channel {self.name}")

    def _setup_default_commands(self) -> Dict[str, Any]:
        """Set up default command definitions."""
        return {
            "run": {
                "type": "workflow",
                "description": "Execute a workflow",
                "arguments": {
                    "workflow": {
                        "flags": ["workflow", "--workflow", "-w"],
                        "type": str,
                        "required": True,
                        "help": "Name of the workflow to execute",
                    },
                    "input": {
                        "flags": ["--input", "-i"],
                        "type": str,
                        "required": False,
                        "help": "JSON string of input parameters",
                    },
                    "file": {
                        "flags": ["--file", "-f"],
                        "type": str,
                        "required": False,
                        "help": "File path containing input parameters",
                    },
                },
            },
            "list": {
                "type": "system",
                "description": "List available items",
                "subcommands": {
                    "workflows": {
                        "help": "List available workflows",
                        "arguments": {
                            "verbose": {
                                "flags": ["--verbose", "-v"],
                                "action": "store_true",
                                "help": "Show detailed information",
                            }
                        },
                    },
                    "sessions": {"help": "List active sessions", "arguments": {}},
                },
            },
            "status": {
                "type": "system",
                "description": "Show system status",
                "arguments": {
                    "verbose": {
                        "flags": ["--verbose", "-v"],
                        "action": "store_true",
                        "help": "Show detailed status",
                    }
                },
            },
            "config": {
                "type": "admin",
                "description": "Manage configuration",
                "subcommands": {
                    "show": {"help": "Show current configuration", "arguments": {}},
                    "set": {
                        "help": "Set configuration value",
                        "arguments": {
                            "key": {
                                "flags": ["key"],
                                "type": str,
                                "required": True,
                                "help": "Configuration key",
                            },
                            "value": {
                                "flags": ["value"],
                                "type": str,
                                "required": True,
                                "help": "Configuration value",
                            },
                        },
                    },
                },
            },
        }

    def _setup_default_routing(self) -> Dict[str, Any]:
        """Set up default command routing configuration."""
        return {
            "run": {
                "type": "workflow_executor",
                "handler": "execute_workflow",
                "description": "Execute workflow command",
            },
            "list:workflows": {
                "type": "handler",
                "handler": "list_workflows",
                "description": "List available workflows",
            },
            "list:sessions": {
                "type": "handler",
                "handler": "list_sessions",
                "description": "List active sessions",
            },
            "status": {
                "type": "handler",
                "handler": "show_status",
                "description": "Show system status",
            },
            "config:show": {
                "type": "handler",
                "handler": "show_config",
                "description": "Show configuration",
            },
            "config:set": {
                "type": "handler",
                "handler": "set_config",
                "description": "Set configuration",
            },
            "help": {
                "type": "handler",
                "handler": "show_help",
                "description": "Show help information",
            },
            "exit": {
                "type": "handler",
                "handler": "exit_cli",
                "description": "Exit CLI",
            },
            "quit": {
                "type": "handler",
                "handler": "exit_cli",
                "description": "Exit CLI",
            },
            "type:workflow": {
                "type": "handler",
                "handler": "handle_unknown_workflow",
                "description": "Handle unknown workflow commands",
            },
        }

    async def start(self) -> None:
        """Start the CLI channel."""
        if self.status == ChannelStatus.RUNNING:
            logger.warning(f"CLI channel {self.name} is already running")
            return

        try:
            self.status = ChannelStatus.STARTING
            self._setup_event_queue()

            # Create default session
            default_session = CLISession(session_id="default", user_id="cli_user")
            self._sessions["default"] = default_session
            self._current_session = default_session

            self._running = True

            # Start main CLI loop
            self._main_task = asyncio.create_task(self._cli_loop())

            self.status = ChannelStatus.RUNNING

            # Emit startup event
            await self.emit_event(
                ChannelEvent(
                    event_id=f"cli_startup_{asyncio.get_event_loop().time()}",
                    channel_name=self.name,
                    channel_type=self.channel_type,
                    event_type="channel_started",
                    payload={"session_count": len(self._sessions)},
                )
            )

            logger.info(f"CLI channel {self.name} started")

        except Exception as e:
            self.status = ChannelStatus.ERROR
            logger.error(f"Failed to start CLI channel {self.name}: {e}")
            raise

    async def stop(self) -> None:
        """Stop the CLI channel."""
        if self.status == ChannelStatus.STOPPED:
            return

        try:
            self.status = ChannelStatus.STOPPING
            self._running = False

            # Emit shutdown event
            await self.emit_event(
                ChannelEvent(
                    event_id=f"cli_shutdown_{asyncio.get_event_loop().time()}",
                    channel_name=self.name,
                    channel_type=self.channel_type,
                    event_type="channel_stopping",
                    payload={},
                )
            )

            # Cancel main task
            if self._main_task and not self._main_task.done():
                self._main_task.cancel()
                try:
                    await self._main_task
                except asyncio.CancelledError:
                    pass

            await self._cleanup()
            self.status = ChannelStatus.STOPPED

            logger.info(f"CLI channel {self.name} stopped")

        except Exception as e:
            self.status = ChannelStatus.ERROR
            logger.error(f"Error stopping CLI channel {self.name}: {e}")
            raise

    async def handle_request(self, request: Dict[str, Any]) -> ChannelResponse:
        """Handle a CLI request.

        Args:
            request: Request data containing command information

        Returns:
            ChannelResponse with command execution results
        """
        try:
            command_input = request.get("command", "")
            session_id = request.get("session_id", "default")

            # Get or create session
            session = self._sessions.get(session_id)
            if not session:
                session = CLISession(session_id=session_id)
                self._sessions[session_id] = session

            # Process command through parsing pipeline
            result = await self._process_command(command_input, session)

            return ChannelResponse(
                success=True,
                data=result,
                metadata={"channel": self.name, "session_id": session_id},
            )

        except Exception as e:
            logger.error(f"Error handling CLI request: {e}")
            return ChannelResponse(
                success=False, error=str(e), metadata={"channel": self.name}
            )

    async def _cli_loop(self) -> None:
        """Main CLI interaction loop."""
        self._write_output("Kailash CLI started. Type 'help' for available commands.\n")

        while self._running:
            try:
                # Generate prompt
                prompt = await self._generate_prompt()
                self._write_output(prompt)

                # Read command (this would be blocking in real implementation)
                # For now, we'll simulate with a small delay
                await asyncio.sleep(0.1)

                # In a real implementation, this would read from input_stream
                # For testing/simulation purposes, we'll break here
                if not self.config.extra_config.get("interactive_mode", False):
                    break

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in CLI loop: {e}")
                self._write_output(f"Error: {e}\n")

    async def _generate_prompt(self) -> str:
        """Generate CLI prompt."""
        if not self._current_session:
            return "kailash> "

        # Use shell node to generate prompt
        shell_result = self.shell_node.execute(
            session_id=self._current_session.session_id,
            command_input="",  # Empty for prompt generation
            session_state=self._current_session.shell_state,
            prompt_template=self.config.extra_config.get(
                "prompt_template", "kailash> "
            ),
        )

        return shell_result.get("prompt", "kailash> ")

    async def _process_command(
        self, command_input: str, session: CLISession
    ) -> Dict[str, Any]:
        """Process a command through the parsing and routing pipeline.

        Args:
            command_input: Raw command input
            session: CLI session

        Returns:
            Command processing results
        """
        try:
            # Update session
            session.command_history.append(command_input)
            session.last_command_time = asyncio.get_event_loop().time()

            # Parse command
            parse_result = self.command_parser.execute(
                command_input=command_input,
                command_definitions=self._command_definitions,
                allow_unknown_commands=True,
                default_command_type="workflow",
            )

            if not parse_result["success"]:
                return {
                    "type": "error",
                    "message": parse_result.get("error", "Failed to parse command"),
                    "command": command_input,
                }

            # Process through shell node
            shell_result = self.shell_node.execute(
                session_id=session.session_id,
                command_input=command_input,
                session_state=session.shell_state,
            )

            # Check if shell handled the command
            if shell_result["shell_result"]["type"] != "passthrough":
                return {
                    "type": "shell_command",
                    "result": shell_result["shell_result"],
                    "session_state": shell_result["session_state"],
                }

            # Route command
            router_result = self.router_node.execute(
                parsed_command=parse_result["parsed_command"],
                routing_config=self._routing_config,
                default_handler="help",
            )

            if not router_result["success"]:
                return {
                    "type": "error",
                    "message": router_result.get("error", "Failed to route command"),
                    "command": command_input,
                }

            # Execute routed command
            execution_result = await self._execute_routed_command(
                router_result["routing_target"],
                router_result["execution_params"],
                session,
            )

            return {
                "type": "command_execution",
                "parse_result": parse_result,
                "routing_result": router_result,
                "execution_result": execution_result,
                "session_id": session.session_id,
            }

        except Exception as e:
            logger.error(f"Error processing command: {e}")
            return {"type": "error", "message": str(e), "command": command_input}

    async def _execute_routed_command(
        self,
        routing_target: Dict[str, Any],
        execution_params: Dict[str, Any],
        session: CLISession,
    ) -> Dict[str, Any]:
        """Execute a routed command.

        Args:
            routing_target: Routing target information
            execution_params: Execution parameters
            session: CLI session

        Returns:
            Execution results
        """
        handler_name = routing_target.get("handler")
        target_type = routing_target.get("type")

        try:
            if target_type == "workflow_executor":
                return await self._execute_workflow_command(execution_params)
            elif target_type == "handler":
                return await self._execute_handler_command(
                    handler_name, execution_params, session
                )
            else:
                return {
                    "success": False,
                    "error": f"Unknown target type: {target_type}",
                }

        except Exception as e:
            logger.error(f"Error executing routed command: {e}")
            return {"success": False, "error": str(e)}

    async def _execute_workflow_command(
        self, execution_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a workflow command.

        Args:
            execution_params: Execution parameters

        Returns:
            Workflow execution results
        """
        # This would integrate with the workflow execution system
        # For now, return a placeholder
        return {
            "success": True,
            "message": "Workflow execution not yet implemented in CLI channel",
            "params": execution_params,
        }

    async def _execute_handler_command(
        self, handler_name: str, execution_params: Dict[str, Any], session: CLISession
    ) -> Dict[str, Any]:
        """Execute a handler command.

        Args:
            handler_name: Name of the handler
            execution_params: Execution parameters
            session: CLI session

        Returns:
            Handler execution results
        """
        if handler_name == "show_help":
            return await self._handle_help(execution_params)
        elif handler_name == "show_status":
            return await self._handle_status(execution_params)
        elif handler_name == "list_workflows":
            return await self._handle_list_workflows(execution_params)
        elif handler_name == "list_sessions":
            return await self._handle_list_sessions(execution_params)
        elif handler_name == "exit_cli":
            return await self._handle_exit(execution_params, session)
        else:
            return {"success": False, "error": f"Unknown handler: {handler_name}"}

    async def _handle_help(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle help command."""
        topic = params.get("command_arguments", {}).get("topic")

        if topic and topic in self._command_definitions:
            cmd_def = self._command_definitions[topic]
            help_text = f"{topic}: {cmd_def.get('description', 'No description')}\n"

            # Add argument information
            arguments = cmd_def.get("arguments", {})
            if arguments:
                help_text += "Arguments:\n"
                for arg_name, arg_config in arguments.items():
                    flags = ", ".join(arg_config.get("flags", [f"--{arg_name}"]))
                    help_desc = arg_config.get("help", "No description")
                    help_text += f"  {flags}: {help_desc}\n"

            # Add subcommands
            subcommands = cmd_def.get("subcommands", {})
            if subcommands:
                help_text += "Subcommands:\n"
                for sub_name, sub_config in subcommands.items():
                    help_desc = sub_config.get("help", "No description")
                    help_text += f"  {sub_name}: {help_desc}\n"
        else:
            # General help
            help_text = "Available commands:\n"
            for cmd_name, cmd_def in self._command_definitions.items():
                description = cmd_def.get("description", "No description")
                help_text += f"  {cmd_name}: {description}\n"

            help_text += "\nType 'help <command>' for detailed information about a specific command.\n"

        return {"success": True, "message": help_text.strip()}

    async def _handle_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle status command."""
        verbose = params.get("command_arguments", {}).get("verbose", False)

        status_info = {
            "channel": self.name,
            "status": self.status.value,
            "sessions": len(self._sessions),
            "active_sessions": len([s for s in self._sessions.values() if s.active]),
        }

        if verbose:
            status_info.update(await self.get_status())

        return {"success": True, "data": status_info}

    async def _handle_list_workflows(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle list workflows command."""
        # This would integrate with workflow registry
        return {
            "success": True,
            "message": "Workflow listing not yet implemented",
            "workflows": [],
        }

    async def _handle_list_sessions(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle list sessions command."""
        sessions_info = []
        for session_id, session in self._sessions.items():
            sessions_info.append(
                {
                    "session_id": session_id,
                    "user_id": session.user_id,
                    "active": session.active,
                    "command_count": len(session.command_history),
                    "last_command_time": session.last_command_time,
                }
            )

        return {"success": True, "data": {"sessions": sessions_info}}

    async def _handle_exit(
        self, params: Dict[str, Any], session: CLISession
    ) -> Dict[str, Any]:
        """Handle exit command."""
        force = params.get("command_arguments", {}).get("force", False)

        if force or len(self._sessions) == 1:
            # Stop the entire CLI
            asyncio.create_task(self.stop())
            return {"success": True, "message": "Exiting CLI..."}
        else:
            # Just deactivate current session
            session.active = False
            return {
                "success": True,
                "message": f"Session {session.session_id} deactivated",
            }

    def _write_output(self, text: str) -> None:
        """Write text to output stream."""
        if self.output_stream:
            self.output_stream.write(text)
            self.output_stream.flush()

    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check."""
        base_health = await super().health_check()

        # Add CLI-specific health checks
        cli_checks = {
            "sessions_active": len([s for s in self._sessions.values() if s.active])
            > 0,
            "command_parser_ready": self.command_parser is not None,
            "routing_configured": len(self._routing_config) > 0,
            "runtime_available": self.runtime is not None,
        }

        all_healthy = base_health["healthy"] and all(cli_checks.values())

        return {
            **base_health,
            "healthy": all_healthy,
            "checks": {**base_health["checks"], **cli_checks},
            "sessions": len(self._sessions),
            "active_sessions": len([s for s in self._sessions.values() if s.active]),
            "commands_available": len(self._command_definitions),
        }
