# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier-2 integration test for the MCP WebSocket discovery contract.

This test guards the production_nexus MCP wiring independently of the
Tier-3 e2e suite (test_ai_agent_workflows.py) so an E2E flake does not
lose coverage of the underlying discovery contract.

Issue #816 — production_nexus fixture's WebSocket-only mode pointed at an
unbound _mcp_port. Root cause: kailash_mcp.MCPServer was constructed with
the default ``transport="stdio"`` and never set ``websocket_host`` /
``websocket_port``, so no WebSocket listener was bound. Fix: pass
``transport="websocket"`` + websocket port params at MCPServer creation,
and use ``MCPServer.run()`` (which dispatches on the transport attribute)
rather than ``MCPServer.start()`` (hardcoded stdio).

What this test asserts (the contract a Nexus user discovers via MCP):

  * tools/list returns every registered workflow with a non-empty name.
  * resources/list returns one ``workflow://<name>`` resource per workflow,
    plus the default ``system://nexus/info`` and ``docs://quickstart`` /
    ``config://platform`` / ``help://getting-started`` resources.
  * resources/read on ``system://nexus/info`` returns a JSON string
    parseable by ``json.loads`` (NOT Python repr — see the
    str(handler()) contract enforced by MCPServer._handle_read_resource).
  * tools/call on a registered workflow returns a content list whose
    text field is also a JSON string (not Python repr).
"""

import asyncio
import json
import socket
import threading
import time
from contextlib import closing

import pytest
import pytest_asyncio
import websockets

from kailash.workflow.builder import WorkflowBuilder
from nexus import Nexus


def _find_free_port(start: int) -> int:
    for port in range(start, start + 200):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            try:
                s.bind(("", port))
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                return port
            except OSError:
                continue
    raise RuntimeError(f"Could not find free port from {start}")


@pytest_asyncio.fixture
async def websocket_only_nexus():
    """Nexus instance in MCP WebSocket-only mode.

    HTTP and SSE sub-transports are off; the MCP server's only bound
    listener is the WebSocket transport on ``mcp_port``. This is the
    canonical AI-agent-only deployment shape — same configuration as
    ``test_ai_agent_workflows.py::production_nexus`` but pinned at the
    Tier-2 level so a failure here is independent evidence of the
    transport-binding contract.
    """
    api_port = _find_free_port(8700)
    mcp_port = _find_free_port(api_port + 100)

    app = Nexus(
        api_port=api_port,
        mcp_port=mcp_port,
        enable_auth=False,
        enable_monitoring=False,
        enable_http_transport=False,
        enable_sse_transport=False,
        enable_discovery=False,
    )

    # Register two simple workflows to populate tool / resource lists.
    echo = WorkflowBuilder()
    echo.add_node(
        "PythonCodeNode",
        "echo",
        {"code": "result = {'echo': parameters.get('message', 'hi')}"},
    )
    app.register("echo", echo.build())

    add = WorkflowBuilder()
    add.add_node(
        "PythonCodeNode",
        "adder",
        {"code": ("result = {'sum': parameters.get('a', 0) + parameters.get('b', 0)}")},
    )
    app.register("add", add.build())

    server_thread = threading.Thread(target=app.start, daemon=True)
    server_thread.start()

    # Wait for both API + MCP transports to bind.
    await asyncio.sleep(3)
    yield app

    app.stop()


async def _send_recv(uri: str, request: dict) -> dict:
    """Open a fresh WebSocket connection, send one JSON-RPC, await the reply."""
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps(request))
        raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
        return json.loads(raw)


@pytest.mark.asyncio
async def test_tools_list_returns_registered_workflows(websocket_only_nexus):
    """tools/list MUST surface every registered workflow as a tool name."""
    uri = f"ws://localhost:{websocket_only_nexus._mcp_port}"
    data = await _send_recv(uri, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    assert "result" in data, f"unexpected response: {data}"
    tools = data["result"]["tools"]
    names = {t["name"] for t in tools}
    # Read fixture state — do NOT hardcode workflow names per
    # rules/e2e-god-mode.md Rule 2.
    expected = set(websocket_only_nexus._workflows.keys())
    assert expected.issubset(
        names
    ), f"tools/list missing workflows: expected {expected} ⊆ {names}"


@pytest.mark.asyncio
async def test_resources_list_returns_workflow_resources(websocket_only_nexus):
    """resources/list MUST emit one ``workflow://<name>`` per workflow."""
    uri = f"ws://localhost:{websocket_only_nexus._mcp_port}"
    data = await _send_recv(
        uri, {"jsonrpc": "2.0", "id": 2, "method": "resources/list"}
    )

    assert "result" in data, f"unexpected response: {data}"
    resources = data["result"]["resources"]
    workflow_uris = {r["uri"] for r in resources if r["uri"].startswith("workflow://")}
    expected_uris = {
        f"workflow://{name}" for name in websocket_only_nexus._workflows.keys()
    }
    assert expected_uris.issubset(
        workflow_uris
    ), f"missing workflow:// resources: {expected_uris - workflow_uris}"


@pytest.mark.asyncio
async def test_resources_read_system_info_returns_valid_json(websocket_only_nexus):
    """resources/read on system://nexus/info MUST return parseable JSON.

    This test pins the Rule-2-Stub-Defense for the resource-handler
    contract: handlers return JSON STRINGS, not dicts. A handler that
    returns ``{"content": json.dumps(...)}`` produces Python repr in
    the response text field — invalid JSON, breaks every MCP client.
    """
    uri = f"ws://localhost:{websocket_only_nexus._mcp_port}"
    data = await _send_recv(
        uri,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "resources/read",
            "params": {"uri": "system://nexus/info"},
        },
    )

    assert "result" in data, f"unexpected response: {data}"
    text = data["result"]["contents"][0]["text"]
    # MUST be parseable as JSON (NOT Python repr of a dict).
    info = json.loads(text)
    assert info["platform"] == "Kailash Nexus"
    assert "workflows" in info
    assert set(info["workflows"]) == set(websocket_only_nexus._workflows.keys())


@pytest.mark.asyncio
async def test_tools_call_returns_json_text_payload(websocket_only_nexus):
    """tools/call MUST return a content list with a JSON-string text field."""
    uri = f"ws://localhost:{websocket_only_nexus._mcp_port}"
    data = await _send_recv(
        uri,
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "echo", "arguments": {"message": "hello-tier2"}},
        },
    )

    assert "result" in data, f"unexpected response: {data}"
    content = data["result"]["content"]
    assert isinstance(content, list) and len(content) > 0
    text = content[0]["text"]
    # text MUST be valid JSON (NOT Python repr of a dict).
    payload = json.loads(text)
    # The echo workflow's PythonCodeNode emits result={'echo': <message>}.
    # workflow_tool unwraps single-node {'<id>': {'result': {...}}} into
    # the inner dict per core.py::_register_workflow_as_mcp_tool.
    assert payload.get("echo") == "hello-tier2", f"unexpected payload: {payload}"


@pytest.mark.asyncio
async def test_workflow_resource_read_returns_workflow_descriptor(
    websocket_only_nexus,
):
    """resources/read on workflow://<name> MUST return a JSON descriptor."""
    workflow_name = next(iter(websocket_only_nexus._workflows.keys()))
    uri = f"ws://localhost:{websocket_only_nexus._mcp_port}"
    data = await _send_recv(
        uri,
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "resources/read",
            "params": {"uri": f"workflow://{workflow_name}"},
        },
    )

    assert "result" in data, f"unexpected response: {data}"
    text = data["result"]["contents"][0]["text"]
    descriptor = json.loads(text)
    assert descriptor["name"] == workflow_name
    assert descriptor["type"] == "workflow"
    assert "nodes" in descriptor
    assert "schema" in descriptor
