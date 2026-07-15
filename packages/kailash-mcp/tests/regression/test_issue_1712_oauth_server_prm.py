# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for #1712 - server-publish half of the OAuth 2.1 surface.

Behavioral pins (construct the REAL objects, call the method, drive the REAL
ASGI route - never source-grep, never mock the SDK under test, per
``rules/testing.md`` Tier 2) for the SERVER-PUBLISH shard of the MCP 2025-11-25
spec-parity work. The CLIENT-side discovery chain is pinned separately in
``test_issue_1712_oauth_discovery.py``; this file pins the server half those
clients discover:

1. **PRM document (RFC 9728 §2)** - ``ResourceServer.get_protected_resource_metadata``
   returns ``{resource, authorization_servers, scopes_supported,
   bearer_methods_supported}`` drawn from config.
2. **Live-transport route (RFC 9728 §3)** - the metadata is served at
   ``GET /.well-known/oauth-protected-resource`` on BOTH the Starlette route
   surface (real ``TestClient``) AND the pure-ASGI app (real scope/receive/send
   harness).
3. **401 challenge (RFC 9110 §11.6.1 / RFC 9728 §5.1)** - the auth-failure path
   emits ``WWW-Authenticate: Bearer resource_metadata="<prm-url>", scope="..."``,
   and the header round-trips through ``parse_www_authenticate``.
4. **Audience fail-closed (RFC 8707 / rules/security.md)** - an audience-absent
   token AND a foreign-audience token are both rejected, each carrying the 401
   challenge.
5. **PKCE S256-only posture** - ``AuthorizationServer.get_well_known_metadata``
   advertises ``code_challenge_methods_supported == ["S256"]`` with ``"plain"``
   absent.

No SDK object is mocked. The route double is a REAL Starlette app driven by the
real ``starlette.testclient.TestClient`` and, separately, the pure-ASGI app
driven directly through the ASGI protocol.
"""

import asyncio

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from kailash_mcp.auth.oauth import (
    AuthorizationServer,
    JWTManager,
    ResourceServer,
    parse_www_authenticate,
)
from kailash_mcp.auth.well_known import (
    build_well_known_routes,
    build_www_authenticate_challenge,
    create_protected_resource_metadata_app,
    protected_resource_metadata_url,
)
from kailash_mcp.errors import AuthenticationError, AuthorizationError

_ISSUER = "https://as.example.com"
_RESOURCE = "https://mcp.example.com"  # origin-root → bare well-known path
_SCOPES = ["mcp:read", "mcp:write"]


def _resource_server(**overrides) -> ResourceServer:
    """Construct a real ResourceServer with a real RS256 JWTManager."""
    kwargs = dict(
        issuer=_ISSUER,
        audience=_RESOURCE,
        jwt_manager=JWTManager(issuer=_ISSUER),
        required_scopes=list(_SCOPES),
    )
    kwargs.update(overrides)
    return ResourceServer(**kwargs)


# ---------------------------------------------------------------------------
# 1. PRM document shape
# ---------------------------------------------------------------------------


def test_protected_resource_metadata_document_shape():
    rs = _resource_server()
    doc = rs.get_protected_resource_metadata()

    assert doc == {
        "resource": _RESOURCE,
        "authorization_servers": [_ISSUER],
        "scopes_supported": _SCOPES,
        "bearer_methods_supported": ["header"],
    }
    # Every RFC 9728 §2 required field present.
    assert set(doc) == {
        "resource",
        "authorization_servers",
        "scopes_supported",
        "bearer_methods_supported",
    }


def test_prm_document_honours_explicit_config():
    rs = _resource_server(
        resource="https://api.example.com/mcp",
        authorization_servers=["https://as1.example.com", "https://as2.example.com"],
        bearer_methods_supported=["header", "body"],
    )
    doc = rs.get_protected_resource_metadata()
    assert doc["resource"] == "https://api.example.com/mcp"
    assert doc["authorization_servers"] == [
        "https://as1.example.com",
        "https://as2.example.com",
    ]
    assert doc["bearer_methods_supported"] == ["header", "body"]


def test_prm_returns_fresh_lists_not_shared_mutable_state():
    rs = _resource_server()
    doc = rs.get_protected_resource_metadata()
    doc["scopes_supported"].append("mcp:admin")
    # Mutating the returned doc MUST NOT corrupt server config.
    assert rs.required_scopes == _SCOPES


# ---------------------------------------------------------------------------
# 2. Live-transport route registration
# ---------------------------------------------------------------------------


def test_starlette_route_serves_prm_at_wellknown_path():
    rs = _resource_server()
    app = Starlette(routes=build_well_known_routes(rs))
    client = TestClient(app)

    resp = client.get("/.well-known/oauth-protected-resource")
    assert resp.status_code == 200
    assert resp.json() == rs.get_protected_resource_metadata()
    assert resp.headers["content-type"].startswith("application/json")


def test_starlette_route_path_tracks_resource_path_component():
    # A path-bearing resource serves PRM at the path-suffixed well-known URL,
    # byte-identical to the client's derivation.
    rs = _resource_server(resource="https://mcp.example.com/mcp")
    app = Starlette(routes=build_well_known_routes(rs))
    client = TestClient(app)

    resp = client.get("/.well-known/oauth-protected-resource/mcp")
    assert resp.status_code == 200
    assert resp.json()["resource"] == "https://mcp.example.com/mcp"
    # And the client-side URL helper agrees on the served path.
    assert protected_resource_metadata_url("https://mcp.example.com/mcp") == (
        "https://mcp.example.com/.well-known/oauth-protected-resource/mcp"
    )


def test_pure_asgi_app_serves_prm_document():
    rs = _resource_server()
    app = create_protected_resource_metadata_app(rs)

    status, headers, body = _drive_asgi(
        app, method="GET", path="/.well-known/oauth-protected-resource"
    )
    assert status == 200
    assert dict(headers)[b"content-type"] == b"application/json"
    import json

    assert json.loads(body) == rs.get_protected_resource_metadata()


def test_pure_asgi_app_404_for_other_paths():
    rs = _resource_server()
    app = create_protected_resource_metadata_app(rs)
    status, _headers, _body = _drive_asgi(app, method="GET", path="/somewhere-else")
    assert status == 404


# ---------------------------------------------------------------------------
# 3. WWW-Authenticate 401 challenge
# ---------------------------------------------------------------------------


def test_unauthorized_response_header_string():
    rs = _resource_server()
    resp = rs.unauthorized_response()

    prm_url = protected_resource_metadata_url(_RESOURCE)
    expected = (
        f'Bearer resource_metadata="{prm_url}", '
        f'error="invalid_token", scope="mcp:read mcp:write"'
    )
    assert resp["status"] == 401
    assert resp["headers"]["WWW-Authenticate"] == expected
    assert resp["body"]["error"] == "invalid_token"


def test_challenge_roundtrips_through_parser():
    # The server-built challenge MUST be parseable by the client-side parser -
    # the two are inverse operations sharing one param shape.
    rs = _resource_server()
    header = rs.www_authenticate_challenge(error="invalid_token")
    params = parse_www_authenticate(header)

    assert params["resource_metadata"] == protected_resource_metadata_url(_RESOURCE)
    assert params["scope"] == "mcp:read mcp:write"
    assert params["error"] == "invalid_token"


def test_challenge_builder_rejects_quote_injection():
    with pytest.raises(ValueError, match="double quote"):
        build_www_authenticate_challenge(
            resource_metadata_url='https://x/"><script>', scope="s"
        )


def test_missing_token_raises_with_challenge():
    rs = _resource_server()
    with pytest.raises(AuthenticationError) as exc_info:
        asyncio.run(rs.authenticate({"other": "no-token-key"}))
    challenge = getattr(exc_info.value, "www_authenticate", None)
    assert challenge is not None
    assert parse_www_authenticate(challenge)["error"] == "invalid_request"


# ---------------------------------------------------------------------------
# 4. Audience fail-closed - both audience-absent AND foreign-audience rejected
# ---------------------------------------------------------------------------


def test_audience_absent_token_rejected_fail_closed():
    jwt_manager = JWTManager(issuer=_ISSUER)
    rs = _resource_server(jwt_manager=jwt_manager)
    # Token minted with NO audience claim.
    token = jwt_manager.create_access_token(
        subject="user-1", scope="mcp:read mcp:write"
    ).token

    with pytest.raises(AuthorizationError) as exc_info:
        asyncio.run(rs.authenticate(token))
    challenge = getattr(exc_info.value, "www_authenticate", None)
    assert challenge is not None
    assert parse_www_authenticate(challenge)["error"] == "invalid_token"


def test_foreign_audience_token_rejected_fail_closed():
    jwt_manager = JWTManager(issuer=_ISSUER)
    rs = _resource_server(jwt_manager=jwt_manager)
    # Token minted for a DIFFERENT resource server.
    token = jwt_manager.create_access_token(
        subject="user-1",
        scope="mcp:read mcp:write",
        audience=["https://other-resource.example.com"],
    ).token

    with pytest.raises(AuthorizationError):
        asyncio.run(rs.authenticate(token))


def test_valid_audience_and_scope_authenticates():
    jwt_manager = JWTManager(issuer=_ISSUER)
    rs = _resource_server(jwt_manager=jwt_manager)
    token = jwt_manager.create_access_token(
        subject="user-1",
        client_id="client-1",
        scope="mcp:read mcp:write",
        audience=[_RESOURCE],
    ).token

    result = asyncio.run(rs.authenticate(token))
    assert result["subject"] == "user-1"
    assert result["scopes"] == ["mcp:read", "mcp:write"]


def test_insufficient_scope_carries_scope_param():
    jwt_manager = JWTManager(issuer=_ISSUER)
    rs = _resource_server(jwt_manager=jwt_manager)
    # Valid audience, but missing mcp:write.
    token = jwt_manager.create_access_token(
        subject="user-1", scope="mcp:read", audience=[_RESOURCE]
    ).token

    with pytest.raises(AuthenticationError) as exc_info:
        asyncio.run(rs.authenticate(token))
    params = parse_www_authenticate(exc_info.value.www_authenticate)
    assert params["error"] == "insufficient_scope"
    assert params["scope"] == "mcp:write"


# ---------------------------------------------------------------------------
# 5. PKCE S256-only posture
# ---------------------------------------------------------------------------


def test_authorization_server_metadata_advertises_s256_only():
    server = AuthorizationServer(issuer=_ISSUER)
    metadata = server.get_well_known_metadata()

    assert metadata["code_challenge_methods_supported"] == ["S256"]
    assert "plain" not in metadata["code_challenge_methods_supported"]


# ---------------------------------------------------------------------------
# ASGI test harness (real ASGI protocol, no mocking)
# ---------------------------------------------------------------------------


def _drive_asgi(app, *, method: str, path: str):
    """Drive a pure-ASGI app through one request; return (status, headers, body)."""
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "query_string": b"",
    }
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(app(scope, receive, send))

    start = next(m for m in messages if m["type"] == "http.response.start")
    body = b"".join(
        m.get("body", b"") for m in messages if m["type"] == "http.response.body"
    )
    return start["status"], start["headers"], body
