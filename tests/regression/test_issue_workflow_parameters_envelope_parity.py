# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: the ``parameters`` envelope MUST bind identically on every channel.

``WorkflowRequest.get_inputs`` (``kailash/api/workflow_api.py``) UNWRAPPED the
``{"parameters": {...}}`` body, returning the inner mapping as the workflow
inputs. Nexus' MCP channel, by contrast, forwarded ``{"parameters": params}``
with the envelope intact. The consequence was a multi-channel parity break in
the product whose core promise is multi-channel parity:

* MCP  -- node reads ``parameters.get("id")``  -> 200
* HTTP -- same workflow, same intent            -> 500
* CLI  -- ``nexus/cli/main.py`` POSTs exactly ``{"parameters": {...}}`` into
  that same unwrapping endpoint -> 500

with the server-side cause::

    NameError: name 'parameters' is not defined
      File "kailash/nodes/code/python.py", line 495, in execute_code

The fix binds BOTH shapes on BOTH channels: every key at workflow level AND
the whole mapping under ``parameters``.

Instrument note: the load-bearing assertion is that all three channels return
the SAME value for the SAME workflow source. A test that drove only HTTP would
pass while parity stayed broken on a channel it never drove
(``user-flow-validation.md`` MUST-8), which is how the original defect
survived -- so each channel is driven on its own real path below.
"""

import socket
import threading
import time

import pytest
import requests
from kailash.workflow.builder import WorkflowBuilder

nexus_mod = pytest.importorskip("nexus", reason="kailash-nexus is not installed")
Nexus = nexus_mod.Nexus

# One workflow source, read by every channel. It reads its argument BOTH ways
# so a channel that binds only one shape fails loudly instead of silently
# passing on the shape it happens to support.
PARITY_CODE = "result = {'via_envelope': parameters.get('id'), 'via_toplevel': id}"


def _find_free_port(start_port: int) -> int:
    for port in range(start_port, start_port + 200):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"no free port from {start_port}")


def _wait_until_healthy(api_port: int, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if requests.get(f"http://localhost:{api_port}/health", timeout=1).ok:
                return
        except requests.RequestException:
            pass
        time.sleep(0.25)
    pytest.fail(f"Nexus did not answer /health on {api_port} within {timeout}s")


@pytest.fixture(scope="module")
def parity_server():
    """A single running Nexus serving the parity workflow on all channels."""
    api_port = _find_free_port(9820)
    app = Nexus(api_port=api_port, auto_discovery=False, enable_durability=False)

    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "echo", {"code": PARITY_CODE})
    app.register("parity", workflow.build())

    threading.Thread(target=app.start, daemon=True).start()
    _wait_until_healthy(api_port)
    try:
        yield app, api_port
    finally:
        app.stop()


def _result_via_http(api_port: int, params: dict) -> dict:
    """Drive the real HTTP channel over the wire."""
    response = requests.post(
        f"http://localhost:{api_port}/workflows/parity",
        json={"parameters": params},
        timeout=30,
    )
    assert (
        response.status_code == 200
    ), f"HTTP channel returned {response.status_code}: {response.text}"
    return response.json()["outputs"]["echo"]["result"]


def _result_via_cli(api_port: int, params: dict) -> dict:
    """Drive the real CLI channel's request shape.

    ``NexusCLI.run_workflow`` prints rather than returns, so this issues the
    exact payload that method builds (``nexus/cli/main.py``:
    ``payload = {"parameters": parameters or {}}``) against the same live
    server. The shape under test is the CLI's, not a re-invention.
    """
    from nexus.cli.main import NexusCLI

    cli = NexusCLI(base_url=f"http://localhost:{api_port}")
    response = requests.post(
        f"{cli.base_url}/workflows/parity",
        json={"parameters": params or {}},
        timeout=30,
    )
    assert (
        response.status_code == 200
    ), f"CLI channel returned {response.status_code}: {response.text}"
    return response.json()["outputs"]["echo"]["result"]


async def _result_via_mcp(app, params: dict) -> dict:
    """Drive the MCP channel's registered tool closure.

    Resolves the tool from the MCP server's ``_tool_registry`` -- the same
    dict ``_handle_call_tool`` dispatches through -- and invokes its
    ``original_function`` with the kwargs an MCP ``tools/call`` delivers.
    That closure is exactly where the channel binds its runtime inputs, so
    this covers the binding under test. It does NOT cover JSON-RPC framing or
    response formatting, which are not what parity depends on.
    """
    import json

    registry = app._mcp_server._tool_registry
    tool_name = next(n for n in registry if "parity" in n)
    tool_fn = registry[tool_name]["original_function"]

    raw = await tool_fn(**params)
    payload = json.loads(raw) if isinstance(raw, str) else raw
    # The tool surfaces a single node's ``result`` dict directly.
    return payload


@pytest.mark.regression
def test_http_channel_binds_both_shapes(parity_server):
    """HTTP MUST bind the envelope AND the top-level keys.

    Falsifying result: before the fix this returned HTTP 500 with
    ``NameError: name 'parameters' is not defined``.
    """
    _, api_port = parity_server
    result = _result_via_http(api_port, {"id": 1})
    assert result == {"via_envelope": 1, "via_toplevel": 1}, result


@pytest.mark.regression
def test_cli_channel_binds_both_shapes(parity_server):
    """The CLI's own payload shape MUST work against the same endpoint."""
    _, api_port = parity_server
    result = _result_via_cli(api_port, {"id": 1})
    assert result == {"via_envelope": 1, "via_toplevel": 1}, result


@pytest.mark.regression
@pytest.mark.asyncio
async def test_mcp_channel_binds_both_shapes(parity_server):
    """MCP MUST bind both shapes too, or parity is one-directional.

    Before the fix MCP bound ONLY the envelope, so ``via_toplevel`` raised
    ``NameError: name 'id' is not defined`` even though HTTP served it.
    """
    app, _ = parity_server
    result = await _result_via_mcp(app, {"id": 1})
    assert result == {"via_envelope": 1, "via_toplevel": 1}, result


@pytest.mark.regression
@pytest.mark.asyncio
async def test_all_three_channels_return_identical_results(parity_server):
    """THE acceptance gate: identical workflow source, identical result.

    This is the property that was actually broken. Asserting the three
    results against each other (not just against a literal) is what makes a
    future one-channel change fail here rather than in production.
    """
    app, api_port = parity_server
    params = {"id": 42}

    via_http = _result_via_http(api_port, params)
    via_cli = _result_via_cli(api_port, params)
    via_mcp = await _result_via_mcp(app, params)

    assert via_http == via_cli == via_mcp, (
        "multi-channel parity broken -- "
        f"HTTP={via_http!r} CLI={via_cli!r} MCP={via_mcp!r}"
    )
    assert via_http == {"via_envelope": 42, "via_toplevel": 42}, via_http


@pytest.mark.regression
def test_inner_parameters_key_collision_envelope_wins(parity_server):
    """Precedence is PINNED, not incidental.

    When the caller's own parameters contain a key literally named
    ``parameters``, the ENVELOPE wins -- the ``parameters`` name always
    refers to the full mapping, so ``parameters.get(...)`` cannot become
    conditional on caller data. The caller's colliding value stays reachable
    at ``parameters["parameters"]``.
    """
    _, api_port = parity_server
    app_workflow = WorkflowBuilder()
    app_workflow.add_node(
        "PythonCodeNode",
        "collide",
        {
            "code": (
                "result = {'envelope_keys': sorted(parameters.keys()), "
                "'inner': parameters.get('parameters'), 'b': parameters.get('b')}"
            )
        },
    )
    app, _ = parity_server
    app.register("parity_collide", app_workflow.build())

    response = requests.post(
        f"http://localhost:{api_port}/workflows/parity_collide",
        json={"parameters": {"parameters": {"a": 1}, "b": 2}},
        timeout=30,
    )
    assert response.status_code == 200, response.text
    result = response.json()["outputs"]["collide"]["result"]

    # Envelope wins: `parameters` is the FULL mapping, not the inner value.
    assert result["envelope_keys"] == ["b", "parameters"], result
    assert result["inner"] == {"a": 1}, result
    assert result["b"] == 2, result


@pytest.mark.regression
def test_bodyless_request_binds_empty_envelope(parity_server):
    """A POST with NO body MUST reach the workflow's own defaults.

    A workflow written to the convention supplies defaults
    (``parameters.get("message", "test")``), so an argument-less call must
    return that default. Returning a bare ``{}`` left ``parameters`` unbound
    and turned a bodyless POST into the same ``NameError`` 500 as the
    unwrapped-envelope defect -- which is why the e2e warm-up loop
    (``requests.post(url)`` with no json) was silently 500ing.
    """
    app, api_port = parity_server
    defaults_workflow = WorkflowBuilder()
    defaults_workflow.add_node(
        "PythonCodeNode",
        "defaulted",
        {"code": "result = {'message': parameters.get('message', 'fallback')}"},
    )
    app.register("parity_defaults", defaults_workflow.build())

    response = requests.post(
        f"http://localhost:{api_port}/workflows/parity_defaults", timeout=30
    )
    assert response.status_code == 200, response.text
    result = response.json()["outputs"]["defaulted"]["result"]
    assert result == {"message": "fallback"}, result


@pytest.mark.regression
def test_inputs_form_is_not_envelope_wrapped(parity_server):
    """The explicit ``inputs`` form MUST stay untouched.

    ``inputs`` is how a caller opts OUT of envelope binding; wrapping it too
    would silently change every existing low-level caller.
    """
    _, api_port = parity_server
    response = requests.post(
        f"http://localhost:{api_port}/workflows/parity",
        json={"inputs": {"parameters": {"id": 7}, "id": 7}},
        timeout=30,
    )
    assert response.status_code == 200, response.text
    result = response.json()["outputs"]["echo"]["result"]
    assert result == {"via_envelope": 7, "via_toplevel": 7}, result
