"""Regression tests for issue #1835 — SSO id_token JWKS verification.

Before the fix, ``SSOAuthenticationNode._handle_oauth_callback`` read the OIDC
``nonce`` claim from an UNVERIFIED id_token: ``_decode_id_token_claims`` was a
base64url-only decode (no signature, no aud, no iss, no exp validation), so a
forged id_token carrying the expected nonce was trusted — an authentication
bypass surface.

The fix adds ``_verify_id_token`` — a JWKS-backed ``jwt.decode`` (RS256/ES256,
audience + issuer + expiry enforced) reusing the provider-class pattern
(``kailash.trust.auth.sso.google``). The nonce is now compared ONLY against
cryptographically verified claims, and the path fails closed when verification
config is missing, the JWKS is unreachable, or verification fails.

These tests use REAL RSA signing + a REAL in-process JWKS endpoint (the
``oidc_jwks_server`` fixture); nothing about the verifier is mocked.

Assertions pinned here:
1. valid token (right key, correct aud/iss/exp, matching nonce) -> ACCEPTED
2. forged signature (signed by a different key)               -> REJECTED
3. wrong audience                                             -> REJECTED
4. wrong issuer                                               -> REJECTED
5. expired (exp in the past)                                  -> REJECTED
6. fail-closed: jwks_uri unconfigured / JWKS unreachable      -> REJECTED
"""

import time

import pytest

from kailash.nodes.auth.sso import SSOAuthenticationNode

pytestmark = pytest.mark.regression


def _make_node(oauth_settings) -> SSOAuthenticationNode:
    return SSOAuthenticationNode(
        name="sso_1835",
        enable_jit_provisioning=False,  # isolate the verify+nonce gate
        oauth_settings=oauth_settings,
    )


def _oauth_settings(harness, *, jwks_uri=..., issuer=..., client_id=...):
    return {
        "client_id": harness.audience if client_id is ... else client_id,
        "auth_endpoint": "https://idp.example.com/oauth2/authorize",
        "token_endpoint": "https://idp.example.com/oauth2/token",
        "userinfo_endpoint": "https://idp.example.com/oauth2/userinfo",
        "jwks_uri": harness.jwks_uri if jwks_uri is ... else jwks_uri,
        "issuer": harness.issuer if issuer is ... else issuer,
    }


async def _seed(node) -> tuple[str, str]:
    """Run the authorize step; return (state, minted_nonce)."""
    init = await node._initiate_oauth("oidc", "https://app.example.com/cb")
    state = init["state"]
    minted = node.provider_cache[state]["nonce"]
    assert minted  # sanity: a nonce was minted
    return state, minted


async def _callback(node, state, id_token):
    """Drive _handle_oauth_callback with a fixed token response."""

    async def fake_exchange(provider, auth_code, cached_data):
        resp = {"access_token": "at", "token_type": "Bearer"}
        if id_token is not None:
            resp["id_token"] = id_token
        return resp

    async def fake_userinfo(provider, access_token):
        return {"sub": "user-1", "email": "user@example.com", "name": "User One"}

    node._exchange_oauth_code = fake_exchange
    node._get_oauth_user_info = fake_userinfo
    return await node._handle_oauth_callback(
        "oidc", {"state": state, "code": "auth-code-1"}
    )


# --------------------------------------------------------------------------- #
# (1) valid token accepted
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_valid_signed_token_with_matching_nonce_accepted(oidc_jwks_server):
    node = _make_node(_oauth_settings(oidc_jwks_server))
    state, minted = await _seed(node)
    token = oidc_jwks_server.sign(oidc_jwks_server.base_claims(nonce=minted))

    result = await _callback(node, state, token)

    assert result["authenticated"] is True


# --------------------------------------------------------------------------- #
# (2) forged signature rejected
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_forged_signature_rejected(oidc_jwks_server):
    """A token signed by a DIFFERENT key (presenting the trusted kid) fails the
    real signature check and is rejected before its nonce is trusted."""
    node = _make_node(_oauth_settings(oidc_jwks_server))
    state, minted = await _seed(node)
    forged = oidc_jwks_server.sign_forged(oidc_jwks_server.base_claims(nonce=minted))

    with pytest.raises(ValueError, match="verification failed"):
        await _callback(node, state, forged)


# --------------------------------------------------------------------------- #
# (3) wrong audience rejected
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_wrong_audience_rejected(oidc_jwks_server):
    node = _make_node(_oauth_settings(oidc_jwks_server))
    state, minted = await _seed(node)
    token = oidc_jwks_server.sign(
        oidc_jwks_server.base_claims(nonce=minted, aud="some-other-client")
    )

    with pytest.raises(ValueError, match="audience"):
        await _callback(node, state, token)


# --------------------------------------------------------------------------- #
# (4) wrong issuer rejected
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_wrong_issuer_rejected(oidc_jwks_server):
    node = _make_node(_oauth_settings(oidc_jwks_server))
    state, minted = await _seed(node)
    token = oidc_jwks_server.sign(
        oidc_jwks_server.base_claims(nonce=minted, iss="https://evil.example.com")
    )

    with pytest.raises(ValueError, match="issuer"):
        await _callback(node, state, token)


# --------------------------------------------------------------------------- #
# (5) expired token rejected
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_expired_token_rejected(oidc_jwks_server):
    node = _make_node(_oauth_settings(oidc_jwks_server))
    state, minted = await _seed(node)
    past = int(time.time()) - 3600
    token = oidc_jwks_server.sign(
        oidc_jwks_server.base_claims(nonce=minted, iat=past - 60, exp=past)
    )

    with pytest.raises(ValueError, match="expired"):
        await _callback(node, state, token)


# --------------------------------------------------------------------------- #
# (6) fail-closed: unconfigured jwks_uri / unreachable JWKS
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_fail_closed_when_jwks_uri_unconfigured(oidc_jwks_server):
    """A nonce flow with NO jwks_uri configured MUST reject — never fall back
    to trusting an unverified id_token."""
    node = _make_node(_oauth_settings(oidc_jwks_server, jwks_uri=None))
    state, minted = await _seed(node)
    # Even a correctly-signed token cannot be trusted with no JWKS configured.
    token = oidc_jwks_server.sign(oidc_jwks_server.base_claims(nonce=minted))

    with pytest.raises(ValueError, match="jwks_uri"):
        await _callback(node, state, token)


@pytest.mark.asyncio
async def test_fail_closed_when_jwks_unreachable(oidc_jwks_server):
    """A configured-but-unreachable JWKS endpoint MUST reject, not accept."""
    node = _make_node(
        _oauth_settings(
            oidc_jwks_server, jwks_uri="http://127.0.0.1:1/jwks"  # dead port
        )
    )
    state, minted = await _seed(node)
    token = oidc_jwks_server.sign(oidc_jwks_server.base_claims(nonce=minted))

    with pytest.raises(ValueError, match="verification failed"):
        await _callback(node, state, token)


# --------------------------------------------------------------------------- #
# structural: the base64url display helper is NOT used for the trust decision
# --------------------------------------------------------------------------- #


def test_nonce_trust_path_uses_verified_claims_not_base64url_decode():
    """The callback trust path must call _verify_id_token, not the unverified
    base64url _decode_id_token_claims helper."""
    import inspect

    src = inspect.getsource(SSOAuthenticationNode._handle_oauth_callback)
    assert "_verify_id_token" in src
    assert "_decode_id_token_claims" not in src
