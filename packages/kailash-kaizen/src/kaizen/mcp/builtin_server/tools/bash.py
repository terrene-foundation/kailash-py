"""
Bash Tools for MCP - Shell Command Execution

Provides 1 MCP tool for bash operations:
- bash_command: Execute shell commands in subprocess

⚠️ SECURITY WARNING ⚠️
======================
This tool uses shell=True and is vulnerable to command injection attacks!

**Command Injection Risk:**
- User input MUST be sanitized before being passed to bash_command
- Malicious input can execute arbitrary commands
- HIGH danger level requires approval workflow protection

**Protection Layers:**
1. HIGH danger level → Requires approval workflow (handled by BaseAgent)
2. User review of command before execution
3. Timeout protection (default 30s, max configurable)
4. Working directory isolation (optional)

All tools use @tool decorator for MCP compliance.
"""

import subprocess
from typing import Optional

from kaizen.mcp.builtin_server.decorators import mcp_tool

# =============================================================================
# MCP Tools (1 total)
# =============================================================================


@mcp_tool(
    name="bash_command",
    description="Execute a shell command in a subprocess (HIGH DANGER: requires approval)",
    parameters={
        "command": {"type": "string", "description": "Shell command to execute"},
        "timeout": {
            "type": "integer",
            "description": "Command timeout in seconds (default 30)",
        },
        "working_dir": {
            "type": "string",
            "description": "Working directory for command execution",
        },
    },
)
async def bash_command(
    command: str, timeout: int = 30, working_dir: Optional[str] = None
) -> dict:
    """
    Execute a bash command in a subprocess (MCP tool implementation).

    ⚠️ SECURITY WARNING: This function uses shell=True which is vulnerable to
    command injection attacks. User input MUST be sanitized before being
    passed to this function. Use shlex.quote() to escape user input.

    The HIGH danger level classification requires approval workflow, which
    provides a critical security layer by allowing human review before execution.

    Args:
        command: Shell command to execute (MUST be sanitized!)
        timeout: Command timeout in seconds (default 30)
        working_dir: Working directory for command execution (optional)

    Returns:
        Dictionary with:
            - stdout (str): Standard output from command
            - stderr (str): Standard error from command
            - exit_code (int): Process exit code
            - success (bool): True if exit_code == 0
            - error (str, optional): Error message if command failed/timed out

    Security Notes:
        - Command injection risk: Malicious commands can be injected via unsanitized input
        - Privilege escalation: Commands run with same privileges as Python process
        - File system access: Commands have full access to file system (within permissions)
        - Network access: Commands can make network requests
        - Resource consumption: Commands can consume CPU/memory/disk

    Example (SAFE):
        >>> import shlex
        >>> user_file = shlex.quote(user_input)  # Escape special characters
        >>> result = await bash_command(command=f"cat {user_file}")

    Example (UNSAFE - DO NOT USE):
        >>> # UNSAFE: Direct user input can execute arbitrary commands!
        >>> result = await bash_command(command=f"cat {user_input}")  # DANGER!
    """
    try:
        # SECURITY WARNING: shell=True enables command injection attacks!
        # This is inherently dangerous but necessary for shell features (pipes, wildcards, etc.)
        # HIGH danger level + approval workflow provides critical protection layer.
        # User input MUST be sanitized before reaching this function (use shlex.quote()).
        result = subprocess.run(
            command,
            shell=True,  # WARNING: Enables command injection! Protected by approval workflow.
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=working_dir,
        )

        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "success": result.returncode == 0,
        }

    except subprocess.TimeoutExpired as e:
        return {
            "stdout": e.stdout.decode() if e.stdout else "",
            "stderr": e.stderr.decode() if e.stderr else "",
            "exit_code": -1,
            "success": False,
            "error": f"Command timed out after {timeout}s",
        }

    except Exception as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1,
            "success": False,
            "error": str(e),
        }
