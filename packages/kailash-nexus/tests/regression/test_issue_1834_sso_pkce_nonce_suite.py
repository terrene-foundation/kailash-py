"""Regression suite for issue #1834 (Nexus mirror) — PKCE + id_token nonce
across the ``nexus.auth.sso`` provider-class suite AND the SSO flow helpers.

Mirror of the ``kailash.trust.auth.sso`` suite (the two are 1:1 mirrors). Covers:
    - Provider ``get_authorization_url`` emits PKCE ``code_challenge`` + ``S256``.
    - Provider ``exchange_code`` replays the ``code_verifier``.
    - Provider ``validate_id_token(nonce=...)`` accepts a match / rejects a
      mismatch on a REAL RSA/ES256-signed id_token verified via a real JWKS.
    - ``initiate_sso_login`` mints + persists PKCE verifier + OIDC nonce, and
      emits ``code_challenge`` (+ ``nonce`` for OIDC providers) on the auth URL.
    - ``handle_sso_callback`` replays the verifier + enforces the nonce
      (fail-closed on mismatch).

Follow-up to #1815 / #1835.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

pytestmark = pytest.mark.regression


class _JWKSHarness:
    """Real in-process JWKS harness (RS256 or ES256) — nothing mocked."""

    def __init__(self, alg: str):
        import jwt
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec, rsa

        self.alg = alg
        self.kid = "test-key-1834n"
        if alg == "RS256":
            self._priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            from jwt.algorithms import RSAAlgorithm

            jwk = json.loads(RSAAlgorithm.to_jwk(self._priv.public_key()))
        else:
            self._priv = ec.generate_private_key(ec.SECP256R1())
            from jwt.algorithms import ECAlgorithm

            jwk = json.loads(ECAlgorithm.to_jwk(self._priv.public_key()))
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
            "sub": "user-1834n",
            "aud": aud,
            "iss": iss,
            "iat": now,
            "exp": now + 3600,
            "email": "u@example.com",
            "name": "User",
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
# Provider classes — PKCE on the authorization URL
# ===========================================================================


def test_google_auth_url_emits_pkce_s256():
    from nexus.auth.sso import GoogleProvider

    p = GoogleProvider(client_id="test-client", client_secret="s")
    url = p.get_authorization_url(
        state="st", redirect_uri="https://app/cb", code_challenge="CHAL"
    )
    assert "code_challenge=CHAL" in url and "code_challenge_method=S256" in url


def test_azure_auth_url_emits_pkce_s256():
    from nexus.auth.sso import AzureADProvider

    p = AzureADProvider(tenant_id="t1", client_id="test-client", client_secret="s")
    url = p.get_authorization_url(
        state="st", redirect_uri="https://app/cb", code_challenge="CHAL"
    )
    assert "code_challenge=CHAL" in url and "code_challenge_method=S256" in url


def test_apple_auth_url_emits_pkce_s256(es256_harness):
    from nexus.auth.sso import AppleProvider

    p = AppleProvider(
        team_id="tm",
        client_id="test-client",
        key_id="k",
        private_key=es256_harness.apple_client_secret_key,
    )
    url = p.get_authorization_url(
        state="st", redirect_uri="https://app/cb", code_challenge="CHAL"
    )
    assert "code_challenge=CHAL" in url and "code_challenge_method=S256" in url


def test_github_auth_url_emits_pkce_and_no_id_token_support():
    from nexus.auth.sso import GitHubProvider

    p = GitHubProvider(client_id="test-client", client_secret="s")
    url = p.get_authorization_url(
        state="st", redirect_uri="https://app/cb", code_challenge="CHAL"
    )
    assert "code_challenge=CHAL" in url and "code_challenge_method=S256" in url
    assert p.supports_id_token is False


# ===========================================================================
# Provider classes — exchange_code replays code_verifier
# ===========================================================================


@pytest.mark.asyncio
async def test_google_exchange_replays_code_verifier(monkeypatch):
    from nexus.auth.sso import GoogleProvider

    p = GoogleProvider(client_id="c", client_secret="s")
    captured = {}

    async def _fake_post_form(url, data):
        captured["data"] = data
        return {"access_token": "at", "token_type": "Bearer", "expires_in": 3600}

    monkeypatch.setattr(p, "_post_form", _fake_post_form)
    await p.exchange_code("code", "https://app/cb", code_verifier="V-1")
    assert captured["data"]["code_verifier"] == "V-1"


@pytest.mark.asyncio
async def test_github_exchange_replays_code_verifier(monkeypatch):
    from nexus.auth.sso import GitHubProvider

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
    await p.exchange_code("code", "https://app/cb", code_verifier="V-GH")
    assert captured["data"]["code_verifier"] == "V-GH"


# ===========================================================================
# Provider classes — validate_id_token nonce accept/reject (real crypto)
# ===========================================================================


def test_google_validate_nonce_accept_and_reject(rs256_harness):
    from nexus.auth.sso import GoogleProvider, SSOAuthError

    p = GoogleProvider(client_id="test-client", client_secret="s")
    _point_jwks(p, rs256_harness)
    token = rs256_harness.sign(
        rs256_harness.base_claims(
            aud="test-client", iss="https://accounts.google.com", nonce="OK"
        )
    )
    assert p.validate_id_token(token, nonce="OK")["nonce"] == "OK"
    with pytest.raises(SSOAuthError, match="nonce mismatch"):
        p.validate_id_token(token, nonce="WRONG")


def test_azure_validate_nonce_accept_and_reject(rs256_harness):
    from nexus.auth.sso import AzureADProvider, SSOAuthError

    p = AzureADProvider(tenant_id="t1", client_id="test-client", client_secret="s")
    _point_jwks(p, rs256_harness)
    token = rs256_harness.sign(
        rs256_harness.base_claims(
            aud="test-client",
            iss="https://login.microsoftonline.com/t1/v2.0",
            nonce="OK",
        )
    )
    assert p.validate_id_token(token, nonce="OK")["nonce"] == "OK"
    with pytest.raises(SSOAuthError, match="nonce mismatch"):
        p.validate_id_token(token, nonce="WRONG")


def test_apple_validate_nonce_accept_and_reject(es256_harness):
    from nexus.auth.sso import AppleProvider, SSOAuthError

    p = AppleProvider(
        team_id="tm",
        client_id="test-client",
        key_id="k",
        private_key=es256_harness.apple_client_secret_key,
    )
    _point_jwks(p, es256_harness)
    token = es256_harness.sign(
        es256_harness.base_claims(
            aud="test-client", iss="https://appleid.apple.com", nonce="OK"
        )
    )
    assert p.validate_id_token(token, nonce="OK")["nonce"] == "OK"
    with pytest.raises(SSOAuthError, match="nonce mismatch"):
        p.validate_id_token(token, nonce="WRONG")


# ===========================================================================
# State store — persists code_verifier + nonce
# ===========================================================================


def test_state_store_round_trips_pkce_and_nonce():
    from nexus.auth.sso import InMemorySSOStateStore

    store = InMemorySSOStateStore()
    store.store("st", code_verifier="V", nonce="N")
    data = store.validate_and_consume("st")
    assert data == {"code_verifier": "V", "nonce": "N"}
    # single-use
    assert store.validate_and_consume("st") is None


def test_state_store_without_data_is_valid_dict():
    """A plain CSRF state (no PKCE/nonce) still validates as a truthy dict."""
    from nexus.auth.sso import InMemorySSOStateStore

    store = InMemorySSOStateStore()
    store.store("st")
    data = store.validate_and_consume("st")
    assert data == {"code_verifier": None, "nonce": None}
    assert data  # truthy → `if not validate_and_consume(...)` stays correct


# ===========================================================================
# initiate_sso_login — mints + persists PKCE + nonce, emits on the auth URL
# ===========================================================================


@pytest.mark.asyncio
async def test_initiate_oidc_provider_mints_pkce_and_nonce():
    from nexus.auth.sso import (
        GoogleProvider,
        InMemorySSOStateStore,
        _get_state_store,
        configure_state_store,
        initiate_sso_login,
    )

    configure_state_store(InMemorySSOStateStore())
    p = GoogleProvider(client_id="c", client_secret="s")
    resp = await initiate_sso_login(p, "https://app.example.com")

    url = resp.headers["location"]
    qs = parse_qs(urlparse(url).query)
    assert qs["code_challenge_method"] == ["S256"]
    assert qs["code_challenge"][0]
    assert qs["nonce"][0]  # OIDC provider → nonce emitted

    state = qs["state"][0]
    data = _get_state_store().validate_and_consume(state)
    assert data["code_verifier"] and data["nonce"] == qs["nonce"][0]


@pytest.mark.asyncio
async def test_initiate_github_mints_pkce_but_no_nonce():
    from nexus.auth.sso import (
        GitHubProvider,
        InMemorySSOStateStore,
        _get_state_store,
        configure_state_store,
        initiate_sso_login,
    )

    configure_state_store(InMemorySSOStateStore())
    p = GitHubProvider(client_id="c", client_secret="s")
    resp = await initiate_sso_login(p, "https://app.example.com")

    url = resp.headers["location"]
    qs = parse_qs(urlparse(url).query)
    assert qs["code_challenge_method"] == ["S256"]
    assert "nonce" not in qs  # GitHub is not OIDC → no nonce

    state = qs["state"][0]
    data = _get_state_store().validate_and_consume(state)
    assert data["code_verifier"] and data["nonce"] is None


# ===========================================================================
# handle_sso_callback — replays verifier + enforces nonce end-to-end
# ===========================================================================


class _FakeJWTMiddleware:
    def create_access_token(self, **kw):
        return "access-token"

    def create_refresh_token(self, **kw):
        return "refresh-token"


class _FakeAuthPlugin:
    _jwt_middleware = _FakeJWTMiddleware()


@pytest.mark.asyncio
async def test_handle_callback_rejects_mismatched_nonce(rs256_harness, monkeypatch):
    from nexus.auth.sso import (
        GoogleProvider,
        InMemorySSOStateStore,
        SSOAuthError,
        configure_state_store,
        handle_sso_callback,
    )
    from nexus.auth.sso.base import SSOTokenResponse

    configure_state_store(InMemorySSOStateStore())
    store = InMemorySSOStateStore()
    configure_state_store(store)
    store.store("st", code_verifier="V", nonce="EXPECTED-NONCE")

    p = GoogleProvider(client_id="test-client", client_secret="s")
    _point_jwks(p, rs256_harness)
    forged = rs256_harness.sign(
        rs256_harness.base_claims(
            aud="test-client",
            iss="https://accounts.google.com",
            nonce="ATTACKER-NONCE",
        )
    )
    captured = {}

    async def _fake_exchange(code, redirect_uri, code_verifier=None):
        captured["code_verifier"] = code_verifier
        return SSOTokenResponse(access_token="at", id_token=forged)

    monkeypatch.setattr(p, "exchange_code", _fake_exchange)

    with pytest.raises(SSOAuthError, match="nonce mismatch"):
        await handle_sso_callback(p, "code", "st", _FakeAuthPlugin(), "https://app")

    # The verifier was replayed to exchange_code before the nonce gate.
    assert captured["code_verifier"] == "V"


@pytest.mark.asyncio
async def test_handle_callback_accepts_matching_nonce(rs256_harness, monkeypatch):
    from nexus.auth.sso import (
        GoogleProvider,
        InMemorySSOStateStore,
        configure_state_store,
        handle_sso_callback,
    )
    from nexus.auth.sso.base import SSOTokenResponse

    store = InMemorySSOStateStore()
    configure_state_store(store)
    store.store("st", code_verifier="V", nonce="GOOD-NONCE")

    p = GoogleProvider(client_id="test-client", client_secret="s")
    _point_jwks(p, rs256_harness)
    good = rs256_harness.sign(
        rs256_harness.base_claims(
            aud="test-client", iss="https://accounts.google.com", nonce="GOOD-NONCE"
        )
    )

    async def _fake_exchange(code, redirect_uri, code_verifier=None):
        return SSOTokenResponse(access_token="at", id_token=good)

    monkeypatch.setattr(p, "exchange_code", _fake_exchange)

    result = await handle_sso_callback(
        p, "code", "st", _FakeAuthPlugin(), "https://app"
    )
    assert result["access_token"] == "access-token"
    assert result["user"]["id"] == "user-1834n"
