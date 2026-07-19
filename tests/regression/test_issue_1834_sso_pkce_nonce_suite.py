"""Regression suite for issue #1834 — PKCE + id_token nonce across the SSO
provider-class suite AND the SSOAuthenticationNode initiators.

Part A: ``kailash.trust.auth.sso`` provider classes (Google/Azure/Apple/GitHub)
    - ``get_authorization_url`` emits PKCE ``code_challenge`` + ``S256``.
    - ``exchange_code`` replays the ``code_verifier`` to the token endpoint.
    - ``validate_id_token(nonce=...)`` ACCEPTS a matching nonce and REJECTS a
      mismatch, against a REAL RSA/ES256-signed id_token verified via a real
      in-process JWKS (nothing about the verifier is mocked).

Part B: ``kailash.nodes.auth.sso.SSOAuthenticationNode``
    - ``_initiate_azure_ad`` / ``_initiate_google`` / ``_initiate_okta`` mint +
      cache a nonce (previously only ``provider=="oidc"`` did).
    - ``_handle_oauth_callback`` REJECTS a mismatched nonce for those providers
      against a real JWKS-verified id_token (the #1835 verified path), and
      ACCEPTS a matching one.

Follow-up to #1815 (node PKCE+nonce) and #1835 (node JWKS id_token verify).
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# Real in-process JWKS harness (RS256 for Google/Azure, ES256 for Apple).
# Mints a real keypair, serves the public half as a JWKS over loopback so
# PyJWT's PyJWKClient performs a real fetch, and signs real id_tokens.
# ---------------------------------------------------------------------------


class _JWKSHarness:
    def __init__(self, alg: str):
        import jwt
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec, rsa

        self.alg = alg
        self.kid = "test-key-1834"
        if alg == "RS256":
            self._priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            from jwt.algorithms import RSAAlgorithm

            jwk = json.loads(RSAAlgorithm.to_jwk(self._priv.public_key()))
        elif alg == "ES256":
            self._priv = ec.generate_private_key(ec.SECP256R1())
            from jwt.algorithms import ECAlgorithm

            jwk = json.loads(ECAlgorithm.to_jwk(self._priv.public_key()))
        else:  # pragma: no cover - test misconfiguration
            raise ValueError(alg)
        jwk.update({"kid": self.kid, "use": "sig", "alg": alg})
        body = json.dumps({"keys": [jwk]}).encode()
        self._jwt = jwt

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        host, port = self._server.server_address
        self.jwks_uri = f"http://{host}:{port}/jwks"
        # An EC private key PEM for AppleProvider's client-secret generation.
        self.apple_client_secret_key = (
            ec.generate_private_key(ec.SECP256R1())
            .private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
            .decode()
        )

    def sign(self, claims: dict) -> str:
        return self._jwt.encode(
            claims, self._priv, algorithm=self.alg, headers={"kid": self.kid}
        )

    def base_claims(self, *, aud: str, iss: str, **overrides) -> dict:
        now = int(time.time())
        claims = {
            "sub": "user-1834",
            "aud": aud,
            "iss": iss,
            "iat": now,
            "exp": now + 3600,
            "email": "u@example.com",
            "name": "User 1834",
        }
        claims.update(overrides)
        return claims

    def close(self):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


@pytest.fixture
def rs256_harness():
    h = _JWKSHarness("RS256")
    try:
        yield h
    finally:
        h.close()


@pytest.fixture
def es256_harness():
    h = _JWKSHarness("ES256")
    try:
        yield h
    finally:
        h.close()


def _point_jwks(provider, harness):
    from jwt import PyJWKClient

    provider._jwks_client = PyJWKClient(harness.jwks_uri)


# ===========================================================================
# Part A — provider classes: PKCE on the authorization URL
# ===========================================================================


def test_google_auth_url_emits_pkce_s256():
    from kailash.trust.auth.sso import GoogleProvider

    p = GoogleProvider(client_id="test-client", client_secret="s")
    url = p.get_authorization_url(
        state="st", redirect_uri="https://app/cb", code_challenge="CHAL"
    )
    assert "code_challenge=CHAL" in url
    assert "code_challenge_method=S256" in url


def test_azure_auth_url_emits_pkce_s256():
    from kailash.trust.auth.sso import AzureADProvider

    p = AzureADProvider(tenant_id="t1", client_id="test-client", client_secret="s")
    url = p.get_authorization_url(
        state="st", redirect_uri="https://app/cb", code_challenge="CHAL"
    )
    assert "code_challenge=CHAL" in url
    assert "code_challenge_method=S256" in url


def test_apple_auth_url_emits_pkce_s256(es256_harness):
    from kailash.trust.auth.sso import AppleProvider

    p = AppleProvider(
        team_id="tm",
        client_id="test-client",
        key_id="k",
        private_key=es256_harness.apple_client_secret_key,
    )
    url = p.get_authorization_url(
        state="st", redirect_uri="https://app/cb", code_challenge="CHAL"
    )
    assert "code_challenge=CHAL" in url
    assert "code_challenge_method=S256" in url


def test_github_auth_url_emits_pkce_s256():
    from kailash.trust.auth.sso import GitHubProvider

    p = GitHubProvider(client_id="test-client", client_secret="s")
    url = p.get_authorization_url(
        state="st", redirect_uri="https://app/cb", code_challenge="CHAL"
    )
    assert "code_challenge=CHAL" in url
    assert "code_challenge_method=S256" in url
    # GitHub is not OIDC — nonce enforcement does not apply.
    assert p.supports_id_token is False


def test_pkce_pair_challenge_is_s256_of_verifier():
    """generate_pkce_pair() produces a valid RFC 7636 S256 challenge."""
    import base64
    import hashlib

    from kailash.trust.auth.sso import GoogleProvider

    verifier, challenge = GoogleProvider.generate_pkce_pair()
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    assert challenge == expected
    assert "=" not in challenge  # no base64 padding


# ===========================================================================
# Part A — provider classes: exchange_code replays code_verifier
# ===========================================================================


@pytest.mark.asyncio
async def test_google_exchange_replays_code_verifier(monkeypatch):
    from kailash.trust.auth.sso import GoogleProvider

    p = GoogleProvider(client_id="c", client_secret="s")
    captured = {}

    async def _fake_post_form(url, data):
        captured["data"] = data
        return {"access_token": "at", "token_type": "Bearer", "expires_in": 3600}

    monkeypatch.setattr(p, "_post_form", _fake_post_form)
    await p.exchange_code("code", "https://app/cb", code_verifier="VERIFIER-123")
    assert captured["data"]["code_verifier"] == "VERIFIER-123"


@pytest.mark.asyncio
async def test_azure_exchange_replays_code_verifier(monkeypatch):
    from kailash.trust.auth.sso import AzureADProvider

    p = AzureADProvider(tenant_id="t1", client_id="c", client_secret="s")
    captured = {}

    async def _fake_post_form(url, data):
        captured["data"] = data
        return {"access_token": "at", "token_type": "Bearer", "expires_in": 3600}

    monkeypatch.setattr(p, "_post_form", _fake_post_form)
    await p.exchange_code("code", "https://app/cb", code_verifier="VERIFIER-AZ")
    assert captured["data"]["code_verifier"] == "VERIFIER-AZ"


@pytest.mark.asyncio
async def test_apple_exchange_replays_code_verifier(monkeypatch, es256_harness):
    from kailash.trust.auth.sso import AppleProvider

    p = AppleProvider(
        team_id="tm",
        client_id="c",
        key_id="k",
        private_key=es256_harness.apple_client_secret_key,
    )
    captured = {}

    async def _fake_post_form(url, data):
        captured["data"] = data
        return {"access_token": "at", "token_type": "Bearer", "expires_in": 3600}

    monkeypatch.setattr(p, "_post_form", _fake_post_form)
    await p.exchange_code("code", "https://app/cb", code_verifier="VERIFIER-AP")
    assert captured["data"]["code_verifier"] == "VERIFIER-AP"


@pytest.mark.asyncio
async def test_github_exchange_replays_code_verifier(monkeypatch):
    from kailash.trust.auth.sso import GitHubProvider

    p = GitHubProvider(client_id="c", client_secret="s")
    captured = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {"access_token": "at", "token_type": "Bearer", "scope": ""}

    class _Client:
        async def post(self, url, data=None, headers=None):
            captured["data"] = data
            return _Resp()

    async def _get_client():
        return _Client()

    monkeypatch.setattr(p, "_get_http_client", _get_client)
    await p.exchange_code("code", "https://app/cb", code_verifier="VERIFIER-GH")
    assert captured["data"]["code_verifier"] == "VERIFIER-GH"


# ===========================================================================
# Part A — provider classes: validate_id_token nonce accept/reject
# (real-signed tokens, real JWKS verification)
# ===========================================================================


def test_google_validate_id_token_nonce_accept_and_reject(rs256_harness):
    from kailash.trust.auth.sso import GoogleProvider, SSOAuthError

    p = GoogleProvider(client_id="test-client", client_secret="s")
    _point_jwks(p, rs256_harness)
    token = rs256_harness.sign(
        rs256_harness.base_claims(
            aud="test-client", iss="https://accounts.google.com", nonce="NONCE-OK"
        )
    )
    # Accept: matching nonce returns claims.
    claims = p.validate_id_token(token, nonce="NONCE-OK")
    assert claims["nonce"] == "NONCE-OK"
    assert claims["sub"] == "user-1834"
    # Reject: mismatched nonce raises.
    with pytest.raises(SSOAuthError, match="nonce mismatch"):
        p.validate_id_token(token, nonce="WRONG")


def test_google_validate_id_token_missing_nonce_claim_rejected(rs256_harness):
    """A minted-nonce flow whose id_token carries NO nonce claim fails closed."""
    from kailash.trust.auth.sso import GoogleProvider, SSOAuthError

    p = GoogleProvider(client_id="test-client", client_secret="s")
    _point_jwks(p, rs256_harness)
    token = rs256_harness.sign(
        rs256_harness.base_claims(aud="test-client", iss="https://accounts.google.com")
    )
    with pytest.raises(SSOAuthError, match="nonce mismatch"):
        p.validate_id_token(token, nonce="EXPECTED")


def test_google_validate_id_token_no_nonce_when_not_requested(rs256_harness):
    """nonce=None skips enforcement (no nonce was minted for this flow)."""
    from kailash.trust.auth.sso import GoogleProvider

    p = GoogleProvider(client_id="test-client", client_secret="s")
    _point_jwks(p, rs256_harness)
    token = rs256_harness.sign(
        rs256_harness.base_claims(aud="test-client", iss="https://accounts.google.com")
    )
    claims = p.validate_id_token(token)  # nonce defaults to None
    assert claims["sub"] == "user-1834"


def test_azure_validate_id_token_nonce_accept_and_reject(rs256_harness):
    from kailash.trust.auth.sso import AzureADProvider, SSOAuthError

    p = AzureADProvider(tenant_id="t1", client_id="test-client", client_secret="s")
    _point_jwks(p, rs256_harness)
    iss = "https://login.microsoftonline.com/t1/v2.0"
    token = rs256_harness.sign(
        rs256_harness.base_claims(aud="test-client", iss=iss, nonce="AZ-NONCE")
    )
    claims = p.validate_id_token(token, nonce="AZ-NONCE")
    assert claims["nonce"] == "AZ-NONCE"
    with pytest.raises(SSOAuthError, match="nonce mismatch"):
        p.validate_id_token(token, nonce="WRONG")


def test_apple_validate_id_token_nonce_accept_and_reject(es256_harness):
    from kailash.trust.auth.sso import AppleProvider, SSOAuthError

    p = AppleProvider(
        team_id="tm",
        client_id="test-client",
        key_id="k",
        private_key=es256_harness.apple_client_secret_key,
    )
    _point_jwks(p, es256_harness)
    token = es256_harness.sign(
        es256_harness.base_claims(
            aud="test-client", iss="https://appleid.apple.com", nonce="AP-NONCE"
        )
    )
    claims = p.validate_id_token(token, nonce="AP-NONCE")
    assert claims["nonce"] == "AP-NONCE"
    with pytest.raises(SSOAuthError, match="nonce mismatch"):
        p.validate_id_token(token, nonce="WRONG")


# ===========================================================================
# Part B — SSOAuthenticationNode: nonce minting + callback enforcement
# ===========================================================================


def _make_node(*, enable_jit_provisioning: bool = True):
    from kailash.nodes.auth.sso import SSOAuthenticationNode

    # enable_jit_provisioning=False isolates the nonce gate from the unrelated
    # audit-logger provisioning path (the #1815/#1835 test convention).
    return SSOAuthenticationNode(
        name="sso_1834", enable_jit_provisioning=enable_jit_provisioning
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "initiator,provider",
    [
        ("_initiate_azure_ad", "azure"),
        ("_initiate_google", "google"),
        ("_initiate_okta", "okta"),
    ],
)
async def test_node_initiators_mint_and_cache_nonce(initiator, provider):
    node = _make_node()
    result = await getattr(node, initiator)("https://app/cb")
    state = result["state"]
    # The auth URL carries the nonce, and it is cached for callback enforcement.
    assert "nonce=" in result["auth_url"]
    cached = node.provider_cache[state]
    assert cached["nonce"], f"{provider} initiator must cache a nonce"
    assert cached["provider"] == provider
    # PKCE verifier is also cached (from #1815).
    assert cached["code_verifier"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "initiator,provider",
    [
        ("_initiate_azure_ad", "azure"),
        ("_initiate_google", "google"),
        ("_initiate_okta", "okta"),
    ],
)
async def test_node_callback_rejects_mismatched_nonce(
    initiator, provider, oidc_jwks_server, monkeypatch
):
    node = _make_node()
    node.oauth_settings.update(
        {
            "jwks_uri": oidc_jwks_server.jwks_uri,
            "issuer": oidc_jwks_server.issuer,
            f"{provider}_client_id": oidc_jwks_server.audience,
        }
    )
    result = await getattr(node, initiator)("https://app/cb")
    state = result["state"]
    expected_nonce = node.provider_cache[state]["nonce"]

    # A real-signed id_token whose nonce does NOT match the minted value.
    forged = oidc_jwks_server.sign(oidc_jwks_server.base_claims(nonce="ATTACKER-NONCE"))
    assert expected_nonce != "ATTACKER-NONCE"

    async def _fake_exchange(prov, code, cached):
        return {"access_token": "at", "id_token": forged}

    monkeypatch.setattr(node, "_exchange_oauth_code", _fake_exchange)

    with pytest.raises(ValueError, match="nonce"):
        await node._handle_oauth_callback(
            provider, {"state": state, "code": "authcode"}
        )


@pytest.mark.asyncio
async def test_node_callback_accepts_matching_nonce(oidc_jwks_server, monkeypatch):
    node = _make_node(enable_jit_provisioning=False)
    node.oauth_settings.update(
        {
            "jwks_uri": oidc_jwks_server.jwks_uri,
            "issuer": oidc_jwks_server.issuer,
            "google_client_id": oidc_jwks_server.audience,
        }
    )
    result = await node._initiate_google("https://app/cb")
    state = result["state"]
    expected_nonce = node.provider_cache[state]["nonce"]

    good = oidc_jwks_server.sign(oidc_jwks_server.base_claims(nonce=expected_nonce))

    async def _fake_exchange(prov, code, cached):
        return {"access_token": "at", "id_token": good}

    async def _fake_userinfo(prov, access_token):
        return {"sub": "s", "email": "u@example.com", "name": "U"}

    monkeypatch.setattr(node, "_exchange_oauth_code", _fake_exchange)
    monkeypatch.setattr(node, "_get_oauth_user_info", _fake_userinfo)

    out = await node._handle_oauth_callback("google", {"state": state, "code": "ac"})
    assert out["authenticated"] is True
