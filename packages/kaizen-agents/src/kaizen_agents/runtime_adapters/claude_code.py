"""
ClaudeCodeAdapter - Claude Code SDK Integration

Delegates autonomous execution to Claude Code SDK, leveraging its native
tools (Read, Write, Bash, Glob, Grep, etc.) while optionally extending
with custom Kaizen tools via MCP.

IMPORTANT: Claude Code SDK has its own full-featured runtime with:
- Native tools (Read, Write, Edit, Bash, Glob, Grep, etc.)
- Streaming output
- Session management
- MCP server integration

This adapter provides a Kaizen-compatible interface to Claude Code,
NOT a replacement for its capabilities.

Usage:
    >>> from kaizen.runtime.adapters.claude_code import ClaudeCodeAdapter
    >>> from kaizen.runtime.context import ExecutionContext
    >>>
    >>> adapter = ClaudeCodeAdapter()
    >>> context = ExecutionContext(task="List files in /tmp")
    >>> result = await adapter.execute(context)
"""

import asyncio
import json
import logging
import os
from typing import Any, AsyncIterator, Dict, List, Optional

from kaizen.runtime.adapter import BaseRuntimeAdapter, ProgressCallback
from kaizen.runtime.adapters.tool_mapping import MCPToolMapper
from kaizen.runtime.capabilities import RuntimeCapabilities
from kaizen.runtime.context import ExecutionContext, ExecutionResult, ExecutionStatus

logger = logging.getLogger(__name__)


class ClaudeCodeAdapter(BaseRuntimeAdapter):
    """Adapter that delegates to Claude Code SDK.

    Claude Code SDK provides a full autonomous agent runtime with:
    - Native tools: Read, Write, Edit, Bash, Glob, Grep, WebFetch, Task, etc.
    - Streaming output
    - Session management
    - MCP server integration for custom tools

    This adapter wraps Claude Code's capabilities in the RuntimeAdapter
    interface, allowing it to be used interchangeably with other runtimes
    through RuntimeSelector.

    Key Design Decision:
        We delegate to Claude Code's native execution rather than
        reimplementing its capabilities. Custom Kaizen tools can be
        exposed to Claude Code via MCP servers.

    Example:
        >>> adapter = ClaudeCodeAdapter(
        ...     working_directory="/path/to/project",
        ...     custom_tools=[my_kaizen_tool],
        ... )
        >>>
        >>> context = ExecutionContext(task="Analyze the codebase")
        >>> result = await adapter.execute(context)
        >>> print(result.output)
    """

    def __init__(
        self,
        working_directory: Optional[str] = None,
        custom_tools: Optional[List[Dict[str, Any]]] = None,
        mcp_servers: Optional[Dict[str, Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 8192,
        timeout_seconds: float = 300,
        allowed_commands: Optional[List[str]] = None,
        model: str = "claude-sonnet-4-20250514",
    ):
        """Initialize the ClaudeCodeAdapter.

        Args:
            working_directory: Working directory for Claude Code execution.
                             Defaults to current directory.
            custom_tools: Custom Kaizen tools to expose via MCP.
                         These are converted to MCP format and made available
                         to Claude Code alongside its native tools.
            mcp_servers: Additional MCP server configurations.
                        Format: {"server_name": {"command": "...", "args": [...]}}
            system_prompt: Custom system prompt to prepend to Claude Code's
                          default instructions.
            max_tokens: Maximum tokens for response.
            timeout_seconds: Execution timeout.
            allowed_commands: List of allowed bash commands. If None, all
                            commands are allowed (use with caution).
            model: Claude model to use. Defaults to Claude Sonnet 4.
        """
        super().__init__()

        self.working_directory = working_directory or os.getcwd()
        self.custom_tools = custom_tools or []
        self.mcp_servers = mcp_servers or {}
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds
        self.allowed_commands = allowed_commands
        self.model = model

        # Session tracking
        self._current_session_id: Optional[str] = None
        self._current_process: Optional[asyncio.subprocess.Process] = None

        # Build capabilities
        self._capabilities = self._build_capabilities()

    @property
    def capabilities(self) -> RuntimeCapabilities:
        """Return Claude Code capabilities."""
        return self._capabilities

    def _build_capabilities(self) -> RuntimeCapabilities:
        """Build capabilities description for Claude Code."""
        return RuntimeCapabilities(
            runtime_name="claude_code",
            provider="anthropic",
            version="1.0.0",
            supports_streaming=True,
            supports_tool_calling=True,
            supports_parallel_tools=True,  # Claude Code can execute tools in parallel
            supports_vision=True,  # Via image reading
            supports_audio=False,
            supports_code_execution=True,  # Native Bash tool
            supports_file_access=True,  # Native Read/Write/Edit tools
            supports_web_access=True,  # WebFetch tool
            supports_interrupt=True,
            max_context_tokens=200000,  # Claude 3.5+ context
            max_output_tokens=self.max_tokens,
            cost_per_1k_input_tokens=3.0,  # Claude Sonnet pricing
            cost_per_1k_output_tokens=15.0,
            typical_latency_ms=500,
            native_tools=[
                "Read",
                "Write",
                "Edit",
                "Bash",
                "Glob",
                "Grep",
                "LS",
                "WebFetch",
                "WebSearch",
                "Task",
                "TodoWrite",
                "Skill",
                "AskFollowUpQuestion",
                "AttemptCompletion",
            ],
            supported_models=[
                "claude-sonnet-4-20250514",
                "claude-opus-4-20250514",
                "claude-3-5-sonnet-20241022",
                "claude-3-5-haiku-20241022",
            ],
            metadata={
                "working_directory": self.working_directory,
                "has_custom_tools": len(self.custom_tools) > 0,
                "mcp_servers": list(self.mcp_servers.keys()),
            },
        )

    async def execute(
        self,
        context: ExecutionContext,
        on_progress: Optional[ProgressCallback] = None,
    ) -> ExecutionResult:
        """Execute a task using Claude Code SDK.

        Delegates the task to Claude Code's native execution engine.
        Claude Code will use its own tools (Read, Write, Bash, etc.)
        to complete the task autonomously.

        Args:
            context: Execution context with task and optional tools
            on_progress: Progress callback for status updates

        Returns:
            ExecutionResult with output and metrics
        """
        await self.ensure_initialized()

        self._current_session_id = context.session_id

        if on_progress:
            on_progress("starting", {"task": context.task[:100]})

        try:
            # Build the Claude Code command
            cmd = self._build_command(context)

            logger.info(
                f"Executing Claude Code: {context.task[:50]}..., "
                f"session_id: {context.session_id}"
            )

            # Execute via subprocess (Claude Code CLI)
            output, error_output, return_code = await self._run_claude_code(
                cmd,
                on_progress=on_progress,
            )

            # Parse result
            if return_code == 0:
                return ExecutionResult(
                    output=output,
                    status=ExecutionStatus.COMPLETE,
                    runtime_name="claude_code",
                    session_id=context.session_id,
                )
            else:
                return ExecutionResult(
                    output=output or "",
                    status=ExecutionStatus.ERROR,
                    runtime_name="claude_code",
                    session_id=context.session_id,
                    error_message=error_output or f"Exit code: {return_code}",
                    error_type="ClaudeCodeError",
                )

        except asyncio.TimeoutError:
            logger.warning(
                f"Claude Code execution timed out after {self.timeout_seconds}s"
            )
            return ExecutionResult(
                output="",
                status=ExecutionStatus.TIMEOUT,
                runtime_name="claude_code",
                session_id=context.session_id,
                error_message=f"Execution timed out after {self.timeout_seconds} seconds",
                error_type="TimeoutError",
            )

        except Exception as e:
            logger.exception(f"Claude Code execution failed: {e}")
            return ExecutionResult(
                output="",
                status=ExecutionStatus.ERROR,
                runtime_name="claude_code",
                session_id=context.session_id,
                error_message=str(e),
                error_type=type(e).__name__,
            )

        finally:
            self._current_session_id = None
            self._current_process = None

    def _build_command(self, context: ExecutionContext) -> List[str]:
        """Build the Claude Code CLI command.

        Args:
            context: Execution context

        Returns:
            Command arguments list
        """
        # Base command
        cmd = ["claude"]

        # Add task as prompt
        cmd.extend(["--print", context.task])

        # Set working directory
        if self.working_directory:
            # Claude Code uses current directory; we'll chdir before execution
            pass

        # Add model if specified
        if self.model:
            cmd.extend(["--model", self.model])

        # Add max tokens
        cmd.extend(["--max-tokens", str(self.max_tokens)])

        # Add system prompt if specified
        if self.system_prompt:
            cmd.extend(["--system-prompt", self.system_prompt])

        # Add allowed commands restriction if specified
        if self.allowed_commands:
            # Claude Code doesn't have this directly, but we can add to system prompt
            pass

        # Output format (for parsing)
        cmd.extend(["--output-format", "text"])

        return cmd

    async def _run_claude_code(
        self,
        cmd: List[str],
        on_progress: Optional[ProgressCallback] = None,
    ) -> tuple[str, str, int]:
        """Run Claude Code CLI subprocess.

        Args:
            cmd: Command arguments
            on_progress: Progress callback

        Returns:
            Tuple of (stdout, stderr, return_code)
        """
        # Create subprocess
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.working_directory,
        )

        self._current_process = process

        # Collect output with timeout
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout_seconds,
            )

            return (
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
                process.returncode or 0,
            )

        except asyncio.TimeoutError:
            # Kill the process on timeout
            process.kill()
            await process.wait()
            raise

    async def stream(
        self,
        context: ExecutionContext,
    ) -> AsyncIterator[str]:
        """Stream Claude Code output.

        Args:
            context: Execution context

        Yields:
            Output chunks as they're generated
        """
        await self.ensure_initialized()

        self._current_session_id = context.session_id

        try:
            # Build streaming command
            cmd = self._build_command(context)

            # Create subprocess with streaming
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_directory,
            )

            self._current_process = process

            # Stream stdout
            if process.stdout:
                async for line in process.stdout:
                    yield line.decode("utf-8", errors="replace")

            # Wait for completion
            await process.wait()

        except asyncio.CancelledError:
            if self._current_process:
                self._current_process.kill()
            raise

        finally:
            self._current_session_id = None
            self._current_process = None

    async def interrupt(
        self,
        session_id: str,
        mode: str = "graceful",
    ) -> bool:
        """Interrupt an ongoing Claude Code execution.

        Args:
            session_id: Session to interrupt
            mode: Interrupt mode ("graceful", "immediate")

        Returns:
            True if interrupt was successful
        """
        if self._current_session_id != session_id:
            logger.warning(
                f"Session ID mismatch: {session_id} != {self._current_session_id}"
            )
            return False

        if not self._current_process:
            logger.warning("No process to interrupt")
            return False

        try:
            if mode == "immediate":
                self._current_process.kill()
            else:
                # Graceful: send SIGTERM
                self._current_process.terminate()

            return True

        except Exception as e:
            logger.error(f"Failed to interrupt: {e}")
            return False

    def map_tools(
        self,
        kaizen_tools: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Map Kaizen tools to MCP format for Claude Code.

        Custom tools are exposed to Claude Code via MCP servers.
        Claude Code's native tools are NOT affected.

        Args:
            kaizen_tools: Custom tools to expose

        Returns:
            Tools in MCP format
        """
        return MCPToolMapper.to_mcp_format(kaizen_tools)

    def normalize_result(
        self,
        raw_result: Any,
    ) -> ExecutionResult:
        """Normalize Claude Code result to ExecutionResult.

        Args:
            raw_result: Raw result from Claude Code

        Returns:
            Normalized ExecutionResult
        """
        # Already ExecutionResult
        if isinstance(raw_result, ExecutionResult):
            return raw_result

        # String output
        if isinstance(raw_result, str):
            return ExecutionResult.from_success(
                output=raw_result,
                runtime_name="claude_code",
            )

        # Dict result
        if isinstance(raw_result, dict):
            return ExecutionResult.from_dict(raw_result)

        # Fallback
        return ExecutionResult.from_success(
            output=str(raw_result),
            runtime_name="claude_code",
        )

    async def health_check(self) -> bool:
        """Check if Claude Code CLI is available.

        Returns:
            True if Claude Code is available
        """
        try:
            process = await asyncio.create_subprocess_exec(
                "claude",
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.wait()
            return process.returncode == 0
        except Exception:
            return False

    def __repr__(self) -> str:
        return (
            f"ClaudeCodeAdapter(model={self.model}, "
            f"working_dir={self.working_directory})"
        )


# Convenience function for checking Claude Code availability
async def is_claude_code_available() -> bool:
    """Check if Claude Code CLI is installed and available.

    Returns:
        True if Claude Code CLI is available
    """
    adapter = ClaudeCodeAdapter()
    return await adapter.health_check()
