# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for #1712 Wave 2 - server lifecycle & list capabilities
(MCP revision 2025-11-25).

Behavioral pins (call the real handler on a real ``MCPServer``, assert the
returned envelope - never source-grep, per ``rules/testing.md``) for the four
server-side gaps:

* **B1** protocolVersion negotiation reaches ``2025-11-25`` (newest supported).
* **D1** opaque-cursor pagination (nextCursor round-trip + ``-32602`` on a bad
  cursor) on tools/list AND prompts/list AND the new resources/templates/list;
  the server chooses the page size (no client ``limit`` needed to page).
* **D2** completion/complete ranks candidates (exact > prefix > substring)
  BEFORE the 100-item cap; the ``completions`` capability is advertised
  top-level.
* **D3** notifications/message is EMITTED, gated by the per-client level set via
  logging/setLevel (below-level suppressed), with secrets/PII redacted.
"""

import pytest

from kailash_mcp.server import (
    LATEST_PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    MCPServer,
    negotiate_protocol_version,
)

_PAGE = 100  # server-chosen page size (_DEFAULT_PAGE_SIZE)


def _make_server() -> MCPServer:
    """A minimal MCPServer with no cache/metrics/auth for handler pins."""
    return MCPServer(
        "lifecycle-lists-test",
        enable_cache=False,
        enable_metrics=False,
    )


# ---------------------------------------------------------------------------
# B1 - protocolVersion reaches 2025-11-25
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_2025_11_25_is_newest_supported():
    """2025-11-25 is in the supported set AND is the newest (latest)."""
    assert "2025-11-25" in SUPPORTED_PROTOCOL_VERSIONS
    assert LATEST_PROTOCOL_VERSION == "2025-11-25"
    assert SUPPORTED_PROTOCOL_VERSIONS[0] == "2025-11-25"


@pytest.mark.regression
def test_negotiate_echoes_2025_11_25():
    """A client requesting 2025-11-25 gets it echoed back verbatim."""
    assert negotiate_protocol_version("2025-11-25") == "2025-11-25"


@pytest.mark.regression
def test_negotiate_unknown_yields_2025_11_25():
    """An unsupported/absent version negotiates DOWN to the newest (2025-11-25)."""
    assert negotiate_protocol_version("1999-01-01") == "2025-11-25"
    assert negotiate_protocol_version(None) == "2025-11-25"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_initialize_advertises_2025_11_25_and_new_capabilities():
    """initialize echoes 2025-11-25 + advertises completions + resourceTemplates."""
    server = _make_server()
    resp = await server._handle_initialize(
        {"protocolVersion": "2025-11-25"}, request_id=1, client_id="c1"
    )
    result = resp["result"]
    assert result["protocolVersion"] == "2025-11-25"
    caps = result["capabilities"]
    # D2 - top-level completions capability (spec 2025-11-25).
    assert "completions" in caps
    # experimental.completion alias retained for backward-compat.
    assert caps["experimental"]["completion"] is True
    # D1 - resource templates advertised under resources.
    assert caps["resources"]["resourceTemplates"] == {"listSupported": True}


# ---------------------------------------------------------------------------
# D1 - opaque-cursor pagination across the list surfaces
# ---------------------------------------------------------------------------


async def _first_and_second_page(server, method, list_key):
    """Drive one list handler through page 1 + page 2 via its nextCursor."""
    handler = getattr(server, method)
    page1 = (await handler({}, request_id=1))["result"]
    assert len(page1[list_key]) == _PAGE
    assert "nextCursor" in page1, "server must emit a cursor without a client limit"

    page2 = (await handler({"cursor": page1["nextCursor"]}, request_id=2))["result"]
    return page1, page2


@pytest.mark.regression
@pytest.mark.asyncio
async def test_tools_list_cursor_round_trips_and_rejects_bad_cursor():
    """tools/list pages via nextCursor; a bad cursor -> -32602."""
    server = _make_server()
    for i in range(150):
        server._tool_registry[f"tool{i:03d}"] = {
            "description": "",
            "input_schema": {},
        }

    page1, page2 = await _first_and_second_page(server, "_handle_list_tools", "tools")
    assert len(page2["tools"]) == 50
    assert "nextCursor" not in page2  # 150 total, second page exhausts it

    # No duplicates across pages (real position advance, not a repeat).
    names = {t["name"] for t in page1["tools"]} | {t["name"] for t in page2["tools"]}
    assert len(names) == 150

    bad = await server._handle_list_tools({"cursor": "not-a-real-cursor"}, request_id=3)
    assert "result" not in bad
    assert bad["error"]["code"] == -32602


@pytest.mark.regression
@pytest.mark.asyncio
async def test_prompts_list_cursor_round_trips_and_rejects_bad_cursor():
    """prompts/list pages via nextCursor; a bad cursor -> -32602."""
    server = _make_server()
    for i in range(150):
        server._prompt_registry[f"prompt{i:03d}"] = {
            "description": "",
            "arguments": [],
        }

    _, page2 = await _first_and_second_page(server, "_handle_list_prompts", "prompts")
    assert len(page2["prompts"]) == 50

    bad = await server._handle_list_prompts({"cursor": "bogus"}, request_id=3)
    assert "result" not in bad
    assert bad["error"]["code"] == -32602


@pytest.mark.regression
@pytest.mark.asyncio
async def test_resource_templates_list_cursor_round_trips_and_rejects_bad_cursor():
    """resources/templates/list lists template-URIs, pages, and rejects a bad cursor."""
    server = _make_server()
    # 150 templates (URI carries a {placeholder}) + one concrete resource.
    for i in range(150):
        server._resource_registry[f"res://item/{{id{i:03d}}}"] = {
            "name": f"item{i:03d}",
            "description": "",
            "mime_type": "application/json",
        }
    server._resource_registry["res://static/readme"] = {
        "name": "readme",
        "description": "",
        "mime_type": "text/plain",
    }

    page1 = (await server._handle_list_resource_templates({}, request_id=1))["result"]
    assert len(page1["resourceTemplates"]) == _PAGE
    # concrete (placeholder-free) resource is NOT a template.
    assert all("{" in tpl["uriTemplate"] for tpl in page1["resourceTemplates"])
    assert page1["resourceTemplates"][0]["uriTemplate"].startswith("res://item/")
    assert "nextCursor" in page1

    page2 = (
        await server._handle_list_resource_templates(
            {"cursor": page1["nextCursor"]}, request_id=2
        )
    )["result"]
    assert len(page2["resourceTemplates"]) == 50  # 150 templates, static excluded
    assert "nextCursor" not in page2

    bad = await server._handle_list_resource_templates({"cursor": "nope"}, request_id=3)
    assert "result" not in bad
    assert bad["error"]["code"] == -32602


@pytest.mark.regression
@pytest.mark.asyncio
async def test_resource_templates_dispatch_branch_wired():
    """resources/templates/list is routed by the live WS dispatcher."""
    server = _make_server()
    server._resource_registry["res://doc/{name}"] = {
        "name": "doc",
        "description": "",
        "mime_type": "text/plain",
    }
    resp = await server._dispatch_ws_method(
        "resources/templates/list", {}, request_id=1, client_id="c1"
    )
    assert resp["result"]["resourceTemplates"][0]["uriTemplate"] == "res://doc/{name}"


# ---------------------------------------------------------------------------
# D2 - completion ranking (exact > prefix > substring) before the cap
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_completion_ranks_exact_prefix_substring():
    """completion/complete orders exact, then prefix, then substring matches."""
    server = _make_server()
    # Insert in a deliberately NON-ranked order to prove sorting happens.
    for name in ("barfoo", "foobar", "foo"):
        server._tool_registry[name] = {"description": "", "inputSchema": {}}

    resp = await server._handle_completion_complete(
        {"ref": {"type": "tool"}, "argument": {"value": "foo"}}, request_id=1
    )
    values = resp["result"]["completion"]["values"]
    names = [v["name"] for v in values]
    assert names == ["foo", "foobar", "barfoo"], names
    assert resp["result"]["completion"]["total"] == 3


@pytest.mark.regression
@pytest.mark.asyncio
async def test_completion_cap_keeps_top_ranked():
    """The 100-item cap keeps the TOP-ranked candidates, not a registry slice."""
    server = _make_server()
    # 120 substring-only matches + 1 exact. The exact MUST survive the cap.
    for i in range(120):
        server._tool_registry[f"zzz-match{i:03d}"] = {
            "description": "",
            "inputSchema": {},
        }
    server._tool_registry["match"] = {"description": "", "inputSchema": {}}

    resp = await server._handle_completion_complete(
        {"ref": {"type": "tool"}, "argument": {"value": "match"}}, request_id=1
    )
    completion = resp["result"]["completion"]
    assert completion["total"] == 121
    assert completion["hasMore"] is True
    assert len(completion["values"]) == 100
    # The exact match ranked first -> it is in the retained top-100.
    assert completion["values"][0]["name"] == "match"


# ---------------------------------------------------------------------------
# D3 - notifications/message emission, level-gated, redacted
# ---------------------------------------------------------------------------


class _CaptureTransport:
    """Minimal WS transport double that records every notification sent."""

    def __init__(self):
        self.sent = []

    async def send_message(self, message, client_id=None):
        self.sent.append((client_id, message))


def _server_with_client(level="WARNING"):
    """A server with one initialized client at a given minimum log level."""
    server = _make_server()
    server._transport = _CaptureTransport()
    server.client_info["c1"] = {"capabilities": {}, "name": "c", "version": "1"}
    server._client_log_levels["c1"] = level
    return server


@pytest.mark.regression
@pytest.mark.asyncio
async def test_setlevel_records_per_client_level():
    """logging/setLevel records the per-client minimum level for gating."""
    server = _make_server()
    resp = await server._handle_logging_set_level(
        {"level": "error", "client_id": "c1"}, request_id=1
    )
    assert resp["result"]["level"] == "ERROR"
    assert server._client_log_levels["c1"] == "ERROR"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_message_at_or_above_level_is_emitted_and_redacted():
    """An at/above-level notifications/message is sent with data redacted."""
    server = _server_with_client(level="WARNING")

    sent = await server.send_log_message(
        "ERROR",
        {"api_key": "sk-secret0123456789ab", "note": "email a@b.com"},
        logger_name="db",
    )
    assert sent == 1
    client_id, message = server._transport.sent[0]
    assert client_id == "c1"
    assert message["method"] == "notifications/message"
    assert message["params"]["level"] == "ERROR"
    assert message["params"]["logger"] == "db"
    # Secret KEY redacted; PII scrubbed from the string value.
    assert message["params"]["data"]["api_key"] == "[REDACTED]"
    assert "a@b.com" not in message["params"]["data"]["note"]
    assert "[REDACTED]" in message["params"]["data"]["note"]


@pytest.mark.regression
@pytest.mark.asyncio
async def test_message_below_level_is_suppressed():
    """A below-level notifications/message is suppressed (not sent)."""
    server = _server_with_client(level="WARNING")

    sent = await server.send_log_message("INFO", {"note": "chatty"})
    assert sent == 0
    assert server._transport.sent == []


@pytest.mark.regression
@pytest.mark.asyncio
async def test_message_invalid_level_raises():
    """An unknown severity is a typed error, not a silent drop."""
    server = _server_with_client()
    with pytest.raises(ValueError):
        await server.send_log_message("LOUD", {"note": "x"})
