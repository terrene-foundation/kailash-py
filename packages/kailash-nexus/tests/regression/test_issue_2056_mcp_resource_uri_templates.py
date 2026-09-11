# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #2056.

``NexusResourceManager.__init__`` raised ``ValueError: Mismatch between URI
parameters set() and function parameters {'uri'}`` whenever the official
``mcp`` package was importable, because all five providers registered a
``scheme://*`` wildcard against handlers taking a ``uri`` argument. FastMCP
requires a template's ``{param}`` placeholders to match the handler signature
exactly, and ``*`` declares none.

BOTH POLES are asserted here. A single-pole test cannot distinguish the real
fix from one that repairs the FastMCP path while breaking ``kailash_mcp``'s
non-FastMCP fallback (which stores handlers under the URI string verbatim and
accepted the broken form, which is why the bug looked import-order dependent).
"""

import re
import types

import pytest

from nexus.resources import NexusResourceManager

# The official MCP package is what triggers the bug. Skipping when it is absent
# would make this file silently vacuous on such a machine, so it is a hard skip
# with a reason rather than a quiet pass.
mcp_server = pytest.importorskip(
    "mcp.server.fastmcp",
    reason="official 'mcp' package required to exercise the FastMCP pole",
)


def _nexus_stub():
    return types.SimpleNamespace(
        _workflows={},
        _api_port=8000,
        _mcp_port=3001,
        _enable_auth=False,
        _enable_monitoring=False,
        _enable_discovery=False,
        rate_limit_config={},
        _get_enabled_transports=lambda: ["websocket"],
    )


EXPECTED_TEMPLATES = {
    "workflow://{name}",
    "docs://{topic}",
    "config://{key}",
    "help://{topic}",
    "data://{seg1}",
    "data://{seg1}/{seg2}",
    "data://{seg1}/{seg2}/{seg3}",
    "data://{seg1}/{seg2}/{seg3}/{seg4}",
}


# --------------------------------------------------------------------------
# Pole 1: official FastMCP present
# --------------------------------------------------------------------------


def test_registration_succeeds_with_official_fastmcp():
    """Construction completes with real FastMCP; every template registers.

    This is the exact call that raised in #2056.
    """
    from kailash_mcp import MCPServer

    server = MCPServer("issue-2056-fastmcp")
    manager = NexusResourceManager(server, _nexus_stub())

    assert manager is not None
    assert set(server._resource_registry) == EXPECTED_TEMPLATES


def test_official_fastmcp_is_actually_the_backend():
    """Guard against the test passing because FastMCP silently was not used.

    If ``_mcp`` were the non-FastMCP fallback, the test above would prove
    nothing about the FastMCP pole. Pin the backend type explicitly.
    """
    from mcp.server.fastmcp import FastMCP

    from kailash_mcp import MCPServer

    server = MCPServer("issue-2056-backend-check")
    NexusResourceManager(server, _nexus_stub())

    assert isinstance(server._mcp, FastMCP), (
        f"expected official FastMCP backend, got {type(server._mcp)!r}; "
        "the FastMCP pole of this regression is not being exercised"
    )


def test_wildcard_form_is_still_rejected_by_fastmcp():
    """Pin WHY the templates changed: the old form genuinely does not work.

    If FastMCP ever stopped rejecting ``scheme://*`` this test goes red and the
    template design can be revisited deliberately rather than by accident.
    """
    from kailash_mcp import MCPServer

    server = MCPServer("issue-2056-wildcard")

    with pytest.raises(ValueError, match="Mismatch between URI parameters"):

        @server.resource("workflow://*")
        async def handler(uri: str):  # pragma: no cover - must raise on decoration
            return uri


# --------------------------------------------------------------------------
# Pole 2: the non-FastMCP fallback
# --------------------------------------------------------------------------


class _FallbackServer:
    """Stand-in for ``kailash_mcp``'s FallbackMCPServer registration surface.

    It stores handlers under the URI string verbatim and imposes no
    signature constraint -- the behaviour that let the broken wildcard form
    survive wherever ``mcp`` was not installed.
    """

    def __init__(self):
        self._resources = {}

    def resource(self, uri):
        def decorator(func):
            self._resources[uri] = func
            return func

        return decorator


def test_registration_succeeds_without_fastmcp():
    """The same templates register against the non-FastMCP fallback."""
    server = _FallbackServer()
    NexusResourceManager(server, _nexus_stub())

    assert set(server._resources) == EXPECTED_TEMPLATES


# --------------------------------------------------------------------------
# The templates must actually ROUTE, not merely register
# --------------------------------------------------------------------------


def _match(template: str, uri: str):
    """Replicate ``ResourceTemplate.matches`` exactly."""
    pattern = template.replace("{", "(?P<").replace("}", ">[^/]+)")
    return re.match(f"^{pattern}$", uri)


@pytest.mark.parametrize(
    "uri",
    [
        "workflow://my_workflow",
        "docs://quickstart",
        "config://platform",
        "help://getting-started",
        "data://sample.json",
        "data://examples/sample.json",
        "data://a/b/c.txt",
        "data://a/b/c/d.txt",
    ],
)
def test_every_documented_uri_matches_some_template(uri):
    """Registration is worthless if concrete URIs do not route.

    ``data://examples/sample.json`` is the module's own documented example and
    is the reason ``data://`` needs one template per depth: FastMCP compiles a
    parameter to ``[^/]+``, so a single ``{path}`` cannot span a slash.
    """
    assert any(
        _match(t, uri) for t in EXPECTED_TEMPLATES
    ), f"{uri!r} matches no registered template"


@pytest.mark.asyncio
async def test_data_multisegment_uri_reaches_the_handler():
    """End-to-end: a nested data URI returns the sample payload, not a 404."""
    server = _FallbackServer()
    NexusResourceManager(server, _nexus_stub())

    uri = "data://examples/sample.json"
    for template, func in server._resources.items():
        match = _match(template, uri)
        if match:
            result = await func(**match.groupdict())
            break
    else:  # pragma: no cover - the parametrized test above already guards this
        pytest.fail(f"no template matched {uri!r}")

    assert result["uri"] == uri
    assert result["mimeType"] == "application/json"
    assert "error" not in result
    assert '"example"' in result["content"]
