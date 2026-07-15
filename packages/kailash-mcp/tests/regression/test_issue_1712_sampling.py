# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for #1712 Wave 4 - sampling/createMessage
(MCP revision 2025-11-25, gap E1).

Behavioral pins (call the real ``MCPServer`` handler / real
``validate_sampling_messages`` — never source-grep, per ``rules/testing.md``)
for the five sub-points of the E1 gap:

1. **Tool-enabled sampling** — ``toolChoice`` is forwarded, and tool_use /
   tool_result BALANCE in the message sequence is enforced (orphan tool_use or
   orphan tool_result rejected).
2. **Content-type validation** — message content must be text / image / audio /
   tool_use / tool_result; an unknown content type is rejected.
3. **Human-in-the-loop (HITL)** — sampling routes through an injectable
   approval callback BEFORE fulfilment. No approver bound → FAILS CLOSED
   (rejected, never auto-approved). An approving approver reaches dispatch; a
   declining approver is rejected.
4. **Dedicated sampling error codes** — rejection / timeout / user-decline use
   the sampling-specific JSON-RPC error codes from ``errors.py``.
5. **Capability** — ``sampling`` is advertised as a TOP-LEVEL client-capability
   key in ``initialize`` (experimental alias retained).

All tests use REAL ``MCPServer`` objects and REAL handlers (no SDK mocking of
the class under test); a minimal capturing transport double satisfies the
``send_message`` structural contract only.
"""

import asyncio

import pytest
from kailash_mcp.errors import MCPError, MCPErrorCode
from kailash_mcp.server import MCPServer, validate_sampling_messages


class _CapturingTransport:
    """Real (non-mock) transport double capturing outbound sampling requests."""

    def __init__(self):
        self.sent: list = []

    async def send_message(self, message, client_id=None):
        self.sent.append((message, client_id))


def _make_server() -> MCPServer:
    server = MCPServer("w4-sampling-test", enable_cache=False, enable_metrics=False)
    server.client_info = {}
    server._pending_sampling_requests = {}
    server._transport = _CapturingTransport()
    # A client that advertises sampling (top-level key, spec 2025-11-25).
    server.client_info["client-1"] = {"capabilities": {"sampling": {}}}
    return server


# ---------------------------------------------------------------------------
# (2) Content-type validation
# ---------------------------------------------------------------------------


def test_validate_accepts_spec_content_types():
    """text / image / audio / tool_use+tool_result blocks all validate."""
    messages = [
        {"role": "user", "content": "plain string is text shorthand"},
        {"role": "user", "content": {"type": "text", "text": "hi"}},
        {"role": "user", "content": {"type": "image", "data": "..."}},
        {"role": "user", "content": {"type": "audio", "data": "..."}},
    ]
    assert validate_sampling_messages(messages) is None


def test_validate_rejects_unknown_content_type():
    """An unknown content type is rejected with a descriptive message."""
    err = validate_sampling_messages(
        [{"role": "user", "content": {"type": "video", "data": "x"}}]
    )
    assert err is not None
    assert "video" in err
    assert "unsupported type" in err


@pytest.mark.regression
@pytest.mark.asyncio
async def test_sampling_rejects_unknown_content_type_with_invalid_params():
    """Handler rejects an unknown content type with INVALID_PARAMS (-32602)."""
    server = _make_server()
    server.set_sampling_approver(lambda ctx: True)
    result = await server._handle_sampling_create_message(
        {"messages": [{"role": "user", "content": {"type": "video"}}]},
        "req-1",
    )
    assert "error" in result
    assert result["error"]["code"] == MCPErrorCode.INVALID_PARAMS.value
    # Rejected BEFORE any content is requested from the client.
    assert server._transport.sent == []


# ---------------------------------------------------------------------------
# (1) Tool-enabled sampling — toolChoice + tool_use/tool_result balance
# ---------------------------------------------------------------------------


def test_validate_balanced_tool_use_result():
    messages = [
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t1"}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1"}]},
    ]
    assert validate_sampling_messages(messages) is None


def test_validate_rejects_orphan_tool_use():
    """A tool_use with no matching tool_result is unbalanced → rejected."""
    err = validate_sampling_messages(
        [{"role": "assistant", "content": [{"type": "tool_use", "id": "t1"}]}]
    )
    assert err is not None
    assert "unbalanced" in err
    assert "t1" in err


def test_validate_rejects_orphan_tool_result():
    """A tool_result referencing an unknown tool_use is unbalanced → rejected."""
    err = validate_sampling_messages(
        [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "ghost"}]}]
    )
    assert err is not None
    assert "unbalanced" in err
    assert "ghost" in err


@pytest.mark.regression
@pytest.mark.asyncio
async def test_sampling_rejects_imbalanced_tool_sequence():
    server = _make_server()
    server.set_sampling_approver(lambda ctx: True)
    result = await server._handle_sampling_create_message(
        {
            "messages": [
                {"role": "assistant", "content": [{"type": "tool_use", "id": "t1"}]}
            ]
        },
        "req-2",
    )
    assert "error" in result
    assert result["error"]["code"] == MCPErrorCode.INVALID_PARAMS.value


@pytest.mark.regression
@pytest.mark.asyncio
async def test_sampling_forwards_tool_choice():
    """toolChoice is forwarded on the outbound sampling request."""
    server = _make_server()
    server.set_sampling_approver(lambda ctx: True)
    result = await server._handle_sampling_create_message(
        {
            "messages": [{"role": "user", "content": "hi"}],
            "toolChoice": {"type": "auto"},
        },
        "req-3",
    )
    assert "result" in result
    assert result["result"]["status"] == "sampling_requested"
    sent_msg, _client = server._transport.sent[0]
    assert sent_msg["params"]["tool_choice"] == {"type": "auto"}


# ---------------------------------------------------------------------------
# (3) HITL approval — fail closed / approve / decline
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_sampling_fails_closed_without_approver():
    """No approver bound → sampling is REJECTED, never auto-approved."""
    server = _make_server()
    # Deliberately do NOT bind an approver.
    result = await server._handle_sampling_create_message(
        {"messages": [{"role": "user", "content": "hi"}]},
        "req-4",
    )
    assert "error" in result
    assert result["error"]["code"] == MCPErrorCode.MCP_SAMPLING_REJECTED.value
    # Nothing dispatched — no model-generated content was requested.
    assert server._transport.sent == []
    assert server._pending_sampling_requests == {}


@pytest.mark.regression
@pytest.mark.asyncio
async def test_sampling_approver_approves_reaches_dispatch():
    server = _make_server()
    approved_contexts: list = []

    def approver(ctx):
        approved_contexts.append(ctx)
        return True

    server.set_sampling_approver(approver)
    result = await server._handle_sampling_create_message(
        {"messages": [{"role": "user", "content": "hi"}]},
        "req-5",
    )
    assert "result" in result
    assert result["result"]["status"] == "sampling_requested"
    # The approver saw the request context BEFORE dispatch.
    assert len(approved_contexts) == 1
    assert approved_contexts[0]["target_client"] == "client-1"
    assert len(server._transport.sent) == 1


@pytest.mark.regression
@pytest.mark.asyncio
async def test_sampling_async_approver_supported():
    """The approval callback may be an async coroutine (awaited)."""
    server = _make_server()

    async def approver(ctx):
        await asyncio.sleep(0)
        return True

    server.set_sampling_approver(approver)
    result = await server._handle_sampling_create_message(
        {"messages": [{"role": "user", "content": "hi"}]},
        "req-6",
    )
    assert result["result"]["status"] == "sampling_requested"


# ---------------------------------------------------------------------------
# (4) Dedicated sampling error codes — decline / timeout / error
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_sampling_decline_uses_declined_code():
    server = _make_server()
    server.set_sampling_approver(lambda ctx: False)
    result = await server._handle_sampling_create_message(
        {"messages": [{"role": "user", "content": "hi"}]},
        "req-7",
    )
    assert result["error"]["code"] == MCPErrorCode.MCP_SAMPLING_DECLINED.value
    assert server._transport.sent == []


@pytest.mark.regression
@pytest.mark.asyncio
async def test_sampling_timeout_uses_timeout_code():
    server = _make_server()

    def approver(ctx):
        raise asyncio.TimeoutError()

    server.set_sampling_approver(approver)
    result = await server._handle_sampling_create_message(
        {"messages": [{"role": "user", "content": "hi"}]},
        "req-8",
    )
    assert result["error"]["code"] == MCPErrorCode.MCP_SAMPLING_TIMEOUT.value


@pytest.mark.regression
@pytest.mark.asyncio
async def test_sampling_approver_mcperror_propagates_code():
    """An approver raising MCPError surfaces that specific code + message."""
    server = _make_server()

    def approver(ctx):
        raise MCPError(
            "policy blocked this sample",
            error_code=MCPErrorCode.MCP_SAMPLING_DECLINED,
        )

    server.set_sampling_approver(approver)
    result = await server._handle_sampling_create_message(
        {"messages": [{"role": "user", "content": "hi"}]},
        "req-9",
    )
    assert result["error"]["code"] == MCPErrorCode.MCP_SAMPLING_DECLINED.value
    assert "policy blocked" in result["error"]["message"]


@pytest.mark.regression
@pytest.mark.asyncio
async def test_sampling_approver_unexpected_error_fails_closed():
    """An approver raising an unexpected error fails CLOSED (rejected)."""
    server = _make_server()

    def approver(ctx):
        raise RuntimeError("approver crashed")

    server.set_sampling_approver(approver)
    result = await server._handle_sampling_create_message(
        {"messages": [{"role": "user", "content": "hi"}]},
        "req-10",
    )
    assert result["error"]["code"] == MCPErrorCode.MCP_SAMPLING_REJECTED.value
    assert server._transport.sent == []


def test_sampling_error_codes_are_distinct():
    """The three sampling codes are distinct and distinct from elicitation."""
    codes = {
        MCPErrorCode.MCP_SAMPLING_REJECTED.value,
        MCPErrorCode.MCP_SAMPLING_TIMEOUT.value,
        MCPErrorCode.MCP_SAMPLING_DECLINED.value,
    }
    assert len(codes) == 3
    assert MCPErrorCode.MCP_REQUEST_CANCELLED.value not in codes


# ---------------------------------------------------------------------------
# (5) Capability advertisement — top-level ``sampling`` key
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_initialize_advertises_sampling_top_level():
    server = MCPServer("w4-cap-test", enable_cache=False, enable_metrics=False)
    result = await server._handle_initialize(
        {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "c", "version": "1"},
        },
        "init-1",
        "client-1",
    )
    caps = result["result"]["capabilities"]
    # Top-level key is the spec requirement.
    assert "sampling" in caps
    # Experimental alias retained for backward compatibility.
    assert caps["experimental"]["sampling"] is True


@pytest.mark.regression
@pytest.mark.asyncio
async def test_sampling_capability_check_accepts_experimental_alias():
    """A client advertising only experimental.sampling is still recognized."""
    server = _make_server()
    server.client_info = {
        "old-client": {"capabilities": {"experimental": {"sampling": True}}}
    }
    server.set_sampling_approver(lambda ctx: True)
    result = await server._handle_sampling_create_message(
        {"messages": [{"role": "user", "content": "hi"}]},
        "req-11",
    )
    assert result["result"]["status"] == "sampling_requested"
    assert result["result"]["target_client"] == "old-client"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_sampling_no_capable_client_rejected_before_hitl():
    """No sampling-capable client → capability error (fires before HITL)."""
    server = _make_server()
    server.client_info = {"plain": {"capabilities": {}}}
    server.set_sampling_approver(lambda ctx: True)
    result = await server._handle_sampling_create_message(
        {"messages": [{"role": "user", "content": "hi"}]},
        "req-12",
    )
    assert result["error"]["code"] == -32601
    assert "No connected clients support sampling" in result["error"]["message"]


# ---------------------------------------------------------------------------
# G1-redteam Finding 3 — tool_use/tool_result balance is ORDER-aware,
# duplicate-detecting, and hashability-guarded (was id-SETS only: blind to
# order + duplicates, and an unhashable id raised an uncaught TypeError).
# ---------------------------------------------------------------------------


def test_validate_rejects_out_of_order_tool_result():
    """A tool_result whose tool_use is introduced at a LATER index is a forward
    reference — rejected (the set-based balance accepted it)."""
    messages = [
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1"}]},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t1"}]},
    ]
    err = validate_sampling_messages(messages)
    assert err is not None
    assert "not introduced by an earlier tool_use" in err


def test_validate_rejects_duplicate_tool_use_id():
    """Two tool_use blocks sharing one id are rejected (the set-based balance
    silently deduped and never saw the collision)."""
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "t1"},
                {"type": "tool_use", "id": "t1"},
            ],
        }
    ]
    err = validate_sampling_messages(messages)
    assert err is not None
    assert "duplicate tool_use id" in err


def test_validate_unhashable_tool_use_id_returns_clean_error_string():
    """An unhashable tool_use id yields an error STRING (mapped to -32602 by the
    handler), NOT an uncaught TypeError (which surfaced as -32603)."""
    messages = [
        {"role": "assistant", "content": [{"type": "tool_use", "id": ["a", "b"]}]}
    ]
    err = validate_sampling_messages(messages)
    assert err is not None
    assert "hashable" in err


def test_validate_unhashable_tool_result_ref_returns_clean_error_string():
    messages = [
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t1"}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": {"k": 1}}]},
    ]
    err = validate_sampling_messages(messages)
    assert err is not None
    assert "hashable" in err


@pytest.mark.regression
@pytest.mark.asyncio
async def test_sampling_unhashable_id_is_invalid_params_not_internal_error():
    """Through the REAL handler, an unhashable tool_use id maps to -32602
    (INVALID_PARAMS), never -32603 (INTERNAL_ERROR)."""
    server = _make_server()
    server.set_sampling_approver(lambda ctx: True)
    result = await server._handle_sampling_create_message(
        {
            "messages": [
                {"role": "assistant", "content": [{"type": "tool_use", "id": ["x"]}]}
            ]
        },
        "req-unhashable",
    )
    assert "error" in result
    assert result["error"]["code"] == MCPErrorCode.INVALID_PARAMS.value
    assert result["error"]["code"] != -32603


# ---------------------------------------------------------------------------
# G1-redteam Finding 4 — sampling capability check treats ONLY a dict as
# advertised; an explicit false/0/"" is NOT advertised (was fail-open under a
# bare ``is not None`` check), while an empty {} still counts.
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("bad_value", [False, 0, ""])
async def test_sampling_explicit_falsey_capability_not_advertised(bad_value):
    """A non-dict ``sampling`` value fails CLOSED → no-capable-client error."""
    server = _make_server()
    server.client_info = {"c": {"capabilities": {"sampling": bad_value}}}
    server.set_sampling_approver(lambda ctx: True)
    result = await server._handle_sampling_create_message(
        {"messages": [{"role": "user", "content": "hi"}]},
        "req-falsey",
    )
    assert result["error"]["code"] == -32601
    assert "No connected clients support sampling" in result["error"]["message"]


@pytest.mark.regression
@pytest.mark.asyncio
async def test_sampling_empty_dict_capability_is_advertised():
    """An empty ``sampling: {}`` object DOES count as advertised (reaches
    dispatch)."""
    server = _make_server()
    server.client_info = {"c": {"capabilities": {"sampling": {}}}}
    server.set_sampling_approver(lambda ctx: True)
    result = await server._handle_sampling_create_message(
        {"messages": [{"role": "user", "content": "hi"}]},
        "req-empty",
    )
    assert result["result"]["status"] == "sampling_requested"
