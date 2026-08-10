"""Bash tool — execute shell commands with timeout and output capture."""

from __future__ import annotations

import subprocess
from typing import Any

from kaizen.utils.credential_scrub import scrub_remote_error
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
                # SCRUBBED. `command` is a REQUIRED field of this tool's own
                # `parameters_schema`, so it arrives verbatim from a model tool
                # call — remote-derived by construction, and the REMOTE preset
                # is what claims the prefix-less shapes (a bare AWS secret, a
                # bare 32+ hex Azure api-key) the conservative one lets
                # through. The sibling `OSError` branch below was already
                # routed this way, so this is closing a partial sweep rather
                # than establishing a new contract.
                #
                # This branch is the sharpest of the three: the gate REFUSED to
                # run the command, and the refusal itself then disclosed the
                # credential the command carried.
                return ToolResult.failure(
                    f"Permission denied for command: {scrub_remote_error(command)}"
                )

        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            # Same operand, same preset, same reason as the denial branch.
            return ToolResult.failure(
                f"Command timed out after {timeout} seconds: "
                f"{scrub_remote_error(command)}"
            )
        except OSError as exc:
            return ToolResult.failure(
                f"Error executing command: {scrub_remote_error(exc)}"
            )

        # NAMED CARVE-OUT — stdout/stderr are NOT scrubbed, and that is a
        # decision rather than the same partial sweep the two branches above
        # were. Recorded here so the next audit does not re-open it.
        #
        # The three error branches interpolate the command as CONTEXT the
        # caller did not ask for; a credential reaching them is INCIDENTAL,
        # which is the disclosure class this issue exists to close. Command
        # output is the opposite: it is the payload the agent explicitly
        # requested, and this tool's whole contract is to return it verbatim.
        #
        # Scrubbing it would be a large functional break for no security gain:
        # `redact_opaque_tokens` claims any 32+ hex run, so `git rev-parse
        # HEAD`, `sha256sum`, `openssl rand -hex 32`, `uuidgen`, and every
        # image digest would come back blanked — the same reasoning that makes
        # `scrub_remote_error`'s filesystem-path carve-out a carve-out.
        #
        # And there is nothing to protect: an actor able to reach this tool
        # already holds arbitrary shell execution under the process's own
        # credentials, so it is inside the trust boundary by construction. The
        # control for that is the `permission_gate` above (which is mandatory —
        # see `__init__`), not a scrub of the results.
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
