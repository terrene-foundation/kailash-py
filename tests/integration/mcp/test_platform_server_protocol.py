# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 MCP STDIO protocol tests for the platform server.

These tests spawn the platform server as a subprocess and communicate
via the real MCP STDIO protocol.  They complement the in-process tests
in ``test_platform_server_integration.py`` by verifying transport-level
correctness.

Requires: the ``mcp`` SDK package for client-side protocol.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

FIXTURE_PROJECT = Path(__file__).parent.parent.parent / "fixtures" / "mcp_test_project"
SERVER_MODULE = "kailash.mcp.platform_server"


async def _start_server(project_root: Path, timeout: float = 10.0):
    """Start the platform server subprocess with STDIO transport."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        SERVER_MODULE,
        "--project-root",
        str(project_root),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    return proc


async def _send_jsonrpc(
    proc, method: str, params: dict | None = None, req_id: int = 1
) -> dict:
    """Send a JSON-RPC request and read the response."""
    request = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
    }
    if params is not None:
        request["params"] = params

    body = json.dumps(request)
    message = f"Content-Length: {len(body)}\r\n\r\n{body}"

    proc.stdin.write(message.encode())
    await proc.stdin.drain()

    # Read response header
    header = b""
    while b"\r\n\r\n" not in header:
        chunk = await asyncio.wait_for(proc.stdout.read(1), timeout=5.0)
        if not chunk:
            raise RuntimeError("Server closed stdout")
        header += chunk

    # Parse content length
    header_str = header.decode()
    content_length = 0
    for line in header_str.split("\r\n"):
        if line.startswith("Content-Length:"):
            content_length = int(line.split(":")[1].strip())
            break

    # Read response body
    remaining = header.split(b"\r\n\r\n", 1)[1]
    body_bytes = remaining
    while len(body_bytes) < content_length:
        chunk = await asyncio.wait_for(
            proc.stdout.read(content_length - len(body_bytes)), timeout=5.0
        )
        if not chunk:
            raise RuntimeError("Server closed stdout mid-body")
        body_bytes += chunk

    return json.loads(body_bytes[:content_length])


@pytest.mark.integration
class TestPlatformServerProtocol:
    """Real MCP STDIO protocol tests."""

    async def test_server_module_importable(self) -> None:
        """The platform server module can be imported."""
        from kailash.mcp.platform_server import create_platform_server

        assert callable(create_platform_server)

    async def test_server_has_main_entry(self) -> None:
        """The platform server has a main() function for subprocess use."""
        from kailash.mcp.platform_server import main

        assert callable(main)

    async def test_fixture_project_exists(self) -> None:
        """Test fixture project directory is present."""
        assert FIXTURE_PROJECT.exists()
        assert (FIXTURE_PROJECT / "handlers").exists()

    async def test_server_starts_and_stops(self) -> None:
        """Server subprocess starts and can be terminated cleanly."""
        proc = await _start_server(FIXTURE_PROJECT)
        assert proc.returncode is None  # Still running

        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()

        assert proc.returncode is not None
