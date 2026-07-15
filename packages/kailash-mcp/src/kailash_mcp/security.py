# Copyright 2026 Terrene Foundation
"""Local-server spawn safety — fail-closed command allowlist.

Per the MCP specification (revision 2025-11-25) local-server spawn safety
requirement: the command allowlist for spawning local MCP servers MUST fail
closed by default — an unlisted command is REJECTED, never warn-and-allowed.

A caller that spawns a local MCP server passes an untrusted ``command`` string
(often sourced from agent output, a config file, or a discovery response).
Spawning an arbitrary command is remote-code-execution by construction; the
fail-closed allowlist is the structural defense.

Design
------
* A curated :data:`DEFAULT_ALLOWED_MCP_COMMANDS` set of the standard MCP
  launcher executables ships as the default. An attacker-injected ``sh`` /
  ``bash`` / ``rm`` / ``curl`` / absolute-path binary is NOT in the set and is
  rejected fail-closed, while the ordinary launchers work out of the box.
* A caller MAY narrow or extend the set with ``allowed_commands``.
* A caller MAY opt OUT of the allowlist entirely with
  ``allow_arbitrary=True`` — an explicit, auditable escape hatch (never the
  default, never a silent warn-and-allow).
"""

from __future__ import annotations

import os
from typing import Optional, Sequence

from kailash_mcp.errors import MCPError, MCPErrorCode

# Standard MCP launcher executables considered safe to spawn without an
# explicit per-caller allowlist. Deliberately EXCLUDES shells (``sh``,
# ``bash``, ``zsh``, ``cmd``, ``powershell``) and generic download/exec tools
# (``curl``, ``wget``) — those are the arbitrary-command-injection vectors the
# fail-closed default exists to reject.
DEFAULT_ALLOWED_MCP_COMMANDS = frozenset(
    {
        "python",
        "python3",
        "uv",
        "uvx",
        "node",
        "npx",
        "deno",
        "bunx",
        "bun",
        "docker",
    }
)


class SpawnSecurityError(MCPError):
    """Raised when a local-server spawn command fails the fail-closed allowlist.

    Carries :data:`MCPErrorCode.AUTHORIZATION_FAILED` (``-32003``) — a spawn
    rejection is an authorization decision, not a transport or validation
    failure.
    """

    def __init__(self, message: str, command: Optional[str] = None) -> None:
        super().__init__(
            message,
            error_code=MCPErrorCode.AUTHORIZATION_FAILED,
            data={"command": command} if command is not None else None,
        )


def validate_spawn_command(
    command: object,
    *,
    allowed_commands: Optional[Sequence[str]] = None,
    allow_arbitrary: bool = False,
) -> None:
    """Validate a local-server spawn command against the fail-closed allowlist.

    Args:
        command: The executable to spawn. MUST be a non-empty string.
        allowed_commands: Optional explicit allowlist (basenames or full
            command strings). When ``None`` the curated
            :data:`DEFAULT_ALLOWED_MCP_COMMANDS` set is used — the fail-closed
            default. Passing an empty sequence rejects EVERY command (the
            maximally-closed posture).
        allow_arbitrary: Explicit opt-out of the allowlist. When ``True`` any
            non-empty, non-traversing command is permitted. This is the ONLY
            way to spawn an unlisted command; it is never the default and is
            intended to be set knowingly by a trusted caller.

    Raises:
        SpawnSecurityError: If ``command`` is empty / not a string, contains a
            path-traversal segment, or (unless ``allow_arbitrary``) is not in
            the effective allowlist.
    """
    if not isinstance(command, str) or not command:
        raise SpawnSecurityError(
            "spawn command must be a non-empty string",
            command=command if isinstance(command, str) else None,
        )

    # Reject path traversal regardless of the allowlist / opt-out — a ``..``
    # segment is never a legitimate launcher and is a directory-escape vector.
    segments = command.replace("\\", "/").split("/")
    if ".." in segments:
        raise SpawnSecurityError(
            f"spawn command rejected (path traversal): {command!r}",
            command=command,
        )

    if allow_arbitrary:
        return

    allowed = (
        frozenset(allowed_commands)
        if allowed_commands is not None
        else DEFAULT_ALLOWED_MCP_COMMANDS
    )
    basename = os.path.basename(command)
    if basename in allowed or command in allowed:
        return

    raise SpawnSecurityError(
        f"spawn command {command!r} is not in the allowlist "
        f"(allowed: {sorted(allowed)}). Add it to `allowed_commands`, pass "
        f"`allow_arbitrary=True` (or set `allow_arbitrary_commands=True` in the "
        f"client/transport config) to permit arbitrary commands.",
        command=command,
    )
