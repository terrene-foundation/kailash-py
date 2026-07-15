# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for #1712 Wave 4 - elicitation/create
(MCP revision 2025-11-25, gap E3).

Behavioral pins (call the REAL ``ElicitationSystem`` / real ``MCPServer``
handler & dispatch path — never source-grep, per ``rules/testing.md``) for the
five sub-points of the E3 gap:

1. **{mode, message, requestedSchema} request shape** — the outbound
   ``elicitation/create`` params carry a ``mode`` field. ``form`` mode restricts
   ``requestedSchema`` to a FLAT object of primitives (nested objects / arrays
   rejected at request time). ``url`` mode carries an ``elicitationId`` + a
   server-identity binding and forces sensitive data OUT-OF-BAND (no inline
   requestedSchema / field values in the JSON-RPC params).
2. **-32602 on undeclared/unknown mode** — a mode not in {form, url} is
   rejected with ``INVALID_PARAMS`` (-32602).
3. **Capability-gated** — before sending, the send-half checks a client
   advertised the ``elicitation`` capability; if none has, it FAILS CLOSED
   (never dispatches blindly).
4. **Three-action accept/decline/cancel response model** — the server dispatch
   path maps accept → provide_input, decline → declined cancel, cancel →
   cancelled cancel, each distinguishable.
5. **Advertise ``elicitation`` capability in initialize** — the server's
   ``_handle_initialize`` advertises ``elicitation`` (form + url modes) at the
   top level, with the experimental alias retained.

All tests use REAL objects (no SDK mocking of the class under test); the
in-process ``async def`` send-callable is a Protocol-Satisfying Deterministic
Adapter (rules/testing.md § Tier 2 Exception) conforming to the ``SendFn``
protocol — it captures outbound JSON-RPC ``elicitation/create`` requests so the
test can inspect them, and delivers responses through the SAME production
dispatch path (``MCPServer._route_server_initiated_response``) the server uses
for real client transports.
"""

import asyncio

import pytest
from kailash_mcp.advanced.features import ElicitationSystem
from kailash_mcp.errors import MCPError, MCPErrorCode, ValidationError
from kailash_mcp.server import MCPServer


class _CapturingTransport:
    """Real (non-mock) deterministic adapter capturing outbound requests."""

    def __init__(self):
        self.sent: list = []

    async def send_message(self, message, client_id=None):
        self.sent.append(message)


def _make_system(*, capability: bool = True, server_identity=None):
    """A real ElicitationSystem wired to a capturing transport.

    ``capability`` drives the bound capability provider so the capability gate
    can be exercised without a full server.
    """
    transport = _CapturingTransport()
    system = ElicitationSystem(
        send=transport.send_message,
        server_identity=server_identity or {"name": "test-server"},
        capability_provider=lambda: capability,
    )
    return system, transport


# ---------------------------------------------------------------------------
# (1) form mode — flat-primitive schema accepted, nested rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_form_mode_flat_primitive_schema_accepted():
    """A flat object of primitives (string/number/boolean/enum) is accepted and
    dispatched with the {mode, message, requestedSchema} shape."""
    system, transport = _make_system()
    flat_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
            "score": {"type": "number"},
            "active": {"type": "boolean"},
            "tier": {"enum": ["free", "pro"]},
        },
    }
    fut = asyncio.ensure_future(
        system.request_input("Fill the form", input_schema=flat_schema, timeout=1.0)
    )
    await asyncio.sleep(0.02)
    assert len(transport.sent) == 1
    params = transport.sent[0]["params"]
    assert params["mode"] == "form"
    assert params["message"] == "Fill the form"
    assert params["requestedSchema"] == flat_schema
    fut.cancel()
    with pytest.raises((asyncio.CancelledError, MCPError)):
        await fut


@pytest.mark.asyncio
async def test_form_mode_nested_object_schema_rejected():
    """A property with a nested object is rejected with INVALID_PARAMS."""
    system, transport = _make_system()
    nested_schema = {
        "type": "object",
        "properties": {
            "addr": {"type": "object", "properties": {"city": {"type": "string"}}}
        },
    }
    with pytest.raises(MCPError) as exc:
        await system.request_input("x", input_schema=nested_schema, mode="form")
    assert exc.value.error_code == MCPErrorCode.INVALID_PARAMS
    assert exc.value.error_code.value == -32602
    # Nothing was dispatched — rejection is at request time, before transport.
    assert transport.sent == []


@pytest.mark.asyncio
async def test_form_mode_array_property_schema_rejected():
    """A property with an array type is rejected with INVALID_PARAMS."""
    system, _ = _make_system()
    array_schema = {
        "type": "object",
        "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
    }
    with pytest.raises(MCPError) as exc:
        await system.request_input("x", input_schema=array_schema, mode="form")
    assert exc.value.error_code == MCPErrorCode.INVALID_PARAMS


# ---------------------------------------------------------------------------
# (1) url mode — elicitationId + server-identity + no inline sensitive data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_url_mode_out_of_band_shape():
    """url mode carries elicitationId + server identity and inlines NO
    sensitive collection surface (no requestedSchema / field values)."""
    system, transport = _make_system(server_identity={"name": "issuer-1"})
    fut = asyncio.ensure_future(
        system.request_input(
            "Confirm at the link", mode="url", url="https://srv/e/abc", timeout=1.0
        )
    )
    await asyncio.sleep(0.02)
    assert len(transport.sent) == 1
    params = transport.sent[0]["params"]
    assert params["mode"] == "url"
    assert params["url"] == "https://srv/e/abc"
    # elicitationId present so the client can correlate the out-of-band flow.
    assert params["elicitationId"]
    # server-identity binding present so the client can verify the issuer.
    assert params["server"] == {"name": "issuer-1"}
    # SECURITY INVARIANT: no inline collection surface / field values.
    assert "requestedSchema" not in params
    assert "content" not in params
    fut.cancel()
    with pytest.raises((asyncio.CancelledError, MCPError)):
        await fut


@pytest.mark.asyncio
async def test_url_mode_rejects_inline_schema():
    """Passing an inline schema in url mode is rejected — it would inline the
    collection surface url mode exists to keep out-of-band."""
    system, transport = _make_system()
    with pytest.raises(MCPError) as exc:
        await system.request_input(
            "x",
            input_schema={"type": "object", "properties": {"pin": {"type": "string"}}},
            mode="url",
            url="https://srv/e/1",
        )
    assert exc.value.error_code == MCPErrorCode.INVALID_PARAMS
    assert transport.sent == []


@pytest.mark.asyncio
async def test_url_mode_requires_url():
    """url mode with no url is rejected with INVALID_PARAMS."""
    system, _ = _make_system()
    with pytest.raises(MCPError) as exc:
        await system.request_input("x", mode="url")
    assert exc.value.error_code == MCPErrorCode.INVALID_PARAMS


@pytest.mark.asyncio
async def test_url_mode_requires_server_identity():
    """url mode with no bound server identity is refused (unverifiable issuer)."""
    system = ElicitationSystem(
        send=_CapturingTransport().send_message,
        server_identity=None,
        capability_provider=lambda: True,
    )
    with pytest.raises(MCPError) as exc:
        await system.request_input("x", mode="url", url="https://srv/e/1")
    assert exc.value.error_code == MCPErrorCode.INVALID_REQUEST


# ---------------------------------------------------------------------------
# (2) -32602 on undeclared / unknown mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_mode_rejected_with_invalid_params():
    """A mode not in {form, url} → INVALID_PARAMS (-32602), before transport."""
    system, transport = _make_system()
    with pytest.raises(MCPError) as exc:
        await system.request_input("x", mode="webhook")
    assert exc.value.error_code == MCPErrorCode.INVALID_PARAMS
    assert exc.value.error_code.value == -32602
    assert transport.sent == []


# ---------------------------------------------------------------------------
# (3) capability-gated — no client elicitation capability → refused
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_capability_gate_refuses_when_no_client_advertises():
    """When the capability provider reports no client supports elicitation, the
    send-half FAILS CLOSED and dispatches nothing."""
    system, transport = _make_system(capability=False)
    with pytest.raises(MCPError) as exc:
        await system.request_input("x", mode="form")
    assert exc.value.error_code == MCPErrorCode.INVALID_REQUEST
    assert transport.sent == []


@pytest.mark.asyncio
async def test_capability_gate_allows_when_client_advertises():
    """When a client advertises elicitation, the request dispatches."""
    system, transport = _make_system(capability=True)
    fut = asyncio.ensure_future(system.request_input("x", mode="form", timeout=1.0))
    await asyncio.sleep(0.02)
    assert len(transport.sent) == 1
    fut.cancel()
    with pytest.raises((asyncio.CancelledError, MCPError)):
        await fut


# ---------------------------------------------------------------------------
# (3) capability detection at the MCPServer level (real handler)
# ---------------------------------------------------------------------------


def test_server_detects_elicitation_capability_top_level():
    """A client advertising the top-level ``elicitation`` capability is seen."""
    server = MCPServer("s", enable_cache=False, enable_metrics=False)
    server.client_info["c1"] = {"capabilities": {"elicitation": {}}}
    assert server._any_client_advertises_elicitation() is True


def test_server_detects_elicitation_capability_experimental_alias():
    """The experimental.elicitation alias is honored."""
    server = MCPServer("s", enable_cache=False, enable_metrics=False)
    server.client_info["c1"] = {"capabilities": {"experimental": {"elicitation": True}}}
    assert server._any_client_advertises_elicitation() is True


def test_server_no_elicitation_capability_when_absent():
    """A client that does not advertise elicitation is not counted."""
    server = MCPServer("s", enable_cache=False, enable_metrics=False)
    server.client_info["c1"] = {"capabilities": {"sampling": {}}}
    assert server._any_client_advertises_elicitation() is False


# ---------------------------------------------------------------------------
# (4) three-action accept / decline / cancel routing (real dispatch path)
# ---------------------------------------------------------------------------


async def _run_action(server, transport, action, content=None):
    """Drive one elicitation round through the real server dispatch path."""
    fut = asyncio.ensure_future(
        server.elicitation_system.request_input("prompt", mode="form", timeout=1.0)
    )
    await asyncio.sleep(0.02)
    rid = transport.sent[-1]["id"]
    result = {"action": action}
    if content is not None:
        result["content"] = content
    routed = await server._route_server_initiated_response(rid, {"result": result})
    return fut, routed


def _server_with_elicitation():
    server = MCPServer("s", enable_cache=False, enable_metrics=False)
    server.client_info["c1"] = {"capabilities": {"elicitation": {}}}
    transport = _CapturingTransport()
    server.elicitation_system.bind_transport(transport.send_message)
    return server, transport


@pytest.mark.asyncio
async def test_route_accept_returns_content():
    server, transport = _server_with_elicitation()
    fut, routed = await _run_action(server, transport, "accept", {"answer": 42})
    assert routed is True
    assert await fut == {"answer": 42}


@pytest.mark.asyncio
async def test_route_decline_cancels_with_declined_reason():
    server, transport = _server_with_elicitation()
    fut, routed = await _run_action(server, transport, "decline")
    assert routed is True
    with pytest.raises(MCPError) as exc:
        await fut
    assert exc.value.error_code == MCPErrorCode.MCP_REQUEST_CANCELLED
    assert "decline" in str(exc.value)


@pytest.mark.asyncio
async def test_route_cancel_cancels_with_cancelled_reason():
    server, transport = _server_with_elicitation()
    fut, routed = await _run_action(server, transport, "cancel")
    assert routed is True
    with pytest.raises(MCPError) as exc:
        await fut
    assert exc.value.error_code == MCPErrorCode.MCP_REQUEST_CANCELLED
    assert "cancel" in str(exc.value)


# ---------------------------------------------------------------------------
# (5) initialize advertises the elicitation capability (form + url modes)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initialize_advertises_elicitation_capability():
    server = MCPServer("s", enable_cache=False, enable_metrics=False)
    resp = await server._handle_initialize(
        {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "c"},
        },
        1,
        "c1",
    )
    caps = resp["result"]["capabilities"]
    # Top-level elicitation capability advertises BOTH modes.
    assert "elicitation" in caps
    assert set(caps["elicitation"]["modes"]) == {"form", "url"}
    # Experimental alias retained for backward compatibility.
    assert caps["experimental"]["elicitation"] is True


# ---------------------------------------------------------------------------
# G1-redteam Finding 1 — the flat-primitive form guard is EXHAUSTIVE:
# every structural JSON-Schema vector that reintroduces nesting/indirection is
# rejected with -32602 at request time (nothing dispatched). Each vector was a
# CONFIRMED bypass of the properties-only guard.
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.parametrize(
    "bad_schema",
    [
        # top-level additionalProperties whose value is a (nested-object) schema
        {
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "additionalProperties": {"type": "object"},
        },
        # top-level additionalProperties: true (open object)
        {"type": "object", "additionalProperties": True},
        # top-level patternProperties (arbitrarily-keyed subschemas)
        {"type": "object", "patternProperties": {"^x": {"type": "string"}}},
        # top-level combinators
        {"type": "object", "allOf": [{"type": "object"}]},
        {"type": "object", "anyOf": [{"type": "string"}]},
        {"type": "object", "oneOf": [{"type": "string"}]},
        {"type": "object", "not": {"type": "string"}},
        {"type": "object", "$ref": "#/$defs/x"},
        {"type": "object", "$defs": {"x": {"type": "string"}}},
        # a property carrying $ref alongside a primitive type sibling
        {"type": "object", "properties": {"a": {"$ref": "#/d", "type": "string"}}},
        # an enum whose members are objects / arrays
        {"type": "object", "properties": {"a": {"enum": [{"o": 1}]}}},
        {"type": "object", "properties": {"a": {"enum": [["x"]]}}},
        # a property whose type is a LIST/union (previously an uncaught TypeError)
        {"type": "object", "properties": {"a": {"type": ["string", "object"]}}},
    ],
    ids=[
        "additionalProperties-as-schema",
        "additionalProperties-true",
        "patternProperties",
        "allOf",
        "anyOf",
        "oneOf",
        "not",
        "ref",
        "defs",
        "prop-ref-plus-type",
        "enum-of-objects",
        "enum-of-arrays",
        "type-list-union",
    ],
)
@pytest.mark.asyncio
async def test_form_mode_rejects_structural_bypass_vectors(bad_schema):
    """Each structural bypass vector is rejected with a clean -32602 at request
    time; the type-list vector in particular no longer raises an uncaught
    TypeError. Nothing reaches the transport."""
    system, transport = _make_system()
    with pytest.raises(MCPError) as exc:
        await system.request_input("x", input_schema=bad_schema, mode="form")
    assert exc.value.error_code == MCPErrorCode.INVALID_PARAMS
    assert exc.value.error_code.value == -32602
    assert transport.sent == []


@pytest.mark.regression
@pytest.mark.asyncio
async def test_form_mode_accepts_additional_properties_false_and_enum_scalars():
    """A closed object (additionalProperties:false) with primitive + enum-scalar
    properties is still accepted and dispatched (no over-rejection)."""
    system, transport = _make_system()
    good = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string"},
            "tier": {"enum": ["free", "pro", 1, True, None]},
            "level": {"type": "integer", "enum": [1, 2, 3]},
        },
    }
    fut = asyncio.ensure_future(
        system.request_input("Fill", input_schema=good, mode="form", timeout=1.0)
    )
    await asyncio.sleep(0.02)
    assert len(transport.sent) == 1
    fut.cancel()
    with pytest.raises((asyncio.CancelledError, MCPError)):
        await fut


# ---------------------------------------------------------------------------
# G1-redteam Finding 2 — form-mode response validation enforces
# additionalProperties:false, so a response carrying undeclared (nested) keys
# is rejected instead of passing validation.
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_form_response_rejects_undeclared_nested_key():
    """A response carrying a key the form schema did not declare is rejected."""
    system, transport = _make_system()
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    fut = asyncio.ensure_future(
        system.request_input("Fill", input_schema=schema, mode="form", timeout=1.0)
    )
    await asyncio.sleep(0.02)
    rid = transport.sent[-1]["id"]
    # Undeclared nested key alongside the declared field.
    await system.provide_input(rid, {"name": "alice", "evil": {"nested": 1}})
    with pytest.raises((ValidationError, MCPError)):
        await fut


@pytest.mark.regression
@pytest.mark.asyncio
async def test_form_response_accepts_declared_keys_only():
    """A response with only declared keys still validates and returns."""
    system, transport = _make_system()
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    fut = asyncio.ensure_future(
        system.request_input("Fill", input_schema=schema, mode="form", timeout=1.0)
    )
    await asyncio.sleep(0.02)
    rid = transport.sent[-1]["id"]
    await system.provide_input(rid, {"name": "alice"})
    assert await fut == {"name": "alice"}


# ---------------------------------------------------------------------------
# G1-redteam Finding 4 — the elicitation capability check treats ONLY a dict as
# advertised; an explicit false/0/"" is NOT advertised (was fail-open), while an
# empty {} still counts.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_value", [False, 0, ""])
def test_elicitation_explicit_falsey_capability_not_advertised(bad_value):
    """An explicit non-dict elicitation value fails CLOSED (not advertised)."""
    server = MCPServer("s", enable_cache=False, enable_metrics=False)
    server.client_info["c1"] = {"capabilities": {"elicitation": bad_value}}
    assert server._any_client_advertises_elicitation() is False
    assert (
        MCPServer._client_advertises_elicitation(
            {"capabilities": {"elicitation": bad_value}}
        )
        is False
    )


def test_elicitation_empty_dict_capability_is_advertised():
    """An empty {} elicitation object DOES count as advertised."""
    server = MCPServer("s", enable_cache=False, enable_metrics=False)
    server.client_info["c1"] = {"capabilities": {"elicitation": {}}}
    assert server._any_client_advertises_elicitation() is True
