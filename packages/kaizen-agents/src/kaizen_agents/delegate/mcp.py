"""MCP client — connect to MCP servers via stdio JSON-RPC transport.

Each MCP server runs as a subprocess communicating over stdin/stdout
using the JSON-RPC 2.0 protocol. The client:

1. Starts the server subprocess
2. Sends ``initialize`` to negotiate capabilities
3. Sends ``tools/list`` to discover available tools
4. Calls ``tools/call`` to execute individual tools
5. Registers discovered tools into the kz ToolRegistry

Configuration comes from ``.kz/config.toml`` under ``[mcp.servers]``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Timeout for individual JSON-RPC requests (seconds)
_REQUEST_TIMEOUT = 30

# Timeout for server startup / initialize handshake (seconds)
_INIT_TIMEOUT = 15


@dataclass(frozen=True)
class McpServerConfig:
    """Configuration for a single MCP server.

    Parsed from TOML::

        [mcp.servers.filesystem]
        command = "npx"
        args = ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
        env = { SOME_VAR = "value" }
    """

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class McpToolDef:
    """A tool definition discovered from an MCP server."""

    name: str
    description: str
    input_schema: dict[str, Any]
    server_name: str


class McpClient:
    """Client that manages one MCP server subprocess.

    Usage::

        config = McpServerConfig(name="fs", command="npx", args=[...])
        client = McpClient(config)
        await client.start()
        tools = await client.discover_tools()
        result = await client.call_tool("read_file", {"path": "/tmp/x"})
        await client.stop()
    """

    def __init__(self, config: McpServerConfig) -> None:
        self._config = config
        self._process: asyncio.subprocess.Process | None = None
        self._request_id: int = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._initialized: bool = False
        self._read_buffer: str = ""

    @property
    def server_name(self) -> str:
        """The configured server name."""
        return self._config.name

    @property
    def is_running(self) -> bool:
        """Whether the server subprocess is running."""
        return self._process is not None and self._process.returncode is None

    async def start(self) -> None:
        """Start the MCP server subprocess and perform the initialize handshake.

        Raises
        ------
        RuntimeError
            If the server fails to start or the initialize handshake fails.
        """
        if self.is_running:
            return

        # Build environment: inherit current env, overlay server-specific vars
        env = dict(os.environ)
        env.update(self._config.env)

        cmd = [self._config.command] + self._config.args

        # Security: log MCP server being started (command comes from config,
        # which could be project-level .kz/config.toml in a cloned repo)
        logger.info(
            "Starting MCP server %r: %s",
            self._config.name,
            " ".join(cmd),
        )

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"MCP server {self._config.name!r}: command not found: {self._config.command!r}"
            ) from exc
        except OSError as exc:
            raise RuntimeError(f"MCP server {self._config.name!r}: failed to start: {exc}") from exc

        # Start background reader for stdout
        self._reader_task = asyncio.create_task(self._read_stdout())

        # Perform initialize handshake
        try:
            result = await asyncio.wait_for(
                self._send_request(
                    "initialize",
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {
                            "name": "kz",
                            "version": "0.1.0",
                        },
                    },
                ),
                timeout=_INIT_TIMEOUT,
            )
            self._initialized = True
            logger.info(
                "MCP server %r initialized: %s",
                self._config.name,
                result.get("serverInfo", {}),
            )

            # Send initialized notification (no response expected)
            await self._send_notification("notifications/initialized", {})

        except asyncio.TimeoutError as exc:
            await self.stop()
            raise RuntimeError(
                f"MCP server {self._config.name!r}: initialize handshake timed out "
                f"after {_INIT_TIMEOUT}s"
            ) from exc
        except Exception as exc:
            await self.stop()
            raise RuntimeError(
                f"MCP server {self._config.name!r}: initialize failed: {exc}"
            ) from exc

    async def stop(self) -> None:
        """Stop the MCP server subprocess."""
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        if self._process is not None:
            if self._process.returncode is None:
                try:
                    self._process.send_signal(signal.SIGTERM)
                    await asyncio.wait_for(self._process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    self._process.kill()
                    await self._process.wait()
                except ProcessLookupError:
                    pass
            self._process = None

        # Cancel any pending futures
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()
        self._initialized = False

    async def discover_tools(self) -> list[McpToolDef]:
        """Send ``tools/list`` and return discovered tool definitions.

        Returns
        -------
        List of McpToolDef with name, description, and input_schema.

        Raises
        ------
        RuntimeError
            If the server is not running or not initialized.
        """
        self._ensure_running()

        result = await asyncio.wait_for(
            self._send_request("tools/list", {}),
            timeout=_REQUEST_TIMEOUT,
        )

        tools: list[McpToolDef] = []
        for tool_data in result.get("tools", []):
            tools.append(
                McpToolDef(
                    name=tool_data.get("name", ""),
                    description=tool_data.get("description", ""),
                    input_schema=tool_data.get("inputSchema", {}),
                    server_name=self._config.name,
                )
            )

        logger.info(
            "MCP server %r: discovered %d tools",
            self._config.name,
            len(tools),
        )
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Call a tool on the MCP server.

        Parameters
        ----------
        name:
            The tool name (as discovered via ``discover_tools``).
        arguments:
            The tool arguments matching the tool's input schema.

        Returns
        -------
        The tool result as a string. If the result contains multiple
        content blocks, they are joined with newlines.

        Raises
        ------
        RuntimeError
            If the server is not running, not initialized, or the call fails.
        """
        self._ensure_running()

        result = await asyncio.wait_for(
            self._send_request(
                "tools/call",
                {"name": name, "arguments": arguments},
            ),
            timeout=_REQUEST_TIMEOUT,
        )

        # MCP tool results contain a list of content blocks
        content_blocks = result.get("content", [])
        if not content_blocks:
            return ""

        parts: list[str] = []
        for block in content_blocks:
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif block.get("type") == "image":
                parts.append(f"[image: {block.get('mimeType', 'unknown')}]")
            else:
                parts.append(str(block))

        # Check for isError flag
        if result.get("isError"):
            return f"MCP tool error: {chr(10).join(parts)}"

        return "\n".join(parts)

    def _ensure_running(self) -> None:
        """Raise if the server is not running and initialized."""
        if not self.is_running:
            raise RuntimeError(
                f"MCP server {self._config.name!r} is not running. Call start() first."
            )
        if not self._initialized:
            raise RuntimeError(f"MCP server {self._config.name!r} is not initialized.")

    def _next_id(self) -> int:
        """Return the next JSON-RPC request ID."""
        self._request_id += 1
        return self._request_id

    async def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request and wait for the response.

        Returns the ``result`` field from the response.

        Raises
        ------
        RuntimeError
            If the response contains an error.
        """
        if self._process is None or self._process.stdin is None:
            raise RuntimeError("Server process is not available")

        req_id = self._next_id()
        message = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }

        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[req_id] = future

        line = json.dumps(message) + "\n"
        self._process.stdin.write(line.encode("utf-8"))
        await self._process.stdin.drain()

        try:
            response = await future
        finally:
            self._pending.pop(req_id, None)

        if "error" in response:
            err = response["error"]
            raise RuntimeError(
                f"MCP server {self._config.name!r} error "
                f"(code={err.get('code')}): {err.get('message')}"
            )

        return response.get("result", {})

    async def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if self._process is None or self._process.stdin is None:
            return

        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        line = json.dumps(message) + "\n"
        self._process.stdin.write(line.encode("utf-8"))
        await self._process.stdin.drain()

    async def _read_stdout(self) -> None:
        """Background task: read JSON-RPC messages from the server's stdout."""
        if self._process is None or self._process.stdout is None:
            return

        try:
            while True:
                raw = await self._process.stdout.readline()
                if not raw:
                    break

                line = raw.decode("utf-8").strip()
                if not line:
                    continue

                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug(
                        "MCP server %r: non-JSON line: %s",
                        self._config.name,
                        line[:200],
                    )
                    continue

                # If the message has an id, it is a response to a request
                msg_id = msg.get("id")
                if msg_id is not None and msg_id in self._pending:
                    future = self._pending[msg_id]
                    if not future.done():
                        future.set_result(msg)
                elif msg.get("method"):
                    # Server-initiated notification — log it
                    logger.debug(
                        "MCP server %r notification: %s",
                        self._config.name,
                        msg.get("method"),
                    )

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error(
                "MCP server %r: reader error: %s",
                self._config.name,
                exc,
                exc_info=True,
            )
            # Fail all pending futures
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(exc)


def load_mcp_server_configs(raw_config: dict[str, Any]) -> list[McpServerConfig]:
    """Parse MCP server configs from a TOML-loaded dict.

    Expects the structure::

        {
            "mcp": {
                "servers": {
                    "name1": {"command": "...", "args": [...], "env": {...}},
                    "name2": {"command": "...", "args": [...]},
                }
            }
        }

    Returns a list of McpServerConfig instances.
    """
    servers_section = raw_config.get("mcp", {}).get("servers", {})
    configs: list[McpServerConfig] = []

    for name, server_data in servers_section.items():
        if not isinstance(server_data, dict):
            logger.warning("MCP server %r: invalid config (expected dict), skipping", name)
            continue

        command = server_data.get("command")
        if not command:
            logger.warning("MCP server %r: missing 'command', skipping", name)
            continue

        configs.append(
            McpServerConfig(
                name=name,
                command=command,
                args=server_data.get("args", []),
                env=server_data.get("env", {}),
            )
        )

    return configs


async def register_mcp_tools(
    client: McpClient,
    registry: Any,
) -> list[McpToolDef]:
    """Discover tools from an MCP client and register them into a ToolRegistry.

    Tools are registered with a prefixed name: ``mcp_<server>_<tool>`` to
    avoid collisions with built-in tools.

    Parameters
    ----------
    client:
        A started McpClient instance.
    registry:
        A kz.cli.loop.ToolRegistry (the async-based loop registry).

    Returns
    -------
    List of discovered McpToolDef instances that were registered.
    """
    tools = await client.discover_tools()

    for tool_def in tools:
        prefixed_name = f"mcp_{client.server_name}_{tool_def.name}"

        # Build an async executor that calls the MCP tool
        async def _executor(
            _client: McpClient = client,
            _tool_name: str = tool_def.name,
            **kwargs: Any,
        ) -> str:
            return await _client.call_tool(_tool_name, kwargs)

        registry.register(
            name=prefixed_name,
            description=f"[MCP:{client.server_name}] {tool_def.description}",
            parameters=tool_def.input_schema,
            executor=_executor,
        )

    return tools
