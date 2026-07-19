"""Regression tests for issue #1815 — OIDC SSO nonce enforcement + PKCE S256.

Two HIGH-severity security gaps in the Core SDK ``SSOAuthenticationNode``:

1. Nonce minted but not enforced. ``_initiate_oauth`` minted an OIDC ``nonce``
   and cached it, but ``_handle_oauth_callback`` never decoded the returned
   ``id_token`` nor compared its ``nonce`` claim to the cached value — the
   minted nonce was dead, leaving the flow open to id_token replay/injection.

2. PKCE S256 absent on the authorization-code flow. No ``code_challenge`` /
   ``code_challenge_method`` was emitted on the authorize request and no
   ``code_verifier`` was sent at token exchange — the auth code was
   interceptable (no proof-of-possession binding).

These tests pin the fixed behavior:
- callback REJECTS (typed ValueError) when the returned id_token nonce claim
  does NOT match the minted nonce, and when the id_token is absent though a
  nonce was minted; ACCEPTS when it matches.
- PKCE round-trip: ``_initiate_oauth`` emits ``code_challenge`` +
  ``code_challenge_method=S256``; the cached ``code_verifier`` flows into
  ``_exchange_oauth_code``; the verifier S256-hashes to the emitted challenge.
"""

import base64
import hashlib
import json
from urllib.parse import parse_qs, urlparse

import pytest

from kailash.nodes.auth.sso import SSOAuthenticationNode

pytestmark = pytest.mark.regression


def _s256(verifier: str) -> str:
    """RFC 7636 S256 transform of a PKCE code_verifier."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _make_id_token(claims: dict) -> str:
    """Build an unsigned-shape JWT (header.payload.signature) for tests.

    Only the base64url payload segment is load-bearing here — the nonce check
    reads the ``nonce`` claim; it does not (and must not) treat this token as
    signature-validated evidence beyond the nonce match.
    """

    def _seg(obj: dict) -> str:
        raw = json.dumps(obj).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    header = _seg({"alg": "RS256", "typ": "JWT"})
    payload = _seg(claims)
    return f"{header}.{payload}.sig"


def _make_node() -> SSOAuthenticationNode:
    return SSOAuthenticationNode(
        name="sso_test",
        enable_jit_provisioning=False,  # skip audit-logger path; isolate the nonce gate
        oauth_settings={
            "client_id": "test-client",
            "auth_endpoint": "https://idp.example.com/oauth2/authorize",
            "token_endpoint": "https://idp.example.com/oauth2/token",
            "userinfo_endpoint": "https://idp.example.com/oauth2/userinfo",
        },
    )


# --------------------------------------------------------------------------- #
# Nonce enforcement
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_callback_rejects_nonce_mismatch():
    """Callback MUST reject when id_token nonce != minted nonce."""
    node = _make_node()
    init = await node._initiate_oauth("oidc", "https://app.example.com/cb")
    state = init["state"]

    async def fake_exchange(provider, auth_code, cached_data):
        return {
            "access_token": "test_access_token",
            "token_type": "Bearer",
            "id_token": _make_id_token({"sub": "u1", "nonce": "ATTACKER-INJECTED"}),
        }

    node._exchange_oauth_code = fake_exchange

    with pytest.raises(ValueError, match="nonce"):
        await node._handle_oauth_callback(
            "oidc", {"state": state, "code": "auth-code-123"}
        )


@pytest.mark.asyncio
async def test_callback_rejects_missing_id_token_when_nonce_minted():
    """When a nonce was minted, an id_token MUST be present; absence rejects."""
    node = _make_node()
    init = await node._initiate_oauth("oidc", "https://app.example.com/cb")
    state = init["state"]

    async def fake_exchange(provider, auth_code, cached_data):
        # No id_token at all.
        return {"access_token": "test_access_token", "token_type": "Bearer"}

    node._exchange_oauth_code = fake_exchange

    with pytest.raises(ValueError):
        await node._handle_oauth_callback(
            "oidc", {"state": state, "code": "auth-code-123"}
        )


@pytest.mark.asyncio
async def test_callback_accepts_matching_nonce():
    """Callback MUST succeed when the id_token nonce matches the minted nonce."""
    node = _make_node()
    init = await node._initiate_oauth("oidc", "https://app.example.com/cb")
    state = init["state"]
    minted_nonce = node.provider_cache[state]["nonce"]
    assert minted_nonce  # sanity: nonce was actually minted

    async def fake_exchange(provider, auth_code, cached_data):
        return {
            "access_token": "test_access_token",
            "token_type": "Bearer",
            "id_token": _make_id_token({"sub": "u1", "nonce": minted_nonce}),
        }

    async def fake_userinfo(provider, access_token):
        return {"sub": "u1", "email": "user@example.com", "name": "User"}

    node._exchange_oauth_code = fake_exchange
    node._get_oauth_user_info = fake_userinfo

    result = await node._handle_oauth_callback(
        "oidc", {"state": state, "code": "auth-code-123"}
    )
    assert result["authenticated"] is True


# --------------------------------------------------------------------------- #
# PKCE S256 round-trip
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_initiate_oauth_emits_pkce_challenge():
    """_initiate_oauth MUST emit code_challenge + code_challenge_method=S256
    and cache the code_verifier that hashes to the challenge."""
    node = _make_node()
    init = await node._initiate_oauth("oidc", "https://app.example.com/cb")

    qs = parse_qs(urlparse(init["auth_url"]).query)
    assert qs.get("code_challenge_method") == ["S256"]
    challenge = qs["code_challenge"][0]

    verifier = node.provider_cache[init["state"]]["code_verifier"]
    assert verifier  # verifier stored in cache

    # The emitted challenge MUST be the S256 transform of the cached verifier.
    assert challenge == _s256(verifier)


@pytest.mark.asyncio
async def test_exchange_sends_cached_code_verifier():
    """The cached code_verifier MUST flow into the token-exchange request."""
    node = _make_node()
    init = await node._initiate_oauth("oidc", "https://app.example.com/cb")
    cached = node.provider_cache.pop(init["state"])
    expected_verifier = cached["code_verifier"]

    captured = {}

    async def fake_http(**kwargs):
        captured.update(kwargs)
        return {"success": True, "response": {"access_token": "x"}}

    node.http_client.async_run = fake_http

    await node._exchange_oauth_code("oidc", "auth-code-123", cached)

    token_data = captured["data"]
    assert token_data["code_verifier"] == expected_verifier


def test_decode_id_token_rejects_non_object_payload():
    """A valid-JSON but non-object id_token payload fails closed with a typed
    ValueError (not an opaque AttributeError from a later ``claims.get``)."""
    import base64 as _b64
    import json as _json

    from kailash.nodes.auth.sso import SSOAuthenticationNode

    for non_object in (123, [1, 2], "just-a-string", True):
        payload = (
            _b64.urlsafe_b64encode(_json.dumps(non_object).encode())
            .rstrip(b"=")
            .decode()
        )
        token = f"header.{payload}.sig"
        with pytest.raises(ValueError, match="not a JSON object"):
            SSOAuthenticationNode._decode_id_token_claims(token)
