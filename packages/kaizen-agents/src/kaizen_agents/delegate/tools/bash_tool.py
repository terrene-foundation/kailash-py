"""Bash tool — execute shell commands with timeout and output capture."""

from __future__ import annotations

import subprocess
from typing import Any

from kaizen_agents.delegate.tools.base import Tool, ToolResult

# Default timeout in seconds
_DEFAULT_TIMEOUT = 120


class BashTool(Tool):
    """Execute a shell command and capture stdout + stderr.

    Includes a configurable timeout (default 120 seconds).  A
    ``permission_gate`` callback can be injected for future permission
    gating (M3-13/M3-14); when set, it is called with the command string
    before execution and must return ``True`` to proceed.
    """

    def __init__(self, *, permission_gate: Any) -> None:
        if permission_gate is None:
            raise ValueError(
                "BashTool requires a permission_gate callback. "
                "Use ExecPolicy.as_permission_gate() or provide a "
                "callable(command: str) -> bool."
            )
        self._permission_gate = permission_gate

    @property
    def name(self) -> str:
        return "bash"

    @property
    def description(self) -> str:
        return "Execute a shell command and return stdout/stderr."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["command"],
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds. Default 120.",
                },
            },
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        command: str = kwargs["command"]
        timeout: int = kwargs.get("timeout", _DEFAULT_TIMEOUT)

        # Permission gating hook point
        if self._permission_gate is not None:
            allowed = self._permission_gate(command)
            if not allowed:
                return ToolResult.failure(f"Permission denied for command: {command}")

        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return ToolResult.failure(f"Command timed out after {timeout} seconds: {command}")
        except OSError as exc:
            return ToolResult.failure(f"Error executing command: {exc}")

        output_parts: list[str] = []
        if proc.stdout:
            output_parts.append(proc.stdout)
        if proc.stderr:
            output_parts.append(proc.stderr)

        combined = "\n".join(output_parts).rstrip()

        if proc.returncode != 0:
            return ToolResult(
                output=combined,
                error=f"Command exited with code {proc.returncode}",
                is_error=True,
            )

        return ToolResult.success(combined if combined else "(no output)")
