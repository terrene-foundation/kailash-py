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

    The opt-out is available HERE because ``WorkflowRequest`` offers BOTH
    ``inputs`` and ``parameters``, so picking one carries meaning. It does NOT
    generalise by field name -- see
    ``test_single_slot_channels_do_not_read_inputs_as_opt_out`` below.
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


# ---------------------------------------------------------------------------
# The cross-surface rule itself
#
# The tests above each drive ONE surface. These assert the PROPERTY that makes
# the surfaces a set rather than a list: equivalent calls agree, and the one
# place they deliberately differ is pinned so it cannot become an accident.
# ---------------------------------------------------------------------------


def _parameters_view_via_channels(params: dict) -> list:
    """Run the parity workflow on every single-slot channel's ``inputs``.

    Returns one ``parameters`` view per channel, so the caller can assert them
    against the HTTP surface AND against each other.
    """
    import asyncio

    from kailash.channels.mcp_channel import MCPChannel
    from kailash.runtime.async_local import AsyncLocalRuntime

    probe = WorkflowBuilder()
    probe.add_node(
        "PythonCodeNode",
        "probe",
        {"code": "result = {'view': dict(parameters)}"},
    )

    async def _run():
        views = []
        # MCPChannel.execute_workflow -- single `inputs` slot.
        channel = MCPChannel.__new__(MCPChannel)
        channel.runtime = AsyncLocalRuntime()
        channel._workflow_registry = {"probe": probe.build()}
        response = await channel._handle_execute_workflow(
            {"workflow_name": "probe", "inputs": params}
        )
        assert response.get("success"), response
        views.append(response["results"]["probe"]["result"]["view"])
        return views

    return asyncio.run(_run())


@pytest.mark.regression
def test_equivalent_calls_agree_across_http_and_single_slot_channels(parity_server):
    """THE rule: the same INTENT gives the same ``parameters`` view everywhere.

    ``WorkflowRequest`` exposes two slots, so its arguments slot is
    ``parameters``. The channels expose one, so theirs is ``inputs``. Those
    are the EQUIVALENT calls, and they MUST agree -- that equivalence is what
    'multi-channel parity' means for a workflow reading ``parameters.get()``.

    Falsifying result: if either surface stopped binding, or one double-bound,
    the two views differ and this fails. Comparing the surfaces against each
    other (not against a literal) is what makes a one-sided future change fail
    here rather than in production.
    """
    _, api_port = parity_server
    params = {"a": 1}

    probe_workflow = WorkflowBuilder()
    probe_workflow.add_node(
        "PythonCodeNode", "probe", {"code": "result = {'view': dict(parameters)}"}
    )
    app, _ = parity_server
    app.register("parity_probe", probe_workflow.build())

    response = requests.post(
        f"http://localhost:{api_port}/workflows/parity_probe",
        json={"parameters": params},
        timeout=30,
    )
    assert response.status_code == 200, response.text
    via_http = response.json()["outputs"]["probe"]["result"]["view"]

    for via_channel in _parameters_view_via_channels(params):
        assert via_channel == via_http, (
            "equivalent calls disagree -- HTTP `{'parameters': P}` and the "
            f"channel `inputs=P` must give one view: HTTP={via_http!r} "
            f"channel={via_channel!r}"
        )
    assert via_http.get("a") == 1, via_http


@pytest.mark.regression
def test_caller_parameters_key_is_clobbered_identically_on_every_surface(
    parity_server,
):
    """The clobber is a BINDER property, not a per-channel divergence.

    ``bind_parameter_envelope`` is ``{**body, "parameters": body}``, so a
    caller whose payload already has a ``parameters`` key does not get that
    value at ``parameters`` -- the envelope does. That is intentional (the
    envelope must not become conditional on caller data), and it is CONSISTENT
    across surfaces, which is the half nothing asserted before: the binder
    test and the HTTP collision test each pinned ONE surface, so a channel
    that clobbered differently would have passed both.

    Falsifying result: if either surface stopped clobbering, or clobbered to a
    different shape, the two views diverge and this fails.
    """
    _, api_port = parity_server
    colliding = {"parameters": {"inner": 1}, "b": 2}

    probe_workflow = WorkflowBuilder()
    probe_workflow.add_node(
        "PythonCodeNode", "probe", {"code": "result = {'view': dict(parameters)}"}
    )
    app, _ = parity_server
    app.register("parity_probe_clobber", probe_workflow.build())

    response = requests.post(
        f"http://localhost:{api_port}/workflows/parity_probe_clobber",
        json={"parameters": colliding},
        timeout=30,
    )
    assert response.status_code == 200, response.text
    via_http = response.json()["outputs"]["probe"]["result"]["view"]

    (via_channel,) = _parameters_view_via_channels(colliding)

    # The envelope won on BOTH surfaces, to the SAME shape.
    assert via_http == via_channel, (
        "the `parameters`-key clobber differs by surface -- it is a property "
        f"of the shared binder, so it must not: HTTP={via_http!r} "
        f"channel={via_channel!r}"
    )
    assert via_http == colliding, via_http
    # The caller's own colliding value is not lost, just relocated.
    assert via_http["parameters"] == {"inner": 1}, via_http


@pytest.mark.regression
def test_single_slot_channels_do_not_read_inputs_as_opt_out(parity_server):
    """The opt-out is structural, and its boundary is PINNED.

    A field named ``inputs`` is an opt-out only where the caller was given a
    second slot to express the choice. On a single-slot channel the same name
    is the arguments slot and BINDS -- so a body that looks identical produces
    deliberately different views on the two surfaces.

    This asymmetry is a consequence of the rule, not an oversight, and it is
    asserted here so a future change to it fails loudly instead of silently
    re-deciding which surfaces envelope. Falsifying result: were the channels
    to treat ``inputs`` as an opt-out, the channel view would equal the HTTP
    view here -- and every ``parameters.get(...)`` workflow would be broken on
    those channels, which is the defect this whole file regresses against.
    """
    _, api_port = parity_server
    body = {"parameters": {"a": 1}}

    probe_workflow = WorkflowBuilder()
    probe_workflow.add_node(
        "PythonCodeNode", "probe", {"code": "result = {'view': dict(parameters)}"}
    )
    app, _ = parity_server
    app.register("parity_probe_optout", probe_workflow.build())

    # HTTP `inputs` -- the caller CHOSE raw, so the mapping is untouched.
    response = requests.post(
        f"http://localhost:{api_port}/workflows/parity_probe_optout",
        json={"inputs": body},
        timeout=30,
    )
    assert response.status_code == 200, response.text
    via_http_optout = response.json()["outputs"]["probe"]["result"]["view"]
    assert via_http_optout == {"a": 1}, via_http_optout

    # Channel `inputs` -- the sole arguments slot, so it BINDS.
    (via_channel,) = _parameters_view_via_channels(body)
    assert via_channel == {"parameters": {"a": 1}}, via_channel
    assert via_channel != via_http_optout, (
        "the opt-out must NOT generalise by field name: a single-slot channel "
        "that stopped binding leaves `parameters.get(...)` workflows broken "
        "with no way for the caller to opt IN"
    )
