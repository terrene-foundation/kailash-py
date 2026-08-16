# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for #1712 - client-side OAuth 2.1 discovery chain.

Behavioral pins (call the function, assert raise/return - never source-grep,
per ``rules/testing.md``) for the CLIENT-side OAuth 2.1 discovery shard of the
MCP 2025-11-25 spec-parity work:

1. **WWW-Authenticate parse (RFC 9728)** - ``parse_www_authenticate`` extracts
   the quoted challenge parameters (``resource_metadata``, ``scope``).
2. **PRM discovery (RFC 9728)** - both mechanisms: the ``resource_metadata``
   header param AND the ``/.well-known/oauth-protected-resource`` fallback;
   ``resource`` mismatch is rejected.
3. **AS metadata discovery (RFC 8414 + OIDC)** - RFC 8414 path-insertion first,
   OIDC ``openid-configuration`` fallback; issuer mismatch is rejected.
4. **PKCE S256 fail-closed guard** - discovery refuses the flow (typed error)
   unless the AS advertises ``S256``; ``plain`` is never accepted.
5. **RFC 8707 resource indicator** - present on all four grant builders
   (authorize URL, code exchange, client-credentials, refresh).
6. **Bearer binding** - ``MCPClient`` attaches the OAuth2Client token to
   outbound headers, refreshing a near-expiry token before it is attached.

The network double is a REAL local ``aiohttp`` server (no mocking) exercising
the actual ``aiohttp`` fetch path in ``OAuth2Client``.
"""

import time
from urllib.parse import parse_qs, urlparse

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from kailash_mcp.auth.oauth import (
    OAuth2Client,
    OAuthDiscoveryError,
    OAuthPKCEUnsupportedError,
    parse_www_authenticate,
)
from kailash_mcp.client import MCPClient
from kailash_mcp.errors import AuthenticationError

_OMIT = object()


def _build_app(
    *,
    resource=None,
    authorization_servers=None,
    issuer=None,
    code_challenge_methods=("S256",),
    serve_rfc8414=True,
    serve_oidc=True,
    token_response=None,
):
    """Build a local OAuth test double. Values referencing the server derive
    from the incoming request host so the random test port is honoured."""
    app = web.Application()
    record = {"token_forms": [], "hits": []}

    def _base(request):
        return f"{request.scheme}://{request.host}"

    async def prm(request):
        record["hits"].append(request.path)
        base = _base(request)
        return web.json_response(
            {
                "resource": base if resource is None else resource,
                "authorization_servers": (
                    [base] if authorization_servers is None else authorization_servers
                ),
            }
        )

    async def as_metadata(request):
        record["hits"].append(request.path)
        base = _base(request)
        md = {
            "issuer": base if issuer is None else issuer,
            "authorization_endpoint": f"{base}/authorize",
            "token_endpoint": f"{base}/token",
        }
        if code_challenge_methods is not None:
            md["code_challenge_methods_supported"] = list(code_challenge_methods)
        return web.json_response(md)

    async def token(request):
        form = dict(await request.post())
        record["token_forms"].append(form)
        resp = token_response or {
            "access_token": "access-token-1",
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": "refresh-token-1",
        }
        return web.json_response(resp)

    app.router.add_get("/.well-known/oauth-protected-resource", prm)
    app.router.add_get("/custom-prm", prm)
    if serve_rfc8414:
        app.router.add_get("/.well-known/oauth-authorization-server", as_metadata)
    if serve_oidc:
        app.router.add_get("/.well-known/openid-configuration", as_metadata)
    app.router.add_post("/token", token)
    return app, record


async def _start(app):
    server = TestServer(app)
    await server.start_server()
    base = str(server.make_url("")).rstrip("/")
    return server, base


# ---------------------------------------------------------------------------
# 1. WWW-Authenticate parse (RFC 9728)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_parse_www_authenticate_extracts_resource_metadata_and_scope():
    header = (
        'Bearer resource_metadata="https://srv/.well-known/oauth-protected-resource", '
        'scope="mcp read", error="invalid_token"'
    )
    params = parse_www_authenticate(header)
    assert (
        params["resource_metadata"]
        == "https://srv/.well-known/oauth-protected-resource"
    )
    assert params["scope"] == "mcp read"
    assert params["error"] == "invalid_token"


@pytest.mark.regression
def test_parse_www_authenticate_empty_header_returns_empty():
    assert parse_www_authenticate("") == {}
    assert parse_www_authenticate(None) == {}


# ---------------------------------------------------------------------------
# 2. PRM discovery (RFC 9728) - both mechanisms + resource validation
# ---------------------------------------------------------------------------


@pytest.mark.regression
async def test_prm_discovery_via_www_authenticate_header():
    app, record = _build_app()
    server, base = await _start(app)
    try:
        client = OAuth2Client("cid")
        header = f'Bearer resource_metadata="{base}/custom-prm"'
        prm = await client.discover_protected_resource_metadata(base, header)
        assert prm["resource"] == base
        assert client._authorization_servers == [base]
        # The header mechanism fetched the CUSTOM url, not the well-known.
        assert "/custom-prm" in record["hits"]
        assert "/.well-known/oauth-protected-resource" not in record["hits"]
    finally:
        await server.close()


@pytest.mark.regression
async def test_prm_discovery_via_wellknown_fallback():
    app, record = _build_app()
    server, base = await _start(app)
    try:
        client = OAuth2Client("cid")
        # No WWW-Authenticate header -> well-known probe.
        prm = await client.discover_protected_resource_metadata(base)
        assert prm["resource"] == base
        assert "/.well-known/oauth-protected-resource" in record["hits"]
    finally:
        await server.close()


@pytest.mark.regression
async def test_prm_resource_mismatch_rejected():
    app, _ = _build_app(resource="https://evil.example.com/mcp")
    server, base = await _start(app)
    try:
        client = OAuth2Client("cid")
        with pytest.raises(OAuthDiscoveryError, match="does not match"):
            await client.discover_protected_resource_metadata(base)
    finally:
        await server.close()


@pytest.mark.regression
async def test_prm_missing_authorization_servers_rejected():
    app, _ = _build_app(authorization_servers=[])
    server, base = await _start(app)
    try:
        client = OAuth2Client("cid")
        with pytest.raises(OAuthDiscoveryError, match="authorization_servers"):
            await client.discover_protected_resource_metadata(base)
    finally:
        await server.close()


@pytest.mark.regression
async def test_prm_cross_origin_resource_metadata_rejected_before_fetch_ssrf():
    """A foreign-origin resource_metadata URL (from an untrusted 401 header)
    MUST be rejected BEFORE the fetch — no SSRF request may fire."""
    app, record = _build_app()
    server, base = await _start(app)
    try:
        client = OAuth2Client("cid")
        # Attacker-controlled 401 challenge steering discovery at a foreign
        # (would-be internal) origin.
        header = 'Bearer resource_metadata="http://169.254.169.254/latest/prm"'
        with pytest.raises(OAuthDiscoveryError, match="origin does not match"):
            await client.discover_protected_resource_metadata(base, header)
        # Fail-closed BEFORE the fetch: the local server saw no discovery hit,
        # and (crucially) the client never issued the SSRF GET at all.
        assert record["hits"] == []
    finally:
        await server.close()


@pytest.mark.regression
async def test_prm_same_host_different_port_rejected():
    """Origin includes the port — a same-host, different-port PRM URL is a
    distinct origin and MUST be rejected."""
    app, _ = _build_app()
    server, base = await _start(app)
    try:
        parsed = urlparse(base)
        foreign_port = (parsed.port or 80) + 1
        foreign = f"{parsed.scheme}://{parsed.hostname}:{foreign_port}/prm"
        client = OAuth2Client("cid")
        header = f'Bearer resource_metadata="{foreign}"'
        with pytest.raises(OAuthDiscoveryError, match="origin does not match"):
            await client.discover_protected_resource_metadata(base, header)
    finally:
        await server.close()


# ---------------------------------------------------------------------------
# 3. AS metadata discovery (RFC 8414 + OIDC fallback)
# ---------------------------------------------------------------------------


@pytest.mark.regression
async def test_as_metadata_rfc8414_preferred():
    app, record = _build_app(serve_rfc8414=True, serve_oidc=True)
    server, base = await _start(app)
    try:
        client = OAuth2Client("cid")
        md = await client.discover_authorization_server_metadata(base)
        assert md["issuer"] == base
        assert client.token_endpoint == f"{base}/token"
        assert client.authorization_endpoint == f"{base}/authorize"
        assert client._code_challenge_methods_supported == ["S256"]
        # RFC 8414 URL was used; OIDC was never needed.
        assert "/.well-known/oauth-authorization-server" in record["hits"]
        assert "/.well-known/openid-configuration" not in record["hits"]
    finally:
        await server.close()


@pytest.mark.regression
async def test_as_metadata_oidc_fallback_when_rfc8414_absent():
    app, record = _build_app(serve_rfc8414=False, serve_oidc=True)
    server, base = await _start(app)
    try:
        client = OAuth2Client("cid")
        md = await client.discover_authorization_server_metadata(base)
        assert md["token_endpoint"] == f"{base}/token"
        # RFC 8414 404'd, OIDC fallback served the metadata.
        assert "/.well-known/openid-configuration" in record["hits"]
    finally:
        await server.close()


@pytest.mark.regression
async def test_as_metadata_issuer_mismatch_rejected():
    app, _ = _build_app(issuer="https://evil.example.com")
    server, base = await _start(app)
    try:
        client = OAuth2Client("cid")
        with pytest.raises(OAuthDiscoveryError, match="issuer"):
            await client.discover_authorization_server_metadata(base)
    finally:
        await server.close()


@pytest.mark.regression
async def test_as_metadata_both_urls_fail_raises():
    app, _ = _build_app(serve_rfc8414=False, serve_oidc=False)
    server, base = await _start(app)
    try:
        client = OAuth2Client("cid")
        with pytest.raises(OAuthDiscoveryError, match="discovery failed"):
            await client.discover_authorization_server_metadata(base)
    finally:
        await server.close()


# ---------------------------------------------------------------------------
# 4. PKCE S256 fail-closed guard
# ---------------------------------------------------------------------------


@pytest.mark.regression
async def test_discover_full_chain_succeeds_with_s256():
    app, _ = _build_app(code_challenge_methods=("S256",))
    server, base = await _start(app)
    try:
        client = OAuth2Client("cid")
        result = await client.discover(base)
        assert "protected_resource_metadata" in result
        assert "authorization_server_metadata" in result
        assert client.token_endpoint == f"{base}/token"
        assert client.resource == base  # RFC 8707 indicator bound from PRM
    finally:
        await server.close()


@pytest.mark.regression
async def test_pkce_guard_fails_closed_when_methods_absent():
    # AS metadata omits code_challenge_methods_supported entirely.
    app, _ = _build_app(code_challenge_methods=None)
    server, base = await _start(app)
    try:
        client = OAuth2Client("cid")
        with pytest.raises(OAuthPKCEUnsupportedError, match="cannot be confirmed"):
            await client.discover(base)
    finally:
        await server.close()


@pytest.mark.regression
async def test_pkce_guard_rejects_plain_only():
    app, _ = _build_app(code_challenge_methods=("plain",))
    server, base = await _start(app)
    try:
        client = OAuth2Client("cid")
        with pytest.raises(OAuthPKCEUnsupportedError, match="S256"):
            await client.discover(base)
    finally:
        await server.close()


@pytest.mark.regression
async def test_pkce_guard_in_authorization_url_after_discovery():
    # Directly seed discovered methods lacking S256, then build the URL.
    client = OAuth2Client(
        "cid",
        authorization_endpoint="https://as/authorize",
        redirect_uri="https://app/callback",
    )
    client._code_challenge_methods_supported = ["plain"]
    with pytest.raises(OAuthPKCEUnsupportedError):
        client.get_authorization_url(use_pkce=True)


# ---------------------------------------------------------------------------
# 5. RFC 8707 resource indicator on all four grant builders
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_authorization_url_carries_resource_and_s256():
    client = OAuth2Client(
        "cid",
        authorization_endpoint="https://as.example.com/authorize",
        redirect_uri="https://app.example.com/callback",
        resource="https://srv.example.com/mcp",
    )
    url, verifier = client.get_authorization_url(scopes=["mcp"], use_pkce=True)
    query = parse_qs(urlparse(url).query)
    assert query["resource"] == ["https://srv.example.com/mcp"]
    assert query["code_challenge_method"] == ["S256"]
    assert "code_challenge" in query
    assert verifier  # PKCE verifier returned


@pytest.mark.regression
async def test_client_credentials_sends_resource():
    app, record = _build_app()
    server, base = await _start(app)
    try:
        client = OAuth2Client(
            "cid",
            client_secret="secret",
            token_endpoint=f"{base}/token",
            resource="https://srv.example.com/mcp",
        )
        await client.get_client_credentials_token(scopes=["mcp"])
        assert record["token_forms"][-1]["resource"] == "https://srv.example.com/mcp"
        assert record["token_forms"][-1]["grant_type"] == "client_credentials"
    finally:
        await server.close()


@pytest.mark.regression
async def test_code_exchange_sends_resource():
    app, record = _build_app()
    server, base = await _start(app)
    try:
        client = OAuth2Client(
            "cid",
            client_secret="secret",
            token_endpoint=f"{base}/token",
            redirect_uri="https://app.example.com/callback",
            resource="https://srv.example.com/mcp",
        )
        await client.exchange_authorization_code("the-code", code_verifier="v")
        form = record["token_forms"][-1]
        assert form["resource"] == "https://srv.example.com/mcp"
        assert form["grant_type"] == "authorization_code"
        assert form["code_verifier"] == "v"
    finally:
        await server.close()


@pytest.mark.regression
async def test_refresh_sends_resource():
    app, record = _build_app()
    server, base = await _start(app)
    try:
        client = OAuth2Client(
            "cid",
            client_secret="secret",
            token_endpoint=f"{base}/token",
            resource="https://srv.example.com/mcp",
        )
        client._refresh_token = "rt-existing"
        await client._refresh_access_token()
        form = record["token_forms"][-1]
        assert form["resource"] == "https://srv.example.com/mcp"
        assert form["grant_type"] == "refresh_token"
    finally:
        await server.close()


# ---------------------------------------------------------------------------
# 6. Bearer binding on outbound requests (attach + refresh-before-attach)
# ---------------------------------------------------------------------------


@pytest.mark.regression
async def test_bearer_attached_from_oauth_client():
    client = OAuth2Client("cid", token_endpoint="https://as/token")
    client._access_token = "live-token"
    client._token_expires_at = time.time() + 3600  # valid

    mcp = MCPClient()
    mcp.set_oauth_client(client)
    headers = await mcp._get_auth_headers_async({"url": "https://srv/mcp"})
    assert headers["Authorization"] == "Bearer live-token"


@pytest.mark.regression
async def test_bearer_refreshed_before_attach_on_expiry():
    app, record = _build_app(
        token_response={
            "access_token": "refreshed-token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }
    )
    server, base = await _start(app)
    try:
        client = OAuth2Client("cid", token_endpoint=f"{base}/token")
        client._access_token = "stale-token"
        client._token_expires_at = time.time() - 10  # expired
        client._refresh_token = "rt-1"

        mcp = MCPClient()
        mcp.set_oauth_client(client)
        headers = await mcp._get_auth_headers_async({"url": f"{base}/mcp"})
        # Refresh happened (token endpoint hit) and the NEW token is attached.
        assert headers["Authorization"] == "Bearer refreshed-token"
        assert record["token_forms"][-1]["grant_type"] == "refresh_token"
    finally:
        await server.close()


@pytest.mark.regression
async def test_bearer_via_per_server_oauth_client_config():
    client = OAuth2Client("cid", token_endpoint="https://as/token")
    client._access_token = "cfg-token"
    client._token_expires_at = time.time() + 3600

    mcp = MCPClient()
    server_config = {
        "url": "https://srv/mcp",
        "auth": {"type": "oauth2", "oauth_client": client},
    }
    headers = await mcp._get_auth_headers_async(server_config)
    assert headers["Authorization"] == "Bearer cfg-token"


@pytest.mark.regression
async def test_configured_provider_without_token_raises():
    client = OAuth2Client("cid")  # never acquired a token, no refresh token
    mcp = MCPClient()
    mcp.set_oauth_client(client)
    with pytest.raises(AuthenticationError, match="no valid token"):
        await mcp._get_auth_headers_async({"url": "https://srv/mcp"})


@pytest.mark.regression
async def test_no_provider_falls_back_to_static_headers():
    mcp = MCPClient()
    server_config = {
        "url": "https://srv/mcp",
        "auth": {"type": "bearer", "token": "static-tok"},
    }
    headers = await mcp._get_auth_headers_async(server_config)
    assert headers["Authorization"] == "Bearer static-tok"
