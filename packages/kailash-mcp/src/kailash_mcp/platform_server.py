# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Kailash Platform MCP Server -- unified introspection for AI assistants.

Provides a single FastMCP server that discovers installed Kailash frameworks
and registers namespace-prefixed tools for each. MCP clients (Claude Code,
Cursor, etc.) configure one server entry and get full project introspection.

Usage::

    kailash-mcp --project-root /path/to/project
    kailash-mcp --transport sse --port 8900

The server uses a contributor plugin system: each framework implements a
``register_tools(server, project_root, namespace)`` function. Contributors
that fail to import (framework not installed) are skipped gracefully.

Health, auth, and rate-limiting middleware are available for SSE/HTTP
transports. Configure via environment variables:

    KAILASH_MCP_AUTH_TOKEN      — Bearer token for auth middleware
    KAILASH_MCP_RATE_LIMIT      — Requests per minute per client (default: 60)
"""

from __future__ import annotations

import argparse
import collections
import importlib
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Server start time — set once when the module is first loaded
# ---------------------------------------------------------------------------
_SERVER_START_TIME: float = time.monotonic()

__all__ = [
    "FRAMEWORK_CONTRIBUTORS",
    "TokenAuthMiddleware",
    "RateLimitMiddleware",
    "create_platform_server",
    "get_health_status",
    "main",
]

FRAMEWORK_CONTRIBUTORS: list[tuple[str, str]] = [
    ("kailash_mcp.contrib.core", "core"),
    ("kailash_mcp.contrib.platform", "platform"),
    ("kailash_mcp.contrib.dataflow", "dataflow"),
    ("kailash_mcp.contrib.nexus", "nexus"),
    ("kailash_mcp.contrib.kaizen", "kaizen"),
    ("kailash_mcp.contrib.trust", "trust"),
    ("kailash_mcp.contrib.pact", "pact"),
]


# ---------------------------------------------------------------------------
# Token-based authentication middleware
# ---------------------------------------------------------------------------


class TokenAuthMiddleware:
    """Simple bearer-token authentication middleware.

    Validates that incoming requests carry an ``Authorization: Bearer <token>``
    header matching the configured token. The token is read from the
    ``KAILASH_MCP_AUTH_TOKEN`` environment variable at construction time.

    When no token is configured (env var empty or absent), the middleware
    passes all requests through — this keeps the default open for local
    STDIO usage while protecting SSE/HTTP deployments.
    """

    def __init__(self, token: str | None = None) -> None:
        self._token: str | None = (
            token or os.environ.get("KAILASH_MCP_AUTH_TOKEN", "") or None
        )

    @property
    def enabled(self) -> bool:
        """Whether authentication is active (token is configured)."""
        return self._token is not None

    def authenticate(self, authorization_header: str | None) -> bool:
        """Check a request's Authorization header.

        Args:
            authorization_header: The raw ``Authorization`` header value,
                e.g. ``"Bearer abc123"``.

        Returns:
            ``True`` if the request is allowed, ``False`` otherwise.
        """
        if not self.enabled:
            return True
        if not authorization_header:
            return False
        parts = authorization_header.split(None, 1)
        if len(parts) != 2:
            return False
        scheme, provided_token = parts
        if scheme.lower() != "bearer":
            return False
        # Constant-time comparison to avoid timing attacks
        import hmac

        return hmac.compare_digest(provided_token, self._token or "")


# ---------------------------------------------------------------------------
# Rate-limiting middleware
# ---------------------------------------------------------------------------


class RateLimitMiddleware:
    """In-memory per-client rate limiter using a sliding window counter.

    Each client is identified by a string key (typically IP address or
    auth token). The limiter tracks request timestamps in a deque and
    rejects requests that exceed the configured ``requests_per_minute``.

    The limit is read from the ``KAILASH_MCP_RATE_LIMIT`` environment
    variable at construction time, defaulting to 60 requests/minute.
    """

    def __init__(self, requests_per_minute: int | None = None) -> None:
        env_limit = os.environ.get("KAILASH_MCP_RATE_LIMIT", "")
        if requests_per_minute is not None:
            self._limit = requests_per_minute
        elif env_limit.isdigit() and int(env_limit) > 0:
            self._limit = int(env_limit)
        else:
            self._limit = 60
        self._window_seconds: float = 60.0
        self._clients: dict[str, collections.deque[float]] = {}

    @property
    def limit(self) -> int:
        """Configured requests-per-minute limit."""
        return self._limit

    def is_allowed(self, client_id: str) -> bool:
        """Check whether a request from *client_id* should be allowed.

        Args:
            client_id: An identifier for the client (IP, token hash, etc.).

        Returns:
            ``True`` if the request is within the rate limit, ``False``
            if the client has exceeded the limit.
        """
        now = time.monotonic()
        cutoff = now - self._window_seconds

        if client_id not in self._clients:
            self._clients[client_id] = collections.deque()
        window = self._clients[client_id]

        # Evict timestamps older than the window
        while window and window[0] < cutoff:
            window.popleft()

        if len(window) >= self._limit:
            return False

        window.append(now)
        return True

    def remaining(self, client_id: str) -> int:
        """Return the number of requests remaining for *client_id*.

        Args:
            client_id: An identifier for the client.

        Returns:
            Non-negative integer of remaining allowed requests in the
            current window.
        """
        now = time.monotonic()
        cutoff = now - self._window_seconds

        window = self._clients.get(client_id)
        if window is None:
            return self._limit

        # Evict stale entries for an accurate count
        while window and window[0] < cutoff:
            window.popleft()

        return max(0, self._limit - len(window))

    def reset(self) -> None:
        """Clear all client tracking state."""
        self._clients.clear()


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


def get_health_status(server: Any) -> dict[str, Any]:
    """Build a health status dictionary for the platform server.

    Args:
        server: The FastMCP server instance to inspect.

    Returns:
        A dictionary with server status, uptime, and registered tool/resource
        counts suitable for returning from a ``/health`` endpoint or MCP tool.
    """
    uptime_seconds = time.monotonic() - _SERVER_START_TIME

    tool_count = 0
    resource_count = 0
    try:
        tool_count = len(server._tool_manager._tools)
    except AttributeError:
        try:
            tool_count = len(server._tools)
        except AttributeError:
            pass
    try:
        resource_count = len(server._resource_manager._resources)
    except AttributeError:
        try:
            resource_count = len(server._resources)
        except AttributeError:
            pass

    return {
        "status": "healthy",
        "uptime_seconds": round(uptime_seconds, 2),
        "server_name": getattr(server, "name", "kailash-platform"),
        "tools_registered": tool_count,
        "resources_registered": resource_count,
    }


def _get_fastmcp_class() -> type:
    """Import FastMCP from the third-party ``mcp`` package.

    The ``kailash.mcp`` sub-package shadows the top-level ``mcp`` package
    when Python resolves imports inside this package.  ``find_spec("mcp")``
    returns ``kailash.mcp`` even when scoped to site-packages, because the
    ``kailash`` namespace package is installed there.

    We work around this by directly locating the ``mcp`` directory inside
    site-packages and loading it via its filesystem path.
    """
    import importlib.util as _ilu

    # Fast path: if the third-party mcp is already in sys.modules, use it.
    existing = sys.modules.get("mcp")
    if existing is not None:
        origin = getattr(existing, "__file__", "") or ""
        if "site-packages" in origin and "kailash" not in origin:
            try:
                mod = importlib.import_module("mcp.server.fastmcp")
                return getattr(mod, "FastMCP")
            except (ImportError, AttributeError):
                pass

    # Walk site-packages to find the third-party mcp package by filesystem.
    # The key challenge: our kailash.mcp package shadows the top-level mcp.
    # We identify the third-party mcp by looking for mcp/ directly under a
    # site-packages directory (the third-party mcp is a top-level package,
    # not nested inside kailash/).
    for path_entry in sys.path:
        if "site-packages" not in path_entry:
            continue
        sp_dir = Path(path_entry)
        candidate = sp_dir / "mcp" / "__init__.py"
        if not candidate.exists():
            continue
        # Verify this is the third-party mcp, not kailash/mcp.
        # The third-party mcp lives at <site-packages>/mcp/__init__.py
        # Our kailash.mcp lives at <src>/kailash/mcp/__init__.py
        # The parent of the candidate's parent should be site-packages.
        # i.e., candidate.parent.parent should equal sp_dir.
        if candidate.parent.parent != sp_dir:
            continue

        # Build a spec from the filesystem path and load it.
        spec = _ilu.spec_from_file_location(
            "mcp",
            str(candidate),
            submodule_search_locations=[str(candidate.parent)],
        )
        if spec is None or spec.loader is None:
            continue

        mcp_pkg = _ilu.module_from_spec(spec)
        sys.modules["mcp"] = mcp_pkg
        try:
            spec.loader.exec_module(mcp_pkg)
            # Chain-import FastMCP through the normal import system.
            mod = importlib.import_module("mcp.server.fastmcp")
            return getattr(mod, "FastMCP")
        except Exception:
            sys.modules.pop("mcp", None)
            continue

    raise ImportError(
        "Cannot import FastMCP from the third-party 'mcp' package. "
        "Install it with: pip install 'mcp[cli]>=1.23.0,<2.0'"
    )


def _get_tool_names(server: Any) -> set[str]:
    """Extract registered tool names from a FastMCP server instance.

    FastMCP's internal API varies across versions. We try several known
    attribute paths to discover tools.
    """
    # FastMCP >= 1.23 uses _tool_manager._tools
    try:
        return set(server._tool_manager._tools.keys())
    except AttributeError:
        pass

    # Older FastMCP versions may use _tools directly
    try:
        return set(server._tools.keys())
    except AttributeError:
        pass

    # Cannot inspect -- return empty set (namespace validation is best-effort)
    return set()


def create_platform_server(project_root: Path | None = None) -> Any:
    """Create and configure the kailash-platform MCP server.

    Args:
        project_root: Root directory of the Kailash project to introspect.
            Defaults to the current working directory.

    Returns:
        A configured FastMCP server instance ready to run.
    """
    FastMCP = _get_fastmcp_class()

    if project_root is None:
        project_root = Path.cwd()
    project_root = Path(project_root).resolve()

    server = FastMCP(
        "kailash-platform",
        instructions=(
            "Kailash Platform provides introspection into a Kailash project. "
            "Use namespace-prefixed tools (core.*, dataflow.*, nexus.*, kaizen.*, "
            "platform.*, trust.*, pact.*) to discover models, handlers, agents, "
            "node types, and cross-framework connections."
        ),
    )

    start = time.monotonic()

    for module_path, namespace in FRAMEWORK_CONTRIBUTORS:
        tools_before = _get_tool_names(server)

        try:
            mod = importlib.import_module(module_path)
            mod.register_tools(server, project_root, namespace)
        except ImportError:
            logger.info("Framework %s not installed, skipping contributor", namespace)
            continue
        except Exception as exc:
            logger.error(
                "Contributor %s failed to register: %s",
                namespace,
                exc,
                exc_info=True,
            )
            continue

        # Namespace validation: check that newly registered tools use the
        # correct namespace prefix.
        tools_after = _get_tool_names(server)
        new_tools = tools_after - tools_before
        prefix = f"{namespace}."
        for tool_name in new_tools:
            if not tool_name.startswith(prefix):
                logger.warning(
                    "Contributor %s registered tool '%s' without '%s' prefix",
                    namespace,
                    tool_name,
                    prefix,
                )

    # -----------------------------------------------------------------------
    # Built-in health tool — always registered, no namespace prefix needed
    # since it's a server-level concern, not a framework contributor.
    # We register it under the "platform" namespace for consistency.
    # -----------------------------------------------------------------------

    @server.tool(name="platform.health")
    async def health() -> dict:
        """Return server health status including uptime and registered counts.

        Use this to verify the MCP server is running and responsive.
        """
        return get_health_status(server)

    elapsed = time.monotonic() - start
    tool_count = len(_get_tool_names(server))
    logger.info("kailash-platform started in %.2fs with %d tools", elapsed, tool_count)

    return server


def main() -> None:
    """CLI entry point for the ``kailash-mcp`` console script."""
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Kailash Platform MCP Server",
        prog="kailash-mcp",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root directory (default: KAILASH_PROJECT_ROOT env var or cwd)",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8900,
        help="Port for SSE transport (default: 8900)",
    )
    args = parser.parse_args()

    # project_root resolution: CLI arg > env var > cwd
    if args.project_root is not None:
        project_root = args.project_root
    else:
        env_root = os.environ.get("KAILASH_PROJECT_ROOT", "")
        project_root = Path(env_root) if env_root else Path.cwd()
    project_root = project_root.resolve()

    server = create_platform_server(project_root)

    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport="sse", port=args.port)


if __name__ == "__main__":
    main()
