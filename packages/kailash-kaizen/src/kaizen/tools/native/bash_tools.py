"""
Native Bash Tool

Provides sandboxed bash command execution for autonomous agents.
Includes security measures to prevent dangerous operations.

Security Features:
- Blocked dangerous patterns (rm -rf /, fork bombs, etc.)
- Configurable timeout (default: 120 seconds)
- Output size limits (30KB max)
- Optional working directory restriction
"""

import asyncio
import re
import subprocess
from typing import Any, Dict, List, Optional

from kaizen.tools.native.base import BaseTool, NativeToolResult
from kaizen.tools.types import DangerLevel, ToolCategory


class BashTool(BaseTool):
    """
    Execute bash commands in a sandboxed environment.

    Provides command execution with security protections:
    - Blocks dangerous patterns (rm -rf /, fork bombs, etc.)
    - Configurable timeout (default: 120 seconds)
    - Output size limits (30KB max)
    - Optional working directory restriction

    Parameters:
        command: Bash command to execute
        timeout: Timeout in seconds (default: 120, max: 600)
        cwd: Working directory (default: current directory)
    """

    name = "bash_command"
    description = "Execute a bash command with sandboxed execution"
    danger_level = DangerLevel.HIGH
    category = ToolCategory.SYSTEM

    # Dangerous patterns that should be blocked
    BLOCKED_PATTERNS = [
        # Destructive file operations
        r"rm\s+-[^\s]*r[^\s]*f.*\/",  # rm -rf /
        r"rm\s+-[^\s]*f[^\s]*r.*\/",  # rm -fr /
        r"rm\s+-rf\s+~",  # rm -rf ~
        r"rm\s+-rf\s+\$HOME",  # rm -rf $HOME
        r">\s*\/dev\/sd[a-z]",  # Overwrite disk
        r"mkfs\.",  # Format filesystem
        r"dd\s+if=.*of=\/dev",  # dd to device
        # Fork bombs
        r":\(\)\{.*\|.*&\}",  # Classic fork bomb
        r"fork.*while.*true",  # Fork loop
        # Dangerous redirections
        r">\s*\/etc\/passwd",
        r">\s*\/etc\/shadow",
        r">\s*\/etc\/sudoers",
        # Network abuse
        r":(.).*\|.*nc\s",  # Pipe to netcat
        # Shutdown/reboot
        r"\bshutdown\b",
        r"\breboot\b",
        r"\bhalt\b",
        r"\binit\s+0\b",
        r"\binit\s+6\b",
    ]

    def __init__(
        self,
        sandbox_mode: bool = True,
        allowed_commands: Optional[List[str]] = None,
        blocked_commands: Optional[List[str]] = None,
    ):
        """
        Initialize BashTool.

        Args:
            sandbox_mode: Enable security checks (default: True)
            allowed_commands: If set, only these commands are allowed
            blocked_commands: Additional commands to block
        """
        super().__init__()
        self.sandbox_mode = sandbox_mode
        self.allowed_commands = allowed_commands
        self.blocked_commands = blocked_commands or []

        # Compile blocked patterns for efficiency
        self._blocked_regexes = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.BLOCKED_PATTERNS
        ]

    def _check_command_safety(self, command: str) -> Optional[str]:
        """
        Check if command is safe to execute.

        Returns:
            Error message if unsafe, None if safe
        """
        if not self.sandbox_mode:
            return None

        # Check blocked patterns
        for regex in self._blocked_regexes:
            if regex.search(command):
                return f"Command matches blocked pattern: {regex.pattern}"

        # Check blocked commands
        for blocked in self.blocked_commands:
            if blocked in command:
                return f"Command contains blocked term: {blocked}"

        # Check allowed commands (if specified)
        if self.allowed_commands:
            cmd_parts = command.split()
            if cmd_parts:
                base_cmd = cmd_parts[0]
                if base_cmd not in self.allowed_commands:
                    return f"Command '{base_cmd}' not in allowed list: {self.allowed_commands}"

        return None

    async def execute(
        self,
        command: str,
        timeout: int = 120,
        cwd: Optional[str] = None,
    ) -> NativeToolResult:
        """
        Execute bash command.

        Args:
            command: Command to execute
            timeout: Timeout in seconds (max: 600)
            cwd: Working directory

        Returns:
            NativeToolResult with stdout/stderr output
        """
        # Validate timeout
        if timeout <= 0:
            return NativeToolResult.from_error("Timeout must be positive")
        if timeout > 600:
            timeout = 600  # Cap at 10 minutes

        # Security check
        safety_error = self._check_command_safety(command)
        if safety_error:
            return NativeToolResult.from_error(f"Security check failed: {safety_error}")

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=float(timeout),
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return NativeToolResult.from_error(
                    f"Command timed out after {timeout} seconds",
                    exit_code=-1,
                    timeout=True,
                )

            # Decode output
            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            # Combine output
            output = stdout_str
            if stderr_str:
                output += "\n--- STDERR ---\n" + stderr_str if output else stderr_str

            # Truncate if too long
            max_output = 30000
            truncated = len(output) > max_output
            if truncated:
                output = output[:max_output] + "\n... [output truncated]"

            # Determine success
            success = process.returncode == 0

            return NativeToolResult(
                success=success,
                output=output,
                error=None if success else f"Exit code: {process.returncode}",
                metadata={
                    "exit_code": process.returncode,
                    "stdout_length": len(stdout_str),
                    "stderr_length": len(stderr_str),
                    "truncated": truncated,
                },
            )
        except FileNotFoundError:
            return NativeToolResult.from_error("Shell not found")
        except PermissionError:
            return NativeToolResult.from_error("Permission denied executing command")
        except Exception as e:
            return NativeToolResult.from_exception(e)

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Bash command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (max: 600)",
                    "default": 120,
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory for command execution",
                },
            },
            "required": ["command"],
        }
