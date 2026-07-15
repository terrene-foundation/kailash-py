"""Stdio transport for MCP client communication.

:class:`StdioTransport` spawns an MCP server subprocess and exchanges
JSON-RPC messages with it via stdin/stdout using LSP-style
``Content-Length`` framing.

Framing format (one message)::

    Content-Length: <N>\\r\\n
    \\r\\n
    <JSON body of exactly N bytes>

This mirrors the Rust SDK's ``StdioTransport`` (see
``kailash-rs/crates/kailash-mcp/src/transport/stdio.rs``) for cross-SDK
parity. Both implementations are wire-level compatible — a Python
client can speak to a Rust-spawned MCP server and vice versa.

Security: subprocess spawning never invokes a shell (``shell=False``),
so the command/args are not interpreted by ``/bin/sh``. The executable
allowlist fails CLOSED by default (MCP 2025-11-25 local-server spawn
safety) — absent an explicit ``allowed_commands`` the curated
:data:`DEFAULT_ALLOWED_COMMANDS` launcher set is enforced and an unlisted
command is rejected. Pass ``allowed_commands=[...]`` to narrow/extend it,
or ``allow_arbitrary_commands=True`` to opt out explicitly.
"""

from __future__ import annotations

import asyncio
import os
import shlex
from asyncio.subprocess import Process
from typing import Optional, Sequence

from .base import ProtocolError, Transport, TransportError

CONTENT_LENGTH_PREFIX = "Content-Length: "

# 64 MiB cap on a single message body — matches the Rust limit and
# guards against malicious / runaway peers that would otherwise drive
# us to OOM by sending an outsized Content-Length header.
MAX_MESSAGE_SIZE = 64 * 1024 * 1024

# Fail-closed default allowlist of standard MCP launcher executables (MCP
# 2025-11-25 local-server spawn safety). Deliberately EXCLUDES shells
# (``sh`` / ``bash`` / ``cmd`` / ``powershell``) and generic download-exec
# tools (``curl`` / ``wget``) — those are the arbitrary-command-injection
# vectors the fail-closed default exists to reject. Absent an explicit
# ``allowed_commands``, an unlisted command is REJECTED, never warn-and-allowed.
DEFAULT_ALLOWED_COMMANDS = frozenset(
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


class StdioTransport(Transport):
    """MCP client transport over a subprocess's stdin/stdout.

    Spawns a child process (no shell) and frames JSON-RPC messages with
    LSP-style ``Content-Length`` headers. Only one request is in flight
    at a time per transport instance — :meth:`send` serializes
    write/read pairs through an :class:`asyncio.Lock`.

    Construct via :meth:`spawn` (async classmethod) or
    :meth:`from_process` (already-spawned process).

    Attributes:
        process: The child :class:`asyncio.subprocess.Process`.
    """

    def __init__(self, process: Process) -> None:
        if process.stdin is None:
            raise TransportError("child process stdin not available")
        if process.stdout is None:
            raise TransportError("child process stdout not available")
        self.process = process
        self._stdin = process.stdin
        self._stdout = process.stdout
        self._send_lock = asyncio.Lock()
        self._closed = False

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    async def spawn(
        cls,
        command: str,
        args: Optional[Sequence[str]] = None,
        *,
        allowed_commands: Optional[Sequence[str]] = None,
        allow_arbitrary_commands: bool = False,
        env: Optional[dict] = None,
        cwd: Optional[str] = None,
    ) -> "StdioTransport":
        """Spawn an MCP server subprocess and connect a transport.

        The command allowlist fails CLOSED by default (MCP 2025-11-25
        local-server spawn safety): an unlisted command is REJECTED, never
        warn-and-allowed.

        Args:
            command: Path or basename of the executable to spawn. Path
                traversal sequences (``..``) are rejected.
            args: Optional list of arguments to pass to the executable.
            allowed_commands: Explicit allowlist. When omitted, the curated
                :data:`DEFAULT_ALLOWED_COMMANDS` set (standard MCP launchers)
                is enforced — the fail-closed default. A command whose
                basename (or full string) is not in the effective allowlist
                raises :class:`TransportError`.
            allow_arbitrary_commands: Explicit opt-out of the allowlist. When
                ``True`` any non-empty, non-traversing command is permitted.
                This is the only way to spawn an unlisted command; it is never
                the default.
            env: Optional environment mapping (passed to the subprocess).
            cwd: Optional working directory for the subprocess.

        Returns:
            A connected :class:`StdioTransport`.

        Raises:
            TransportError: If the command fails validation or spawning
                fails.
        """
        cls._validate_command(command, allowed_commands, allow_arbitrary_commands)
        cmd_args: list[str] = list(args or [])
        try:
            process = await asyncio.create_subprocess_exec(
                command,
                *cmd_args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=env,
                cwd=cwd,
            )
        except (OSError, FileNotFoundError) as exc:
            raise TransportError(f"failed to spawn {command!r}: {exc}") from exc
        return cls(process)

    @classmethod
    def from_process(cls, process: Process) -> "StdioTransport":
        """Create a transport from an already-spawned subprocess.

        The process MUST have been spawned with ``stdin=PIPE`` and
        ``stdout=PIPE``. Useful when the caller wants control over
        spawning (e.g., custom rlimits, namespace setup).
        """
        return cls(process)

    @staticmethod
    def _validate_command(
        command: str,
        allowed: Optional[Sequence[str]],
        allow_arbitrary: bool = False,
    ) -> None:
        if not isinstance(command, str) or not command:
            raise TransportError("command must be a non-empty string")
        if ".." in command.replace("\\", "/").split("/"):
            raise TransportError(f"command rejected (path traversal): {command!r}")
        if allow_arbitrary:
            return
        # Fail closed: absent an explicit allowlist, enforce the curated
        # default launcher set rather than permitting arbitrary commands.
        effective = allowed if allowed is not None else DEFAULT_ALLOWED_COMMANDS
        basename = os.path.basename(command)
        if basename not in effective and command not in effective:
            allowed_str = ", ".join(repr(c) for c in sorted(effective))
            raise TransportError(
                f"command {command!r} not in the allowlist [{allowed_str}]; "
                f"pass allowed_commands=[...] or allow_arbitrary_commands=True"
            )

    # ------------------------------------------------------------------
    # Transport protocol
    # ------------------------------------------------------------------

    async def send(self, message: str) -> str:
        """Send a framed request, return the framed response."""
        if self._closed:
            raise TransportError("transport is closed")
        async with self._send_lock:
            await write_framed_message(self._stdin, message)
            return await read_framed_message(self._stdout)

    async def receive(self) -> str:
        """Read a single unsolicited message from the subprocess.

        For request/response use, prefer :meth:`send`. ``receive`` is
        provided for transports / clients that subscribe to server-side
        notifications.
        """
        if self._closed:
            raise TransportError("transport is closed")
        return await read_framed_message(self._stdout)

    async def close(self) -> None:
        """Close stdin/stdout and terminate the subprocess.

        Idempotent. Sends EOF on stdin first to give a well-behaved
        server a chance to exit cleanly; if it does not exit within a
        short grace period the process is killed.
        """
        if self._closed:
            return
        self._closed = True

        try:
            if self._stdin and not self._stdin.is_closing():
                self._stdin.close()
        except Exception:
            pass

        if self.process.returncode is None:
            try:
                await asyncio.wait_for(self.process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                try:
                    self.process.terminate()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    try:
                        self.process.kill()
                    except ProcessLookupError:
                        pass
                    try:
                        await self.process.wait()
                    except Exception:
                        pass


# ---------------------------------------------------------------------------
# Framing helpers — exposed publicly so other transport-shaped consumers
# (test fixtures, alternate stdio wrappers) can reuse the same wire
# format without re-implementing it.
# ---------------------------------------------------------------------------


async def write_framed_message(writer: asyncio.StreamWriter, body: str) -> None:
    """Write ``body`` to ``writer`` with LSP-style framing.

    Format: ``Content-Length: <N>\\r\\n\\r\\n<body>``.

    Raises:
        TransportError: On underlying I/O failure.
    """
    body_bytes = body.encode("utf-8")
    header = f"{CONTENT_LENGTH_PREFIX}{len(body_bytes)}\r\n\r\n".encode("ascii")
    try:
        writer.write(header)
        writer.write(body_bytes)
        await writer.drain()
    except (ConnectionError, BrokenPipeError, OSError) as exc:
        raise TransportError(f"failed to write framed message: {exc}") from exc


async def read_framed_message(reader: asyncio.StreamReader) -> str:
    """Read a single framed message from ``reader``.

    Reads header lines until a blank line, parses the
    ``Content-Length``, then reads exactly that many bytes for the
    body.

    Raises:
        TransportError: On EOF or I/O error.
        ProtocolError: If ``Content-Length`` is missing, malformed, or
            exceeds :data:`MAX_MESSAGE_SIZE`, or if the body is not
            valid UTF-8.
    """
    content_length: Optional[int] = None

    while True:
        try:
            line = await reader.readline()
        except (ConnectionError, OSError) as exc:
            raise TransportError(f"failed to read header line: {exc}") from exc

        if not line:
            raise TransportError("EOF while reading headers")

        try:
            decoded = line.decode("ascii")
        except UnicodeDecodeError as exc:
            raise ProtocolError(f"non-ASCII byte in header line: {exc}") from exc

        trimmed = decoded.rstrip("\r\n")
        if trimmed == "":
            break

        if trimmed.startswith(CONTENT_LENGTH_PREFIX):
            value = trimmed[len(CONTENT_LENGTH_PREFIX) :].strip()
            try:
                content_length = int(value)
            except ValueError as exc:
                raise ProtocolError(
                    f"invalid Content-Length value {value!r}: {exc}"
                ) from exc

    if content_length is None:
        raise ProtocolError("missing Content-Length header")
    if content_length < 0:
        raise ProtocolError(f"Content-Length {content_length} is negative")
    if content_length > MAX_MESSAGE_SIZE:
        raise ProtocolError(
            f"Content-Length {content_length} exceeds maximum allowed size "
            f"({MAX_MESSAGE_SIZE} bytes)"
        )

    try:
        body = await reader.readexactly(content_length)
    except asyncio.IncompleteReadError as exc:
        raise TransportError(
            f"failed to read message body ({content_length} bytes, "
            f"got {len(exc.partial)})"
        ) from exc
    except (ConnectionError, OSError) as exc:
        raise TransportError(f"failed to read message body: {exc}") from exc

    try:
        return body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProtocolError(f"message body is not valid UTF-8: {exc}") from exc


def _quote_for_log(command: str, args: Sequence[str]) -> str:
    """Render a spawn command + args for log output (debug only)."""
    return shlex.join([command, *args])


def validate_spawn_command(
    command: str,
    allowed_commands: Optional[Sequence[str]] = None,
    allow_arbitrary_commands: bool = False,
) -> None:
    """Fail-closed validation of an MCP local-server spawn command.

    Shared entry point for every MCP stdio spawn site (this transport AND the
    middleware MCP client). Absent ``allowed_commands`` the curated
    :data:`DEFAULT_ALLOWED_COMMANDS` set is enforced; an unlisted command
    raises :class:`TransportError` (never warn-and-allow). Set
    ``allow_arbitrary_commands=True`` to opt out explicitly.
    """
    StdioTransport._validate_command(
        command, allowed_commands, allow_arbitrary_commands
    )


__all__ = [
    "StdioTransport",
    "write_framed_message",
    "read_framed_message",
    "validate_spawn_command",
    "DEFAULT_ALLOWED_COMMANDS",
    "MAX_MESSAGE_SIZE",
    "CONTENT_LENGTH_PREFIX",
]
