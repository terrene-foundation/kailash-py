# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for #1712 Wave 2 security hardening (F2 + F5).

Behavioral pins — construct the REAL SDK objects, call the real methods, assert
the real fail-loud / fail-closed behavior (no mocking of the SDK under test, per
``rules/testing.md`` Tier 2).

**F2 (MED) — PRM URL malformed on the module's documented default config.**
``ResourceServer(issuer=..., audience="mcp-api")`` (the documented example, no
``resource``) set ``self.resource == "mcp-api"`` — a bare token. RFC 9728 §3.1
PRM URL derivation from a non-URL identifier produced a corrupt
``:///.well-known/oauth-protected-resource...`` string (served PRM doc, mountable
route path, AND the ``WWW-Authenticate`` ``resource_metadata`` param all broken),
so a spec RFC 9728 client could not bootstrap. Fix: ``ResourceServer.__init__``
now REQUIRES the effective ``resource`` to be an absolute http(s) URL and raises
``ValueError`` otherwise; ``well_known`` PRM helpers reject a non-URL resource
too (defense in depth). ``resource`` and ``audience`` remain INDEPENDENT — a
URL ``resource`` with a bare-token ``audience`` stays valid.

**F5 (MED) — S256-only advertised but not enforced at the Authorization Server.**
``get_well_known_metadata`` advertised only ``["S256"]`` while
``create_authorization_url`` / ``generate_authorization_code`` still accepted
``code_challenge_method == "plain"`` and ``AuthorizationCode.validate_pkce``
still validated a ``plain`` challenge — a PKCE downgrade the metadata claims is
unsupported (enforcement-surface parity failure). Fix: the AS enforcement
surfaces reject any non-S256 method fail-closed; the ``plain`` validation branch
is dropped so a ``plain`` challenge can never validate. S256 stays fully working.
"""

import asyncio
import base64
import hashlib
import secrets

import pytest

from kailash_mcp.auth.oauth import (
    AuthorizationCode,
    AuthorizationServer,
    JWTManager,
    ResourceServer,
    parse_www_authenticate,
)
from kailash_mcp.auth.well_known import (
    protected_resource_metadata_path,
    protected_resource_metadata_url,
)
from kailash_mcp.errors import AuthorizationError

_ISSUER = "https://as.example.com"
_WELL_KNOWN_SUFFIX = "/.well-known/oauth-protected-resource"


# ---------------------------------------------------------------------------
# F2 — resource identifier must be an absolute http(s) URL for PRM derivation
# ---------------------------------------------------------------------------


def test_resource_server_bare_audience_no_resource_raises():
    """The documented default ``ResourceServer(audience="mcp-api")`` (no URL
    resource) must fail loud rather than emit a corrupt PRM URL."""
    with pytest.raises(ValueError) as exc_info:
        ResourceServer(
            issuer=_ISSUER,
            audience="mcp-api",
            jwt_manager=JWTManager(issuer=_ISSUER),
        )
    msg = str(exc_info.value)
    assert "mcp-api" in msg
    assert "absolute" in msg and "http(s)" in msg
    assert 'resource="https://' in msg  # actionable instruction to the caller


@pytest.mark.parametrize("bad_resource", ["mcp-api", "not a url", "ftp://x/y", ""])
def test_resource_server_non_url_resource_raises(bad_resource):
    """Any non-absolute-http(s) ``resource`` is rejected regardless of ``audience``."""
    with pytest.raises(ValueError):
        ResourceServer(
            issuer=_ISSUER,
            audience="mcp-api",
            resource=bad_resource,
            jwt_manager=JWTManager(issuer=_ISSUER),
        )


def test_resource_server_url_resource_bare_audience_is_valid():
    """A URL-shaped ``resource`` with a bare-token ``audience`` stays valid:
    the PRM URL derives from ``resource``; the audience check uses ``audience``.
    ``resource`` and ``audience`` remain independent params."""
    rs = ResourceServer(
        issuer=_ISSUER,
        audience="mcp-api",  # bare token — used for the RFC 8707 aud check
        resource="https://mcp.example.com/mcp",  # URL — used for PRM derivation
        jwt_manager=JWTManager(issuer=_ISSUER),
        required_scopes=["mcp:read"],
    )
    # audience and resource stay independent
    assert rs.audience == "mcp-api"
    assert rs.resource == "https://mcp.example.com/mcp"

    # PRM URL is well-formed
    url = rs.resource_metadata_url
    assert url.startswith("https://")
    assert _WELL_KNOWN_SUFFIX in url
    assert url == "https://mcp.example.com/.well-known/oauth-protected-resource/mcp"

    # PRM document carries the URL resource identifier
    doc = rs.get_protected_resource_metadata()
    assert doc["resource"] == "https://mcp.example.com/mcp"

    # the 401 challenge resource_metadata is a valid https URL
    challenge = rs.www_authenticate_challenge(error="invalid_token")
    params = parse_www_authenticate(challenge)
    assert params["resource_metadata"].startswith("https://")
    assert _WELL_KNOWN_SUFFIX in params["resource_metadata"]
    assert params["resource_metadata"] == url


def test_well_known_helpers_reject_non_url_resource():
    """Defense in depth: the pure PRM builders reject a non-URL resource too,
    with the correct ``/`` separator preserved for a valid URL."""
    with pytest.raises(ValueError):
        protected_resource_metadata_url("mcp-api")
    with pytest.raises(ValueError):
        protected_resource_metadata_path("mcp-api")

    # valid URL → correct separator, no missing '/'
    assert (
        protected_resource_metadata_path("https://mcp.example.com/mcp")
        == "/.well-known/oauth-protected-resource/mcp"
    )
    # origin-root → bare well-known path
    assert (
        protected_resource_metadata_path("https://mcp.example.com")
        == "/.well-known/oauth-protected-resource"
    )


# ---------------------------------------------------------------------------
# F5 — S256-only enforced at every Authorization Server surface (fail-closed)
# ---------------------------------------------------------------------------


def _registered_client(server: AuthorizationServer, redirect_uri: str):
    """Register a public client (no secret) able to run the auth-code flow."""
    return asyncio.run(
        server.register_client(
            client_name="test-client",
            redirect_uris=[redirect_uri],
            grant_types=["authorization_code"],
            scopes=["mcp.tools"],
            client_type="public",
        )
    )


def _s256_pair():
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    return verifier, challenge


def test_create_authorization_url_rejects_plain():
    server = AuthorizationServer(issuer=_ISSUER)
    redirect_uri = "https://client.example.com/cb"
    client = _registered_client(server, redirect_uri)
    with pytest.raises(AuthorizationError) as exc_info:
        asyncio.run(
            server.create_authorization_url(
                client_id=client.client_id,
                redirect_uri=redirect_uri,
                code_challenge="whatever",
                code_challenge_method="plain",
            )
        )
    assert "S256" in str(exc_info.value)
    assert "plain" in str(exc_info.value)


def test_generate_authorization_code_rejects_plain():
    server = AuthorizationServer(issuer=_ISSUER)
    redirect_uri = "https://client.example.com/cb"
    client = _registered_client(server, redirect_uri)
    with pytest.raises(AuthorizationError) as exc_info:
        asyncio.run(
            server.generate_authorization_code(
                client_id=client.client_id,
                user_id="user-1",
                redirect_uri=redirect_uri,
                code_challenge="whatever",
                code_challenge_method="plain",
            )
        )
    assert "S256" in str(exc_info.value)


def test_validate_pkce_plain_challenge_never_validates():
    """A stored ``plain`` challenge can never validate (fail-closed), even when
    the verifier equals the challenge (the old ``plain`` semantics)."""
    code = AuthorizationCode(
        code="c",
        client_id="client",
        redirect_uri="https://client.example.com/cb",
        code_challenge="literal-secret",
        code_challenge_method="plain",
    )
    assert code.validate_pkce("literal-secret") is False
    assert code.validate_pkce("anything") is False


def test_s256_flow_succeeds_end_to_end():
    """S256 stays fully working: issue an S256 code, exchange it with the
    matching verifier, receive a token."""
    server = AuthorizationServer(issuer=_ISSUER)
    redirect_uri = "https://client.example.com/cb"
    client = _registered_client(server, redirect_uri)
    verifier, challenge = _s256_pair()

    code = asyncio.run(
        server.generate_authorization_code(
            client_id=client.client_id,
            user_id="user-1",
            redirect_uri=redirect_uri,
            scopes=["mcp.tools"],
            code_challenge=challenge,
            code_challenge_method="S256",
        )
    )
    assert isinstance(code, str) and code

    tokens = asyncio.run(
        server.exchange_authorization_code(
            client_id=client.client_id,
            client_secret=None,  # public client
            code=code,
            redirect_uri=redirect_uri,
            code_verifier=verifier,
        )
    )
    assert tokens["access_token"]
    assert tokens["token_type"] == "Bearer"


def test_s256_flow_rejects_wrong_verifier():
    """S256 still rejects a mismatched verifier (fail-closed unchanged)."""
    server = AuthorizationServer(issuer=_ISSUER)
    redirect_uri = "https://client.example.com/cb"
    client = _registered_client(server, redirect_uri)
    _, challenge = _s256_pair()

    code = asyncio.run(
        server.generate_authorization_code(
            client_id=client.client_id,
            user_id="user-1",
            redirect_uri=redirect_uri,
            code_challenge=challenge,
            code_challenge_method="S256",
        )
    )
    with pytest.raises(AuthorizationError):
        asyncio.run(
            server.exchange_authorization_code(
                client_id=client.client_id,
                client_secret=None,
                code=code,
                redirect_uri=redirect_uri,
                code_verifier="the-wrong-verifier",
            )
        )
