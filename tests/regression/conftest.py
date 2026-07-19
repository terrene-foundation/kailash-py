"""Shared regression fixtures.

``oidc_jwks_server`` — a REAL in-process OIDC JWKS test harness backing the
issue #1835 (JWKS id_token verification) + #1815 (nonce/PKCE) regression suites.

The harness mints a real RSA keypair, serves its public half as a JWKS over a
loopback HTTP endpoint (so PyJWT's ``PyJWKClient`` performs a real network
fetch), and signs real RS256 id_tokens with the private half. Signature
verification exercised by the tests is the SDK's REAL ``jwt.decode`` against the
served JWKS — nothing about the verifier is mocked (per ``rules/testing.md``
Tier-2 NO-MOCKING contract for security-critical paths).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Optional

import pytest


@dataclass
class OIDCJWKSHarness:
    """Real RSA-signing OIDC harness (see module docstring)."""

    jwks_uri: str
    issuer: str
    audience: str
    kid: str
    _sign: Callable[..., str]
    _wrong_sign: Callable[..., str]

    def sign(self, claims: Dict[str, Any]) -> str:
        """Sign an id_token with the harness's real key (valid signature)."""
        return self._sign(claims)

    def sign_forged(self, claims: Dict[str, Any]) -> str:
        """Sign with a DIFFERENT key but present the trusted ``kid``.

        The JWKS returns the harness's real public key for that ``kid``, so the
        signature check runs against the wrong key and fails — a genuine forged
        signature, verified by real crypto, not a mock.
        """
        return self._wrong_sign(claims)

    def base_claims(self, **overrides: Any) -> Dict[str, Any]:
        """A valid claim set (correct aud/iss, future exp) for mutation."""
        now = int(time.time())
        claims: Dict[str, Any] = {
            "sub": "user-1",
            "aud": self.audience,
            "iss": self.issuer,
            "iat": now,
            "exp": now + 3600,
            "email": "user@example.com",
            "name": "User One",
        }
        claims.update(overrides)
        return claims


@pytest.fixture
def oidc_jwks_server():
    """Yield a real RSA-signing JWKS harness on a loopback HTTP endpoint."""
    import json

    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from jwt.algorithms import RSAAlgorithm

    kid = "test-key-1"
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    # A SECOND, unrelated key — used to forge signatures the JWKS cannot verify.
    wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    jwk = json.loads(RSAAlgorithm.to_jwk(public_key))
    jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    jwks_body = json.dumps({"keys": [jwk]}).encode()

    class _JWKSHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (BaseHTTPRequestHandler API)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(jwks_body)))
            self.end_headers()
            self.wfile.write(jwks_body)

        def log_message(self, *args):  # silence per-request stderr noise
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), _JWKSHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    jwks_uri = f"http://{host}:{port}/jwks"

    def _sign(claims: Dict[str, Any]) -> str:
        return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})

    def _wrong_sign(claims: Dict[str, Any]) -> str:
        # Present the trusted kid so the JWKS returns the real public key; the
        # signature (made with wrong_key) then fails verification.
        return jwt.encode(claims, wrong_key, algorithm="RS256", headers={"kid": kid})

    harness = OIDCJWKSHarness(
        jwks_uri=jwks_uri,
        issuer="https://idp.example.com",
        audience="test-client",
        kid=kid,
        _sign=_sign,
        _wrong_sign=_wrong_sign,
    )
    try:
        yield harness
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
