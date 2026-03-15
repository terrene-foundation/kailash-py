# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""MCP Proxy — transport-level trust enforcement.

Transforms TrustPlane from sidecar (AI calls trust_check voluntarily)
to proxy (AI tool calls route THROUGH TrustPlane). This achieves
infrastructure-enforced constraint checking.

Architecture:
  AI → TrustPlane MCP Proxy → constraint check → Tool Server
  AI ✗ Tool Server (no direct access)

The AI physically cannot reach tool servers without going through
TrustPlane. This is Tier 3 enforcement (transport-level).

Enforcement flow for each proxied tool call:
  1. Evaluate call against constraint envelope
  2. AUTO_APPROVED/FLAGGED → forward to target, record audit anchor
  3. HELD → block, wait for human resolution
  4. BLOCKED → return error with constraint violation details
"""

import inspect
import logging
import os
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class ProxyServerConfig:
    """Configuration for a downstream MCP server to proxy."""

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    action_category: str = ""
    env: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "command": self.command,
            "args": self.args,
            "action_category": self.action_category,
            "env": self.env,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProxyServerConfig":
        return cls(
            name=data["name"],
            command=data["command"],
            args=data.get("args", []),
            action_category=data.get("action_category", ""),
            env=data.get("env", {}),
        )


@dataclass
class ProxiedToolCall:
    """A tool call routed through the proxy."""

    tool_name: str
    server_name: str
    original_tool: str
    arguments: dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ProxyResult:
    """Result of a proxied tool call."""

    verdict: str  # AUTO_APPROVED, FLAGGED, HELD, BLOCKED
    forwarded: bool
    result: Any = None
    error: str | None = None
    anchor_id: str | None = None


class ProxyConfig:
    """Proxy configuration managing target server registrations."""

    def __init__(self, config_path: Path | None = None) -> None:
        self._servers: dict[str, ProxyServerConfig] = {}
        self._config_path = config_path
        if config_path and config_path.exists():
            self._load(config_path)

    def _load(self, path: Path) -> None:
        """Load proxy configuration from TOML file (symlink-safe)."""
        import errno as _errno

        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]

        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(str(path), flags)
        except OSError as e:
            if e.errno == _errno.ELOOP:
                raise OSError(
                    f"Refusing to read symlink config (possible attack): {path}"
                ) from e
            raise
        try:
            f = os.fdopen(fd, "rb")
        except Exception:
            os.close(fd)
            raise
        with f:
            data = tomllib.load(f)

        for server_data in data.get("servers", []):
            config = ProxyServerConfig.from_dict(server_data)
            self._servers[config.name] = config

    def add_server(self, config: ProxyServerConfig) -> None:
        """Register a target server."""
        self._servers[config.name] = config

    def remove_server(self, name: str) -> None:
        """Remove a target server."""
        self._servers.pop(name, None)

    def get_server(self, name: str) -> ProxyServerConfig | None:
        return self._servers.get(name)

    @property
    def servers(self) -> dict[str, ProxyServerConfig]:
        return dict(self._servers)

    def save(self, path: Path | None = None) -> None:
        """Save configuration to JSON (TOML write requires extra dep)."""
        from trustplane._locking import atomic_write

        target = path or self._config_path
        if target is None:
            raise ValueError("No config path specified")
        data = {"servers": [s.to_dict() for s in self._servers.values()]}
        atomic_write(target, data)


class TrustProxy:
    """MCP Proxy that interposes constraint checking on tool calls.

    The proxy sits between the AI and downstream MCP tool servers.
    Every tool call passes through constraint checking before being
    forwarded to the target server.

    This is Tier 3 enforcement — transport-level, infrastructure-enforced.
    """

    def __init__(
        self,
        project: Any,  # TrustProject — avoid circular import
        config: ProxyConfig | None = None,
    ) -> None:
        self._project = project
        self._config = config or ProxyConfig()
        self._tool_handlers: dict[str, Callable[..., Awaitable[Any]]] = {}
        self._running = False
        self._call_log: deque[dict[str, Any]] = deque(maxlen=10_000)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def servers(self) -> dict[str, ProxyServerConfig]:
        return self._config.servers

    @property
    def call_log(self) -> list[dict[str, Any]]:
        return list(self._call_log)

    @staticmethod
    def _filter_arguments(
        handler: Callable[..., Awaitable[Any]], arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Filter arguments to only those accepted by the handler signature.

        Prevents argument injection where the caller passes unexpected keyword
        arguments (e.g., admin=True) to handlers with security-sensitive defaults.
        """
        sig = inspect.signature(handler)
        # If handler accepts **kwargs, pass everything (handler opts in)
        for param in sig.parameters.values():
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                return arguments
        accepted = set(sig.parameters.keys())
        return {k: v for k, v in arguments.items() if k in accepted}

    def register_tool_handler(
        self,
        server_name: str,
        tool_name: str,
        handler: Callable[..., Awaitable[Any]],
    ) -> None:
        """Register a handler for a proxied tool.

        The handler is the actual function that executes the tool.
        The proxy wraps it with constraint checking.

        Args:
            server_name: Name of the target server
            tool_name: Original tool name on the target server
            handler: Async function that executes the tool
        """
        namespaced = f"{server_name}__{tool_name}"
        self._tool_handlers[namespaced] = handler

    def start(self) -> None:
        """Start the proxy."""
        self._running = True
        logger.info(
            "TrustProxy started with %d servers, %d tools",
            len(self._config.servers),
            len(self._tool_handlers),
        )

    def stop(self) -> None:
        """Stop the proxy. AI loses all tool access (fail-closed)."""
        self._running = False
        logger.info("TrustProxy stopped — all tool access revoked")

    async def handle_call(
        self, namespaced_tool: str, arguments: dict[str, Any]
    ) -> ProxyResult:
        """Handle a proxied tool call with constraint enforcement.

        This is the core proxy logic:
        1. Check if proxy is running (fail-closed)
        2. Parse the namespaced tool name
        3. Check constraints
        4. Forward or block based on verdict

        Args:
            namespaced_tool: Tool name in format "server__tool"
            arguments: Tool call arguments

        Returns:
            ProxyResult with verdict, result, and audit info
        """
        if not self._running:
            return ProxyResult(
                verdict="BLOCKED",
                forwarded=False,
                error="Proxy is not running — all tool access denied (fail-closed)",
            )

        # Parse namespaced tool
        parts = namespaced_tool.split("__", 1)
        if len(parts) != 2:
            return ProxyResult(
                verdict="BLOCKED",
                forwarded=False,
                error=f"Invalid tool name format: {namespaced_tool}. Expected 'server__tool'.",
            )

        server_name, tool_name = parts
        server = self._config.get_server(server_name)
        if server is None:
            logger.warning("Unknown server requested: %s", server_name)
            return ProxyResult(
                verdict="BLOCKED",
                forwarded=False,
                error="Requested server is not registered",
            )

        handler = self._tool_handlers.get(namespaced_tool)
        if handler is None:
            logger.warning("No handler for tool: %s", namespaced_tool)
            return ProxyResult(
                verdict="BLOCKED",
                forwarded=False,
                error="Requested tool is not registered",
            )

        # Build context for constraint check
        action = server.action_category or tool_name
        context = {
            "server": server_name,
            "tool": tool_name,
            "resource": arguments.get("path", arguments.get("resource", "")),
        }

        # Check constraints
        from eatp.enforce.strict import Verdict

        verdict = self._project.check(action, context)

        log_entry = {
            "tool": namespaced_tool,
            "server": server_name,
            "original_tool": tool_name,
            "verdict": verdict.name if hasattr(verdict, "name") else str(verdict),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "arguments_keys": list(arguments.keys()),
        }

        if verdict == Verdict.BLOCKED:
            log_entry["forwarded"] = False
            self._call_log.append(log_entry)
            return ProxyResult(
                verdict="BLOCKED",
                forwarded=False,
                error="Action blocked by constraint envelope",
            )

        if verdict == Verdict.HELD:
            log_entry["forwarded"] = False
            self._call_log.append(log_entry)
            return ProxyResult(
                verdict="HELD",
                forwarded=False,
                error="Action held for human review. Use 'attest holds' to resolve.",
            )

        # Forward the call (AUTO_APPROVED or FLAGGED)
        try:
            filtered_args = self._filter_arguments(handler, arguments)
            result = await handler(**filtered_args)
        except Exception as e:
            logger.error("Proxied tool execution failed: %s", e, exc_info=True)
            log_entry["forwarded"] = True
            log_entry["error"] = str(e)
            self._call_log.append(log_entry)
            return ProxyResult(
                verdict=verdict.name,
                forwarded=True,
                error="Tool execution failed",
            )

        # Record audit anchor for the proxied call
        from eatp.chain import ActionResult

        anchor = await self._project._ops.audit(
            agent_id=self._project._agent_id,
            action=f"proxy_{tool_name}",
            resource=f"proxy/{server_name}/{tool_name}",
            result=ActionResult.SUCCESS,
            context_data={
                "proxy_server": server_name,
                "proxy_tool": tool_name,
                "verdict": verdict.name,
                "parent_anchor_id": self._project._last_anchor_id,
            },
        )
        self._project._last_anchor_id = anchor.id

        log_entry["forwarded"] = True
        log_entry["anchor_id"] = anchor.id
        self._call_log.append(log_entry)

        if verdict == Verdict.FLAGGED:
            logger.warning(
                "Proxied call %s FLAGGED — forwarded with audit trail",
                namespaced_tool,
            )

        return ProxyResult(
            verdict=verdict.name,
            forwarded=True,
            result=result,
            anchor_id=anchor.id,
        )

    def status(self) -> dict[str, Any]:
        """Proxy health status."""
        return {
            "running": self._running,
            "servers": {
                name: {
                    "command": s.command,
                    "action_category": s.action_category,
                }
                for name, s in self._config.servers.items()
            },
            "registered_tools": list(self._tool_handlers.keys()),
            "total_calls": len(self._call_log),
        }
