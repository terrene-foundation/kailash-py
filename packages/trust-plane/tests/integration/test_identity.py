# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for identity/OIDC module.

Tests IdentityProvider serialization, IdentityConfig persistence,
OIDCVerifier JWT verification with locally-generated tokens, and
JWKSProvider auto-discovery and caching.
"""

from __future__ import annotations

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from trustplane.identity import (
    IdentityConfig,
    IdentityProvider,
    JWKSProvider,
    OIDCVerifier,
    SUPPORTED_PROVIDERS,
)
from trustplane.identity import JWKSError


# ---------------------------------------------------------------------------
# Helpers: RSA key pair for test JWT signing/verification
# ---------------------------------------------------------------------------


@pytest.fixture
def rsa_key_pair():
    """Generate an RSA key pair for JWT signing tests."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    public_key = private_key.public_key()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


@pytest.fixture
def identity_dir(tmp_path):
    """Create a temporary directory for identity config."""
    d = tmp_path / "trust-plane"
    d.mkdir()
    return d


@pytest.fixture
def config_path(identity_dir):
    """Return the path for identity-config.json."""
    return identity_dir / "identity-config.json"


# ---------------------------------------------------------------------------
# IdentityProvider Tests
# ---------------------------------------------------------------------------


class TestIdentityProvider:
    """Test IdentityProvider dataclass."""

    def test_create_provider(self):
        provider = IdentityProvider(
            provider_type="okta",
            domain="dev-12345.okta.com",
            client_id="abc123",
            issuer_url="https://dev-12345.okta.com/oauth2/default",
        )
        assert provider.provider_type == "okta"
        assert provider.domain == "dev-12345.okta.com"
        assert provider.client_id == "abc123"
        assert provider.issuer_url == "https://dev-12345.okta.com/oauth2/default"

    def test_to_dict(self):
        provider = IdentityProvider(
            provider_type="azure_ad",
            domain="mycompany.onmicrosoft.com",
            client_id="client-xyz",
            issuer_url="https://login.microsoftonline.com/tenant-id/v2.0",
        )
        data = provider.to_dict()
        assert data["provider_type"] == "azure_ad"
        assert data["domain"] == "mycompany.onmicrosoft.com"
        assert data["client_id"] == "client-xyz"
        assert data["issuer_url"] == "https://login.microsoftonline.com/tenant-id/v2.0"

    def test_from_dict(self):
        data = {
            "provider_type": "google",
            "domain": "mycompany.com",
            "client_id": "google-client-id",
            "issuer_url": "https://accounts.google.com",
        }
        provider = IdentityProvider.from_dict(data)
        assert provider.provider_type == "google"
        assert provider.domain == "mycompany.com"
        assert provider.client_id == "google-client-id"
        assert provider.issuer_url == "https://accounts.google.com"

    def test_from_dict_roundtrip(self):
        original = IdentityProvider(
            provider_type="generic_oidc",
            domain="idp.example.com",
            client_id="generic-id",
            issuer_url="https://idp.example.com",
        )
        restored = IdentityProvider.from_dict(original.to_dict())
        assert restored.provider_type == original.provider_type
        assert restored.domain == original.domain
        assert restored.client_id == original.client_id
        assert restored.issuer_url == original.issuer_url

    def test_from_dict_missing_required_field_raises(self):
        with pytest.raises(ValueError, match="provider_type"):
            IdentityProvider.from_dict(
                {
                    "domain": "example.com",
                    "client_id": "id",
                    "issuer_url": "https://example.com",
                }
            )

    def test_from_dict_missing_domain_raises(self):
        with pytest.raises(ValueError, match="domain"):
            IdentityProvider.from_dict(
                {
                    "provider_type": "okta",
                    "client_id": "id",
                    "issuer_url": "https://example.com",
                }
            )

    def test_from_dict_missing_client_id_raises(self):
        with pytest.raises(ValueError, match="client_id"):
            IdentityProvider.from_dict(
                {
                    "provider_type": "okta",
                    "domain": "example.com",
                    "issuer_url": "https://example.com",
                }
            )

    def test_from_dict_missing_issuer_url_raises(self):
        with pytest.raises(ValueError, match="issuer_url"):
            IdentityProvider.from_dict(
                {
                    "provider_type": "okta",
                    "domain": "example.com",
                    "client_id": "id",
                }
            )

    def test_unsupported_provider_raises(self):
        with pytest.raises(ValueError, match="Unsupported provider"):
            IdentityProvider(
                provider_type="auth0",
                domain="example.auth0.com",
                client_id="id",
                issuer_url="https://example.auth0.com",
            )

    def test_issuer_url_must_be_https(self):
        with pytest.raises(ValueError, match="issuer_url must use HTTPS"):
            IdentityProvider(
                provider_type="okta",
                domain="example.okta.com",
                client_id="id",
                issuer_url="http://example.okta.com",
            )

    def test_supported_providers(self):
        assert "okta" in SUPPORTED_PROVIDERS
        assert "azure_ad" in SUPPORTED_PROVIDERS
        assert "google" in SUPPORTED_PROVIDERS
        assert "generic_oidc" in SUPPORTED_PROVIDERS
        assert len(SUPPORTED_PROVIDERS) == 4


# ---------------------------------------------------------------------------
# IdentityConfig Tests
# ---------------------------------------------------------------------------


class TestIdentityConfig:
    """Test IdentityConfig persistence."""

    def test_configure_and_get(self, config_path):
        config = IdentityConfig(config_path)
        provider = IdentityProvider(
            provider_type="okta",
            domain="dev-12345.okta.com",
            client_id="abc123",
            issuer_url="https://dev-12345.okta.com/oauth2/default",
        )
        config.configure(provider)
        loaded = config.get_provider()
        assert loaded is not None
        assert loaded.provider_type == "okta"
        assert loaded.domain == "dev-12345.okta.com"

    def test_is_configured_false_initially(self, config_path):
        config = IdentityConfig(config_path)
        assert config.is_configured() is False

    def test_is_configured_true_after_configure(self, config_path):
        config = IdentityConfig(config_path)
        provider = IdentityProvider(
            provider_type="google",
            domain="mycompany.com",
            client_id="google-id",
            issuer_url="https://accounts.google.com",
        )
        config.configure(provider)
        assert config.is_configured() is True

    def test_get_provider_none_when_unconfigured(self, config_path):
        config = IdentityConfig(config_path)
        assert config.get_provider() is None

    def test_persistence_across_instances(self, config_path):
        """Configure in one instance, reload in another."""
        config1 = IdentityConfig(config_path)
        provider = IdentityProvider(
            provider_type="azure_ad",
            domain="mycompany.onmicrosoft.com",
            client_id="az-client",
            issuer_url="https://login.microsoftonline.com/tenant/v2.0",
        )
        config1.configure(provider)

        config2 = IdentityConfig(config_path)
        loaded = config2.get_provider()
        assert loaded is not None
        assert loaded.provider_type == "azure_ad"
        assert loaded.domain == "mycompany.onmicrosoft.com"

    def test_reconfigure_overwrites(self, config_path):
        config = IdentityConfig(config_path)
        provider1 = IdentityProvider(
            provider_type="okta",
            domain="first.okta.com",
            client_id="first",
            issuer_url="https://first.okta.com",
        )
        config.configure(provider1)

        provider2 = IdentityProvider(
            provider_type="google",
            domain="second.google.com",
            client_id="second",
            issuer_url="https://accounts.google.com",
        )
        config.configure(provider2)

        loaded = config.get_provider()
        assert loaded is not None
        assert loaded.provider_type == "google"
        assert loaded.domain == "second.google.com"

    def test_creates_parent_directories(self, tmp_path):
        deep_path = tmp_path / "a" / "b" / "c" / "identity-config.json"
        config = IdentityConfig(deep_path)
        provider = IdentityProvider(
            provider_type="okta",
            domain="deep.okta.com",
            client_id="deep-id",
            issuer_url="https://deep.okta.com",
        )
        config.configure(provider)
        assert deep_path.exists()

    def test_json_format(self, config_path):
        config = IdentityConfig(config_path)
        provider = IdentityProvider(
            provider_type="okta",
            domain="example.okta.com",
            client_id="test-id",
            issuer_url="https://example.okta.com",
        )
        config.configure(provider)

        data = json.loads(config_path.read_text())
        assert "provider" in data
        assert data["provider"]["provider_type"] == "okta"

    def test_corrupt_json_raises(self, config_path):
        """If identity-config.json is corrupt, raise on load."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("{corrupt")
        with pytest.raises(Exception):
            IdentityConfig(config_path)

    def test_empty_file_raises(self, config_path):
        """If identity-config.json is empty, raise on load."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("")
        with pytest.raises(Exception):
            IdentityConfig(config_path)


# ---------------------------------------------------------------------------
# OIDCVerifier Tests
# ---------------------------------------------------------------------------


class TestOIDCVerifier:
    """Test OIDCVerifier JWT verification with locally-generated tokens."""

    def _make_token(self, private_pem, claims, headers=None):
        """Create a signed JWT with the given claims."""
        return jwt.encode(claims, private_pem, algorithm="RS256", headers=headers)

    def test_verify_valid_token(self, rsa_key_pair):
        private_pem, public_pem = rsa_key_pair
        provider = IdentityProvider(
            provider_type="okta",
            domain="dev-12345.okta.com",
            client_id="abc123",
            issuer_url="https://dev-12345.okta.com/oauth2/default",
        )
        verifier = OIDCVerifier(provider)

        now = int(time.time())
        claims = {
            "sub": "user-001",
            "iss": "https://dev-12345.okta.com/oauth2/default",
            "aud": "abc123",
            "iat": now,
            "exp": now + 3600,
            "email": "alice@example.com",
        }
        token = self._make_token(private_pem, claims)

        result = verifier.verify_token(token, public_key_pem=public_pem)
        assert result["sub"] == "user-001"
        assert result["email"] == "alice@example.com"

    def test_verify_expired_token_raises(self, rsa_key_pair):
        private_pem, public_pem = rsa_key_pair
        provider = IdentityProvider(
            provider_type="okta",
            domain="dev-12345.okta.com",
            client_id="abc123",
            issuer_url="https://dev-12345.okta.com/oauth2/default",
        )
        verifier = OIDCVerifier(provider)

        now = int(time.time())
        claims = {
            "sub": "user-expired",
            "iss": "https://dev-12345.okta.com/oauth2/default",
            "aud": "abc123",
            "iat": now - 7200,
            "exp": now - 3600,  # expired 1 hour ago
        }
        token = self._make_token(private_pem, claims)

        from trustplane.exceptions import TrustPlaneError

        with pytest.raises(TrustPlaneError, match="expired"):
            verifier.verify_token(token, public_key_pem=public_pem)

    def test_verify_wrong_issuer_raises(self, rsa_key_pair):
        private_pem, public_pem = rsa_key_pair
        provider = IdentityProvider(
            provider_type="okta",
            domain="dev-12345.okta.com",
            client_id="abc123",
            issuer_url="https://dev-12345.okta.com/oauth2/default",
        )
        verifier = OIDCVerifier(provider)

        now = int(time.time())
        claims = {
            "sub": "user-wrong-iss",
            "iss": "https://evil.example.com",
            "aud": "abc123",
            "iat": now,
            "exp": now + 3600,
        }
        token = self._make_token(private_pem, claims)

        from trustplane.exceptions import TrustPlaneError

        with pytest.raises(TrustPlaneError, match="issuer"):
            verifier.verify_token(token, public_key_pem=public_pem)

    def test_verify_wrong_audience_raises(self, rsa_key_pair):
        private_pem, public_pem = rsa_key_pair
        provider = IdentityProvider(
            provider_type="okta",
            domain="dev-12345.okta.com",
            client_id="abc123",
            issuer_url="https://dev-12345.okta.com/oauth2/default",
        )
        verifier = OIDCVerifier(provider)

        now = int(time.time())
        claims = {
            "sub": "user-wrong-aud",
            "iss": "https://dev-12345.okta.com/oauth2/default",
            "aud": "wrong-client-id",
            "iat": now,
            "exp": now + 3600,
        }
        token = self._make_token(private_pem, claims)

        from trustplane.exceptions import TrustPlaneError

        with pytest.raises(TrustPlaneError, match="audience"):
            verifier.verify_token(token, public_key_pem=public_pem)

    def test_verify_invalid_signature_raises(self, rsa_key_pair):
        """Token signed with different key should fail verification."""
        private_pem, public_pem = rsa_key_pair

        # Generate a DIFFERENT key pair
        other_private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048
        )
        other_private_pem = other_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        provider = IdentityProvider(
            provider_type="okta",
            domain="dev-12345.okta.com",
            client_id="abc123",
            issuer_url="https://dev-12345.okta.com/oauth2/default",
        )
        verifier = OIDCVerifier(provider)

        now = int(time.time())
        claims = {
            "sub": "user-bad-sig",
            "iss": "https://dev-12345.okta.com/oauth2/default",
            "aud": "abc123",
            "iat": now,
            "exp": now + 3600,
        }
        # Sign with the OTHER key
        token = self._make_token(other_private_pem, claims)

        from trustplane.exceptions import TrustPlaneError

        with pytest.raises(TrustPlaneError, match="[Ss]ignature|[Vv]erification"):
            verifier.verify_token(token, public_key_pem=public_pem)

    def test_verify_malformed_token_raises(self):
        provider = IdentityProvider(
            provider_type="okta",
            domain="dev-12345.okta.com",
            client_id="abc123",
            issuer_url="https://dev-12345.okta.com/oauth2/default",
        )
        verifier = OIDCVerifier(provider)

        from trustplane.exceptions import TrustPlaneError

        with pytest.raises(TrustPlaneError, match="[Tt]oken|[Dd]ecode"):
            verifier.verify_token("not.a.jwt", public_key_pem=b"not-a-key")

    def test_custom_max_age(self, rsa_key_pair):
        """Verify that custom max_age_hours is respected."""
        private_pem, public_pem = rsa_key_pair
        provider = IdentityProvider(
            provider_type="okta",
            domain="dev-12345.okta.com",
            client_id="abc123",
            issuer_url="https://dev-12345.okta.com/oauth2/default",
        )
        # 1-hour max age
        verifier = OIDCVerifier(provider, max_age_hours=1)

        now = int(time.time())
        # Token issued 2 hours ago, expires in 6 hours — valid by exp but too old
        claims = {
            "sub": "user-old",
            "iss": "https://dev-12345.okta.com/oauth2/default",
            "aud": "abc123",
            "iat": now - 7200,
            "exp": now + 21600,
        }
        token = self._make_token(private_pem, claims)

        from trustplane.exceptions import TrustPlaneError

        with pytest.raises(TrustPlaneError, match="age|old"):
            verifier.verify_token(token, public_key_pem=public_pem)

    def test_default_max_age_8_hours(self):
        provider = IdentityProvider(
            provider_type="okta",
            domain="dev-12345.okta.com",
            client_id="abc123",
            issuer_url="https://dev-12345.okta.com/oauth2/default",
        )
        verifier = OIDCVerifier(provider)
        assert verifier.max_age_hours == 8

    def test_max_age_hours_rejects_nan(self):
        import math

        provider = IdentityProvider(
            provider_type="okta",
            domain="dev-12345.okta.com",
            client_id="abc123",
            issuer_url="https://dev-12345.okta.com/oauth2/default",
        )
        with pytest.raises(ValueError, match="must be finite"):
            OIDCVerifier(provider, max_age_hours=float("nan"))

    def test_max_age_hours_rejects_inf(self):
        provider = IdentityProvider(
            provider_type="okta",
            domain="dev-12345.okta.com",
            client_id="abc123",
            issuer_url="https://dev-12345.okta.com/oauth2/default",
        )
        with pytest.raises(ValueError, match="must be finite"):
            OIDCVerifier(provider, max_age_hours=float("inf"))

    def test_max_age_hours_rejects_zero(self):
        provider = IdentityProvider(
            provider_type="okta",
            domain="dev-12345.okta.com",
            client_id="abc123",
            issuer_url="https://dev-12345.okta.com/oauth2/default",
        )
        with pytest.raises(ValueError, match="must be positive"):
            OIDCVerifier(provider, max_age_hours=0)

    def test_verify_token_without_public_key_raises(self, rsa_key_pair):
        """Calling verify_token without providing a public key should raise."""
        private_pem, _ = rsa_key_pair
        provider = IdentityProvider(
            provider_type="okta",
            domain="dev-12345.okta.com",
            client_id="abc123",
            issuer_url="https://dev-12345.okta.com/oauth2/default",
        )
        verifier = OIDCVerifier(provider)

        now = int(time.time())
        claims = {
            "sub": "user-001",
            "iss": "https://dev-12345.okta.com/oauth2/default",
            "aud": "abc123",
            "iat": now,
            "exp": now + 3600,
        }
        token = self._make_token(private_pem, claims)

        from trustplane.exceptions import TrustPlaneError

        with pytest.raises(TrustPlaneError, match="public.key|JWKS"):
            verifier.verify_token(token)


# ---------------------------------------------------------------------------
# Helpers: JWK generation from RSA keys
# ---------------------------------------------------------------------------


def _rsa_key_to_jwk(public_key, kid: str, alg: str = "RS256") -> dict:
    """Convert an RSA public key to a JWK dict."""
    numbers = public_key.public_numbers()
    # Encode n and e as base64url without padding (per RFC 7518)
    import base64

    def _b64url(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    n_bytes = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, byteorder="big")
    e_bytes = numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, byteorder="big")
    return {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": alg,
        "n": _b64url(n_bytes),
        "e": _b64url(e_bytes),
    }


@pytest.fixture
def rsa_key_and_jwk():
    """Generate an RSA key pair and its corresponding JWK dict."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    public_key = private_key.public_key()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    jwk = _rsa_key_to_jwk(public_key, kid="test-key-1")
    return private_pem, jwk


# ---------------------------------------------------------------------------
# JWKSProvider mock-heavy tests moved to tests/unit/test_identity_jwks.py
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# OIDCVerifier + JWKSProvider Integration Tests
# ---------------------------------------------------------------------------


class TestOIDCVerifierWithJWKS:
    """Test OIDCVerifier using JWKSProvider for key resolution."""

    def _make_token(self, private_pem, claims, kid="test-key-1", alg="RS256"):
        """Create a signed JWT with a kid header."""
        return jwt.encode(claims, private_pem, algorithm=alg, headers={"kid": kid})

    def test_verify_via_jwks(self, rsa_key_and_jwk):
        """Full verification using JWKS-resolved key."""
        private_pem, jwk = rsa_key_and_jwk

        provider = IdentityProvider(
            provider_type="okta",
            domain="dev-12345.okta.com",
            client_id="abc123",
            issuer_url="https://dev-12345.okta.com/oauth2/default",
        )

        jwks_provider = JWKSProvider("https://dev-12345.okta.com/oauth2/default")

        # Pre-populate the JWKS cache so we don't need real HTTP.
        jwks_provider._keys = {"test-key-1": jwk}
        jwks_provider._last_fetch_time = time.monotonic()

        verifier = OIDCVerifier(provider, jwks_provider=jwks_provider)

        now = int(time.time())
        claims = {
            "sub": "user-001",
            "iss": "https://dev-12345.okta.com/oauth2/default",
            "aud": "abc123",
            "iat": now,
            "exp": now + 3600,
        }
        token = self._make_token(private_pem, claims, kid="test-key-1")

        result = verifier.verify_token(token)
        assert result["sub"] == "user-001"

    def test_public_key_pem_takes_precedence_over_jwks(self, rsa_key_pair):
        """When public_key_pem is provided, it takes precedence over JWKS."""
        private_pem, public_pem = rsa_key_pair

        provider = IdentityProvider(
            provider_type="okta",
            domain="dev-12345.okta.com",
            client_id="abc123",
            issuer_url="https://dev-12345.okta.com/oauth2/default",
        )

        # Create a JWKSProvider that would fail if called.
        jwks_provider = JWKSProvider("https://dev-12345.okta.com/oauth2/default")

        verifier = OIDCVerifier(provider, jwks_provider=jwks_provider)

        now = int(time.time())
        claims = {
            "sub": "user-001",
            "iss": "https://dev-12345.okta.com/oauth2/default",
            "aud": "abc123",
            "iat": now,
            "exp": now + 3600,
        }
        # No kid header needed when using explicit PEM.
        token = jwt.encode(claims, private_pem, algorithm="RS256")

        result = verifier.verify_token(token, public_key_pem=public_pem)
        assert result["sub"] == "user-001"

    def test_missing_kid_header_raises(self, rsa_key_pair):
        """Token without kid header raises when using JWKS."""
        private_pem, _ = rsa_key_pair

        provider = IdentityProvider(
            provider_type="okta",
            domain="dev-12345.okta.com",
            client_id="abc123",
            issuer_url="https://dev-12345.okta.com/oauth2/default",
        )

        jwks_provider = JWKSProvider("https://dev-12345.okta.com/oauth2/default")

        verifier = OIDCVerifier(provider, jwks_provider=jwks_provider)

        now = int(time.time())
        claims = {
            "sub": "user-001",
            "iss": "https://dev-12345.okta.com/oauth2/default",
            "aud": "abc123",
            "iat": now,
            "exp": now + 3600,
        }
        # No kid header.
        token = jwt.encode(claims, private_pem, algorithm="RS256")

        from trustplane.exceptions import TrustPlaneError

        with pytest.raises(TrustPlaneError, match="kid"):
            verifier.verify_token(token)

    def test_unsupported_jwt_algorithm_raises(self, rsa_key_pair):
        """Token with unsupported algorithm raises."""
        private_pem, _ = rsa_key_pair

        provider = IdentityProvider(
            provider_type="okta",
            domain="dev-12345.okta.com",
            client_id="abc123",
            issuer_url="https://dev-12345.okta.com/oauth2/default",
        )

        jwks_provider = JWKSProvider("https://dev-12345.okta.com/oauth2/default")

        verifier = OIDCVerifier(provider, jwks_provider=jwks_provider)

        now = int(time.time())
        claims = {
            "sub": "user-001",
            "iss": "https://dev-12345.okta.com/oauth2/default",
            "aud": "abc123",
            "iat": now,
            "exp": now + 3600,
        }
        # PS256 is not in SUPPORTED_JWKS_ALGORITHMS.
        token = jwt.encode(
            claims, private_pem, algorithm="PS256", headers={"kid": "k1"}
        )

        from trustplane.exceptions import TrustPlaneError

        with pytest.raises(TrustPlaneError, match="not supported"):
            verifier.verify_token(token)

    def test_jwks_lookup_failure_raises_token_error(self, rsa_key_pair):
        """JWKSError during key lookup is wrapped as TokenVerificationError."""
        private_pem, _ = rsa_key_pair

        provider = IdentityProvider(
            provider_type="okta",
            domain="dev-12345.okta.com",
            client_id="abc123",
            issuer_url="https://dev-12345.okta.com/oauth2/default",
        )

        # Use a subclass instead of mock — NO MOCKING in integration tests.
        class _FailingJWKSProvider(JWKSProvider):
            def get_key(self, kid: str) -> dict:
                raise JWKSError("connection refused")

        failing_jwks = _FailingJWKSProvider("https://dev-12345.okta.com/oauth2/default")

        verifier = OIDCVerifier(provider, jwks_provider=failing_jwks)

        now = int(time.time())
        claims = {
            "sub": "user-001",
            "iss": "https://dev-12345.okta.com/oauth2/default",
            "aud": "abc123",
            "iat": now,
            "exp": now + 3600,
        }
        token = self._make_token(private_pem, claims, kid="k1")

        from trustplane.exceptions import TrustPlaneError

        with pytest.raises(TrustPlaneError, match="JWKS key lookup failed"):
            verifier.verify_token(token)

    def test_no_key_source_raises(self):
        """Verifier with no JWKS and no PEM raises TokenVerificationError."""
        provider = IdentityProvider(
            provider_type="okta",
            domain="dev-12345.okta.com",
            client_id="abc123",
            issuer_url="https://dev-12345.okta.com/oauth2/default",
        )
        # No jwks_provider.
        verifier = OIDCVerifier(provider)

        from trustplane.exceptions import TrustPlaneError

        with pytest.raises(TrustPlaneError, match="JWKS provider"):
            verifier.verify_token("eyJ.eyJ.sig")
